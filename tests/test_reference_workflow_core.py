from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
RUNTIME = PRODUCT_ROOT / "runtime"
sys.path.insert(0, str(SCRIPTS))

from editaplot_core import (  # noqa: E402
    EditaPlotError,
    build_plan,
    build_worker_command,
    inspect_reference,
    review_reference_figure,
    understand_data,
)


def _draft_reference_spec(reference: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "reference": reference,
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
        "marks": [
            {
                "id": "measurement_curve",
                "panel_id": "main",
                "kind": "line",
                "evidence_role": "primary",
                "essential": True,
                "confidence": 0.95,
            },
            {
                "id": "legend",
                "panel_id": "main",
                "kind": "legend",
                "evidence_role": "context",
                "essential": False,
                "confidence": 0.9,
            },
        ],
        "encodings": [
            {
                "id": "measurement_y",
                "mark_id": "measurement_curve",
                "channel": "y",
                "semantic_role": "intensity_series",
                "data_binding": "intensity",
                "confidence": 0.95,
            }
        ],
        "style": {
            "palette_family": "cool_scientific",
            "palette_id": None,
            "line_weight": "medium",
            "marker_density": "none",
            "fill_transparency": "none",
            "legend_position": "inside",
            "legend_frame": False,
            "grid": "none",
            "background": "white",
            "typography_hierarchy": "publication_informed",
        },
        "text_roles": [
            {
                "id": "x_title",
                "panel_id": "main",
                "role": "x_title",
                "observed_present": True,
                "copy_policy": "user_data_or_confirmation_only",
                "binding_id": "theta",
                "confidence": 0.9,
            }
        ],
        "essential_features": [
            {
                "id": "measurement_evidence",
                "feature_role": "primary_measurement",
                "mark_ids": ["measurement_curve"],
                "required_encoding_ids": ["measurement_y"],
            }
        ],
        "confirmation": {
            "required": True,
            "confirmed": False,
            "confirmed_contract_sha256": None,
        },
    }


def test_reference_review_is_path_free_and_requires_separate_confirmation(
    tmp_path: Path,
) -> None:
    image = tmp_path / "参考图.png"
    Image.new("RGB", (32, 20), "white").save(image)

    inspected = inspect_reference(image, engine_home=RUNTIME)
    reviewed = review_reference_figure(
        image,
        _draft_reference_spec(inspected["reference"]),
        engine_home=RUNTIME,
    )

    assert "path" not in inspected["reference"]
    assert reviewed["state"] == "awaiting_reference_confirmation"
    assert reviewed["safety_boundary"]["copy_reference_values"] is False
    assert reviewed["safety_boundary"]["execute_generated_code"] is False
    assert reviewed["confirmation_gate"]["confirmation_payload_template"]["confirmed"] is True


