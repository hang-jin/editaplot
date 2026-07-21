"""Publication-informed, Origin-free PNG previews for prepared XPS data.

The adapter intentionally does not infer column roles.  It reloads the exact
source recorded by :func:`origin_sciplot.xps_workflow.prepare_xps`, verifies its
digest, and renders only the roles and axis semantics in the shared plot spec.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import AutoMinorLocator, FixedLocator, FuncFormatter, MaxNLocator, NullLocator

from origin_sciplot.origin_backend.base_style_contract import (
    FIXED_ORIGIN_STYLE,
    origin_points_to_preview_points,
    page_size_inches,
)
from origin_sciplot.xps_adaptive import XpsProfile, XpsSeries, build_axis_plan
from origin_sciplot.xps_workflow import XpsWorkflowError, load_xps_frame, xps_y_axis_title

if TYPE_CHECKING:
    from origin_sciplot.xps_workflow import XpsPreparation


# Keep vector text editable even though this adapter currently returns PNG.
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
        "font.size": 8.5,
        "axes.labelsize": 10,
        "axes.linewidth": 0.8,
        "axes.spines.right": True,
        "axes.spines.top": True,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
        "legend.frameon": False,
    }
)


RAW_COLOR = "#0F4D92"
FIXED_RAW_COLOR = "#767676"
BACKGROUND_COLOR = "#606060"
FIXED_BACKGROUND_COLOR = "#6F6887"
ENVELOPE_COLOR = "#B64342"
FIXED_ENVELOPE_COLOR = "#D62728"
FIXED_COMPONENT_COLORS = ("#4C78A8", "#59A14F", "#E7A1AE", "#E39C37")
COMPONENT_COLORS = (
    "#3E9E96",
    "#7C6CCF",
    "#C7766A",
    "#C49A2C",
    "#5B8FD6",
    "#8A5CA8",
    "#6F8E5E",
    "#767676",
)
COMPONENT_FILL_COLORS = (
    "#7BCDC4",
    "#A59ADE",
    "#D69A8D",
    "#D5B24A",
    "#8DB7E8",
    "#CAA3D5",
    "#BBD6B2",
    "#B0B0B0",
)

PREVIEW_WIDTH_IN = 7.2
PREVIEW_HEIGHT_IN = PREVIEW_WIDTH_IN * page_size_inches(FIXED_ORIGIN_STYLE)[1] / page_size_inches(
    FIXED_ORIGIN_STYLE
)[0]
PREVIEW_AXIS_TITLE_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.axis_title_size_pt, PREVIEW_WIDTH_IN
)
PREVIEW_TICK_LABEL_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.tick_label_size_pt, PREVIEW_WIDTH_IN
)
PREVIEW_LEGEND_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.legend_size_pt, PREVIEW_WIDTH_IN
)
PREVIEW_PLOT_LINE_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.plot_line_width_pt, PREVIEW_WIDTH_IN
)
PREVIEW_FRAME_LINE_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.frame_line_width_pt, PREVIEW_WIDTH_IN
)
PREVIEW_MAJOR_TICK_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.major_tick_length_pt, PREVIEW_WIDTH_IN
)
PREVIEW_MINOR_TICK_PT = origin_points_to_preview_points(
    FIXED_ORIGIN_STYLE.minor_tick_length_pt, PREVIEW_WIDTH_IN
)
PREVIEW_RAW_SYMBOL_SIZE_PT = origin_points_to_preview_points(7.0, PREVIEW_WIDTH_IN)
PREVIEW_RAW_SYMBOL_EDGE_PT = PREVIEW_RAW_SYMBOL_SIZE_PT * 0.25


class XpsPreviewError(ValueError):
    """Stable preview failure suitable for display in the desktop UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _SeriesView:
    spec: Any
    values: np.ndarray
    fill_baseline: np.ndarray | None
    component_index: int | None = None


