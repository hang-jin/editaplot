"""Native Line plots for an explicit, display-only common-amplitude signal stack.

The caller owns Origin sessions, capability probes, saving and exports. This
builder does not filter or resample.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from ..scientific_visual import interpolate_hex_colors
from ..scientific_workflow import ScientificPreparation
from ..signal_stack import SignalStackPlan, build_signal_stack_plan
from ..signal_stack_layout import build_signal_stack_layout
from .base_style_contract import pt_to_origin_width_units
from .safe_errors import OriginDrawError

REFERENCE_COLOR = "#52616B"
SOURCE_RECOVERY_TOLERANCE = 1e-12


def _signal_import_copy(frame: pd.DataFrame, plan: SignalStackPlan) -> pd.DataFrame:
    """Use originpro's documented categorical-to-DF_TEXT path for source labels."""
    imported = frame.copy(deep=True)
    for column in imported:
        values = imported[column]
        if column == plan.channel_column:
            imported[column] = pd.Categorical(values.map(str), categories=plan.channel_order, ordered=True)
        elif len(values.dropna()) and all(isinstance(value, str) for value in values.dropna()):
            imported[column] = pd.Categorical(values, categories=pd.unique(values.dropna()), ordered=True)
    return imported


def _prepare_signal_channel_data(
    frame: pd.DataFrame, plan: SignalStackPlan
) -> tuple[tuple[str, pd.DataFrame], ...]:
    try:
        current = build_signal_stack_plan(
            frame,
            time_column=plan.time_column,
            value_column=plan.value_column,
            channel_column=plan.channel_column,
            time_unit=plan.time_unit,
            value_unit=plan.value_unit,
        )
    except ValueError as error:
        raise OriginDrawError(f"Invalid signal source table: {error}") from error
    if current != plan:
        raise OriginDrawError("The signal stack plan no longer matches its source table.")
    offsets = dict(plan.offsets)
    channels = []
    for label, positions in plan.channel_rows:
        source = frame.iloc[list(positions)]
        amplitude = source[plan.value_column].to_numpy(dtype=float, copy=True)
        plot_frame = pd.DataFrame(
            {
                "SourceTime": source[plan.time_column].to_numpy(dtype=float, copy=True),
                "SourceAmplitude": amplitude,
                "PlotY": amplitude + offsets[label],
            }
        )
        # Large offsets must not silently erase low-amplitude source detail.
        _verify_signal_helper_arrays(plot_frame, plot_frame, label, offsets[label])
        channels.append((label, plot_frame))
    return tuple(channels)


def _verify_signal_helper_arrays(
    actual: pd.DataFrame, expected: pd.DataFrame, label: str, offset: float
) -> dict[str, Any]:
    try:
        array = actual.loc[:, expected.columns].to_numpy(dtype=float)
        equal = len(actual) == len(expected) and np.array_equal(array, expected.to_numpy(dtype=float))
        recovered = actual["PlotY"].to_numpy(dtype=float) - offset
        preserves_amplitude = len(actual) == len(expected) and np.allclose(
            recovered,
            expected["SourceAmplitude"].to_numpy(dtype=float),
            rtol=SOURCE_RECOVERY_TOLERANCE,
            atol=SOURCE_RECOVERY_TOLERANCE,
        )
    except (KeyError, TypeError, ValueError):
        equal = preserves_amplitude = False
    if not equal or not preserves_amplitude:
        raise OriginDrawError(f"Origin signal helper changed source time or amplitude: {label}.")
    return {
        "count": len(expected),
        "source_time_exact": True,
        "source_amplitude_exact": True,
        "plot_y_exact": True,
        "offset_subtraction_preserves_amplitude": True,
        "source_recovery_relative_tolerance": SOURCE_RECOVERY_TOLERANCE,
        "source_recovery_absolute_tolerance": SOURCE_RECOVERY_TOLERANCE,
    }


def _resolve_signal_stack_layout(preparation: ScientificPreparation, plan: SignalStackPlan) -> dict[str, Any]:
    spec = preparation.plot_spec
    if spec.x_scale != "linear" or spec.y_scale != "linear":
        raise OriginDrawError("Signal stacks require linear frozen axes to preserve amplitude units.")
    for title, unit in ((spec.x_title, plan.time_unit), (spec.y_title, plan.value_unit)):
        if not title or re.search(rf"(?<!\w){re.escape(unit.strip())}(?!\w)", title) is None:
            raise OriginDrawError("Signal stack frozen axis titles must include the supplied units.")
    axis = spec.axis_plan
    limits = (axis.x_from, axis.x_to, axis.x_step, axis.y_from, axis.y_to, axis.y_step)
    if any(value is None or not math.isfinite(value) for value in limits):
        raise OriginDrawError("Signal stack axes require finite frozen limits and steps.")
    x0, x1, dx, y0, y1, dy = (float(value) for value in limits)
    if x1 <= x0 or y1 <= y0 or dx <= 0 or dy <= 0:
        raise OriginDrawError("Signal stack axes require increasing frozen limits and positive steps.")
    if (x0, x1) != plan.time_range:
        raise OriginDrawError("Signal frozen X limits must equal the supplied time extent.")
    try:
        expected = build_signal_stack_layout(plan, spec.display_plan.figure_style, y_range=(y0, y1))
    except ValueError as error:
        raise OriginDrawError(str(error)) from error
    if expected != spec.signal_stack_layout:
        raise OriginDrawError("The frozen signal label/ruler layout differs from its physical contract.")
    return {**asdict(expected), "x_step": dx, "y_step": dy, "source_time_range": plan.time_range}


