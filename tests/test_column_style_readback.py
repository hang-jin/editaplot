"""Column fills and borders must not be validated through a line-color cache."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime" / "src"))
from origin_sciplot.origin_backend import categorical_renderer as categorical  # noqa: E402
from origin_sciplot.origin_backend import scientific_renderer as renderer  # noqa: E402
from origin_sciplot.origin_backend import verify_utils as verify  # noqa: E402
from origin_sciplot.scientific_visual import resolve_adaptive_style  # noqa: E402


class NativeColumn:
    def __init__(
        self,
        scale: float = 1.0,
        *,
        reject_width_restore: bool = False,
        ignore_vw: bool = False,
        pbw_uses_points: bool = False,
    ) -> None:
        self.options = {"-c": 1.0, "-pfb": 1.0, "-pbc": 1.0, "-pbw": 0.5 * scale}
        self.variables: dict[str, float] = {}
        self.commands: list[str] = []
        self.scale = scale
        self.reject_width_restore = reject_width_restore
        self.ignore_vw = ignore_vw
        self.pbw_uses_points = pbw_uses_points
        self.layer = self

    @property
    def color(self):
        raise AssertionError("Python color cache is not native readback")

    def lt_range(self) -> str:
        return "[Graph1]1!1"

    def set_cmd(self, command: str) -> None:
        self.commands.append(command)
        option, raw = command.split()
        value = float(raw)
        if option == "-vw":
            if not self.ignore_vw and (value == 1 or not self.reject_width_restore):
                self.options["-pbw"] = value * self.scale
        elif option == "-pbw":
            if value == 1 or not self.reject_width_restore:
                self.options[option] = value * (self.scale if self.pbw_uses_points else 1)
        else:
            self.options[option] = value

    def LT_execute(self, command: str) -> int:
        match = re.search(r"get rr (-[a-z]+) ([a-zA-Z0-9_]+);", command)
        assert match is not None
        self.variables[match[2]] = self.options[match[1]]
        return 1

    def lt_float(self, name: str) -> float:
        return self.variables[name]

    @staticmethod
    def ocolor(color: str) -> int:
        return int(color.lstrip("#"), 16) + 0x1000000


def test_column_style_uses_explicit_fill_border_and_point_width() -> None:
    column = NativeColumn()
    verify.apply_column_style(column, column, "#247B8B", border_width_pt=1.3)
    code = column.ocolor("#247B8B")
    assert column.options["-c"] == 1  # It remains an unrelated line property.
    assert column.options["-pfb"] == column.options["-pbc"] == code
    assert column.options["-pbw"] == pytest.approx(1.3)


@pytest.mark.parametrize("bad_option", [None, "-pfb", "-pbc"])
def test_column_color_validation_checks_both_native_channels(bad_option: str | None) -> None:
    column = NativeColumn()
    code = column.ocolor("#247B8B")
    column.options.update({"-pfb": code, "-pbc": code})
    if bad_option:
        column.options[bad_option] = 1
        with pytest.raises(RuntimeError, match="column"):
            verify.verify_column_colors(column, column, "#247B8B", variable_name="__test")
    else:
        result = verify.verify_column_colors(column, column, "#247B8B", variable_name="__test")
        assert result["fill_origin_color_code"] == result["border_origin_color_code"] == code


@pytest.mark.parametrize("native_scale", [1.0, 500.0])
@pytest.mark.parametrize("pbw_uses_points", [False, True])
def test_column_border_width_calibrates_native_read_units_and_restores_contract(
    native_scale: float, pbw_uses_points: bool
) -> None:
    column = NativeColumn(native_scale, pbw_uses_points=pbw_uses_points)
    result = verify.verify_column_border_widths(column, {"Series": column}, 1.3)
    assert column.options["-pbw"] == pytest.approx(1.3 * native_scale)
    assert result["Series"]["border_width_pt"] == pytest.approx(1.3)
    assert result["Series"]["native_units_per_pt"] == native_scale


def test_group_member_width_works_when_vw_only_applies_to_group_head() -> None:
    head = NativeColumn()
    member = NativeColumn(ignore_vw=True)
    member.variables = head.variables
    result = verify.verify_column_border_widths(head, {"Head": head, "Member": member}, 1.3)
    assert member.options["-pbw"] == pytest.approx(1.3)
    assert result["Member"]["border_width_pt"] == pytest.approx(1.3)


def test_native_plot_reference_does_not_depend_on_cached_getindex() -> None:
    calls: list[str] = []
    layer = SimpleNamespace(LT_execute=lambda command: calls.append(command) or True)
    ref = verify.NativePlotReference("[Graph1]1!2", layer)
    ref.set_cmd("-pfb 123", "-vw 1.3")
    assert ref.lt_range() == "[Graph1]1!2"
    assert ref.native_index == 2
    assert "range rr=[Graph1]1!2" in calls[0]


def test_native_plot_reference_rejects_executable_or_non_plot_ranges() -> None:
    with pytest.raises(ValueError):
        verify.NativePlotReference("[Graph1]1!2;run anything", None)


def test_column_width_rejects_a_setter_that_does_not_apply_final_width() -> None:
    column = NativeColumn(reject_width_restore=True)
    with pytest.raises(RuntimeError, match="border width"):
        verify.verify_column_border_widths(column, {"Series": column}, 1.3)


def test_unknown_width_encoding_is_rejected_and_frozen_width_is_still_restored() -> None:
    column = NativeColumn(10.0)
    with pytest.raises(RuntimeError, match="unit"):
        verify.verify_column_border_widths(column, {"Series": column}, 1.3)
    assert column.commands[-1] == "-vw 1.3"


@pytest.mark.parametrize("phase_tick", [False, True])
def test_generic_open_marks_use_the_native_open_flag_except_phase_ticks(phase_tick: bool) -> None:
    commands: list[str] = []
    plot = SimpleNamespace(set_cmd=commands.append, lt_range=lambda: "[Graph1]1!1")
    plots: list[object] = []

    def add_plot(*_args, **_kwargs):
        plots.append(plot)
        return plot

    layer = SimpleNamespace(plot_list=lambda: plots, add_plot=add_plot)
    series = renderer.OriginSeriesPlan(
        source_column="Y",
        plot_column="Y",
        x_column="X",
        error_column=None,
        label="Demo",
        axis="left",
        plot_type="s",
        color="#247B8B",
        is_phase_tick=phase_tick,
        bar_gap_percent=None,
        marker_size_pt=4.0,
    )
    style = resolve_adaptive_style(template_id="scatter", plot_kind="scatter", row_count=10, series_count=1)
    renderer._add_plot(None, layer, None, series, "X", style)
    assert ("-kf 1" in commands) is (not phase_tick)


@pytest.mark.parametrize(
    "actual_dataset,actual_count,valid", [("Data_B", 5, True), ("Data_C", 5, False), ("Data_B", 4, False)]
)
def test_categorical_binding_requires_the_real_dataset_and_all_values(actual_dataset, actual_count, valid):
    layer = SimpleNamespace(obj=SimpleNamespace(LT_execute=lambda _command: True))
    op = SimpleNamespace(
        get_lt_str=lambda name: actual_dataset if "actual" in name else "Data_B",
        lt_float=lambda name: actual_count if "actual" in name else 5,
    )
    sheet = SimpleNamespace(lt_col_index=lambda _column: 2, lt_range=lambda _flag: "[Book1]Data")
    plot = verify.NativePlotReference("[Graph1]1!1", layer.obj)
    plan = renderer.OriginSeriesPlan(
        source_column="Y",
        plot_column="Y",
        x_column=None,
        error_column=None,
        label="Demo",
        axis="left",
        plot_type="c",
        color="#247B8B",
        bar_gap_percent=None,
        marker_size_pt=4,
    )
    if valid:
        result = categorical._verify_column_y_bindings(op, layer, sheet, {"Demo": plot}, (plan,))
        assert result["Demo"]["numeric_count"] == 5
    else:
        with pytest.raises(categorical.OriginDrawError, match="binding"):
            categorical._verify_column_y_bindings(op, layer, sheet, {"Demo": plot}, (plan,))
