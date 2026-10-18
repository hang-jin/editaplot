from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "runtime/src"), str(ROOT / "skill/editaplot/scripts"), str(ROOT)]

from editaplot_core import build_plan, understand_data  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
)

from tools.generate_research_data import flim_phasor_data  # noqa: E402


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "synthetic_phasor.csv"
    flim_phasor_data().to_csv(path, index=False, float_format="%.10g")
    return path


def test_phasor_route_keeps_source_and_freezes_equal_unit_geometry(source):
    before = source.read_bytes()
    prepared = prepare_scientific(source, "flim_phasor")
    plan = prepared.plot_spec.phasor_plan
    style = prepared.plot_spec.display_plan.figure_style

    assert prepared.row_count == 540
    assert len(plan.group_order) == 3
    assert source.read_bytes() == before
    assert dict(prepared.assignments) == {"G": "x", "S": "series", "Group": "category"}
    assert not prepared.requires_confirmation
    x_cm_per_unit = style.page_width_cm * style.layer_width_percent / 100 / np.ptp(plan.x_range)
    y_cm_per_unit = style.page_height_cm * style.layer_height_percent / 100 / np.ptp(plan.y_range)
    assert x_cm_per_unit == pytest.approx(y_cm_per_unit)
    assert style.x_title_upshift_page_percent == 0
    assert style.profile_name.endswith("-external-legend")


def test_chinese_columns_and_extra_columns_require_explicit_confirmation(tmp_path):
    data = flim_phasor_data().rename(columns={"G": "相量G", "S": "相量S", "Group": "分组"})
    data["备注"] = "合成数据"
    path = tmp_path / "相量.csv"
    data.to_csv(path, index=False)
    prepared = prepare_scientific(path, "flim_phasor")
    assert dict(prepared.assignments) == {
        "相量G": "x",
        "相量S": "series",
        "分组": "category",
        "备注": "ignored",
    }
    assert prepared.requires_confirmation
    confirmed = prepare_scientific(
        path, "flim_phasor", column_mapping=ScientificColumnMapping(prepared.assignments)
    )
    assert not confirmed.requires_confirmation
    assert confirmed.plot_spec.phasor_plan.g_column == "相量G"


def test_extreme_aspect_fails_without_shrinking_fonts(tmp_path):
    data = flim_phasor_data()
    data.loc[0, "G"] = 300.0
    path = tmp_path / "extreme.csv"
    data.to_csv(path, index=False)
    with pytest.raises(ScientificWorkflowError, match="physical|layout"):
        prepare_scientific(path, "flim_phasor")


def test_preview_keeps_all_points_and_semicircle_metric(source):
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure
    from origin_sciplot.scientific_workflow import load_scientific_frame

    preparation = prepare_scientific(source, "flim_phasor")
    figure = _build_scientific_preview_figure(preparation)
    axis = figure.axes[0]
    points = np.concatenate([collection.get_offsets() for collection in axis.collections])
    assert points.shape == (540, 2)
    raw = load_scientific_frame(source, preparation)
    plan = preparation.plot_spec.phasor_plan
    expected = np.concatenate(
        [
            raw.iloc[list(rows)][[plan.g_column, plan.s_column]].to_numpy(dtype=float)
            for _label, rows in plan.group_rows
        ]
    )
    np.testing.assert_array_equal(points, expected)
    assert len(axis.lines) == 1
    assert len(axis.lines[0].get_xdata()) == 181
    rectangle = axis.get_position()
    ratio = (rectangle.width * figure.get_figwidth() / np.ptp(axis.get_xlim())) / (
        rectangle.height * figure.get_figheight() / np.ptp(axis.get_ylim())
    )
    assert ratio == pytest.approx(1.0, rel=0.003)
    assert axis.get_legend() is not None
    assert not axis.get_legend().get_frame_on()
    figure.clear()


