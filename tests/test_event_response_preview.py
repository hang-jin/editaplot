from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgba

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_preview import _build_scientific_preview_figure  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    prepare_scientific,
)

INTERVAL = "上游提供的不对称范围（非统计估计）"


def _frame(
    *,
    positive_time_only: bool = False,
    conditions: tuple[str, str] = ("刺激组", "对照组"),
) -> pd.DataFrame:
    first_time = (0.10, 2.0, 6.0) if positive_time_only else (-1.0, 0.4, 2.1)
    second_time = (0.25, 2.6, 7.0) if positive_time_only else (-0.6, 0.9, 3.2)
    rows = []
    values = (
        (first_time[0], conditions[0], 1.0, 0.2, 1.3),
        (second_time[0], conditions[1], 0.8, 0.4, 1.7),
        (first_time[1], conditions[0], 2.4, 1.1, 3.8),
        (second_time[1], conditions[1], 1.4, 0.9, 2.0),
        (first_time[2], conditions[0], 1.7, 1.6, 2.9),
        (second_time[2], conditions[1], 1.1, 0.3, 1.5),
    )
    for time, condition, mean, lower, upper in values:
        rows.append(
            {
                "Time(s)": time,
                "Condition": condition,
                "Mean(uV)": mean,
                "Lower(uV)": lower,
                "Upper(uV)": upper,
                "AcquisitionNote": "source-only note",
            }
        )
    return pd.DataFrame(rows)


