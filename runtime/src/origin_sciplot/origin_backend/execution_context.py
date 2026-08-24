"""Detect whether an Origin worker has the interactive Windows user token."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .safe_errors import OriginEnvironmentError


@dataclass(frozen=True)
class OriginExecutionContext:
    """Small, testable description of the worker's real execution identity."""

    is_windows: bool
    account_name: str | None
    identity_source: str
    is_codex_sandbox: bool

    @property
    def status(self) -> str:
        """Return a public classification without exposing the account name."""

        if not self.is_windows:
            return "non_windows"
        if self.is_codex_sandbox:
            return "codex_sandbox"
        if self.account_name:
            return "interactive_user"
        return "unknown"

    @property
    def requires_current_user_approval(self) -> bool:
        return self.status == "codex_sandbox"

    def to_public_dict(self) -> dict[str, object]:
        """Return the JSON-safe, redacted shape suitable for doctor reports."""

        return {
            "status": self.status,
            "requires_current_user_approval": self.requires_current_user_approval,
        }


def _windows_token_name_from_winapi() -> str | None:
    """Read the account attached to the current Windows security token.

    Environment variables and :func:`getpass.getuser` are intentionally not
    used: a sandboxed Codex process can inherit the signed-in user's profile
    variables while its Windows token belongs to ``CodexSandboxOffline``.
    """

    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        size = wintypes.DWORD(257)
        buffer = ctypes.create_unicode_buffer(size.value)
        get_user_name = ctypes.windll.advapi32.GetUserNameW
        get_user_name.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        get_user_name.restype = wintypes.BOOL
        if not get_user_name(buffer, ctypes.byref(size)):
            return None
        value = buffer.value.strip()
        return value or None
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None


def _account_leaf(account_name: str | None) -> str:
    if not account_name:
        return ""
    return account_name.replace("/", "\\").rsplit("\\", 1)[-1].strip().casefold()


def classify_origin_execution_context(
    *,
    os_name: str,
    account_name: str | None,
    identity_source: str,
) -> OriginExecutionContext:
    """Classify an explicit account name without consulting profile variables."""

    is_windows = os_name == "nt"
    is_codex_sandbox = is_windows and _account_leaf(account_name).startswith(
        "codexsandbox"
    )
    return OriginExecutionContext(
        is_windows=is_windows,
        account_name=account_name,
        identity_source=identity_source,
        is_codex_sandbox=is_codex_sandbox,
    )


def detect_origin_execution_context(
    *,
    os_name: str | None = None,
) -> OriginExecutionContext:
    """Detect the current worker identity from the OS token when on Windows."""

    effective_os_name = os.name if os_name is None else os_name
    if effective_os_name != "nt":
        return classify_origin_execution_context(
            os_name=effective_os_name,
            account_name=None,
            identity_source="not_windows",
        )

    account_name = _windows_token_name_from_winapi()
    source = "winapi_token"
    if account_name is None:
        try:
            account_name = os.getlogin()
        except OSError:
            account_name = None
        source = "os.getlogin" if account_name else "unavailable"
    return classify_origin_execution_context(
        os_name=effective_os_name,
        account_name=account_name,
        identity_source=source,
    )


def require_interactive_origin_context(
    context: OriginExecutionContext | None = None,
) -> OriginExecutionContext:
    """Stop before COM when Codex has not yet approved local Origin access."""

    detected = context or detect_origin_execution_context()
    if detected.is_codex_sandbox:
        raise OriginEnvironmentError(
            "Origin must run in the signed-in Windows user context; "
            "approve the local Origin command in Codex and retry.",
            code="origin_codex_sandbox_context",
            stage="validate_execution_context",
            diagnostics={
                "execution_context": "codex_sandbox",
                "requires_user_approval": True,
            },
        )
    if detected.is_windows and detected.status == "unknown":
        raise OriginEnvironmentError(
            "EditaPlot could not verify the Windows account used for Origin; "
            "stop before Automation and retry from a normal signed-in user context.",
            code="origin_execution_context_unknown",
            stage="validate_execution_context",
            diagnostics={"execution_context": "unknown"},
        )
    return detected


def public_origin_execution_context() -> dict[str, object]:
    """Detect and return only the redacted public execution-context fields."""

    return detect_origin_execution_context().to_public_dict()


__all__ = [
    "OriginExecutionContext",
    "classify_origin_execution_context",
    "detect_origin_execution_context",
    "public_origin_execution_context",
    "require_interactive_origin_context",
]
