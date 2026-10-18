from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime" / "src"))
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
)


@pytest.mark.parametrize("component_count", [2, 4, 8])
@pytest.mark.parametrize("with_total_sd", [False, True])
def test_stacked_axis_covers_sums_and_supplied_total_error(
    tmp_path: Path, component_count: int, with_total_sd: bool
) -> None:
    frame = pd.DataFrame({"Category": ["A", "B", "C"]})
    columns = [f"Part {i + 1}" for i in range(component_count)]
    for i, column in enumerate(columns):
        frame[column] = [10 + i, 14 + i, 18 + i]
    if with_total_sd:
        frame["Total_SD"] = [2.0, 3.0, 4.0]
    source = tmp_path / "stacked.csv"
    frame.to_csv(source, index=False)
    original = source.read_bytes()
    result = prepare_scientific(source, "stacked_bar")
    axis = result.plot_spec.axis_plan
    upper = frame[columns].sum(axis=1)
    if with_total_sd:
        upper = upper + frame["Total_SD"]
    assert axis.y_from == 0
    assert axis.y_to > float(upper.max())
    assert axis.y_step > 0
    assert source.read_bytes() == original


def test_total_error_lower_bound_is_not_clipped_at_zero(tmp_path: Path) -> None:
    source = tmp_path / "large_error.csv"
    source.write_text("Category,Part A,Part B,Total_SD\nA,1,2,8\nB,2,3,9\n", encoding="utf-8")
    result = prepare_scientific(source, "stacked_bar")
    assert result.plot_spec.axis_plan.y_from < -5
    assert result.plot_spec.axis_plan.y_to > 14


def test_percent_axis_matches_the_confirmed_display_normalization(tmp_path: Path) -> None:
    source = tmp_path / "percent.csv"
    source.write_text("Category,Part A,Part B\nA,1,2\nB,20,50\nC,1000,3000\n", encoding="utf-8")
    original = source.read_bytes()
    result = prepare_scientific(source, "percent_stacked_bar")
    axis = result.plot_spec.axis_plan
    assert (axis.y_from, axis.y_to, axis.y_step) == (0, 100, 20)
    assert source.read_bytes() == original


@pytest.mark.parametrize("template", ["stacked_bar", "percent_stacked_bar"])
def test_missing_composition_is_not_silently_treated_as_zero(tmp_path: Path, template: str) -> None:
    source = tmp_path / "missing_part.csv"
    source.write_text("Category,Part A,Part B\nA,1,2\nB,,3\nC,4,5\n", encoding="utf-8")
    original = source.read_bytes()
    with pytest.raises(ScientificWorkflowError) as error:
        prepare_scientific(source, template)
    assert error.value.code == "composition_missing_value"
    assert source.read_bytes() == original


def test_percent_uncertainty_is_not_silently_included_in_the_denominator(tmp_path: Path) -> None:
    source = tmp_path / "percent_with_sd.csv"
    source.write_text("Category,Part A,Part B,Part A_SD\nA,10,20,1\nB,20,30,2\n", encoding="utf-8")
    original = source.read_bytes()
    result = prepare_scientific(source, "percent_stacked_bar")
    assert dict(result.assignments)["Part A_SD"] == "ignored"
    assert len(result.plot_spec.series) == 2
    assert result.requires_confirmation
    assert "percent_error_columns_retained" in result.warnings
    assert source.read_bytes() == original


def test_explicit_percentage_error_role_needs_an_uncertainty_aware_route(tmp_path: Path) -> None:
    source = tmp_path / "explicit_error.csv"
    source.write_text("Category,Part A,Part B,Part A_SD\nA,10,20,1\nB,20,30,2\n", encoding="utf-8")
    mapping = ScientificColumnMapping(
        (
            ("Category", "category"),
            ("Part A", "series"),
            ("Part B", "series"),
            ("Part A_SD", "error"),
        )
    )
    with pytest.raises(ScientificWorkflowError) as error:
        prepare_scientific(source, "percent_stacked_bar", column_mapping=mapping)
    assert error.value.code == "mapping_unknown_role"


def test_explicit_component_role_can_override_an_error_like_header(tmp_path: Path) -> None:
    source = tmp_path / "confirmed_component.csv"
    source.write_text("Category,Part A,Part B,Part A_SD\nA,10,20,1\nB,20,30,2\n", encoding="utf-8")
    mapping = ScientificColumnMapping(
        (
            ("Category", "category"),
            ("Part A", "series"),
            ("Part B", "series"),
            ("Part A_SD", "series"),
        )
    )
    result = prepare_scientific(source, "percent_stacked_bar", column_mapping=mapping)
    assert len(result.plot_spec.series) == 3
    assert dict(result.assignments)["Part A_SD"] == "series"
    assert "percent_error_columns_retained" not in result.warnings


def test_radar_frozen_axis_records_the_shared_native_score_scale(tmp_path: Path) -> None:
    source = tmp_path / "radar.csv"
    source.write_text("Metric,A,B\nM1,0.5,0.7\nM2,0.6,0.8\nM3,0.4,0.9\n", encoding="utf-8")
    result = prepare_scientific(source, "radar")
    axis = result.plot_spec.axis_plan
    assert (axis.y_from, axis.y_to, axis.y_step) == (0, 1, 0.2)
