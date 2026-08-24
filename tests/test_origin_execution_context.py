from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import execution_context  # noqa: E402
from origin_sciplot.origin_backend.execution_context import (  # noqa: E402
    OriginExecutionContext,
    classify_origin_execution_context,
    detect_origin_execution_context,
    require_interactive_origin_context,
)
from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginEnvironmentError,
    WorkerExitCode,
)
from origin_sciplot.workers import (  # noqa: E402
    origin_smoke_worker,
    run_template_worker,
)

SYNTHETIC_PROFILE = "\\".join((f"{chr(67)}:", "Users", "Example", "Profile"))


@pytest.mark.parametrize(
    "account_name",
    [
        "CodexSandboxOffline",
        "DESKTOP-TEST\\CodexSandboxOffline",
        "CodexSandbox",
        "desktop-test\\CODEXSANDBOX-42",
    ],
)
def test_windows_codex_sandbox_accounts_are_detected(account_name: str) -> None:
    context = classify_origin_execution_context(
        os_name="nt",
        account_name=account_name,
        identity_source="test",
    )

    assert context.is_windows is True
    assert context.is_codex_sandbox is True


def test_normal_windows_account_is_not_treated_as_codex_sandbox() -> None:
    context = classify_origin_execution_context(
        os_name="nt",
        account_name="DESKTOP-TEST\\JGH",
        identity_source="test",
    )

    assert context.is_windows is True
    assert context.is_codex_sandbox is False
    assert context.to_public_dict() == {
        "status": "interactive_user",
        "requires_current_user_approval": False,
    }
    assert "JGH" not in json.dumps(context.to_public_dict())


def test_non_windows_process_is_not_blocked_by_a_similar_account_name() -> None:
    context = classify_origin_execution_context(
        os_name="posix",
        account_name="CodexSandboxOffline",
        identity_source="test",
    )

    assert context.is_windows is False
    assert context.is_codex_sandbox is False
    assert context.to_public_dict() == {
        "status": "non_windows",
        "requires_current_user_approval": False,
    }


def test_detection_prefers_winapi_token_identity_over_environment_and_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USERNAME", "JGH")
    monkeypatch.setenv("USERPROFILE", SYNTHETIC_PROFILE)
    monkeypatch.setattr(
        execution_context,
        "_windows_token_name_from_winapi",
        lambda: "CodexSandboxOffline",
    )
    monkeypatch.setattr(execution_context.os, "getlogin", lambda: "JGH")

    context = detect_origin_execution_context(os_name="nt")

    assert context.account_name == "CodexSandboxOffline"
    assert context.identity_source == "winapi_token"
    assert context.is_codex_sandbox is True
    assert context.to_public_dict() == {
        "status": "codex_sandbox",
        "requires_current_user_approval": True,
    }


def test_detection_falls_back_to_os_getlogin_when_winapi_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution_context,
        "_windows_token_name_from_winapi",
        lambda: None,
    )
    monkeypatch.setattr(
        execution_context.os,
        "getlogin",
        lambda: "DESKTOP-TEST\\CodexSandboxOffline",
    )

    context = detect_origin_execution_context(os_name="nt")

    assert context.identity_source == "os.getlogin"
    assert context.is_codex_sandbox is True


def test_windows_identity_unavailable_is_reported_without_profile_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USERNAME", "JGH")
    monkeypatch.setenv("USERPROFILE", SYNTHETIC_PROFILE)
    monkeypatch.setattr(
        execution_context,
        "_windows_token_name_from_winapi",
        lambda: None,
    )

    def unavailable_login() -> str:
        raise OSError("login unavailable")

    monkeypatch.setattr(execution_context.os, "getlogin", unavailable_login)

    context = detect_origin_execution_context(os_name="nt")

    assert context.to_public_dict() == {
        "status": "unknown",
        "requires_current_user_approval": False,
    }
    assert "JGH" not in json.dumps(context.to_public_dict())


