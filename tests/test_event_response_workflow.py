from __future__ import annotations

import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_context import ScientificContextError  # noqa: E402
from origin_sciplot.scientific_preview import (  # noqa: E402
    ScientificPreviewError,
    _build_scientific_preview_figure,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    SUPPORTED_SCIENTIFIC_TEMPLATE_IDS,
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
    role_options,
)
from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402
from origin_sciplot.semantic_contract import SemanticContractError  # noqa: E402

INTERVAL = "Upstream asymmetric interval (not CI)"


def _event_frame(*, unit_headers: bool = True) -> pd.DataFrame:
    time = "Time(s)" if unit_headers else "Time"
    mean = "Mean(uV)" if unit_headers else "Mean"
    lower = "Lower(uV)" if unit_headers else "Lower"
    upper = "Upper(uV)" if unit_headers else "Upper"
    return pd.DataFrame(
        {
            time: [-1.0, -0.75, 0.25, 0.5, 1.8, 2.2],
            "Condition": ["Stimulus", "Control", "Stimulus", "Control", "Stimulus", "Control"],
            mean: [1.0, 0.8, 2.4, 1.4, 1.7, 1.1],
            lower: [0.2, 0.4, 1.1, 0.9, 1.6, 0.3],
            upper: [1.3, 1.7, 3.8, 2.0, 2.9, 1.5],
            "AcquisitionNote": ["kept"] * 6,
        }
    )


def _write_event_csv(tmp_path: Path, *, unit_headers: bool = True) -> Path:
    source = tmp_path / ("event_units.csv" if unit_headers else "event_bare.csv")
    _event_frame(unit_headers=unit_headers).to_csv(source, index=False)
    return source


def _assignments(*, unit_headers: bool = True) -> tuple[tuple[str, str], ...]:
    suffix = "(uV)" if unit_headers else ""
    return (
        (("Time(s)" if unit_headers else "Time"), "x"),
        ("Condition", "condition"),
        (f"Mean{suffix}", "mean"),
        (f"Lower{suffix}", "lower"),
        (f"Upper{suffix}", "upper"),
        ("AcquisitionNote", "ignored"),
    )


def _mapping(
    *,
    unit_headers: bool = True,
    context: object = None,
) -> ScientificColumnMapping:
    kwargs = {}
    if context is not None:
        kwargs["scientific_context"] = context
    return ScientificColumnMapping(_assignments(unit_headers=unit_headers), **kwargs)


def _semantic_proposal(preparation):
    prepared = SimpleNamespace(
        template_id="event_response",
        source_columns=preparation.source_columns,
        confidence=preparation.confidence,
        requires_confirmation=preparation.requires_confirmation,
        confirmation_reasons=preparation.confirmation_reasons,
        payload=preparation,
    )
    return propose_prepared_semantics(prepared)


def test_event_response_route_declares_five_unique_roles_plus_ignore() -> None:
    assert "event_response" in SUPPORTED_SCIENTIFIC_TEMPLATE_IDS
    assert role_options("event_response") == (
        ("x", "X / 横坐标", True),
        ("condition", "Condition / 条件", True),
        ("mean", "Mean / 上游均值", True),
        ("lower", "Lower / 上游下界", True),
        ("upper", "Upper / 上游上界", True),
        ("ignored", "Ignored / 不绘制", False),
    )


@pytest.mark.parametrize("context", [None, {}, ()])
def test_empty_mapping_context_preserves_the_legacy_two_key_payload(context: object) -> None:
    mapping = _mapping(context=context)
    assert mapping.to_dict() == {
        "assignments": dict(_assignments()),
        "plot_mode": None,
    }


def test_mapping_freezes_and_sorts_dict_context_without_following_later_mutation() -> None:
    context = {"response_unit": "uV", "interval_label": INTERVAL, "time_unit": "s"}
    mapping = _mapping(context=context)
    context["time_unit"] = "ms"
    assert mapping.scientific_context == (
        ("interval_label", INTERVAL),
        ("response_unit", "uV"),
        ("time_unit", "s"),
    )
    assert mapping.to_dict()["scientific_context"] == {
        "interval_label": INTERVAL,
        "response_unit": "uV",
        "time_unit": "s",
    }


