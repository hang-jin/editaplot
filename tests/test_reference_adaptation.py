from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.reference_adaptation import (  # noqa: E402
    ALLOWED_REFERENCE_PRIMITIVES,
    TEMPLATE_PRIMITIVE_COMPATIBILITY,
    ReferenceAdaptationError,
    ReferenceAdaptationRoute,
    build_reference_adaptation_plan,
)
from origin_sciplot.reference_figure import (  # noqa: E402
    REFERENCE_FIGURE_JSON_SCHEMA,
    ReferenceFigureSpec,
    inspect_reference_image,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    SUPPORTED_SCIENTIFIC_TEMPLATE_IDS,
)
from origin_sciplot.semantic_contract import (  # noqa: E402
    ConfirmedSemanticContract,
    DataDisposition,
    FigureElement,
    SemanticDataItem,
    SemanticProposal,
)


def _confirmed_semantic_contract() -> ConfirmedSemanticContract:
    proposal = SemanticProposal(
        source_sha256="1" * 64,
        source_columns=(
            "2Theta",
            "Yobs private values",
            "Ycalc private values",
            "Weight",
            "Internal note",
        ),
        domain_family="xrd",
        domain_mode="rietveld_refinement",
        domain_confidence=0.97,
        data_items=(
            SemanticDataItem(
                item_id="theta",
                source_column="2Theta",
                semantic_role="two_theta",
                disposition=DataDisposition.RENDER_PRIMARY,
                confidence=0.99,
            ),
            SemanticDataItem(
                item_id="observed",
                source_column="Yobs private values",
                semantic_role="observed_intensity",
                disposition=DataDisposition.RENDER_PRIMARY,
                confidence=0.98,
            ),
            SemanticDataItem(
                item_id="calculated",
                source_column="Ycalc private values",
                semantic_role="calculated_intensity",
                disposition=DataDisposition.RENDER_SECONDARY,
                confidence=0.97,
            ),
            SemanticDataItem(
                item_id="weight",
                source_column="Weight",
                semantic_role="refinement_weight",
                disposition=DataDisposition.SUPPORT_ONLY,
                confidence=0.95,
            ),
            SemanticDataItem(
                item_id="internal_note",
                source_column="Internal note",
                semantic_role="refinement_auxiliary",
                disposition=DataDisposition.RETAIN_NOT_RENDER,
                confidence=0.93,
            ),
        ),
        figure_elements=(
            FigureElement(
                element_id="observed_curve",
                element_kind="symbol",
                data_item_ids=("theta", "observed"),
                required=True,
            ),
            FigureElement(
                element_id="calculated_curve",
                element_kind="line",
                data_item_ids=("theta", "calculated"),
                required=True,
            ),
        ),
    )
    return proposal.confirm(user_confirmed=True)