def test_math_reference_requires_explicit_approval(source):
    from editaplot_core import EditaPlotError

    understanding = understand_data(source, template_id="flim_phasor", engine_home=ROOT / "runtime")
    proposal = understanding["understanding"]
    reference = next(
        item for item in proposal["derived_items"] if item["operation_id"] == "phasor_reference_semicircle"
    )
    assert reference["explicit_approval_required"] is True
    assert reference["parameters"]["reference_kind"] == "mathematical_reference_not_experimental_data"
    element = next(
        item for item in proposal["figure_elements"] if item["element_id"] == "phasor_reference_semicircle"
    )
    assert element["element_kind"] == "line"
    assert element["axis"] == "mathematical_reference_not_experimental_data"
    assert element["data_item_ids"] == [reference["item_id"]]
    confirmation = understanding["confirmation_gate"]["confirmation_payload_template"]
    result = build_plan(
        source,
        template_id="flim_phasor",
        claim="Synthetic upstream phasor coordinate comparison.",
        evidence_role="distribution",
        semantic_confirmation=confirmation,
        engine_home=ROOT / "runtime",
    )
    from editaplot_core import VERIFIED_TEMPLATE_IDS

    assert result["can_render"] is ("flim_phasor" in VERIFIED_TEMPLATE_IDS)
    with pytest.raises(EditaPlotError, match="approv"):
        build_plan(
            source,
            template_id="flim_phasor",
            claim="Synthetic upstream phasor coordinate comparison.",
            evidence_role="distribution",
            semantic_confirmation={**confirmation, "approved_derived_item_ids": []},
            engine_home=ROOT / "runtime",
        )


def test_fixed_reference_operation_rejects_changed_parameters(source):
    from origin_sciplot.semantic_contract import DataDisposition, DerivedDataItem, SemanticContractError

    item = DerivedDataItem(
        item_id="reference",
        semantic_role="mathematical_reference",
        disposition=DataDisposition.RENDER_SECONDARY,
        operation_id="phasor_reference_semicircle",
        input_item_ids=("g", "s"),
        confidence=1.0,
        parameters=(
            ("center_g", 0.5),
            ("center_s", 0.0),
            ("radius", 0.5),
            ("point_count", 181),
            ("reference_kind", "mathematical_reference_not_experimental_data"),
            ("lineage_kind", "coordinate_definition_not_value_derivation"),
        ),
    )
    item.validate()
    with pytest.raises(SemanticContractError, match="fixed"):
        changed = tuple((key, 0.7 if key == "radius" else value) for key, value in item.parameters)
        replace(item, parameters=changed).validate()


def test_planned_route_preparation_does_not_execute_service_or_enter_implemented(source, monkeypatch):
    from origin_sciplot import template_service
    from origin_sciplot.template_registry import TemplateRegistry

    backing = TemplateRegistry(ROOT / "runtime/templates")
    planned = replace(backing.get("flim_phasor"), status="planned")
    from types import SimpleNamespace

    registry = template_service.TemplateServiceRegistry(
        SimpleNamespace(
            implemented=lambda: [m for m in backing.implemented() if m.id != "flim_phasor"],
            get=lambda template_id: planned if template_id == "flim_phasor" else backing.get(template_id),
        )
    )
    before = [service.manifest.id for service in registry.implemented()]

    def reject_dynamic_load(*_args, **_kwargs):
        raise AssertionError("A planned route must not execute an arbitrary service.py")

    monkeypatch.setattr(template_service.importlib.util, "spec_from_file_location", reject_dynamic_load)
    service = registry.get("flim_phasor")
    prepared = service.prepare(source)
    assert prepared.row_count == 540
    assert service.manifest.status == "planned"
    assert [service.manifest.id for service in registry.implemented()] == before
    assert "flim_phasor" not in before


def test_planned_manifest_cannot_render_with_stale_verified_membership(source, monkeypatch):
    from types import SimpleNamespace

    import editaplot_core as core
    from origin_sciplot import template_service
    from origin_sciplot.template_registry import TemplateRegistry

    planned = replace(TemplateRegistry(ROOT / "runtime/templates").get("flim_phasor"), status="planned")
    service = template_service.ScientificTemplateService(planned)
    monkeypatch.setattr(
        template_service, "TemplateServiceRegistry", lambda: SimpleNamespace(get=lambda _: service)
    )
    monkeypatch.setattr(core, "VERIFIED_TEMPLATE_IDS", core.VERIFIED_TEMPLATE_IDS | {"flim_phasor"})
    understanding = core.understand_data(source, template_id="flim_phasor", engine_home=ROOT / "runtime")
    result = core.build_plan(
        source,
        template_id="flim_phasor",
        claim="Synthetic precomputed coordinate comparison.",
        evidence_role="distribution",
        engine_home=ROOT / "runtime",
        semantic_confirmation=understanding["confirmation_gate"]["confirmation_payload_template"],
    )
    assert result["can_render"] is False
    assert "template_not_implemented" in result["blocked_reasons"]


def test_existing_shap_digest_does_not_include_empty_phasor_field():
    prepared = prepare_scientific(ROOT / "examples/gallery/medical_shap_summary.csv", "shap_summary")
    assert prepared.plot_spec.phasor_plan is None
    assert prepared.plan_digest == "514b394faa9b89b807144df8eb3252457577ddf974c1dddeed8098e5346d2d1d"
