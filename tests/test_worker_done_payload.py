from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.workers import run_template_worker as worker  # noqa: E402
from origin_sciplot.workers.run_template_worker import (  # noqa: E402
    _compact_plot_spec_payload,
    _compact_runner_result,
    _load_template_manifest,
    _run_data_analysis,
    _run_origin_draw_export_verify,
)


def test_done_payload_keeps_artifacts_but_not_full_origin_readback(
    tmp_path: Path,
) -> None:
    report = tmp_path / "origin_verify_report.json"
    result = {
        "opju": str(tmp_path / "result.opju"),
        "png": str(tmp_path / "result.png"),
        "pdf": str(tmp_path / "result.pdf"),
        "tif": str(tmp_path / "result.tif"),
        "verify": {
            "template_id": "circular_network",
            "width_cm": 42.4,
            "height_cm": 20.5,
            "source_data_modified": False,
            "exports": {"png": True, "pdf": True, "tif": True},
            "origin_plot_state": {"large": ["object"] * 200},
        },
    }
    compatibility = {
        "origin_version": {
            "product_label": "2024b",
            "numeric": 10.15,
        }
    }

    payload = _compact_runner_result(
        result,
        SimpleNamespace(origin_verify_report=report),
        compatibility,
    )

    assert payload["opju"].endswith("result.opju")
    assert payload["origin_version"] == "2024b"
    assert payload["origin_verify_report"] == str(report)
    assert "verify" not in payload
    assert "origin_plot_state" not in payload["verification_summary"]
    assert payload["verification_summary"] == {
        "template_id": "circular_network",
        "page_width_cm": 42.4,
        "page_height_cm": 20.5,
        "source_data_modified": False,
        "exports": {"png": True, "pdf": True, "tif": True},
        "full_readback": str(report),
    }


@pytest.mark.parametrize("plot_kind", ["bar", "heatmap", "violin"])
def test_scientific_plot_spec_terminal_payload_is_a_bounded_summary(
    tmp_path: Path,
    plot_kind: str,
) -> None:
    report = tmp_path / f"{plot_kind}_analysis_report.json"
    series = tuple(
        SimpleNamespace(
            label=f"Series {index} " + ("X" * 500),
            series_role="data",
        )
        for index in range(80)
    )
    analysis = SimpleNamespace(
        template_id=plot_kind,
        plot_spec=SimpleNamespace(
            plot_kind=plot_kind,
            plot_mode="comparison",
            x_title="Time " + ("X" * 500),
            y_title="Response",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            series=series,
            network_layout=None,
            display_plan={"large": list(range(5_000))},
            axis_plan={"large": list(range(5_000))},
        ),
    )

    payload = _compact_plot_spec_payload(analysis, report)

    assert payload["plot_kind"] == plot_kind
    assert payload["series"]["count"] == 80
    assert payload["series"]["truncated"] is True
    assert len(payload["series"]["labels"]) < 80
    assert len(payload["x_title"]) <= worker.MAX_SUMMARY_TEXT_CHARS
    assert payload["full_plot_spec"] == str(report)
    assert "display_plan" not in payload
    assert "axis_plan" not in payload


def test_network_plot_spec_summary_preserves_bounded_geometry_evidence(
    tmp_path: Path,
) -> None:
    report = tmp_path / "circular_network_analysis_report.json"
    layout = SimpleNamespace(
        panel_order=("2000-2010", "2010-2020"),
        node_order=tuple(f"Node {index}" for index in range(40)),
        panels=(
            SimpleNamespace(panel="2000-2010", edges=tuple(range(7))),
            SimpleNamespace(panel="2010-2020", edges=tuple(range(9))),
        ),
        weight_scale=SimpleNamespace(to_dict=lambda: {"minimum": 0.1, "maximum": 0.9}),
        sample_count=24,
        node_radius=1.0,
    )
    analysis = SimpleNamespace(
        template_id="circular_network",
        plot_spec=SimpleNamespace(
            plot_kind="circular_network",
            plot_mode="directed_weighted",
            x_title="",
            y_title="",
            y2_title=None,
            x_scale="linear",
            y_scale="linear",
            series=(),
            network_layout=layout,
        ),
    )

    payload = _compact_plot_spec_payload(analysis, report)
    network = payload["network_layout"]

    assert network["panel_order"] == ["2000-2010", "2010-2020"]
    assert network["panel_count"] == 2
    assert network["node_count"] == 40
    assert network["node_order_truncated"] is True
    assert network["edge_counts"] == {"2000-2010": 7, "2010-2020": 9}
    assert network["total_edge_count"] == 16
    assert network["weight_scale"] == {"minimum": 0.1, "maximum": 0.9}
    assert network["sample_count"] == 24
    assert network["node_radius"] == 1.0
    assert network["full_geometry_report"] == str(report)


