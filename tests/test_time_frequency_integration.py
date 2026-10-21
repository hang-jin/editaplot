from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime/src"), str(ROOT / "skill/editaplot/scripts"), str(ROOT)]

from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
)

from tools.generate_research_data import time_frequency_data  # noqa: E402


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "supplied_time_frequency.csv"
    time_frequency_data().to_csv(path, index=False, float_format="%.12g")
    return path


def test_time_frequency_route_freezes_physical_cells_not_categories(source):
    before = source.read_bytes()
    prepared = prepare_scientific(source, "time_frequency")
    spec = prepared.plot_spec
    plan = spec.time_frequency_plan
    assert dict(prepared.assignments) == {
        "Time (s)": "x", "Frequency (Hz)": "frequency_axis", "Power (dB)": "series",
    }
    assert not prepared.requires_confirmation
    assert plan.time_unit == "s"
    assert plan.frequency_unit == "Hz"
    assert plan.value_unit == "dB"
    assert plan.color_semantics == "sequential"
    assert plan.color_reference is None
    assert np.asarray(plan.grid.values).shape == (81, 121)
    assert spec.axis_plan.x_step == pytest.approx(0.2)
    assert spec.axis_plan.x_from < -0.4
    assert spec.axis_plan.x_to > 1.2
    assert spec.y_title == "Frequency (Hz)"
    assert source.read_bytes() == before


def test_chinese_headers_and_retained_columns_need_confirmation(tmp_path):
    frame = pd.DataFrame({
        "时间 (ms)": [0, 5, 0, 5], "频率 (Hz)": [10, 10, 20, 20],
        "功率 (微伏平方/Hz)": [-5, -3, 2, 9], "备注": ["上游表"] * 4,
    })
    path = tmp_path / "时频.csv"
    frame.to_csv(path, index=False)
    prepared = prepare_scientific(path, "time_frequency")
    assert prepared.requires_confirmation
    assert dict(prepared.assignments)["备注"] == "ignored"
    confirmed = prepare_scientific(
        path, "time_frequency", column_mapping=ScientificColumnMapping(prepared.assignments)
    )
    assert not confirmed.requires_confirmation
    assert confirmed.plot_spec.time_frequency_plan.retained_columns == ("备注",)
    assert confirmed.plot_spec.time_frequency_plan.time_unit == "ms"
    assert confirmed.plot_spec.time_frequency_plan.value_unit == "微伏平方/Hz"


@pytest.mark.parametrize("header", ["Time (s)", "Frequency (Hz)", "Power (dB)"])
def test_missing_explicit_units_stop_before_plotting(source, header):
    frame = pd.read_csv(source)
    frame.rename(columns={header: header.split(" (")[0]}).to_csv(source, index=False)
    with pytest.raises(ScientificWorkflowError, match="unit|单位"):
        prepare_scientific(source, "time_frequency")


def test_raw_eeg_does_not_become_a_time_frequency_matrix(tmp_path):
    path = tmp_path / "raw_eeg.csv"
    pd.DataFrame({"Time (s)": [0, 1, 2], "Voltage (uV)": [2, 1, 3]}).to_csv(path, index=False)
    with pytest.raises(ScientificWorkflowError):
        prepare_scientific(path, "time_frequency")


def test_unregistered_color_reference_is_not_silently_ignored(source):
    inferred = prepare_scientific(source, "time_frequency")
    with pytest.raises(ScientificWorkflowError, match="mode|模式"):
        prepare_scientific(source, "time_frequency", column_mapping=ScientificColumnMapping(
            inferred.assignments, plot_mode="diverging_zero"
        ))


def test_preview_preserves_all_values_orientation_and_detached_colorbar(source):
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure

    prepared = prepare_scientific(source, "time_frequency")
    plan = prepared.plot_spec.time_frequency_plan
    figure = _build_scientific_preview_figure(prepared)
    axis, colorbar = figure.axes
    cells = axis.collections[0]
    np.testing.assert_array_equal(np.asarray(cells.get_array()).ravel(), np.asarray(plan.grid.values).ravel())
    assert cells.get_clim() == plan.color_limits
    assert axis.get_xlim() == plan.x_range
    assert axis.get_ylim() == plan.y_range
    assert axis.get_xlabel() == "Time (s)"
    assert axis.get_ylabel() == "Frequency (Hz)"
    assert colorbar.get_ylabel() == "Power (dB)"
    assert axis.get_position().x1 < colorbar.get_position().x0
    assert len(axis.texts) == 0
    assert len(axis.lines) == 0
    figure.clear()


