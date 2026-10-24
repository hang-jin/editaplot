"""Source-bound spatial matrices with explicitly selected orthogonal profiles.

No peak selection, interpolation, normalization, fitting, FWHM or resolution
analysis is performed. Units are declarations and are never converted; even
different coordinate units remain explicit without a physical-aspect inference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
import pandas as pd

from .research_grid import OrthogonalProfiles, PhysicalGrid, physical_grid


@dataclass(frozen=True)
class SpatialProfilePlan:
    x_column: str
    y_column: str
    value_column: str
    x_unit: str
    y_unit: str
    value_unit: str
    grid: PhysicalGrid
    profiles: OrthogonalProfiles
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    retained_columns: tuple[str, ...]
    display_transform: str = "identity"
    processing_boundary: str = "supplied_spatial_values_only"


def _profile_position(coordinates: tuple[float, ...], value: object, label: str) -> int:
    if not isinstance(value, Real) or isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be a finite real supplied coordinate.")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite real supplied coordinate.") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite real supplied coordinate.")
    # Keep exact equality against the supplied real, not its rounded float cast.
    # Native integers also avoid NumPy's integer/float comparison rounding.
    exact_value = int(value) if isinstance(value, Integral) else value
    matches = [index for index, coordinate in enumerate(coordinates) if coordinate == exact_value]
    if len(matches) != 1:
        raise ValueError(
            f"{label} must match exactly one supplied coordinate; no nearest selection is performed."
        )
    return matches[0]


def build_spatial_profile_plan(
    frame: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    value_column: str,
    x_unit: str,
    y_unit: str,
    value_unit: str,
    profile_x: float,
    profile_y: float,
) -> SpatialProfilePlan:
    """Freeze one complete uniform long table and two exact caller-selected cuts.

    A horizontal cut fixes ``profile_y`` and follows the supplied X direction;
    a vertical cut fixes ``profile_x`` and follows the supplied Y direction.
    Source rows are original ``iloc`` positions, not DataFrame index labels.
    Half-cell display edges are bounds only, not additional observations.
    """
    columns = (x_column, y_column, value_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide explicit X, Y and Value source columns.")
    for unit in (x_unit, y_unit, value_unit):
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError("X, Y and value units must be explicitly declared.")
    grid = physical_grid(frame, *columns)
    xi = _profile_position(grid.x, profile_x, "profile_x")
    yi = _profile_position(grid.y, profile_y, "profile_y")
    profiles = OrthogonalProfiles(
        x_at=grid.x[xi], y_at=grid.y[yi],
        horizontal_values=grid.values[yi],
        vertical_values=tuple(row[xi] for row in grid.values),
        horizontal_source_rows=grid.source_rows[yi],
        vertical_source_rows=tuple(row[xi] for row in grid.source_rows),
    )
    edges = grid.cell_edges
    if not all(math.isfinite(end - begin) and begin != end for begin, end in (edges[:2], edges[2:])):
        raise ValueError("Spatial coordinates cannot produce finite display bounds.")
    return SpatialProfilePlan(
        x_column=x_column, y_column=y_column, value_column=value_column,
        x_unit=x_unit, y_unit=y_unit, value_unit=value_unit,
        grid=grid, profiles=profiles, x_range=edges[:2], y_range=edges[2:],
        retained_columns=tuple(str(column) for column in frame.columns if column not in columns),
    )