def test_complete_header_units_build_a_frozen_plan_and_layout_without_rewriting_rows(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path)
    preparation = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(context={"interval_label": INTERVAL}),
    )

    assert preparation.requires_confirmation is False
    assert preparation.scientific_context == (
        ("interval_label", INTERVAL),
        ("response_unit", "uV"),
        ("time_unit", "s"),
    )
    plan = preparation.plot_spec.event_response_plan
    layout = preparation.plot_spec.event_response_layout
    assert plan.condition_order == ("Stimulus", "Control")
    assert plan.condition_rows == (("Stimulus", (0, 2, 4)), ("Control", (1, 3, 5)))
    assert (plan.time_column, plan.mean_column, plan.lower_column, plan.upper_column) == (
        "Time(s)",
        "Mean(uV)",
        "Lower(uV)",
        "Upper(uV)",
    )
    assert plan.interval_label == INTERVAL
    assert layout.condition_colors[0][0] == "Stimulus"
    assert dict(preparation.assignments)["AcquisitionNote"] == "ignored"
    with pytest.raises(FrozenInstanceError):
        plan.interval_label = "changed"
    with pytest.raises(FrozenInstanceError):
        layout.interval_label_center = (0.0, 0.0)


def test_irregular_sampling_and_asymmetric_bounds_retain_exact_source_values(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path)
    preparation = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(context={"interval_label": INTERVAL}),
    )
    plan = preparation.plot_spec.event_response_plan
    original = pd.read_csv(source)
    assert [original.iloc[row][plan.time_column] for row in plan.condition_rows[0][1]] == [-1.0, 0.25, 1.8]
    assert original[plan.mean_column].sub(original[plan.lower_column]).tolist() == pytest.approx(
        [0.8, 0.4, 1.3, 0.5, 0.1, 0.8]
    )
    assert original[plan.upper_column].sub(original[plan.mean_column]).tolist() == pytest.approx(
        [0.3, 0.9, 1.4, 0.6, 1.2, 0.4]
    )


def test_bare_headers_accept_explicit_units_from_context(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path, unit_headers=False)
    preparation = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(
            unit_headers=False,
            context={"interval_label": INTERVAL, "time_unit": "s", "response_unit": "uV"},
        ),
    )
    assert preparation.requires_confirmation is False
    assert preparation.plot_spec.event_response_plan.time_unit == "s"
    assert preparation.plot_spec.event_response_plan.response_unit == "uV"


def test_missing_interval_label_returns_a_nonrenderable_draft_even_with_explicit_roles(
    tmp_path: Path,
) -> None:
    preparation = prepare_scientific(
        _write_event_csv(tmp_path),
        "event_response",
        column_mapping=_mapping(context={}),
    )
    assert preparation.mapping_confirmed is True
    assert preparation.requires_confirmation is True
    assert any("interval" in reason for reason in preparation.confirmation_reasons)
    assert preparation.plot_spec.event_response_plan is None
    assert preparation.plot_spec.event_response_layout is None


def test_missing_header_units_returns_a_draft_instead_of_inventing_units(tmp_path: Path) -> None:
    preparation = prepare_scientific(
        _write_event_csv(tmp_path, unit_headers=False),
        "event_response",
        column_mapping=_mapping(unit_headers=False, context={"interval_label": INTERVAL}),
    )
    assert preparation.requires_confirmation is True
    assert {reason for reason in preparation.confirmation_reasons if "unit" in reason}
    assert preparation.plot_spec.event_response_plan is None
    assert preparation.plot_spec.event_response_layout is None


@pytest.mark.parametrize(
    "context",
    [
        {"interval_label": INTERVAL, "time_unit": "ms"},
        {"interval_label": INTERVAL, "response_unit": "mV"},
    ],
)
def test_context_units_conflicting_with_headers_are_rejected_without_conversion(
    tmp_path: Path,
    context: dict[str, str],
) -> None:
    with pytest.raises(ScientificWorkflowError) as caught:
        prepare_scientific(
            _write_event_csv(tmp_path),
            "event_response",
            column_mapping=_mapping(context=context),
        )
    assert "conflict" in caught.value.code or "conflict" in str(caught.value).casefold()


@pytest.mark.parametrize(
    "context",
    [
        {"interval_label": INTERVAL, "unknown": "value"},
        {"interval_label": {"nested": "not allowed"}},
        {"interval_label": "line one\nline two"},
    ],
)
def test_mapping_uses_the_existing_strict_scientific_context_schema(context: object) -> None:
    with pytest.raises(ScientificContextError):
        _mapping(context=context)


