"""Build the verified EditaPlot gallery with the public CLI and a callable local Origin."""

# ruff: noqa: E501, S603

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skill" / "editaplot" / "scripts" / "editaplot.py"
DATA = ROOT / "examples" / "gallery"
GALLERY = ROOT / "showcase" / "gallery"


@dataclass(frozen=True)
class ShowcaseCase:
    id: str
    template_id: str
    data_file: str
    claim: str
    evidence_role: str
    intent: str
    x_title: str | None = None
    y_title: str | None = None
    title_zh: str | None = None
    display_in_gallery: bool = True


CASES = (
    ShowcaseCase(
        "xps-fit",
        "xps",
        "xps_fit.csv",
        "The teaching spectrum is represented by a background, fitted envelope, and three editable components.",
        "comparison",
        "XPS peak fitting",
    ),
    ShowcaseCase(
        "xps-comparison",
        "xps_compare",
        "xps_compare.csv",
        "Three independent synthetic XPS measurements share one binding-energy axis without being reinterpreted as fitted components.",
        "spectral comparison",
        "XPS multi-spectrum comparison",
        title_zh="XPS 多样品谱线对比",
    ),
    ShowcaseCase(
        "xrd-multi",
        "xrd",
        "xrd_multi.csv",
        "The teaching diffraction profiles differ across the measured angle range.",
        "comparison",
        "XRD multi-series comparison",
    ),
    ShowcaseCase(
        "eis-nyquist",
        "eis",
        "eis_nyquist.csv",
        "The teaching impedance response follows a resolved Nyquist arc.",
        "relationship",
        "EIS Nyquist impedance",
    ),
    ShowcaseCase(
        "trajectory3d",
        "trajectory3d",
        "trajectory3d.csv",
        "Three synthetic Nyquist trajectories remain separated by a real, unit-bearing measurement position rather than decorative depth.",
        "three-axis relationship",
        "multi-position 3D Nyquist trajectory",
        title_zh="三维多位置 Nyquist 轨迹",
    ),
    ShowcaseCase(
        "density-ridgeline3d",
        "density_ridgeline3d",
        "density_ridgeline3d.csv",
        "Four synthetic follow-up conditions compare two upstream precomputed density profiles while each supplied focal value remains a Z=0 baseline locator.",
        "three-axis distribution comparison",
        "3D dual-density ridgeline with supplied baseline focal locators",
        title_zh="三维双密度曲线与基线焦点",
    ),
    ShowcaseCase(
        "cv-cycles",
        "cv",
        "cv_cycles.csv",
        "The two teaching cycles preserve the forward and reverse scan response.",
        "comparison",
        "CV cyclic voltammetry",
    ),
    ShowcaseCase(
        "lsv-multi",
        "lsv",
        "lsv_multi.csv",
        "The teaching samples show distinct current responses over the linear sweep.",
        "comparison",
        "LSV linear sweep",
    ),
    ShowcaseCase(
        "xas-profiles",
        "xas",
        "xas_profiles.csv",
        "The teaching absorption profiles show distinguishable edge positions and post-edge responses.",
        "comparison",
        "XAS absorption spectrum",
    ),
    ShowcaseCase(
        "pl-trpl",
        "pl",
        "pl_trpl.csv",
        "Three synthetic time-resolved photoluminescence traces and their explicit fit curves remain independently editable on a logarithmic intensity axis.",
        "decay comparison",
        "TRPL photoluminescence decay with user supplied fits",
    ),
    ShowcaseCase(
        "pl-steady-state",
        "pl",
        "pl_steady_state.csv",
        "Three user-supplied steady-state photoluminescence spectra remain independently editable without hidden normalization or peak fitting.",
        "spectral comparison",
        "steady-state PL emission spectrum",
        x_title="Wavelength (nm)",
    ),
    ShowcaseCase(
        "pl-temperature-series",
        "pl",
        "pl_temperature_series.csv",
        "Six synthetic steady-state PL spectra preserve an ordered temperature progression without hidden normalization or peak labels.",
        "ordered spectral comparison",
        "steady-state PL temperature series",
        title_zh="PL 温度序列光谱",
    ),
    ShowcaseCase(
        "uv-vis-tauc",
        "uv_vis",
        "uv_vis_tauc.csv",
        "The measured absorbance spectrum is shown with a Tauc inset that uses only user-supplied photon-energy, Tauc, fit, and band-gap values.",
        "optical spectroscopy",
        "UV-vis absorbance with supplied Tauc inset",
    ),
    ShowcaseCase(
        "uv-vis-multi",
        "uv_vis",
        "uv_vis_multi.csv",
        "Three independently editable synthetic absorbance spectra preserve the measured wavelength range without an invented Tauc analysis.",
        "optical spectral comparison",
        "UV-vis multi-sample absorbance comparison",
        title_zh="UV-Vis 多样品吸收光谱",
    ),
    ShowcaseCase(
        "dsc-multi",
        "dsc",
        "dsc_multi.csv",
        "Three synthetic DSC heat-flow curves preserve their supplied sign convention and remain independently editable.",
        "thermal comparison",
        "DSC multi-sample heat flow comparison",
        title_zh="DSC 多样品热流曲线",
    ),
    ShowcaseCase(
        "nmr-comparison",
        "nmr",
        "nmr_comparison.csv",
        "Two synthetic 19F NMR spectra retain a descending chemical-shift axis without automatic peak assignment.",
        "spectral comparison",
        "19F NMR spectrum comparison",
        title_zh="19F NMR 光谱对比",
    ),
    ShowcaseCase(
        "ftir-temperature-series",
        "ftir",
        "ftir_temperature_series.csv",
        "Six synthetic FTIR transmittance spectra preserve an ordered temperature progression without baseline correction or peak labels.",
        "ordered spectral comparison",
        "FTIR temperature series comparison",
        title_zh="FTIR 温度序列光谱",
    ),
    ShowcaseCase(
        "bar-error-groups",
        "bar",
        "bar_grouped_error.csv",
        "Three teaching groups are compared across five conditions with explicitly defined SD uncertainty.",
        "comparison",
        "grouped bar with SD error bars",
    ),
    ShowcaseCase(
        "horizontal-long-labels",
        "horizontal_bar",
        "horizontal_long_labels.csv",
        "A compact ablation comparison keeps long variant labels readable with explicit SEM uncertainty.",
        "comparison",
        "horizontal bar for long labels",
    ),
    ShowcaseCase(
        "diverging-effects",
        "horizontal_bar",
        "diverging_effects.csv",
        "Signed teaching effect scores preserve direction and magnitude with a restrained cool-neutral-warm encoding.",
        "effect comparison",
        "diverging signed-effect horizontal bars",
    ),
    ShowcaseCase(
        "stacked-composition",
        "stacked_bar",
        "stacked_composition.csv",
        "Five teaching samples differ in absolute component composition with explicit total SD.",
        "composition",
        "absolute stacked composition",
    ),
    ShowcaseCase(
        "percent-composition",
        "percent_stacked_bar",
        "percent_composition.csv",
        "Five teaching cohorts differ in relative four-component composition.",
        "composition",
        "percentage composition with confirmed row denominator",
    ),
    ShowcaseCase(
        "pie-five-parts",
        "pie",
        "pie_five_parts.csv",
        "Five mutually exclusive teaching parts form one complete composition.",
        "composition",
        "pie part-to-whole",
    ),
    ShowcaseCase(
        "sankey-flow",
        "sankey",
        "sankey_four_stage.csv",
        "Teaching inputs are redistributed through two intermediate stages into three outcomes.",
        "relationship",
        "four-stage Sankey flow",
    ),
    ShowcaseCase(
        "circular-network",
        "circular_network",
        "circular_network.csv",
        "Directed relationships change between two periods while shared nodes retain fixed positions and one global weight scale.",
        "temporal directed relationship",
        "two-period circular directed weighted network",
        title_zh="多阶段环形有向加权网络图",
    ),
    ShowcaseCase(
        "scatter-dense",
        "scatter",
        "scatter_dense.csv",
        "Three teaching response series show distinct relationships with the continuous variable.",
        "relationship",
        "dense scatter relationship",
    ),
    ShowcaseCase(
        "line-error",
        "line_error",
        "line_error.csv",
        "The teaching treatment trend separates from control with explicitly defined uncertainty.",
        "comparison",
        "trend with SD and SEM error bars",
    ),
    ShowcaseCase(
        "trend-progression",
        "trend",
        "trend_progression.csv",
        "Three teaching methods show distinct progression over twelve ordered steps.",
        "comparison",
        "multi-series progression trendline",
    ),
    ShowcaseCase(
        "radar-multimetric",
        "radar",
        "radar_multimetric.csv",
        "Three teaching methods exhibit distinct profiles across five comparable normalized metrics.",
        "comparison",
        "radar multimetric comparison",
    ),
    ShowcaseCase(
        "heatmap-results",
        "heatmap",
        "heatmap_results.csv",
        "Five teaching methods are compared across six datasets in one annotated result matrix.",
        "comparison",
        "annotated results heatmap matrix",
        display_in_gallery=False,
    ),
    ShowcaseCase(
        "heatmap-dense-40x40",
        "heatmap",
        "heatmap_dense_40x40.csv",
        "A 40 by 40 synthetic result matrix uses sparse deterministic tick labels and a detached colorbar without unreadable cell text.",
        "high-density comparison",
        "dense 40 by 40 heatmap matrix",
        title_zh="40×40 高密度热力图",
        display_in_gallery=False,
    ),
    ShowcaseCase(
        "heatmap-dense-30x30",
        "heatmap",
        "heatmap_dense_30x30.csv",
        "A 30 by 30 synthetic result matrix keeps all 900 values while using sparse deterministic tick labels and a detached colorbar.",
        "high-density comparison",
        "dense 30 by 30 heatmap matrix",
        title_zh="30×30 高密度热力图",
    ),
    ShowcaseCase(
        "raw-observations",
        "raw_summary",
        "raw_observations.csv",
        "Every teaching observation remains visible while the median summarizes each group.",
        "comparison",
        "raw observations dot summary",
    ),
    ShowcaseCase(
        "violin-distributions",
        "violin",
        "violin_distributions.csv",
        "The three teaching groups show distinct distribution locations and shapes.",
        "distribution",
        "violin distribution comparison",
    ),
    ShowcaseCase(
        "histogram-frozen-bins",
        "histogram",
        "histogram_values.csv",
        "The teaching observations form a resolved univariate frequency distribution.",
        "distribution",
        "histogram frequency distribution",
    ),
    ShowcaseCase(
        "forest-intervals",
        "forest",
        "forest_intervals.csv",
        "The teaching effect estimates and explicit confidence intervals separate around a zero reference.",
        "comparison",
        "forest effect confidence interval",
    ),
    ShowcaseCase(
        "bubble-indexed-size",
        "bubble",
        "bubble_indexed_size.csv",
        "Response increases with exposure while bubble area preserves the teaching sample-size variable.",
        "relationship",
        "bubble indexed size relationship",
    ),
    ShowcaseCase(
        "medical-roc",
        "diagnostic_curve",
        "medical_roc.csv",
        "Three precomputed diagnostic ROC curves preserve the discrimination comparison without hidden smoothing or AUC calculation.",
        "discrimination",
        "medical imaging ROC diagnostic curve",
    ),
    ShowcaseCase(
        "medical-pr",
        "diagnostic_curve",
        "medical_pr.csv",
        "Two precomputed precision-recall curves are interpreted against an explicit prevalence baseline.",
        "discrimination",
        "medical imaging precision recall PR curve",
    ),
    ShowcaseCase(
        "medical-calibration",
        "calibration_curve",
        "medical_calibration.csv",
        "Observed event fractions track predicted risk while the bottom bars retain the precomputed bin-size distribution.",
        "reliability",
        "medical model calibration curve reliability",
    ),
    ShowcaseCase(
        "medical-decision",
        "decision_curve",
        "medical_decision.csv",
        "The imaging model retains greater precomputed net benefit than the clinical model over the useful threshold range.",
        "clinical utility",
        "medical decision curve DCA net benefit",
    ),
    ShowcaseCase(
        "medical-confusion",
        "confusion_matrix",
        "medical_confusion.csv",
        "A three-class count matrix keeps actual rows and predicted columns explicit without silent normalization.",
        "classification errors",
        "medical classification confusion matrix",
    ),
    ShowcaseCase(
        "medical-agreement",
        "bland_altman",
        "medical_bland_altman.csv",
        "Precomputed bias and limits of agreement frame the method-comparison differences without hidden pair inference.",
        "agreement",
        "Bland Altman medical measurement agreement",
    ),
    ShowcaseCase(
        "medical-longitudinal",
        "paired_trajectory",
        "medical_paired.csv",
        "Stable subject identities reveal consistent longitudinal change across four visits.",
        "paired stability",
        "paired longitudinal medical trajectory",
    ),
    ShowcaseCase(
        "medical-grouped-box",
        "grouped_box",
        "grouped_box_medical.csv",
        "Eight raw-data groups preserve every observation, grouped condition labels, and explicit sample sizes without automatically inventing significance annotations.",
        "distribution comparison",
        "medical grouped boxplot with raw observations",
        x_title="Experimental condition",
        y_title="Normalized response ratio",
    ),
    ShowcaseCase(
        "medical-raincloud",
        "raincloud",
        "medical_raincloud.csv",
        "All deidentified teaching observations remain visible beside editable half-violin densities and compact mean plus or minus one SD summaries.",
        "distribution",
        "medical imaging Raincloud raw distribution",
    ),
    ShowcaseCase(
        "medical-shap",
        "shap_summary",
        "medical_shap_summary.csv",
        "Externally precomputed per-sample SHAP contributions preserve 576 exact horizontal values while supplied Mean absolute SHAP and group contributions remain linked, editable evidence.",
        "interpretability",
        "medical imaging composite SHAP beeswarm mean importance and grouped contribution",
        title_zh="复合 SHAP 特征贡献图",
    ),
)


