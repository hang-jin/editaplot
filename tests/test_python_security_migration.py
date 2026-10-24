from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "editaplot" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

import bootstrap_editaplot as bootstrap  # noqa: E402
import build_runtime_manifest  # noqa: E402
import editaplot_core as core  # noqa: E402


@pytest.mark.parametrize("path", [
    "runtime/.editaplot-venv.retained-probe/sentinel.bin",
    ".editaplot.editaplot-retained-probe/sentinel.bin",
])
def test_retained_environment_generations_are_excluded_from_git_inputs(path):
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "check-ignore", "--no-index", path], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == path


@pytest.mark.parametrize("minor, compatible", [(10, False), (11, True), (12, True), (13, False)])
def test_security_runtime_rejects_python_310_and_preserves_supported_minors(minor, compatible):
    result = core.python_compatibility(
        version=(3, minor, 9), implementation="CPython", architecture_bits=64,
        system="Windows", machine="AMD64", windows_major=10,
    )
    assert result["compatible"] is compatible


def _fake_environment_boundary(monkeypatch, root, *, failure=None):
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")

    def status(engine):
        env = engine / ".editaplot-venv"
        return {
            "exists": env.exists(), "valid": (env / "ready").exists(),
            "reason": "ready" if (env / "ready").exists() else "outdated",
            "python_executable": str(env / "Scripts" / "python.exe"),
        }

    def run(command, **_kwargs):
        if command[1:3] == ["-m", "venv"]:
            build = Path(command[-1])
            (build / "Scripts").mkdir(parents=True)
            (build / "Scripts" / "python.exe").write_bytes(b"new-python")
            (build / "new.bin").write_bytes(b"new-environment")
            (build / "ready").touch()
        if "pip" in command and failure == "install":
            return SimpleNamespace(returncode=1, stderr="controlled pip failure", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    def dependencies(python):
        if Path(python).parent.parent == root / ".editaplot-venv" and failure == "post_swap":
            raise KeyboardInterrupt
        return {"ok": True}

    monkeypatch.setattr(core, "managed_environment_status", status)
    monkeypatch.setattr(core.subprocess, "run", run)
    monkeypatch.setattr(core, "_verify_managed_dependencies", dependencies)
    monkeypatch.setattr(core, "_probe_python_executable", lambda python: {
        "ok": True, "compatible": True, "version": "3.12.9", "architecture_bits": 64,
        "executable": str(python),
    })


@pytest.mark.parametrize("failure", [None, "install", "post_swap"])
def test_environment_migration_preserves_every_generation_on_success_failure_and_next_recovery(
    tmp_path, monkeypatch, failure,
):
    env = tmp_path / ".editaplot-venv"
    abandoned = tmp_path / ".editaplot-venv.build-abandoned"
    stale = tmp_path / ".editaplot-venv.stale-historical"
    for directory, filename, content in (
        (env, "old.bin", b"old-environment"),
        (abandoned, "abandoned.bin", b"abandoned-environment"),
        (stale, "historical.bin", b"historical-environment"),
    ):
        directory.mkdir()
        (directory / filename).write_bytes(content)
    _fake_environment_boundary(monkeypatch, tmp_path, failure=failure)
    compatibility = {"version": "3.12.9"}

    if failure is None:
        result = core._repair_environment_transaction(tmp_path, compatibility)
        assert result["ok"] is True
        assert (env / "new.bin").read_bytes() == b"new-environment"
    else:
        with pytest.raises((core.EditaPlotError, KeyboardInterrupt)):
            core._repair_environment_transaction(tmp_path, compatibility)
        assert (env / "old.bin").read_bytes() == b"old-environment"

    expected = {
        "old.bin": b"old-environment", "new.bin": b"new-environment",
        "abandoned.bin": b"abandoned-environment", "historical.bin": b"historical-environment",
    }
    before = {path.name: path.read_bytes() for path in tmp_path.rglob("*.bin")}
    assert before == expected
    assert list(tmp_path.glob(".editaplot-venv.retained-*"))
    core._recover_managed_environment(tmp_path, [])
    assert {path.name: path.read_bytes() for path in tmp_path.rglob("*.bin")} == expected


def test_interrupted_swap_restores_old_ready_environment_but_never_activates_retained(tmp_path, monkeypatch):
    _fake_environment_boundary(monkeypatch, tmp_path)
    retained = tmp_path / ".editaplot-venv.retained-previous-failure"
    stale = tmp_path / ".editaplot-venv.stale-interrupted"
    for directory in (retained, stale):
        directory.mkdir()
        (directory / "ready").touch()
    (stale / "old.bin").write_bytes(b"old")
    (retained / "failed.bin").write_bytes(b"failed")
    core._recover_managed_environment(tmp_path, [])
    assert (tmp_path / ".editaplot-venv" / "old.bin").read_bytes() == b"old"
    assert (retained / "failed.bin").read_bytes() == b"failed"


def test_no_compatible_python_fails_before_setup_creates_any_files(tmp_path, monkeypatch, capsys):
    target = tmp_path / "not-created" / "editaplot"
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ROOT / "runtime", {}))
    monkeypatch.setattr(bootstrap, "discover_python", lambda _root: {"selected": None, "attempts": []})
    assert bootstrap.install_skill(["--target", str(target)]) == 3
    assert not list(tmp_path.iterdir())
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["code"] == "compatible_python_not_found"
    assert "3.11" in payload["error"]["message"]


