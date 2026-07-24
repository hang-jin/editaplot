from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
RUNTIME = PRODUCT_ROOT / "runtime"
RUNTIME_SRC = RUNTIME / "src"
for candidate in (SCRIPTS, RUNTIME_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import editaplot_core as core  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import (  # noqa: E402
    OriginEnvironmentError,
    WorkerExitCode,
)
from origin_sciplot.workers import origin_smoke_worker  # noqa: E402


def test_smoke_command_uses_runtime_module_and_isolated_close_default(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "smoke"

    command, env, root = core.build_origin_smoke_command(
        output_dir=output_dir,
        engine_home=RUNTIME,
        python_executable="python-test.exe",
    )

    assert root == RUNTIME.resolve()
    assert command == [
        "python-test.exe",
        "-m",
        "origin_sciplot.workers.origin_smoke_worker",
        "--output-dir",
        str(output_dir.resolve()),
        "--close-origin",
    ]
    assert str(RUNTIME_SRC) in env["PYTHONPATH"]
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_smoke_command_can_keep_owned_instance_open(tmp_path: Path) -> None:
    command, _env, _root = core.build_origin_smoke_command(
        output_dir=tmp_path / "smoke",
        engine_home=RUNTIME,
        keep_origin_open=True,
    )

    assert command[-1] == "--keep-origin-open"


def test_smoke_worker_emits_concise_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "smoke"
    result = {
        "status": "passed",
        "opju": str(output_dir / "result.opju"),
        "png": str(output_dir / "result.png"),
        "pdf": str(output_dir / "result.pdf"),
        "tif": str(output_dir / "result.tif"),
        "environment_report": str(output_dir / "environment_report.json"),
        "origin_verify_report": str(output_dir / "origin_verify_report.json"),
        "compatibility_report": str(output_dir / "compatibility-report.json"),
        "verify": {"internal": "not emitted"},
    }
    monkeypatch.setattr(origin_smoke_worker, "run_origin_smoke", lambda *_args, **_kwargs: result)

    returncode = origin_smoke_worker.main(["--output-dir", str(output_dir)])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert returncode == WorkerExitCode.SUCCESS
    assert [line["type"] for line in lines] == ["progress", "done"]
    assert lines[-1]["message"] == "Origin 最小绘图闭环已通过。"
    assert "verify" not in lines[-1]


def test_smoke_worker_preserves_structured_error_without_private_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "smoke"
    output_dir.mkdir()
    report = output_dir / "compatibility-report.json"
    report.write_text("{}\n", encoding="utf-8")

    def fail(*_args: object, **_kwargs: object) -> dict[str, object]:
        try:
            private_detail = "\\".join(
                (f"{chr(67)}:", "Users", "Private", "Origin 0x80004005")
            )
            raise RuntimeError(private_detail)
        except RuntimeError as cause:
            raise OriginEnvironmentError(
                "Origin Automation connection failed",
                code="origin_instance_start_failed",
                stage="create_instance",
            ) from cause

    monkeypatch.setattr(origin_smoke_worker, "run_origin_smoke", fail)

    returncode = origin_smoke_worker.main(["--output-dir", str(output_dir)])
    output = capsys.readouterr().out
    lines = [json.loads(line) for line in output.splitlines()]

    assert returncode == WorkerExitCode.ORIGIN_ENVIRONMENT
    assert lines[-1]["type"] == "error"
    assert lines[-1]["code"] == "origin_instance_start_failed"
    assert lines[-1]["stage"] == "create_instance"
    assert lines[-1]["compatibility_report"] == str(report.resolve())
    assert "Private" not in output
    assert "0x80004005" not in output
