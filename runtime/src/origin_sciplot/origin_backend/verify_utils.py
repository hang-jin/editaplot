"""Verification helpers for Origin-generated artifacts."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from .base_style_contract import FIXED_ORIGIN_STYLE, pt_to_origin_width_units


def require_nonempty(path: str | Path) -> None:
    candidate = Path(path)
    if not candidate.is_file() or candidate.stat().st_size <= 0:
        raise RuntimeError(f"Required output was not generated: {candidate.name}")


def verify_text_sizes(
    labels: Mapping[str, Any],
    expected_points: Mapping[str, float],
    *,
    tolerance: float = 0.05,
) -> dict[str, float]:
    """Read back Origin text-object point sizes and enforce the locked contract."""
    state: dict[str, float] = {}
    for name, expected in expected_points.items():
        label = labels.get(name)
        if label is None:
            raise RuntimeError(f"Origin text verification failed: missing {name}")
        actual = float(label.get_float("fsize"))
        state[f"{name}.fsize"] = actual
        if abs(actual - float(expected)) > tolerance:
            raise RuntimeError(
                f"Origin text verification failed: {name}.fsize={actual:g}, expected {expected:g}"
            )
    return state


def verify_text_fonts(
    op: Any,
    labels: Mapping[str, Any],
    font_family: str,
    *,
    tolerance: float = 0.5,
) -> dict[str, int | str]:
    """Read back every editable Origin text object's font code.

    Origin does not reliably cascade a page font to axis titles, legends, and
    manually added labels.  Each object must therefore be styled separately
    and verified separately, especially after a dataset-backed axis label is
    rebound with ``axis -ps``.
    """
    expected = int(round(float(op.lt_float(f"font({font_family})"))))
    state: dict[str, int | str] = {
        "font_family_expected": font_family,
        "font_code_expected": expected,
    }
    for name, label in labels.items():
        if label is None:
            raise RuntimeError(f"Origin font verification failed: missing {name}")
        actual = int(round(float(label.get_float("font"))))
        state[f"{name}.font_code"] = actual
        if abs(actual - expected) > tolerance:
            raise RuntimeError(
                f"Origin font verification failed: {name}.font={actual}, expected "
                f"{font_family} ({expected})"
            )
    return state


def _read_plot_option(op: Any, plot: Any, option: str, variable_name: str) -> float:
    command = f"{{range rr={plot.lt_range()};get rr {option} {variable_name};}}"
    result = plot.layer.LT_execute(command)
    if result is False:
        raise RuntimeError(f"Origin plot verification command failed: {option}")
    value = float(op.lt_float(variable_name))
    if not math.isfinite(value):
        raise RuntimeError(f"Origin plot verification returned a non-finite value: {option}")
    return value


def verify_plot_line_widths(
    op: Any,
    plots: Mapping[str, Any],
    expected_points: float,
    *,
    tolerance_units: float = 1.0,
) -> dict[str, dict[str, float]]:
    """Read back visible DataPlot widths; LabTalk ``get -w`` returns pt x 500."""
    expected_units = float(pt_to_origin_width_units(expected_points))
    state: dict[str, dict[str, float]] = {}
    for index, (name, plot) in enumerate(plots.items()):
        actual_units = _read_plot_option(op, plot, "-w", f"__osc_width_{index}")
        state[name] = {
            "set_w_units": actual_units,
            "line_width_pt": actual_units / 500.0,
        }
        if abs(actual_units - expected_units) > tolerance_units:
            raise RuntimeError(
                f"Origin plot width verification failed: {name}={actual_units / 500.0:g} pt, "
                f"expected {expected_points:g} pt"
            )
    return state


def verify_plot_color(
    op: Any,
    plot: Any,
    expected_html: str,
    *,
    variable_name: str,
) -> dict[str, float | str]:
    """Read back the effective line/symbol edge color after a ``set -c`` call."""
    actual = _read_plot_option(op, plot, "-c", variable_name)
    expected = float(op.ocolor(expected_html))
    if int(actual) != int(expected):
        raise RuntimeError(
            f"Origin plot color verification failed: {actual:g}, expected {expected:g} "
            f"for {expected_html}"
        )
    return {
        "html": expected_html,
        "origin_color_code": actual,
    }


def verify_symbol_style(
    op: Any,
    plot: Any,
    *,
    expected_size_pt: float,
    expected_edge_percent: float,
    expected_kind: int = 2,
    tolerance: float = 0.05,
) -> dict[str, float | int]:
    """Read back a scatter symbol's point size and radius-relative edge thickness."""
    kind = int(plot.symbol_kind)
    size = _read_plot_option(op, plot, "-z", "__osc_symbol_size")
    edge = _read_plot_option(op, plot, "-kh", "__osc_symbol_edge")
    if kind != expected_kind:
        raise RuntimeError(
            f"Origin symbol kind verification failed: {kind}, expected {expected_kind}"
        )
    if abs(size - expected_size_pt) > tolerance:
        raise RuntimeError(
            f"Origin symbol size verification failed: {size:g} pt, expected {expected_size_pt:g} pt"
        )
    if abs(edge - expected_edge_percent) > tolerance:
        raise RuntimeError(
            "Origin symbol edge verification failed: "
            f"{edge:g}% of radius, expected {expected_edge_percent:g}%"
        )
    return {
        "symbol_kind": kind,
        "symbol_size_pt": size,
        "symbol_edge_percent_of_radius": edge,
    }


