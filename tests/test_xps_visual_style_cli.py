from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
RUNTIME = PRODUCT_ROOT / "runtime"
sys.path.insert(0, str(SCRIPTS))

import editaplot as editaplot_cli  # noqa: E402
from editaplot_core import (  # noqa: E402
    EditaPlotError,
    build_plan,
    build_worker_command,
    inspect_reference,
    review_reference_figure,
    understand_data,
    validate_plan,
)

XPS_SOURCE = RUNTIME / "templates" / "xps_adaptive" / "example_standard.csv"
XRD_SOURCE = RUNTIME / "templates" / "xrd" / "example_standard.csv"


def _canonical_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _rehash_plan(plan: dict[str, object]) -> None:
    payload = copy.deepcopy(plan)
    payload.pop("plan_hash", None)
    plan["plan_hash"] = _canonical_hash(payload)


def _semantic_confirmation(source: Path, template_id: str) -> dict[str, object]:
    understood = understand_data(
        source,
        template_id=template_id,
        engine_home=RUNTIME,
    )
    gate = understood["confirmation_gate"]
    assert gate["can_confirm_now"] is True
    return gate["confirmation_payload_template"]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _exact_style_request() -> dict[str, object]:
    # Deliberately use values that need canonicalization so the CLI/worker
    # boundary cannot accidentally preserve a second spelling of one contract.
    return {
        "palette_id": "deep_sea_gold",
        "series_colors": {"raw": "#123abc"},
        "line_width_pt": 2,
        "fill_transparency_percent": 37,
        "page_size_cm": [18, 18],
        "legend_visible": False,
        "legend_frame": False,
    }


def _plan_xps_via_cli(tmp_path: Path) -> dict[str, object]:
    style_path = tmp_path / "visual-style.json"
    confirmation_path = tmp_path / "semantic-confirmation.json"
    output_path = tmp_path / "render-plan.json"
    _write_json(style_path, _exact_style_request())
    _write_json(confirmation_path, _semantic_confirmation(XPS_SOURCE, "xps"))

    exit_code = editaplot_cli.main(
        [
            "plan",
            str(XPS_SOURCE),
            "--template-id",
            "xps",
            "--claim",
            "The fitted XPS components explain the measured envelope.",
            "--evidence-role",
            "fit decomposition",
            "--semantic-confirmation-json",
            str(confirmation_path),
            "--visual-style-json",
            str(style_path),
            "--output",
            str(output_path),
            "--engine-home",
            str(RUNTIME),
        ]
    )

    assert exit_code == 0
    assert output_path.is_file()
    return json.loads(output_path.read_text(encoding="utf-8"))


def _reference_spec(reference: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "reference": reference,
        "layout": {
            "archetype": "single_chart",
            "aspect_ratio_class": "square",
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
                "confidence": 0.98,
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
                "semantic_role": "raw_intensity",
                "data_binding": "raw_curve",
                "confidence": 0.98,
            }
        ],
        "style": {
            "palette_family": None,
            "palette_id": "navy_cyan_gold",
            "line_weight": "heavy",
            "marker_density": "adaptive",
            "fill_transparency": "heavy",
            "legend_position": "inside",
            "legend_frame": True,
            "grid": "none",
            "background": "white",
            "typography_hierarchy": "publication_informed",
        },
        "text_roles": [],
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


def _valid_exact_plan() -> dict[str, object]:
    return build_plan(
        XPS_SOURCE,
        template_id="xps",
        claim="The fitted XPS components explain the measured envelope.",
        evidence_role="fit decomposition",
        visual_style=_exact_style_request(),
        semantic_confirmation=_semantic_confirmation(XPS_SOURCE, "xps"),
        engine_home=RUNTIME,
    )


def test_visual_style_cli_freezes_canonical_report_and_final_digest(
    tmp_path: Path,
) -> None:
    plan = _plan_xps_via_cli(tmp_path)
    visual = plan["figure_contract"]["visual_style"]
    report = visual["report"]

    assert visual["tokens"] == report["requested_tokens"]
    assert visual["tokens"]["series_colors"] == {"raw": "#123ABC"}
    assert visual["tokens"]["page_size_cm"] == {"width": 18.0, "height": 18.0}
    assert report["input_plan_digest"] != report["output_plan_digest"]
    assert report["output_plan_digest"] == plan["template"]["plan_digest"]

    report_payload = dict(report)
    report_hash = report_payload.pop("report_hash")
    assert report_hash == _canonical_hash(report_payload)
    plan_payload = dict(plan)
    plan_hash = plan_payload.pop("plan_hash")
    assert plan_hash == _canonical_hash(plan_payload)
    validate_plan(plan)


def test_worker_command_passes_canonical_tokens_and_expected_report_hash(
    tmp_path: Path,
) -> None:
    plan = _plan_xps_via_cli(tmp_path)

    command, _env, _root = build_worker_command(plan, engine_home=RUNTIME)
    request_index = command.index("--visual-style-json")
    request = json.loads(command[request_index + 1])
    report = plan["figure_contract"]["visual_style"]["report"]

    assert request == {
        "tokens": report["requested_tokens"],
        "expected_report_hash": report["report_hash"],
    }
    assert command[command.index("--expected-plan-digest") + 1] == plan["template"][
        "plan_digest"
    ]


