"""Editable Origin renderer for categorical, composition, and flow templates.

Only Origin commands already isolated against Origin 2024b/10.15 are used here:
official ``plotxy`` plot IDs, the bundled ``Pie2D`` template, and Origin's own
``PLOTPROF`` Sankey entry.  The user's source file is never written.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from origin_sciplot.logging_utils import RunLogger
from origin_sciplot.output_manager import RunOutput, write_json
from origin_sciplot.scientific_visual import (
    AdaptiveOriginStyle,
    interpolate_hex_colors,
    palette_colors,
    signed_effect_colors,
)
from origin_sciplot.scientific_workflow import ScientificPreparation, prepare_scientific
from origin_sciplot.template_registry import TemplateManifest

from .base_style_contract import page_size_inches, pt_to_origin_width_units
from .export_utils import export_graph
from .safe_errors import OriginDrawError
from .scientific_renderer import (
    OriginSeriesPlan,
    _apply_axis_label_font,
    _apply_page_layer,
    _bind_category_labels,
    _clean_numeric_x_axis,
    _figure_style,
    _origin_font_code,
    _position_axis_titles_on_page,
    _position_x_title,
    _read_axis_state,
    _set_axis_titles,
    _set_borderless_legend,
    _style_axes,
    _style_label,
    _style_legend,
    _title_geometry,
)
from .session import OriginSession
from .verify_utils import (
    require_nonempty,
    verify_page_and_layer,
    verify_plot_line_widths,
    verify_text_fonts,
    verify_text_sizes,
)

_PLOTXY_CONTRACT = {
    "horizontal_bar": (215, "BAR"),
    "stacked_bar": (213, "STACKCOLUMN"),
    "percent_stacked_bar": (213, "StackColP"),
}


_SANKEY_STAGE_RAMPS: tuple[tuple[str, str], ...] = (
    ("#355F8A", "#7093B5"),
    ("#4D8F89", "#94C5BF"),
    ("#756A9B", "#B5AACC"),
    ("#B56F78", "#DFB6BA"),
    ("#8A6B35", "#D5B978"),
    ("#536C78", "#9CB0B8"),
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
            f"Scientific preparation {resolved.template_id!r} does not match {manifest.id!r}."
        )
    if tuple(map(str, frame.columns)) != resolved.source_columns:
        raise OriginDrawError("Categorical preparation columns do not match the validated source copy.")
    if resolved.requires_confirmation:
        raise OriginDrawError("Column mapping confirmation is required before Origin can run.")
    return resolved


def _column_letter(index: int) -> str:
    """Return a one-based spreadsheet column index as an Origin column letter."""
    if index < 1:
        raise ValueError("Column index must be positive")
    value = index
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _heatmap_color_scale_geometry(
    layer_left_percent: float,
    layer_width_percent: float,
    *,
    gap_fraction: float = 0.015,
    page_right_fraction: float = 0.995,
    minimum_width_fraction: float = 0.04,
) -> tuple[float, float, float]:
    """Return non-overlapping color-scale geometry as page-width fractions."""
    layer_right_fraction = (layer_left_percent + layer_width_percent) / 100.0
    color_scale_left_fraction = layer_right_fraction + gap_fraction
    color_scale_width_fraction = page_right_fraction - color_scale_left_fraction
    if color_scale_width_fraction < minimum_width_fraction:
        raise ValueError(
            "Heatmap color scale has insufficient right margin; reduce the layer width."
        )
    return (
        layer_right_fraction,
        color_scale_left_fraction,
        color_scale_width_fraction,
    )


def _sankey_node_color_plan(
    sources: list[str],
    targets: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, int]]:
    """Return first-appearance node order and restrained colors by flow depth."""
    if len(sources) != len(targets):
        raise ValueError("Sankey source and target arrays must have equal length")
    node_order = tuple(
        dict.fromkeys(
            node
            for source, target in zip(sources, targets, strict=True)
            for node in (source, target)
        )
    )
    incoming = {node: 0 for node in node_order}
    adjacency: dict[str, list[str]] = {node: [] for node in node_order}
    for source, target in zip(sources, targets, strict=True):
        incoming[target] += 1
        adjacency[source].append(target)
    depth = {node: 0 for node in node_order}
    queue = [node for node in node_order if incoming[node] == 0]
    visited: set[str] = set()
    while queue:
        source = queue.pop(0)
        visited.add(source)
        for target in adjacency[source]:
            depth[target] = max(depth[target], depth[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    # Origin can still display cyclic input. Keep unresolved nodes in one
    # neutral family instead of inventing a direction or mutating the data.
    unresolved_depth = max((depth[node] for node in visited), default=0) + 1
    for node in node_order:
        if node not in visited:
            depth[node] = unresolved_depth
    nodes_by_depth: dict[int, list[str]] = {}
    for node in node_order:
        nodes_by_depth.setdefault(depth[node], []).append(node)
    color_by_node: dict[str, str] = {}
    for stage, nodes in nodes_by_depth.items():
        start, end = _SANKEY_STAGE_RAMPS[stage % len(_SANKEY_STAGE_RAMPS)]
        colors = interpolate_hex_colors(start, end, len(nodes))
        color_by_node.update(zip(nodes, colors, strict=True))
    return node_order, tuple(color_by_node[node] for node in node_order), depth


def _selected_plot_frame(
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    spec = preparation.plot_spec
    if spec.plot_kind == "sankey":
        if not spec.source_column or not spec.target_column:
            raise OriginDrawError("Sankey source and target columns are missing.")
        columns = [spec.source_column, spec.target_column, spec.series[0].source_column]
        return frame.loc[:, columns].copy(deep=True), ()
    if spec.category_column is None:
        raise OriginDrawError("Categorical plot column is missing.")
    columns = [spec.category_column, *(item.source_column for item in spec.series)]
    error_columns = [item.error_column for item in spec.series if item.error_column]
    if spec.aggregate_error_column:
        error_columns.append(spec.aggregate_error_column)
    columns.extend(column for column in error_columns if column not in columns)
    selected = frame.loc[:, columns].copy(deep=True)
    helpers: list[str] = []
    if spec.plot_kind == "stacked_bar" and spec.aggregate_error_column:
        total_name = "__StackTotal"
        x_name = "__StackX"
        selected[total_name] = selected.loc[
            :, [item.source_column for item in spec.series]
        ].sum(axis=1, min_count=1)
        selected[x_name] = np.arange(1, len(selected) + 1, dtype=float)
        helpers.extend((total_name, x_name))
    if spec.plot_kind != "percent_stacked_bar":
        return selected, tuple(helpers)
    values = selected.iloc[:, 1:].to_numpy(dtype=float, copy=True)
    totals = np.nansum(values, axis=1)
    normalized = np.divide(
        values,
        totals[:, None],
        out=np.zeros_like(values),
        where=totals[:, None] > 0,
    ) * 100.0
    helper_columns: list[str] = list(helpers)
    for index, series in enumerate(spec.series):
        helper = f"{series.label} (%)"
        selected[helper] = normalized[:, index]
        helper_columns.append(helper)
    selected = selected.loc[:, [spec.category_column, *helper_columns]]
    return selected, tuple(helper_columns)


def _create_origin_sheets(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, Any, tuple[str, ...]]:
    raw = op.new_sheet("w", f"{preparation.template_id.upper()} Source")
    if raw is None:
        raise OriginDrawError("Origin could not create the source worksheet.")
    raw.from_df(frame.copy(deep=True))
    raw.cols_axis()
    plot_frame, helpers = _selected_plot_frame(frame, preparation)
    plot_sheet = op.new_sheet("w", f"{preparation.template_id.upper()} Plot Data")
    if plot_sheet is None:
        raise OriginDrawError("Origin could not create the categorical plot worksheet.")
    plot_sheet.from_df(plot_frame)
    plot_sheet.cols_axis("xy")
    return raw, plot_sheet, helpers


def _set_page_size(graph: Any, style: AdaptiveOriginStyle) -> dict[str, float]:
    width_in, height_in = page_size_inches(style)
    graph.activate()
    graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;")
    state = {
        "width_cm": float(graph.obj.GetWidth()) * 2.54,
        "height_cm": float(graph.obj.GetHeight()) * 2.54,
    }
    for _attempt in range(3):
        if not graph.obj.LT_execute(
            f"page.width=({width_in:g})*page.resx;"
            f"page.height=({height_in:g})*page.resy;doc -uw;"
        ):
            raise OriginDrawError("Origin could not set the adaptive physical page size.")
        state = {
            "width_cm": float(graph.obj.GetWidth()) * 2.54,
            "height_cm": float(graph.obj.GetHeight()) * 2.54,
        }
        if (
            abs(state["width_cm"] - style.page_width_cm) <= 0.01
            and abs(state["height_cm"] - style.page_height_cm) <= 0.01
        ):
            return state
    raise OriginDrawError(
        "Origin special-plot page size did not match the adaptive physical contract: "
        f"got {state['width_cm']:.4f} x {state['height_cm']:.4f} cm, expected "
        f"{style.page_width_cm:.4f} x {style.page_height_cm:.4f} cm."
    )


def _style_special_legend(
    op: Any,
    layer: Any,
    style: AdaptiveOriginStyle,
) -> Any | None:
    legend = layer.label("legend")
    if legend is None:
        legend = layer.label("Legend")
    if legend is None:
        return None
    _style_label(legend, style.legend_size_pt, bold=False)
    layer.obj.LT_execute(
        f"legend.font=font({style.font_family});"
        "legend.color=color(black);legend.bold=0;"
    )
    legend.set_int("font", _origin_font_code(op, style.font_family))
    _set_borderless_legend(legend)
    return legend


def _special_plot_readback(
    op: Any,
    layer: Any,
    plot: Any,
    style: AdaptiveOriginStyle,
) -> dict[str, float]:
    plot_range = plot.lt_range()
    plot.set_cmd(
        f"-qs {style.tick_label_size_pt:g}",
        "-qb 1",
        f"-qf $(font({style.font_family}))",
    )
    if not layer.obj.LT_execute(
        "{"
        f"range __categorical_special={plot_range};"
        "get __categorical_special -qs __categorical_qs;"
        "get __categorical_special -qb __categorical_qb;"
        "get __categorical_special -qf __categorical_qf;"
        "}"
    ):
        raise OriginDrawError("Origin did not read back special-plot label style.")
    size = float(op.lt_float("__categorical_qs"))
    bold = float(op.lt_float("__categorical_qb"))
    font = float(op.lt_float("__categorical_qf"))
    expected_font = _origin_font_code(op, style.font_family)
    if (
        abs(size - style.tick_label_size_pt) > 0.05
        or int(round(bold)) != 1
        or int(round(font)) != expected_font
    ):
        raise OriginDrawError("Origin special-plot labels do not match the adaptive bold contract.")
    return {
        "label_size_pt": size,
        "label_bold": bold,
        "label_font_code": font,
        "font_code_expected": expected_font,
    }


def _position_external_legend(
    op: Any,
    layer: Any,
    legend: Any,
    style: AdaptiveOriginStyle,
) -> dict[str, float]:
    """Place a categorical legend in the page column reserved by the profile."""
    op.lt_exec("doc -uw;")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    layer_right = page_width * (
        style.layer_left_percent + style.layer_width_percent
    ) / 100.0
    gap = page_width * 0.025
    legend.set_float("left", layer_right + gap)
    legend.set_float("top", page_height * 0.14)
    op.lt_exec("doc -uw;")
    state = {
        "page_width": page_width,
        "page_height": page_height,
        "layer_right": layer_right,
        "gap_to_layer": float(legend.get_float("left")) - layer_right,
        "legend.left": float(legend.get_float("left")),
        "legend.top": float(legend.get_float("top")),
        "legend.width": float(legend.get_float("width")),
        "legend.height": float(legend.get_float("height")),
    }
    state["legend.right"] = state["legend.left"] + state["legend.width"]
    state["legend.bottom"] = state["legend.top"] + state["legend.height"]
    if (
        state["gap_to_layer"] < page_width * 0.015
        or state["legend.right"] > page_width * 0.995
        or state["legend.bottom"] > page_height * 0.98
    ):
        raise OriginDrawError("Origin external legend does not fit the reserved page column.")
    return state


def _bar_series_plans(preparation: ScientificPreparation) -> tuple[OriginSeriesPlan, ...]:
    style = _figure_style(preparation)
    colors = palette_colors(style.palette_name)
    return tuple(
        OriginSeriesPlan(
            source_column=series.source_column,
            plot_column=series.source_column,
            x_column=None,
            error_column=series.error_column,
            label=series.label,
            axis="left",
            plot_type="c",
            color=colors[index % len(colors)],
            bar_gap_percent=20.0,
            marker_size_pt=preparation.plot_spec.display_plan.marker_size_pt,
        )
        for index, series in enumerate(preparation.plot_spec.series)
    )


def _raw_title_geometry(op: Any, labels: dict[str, Any]) -> dict[str, float | str]:
    """Record transposed BAR title geometry without applying Cartesian clipping rules."""
    state: dict[str, float | str] = {
        "page.width": float(op.lt_float("page.width")),
        "page.height": float(op.lt_float("page.height")),
        "geometry_contract": "origin_transposed_bar_coordinates",
    }
    for name, label in labels.items():
        if label is None:
            raise OriginDrawError(f"Origin axis title object is missing: {name}")
        for prop in ("left", "top", "width", "height", "rotate"):
            state[f"{name}.{prop}"] = float(label.get_float(prop))
    return state


def _position_horizontal_value_title(op: Any, layer: Any, label: Any) -> None:
    """Keep the transposed BAR value title horizontal and inside the page."""
    if label is None:
        raise OriginDrawError("Origin horizontal value-axis title is missing.")
    label.set_int("attach", 1)
    label.set_float("rotate", 0.0)
    op.lt_exec("doc -uw;")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    layer_center = page_width * (
        layer.get_float("left") + layer.get_float("width") / 2.0
    ) / 100.0
    label.set_float("left", layer_center - label.get_float("width") / 2.0)
    label.set_float("top", page_height - label.get_float("height") - page_height * 0.015)
    op.lt_exec("doc -uw;")
    if abs(label.get_float("rotate")) > 0.05:
        raise OriginDrawError("Origin did not keep the horizontal value-axis title unrotated.")
    if (
        label.get_float("left") < 0
        or label.get_float("left") + label.get_float("width") > page_width
        or label.get_float("top") < 0
        or label.get_float("top") + label.get_float("height") > page_height
    ):
        raise OriginDrawError("Origin horizontal value-axis title is clipped by the page.")


def _nice_stacked_step(upper: float, *, target_intervals: int = 8) -> float:
    """Return a 1/2/5 major step that avoids dense stacked-bar labels."""
    if not math.isfinite(upper) or upper <= 0:
        raise OriginDrawError("Origin stacked-bar upper limit is invalid.")
    raw = upper / target_intervals
    exponent = math.floor(math.log10(raw))
    scale = 10.0**exponent
    fraction = raw / scale
    if fraction <= 1.0:
        nice = 1.0
    elif fraction <= 2.0:
        nice = 2.0
    elif fraction <= 2.5:
        nice = 2.5
    elif fraction <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * scale


def _position_rotated_category_title(op: Any, label: Any) -> None:
    """Place the axis title below 45-degree category labels without overlap."""
    if label is None:
        raise OriginDrawError("Origin category-axis title is missing.")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    layer_center = page_width * 0.61005
    label.set_float("left", layer_center - label.get_float("width") / 2.0)
    label.set_float("top", page_height * 0.90)
    op.lt_exec("doc -uw;")


def _style_bar_data_labels(
    op: Any,
    layer: Any,
    plots: dict[str, Any],
    style: AdaptiveOriginStyle,
) -> dict[str, dict[str, float]]:
    """Apply and verify the physical font contract for editable bar labels."""
    label_size = float(round(style.tick_label_size_pt * 0.88))
    expected_font = float(op.lt_float(f"font({style.font_family})"))
    state: dict[str, dict[str, float]] = {}
    for index, (label, plot) in enumerate(plots.items(), start=1):
        plot.set_cmd(
            f"-qs {label_size:g}",
            "-qb 0",
            f"-qf $(font({style.font_family}))",
        )
        if not layer.obj.LT_execute(
            f"range __bar_label{index}={plot.lt_range()};"
            f"get __bar_label{index} -qs __bar_qs{index};"
            f"get __bar_label{index} -qb __bar_qb{index};"
            f"get __bar_label{index} -qf __bar_qf{index};"
        ):
            raise OriginDrawError(f"Origin could not read back data labels for {label}.")
        actual = {
            "size_pt": float(op.lt_float(f"__bar_qs{index}")),
            "bold": float(op.lt_float(f"__bar_qb{index}")),
            "font_code": float(op.lt_float(f"__bar_qf{index}")),
        }
        if (
            abs(actual["size_pt"] - label_size) > 0.05
            or int(round(actual["bold"])) != 0
            or abs(actual["font_code"] - expected_font) > 0.5
        ):
            raise OriginDrawError(f"Origin data labels failed the font contract for {label}.")
        state[label] = actual
    return state


def _build_bar_graph(
    op: Any,
    plot_sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    plot_id, template = _PLOTXY_CONTRACT[spec.plot_kind]
    plans = _bar_series_plans(preparation)
    error_columns = tuple(plan.error_column for plan in plans if plan.error_column)
    plotted_column_count = (
        len(plot_sheet.to_df().columns)
        if spec.plot_kind == "horizontal_bar"
        else len(spec.series) + 1
    )
    last_column = _column_letter(plotted_column_count)
    data_range = f"{plot_sheet.lt_range(False)}!(A,B:{last_column})"
    plot_sheet.activate()
    if not op.lt_exec(
        f"plotxy iy:={data_range} plot:={plot_id} ogl:=<new template:={template}>;"
    ):
        raise OriginDrawError(f"Origin plotxy failed for {spec.plot_kind}.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the categorical graph.")
    layer = graph[0]
    _set_page_size(graph, style)
    layer.set_int("unit", 1)
    layer.set_float("left", style.layer_left_percent)
    layer.set_float("top", style.layer_top_percent)
    layer.set_float("width", style.layer_width_percent)
    layer.set_float("height", style.layer_height_percent)
    layer.set_int("fixed", style.layer_fixed)
    layer.set_float("factor", style.layer_factor)
    graph.obj.LT_execute("doc -uw;")
    op.set_show(True)
    geometry = verify_page_and_layer(
        graph,
        layer,
        style=style,
    )
    initial_plots = list(layer.plot_list())
    expected_initial = len(spec.series) + (
        len(error_columns) if spec.plot_kind == "horizontal_bar" else 0
    )
    if len(initial_plots) != expected_initial:
        raise OriginDrawError(
            f"Origin created {len(initial_plots)} plots; expected {expected_initial}."
        )

    # Origin's BAR template transposes the data axes.  Plot the explicit error
    # columns, then convert each one with Origin's documented
    # ``set error_dataset -o value_dataset`` route.  The source table remains
    # unchanged and the error objects remain editable in the OPJU.
    if spec.plot_kind == "horizontal_bar" and error_columns:
        initial_values = initial_plots[: len(spec.series)]
        initial_errors = initial_plots[len(spec.series) :]
        error_index = 0
        for plan, value_plot in zip(plans, initial_values, strict=True):
            if not plan.error_column:
                continue
            error_plot = initial_errors[error_index]
            error_index += 1
            if not layer.obj.LT_execute(
                f"range __bar_value{error_index}={value_plot.lt_range()};"
                f"range __bar_error{error_index}={error_plot.lt_range()};"
                f"set __bar_error{error_index} -o __bar_value{error_index};"
                "doc -uw;"
            ):
                raise OriginDrawError(
                    f"Origin could not bind {plan.error_column} to {plan.label}."
                )

    plots = list(layer.plot_list())
    if len(plots) != expected_initial:
        raise OriginDrawError("Origin changed the categorical plot count during styling.")
    value_plots = plots[: len(spec.series)]
    converted_error_plots = plots[len(spec.series) :]
    main_plots: dict[str, Any] = {}
    error_plots: dict[str, Any] = {}
    for plan, plot in zip(plans, value_plots, strict=True):
        plot.color = plan.color
        plot.set_cmd(f"-w {pt_to_origin_width_units(style.bar_border_width_pt)}")
        plot.set_cmd("-vg 20")
        main_plots[plan.label] = plot

    for index, error_plot in enumerate(converted_error_plots, start=1):
        error_plot.color = op.ocolor("#202020")
        error_plot.set_cmd(f"-w {pt_to_origin_width_units(style.error_bar_width_pt)}")
        error_plots[f"horizontal error {index}"] = error_plot

    plot_indices = {
        plot.lt_range(): index for index, plot in enumerate(layer.plot_list(), start=1)
    }
    transparency_state: dict[str, float] = {}
    for plan, plot in zip(plans, value_plots, strict=True):
        plot_index = plot_indices.get(plot.lt_range())
        if plot_index is None:
            raise OriginDrawError(f"Origin plot index is missing: {plan.label}")
        key = f"plot{plot_index}.transparency"
        layer.set_float(key, style.fill_transparency_percent)
        actual = float(layer.get_float(key))
        if abs(actual - style.fill_transparency_percent) > 0.05:
            raise OriginDrawError(f"Origin did not keep bar transparency for {plan.label}.")
        transparency_state[plan.label] = actual

    point_fill_state: dict[str, Any] = {}
    if spec.plot_kind == "horizontal_bar" and len(plans) == 1:
        plot_frame = plot_sheet.to_df()
        values = plot_frame[plans[0].source_column].to_numpy(dtype=float, copy=True)
        finite_values = values[np.isfinite(values)]
        signed = bool(
            finite_values.size
            and float(np.min(finite_values)) < 0 < float(np.max(finite_values))
        )
        if signed:
            colors = signed_effect_colors(values)
        else:
            palette = palette_colors(style.palette_name)
            colors = interpolate_hex_colors(
                palette[0],
                palette[-1],
                len(plot_frame),
            )
        plot = value_plots[0]
        commands = [f"range __horizontal_bar={plot.lt_range()};"]
        expected_codes: list[float] = []
        for row, color in enumerate(colors, start=1):
            code = float(op.ocolor(color))
            expected_codes.append(code)
            commands.append(f"set __horizontal_bar {row} -pfb {int(code)};")
            commands.append(
                f"get __horizontal_bar {row} -pfb __horizontal_fill{row};"
            )
        commands.append("doc -uw;")
        if not layer.obj.LT_execute("".join(commands)):
            raise OriginDrawError("Origin could not apply the horizontal ablation color ramp.")
        actual_codes = [
            float(op.lt_float(f"__horizontal_fill{row}"))
            for row in range(1, len(colors) + 1)
        ]
        if any(
            abs(actual - expected) > 0.5
            for actual, expected in zip(actual_codes, expected_codes, strict=True)
        ):
            raise OriginDrawError("Origin horizontal ablation colors failed readback.")
        point_fill_state = {
            "mode": (
                "signed_effect_by_direction_and_magnitude"
                if signed
                else "same_family_by_category"
            ),
            "hex": list(colors),
            "origin_codes": actual_codes,
        }

    if spec.plot_kind == "stacked_bar" and spec.aggregate_error_column:
        total_column = plot_sheet.lt_col_index("__StackTotal")
        x_column = plot_sheet.lt_col_index("__StackX")
        error_column = plot_sheet.lt_col_index(spec.aggregate_error_column)
        if min(total_column, x_column, error_column) < 1:
            raise OriginDrawError("Origin stacked total/error helper columns are missing.")
        before = {item.lt_range() for item in layer.plot_list()}
        total_plot = layer.add_plot(
            plot_sheet,
            "__StackTotal",
            "__StackX",
            type="s",
            colyerr=spec.aggregate_error_column,
        )
        if total_plot is None:
            raise OriginDrawError("Origin could not add the stacked-total error plot.")
        total_plot.symbol_size = 0.01
        additions = [item for item in layer.plot_list() if item.lt_range() not in before]
        for index, error_plot in enumerate(additions, start=1):
            if error_plot.lt_range() == total_plot.lt_range():
                continue
            error_plot.color = op.ocolor("#202020")
            error_plot.set_cmd(f"-w {pt_to_origin_width_units(style.error_bar_width_pt)}")
            error_plots[f"stack total error {index}"] = error_plot

    layer.rescale()
    _style_axes(op, layer, preparation)
    layer.axis("x").scale = "linear"
    if spec.plot_kind == "horizontal_bar":
        # The BAR template transposes the categorical X axis into the visible
        # vertical direction.  Descending X limits keep the first source row
        # at the top, matching the preview and common ablation-table reading.
        layer.axis("x").set_limits(len(plot_sheet.to_df()) + 0.5, 0.5, -1.0)
    else:
        layer.axis("x").set_limits(0.5, len(plot_sheet.to_df()) + 0.5, 1.0)
    if spec.plot_kind == "percent_stacked_bar":
        layer.axis("y").set_limits(0.0, 100.0, 20.0)
    elif spec.plot_kind == "stacked_bar":
        plot_values = plot_sheet.to_df().iloc[:, 1:].to_numpy(dtype=float)
        upper = float(np.nanmax(np.nansum(plot_values, axis=1)))
        if spec.aggregate_error_column:
            errors = plot_sheet.to_df()[spec.aggregate_error_column].to_numpy(dtype=float)
            upper = float(np.nanmax(np.nansum(plot_values[:, : len(spec.series)], axis=1) + errors))
        y_to = upper * 1.08
        y_step = _nice_stacked_step(y_to)
        layer.axis("y").set_limits(0.0, y_to, y_step)
    else:
        plan = spec.axis_plan
        layer.axis("y").set_limits(plan.y_from, plan.y_to, plan.y_step)
    title_labels = _set_axis_titles(op, layer, preparation)
    graph.activate()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    _clean_numeric_x_axis(op, graph)
    _style_axes(op, layer, preparation)
    _bind_category_labels(
        layer,
        plot_sheet,
        type("CategoryPlan", (), {"category_column": str(plot_sheet.to_df().columns[0])})(),
    )
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    if spec.plot_kind == "horizontal_bar":
        layer.set_int("x.label.wrap", 0)
        if layer.get_int("x.label.wrap") != 0:
            raise OriginDrawError("Origin did not keep horizontal category labels on one line.")
    layer.set_float("x.label.rotate", spec.display_plan.category_label_rotation_deg)
    if abs(layer.get_float("x.label.rotate") - spec.display_plan.category_label_rotation_deg) > 0.05:
        raise OriginDrawError("Origin did not keep the planned category-label rotation.")
    legend = _style_legend(op, layer, list(plans), main_plots, style)
    external_legend_state = (
        _position_external_legend(op, layer, legend, style)
        if spec.plot_kind == "percent_stacked_bar" and legend is not None
        else {}
    )
    data_label_state = (
        _style_bar_data_labels(op, layer, main_plots, style)
        if spec.plot_kind == "percent_stacked_bar"
        else {}
    )
    op.lt_exec("doc -uw;")
    _position_axis_titles_on_page(op, layer, title_labels)
    op.lt_exec("doc -uw;")
    if spec.plot_kind == "horizontal_bar":
        # The category names already identify the categorical axis.  Hiding
        # the redundant generic title preserves room for long 24 pt labels.
        title_labels["x_title"].set_int("show", 0)
        _position_horizontal_value_title(op, layer, title_labels["y_title"])
    elif spec.display_plan.category_label_rotation_deg:
        _position_rotated_category_title(op, title_labels["x_title"])
    else:
        _position_x_title(op, title_labels["x_title"], style)
    op.lt_exec("doc -uw;")

    axis_state = _read_axis_state(op, layer, preparation)
    axis_state["x.label.rotate"] = layer.get_float("x.label.rotate")
    if spec.plot_kind == "horizontal_bar":
        axis_state["x.label.wrap"] = layer.get_int("x.label.wrap")
        axis_state["category_title_visible"] = title_labels["x_title"].get_int("show")
    expected_text = {
        name: style.axis_title_size_pt for name in title_labels
    }
    labels_for_verify = dict(title_labels)
    if legend is not None:
        labels_for_verify["legend"] = legend
        expected_text["legend"] = style.legend_size_pt
    try:
        text_state = verify_text_sizes(labels_for_verify, expected_text)
        font_state = verify_text_fonts(op, labels_for_verify, style.font_family)
        line_state = verify_plot_line_widths(op, main_plots, style.bar_border_width_pt)
        error_state = (
            verify_plot_line_widths(op, error_plots, style.error_bar_width_pt)
            if error_plots
            else {}
        )
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {
            **text_state,
            **font_state,
            "external_legend": external_legend_state,
            "data_labels": data_label_state,
            "legend.showframe": (
                int(legend.get_int("showframe")) if legend is not None else None
            ),
            **(
                _raw_title_geometry(op, title_labels)
                if spec.plot_kind == "horizontal_bar"
                else _title_geometry(op, title_labels)
            ),
        },
        "origin_plot_state": {
            "bar_border_widths": line_state,
            "error_bar_widths": error_state,
            "palette_name": style.palette_name,
            "bar_transparency_percent": transparency_state,
            "point_fill": point_fill_state,
        },
    }


def _build_pie_graph(
    op: Any,
    plot_sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    style = _figure_style(preparation)
    palette = palette_colors(style.palette_name)
    row_count = len(plot_sheet.to_df())
    colors = interpolate_hex_colors(palette[0], palette[-1], row_count)
    color_codes = [float(op.ocolor(color)) for color in colors]
    color_column_index = len(plot_sheet.to_df().columns)
    plot_sheet.from_list(
        color_column_index,
        [int(code) for code in color_codes],
        lname="__PieColor",
        axis="N",
    )
    graph = op.new_graph("PIE Figure", template="Pie2D")
    if graph is None:
        raise OriginDrawError("Origin could not create the official Pie2D graph.")
    layer = graph[0]
    plot = layer.add_plot(f"{plot_sheet.lt_range(False)}!(A,B)", type="?")
    if plot is None:
        raise OriginDrawError("Origin could not add the pie data plot.")
    color_column = _column_letter(color_column_index + 1)
    if not layer.obj.LT_execute(
        f"range __pie_plot={plot.lt_range()};"
        f"range __pie_colors={plot_sheet.lt_range(False)}!col({color_column});"
        "set __pie_plot -cue 1;"
        "set __pie_plot -cuf __pie_colors;"
        "dataset __pie_cuf;"
        "get __pie_plot -cue __pie_cue;"
        "get __pie_plot -cuf __pie_cuf;"
        "doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the verified pie color list.")
    cue_state = float(op.lt_float("__pie_cue"))
    color_readback = [
        float(op.lt_float(f"__pie_cuf[{index}]"))
        for index in range(1, row_count + 1)
    ]
    if int(round(cue_state)) != 1 or any(
        abs(actual - expected) > 0.5
        for actual, expected in zip(color_readback, color_codes, strict=True)
    ):
        raise OriginDrawError("Origin pie colors failed custom-list readback.")
    layer.rescale()
    graph.set_int("background", op.ocolor("#FFFFFF"))
    page_state = _set_page_size(graph, style)
    special_state = _special_plot_readback(op, layer, plot, style)
    legend = _style_special_legend(op, layer, style)
    text_state: dict[str, Any] = {}
    if legend is not None:
        page_width = float(op.lt_float("page.width"))
        page_height = float(op.lt_float("page.height"))
        legend.set_float("left", page_width - legend.get_float("width") - page_width * 0.03)
        legend.set_float("top", page_height * 0.06)
        op.lt_exec("doc -uw;")
        legend_right = legend.get_float("left") + legend.get_float("width")
        legend_bottom = legend.get_float("top") + legend.get_float("height")
        if (
            legend.get_float("left") < 0
            or legend.get_float("top") < 0
            or legend_right > page_width
            or legend_bottom > page_height
        ):
            raise OriginDrawError("Origin pie legend is clipped by the physical page.")
        try:
            text_state = verify_text_sizes(
                {"legend": legend}, {"legend": style.legend_size_pt}
            )
            text_state.update(
                verify_text_fonts(op, {"legend": legend}, style.font_family)
            )
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
        text_state.update(
            {
                "legend.left": legend.get_float("left"),
                "legend.top": legend.get_float("top"),
                "legend.width": legend.get_float("width"),
                "legend.height": legend.get_float("height"),
                "legend.showframe": int(legend.get_int("showframe")),
            }
        )
    return graph, {
        **page_state,
        "origin_axis_state": {"plot_kind": "pie", "plot_count": len(layer.plot_list())},
        "origin_text_state": {**text_state, "special_plot": special_state},
        "origin_plot_state": {
            "flat_2d_template": "Pie2D",
            "palette_name": style.palette_name,
            "slice_color_hex": list(colors),
            "slice_color_codes": color_readback,
            "custom_increment_enabled": cue_state,
        },
        "origin_helper_columns": ["__PieColor"],
    }


def _build_sankey_graph(
    op: Any,
    plot_sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    style = _figure_style(preparation)
    plot_frame = plot_sheet.to_df()
    sources = [str(value) for value in plot_frame.iloc[:, 0].tolist()]
    targets = [str(value) for value in plot_frame.iloc[:, 1].tolist()]
    node_order, node_colors, node_depth = _sankey_node_color_plan(sources, targets)
    color_codes = [float(op.ocolor(color)) for color in node_colors]
    color_column_index = len(plot_frame.columns)
    plot_sheet.from_list(
        color_column_index,
        [int(code) for code in color_codes],
        lname="__SankeyColor",
        axis="N",
    )
    plot_sheet.activate()
    if not plot_sheet.obj.LT_execute("worksheet -s 1 0 3 0;run.section(PLOTPROF, Sankey);"):
        raise OriginDrawError("Origin's official Sankey plot profile did not execute.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the Sankey graph.")
    layer = graph[0]
    plots = list(layer.plot_list())
    if len(plots) != 1:
        raise OriginDrawError(f"Origin created {len(plots)} Sankey plots; expected one.")
    color_column = _column_letter(color_column_index + 1)
    if not layer.obj.LT_execute(
        f"range __sankey_plot={plots[0].lt_range()};"
        f"range __sankey_colors={plot_sheet.lt_range(False)}!col({color_column});"
        "set __sankey_plot -cue 1;"
        "set __sankey_plot -cuf __sankey_colors;"
        "dataset __sankey_cuf;"
        "get __sankey_plot -cue __sankey_cue;"
        "get __sankey_plot -cuf __sankey_cuf;"
        "doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the verified Sankey node color list.")
    cue_state = float(op.lt_float("__sankey_cue"))
    color_readback = [
        float(op.lt_float(f"__sankey_cuf[{index}]"))
        for index in range(1, len(node_colors) + 1)
    ]
    if int(round(cue_state)) != 1 or any(
        abs(actual - expected) > 0.5
        for actual, expected in zip(color_readback, color_codes, strict=True)
    ):
        raise OriginDrawError("Origin Sankey colors failed custom-list readback.")
    graph.set_int("background", op.ocolor("#FFFFFF"))
    page_state = _set_page_size(graph, style)
    special_state = _special_plot_readback(op, layer, plots[0], style)
    return graph, {
        **page_state,
        "origin_axis_state": {"plot_kind": "sankey", "plot_count": 1},
        "origin_text_state": {"special_plot": special_state},
        "origin_plot_state": {
            "profile": "PLOTPROF/Sankey",
            "palette_name": style.palette_name,
            "adaptive_profile": style.to_dict(),
            "node_order": list(node_order),
            "node_depth": {node: node_depth[node] for node in node_order},
            "node_color_hex": list(node_colors),
            "node_color_codes": color_readback,
            "custom_increment_enabled": cue_state,
        },
        "origin_helper_columns": ["__SankeyColor"],
    }


def _radar_series_plans(preparation: ScientificPreparation) -> tuple[OriginSeriesPlan, ...]:
    style = _figure_style(preparation)
    colors = palette_colors(style.palette_name)
    return tuple(
        OriginSeriesPlan(
            source_column=series.source_column,
            plot_column=series.source_column,
            x_column=None,
            error_column=None,
            label=series.label,
            axis="left",
            plot_type="y",
            color=colors[index % len(colors)],
            bar_gap_percent=None,
            marker_size_pt=preparation.plot_spec.display_plan.marker_size_pt,
        )
        for index, series in enumerate(preparation.plot_spec.series)
    )


def _build_radar_graph(
    op: Any,
    plot_sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    style = _figure_style(preparation)
    last_column = _column_letter(len(preparation.plot_spec.series) + 1)
    data_range = f"{plot_sheet.lt_range(False)}!(A,B:{last_column})"
    plot_sheet.activate()
    if not op.lt_exec(
        f"plotxy iy:={data_range} plot:=202 ogl:=<new template:=Radar>;"
    ):
        raise OriginDrawError("Origin's official Radar template did not execute.")
    graph = op.find_graph()
    if graph is None:
        raise OriginDrawError("Origin did not create the Radar graph.")
    layer = graph[0]
    geometry = _apply_page_layer(
        op,
        graph,
        layer,
        dual_y=False,
        preparation=preparation,
    )
    layer.group(False)
    plots = list(layer.plot_list())
    plans = _radar_series_plans(preparation)
    if len(plots) != len(plans):
        raise OriginDrawError(
            f"Origin created {len(plots)} Radar plots; expected {len(plans)}."
        )
    main_plots: dict[str, Any] = {}
    for plot, plan in zip(plots, plans, strict=True):
        color_code = op.ocolor(plan.color)
        plot.color = plan.color
        plot.set_cmd(f"-c color({plan.color})", f"-cl {color_code}")
        plot.set_cmd(f"-w {pt_to_origin_width_units(style.plot_line_width_pt)}")
        plot.symbol_kind = 2
        plot.symbol_interior = 2
        plot.symbol_size = plan.marker_size_pt
        plot.set_cmd("-kh 32")
        main_plots[plan.label] = plot
    layer.rescale()
    values = plot_sheet.to_df().iloc[:, 1 : len(plans) + 1].to_numpy(dtype=float)
    maximum = float(np.nanmax(values))
    if maximum <= 1.0:
        upper = 1.0
        increment = 0.2
    else:
        upper = maximum * 1.08
        increment = _nice_stacked_step(upper, target_intervals=5)
        upper = math.ceil(upper / increment) * increment
    layer.axis("y").set_limits(0.0, upper, increment)
    layer.set_float("x.label.pt", style.tick_label_size_pt)
    layer.set_float("y.label.pt", style.tick_label_size_pt * 0.88)
    layer.set_float("x.tickthickness", style.frame_line_width_pt)
    layer.set_float("y.tickthickness", style.frame_line_width_pt)
    graph.activate()
    radial_label_offset = 70.0
    if not layer.obj.LT_execute(
        f"layer.x.label.font=font({style.font_family});"
        f"layer.y.label.font=font({style.font_family});"
        f"layer.y.label.offsetH={radial_label_offset:g};"
        f"doc -e G {{%B.font=font({style.font_family});}};"
        "doc -uw;"
    ):
        raise OriginDrawError("Origin could not style the Radar axes.")
    for title_name in ("xb", "yl"):
        title = layer.label(title_name)
        if title is not None:
            title.set_int("show", 0)
    legend = _style_legend(op, layer, list(plans), main_plots, style)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    op.lt_exec("doc -uw;")
    try:
        line_state = verify_plot_line_widths(op, main_plots, style.plot_line_width_pt)
        text_state = (
            verify_text_sizes({"legend": legend}, {"legend": style.legend_size_pt})
            if legend is not None
            else {}
        )
        if legend is not None:
            text_state.update(
                verify_text_fonts(op, {"legend": legend}, style.font_family)
            )
            text_state["legend.showframe"] = int(legend.get_int("showframe"))
    except RuntimeError as exc:
        raise OriginDrawError(str(exc)) from exc
    axis_state = {
        "plot_kind": "radar",
        "plot_count": len(plots),
        "radial_from": float(layer.get_float("y.from")),
        "radial_to": float(layer.get_float("y.to")),
        "radial_increment": float(layer.get_float("y.inc")),
        "category_label_size_pt": float(layer.get_float("x.label.pt")),
        "radial_label_size_pt": float(layer.get_float("y.label.pt")),
        "category_label_font_code": float(layer.get_float("x.label.font")),
        "radial_label_font_code": float(layer.get_float("y.label.font")),
        "font_code_expected": float(op.lt_float(f"font({style.font_family})")),
        "radial_label_offset_percent_font": float(layer.get_float("y.label.offsetH")),
    }
    if abs(axis_state["category_label_size_pt"] - style.tick_label_size_pt) > 0.05:
        raise OriginDrawError("Origin Radar category labels failed the adaptive font contract.")
    arial_font_code = float(op.lt_float(f"font({style.font_family})"))
    if (
        int(round(axis_state["category_label_font_code"])) != int(round(arial_font_code))
        or int(round(axis_state["radial_label_font_code"])) != int(round(arial_font_code))
        or abs(axis_state["radial_label_offset_percent_font"] - radial_label_offset) > 0.05
    ):
        raise OriginDrawError("Origin Radar labels failed the font or offset readback contract.")
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": text_state,
        "origin_plot_state": {
            "template": "Radar",
            "line_widths": line_state,
            "palette_name": style.palette_name,
            "editable_plot_count": len(plots),
        },
    }


def _bind_heatmap_labels(
    op: Any,
    layer: Any,
    label_sheet: Any,
    *,
    x_rotation: float,
    style: AdaptiveOriginStyle,
) -> dict[str, float]:
    x_labels = f"{label_sheet.lt_range(False)}!col(1)"
    y_labels = f"{label_sheet.lt_range(False)}!col(2)"
    if not layer.obj.LT_execute(
        f"range __heatmap_x_labels={x_labels};"
        f"range __heatmap_y_labels={y_labels};"
        "axis -ps X T __heatmap_x_labels;axis -ps Y T __heatmap_y_labels;"
    ):
        raise OriginDrawError("Origin could not bind Heatmap category labels.")
    layer.set_int("x.minorTicks", 0)
    layer.set_int("y.minorTicks", 0)
    layer.set_float("x.label.rotate", x_rotation)
    _apply_axis_label_font(op, layer, ("x", "y"), style)
    state = {
        "x_label_type": float(layer.get_int("x.label.type")),
        "y_label_type": float(layer.get_int("y.label.type")),
        "x_label_rotation_deg": float(layer.get_float("x.label.rotate")),
        "x_label_size_pt": float(layer.get_float("x.label.pt")),
        "y_label_size_pt": float(layer.get_float("y.label.pt")),
        "x_label_font_code": float(layer.get_float("x.label.font")),
        "y_label_font_code": float(layer.get_float("y.label.font")),
        "font_code_expected": float(_origin_font_code(op, style.font_family)),
    }
    if int(round(state["x_label_type"])) != 2 or int(round(state["y_label_type"])) != 2:
        raise OriginDrawError("Origin Heatmap labels are not bound as Text from Dataset.")
    if abs(state["x_label_rotation_deg"] - x_rotation) > 0.05:
        raise OriginDrawError("Origin Heatmap X-label rotation does not match the adaptive plan.")
    for axis_name in ("x", "y"):
        if abs(state[f"{axis_name}_label_size_pt"] - style.tick_label_size_pt) > 0.05:
            raise OriginDrawError("Origin Heatmap axis-label size verification failed.")
        if int(round(state[f"{axis_name}_label_font_code"])) != int(
            round(state["font_code_expected"])
        ):
            raise OriginDrawError("Origin Heatmap axis-label font verification failed.")
    return state


def _build_heatmap_graph(
    op: Any,
    plot_sheet: Any,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    spec = preparation.plot_spec
    style = _figure_style(preparation)
    plot_frame = plot_sheet.to_df()
    categories = [str(value) for value in plot_frame.iloc[:, 0].tolist()]
    series_labels = [series.label for series in spec.series]
    values = plot_frame.loc[:, [series.source_column for series in spec.series]].to_numpy(
        dtype=float,
        copy=True,
    )
    rows, columns = values.shape
    matrix = op.new_sheet("m", "HEATMAP Matrix")
    if matrix is None:
        raise OriginDrawError("Origin could not create the Heatmap matrix sheet.")
    matrix.from_np(values)
    matrix.xymap = (1.0, float(columns), 1.0, float(rows))
    label_count = max(rows, columns)
    label_frame = pd.DataFrame(
        {
            "X Labels": series_labels + [None] * (label_count - columns),
            "Y Labels": categories + [None] * (label_count - rows),
        }
    )
    label_sheet = op.new_sheet("w", "HEATMAP Labels")
    if label_sheet is None:
        raise OriginDrawError("Origin could not create the Heatmap label worksheet.")
    label_sheet.from_df(label_frame)
    show_cell_labels = rows <= 15 and columns <= 12 and values.size <= 150
    template = "Heat_Map_With_Labels" if show_cell_labels else "heatmap"
    graph = op.new_graph("HEATMAP Figure", template=template)
    if graph is None:
        raise OriginDrawError(f"Origin could not create the official {template} graph.")
    layer = graph[0]
    plot = layer.add_plot(matrix, colz=0)
    if plot is None:
        raise OriginDrawError("Origin could not add the editable matrix Heatmap plot.")
    layer.rescale("z")
    plot.colormap = style.heatmap_palette
    if not layer.obj.LT_execute(
        "layer.cmap.flippal=1;layer.cmap.updateScale();"
    ):
        raise OriginDrawError("Origin could not apply the Heatmap palette direction.")
    _set_page_size(graph, style)
    layer.set_int("unit", 1)
    layer.set_float("left", style.layer_left_percent)
    layer.set_float("top", style.layer_top_percent)
    layer.set_float("width", style.layer_width_percent)
    layer.set_float("height", style.layer_height_percent)
    layer.set_int("fixed", style.layer_fixed)
    layer.set_float("factor", style.layer_factor)
    graph.obj.LT_execute("doc -uw;")
    op.set_show(True)
    geometry = verify_page_and_layer(
        graph,
        layer,
        style=style,
    )
    _style_axes(op, layer, preparation)
    layer.axis("x").set_limits(0.5, columns + 0.5, 1.0)
    layer.axis("y").set_limits(rows + 0.5, 0.5, -1.0)
    max_x_label = max((len(value) for value in series_labels), default=0)
    if preparation.template_id == "confusion_matrix" and columns <= 4:
        x_rotation = 0.0
    else:
        x_rotation = 35.0 if columns > 6 or max_x_label > 10 else 0.0
    label_state = _bind_heatmap_labels(
        op,
        layer,
        label_sheet,
        x_rotation=x_rotation,
        style=style,
    )
    title_state: dict[str, float] = {}
    title_labels: dict[str, Any] = {}
    if preparation.template_id == "confusion_matrix":
        title_labels = _set_axis_titles(op, layer, preparation)
        title_text = {
            "x_title": preparation.plot_spec.x_title,
            "y_title": preparation.plot_spec.y_title,
        }
        for name, title in title_labels.items():
            if title is not None:
                title.text = rf"\b({title_text[name]})"
                title.set_int("show", 1)
                title.set_int("bold", 1)
        op.lt_exec("doc -uw;")
        if x_rotation:
            _position_rotated_category_title(op, title_labels["x_title"])
        else:
            _position_x_title(op, title_labels["x_title"], style)
        op.lt_exec("doc -uw;")
        title_state = _title_geometry(op, title_labels)
        try:
            title_state.update(
                verify_text_sizes(
                    title_labels,
                    {name: style.axis_title_size_pt for name in title_labels},
                )
            )
            title_state.update(verify_text_fonts(op, title_labels, style.font_family))
        except RuntimeError as exc:
            raise OriginDrawError(str(exc)) from exc
    else:
        layer.axis("x").title = ""
        layer.axis("y").title = ""
    graph.set_int("background", op.ocolor("#FFFFFF"))
    cell_label_state: dict[str, float] = {"show": float(show_cell_labels)}
    if show_cell_labels:
        cell_size = float(round(style.tick_label_size_pt * 0.76))
        plot_range = plot.lt_range()
        plot.set_cmd(
            f"-qs {cell_size:g}",
            "-qb 0",
            f"-qf $(font({style.font_family}))",
        )
        if not layer.obj.LT_execute(
            "{"
            f"range __heatmap_plot={plot_range};"
            "get __heatmap_plot -qs __heatmap_qs;"
            "get __heatmap_plot -qb __heatmap_qb;"
            "get __heatmap_plot -qf __heatmap_qf;"
            "}"
        ):
            raise OriginDrawError("Origin did not read back Heatmap cell-label style.")
        cell_label_state.update(
            {
                "size_pt": float(op.lt_float("__heatmap_qs")),
                "bold": float(op.lt_float("__heatmap_qb")),
                "font_code": float(op.lt_float("__heatmap_qf")),
                "font_code_expected": float(_origin_font_code(op, style.font_family)),
            }
        )
        if (
            abs(cell_label_state["size_pt"] - cell_size) > 0.05
            or int(round(cell_label_state["bold"])) != 0
            or int(round(cell_label_state["font_code"]))
            != int(round(cell_label_state["font_code_expected"]))
        ):
            raise OriginDrawError("Origin Heatmap cell labels failed the adaptive contract.")
    color_scale_size = float(round(style.tick_label_size_pt * 0.82))
    if preparation.template_id != "confusion_matrix":
        for title_name in ("xb", "yl"):
            title = layer.label(title_name)
            if title is not None:
                title.set_int("show", 0)
    (
        layer_right_fraction,
        color_scale_left_fraction,
        color_scale_width_fraction,
    ) = _heatmap_color_scale_geometry(
        style.layer_left_percent,
        style.layer_width_percent,
    )
    if not layer.obj.LT_execute(
        "spectrum1.title=0;"
        "spectrum1.show=1;spectrum1.attach=0;"
        "spectrum1.labels.autodisp=0;"
        f"spectrum1.labels.fsize={color_scale_size:g};"
        "spectrum1.labels.bold=0;"
        f"spectrum1.labels.font=font({style.font_family});"
        f"spectrum1.left=page.width*{color_scale_left_fraction:g};"
        "spectrum1.top=page.height*0.08;"
        f"spectrum1.width=page.width*{color_scale_width_fraction:g};"
        "spectrum1.height=page.height*0.75;"
        "spectrum1.barthick=100;"
    ):
        raise OriginDrawError("Origin could not style the Heatmap color scale.")
    page_width_units = float(op.lt_float("page.width"))
    layer_right_units = page_width_units * layer_right_fraction
    color_scale_state = {
        "title_visible": float(op.lt_float("spectrum1.title")),
        "show": float(op.lt_float("spectrum1.show")),
        "label_size_pt": float(op.lt_float("spectrum1.labels.fsize")),
        "label_font_code": float(op.lt_float("spectrum1.labels.font")),
        "font_code_expected": float(_origin_font_code(op, style.font_family)),
        "palette_flipped": float(layer.get_float("cmap.flippal")),
        "left": float(op.lt_float("spectrum1.left")),
        "top": float(op.lt_float("spectrum1.top")),
        "width": float(op.lt_float("spectrum1.width")),
        "height": float(op.lt_float("spectrum1.height")),
        "page_width": page_width_units,
        "layer_right": layer_right_units,
    }
    color_scale_state["gap_to_layer"] = color_scale_state["left"] - layer_right_units
    color_scale_state["right"] = color_scale_state["left"] + color_scale_state["width"]
    if (
        int(round(color_scale_state["title_visible"])) != 0
        or int(round(color_scale_state["show"])) != 1
        or abs(color_scale_state["label_size_pt"] - color_scale_size) > 0.05
        or int(round(color_scale_state["label_font_code"]))
        != int(round(color_scale_state["font_code_expected"]))
        or int(round(color_scale_state["palette_flipped"])) != 1
        or color_scale_state["gap_to_layer"] < page_width_units * 0.01
        or color_scale_state["right"] > page_width_units * 1.005
    ):
        raise OriginDrawError("Origin Heatmap color scale failed readback verification.")
    graph.activate()
    if not op.lt_exec(
        f"doc -e G {{%B.font=font({style.font_family});}};doc -uw;"
    ):
        raise OriginDrawError("Origin could not apply the Heatmap page font contract.")
    return graph, {
        **geometry,
        "origin_axis_state": {
            "plot_kind": "heatmap",
            "plot_count": len(layer.plot_list()),
            "matrix_rows": rows,
            "matrix_columns": columns,
            "y_order": "source_top_to_bottom",
            **label_state,
        },
        "origin_text_state": {
            "cell_labels": cell_label_state,
            "color_scale": color_scale_state,
            "axis_titles": title_state,
        },
        "origin_plot_state": {
            "template": template,
            "matrix_plot_range": plot.lt_range(),
            "palette": style.heatmap_palette,
            "editable_plot_count": len(layer.plot_list()),
            "helper_sheets": ["HEATMAP Matrix", "HEATMAP Labels"],
        },
    }


def _build_origin_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
) -> tuple[Any, dict[str, Any]]:
    _raw_sheet, plot_sheet, helpers = _create_origin_sheets(op, frame, preparation)
    kind = preparation.plot_spec.plot_kind
    if kind in _PLOTXY_CONTRACT:
        graph, state = _build_bar_graph(op, plot_sheet, preparation)
    elif kind == "pie":
        graph, state = _build_pie_graph(op, plot_sheet, preparation)
    elif kind == "sankey":
        graph, state = _build_sankey_graph(op, plot_sheet, preparation)
    elif kind == "radar":
        graph, state = _build_radar_graph(op, plot_sheet, preparation)
    elif kind == "heatmap":
        graph, state = _build_heatmap_graph(op, plot_sheet, preparation)
    else:
        raise OriginDrawError(f"Unsupported categorical plot kind: {kind}")
    renderer_helpers = tuple(state.pop("origin_helper_columns", ()))
    report = {
        **state,
        "template_id": preparation.template_id,
        "plan_digest": preparation.plan_digest,
        "plot_spec": asdict(preparation.plot_spec),
        "source_sha256": preparation.source_sha256,
        "source_columns": list(preparation.source_columns),
        "origin_helper_columns": [*helpers, *renderer_helpers],
        "source_data_modified": False,
    }
    return graph, report


def run_categorical_template(
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
        graph, verify_report = _build_origin_graph(op, frame, resolved)
        output.result_opju.unlink(missing_ok=True)
        if not op.save(str(output.result_opju)):
            raise OriginDrawError("Origin did not save result.opju")
        require_nonempty(output.result_opju)
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
        logger.write("Categorical Origin graph verified and exported")
    return {
        "opju": str(output.result_opju),
        "png": str(output.result_png),
        "pdf": str(output.result_pdf),
        "tif": str(output.result_tif),
        "verify": verify_report,
    }


__all__ = ["run_categorical_template"]