def _clear_fresh_layer_objects(layer: Any) -> dict[str, Any]:
    """Clear inherited visible objects only on a new empty caller-owned layer."""
    if layer.plot_list():
        raise OriginDrawError("Template cleanup requires a fresh empty graph layer.")
    names = [obj.GetName() for obj in layer.obj.GraphObjects if not obj.GetName().startswith("__")]
    for name in names:
        layer.remove_label(name)
    remaining = [obj.GetName() for obj in layer.obj.GraphObjects if not obj.GetName().startswith("__")]
    if remaining:
        raise OriginDrawError("The new signal graph retained inherited template objects.")
    return {"removed_inherited_objects": names, "remaining_visible_objects": remaining}


def _verify_signal_ruler(op: Any, line: Any, layout: dict[str, Any], width: float) -> dict[str, Any]:
    expected = {
        "x1": layout["reference_x"],
        "x2": layout["reference_x"],
        "y1": layout["reference_y_from"],
        "y2": layout["reference_y_to"],
    }
    state = {key: float(line.get_float(key)) for key in expected}
    state.update(
        {
            "attach": line.get_int("attach"),
            "width_pt": float(line.width),
            "color": float(line.get_float("color")),
        }
    )
    for key in ("arrowbeginwidth", "arrowbeginlength", "arrowendwidth", "arrowendlength"):
        state[key] = float(line.get_float(key))
        if state[key] != 0:
            raise OriginDrawError("The amplitude ruler retained a nonzero arrowhead dimension.")
    if (
        state["attach"] != 2
        or not math.isclose(state["width_pt"], width, abs_tol=0.05)
        or state["color"] != op.ocolor(REFERENCE_COLOR)
        or any(
            not math.isclose(state[key], value, rel_tol=1e-10, abs_tol=1e-12)
            for key, value in expected.items()
        )
    ):
        raise OriginDrawError("The common amplitude ruler failed native geometry/style readback.")
    state["amplitude_length"] = state["y2"] - state["y1"]
    state["physical_height_cm"] = layout["reference_height_cm"]
    return state


def _verify_signal_axes(op: Any, layer: Any, style: Any, layout: dict[str, Any]) -> dict[str, Any]:
    from .evidence_renderer import _axis_state
    from .scientific_renderer import _origin_font_code

    state = _axis_state(layer)
    expected_font = _origin_font_code(op, style.font_family)
    state["font_code_expected"] = expected_font
    for axis in ("x", "y"):
        for prop, expected in zip(
            ("from", "to", "inc"), (*layout[f"{axis}_range"], layout[f"{axis}_step"]), strict=True
        ):
            actual = float(state[f"{axis}.{prop}"])
            if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12):
                raise OriginDrawError(f"Origin signal {axis}.{prop} differs from its frozen axis plan.")
        for prop, expected in (
            ("showAxes", 3),
            ("atZero", 0),
            ("label.table", 0),
            ("type", 1),  # Native LabTalk axis type 1 is linear.
            ("showLabels", 1 if axis == "x" else 0),
        ):
            if int(state[f"{axis}.{prop}"]) != expected:
                raise OriginDrawError(
                    f"Origin signal {axis}.{prop} violates the visible-X/hidden-Y contract."
                )
        if int(round(float(state[f"{axis}.label.font"]))) != expected_font:
            raise OriginDrawError(f"Origin signal {axis} tick font differs from {style.font_family}.")
        for prop, expected in (
            ("label.pt", style.tick_label_size_pt),
            ("thickness", style.frame_line_width_pt),
            ("label.rotate", 0.0),
        ):
            if not math.isclose(float(state[f"{axis}.{prop}"]), expected, rel_tol=0, abs_tol=0.05):
                raise OriginDrawError(f"Origin signal {axis}.{prop} violates the frozen typography contract.")
    if int(state["y.ticks"]) != 0 or int(state["y.minorTicks"]) != 0:
        raise OriginDrawError(
            "Origin signal Y numeric ticks must stay hidden; amplitude uses the shared ruler."
        )
    return state


