from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "runtime" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from origin_sciplot.origin_backend.capabilities import parse_origin_version  # noqa: E402
from origin_sciplot.origin_backend.version_risks import (  # noqa: E402
    BuildMatch,
    ProbePriority,
    known_version_risks,
)


def _risks(version: str):
    return {
        risk.risk_id: risk
        for risk in known_version_risks(parse_origin_version(version))
    }


@pytest.mark.parametrize(
    ("version", "expected_match", "expected_priority"),
    [
        ("9.850201", BuildMatch.KNOWN_AFFECTED, ProbePriority.HIGH),
        ("9.850204", BuildMatch.KNOWN_AFFECTED, ProbePriority.HIGH),
        ("9.850212", BuildMatch.KNOWN_FIXED, ProbePriority.NORMAL),
        ("9.850299", BuildMatch.UNKNOWN, ProbePriority.HIGH),
        ("9.85", BuildMatch.UNKNOWN, ProbePriority.HIGH),
    ],
)
def test_2021b_attach_build_evidence_is_conservative(
    version: str,
    expected_match: BuildMatch,
    expected_priority: ProbePriority,
) -> None:
    risk = _risks(version)["origin_2021b_attach_lifecycle"]

    assert risk.build_match is expected_match
    assert risk.probe_priority is expected_priority
    assert risk.probe_ids == ("attach_existing_lifecycle",)


@pytest.mark.parametrize(
    ("version", "expected_match"),
    [
        ("10.050153", BuildMatch.KNOWN_AFFECTED),
        ("10.050156", BuildMatch.KNOWN_FIXED),
        ("10.050160", BuildMatch.UNKNOWN),
        ("10.05", BuildMatch.UNKNOWN),
    ],
)
def test_2023b_error_bar_build_evidence_is_exact_only(
    version: str,
    expected_match: BuildMatch,
) -> None:
    risk = _risks(version)["origin_2023b_error_bar_visibility"]

    assert risk.build_match is expected_match
    assert risk.evidence_scope == "build"
    assert risk.probe_ids == ("error_bar_render", "categorical_tick_dataset")


def test_2025b_combines_product_and_build_scoped_advisories() -> None:
    risks = _risks("10.2502122")

    defaults = risks["origin_2025b_graph_defaults"]
    assert defaults.build_match is BuildMatch.PRODUCT
    assert defaults.evidence_scope == "product"
    assert defaults.probe_priority is ProbePriority.HIGH

    y2_title = risks["origin_2025b_secondary_y_title"]
    assert y2_title.build_match is BuildMatch.KNOWN_AFFECTED
    assert y2_title.probe_ids == ("secondary_y_title",)

    assert "origin_2025_2026_label_geometry" in risks


def test_2025b_known_sr1_y2_fix_still_recommends_a_probe() -> None:
    risk = _risks("10.250234")["origin_2025b_secondary_y_title"]

    assert risk.build_match is BuildMatch.KNOWN_FIXED
    assert risk.probe_priority is ProbePriority.NORMAL
    assert risk.probe_ids == ("secondary_y_title",)


@pytest.mark.parametrize("version", ["10.20", "10.25", "10.30"])
def test_label_geometry_advisory_covers_2025_through_2026(version: str) -> None:
    risk = _risks(version)["origin_2025_2026_label_geometry"]

    assert risk.build_match is BuildMatch.PRODUCT
    assert risk.probe_ids == ("label_geometry",)


def test_2026_adds_categorical_tick_probe() -> None:
    risks = _risks("10.300197")

    assert risks["origin_2026_categorical_ticks"].probe_ids == (
        "categorical_tick_dataset",
    )
    assert "origin_2025_2026_label_geometry" in risks


@pytest.mark.parametrize(
    ("version", "expected_match"),
    [
        ("10.3502223", BuildMatch.KNOWN_AFFECTED),
        ("10.3502300", BuildMatch.UNKNOWN),
        ("10.35", BuildMatch.UNKNOWN),
    ],
)
def test_2026b_reference_rescale_unknown_builds_remain_unknown(
    version: str,
    expected_match: BuildMatch,
) -> None:
    risk = _risks(version)["origin_2026b_reference_rescale"]

    assert risk.build_match is expected_match
    assert risk.probe_priority is ProbePriority.HIGH
    assert risk.probe_ids == (
        "reference_line_rescale",
        "bland_altman_axis_limits",
    )


def test_reports_are_json_safe_and_explicitly_non_blocking() -> None:
    risk = _risks("10.2502122")["origin_2025b_secondary_y_title"]

    assert risk.to_dict() == {
        "risk_id": "origin_2025b_secondary_y_title",
        "summary": risk.summary,
        "origin_product": "2025b",
        "origin_numeric": 10.25,
        "evidence_scope": "build",
        "build_match": "known_affected",
        "probe_priority": "high",
        "probe_ids": ["secondary_y_title"],
        "blocks_render": False,
    }


def test_unrelated_or_future_products_have_no_known_advisories() -> None:
    assert known_version_risks(parse_origin_version("10.15")) == ()
    assert known_version_risks(parse_origin_version("10.40")) == ()
