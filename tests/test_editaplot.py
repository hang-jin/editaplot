from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
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

from editaplot_core import (  # noqa: E402
    RUNTIME_DEPENDENCIES,
    EditaPlotError,
    build_medical_panel_plan,
    build_plan,
    build_worker_command,
    doctor,
    inspect_data,
    palette_catalog,
    recommend_charts,
    validate_plan,
    verify_output,
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


def test_render_requires_manual_origin_confirmation(tmp_path: Path) -> None:
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
    assert payload["error"]["code"] == "manual_origin_confirmation_required"


def test_verify_refuses_incomplete_output(tmp_path: Path) -> None:
    (tmp_path / "result.png").write_bytes(b"png")

    result = verify_output(tmp_path)

    assert result["programmatic_pass"] is False
    assert result["human_visual_qa"]["status"] == "pending"


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
    assert result["manual_origin_launch_confirmation"] == "required_before_render"
    assert result["automatic_repair"]["scope"] == "project_local_python_dependencies_only"
    assert result["automatic_repair"]["origin_installation_modified"] is False


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
        if path.is_file()
        and path != manifest_path
        and "__pycache__" not in path.parts
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
