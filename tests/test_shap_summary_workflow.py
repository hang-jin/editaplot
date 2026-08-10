from __future__ import annotations

import csv
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    _scientific_plan_digest,
    prepare_scientific,
    role_options,
)
from origin_sciplot.shap_composite import (  # noqa: E402
    SHAP_COMPOSITE_LAYOUT_VERSION,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _base_rows() -> list[dict[str, object]]:
    return [
        {"Feature": "Texture", "SHAP value": -2.0, "Feature value": 0.1},
        {"Feature": "Texture", "SHAP value": 0.0, "Feature value": 0.5},
        {"Feature": "Texture", "SHAP value": 2.0, "Feature value": 0.9},
        {"Feature": "Shape", "SHAP value": -1.0, "Feature value": 0.2},
        {"Feature": "Shape", "SHAP value": 1.0, "Feature value": 0.6},
        {"Feature": "Shape", "SHAP value": 3.0, "Feature value": 1.0},
    ]


def _composite_rows(*, chinese: bool = False) -> list[dict[str, object]]:
    names = (
        {
            "feature": "特征",
            "shap": "SHAP值",
            "feature_value": "特征值",
            "sample": "样本编号",
            "order": "显示顺序",
            "mean_abs": "平均绝对SHAP",
            "group": "特征组",
            "group_contribution": "组贡献百分比",
        }
        if chinese
        else {
            "feature": "Feature",
            "shap": "SHAP value",
            "feature_value": "Feature value",
            "sample": "Sample ID",
            "order": "Feature Order",
            "mean_abs": "Mean absolute SHAP",
            "group": "Feature Group",
            "group_contribution": "Group contribution (%)",
        }
    )
    definitions = (
        # Feature order is intentionally different from source row order.
        ("Texture", 2, "Imaging", 2.0, 3.0 / 7.0 * 100.0, (-3.0, 1.0, 2.0)),
        ("Age", 1, "Clinical", 4.0, 4.0 / 7.0 * 100.0, (-6.0, 2.0, 4.0)),
        ("Shape", 3, "Imaging", 1.0, 3.0 / 7.0 * 100.0, (-1.0, 0.0, 2.0)),
    )
    rows: list[dict[str, object]] = []
    for feature, order, group, mean_abs, contribution, shap_values in definitions:
        for sample_index, shap_value in enumerate(shap_values, start=1):
            rows.append(
                {
                    names["feature"]: feature,
                    names["shap"]: shap_value,
                    names["feature_value"]: sample_index / 3.0,
                    names["sample"]: f"S{sample_index:02d}",
                    names["order"]: order,
                    names["mean_abs"]: mean_abs,
                    names["group"]: group,
                    names["group_contribution"]: contribution,
                }
            )
    return rows


def _mapping_for(columns: list[str], roles: dict[str, str], *, plot_mode: str):
    return ScientificColumnMapping(
        assignments=tuple((column, roles.get(column, "ignored")) for column in columns),
        plot_mode=plot_mode,
    )


def _sparse_summary_cells(rows: list[dict[str, object]]) -> None:
    """Keep one summary cell per feature/group, as exported tables commonly do."""
    seen_features: set[str] = set()
    seen_groups: set[str] = set()
    for row in rows:
        feature = str(row["Feature"])
        group = str(row["Feature Group"])
        if feature in seen_features:
            row["Feature Order"] = ""
            row["Mean absolute SHAP"] = ""
            row["Feature Group"] = ""
        else:
            seen_features.add(feature)
        if group in seen_groups:
            row["Group contribution (%)"] = ""
        else:
            seen_groups.add(group)


def _assert_error(
    code: str | tuple[str, ...],
    operation,
) -> ScientificWorkflowError:
    with pytest.raises(ScientificWorkflowError) as caught:
        operation()
    accepted = (code,) if isinstance(code, str) else code
    assert caught.value.code in accepted
    return caught.value


def _pairs(value: object) -> dict[str, object]:
    return dict(value)  # type: ignore[arg-type]


def test_legacy_three_column_input_remains_valid_and_derives_mean_abs(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "legacy_shap.csv", _base_rows())
    before = source.read_bytes()

    preparation = prepare_scientific(source, "shap_summary")

    assert source.read_bytes() == before
    assert dict(preparation.assignments) == {
        "Feature": "feature",
        "SHAP value": "shap",
        "Feature value": "feature_value",
    }
    assert preparation.plot_spec.plot_mode == "beeswarm_mean_abs"
    plan = preparation.plot_spec.shap_plan
    assert plan.layout_version == SHAP_COMPOSITE_LAYOUT_VERSION
    assert asdict(plan)["layout_version"] == SHAP_COMPOSITE_LAYOUT_VERSION
    assert plan.profile == "beeswarm_mean_abs"
    assert plan.feature_order == ("Texture", "Shape")
    assert plan.mean_abs_source == "derived_from_supplied_shap"
    assert _pairs(plan.mean_abs_values) == pytest.approx(
        {"Texture": 4.0 / 3.0, "Shape": 5.0 / 3.0}
    )
    assert plan.feature_groups == ()
    assert plan.group_contributions == ()


def test_layout_version_is_part_of_the_frozen_scientific_plan_digest(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "layout_version.csv", _base_rows())
    preparation = prepare_scientific(source, "shap_summary")
    plan = preparation.plot_spec.shap_plan

    changed_plan = replace(plan, layout_version="shap-composite-layout-test-next")
    changed_spec = replace(preparation.plot_spec, shap_plan=changed_plan)

    assert _scientific_plan_digest(preparation, changed_spec) != preparation.plan_digest


@pytest.mark.parametrize("chinese", [False, True], ids=["english", "chinese"])
def test_optional_composite_columns_are_recognised_bilingually(
    tmp_path: Path,
    chinese: bool,
) -> None:
    rows = _composite_rows(chinese=chinese)
    source = _write_csv(tmp_path / f"composite_{chinese}.csv", rows)

    preparation = prepare_scientific(source, "shap_summary")

    expected_roles = (
        {
            "特征": "feature",
            "SHAP值": "shap",
            "特征值": "feature_value",
            "样本编号": "sample_id",
            "显示顺序": "feature_order",
            "平均绝对SHAP": "mean_abs_shap",
            "特征组": "feature_group",
            "组贡献百分比": "group_contribution",
        }
        if chinese
        else {
            "Feature": "feature",
            "SHAP value": "shap",
            "Feature value": "feature_value",
            "Sample ID": "sample_id",
            "Feature Order": "feature_order",
            "Mean absolute SHAP": "mean_abs_shap",
            "Feature Group": "feature_group",
            "Group contribution (%)": "group_contribution",
        }
    )
    assert dict(preparation.assignments) == expected_roles
    assert preparation.requires_confirmation is False
    assert preparation.plot_spec.plot_mode == "beeswarm_mean_abs_grouped"
    plan = preparation.plot_spec.shap_plan
    assert plan.profile == "beeswarm_mean_abs_grouped"
    assert plan.feature_order == ("Age", "Texture", "Shape")
    assert plan.mean_abs_source == "provided"
    assert plan.group_contribution_source == "provided"
    assert _pairs(plan.mean_abs_values) == pytest.approx(
        {"Age": 4.0, "Texture": 2.0, "Shape": 1.0}
    )
    assert _pairs(plan.feature_groups) == {
        "Age": "Clinical",
        "Texture": "Imaging",
        "Shape": "Imaging",
    }
    assert plan.group_order == ("Clinical", "Imaging")
    assert _pairs(plan.group_contributions) == pytest.approx(
        {"Clinical": 4.0 / 7.0 * 100.0, "Imaging": 3.0 / 7.0 * 100.0}
    )


def test_mapping_ui_exposes_all_shap_roles_with_unique_bindings() -> None:
    options = {key: unique for key, _label, unique in role_options("shap_summary")}

    assert set(options) == {
        "feature",
        "shap",
        "feature_value",
        "sample_id",
        "feature_order",
        "mean_abs_shap",
        "feature_group",
        "group_contribution",
        "ignored",
    }
    assert all(options[role] for role in set(options) - {"ignored"})
    assert options["ignored"] is False


def test_manual_plot_mode_can_keep_a_beeswarm_only_profile(tmp_path: Path) -> None:
    rows = _base_rows()
    source = _write_csv(tmp_path / "manual_beeswarm.csv", rows)
    columns = list(rows[0])
    mapping = _mapping_for(
        columns,
        {
            "Feature": "feature",
            "SHAP value": "shap",
            "Feature value": "feature_value",
        },
        plot_mode="beeswarm_only",
    )

    preparation = prepare_scientific(source, "shap_summary", column_mapping=mapping)

    assert preparation.mapping_confirmed is True
    assert preparation.plot_spec.plot_mode == "beeswarm_only"
    assert preparation.plot_spec.shap_plan.profile == "beeswarm_only"


def test_legacy_precomputed_long_plot_mode_maps_to_beeswarm_only(tmp_path: Path) -> None:
    rows = _base_rows()
    source = _write_csv(tmp_path / "legacy_plot_mode.csv", rows)
    columns = list(rows[0])
    mapping = _mapping_for(
        columns,
        {
            "Feature": "feature",
            "SHAP value": "shap",
            "Feature value": "feature_value",
        },
        plot_mode="precomputed_long",
    )

    preparation = prepare_scientific(source, "shap_summary", column_mapping=mapping)

    assert preparation.plot_spec.plot_mode == "beeswarm_only"
    assert preparation.plot_spec.shap_plan.profile == "beeswarm_only"


def test_manual_grouped_mode_requires_a_feature_group_column(tmp_path: Path) -> None:
    rows = _base_rows()
    source = _write_csv(tmp_path / "group_missing.csv", rows)
    columns = list(rows[0])
    mapping = _mapping_for(
        columns,
        {
            "Feature": "feature",
            "SHAP value": "shap",
            "Feature value": "feature_value",
        },
        plot_mode="beeswarm_mean_abs_grouped",
    )

    _assert_error(
        "shap_feature_group_missing",
        lambda: prepare_scientific(source, "shap_summary", column_mapping=mapping),
    )


def test_feature_order_is_constant_unique_and_controls_display_order(tmp_path: Path) -> None:
    rows = _composite_rows()
    source = _write_csv(tmp_path / "ordered.csv", rows)

    plan = prepare_scientific(source, "shap_summary").plot_spec.shap_plan

    assert plan.feature_order == ("Age", "Texture", "Shape")


def test_one_summary_cell_per_feature_or_group_is_allowed(tmp_path: Path) -> None:
    rows = _composite_rows()
    _sparse_summary_cells(rows)
    source = _write_csv(tmp_path / "sparse_summary_cells.csv", rows)

    plan = prepare_scientific(source, "shap_summary").plot_spec.shap_plan

    assert plan.feature_order == ("Age", "Texture", "Shape")
    assert plan.mean_abs_source == "provided"
    assert dict(plan.mean_abs_values) == pytest.approx(
        {"Age": 4.0, "Texture": 2.0, "Shape": 1.0}
    )
    assert dict(plan.feature_groups) == {
        "Age": "Clinical",
        "Texture": "Imaging",
        "Shape": "Imaging",
    }
    assert plan.group_contribution_source == "provided"
    assert dict(plan.group_contributions) == pytest.approx(
        {"Clinical": 4.0 / 7.0 * 100.0, "Imaging": 3.0 / 7.0 * 100.0}
    )


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda rows: rows[1].__setitem__("Feature Order", 4),
            "shap_feature_order_inconsistent",
        ),
        (
            lambda rows: [
                row.__setitem__("Feature Order", 1)
                for row in rows
                if row["Feature"] == "Texture"
            ],
            "shap_feature_order_duplicate",
        ),
        (
            lambda rows: [
                row.__setitem__("Feature Order", "")
                for row in rows
                if row["Feature"] == "Texture"
            ],
            "shap_feature_order_missing",
        ),
        (
            lambda rows: rows[0].__setitem__("Feature Order", "inf"),
            ("shap_feature_order_nonfinite", "non_finite"),
        ),
    ],
    ids=["within-feature", "duplicate", "missing", "nonfinite"],
)
def test_invalid_feature_order_is_rejected_without_silent_fallback(
    tmp_path: Path,
    mutate,
    code: str | tuple[str, ...],
) -> None:
    rows = _composite_rows()
    mutate(rows)
    source = _write_csv(tmp_path / "invalid_feature_order.csv", rows)

    _assert_error(code, lambda: prepare_scientific(source, "shap_summary"))


