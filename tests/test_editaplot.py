from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PRODUCT_ROOT / "skill" / "editaplot"
SCRIPTS = SKILL_ROOT / "scripts"
RUNTIME = PRODUCT_ROOT / "runtime"
ENGINE = Path(os.environ.get("EDITAPLOT_TEST_ENGINE_HOME", RUNTIME)).resolve()
EXAMPLES = PRODUCT_ROOT / "examples"
LOCAL_SHOWCASE = PRODUCT_ROOT / "showcase"
requires_local_showcase = pytest.mark.skipif(
    not (LOCAL_SHOWCASE / "visual-qa.json").is_file(),
    reason="full local Origin showcase evidence is intentionally excluded from the public repository",
)

sys.path.insert(0, str(SCRIPTS))

import bootstrap_editaplot as bootstrap  # noqa: E402
import editaplot as editaplot_cli  # noqa: E402
import editaplot_core as core  # noqa: E402
from editaplot_core import (  # noqa: E402
    RUNTIME_DEPENDENCIES,
    EditaPlotError,
    build_medical_panel_plan,
    build_plan,
    build_worker_command,
    discover_origin_application,
    doctor,
    inspect_data,
    managed_environment_status,
    palette_catalog,
    python_compatibility,
    recommend_charts,
    repair_environment,
    start_session,
    validate_plan,
    verify_output,
    windows_host_compatibility,
)

pytestmark = pytest.mark.skipif(not ENGINE.is_dir(), reason="EditaPlot runtime is unavailable")

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.parametrize(
    ("relative_path", "intent", "expected"),
    [
        ("templates/xps_c1s_fit/example_standard.csv", "XPS peak fitting", "xps"),
        ("templates/xrd/example_standard.csv", "XRD diffraction", "xrd"),
        ("templates/bar/example_multi_group.csv", "compare groups with bars", "bar"),
        ("templates/sankey/example_standard.csv", "Sankey flow", "sankey"),
        ("templates/scatter/example_dense.csv", "scatter relationship", "scatter"),
        ("templates/line_error/example_chinese.csv", "trend with error bars", "line_error"),
        ("templates/trend/example_standard.csv", "multi-series progression trendline", "trend"),
        ("templates/radar/example_standard.csv", "radar multimetric comparison", "radar"),
        ("templates/heatmap/example_standard.csv", "annotated results heatmap matrix", "heatmap"),
        ("templates/raw_summary/example_standard.csv", "raw observations dot summary", "raw_summary"),
        ("templates/violin/example_standard.csv", "violin distribution density", "violin"),
        ("templates/histogram/example_standard.csv", "histogram frequency distribution", "histogram"),
        ("templates/forest/example_standard.csv", "forest effect confidence interval", "forest"),
        ("templates/bubble/example_standard.csv", "bubble indexed size relationship", "bubble"),
        (
            "templates/diagnostic_curve/example_standard.csv",
            "medical imaging ROC diagnostic curve",
            "diagnostic_curve",
        ),
        (
            "templates/confusion_matrix/example_standard.csv",
            "medical classification confusion matrix",
            "confusion_matrix",
        ),
        (
            "templates/bland_altman/example_standard.csv",
            "Bland Altman medical measurement agreement",
            "bland_altman",
        ),
        (
            "templates/paired_trajectory/example_standard.csv",
            "paired longitudinal medical trajectory",
            "paired_trajectory",
        ),
        (
            "templates/calibration_curve/example_standard.csv",
            "medical model calibration curve reliability",
            "calibration_curve",
        ),
        (
            "templates/decision_curve/example_standard.csv",
            "medical decision curve DCA net benefit",
            "decision_curve",
        ),
        (
            "templates/raincloud/example_standard.csv",
            "medical imaging Raincloud raw distribution",
            "raincloud",
        ),
        (
            "templates/shap_summary/example_standard.csv",
            "medical imaging precomputed SHAP summary feature contribution",
            "shap_summary",
        ),
        (
            "templates/grouped_box/example_standard.csv",
            "medical grouped boxplot with raw observations",
            "grouped_box",
        ),
        ("templates/pl/example_standard.csv", "TRPL photoluminescence decay with user supplied fits", "pl"),
        ("templates/uv_vis/example_standard.csv", "UV-vis absorbance with supplied Tauc inset", "uv_vis"),
        (
            "templates/trajectory3d/example_standard.csv",
            "3D Nyquist multi-condition trajectory",
            "trajectory3d",
        ),
    ],
)
def test_recommendation_routes_verified_examples(relative_path: str, intent: str, expected: str) -> None:
    result = recommend_charts(ENGINE / relative_path, intent=intent, engine_home=ENGINE)

    assert result["candidates"][0]["template_id"] == expected
    assert result["candidates"][0]["support_level"] == "verified"
    assert result["auto_selection"]["allowed"] is True


def test_ambiguous_numeric_xy_does_not_auto_select() -> None:
    result = recommend_charts(EXAMPLES / "ambiguous_xy.csv", engine_home=ENGINE)

    assert result["candidates"][0]["template_id"] == "scatter"
    assert result["auto_selection"]["allowed"] is False
    assert "top_score_below_threshold" in result["auto_selection"]["gate_reasons"]


def test_recommend_limit_one_still_uses_full_runner_up_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core.bootstrap_engine(ENGINE)
    from origin_sciplot import template_service

    prepared = types.SimpleNamespace(
        confidence=0.95,
        requires_confirmation=False,
        renderer_template_id="renderer",
        summary=types.SimpleNamespace(heading="candidate", warnings=()),
    )

    class FakeService:
        def __init__(self, template_id: str) -> None:
            self.manifest = types.SimpleNamespace(id=template_id, name=template_id)

        def prepare(self, _path: object) -> object:
            return prepared

    monkeypatch.setattr(
        template_service.TemplateServiceRegistry,
        "implemented",
        lambda _self: [FakeService("bar"), FakeService("scatter")],
    )
    monkeypatch.setattr(
        core,
        "inspect_data",
        lambda *_args, **_kwargs: {
            "source": {"sha256": "0" * 64},
            "table": {"layouts": [], "row_count": 2, "column_count": 2},
            "domain_signals": [],
        },
    )
    monkeypatch.setattr(core, "bootstrap_engine", lambda _value=None: ENGINE)
    monkeypatch.setattr(
        core,
        "_score_candidate",
        lambda template_id, *_args: (
            (0.90 if template_id == "bar" else 0.85),
            [],
            [],
        ),
    )

    result = recommend_charts("ignored.csv", engine_home=ENGINE, limit=1)

    assert len(result["candidates"]) == 1
    assert result["auto_selection"]["top_score"] == 0.9
    assert result["auto_selection"]["margin"] == 0.05
    assert result["auto_selection"]["allowed"] is False
    assert "candidate_margin_too_small" in result["auto_selection"]["gate_reasons"]


def test_beginner_start_high_confidence_is_read_only_and_still_asks_scientific_purpose() -> None:
    source = ENGINE / "templates" / "xrd" / "example_standard.csv"
    before = source.read_bytes()

    result = start_session(
        source,
        intent="XRD diffraction pattern",
        engine_home=ENGINE,
    )

    assert result["session_type"] == "beginner_start"
    assert result["state"] == "awaiting_scientific_confirmation"
    assert result["source"]["bytes_unchanged"] is True
    assert result["source"]["sha256"] == hashlib.sha256(before).hexdigest()
    assert result["source"]["row_count"] > 0
    assert result["source"]["column_count"] == len(result["column_roles"])
    assert "bandgap" not in result["column_roles"][0]["semantic_roles"]
    assert result["recommendation"]["top_candidate"]["template_id"] == "xrd"
    assert result["recommendation"]["auto_selection_gate"]["allowed"] is True
    assert result["requires_scientific_confirmation"] is True
    assert "scientific_purpose" in {
        question["id"] for question in result["confirmation_questions"]
    }
    assert result["execution"] == {
        "plan_created": False,
        "render_started": False,
        "origin_called": False,
    }
    origin_default = result["safe_defaults"]["origin"]
    assert "Automation" in origin_default
    assert not any(token in origin_default for token in ("官方", "合法", "授权", "激活", "手动启动"))
    assert source.read_bytes() == before


def test_beginner_start_ambiguous_xy_asks_for_template_and_column_meanings() -> None:
    result = start_session(EXAMPLES / "ambiguous_xy.csv", engine_home=ENGINE)

    question_ids = {question["id"] for question in result["confirmation_questions"]}
    assert result["recommendation"]["auto_selection_gate"]["allowed"] is False
    assert result["recommendation"]["top_candidate"]["template_id"] == "scatter"
    assert {"scientific_purpose", "template_choice", "column_meanings"}.issubset(question_ids)
    assert result["next_step"]["action"] == "collect_scientific_confirmations"