def _reference_spec(
    tmp_path: Path,
    *,
    observed_binding: str = "observed",
    extra_mark: str | None = None,
    extra_mark_binding: str | None = None,
    include_inset: bool = False,
    mark_id: str = "observed_mark",
    optional_unbound: bool = False,
) -> ReferenceFigureSpec:
    source = tmp_path / "reference.png"
    Image.new("RGB", (16, 10), "white").save(source)
    metadata = inspect_reference_image(source)
    marks: list[dict[str, object]] = [
        {
            "id": mark_id,
            "panel_id": "main",
            "kind": "symbol",
            "evidence_role": "primary",
            "essential": True,
            "confidence": 0.95,
        },
        {
            "id": "calculated_mark",
            "panel_id": "main",
            "kind": "line",
            "evidence_role": "validation",
            "essential": True,
            "confidence": 0.94,
        },
        {
            "id": "legend_mark",
            "panel_id": "main",
            "kind": "legend",
            "evidence_role": "context",
            "essential": False,
            "confidence": 0.9,
        },
    ]
    if extra_mark is not None:
        marks.append(
            {
                "id": "extra_mark",
                "panel_id": "main",
                "kind": extra_mark,
                "evidence_role": "context",
                "essential": False,
                "confidence": 0.8,
            }
        )
    if include_inset:
        marks.append(
            {
                "id": "inset_mark",
                "panel_id": "main",
                "kind": "inset",
                "evidence_role": "context",
                "essential": False,
                "confidence": 0.91,
            }
        )
    encodings: list[dict[str, object]] = [
        {
            "id": "observed_y",
            "mark_id": mark_id,
            "channel": "y",
            "semantic_role": "observed_intensity",
            "data_binding": observed_binding,
            "confidence": 0.94,
        },
        {
            "id": "calculated_y",
            "mark_id": "calculated_mark",
            "channel": "y",
            "semantic_role": "calculated_intensity",
            "data_binding": "calculated",
            "confidence": 0.93,
        },
    ]
    if extra_mark is not None and extra_mark_binding is not None:
        encodings.append(
            {
                "id": "extra_mark_y",
                "mark_id": "extra_mark",
                "channel": "y",
                "semantic_role": "context_value",
                "data_binding": extra_mark_binding,
                "confidence": 0.8,
            }
        )
    if optional_unbound:
        marks.append(
            {
                "id": "optional_reference",
                "panel_id": "main",
                "kind": "reference_line",
                "evidence_role": "context",
                "essential": False,
                "confidence": 0.7,
            }
        )
        encodings.append(
            {
                "id": "optional_reference_y",
                "mark_id": "optional_reference",
                "channel": "y",
                "semantic_role": "reference_value",
                "data_binding": None,
                "confidence": 0.7,
            }
        )
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "reference": metadata.to_dict(),
        "layout": {
            "archetype": "single_chart",
            "aspect_ratio_class": "wide",
            "panels": [
                {
                    "id": "main",
                    "evidence_role": "hero",
                    "coordinate_system": "cartesian_2d",
                    "relative_bbox": [0.0, 0.0, 1.0, 1.0],
                    "shared_axis_group": None,
                }
            ],
        },
        "marks": marks,
        "encodings": encodings,
        "style": {
            "palette_family": "navy_cyan_gold",
            "palette_id": None,
            "line_weight": "medium",
            "marker_density": "dense",
            "fill_transparency": "none",
            "legend_position": "inside",
            "legend_frame": False,
            "grid": "none",
            "background": "white",
            "typography_hierarchy": "publication_informed",
        },
        "text_roles": [
            {
                "id": "x_axis",
                "panel_id": "main",
                "role": "x_title",
                "observed_present": True,
                "copy_policy": "user_data_or_confirmation_only",
                "binding_id": "theta",
                "confidence": 0.92,
            },
            {
                "id": "unbound_annotation",
                "panel_id": "main",
                "role": "annotation",
                "observed_present": True,
                "copy_policy": "user_data_or_confirmation_only",
                "binding_id": None,
                "confidence": 0.6,
            },
        ],
        "essential_features": [
            {
                "id": "observed_feature",
                "feature_role": "primary_measurement",
                "mark_ids": [mark_id],
                "required_encoding_ids": ["observed_y"],
            },
            {
                "id": "calculated_feature",
                "feature_role": "fit_validation",
                "mark_ids": ["calculated_mark"],
                "required_encoding_ids": ["calculated_y"],
            },
        ],
        "confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_contract_sha256": None,
        },
    }
    return ReferenceFigureSpec.from_dict(payload, image_metadata=metadata).confirm()


def _confirmed_domain_contract(
    domain_family: str,
    domain_mode: str,
    items: tuple[tuple[str, str, DataDisposition], ...],
) -> ConfirmedSemanticContract:
    proposal = SemanticProposal(
        source_sha256="2" * 64,
        source_columns=tuple(item_id for item_id, _role, _disposition in items),
        domain_family=domain_family,
        domain_mode=domain_mode,
        domain_confidence=1.0,
        data_items=tuple(
            SemanticDataItem(
                item_id=item_id,
                source_column=item_id,
                semantic_role=role,
                disposition=disposition,
                confidence=1.0,
            )
            for item_id, role, disposition in items
        ),
        figure_elements=tuple(
            FigureElement(
                element_id=f"{item_id}_element",
                element_kind="line",
                data_item_ids=(item_id,),
                required=True,
            )
            for item_id, _role, disposition in items
            if disposition
            in {
                DataDisposition.RENDER_PRIMARY,
                DataDisposition.RENDER_SECONDARY,
            }
        ),
    )
    return proposal.confirm(user_confirmed=True)


