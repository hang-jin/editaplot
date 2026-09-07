"""Generate deterministic teaching data, never recovered reference measurements."""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]


def build_rows():
    specs = (
        ("Vegetation index", "Surface cover", 1.28, -1),
        ("Road distance", "Human engineering", 0.58, 1),
        ("Slope", "Geomorphology", 0.49, -1),
        ("Lithology", "Geology", 0.45, 1),
        ("Aspect", "Geomorphology", 0.39, 1),
        ("Land cover", "Surface cover", 0.33, -1),
        ("River distance", "Hydrology", 0.30, -1),
        ("Fault distance", "Geology", 0.27, 1),
        ("Wetness index", "Hydrology", 0.23, 1),
        ("Curvature", "Geomorphology", 0.19, -1),
        ("Elevation", "Geomorphology", 0.15, 1),
        ("Soil", "Surface cover", 0.10, -1),
    )
    rows = []
    normal = NormalDist()
    for order, (feature, group, scale, sign) in enumerate(specs, 1):
        for i in range(120):
            z = normal.inv_cdf((i + 0.5) / 120)
            shap = scale * (z + 0.18 * math.sin(i * 1.73 + order))
            value = min(1, max(0, 0.5 + sign * z / 5 + 0.1 * math.sin(i * 0.81 + order)))
            rows.append(
                [feature, f"{shap:.7f}", f"{value:.7f}", group, f"DEMO{i + 1:03d}", order if i == 0 else ""]
            )
    return rows


def main():
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["Feature", "SHAP value", "Feature value", "Feature Group", "Sample ID", "Feature Order"])
    writer.writerows(build_rows())
    for path in (
        ROOT / "examples/gallery/shap_dashboard.csv",
        ROOT / "runtime/templates/shap_dashboard/example_standard.csv",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stream.getvalue(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
