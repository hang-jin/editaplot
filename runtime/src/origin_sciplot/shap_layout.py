"""Shared, renderer-neutral geometry for SHAP composite figures.

The Matplotlib preview and editable Origin renderer must consume the same
page-relative regions.  Keeping this module free of either plotting backend
prevents the preview from becoming a second, subtly different template.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .shap_composite import SHAP_COMPOSITE_LAYOUT_VERSION, SHAP_COMPOSITE_PROFILES

SHAP_FEATURE_VALUE_COLORS = ("#3B4CC0", "#F7F7F7", "#B40426")
SHAP_MEAN_ABS_BAR_COLOR = "#B8CADB"
SHAP_MEAN_ABS_BAR_EDGE_COLOR = "#8FA9BE"
SHAP_ZERO_LINE_COLOR = "#737A80"
SHAP_GROUP_COLORS = (
    "#DDE8F2",
    "#BED3E3",
    "#91B7CE",
    "#6399B7",
    "#3C7698",
)


@dataclass(frozen=True, slots=True)
class ShapCompositeRegion:
    """One figure region using Origin's percent-of-page, top-origin geometry."""

    role: str
    left_percent: float
    top_percent: float
    width_percent: float
    height_percent: float

    def to_dict(self) -> dict[str, float]:
        return {
            "left_percent": float(self.left_percent),
            "top_percent": float(self.top_percent),
            "width_percent": float(self.width_percent),
            "height_percent": float(self.height_percent),
        }

    def matplotlib_bounds(self) -> tuple[float, float, float, float]:
        """Return Matplotlib ``add_axes`` bounds using a bottom-origin page."""

        return (
            self.left_percent / 100.0,
            1.0 - (self.top_percent + self.height_percent) / 100.0,
            self.width_percent / 100.0,
            self.height_percent / 100.0,
        )


@dataclass(frozen=True, slots=True)
class ShapCompositeGeometry:
    """Deterministic page and region geometry for one frozen SHAP profile."""

    profile: str
    page_width_cm: float
    page_height_cm: float
    regions: tuple[ShapCompositeRegion, ...]
    layout_version: str = SHAP_COMPOSITE_LAYOUT_VERSION

    def region(self, role: str) -> ShapCompositeRegion:
        for region in self.regions:
            if region.role == role:
                return region
        raise KeyError(role)

    def to_dict(self) -> dict[str, object]:
        return {
            "layout_version": self.layout_version,
            "profile": self.profile,
            "page_width_cm": float(self.page_width_cm),
            "page_height_cm": float(self.page_height_cm),
            "regions": {region.role: region.to_dict() for region in self.regions},
        }


def _style_number(style: Any | None, name: str, default: float) -> float:
    value = default if style is None else getattr(style, name, default)
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"SHAP layout field {name!r} must be finite.")
    return numeric


def _region(
    role: str,
    left: float,
    top: float,
    width: float,
    height: float,
) -> ShapCompositeRegion:
    values = (left, top, width, height)
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"SHAP region {role!r} contains a non-finite value.")
    if left < 0.0 or top < 0.0 or width <= 0.0 or height <= 0.0:
        raise ValueError(f"SHAP region {role!r} has invalid page geometry.")
    if left + width > 100.0 + 1e-9 or top + height > 100.0 + 1e-9:
        raise ValueError(f"SHAP region {role!r} extends beyond the page.")
    return ShapCompositeRegion(
        role=role,
        left_percent=round(left, 4),
        top_percent=round(top, 4),
        width_percent=round(width, 4),
        height_percent=round(height, 4),
    )


def resolve_shap_mean_axis(maximum: float) -> tuple[float, float, float]:
    """Return a padded, publication-readable Mean-|SHAP| axis."""

    maximum = float(maximum)
    if not math.isfinite(maximum) or maximum < 0.0:
        raise ValueError("Mean |SHAP| maximum must be finite and non-negative.")
    if maximum == 0.0:
        return (0.0, 1.0, 0.2)
    padded = maximum * 1.08
    raw_step = padded / 5.0
    magnitude = 10.0 ** math.floor(math.log10(raw_step))
    fraction = raw_step / magnitude
    if fraction <= 1.0:
        nice_fraction = 1.0
    elif fraction <= 2.0:
        nice_fraction = 2.0
    elif fraction <= 2.5:
        nice_fraction = 2.5
    elif fraction <= 5.0:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    step = nice_fraction * magnitude
    upper = math.ceil((padded - step * 1e-12) / step) * step
    return (0.0, float(upper), float(step))