def _primitive_reference(
    tmp_path: Path,
    primitives: tuple[tuple[str, str, str, bool], ...],
) -> ReferenceFigureSpec:
    source = tmp_path / "primitive-reference.png"
    Image.new("RGB", (18, 12), "white").save(source)
    metadata = inspect_reference_image(source)
    marks = [
        {
            "id": primitive_id,
            "panel_id": "main",
            "kind": primitive,
            "evidence_role": "primary" if essential else "context",
            "essential": essential,
            "confidence": 0.95,
        }
        for primitive_id, primitive, _binding_id, essential in primitives
    ]
    encodings = [
        {
            "id": f"{primitive_id}_encoding",
            "mark_id": primitive_id,
            "channel": "y",
            "semantic_role": "confirmed_value",
            "data_binding": binding_id,
            "confidence": 0.95,
        }
        for primitive_id, _primitive, binding_id, _essential in primitives
    ]
    essential_features = [
        {
            "id": f"{primitive_id}_feature",
            "feature_role": f"{primitive}_evidence",
            "mark_ids": [primitive_id],
            "required_encoding_ids": [f"{primitive_id}_encoding"],
        }
        for primitive_id, primitive, _binding_id, essential in primitives
        if essential
    ]
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "reference": metadata.to_dict(),
        "layout": {
            "archetype": "single_chart",
            "aspect_ratio_class": "adaptive",
            "panels": [
                {
                    "id": "main",
                    "evidence_role": "hero",
                    "coordinate_system": "cartesian_2d",
                    "relative_bbox": [0.0, 0.0, 1.0, 1.0],
                    "shared_axis_group": None,
                }
            ],
        },
        "marks": marks,
        "encodings": encodings,
        "style": {
            "palette_family": "navy_cyan_gold",
            "palette_id": None,
            "line_weight": "medium",
            "marker_density": "adaptive",
            "fill_transparency": "light",
            "legend_position": "inside",
            "legend_frame": False,
            "grid": "none",
            "background": "white",
            "typography_hierarchy": "publication_informed",
        },
        "text_roles": [],
        "essential_features": essential_features,
        "confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_contract_sha256": None,
        },
    }
    return ReferenceFigureSpec.from_dict(payload, image_metadata=metadata).confirm()


def test_adaptation_allowlist_covers_every_declared_mark_and_public_template() -> None:
    declared_marks = set(
        REFERENCE_FIGURE_JSON_SCHEMA["properties"]["marks"]["items"]["properties"]["kind"]["enum"]
    )

    assert ALLOWED_REFERENCE_PRIMITIVES == declared_marks
    assert set(TEMPLATE_PRIMITIVE_COMPATIBILITY) == {
        *SUPPORTED_SCIENTIFIC_TEMPLATE_IDS,
        "xps",
    }


