from __future__ import annotations

import csv
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from matplotlib.patches import Wedge

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import evidence_renderer  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.origin_backend.template_capabilities import (  # noqa: E402
    ALL_ORIGIN_CAPABILITIES,
    OriginCapability,
    evaluate_template_compatibility,
    get_template_capability_profile,
)
from origin_sciplot.origin_backend.verify_utils import verify_symbol_style  # noqa: E402
from origin_sciplot.scientific_preview import (  # noqa: E402
    ScientificPreviewError,
    _build_scientific_preview_figure,
)
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    prepare_scientific,
)
from origin_sciplot.shap_layout import (  # noqa: E402
    SHAP_ZERO_LINE_COLOR,
    resolve_shap_composite_geometry,
    resolve_shap_mean_axis,
)
from origin_sciplot.workers.run_template_worker import (  # noqa: E402
    _activated_optional_capabilities,
)

PROFILE_AXES = {
    "beeswarm_only": {
        "shap_beeswarm",
        "shap_feature_value_colorbar",
    },
    "beeswarm_mean_abs": {
        "shap_beeswarm",
        "shap_mean_abs",
        "shap_feature_value_colorbar",
    },
    "beeswarm_mean_abs_grouped": {
        "shap_beeswarm",
        "shap_mean_abs",
        "shap_feature_value_colorbar",
        "shap_group_contribution",
    },
}


@pytest.mark.parametrize("layer_index", (1, 2, 3))
def test_shap_explicit_plot_range_uses_verified_numeric_layer_notation(
    layer_index: int,
) -> None:
    graph = SimpleNamespace(name="SHAPComposite")

    assert evidence_renderer._shap_explicit_plot_range(graph, layer_index) == (
        f"[SHAPComposite]{layer_index}!1"
    )


def test_shap_binding_accepts_equivalent_origin_range_spellings() -> None:
    assert evidence_renderer._shap_binding_identity_matches(
        {
            "actual_range": '[Book3]Sheet1!A"__SHAP_X"',
            "expected_range": "[Book3]1!col(1)",
            "actual_dataset": "Book3_A",
            "expected_dataset": "Book3_A",
            "actual_count": 48,
            "expected_count": 48,
        }
    )


class _SymbolProbeLayer:
    def __init__(self, *, fail_option: str | None = None) -> None:
        self.fail_option = fail_option
        self.commands: list[str] = []

    def LT_execute(self, command: str) -> int:
        self.commands.append(command)
        if self.fail_option is not None and f" {self.fail_option} " in command:
            return 0
        return 1


class _SymbolProbePlot:
    def __init__(self, layer: _SymbolProbeLayer) -> None:
        self.layer = layer

    @staticmethod
    def lt_range() -> str:
        return "[SHAPComposite]2!1"


def test_symbol_verifier_reads_kind_and_interior_from_origin_commands() -> None:
    layer = _SymbolProbeLayer()
    plot = _SymbolProbePlot(layer)
    origin = SimpleNamespace(
        lt_float=lambda name: {
            "__osc_symbol_size": 6.8,
            "__osc_symbol_edge": 20.0,
            "__osc_symbol_kind": 2.0,
            "__osc_symbol_interior": 0.0,
        }[name]
    )

    state = verify_symbol_style(
        origin,
        plot,
        expected_size_pt=6.8,
        expected_edge_percent=20.0,
        expected_symbol_kind=2,
        expected_symbol_interior=0,
    )

    assert state["symbol_kind"] == pytest.approx(2.0)
    assert state["symbol_interior"] == pytest.approx(0.0)
    assert any("get rr -k __osc_symbol_kind" in command for command in layer.commands)
    assert any("get rr -kf __osc_symbol_interior" in command for command in layer.commands)