def test_beginner_start_explicitly_asks_whether_error_is_sd_se_or_sem() -> None:
    source = ENGINE / "templates" / "line_error" / "example_chinese.csv"

    result = start_session(
        source,
        intent="带误差棒的趋势图",
        engine_home=ENGINE,
    )

    error_question = next(
        question for question in result["confirmation_questions"] if question["id"] == "error_semantics"
    )
    assert all(token in error_question["question_zh"] for token in ("SD", "SE", "SEM"))
    assert result["safe_defaults"]["analysis_boundary"].startswith("不推断统计检验")


@pytest.mark.parametrize(
    ("template_id", "header", "expects_notice"),
    [
        ("xps", "Binding Energy,Counts\n285,100\n284,110\n", False),
        ("xps", "Binding Energy,Counts,Background\n285,100,90\n284,110,92\n", True),
        ("pl", "Wavelength,PL intensity\n500,10\n510,12\n", False),
        ("pl", "Time,PL intensity\n0,1\n1,0.8\n", False),
        ("pl", "Time,PL intensity,Fit\n0,1,1\n1,0.8,0.79\n", True),
        ("uv_vis", "Wavelength,Absorbance\n300,0.8\n400,0.2\n", False),
        ("uv_vis", "Wavelength,Absorbance,Tauc value\n300,0.8,0.1\n400,0.2,0.5\n", True),
    ],
)
def test_beginner_start_only_requires_precomputed_results_when_semantics_are_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    template_id: str,
    header: str,
    expects_notice: bool,
) -> None:
    source = tmp_path / f"{template_id}.csv"
    source.write_text(header, encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def fake_recommend(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "source": {"sha256": digest},
            "candidates": [
                {
                    "template_id": template_id,
                    "template_name": template_id,
                    "score": 0.95,
                    "requires_column_confirmation": False,
                    "reasons": ["test candidate"],
                    "warnings": [],
                }
            ],
            "auto_selection": {
                "allowed": True,
                "selected_template_id": template_id,
                "top_score": 0.95,
                "margin": 0.5,
                "required_score": core.AUTO_SCORE_THRESHOLD,
                "required_margin": core.AUTO_MARGIN_THRESHOLD,
                "gate_reasons": [],
            },
        }

    monkeypatch.setattr(core, "recommend_charts", fake_recommend)

    result = start_session(source, engine_home=ENGINE)

    assert (result["professional_precomputed_notice"] is not None) is expects_notice
    question_ids = {question["id"] for question in result["confirmation_questions"]}
    assert ("precomputed_evidence" in question_ids) is expects_notice


def test_beginner_start_rejects_inconsistent_hashes_between_read_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = EXAMPLES / "ambiguous_xy.csv"
    original = core.recommend_charts

    def mismatched_recommend(*args: object, **kwargs: object) -> dict[str, object]:
        result = original(*args, **kwargs)
        result["source"] = {**result["source"], "sha256": "0" * 64}
        return result

    monkeypatch.setattr(core, "recommend_charts", mismatched_recommend)

    with pytest.raises(EditaPlotError) as raised:
        start_session(source, engine_home=ENGINE)

    assert raised.value.code == "source_changed_during_start"
    assert set(raised.value.details["observed_hashes"]) == {
        "before",
        "inspection",
        "recommendation",
        "after",
    }


def test_beginner_start_cli_emits_json_without_creating_a_plan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = ENGINE / "templates" / "xrd" / "example_standard.csv"

    returncode = editaplot_cli.main(
        ["start", str(source), "--intent", "XRD diffraction", "--engine-home", str(ENGINE)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload["ok"] is True
    assert payload["execution"]["plan_created"] is False
    assert payload["execution"]["render_started"] is False


def test_bootstrap_normalizes_a_dropped_supported_table_to_start(tmp_path: Path) -> None:
    source = tmp_path / "teaching data.csv"
    source.write_text("X,Y\n1,2\n", encoding="utf-8")

    normalized = bootstrap._normalize_cli_arguments(
        [str(source), "--intent", "scatter relationship", "--limit", "2"]
    )

    assert normalized == [
        "start",
        str(source),
        "--intent",
        "scatter relationship",
        "--limit",
        "2",
    ]
    assert bootstrap._normalize_cli_arguments(["inspect", str(source)]) == ["inspect", str(source)]


@pytest.mark.parametrize("command", ["inspect", "start", "recommend", "plan"])
def test_data_commands_refuse_to_replace_the_source_file(
    command: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "immutable.csv"
    source.write_bytes((EXAMPLES / "ambiguous_xy.csv").read_bytes())
    before = source.read_bytes()
    arguments = [command, str(source)]
    if command == "plan":
        arguments.extend(
            [
                "--template-id",
                "scatter",
                "--claim",
                "X and Y are related in this teaching dataset.",
                "--output",
                str(source),
            ]
        )
    else:
        arguments.extend(["--output", str(source)])

    returncode = editaplot_cli.main(arguments)
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "source_output_conflict"
    assert source.read_bytes() == before


def test_panel_plan_refuses_to_replace_its_config_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "medical-panels.json"
    config.write_text('{"panels": []}\n', encoding="utf-8")
    before = config.read_bytes()

    returncode = editaplot_cli.main(
        [
            "panel-plan",
            str(config),
            "--claim",
            "Teaching claim",
            "--output",
            str(config),
        ]
    )
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "source_output_conflict"
    assert config.read_bytes() == before


def test_plan_refuses_to_replace_its_mapping_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.csv"
    source.write_bytes((EXAMPLES / "ambiguous_xy.csv").read_bytes())
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"assignments": {}}\n', encoding="utf-8")
    before = mapping.read_bytes()

    returncode = editaplot_cli.main(
        [
            "plan",
            str(source),
            "--template-id",
            "scatter",
            "--claim",
            "X and Y are related in this teaching dataset.",
            "--mapping-json",
            str(mapping),
            "--output",
            str(mapping),
        ]
    )
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "source_output_conflict"
    assert mapping.read_bytes() == before


def test_trajectory3d_recommendation_requires_explicit_three_axis_evidence(
    tmp_path: Path,
) -> None:
    ambiguous = tmp_path / "trajectory3d_ambiguous.csv"
    ambiguous.write_text(
        "Zreal (Ohm),Exposure Dose (mg/kg),-Zimag (Ohm),Series\n"
        "0.4,5,0.0,A\n1.0,5,0.7,A\n1.8,10,0.0,B\n2.4,10,0.9,B\n",
        encoding="utf-8",
    )
    result = recommend_charts(
        ambiguous,
        intent="3D Nyquist trajectory",
        engine_home=ENGINE,
    )
    candidate = next(item for item in result["candidates"] if item["template_id"] == "trajectory3d")
    assert candidate["requires_column_confirmation"] is True
    assert result["auto_selection"]["allowed"] is False

    no_unit = tmp_path / "trajectory3d_no_unit.csv"
    no_unit.write_text(
        "Zreal (Ohm),Temperature,-Zimag (Ohm),Series\n0.4,300,0.0,A\n1.0,300,0.7,A\n",
        encoding="utf-8",
    )
    rejected = recommend_charts(
        no_unit,
        intent="3D Nyquist trajectory",
        engine_home=ENGINE,
    )
    assert all(item["template_id"] != "trajectory3d" for item in rejected["candidates"])


def test_inspection_is_read_only_and_reports_layout() -> None:
    source = EXAMPLES / "sankey_zh.csv"
    before = source.read_bytes()

    result = inspect_data(source, engine_home=ENGINE)

    assert result["source"]["sha256"]
    assert "edge_list" in result["table"]["layouts"]
    assert result["domain_signals"]["sankey"] == 3
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    ("relative_path", "layout"),
    [
        ("templates/histogram/example_standard.csv", "numeric_univariate"),
        ("templates/forest/example_standard.csv", "interval_table"),
        ("templates/bubble/example_standard.csv", "indexed_size"),
        ("templates/diagnostic_curve/example_standard.csv", "diagnostic_coordinates"),
        ("templates/confusion_matrix/example_standard.csv", "confusion_matrix"),
        ("templates/bland_altman/example_standard.csv", "bland_altman_limits"),
        ("templates/paired_trajectory/example_standard.csv", "paired_wide"),
        ("templates/calibration_curve/example_standard.csv", "calibration_bins"),
        ("templates/decision_curve/example_standard.csv", "decision_net_benefit"),
        ("templates/shap_summary/example_standard.csv", "shap_long"),
        ("templates/grouped_box/example_standard.csv", "grouped_box_wide"),
        ("templates/pl/example_standard.csv", "trpl_wide"),
        ("templates/uv_vis/example_standard.csv", "uv_vis_wide"),
        ("templates/trajectory3d/example_standard.csv", "trajectory3d_long"),
    ],
)
def test_inspection_reports_new_evidence_layouts(relative_path: str, layout: str) -> None:
    result = inspect_data(ENGINE / relative_path, engine_home=ENGINE)

    assert layout in result["table"]["layouts"]


def test_plan_is_hash_bound_and_builds_safe_worker_command() -> None:
    source = ENGINE / "templates" / "xrd" / "example_standard.csv"
    plan = build_plan(
        source,
        template_id="xrd",
        claim="The teaching patterns differ across the measured angle range.",
        evidence_role="comparison",
        intent="XRD diffraction",
        engine_home=ENGINE,
    )

    validate_plan(plan)
    command, env, root = build_worker_command(plan, engine_home=ENGINE)

    assert plan["can_render"] is True
    assert plan["execution"]["origin_callability_check"] == "performed_by_render_worker"
    assert "requires_manual_origin_start_confirmation" not in plan["execution"]
    assert command[:3] == [sys.executable, "-m", "origin_sciplot.workers.run_template_worker"]
    assert "--expected-plan-digest" in command
    assert "--keep-origin-open" in command
    assert root == ENGINE.resolve()
    assert str(ENGINE / "src") in env["PYTHONPATH"]


def test_changed_source_blocks_plan(tmp_path: Path) -> None:
    source = tmp_path / "changed.csv"
    shutil.copy2(EXAMPLES / "ambiguous_xy.csv", source)
    plan = build_plan(
        source,
        template_id="scatter",
        claim="Y increases with X in the teaching observations.",
        evidence_role="relationship",
        engine_home=ENGINE,
    )
    source.write_text(source.read_text(encoding="utf-8") + "10,11\n", encoding="utf-8")

    with pytest.raises(EditaPlotError, match="source file changed") as error:
        validate_plan(plan)

    assert error.value.code == "source_changed"


def test_previous_render_plan_schema_is_rejected() -> None:
    plan = build_plan(
        ENGINE / "templates" / "xrd" / "example_standard.csv",
        template_id="xrd",
        claim="The teaching patterns differ across the measured angle range.",
        evidence_role="comparison",
        engine_home=ENGINE,
    )
    plan["plan_version"] = "1.0"

    with pytest.raises(EditaPlotError) as raised:
        validate_plan(plan)

    assert raised.value.code == "plan_version_unsupported"


def test_render_reaches_plan_validation_without_origin_confirmation_flag(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "editaplot.py"), "render", str(plan_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = json.loads(completed.stderr)
    assert completed.returncode == 2
    assert payload["error"]["code"] == "plan_version_unsupported"


def test_render_help_has_no_legacy_origin_confirmation_option() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / "editaplot.py"), "render", "--help"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert "--confirm-origin-started" not in completed.stdout


def test_verify_refuses_incomplete_output(tmp_path: Path) -> None:
    (tmp_path / "result.png").write_bytes(b"png")

    result = verify_output(tmp_path)

    assert result["programmatic_pass"] is False
    assert result["human_visual_qa"]["status"] == "pending"


@pytest.mark.parametrize(
    "artifact_name",
    [
        "result.png",
        "result.pdf",
        "result.tif",
        "result.opju",
        "origin_verify_report.json",
        "validation_report.json",
    ],
)
def test_verify_json_output_cannot_replace_required_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    artifact_name: str,
) -> None:
    artifact = tmp_path / artifact_name
    before = f"immutable-{artifact_name}".encode()
    artifact.write_bytes(before)

    returncode = editaplot_cli.main(
        ["verify", str(tmp_path), "--output", str(artifact)]
    )
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "verification_artifact_output_conflict"
    assert artifact.read_bytes() == before


def _write_medical_panel_config(
    tmp_path: Path,
    panels: list[dict[str, object]],
    **options: object,
) -> Path:
    path = tmp_path / "medical-panels.json"
    payload: dict[str, object] = {"panels": panels, **options}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@requires_local_showcase
def test_medical_panel_plan_accepts_verified_origin_and_attested_image(tmp_path: Path) -> None:
    image = tmp_path / "deidentified-mri.png"
    image.write_bytes(ONE_PIXEL_PNG)
    config = _write_medical_panel_config(
        tmp_path,
        [
            {
                "kind": "quantitative",
                "title": "Internal and external ROC",
                "evidence_role": "diagnostic discrimination",
                "source": str(PRODUCT_ROOT / "showcase" / "gallery" / "medical-roc" / "origin-output"),
                "human_visual_qa": "pass",
            },
            {
                "kind": "image",
                "title": "Representative lesion",
                "evidence_role": "qualitative localization",
                "source": str(image),
                "deidentified": True,
                "burned_in_text_checked": True,
                "modality": "MRI",
                "plane": "axial",
                "display_parameters": "user-supplied T2-weighted display",
            },
        ],
    )

    plan = build_medical_panel_plan(
        config,
        claim="The model separates the cohorts and localizes the representative lesion.",
    )

    assert plan["can_compose"] is True
    assert [panel["label"] for panel in plan["panels"]] == ["A", "B"]
    assert plan["layout"]["profile"] == "grid-1x2"
    assert plan["deidentification_gate"]["all_image_attestations_pass"] is True
    assert plan["composition_backend"]["merged_origin_opju_claimed"] is False
    assert plan["plan_hash"]


@requires_local_showcase
def test_medical_panel_plan_blocks_unattested_image(tmp_path: Path) -> None:
    image = tmp_path / "unchecked.png"
    image.write_bytes(ONE_PIXEL_PNG)
    config = _write_medical_panel_config(
        tmp_path,
        [
            {
                "kind": "quantitative",
                "title": "ROC",
                "evidence_role": "diagnostic discrimination",
                "source": str(PRODUCT_ROOT / "showcase" / "gallery" / "medical-roc" / "origin-output"),
                "human_visual_qa": "pass",
            },
            {
                "kind": "image",
                "title": "Unchecked image",
                "evidence_role": "qualitative localization",
                "source": str(image),
                "deidentified": False,
                "burned_in_text_checked": False,
                "modality": "CT",
                "plane": "axial",
                "display_parameters": "user-supplied window",
            },
        ],
    )

    plan = build_medical_panel_plan(config, claim="Teaching claim")

    assert plan["can_compose"] is False
    assert "panel_2_deidentification_attestation_required" in plan["blocked_reasons"]
    assert "panel_2_burned_in_text_check_required" in plan["blocked_reasons"]


@requires_local_showcase
def test_medical_panel_plan_freezes_cross_panel_semantics(tmp_path: Path) -> None:
    roc_output = PRODUCT_ROOT / "showcase" / "gallery" / "medical-roc" / "origin-output"
    calibration_output = PRODUCT_ROOT / "showcase" / "gallery" / "medical-calibration" / "origin-output"
    config = _write_medical_panel_config(
        tmp_path,
        [
            {
                "kind": "quantitative",
                "title": "ROC",
                "evidence_role": "model performance",
                "source": str(roc_output),
                "human_visual_qa": "pass",
            },
            {
                "kind": "quantitative",
                "title": "Calibration",
                "evidence_role": "model performance",
                "source": str(calibration_output),
                "human_visual_qa": "pass",
            },
        ],
    )

    plan = build_medical_panel_plan(config, claim="The models are discriminative and calibrated.")

    assert plan["can_compose"] is False
    assert "each_panel_needs_unique_evidence_role" in plan["blocked_reasons"]
    assert "condition_color_map_required_for_multiple_quantitative_panels" in plan["blocked_reasons"]

    valid_config = _write_medical_panel_config(
        tmp_path,
        [
            {
                "kind": "quantitative",
                "title": "ROC",
                "evidence_role": "diagnostic discrimination",
                "source": str(roc_output),
                "human_visual_qa": "pass",
            },
            {
                "kind": "quantitative",
                "title": "Calibration",
                "evidence_role": "probability reliability",
                "source": str(calibration_output),
                "human_visual_qa": "pass",
            },
        ],
        condition_color_map={"Internal model": "#2F6B9A", "External model": "#73A6C6"},
    )

    valid_plan = build_medical_panel_plan(
        valid_config,
        claim="The models are discriminative and calibrated.",
    )

    assert valid_plan["can_compose"] is True
    assert valid_plan["semantic_contract"]["each_panel_has_unique_evidence_role"] is True
    assert valid_plan["semantic_contract"]["condition_color_map"]["Internal model"] == "#2F6B9A"


def test_doctor_reports_supported_runtime() -> None:
    result = doctor(engine_home=ENGINE)

    assert result["ready_for_analysis"] is True
    assert result["origin_callability_check"] == "performed_during_render"
    assert "manual_origin_launch_confirmation" not in result
    assert result["automatic_repair"]["scope"] == "project_local_python_dependencies_only"
    assert result["automatic_repair"]["origin_installation_modified"] is False


def test_origin_connection_failure_is_reported_as_neutral_technical_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_src = RUNTIME / "src"
    monkeypatch.syspath_prepend(str(runtime_src))
    from origin_sciplot.origin_backend.safe_errors import OriginEnvironmentError
    from origin_sciplot.origin_backend.session import OriginSession

    def fail_connection(_show: bool) -> None:
        raise RuntimeError("private local Origin environment details must not escape")

    fake_originpro = types.SimpleNamespace(
        oext=True,
        set_show=fail_connection,
        new=lambda **_kwargs: None,
        lt_float=lambda _name: 10.15,
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession().__enter__()

    assert str(raised.value) == "Origin Automation connection failed"
    assert "private local" not in str(raised.value)


def test_origin_connection_failure_restores_application_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_src = RUNTIME / "src"
    monkeypatch.syspath_prepend(str(runtime_src))
    from origin_sciplot.origin_backend.safe_errors import OriginEnvironmentError
    from origin_sciplot.origin_backend.session import OriginSession

    visibility: list[bool] = []

    def record_visibility(show: bool) -> None:
        visibility.append(show)

    def fail_new(**_kwargs: object) -> None:
        raise RuntimeError("private local details")

    fake_originpro = types.SimpleNamespace(
        oext=True,
        set_show=record_visibility,
        new=fail_new,
        lt_float=lambda _name: 10.15,
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError, match="Origin Automation connection failed"):
        OriginSession().__enter__()

    assert visibility == [False, True]


@pytest.mark.parametrize("minor", [10, 11, 12])
def test_python_compatibility_accepts_only_verified_cpython_minors(minor: int) -> None:
    result = python_compatibility(
        version=(3, minor, 7),
        implementation="CPython",
        architecture_bits=64,
    )

    assert result["compatible"] is True
    assert result["required"] == "64-bit CPython >=3.10,<3.13"


@pytest.mark.parametrize(
    ("version", "implementation", "bits", "reason"),
    [
        ((3, 9, 18), "CPython", 64, "python_too_old"),
        ((3, 13, 1), "CPython", 64, "python_not_yet_verified"),
        ((3, 12, 7), "PyPy", 64, "cpython_required"),
        ((3, 12, 7), "CPython", 32, "64_bit_python_required"),
    ],
)
def test_python_compatibility_rejects_unverified_runtimes(
    version: tuple[int, int, int],
    implementation: str,
    bits: int,
    reason: str,
) -> None:
    result = python_compatibility(
        version=version,
        implementation=implementation,
        architecture_bits=bits,
    )

    assert result["compatible"] is False
    assert reason in result["reasons"]


@pytest.mark.parametrize(
    ("system", "machine", "windows_major", "reason"),
    [
        ("Darwin", "x86_64", None, "windows_required"),
        ("Windows", "ARM64", 11, "windows_x64_amd64_required"),
        ("Windows", "AMD64", 6, "windows_10_or_newer_required"),
    ],
)
def test_windows_host_gate_rejects_unsupported_hosts(
    system: str,
    machine: str,
    windows_major: int | None,
    reason: str,
) -> None:
    host = windows_host_compatibility(
        system=system,
        machine=machine,
        windows_major=windows_major,
    )
    runtime = python_compatibility(
        version=(3, 12, 7),
        implementation="CPython",
        architecture_bits=64,
        system=system,
        machine=machine,
        windows_major=windows_major,
    )

    assert host["compatible"] is False
    assert runtime["compatible"] is False
    assert reason in host["reasons"]
    assert reason in runtime["reasons"]


def test_windows_host_gate_accepts_windows_10_amd64() -> None:
    result = windows_host_compatibility(
        system="Windows",
        machine="AMD64",
        windows_major=10,
    )

    assert result["compatible"] is True
    assert result["virtual_machine_detection_performed"] is False


def test_bootstrap_prefers_explicit_compatible_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITAPLOT_PYTHON", "explicit-python.exe")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")

    def fake_probe(command: list[str], *, source: str, detail: str) -> dict[str, object]:
        return {
            "source": source,
            "detail": detail,
            "usable": True,
            "compatible": True,
            "executable": command[0],
            "version": "3.11.9",
            "version_info": [3, 11, 9],
            "implementation": "CPython",
            "architecture_bits": 64,
            "reasons": [],
        }

    monkeypatch.setattr(bootstrap, "_probe", fake_probe)
    result = bootstrap.discover_python(None)

    assert result["selected"]["source"] == "EDITAPLOT_PYTHON"
    assert len(result["attempts"]) == 1


def test_bootstrap_rejects_explicit_python_313_and_falls_back_to_py(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDITAPLOT_PYTHON", "python-3.13.exe")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "py.exe")
    monkeypatch.setattr(bootstrap, "_candidate_paths_from_standard_locations", lambda: [])

    def fake_probe(command: list[str], *, source: str, detail: str) -> dict[str, object]:
        if source == "EDITAPLOT_PYTHON":
            return {
                "source": source,
                "detail": detail,
                "usable": True,
                "compatible": False,
                "executable": command[0],
                "version": "3.13.1",
                "version_info": [3, 13, 1],
                "reasons": ["python_not_yet_verified"],
            }
        minor = int(command[1].split(".")[1])
        compatible = minor == 12
        return {
            "source": source,
            "detail": detail,
            "usable": compatible,
            "compatible": compatible,
            "executable": f"python-3.{minor}.exe",
            "version": f"3.{minor}.0",
            "version_info": [3, minor, 0],
            "reasons": [] if compatible else ["probe_failed"],
        }

    monkeypatch.setattr(bootstrap, "_probe", fake_probe)
    result = bootstrap.discover_python(None)

    assert result["selected"]["source"] == "windows_py_launcher"
    assert result["selected"]["version"] == "3.12.0"
    assert any(
        attempt.get("source") == "EDITAPLOT_PYTHON" and not attempt.get("compatible")
        for attempt in result["attempts"]
    )


def test_bootstrap_selects_highest_general_python_across_discovery_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EDITAPLOT_PYTHON", raising=False)
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        bootstrap.shutil,
        "which",
        lambda name: "py.exe" if name in {"py.exe", "py"} else None,
    )
    standard_python = tmp_path / "Python312" / "python.exe"
    standard_python.parent.mkdir()
    standard_python.touch()
    monkeypatch.setattr(
        bootstrap,
        "_candidate_paths_from_standard_locations",
        lambda: [standard_python],
    )

    def fake_probe(command: list[str], *, source: str, detail: str) -> dict[str, object]:
        if source == "windows_py_launcher":
            minor = int(command[1].split(".")[1])
            if minor != 10:
                return {
                    "source": source,
                    "detail": detail,
                    "usable": False,
                    "compatible": False,
                    "reason": "probe_failed",
                }
            executable = "python-3.10.exe"
        else:
            minor = 12
            executable = str(standard_python)
        return {
            "source": source,
            "detail": detail,
            "usable": True,
            "compatible": True,
            "executable": executable,
            "version": f"3.{minor}.9",
            "version_info": [3, minor, 9],
            "implementation": "CPython",
            "architecture_bits": 64,
            "reasons": [],
        }

    monkeypatch.setattr(bootstrap, "_probe", fake_probe)

    result = bootstrap.discover_python(None)

    assert result["selected"]["source"] == "standard_windows_installations"
    assert result["selected"]["version"] == "3.12.9"
    assert {attempt["source"] for attempt in result["attempts"]} >= {
        "windows_py_launcher",
        "standard_windows_installations",
    }


def test_managed_environment_requires_a_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")
    python = tmp_path / ".editaplot-venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()

    result = managed_environment_status(tmp_path)

    assert result["valid"] is False
    assert result["reason"] == "managed_fingerprint_missing"


@pytest.mark.parametrize("failure", [OSError("missing"), subprocess.TimeoutExpired("probe", 30)])
def test_managed_dependency_probe_failures_are_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    monkeypatch.setattr(core.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))

    result = core._verify_managed_dependencies(tmp_path / "python.exe")

    assert result["ok"] is False
    assert result["reason"].startswith("dependency_probe_")


