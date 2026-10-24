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
    apply_scientific_text_overrides,
    load_scientific_frame,
    prepare_scientific,
)

from tools.generate_research_data import event_raster_data  # noqa: E402


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "events.csv"
    event_raster_data().to_csv(path, index=False, float_format="%.12g")
    return path


def test_raster_preparation_keeps_all_events_inventory_and_source_order(source):
    before = source.read_bytes()
    prepared = prepare_scientific(source, "event_raster")
    spec = prepared.plot_spec
    plan = spec.event_raster_plan
    assert not prepared.requires_confirmation
    assert dict(prepared.assignments) == {"Time (s)": "x", "Trial": "category", "Condition": "series_id"}
    assert prepared.row_count == 437
    assert len(plan.event_rows) == 433 and len(plan.inventory_rows) == 4
    assert plan.empty_trial_ids == ("Demo trial 05", "Demo trial 16", "Demo trial 28", "Demo trial 39")
    assert spec.axis_plan.y_from == 40.5 and spec.axis_plan.y_to == 0.5
    assert spec.axis_plan.y_step == 5
    assert spec.plot_mode == "events_only"
    assert spec.display_transform == "source_order_trial_ordinal"
    frame = load_scientific_frame(source, prepared)
    assert len(frame) == 437 and frame["Time (s)"].isna().sum() == 4
    assert source.read_bytes() == before


def test_chinese_columns_and_retained_metadata_need_no_invented_series(tmp_path):
    path = tmp_path / "事件.csv"
    pd.DataFrame(
        {
            "事件时间（毫秒）": [0.1, None, 0.2],
            "试次": ["01", "02", "01"],
            "条件": ["A", "B", "A"],
            "说明": ["upstream"] * 3,
        }
    ).to_csv(path, index=False)
    prepared = prepare_scientific(path, "event_raster")
    assert prepared.requires_confirmation
    confirmed = prepare_scientific(
        path, "event_raster", column_mapping=ScientificColumnMapping(prepared.assignments)
    )
    assert not confirmed.requires_confirmation
    assert confirmed.plot_spec.event_raster_plan.trial_order == ("01", "02")
    assert confirmed.plot_spec.event_raster_plan.empty_trial_ids == ("02",)
    assert confirmed.plot_spec.event_raster_plan.time_unit == "毫秒"
    assert dict(confirmed.assignments)["说明"] == "ignored"
    assert len(confirmed.plot_spec.series) == 2


def test_boolean_event_times_are_rejected_before_excel_numeric_coercion(tmp_path):
    path = tmp_path / "events.xlsx"
    pd.DataFrame({"Time (s)": [True, False], "Trial": ["A", "A"], "Condition": ["C", "C"]}).to_excel(
        path, index=False
    )
    with pytest.raises(ScientificWorkflowError, match="real numeric"):
        prepare_scientific(path, "event_raster")


@pytest.mark.parametrize("mode", ["detect_spikes", "psth", "sort_by_rate"])
def test_raster_does_not_silently_apply_signal_analysis_or_scientific_reordering(source, mode):
    prepared = prepare_scientific(source, "event_raster")
    with pytest.raises(ScientificWorkflowError, match="mode"):
        prepare_scientific(
            source,
            "event_raster",
            column_mapping=ScientificColumnMapping(prepared.assignments, plot_mode=mode),
        )


def test_raster_titles_reflow_geometry_without_changing_trials_or_values(source):
    before = prepare_scientific(source, "event_raster")
    after = apply_scientific_text_overrides(before, x_title="W" * 90 + " (s)")
    assert (
        after.plot_spec.event_raster_layout.style.page_width_cm
        > before.plot_spec.event_raster_layout.style.page_width_cm
    )
    assert after.plot_spec.event_raster_plan == before.plot_spec.event_raster_plan
    assert after.plot_spec.axis_plan == before.plot_spec.axis_plan
    assert after.plan_digest != before.plan_digest


