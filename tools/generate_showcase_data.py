"""Generate deterministic, neutral teaching tables for the EditaPlot gallery."""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "examples" / "gallery"


def _write(name: str, headers: list[str], rows: Iterable[Iterable[object]]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)


def _gaussian(x: float, center: float, width: float, amplitude: float) -> float:
    return amplitude * math.exp(-0.5 * ((x - center) / width) ** 2)


def generate_xps() -> None:
    rows = []
    for index in range(201):
        energy = 292.0 - 0.05 * index
        background = 1180.0 + 24.0 * (292.0 - energy)
        peak_cc = _gaussian(energy, 284.8, 0.62, 4300.0)
        peak_co = _gaussian(energy, 286.35, 0.78, 1850.0)
        peak_oco = _gaussian(energy, 288.75, 0.72, 1050.0)
        envelope = background + peak_cc + peak_co + peak_oco
        residual = 42.0 * math.sin(index * 0.43) + 18.0 * math.sin(index * 1.17)
        raw = envelope + residual
        rows.append(
            (
                f"{energy:.2f}",
                f"{raw:.3f}",
                f"{background:.3f}",
                f"{envelope:.3f}",
                f"{peak_cc:.3f}",
                f"{peak_co:.3f}",
                f"{peak_oco:.3f}",
                f"{residual:.3f}",
            )
        )
    _write(
        "xps_fit.csv",
        [
            "Binding Energy (eV)",
            "Raw Counts",
            "Background",
            "Fit Envelope",
            "Peak C-C",
            "Peak C-O",
            "Peak O-C=O",
            "Residual",
        ],
        rows,
    )


def generate_xrd() -> None:
    rows = []
    centers = (24.8, 31.7, 45.2, 59.8, 68.4)
    for index in range(351):
        angle = 10.0 + index * 0.2
        values = []
        for series_index in range(3):
            baseline = 88.0 + 5.0 * series_index + 8.0 * math.sin(angle * 0.13 + series_index)
            intensity = baseline
            for peak_index, center in enumerate(centers):
                shifted = center + (series_index - 1) * (0.12 + 0.03 * peak_index)
                width = 0.40 + 0.08 * peak_index + 0.04 * series_index
                amplitude = (430.0 - 48.0 * peak_index) * (0.88 + 0.09 * series_index)
                intensity += _gaussian(angle, shifted, width, amplitude)
            intensity += 5.0 * math.sin(index * 0.71 + series_index * 1.3)
            values.append(f"{intensity:.3f}")
        rows.append((f"{angle:.2f}", *values))
    _write(
        "xrd_multi.csv",
        ["2Theta (deg)", "Profile A Intensity", "Profile B Intensity", "Profile C Intensity"],
        rows,
    )


def generate_eis() -> None:
    rows = []
    for index in range(61):
        theta = math.pi * index / 60.0
        real = 2.0 + 12.5 * (1.0 - math.cos(theta))
        imag = -(10.8 * math.sin(theta) + 0.65 * math.sin(2.0 * theta))
        rows.append((f"{real:.4f}", f"{imag:.4f}"))
    _write("eis_nyquist.csv", ["Zreal (ohm)", "Zimag (ohm)"], rows)


def generate_cv() -> None:
    forward = [-0.50 + index * 0.01 for index in range(131)]
    reverse = [0.80 - index * 0.01 for index in range(131)]
    rows = []
    for branch, potentials in ((1, forward), (-1, reverse)):
        for index, potential in enumerate(potentials):
            oxidation = _gaussian(potential, 0.33, 0.11, 1.85)
            reduction = _gaussian(potential, 0.04, 0.13, 1.45)
            cycle1 = 0.28 * potential + oxidation if branch == 1 else 0.28 * potential - reduction
            cycle2 = 1.08 * cycle1 + 0.035 * math.sin(index * 0.31)
            rows.append((f"{potential:.3f}", f"{cycle1:.4f}", f"{cycle2:.4f}"))
    _write("cv_cycles.csv", ["Potential (V)", "Cycle 1 (mA)", "Cycle 2 (mA)"], rows)


def generate_lsv() -> None:
    rows = []
    for index in range(111):
        potential = -0.20 + index * 0.01
        base = 0.015 + 5.1 / (1.0 + math.exp(-(potential - 0.47) / 0.085))
        sample_a = base + 0.035 * math.sin(index * 0.27)
        sample_b = 0.88 * base + 0.025 * math.sin(index * 0.31 + 0.8)
        rows.append((f"{potential:.3f}", f"{sample_a:.4f}", f"{sample_b:.4f}"))
    _write(
        "lsv_multi.csv",
        ["Potential (V)", "Sample A (mA cm-2)", "Sample B (mA cm-2)"],
        rows,
    )


