"""Axis-title attachment compatibility tests.

Origin's general text-object contract defines ``attach=0`` as layer-frame
coordinates, ``attach=1`` as page coordinates, and ``attach=2`` as axis-scale
coordinates.  Special axis-title objects such as XB, YL, and YR can normalize
to mode 2 after a graph refresh even when page attachment was requested.

For these special objects, the final physical ``left/top/width/height``
readback is therefore the clipping authority; attachment is recorded and must
be one of the three documented modes, but is not forced to mode 1.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.origin_backend.scientific_renderer import (  # noqa: E402
    _title_geometry,
)

XPS_ADAPTIVE_RUNNER = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "templates"
    / "xps_adaptive"
    / "runner.py"
)
XPS_C1S_RUNNER = (
    Path(__file__).resolve().parents[1]
    / "runtime"
    / "templates"
    / "xps_c1s_fit"
    / "runner.py"
)


def _load_xps_adaptive_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_editaplot_test_xps_adaptive_runner",
        XPS_ADAPTIVE_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the adaptive XPS runner for testing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


XPS_ADAPTIVE = _load_xps_adaptive_runner()


def _load_xps_c1s_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_editaplot_test_xps_c1s_runner",
        XPS_C1S_RUNNER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the fixed C1s runner for testing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


XPS_C1S = _load_xps_c1s_runner()


class _FakeOrigin:
    def __init__(self, *, page_width: float = 1000.0, page_height: float = 800.0) -> None:
        self.values = {
            "page.width": page_width,
            "page.height": page_height,
        }

    def lt_float(self, name: str) -> float:
        return self.values[name]

    def lt_exec(self, _command: str) -> None:
        return None


class _FakeTitle:
    def __init__(
        self,
        *,
        attachment: int,
        left: float = 100.0,
        top: float = 120.0,
        width: float = 180.0,
        height: float = 45.0,
    ) -> None:
        self.attachment = attachment
        self.geometry = {
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }

    def get_int(self, name: str) -> int:
        assert name == "attach"
        return self.attachment

    def get_float(self, name: str) -> float:
        return self.geometry[name]

    def set_float(self, name: str, value: float) -> None:
        self.geometry[name] = value


@pytest.mark.parametrize("attachment", [0, 1, 2])
def test_axis_title_geometry_accepts_all_documented_attachment_modes(
    attachment: int,
) -> None:
    state = _title_geometry(
        _FakeOrigin(),
        {
            "x_title": _FakeTitle(attachment=attachment),
            "y_title": _FakeTitle(attachment=attachment, left=20.0, top=250.0),
        },
    )

    assert state["x_title.attach"] == float(attachment)
    assert state["y_title.attach"] == float(attachment)


def test_special_axis_titles_may_normalize_to_axes_scale_attachment() -> None:
    state = _title_geometry(
        _FakeOrigin(),
        {
            "x_title": _FakeTitle(attachment=2, left=380.0, top=720.0),
            "y_title": _FakeTitle(attachment=2, left=10.0, top=300.0),
            "y2_title": _FakeTitle(attachment=2, left=810.0, top=300.0),
        },
    )

    assert state["x_title.attach"] == 2.0
    assert state["y_title.attach"] == 2.0
    assert state["y2_title.attach"] == 2.0
    assert state["x_title.left"] == 380.0
    assert state["x_title.top"] == 720.0


def test_axis_title_geometry_rejects_unknown_attachment_mode() -> None:
    with pytest.raises(OriginDrawError, match="unknown attachment mode"):
        _title_geometry(
            _FakeOrigin(),
            {"x_title": _FakeTitle(attachment=3)},
        )


@pytest.mark.parametrize("attachment", [0, 1, 2])
def test_legal_attachment_does_not_bypass_physical_page_boundary_check(
    attachment: int,
) -> None:
    with pytest.raises(OriginDrawError, match="is clipped"):
        _title_geometry(
            _FakeOrigin(page_width=1000.0, page_height=800.0),
            {
                "x_title": _FakeTitle(
                    attachment=attachment,
                    left=900.0,
                    top=760.0,
                    width=180.0,
                    height=45.0,
                )
            },
        )


def _verified_xps_title_state() -> dict[str, float]:
    return {
        "page.width": 5270.0,
        "page.height": 3973.0,
        "x_title.attach": 2.0,
        "x_title.left": 2177.0,
        "x_title.top": 3639.0,
        "x_title.width": 2076.0,
        "x_title.height": 251.0,
        "y_title.attach": 2.0,
        "y_title.left": 60.0,
        "y_title.top": 1128.0,
        "y_title.width": 254.0,
        "y_title.height": 1260.0,
    }


def test_xps_title_gate_accepts_verified_tick_title_separation() -> None:
    XPS_ADAPTIVE._require_axis_titles_inside_page(  # noqa: SLF001
        _verified_xps_title_state()
    )


def test_xps_title_gate_rejects_visual_tick_title_overlap() -> None:
    state = _verified_xps_title_state()
    state["x_title.top"] = 3440.0

    with pytest.raises(OriginDrawError, match="overlap the 24 pt tick labels"):
        XPS_ADAPTIVE._require_axis_titles_inside_page(state)  # noqa: SLF001


def test_fixed_c1s_accepts_axes_scale_attachment_with_physical_bounds() -> None:
    state = XPS_C1S._position_axis_titles(  # noqa: SLF001
        _FakeOrigin(),
        _FakeTitle(attachment=2, left=380.0, top=750.0),
        _FakeTitle(attachment=2, left=20.0, top=250.0),
    )

    assert state["x_title.attach"] == 2.0
    assert state["y_title.attach"] == 2.0
    assert state["x_title.top"] == pytest.approx(726.0)


def test_fixed_c1s_rejects_unknown_attachment_mode() -> None:
    with pytest.raises(OriginDrawError, match="unknown attachment mode"):
        XPS_C1S._position_axis_titles(  # noqa: SLF001
            _FakeOrigin(),
            _FakeTitle(attachment=3, left=380.0, top=750.0),
            _FakeTitle(attachment=2, left=20.0, top=250.0),
        )


def test_fixed_c1s_rejects_clipped_title_even_with_legal_attachment() -> None:
    with pytest.raises(OriginDrawError, match="is clipped"):
        XPS_C1S._position_axis_titles(  # noqa: SLF001
            _FakeOrigin(),
            _FakeTitle(
                attachment=2,
                left=900.0,
                top=750.0,
                width=180.0,
            ),
            _FakeTitle(attachment=2, left=20.0, top=250.0),
        )


def test_fixed_c1s_rejects_visual_tick_title_overlap() -> None:
    with pytest.raises(OriginDrawError, match="overlap the 24 pt tick labels"):
        XPS_C1S._position_axis_titles(  # noqa: SLF001
            _FakeOrigin(),
            _FakeTitle(attachment=2, left=380.0, top=700.0),
            _FakeTitle(attachment=2, left=20.0, top=250.0),
        )
