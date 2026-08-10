from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.template_capabilities import (  # noqa: E402
    ALL_ORIGIN_CAPABILITIES,
    TEMPLATE_CAPABILITY_PROFILES,
    CapabilityProbeResult,
    OriginCapability,
    evaluate_template_compatibility,
    get_template_capability_profile,
    resolve_activated_optional_capabilities,
)


def _public_implemented_manifest_ids() -> set[str]:
    template_root = Path(__file__).resolve().parents[1] / "runtime" / "templates"
    result: set[str] = set()
    for path in template_root.glob("*/manifest.yaml"):
        manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
        if manifest.get("status") == "implemented" and manifest.get("visibility") == "public":
            result.add(str(manifest["id"]))
    return result


def test_every_public_implemented_manifest_has_exactly_one_profile() -> None:
    assert set(TEMPLATE_CAPABILITY_PROFILES) == _public_implemented_manifest_ids()
    assert all(
        template_id == profile.template_id
        for template_id, profile in TEMPLATE_CAPABILITY_PROFILES.items()
    )


def test_missing_open_gl_blocks_only_the_3d_templates() -> None:
    without_3d = ALL_ORIGIN_CAPABILITIES - {OriginCapability.OPEN_GL_3D}

    scatter = evaluate_template_compatibility("scatter", 10.15, without_3d)
    trajectory = evaluate_template_compatibility("trajectory3d", 10.15, without_3d)
    ridgeline = evaluate_template_compatibility("density_ridgeline3d", 10.15, without_3d)

    assert scatter.status == "verified"
    assert scatter.missing_required == ()
    assert trajectory.status == "blocked"
    assert trajectory.missing_required == (OriginCapability.OPEN_GL_3D,)
    assert ridgeline.status == "blocked"
    assert ridgeline.missing_required == (OriginCapability.OPEN_GL_3D,)


@pytest.mark.parametrize(
    ("template_id", "special_capability"),
    [
        ("xps", OriginCapability.XPS_FILL_TWO_COLOR),
        ("heatmap", OriginCapability.MATRIX_HEATMAP),
        ("confusion_matrix", OriginCapability.MATRIX_HEATMAP),
        ("sankey", OriginCapability.SANKEY),
        ("trajectory3d", OriginCapability.OPEN_GL_3D),
        ("density_ridgeline3d", OriginCapability.OPEN_GL_3D),
    ],
)
def test_special_templates_are_blocked_without_their_required_capability(
    template_id: str,
    special_capability: OriginCapability,
) -> None:
    decision = evaluate_template_compatibility(
        template_id,
        10.15,
        ALL_ORIGIN_CAPABILITIES - {special_capability},
    )

    assert decision.status == "blocked"
    assert special_capability in decision.missing_required
    assert decision.block_reason == "missing_required_capabilities"


def test_optional_data_dependent_capability_does_not_block_basic_mode() -> None:
    profile = get_template_capability_profile("uv_vis")
    assert OriginCapability.INSET_LAYER in profile.optional

    decision = evaluate_template_compatibility(
        "uv_vis",
        10.15,
        ALL_ORIGIN_CAPABILITIES - {OriginCapability.INSET_LAYER},
    )
    assert decision.status == "verified"

    inset_decision = evaluate_template_compatibility(
        "uv_vis",
        10.15,
        ALL_ORIGIN_CAPABILITIES - {OriginCapability.INSET_LAYER},
        activated_optional={OriginCapability.INSET_LAYER},
    )
    assert inset_decision.status == "blocked"
    assert inset_decision.missing_required == (OriginCapability.INSET_LAYER,)
    assert inset_decision.activated_optional == frozenset(
        {OriginCapability.INSET_LAYER}
    )


