"""Source-bound display planning for already processed time-frequency cells.

No FFT, STFT, wavelet transform, baseline correction, conversion to dB,
interpolation, filtering, clustering, or missing-cell repair is performed.
Color semantics and physical units are explicit declarations, not inferences
from a negative number or a filename. Source rows remain positional bindings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd

from .research_grid import PhysicalGrid, physical_grid


@dataclass(frozen=True)
class TimeFrequencyPlan:
    time_column: str
    frequency_column: str
    value_column: str
    time_unit: str
    frequency_unit: str
    value_unit: str
    grid: PhysicalGrid
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    color_semantics: str
    color_reference: float | None
    color_limits: tuple[float, float]
    retained_columns: tuple[str, ...]
    display_transform: str = "identity"
    processing_boundary: str = "supplied_time_frequency_values_only"


def _finite_real(value: object) -> float:
    if not isinstance(value, Real) or isinstance(value, (bool, np.bool_)):
        raise ValueError("Color declarations must be finite real numbers.")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError("Color declarations must be finite real numbers.") from error
    if not math.isfinite(number):
        raise ValueError("Color declarations must be finite real numbers.")
    return number


def build_time_frequency_plan(
    frame: pd.DataFrame,
    *,
    time_column: str,
    frequency_column: str,
    value_column: str,
    time_unit: str,
    frequency_unit: str,
    value_unit: str,
    color_semantics: Literal["sequential", "diverging"],
    color_reference: float | None = None,
    color_limits: tuple[float, float] | None = None,
) -> TimeFrequencyPlan:
    """Freeze complete uniform cells without interpreting raw signal recordings.

    Source-coordinate directions, cells, extra columns, and units are retained.
    Half-cell display edges do not create new observations. Negative dB values
    do not imply baseline-relative change: diverging colors require an explicit
    reference, with a symmetric, non-clipping display range in those units.
    """
    columns = (time_column, frequency_column, value_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide explicit Time, Frequency and Value source columns.")
    for unit in (time_unit, frequency_unit, value_unit):
        if not isinstance(unit, str) or not unit.strip():
            raise ValueError("Time, frequency and value units must be explicitly declared.")
    if color_semantics not in ("sequential", "diverging"):
        raise ValueError("Declare sequential values or diverging changes with a reference.")
    if color_semantics == "sequential" and color_reference is not None:
        raise ValueError("A sequential scale must not silently introduce a color reference.")
    if color_semantics == "diverging" and color_reference is None:
        raise ValueError("A diverging scale requires an explicit scientific color reference.")
    reference = _finite_real(color_reference) if color_reference is not None else None
    grid = physical_grid(frame, *columns)
    if min(grid.y) < 0:
        raise ValueError("Frequency coordinates must be nonnegative in the declared units.")
    values = np.asarray(grid.values)
    lower, upper = float(values.min()), float(values.max())
    if color_limits is None:
        if reference is not None:
            extent = max(abs(lower - reference), abs(upper - reference))
            extent = extent if extent > 0 else max(abs(reference), 1.0) * 0.05
            limits = reference - extent, reference + extent
        elif lower == upper:
            padding = max(abs(lower), 1.0) * 0.05
            limits = lower - padding, upper + padding
        else:
            limits = lower, upper
    else:
        try:
            limits = tuple(_finite_real(value) for value in color_limits)
        except TypeError as error:
            raise ValueError("Provide two finite color-limit endpoints.") from error
    if (
        len(limits) != 2 or not all(map(math.isfinite, limits)) or limits[0] >= limits[1]
        or not math.isfinite(limits[1] - limits[0]) or limits[0] > lower or limits[1] < upper
    ):
        raise ValueError("Color limits must increase, remain finite and contain every supplied cell.")
    if reference is not None:
        midpoint = limits[0] * 0.5 + limits[1] * 0.5
        tolerance = max((limits[1] - limits[0]) * 1e-10, math.ulp(reference) * 4)
        if not math.isclose(midpoint, reference, rel_tol=0, abs_tol=tolerance):
            raise ValueError("Diverging color limits must be symmetric around the declared reference.")
    edges = grid.cell_edges
    return TimeFrequencyPlan(
        time_column=time_column, frequency_column=frequency_column, value_column=value_column,
        time_unit=time_unit, frequency_unit=frequency_unit, value_unit=value_unit,
        grid=grid, x_range=edges[:2], y_range=edges[2:], color_semantics=color_semantics,
        color_reference=reference, color_limits=(limits[0], limits[1]),
        retained_columns=tuple(str(column) for column in frame.columns if column not in columns),
    )
