"""Measured editable row labels for ordinary heatmaps (not confusion matrices)."""

from __future__ import annotations

import math
from typing import Any

from origin_sciplot.heatmap_layout import (
    HeatmapLayoutPlan,
    resolve_heatmap_row_label_anchors,
    verify_heatmap_row_label_geometry,
)
from origin_sciplot.scientific_visual import AdaptiveOriginStyle

from .safe_errors import OriginDrawError

_Y_LABEL_PROPERTIES = ("y.showLabels", "y.showlabel", "y.label.show")


def _anchors(layout: HeatmapLayoutPlan, style: AdaptiveOriginStyle, geometry: dict[str, Any]):
    return resolve_heatmap_row_label_anchors(
        layout,
        page_width_cm=style.page_width_cm,
        layer_left_percent=geometry["left_percent"],
        layer_top_percent=geometry["top_percent"],
        layer_height_percent=geometry["height_percent"],
    )


def verify_heatmap_row_labels(
    op: Any,
    layer: Any,
    *,
    layout: HeatmapLayoutPlan,
    style: AdaptiveOriginStyle,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    """Re-read actual objects after refresh/export; page containment alone is insufficient."""

    if any(layer.get_int(prop) != 0 for prop in _Y_LABEL_PROPERTIES):
        raise OriginDrawError("Origin Heatmap restored automatic Y labels beside the page labels.")
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    font_code = float(op.lt_float(f"font({style.font_family})"))
    if not all(math.isfinite(value) and value > 0 for value in (page_width, page_height, font_code)):
        raise OriginDrawError("Origin Heatmap page dimensions or font readback are invalid.")
    labels = []
    previous_bottom = None
    for anchor in _anchors(layout, style, geometry):
        name = f"HeatmapRow{anchor.source_index + 1}"
        obj = layer.label(name)
        if obj is None:
            raise OriginDrawError(f"Origin Heatmap is missing row label {name}.")
        actual = {prop: float(obj.get_float(prop)) for prop in
                  ("left", "top", "width", "height", "fsize", "font", "rotate")}
        if not all(math.isfinite(value) for value in actual.values()):
            raise OriginDrawError(f"Origin Heatmap row label {name} has non-finite readback.")
        if str(obj.text).replace("\r\n", "\n") != anchor.text.replace("\r\n", "\n"):
            raise OriginDrawError(f"Origin Heatmap row label {name} no longer matches the source text.")
        if (
            any(obj.get_int(prop) != expected for prop, expected in
                (("attach", 1), ("showframe", 0), ("show", 1), ("bold", 0), ("link", 0)))
            or abs(actual["fsize"] - style.tick_label_size_pt) > 0.05
            or abs(actual["font"] - font_code) > 0.5
            or abs(actual["rotate"]) > 0.1
        ):
            raise OriginDrawError(f"Origin Heatmap row label {name} changed its font or display contract.")
        try:
            measured = verify_heatmap_row_label_geometry(
                anchor,
                left_percent=actual["left"] / page_width * 100,
                top_percent=actual["top"] / page_height * 100,
                width_percent=actual["width"] / page_width * 100,
                height_percent=actual["height"] / page_height * 100,
                page_width_cm=style.page_width_cm,
                layer_left_percent=geometry["left_percent"],
                y_label_gap_cm=layout.y_label_gap_cm,
            )
        except ValueError as error:
            raise OriginDrawError(f"Origin Heatmap row label {name}: {error}") from error
        if previous_bottom is not None and actual["top"] < previous_bottom:
            raise OriginDrawError(
                "Origin Heatmap row labels overlap vertically; use shorter labels or a taller page."
            )
        previous_bottom = actual["top"] + actual["height"]
        labels.append({"name": name, "source_index": anchor.source_index, "text": anchor.text, "link": 0,
                       **actual, **measured})
    return {"mode": "editable_page_labels", "planned_gap_cm": layout.y_label_gap_cm,
            "native_y_labels_hidden": True, "labels": labels}


def add_heatmap_row_labels(
    op: Any,
    graph: Any,
    layer: Any,
    *,
    layout: HeatmapLayoutPlan,
    style: AdaptiveOriginStyle,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    """Use the existing isolated page-label API, aligning measured widths to the right edge."""

    from .evidence_renderer import _add_shap_page_label

    for prop in _Y_LABEL_PROPERTIES:
        layer.set_int(prop, 0)
    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    for anchor in _anchors(layout, style, geometry):
        obj, _initial_state = _add_shap_page_label(
            op, graph, layer,
            name=f"HeatmapRow{anchor.source_index + 1}", text="Row label",
            center_x_percent=anchor.right_percent - 2,
            center_y_percent=anchor.center_y_percent,
            size_pt=style.tick_label_size_pt, font_family=style.font_family,
            bold=False, color="#000000",
        )
        # GObject.link=0 is documented since Origin 2015 SR1 and isolated on 2024b.
        # Disable substitutions before assigning source text, never after its first refresh.
        obj.set_int("link", 0)
        if obj.get_int("link") != 0:
            raise OriginDrawError("Origin Heatmap could not retain literal row-label text mode.")
        obj.text = anchor.text
        op.lt_exec("doc -uw;")
        obj.set_int("showframe", 0)
        obj.set_float("left", page_width * anchor.right_percent / 100 - obj.get_float("width"))
        obj.set_float("top", page_height * anchor.center_y_percent / 100 - obj.get_float("height") / 2)
    op.lt_exec("doc -uw;")
    return verify_heatmap_row_labels(op, layer, layout=layout, style=style, geometry=geometry)
