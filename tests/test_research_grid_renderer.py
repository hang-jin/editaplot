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

    def to_np2d(self, index=0):
        assert index == 0
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


class Text:
    def __init__(self, text):
        self.text = text
        self.name = ""
        self.values = {"width": max(300.0, len(text) * 75.0), "height": 120.0, "rotate": 0.0}

    def set_int(self, key, value):
        self.values[key] = value

    set_float = set_int

    def get_float(self, key):
        return float(self.values[key])

    def get_int(self, key):
        return int(self.values[key])


class Layer:
    def __init__(self, op):
        self.op = op
        self.obj = self
        self.plots = []
        self.texts = []
        self.theme_values = dict.fromkeys(
            ("Units", "PosAlignment", "PosX", "PosY", "Left", "Top", "Width", "Height"), 0.0
        )
        self.theme_applied = False
        self.theme_values["Width"] = 4.0
        self.extends_values = {"HideHeadLevel": 0, "HideTailLevel": 0}

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
        if name.casefold() != "spectrum1":
            return next((text for text in self.texts if text.name == name), None)
        return SimpleNamespace(obj=self)

    def add_label(self, text):
        label = Text(text)
        self.texts.append(label)
        return label

    def GetTheme(self):
        class Value:
            def __init__(self, value):
                self.value = value

            def SetDoubleValue(self, value):
                self.value = float(value)

            SetIntValue = SetDoubleValue

            def GetDoubleValue(self):
                return self.value

            GetIntValue = GetDoubleValue

        return SimpleNamespace(
            Dimension=SimpleNamespace(**{key: Value(value) for key, value in self.theme_values.items()}),
            Extends=SimpleNamespace(**{key: Value(value) for key, value in self.extends_values.items()}),
        )

    def PutTheme(self, theme):
        if self.op.corruption == "theme":
            return True  # A successful setter alone is not evidence.
        self.theme_values = {
            key: getattr(theme.Dimension, key).GetDoubleValue() for key in self.theme_values
        }
        self.theme_applied = True
        self.extends_values = {
            key: getattr(theme.Extends, key).GetIntValue() for key in self.extends_values
        }
        for name, dimension in (("left", "page.width"), ("top", "page.height"),
                                ("width", "page.width"), ("height", "page.height")):
            self.op.state[f"spectrum1.{name}"] = (
                self.theme_values[name.title()] / 100 * self.op.state[dimension]
            )
        return False  # Mirrors the real specialized object's legacy return value.

    def LT_execute(self, command):
        self.op.commands.append(command)
        if self.op.corruption == "command":
            return False
        for statement in command.split(";"):
            if "=" not in statement:
                continue
            key, raw = statement.split("=", 1)
            raw = raw.strip()
            if key.endswith("$"):
                self.op.state[key[:-1]] = raw.strip('"')
                continue
            if raw.startswith("font("):
                value = 42
            elif "*" in raw:
                term, multiplier = raw.split("*")
                value = self.op.state[term] * float(multiplier)
            else:
                value = float(raw)
            self.op.state[key] = value
        if "layer.cmap.SetLevels();" in command:
            # Live PID105 retains its inherited eight-level count in no-arg mode.
            self.op.state["layer.cmap.numColors"] = 8
        if "layer.cmap.SetLevels(1);" in command:
            self.op.state["layer.cmap.numColors"] = self.op.state["layer.cmap.numMajorLevels"]
        if "spectrum1.left" in self.op.state and not self.theme_applied:
            self.op.state["spectrum1.left"] = 1000.0  # Refresh restores the native anchor.
        return True


class Origin:
    def __init__(self, corruption=None):
        self.corruption = corruption
        self.state = {
            "page.width": 10000.0, "page.height": 7500.0,
            "page.resx": 600.0,
            "layer.cmap.zmin": 0.0, "layer.cmap.zmax": 1.0,
            "layer.cmap.type": 1,
        }
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

    def lt_exec(self, command):
        return self.layer.LT_execute(command)

    def get_lt_str(self, key):
        return self.state[key]

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
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=10, height_percent=65)
    state = position_grid_colorbar(
        op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17
    )
    assert state["geometry"] == pytest.approx(
        {"left_percent": 85, "top_percent": 12, "width_percent": 4, "height_percent": 65}
    )
    assert state["label_font_code"] == state["font_code_expected"] == 42
    assert state["label_size_pt"] == 17
    assert [label["text"] for label in state["numeric_labels"]] == ["1", "0.8", "0.6", "0.4", "0.2", "0"]
    assert len(op.layer.texts) == 6


@pytest.mark.parametrize("corruption", ["font", "geometry", "theme"])
def test_colorbar_does_not_accept_wrong_font_or_geometry(corruption):
    op = Origin(corruption)
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=10, height_percent=65)
    with pytest.raises(OriginDrawError):
        position_grid_colorbar(op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17)


def test_numeric_color_labels_cannot_spill_beyond_the_reserved_gutter():
    op = Origin()
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=6, height_percent=65)
    with pytest.raises(OriginDrawError, match="reserved column"):
        position_grid_colorbar(op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17)


def test_wide_numeric_scale_labels_use_the_reserved_space_without_overlapping_the_bar():
    op = Origin()
    op.state.update({"layer.cmap.zmin": 100000000.0, "layer.cmap.zmax": 100000001.0})
    region = SimpleNamespace(left_percent=78, top_percent=12, width_percent=20, height_percent=65)
    state = position_grid_colorbar(
        op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17
    )
    assert len(state["numeric_labels"]) == 6
    lefts = [label.get_float("left") for label in op.layer.texts]
    assert max(lefts) - min(lefts) < 1e-9
    assert all(left > 8200 for left in lefts)
    assert all(label.get_float("left") + label.get_float("width") <= 9800 for label in op.layer.texts)


def test_log_color_scale_cannot_receive_linear_numeric_labels():
    op = Origin()
    op.state["layer.cmap.type"] = 2
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=10, height_percent=65)
    with pytest.raises(OriginDrawError, match="linear"):
        position_grid_colorbar(op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17)


def test_existing_scale_text_is_not_silently_duplicated_or_replaced():
    op = Origin()
    old = op.layer.add_label("User-owned text")
    old.name = "PhysicalGridScaleValue1"
    region = SimpleNamespace(left_percent=85, top_percent=12, width_percent=10, height_percent=65)
    with pytest.raises(OriginDrawError, match="already"):
        position_grid_colorbar(op, op.graph, op.layer, region=region, font_family="Arial", label_size_pt=17)
    assert op.layer.texts == [old]
    assert old.text == "User-owned text"


@pytest.mark.parametrize("bounds", [(1e-9, 6e-9), (100000000.0, 100000001.0)])
def test_numeric_scale_labels_keep_small_or_narrow_range_differences(bounds):
    from origin_sciplot.origin_backend.research_grid_renderer import _grid_scale_labels

    ticks = _grid_scale_labels(*bounds)
    assert len(ticks) == 6
    assert len({text for _, text in ticks}) == 6
    numbers = [float(text) for _, text in ticks]
    assert all(a > b for a, b in zip(numbers[:-1], numbers[1:], strict=True))
    assert numbers[0] == pytest.approx(bounds[1])
    assert numbers[-1] == pytest.approx(bounds[0])


def test_no_category_binding_session_export_or_palette_selection_commands():
    op = Origin()
    build(op)
    commands = "".join(op.commands)
    assert not re.search(r"axis\s+-ps|plotvm|pfm|save|expGraph|exit|normalize|smooth", commands)
    assert "linkpal=0" in commands
