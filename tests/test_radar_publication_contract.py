"""Radar-specific publication regressions without starting Origin COM."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "src"))
sys.path.insert(0, str(ROOT / "skill" / "editaplot" / "scripts"))

from editaplot_core import _font_readback_audit  # noqa: E402
from origin_sciplot.origin_backend import categorical_renderer  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


class _Label:
    def __init__(self, text: str, *, showframe: int = 0) -> None:
        self.text = text
        self.properties = {"show": 1, "showframe": showframe}

    def set_int(self, name: str, value: int) -> None:
        self.properties[name] = value

    def get_int(self, name: str) -> int:
        return int(self.properties[name])

    def set_float(self, name: str, value: float) -> None:
        self.properties[name] = value

    def get_float(self, name: str) -> float:
        return float(self.properties.get(name, {"width": 10.0, "height": 10.0}.get(name, 0.0)))


class _Plot:
    def __init__(self, index: int) -> None:
        self.index = index

    def set_cmd(self, *commands: str) -> None:
        pass

    def lt_range(self) -> str:
        return f"[Radar]1!{self.index}"


class _Layer:
    def __init__(self) -> None:
        # Origin Radar uses radial-axis titles for metric names, not the
        # Cartesian convention that both XB and YL are redundant quantities.
        self.labels = {"yl": _Label("Accuracy"), "legend": _Label("Methods", showframe=1)}
        self.properties: dict[str, float] = {}
        self.plots = [_Plot(index) for index in range(1, 4)]
        self.obj = SimpleNamespace(LT_execute=self._execute)

    def _execute(self, command: str) -> int:
        for axis in ("x", "y"):
            if f"layer.{axis}.label.font=font(Arial)" in command:
                self.properties[f"{axis}.label.font"] = 71.0
        offset = re.search(r"layer.y.label.offsetH=([\d.]+)", command)
        if offset:
            self.properties["y.label.offsetH"] = float(offset.group(1))
        return 1

    def group(self, enabled: bool) -> None:
        pass

    def plot_list(self) -> list[_Plot]:
        return self.plots

    def rescale(self) -> None:
        pass

    def axis(self, name: str) -> SimpleNamespace:
        def set_limits(start: float, stop: float, step: float) -> None:
            self.properties.update({f"{name}.from": start, f"{name}.to": stop, f"{name}.inc": step})
        return SimpleNamespace(set_limits=set_limits)

    def set_float(self, name: str, value: float) -> None:
        self.properties[name] = value

    def get_float(self, name: str) -> float:
        return float(self.properties[name])

    def label(self, name: str) -> _Label | None:
        return self.labels.get(name.lower())


class _Graph:
    def __init__(self, layer: _Layer) -> None:
        self.layer = layer

    def __getitem__(self, index: int) -> _Layer:
        assert index == 0
        return self.layer

    def activate(self) -> None:
        pass

    def set_int(self, name: str, value: int) -> None:
        pass


def _render(monkeypatch: pytest.MonkeyPatch, *, restore_frame_on_refresh: bool = False):
    source = ROOT / "examples" / "gallery" / "radar_multimetric.csv"
    preparation = prepare_scientific(source, "radar")
    frame = pd.read_csv(source)
    layer = _Layer()
    graph = _Graph(layer)

    def execute(command: str) -> bool:
        if restore_frame_on_refresh and command == "doc -uw;":
            layer.labels["legend"].set_int("showframe", 1)
        return True

    op = SimpleNamespace(
        lt_exec=execute,
        find_graph=lambda: graph,
        ocolor=lambda _: 1,
        lt_float=lambda _: 71.0,
    )
    sheet = SimpleNamespace(
        lt_range=lambda _: "[Book1]Sheet1",
        activate=lambda: None,
        to_df=lambda: frame,
    )
    monkeypatch.setattr(categorical_renderer, "_apply_page_layer", lambda *args, **kwargs: {})
    monkeypatch.setattr(categorical_renderer, "verify_plot_line_widths", lambda *args: {})
    monkeypatch.setattr(categorical_renderer, "verify_text_sizes", lambda *args: {})
    monkeypatch.setattr(categorical_renderer, "verify_text_fonts", lambda *args: {})
    _, state = categorical_renderer._build_radar_graph(op, sheet, preparation)
    return layer, state


def test_radar_keeps_native_first_metric_title_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    layer, _ = _render(monkeypatch)

    assert layer.labels["yl"].text == "Accuracy"
    assert layer.labels["yl"].get_int("show") == 1


def test_radar_legend_is_borderless_after_final_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    layer, state = _render(monkeypatch)

    assert layer.labels["legend"].get_int("showframe") == 0
    assert state["origin_text_state"]["legend.showframe"] == 0


def test_radar_rejects_legend_frame_restored_by_template_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(OriginDrawError, match="borderless legend"):
        _render(monkeypatch, restore_frame_on_refresh=True)


def test_radar_label_offset_is_not_interpreted_as_a_font_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = _render(monkeypatch)

    audit = _font_readback_audit(state)
    assert audit["ok"] is True
    assert set(audit["actual_font_codes"].values()) == {71}
    assert state["origin_axis_state"]["radial_label_offset_percent"] == 70.0
