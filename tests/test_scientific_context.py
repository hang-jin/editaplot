from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_context import (  # noqa: E402
    ScientificContextError,
    normalize_scientific_context,
)


def test_absent_context_preserves_existing_templates() -> None:
    assert normalize_scientific_context("existing_template") == ()


@pytest.mark.parametrize("template_id", ["event_response", "spatial_profile", "ratiometric_response", "old"])
@pytest.mark.parametrize("value", [None, {}, ()])
def test_empty_context_is_absent_without_completeness(template_id: str, value: object) -> None:
    assert normalize_scientific_context(template_id, value) == ()


@pytest.mark.parametrize(
    ("template_id", "value", "expected"),
    [
        (
            "event_response",
            {"response_unit": "mV", "interval_label": "  刺激 Ａ  ", "time_unit": "s"},
            (("interval_label", "  刺激 Ａ  "), ("response_unit", "mV"), ("time_unit", "s")),
        ),
        (
            "spatial_profile",
            {"profile_y": -0.0, "profile_x": 9007199254740993, "value_unit": "a.u.", "y_unit": "µm"},
            (("profile_x", 9007199254740993), ("profile_y", -0.0), ("value_unit", "a.u."), ("y_unit", "µm")),
        ),
        (
            "ratiometric_response",
            {
                "ratio_unit": "dimensionless",
                "numerator_unit": "mV",
                "denominator_unit": "mV",
                "ratio_definition": "F340 / F380",
                "x_unit": "s",
            },
            (
                ("denominator_unit", "mV"),
                ("numerator_unit", "mV"),
                ("ratio_definition", "F340 / F380"),
                ("ratio_unit", "dimensionless"),
                ("x_unit", "s"),
            ),
        ),
    ],
)
def test_normalizes_complete_context_without_coercion(
    template_id: str,
    value: object,
    expected: tuple[tuple[str, str | int | float], ...],
) -> None:
    result = normalize_scientific_context(template_id, value, require_complete=True)
    assert result == expected
    assert isinstance(result, tuple)
    assert all(isinstance(pair, tuple) for pair in result)
    assert tuple(type(pair[1]) for pair in result) == tuple(type(pair[1]) for pair in expected)


def test_tuple_replay_is_sorted_and_independent_from_mutable_input() -> None:
    original = {"profile_y": 3.25, "profile_x": 2}
    frozen = normalize_scientific_context("spatial_profile", original)
    original["profile_x"] = 99
    assert frozen == (("profile_x", 2), ("profile_y", 3.25))
    assert normalize_scientific_context("spatial_profile", tuple(reversed(frozen))) == frozen
    assert normalize_scientific_context("spatial_profile", MappingProxyType(original)) == (
        ("profile_x", 99),
        ("profile_y", 3.25),
    )


@pytest.mark.parametrize(
    ("template_id", "context"),
    [
        ("event_response", {"interval_label": "stimulation"}),
        ("spatial_profile", {"profile_x": 0, "profile_y": 0}),
        ("ratiometric_response", {"ratio_definition": "A / B"}),
    ],
)
def test_complete_context_does_not_require_units(template_id: str, context: object) -> None:
    assert normalize_scientific_context(template_id, context, require_complete=True)


@pytest.mark.parametrize(
    ("template_id", "value", "missing"),
    [
        ("event_response", None, ["interval_label"]),
        ("event_response", {"time_unit": "s"}, ["interval_label"]),
        ("spatial_profile", {}, ["profile_x", "profile_y"]),
        ("spatial_profile", {"profile_x": 0}, ["profile_y"]),
        ("spatial_profile", {"profile_y": 0}, ["profile_x"]),
        ("ratiometric_response", (), ["ratio_definition"]),
    ],
)
def test_complete_context_reports_missing_scientific_facts(
    template_id: str, value: object, missing: list[str]
) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context(template_id, value, require_complete=True)
    assert caught.value.code == "missing_scientific_context_keys"
    assert caught.value.details["missing_keys"] == missing
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize("value", [None, {}, ()])
def test_unknown_template_accepts_absence_even_when_complete(value: object) -> None:
    assert normalize_scientific_context("existing_template", value, require_complete=True) == ()


def test_unknown_template_rejects_nonempty_context() -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("existing_template", {"interval_label": "pulse"})
    assert caught.value.code == "unsupported_scientific_context"


