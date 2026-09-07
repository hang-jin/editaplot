"""Editable PID215/PID201 and native nested PID225 doughnut composition."""

from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np

from ..shap_dashboard import DASHBOARD_LAYOUT_VERSION, dashboard_regions
from ..shap_layout import ShapCompositeRegion, resolve_shap_mean_axis
from .safe_errors import OriginDrawError


def _require(value, message):
    if not value:
        raise OriginDrawError(message, code="shap_dashboard_readback_failed")


def _doughnut_theme(op, plot, hole, radius):
    """Theme paths discovered and independently read back on isolated PID225."""
    theme = plot.obj.GetTheme()
    theme.Geometry.Angle.SetDoubleValue(90)
    theme.Geometry.Thickness.SetDoubleValue(0)
    theme.Geometry.Donut.SetIntValue(1)
    theme.Geometry.DonutHoleAuto.SetIntValue(0)
    theme.Geometry.DoughnutHole.SetDoubleValue(hole)
    theme.Geometry.Rescale.SetDoubleValue(radius)
    theme.Geometry.Azimuth.SetDoubleValue(90)
    theme.Geometry.CCW.SetIntValue(0)
    for key in ("Values", "Percentages", "Categories", "Custom"):
        getattr(theme.Labels, key).SetIntValue(0)
    plot.obj.PutTheme(theme)
    plot.set_cmd(f"-c {op.ocolor('#FFFFFF')}", "-w 400")
    op.lt_exec("doc -uw;")
    applied = plot.obj.GetTheme()
    expected = {
        "Angle": 90,
        "Thickness": 0,
        "Donut": 1,
        "DonutHoleAuto": 0,
        "DoughnutHole": hole,
        "Rescale": radius,
        "Azimuth": 90,
        "CCW": 0,
    }
    actual = {key: float(getattr(applied.Geometry, key).GetDoubleValue()) for key in expected}
    _require(
        all(math.isfinite(actual[k]) and abs(actual[k] - v) < 0.01 for k, v in expected.items()),
        "Origin doughnut geometry differs from the frozen contract.",
    )
    labels = {
        key: int(getattr(applied.Labels, key).GetIntValue())
        for key in ("Values", "Percentages", "Categories", "Custom")
    }
    _require(not any(labels.values()), "Origin doughnut retains automatic wedge labels.")
    return {"geometry": actual, "labels": labels}


def _apply_ramp(op, layer, colors):
    codes = [int(op.ocolor(color)) for color in colors]
    commands = ["layer.cmap.linkpal=0;"]
    commands.extend(f"layer.cmap.color{i}={c};" for i, c in enumerate(codes, 1))
    commands.append("layer.cmap.updateScale();doc -uw;")
    _require(layer.obj.LT_execute("".join(commands)), "Origin rejected the dashboard color levels.")
    actual = [float(op.lt_float(f"layer.cmap.color{i}")) for i in range(1, len(codes) + 1)]
    _require(actual == codes, "Origin dashboard color-level readback differs.")
    return {
        "expected_hex": list(colors),
        "origin_codes": actual,
        "zmin": float(op.lt_float("layer.cmap.zmin")),
        "zmax": float(op.lt_float("layer.cmap.zmax")),
    }


def _apply_pie_colors(op, layer, plot, sheet, colors):
    codes = [int(op.ocolor(color)) for color in colors]
    index = sheet.cols
    sheet.from_list(index, codes, lname="DashboardRingColor", axis="N")
    color_range = f"{sheet.lt_range(False)}!col({index + 1})"
    _require(
        layer.obj.LT_execute(
            f"range p29pie={plot.lt_range()};range p29col={color_range};"
            "set p29pie -cue 1;set p29pie -cuf p29col;"
            "dataset p29actual;get p29pie -cuf p29actual;doc -uw;"
        ),
        "Origin rejected the dashboard ring color binding.",
    )
    actual = [float(op.lt_float(f"p29actual[{i}]")) for i in range(1, len(codes) + 1)]
    _require(actual == codes, "Origin ring colors differ from feature-group colors.")
    return actual


