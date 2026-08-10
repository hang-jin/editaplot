"""Editable Origin renderer for evidence-first general scientific plots.

The specialized routes in this module were first exercised under
``test_outputs/origin_api_lab/nature_expansion_probe.py`` against Origin
2024b/10.15.  It uses only documented Origin plot IDs, ``plotgboxraw``,
``addline``, and Layer.Plotn properties.  The user's source table is never
written; display helpers exist only inside the OPJU workbook.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_visual import interpolate_hex_colors, palette_colors
from origin_sciplot.scientific_workflow import (
    ScientificPreparation,
    evidence_jitter_offsets,
    prepare_scientific,
    shap_beeswarm_offsets,
    shap_within_feature_color_values,
)
from origin_sciplot.shap_composite import SHAP_COMPOSITE_PROFILES, ShapCompositePlan
from origin_sciplot.shap_layout import (
    SHAP_FEATURE_VALUE_COLORS,
    SHAP_GROUP_COLORS,
    SHAP_MEAN_ABS_BAR_COLOR,
    SHAP_ZERO_LINE_COLOR,
    ShapCompositeGeometry,
    ShapCompositeRegion,
    resolve_shap_composite_geometry,
    resolve_shap_mean_axis,
)
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import page_size_inches, pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .scientific_renderer import (
    _apply_axis_label_font,
    _apply_page_layer,
    _clean_numeric_x_axis,
    _figure_style,
    _origin_font_code,
    _position_x_title,
    _set_axis_titles,
    _set_borderless_legend,
    _style_axis,
    _style_label,
    _title_geometry,
)
from .session import OriginSession
from .verify_utils import (
    LAYER_GEOMETRY_TOLERANCE_PERCENT,
    require_nonempty,
    verify_page_and_layer,
    verify_plot_color,
    verify_plot_line_widths,
    verify_symbol_style,
    verify_text_fonts,
    verify_text_sizes,
)

_SUPPORTED_KINDS = frozenset(
    {
        "raw_summary",
        "violin",
        "raincloud",
        "histogram",
        "forest",
        "bubble",
        "shap_summary",
        "grouped_box",
    }
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
            f"Evidence preparation {resolved.template_id!r} does not match {manifest.id!r}."
        )
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError("Evidence preparation columns do not match the validated source copy.")
    if resolved.requires_confirmation:
        raise OriginDrawError("Column mapping confirmation is required before Origin can run.")
    if resolved.plot_spec.plot_kind not in _SUPPORTED_KINDS:
        raise OriginDrawError(f"Unsupported evidence plot kind: {resolved.plot_spec.plot_kind}")
    return resolved


def _source_sheet(op: Any, frame: pd.DataFrame, preparation: ScientificPreparation) -> Any:
    sheet = op.new_sheet("w", f"{preparation.template_id.upper()} Source")
    if sheet is None:
        raise OriginDrawError("Origin could not create the evidence source worksheet.")
    sheet.from_df(frame.copy(deep=True))
    sheet.cols_axis()
    return sheet


def _remove_label(layer: Any, name: str) -> None:
    with suppress(Exception):
        label = layer.label(name)
        if label is not None:
            label.remove()


def _style_evidence_axes(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
    *,
    x_numeric: bool,
    y_numeric: bool,
) -> None:
    style = _figure_style(preparation)
    font_code = _origin_font_code(op, style.font_family)
    _style_axis(
        layer,
        "x",
        visible=True,
        numeric_labels=x_numeric,
        minor_ticks=1 if x_numeric else 0,
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
        numeric_labels=y_numeric,
        minor_ticks=1 if y_numeric else 0,
        style=style,
        font_code=font_code,
    )
    _style_axis(
        layer,
        "y2",
        visible=False,
        numeric_labels=True,
        minor_ticks=0,
        style=style,
        font_code=font_code,
    )
    # Origin 10.15 shares paired-axis flags.  Restore visible axes last.
    for axis_name in ("x", "y"):
        layer.set_int(f"{axis_name}.showLabels", 1)
        layer.set_int(f"{axis_name}.showlabel", 1)
        layer.set_int(f"{axis_name}.label.show", 1)
    _apply_axis_label_font(op, layer, ("x", "y"), style)


def _axis_state(layer: Any) -> dict[str, float | int]:
    state: dict[str, float | int] = {}
    for axis_name in ("x", "y"):
        for prop in (
            "from",
            "to",
            "inc",
            "type",
            "showAxes",
            "ticks",
            "minorTicks",
            "showLabels",
            "label.table",
            "label.type",
            "label.pt",
            "label.font",
            "label.rotate",
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
                    "label.table",
                    "label.type",
                    "atZero",
                }
                else layer.get_float(key)
            )
    return state


def _validate_axes(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
) -> dict[str, float | int]:
    style = _figure_style(preparation)
    state = _axis_state(layer)
    expected_font_code = _origin_font_code(op, style.font_family)
    state["font_code_expected"] = expected_font_code
    for axis_name in ("x", "y"):
        if int(state[f"{axis_name}.showAxes"]) != 3:
            raise OriginDrawError(f"Origin {axis_name.upper()} frame is incomplete.")
        if int(state[f"{axis_name}.showLabels"]) != 1:
            raise OriginDrawError(f"Origin {axis_name.upper()} labels are hidden.")
        if int(state[f"{axis_name}.atZero"]) != 0:
            raise OriginDrawError(f"Origin kept an unwanted {axis_name.upper()} zero axis.")
        if int(state[f"{axis_name}.label.table"]) != 0:
            raise OriginDrawError(
                f"Origin kept an inherited {axis_name.upper()} tick-label table."
            )
        if abs(float(state[f"{axis_name}.label.pt"]) - style.tick_label_size_pt) > 0.05:
            raise OriginDrawError(
                f"Origin {axis_name.upper()} labels are not {style.tick_label_size_pt:g} pt."
            )
        if abs(float(state[f"{axis_name}.thickness"]) - style.frame_line_width_pt) > 0.05:
            raise OriginDrawError(
                f"Origin {axis_name.upper()} frame is not {style.frame_line_width_pt:g} pt."
            )
        if int(round(float(state[f"{axis_name}.label.font"]))) != expected_font_code:
            raise OriginDrawError(
                f"Origin {axis_name.upper()} tick labels are not {style.font_family}."
            )
        if abs(float(state[f"{axis_name}.label.rotate"])) > 0.05:
            raise OriginDrawError(
                f"Origin {axis_name.upper()} labels inherited an unwanted rotation."
            )
    return state


def _style_titles(
    op: Any,
    graph: Any,
    layer: Any,
    preparation: ScientificPreparation,
    *,
    keep_y_title: bool = True,
) -> tuple[dict[str, Any], dict[str, float], dict[str, Any]]:
    style = _figure_style(preparation)
    labels = _set_axis_titles(op, layer, preparation)
    if not keep_y_title:
        _remove_label(layer, "yl")
        labels.pop("y_title", None)
    font_code = _origin_font_code(op, style.font_family)
    for label in labels.values():
        if label is not None:
            label.set_int("font", font_code)
    graph.activate()
    op.lt_exec("doc -uw;")
    _position_x_title(op, labels.get("x_title"), style)
    op.lt_exec("doc -uw;")
    geometry = _title_geometry(op, labels)
    try:
        sizes = verify_text_sizes(
            labels,
            {name: style.axis_title_size_pt for name in labels},
        )
        sizes.update(verify_text_fonts(op, labels, style.font_family))
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return labels, geometry, sizes


def _style_plot_family(
    op: Any,
    layer: Any,
    preparation: ScientificPreparation,
    *,
    transparency: float | None = None,
) -> list[dict[str, Any]]:
    style = _figure_style(preparation)
    colors = palette_colors(style.palette_name)
    plots = list(layer.plot_list())
    state: list[dict[str, Any]] = []
    for index, plot in enumerate(plots, start=1):
        color = colors[(index - 1) % len(colors)]
        plot.color = op.ocolor(color)
        plot.set_cmd(f"-c color({color})")
        alpha = style.fill_transparency_percent if transparency is None else transparency
        layer.set_float(f"plot{index}.transparency", alpha)
        pid = int(layer.get_int(f"plot{index}.pid"))
        try:
            color_state = verify_plot_color(
                op,
                plot,
                color,
                variable_name=f"__osc_evidence_color_{index}",
            )
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
        state.append(
            {
                "index": index,
                "pid": pid,
                "color_hex": color,
                "color_readback": float(layer.get_float(f"plot{index}.color")),
                "effective_color": color_state,
                "transparency_percent": float(
                    layer.get_float(f"plot{index}.transparency")
                ),
            }
        )
    return state


def _raw_summary_plot_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Create editable Origin-only jitter and median helpers from raw observations."""
    series_items = preparation.plot_spec.series
    maximum = max(int(frame[item.source_column].notna().sum()) for item in series_items)
    length = max(maximum, len(series_items), 3)
    plot_frame = pd.DataFrame(index=range(length))
    plot_frame["__GroupLabel"] = pd.Series([item.label for item in series_items])
    helpers: list[str] = ["__GroupLabel"]
    for index, series in enumerate(series_items, start=1):
        values = frame[series.source_column].dropna().to_numpy(dtype=float)
        offsets = evidence_jitter_offsets(values.size, index - 1)
        raw_x = f"__RawX_{index}"
        raw_y = f"__RawY_{index}"
        median_x = f"__MedianX_{index}"
        median_y = f"__MedianY_{index}"
        plot_frame[raw_x] = pd.Series(np.full(values.size, float(index)) + offsets)
        plot_frame[raw_y] = pd.Series(values)
        plot_frame[median_x] = pd.Series([index - 0.23, index + 0.23])
        plot_frame[median_y] = pd.Series([float(np.median(values))] * 2)
        helpers.extend((raw_x, raw_y, median_x, median_y))
    return plot_frame, tuple(helpers)