def _read_prepared_source(preparation: XpsPreparation) -> dict[str, np.ndarray]:
    try:
        frame = load_xps_frame(preparation.source_path, preparation)
    except XpsWorkflowError as exc:
        code = "source_changed" if exc.code == "analysis_changed" else exc.code
        raise XpsPreviewError(code, str(exc)) from exc
    required = {preparation.roles.x}
    required.update(series.column for series in preparation.plot_spec.series)
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise XpsPreviewError("source_columns_changed", f"XPS preview columns are missing: {', '.join(missing)}")
    if frame.empty:
        raise XpsPreviewError("source_empty", "The XPS preview source has no data rows.")
    return {
        column: frame[column].to_numpy(dtype=float, copy=True)
        for column in required
    }


def _series_views(preparation: XpsPreparation, columns: dict[str, np.ndarray]) -> list[_SeriesView]:
    background_name = preparation.roles.background
    background = columns.get(background_name) if background_name is not None else None
    basis = preparation.plot_spec.component_basis
    views: list[_SeriesView] = []
    component_index = 0
    for spec in preparation.plot_spec.series:
        if spec.role == "residual":
            # The shared contract preserves residuals in data/OPJU, not on the
            # main counts axis.  A future residual panel can consume them.
            continue
        values = columns[spec.column]
        baseline: np.ndarray | None = None
        index: int | None = None
        if spec.role == "component":
            index = component_index
            component_index += 1
            if background is not None and basis == "relative_to_background":
                values = background + values
                baseline = background
            elif background is not None and basis == "baseline_inclusive":
                baseline = background
            # An unresolved basis remains an unfilled source curve.  Guessing
            # here would make preview and editable output scientifically differ.
        views.append(_SeriesView(spec=spec, values=values, fill_baseline=baseline, component_index=index))
    if not views:
        raise XpsPreviewError("no_main_series", "The XPS plot spec has no series for the main axis.")
    return views


def _adaptive_axis_plan(preparation: XpsPreparation, columns: dict[str, np.ndarray]) -> Any:
    """Reuse the exact dynamic-axis planner used by the editable Origin runner."""
    profile = XpsProfile(
        x_column=preparation.roles.x,
        raw_column=preparation.roles.raw,
        background_column=preparation.roles.background,
        envelope_column=preparation.roles.envelope,
        residuals_column=preparation.roles.residual,
        component_columns=preparation.roles.components,
        series=tuple(
            XpsSeries(series.column, series.label, series.role)
            for series in preparation.plot_spec.series
        ),
    )
    frame = pd.DataFrame({column: values for column, values in columns.items()})
    return build_axis_plan(frame, profile, preparation)


def _finite_values(arrays: list[np.ndarray]) -> np.ndarray:
    finite = [array[np.isfinite(array)] for array in arrays]
    nonempty = [array for array in finite if array.size]
    return np.concatenate(nonempty) if nonempty else np.asarray([], dtype=float)


def _y_limits(preparation: XpsPreparation, views: list[_SeriesView]) -> tuple[float, float]:
    preferred_roles = {"raw", "background", "envelope"}
    preferred = [view.values for view in views if view.spec.role in preferred_roles]
    values = _finite_values(preferred or [view.values for view in views])
    if values.size == 0:
        raise XpsPreviewError("no_finite_values", "The XPS plot spec has no finite intensity values.")

    if preparation.plot_spec.visual_profile == "adaptive_counts":
        positive = values[values > 0]
        if positive.size and float(np.nanmax(values)) > 0:
            values = positive
    y_min = float(np.min(values))
    y_max = float(np.max(values))
    if math.isclose(y_min, y_max):
        padding = max(abs(y_min) * 0.06, 1.0)
    else:
        padding = (y_max - y_min) * 0.06
    lower = y_min - padding
    if y_min >= 0:
        lower = max(0.0, lower)
    return lower, y_max + padding


def _axis_major_ticks(axis_plan: Any) -> list[float]:
    step = float(axis_plan.major_step_ev)
    first = float(axis_plan.first_tick_ev)
    lower = min(float(axis_plan.display_from_ev), float(axis_plan.display_to_ev))
    upper = max(float(axis_plan.display_from_ev), float(axis_plan.display_to_ev))
    if not all(math.isfinite(value) for value in (step, first, lower, upper)) or step <= 0:
        return []
    first_k = math.ceil((lower - first) / step - 1e-9)
    last_k = math.floor((upper - first) / step + 1e-9)
    return [first + k * step for k in range(first_k, last_k + 1)]