def test_descending_supplied_axes_keep_coordinate_direction(tmp_path):
    path = tmp_path / "descending.csv"
    pd.DataFrame({
        "Time (s)": [1, 0, 1, 0], "Frequency (Hz)": [20, 20, 10, 10],
        "Power (dB)": [1, 2, 3, 4],
    }).to_csv(path, index=False)
    plan = prepare_scientific(path, "time_frequency").plot_spec.time_frequency_plan
    assert plan.x_range == (1.5, -0.5)
    assert plan.y_range == (25, 5)
    assert plan.grid.values == ((1.0, 2.0), (3.0, 4.0))


def test_semantic_proposal_binds_frequency_cells_and_colorbar(source):
    from origin_sciplot.semantic_analysis import propose_prepared_semantics
    from origin_sciplot.template_registry import TemplateRegistry
    from origin_sciplot.template_service import ScientificTemplateService

    manifest = TemplateRegistry(ROOT / "runtime/templates").get("time_frequency")
    service = ScientificTemplateService(manifest)
    wrapped = service.prepare(source)
    proposal = propose_prepared_semantics(wrapped).to_dict()
    assert {item["disposition"] for item in proposal["data_items"]} == {"render_primary"}
    assert {item["element_kind"] for item in proposal["figure_elements"]} == {"heatmap_cell", "colorbar"}
    assert len(proposal["figure_elements"]) == 2
    assert proposal["derived_items"] == []
    cell = next(item for item in proposal["figure_elements"] if item["element_kind"] == "heatmap_cell")
    assert len(cell["data_item_ids"]) == 3
    assert "81" in dict(wrapped.summary.facts)["物理网格"]
    assert len(wrapped.payload.plot_spec.color_scale_hex) == 101


def test_source_change_is_rejected_before_any_native_call(source):
    from origin_sciplot.origin_backend.safe_errors import OriginDrawError
    from origin_sciplot.origin_backend.time_frequency_renderer import build_time_frequency_graph

    prepared = prepare_scientific(source, "time_frequency")
    frame = pd.read_csv(source)
    frame.iloc[0, 2] += 0.1
    with pytest.raises(OriginDrawError, match="match|changed"):
        build_time_frequency_graph(None, frame, prepared)


def test_frequency_axis_is_numeric_in_origin_bound_source_copy(source):
    from origin_sciplot.scientific_workflow import load_scientific_frame

    prepared = prepare_scientific(source, "time_frequency")
    frame = load_scientific_frame(source, prepared)
    assert frame["Frequency (Hz)"].dtype.kind == "f"
    assert frame["Frequency (Hz)"].iloc[0] == 3.0


def test_native_axis_writer_uses_signed_spacing_for_descending_coordinates():
    from types import SimpleNamespace

    from origin_sciplot.origin_backend.time_frequency_renderer import _set_physical_axes

    # This boundary double models the real GAxis behavior observed in the
    # retained descending-axis probe: positive increments are not a valid
    # replacement for an already descending scale's negative increment.
    class Axis:
        def __init__(self):
            self.values = None

        def set_limits(self, begin, end, step):
            self.values = (begin, end, step)

    axes = {"x": Axis(), "y": Axis()}
    layer = SimpleNamespace(axis=lambda name: axes[name])
    _set_physical_axes(
        layer, SimpleNamespace(x_range=(1.5, -0.5), y_range=(25.0, 5.0)),
        SimpleNamespace(x_step=0.2, y_step=5.0),
    )
    assert axes["x"].values == (1.5, -0.5, -0.2)
    assert axes["y"].values == (25.0, 5.0, -5.0)


def test_public_plan_requires_semantic_confirmation_then_allows_verified_route(source):
    from editaplot_core import build_plan, understand_data

    understanding = understand_data(source, template_id="time_frequency", engine_home=ROOT / "runtime")
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    result = build_plan(
        source, template_id="time_frequency",
        claim="Synthetic supplied time-frequency values show two illustrative regions.",
        evidence_role="time-frequency distribution", semantic_confirmation=confirmation,
        engine_home=ROOT / "runtime",
    )
    assert result["can_render"] is True
    assert result["data_understanding"]["status"] == "confirmed"
