"""Pure Origin compatibility types and version classification.

This module intentionally has no dependency on ``originpro`` or ``OriginExt``.
It can therefore be used by diagnostics and planning code before an Origin
Automation connection is attempted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from enum import Enum


class ConnectionMode(str, Enum):
    """Supported ways to obtain an Origin Automation session."""

    NEW_ISOLATED = "new_isolated"
    ATTACH_EXISTING = "attach_existing"


class SessionOwnership(str, Enum):
    """Identify who owns the lifecycle of the connected Origin session."""

    EDITAPLOT = "editaplot"
    USER = "user"


@dataclass(frozen=True)
class OriginVersionInfo:
    """Normalized product and compatibility information for an Origin version."""

    numeric: float
    product_label: str
    supported_by_originpro: bool
    verified_baseline: bool
    compatibility_status: str
    raw_numeric: float | None = None

    def to_dict(self) -> dict[str, bool | float | str | None]:
        """Return a serialization-safe representation."""

        return asdict(self)


_PRODUCT_LABELS = {
    Decimal("9.80"): "2021",
    Decimal("9.85"): "2021b",
    Decimal("9.90"): "2022",
    Decimal("9.95"): "2022b",
    Decimal("10.00"): "2023",
    Decimal("10.05"): "2023b",
    Decimal("10.10"): "2024",
    Decimal("10.15"): "2024b",
    Decimal("10.20"): "2025",
    Decimal("10.25"): "2025b",
    Decimal("10.30"): "2026",
    Decimal("10.35"): "2026b",
}
_ORIGINPRO_MINIMUM = Decimal("9.80")
_VERIFIED_BASELINE = Decimal("10.15")


def _numeric_decimal(value: float | str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Origin version must be a finite number")

    try:
        numeric = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Origin version must be a finite number") from exc

    if not numeric.is_finite():
        raise ValueError("Origin version must be a finite number")
    return numeric


def _unknown_product_label(numeric: Decimal) -> str:
    text = format(numeric, "f")
    if "." not in text:
        text = f"{text}.00"
    else:
        whole, fraction = text.split(".", maxsplit=1)
        text = f"{whole}.{fraction.rstrip('0') or '0'}"
    return f"Unknown Origin ({text})"


def parse_origin_version(value: float | str) -> OriginVersionInfo:
    """Normalize an Origin numeric version without opening Origin.

    Origin 2021 (9.80) is the minimum product supported by the current
    ``originpro`` integration. Origin 2024b (10.15) remains EditaPlot's
    verified baseline; other supported versions are classified as compatible
    but unverified until they pass the full real-Origin evidence gate.
    """

    raw_numeric = _numeric_decimal(value)
    # Origin's @V may append a product build after the release number, for
    # example 10.150132 for Origin 2024b. The first two decimal places are the
    # public product version. Truncate rather than round so a build can never
    # be promoted to the next product release.
    numeric = raw_numeric.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    supported = numeric >= _ORIGINPRO_MINIMUM
    verified = numeric == _VERIFIED_BASELINE

    if verified:
        status = "verified"
    elif supported:
        status = "compatible_unverified"
    else:
        status = "unsupported"

    return OriginVersionInfo(
        numeric=float(numeric),
        product_label=_PRODUCT_LABELS.get(numeric, _unknown_product_label(numeric)),
        supported_by_originpro=supported,
        verified_baseline=verified,
        compatibility_status=status,
        raw_numeric=float(raw_numeric),
    )
