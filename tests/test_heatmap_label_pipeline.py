"""Regression checks for source-bound heatmap label placement, not just font size."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "src"))

from origin_sciplot.origin_backend import categorical_renderer  # noqa: E402
from origin_sciplot.scientific_preview import _build_scientific_preview_figure  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    _scientific_plan_digest,
    prepare_scientific,
)


def _source(tmp_path: Path, size: int) -> Path:
    frame = pd.DataFrame(
        np.arange(size * size, dtype=float).reshape(size, size),
        columns=[f"Series {index + 1:02d}" for index in range(size)],
    )
    frame.insert(0, "Sample", [f"Dataset {index + 1:02d}" for index in range(size)])
    path = tmp_path / "matrix.csv"
    frame.to_csv(path, index=False)
    return path


def test_heatmap_layout_is_frozen_and_changing_gap_invalidates_approval(tmp_path: Path) -> None:
    preparation = prepare_scientific(_source(tmp_path, 30), "heatmap")
    layout = getattr(preparation.plot_spec, "heatmap_layout", None)
    assert layout is not None, "Heatmap source labels and physical clearance must be frozen in the plan"
    assert layout.y_display_labels[0] == "Dataset 01"
    assert layout.y_display_labels[-1] == "Dataset 30"
    changed_digest = _scientific_plan_digest(
        preparation,
        replace(preparation.plot_spec, heatmap_layout=replace(layout, y_label_gap_cm=0.35)),
    )
    assert changed_digest != preparation.plan_digest


@pytest.mark.parametrize("size", [4, 30, 40])
def test_preview_row_ink_has_frozen_clearance_from_frame(tmp_path: Path, size: int) -> None:
    preparation = prepare_scientific(_source(tmp_path, size), "heatmap")
    figure = _build_scientific_preview_figure(preparation)
    try:
        canvas = FigureCanvasAgg(figure)
        canvas.draw()
        renderer = canvas.get_renderer()
        axis = next(item for item in figure.axes if item.images)
        rows = [item for item in figure.texts if item.get_gid() == "heatmap-row-label"]
        assert rows, "Preview must consume the same page-anchored row labels as native Origin"
        assert rows[0].get_text() == "Dataset 01"
        assert rows[-1].get_text() == f"Dataset {size:02d}"
        style = preparation.plot_spec.display_plan.figure_style
        frame_left = axis.get_window_extent(renderer).x0
        physical_gap_px = 0.20 / style.page_width_cm * figure.bbox.width
        for text in rows:
            bbox = text.get_window_extent(renderer)
            assert bbox.x0 >= 0
            assert frame_left - bbox.x1 == pytest.approx(physical_gap_px, abs=0.05)
            source_index = int(text.get_text().split()[-1]) - 1
            row_center = axis.transData.transform((0, source_index))[1]
            assert (bbox.y0 + bbox.y1) / 2 == pytest.approx(row_center, abs=0.05)
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    ("template_id", "source_sha", "digest"),
    [
        ("bar", "61f78697beeb63592dc823350a9dc9e59478a9744a599cf6383e69905900e46c",
         "65cd823450b05ed1b5a7bfafb4630c89a401b53b80154cfa022493bb55cafe94"),
        ("confusion_matrix", "02bcc22d8ebb8bdb4c475f533f4ca078d4e3a0fb94e8c6f9bd6e845b6a2ee62c",
         "f097077c94b8a36ea58eef17eb86c7d8852f3b1538e5a889e8ec8eebf2001795"),
        ("radar", "e6e2618ed657ae7714c6d88bb28724a3f68d13da17877f079c845b5e2b266932",
         "231420edcaa824ac5a9059cb8696279d057a2708226ca8136e0f8fcc018ad651"),
    ],
)
def test_unrelated_approved_plans_keep_their_digest(template_id: str, source_sha: str, digest: str) -> None:
    preparation = prepare_scientific(
        ROOT / "runtime/templates" / template_id / "example_standard.csv", template_id,
    )
    assert preparation.source_sha256 == source_sha
    assert preparation.plan_digest == digest
    assert getattr(preparation.plot_spec, "heatmap_layout", None) is None


class _MeasuredLabel:
    """Only the documented label properties consumed by native readback."""

    def __init__(self, text: str, left: float, top: float) -> None:
        self.text = text
        self.properties = {
            "left": left, "top": top, "width": 40.0, "height": 10.0,
            "fsize": 17.0, "font": 2, "rotate": 0.0,
            "attach": 1, "showframe": 0, "show": 1, "bold": 0, "link": 0,
        }

    def get_float(self, prop: str) -> float:
        return float(self.properties[prop])

    def get_int(self, prop: str) -> int:
        return int(self.properties[prop])


class _ReadbackLayer:
    def __init__(self, labels: dict[str, _MeasuredLabel]) -> None:
        self.labels = labels
        self.visibility = {"y.showLabels": 0, "y.showlabel": 0, "y.label.show": 0}

    def label(self, name: str) -> _MeasuredLabel | None:
        return self.labels.get(name)

    def get_int(self, prop: str) -> int:
        return self.visibility[prop]


class _ReadbackOrigin:
    def lt_float(self, expression: str) -> float:
        return {"page.width": 1000.0, "page.height": 1000.0, "font(Arial)": 2.0}[expression]


def test_native_readback_accepts_measured_clearance_and_source_order(tmp_path: Path) -> None:
    preparation = prepare_scientific(_source(tmp_path, 4), "heatmap")
    style = replace(preparation.plot_spec.display_plan.figure_style, page_width_cm=20.0,
                    layer_left_percent=20.0, layer_top_percent=10.0, layer_height_percent=80.0)
    labels = {f"HeatmapRow{i + 1}": _MeasuredLabel(f"Dataset {i + 1:02d}", 150.0, 195.0 + i * 200)
              for i in range(4)}
    state = categorical_renderer.verify_heatmap_row_labels(
        _ReadbackOrigin(), _ReadbackLayer(labels), layout=preparation.plot_spec.heatmap_layout, style=style,
        geometry={"left_percent": 20.0, "top_percent": 10.0, "height_percent": 80.0},
    )
    assert [item["source_index"] for item in state["labels"]] == [0, 1, 2, 3]
    assert all(item["gap_cm"] == pytest.approx(0.20) for item in state["labels"])


@pytest.mark.parametrize(
    ("property_name", "bad_value"),
    [("left", 999.0), ("left", float("nan")), ("top", 95.0), ("width", 0.0),
     ("font", 3), ("fsize", 12.0), ("attach", 0), ("showframe", 1),
     ("show", 0), ("rotate", 90.0), ("bold", 1), ("link", 1), ("text", "Wrong source row")],
)
def test_native_readback_rejects_changed_row_objects(
    tmp_path: Path, property_name: str, bad_value: object,
) -> None:
    preparation = prepare_scientific(_source(tmp_path, 4), "heatmap")
    style = preparation.plot_spec.display_plan.figure_style
    # Literal page-unit positions for a 20 cm page, left=20%, top=10%, height=80%.
    labels = {f"HeatmapRow{i + 1}": _MeasuredLabel(f"Dataset {i + 1:02d}", 150.0, 195.0 + i * 200)
              for i in range(4)}
    obj = labels["HeatmapRow1"]
    if property_name == "text":
        obj.text = str(bad_value)
    else:
        obj.properties[property_name] = bad_value
    style = replace(style, page_width_cm=20.0, layer_left_percent=20.0,
                    layer_top_percent=10.0, layer_height_percent=80.0)
    with pytest.raises(RuntimeError):
        categorical_renderer.verify_heatmap_row_labels(
            _ReadbackOrigin(), _ReadbackLayer(labels),
            layout=preparation.plot_spec.heatmap_layout, style=style,
            geometry={"left_percent": 20.0, "top_percent": 10.0, "height_percent": 80.0},
        )


def test_native_readback_rejects_restored_automatic_y_labels(tmp_path: Path) -> None:
    preparation = prepare_scientific(_source(tmp_path, 4), "heatmap")
    layer = _ReadbackLayer({})
    layer.visibility["y.showLabels"] = 1
    with pytest.raises(RuntimeError):
        categorical_renderer.verify_heatmap_row_labels(
            _ReadbackOrigin(), layer, layout=preparation.plot_spec.heatmap_layout,
            style=preparation.plot_spec.display_plan.figure_style,
            geometry={"left_percent": 20.0, "top_percent": 10.0, "height_percent": 80.0},
        )
