#!/usr/bin/env python
"""Dependency-free Windows bootstrap for the EditaPlot command line.

The batch launcher starts this module only with a verified 64-bit CPython.
The module then applies the full discovery policy, launches the real CLI with
an absolute interpreter path, and confines dependency repair to EditaPlot's
managed environment.  It never installs Python or Origin system-wide.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO

from editaplot_core import (
    MANAGED_ENV_LOCK,
    managed_environment_status,
    python_compatibility,
    resolve_engine_home,
    windows_host_compatibility,
)

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIRECTORY.parent
LOCAL_CONFIG_NAME = ".editaplot-local.json"
INSTALL_STATE_NAME = ".editaplot-install-state.json"
DISCOVERY_ORDER = (
    "EDITAPLOT_PYTHON",
    "managed_environment",
    "windows_py_launcher",
    "PATH",
    "standard_windows_installations",
)
CLI_COMMANDS = frozenset(
    {
        "doctor",
        "catalog",
        "palettes",
        "inspect",
        "start",
        "recommend",
        "plan",
        "render",
        "repair-environment",
        "verify",
        "panel-plan",
        "setup",
        "install-skill",
    }
)
SUPPORTED_TABLE_SUFFIXES = frozenset({".csv", ".txt", ".xls", ".xlsx"})
PROBE_CODE = (
    "import json,platform,struct,sys;"
    "print(json.dumps({'executable':sys.executable,'implementation':"
    "platform.python_implementation(),'version':list(sys.version_info[:3]),"
    "'architecture_bits':struct.calcsize('P')*8}))"
)


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream, flush=True)


@contextmanager
def _exclusive_file_lock(path: Path, *, error_code: str) -> Iterator[None]:
    """Hold a non-blocking process lock; OS lock release is crash-safe."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle: BinaryIO = path.open("a+b")
    handle.seek(0)
    if handle.read(1) != b"1":
        handle.seek(0)
        handle.write(b"1")
        handle.flush()
    handle.seek(0)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - production support is Windows; used by cross-platform tests
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
    except (OSError, BlockingIOError) as exc:
        handle.close()
        raise RuntimeError(error_code) from exc
    try:
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - production support is Windows
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _repository_root() -> Path | None:
    candidate = SCRIPT_DIRECTORY.parents[2] if len(SCRIPT_DIRECTORY.parents) >= 3 else None
    if candidate is not None and (candidate / "skill" / "editaplot" / "scripts").is_dir():
        return candidate
    return None


def _local_config() -> dict[str, Any]:
    path = SKILL_ROOT / LOCAL_CONFIG_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"config_error": "invalid_local_config", "config_path": str(path)}
    return payload if isinstance(payload, dict) else {"config_error": "invalid_local_config"}


def _engine_argument(argv: list[str]) -> str | None:
    for index, value in enumerate(argv):
        if value == "--engine-home" and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith("--engine-home="):
            return value.partition("=")[2]
    return None


def _normalize_cli_arguments(argv: list[str]) -> list[str]:
    """Turn a dropped/first-position table into the beginner ``start`` command."""
    if not argv or argv[0] in CLI_COMMANDS or argv[0].startswith("-"):
        return list(argv)
    raw_path = os.path.expandvars(argv[0].strip().strip('"'))
    candidate = Path(raw_path).expanduser()
    try:
        supported_file = candidate.suffix.casefold() in SUPPORTED_TABLE_SUFFIXES and candidate.is_file()
    except OSError:
        supported_file = False
    if not supported_file:
        return list(argv)
    return ["start", str(candidate), *argv[1:]]


def _resolve_engine(argv: list[str]) -> tuple[Path | None, dict[str, Any]]:
    config = _local_config()
    requested = _engine_argument(argv) or os.environ.get("EDITAPLOT_ENGINE_HOME")
    if not requested and config.get("engine_home"):
        requested = str(config["engine_home"])
    repository = _repository_root()
    if not requested and repository is not None and (repository / "runtime").is_dir():
        requested = str(repository / "runtime")
    try:
        return resolve_engine_home(requested), config
    except Exception as exc:  # the CLI doctor will report the full structured engine error
        return None, {**config, "engine_error": str(exc)}


