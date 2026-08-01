from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.colors as mcolors
import numpy as np
import pytest
from matplotlib.collections import PathCollection

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.base_style_contract import (  # noqa: E402
    origin_points_to_preview_points,
)
from origin_sciplot.xps_preview import _build_xps_preview_figure  # noqa: E402
from origin_sciplot.xps_visual_style import apply_xps_visual_style  # noqa: E402
from origin_sciplot.xps_workflow import XpsPreparation, prepare_xps  # noqa: E402

ADAPTIVE_SOURCE = ROOT / "runtime" / "templates" / "xps_adaptive" / "example_standard.csv"
FIXED_SOURCE = ROOT / "runtime" / "templates" / "xps_c1s_fit" / "example_standard.csv"
PREVIEW_WIDTH_IN = 7.2
EXACT_RAW_COLOR = "#2457A7"


@pytest.fixture(
    params=(ADAPTIVE_SOURCE, FIXED_SOURCE),
    ids=("adaptive", "fixed-c1s"),
)
def preparation(request: pytest.FixtureRequest) -> XpsPreparation:
    return prepare_xps(Path(request.param))


def _line_by_label(axis: object, label: str) -> object:
    matches = [line for line in axis.lines if line.get_label() == label]
    assert len(matches) == 1
    return matches[0]


