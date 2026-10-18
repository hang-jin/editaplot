from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))

from origin_sciplot.origin_backend.research_grid_renderer import (  # noqa: E402
    build_physical_grid_layer,
    position_grid_colorbar,
)
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.research_grid import PhysicalGrid, physical_grid  # noqa: E402

COLORS = tuple(f"#{i:02X}{255 - i:02X}57" for i in range(101))


def grid():
    frame = pd.DataFrame(
        {
            "x": [10.5, 13.0, 15.5] * 2,
            "y": [80.0] * 3 + [76.0] * 3,
            "value": [-2.125, 0.0, 3.625, 4.25, 5.5, 6.875],
        }
    )
    return physical_grid(frame, "x", "y", "value")


class Matrix:
    def __init__(self, op):
        self.op = op
        self.values = None
        self.mapping = None

    def from_np(self, values):
        self.values = values.copy()

    def to_np(self):
        result = self.values.copy()
        if self.op.corruption == "matrix":
            result[0, 1] = 99
        return result

    @property
    def xymap(self):
        return (1, 3, 1, 2) if self.op.corruption == "xymap" else self.mapping

    @xymap.setter
    def xymap(self, value):
        self.mapping = tuple(value)

    def set_label(self, index, label):
        self.label = index, label

    def lt_range(self):
        return "[PhysicalGrid]MSheet1"


class Axis:
    def __init__(self, layer, name):
        self.layer, self.name = layer, name

    def set_limits(self, begin, end):
        self.layer.op.state[f"layer.{self.name}.from"] = begin
        self.layer.op.state[f"layer.{self.name}.to"] = end


class Layer:
    def __init__(self, op):
        self.op = op
        self.obj = self
        self.plots = []

    def activate(self):
        self.op.active_layer = self

    def plot_list(self):
        return self.plots

    def add_mplot(self, matrix, index, *, type):
        assert index == 0 and type == 105
        self.matrix = matrix
        plot = SimpleNamespace(lt_range=lambda: "[Graph1]1!1")
        self.plots.append(plot)
        self.op.state["layer.plot.pid"] = type
        return plot

    def rescale(self, axis):
        assert axis == "z"

    def axis(self, name):
        return Axis(self, name)

    def set_int(self, name, value):
        self.op.state[f"layer.{name}"] = value

    def get_float(self, name):
        return self.op.lt_float(f"layer.{name}")

    def get_int(self, name):
        return int(self.get_float(name))

    def label(self, name):
        return object() if name.casefold() == "spectrum1" else None

    def LT_execute(self, command):
        self.op.commands.append(command)
        if self.op.corruption == "command":
            return False
        for statement in command.split(";"):
            if "=" not in statement:
                continue
            key, raw = statement.split("=", 1)
            raw = raw.strip()
            if raw.startswith("font("):
                value = 42
            elif "*" in raw:
                term, multiplier = raw.split("*")
                value = self.op.state[term] * float(multiplier)
            else:
                value = float(raw)
            self.op.state[key] = value
        return True


class Origin:
    def __init__(self, corruption=None):
        self.corruption = corruption
        self.state = {"page.width": 10000.0, "page.height": 7500.0}
        self.commands = []
        self.sheets = []
        self.layer = Layer(self)
        self.graph = SimpleNamespace(activate=lambda: None)

    def new_sheet(self, type, name):
        assert type == "m", "Physical coordinates must not become a label worksheet."
        matrix = Matrix(self)
        self.sheets.append(matrix)
        return matrix

    def ocolor(self, color):
        return int(color[1:], 16)

    def lt_float(self, key):
        if key.startswith("font("):
            return 42
        if (self.corruption, key) in {
            ("color", "layer.cmap.color51"),
            ("zrange", "layer.cmap.zmin"),
            ("axis", "layer.x.from"),
            ("font", "spectrum1.labels.font"),
            ("geometry", "spectrum1.left"),
        }:
            return self.state[key] + 100
        return self.state[key]


def build(op, source=None, **overrides):
    options = dict(value_label="Intensity (a.u.)", palette_hex=COLORS, z_range=(-3.0, 7.0))
    options.update(overrides)
    return build_physical_grid_layer(op, op.graph, op.layer, source or grid(), **options)


