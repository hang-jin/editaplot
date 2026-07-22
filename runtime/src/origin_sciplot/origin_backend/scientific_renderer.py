"""Shared editable Origin renderer for generic scientific table templates."""

from __future__ import annotations

import math
import re
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_workflow import (
    ScientificPreparation,
    log_decade_increment,
    prepare_scientific,
    series_values,
)
from origin_sciplot.scientific_visual import AdaptiveOriginStyle, palette_colors
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import FIXED_ORIGIN_STYLE, page_size_inches, pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .session import OriginSession
from .verify_utils import (
    require_nonempty,
    verify_page_and_layer,
    verify_plot_line_widths,
    verify_symbol_style,
    verify_text_fonts,
    verify_text_sizes,
)


GENERAL_LAYER_LEFT_PERCENT = 23.0
GENERAL_LAYER_WIDTH_PERCENT = 76.01
DUAL_Y_LAYER_LEFT_PERCENT = 18.0
DUAL_Y_LAYER_WIDTH_PERCENT = 64.0
ERROR_BAR_WIDTH_PT = 3.0
BAR_BORDER_WIDTH_PT = 3.0
BAR_FILL_TRANSPARENCY_PERCENT = 12.0
MARKER_EDGE_PERCENT = 50.0
XRD_STACK_OFFSET = 1.15

NATURE_COLORS = palette_colors("comparison_family")

_ORIGIN_AXIS_FORMAT_SOURCE = r'''#include <Origin.h>
#pragma labtalk(2)
void CleanScientificXAxisLabels()
{
    GraphLayer gl = Project.ActiveLayer();
    if (!gl) return;
    Axis axis_x = gl.XAxis;
    Tree format_tree;
    format_tree.Root.Labels.BottomLabels.ShowMinor.nVal = 0;
    format_tree.Root.Labels.BottomLabels.Table.nVal = 0;
    format_tree.Root.Specials.BottomSpecials.SpecialCount.nVal = 0;
    format_tree.Root.Specials.TopSpecials.SpecialCount.nVal = 0;
    if (axis_x.UpdateThemeIDs(format_tree.Root) == 0)
        axis_x.ApplyFormat(format_tree, true, true, true);
    Page page = gl.GetPage();
    page.Refresh();
}
'''


@dataclass(frozen=True)
class OriginSeriesPlan:
    source_column: str
    plot_column: str
    x_column: str | None
    error_column: str | None
    label: str
    axis: str
    plot_type: str
    color: str
    bar_gap_percent: float | None
    marker_size_pt: float
    is_reference: bool = False
    line_style: int = 0
    transparency_percent: float = 0.0


@dataclass(frozen=True)
class OriginTablePlan:
    frame: pd.DataFrame
    x_column: str | None
    category_column: str | None
    series: tuple[OriginSeriesPlan, ...]
    helper_columns: tuple[str, ...]


def _figure_style(preparation: ScientificPreparation) -> AdaptiveOriginStyle:
    style = preparation.plot_spec.display_plan.figure_style
    if style is None:  # Compatibility with plans created before adaptive profiles existed.
        return AdaptiveOriginStyle(
            profile_name="legacy-general",
            page_width_cm=FIXED_ORIGIN_STYLE.page_width_cm,
            page_height_cm=FIXED_ORIGIN_STYLE.page_height_cm,
            layer_left_percent=GENERAL_LAYER_LEFT_PERCENT,
            layer_top_percent=FIXED_ORIGIN_STYLE.layer_top_percent,
            layer_width_percent=GENERAL_LAYER_WIDTH_PERCENT,
            layer_height_percent=FIXED_ORIGIN_STYLE.layer_height_percent,
            axis_title_size_pt=FIXED_ORIGIN_STYLE.axis_title_size_pt,
            tick_label_size_pt=FIXED_ORIGIN_STYLE.tick_label_size_pt,
            legend_size_pt=FIXED_ORIGIN_STYLE.legend_size_pt,
            plot_line_width_pt=FIXED_ORIGIN_STYLE.plot_line_width_pt,
            frame_line_width_pt=FIXED_ORIGIN_STYLE.frame_line_width_pt,
            major_tick_length_pt=FIXED_ORIGIN_STYLE.major_tick_length_pt,
            minor_tick_length_pt=FIXED_ORIGIN_STYLE.minor_tick_length_pt,
            bar_border_width_pt=BAR_BORDER_WIDTH_PT,
            error_bar_width_pt=ERROR_BAR_WIDTH_PT,
            fill_transparency_percent=BAR_FILL_TRANSPARENCY_PERCENT,
        )
    return style


