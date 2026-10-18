"""Native Line plots for an explicit, display-only common-amplitude signal stack.

The caller owns Origin sessions, capability probes, saving and exports. This
builder is not a public registered template and does not filter or resample.
"""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from ..scientific_visual import interpolate_hex_colors
from ..scientific_workflow import ScientificPreparation
from ..signal_stack import SignalStackPlan, build_signal_stack_plan
from .base_style_contract import pt_to_origin_width_units
from .safe_errors import OriginDrawError

REFERENCE_COLOR = "#52616B"
SOURCE_RECOVERY_TOLERANCE = 1e-12
LEFT_RESERVE_FRACTION = 0.14
RIGHT_RESERVE_FRACTION = 0.22


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
    time0, time1 = plan.time_range
    time_span = time1 - time0
    if not math.isfinite(time_span) or time_span <= 0:
        raise OriginDrawError("Signal source timestamps do not provide a finite plotting span.")
    left_reserve, right_reserve = time0 - x0, x1 - time1
    if left_reserve < time_span * LEFT_RESERVE_FRACTION or right_reserve < time_span * RIGHT_RESERVE_FRACTION:
        raise OriginDrawError(
            "Signal stack frozen X limits must reserve at least 14% of the source time span "
            "on the left for channel names and 22% on the right for the amplitude ruler."
        )
    if y0 > plan.display_y_range[0] or y1 < plan.display_y_range[1]:
        raise OriginDrawError("Signal stack frozen Y limits do not include all unscaled channel values.")
    y_span = y1 - y0
    reference_from = y0 + y_span * 0.08
    reference_to = reference_from + plan.amplitude_scale_length
    if not math.isfinite(reference_to) or reference_to > y1 - y_span * 0.08:
        raise OriginDrawError(
            "Signal stack frozen Y limits leave insufficient space for the amplitude ruler."
        )
    source_midpoint = plan.source_value_range[0] * 0.5 + plan.source_value_range[1] * 0.5
    return {
        "x_range": (x0, x1),
        "y_range": (y0, y1),
        "x_step": dx,
        "y_step": dy,
        "channel_label_x": x0 + left_reserve * 0.08,
        "channel_label_y": tuple((label, source_midpoint + offset) for label, offset in plan.offsets),
        "reference_x": time1 + right_reserve * 0.18,
        "reference_label_x": time1 + right_reserve * 0.32,
        "reference_y_from": reference_from,
        "reference_y_to": reference_to,
        "source_time_range": plan.time_range,
    }


def _signal_text(
    op: Any,
    layer: Any,
    *,
    name: str,
    text: str,
    x: float,
    y: float,
    size: float,
    font_code: int,
) -> Any:
    from .scientific_renderer import _style_label

    label = layer.add_label(text)
    if label is None:
        raise OriginDrawError(f"Origin could not create signal text {name}.")
    label.name = name
    label.set_int("attach", 2)
    label.set_float("x1", x)
    label.set_float("y1", y)
    _style_label(label, size, bold=False)
    label.set_int("font", font_code)
    label.color = op.ocolor("#263D46")
    return label