@pytest.mark.parametrize("template_id", ["event_response", "spatial_profile", "ratiometric_response"])
def test_unknown_keys_are_reported_sorted(template_id: str) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context(template_id, {"z_extra": "x", "a_extra": "y"})
    assert caught.value.code == "unknown_scientific_context_keys"
    assert caught.value.details["unknown_keys"] == ["a_extra", "z_extra"]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "{}",
        [],
        [("interval_label", "pulse")],
        0,
        False,
        {1: "pulse"},
        (("interval_label",),),
        (("interval_label", "pulse", "extra"),),
        (["interval_label", "pulse"],),
        ("interval_label", "pulse"),
        ((None, "pulse"),),
    ],
)
def test_rejects_malformed_context_objects_and_pairs(value: object) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("event_response", value)
    assert caught.value.code == "invalid_scientific_context"


def test_rejects_duplicate_tuple_keys_before_replay_can_lose_them() -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("event_response", (("interval_label", "one"), ("interval_label", "two")))
    assert caught.value.code == "invalid_scientific_context"
    assert caught.value.details["duplicate_keys"] == ["interval_label"]


@pytest.mark.parametrize(
    ("template_id", "key"),
    [
        ("event_response", "interval_label"),
        ("event_response", "time_unit"),
        ("event_response", "response_unit"),
        ("spatial_profile", "x_unit"),
        ("spatial_profile", "y_unit"),
        ("spatial_profile", "value_unit"),
        ("ratiometric_response", "ratio_definition"),
        ("ratiometric_response", "x_unit"),
        ("ratiometric_response", "numerator_unit"),
        ("ratiometric_response", "denominator_unit"),
        ("ratiometric_response", "ratio_unit"),
    ],
)
@pytest.mark.parametrize("value", ["", "  ", "a\nb", "a\rb", "a\tb", "a\x00b", "a\x7fb", "a" * 257])
def test_rejects_blank_multiline_control_or_overlong_text(template_id: str, key: str, value: str) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context(template_id, {key: value})
    assert caught.value.code == "invalid_scientific_context"
    assert caught.value.details["field"] == key


@pytest.mark.parametrize("value", ["a\u0085b", "a\u2028b", "a\u2029b", "a\u200bb", "a\ud800b"])
def test_rejects_unicode_line_separators_and_control_text(value: str) -> None:
    with pytest.raises(ScientificContextError):
        normalize_scientific_context("event_response", {"interval_label": value})


@pytest.mark.parametrize("value", [None, True, False, 1, 1.5, [], {}, ("nested",)])
def test_text_is_not_implicitly_coerced(value: object) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("event_response", {"interval_label": value})
    assert caught.value.code == "invalid_scientific_context"


@pytest.mark.parametrize("key", ["profile_x", "profile_y"])
@pytest.mark.parametrize(
    "value", [
        None, True, False, "1", "1.25", Decimal("1.25"), [], {},
        float("nan"), float("inf"), -float("inf"), 10**1000,
    ]
)
def test_coordinates_require_finite_native_numbers(key: str, value: object) -> None:
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("spatial_profile", {key: value})
    assert caught.value.code == "invalid_scientific_context"
    assert caught.value.details["field"] == key


def test_preserves_exact_large_integer_coordinate() -> None:
    result = normalize_scientific_context("spatial_profile", {"profile_x": 10**100})
    assert result == (("profile_x", 10**100),)
    assert type(result[0][1]) is int


def test_text_boundary_and_formula_like_content_are_inert_preserved_data() -> None:
    text = "x" * 256
    assert normalize_scientific_context("event_response", {"interval_label": text}) == (
        ("interval_label", text),
    )
    formula = "__import__('os').system('do-not-execute')"
    assert normalize_scientific_context("ratiometric_response", {"ratio_definition": formula}) == (
        ("ratio_definition", formula),
    )


def test_error_diagnostics_do_not_copy_context_values() -> None:
    local_path = "SYNTHETIC_CONTEXT_MARKER\n"
    with pytest.raises(ScientificContextError) as caught:
        normalize_scientific_context("event_response", {"interval_label": local_path})
    assert local_path not in str(caught.value)
    assert local_path not in repr(caught.value.details)