def test_origin_discovery_uses_registered_clsid_and_existing_origin64(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "Origin64.exe"
    executable.touch()
    clsid = "{00000000-0000-0000-0000-000000000001}"

    class FakeKey:
        def __init__(self, subkey: str, view: int) -> None:
            self.subkey = subkey
            self.view = view

        def __enter__(self) -> FakeKey:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    fake_winreg = types.SimpleNamespace(
        HKEY_CLASSES_ROOT=object(),
        KEY_READ=1,
        KEY_WOW64_32KEY=2,
        KEY_WOW64_64KEY=4,
    )

    def open_key(_root: object, subkey: str, _reserved: int, access: int) -> FakeKey:
        return FakeKey(subkey, access)

    def query_value(key: FakeKey, _name: object) -> tuple[str, int]:
        if key.subkey == r"Origin.ApplicationSI\CLSID":
            return clsid, 1
        if key.subkey == rf"CLSID\{clsid}\LocalServer32" and key.view & 2:
            return f'"{executable}" /Automation', 1
        raise FileNotFoundError(key.subkey)

    fake_winreg.OpenKey = open_key
    fake_winreg.QueryValueEx = query_value
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")

    result = discover_origin_application()

    assert result["application_present"] is True
    assert Path(result["path"]) == executable.resolve()
    assert result["callability_status"] == "ready_to_attempt"
    assert "license_confirmed" not in result
    assert "manual_startup_confirmation" not in result


def test_doctor_render_gate_requires_registered_origin_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {
        {"yaml": "PyYAML", "PIL": "pillow"}.get(module, module): spec.partition("==")[2]
        for module, spec in RUNTIME_DEPENDENCIES
    }
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")
    monkeypatch.setattr(core.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(core.importlib_metadata, "version", lambda name: versions[name])
    monkeypatch.setattr(
        core,
        "discover_origin_application",
        lambda: {
            "application_present": False,
            "path": None,
            "callability_status": "not_detected",
        },
    )

    result = doctor(engine_home=ENGINE)

    assert result["ready_for_analysis"] is True
    assert result["ready_for_render"] is False
    assert "origin_automation_application_not_detected" in result["manual_blockers"]


def test_doctor_hard_rejects_arm64_windows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    host = windows_host_compatibility(
        system="Windows",
        machine="ARM64",
        windows_major=11,
    )
    versions = {
        {"yaml": "PyYAML", "PIL": "pillow"}.get(module, module): spec.partition("==")[2]
        for module, spec in RUNTIME_DEPENDENCIES
    }
    monkeypatch.setattr(core, "windows_host_compatibility", lambda **_kwargs: host)
    monkeypatch.setattr(core.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(core.importlib_metadata, "version", lambda name: versions[name])
    monkeypatch.setattr(
        core,
        "discover_origin_application",
        lambda: {
            "application_present": True,
            "path": "Origin64.exe",
            "callability_status": "ready_to_attempt",
        },
    )

    result = doctor(engine_home=ENGINE)

    assert result["ready_for_analysis"] is False
    assert "windows_x64_amd64_required" in result["manual_blockers"]


def test_setup_hard_rejects_unsupported_windows_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    host = windows_host_compatibility(
        system="Windows",
        machine="ARM64",
        windows_major=11,
    )
    monkeypatch.setattr(bootstrap, "windows_host_compatibility", lambda: host)

    returncode = bootstrap.install_skill(["--target", str(tmp_path / "editaplot")])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 3
    assert payload["error"]["code"] == "unsupported_windows_host"
    assert "windows_x64_amd64_required" in payload["error"]["host"]["reasons"]
    assert not (tmp_path / "editaplot").exists()


def test_repair_uses_the_same_python_compatibility_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    incompatible = python_compatibility(
        version=(3, 13, 1),
        implementation="CPython",
        architecture_bits=64,
    )
    monkeypatch.setattr(core, "python_compatibility", lambda: incompatible)

    with pytest.raises(EditaPlotError) as raised:
        repair_environment(engine_home=ENGINE)

    assert raised.value.code == "python_version_unrepairable"
    assert raised.value.details["compatibility"]["required"] == "64-bit CPython >=3.10,<3.13"


def test_repair_keyboard_interrupt_restores_old_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_root = tmp_path / core.MANAGED_ENV_DIRECTORY
    env_root.mkdir()
    sentinel = env_root / "old-environment.bin"
    sentinel.write_bytes(b"old-valid-bytes")
    compatibility = python_compatibility(
        version=(3, 12, 4),
        implementation="CPython",
        architecture_bits=64,
    )
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")
    monkeypatch.setattr(core, "bootstrap_engine", lambda _value=None: tmp_path)
    monkeypatch.setattr(core, "python_compatibility", lambda: compatibility)

    def fake_status(root: Path) -> dict[str, object]:
        python = root / core.MANAGED_ENV_DIRECTORY / "Scripts" / "python.exe"
        return {
            "exists": (root / core.MANAGED_ENV_DIRECTORY).exists(),
            "valid": python.is_file(),
            "reason": "ready" if python.is_file() else "managed_python_missing",
            "python_executable": str(python),
        }

    monkeypatch.setattr(core, "managed_environment_status", fake_status)
    dependency_checks = 0

    def fake_dependencies(_python: Path) -> dict[str, object]:
        nonlocal dependency_checks
        dependency_checks += 1
        if dependency_checks == 2:
            raise KeyboardInterrupt
        return {"ok": True, "missing_or_mismatched": []}

    monkeypatch.setattr(core, "_verify_managed_dependencies", fake_dependencies)
    monkeypatch.setattr(
        core,
        "_probe_python_executable",
        lambda python: {
            "ok": True,
            "compatible": True,
            "version": "3.12.4",
            "architecture_bits": 64,
            "executable": str(python),
        },
    )

    def fake_subprocess(command: list[str], **_kwargs: object) -> types.SimpleNamespace:
        if command[1:3] == ["-m", "venv"]:
            staged_python = Path(command[-1]) / "Scripts" / "python.exe"
            staged_python.parent.mkdir(parents=True)
            staged_python.touch()
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(core.subprocess, "run", fake_subprocess)

    with pytest.raises(KeyboardInterrupt):
        repair_environment(engine_home=tmp_path)

    assert sentinel.read_bytes() == b"old-valid-bytes"
    assert not list(tmp_path.glob(f"{core.MANAGED_ENV_DIRECTORY}.build-*"))
    assert not list(tmp_path.glob(f"{core.MANAGED_ENV_DIRECTORY}.stale-*"))


def test_managed_path_removal_rejects_paths_outside_engine_root(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    engine.mkdir()
    outside = tmp_path / f"{core.MANAGED_ENV_DIRECTORY}.build-attacker"
    outside.mkdir()

    with pytest.raises(EditaPlotError) as raised:
        core._remove_managed_path(engine, outside)

    assert raised.value.code == "managed_path_outside_engine_root"
    assert outside.is_dir()


def test_doctor_repair_reports_origin_only_blocker_without_dependency_repair(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {
        "schema_version": "1.0",
        "ok": True,
        "ready_for_analysis": True,
        "ready_for_render": False,
        "missing_python_dependencies": [],
        "automatic_repair": {
            "available": False,
            "supported_python": "64-bit CPython >=3.10,<3.13",
        },
        "manual_blockers": ["origin_automation_application_not_detected"],
    }
    monkeypatch.setattr(editaplot_cli, "doctor", lambda **_kwargs: report)
    monkeypatch.setattr(
        editaplot_cli,
        "repair_environment",
        lambda **_kwargs: pytest.fail("dependency repair must not run for an Origin-only blocker"),
    )

    returncode = editaplot_cli.main(["doctor", "--repair"])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload == report


def test_setup_refuses_to_force_overwrite_an_unrecognized_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "not-a-skill"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("user content", encoding="utf-8")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "skill_destination_not_editaplot"
    assert sentinel.read_text(encoding="utf-8") == "user content"
    assert not (target / "scripts").exists()


def test_setup_recognizes_complete_pre_bootstrap_editaplot_installation(tmp_path: Path) -> None:
    target = tmp_path / "editaplot"
    required_files = (
        target / "SKILL.md",
        target / "scripts" / "editaplot.py",
        target / "scripts" / "editaplot_core.py",
        target / "scripts" / "requirements-runtime.lock",
        target / "agents" / "openai.yaml",
        target / "references" / "runtime.md",
    )
    for path in required_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "---\nname: editaplot\n---\n" if path.name == "SKILL.md" else "legacy\n"
        path.write_text(content, encoding="utf-8")

    assert bootstrap._is_recognized_editaplot_skill(target) is True


def test_setup_rejects_incomplete_pre_bootstrap_lookalike(tmp_path: Path) -> None:
    target = tmp_path / "editaplot-lookalike"
    (target / "scripts").mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: editaplot\n---\n", encoding="utf-8")
    (target / "scripts" / "editaplot.py").write_text("# unrelated\n", encoding="utf-8")

    assert bootstrap._is_recognized_editaplot_skill(target) is False


def test_setup_rejects_unknown_argument_without_using_default_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    returncode = bootstrap.install_skill(["--taret", str(tmp_path / "wrong")])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "setup_argument_unknown"
    assert not (tmp_path / "codex-home").exists()


def test_setup_rejects_a_target_nested_inside_the_source_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    target = source / "nested-install"
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "SKILL_ROOT", source)

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 2
    assert payload["error"]["code"] == "skill_destination_inside_source_rejected"
    assert not target.exists()


def _write_transaction_test_skill(path: Path, *, lock: bytes, label: str) -> None:
    scripts = path / "scripts"
    scripts.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: editaplot\n---\n", encoding="utf-8")
    (scripts / "editaplot.py").write_text(f"# {label}\n", encoding="utf-8")
    (scripts / "bootstrap_editaplot.py").write_text(f"# {label}\n", encoding="utf-8")
    (scripts / "requirements-runtime.lock").write_bytes(lock)
    (path / "identity.txt").write_text(label, encoding="utf-8")


@pytest.mark.parametrize("environment_committed", [False, True])
def test_setup_crash_recovery_uses_skill_and_environment_lock_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_committed: bool,
) -> None:
    target = tmp_path / "editaplot"
    _write_transaction_test_skill(target, lock=b"old-lock", label="old")
    staging = bootstrap._next_install_sibling(target, "build")
    _write_transaction_test_skill(staging, lock=b"new-lock", label="new")
    bootstrap._write_install_state(staging, target=target, kind="build")
    backup = bootstrap._next_install_sibling(target, "backup")
    engine = tmp_path / "engine"
    engine.mkdir()
    bootstrap._write_install_journal(target, backup, engine, staging)
    os.replace(target, backup)
    os.replace(staging, target)
    old_hash = hashlib.sha256(b"old-lock").hexdigest()
    new_hash = hashlib.sha256(b"new-lock").hexdigest()
    monkeypatch.setattr(bootstrap, "resolve_engine_home", lambda _value: engine)
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "dependency_lock_sha256": new_hash if environment_committed else old_hash,
        },
    )

    recovery = bootstrap._recover_install_swap(target)

    expected = "new" if environment_committed else "old"
    assert (target / "identity.txt").read_text(encoding="utf-8") == expected
    assert recovery == (
        "committed_skill_and_environment"
        if environment_committed
        else "restored_previous_skill_after_environment_mismatch"
    )
    assert not backup.exists()
    assert not bootstrap._install_journal(target).exists()


def test_setup_recovery_cleans_staging_when_crash_precedes_old_target_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "editaplot"
    _write_transaction_test_skill(target, lock=b"old-lock", label="old")
    staging = bootstrap._next_install_sibling(target, "build")
    _write_transaction_test_skill(staging, lock=b"new-lock", label="new")
    bootstrap._write_install_state(staging, target=target, kind="build")
    backup = bootstrap._next_install_sibling(target, "backup")
    engine = tmp_path / "engine"
    engine.mkdir()
    bootstrap._write_install_journal(target, backup, engine, staging)
    monkeypatch.setattr(bootstrap, "resolve_engine_home", lambda _value: engine)
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "dependency_lock_sha256": hashlib.sha256(b"old-lock").hexdigest(),
        },
    )

    recovery = bootstrap._recover_install_swap(target)

    assert recovery == "cancelled_before_skill_swap"
    assert (target / "identity.txt").read_text(encoding="utf-8") == "old"
    assert not staging.exists()
    assert not bootstrap._install_journal(target).exists()