@pytest.mark.parametrize("fail_option", ("-k", "-kf"))
def test_symbol_verifier_fails_closed_when_origin_option_read_fails(
    fail_option: str,
) -> None:
    layer = _SymbolProbeLayer(fail_option=fail_option)
    plot = _SymbolProbePlot(layer)
    origin = SimpleNamespace(
        lt_float=lambda name: {
            "__osc_symbol_size": 6.8,
            "__osc_symbol_edge": 20.0,
            "__osc_symbol_kind": 2.0,
            "__osc_symbol_interior": 0.0,
        }[name]
    )

    with pytest.raises(RuntimeError, match="Origin plot verification command failed"):
        verify_symbol_style(
            origin,
            plot,
            expected_size_pt=6.8,
            expected_edge_percent=20.0,
            expected_symbol_kind=2,
            expected_symbol_interior=0,
        )


def test_shap_binding_rejects_a_different_origin_dataset() -> None:
    assert not evidence_renderer._shap_binding_identity_matches(
        {
            "actual_range": '[Book3]Sheet1!A"__SHAP_X"',
            "expected_range": "[Book3]1!col(1)",
            "actual_dataset": "Book3_B",
            "expected_dataset": "Book3_A",
            "actual_count": 48,
            "expected_count": 48,
        }
    )


def _rows() -> list[dict[str, object]]:
    definitions = (
        ("Age", 1, "Clinical", 4.0, (-6.0, 2.0, 4.0)),
        ("Texture", 2, "Imaging", 2.0, (-3.0, 1.0, 2.0)),
        ("Shape", 3, "Imaging", 1.0, (-1.0, 0.0, 2.0)),
    )
    rows: list[dict[str, object]] = []
    for feature, order, group, mean_abs, shap_values in definitions:
        contribution = (4.0 if group == "Clinical" else 3.0) / 7.0 * 100.0
        for sample_index, shap_value in enumerate(shap_values, start=1):
            rows.append(
                {
                    "Feature": feature,
                    "SHAP value": shap_value,
                    "Feature value": sample_index / 3.0,
                    "Sample ID": f"S{sample_index:02d}",
                    "Feature Order": order,
                    "Mean absolute SHAP": mean_abs,
                    "Feature Group": group,
                    "Group contribution (%)": contribution,
                }
            )
    return rows


def _source(tmp_path: Path) -> Path:
    rows = _rows()
    path = tmp_path / "shap_composite.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _prepare(source: Path, profile: str):
    columns = list(_rows()[0])
    roles = {
        "Feature": "feature",
        "SHAP value": "shap",
        "Feature value": "feature_value",
        "Sample ID": "sample_id",
        "Feature Order": "feature_order",
        "Mean absolute SHAP": "mean_abs_shap",
        "Feature Group": "feature_group",
        "Group contribution (%)": "group_contribution",
    }
    mapping = ScientificColumnMapping(
        assignments=tuple((column, roles[column]) for column in columns),
        plot_mode=profile,
    )
    return prepare_scientific(source, "shap_summary", column_mapping=mapping)


def _axes_by_role(figure) -> dict[str, object]:
    return {axis.get_label(): axis for axis in figure.axes if axis.get_label()}


def _renderer_seam(name: str):
    seam = getattr(evidence_renderer, name, None)
    assert callable(seam), f"SHAP renderer must expose the pure {name} seam"
    return seam


def _geometry_payload(profile: str) -> dict[str, object]:
    geometry = _renderer_seam("resolve_shap_composite_geometry")(profile)
    payload = geometry.to_dict() if hasattr(geometry, "to_dict") else geometry
    assert isinstance(payload, dict)
    return payload


def _binding_contract(
    x_helper: str,
    y_helper: str,
    *,
    count: int,
    layer_index: int,
) -> dict[str, object]:
    def component(helper: str, designation: str) -> dict[str, object]:
        return {
            "helper_column": helper,
            "helper_column_index": 1 if designation == "x" else 2,
            "actual_range": f'[Book3]Sheet1!{designation.upper()}"{helper}"',
            "expected_range": f"[Book3]1!col({1 if designation == 'x' else 2})",
            "actual_dataset": f"Book3_{designation.upper()}",
            "expected_dataset": f"Book3_{designation.upper()}",
            "actual_count": count,
            "expected_count": count,
        }

    return {
        "plot_range": f"[SHAPComposite]{layer_index}!1",
        "x": component(x_helper, "x"),
        "y": component(y_helper, "y"),
    }


