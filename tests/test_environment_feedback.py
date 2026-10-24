from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime" / "src"))

from origin_sciplot.origin_backend import safe_errors  # noqa: E402
from origin_sciplot.origin_backend import smoke_test as smoke  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginEnvironmentError  # noqa: E402
from origin_sciplot.origin_backend.smoke_test import (  # noqa: E402
    _safe_error_payload,
    _stable_stage_error,
)

SYNTHETIC_PRIVATE_PATH = "/".join((f"{chr(67)}:", "Users", "private"))


@pytest.mark.parametrize(
    "private_reason", ["No module named originpro", "DLL load failed " + SYNTHETIC_PRIVATE_PATH]
)
def test_import_failure_is_not_reported_as_com_activation(private_reason: str) -> None:
    cause = OriginEnvironmentError(private_reason, code="originpro_import_failed", stage="import_originpro")
    result = _stable_stage_error("activate", cause)
    payload = _safe_error_payload(result)
    assert payload["code"] == "originpro_import_failed"
    assert payload["stage"] == "import_originpro"
    assert "import" in payload["message"].lower()
    assert "selected Python" in payload["message"]
    assert "Automation" not in payload["message"]
    assert private_reason not in payload["message"]
    assert SYNTHETIC_PRIVATE_PATH not in json.dumps(payload)


def test_real_activation_error_keeps_activation_message_and_safe_code() -> None:
    cause = OriginEnvironmentError(
        "private failure", code="origin_com_server_execution_failed", stage="create_instance"
    )
    result = _stable_stage_error("activate", cause)
    assert result.code == "origin_com_server_execution_failed"
    assert result.stage == "create_instance"
    assert str(result) == "Origin Automation could not be activated"


def test_smoke_geometry_failure_exposes_only_numeric_measurements() -> None:
    error_type = getattr(safe_errors, "OriginGeometryError", safe_errors.OriginDrawError)
    cause = error_type(
        "private diagnostic",
        code="origin_page_geometry_mismatch",
        stage="style_graph",
        diagnostics={
            "geometry_check": "page_width_cm",
            "expected_value": 18.0,
            "measured_value": 17.957,
            "tolerance_value": 0.03,
            "private_text": "private diagnostic",
        },
    )
    payload = _safe_error_payload(_stable_stage_error("style_graph", cause))
    assert payload["code"] == "origin_page_geometry_mismatch"
    assert payload["diagnostics"] == {
        "geometry_check": "page_width_cm",
        "expected_value": 18.0,
        "measured_value": 17.957,
        "tolerance_value": 0.03,
    }
    assert "private diagnostic" not in json.dumps(payload)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "private account", True])
def test_geometry_diagnostics_reject_non_numeric_or_non_finite_values(bad_value) -> None:
    cause = safe_errors.OriginDrawError(
        "Safe message", diagnostics={"geometry_check": "page_width_cm", "measured_value": bad_value}
    )
    assert "measured_value" not in cause.diagnostics
    json.dumps(cause.diagnostics, allow_nan=False)


@pytest.mark.parametrize("bad_check", [{"private": "value"}, ["page_width_cm"], 42, None])
def test_untrusted_geometry_check_does_not_replace_the_original_error(bad_check) -> None:
    cause = safe_errors.OriginDrawError(
        "Original error", diagnostics={"geometry_check": bad_check, "measured_value": 5.0}
    )
    assert str(cause) == "Original error"
    assert cause.diagnostics == {}


def test_geometry_failure_does_not_falsely_mark_text_readback_unavailable() -> None:
    stages = smoke._new_stage_records()
    smoke._mark_passed(stages, "create_graph")
    smoke._mark_failed(stages, "style_graph", safe_errors.OriginGeometryError("Size mismatch"))
    probe = smoke._capability_probe_from_stages(stages)
    assert smoke.OriginCapability.TEXT_READBACK not in probe.unavailable_capabilities
    assert smoke.OriginCapability.TEXT_READBACK not in probe.available_capabilities
    assert probe.probe_complete is False


@pytest.mark.skipif(os.name != "nt", reason="Exercises the installed Windows batch launcher")
@pytest.mark.parametrize("use_override", [False, True])
def test_installed_launcher_without_python_on_path(tmp_path: Path, use_override: bool) -> None:
    # A real installed layout: JSON points outside the Skill, and no Python is on PATH.
    installed = tmp_path / "中文 installed skill"
    scripts = installed / "scripts"
    scripts.mkdir(parents=True)
    engine = tmp_path / "中文 external engine"
    managed = engine / ".editaplot-venv"
    venv.EnvBuilder(with_pip=False).create(managed)
    managed_python = managed / "Scripts" / "python.exe"
    shutil.copy2(ROOT / "editaplot.cmd", installed / "editaplot.cmd")
    helper = ROOT / "skill" / "editaplot" / "scripts" / "launch_managed.ps1"
    if helper.exists():
        shutil.copy2(helper, scripts / helper.name)
    (installed / ".editaplot-local.json").write_text(
        json.dumps({"schema_version": "1.0", "engine_home": str(engine)}, ensure_ascii=False),
        encoding="utf-8",
    )
    (scripts / "bootstrap_editaplot.py").write_text(
        "import json,sys;print(json.dumps({'prefix':sys.prefix,'args':sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    environment = {key.upper(): value for key, value in os.environ.items()}
    for name in ("EDITAPLOT_PYTHON", "EDITAPLOT_ENGINE_HOME", "PYTHONHOME", "PYTHONPATH"):
        environment.pop(name, None)
    system_root = Path(environment["SYSTEMROOT"])
    environment["PATH"] = str(system_root / "System32")
    environment["LOCALAPPDATA"] = str(tmp_path / "no-user-installs")
    environment["PROGRAMFILES"] = str(tmp_path / "no-system-installs")
    if use_override:
        environment["EDITAPLOT_PYTHON"] = str(Path(sys.executable).resolve())
    source = str(tmp_path / "中文 input & measurements.csv")
    batch_command = subprocess.list2cmdline(
        [str(installed / "editaplot.cmd"), "--diagnose", "--source", source]
    )
    completed = subprocess.run(
        f'"{system_root / "System32" / "cmd.exe"}" /d /s /c "{batch_command}"',
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    payload = json.loads(completed.stdout)
    expected_prefix = sys.prefix if use_override else str(managed)
    assert Path(payload["prefix"]).resolve() == Path(expected_prefix).resolve()
    assert payload["args"] == ["--diagnose", "--source", source]
    assert managed_python.is_file()