def test_compatible_verified_python_311_environment_is_reused_without_install(tmp_path, monkeypatch):
    _fake_environment_boundary(monkeypatch, tmp_path)
    env = tmp_path / ".editaplot-venv"
    env.mkdir()
    (env / "ready").touch()
    (env / "old.bin").write_bytes(b"verified-python311")

    def no_install(*_args, **_kwargs):
        raise AssertionError("A verified managed environment must not run an installer")

    monkeypatch.setattr(core.subprocess, "run", no_install)
    result = core._repair_environment_transaction(tmp_path, {"version": "3.12.9"})
    assert result["ok"] is True
    assert (env / "old.bin").read_bytes() == b"verified-python311"
    assert result["actions"][-1]["action"] == "reuse_verified_project_venv"


def test_environment_creation_failure_leaves_old_environment_active(tmp_path, monkeypatch):
    env = tmp_path / ".editaplot-venv"
    env.mkdir()
    (env / "old.bin").write_bytes(b"old-before-build")
    _fake_environment_boundary(monkeypatch, tmp_path)

    def creation_fails(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stderr="controlled venv failure", stdout="")

    monkeypatch.setattr(core.subprocess, "run", creation_fails)
    with pytest.raises(core.EditaPlotError, match="staged project-local"):
        core._repair_environment_transaction(tmp_path, {"version": "3.12.9"})
    assert (env / "old.bin").read_bytes() == b"old-before-build"


def test_managed_python_cannot_replace_itself(tmp_path, monkeypatch):
    _fake_environment_boundary(monkeypatch, tmp_path)
    env = tmp_path / ".editaplot-venv"
    python = env / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"active-managed-python")
    monkeypatch.setattr(core.sys, "executable", str(python))
    with pytest.raises(core.EditaPlotError) as raised:
        core._repair_environment_transaction(tmp_path, {"version": "3.11.9"})
    assert raised.value.code == "managed_environment_self_repair_requires_base_python"
    assert python.read_bytes() == b"active-managed-python"
    assert not list(tmp_path.glob(".editaplot-venv.build-*"))


def test_retained_environments_are_excluded_from_skill_copy_without_deleting_source(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "copied"
    archive = source / "nested" / ".editaplot-venv.retained-old" / "old.bin"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"archived-environment")
    (source / "public.txt").write_text("public", encoding="utf-8")
    assert bootstrap._copy_tree_without_deleting(source, destination) == 1
    assert (destination / "public.txt").read_text(encoding="utf-8") == "public"
    assert not list(destination.rglob("old.bin"))
    assert archive.read_bytes() == b"archived-environment"


def test_retained_environments_are_excluded_from_runtime_inventory(tmp_path, monkeypatch):
    marker = tmp_path / "src" / "origin_sciplot" / "__init__.py"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")
    retained = tmp_path / ".editaplot-venv.retained-old" / "old.bin"
    retained.parent.mkdir()
    retained.write_bytes(b"archived-environment")
    monkeypatch.setattr(sys, "argv", ["manifest", "--runtime", str(tmp_path)])
    assert build_runtime_manifest.main() == 0
    manifest = json.loads((tmp_path / "runtime-manifest.json").read_text(encoding="utf-8"))
    assert [record["path"] for record in manifest["files"]] == ["src/origin_sciplot/__init__.py"]
    assert retained.read_bytes() == b"archived-environment"


