from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import editaplot_core as core  # noqa: E402, I001


UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


class _FakeKey:
    def __init__(self, root: str, subkey: str, view: int) -> None:
        self.root = root
        self.subkey = subkey
        self.view = view

    def __enter__(self) -> _FakeKey:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeWinreg:
    KEY_READ = 1
    KEY_WOW64_32KEY = 2
    KEY_WOW64_64KEY = 4
    HKEY_CLASSES_ROOT = "HKCR"
    HKEY_LOCAL_MACHINE = "HKLM"
    HKEY_CURRENT_USER = "HKCU"

    def __init__(self) -> None:
        self.values: dict[tuple[str, str, int, str | None], str] = {}
        self.subkeys: dict[tuple[str, str, int], list[str]] = {}

    def module(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            KEY_READ=self.KEY_READ,
            KEY_WOW64_32KEY=self.KEY_WOW64_32KEY,
            KEY_WOW64_64KEY=self.KEY_WOW64_64KEY,
            HKEY_CLASSES_ROOT=self.HKEY_CLASSES_ROOT,
            HKEY_LOCAL_MACHINE=self.HKEY_LOCAL_MACHINE,
            HKEY_CURRENT_USER=self.HKEY_CURRENT_USER,
            OpenKey=self.open_key,
            QueryValueEx=self.query_value,
            QueryInfoKey=self.query_info,
            EnumKey=self.enum_key,
        )

    def open_key(
        self,
        root: str,
        subkey: str,
        _reserved: int,
        access: int,
    ) -> _FakeKey:
        view = access & (self.KEY_WOW64_32KEY | self.KEY_WOW64_64KEY)
        has_value = any(
            item_root == root and item_subkey == subkey and item_view == view
            for item_root, item_subkey, item_view, _name in self.values
        )
        has_subkeys = (root, subkey, view) in self.subkeys
        if not has_value and not has_subkeys:
            raise FileNotFoundError(subkey)
        return _FakeKey(root, subkey, view)

    def query_value(self, key: _FakeKey, name: str | None) -> tuple[str, int]:
        try:
            return self.values[(key.root, key.subkey, key.view, name)], 1
        except KeyError as exc:
            raise FileNotFoundError(key.subkey) from exc

    def query_info(self, key: _FakeKey) -> tuple[int, int, int]:
        return len(self.subkeys.get((key.root, key.subkey, key.view), [])), 0, 0

    def enum_key(self, key: _FakeKey, index: int) -> str:
        return self.subkeys[(key.root, key.subkey, key.view)][index]

    def add_com(
        self,
        *,
        progid: str,
        clsid: str,
        executable: Path | None,
        progid_view: int = 0,
        server_view: int = KEY_WOW64_32KEY,
        command: str | None = None,
    ) -> None:
        self.values[
            (self.HKEY_CLASSES_ROOT, rf"{progid}\CLSID", progid_view, None)
        ] = clsid
        if executable is not None or command is not None:
            server = command if command is not None else f'"{executable}" /Automation'
            self.values[
                (
                    self.HKEY_CLASSES_ROOT,
                    rf"CLSID\{clsid}\LocalServer32",
                    server_view,
                    None,
                )
            ] = str(server)

    def add_install(
        self,
        *,
        key_name: str,
        display_name: str,
        display_version: str,
        executable: Path,
        hive: str = HKEY_LOCAL_MACHINE,
        view: int = KEY_WOW64_32KEY,
    ) -> None:
        self.subkeys.setdefault((hive, UNINSTALL_KEY, view), []).append(key_name)
        product_key = rf"{UNINSTALL_KEY}\{key_name}"
        self.values[(hive, product_key, view, "DisplayName")] = display_name
        self.values[(hive, product_key, view, "DisplayVersion")] = display_version
        self.values[(hive, product_key, view, "DisplayIcon")] = f'"{executable}",0'
        self.values[(hive, product_key, view, "InstallLocation")] = str(executable.parent)


def _install_fake_registry(
    monkeypatch: pytest.MonkeyPatch,
    registry: FakeWinreg,
) -> None:
    monkeypatch.setitem(sys.modules, "winreg", registry.module())
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")


def _origin_executable(tmp_path: Path, version: str) -> Path:
    executable = tmp_path / version / "Origin64.exe"
    executable.parent.mkdir()
    executable.touch()
    return executable


