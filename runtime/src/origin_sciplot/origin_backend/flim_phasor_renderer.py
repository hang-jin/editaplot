"""Native, editable FLIM G/S scatter and mathematical-reference graph builder.

Session ownership, capability probes, saving and exports belong to the caller.
This builder never estimates a lifetime or changes upstream phasor coordinates.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ..flim_phasor import PhasorPlan, build_phasor_plan
from ..scientific_visual import series_palette_colors
from ..scientific_workflow import ScientificPreparation
from .base_style_contract import pt_to_origin_width_units
from .safe_errors import OriginDrawError

REFERENCE_COLOR = "#89939D"
SYMBOL_EDGE_PERCENT = 35.0
# LabTalk -kf uses 0=solid, 1=open; do not copy a differently numbered
# Python/property documentation table into the native option readback.
SYMBOL_INTERIOR = 1
PHYSICAL_UNIT_TOLERANCE = 0.003


def _prepare_phasor_group_data(
    frame: pd.DataFrame, plan: PhasorPlan
) -> tuple[tuple[str, pd.DataFrame], ...]:
    try:
        current = build_phasor_plan(
            frame, g_column=plan.g_column, s_column=plan.s_column, group_column=plan.group_column
        )
    except ValueError as error:
        raise OriginDrawError(f"Invalid phasor source table: {error}") from error
    if current != plan:
        raise OriginDrawError("The phasor plan no longer matches its source table.")
    groups = []
    for label, positions in plan.group_rows:
        source = frame.iloc[list(positions)]
        groups.append(
            (
                label,
                pd.DataFrame(
                    {
                        "PlotG": source[plan.g_column].to_numpy(dtype=float, copy=True),
                        "PlotS": source[plan.s_column].to_numpy(dtype=float, copy=True),
                    }
                ),
            )
        )
    return tuple(groups)


def _verify_phasor_helper_arrays(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> int:
    columns = list(expected.columns)
    try:
        matches = len(actual) == len(expected) and np.array_equal(
            actual.loc[:, columns].to_numpy(dtype=float), expected.to_numpy(dtype=float)
        )
    except (KeyError, TypeError, ValueError):
        matches = False
    if not matches:
        raise OriginDrawError(f"Origin phasor helper changed source coordinates: {label}.")
    return len(expected)


def _verify_phasor_metric_geometry(
    geometry: dict[str, Any], x_range: tuple[float, float], y_range: tuple[float, float]
) -> dict[str, float]:
    physical_width = float(geometry["width_cm"]) * float(geometry["width_percent"]) / 100.0
    physical_height = float(geometry["height_cm"]) * float(geometry["height_percent"]) / 100.0
    x_span, y_span = x_range[1] - x_range[0], y_range[1] - y_range[0]
    dimensions = (physical_width, physical_height, x_span, y_span)
    if not all(math.isfinite(value) and value > 0 for value in dimensions):
        raise OriginDrawError("Phasor physical axis lengths and spans must be finite and positive.")
    cm_per_g, cm_per_s = physical_width / x_span, physical_height / y_span
    ratio = cm_per_g / cm_per_s
    if not math.isfinite(ratio) or abs(ratio - 1.0) > PHYSICAL_UNIT_TOLERANCE:
        raise OriginDrawError(
            "Phasor physical G/S units differ by more than 0.3%; "
            "adjust the frozen layer geometry instead of distorting the reference semicircle."
        )
    return {
        "cm_per_g": cm_per_g,
        "cm_per_s": cm_per_s,
        "unit_ratio": ratio,
        "relative_tolerance": PHYSICAL_UNIT_TOLERANCE,
    }


def build_flim_phasor_graph(
    op: Any,
    frame: pd.DataFrame,
    preparation: ScientificPreparation,
    plan: PhasorPlan,
) -> tuple[Any, dict[str, Any]]:
    from . import evidence_renderer as evidence
    from .scientific_renderer import (
        OriginSeriesPlan,
        _apply_page_layer,
        _clean_numeric_x_axis,
        _figure_style,
        _position_publication_legend,
        _style_legend,
    )
    from .verify_utils import (
        verify_page_and_layer,
        verify_plot_color,
        verify_plot_line_widths,
        verify_symbol_style,
        verify_text_fonts,
        verify_text_sizes,
    )

    groups = _prepare_phasor_group_data(frame, plan)
    style = _figure_style(preparation)
    if not style.profile_name.endswith("-external-legend"):
        raise OriginDrawError("Phasor drawing requires a frozen external-legend layout.")
    marker_size = float(preparation.plot_spec.display_plan.marker_size_pt)
    if not math.isfinite(marker_size) or marker_size <= 0:
        raise OriginDrawError("Phasor scatter symbols require a positive, finite size.")
    axis_plan = preparation.plot_spec.axis_plan
    steps = (axis_plan.x_step, axis_plan.y_step)
    if any(value is None or not math.isfinite(value) or value <= 0 for value in steps):
        raise OriginDrawError("Phasor axes require positive, finite frozen tick steps.")
    source_snapshot = frame.copy(deep=True)
    source_sheet = evidence._source_sheet(op, frame, preparation)
    graph = op.new_graph("FLIM Phasor Figure", template="Line")
    if graph is None:
        raise OriginDrawError("Origin could not create the phasor graph.")
    layer = graph[0]
    _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))

    reference_frame = pd.DataFrame({"ReferenceG": plan.reference_g, "ReferenceS": plan.reference_s})
    reference_sheet = op.new_sheet("w", "Phasor Mathematical Reference")
    if reference_sheet is None:
        raise OriginDrawError("Origin could not create the phasor reference helper.")
    reference_sheet.from_df(reference_frame)
    reference_sheet.cols_axis("xy")
    reference = layer.add_plot(reference_sheet, "ReferenceS", "ReferenceG", type="l")
    if reference is None:
        raise OriginDrawError("Origin could not create the mathematical semicircle.")
    reference.color = REFERENCE_COLOR
    reference_width = min(1.2, float(style.plot_line_width_pt) * 0.5)
    reference.set_cmd(f"-c color({REFERENCE_COLOR})", f"-w {pt_to_origin_width_units(reference_width)}")
    reference_label = "Universal semicircle"
    while reference_label in plan.group_order:
        reference_label += " (reference)"
    main_plots = {reference_label: reference}
    entries = [
        OriginSeriesPlan(
            "ReferenceS", "ReferenceS", "ReferenceG", None, reference_label,
            "left", "l", REFERENCE_COLOR, None, 0.0, is_reference=True,
        )
    ]
    helpers: list[tuple[str, Any, pd.DataFrame]] = []
    scatter_plots: dict[str, Any] = {}
    colors = series_palette_colors(style.palette_name, len(groups))
    for index, ((label, plot_frame), color) in enumerate(zip(groups, colors, strict=True), start=1):
        sheet = op.new_sheet("w", f"Phasor Plot Data {index}")
        if sheet is None:
            raise OriginDrawError(f"Origin could not create phasor group {index}.")
        sheet.from_df(plot_frame)
        sheet.cols_axis("xy")
        plot = layer.add_plot(sheet, "PlotS", "PlotG", type="s")
        if plot is None:
            raise OriginDrawError(f"Origin could not create phasor scatter group {index}.")
        plot.color = color
        plot.symbol_kind = 2
        plot.symbol_size = marker_size
        plot.set_cmd(f"-c color({color})", f"-kh {SYMBOL_EDGE_PERCENT:g}", f"-kf {SYMBOL_INTERIOR}")
        main_plots[label] = plot
        scatter_plots[label] = plot
        helpers.append((label, sheet, plot_frame))
        entries.append(
            OriginSeriesPlan(
                plan.s_column, "PlotS", "PlotG", None, label, "left", "s",
                color, None, marker_size, symbol_kind=2,
            )
        )

    graph.activate()
    layer.activate()
    layer.rescale()
    _clean_numeric_x_axis(op, graph)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=True)
    legend = _style_legend(op, layer, entries, main_plots, style)
    if legend is None:
        raise OriginDrawError("Origin could not retain the native phasor legend.")
    labels, title_state, text_state = evidence._style_titles(op, graph, layer, preparation)
    legend_state = _position_publication_legend(op, layer, legend, style)
    # Labels and legend refresh may rescale a native graph. Restore both axes
    # after those operations, then validate the real physical metric geometry.
    layer.axis("x").set_limits(*plan.x_range, axis_plan.x_step)
    layer.axis("y").set_limits(*plan.y_range, axis_plan.y_step)
    op.lt_exec("doc -uw;")
    axis_state = evidence._validate_axes(op, layer, preparation)
    for axis, limits, step in (("x", plan.x_range, axis_plan.x_step), ("y", plan.y_range, axis_plan.y_step)):
        for key, expected in zip(("from", "to", "inc"), (*limits, step), strict=True):
            actual = float(axis_state[f"{axis}.{key}"])
            if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-10):
                raise OriginDrawError(f"Origin phasor {axis}.{key} differs from its frozen plan.")
    geometry = verify_page_and_layer(graph, layer, origin=op, style=style)
    metric = _verify_phasor_metric_geometry(geometry, plan.x_range, plan.y_range)

    try:
        pd.testing.assert_frame_equal(frame, source_snapshot)
        pd.testing.assert_frame_equal(
            source_sheet.to_df().reset_index(drop=True), frame.reset_index(drop=True),
            check_dtype=False, check_exact=True,
        )
    except AssertionError as error:
        raise OriginDrawError(
            "Origin phasor source-table values did not survive the worksheet round trip."
        ) from error
    group_counts = {
        label: _verify_phasor_helper_arrays(sheet.to_df(), expected, label)
        for label, sheet, expected in helpers
    }
    reference_count = _verify_phasor_helper_arrays(
        reference_sheet.to_df(), reference_frame, "mathematical reference"
    )
    try:
        plot_colors = {
            entry.label: verify_plot_color(
                op, main_plots[entry.label], entry.color, variable_name=f"__phasor_color_{index}"
            )
            for index, entry in enumerate(entries)
        }
        widths = verify_plot_line_widths(op, {reference_label: reference}, reference_width)
        symbols = {
            label: verify_symbol_style(
                op, plot, expected_size_pt=marker_size,
                expected_edge_percent=SYMBOL_EDGE_PERCENT,
                expected_symbol_kind=2, expected_symbol_interior=SYMBOL_INTERIOR,
            )
            for label, plot in scatter_plots.items()
        }
        text_labels = {**labels, "legend": legend}
        fonts = verify_text_fonts(op, text_labels, style.font_family)
        sizes = verify_text_sizes(
            text_labels,
            {**{name: style.axis_title_size_pt for name in labels}, "legend": style.legend_size_pt},
        )
    except RuntimeError as error:
        raise OriginDrawError(str(error)) from error
    native_pids = [int(layer.get_int(f"plot{index}.pid")) for index in range(1, len(entries) + 1)]
    if native_pids != [200, *([201] * len(groups))]:
        raise OriginDrawError(
            "Origin phasor graph no longer contains one line and the requested scatter plots."
        )
    return graph, {
        **geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {**text_state, **title_state, **legend_state, **fonts, **sizes},
        "origin_plot_state": {"colors": plot_colors, "reference_line": widths, "symbols": symbols},
        "origin_phasor_readback": {
            "physical_axis_units": metric,
            "reference_kind": plan.reference_kind,
            "reference_point_count": reference_count,
            "outside_reference_count": plan.outside_reference_count,
            "source_observation_count": len(frame),
            "group_counts": group_counts,
            "group_rows": plan.group_rows,
            "source_columns": list(frame.columns),
            "source_dataframe_unchanged": True,
            "source_table_values_roundtrip_checked": True,
            "coordinate_arrays_equal": True,
            "native_plot_types": native_pids,
        },
        "origin_helper_columns": ["ReferenceG", "ReferenceS", "PlotG", "PlotS"],
        "origin_plot_data_columns": [plan.g_column, plan.s_column],
        "title_objects": list(labels),
    }