def _verify_signal_text(label: Any, text: str, x: float, y: float) -> dict[str, Any]:
    native_text = str(label.text)
    expected_text = text.replace("\r\n", "\n")
    state = {
        "text": native_text.replace("\r\n", "\n"),
        "native_text": native_text,
        "attach": int(label.get_int("attach")),
        "x": float(label.get_float("x1")),
        "y": float(label.get_float("y1")),
        "show": int(label.get_int("show")),
    }
    if state["text"] != expected_text or state["attach"] != 2 or state["show"] != 1:
        raise OriginDrawError("Origin signal labels lost their source text or scale attachment.")
    for key, expected in (("x", x), ("y", y)):
        if not math.isclose(state[key], expected, rel_tol=1e-10, abs_tol=1e-12):
            raise OriginDrawError("Origin signal label position differs from its frozen layout.")
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
        _origin_font_code,
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
    source_sheet = evidence._source_sheet(op, frame, preparation)
    graph = op.new_graph("Processed Signal Stack", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the signal stack graph.")
    layer = graph[0]
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

    reference_data = pd.DataFrame(
        {
            "ReferenceX": [layout["reference_x"]] * 2,
            "ReferenceY": [layout["reference_y_from"], layout["reference_y_to"]],
        }
    )
    reference_sheet = op.new_sheet("w", "Signal Amplitude Reference")
    if reference_sheet is None:
        raise OriginDrawError("Origin could not create the signal amplitude reference helper.")
    reference_sheet.from_df(reference_data)
    reference_sheet.cols_axis("xy")
    reference = layer.add_plot(reference_sheet, "ReferenceY", "ReferenceX", type="l")
    if reference is None:
        raise OriginDrawError("Origin could not create the signal amplitude reference line.")
    reference_width = min(1.5, float(style.plot_line_width_pt))
    reference.color = REFERENCE_COLOR
    reference.set_cmd(f"-c color({REFERENCE_COLOR})", f"-w {pt_to_origin_width_units(reference_width)}")

    graph.activate()
    layer.activate()
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=False)
    titles, title_geometry, text_state = evidence._style_titles(op, graph, layer, preparation)
    for name in ("legend", "Legend"):
        evidence._remove_label(layer, name)
    font_code = _origin_font_code(op, style.font_family)
    text_objects: dict[str, Any] = {}
    expected_text: dict[str, tuple[str, float, float]] = {}
    for index, (label, y) in enumerate(layout["channel_label_y"], start=1):
        name = f"SignalChannelLabel{index}"
        x = layout["channel_label_x"]
        text_objects[name] = _signal_text(
            op, layer, name=name, text=label, x=x, y=y, size=style.legend_size_pt, font_code=font_code
        )
        expected_text[name] = (label, x, y)
    reference_text = f"Shared scale\n{plan.amplitude_scale_length:g} {plan.value_unit}\n(display offsets)"
    reference_text_y = (layout["reference_y_from"] + layout["reference_y_to"]) * 0.5
    text_objects["SignalAmplitudeScale"] = _signal_text(
        op,
        layer,
        name="SignalAmplitudeScale",
        text=reference_text,
        x=layout["reference_label_x"],
        y=reference_text_y,
        size=style.legend_size_pt,
        font_code=font_code,
    )
    expected_text["SignalAmplitudeScale"] = (reference_text, layout["reference_label_x"], reference_text_y)
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
    text_readback = {
        name: _verify_signal_text(text_objects[name], *expected) for name, expected in expected_text.items()
    }
    label_geometry = _title_geometry(op, text_objects)
    try:
        pd.testing.assert_frame_equal(frame, source_snapshot, check_exact=True)
        pd.testing.assert_frame_equal(
            source_sheet.to_df().reset_index(drop=True),
            frame.reset_index(drop=True),
            check_dtype=False,
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
    try:
        reference_actual = reference_sheet.to_df().loc[:, reference_data.columns].to_numpy(dtype=float)
        if not np.array_equal(reference_actual, reference_data.to_numpy(dtype=float)):
            raise ValueError("Reference coordinates changed.")
        reference_length = float(reference_actual[1, 1] - reference_actual[0, 1])
        if not math.isclose(reference_length, plan.amplitude_scale_length, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Reference length changed.")
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise OriginDrawError(
            "Origin signal amplitude ruler does not match its display-unit length."
        ) from error
    try:
        color_state = {
            label: verify_plot_color(op, plots[label], color, variable_name=f"__signal_color_{index}")
            for index, (label, color) in enumerate(zip(plan.channel_order, colors, strict=True))
        }
        reference_color = verify_plot_color(
            op, reference, REFERENCE_COLOR, variable_name="__signal_reference_color"
        )
        widths = verify_plot_line_widths(op, plots, style.plot_line_width_pt)
        reference_widths = verify_plot_line_widths(op, {"amplitude_reference": reference}, reference_width)
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
    native_pids = [int(layer.get_int(f"plot{index}.pid")) for index in range(1, len(channels) + 2)]
    if native_pids != [200] * (len(channels) + 1):
        raise OriginDrawError(
            "Origin signal graph must retain all channel and amplitude-reference native Line plots."
        )
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {**text_state, **title_geometry, **label_geometry, **fonts, **sizes},
        "origin_plot_state": {
            "colors": {"channels": color_state, "amplitude_reference": reference_color},
            "channel_widths": widths,
            "reference_width": reference_widths,
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
            "amplitude_reference_value": reference_length,
            "channel_helpers": helpers_readback,
            "layout": layout,
            "direct_labels": text_readback,
            "native_plot_types": native_pids,
            "source_dataframe_unchanged": True,
            "source_table_values_roundtrip_checked": True,
        },
        "origin_helper_columns": ["SourceTime", "SourceAmplitude", "PlotY", "ReferenceX", "ReferenceY"],
        "origin_plot_data_columns": [plan.time_column, plan.value_column],
        "title_objects": list(titles),
    }
