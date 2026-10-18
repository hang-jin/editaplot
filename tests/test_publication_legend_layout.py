from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))

from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.origin_backend.scientific_renderer import _position_publication_legend  # noqa: E402
from origin_sciplot.scientific_visual import resolve_adaptive_style  # noqa: E402


@pytest.mark.parametrize(
    "kind", ["line", "stacked_line", "line_error", "scatter", "diagnostic_curve", "decision_curve"]
)
def test_comparison_legends_have_a_reserved_physical_column(kind):
    style = resolve_adaptive_style(
        template_id="test", plot_kind=kind, row_count=100, series_count=3, max_label_length=20
    )
    right_cm = style.page_width_cm * (100 - style.layer_left_percent - style.layer_width_percent) / 100
    assert right_cm >= 6.4
    assert style.profile_name.endswith("-external-legend")
    assert style.legend_size_pt >= 17
    assert style.x_title_upshift_page_percent == 0


def test_legend_reservation_adapts_to_long_labels_without_shrinking_text():
    short = resolve_adaptive_style(
        template_id="trend", plot_kind="line", row_count=10, series_count=2, max_label_length=8
    )
    long = resolve_adaptive_style(
        template_id="trend", plot_kind="line", row_count=10, series_count=2, max_label_length=40
    )
    assert long.page_width_cm > short.page_width_cm
    assert long.legend_size_pt == short.legend_size_pt
    right_cm = long.page_width_cm * (
        100 - long.layer_left_percent - long.layer_width_percent
    ) / 100
    # Full scientific series labels include units, not only short method names.
    assert right_cm >= 12.0


def test_one_curve_does_not_get_an_unused_legend_column():
    style = resolve_adaptive_style(template_id="trend", plot_kind="line", row_count=100, series_count=1)
    assert not style.profile_name.endswith("-external-legend")


def test_existing_composite_shap_profile_is_not_changed_by_generic_legend_rule():
    style = resolve_adaptive_style(
        template_id="shap_summary", plot_kind="shap_summary", row_count=8, series_count=8
    )
    assert not style.profile_name.endswith("-external-legend")


@pytest.mark.parametrize("legend_width,valid", [(140, True), (1000, False)])
def test_single_series_legend_has_explicit_page_attachment_and_bounds(legend_width, valid):
    style = resolve_adaptive_style(template_id="trend", plot_kind="line", row_count=10, series_count=1)
    values = {"width": legend_width, "height": 100, "showframe": 0, "top": -50, "left": 1200}
    label = SimpleNamespace(
        set_int=values.__setitem__, set_float=values.__setitem__,
        get_int=values.__getitem__, get_float=values.__getitem__,
    )
    op = SimpleNamespace(lt_float=lambda key: 1000 if key == "page.width" else 700)
    layer = SimpleNamespace(obj=SimpleNamespace(LT_execute=lambda command: True))
    if not valid:
        with pytest.raises(OriginDrawError, match="page"):
            _position_publication_legend(op, layer, label, style)
    else:
        result = _position_publication_legend(op, layer, label, style)
        assert result["legend.attach"] == 1
        assert result["legend.outside_data_field"] is False
        assert 0 <= result["legend.left"] < 1000
        assert result["legend.top"] >= 0


@pytest.mark.parametrize("legend_width,valid", [(140, True), (500, False)])
def test_native_legend_bounds_are_checked_without_shrinking(legend_width, valid):
    style = resolve_adaptive_style(template_id="trend", plot_kind="line", row_count=10, series_count=3)
    values = {"width": legend_width, "height": 100, "showframe": 0}
    label = SimpleNamespace(
        set_int=values.__setitem__,
        set_float=values.__setitem__,
        get_int=values.__getitem__,
        get_float=values.__getitem__,
    )
    op = SimpleNamespace(lt_float=lambda key: 1000 if key == "page.width" else 700)
    layer = SimpleNamespace(obj=SimpleNamespace(LT_execute=lambda command: True))
    if not valid:
        with pytest.raises(OriginDrawError, match="reserved column"):
            _position_publication_legend(op, layer, label, style)
    else:
        readback = _position_publication_legend(op, layer, label, style)
        assert readback["legend.outside_data_field"]
        assert readback["legend.attach"] == 1
        assert readback["legend.width"] == legend_width
