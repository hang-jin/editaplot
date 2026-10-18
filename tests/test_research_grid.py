from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))

from origin_sciplot.research_grid import (  # noqa: E402
    ResearchGridError,
    orthogonal_profiles,
    physical_grid,
)


def table():
    return pd.DataFrame({"x": [0, 1, 2] * 2, "y": [4] * 3 + [6] * 3, "value": [-2.0, 0, 3, 4, 5, 6]})


def test_physical_grid_preserves_values_and_coordinate_directions():
    frame = table()
    before = frame.copy(deep=True)
    grid = physical_grid(frame, "x", "y", "value")
    assert grid.x == (0, 1, 2)
    assert grid.y == (4, 6)
    assert grid.values == ((-2, 0, 3), (4, 5, 6))
    assert grid.xymap == (0, 2, 4, 6)
    assert grid.cell_edges == (-0.5, 2.5, 3, 7)
    assert grid.source_rows == ((0, 1, 2), (3, 4, 5))
    pd.testing.assert_frame_equal(before, frame)
    reverse = physical_grid(frame.iloc[::-1], "x", "y", "value")
    assert reverse.xymap == (2, 0, 6, 4)
    assert reverse.values[0] == (6, 5, 4)


def test_interleaved_rows_keep_source_binding_without_changing_data():
    frame = table().iloc[[0, 3, 1, 4, 2, 5]]
    grid = physical_grid(frame, "x", "y", "value")
    assert grid.values == ((-2, 0, 3), (4, 5, 6))
    assert grid.source_rows == ((0, 2, 4), (1, 3, 5))


@pytest.mark.parametrize("case", ["missing", "duplicate", "nonuniform", "nan", "inf"])
def test_invalid_grid_cannot_be_imputed_or_plotted_as_even_categories(case):
    frame = table()
    if case == "missing":
        frame = frame.iloc[:-1]
    elif case == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    elif case == "nonuniform":
        frame.loc[frame.x == 2, "x"] = 3
    else:
        frame.loc[2, "value"] = np.nan if case == "nan" else np.inf
    with pytest.raises(ResearchGridError):
        physical_grid(frame, "x", "y", "value")


def test_profiles_select_exact_supplied_coordinates_without_interpolation():
    grid = physical_grid(table(), "x", "y", "value")
    profiles = orthogonal_profiles(grid, x_at=1, y_at=6)
    assert profiles.horizontal_values == (4, 5, 6)
    assert profiles.vertical_values == (0, 5)
    assert profiles.horizontal_source_rows == (3, 4, 5)
    assert profiles.vertical_source_rows == (1, 4)
    with pytest.raises(ResearchGridError, match="supplied coordinate"):
        orthogonal_profiles(grid, x_at=1.4, y_at=6)


@pytest.mark.parametrize("case", ["complex", "bool", "duplicate_column", "overflow"])
def test_grid_does_not_silently_cast_nonmeasurement_coordinates(case):
    frame = table()
    if case == "complex":
        frame["value"] = frame["value"].astype(complex) + 1j
    elif case == "bool":
        frame["value"] = frame["value"] > 0
    elif case == "duplicate_column":
        frame = pd.concat([frame, frame[["x"]]], axis=1)
    else:
        frame["y"] = [-1e308] * 3 + [1e308] * 3
    with pytest.raises(ResearchGridError):
        physical_grid(frame, "x", "y", "value")