def test_template_adaptation_plan_is_stable_path_free_and_hash_bound(tmp_path: Path) -> None:
    semantics = _confirmed_semantic_contract()
    reference = _reference_spec(tmp_path, optional_unbound=True)

    plan = build_reference_adaptation_plan(
        semantics,
        reference,
        route="template_adaptation",
        template_id="xrd",
    )
    payload = plan.to_dict()

    assert plan.route is ReferenceAdaptationRoute.TEMPLATE_ADAPTATION
    assert plan.template_id == "xrd"
    assert payload["semantic_contract_hash"] == semantics.contract_hash
    assert payload["reference_contract_hash"] == reference.contract_sha256
    assert payload["origin_capability_gate"]["template_profile_id"] == "xrd"
    assert payload["origin_capability_gate"]["support_status"] == "capability_gated"
    assert payload["style_tokens"] == reference.to_dict()["style"]
    assert payload["omitted_reference_elements"] == {
        "primitive_ids": ["optional_reference"],
        "encoding_ids": ["optional_reference_y"],
        "text_role_ids": ["unbound_annotation"],
        "rejected_primitives": [],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "private values" not in encoded
    assert str(tmp_path) not in encoded
    assert "ocr_text" not in encoded
    assert len(payload["plan_hash"]) == 64


def test_same_confirmed_inputs_produce_same_plan_hash(tmp_path: Path) -> None:
    semantics = _confirmed_semantic_contract()
    reference = _reference_spec(tmp_path)

    first = build_reference_adaptation_plan(
        semantics,
        reference,
        route="template_adaptation",
        template_id="xrd",
        semantic_bindings={
            "calculated": "calculated",
            "observed": "observed",
            "theta": "theta",
        },
    )
    second = build_reference_adaptation_plan(
        semantics,
        reference,
        route="template_adaptation",
        template_id="xrd",
        semantic_bindings={
            "theta": "theta",
            "observed": "observed",
            "calculated": "calculated",
        },
    )

    assert first.to_dict() == second.to_dict()
    assert first.plan_hash == second.plan_hash


def test_controlled_composition_is_experimental_and_flags_inset_capability(
    tmp_path: Path,
) -> None:
    plan = build_reference_adaptation_plan(
        _confirmed_semantic_contract(),
        _reference_spec(tmp_path, include_inset=True),
        route="controlled_composition",
    ).to_dict()

    assert plan["template_id"] is None
    assert plan["origin_capability_gate"] == {
        "template_profile_id": None,
        "template_profile_required": False,
        "additional_required_capabilities": ["inset_layer"],
        "support_status": "experimental",
    }
    assert any(item["primitive"] == "inset" for item in plan["primitives"])


def test_template_route_requires_safe_template_id(tmp_path: Path) -> None:
    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            _reference_spec(tmp_path),
            route="template_adaptation",
            template_id=None,
        )

    assert caught.value.code == "reference_template_required"


def test_controlled_composition_rejects_template_identity(tmp_path: Path) -> None:
    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            _reference_spec(tmp_path),
            route="controlled_composition",
            template_id="xrd",
        )

    assert caught.value.code == "reference_template_forbidden"


def test_declared_bar_primitive_remains_available_to_controlled_composition(
    tmp_path: Path,
) -> None:
    payload = build_reference_adaptation_plan(
        _confirmed_semantic_contract(),
        _reference_spec(
            tmp_path,
            extra_mark="bar",
            extra_mark_binding="observed",
        ),
        route="controlled_composition",
    ).to_dict()

    assert any(item["primitive"] == "bar" for item in payload["primitives"])
    assert "categorical_axis" in payload["origin_capability_gate"][
        "additional_required_capabilities"
    ]


@pytest.mark.parametrize(
    ("template_id", "domain_mode", "primitive", "required_capability"),
    [
        ("bar", "default", "bar", "categorical_axis"),
        ("grouped_box", "wide_category_group_raw", "box", "statistical_plot"),
        ("heatmap", "default", "heatmap_cell", "matrix_heatmap"),
    ],
)
def test_data_primitives_pass_only_their_compatible_public_template(
    tmp_path: Path,
    template_id: str,
    domain_mode: str,
    primitive: str,
    required_capability: str,
) -> None:
    semantics = _confirmed_domain_contract(
        template_id,
        domain_mode,
        (("value", "series", DataDisposition.RENDER_PRIMARY),),
    )
    reference = _primitive_reference(
        tmp_path,
        ((f"{primitive}_mark", primitive, "value", True),),
    )

    payload = build_reference_adaptation_plan(
        semantics,
        reference,
        route="template_adaptation",
        template_id=template_id,
    ).to_dict()

    assert payload["primitives"][0]["primitive"] == primitive
    assert payload["template_compatibility"]["enforced"] is True
    assert primitive in payload["template_compatibility"]["compatible_primitives"]
    assert required_capability in payload["origin_capability_gate"][
        "additional_required_capabilities"
    ]


