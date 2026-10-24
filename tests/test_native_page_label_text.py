from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/src"))

from origin_sciplot.origin_backend import evidence_renderer  # noqa: E402
from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402


@pytest.mark.parametrize("actual", ["Sensor 1\nRegion A", "Sensor 1\r\nRegion A"])
def test_page_label_allows_native_crlf_but_keeps_raw_readback(actual):
    assert evidence_renderer._verify_page_label_text(actual, "Sensor 1\nRegion A", "Channel1") == actual


@pytest.mark.parametrize("actual", ["A B", "A\n\nB", " A\nB", "A\nB ", "A\rB", "B\nA"])
def test_page_label_still_rejects_changed_text_spacing_or_line_structure(actual):
    with pytest.raises(OriginDrawError, match="Channel1"):
        evidence_renderer._verify_page_label_text(actual, "A\nB", "Channel1")


def test_page_label_does_not_normalize_scientific_symbols():
    with pytest.raises(OriginDrawError):
        evidence_renderer._verify_page_label_text("Power (μV2)", "Power (µV²)", "PowerLabel")