def _raw_scatter(axis: object, label: str) -> PathCollection:
    matches = [
        collection
        for collection in axis.collections
        if isinstance(collection, PathCollection) and collection.get_label() == label
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_scientific_axis_contract(preparation: XpsPreparation, axis: object) -> None:
    axis_plan = preparation.plot_spec.axis
    assert axis.get_xlim() == pytest.approx((axis_plan.display_from_ev, axis_plan.display_to_ev))
    assert axis.get_xlim()[0] > axis.get_xlim()[1]
    assert axis.get_xlabel() == axis_plan.x_title
    assert axis_plan.transform == "negate"
    assert not any(line.get_visible() for line in axis.get_xgridlines())
    assert not any(line.get_visible() for line in axis.get_ygridlines())

    if preparation.plot_spec.visual_profile == "fixed_c1s_publication":
        assert axis.get_ylabel() == "Intensity (a.u.)"
        assert len(axis.get_yticks()) == 0
        assert axis.get_yticklabels() == []
    else:
        assert axis.get_ylabel() == "Counts / s"
        assert axis.get_yticks().size >= 3
        assert all(label.get_visible() for label in axis.get_yticklabels())


def test_default_xps_preview_artist_contract_does_not_regress(
    preparation: XpsPreparation,
) -> None:
    figure = _build_xps_preview_figure(preparation)
    axis = figure.axes[0]
    visual = preparation.visual_contract
    style = visual.figure_style

    assert figure.get_size_inches()[0] == pytest.approx(PREVIEW_WIDTH_IN)
    assert figure.get_size_inches()[1] == pytest.approx(
        PREVIEW_WIDTH_IN * style.page_height_cm / style.page_width_cm
    )
    expected_line_width = origin_points_to_preview_points(
        style.plot_line_width_pt,
        PREVIEW_WIDTH_IN,
        style,
    )
    expected_frame_width = origin_points_to_preview_points(
        style.frame_line_width_pt,
        PREVIEW_WIDTH_IN,
        style,
    )
    assert axis.lines
    assert all(line.get_linewidth() == pytest.approx(expected_line_width) for line in axis.lines)
    assert all(spine.get_visible() for spine in axis.spines.values())
    assert all(spine.get_linewidth() == pytest.approx(expected_frame_width) for spine in axis.spines.values())

    raw_spec = next(spec for spec in preparation.plot_spec.series if spec.role == "raw")
    if preparation.plot_spec.visual_profile == "fixed_c1s_publication":
        raw = _raw_scatter(axis, raw_spec.label)
        assert raw.get_facecolors().size == 0
        assert raw.get_edgecolors()[0] == pytest.approx(mcolors.to_rgba(visual.raw_color))
        expected_fill_alpha = 0.55
        assert len(axis.images) == len(preparation.roles.components)
    else:
        raw = _line_by_label(axis, raw_spec.label)
        assert mcolors.to_rgba(raw.get_color()) == pytest.approx(mcolors.to_rgba(visual.raw_color))
        assert raw.get_alpha() == pytest.approx(0.95)
        expected_fill_alpha = 0.42
        assert len(axis.images) == len(preparation.roles.components) + 1

    observed_fill_alpha = max(float(np.max(image.get_array()[..., 3])) for image in axis.images)
    assert observed_fill_alpha == pytest.approx(expected_fill_alpha)
    legend = axis.get_legend()
    assert legend is not None
    assert legend.get_frame_on() is False
    _assert_scientific_axis_contract(preparation, axis)


def test_exact_xps_preview_style_reaches_artists_without_changing_science(
    preparation: XpsPreparation,
) -> None:
    raw_column = preparation.roles.raw
    assert raw_column is not None
    application = apply_xps_visual_style(
        preparation,
        {
            "series_colors": {raw_column: EXACT_RAW_COLOR},
            "line_width_pt": 3.2,
            "fill_transparency_percent": 68.0,
            "page_size_cm": {"width": 19.0, "height": 19.0},
            "legend_visible": False,
        },
        source="explicit_user",
    )
    styled = application.preparation
    figure = _build_xps_preview_figure(styled)
    axis = figure.axes[0]
    style = styled.visual_contract.figure_style

    assert styled.plot_spec == preparation.plot_spec
    assert styled.roles == preparation.roles
    assert styled.source_sha256 == preparation.source_sha256
    assert figure.get_size_inches() == pytest.approx((PREVIEW_WIDTH_IN, PREVIEW_WIDTH_IN))
    expected_line_width = origin_points_to_preview_points(
        3.2,
        PREVIEW_WIDTH_IN,
        style,
    )
    assert all(line.get_linewidth() == pytest.approx(expected_line_width) for line in axis.lines)

    raw_spec = next(spec for spec in styled.plot_spec.series if spec.role == "raw")
    if styled.plot_spec.visual_profile == "fixed_c1s_publication":
        raw = _raw_scatter(axis, raw_spec.label)
        assert raw.get_edgecolors()[0] == pytest.approx(mcolors.to_rgba(EXACT_RAW_COLOR))
        base_fill_alpha = 0.55
    else:
        raw = _line_by_label(axis, raw_spec.label)
        assert mcolors.to_rgba(raw.get_color()) == pytest.approx(mcolors.to_rgba(EXACT_RAW_COLOR))
        base_fill_alpha = 0.42

    observed_fill_alpha = max(float(np.max(image.get_array()[..., 3])) for image in axis.images)
    assert observed_fill_alpha == pytest.approx(base_fill_alpha * (1.0 - 0.68))
    assert axis.get_legend() is None
    _assert_scientific_axis_contract(styled, axis)


def test_xps_preview_supports_outside_right_framed_legend(
    preparation: XpsPreparation,
) -> None:
    baseline = _build_xps_preview_figure(preparation)
    baseline_axis = baseline.axes[0]
    application = apply_xps_visual_style(
        preparation,
        {
            "legend_position": "outside_right",
            "legend_frame": True,
        },
        source="explicit_user",
    )
    styled = application.preparation
    figure = _build_xps_preview_figure(styled)
    axis = figure.axes[0]
    legend = axis.get_legend()

    assert legend is not None
    assert legend.get_frame_on() is True
    legend_anchor = legend.get_bbox_to_anchor().transformed(axis.transAxes.inverted())
    assert legend_anchor.bounds == pytest.approx((1.02, 1.0, 0.0, 0.0))
    assert axis.get_position().x1 == pytest.approx(0.78)
    assert axis.get_position().width < baseline_axis.get_position().width
    if styled.plot_spec.visual_profile == "adaptive_counts":
        expected_labels = [spec.label for spec in styled.plot_spec.series if spec.role != "residual"]
    else:
        expected_labels = [
            "Raw",
            "Envelope",
            "Background",
            "C-C / C=C",
            "C-O",
            "C=O",
            "O-C=O",
        ]
    assert [text.get_text() for text in legend.get_texts()] == expected_labels
    _assert_scientific_axis_contract(styled, axis)