def test_native_cells_keep_nonindex_coordinates_source_values_and_halfstep_edges():
    source = grid()
    op = Origin()
    state = build(op, source)
    assert op.sheets[0].mapping == (10.5, 15.5, 80.0, 76.0)
    np.testing.assert_array_equal(op.sheets[0].values, source.values)
    assert state["matrix"]["cell_edges"] == [9.25, 16.75, 82.0, 74.0]
    assert state["matrix"]["values"] == [list(row) for row in source.values]
    assert state["matrix"]["source_rows"] == [list(row) for row in source.source_rows]
    assert state["axes"]["x_range"] == [9.25, 16.75]
    assert state["axes"]["y_range"] == [82.0, 74.0]
    assert state["axes"]["axis_display_reversed"] == {"x": False, "y": True}
    assert len(op.sheets) == 1
    assert state["styling_status"] == "caller_font_title_geometry_verification_required"


def test_explicit_display_reversal_changes_no_matrix_value_coordinate_or_source_binding():
    source = grid()
    op = Origin()
    state = build(op, source, x_range=(16.75, 9.25), y_range=(74.0, 82.0))
    assert state["axes"]["axis_display_reversed"] == {"x": True, "y": False}
    assert state["axes"]["reversed_relative_to_source"] == {"x": True, "y": True}
    assert op.sheets[0].mapping == source.xymap
    np.testing.assert_array_equal(op.sheets[0].values, source.values)
    assert state["matrix"]["source_rows"] == [list(row) for row in source.source_rows]


def test_exact_101_color_order_and_fixed_range_are_read_back():
    state = build(Origin(), palette_hex=tuple(reversed(COLORS)), z_range=(-100, 200))
    assert state["color_map"]["expected_hex"] == list(reversed(COLORS))
    assert state["color_map"]["origin_codes"] == [int(c[1:], 16) for c in reversed(COLORS)]
    assert (state["color_map"]["zmin"], state["color_map"]["zmax"]) == (-100, 200)
    assert state["color_map"]["num_colors"] == 101


@pytest.mark.parametrize(
    "limits", [(1, 1), (3, -3), (float("nan"), 7), (-3, float("inf")), (-1, 7), (-3, 6), (1,), (-3, 7, 8)]
)
def test_invalid_or_clipping_z_range_fails_before_origin_mutation(limits):
    op = Origin()
    with pytest.raises(OriginDrawError, match="range"):
        build(op, z_range=limits)
    assert not op.sheets


@pytest.mark.parametrize("colors", [COLORS[:-1], COLORS + ("#FFFFFF",), ("#GGFFFF",) + COLORS[1:]])
def test_palette_is_exactly_101_supplied_hex_colors(colors):
    op = Origin()
    with pytest.raises(OriginDrawError, match="101|HEX"):
        build(op, palette_hex=colors)
    assert not op.sheets


def test_axis_limits_cannot_clip_pixels_or_replace_physical_values_with_indices():
    op = Origin()
    with pytest.raises(OriginDrawError, match="cell"):
        build(op, x_range=(1, 3))
    assert not op.sheets


@pytest.mark.parametrize("corruption", ["matrix", "xymap", "color", "zrange", "axis", "command"])
def test_any_inexact_native_readback_fails_closed(corruption):
    with pytest.raises(OriginDrawError):
        build(Origin(corruption))


@pytest.mark.parametrize("bad_value", [float("nan"), True, complex(1, 2)])
def test_malformed_direct_grid_cannot_bypass_source_model_validation(bad_value):
    source = grid()
    invalid = PhysicalGrid(source.x, source.y, ((1, 2, bad_value), (4, 5, 6)), source.source_rows)
    op = Origin()
    with pytest.raises(OriginDrawError):
        build(op, invalid)
    assert not op.sheets


def test_colorbar_uses_given_page_region_and_readbacks_font_and_all_dimensions():
    op = Origin()
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=7, height_percent=65)
    state = position_grid_colorbar(
        op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17
    )
    assert state["geometry"] == pytest.approx(
        {"left_percent": 85, "top_percent": 12, "width_percent": 7, "height_percent": 65}
    )
    assert state["label_font_code"] == state["font_code_expected"] == 42
    assert state["label_size_pt"] == 17


@pytest.mark.parametrize("corruption", ["font", "geometry"])
def test_colorbar_does_not_accept_wrong_font_or_geometry(corruption):
    op = Origin(corruption)
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=7, height_percent=65)
    with pytest.raises(OriginDrawError):
        position_grid_colorbar(op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17)


def test_no_category_binding_session_export_or_palette_selection_commands():
    op = Origin()
    build(op)
    commands = "".join(op.commands)
    assert not re.search(r"axis\s+-ps|plotvm|pfm|save|expGraph|exit|normalize|smooth", commands)
    assert "linkpal=0" in commands
