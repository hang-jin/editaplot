from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.flim_phasor import PhasorPlan, build_phasor_plan  # noqa: E402


def _plan(frame: pd.DataFrame) -> PhasorPlan:
    return build_phasor_plan(frame, g_column="G", s_column="S", group_column="Group")


def test_plan_preserves_source_values_group_appearance_and_positional_rows() -> None:
    frame = pd.DataFrame({"G": [0.2, 0.5, 0.7, 0.8], "S": [0.1, 0.3, 0.2, 0.1],
                          "Group": ["B", "A", "B", "A"], "Unused": [9, 8, 7, 6]},
                         index=[50, 10, 50, 3])
    original = frame.copy(deep=True)

    plan = _plan(frame)

    pd.testing.assert_frame_equal(frame, original)
    assert plan.group_order == ("B", "A")
    assert plan.group_rows == (("B", (0, 2)), ("A", (1, 3)))
    assert (plan.g_column, plan.s_column, plan.group_column) == ("G", "S", "Group")
    assert not {"g_values", "s_values", "points"} & {field.name for field in fields(plan)}
    with pytest.raises(FrozenInstanceError):
        plan.g_column = "another"  # type: ignore[misc]


def test_negative_s_and_points_outside_reference_are_retained_with_warning() -> None:
    frame = pd.DataFrame({"G": [-0.2, 0.5, 1.2, 0.5], "S": [0.1, -0.2, 0.1, 0.7],
                          "Group": ["A"] * 4})
    plan = _plan(frame)

    assert plan.group_rows == (("A", (0, 1, 2, 3)),)
    assert plan.outside_reference_count == 4
    assert plan.warnings and "4" in plan.warnings[0]
    assert plan.x_range == pytest.approx((-0.27, 1.27))
    assert plan.y_range == pytest.approx((-0.245, 0.745))
    assert all(plan.x_range[0] < value < plan.x_range[1] for value in frame["G"])
    assert all(plan.y_range[0] < value < plan.y_range[1] for value in frame["S"])


def test_single_constant_group_still_uses_reference_bounds_and_finite_padding() -> None:
    frame = pd.DataFrame({"G": [0.5, 0.5], "S": [0.25, 0.25], "Group": ["A", "A"]})
    plan = _plan(frame)

    assert plan.group_order == ("A",)
    assert plan.x_range == pytest.approx((-0.05, 1.05))
    assert plan.y_range == pytest.approx((-0.025, 0.525))
    assert plan.outside_reference_count == 0
    assert plan.warnings == ()


def test_reference_semicircle_is_fixed_mathematical_geometry_not_experimental_values() -> None:
    plan = _plan(pd.DataFrame({"G": [0.5], "S": [0.25], "Group": ["A"]}))
    theta = np.linspace(0, np.pi, 181)

    assert plan.reference_kind == "mathematical_reference_not_experimental_data"
    assert plan.reference_g == pytest.approx(0.5 + 0.5 * np.cos(theta))
    assert plan.reference_s == pytest.approx(0.5 * np.sin(theta))
    assert np.square(np.asarray(plan.reference_g) - 0.5) + np.square(plan.reference_s) == pytest.approx(
        np.full(181, 0.25)
    )
    assert min(plan.reference_s) >= 0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, "not numeric", True, 0.3 + 0.1j])
@pytest.mark.parametrize("column", ["G", "S"])
def test_rejects_nonfinite_or_nonreal_numeric_coordinates(column: str, bad: object) -> None:
    frame = pd.DataFrame({"G": [0.5], "S": [0.25], "Group": ["A"]})
    frame[column] = [bad]
    with pytest.raises(ValueError, match=column):
        _plan(frame)


@pytest.mark.parametrize("bad", [None, np.nan, "", " \t "])
def test_rejects_empty_group_labels(bad: object) -> None:
    with pytest.raises(ValueError, match="Group"):
        _plan(pd.DataFrame({"G": [0.5], "S": [0.25], "Group": [bad]}))


def test_rejects_empty_table_and_more_than_eight_groups() -> None:
    with pytest.raises(ValueError, match="at least one"):
        _plan(pd.DataFrame(columns=["G", "S", "Group"]))
    with pytest.raises(ValueError, match="1.?8"):
        _plan(pd.DataFrame({"G": [0.5] * 9, "S": [0.25] * 9,
                           "Group": [f"G{i}" for i in range(9)]}))


def test_accepts_eight_groups_without_reordering_or_dropping_points() -> None:
    groups = [f"G{i}" for i in range(8, 0, -1)]
    plan = _plan(pd.DataFrame({"G": [0.5] * 8, "S": [0.25] * 8, "Group": groups}))
    assert plan.group_order == tuple(groups)
    assert plan.group_rows == tuple((group, (i,)) for i, group in enumerate(groups))


def test_numeric_group_ids_do_not_silently_merge_with_identical_text_labels() -> None:
    frame = pd.DataFrame({"G": [0.5, 0.5], "S": [0.25, 0.25], "Group": [1, "1"]})
    with pytest.raises(ValueError, match="ambiguous Group"):
        _plan(frame)


def test_requires_explicit_distinct_unambiguous_column_names() -> None:
    frame = pd.DataFrame({"G": [0.5], "S": [0.25], "Group": ["A"]})
    with pytest.raises(TypeError):
        build_phasor_plan(frame, "G", "S", "Group")  # type: ignore[misc]
    with pytest.raises(ValueError, match="Missing"):
        build_phasor_plan(frame, g_column="missing", s_column="S", group_column="Group")
    with pytest.raises(ValueError, match="distinct"):
        build_phasor_plan(frame, g_column="G", s_column="G", group_column="Group")
    duplicate = pd.DataFrame([[0.3, 0.4, 0.2, "A"]], columns=["G", "G", "S", "Group"])
    with pytest.raises(ValueError, match="ambiguous"):
        _plan(duplicate)