def _template_cleanup_contract() -> dict[str, object]:
    return {
        "requested": ["Legend", "legend", "xb", "yl", "yr"],
        "remaining": [],
        "verified": True,
    }


@pytest.mark.parametrize("profile", tuple(PROFILE_AXES))
def test_preview_exposes_only_the_axes_required_by_each_profile(
    tmp_path: Path,
    profile: str,
) -> None:
    preparation = _prepare(_source(tmp_path), profile)

    figure = _build_scientific_preview_figure(preparation)
    roles = set(_axes_by_role(figure))

    assert roles == PROFILE_AXES[profile]


@pytest.mark.parametrize("profile", tuple(PROFILE_AXES))
def test_preview_preserves_source_csv_and_exact_supplied_shap_x_values(
    tmp_path: Path,
    profile: str,
) -> None:
    source = _source(tmp_path)
    before = source.read_bytes()
    supplied_x = pd.read_csv(source)["SHAP value"].to_numpy(dtype=float)
    preparation = _prepare(source, profile)

    figure = _build_scientific_preview_figure(preparation)

    assert source.read_bytes() == before
    beeswarm = _axes_by_role(figure)["shap_beeswarm"]
    displayed_x = np.concatenate(
        [
            np.asarray(collection.get_offsets(), dtype=float)[:, 0]
            for collection in beeswarm.collections
            if np.asarray(collection.get_offsets()).shape[0] > 0
        ]
    )
    assert np.sort(displayed_x) == pytest.approx(np.sort(supplied_x))


def test_preview_uses_a_real_detached_feature_value_colorbar(tmp_path: Path) -> None:
    preparation = _prepare(_source(tmp_path), "beeswarm_mean_abs")

    figure = _build_scientific_preview_figure(preparation)
    axes = _axes_by_role(figure)
    beeswarm = axes["shap_beeswarm"]
    colorbar = axes["shap_feature_value_colorbar"]

    assert "Feature value" in colorbar.get_ylabel()
    assert colorbar.collections
    assert colorbar.get_position().x0 > beeswarm.get_position().x1
    assert not {
        "Low feature value",
        "High feature value",
    }.intersection(text.get_text() for text in beeswarm.texts)


@pytest.mark.parametrize(
    "profile",
    ["beeswarm_mean_abs", "beeswarm_mean_abs_grouped"],
)
def test_mean_abs_panel_is_horizontal_source_bound_and_uses_a_top_axis(
    tmp_path: Path,
    profile: str,
) -> None:
    preparation = _prepare(_source(tmp_path), profile)
    expected = dict(preparation.plot_spec.shap_plan.mean_abs_values)

    figure = _build_scientific_preview_figure(preparation)
    mean_axis = _axes_by_role(figure)["shap_mean_abs"]
    widths = [float(patch.get_width()) for patch in mean_axis.patches]

    assert len(widths) == len(expected)
    assert sorted(widths) == pytest.approx(sorted(expected.values()))
    assert mean_axis.xaxis.get_label_position() == "top"
    assert "Mean |SHAP" in mean_axis.get_xlabel()
    beeswarm = _axes_by_role(figure)["shap_beeswarm"]
    assert mean_axis.get_position().bounds == pytest.approx(
        beeswarm.get_position().bounds,
        abs=1e-6,
    )


def test_grouped_preview_inset_uses_frozen_group_contribution_values(
    tmp_path: Path,
) -> None:
    preparation = _prepare(_source(tmp_path), "beeswarm_mean_abs_grouped")
    expected = dict(preparation.plot_spec.shap_plan.group_contributions)

    figure = _build_scientific_preview_figure(preparation)
    inset = _axes_by_role(figure)["shap_group_contribution"]
    wedges = [patch for patch in inset.patches if isinstance(patch, Wedge)]
    fractions = [(float(wedge.theta2) - float(wedge.theta1)) / 360.0 * 100.0 for wedge in wedges]

    assert len(wedges) == len(expected)
    assert sorted(fractions) == pytest.approx(sorted(expected.values()), abs=0.05)
    inset_text = " ".join(text.get_text() for text in inset.texts)
    assert all(group in inset_text for group in expected)
    assert inset.get_aspect() == pytest.approx(1.0)
    beeswarm = _axes_by_role(figure)["shap_beeswarm"].get_position()
    inset_box = inset.get_position()
    assert inset_box.x0 >= beeswarm.x0
    assert inset_box.y0 >= beeswarm.y0
    assert inset_box.x1 <= beeswarm.x1
    assert inset_box.y1 <= beeswarm.y1