def generate_xas() -> None:
    rows = []
    for index in range(181):
        energy = 7080.0 + index * 0.75
        edge_a = 0.12 + 1.02 / (1.0 + math.exp(-(energy - 7119.0) / 2.8))
        edge_b = 0.10 + 0.98 / (1.0 + math.exp(-(energy - 7121.5) / 3.2))
        oscillation = math.exp(-max(0.0, energy - 7125.0) / 75.0)
        signal_a = edge_a + (0.065 * math.sin((energy - 7124.0) / 4.7) * oscillation if energy > 7124 else 0)
        signal_b = edge_b + (0.052 * math.sin((energy - 7126.0) / 5.2) * oscillation if energy > 7126 else 0)
        rows.append((f"{energy:.2f}", f"{signal_a:.5f}", f"{signal_b:.5f}"))
    _write("xas_profiles.csv", ["Energy (eV)", "Profile A mu(E)", "Profile B mu(E)"], rows)


def generate_scatter() -> None:
    rows = []
    for index in range(1, 241):
        x = index / 12.0
        y_a = 1.8 + 0.62 * x + 1.05 * math.sin(index * 0.47)
        y_b = 4.1 + 0.43 * x + 0.90 * math.cos(index * 0.39 + 0.4)
        y_c = 2.9 + 0.53 * x + 0.82 * math.sin(index * 0.31 + 1.2)
        rows.append((f"{x:.3f}", f"{y_a:.4f}", f"{y_b:.4f}", f"{y_c:.4f}"))
    _write("scatter_dense.csv", ["Independent variable", "Response A", "Response B", "Response C"], rows)


def generate_line_error() -> None:
    rows = []
    for index in range(13):
        time = index * 2
        control = 1.0 + 0.065 * time + 0.06 * math.sin(index * 0.6)
        treatment = 1.0 + 0.13 * time + 0.13 * math.sin(index * 0.45)
        rows.append(
            (
                time,
                f"{control:.4f}",
                f"{0.07 + 0.006 * index:.4f}",
                f"{treatment:.4f}",
                f"{0.05 + 0.005 * index:.4f}",
            )
        )
    _write(
        "line_error.csv",
        ["Time (h)", "Control", "Control_SD", "Treatment", "Treatment_SEM"],
        rows,
    )


def generate_categories() -> None:
    bar_rows = [
        ("Control", 18.4, 1.1, 22.6, 1.3, 25.2, 1.4),
        ("Low", 20.1, 1.2, 26.3, 1.5, 29.8, 1.6),
        ("Medium", 23.0, 1.4, 30.2, 1.7, 35.0, 1.9),
        ("High", 24.7, 1.5, 34.1, 1.9, 39.4, 2.1),
        ("Recovery", 22.2, 1.3, 31.5, 1.6, 36.8, 1.8),
    ]
    _write(
        "bar_grouped_error.csv",
        [
            "Condition",
            "Reference",
            "Reference_SD",
            "Treatment A",
            "Treatment A_SD",
            "Treatment B",
            "Treatment B_SD",
        ],
        bar_rows,
    )

    _write(
        "horizontal_long_labels.csv",
        ["Category", "Performance", "Performance_SEM"],
        [
            ("Full model", 0.91, 0.012),
            ("Without feature alignment", 0.84, 0.016),
            ("Without consistency loss", 0.81, 0.018),
            ("Without adaptive weighting", 0.78, 0.020),
            ("Single-scale encoder", 0.74, 0.019),
            ("Baseline backbone", 0.69, 0.022),
        ],
    )

    composition_rows = [
        ("Cohort A", 36, 29, 22, 13),
        ("Cohort B", 30, 32, 25, 13),
        ("Cohort C", 25, 35, 27, 13),
        ("Cohort D", 21, 38, 29, 12),
        ("Cohort E", 18, 40, 31, 11),
    ]
    _write(
        "percent_composition.csv",
        ["Category", "Component A", "Component B", "Component C", "Component D"],
        composition_rows,
    )
    _write(
        "stacked_composition.csv",
        ["Category", "Phase A", "Phase B", "Phase C", "Phase D", "Total_SD"],
        [
            ("Sample 1", 18, 11, 7, 4, 2.1),
            ("Sample 2", 20, 14, 9, 5, 2.4),
            ("Sample 3", 16, 17, 12, 6, 2.3),
            ("Sample 4", 23, 15, 10, 8, 2.8),
            ("Sample 5", 21, 18, 13, 7, 2.5),
        ],
    )
    _write(
        "pie_five_parts.csv",
        ["Category", "Value"],
        [("Part A", 34), ("Part B", 27), ("Part C", 18), ("Part D", 13), ("Part E", 8)],
    )
    _write(
        "sankey_four_stage.csv",
        ["Source", "Target", "Value"],
        [
            ("Input A", "Curated A", 32),
            ("Input A", "Curated B", 16),
            ("Input B", "Curated A", 14),
            ("Input B", "Curated C", 32),
            ("Input C", "Curated B", 28),
            ("Input C", "Curated C", 14),
            ("Curated A", "Model X", 28),
            ("Curated A", "Model Y", 18),
            ("Curated B", "Model X", 12),
            ("Curated B", "Model Z", 32),
            ("Curated C", "Model Y", 24),
            ("Curated C", "Model Z", 22),
            ("Model X", "Outcome P", 28),
            ("Model X", "Outcome Q", 12),
            ("Model Y", "Outcome P", 10),
            ("Model Y", "Outcome R", 32),
            ("Model Z", "Outcome Q", 26),
            ("Model Z", "Outcome R", 28),
        ],
    )


