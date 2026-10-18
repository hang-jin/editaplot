from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.event_raster import build_event_raster_plan  # noqa: E402


def _plan(frame: pd.DataFrame):
    return build_event_raster_plan(
        frame, event_time_column="Time", trial_column="Trial",
        condition_column="Condition", time_unit="ms",
    )


def test_preserves_explicit_empty_trials_source_order_and_positional_lineage() -> None:
    frame = pd.DataFrame({"Time": [None, -2.0, 2.0, "", 0.5],
                          "Trial": ["T5", "T2", "T2", "T8", "T9"],
                          "Condition": ["B", "A", "A", "B", "A"],
                          "Unused": [4, 3, 2, 1, 0]}, index=[99, 5, 5, 1, -3])
    original = frame.copy(deep=True)
    plan = _plan(frame)

    pd.testing.assert_frame_equal(frame, original)
    assert plan.trial_order == ("T5", "T2", "T8", "T9")
    assert plan.condition_order == ("B", "A")
    assert plan.event_rows == (1, 2, 4)
    assert plan.inventory_rows == (0, 3)
    assert plan.empty_trial_ids == ("T5", "T8")
    assert plan.trial_conditions == (("T5", "B"), ("T2", "A"), ("T8", "B"), ("T9", "A"))
    assert plan.row_trial_positions == ((0, 1), (1, 2), (2, 2), (3, 3), (4, 4))
    assert plan.x_range == pytest.approx((-2.2, 2.2))
    assert plan.y_range == (0.5, 4.5)
    assert plan.time_unit == "ms"
    assert (plan.event_time_column, plan.trial_column, plan.condition_column) == (
        "Time", "Trial", "Condition"
    )
    assert not {"event_times", "values", "points"} & {field.name for field in fields(plan)}
    with pytest.raises(FrozenInstanceError):
        plan.time_unit = "s"


def test_does_not_infer_missing_trials_between_numeric_ids_or_fill_zero_events() -> None:
    frame = pd.DataFrame({"Time": [-1.0, 2.0], "Trial": [1, 3], "Condition": ["A", "A"]})
    plan = _plan(frame)
    assert plan.trial_order == ("1", "3")
    assert plan.empty_trial_ids == ()
    assert plan.inventory_rows == ()
    assert plan.event_rows == (0, 1)


@pytest.mark.parametrize("empty", [None, np.nan, pd.NA, "", "  "])
def test_accepts_one_inventory_row_for_trial_that_also_has_events(empty: object) -> None:
    plan = _plan(pd.DataFrame({"Time": [empty, 0.0, 1.0], "Trial": ["T1"] * 3,
                               "Condition": ["A"] * 3}))
    assert plan.inventory_rows == (0,)
    assert plan.event_rows == (1, 2)
    assert plan.empty_trial_ids == ()


def test_rejects_duplicate_event_without_silently_deduplicating() -> None:
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        _plan(pd.DataFrame({"Time": [1, "1.0"], "Trial": ["T1", "T1"], "Condition": ["A", "A"]}))


def test_same_time_is_valid_across_different_trials() -> None:
    plan = _plan(pd.DataFrame({"Time": [1.0, 1.0], "Trial": ["T1", "T2"], "Condition": ["A", "A"]}))
    assert plan.event_rows == (0, 1)


def test_rejects_multiple_inventory_rows_for_the_same_trial() -> None:
    with pytest.raises(ValueError, match="inventory"):
        _plan(pd.DataFrame({"Time": [None, "", 1.0], "Trial": ["T1", "T1", "T2"],
                           "Condition": ["A", "A", "A"]}))


def test_rejects_conflicting_conditions_even_when_one_row_is_inventory() -> None:
    with pytest.raises(ValueError, match="one condition"):
        _plan(pd.DataFrame({"Time": [None, 1.0], "Trial": ["T1", "T1"], "Condition": ["A", "B"]}))


