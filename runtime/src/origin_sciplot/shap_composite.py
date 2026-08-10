"""Frozen data semantics for editable SHAP composite figures.

The renderer consumes only externally precomputed, row-level SHAP values.  This
module may summarize those supplied values for the optional Mean |SHAP| panel
and grouped contribution inset, but it never trains a model or invokes SHAP.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

ShapCompositeProfile = Literal[
    "beeswarm_only",
    "beeswarm_mean_abs",
    "beeswarm_mean_abs_grouped",
]
ShapSummarySource = Literal["not_used", "provided", "derived_from_supplied_shap"]

SHAP_COMPOSITE_LAYOUT_VERSION = "shap-composite-layout-v1"

SHAP_COMPOSITE_PROFILES = frozenset(
    {
        "beeswarm_only",
        "beeswarm_mean_abs",
        "beeswarm_mean_abs_grouped",
    }
)


class ShapCompositeError(ValueError):
    """Stable fail-closed validation error for SHAP composite data."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        column: str | None = None,
        row: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.column = column
        self.row = row


@dataclass(frozen=True)
class ShapCompositePlan:
    """Source-bound summaries shared by preview, Origin, and semantic review."""

    layout_version: str
    profile: ShapCompositeProfile
    feature_order: tuple[str, ...]
    feature_order_column: str | None
    sample_id_column: str | None
    mean_abs_column: str | None
    mean_abs_source: ShapSummarySource
    mean_abs_values: tuple[tuple[str, float], ...]
    feature_group_column: str | None
    feature_groups: tuple[tuple[str, str], ...]
    group_order: tuple[str, ...]
    group_contribution_column: str | None
    group_contribution_source: ShapSummarySource
    group_contributions: tuple[tuple[str, float], ...]


def _normalised_feature_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    values = np.asarray([str(value).strip() for value in frame[column]], dtype=object)
    blank = np.asarray(
        [not value or value.casefold() == "nan" for value in values],
        dtype=bool,
    )
    if bool(blank.any()):
        index = int(np.flatnonzero(blank)[0])
        raise ShapCompositeError(
            "shap_feature_empty",
            f"Feature column {column!r} is empty at data row {index + 2}.",
            column=column,
            row=index + 2,
        )
    return values


def _one_column(assignments: dict[str, str], role: str) -> str | None:
    matches = [column for column, assigned in assignments.items() if assigned == role]
    if len(matches) > 1:
        raise ShapCompositeError(
            f"shap_{role}_conflict",
            f"Only one source column can be assigned to {role}.",
        )
    return matches[0] if matches else None


def _sparse_numeric_by_key(
    frame: pd.DataFrame,
    *,
    key_values: np.ndarray,
    key_order: tuple[str, ...],
    value_column: str,
    role_name: str,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in key_order:
        subset = frame.loc[key_values == key, value_column].dropna().to_numpy(dtype=float)
        if subset.size == 0:
            raise ShapCompositeError(
                f"shap_{role_name}_missing",
                f"Column {value_column!r} needs one finite {role_name} value for {key!r}.",
                column=value_column,
            )
        if not np.all(np.isfinite(subset)):
            raise ShapCompositeError(
                f"shap_{role_name}_nonfinite",
                f"Column {value_column!r} contains a non-finite {role_name} value for {key!r}.",
                column=value_column,
            )
        first = float(subset[0])
        if not np.allclose(subset, first, rtol=1e-9, atol=1e-12):
            raise ShapCompositeError(
                f"shap_{role_name}_inconsistent",
                f"Column {value_column!r} must be constant within {key!r}.",
                column=value_column,
            )
        result[key] = first
    return result


def _feature_order(
    frame: pd.DataFrame,
    *,
    features: np.ndarray,
    input_order: tuple[str, ...],
    order_column: str | None,
) -> tuple[str, ...]:
    if order_column is None:
        return input_order
    order_values = _sparse_numeric_by_key(
        frame,
        key_values=features,
        key_order=input_order,
        value_column=order_column,
        role_name="feature_order",
    )
    ordered_values = tuple(order_values[feature] for feature in input_order)
    if len(set(ordered_values)) != len(ordered_values):
        raise ShapCompositeError(
            "shap_feature_order_duplicate",
            f"Column {order_column!r} must assign a unique display order to every feature.",
            column=order_column,
        )
    return tuple(sorted(input_order, key=lambda feature: order_values[feature]))


def _mean_absolute_values(
    frame: pd.DataFrame,
    *,
    features: np.ndarray,
    feature_order: tuple[str, ...],
    shap_column: str,
) -> dict[str, float]:
    shap_values = frame[shap_column].to_numpy(dtype=float, copy=True)
    if not np.all(np.isfinite(shap_values)):
        raise ShapCompositeError(
            "shap_value_nonfinite",
            f"Column {shap_column!r} must contain only finite precomputed SHAP values.",
            column=shap_column,
        )
    return {
        feature: float(np.mean(np.abs(shap_values[features == feature])))
        for feature in feature_order
    }


def _validated_mean_absolute_values(
    frame: pd.DataFrame,
    *,
    features: np.ndarray,
    feature_order: tuple[str, ...],
    shap_column: str,
    mean_abs_column: str | None,
) -> tuple[ShapSummarySource, dict[str, float]]:
    calculated = _mean_absolute_values(
        frame,
        features=features,
        feature_order=feature_order,
        shap_column=shap_column,
    )
    if mean_abs_column is None:
        return "derived_from_supplied_shap", calculated
    provided = _sparse_numeric_by_key(
        frame,
        key_values=features,
        key_order=feature_order,
        value_column=mean_abs_column,
        role_name="mean_abs",
    )
    for feature in feature_order:
        expected = calculated[feature]
        actual = provided[feature]
        if actual < 0.0 or not math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-9):
            raise ShapCompositeError(
                "shap_mean_abs_mismatch",
                f"Provided Mean |SHAP| for {feature!r} does not match the supplied SHAP rows; "
                "correct the summary column or omit it so EditaPlot can derive it transparently.",
                column=mean_abs_column,
            )
    return "provided", provided


