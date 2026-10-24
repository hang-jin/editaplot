"""Lossless uniform physical grids for source-bound imaging research panels.

No gridding, interpolation, averaging, normalization or missing-value repair is
performed. Row indices refer to positions in the original input, not its index.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


class ResearchGridError(ValueError):
    """The supplied coordinates cannot be represented by a uniform matrix."""


@dataclass(frozen=True)
class PhysicalGrid:
    x: tuple[float, ...]
    y: tuple[float, ...]
    values: tuple[tuple[float, ...], ...]
    source_rows: tuple[tuple[int, ...], ...]

    @property
    def xymap(self) -> tuple[float, float, float, float]:
        return self.x[0], self.x[-1], self.y[0], self.y[-1]

    @property
    def cell_edges(self) -> tuple[float, float, float, float]:
        dx, dy = self.x[1] - self.x[0], self.y[1] - self.y[0]
        return self.x[0] - dx / 2, self.x[-1] + dx / 2, self.y[0] - dy / 2, self.y[-1] + dy / 2


def _uniform_coordinates(values: np.ndarray, label: str) -> tuple[float, ...]:
    coordinates = tuple(dict.fromkeys(map(float, values)))
    if len(coordinates) < 2:
        raise ResearchGridError(f"{label} needs at least two supplied coordinates.")
    with np.errstate(over="ignore", invalid="ignore"):
        steps = np.diff(coordinates)
    if not np.isfinite(steps).all():
        raise ResearchGridError(f"{label} coordinate spacing exceeds finite display bounds.")
    if not (np.all(steps > 0) or np.all(steps < 0)):
        raise ResearchGridError(f"{label} coordinates must be monotone in first-appearance order.")
    if not np.allclose(steps, steps[0], rtol=1e-7, atol=abs(steps[0]) * 1e-10):
        raise ResearchGridError(f"{label} is not uniformly spaced; no resampling is performed.")
    return coordinates


def physical_grid(frame: pd.DataFrame, x_column: str, y_column: str, value_column: str) -> PhysicalGrid:
    columns = (x_column, y_column, value_column)
    if len(set(columns)) != 3 or not set(columns).issubset(frame.columns):
        raise ResearchGridError("Supply three distinct coordinate/value columns.")
    if any(sum(name == column for name in frame.columns) != 1 for column in columns):
        raise ResearchGridError("Grid column names must be unique.")
    try:
        arrays = []
        for column in columns:
            source = frame[column]
            if (
                any(isinstance(value, (bool, np.bool_)) for value in source)
                or pd.api.types.is_datetime64_any_dtype(source)
                or pd.api.types.is_timedelta64_dtype(source)
            ):
                raise ResearchGridError("Grid values must be real measurements, not flags or timestamps.")
            numeric = pd.to_numeric(source, errors="raise")
            if np.iscomplexobj(numeric):
                raise ResearchGridError("Complex grid values require explicit upstream processing.")
            arrays.append(numeric.to_numpy(dtype=float, copy=True))
        data = np.column_stack(arrays)
    except (TypeError, ValueError) as exc:
        raise ResearchGridError("Grid coordinates and values must be numeric.") from exc
    if not len(data) or not np.all(np.isfinite(data)):
        raise ResearchGridError("A complete grid requires finite values; missing cells are not filled.")
    x = _uniform_coordinates(data[:, 0], x_column)
    y = _uniform_coordinates(data[:, 1], y_column)
    rows: dict[tuple[float, float], tuple[int, float]] = {}
    for position, (xx, yy, value) in enumerate(data):
        key = float(xx), float(yy)
        if key in rows:
            raise ResearchGridError("Duplicate grid coordinates cannot be averaged by the drawing layer.")
        rows[key] = position, float(value)
    if len(rows) != len(x) * len(y):
        raise ResearchGridError("The rectangular grid has missing cells; no imputation is performed.")
    grid = PhysicalGrid(
        x=x,
        y=y,
        values=tuple(tuple(rows[xx, yy][1] for xx in x) for yy in y),
        source_rows=tuple(tuple(rows[xx, yy][0] for xx in x) for yy in y),
    )
    if not np.isfinite(grid.cell_edges).all():
        raise ResearchGridError("Physical pixel edges exceed finite display bounds.")
    return grid


@dataclass(frozen=True)
class OrthogonalProfiles:
    x_at: float
    y_at: float
    horizontal_values: tuple[float, ...]
    vertical_values: tuple[float, ...]
    horizontal_source_rows: tuple[int, ...]
    vertical_source_rows: tuple[int, ...]


def orthogonal_profiles(grid: PhysicalGrid, *, x_at: float, y_at: float) -> OrthogonalProfiles:
    """Select a user-specified row/column, never a peak or an interpolated cut."""

    def position(coordinates: tuple[float, ...], value: float) -> int:
        tolerance = abs(coordinates[1] - coordinates[0]) * 1e-7
        matches = [i for i, v in enumerate(coordinates) if abs(v - value) <= tolerance]
        if len(matches) != 1:
            raise ResearchGridError("The requested cut must match exactly one supplied coordinate.")
        return matches[0]

    xi, yi = position(grid.x, x_at), position(grid.y, y_at)
    return OrthogonalProfiles(
        x_at=grid.x[xi],
        y_at=grid.y[yi],
        horizontal_values=grid.values[yi],
        vertical_values=tuple(row[xi] for row in grid.values),
        horizontal_source_rows=grid.source_rows[yi],
        vertical_source_rows=tuple(row[xi] for row in grid.source_rows),
    )