def test_preview_rejects_a_frozen_plan_from_an_unknown_layout_contract(
    tmp_path: Path,
) -> None:
    preparation = _prepare(_source(tmp_path), "beeswarm_mean_abs")
    stale_plan = replace(
        preparation.plot_spec.shap_plan,
        layout_version="shap-composite-layout-stale",
    )
    stale_spec = replace(preparation.plot_spec, shap_plan=stale_plan)
    stale_preparation = replace(preparation, plot_spec=stale_spec)

    with pytest.raises(ScientificPreviewError) as captured:
        _build_scientific_preview_figure(stale_preparation)

    assert captured.value.code == "shap_composite_layout_version_mismatch"


@pytest.mark.parametrize("profile", tuple(PROFILE_AXES))
def test_origin_helper_data_preserves_source_x_and_adds_only_profile_helpers(
    tmp_path: Path,
    profile: str,
) -> None:
    source = _source(tmp_path)
    preparation = _prepare(source, profile)
    source_frame = pd.read_csv(source)
    before = source_frame.copy(deep=True)

    helper_frame, helper_columns = _renderer_seam("build_shap_composite_helper_frame")(
        source_frame, preparation
    )

    pd.testing.assert_frame_equal(source_frame, before)
    assert np.array_equal(
        helper_frame["__SHAP_X"].dropna().to_numpy(dtype=float),
        source_frame["SHAP value"].to_numpy(dtype=float),
    )
    required = {
        "__SHAP_X",
        "__SHAP_Y",
        "__FeatureValueNormalized",
        "__FeatureLabel",
    }
    if profile != "beeswarm_only":
        required.update({"__MeanAbsFeature", "__MeanAbsValue"})
    if profile == "beeswarm_mean_abs_grouped":
        required.update({"__GroupLabel", "__GroupContribution"})
    assert required.issubset(helper_frame.columns)
    assert required.issubset(helper_columns)

    plan = preparation.plot_spec.shap_plan
    if profile != "beeswarm_only":
        observed_mean = dict(
            zip(
                helper_frame["__MeanAbsFeature"].dropna(),
                helper_frame["__MeanAbsValue"].dropna(),
                strict=True,
            )
        )
        assert observed_mean == pytest.approx(dict(plan.mean_abs_values))
    if profile == "beeswarm_mean_abs_grouped":
        observed_groups = dict(
            zip(
                helper_frame["__GroupLabel"].dropna(),
                helper_frame["__GroupContribution"].dropna(),
                strict=True,
            )
        )
        assert observed_groups == pytest.approx(dict(plan.group_contributions))