def _safe_helper_name(source: str, suffix: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_") or "Series"
    candidate = f"__{suffix}_{base}"
    index = 2
    while candidate in used:
        candidate = f"__{suffix}_{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def _origin_plot_type(plot_kind: str) -> str:
    if plot_kind == "bar_error":
        return "c"
    if plot_kind in {"scatter", "bland_altman"}:
        return "s"
    if plot_kind in {"line_error", "nyquist", "paired_trajectory", "calibration_curve"}:
        return "y"
    if plot_kind in {"pl_spectrum", "uv_vis"}:
        return "y"
    return "l"


def _prepare_origin_table(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> OriginTablePlan:
    """Add only documented display helpers to a deep copy of the source frame."""
    origin_frame = frame.copy(deep=True)
    used = {str(column) for column in origin_frame.columns}
    helpers: list[str] = []
    series_plans: list[OriginSeriesPlan] = []
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    colors = palette_colors(style.palette_name)
    is_bar = spec.plot_kind == "bar_error"
    series_count = len(spec.series)
    bar_spacing = spec.display_plan.bar_group_span / series_count if is_bar else 0.0
    bar_gap_percent = (
        round(100.0 - spec.display_plan.bar_inner_width / series_count * 100.0, 6)
        if is_bar
        else None
    )
    assignment_roles = dict(preparation.assignments)
    observed_color_index = {
        series.source_column: index
        for index, series in enumerate(spec.series)
        if series.series_role != "fit"
    }
    for index, series in enumerate(spec.series):
        plot_column = series.source_column
        x_column: str | None = None
        values = series_values(frame, series)
        if series.transform != "identity":
            plot_column = _safe_helper_name(series.source_column, "Plot", used)
            origin_frame[plot_column] = values
            helpers.append(plot_column)
        elif spec.display_transform == "normalize_max_and_offset":
            finite = values[np.isfinite(values)]
            scale = float(np.max(np.abs(finite))) if finite.size else 1.0
            if math.isclose(scale, 0.0):
                scale = 1.0
            plot_column = _safe_helper_name(series.source_column, "Display", used)
            origin_frame[plot_column] = values / scale + index * XRD_STACK_OFFSET
            helpers.append(plot_column)
        if is_bar:
            x_column = _safe_helper_name(series.source_column, "BarX", used)
            offset = (index - (series_count - 1) / 2.0) * bar_spacing
            origin_frame[x_column] = np.arange(1, len(origin_frame) + 1, dtype=float) + offset
            helpers.append(x_column)
        color_index = (
            observed_color_index.get(series.paired_with, index)
            if series.series_role == "fit"
            else observed_color_index.get(series.source_column, index)
        )
        color = colors[color_index % len(colors)]
        line_style = 0
        if spec.plot_kind == "decision_curve":
            role = assignment_roles.get(series.source_column)
            if role == "treat_all":
                color = "#6F7478"
                line_style = 1
            elif role == "treat_none":
                color = "#A7ABAE"
                line_style = 2
        plot_type = _origin_plot_type(spec.plot_kind)
        if (
            spec.plot_kind == "line"
            and spec.display_plan.show_markers
            and series.series_role == "data"
        ):
            plot_type = "y"
        if spec.plot_kind == "pl_decay":
            plot_type = "l" if series.series_role == "fit" else "s"
        series_plans.append(
            OriginSeriesPlan(
                source_column=series.source_column,
                plot_column=plot_column,
                x_column=x_column,
                error_column=series.error_column,
                label=series.label,
                axis=series.axis,
                plot_type=plot_type,
                color=color,
                bar_gap_percent=bar_gap_percent,
                marker_size_pt=(
                    0.0 if series.series_role == "fit" else spec.display_plan.marker_size_pt
                ),
                is_reference=series.series_role == "fit",
                line_style=line_style,
                transparency_percent=(
                    style.fill_transparency_percent
                    if spec.plot_kind == "paired_trajectory"
                    else 0.0
                ),
            )
        )
    if spec.plot_kind == "calibration_curve":
        if len(spec.series) != 1 or spec.series[0].size_column is None or spec.x_column is None:
            raise OriginDrawError("Calibration plan needs one observed series and one bin-count column.")
        count_column = spec.series[0].size_column
        counts = frame[count_column].to_numpy(dtype=float, copy=True)
        finite = counts[np.isfinite(counts)]
        maximum = float(np.max(finite)) if finite.size else 0.0
        if maximum <= 0.0:
            raise OriginDrawError("Calibration bin counts need at least one positive value.")
        helper_y = _safe_helper_name("PredictionDistribution", "Display", used)
        origin_frame[helper_y] = counts / maximum * 0.12
        helpers.append(helper_y)
        series_plans.append(
            OriginSeriesPlan(
                source_column=count_column,
                plot_column=helper_y,
                x_column=spec.x_column,
                error_column=None,
                label="Prediction distribution",
                axis="left",
                plot_type="c",
                color="#A9CBE8",
                bar_gap_percent=30.0,
                marker_size_pt=0.0,
                is_reference=True,
            )
        )
    if spec.reference_geometry:
        if spec.x_column is None:
            raise OriginDrawError("A reference-line plot needs a numeric X column.")
        helper_x = _safe_helper_name("Reference", "ReferenceX", used)
        x_values = np.full(len(origin_frame), np.nan, dtype=float)
        x_values[:2] = (float(spec.axis_plan.x_from), float(spec.axis_plan.x_to))
        origin_frame[helper_x] = x_values
        helpers.append(helper_x)
        if spec.reference_geometry == "diagonal":
            helper_y = _safe_helper_name("Chance", "ReferenceY", used)
            y_values = np.full(len(origin_frame), np.nan, dtype=float)
            y_values[:2] = (float(spec.axis_plan.y_from), float(spec.axis_plan.y_to))
            origin_frame[helper_y] = y_values
            helpers.append(helper_y)
            series_plans.append(
                OriginSeriesPlan(
                    source_column=helper_y,
                    plot_column=helper_y,
                    x_column=helper_x,
                    error_column=None,
                    label=spec.reference_labels[0] if spec.reference_labels else "Reference",
                    axis="left",
                    plot_type="l",
                    color="#8A8F94",
                    bar_gap_percent=None,
                    marker_size_pt=0.0,
                    is_reference=True,
                    line_style=0,
                )
            )
        elif spec.reference_geometry == "horizontal":
            for index, value in enumerate(spec.reference_values):
                base_label = (
                    spec.reference_labels[index]
                    if index < len(spec.reference_labels)
                    else f"Reference {index + 1}"
                )
                label = (
                    f"{base_label} = {value:g}"
                    if spec.plot_kind == "bland_altman"
                    else base_label
                )
                helper_y = _safe_helper_name(base_label, "ReferenceY", used)
                y_values = np.full(len(origin_frame), np.nan, dtype=float)
                y_values[:2] = float(value)
                origin_frame[helper_y] = y_values
                helpers.append(helper_y)
                series_plans.append(
                    OriginSeriesPlan(
                        source_column=helper_y,
                        plot_column=helper_y,
                        x_column=helper_x,
                        error_column=None,
                        label=label,
                        axis="left",
                        plot_type="l",
                        color=(
                            "#B65C67"
                            if spec.plot_kind == "bland_altman" and index == 0
                            else "#8A8F94"
                        ),
                        bar_gap_percent=None,
                        marker_size_pt=0.0,
                        is_reference=True,
                        line_style=(
                            0 if spec.plot_kind == "bland_altman" and index == 0 else 1
                        ),
                    )
                )
        else:
            raise OriginDrawError(
                f"Unsupported reference geometry: {spec.reference_geometry}"
            )
    return OriginTablePlan(
        frame=origin_frame,
        x_column=spec.x_column,
        category_column=spec.category_column,
        series=tuple(series_plans),
        helper_columns=tuple(helpers),
    )


def _resolve_preparation(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation | None,
) -> ScientificPreparation:
    resolved = preparation or prepare_scientific(output.input_copy, manifest.id)
    if resolved.template_id != manifest.id:
        raise OriginDrawError(
            f"Scientific preparation template {resolved.template_id!r} does not match {manifest.id!r}."
        )
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError("Scientific preparation columns do not match the validated source copy.")
    if resolved.requires_confirmation:
        raise OriginDrawError("Column mapping confirmation is required before Origin can run.")
    return resolved


def _apply_page_layer(
    op: Any,
    graph: Any,
    layer: Any,
    *,
    dual_y: bool,
    preparation: ScientificPreparation,
) -> dict[str, float]:
    style = _figure_style(preparation)
    left = max(style.layer_left_percent, 18.0) if dual_y else style.layer_left_percent
    width = min(style.layer_width_percent, 76.0) if dual_y else style.layer_width_percent
    width_in, height_in = page_size_inches(style)
    graph.activate()
    if not graph.obj.LT_execute(
        "page.updatetoprinter=0;page.kar=0;"
        f"page.width=({width_in:g})*page.resx;"
        f"page.height=({height_in:g})*page.resy;doc -uw;"
    ):
        raise OriginDrawError("Origin could not set the adaptive physical page size.")
    layer.set_int("unit", 1)
    layer.set_float("left", left)
    layer.set_float("top", style.layer_top_percent)
    layer.set_float("width", width)
    layer.set_float("height", style.layer_height_percent)
    layer.set_int("fixed", style.layer_fixed)
    layer.set_float("factor", style.layer_factor)
    op.set_show(True)
    return verify_page_and_layer(
        graph,
        layer,
        style=style,
        expected_layer={"left_percent": left, "width_percent": width},
    )


def _style_label(label: Any, size_pt: float, *, bold: bool = True) -> None:
    if label is None:
        return
    label.set_int("show", 1)
    label.set_float("fsize", size_pt)
    label.set_int("bold", int(bold))
    label.set_int("color", 1)


def _origin_font_code(op: Any, font_family: str) -> int:
    return int(round(float(op.lt_float(f"font({font_family})"))))


def _apply_axis_label_font(
    op: Any,
    layer: Any,
    axis_names: tuple[str, ...],
    style: AdaptiveOriginStyle,
) -> int:
    """Apply the physical font contract after any axis-label rebinding."""
    font_code = _origin_font_code(op, style.font_family)
    for axis_name in axis_names:
        layer.set_int(f"{axis_name}.label.font", font_code)
        layer.set_float(f"{axis_name}.label.pt", style.tick_label_size_pt)
        layer.set_int(f"{axis_name}.label.color", 1)
    return font_code


def _style_axis(
    layer: Any,
    axis_name: str,
    *,
    visible: bool,
    numeric_labels: bool,
    minor_ticks: int,
    style: AdaptiveOriginStyle,
    font_code: int | None = None,
) -> None:
    show = 1 if visible else 0
    layer.set_int(f"{axis_name}.showGrids", 0)
    if axis_name in {"x", "y"}:
        # Origin's Line template can inherit only the opposite axis line.
        # The documented value 3 keeps both bottom/top or left/right frame lines.
        layer.set_int(f"{axis_name}.showAxes", 3)
        layer.set_int(f"{axis_name}.atZero", 0)
    layer.set_int(f"{axis_name}.ticks", 5 if visible else 0)
    if axis_name not in {"x2", "y2"} or visible:
        layer.set_int(f"{axis_name}.showLabels", show)
    layer.set_int(f"{axis_name}.showlabel", show)
    layer.set_int(f"{axis_name}.label.show", show)
    if visible:
        if numeric_labels:
            layer.set_int(f"{axis_name}.label.type", 1)
            layer.set_int(f"{axis_name}.label.numFormat", 1)
        layer.set_int(f"{axis_name}.label.align", 1)
    layer.set_int(f"{axis_name}.minorTicks", minor_ticks if visible else 0)
    layer.set_float(f"{axis_name}.thickness", style.frame_line_width_pt)
    layer.set_float(f"{axis_name}.tickthickness", style.frame_line_width_pt)
    layer.set_float(f"{axis_name}.mtickthickness", 1.2)
    layer.set_float(f"{axis_name}.ticklength", style.major_tick_length_pt)
    layer.set_float(f"{axis_name}.mticklength", style.minor_tick_length_pt)
    layer.set_float(f"{axis_name}.label.pt", style.tick_label_size_pt)
    if font_code is not None:
        layer.set_int(f"{axis_name}.label.font", font_code)
    layer.obj.LT_execute(
        f"layer.{axis_name}.label.font=font({style.font_family});"
        f"layer.{axis_name}.label.color=color(black);"
        f"layer.{axis_name}.label.pt={style.tick_label_size_pt};"
    )


def _style_axes(op: Any, layer: Any, preparation: ScientificPreparation) -> None:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    categorical = spec.category_column is not None
    dual_y = spec.y2_title is not None
    font_code = _origin_font_code(op, style.font_family)
    x_minor = (
        0
        if categorical
        else 8
        if spec.x_scale == "log10"
        else 4
        if preparation.template_id == "xrd"
        else 1
    )
    _style_axis(
        layer,
        "x",
        visible=True,
        numeric_labels=not categorical,
        minor_ticks=x_minor,
        style=style,
        font_code=font_code,
    )
    _style_axis(
        layer,
        "x2",
        visible=False,
        numeric_labels=True,
        minor_ticks=0,
        style=style,
        font_code=font_code,
    )
    _style_axis(
        layer,
        "y",
        visible=True,
        numeric_labels=True,
        minor_ticks=1,
        style=style,
        font_code=font_code,
    )
    _style_axis(
        layer,
        "y2",
        visible=dual_y,
        numeric_labels=True,
        minor_ticks=1,
        style=style,
        font_code=font_code,
    )

    # Restore the visible axes last.  Origin 10.15 shares some paired-axis
    # properties, so hidden x2/y2 settings must never be the final writes.
    layer.set_int("x.showLabels", 1)
    layer.set_int("x.showlabel", 1)
    layer.set_int("x.label.show", 1)
    layer.set_int("y.showLabels", 1)
    layer.set_int("y.showlabel", 1)
    layer.set_int("y.label.show", 1)
    if dual_y:
        layer.set_int("y.IndivScale", 1)
        # showLabels is a shared axis-pair bit value: 3 means left and right.
        layer.set_int("y.showLabels", 3)
        layer.set_int("y2.showlabel", 1)
        layer.set_int("y2.label.show", 1)
    _apply_axis_label_font(
        op,
        layer,
        ("x", "y", "y2") if dual_y else ("x", "y"),
        style,
    )


def _set_axis_titles(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
) -> dict[str, Any]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    layer.axis("x").title = spec.x_title
    layer.axis("y").title = spec.y_title
    layer.axis("x2").title = ""
    layer.axis("y2").title = spec.y2_title or ""
    labels = {
        "x_title": layer.label("xb"),
        "y_title": layer.label("yl"),
    }
    if spec.y2_title:
        labels["y2_title"] = layer.label("yr")
    for name, label in labels.items():
        _style_label(label, style.axis_title_size_pt)
        if label is not None:
            label.set_int("font", _origin_font_code(op, style.font_family))
            text = {
                "x_title": spec.x_title,
                "y_title": spec.y_title,
                "y2_title": spec.y2_title or "",
            }[name]
            label.text = rf"\b({text})"
    layer.obj.LT_execute(
        f"xb.font=font({style.font_family});xb.bold=1;xb.color=color(black);"
        f"xb.fsize={style.axis_title_size_pt};"
        f"yl.font=font({style.font_family});yl.bold=1;yl.color=color(black);"
        f"yl.fsize={style.axis_title_size_pt};"
    )
    if spec.y2_title:
        layer.obj.LT_execute(
            f"yr.font=font({style.font_family});yr.bold=1;yr.color=color(black);"
            f"yr.fsize={style.axis_title_size_pt};"
        )
    return labels


def _position_x_title(
    op: Any,
    label: Any,
    style: AdaptiveOriginStyle | None = None,
) -> None:
    if label is None:
        return
    resolved = style or AdaptiveOriginStyle(
        profile_name="legacy-title",
        page_width_cm=FIXED_ORIGIN_STYLE.page_width_cm,
        page_height_cm=FIXED_ORIGIN_STYLE.page_height_cm,
        layer_left_percent=FIXED_ORIGIN_STYLE.layer_left_percent,
        layer_top_percent=FIXED_ORIGIN_STYLE.layer_top_percent,
        layer_width_percent=FIXED_ORIGIN_STYLE.layer_width_percent,
        layer_height_percent=FIXED_ORIGIN_STYLE.layer_height_percent,
        x_title_upshift_page_percent=FIXED_ORIGIN_STYLE.x_title_upshift_page_percent,
    )
    page_height = float(op.lt_float("page.height"))
    label.set_float(
        "top",
        label.get_float("top")
        - page_height * resolved.x_title_upshift_page_percent / 100.0,
    )


def _position_rotated_category_title(op: Any, label: Any) -> None:
    """Place the X title below 45-degree category tick labels."""
    if label is None:
        raise OriginDrawError("Origin category-axis title is missing.")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    layer_center = page_width * 0.61005
    label.set_float("left", layer_center - label.get_float("width") / 2.0)
    label.set_float("top", page_height * 0.90)
    op.lt_exec("doc -uw;")


def _title_geometry(op: Any, labels: dict[str, Any]) -> dict[str, float]:
    state: dict[str, float] = {
        "page.width": float(op.lt_float("page.width")),
        "page.height": float(op.lt_float("page.height")),
    }
    for name, label in labels.items():
        if label is None:
            raise OriginDrawError(f"Origin axis title object is missing: {name}")
        for prop in ("left", "top", "width", "height"):
            state[f"{name}.{prop}"] = float(label.get_float(prop))
    for name in labels:
        left = state[f"{name}.left"]
        top = state[f"{name}.top"]
        right = left + state[f"{name}.width"]
        bottom = top + state[f"{name}.height"]
        if left < 0 or top < 0 or right > state["page.width"] or bottom > state["page.height"]:
            raise OriginDrawError(
                f"Origin {name.replace('_', ' ')} is clipped: "
                f"left={left:g}, top={top:g}, right={right:g}, bottom={bottom:g}"
            )
    return state


def _add_plot(
    layer: Any,
    worksheet: Any,
    series: OriginSeriesPlan,
    x_column: str,
    style: AdaptiveOriginStyle,
) -> tuple[Any, list[Any]]:
    before = {plot.lt_range() for plot in layer.plot_list()}
    plot = layer.add_plot(
        worksheet,
        series.plot_column,
        x_column,
        type=series.plot_type,
        colyerr=series.error_column if series.error_column else -1,
    )
    if plot is None:
        raise OriginDrawError(f"Origin could not add plot: {series.source_column}")
    plot.color = series.color
    if series.plot_type == "c":
        plot.set_cmd(f"-w {pt_to_origin_width_units(style.bar_border_width_pt)}")
        if series.bar_gap_percent is not None:
            # Official LabTalk set option: -vg sets the column/bar gap percentage.
            plot.set_cmd(f"-vg {series.bar_gap_percent:g}")
    else:
        plot.set_cmd(f"-w {pt_to_origin_width_units(style.plot_line_width_pt)}")
        if series.plot_type in {"l", "y"}:
            plot.set_cmd(f"-d {series.line_style}")
    if series.plot_type in {"s", "y"}:
        plot.symbol_kind = 2
        plot.symbol_interior = 2
        plot.symbol_size = series.marker_size_pt
        plot.set_cmd(f"-kh {MARKER_EDGE_PERCENT:g}")
    if series.axis == "right":
        # Official LabTalk set command: -ay assigns a data plot to Y axis 2.
        plot.set_cmd("-ay 2")
    if series.transparency_percent:
        plot.transparency = series.transparency_percent

    additions = [item for item in layer.plot_list() if item.lt_range() not in before]
    error_plots = [item for item in additions if item.lt_range() != plot.lt_range()]
    for error_plot in error_plots:
        error_plot.color = series.color
        error_plot.set_cmd(f"-w {pt_to_origin_width_units(style.error_bar_width_pt)}")
    return plot, error_plots


def _set_bar_transparency(
    layer: Any,
    table: OriginTablePlan,
    main_plots: dict[str, Any],
    style: AdaptiveOriginStyle,
) -> dict[str, float]:
    """Set and read back the documented ``layer.plotn.transparency`` property."""
    plot_indices = {
        plot.lt_range(): index for index, plot in enumerate(layer.plot_list(), start=1)
    }
    state: dict[str, float] = {}
    for series in table.series:
        if series.plot_type != "c":
            continue
        plot = main_plots[series.label]
        index = plot_indices.get(plot.lt_range())
        if index is None:
            raise OriginDrawError(f"Origin bar plot index is missing: {series.label}")
        key = f"plot{index}.transparency"
        layer.set_float(key, style.fill_transparency_percent)
        value = float(layer.get_float(key))
        if not math.isfinite(value) or abs(value - style.fill_transparency_percent) > 0.05:
            raise OriginDrawError(
                f"Origin bar transparency is {value:g}%, expected "
                f"{style.fill_transparency_percent:g}%: {series.label}"
            )
        state[series.label] = value
    return state


def _apply_axis_limits(
    layer: Any,
    frame: pd.DataFrame,
    table: OriginTablePlan,
    preparation: ScientificPreparation,
) -> None:
    spec = preparation.plot_spec
    plan = spec.axis_plan
    if table.category_column is not None:
        layer.axis("x").scale = "linear"
        layer.axis("x").set_limits(0.5, len(table.frame) + 0.5, 1.0)
    else:
        if spec.x_scale == "log10":
            layer.axis("x").scale = "log10"
            layer.set_int("x.label.numFormat", 2)
            layer.set_int("x.label.decPlaces", 0)
            values = frame[spec.x_column].to_numpy(dtype=float)  # type: ignore[index]
            finite = values[np.isfinite(values) & (values > 0)]
            layer.axis("x").set_limits(float(np.min(finite)) * 0.90, float(np.max(finite)) * 1.10)
            layer.set_float("x.inc", log_decade_increment(finite))
        else:
            layer.axis("x").scale = "linear"
            layer.axis("x").set_limits(plan.x_from, plan.x_to, plan.x_step)

    if spec.plot_kind == "stacked_line":
        upper = max(1.05, (len(table.series) - 1) * XRD_STACK_OFFSET + 1.10)
        layer.axis("y").set_limits(-0.10, upper, 0.5)
        layer.set_int("y.ticks", 0)
        layer.set_int("y.minorTicks", 0)
        layer.set_int("y.showLabels", 0)
        layer.set_int("y.showlabel", 0)
        layer.set_int("y.label.show", 0)
    elif spec.y_scale == "log10":
        layer.axis("y").scale = "log10"
        layer.set_int("y.label.numFormat", 2)
        layer.set_int("y.label.decPlaces", 0)
        left_values = np.concatenate(
            [
                table.frame[item.plot_column].to_numpy(dtype=float)
                for item in table.series
                if item.axis == "left"
            ]
        )
        positive = left_values[np.isfinite(left_values) & (left_values > 0)]
        layer.axis("y").set_limits(float(np.min(positive)) * 0.85, float(np.max(positive)) * 1.15)
        layer.set_float("y.inc", log_decade_increment(positive))
    else:
        layer.axis("y").scale = "linear"
        layer.axis("y").set_limits(plan.y_from, plan.y_to, plan.y_step)
    if spec.y2_title and plan.y2_from is not None and plan.y2_to is not None:
        layer.axis("y2").scale = "linear"
        layer.axis("y2").set_limits(plan.y2_from, plan.y2_to, plan.y2_step)


def _bind_category_labels(layer: Any, worksheet: Any, table: OriginTablePlan) -> None:
    if table.category_column is None:
        return
    column_index = worksheet.lt_col_index(table.category_column)
    if column_index < 1:
        raise OriginDrawError("Origin category column could not be resolved.")
    dataset = f"{worksheet.lt_range(False)}!col({column_index})"
    # Official Axis command: T binds X tick labels to a worksheet dataset.
    if not layer.obj.LT_execute(
        f"range __scientific_categories={dataset};axis -ps X T __scientific_categories;"
    ):
        raise OriginDrawError("Origin could not bind category tick labels.")
    layer.set_int("x.minorTicks", 0)
    if layer.get_int("x.label.type") != 2:
        raise OriginDrawError("Origin did not keep Text from Dataset category labels.")
    if layer.get_int("x.minorTicks") != 0:
        raise OriginDrawError("Origin did not disable categorical minor ticks.")


def _clean_numeric_x_axis(op: Any, graph: Any) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".c", encoding="ascii", delete=False) as handle:
        handle.write(_ORIGIN_AXIS_FORMAT_SOURCE)
        source_path = Path(handle.name)
    try:
        graph.activate()
        op.lt_exec(f'__scientific_axis_oc_error=run.LoadOC("{source_path}", 16);')
        if op.lt_int("__scientific_axis_oc_error") != 0:
            raise OriginDrawError("Origin C scientific axis formatter did not compile")
        if not op.lt_exec("run -oc CleanScientificXAxisLabels;"):
            raise OriginDrawError("Origin C scientific axis formatter did not execute")
    finally:
        source_path.unlink(missing_ok=True)


def _legend_lines(
    entries: list[Any],
    main_plots: dict[str, Any],
    plots: list[Any],
) -> list[str]:
    plot_indices = {plot.lt_range(): index for index, plot in enumerate(plots, start=1)}
    lines: list[str] = []
    for entry in entries:
        label = re.sub(r"\s+", " ", entry.label.replace("×", "x")).strip() or "Series"
        if entry.error_column:
            match = re.search(r"(?i)(SEM|SD|SE|ERR|ERROR)$", entry.error_column)
            kind = match.group(1).upper() if match else "error"
            label = f"{label} (+/-{kind})"
        plot = main_plots.get(entry.label)
        if plot is None or plot.lt_range() not in plot_indices:
            raise OriginDrawError(f"Origin legend plot is missing: {entry.label}")
        lines.append(rf"\L({plot_indices[plot.lt_range()]}) {label}")
    return lines


def _style_legend(
    op: Any,
    layer: Any,
    entries: list[OriginSeriesPlan],
    main_plots: dict[str, Any],
    style: AdaptiveOriginStyle,
) -> Any | None:
    if not entries:
        for name in ("legend", "Legend"):
            try:
                label = layer.label(name)
                if label is not None:
                    label.remove()
            except Exception:  # noqa: BLE001 - Origin templates vary
                pass
        return None
    if len(entries) == 1 and entries[0].error_column is None:
        for name in ("legend", "Legend"):
            try:
                label = layer.label(name)
                if label is not None:
                    label.remove()
            except Exception:  # noqa: BLE001 - Origin templates vary
                pass
        return None
    legend = layer.label("legend")
    if legend is None:
        return None
    legend.set_int("link", 1)
    legend.text = "\n".join(_legend_lines(entries, main_plots, layer.plot_list()))
    _style_label(legend, style.legend_size_pt, bold=False)
    layer.obj.LT_execute(
        f"legend.font=font({style.font_family});"
        "legend.color=color(black);legend.bold=0;"
    )
    legend.set_int("font", _origin_font_code(op, style.font_family))
    return legend


def _add_bland_altman_labels(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
) -> dict[str, Any]:
    spec = preparation.plot_spec
    if spec.plot_kind != "bland_altman":
        return {}
    style = _figure_style(preparation)
    x_span = float(spec.axis_plan.x_to - spec.axis_plan.x_from)
    y_span = float(spec.axis_plan.y_to - spec.axis_plan.y_from)
    x = float(spec.axis_plan.x_from + x_span * 0.68)
    direct_label_size_pt = float(round(style.legend_size_pt * 0.88))
    labels: dict[str, Any] = {}
    for index, value in enumerate(spec.reference_values):
        base = spec.reference_labels[index] if index < len(spec.reference_labels) else "Reference"
        canonical = re.sub(r"\s+", "", base).casefold()
        if "upper" in canonical:
            y_offset = -0.070
        else:
            y_offset = 0.045
        y = float(value + y_span * y_offset)
        label = layer.add_label(f"{base}  {value:+.2f}", x, y)
        if label is None:
            raise OriginDrawError("Origin could not add Bland-Altman direct labels.")
        _style_label(label, direct_label_size_pt, bold=False)
        label.color = op.ocolor("#A54855" if "bias" in canonical else "#374151")
        labels[f"bland_label_{index + 1}"] = label
    if not op.lt_exec(
        f"doc -e G {{%B.font=font({style.font_family});}};doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the Bland-Altman direct-label font.")
    return labels


def _read_axis_state(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
) -> dict[str, float | int]:
    state: dict[str, float | int] = {}
    for axis_name in ("x", "y", "y2"):
        for prop in (
            "from",
            "to",
            "inc",
            "type",
            "showAxes",
            "ticks",
            "minorTicks",
            "showLabels",
            "showlabel",
            "label.show",
            "label.table",
            "label.type",
            "label.pt",
            "label.font",
            "thickness",
            "tickthickness",
            "atZero",
        ):
            key = f"{axis_name}.{prop}"
            state[key] = (
                layer.get_int(key)
                if prop
                in {
                    "type",
                    "showAxes",
                    "ticks",
                    "minorTicks",
                    "showLabels",
                    "showlabel",
                    "label.show",
                    "label.table",
                    "label.type",
                    "atZero",
                }
                else layer.get_float(key)
            )
    for key in ("x2.ticks", "x2.showlabel", "x2.label.show"):
        state[key] = layer.get_int(key)

    style = _figure_style(preparation)
    expected_font_code = _origin_font_code(op, style.font_family)
    state["font_code_expected"] = expected_font_code
    expected_y_labels = (
        0
        if preparation.plot_spec.plot_kind == "stacked_line"
        else 3
        if preparation.plot_spec.y2_title
        else 1
    )
    if int(state["x.showLabels"]) != 1 or int(state["y.showLabels"]) != expected_y_labels:
        raise OriginDrawError("Origin did not keep the expected bottom/left axis labels visible.")
    if int(state["x.atZero"]) != 0 or int(state["y.atZero"]) != 0:
        raise OriginDrawError("Origin kept an unwanted zero-axis line inside the plot.")
    if int(state["x.showAxes"]) != 3 or int(state["y.showAxes"]) != 3:
        raise OriginDrawError("Origin did not keep the complete bottom/top and left/right frame.")
    expected_x_label_type = 2 if preparation.plot_spec.category_column else 1
    if int(state["x.label.type"]) != expected_x_label_type:
        raise OriginDrawError("Origin X tick-label type does not match the plot contract.")
    if int(state["x.label.table"]) != 0:
        raise OriginDrawError("Origin kept an inherited X tick-label table.")
    expected_x_axis_type = 2 if preparation.plot_spec.x_scale == "log10" else {0, 1}
    expected_y_axis_type = 2 if preparation.plot_spec.y_scale == "log10" else {0, 1}
    x_axis_type = int(state["x.type"])
    y_axis_type = int(state["y.type"])
    if (
        x_axis_type != expected_x_axis_type
        if isinstance(expected_x_axis_type, int)
        else x_axis_type not in expected_x_axis_type
    ):
        raise OriginDrawError("Origin X scale type does not match the plot contract.")
    if (
        y_axis_type != expected_y_axis_type
        if isinstance(expected_y_axis_type, int)
        else y_axis_type not in expected_y_axis_type
    ):
        raise OriginDrawError("Origin Y scale type does not match the plot contract.")
    for axis_name in ("x", "y"):
        if abs(float(state[f"{axis_name}.label.pt"]) - style.tick_label_size_pt) > 0.05:
            raise OriginDrawError(
                f"Origin {axis_name} tick labels are not {style.tick_label_size_pt:g} pt."
            )
        if abs(float(state[f"{axis_name}.thickness"]) - style.frame_line_width_pt) > 0.05:
            raise OriginDrawError(
                f"Origin {axis_name} frame is not {style.frame_line_width_pt:g} pt."
            )
        if int(round(float(state[f"{axis_name}.label.font"]))) != expected_font_code:
            raise OriginDrawError(
                f"Origin {axis_name} tick-label font does not match {style.font_family}."
            )
    if preparation.plot_spec.y2_title and int(state["y2.showLabels"]) != 3:
        raise OriginDrawError("Origin did not keep the right Y axis labels visible.")
    if preparation.plot_spec.y2_title:
        if abs(float(state["y2.label.pt"]) - style.tick_label_size_pt) > 0.05:
            raise OriginDrawError("Origin right-Y tick-label size verification failed.")
        if int(round(float(state["y2.label.font"]))) != expected_font_code:
            raise OriginDrawError("Origin right-Y tick-label font verification failed.")
    return state


def _verify_plots(
    op: Any,
    table: OriginTablePlan,
    main_plots: dict[str, Any],
    error_plots: dict[str, Any],
    bar_transparency: dict[str, float],
    style: AdaptiveOriginStyle,
) -> dict[str, Any]:
    line_styles: dict[str, float] = {}
    transparency: dict[str, float] = {}
    for index, item in enumerate(table.series, start=1):
        plot = main_plots[item.label]
        transparency[item.label] = float(plot.transparency)
        if item.plot_type in {"l", "y"}:
            variable = f"__osc_line_style_{index}"
            if not plot.layer.LT_execute(
                f"{{range __osc_style_range={plot.lt_range()};get __osc_style_range -d {variable};}}"
            ):
                raise OriginDrawError(f"Origin could not read line style for {item.label}.")
            line_styles[item.label] = float(op.lt_float(variable))
            if abs(line_styles[item.label] - item.line_style) > 0.05:
                raise OriginDrawError(
                    f"Origin line style for {item.label} is {line_styles[item.label]:g}, "
                    f"expected {item.line_style}."
                )
    line_plots = {
        item.label: main_plots[item.label]
        for item in table.series
        if item.plot_type in {"l", "y"}
    }
    scatter_plots = {
        item.label: main_plots[item.label]
        for item in table.series
        if item.plot_type in {"s", "y"}
    }
    bar_plots = {
        item.label: main_plots[item.label]
        for item in table.series
        if item.plot_type == "c"
    }
    try:
        state: dict[str, Any] = {
            "line_widths": (
                verify_plot_line_widths(op, line_plots, style.plot_line_width_pt)
                if line_plots
                else {}
            ),
            "bar_border_widths": (
                verify_plot_line_widths(op, bar_plots, style.bar_border_width_pt)
                if bar_plots
                else {}
            ),
            "bar_transparency_percent": bar_transparency,
            "error_bar_widths": (
                verify_plot_line_widths(op, error_plots, style.error_bar_width_pt)
                if error_plots
                else {}
            ),
            "symbols": {
                item.label: verify_symbol_style(
                    op,
                    main_plots[item.label],
                    expected_size_pt=item.marker_size_pt,
                    expected_edge_percent=MARKER_EDGE_PERCENT,
                )
                for item in table.series
                if item.label in scatter_plots
            },
            "line_styles": line_styles,
            "transparency_percent": transparency,
        }
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return state


def _add_uv_vis_inset(
    op: Any,
    graph: Any,
    worksheet: Any,
    preparation: ScientificPreparation,
) -> dict[str, Any] | None:
    spec = preparation.plot_spec
    if spec.plot_kind != "uv_vis" or not spec.inset_series:
        return None
    if spec.inset_x_column is None or spec.inset_axis_plan is None:
        raise OriginDrawError("UV-Vis Tauc inset plan is incomplete.")
    graph.activate()
    if not op.lt_exec("layadd type:=inset;"):
        raise OriginDrawError("Origin rejected the verified inset-layer command.")
    if len(graph) != 2:
        raise OriginDrawError(f"Origin created {len(graph)} UV-Vis layers instead of two.")
    inset = graph[1]
    inset.set_int("unit", 1)
    inset.set_float("left", 56.0)
    inset.set_float("top", 9.0)
    inset.set_float("width", 36.0)
    inset.set_float("height", 43.0)
    style = _figure_style(preparation)
    inset_style = replace(
        style,
        axis_title_size_pt=style.inset_axis_title_size_pt,
        tick_label_size_pt=style.inset_tick_label_size_pt,
        frame_line_width_pt=style.inset_frame_line_width_pt,
        plot_line_width_pt=max(1.5, style.plot_line_width_pt * 0.78),
        major_tick_length_pt=max(3.6, style.major_tick_length_pt * 0.72),
        minor_tick_length_pt=max(2.0, style.minor_tick_length_pt * 0.70),
    )
    colors = palette_colors(style.palette_name)
    plots: list[dict[str, Any]] = []
    for index, series in enumerate(spec.inset_series, start=1):
        plot_type = "l" if series.series_role == "fit" else "y"
        plot = inset.add_plot(
            worksheet,
            series.source_column,
            spec.inset_x_column,
            type=plot_type,
        )
        if plot is None:
            raise OriginDrawError("Origin could not add all Tauc inset plots.")
        color = "#27343D" if series.series_role == "fit" else colors[2 % len(colors)]
        plot.color = color
        plot.set_cmd(
            f"-c color({color})",
            f"-w {pt_to_origin_width_units(inset_style.plot_line_width_pt)}",
            "-d 0",
        )
        if plot_type == "y":
            plot.symbol_kind = 2
            plot.symbol_interior = 2
            plot.symbol_size = 3.8
            plot.set_cmd("-kh 45")
        plots.append(
            {
                "source_column": series.source_column,
                "series_role": series.series_role,
                "plot_range": plot.lt_range(),
                "color": color,
                "plot_type": plot_type,
            }
        )
    inset.rescale()
    _style_axis(
        inset,
        "x",
        visible=True,
        numeric_labels=True,
        minor_ticks=1,
        style=inset_style,
        font_code=_origin_font_code(op, inset_style.font_family),
    )
    _style_axis(
        inset,
        "x2",
        visible=False,
        numeric_labels=True,
        minor_ticks=0,
        style=inset_style,
        font_code=_origin_font_code(op, inset_style.font_family),
    )
    _style_axis(
        inset,
        "y",
        visible=True,
        numeric_labels=True,
        minor_ticks=1,
        style=inset_style,
        font_code=_origin_font_code(op, inset_style.font_family),
    )
    _style_axis(
        inset,
        "y2",
        visible=False,
        numeric_labels=True,
        minor_ticks=0,
        style=inset_style,
        font_code=_origin_font_code(op, inset_style.font_family),
    )
    inset.set_int("x.showLabels", 1)
    inset.set_int("y.showLabels", 1)
    _apply_axis_label_font(op, inset, ("x", "y"), inset_style)
    plan = spec.inset_axis_plan
    inset.axis("x").set_limits(plan.x_from, plan.x_to, plan.x_step)
    inset.axis("y").set_limits(plan.y_from, plan.y_to, plan.y_step)
    inset.axis("x").title = spec.inset_x_title or ""
    inset.axis("y").title = spec.inset_y_title or ""
    x_title = inset.label("xb")
    y_title = inset.label("yl")
    if x_title is None or y_title is None:
        raise OriginDrawError("Origin Tauc inset axis-title objects are missing.")
    x_title.text = rf"\b({spec.inset_x_title or ''})"
    y_title.text = rf"\b({spec.inset_y_title or ''})"
    _style_label(x_title, inset_style.axis_title_size_pt)
    _style_label(y_title, inset_style.axis_title_size_pt)
    inset_font_code = _origin_font_code(op, inset_style.font_family)
    x_title.set_int("font", inset_font_code)
    y_title.set_int("font", inset_font_code)
    inset.obj.LT_execute(
        f"xb.font=font({inset_style.font_family});xb.bold=1;xb.fsize={inset_style.axis_title_size_pt};"
        f"yl.font=font({inset_style.font_family});yl.bold=1;yl.fsize={inset_style.axis_title_size_pt};"
    )
    for name in ("Legend", "legend"):
        try:
            label = inset.label(name)
            if label is not None:
                label.remove()
        except Exception:  # noqa: BLE001 - Origin templates vary
            pass
    annotation = None
    if spec.inset_annotation:
        x_span = float(plan.x_to - plan.x_from)
        y_span = float(plan.y_to - plan.y_from)
        annotation = inset.add_label(
            spec.inset_annotation,
            float(plan.x_from + x_span * 0.07),
            float(plan.y_from + y_span * 0.10),
        )
        if annotation is None:
            raise OriginDrawError("Origin could not add the user-provided band-gap annotation.")
        _style_label(annotation, inset_style.tick_label_size_pt, bold=True)
        annotation.set_int("font", _origin_font_code(op, inset_style.font_family))
        annotation.color = op.ocolor("#27343D")
    inset.activate()
    op.lt_exec("doc -uw;")
    geometry = {
        key: float(inset.get_float(key)) for key in ("left", "top", "width", "height")
    }
    if geometry["left"] + geometry["width"] > 100.05 or geometry["top"] + geometry["height"] > 100.05:
        raise OriginDrawError("Origin Tauc inset extends beyond the page.")
    axis_state = {
        key: float(inset.get_float(key))
        for key in (
            "x.from",
            "x.to",
            "x.inc",
            "x.label.pt",
            "x.label.font",
            "x.thickness",
            "y.from",
            "y.to",
            "y.inc",
            "y.label.pt",
            "y.label.font",
            "y.thickness",
        )
    }
    for axis_name in ("x", "y"):
        if abs(axis_state[f"{axis_name}.label.pt"] - inset_style.tick_label_size_pt) > 0.05:
            raise OriginDrawError("Origin Tauc inset tick-label size verification failed.")
        if int(round(axis_state[f"{axis_name}.label.font"])) != _origin_font_code(
            op, inset_style.font_family
        ):
            raise OriginDrawError("Origin Tauc inset tick-label font verification failed.")
    text_state = {
        "x_title_pt": float(x_title.get_float("fsize")),
        "y_title_pt": float(y_title.get_float("fsize")),
        "annotation_pt": float(annotation.get_float("fsize")) if annotation is not None else None,
    }
    if any(
        abs(float(text_state[key]) - inset_style.axis_title_size_pt) > 0.05
        for key in ("x_title_pt", "y_title_pt")
    ):
        raise OriginDrawError("Origin Tauc inset title-size verification failed.")
    inset_labels = {"x_title": x_title, "y_title": y_title}
    if annotation is not None:
        inset_labels["annotation"] = annotation
    try:
        text_state.update(verify_text_fonts(op, inset_labels, inset_style.font_family))
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return {
        "command": "layadd type:=inset;",
        "layer_count": len(graph),
        "geometry_percent": geometry,
        "axis_state": axis_state,
        "text_state": text_state,
        "plots": plots,
        "annotation_from_input": spec.inset_annotation,
        "calculation_performed": False,
    }


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    table = _prepare_origin_table(frame, preparation)
    style = _figure_style(preparation)
    worksheet = op.new_sheet("w", f"{preparation.template_id.upper()} Input")
    if worksheet is None:
        raise OriginDrawError("Origin could not create the scientific input worksheet.")
    worksheet.from_df(table.frame)
    worksheet.cols_axis()

    graph = op.new_graph(f"{preparation.template_id.upper()} Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create a graph from the Line template.")
    layer = graph[0]
    dual_y = preparation.plot_spec.y2_title is not None
    geometry = _apply_page_layer(
        op,
        graph,
        layer,
        dual_y=dual_y,
        preparation=preparation,
    )
    category_rotation = preparation.plot_spec.display_plan.category_label_rotation_deg
    if category_rotation:
        layer.set_float("height", style.layer_height_percent)
        geometry = verify_page_and_layer(
            graph,
            layer,
            style=style,
            expected_layer={
                "left_percent": style.layer_left_percent,
                "width_percent": style.layer_width_percent,
                "height_percent": style.layer_height_percent,
            },
        )

    x_column = table.category_column or table.x_column
    if x_column is None:
        raise OriginDrawError("Scientific plot plan has no X or category column.")
    main_plots: dict[str, Any] = {}
    error_plots: dict[str, Any] = {}
    for series in table.series:
        main, errors = _add_plot(
            layer,
            worksheet,
            series,
            series.x_column or x_column,
            style,
        )
        main_plots[series.label] = main
        for index, error in enumerate(errors, start=1):
            error_plots[f"{series.label} error {index}"] = error
    bar_transparency = _set_bar_transparency(layer, table, main_plots, style)

    layer.rescale()
    _style_axes(op, layer, preparation)
    _apply_axis_limits(layer, frame, table, preparation)
    title_labels = _set_axis_titles(op, layer, preparation)
    legend_entries = [item for item in table.series if not item.is_reference]
    if preparation.plot_spec.plot_kind == "paired_trajectory":
        legend_entries = []
    legend = _style_legend(op, layer, legend_entries, main_plots, style)
    graph.activate()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    _clean_numeric_x_axis(op, graph)
    _style_axes(op, layer, preparation)
    _apply_axis_limits(layer, frame, table, preparation)
    _bind_category_labels(layer, worksheet, table)
    _apply_axis_label_font(
        op,
        layer,
        ("x", "y", "y2") if preparation.plot_spec.y2_title else ("x", "y"),
        style,
    )
    if category_rotation:
        # Official LabTalk Layer.Axis.Label.rotate property.  Apply it after
        # dataset-backed category labels are bound because ``axis -ps`` can
        # replace the visible label object.
        if not layer.obj.LT_execute(f"layer.x.label.rotate={category_rotation:g};"):
            raise OriginDrawError("Origin could not rotate category tick labels.")
        if abs(layer.get_float("x.label.rotate") - category_rotation) > 0.05:
            raise OriginDrawError("Origin did not keep the planned category-label rotation.")
    for label in title_labels.values():
        if label is not None:
            label.set_int("show", 1)
    op.lt_exec("doc -uw;")
    if category_rotation:
        _position_rotated_category_title(op, title_labels["x_title"])
    else:
        _position_x_title(op, title_labels["x_title"], style)
    op.lt_exec("doc -uw;")

    bland_labels = _add_bland_altman_labels(op, layer, preparation)
    title_labels.update(bland_labels)

    axis_state = _read_axis_state(op, layer, preparation)
    axis_state["x.label.rotate"] = layer.get_float("x.label.rotate")
    title_state = _title_geometry(op, title_labels)
    expected_text = {
        name: style.axis_title_size_pt for name in title_labels
    }
    for name in bland_labels:
        expected_text[name] = float(round(style.legend_size_pt * 0.88))
    if legend is not None:
        title_labels["legend"] = legend
        expected_text["legend"] = style.legend_size_pt
    try:
        text_state = verify_text_sizes(title_labels, expected_text)
        font_state = verify_text_fonts(op, title_labels, style.font_family)
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    plot_state = _verify_plots(
        op,
        table,
        main_plots,
        error_plots,
        bar_transparency,
        style,
    )
    inset_state = _add_uv_vis_inset(op, graph, worksheet, preparation)

    output.result_opju.unlink(missing_ok=True)
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save result.opju")
    require_nonempty(output.result_opju)

    report = {
        **geometry,
        "template_id": preparation.template_id,
        "plan_digest": preparation.plan_digest,
        "plot_spec": asdict(preparation.plot_spec),
        "source_sha256": preparation.source_sha256,
        "source_columns": list(preparation.source_columns),
        "origin_helper_columns": list(table.helper_columns),
        "origin_series_columns": [asdict(item) for item in table.series],
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **font_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "plot_set_w_units": pt_to_origin_width_units(
                style.plot_line_width_pt
            ),
            "frame_line_width_pt": style.frame_line_width_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_plot_state": plot_state,
        "origin_inset_state": inset_state,
        "source_data_modified": False,
    }
    return graph, report


def run_scientific_template(
    manifest: TemplateManifest,
    frame: pd.DataFrame,
    output: RunOutput,
    logger: RunLogger,
    *,
    keep_origin_open: bool = True,
    preparation: ScientificPreparation | None = None,
) -> dict[str, Any]:
    resolved = _resolve_preparation(manifest, frame, output, preparation)
    with OriginSession(keep_open=keep_origin_open) as session:
        op = session.op
        if op is None or session.environment is None:
            raise OriginDrawError("Origin session was not initialized")
        logger.write(f"Origin connected: version {session.environment.origin_version}")
        graph, verify_report = _build_origin_graph(op, frame, output, resolved)
        exports = export_graph(
            op,
            graph,
            output.result_png,
            output.result_pdf,
            output.result_tif,
        )
        verify_report["exports"] = exports
        write_json(output.origin_verify_report, verify_report)
        write_json(
            output.environment_report,
            {
                "backend": "Origin",
                "origin_version": session.environment.origin_version,
                "originpro_version": session.environment.originpro_version,
            },
        )
        logger.write("Scientific Origin graph verified and exported")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = [
    "DUAL_Y_LAYER_LEFT_PERCENT",
    "DUAL_Y_LAYER_WIDTH_PERCENT",
    "GENERAL_LAYER_LEFT_PERCENT",
    "GENERAL_LAYER_WIDTH_PERCENT",
    "OriginSeriesPlan",
    "OriginTablePlan",
    "_prepare_origin_table",
    "run_scientific_template",
]
