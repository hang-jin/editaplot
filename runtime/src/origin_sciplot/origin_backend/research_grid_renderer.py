"""Lossless native physical-grid marks; no session, export or scientific transforms.

Origin's ``Plot Heatmap from Matrix Data`` example supplies the matrix/PID105
route: https://docs.originlab.com/python/examples/graphing/ . The color-level
commands reuse the verified SHAP scatter scale and dashboard ``_apply_ramp``;
Spectrum1 positioning reuses the categorical heatmap's page-unit properties.

The caller owns the graph and final font/title/page/layer geometry contract.
Pure tests are not live Origin evidence: a new composition remains experimental
until its native readback, OPJU/PNG/PDF/TIF and visual QA all pass.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

import numpy as np

from ..research_grid import PhysicalGrid
from .safe_errors import OriginDrawError
from .shap_dashboard_renderer import _apply_ramp
from .verify_utils import LAYER_GEOMETRY_TOLERANCE_PERCENT


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OriginDrawError(message, code="physical_grid_readback_failed")


def _range(value: Sequence[float], label: str) -> tuple[float, float]:
    try:
        values = tuple(map(float, value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise OriginDrawError(f"The {label} range must have two finite endpoints.") from exc
    _require(
        len(values) == 2 and all(map(math.isfinite, values)) and values[0] != values[1],
        f"The {label} range must have two distinct finite endpoints.",
    )
    return values[0], values[1]


def _matrix_values(grid: PhysicalGrid) -> np.ndarray:
    """Defend the public dataclass boundary without repairing or sorting it."""
    try:
        raw_arrays = [np.asarray(part) for part in (grid.x, grid.y, grid.values)]
        _require(
            all(array.dtype.kind in "iuf" for array in raw_arrays)
            and not any(
                isinstance(value, (bool, np.bool_))
                for part in (grid.x, grid.y, grid.values)
                for value in np.asarray(part, dtype=object).flat
            ),
            "Physical-grid coordinates and cells must be real measurements, not flags or complex values.",
        )
        x, y = np.asarray(grid.x, dtype=float), np.asarray(grid.y, dtype=float)
        values = np.asarray(grid.values, dtype=float)
        source_rows = np.asarray(grid.source_rows)
    except (TypeError, ValueError) as exc:
        raise OriginDrawError("The physical grid must be a finite rectangular matrix.") from exc
    for coordinates in (x, y):
        _require(
            coordinates.ndim == 1 and len(coordinates) >= 2 and bool(np.isfinite(coordinates).all()),
            "The physical grid needs at least two finite coordinates on each axis.",
        )
        with np.errstate(over="ignore", invalid="ignore"):
            steps = np.diff(coordinates)
        _require(
            bool(np.isfinite(steps).all())
            and bool(np.all(steps > 0) or np.all(steps < 0))
            and bool(np.allclose(steps, steps[0], rtol=1e-7, atol=abs(steps[0]) * 1e-10)),
            "Physical grid coordinates must remain uniformly spaced and monotone.",
        )
    _require(
        values.shape == (len(y), len(x)) and bool(np.isfinite(values).all()),
        "The physical grid must retain all finite source cell values.",
    )
    _require(
        source_rows.shape == values.shape
        and np.issubdtype(source_rows.dtype, np.integer)
        and bool((source_rows >= 0).all())
        and len(np.unique(source_rows)) == values.size,
        "The physical grid must retain unique source-row bindings for every cell.",
    )
    return values.copy()


def build_physical_grid_layer(
    op: Any,
    graph: Any,
    layer: Any,
    grid: PhysicalGrid,
    *,
    value_label: str,
    palette_hex: Sequence[str],
    z_range: Sequence[float],
    x_range: Sequence[float] | None = None,
    y_range: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Add one native matrix to an empty caller-owned layer and verify its marks.

    Defaults expose full half-step cell edges in source-coordinate direction.
    Explicit XY limits may reverse display, but may not clip cells. Z limits
    must be finite, increasing and contain every supplied value (no saturation).
    No title/font/geometry success is claimed; the caller must apply and verify
    those using its existing style helpers *after* constructing all layers.
    """
    values = _matrix_values(grid)
    zmin, zmax = _range(z_range, "color")
    _require(
        zmin < zmax
        and math.isfinite(zmax - zmin)
        and zmin <= float(values.min())
        and zmax >= float(values.max()),
        "The color range must increase and contain every source value.",
    )
    colors = tuple(palette_hex)
    _require(len(colors) == 101, "The physical grid requires exactly 101 supplied HEX colors.")
    _require(
        all(isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in colors),
        "Every physical-grid color must be a six-digit HEX value.",
    )
    _require(isinstance(value_label, str) and bool(value_label.strip()), "A matrix value label is required.")
    edges = grid.cell_edges
    limits = {
        "x": _range(edges[:2] if x_range is None else x_range, "X"),
        "y": _range(edges[2:] if y_range is None else y_range, "Y"),
    }
    for axis, physical_edges in (("x", edges[:2]), ("y", edges[2:])):
        _require(
            min(limits[axis]) <= min(physical_edges) and max(limits[axis]) >= max(physical_edges),
            f"The {axis.upper()} range must contain the complete physical cell edges.",
        )
    _require(len(layer.plot_list()) == 0, "The physical grid requires an empty caller-owned layer.")
    matrix = op.new_sheet("m", "Physical Grid Matrix")
    _require(matrix is not None, "Origin could not create the physical-grid matrix.")
    matrix.from_np(values)
    matrix.set_label(0, value_label)
    matrix.xymap = grid.xymap
    actual_values = np.asarray(matrix.to_np(), dtype=float)
    actual_mapping = tuple(map(float, matrix.xymap))
    _require(np.array_equal(actual_values, values), "Origin matrix values failed exact readback.")
    _require(actual_mapping == grid.xymap, "Origin matrix xymap failed exact physical-coordinate readback.")
    graph.activate()
    layer.activate()
    plot = layer.add_mplot(matrix, 0, type=105)
    _require(plot is not None, "Origin could not create the native PID105 matrix heatmap.")
    _require(
        len(layer.plot_list()) == 1 and int(layer.get_int("plot.pid")) == 105,
        "Origin physical-grid plot count or native PID105 readback differs.",
    )
    layer.rescale("z")
    _require(
        bool(
            layer.obj.LT_execute(
                f"layer.cmap.zmin={zmin:.17g};layer.cmap.zmax={zmax:.17g};"
                "layer.cmap.numColors=101;layer.cmap.numMinorLevels=0;"
                "layer.cmap.linkpal=0;layer.cmap.stretchpal=1;"
                "layer.cmap.flippal=0;layer.cmap.SetLevels();"
                "layer.cmap.updateScale();doc -uw;"
            )
        ),
        "Origin rejected the frozen physical-grid color range.",
    )
    color_state = _apply_ramp(op, layer, colors)
    expected_scale = {"numColors": 101, "numMinorLevels": 0, "linkpal": 0, "stretchpal": 1, "flippal": 0}
    actual_scale = {name: float(layer.get_float(f"cmap.{name}")) for name in expected_scale}
    _require(
        color_state["zmin"] == zmin and color_state["zmax"] == zmax and actual_scale == expected_scale,
        "Origin physical-grid color range or level configuration failed exact readback.",
    )
    color_state.update(num_colors=101, level_state=actual_scale)
    for name, endpoints in limits.items():
        layer.axis(name).set_limits(*endpoints)
        # Proven numeric-label property; no worksheet/category binding is made.
        layer.set_int(f"{name}.label.type", 1)
        actual = tuple(float(layer.get_float(f"{name}.{prop}")) for prop in ("from", "to"))
        _require(actual == endpoints, f"Origin {name.upper()} physical axis limits failed exact readback.")
        _require(layer.get_int(f"{name}.label.type") == 1, "Origin retained a nonnumeric axis label type.")
    # Check again after native plot/scale updates, not only immediately after import.
    _require(np.array_equal(matrix.to_np(), values), "Origin plotting changed a source matrix cell.")
    _require(tuple(map(float, matrix.xymap)) == grid.xymap, "Origin plotting changed physical xymap.")
    return {
        "matrix": {
            "range": matrix.lt_range(),
            "xymap": list(actual_mapping),
            "cell_edges": list(edges),
            "x": list(grid.x),
            "y": list(grid.y),
            "values": actual_values.tolist(),
            "source_rows": [list(row) for row in grid.source_rows],
            "rows": values.shape[0],
            "columns": values.shape[1],
            "value_label": value_label,
            "source_values_exact": True,
            "physical_coordinates_exact": True,
        },
        "axes": {
            "x_range": list(limits["x"]),
            "y_range": list(limits["y"]),
            "axis_display_reversed": {name: ends[0] > ends[1] for name, ends in limits.items()},
            "reversed_relative_to_source": {
                name: (limits[name][1] - limits[name][0]) * (coordinates[-1] - coordinates[0]) < 0
                for name, coordinates in (("x", grid.x), ("y", grid.y))
            },
            "explicit_display_limits": {"x": x_range is not None, "y": y_range is not None},
        },
        "color_map": color_state,
        "plot_range": plot.lt_range(),
        "plot_type": 105,
        "editable_plot_count": 1,
        "styling_status": "caller_font_title_geometry_verification_required",
    }