@pytest.mark.parametrize("title", ["Event time (ms)", "Trial's event time (ms)", "Events [s] time (ms)"])
def test_raster_title_cannot_silently_change_time_units(source, title):
    prepared = prepare_scientific(source, "event_raster")
    with pytest.raises(ScientificWorkflowError, match="unit"):
        apply_scientific_text_overrides(prepared, x_title=title)


@pytest.mark.parametrize(
    "title", ["Trial's event time (s)", "Event time [s]", "事件时间（s）", "事件时间［s］"]
)
def test_raster_accepts_explicit_matching_unit_suffix(source, title):
    prepared = prepare_scientific(source, "event_raster")
    changed = apply_scientific_text_overrides(prepared, x_title=title)
    assert changed.plot_spec.x_title == title
    assert changed.plot_spec.event_raster_plan == prepared.plot_spec.event_raster_plan


def test_raster_palette_choice_is_frozen_and_survives_title_reflow(source):
    from origin_sciplot.scientific_visual import palette_colors
    from origin_sciplot.scientific_workflow import apply_scientific_palette_override

    original = prepare_scientific(source, "event_raster")
    changed = apply_scientific_palette_override(original, palette_id="blue_coral")
    assert changed.plot_spec.event_raster_layout.condition_colors == tuple(
        zip(
            original.plot_spec.event_raster_plan.condition_order,
            palette_colors("blue_coral")[:2],
            strict=True,
        )
    )
    renamed = apply_scientific_text_overrides(changed, x_title="W" * 90 + " (s)")
    assert (
        renamed.plot_spec.event_raster_layout.condition_colors
        == changed.plot_spec.event_raster_layout.condition_colors
    )
    assert renamed.plot_spec.display_plan.figure_style.palette_name == "blue_coral"
    assert renamed.plot_spec.event_raster_plan == original.plot_spec.event_raster_plan


def test_raster_preview_draws_all_event_marks_and_no_inventory_pseudo_events(source):
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure

    prepared = prepare_scientific(source, "event_raster")
    frame = load_scientific_frame(source, prepared)
    plan = prepared.plot_spec.event_raster_plan
    colors = dict(prepared.plot_spec.event_raster_layout.condition_colors)
    figure = _build_scientific_preview_figure(prepared)
    try:
        axis = figure.axes[0]
        assert axis.get_ylim() == (40.5, 0.5)
        assert prepared.plot_spec.axis_plan.x_step == 0.2
        assert np.any(np.isclose(axis.xaxis.get_minorticklocs(), 0.1))
        assert sum(len(line.get_xdata()) for line in axis.lines) == 433
        expected_y = dict(plan.row_trial_positions)
        for condition, line in zip(plan.condition_order, axis.lines, strict=True):
            rows = [r for r in plan.event_rows if frame.iloc[r]["Condition"] == condition]
            np.testing.assert_array_equal(line.get_xdata(), frame.iloc[rows]["Time (s)"].to_numpy())
            np.testing.assert_array_equal(line.get_ydata(), [expected_y[r] for r in rows])
            assert line.get_marker() == "|" and line.get_linestyle() == "None"
            assert line.get_color() == colors[condition]
        assert axis.get_legend() is None
        assert all(
            condition in [label.get_text() for label in figure.texts] for condition in plan.condition_order
        )
    finally:
        figure.clear()


def test_raster_semantics_explains_trial_ordinals_and_retained_blank_inventory(source):
    from origin_sciplot.semantic_analysis import propose_prepared_semantics
    from origin_sciplot.template_registry import TemplateRegistry
    from origin_sciplot.template_service import ScientificTemplateService

    manifest = TemplateRegistry(ROOT / "runtime/templates").get("event_raster")
    prepared = ScientificTemplateService(manifest).prepare(source)
    proposal = propose_prepared_semantics(prepared).to_dict()
    assert {item["disposition"] for item in proposal["data_items"]} == {"render_primary"}
    assert len(proposal["derived_items"]) == 1
    helper = proposal["derived_items"][0]
    assert helper["operation_id"] == "source_order_trial_ordinal"
    assert helper["explicit_approval_required"] is True
    assert helper["parameters"]["order_rule"] == "first_source_appearance"
    assert helper["parameters"]["event_count"] == 433
    assert helper["parameters"]["empty_trial_count"] == 4
    assert len(helper["input_item_ids"]) == 3
    assert [item["element_kind"] for item in proposal["figure_elements"]].count("scatter") == 2
    assert dict(prepared.summary.facts)["空试次"] == "4；保留空白泳道，不替换成时间0事件"


