from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from origin_sciplot.origin_backend.safe_errors import OriginDrawError
from origin_sciplot.origin_backend.scientific_renderer import (
    ORIGIN_PHASE_TICK_SYMBOL_KIND,
    _prepare_origin_table,
)
from origin_sciplot.scientific_preview import _build_scientific_preview_figure
from origin_sciplot.scientific_visual import resolve_adaptive_style
from origin_sciplot.scientific_workflow import (
    ScientificAxisPlan,
    ScientificDisplayPlan,
    ScientificPlotSpec,
    ScientificPreparation,
    ScientificSeries,
)


def _rietveld_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "2Theta": np.linspace(20.0, 80.0, 9),
            "Observed": [98.0, 132.0, 421.0, 210.0, 172.0, 318.0, 165.0, 121.0, 102.0],
            "Calculated": [100.0, 129.0, 416.0, 214.0, 170.0, 313.0, 169.0, 119.0, 103.0],
            "Background": [82.0, 84.0, 88.0, 91.0, 94.0, 96.0, 98.0, 100.0, 101.0],
            "Diff": [-2.0, 3.0, 5.0, -4.0, 2.0, 5.0, -4.0, 2.0, -1.0],
            "Phase alpha": [24.0, 35.0, 47.0, 61.0, np.nan, np.nan, np.nan, np.nan, np.nan],
            "Phase beta": [29.0, 42.0, 55.0, 72.0, np.nan, np.nan, np.nan, np.nan, np.nan],
        }
    )


def _preparation(
    frame: pd.DataFrame,
    *,
    phase_tick_columns: tuple[str, ...] = ("Phase alpha", "Phase beta"),
) -> ScientificPreparation:
    series = (
        ScientificSeries("Observed", "Observed", series_role="observed"),
        ScientificSeries("Calculated", "Calculated", series_role="calculated"),
        ScientificSeries("Background", "Background", series_role="background"),
        ScientificSeries("Diff", "Difference", series_role="difference"),
    )
    style = resolve_adaptive_style(
        template_id="xrd",
        plot_kind="rietveld_refinement",
        row_count=len(frame),
        series_count=len(series),
    )
    spec = ScientificPlotSpec(
        plot_kind="rietveld_refinement",
        plot_mode="rietveld_refinement",
        x_column="2Theta",
        category_column=None,
        series=series,
        x_title=r"2θ (°)",
        y_title="Intensity (a.u.)",
        y2_title=None,
        x_scale="linear",
        y_scale="linear",
        display_transform="identity",
        display_plan=ScientificDisplayPlan(
            marker_size_pt=5.2,
            bar_group_span=0.8,
            bar_inner_width=0.72,
            figure_style=style,
        ),
        axis_plan=ScientificAxisPlan(
            x_from=20.0,
            x_to=80.0,
            x_step=10.0,
            y_from=-20.0,
            y_to=460.0,
            y_step=100.0,
        ),
        phase_tick_columns=phase_tick_columns,
        source_profile="gsas_ii_publication_csv",
    )
    assignments = (
        ("2Theta", "x"),
        ("Observed", "observed"),
        ("Calculated", "calculated"),
        ("Background", "background"),
        ("Diff", "difference"),
        *(tuple((column, "phase_tick") for column in phase_tick_columns)),
    )
    return ScientificPreparation(
        template_id="xrd",
        source_path="unused.csv",
        source_sha256="0" * 64,
        source_size_bytes=0,
        source_format="csv",
        source_sheet=None,
        source_columns=tuple(str(column) for column in frame.columns),
        row_count=len(frame),
        ignored_empty_rows=0,
        assignments=assignments,
        plot_spec=spec,
        confidence=1.0,
        requires_confirmation=False,
        confirmation_reasons=(),
        warnings=(),
        mapping_confirmed=True,
        plan_digest="1" * 64,
    )


