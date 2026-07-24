from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.capabilities import (  # noqa: E402
    ConnectionMode,
    OriginVersionInfo,
    SessionOwnership,
    parse_origin_version,
)


@pytest.mark.parametrize(
    ("numeric", "product_label"),
    [
        (9.80, "2021"),
        ("9.85", "2021b"),
        (9.90, "2022"),
        ("9.95", "2022b"),
        (10.00, "2023"),
        ("10.05", "2023b"),
        (10.10, "2024"),
        ("10.15", "2024b"),
        (10.20, "2025"),
        ("10.25", "2025b"),
        (10.30, "2026"),
        ("10.35", "2026b"),
    ],
)
def test_parse_origin_version_maps_known_products(
    numeric: float | str,
    product_label: str,
) -> None:
    result = parse_origin_version(numeric)

    assert result.product_label == product_label
    assert result.supported_by_originpro is True
    assert result.compatibility_status in {"verified", "compatible_unverified"}


def test_origin_2024b_is_the_verified_baseline() -> None:
    result = parse_origin_version("10.1500")

    assert result.numeric == 10.15
    assert result.verified_baseline is True
    assert result.compatibility_status == "verified"


@pytest.mark.parametrize("numeric", [9.79, "9.70", 0])
def test_versions_before_origin_2021_are_unsupported(numeric: float | str) -> None:
    result = parse_origin_version(numeric)

    assert result.supported_by_originpro is False
    assert result.verified_baseline is False
    assert result.compatibility_status == "unsupported"


def test_other_supported_versions_remain_compatible_unverified() -> None:
    result = parse_origin_version(10.25)

    assert result.verified_baseline is False
    assert result.compatibility_status == "compatible_unverified"


def test_future_unknown_version_retains_its_numeric_value() -> None:
    result = parse_origin_version("10.40")

    assert result.numeric == 10.4
    assert result.product_label == "Unknown Origin (10.4)"
    assert result.supported_by_originpro is True
    assert result.compatibility_status == "compatible_unverified"


def test_origin_version_info_serializes_to_plain_values() -> None:
    result = parse_origin_version(10.15)

    assert result.to_dict() == {
        "numeric": 10.15,
        "product_label": "2024b",
        "supported_by_originpro": True,
        "verified_baseline": True,
        "compatibility_status": "verified",
        "raw_numeric": 10.15,
    }


def test_origin_version_info_is_frozen() -> None:
    result = parse_origin_version(10.15)

    with pytest.raises(FrozenInstanceError):
        result.numeric = 10.25  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", "not-a-version", "NaN", float("inf"), True])
def test_invalid_versions_are_rejected(value: float | str) -> None:
    with pytest.raises(ValueError, match="finite number"):
        parse_origin_version(value)


def test_connection_and_ownership_enums_have_stable_wire_values() -> None:
    assert ConnectionMode.NEW_ISOLATED.value == "new_isolated"
    assert ConnectionMode.ATTACH_EXISTING.value == "attach_existing"
    assert SessionOwnership.EDITAPLOT.value == "editaplot"
    assert SessionOwnership.USER.value == "user"


def test_origin_version_info_can_be_constructed_directly() -> None:
    value = OriginVersionInfo(
        numeric=9.8,
        product_label="2021",
        supported_by_originpro=True,
        verified_baseline=False,
        compatibility_status="compatible_unverified",
    )

    assert value.product_label == "2021"


def test_origin_build_suffix_is_truncated_to_public_product_version() -> None:
    result = parse_origin_version("10.150132000000001")

    assert result.numeric == 10.15
    assert result.raw_numeric == pytest.approx(10.150132)
    assert result.product_label == "2024b"
    assert result.verified_baseline is True
    assert result.compatibility_status == "verified"


def test_version_truncation_never_promotes_a_pre_2021_value() -> None:
    result = parse_origin_version("9.799999")

    assert result.numeric == 9.79
    assert result.supported_by_originpro is False