def _build_raw_summary_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    plot_frame, helpers = _raw_summary_plot_frame(frame, preparation)
    sheet = op.new_sheet("w", "RAW SUMMARY Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the raw-summary plot worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis()
    graph = op.new_graph("RAW SUMMARY Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the raw-summary graph.")
    layer = graph[0]
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    colors = palette_colors(style.palette_name)
    scatter_plots: dict[str, Any] = {}
    median_plots: dict[str, Any] = {}
    color_state: list[dict[str, float | str]] = []
    for index, series in enumerate(spec.series, start=1):
        scatter = layer.add_plot(sheet, f"__RawY_{index}", f"__RawX_{index}", type="s")
        median = layer.add_plot(sheet, f"__MedianY_{index}", f"__MedianX_{index}", type="l")
        if scatter is None or median is None:
            raise OriginDrawError("Origin could not create all raw-summary plot objects.")
        color = colors[(index - 1) % len(colors)]
        scatter.color = color
        scatter.set_cmd(
            f"-c color({color})",
            "-k 2",
            "-kf 0",
            f"-z {spec.display_plan.marker_size_pt:g}",
            "-kh 35",
        )
        median.color = "#39424E"
        median.set_cmd(
            "-c color(#39424E)",
            f"-w {pt_to_origin_width_units(style.plot_line_width_pt)}",
        )
        scatter_plots[series.label] = scatter
        median_plots[series.label] = median
        try:
            color_state.append(
                verify_plot_color(
                    op,
                    scatter,
                    color,
                    variable_name=f"__osc_raw_color_{index}",
                )
            )
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    _style_evidence_axes(op, layer, preparation, x_numeric=False, y_numeric=True)
    layer.axis("x").set_limits(0.5, len(spec.series) + 0.5, 1.0)
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    label_index = sheet.lt_col_index("__GroupLabel")
    label_range = f"{sheet.lt_range(False)}!col({label_index})"
    if not layer.obj.LT_execute(
        f"range __raw_group_labels={label_range};axis -ps X T __raw_group_labels;"
    ):
        raise OriginDrawError("Origin could not bind raw-summary group labels.")
    layer.set_int("x.minorTicks", 0)
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    _remove_label(layer, "Legend")
    _remove_label(layer, "legend")
    labels, title_state, text_state = _style_titles(op, graph, layer, preparation)
    axis_state = _validate_axes(op, layer, preparation)
    symbol_state: dict[str, Any] = {}
    try:
        for name, plot in scatter_plots.items():
            symbol_state[name] = verify_symbol_style(
                op,
                plot,
                expected_size_pt=spec.display_plan.marker_size_pt,
                expected_edge_percent=35.0,
            )
        line_state = verify_plot_line_widths(
            op,
            median_plots,
            style.plot_line_width_pt,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return graph, {
        **geometry,
        "origin_plot_state": {
            "raw_colors": color_state,
            "raw_symbols": symbol_state,
            "median_lines": line_state,
            "center_statistic": "median",
        },
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": list(helpers),
        "origin_plot_data_columns": list(plot_frame.columns),
        "title_objects": list(labels),
    }


def _build_distribution_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    series_columns = [item.source_column for item in spec.series]
    plot_frame = frame.loc[:, series_columns].copy(deep=True)
    sheet = op.new_sheet("w", f"{preparation.template_id.upper()} Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the distribution plot worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis("y")
    sheet.activate()
    theme = "Box_HalfViolin" if spec.plot_kind == "raincloud" else "Box_Violin"
    command = (
        f'plotgboxraw irng:={sheet.lt_range(False)}!1:{len(series_columns)} '
        f'num:=1 g1:="Long Name" sort:=0 theme:="{theme}";'
    )
    if not op.lt_exec(command):
        raise OriginDrawError(f"Origin rejected the documented plotgboxraw theme {theme!r}.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the distribution graph.")
    layer = graph[0]
    # plotgboxraw creates a grouped statistics plot.  The documented ungroup
    # operation is required before each source group can retain its own color.
    layer.group(False)
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    layer.rescale()
    _style_evidence_axes(op, layer, preparation, x_numeric=False, y_numeric=True)
    layer.axis("x").set_limits(0.5, len(series_columns) + 0.5, 1.0)
    plan = spec.axis_plan
    layer.axis("y").set_limits(plan.y_from, plan.y_to, plan.y_step)
    plot_state = _style_plot_family(
        op,
        layer,
        preparation,
        transparency=style.fill_transparency_percent,
    )
    box_state: list[dict[str, float]] = []
    for index in range(1, len(layer.plot_list()) + 1):
        # Documented box-chart and symbol properties.  The Violin envelope
        # remains a neutral density field while the box/raw observations carry
        # the coherent family colors.
        layer.set_float(f"plot{index}.boxchart.width", 24.0)
        layer.set_int(f"plot{index}.symbol.kind", 2)
        layer.set_int(f"plot{index}.symbol.interior", 0)
        layer.set_int(f"plot{index}.boxchart.line", 2)
        item = {
            "width": float(layer.get_float(f"plot{index}.boxchart.width")),
            "symbol_kind": float(layer.get_float(f"plot{index}.symbol.kind")),
            "symbol_interior": float(layer.get_float(f"plot{index}.symbol.interior")),
            "boxchart_line": float(layer.get_float(f"plot{index}.boxchart.line")),
        }
        if abs(item["width"] - 24.0) > 0.05 or int(item["symbol_kind"]) != 2:
            raise OriginDrawError("Origin distribution object did not keep the frozen symbol/width contract.")
        box_state.append(item)
    _remove_label(layer, "Legend")
    _remove_label(layer, "legend")
    labels, title_state, text_state = _style_titles(op, graph, layer, preparation)
    axis_state = _validate_axes(op, layer, preparation)
    return graph, {
        **geometry,
        "origin_command": command,
        "origin_plot_state": plot_state,
        "origin_distribution_state": box_state,
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": [],
        "origin_plot_data_columns": series_columns,
        "specialized_theme": theme,
        "title_objects": list(labels),
    }


def _build_grouped_box_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    """Build grouped raw boxes from immutable wide columns plus OPJU-only jitter."""
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    columns = [series.source_column for series in spec.series]
    raw_frame = frame.loc[:, columns].copy(deep=True)
    sheet = op.new_sheet("w", "GROUPED BOX Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the grouped-box worksheet.")
    sheet.from_df(raw_frame)
    sheet.cols_axis("y" * len(columns))
    for index, series in enumerate(spec.series):
        sheet.set_label(index, series.category or series.label, "L")
        sheet.set_label(index, series.group or "Group", "C")
    sheet.activate()
    theme = "Box_Dashed Whisker Thick Median"
    command = (
        f'plotgboxraw irng:={sheet.lt_range(False)}!1:{len(columns)} '
        f'num:=1 g1:="Long Name" sort:=0 theme:="{theme}";'
    )
    if not op.lt_exec(command):
        raise OriginDrawError("Origin rejected the verified grouped-box theme.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the grouped-box graph.")
    layer = graph[0]
    layer.group(False)
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    layer.rescale()
    _style_evidence_axes(op, layer, preparation, x_numeric=False, y_numeric=True)
    font_code = int(round(float(op.lt_float(f"font({style.font_family})"))))
    layer.set_int("x.label.font", font_code)
    layer.set_int("y.label.font", font_code)
    layer.axis("x").set_limits(0.5, len(columns) + 0.5, 1.0)
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    colors = palette_colors(style.palette_name)
    group_colors = {
        group: colors[index % len(colors)] for index, group in enumerate(spec.group_order)
    }
    box_state: list[dict[str, Any]] = []
    box_plots = list(layer.plot_list())
    for index, (plot, series) in enumerate(zip(box_plots, spec.series, strict=True), start=1):
        color = group_colors[series.group or spec.group_order[0]]
        plot.color = op.ocolor(color)
        plot.set_cmd(f"-c color({color})")
        layer.set_float(f"plot{index}.transparency", style.fill_transparency_percent)
        layer.set_float(f"plot{index}.boxchart.width", 34.0)
        layer.set_int(f"plot{index}.boxchart.line", 2)
        box_state.append(
            {
                "index": index,
                "category": series.category,
                "group": series.group,
                "color": color,
                "transparency_percent": float(layer.get_float(f"plot{index}.transparency")),
                "width": float(layer.get_float(f"plot{index}.boxchart.width")),
                "boxchart_line": int(layer.get_int(f"plot{index}.boxchart.line")),
            }
        )

    maximum = max(int(frame[column].notna().sum()) for column in columns)
    jitter_frame = pd.DataFrame(index=range(maximum))
    helper_columns: list[str] = []
    for index, series in enumerate(spec.series, start=1):
        values = frame[series.source_column].dropna().to_numpy(dtype=float)
        x_name = f"__RawX_{index}"
        y_name = f"__RawY_{index}"
        jitter_frame[x_name] = pd.Series(
            np.full(values.size, float(index)) + evidence_jitter_offsets(values.size, index - 1) * 0.72
        )
        jitter_frame[y_name] = pd.Series(values)
        helper_columns.extend((x_name, y_name))
    jitter_sheet = op.new_sheet("w", "GROUPED BOX Raw Point Helpers")
    if jitter_sheet is None:
        raise OriginDrawError("Origin could not create grouped-box raw-point helpers.")
    jitter_sheet.from_df(jitter_frame)
    jitter_sheet.cols_axis()
    raw_plots: dict[str, Any] = {}
    for index, series in enumerate(spec.series, start=1):
        plot = layer.add_plot(jitter_sheet, f"__RawY_{index}", f"__RawX_{index}", type="s")
        if plot is None:
            raise OriginDrawError("Origin could not overlay grouped-box raw observations.")
        plot.color = "#20262B"
        plot.set_cmd(
            "-c color(#20262B)",
            "-k 2",
            "-kf 0",
            f"-z {spec.display_plan.marker_size_pt:g}",
            "-kh 30",
        )
        plot.transparency = 18.0
        raw_plots[series.label] = plot

    # Adding raw scatter overlays can trigger Origin's automatic rescale and
    # silently discard the frozen evidence bands. Restore the exact plan only
    # after every data plot exists, before placing data-attached text.
    layer.axis("x").set_limits(
        spec.axis_plan.x_from,
        spec.axis_plan.x_to,
        spec.axis_plan.x_step,
    )
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )

    y_span = spec.axis_plan.y_to - spec.axis_plan.y_from
    x_span = spec.axis_plan.x_to - spec.axis_plan.x_from

    def add_scale_text(
        text: str,
        x_value: float,
        y_value: float,
        *,
        size_pt: float,
        bold: bool,
        color: str,
    ) -> tuple[Any, dict[str, float | int | str]]:
        label = layer.add_label(text)
        if label is None:
            raise OriginDrawError(f"Origin could not add grouped-box text {text!r}.")
        # originpro.add_label defaults to page attachment (attach=0), even
        # when x/y values are supplied.  These labels must follow the data
        # axes when a user edits or rescales the graph.
        label.set_int("attach", 2)
        label.set_float("x1", float(x_value))
        label.set_float("y1", float(y_value))
        _style_label(label, size_pt, bold=bold)
        label.set_int("font", font_code)
        label.color = op.ocolor(color)
        state: dict[str, float | int | str] = {
            "text": str(label.text),
            "attach": int(label.get_int("attach")),
            "x": float(label.get_float("x1")),
            "y": float(label.get_float("y1")),
            "font_code": int(round(float(label.get_float("font")))),
            "font_size_pt": float(label.get_float("fsize")),
        }
        if state["text"] != text:
            raise OriginDrawError(f"Origin changed grouped-box text {text!r}.")
        if state["attach"] != 2:
            raise OriginDrawError(f"Origin did not attach grouped-box text {text!r} to the data scale.")
        if state["font_code"] != font_code:
            raise OriginDrawError(f"Origin grouped-box text {text!r} is not {style.font_family}.")
        if abs(float(state["font_size_pt"]) - size_pt) > 0.05:
            raise OriginDrawError(f"Origin grouped-box text {text!r} has the wrong font size.")
        return label, state

    n_labels: dict[str, dict[str, float | int | str]] = {}
    n_label_y = spec.axis_plan.y_from + y_span * 0.10
    for index, series in enumerate(spec.series, start=1):
        count = int(frame[series.source_column].notna().sum())
        _label, label_state = add_scale_text(
            f"n={count}",
            float(index) - min(0.18, x_span * 0.0225),
            float(n_label_y),
            size_pt=style.legend_size_pt * 0.78,
            bold=False,
            color="#59636B",
        )
        label_state["count"] = count
        label_state["source_column"] = series.source_column
        n_labels[series.label] = label_state

    # The native plotgboxraw legend inherits a framed template object whose
    # attachment coordinates vary with the physical page. Replace it with
    # borderless editable labels in data coordinates so placement is stable.
    _remove_label(layer, "Legend")
    _remove_label(layer, "legend")
    legend_x = np.linspace(
        spec.axis_plan.x_from + x_span * 0.38,
        spec.axis_plan.x_from + x_span * 0.62,
        max(1, len(spec.group_order)),
    )
    legend_y = spec.axis_plan.y_to - y_span * 0.055
    direct_legend: dict[str, dict[str, Any]] = {}
    for group, x_value in zip(spec.group_order, legend_x, strict=True):
        swatch_x = float(x_value - x_span * 0.020)
        text_x = float(x_value + x_span * 0.012)
        _swatch, swatch_state = add_scale_text(
            "■",
            swatch_x,
            float(legend_y),
            size_pt=style.legend_size_pt,
            bold=False,
            color=group_colors[group],
        )
        _text_label, text_state_item = add_scale_text(
            group,
            text_x,
            float(legend_y),
            size_pt=style.legend_size_pt,
            bold=False,
            color="#20262B",
        )
        direct_legend[group] = {
            "swatch": swatch_state,
            "label": text_state_item,
            "color": group_colors[group],
        }
    if layer.label("Legend") is not None or layer.label("legend") is not None:
        raise OriginDrawError("Origin kept the unwanted framed grouped-box legend.")
    labels, title_state, text_state = _style_titles(op, graph, layer, preparation)
    title_font_codes: dict[str, int] = {}
    for name, label in labels.items():
        if label is None:
            continue
        label.set_int("font", font_code)
        title_font_codes[name] = int(round(float(label.get_float("font"))))
        if title_font_codes[name] != font_code:
            raise OriginDrawError(f"Origin grouped-box {name} is not {style.font_family}.")
    op.lt_exec("doc -uw;")
    axis_state = _validate_axes(op, layer, preparation)
    axis_state["x.label.font"] = float(layer.get_float("x.label.font"))
    axis_state["y.label.font"] = float(layer.get_float("y.label.font"))
    expected_limits = {
        "x.from": spec.axis_plan.x_from,
        "x.to": spec.axis_plan.x_to,
        "y.from": spec.axis_plan.y_from,
        "y.to": spec.axis_plan.y_to,
    }
    for key, expected in expected_limits.items():
        if expected is None or abs(float(axis_state[key]) - float(expected)) > 1e-6:
            raise OriginDrawError(f"Origin grouped-box axis {key} does not match the frozen plan.")
    if any(abs(float(axis_state[key]) - font_code) > 0.05 for key in ("x.label.font", "y.label.font")):
        raise OriginDrawError(f"Origin grouped-box tick labels are not {style.font_family}.")
    try:
        symbol_state = {
            name: verify_symbol_style(
                op,
                plot,
                expected_size_pt=spec.display_plan.marker_size_pt,
                expected_edge_percent=30.0,
            )
            for name, plot in raw_plots.items()
        }
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return graph, {
        **geometry,
        "origin_command": command,
        "specialized_theme": theme,
        "origin_plot_state": {
            "boxes": box_state,
            "raw_symbols": symbol_state,
            "sample_size_labels": n_labels,
            "native_group_legend_present": False,
            "borderless_group_legend": direct_legend,
            "category_labels": list(spec.category_order),
            "group_labels": list(spec.group_order),
        },
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "font_code_expected": font_code,
            "title_font_codes": title_font_codes,
            "axis_titles": {"x": spec.x_title, "y": spec.y_title},
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": helper_columns,
        "origin_plot_data_columns": columns,
        "column_label_rows": {
            "Long Name": [series.category for series in spec.series],
            "Comments": [series.group for series in spec.series],
        },
        "title_objects": list(labels),
    }


def _build_histogram_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    series_columns = [item.source_column for item in spec.series]
    plot_frame = frame.loc[:, series_columns].copy(deep=True)
    sheet = op.new_sheet("w", "HISTOGRAM Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the histogram plot worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis("y")
    sheet.activate()
    command = (
        f"plotxy iy:={sheet.lt_range(False)}!1:{len(series_columns)} plot:=219 "
        "ogl:=<new template:=HISTGM>;"
    )
    if not op.lt_exec(command):
        raise OriginDrawError("Origin rejected official Histogram plot type 219.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the Histogram graph.")
    layer = graph[0]
    if spec.bin_begin is None or spec.bin_end is None or spec.bin_size is None:
        raise OriginDrawError("Histogram bin contract is incomplete.")
    for index in range(1, len(series_columns) + 1):
        layer.set_float(f"plot{index}.boxchart.binBegin", spec.bin_begin)
        layer.set_float(f"plot{index}.boxchart.binEnd", spec.bin_end)
        layer.set_float(f"plot{index}.boxchart.binSize", spec.bin_size)
    graph.activate()
    op.lt_exec("doc -uw;")
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    _style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=True)
    layer.axis("x").set_limits(
        spec.axis_plan.x_from,
        spec.axis_plan.x_to,
        spec.axis_plan.x_step,
    )
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    plot_state = _style_plot_family(op, layer, preparation)
    bin_state: list[dict[str, float]] = []
    for index in range(1, len(layer.plot_list()) + 1):
        item = {
            "begin": float(layer.get_float(f"plot{index}.boxchart.binBegin")),
            "end": float(layer.get_float(f"plot{index}.boxchart.binEnd")),
            "size": float(layer.get_float(f"plot{index}.boxchart.binSize")),
        }
        if not all(math.isfinite(value) for value in item.values()) or item["size"] <= 0:
            raise OriginDrawError("Origin Histogram bin state is invalid.")
        expected = (spec.bin_begin, spec.bin_end, spec.bin_size)
        actual = (item["begin"], item["end"], item["size"])
        if any(
            abs(got - wanted) > 1e-9
            for got, wanted in zip(actual, expected, strict=True)
        ):
            raise OriginDrawError(
                f"Origin Histogram bin readback {actual!r} does not match plan {expected!r}."
            )
        bin_state.append(item)
    legend = None
    if len(series_columns) == 1:
        _remove_label(layer, "Legend")
        _remove_label(layer, "legend")
    else:
        legend = layer.label("Legend") or layer.label("legend")
        _style_label(legend, style.legend_size_pt, bold=False)
        if legend is None:
            raise OriginDrawError("Origin Histogram legend is missing.")
        legend.set_int("font", _origin_font_code(op, style.font_family))
        _set_borderless_legend(legend)
    labels, title_state, text_state = _style_titles(op, graph, layer, preparation)
    if legend is not None:
        try:
            text_state.update(
                verify_text_sizes({"legend": legend}, {"legend": style.legend_size_pt})
            )
            text_state.update(
                verify_text_fonts(op, {"legend": legend}, style.font_family)
            )
            text_state["legend.showframe"] = int(legend.get_int("showframe"))
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
    axis_state = _validate_axes(op, layer, preparation)
    return graph, {
        **geometry,
        "origin_command": command,
        "origin_plot_state": plot_state,
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_histogram_bins": bin_state,
        "origin_helper_columns": [],
        "origin_plot_data_columns": series_columns,
        "title_objects": list(labels),
    }


def _build_bubble_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    series = spec.series[0]
    if not spec.x_column or not series.size_column:
        raise OriginDrawError("Bubble X or size column is missing.")
    columns = [spec.x_column, series.source_column, series.size_column]
    plot_frame = frame.loc[:, columns].copy(deep=True)
    sheet = op.new_sheet("w", "BUBBLE Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the Bubble plot worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis("xyy")
    sheet.activate()
    command = (
        f"plotxy iy:={sheet.lt_range(False)}!(A,B:C) plot:=193 "
        "ogl:=<new template:=Bubble>;"
    )
    if not op.lt_exec(command):
        raise OriginDrawError("Origin rejected official indexed-size Bubble plot type 193.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the Bubble graph.")
    layer = graph[0]
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    _style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=True)
    layer.axis("x").set_limits(
        spec.axis_plan.x_from,
        spec.axis_plan.x_to,
        spec.axis_plan.x_step,
    )
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    plot_state = _style_plot_family(op, layer, preparation)
    plot = list(layer.plot_list())[0]
    # Keep the native indexed-size mapping from the official Bubble template,
    # but freeze the visible glyph to the publication profile used by preview:
    # solid circles with a restrained same-family edge.
    plot.symbol_kind = 2
    plot.symbol_interior = 0
    plot.set_cmd("-k 2", "-kf 0", "-kh 35")
    layer.set_float("plot1.symbol.transparency", style.fill_transparency_percent)
    _remove_label(layer, "Legend")
    _remove_label(layer, "legend")
    # Origin's native Bubble Scale is editable, but Origin 2024b does not expose
    # its nested title/label point sizes through the normal label API.  Keeping
    # it would therefore bypass our verified 16 pt legend contract.  Replace it
    # with an editable, explicit mapping note whose font can be read back.
    native_scale = layer.label("BUBBLELEGEND1")
    native_scale_present = native_scale is not None
    if native_scale is not None:
        native_scale.remove()
    size_min = float(frame[series.size_column].min())
    size_max = float(frame[series.size_column].max())
    x_span = spec.axis_plan.x_to - spec.axis_plan.x_from
    y_span = spec.axis_plan.y_to - spec.axis_plan.y_from
    note_text = f"Bubble area = {series.size_column} ({size_min:g}-{size_max:g})"
    size_note = layer.add_label(
        note_text,
        spec.axis_plan.x_from + x_span * 0.035,
        spec.axis_plan.y_to - y_span * 0.045,
    )
    if size_note is None:
        raise OriginDrawError("Origin could not create the editable Bubble size note.")
    _style_label(size_note, style.legend_size_pt, bold=False)
    size_note.set_int("font", _origin_font_code(op, style.font_family))
    size_note.color = op.ocolor("#334155")
    op.lt_exec("doc -uw;")
    note_size = float(size_note.get_float("fsize"))
    note_font = int(round(float(size_note.get_float("font"))))
    if abs(note_size - style.legend_size_pt) > 0.05:
        raise OriginDrawError(
            "Origin Bubble size-note font verification failed: "
            f"{note_size:g} pt, expected {style.legend_size_pt:g} pt"
        )
    if note_font != _origin_font_code(op, style.font_family):
        raise OriginDrawError("Origin Bubble size-note font verification failed.")
    bubble_scale_state: dict[str, float | bool | str] = {
        "native_scale_was_present": native_scale_present,
        "native_scale_removed": layer.label("BUBBLELEGEND1") is None,
        "mapping_note_present": True,
        "mapping_note_text": note_text,
        "mapping_note_font_size_pt": note_size,
        "mapping_note_font_code": note_font,
        "font_code_expected": _origin_font_code(op, style.font_family),
        "mapping_note_x": float(size_note.get_float("x1")),
        "mapping_note_y": float(size_note.get_float("y1")),
    }
    labels, title_state, text_state = _style_titles(op, graph, layer, preparation)
    axis_state = _validate_axes(op, layer, preparation)
    return graph, {
        **geometry,
        "origin_command": command,
        "origin_plot_state": plot_state,
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_bubble_scale": bubble_scale_state,
        "origin_size_column": series.size_column,
        "origin_size_range": [
            size_min,
            size_max,
        ],
        "origin_helper_columns": [],
        "origin_plot_data_columns": columns,
        "title_objects": list(labels),
    }


def _forest_plot_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    spec = preparation.plot_spec
    category = spec.category_column
    series = spec.series[0]
    if not category or not series.lower_column or not series.upper_column:
        raise OriginDrawError("Forest category or interval columns are missing.")
    count = len(frame)
    rows = np.arange(count, 0, -1, dtype=float)
    interval_x: list[float] = []
    interval_y: list[float] = []
    cap_x: list[float] = []
    cap_y: list[float] = []
    cap_half_height = 0.13
    for row_index, row_value in enumerate(rows):
        low = float(frame.iloc[row_index][series.lower_column])
        high = float(frame.iloc[row_index][series.upper_column])
        interval_x.extend((low, high, np.nan))
        interval_y.extend((row_value, row_value, np.nan))
        cap_x.extend((low, low, np.nan, high, high, np.nan))
        cap_y.extend(
            (
                row_value - cap_half_height,
                row_value + cap_half_height,
                np.nan,
                row_value - cap_half_height,
                row_value + cap_half_height,
                np.nan,
            )
        )
    length = max(count, len(interval_x), len(cap_x))
    plot_frame = pd.DataFrame(index=range(length))
    plot_frame[series.source_column] = pd.Series(
        frame[series.source_column].to_numpy(dtype=float)
    )
    plot_frame["__ForestRow"] = pd.Series(rows)
    plot_frame["__ForestLabel"] = pd.Series(
        list(reversed([str(value) for value in frame[category]]))
    )
    plot_frame["__CI_X"] = pd.Series(interval_x)
    plot_frame["__CI_Y"] = pd.Series(interval_y)
    plot_frame["__Cap_X"] = pd.Series(cap_x)
    plot_frame["__Cap_Y"] = pd.Series(cap_y)
    return plot_frame, (
        "__ForestRow",
        "__ForestLabel",
        "__CI_X",
        "__CI_Y",
        "__Cap_X",
        "__Cap_Y",
    )


def _build_forest_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    plot_frame, helpers = _forest_plot_frame(frame, preparation)
    sheet = op.new_sheet("w", "FOREST Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the Forest plot worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis()
    graph = op.new_graph("FOREST Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the Forest graph.")
    layer = graph[0]
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    interval = layer.add_plot(sheet, "__CI_Y", "__CI_X", type="l")
    caps = layer.add_plot(sheet, "__Cap_Y", "__Cap_X", type="l")
    estimate = layer.add_plot(sheet, "__ForestRow", spec.series[0].source_column, type="s")
    if interval is None or caps is None or estimate is None:
        raise OriginDrawError("Origin could not create all editable Forest plot objects.")
    colors = palette_colors(style.palette_name)
    interval.color = colors[0]
    caps.color = colors[0]
    estimate.color = colors[0]
    interval.set_cmd(f"-w {pt_to_origin_width_units(style.error_bar_width_pt)}")
    caps.set_cmd(f"-w {pt_to_origin_width_units(style.error_bar_width_pt)}")
    estimate.symbol_kind = 2
    estimate.symbol_interior = 0
    estimate.symbol_size = spec.display_plan.marker_size_pt
    estimate.set_cmd(f"-c color({colors[0]})", "-k 2", "-kf 0", "-kh 45")
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    _style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=False)
    layer.axis("x").set_limits(
        spec.axis_plan.x_from,
        spec.axis_plan.x_to,
        spec.axis_plan.x_step,
    )
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    label_index = sheet.lt_col_index("__ForestLabel")
    label_range = f"{sheet.lt_range(False)}!col({label_index})"
    if not layer.obj.LT_execute(
        f"range __forest_labels={label_range};axis -ps Y T __forest_labels;"
    ):
        raise OriginDrawError("Origin could not bind Forest row labels.")
    layer.set_int("y.minorTicks", 0)
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    if layer.get_int("y.label.type") != 2:
        raise OriginDrawError("Origin did not keep Forest text labels on the Y axis.")
    reference_state: dict[str, float | bool] = {"present": False}
    if spec.reference_value is not None:
        graph.activate()
        command = (
            f"addline type:=0 value:={spec.reference_value:g} color:=color(#777777) "
            "style:=1 select:=1 move:=1 name:=ReferenceLine;"
        )
        if not op.lt_exec(command):
            raise OriginDrawError("Origin rejected the documented Forest reference line.")
        _remove_label(layer, "ReferenceLineText")
        reference_state = {
            "present": layer.label("ReferenceLine") is not None,
            "text_present": layer.label("ReferenceLineText") is not None,
            "value": spec.reference_value,
        }
        if not reference_state["present"]:
            raise OriginDrawError("Origin Forest reference line is missing after addline.")
        if reference_state["text_present"]:
            raise OriginDrawError("Origin Forest reference line kept an unwanted value label.")
    _remove_label(layer, "Legend")
    _remove_label(layer, "legend")
    labels, title_state, text_state = _style_titles(
        op,
        graph,
        layer,
        preparation,
        keep_y_title=False,
    )
    axis_state = _validate_axes(op, layer, preparation)
    try:
        line_state = verify_plot_line_widths(
            op,
            {"interval": interval, "caps": caps},
            style.error_bar_width_pt,
        )
        symbol_state = verify_symbol_style(
            op,
            estimate,
            expected_size_pt=spec.display_plan.marker_size_pt,
            expected_edge_percent=45.0,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return graph, {
        **geometry,
        "origin_plot_state": {
            "line_widths": line_state,
            "estimate_symbol": symbol_state,
            "reference": reference_state,
        },
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": list(helpers),
        "origin_plot_data_columns": list(plot_frame.columns),
        "title_objects": list(labels),
    }


def build_shap_composite_helper_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Build profile-specific Origin helpers without mutating source data.

    The supplied SHAP values are copied exactly into ``__SHAP_X``.  Every
    additional column is an Origin-workbook helper derived from the frozen
    :class:`~origin_sciplot.shap_composite.ShapCompositePlan`; no helper is
    written back to the user's source frame.
    """
    spec = preparation.plot_spec
    plan = spec.shap_plan
    series = spec.series[0]
    if plan is None:
        raise OriginDrawError(
            "The frozen SHAP composite plan is missing.",
            code="shap_composite_plan_missing",
        )
    if plan.profile not in SHAP_COMPOSITE_PROFILES:
        raise OriginDrawError(
            f"Unknown SHAP composite profile: {plan.profile!r}.",
            code="shap_composite_profile_invalid",
        )
    if not spec.category_column or not series.color_column:
        raise OriginDrawError(
            "SHAP category or color column is missing.",
            code="shap_composite_roles_missing",
        )
    features = np.asarray(
        [str(value).strip() for value in frame[spec.category_column]],
        dtype=object,
    )
    shap_values = frame[series.source_column].to_numpy(dtype=float, copy=True)
    normalized = shap_within_feature_color_values(
        frame,
        spec.category_column,
        series.color_column,
    )
    y_values = np.empty(shap_values.size, dtype=float)
    count = len(plan.feature_order)
    for index, feature in enumerate(plan.feature_order):
        members = np.flatnonzero(features == feature)
        y_values[members] = float(count - index) + shap_beeswarm_offsets(shap_values[members])
    mean_count = len(plan.mean_abs_values)
    group_count = len(plan.group_contributions)
    length = max(len(frame), count, mean_count, group_count)
    plot_frame = pd.DataFrame(index=range(length))
    plot_frame["__SHAP_X"] = pd.Series(shap_values)
    plot_frame["__SHAP_Y"] = pd.Series(y_values)
    plot_frame["__FeatureValueNormalized"] = pd.Series(normalized)
    plot_frame["__FeatureLabel"] = pd.Series(list(reversed(plan.feature_order)))
    helpers = [
        "__SHAP_X",
        "__SHAP_Y",
        "__FeatureValueNormalized",
        "__FeatureLabel",
    ]
    if plan.profile != "beeswarm_only":
        # Origin's horizontal BAR template draws the final worksheet row at
        # the top.  Store the frozen feature order in reverse so the native
        # bars align with the beeswarm's top-to-bottom feature order without
        # reversing or rewriting any supplied SHAP values.
        mean_rows = tuple(reversed(plan.mean_abs_values))
        plot_frame["__MeanAbsFeature"] = pd.Series(
            [feature for feature, _value in mean_rows],
            dtype=object,
        )
        plot_frame["__MeanAbsValue"] = pd.Series(
            [float(value) for _feature, value in mean_rows],
            dtype=float,
        )
        helpers.extend(("__MeanAbsFeature", "__MeanAbsValue"))
    if plan.profile == "beeswarm_mean_abs_grouped":
        plot_frame["__GroupLabel"] = pd.Series(
            [group for group, _value in plan.group_contributions],
            dtype=object,
        )
        plot_frame["__GroupContribution"] = pd.Series(
            [float(value) for _group, value in plan.group_contributions],
            dtype=float,
        )
        helpers.extend(("__GroupLabel", "__GroupContribution"))
    return plot_frame, tuple(helpers)


def _shap_plot_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Compatibility wrapper for the former private SHAP helper seam."""

    return build_shap_composite_helper_frame(frame, preparation)


def _required_shap_helpers(
    plan: ShapCompositePlan,
    *,
    include_pie_color: bool,
) -> tuple[str, ...]:
    required = [
        "__SHAP_X",
        "__SHAP_Y",
        "__FeatureValueNormalized",
        "__FeatureLabel",
    ]
    if plan.profile != "beeswarm_only":
        required.extend(("__MeanAbsFeature", "__MeanAbsValue"))
    if plan.profile == "beeswarm_mean_abs_grouped":
        required.extend(("__GroupLabel", "__GroupContribution"))
        if include_pie_color:
            required.append("__PieColor")
    return tuple(required)


def _readback_mapping(state: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = state.get(key)
    if not isinstance(value, Mapping):
        raise OriginDrawError(
            f"Origin SHAP readback is missing {key!r} evidence.",
            code="shap_composite_readback_incomplete",
        )
    return value


def _readback_number(mapping: Mapping[str, object], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool):
        raise OriginDrawError(
            f"Origin SHAP readback field {key!r} is not numeric.",
            code="shap_composite_readback_invalid",
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OriginDrawError(
            f"Origin SHAP readback field {key!r} is not numeric.",
            code="shap_composite_readback_invalid",
        ) from exc
    if not math.isfinite(number):
        raise OriginDrawError(
            f"Origin SHAP readback field {key!r} is not finite.",
            code="shap_composite_readback_invalid",
        )
    return number


def _readback_string_sequence(
    mapping: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    raw = mapping.get(key)
    if not isinstance(raw, (list, tuple)) or not all(isinstance(item, str) for item in raw):
        raise OriginDrawError(
            f"Origin SHAP readback field {key!r} is not a string sequence.",
            code="shap_composite_readback_invalid",
        )
    return tuple(raw)


def _readback_number_sequence(
    mapping: Mapping[str, object],
    key: str,
) -> tuple[float, ...]:
    raw = mapping.get(key)
    if not isinstance(raw, (list, tuple)):
        raise OriginDrawError(
            f"Origin SHAP readback field {key!r} is not a numeric sequence.",
            code="shap_composite_readback_invalid",
        )
    return tuple(_readback_number({key: item}, key) for item in raw)


def _require_close_sequence(
    actual: tuple[float, ...],
    expected: tuple[float, ...],
    *,
    code: str,
    message: str,
) -> None:
    if len(actual) != len(expected) or any(
        not math.isclose(got, wanted, rel_tol=1e-9, abs_tol=1e-9)
        for got, wanted in zip(actual, expected, strict=True)
    ):
        raise OriginDrawError(message, code=code)


def _validate_shap_plot_binding(
    panel: Mapping[str, object],
    *,
    expected_x: str,
    expected_y: str,
) -> None:
    binding = _readback_mapping(panel, "plot_binding")
    if not str(binding.get("plot_range", "")):
        raise OriginDrawError(
            "Origin SHAP plot-binding readback is missing its graph range.",
            code="shap_composite_plot_binding_mismatch",
        )
    for designation, expected_helper in (("x", expected_x), ("y", expected_y)):
        component = _readback_mapping(binding, designation)
        if (
            component.get("helper_column") != expected_helper
            or not _shap_binding_identity_matches(component)
        ):
            raise OriginDrawError(
                "Origin SHAP plot is not bound to the exact planned helper columns.",
                code="shap_composite_plot_binding_mismatch",
            )


def _validate_shap_template_cleanup(panel: Mapping[str, object]) -> None:
    cleanup = _readback_mapping(panel, "template_cleanup")
    requested = cleanup.get("requested")
    remaining = cleanup.get("remaining")
    if (
        cleanup.get("verified") is not True
        or not isinstance(requested, (list, tuple))
        or tuple(requested) != ("Legend", "legend", "xb", "yl", "yr")
        or not isinstance(remaining, (list, tuple))
        or tuple(remaining)
    ):
        raise OriginDrawError(
            "Origin SHAP template-object cleanup is incomplete.",
            code="shap_composite_template_cleanup_mismatch",
        )


def validate_shap_composite_readback(
    plan: ShapCompositePlan,
    geometry: ShapCompositeGeometry,
    state: Mapping[str, object],
) -> None:
    """Fail closed unless Origin proves the exact frozen SHAP composite.

    The state is deliberately backend-neutral so tests can exercise the same
    gate without launching Origin.  Production builds the state exclusively
    from worksheet, plot, graph-object and geometry readback after merge.
    """

    if not isinstance(plan, ShapCompositePlan):
        raise OriginDrawError(
            "Origin SHAP readback did not receive a frozen composite plan.",
            code="shap_composite_plan_missing",
        )
    if plan.profile not in SHAP_COMPOSITE_PROFILES:
        raise OriginDrawError(
            f"Unknown SHAP composite profile: {plan.profile!r}.",
            code="shap_composite_profile_invalid",
        )
    if not isinstance(geometry, ShapCompositeGeometry):
        raise OriginDrawError(
            "Origin SHAP readback did not receive frozen composite geometry.",
            code="shap_composite_geometry_missing",
        )
    if geometry.profile != plan.profile or geometry.layout_version != plan.layout_version:
        raise OriginDrawError(
            "Origin SHAP geometry does not match the frozen plan version/profile.",
            code="shap_composite_layout_version_mismatch",
        )
    if not isinstance(state, Mapping):
        raise OriginDrawError(
            "Origin SHAP readback is not a mapping.",
            code="shap_composite_readback_invalid",
        )
    if state.get("profile") != plan.profile:
        raise OriginDrawError(
            "Origin SHAP readback profile does not match the frozen plan.",
            code="shap_composite_profile_mismatch",
        )
    if state.get("layout_version") != plan.layout_version:
        raise OriginDrawError(
            "Origin SHAP readback layout version does not match the frozen plan.",
            code="shap_composite_layout_version_mismatch",
        )
    if state.get("source_x_unchanged") is not True:
        raise OriginDrawError(
            "Origin SHAP readback did not preserve the supplied SHAP X values.",
            code="shap_composite_source_x_changed",
        )

    raw_helpers = state.get("helper_columns")
    if not isinstance(raw_helpers, (list, tuple)) or not all(
        isinstance(column, str) for column in raw_helpers
    ):
        raise OriginDrawError(
            "Origin SHAP helper-column readback is missing or invalid.",
            code="shap_composite_helpers_missing",
        )
    expected_helpers = _required_shap_helpers(plan, include_pie_color=True)
    if tuple(raw_helpers) != expected_helpers:
        raise OriginDrawError(
            "Origin SHAP helper-column readback does not exactly match the selected profile.",
            code="shap_composite_helpers_mismatch",
        )

    expected_geometry = geometry.to_dict()["regions"]
    regions = _readback_mapping(state, "regions")
    if set(regions) != set(expected_geometry):
        raise OriginDrawError(
            "Origin SHAP readback does not contain exactly the planned figure regions.",
            code="shap_composite_regions_mismatch",
        )
    geometry_fields = (
        "left_percent",
        "top_percent",
        "width_percent",
        "height_percent",
    )
    for role, expected_box in expected_geometry.items():
        actual_box = regions.get(role)
        if not isinstance(actual_box, Mapping):
            raise OriginDrawError(
                f"Origin SHAP region {role!r} is missing geometry.",
                code="shap_composite_regions_mismatch",
            )
        if set(actual_box) != set(geometry_fields):
            raise OriginDrawError(
                f"Origin SHAP region {role!r} contains incomplete or extra geometry fields.",
                code="shap_composite_regions_mismatch",
            )
        if any(
            not math.isclose(
                _readback_number(actual_box, field),
                float(expected_box[field]),
                rel_tol=0.0,
                abs_tol=LAYER_GEOMETRY_TOLERANCE_PERCENT,
            )
            for field in geometry_fields
        ):
            raise OriginDrawError(
                f"Origin SHAP region {role!r} does not match the frozen geometry.",
                code="shap_composite_regions_mismatch",
            )

    plot_counts = _readback_mapping(state, "plot_counts")
    expected_plot_counts = {"shap_beeswarm": 1}
    if plan.profile != "beeswarm_only":
        expected_plot_counts["shap_mean_abs"] = 1
    if plan.profile == "beeswarm_mean_abs_grouped":
        expected_plot_counts["shap_group_contribution"] = 1
    if set(plot_counts) != set(expected_plot_counts) or any(
        _readback_number(plot_counts, role) != float(count)
        for role, count in expected_plot_counts.items()
    ):
        raise OriginDrawError(
            "Origin SHAP editable plot counts do not exactly match the selected profile.",
            code="shap_composite_plot_mismatch",
        )

    beeswarm = _readback_mapping(state, "beeswarm")
    if int(_readback_number(beeswarm, "pid")) != 201:
        raise OriginDrawError(
            "Origin SHAP beeswarm is not the planned editable scatter primitive.",
            code="shap_composite_beeswarm_mismatch",
        )
    reference = _readback_mapping(beeswarm, "reference")
    if (
        reference.get("present") is not True
        or reference.get("text_present") is not False
        or not math.isclose(
            _readback_number(reference, "value"),
            0.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or reference.get("color") != SHAP_ZERO_LINE_COLOR
    ):
        raise OriginDrawError(
            "Origin SHAP zero-reference evidence does not match the frozen design.",
            code="shap_composite_beeswarm_mismatch",
        )
    symbol = _readback_mapping(beeswarm, "symbol")
    if (
        _readback_number(symbol, "symbol_size_pt") <= 0.0
        or not math.isclose(
            _readback_number(symbol, "symbol_edge_percent_of_radius"),
            20.0,
            rel_tol=0.0,
            abs_tol=0.05,
        )
        or int(_readback_number(symbol, "symbol_kind")) != 2
        or int(_readback_number(symbol, "symbol_interior")) != 0
    ):
        raise OriginDrawError(
            "Origin SHAP scatter-symbol readback is incomplete or changed.",
            code="shap_composite_beeswarm_mismatch",
        )
    _validate_shap_plot_binding(
        beeswarm,
        expected_x="__SHAP_X",
        expected_y="__SHAP_Y",
    )
    _validate_shap_template_cleanup(beeswarm)

    colorbar = _readback_mapping(state, "colorbar")
    if colorbar.get("present") is not True:
        raise OriginDrawError(
            "Origin SHAP feature-value colorbar is missing.",
            code="shap_composite_colorbar_missing",
        )
    if colorbar.get("dataset") != "__FeatureValueNormalized":
        raise OriginDrawError(
            "Origin SHAP colorbar is not bound to the normalized feature-value helper.",
            code="shap_composite_colorbar_dataset_mismatch",
        )
    if colorbar.get("associated_object") != "Spectrum1":
        raise OriginDrawError(
            "Origin SHAP colorbar is not the associated editable Spectrum1 object.",
            code="shap_composite_colorbar_object_mismatch",
        )
    if _readback_number(colorbar, "edge_mode") != 2.0 or _readback_number(
        colorbar,
        "fill_mode",
    ) != 2.0:
        raise OriginDrawError(
            "Origin SHAP symbols are not dataset-bound for both edge and fill color.",
            code="shap_composite_colorbar_dataset_mismatch",
        )
    edge_dataset = str(colorbar.get("edge_dataset", ""))
    fill_dataset = str(colorbar.get("fill_dataset", ""))
    if edge_dataset != "__FeatureValueNormalized" or fill_dataset != edge_dataset:
        raise OriginDrawError(
            "Origin SHAP edge/fill colors do not use the normalized helper dataset.",
            code="shap_composite_colorbar_dataset_mismatch",
        )
    color_minimum = _readback_number(colorbar, "minimum")
    color_maximum = _readback_number(colorbar, "maximum")
    if not math.isclose(color_minimum, 0.0, abs_tol=0.01) or not math.isclose(
        color_maximum,
        1.0,
        abs_tol=0.01,
    ):
        raise OriginDrawError(
            "Origin SHAP colorbar must retain the normalized 0-to-1 scale.",
            code="shap_composite_colorbar_range_mismatch",
        )
    if colorbar.get("direction") != "low_blue_high_red":
        raise OriginDrawError(
            "Origin SHAP colorbar direction is not low-blue/high-red.",
            code="shap_composite_colorbar_direction_mismatch",
        )
    if _readback_number(colorbar, "spectrum_revorder") != 1.0:
        raise OriginDrawError(
            "Origin SHAP Spectrum1 must place high/red at the top and low/blue at the bottom.",
            code="shap_composite_colorbar_direction_mismatch",
        )

    mean_abs = _readback_mapping(state, "mean_abs")
    expected_mean_abs = plan.profile != "beeswarm_only"
    if (mean_abs.get("present") is True) is not expected_mean_abs:
        raise OriginDrawError(
            "Origin SHAP Mean |SHAP| panel presence does not match the selected profile.",
            code="shap_composite_mean_abs_mismatch",
        )
    if expected_mean_abs:
        expected_labels = tuple(feature for feature, _value in plan.mean_abs_values)
        expected_values = tuple(float(value) for _feature, value in plan.mean_abs_values)
        if _readback_string_sequence(mean_abs, "labels") != expected_labels:
            raise OriginDrawError(
                "Origin Mean |SHAP| labels do not match the frozen feature order.",
                code="shap_composite_mean_abs_mismatch",
            )
        _require_close_sequence(
            _readback_number_sequence(mean_abs, "values"),
            expected_values,
            code="shap_composite_mean_abs_mismatch",
            message="Origin Mean |SHAP| values do not match the frozen summary.",
        )
        if (
            mean_abs.get("source") != plan.mean_abs_source
            or mean_abs.get("label_dataset") != "__MeanAbsFeature"
            or mean_abs.get("value_dataset") != "__MeanAbsValue"
            or int(_readback_number(mean_abs, "pid")) != 215
        ):
            raise OriginDrawError(
                "Origin Mean |SHAP| datasets/source do not match the frozen plan.",
                code="shap_composite_mean_abs_mismatch",
            )
        _mean_from, expected_mean_to, expected_mean_step = resolve_shap_mean_axis(
            max(expected_values, default=0.0)
        )
        _require_close_sequence(
            _readback_number_sequence(mean_abs, "mean_axis_limits"),
            (0.0, expected_mean_to),
            code="shap_composite_mean_abs_mismatch",
            message="Origin Mean |SHAP| axis limits are not publication-readable.",
        )
        if not math.isclose(
            _readback_number(mean_abs, "mean_axis_step"),
            expected_mean_step,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise OriginDrawError(
                "Origin Mean |SHAP| axis increment changed from the frozen nice step.",
                code="shap_composite_mean_abs_mismatch",
            )
        layer_link = _readback_mapping(mean_abs, "layer_link")
        expected_layer_link: dict[str, object] = {
            "parent_layer": 1,
            "expected_parent_layer": 1,
            "child_layer": 2,
            "expected_child_layer": 2,
            "parent_role": "shap_mean_abs",
            "child_role": "shap_beeswarm",
            "unit": 1,
            "expected_unit": 1,
            "requested_x_axis_link": 0,
            "requested_y_axis_link": 0,
            "verified": True,
            "final_parent_layer": 1,
            "final_unit": 1,
        }
        if set(layer_link) != set(expected_layer_link) or any(
            layer_link.get(key) != expected
            for key, expected in expected_layer_link.items()
        ):
            raise OriginDrawError(
                "Origin Mean |SHAP| and beeswarm layers lost their frozen geometry link.",
                code="shap_composite_mean_link_mismatch",
            )
        title_collision = _readback_mapping(mean_abs, "title_collision")
        expected_maximum = geometry.region("shap_mean_abs").top_percent - 3.2
        title_bottom = _readback_number(title_collision, "bottom_percent")
        maximum_bottom = _readback_number(
            title_collision,
            "maximum_bottom_percent",
        )
        if (
            title_collision.get("object") != "SHAPMeanTitle"
            or title_collision.get("verified") is not True
            or not math.isclose(
                maximum_bottom,
                expected_maximum,
                rel_tol=0.0,
                abs_tol=LAYER_GEOMETRY_TOLERANCE_PERCENT,
            )
            or title_bottom > maximum_bottom
        ):
            raise OriginDrawError(
                "Origin Mean |SHAP| title collision evidence is missing or invalid.",
                code="shap_composite_mean_title_overlap",
            )
        _validate_shap_plot_binding(
            mean_abs,
            expected_x="__MeanAbsFeature",
            expected_y="__MeanAbsValue",
        )
        _validate_shap_template_cleanup(mean_abs)
    group_inset = _readback_mapping(state, "group_inset")
    expected_group_inset = plan.profile == "beeswarm_mean_abs_grouped"
    if (group_inset.get("present") is True) is not expected_group_inset:
        raise OriginDrawError(
            "Origin SHAP group-composition pie presence does not match the selected profile.",
            code="shap_composite_group_inset_mismatch",
        )
    if expected_group_inset:
        expected_labels = tuple(group for group, _value in plan.group_contributions)
        expected_values = tuple(float(value) for _group, value in plan.group_contributions)
        pie_label_theme = _readback_mapping(group_inset, "label_theme")
        if _readback_string_sequence(group_inset, "labels") != expected_labels:
            raise OriginDrawError(
                "Origin SHAP group labels do not match the frozen group order.",
                code="shap_composite_group_inset_mismatch",
            )
        _require_close_sequence(
            _readback_number_sequence(group_inset, "values"),
            expected_values,
            code="shap_composite_group_inset_mismatch",
            message="Origin SHAP group contributions do not match the frozen summary.",
        )
        if (
            group_inset.get("source") != plan.group_contribution_source
            or group_inset.get("label_dataset") != "__GroupLabel"
            or group_inset.get("value_dataset") != "__GroupContribution"
            or group_inset.get("color_dataset") != "__PieColor"
            or int(_readback_number(group_inset, "pid")) != 225
            or int(group_inset.get("data_labels_enabled", -1)) != 0
            or set(pie_label_theme)
            != {"values", "percentages", "categories", "custom"}
            or any(int(value) != 0 for value in pie_label_theme.values())
        ):
            raise OriginDrawError(
                "Origin SHAP group pie datasets/source do not match the frozen plan.",
                code="shap_composite_group_inset_mismatch",
            )
        expected_legend_objects = tuple(
            object_name
            for index in range(1, len(plan.group_contributions) + 1)
            for object_name in (f"SHAPGroupKey{index}", f"SHAPGroupLabel{index}")
        )
        legend_objects = group_inset.get("legend_objects")
        if (
            not isinstance(legend_objects, (list, tuple))
            or tuple(legend_objects) != expected_legend_objects
        ):
            raise OriginDrawError(
                "Origin SHAP group legend objects do not match the frozen contribution rows.",
                code="shap_composite_group_legend_mismatch",
            )
        _validate_shap_plot_binding(
            group_inset,
            expected_x="__GroupLabel",
            expected_y="__GroupContribution",
        )
        _validate_shap_template_cleanup(group_inset)


def _shap_column_letter(index: int) -> str:
    if index < 1:
        raise OriginDrawError("Origin returned an invalid SHAP worksheet column index.")
    letters = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _remove_shap_template_labels(
    layer: Any,
    *,
    keep_axis_titles: bool,
) -> dict[str, object]:
    """Remove inherited template objects and prove that none survived.

    ``_remove_label`` is intentionally forgiving for the general renderer,
    but a SHAP composite must not silently retain a template legend or axis
    title after pages are merged.  The explicit second lookup turns that
    cleanup into fail-closed readback evidence.
    """

    names = ["Legend", "legend"]
    if not keep_axis_titles:
        names.extend(("xb", "yl", "yr"))
    for name in names:
        _remove_label(layer, name)
    remaining: list[str] = []
    for name in names:
        try:
            if layer.label(name) is not None:
                remaining.append(name)
        except Exception as exc:
            raise OriginDrawError(
                f"Origin could not verify removal of SHAP template object {name!r}."
            ) from exc
    if remaining:
        raise OriginDrawError(
            "Origin retained unplanned SHAP template objects: "
            + ", ".join(remaining)
            + "."
        )
    return {
        "requested": names,
        "remaining": remaining,
        "verified": True,
    }


def _shap_layer_region_readback(
    op: Any,
    graph: Any,
    layer: Any,
    preparation: ScientificPreparation,
    region: ShapCompositeRegion,
) -> dict[str, float]:
    style = _figure_style(preparation)
    graph.activate()
    layer.activate()
    layer.set_int("unit", 1)
    layer.set_float("left", region.left_percent)
    layer.set_float("top", region.top_percent)
    layer.set_float("width", region.width_percent)
    layer.set_float("height", region.height_percent)
    layer.set_int("fixed", style.layer_fixed)
    layer.set_float("factor", style.layer_factor)
    if not layer.obj.LT_execute(
        "layer.unit=1;"
        f"layer.left={region.left_percent:g};"
        f"layer.top={region.top_percent:g};"
        f"layer.width={region.width_percent:g};"
        f"layer.height={region.height_percent:g};"
        f"layer.fixed={int(style.layer_fixed)};"
        f"layer.factor={style.layer_factor:g};doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the frozen SHAP layer geometry.")
    try:
        readback = verify_page_and_layer(
            graph,
            layer,
            origin=op,
            style=style,
            expected_layer={
                "left_percent": region.left_percent,
                "top_percent": region.top_percent,
                "width_percent": region.width_percent,
                "height_percent": region.height_percent,
            },
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return {
        key: float(readback[key])
        for key in (
            "left_percent",
            "top_percent",
            "width_percent",
            "height_percent",
        )
    }


def _build_shap_scatter_page(
    op: Any,
    sheet: Any,
    preparation: ScientificPreparation,
) -> Any:
    graph = op.new_graph("SHAPScatter", template="Scatter")
    if graph is None:
        raise OriginDrawError("Origin could not create the SHAP scatter page.")
    layer = graph[0]
    plot = layer.add_plot(sheet, "__SHAP_Y", "__SHAP_X", type="s")
    if plot is None:
        raise OriginDrawError("Origin could not create the editable SHAP scatter object.")
    marker_size = preparation.plot_spec.display_plan.marker_size_pt
    plot.set_cmd("-k 2", "-kf 0", f"-z {marker_size:g}", "-kh 20")
    color_index = sheet.lt_col_index("__FeatureValueNormalized")
    color_range = f"{sheet.lt_range(False)}!col({color_index})"
    plot_range = plot.lt_range()
    graph.activate()
    layer.activate()
    if not layer.obj.LT_execute(
        f"range __shap_scatter={plot_range};"
        f"range __shap_color={color_range};"
        "set __shap_scatter -csem __shap_color;"
        "set __shap_scatter -csfm __shap_color;"
        "doc -uw;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP dataset color route.")
    plot.colormap = "RedWhiteBlue.PAL"
    layer.rescale()
    if not layer.obj.LT_execute(
        "layer.cmap.zmin=0;layer.cmap.zmax=1;"
        "layer.cmap.numColors=101;layer.cmap.numMinorLevels=0;"
        "layer.cmap.linkpal=1;layer.cmap.stretchpal=1;"
        "layer.cmap.flippal=0;layer.cmap.SetLevels();"
        "layer.cmap.updateScale();doc -uw;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP color scale.")
    if layer.label("Spectrum1") is None and not layer.obj.LT_execute("spectrum;"):
        raise OriginDrawError("Origin could not create the associated SHAP Spectrum1 object.")
    if layer.label("Spectrum1") is None:
        raise OriginDrawError("Origin did not retain the associated SHAP Spectrum1 object.")
    return graph


def _build_shap_bar_page(op: Any, sheet: Any) -> Any:
    feature_letter = _shap_column_letter(sheet.lt_col_index("__MeanAbsFeature"))
    value_letter = _shap_column_letter(sheet.lt_col_index("__MeanAbsValue"))
    sheet.activate()
    if not op.lt_exec(
        f"plotxy iy:={sheet.lt_range(False)}!({feature_letter},{value_letter}) "
        "plot:=215 ogl:=<new template:=BAR>;"
    ):
        raise OriginDrawError("Origin rejected official horizontal Bar plot type 215.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the Mean |SHAP| bar page.")
    graph.name = "SHAPBar"
    layer = graph[0]
    layer.activate()
    if (
        int(layer.get_int("plot.pid")) != 215
        or int(layer.get_int("exchangexy")) != 1
        or len(layer.plot_list()) != 1
    ):
        raise OriginDrawError("Origin Mean |SHAP| bar primitive failed PID/orientation readback.")
    return graph


def _build_shap_pie_page(
    op: Any,
    sheet: Any,
    plan: ShapCompositePlan,
) -> Any:
    colors = interpolate_hex_colors(
        SHAP_GROUP_COLORS[0],
        SHAP_GROUP_COLORS[-1],
        len(plan.group_contributions),
    )
    color_codes = [int(op.ocolor(color)) for color in colors]
    color_column_index = len(sheet.to_df().columns)
    sheet.from_list(
        color_column_index,
        color_codes,
        lname="__PieColor",
        axis="N",
    )
    graph = op.new_graph("SHAPPie", template="Pie2D")
    if graph is None:
        raise OriginDrawError("Origin could not create the official SHAP Pie2D page.")
    layer = graph[0]
    label_letter = _shap_column_letter(sheet.lt_col_index("__GroupLabel"))
    value_letter = _shap_column_letter(sheet.lt_col_index("__GroupContribution"))
    plot = layer.add_plot(
        f"{sheet.lt_range(False)}!({label_letter},{value_letter})",
        type="?",
    )
    if plot is None:
        raise OriginDrawError("Origin could not add the SHAP group-contribution pie.")
    color_range = f"{sheet.lt_range(False)}!col({sheet.lt_col_index('__PieColor')})"
    if not layer.obj.LT_execute(
        f"range __shap_pie={plot.lt_range()};"
        f"range __shap_pie_colors={color_range};"
        "set __shap_pie -cue 1;set __shap_pie -cuf __shap_pie_colors;doc -uw;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP pie color-list route.")
    layer.rescale()
    layer.activate()
    if int(layer.get_int("plot.pid")) != 225 or len(layer.plot_list()) != 1:
        raise OriginDrawError("Origin SHAP pie primitive failed PID/count readback.")
    return graph


def _merge_shap_pages(op: Any, pages: list[Any]) -> Any:
    if len(pages) == 1:
        pages[0].name = "SHAPComposite"
        return pages[0]
    graph_expression = "+char(10)$+".join(f'"{page.name}"' for page in pages)
    if not op.lt_exec(
        "merge_graph option:=specified "
        f"graphs:={graph_expression} keep:=1 arrange:=0 row:=1 col:={len(pages)} "
        "groupgraph:=1 linkarrange:=0 labeltext:=none;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP merge_graph route.")
    graph = op.find_graph()
    if graph is None or len(graph) != len(pages):
        raise OriginDrawError("Origin SHAP composite layer count failed after merge_graph.")
    graph.name = "SHAPComposite"
    return graph


def _shap_layers_by_role(
    graph: Any,
    plan: ShapCompositePlan,
) -> dict[str, tuple[int, Any]]:
    role_by_pid = {
        201: "shap_beeswarm",
        215: "shap_mean_abs",
        225: "shap_group_contribution",
    }
    resolved: dict[str, tuple[int, Any]] = {}
    for index, layer in enumerate(graph, start=1):
        layer.activate()
        plots = list(layer.plot_list())
        if len(plots) != 1:
            raise OriginDrawError("Every SHAP composite layer must contain exactly one plot.")
        pid = int(layer.get_int("plot.pid"))
        role = role_by_pid.get(pid)
        if role is None or role in resolved:
            raise OriginDrawError(f"Origin SHAP composite contains unexpected plot PID {pid}.")
        resolved[role] = (index, layer)
    expected = {"shap_beeswarm"}
    if plan.profile != "beeswarm_only":
        expected.add("shap_mean_abs")
    if plan.profile == "beeswarm_mean_abs_grouped":
        expected.add("shap_group_contribution")
    if set(resolved) != expected:
        raise OriginDrawError("Origin SHAP composite layer roles do not match the selected profile.")
    return resolved


def _link_shap_mean_layer(
    op: Any,
    graph: Any,
    *,
    scatter_index: int,
    mean_index: int,
    scatter_layer: Any,
) -> dict[str, object]:
    """Link beeswarm geometry to the behind-the-data Mean-|SHAP| layer.

    ``laylink`` is the verified, documented route used by the Origin probe.
    Origin requires the parent to have the smaller layer index.  The Mean
    layer therefore remains layer 1 (behind the symbols) and controls only the
    shared page geometry; X and Y scales remain independent.  The child
    beeswarm layer's ``link`` property is then read back so the renderer does
    not infer success merely from a truthy X-Function return value.
    """

    graph.activate()
    if not op.lt_exec(
        f"laylink igp:={graph.name} igl:={mean_index} "
        f"destlayers:={scatter_index} XAxis:=0 YAxis:=0 unit:=page;"
    ):
        raise OriginDrawError("Origin could not link the Mean |SHAP| overlay layer.")
    scatter_layer.activate()
    parent_layer = int(scatter_layer.get_int("link"))
    unit = int(scatter_layer.get_int("unit"))
    if parent_layer != mean_index:
        raise OriginDrawError(
            "Origin beeswarm overlay is not linked to the Mean |SHAP| geometry layer."
        )
    if unit != 1:
        raise OriginDrawError(
            "Origin Mean |SHAP| overlay did not retain percent-of-page geometry units."
        )
    return {
        "parent_layer": parent_layer,
        "expected_parent_layer": mean_index,
        "child_layer": scatter_index,
        "expected_child_layer": scatter_index,
        "parent_role": "shap_mean_abs",
        "child_role": "shap_beeswarm",
        "unit": unit,
        "expected_unit": 1,
        "requested_x_axis_link": 0,
        "requested_y_axis_link": 0,
        "verified": True,
    }


def _shap_sheet_pairs(
    sheet_frame: pd.DataFrame,
    label_column: str,
    value_column: str,
) -> tuple[tuple[str, ...], tuple[float, ...]]:
    mask = sheet_frame[label_column].notna() & sheet_frame[value_column].notna()
    labels = tuple(str(value) for value in sheet_frame.loc[mask, label_column])
    values = tuple(float(value) for value in sheet_frame.loc[mask, value_column])
    return labels, values


def _shap_explicit_plot_range(graph: Any, layer_index: int) -> str:
    if layer_index < 1:
        raise OriginDrawError("Origin returned an invalid SHAP graph-layer index.")
    return f"[{graph.name}]{layer_index}!1"


def _shap_origin_dataset_name(sheet: Any, column: str) -> str:
    sheet_range = str(sheet.lt_range(False))
    if "]" not in sheet_range:
        raise OriginDrawError("Origin SHAP helper worksheet has an invalid LT range.")
    book_name = sheet_range.split("]", 1)[0].lstrip("[")
    if not book_name:
        raise OriginDrawError("Origin SHAP helper workbook name is missing.")
    letter = _shap_column_letter(sheet.lt_col_index(column))
    return f"{book_name}_{letter}"


def _shap_binding_identity_matches(component: Mapping[str, object]) -> bool:
    """Return whether two Origin range spellings resolve to one dataset.

    Origin may serialize an identical worksheet column as either a named
    sheet/column range (for example ``[Book]Sheet!A\"Long Name\"``) or a
    numeric worksheet/``col(n)`` range.  The documented ``nameof(range)$``
    result and point count are therefore the canonical binding evidence;
    both textual ranges remain required and are retained for diagnostics.
    """

    actual_range = str(component.get("actual_range", ""))
    expected_range = str(component.get("expected_range", ""))
    actual_dataset = str(component.get("actual_dataset", ""))
    expected_dataset = str(component.get("expected_dataset", ""))
    try:
        actual_count = int(component["actual_count"])
        expected_count = int(component["expected_count"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        bool(actual_range)
        and bool(expected_range)
        and bool(actual_dataset)
        and bool(expected_dataset)
        and actual_dataset == expected_dataset
        and actual_count == expected_count
    )


def _read_shap_plot_binding(
    op: Any,
    layer: Any,
    graph_plot_range: str,
    sheet: Any,
    label_column: str,
    value_column: str,
    *,
    prefix: str,
) -> dict[str, object]:
    """Read merged plot X/Y source columns through official graph ranges."""

    result: dict[str, object] = {"plot_range": graph_plot_range}
    for designation, switch, column in (
        ("x", "-wx", label_column),
        ("y", "-wy", value_column),
    ):
        index = sheet.lt_col_index(column)
        variable = f"__s{prefix}{designation}"
        actual_range = f"{variable}a"
        expected_range = f"{variable}e"
        actual_string = f"{variable}as"
        expected_string = f"{variable}es"
        actual_dataset = f"{variable}ad"
        expected_dataset = f"{variable}ed"
        actual_count = f"{variable}ac"
        expected_count = f"{variable}ec"
        if not layer.obj.LT_execute(
            f"range {switch} {actual_range}={graph_plot_range};"
            f"range {expected_range}={sheet.lt_range(False)}!col({index});"
            f"string {actual_string}$=%({actual_range});"
            f"string {expected_string}$=%({expected_range});"
            f"string {actual_dataset}$=nameof({actual_range})$;"
            f"string {expected_dataset}$=nameof({expected_range})$;"
            f"{actual_count}=count({actual_range},1);"
            f"{expected_count}=count({expected_range},1);"
        ):
            raise OriginDrawError(
                f"Origin could not read merged SHAP {designation.upper()} worksheet binding."
            )
        component: dict[str, object] = {
            "helper_column": column,
            "helper_column_index": index,
            "actual_range": str(op.get_lt_str(actual_string)),
            "expected_range": str(op.get_lt_str(expected_string)),
            "actual_dataset": str(op.get_lt_str(actual_dataset)),
            "expected_dataset": str(op.get_lt_str(expected_dataset)),
            "actual_count": int(round(float(op.lt_float(actual_count)))),
            "expected_count": int(round(float(op.lt_float(expected_count)))),
        }

        if not _shap_binding_identity_matches(component):
            raise OriginDrawError(
                "Origin merged SHAP plot is not bound to its planned worksheet "
                f"{designation.upper()} column: {component!r}."
            )
        result[designation] = component
    return result


def _add_shap_page_label(
    op: Any,
    graph: Any,
    layer: Any,
    *,
    name: str,
    text: str,
    center_x_percent: float,
    center_y_percent: float,
    size_pt: float,
    font_family: str,
    bold: bool,
    rotation_deg: float = 0.0,
    color: str = "#20262B",
) -> tuple[Any, dict[str, float | int | str]]:
    label = layer.add_label(text)
    if label is None:
        raise OriginDrawError(f"Origin could not create SHAP text object {name!r}.")
    label.name = name
    label.set_int("attach", 1)
    _style_label(label, size_pt, bold=bold)
    label.set_int("font", _origin_font_code(op, font_family))
    label.set_float("rotate", rotation_deg)
    label.color = op.ocolor(color)
    graph.activate()
    layer.activate()
    op.lt_exec("doc -uw;")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    width = float(label.get_float("width"))
    height = float(label.get_float("height"))
    padding_x = page_width * 0.004
    padding_y = page_height * 0.004
    target_left = page_width * center_x_percent / 100.0 - width / 2.0
    target_top = page_height * center_y_percent / 100.0 - height / 2.0
    label.set_float(
        "left",
        min(max(target_left, padding_x), page_width - width - padding_x),
    )
    label.set_float(
        "top",
        min(max(target_top, padding_y), page_height - height - padding_y),
    )
    op.lt_exec("doc -uw;")
    if layer.label(name) is None:
        raise OriginDrawError(f"Origin did not retain SHAP text object {name!r}.")
    try:
        text_state: dict[str, float | int | str] = {
            **verify_text_sizes({name: label}, {name: size_pt}),
            **verify_text_fonts(op, {name: label}, font_family),
        }
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    actual_left = float(label.get_float("left"))
    actual_top = float(label.get_float("top"))
    actual_width = float(label.get_float("width"))
    actual_height = float(label.get_float("height"))
    actual_attach = int(label.get_int("attach"))
    actual_rotation = float(label.get_float("rotate"))
    if (
        actual_left < 0.0
        or actual_top < 0.0
        or actual_left + actual_width > page_width
        or actual_top + actual_height > page_height
    ):
        raise OriginDrawError(f"Origin SHAP text object {name!r} is clipped by the page.")
    if str(label.text) != text:
        raise OriginDrawError(f"Origin changed SHAP text object {name!r}.")
    if actual_attach != 1:
        raise OriginDrawError(
            f"Origin SHAP text object {name!r} is not attached to the graph page."
        )
    if not math.isclose(actual_rotation, rotation_deg, rel_tol=0.0, abs_tol=0.1):
        raise OriginDrawError(
            f"Origin SHAP text object {name!r} changed its planned rotation."
        )
    text_state.update(
        {
            f"{name}.text": text,
            f"{name}.attach": actual_attach,
            f"{name}.rotate": actual_rotation,
            f"{name}.left": actual_left,
            f"{name}.top": actual_top,
            f"{name}.width": actual_width,
            f"{name}.height": actual_height,
        }
    )
    return label, text_state


def _read_shap_scatter_mapping(
    op: Any,
    graph: Any,
    layer_index: int,
    layer: Any,
    sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[dict[str, Any], dict[str, float]]:
    plot_range = _shap_explicit_plot_range(graph, layer_index)
    graph.activate()
    layer.activate()
    plots = list(layer.plot_list())
    if len(plots) != 1:
        raise OriginDrawError("Origin SHAP beeswarm must contain exactly one scatter plot.")
    plot = plots[0]
    # ``merge_graph`` may rescale plot elements even when the destination page
    # geometry is restored afterwards.  Re-apply the frozen symbol contract on
    # the merged plot and let ``verify_symbol_style`` independently read it
    # back below; accepting the merge-time scale factor would make composite
    # profiles visibly inconsistent with ``beeswarm_only``.
    marker_size = preparation.plot_spec.display_plan.marker_size_pt
    plot.set_cmd("-k 2", "-kf 0", f"-z {marker_size:g}", "-kh 20")
    # Re-apply the planned palette after merge, then use OriginPro's public
    # colormap getter as the actual palette readback.  This avoids claiming
    # color semantics from a pre-merge assignment that Origin may discard.
    plot.colormap = "RedWhiteBlue.PAL"
    if not layer.obj.LT_execute(
        "layer.cmap.zmin=0;layer.cmap.zmax=1;"
        "layer.cmap.numColors=101;layer.cmap.numMinorLevels=0;"
        "layer.cmap.linkpal=1;layer.cmap.stretchpal=1;"
        "layer.cmap.flippal=0;layer.cmap.SetLevels();"
        "layer.cmap.updateScale();"
        f"range __shap_final_scatter={plot_range};"
        "get __shap_final_scatter -cseo __shap_edge_mode;"
        "get __shap_final_scatter -csem __shap_edge_dataset$;"
        "get __shap_final_scatter -csfo __shap_fill_mode;"
        "get __shap_final_scatter -csfm __shap_fill_dataset$;"
        "doc -uw;"
    ):
        raise OriginDrawError("Origin could not read the merged SHAP color binding.")
    edge_mode = int(round(float(op.lt_float("__shap_edge_mode"))))
    fill_mode = int(round(float(op.lt_float("__shap_fill_mode"))))
    edge_dataset = str(op.get_lt_str("__shap_edge_dataset"))
    fill_dataset = str(op.get_lt_str("__shap_fill_dataset"))
    expected_dataset = _shap_origin_dataset_name(sheet, "__FeatureValueNormalized")
    minimum = float(layer.get_float("cmap.zmin"))
    maximum = float(layer.get_float("cmap.zmax"))
    palette_flipped = float(layer.get_float("cmap.flippal"))
    level_count = int(round(float(layer.get_float("cmap.numColors"))))
    minor_level_count = int(round(float(layer.get_float("cmap.numMinorLevels"))))
    palette_linked = int(round(float(layer.get_float("cmap.linkpal"))))
    palette_stretched = int(round(float(layer.get_float("cmap.stretchpal"))))
    actual_palette = str(plot.colormap)
    palette_matches = actual_palette.casefold() == "redwhiteblue.pal".casefold()
    if (
        edge_mode != 2
        or fill_mode != 2
        or edge_dataset != expected_dataset
        or fill_dataset != expected_dataset
        or not math.isclose(minimum, 0.0, abs_tol=0.01)
        or not math.isclose(maximum, 1.0, abs_tol=0.01)
        or not math.isclose(palette_flipped, 0.0, abs_tol=0.05)
        or level_count != 101
        or minor_level_count != 0
        or palette_linked != 1
        or palette_stretched != 1
        or not palette_matches
    ):
        raise OriginDrawError(
            "Origin merged SHAP scatter failed its dataset color-scale readback."
        )
    try:
        symbol_state = verify_symbol_style(
            op,
            plot,
            expected_size_pt=preparation.plot_spec.display_plan.marker_size_pt,
            expected_edge_percent=20.0,
            expected_symbol_kind=2,
            expected_symbol_interior=0,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return (
        {
            "present": True,
            "dataset": "__FeatureValueNormalized",
            "associated_object": "Spectrum1",
            "edge_mode": edge_mode,
            "fill_mode": fill_mode,
            "edge_dataset": "__FeatureValueNormalized",
            "fill_dataset": "__FeatureValueNormalized",
            "edge_dataset_readback": edge_dataset,
            "fill_dataset_readback": fill_dataset,
            "expected_dataset": expected_dataset,
            "minimum": minimum,
            "maximum": maximum,
            "direction": "pending_spectrum_readback",
            "palette_flipped": palette_flipped,
            "level_count": level_count,
            "minor_level_count": minor_level_count,
            "palette_linked": palette_linked,
            "palette_stretched": palette_stretched,
            "palette": actual_palette,
            "palette_expected": "RedWhiteBlue.PAL",
            "palette_readback_verified": palette_matches,
            "semantic_color_endpoints": list(SHAP_FEATURE_VALUE_COLORS),
            "plot_range": plot_range,
        },
        symbol_state,
    )


def _style_shap_scatter_layer(
    op: Any,
    graph: Any,
    layer_index: int,
    layer: Any,
    sheet: Any,
    preparation: ScientificPreparation,
    region: ShapCompositeRegion,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any], dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    graph.activate()
    layer.activate()
    layer.rescale()
    geometry_state = _shap_layer_region_readback(
        op,
        graph,
        layer,
        preparation,
        region,
    )
    _style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=False)
    _clean_numeric_x_axis(op, graph)
    layer.axis("x").set_limits(
        spec.axis_plan.x_from,
        spec.axis_plan.x_to,
        spec.axis_plan.x_step,
    )
    layer.axis("y").set_limits(
        spec.axis_plan.y_from,
        spec.axis_plan.y_to,
        spec.axis_plan.y_step,
    )
    label_range = f"{sheet.lt_range(False)}!col({sheet.lt_col_index('__FeatureLabel')})"
    if not layer.obj.LT_execute(
        f"range __shap_labels={label_range};axis -ps Y T __shap_labels;"
    ):
        raise OriginDrawError("Origin could not bind SHAP feature labels.")
    layer.set_int("y.minorTicks", 0)
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    if int(layer.get_int("y.label.type")) != 2:
        raise OriginDrawError("Origin did not keep SHAP text labels on the Y axis.")

    graph.activate()
    layer.activate()
    if not op.lt_exec(
        f"addline type:=0 value:=0 color:=color({SHAP_ZERO_LINE_COLOR}) "
        "style:=1 select:=1 move:=1 name:=SHAPZero;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP zero reference line.")
    _remove_label(layer, "SHAPZeroText")
    reference_state = {
        "present": layer.label("SHAPZero") is not None,
        "text_present": layer.label("SHAPZeroText") is not None,
        "value": 0.0,
        "color": SHAP_ZERO_LINE_COLOR,
    }
    if not reference_state["present"] or reference_state["text_present"]:
        raise OriginDrawError("Origin SHAP zero reference line verification failed.")

    template_cleanup_state = _remove_shap_template_labels(
        layer,
        keep_axis_titles=False,
    )
    labels, title_state, text_state = _style_titles(
        op,
        graph,
        layer,
        preparation,
        keep_y_title=False,
    )
    axis_state = _validate_axes(op, layer, preparation)
    colorbar_state, symbol_state = _read_shap_scatter_mapping(
        op,
        graph,
        layer_index,
        layer,
        sheet,
        preparation,
    )
    plot_binding = _read_shap_plot_binding(
        op,
        layer,
        _shap_explicit_plot_range(graph, layer_index),
        sheet,
        "__SHAP_X",
        "__SHAP_Y",
        prefix="s",
    )
    return (
        geometry_state,
        {
            "pid": 201,
            "axis": axis_state,
            "reference": reference_state,
            "symbol": symbol_state,
            "color_mapping": colorbar_state,
            "plot_binding": plot_binding,
            "template_cleanup": template_cleanup_state,
        },
        {
            **text_state,
            **title_state,
            "title_objects": list(labels),
        },
        colorbar_state,
    )


def _position_shap_spectrum(
    op: Any,
    graph: Any,
    layer: Any,
    preparation: ScientificPreparation,
    region: ShapCompositeRegion,
) -> tuple[dict[str, float], dict[str, Any]]:
    style = _figure_style(preparation)
    graph.activate()
    layer.activate()
    spectrum = layer.label("Spectrum1")
    if spectrum is None:
        raise OriginDrawError("Origin SHAP Spectrum1 object disappeared after merge.")
    if not layer.obj.LT_execute(
        "spectrum1.show=1;spectrum1.attach=1;spectrum1.revorder=1;"
        "spectrum1.labels.autodisp=0;"
        "spectrum1.labels.show=0;"
        "spectrum1.levels.major=3;"
        "spectrum1.levels.from=0;spectrum1.levels.to=1;"
        "spectrum1.levels.inc=0;spectrum1.levels.majorticks=2;"
        "spectrum1.levels.minorticks=0;"
        "spectrum1.labels.numdisp=6;spectrum1.labels.cusfmt$=\" \";"
        f"spectrum1.labels.fsize={style.tick_label_size_pt:g};"
        "spectrum1.labels.bold=0;"
        f"spectrum1.labels.font=font({style.font_family});"
        "spectrum1.barthick=100;doc -uw;"
    ):
        raise OriginDrawError("Origin could not style the associated SHAP Spectrum1 object.")
    # Spectrum1 is a specialized graph object.  Its ordinary left/top setters
    # are overwritten by the color-scale anchor during a window refresh.  The
    # Origin color-scale Position controls are stored in the object Theme as
    # Dimension.Units/PosX/PosY/PosAlignment.  Unit 7 is "% of Page" and
    # anchor 1 is Left-Top; setting the matching Dimension rectangle makes the
    # editable object and the frozen preview geometry agree after refresh.
    try:
        theme = spectrum.obj.GetTheme()
        dimension = theme.Dimension
        dimension.Units.SetIntValue(7)
        dimension.PosX.SetDoubleValue(region.left_percent)
        dimension.PosY.SetDoubleValue(region.top_percent)
        dimension.PosAlignment.SetIntValue(1)
        dimension.Left.SetDoubleValue(region.left_percent)
        dimension.Top.SetDoubleValue(region.top_percent)
        dimension.Width.SetDoubleValue(region.width_percent)
        dimension.Height.SetDoubleValue(region.height_percent)
        theme.Layout.Background.SetIntValue(0)
        theme.Layout.LayoutStyle.SetIntValue(0)
        theme.Extends.HideHeadLevel.SetIntValue(1)
        theme.Extends.HideTailLevel.SetIntValue(1)
        # OriginExt returns False for this specialized object even when the
        # theme is applied.  The authoritative gate is the independent theme
        # plus LabTalk geometry readback below, not this legacy return value.
        spectrum.obj.PutTheme(theme)
    except Exception as exc:
        raise OriginDrawError(
            "Origin could not apply the SHAP Spectrum1 page-position theme."
        ) from exc
    if not op.lt_exec("doc -uw;"):
        raise OriginDrawError("Origin could not refresh the positioned SHAP Spectrum1 object.")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    actual = {
        "left_percent": float(op.lt_float("spectrum1.left")) / page_width * 100.0,
        "top_percent": float(op.lt_float("spectrum1.top")) / page_height * 100.0,
        "width_percent": float(op.lt_float("spectrum1.width")) / page_width * 100.0,
        "height_percent": float(op.lt_float("spectrum1.height")) / page_height * 100.0,
    }
    expected = region.to_dict()
    if any(
        abs(actual[field] - expected[field]) > LAYER_GEOMETRY_TOLERANCE_PERCENT
        for field in expected
    ):
        raise OriginDrawError(
            "Origin SHAP Spectrum1 geometry does not match the frozen region: "
            f"actual={actual!r}, expected={expected!r}."
        )
    try:
        positioned_theme = spectrum.obj.GetTheme()
        positioned_dimension = positioned_theme.Dimension
        theme_position_state = {
            "Spectrum1.position_units": int(positioned_dimension.Units.GetIntValue()),
            "Spectrum1.theme_attachment": int(
                positioned_dimension.Attachment.GetIntValue()
            ),
            "Spectrum1.position_x_percent": float(
                positioned_dimension.PosX.GetDoubleValue()
            ),
            "Spectrum1.position_y_percent": float(
                positioned_dimension.PosY.GetDoubleValue()
            ),
            "Spectrum1.position_anchor": int(
                positioned_dimension.PosAlignment.GetIntValue()
            ),
            "Spectrum1.background": int(
                positioned_theme.Layout.Background.GetIntValue()
            ),
            "Spectrum1.layout_style": int(
                positioned_theme.Layout.LayoutStyle.GetIntValue()
            ),
            "Spectrum1.hide_head_level": int(
                positioned_theme.Extends.HideHeadLevel.GetIntValue()
            ),
            "Spectrum1.hide_tail_level": int(
                positioned_theme.Extends.HideTailLevel.GetIntValue()
            ),
        }
    except Exception as exc:
        raise OriginDrawError(
            "Origin could not read back the SHAP Spectrum1 page-position theme."
        ) from exc
    spectrum_state = {
        "Spectrum1.show": float(op.lt_float("spectrum1.show")),
        "Spectrum1.attach": float(op.lt_float("spectrum1.attach")),
        "Spectrum1.revorder": float(op.lt_float("spectrum1.revorder")),
        "Spectrum1.labels_show": float(op.lt_float("spectrum1.labels.show")),
        "Spectrum1.levels_major": float(op.lt_float("spectrum1.levels.major")),
        "Spectrum1.levels_from": float(op.lt_float("spectrum1.levels.from")),
        "Spectrum1.levels_to": float(op.lt_float("spectrum1.levels.to")),
        "Spectrum1.levels_increment_mode": float(
            op.lt_float("spectrum1.levels.inc")
        ),
        "Spectrum1.levels_major_ticks": float(
            op.lt_float("spectrum1.levels.majorticks")
        ),
        "Spectrum1.levels_minor_ticks": float(
            op.lt_float("spectrum1.levels.minorticks")
        ),
        "Spectrum1.label_display_type": float(
            op.lt_float("spectrum1.labels.numdisp")
        ),
        "Spectrum1.label_custom_format": str(
            op.get_lt_str("spectrum1.labels.cusfmt$")
        ),
        "Spectrum1.label_size_pt": float(op.lt_float("spectrum1.labels.fsize")),
        "Spectrum1.label_font_code": int(
            round(float(op.lt_float("spectrum1.labels.font")))
        ),
        "Spectrum1.font_code_expected": _origin_font_code(op, style.font_family),
        **theme_position_state,
    }
    if (
        int(round(float(spectrum_state["Spectrum1.show"]))) != 1
        or int(round(float(spectrum_state["Spectrum1.attach"]))) != 1
        or int(round(float(spectrum_state["Spectrum1.revorder"]))) != 1
        or int(round(float(spectrum_state["Spectrum1.labels_show"]))) != 0
        or int(round(float(spectrum_state["Spectrum1.levels_major"]))) != 3
        or not math.isclose(
            float(spectrum_state["Spectrum1.levels_from"]),
            0.0,
            rel_tol=0.0,
            abs_tol=0.01,
        )
        or not math.isclose(
            float(spectrum_state["Spectrum1.levels_to"]),
            1.0,
            rel_tol=0.0,
            abs_tol=0.01,
        )
        or int(round(float(spectrum_state["Spectrum1.levels_increment_mode"])))
        != 0
        or int(round(float(spectrum_state["Spectrum1.levels_major_ticks"]))) != 2
        or int(round(float(spectrum_state["Spectrum1.levels_minor_ticks"]))) != 0
        or int(round(float(spectrum_state["Spectrum1.label_display_type"]))) != 6
        or str(spectrum_state["Spectrum1.label_custom_format"]) != " "
        or int(spectrum_state["Spectrum1.position_units"]) != 7
        or int(spectrum_state["Spectrum1.theme_attachment"]) != 1
        or int(spectrum_state["Spectrum1.position_anchor"]) != 1
        or int(spectrum_state["Spectrum1.background"]) != 0
        or int(spectrum_state["Spectrum1.layout_style"]) != 0
        or int(spectrum_state["Spectrum1.hide_head_level"]) != 1
        or int(spectrum_state["Spectrum1.hide_tail_level"]) != 1
        or abs(
            float(spectrum_state["Spectrum1.position_x_percent"])
            - region.left_percent
        )
        > LAYER_GEOMETRY_TOLERANCE_PERCENT
        or abs(
            float(spectrum_state["Spectrum1.position_y_percent"])
            - region.top_percent
        )
        > LAYER_GEOMETRY_TOLERANCE_PERCENT
        or abs(
            float(spectrum_state["Spectrum1.label_size_pt"])
            - style.tick_label_size_pt
        )
        > 0.05
        or int(spectrum_state["Spectrum1.label_font_code"])
        != int(spectrum_state["Spectrum1.font_code_expected"])
    ):
        raise OriginDrawError("Origin SHAP Spectrum1 text/style readback failed.")
    title_x = max(1.0, region.left_percent - 1.25)
    _title, title_state = _add_shap_page_label(
        op,
        graph,
        layer,
        name="SHAPColorbarTitle",
        text="Feature value",
        center_x_percent=title_x,
        center_y_percent=region.top_percent + region.height_percent / 2.0,
        size_pt=style.legend_size_pt,
        font_family=style.font_family,
        bold=True,
        rotation_deg=90.0,
    )
    # Keep endpoint text entirely to the right of the native bar.  Centering
    # the text too close to the bar makes the first glyph cross its border at
    # publication-size exports even though the object itself is on-page.
    endpoint_x = min(98.0, region.left_percent + region.width_percent + 2.5)
    _high, high_state = _add_shap_page_label(
        op,
        graph,
        layer,
        name="SHAPColorbarHigh",
        text="High",
        center_x_percent=endpoint_x,
        center_y_percent=region.top_percent,
        size_pt=style.tick_label_size_pt,
        font_family=style.font_family,
        bold=False,
    )
    _low, low_state = _add_shap_page_label(
        op,
        graph,
        layer,
        name="SHAPColorbarLow",
        text="Low",
        center_x_percent=endpoint_x,
        center_y_percent=region.top_percent + region.height_percent,
        size_pt=style.tick_label_size_pt,
        font_family=style.font_family,
        bold=False,
    )
    return actual, {
        **spectrum_state,
        **title_state,
        **high_state,
        **low_state,
    }


def _style_shap_mean_layer(
    op: Any,
    graph: Any,
    layer_index: int,
    layer: Any,
    sheet: Any,
    sheet_frame: pd.DataFrame,
    preparation: ScientificPreparation,
    plan: ShapCompositePlan,
    region: ShapCompositeRegion,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    style = _figure_style(preparation)
    graph.activate()
    layer.activate()
    plots = list(layer.plot_list())
    if len(plots) != 1 or int(layer.get_int("plot.pid")) != 215:
        raise OriginDrawError("Origin Mean |SHAP| layer lost its editable PID 215 bar.")
    plot = plots[0]
    plot.color = op.ocolor(SHAP_MEAN_ABS_BAR_COLOR)
    plot.set_cmd(
        f"-c color({SHAP_MEAN_ABS_BAR_COLOR})",
        f"-w {pt_to_origin_width_units(style.bar_border_width_pt)}",
    )
    layer.set_float("plot1.transparency", 58.0)
    layer.rescale()
    geometry_state = _shap_layer_region_readback(
        op,
        graph,
        layer,
        preparation,
        region,
    )
    mean_max = max((float(value) for _feature, value in plan.mean_abs_values), default=0.0)
    mean_from, mean_to, mean_step = resolve_shap_mean_axis(mean_max)
    # PID 215 has ``exchangexy=1``: Origin's X scale is the categorical
    # feature-row coordinate while Y is the Mean-|SHAP| numeric magnitude.
    # Keeping X identical to the beeswarm Y scale makes the bars line up with
    # the scatter rows; the paired Y axis becomes the physical top scale.
    layer.axis("x").set_limits(
        preparation.plot_spec.axis_plan.y_from,
        preparation.plot_spec.axis_plan.y_to,
        preparation.plot_spec.axis_plan.y_step,
    )
    layer.axis("y").set_limits(mean_from, mean_to, mean_step)
    font_code = _origin_font_code(op, style.font_family)
    _style_axis(
        layer,
        "x",
        visible=False,
        numeric_labels=False,
        minor_ticks=0,
        style=style,
        font_code=font_code,
    )
    _style_axis(
        layer,
        "y",
        visible=True,
        numeric_labels=True,
        minor_ticks=0,
        style=style,
        font_code=font_code,
    )
    layer.set_int("x.showLabels", 0)
    layer.set_int("x.showlabel", 0)
    layer.set_int("x.label.show", 0)
    layer.set_int("x.ticks", 0)
    # With exchange-XY active the Y pair is drawn horizontally.  ``2`` keeps
    # numeric labels on its physical top side only.  Do not write the known-
    # risky y2.showLabels/y2.minorTicks properties on Origin 10.15.
    layer.set_int("y.showLabels", 2)
    layer.set_int("y.showlabel", 0)
    layer.set_int("y.label.show", 0)
    layer.set_int("y.ticks", 0)
    layer.set_int("y2.showlabel", 1)
    layer.set_int("y2.label.show", 1)
    layer.set_int("y2.ticks", 5)
    layer.set_float("y2.thickness", style.frame_line_width_pt)
    layer.set_float("y2.tickthickness", style.frame_line_width_pt)
    layer.set_float("y2.ticklength", style.major_tick_length_pt)
    _apply_axis_label_font(op, layer, ("y2",), style)
    template_cleanup_state = _remove_shap_template_labels(
        layer,
        keep_axis_titles=False,
    )
    # The exchanged PID-215 numeric labels occupy the band immediately above
    # the frame.  Reserve a full tick-label band between them and the editable
    # page title instead of relying on Origin's version-dependent default axis
    # title offset.
    title_y = max(2.4, region.top_percent - 6.5)
    title, title_state = _add_shap_page_label(
        op,
        graph,
        layer,
        name="SHAPMeanTitle",
        text="Mean |SHAP value|",
        center_x_percent=region.left_percent + region.width_percent / 2.0,
        center_y_percent=title_y,
        size_pt=style.axis_title_size_pt,
        font_family=style.font_family,
        bold=True,
    )
    page_height = float(op.lt_float("page.height"))
    title_bottom_percent = (
        float(title.get_float("top")) + float(title.get_float("height"))
    ) / page_height * 100.0
    if title_bottom_percent > region.top_percent - 3.2:
        raise OriginDrawError(
            "Origin Mean |SHAP| title overlaps the top numeric tick-label band."
        )
    title_state["SHAPMeanTitle.bottom_percent"] = title_bottom_percent
    title_state["SHAPMeanTitle.maximum_bottom_percent"] = (
        region.top_percent - 3.2
    )
    try:
        color_state = verify_plot_color(
            op,
            plot,
            SHAP_MEAN_ABS_BAR_COLOR,
            variable_name="__shap_mean_bar_color",
        )
        width_state = verify_plot_line_widths(
            op,
            {"mean_abs": plot},
            style.bar_border_width_pt,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    graph_plot_range = _shap_explicit_plot_range(graph, layer_index)
    plot_binding = _read_shap_plot_binding(
        op,
        layer,
        graph_plot_range,
        sheet,
        "__MeanAbsFeature",
        "__MeanAbsValue",
        prefix="m",
    )
    native_labels, native_values = _shap_sheet_pairs(
        sheet_frame,
        "__MeanAbsFeature",
        "__MeanAbsValue",
    )
    expected_native = tuple(reversed(plan.mean_abs_values))
    if native_labels != tuple(feature for feature, _value in expected_native):
        raise OriginDrawError("Origin Mean |SHAP| helper feature order changed.")
    _require_close_sequence(
        native_values,
        tuple(float(value) for _feature, value in expected_native),
        code="shap_composite_mean_abs_mismatch",
        message="Origin Mean |SHAP| helper values changed.",
    )
    exchange_xy = int(layer.get_int("exchangexy"))
    x_from = float(layer.get_float("x.from"))
    x_to = float(layer.get_float("x.to"))
    y_from = float(layer.get_float("y.from"))
    y_to = float(layer.get_float("y.to"))
    y_step = float(layer.get_float("y.inc"))
    x_hidden = (
        int(layer.get_int("x.showLabels")) == 0
        and int(layer.get_int("x.showlabel")) == 0
        and int(layer.get_int("x.ticks")) == 0
    )
    top_axis_only = int(layer.get_int("y.showLabels")) == 2
    if exchange_xy != 1:
        raise OriginDrawError("Origin Mean |SHAP| layer lost PID 215 exchange-XY mode.")
    if not (
        math.isclose(
            x_from,
            preparation.plot_spec.axis_plan.y_from,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        and math.isclose(
            x_to,
            preparation.plot_spec.axis_plan.y_to,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        and math.isclose(y_from, mean_from, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(y_to, mean_to, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(y_step, mean_step, rel_tol=0.0, abs_tol=1e-6)
    ):
        raise OriginDrawError("Origin Mean |SHAP| exchanged-axis limits changed.")
    if not x_hidden:
        raise OriginDrawError("Origin Mean |SHAP| categorical X labels were not hidden.")
    if not top_axis_only:
        raise OriginDrawError("Origin Mean |SHAP| layer did not retain its top-only Y labels.")
    state = {
        "present": True,
        "labels": [feature for feature, _value in plan.mean_abs_values],
        "values": [float(value) for _feature, value in plan.mean_abs_values],
        "source": plan.mean_abs_source,
        "label_dataset": "__MeanAbsFeature",
        "value_dataset": "__MeanAbsValue",
        "plot_range": graph_plot_range,
        "plot_binding": plot_binding,
        "pid": 215,
        "native_row_order": list(native_labels),
        "color": color_state,
        "line_width": width_state,
        "transparency_percent": float(layer.get_float("plot1.transparency")),
        "exchange_xy": exchange_xy,
        "category_axis": "x",
        "mean_value_axis": "y",
        "category_axis_limits": [x_from, x_to],
        "mean_axis_limits": [y_from, y_to],
        "mean_axis_step": y_step,
        "category_axis_hidden": x_hidden,
        "top_axis_pair": "y",
        "top_axis_only": top_axis_only,
        "title_collision": {
            "object": "SHAPMeanTitle",
            "bottom_percent": title_bottom_percent,
            "maximum_bottom_percent": region.top_percent - 3.2,
            "verified": True,
        },
        "template_cleanup": template_cleanup_state,
    }
    return geometry_state, state, title_state


def _style_shap_group_layer(
    op: Any,
    graph: Any,
    layer_index: int,
    layer: Any,
    sheet: Any,
    sheet_frame: pd.DataFrame,
    preparation: ScientificPreparation,
    plan: ShapCompositePlan,
    region: ShapCompositeRegion,
) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    style = _figure_style(preparation)
    graph.activate()
    layer.activate()
    plots = list(layer.plot_list())
    if len(plots) != 1 or int(layer.get_int("plot.pid")) != 225:
        raise OriginDrawError("Origin SHAP group inset lost its editable PID 225 pie.")
    plot = plots[0]
    # Pie2D wedge labels use the plot's dedicated Labels theme; the generic
    # ``set -q 0`` flag can read back as disabled while percentages remain
    # visible.  Apply the verified 2024b theme nodes and gate on a fresh theme
    # readback because PutTheme() itself returns False even when successful.
    try:
        pie_theme = plot.obj.GetTheme()
        pie_theme.Labels.Values.SetIntValue(0)
        pie_theme.Labels.Percentages.SetIntValue(0)
        pie_theme.Labels.Categories.SetIntValue(0)
        pie_theme.Labels.Custom.SetIntValue(0)
        plot.obj.PutTheme(pie_theme)
        op.lt_exec("doc -uw;")
        applied_theme = plot.obj.GetTheme()
        pie_label_theme_state = {
            "values": int(applied_theme.Labels.Values.GetIntValue()),
            "percentages": int(applied_theme.Labels.Percentages.GetIntValue()),
            "categories": int(applied_theme.Labels.Categories.GetIntValue()),
            "custom": int(applied_theme.Labels.Custom.GetIntValue()),
        }
    except Exception as exc:
        raise OriginDrawError(
            "Origin could not apply or read back the SHAP Pie2D label theme."
        ) from exc
    if any(value != 0 for value in pie_label_theme_state.values()):
        raise OriginDrawError("Origin SHAP Pie2D wedge labels remained enabled.")
    data_labels_enabled = 0
    geometry_state = _shap_layer_region_readback(
        op,
        graph,
        layer,
        preparation,
        region,
    )
    template_cleanup_state = _remove_shap_template_labels(
        layer,
        keep_axis_titles=False,
    )
    for axis_name in ("x", "y"):
        layer.set_int(f"{axis_name}.showAxes", 0)
        layer.set_int(f"{axis_name}.showLabels", 0)
        layer.set_int(f"{axis_name}.ticks", 0)
        layer.set_int(f"{axis_name}.minorTicks", 0)

    colors = interpolate_hex_colors(
        SHAP_GROUP_COLORS[0],
        SHAP_GROUP_COLORS[-1],
        len(plan.group_contributions),
    )
    expected_codes = [float(op.ocolor(color)) for color in colors]
    plot_range = _shap_explicit_plot_range(graph, layer_index)
    if not layer.obj.LT_execute(
        f"range __shap_final_pie={plot_range};"
        "dataset __shap_final_pie_colors;"
        "get __shap_final_pie -cue __shap_final_pie_cue;"
        "get __shap_final_pie -cuf __shap_final_pie_colors;doc -uw;"
    ):
        raise OriginDrawError("Origin could not read back SHAP pie colors after merge.")
    cue_state = float(op.lt_float("__shap_final_pie_cue"))
    actual_codes = [
        float(op.lt_float(f"__shap_final_pie_colors[{index}]"))
        for index in range(1, len(expected_codes) + 1)
    ]
    if data_labels_enabled != 0 or int(round(cue_state)) != 1 or any(
        abs(actual - expected) > 0.5
        for actual, expected in zip(actual_codes, expected_codes, strict=True)
    ):
        raise OriginDrawError("Origin SHAP pie color-list readback changed after merge.")
    plot_binding = _read_shap_plot_binding(
        op,
        layer,
        plot_range,
        sheet,
        "__GroupLabel",
        "__GroupContribution",
        prefix="g",
    )

    title_y = max(1.0, region.top_percent - 1.25)
    _title, title_state = _add_shap_page_label(
        op,
        graph,
        layer,
        name="SHAPGroupTitle",
        text="Relative contribution",
        center_x_percent=region.left_percent + region.width_percent / 2.0,
        center_y_percent=title_y,
        size_pt=style.inset_axis_title_size_pt,
        font_family=style.font_family,
        bold=True,
    )
    # Origin rewrites embedded newlines in a single label object.  Use one
    # editable key and one plain-text label per group so text round-trips
    # exactly and users can move individual legend rows after delivery.
    legend_state: dict[str, float | int | str] = {}
    legend_objects: list[str] = []
    legend_left = region.left_percent + region.width_percent + 2.0
    row_count = len(plan.group_contributions)
    for index, ((group, value), color) in enumerate(
        zip(plan.group_contributions, colors, strict=True),
        start=1,
    ):
        center_y = region.top_percent + region.height_percent * index / (row_count + 1)
        key_name = f"SHAPGroupKey{index}"
        label_name = f"SHAPGroupLabel{index}"
        _key, key_state = _add_shap_page_label(
            op,
            graph,
            layer,
            name=key_name,
            text="■",
            center_x_percent=legend_left + 0.65,
            center_y_percent=center_y,
            size_pt=style.inset_tick_label_size_pt,
            font_family=style.font_family,
            bold=False,
            color=color,
        )
        _label, label_state = _add_shap_page_label(
            op,
            graph,
            layer,
            name=label_name,
            text=f"{' '.join(str(group).split())}  {float(value):.1f}%",
            center_x_percent=legend_left + 6.2,
            center_y_percent=center_y,
            size_pt=style.inset_tick_label_size_pt,
            font_family=style.font_family,
            bold=False,
        )
        legend_state.update(key_state)
        legend_state.update(label_state)
        legend_objects.extend((key_name, label_name))
    observed_labels, observed_values = _shap_sheet_pairs(
        sheet_frame,
        "__GroupLabel",
        "__GroupContribution",
    )
    expected_labels = tuple(group for group, _value in plan.group_contributions)
    expected_values = tuple(float(value) for _group, value in plan.group_contributions)
    if observed_labels != expected_labels:
        raise OriginDrawError("Origin SHAP group helper order changed.")
    _require_close_sequence(
        observed_values,
        expected_values,
        code="shap_composite_group_inset_mismatch",
        message="Origin SHAP group contribution helper values changed.",
    )
    state = {
        "present": True,
        "labels": list(observed_labels),
        "values": list(observed_values),
        "source": plan.group_contribution_source,
        "label_dataset": "__GroupLabel",
        "value_dataset": "__GroupContribution",
        "color_dataset": "__PieColor",
        "pid": 225,
        "plot_range": plot_range,
        "plot_binding": plot_binding,
        "colors": list(colors),
        "color_codes": actual_codes,
        "custom_increment_enabled": cue_state,
        "data_labels_enabled": data_labels_enabled,
        "label_theme": pie_label_theme_state,
        "legend_objects": legend_objects,
        "template_cleanup": template_cleanup_state,
    }
    return geometry_state, state, {**title_state, **legend_state}


def _build_shap_summary_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    plan = spec.shap_plan
    style = _figure_style(preparation)
    if plan is None:
        raise OriginDrawError(
            "The frozen SHAP composite plan is missing.",
            code="shap_composite_plan_missing",
        )
    try:
        geometry = resolve_shap_composite_geometry(plan.profile, style)
    except ValueError as exc:
        raise OriginDrawError(
            str(exc),
            code="shap_composite_geometry_invalid",
        ) from exc
    if geometry.layout_version != plan.layout_version:
        raise OriginDrawError(
            "The SHAP composite layout version does not match the frozen plan.",
            code="shap_composite_layout_version_mismatch",
        )

    source_snapshot = frame.copy(deep=True)
    _source_sheet(op, frame, preparation)
    plot_frame, _planned_helpers = build_shap_composite_helper_frame(frame, preparation)
    sheet = op.new_sheet("w", "SHAP Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the SHAP helper worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis()

    scatter_page = _build_shap_scatter_page(op, sheet, preparation)
    bar_page = _build_shap_bar_page(op, sheet) if plan.profile != "beeswarm_only" else None
    pie_page = (
        _build_shap_pie_page(op, sheet, plan)
        if plan.profile == "beeswarm_mean_abs_grouped"
        else None
    )
    pages = [page for page in (bar_page, scatter_page, pie_page) if page is not None]
    graph = _merge_shap_pages(op, pages)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    page_width_in, page_height_in = page_size_inches(style)
    graph.activate()
    if not graph.obj.LT_execute(
        "page.updatetoprinter=0;page.kar=0;"
        f"page.width=({page_width_in:g})*page.resx;"
        f"page.height=({page_height_in:g})*page.resy;doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the SHAP composite physical page size.")
    layers = _shap_layers_by_role(graph, plan)
    scatter_layer_index = layers["shap_beeswarm"][0]
    if (
        plan.profile != "beeswarm_only"
        and layers["shap_mean_abs"][0] >= scatter_layer_index
    ):
        raise OriginDrawError(
            "Origin SHAP layer order is invalid: Mean |SHAP| bars must remain behind the beeswarm."
        )
    if (
        plan.profile == "beeswarm_mean_abs_grouped"
        and layers["shap_group_contribution"][0] <= scatter_layer_index
    ):
        raise OriginDrawError(
            "Origin SHAP layer order is invalid: the group inset must remain above the beeswarm."
        )
    if plan.profile != "beeswarm_only":
        mean_layer_index = layers["shap_mean_abs"][0]
        scatter_layer_for_link = layers["shap_beeswarm"][1]
        mean_link_state = _link_shap_mean_layer(
            op,
            graph,
            scatter_index=scatter_layer_index,
            mean_index=mean_layer_index,
            scatter_layer=scatter_layer_for_link,
        )
    else:
        mean_link_state = None

    sheet_frame = sheet.to_df()
    helper_columns = tuple(map(str, sheet_frame.columns))
    source_x = frame[spec.series[0].source_column].to_numpy(dtype=float, copy=True)
    helper_x = sheet_frame["__SHAP_X"].dropna().to_numpy(dtype=float, copy=True)
    source_x_unchanged = frame.equals(source_snapshot) and np.array_equal(source_x, helper_x)

    regions: dict[str, dict[str, float]] = {}
    plot_counts: dict[str, int] = {}
    text_state: dict[str, Any] = {}
    plot_state: dict[str, Any] = {}

    if plan.profile != "beeswarm_only":
        mean_index, mean_layer = layers["shap_mean_abs"]
        mean_geometry, mean_state, mean_text_state = _style_shap_mean_layer(
            op,
            graph,
            mean_index,
            mean_layer,
            sheet,
            sheet_frame,
            preparation,
            plan,
            geometry.region("shap_mean_abs"),
        )
        regions["shap_mean_abs"] = mean_geometry
        plot_counts["shap_mean_abs"] = len(mean_layer.plot_list())
        text_state.update(mean_text_state)
        if mean_link_state is None:
            raise OriginDrawError("Origin Mean |SHAP| layer-link evidence is missing.")
        mean_state["layer_link"] = dict(mean_link_state)
        plot_state["mean_abs"] = mean_state
    else:
        mean_state = {"present": False}

    scatter_index, scatter_layer = layers["shap_beeswarm"]
    scatter_geometry, scatter_state, scatter_text_state, colorbar_state = (
        _style_shap_scatter_layer(
            op,
            graph,
            scatter_index,
            scatter_layer,
            sheet,
            preparation,
            geometry.region("shap_beeswarm"),
        )
    )
    regions["shap_beeswarm"] = scatter_geometry
    plot_counts["shap_beeswarm"] = len(scatter_layer.plot_list())
    text_state.update(scatter_text_state)
    plot_state["beeswarm"] = scatter_state
    if plan.profile != "beeswarm_only":
        mean_index = layers["shap_mean_abs"][0]
        final_parent = int(scatter_layer.get_int("link"))
        final_unit = int(scatter_layer.get_int("unit"))
        if final_parent != mean_index or final_unit != 1:
            raise OriginDrawError(
                "Origin SHAP overlay geometry link changed during final styling."
            )
        mean_state["layer_link"].update(
            {
                "final_parent_layer": final_parent,
                "final_unit": final_unit,
            }
        )
    colorbar_geometry, spectrum_text_state = _position_shap_spectrum(
        op,
        graph,
        scatter_layer,
        preparation,
        geometry.region("shap_feature_value_colorbar"),
    )
    regions["shap_feature_value_colorbar"] = colorbar_geometry
    text_state.update(spectrum_text_state)
    spectrum_revorder = int(round(float(spectrum_text_state["Spectrum1.revorder"])))
    spectrum_attach = int(round(float(spectrum_text_state["Spectrum1.attach"])))
    spectrum_show = int(round(float(spectrum_text_state["Spectrum1.show"])))
    if (
        colorbar_state.get("palette_readback_verified") is not True
        or not math.isclose(
            float(colorbar_state.get("palette_flipped", math.nan)),
            0.0,
            rel_tol=0.0,
            abs_tol=0.05,
        )
        or spectrum_revorder != 1
        or spectrum_attach != 1
        or spectrum_show != 1
    ):
        raise OriginDrawError(
            "Origin SHAP colorbar direction/attachment evidence is incomplete."
        )
    colorbar_state.update(
        {
            "direction": "low_blue_high_red",
            "spectrum_revorder": spectrum_revorder,
            "spectrum_attach": spectrum_attach,
            "spectrum_show": spectrum_show,
            "endpoint_objects": ["SHAPColorbarLow", "SHAPColorbarHigh"],
            "endpoint_labels": ["Low", "High"],
        }
    )

    if plan.profile == "beeswarm_mean_abs_grouped":
        group_index, group_layer = layers["shap_group_contribution"]
        group_geometry, group_state, group_text_state = _style_shap_group_layer(
            op,
            graph,
            group_index,
            group_layer,
            sheet,
            sheet_frame,
            preparation,
            plan,
            geometry.region("shap_group_contribution"),
        )
        regions["shap_group_contribution"] = group_geometry
        plot_counts["shap_group_contribution"] = len(group_layer.plot_list())
        text_state.update(group_text_state)
        plot_state["group_inset"] = group_state
    else:
        group_state = {"present": False}

    readback_state: dict[str, object] = {
        "layout_version": plan.layout_version,
        "profile": plan.profile,
        "source_x_unchanged": source_x_unchanged,
        "helper_columns": list(helper_columns),
        "regions": regions,
        "plot_counts": plot_counts,
        "beeswarm": scatter_state,
        "colorbar": colorbar_state,
        "mean_abs": mean_state,
        "group_inset": group_state,
    }
    validate_shap_composite_readback(plan, geometry, readback_state)

    page_state = {
        "width_cm": float(graph.obj.GetWidth()) * 2.54,
        "height_cm": float(graph.obj.GetHeight()) * 2.54,
        **scatter_geometry,
    }
    return graph, {
        **page_state,
        "origin_shap_composite_readback": readback_state,
        "origin_plot_state": plot_state,
        "origin_axis_state": scatter_state["axis"],
        "origin_text_state": {
            **text_state,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": list(helper_columns),
        "origin_plot_data_columns": list(helper_columns),
        "origin_color_key": {
            "independent_color_scale_added": True,
            "associated_object": "Spectrum1",
            "dataset": "__FeatureValueNormalized",
            "direction": "low_blue_high_red",
        },
        "title_objects": list(scatter_text_state["title_objects"]),
    }


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    output: RunOutput,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    kind = preparation.plot_spec.plot_kind
    if kind == "raw_summary":
        graph, state = _build_raw_summary_graph(op, frame, preparation)
    elif kind == "violin":
        graph, state = _build_distribution_graph(op, frame, preparation)
    elif kind == "raincloud":
        graph, state = _build_distribution_graph(op, frame, preparation)
    elif kind == "grouped_box":
        graph, state = _build_grouped_box_graph(op, frame, preparation)
    elif kind == "histogram":
        graph, state = _build_histogram_graph(op, frame, preparation)
    elif kind == "bubble":
        graph, state = _build_bubble_graph(op, frame, preparation)
    elif kind == "forest":
        graph, state = _build_forest_graph(op, frame, preparation)
    elif kind == "shap_summary":
        graph, state = _build_shap_summary_graph(op, frame, preparation)
    else:  # pragma: no cover - protected by preparation validation
        raise OriginDrawError(f"Unsupported evidence plot kind: {kind}")

    output.result_opju.unlink(missing_ok=True)
    if not op.save(str(output.result_opju)):
        raise OriginDrawError("Origin did not save result.opju")
    require_nonempty(output.result_opju)
    return graph, {
        **state,
        "template_id": preparation.template_id,
        "plan_digest": preparation.plan_digest,
        "plot_spec": asdict(preparation.plot_spec),
        "source_sha256": preparation.source_sha256,
        "source_columns": list(preparation.source_columns),
        "source_data_modified": False,
    }


def run_evidence_template(
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
                **session.environment.to_dict(),
            },
        )
        logger.write("Evidence-first Origin graph verified and exported")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = ["run_evidence_template"]