def _run(command: list[str], *, log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if log_path is not None:
        log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-20:])
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command[:3])}\n{tail}")
    return completed


def build_case(
    case: ShowcaseCase,
    *,
    engine: Path,
    python: Path,
    render: bool,
    force: bool,
    rerender: bool,
) -> None:
    entry = GALLERY / case.id
    entry.mkdir(parents=True, exist_ok=True)
    plan_path = entry / "render-plan.json"
    understanding_path = entry / "semantic-understanding.json"
    confirmation_path = entry / "semantic-confirmation.json"
    source = DATA / case.data_file
    _run(
        [
            str(python),
            str(CLI),
            "understand",
            str(source),
            "--template-id",
            case.template_id,
            "--engine-home",
            str(engine),
            "--output",
            str(understanding_path),
        ],
        log_path=entry / "understand.log",
    )
    understanding = json.loads(understanding_path.read_text(encoding="utf-8"))
    gate = understanding.get("confirmation_gate", {})
    if not gate.get("can_confirm_now"):
        raise RuntimeError(
            f"{case.id} semantic proposal is blocked: "
            f"{gate.get('blocking_ambiguity_ids') or gate.get('uncertain_item_ids')}"
        )
    # These are deterministic, repository-owned synthetic teaching tables.
    # The build records the exact proposal-bound confirmation before planning;
    # user-owned data must still be confirmed interactively through the CLI.
    confirmation_path.write_text(
        json.dumps(
            gate["confirmation_payload_template"],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    plan_command = [
        str(python),
        str(CLI),
        "plan",
        str(source),
        "--template-id",
        case.template_id,
        "--claim",
        case.claim,
        "--evidence-role",
        case.evidence_role,
        "--intent",
        case.intent,
        "--engine-home",
        str(engine),
        "--semantic-confirmation-json",
        str(confirmation_path),
        "--output",
        str(plan_path),
    ]
    if case.x_title is not None:
        plan_command.extend(("--x-title", case.x_title))
    if case.y_title is not None:
        plan_command.extend(("--y-title", case.y_title))
    _run(
        plan_command,
        log_path=entry / "plan.log",
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not plan.get("can_render"):
        raise RuntimeError(f"{case.id} plan is blocked: {plan.get('blocked_reasons')}")
    if not render:
        print(f"PLAN OK  {case.id}", flush=True)
        return

    output = entry / "origin-output"
    verification_path = entry / "verification.json"
    if force and output.exists():
        resolved_output = output.resolve()
        if not resolved_output.is_relative_to(GALLERY.resolve()):
            raise RuntimeError(f"Refusing to remove output outside gallery: {resolved_output}")
        shutil.rmtree(resolved_output)
    reusable_outputs = sorted(
        (
            candidate
            for candidate in (output, *entry.glob("origin-output_*"))
            if (candidate / "result.opju").is_file()
        ),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    if not rerender:
        for candidate in reusable_outputs:
            _run(
                [
                    str(python),
                    str(CLI),
                    "verify",
                    str(candidate),
                    "--output",
                    str(verification_path),
                ],
                log_path=entry / "verify.log",
            )
            existing_verification = json.loads(verification_path.read_text(encoding="utf-8"))
            if existing_verification.get("programmatic_pass"):
                print(f"SKIP     {case.id} (verified Origin output: {candidate.name})", flush=True)
                return
    print(f"RENDER   {case.id}", flush=True)
    completed = _run(
        [
            str(python),
            str(CLI),
            "render",
            str(plan_path),
            "--engine-home",
            str(engine),
            "--python",
            str(python),
            "--output-dir",
            str(output),
            "--close-origin",
        ],
        log_path=entry / "render.log",
    )
    actual_output = output
    for line in reversed(completed.stdout.splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "done" and event.get("output_dir"):
            actual_output = Path(event["output_dir"]).resolve()
            break
    _run(
        [
            str(python),
            str(CLI),
            "verify",
            str(actual_output),
            "--output",
            str(verification_path),
        ],
        log_path=entry / "verify.log",
    )
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if not verification.get("programmatic_pass"):
        raise RuntimeError(f"{case.id} failed programmatic verification")
    print(f"PASS     {case.id}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-home", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="Create a new suffixed Origin output without deleting prior verified outputs.",
    )
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    engine = Path(args.engine_home).resolve()
    python = Path(args.python).resolve()
    selected = [case for case in CASES if not args.only or case.id in set(args.only)]
    for case in selected:
        build_case(
            case,
            engine=engine,
            python=python,
            render=args.render,
            force=args.force,
            rerender=args.rerender,
        )
    print(f"Completed {len(selected)} showcase case(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