def test_supplied_mean_abs_must_be_constant_and_match_supplied_shap_rows(
    tmp_path: Path,
) -> None:
    inconsistent = _composite_rows()
    inconsistent[1]["Mean absolute SHAP"] = 2.5
    source = _write_csv(tmp_path / "mean_abs_inconsistent.csv", inconsistent)
    _assert_error(
        "shap_mean_abs_inconsistent",
        lambda: prepare_scientific(source, "shap_summary"),
    )

    mismatched = _composite_rows()
    for row in mismatched:
        if row["Feature"] == "Texture":
            row["Mean absolute SHAP"] = 3.0
    source = _write_csv(tmp_path / "mean_abs_mismatch.csv", mismatched)
    _assert_error(
        "shap_mean_abs_mismatch",
        lambda: prepare_scientific(source, "shap_summary"),
    )


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("", "shap_mean_abs_missing"),
        (
            "nan",
            ("shap_mean_abs_missing", "shap_mean_abs_nonfinite", "non_finite"),
        ),
        ("inf", ("shap_mean_abs_nonfinite", "non_finite")),
    ],
)
def test_supplied_mean_abs_rejects_missing_or_nonfinite_values(
    tmp_path: Path,
    value: str,
    code: str | tuple[str, ...],
) -> None:
    rows = _composite_rows()
    for row in rows:
        if row["Feature"] == "Texture":
            row["Mean absolute SHAP"] = value
    source = _write_csv(tmp_path / f"mean_abs_{value or 'blank'}.csv", rows)

    _assert_error(code, lambda: prepare_scientific(source, "shap_summary"))


