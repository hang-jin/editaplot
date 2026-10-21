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

from tools.generate_research_data import signal_stack_data  # noqa: E402


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "signals.csv"
    signal_stack_data().to_csv(path, index=False, float_format="%.12g")
    return path


def test_signal_route_keeps_observations_and_real_time_extent(source):
    original = source.read_bytes()
    prepared = prepare_scientific(source, "signal_stack")
    spec = prepared.plot_spec
    plan = spec.signal_stack_plan
    assert prepared.row_count == 8008
    assert dict(prepared.assignments) == {"Time (s)": "x", "Channel": "category", "Amplitude (uV)": "series"}
    assert (spec.axis_plan.x_from, spec.axis_plan.x_to) == (0.0, 4.0)
    assert plan.display_transform == "channel_offset_only"
    assert len(plan.channel_order) == 8
    assert [s.display_offset for s in spec.series] == [offset for _, offset in plan.offsets]
    assert source.read_bytes() == original


def test_signal_preview_uses_outside_labels_and_common_amplitude_ruler(source):
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure

    prep = prepare_scientific(source, "signal_stack")
    figure = _build_scientific_preview_figure(prep)
    axis = figure.axes[0]
    plan = prep.plot_spec.signal_stack_plan
    frame = pd.read_csv(source)
    assert axis.get_xlim() == (0.0, 4.0)
    assert len(axis.lines) == 9  # eight complete traces and a scale ruler
    for line, (_, rows), (_, offset) in zip(axis.lines[:8], plan.channel_rows, plan.offsets, strict=True):
        values = frame.iloc[list(rows)]
        np.testing.assert_array_equal(line.get_xdata(), values[plan.time_column])
        np.testing.assert_allclose(
            line.get_ydata() - offset, values[plan.value_column], rtol=1e-12, atol=1e-12
        )
    ruler = axis.lines[-1]
    assert min(ruler.get_xdata()) > axis.get_xlim()[1]
    assert np.diff(ruler.get_ydata())[0] == pytest.approx(plan.amplitude_scale_length)
    assert not ruler.get_clip_on()
    labels = [text for text in figure.texts if text.get_text() in plan.channel_order]
    assert len(labels) == 8
    assert all(text.get_position()[0] < axis.get_position().x0 for text in labels)
    assert axis.get_legend() is None
    figure.clear()


def test_more_channels_and_long_names_allocate_physical_space(tmp_path):
    frame = signal_stack_data()
    short = tmp_path / "short.csv"
    frame.loc[frame.Channel.isin(frame.Channel.unique()[:2])].to_csv(short, index=False)
    long = tmp_path / "long.csv"
    frame.Channel = frame.Channel + " - supplied sensor name"
    frame.to_csv(long, index=False)
    a = prepare_scientific(short, "signal_stack").plot_spec.display_plan.figure_style
    b = prepare_scientific(long, "signal_stack").plot_spec.display_plan.figure_style
    assert b.page_width_cm > a.page_width_cm
    assert b.page_height_cm > a.page_height_cm
    assert b.legend_size_pt == a.legend_size_pt == 17


def test_chinese_units_and_extra_columns_require_explicit_mapping_confirmation(tmp_path):
    path = tmp_path / "信号.csv"
    frame = signal_stack_data().rename(
        columns={"Time (s)": "时间（毫秒）", "Channel": "通道", "Amplitude (uV)": "幅值（µV）"}
    )
    frame["备注"] = "合成教学数据"
    frame.to_csv(path, index=False)
    prep = prepare_scientific(path, "signal_stack")
    assert prep.requires_confirmation
    prep = prepare_scientific(path, "signal_stack", column_mapping=ScientificColumnMapping(prep.assignments))
    assert not prep.requires_confirmation
    assert prep.plot_spec.signal_stack_plan.time_unit == "毫秒"
    assert prep.plot_spec.signal_stack_plan.value_unit == "µV"


def test_signal_source_booleans_are_rejected_before_numeric_coercion(tmp_path):
    path = tmp_path / "booleans.xlsx"
    pd.DataFrame({"Time (s)": [0, 1], "Channel": ["A", "A"], "Amplitude (uV)": [True, False]}).to_excel(
        path, index=False
    )
    with pytest.raises(ScientificWorkflowError, match="bool"):
        prepare_scientific(path, "signal_stack")


