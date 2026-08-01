from __future__ import annotations

import csv
import inspect
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.density_ridgeline3d_renderer import (  # noqa: E402
    AXIS_EXPECTED_STATE,
    CAMERA_EXPECTED_STATE,
    FOCAL_MARKER_SIZE_PT,
    DensityRidgeline3DHelperPlan,
    DensityRidgeline3DPlotMapping,
    _build_graph,
    _read_plot_binding,
    _verify_axis_state,
    _verify_camera_state,
    build_density_ridgeline3d_helper_plan,
    density_ridgeline3d_helper_column_metadata,
    density_ridgeline3d_legend_text,
    density_ridgeline3d_style_commands,
)
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def _rows(condition_count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    x_values = (0.2, 0.35, 0.5, 0.65, 0.8)
    for condition_index in range(condition_count):
        condition = f"C{condition_index + 1}"
        position = 2000.0 + condition_index * 5.0
        focus = 0.42 + condition_index * 0.04
        for point_index, x_value in enumerate(x_values):
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


def _source(tmp_path: Path, condition_count: int) -> Path:
    rows = _rows(condition_count)
    path = tmp_path / f"density_{condition_count}.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("condition_count", [2, 6])
def test_helper_plan_builds_three_xyz_plots_per_condition_without_source_mutation(
    tmp_path: Path,
    condition_count: int,
) -> None:
    source = _source(tmp_path, condition_count)
    preparation = prepare_scientific(source, "density_ridgeline3d")
    frame = pd.read_csv(source)
    before = frame.copy(deep=True)

    helper = build_density_ridgeline3d_helper_plan(frame, preparation)

    assert isinstance(helper, DensityRidgeline3DHelperPlan)
    pd.testing.assert_frame_equal(frame, before)
    assert helper.source_frame_unchanged is True
    assert len(helper.mappings) == condition_count * 3
    assert len(helper.helper_columns) == condition_count * 9
    assert tuple(helper.frame.columns) == helper.helper_columns
    assert [mapping.role for mapping in helper.mappings] == [
        role
        for _condition in range(condition_count)
        for role in ("density_solid", "density_dashed", "focal")
    ]
    assert len(set(helper.helper_columns)) == len(helper.helper_columns)

    for condition_index in range(condition_count):
        condition = f"C{condition_index + 1}"
        solid, dashed, focal = helper.mappings[condition_index * 3 : condition_index * 3 + 3]
        assert solid.condition == dashed.condition == focal.condition == condition
        assert solid.row_count == dashed.row_count == 5
        assert focal.row_count == 1
        assert solid.source_z == "Solid Density (a.u.)"
        assert dashed.source_z == "Dashed Density (a.u.)"
        assert focal.source_x == "Focal X"
        assert focal.source_z is None
        assert focal.z_derivation == "scale_by_constant(factor=0)"
        assert helper.frame[focal.helper_x].notna().sum() == 1
        assert helper.frame[focal.helper_y].notna().sum() == 1
        assert helper.frame[focal.helper_z].notna().sum() == 1
        assert helper.frame[focal.helper_z].dropna().to_numpy(dtype=float) == pytest.approx([0.0])
        assert helper.frame[solid.helper_y].dropna().nunique() == 1
        assert helper.frame[dashed.helper_y].dropna().nunique() == 1


def test_style_commands_freeze_only_live_proved_properties() -> None:
    solid = density_ridgeline3d_style_commands(
        "density_solid",
        color="#2B7A78",
        font_code=71,
        curve_width_units=1200,
    )
    dashed = density_ridgeline3d_style_commands(
        "density_dashed",
        color="#2B7A78",
        font_code=71,
        curve_width_units=1200,
    )
    focal = density_ridgeline3d_style_commands(
        "focal",
        color="#A66224",
        font_code=71,
        curve_width_units=1200,
    )

    assert "-so -l 1" in solid and "-so -d 0" in solid
    assert "-so -l 1" in dashed and "-so -d 1" in dashed
    for commands in (solid, dashed):
        assert "-so -w 1200" in commands
        assert "-so -k 0" in commands
        assert not any(command.split()[1] == "-kf" for command in commands)
        assert "-so -z 0" in commands
        assert all(command in commands for command in ("-so -lh 0", "-so -lv 0", "-so -lo 0"))
        assert "-so -q 0" in commands

    assert "-so -l 0" in focal
    assert f"-so -z {FOCAL_MARKER_SIZE_PT}" in focal
    assert "-so -q 1" in focal
    assert "-so -qm 1" in focal
    assert "-so -qf 71" in focal
    assert "-so -qs 15" in focal
    assert "-so -qp 4" in focal
    assert "-so -qw 0" in focal
    assert all(command.split()[1] not in {"-k", "-kf"} for command in focal)

    joined = " ".join((*solid, *dashed, *focal)).lower()
    assert "water" not in joined
    assert "-pf" not in joined
    assert "fill" not in joined
    assert all(command.startswith("-so ") for command in (*solid, *dashed, *focal))


def test_helper_plan_rejects_non_density_or_incomplete_preparation(tmp_path: Path) -> None:
    source = _source(tmp_path, 2)
    preparation = prepare_scientific(source, "density_ridgeline3d")
    frame = pd.read_csv(source)

    wrong_kind = replace(
        preparation,
        plot_spec=replace(preparation.plot_spec, plot_kind="trajectory3d"),
    )
    with pytest.raises(OriginDrawError, match="preparation is incomplete"):
        build_density_ridgeline3d_helper_plan(frame, wrong_kind)

    missing_focal = replace(
        preparation,
        plot_spec=replace(preparation.plot_spec, focal_x_column=None),
    )
    with pytest.raises(OriginDrawError, match="preparation is incomplete"):
        build_density_ridgeline3d_helper_plan(frame, missing_focal)

    missing_position = replace(
        preparation,
        plot_spec=replace(
            preparation.plot_spec,
            condition_positions=preparation.plot_spec.condition_positions[:-1],
        ),
    )
    with pytest.raises(OriginDrawError, match="positions are incomplete"):
        build_density_ridgeline3d_helper_plan(frame, missing_position)


def test_unknown_style_role_fails_closed() -> None:
    with pytest.raises(OriginDrawError, match="Unknown density_ridgeline3d plot role"):
        density_ridgeline3d_style_commands(
            "unknown",
            color="#000000",
            font_code=71,
            curve_width_units=1200,
        )


def test_renderer_never_deletes_or_unlinks_an_existing_output() -> None:
    source = inspect.getsource(_build_graph)

    assert ".unlink(" not in source
    assert "refuses to overwrite an existing editable OPJU" in source


def test_legend_uses_series_labels_and_neutralizes_origin_control_syntax() -> None:
    text = density_ridgeline3d_legend_text(
        r"H-dominated \l(9) %(unsafe)",
        r"V-dominated $(unsafe)",
    )

    assert text.startswith(r"\l(1) H-dominated")
    assert r"\l(2) V-dominated" in text
    assert text.endswith(r"\l(3) Baseline focal locator")
    assert text.count(r"\l(") == 3
    assert r"\l(9)" not in text
    assert "%(unsafe)" not in text
    assert "$(unsafe)" not in text
    assert "＼l(9)" in text
    assert "％(unsafe)" in text
    assert "＄(unsafe)" in text


@pytest.mark.parametrize("unsafe", ["line one\nline two", "bad\x00label", "   "])
def test_legend_rejects_multiline_nul_or_blank_series_labels(unsafe: str) -> None:
    with pytest.raises(OriginDrawError, match="printable single lines"):
        density_ridgeline3d_legend_text(unsafe, "valid")


def test_helper_focal_coordinates_match_source_and_frozen_condition_positions(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path, 2)
    preparation = prepare_scientific(source, "density_ridgeline3d")
    frame = pd.read_csv(source)

    helper = build_density_ridgeline3d_helper_plan(frame, preparation)
    focal_mappings = [mapping for mapping in helper.mappings if mapping.role == "focal"]

    assert [mapping.condition_position for mapping in focal_mappings] == pytest.approx(
        [2000.0, 2005.0]
    )
    for mapping, expected_x in zip(focal_mappings, (0.42, 0.46), strict=True):
        assert helper.frame[mapping.helper_x].dropna().to_numpy(dtype=float) == pytest.approx(
            [expected_x]
        )
        assert helper.frame[mapping.helper_y].dropna().to_numpy(dtype=float) == pytest.approx(
            [mapping.condition_position]
        )
        assert np.allclose(
            helper.frame[mapping.helper_z].dropna().to_numpy(dtype=float),
            0.0,
        )


def test_focal_helper_z_metadata_is_explicitly_derived_baseline(tmp_path: Path) -> None:
    source = _source(tmp_path, 2)
    preparation = prepare_scientific(source, "density_ridgeline3d")
    frame = pd.read_csv(source)
    helper = build_density_ridgeline3d_helper_plan(frame, preparation)
    focal = next(mapping for mapping in helper.mappings if mapping.role == "focal")

    metadata = density_ridgeline3d_helper_column_metadata(
        focal,
        x_title="Response Score (a.u.)",
        y_title="Follow-up Time (month)",
        z_title="Density (a.u.)",
    )

    assert metadata[2][0] == "Baseline locator Z"
    assert metadata[2][1] == "a.u."
    assert "scale_by_constant(factor=0)" in metadata[2][2]


class _BindingOp:
    def __init__(self, *, dataset_override: str | None = None, count_override: int | None = None):
        self.strings: dict[str, str] = {}
        self.numbers: dict[str, float] = {}
        for designation, column in zip(("x", "y", "z"), ("A", "B", "C"), strict=True):
            self.strings[f"__d3as1{designation}"] = f'[Book2]Sheet1!{column}"Helper {designation}"'
            self.strings[f"__d3es1{designation}"] = f"[Book2]1!col({column})"
            dataset = f"Book2_{column}"
            self.strings[f"__d3ad1{designation}"] = dataset
            self.strings[f"__d3ed1{designation}"] = dataset
            self.numbers[f"__d3ac1{designation}"] = 5.0
            self.numbers[f"__d3ec1{designation}"] = 5.0
            self.numbers[f"__d3pc1{designation}"] = 5.0
        if dataset_override is not None:
            self.strings["__d3ad1z"] = dataset_override
        if count_override is not None:
            self.numbers["__d3pc1z"] = float(count_override)

    def get_lt_str(self, name: str) -> str:
        return self.strings[name]

    def lt_float(self, name: str) -> float:
        return self.numbers[name]


class _BindingLayer:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        return True


class _BindingPlot:
    def lt_range(self) -> str:
        return "[Graph1]1!1"


class _BindingSheet:
    _columns = {"Helper X": 1, "Helper Y": 2, "Helper Z": 3}

    def lt_col_index(self, name: str) -> int:
        return self._columns[name]

    def lt_range(self, use_name: bool = True) -> str:
        del use_name
        return "[Book2]1"

    def get_label(self, column: int, label_type: str) -> str:
        labels = {
            "L": ("Score", "Year", "Density"),
            "U": ("a.u.", "year", "a.u."),
            "C": ("C1: density_solid",) * 3,
        }
        return labels[label_type][column]


def _binding_mapping() -> DensityRidgeline3DPlotMapping:
    return DensityRidgeline3DPlotMapping(
        condition="C1",
        condition_position=2000.0,
        role="density_solid",
        row_count=5,
        source_category="Condition",
        source_x="Score (a.u.)",
        source_y="Year",
        source_z="Density (a.u.)",
        helper_x="Helper X",
        helper_y="Helper Y",
        helper_z="Helper Z",
    )


def test_origin_binding_gate_uses_official_xyz_ranges_and_plotdata_counts() -> None:
    op = _BindingOp()
    layer = _BindingLayer()

    state = _read_plot_binding(
        op,
        layer,
        _BindingPlot(),
        _BindingSheet(),
        ("Helper X", "Helper Y", "Helper Z"),
        _binding_mapping(),
        1,
    )

    assert state["verified"] is True
    assert [state[axis]["actual_dataset"] for axis in ("x", "y", "z")] == [
        "Book2_A",
        "Book2_B",
        "Book2_C",
    ]
    assert all(state[axis]["plotdata_numeric_count"] == 5 for axis in ("x", "y", "z"))
    script = "".join(layer.commands).lower()
    assert all(token in script for token in ("range -wx", "range -wy", "range -wz"))
    assert "nameof(" in script
    assert all(token in script for token in ("plotdata(1,x)", "plotdata(1,y)", "plotdata(1,z)"))


@pytest.mark.parametrize(
    ("op", "message"),
    [
        (_BindingOp(dataset_override="Book9_Z"), "dataset binding mismatch"),
        (_BindingOp(count_override=4), "plotdata_numeric_count"),
    ],
)
def test_origin_binding_gate_fails_on_wrong_column_or_point_count(
    op: _BindingOp,
    message: str,
) -> None:
    with pytest.raises(OriginDrawError, match=message):
        _read_plot_binding(
            op,
            _BindingLayer(),
            _BindingPlot(),
            _BindingSheet(),
            ("Helper X", "Helper Y", "Helper Z"),
            _binding_mapping(),
            1,
        )


def test_axis_state_gate_asserts_every_visibility_and_tick_property() -> None:
    _verify_axis_state("x", dict(AXIS_EXPECTED_STATE))

    for key in AXIS_EXPECTED_STATE:
        state = dict(AXIS_EXPECTED_STATE)
        state[key] += 1
        with pytest.raises(OriginDrawError, match=key):
            _verify_axis_state("x", state)


def test_camera_gate_asserts_expected_values_and_reasonable_ranges() -> None:
    _verify_camera_state(dict(CAMERA_EXPECTED_STATE))

    drifted = dict(CAMERA_EXPECTED_STATE)
    drifted["inclination"] = 18.0
    with pytest.raises(OriginDrawError, match="camera.inclination"):
        _verify_camera_state(drifted)

    outside = dict(CAMERA_EXPECTED_STATE)
    outside["azimuth"] = 361.0
    with pytest.raises(OriginDrawError, match="outside the allowed range"):
        _verify_camera_state(outside)
