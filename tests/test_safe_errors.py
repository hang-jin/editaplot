from __future__ import annotations

import sys
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    classify_origin_activation_error,
    origin_activation_recovery,
)
from origin_sciplot.project_paths import redact_windows_paths  # noqa: E402

PRIVATE_DRIVE_BACKSLASH = "\\".join(
    (f"{chr(67)}:", "Users", "Somebody", "Private", "result.csv")
)
PRIVATE_DRIVE_SLASH = "/".join(
    (f"{chr(67)}:", "Users", "Somebody", "Private", "result.csv")
)
PRIVATE_UNC = "\\" * 2 + "\\".join(
    ("server", "research-share", "private", "result.csv")
)
PRIVATE_EXTENDED = (
    "\\" * 2
    + "?"
    + "\\"
    + "\\".join((f"{chr(67)}:", "very-long-private-path", "result.csv"))
)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            RuntimeError(-2146959355, "private detail"),
            "origin_com_server_execution_failed",
        ),
        (
            RuntimeError(0x80040154, "private detail"),
            "origin_com_class_not_registered",
        ),
        (
            RuntimeError("private detail 0x80070005"),
            "origin_com_activation_access_denied",
        ),
        (
            RuntimeError("private detail"),
            "origin_instance_start_failed",
        ),
    ],
)
def test_classify_origin_activation_error(error: BaseException, expected: str) -> None:
    assert classify_origin_activation_error(error) == expected


def test_classify_origin_activation_error_reads_nested_cause() -> None:
    try:
        raise RuntimeError(-2146959355, "private nested detail")
    except RuntimeError as cause:
        error = RuntimeError("public wrapper")
        error.__cause__ = cause

    assert classify_origin_activation_error(error) == "origin_com_server_execution_failed"


def test_activation_recovery_allows_only_one_approved_same_context_retry() -> None:
    payload = origin_activation_recovery("origin_com_server_execution_failed")

    assert payload == {
        "action": "retry_same_command_in_active_interactive_user_context",
        "maximum_attempts": 1,
        "requires_user_approval": True,
        "must_preserve_execution_context_for_render": True,
        "automatic_fallback_to_attach_existing": False,
        "system_configuration_changes_allowed": False,
    }
    assert origin_activation_recovery("origin_draw_failed") is None


@pytest.mark.parametrize(
    "private_path",
    [
        PRIVATE_DRIVE_BACKSLASH,
        PRIVATE_DRIVE_SLASH,
        PRIVATE_UNC,
        PRIVATE_EXTENDED,
    ],
)
def test_redact_windows_paths_covers_common_absolute_forms(private_path: str) -> None:
    message = f"Could not read {private_path}; retry with another file."
    redacted = redact_windows_paths(message)

    assert private_path not in redacted
    assert "Somebody" not in redacted
    assert "research-share" not in redacted
    assert "very-long-private-path" not in redacted
    assert "<path-redacted>" in redacted
