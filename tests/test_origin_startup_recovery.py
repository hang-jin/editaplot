from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginEnvironmentError,
    WorkerExitCode,
    classify_origin_activation_error,
    origin_activation_recovery,
)
from origin_sciplot.origin_backend.session import OriginSession  # noqa: E402
from origin_sciplot.workers import (  # noqa: E402
    origin_smoke_worker,
    run_template_worker,
)


class _AttributeActivationError(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("attribute", "value", "expected"),
    [
        ("hresult", -2146959355, "origin_com_server_execution_failed"),
        ("HResult", 0x80040154, "origin_com_class_not_registered"),
        ("winerror", 0x80070005, "origin_com_activation_access_denied"),
        ("scode", 0x800706BA, "origin_com_server_unavailable"),
    ],
)
def test_activation_classifier_reads_hresult_attributes(
    attribute: str,
    value: int,
    expected: str,
) -> None:
    error = _AttributeActivationError("redacted local detail")
    setattr(error, attribute, value)

    assert classify_origin_activation_error(error) == expected


def test_generic_activation_failure_has_one_bounded_fresh_directory_recovery() -> None:
    assert origin_activation_recovery("origin_instance_start_failed") == {
        "action": "retry_in_active_user_context_with_fresh_output_directory",
        "maximum_attempts": 1,
        "requires_user_approval": True,
        "must_preserve_execution_context_for_render": True,
        "must_use_fresh_output_directory": True,
        "preserve_previous_diagnostics": True,
        "automatic_fallback_to_attach_existing": False,
        "system_configuration_changes_allowed": False,
    }


@pytest.mark.parametrize(
    ("failure_stage", "expected_code", "expected_stage"),
    [
        ("read_version", "origin_version_read_failed", "read_version"),
        (
            "initialize_project",
            "origin_project_initialization_failed",
            "initialize_project",
        ),
    ],
)
def test_keep_open_entry_failure_still_exits_owned_instance(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    expected_code: str,
    expected_stage: str,
) -> None:
    events: list[object] = []

    def lt_float(formula: str) -> float:
        events.append(("lt_float", formula))
        if formula == "run.isOCready()":
            return 1.0
        assert formula == "@V"
        if failure_stage == "read_version":
            raise RuntimeError("redacted version failure")
        return 10.15

    def new(**kwargs: object) -> None:
        events.append(("new", kwargs))
        if failure_stage == "initialize_project":
            raise RuntimeError("redacted project failure")

    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_exec=lambda command: events.append(("lt_exec", command)) or True,
        lt_float=lt_float,
        new=new,
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession(keep_open=True).__enter__()

    assert raised.value.code == expected_code
    assert raised.value.stage == expected_stage
    assert "exit" in events
    assert ("show", True) not in events


@pytest.mark.parametrize("ready_value", [0.0, float("nan"), float("inf")])
def test_origin_c_not_ready_exits_without_reading_version_or_creating_project(
    monkeypatch: pytest.MonkeyPatch,
    ready_value: float,
) -> None:
    events: list[object] = []

    def lt_float(formula: str) -> float:
        events.append(("lt_float", formula))
        if formula == "run.isOCready()":
            return ready_value
        pytest.fail(f"unexpected LabTalk read after failed readiness: {formula}")

    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_exec=lambda command: events.append(("lt_exec", command)) or True,
        lt_float=lt_float,
        new=lambda **_kwargs: pytest.fail("project must not be reset before Origin is ready"),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession(keep_open=True).__enter__()

    assert raised.value.code == "origin_startup_not_ready"
    assert raised.value.stage == "wait_origin_ready"
    assert events == [
        ("show", False),
        ("lt_exec", "sec -poc 30;"),
        ("lt_float", "run.isOCready()"),
        "exit",
    ]


def test_origin_c_wait_command_failure_does_not_read_stale_ready_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_exec=lambda command: events.append(("lt_exec", command)) or False,
        lt_float=lambda formula: pytest.fail(f"stale readiness must not be read: {formula}"),
        new=lambda **_kwargs: pytest.fail("project must not be reset before Origin is ready"),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession(keep_open=True).__enter__()

    assert raised.value.code == "origin_startup_not_ready"
    assert raised.value.stage == "wait_origin_ready"
    assert events == [
        ("show", False),
        ("lt_exec", "sec -poc 30;"),
        "exit",
    ]