def test_group_mapping_and_contribution_are_validated_against_feature_importance(
    tmp_path: Path,
) -> None:
    rows = _composite_rows()
    source = _write_csv(tmp_path / "grouped.csv", rows)

    plan = prepare_scientific(source, "shap_summary").plot_spec.shap_plan

    assert _pairs(plan.feature_groups) == {
        "Age": "Clinical",
        "Texture": "Imaging",
        "Shape": "Imaging",
    }
    assert _pairs(plan.group_contributions) == pytest.approx(
        {"Clinical": 4.0 / 7.0 * 100.0, "Imaging": 3.0 / 7.0 * 100.0}
    )


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda rows: rows[1].__setitem__("Feature Group", "Clinical"),
            "shap_feature_group_inconsistent",
        ),
        (
            lambda rows: [
                row.__setitem__("Feature Group", "")
                for row in rows
                if row["Feature"] == "Texture"
            ],
            "shap_feature_group_missing",
        ),
        (
            lambda rows: rows[1].__setitem__("Group contribution (%)", 55.0),
            "shap_group_contribution_inconsistent",
        ),
        (
            lambda rows: [
                row.__setitem__("Group contribution (%)", "")
                for row in rows
                if row["Feature Group"] == "Imaging"
            ],
            "shap_group_contribution_missing",
        ),
        (
            lambda rows: rows[0].__setitem__("Group contribution (%)", math.inf),
            ("shap_group_contribution_nonfinite", "non_finite"),
        ),
        (
            lambda rows: [
                row.__setitem__("Group contribution (%)", 50.0)
                for row in rows
            ],
            "shap_group_contribution_mismatch",
        ),
    ],
    ids=[
        "feature-group-inconsistent",
        "feature-group-missing",
        "contribution-inconsistent",
        "contribution-missing",
        "contribution-nonfinite",
        "contribution-mismatch",
    ],
)
def test_invalid_group_metadata_is_rejected(
    tmp_path: Path,
    mutate,
    code: str | tuple[str, ...],
) -> None:
    rows = _composite_rows()
    mutate(rows)
    source = _write_csv(tmp_path / "invalid_group_metadata.csv", rows)

    _assert_error(code, lambda: prepare_scientific(source, "shap_summary"))


