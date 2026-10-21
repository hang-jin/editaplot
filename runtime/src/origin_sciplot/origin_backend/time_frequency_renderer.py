"""Native, source-bound time-frequency matrix composition, without signal analysis."""

from __future__ import annotations

import math
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

import pandas as pd

from ..scientific_visual import time_frequency_scale_region
from ..scientific_workflow import ScientificPreparation
from ..time_frequency import build_time_frequency_plan
from .research_grid_renderer import build_physical_grid_layer, position_grid_colorbar
from .safe_errors import OriginDrawError


def _set_physical_axes(layer: Any, plan: Any, axis_plan: Any) -> None:
    for axis, limits, spacing in (
        ("x", plan.x_range, axis_plan.x_step), ("y", plan.y_range, axis_plan.y_step)
    ):
        layer.axis(axis).set_limits(*limits, math.copysign(spacing, limits[1] - limits[0]))


def build_time_frequency_graph(
    op: Any, frame: pd.DataFrame, preparation: ScientificPreparation
) -> tuple[Any, dict[str, Any]]:
    from . import evidence_renderer as evidence
    from .scientific_renderer import _apply_page_layer, _clean_numeric_x_axis, _figure_style
    from .verify_utils import verify_page_and_layer

    spec = preparation.plot_spec
    plan = spec.time_frequency_plan
    if plan is None or spec.plot_kind != "time_frequency" or spec.plot_mode != "sequential":
        raise OriginDrawError("A frozen sequential time-frequency plan is required.")
    try:
        current = build_time_frequency_plan(
            frame, time_column=plan.time_column, frequency_column=plan.frequency_column,
            value_column=plan.value_column, time_unit=plan.time_unit, frequency_unit=plan.frequency_unit,
            value_unit=plan.value_unit, color_semantics="sequential", color_limits=plan.color_limits,
        )
    except ValueError as error:
        raise OriginDrawError(f"The time-frequency source no longer matches its plan: {error}") from error
    if current != plan:
        raise OriginDrawError("The time-frequency plan no longer matches its source table.")
    style = _figure_style(preparation)
    if style.profile_name != "research-time-frequency" or len(spec.color_scale_hex) != 101:
        raise OriginDrawError("The frozen physical-grid profile and 101 exact colors are required.")
    snapshot = frame.copy(deep=True)
    source_sheet = evidence._source_sheet(op, frame, preparation)
    graph = op.new_graph("Time Frequency Figure", template="heatmap")
    if graph is None:
        raise OriginDrawError("Origin could not create the time-frequency graph.")
    layer = graph[0]
    _apply_page_layer(op, graph, layer, dual_y=False, preparation=preparation)
    graph.set_int("background", op.ocolor("#FFFFFF"))
    grid_state = build_physical_grid_layer(
        op, graph, layer, plan.grid, value_label=plan.value_column,
        palette_hex=spec.color_scale_hex, z_range=plan.color_limits,
    )
    _clean_numeric_x_axis(op, graph)
    for axis in ("x", "y"):
        layer.set_int(f"{axis}.label.table", 0)
        layer.set_int(f"{axis}.label.type", 1)
    evidence._style_evidence_axes(op, layer, preparation, x_numeric=True, y_numeric=True)
    region = time_frequency_scale_region(style)
    scale = position_grid_colorbar(
        op, graph, layer,
        region=SimpleNamespace(**{key: region[key] for key in (
            "left_percent", "top_percent", "width_percent", "height_percent"
        )}),
        font_family=style.font_family, label_size_pt=15.0,
    )
    labels, title_geometry, text_state = evidence._style_titles(op, graph, layer, preparation)
    _, value_state = evidence._add_shap_page_label(
        op, graph, layer, name="PhysicalGridValueTitle", text=spec.series[0].label,
        center_x_percent=region["title_x_percent"], center_y_percent=region["title_y_percent"],
        size_pt=17.0, font_family=style.font_family, bold=False, rotation_deg=90,
    )
    axes = spec.axis_plan
    _set_physical_axes(layer, plan, axes)
    op.lt_exec("doc -uw;")
    axis_state = evidence._validate_axes(op, layer, preparation)
    for axis, ends, step in (("x", plan.x_range, axes.x_step), ("y", plan.y_range, axes.y_step)):
        # Origin returns a signed increment for a descending physical axis.
        # The frozen positive step is its spacing, not permission to flip data.
        native_step = math.copysign(step, ends[1] - ends[0])
        for key, expected in zip(("from", "to", "inc"), (*ends, native_step), strict=True):
            actual = float(axis_state[f"{axis}.{key}"])
            if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-10):
                raise OriginDrawError(
                    f"The physical {axis}.{key} differs from its frozen time-frequency plan."
                )
    try:
        pd.testing.assert_frame_equal(frame, snapshot, check_exact=True)
        pd.testing.assert_frame_equal(
            source_sheet.to_df().reset_index(drop=True), frame.reset_index(drop=True),
            check_dtype=False, check_exact=True,
        )
    except AssertionError as error:
        raise OriginDrawError("The source worksheet changed a supplied time-frequency value.") from error
    return graph, {
        **verify_page_and_layer(graph, layer, origin=op, style=style),
        "origin_axis_state": axis_state,
        "origin_text_state": {**text_state, **title_geometry, "value_title": value_state},
        "origin_plot_state": {"native_pid": 105, "plot_range": grid_state["plot_range"]},
        "origin_time_frequency_readback": {
            **grid_state, "colorbar": scale, "value_title": value_state,
            "time_unit": plan.time_unit, "frequency_unit": plan.frequency_unit,
            "value_unit": plan.value_unit, "color_semantics": plan.color_semantics,
            "color_reference": None, "source_dataframe_unchanged": True,
            "source_table_values_roundtrip_checked": True,
            "processing_boundary": plan.processing_boundary, "profile": asdict(style),
        },
        "origin_helper_columns": [],
        "origin_plot_data_columns": [plan.time_column, plan.frequency_column, plan.value_column],
        "title_objects": list(labels),
    }
