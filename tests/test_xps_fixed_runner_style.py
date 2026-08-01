from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
RUNNER_PATH = ROOT / "runtime" / "templates" / "xps_c1s_fit" / "runner.py"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.xps_visual_style import apply_xps_visual_style  # noqa: E402
from origin_sciplot.xps_workflow import (  # noqa: E402
    prepare_xps,
    replace_xps_visual_contract,
)


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("xps_fixed_style_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()
SOURCE = ROOT / "runtime" / "templates" / "xps_c1s_fit" / "example_standard.csv"


class _LayerObject:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def LT_execute(self, command: str) -> bool:  # noqa: N802
        self.commands.append(command)
        return True


class _AxisLayer:
    def __init__(self) -> None:
        self.ints: dict[str, int] = {}
        self.floats: dict[str, float] = {}
        self.obj = _LayerObject()

    def set_int(self, name: str, value: int) -> None:
        self.ints[name] = int(value)

    def set_float(self, name: str, value: float) -> None:
        self.floats[name] = float(value)


class _Legend:
    def __init__(self) -> None:
        self.values: dict[str, float | int] = {
            "show": 1,
            "showframe": 0,
            "left": 100.0,
            "top": 80.0,
            "width": 100.0,
            "height": 240.0,
        }
        self.text = ""

    def set_int(self, name: str, value: int) -> None:
        self.values[name] = int(value)

    def set_float(self, name: str, value: float) -> None:
        self.values[name] = float(value)

    def get_int(self, name: str) -> int:
        return int(self.values[name])

    def get_float(self, name: str) -> float:
        return float(self.values[name])

    def remove(self) -> None:
        self.values["show"] = 0


class _LegendLayer:
    def __init__(self) -> None:
        self.legend = _Legend()
        self.obj = _LayerObject()

    def label(self, _name: str) -> _Legend:
        return self.legend


class _LegendOrigin:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def lt_exec(self, command: str) -> bool:
        self.commands.append(command)
        return True

    def lt_float(self, expression: str) -> float:
        return {"page.width": 1000.0, "page.height": 800.0}[expression]


def test_fixed_preparation_keeps_raw_default_and_accepts_exact_series_colors() -> None:
    preparation = prepare_xps(SOURCE)
    assert preparation.visual_contract.raw_color == "#808080"

    styled = apply_xps_visual_style(
        preparation,
        {
            "series_colors": {
                "raw": "#123456",
                "component": "#ABCDEF",
                "Peak_CC": "#0A6F8F",
            },
            "line_width_pt": 3.25,
            "fill_transparency_percent": 37.5,
            "page_size_cm": {"width": 18.0, "height": 18.0},
        },
        source="explicit_user",
    ).preparation

    assert RUNNER._series_color(styled, "Raw", "raw") == "#123456"  # noqa: SLF001
    assert (
        RUNNER._series_color(styled, "Peak_CC", "component", 0)  # noqa: SLF001
        == "#0A6F8F"
    )
    assert (
        RUNNER._series_color(styled, "Peak_CO", "component", 1)  # noqa: SLF001
        == "#ABCDEF"
    )
    assert (
        RUNNER._component_fill_color(styled, "Peak_CC", 0)  # noqa: SLF001
        == "#0A6F8F"
    )
    style = styled.visual_contract.figure_style
    assert style.plot_line_width_pt == 3.25
    assert style.fill_transparency_percent == 37.5
    assert (style.page_width_cm, style.page_height_cm) == (18.0, 18.0)


def test_helper_columns_are_workbook_only_and_plot_x_remains_negated() -> None:
    preparation = prepare_xps(SOURCE)
    frame = pd.read_csv(SOURCE)
    original = frame.copy(deep=True)

    prepared = RUNNER._prepare_frame(frame, preparation)  # noqa: SLF001

    pd.testing.assert_frame_equal(frame, original)
    assert prepared["PlotX"].tolist() == pytest.approx(
        (-prepared["BindingEnergy"]).tolist()
    )
    for component in preparation.roles.components:
        assert f"{component}{RUNNER.FILL_TOP_SUFFIX}" in prepared.columns
        assert f"{component}{RUNNER.FILL_BASE_SUFFIX}" in prepared.columns
        assert prepared[f"{component}{RUNNER.FILL_TOP_SUFFIX}"].tolist() == pytest.approx(
            (prepared["Background"] + prepared[component]).tolist()
        )


def test_fixed_axis_contract_keeps_verified_negated_binding_energy_route() -> None:
    layer = _AxisLayer()

    RUNNER._apply_x_axis_contract(layer, -292.0)  # noqa: SLF001
    RUNNER._apply_y_axis_contract(layer)  # noqa: SLF001

    assert layer.floats["x.label.divideBy"] == -1.0
    assert layer.floats["x.firstTick"] == -292.0
    assert layer.ints["x.reverse"] == 0
    assert layer.ints["x.label.align"] == 1
    assert layer.ints["y.ticks"] == 0
    assert layer.ints["y.minorTicks"] == 0
    assert layer.ints["y.showLabels"] == 0
    assert layer.ints["x2.ticks"] == 0
    assert layer.ints["y2.ticks"] == 0
    assert "x2.showLabels" not in layer.ints
    assert "y2.showLabels" not in layer.ints


def test_hidden_legend_does_not_require_a_text_object_for_verification() -> None:
    preparation = prepare_xps(SOURCE)
    visual = replace(
        preparation.visual_contract,
        legend_visible=False,
        legend_position="none",
    )
    preparation = replace_xps_visual_contract(preparation, visual)
    layer = _LegendLayer()

    legend, state = RUNNER._style_legend(  # noqa: SLF001
        _LegendOrigin(),
        layer,
        [("raw", "#808080", "Raw")],
        preparation,
    )

    assert legend is None
    assert state == {
        "visible": False,
        "visible_readback": False,
        "position": "none",
        "showframe": None,
    }
    assert layer.legend.get_int("show") == 0


def test_outside_legend_position_frame_and_dynamic_width_are_read_back() -> None:
    preparation = apply_xps_visual_style(
        prepare_xps(SOURCE),
        {
            "legend_position": "outside_right",
            "legend_frame": True,
            "line_width_pt": 2.75,
        },
        source="explicit_user",
    ).preparation
    layer = _LegendLayer()

    legend, state = RUNNER._style_legend(  # noqa: SLF001
        _LegendOrigin(),
        layer,
        [("raw", "#123456", "Raw"), ("envelope", "#654321", "Envelope")],
        preparation,
    )

    assert legend is layer.legend
    assert state["visible_readback"] is True
    assert state["position"] == "outside_right"
    assert state["showframe"] == 1
    assert state["inside_page"] is True
    style = preparation.visual_contract.figure_style
    layer_right = 1000.0 * (
        style.layer_left_percent + style.layer_width_percent
    ) / 100.0
    assert state["left"] >= layer_right
    assert state["attach"] == 1
    assert "LineWidth:2.75" in layer.legend.text
    assert "EdgeColor:#123456" in layer.legend.text


def test_runner_keeps_independent_pfm3_fill_and_full_style_readback() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")

    assert "style = visual.figure_style" in text
    assert "fill_plot.transparency = style.fill_transparency_percent" in text
    assert "fill_plot.set_fill_area(" in text
    assert 'fill_plot.set_cmd("-pfm 3")' in text
    assert "four-colour" in text
    assert "visible_series_colors" in text
    assert "fill_transparency_percent_expected" in text
    assert '"legend": legend_state' in text
    assert '"xps_visual_contract": visual.to_dict()' in text
    assert "labels = {\"x_title\": x_title, \"y_title\": y_title}" in text