@pytest.mark.parametrize("minor, valid", [(10, False), (11, True), (12, True)])
def test_real_managed_fingerprint_gate_checks_the_interpreter_version(tmp_path, monkeypatch, minor, valid):
    env = tmp_path / ".editaplot-venv"
    python = env / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    lock = ROOT / "skill" / "editaplot" / "scripts" / "requirements-runtime.lock"
    fingerprint = {
        "schema_version": "1.0", "managed_python_version": f"3.{minor}.9",
        "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "dependency_policy_sha256": core._dependency_policy_hash(),
    }
    (env / ".editaplot-environment.json").write_text(json.dumps(fingerprint), encoding="utf-8")

    def probe(command, **_kwargs):
        if "architecture_bits" in command[-1]:
            payload = {
                "executable": str(python), "implementation": "CPython", "version": [3, minor, 9],
                "architecture_bits": 64,
            }
        else:
            payload = {
                "numpy": True, "pandas": True, "PyYAML": True, "jsonschema": True,
                "matplotlib": True, "originpro": True, "OriginExt": True, "openpyxl": True,
                "xlrd": True, "pillow": True,
            }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    monkeypatch.setattr(core.subprocess, "run", probe)
    result = core.managed_environment_status(tmp_path)
    assert result["valid"] is valid
    assert python.is_file()


@pytest.mark.parametrize("repair_fails", [False, True])
def test_skill_update_retains_old_and_failed_nested_environments_across_recovery(
    tmp_path, monkeypatch, capsys, repair_fails,
):
    target = tmp_path / "editaplot"
    scripts = target / "scripts"
    scripts.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: editaplot\n---\n", encoding="utf-8")
    for filename in ("editaplot.py", "bootstrap_editaplot.py"):
        (scripts / filename).write_text("# old skill\n", encoding="utf-8")
    for relative, content in (
        (".editaplot-venv/old.bin", b"old-managed-environment"),
        (".editaplot-venv.retained-older/older.bin", b"older-retained-environment"),
    ):
        path = target / relative
        path.parent.mkdir()
        path.write_bytes(content)
    monkeypatch.setattr(bootstrap, "_resolve_engine", lambda _argv: (ROOT / "runtime", {}))
    monkeypatch.setattr(bootstrap, "discover_python", lambda _root: {
        "selected": {"source": "test", "executable": "selected-base.exe"}, "attempts": [],
    })
    monkeypatch.setattr(bootstrap, "managed_environment_status", lambda _root: {
        "valid": True, "python_executable": "managed.exe",
        "dependency_lock_sha256": bootstrap._skill_dependency_lock_sha(bootstrap.SKILL_ROOT),
    })

    def run(command, **_kwargs):
        if "repair-environment" in command:
            failed_or_new = target / ".editaplot-venv" / "new.bin"
            failed_or_new.parent.mkdir()
            failed_or_new.write_bytes(b"new-environment")
            return (18, {"ok": False}) if repair_fails else (0, {"ok": True})
        return 0, {"ok": True, "ready_for_analysis": True, "ready_for_render": False}

    monkeypatch.setattr(bootstrap, "_run_json_command", run)
    assert bootstrap.install_skill(["--target", str(target)]) == (18 if repair_fails else 0)
    capsys.readouterr()
    expected = {
        "old.bin": b"old-managed-environment", "older.bin": b"older-retained-environment",
        "new.bin": b"new-environment",
    }
    assert {path.name: path.read_bytes() for path in tmp_path.rglob("*.bin")} == expected
    assert list(tmp_path.glob(".editaplot.editaplot-retained-*"))
    bootstrap._recover_install_swap(target)
    assert {path.name: path.read_bytes() for path in tmp_path.rglob("*.bin")} == expected
    target.rename(tmp_path / "saved-active")
    bootstrap._recover_install_swap(target)
    assert not target.exists(), "Retained Skill generations must not become recovery candidates"


def test_abandoned_skill_build_is_retained_with_nested_environment(tmp_path):
    target = tmp_path / "editaplot"
    build = bootstrap._next_install_sibling(target, "build")
    nested = build / ".editaplot-venv.retained-old" / "old.bin"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"abandoned-nested-environment")
    bootstrap._write_install_state(build, target=target, kind="build")
    bootstrap._recover_install_swap(target)
    assert not build.exists()
    retained = list(tmp_path.glob(".editaplot.editaplot-retained-*"))
    assert len(retained) == 1
    assert (retained[0] / ".editaplot-venv.retained-old" / "old.bin").read_bytes() == (
        b"abandoned-nested-environment"
    )
    bootstrap._recover_install_swap(target)
    assert not target.exists()
    assert retained[0].is_dir()