def _probe(command: list[str], *, source: str, detail: str) -> dict[str, Any]:
    record: dict[str, Any] = {"source": source, "detail": detail, "command": command[0]}
    try:
        completed = subprocess.run(  # noqa: S603 - local interpreter discovery, never shell=True
            [*command, "-I", "-c", PROBE_CODE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**record, "usable": False, "reason": type(exc).__name__}
    if completed.returncode != 0:
        return {
            **record,
            "usable": False,
            "reason": "probe_failed",
            "returncode": completed.returncode,
        }
    try:
        raw = json.loads(completed.stdout.strip().splitlines()[-1])
        compatibility = python_compatibility(
            version=tuple(int(part) for part in raw["version"]),
            implementation=str(raw["implementation"]),
            architecture_bits=int(raw["architecture_bits"]),
        )
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {**record, "usable": False, "reason": f"invalid_probe:{type(exc).__name__}"}
    return {
        **record,
        "usable": True,
        "compatible": bool(compatibility["compatible"]),
        "executable": str(Path(str(raw["executable"])).resolve()),
        "version": compatibility["version"],
        "version_info": compatibility["version_info"],
        "implementation": compatibility["implementation"],
        "architecture_bits": compatibility["architecture_bits"],
        "reasons": compatibility["reasons"],
    }


def _candidate_paths_from_registry() -> list[Path]:
    if platform.system() != "Windows":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover - winreg exists on supported Windows CPython
        return []
    paths: list[Path] = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    views = tuple(
        dict.fromkeys(
            (
                getattr(winreg, "KEY_WOW64_64KEY", 0),
                0,
                getattr(winreg, "KEY_WOW64_32KEY", 0),
            )
        )
    )
    for root in roots:
        for version in ("3.12", "3.11", "3.10"):
            for view in views:
                try:
                    with winreg.OpenKey(
                        root,
                        rf"Software\Python\PythonCore\{version}\InstallPath",
                        0,
                        winreg.KEY_READ | view,
                    ) as key:
                        install_path, _kind = winreg.QueryValueEx(key, None)
                except OSError:
                    continue
                paths.append(Path(str(install_path)) / "python.exe")
    return paths


def _candidate_paths_from_standard_locations() -> list[Path]:
    roots = [
        Path(value)
        for value in (
            os.environ.get("LocalAppData"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramW6432"),
            os.environ.get("ProgramFiles(x86)"),
        )
        if value
    ]
    candidates: list[Path] = []
    for root in roots:
        bases = (root / "Programs" / "Python", root)
        for base in bases:
            for directory in ("Python312", "Python311", "Python310"):
                candidates.append(base / directory / "python.exe")
    candidates.extend(_candidate_paths_from_registry())
    return candidates


def _first_compatible_group(
    commands: list[tuple[list[str], str]],
    *,
    source: str,
    attempts: list[dict[str, Any]],
    seen: set[str],
) -> dict[str, Any] | None:
    compatible: list[dict[str, Any]] = []
    for command, detail in commands:
        record = _probe(command, source=source, detail=detail)
        executable = os.path.normcase(str(record.get("executable") or ""))
        if executable and executable in seen:
            continue
        if executable:
            seen.add(executable)
        attempts.append(record)
        if record.get("compatible"):
            compatible.append(record)
    if not compatible:
        return None
    return max(compatible, key=lambda item: tuple(item["version_info"]))


def discover_python(engine_root: Path | None) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    selected: dict[str, Any] | None = None

    explicit = os.environ.get("EDITAPLOT_PYTHON")
    if explicit:
        selected = _first_compatible_group(
            [([os.path.expandvars(explicit.strip().strip('"'))], "environment override")],
            source="EDITAPLOT_PYTHON",
            attempts=attempts,
            seen=seen,
        )

    if selected is None and engine_root is not None:
        status = managed_environment_status(engine_root)
        if status["valid"]:
            selected = _first_compatible_group(
                [([status["python_executable"]], "verified fingerprint and dependency lock")],
                source="managed_environment",
                attempts=attempts,
                seen=seen,
            )
        elif status["exists"]:
            attempts.append(
                {
                    "source": "managed_environment",
                    "detail": str(status["environment"]),
                    "usable": False,
                    "compatible": False,
                    "reason": status["reason"],
                }
            )

    if selected is None:
        general_candidates: list[dict[str, Any]] = []
        launcher = shutil.which("py.exe") or shutil.which("py")
        if launcher:
            launcher_candidate = _first_compatible_group(
                [
                    ([launcher, "-3.12"], "py -3.12"),
                    ([launcher, "-3.11"], "py -3.11"),
                    ([launcher, "-3.10"], "py -3.10"),
                ],
                source="windows_py_launcher",
                attempts=attempts,
                seen=seen,
            )
            if launcher_candidate is not None:
                general_candidates.append(launcher_candidate)

        path_commands: list[tuple[list[str], str]] = []
        for name in ("python.exe", "python3.exe", "python", "python3"):
            executable = shutil.which(name)
            if executable and (
                launcher is None
                or os.path.normcase(os.path.abspath(executable))
                != os.path.normcase(os.path.abspath(launcher))
            ):
                path_commands.append(([executable], name))
        path_candidate = _first_compatible_group(
            path_commands,
            source="PATH",
            attempts=attempts,
            seen=seen,
        )
        if path_candidate is not None:
            general_candidates.append(path_candidate)

        standard_commands = [
            ([str(path)], "standard location")
            for path in _candidate_paths_from_standard_locations()
            if path.is_file()
        ]
        standard_candidate = _first_compatible_group(
            standard_commands,
            source="standard_windows_installations",
            attempts=attempts,
            seen=seen,
        )
        if standard_candidate is not None:
            general_candidates.append(standard_candidate)
        if general_candidates:
            selected = max(general_candidates, key=lambda item: tuple(item["version_info"]))

    host = windows_host_compatibility()
    if not host["compatible"]:
        selected = None
    return {
        "selected": selected,
        "attempts": attempts,
        "discovery_order": list(DISCOVERY_ORDER),
        "required": "Windows with 64-bit CPython 3.10, 3.11, or 3.12",
        "host": host,
    }


def _copy_tree_without_deleting(source: Path, destination: Path) -> int:
    copied = 0
    generated_segments = {
        ".editaplot-venv",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    }
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(part in generated_segments for part in relative.parts):
            continue
        if relative.name == LOCAL_CONFIG_NAME or path.suffix.casefold() in {".pyc", ".pyo"}:
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(path), str(target))
            copied += 1
    return copied


def _install_prefix(target: Path, kind: str) -> str:
    return f".{target.name}.editaplot-{kind}-"


def _validated_install_sibling(target: Path, path: Path, kind: str) -> Path:
    """Accept only an EditaPlot-owned staging/backup sibling of ``target``."""

    parent = target.parent.resolve()
    candidate = path.expanduser()
    try:
        direct_sibling = candidate.parent.resolve() == parent
    except OSError:
        direct_sibling = False
    if not direct_sibling or not candidate.name.startswith(_install_prefix(target, kind)):
        raise ValueError(f"unsafe EditaPlot {kind} path: {candidate}")
    if candidate.exists() and not candidate.is_symlink():
        try:
            contained = candidate.resolve().parent == parent
        except OSError:
            contained = False
        if not contained:
            raise ValueError(f"EditaPlot {kind} path escapes its target parent: {candidate}")
    return candidate


def _next_install_sibling(target: Path, kind: str) -> Path:
    candidate = target.parent / f"{_install_prefix(target, kind)}{os.getpid()}"
    suffix = 0
    while candidate.exists() or candidate.is_symlink():
        suffix += 1
        candidate = target.parent / f"{_install_prefix(target, kind)}{os.getpid()}-{suffix}"
    return _validated_install_sibling(target, candidate, kind)


def _remove_install_sibling(target: Path, path: Path, kind: str) -> None:
    candidate = _validated_install_sibling(target, path, kind)
    if candidate.is_symlink() or candidate.is_file():
        candidate.unlink(missing_ok=True)
    elif candidate.is_dir():
        shutil.rmtree(candidate)


def _write_install_state(path: Path, *, target: Path, kind: str) -> None:
    (path / INSTALL_STATE_NAME).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "managed_by": "EditaPlot",
                "kind": kind,
                "target": str(target.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _owned_install_state(path: Path, *, target: Path, kind: str) -> bool:
    state = path / INSTALL_STATE_NAME
    if not state.is_file():
        return False
    try:
        payload = json.loads(state.read_text(encoding="utf-8"))
        recorded_target = Path(str(payload["target"])).resolve()
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        payload.get("managed_by") == "EditaPlot"
        and payload.get("kind") == kind
        and recorded_target == target.resolve()
    )


def _install_journal(target: Path) -> Path:
    return target.parent / f".{target.name}.editaplot-transaction.json"


def _skill_dependency_lock_sha(path: Path) -> str | None:
    lock = path / "scripts" / "requirements-runtime.lock"
    if not lock.is_file():
        return None
    return hashlib.sha256(lock.read_bytes()).hexdigest()


def _write_install_journal(
    target: Path,
    backup: Path | None,
    engine_root: Path,
    skill_root: Path,
) -> None:
    journal = _install_journal(target)
    temporary = journal.with_suffix(f".tmp-{os.getpid()}")
    expected_lock_sha256 = _skill_dependency_lock_sha(skill_root)
    if expected_lock_sha256 is None:
        raise ValueError("the staged Skill dependency lock is missing")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "managed_by": "EditaPlot",
                "target": str(target.resolve()),
                "backup_name": backup.name if backup is not None else None,
                "engine_home": str(engine_root.resolve()),
                "expected_dependency_lock_sha256": expected_lock_sha256,
                "phase": "skill_swap_pending_environment_repair",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, journal)