def _regular_ticks(lower: float, upper: float, step: float) -> list[float]:
    if not all(math.isfinite(value) for value in (lower, upper, step)) or step <= 0:
        return []
    low, high = sorted((lower, upper))
    first_k = math.ceil(low / step - 1e-9)
    last_k = math.floor(high / step + 1e-9)
    if last_k < first_k or last_k - first_k > 1000:
        return []
    return [k * step for k in range(first_k, last_k + 1)]


def _component_color(index: int, *, fixed: bool, fill: bool = False) -> str:
    if fixed:
        return FIXED_COMPONENT_COLORS[index % len(FIXED_COMPONENT_COLORS)]
    palette = COMPONENT_FILL_COLORS if fill else COMPONENT_COLORS
    return palette[index % len(palette)]


def _clean_label(value: object) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split()) or "Series"


def _scientific_tick_label(value: float, _position: float) -> str:
    """Match Origin's per-tick notation without a separate, clipped multiplier."""
    if not math.isfinite(value):
        return ""
    if value == 0:
        return "0"
    exponent = int(math.floor(math.log10(abs(value))))
    mantissa = value / (10**exponent)
    superscript = str(exponent).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))
    return f"{mantissa:.2f}×10{superscript}"


def _draw_single_fill(
    axis: Any,
    x: np.ndarray,
    top: np.ndarray,
    baseline: np.ndarray | float,
    color: str,
    *,
    alpha: float,
    zorder: float,
) -> None:
    """Draw one continuous color-to-transparent region, never a FillBand stack."""
    if np.isscalar(baseline):
        baseline_values = np.full_like(top, float(baseline), dtype=float)
    else:
        baseline_values = np.asarray(baseline, dtype=float)
    valid = np.isfinite(x) & np.isfinite(top) & np.isfinite(baseline_values)
    if np.count_nonzero(valid) < 2:
        return

    x_valid = np.asarray(x[valid], dtype=float)
    top_valid = np.asarray(top[valid], dtype=float)
    base_valid = np.asarray(baseline_values[valid], dtype=float)
    unique_x, inverse = np.unique(x_valid, return_inverse=True)
    if unique_x.size < 2:
        return
    counts = np.bincount(inverse)
    unique_top = np.bincount(inverse, weights=top_valid) / counts
    unique_base = np.bincount(inverse, weights=base_valid) / counts

    width = max(256, min(1200, int(unique_x.size * 3)))
    height = 256
    x_grid = np.linspace(float(unique_x[0]), float(unique_x[-1]), width)
    top_grid = np.interp(x_grid, unique_x, unique_top)
    base_grid = np.interp(x_grid, unique_x, unique_base)
    y_min = float(np.min(np.minimum(top_grid, base_grid)))
    y_max = float(np.max(np.maximum(top_grid, base_grid)))
    if math.isclose(y_min, y_max):
        return

    y_grid = np.linspace(y_min, y_max, height)[:, None]
    span = top_grid - base_grid
    with np.errstate(divide="ignore", invalid="ignore"):
        progress = (y_grid - base_grid) / span
    inside = np.isfinite(progress) & (progress >= 0.0) & (progress <= 1.0)
    fade = np.where(inside, np.clip(progress, 0.0, 1.0) ** 2.2, 0.0)
    red, green, blue, _ = mpl.colors.to_rgba(color)
    rgba = np.empty((height, width, 4), dtype=float)
    rgba[..., 0] = red
    rgba[..., 1] = green
    rgba[..., 2] = blue
    rgba[..., 3] = float(alpha) * fade
    axis.imshow(
        rgba,
        extent=(float(unique_x[0]), float(unique_x[-1]), y_min, y_max),
        origin="lower",
        interpolation="bilinear",
        aspect="auto",
        zorder=zorder,
    )


