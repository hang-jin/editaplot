"""Lossless matrix and explicitly requested cuts, without spatial analysis."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import FrozenInstanceError
from datetime import date
from fractions import Fraction
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))


def source():
    return pd.DataFrame({
        "X": [2, 2, 1, 1, 0, 0],
        "Y": [-3, 1, -3, 1, -3, 1],
        "Signal": [-2.0, 4.0, 0.0, 5.0, 3.0, 6.0],
        "QC note": ["retained, not drawn"] * 6,
    }, index=[9, 9, 3, 2, -1, 5])


def build(frame=None, **overrides):
    assert importlib.util.find_spec("origin_sciplot.spatial_profile") is not None
    function = importlib.import_module("origin_sciplot.spatial_profile").build_spatial_profile_plan
    options = dict(
        x_column="X", y_column="Y", value_column="Signal",
        x_unit="mm", y_unit="mm", value_unit="a.u.", profile_x=1, profile_y=1,
    )
    options.update(overrides)
    return function(source() if frame is None else frame, **options)


def test_every_cell_and_positional_binding_survives_interleaved_source_rows():
    frame = source()
    before = frame.copy(deep=True)
    plan = build(frame)
    assert plan.grid.x == (2, 1, 0)
    assert plan.grid.y == (-3, 1)
    assert plan.grid.values == ((-2, 0, 3), (4, 5, 6))
    assert plan.grid.source_rows == ((0, 2, 4), (1, 3, 5))
    assert plan.retained_columns == ("QC note",)
    assert plan.display_transform == "identity"
    assert plan.processing_boundary == "supplied_spatial_values_only"
    pd.testing.assert_frame_equal(frame, before, check_exact=True)


def test_requested_cuts_retain_coordinate_order_values_and_source_rows():
    plan = build()
    assert (plan.profiles.x_at, plan.profiles.y_at) == (1, 1)
    assert plan.profiles.horizontal_values == (4, 5, 6)
    assert plan.profiles.vertical_values == (0, 5)
    assert plan.profiles.horizontal_source_rows == (1, 3, 5)
    assert plan.profiles.vertical_source_rows == (2, 3)


def test_requested_cut_is_not_moved_to_the_largest_cell():
    plan = build(profile_x=2, profile_y=-3)
    assert plan.profiles.horizontal_values == (-2, 0, 3)
    assert plan.profiles.vertical_values == (-2, 4)
    assert plan.profiles.horizontal_source_rows == (0, 2, 4)
    assert plan.profiles.vertical_source_rows == (0, 1)


def test_reverse_coordinates_retain_direction_and_half_cell_display_edges():
    plan = build(source().iloc[::-1])
    assert plan.grid.x == (0, 1, 2)
    assert plan.grid.y == (1, -3)
    assert plan.grid.values == ((6, 5, 4), (3, 0, -2))
    assert plan.grid.source_rows == ((0, 2, 4), (1, 3, 5))
    assert plan.x_range == (-0.5, 2.5)
    assert plan.y_range == (3, -5)
    assert plan.profiles.horizontal_values == (6, 5, 4)
    assert plan.profiles.vertical_values == (5, 0)
    assert plan.profiles.vertical_source_rows == (2, 3)


def test_different_explicit_units_and_chinese_roles_do_not_convert_cells():
    frame = source().rename(columns={"X": "横坐标", "Y": "纵坐标", "Signal": "信号"})
    plan = build(
        frame, x_column="横坐标", y_column="纵坐标", value_column="信号",
        x_unit="mm", y_unit="µm", value_unit="counts",
    )
    assert (plan.x_column, plan.y_column, plan.value_column) == ("横坐标", "纵坐标", "信号")
    assert (plan.x_unit, plan.y_unit, plan.value_unit) == ("mm", "µm", "counts")
    assert plan.grid.x == (2, 1, 0)
    assert plan.grid.y == (-3, 1)
    assert plan.grid.values == ((-2, 0, 3), (4, 5, 6))


def test_plan_and_nested_grid_and_profiles_are_frozen_snapshots():
    frame = source()
    plan = build(frame)
    for target, attribute in [(plan, "x_unit"), (plan.grid, "x"), (plan.profiles, "x_at")]:
        with pytest.raises(FrozenInstanceError):
            setattr(target, attribute, "changed")
    with pytest.raises(TypeError):
        plan.grid.values[0][0] = 100
    frame.iloc[0, 2] = 100
    assert plan.grid.values[0][0] == -2
    assert plan.profiles.vertical_values == (0, 5)


@pytest.mark.parametrize("options", [
    {"x_unit": ""}, {"y_unit": "  "}, {"value_unit": None},
    {"x_unit": 1}, {"y_unit": False}, {"value_unit": []},
    {"x_column": ""}, {"y_column": None}, {"value_column": "  "},
    {"x_column": "missing"}, {"y_column": "X"}, {"value_column": "Y"},
])
def test_missing_or_ambiguous_columns_and_units_are_rejected(options):
    with pytest.raises(ValueError):
        build(**options)


@pytest.mark.parametrize("coordinate", [
    1.5, 1 + 1e-8, np.nextafter(1.0, 2.0), -100,
    True, np.bool_(True), None, "1", 1 + 0j,
    np.nan, np.inf, -np.inf, 10**1000, date(2026, 1, 1), pd.Timestamp("2026-01-01"),
])
@pytest.mark.parametrize("axis", ["profile_x", "profile_y"])
def test_profiles_require_exact_finite_real_supplied_coordinates(axis, coordinate):
    with pytest.raises(ValueError):
        build(**{axis: coordinate})


def test_numpy_real_profile_coordinates_select_the_source_cells():
    plan = build(profile_x=np.float64(1), profile_y=np.int64(-3))
    assert plan.profiles.horizontal_values == (-2, 0, 3)
    assert plan.profiles.vertical_values == (0, 5)


@pytest.mark.parametrize("coordinates", [(1.6e308, 1.75e308), (-8e307, 8e307)])
def test_finite_source_coordinates_cannot_freeze_infinite_display_edges_or_spans(coordinates):
    frame = pd.DataFrame({
        "X": [coordinates[0], coordinates[0], coordinates[1], coordinates[1]],
        "Y": [0, 1, 0, 1], "Signal": [1, 2, 3, 4],
    })
    before = frame.copy(deep=True)
    with pytest.raises(ValueError, match="display bounds"):
        build(frame, profile_x=coordinates[0], profile_y=0)
    pd.testing.assert_frame_equal(frame, before)


def test_profile_coordinate_must_not_round_onto_a_supplied_float():
    with pytest.raises(ValueError):
        build(profile_x=Fraction(2**60 + 1, 2**60))


@pytest.mark.parametrize("coordinate", [2**53 + 1, np.int64(2**53 + 1)])
def test_large_integer_profile_coordinate_must_not_round_onto_a_source_cell(coordinate):
    frame = source()
    frame["X"] = [2**53 + 4, 2**53 + 4, 2**53 + 2, 2**53 + 2, 2**53, 2**53]
    with pytest.raises(ValueError):
        build(frame, profile_x=coordinate)


@pytest.mark.parametrize("fault", [
    "missing_cell", "duplicate_cell", "nonuniform_x", "nonuniform_y", "nonmonotone",
    "nan", "inf", "bool", "date", "datetime", "timedelta", "complex",
    "duplicate_column", "single_x", "empty",
])
def test_invalid_grid_is_rejected_without_mutating_or_repairing_source(fault):
    frame = source()
    if fault == "missing_cell":
        frame = frame.iloc[:-1].copy()
    elif fault == "duplicate_cell":
        frame = pd.concat([frame, frame.iloc[[0]]])
    elif fault == "nonuniform_x":
        frame["X"] = [3, 3, 1, 1, 0, 0]
    elif fault == "nonuniform_y":
        extra = frame.iloc[[0, 2, 4]].copy()
        extra["Y"] = 7
        frame = pd.concat([frame, extra])
    elif fault == "nonmonotone":
        frame["X"] = [2, 2, 0, 0, 1, 1]
    elif fault in ("nan", "inf"):
        frame.iloc[0, 2] = np.nan if fault == "nan" else np.inf
    elif fault == "bool":
        frame["Signal"] = frame["Signal"].astype(object)
        frame.iloc[0, 2] = True
    elif fault == "date":
        frame["X"] = [date(2026, 1, 1)] * 6
    elif fault == "datetime":
        frame["Y"] = pd.date_range("2026-01-01", periods=6)
    elif fault == "timedelta":
        frame["Signal"] = pd.to_timedelta(range(6), unit="s")
    elif fault == "complex":
        frame["Signal"] = frame["Signal"].astype(complex) + 1j
    elif fault == "duplicate_column":
        frame = pd.concat([frame, frame[["X"]]], axis=1)
    elif fault == "single_x":
        frame["X"] = 1
    else:
        frame = frame.iloc[:0].copy()
    before = frame.copy(deep=True)
    with pytest.raises(ValueError):
        build(frame)
    pd.testing.assert_frame_equal(frame, before, check_exact=True)
