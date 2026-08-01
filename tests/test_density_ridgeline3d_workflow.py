from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_preview import (  # noqa: E402
    _build_scientific_preview_figure,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
    role_options,
)
from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402
from origin_sciplot.semantic_contract import SemanticContractError  # noqa: E402


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for condition_index, (condition, position, focus) in enumerate(
        (("C1", 2000.0, 0.42), ("C2", 2005.0, 0.48), ("C3", 2010.0, 0.54))
    ):
        for point_index, x_value in enumerate((0.2, 0.35, 0.5, 0.65, 0.8)):
            rows.append(
                {
                    "Condition": condition,
                    "Follow-up Time (month)": position,
                    "Response Score (a.u.)": x_value,
                    "Solid Density (a.u.)": (point_index + 1) * (condition_index + 1) * 0.7,
                    "Dashed Density (a.u.)": (5 - point_index) * (condition_index + 1) * 0.4,
                    "Focal X": focus if point_index == 2 else "",
                }
            )
    return rows


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _rename_column(
    rows: list[dict[str, object]],
    old: str,
    new: str,
) -> list[dict[str, object]]:
    return [
        {new if key == old else key: value for key, value in row.items()}
        for row in rows
    ]


def _prepare(tmp_path: Path, rows: list[dict[str, object]] | None = None):
    source = _write(tmp_path / "density_focus.csv", rows or _rows())
    return source, prepare_scientific(source, "density_ridgeline3d")


def _wrapped(preparation):
    return SimpleNamespace(
        template_id="density_ridgeline3d",
        source_columns=preparation.source_columns,
        confidence=preparation.confidence,
        requires_confirmation=preparation.requires_confirmation,
        confirmation_reasons=preparation.confirmation_reasons,
        payload=preparation,
    )