@pytest.mark.parametrize(
    ("shap_profile", "expected"),
    [
        (
            "beeswarm_only",
            frozenset({OriginCapability.DATASET_COLOR_SCALE}),
        ),
        (
            "beeswarm_mean_abs",
            frozenset(
                {
                    OriginCapability.DATASET_COLOR_SCALE,
                    OriginCapability.HORIZONTAL_BAR_LAYER,
                    OriginCapability.MULTI_LAYER_PAGE,
                }
            ),
        ),
        (
            "beeswarm_mean_abs_grouped",
            frozenset(
                {
                    OriginCapability.DATASET_COLOR_SCALE,
                    OriginCapability.HORIZONTAL_BAR_LAYER,
                    OriginCapability.MULTI_LAYER_PAGE,
                    OriginCapability.PIE,
                    OriginCapability.PIE_IN_MULTI_LAYER_PAGE,
                }
            ),
        ),
    ],
)
def test_shap_profile_resolver_activates_exact_origin_primitives(
    shap_profile: str,
    expected: frozenset[OriginCapability],
) -> None:
    plot_spec = SimpleNamespace(
        shap_plan=SimpleNamespace(profile=shap_profile),
        plot_mode=shap_profile,
        series=(),
        inset_series=(),
        x_scale="linear",
        y_scale="linear",
    )

    assert resolve_activated_optional_capabilities("shap_summary", plot_spec) == expected
    assert expected.issubset(get_template_capability_profile("shap_summary").optional)


def test_shap_template_declares_only_the_five_profile_dependent_capabilities() -> None:
    assert get_template_capability_profile("shap_summary").optional == frozenset(
        {
            OriginCapability.DATASET_COLOR_SCALE,
            OriginCapability.HORIZONTAL_BAR_LAYER,
            OriginCapability.MULTI_LAYER_PAGE,
            OriginCapability.PIE,
            OriginCapability.PIE_IN_MULTI_LAYER_PAGE,
        }
    )


def test_shared_resolver_preserves_existing_non_shap_optional_routes() -> None:
    error_spec = SimpleNamespace(
        aggregate_error_column="SD",
        series=(),
        inset_series=(),
        x_scale="linear",
        y_scale="linear",
    )
    inset_spec = SimpleNamespace(
        aggregate_error_column=None,
        series=(),
        inset_series=(object(),),
        x_scale="linear",
        y_scale="linear",
    )
    log_spec = SimpleNamespace(
        aggregate_error_column=None,
        series=(),
        inset_series=(),
        x_scale="linear",
        y_scale="log10",
    )

    assert resolve_activated_optional_capabilities("bar", error_spec) == frozenset(
        {OriginCapability.ERROR_BARS}
    )
    assert resolve_activated_optional_capabilities("uv_vis", inset_spec) == frozenset(
        {OriginCapability.INSET_LAYER}
    )
    assert resolve_activated_optional_capabilities("pl", log_spec) == frozenset(
        {OriginCapability.LOG_AXIS}
    )


def test_non_optional_capability_cannot_be_promoted_silently() -> None:
    with pytest.raises(ValueError, match="not optional"):
        evaluate_template_compatibility(
            "scatter",
            10.15,
            ALL_ORIGIN_CAPABILITIES,
            activated_optional={OriginCapability.OPEN_GL_3D},
        )


def test_error_bar_and_statistical_routes_are_classified() -> None:
    assert OriginCapability.ERROR_BARS in get_template_capability_profile("line_error").required
    assert OriginCapability.ERROR_BARS in get_template_capability_profile("bar").optional
    assert (
        OriginCapability.STATISTICAL_PLOT
        in get_template_capability_profile("grouped_box").required
    )
    assert OriginCapability.STATISTICAL_PLOT in get_template_capability_profile("violin").required


@pytest.mark.parametrize(
    "missing_capability",
    [
        OriginCapability.GRAPH_OBJECT_ARROW,
        OriginCapability.MULTI_LAYER_PAGE,
    ],
)
def test_circular_network_requires_editable_arrows_and_multi_layer_page(
    missing_capability: OriginCapability,
) -> None:
    profile = get_template_capability_profile("circular_network")
    assert {
        OriginCapability.GRAPH_OBJECT_ARROW,
        OriginCapability.MULTI_LAYER_PAGE,
    }.issubset(profile.required)

    decision = evaluate_template_compatibility(
        "circular_network",
        10.15,
        ALL_ORIGIN_CAPABILITIES - {missing_capability},
    )

    assert decision.status == "blocked"
    assert decision.missing_required == (missing_capability,)
    assert decision.block_reason == "missing_required_capabilities"


