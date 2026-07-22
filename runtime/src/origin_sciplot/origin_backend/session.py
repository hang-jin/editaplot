"""Origin session lifecycle."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from importlib import metadata

from .safe_errors import OriginEnvironmentError


@dataclass
class OriginEnvironment:
    origin_version: str
    originpro_version: str


class OriginSession:
    """External Python connection to a real Origin instance."""

    def __init__(self, keep_open: bool = True) -> None:
        self.keep_open = keep_open
        self.op = None
        self.environment: OriginEnvironment | None = None

    def __enter__(self):
        try:
            import originpro as op  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise OriginEnvironmentError("originpro is not importable") from exc
        if not getattr(op, "oext", False):
            raise OriginEnvironmentError("external Python COM automation is required")
        try:
            op.set_show(False)
            op.new(asksave=False)
            origin_version = f"{float(op.lt_float('@V')):.2f}"
        except Exception as exc:  # noqa: BLE001 - redact local Automation failure details
            # A failed connection probe must not leave a user-visible application hidden.
            with suppress(Exception):
                op.set_show(True)
            self.op = None
            raise OriginEnvironmentError("Origin Automation connection failed") from exc
        self.op = op
        try:
            originpro_version = metadata.version("originpro")
        except Exception:  # noqa: BLE001 - optional package metadata must not break a live session
            originpro_version = "unknown"
        self.environment = OriginEnvironment(origin_version, originpro_version)
        return self

    def show(self) -> None:
        if self.op is not None:
            self.op.set_show(True)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.op is not None and getattr(self.op, "oext", False) and not self.keep_open:
            self.op.exit()