def _draw_preview_series(
    axis: Any,
    preparation: XpsPreparation,
    x: np.ndarray,
    views: list[_SeriesView],
    y_floor: float,
) -> None:
    fixed = preparation.plot_spec.visual_profile == "fixed_c1s_publication"
    background = next((view.values for view in views if view.spec.role == "background"), None)

    # Fills are deliberately subordinate and are drawn before every line.
    for view in views:
        if view.spec.role == "component" and view.fill_baseline is not None:
            assert view.component_index is not None
            _draw_single_fill(
                axis,
                x,
                view.values,
                view.fill_baseline,
                _component_color(view.component_index, fixed=fixed, fill=True),
                alpha=0.55 if fixed else 0.42,
                zorder=1.0 + view.component_index * 0.01,
            )
        elif view.spec.role == "raw" and not fixed:
            _draw_single_fill(
                axis,
                x,
                view.values,
                background if background is not None else y_floor,
                "#7884B4",
                alpha=0.20,
                zorder=0.5,
            )

    # Plot components first, then structural/reference curves so the measured
    # spectrum and total envelope remain visually dominant.
    draw_order = {"component": 0, "background": 1, "raw": 2, "envelope": 3}
    for view in sorted(views, key=lambda item: draw_order.get(item.spec.role, 4)):
        role = view.spec.role
        label = _clean_label(view.spec.label)
        if role == "component":
            assert view.component_index is not None
            axis.plot(
                x,
                view.values,
                color=_component_color(view.component_index, fixed=fixed),
                linewidth=PREVIEW_PLOT_LINE_PT,
                label=label,
                zorder=3,
            )
        elif role == "background":
            axis.plot(
                x,
                view.values,
                color=FIXED_BACKGROUND_COLOR if fixed else BACKGROUND_COLOR,
                linewidth=PREVIEW_PLOT_LINE_PT,
                label=label,
                zorder=4,
            )
        elif role == "envelope":
            axis.plot(
                x,
                view.values,
                color=FIXED_ENVELOPE_COLOR if fixed else ENVELOPE_COLOR,
                linewidth=PREVIEW_PLOT_LINE_PT,
                label=label,
                zorder=6,
            )
        elif role == "raw" and fixed:
            finite = np.flatnonzero(np.isfinite(x) & np.isfinite(view.values))
            if finite.size > 400:
                finite = finite[np.linspace(0, finite.size - 1, 400, dtype=int)]
            axis.scatter(
                x[finite],
                view.values[finite],
                s=PREVIEW_RAW_SYMBOL_SIZE_PT**2,
                marker="o",
                facecolors="none",
                edgecolors=FIXED_RAW_COLOR,
                linewidths=PREVIEW_RAW_SYMBOL_EDGE_PT,
                label=label,
                zorder=5,
            )
        elif role == "raw":
            axis.plot(
                x,
                view.values,
                color=RAW_COLOR,
                linewidth=PREVIEW_PLOT_LINE_PT,
                alpha=0.95,
                label=label,
                zorder=5,
            )


