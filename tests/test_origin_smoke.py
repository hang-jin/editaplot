from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import smoke_test as smoke_module  # noqa: E402
from origin_sciplot.origin_backend.capabilities import ConnectionMode  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginDrawError,
    OriginEnvironmentError,
    OriginExportError,
)
from origin_sciplot.origin_backend.smoke_test import (  # noqa: E402
    READY_COMMAND,
    SMOKE_STAGES,
    run_origin_smoke,
)

PRIVATE_ORIGIN_PATH = "\\".join(
    (f"{chr(67)}:", "Users", "Somebody", "Private Origin")
)
PRIVATE_DETAIL = f"{PRIVATE_ORIGIN_PATH} HRESULT 0x80004005"
EXPECTED_ARTIFACTS = {
    "result.opju",
    "result.png",
    "result.pdf",
    "result.tif",
    "environment_report.json",
    "origin_verify_report.json",
    "compatibility-report.json",
}


class FakeEnvironment:
    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_version": "10.15",
            "origin_version_raw": 10.150132,
            "origin_product": "2024b",
            "origin_compatibility_status": "verified",
            "originpro_version": "1.1.15",
            "originext_version": "1.2.5",
            "python_version": "3.10.11",
            "python_architecture_bits": 64,
            "connection_mode": "new_isolated",
            "session_ownership": "editaplot",
        }


class FakeAxis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    @property
    def limits(self) -> tuple[float, float, float]:
        if self.fail:
            raise RuntimeError(PRIVATE_DETAIL)
        return (0.0, 10.0, 2.0)

    @property
    def scale(self) -> int:
        return 1


class FakeLayer:
    def __init__(self, fail_stage: str | None, events: list[Any]) -> None:
        self.fail_stage = fail_stage
        self.events = events

    def add_plot(self, sheet: Any, y: str, x: str, *, type: str) -> object:
        del sheet
        self.events.append(("add_plot", y, x, type))
        return object()

    def rescale(self) -> None:
        self.events.append("rescale")

    def axis(self, name: str) -> FakeAxis:
        self.events.append(("axis", name))
        return FakeAxis(fail=self.fail_stage == "readback" and name == "x")


class FakeGraph:
    def __init__(self, fail_stage: str | None, events: list[Any]) -> None:
        self.layer = FakeLayer(fail_stage, events)

    def __getitem__(self, index: int) -> FakeLayer:
        assert index == 0
        return self.layer


class FakeSheet:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def from_list(
        self,
        column: int,
        data: list[float],
        *,
        lname: str,
        axis: str,
    ) -> None:
        self.events.append(("from_list", column, tuple(data), lname, axis))


class FakeBook:
    def __init__(self, events: list[Any]) -> None:
        self.sheet = FakeSheet(events)

    def __getitem__(self, index: int) -> FakeSheet:
        assert index == 0
        return self.sheet


class FakeOrigin:
    def __init__(self, fail_stage: str | None, events: list[Any]) -> None:
        self.fail_stage = fail_stage
        self.events = events

    def path(self, kind: str) -> str:
        self.events.append(("path", kind))
        if self.fail_stage == "read_program_path":
            raise RuntimeError(PRIVATE_DETAIL)
        return PRIVATE_ORIGIN_PATH

    def lt_exec(self, command: str) -> bool:
        self.events.append(("lt_exec", command))
        if self.fail_stage == "ready":
            raise RuntimeError(PRIVATE_DETAIL)
        return True

    def new_book(self, kind: str, name: str) -> FakeBook:
        self.events.append(("new_book", kind, name))
        if self.fail_stage == "create_book":
            raise RuntimeError(PRIVATE_DETAIL)
        return FakeBook(self.events)

    def new_graph(self, name: str, *, template: str) -> FakeGraph:
        self.events.append(("new_graph", name, template))
        if self.fail_stage == "create_graph":
            raise RuntimeError(PRIVATE_DETAIL)
        return FakeGraph(self.fail_stage, self.events)

    def save(self, path: str) -> bool:
        self.events.append(("save", Path(path).name))
        if self.fail_stage == "save_project":
            raise RuntimeError(PRIVATE_DETAIL)
        Path(path).write_bytes(b"editable-origin-project")
        return True