def _assert_error(code: str, operation) -> ScientificWorkflowError:
    with pytest.raises(ScientificWorkflowError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


def test_six_source_roles_freeze_ordered_profiles_and_focal_baseline(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "density_focus.csv", _rows())
    before = source.read_bytes()

    preparation = prepare_scientific(source, "density_ridgeline3d")

    assert source.read_bytes() == before
    assert preparation.confidence == pytest.approx(0.98)
    assert preparation.requires_confirmation is False
    assert dict(preparation.assignments) == {
        "Condition": "condition_id",
        "Follow-up Time (month)": "condition_position",
        "Response Score (a.u.)": "density_x",
        "Solid Density (a.u.)": "density_solid",
        "Dashed Density (a.u.)": "density_dashed",
        "Focal X": "focal_x",
    }
    spec = preparation.plot_spec
    assert spec.plot_kind == "density_ridgeline3d"
    assert spec.plot_mode == "ordered_dual_profile_focus"
    assert spec.x_column == "Response Score (a.u.)"
    assert spec.y_column == "Follow-up Time (month)"
    assert spec.category_column == "Condition"
    assert spec.focal_x_column == "Focal X"
    assert spec.z_title == "Density (a.u.)"
    assert spec.group_order == ("C1", "C2", "C3")
    assert spec.condition_positions == (("C1", 2000.0), ("C2", 2005.0), ("C3", 2010.0))
    assert [series.series_role for series in spec.series] == [
        "density_solid",
        "density_dashed",
    ]
    assert spec.display_transform == "identity"
    style = spec.display_plan.figure_style
    assert style is not None
    assert style.profile_name == "adaptive-density_ridgeline3d-density_ridgeline3d"
    assert style.palette_name == "trajectory3d_family"
    assert spec.display_plan.marker_size_pt == 9.0


def test_threshold_named_sparse_column_requires_focal_semantic_confirmation(
    tmp_path: Path,
) -> None:
    rows = _rename_column(_rows(), "Focal X", "Threshold X (a.u.)")
    source = _write(tmp_path / "density_threshold.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")

    assert dict(preparation.assignments)["Threshold X (a.u.)"] == "focal_x"
    assert preparation.confidence < 0.9
    assert preparation.requires_confirmation is True
    assert "focal_x_role_inferred" in preparation.confirmation_reasons


def test_role_options_are_six_unique_scientific_bindings() -> None:
    options = {key: unique for key, _label, unique in role_options("density_ridgeline3d")}

    assert set(options) == {
        "condition_id",
        "condition_position",
        "density_x",
        "density_solid",
        "density_dashed",
        "focal_x",
        "ignored",
    }
    assert all(options[role] for role in set(options) - {"ignored"})
    assert options["ignored"] is False


def test_preview_contains_exactly_two_profiles_per_condition_and_baseline_points(
    tmp_path: Path,
) -> None:
    _source, preparation = _prepare(tmp_path)

    figure = _build_scientific_preview_figure(preparation)
    axis = figure.axes[0]

    assert len(axis.lines) == 2 * len(preparation.plot_spec.group_order)
    assert [line.get_linestyle() for line in axis.lines] == ["-", "--"] * 3
    for line in axis.lines:
        x, y, z = line._verts3d
        assert len(x) == 5
        assert len(set(np.asarray(y, dtype=float))) == 1
        assert not np.allclose(np.asarray(z, dtype=float), 0.0)
    focus_collections = [collection for collection in axis.collections if hasattr(collection, "_offsets3d")]
    assert len(focus_collections) == 1
    focus_x, focus_y, focus_z = focus_collections[0]._offsets3d
    assert np.asarray(focus_x, dtype=float) == pytest.approx([0.42, 0.48, 0.54])
    assert np.asarray(focus_y, dtype=float) == pytest.approx([2000.0, 2005.0, 2010.0])
    assert np.asarray(focus_z, dtype=float) == pytest.approx([0.0, 0.0, 0.0])


def test_semantic_contract_classifies_each_column_once_and_requires_zero_approval(
    tmp_path: Path,
) -> None:
    _source, preparation = _prepare(tmp_path)

    proposal = propose_prepared_semantics(_wrapped(preparation))

    assert [item.source_column for item in proposal.data_items] == list(preparation.source_columns)
    assert len({item.source_column for item in proposal.data_items}) == 6
    dispositions = {item.semantic_role: item.disposition.value for item in proposal.data_items}
    assert dispositions == {
        "condition_id": "render_primary",
        "condition_position": "render_primary",
        "density_x": "render_primary",
        "density_solid": "render_primary",
        "density_dashed": "render_primary",
        "focal_x": "render_secondary",
    }
    assert len(proposal.derived_items) == 1
    baseline = proposal.derived_items[0]
    assert baseline.item_id == "derived_density_focus_baseline_zero"
    assert baseline.operation_id == "scale_by_constant"
    assert dict(baseline.parameters) == {"factor": 0.0}
    assert [element.element_kind for element in proposal.figure_elements] == [
        "line",
        "line",
        "symbol",
    ]
    assert proposal.figure_elements[-1].axis == "baseline_z_zero"
    assert (
        proposal.figure_elements[-1].legend_label
        == "Baseline focal locator / 基线焦点定位点"
    )
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=True)
    assert caught.value.code == "semantic_derived_approval_required"
    proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=(baseline.item_id,),
    )


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda rows: rows.__setitem__(6, {**rows[6], "Follow-up Time (month)": 2005.5}),
            "density_ridgeline3d_position_not_constant",
        ),
        (
            lambda rows: rows.__setitem__(7, {**rows[7], "Response Score (a.u.)": 0.35}),
            "density_ridgeline3d_x_not_strict_monotonic",
        ),
        (
            lambda rows: [
                row.update(
                    {"Response Score (a.u.)": 1.0 - float(row["Response Score (a.u.)"])}
                )
                for row in rows
                if row["Condition"] == "C2"
            ],
            "density_ridgeline3d_x_direction_mismatch",
        ),
        (
            lambda rows: rows.__setitem__(3, {**rows[3], "Solid Density (a.u.)": -0.1}),
            "density_ridgeline3d_density_negative",
        ),
        (
            lambda rows: rows.__setitem__(1, {**rows[1], "Focal X": 0.3}),
            "density_ridgeline3d_focal_count",
        ),
        (
            lambda rows: rows.__setitem__(2, {**rows[2], "Focal X": 1.2}),
            "density_ridgeline3d_focal_out_of_range",
        ),
        (
            lambda rows: [
                row.update({"Follow-up Time (month)": 1995.0})
                for row in rows
                if row["Condition"] == "C3"
            ],
            "density_ridgeline3d_condition_order_invalid",
        ),
    ],
)
def test_contract_violations_fail_without_repair(
    tmp_path: Path,
    mutate,
    code: str,
) -> None:
    rows = _rows()
    mutate(rows)
    source = _write(tmp_path / f"{code}.csv", rows)

    _assert_error(code, lambda: prepare_scientific(source, "density_ridgeline3d"))


