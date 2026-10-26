"""Native source-bound response bands; the existing caller owns sessions and exports."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from ..event_response import EventResponsePlan, build_event_response_plan, validate_event_response_titles
from ..event_response_layout import build_event_response_layout
from ..scientific_workflow import ScientificPreparation, _nice_number, load_scientific_frame
from .safe_errors import OriginDrawError


def _response_source_copy(frame: pd.DataFrame, plan: EventResponsePlan) -> pd.DataFrame:
    imported = frame.copy(deep=True)
    for column in imported:
        values = imported[column]
        if column == plan.condition_column:
            imported[column] = pd.Categorical(values.map(str), categories=plan.condition_order, ordered=True)
        elif len(values.dropna()) and all(isinstance(value, str) for value in values.dropna()):
            imported[column] = pd.Categorical(values, categories=pd.unique(values.dropna()), ordered=True)
    return imported


def _prepare_event_response_data(frame: pd.DataFrame, preparation: ScientificPreparation):
    plan = preparation.plot_spec.event_response_plan
    if plan is None or preparation.requires_confirmation:
        raise OriginDrawError("The source-bound event-response plan is missing or incomplete.")
    try:
        source = load_scientific_frame(preparation.source_path, preparation)
        pd.testing.assert_frame_equal(frame, source, check_exact=True)
        current = build_event_response_plan(
            frame,
            time_column=plan.time_column,
            mean_column=plan.mean_column,
            lower_column=plan.lower_column,
            upper_column=plan.upper_column,
            condition_column=plan.condition_column,
            time_unit=plan.time_unit,
            response_unit=plan.response_unit,
            interval_label=plan.interval_label,
        )
    except (ValueError, AssertionError) as error:
        raise OriginDrawError(
            "The event-response source no longer matches its frozen source table."
        ) from error
    if current != plan or dict(preparation.scientific_context) != {
        "time_unit": plan.time_unit,
        "response_unit": plan.response_unit,
        "interval_label": plan.interval_label,
    }:
        raise OriginDrawError("The event-response source plan or declarations no longer match.")
    return tuple(
        (
            condition,
            pd.DataFrame(
                {
                    "SourceTime": frame.iloc[list(rows)][plan.time_column].to_numpy(dtype=float),
                    "Upper": frame.iloc[list(rows)][plan.upper_column].to_numpy(dtype=float),
                    "Lower": frame.iloc[list(rows)][plan.lower_column].to_numpy(dtype=float),
                    "Mean": frame.iloc[list(rows)][plan.mean_column].to_numpy(dtype=float),
                    "SourceRow": np.asarray(rows, dtype=float) + 1,
                }
            ),
        )
        for condition, rows in plan.condition_rows
    )


def _verify_response_helper(actual: pd.DataFrame, expected: pd.DataFrame) -> dict[str, Any]:
    try:
        equal = tuple(actual.columns) == tuple(expected.columns) and np.array_equal(
            actual.to_numpy(dtype=float),
            expected.to_numpy(dtype=float),
        )
    except (KeyError, TypeError, ValueError):
        equal = False
    if not equal:
        raise OriginDrawError("Origin changed an event-response helper's bounds, mean, time or source row.")
    return {
        "rows": len(expected),
        "source_values_exact": True,
        "source_time_exact": True,
        "bounds_exact": True,
        "mean_exact": True,
        "source_row_exact": True,
    }


def _validate_response_layout(preparation: ScientificPreparation):
    spec = preparation.plot_spec
    plan, layout, style = spec.event_response_plan, spec.event_response_layout, spec.display_plan.figure_style
    if plan is None or layout is None or style is None:
        raise OriginDrawError("The frozen event-response layout is missing.")
    try:
        validate_event_response_titles(plan, spec.x_title, spec.y_title)
    except ValueError as error:
        raise OriginDrawError(str(error)) from error
    expected = build_event_response_layout(plan, spec.x_title, spec.y_title, palette_name=style.palette_name)
    if layout != expected or style != layout.style:
        raise OriginDrawError("The event-response layout no longer matches its physical contract.")
    axis = spec.axis_plan
    expected_steps = tuple(
        _nice_number(bounds[1] / 5 - bounds[0] / 5, round_value=True)
        for bounds in (plan.x_range, plan.y_range)
    )
    if (
        (axis.x_from, axis.x_to) != plan.x_range
        or (axis.y_from, axis.y_to) != plan.y_range
        or (axis.x_step, axis.y_step) != expected_steps
        or spec.x_scale != "linear"
        or spec.y_scale != "linear"
        or any(not math.isfinite(value) or value <= 0 for value in expected_steps)
    ):
        raise OriginDrawError("The event-response axis layout changed its supplied-coordinate contract.")
    return layout


def _literal_label(
    op, graph, layer, *, name, text, anchor, size, font, color="#000000", bold=False, rotation=0, left=False
):
    from .evidence_renderer import _add_shap_page_label

    obj, _ = _add_shap_page_label(
        op,
        graph,
        layer,
        name=name,
        text="Text",
        center_x_percent=anchor[0],
        center_y_percent=anchor[1],
        size_pt=size,
        font_family=font,
        bold=bold,
        rotation_deg=rotation,
        color=color,
    )
    obj.set_int("link", 0)
    if obj.get_int("link") != 0:
        raise OriginDrawError("Origin did not retain literal event-response text mode.")
    obj.text = rf"\b({text})" if bold else text
    obj.set_int("showframe", 0)
    op.lt_exec("doc -uw;")
    page_width, page_height = op.lt_float("page.width"), op.lt_float("page.height")
    obj.set_float("left", page_width * anchor[0] / 100 - (0 if left else obj.get_float("width") / 2))
    obj.set_float("top", page_height * anchor[1] / 100 - obj.get_float("height") / 2)
    return obj


def _verify_text(op, layer, preparation):
    from .verify_utils import verify_text_fonts, verify_text_sizes

    spec = preparation.plot_spec
    plan, layout = spec.event_response_plan, spec.event_response_layout
    style = layout.style
    expected = {
        "ResponseYTitle": (
            spec.y_title,
            layout.y_title_center,
            style.axis_title_size_pt,
            90,
            False,
            True,
            "#000000",
        ),
        "ResponseInterval": (
            plan.interval_label,
            layout.interval_label_center,
            style.legend_size_pt,
            0,
            False,
            False,
            "#000000",
        ),
    }
    colors = dict(layout.condition_colors)
    for index, (text, x, y) in enumerate(layout.condition_labels):
        expected[f"ResponseCondition{index}"] = (
            text,
            (x, y),
            style.legend_size_pt,
            0,
            True,
            False,
            colors[text],
        )
    page_width, page_height = float(op.lt_float("page.width")), float(op.lt_float("page.height"))
    state, objects, sizes = {}, {}, {}
    for name, (text, anchor, size, rotation, left, bold, color) in expected.items():
        obj = layer.label(name)
        native_text = rf"\b({text})" if bold else text
        if obj is None or str(obj.text).replace("\r\n", "\n") != native_text.replace("\r\n", "\n"):
            raise OriginDrawError(f"Origin event-response text no longer matches its declaration: {name}.")
        values = {key: float(obj.get_float(key)) for key in ("left", "top", "width", "height", "rotate")}
        if not all(math.isfinite(value) for value in values.values()):
            raise OriginDrawError("Origin event-response text geometry is not finite.")
        actual_x = values["left"] + (0 if left else values["width"] / 2)
        actual_y = values["top"] + values["height"] / 2
        if (
            not math.isclose(actual_x / page_width * 100, anchor[0], rel_tol=0, abs_tol=0.03)
            or not math.isclose(actual_y / page_height * 100, anchor[1], rel_tol=0, abs_tol=0.03)
            or abs(values["rotate"] - rotation) > 0.1
            or obj.get_int("attach") != 1
            or obj.get_int("link") != 0
            or obj.get_int("showframe") != 0
            or obj.get_int("show") != 1
            or obj.get_int("color") != op.ocolor(color)
            or values["width"] <= 0
            or values["height"] <= 0
            or values["left"] < 0
            or values["top"] < 0
            or values["left"] + values["width"] > page_width
            or values["top"] + values["height"] > page_height
        ):
            raise OriginDrawError(f"Origin event-response text moved or lost its style: {name}.")
        objects[name], sizes[name] = obj, size
        state[name] = {
            "text": text,
            "native_text": str(obj.text),
            "bold_format": bold,
            "anchor": anchor,
            "left_aligned": left,
            "link": 0,
            **values,
        }
    x_title = layer.label("xb")
    if x_title is None or str(x_title.text) != rf"\b({spec.x_title})" or x_title.get_int("link") != 0:
        raise OriginDrawError("Origin changed the event-response X title.")
    if layer.label("yl").get_int("show") != 0:
        raise OriginDrawError("Origin restored a duplicate event-response Y title.")
    objects["x_title"], sizes["x_title"] = x_title, style.axis_title_size_pt
    try:
        state.update(verify_text_fonts(op, objects, style.font_family))
        state.update(verify_text_sizes(objects, sizes))
    except RuntimeError as error:
        raise OriginDrawError(str(error)) from error
    return state


def verify_event_response_graph(op, graph, preparation, *, source_sheet, helpers):
    """Re-read native source, fills, bindings, axes and labels after final refresh/export."""
    from . import evidence_renderer as evidence
    from .base_style_contract import pt_to_origin_width_units
    from .verify_utils import NativePlotReference, _read_plot_option, verify_page_and_layer, verify_plot_color

    layout = _validate_response_layout(preparation)
    plan, axis, style = (
        preparation.plot_spec.event_response_plan,
        preparation.plot_spec.axis_plan,
        layout.style,
    )
    graph.activate()
    layer = graph[0]
    layer.activate()
    geometry = verify_page_and_layer(graph, layer, origin=op, style=style)
    expected_axes = {
        "x.from": axis.x_from,
        "x.to": axis.x_to,
        "x.inc": axis.x_step,
        "y.from": axis.y_from,
        "y.to": axis.y_to,
        "y.inc": axis.y_step,
    }
    axis_state = evidence._axis_state(layer)
    for key, value in expected_axes.items():
        if not math.isclose(axis_state[key], value, rel_tol=1e-9, abs_tol=1e-9):
            raise OriginDrawError(f"Origin changed an event-response numeric axis: {key}.")
    for name in ("x", "y"):
        for prop, value in (
            ("type", 1),
            ("showAxes", 3),
            ("showLabels", 1),
            ("label.table", 0),
            ("minorTicks", 1),
            ("label.pt", style.tick_label_size_pt),
            ("label.font", op.lt_float(f"font({style.font_family})")),
        ):
            if abs(axis_state[f"{name}.{prop}"] - value) > 0.05:
                raise OriginDrawError("Origin changed event-response axis visibility or typography.")
    current = load_scientific_frame(preparation.source_path, preparation)
    try:
        pd.testing.assert_frame_equal(
            source_sheet.to_df(),
            _response_source_copy(current, plan),
            check_dtype=False,
            check_categorical=False,
            check_exact=True,
        )
    except AssertionError as error:
        raise OriginDrawError("Origin changed the event-response source workbook.") from error
    groups = _prepare_event_response_data(current, preparation)
    if len(helpers) != len(groups) or len(layer.plot_list()) != len(groups) * 3:
        raise OriginDrawError("Origin changed the source-bound response plot/helper count.")
    bindings, fills, means, helper_state = [], [], [], {}
    colors = dict(layout.condition_colors)
    count = len(groups)
    for index, ((condition, data), (recorded, sheet)) in enumerate(zip(groups, helpers, strict=True)):
        if recorded != condition:
            raise OriginDrawError("Origin response helpers changed condition order.")
        helper_state[condition] = _verify_response_helper(sheet.to_df(), data)
        slots = ((2 * index + 1, "Upper"), (2 * index + 2, "Lower"), (2 * count + index + 1, "Mean"))
        for slot, column in slots:
            if layer.get_int(f"plot{slot}.pid") != 200:
                raise OriginDrawError("Response intervals require native Line plots.")
            bindings.append(
                evidence._read_shap_plot_binding(
                    op,
                    layer,
                    f"[{graph.name}]1!{slot}",
                    sheet,
                    "SourceTime",
                    column,
                    prefix=f"response{slot}",
                )
            )
        upper_slot, lower_slot, mean_slot = [slot for slot, _ in slots]
        reference = NativePlotReference(f"[{graph.name}]1!{upper_slot}", layer.obj)
        values = {
            option: _read_plot_option(op, reference, option, f"__response_{index}_{option[1:]}")
            for option in ("-pf", "-pfv", "-pfm", "-p2fm", "-pfb", "-p2fb", "-pfn", "-paaf", "-lfp")
        }
        expected_fill = {
            "-pf": 1,
            "-pfv": 9,
            "-pfm": 1,
            "-p2fm": 1,
            "-pfn": 1,
            "-paaf": 0,
            "-lfp": 0,
            "-pfb": op.ocolor(colors[condition]),
            "-p2fb": op.ocolor(colors[condition]),
        }
        if any(values[key] != expected for key, expected in expected_fill.items()):
            raise OriginDrawError("Origin response band lost its adjacent Lower target or flat fill style.")
        opacity = {
            slot: float(layer.get_float(f"plot{slot}.transparency"))
            for slot in (upper_slot, lower_slot, mean_slot)
        }
        if (
            opacity[upper_slot] != style.fill_transparency_percent
            or opacity[lower_slot] != 100
            or opacity[mean_slot] != 0
        ):
            raise OriginDrawError("Origin changed response-band or mean-line transparency.")
        mean_ref = NativePlotReference(f"[{graph.name}]1!{mean_slot}", layer.obj)
        width = _read_plot_option(op, mean_ref, "-w", f"__response_mean_width{index}")
        if abs(width - pt_to_origin_width_units(style.plot_line_width_pt)) > 0.05:
            raise OriginDrawError("Origin changed the response mean-line width.")
        color = verify_plot_color(op, mean_ref, colors[condition], variable_name=f"__response_color{index}")
        fills.append(
            {
                "condition": condition,
                "upper_slot": upper_slot,
                "lower_slot": lower_slot,
                "native_options": values,
                "transparency": opacity[upper_slot],
            }
        )
        means.append(
            {
                "condition": condition,
                "slot": mean_slot,
                "width_units": width,
                "transparency": opacity[mean_slot],
                "color": color,
            }
        )
    reference = layer.label("DeclaredEventOrigin")
    zero_state = None
    if plan.zero_time_visible:
        if reference is None:
            raise OriginDrawError("Origin lost the declared event-zero reference.")
        zero_state = {
            key: float(reference.get_float(key))
            for key in (
                "x1",
                "x2",
                "y1",
                "y2",
                "attach",
                "arrowbeginwidth",
                "arrowbeginlength",
                "arrowendwidth",
                "arrowendlength",
            )
        }
        if (
            zero_state["attach"] != 2
            or zero_state["x1"] != 0
            or zero_state["x2"] != 0
            or not math.isclose(zero_state["y1"], plan.y_range[0], rel_tol=1e-9, abs_tol=1e-9)
            or not math.isclose(zero_state["y2"], plan.y_range[1], rel_tol=1e-9, abs_tol=1e-9)
            or any(zero_state[key] != 0 for key in zero_state if key.startswith("arrow"))
        ):
            raise OriginDrawError("Origin event-zero object is not an arrow-free data-coordinate reference.")
    elif reference is not None:
        raise OriginDrawError("Origin added a zero reference outside the supplied event domain.")
    return {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": _verify_text(op, layer, preparation),
        "origin_plot_state": {"fills": fills, "means": means},
        "origin_event_response_readback": {
            "source_values_exact": True,
            "helpers": helper_state,
            "plot_bindings": bindings,
            "condition_helpers": {name: sheet.lt_range() for name, sheet in helpers},
            "source_sheet": source_sheet.lt_range(),
            "condition_order": plan.condition_order,
            "event_zero": zero_state,
            "source_row_count": len(current),
        },
    }


def build_event_response_graph(op: Any, frame: pd.DataFrame, preparation: ScientificPreparation):
    from . import evidence_renderer as evidence
    from .base_style_contract import pt_to_origin_width_units
    from .scientific_renderer import (
        _apply_page_layer,
        _clean_numeric_x_axis,
        _position_x_title,
        _set_axis_titles,
    )
    from .signal_stack_renderer import _clear_fresh_layer_objects

    groups = _prepare_event_response_data(frame, preparation)
    layout = _validate_response_layout(preparation)
    spec, style = preparation.plot_spec, layout.style
    source_sheet = op.new_sheet("w", "Event response source")
    source_sheet.from_df(_response_source_copy(frame, spec.event_response_plan))
    graph = op.new_graph("Supplied event response", template="Line")
    layer = graph[0]
    _clear_fresh_layer_objects(layer)
    _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    colors, helpers = dict(layout.condition_colors), []
    for index, (condition, data) in enumerate(groups):
        sheet = op.new_sheet("w", f"Response condition {index + 1}")
        sheet.from_df(data)
        sheet.cols_axis("xyyyy")
        upper = layer.add_plot(sheet, "Upper", "SourceTime", type="l")
        lower = layer.add_plot(sheet, "Lower", "SourceTime", type="l")
        upper.color = lower.color = colors[condition]
        upper.set_cmd(f"-w {pt_to_origin_width_units(0.01)}")
        lower.set_cmd(f"-w {pt_to_origin_width_units(0.01)}")
        upper.transparency, lower.transparency = style.fill_transparency_percent, 100
        graph.activate()
        layer.activate()
        upper.set_fill_area(above=op.ocolor(colors[condition]), type=9, below=op.ocolor(colors[condition]))
        upper.set_cmd("-pfm 1", "-p2fm 1", "-pfn 1", "-paaf 0")
        helpers.append((condition, sheet))
    for condition, sheet in helpers:
        mean = layer.add_plot(sheet, "Mean", "SourceTime", type="l")
        mean.color, mean.transparency = colors[condition], 0
        mean.set_cmd(f"-w {pt_to_origin_width_units(style.plot_line_width_pt)}")
    graph.activate()
    layer.activate()
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=True)
    safe = replace(preparation, plot_spec=replace(spec, x_title="Response time", y_title="Response value"))
    titles = _set_axis_titles(op, layer, safe)
    for name, text in (("x_title", spec.x_title), ("y_title", spec.y_title)):
        titles[name].set_int("link", 0)
        if titles[name].get_int("link") != 0:
            raise OriginDrawError("Origin could not retain literal response axis titles.")
        titles[name].text = rf"\b({text})"
    titles["y_title"].set_int("show", 0)
    titles["x_title"].set_float("rotate", 0)
    op.lt_exec("doc -uw;")
    _position_x_title(op, titles["x_title"], style)
    for name in ("legend", "Legend"):
        evidence._remove_label(layer, name)
    for index, (condition, x, y) in enumerate(layout.condition_labels):
        _literal_label(
            op,
            graph,
            layer,
            name=f"ResponseCondition{index}",
            text=condition,
            anchor=(x, y),
            size=style.legend_size_pt,
            font=style.font_family,
            color=colors[condition],
            left=True,
        )
    _literal_label(
        op,
        graph,
        layer,
        name="ResponseInterval",
        text=spec.event_response_plan.interval_label,
        anchor=layout.interval_label_center,
        size=style.legend_size_pt,
        font=style.font_family,
    )
    _literal_label(
        op,
        graph,
        layer,
        name="ResponseYTitle",
        text=spec.y_title,
        anchor=layout.y_title_center,
        size=style.axis_title_size_pt,
        font=style.font_family,
        bold=True,
        rotation=90,
    )
    layer.axis("x").set_limits(spec.axis_plan.x_from, spec.axis_plan.x_to, spec.axis_plan.x_step)
    layer.axis("y").set_limits(spec.axis_plan.y_from, spec.axis_plan.y_to, spec.axis_plan.y_step)
    for name in ("x", "y"):
        layer.set_int(f"{name}.minorTicks", 1)
    if spec.event_response_plan.zero_time_visible:
        reference = layer.add_line(0, spec.axis_plan.y_from, 0, spec.axis_plan.y_to)
        reference.name, reference.width, reference.color = "DeclaredEventOrigin", 1, "#9AA7AE"
        for key in ("arrowbeginwidth", "arrowbeginlength", "arrowendwidth", "arrowendlength"):
            reference.set_float(key, 0)
    op.lt_exec("doc -uw;")
    return graph, verify_event_response_graph(
        op, graph, preparation, source_sheet=source_sheet, helpers=helpers
    )