@pytest.mark.parametrize("primitive", ["bar", "box", "heatmap_cell"])
def test_essential_data_primitive_is_rejected_by_wrong_xrd_template(
    tmp_path: Path,
    primitive: str,
) -> None:
    semantics = _confirmed_domain_contract(
        "xrd",
        "ordinary_scan",
        (("value", "intensity_series", DataDisposition.RENDER_PRIMARY),),
    )
    reference = _primitive_reference(
        tmp_path,
        ((f"{primitive}_mark", primitive, "value", True),),
    )

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            semantics,
            reference,
            route="template_adaptation",
            template_id="xrd",
        )

    assert caught.value.code == "reference_essential_primitive_incompatible"


def test_nonessential_incompatible_primitive_is_omitted_with_reason(
    tmp_path: Path,
) -> None:
    payload = build_reference_adaptation_plan(
        _confirmed_semantic_contract(),
        _reference_spec(
            tmp_path,
            extra_mark="bar",
            extra_mark_binding="observed",
        ),
        route="template_adaptation",
        template_id="xrd",
    ).to_dict()

    assert not any(item["primitive"] == "bar" for item in payload["primitives"])
    assert payload["omitted_reference_elements"]["rejected_primitives"] == [
        {
            "primitive_id": "extra_mark",
            "primitive": "bar",
            "reason_code": "template_primitive_incompatible",
        }
    ]
    assert "extra_mark" in payload["omitted_reference_elements"]["primitive_ids"]
    assert "extra_mark_y" in payload["omitted_reference_elements"]["encoding_ids"]


def test_unbound_nonessential_incompatible_primitive_still_records_reason(
    tmp_path: Path,
) -> None:
    payload = build_reference_adaptation_plan(
        _confirmed_semantic_contract(),
        _reference_spec(tmp_path, extra_mark="box"),
        route="template_adaptation",
        template_id="xrd",
    ).to_dict()

    assert payload["omitted_reference_elements"]["rejected_primitives"] == [
        {
            "primitive_id": "extra_mark",
            "primitive": "box",
            "reason_code": "template_primitive_incompatible",
        }
    ]


def test_rietveld_mode_accepts_confirmed_residual_and_phase_tick_primitives(
    tmp_path: Path,
) -> None:
    semantics = _confirmed_domain_contract(
        "xrd",
        "rietveld_refinement",
        (
            (
                "residual",
                "difference_curve",
                DataDisposition.RENDER_SECONDARY,
            ),
            (
                "phase_positions",
                "phase_reflection_positions",
                DataDisposition.RENDER_SECONDARY,
            ),
        ),
    )
    reference = _primitive_reference(
        tmp_path,
        (
            ("residual_mark", "residual_curve", "residual", True),
            ("phase_mark", "phase_tick", "phase_positions", True),
        ),
    )

    payload = build_reference_adaptation_plan(
        semantics,
        reference,
        route="template_adaptation",
        template_id="xrd",
    ).to_dict()

    assert {item["primitive"] for item in payload["primitives"]} == {
        "residual_curve",
        "phase_tick",
    }
    # These are native parts of the confirmed XRD Rietveld renderer.  They do
    # not invent capability identifiers outside OriginCapability.
    assert payload["origin_capability_gate"]["additional_required_capabilities"] == []


@pytest.mark.parametrize("primitive", ["residual_curve", "phase_tick"])
def test_ordinary_xrd_mode_rejects_rietveld_only_primitives(
    tmp_path: Path,
    primitive: str,
) -> None:
    semantics = _confirmed_domain_contract(
        "xrd",
        "ordinary_scan",
        (("value", "intensity_series", DataDisposition.RENDER_PRIMARY),),
    )
    reference = _primitive_reference(
        tmp_path,
        ((f"{primitive}_mark", primitive, "value", True),),
    )

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            semantics,
            reference,
            route="template_adaptation",
            template_id="xrd",
        )

    assert caught.value.code == "reference_essential_primitive_incompatible"