def test_shap_capability_profile_and_route_activation_follow_selected_profile(
    tmp_path: Path,
) -> None:
    profile = get_template_capability_profile("shap_summary")
    assert {
        OriginCapability.DATASET_COLOR_SCALE,
        OriginCapability.HORIZONTAL_BAR_LAYER,
        OriginCapability.MULTI_LAYER_PAGE,
        OriginCapability.PIE,
        OriginCapability.PIE_IN_MULTI_LAYER_PAGE,
    }.issubset(profile.optional)

    source = _source(tmp_path)
    beeswarm = _prepare(source, "beeswarm_only")
    mean_abs = _prepare(source, "beeswarm_mean_abs")
    grouped = _prepare(source, "beeswarm_mean_abs_grouped")
    assert _activated_optional_capabilities("shap_summary", beeswarm) == frozenset(
        {OriginCapability.DATASET_COLOR_SCALE}
    )
    assert _activated_optional_capabilities("shap_summary", mean_abs) == frozenset(
        {
            OriginCapability.DATASET_COLOR_SCALE,
            OriginCapability.HORIZONTAL_BAR_LAYER,
            OriginCapability.MULTI_LAYER_PAGE,
        }
    )
    assert _activated_optional_capabilities("shap_summary", grouped) == frozenset(
        {
            OriginCapability.DATASET_COLOR_SCALE,
            OriginCapability.HORIZONTAL_BAR_LAYER,
            OriginCapability.MULTI_LAYER_PAGE,
            OriginCapability.PIE,
            OriginCapability.PIE_IN_MULTI_LAYER_PAGE,
        }
    )

    without_multilayer = ALL_ORIGIN_CAPABILITIES - {OriginCapability.MULTI_LAYER_PAGE}
    decision = evaluate_template_compatibility(
        "shap_summary",
        10.15,
        without_multilayer,
        activated_optional=_activated_optional_capabilities("shap_summary", mean_abs),
    )
    assert decision.status == "blocked"
    assert decision.missing_required == (OriginCapability.MULTI_LAYER_PAGE,)


@pytest.mark.parametrize("profile", tuple(PROFILE_AXES))
def test_origin_geometry_plan_is_profile_specific_and_physically_bounded(
    profile: str,
) -> None:
    payload = _geometry_payload(profile)

    assert payload["profile"] == profile
    assert float(payload["page_width_cm"]) > 0.0
    assert float(payload["page_height_cm"]) > 0.0
    regions = payload["regions"]
    assert isinstance(regions, dict)
    assert set(regions) == PROFILE_AXES[profile]
    for role, raw_box in regions.items():
        assert isinstance(raw_box, dict), role
        left = float(raw_box["left_percent"])
        top = float(raw_box["top_percent"])
        width = float(raw_box["width_percent"])
        height = float(raw_box["height_percent"])
        assert 0.0 <= left < 100.0
        assert 0.0 <= top < 100.0
        assert width > 0.0 and height > 0.0
        assert left + width <= 100.0 + 1e-9
        assert top + height <= 100.0 + 1e-9

    beeswarm = regions["shap_beeswarm"]
    colorbar = regions["shap_feature_value_colorbar"]
    beeswarm_right = float(beeswarm["left_percent"]) + float(beeswarm["width_percent"])
    assert float(colorbar["left_percent"]) >= beeswarm_right - 0.05
    if profile != "beeswarm_only":
        mean_abs = regions["shap_mean_abs"]
        for key in ("left_percent", "top_percent", "width_percent", "height_percent"):
            assert float(mean_abs[key]) == pytest.approx(float(beeswarm[key]), abs=0.05)
    if profile == "beeswarm_mean_abs_grouped":
        inset = regions["shap_group_contribution"]
        assert float(inset["left_percent"]) >= float(beeswarm["left_percent"])
        assert float(inset["top_percent"]) >= float(beeswarm["top_percent"])
        assert float(inset["left_percent"]) + float(inset["width_percent"]) <= (
            float(beeswarm["left_percent"]) + float(beeswarm["width_percent"]) + 0.05
        )
        assert float(inset["top_percent"]) + float(inset["height_percent"]) <= (
            float(beeswarm["top_percent"]) + float(beeswarm["height_percent"]) + 0.05
        )
        assert float(payload["page_width_cm"]) * float(inset["width_percent"]) / 100.0 <= (
            4.8 + 0.03
        )
        assert float(payload["page_height_cm"]) * float(inset["height_percent"]) / 100.0 <= (
            4.8 + 0.03
        )


def test_grouped_inset_hits_the_frozen_4_8_cm_cap_on_a_large_page() -> None:
    geometry = resolve_shap_composite_geometry(
        "beeswarm_mean_abs_grouped",
        SimpleNamespace(page_width_cm=40.0, page_height_cm=30.0),
    )
    inset = geometry.region("shap_group_contribution")

    assert geometry.page_width_cm * inset.width_percent / 100.0 == pytest.approx(
        4.8,
        abs=0.002,
    )
    assert geometry.page_height_cm * inset.height_percent / 100.0 == pytest.approx(
        4.8,
        abs=0.002,
    )


