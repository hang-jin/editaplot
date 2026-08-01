from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
RUNTIME_SRC = RUNTIME / "src"
SKILL_SCRIPTS = ROOT / "skill" / "editaplot" / "scripts"
for path in (RUNTIME_SRC, SKILL_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from editaplot_core import (  # noqa: E402
    AUTO_SCORE_THRESHOLD,
    VERIFIED_TEMPLATE_IDS,
    _score_candidate,
    inspect_data,
    recommend_charts,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificWorkflowError,
    prepare_scientific,
)
from origin_sciplot.template_registry import TemplateRegistry  # noqa: E402

TEMPLATE = RUNTIME / "templates" / "density_ridgeline3d"
EXAMPLE = TEMPLATE / "example_standard.csv"


def test_density_ridgeline3d_is_registered_and_promoted() -> None:
    registry = TemplateRegistry(RUNTIME / "templates")
    manifest = registry.get("density_ridgeline3d")

    assert manifest.version == "1.0.0"
    assert manifest.status == "implemented"
    assert manifest.visibility == "public"
    assert manifest.workflow == "scientific_table"
    assert manifest.raw["origin_acceptance"] == "origin_acceptance.md"
    assert manifest.id in VERIFIED_TEMPLATE_IDS
    assert manifest.id in {item.id for item in registry.implemented()}
    assert manifest.id not in {item.id for item in registry.internal_implemented()}


def test_density_ridgeline3d_schema_freezes_one_mixed_wide_contract() -> None:
    schema = json.loads((TEMPLATE / "schema.json").read_text(encoding="utf-8"))

    assert schema["layout"] == "precomputed_dual_density_mixed_wide"
    assert schema["required_roles"] == [
        "condition_id",
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
    ]
    assert schema["axis_roles_requiring_semantic_name_and_unit"] == [
        "density_x",
        "condition_position",
        "density_solid",
        "density_dashed",
    ]
    assert schema["min_conditions"] == 2
    assert schema["max_conditions"] == 6
    assert schema["min_points_per_condition"] == 5
    assert schema["condition_position_order"].startswith("strictly_increasing")
    assert schema["density_x_direction_across_conditions"].startswith("all_conditions")
    assert schema["condition_axis_year_aliases_use_implicit_unit"] == ["Year", "年份", "年度"]
    assert schema["focal_x_constraint"].startswith("exactly_one_finite_nonempty_value")
    assert schema["threshold_named_column_requires_user_confirmation_as_focal_x"] is True
    assert schema["automatic_kde"] is False
    assert schema["automatic_interpolation"] is False
    assert schema["automatic_focal_calculation"] is False


def test_original_synthetic_example_obeys_mixed_wide_density_contract() -> None:
    before = EXAMPLE.read_bytes()
    with EXAMPLE.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    assert list(rows[0]) == [
        "Condition ID",
        "Follow-up Time (month)",
        "Response Score (a.u.)",
        "Solid Density (a.u.)",
        "Dashed Density (a.u.)",
        "Focal X (a.u.)",
    ]
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["Condition ID"]].append(row)
    assert 2 <= len(grouped) <= 6

    condition_positions: dict[str, float] = {}
    for condition_id, group in grouped.items():
        assert condition_id
        assert len(group) >= 5
        positions = {float(row["Follow-up Time (month)"]) for row in group}
        assert len(positions) == 1
        condition_positions[condition_id] = positions.pop()
        x_values = [float(row["Response Score (a.u.)"]) for row in group]
        assert all(right > left for left, right in zip(x_values, x_values[1:], strict=False))
        assert all(float(row["Solid Density (a.u.)"]) >= 0 for row in group)
        assert all(float(row["Dashed Density (a.u.)"]) >= 0 for row in group)
        focal_values = [float(row["Focal X (a.u.)"]) for row in group if row["Focal X (a.u.)"]]
        assert len(focal_values) == 1
        assert min(x_values) <= focal_values[0] <= max(x_values)

    assert len(set(condition_positions.values())) == len(condition_positions)
    assert EXAMPLE.read_bytes() == before


