"""Display-only safeguards for the native violin's density tails."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "src"))

from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402


def test_violin_freezes_density_tail_room_without_modifying_observations():
    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    before = source.read_bytes()
    values = pd.read_csv(source).to_numpy(dtype=float)
    preparation = prepare_scientific(source, "violin")
    axis = preparation.plot_spec.axis_plan
    span = float(values.max() - values.min())

    assert axis.y_from <= float(values.min()) - span * 0.25 + 1e-10
    assert axis.y_to >= float(values.max()) + span * 0.25 - 1e-10
    assert source.read_bytes() == before
    assert preparation.row_count == len(values)
    assert preparation.plot_spec.display_transform == "identity"
    assert [item.source_column for item in preparation.plot_spec.series] == list(pd.read_csv(source).columns)


@pytest.mark.parametrize("template_id", ["raw_summary", "raincloud"])
def test_violin_padding_does_not_change_other_distribution_plans(template_id):
    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    values = pd.read_csv(source).to_numpy(dtype=float)
    axis = prepare_scientific(source, template_id).plot_spec.axis_plan
    padding = 0.25 if template_id == "raincloud" else 0.05
    span = float(values.max() - values.min())

    assert axis.y_from == pytest.approx(float(values.min()) - span * padding)
    assert axis.y_to == pytest.approx(float(values.max()) + span * padding)


def test_violin_mixed_ranges_and_outliers_are_not_trimmed(tmp_path):
    source = tmp_path / "mixed_violin.csv"
    frame = pd.DataFrame(
        {
            "Compact": [0.8, 0.9, 0.94, 0.99, 1.02, 1.03, 1.1, 1.2],
            "Wide": [-20.0, -4.0, -1.0, 0.0, 2.0, 3.0, 5.0, 60.0],
            "High": [85.0, 89.0, 90.0, 94.0, 96.0, 98.0, 99.0, 150.0],
        }
    )
    frame.to_csv(source, index=False)
    before = source.read_bytes()
    preparation = prepare_scientific(source, "violin")

    assert preparation.plot_spec.axis_plan.y_from == pytest.approx(-62.5)
    assert preparation.plot_spec.axis_plan.y_to == pytest.approx(192.5)
    assert preparation.row_count == 8
    assert source.read_bytes() == before


def test_violin_preview_uses_the_frozen_axis_plan():
    from origin_sciplot.scientific_preview import _build_scientific_preview_figure

    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    preparation = prepare_scientific(source, "violin")
    figure = _build_scientific_preview_figure(preparation)
    plan = preparation.plot_spec.axis_plan

    assert figure.axes[0].get_ylim() == pytest.approx((plan.y_from, plan.y_to))
    figure.clear()


def test_violin_native_autoscale_report_is_diagnostic_not_a_density_claim():
    from origin_sciplot.origin_backend.evidence_renderer import _violin_viewport_report

    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    frame = pd.read_csv(source)
    preparation = prepare_scientific(source, "violin")
    plan = preparation.plot_spec.axis_plan
    before = frame.copy(deep=True)
    report = _violin_viewport_report(
        frame,
        preparation,
        native_auto_y_limits=(0.5, 1.6),
        actual_y_limits=(plan.y_from, plan.y_to),
    )

    assert report["native_auto_y_limits"] == [0.5, 1.6]
    assert report["actual_y_limits"] == pytest.approx([plan.y_from, plan.y_to])
    assert report["native_auto_range_is_density_extent"] is False
    assert report["density_tail_visibility_requires_visual_qa"] is True
    assert report["source_counts"] == {column: 32 for column in frame.columns}
    pd.testing.assert_frame_equal(frame, before)


def test_violin_native_readback_must_match_plan_and_preserve_extremes():
    from origin_sciplot.origin_backend.evidence_renderer import _violin_viewport_report
    from origin_sciplot.origin_backend.safe_errors import OriginDrawError

    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    frame = pd.read_csv(source)
    preparation = prepare_scientific(source, "violin")

    with pytest.raises(OriginDrawError, match="violin Y limits"):
        _violin_viewport_report(
            frame,
            preparation,
            native_auto_y_limits=(0.5, 1.6),
            actual_y_limits=(0.8, 1.2),
        )

    # Even a matching readback must not validate a viewport that hides raw
    # extrema. Keep this separate from the KDE-tail visual review requirement.
    narrow = replace(
        preparation,
        plot_spec=replace(
            preparation.plot_spec,
            axis_plan=replace(preparation.plot_spec.axis_plan, y_from=0.8, y_to=1.2),
        ),
    )
    with pytest.raises(OriginDrawError, match="exclude source observations"):
        _violin_viewport_report(
            frame,
            narrow,
            native_auto_y_limits=(0.5, 1.6),
            actual_y_limits=(0.8, 1.2),
        )


def test_violin_restores_frozen_y_after_label_binding_and_title_refresh(monkeypatch):
    from origin_sciplot.origin_backend import evidence_renderer as renderer

    source = ROOT / "examples" / "gallery" / "violin_distributions.csv"
    frame = pd.read_csv(source)
    preparation = prepare_scientific(source, "violin")
    expected_labels = list(frame.columns)
    written_sheets = []

    class Sheet:
        def __init__(self, name):
            self.name = name
            self.frame = None
            self.labels = None

        def from_df(self, data):
            self.frame = data.copy(deep=True)

        def cols_axis(self, designation):
            assert designation == "y"

        def activate(self):
            pass

        def lt_range(self, _full):
            return f"[Book{written_sheets.index(self) + 1}]1"

        def from_list(self, column, values, *, lname, axis):
            assert (column, lname, axis) == (0, "GroupLabel", "N")
            self.labels = list(values)

        def to_list(self, column):
            assert column == 0
            return list(self.labels)

    class Axis:
        def __init__(self, layer, name):
            self.layer, self.name = layer, name

        def set_limits(self, lower, upper, step):
            self.layer.values.update(
                {f"{self.name}.from": lower, f"{self.name}.to": upper, f"{self.name}.inc": step}
            )

    class Layer:
        def __init__(self):
            self.values = {"x.label.table": 1, "x.label.type": 7, "y.from": 0.7, "y.to": 1.5}
            self.obj = self

        def group(self, _grouped):
            pass

        def activate(self):
            pass

        def rescale(self):
            self.values.update({"y.from": 0.7, "y.to": 1.5})

        def axis(self, name):
            return Axis(self, name)

        def plot_list(self):
            return [object() for _ in range(3)]

        def set_int(self, key, value):
            self.values[key] = value

        set_float = set_int

        def get_int(self, key):
            return self.values[key]

        get_float = get_int

        def LT_execute(self, command):
            assert "axis -ps X T" in command
            self.values.update({"x.label.type": 2, "y.from": 0.7, "y.to": 1.5})
            return True

    layer = Layer()

    class Graph:
        def __getitem__(self, index):
            assert index == 0
            return layer

        def activate(self):
            pass

        def set_int(self, _key, _value):
            pass

    graph = Graph()

    class Origin:
        def new_sheet(self, kind, name):
            assert kind == "w"
            sheet = Sheet(name)
            written_sheets.append(sheet)
            return sheet

        def lt_exec(self, _command):
            return True

        def find_graph(self):
            return graph

        def ocolor(self, _color):
            return 0

    def title_refresh(*_args, **_kwargs):
        # The true Origin probe showed this late range reset after labels and
        # titles; a restore performed only before this point is insufficient.
        layer.values.update({"y.from": 0.7, "y.to": 1.5})
        return {}, {}, {}

    monkeypatch.setattr(renderer, "_source_sheet", lambda *_args: None)
    monkeypatch.setattr(renderer, "_apply_page_layer", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(renderer, "_style_evidence_axes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(renderer, "_style_plot_family", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(renderer, "_remove_label", lambda *_args: None)
    monkeypatch.setattr(renderer, "_style_titles", title_refresh)
    monkeypatch.setattr(renderer, "_apply_axis_label_font", lambda *_args: None)
    monkeypatch.setattr(
        renderer, "_clean_numeric_x_axis", lambda *_args: layer.values.update({"x.label.table": 0})
    )
    monkeypatch.setattr(renderer, "_validate_axes", lambda *_args: dict(layer.values))

    _graph, report = renderer._build_distribution_graph(Origin(), frame, preparation)
    axis = preparation.plot_spec.axis_plan

    assert report["origin_violin_viewport"]["actual_y_limits"] == pytest.approx([axis.y_from, axis.y_to])
    binding = report["origin_group_label_binding"]
    assert binding["labels"] == expected_labels
    assert binding["source_columns"] == expected_labels
    assert binding["explicit_after"] == {"x.label.table": 0, "x.label.type": 2}
    assert binding["y_after_binding_and_titles"] == [0.7, 1.5]
    assert report["origin_helper_columns"] == ["GroupLabel"]
    assert report["origin_plot_data_columns"] == expected_labels
    pd.testing.assert_frame_equal(written_sheets[0].frame, frame)
    assert written_sheets[1].labels == expected_labels