def test_manual_mapping_retains_unrendered_columns_without_reclassification(
    tmp_path: Path,
) -> None:
    rows = [{**row, "Notes": "kept"} for row in _rows()]
    source = _write(tmp_path / "manual.csv", rows)
    automatic = prepare_scientific(source, "density_ridgeline3d")
    assert automatic.requires_confirmation is True
    assert automatic.confirmation_reasons == ("additional_columns_retained_not_rendered",)
    mapping = ScientificColumnMapping(
        assignments=(
            ("Condition", "condition_id"),
            ("Follow-up Time (month)", "condition_position"),
            ("Response Score (a.u.)", "density_x"),
            ("Solid Density (a.u.)", "density_solid"),
            ("Dashed Density (a.u.)", "density_dashed"),
            ("Focal X", "focal_x"),
            ("Notes", "ignored"),
        )
    )

    confirmed = prepare_scientific(
        source,
        "density_ridgeline3d",
        column_mapping=mapping,
    )

    assert confirmed.mapping_confirmed is True
    assert confirmed.requires_confirmation is False
    proposal = propose_prepared_semantics(_wrapped(confirmed))
    notes = next(item for item in proposal.data_items if item.source_column == "Notes")
    assert notes.disposition.value == "retain_not_render"


@pytest.mark.parametrize(
    ("old", "new", "code"),
    [
        (
            "Follow-up Time (month)",
            "Condition Position",
            "density_ridgeline3d_condition_axis_semantics_missing",
        ),
        (
            "Response Score (a.u.)",
            "Density X",
            "density_ridgeline3d_x_axis_semantics_missing",
        ),
        (
            "Response Score (a.u.)",
            "Metric (unit)",
            "density_ridgeline3d_x_axis_semantics_missing",
        ),
    ],
)
def test_plain_numeric_axis_headers_cannot_enter_scientific_3d(
    tmp_path: Path,
    old: str,
    new: str,
    code: str,
) -> None:
    source = _write(tmp_path / f"{code}_{new.replace(' ', '_')}.csv", _rename_column(_rows(), old, new))

    _assert_error(code, lambda: prepare_scientific(source, "density_ridgeline3d"))


def test_year_and_explicit_dimensionless_axis_semantics_are_accepted(tmp_path: Path) -> None:
    rows = _rename_column(_rows(), "Follow-up Time (month)", "Measurement Year")
    rows = _rename_column(rows, "Response Score (a.u.)", "Response Score (dimensionless)")
    source = _write(tmp_path / "year_dimensionless.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")

    assert preparation.requires_confirmation is False
    assert preparation.plot_spec.y_column == "Measurement Year"
    assert preparation.plot_spec.x_column == "Response Score (dimensionless)"


@pytest.mark.parametrize(
    ("old", "new", "code"),
    [
        (
            "Solid Density (a.u.)",
            "Solid Density",
            "density_ridgeline3d_density_semantics_missing",
        ),
        (
            "Solid Density (a.u.)",
            "Solid Profile (a.u.)",
            "density_ridgeline3d_density_semantics_missing",
        ),
        (
            "Dashed Density (a.u.)",
            "Dashed Density (counts)",
            "density_ridgeline3d_density_unit_mismatch",
        ),
    ],
)
def test_density_semantics_and_units_are_hard_gates(
    tmp_path: Path,
    old: str,
    new: str,
    code: str,
) -> None:
    source = _write(tmp_path / f"density_{code}.csv", _rename_column(_rows(), old, new))

    _assert_error(code, lambda: prepare_scientific(source, "density_ridgeline3d"))


def test_matching_explicit_dimensionless_density_freezes_z_title(tmp_path: Path) -> None:
    rows = _rename_column(
        _rows(),
        "Solid Density (a.u.)",
        "Solid Density (dimensionless)",
    )
    rows = _rename_column(
        rows,
        "Dashed Density (a.u.)",
        "Dashed Density (无量纲)",
    )
    source = _write(tmp_path / "dimensionless_density.csv", rows)

    preparation = prepare_scientific(source, "density_ridgeline3d")

    assert preparation.plot_spec.z_title == "Density (dimensionless)"