def test_template_route_rejects_semantic_domain_mismatch(tmp_path: Path) -> None:
    semantics = _confirmed_domain_contract(
        "bar",
        "default",
        (("value", "series", DataDisposition.RENDER_PRIMARY),),
    )
    reference = _primitive_reference(
        tmp_path,
        (("bar_mark", "bar", "value", True),),
    )

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            semantics,
            reference,
            route="template_adaptation",
            template_id="xrd",
        )

    assert caught.value.code == "reference_template_semantic_domain_mismatch"


@pytest.mark.parametrize("semantic_item_id", ["weight", "internal_note"])
def test_support_and_retained_items_cannot_become_visible(
    tmp_path: Path,
    semantic_item_id: str,
) -> None:
    reference = _reference_spec(tmp_path, observed_binding="requested_visible")

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            reference,
            route="template_adaptation",
            template_id="xrd",
            semantic_bindings={
                "requested_visible": semantic_item_id,
                "calculated": "calculated",
                "theta": "theta",
            },
        )

    assert caught.value.code == "reference_binding_not_renderable"


def test_missing_essential_semantic_binding_is_a_hard_block(tmp_path: Path) -> None:
    reference = _reference_spec(tmp_path, observed_binding="requested_visible")

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            reference,
            route="template_adaptation",
            template_id="xrd",
            semantic_bindings={
                "calculated": "calculated",
                "theta": "theta",
            },
        )

    assert caught.value.code == "reference_binding_missing"


def test_unknown_semantic_binding_is_rejected(tmp_path: Path) -> None:
    reference = _reference_spec(tmp_path, observed_binding="requested_visible")

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            reference,
            route="template_adaptation",
            template_id="xrd",
            semantic_bindings={
                "requested_visible": "invented_item",
                "calculated": "calculated",
                "theta": "theta",
            },
        )

    assert caught.value.code == "reference_binding_unknown"


def test_unused_binding_entries_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            _reference_spec(tmp_path),
            route="template_adaptation",
            template_id="xrd",
            semantic_bindings={
                "observed": "observed",
                "calculated": "calculated",
                "theta": "theta",
                "hidden": "weight",
            },
        )

    assert caught.value.code == "reference_binding_unused"


def test_text_role_uses_confirmed_binding_not_reference_text(tmp_path: Path) -> None:
    payload = build_reference_adaptation_plan(
        _confirmed_semantic_contract(),
        _reference_spec(tmp_path),
        route="template_adaptation",
        template_id="xrd",
    ).to_dict()

    assert payload["text_roles"] == [
        {
            "text_role_id": "x_axis",
            "panel_id": "main",
            "role": "x_title",
            "semantic_item_id": "theta",
            "confirmed_semantic_role": "two_theta",
            "text_source": "confirmed_semantic_binding",
            "copy_policy": "user_data_or_confirmation_only",
        }
    ]
    assert not any("text" in item and item["text"] for item in payload["text_roles"])


@pytest.mark.parametrize("mark_id", ["publisher_logo", "author_signature", "render_command"])
def test_logo_author_and_command_identifiers_are_rejected(
    tmp_path: Path,
    mark_id: str,
) -> None:
    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            _reference_spec(tmp_path, mark_id=mark_id),
            route="controlled_composition",
        )

    assert caught.value.code in {
        "reference_content_not_adaptable",
        "reference_execution_content_forbidden",
    }


def test_unconfirmed_reference_spec_is_rejected(tmp_path: Path) -> None:
    confirmed = _reference_spec(tmp_path)
    payload = confirmed.to_dict()
    payload["confirmation"] = {
        "required": True,
        "confirmed": False,
        "confirmed_contract_sha256": None,
    }
    unconfirmed = ReferenceFigureSpec.from_dict(payload)

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(
            _confirmed_semantic_contract(),
            unconfirmed,
            route="controlled_composition",
        )

    assert caught.value.code == "reference_confirmation_required"


def test_unconfirmed_semantic_proposal_is_rejected(tmp_path: Path) -> None:
    proposal = _confirmed_semantic_contract().proposal

    with pytest.raises(ReferenceAdaptationError) as caught:
        build_reference_adaptation_plan(  # type: ignore[arg-type]
            proposal,
            _reference_spec(tmp_path),
            route="controlled_composition",
        )

    assert caught.value.code == "semantic_confirmation_required"
