"""Precomputed spectral-density display, with explicit intervals and reference bands."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))
sys.path.insert(0, str(ROOT / "tools"))


def source():
    return pd.DataFrame(
        {
            "Frequency": [1.0, 2.0, 10.0, 8.0, 40.0, 35.0],
            "Condition": ["A", "B"] * 3,
            "PSD": [4.0, 3.0, 1.0, 2.0, 0.2, 0.4],
            "Lower": [3.5, 2.6, 0.8, 1.7, 0.1, 0.2],
            "Upper": [4.6, 3.4, 1.3, 2.5, 0.3, 0.7],
            "QC": ["retained"] * 6,
        },
        index=[10, 10, -1, 8, 2, 8],
    )


def module():
    assert importlib.util.find_spec("origin_sciplot.spectral_density") is not None
    return importlib.import_module("origin_sciplot.spectral_density")


def build(frame=None, **overrides):
    mod = module()
    options = dict(
        frequency_column="Frequency",
        value_column="PSD",
        condition_column="Condition",
        lower_column="Lower",
        upper_column="Upper",
        interval_label="Illustrative interval (not CI)",
        frequency_unit="Hz",
        value_unit="uV^2/Hz",
        value_representation="linear_density",
    )
    options.update(overrides)
    if "bands" in options:
        options["bands"] = tuple(mod.FrequencyBand(*band) for band in options["bands"])
    return mod.build_spectral_density_plan(source() if frame is None else frame, **options)


def test_nonuniform_interleaved_curves_keep_source_rows_units_and_all_supplied_bounds():
    frame = source()
    original = frame.copy(deep=True)
    plan = build(frame)
    assert plan.series_order == ("A", "B")
    assert plan.series_rows == (("A", (0, 2, 4)), ("B", (1, 3, 5)))
    assert plan.frequency_range == (1, 40)
    assert plan.value_range == pytest.approx((0, 4.96))
    assert plan.retained_columns == ("QC",)
    assert plan.interval_label == "Illustrative interval (not CI)"
    assert plan.display_transform == "identity"
    assert plan.processing_boundary == "upstream_spectral_density_only"
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_two_column_spectrum_needs_no_fabricated_condition_or_error_columns():
    frame = source().iloc[[0, 2, 4]][["Frequency", "PSD"]].copy()
    plan = build(frame, condition_column=None, lower_column=None, upper_column=None, interval_label=None)
    assert plan.series_order == ("PSD",)
    assert plan.series_rows == (("PSD", (0, 1, 2)),)
    assert plan.lower_column is plan.upper_column is plan.interval_label is None
    assert list(frame.columns) == ["Frequency", "PSD"]


def test_chinese_names_and_declared_units_are_not_converted_or_shortened():
    frame = source().rename(columns={"Frequency": "频率", "PSD": "功率密度", "Condition": "条件"})
    frame["条件"] = ["条件甲", "条件乙"] * 3
    plan = build(
        frame,
        frequency_column="频率",
        value_column="功率密度",
        condition_column="条件",
        frequency_unit="kHz",
        value_unit="a.u./kHz",
    )
    assert plan.series_order == ("条件甲", "条件乙")
    assert plan.frequency_range == (1, 40)
    assert (plan.frequency_unit, plan.value_unit) == ("kHz", "a.u./kHz")


def test_log_axes_keep_the_supplied_values_and_cover_the_complete_interval():
    frame = source()
    original = frame.copy(deep=True)
    plan = build(frame, x_scale="log10", y_scale="log10")
    assert plan.x_scale == plan.y_scale == "log10"
    assert 0 < plan.value_range[0] < 0.1
    assert plan.value_range[1] > 4.6
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_already_logarithmic_values_stay_on_a_linear_value_axis():
    frame = source()
    for column in ("PSD", "Lower", "Upper"):
        frame[column] -= 10
    plan = build(frame, value_representation="already_logarithmic", value_unit="dB/Hz")
    assert plan.value_range[1] < 0
    assert plan.y_scale == "linear"
    with pytest.raises(ValueError, match="already logarithmic"):
        build(frame, value_representation="already_logarithmic", value_unit="dB/Hz", y_scale="log10")


def test_positive_db_values_also_cannot_silently_receive_a_second_logarithm():
    with pytest.raises(ValueError, match="already logarithmic"):
        build(value_representation="already_logarithmic", value_unit="dB/Hz", y_scale="log10")


def test_negative_linear_density_is_not_mistaken_for_a_valid_log_density():
    frame = source()
    frame.iloc[0, 2] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        build(frame)


def test_negative_supplied_interval_is_retained_and_flagged_not_clipped():
    frame = source()
    frame.iloc[0, 3] = -0.5
    plan = build(frame)
    assert "provided_interval_below_zero" in plan.warnings
    assert plan.value_range[0] < -0.5
    assert frame.iloc[0, 3] == -0.5
    with pytest.raises(ValueError, match="positive"):
        build(frame, y_scale="log10")


def test_signed_precomputed_frequencies_require_explicit_two_sided_declaration():
    frame = source()
    frame["Frequency"] = [-10, -8, 0, 2, 10, 9]
    with pytest.raises(ValueError, match="frequency"):
        build(frame)
    plan = build(frame, frequency_domain="signed")
    assert plan.frequency_range == (-10, 10)
    assert plan.series_rows[0] == ("A", (0, 2, 4))
    with pytest.raises(ValueError, match="positive"):
        build(frame, frequency_domain="signed", x_scale="log10")


def test_declared_bands_are_reference_ranges_not_automatically_integrated_power():
    plan = build(bands=[("Band B", 8, 12), ("Band A", 3, 7)])
    assert [(band.name, band.lower, band.upper) for band in plan.bands] == [
        ("Band B", 8, 12),
        ("Band A", 3, 7),
    ]
    assert plan.band_role == "reference_only_no_integral"
    assert plan.series_rows[1] == ("B", (1, 3, 5))


def test_distinct_band_intervals_may_touch_without_overlapping():
    plan = build(bands=[("Band A", 3, 8), ("Band B", 8, 12)])
    assert plan.bands[0].upper == plan.bands[1].lower == 8


@pytest.mark.parametrize(
    "bands",
    [
        [("Band", 3, 8), ("Band", 8, 12)],
        [("A", 3, 9), ("B", 8, 12)],
        [("", 3, 7)],
        [("A", 7, 3)],
        [("A", 0, 7)],
        [("A", 3, 50)],
        [("A", np.nan, 7)],
    ],
)
def test_invalid_overlapping_or_uncovered_band_declarations_are_rejected(bands):
    with pytest.raises(ValueError):
        build(bands=bands)


@pytest.mark.parametrize(
    "options",
    [
        {"frequency_unit": ""},
        {"value_unit": None},
        {"value_representation": "amplitude"},
        {"frequency_domain": "guess"},
        {"x_scale": "unknown"},
        {"y_scale": "unknown"},
        {"lower_column": None},
        {"upper_column": None},
        {"interval_label": None},
        {"interval_label": " "},
        {"value_column": "missing"},
        {"frequency_column": "PSD"},
    ],
)
def test_missing_roles_or_ambiguous_semantic_declarations_are_rejected(options):
    with pytest.raises(ValueError):
        build(**options)


@pytest.mark.parametrize(
    "fault", ["zero_log_frequency", "duplicate", "decreasing", "nan", "bool", "interval"]
)
def test_bad_samples_or_intervals_are_not_silently_deleted_or_repaired(fault):
    frame = source()
    options = {}
    if fault == "zero_log_frequency":
        frame.iloc[0, 0] = 0
        options["x_scale"] = "log10"
    elif fault == "duplicate":
        frame.iloc[2, 0] = 1
    elif fault == "decreasing":
        frame.iloc[2, 0] = 0.5
    elif fault == "nan":
        frame.iloc[0, 2] = np.nan
    elif fault == "bool":
        frame["PSD"] = frame["PSD"].astype(object)
        frame.iloc[0, 2] = True
    else:
        frame.iloc[0, 3] = 5
    original = frame.copy(deep=True)
    with pytest.raises(ValueError):
        build(frame, **options)
    pd.testing.assert_frame_equal(frame, original, check_exact=True)


def test_synthetic_psd_fixture_supplies_all_intervals_and_explicit_reference_bands():
    import generate_research_data as demos

    generate = getattr(demos, "spectral_density_data", None)
    assert callable(generate), "A PSD example must provide reproducible source values and intervals"
    frame, repeated = generate(), generate()
    pd.testing.assert_frame_equal(frame, repeated, check_exact=True)
    assert frame.shape == (642, 5)
    assert frame.attrs["data_origin"] == "synthetic_teaching_data"
    assert frame.attrs["scientific_claim"] == "none"
    assert frame.attrs["processing"] == "authored_density_not_estimated_from_recordings"
    assert frame.attrs["interval_label"] == "Illustrative interval (not CI)"
    plan = build(
        frame,
        frequency_column="Frequency (Hz)",
        value_column="PSD (uV^2/Hz)",
        y_scale="log10",
        bands=frame.attrs["reference_bands"],
    )
    assert plan.series_order == ("Demo A", "Demo B")
    assert [len(rows) for _, rows in plan.series_rows] == [321, 321]
    assert plan.frequency_range == (0.5, 80)
    assert len(plan.bands) == 2 and plan.band_role == "reference_only_no_integral"
