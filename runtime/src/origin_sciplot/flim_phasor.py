"""Freeze a display-only plan for upstream-calculated FLIM G/S coordinates.

No lifetimes, fits, clusters, or mixture fractions are inferred here. Source
coordinates remain in the caller's table; the plan stores zero-based positional
row references. The universal semicircle is mathematical reference geometry,
not a measured dataset or a reason to remove observations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

REFERENCE_POINT_COUNT = 181
REFERENCE_KIND = "mathematical_reference_not_experimental_data"


@dataclass(frozen=True)
class PhasorPlan:
    g_column: str
    s_column: str
    group_column: str
    group_order: tuple[str, ...]
    group_rows: tuple[tuple[str, tuple[int, ...]], ...]
    reference_g: tuple[float, ...]
    reference_s: tuple[float, ...]
    reference_kind: str
    outside_reference_count: int
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    warnings: tuple[str, ...]


def _coordinates(frame: pd.DataFrame, column: str) -> np.ndarray:
    series = frame[column]
    if any(isinstance(value, (bool, np.bool_)) for value in series):
        raise ValueError(f"{column}: coordinates must be real numeric values, not booleans.")
    try:
        numeric = pd.to_numeric(series, errors="raise")
        if np.iscomplexobj(numeric):
            raise ValueError("Complex values are not phasor coordinates.")
        values = numeric.to_numpy(dtype=float, copy=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{column}: coordinates must be finite real numeric values.") from error
    if not np.isfinite(values).all():
        raise ValueError(f"{column}: coordinates must be finite real numeric values.")
    return values


def _padded_range(lower: float, upper: float) -> tuple[float, float]:
    # Scale the endpoints before subtraction to avoid overflow in upper-lower.
    padding = upper * 0.05 - lower * 0.05
    bounds = (lower - padding, upper + padding)
    if not all(math.isfinite(value) for value in bounds) or bounds[0] >= bounds[1]:
        raise ValueError("Coordinates are too large for finite 5% padded display bounds.")
    return bounds


def build_phasor_plan(
    frame: pd.DataFrame,
    *,
    g_column: str,
    s_column: str,
    group_column: str,
) -> PhasorPlan:
    """Validate explicit columns without modifying or copying points into the plan.

    ``group_rows`` are positions for ``frame.iloc``, never DataFrame index labels.
    Labels retain their source spelling (numeric labels become strings), and
    groups retain first-appearance order. Both axis ranges include every source
    coordinate and the reference semicircle, with 5% padding on each side. The
    renderer must give G and S equal physical units; equal numeric ranges are
    not required. Values outside the upper reference disk generate a warning,
    not deletion, clipping, or a scientific quality classification.
    """
    columns = (g_column, s_column, group_column)
    if any(not isinstance(column, str) or not column.strip() for column in columns):
        raise ValueError("Provide explicit nonempty G, S, and Group column names.")
    if len(set(columns)) != 3:
        raise ValueError("G, S, and Group must use three distinct source columns.")
    for column in columns:
        matches = sum(name == column for name in frame.columns)
        if matches == 0:
            raise ValueError(f"Missing source column: {column}.")
        if matches != 1:
            raise ValueError(f"Source column {column} is ambiguous because its name is duplicated.")
    if frame.empty:
        raise ValueError("A phasor table requires at least one observation.")

    g = _coordinates(frame, g_column)
    s = _coordinates(frame, s_column)
    rows: dict[str, list[int]] = {}
    original_labels: dict[str, object] = {}
    for position, value in enumerate(frame[group_column]):
        if not pd.api.types.is_scalar(value) or pd.isna(value) or not str(value).strip():
            raise ValueError(f"{group_column}: Group labels must be nonempty scalar values.")
        label = str(value)
        if label in original_labels and original_labels[label] != value:
            raise ValueError(f"{group_column}: ambiguous Group values share the display label {label!r}.")
        original_labels[label] = value
        rows.setdefault(label, []).append(position)
    if not 1 <= len(rows) <= 8:
        raise ValueError("A phasor plot supports 1–8 explicit groups.")

    theta = np.linspace(0.0, np.pi, REFERENCE_POINT_COUNT)
    reference_g = 0.5 + 0.5 * np.cos(theta)
    reference_s = 0.5 * np.sin(theta)
    # A small radius tolerance keeps floating-point samples on the mathematical
    # circle from being counted as exterior. Negative S is retained and flagged.
    outside_count = int(np.count_nonzero((s < 0.0) | (np.hypot(g - 0.5, s) > 0.5 + 1e-12)))
    warnings = (
        (
            f"{outside_count} source point(s) lie outside the upper mathematical reference disk; "
            "all points are retained unchanged. This is not a lifetime estimate or quality classification."
        ),
    ) if outside_count else ()

    return PhasorPlan(
        g_column=g_column,
        s_column=s_column,
        group_column=group_column,
        group_order=tuple(rows),
        group_rows=tuple((label, tuple(positions)) for label, positions in rows.items()),
        reference_g=tuple(float(value) for value in reference_g),
        reference_s=tuple(float(value) for value in reference_s),
        reference_kind=REFERENCE_KIND,
        outside_reference_count=outside_count,
        x_range=_padded_range(min(float(g.min()), 0.0), max(float(g.max()), 1.0)),
        y_range=_padded_range(min(float(s.min()), 0.0), max(float(s.max()), 0.5)),
        warnings=warnings,
    )