def _feature_groups(
    frame: pd.DataFrame,
    *,
    features: np.ndarray,
    feature_order: tuple[str, ...],
    group_column: str,
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    groups: list[tuple[str, str]] = []
    for feature in feature_order:
        raw = frame.loc[features == feature, group_column]
        values = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in raw
                if str(value).strip() and str(value).strip().casefold() != "nan"
            )
        )
        if len(values) != 1:
            code = "shap_feature_group_missing" if not values else "shap_feature_group_inconsistent"
            raise ShapCompositeError(
                code,
                f"Column {group_column!r} must assign exactly one non-empty group to {feature!r}.",
                column=group_column,
            )
        groups.append((feature, values[0]))
    group_order = tuple(dict.fromkeys(group for _feature, group in groups))
    if not 2 <= len(group_order) <= 5:
        raise ShapCompositeError(
            "shap_group_count",
            "Grouped SHAP composition needs between two and five feature groups.",
            column=group_column,
        )
    return tuple(groups), group_order


def _derived_group_contributions(
    *,
    mean_abs: dict[str, float],
    feature_groups: tuple[tuple[str, str], ...],
    group_order: tuple[str, ...],
) -> dict[str, float]:
    totals = {group: 0.0 for group in group_order}
    for feature, group in feature_groups:
        totals[group] += mean_abs[feature]
    overall = float(sum(totals.values()))
    if overall <= 0.0:
        raise ShapCompositeError(
            "shap_group_total_zero",
            "Grouped SHAP contribution cannot be calculated because all Mean |SHAP| values are zero.",
        )
    return {group: totals[group] * 100.0 / overall for group in group_order}


def _validated_group_contributions(
    frame: pd.DataFrame,
    *,
    row_groups: np.ndarray,
    group_order: tuple[str, ...],
    calculated: dict[str, float],
    contribution_column: str | None,
) -> tuple[ShapSummarySource, dict[str, float]]:
    if contribution_column is None:
        return "derived_from_supplied_shap", calculated
    provided = _sparse_numeric_by_key(
        frame,
        key_values=row_groups,
        key_order=group_order,
        value_column=contribution_column,
        role_name="group_contribution",
    )
    if not math.isclose(sum(provided.values()), 100.0, rel_tol=0.0, abs_tol=0.5):
        raise ShapCompositeError(
            "shap_group_contribution_total",
            f"Column {contribution_column!r} must sum to 100% (rounding tolerance ±0.5 percentage points).",
            column=contribution_column,
        )
    for group in group_order:
        actual = provided[group]
        if not 0.0 <= actual <= 100.0 or not math.isclose(
            actual,
            calculated[group],
            rel_tol=0.0,
            abs_tol=0.5,
        ):
            raise ShapCompositeError(
                "shap_group_contribution_mismatch",
                f"Provided contribution for group {group!r} does not match the supplied SHAP rows.",
                column=contribution_column,
            )
    return "provided", provided


