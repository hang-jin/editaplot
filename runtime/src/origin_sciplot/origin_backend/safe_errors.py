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


class OriginEnvironmentError(RuntimeError):
    """Origin or originpro is unavailable."""


class OriginDrawError(RuntimeError):
    """Origin drawing failed after the environment connected."""


class OriginExportError(RuntimeError):
    """Origin export failed."""


def safe_error_message(error: BaseException) -> str:
    return redact_windows_paths(str(error).replace("\r", " ").replace("\n", " "))[:800]
