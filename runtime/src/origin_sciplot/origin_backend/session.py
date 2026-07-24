"""Origin session lifecycle."""

from __future__ import annotations

import platform
import struct
from contextlib import suppress
from dataclasses import dataclass
from importlib import metadata
from types import ModuleType
from typing import Any

from .capabilities import (
    ConnectionMode,
    OriginVersionInfo,
    SessionOwnership,
    parse_origin_version,
)
from .safe_errors import OriginEnvironmentError
from .version_risks import ProbePriority, known_version_risks


@dataclass(frozen=True)
class OriginEnvironment:
    """Versions and lifecycle details recorded during the Origin handshake."""

    origin_version: str
    originpro_version: str
    originext_version: str
    python_version: str
    python_architecture_bits: int
    connection_mode: ConnectionMode
    ownership: SessionOwnership
    origin_version_info: OriginVersionInfo

    @property
    def version_status(self) -> str:
        """Report whether the product identity is known to this runtime."""

        if self.origin_version_info.compatibility_status == "unknown":
            return "unknown"
        return "recognized"

    @property
    def probe_priority(self) -> ProbePriority:
        """Prioritize probes without treating the advisory as a gate."""

        risks = known_version_risks(self.origin_version_info)
        if self.version_status == "unknown":
            return ProbePriority.HIGH
        if any(risk.probe_priority is ProbePriority.HIGH for risk in risks):
            return ProbePriority.HIGH
        return ProbePriority.NORMAL

    def version_advisory_to_dict(self) -> dict[str, Any]:
        """Return non-blocking version evidence for reports and probe planning."""

        risks = known_version_risks(self.origin_version_info)
        return {
            "version_status": self.version_status,
            "known_version_risks": [risk.to_dict() for risk in risks],
            "probe_priority": self.probe_priority.value,
            "requires_full_capability_probe": self.version_status == "unknown",
            "version_advisory_only": True,
            "version_advisory_blocks_render": False,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a stable, JSON-safe environment report payload."""

        unknown_version = self.version_status == "unknown"
        payload = {
            "origin_version": self.origin_version,
            "origin_version_raw": self.origin_version_info.raw_numeric,
            "origin_product": self.origin_version_info.product_label,
            "origin_compatibility_status": self.origin_version_info.compatibility_status,
            "origin_supported_by_originpro": (
                None
                if unknown_version
                else self.origin_version_info.supported_by_originpro
            ),
            "origin_verified_baseline": self.origin_version_info.verified_baseline,
            "originpro_version": self.originpro_version,
            "originext_version": self.originext_version,
            "python_version": self.python_version,
            "python_architecture_bits": self.python_architecture_bits,
            "connection_mode": self.connection_mode.value,
            "session_ownership": self.ownership.value,
        }
        # Preserve the established baseline payload when there is no version
        # advisory. Risk-bearing and unknown products carry the additional
        # evidence needed by diagnostics and render planning.
        advisory = self.version_advisory_to_dict()
        if advisory["known_version_risks"] or unknown_version:
            payload.update(advisory)
        return payload


class OriginSession:
    """External Python connection to a real Origin instance."""

    def __init__(
        self,
        keep_open: bool = True,
        *,
        connection_mode: ConnectionMode | str = ConnectionMode.NEW_ISOLATED,
    ) -> None:
        self.keep_open = keep_open
        self.connection_mode = ConnectionMode(connection_mode)
        self.ownership: SessionOwnership | None = None
        self.op: ModuleType | Any | None = None
        self.environment: OriginEnvironment | None = None

    def __enter__(self):
        try:
            import originpro as op  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise OriginEnvironmentError(
                "originpro is not importable",
                code="originpro_import_failed",
                stage="import_originpro",
            ) from exc
        if not getattr(op, "oext", False):
            raise OriginEnvironmentError(
                "external Python COM automation is required",
                code="external_automation_required",
                stage="validate_runtime",
            )

        if self.connection_mode is ConnectionMode.ATTACH_EXISTING:
            return self._enter_attached(op)
        return self._enter_isolated(op)

    def _enter_isolated(self, op: ModuleType | Any):
        """Create and own a fresh Origin instance without requiring manual launch."""

        self.op = op
        try:
            # In external originpro mode this first call activates
            # OriginExt.Application(), which always creates a new instance.
            op.set_show(False)
        except Exception as exc:  # noqa: BLE001 - redact local Automation failure details
            # Activation may have progressed far enough to hide a window even
            # when the call raises. Restore visibility without exposing the
            # underlying local COM error.
            with suppress(Exception):
                op.set_show(True)
            self._clear_failed_entry()
            raise OriginEnvironmentError(
                "Origin Automation connection failed",
                code="origin_instance_start_failed",
                stage="create_instance",
            ) from exc

        self.ownership = SessionOwnership.EDITAPLOT
        version_info = self._read_supported_version(op)

        try:
            # Only an EditaPlot-owned instance may discard its current project.
            op.new(asksave=False)
        except Exception as exc:  # noqa: BLE001 - redact local Automation failure details
            self._cleanup_failed_entry(op)
            raise OriginEnvironmentError(
                "Origin Automation connection failed",
                code="origin_project_initialization_failed",
                stage="initialize_project",
            ) from exc

        self.environment = self._environment(version_info)
        return self

    def _enter_attached(self, op: ModuleType | Any):
        """Attach to a user session without resetting, hiding, or owning it."""

        self.op = op
        try:
            op.attach()
        except Exception as exc:  # noqa: BLE001 - redact local Automation failure details
            self._clear_failed_entry()
            raise OriginEnvironmentError(
                "Origin Automation connection failed",
                code="origin_attach_failed",
                stage="attach_instance",
            ) from exc

        self.ownership = SessionOwnership.USER
        version_info = self._read_supported_version(op)
        self.environment = self._environment(version_info)
        return self

    def _read_supported_version(self, op: ModuleType | Any) -> OriginVersionInfo:
        try:
            raw_version = op.lt_float("@V")
        except Exception as exc:  # noqa: BLE001 - redact local Automation failure details
            self._cleanup_failed_entry(op)
            raise OriginEnvironmentError(
                "Origin version could not be read",
                code="origin_version_read_failed",
                stage="read_version",
            ) from exc

        try:
            version_info = parse_origin_version(raw_version)
        except (TypeError, ValueError):
            # Automation itself is alive, so an unfamiliar representation is
            # advisory evidence rather than a reason to terminate the owned
            # instance. Live probes must establish the actual capabilities.
            return _unknown_version_info()

        if not version_info.supported_by_originpro:
            self._cleanup_failed_entry(op)
            raise OriginEnvironmentError(
                "Origin 2021 or later is required",
                code="origin_version_unsupported",
                stage="validate_version",
            )
        if version_info.product_label.startswith("Unknown Origin ("):
            return _unknown_version_info(version_info)
        return version_info

    def _environment(self, version_info: OriginVersionInfo) -> OriginEnvironment:
        if self.ownership is None:
            raise RuntimeError("Origin session ownership was not established")
        origin_version = (
            "unknown"
            if version_info.compatibility_status == "unknown"
            else f"{version_info.numeric:.2f}"
        )
        return OriginEnvironment(
            origin_version=origin_version,
            originpro_version=_safe_package_version("originpro"),
            originext_version=_safe_package_version("OriginExt"),
            python_version=platform.python_version(),
            python_architecture_bits=struct.calcsize("P") * 8,
            connection_mode=self.connection_mode,
            ownership=self.ownership,
            origin_version_info=version_info,
        )

    def _cleanup_failed_entry(self, op: ModuleType | Any) -> None:
        """Best-effort cleanup which never replaces the original stage error."""

        if self.ownership is SessionOwnership.USER:
            with suppress(Exception):
                op.detach()
        elif self.ownership is SessionOwnership.EDITAPLOT:
            if self.keep_open:
                with suppress(Exception):
                    op.set_show(True)
            else:
                with suppress(Exception):
                    op.exit()
        self._clear_failed_entry()

    def _clear_failed_entry(self) -> None:
        self.op = None
        self.ownership = None
        self.environment = None

    def show(self) -> None:
        if self.op is not None:
            self.op.set_show(True)

    def __exit__(self, exc_type, exc, tb) -> None:
        op = self.op
        ownership = self.ownership
        if op is None or not getattr(op, "oext", False) or ownership is None:
            return

        cleanup_error: tuple[str, str, str, Exception] | None = None
        try:
            if ownership is SessionOwnership.USER:
                # Attached sessions are always detached and never closed.
                op.detach()
            elif self.keep_open:
                # A renderer may fail immediately after __enter__. Keep-open
                # still means the EditaPlot-owned window must be visible.
                op.set_show(True)
            else:
                op.exit()
        except Exception as cleanup_exc:  # noqa: BLE001 - redact local Automation failure details
            if ownership is SessionOwnership.USER:
                cleanup_error = (
                    "Origin session could not be detached",
                    "origin_detach_failed",
                    "detach_instance",
                    cleanup_exc,
                )
            elif self.keep_open:
                cleanup_error = (
                    "Origin window visibility could not be restored",
                    "origin_visibility_restore_failed",
                    "restore_visibility",
                    cleanup_exc,
                )
            else:
                cleanup_error = (
                    "Origin session could not be closed",
                    "origin_exit_failed",
                    "close_instance",
                    cleanup_exc,
                )

        if cleanup_error is not None and exc_type is None:
            message, code, stage, cleanup_exc = cleanup_error
            raise OriginEnvironmentError(message, code=code, stage=stage) from cleanup_exc


def _safe_package_version(distribution_name: str) -> str:
    """Read package metadata without risking the live Automation session."""

    try:
        value = metadata.version(distribution_name)
    except Exception:  # noqa: BLE001 - optional metadata must never break a live session
        return "unknown"
    return str(value).replace("\r", "").replace("\n", "").strip()[:128] or "unknown"


def _unknown_version_info(
    parsed: OriginVersionInfo | None = None,
) -> OriginVersionInfo:
    """Represent an unreadable or unfamiliar product without claiming support."""

    return OriginVersionInfo(
        numeric=parsed.numeric if parsed is not None else 0.0,
        product_label="unknown",
        supported_by_originpro=False,
        verified_baseline=False,
        compatibility_status="unknown",
        raw_numeric=parsed.raw_numeric if parsed is not None else None,
    )