def _prepare_doctor_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    versions = {
        {"yaml": "PyYAML", "PIL": "pillow"}.get(module, module): spec.partition("==")[2]
        for module, spec in core.RUNTIME_DEPENDENCIES
    }
    monkeypatch.setattr(
        core,
        "windows_host_compatibility",
        lambda **_kwargs: {
            "compatible": True,
            "machine": "AMD64",
            "windows_major": 11,
            "required": "Windows 10/11 x64",
            "reasons": [],
        },
    )
    monkeypatch.setattr(core.platform, "platform", lambda: "Windows-11-AMD64")
    monkeypatch.setattr(
        core,
        "python_compatibility",
        lambda **_kwargs: {
            "compatible": True,
            "implementation": "CPython",
            "architecture_bits": 64,
            "required": "64-bit CPython >=3.10,<3.13",
            "reasons": [],
        },
    )
    monkeypatch.setattr(core, "bootstrap_engine", lambda _root: tmp_path)
    monkeypatch.setattr(
        core,
        "managed_environment_status",
        lambda _root: {"exists": False, "valid": False, "reason": "not_created"},
    )
    monkeypatch.setattr(core.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(core.importlib_metadata, "version", lambda name: versions[name])


def _registration_by_role(result: dict[str, Any], role: str) -> dict[str, Any]:
    return next(item for item in result["registrations"] if item["role"] == role)


def test_discovers_both_origin_progids_and_keeps_launch_as_legacy_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _origin_executable(tmp_path, "Origin2024b")
    registry = FakeWinreg()
    registry.add_com(
        progid="Origin.Application",
        clsid="{LAUNCH}",
        executable=executable,
    )
    registry.add_com(
        progid="Origin.ApplicationSI",
        clsid="{ATTACH}",
        executable=executable,
    )
    _install_fake_registry(monkeypatch, registry)

    result = core.discover_origin_application()

    assert result["application_present"] is True
    assert result["path"] == str(executable.resolve())
    assert result["progid"] == "Origin.Application"
    assert result["clsid"] == "{LAUNCH}"
    assert result["registry_view"] == "32-bit registry view"
    assert result["callability_status"] == "registration_detected"
    assert result["registration_detected"] is True
    assert result["launch_registration_detected"] is True
    assert result["attach_registration_detected"] is True
    assert result["preferred_connection_mode"] == "launch_isolated"
    assert result["live_connection_tested"] is False
    assert result["live_connection_status"] == "not_tested"
    assert _registration_by_role(result, "launch_isolated")["progid"] == "Origin.Application"
    assert _registration_by_role(result, "attach_existing")["progid"] == "Origin.ApplicationSI"


def test_discovers_launch_registration_without_attach_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _origin_executable(tmp_path, "Origin2022")
    registry = FakeWinreg()
    registry.add_com(
        progid="Origin.Application",
        clsid="{LAUNCH-ONLY}",
        executable=executable,
    )
    _install_fake_registry(monkeypatch, registry)

    result = core.discover_origin_application()

    assert result["application_present"] is True
    assert result["registration_detected"] is True
    assert result["launch_registration_detected"] is True
    assert result["attach_registration_detected"] is False
    assert result["callability_status"] == "registration_detected"


def test_discovery_tolerates_minimal_fake_winreg_without_uninstall_hives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _origin_executable(tmp_path, "Origin2023")
    clsid = "{MINIMAL-WINREG}"

    class MinimalKey:
        def __init__(self, subkey: str, access: int) -> None:
            self.subkey = subkey
            self.access = access

        def __enter__(self) -> MinimalKey:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def open_key(_root: object, subkey: str, _reserved: int, access: int) -> MinimalKey:
        return MinimalKey(subkey, access)

    def query_value(key: MinimalKey, _name: object) -> tuple[str, int]:
        if key.subkey == r"Origin.Application\CLSID":
            return clsid, 1
        if key.subkey == rf"CLSID\{clsid}\LocalServer32" and key.access & 2:
            return f'"{executable}" /Automation', 1
        raise FileNotFoundError(key.subkey)

    minimal_winreg = types.SimpleNamespace(
        HKEY_CLASSES_ROOT=object(),
        KEY_READ=1,
        KEY_WOW64_32KEY=2,
        KEY_WOW64_64KEY=4,
        OpenKey=open_key,
        QueryValueEx=query_value,
    )
    monkeypatch.setitem(sys.modules, "winreg", minimal_winreg)
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")

    result = core.discover_origin_application()

    assert result["application_present"] is True
    assert result["installed_candidates"] == []
    assert result["multiple_installations_detected"] is False


def test_attach_only_registration_is_not_ready_for_isolated_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _origin_executable(tmp_path, "Origin2021")
    registry = FakeWinreg()
    registry.add_com(
        progid="Origin.ApplicationSI",
        clsid="{ATTACH-ONLY}",
        executable=executable,
    )
    _install_fake_registry(monkeypatch, registry)
    _prepare_doctor_dependencies(monkeypatch, tmp_path)

    discovery = core.discover_origin_application()
    report = core.doctor(engine_home=tmp_path)

    assert discovery["registration_detected"] is True
    assert discovery["application_present"] is False
    assert discovery["path"] is None
    assert discovery["progid"] == "Origin.Application"
    assert discovery["launch_registration_detected"] is False
    assert discovery["attach_registration_detected"] is True
    assert discovery["reason"] == "origin_isolated_registration_missing"
    assert report["schema_version"] == "1.0"
    assert report["ready_for_analysis"] is True
    assert report["ready_for_render"] is False
    assert "origin_isolated_registration_missing" in report["manual_blockers"]


def test_damaged_localserver_does_not_count_as_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeWinreg()
    missing = tmp_path / "missing" / "Origin64.exe"
    registry.add_com(
        progid="Origin.Application",
        clsid="{BROKEN}",
        executable=None,
        command=f'"{missing}" /Automation',
    )
    _install_fake_registry(monkeypatch, registry)

    result = core.discover_origin_application()
    launch = _registration_by_role(result, "launch_isolated")

    assert result["application_present"] is False
    assert result["registration_detected"] is False
    assert result["callability_status"] == "not_detected"
    assert launch["clsid"] == "{BROKEN}"
    assert launch["reason"] == "registered_origin64_executable_missing"


def test_multiple_installs_are_inventory_only_and_active_registration_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = _origin_executable(tmp_path, "Origin2022")
    newer_not_registered = _origin_executable(tmp_path, "Origin2025b")
    registry = FakeWinreg()
    registry.add_com(
        progid="Origin.Application",
        clsid="{ACTIVE-LAUNCH}",
        executable=active,
    )
    registry.add_com(
        progid="Origin.ApplicationSI",
        clsid="{ACTIVE-ATTACH}",
        executable=active,
    )
    registry.add_install(
        key_name="{ORIGIN-2022}",
        display_name="Origin2022",
        display_version="9.9.0",
        executable=active,
    )
    registry.add_install(
        key_name="{ORIGIN-2025B}",
        display_name="Origin2025b",
        display_version="10.25.0",
        executable=newer_not_registered,
    )
    _install_fake_registry(monkeypatch, registry)

    result = core.discover_origin_application()

    assert result["multiple_installations_detected"] is True
    assert len(result["installed_candidates"]) == 2
    assert result["path"] == str(active.resolve())
    assert result["installed_candidates"][0]["path"] == str(active.resolve())
    assert result["installed_candidates"][0]["active_registration"] is True
    assert result["installed_candidates"][0]["active_registration_roles"] == [
        "launch_isolated",
        "attach_existing",
    ]
    inactive = next(
        item
        for item in result["installed_candidates"]
        if item["path"] == str(newer_not_registered.resolve())
    )
    assert inactive["active_registration"] is False


def test_doctor_reports_originpro_and_originext_without_live_success_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _origin_executable(tmp_path, "Origin2024b")
    registry = FakeWinreg()
    registry.add_com(
        progid="Origin.Application",
        clsid="{LAUNCH}",
        executable=executable,
    )
    _install_fake_registry(monkeypatch, registry)
    _prepare_doctor_dependencies(monkeypatch, tmp_path)

    report = core.doctor(engine_home=tmp_path)
    checks = {item["name"]: item for item in report["checks"]}

    assert report["ready_for_render"] is True
    assert report["origin_application"]["live_connection_tested"] is False
    assert report["origin_application"]["live_connection_status"] == "not_tested"
    assert report["origin_callability_check"] == "performed_during_render"
    assert checks["origin_application"]["callability_status"] == "registration_detected"
    assert checks["origin_application"]["live_connection_tested"] is False
    assert checks["python_dependency:originpro"]["required"] == "1.1.15"
    assert checks["python_dependency:OriginExt"]["required"] == "1.2.5"
    serialized_statuses = {
        str(report["origin_application"]["callability_status"]),
        str(report["origin_application"]["live_connection_status"]),
    }
    assert "connected" not in serialized_statuses
    assert "success" not in serialized_statuses


def test_runtime_repair_dependency_list_explicitly_includes_origin_binary_pair() -> None:
    requirements = dict(core.RUNTIME_DEPENDENCIES)

    assert requirements["originpro"] == "originpro==1.1.15"
    assert requirements["OriginExt"] == "OriginExt==1.2.5"