def resolve_shap_composite_geometry(
    profile: str,
    style: Any | None = None,
) -> ShapCompositeGeometry:
    """Resolve shared SHAP regions from a frozen adaptive style and profile.

    ``style=None`` exists for pure contract tests and returns the standard
    adaptive SHAP page.  Production callers pass the plan's
    :class:`AdaptiveOriginStyle` so label length and feature count still drive
    the physical page.
    """

    if profile not in SHAP_COMPOSITE_PROFILES:
        raise ValueError(f"Unknown SHAP composite profile: {profile!r}.")

    page_width_cm = _style_number(style, "page_width_cm", 28.0)
    page_height_cm = _style_number(style, "page_height_cm", 17.0)
    layer_left = _style_number(style, "layer_left_percent", 25.0)
    layer_top = _style_number(style, "layer_top_percent", 7.0)
    layer_width = _style_number(style, "layer_width_percent", 71.0)
    layer_height = _style_number(style, "layer_height_percent", 78.0)
    if page_width_cm <= 0.0 or page_height_cm <= 0.0:
        raise ValueError("SHAP composite page dimensions must be positive.")

    # Physical spacing stays readable as adaptive pages widen for long labels.
    # Keep a dedicated right gutter for the colorbar's High/Low tick labels;
    # otherwise a valid adaptive layer can still export those words beyond the
    # page edge.  Mean-|SHAP| profiles also need physical headroom for the
    # independent top axis and its title.
    colorbar_gap = 0.72 / page_width_cm * 100.0
    colorbar_width = 0.52 / page_width_cm * 100.0
    colorbar_label_gutter = 1.18 / page_width_cm * 100.0
    mean_top_gutter = (
        0.78 / page_height_cm * 100.0 if profile != "beeswarm_only" else 0.0
    )
    main_width = layer_width - colorbar_gap - colorbar_width - colorbar_label_gutter
    main_top = layer_top + mean_top_gutter
    main_height = layer_height - mean_top_gutter
    if main_width <= 20.0:
        raise ValueError("SHAP composite style leaves insufficient width for the main plot.")
    if main_height <= 20.0:
        raise ValueError("SHAP composite style leaves insufficient height for the main plot.")

    beeswarm = _region(
        "shap_beeswarm",
        layer_left,
        main_top,
        main_width,
        main_height,
    )
    colorbar_height = main_height * 0.70
    colorbar = _region(
        "shap_feature_value_colorbar",
        layer_left + main_width + colorbar_gap,
        main_top + (main_height - colorbar_height) / 2.0,
        colorbar_width,
        colorbar_height,
    )
    regions: list[ShapCompositeRegion] = [beeswarm]

    if profile != "beeswarm_only":
        regions.append(
            _region(
                "shap_mean_abs",
                beeswarm.left_percent,
                beeswarm.top_percent,
                beeswarm.width_percent,
                beeswarm.height_percent,
            )
        )
    regions.append(colorbar)

    if profile == "beeswarm_mean_abs_grouped":
        main_width_cm = beeswarm.width_percent / 100.0 * page_width_cm
        main_height_cm = beeswarm.height_percent / 100.0 * page_height_cm
        # Keep the optional native Pie large enough to edit while preserving
        # the lower-left beeswarm rows.  The first composite prototype used a
        # 6.4 cm inset, which visually occupied several feature rows on wide
        # adaptive pages; 4.8 cm is the publication-size upper bound for v1.
        inset_size_cm = min(4.8, main_width_cm * 0.28, main_height_cm * 0.34)
        inset_width = inset_size_cm / page_width_cm * 100.0
        inset_height = inset_size_cm / page_height_cm * 100.0
        inset_left_margin = min(beeswarm.width_percent * 0.045, 0.45 / page_width_cm * 100.0)
        inset_bottom_margin = min(
            beeswarm.height_percent * 0.045,
            0.45 / page_height_cm * 100.0,
        )
        regions.append(
            _region(
                "shap_group_contribution",
                beeswarm.left_percent + inset_left_margin,
                beeswarm.top_percent
                + beeswarm.height_percent
                - inset_height
                - inset_bottom_margin,
                inset_width,
                inset_height,
            )
        )

    return ShapCompositeGeometry(
        profile=profile,
        page_width_cm=round(page_width_cm, 4),
        page_height_cm=round(page_height_cm, 4),
        regions=tuple(regions),
    )


__all__ = [
    "SHAP_COMPOSITE_LAYOUT_VERSION",
    "SHAP_FEATURE_VALUE_COLORS",
    "SHAP_GROUP_COLORS",
    "SHAP_MEAN_ABS_BAR_COLOR",
    "SHAP_MEAN_ABS_BAR_EDGE_COLOR",
    "SHAP_ZERO_LINE_COLOR",
    "ShapCompositeGeometry",
    "ShapCompositeRegion",
    "resolve_shap_composite_geometry",
    "resolve_shap_mean_axis",
]