def test_setup_final_skill_rename_failure_restores_old_target_before_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "editaplot"
    _write_transaction_test_skill(target, lock=b"old-lock", label="old")
    before = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "base-python.exe"},
            "attempts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_run_json_command",
        lambda *_args, **_kwargs: pytest.fail("environment repair must follow Skill swap"),
    )
    original_replace = bootstrap.os.replace

    def fail_final_rename(source: object, destination: object) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if (
            source_path.is_dir()
            and source_path.name.startswith(bootstrap._install_prefix(target, "build"))
            and destination_path == target
        ):
            raise OSError("injected final Skill rename failure")
        original_replace(source, destination)

    monkeypatch.setattr(bootstrap.os, "replace", fail_final_rename)

    with pytest.raises(OSError, match="injected final Skill rename failure"):
        bootstrap.install_skill(["--target", str(target)])

    after = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not bootstrap._install_journal(target).exists()


def test_crashed_fresh_install_mismatch_then_repair_failure_leaves_no_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "editaplot"
    staging = bootstrap._next_install_sibling(target, "build")
    _write_transaction_test_skill(staging, lock=b"new-lock", label="incomplete")
    bootstrap._write_install_state(staging, target=target, kind="build")
    engine = tmp_path / "engine"
    engine.mkdir()
    bootstrap._write_install_journal(target, None, engine, staging)
    os.replace(staging, target)
    monkeypatch.setattr(bootstrap, "resolve_engine_home", lambda _value: engine)
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "dependency_lock_sha256": hashlib.sha256(b"old-lock").hexdigest(),
        },
    )
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "base-python.exe"},
            "attempts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_run_json_command",
        lambda *_args, **_kwargs: (
            18,
            {"ok": False, "error": {"code": "second_repair_failed"}},
        ),
    )

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 18
    assert payload["status"] == "setup_repair_failed_fresh_install_removed"
    assert not target.exists()
    assert not bootstrap._install_journal(target).exists()


