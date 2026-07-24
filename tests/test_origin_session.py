from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend import session as session_module  # noqa: E402
from origin_sciplot.origin_backend.capabilities import (  # noqa: E402
    ConnectionMode,
    SessionOwnership,
)
from origin_sciplot.origin_backend.safe_errors import OriginEnvironmentError  # noqa: E402
from origin_sciplot.origin_backend.session import OriginSession  # noqa: E402


def test_default_session_launches_and_owns_an_isolated_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_float=lambda name: events.append(("read", name)) or 10.15,
        new=lambda **kwargs: events.append(("new", kwargs)),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)
    monkeypatch.setattr(
        session_module.metadata,
        "version",
        lambda name: {"originpro": "1.1.15", "OriginExt": "1.2.5"}[name],
    )

    with OriginSession(keep_open=False) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        assert environment.origin_version == "10.15"
        assert environment.originpro_version == "1.1.15"
        assert environment.originext_version == "1.2.5"
        assert environment.connection_mode is ConnectionMode.NEW_ISOLATED
        assert environment.ownership is SessionOwnership.EDITAPLOT
        assert environment.origin_version_info.product_label == "2024b"
        assert environment.python_version
        assert environment.python_architecture_bits in {32, 64}
        assert environment.to_dict() == {
            "origin_version": "10.15",
            "origin_version_raw": 10.15,
            "origin_product": "2024b",
            "origin_compatibility_status": "verified",
            "origin_supported_by_originpro": True,
            "origin_verified_baseline": True,
            "originpro_version": "1.1.15",
            "originext_version": "1.2.5",
            "python_version": environment.python_version,
            "python_architecture_bits": environment.python_architecture_bits,
            "connection_mode": "new_isolated",
            "session_ownership": "editaplot",
        }

    assert events == [
        ("show", False),
        ("read", "@V"),
        ("new", {"asksave": False}),
        "exit",
    ]


def test_attach_mode_never_hides_resets_or_closes_user_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        attach=lambda: events.append("attach"),
        lt_float=lambda name: events.append(("read", name)) or 10.25,
        detach=lambda: events.append("detach"),
        set_show=lambda show: events.append(("unexpected_show", show)),
        new=lambda **kwargs: events.append(("unexpected_new", kwargs)),
        exit=lambda: events.append("unexpected_exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with OriginSession(
        keep_open=False,
        connection_mode=ConnectionMode.ATTACH_EXISTING,
    ) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        assert environment.connection_mode is ConnectionMode.ATTACH_EXISTING
        assert environment.ownership is SessionOwnership.USER
        assert environment.origin_version_info.product_label == "2025b"

    assert events == ["attach", ("read", "@V"), "detach"]


def test_session_preserves_build_suffixed_origin_version_in_environment_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda _show: None,
        lt_float=lambda _name: 10.150132000000001,
        new=lambda **_kwargs: None,
        exit=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with OriginSession(keep_open=False) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        report = environment.to_dict()

    assert report["origin_version"] == "10.15"
    assert report["origin_version_raw"] == pytest.approx(10.150132)
    assert report["origin_product"] == "2024b"
    assert report["origin_compatibility_status"] == "verified"


def test_keep_open_restores_owned_window_after_early_drawing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_float=lambda _name: 10.15,
        new=lambda **_kwargs: events.append("new"),
        exit=lambda: events.append("unexpected_exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(LookupError, match="drawing failed"):
        with OriginSession(keep_open=True):
            raise LookupError("drawing failed")

    assert events == [("show", False), "new", ("show", True)]


def test_start_failure_has_stable_redacted_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visibility: list[bool] = []

    def set_show(show: bool) -> None:
        visibility.append(show)
        if not show:
            private_path = "\\".join(
                (f"{chr(67)}:", "private", "installation", "origin.exe")
            )
            raise RuntimeError(private_path)

    fake_originpro = SimpleNamespace(oext=True, set_show=set_show)
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession().__enter__()

    assert str(raised.value) == "Origin Automation connection failed"
    assert raised.value.code == "origin_instance_start_failed"
    assert raised.value.stage == "create_instance"
    assert "private" not in str(raised.value)
    assert visibility == [False, True]


def test_version_is_read_before_project_initialization_and_rejects_pre_2021(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda show: events.append(("show", show)),
        lt_float=lambda name: events.append(("read", name)) or 9.70,
        new=lambda **kwargs: events.append(("unexpected_new", kwargs)),
        exit=lambda: events.append("exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession(keep_open=False).__enter__()

    assert raised.value.code == "origin_version_unsupported"
    assert raised.value.stage == "validate_version"
    assert str(raised.value) == "Origin 2021 or later is required"
    assert events == [("show", False), ("read", "@V"), "exit"]


def test_attached_version_failure_detaches_without_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def fail_version(_name: str) -> float:
        raise RuntimeError("local COM details")

    fake_originpro = SimpleNamespace(
        oext=True,
        attach=lambda: events.append("attach"),
        lt_float=fail_version,
        detach=lambda: events.append("detach"),
        exit=lambda: events.append("unexpected_exit"),
    )
    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)

    with pytest.raises(OriginEnvironmentError) as raised:
        OriginSession(connection_mode="attach_existing").__enter__()

    assert raised.value.code == "origin_version_read_failed"
    assert raised.value.stage == "read_version"
    assert events == ["attach", "detach"]


def test_broken_package_metadata_never_breaks_live_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_originpro = SimpleNamespace(
        oext=True,
        set_show=lambda _show: None,
        lt_float=lambda _name: 9.80,
        new=lambda **_kwargs: None,
        exit=lambda: None,
    )

    def fail_metadata(_name: str) -> str:
        raise RuntimeError("broken package metadata")

    monkeypatch.setitem(sys.modules, "originpro", fake_originpro)
    monkeypatch.setattr(session_module.metadata, "version", fail_metadata)

    with OriginSession(keep_open=False) as origin_session:
        environment = origin_session.environment
        assert environment is not None
        assert environment.originpro_version == "unknown"
        assert environment.originext_version == "unknown"
        assert environment.origin_version_info.product_label == "2021"