def test_analysis_progress_wraps_only_the_observed_analysis_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str, str] | str] = []
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, text: events.append((step, status, text)),
    )

    result = _run_data_analysis(
        lambda: events.append("analysis") or {"ok": True},
        success_text="数据分析完成",
    )

    assert result == {"ok": True}
    assert events == [
        ("analyze_data", "running", "正在分析数据与绘图语义"),
        "analysis",
        ("analyze_data", "success", "数据分析完成"),
    ]


def test_manifest_stage_contains_only_the_registry_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str] | str] = []
    manifest = SimpleNamespace(name="Bar")

    class FakeRegistry:
        def get(self, template_id: str) -> SimpleNamespace:
            assert template_id == "bar"
            events.append("registry")
            return manifest

    monkeypatch.setattr(worker, "TemplateRegistry", FakeRegistry)
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, _text: events.append((step, status)),
    )

    assert _load_template_manifest("bar") is manifest
    assert events == [
        ("load_template", "running"),
        "registry",
        ("load_template", "success"),
    ]


def test_analysis_failure_does_not_emit_false_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, _text: events.append((step, status)),
    )

    with pytest.raises(RuntimeError, match="analysis failed"):
        _run_data_analysis(
            lambda: (_ for _ in ()).throw(RuntimeError("analysis failed")),
            success_text="数据分析完成",
        )

    assert events == [("analyze_data", "running")]


def test_runner_and_verification_emit_only_observable_combined_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str] | str] = []
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, _text: events.append((step, status)),
    )
    monkeypatch.setattr(worker, "require_interactive_origin_context", lambda: None)

    result, compatibility = _run_origin_draw_export_verify(
        lambda: events.append("runner") or {"png": "result.png"},
        lambda payload: events.append("verify") or {"status": "verified"},
    )

    assert result == {"png": "result.png"}
    assert compatibility == {"status": "verified"}
    assert events == [
        ("launch_origin_draw_export_verify", "running"),
        "runner",
        ("launch_origin_draw_export_verify", "success"),
        ("verify_outputs", "running"),
        "verify",
        ("verify_outputs", "success"),
    ]


def test_origin_queue_wraps_runner_and_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    @contextmanager
    def fake_slot(**kwargs: object) -> Iterator[SimpleNamespace]:
        assert kwargs["job_kind"] == "render"
        events.append("queue-enter")
        try:
            yield SimpleNamespace(waited=False)
        finally:
            events.append("queue-exit")

    monkeypatch.setattr(worker, "origin_job_slot", fake_slot)
    monkeypatch.setattr(worker, "require_interactive_origin_context", lambda: None)
    monkeypatch.setattr(worker.proto, "progress", lambda *_args: None)

    _run_origin_draw_export_verify(
        lambda: events.append("runner") or {"png": "result.png"},
        lambda _payload: events.append("verify") or {"status": "verified"},
    )

    assert events == ["queue-enter", "runner", "verify", "queue-exit"]


def test_verification_failure_does_not_emit_false_verify_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, _text: events.append((step, status)),
    )
    monkeypatch.setattr(worker, "require_interactive_origin_context", lambda: None)

    with pytest.raises(RuntimeError, match="readback invalid"):
        _run_origin_draw_export_verify(
            lambda: {"png": "result.png"},
            lambda _payload: (_ for _ in ()).throw(RuntimeError("readback invalid")),
        )

    assert events == [
        ("launch_origin_draw_export_verify", "running"),
        ("launch_origin_draw_export_verify", "success"),
        ("verify_outputs", "running"),
    ]


def test_origin_queue_wait_progress_is_concise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        worker.proto,
        "progress",
        lambda step, status, text: events.append((step, status, text)),
    )

    worker._report_origin_queue_wait(31.8)

    assert events == [
        (
            "origin_job_queue",
            "waiting",
            "正在等待另一项 Origin 任务结束；已等待 31 秒。",
        )
    ]