def generate_multivariate() -> None:
    trend_rows = []
    for step in range(1, 13):
        baseline = 0.39 + 0.31 * (1.0 - math.exp(-step / 4.7))
        augmented = 0.41 + 0.40 * (1.0 - math.exp(-step / 4.2))
        proposed = 0.43 + 0.47 * (1.0 - math.exp(-step / 3.8))
        trend_rows.append((step, f"{baseline:.4f}", f"{augmented:.4f}", f"{proposed:.4f}"))
    _write(
        "trend_progression.csv",
        ["Step", "Baseline", "Augmented", "Proposed"],
        trend_rows,
    )
    _write(
        "radar_multimetric.csv",
        ["Metric", "Baseline", "Enhanced", "Proposed"],
        [
            ("Accuracy", 0.72, 0.82, 0.88),
            ("Robustness", 0.68, 0.77, 0.83),
            ("Efficiency", 0.81, 0.79, 0.77),
            ("Recall", 0.70, 0.80, 0.86),
            ("Calibration", 0.66, 0.75, 0.80),
        ],
    )
    _write(
        "heatmap_results.csv",
        ["Dataset", "Baseline", "Augmented", "Fine-tuned", "Ensemble", "Proposed"],
        [
            ("Dataset A", 0.58, 0.66, 0.73, 0.79, 0.86),
            ("Dataset B", 0.61, 0.69, 0.76, 0.82, 0.89),
            ("Dataset C", 0.54, 0.64, 0.71, 0.78, 0.85),
            ("Dataset D", 0.63, 0.72, 0.78, 0.84, 0.91),
            ("Dataset E", 0.56, 0.67, 0.75, 0.81, 0.88),
            ("Dataset F", 0.60, 0.70, 0.77, 0.83, 0.90),
        ],
    )


def generate_evidence_plots() -> None:
    raw_rows = []
    for index in range(14):
        reference = 0.83 + 0.045 * math.sin(index * 1.31) + 0.018 * math.cos(index * 0.47)
        treatment_a = 1.01 + 0.060 * math.sin(index * 1.09 + 0.4) + 0.022 * math.cos(index * 0.53)
        treatment_b = 1.17 + 0.072 * math.sin(index * 0.91 + 0.8) + 0.028 * math.cos(index * 0.61)
        raw_rows.append((f"{reference:.4f}", f"{treatment_a:.4f}", f"{treatment_b:.4f}"))
    _write("raw_observations.csv", ["Reference", "Treatment A", "Treatment B"], raw_rows)

    violin_rows = []
    for index in range(32):
        reference = 0.84 + 0.060 * math.sin(index * 1.37) + 0.020 * math.cos(index * 0.43)
        treatment_a = 1.04 + 0.078 * math.sin(index * 1.11 + 0.4) + 0.026 * math.cos(index * 0.51)
        treatment_b = 1.20 + 0.090 * math.sin(index * 0.93 + 0.8) + 0.034 * math.cos(index * 0.61)
        violin_rows.append((f"{reference:.4f}", f"{treatment_a:.4f}", f"{treatment_b:.4f}"))
    _write("violin_distributions.csv", ["Reference", "Treatment A", "Treatment B"], violin_rows)

    histogram_rows = []
    for index in range(90):
        value = (
            4.8
            + 0.75 * math.sin(index * 0.71)
            + 0.38 * math.sin(index * 1.93 + 0.4)
            + (0.42 if index % 9 == 0 else 0.0)
        )
        histogram_rows.append((f"{value:.5f}",))
    _write("histogram_values.csv", ["Observed value"], histogram_rows)

    _write(
        "forest_intervals.csv",
        ["Label", "Estimate", "CI Low", "CI High", "Reference"],
        [
            ("Reference method", -0.18, -0.32, -0.04, 0.0),
            ("Cohort A", 0.07, -0.10, 0.24, 0.0),
            ("Cohort B", 0.24, 0.12, 0.36, 0.0),
            ("Cohort C", 0.39, 0.20, 0.58, 0.0),
            ("Cohort D", 0.51, 0.35, 0.67, 0.0),
            ("Cohort E", 0.66, 0.45, 0.87, 0.0),
        ],
    )

    _write(
        "bubble_indexed_size.csv",
        ["Exposure", "Response", "Sample size"],
        [
            (0.8, 1.1, 8),
            (1.4, 1.8, 11),
            (2.1, 1.5, 9),
            (2.8, 2.6, 15),
            (3.6, 3.0, 13),
            (4.5, 3.8, 18),
            (5.3, 3.4, 12),
            (6.2, 4.5, 20),
            (7.1, 5.1, 17),
            (8.0, 5.6, 22),
        ],
    )


