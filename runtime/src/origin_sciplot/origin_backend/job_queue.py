"""Cross-process coordination for the local Origin automation lifecycle.

Origin Automation is deliberately serialized per Windows user.  The lock is an
OS-held lock, so it is released automatically when a worker exits or crashes.
Windows uses a session-local named mutex; other platforms use a byte-range lock.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from origin_sciplot.origin_backend.safe_errors import OriginEnvironmentError

DEFAULT_ORIGIN_JOB_MAX_WAIT_SECONDS = 1800.0


@dataclass(frozen=True)
class OriginJobLease:
    """Evidence that the current worker owns the Origin automation slot."""

    job_kind: str
    waited: bool
    wait_seconds: float


def default_origin_job_lock_path() -> Path:
    """Return one stable lock path shared by EditaPlot clones for this user."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:
        root = Path(tempfile.gettempdir())
    return root / "EditaPlot" / "locks" / "origin-automation-v1.lock"


def _prepare_lock_file(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
    handle.seek(0)
    return handle


class _LockHandle(Protocol):
    def try_acquire(self) -> bool: ...

    def release(self) -> None: ...

    def close(self) -> None: ...


class _WindowsMutex:
    _WAIT_OBJECT_0 = 0x00000000
    _WAIT_ABANDONED = 0x00000080
    _WAIT_TIMEOUT = 0x00000102

    def __init__(self, namespace_key: str) -> None:
        import ctypes
        from ctypes import wintypes

        digest = hashlib.sha256(namespace_key.encode("utf-8")).hexdigest()[:24]
        name = rf"Local\EditaPlot.OriginAutomation.v1.{digest}"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._kernel32 = kernel32
        self._handle = handle

    def try_acquire(self) -> bool:
        result = self._kernel32.WaitForSingleObject(self._handle, 0)
        if result in {self._WAIT_OBJECT_0, self._WAIT_ABANDONED}:
            return True
        if result == self._WAIT_TIMEOUT:
            return False
        import ctypes

        raise ctypes.WinError(ctypes.get_last_error())

    def release(self) -> None:
        if not self._kernel32.ReleaseMutex(self._handle):
            import ctypes

            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        self._kernel32.CloseHandle(self._handle)


class _FileLock:
    def __init__(self, lock_path: Path) -> None:
        self._handle = _prepare_lock_file(lock_path)

    def try_acquire(self) -> bool:
        return _try_lock(self._handle)

    def release(self) -> None:
        _unlock(self._handle)

    def close(self) -> None:
        self._handle.close()


def _open_lock(lock_path: Path) -> _LockHandle:
    if os.name == "nt":
        return _WindowsMutex(str(lock_path).casefold())
    return _FileLock(lock_path)


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def origin_job_slot(
    *,
    job_kind: str = "origin",
    lock_path: str | Path | None = None,
    poll_seconds: float = 0.25,
    wait_report_interval: float = 10.0,
    max_wait_seconds: float = DEFAULT_ORIGIN_JOB_MAX_WAIT_SECONDS,
    on_wait: Callable[[float], None] | None = None,
) -> Iterator[OriginJobLease]:
    """Wait for and hold the current user's exclusive Origin automation slot.

    Only the calling worker is paused.  Data inspection and planning should be
    completed before entering this context manager.
    """

    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be greater than zero")
    if wait_report_interval <= 0:
        raise ValueError("wait_report_interval must be greater than zero")
    if max_wait_seconds <= 0:
        raise ValueError("max_wait_seconds must be greater than zero")

    resolved_path = (
        Path(lock_path).expanduser().resolve()
        if lock_path is not None
        else default_origin_job_lock_path()
    )
    handle = _open_lock(resolved_path)
    acquired = False
    waited = False
    started = time.monotonic()
    next_report = 0.0
    try:
        while not handle.try_acquire():
            waited = True
            elapsed = time.monotonic() - started
            if elapsed >= max_wait_seconds:
                raise OriginEnvironmentError(
                    "Waiting for another EditaPlot Origin job exceeded 30 minutes; "
                    "this waiting job stopped without interrupting the active job.",
                    code="origin_job_queue_timeout",
                    stage="wait_origin_job_slot",
                )
            if on_wait is not None and elapsed >= next_report:
                on_wait(elapsed)
                next_report = elapsed + wait_report_interval
            time.sleep(poll_seconds)

        acquired = True
        wait_seconds = time.monotonic() - started if waited else 0.0
        yield OriginJobLease(
            job_kind=job_kind,
            waited=waited,
            wait_seconds=round(wait_seconds, 3),
        )
    finally:
        body_failed = sys.exc_info()[0] is not None
        cleanup_error: BaseException | None = None
        if acquired:
            try:
                handle.release()
            except BaseException as exc:  # noqa: BLE001 - preserve an active body error
                cleanup_error = exc
        try:
            handle.close()
        except BaseException as exc:  # noqa: BLE001 - always attempt handle closure
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None and not body_failed:
            raise OriginEnvironmentError(
                "EditaPlot could not release its Origin job slot cleanly.",
                code="origin_job_queue_cleanup_failed",
                stage="release_origin_job_slot",
            ) from cleanup_error


__all__ = [
    "OriginJobLease",
    "DEFAULT_ORIGIN_JOB_MAX_WAIT_SECONDS",
    "default_origin_job_lock_path",
    "origin_job_slot",
]