def test_setup_updates_recognized_skill_then_repairs_and_rechecks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "editaplot"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: editaplot\n---\n", encoding="utf-8")
    (scripts / "editaplot.py").write_text("# old\n", encoding="utf-8")
    (scripts / "bootstrap_editaplot.py").write_text("# old\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "selected-python.exe"},
            "attempts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "python_executable": "managed-python.exe",
            "dependency_lock_sha256": bootstrap._skill_dependency_lock_sha(SKILL_ROOT),
        },
    )
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        environment: dict[str, str],
        timeout: int = 1200,
    ) -> tuple[int, dict[str, object]]:
        del environment, timeout
        commands.append(command)
        if "repair-environment" in command:
            return 0, {"ok": True, "repair": {"ok": True}}
        return 0, {
            "ok": True,
            "ready_for_analysis": True,
            "ready_for_render": False,
            "manual_blockers": ["origin_automation_application_not_detected"],
        }

    monkeypatch.setattr(bootstrap, "_run_json_command", fake_run)

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload["status"] == "updated_and_environment_ready"
    assert payload["ready_for_analysis"] is True
    assert payload["ready_for_render"] is False
    assert commands[0][2] == "repair-environment"
    assert "--repair" not in commands[0]
    assert "--repair" not in commands[1]
    assert commands[1][0] == "managed-python.exe"
    assert (target / ".editaplot-local.json").is_file()