def test_rietveld_origin_plan_uses_semantic_plot_types_and_direct_difference() -> None:
    frame = _rietveld_frame()
    table = _prepare_origin_table(frame, _preparation(frame))
    plans = {item.series_role: item for item in table.series if not item.is_phase_tick}

    assert plans["observed"].plot_type == "s"
    assert plans["observed"].symbol_kind == 2
    assert plans["calculated"].plot_type == "l"
    assert plans["background"].plot_type == "l"
    assert plans["difference"].plot_type == "l"
    assert plans["difference"].plot_column == "Diff"
    assert np.array_equal(
        table.frame["Diff"].to_numpy(),
        frame["Diff"].to_numpy(),
        equal_nan=True,
    )
    assert not any("Diff" in helper for helper in table.helper_columns)


def test_rietveld_phase_ticks_use_source_x_and_only_helper_y_lanes() -> None:
    frame = _rietveld_frame()
    table = _prepare_origin_table(frame, _preparation(frame))
    phase_plans = [item for item in table.series if item.is_phase_tick]

    assert table.phase_tick_columns == ("Phase alpha", "Phase beta")
    assert len(phase_plans) == 2
    assert set(table.helper_columns) == {item.plot_column for item in phase_plans}
    for item in phase_plans:
        assert item.x_column == item.source_column
        assert item.plot_column != item.source_column
        assert item.symbol_kind == ORIGIN_PHASE_TICK_SYMBOL_KIND == 10
        supplied = frame[item.source_column].notna().to_numpy()
        lane = table.frame[item.plot_column].to_numpy(dtype=float)
        assert np.array_equal(np.isfinite(lane), supplied)
        assert np.unique(lane[supplied]).size == 1


def test_rietveld_origin_table_does_not_mutate_the_source_frame() -> None:
    frame = _rietveld_frame()
    before = frame.copy(deep=True)

    table = _prepare_origin_table(frame, _preparation(frame))

    pd.testing.assert_frame_equal(frame, before, check_exact=True)
    assert table.source_frame_unchanged is True
    assert tuple(frame.columns) == tuple(before.columns)


def test_rietveld_without_phase_columns_needs_no_helper() -> None:
    frame = _rietveld_frame().drop(columns=["Phase alpha", "Phase beta"])
    preparation = _preparation(frame, phase_tick_columns=())

    table = _prepare_origin_table(frame, preparation)

    assert table.phase_tick_columns == ()
    assert table.helper_columns == ()
    assert not any(item.is_phase_tick for item in table.series)


def test_rietveld_preview_matches_profile_roles_and_phase_lanes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _rietveld_frame()
    preparation = _preparation(frame)
    monkeypatch.setattr(
        "origin_sciplot.scientific_preview.load_scientific_frame",
        lambda _path, _preparation: frame.copy(deep=True),
    )

    figure = _build_scientific_preview_figure(preparation)
    axis = figure.axes[0]
    lines = {line.get_label(): line for line in axis.lines}

    assert lines["Observed"].get_marker() == "o"
    assert lines["Observed"].get_linestyle() == "None"
    assert lines["Calculated"].get_linestyle() == "-"
    assert lines["Background"].get_linestyle() == "--"
    assert np.array_equal(
        np.asarray(lines["Difference"].get_ydata(), dtype=float),
        frame["Diff"].to_numpy(dtype=float),
    )
    assert lines["Phase alpha"].get_marker() == "|"
    assert lines["Phase beta"].get_marker() == "|"
    assert np.unique(lines["Phase alpha"].get_ydata()).size == 1
    legend = axis.get_legend()
    assert legend is not None
    assert legend.get_frame().get_visible() is False
    figure.clear()


def test_rietveld_difference_transform_is_rejected() -> None:
    frame = _rietveld_frame()
    preparation = _preparation(frame)
    bad_series = tuple(
        replace(series, transform="negate") if series.series_role == "difference" else series
        for series in preparation.plot_spec.series
    )
    bad_spec = replace(preparation.plot_spec, series=bad_series)

    with pytest.raises(OriginDrawError, match="must be plotted directly"):
        _prepare_origin_table(frame, replace(preparation, plot_spec=bad_spec))
