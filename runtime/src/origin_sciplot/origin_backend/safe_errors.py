"""Friendly, redacted errors and worker exit codes."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Any

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
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.stage = stage or self.default_stage
        self.diagnostics = _normalize_public_diagnostics(diagnostics)


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
    0x80004005: "origin_com_unspecified_failure",
    0x80010001: "origin_com_call_rejected",
    0x80010108: "origin_com_disconnected",
    0x8001010A: "origin_com_server_busy",
    0x80080005: "origin_com_server_execution_failed",
    0x80040154: "origin_com_class_not_registered",
    0x80070005: "origin_com_activation_access_denied",
    0x800706BA: "origin_com_server_unavailable",
}
_HRESULT_TEXT = re.compile(r"(?i)\b0x([0-9a-f]{8})\b")
_HRESULT_ATTRIBUTES = ("hresult", "HResult", "winerror", "scode")
_RETRYABLE_ACTIVATION_CODES = frozenset(
    {
        "origin_instance_start_failed",
        "origin_com_unspecified_failure",
        "origin_com_call_rejected",
        "origin_com_disconnected",
        "origin_com_server_busy",
        "origin_com_server_execution_failed",
        "origin_com_server_unavailable",
    }
)

_PUBLIC_DIAGNOSTIC_FIELDS = frozenset(
    {
        "primary_activation_code",
        "primary_activation_stage",
        "cleanup_error_code",
        "cleanup_error_stage",
        # Reserved for the execution-context preflight. They describe only a
        # product-defined context class and approval requirement, never an OS
        # account name or profile path.
        "detected_context",
        "execution_context",
        "requires_codex_user_approval",
        "requires_user_approval",
    }
)
_PUBLIC_DIAGNOSTIC_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_PUBLIC_ACTIVATION_CODES = frozenset(_ACTIVATION_HRESULT_CODES.values()) | {
    "origin_instance_start_failed"
}
_PUBLIC_DIAGNOSTIC_ENUMS = {
    "primary_activation_code": _PUBLIC_ACTIVATION_CODES,
    "primary_activation_stage": frozenset({"create_instance"}),
    "cleanup_error_code": _PUBLIC_ACTIVATION_CODES,
    "cleanup_error_stage": frozenset({"cleanup_partial_instance"}),
    "execution_context": frozenset(
        {"interactive_user", "codex_sandbox", "non_windows", "unknown"}
    ),
    "detected_context": frozenset(
        {"interactive_user", "codex_sandbox", "non_windows", "unknown"}
    ),
}


def _normalize_public_diagnostics(
    diagnostics: Mapping[str, object] | None,
) -> dict[str, object]:
    """Keep only explicitly public, stable diagnostic identifiers.

    The structured channel must not become an accidental route for raw COM
    text, HRESULTs, account names, or filesystem paths. Unsupported fields or
    values are dropped rather than replacing the original Origin failure.
    """

    if diagnostics is None:
        return {}
    normalized: dict[str, object] = {}
    for key, value in diagnostics.items():
        if key not in _PUBLIC_DIAGNOSTIC_FIELDS:
            continue
        allowed_values = _PUBLIC_DIAGNOSTIC_ENUMS.get(key)
        if isinstance(value, bool) and allowed_values is None:
            normalized[key] = value
        elif isinstance(value, str) and _PUBLIC_DIAGNOSTIC_IDENTIFIER.fullmatch(value):
            if allowed_values is not None and value not in allowed_values:
                continue
            normalized[key] = value
    return normalized


def structured_error_diagnostics(error: BaseException) -> dict[str, Any]:
    """Return a fresh JSON-safe copy of approved structured diagnostics."""

    value = getattr(error, "diagnostics", None)
    return _normalize_public_diagnostics(value if isinstance(value, Mapping) else None)


def classify_origin_activation_error(
    error: BaseException,
    *,
    include_exception_chain: bool = True,
) -> str:
    """Return a stable activation code without exposing local COM details.

    ``pywintypes.com_error`` and ``comtypes`` do not use one consistent
    exception shape.  HRESULT values may be signed integers, unsigned
    integers, nested inside ``args``, or present only as hexadecimal text.
    This classifier deliberately returns only a public code; callers must
    never surface the inspected exception payload.
    """

    for value in _iter_error_values(
        error,
        include_exception_chain=include_exception_chain,
    ):
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


def is_retryable_origin_activation_error(code: str) -> bool:
    """Return whether one fresh isolated-instance attempt is safe."""

    return code in _RETRYABLE_ACTIVATION_CODES


def origin_activation_recovery(code: str) -> dict[str, object] | None:
    """Return a bounded, non-mutating recovery policy for activation errors."""

    if code == "origin_codex_sandbox_context":
        return {
            "action": "rerun_origin_command_with_codex_user_approval",
            "maximum_attempts": 1,
            "requires_user_approval": True,
            "manual_powershell_required": False,
            "administrator_required": False,
            "automatic_fallback_to_attach_existing": False,
            "system_configuration_changes_allowed": False,
        }
    if code == "origin_job_queue_timeout":
        return {
            "action": "retry_after_active_origin_job_finishes",
            "maximum_attempts": 0,
            "requires_user_approval": True,
            "manual_powershell_required": False,
            "administrator_required": False,
            "active_job_preserved": True,
            "origin_instance_modified": False,
            "system_configuration_changes_allowed": False,
        }
    if is_retryable_origin_activation_error(code):
        return {
            "action": "retry_in_active_user_context_with_fresh_output_directory",
            "maximum_attempts": 1,
            "requires_user_approval": True,
            "must_preserve_execution_context_for_render": True,
            "must_use_fresh_output_directory": True,
            "preserve_previous_diagnostics": True,
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


def _iter_error_values(
    error: BaseException,
    *,
    include_exception_chain: bool = True,
) -> Iterator[object]:
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
            for attribute in _HRESULT_ATTRIBUTES:
                try:
                    attribute_value = getattr(value, attribute)
                except (AttributeError, OSError, RuntimeError):
                    continue
                pending.append(attribute_value)
            pending.extend(value.args)
            if include_exception_chain:
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