def build_shap_dashboard_graph(op, frame, preparation):
    # Reuse the validated native primitive builders and verification helpers;
    # the established SHAP template remains unchanged for ordinary users.
    from . import evidence_renderer as ev

    spec = preparation.plot_spec
    plan = spec.shap_plan
    dashboard = spec.shap_dashboard
    _require(
        dashboard is not None and dashboard.layout_version == DASHBOARD_LAYOUT_VERSION,
        "The frozen SHAP dashboard layout is missing or obsolete.",
    )
    graph, _base_state = ev._build_shap_summary_graph(op, frame, preparation)
    graph.name = "SHAPDashboard"
    style = spec.display_plan.figure_style
    regions = dashboard_regions(dashboard)
    inset_layout = dashboard.contribution_layout == "inset"
    title_y = 94 if inset_layout else 67
    bar, scatter, outer = graph[0], graph[1], graph[2]
    scatter.set_int("link", 0)
    _require(scatter.get_int("link") == 0, "Origin could not detach the overlay geometry link.")
    # Reacquire the source-bound helper sheet from the actual plot range.
    sheet = None
    # Source-sheet long names are unique in this owned project.
    for book in op.pages("w"):
        for candidate in book:
            if "__SHAP_X" in tuple(map(str, candidate.to_df().columns)):
                sheet = candidate
                break
        if sheet is not None:
            break
    _require(sheet is not None, "Origin lost the SHAP helper worksheet.")
    helper = sheet.to_df()
    _require(
        np.array_equal(
            helper["__SHAP_X"].dropna().to_numpy(dtype=float), frame[spec.x_column].to_numpy(dtype=float)
        ),
        "SHAP source X changed.",
    )
    text_state = {}

    def page_label(layer, name, text, x, y, size=15, color="#26363E", bold=False, align="center"):
        label, state = ev._add_shap_page_label(
            op,
            graph,
            layer,
            name=name,
            text=text,
            center_x_percent=x,
            center_y_percent=y,
            size_pt=size,
            font_family=style.font_family,
            bold=bold,
            color=color,
        )
        if align != "center":
            page_width = float(op.lt_float("page.width"))
            width = float(label.get_float("width"))
            left = page_width * x / 100.0 - (width if align == "right" else 0)
            label.set_float("left", left)
            op.lt_exec("doc -uw;")
            actual_left = float(label.get_float("left"))
            _require(
                actual_left >= 0 and actual_left + width <= page_width,
                "Dashboard text extends outside the page.",
            )
            state[f"{name}.left"] = actual_left
        text_state.update(state)
        return label

    # Bar is native exchange-XY: X indexes features and Y is the numeric mean.
    ev._remove_label(bar, "SHAPMeanTitle")
    bar_geometry = ev._shap_layer_region_readback(op, graph, bar, preparation, regions["importance"])
    bar.axis("x").set_limits(0.5, len(plan.feature_order) + 0.5, 1)
    _, mean_to, step = resolve_shap_mean_axis(max(v for _, v in plan.mean_abs_values) * 1.18)
    bar.axis("y").set_limits(0, mean_to, step)
    for key, value in (
        ("y.showLabels", 1),
        ("y.showlabel", 1),
        ("y.label.show", 1),
        ("y.ticks", 5),
        ("y2.showlabel", 0),
        ("y2.label.show", 0),
        ("y2.ticks", 0),
    ):
        bar.set_int(key, value)
    ev._apply_axis_label_font(op, bar, ("y",), style)
    bar.set_float("plot1.transparency", 8)
    bar.set_int("x.showAxes", 1)
    bar.set_int("y.showAxes", 1)
    feature_colors = dict(dashboard.feature_colors)
    commands = [f"range p29bar={bar.plot_list()[0].lt_range()};"]
    expected_colors = [int(op.ocolor(feature_colors[f])) for f in reversed(plan.feature_order)]
    for row, code in enumerate(expected_colors, 1):
        commands.extend((f"set p29bar {row} -pfb {code};", f"get p29bar {row} -pfb p29b{row};"))
    _require(bar.obj.LT_execute("".join(commands) + "doc -uw;"), "Origin bar colors failed.")
    actual_colors = [float(op.lt_float(f"p29b{i}")) for i in range(1, len(expected_colors) + 1)]
    _require(actual_colors == expected_colors, "Origin bar color readback differs.")
    _require(int(bar.get_int("y.showLabels")) == 1, "Importance numeric axis is not on the bottom.")
    means, percent = dict(plan.mean_abs_values), dict(dashboard.feature_percentages)
    n = len(plan.feature_order)
    area = regions["importance"]
    for i, f in enumerate(plan.feature_order):
        y = area.top_percent + area.height_percent * (i + 0.5) / n
        page_label(bar, f"FeatureName{i + 1}", f, area.left_percent - 0.8, y, size=15, align="right")
        x = area.left_percent + means[f] / mean_to * area.width_percent + 0.6
        page_label(bar, f"FeatureShare{i + 1}", f"{percent[f]:.2f}%", x, y - 0.65, size=12, align="left")
        page_label(bar, f"FeatureMean{i + 1}", f"({means[f]:.3g})", x, y + 0.65, size=12, align="left")
    page_label(bar, "DashboardMeanTitle", "Mean |SHAP value|", 32.5, title_y, size=18, bold=True)
    bar_binding = ev._read_shap_plot_binding(
        op, bar, f"[{graph.name}]1!1", sheet, "__MeanAbsFeature", "__MeanAbsValue", prefix="m"
    )

    # Re-style the scatter after moving it, then install the frozen 101-color
    # map. No reference pixels or externally loaded palette files are needed.
    for name in (
        "SHAPZero",
        "SHAPZeroText",
        "x_title",
        "SHAPColorbarTitle",
        "SHAPColorbarHigh",
        "SHAPColorbarLow",
    ):
        ev._remove_label(scatter, name)
    scatter_geometry, scatter_state, scatter_text, _old_cmap = ev._style_shap_scatter_layer(
        op, graph, 2, scatter, sheet, preparation, regions["beeswarm"]
    )
    scatter.set_int("y.showLabels", 0)
    scatter.set_int("y.ticks", 0)
    scatter.set_int("x.showAxes", 1)
    scatter.set_int("y.showAxes", 0)
    ev._remove_label(scatter, "xb")
    ev._remove_label(scatter, "yl")
    # Existing title helper names are canonical and explicitly removed before
    # replacing the text at the final dashboard position.
    for name in scatter_text.get("title_objects", []):
        ev._remove_label(scatter, name)
    page_label(scatter, "DashboardShapTitle", spec.x_title, 75, title_y, size=17, bold=False)
    scatter.activate()
    ramp_state = _apply_ramp(op, scatter, dashboard.palette_colors)
    colorbar_geometry, spectrum_state = ev._position_shap_spectrum(
        op, graph, scatter, preparation, regions["colorbar"]
    )
    text_state.update(spectrum_state)
    _require(int(scatter.get_int("y.showLabels")) == 0, "Duplicate bee feature labels survived.")
    axis_state = ev._axis_state(scatter)
    scatter_state["axis"] = axis_state
    scatter_state["color_mapping"] = {
        "dataset": "__FeatureValueNormalized",
        "edge_mode": _old_cmap["edge_mode"],
        "fill_mode": _old_cmap["fill_mode"],
        "edge_dataset_readback": _old_cmap["edge_dataset_readback"],
        "fill_dataset_readback": _old_cmap["fill_dataset_readback"],
        "embedded_color_levels": ramp_state,
    }

    # Reuse the existing group pie as an outer native donut; a separate native
    # PID225 layer carries the inner feature wedges on the same physical frame.
    for name in (
        "SHAPGroupTitle",
        *[f"SHAPGroupKey{i}" for i in range(1, 6)],
        *[f"SHAPGroupLabel{i}" for i in range(1, 6)],
    ):
        ev._remove_label(outer, name)
    ring_region = regions["rings"]
    size_cm = min(
        ring_region.width_percent * style.page_width_cm / 100,
        ring_region.height_percent * style.page_height_cm / 100,
    )
    ring_region = ShapCompositeRegion(
        "rings",
        ring_region.left_percent,
        ring_region.top_percent,
        size_cm / style.page_width_cm * 100,
        size_cm / style.page_height_cm * 100,
    )
    group_values = [v for _, v in dashboard.ring_group_percentages]
    sheet.from_list(sheet.lt_col_index("__GroupContribution") - 1, group_values, lname="__GroupContribution")
    outer_geometry = ev._shap_layer_region_readback(op, graph, outer, preparation, ring_region)
    outer_plot = outer.plot_list()[0]
    outer_theme = _doughnut_theme(op, outer_plot, 70, 95)
    outer_colors = _apply_pie_colors(op, outer, outer_plot, sheet, [c for _, c in dashboard.group_colors])
    ring_sheet = op.new_sheet("w", "Dashboard Feature Ring")
    ring_sheet.from_list(0, list(dashboard.ring_feature_order), lname="RingFeature", axis="X")
    ring_sheet.from_list(1, [percent[f] for f in dashboard.ring_feature_order], lname="RingValue", axis="Y")
    graph.activate()
    inner = graph.add_layer(0)
    inner_plot = inner.add_plot(f"{ring_sheet.lt_range(False)}!(A,B)", type=225)
    _require(inner_plot is not None, "Origin could not build the inner feature donut.")
    inner.rescale()
    inner_geometry = ev._shap_layer_region_readback(op, graph, inner, preparation, ring_region)
    inner_theme = _doughnut_theme(op, inner_plot, 58, 65)
    inner_colors = _apply_pie_colors(
        op, inner, inner_plot, ring_sheet, [feature_colors[f] for f in dashboard.ring_feature_order]
    )
    for layer in (outer, inner):
        ev._remove_shap_template_labels(layer, keep_axis_titles=False)
        for axis in ("x", "y"):
            layer.set_int(f"{axis}.showAxes", 0)
            layer.set_int(f"{axis}.showLabels", 0)
            layer.set_int(f"{axis}.ticks", 0)
    center_x = ring_region.left_percent + ring_region.width_percent / 2
    center_y = ring_region.top_percent + ring_region.height_percent / 2
    page_label(inner, "RingCenter1", "Feature", center_x, center_y - 0.8, size=12)
    page_label(inner, "RingCenter2", "contribution", center_x, center_y + 0.8, size=12)
    if not inset_layout:
        page_label(inner, "RingGuide", "Outer: groups    Inner: features", center_x, 72, size=13)
    legend_x, legend_y = (35, 67) if inset_layout else (60, 77)
    page_label(
        inner, "GroupGuide", "Feature groups", legend_x, legend_y - 1.5, size=14, bold=True, align="left"
    )
    for i, ((group, value), (_, color)) in enumerate(
        zip(dashboard.ring_group_percentages, dashboard.group_colors, strict=True), 1
    ):
        page_label(
            inner,
            f"DashboardGroup{i}",
            f"{group}   {value:.2f}%",
            legend_x,
            legend_y + i * 3.5,
            color=color,
            size=15,
            align="left",
        )
    outer_binding = ev._read_shap_plot_binding(
        op, outer, f"[{graph.name}]3!1", sheet, "__GroupLabel", "__GroupContribution", prefix="g"
    )
    inner_binding = ev._read_shap_plot_binding(
        op, inner, f"[{graph.name}]4!1", ring_sheet, "RingFeature", "RingValue", prefix="f"
    )
    _require(len(graph) == 4, "Dashboard must retain four native plot layers.")
    final_helper = sheet.to_df()
    _require(
        np.array_equal(
            final_helper["__SHAP_X"].dropna().to_numpy(dtype=float),
            frame[spec.x_column].to_numpy(dtype=float),
        ),
        "Dashboard altered source SHAP X values during composition.",
    )
    _require(
        np.allclose(
            final_helper["__MeanAbsValue"].dropna().to_numpy(dtype=float),
            [v for _, v in reversed(plan.mean_abs_values)],
            rtol=1e-12,
            atol=1e-12,
        ),
        "Dashboard importance values changed.",
    )
    _require(
        np.allclose(
            ring_sheet.to_df()["RingValue"].dropna().to_numpy(dtype=float),
            [percent[f] for f in dashboard.ring_feature_order],
            rtol=1e-12,
            atol=1e-12,
        ),
        "Dashboard inner-ring proportions changed.",
    )
    _require(
        all(abs(bar_geometry[k] - scatter_geometry[k]) <= 0.05 for k in ("top_percent", "height_percent")),
        "Dashboard feature rows are not aligned across panels.",
    )
    _require(
        all(
            int(layer.get_int("plot.pid")) == pid
            for layer, pid in zip(graph, (215, 201, 225, 225), strict=True)
        ),
        "Dashboard native plot types changed.",
    )
    return graph, {
        "width_cm": float(graph.obj.GetWidth()) * 2.54,
        "height_cm": float(graph.obj.GetHeight()) * 2.54,
        **scatter_geometry,
        "origin_axis_state": axis_state,
        "origin_text_state": {**text_state, "font_family_expected": style.font_family},
        "origin_helper_columns": list(map(str, sheet.to_df().columns)),
        "origin_dashboard_readback": {
            "plan": asdict(dashboard),
            "source_x_unchanged": True,
            "native_plot_types": [215, 201, 225, 225],
            "feature_rows_aligned": True,
            "source_observation_count": len(frame),
            "regions": {
                "importance": bar_geometry,
                "beeswarm": scatter_geometry,
                "colorbar": colorbar_geometry,
                "outer_ring": outer_geometry,
                "inner_ring": inner_geometry,
            },
            "importance": {"binding": bar_binding, "colors": actual_colors, "value_axis_to": mean_to},
            "beeswarm": scatter_state,
            "color_map": ramp_state,
            "outer_ring": {"theme": outer_theme, "binding": outer_binding, "colors": outer_colors},
            "inner_ring": {"theme": inner_theme, "binding": inner_binding, "colors": inner_colors},
        },
    }