def test_cli_detects_only_the_complete_unit_bearing_mixed_wide_contract(tmp_path: Path) -> None:
    before = EXAMPLE.read_bytes()
    result = inspect_data(EXAMPLE, engine_home=RUNTIME)

    assert "density_ridgeline3d_mixed_wide" in result["table"]["layouts"]
    assert result["domain_signals"]["density_ridgeline3d"] == 6
    detection = result["table"]["density_ridgeline3d_detection"]
    assert detection == {
        "detected_role_count": 6,
        "required_role_count": 6,
        "candidate": True,
        "strict": True,
        "requires_confirmation": False,
        "role_columns": {
            "condition_id": "Condition ID",
            "condition_position": "Follow-up Time (month)",
            "density_x": "Response Score (a.u.)",
            "density_solid": "Solid Density (a.u.)",
            "density_dashed": "Dashed Density (a.u.)",
            "focal_x": "Focal X (a.u.)",
        },
        "issues": [],
    }
    assert EXAMPLE.read_bytes() == before

    no_x_unit = tmp_path / "missing-density-x-unit.csv"
    no_x_unit.write_text(
        EXAMPLE.read_text(encoding="utf-8").replace(
            "Response Score (a.u.)", "Density X", 1
        ),
        encoding="utf-8",
    )
    incomplete = inspect_data(no_x_unit, engine_home=RUNTIME)
    incomplete_detection = incomplete["table"]["density_ridgeline3d_detection"]
    assert "density_ridgeline3d_candidate" in incomplete["table"]["layouts"]
    assert "density_ridgeline3d_mixed_wide" not in incomplete["table"]["layouts"]
    assert incomplete["domain_signals"]["density_ridgeline3d"] == 0
    assert incomplete_detection["requires_confirmation"] is True
    assert "density_x_semantic_name_or_unit_missing" in incomplete_detection["issues"]


def test_duplicate_focal_value_is_a_conflict_and_scores_below_auto_gate(tmp_path: Path) -> None:
    duplicate_focal = tmp_path / "duplicate-focal.csv"
    duplicate_focal.write_text(
        EXAMPLE.read_text(encoding="utf-8").replace(
            "Month 0,0,0.45,2.55,1.65,\n",
            "Month 0,0,0.45,2.55,1.65,0.47\n",
            1,
        ),
        encoding="utf-8",
    )
    conflicted = inspect_data(duplicate_focal, engine_home=RUNTIME)
    conflicted_detection = conflicted["table"]["density_ridgeline3d_detection"]

    assert conflicted_detection["candidate"] is True
    assert conflicted_detection["strict"] is False
    assert conflicted_detection["requires_confirmation"] is True
    assert "focal_x_must_have_exactly_one_finite_value_per_condition" in conflicted_detection["issues"]
    assert conflicted["domain_signals"]["density_ridgeline3d"] == 0

    strict = inspect_data(EXAMPLE, engine_home=RUNTIME)
    strict_score, strict_codes, _ = _score_candidate(
        "density_ridgeline3d",
        SimpleNamespace(confidence=0.98, requires_confirmation=False),
        strict,
        "三维密度曲线与基线焦点",
    )
    conflict_score, conflict_codes, _ = _score_candidate(
        "density_ridgeline3d",
        SimpleNamespace(confidence=0.98, requires_confirmation=True),
        conflicted,
        "三维密度曲线与基线焦点",
    )

    assert strict_score >= AUTO_SCORE_THRESHOLD
    assert "explicit_precomputed_dual_density_3d_match" in strict_codes
    assert conflict_score < AUTO_SCORE_THRESHOLD
    assert "density_ridgeline3d_role_conflict_requires_confirmation" in conflict_codes
    assert "column_confirmation_required" in conflict_codes


def _loaded_example_rows() -> list[dict[str, str]]:
    with EXAMPLE.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _renamed_rows(
    rows: list[dict[str, str]],
    replacements: dict[str, str],
) -> list[dict[str, str]]:
    return [
        {replacements.get(column, column): value for column, value in row.items()}
        for row in rows
    ]


@pytest.mark.parametrize(
    "variant",
    [
        "numeric_condition_id",
        "year_and_dimensionless_x",
        "explicit_dimensionless_density",
    ],
)
def test_cli_strict_detection_matches_runtime_for_accepted_contract_variants(
    tmp_path: Path,
    variant: str,
) -> None:
    rows = _loaded_example_rows()
    if variant == "numeric_condition_id":
        condition_ids = {
            condition: str(index)
            for index, condition in enumerate(
                dict.fromkeys(row["Condition ID"] for row in rows),
                start=1,
            )
        }
        for row in rows:
            row["Condition ID"] = condition_ids[row["Condition ID"]]
    elif variant == "year_and_dimensionless_x":
        rows = _renamed_rows(
            rows,
            {
                "Follow-up Time (month)": "Year",
                "Response Score (a.u.)": "Response Score dimensionless",
            },
        )
    else:
        rows = _renamed_rows(
            rows,
            {
                "Solid Density (a.u.)": "Solid Density dimensionless",
                "Dashed Density (a.u.)": "Dashed Density 无量纲",
            },
        )
    source = _write_rows(tmp_path / f"accepted-{variant}.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")
    detection = inspect_data(source, engine_home=RUNTIME)["table"][
        "density_ridgeline3d_detection"
    ]

    assert preparation.plot_spec.plot_kind == "density_ridgeline3d"
    assert detection["candidate"] is True
    assert detection["strict"] is True
    assert detection["requires_confirmation"] is False
    assert detection["issues"] == []