def _read_install_journal(target: Path) -> dict[str, Any] | None:
    journal = _install_journal(target)
    if not journal.is_file():
        return None
    try:
        payload = json.loads(journal.read_text(encoding="utf-8"))
        recorded_target = Path(str(payload["target"])).resolve()
        backup_name = payload.get("backup_name")
        backup = target.parent / str(backup_name) if backup_name else None
        engine_root = resolve_engine_home(str(payload["engine_home"]))
        expected_lock_sha256 = str(payload["expected_dependency_lock_sha256"])
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("managed_by") != "EditaPlot" or recorded_target != target.resolve():
        return None
    try:
        validated_backup = (
            _validated_install_sibling(target, backup, "backup")
            if backup is not None
            else None
        )
    except ValueError:
        return None
    return {
        "backup": validated_backup,
        "engine_root": engine_root,
        "expected_dependency_lock_sha256": expected_lock_sha256,
    }


def _install_siblings(target: Path, kind: str) -> list[Path]:
    prefix = _install_prefix(target, kind)
    if not target.parent.is_dir():
        return []
    return sorted(
        (
            _validated_install_sibling(target, candidate, kind)
            for candidate in target.parent.iterdir()
            if candidate.name.startswith(prefix)
        ),
        key=lambda item: item.name,
    )