class FakeSessionContext:
    def __init__(
        self,
        *,
        keep_open: bool,
        connection_mode: ConnectionMode,
        fail_stage: str | None,
        events: list[Any],
    ) -> None:
        self.keep_open = keep_open
        self.connection_mode = connection_mode
        self.fail_stage = fail_stage
        self.events = events
        self.op = FakeOrigin(fail_stage, events)
        self.environment = FakeEnvironment()

    def __enter__(self) -> FakeSessionContext:
        self.events.append(
            ("session_enter", self.keep_open, self.connection_mode.value)
        )
        if self.fail_stage == "activate":
            try:
                raise RuntimeError(PRIVATE_DETAIL)
            except RuntimeError as cause:
                raise OriginEnvironmentError(
                    "Origin Automation connection failed",
                    code="origin_instance_start_failed",
                    stage="create_instance",
                ) from cause
        if self.fail_stage == "read_version":
            try:
                raise RuntimeError(PRIVATE_DETAIL)
            except RuntimeError as cause:
                raise OriginEnvironmentError(
                    "Origin version could not be read",
                    code="origin_version_read_failed",
                    stage="read_version",
                ) from cause
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        del exc, tb
        self.events.append(("session_exit", exc_type is None))
        if self.fail_stage == "cleanup":
            raise RuntimeError(PRIVATE_DETAIL)


class FakeSessionFactory:
    def __init__(self, fail_stage: str | None = None) -> None:
        self.fail_stage = fail_stage
        self.events: list[Any] = []

    def __call__(
        self,
        *,
        keep_open: bool,
        connection_mode: ConnectionMode,
    ) -> FakeSessionContext:
        self.events.append(
            ("session_factory", keep_open, connection_mode.value)
        )
        return FakeSessionContext(
            keep_open=keep_open,
            connection_mode=connection_mode,
            fail_stage=self.fail_stage,
            events=self.events,
        )


def _install_exporter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail: bool = False,
) -> None:
    def fake_export(
        origin: Any,
        graph: Any,
        output_png: Path,
        output_pdf: Path,
        output_tif: Path,
    ) -> dict[str, bool]:
        del origin, graph
        if fail:
            raise RuntimeError(PRIVATE_DETAIL)
        output_png.write_bytes(b"png")
        output_pdf.write_bytes(b"pdf")
        output_tif.write_bytes(b"tif")
        return {"png": True, "pdf": True, "tif": True}

    monkeypatch.setattr(smoke_module, "export_graph", fake_export)

    def fake_style(origin: Any, *_args: Any) -> dict[str, Any]:
        if origin.fail_stage == "style_graph":
            raise RuntimeError(PRIVATE_DETAIL)
        return {
            "style_profile": {"font_family": "Arial"},
            "axis_style": {
                "font_code_expected": 1,
                "x.label.font": 1,
                "y.label.font": 1,
            },
            "legend_absent_after": True,
        }

    monkeypatch.setattr(smoke_module, "_style_smoke_graph", fake_style)