def _prepare(
    tmp_path: Path,
    *,
    positive_time_only: bool = False,
    conditions: tuple[str, str] = ("刺激组", "对照组"),
    interval_label: str = INTERVAL,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / ("positive.csv" if positive_time_only else "crossing.csv")
    _frame(positive_time_only=positive_time_only, conditions=conditions).to_csv(source, index=False)
    mapping = ScientificColumnMapping(
        (
            ("Time(s)", "x"),
            ("Condition", "condition"),
            ("Mean(uV)", "mean"),
            ("Lower(uV)", "lower"),
            ("Upper(uV)", "upper"),
            ("AcquisitionNote", "ignored"),
        ),
        scientific_context={"interval_label": interval_label},
    )
    return source, prepare_scientific(source, "event_response", column_mapping=mapping)


def _draw(preparation):
    figure = _build_scientific_preview_figure(preparation)
    FigureCanvasAgg(figure).draw()
    assert len(figure.axes) == 1
    return figure, figure.axes[0]


def _zero_reference_lines(axis) -> list:
    result = []
    for line in axis.lines:
        x = np.asarray(line.get_xdata(), dtype=float)
        if x.size >= 2 and np.allclose(x, 0.0):
            result.append(line)
    return result


def _mean_lines(axis) -> list:
    return [line for line in axis.lines if line not in _zero_reference_lines(axis)]


def _path_values(collection) -> tuple[np.ndarray, np.ndarray]:
    vertices = collection.get_paths()[0].vertices
    return vertices[:, 0], vertices[:, 1]


def test_ready_event_response_builds_a_real_agg_preview_instead_of_generic_fallback(
    tmp_path: Path,
) -> None:
    _source, preparation = _prepare(tmp_path)
    figure, axis = _draw(preparation)
    assert axis.get_xlabel() == preparation.plot_spec.x_title
    assert figure.canvas is not None
    assert len(_mean_lines(axis)) == 2
    assert len(axis.collections) == 2


def test_each_condition_keeps_its_own_mean_coordinates_without_connecting_interleaved_rows(
    tmp_path: Path,
) -> None:
    source, preparation = _prepare(tmp_path)
    _figure, axis = _draw(preparation)
    frame = pd.read_csv(source)
    plan = preparation.plot_spec.event_response_plan

    assert plan is not None
    lines = _mean_lines(axis)
    assert len(lines) == len(plan.condition_rows) == 2
    for line, (condition, rows) in zip(lines, plan.condition_rows, strict=True):
        expected = frame.iloc[list(rows)]
        assert line.get_label() == condition
        assert np.asarray(line.get_xdata(), dtype=float) == pytest.approx(expected[plan.time_column])
        assert np.asarray(line.get_ydata(), dtype=float) == pytest.approx(expected[plan.mean_column])
    assert all(len(line.get_xdata()) == 3 for line in lines)


def test_each_condition_has_one_source_bound_asymmetric_band_on_its_own_irregular_x(
    tmp_path: Path,
) -> None:
    source, preparation = _prepare(tmp_path)
    _figure, axis = _draw(preparation)
    frame = pd.read_csv(source)
    plan = preparation.plot_spec.event_response_plan

    assert plan is not None
    assert len(axis.collections) == len(plan.condition_rows) == 2
    for collection, (_condition, rows) in zip(axis.collections, plan.condition_rows, strict=True):
        expected = frame.iloc[list(rows)]
        polygon_x, polygon_y = _path_values(collection)
        assert sorted(set(np.round(polygon_x, 12))) == pytest.approx(
            sorted(expected[plan.time_column].tolist())
        )
        supplied_bounds = [
            *expected[plan.lower_column].tolist(),
            *expected[plan.upper_column].tolist(),
        ]
        for value in supplied_bounds:
            assert np.any(np.isclose(polygon_y, value))
        assert not np.allclose(
            expected[plan.mean_column] - expected[plan.lower_column],
            expected[plan.upper_column] - expected[plan.mean_column],
        )


def test_event_zero_reference_is_drawn_only_when_the_observed_time_domain_contains_zero(
    tmp_path: Path,
) -> None:
    _crossing_source, crossing = _prepare(tmp_path / "crossing")
    crossing_figure, crossing_axis = _draw(crossing)
    _positive_source, positive = _prepare(tmp_path / "positive", positive_time_only=True)
    positive_figure, positive_axis = _draw(positive)

    assert crossing.plot_spec.event_response_plan.zero_time_visible is True
    assert len(_zero_reference_lines(crossing_axis)) == 1
    assert positive.plot_spec.event_response_plan.zero_time_visible is False
    assert positive.plot_spec.event_response_plan.x_range[0] < 0.0
    assert len(_zero_reference_lines(positive_axis)) == 0
    crossing_figure.clear()
    positive_figure.clear()


def test_preview_uses_the_frozen_physical_axis_rectangle_and_plan_ranges(tmp_path: Path) -> None:
    _source, preparation = _prepare(tmp_path)
    _figure, axis = _draw(preparation)
    plan = preparation.plot_spec.event_response_plan
    layout = preparation.plot_spec.event_response_layout
    style = layout.style
    expected_bounds = (
        style.layer_left_percent / 100,
        1 - (style.layer_top_percent + style.layer_height_percent) / 100,
        style.layer_width_percent / 100,
        style.layer_height_percent / 100,
    )
    assert axis.get_position().bounds == pytest.approx(expected_bounds)
    assert axis.get_xlim() == pytest.approx(plan.x_range)
    assert axis.get_ylim() == pytest.approx(plan.y_range)


def test_mean_lines_bands_and_condition_text_share_frozen_condition_colors(tmp_path: Path) -> None:
    _source, preparation = _prepare(tmp_path)
    figure, axis = _draw(preparation)
    layout = preparation.plot_spec.event_response_layout
    expected = dict(layout.condition_colors)
    preview_style = figure._origin_sciplot_preview_style

    for line, (condition, _rows) in zip(
        _mean_lines(axis), preparation.plot_spec.event_response_plan.condition_rows, strict=True
    ):
        assert to_rgba(line.get_color()) == pytest.approx(to_rgba(expected[condition]))
    for collection, (condition, _rows) in zip(
        axis.collections, preparation.plot_spec.event_response_plan.condition_rows, strict=True
    ):
        face = collection.get_facecolor()[0]
        assert face[:3] == pytest.approx(to_rgba(expected[condition])[:3])
        assert face[3] == pytest.approx(1 - preview_style.fill_transparency_percent / 100)
    text_by_value = {text.get_text(): text for text in figure.texts}
    for condition, color in expected.items():
        assert to_rgba(text_by_value[condition].get_color()) == pytest.approx(to_rgba(color))


def test_condition_and_interval_declarations_are_complete_unframed_figure_text(tmp_path: Path) -> None:
    _source, preparation = _prepare(tmp_path)
    figure, axis = _draw(preparation)
    layout = preparation.plot_spec.event_response_layout
    text_by_value = {text.get_text(): text for text in figure.texts}
    expected_positions = {
        condition: (left / 100, 1 - top / 100) for condition, left, top in layout.condition_labels
    }
    expected_positions[INTERVAL] = (
        layout.interval_label_center[0] / 100,
        1 - layout.interval_label_center[1] / 100,
    )

    assert axis.get_legend() is None
    for label, position in expected_positions.items():
        artist = text_by_value[label]
        assert artist.get_text() == label
        assert artist.get_position() == pytest.approx(position)
        assert artist.get_transform() is figure.transFigure
        assert artist.get_bbox_patch() is None
    assert all(
        text_by_value[label].get_position()[1] > axis.get_position().y1 for label in expected_positions
    )


def test_long_chinese_declarations_remain_verbatim_at_the_same_frozen_font_size(tmp_path: Path) -> None:
    short_source, short = _prepare(tmp_path / "short")
    assert short_source.exists()
    long_conditions = (
        "刺激条件甲·" + "长中文标签" * 14,
        "对照条件乙·" + "长中文标签" * 12,
    )
    long_interval = "上游定义·" + "不对称显示范围不得解释为新统计量" * 12
    _long_source, long = _prepare(tmp_path / "long", conditions=long_conditions, interval_label=long_interval)
    _short_figure, _short_axis = _draw(short)
    long_figure, _long_axis = _draw(long)
    long_style = long_figure._origin_sciplot_preview_style
    long_text = {artist.get_text(): artist for artist in long_figure.texts}

    assert long.plot_spec.event_response_layout.style.page_width_cm > (
        short.plot_spec.event_response_layout.style.page_width_cm
    )
    assert long_text[long_interval].get_text() == long_interval
    assert tuple(label for label in long_conditions if label in long_text) == long_conditions
    assert long.plot_spec.event_response_layout.style.legend_size_pt == 17
    assert long_text[long_interval].get_fontsize() == pytest.approx(long_style.legend_pt)
    physical_scale = (
        long_figure.get_figwidth() * 2.54 / long.plot_spec.event_response_layout.style.page_width_cm
    )
    assert long_text[long_interval].get_fontsize() / physical_scale == pytest.approx(17)


def test_agg_preview_neither_mutates_source_bytes_nor_invents_sample_statistics(tmp_path: Path) -> None:
    source, preparation = _prepare(tmp_path)
    before = source.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    figure, axis = _draw(preparation)
    after = source.read_bytes()
    visible_text = [artist.get_text() for artist in figure.texts]
    visible_text.extend((axis.get_xlabel(), axis.get_ylabel(), axis.get_title()))

    assert after == before
    assert hashlib.sha256(after).hexdigest() == before_hash == preparation.source_sha256
    assert not any("n=" in text.casefold() or "sem" in text.casefold() for text in visible_text)
    assert INTERVAL in visible_text
    assert "AcquisitionNote" not in visible_text