def test_processed_fluorescence_roi_headers_map_without_signal_analysis(tmp_path):
    path = tmp_path / "roi.csv"
    pd.DataFrame(
        {"Time (s)": [0, 1, 0, 1], "ROI": ["A", "A", "B", "B"], "Intensity (a.u.)": [1, 2, 3, 4]}
    ).to_csv(path, index=False)
    prepared = prepare_scientific(path, "signal_stack")
    assert dict(prepared.assignments) == {"Time (s)": "x", "ROI": "category", "Intensity (a.u.)": "series"}
    assert prepared.plot_spec.signal_stack_plan.value_unit == "a.u."
    assert prepared.plot_spec.display_transform == "channel_offset_only"


def test_requested_normalization_is_not_silently_applied(source):
    prepared = prepare_scientific(source, "signal_stack")
    with pytest.raises(ScientificWorkflowError, match="mode"):
        prepare_scientific(
            source,
            "signal_stack",
            column_mapping=ScientificColumnMapping(prepared.assignments, plot_mode="normalize_each_channel"),
        )


def test_explicit_long_axis_titles_reflow_layout_and_keep_source_extent(source):
    from origin_sciplot.scientific_workflow import apply_scientific_text_overrides

    prepared = prepare_scientific(source, "signal_stack")
    title = "Time coordinate of the supplied recording measured for every retained observation (s)"
    changed = apply_scientific_text_overrides(prepared, x_title=title)
    old_style = prepared.plot_spec.display_plan.figure_style
    new_style = changed.plot_spec.display_plan.figure_style
    assert new_style.page_width_cm > old_style.page_width_cm
    assert changed.plot_spec.signal_stack_layout.x_range == (0.0, 4.0)
    assert changed.plot_spec.signal_stack_layout != prepared.plot_spec.signal_stack_layout
    assert new_style.axis_title_size_pt == old_style.axis_title_size_pt
    assert changed.plan_digest != prepared.plan_digest


def test_semantics_requires_explicit_offset_and_amplitude_reference_approval(source):
    from editaplot_core import EditaPlotError, build_plan, understand_data

    understanding = understand_data(source, template_id="signal_stack", engine_home=ROOT / "runtime")
    proposal = understanding["understanding"]
    offsets = [item for item in proposal["derived_items"] if item["operation_id"] == "offset_by_constant"]
    rulers = [item for item in proposal["derived_items"] if item["operation_id"] == "signal_amplitude_ruler"]
    assert len(offsets) == 8 and len(rulers) == 1
    assert all(item["explicit_approval_required"] for item in [*offsets, *rulers])
    assert rulers[0]["parameters"]["reference_kind"] == "display_unit_length_not_statistical_estimate"
    assert len(proposal["figure_elements"]) == 9
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    with pytest.raises(EditaPlotError, match="approv"):
        build_plan(
            source,
            template_id="signal_stack",
            claim="Synthetic common-amplitude channel comparison.",
            evidence_role="signal comparison",
            engine_home=ROOT / "runtime",
            semantic_confirmation={**confirmation, "approved_derived_item_ids": []},
        )


def test_scale_ruler_contract_does_not_accept_statistical_claim_or_negative_length():
    from origin_sciplot.semantic_contract import DataDisposition, DerivedDataItem, SemanticContractError

    for length, kind in ((-1, "display_unit_length_not_statistical_estimate"), (10, "confidence_interval")):
        item = DerivedDataItem(
            item_id="ruler",
            semantic_role="amplitude_display_reference",
            disposition=DataDisposition.RENDER_SECONDARY,
            operation_id="signal_amplitude_ruler",
            input_item_ids=("source_001",),
            confidence=1.0,
            parameters=(
                ("length", length),
                ("unit", "uV"),
                ("reference_kind", kind),
                ("rule", "nice_125_global_span_quarter"),
            ),
        )
        with pytest.raises(SemanticContractError):
            item.validate()