def test_codex_sandbox_preflight_has_stable_actionable_error() -> None:
    context = OriginExecutionContext(
        is_windows=True,
        account_name="CodexSandboxOffline",
        identity_source="test",
        is_codex_sandbox=True,
    )

    with pytest.raises(OriginEnvironmentError) as raised:
        require_interactive_origin_context(context)

    assert raised.value.code == "origin_codex_sandbox_context"
    assert raised.value.stage == "validate_execution_context"
    assert raised.value.diagnostics == {
        "execution_context": "codex_sandbox",
        "requires_user_approval": True,
    }
    assert "approve" in str(raised.value).lower()


def test_unknown_windows_identity_stops_before_origin() -> None:
    context = OriginExecutionContext(
        is_windows=True,
        account_name=None,
        identity_source="unavailable",
        is_codex_sandbox=False,
    )

    with pytest.raises(OriginEnvironmentError) as raised:
        require_interactive_origin_context(context)

    assert raised.value.code == "origin_execution_context_unknown"
    assert raised.value.stage == "validate_execution_context"
    assert raised.value.diagnostics == {"execution_context": "unknown"}


def _raise_sandbox_preflight() -> None:
    raise OriginEnvironmentError(
        "Origin must run in the signed-in Windows user context; "
        "approve the local Origin command in Codex and retry.",
        code="origin_codex_sandbox_context",
        stage="validate_execution_context",
    )


def test_smoke_worker_stops_before_origin_in_codex_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    origin_called = False

    def forbidden_origin_call(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal origin_called
        origin_called = True
        raise AssertionError("Origin must not be called from the Codex sandbox")

    monkeypatch.setattr(
        origin_smoke_worker,
        "require_interactive_origin_context",
        _raise_sandbox_preflight,
    )
    monkeypatch.setattr(origin_smoke_worker, "run_origin_smoke", forbidden_origin_call)

    returncode = origin_smoke_worker.main(["--output-dir", str(tmp_path / "smoke")])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert returncode == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert origin_called is False
    assert lines[-1]["code"] == "origin_codex_sandbox_context"
    assert lines[-1]["stage"] == "validate_execution_context"
    assert lines[-1]["recovery"]["action"] == (
        "rerun_origin_command_with_codex_user_approval"
    )


def test_render_worker_stops_before_origin_call_in_codex_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin_called = False

    def forbidden_origin_call() -> object:
        nonlocal origin_called
        origin_called = True
        raise AssertionError("Origin must not be called from the Codex sandbox")

    monkeypatch.setattr(
        run_template_worker,
        "require_interactive_origin_context",
        _raise_sandbox_preflight,
    )
    with pytest.raises(OriginEnvironmentError) as raised:
        run_template_worker._run_origin_draw_export_verify(
            forbidden_origin_call,
            lambda _payload: {},
        )

    assert origin_called is False
    assert raised.value.code == "origin_codex_sandbox_context"
    assert raised.value.stage == "validate_execution_context"


def test_render_main_stops_before_output_directory_in_codex_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    output_called = False

    def forbidden_output(*_args: object, **_kwargs: object) -> object:
        nonlocal output_called
        output_called = True
        raise AssertionError("sandbox preflight must precede output creation")

    monkeypatch.setattr(
        run_template_worker,
        "require_interactive_origin_context",
        _raise_sandbox_preflight,
    )
    monkeypatch.setattr(
        run_template_worker,
        "prepare_scientific",
        lambda *_args, **_kwargs: SimpleNamespace(requires_confirmation=False),
    )
    monkeypatch.setattr(run_template_worker, "create_run_output", forbidden_output)

    returncode = run_template_worker.main(
        ["--template-id", "bar", "--input-file", str(source)]
    )
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert returncode == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert output_called is False
    assert lines[-1]["code"] == "origin_codex_sandbox_context"
    assert lines[-1]["stage"] == "validate_execution_context"