def build_signal_stack_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
    plan: SignalStackPlan,
) -> tuple[Any, dict[str, Any]]:
    from . import evidence_renderer as evidence
    from .scientific_renderer import (
        _apply_page_layer,
        _clean_numeric_x_axis,
        _figure_style,
        _position_x_title,
        _set_axis_titles,
        _title_geometry,
    )
    from .verify_utils import (
        verify_page_and_layer,
        verify_plot_color,
        verify_plot_line_widths,
        verify_text_fonts,
        verify_text_sizes,
    )

    channels = _prepare_signal_channel_data(frame, plan)
    layout = _resolve_signal_stack_layout(preparation, plan)
    style = _figure_style(preparation)
    source_snapshot = frame.copy(deep=True)
    imported_source = _signal_import_copy(frame, plan)
    source_sheet = evidence._source_sheet(op, imported_source, preparation)
    graph = op.new_graph("Processed Signal Stack", template="Line")
    if graph is None or len(graph) != 1:
        raise OriginDrawError("Origin must create one fresh single-layer signal graph.")
    layer = graph[0]
    template_cleanup = _clear_fresh_layer_objects(layer)
    _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    colors = interpolate_hex_colors("#24485A", "#207E80", len(channels))
    plots: dict[str, Any] = {}
    helpers = []
    for index, ((label, data), color) in enumerate(zip(channels, colors, strict=True), start=1):
        sheet = op.new_sheet("w", f"Signal Channel {index}")
        if sheet is None:
            raise OriginDrawError(f"Origin could not create signal channel helper {index}.")
        sheet.from_df(data)
        sheet.cols_axis("xyy")
        plot = layer.add_plot(sheet, "PlotY", "SourceTime", type="l")
        if plot is None:
            raise OriginDrawError(f"Origin could not draw signal channel {index}.")
        plot.color = color
        plot.set_cmd(f"-c color({color})", f"-w {pt_to_origin_width_units(style.plot_line_width_pt)}")
        plots[label] = plot
        helpers.append((label, sheet, data))

    graph.activate()
    layer.activate()
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    for axis in ("x", "y"):
        layer.set_int(f"{axis}.type", 1)
        layer.set_int(f"{axis}.label.table", 0)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=False)
    titles = _set_axis_titles(op, layer, preparation)
    for name in ("legend", "Legend"):
        evidence._remove_label(layer, name)
    page_width, page_height = float(op.lt_float("page.width")), float(op.lt_float("page.height"))
    y_title = titles["y_title"]
    y_title.set_float("rotate", 90)
    titles["x_title"].set_float("rotate", 0)
    op.lt_exec("doc -uw;")
    _position_x_title(op, titles["x_title"], style)
    y_title.set_float("left", page_width * layout["y_title_x_percent"] / 100 - y_title.get_float("width") / 2)
    y_title.set_float(
        "top", page_height * layout["y_title_y_percent"] / 100 - y_title.get_float("height") / 2
    )
    text_objects: dict[str, Any] = {}
    text_readback = {}
    for index, (label, right, center_y) in enumerate(layout["channel_labels"], start=1):
        name = f"SignalChannelLabel{index}"
        obj, report = evidence._add_shap_page_label(
            op,
            graph,
            layer,
            name=name,
            text=label,
            center_x_percent=right - 2,
            center_y_percent=center_y,
            size_pt=style.legend_size_pt,
            font_family=style.font_family,
            bold=False,
            color="#263D46",
        )
        obj.set_float("left", page_width * right / 100 - obj.get_float("width"))
        op.lt_exec("doc -uw;")
        left = float(obj.get_float("left"))
        if left < page_width * 1.8 / style.page_width_cm:
            raise OriginDrawError("A channel label overlaps the reserved amplitude-title column.")
        if not math.isclose((left + obj.get_float("width")) / page_width * 100, right, abs_tol=0.03):
            raise OriginDrawError("A channel label lost its right-aligned physical position.")
        report[f"{name}.left"] = left
        text_objects[name], text_readback[name] = obj, report
    obj, report = evidence._add_shap_page_label(
        op,
        graph,
        layer,
        name="SignalAmplitudeScale",
        text=layout["reference_text"],
        center_x_percent=layout["reference_text_x_percent"],
        center_y_percent=layout["reference_text_y_percent"],
        size_pt=style.legend_size_pt,
        font_family=style.font_family,
        bold=False,
        color="#263D46",
    )
    text_objects["SignalAmplitudeScale"], text_readback["SignalAmplitudeScale"] = obj, report
    reference = layer.add_line(
        layout["reference_x"], layout["reference_y_from"], layout["reference_x"], layout["reference_y_to"]
    )
    if reference is None:
        raise OriginDrawError("Origin could not create the native amplitude ruler object.")
    reference.name = "SignalAmplitudeRuler"
    reference_width = min(1.5, float(style.plot_line_width_pt))
    reference.width, reference.color = reference_width, REFERENCE_COLOR
    for key in ("arrowbeginwidth", "arrowbeginlength", "arrowendwidth", "arrowendlength"):
        reference.set_float(key, 0)
    # Keep the already frozen axes: reserves belong to the plan, not a runtime
    # rescale. Restore numeric X and hidden numeric Y after all text refreshes.
    for axis in ("x", "y"):
        layer.axis(axis).set_limits(*layout[f"{axis}_range"], layout[f"{axis}_step"])
    for prop in ("showLabels", "showlabel", "label.show", "ticks", "minorTicks"):
        layer.set_int(f"y.{prop}", 0)
    for prop in ("showLabels", "showlabel", "label.show"):
        layer.set_int(f"x.{prop}", 1)
    op.lt_exec("doc -uw;")
    axis_state = _verify_signal_axes(op, layer, style, layout)
    geometry = verify_page_and_layer(graph, layer, origin=op, style=style)
    reference_state = _verify_signal_ruler(op, reference, layout, reference_width)
    label_geometry = _title_geometry(op, text_objects)
    try:
        pd.testing.assert_frame_equal(frame, source_snapshot, check_exact=True)
        pd.testing.assert_frame_equal(
            source_sheet.to_df().reset_index(drop=True),
            imported_source.reset_index(drop=True),
            check_dtype=False,
            check_categorical=False,
            check_exact=True,
        )
    except AssertionError as error:
        raise OriginDrawError(
            "Origin signal source-table values changed during worksheet round trip."
        ) from error
    helpers_readback = {
        label: _verify_signal_helper_arrays(sheet.to_df(), expected, label, dict(plan.offsets)[label])
        for label, sheet, expected in helpers
    }
    bindings = [
        evidence._read_shap_plot_binding(
            op, layer, f"[{graph.name}]1!{index}", sheet, "SourceTime", "PlotY", prefix=f"signal{index}"
        )
        for index, (_label, sheet, _expected) in enumerate(helpers, start=1)
    ]
    try:
        color_state = {
            label: verify_plot_color(op, plots[label], color, variable_name=f"__signal_color_{index}")
            for index, (label, color) in enumerate(zip(plan.channel_order, colors, strict=True))
        }
        widths = verify_plot_line_widths(op, plots, style.plot_line_width_pt)
        all_labels = {**titles, **text_objects}
        fonts = verify_text_fonts(op, all_labels, style.font_family)
        sizes = verify_text_sizes(
            all_labels,
            {
                **{name: style.axis_title_size_pt for name in titles},
                **{name: style.legend_size_pt for name in text_objects},
            },
        )
    except RuntimeError as error:
        raise OriginDrawError(str(error)) from error
    native_pids = [int(layer.get_int(f"plot{index}.pid")) for index in range(1, len(channels) + 1)]
    if native_pids != [200] * len(channels):
        raise OriginDrawError("Origin signal graph must retain exactly the supplied channel Line plots.")
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {**_title_geometry(op, titles), **label_geometry, **fonts, **sizes},
        "origin_plot_state": {
            "colors": {"channels": color_state},
            "channel_widths": widths,
            "amplitude_ruler": reference_state,
        },
        "origin_signal_stack_readback": {
            "source_observation_count": len(frame),
            "source_columns": list(frame.columns),
            "source_time_range": plan.time_range,
            "source_value_range": plan.source_value_range,
            "channel_rows": plan.channel_rows,
            "channel_offsets": plan.offsets,
            "offset_step": plan.offset_step,
            "display_transform": plan.display_transform,
            "common_amplitude_units": plan.value_unit,
            "amplitude_reference_kind": plan.amplitude_scale_kind,
            "amplitude_reference_value": reference_state["amplitude_length"],
            "channel_helpers": helpers_readback,
            "source_sheet_range": source_sheet.lt_range(),
            "channel_helper_sheets": {label: sheet.lt_range() for label, sheet, _data in helpers},
            "layout": layout,
            "direct_labels": text_readback,
            "plot_bindings": bindings,
            "template_cleanup": template_cleanup,
            "native_plot_types": native_pids,
            "source_dataframe_unchanged": True,
            "source_table_values_roundtrip_checked": True,
            "source_category_encoding": "original_channel_labels_as_text",
            "source_text_columns": [
                str(column)
                for column in imported_source
                if isinstance(imported_source[column].dtype, pd.CategoricalDtype)
            ],
        },
        "origin_helper_columns": ["SourceTime", "SourceAmplitude", "PlotY"],
        "origin_plot_data_columns": [plan.time_column, plan.value_column],
        "title_objects": list(titles),
    }