def build_shap_composite_plan(
    frame: pd.DataFrame,
    assignments: dict[str, str],
    *,
    profile: str,
) -> ShapCompositePlan:
    """Validate and freeze the display summaries for a selected SHAP profile."""
    if profile not in SHAP_COMPOSITE_PROFILES:
        raise ShapCompositeError(
            "shap_profile_invalid",
            f"Unknown SHAP display profile: {profile!r}.",
        )
    feature_column = _one_column(assignments, "feature")
    shap_column = _one_column(assignments, "shap")
    if feature_column is None or shap_column is None:
        raise ShapCompositeError(
            "shap_roles_missing",
            "SHAP composite planning needs Feature and precomputed SHAP value columns.",
        )
    order_column = _one_column(assignments, "feature_order")
    sample_id_column = _one_column(assignments, "sample_id")
    mean_abs_column = _one_column(assignments, "mean_abs_shap")
    group_column = _one_column(assignments, "feature_group")
    contribution_column = _one_column(assignments, "group_contribution")

    features = _normalised_feature_values(frame, feature_column)
    input_order = tuple(dict.fromkeys(features.tolist()))
    feature_order = _feature_order(
        frame,
        features=features,
        input_order=input_order,
        order_column=order_column,
    )
    if profile == "beeswarm_only":
        return ShapCompositePlan(
            layout_version=SHAP_COMPOSITE_LAYOUT_VERSION,
            profile=profile,
            feature_order=feature_order,
            feature_order_column=order_column,
            sample_id_column=sample_id_column,
            mean_abs_column=mean_abs_column,
            mean_abs_source="not_used",
            mean_abs_values=(),
            feature_group_column=group_column,
            feature_groups=(),
            group_order=(),
            group_contribution_column=contribution_column,
            group_contribution_source="not_used",
            group_contributions=(),
        )

    mean_abs_source, mean_abs = _validated_mean_absolute_values(
        frame,
        features=features,
        feature_order=feature_order,
        shap_column=shap_column,
        mean_abs_column=mean_abs_column,
    )
    if profile == "beeswarm_mean_abs":
        return ShapCompositePlan(
            layout_version=SHAP_COMPOSITE_LAYOUT_VERSION,
            profile=profile,
            feature_order=feature_order,
            feature_order_column=order_column,
            sample_id_column=sample_id_column,
            mean_abs_column=mean_abs_column,
            mean_abs_source=mean_abs_source,
            mean_abs_values=tuple((feature, mean_abs[feature]) for feature in feature_order),
            feature_group_column=group_column,
            feature_groups=(),
            group_order=(),
            group_contribution_column=contribution_column,
            group_contribution_source="not_used",
            group_contributions=(),
        )

    if group_column is None:
        raise ShapCompositeError(
            "shap_feature_group_missing",
            "The grouped SHAP profile needs a Feature Group / 特征组 column.",
        )
    feature_groups, group_order = _feature_groups(
        frame,
        features=features,
        feature_order=feature_order,
        group_column=group_column,
    )
    group_by_feature = dict(feature_groups)
    row_groups = np.asarray([group_by_feature[feature] for feature in features], dtype=object)
    calculated_group_contributions = _derived_group_contributions(
        mean_abs=mean_abs,
        feature_groups=feature_groups,
        group_order=group_order,
    )
    contribution_source, contributions = _validated_group_contributions(
        frame,
        row_groups=row_groups,
        group_order=group_order,
        calculated=calculated_group_contributions,
        contribution_column=contribution_column,
    )
    return ShapCompositePlan(
        layout_version=SHAP_COMPOSITE_LAYOUT_VERSION,
        profile=profile,
        feature_order=feature_order,
        feature_order_column=order_column,
        sample_id_column=sample_id_column,
        mean_abs_column=mean_abs_column,
        mean_abs_source=mean_abs_source,
        mean_abs_values=tuple((feature, mean_abs[feature]) for feature in feature_order),
        feature_group_column=group_column,
        feature_groups=feature_groups,
        group_order=group_order,
        group_contribution_column=contribution_column,
        group_contribution_source=contribution_source,
        group_contributions=tuple((group, contributions[group]) for group in group_order),
    )


__all__ = [
    "SHAP_COMPOSITE_LAYOUT_VERSION",
    "SHAP_COMPOSITE_PROFILES",
    "ShapCompositeError",
    "ShapCompositePlan",
    "ShapCompositeProfile",
    "ShapSummarySource",
    "build_shap_composite_plan",
]
