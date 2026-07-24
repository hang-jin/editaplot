"""Advisory Origin version risks used to prioritize live capability probes.

The records in this module are deliberately non-blocking.  Origin release
notes can identify a product-level behavior change or a problem in a published
service-release build, but they cannot prove how an arbitrary local
Origin/originpro/OriginExt combination behaves.

Published build values are therefore matched only when ``@V`` readback is an
exact known value.  An unfamiliar suffix is reported as ``unknown`` rather
than being interpreted as an Origin service release.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum

from .capabilities import OriginVersionInfo


class BuildMatch(str, Enum):
    """How the live ``@V`` value relates to published build evidence."""

    PRODUCT = "product"
    KNOWN_AFFECTED = "known_affected"
    KNOWN_FIXED = "known_fixed"
    UNKNOWN = "unknown"


class ProbePriority(str, Enum):
    """Relative priority for the suggested live probes."""

    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True)
class KnownVersionRisk:
    """One advisory risk relevant to a concrete Origin runtime."""

    risk_id: str
    summary: str
    origin_product: str
    origin_numeric: float
    evidence_scope: str
    build_match: BuildMatch
    probe_priority: ProbePriority
    probe_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-safe report without implying a hard block."""

        payload = asdict(self)
        payload["build_match"] = self.build_match.value
        payload["probe_priority"] = self.probe_priority.value
        payload["probe_ids"] = list(self.probe_ids)
        payload["blocks_render"] = False
        return payload


@dataclass(frozen=True)
class _RiskSpec:
    risk_id: str
    products: frozenset[Decimal]
    summary: str
    probe_ids: tuple[str, ...]
    known_affected_builds: frozenset[Decimal] = frozenset()
    known_fixed_builds: frozenset[Decimal] = frozenset()

    @property
    def is_build_scoped(self) -> bool:
        return bool(self.known_affected_builds or self.known_fixed_builds)


_RISK_SPECS = (
    _RiskSpec(
        risk_id="origin_2021b_attach_lifecycle",
        products=frozenset({Decimal("9.85")}),
        summary=(
            "Origin 2021b introduced originpro attach support in SR2; "
            "probe ApplicationSI attach and release-only detach before use."
        ),
        probe_ids=("attach_existing_lifecycle",),
        known_affected_builds=frozenset(
            {
                Decimal("9.850201"),
                Decimal("9.850204"),
            }
        ),
        known_fixed_builds=frozenset({Decimal("9.850212")}),
    ),
    _RiskSpec(
        risk_id="origin_2023b_error_bar_visibility",
        products=frozenset({Decimal("10.05")}),
        summary=(
            "Origin 2023b SR0 could hide error bars for some categorical "
            "tick-label configurations; verify the rendered error plot."
        ),
        probe_ids=("error_bar_render", "categorical_tick_dataset"),
        known_affected_builds=frozenset({Decimal("10.050153")}),
        known_fixed_builds=frozenset({Decimal("10.050156")}),
    ),
    _RiskSpec(
        risk_id="origin_2025b_graph_defaults",
        products=frozenset({Decimal("10.25")}),
        summary=(
            "Origin 2025b changed graph page, margin, font, frame, line-width, "
            "and tick-label rotation defaults."
        ),
        probe_ids=(
            "page_layer_geometry",
            "axis_text_style",
            "tick_label_rotation",
        ),
    ),
    _RiskSpec(
        risk_id="origin_2025b_secondary_y_title",
        products=frozenset({Decimal("10.25")}),
        summary=(
            "Origin 2025b SR0 had a Python right-Y-axis title access problem; "
            "verify the YR object text and geometry."
        ),
        probe_ids=("secondary_y_title",),
        known_affected_builds=frozenset({Decimal("10.2502122")}),
        known_fixed_builds=frozenset({Decimal("10.250234")}),
    ),
    _RiskSpec(
        risk_id="origin_2025_2026_label_geometry",
        products=frozenset(
            {
                Decimal("10.20"),
                Decimal("10.25"),
                Decimal("10.30"),
            }
        ),
        summary=(
            "Python-created label coordinates require explicit attachment and "
            "geometry readback across Origin 2025 through Origin 2026."
        ),
        probe_ids=("label_geometry",),
    ),
    _RiskSpec(
        risk_id="origin_2026_categorical_ticks",
        products=frozenset({Decimal("10.30")}),
        summary=(
            "Origin 2026 could omit some custom-position tick labels sourced "
            "from a dataset."
        ),
        probe_ids=("categorical_tick_dataset",),
    ),
    _RiskSpec(
        risk_id="origin_2026b_reference_rescale",
        products=frozenset({Decimal("10.35")}),
        summary=(
            "Origin 2026b SR0 requires explicit reference-line and "
            "Bland-Altman rescale verification."
        ),
        probe_ids=("reference_line_rescale", "bland_altman_axis_limits"),
        known_affected_builds=frozenset({Decimal("10.3502223")}),
    ),
)


def _raw_build(version: OriginVersionInfo) -> Decimal | None:
    if version.raw_numeric is None:
        return None
    return Decimal(str(version.raw_numeric))


def _build_match(
    spec: _RiskSpec,
    version: OriginVersionInfo,
) -> BuildMatch:
    if not spec.is_build_scoped:
        return BuildMatch.PRODUCT

    raw_build = _raw_build(version)
    if raw_build in spec.known_affected_builds:
        return BuildMatch.KNOWN_AFFECTED
    if raw_build in spec.known_fixed_builds:
        return BuildMatch.KNOWN_FIXED
    return BuildMatch.UNKNOWN


def _probe_priority(build_match: BuildMatch) -> ProbePriority:
    if build_match is BuildMatch.KNOWN_FIXED:
        return ProbePriority.NORMAL
    return ProbePriority.HIGH


def known_version_risks(
    version: OriginVersionInfo,
) -> tuple[KnownVersionRisk, ...]:
    """Return non-blocking probe advisories for one normalized Origin version."""

    product = Decimal(str(version.numeric)).quantize(Decimal("0.01"))
    risks: list[KnownVersionRisk] = []
    for spec in _RISK_SPECS:
        if product not in spec.products:
            continue
        build_match = _build_match(spec, version)
        risks.append(
            KnownVersionRisk(
                risk_id=spec.risk_id,
                summary=spec.summary,
                origin_product=version.product_label,
                origin_numeric=version.numeric,
                evidence_scope="build" if spec.is_build_scoped else "product",
                build_match=build_match,
                probe_priority=_probe_priority(build_match),
                probe_ids=spec.probe_ids,
            )
        )
    return tuple(risks)


__all__ = [
    "BuildMatch",
    "KnownVersionRisk",
    "ProbePriority",
    "known_version_risks",
]