def _recover_install_swap(target: Path) -> str:
    """Recover only deterministic siblings left by an interrupted prior setup."""

    builds = _install_siblings(target, "build")
    owned_backups = [
        item
        for item in _install_siblings(target, "backup")
        if _owned_install_state(item, target=target, kind="backup")
    ]
    transaction = _read_install_journal(target)
    recovery = "none"
    if transaction is not None:
        journal_backup = transaction["backup"]
        if not target.exists() and not target.is_symlink() and journal_backup is not None:
            if journal_backup.exists() or journal_backup.is_symlink():
                os.replace(journal_backup, target)
                recovery = "restored_previous_skill_before_environment_commit"
        elif target.is_dir() and _is_recognized_editaplot_skill(target):
            target_lock = _skill_dependency_lock_sha(target)
            engine_root = transaction["engine_root"]
            try:
                with _exclusive_file_lock(
                    engine_root / MANAGED_ENV_LOCK,
                    error_code="environment_repair_in_progress",
                ):
                    managed_lock = managed_environment_status(engine_root).get(
                        "dependency_lock_sha256"
                    )
            except RuntimeError:
                raise
            environment_committed = bool(
                target_lock
                and target_lock == transaction["expected_dependency_lock_sha256"]
                and target_lock == managed_lock
            )
            if environment_committed:
                if journal_backup is not None and (
                    journal_backup.exists() or journal_backup.is_symlink()
                ):
                    _remove_install_sibling(target, journal_backup, "backup")
                (target / INSTALL_STATE_NAME).unlink(missing_ok=True)
                recovery = "committed_skill_and_environment"
            elif journal_backup is not None and (
                journal_backup.exists() or journal_backup.is_symlink()
            ):
                abandoned = _next_install_sibling(target, "build")
                os.replace(target, abandoned)
                os.replace(journal_backup, target)
                _remove_install_sibling(target, abandoned, "build")
                recovery = "restored_previous_skill_after_environment_mismatch"
            elif _owned_install_state(target, target=target, kind="build"):
                abandoned = _next_install_sibling(target, "build")
                os.replace(target, abandoned)
                _remove_install_sibling(target, abandoned, "build")
                recovery = "removed_incomplete_fresh_skill"
            else:
                recovery = "cancelled_before_skill_swap"
        elif journal_backup is None:
            recovery = "cancelled_fresh_install_before_skill_swap"
        if target.exists() and (
            journal_backup is None
            or not (journal_backup.exists() or journal_backup.is_symlink())
        ):
            _install_journal(target).unlink(missing_ok=True)
        elif not target.exists() and journal_backup is None:
            _install_journal(target).unlink(missing_ok=True)
    if not target.exists() and not target.is_symlink() and owned_backups:
        restore = owned_backups.pop()
        (restore / INSTALL_STATE_NAME).unlink(missing_ok=True)
        os.replace(restore, target)
    if target.is_dir() and _is_recognized_editaplot_skill(target):
        for backup in owned_backups:
            _remove_install_sibling(target, backup, "backup")
    for build in builds:
        if _owned_install_state(build, target=target, kind="build"):
            _remove_install_sibling(target, build, "build")
    return recovery