def test_group_contribution_is_derived_when_source_column_is_absent(tmp_path: Path) -> None:
    rows = _composite_rows()
    for row in rows:
        row.pop("Group contribution (%)")
    source = _write_csv(tmp_path / "derived_group_contribution.csv", rows)

    plan = prepare_scientific(source, "shap_summary").plot_spec.shap_plan

    assert plan.profile == "beeswarm_mean_abs_grouped"
    assert plan.group_contribution_source == "derived_from_supplied_shap"
    assert _pairs(plan.group_contributions) == pytest.approx(
        {"Clinical": 4.0 / 7.0 * 100.0, "Imaging": 3.0 / 7.0 * 100.0}
    )


def test_generic_domain_header_requires_manual_feature_group_confirmation(tmp_path: Path) -> None:
    rows = _composite_rows()
    for row in rows:
        row["Domain"] = row.pop("Feature Group")
    source = _write_csv(tmp_path / "generic_domain.csv", rows)

    automatic = prepare_scientific(source, "shap_summary")

    assert automatic.requires_confirmation is True
    assert "generic_domain_role_requires_confirmation" in automatic.confirmation_reasons
    confirmed = prepare_scientific(
        source,
        "shap_summary",
        column_mapping=_mapping_for(
            list(rows[0]),
            {
                "Feature": "feature",
                "SHAP value": "shap",
                "Feature value": "feature_value",
                "Sample ID": "sample_id",
                "Feature Order": "feature_order",
                "Mean absolute SHAP": "mean_abs_shap",
                "Domain": "feature_group",
                "Group contribution (%)": "group_contribution",
            },
            plot_mode="beeswarm_mean_abs_grouped",
        ),
    )
    assert confirmed.requires_confirmation is False
    assert confirmed.plot_spec.shap_plan.profile == "beeswarm_mean_abs_grouped"
