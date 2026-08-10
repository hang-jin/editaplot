"""Origin-free previews driven by the shared scientific plot plan."""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch, PathPatch, Rectangle
from matplotlib.path import Path
from matplotlib.text import Text
from matplotlib.ticker import AutoMinorLocator, FixedLocator, MaxNLocator

from .circular_network_layout import (
    MAX_NODE_GROUP_COUNT,
    NETWORK_EDGE_TRANSPARENCY_PERCENT,
    NETWORK_NODE_GROUP_COLORS,
    CircularNetworkLayoutPlan,
)
from .heatmap_layout import (
    resolve_heatmap_colorbar_geometry,
    resolve_heatmap_layout,
)
from .scientific_visual import (
    AdaptiveOriginStyle,
    interpolate_hex_colors,
    palette_colors,
    series_palette_colors,
    signed_effect_colors,
)
from .scientific_workflow import (
    ScientificPreparation,
    ScientificSeries,
    ScientificWorkflowError,
    evidence_jitter_offsets,
    load_scientific_frame,
    log_decade_increment,
    series_values,
    shap_beeswarm_offsets,
    shap_within_feature_color_values,
)
from .shap_layout import (
    SHAP_FEATURE_VALUE_COLORS,
    SHAP_GROUP_COLORS,
    SHAP_MEAN_ABS_BAR_COLOR,
    SHAP_MEAN_ABS_BAR_EDGE_COLOR,
    SHAP_ZERO_LINE_COLOR,
    resolve_shap_composite_geometry,
    resolve_shap_mean_axis,
)

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Arial",
            "Microsoft YaHei",
            "SimHei",
            "Helvetica",
            "DejaVu Sans",
            "sans-serif",
        ],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "legend.frameon": False,
        "axes.unicode_minus": True,
    }
)


NATURE_PALETTE = palette_colors("comparison_family")

# Origin 2024b's official flat Pie2D template increments wedges in this order.
# Keeping it explicit makes the UI proxy agree with the editable Origin graph.
ORIGIN_PIE_PALETTE = (
    "#F83E42",
    "#2773DB",
    "#3CAF6D",
    "#A66ED7",
    "#D5A100",
    "#56B4E9",
    "#CC79A7",
    "#5F6368",
)

PREVIEW_WIDTH_IN = 7.2

RIETVELD_ROLE_STYLES: dict[str, tuple[str, str]] = {
    "observed": ("marker", "#252B31"),
    "calculated": ("line", "#C64E59"),
    "background": ("secondary_line", "#7B8783"),
    "difference": ("line", "#3E718C"),
}
RIETVELD_PHASE_COLORS = (
    "#5B6F9D",
    "#8A6A9B",
    "#4F8073",
    "#9A7048",
)
CIRCULAR_NETWORK_NODE_COLORS = NETWORK_NODE_GROUP_COLORS
CIRCULAR_NETWORK_EDGE_COLORS = {
    "positive": "#2F6B6F",
    "negative": "#B65C67",
    "neutral": "#7B8794",
}
CIRCULAR_NETWORK_SIGN_LABELS = {
    "positive": "Positive",
    "negative": "Negative",
    "neutral": "Neutral",
}


@dataclass(frozen=True)
class _PreviewStyle:
    height_in: float
    axis_title_pt: float
    tick_label_pt: float
    legend_pt: float
    plot_line_pt: float
    frame_line_pt: float
    error_bar_pt: float
    bar_border_pt: float
    major_tick_pt: float
    minor_tick_pt: float
    marker_pt: float
    fill_transparency_percent: float
    colors: tuple[str, ...]


def _preview_style(figure: Figure) -> _PreviewStyle:
    style = getattr(figure, "_origin_sciplot_preview_style", None)
    if not isinstance(style, _PreviewStyle):
        raise ScientificPreviewError("preview_style_missing", "Adaptive preview style is missing.")
    return style


def _resolved_preview_style(
    style: AdaptiveOriginStyle, marker_size_pt: float, series_count: int
) -> _PreviewStyle:
    page_width_in = style.page_width_cm / 2.54
    scale = PREVIEW_WIDTH_IN / page_width_in
    return _PreviewStyle(
        height_in=PREVIEW_WIDTH_IN * style.page_height_cm / style.page_width_cm,
        axis_title_pt=style.axis_title_size_pt * scale,
        tick_label_pt=style.tick_label_size_pt * scale,
        legend_pt=style.legend_size_pt * scale,
        plot_line_pt=style.plot_line_width_pt * scale,
        frame_line_pt=style.frame_line_width_pt * scale,
        error_bar_pt=style.error_bar_width_pt * scale,
        bar_border_pt=style.bar_border_width_pt * scale,
        major_tick_pt=style.major_tick_length_pt * scale,
        minor_tick_pt=style.minor_tick_length_pt * scale,
        marker_pt=marker_size_pt * scale,
        fill_transparency_percent=style.fill_transparency_percent,
        colors=series_palette_colors(style.palette_name, max(1, series_count)),
    )


def _fill_alpha(style: _PreviewStyle) -> float:
    """Translate Origin percent transparency into Matplotlib opacity."""
    return max(0.0, min(1.0, 1.0 - style.fill_transparency_percent / 100.0))


class ScientificPreviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _matplotlib_label(text: str) -> str:
    """Keep scientific superscripts visible when Matplotlib's Arial lacks the glyph."""
    replacements = {
        "⁻¹": r"$^{-1}$",
        "⁻²": r"$^{-2}$",
        "⁻³": r"$^{-3}$",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text


def _series_label(series: ScientificSeries) -> str:
    if not series.error_kind:
        return series.label
    kind = series.error_kind.upper() if series.error_kind != "custom" else "error"
    return f"{series.label} (±{kind})"


def _new_figure(
    preparation: ScientificPreparation,
    *,
    dual_y: bool = False,
    horizontal_bar: bool = False,
    rotated_category: bool = False,
) -> tuple[Figure, Any]:
    origin_style = preparation.plot_spec.display_plan.figure_style
    if origin_style is None:
        raise ScientificPreviewError("preview_style_missing", "Adaptive figure profile is missing.")
    preview = _resolved_preview_style(
        origin_style,
        preparation.plot_spec.display_plan.marker_size_pt,
        len(preparation.plot_spec.series),
    )
    figure = Figure(
        figsize=(PREVIEW_WIDTH_IN, preview.height_in),
        dpi=100,
        facecolor="white",
    )
    setattr(figure, "_origin_sciplot_preview_style", preview)
    left = origin_style.layer_left_percent / 100.0
    bottom = max(0.06, 1.0 - (origin_style.layer_top_percent + origin_style.layer_height_percent) / 100.0)
    width = origin_style.layer_width_percent / 100.0
    height = origin_style.layer_height_percent / 100.0
    if dual_y:
        width = min(width, 0.76)
    geometry = [left, bottom, width, height]
    axis = figure.add_axes(geometry, facecolor="white")
    return figure, axis


def _new_empty_figure(preparation: ScientificPreparation) -> Figure:
    origin_style = preparation.plot_spec.display_plan.figure_style
    if origin_style is None:
        raise ScientificPreviewError("preview_style_missing", "Adaptive figure profile is missing.")
    series_count = (
        len(preparation.plot_spec.group_order)
        if preparation.plot_spec.plot_kind == "density_ridgeline3d"
        else len(preparation.plot_spec.series)
    )
    preview = _resolved_preview_style(
        origin_style,
        preparation.plot_spec.display_plan.marker_size_pt,
        series_count,
    )
    figure = Figure(
        figsize=(PREVIEW_WIDTH_IN, preview.height_in),
        dpi=100,
        facecolor="white",
    )
    setattr(figure, "_origin_sciplot_preview_style", preview)
    return figure


def _draw_trajectory3d(
    figure: Figure,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    """Draw a non-authoritative proxy of the verified Origin glTraject route."""
    spec = preparation.plot_spec
    if spec.x_column is None or spec.y_column is None or spec.category_column is None:
        raise ScientificPreviewError("trajectory3d_plan_invalid", "The XYZ/Series plan is incomplete.")
    style = _preview_style(figure)
    axis = figure.add_axes([0.10, 0.08, 0.82, 0.84], projection="3d", facecolor="white")
    group_values = frame[spec.category_column].astype(str).str.strip()
    z_column = spec.series[0].source_column
    for index, group in enumerate(spec.group_order):
        mask = group_values == group
        x = frame.loc[mask, spec.x_column].to_numpy(dtype=float, copy=True)
        y = frame.loc[mask, spec.y_column].to_numpy(dtype=float, copy=True)
        z = frame.loc[mask, z_column].to_numpy(dtype=float, copy=True)
        color = style.colors[index % len(style.colors)]
        axis.plot(
            x,
            y,
            z,
            color=color,
            linewidth=style.plot_line_pt,
            marker="o",
            markersize=max(style.marker_pt, 3.5),
            markerfacecolor=color,
            markeredgecolor="white",
            markeredgewidth=max(style.frame_line_pt * 0.45, 0.5),
            zorder=3,
        )
        for x_value, y_value, z_value in zip(x, y, z, strict=True):
            axis.plot(
                [x_value, x_value],
                [y_value, y_value],
                [0.0, z_value],
                color=color,
                linewidth=max(style.frame_line_pt * 0.40, 0.35),
                alpha=0.55,
                zorder=1,
            )
    plan = spec.axis_plan
    if plan.x_from is not None and plan.x_to is not None:
        axis.set_xlim(plan.x_from, plan.x_to)
    axis.set_ylim(plan.y_from, plan.y_to)
    if plan.z_from is not None and plan.z_to is not None:
        axis.set_zlim(plan.z_from, plan.z_to)
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_zlabel(
        _matplotlib_label(spec.z_title or z_column),
        fontsize=style.axis_title_pt,
        fontweight="bold",
    )
    axis.tick_params(labelsize=style.tick_label_pt, width=style.frame_line_pt)
    axis.view_init(elev=15.8, azim=-50.0)
    axis.grid(True, color="#D7DADD", linewidth=0.55)
    for pane_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        pane_axis.pane.set_facecolor((1.0, 1.0, 1.0, 1.0))
        pane_axis.pane.set_edgecolor("#222222")


def _draw_density_ridgeline3d(
    figure: Figure,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    """Preview two supplied profiles and one supplied baseline focus per condition."""

    spec = preparation.plot_spec
    if (
        spec.x_column is None
        or spec.y_column is None
        or spec.category_column is None
        or spec.focal_x_column is None
        or len(spec.series) != 2
        or not spec.condition_positions
    ):
        raise ScientificPreviewError(
            "density_ridgeline3d_plan_invalid",
            "The ordered density-profile/focus plan is incomplete.",
        )
    style = _preview_style(figure)
    axis = figure.add_axes([0.08, 0.08, 0.79, 0.84], projection="3d", facecolor="white")
    conditions = frame[spec.category_column].astype(str).str.strip()
    positions = dict(spec.condition_positions)
    focal_x_values: list[float] = []
    focal_y_values: list[float] = []

    for index, condition in enumerate(spec.group_order):
        mask = conditions == condition
        x = frame.loc[mask, spec.x_column].to_numpy(dtype=float, copy=True)
        y = np.full(x.size, positions[condition], dtype=float)
        solid = frame.loc[mask, spec.series[0].source_column].to_numpy(
            dtype=float,
            copy=True,
        )
        dashed = frame.loc[mask, spec.series[1].source_column].to_numpy(
            dtype=float,
            copy=True,
        )
        color = style.colors[index % len(style.colors)]
        axis.plot(
            x,
            y,
            solid,
            color=color,
            linewidth=style.plot_line_pt,
            linestyle="-",
            marker=None,
            zorder=3,
        )
        axis.plot(
            x,
            y,
            dashed,
            color=color,
            linewidth=style.plot_line_pt,
            linestyle="--",
            marker=None,
            zorder=2,
        )
        focus = frame.loc[mask, spec.focal_x_column].dropna().to_numpy(
            dtype=float,
            copy=True,
        )
        focal_x_values.append(float(focus[0]))
        focal_y_values.append(float(positions[condition]))

    focus_color = "#8A541D"
    axis.scatter(
        focal_x_values,
        focal_y_values,
        np.zeros(len(focal_x_values), dtype=float),
        s=max(style.marker_pt, 5.0) ** 2,
        c=focus_color,
        edgecolors="white",
        linewidths=max(style.frame_line_pt * 0.55, 0.6),
        depthshade=False,
        zorder=5,
    )
    for x_value, y_value in zip(focal_x_values, focal_y_values, strict=True):
        axis.text(
            x_value,
            y_value,
            0.0,
            f" {x_value:.3g}",
            fontsize=max(style.legend_pt * 0.84, 8.0),
            color="#292929",
            zorder=6,
        )

    plan = spec.axis_plan
    if plan.x_from is not None and plan.x_to is not None:
        axis.set_xlim(plan.x_from, plan.x_to)
    axis.set_ylim(plan.y_from, plan.y_to)
    if plan.z_from is not None and plan.z_to is not None:
        axis.set_zlim(plan.z_from, plan.z_to)
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_zlabel(
        _matplotlib_label(spec.z_title or "Density"),
        fontsize=style.axis_title_pt,
        fontweight="bold",
    )
    axis.tick_params(labelsize=style.tick_label_pt, width=style.frame_line_pt)
    axis.view_init(elev=18.0, azim=-55.0)
    axis.grid(True, color="#D9DCDF", linewidth=0.50)
    for pane_axis in (axis.xaxis, axis.yaxis, axis.zaxis):
        pane_axis.pane.set_facecolor((1.0, 1.0, 1.0, 1.0))
        pane_axis.pane.set_edgecolor("#252525")

    axis.legend(
        handles=(
            Line2D([0], [0], color="#343434", linewidth=style.plot_line_pt, linestyle="-"),
            Line2D([0], [0], color="#343434", linewidth=style.plot_line_pt, linestyle="--"),
            Line2D(
                [0],
                [0],
                color="none",
                marker="o",
                markerfacecolor=focus_color,
                markeredgecolor="white",
                markersize=max(style.marker_pt, 5.0),
            ),
        ),
        labels=(
            spec.series[0].label,
            spec.series[1].label,
            "Baseline focal locator / 基线焦点定位点",
        ),
        loc="upper left",
        frameon=False,
        fontsize=style.legend_pt,
        handlelength=1.8,
    )


def _style_axis(axis: Any, *, right_axis: bool = False) -> None:
    style = _preview_style(axis.figure)
    axis.grid(False)
    axis.tick_params(
        axis="both",
        which="major",
        direction="out",
        length=style.major_tick_pt,
        width=style.frame_line_pt,
        labelsize=style.tick_label_pt,
        top=False,
        right=right_axis,
    )
    axis.tick_params(
        axis="both",
        which="minor",
        direction="out",
        length=style.minor_tick_pt,
        width=style.frame_line_pt,
        top=False,
        right=right_axis,
    )
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_color("#111111")
        spine.set_linewidth(style.frame_line_pt)
    axis.xaxis.label.set_fontsize(style.axis_title_pt)
    axis.yaxis.label.set_fontsize(style.axis_title_pt)
    axis.xaxis.label.set_fontweight("bold")
    axis.yaxis.label.set_fontweight("bold")


def _error_values(frame: Any, series: ScientificSeries) -> np.ndarray | None:
    if series.error_column is None:
        return None
    return frame[series.error_column].to_numpy(dtype=float, copy=True)


def _draw_line_profiles(axis: Any, frame: Any, preparation: ScientificPreparation) -> Any | None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.x_column is not None
    x = frame[spec.x_column].to_numpy(dtype=float, copy=True)
    marker_size = style.marker_pt
    right_axis = None
    assignment_roles = dict(preparation.assignments)
    observed_color_index = {
        series.source_column: index for index, series in enumerate(spec.series) if series.series_role != "fit"
    }
    for index, series in enumerate(spec.series):
        target = axis
        if series.axis == "right":
            if right_axis is None:
                right_axis = axis.twinx()
                _style_axis(right_axis, right_axis=True)
            target = right_axis
        y = series_values(frame, series)
        color_index = (
            observed_color_index.get(series.paired_with, index)
            if series.series_role == "fit"
            else observed_color_index.get(series.source_column, index)
        )
        color = style.colors[color_index % len(style.colors)]
        line_style = "-"
        if spec.plot_kind == "decision_curve":
            role = assignment_roles.get(series.source_column)
            if role == "treat_all":
                color = "#6F7478"
                line_style = "--"
            elif role == "treat_none":
                color = "#A7ABAE"
                line_style = ":"
        label = "_nolegend_" if series.series_role == "fit" else _series_label(series)
        if spec.plot_kind in {"scatter", "bland_altman"}:
            target.scatter(
                x,
                y,
                s=marker_size**2,
                color=color,
                edgecolors="white",
                linewidths=max(style.frame_line_pt * 0.55, 0.7),
                alpha=0.90,
                label=label,
                zorder=3,
            )
        elif spec.plot_kind == "pl_decay" and series.series_role != "fit":
            target.scatter(
                x,
                y,
                s=marker_size**2,
                facecolors="white",
                edgecolors=color,
                linewidths=max(style.frame_line_pt * 0.72, 0.8),
                alpha=0.92,
                label=label,
                zorder=3,
            )
        elif spec.plot_kind == "pl_decay":
            target.plot(
                x,
                y,
                color=color,
                linewidth=style.plot_line_pt,
                label=label,
                zorder=2,
            )
        elif spec.plot_kind == "line_error":
            target.errorbar(
                x,
                y,
                yerr=_error_values(frame, series),
                color=color,
                linewidth=style.plot_line_pt,
                elinewidth=style.error_bar_pt,
                capsize=style.marker_pt * 0.65,
                capthick=style.error_bar_pt,
                marker="o",
                markersize=marker_size,
                markerfacecolor="white",
                markeredgewidth=style.frame_line_pt * 0.55,
                label=label,
                zorder=3,
            )
        elif spec.plot_kind in {
            "nyquist",
            "paired_trajectory",
            "calibration_curve",
            "pl_spectrum",
            "uv_vis",
        }:
            target.plot(
                x,
                y,
                color=color,
                linewidth=style.plot_line_pt,
                marker="o" if marker_size > 0.0 else None,
                markersize=marker_size,
                markerfacecolor="white",
                markeredgewidth=style.frame_line_pt * 0.55,
                alpha=0.66 if spec.plot_kind == "paired_trajectory" else 0.94,
                label=label,
                zorder=3,
            )
        else:
            target.plot(
                x,
                y,
                color=color,
                linewidth=style.plot_line_pt,
                linestyle=line_style,
                label=label,
                zorder=3,
            )
    return right_axis


def _draw_rietveld_refinement(
    axis: Any,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    """Draw the confirmed GSAS/Rietveld grammar without altering source values."""
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    if spec.x_column is None:
        raise ScientificPreviewError(
            "rietveld_x_missing",
            "Rietveld preview needs the confirmed diffraction-angle column.",
        )
    if spec.display_transform != "identity":
        raise ScientificPreviewError(
            "rietveld_display_transform_invalid",
            "Rietveld profiles must use their source values directly.",
        )
    x = frame[spec.x_column].to_numpy(dtype=float, copy=True)
    for series in spec.series:
        if series.series_role not in RIETVELD_ROLE_STYLES:
            raise ScientificPreviewError(
                "rietveld_role_invalid",
                f"Unsupported Rietveld profile role: {series.series_role}",
            )
        if series.transform != "identity":
            raise ScientificPreviewError(
                "rietveld_series_transform_invalid",
                f"Rietveld {series.series_role} values must be plotted directly.",
            )
        mark_kind, color = RIETVELD_ROLE_STYLES[series.series_role]
        y = frame[series.source_column].to_numpy(dtype=float, copy=True)
        if mark_kind == "marker":
            axis.plot(
                x,
                y,
                linestyle="none",
                marker="o",
                markersize=max(2.4, style.marker_pt * 0.72),
                markerfacecolor="white",
                markeredgecolor=color,
                markeredgewidth=max(0.65, style.frame_line_pt * 0.50),
                label=_series_label(series),
                zorder=4,
            )
        else:
            axis.plot(
                x,
                y,
                color=color,
                linewidth=(
                    style.plot_line_pt if series.series_role == "calculated" else style.plot_line_pt * 0.78
                ),
                linestyle="--" if mark_kind == "secondary_line" else "-",
                label=_series_label(series),
                zorder=3 if series.series_role == "calculated" else 2,
            )

    phase_tick_columns = tuple(getattr(spec, "phase_tick_columns", ()))
    y_span = float(spec.axis_plan.y_to - spec.axis_plan.y_from)
    if phase_tick_columns and (not math.isfinite(y_span) or y_span <= 0.0):
        raise ScientificPreviewError(
            "rietveld_phase_lane_invalid",
            "Rietveld phase lanes need a finite positive Y range.",
        )
    phase_step = min(
        0.010,
        0.034 / max(1, len(phase_tick_columns) - 1),
    )
    for index, phase_column in enumerate(phase_tick_columns):
        if phase_column not in frame.columns:
            raise ScientificPreviewError(
                "rietveld_phase_column_missing",
                f"Rietveld phase-tick column is missing: {phase_column}",
            )
        phase_x = frame[phase_column].to_numpy(dtype=float, copy=True)
        finite_x = phase_x[np.isfinite(phase_x)]
        if not finite_x.size:
            continue
        lane_y = float(spec.axis_plan.y_from + y_span * (0.010 + index * phase_step))
        axis.plot(
            finite_x,
            np.full(finite_x.shape, lane_y, dtype=float),
            linestyle="none",
            marker="|",
            markersize=max(5.0, style.marker_pt * 1.10),
            markeredgewidth=max(1.0, style.frame_line_pt * 0.72),
            color=RIETVELD_PHASE_COLORS[index % len(RIETVELD_PHASE_COLORS)],
            label=str(phase_column),
            zorder=5,
        )


def _draw_calibration_distribution(
    axis: Any,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    spec = preparation.plot_spec
    if spec.plot_kind != "calibration_curve" or not spec.series:
        return
    count_column = spec.series[0].size_column
    if count_column is None or spec.x_column is None:
        raise ScientificPreviewError(
            "calibration_count_missing",
            "Calibration preview needs the frozen bin-count column.",
        )
    counts = frame[count_column].to_numpy(dtype=float, copy=True)
    finite = counts[np.isfinite(counts)]
    maximum = float(np.max(finite)) if finite.size else 0.0
    if maximum <= 0.0:
        raise ScientificPreviewError(
            "calibration_count_invalid",
            "Calibration bin counts need at least one positive value.",
        )
    x = frame[spec.x_column].to_numpy(dtype=float, copy=True)
    unique_x = np.sort(np.unique(x[np.isfinite(x)]))
    width = float(np.min(np.diff(unique_x))) * 0.70 if unique_x.size > 1 else 0.07
    axis.bar(
        x,
        counts / maximum * 0.12,
        width=width,
        color="#A9CBE8",
        edgecolor="#7398B8",
        linewidth=_preview_style(axis.figure).bar_border_pt,
        alpha=_fill_alpha(_preview_style(axis.figure)),
        zorder=0,
    )


def _draw_reference_lines(axis: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    if spec.reference_geometry == "diagonal":
        axis.plot(
            [spec.axis_plan.x_from, spec.axis_plan.x_to],
            [spec.axis_plan.y_from, spec.axis_plan.y_to],
            color="#8A8F94",
            linewidth=_preview_style(axis.figure).frame_line_pt,
            zorder=1,
        )
    elif spec.reference_geometry == "horizontal":
        for index, value in enumerate(spec.reference_values):
            base_label = (
                spec.reference_labels[index]
                if index < len(spec.reference_labels)
                else f"Reference {index + 1}"
            )
            axis.axhline(
                value,
                color=("#B65C67" if spec.plot_kind == "bland_altman" and index == 0 else "#8A8F94"),
                linewidth=_preview_style(axis.figure).frame_line_pt,
                linestyle="-" if spec.plot_kind == "bland_altman" and index == 0 else "--",
                label=None,
                zorder=1,
            )
            if spec.plot_kind == "bland_altman":
                axis.text(
                    0.975,
                    value,
                    f"{base_label}  {value:+.2f}",
                    transform=axis.get_yaxis_transform(),
                    ha="right",
                    va="bottom",
                    color="#A54855" if index == 0 else "#62676B",
                    fontsize=_preview_style(axis.figure).legend_pt * 0.88,
                    zorder=4,
                )


def _draw_grouped_box(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    positions = np.arange(1, len(spec.series) + 1, dtype=float)
    group_colors = {
        group: style.colors[index % len(style.colors)] for index, group in enumerate(spec.group_order)
    }
    y_span = spec.axis_plan.y_to - spec.axis_plan.y_from
    for index, (position, series) in enumerate(zip(positions, spec.series, strict=True)):
        values = frame[series.source_column].dropna().to_numpy(dtype=float)
        color = group_colors.get(series.group or "", style.colors[index % len(style.colors)])
        result = axis.boxplot(
            [values],
            positions=[position],
            widths=0.58,
            patch_artist=True,
            showfliers=False,
            whis=1.5,
            boxprops={
                "facecolor": color,
                "edgecolor": color,
                "alpha": _fill_alpha(style),
                "linewidth": style.bar_border_pt,
            },
            whiskerprops={
                "color": color,
                "linewidth": style.plot_line_pt,
                "linestyle": "--",
            },
            capprops={"color": color, "linewidth": style.plot_line_pt},
            medianprops={"color": "#353B40", "linewidth": style.plot_line_pt},
        )
        _ = result
        offsets = evidence_jitter_offsets(values.size, index) * 0.72
        axis.scatter(
            np.full(values.size, position) + offsets,
            values,
            s=(style.marker_pt * 0.76) ** 2,
            color="#1F252A",
            edgecolors="white",
            linewidths=max(0.45, style.frame_line_pt * 0.35),
            alpha=_fill_alpha(style),
            zorder=4,
        )
        axis.text(
            position,
            spec.axis_plan.y_from + y_span * 0.10,
            f"n={values.size}",
            ha="center",
            va="center",
            fontsize=style.legend_pt * 0.78,
            fontfamily="Arial",
            color="#59636B",
        )
    category_positions: list[float] = []
    for category in spec.category_order:
        members = [
            positions[index] for index, series in enumerate(spec.series) if series.category == category
        ]
        category_positions.append(float(np.mean(members)))
    axis.set_xticks(category_positions, spec.category_order)
    axis.set_xlim(0.4, len(spec.series) + 0.6)
    handles = [
        Rectangle(
            (0, 0),
            1,
            1,
            facecolor=group_colors[group],
            edgecolor=group_colors[group],
            alpha=_fill_alpha(style),
        )
        for group in spec.group_order
    ]
    axis.legend(
        handles,
        spec.group_order,
        frameon=False,
        fontsize=style.legend_pt,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncols=min(3, len(handles)),
    )


def _draw_uv_vis_inset(figure: Figure, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    if not spec.inset_series or spec.inset_x_column is None or spec.inset_axis_plan is None:
        return
    style = _preview_style(figure)
    inset = figure.add_axes([0.57, 0.48, 0.33, 0.36], facecolor="white")
    x = frame[spec.inset_x_column].to_numpy(dtype=float, copy=True)
    for index, series in enumerate(spec.inset_series):
        y = frame[series.source_column].to_numpy(dtype=float, copy=True)
        color = style.colors[2 % len(style.colors)] if series.series_role != "fit" else "#27343D"
        inset.plot(
            x,
            y,
            color=color,
            linewidth=style.plot_line_pt * (0.88 if series.series_role == "fit" else 0.72),
            marker=None if series.series_role == "fit" else "o",
            markersize=style.marker_pt * 0.48 if series.series_role != "fit" else 0,
            markerfacecolor="white",
            markeredgewidth=max(0.55, style.frame_line_pt * 0.42),
        )
    plan = spec.inset_axis_plan
    inset.set_xlim(plan.x_from, plan.x_to)
    inset.set_ylim(plan.y_from, plan.y_to)
    inset.set_xlabel(spec.inset_x_title or "", fontsize=style.axis_title_pt * 0.70, fontweight="bold")
    inset.set_ylabel(spec.inset_y_title or "", fontsize=style.axis_title_pt * 0.70, fontweight="bold")
    inset.tick_params(
        axis="both",
        which="major",
        direction="out",
        length=style.major_tick_pt * 0.62,
        width=style.frame_line_pt * 0.76,
        labelsize=style.tick_label_pt * 0.70,
        top=False,
        right=False,
    )
    for spine in inset.spines.values():
        spine.set_linewidth(style.frame_line_pt * 0.76)
    if spec.inset_annotation:
        inset.text(
            0.05,
            0.08,
            spec.inset_annotation,
            transform=inset.transAxes,
            fontsize=style.legend_pt * 0.72,
            color="#27343D",
            fontweight="bold",
        )


def _draw_xrd_stacked(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.x_column is not None
    x = frame[spec.x_column].to_numpy(dtype=float, copy=True)
    offset = 1.15
    for index, series in enumerate(spec.series):
        values = series_values(frame, series)
        finite = values[np.isfinite(values)]
        scale = float(np.max(np.abs(finite))) if finite.size else 1.0
        if math.isclose(scale, 0.0):
            scale = 1.0
        display = values / scale + index * offset
        axis.plot(
            x,
            display,
            color=style.colors[index % len(style.colors)],
            linewidth=style.plot_line_pt,
            label=series.label,
            zorder=3,
        )
    axis.set_ylim(-0.10, max(1.05, (len(spec.series) - 1) * offset + 1.10))
    axis.set_yticks([])
    axis.tick_params(axis="y", which="both", length=0)


def _draw_bars(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.category_column is not None
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    x = np.arange(len(categories), dtype=float)
    count = len(spec.series)
    spacing = spec.display_plan.bar_group_span / max(count, 1)
    width = min(spec.display_plan.bar_inner_width / max(count, 1), 0.62)
    for index, series in enumerate(spec.series):
        offset = (index - (count - 1) / 2.0) * spacing
        axis.bar(
            x + offset,
            series_values(frame, series),
            width=width,
            yerr=_error_values(frame, series),
            color=style.colors[index % len(style.colors)],
            alpha=_fill_alpha(style),
            edgecolor="#111111",
            linewidth=style.bar_border_pt,
            error_kw={
                "elinewidth": style.error_bar_pt,
                "capthick": style.error_bar_pt,
                "capsize": style.marker_pt * 0.60,
            },
            label=_series_label(series),
            zorder=3,
        )
    axis.set_xticks(
        x,
        categories,
        rotation=spec.display_plan.category_label_rotation_deg,
        ha="right" if spec.display_plan.category_label_rotation_deg else "center",
    )
    axis.set_xlim(-0.60, max(len(categories) - 0.40, 0.60))


def _draw_horizontal_bars(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.category_column is not None
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    y = np.arange(len(categories), dtype=float)
    count = len(spec.series)
    spacing = spec.display_plan.bar_group_span / max(count, 1)
    height = min(spec.display_plan.bar_inner_width / max(count, 1), 0.62)
    ablation_colors: tuple[str, ...] = ()
    if count == 1:
        values = series_values(frame, spec.series[0])
        finite = values[np.isfinite(values)]
        if finite.size and float(np.min(finite)) < 0 < float(np.max(finite)):
            ablation_colors = signed_effect_colors(values)
        else:
            ablation_colors = interpolate_hex_colors(style.colors[0], style.colors[-1], len(categories))
    for index, series in enumerate(spec.series):
        offset = (index - (count - 1) / 2.0) * spacing
        axis.barh(
            y + offset,
            series_values(frame, series),
            xerr=_error_values(frame, series),
            height=height,
            color=(ablation_colors if ablation_colors else style.colors[index % len(style.colors)]),
            alpha=_fill_alpha(style),
            edgecolor="#111111",
            linewidth=style.bar_border_pt,
            error_kw={
                "elinewidth": style.error_bar_pt,
                "capthick": style.error_bar_pt,
                "capsize": style.marker_pt * 0.60,
            },
            label=_series_label(series),
            zorder=3,
        )
    axis.set_yticks(y, categories)
    axis.set_ylim(-0.60, max(len(categories) - 0.40, 0.60))
    axis.invert_yaxis()


def _draw_stacked_bars(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.category_column is not None
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    x = np.arange(len(categories), dtype=float)
    values = np.column_stack([series_values(frame, item) for item in spec.series])
    if spec.plot_kind == "percent_stacked_bar":
        totals = np.nansum(values, axis=1)
        values = (
            np.divide(
                values,
                totals[:, None],
                out=np.zeros_like(values),
                where=totals[:, None] > 0,
            )
            * 100.0
        )
    bottom = np.zeros(len(categories), dtype=float)
    for index, series in enumerate(spec.series):
        display = np.nan_to_num(values[:, index], nan=0.0)
        axis.bar(
            x,
            display,
            bottom=bottom,
            width=spec.display_plan.bar_inner_width,
            color=style.colors[index % len(style.colors)],
            alpha=_fill_alpha(style),
            edgecolor="#111111",
            linewidth=style.bar_border_pt,
            label=series.label,
            zorder=3,
        )
        bottom += display
    if spec.plot_kind == "stacked_bar" and spec.aggregate_error_column:
        errors = frame[spec.aggregate_error_column].to_numpy(dtype=float, copy=True)
        axis.errorbar(
            x,
            bottom,
            yerr=errors,
            fmt="none",
            ecolor="#202020",
            elinewidth=style.error_bar_pt,
            capthick=style.error_bar_pt,
            capsize=style.marker_pt * 0.60,
            zorder=5,
        )
    axis.set_xticks(
        x,
        categories,
        rotation=spec.display_plan.category_label_rotation_deg,
        ha="right" if spec.display_plan.category_label_rotation_deg else "center",
    )
    axis.set_xlim(-0.60, max(len(categories) - 0.40, 0.60))


def _finite_series(frame: Any, series: ScientificSeries) -> np.ndarray:
    values = frame[series.source_column].to_numpy(dtype=float, copy=True)
    return values[np.isfinite(values)]


def _draw_raw_summary(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    """Draw every observation plus a compact median line."""
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    positions = np.arange(1, len(spec.series) + 1, dtype=float)
    for series_index, (position, series) in enumerate(zip(positions, spec.series)):
        values = _finite_series(frame, series)
        offsets = evidence_jitter_offsets(values.size, series_index)
        color = style.colors[series_index % len(style.colors)]
        axis.scatter(
            np.full(values.size, position) + offsets,
            values,
            s=style.marker_pt**2,
            color=color,
            edgecolors="white",
            linewidths=max(0.35, style.frame_line_pt * 0.42),
            alpha=_fill_alpha(style),
            zorder=3,
        )
        axis.hlines(
            float(np.median(values)),
            position - 0.23,
            position + 0.23,
            color="#17212B",
            linewidth=max(style.plot_line_pt, style.frame_line_pt * 1.05),
            zorder=4,
        )
    axis.set_xlim(0.5, len(spec.series) + 0.5)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xticks(positions, [series.label for series in spec.series])
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_minor_locator(AutoMinorLocator(2))


def _draw_violin(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    """Mirror Origin's Box_Violin evidence structure for the UI proxy."""
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    datasets = [_finite_series(frame, series) for series in spec.series]
    positions = np.arange(1, len(datasets) + 1, dtype=float)
    violin = axis.violinplot(
        datasets,
        positions=positions,
        widths=0.72,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for index, body in enumerate(violin["bodies"]):
        color = style.colors[index % len(style.colors)]
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_linewidth(style.bar_border_pt)
        body.set_alpha(_fill_alpha(style))
    boxes = axis.boxplot(
        datasets,
        positions=positions,
        widths=0.16,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#17212B", "linewidth": style.plot_line_pt},
        whiskerprops={"color": "#39424E", "linewidth": style.frame_line_pt * 0.8},
        capprops={"color": "#39424E", "linewidth": style.frame_line_pt * 0.8},
    )
    for index, box in enumerate(boxes["boxes"]):
        box.set_facecolor(style.colors[index % len(style.colors)])
        box.set_edgecolor("#39424E")
        box.set_linewidth(style.bar_border_pt)
        box.set_alpha(_fill_alpha(style))
    axis.set_xlim(0.5, len(datasets) + 0.5)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xticks(positions, [series.label for series in spec.series])
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_minor_locator(AutoMinorLocator(2))


def _draw_raincloud(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    """Mirror Origin's verified ``Box_HalfViolin`` evidence structure."""
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    datasets = [_finite_series(frame, series) for series in spec.series]
    positions = np.arange(1, len(datasets) + 1, dtype=float)
    violin = axis.violinplot(
        datasets,
        positions=positions,
        widths=0.74,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for index, (position, body) in enumerate(zip(positions, violin["bodies"])):
        color = style.colors[index % len(style.colors)]
        for path in body.get_paths():
            vertices = path.vertices
            vertices[:, 0] = np.maximum(vertices[:, 0], position)
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_linewidth(style.bar_border_pt)
        body.set_alpha(_fill_alpha(style))

    for index, (position, values) in enumerate(zip(positions, datasets)):
        color = style.colors[index % len(style.colors)]
        offsets = evidence_jitter_offsets(values.size, index)
        raw_x = np.full(values.size, position - 0.20) + offsets * 0.46
        axis.scatter(
            raw_x,
            values,
            s=(style.marker_pt * 0.76) ** 2,
            color=color,
            edgecolors="white",
            linewidths=max(0.35, style.frame_line_pt * 0.40),
            alpha=_fill_alpha(style),
            zorder=3,
        )
        mean = float(np.mean(values))
        sd = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
        axis.errorbar(
            position,
            mean,
            yerr=sd,
            fmt="o",
            markersize=style.marker_pt * 0.72,
            markerfacecolor="white",
            markeredgecolor="#17212B",
            markeredgewidth=max(0.45, style.frame_line_pt * 0.55),
            ecolor="#17212B",
            elinewidth=style.plot_line_pt * 0.70,
            capsize=style.marker_pt * 0.42,
            zorder=5,
        )
    axis.set_xlim(0.5, len(datasets) + 0.5)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xticks(positions, [series.label for series in spec.series])
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_minor_locator(AutoMinorLocator(2))


def _draw_shap_composite(
    figure: Figure,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    """Draw the selected SHAP profile from frozen, source-bound summaries."""

    spec = preparation.plot_spec
    plan = spec.shap_plan
    origin_style = spec.display_plan.figure_style
    if plan is None or origin_style is None:
        raise ScientificPreviewError(
            "shap_composite_plan_missing",
            "The frozen SHAP composite plan or adaptive style is missing.",
        )
    geometry = resolve_shap_composite_geometry(plan.profile, origin_style)
    if plan.layout_version != geometry.layout_version:
        raise ScientificPreviewError(
            "shap_composite_layout_version_mismatch",
            "The frozen SHAP plan and preview layout contract do not match.",
        )
    style = _preview_style(figure)
    series = spec.series[0]
    if spec.category_column is None or series.color_column is None:
        raise ScientificPreviewError(
            "shap_composite_roles_missing",
            "The SHAP feature or feature-value color role is missing.",
        )
    features = np.asarray(
        [str(value).strip() for value in frame[spec.category_column]],
        dtype=object,
    )
    shap_values = frame[series.source_column].to_numpy(dtype=float, copy=True)
    color_values = shap_within_feature_color_values(
        frame,
        spec.category_column,
        series.color_column,
    )
    colormap = mpl.colors.LinearSegmentedColormap.from_list(
        "EditaPlotShapFeatureValue",
        SHAP_FEATURE_VALUE_COLORS,
    )
    color_norm = mpl.colors.Normalize(vmin=0.0, vmax=1.0)
    count = len(plan.feature_order)
    positions = np.arange(count, 0, -1, dtype=float)
    main_bounds = geometry.region("shap_beeswarm").matplotlib_bounds()

    if plan.profile != "beeswarm_only":
        mean_axis = figure.add_axes(
            main_bounds,
            facecolor="none",
            label="shap_mean_abs",
            zorder=1,
        )
        _style_axis(mean_axis)
        mean_values = dict(plan.mean_abs_values)
        widths = np.asarray(
            [float(mean_values[feature]) for feature in plan.feature_order],
            dtype=float,
        )
        mean_axis.barh(
            positions,
            widths,
            height=0.68,
            color=SHAP_MEAN_ABS_BAR_COLOR,
            edgecolor=SHAP_MEAN_ABS_BAR_EDGE_COLOR,
            linewidth=max(0.35, style.bar_border_pt * 0.55),
            alpha=0.42,
            zorder=1,
        )
        mean_max = float(np.max(widths)) if widths.size else 0.0
        mean_from, mean_to, mean_step = resolve_shap_mean_axis(mean_max)
        mean_axis.set_xlim(mean_from, mean_to)
        mean_axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
        mean_axis.set_yticks(positions)
        mean_axis.set_yticklabels([])
        mean_axis.set_xlabel(
            "Mean |SHAP value|",
            fontsize=style.axis_title_pt,
            fontweight="bold",
            labelpad=max(2.0, style.major_tick_pt * 0.45),
        )
        mean_axis.xaxis.set_label_position("top")
        mean_axis.xaxis.tick_top()
        mean_axis.set_xticks(
            np.arange(mean_from, mean_to + mean_step * 0.5, mean_step),
        )
        mean_axis.tick_params(
            axis="x",
            which="major",
            top=True,
            labeltop=True,
            bottom=False,
            labelbottom=False,
        )
        mean_axis.tick_params(axis="y", which="both", left=False, right=False)
        mean_axis.spines["left"].set_visible(False)
        mean_axis.spines["right"].set_visible(False)
        mean_axis.spines["bottom"].set_visible(False)

    axis = figure.add_axes(
        main_bounds,
        facecolor="none",
        label="shap_beeswarm",
        zorder=2,
    )
    _style_axis(axis)
    axis.patch.set_alpha(0.0)
    for index, feature in enumerate(plan.feature_order):
        row = float(count - index)
        members = np.flatnonzero(features == feature)
        offsets = shap_beeswarm_offsets(shap_values[members])
        axis.scatter(
            shap_values[members],
            np.full(members.size, row) + offsets,
            c=color_values[members],
            cmap=colormap,
            norm=color_norm,
            s=style.marker_pt**2,
            edgecolors="white",
            linewidths=max(0.25, style.frame_line_pt * 0.28),
            alpha=0.90,
            zorder=3,
        )
    axis.axvline(
        0.0,
        color=SHAP_ZERO_LINE_COLOR,
        linewidth=style.frame_line_pt,
        linestyle="--",
        zorder=1,
    )
    axis.set_yticks(positions, list(plan.feature_order))
    axis.set_xlim(spec.axis_plan.x_from, spec.axis_plan.x_to)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel("")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.xaxis.set_minor_locator(AutoMinorLocator(2))
    axis.yaxis.set_minor_locator(FixedLocator([]))

    colorbar_axis = figure.add_axes(
        geometry.region("shap_feature_value_colorbar").matplotlib_bounds(),
        facecolor="white",
        label="shap_feature_value_colorbar",
        zorder=3,
    )
    scalar_mappable = mpl.cm.ScalarMappable(norm=color_norm, cmap=colormap)
    scalar_mappable.set_array(np.asarray([0.0, 1.0], dtype=float))
    colorbar = figure.colorbar(scalar_mappable, cax=colorbar_axis, orientation="vertical")
    colorbar.set_ticks((0.0, 1.0))
    colorbar.set_ticklabels(("Low", "High"))
    colorbar.set_label(
        "Feature value",
        fontsize=style.legend_pt,
        fontweight="bold",
        labelpad=max(2.0, style.major_tick_pt * 0.40),
    )
    colorbar_axis.yaxis.set_label_position("left")
    colorbar_axis.tick_params(
        axis="y",
        which="major",
        direction="out",
        length=style.major_tick_pt,
        width=style.frame_line_pt,
        labelsize=style.tick_label_pt,
    )
    colorbar.outline.set_linewidth(style.frame_line_pt)
    colorbar.outline.set_edgecolor("#111111")

    if plan.profile == "beeswarm_mean_abs_grouped":
        contribution_axis = figure.add_axes(
            geometry.region("shap_group_contribution").matplotlib_bounds(),
            facecolor="white",
            label="shap_group_contribution",
            zorder=5,
        )
        contributions = tuple((group, float(value)) for group, value in plan.group_contributions)
        group_colors = interpolate_hex_colors(
            SHAP_GROUP_COLORS[0],
            SHAP_GROUP_COLORS[-1],
            len(contributions),
        )
        contribution_axis.pie(
            [value for _group, value in contributions],
            colors=group_colors,
            startangle=90.0,
            counterclock=False,
            normalize=True,
            radius=0.54,
            center=(-0.56, 0.0),
            wedgeprops={
                "edgecolor": "white",
                "linewidth": max(0.45, style.frame_line_pt * 0.62),
            },
        )
        legend_font_size = max(7.0, style.legend_pt * 0.78)
        legend_y = np.linspace(0.69, 0.23, len(contributions))
        for index, ((group, value), y_position) in enumerate(
            zip(contributions, legend_y, strict=True)
        ):
            contribution_axis.add_patch(
                Rectangle(
                    (0.51, float(y_position) - 0.022),
                    0.055,
                    0.044,
                    transform=contribution_axis.transAxes,
                    facecolor=group_colors[index],
                    edgecolor="white",
                    linewidth=max(0.35, style.frame_line_pt * 0.45),
                    clip_on=False,
                )
            )
            contribution_axis.text(
                0.585,
                float(y_position),
                f"{group}  {value:.1f}%",
                transform=contribution_axis.transAxes,
                ha="left",
                va="center",
                color="#263746",
                fontsize=legend_font_size,
                fontweight="bold",
            )
        contribution_axis.set_aspect(1.0, adjustable="box")
        contribution_axis.set_xlim(-1.15, 1.15)
        contribution_axis.set_ylim(-1.08, 1.08)
        contribution_axis.set_title(
            "Relative contribution",
            fontsize=max(7.0, style.legend_pt * 0.82),
            fontweight="bold",
            pad=max(1.0, style.major_tick_pt * 0.28),
        )
        contribution_axis.set_xticks([])
        contribution_axis.set_yticks([])
        contribution_axis.patch.set_alpha(0.94)
        for spine in contribution_axis.spines.values():
            spine.set_visible(False)


def _draw_histogram(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    assert spec.bin_begin is not None and spec.bin_end is not None and spec.bin_size is not None
    bins = np.arange(spec.bin_begin, spec.bin_end + spec.bin_size * 0.5, spec.bin_size)
    for index, series in enumerate(spec.series):
        values = _finite_series(frame, series)
        color = style.colors[index % len(style.colors)]
        axis.hist(
            values,
            bins=bins,
            histtype="stepfilled",
            color=color,
            edgecolor=color,
            linewidth=style.frame_line_pt,
            alpha=_fill_alpha(style),
            label=series.label,
        )
    axis.set_xlim(spec.axis_plan.x_from, spec.axis_plan.x_to)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.xaxis.set_minor_locator(AutoMinorLocator(2))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
    if len(spec.series) > 1:
        axis.legend(frameon=False, fontsize=style.legend_pt, handlelength=1.5)


def _draw_forest(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    series = spec.series[0]
    assert spec.category_column and series.lower_column and series.upper_column
    estimates = frame[series.source_column].to_numpy(dtype=float, copy=True)
    lower = frame[series.lower_column].to_numpy(dtype=float, copy=True)
    upper = frame[series.upper_column].to_numpy(dtype=float, copy=True)
    positions = np.arange(len(frame), 0, -1, dtype=float)
    color = style.colors[0]
    axis.hlines(positions, lower, upper, color=color, linewidth=style.plot_line_pt, zorder=2)
    axis.vlines(
        np.concatenate((lower, upper)),
        np.concatenate((positions - 0.13, positions - 0.13)),
        np.concatenate((positions + 0.13, positions + 0.13)),
        color=color,
        linewidth=style.plot_line_pt,
        zorder=2,
    )
    axis.scatter(
        estimates,
        positions,
        s=style.marker_pt**2,
        color=color,
        edgecolors="white",
        linewidths=max(0.4, style.frame_line_pt * 0.45),
        zorder=3,
    )
    if spec.reference_value is not None:
        axis.axvline(
            spec.reference_value,
            color="#777777",
            linewidth=style.frame_line_pt,
            linestyle="--",
            zorder=1,
        )
    axis.set_xlim(spec.axis_plan.x_from, spec.axis_plan.x_to)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_yticks(positions, [str(value) for value in frame[spec.category_column].tolist()])
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel("")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.xaxis.set_minor_locator(AutoMinorLocator(2))
    axis.yaxis.set_minor_locator(FixedLocator([]))


def _draw_bubble(axis: Any, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    series = spec.series[0]
    assert spec.x_column and series.size_column
    x = frame[spec.x_column].to_numpy(dtype=float, copy=True)
    y = frame[series.source_column].to_numpy(dtype=float, copy=True)
    size = frame[series.size_column].to_numpy(dtype=float, copy=True)
    root = np.sqrt(size)
    span = float(np.max(root) - np.min(root))
    normalized = np.zeros_like(root) if span == 0.0 else (root - np.min(root)) / span
    diameters = style.marker_pt * (0.85 + normalized * 1.45)
    color = style.colors[0]
    axis.scatter(
        x,
        y,
        s=diameters**2,
        color=color,
        edgecolors="#FFFFFF",
        linewidths=max(0.45, style.frame_line_pt * 0.48),
        alpha=_fill_alpha(style),
    )
    axis.set_xlim(spec.axis_plan.x_from, spec.axis_plan.x_to)
    axis.set_ylim(spec.axis_plan.y_from, spec.axis_plan.y_to)
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.xaxis.set_minor_locator(AutoMinorLocator(2))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_minor_locator(AutoMinorLocator(2))
    axis.text(
        0.035,
        0.955,
        f"Bubble area = {series.size_column} ({float(np.min(size)):g}-{float(np.max(size)):g})",
        transform=axis.transAxes,
        ha="left",
        va="top",
        color="#334155",
        fontsize=style.legend_pt,
    )


def _draw_pie(figure: Figure, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(figure)
    assert spec.category_column is not None
    axis = figure.add_axes([0.05, 0.08, 0.62, 0.84], facecolor="white")
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    values = series_values(frame, spec.series[0])
    colors = interpolate_hex_colors(style.colors[0], style.colors[-1], len(values))
    wedges, _, _ = axis.pie(
        values,
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 4.0 else "",
        pctdistance=0.72,
        textprops={"fontsize": style.tick_label_pt},
        wedgeprops={"edgecolor": "white", "linewidth": style.frame_line_pt * 0.8},
    )
    axis.set_aspect("equal")
    legend = figure.legend(
        wedges,
        categories,
        loc="center right",
        bbox_to_anchor=(0.98, 0.50),
        frameon=False,
        fontsize=style.legend_pt,
    )


def _sankey_depths(edges: list[tuple[str, str, float]]) -> dict[str, int]:
    nodes = list(dict.fromkeys([node for edge in edges for node in edge[:2]]))
    incoming = {node: 0 for node in nodes}
    adjacency = {node: [] for node in nodes}
    for source, target, _value in edges:
        incoming[target] += 1
        adjacency[source].append(target)
    depth = {node: 0 for node in nodes}
    queue = [node for node in nodes if incoming[node] == 0]
    visited: set[str] = set()
    while queue:
        source = queue.pop(0)
        visited.add(source)
        for target in adjacency[source]:
            depth[target] = max(depth[target], depth[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    unresolved = [node for node in nodes if node not in visited]
    for index, node in enumerate(unresolved, start=1):
        depth[node] = index % max(min(len(nodes), 4), 1)
    return depth


def _draw_sankey(figure: Figure, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(figure)
    assert spec.source_column is not None and spec.target_column is not None
    value_column = spec.series[0].source_column
    edges = [
        (str(source), str(target), float(value))
        for source, target, value in zip(
            frame[spec.source_column],
            frame[spec.target_column],
            frame[value_column],
            strict=True,
        )
    ]
    axis = figure.add_axes([0.04, 0.06, 0.92, 0.88], facecolor="white")
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")
    depth = _sankey_depths(edges)
    max_depth = max(depth.values(), default=1)
    incoming: dict[str, float] = {node: 0.0 for node in depth}
    outgoing: dict[str, float] = {node: 0.0 for node in depth}
    for source, target, value in edges:
        outgoing[source] += value
        incoming[target] += value
    weights = {node: max(incoming[node], outgoing[node], 1e-12) for node in depth}
    columns: dict[int, list[str]] = {}
    for node, column in depth.items():
        columns.setdefault(column, []).append(node)
    positions: dict[str, tuple[float, float, float]] = {}
    gap = 0.035
    for column, nodes in columns.items():
        total = sum(weights[node] for node in nodes)
        available = 0.88 - gap * max(len(nodes) - 1, 0)
        cursor = 0.94
        for node in nodes:
            height = max(available * weights[node] / total, 0.035)
            bottom = cursor - height
            x = 0.04 + (0.88 * column / max(max_depth, 1))
            positions[node] = (x, bottom, height)
            cursor = bottom - gap
    source_cursor = {node: positions[node][1] for node in positions}
    target_cursor = {node: positions[node][1] for node in positions}
    node_index = {node: index for index, node in enumerate(depth)}
    node_width = 0.018
    for source, target, value in edges:
        sx, sy, sh = positions[source]
        tx, ty, th = positions[target]
        source_height = sh * value / outgoing[source]
        target_height = th * value / incoming[target]
        sy0 = source_cursor[source]
        ty0 = target_cursor[target]
        source_cursor[source] += source_height
        target_cursor[target] += target_height
        sx0 = sx + node_width
        tx0 = tx
        control = max((tx0 - sx0) * 0.50, 0.06)
        vertices = [
            (sx0, sy0),
            (sx0 + control, sy0),
            (tx0 - control, ty0),
            (tx0, ty0),
            (tx0, ty0 + target_height),
            (tx0 - control, ty0 + target_height),
            (sx0 + control, sy0 + source_height),
            (sx0, sy0 + source_height),
            (sx0, sy0),
        ]
        codes = [
            Path.MOVETO,
            Path.CURVE4,
            Path.CURVE4,
            Path.CURVE4,
            Path.LINETO,
            Path.CURVE4,
            Path.CURVE4,
            Path.CURVE4,
            Path.CLOSEPOLY,
        ]
        axis.add_patch(
            PathPatch(
                Path(vertices, codes),
                facecolor=style.colors[node_index[source] % len(style.colors)],
                edgecolor="none",
                alpha=0.42,
            )
        )
    for node, (x, y, height) in positions.items():
        color = style.colors[node_index[node] % len(style.colors)]
        axis.add_patch(
            Rectangle(
                (x, y),
                node_width,
                height,
                facecolor=color,
                edgecolor="#111111",
                linewidth=style.frame_line_pt * 0.45,
                alpha=0.92,
            )
        )
        on_right = x > 0.72
        axis.text(
            x - 0.008 if on_right else x + node_width + 0.008,
            y + height / 2.0,
            node,
            ha="right" if on_right else "left",
            va="center",
            fontsize=style.tick_label_pt,
        )


def _circular_network_panel_geometry(panel_count: int) -> tuple[tuple[float, ...], ...]:
    """Reserve a real bottom legend lane instead of overlaying the network."""

    if panel_count == 1:
        return ((0.09, 0.19, 0.82, 0.73),)
    if panel_count == 2:
        return (
            (0.025, 0.20, 0.455, 0.70),
            (0.520, 0.20, 0.455, 0.70),
        )
    if panel_count == 3:
        return (
            (0.012, 0.20, 0.315, 0.70),
            (0.343, 0.20, 0.315, 0.70),
            (0.674, 0.20, 0.315, 0.70),
        )
    if panel_count == 4:
        return (
            (0.035, 0.545, 0.440, 0.365),
            (0.525, 0.545, 0.440, 0.365),
            (0.035, 0.135, 0.440, 0.365),
            (0.525, 0.135, 0.440, 0.365),
        )
    raise ScientificPreviewError(
        "circular_network_panel_count_invalid",
        "Circular-network preview supports one to four panels.",
    )


def _draw_circular_network(
    figure: Figure,
    frame: Any,
    preparation: ScientificPreparation,
) -> None:
    """Draw the frozen shared geometry without deriving or aggregating edges."""

    del frame  # geometry and semantics are already frozen in the preparation
    spec = preparation.plot_spec
    style = _preview_style(figure)
    layout = getattr(spec, "network_layout", None)
    if not isinstance(layout, CircularNetworkLayoutPlan):
        raise ScientificPreviewError(
            "circular_network_layout_missing",
            "The circular-network preparation does not contain a frozen layout plan.",
        )
    panel_geometry = _circular_network_panel_geometry(len(layout.panels))
    node_groups = dict(getattr(spec, "node_groups", ()))
    group_order = tuple(
        dict.fromkeys(node_groups.get(node.node, "Ungrouped") for node in layout.nodes)
    )
    if len(group_order) > MAX_NODE_GROUP_COUNT:
        raise ScientificPreviewError(
            "circular_network_node_group_count",
            (
                f"Circular-network preview supports at most {MAX_NODE_GROUP_COUNT} "
                "independently coloured node groups."
            ),
        )
    origin_style = spec.display_plan.figure_style
    if origin_style is None:
        raise ScientificPreviewError(
            "preview_style_missing",
            "Adaptive figure profile is missing.",
        )
    node_palette = palette_colors(origin_style.palette_name)
    group_colors = {
        group: node_palette[index]
        for index, group in enumerate(group_order)
    }
    panel_count = len(layout.panels)
    node_diameter_pt = max(10.0, style.marker_pt * 1.25)
    node_label_pt = max(7.0, style.tick_label_pt)
    horizontal_limit = {1: 1.48, 2: 1.72, 3: 1.90, 4: 1.72}[panel_count]
    vertical_limit = 1.40 if panel_count < 4 else 1.48
    edge_alpha = 1.0 - NETWORK_EDGE_TRANSPARENCY_PERCENT / 100.0
    signs_used: list[str] = []

    for geometry, panel in zip(panel_geometry, layout.panels, strict=True):
        axis = figure.add_axes(geometry, facecolor="white")
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlim(-horizontal_limit, horizontal_limit)
        axis.set_ylim(-vertical_limit, vertical_limit)
        axis.axis("off")
        axis.set_title(
            panel.panel,
            fontsize=max(8.0, style.axis_title_pt),
            fontweight="semibold",
            pad=max(4.0, style.axis_title_pt * 0.35),
            color="#25313B",
        )
        for edge in panel.edges:
            color = CIRCULAR_NETWORK_EDGE_COLORS[edge.sign]
            if edge.sign not in signs_used:
                signs_used.append(edge.sign)
            vertices = [(point.x, point.y) for point in edge.sampled_points]
            codes = [Path.MOVETO, *([Path.LINETO] * (len(vertices) - 1))]
            axis.add_patch(
                PathPatch(
                    Path(vertices, codes),
                    fill=False,
                    edgecolor=color,
                    linewidth=edge.line_width_pt,
                    alpha=edge_alpha,
                    capstyle="round",
                    joinstyle="round",
                    zorder=1,
                )
            )
            arrow = edge.arrow_segment
            axis.add_patch(
                FancyArrowPatch(
                    (arrow.start.x, arrow.start.y),
                    (arrow.end.x, arrow.end.y),
                    arrowstyle="-|>",
                    mutation_scale=7.0 + edge.line_width_pt * 1.25,
                    linewidth=max(0.8, edge.line_width_pt * 0.62),
                    color=color,
                    alpha=edge_alpha,
                    shrinkA=0.0,
                    shrinkB=0.0,
                    zorder=3,
                )
            )
            if edge.label and panel.edge_labels_visible:
                axis.text(
                    edge.label_anchor.x,
                    edge.label_anchor.y,
                    edge.label,
                    ha="center",
                    va="center",
                    fontsize=max(6.0, node_label_pt * 0.66),
                    color=color,
                    bbox={
                        "boxstyle": "round,pad=0.12",
                        "facecolor": "white",
                        "edgecolor": "none",
                        "alpha": 0.88,
                    },
                    zorder=4,
                )
        for node in layout.nodes:
            group = node_groups.get(node.node, "Ungrouped")
            color = group_colors[group]
            axis.scatter(
                [node.point.x],
                [node.point.y],
                s=node_diameter_pt**2,
                facecolors=color,
                edgecolors="#4B5660",
                linewidths=max(0.6, style.frame_line_pt * 0.55),
                zorder=5,
            )
            radial_length = max(math.hypot(node.point.x, node.point.y), 1e-12)
            label_x = node.point.x + 0.13 * node.point.x / radial_length
            label_y = node.point.y + 0.13 * node.point.y / radial_length
            if abs(node.point.x) < 0.18:
                horizontal_alignment = "center"
            else:
                horizontal_alignment = "left" if node.point.x > 0.0 else "right"
            if abs(node.point.y) < 0.18:
                vertical_alignment = "center"
            else:
                vertical_alignment = "bottom" if node.point.y > 0.0 else "top"
            axis.text(
                label_x,
                label_y,
                node.node,
                ha=horizontal_alignment,
                va=vertical_alignment,
                fontsize=node_label_pt,
                color="#25313B",
                zorder=6,
            )

    legend_handles: list[Any] = [
        Patch(
            facecolor=group_colors[group],
            edgecolor="#4B5660",
            linewidth=max(0.5, style.frame_line_pt * 0.45),
            label=group,
        )
        for group in group_order
    ]
    legend_handles.extend(
        Line2D(
            [0],
            [0],
            color=CIRCULAR_NETWORK_EDGE_COLORS[sign],
            linewidth=2.2,
            label=CIRCULAR_NETWORK_SIGN_LABELS[sign],
        )
        for sign in signs_used
    )
    if legend_handles:
        figure.legend(
            handles=legend_handles,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.018),
            ncol=min(6, len(legend_handles)),
            frameon=False,
            fontsize=max(7.0, style.legend_pt),
            handlelength=1.5,
            columnspacing=1.15,
            handletextpad=0.45,
        )


def _draw_radar(figure: Figure, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(figure)
    assert spec.category_column is not None
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    count = len(categories)
    angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    closed_angles = np.concatenate([angles, angles[:1]])
    origin_style = spec.display_plan.figure_style
    assert origin_style is not None
    axis = figure.add_axes(
        [
            origin_style.layer_left_percent / 100.0,
            max(
                0.08,
                1.0 - (origin_style.layer_top_percent + origin_style.layer_height_percent) / 100.0,
            ),
            origin_style.layer_width_percent / 100.0,
            origin_style.layer_height_percent / 100.0,
        ],
        projection="polar",
        facecolor="white",
    )
    axis.set_theta_offset(np.pi / 2.0)
    axis.set_theta_direction(-1)
    upper = max(float(np.nanmax(series_values(frame, series))) for series in spec.series)
    upper = max(upper * 1.08, 1.0)
    for index, series in enumerate(spec.series):
        values = series_values(frame, series)
        closed_values = np.concatenate([values, values[:1]])
        color = style.colors[index % len(style.colors)]
        axis.plot(
            closed_angles,
            closed_values,
            color=color,
            linewidth=style.plot_line_pt,
            marker="o",
            markersize=style.marker_pt * 0.80,
            markerfacecolor="white",
            markeredgewidth=style.frame_line_pt * 0.55,
            label=series.label,
            zorder=3,
        )
    axis.set_xticks(angles, categories, fontsize=style.tick_label_pt)
    axis.set_ylim(0.0, upper)
    axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
    axis.tick_params(axis="y", labelsize=style.tick_label_pt * 0.86, pad=2)
    axis.grid(color="#D9DEE5", linewidth=style.frame_line_pt * 0.50, alpha=0.85)
    axis.spines["polar"].set_color("#39424E")
    axis.spines["polar"].set_linewidth(style.frame_line_pt)
    axis.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.08),
        frameon=False,
        fontsize=style.legend_pt,
        handlelength=1.5,
    )


def _draw_heatmap(figure: Figure, frame: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _preview_style(figure)
    assert spec.category_column is not None
    origin_style = spec.display_plan.figure_style
    assert origin_style is not None
    categories = [str(item) for item in frame[spec.category_column].tolist()]
    series_labels = [series.label for series in spec.series]
    values = np.column_stack([series_values(frame, series) for series in spec.series])
    layout = resolve_heatmap_layout(
        x_labels=series_labels,
        y_labels=categories,
        tick_label_size_pt=origin_style.tick_label_size_pt,
        major_tick_length_pt=origin_style.major_tick_length_pt,
    )
    left = origin_style.layer_left_percent / 100.0
    bottom = max(
        0.08,
        1.0 - (origin_style.layer_top_percent + origin_style.layer_height_percent) / 100.0,
    )
    width = min(origin_style.layer_width_percent / 100.0, 0.76)
    height = origin_style.layer_height_percent / 100.0
    axis = figure.add_axes([left, bottom, width, height], facecolor="white")
    finite = values[np.isfinite(values)]
    signed = bool(finite.size and float(np.min(finite)) < 0.0 < float(np.max(finite)))
    if signed:
        magnitude = max(abs(float(np.min(finite))), abs(float(np.max(finite))))
        image = axis.imshow(
            values,
            aspect="auto",
            interpolation="nearest",
            cmap="RdBu_r",
            vmin=-magnitude,
            vmax=magnitude,
        )
    else:
        image = axis.imshow(
            values,
            aspect="auto",
            interpolation="nearest",
            cmap="viridis",
        )
    axis.set_xticks(np.arange(len(series_labels)), layout.x_display_labels)
    axis.set_yticks(np.arange(len(categories)), layout.y_display_labels)
    preview_scale = style.tick_label_pt / origin_style.tick_label_size_pt
    axis.tick_params(
        axis="both",
        which="major",
        labelsize=style.tick_label_pt,
        pad=5,
    )
    axis.tick_params(axis="x", length=layout.x_tick_length_pt * preview_scale)
    axis.tick_params(axis="y", length=layout.y_tick_length_pt * preview_scale)
    if layout.x_rotation_deg:
        for label in axis.get_xticklabels():
            label.set_rotation(layout.x_rotation_deg)
            label.set_ha("right")
    for spine in axis.spines.values():
        spine.set_color("#39424E")
        spine.set_linewidth(style.frame_line_pt)
    if layout.show_cell_labels:
        normalization = image.norm
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                value = values[row, column]
                if not np.isfinite(value):
                    continue
                rgba = image.cmap(normalization(value))
                luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
                axis.text(
                    column,
                    row,
                    f"{value:.2g}",
                    ha="center",
                    va="center",
                    color="white" if luminance < 0.48 else "#17212B",
                    fontsize=layout.cell_label_size_pt * preview_scale,
                )
    geometry = resolve_heatmap_colorbar_geometry(
        origin_style.layer_left_percent,
        origin_style.layer_width_percent,
    )
    color_axis = figure.add_axes(
        [
            geometry.left_fraction,
            bottom,
            geometry.bar_axis_width_fraction,
            height,
        ]
    )
    colorbar = figure.colorbar(image, cax=color_axis)
    colorbar.ax.tick_params(
        labelsize=layout.colorbar_label_size_pt * preview_scale,
        length=style.major_tick_pt * 0.75,
        width=style.frame_line_pt * 0.75,
    )
    colorbar.outline.set_linewidth(style.frame_line_pt * 0.75)


def _set_axis_contract(axis: Any, preparation: ScientificPreparation, right_axis: Any | None) -> None:
    spec = preparation.plot_spec
    style = _preview_style(axis.figure)
    plan = spec.axis_plan
    if spec.plot_kind == "horizontal_bar":
        axis.set_xlabel(
            _matplotlib_label(spec.y_title),
            fontsize=style.axis_title_pt,
            fontweight="bold",
        )
        axis.set_ylabel(
            _matplotlib_label(spec.x_title),
            fontsize=style.axis_title_pt,
            fontweight="bold",
        )
        axis.set_xlim(plan.y_from, plan.y_to)
        axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.xaxis.set_minor_locator(AutoMinorLocator(2))
        return
    axis.set_xlabel(_matplotlib_label(spec.x_title), fontsize=style.axis_title_pt, fontweight="bold")
    axis.set_ylabel(_matplotlib_label(spec.y_title), fontsize=style.axis_title_pt, fontweight="bold")
    if right_axis is not None and spec.y2_title:
        right_axis.set_ylabel(
            _matplotlib_label(spec.y2_title),
            fontsize=style.axis_title_pt,
            fontweight="bold",
        )
    if spec.plot_kind == "grouped_box":
        axis.set_ylim(plan.y_from, plan.y_to)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.yaxis.set_minor_locator(AutoMinorLocator(2))
        return

    if spec.x_scale == "log10":
        axis.set_xscale("log")
        if spec.x_column is not None:
            values = axis.lines[0].get_xdata() if axis.lines else np.asarray([])
            finite = np.asarray(values, dtype=float)
            finite = finite[np.isfinite(finite) & (finite > 0)]
            if finite.size:
                axis.set_xlim(float(np.min(finite)) * 0.90, float(np.max(finite)) * 1.10)
                exponent_from = math.floor(math.log10(float(np.min(finite))))
                exponent_to = math.ceil(math.log10(float(np.max(finite))))
                exponent_step = int(log_decade_increment(finite))
                exponents = np.arange(exponent_from, exponent_to + 1, exponent_step)
                axis.xaxis.set_major_locator(FixedLocator(np.power(10.0, exponents)))
    elif plan.x_from is not None and plan.x_to is not None:
        axis.set_xlim(plan.x_from, plan.x_to)
        axis.xaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.xaxis.set_minor_locator(AutoMinorLocator(2))

    if spec.plot_kind == "percent_stacked_bar":
        axis.set_ylim(0.0, 100.0)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.yaxis.set_minor_locator(AutoMinorLocator(2))
    elif spec.plot_kind == "stacked_bar":
        upper = max((patch.get_y() + patch.get_height() for patch in axis.patches), default=1.0)
        if spec.aggregate_error_column:
            frame = load_scientific_frame(preparation.source_path, preparation)
            errors = frame[spec.aggregate_error_column].to_numpy(dtype=float, copy=True)
            totals = np.nansum(
                np.column_stack([series_values(frame, series) for series in spec.series]),
                axis=1,
            )
            upper = max(upper, float(np.nanmax(totals + errors)))
        axis.set_ylim(0.0, upper * 1.08 if upper > 0 else 1.0)
        axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
        axis.yaxis.set_minor_locator(AutoMinorLocator(2))
    elif spec.plot_kind != "stacked_line":
        if spec.y_scale == "log10":
            axis.set_yscale("log")
            frame = load_scientific_frame(preparation.source_path, preparation)
            y_values = np.concatenate([series_values(frame, series) for series in spec.series])
            finite_y = y_values[np.isfinite(y_values) & (y_values > 0)]
            if finite_y.size:
                exponent_from = math.floor(math.log10(float(np.min(finite_y))))
                exponent_to = math.ceil(math.log10(float(np.max(finite_y))))
                exponent_step = int(log_decade_increment(finite_y))
                exponents = np.arange(exponent_from, exponent_to + 1, exponent_step)
                axis.yaxis.set_major_locator(FixedLocator(np.power(10.0, exponents)))
        else:
            axis.set_ylim(plan.y_from, plan.y_to)
            axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
            axis.yaxis.set_minor_locator(AutoMinorLocator(2))
    if right_axis is not None and plan.y2_from is not None and plan.y2_to is not None:
        right_axis.set_ylim(plan.y2_from, plan.y2_to)
        right_axis.yaxis.set_major_locator(MaxNLocator(nbins=6))


def _add_legend(axis: Any, right_axis: Any | None, preparation: ScientificPreparation) -> None:
    if preparation.plot_spec.plot_kind in {"paired_trajectory", "bland_altman", "grouped_box"}:
        return
    visible_series = [series for series in preparation.plot_spec.series if series.series_role != "fit"]
    needs_legend = len(visible_series) > 1 or any(series.error_kind for series in visible_series)
    if not needs_legend:
        return
    style = _preview_style(axis.figure)
    handles, labels = axis.get_legend_handles_labels()
    if right_axis is not None:
        right_handles, right_labels = right_axis.get_legend_handles_labels()
        handles.extend(right_handles)
        labels.extend(right_labels)
    external = preparation.plot_spec.plot_kind == "percent_stacked_bar"
    legend = axis.legend(
        handles,
        labels,
        loc="center left" if external else "best",
        bbox_to_anchor=(1.03, 0.5) if external else None,
        frameon=False,
        fontsize=style.legend_pt,
        handlelength=1.5,
    )


def _apply_font_contract(figure: Figure) -> None:
    """Use Arial unless a CJK label needs the Windows sans-serif fallback."""
    for text in figure.findobj(match=Text):
        if re.search(r"[\u3400-\u9fff]", text.get_text()):
            text.set_fontfamily("Microsoft YaHei")
        else:
            text.set_fontfamily("Arial")


def _build_scientific_preview_figure(preparation: ScientificPreparation) -> Figure:
    try:
        frame = load_scientific_frame(preparation.source_path, preparation)
    except ScientificWorkflowError as exc:
        code = "source_changed" if exc.code == "analysis_changed" else exc.code
        raise ScientificPreviewError(code, str(exc)) from exc

    spec = preparation.plot_spec
    if spec.plot_kind == "trajectory3d":
        figure = _new_empty_figure(preparation)
        _draw_trajectory3d(figure, frame, preparation)
        _apply_font_contract(figure)
        return figure
    if spec.plot_kind == "density_ridgeline3d":
        figure = _new_empty_figure(preparation)
        _draw_density_ridgeline3d(figure, frame, preparation)
        _apply_font_contract(figure)
        return figure
    if spec.plot_kind == "shap_summary":
        figure = _new_empty_figure(preparation)
        _draw_shap_composite(figure, frame, preparation)
        _apply_font_contract(figure)
        return figure
    if spec.plot_kind in {"pie", "sankey", "circular_network", "radar", "heatmap"}:
        figure = _new_empty_figure(preparation)
        if spec.plot_kind == "pie":
            _draw_pie(figure, frame, preparation)
        elif spec.plot_kind == "sankey":
            _draw_sankey(figure, frame, preparation)
        elif spec.plot_kind == "circular_network":
            _draw_circular_network(figure, frame, preparation)
        elif spec.plot_kind == "radar":
            _draw_radar(figure, frame, preparation)
        else:
            _draw_heatmap(figure, frame, preparation)
        _apply_font_contract(figure)
        return figure

    figure, axis = _new_figure(
        preparation,
        dual_y=spec.y2_title is not None,
        horizontal_bar=spec.plot_kind == "horizontal_bar",
        rotated_category=bool(spec.display_plan.category_label_rotation_deg),
    )
    _style_axis(axis)
    if spec.plot_kind == "raw_summary":
        _draw_raw_summary(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "violin":
        _draw_violin(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "raincloud":
        _draw_raincloud(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "grouped_box":
        _draw_grouped_box(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "histogram":
        _draw_histogram(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "forest":
        _draw_forest(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "bubble":
        _draw_bubble(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "stacked_line":
        _draw_xrd_stacked(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "bar_error":
        _draw_bars(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "horizontal_bar":
        _draw_horizontal_bars(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind in {"stacked_bar", "percent_stacked_bar"}:
        _draw_stacked_bars(axis, frame, preparation)
        right_axis = None
    elif spec.plot_kind == "rietveld_refinement":
        _draw_rietveld_refinement(axis, frame, preparation)
        right_axis = None
    else:
        _draw_calibration_distribution(axis, frame, preparation)
        right_axis = _draw_line_profiles(axis, frame, preparation)
        _draw_reference_lines(axis, preparation)
    if spec.plot_kind not in {
        "raw_summary",
        "violin",
        "raincloud",
        "histogram",
        "forest",
        "bubble",
    }:
        _set_axis_contract(axis, preparation, right_axis)
        if spec.plot_kind == "uv_vis":
            _draw_uv_vis_inset(figure, frame, preparation)
        if spec.plot_kind in {"diagnostic_curve", "calibration_curve"}:
            axis.set_aspect("equal", adjustable="box")
        _add_legend(axis, right_axis, preparation)
    _apply_font_contract(figure)
    return figure


def render_scientific_preview_png(preparation: ScientificPreparation) -> bytes:
    figure = _build_scientific_preview_figure(preparation)
    figure.set_dpi(150)
    buffer = io.BytesIO()
    FigureCanvasAgg(figure).print_png(buffer)
    return buffer.getvalue()


__all__ = [
    "NATURE_PALETTE",
    "ORIGIN_PIE_PALETTE",
    "PREVIEW_WIDTH_IN",
    "ScientificPreviewError",
    "_build_scientific_preview_figure",
    "render_scientific_preview_png",
]
