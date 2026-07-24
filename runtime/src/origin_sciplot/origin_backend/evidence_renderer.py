"""Editable Origin renderer for evidence-first general scientific plots.

The specialized routes in this module were first exercised under
``test_outputs/origin_api_lab/nature_expansion_probe.py`` against Origin
2024b/10.15.  It uses only documented Origin plot IDs, ``plotgboxraw``,
``addline``, and Layer.Plotn properties.  The user's source table is never
written; display helpers exist only inside the OPJU workbook.
"""

from __future__ import annotations

import math
from contextlib import suppress
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_visual import palette_colors
from origin_sciplot.scientific_workflow import (
    ScientificPreparation,
    evidence_jitter_offsets,
    prepare_scientific,
    shap_beeswarm_offsets,
    shap_within_feature_color_values,
)
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import pt_to_origin_width_units
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
    require_nonempty,
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


def _shap_plot_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Create Origin-only beeswarm/color helpers without changing SHAP X values."""
    spec = preparation.plot_spec
    series = spec.series[0]
    if not spec.category_column or not series.color_column:
        raise OriginDrawError("SHAP category or color column is missing.")
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
    count = len(spec.category_order)
    for index, feature in enumerate(spec.category_order):
        members = np.flatnonzero(features == feature)
        y_values[members] = float(count - index) + shap_beeswarm_offsets(shap_values[members])
    length = max(len(frame), count)
    plot_frame = pd.DataFrame(index=range(length))
    plot_frame["__SHAP_X"] = pd.Series(shap_values)
    plot_frame["__SHAP_Y"] = pd.Series(y_values)
    plot_frame["__FeatureValueNormalized"] = pd.Series(normalized)
    plot_frame["__FeatureLabel"] = pd.Series(list(reversed(spec.category_order)))
    return plot_frame, (
        "__SHAP_X",
        "__SHAP_Y",
        "__FeatureValueNormalized",
        "__FeatureLabel",
    )


def _build_shap_summary_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    _source_sheet(op, frame, preparation)
    plot_frame, helpers = _shap_plot_frame(frame, preparation)
    sheet = op.new_sheet("w", "SHAP Plot Data")
    if sheet is None:
        raise OriginDrawError("Origin could not create the SHAP helper worksheet.")
    sheet.from_df(plot_frame)
    sheet.cols_axis("xyyy")
    graph = op.new_graph("SHAP Summary Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the SHAP summary graph.")
    layer = graph[0]
    geometry = _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    scatter = layer.add_plot(sheet, "__SHAP_Y", "__SHAP_X", type="s")
    if scatter is None:
        raise OriginDrawError("Origin could not create the editable SHAP scatter object.")
    scatter.set_cmd(
        "-k 2",
        "-kf 0",
        f"-z {spec.display_plan.marker_size_pt:g}",
        "-kh 20",
    )
    scatter_range = scatter.lt_range()
    graph.activate()
    if not layer.obj.LT_execute(
        "layer.plot1.color=color(1,m);"
        "layer.cmap.zmin=0;layer.cmap.zmax=1;doc -uw;"
    ):
        raise OriginDrawError("Origin rejected the verified dataset color-mapping route.")
    scatter.colormap = "RedWhiteBlue.PAL"
    if not layer.obj.LT_execute(
        "layer.cmap.flippal=0;layer.cmap.updateScale();doc -uw;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP palette direction.")

    if not layer.obj.LT_execute(
        "{"
        f"range __shap_plot={scatter_range};"
        "get __shap_plot -co __shap_color_mode;"
        "get __shap_plot -cm __shap_color_dataset$;"
        "}"
    ):
        raise OriginDrawError("Origin could not read back SHAP dataset color mapping.")
    color_mode = int(round(float(op.lt_float("__shap_color_mode"))))
    color_dataset = str(op.get_lt_str("__shap_color_dataset"))
    sheet_range = str(sheet.lt_range(False))
    book_name = sheet_range.split("]", 1)[0].lstrip("[") if "]" in sheet_range else ""
    expected_dataset = f"{book_name}_C" if book_name else ""
    if color_mode != 2:
        raise OriginDrawError(
            f"Origin SHAP color mapping mode is {color_mode}, expected dataset mode 2."
        )
    if expected_dataset and color_dataset != expected_dataset:
        raise OriginDrawError(
            "Origin SHAP color mapping points to "
            f"{color_dataset!r}, expected helper dataset {expected_dataset!r}."
        )
    if abs(float(layer.get_float("cmap.flippal")) - 0.0) > 0.05:
        raise OriginDrawError("Origin did not keep the low-blue/high-red SHAP palette direction.")

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
    label_index = sheet.lt_col_index("__FeatureLabel")
    label_range = f"{sheet.lt_range(False)}!col({label_index})"
    if not layer.obj.LT_execute(
        f"range __shap_labels={label_range};axis -ps Y T __shap_labels;"
    ):
        raise OriginDrawError("Origin could not bind SHAP feature labels.")
    layer.set_int("y.minorTicks", 0)
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    if layer.get_int("y.label.type") != 2:
        raise OriginDrawError("Origin did not keep SHAP text labels on the Y axis.")

    reference_state: dict[str, float | bool] = {"present": False}
    graph.activate()
    if not op.lt_exec(
        "addline type:=0 value:=0 color:=color(#7A7A7A) "
        "style:=1 select:=1 move:=1 name:=SHAPZero;"
    ):
        raise OriginDrawError("Origin rejected the verified SHAP zero reference line.")
    _remove_label(layer, "SHAPZeroText")
    reference_state = {
        "present": layer.label("SHAPZero") is not None,
        "text_present": layer.label("SHAPZeroText") is not None,
        "value": 0.0,
    }
    if not reference_state["present"] or reference_state["text_present"]:
        raise OriginDrawError("Origin SHAP zero reference line verification failed.")

    x_span = float(spec.axis_plan.x_to - spec.axis_plan.x_from)
    y_span = float(spec.axis_plan.y_to - spec.axis_plan.y_from)
    note_y = float(spec.axis_plan.y_to - y_span * 0.035)
    low_note = layer.add_label(
        "Low feature value",
        float(spec.axis_plan.x_from + x_span * 0.025),
        note_y,
    )
    high_note = layer.add_label(
        "High feature value",
        float(spec.axis_plan.x_from + x_span * 0.72),
        note_y,
    )
    if low_note is None or high_note is None:
        raise OriginDrawError("Origin could not create the editable SHAP color-key labels.")
    _style_label(low_note, style.legend_size_pt, bold=False)
    _style_label(high_note, style.legend_size_pt, bold=False)
    font_code = _origin_font_code(op, style.font_family)
    low_note.set_int("font", font_code)
    high_note.set_int("font", font_code)
    low_note.color = op.ocolor("#3B4CC0")
    high_note.color = op.ocolor("#B40426")
    op.lt_exec("doc -uw;")
    try:
        note_sizes = verify_text_sizes(
            {"low_feature_value": low_note, "high_feature_value": high_note},
            {
                "low_feature_value": style.legend_size_pt,
                "high_feature_value": style.legend_size_pt,
            },
        )
        note_sizes.update(
            verify_text_fonts(
                op,
                {"low_feature_value": low_note, "high_feature_value": high_note},
                style.font_family,
            )
        )
        symbol_state = verify_symbol_style(
            op,
            scatter,
            expected_size_pt=spec.display_plan.marker_size_pt,
            expected_edge_percent=20.0,
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc

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
    return graph, {
        **geometry,
        "origin_plot_state": {
            "symbol": symbol_state,
            "color_mode": color_mode,
            "color_dataset": color_dataset,
            "expected_color_dataset": expected_dataset,
            "colormap": "RedWhiteBlue.PAL",
            "palette_flipped": float(layer.get_float("cmap.flippal")),
            "reference": reference_state,
        },
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **title_state,
            **note_sizes,
            "font_family_expected": style.font_family,
            "axis_title_size_pt": style.axis_title_size_pt,
            "tick_label_size_pt": style.tick_label_size_pt,
            "legend_size_pt": style.legend_size_pt,
            "adaptive_profile": style.to_dict(),
        },
        "origin_helper_columns": list(helpers),
        "origin_plot_data_columns": list(plot_frame.columns),
        "origin_color_key": {
            "low_text": "Low feature value",
            "low_color": "#3B4CC0",
            "high_text": "High feature value",
            "high_color": "#B40426",
            "independent_color_scale_added": False,
        },
        "title_objects": list(labels),
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
