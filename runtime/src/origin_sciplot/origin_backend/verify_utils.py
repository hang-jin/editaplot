"""Verification helpers for Origin-generated artifacts."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .base_style_contract import FIXED_ORIGIN_STYLE, pt_to_origin_width_units
from .safe_errors import OriginGeometryError

# Origin stores page dimensions in internal/printer units and can round an
# adaptive size by roughly one tenth of a millimetre on readback.  A 0.3 mm
# gate accepts that quantization while remaining far below a visible layout
# change.
PAGE_SIZE_TOLERANCE_CM = 0.03
LAYER_GEOMETRY_TOLERANCE_PERCENT = 0.03


class NativePlotReference:
    """An owned plot slot that survives OriginExt GetIndex proxy invalidation."""

    def __init__(self, native_range: str, layer: Any) -> None:
        match = re.fullmatch(r"\[[\w]+\][1-9]\d*![1-9]\d*", native_range)
        if match is None:
            raise ValueError("Expected an explicit native graph-layer plot range")
        self._native_range = native_range
        self.layer = layer
        self.native_index = int(native_range.rsplit("!", 1)[1])

    def lt_range(self) -> str:
        return self._native_range

    def set_cmd(self, *commands: str) -> None:
        script = "{" + f"range rr={self._native_range};" + "".join(f"set rr {c};" for c in commands) + "}"
        if not self.layer.LT_execute(script):
            raise RuntimeError("Origin could not style the owned native plot range")


def _finite_float(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"Origin geometry readback is non-finite: {label}")
    return number


def _read_bridge_geometry(layer: Any) -> dict[str, float | None]:
    """Read the originpro bridge for diagnostics without making it canonical."""

    state: dict[str, float | None] = {}
    for output_name, property_name in (
        ("bridge_layer_unit", "unit"),
        ("bridge_left_percent", "left"),
        ("bridge_top_percent", "top"),
        ("bridge_width_percent", "width"),
        ("bridge_height_percent", "height"),
        ("bridge_factor", "factor"),
    ):
        try:
            value = float(layer.get_float(property_name))
        except Exception:
            value = math.nan
        state[output_name] = value if math.isfinite(value) else None
    return state


def read_layer_geometry_percent(origin: Any, layer: Any) -> dict[str, Any]:
    """Read percent-of-page geometry through two cross-checked LabTalk paths.

    A reported Origin 2026b SR1 environment returned a conflicting ``left``
    value through the originpro ``GetNumProp`` bridge. LabTalk's layer
    properties and the documented ``layer -x`` command provide the native
    cross-check needed to distinguish a bridge-only disagreement from a real
    layout failure. The bridge values are retained as diagnostics, but never
    override two agreeing native readbacks.

    ``layer -x`` has a non-intuitive official order: ``v1=width``,
    ``v2=height``, ``v3=left``, and ``v4=top``.
    """

    layer.activate()
    # Clear the shared v-registers first.  If a version returns success without
    # refreshing them, the finite-value gate below must fail instead of
    # accepting geometry left behind by an earlier layer.
    command_ok = layer.obj.LT_execute(
        "v1=NA();v2=NA();v3=NA();v4=NA();layer -x;"
    )
    if not command_ok:
        raise RuntimeError("Origin LabTalk layer geometry command failed: layer -x")

    # Capture v1..v4 immediately; later LabTalk expression evaluations must
    # not get a chance to replace the command result on another version.
    layer_x = {
        "width_percent": _finite_float(
            origin.lt_float("v1"), "layer -x v1 (width)"
        ),
        "height_percent": _finite_float(
            origin.lt_float("v2"), "layer -x v2 (height)"
        ),
        "left_percent": _finite_float(
            origin.lt_float("v3"), "layer -x v3 (left)"
        ),
        "top_percent": _finite_float(
            origin.lt_float("v4"), "layer -x v4 (top)"
        ),
    }
    direct = {
        "layer_unit": _finite_float(origin.lt_float("layer.unit"), "layer.unit"),
        "left_percent": _finite_float(origin.lt_float("layer.left"), "layer.left"),
        "top_percent": _finite_float(origin.lt_float("layer.top"), "layer.top"),
        "width_percent": _finite_float(origin.lt_float("layer.width"), "layer.width"),
        "height_percent": _finite_float(origin.lt_float("layer.height"), "layer.height"),
        "factor": _finite_float(origin.lt_float("layer.factor"), "layer.factor"),
    }
    if abs(direct["layer_unit"] - 1.0) > LAYER_GEOMETRY_TOLERANCE_PERCENT:
        raise RuntimeError(
            "Origin layer geometry unit verification failed: "
            f"got {direct['layer_unit']:.3f}, expected 1 (% of page)"
        )
    for key, layer_x_value in layer_x.items():
        direct_value = direct[key]
        if abs(direct_value - layer_x_value) > LAYER_GEOMETRY_TOLERANCE_PERCENT:
            raise RuntimeError(
                "Origin LabTalk layer geometry paths disagree: "
                f"{key} direct={direct_value:.3f}, layer-x={layer_x_value:.3f}"
            )

    bridge = _read_bridge_geometry(layer)
    bridge_geometry_consistent = (
        bridge["bridge_layer_unit"] is not None
        and abs(float(bridge["bridge_layer_unit"]) - direct["layer_unit"])
        <= LAYER_GEOMETRY_TOLERANCE_PERCENT
        and all(
            bridge[f"bridge_{key}"] is not None
        and abs(float(bridge[f"bridge_{key}"]) - direct[key])
        <= LAYER_GEOMETRY_TOLERANCE_PERCENT
            for key in (
                "left_percent",
                "top_percent",
                "width_percent",
                "height_percent",
                "factor",
            )
        )
    )
    return {
        **direct,
        "geometry_readback_source": "labtalk_crosscheck",
        "layer_x_left_percent": layer_x["left_percent"],
        "layer_x_top_percent": layer_x["top_percent"],
        "layer_x_width_percent": layer_x["width_percent"],
        "layer_x_height_percent": layer_x["height_percent"],
        **bridge,
        "bridge_geometry_consistent": bridge_geometry_consistent,
    }


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
                f"Origin font verification failed: {name}.font={actual}, expected {font_family} ({expected})"
            )
    return state


def _read_plot_option(op: Any, plot: Any, option: str, variable_name: str) -> float:
    command = f"{{range rr={plot.lt_range()};get rr {option} {variable_name};}}"
    result = plot.layer.LT_execute(command)
    if not result:
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
            f"Origin plot color verification failed: {actual:g}, expected {expected:g} for {expected_html}"
        )
    return {
        "html": expected_html,
        "origin_color_code": actual,
    }


def apply_column_style(op: Any, plot: Any, color: str, *, border_width_pt: float) -> None:
    """Set the documented column fill, border and point-sized border width."""
    if not math.isfinite(border_width_pt) or border_width_pt <= 0:
        raise ValueError("Column border width must be a positive point value")
    code = int(op.ocolor(color))
    plot.set_cmd(f"-pfb {code}")
    plot.set_cmd(f"-pbc {code}")
    plot.set_cmd(f"-vw {border_width_pt:g}")


def verify_column_colors(
    op: Any, plot: Any, expected_html: str, *, variable_name: str
) -> dict[str, float | str]:
    """Read the column fill and border independently; -c is a line property."""
    expected = int(op.ocolor(expected_html))
    fill = _read_plot_option(op, plot, "-pfb", f"{variable_name}_fill")
    border = _read_plot_option(op, plot, "-pbc", f"{variable_name}_border")
    if int(fill) != expected or int(border) != expected:
        raise RuntimeError(
            f"Origin column color verification failed: fill={fill:g}, border={border:g}, "
            f"expected {expected} for {expected_html}"
        )
    return {"html": expected_html, "fill_origin_color_code": fill, "border_origin_color_code": border}


def verify_column_border_widths(
    op: Any, plots: Mapping[str, Any], expected_points: float
) -> dict[str, dict[str, float]]:
    """Measure native read units and restore the frozen point width.

    The documented -vw setter uses points. Old get documentation describes
    -pbw as pt*500, whereas 10.15 returns points. Calibrate on the owned plot
    instead of mistaking a 500-times-too-wide border for another unit encoding.
    """
    if not math.isfinite(expected_points) or expected_points <= 0:
        raise ValueError("Column border width must be a positive point value")
    state: dict[str, dict[str, float]] = {}
    if not plots:
        return state
    head = next(iter(plots.values()))
    try:
        head.set_cmd("-vw 1")
        scale = _read_plot_option(op, head, "-pbw", "__osc_bar_reference_unit")
        if not any(math.isclose(scale, candidate, rel_tol=0, abs_tol=0.001) for candidate in (1, 500)):
            raise RuntimeError("Origin column border width has an unknown native unit")
    finally:
        head.set_cmd(f"-vw {expected_points:g}")
    for index, (name, plot) in enumerate(plots.items()):
        plot.set_cmd("-pbw 1")
        probe = _read_plot_option(op, plot, "-pbw", f"__osc_bar_setter_unit_{index}")
        if not any(math.isclose(probe, candidate, rel_tol=0, abs_tol=0.001) for candidate in (1, 500)):
            plot.set_cmd(f"-vw {expected_points:g}")
            raise RuntimeError("Origin column border setter has an unknown native unit")
        setter_units_per_pt = scale / probe
        plot.set_cmd(f"-pbw {expected_points * setter_units_per_pt:g}")
        actual = _read_plot_option(op, plot, "-pbw", f"__osc_bar_width_{index}")
        points = actual / scale
        if not math.isclose(points, expected_points, rel_tol=0, abs_tol=0.01):
            raise RuntimeError(
                f"Origin column border width verification failed: {name}={points:g} pt, "
                f"expected {expected_points:g} pt"
            )
        state[name] = {
            "native_value": actual, "native_units_per_pt": scale, "border_width_pt": points,
            "setter_units_per_pt": setter_units_per_pt,
        }
    return state


def verify_symbol_style(
    op: Any,
    plot: Any,
    *,
    expected_size_pt: float,
    expected_edge_percent: float,
    expected_symbol_kind: int | None = None,
    expected_symbol_interior: int | None = None,
    tolerance: float = 0.05,
) -> dict[str, float]:
    """Read back the requested scatter-symbol contract from the merged plot."""
    size = _read_plot_option(op, plot, "-z", "__osc_symbol_size")
    edge = _read_plot_option(op, plot, "-kh", "__osc_symbol_edge")
    kind = (
        _read_plot_option(op, plot, "-k", "__osc_symbol_kind")
        if expected_symbol_kind is not None
        else None
    )
    interior = (
        _read_plot_option(op, plot, "-kf", "__osc_symbol_interior")
        if expected_symbol_interior is not None
        else None
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
    if kind is not None and abs(kind - float(expected_symbol_kind)) > tolerance:
        raise RuntimeError(
            f"Origin symbol kind verification failed: {kind:g}, "
            f"expected {expected_symbol_kind}"
        )
    if interior is not None and abs(interior - float(expected_symbol_interior)) > tolerance:
        raise RuntimeError(
            f"Origin symbol interior verification failed: {interior:g}, "
            f"expected {expected_symbol_interior}"
        )
    state = {
        "symbol_size_pt": size,
        "symbol_edge_percent_of_radius": edge,
    }
    if kind is not None:
        state["symbol_kind"] = kind
    if interior is not None:
        state["symbol_interior"] = interior
    return state


def read_page_geometry_cm(origin: Any, graph: Any) -> dict[str, Any]:
    """Use documented printer dots/resolution for physical page dimensions."""
    graph.activate()
    native = {
        name: _finite_float(origin.lt_float(f"page.{name}"), f"page.{name}")
        for name in ("width", "height", "resx", "resy")
    }
    for name, value in native.items():
        if value <= 0:
            raise RuntimeError(f"Origin page geometry requires positive page.{name}")
    width = _finite_float(native["width"] / native["resx"] * 2.54, "page.width_cm")
    height = _finite_float(native["height"] / native["resy"] * 2.54, "page.height_cm")
    bridge: dict[str, float | None] = {}
    for dimension, method in (("width", "GetWidth"), ("height", "GetHeight")):
        try:
            value = float(getattr(graph.obj, method)()) * 2.54
            bridge[dimension] = value if math.isfinite(value) else None
        except Exception:  # Optional COM bridge diagnostics, never the physical-size source.
            bridge[dimension] = None
    return {
        "width_cm": width, "height_cm": height,
        "page_geometry_readback_source": "labtalk_printer_dots",
        "page_width_dots": native["width"], "page_height_dots": native["height"],
        "page_resx": native["resx"], "page_resy": native["resy"],
        "page_bridge_width_cm": bridge["width"], "page_bridge_height_cm": bridge["height"],
        "page_bridge_geometry_consistent": all(
            bridge[name] is not None and abs(float(bridge[name]) - actual) <= PAGE_SIZE_TOLERANCE_CM
            for name, actual in (("width", width), ("height", height))
        ),
    }


def verify_page_and_layer(
    graph: Any,
    layer: Any,
    *,
    origin: Any,
    style: Any = FIXED_ORIGIN_STYLE,
    expected_layer: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    expected = {
        "left_percent": style.layer_left_percent,
        "top_percent": style.layer_top_percent,
        "width_percent": style.layer_width_percent,
        "height_percent": style.layer_height_percent,
        "factor": style.layer_factor,
    }
    if expected_layer is not None:
        expected.update(expected_layer)

    def read_layer() -> dict[str, Any]:
        return read_layer_geometry_percent(origin, layer)

    def read_page() -> dict[str, Any]:
        return read_page_geometry_cm(origin, graph)

    def restore_contract() -> None:
        graph.activate()
        for name in ("resx", "resy"):
            if _finite_float(origin.lt_float(f"page.{name}"), f"page.{name}") <= 0:
                raise RuntimeError(f"Origin page geometry requires positive page.{name}")
        if not graph.obj.LT_execute(
            "page.updatetoprinter=0;page.kar=0;"
            f"page.width=({style.page_width_cm:.17g}/2.54)*page.resx;"
            f"page.height=({style.page_height_cm:.17g}/2.54)*page.resy;doc -uw;"
        ):
            raise RuntimeError("Origin native page size assignment failed")
        layer.activate()
        layer.set_int("unit", 1)
        layer.set_float("left", expected["left_percent"])
        layer.set_float("top", expected["top_percent"])
        layer.set_float("width", expected["width_percent"])
        layer.set_float("height", expected["height_percent"])
        layer.set_int("fixed", style.layer_fixed)
        layer.set_float("factor", expected["factor"])
        # The property assignments are documented LabTalk and provide a
        # version-neutral write path in addition to the originpro setters.
        layer.obj.LT_execute(
            "layer.unit=1;"
            f"layer.left={expected['left_percent']:g};"
            f"layer.top={expected['top_percent']:g};"
            f"layer.width={expected['width_percent']:g};"
            f"layer.height={expected['height_percent']:g};"
            f"layer.fixed={int(style.layer_fixed)};"
            f"layer.factor={expected['factor']:g};"
            "doc -uw;"
        )

    layer_values: dict[str, Any] = {}
    for _attempt in range(3):
        try:
            page_cm = read_page()
            layer_values = read_layer()
        except RuntimeError:
            page_cm = {}
            layer_values = {}
        page_ok = bool(page_cm) and (
            abs(page_cm["width_cm"] - style.page_width_cm) <= PAGE_SIZE_TOLERANCE_CM
            and abs(page_cm["height_cm"] - style.page_height_cm) <= PAGE_SIZE_TOLERANCE_CM
        )
        layer_ok = bool(layer_values) and all(
            abs(float(layer_values[key]) - value) <= LAYER_GEOMETRY_TOLERANCE_PERCENT
            for key, value in expected.items()
        )
        if page_ok and layer_ok:
            return {**page_cm, **layer_values}
        restore_contract()

    try:
        page_cm = read_page()
    except RuntimeError as exc:
        raise RuntimeError(f"Origin page geometry verification failed: {exc}") from exc
    if abs(page_cm["width_cm"] - style.page_width_cm) > PAGE_SIZE_TOLERANCE_CM:
        raise OriginGeometryError(
            f"Origin page width verification failed: got {page_cm['width_cm']:.3f} cm, "
            f"expected {style.page_width_cm:.3f} cm",
            diagnostics={"geometry_check": "page_width_cm", "expected_value": style.page_width_cm,
                         "measured_value": page_cm["width_cm"], "tolerance_value": PAGE_SIZE_TOLERANCE_CM},
        )
    if abs(page_cm["height_cm"] - style.page_height_cm) > PAGE_SIZE_TOLERANCE_CM:
        raise OriginGeometryError(
            f"Origin page height verification failed: got {page_cm['height_cm']:.3f} cm, "
            f"expected {style.page_height_cm:.3f} cm",
            diagnostics={"geometry_check": "page_height_cm", "expected_value": style.page_height_cm,
                         "measured_value": page_cm["height_cm"], "tolerance_value": PAGE_SIZE_TOLERANCE_CM},
        )
    try:
        layer_values = read_layer()
    except RuntimeError as exc:
        raise RuntimeError(f"Origin layer geometry verification failed: {exc}") from exc
    for key, value in expected.items():
        actual = float(layer_values[key])
        if abs(actual - value) > LAYER_GEOMETRY_TOLERANCE_PERCENT:
            raise RuntimeError(
                f"Origin layer {key} verification failed: got {actual:.3f}, expected {value:.3f}"
            )
    return {**page_cm, **layer_values}
