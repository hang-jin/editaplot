from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import session as session_module  # noqa: E402
from origin_sciplot.origin_backend.capabilities import (  # noqa: E402
    ConnectionMode,
    SessionOwnership,
    parse_origin_version,
)
from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginEnvironmentError,
)
from origin_sciplot.origin_backend.session import (  # noqa: E402
    OriginEnvironment,
    OriginSession,
)
from origin_sciplot.origin_backend.smoke_test import run_origin_smoke  # noqa: E402


def _install_fake_originpro(
    monkeypatch: pytest.MonkeyPatch,
    raw_version: object,
) -> list[object]:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_float=lambda name: events.append(("read", name)) or raw_version,
        new=lambda **kwargs: events.append(("new", kwargs)),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)
    monkeypatch.setattr(
        session_module.metadata,
        "version",
        lambda name: {"originpro": "1.1.15", "OriginExt": "1.2.5"}[name],
    )
    return events


def test_session_exposes_known_risks_without_blocking_instance_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _install_fake_originpro(monkeypatch, "10.2502122")

    with OriginSession(keep_open=False) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        payload = environment.to_dict()

    risks = {
        item["risk_id"]: item
        for item in payload["known_version_risks"]
    }
    assert payload["version_status"] == "recognized"
    assert payload["probe_priority"] == "high"
    assert payload["version_advisory_only"] is True
    assert payload["version_advisory_blocks_render"] is False
    assert risks["origin_2025b_secondary_y_title"]["build_match"] == (
        "known_affected"
    )
    assert risks["origin_2025b_secondary_y_title"]["blocks_render"] is False
    assert events == [
        ("show", False),
        ("read", "@V"),
        ("new", {"asksave": False}),
        "exit",
    ]


@pytest.mark.parametrize(
    ("raw_version", "expected_raw"),
    [
        ("not-a-version", None),
        ("10.40", 10.40),
    ],
)
def test_unfamiliar_but_readable_version_is_unknown_and_probe_driven(
    raw_version: object,
    expected_raw: float | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _install_fake_originpro(monkeypatch, raw_version)

    with OriginSession(keep_open=False) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        payload = environment.to_dict()

    assert payload["origin_version"] == "unknown"
    assert payload["origin_version_raw"] == expected_raw
    assert payload["origin_product"] == "unknown"
    assert payload["origin_compatibility_status"] == "unknown"
    assert payload["origin_supported_by_originpro"] is None
    assert payload["version_status"] == "unknown"
    assert payload["known_version_risks"] == []
    assert payload["probe_priority"] == "high"
    assert payload["requires_full_capability_probe"] is True
    assert ("new", {"asksave": False}) in events


class _FailAfterHandshakeOrigin:
    def path(self, _kind: str) -> str:
        raise RuntimeError("private local path and HRESULT")


class _FailAfterHandshakeSession:
    def __init__(self, environment: OriginEnvironment) -> None:
        self.environment = environment
        self.op = _FailAfterHandshakeOrigin()

    def __enter__(self) -> _FailAfterHandshakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def test_smoke_report_carries_advisory_without_turning_it_into_a_gate(
    tmp_path: Path,
) -> None:
    version = parse_origin_version("10.2502122")
    environment = OriginEnvironment(
        origin_version="10.25",
        originpro_version="1.1.15",
        originext_version="1.2.5",
        python_version="3.10.11",
        python_architecture_bits=64,
        connection_mode=ConnectionMode.NEW_ISOLATED,
        ownership=SessionOwnership.EDITAPLOT,
        origin_version_info=version,
    )
    calls: list[tuple[bool, ConnectionMode]] = []

    def session_factory(
        *,
        keep_open: bool,
        connection_mode: ConnectionMode,
    ) -> _FailAfterHandshakeSession:
        calls.append((keep_open, connection_mode))
        return _FailAfterHandshakeSession(environment)

    output_dir = tmp_path / "smoke"
    with pytest.raises(OriginEnvironmentError) as raised:
        run_origin_smoke(output_dir, session_factory=session_factory)

    assert raised.value.stage == "read_program_path"
    report = json.loads(
        (output_dir / "compatibility-report.json").read_text("utf-8")
    )
    advisory = report["version_advisory"]
    assert advisory["version_status"] == "recognized"
    assert advisory["probe_priority"] == "high"
    assert advisory["advisory_only"] is True
    assert advisory["blocks_render"] is False
    assert {
        item["risk_id"]
        for item in advisory["known_version_risks"]
    } >= {
        "origin_2025b_graph_defaults",
        "origin_2025b_secondary_y_title",
    }
    read_version = next(
        item
        for item in report["stages"]
        if item["name"] == "read_version"
    )
    assert read_version["status"] == "passed"
    assert read_version["probe_priority"] == "high"
    assert read_version["advisory_only"] is True
    assert read_version["blocks_render"] is False
    assert calls == [(False, ConnectionMode.NEW_ISOLATED)]