def verify_page_and_layer(
    graph: Any,
    layer: Any,
    *,
    style: Any = FIXED_ORIGIN_STYLE,
    expected_layer: Mapping[str, float] | None = None,
) -> dict[str, float]:
    expected = {
        "left_percent": style.layer_left_percent,
        "top_percent": style.layer_top_percent,
        "width_percent": style.layer_width_percent,
        "height_percent": style.layer_height_percent,
        "factor": style.layer_factor,
    }
    if expected_layer is not None:
        expected.update(expected_layer)

    for _attempt in range(3):
        page_cm = {
            "width_cm": graph.obj.GetWidth() * 2.54,
            "height_cm": graph.obj.GetHeight() * 2.54,
        }
        layer_values = {
            "left_percent": layer.get_float("left"),
            "top_percent": layer.get_float("top"),
            "width_percent": layer.get_float("width"),
            "height_percent": layer.get_float("height"),
            "factor": layer.get_float("factor"),
        }
        page_ok = (
            abs(page_cm["width_cm"] - style.page_width_cm) <= 0.01
            and abs(page_cm["height_cm"] - style.page_height_cm) <= 0.01
        )
        layer_ok = all(abs(layer_values[key] - value) <= 0.02 for key, value in expected.items())
        if page_ok and layer_ok:
            return {**page_cm, **layer_values}

        graph.activate()
        graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;doc -uw;")
        graph.obj.PutWidth(style.page_width_cm / 2.54)
        graph.obj.PutHeight(style.page_height_cm / 2.54)
        layer.set_int("unit", 1)
        layer.set_float("left", expected["left_percent"])
        layer.set_float("top", expected["top_percent"])
        layer.set_float("width", expected["width_percent"])
        layer.set_float("height", expected["height_percent"])
        layer.set_int("fixed", style.layer_fixed)
        layer.set_float("factor", expected["factor"])
        graph.obj.LT_execute("doc -uw;")

    page_cm = {
        "width_cm": graph.obj.GetWidth() * 2.54,
        "height_cm": graph.obj.GetHeight() * 2.54,
    }
    if abs(page_cm["width_cm"] - style.page_width_cm) > 0.01:
        raise RuntimeError(
            f"Origin page width verification failed: got {page_cm['width_cm']:.3f} cm, "
            f"expected {style.page_width_cm:.3f} cm"
        )
    if abs(page_cm["height_cm"] - style.page_height_cm) > 0.01:
        raise RuntimeError(
            f"Origin page height verification failed: got {page_cm['height_cm']:.3f} cm, "
            f"expected {style.page_height_cm:.3f} cm"
        )
    for key, value in expected.items():
        actual = layer.get_float(key.removesuffix("_percent") if key.endswith("_percent") else key)
        if abs(actual - value) > 0.02:
            raise RuntimeError(f"Origin layer {key} verification failed: got {actual:.3f}, expected {value:.3f}")
    return {
        **page_cm,
        "left_percent": layer.get_float("left"),
        "top_percent": layer.get_float("top"),
        "width_percent": layer.get_float("width"),
        "height_percent": layer.get_float("height"),
        "factor": layer.get_float("factor"),
    }
