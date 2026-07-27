"""Friendly, redacted errors and worker exit codes."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..project_paths import redact_windows_paths


class WorkerExitCode:
    SUCCESS = 0
    VALIDATION_FAILED = 1
    ORIGIN_ENVIRONMENT = 2
    ORIGIN_DRAW = 3
    EXPORT_FAILED = 4
    UNKNOWN = 5


class _StructuredOriginError(RuntimeError):
    """Base class for short user text plus stable machine diagnostics."""

    default_code = "origin_runtime_failed"
    default_stage = "origin_runtime"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.stage = stage or self.default_stage


class OriginEnvironmentError(_StructuredOriginError):
    """Origin or originpro is unavailable.

    ``code`` and ``stage`` are stable, machine-readable diagnostics.  The
    human-facing exception text stays deliberately short and never includes
    the underlying COM/import exception.
    """

    default_code = "origin_environment_unavailable"
    default_stage = "environment"


class OriginDrawError(_StructuredOriginError):
    """Origin drawing failed after the environment connected."""

    default_code = "origin_draw_failed"
    default_stage = "draw"


class OriginExportError(_StructuredOriginError):
    """Origin export failed."""

    default_code = "origin_export_failed"
    default_stage = "export"


_ACTIVATION_HRESULT_CODES = {
    0x80080005: "origin_com_server_execution_failed",
    0x80040154: "origin_com_class_not_registered",
    0x80070005: "origin_com_activation_access_denied",
}
_HRESULT_TEXT = re.compile(r"(?i)\b0x([0-9a-f]{8})\b")


def classify_origin_activation_error(error: BaseException) -> str:
    """Return a stable activation code without exposing local COM details.

    ``pywintypes.com_error`` and ``comtypes`` do not use one consistent
    exception shape.  HRESULT values may be signed integers, unsigned
    integers, nested inside ``args``, or present only as hexadecimal text.
    This classifier deliberately returns only a public code; callers must
    never surface the inspected exception payload.
    """

    for value in _iter_error_values(error):
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            code = _ACTIVATION_HRESULT_CODES.get(value & 0xFFFFFFFF)
            if code is not None:
                return code
        elif isinstance(value, str):
            for match in _HRESULT_TEXT.finditer(value):
                code = _ACTIVATION_HRESULT_CODES.get(int(match.group(1), 16))
                if code is not None:
                    return code
    return "origin_instance_start_failed"


def origin_activation_recovery(code: str) -> dict[str, object] | None:
    """Return a bounded, non-mutating recovery policy for activation errors."""

    if code in {
        "origin_com_server_execution_failed",
        "origin_com_activation_access_denied",
    }:
        return {
            "action": "retry_same_command_in_active_interactive_user_context",
            "maximum_attempts": 1,
            "requires_user_approval": True,
            "must_preserve_execution_context_for_render": True,
            "automatic_fallback_to_attach_existing": False,
            "system_configuration_changes_allowed": False,
        }
    if code == "origin_com_class_not_registered":
        return {
            "action": "stop_and_report_user_managed_origin_automation_entry",
            "maximum_attempts": 0,
            "requires_user_approval": False,
            "automatic_fallback_to_attach_existing": False,
            "system_configuration_changes_allowed": False,
        }
    return None


def _iter_error_values(error: BaseException) -> Iterator[object]:
    """Yield bounded nested exception values for HRESULT classification."""

    pending: list[object] = [error]
    seen: set[int] = set()
    while pending and len(seen) < 64:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        if isinstance(value, BaseException):
            pending.extend(value.args)
            if value.__cause__ is not None:
                pending.append(value.__cause__)
            if value.__context__ is not None:
                pending.append(value.__context__)
            continue
        if isinstance(value, (tuple, list)):
            pending.extend(value[:32])
            continue
        yield value


def safe_error_message(error: BaseException) -> str:
    return redact_windows_paths(str(error).replace("\r", " ").replace("\n", " "))[:800]
