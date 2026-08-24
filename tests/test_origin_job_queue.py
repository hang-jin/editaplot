from __future__ import annotations

import multiprocessing
import os
import sys
import threading
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import job_queue  # noqa: E402
from origin_sciplot.origin_backend.job_queue import (  # noqa: E402
    DEFAULT_ORIGIN_JOB_MAX_WAIT_SECONDS,
    origin_job_slot,
)
from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginEnvironmentError,
)


def _hold_origin_slot(
    lock_path: str,
    acquired: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    with origin_job_slot(lock_path=lock_path, poll_seconds=0.01):
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("test did not release the Origin job slot")


def _crash_while_holding_origin_slot(
    lock_path: str,
    acquired: multiprocessing.synchronize.Event,
    crash_now: multiprocessing.synchronize.Event,
) -> None:
    with origin_job_slot(lock_path=lock_path, poll_seconds=0.01):
        acquired.set()
        if not crash_now.wait(10):
            raise RuntimeError("test did not trigger the controlled crash")
        os._exit(23)


def test_origin_job_slot_is_immediate_when_idle(tmp_path: Path) -> None:
    assert DEFAULT_ORIGIN_JOB_MAX_WAIT_SECONDS == 1800.0
    lock_path = tmp_path / "origin.lock"
    reports: list[float] = []

    with origin_job_slot(
        job_kind="render",
        lock_path=lock_path,
        poll_seconds=0.01,
        on_wait=reports.append,
    ) as lease:
        assert lease.job_kind == "render"
        assert lease.waited is False
        assert lease.wait_seconds == 0.0

    assert reports == []


def test_origin_job_slot_waits_for_another_process_then_acquires(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    lock_path = tmp_path / "origin.lock"
    holder = context.Process(
        target=_hold_origin_slot,
        args=(str(lock_path), acquired, release),
    )
    holder.start()
    assert acquired.wait(10)

    wait_observed = threading.Event()
    finished = threading.Event()
    result: dict[str, object] = {}

    def wait_for_slot() -> None:
        try:
            with origin_job_slot(
                job_kind="smoke",
                lock_path=lock_path,
                poll_seconds=0.01,
                wait_report_interval=0.05,
                on_wait=lambda _elapsed: wait_observed.set(),
            ) as lease:
                result["lease"] = lease
        except BaseException as exc:  # noqa: BLE001 - forwarded to the test thread
            result["error"] = exc
        finally:
            finished.set()

    waiter = threading.Thread(target=wait_for_slot, daemon=True)
    waiter.start()
    try:
        assert wait_observed.wait(10)
        assert not finished.is_set()
        release.set()
        assert finished.wait(10)
    finally:
        release.set()
        holder.join(10)
        waiter.join(10)

    assert holder.exitcode == 0
    assert "error" not in result
    lease = result["lease"]
    assert lease.waited is True
    assert lease.wait_seconds >= 0.0


def test_wait_timeout_stops_only_waiter_and_preserves_active_job(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    lock_path = tmp_path / "origin.lock"
    holder = context.Process(
        target=_hold_origin_slot,
        args=(str(lock_path), acquired, release),
    )
    holder.start()
    assert acquired.wait(10)

    try:
        with pytest.raises(OriginEnvironmentError) as raised:
            with origin_job_slot(
                lock_path=lock_path,
                poll_seconds=0.01,
                max_wait_seconds=0.05,
            ):
                raise AssertionError("timed-out waiter must not acquire the slot")
        assert raised.value.code == "origin_job_queue_timeout"
        assert raised.value.stage == "wait_origin_job_slot"
        assert holder.is_alive()
    finally:
        release.set()
        holder.join(10)

    assert holder.exitcode == 0
    with origin_job_slot(lock_path=lock_path, poll_seconds=0.01) as lease:
        assert lease.waited is False


def test_wait_limit_does_not_time_out_the_slot_body(tmp_path: Path) -> None:
    with origin_job_slot(
        lock_path=tmp_path / "origin.lock",
        poll_seconds=0.01,
        max_wait_seconds=0.001,
    ) as lease:
        threading.Event().wait(0.02)
        assert lease.waited is False


def test_invalid_wait_limit_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_wait_seconds"):
        with origin_job_slot(
            lock_path=tmp_path / "origin.lock",
            max_wait_seconds=0,
        ):
            raise AssertionError("invalid queue settings must not enter the body")


def test_lock_cleanup_does_not_replace_a_render_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenCleanupLock:
        closed = False

        def try_acquire(self) -> bool:
            return True

        def release(self) -> None:
            raise OSError("injected release failure")

        def close(self) -> None:
            self.closed = True

    lock = BrokenCleanupLock()
    monkeypatch.setattr(job_queue, "_open_lock", lambda _path: lock)

    with pytest.raises(RuntimeError, match="primary render failure"):
        with origin_job_slot(lock_path=tmp_path / "origin.lock"):
            raise RuntimeError("primary render failure")

    assert lock.closed is True


def test_lock_cleanup_failure_is_structured_after_successful_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenCleanupLock:
        closed = False

        def try_acquire(self) -> bool:
            return True

        def release(self) -> None:
            raise OSError("injected release failure")

        def close(self) -> None:
            self.closed = True

    lock = BrokenCleanupLock()
    monkeypatch.setattr(job_queue, "_open_lock", lambda _path: lock)

    with pytest.raises(OriginEnvironmentError) as raised:
        with origin_job_slot(lock_path=tmp_path / "origin.lock"):
            pass

    assert raised.value.code == "origin_job_queue_cleanup_failed"
    assert raised.value.stage == "release_origin_job_slot"
    assert lock.closed is True


def test_origin_job_slot_releases_after_exception(tmp_path: Path) -> None:
    lock_path = tmp_path / "origin.lock"

    with pytest.raises(RuntimeError, match="render failed"):
        with origin_job_slot(lock_path=lock_path, poll_seconds=0.01):
            raise RuntimeError("render failed")

    with origin_job_slot(lock_path=lock_path, poll_seconds=0.01) as lease:
        assert lease.waited is False


def test_origin_job_slot_is_released_by_os_when_owner_process_crashes(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    crash_now = context.Event()
    lock_path = tmp_path / "origin.lock"
    holder = context.Process(
        target=_crash_while_holding_origin_slot,
        args=(str(lock_path), acquired, crash_now),
    )
    holder.start()
    assert acquired.wait(10)

    wait_observed = threading.Event()
    finished = threading.Event()
    result: dict[str, object] = {}

    def wait_for_slot() -> None:
        try:
            with origin_job_slot(
                lock_path=lock_path,
                poll_seconds=0.01,
                on_wait=lambda _elapsed: wait_observed.set(),
            ) as lease:
                result["lease"] = lease
        except BaseException as exc:  # noqa: BLE001 - forwarded to the test thread
            result["error"] = exc
        finally:
            finished.set()

    waiter = threading.Thread(target=wait_for_slot, daemon=True)
    waiter.start()
    try:
        assert wait_observed.wait(10)
        crash_now.set()
        holder.join(10)
        assert holder.exitcode == 23
        assert finished.wait(10)
    finally:
        crash_now.set()
        holder.join(10)
        waiter.join(10)

    assert "error" not in result
    lease = result["lease"]
    assert lease.waited is True
