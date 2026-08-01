from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.workers import progress_protocol as proto  # noqa: E402


def test_message_adds_elapsed_seconds_from_monotonic_worker_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proto, "_WORKER_STARTED_MONOTONIC", 100.0)
    monkeypatch.setattr(proto.time, "monotonic", lambda: 101.23456)

    payload = proto.message("progress", step="connect")

    assert payload == {
        "type": "progress",
        "elapsed_seconds": 1.235,
        "step": "connect",
    }


def test_message_preserves_explicit_elapsed_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proto, "_WORKER_STARTED_MONOTONIC", 100.0)
    monkeypatch.setattr(proto.time, "monotonic", lambda: 999.0)

    payload = proto.message("done", elapsed_seconds=4.321)

    assert payload["elapsed_seconds"] == 4.321


def test_all_protocol_helpers_emit_elapsed_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[dict[str, Any]] = []
    monotonic_values = iter((100.0014, 100.0125, 100.1236, 101.9999))
    monkeypatch.setattr(proto, "_WORKER_STARTED_MONOTONIC", 100.0)
    monkeypatch.setattr(proto.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(proto, "emit", emitted.append)

    proto.progress("connect", "running", "Connecting")
    proto.warning("slow", "Still running")
    proto.error("failed", "Could not connect")
    proto.done(ok=True)

    assert [item["elapsed_seconds"] for item in emitted] == [
        0.001,
        0.013,
        0.124,
        2.0,
    ]


def test_emit_truncates_an_individual_text_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = io.StringIO()
    monkeypatch.setattr(proto.sys, "stdout", stdout)

    proto.emit(
        {
            "type": "warning",
            "message": "数" * (proto.MAX_FIELD_CHARS + 500),
        }
    )

    raw = stdout.getvalue()
    decoded = json.loads(raw)
    assert len(raw.encode("utf-8")) <= proto.MAX_JSONL_BYTES
    assert decoded["message"].endswith("[truncated]")
    assert len(decoded["message"]) == proto.MAX_FIELD_CHARS


def test_emit_caps_a_pathological_nested_jsonl_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = io.StringIO()
    monkeypatch.setattr(proto.sys, "stdout", stdout)
    huge_readback = {
        f"object_{index:03d}": {
            "label": "测" * 4_000,
            "points": list(range(500)),
        }
        for index in range(200)
    }

    proto.done(
        output_dir="sample-output",
        selected_template_id="circular_network",
        verification_summary={"origin_plot_state": huge_readback},
    )

    raw = stdout.getvalue()
    decoded = json.loads(raw)
    assert raw.endswith("\n")
    assert len(raw.encode("utf-8")) <= proto.MAX_JSONL_BYTES
    assert decoded["type"] == "done"
    assert decoded["output_dir"] == "sample-output"
    assert decoded["selected_template_id"] == "circular_network"
    assert decoded["payload_truncated"] is True