def position_grid_colorbar(
    op: Any,
    graph: Any,
    layer: Any,
    *,
    region: Any,
    font_family: str,
    label_size_pt: float,
) -> dict[str, Any]:
    """Position an existing Spectrum1 in caller-reserved percent-of-page space.

    This keeps numeric color labels and hides only the automatic title; the
    caller may add its own verified editable value/unit title. Detachment from
    other panels is the caller's layout responsibility. No z levels are changed.
    """
    expected = {
        name: float(getattr(region, name))
        for name in ("left_percent", "top_percent", "width_percent", "height_percent")
    }
    _require(
        all(map(math.isfinite, expected.values()))
        and expected["left_percent"] >= 0
        and expected["top_percent"] >= 0
        and expected["width_percent"] > 0
        and expected["height_percent"] > 0
        and expected["left_percent"] + expected["width_percent"] <= 100
        and expected["top_percent"] + expected["height_percent"] <= 100,
        "The colorbar region must lie inside the page.",
    )
    _require(
        isinstance(font_family, str)
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", font_family) is not None
        and math.isfinite(label_size_pt)
        and label_size_pt > 0,
        "The colorbar needs a safe font family and finite positive label size.",
    )
    graph.activate()
    layer.activate()
    _require(layer.label("Spectrum1") is not None, "The physical-grid Spectrum1 object is missing.")
    _require(
        bool(
            layer.obj.LT_execute(
                "spectrum1.title=0;spectrum1.show=1;spectrum1.attach=0;"
                "spectrum1.labels.autodisp=0;spectrum1.labels.show=1;"
                f"spectrum1.labels.fsize={label_size_pt:.17g};spectrum1.labels.bold=0;"
                f"spectrum1.labels.font=font({font_family});"
                f"spectrum1.left=page.width*{expected['left_percent'] / 100:.17g};"
                f"spectrum1.top=page.height*{expected['top_percent'] / 100:.17g};"
                f"spectrum1.width=page.width*{expected['width_percent'] / 100:.17g};"
                f"spectrum1.height=page.height*{expected['height_percent'] / 100:.17g};"
                "spectrum1.barthick=100;doc -uw;"
            )
        ),
        "Origin rejected physical-grid colorbar styling.",
    )
    page_width, page_height = float(op.lt_float("page.width")), float(op.lt_float("page.height"))
    _require(
        all(math.isfinite(value) and value > 0 for value in (page_width, page_height)),
        "Origin colorbar page geometry is unavailable.",
    )
    geometry = {
        f"{name}_percent": float(op.lt_float(f"spectrum1.{name}")) / dimension * 100
        for name, dimension in (
            ("left", page_width),
            ("top", page_height),
            ("width", page_width),
            ("height", page_height),
        )
    }
    _require(
        all(
            math.isfinite(geometry[key]) and abs(geometry[key] - value) <= LAYER_GEOMETRY_TOLERANCE_PERCENT
            for key, value in expected.items()
        ),
        "Origin physical-grid colorbar geometry differs from the frozen region.",
    )
    font_code = float(op.lt_float(f"font({font_family})"))
    expected_style = {
        "title": 0,
        "show": 1,
        "attach": 0,
        "labels.autodisp": 0,
        "labels.show": 1,
        "labels.fsize": label_size_pt,
        "labels.bold": 0,
        "labels.font": font_code,
        "barthick": 100,
    }
    actual_style = {name: float(op.lt_float(f"spectrum1.{name}")) for name in expected_style}
    _require(
        math.isfinite(font_code) and font_code > 0 and actual_style == expected_style,
        "Origin physical-grid colorbar font or visibility failed exact readback.",
    )
    return {
        "geometry": geometry,
        "label_size_pt": actual_style["labels.fsize"],
        "label_font_code": actual_style["labels.font"],
        "font_code_expected": font_code,
        "object_state": actual_style,
    }