@pytest.mark.parametrize(
    ("variant", "runtime_code", "cli_issue"),
    [
        (
            "solid_density_unit_missing",
            "density_ridgeline3d_density_semantics_missing",
            "density_solid_semantic_name_or_unit_missing",
        ),
        (
            "density_unit_mismatch",
            "density_ridgeline3d_density_unit_mismatch",
            "density_units_mismatch",
        ),
        (
            "x_direction_mismatch",
            "density_ridgeline3d_x_direction_mismatch",
            "density_x_direction_mismatch_between_conditions",
        ),
        (
            "condition_order_invalid",
            "density_ridgeline3d_condition_order_invalid",
            "condition_positions_not_strictly_increasing_in_first_appearance_order",
        ),
    ],
)
def test_cli_conflicts_match_runtime_rejections_and_block_auto_selection(
    tmp_path: Path,
    variant: str,
    runtime_code: str,
    cli_issue: str,
) -> None:
    rows = _loaded_example_rows()
    if variant == "solid_density_unit_missing":
        rows = _renamed_rows(rows, {"Solid Density (a.u.)": "Solid Density"})
    elif variant == "density_unit_mismatch":
        rows = _renamed_rows(rows, {"Dashed Density (a.u.)": "Dashed Density (counts)"})
    elif variant == "x_direction_mismatch":
        conditions = list(dict.fromkeys(row["Condition ID"] for row in rows))
        selected = [row for row in rows if row["Condition ID"] == conditions[1]]
        reversed_x = [row["Response Score (a.u.)"] for row in reversed(selected)]
        for row, x_value in zip(selected, reversed_x, strict=True):
            row["Response Score (a.u.)"] = x_value
    else:
        conditions = list(dict.fromkeys(row["Condition ID"] for row in rows))
        for row in rows:
            if row["Condition ID"] == conditions[-1]:
                row["Follow-up Time (month)"] = "-1"
    source = _write_rows(tmp_path / f"rejected-{variant}.csv", rows)

    with pytest.raises(ScientificWorkflowError) as caught:
        prepare_scientific(source, "density_ridgeline3d")
    assert caught.value.code == runtime_code

    inspection = inspect_data(source, engine_home=RUNTIME)
    detection = inspection["table"]["density_ridgeline3d_detection"]
    assert detection["candidate"] is True
    assert detection["strict"] is False
    assert detection["requires_confirmation"] is True
    assert cli_issue in detection["issues"]
    assert inspection["domain_signals"]["density_ridgeline3d"] == 0

    recommendation = recommend_charts(
        source,
        intent="三维密度双轮廓和用户提供的基线焦点",
        engine_home=RUNTIME,
    )
    assert recommendation["auto_selection"]["allowed"] is False
    assert (
        "density_ridgeline3d_contract_requires_confirmation"
        in recommendation["auto_selection"]["gate_reasons"]
    )


def test_low_confidence_density_mapping_cannot_pass_auto_selection(tmp_path: Path) -> None:
    rows = [{**row, "Notes": "retained, not rendered"} for row in _loaded_example_rows()]
    source = _write_rows(tmp_path / "density-extra-column.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")
    assert preparation.requires_confirmation is True
    assert preparation.confidence < AUTO_SCORE_THRESHOLD

    recommendation = recommend_charts(
        source,
        intent="三维密度双轮廓和用户提供的基线焦点",
        engine_home=RUNTIME,
    )
    density_candidate = next(
        candidate
        for candidate in recommendation["candidates"]
        if candidate["template_id"] == "density_ridgeline3d"
    )
    assert density_candidate["requires_column_confirmation"] is True
    assert recommendation["auto_selection"]["allowed"] is False
    assert (
        "density_ridgeline3d_mapping_requires_confirmation"
        in recommendation["auto_selection"]["gate_reasons"]
    )


def test_threshold_named_locator_cannot_pass_density_auto_selection(
    tmp_path: Path,
) -> None:
    rows = _renamed_rows(
        _loaded_example_rows(),
        {"Focal X (a.u.)": "Threshold X (a.u.)"},
    )
    source = _write_rows(tmp_path / "density-threshold-locator.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")
    assert preparation.requires_confirmation is True
    assert "focal_x_role_inferred" in preparation.confirmation_reasons

    inspection = inspect_data(source, engine_home=RUNTIME)
    detection = inspection["table"]["density_ridgeline3d_detection"]
    assert detection["strict"] is False
    assert inspection["domain_signals"]["density_ridgeline3d"] == 0

    recommendation = recommend_charts(
        source,
        intent="三维密度双轮廓和用户提供的基线焦点",
        engine_home=RUNTIME,
    )
    assert all(
        candidate["template_id"] != "density_ridgeline3d"
        for candidate in recommendation["candidates"]
    )
    assert recommendation["auto_selection"]["allowed"] is False
    assert (
        "density_ridgeline3d_mapping_requires_confirmation"
        in recommendation["auto_selection"]["gate_reasons"]
    )