def generate_medical_distribution_interpretability() -> None:
    raincloud_rows = []
    for index in range(28):
        baseline = 0.815 + 0.027 * math.sin(index * 1.17) + 0.012 * math.cos(index * 0.43)
        attention = 0.851 + 0.025 * math.sin(index * 1.03 + 0.6) + 0.011 * math.cos(index * 0.51)
        proposed = 0.895 + 0.023 * math.sin(index * 0.91 + 1.0) + 0.010 * math.cos(index * 0.57)
        raincloud_rows.append((f"{baseline:.4f}", f"{attention:.4f}", f"{proposed:.4f}"))
    _write(
        "medical_raincloud.csv",
        ["Baseline U-Net", "Attention U-Net", "Proposed model"],
        raincloud_rows,
    )

    feature_specs = (
        ("Tumor volume", 8.0, 46.0, 0.92, 0.3),
        ("ADC mean", 0.72, 1.38, -0.84, 1.0),
        ("Texture entropy", 3.8, 6.3, 0.66, 1.7),
        ("Enhancement ratio", 0.78, 1.90, 0.52, 2.3),
        ("Age", 35.0, 76.0, 0.30, 2.9),
    )
    shap_rows = []
    for feature_index, (feature, lower, upper, effect, phase) in enumerate(feature_specs):
        for sample_index in range(28):
            unit = (math.sin(sample_index * (0.71 + feature_index * 0.035) + phase) + 1.0) / 2.0
            feature_value = lower + (upper - lower) * unit
            contribution = effect * (unit - 0.5) + 0.065 * math.sin(sample_index * 1.43 + feature_index * 0.8)
            shap_rows.append(
                (
                    feature,
                    f"{contribution:.4f}",
                    f"{feature_value:.4f}",
                    f"S{sample_index + 1:03d}",
                )
            )
    _write(
        "medical_shap_summary.csv",
        ["Feature", "SHAP value", "Feature value", "Sample ID"],
        shap_rows,
    )


def generate_pl_trpl() -> None:
    """Create neutral synthetic decay/fit pairs without copying a published material example."""
    series = (
        ("Reference film", 96.0, 0.022, 0.35),
        ("Blend A", 54.0, 0.026, 1.10),
        ("Blend B", 31.0, 0.030, 1.85),
    )
    headers = ["Time after excitation (ns)"]
    for label, lifetime, _noise, _phase in series:
        headers.extend(
            (
                f"{label} normalized PL ({lifetime:.1f} ns)",
                f"{label} normalized PL ({lifetime:.1f} ns) Fit",
            )
        )

    rows = []
    for time_ns in range(0, 101, 5):
        row: list[object] = [time_ns]
        for _label, lifetime, noise, phase in series:
            fitted = math.exp(-time_ns / lifetime)
            modulation = 1.0 + noise * math.sin(time_ns * 0.31 + phase)
            measured = max(fitted * modulation, 0.002)
            row.extend((f"{measured:.4f}", f"{fitted:.4f}"))
        rows.append(row)
    _write("pl_trpl.csv", headers, rows)


def main() -> None:
    generate_xps()
    generate_xrd()
    generate_eis()
    generate_cv()
    generate_lsv()
    generate_xas()
    generate_scatter()
    generate_line_error()
    generate_categories()
    generate_multivariate()
    generate_evidence_plots()
    generate_medical_distribution_interpretability()
    generate_pl_trpl()
    print(f"Generated showcase data in {OUTPUT}")


if __name__ == "__main__":
    main()