def test_profile_probe_and_decision_are_json_serializable() -> None:
    probe = CapabilityProbeResult(
        available_capabilities=ALL_ORIGIN_CAPABILITIES,
        unavailable_capabilities=frozenset(),
    )
    decision = evaluate_template_compatibility("scatter", "10.15", probe)

    payload = {
        "profile": get_template_capability_profile("scatter").to_dict(),
        "probe": probe.to_dict(),
        "decision": decision.to_dict(),
    }
    encoded = json.dumps(payload, sort_keys=True)

    assert '"status": "verified"' in encoded
    assert payload["decision"]["origin_version"]["product_label"] == "2024b"


def test_incomplete_probe_keeps_unprobed_special_route_experimental() -> None:
    core_only = get_template_capability_profile("scatter").required
    probe = CapabilityProbeResult(
        available_capabilities=core_only,
        unavailable_capabilities=frozenset(),
        probe_complete=False,
    )

    scatter = evaluate_template_compatibility("scatter", 10.25, probe)
    trajectory = evaluate_template_compatibility("trajectory3d", 10.25, probe)
    ridgeline = evaluate_template_compatibility("density_ridgeline3d", 10.25, probe)

    assert scatter.status == "compatible_unverified"
    assert scatter.unprobed_required == ()
    assert trajectory.status == "experimental"
    assert trajectory.missing_required == ()
    assert trajectory.unprobed_required == (OriginCapability.OPEN_GL_3D,)
    assert ridgeline.status == "experimental"
    assert ridgeline.missing_required == ()
    assert ridgeline.unprobed_required == (OriginCapability.OPEN_GL_3D,)


def test_basic_smoke_does_not_overclaim_unprobed_xps_fill() -> None:
    core_only = get_template_capability_profile("scatter").required
    probe = CapabilityProbeResult(
        available_capabilities=core_only,
        unavailable_capabilities=frozenset(),
        probe_complete=False,
    )

    xps = evaluate_template_compatibility("xps", 10.15, probe)

    assert xps.status == "experimental"
    assert xps.missing_required == ()
    assert xps.unprobed_required == (OriginCapability.XPS_FILL_TWO_COLOR,)


def test_probe_rejects_contradictory_capability_state() -> None:
    with pytest.raises(ValueError, match="both available and unavailable"):
        CapabilityProbeResult(
            available_capabilities=frozenset({OriginCapability.CORE_2D}),
            unavailable_capabilities=frozenset({OriginCapability.CORE_2D}),
            probe_complete=False,
        )


@pytest.mark.parametrize(
    ("origin_version", "expected_status"),
    [
        (9.79, "blocked"),
        (9.80, "compatible_unverified"),
        (10.10, "compatible_unverified"),
        (10.15, "verified"),
        (10.25, "compatible_unverified"),
        (10.40, "compatible_unverified"),
    ],
)
def test_version_status_is_applied_after_capability_check(
    origin_version: float,
    expected_status: str,
) -> None:
    decision = evaluate_template_compatibility(
        "scatter",
        origin_version,
        ALL_ORIGIN_CAPABILITIES,
    )

    assert decision.status == expected_status


def test_unsupported_version_is_blocked_even_when_all_capabilities_are_available() -> None:
    decision = evaluate_template_compatibility(
        "scatter",
        9.7,
        ALL_ORIGIN_CAPABILITIES,
    )

    assert decision.status == "blocked"
    assert decision.missing_required == ()
    assert decision.block_reason == "origin_version_unsupported"


def test_unknown_template_raises_a_clear_error() -> None:
    with pytest.raises(KeyError, match="Unknown public template capability profile"):
        evaluate_template_compatibility("not-a-template", 10.15, ALL_ORIGIN_CAPABILITIES)


def test_unknown_capability_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown Origin capability"):
        evaluate_template_compatibility("scatter", 10.15, ["core_2d", "not-a-capability"])
