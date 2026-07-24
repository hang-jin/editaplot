"""Static Origin capability requirements for public EditaPlot templates.

The matrix in this module is deliberately independent from ``originpro`` and
Origin itself.  It describes what a renderer needs; a separate live probe can
later report which capabilities a particular installation actually provides.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from .capabilities import OriginVersionInfo, parse_origin_version


class OriginCapability(str, Enum):
    """Independently testable Origin features used by EditaPlot renderers."""

    CORE_2D = "core_2d"
    EDITABLE_OPJU = "editable_opju"
    PNG_EXPORT = "png_export"
    PDF_EXPORT = "pdf_export"
    TIF_EXPORT = "tif_export"
    AXIS_READBACK = "axis_readback"
    TEXT_READBACK = "text_readback"
    CATEGORICAL_AXIS = "categorical_axis"
    ERROR_BARS = "error_bars"
    STATISTICAL_PLOT = "statistical_plot"
    MATRIX_HEATMAP = "matrix_heatmap"
    SANKEY = "sankey"
    PIE = "pie"
    INSET_LAYER = "inset_layer"
    LOG_AXIS = "log_axis"
    XPS_FILL_TWO_COLOR = "xps_fill_two_color"
    OPEN_GL_3D = "open_gl_3d"


@dataclass(frozen=True)
class TemplateCapabilityProfile:
    """Required and optional Origin capabilities for one public template."""

    template_id: str
    required: frozenset[OriginCapability]
    optional: frozenset[OriginCapability] = field(default_factory=frozenset)
    verified_versions: tuple[float, ...] = (10.15,)

    def to_dict(self) -> dict[str, object]:
        return {
            "template_id": self.template_id,
            "required": _capability_values(self.required),
            "optional": _capability_values(self.optional),
            "verified_versions": list(self.verified_versions),
        }


@dataclass(frozen=True)
class CapabilityProbeResult:
    """Serializable result produced by a future live capability probe."""

    available_capabilities: frozenset[OriginCapability]
    unavailable_capabilities: frozenset[OriginCapability] = field(default_factory=frozenset)
    probe_complete: bool = True

    def __post_init__(self) -> None:
        overlap = self.available_capabilities & self.unavailable_capabilities
        if overlap:
            names = ", ".join(_capability_values(overlap))
            raise ValueError(f"Origin capabilities cannot be both available and unavailable: {names}")

    def to_dict(self) -> dict[str, object]:
        return {
            "available_capabilities": _capability_values(self.available_capabilities),
            "unavailable_capabilities": _capability_values(self.unavailable_capabilities),
            "probe_complete": self.probe_complete,
        }


@dataclass(frozen=True)
class TemplateCompatibilityDecision:
    """Compatibility decision for one template and one Origin installation."""

    template_id: str
    origin_version: OriginVersionInfo
    status: str
    missing_required: tuple[OriginCapability, ...]
    unprobed_required: tuple[OriginCapability, ...]
    available_capabilities: frozenset[OriginCapability]
    activated_optional: frozenset[OriginCapability] = field(default_factory=frozenset)
    block_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "template_id": self.template_id,
            "origin_version": self.origin_version.to_dict(),
            "status": self.status,
            "missing_required": _capability_values(self.missing_required),
            "unprobed_required": _capability_values(self.unprobed_required),
            "available_capabilities": _capability_values(self.available_capabilities),
            "activated_optional": _capability_values(self.activated_optional),
            "block_reason": self.block_reason,
        }


_CORE_2D_REQUIRED = frozenset(
    {
        OriginCapability.CORE_2D,
        OriginCapability.EDITABLE_OPJU,
        OriginCapability.PNG_EXPORT,
        OriginCapability.PDF_EXPORT,
        OriginCapability.TIF_EXPORT,
        OriginCapability.AXIS_READBACK,
        OriginCapability.TEXT_READBACK,
    }
)


def _profile(
    template_id: str,
    *required: OriginCapability,
    optional: Iterable[OriginCapability] = (),
) -> TemplateCapabilityProfile:
    return TemplateCapabilityProfile(
        template_id=template_id,
        required=_CORE_2D_REQUIRED.union(required),
        optional=frozenset(optional),
    )


# Keep this table aligned with public, implemented runtime/templates manifests.
# Optional capabilities represent data-dependent routes: their absence does not
# block the template's simpler supported mode.
TEMPLATE_CAPABILITY_PROFILES: dict[str, TemplateCapabilityProfile] = {
    "bar": _profile(
        "bar",
        OriginCapability.CATEGORICAL_AXIS,
        optional=(OriginCapability.ERROR_BARS,),
    ),
    "bland_altman": _profile("bland_altman"),
    "bubble": _profile("bubble"),
    "calibration_curve": _profile("calibration_curve"),
    "confusion_matrix": _profile(
        "confusion_matrix",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.MATRIX_HEATMAP,
    ),
    "cv": _profile("cv"),
    "decision_curve": _profile("decision_curve"),
    "diagnostic_curve": _profile("diagnostic_curve"),
    "eis": _profile("eis", optional=(OriginCapability.LOG_AXIS,)),
    "forest": _profile("forest", OriginCapability.ERROR_BARS),
    "grouped_box": _profile(
        "grouped_box",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.STATISTICAL_PLOT,
    ),
    "heatmap": _profile(
        "heatmap",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.MATRIX_HEATMAP,
    ),
    "histogram": _profile(
        "histogram",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.STATISTICAL_PLOT,
    ),
    "horizontal_bar": _profile(
        "horizontal_bar",
        OriginCapability.CATEGORICAL_AXIS,
        optional=(OriginCapability.ERROR_BARS,),
    ),
    "line_error": _profile("line_error", OriginCapability.ERROR_BARS),
    "lsv": _profile("lsv"),
    "paired_trajectory": _profile("paired_trajectory"),
    "percent_stacked_bar": _profile(
        "percent_stacked_bar",
        OriginCapability.CATEGORICAL_AXIS,
    ),
    "pie": _profile("pie", OriginCapability.PIE),
    "pl": _profile("pl", optional=(OriginCapability.LOG_AXIS,)),
    "radar": _profile("radar", OriginCapability.CATEGORICAL_AXIS),
    "raincloud": _profile(
        "raincloud",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.STATISTICAL_PLOT,
    ),
    "raw_summary": _profile(
        "raw_summary",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.STATISTICAL_PLOT,
    ),
    "sankey": _profile("sankey", OriginCapability.SANKEY),
    "scatter": _profile("scatter"),
    "shap_summary": _profile("shap_summary", OriginCapability.CATEGORICAL_AXIS),
    "stacked_bar": _profile(
        "stacked_bar",
        OriginCapability.CATEGORICAL_AXIS,
        optional=(OriginCapability.ERROR_BARS,),
    ),
    "trajectory3d": _profile("trajectory3d", OriginCapability.OPEN_GL_3D),
    "trend": _profile("trend"),
    "uv_vis": _profile("uv_vis", optional=(OriginCapability.INSET_LAYER,)),
    "violin": _profile(
        "violin",
        OriginCapability.CATEGORICAL_AXIS,
        OriginCapability.STATISTICAL_PLOT,
    ),
    "xas": _profile("xas"),
    "xps": _profile("xps", OriginCapability.XPS_FILL_TWO_COLOR),
    "xrd": _profile("xrd"),
}

ALL_ORIGIN_CAPABILITIES = frozenset(OriginCapability)


def _capability_values(capabilities: Iterable[OriginCapability]) -> list[str]:
    return sorted(capability.value for capability in capabilities)


def _normalize_capabilities(
    capabilities: Iterable[OriginCapability | str],
) -> frozenset[OriginCapability]:
    if isinstance(capabilities, (str, OriginCapability)):
        capabilities = (capabilities,)

    try:
        return frozenset(OriginCapability(capability) for capability in capabilities)
    except ValueError as exc:
        raise ValueError(f"Unknown Origin capability: {exc}") from exc


def get_template_capability_profile(template_id: str) -> TemplateCapabilityProfile:
    """Return a public template profile or fail with a clear identifier."""

    try:
        return TEMPLATE_CAPABILITY_PROFILES[template_id]
    except KeyError as exc:
        raise KeyError(f"Unknown public template capability profile: {template_id!r}") from exc


def evaluate_template_compatibility(
    template_id: str,
    origin_version: float | str,
    available_capabilities: Iterable[OriginCapability | str] | CapabilityProbeResult,
    *,
    activated_optional: Iterable[OriginCapability | str] = (),
) -> TemplateCompatibilityDecision:
    """Evaluate one concrete render route without importing or connecting to Origin.

    ``activated_optional`` promotes data-dependent features (for example an
    error-bar column or a UV-vis inset) to required capabilities for this
    decision while keeping the template's simpler route available.
    """

    profile = get_template_capability_profile(template_id)
    version = parse_origin_version(origin_version)
    if isinstance(available_capabilities, CapabilityProbeResult):
        available = available_capabilities.available_capabilities
        unavailable = available_capabilities.unavailable_capabilities
        probe_complete = available_capabilities.probe_complete
    else:
        available = _normalize_capabilities(available_capabilities)
        unavailable = ALL_ORIGIN_CAPABILITIES - available
        probe_complete = True
    activated = _normalize_capabilities(activated_optional)
    invalid_activated = activated - profile.optional
    if invalid_activated:
        invalid = ", ".join(_capability_values(invalid_activated))
        raise ValueError(
            f"Capabilities are not optional for template {template_id!r}: {invalid}"
        )
    effective_required = profile.required.union(activated)
    unresolved = effective_required - available
    missing_set = unresolved if probe_complete else unresolved & unavailable
    unprobed_set = frozenset() if probe_complete else unresolved - unavailable
    missing = tuple(
        sorted(missing_set, key=lambda capability: capability.value)
    )
    unprobed = tuple(
        sorted(unprobed_set, key=lambda capability: capability.value)
    )

    if not version.supported_by_originpro:
        status = "blocked"
        block_reason = "origin_version_unsupported"
    elif missing:
        status = "blocked"
        block_reason = "missing_required_capabilities"
    elif unprobed:
        status = "experimental"
        block_reason = None
    elif version.numeric in profile.verified_versions:
        status = "verified"
        block_reason = None
    else:
        status = "compatible_unverified"
        block_reason = None

    return TemplateCompatibilityDecision(
        template_id=template_id,
        origin_version=version,
        status=status,
        missing_required=missing,
        unprobed_required=unprobed,
        available_capabilities=available,
        activated_optional=activated,
        block_reason=block_reason,
    )


__all__ = [
    "ALL_ORIGIN_CAPABILITIES",
    "TEMPLATE_CAPABILITY_PROFILES",
    "CapabilityProbeResult",
    "OriginCapability",
    "TemplateCapabilityProfile",
    "TemplateCompatibilityDecision",
    "evaluate_template_compatibility",
    "get_template_capability_profile",
]