@pytest.mark.parametrize(
    "first_error",
    [
        RuntimeError("redacted generic startup failure"),
        RuntimeError(0x80080005, "redacted server startup failure"),
    ],
)
def test_retryable_activation_failure_is_cleaned_then_retried_once(
    monkeypatch: pytest.MonkeyPatch,
    first_error: RuntimeError,
) -> None:
    events: list[object] = []
    attempts = 0

    def set_show(show: bool) -> None:
        nonlocal attempts
        events.append(("show", show))
        if show is False:
            attempts += 1
            if attempts == 1:
                raise first_error

    def lt_float(formula: str) -> float:
        events.append(("lt_float", formula))
        return 1.0 if formula == "run.isOCready()" else 10.15

    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=set_show,
        lt_exec=lambda command: events.append(("lt_exec", command)) or True,
        lt_float=lt_float,
        new=lambda **kwargs: events.append(("new", kwargs)),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with OriginSession(keep_open=False) as session:
        assert session.environment is not None

    assert attempts == 2
    assert events.count("exit") == 2
    assert events[:3] == [("show", False), "exit", ("show", False)]


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ((0x80040154, "redacted class failure"), "origin_com_class_not_registered"),
        ((0x80070005, "redacted access failure"), "origin_com_activation_access_denied"),
    ],
)
def test_nonretryable_activation_failure_is_not_automatically_retried(
    monkeypatch: pytest.MonkeyPatch,
    payload: tuple[object, ...],
    expected_code: str,
) -> None:
    attempts = 0
    exits = 0

    def set_show(_show: bool) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError(*payload)

    def exit_origin() -> None:
        nonlocal exits
        exits += 1

    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=set_show,
        exit=exit_origin,
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession().__enter__()

    assert raised.value.code == expected_code
    assert attempts == 1
    assert exits == 1


def test_retryable_activation_failure_stops_when_partial_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    exits = 0

    def set_show(_show: bool) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError(
            "private activation detail 0x80080005 "
            + "\\".join((f"{chr(67)}:", "Users", "Private", "origin.ini"))
        )

    def fail_exit() -> None:
        nonlocal exits
        exits += 1
        raise RuntimeError(
            "private cleanup detail 0x80070005 "
            + "\\".join((f"{chr(67)}:", "Users", "Private", "cleanup.log"))
        )

    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=set_show,
        exit=fail_exit,
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession().__enter__()

    assert raised.value.code == "origin_activation_cleanup_failed"
    assert raised.value.stage == "cleanup_partial_instance"
    assert raised.value.diagnostics == {
        "primary_activation_code": "origin_com_server_execution_failed",
        "primary_activation_stage": "create_instance",
        "cleanup_error_code": "origin_com_activation_access_denied",
        "cleanup_error_stage": "cleanup_partial_instance",
    }
    assert "Private" not in str(raised.value.diagnostics)
    assert "0x80080005" not in str(raised.value.diagnostics)
    assert "0x80070005" not in str(raised.value.diagnostics)
    assert origin_activation_recovery(raised.value.code) is None
    assert attempts == 1
    assert exits == 1


def test_smoke_and_render_workers_emit_the_same_activation_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        origin_smoke_worker,
        "require_interactive_origin_context",
        lambda: None,
    )
    monkeypatch.setattr(
        run_template_worker,
        "require_interactive_origin_context",
        lambda: None,
    )

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise OriginEnvironmentError(
            "Origin Automation connection failed",
            code="origin_instance_start_failed",
            stage="create_instance",
        )

    monkeypatch.setattr(origin_smoke_worker, "run_origin_smoke", fail)
    smoke_code = origin_smoke_worker.main(
        ["--output-dir", str(tmp_path / "smoke")]
    )
    smoke_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    monkeypatch.setattr(run_template_worker, "_load_template_manifest", fail)
    render_code = run_template_worker.main(
        [
            "--template-id",
            "test-template",
            "--input-file",
            str(tmp_path / "unused.csv"),
        ]
    )
    render_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert smoke_code == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert render_code == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert smoke_lines[-1]["code"] == render_lines[-1]["code"]
    assert smoke_lines[-1]["stage"] == render_lines[-1]["stage"]
    assert smoke_lines[-1]["recovery"] == render_lines[-1]["recovery"]


def test_smoke_and_render_workers_preserve_stable_cleanup_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        origin_smoke_worker,
        "require_interactive_origin_context",
        lambda: None,
    )
    monkeypatch.setattr(
        run_template_worker,
        "require_interactive_origin_context",
        lambda: None,
    )
    diagnostics = {
        "primary_activation_code": "origin_com_server_execution_failed",
        "primary_activation_stage": "create_instance",
        "cleanup_error_code": "origin_com_activation_access_denied",
        "cleanup_error_stage": "cleanup_partial_instance",
    }

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise OriginEnvironmentError(
            "Origin startup cleanup failed",
            code="origin_activation_cleanup_failed",
            stage="cleanup_partial_instance",
            diagnostics=diagnostics,
        )

    monkeypatch.setattr(origin_smoke_worker, "run_origin_smoke", fail)
    smoke_code = origin_smoke_worker.main(
        ["--output-dir", str(tmp_path / "smoke")]
    )
    smoke_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    monkeypatch.setattr(run_template_worker, "_load_template_manifest", fail)
    render_code = run_template_worker.main(
        [
            "--template-id",
            "test-template",
            "--input-file",
            str(tmp_path / "unused.csv"),
        ]
    )
    render_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert smoke_code == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert render_code == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert smoke_lines[-1]["diagnostics"] == diagnostics
    assert render_lines[-1]["diagnostics"] == diagnostics
    assert "recovery" not in smoke_lines[-1]
    assert "recovery" not in render_lines[-1]