def test_reference_template_plan_is_safe_executable_and_worker_digest_matches(
    tmp_path: Path,
) -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    image = tmp_path / "reference.png"
    Image.new("RGB", (48, 28), "white").save(image)
    inspected = inspect_reference(image, engine_home=RUNTIME)
    draft = _draft_reference_spec(inspected["reference"])
    reviewed = review_reference_figure(image, draft, engine_home=RUNTIME)
    semantics = understand_data(
        source,
        template_id="xrd",
        engine_home=RUNTIME,
    )

    plan = build_plan(
        source,
        template_id="xrd",
        claim="The supplied XRD patterns differ across the angular range.",
        evidence_role="comparison",
        semantic_confirmation=semantics["confirmation_gate"][
            "confirmation_payload_template"
        ],
        reference_image=image,
        reference_spec=draft,
        reference_confirmation=reviewed["confirmation_gate"][
            "confirmation_payload_template"
        ],
        reference_bindings={
            "intensity": "src:001",
            "theta": "src:000",
        },
        engine_home=RUNTIME,
    )

    assert plan["reference_adaptation"]["route"] == "template_adaptation"
    assert plan["reference_adaptation"]["safety_contract"][
        "reference_pixels_embedded"
    ] is False
    assert plan["can_render"] is True
    assert plan["blocked_reasons"] == []
    assert plan["reference_style"]["execution_allowed"] is True
    assert plan["reference_style"]["output_plan_digest"] == plan["template"][
        "plan_digest"
    ]
    assert plan["reference_style"]["safety"]["marker_points_sampled_or_removed"] == 0

    command, _env, _root = build_worker_command(plan, engine_home=RUNTIME)
    style_index = command.index("--reference-style-json")
    request = json.loads(command[style_index + 1])
    assert request["expected_report_hash"] == plan["reference_style"]["report_hash"]

    from origin_sciplot.scientific_workflow import (  # noqa: PLC0415
        ScientificColumnMapping,
        prepare_scientific,
    )
    from origin_sciplot.workers.run_template_worker import (  # noqa: PLC0415
        _apply_reference_style_request,
    )

    worker_mapping = plan["template"]["worker_mapping"]
    preparation = (
        prepare_scientific(
            source,
            "xrd",
            column_mapping=ScientificColumnMapping(
                assignments=tuple(worker_mapping["assignments"].items()),
                plot_mode=worker_mapping.get("plot_mode"),
            ),
        )
        if worker_mapping
        else prepare_scientific(source, "xrd")
    )
    worker_preparation, worker_report = _apply_reference_style_request(
        preparation,
        request,
    )
    assert worker_preparation.plan_digest == plan["template"]["plan_digest"]
    assert worker_report == plan["reference_style"]


def test_reference_confirmation_is_bound_to_the_exact_image(tmp_path: Path) -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    image = tmp_path / "reference.png"
    Image.new("RGB", (20, 20), "white").save(image)
    inspected = inspect_reference(image, engine_home=RUNTIME)
    draft = _draft_reference_spec(inspected["reference"])
    reviewed = review_reference_figure(image, draft, engine_home=RUNTIME)
    Image.new("RGB", (21, 20), "white").save(image)
    semantics = understand_data(source, template_id="xrd", engine_home=RUNTIME)

    with pytest.raises(EditaPlotError) as caught:
        build_plan(
            source,
            template_id="xrd",
            claim="The supplied XRD patterns differ.",
            evidence_role="comparison",
            semantic_confirmation=semantics["confirmation_gate"][
                "confirmation_payload_template"
            ],
            reference_image=image,
            reference_spec=draft,
            reference_confirmation=reviewed["confirmation_gate"][
                "confirmation_payload_template"
            ],
            reference_bindings={
                "intensity": "src:001",
                "theta": "src:000",
            },
            engine_home=RUNTIME,
        )

    assert caught.value.code == "reference_metadata_mismatch"


def test_controlled_composition_remains_experimental_and_blocked(
    tmp_path: Path,
) -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    image = tmp_path / "reference.png"
    Image.new("RGB", (36, 24), "white").save(image)
    inspected = inspect_reference(image, engine_home=RUNTIME)
    draft = _draft_reference_spec(inspected["reference"])
    reviewed = review_reference_figure(image, draft, engine_home=RUNTIME)
    semantics = understand_data(source, template_id="xrd", engine_home=RUNTIME)

    plan = build_plan(
        source,
        template_id="xrd",
        claim="The supplied XRD patterns differ.",
        evidence_role="comparison",
        semantic_confirmation=semantics["confirmation_gate"][
            "confirmation_payload_template"
        ],
        reference_image=image,
        reference_spec=draft,
        reference_confirmation=reviewed["confirmation_gate"][
            "confirmation_payload_template"
        ],
        reference_route="controlled_composition",
        reference_bindings={
            "intensity": "src:001",
            "theta": "src:000",
        },
        engine_home=RUNTIME,
    )

    assert plan["reference_adaptation"]["route"] == "controlled_composition"
    assert plan["reference_style"]["execution_allowed"] is False
    assert plan["can_render"] is False
    assert (
        "reference_controlled_composition_renderer_not_verified"
        in plan["blocked_reasons"]
    )
