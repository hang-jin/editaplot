"""Exercise real Service/Core/worker context seams without COM or public registration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))
sys.path.insert(0, str(ROOT / "skill/editaplot/scripts"))

import editaplot_core as core  # noqa: E402
from origin_sciplot.scientific_workflow import ScientificColumnMapping, ScientificWorkflowError  # noqa: E402
from origin_sciplot.template_service import (  # noqa: E402
    ScientificTemplateService,
    TemplateServiceError,
    TemplateServiceRegistry,
)
from origin_sciplot.workers import run_template_worker as worker  # noqa: E402


@pytest.fixture
def route(tmp_path):
    path = tmp_path / "response.csv"
    pd.DataFrame(
        {
            "Time (s)": [-1, 0, 1],
            "Condition": ["A"] * 3,
            "Mean (uV)": [0, 1, 0.5],
            "Lower (uV)": [-0.2, 0.7, 0.4],
            "Upper (uV)": [0.4, 1.5, 0.8],
        }
    ).to_csv(path, index=False)
    assignments = dict(
        zip(pd.read_csv(path).columns, ("x", "condition", "mean", "lower", "upper"), strict=True)
    )
    service = ScientificTemplateService(SimpleNamespace(id="event_response", name="事件响应"))
    mapping = {"assignments": assignments, "scientific_context": {"interval_label": "Supplied 95% CI"}}
    return path, service, mapping


def test_core_prepare_keeps_context_and_service_exports_it_for_worker(route):
    path, service, mapping = route
    original = path.read_bytes()
    prepared = core._prepare_with_mapping(service, path, mapping)
    assert not prepared.requires_confirmation
    exported = service.worker_mapping(prepared)
    assert exported["scientific_context"] == {
        "interval_label": "Supplied 95% CI",
        "time_unit": "s",
        "response_unit": "uV",
    }
    replay = worker.parse_scientific_mapping_json(json.dumps(exported))
    assert replay.scientific_context == prepared.payload.scientific_context
    assert path.read_bytes() == original


def test_service_confirmation_carries_context_without_requiring_an_extra_csv_column(route):
    path, service, mapping = route
    draft = service.prepare(path)
    assert draft.requires_confirmation
    ready = service.confirm_mapping(
        draft,
        assignments=mapping["assignments"],
        energy_kind="default",
        scientific_context=mapping["scientific_context"],
    )
    assert not ready.requires_confirmation
    assert ready.source_columns == draft.source_columns
    assert ready.payload.plot_spec.event_response_plan.interval_label == "Supplied 95% CI"


@pytest.mark.parametrize("complete", [False, True])
def test_understanding_explains_context_and_blocks_only_the_missing_facts(route, monkeypatch, complete):
    path, service, mapping = route
    prepared = service.prepare(
        path,
        column_mapping=ScientificColumnMapping(
            tuple(mapping["assignments"].items()),
            scientific_context=mapping["scientific_context"] if complete else (),
        ),
    )
    monkeypatch.setattr(
        core, "_prepare_template_for_understanding", lambda *a, **k: (service, prepared, ROOT)
    )
    result = core.understand_data(path, template_id="event_response")
    assert result["understanding"]["scientific_context"] == dict(prepared.payload.scientific_context)
    assert result["confirmation_gate"]["can_confirm_now"] is complete
    assert all(item["disposition"] != "uncertain" for item in result["understanding"]["column_decisions"])
    if complete:
        elements = result["understanding"]["figure_elements"]
        assert any(item["element_kind"] == "uncertainty_band" for item in elements)
        assert any(item["element_kind"] == "reference_line" for item in elements)
        assert all(item["required"] for item in elements if item["element_kind"] == "reference_line")
    else:
        assert result["state"] == "awaiting_scientific_context"
        assert any("interval" in item["question_zh"] for item in result["understanding"]["ambiguities"])


@pytest.mark.parametrize("bad", [{"unknown": "value"}, {"interval_label": {"nested": 1}}])
def test_worker_decoder_rejects_invalid_context_before_any_origin_access(route, bad):
    _path, _service, mapping = route
    with pytest.raises(ScientificWorkflowError, match="mapping"):
        worker.parse_scientific_mapping_json(json.dumps({**mapping, "scientific_context": bad}))


def test_invalid_context_has_a_normalized_error_at_public_service_and_core_seams(route):
    path, service, mapping = route
    invalid = {"interval_label": {"nested": "invalid"}}
    with pytest.raises(core.EditaPlotError, match="context"):
        core._prepare_with_mapping(service, path, {**mapping, "scientific_context": invalid})
    with pytest.raises(TemplateServiceError, match="context"):
        service.confirm_mapping(
            service.prepare(path),
            assignments=mapping["assignments"],
            energy_kind="default",
            scientific_context=invalid,
        )


def test_planned_route_is_read_only_at_plan_preview_and_worker_entry_points(route):
    path, _service, mapping = route
    service = TemplateServiceRegistry().get("event_response")
    ready = core._prepare_with_mapping(service, path, mapping)
    with pytest.raises(TemplateServiceError) as caught:
        service.render_preview(ready)
    assert caught.value.code == "template_not_implemented"
    with pytest.raises(core.EditaPlotError) as caught:
        core.build_plan(
            path,
            template_id="event_response",
            mapping=mapping,
            claim="Synthetic response.",
            evidence_role="software regression only",
            engine_home=ROOT / "runtime",
        )
    assert caught.value.code == "template_not_implemented"
    with pytest.raises(ScientificWorkflowError) as caught:
        worker._load_template_manifest("event_response")
    assert caught.value.code == "template_not_implemented"


@pytest.mark.parametrize("mode", [False, 0, [], ""])
def test_explicit_invalid_event_modes_do_not_become_defaults_at_core_or_worker(route, mode):
    path, service, mapping = route
    with pytest.raises((core.EditaPlotError, TemplateServiceError)):
        core._prepare_with_mapping(service, path, {**mapping, "plot_mode": mode})
    with pytest.raises(ScientificWorkflowError):
        worker.parse_scientific_mapping_json(
            json.dumps({**mapping, "plot_mode": mode}), template_id="event_response"
        )