def _build_xps_preview_figure(preparation: XpsPreparation) -> Figure:
    """Build the preview figure; private seam used by non-pixel semantic tests."""
    columns = _read_prepared_source(preparation)
    x = columns[preparation.roles.x]
    views = _series_views(preparation, columns)

    fixed = preparation.plot_spec.visual_profile == "fixed_c1s_publication"
    if fixed:
        y_from, y_to = _y_limits(preparation, views)
        adaptive_axis_plan = None
    else:
        adaptive_axis_plan = _adaptive_axis_plan(preparation, columns)
        y_from, y_to = adaptive_axis_plan.y_from, adaptive_axis_plan.y_to
    figure = Figure(figsize=(PREVIEW_WIDTH_IN, PREVIEW_HEIGHT_IN), dpi=100, facecolor="white")
    FigureCanvasAgg(figure)
    axis = figure.add_subplot(1, 1, 1)
    axis.set_facecolor("white")
    _draw_preview_series(axis, preparation, x, views, y_from)

    axis_plan = preparation.plot_spec.axis
    axis.set_xlim(float(axis_plan.display_from_ev), float(axis_plan.display_to_ev))
    axis.set_ylim(y_from, y_to)
    axis.set_xlabel(
        _clean_label(axis_plan.x_title),
        fontsize=PREVIEW_AXIS_TITLE_PT,
        fontweight="bold",
        labelpad=7,
    )
    axis.set_ylabel(
        "Intensity (a.u.)" if fixed else _clean_label(xps_y_axis_title(preparation)),
        fontsize=PREVIEW_AXIS_TITLE_PT,
        fontweight="bold",
        labelpad=9,
    )
    if not fixed:
        axis.yaxis.set_label_coords(-0.245, 0.5)

    ticks = _axis_major_ticks(axis_plan)
    if ticks:
        axis.xaxis.set_major_locator(FixedLocator(ticks))
    axis.xaxis.set_minor_locator(AutoMinorLocator(2))
    axis.tick_params(
        axis="x",
        which="major",
        direction="out",
        length=PREVIEW_MAJOR_TICK_PT,
        width=PREVIEW_FRAME_LINE_PT,
        labelsize=PREVIEW_TICK_LABEL_PT,
        pad=4,
    )
    axis.tick_params(
        axis="x",
        which="minor",
        direction="out",
        length=PREVIEW_MINOR_TICK_PT,
        width=max(PREVIEW_FRAME_LINE_PT * 0.6, 0.5),
    )
    if fixed:
        axis.yaxis.set_major_locator(NullLocator())
        axis.yaxis.set_minor_locator(NullLocator())
        axis.tick_params(axis="y", which="both", left=False, labelleft=False)
    else:
        assert adaptive_axis_plan is not None
        y_ticks = _regular_ticks(y_from, y_to, adaptive_axis_plan.y_step)
        if y_ticks:
            axis.yaxis.set_major_locator(FixedLocator(y_ticks))
        else:
            axis.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
        axis.yaxis.set_minor_locator(NullLocator())
        axis.yaxis.set_major_formatter(FuncFormatter(_scientific_tick_label))
        axis.yaxis.get_offset_text().set_visible(False)
        axis.tick_params(
            axis="y",
            which="major",
            direction="out",
            length=PREVIEW_MAJOR_TICK_PT,
            width=PREVIEW_FRAME_LINE_PT,
            labelsize=PREVIEW_TICK_LABEL_PT,
            pad=4,
        )

    axis.grid(False, which="both")
    for spine in axis.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(PREVIEW_FRAME_LINE_PT)

    handles, labels = axis.get_legend_handles_labels()
    if handles:
        # Re-establish plot-spec order after using a deliberate visual z-order.
        handle_by_label = dict(zip(labels, handles))
        ordered_specs = [spec for spec in preparation.plot_spec.series if spec.role != "residual"]
        if fixed:
            fixed_order = {"raw": 0, "envelope": 1, "background": 2, "component": 3}
            ordered_specs.sort(key=lambda spec: fixed_order[spec.role])
        ordered_labels = [
            _clean_label(spec.label)
            for spec in ordered_specs
            if _clean_label(spec.label) in handle_by_label
        ]
        axis.legend(
            [handle_by_label[label] for label in ordered_labels],
            ordered_labels,
            loc="upper left",
            borderaxespad=0.65,
            frameon=False,
            handlelength=2.2,
            handletextpad=0.65,
            labelspacing=0.55,
            prop={
                "family": ["Arial", "Microsoft YaHei", "SimHei"],
                "size": PREVIEW_LEGEND_PT,
                "weight": "bold",
            },
        )
    figure.subplots_adjust(
        left=0.14 if fixed else 0.23,
        right=0.99,
        bottom=0.15,
        top=0.97,
    )
    return figure


def render_xps_preview_png(preparation: XpsPreparation) -> bytes:
    """Render a prepared XPS plot to deterministic in-memory PNG bytes.

    No Origin session is imported or started.  The input CSV is opened read-only
    and its SHA-256 digest must still match the preparation object.
    """
    figure = _build_xps_preview_figure(preparation)
    output = io.BytesIO()
    try:
        figure.savefig(
            output,
            format="png",
            dpi=160,
            facecolor="white",
            edgecolor="none",
            metadata={"Software": "EditaPlot"},
        )
        return output.getvalue()
    finally:
        figure.clear()


__all__ = ["XpsPreviewError", "render_xps_preview_png"]