@pytest.mark.parametrize(
    ("maximum", "expected"),
    [
        (0.0, (0.0, 1.0, 0.2)),
        (0.36893, (0.0, 0.4, 0.1)),
        (0.99, (0.0, 1.25, 0.25)),
    ],
)
def test_mean_shap_axis_uses_readable_frozen_increments(
    maximum: float,
    expected: tuple[float, float, float],
) -> None:
    assert resolve_shap_mean_axis(maximum) == pytest.approx(expected)


def _valid_readback_contract(tmp_path: Path, profile: str):
    preparation = _prepare(_source(tmp_path), profile)
    plan = preparation.plot_spec.shap_plan
    assert plan is not None
    style = preparation.plot_spec.display_plan.figure_style
    assert style is not None
    geometry = resolve_shap_composite_geometry(profile, style)
    helper_columns = [
        "__SHAP_X",
        "__SHAP_Y",
        "__FeatureValueNormalized",
        "__FeatureLabel",
    ]
    plot_counts = {"shap_beeswarm": 1}
    state: dict[str, object] = {
        "profile": profile,
        "layout_version": plan.layout_version,
        "source_x_unchanged": True,
        "helper_columns": helper_columns,
        "regions": geometry.to_dict()["regions"],
        "plot_counts": plot_counts,
        "beeswarm": {
            "pid": 201,
            "reference": {
                "present": True,
                "text_present": False,
                "value": 0.0,
                "color": SHAP_ZERO_LINE_COLOR,
            },
            "symbol": {
                "symbol_size_pt": 6.8,
                "symbol_edge_percent_of_radius": 20.0,
                "symbol_kind": 2,
                "symbol_interior": 0,
            },
            "plot_binding": _binding_contract(
                "__SHAP_X",
                "__SHAP_Y",
                count=len(_rows()),
                layer_index=1 if profile == "beeswarm_only" else 2,
            ),
            "template_cleanup": _template_cleanup_contract(),
        },
        "colorbar": {
            "present": True,
            "dataset": "__FeatureValueNormalized",
            "associated_object": "Spectrum1",
            "edge_mode": 2,
            "fill_mode": 2,
            "edge_dataset": "__FeatureValueNormalized",
            "fill_dataset": "__FeatureValueNormalized",
            "minimum": 0.0,
            "maximum": 1.0,
            "direction": "low_blue_high_red",
            "spectrum_revorder": 1,
        },
        "mean_abs": {"present": False},
        "group_inset": {"present": False},
    }
    if profile != "beeswarm_only":
        helper_columns.extend(["__MeanAbsFeature", "__MeanAbsValue"])
        plot_counts["shap_mean_abs"] = 1
        mean_from, mean_to, mean_step = resolve_shap_mean_axis(
            max(float(value) for _feature, value in plan.mean_abs_values)
        )
        state["mean_abs"] = {
            "present": True,
            "pid": 215,
            "labels": [feature for feature, _value in plan.mean_abs_values],
            "values": [float(value) for _feature, value in plan.mean_abs_values],
            "source": plan.mean_abs_source,
            "label_dataset": "__MeanAbsFeature",
            "value_dataset": "__MeanAbsValue",
            "mean_axis_limits": [mean_from, mean_to],
            "mean_axis_step": mean_step,
            "plot_binding": _binding_contract(
                "__MeanAbsFeature",
                "__MeanAbsValue",
                count=len(plan.mean_abs_values),
                layer_index=1,
            ),
            "layer_link": {
                "parent_layer": 1,
                "expected_parent_layer": 1,
                "child_layer": 2,
                "expected_child_layer": 2,
                "parent_role": "shap_mean_abs",
                "child_role": "shap_beeswarm",
                "unit": 1,
                "expected_unit": 1,
                "requested_x_axis_link": 0,
                "requested_y_axis_link": 0,
                "verified": True,
                "final_parent_layer": 1,
                "final_unit": 1,
            },
            "title_collision": {
                "object": "SHAPMeanTitle",
                "bottom_percent": geometry.region("shap_mean_abs").top_percent - 4.0,
                "maximum_bottom_percent": geometry.region("shap_mean_abs").top_percent - 3.2,
                "verified": True,
            },
            "template_cleanup": _template_cleanup_contract(),
        }
    if profile == "beeswarm_mean_abs_grouped":
        helper_columns.extend(["__GroupLabel", "__GroupContribution", "__PieColor"])
        plot_counts["shap_group_contribution"] = 1
        state["group_inset"] = {
            "present": True,
            "pid": 225,
            "labels": [group for group, _value in plan.group_contributions],
            "values": [float(value) for _group, value in plan.group_contributions],
            "source": plan.group_contribution_source,
            "label_dataset": "__GroupLabel",
            "value_dataset": "__GroupContribution",
            "color_dataset": "__PieColor",
            "data_labels_enabled": 0,
            "label_theme": {
                "values": 0,
                "percentages": 0,
                "categories": 0,
                "custom": 0,
            },
            "legend_objects": [
                object_name
                for index in range(1, len(plan.group_contributions) + 1)
                for object_name in (f"SHAPGroupKey{index}", f"SHAPGroupLabel{index}")
            ],
            "plot_binding": _binding_contract(
                "__GroupLabel",
                "__GroupContribution",
                count=len(plan.group_contributions),
                layer_index=3,
            ),
            "template_cleanup": _template_cleanup_contract(),
        }
    return plan, geometry, state


