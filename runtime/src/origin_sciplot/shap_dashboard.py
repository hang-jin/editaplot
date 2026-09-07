"""Frozen summaries and layout for the side-by-side SHAP dashboard.

Angles express a share of total mean absolute SHAP, not area or causality.
The bar/beeswarm retain feature order; only the ring is grouped by membership.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .shap_composite import ShapCompositeError, ShapCompositePlan
from .shap_layout import ShapCompositeRegion, resolve_shap_mean_axis

DASHBOARD_LAYOUT_VERSION = "shap-dashboard-layout-v1"
DASHBOARD_PALETTES = {
    "blue_red": ("#236887", "#76B5C5", "#F4F1E9", "#CA7166", "#8E2245"),
    "viridis": ("#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725"),
    "red_blue": ("#A62A43", "#E58E73", "#F6EDBB", "#92C5DE", "#36558F"),
}
DASHBOARD_MODES = tuple(f"dashboard_{key}" for key in DASHBOARD_PALETTES)
GROUP_COLORS = ("#607D82", "#D39A58", "#BF416A", "#80709A", "#739B5D")


@dataclass(frozen=True)
class ShapDashboardPlan:
    layout_version: str
    contribution_layout: str
    palette_id: str
    palette_colors: tuple[str, ...]
    feature_percentages: tuple[tuple[str, float], ...]
    feature_colors: tuple[tuple[str, str], ...]
    group_colors: tuple[tuple[str, str], ...]
    ring_feature_order: tuple[str, ...]
    ring_group_percentages: tuple[tuple[str, float], ...]


def color_ramp(anchors: tuple[str, ...], count: int = 101) -> tuple[str, ...]:
    if len(anchors) < 2 or count < 2:
        raise ValueError("A color ramp needs at least two colors and levels.")
    rgb = np.asarray([[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in anchors])
    values = np.linspace(0, len(anchors) - 1, count)
    channels = [np.interp(values, np.arange(len(anchors)), rgb[:, c]) for c in range(3)]
    return tuple("#" + "".join(f"{int(round(v)):02X}" for v in row) for row in zip(*channels, strict=True))


def build_dashboard_plan(plan: ShapCompositePlan, palette_id: str) -> ShapDashboardPlan:
    if palette_id not in DASHBOARD_PALETTES:
        raise ShapCompositeError("shap_dashboard_palette", "Select blue_red, viridis, or red_blue.")
    if plan.profile != "beeswarm_mean_abs_grouped":
        raise ShapCompositeError("shap_dashboard_group_required", "The dashboard requires Feature Group.")
    if not 2 <= len(plan.feature_order) <= 20:
        raise ShapCompositeError("shap_dashboard_feature_count", "The dashboard supports 2–20 features.")
    if any(len(label) > 48 for label in (*plan.feature_order, *plan.group_order)):
        raise ShapCompositeError("shap_dashboard_label_length", "Use display names up to 48 characters.")
    means = dict(plan.mean_abs_values)
    total = math.fsum(means.values())
    if not math.isfinite(total) or total <= 0:
        raise ShapCompositeError("shap_dashboard_zero_total", "Total Mean |SHAP| must be positive.")
    groups = dict(plan.feature_groups)
    percentages = tuple((f, means[f] / total * 100.0) for f in plan.feature_order)
    group_colors = tuple(zip(plan.group_order, GROUP_COLORS, strict=False))
    group_map = dict(group_colors)
    feature_colors: list[tuple[str, str]] = []
    ring_order: list[str] = []
    for group in plan.group_order:
        members = [f for f in plan.feature_order if groups[f] == group]
        ramp = color_ramp((group_map[group], "#DDE4E2"), max(2, len(members) + 1))
        for i, feature in enumerate(members):
            feature_colors.append((feature, ramp[i]))
            ring_order.append(feature)
    # Use one exact denominator for both rings, so their angular boundaries
    # align even when a supplied, independently validated percentage is rounded.
    grouped = tuple(
        (g, math.fsum(means[f] for f in plan.feature_order if groups[f] == g) / total * 100.0)
        for g in plan.group_order
    )
    upper = resolve_shap_mean_axis(max(means.values()) * 1.18)[1]
    tail = plan.feature_order[max(1, len(plan.feature_order) // 3) :]
    can_inset = (
        len(plan.feature_order) >= 8
        and max(len(f) for f in plan.feature_order) <= 24
        and max(means[f] for f in tail) / upper <= 0.28
    )
    return ShapDashboardPlan(
        layout_version=DASHBOARD_LAYOUT_VERSION,
        contribution_layout="inset" if can_inset else "reserved",
        palette_id=palette_id,
        palette_colors=color_ramp(DASHBOARD_PALETTES[palette_id]),
        feature_percentages=percentages,
        feature_colors=tuple(feature_colors),
        group_colors=group_colors,
        ring_feature_order=tuple(ring_order),
        ring_group_percentages=grouped,
    )


def dashboard_regions(plan: ShapDashboardPlan | None = None) -> dict[str, ShapCompositeRegion]:
    """Align comparable plot rectangles; keep the ring below the left panel."""
    if plan is not None and plan.contribution_layout == "inset":
        return {
            "importance": ShapCompositeRegion("importance", 16, 8, 33, 80),
            "beeswarm": ShapCompositeRegion("beeswarm", 59, 8, 32, 80),
            "colorbar": ShapCompositeRegion("colorbar", 94, 16, 1.05, 62),
            "rings": ShapCompositeRegion("rings", 34, 40, 18, 24),
        }
    return {
        "importance": ShapCompositeRegion("importance", 16, 8, 33, 54),
        "beeswarm": ShapCompositeRegion("beeswarm", 59, 8, 32, 54),
        "colorbar": ShapCompositeRegion("colorbar", 94, 14, 1.05, 42),
        "rings": ShapCompositeRegion("rings", 23, 73, 17, 23),
    }


def draw_dashboard_preview(figure, frame, preparation) -> None:
    """Preview the same source-bound mark grammar with editable-backend geometry."""
    from matplotlib import colors
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import ListedColormap

    from .scientific_workflow import shap_beeswarm_offsets, shap_within_feature_color_values

    spec = preparation.plot_spec
    plan = spec.shap_plan
    dashboard = spec.shap_dashboard
    style = spec.display_plan.figure_style
    figure.set_size_inches(style.page_width_cm / 2.54, style.page_height_cm / 2.54)
    regions = dashboard_regions(dashboard)
    importance = figure.add_axes(regions["importance"].matplotlib_bounds(), label="dashboard_importance")
    beeswarm = figure.add_axes(regions["beeswarm"].matplotlib_bounds(), label="dashboard_beeswarm")
    mean_map = dict(plan.mean_abs_values)
    percent = dict(dashboard.feature_percentages)
    feature_colors = dict(dashboard.feature_colors)
    count = len(plan.feature_order)
    positions = np.arange(count, 0, -1)
    importance.barh(
        positions,
        [mean_map[f] for f in plan.feature_order],
        color=[feature_colors[f] for f in plan.feature_order],
        height=0.68,
    )
    importance.set_yticks(positions, plan.feature_order)
    maximum = max(mean_map.values())
    importance.set_xlim(0, resolve_shap_mean_axis(maximum * 1.18)[1])
    importance.set_ylim(0.5, count + 0.5)
    importance.set_xlabel("Mean |SHAP value|")
    for f, y in zip(plan.feature_order, positions, strict=True):
        importance.text(
            mean_map[f] + maximum * 0.025,
            y,
            f"{percent[f]:.2f}%  ({mean_map[f]:.3g})",
            va="center",
            fontsize=10,
        )
    cmap = ListedColormap(dashboard.palette_colors)
    for f, y in zip(plan.feature_order, positions, strict=True):
        subset = frame.loc[frame[spec.category_column].astype(str).str.strip() == f]
        x = subset[spec.x_column].to_numpy(dtype=float)
        offset = shap_beeswarm_offsets(x)
        normalized = shap_within_feature_color_values(
            subset, spec.category_column, spec.series[0].color_column
        )
        beeswarm.scatter(x, y + offset, c=normalized, cmap=cmap, vmin=0, vmax=1, s=10, linewidths=0)
    beeswarm.axvline(0, color="#879398", linewidth=0.8)
    beeswarm.set_ylim(0.5, count + 0.5)
    beeswarm.set_xlim(spec.axis_plan.x_from, spec.axis_plan.x_to)
    beeswarm.set_yticks(positions, [""] * count)
    beeswarm.set_xlabel("SHAP value (impact on model output)")
    for axis in (importance, beeswarm):
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(labelsize=11)
    cax = figure.add_axes(regions["colorbar"].matplotlib_bounds(), label="dashboard_colorbar")
    colorbar = figure.colorbar(ScalarMappable(norm=colors.Normalize(0, 1), cmap=cmap), cax=cax)
    colorbar.set_ticks([0, 1], labels=["Low", "High"])
    colorbar.set_label("Relative feature value")
    ring_axis = figure.add_axes(regions["rings"].matplotlib_bounds(), label="dashboard_rings")
    ring_axis.pie(
        [v for _, v in dashboard.ring_group_percentages],
        radius=1,
        colors=[c for _, c in dashboard.group_colors],
        startangle=270,
        counterclock=False,
        wedgeprops={"width": 0.28, "edgecolor": "white"},
    )
    ring_axis.pie(
        [percent[f] for f in dashboard.ring_feature_order],
        radius=0.70,
        colors=[feature_colors[f] for f in dashboard.ring_feature_order],
        startangle=270,
        counterclock=False,
        wedgeprops={"width": 0.28, "edgecolor": "white"},
    )
    ring_axis.text(0, 0, "Feature\ncontribution", ha="center", va="center", fontsize=9)
    ring_axis.set_aspect("equal")
    inset = dashboard.contribution_layout == "inset"
    legend_x, legend_y = (0.35, 0.30) if inset else (0.59, 0.205)
    figure.text(legend_x, legend_y + 0.04, "Feature groups", fontsize=13, fontweight="bold")
    for i, ((g, v), (_, color)) in enumerate(
        zip(dashboard.ring_group_percentages, dashboard.group_colors, strict=True)
    ):
        figure.text(legend_x, legend_y - i * 0.035, f"{g}   {v:.2f}%", color=color, fontsize=12)
