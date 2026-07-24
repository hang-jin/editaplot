from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.workers.run_template_worker import (  # noqa: E402
    _record_template_compatibility,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "skill" / "editaplot" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from editaplot_core import build_plan, understand_data  # noqa: E402


def _semantic_confirmation(source: Path, template_id: str, runtime: Path) -> dict[str, object]:
    result = understand_data(
        source,
        template_id=template_id,
        engine_home=runtime,
    )
    assert result["confirmation_gate"]["can_confirm_now"] is True
    return result["confirmation_gate"]["confirmation_payload_template"]


@pytest.mark.parametrize(
    ("origin_version", "expected_status"),
    [("10.15", "verified"), ("10.25", "compatible_unverified")],
)
def test_successful_render_records_version_aware_template_decision(
    tmp_path: Path,
    origin_version: str,
    expected_status: str,
) -> None:
    environment_report = tmp_path / "environment_report.json"
    origin_verify_report = tmp_path / "origin_verify_report.json"
    environment_report.write_text(
        json.dumps({"origin_version": origin_version}),
        encoding="utf-8",
    )
    origin_verify_report.write_text(
        json.dumps({"origin_axis_state": {"x": {}, "y": {}}}),
        encoding="utf-8",
    )
    output = SimpleNamespace(
        environment_report=environment_report,
        origin_verify_report=origin_verify_report,
    )

    decision = _record_template_compatibility(
        output,
        SimpleNamespace(id="scatter"),
        None,
    )

    assert decision["status"] == expected_status
    stored_environment = json.loads(environment_report.read_text(encoding="utf-8"))
    stored_verify = json.loads(origin_verify_report.read_text(encoding="utf-8"))
    assert stored_environment["template_compatibility"] == decision
    assert stored_verify["template_compatibility"] == decision


def test_successful_optional_inset_route_is_recorded(tmp_path: Path) -> None:
    environment_report = tmp_path / "environment_report.json"
    origin_verify_report = tmp_path / "origin_verify_report.json"
    environment_report.write_text('{"origin_version":"10.15"}', encoding="utf-8")
    origin_verify_report.write_text("{}", encoding="utf-8")
    output = SimpleNamespace(
        environment_report=environment_report,
        origin_verify_report=origin_verify_report,
    )
    analysis = SimpleNamespace(
        plot_spec=SimpleNamespace(
            series=(),
            inset_series=(object(),),
            x_scale="linear",
            y_scale="linear",
        )
    )

    decision = _record_template_compatibility(
        output,
        SimpleNamespace(id="uv_vis"),
        analysis,
    )

    assert decision["status"] == "verified"
    assert decision["activated_optional"] == ["inset_layer"]


def test_successful_aggregate_error_route_is_recorded(tmp_path: Path) -> None:
    environment_report = tmp_path / "environment_report.json"
    origin_verify_report = tmp_path / "origin_verify_report.json"
    environment_report.write_text('{"origin_version":"10.15"}', encoding="utf-8")
    origin_verify_report.write_text("{}", encoding="utf-8")
    output = SimpleNamespace(
        environment_report=environment_report,
        origin_verify_report=origin_verify_report,
    )
    analysis = SimpleNamespace(
        plot_spec=SimpleNamespace(
            series=(),
            aggregate_error_column="Total_SD",
            inset_series=(),
            x_scale="linear",
            y_scale="linear",
        )
    )

    decision = _record_template_compatibility(
        output,
        SimpleNamespace(id="stacked_bar"),
        analysis,
    )

    assert decision["status"] == "verified"
    assert decision["activated_optional"] == ["error_bars"]
    assert "error_bars" in decision["available_capabilities"]


def test_successful_xps_render_records_required_fill_evidence(tmp_path: Path) -> None:
    environment_report = tmp_path / "environment_report.json"
    origin_verify_report = tmp_path / "origin_verify_report.json"
    environment_report.write_text('{"origin_version":"10.15"}', encoding="utf-8")
    origin_verify_report.write_text("{}", encoding="utf-8")
    output = SimpleNamespace(
        environment_report=environment_report,
        origin_verify_report=origin_verify_report,
    )

    decision = _record_template_compatibility(
        output,
        SimpleNamespace(id="xps"),
        None,
    )

    assert decision["status"] == "verified"
    assert "xps_fill_two_color" in decision["available_capabilities"]
    assert decision["evidence_source"] == "successful_template_render"
    assert decision["global_capability_probe"] is False


def test_render_plan_freezes_data_dependent_optional_capabilities() -> None:
    runtime = Path(__file__).resolve().parents[1] / "runtime"

    bar_plan = build_plan(
        runtime / "templates" / "bar" / "example_standard.csv",
        template_id="bar",
        claim="The teaching groups differ.",
        evidence_role="comparison",
        semantic_confirmation=_semantic_confirmation(
            runtime / "templates" / "bar" / "example_standard.csv",
            "bar",
            runtime,
        ),
        engine_home=runtime,
    )
    uv_plan = build_plan(
        runtime / "templates" / "uv_vis" / "example_standard.csv",
        template_id="uv_vis",
        claim="The supplied spectrum and Tauc inset summarize the teaching sample.",
        evidence_role="mechanism",
        semantic_confirmation=_semantic_confirmation(
            runtime / "templates" / "uv_vis" / "example_standard.csv",
            "uv_vis",
            runtime,
        ),
        engine_home=runtime,
    )
    stacked_plan = build_plan(
        runtime / "templates" / "stacked_bar" / "example_standard.csv",
        template_id="stacked_bar",
        claim="The teaching composition totals differ.",
        evidence_role="comparison",
        semantic_confirmation=_semantic_confirmation(
            runtime / "templates" / "stacked_bar" / "example_standard.csv",
            "stacked_bar",
            runtime,
        ),
        engine_home=runtime,
    )

    assert bar_plan["template"]["activated_optional_capabilities"] == ["error_bars"]
    assert uv_plan["template"]["activated_optional_capabilities"] == ["inset_layer"]
    assert stacked_plan["template"]["activated_optional_capabilities"] == ["error_bars"]