def test_setup_repair_failure_preserves_recognized_target_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "editaplot"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: editaplot\n---\nold\n", encoding="utf-8")
    (scripts / "editaplot.py").write_bytes(b"old cli\r\n")
    (scripts / "bootstrap_editaplot.py").write_bytes(b"old bootstrap\r\n")
    (target / "legacy-only.txt").write_bytes(b"must survive")
    before = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "selected-python.exe"},
            "attempts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_run_json_command",
        lambda *_args, **_kwargs: (
            17,
            {"ok": False, "error": {"code": "injected_repair_failure"}},
        ),
    )

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().err)
    after = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file()
    }

    assert returncode == 17
    assert payload["status"] == "setup_repair_failed_previous_skill_restored"
    assert after == before
    assert not list(tmp_path.glob(".editaplot.editaplot-build-*"))


@pytest.mark.parametrize("existing", [False, True])
def test_setup_zero_repair_with_old_environment_hash_rolls_back_immediately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing: bool,
) -> None:
    target = tmp_path / "editaplot"
    if existing:
        _write_transaction_test_skill(target, lock=b"old-lock", label="old")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "base-python.exe"},
            "attempts": [],
        },
    )
    old_hash = hashlib.sha256(b"old-lock").hexdigest()
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "python_executable": "managed-python.exe",
            "dependency_lock_sha256": old_hash,
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "_run_json_command",
        lambda command, **_kwargs: (
            (0, {"ok": True})
            if "repair-environment" in command
            else pytest.fail("doctor must not run for a mismatched environment commit")
        ),
    )

    returncode = bootstrap.install_skill(["--target", str(target)])
    payload = json.loads(capsys.readouterr().err)

    assert returncode == 3
    recovery = payload["post_repair_doctor"]["error"]["transaction_recovery"]
    if existing:
        assert (target / "identity.txt").read_text(encoding="utf-8") == "old"
        assert recovery == "restored_previous_skill_after_environment_mismatch"
    else:
        assert not target.exists()
        assert recovery == "removed_incomplete_fresh_skill"
    assert not bootstrap._install_journal(target).exists()