@pytest.mark.parametrize("bad", [np.inf, -np.inf, "inf", "nan", True, 1 + 2j, "invalid"])
def test_rejects_nonfinite_or_nonreal_nonempty_event_times(bad: object) -> None:
    with pytest.raises(ValueError, match="Time"):
        _plan(pd.DataFrame({"Time": [bad], "Trial": ["T1"], "Condition": ["A"]}))


@pytest.mark.parametrize("column", ["Trial", "Condition"])
@pytest.mark.parametrize("bad", [None, np.nan, "", "\t "])
def test_rejects_empty_trial_or_condition(column: str, bad: object) -> None:
    frame = pd.DataFrame({"Time": [1.0], "Trial": ["T1"], "Condition": ["A"]})
    frame[column] = [bad]
    with pytest.raises(ValueError, match=column):
        _plan(frame)


@pytest.mark.parametrize("column", ["Trial", "Condition"])
def test_rejects_ambiguous_mixed_numeric_and_string_labels(column: str) -> None:
    frame = pd.DataFrame({"Time": [1.0, 2.0], "Trial": ["T1", "T2"], "Condition": ["A", "B"]})
    frame[column] = [1, "1"]
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(frame)


@pytest.mark.parametrize("time", [0.0, -10.0, 0.001])
def test_constant_time_has_positive_finite_axis_span(time: float) -> None:
    plan = _plan(pd.DataFrame({"Time": [time], "Trial": ["T1"], "Condition": ["A"]}))
    margin = max(abs(time), 1.0) * 0.05
    assert plan.x_range == pytest.approx((time - margin, time + margin))
    assert plan.x_range[0] < time < plan.x_range[1]


def test_rejects_table_with_only_inventory_or_no_observations() -> None:
    for frame in (pd.DataFrame(columns=["Time", "Trial", "Condition"]),
                  pd.DataFrame({"Time": [np.nan], "Trial": ["T1"], "Condition": ["A"]})):
        with pytest.raises(ValueError, match="at least one finite event"):
            _plan(frame)


def test_enforces_condition_and_trial_limits() -> None:
    with pytest.raises(ValueError, match="1.?8"):
        _plan(pd.DataFrame({"Time": list(range(9)), "Trial": list(range(9)), "Condition": list(range(9))}))
    with pytest.raises(ValueError, match="200"):
        _plan(pd.DataFrame({"Time": list(range(201)), "Trial": list(range(201)), "Condition": ["A"] * 201}))
    plan = _plan(pd.DataFrame({"Time": list(range(200)), "Trial": list(range(200)),
                              "Condition": [f"C{i % 8}" for i in range(200)]}))
    assert len(plan.trial_order) == 200 and len(plan.condition_order) == 8


@pytest.mark.parametrize("unit", [None, "", "  "])
def test_requires_explicit_nonempty_time_unit(unit: object) -> None:
    frame = pd.DataFrame({"Time": [1.0], "Trial": ["T1"], "Condition": ["A"]})
    with pytest.raises(ValueError, match="time_unit"):
        build_event_raster_plan(frame, event_time_column="Time", trial_column="Trial",
                                condition_column="Condition", time_unit=unit)


def test_requires_distinct_unambiguous_source_columns_and_keyword_arguments() -> None:
    frame = pd.DataFrame({"Time": [1.0], "Trial": ["T1"], "Condition": ["A"]})
    with pytest.raises(TypeError):
        build_event_raster_plan(frame, "Time", "Trial", "Condition", "ms")
    with pytest.raises(ValueError, match="distinct"):
        build_event_raster_plan(frame, event_time_column="Time", trial_column="Trial",
                                condition_column="Trial", time_unit="ms")
    with pytest.raises(ValueError, match="Missing"):
        _plan(frame.drop(columns="Time"))
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(pd.DataFrame([[1.0, 2.0, "T1", "A"]], columns=["Time", "Time", "Trial", "Condition"]))