def test_dict_and_frozen_tuple_contexts_produce_the_same_plan(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path, unit_headers=False)
    context = {"interval_label": INTERVAL, "time_unit": "s", "response_unit": "uV"}
    from_dict = prepare_scientific(
        source, "event_response", column_mapping=_mapping(unit_headers=False, context=context)
    )
    from_tuple = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(unit_headers=False, context=tuple(reversed(tuple(context.items())))),
    )
    assert from_dict.scientific_context == from_tuple.scientific_context
    assert from_dict.plan_digest == from_tuple.plan_digest
    assert from_dict.plot_spec.event_response_plan == from_tuple.plot_spec.event_response_plan


def test_context_change_invalidates_both_plan_and_semantic_proposal_hash(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path)
    first = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(context={"interval_label": "Supplied 95% CI"}),
    )
    second = prepare_scientific(
        source,
        "event_response",
        column_mapping=_mapping(context={"interval_label": "Supplied one-SD interval"}),
    )
    assert first.plan_digest != second.plan_digest
    assert _semantic_proposal(first).proposal_hash != _semantic_proposal(second).proposal_hash


def test_preparation_dict_prunes_absent_context_and_event_only_optional_fields(tmp_path: Path) -> None:
    source = tmp_path / "scatter.csv"
    pd.DataFrame({"X": [0, 1], "Y": [2, 3]}).to_csv(source, index=False)
    legacy = prepare_scientific(
        source,
        "scatter",
        column_mapping=ScientificColumnMapping((("X", "x"), ("Y", "series"))),
    )
    payload = legacy.to_dict()
    assert "scientific_context" not in payload
    assert "event_response_plan" not in payload["plot_spec"]
    assert "event_response_layout" not in payload["plot_spec"]


def test_low_level_preview_rejects_incomplete_context_even_if_called_without_service(tmp_path: Path) -> None:
    preparation = prepare_scientific(_write_event_csv(tmp_path), "event_response", column_mapping=_mapping())
    with pytest.raises(ScientificPreviewError) as caught:
        _build_scientific_preview_figure(preparation)
    assert caught.value.code == "scientific_context_required"


def test_unknown_event_response_mode_is_not_silently_replaced_by_a_default(tmp_path: Path) -> None:
    mapping = ScientificColumnMapping(
        _assignments(), plot_mode="compute_erp", scientific_context={"interval_label": INTERVAL}
    )
    with pytest.raises(ScientificWorkflowError) as caught:
        prepare_scientific(_write_event_csv(tmp_path), "event_response", column_mapping=mapping)
    assert caught.value.code == "mapping_plot_mode"


def test_legacy_native_plot_report_has_its_exact_pre_event_shape() -> None:
    # Captured from verified native teaching-data output, including b8de82f's heatmap field.
    expected = json.loads((ROOT / "tests/fixtures/legacy_bar_plot_spec.json").read_text("utf-8"))
    prepared = prepare_scientific(ROOT / "examples/gallery/bar_grouped_error.csv", "bar")
    actual = json.loads(json.dumps(prepared.plot_spec.to_dict()))
    assert actual == expected


def test_complete_event_data_cannot_fall_through_to_a_generic_line_preview(tmp_path: Path) -> None:
    preparation = prepare_scientific(
        _write_event_csv(tmp_path),
        "event_response",
        column_mapping=_mapping(context={"interval_label": INTERVAL}),
    )
    figure = _build_scientific_preview_figure(preparation)
    assert len(figure.axes[0].collections) == 2  # Each supplied condition keeps its own band.


def test_missing_scientific_facts_cannot_be_confirmed_by_a_generic_resolution_choice(tmp_path: Path) -> None:
    source = _write_event_csv(tmp_path)
    draft = prepare_scientific(source, "event_response", column_mapping=_mapping())
    proposal = _semantic_proposal(draft)
    resolutions = {item.ambiguity_id: "provide_scientific_context" for item in proposal.ambiguities}
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=True, resolved_ambiguities=resolutions)
    assert caught.value.code == "semantic_scientific_context_required"
    ready = prepare_scientific(
        source, "event_response", column_mapping=_mapping(context={"interval_label": INTERVAL})
    )
    assert _semantic_proposal(ready).confirm(user_confirmed=True).proposal.scientific_context