def test_setup_success_atomically_removes_files_deleted_from_new_skill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "editaplot"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: editaplot\n---\n", encoding="utf-8")
    (scripts / "editaplot.py").write_text("# old\n", encoding="utf-8")
    (scripts / "bootstrap_editaplot.py").write_text("# old\n", encoding="utf-8")
    legacy = target / "deleted-in-new-version.txt"
    legacy.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "test", "executable": "base-python.exe"},
            "attempts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "managed_environment_status",
        lambda _root: {
            "valid": True,
            "python_executable": "managed-python.exe",
            "dependency_lock_sha256": bootstrap._skill_dependency_lock_sha(SKILL_ROOT),
        },
    )

    def fake_run(command: list[str], **_kwargs: object) -> tuple[int, dict[str, object]]:
        if "repair-environment" in command:
            return 0, {"ok": True, "managed_environment": "ready"}
        return 0, {"ok": True, "ready_for_analysis": True, "ready_for_render": False}

    monkeypatch.setattr(bootstrap, "_run_json_command", fake_run)

    assert bootstrap.install_skill(["--target", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "updated_and_environment_ready"
    assert not legacy.exists()
    assert not (target / bootstrap.INSTALL_STATE_NAME).exists()
    assert (target / "scripts" / "editaplot.py").read_bytes() == (
        SKILL_ROOT / "scripts" / "editaplot.py"
    ).read_bytes()


def test_setup_always_requests_managed_repair_even_when_base_is_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "fresh-editaplot"
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Windows")
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ENGINE, {}))
    monkeypatch.setattr(
        bootstrap,
        "discover_python",
        lambda _root: {
            "selected": {"source": "base_ready", "executable": "base-python.exe"},
            "attempts": [],
        },
    )
    statuses = iter(
        [
            {
                "valid": True,
                "python_executable": "managed-python.exe",
                "dependency_lock_sha256": bootstrap._skill_dependency_lock_sha(SKILL_ROOT),
            },
        ]
    )
    monkeypatch.setattr(bootstrap, "managed_environment_status", lambda _root: next(statuses))
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> tuple[int, dict[str, object]]:
        commands.append(command)
        if "repair-environment" in command:
            return 0, {"ok": True}
        return 0, {"ok": True, "ready_for_analysis": True, "ready_for_render": False}

    monkeypatch.setattr(bootstrap, "_run_json_command", fake_run)

    assert bootstrap.install_skill(["--target", str(target)]) == 0
    capsys.readouterr()
    assert commands[0][2] == "repair-environment"
    assert commands[1][0] == "managed-python.exe"


def test_setup_command_timeout_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    def time_out(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(
            cmd=["python.exe"],
            timeout=7,
            output=b"partial output",
            stderr=b"partial error",
        )

    monkeypatch.setattr(bootstrap.subprocess, "run", time_out)

    code, payload = bootstrap._run_json_command(
        ["python.exe", "editaplot.py", "repair-environment"],
        environment={},
        timeout=7,
    )

    assert code == 124
    assert payload["error"]["code"] == "setup_command_timeout"
    assert payload["error"]["timeout_seconds"] == 7
    assert "partial output" in payload["error"]["output_tail"]


def test_setup_command_disappearance_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError(2, "missing")),
    )

    code, payload = bootstrap._run_json_command(
        ["vanished-python.exe", "editaplot.py", "repair-environment"],
        environment={},
    )

    assert code == 126
    assert payload["error"] == {
        "code": "setup_command_unavailable",
        "message": "The selected setup interpreter or command became unavailable.",
        "command": "vanished-python.exe",
        "os_error": "FileNotFoundError",
        "errno": 2,
    }


def test_install_path_removal_rejects_non_sibling(tmp_path: Path) -> None:
    target = tmp_path / "target" / "editaplot"
    target.parent.mkdir()
    outside = tmp_path / ".editaplot.editaplot-build-attacker"
    outside.mkdir()

    with pytest.raises(ValueError, match="unsafe EditaPlot build path"):
        bootstrap._remove_install_sibling(target, outside, "build")

    assert outside.is_dir()


def test_batch_launcher_probes_compatibility_before_bootstrap() -> None:
    launcher = (PRODUCT_ROOT / "editaplot.cmd").read_text(encoding="utf-8")

    assert "EDITAPLOT_PYTHON_PROBE" in launcher
    assert "sys.version_info[:2] in ((3,10),(3,11),(3,12))" in launcher
    assert '-c "import sys"' not in launcher
    assert "if not defined EDITAPLOT_PYTHON goto launcher_312" in launcher
    assert "reg.exe query" in launcher
    assert "PythonCore\\%~1\\InstallPath" in launcher
    assert launcher.find(":registry_python") < launcher.find(":local_312")
    assert launcher.rfind("goto managed_runtime") > launcher.find(":local_310")