def _is_recognized_editaplot_skill(path: Path) -> bool:
    skill_file = path / "SKILL.md"
    cli_file = path / "scripts" / "editaplot.py"
    bootstrap_file = path / "scripts" / "bootstrap_editaplot.py"
    if not skill_file.is_file() or not cli_file.is_file():
        return False
    try:
        header = skill_file.read_text(encoding="utf-8")[:2048]
    except OSError:
        return False
    if "\nname: editaplot\n" not in f"\n{header}":
        return False
    if bootstrap_file.is_file():
        return True

    # EditaPlot releases before the transactional bootstrap did not include an
    # install marker or bootstrap script.  Recognize only that complete legacy
    # layout so existing users can upgrade without weakening the guard against
    # overwriting an unrelated directory that happens to contain SKILL.md.
    legacy_signature = (
        path / "scripts" / "editaplot_core.py",
        path / "scripts" / "requirements-runtime.lock",
        path / "agents" / "openai.yaml",
        path / "references" / "runtime.md",
    )
    return all(item.is_file() for item in legacy_signature)


def _run_json_command(
    command: list[str],
    *,
    environment: dict[str, str],
    timeout: int = 1500,
) -> tuple[int, dict[str, Any]]:
    try:
        completed = subprocess.run(  # noqa: S603 - selected absolute Python and fixed local CLI
            command,
            cwd=os.getcwd(),
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        return 124, {
            "ok": False,
            "error": {
                "code": "setup_command_timeout",
                "message": "The setup subprocess exceeded its bounded run time.",
                "timeout_seconds": timeout,
                "command": Path(command[0]).name,
                "output_tail": ((stdout or "") + (stderr or ""))[-1200:],
            },
        }
    except OSError as exc:
        return 126, {
            "ok": False,
            "error": {
                "code": "setup_command_unavailable",
                "message": "The selected setup interpreter or command became unavailable.",
                "command": Path(command[0]).name,
                "os_error": type(exc).__name__,
                "errno": exc.errno,
            },
        }
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = {
            "ok": False,
            "error": {
                "code": "setup_command_output_invalid",
                "returncode": completed.returncode,
                "output_tail": output[-1200:],
            },
        }
    return int(completed.returncode), payload


def _parse_setup_target(argv: list[str]) -> tuple[Path | None, dict[str, Any] | None]:
    target: Path | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--target":
            if target is not None:
                return None, {"code": "setup_target_repeated"}
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                return None, {"code": "setup_target_missing"}
            target = Path(argv[index + 1]).expanduser()
            index += 2
            continue
        if argument.startswith("--target="):
            if target is not None:
                return None, {"code": "setup_target_repeated"}
            value = argument.partition("=")[2]
            if not value:
                return None, {"code": "setup_target_missing"}
            target = Path(value).expanduser()
            index += 1
            continue
        return None, {"code": "setup_argument_unknown", "argument": argument}
    return target, None


def install_skill(argv: list[str], *, _lock_held: bool = False) -> int:
    """Install/update the Skill and finish one project-local dependency setup pass."""

    host = windows_host_compatibility()
    if not host["compatible"]:
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "unsupported_windows_host",
                    "message": "EditaPlot requires Windows 10/11 x64 on AMD64/x86_64.",
                    "host": host,
                },
            },
            stream=sys.stderr,
        )
        return 3
    target, argument_error = _parse_setup_target(argv)
    if argument_error is not None:
        _emit({"ok": False, "error": argument_error}, stream=sys.stderr)
        return 2
    if target is None:
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
        target = codex_home / "skills" / "editaplot"
    if target.is_symlink():
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "skill_destination_symlink_rejected",
                    "target": str(target),
                },
            },
            stream=sys.stderr,
        )
        return 2
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not _lock_held:
        lock_path = target.parent / f".{target.name}.editaplot-setup.lock"
        try:
            with _exclusive_file_lock(lock_path, error_code="skill_setup_in_progress"):
                return install_skill(["--target", str(target)], _lock_held=True)
        except RuntimeError as exc:
            _emit(
                {
                    "ok": False,
                    "error": {
                        "code": str(exc),
                        "message": "Another EditaPlot setup is already using this target.",
                        "target": str(target),
                    },
                },
                stream=sys.stderr,
            )
            return 4
    _recover_install_swap(target)
    source_root = SKILL_ROOT.resolve()
    same_as_source = target == source_root
    try:
        target_is_source_child = not same_as_source and target.is_relative_to(source_root)
    except ValueError:  # pragma: no cover - different Windows drives
        target_is_source_child = False
    if target_is_source_child:
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "skill_destination_inside_source_rejected",
                    "message": "The setup target cannot be a child directory of the source Skill.",
                    "target": str(target),
                },
            },
            stream=sys.stderr,
        )
        return 2
    if target.exists() and not target.is_dir():
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "skill_destination_not_directory",
                    "target": str(target),
                },
            },
            stream=sys.stderr,
        )
        return 2
    target_nonempty = target.exists() and any(target.iterdir())
    recognized_target = same_as_source or (target_nonempty and _is_recognized_editaplot_skill(target))
    if target_nonempty and not recognized_target:
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "skill_destination_not_editaplot",
                    "message": (
                        "Refusing to overwrite a non-empty directory that is not a recognized "
                        "EditaPlot Skill. Choose an empty target."
                    ),
                    "target": str(target),
                },
            },
            stream=sys.stderr,
        )
        return 2
    engine_root, _config = _resolve_engine([])
    if engine_root is None:
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "engine_not_found",
                    "message": "The EditaPlot runtime was not found; the existing Skill was unchanged.",
                    "target": str(target),
                },
            },
            stream=sys.stderr,
        )
        return 3
    discovery = discover_python(engine_root)
    selected = discovery["selected"]
    if selected is None:
        _emit(
            {
                "ok": False,
                "error": {
                    "code": "compatible_python_not_found",
                    "message": "Install 64-bit CPython 3.10-3.12, then run setup again.",
                },
                "target": str(target),
                "python_discovery": discovery,
            },
            stream=sys.stderr,
        )
        return 3

    local_config = {
        "schema_version": "1.0",
        "engine_home": str(engine_root),
        "generated_by": "EditaPlot setup",
    }
    copied = 0
    staging: Path | None = None
    if not same_as_source:
        staging = _next_install_sibling(target, "build")
        staging.mkdir()
        _write_install_state(staging, target=target, kind="build")
        try:
            copied = _copy_tree_without_deleting(SKILL_ROOT, staging)
            repository = _repository_root()
            launcher_source = (
                repository / "editaplot.cmd"
                if repository is not None
                else SKILL_ROOT / "editaplot.cmd"
            )
            launcher_target = staging / "editaplot.cmd"
            if launcher_source.is_file() and launcher_source.resolve() != launcher_target.resolve():
                shutil.copy2(str(launcher_source), str(launcher_target))
                copied += 1
            (staging / LOCAL_CONFIG_NAME).write_text(
                json.dumps(local_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if not _is_recognized_editaplot_skill(staging):
                raise OSError("staged Skill failed its identity check")
        except BaseException:
            if staging.exists() or staging.is_symlink():
                _remove_install_sibling(target, staging, "build")
            raise

    environment = os.environ.copy()
    environment["EDITAPLOT_ENGINE_HOME"] = str(engine_root)
    environment["EDITAPLOT_BOOTSTRAP_SOURCE"] = str(selected["source"])
    current_compatibility = python_compatibility()
    repair_python = (
        str(Path(sys.executable).resolve())
        if current_compatibility["compatible"]
        else str(selected["executable"])
    )
    backup: Path | None = None
    skill_swap_committed = same_as_source
    if same_as_source:
        temporary_config = target / f"{LOCAL_CONFIG_NAME}.tmp-{os.getpid()}"
        temporary_config.write_text(
            json.dumps(local_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_config, target / LOCAL_CONFIG_NAME)
    else:
        if staging is None:  # pragma: no cover - guarded by the same_as_source branch
            raise RuntimeError("missing Skill staging directory")
        try:
            if target.exists():
                backup = _next_install_sibling(target, "backup")
            _write_install_journal(target, backup, engine_root, staging)
            if backup is not None:
                os.replace(target, backup)
            os.replace(staging, target)
            skill_swap_committed = True
        except BaseException:
            if backup is not None and (backup.exists() or backup.is_symlink()):
                if target.exists() or target.is_symlink():
                    if not (staging.exists() or staging.is_symlink()):
                        os.replace(target, staging)
                os.replace(backup, target)
            elif (target.exists() or target.is_symlink()) and not (
                staging.exists() or staging.is_symlink()
            ):
                os.replace(target, staging)
            if staging.exists() or staging.is_symlink():
                _remove_install_sibling(target, staging, "build")
            _install_journal(target).unlink(missing_ok=True)
            raise

    target_cli = target / "scripts" / "editaplot.py"
    repair_code, repair_payload = _run_json_command(
        [
            repair_python,
            str(target_cli),
            "repair-environment",
            "--engine-home",
            str(engine_root),
        ],
        environment=environment,
    )
    if repair_code != 0:
        if not same_as_source and skill_swap_committed:
            rollback = _next_install_sibling(target, "build")
            os.replace(target, rollback)
            if backup is not None and (backup.exists() or backup.is_symlink()):
                os.replace(backup, target)
            _remove_install_sibling(target, rollback, "build")
            _install_journal(target).unlink(missing_ok=True)
        _emit(
            {
                "ok": False,
                "status": (
                    "setup_repair_failed_previous_skill_restored"
                    if target_nonempty
                    else "setup_repair_failed_fresh_install_removed"
                ),
                "target": str(target),
                "repair": repair_payload,
                "origin_installation_modified": False,
            },
            stream=sys.stderr,
        )
        return repair_code

    managed_status = managed_environment_status(engine_root)
    target_lock_sha256 = _skill_dependency_lock_sha(target)
    environment_committed = bool(
        managed_status["valid"]
        and target_lock_sha256
        and managed_status.get("dependency_lock_sha256") == target_lock_sha256
    )
    if environment_committed:
        post_python = str(managed_status["python_executable"])
        doctor_code, doctor_payload = _run_json_command(
            [
                post_python,
                str(target_cli),
                "doctor",
                "--engine-home",
                str(engine_root),
            ],
            environment=environment,
            timeout=120,
        )
        environment_ready = bool(doctor_code == 0 and doctor_payload.get("ready_for_analysis"))
    else:
        transaction_recovery = (
            _recover_install_swap(target) if not same_as_source else "same_as_source_not_swapped"
        )
        doctor_code = 3
        doctor_payload = {
            "ok": False,
            "error": {
                "code": "managed_environment_invalid_after_repair",
                "managed_environment_status": managed_status,
                "target_dependency_lock_sha256": target_lock_sha256,
                "transaction_recovery": transaction_recovery,
            },
        }
        environment_ready = False

    if environment_committed and not same_as_source:
        (target / INSTALL_STATE_NAME).unlink(missing_ok=True)
        if backup is not None and (backup.exists() or backup.is_symlink()):
            _remove_install_sibling(target, backup, "backup")
        _install_journal(target).unlink(missing_ok=True)

    installed_status = (
        "already_installed" if same_as_source else "updated" if target_nonempty else "installed"
    )
    payload = {
        "ok": environment_ready,
        "status": f"{installed_status}_and_environment_ready" if environment_ready else installed_status,
        "target": str(target),
        "copied_files": copied,
        "local_config": str(target / LOCAL_CONFIG_NAME),
        "selected_python": selected,
        "repair": repair_payload,
        "post_repair_doctor": doctor_payload,
        "ready_for_analysis": bool(doctor_payload.get("ready_for_analysis")),
        "ready_for_render": bool(doctor_payload.get("ready_for_render")),
        "origin_installation_modified": False,
        "manual_origin_launch_confirmation": "required_before_render",
        "next_step": (
            "Confirm licensed Origin starts manually, then submit a data file."
            if doctor_payload.get("ready_for_render")
            else "Follow post_repair_doctor.manual_blockers, then run editaplot.cmd doctor."
        ),
    }
    _emit(payload, stream=sys.stdout if environment_ready else sys.stderr)
    return 0 if environment_ready else 3


def main(argv: list[str] | None = None) -> int:
    arguments = _normalize_cli_arguments(list(sys.argv[1:] if argv is None else argv))
    if arguments and arguments[0] in {"setup", "install-skill"}:
        return install_skill(arguments[1:])

    engine_root, config = _resolve_engine(arguments)
    discovery = discover_python(engine_root)
    diagnostic = {
        "schema_version": "1.0",
        "ok": bool(discovery["selected"] and discovery["host"]["compatible"]),
        "platform": platform.platform(),
        "windows_supported": discovery["host"]["compatible"],
        "macos_supported": False,
        "engine_home": str(engine_root) if engine_root is not None else None,
        "local_config": config,
        **discovery,
    }
    if arguments == ["--diagnose"]:
        _emit(diagnostic)
        return 0 if diagnostic["ok"] else 3
    selected = discovery["selected"]
    if selected is None:
        _emit(
            {
                **diagnostic,
                "error": {
                    "code": "compatible_python_not_found"
                    if discovery["host"]["compatible"]
                    else "unsupported_windows_host",
                    "message": (
                        "Install 64-bit CPython 3.10-3.12, or set EDITAPLOT_PYTHON to it."
                        if discovery["host"]["compatible"]
                        else "EditaPlot requires Windows 10/11 x64 on AMD64/x86_64."
                    ),
                },
            },
            stream=sys.stderr,
        )
        return 3

    cli = SCRIPT_DIRECTORY / "editaplot.py"
    cli_arguments = arguments or ["doctor"]
    environment = os.environ.copy()
    if engine_root is not None:
        environment["EDITAPLOT_ENGINE_HOME"] = str(engine_root)
    environment["EDITAPLOT_BOOTSTRAP_SOURCE"] = str(selected["source"])
    completed = subprocess.run(  # noqa: S603 - selected absolute Python and fixed local CLI
        [str(selected["executable"]), str(cli), *cli_arguments],
        cwd=os.getcwd(),
        env=environment,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