def test_exact_style_precedes_equivalent_reference_fields_and_chains_digests(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "reference.png"
    Image.new("RGB", (72, 72), "white").save(image_path)
    inspected = inspect_reference(image_path, engine_home=RUNTIME)
    draft = _reference_spec(inspected["reference"])
    reviewed = review_reference_figure(image_path, draft, engine_home=RUNTIME)
    exact = {
        "palette_id": "deep_sea_gold",
        "line_width_pt": 2.2,
        "fill_transparency_percent": 36.0,
        "page_size_cm": {"width": 18.0, "height": 18.0},
        "legend_visible": False,
        "legend_frame": False,
    }

    plan = build_plan(
        XPS_SOURCE,
        template_id="xps",
        claim="The fitted XPS components explain the measured envelope.",
        evidence_role="fit decomposition",
        visual_style=exact,
        semantic_confirmation=_semantic_confirmation(XPS_SOURCE, "xps"),
        reference_image=image_path,
        reference_spec=draft,
        reference_confirmation=reviewed["confirmation_gate"][
            "confirmation_payload_template"
        ],
        reference_bindings={"raw_curve": "source_001"},
        engine_home=RUNTIME,
    )

    explicit_report = plan["figure_contract"]["visual_style"]["report"]
    reference_report = plan["reference_style"]
    assert explicit_report["output_plan_digest"] == reference_report["input_plan_digest"]
    assert reference_report["output_plan_digest"] == plan["template"]["plan_digest"]
    assert reference_report["output_plan_digest"] == explicit_report["output_plan_digest"]

    rejected = {item["token"]: item for item in reference_report["rejected"]}
    for field in (
        "palette_id",
        "line_weight",
        "fill_transparency",
        "aspect_ratio_class",
        "legend_position",
        "legend_frame",
    ):
        assert rejected[field]["reason"] == "explicit_user_visual_setting_has_precedence"


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ("tokens", "xps_visual_style_report_mismatch"),
        ("report", "xps_visual_style_report_mismatch"),
        ("report_hash", "xps_visual_style_report_mismatch"),
        ("plan_digest", "xps_visual_style_report_mismatch"),
    ],
)
def test_internal_visual_style_tampering_is_rejected_before_origin(
    tamper: str,
    expected_code: str,
) -> None:
    plan = copy.deepcopy(_valid_exact_plan())
    visual = plan["figure_contract"]["visual_style"]
    report = visual["report"]

    if tamper == "tokens":
        visual["tokens"]["line_width_pt"] = 5.9
    elif tamper == "report":
        report["applied"][0]["reason"] = "tampered"
    elif tamper == "report_hash":
        report["report_hash"] = "0" * 64
    elif tamper == "plan_digest":
        plan["template"]["plan_digest"] = "f" * 64
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(tamper)
    _rehash_plan(plan)

    with pytest.raises(EditaPlotError) as caught:
        build_worker_command(plan, engine_home=RUNTIME)

    assert caught.value.code == expected_code


def test_outer_plan_hash_tampering_is_rejected_before_origin() -> None:
    plan = copy.deepcopy(_valid_exact_plan())
    plan["figure_contract"]["core_conclusion"] = "tampered claim"

    with pytest.raises(EditaPlotError) as caught:
        build_worker_command(plan, engine_home=RUNTIME)

    assert caught.value.code == "plan_hash_mismatch"


def test_legacy_palette_flag_conflict_with_visual_palette_is_clear(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    style_path = tmp_path / "visual-style.json"
    confirmation_path = tmp_path / "semantic-confirmation.json"
    output_path = tmp_path / "render-plan.json"
    _write_json(style_path, {"palette_id": "navy_cyan_gold"})
    _write_json(confirmation_path, _semantic_confirmation(XPS_SOURCE, "xps"))

    exit_code = editaplot_cli.main(
        [
            "plan",
            str(XPS_SOURCE),
            "--template-id",
            "xps",
            "--claim",
            "The fitted XPS components explain the measured envelope.",
            "--semantic-confirmation-json",
            str(confirmation_path),
            "--palette-id",
            "deep_sea_gold",
            "--visual-style-json",
            str(style_path),
            "--output",
            str(output_path),
            "--engine-home",
            str(RUNTIME),
        ]
    )

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert exit_code == 2
    assert error["error"]["code"] == "visual_style_conflict"
    assert "palette_id" in error["error"]["message"]
    assert "visual_style.palette_id" in error["error"]["message"]
    assert not output_path.exists()


def test_non_xps_template_rejects_exact_visual_style() -> None:
    with pytest.raises(EditaPlotError) as caught:
        build_plan(
            XRD_SOURCE,
            template_id="xrd",
            claim="The supplied diffraction profiles differ.",
            evidence_role="comparison",
            visual_style={"line_width_pt": 2.2},
            semantic_confirmation=_semantic_confirmation(XRD_SOURCE, "xrd"),
            engine_home=RUNTIME,
        )

    assert caught.value.code == "visual_style_template_unsupported"
    assert "Exact visual_style fields are currently implemented for XPS only" in str(
        caught.value
    )