def test_bundled_runtime_is_self_contained_for_doctor_and_catalog() -> None:
    result = doctor(engine_home=RUNTIME)
    palettes = palette_catalog(engine_home=RUNTIME)

    assert result["ready_for_analysis"] is True
    assert Path(next(item["value"] for item in result["checks"] if item["name"] == "engine")) == RUNTIME
    assert palettes["palette_count"] == 8
    manifest = json.loads((RUNTIME / "runtime-manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] >= 300


def test_runtime_manifest_is_an_exact_hash_inventory() -> None:
    manifest_path = RUNTIME / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {item["path"]: item for item in manifest["files"]}
    actual = {
        path.relative_to(RUNTIME).as_posix(): path
        for path in RUNTIME.rglob("*")
        for relative in (path.relative_to(RUNTIME),)
        if path.is_file()
        and path != manifest_path
        and path.name != core.MANAGED_ENV_LOCK
        and not any(
            part in {"__pycache__", core.MANAGED_ENV_DIRECTORY}
            or part.startswith(
                (
                    f"{core.MANAGED_ENV_DIRECTORY}.build-",
                    f"{core.MANAGED_ENV_DIRECTORY}.stale-",
                )
            )
            for part in relative.parts
        )
        and path.suffix.lower() not in {".pyc", ".pyo"}
    }

    assert manifest["file_count"] == len(records) == len(actual)
    assert set(records) == set(actual)
    for relative, path in actual.items():
        assert records[relative]["size_bytes"] == path.stat().st_size
        assert records[relative]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    assert (RUNTIME / "LICENSE").read_bytes() == (PRODUCT_ROOT / "LICENSE").read_bytes()
    assert (RUNTIME / "NOTICE").read_bytes() == (PRODUCT_ROOT / "NOTICE").read_bytes()


def test_runtime_dependency_allowlist_matches_release_file() -> None:
    declared = {
        line.strip()
        for line in (PRODUCT_ROOT / "requirements-runtime.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert declared == {spec for _module, spec in RUNTIME_DEPENDENCIES}


def test_public_skill_metadata_and_legal_copies_are_self_contained() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert skill_text.startswith("---\n")
    _opening, frontmatter, body = skill_text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)
    agent = yaml.safe_load((SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))

    assert metadata["name"] == "editaplot"
    assert "Origin/OriginPro" in metadata["description"]
    assert "# EditaPlot" in body
    assert agent["interface"]["display_name"] == "EditaPlot"
    default_prompt = agent["interface"]["default_prompt"]
    assert "Origin Automation" in default_prompt
    assert not any(
        token in default_prompt
        for token in ("合法", "授权", "激活", "手动启动", "licensed", "activation")
    )
    assert (SKILL_ROOT / "LICENSE").read_bytes() == (PRODUCT_ROOT / "LICENSE").read_bytes()
    assert (SKILL_ROOT / "NOTICE").read_bytes() == (PRODUCT_ROOT / "NOTICE").read_bytes()


def test_runtime_dependency_lock_is_exact_and_bundled_with_skill() -> None:
    release_lock = (PRODUCT_ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
    skill_lock = (SCRIPTS / "requirements-runtime.lock").read_text(encoding="utf-8")
    pinned = [line for line in release_lock.splitlines() if line and not line.startswith("#")]

    assert release_lock == skill_lock
    assert pinned
    assert all(
        "==" in line and not any(token in line for token in (">=", "<=", "~=", "<", ">")) for line in pinned
    )
    assert {spec for _module, spec in RUNTIME_DEPENDENCIES}.issubset(set(pinned))


def test_public_asset_provenance_is_complete_and_synthetic() -> None:
    provenance = json.loads(
        (PRODUCT_ROOT / "assets" / "provenance-manifest.json").read_text(encoding="utf-8")
    )
    records = {item["path"]: item for item in provenance["assets"]}
    assert provenance["human_review"]["decision"] == "approved_for_public_source_release"
    for field in ("inventory_generator", "gallery_fixture_generator"):
        binding = provenance[field]
        bound_path = PRODUCT_ROOT / binding["path"]
        assert binding["sha256"] == hashlib.sha256(bound_path.read_bytes()).hexdigest()
    public_assets = {
        path.relative_to(PRODUCT_ROOT).as_posix(): path
        for root in (
            PRODUCT_ROOT / "examples",
            PRODUCT_ROOT / "runtime" / "templates",
            PRODUCT_ROOT / "runtime" / "src" / "origin_sciplot" / "resources",
            PRODUCT_ROOT / "assets" / "gallery",
            PRODUCT_ROOT / "assets" / "palettes",
            PRODUCT_ROOT / "skill" / "editaplot" / "assets" / "palettes",
        )
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".png"}
    }

    assert provenance["asset_count"] == len(records) == len(public_assets)
    assert set(records) == set(public_assets)
    for relative, path in public_assets.items():
        record = records[relative]
        assert record["synthetic_or_generated"] is True
        assert record["contains_phi"] is False
        assert record["size_bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        if relative.startswith("assets/gallery/"):
            assert not any(record["png_text"].values())

    preview = records["runtime/templates/xps_c1s_fit/preview.png"]
    assert preview["png_text"] == {"Software": "EditaPlot"}
    trpl_header = (
        (PRODUCT_ROOT / "examples" / "gallery" / "pl_trpl.csv").read_text(encoding="utf-8").splitlines()[0]
    )
    assert "Reference film" in trpl_header
    assert all(legacy not in trpl_header for legacy in ("Glass", "BDT-PTZ", "BDT-POZ"))


def test_palette_catalog_is_chinese_first_and_has_advanced_options() -> None:
    public = palette_catalog(engine_home=ENGINE)
    complete = palette_catalog(engine_home=ENGINE, public_only=False)

    assert public["palette_count"] == 8
    assert complete["palette_count"] == 10
    assert all(item["name_zh"] and item["palette_id"] for item in complete["palettes"])
    assert {item["palette_id"] for item in complete["palettes"] if not item["public_default"]} == {
        "forest_amber",
        "violet_lime",
    }


def test_plan_freezes_palette_and_passes_it_to_worker() -> None:
    source = PRODUCT_ROOT / "examples" / "gallery" / "line_error.csv"
    base = build_plan(
        source,
        template_id="line_error",
        claim="Two series have distinct response trajectories.",
        evidence_role="comparison",
        engine_home=ENGINE,
    )
    plan = build_plan(
        source,
        template_id="line_error",
        claim="Two series have distinct response trajectories.",
        evidence_role="comparison",
        palette_id="ocean_coral",
        engine_home=ENGINE,
    )

    assert plan["figure_contract"]["palette"]["palette_id"] == "ocean_coral"
    assert plan["template"]["plan_digest"] != base["template"]["plan_digest"]
    command, _env, _root = build_worker_command(plan, engine_home=ENGINE)
    index = command.index("--palette-id")
    assert command[index + 1] == "ocean_coral"


def test_palette_override_does_not_weaken_xps_contract() -> None:
    with pytest.raises(EditaPlotError, match="XPS keeps"):
        build_plan(
            EXAMPLES / "xps_fit.csv",
            template_id="xps",
            claim="XPS component evidence remains editable.",
            evidence_role="spectral decomposition",
            palette_id="ocean_coral",
            engine_home=ENGINE,
        )


def test_public_bar_showcase_uses_few_series_and_explicit_sd() -> None:
    plan = build_plan(
        PRODUCT_ROOT / "examples" / "gallery" / "bar_grouped_error.csv",
        template_id="bar",
        claim="Three teaching groups differ across four conditions with explicit SD uncertainty.",
        evidence_role="comparison",
        intent="grouped bar with SD error bars",
        engine_home=ENGINE,
    )

    roles = dict(plan["template"]["summary"]["roles"])
    assert roles["Series"] == "Reference, Treatment A, Treatment B"
    assert roles["Error"] == "Reference_SD, Treatment A_SD, Treatment B_SD"
    assert plan["source"]["row_count"] == 5
    assert plan["can_render"] is True


def test_grouped_box_plan_freezes_exact_axis_wording_and_worker_arguments() -> None:
    source = PRODUCT_ROOT / "examples" / "gallery" / "grouped_box_medical.csv"
    base = build_plan(
        source,
        template_id="grouped_box",
        claim="Raw observations remain visible in every group.",
        evidence_role="distribution comparison",
        engine_home=ENGINE,
    )
    plan = build_plan(
        source,
        template_id="grouped_box",
        claim="Raw observations remain visible in every group.",
        evidence_role="distribution comparison",
        x_title="处理条件",
        y_title="归一化器官重量比",
        engine_home=ENGINE,
    )

    assert plan["figure_contract"]["axis_title_overrides"] == {
        "x_title": "处理条件",
        "y_title": "归一化器官重量比",
    }
    assert plan["template"]["plan_digest"] != base["template"]["plan_digest"]
    facts = dict(plan["template"]["summary"]["facts"])
    assert facts["X 轴"] == "处理条件"
    assert facts["Y 轴"] == "归一化器官重量比"

    command, _env, _root = build_worker_command(plan, engine_home=ENGINE)
    index = command.index("--text-overrides-json")
    assert json.loads(command[index + 1]) == plan["figure_contract"]["axis_title_overrides"]


def test_radar_without_scale_intent_does_not_silently_auto_select() -> None:
    result = recommend_charts(
        ENGINE / "templates" / "radar" / "example_standard.csv",
        engine_home=ENGINE,
    )

    radar = next(item for item in result["candidates"] if item["template_id"] == "radar")
    assert "radar_scale_confirmation_preferred" in radar["reason_codes"]
    assert result["auto_selection"]["allowed"] is False


@requires_local_showcase
def test_gallery_report_covers_all_public_verified_routes() -> None:
    report = json.loads((PRODUCT_ROOT / "showcase" / "visual-qa.json").read_text(encoding="utf-8"))

    assert report["case_count"] == 36
    assert report["route_count"] == 33
    assert report["programmatic_pass_count"] == 36
    assert report["manual_visual_pass_count"] == 36
    assert report["collection_count"] == 6
    assert {case["programmatic_status"] for case in report["cases"]} == {"pass"}
    assert {case["manual_visual_review"] for case in report["cases"]} == {"pass"}


@requires_local_showcase
def test_capability_poster_is_retained_as_an_archived_promotion_asset() -> None:
    manifest_path = PRODUCT_ROOT / "showcase" / "posters" / "editaplot_all_templates_overview_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("the archived promotion poster has not been regenerated under the public brand")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["scientific_plots_redrawn"] is False
    assert manifest["source_case_count"] == len(manifest["source_cases"])
    assert sum(len(section["case_ids"]) for section in manifest["sections"]) == manifest["source_case_count"]
    for output in manifest["outputs"].values():
        path = PRODUCT_ROOT / output["path"]
        assert path.is_file()
        assert path.stat().st_size > 0


@requires_local_showcase
def test_gallery_index_links_are_relative_to_the_showcase_directory() -> None:
    showcase = PRODUCT_ROOT / "showcase"
    report = json.loads((showcase / "visual-qa.json").read_text(encoding="utf-8"))
    document = (showcase / "index.html").read_text(encoding="utf-8")
    chinese = (showcase / "index.zh-CN.html").read_text(encoding="utf-8")

    assert "showcase/showcase/" not in document.replace("\\", "/")
    assert "showcase/showcase/" not in chinese.replace("\\", "/")
    assert '<html lang="en">' in document
    assert '<html lang="zh-CN">' in chinese
    assert 'href="index.zh-CN.html"' in document
    assert 'href="index.html"' in chinese
    assert "按科研目的浏览六大类" in chinese
    assert "可直接改写的精确需求词" in chinese
    assert "医学分组箱线图与原始点" in chinese
    assert 'class="skip-link"' in document
    assert 'class="skip-link"' in chinese
    assert "minmax(min(100%,340px),1fr)" in document
    assert "poster-feature" not in document
    assert "poster-feature" not in chinese
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            product_path = PRODUCT_ROOT / artifact
            index_href = product_path.relative_to(showcase).as_posix()
            assert product_path.is_file()
            assert f'="{index_href}"' in document
            assert f'="{index_href}"' in chinese


@requires_local_showcase
def test_curated_collection_pages_link_back_to_verified_artifacts() -> None:
    showcase = PRODUCT_ROOT / "showcase"
    collection_dir = showcase / "collections"
    collection_zh_dir = showcase / "collections-zh"
    pages = sorted(collection_dir.glob("*.html"))
    chinese_pages = sorted(collection_zh_dir.glob("*.html"))

    assert len(pages) == 6
    assert len(chinese_pages) == 6
    for page in pages:
        document = page.read_text(encoding="utf-8")
        assert 'href="../index.html"' in document
        assert "../gallery/" in document
        assert '<html lang="en">' in document
    for page in chinese_pages:
        document = page.read_text(encoding="utf-8")
        assert 'href="../index.zh-CN.html"' in document
        assert "../gallery/" in document
        assert '<html lang="zh-CN">' in document
