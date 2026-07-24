"""Friendly, redacted errors and worker exit codes."""

from __future__ import annotations

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


def safe_error_message(error: BaseException) -> str:
    return redact_windows_paths(str(error).replace("\r", " ").replace("\n", " "))[:800]
