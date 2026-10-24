"""A grouped-box category table is semantic data, not unwanted numeric-axis state."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.origin_backend import evidence_renderer as renderer  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def preparation():
    return prepare_scientific(ROOT / "examples/gallery/grouped_box_medical.csv", "grouped_box")


class Layer:
    def __init__(self, *, corrupt=None):
        self.values = {"x.label.table": 1, "x.label.type": 7, "x.label.collabel": 1}
        self.corrupt = corrupt
        self.obj = self

    def activate(self):
        pass

    def set_int(self, key, value):
        self.values[key] = value

    def get_int(self, key):
        return 0 if key == self.corrupt else self.values[key]


class Sheet:
    def __init__(self, *, corrupt=None):
        self.labels = {
            "L": ["No injection", "No injection", "PBS", "PBS", "Low LPS", "Low LPS", "High LPS", "High LPS"],
            "C": ["WT", "Mutant"] * 4,
        }
        if corrupt:
            self.labels[corrupt][2] = "Wrong source label"

    def get_labels(self, row):
        return self.labels[row].copy()


def bind(layer, sheet, prep):
    function = getattr(renderer, "_bind_grouped_box_labels", None)
    assert callable(function), "Grouped-box labels need an explicit source-bound native contract"
    return function(
        SimpleNamespace(lt_exec=lambda script: True),
        SimpleNamespace(activate=lambda: None), layer, sheet, prep,
    )


def test_grouped_box_preserves_both_header_roles_and_the_merged_category_table():
    prep, layer, sheet = preparation(), Layer(), Sheet()
    before = {row: labels.copy() for row, labels in sheet.labels.items()}
    result = bind(layer, sheet, prep)
    assert result["column_label_rows"] == {"Long Name": before["L"], "Comments": before["C"]}
    assert result["axis_label_table"] == 1
    assert result["axis_label_type"] == 7
    assert result["axis_column_label"] == 1
    assert result["category_order"] == ["No injection", "PBS", "Low LPS", "High LPS"]
    assert result["group_order"] == ["WT", "Mutant"]
    assert sheet.labels == before


@pytest.mark.parametrize("row", ["L", "C"])
def test_a_correct_native_table_cannot_hide_changed_category_or_group_names(row):
    with pytest.raises(OriginDrawError, match="label"):
        bind(Layer(), Sheet(corrupt=row), preparation())


@pytest.mark.parametrize("key", ["x.label.table", "x.label.type", "x.label.collabel"])
def test_grouped_box_rejects_native_table_or_display_role_mismatch(key):
    with pytest.raises(OriginDrawError, match="label"):
        bind(Layer(corrupt=key), Sheet(), preparation())


def test_grouped_box_binding_cannot_be_used_as_a_generic_table_exception():
    prep = prepare_scientific(ROOT / "examples/gallery/violin_distributions.csv", "violin")
    with pytest.raises(OriginDrawError, match="grouped"):
        bind(Layer(), Sheet(), prep)


def numeric_layer():
    prep = preparation()
    style = prep.plot_spec.display_plan.figure_style
    values = {}
    for axis in ("x", "y"):
        for key in ("from", "to", "inc", "type", "showAxes", "ticks", "minorTicks", "showLabels",
                    "label.table", "label.type", "label.pt", "label.font", "label.rotate",
                    "thickness", "tickthickness", "atZero"):
            values[f"{axis}.{key}"] = 0
        values.update({
            f"{axis}.showAxes": 3, f"{axis}.showLabels": 1, f"{axis}.label.font": 73,
            f"{axis}.label.pt": style.tick_label_size_pt,
            f"{axis}.thickness": style.frame_line_width_pt,
        })
    values["x.label.table"] = 1
    return prep, values, SimpleNamespace(get_int=values.__getitem__, get_float=values.__getitem__)


def test_explicit_grouped_box_table_passes_without_weakening_other_axis_checks():
    prep, values, layer = numeric_layer()
    op = SimpleNamespace(lt_float=lambda expression: 73)
    result = renderer._validate_axes(op, layer, prep, expected_x_label_table=1)
    assert result["x.label.table"] == 1
    values["y.label.table"] = 1
    with pytest.raises(OriginDrawError, match="Y tick-label table"):
        renderer._validate_axes(op, layer, prep, expected_x_label_table=1)
    values["y.label.table"] = 0
    values["x.label.font"] = 72
    with pytest.raises(OriginDrawError, match="font|Arial"):
        renderer._validate_axes(op, layer, prep, expected_x_label_table=1)


def test_default_evidence_validation_still_rejects_an_inherited_x_table():
    prep, _, layer = numeric_layer()
    with pytest.raises(OriginDrawError, match="X tick-label table"):
        renderer._validate_axes(SimpleNamespace(lt_float=lambda expression: 73), layer, prep)


def test_a_numeric_or_violin_axis_cannot_request_the_grouped_box_table_exception():
    prep = prepare_scientific(ROOT / "examples/gallery/violin_distributions.csv", "violin")
    with pytest.raises(OriginDrawError, match="source-bound grouped-box"):
        renderer._validate_axes(None, None, prep, expected_x_label_table=1)