@pytest.mark.parametrize("profile", tuple(PROFILE_AXES))
def test_origin_readback_validator_accepts_only_a_complete_profile_state(
    tmp_path: Path,
    profile: str,
) -> None:
    validator = _renderer_seam("validate_shap_composite_readback")
    plan, geometry, state = _valid_readback_contract(tmp_path, profile)

    validator(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("layout_version", "shap-composite-layout-stale"),
        ("source_x_unchanged", False),
        ("helper_columns", ["__SHAP_X", "__SHAP_Y"]),
        ("colorbar", {"present": False}),
        ("regions", {}),
    ],
)
def test_origin_readback_validator_fails_closed_on_missing_evidence(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    profile = "beeswarm_mean_abs_grouped"
    plan, geometry, state = _valid_readback_contract(tmp_path, profile)
    state[field] = replacement

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("symbol_size_pt", 0.0),
        ("symbol_edge_percent_of_radius", 35.0),
        ("symbol_kind", 1),
        ("symbol_interior", 2),
    ],
)
def test_origin_readback_validator_rejects_changed_beeswarm_symbol_contract(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_only")
    beeswarm = deepcopy(state["beeswarm"])
    beeswarm["symbol"][field] = replacement
    state["beeswarm"] = beeswarm

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_wrong_beeswarm_dataset_binding(
    tmp_path: Path,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_only")
    beeswarm = deepcopy(state["beeswarm"])
    beeswarm["plot_binding"]["x"]["actual_dataset"] = "Book3_WRONG"
    state["beeswarm"] = beeswarm

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("reference", "present", False),
        ("reference", "value", 1.0),
        ("template_cleanup", "verified", False),
        ("template_cleanup", "remaining", ["Legend"]),
    ],
)
def test_origin_readback_validator_rejects_incomplete_beeswarm_object_evidence(
    tmp_path: Path,
    section: str,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_only")
    beeswarm = deepcopy(state["beeswarm"])
    beeswarm[section][field] = replacement
    state["beeswarm"] = beeswarm

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("parent_layer", 2),
        ("child_layer", 1),
        ("unit", 0),
        ("final_parent_layer", 0),
        ("final_unit", 0),
        ("verified", False),
    ],
)
def test_origin_readback_validator_rejects_changed_mean_layer_link(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_mean_abs")
    mean_abs = deepcopy(state["mean_abs"])
    mean_abs["layer_link"][field] = replacement
    state["mean_abs"] = mean_abs

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_mean_title_tick_collision(
    tmp_path: Path,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_mean_abs")
    mean_abs = deepcopy(state["mean_abs"])
    mean_abs["title_collision"]["bottom_percent"] = (
        mean_abs["title_collision"]["maximum_bottom_percent"] + 0.5
    )
    state["mean_abs"] = mean_abs

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_missing_group_legend_object(
    tmp_path: Path,
) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    group_inset = deepcopy(state["group_inset"])
    group_inset["legend_objects"] = group_inset["legend_objects"][:-1]
    state["group_inset"] = group_inset

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    "role",
    [
        "shap_beeswarm",
        "shap_mean_abs",
        "shap_feature_value_colorbar",
        "shap_group_contribution",
    ],
)
@pytest.mark.parametrize(
    "field",
    ["left_percent", "top_percent", "width_percent", "height_percent"],
)
def test_origin_readback_validator_rejects_any_geometry_offset(
    tmp_path: Path,
    role: str,
    field: str,
) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    regions = deepcopy(state["regions"])
    regions[role][field] += 1.0
    state["regions"] = regions

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_an_extra_helper_column(tmp_path: Path) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    state["helper_columns"] = [*state["helper_columns"], "__UnexpectedHelper"]

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_an_extra_plot_role(tmp_path: Path) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    state["plot_counts"] = {**state["plot_counts"], "shap_unplanned_layer": 1}

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("labels", ["Wrong feature", "Texture", "Shape"]),
        ("values", [9.0, 2.0, 1.0]),
        ("source", "calculated"),
        ("label_dataset", "__WrongMeanLabel"),
        ("value_dataset", "__WrongMeanValue"),
        ("mean_axis_limits", [0.0, 0.333333]),
        ("mean_axis_step", 0.033333),
    ],
)
def test_origin_readback_validator_rejects_wrong_mean_summary_evidence(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_mean_abs")
    mean_abs = deepcopy(state["mean_abs"])
    mean_abs[field] = replacement
    state["mean_abs"] = mean_abs

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_reordered_mean_summary(tmp_path: Path) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_mean_abs")
    mean_abs = deepcopy(state["mean_abs"])
    mean_abs["labels"] = list(reversed(mean_abs["labels"]))
    mean_abs["values"] = list(reversed(mean_abs["values"]))
    state["mean_abs"] = mean_abs

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("labels", ["Wrong group", "Imaging"]),
        ("values", [50.0, 50.0]),
        ("source", "calculated"),
        ("label_dataset", "__WrongGroupLabel"),
        ("value_dataset", "__WrongGroupValue"),
        ("color_dataset", "__WrongPieColor"),
        ("data_labels_enabled", 1),
        ("label_theme", {"values": 0, "percentages": 1, "categories": 0, "custom": 0}),
    ],
)
def test_origin_readback_validator_rejects_wrong_group_summary_evidence(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    group_inset = deepcopy(state["group_inset"])
    group_inset[field] = replacement
    state["group_inset"] = group_inset

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


def test_origin_readback_validator_rejects_reordered_group_summary(tmp_path: Path) -> None:
    plan, geometry, state = _valid_readback_contract(
        tmp_path,
        "beeswarm_mean_abs_grouped",
    )
    group_inset = deepcopy(state["group_inset"])
    group_inset["labels"] = list(reversed(group_inset["labels"]))
    group_inset["values"] = list(reversed(group_inset["values"]))
    state["group_inset"] = group_inset

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("associated_object", "DetachedSpectrum"),
        ("dataset", "__WrongColorDataset"),
        ("edge_dataset", "__WrongColorDataset"),
        ("fill_dataset", "__WrongColorDataset"),
        ("edge_mode", 0),
        ("fill_mode", 0),
        ("minimum", -1.0),
        ("maximum", 2.0),
        ("direction", "low_red_high_blue"),
        ("spectrum_revorder", 0),
    ],
)
def test_origin_readback_validator_rejects_wrong_colorbar_evidence(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    plan, geometry, state = _valid_readback_contract(tmp_path, "beeswarm_mean_abs")
    colorbar = deepcopy(state["colorbar"])
    colorbar[field] = replacement
    state["colorbar"] = colorbar

    with pytest.raises(OriginDrawError):
        _renderer_seam("validate_shap_composite_readback")(plan, geometry, state)