def test_trial_ordinal_contract_rejects_data_driven_sorting_and_inventory_zero_filling():
    from origin_sciplot.semantic_contract import DataDisposition, DerivedDataItem, SemanticContractError

    parameters = {
        "order_rule": "first_source_appearance",
        "index_origin": 1,
        "trial_count": 2,
        "event_count": 2,
        "inventory_row_count": 1,
        "empty_trial_count": 1,
        "inventory_semantics": "blank_time_declares_trial_not_event",
    }
    for key, changed in (
        ("order_rule", "sort_by_event_count"),
        ("index_origin", True),
        ("empty_trial_count", 3),
        ("inventory_semantics", "replace_blank_with_zero"),
    ):
        item = DerivedDataItem(
            item_id="trial_ordinal",
            semantic_role="display_position_not_measurement",
            disposition=DataDisposition.RENDER_PRIMARY,
            operation_id="source_order_trial_ordinal",
            input_item_ids=("time", "trial", "condition"),
            confidence=1,
            parameters=tuple({**parameters, key: changed}.items()),
        )
        with pytest.raises(SemanticContractError):
            item.validate()


def test_public_raster_plan_requires_ordinal_approval_then_uses_verified_route(source):
    from editaplot_core import EditaPlotError, build_plan, understand_data

    understanding = understand_data(source, template_id="event_raster", engine_home=ROOT / "runtime")
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    arguments = dict(
        template_id="event_raster",
        claim="Synthetic supplied event times retain explicit empty trials.",
        evidence_role="event timing",
        engine_home=ROOT / "runtime",
    )
    with pytest.raises(EditaPlotError, match="approv"):
        build_plan(
            source, semantic_confirmation={**confirmation, "approved_derived_item_ids": []}, **arguments
        )
    result = build_plan(source, semantic_confirmation=confirmation, **arguments)
    assert result["can_render"] is True
    assert result["data_understanding"]["status"] == "confirmed"


def test_public_manual_mapping_is_applied_before_automatic_role_failure(tmp_path):
    from editaplot_core import build_plan, understand_data

    source = tmp_path / "custom_headers.csv"
    pd.DataFrame(
        {"custom_t (s)": [0, 1, None], "custom_trial": ["01", "01", "02"], "custom_arm": ["A", "A", "B"]}
    ).to_csv(source, index=False)
    before = source.read_bytes()
    mapping = {
        "assignments": {"custom_t (s)": "x", "custom_trial": "category", "custom_arm": "series_id"},
        "plot_mode": "events_only",
    }
    understanding = understand_data(
        source, template_id="event_raster", mapping=mapping, engine_home=ROOT / "runtime"
    )
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    plan = build_plan(
        source,
        template_id="event_raster",
        mapping=mapping,
        engine_home=ROOT / "runtime",
        claim="Supplied events retain custom column names and explicit empty trials.",
        evidence_role="event timing",
        semantic_confirmation=confirmation,
    )
    assert plan["can_render"] is True
    assert source.read_bytes() == before


def test_explicit_mapping_preserves_legacy_preparation_digest_for_standard_headers(source):
    from origin_sciplot.template_registry import TemplateRegistry
    from origin_sciplot.template_service import ScientificTemplateService

    service = ScientificTemplateService(TemplateRegistry(ROOT / "runtime/templates").get("event_raster"))
    automatic = service.prepare(source)
    assignments = dict(automatic.payload.assignments)
    legacy = service.confirm_mapping(automatic, assignments=assignments, energy_kind="events_only")
    direct = service.prepare(
        source,
        column_mapping=ScientificColumnMapping(
            assignments=tuple(assignments.items()),
            plot_mode="events_only",
        ),
    )
    assert direct.plan_digest == legacy.plan_digest
    assert direct.payload.to_dict() == legacy.payload.to_dict()
