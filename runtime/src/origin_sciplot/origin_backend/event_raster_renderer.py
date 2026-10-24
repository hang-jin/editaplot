"""Source-bound native event marks. The existing caller owns Origin sessions."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ..event_raster import (
    EventRasterPlan,
    build_event_raster_plan,
    event_rows_by_condition,
    validate_event_time_title,
)
from ..event_raster_layout import build_event_raster_layout
from ..scientific_workflow import ScientificPreparation, ScientificWorkflowError, load_scientific_frame
from .safe_errors import OriginDrawError


def _event_source_copy(frame: pd.DataFrame, plan: EventRasterPlan) -> pd.DataFrame:
    imported = frame.copy(deep=True)
    for column in imported:
        values = imported[column]
        if column in {plan.trial_column, plan.condition_column}:
            order = plan.trial_order if column == plan.trial_column else plan.condition_order
            imported[column] = pd.Categorical(values.map(str), categories=order, ordered=True)
        elif len(values.dropna()) and all(isinstance(value, str) for value in values.dropna()):
            imported[column] = pd.Categorical(values, categories=pd.unique(values.dropna()), ordered=True)
    return imported


def _prepare_event_raster_data(
    frame: pd.DataFrame, preparation: ScientificPreparation
) -> tuple[tuple[str, pd.DataFrame], ...]:
    plan = preparation.plot_spec.event_raster_plan
    if plan is None:
        raise OriginDrawError("The source-bound event plan is missing.")
    try:
        source = load_scientific_frame(preparation.source_path, preparation)
        pd.testing.assert_frame_equal(frame, source, check_exact=True)
        current = build_event_raster_plan(
            frame,
            event_time_column=plan.event_time_column,
            trial_column=plan.trial_column,
            condition_column=plan.condition_column,
            time_unit=plan.time_unit,
        )
    except (ScientificWorkflowError, ValueError, AssertionError) as error:
        raise OriginDrawError("The event source no longer matches the frozen source table.") from error
    if current != plan:
        raise OriginDrawError("The event plan no longer matches the source table.")
    row_y = dict(plan.row_trial_positions)
    groups = []
    for condition, source_rows in event_rows_by_condition(plan):
        rows = list(source_rows)
        groups.append(
            (
                condition,
                pd.DataFrame(
                    {
                        "SourceTime": frame.iloc[rows][plan.event_time_column].to_numpy(dtype=float),
                        "TrialOrdinal": np.asarray([row_y[row] for row in rows], dtype=float),
                        "SourceRow": np.asarray([row + 1 for row in rows], dtype=float),
                    }
                ),
            )
        )
    return tuple(groups)


def _verify_event_helper(actual: pd.DataFrame, expected: pd.DataFrame) -> dict[str, Any]:
    try:
        equal = np.array_equal(
            actual.loc[:, expected.columns].to_numpy(dtype=float), expected.to_numpy(dtype=float)
        )
    except (KeyError, TypeError, ValueError):
        equal = False
    if not equal:
        raise OriginDrawError("Origin changed an event helper's time, trial ordinal or source-row binding.")
    return {
        "event_count": len(expected),
        "source_time_exact": True,
        "trial_ordinal_exact": True,
        "source_row_exact": True,
    }


def _validate_event_layout(preparation: ScientificPreparation):
    spec = preparation.plot_spec
    plan, layout = spec.event_raster_plan, spec.event_raster_layout
    if plan is None or layout is None:
        raise OriginDrawError("The frozen event layout is missing.")
    expected = build_event_raster_layout(
        plan, spec.x_title, spec.y_title, palette_name=spec.display_plan.figure_style.palette_name
    )
    if (
        layout != expected
        or spec.display_plan.figure_style != layout.style
        or spec.display_plan.marker_size_pt != layout.marker_size_pt
    ):
        raise OriginDrawError("The event layout no longer matches its physical contract.")
    axis = spec.axis_plan
    if (
        (axis.x_from, axis.x_to) != layout.x_range
        or (axis.y_from, axis.y_to) != layout.y_range
        or axis.y_step != layout.y_step
        or axis.x_step is None
        or not math.isfinite(axis.x_step)
        or axis.x_step <= 0
        or spec.x_scale != "linear"
        or spec.y_scale != "linear"
    ):
        raise OriginDrawError(
            "The event axis layout must preserve frozen coordinates and source trial order."
        )
    try:
        validate_event_time_title(spec.x_title, plan.time_unit)
    except ValueError as error:
        raise OriginDrawError(str(error)) from error
    return layout


def _verify_event_axes(op: Any, layer: Any, preparation: ScientificPreparation) -> dict[str, Any]:
    from .evidence_renderer import _axis_state
    from .scientific_renderer import _origin_font_code

    state = _axis_state(layer)
    axis, style = preparation.plot_spec.axis_plan, preparation.plot_spec.display_plan.figure_style
    expected_font = _origin_font_code(op, style.font_family)
    for name, limits in (
        ("x", (axis.x_from, axis.x_to, axis.x_step)),
        ("y", (axis.y_from, axis.y_to, -axis.y_step)),
    ):
        tolerance = 16 * math.ulp(max(abs(value) for value in limits))
        for prop, expected in zip(("from", "to", "inc"), limits, strict=True):
            value = float(state[f"{name}.{prop}"])
            if not math.isfinite(value) or not math.isclose(
                value, expected, rel_tol=1e-10, abs_tol=tolerance
            ):
                raise OriginDrawError(f"Origin event {name}.{prop} differs from its frozen coordinate plan.")
        for prop, expected in (
            ("showAxes", 3),
            ("atZero", 0),
            ("label.table", 0),
            ("type", 1),
            ("showLabels", 1 if name == "x" else 0),
            ("label.font", expected_font),
        ):
            if int(state[f"{name}.{prop}"]) != expected:
                raise OriginDrawError(f"Origin event {name}.{prop} violates the frozen axis contract.")
        for prop, expected in (
            ("label.pt", style.tick_label_size_pt),
            ("thickness", style.frame_line_width_pt),
            ("label.rotate", 0),
        ):
            if not math.isclose(float(state[f"{name}.{prop}"]), expected, rel_tol=0, abs_tol=0.05):
                raise OriginDrawError(
                    f"Origin event {name}.{prop} violates the physical font/frame contract."
                )
    if state["y.ticks"] != 0 or state["y.minorTicks"] != 0:
        raise OriginDrawError("Trial labels must use source IDs, not numeric Y ticks.")
    return state


def _verify_event_y_title(
    label: Any, layout: Any, page_width: float, page_height: float, *, expected_text: str | None = None
) -> dict[str, float]:
    if expected_text is not None:
        from .evidence_renderer import _verify_page_label_text

        _verify_page_label_text(str(label.text), rf"\b({expected_text})", "EventYTitle")
    center_x = (label.get_float("left") + label.get_float("width") / 2) / page_width * 100
    center_y = (label.get_float("top") + label.get_float("height") / 2) / page_height * 100
    if (
        label.get_int("attach") != 1
        or not math.isclose(center_x, layout.y_title_x_percent, rel_tol=0, abs_tol=0.03)
        or not math.isclose(center_y, layout.y_title_y_percent, rel_tol=0, abs_tol=0.03)
    ):
        raise OriginDrawError("The event Y title moved into the reserved trial-label column.")
    return {"center_x_percent": center_x, "center_y_percent": center_y}


def build_event_raster_graph(op: Any, frame: pd.DataFrame, preparation: ScientificPreparation):
    from . import evidence_renderer as evidence
    from .scientific_renderer import (
        _apply_page_layer,
        _clean_numeric_x_axis,
        _position_x_title,
        _set_axis_titles,
        _title_geometry,
    )
    from .signal_stack_renderer import _clear_fresh_layer_objects
    from .verify_utils import (
        verify_page_and_layer,
        verify_plot_color,
        verify_symbol_style,
        verify_text_fonts,
        verify_text_sizes,
    )

    groups = _prepare_event_raster_data(frame, preparation)
    layout = _validate_event_layout(preparation)
    plan, style, axis = preparation.plot_spec.event_raster_plan, layout.style, preparation.plot_spec.axis_plan
    source_snapshot = frame.copy(deep=True)
    imported = _event_source_copy(frame, plan)
    source_sheet = evidence._source_sheet(op, imported, preparation)
    graph = op.new_graph("Supplied event raster", template="Scatter")
    if graph is None or len(graph) != 1:
        raise OriginDrawError("Origin must create one fresh single-layer event graph.")
    layer = graph[0]
    cleanup = _clear_fresh_layer_objects(layer)
    _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    colors, helpers, symbols, color_state = dict(layout.condition_colors), [], {}, {}
    for condition, data in groups:
        if data.empty:
            continue  # Its source inventory and legend remain; no invented event or placeholder plot.
        index = len(helpers) + 1
        sheet = op.new_sheet("w", f"Event Condition {index}")
        if sheet is None:
            raise OriginDrawError("Origin could not create an event helper worksheet.")
        sheet.from_df(data)
        sheet.cols_axis("xyy")
        plot = layer.add_plot(sheet, "TrialOrdinal", "SourceTime", type="s")
        if plot is None:
            raise OriginDrawError("Origin could not create the source-bound event marks.")
        plot.color = colors[condition]
        plot.symbol_kind = 10
        plot.symbol_size = layout.marker_size_pt
        plot.set_cmd("-kf 1", f"-kh {layout.marker_edge_percent:g}")
        symbols[condition] = verify_symbol_style(
            op,
            plot,
            expected_size_pt=layout.marker_size_pt,
            expected_edge_percent=layout.marker_edge_percent,
            expected_symbol_kind=10,
            expected_symbol_interior=1,
        )
        color_state[condition] = verify_plot_color(
            op, plot, colors[condition], variable_name=f"__event_color{index}"
        )
        helpers.append((condition, sheet, data))
    layer.rescale()
    graph.activate()
    layer.activate()
    _clean_numeric_x_axis(op, graph)
    for name in ("x", "y"):
        layer.set_int(f"{name}.type", 1)
        layer.set_int(f"{name}.label.table", 0)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=False)
    titles = _set_axis_titles(op, layer, preparation)
    titles["x_title"].set_float("rotate", 0)
    titles["y_title"].set_float("rotate", 90)
    op.lt_exec("doc -uw;")
    _position_x_title(op, titles["x_title"], style)
    page_width, page_height = float(op.lt_float("page.width")), float(op.lt_float("page.height"))
    for name in ("Legend", "legend"):
        evidence._remove_label(layer, name)
    labels, anchors = {}, {}
    for text, ordinal, right, center_y in layout.trial_labels:
        name = f"EventTrial{ordinal}"
        obj, _ = evidence._add_shap_page_label(
            op,
            graph,
            layer,
            name=name,
            text=text,
            center_x_percent=right - 2,
            center_y_percent=center_y,
            size_pt=style.legend_size_pt,
            font_family=style.font_family,
            bold=False,
        )
        obj.set_float("left", page_width * right / 100 - obj.get_float("width"))
        labels[name], anchors[name] = obj, ("right", right, center_y, text)
    for index, (condition, left, center_y) in enumerate(layout.condition_labels, 1):
        name = f"EventCondition{index}"
        obj, _ = evidence._add_shap_page_label(
            op,
            graph,
            layer,
            name=name,
            text=condition,
            center_x_percent=left + 2,
            center_y_percent=center_y,
            size_pt=style.legend_size_pt,
            font_family=style.font_family,
            bold=False,
            color=colors[condition],
        )
        obj.set_float("left", page_width * left / 100)
        obj.set_int("showframe", 0)
        if obj.get_int("showframe") != 0 or obj.get_int("color") != op.ocolor(colors[condition]):
            raise OriginDrawError("An event condition legend lost its borderless color mapping.")
        labels[name], anchors[name] = obj, ("left", left, center_y, condition)
    layer.axis("x").set_limits(axis.x_from, axis.x_to, axis.x_step)
    layer.axis("y").set_limits(axis.y_from, axis.y_to, -axis.y_step)
    for prop in ("showLabels", "showlabel", "label.show", "ticks", "minorTicks"):
        layer.set_int(f"y.{prop}", 0)
    op.lt_exec("doc -uw;")
    # YL is a special axis-owned object: Origin can move it after refresh/save.
    # Keep its axis information, but display an ordinary editable page label.
    titles["y_title"].set_int("show", 0)
    page_title, _ = evidence._add_shap_page_label(
        op,
        graph,
        layer,
        name="EventYTitle",
        text=rf"\b({preparation.plot_spec.y_title})",
        center_x_percent=layout.y_title_x_percent,
        center_y_percent=layout.y_title_y_percent,
        size_pt=style.axis_title_size_pt,
        font_family=style.font_family,
        bold=True,
        rotation_deg=90,
        color="#000000",
    )
    titles["y_title"] = page_title
    op.lt_exec("doc -uw;")
    if layer.label("yl").get_int("show") != 0:
        raise OriginDrawError("Origin restored an unwanted automatic Y title.")
    y_title_anchor = _verify_event_y_title(
        titles["y_title"], layout, page_width, page_height, expected_text=preparation.plot_spec.y_title
    )
    axis_state = _verify_event_axes(op, layer, preparation)
    geometry = verify_page_and_layer(graph, layer, origin=op, style=style)
    label_state = _title_geometry(op, {**titles, **labels})
    for name, (edge, x, y, text) in anchors.items():
        obj = labels[name]
        actual_x = obj.get_float("left") + (obj.get_float("width") if edge == "right" else 0)
        actual_y = obj.get_float("top") + obj.get_float("height") / 2
        if not math.isclose(actual_x / page_width * 100, x, rel_tol=0, abs_tol=0.03) or not math.isclose(
            actual_y / page_height * 100, y, rel_tol=0, abs_tol=0.03
        ):
            raise OriginDrawError("An event trial/condition label moved away from its frozen position.")
        evidence._verify_page_label_text(str(obj.text), text, name)
    try:
        pd.testing.assert_frame_equal(frame, source_snapshot, check_exact=True)
        pd.testing.assert_frame_equal(
            source_sheet.to_df(), imported, check_dtype=False, check_categorical=False, check_exact=True
        )
    except AssertionError as error:
        raise OriginDrawError("Origin changed the event source table.") from error
    helper_state, bindings = {}, []
    for index, (condition, sheet, data) in enumerate(helpers, 1):
        helper_state[condition] = _verify_event_helper(sheet.to_df(), data)
        bindings.append(
            evidence._read_shap_plot_binding(
                op,
                layer,
                f"[{graph.name}]1!{index}",
                sheet,
                "SourceTime",
                "TrialOrdinal",
                prefix=f"event{index}",
            )
        )
    pids = [layer.get_int(f"plot{index}.pid") for index in range(1, len(layer.plot_list()) + 1)]
    if pids != [201] * len(helpers):
        raise OriginDrawError("The raster must retain exactly its supplied-event Scatter plots.")
    fonts = verify_text_fonts(op, {**titles, **labels}, style.font_family)
    sizes = verify_text_sizes(
        {**titles, **labels},
        {**dict.fromkeys(titles, style.axis_title_size_pt), **dict.fromkeys(labels, style.legend_size_pt)},
    )
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {**label_state, **fonts, **sizes},
        "origin_plot_state": {"event_symbols": symbols, "condition_colors": color_state},
        "origin_event_raster_readback": {
            "y_title_anchor": y_title_anchor,
            "y_title_object": "EventYTitle",
            "native_y_title_hidden": True,
            "event_count": len(plan.event_rows),
            "trial_count": len(plan.trial_order),
            "inventory_rows": plan.inventory_rows,
            "empty_trial_ids": plan.empty_trial_ids,
            "trial_order": plan.trial_order,
            "trial_conditions": plan.trial_conditions,
            "event_count_per_condition": {condition: len(data) for condition, data in groups},
            "source_sheet_range": source_sheet.lt_range(),
            "condition_helper_sheets": {condition: sheet.lt_range() for condition, sheet, _data in helpers},
            "helpers": helper_state,
            "plot_bindings": bindings,
            "native_plot_types": pids,
            "source_dataframe_unchanged": True,
            "source_table_values_roundtrip_checked": True,
            "template_cleanup": cleanup,
            "label_anchors": anchors,
        },
        "origin_helper_columns": ["SourceTime", "TrialOrdinal", "SourceRow"],
        "origin_plot_data_columns": [plan.event_time_column, plan.trial_column, plan.condition_column],
        "title_objects": list(titles),
    }