def test_smoke_success_requires_complete_artifacts_and_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    _install_exporter(monkeypatch)
    output_dir = tmp_path / "origin-smoke"

    result = run_origin_smoke(output_dir, session_factory=factory)

    assert result["status"] == "passed"
    assert {path.name for path in output_dir.iterdir()} == EXPECTED_ARTIFACTS
    for name in ("result.opju", "result.png", "result.pdf", "result.tif"):
        assert (output_dir / name).stat().st_size > 0

    verify = json.loads((output_dir / "origin_verify_report.json").read_text("utf-8"))
    assert set(verify["origin_axis_state"]) == {"x", "y"}
    assert verify["program_path_readback"] == {
        "detected": True,
        "value_included": False,
    }
    assert verify["origin_style_state"]["legend_absent_after"] is True
    assert verify["capability_probe"] == {
        "available_capabilities": [
            "axis_readback",
            "core_2d",
            "editable_opju",
            "pdf_export",
            "png_export",
            "text_readback",
            "tif_export",
        ],
        "unavailable_capabilities": [],
        "probe_complete": False,
    }

    compatibility = json.loads(
        (output_dir / "compatibility-report.json").read_text("utf-8")
    )
    assert compatibility["status"] == "passed"
    assert compatibility["capability_probe"] == verify["capability_probe"]
    assert [item["name"] for item in compatibility["stages"]] == list(SMOKE_STAGES)
    assert all(item["status"] == "passed" for item in compatibility["stages"])
    read_version = next(
        item for item in compatibility["stages"] if item["name"] == "read_version"
    )
    assert read_version["origin_version"] == "10.15"
    assert read_version["origin_version_raw"] == pytest.approx(10.150132)
    assert ("lt_exec", READY_COMMAND) in factory.events

    serialized_reports = " ".join(
        path.read_text("utf-8")
        for path in output_dir.glob("*.json")
    )
    assert PRIVATE_DETAIL not in serialized_reports
    assert "Somebody" not in serialized_reports


@pytest.mark.parametrize(
    ("failed_stage", "expected_error"),
    [
        ("activate", OriginEnvironmentError),
        ("read_version", OriginEnvironmentError),
        ("read_program_path", OriginEnvironmentError),
        ("ready", OriginEnvironmentError),
        ("create_book", OriginDrawError),
        ("create_graph", OriginDrawError),
        ("style_graph", OriginDrawError),
        ("save_project", OriginDrawError),
        ("export", OriginExportError),
        ("readback", OriginDrawError),
        ("cleanup", OriginEnvironmentError),
    ],
)
def test_each_smoke_stage_failure_is_structured_and_redacted(
    failed_stage: str,
    expected_error: type[Exception],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory(failed_stage)
    _install_exporter(monkeypatch, fail=failed_stage == "export")
    output_dir = tmp_path / failed_stage

    with pytest.raises(expected_error) as raised:
        run_origin_smoke(output_dir, session_factory=factory)

    assert PRIVATE_DETAIL not in str(raised.value)
    report_text = (output_dir / "compatibility-report.json").read_text("utf-8")
    assert PRIVATE_DETAIL not in report_text
    assert "Somebody" not in report_text
    assert "0x80004005" not in report_text

    report = json.loads(report_text)
    assert report["status"] == "failed"
    failed_records = [
        item for item in report["stages"] if item["status"] == "failed"
    ]
    assert [item["name"] for item in failed_records] == [failed_stage]
    assert report["privacy"] == {
        "raw_exception_included": False,
        "hresult_included": False,
        "program_path_included": False,
    }


def test_smoke_outputs_stay_inside_requested_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    _install_exporter(monkeypatch)
    working_dir = tmp_path / "working"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    output_dir = tmp_path / "isolated" / "smoke"

    result = run_origin_smoke(output_dir, session_factory=factory)

    assert not any((working_dir / name).exists() for name in EXPECTED_ARTIFACTS)
    for key in (
        "opju",
        "png",
        "pdf",
        "tif",
        "environment_report",
        "origin_verify_report",
        "compatibility_report",
    ):
        assert Path(result[key]).resolve().parent == output_dir.resolve()


def test_smoke_forwards_keep_open_and_uses_isolated_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = FakeSessionFactory()
    _install_exporter(monkeypatch)

    run_origin_smoke(
        tmp_path / "keep-open",
        keep_open=True,
        session_factory=factory,
    )

    assert factory.events[0] == ("session_factory", True, "new_isolated")
    assert ("session_enter", True, "new_isolated") in factory.events
    assert ("session_exit", True) in factory.events
