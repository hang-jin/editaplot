from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.smoke_test import SMOKE_STYLE  # noqa: E402
from origin_sciplot.origin_backend.verify_utils import (  # noqa: E402
    verify_page_and_layer,
)


class FakeGraphObject:
    def __init__(
        self,
        *,
        width_inches: float | None = None,
        height_inches: float | None = None,
    ) -> None:
        self.width_inches = width_inches
        self.height_inches = height_inches

    def GetWidth(self) -> float:
        if self.width_inches is not None:
            return self.width_inches
        return SMOKE_STYLE.page_width_cm / 2.54

    def GetHeight(self) -> float:
        if self.height_inches is not None:
            return self.height_inches
        return SMOKE_STYLE.page_height_cm / 2.54

    def PutWidth(self, _value: float) -> None:
        return None

    def PutHeight(self, _value: float) -> None:
        return None

    def LT_execute(self, _command: str) -> bool:
        return True


class FakeGraph:
    def __init__(
        self,
        *,
        width_inches: float | None = None,
        height_inches: float | None = None,
    ) -> None:
        self.obj = FakeGraphObject(
            width_inches=width_inches,
            height_inches=height_inches,
        )

    def activate(self) -> None:
        return None


class FakeLayerObject:
    def __init__(self, *, command_ok: bool | int = True) -> None:
        self.command_ok = command_ok
        self.commands: list[str] = []

    def LT_execute(self, command: str) -> bool | int:
        self.commands.append(command)
        return self.command_ok


class FakeLayer:
    """Simulate the Origin 2026b bridge symptom reported by a real user."""

    def __init__(
        self,
        *,
        command_ok: bool | int = True,
        bridge_overrides: dict[str, float] | None = None,
    ) -> None:
        self.obj = FakeLayerObject(command_ok=command_ok)
        self.bridge_values = {
            "unit": 1.0,
            "left": 70.06,
            "top": 6.0,
            "width": 78.0,
            "height": 80.0,
            "factor": 1.0,
        }
        self.bridge_values.update(bridge_overrides or {})

    def activate(self) -> None:
        return None

    def get_float(self, name: str) -> float:
        return self.bridge_values[name]

    def set_int(self, _name: str, _value: int) -> None:
        return None

    def set_float(self, _name: str, _value: float) -> None:
        return None


class FakeOrigin:
    def __init__(self, overrides: dict[str, float] | None = None) -> None:
        self.values = {
            "layer.unit": 1.0,
            "layer.left": 17.0,
            "layer.top": 6.0,
            "layer.width": 78.0,
            "layer.height": 80.0,
            "layer.factor": 1.0,
            # Official `layer -x` order: width, height, left, top.
            "v1": 78.0,
            "v2": 80.0,
            "v3": 17.0,
            "v4": 6.0,
        }
        self.values.update(overrides or {})

    def lt_float(self, expression: str) -> float:
        return self.values[expression]


def test_verify_page_and_layer_accepts_two_agreeing_labtalk_paths_when_bridge_is_stale() -> None:
    geometry = verify_page_and_layer(
        FakeGraph(),
        FakeLayer(),
        origin=FakeOrigin(),
        style=SMOKE_STYLE,
    )

    assert geometry["left_percent"] == pytest.approx(17.0)
    assert geometry["layer_unit"] == pytest.approx(1.0)
    assert geometry["bridge_left_percent"] == pytest.approx(70.06)
    assert geometry["bridge_geometry_consistent"] is False
    assert geometry["geometry_readback_source"] == "labtalk_crosscheck"


def test_verify_page_and_layer_keeps_correct_bridge_as_diagnostic() -> None:
    geometry = verify_page_and_layer(
        FakeGraph(),
        FakeLayer(bridge_overrides={"left": 17.0}),
        origin=FakeOrigin(),
        style=SMOKE_STYLE,
    )

    assert geometry["bridge_geometry_consistent"] is True
    assert geometry["geometry_readback_source"] == "labtalk_crosscheck"


def test_verify_page_and_layer_rejects_disagreeing_labtalk_paths() -> None:
    with pytest.raises(RuntimeError, match="LabTalk layer geometry paths disagree"):
        verify_page_and_layer(
            FakeGraph(),
            FakeLayer(),
            origin=FakeOrigin({"v3": 70.06}),
            style=SMOKE_STYLE,
        )


def test_verify_page_and_layer_rejects_non_percent_layer_unit() -> None:
    with pytest.raises(RuntimeError, match="unit verification failed"):
        verify_page_and_layer(
            FakeGraph(),
            FakeLayer(),
            origin=FakeOrigin({"layer.unit": 0.0}),
            style=SMOKE_STYLE,
        )


def test_verify_page_and_layer_rejects_non_finite_native_readback() -> None:
    with pytest.raises(RuntimeError, match="non-finite"):
        verify_page_and_layer(
            FakeGraph(),
            FakeLayer(),
            origin=FakeOrigin({"v4": math.nan}),
            style=SMOKE_STYLE,
        )


def test_verify_page_and_layer_rejects_non_finite_page_readback() -> None:
    with pytest.raises(RuntimeError, match="page.width_cm"):
        verify_page_and_layer(
            FakeGraph(width_inches=math.nan),
            FakeLayer(),
            origin=FakeOrigin(),
            style=SMOKE_STYLE,
        )


def test_verify_page_and_layer_rejects_failed_layer_x_command() -> None:
    with pytest.raises(RuntimeError, match="layer -x"):
        verify_page_and_layer(
            FakeGraph(),
            FakeLayer(command_ok=False),
            origin=FakeOrigin(),
            style=SMOKE_STYLE,
        )


def test_verify_page_and_layer_rejects_integer_zero_command_result() -> None:
    with pytest.raises(RuntimeError, match="layer -x"):
        verify_page_and_layer(
            FakeGraph(),
            FakeLayer(command_ok=0),
            origin=FakeOrigin(),
            style=SMOKE_STYLE,
        )


def test_layer_x_mapping_uses_width_height_left_top_order() -> None:
    layer = FakeLayer()
    geometry = verify_page_and_layer(
        FakeGraph(), layer, origin=FakeOrigin(), style=SMOKE_STYLE
    )

    assert layer.obj.commands[0] == "v1=NA();v2=NA();v3=NA();v4=NA();layer -x;"
    assert geometry["layer_x_width_percent"] == pytest.approx(78.0)
    assert geometry["layer_x_height_percent"] == pytest.approx(80.0)
    assert geometry["layer_x_left_percent"] == pytest.approx(17.0)
    assert geometry["layer_x_top_percent"] == pytest.approx(6.0)
