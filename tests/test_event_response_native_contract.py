"""Contract tests for the native supplied event-response renderer.

The renderer is imported inside each test path so this red-test module remains
collectable before ``origin_backend.event_response_renderer`` is implemented.
No test opens Origin or supplies a functional Origin object.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    load_scientific_frame,
    prepare_scientific,
)

INTERVAL_LABEL = "Upstream asymmetric interval (not CI)"


def _renderer():
    from origin_sciplot.origin_backend import event_response_renderer

    return event_response_renderer


@pytest.fixture
def native_case(tmp_path: Path):
    source = tmp_path / "event_response_native.csv"
    authored = pd.DataFrame(
        {
            "Time (ms)": [-3.0, -2.5, -0.5, 0.75, 2.25, 3.75],
            "Condition": ["01", "02", "01", "02", "01", "02"],
            "Mean (uV)": [1.0, 0.7, 2.4, 1.5, 1.8, 0.9],
            "Lower (uV)": [0.1, 0.4, 1.2, 1.1, 1.6, 0.2],
            "Upper (uV)": [1.4, 1.8, 3.9, 2.1, 2.7, 1.3],
            "AcquisitionNote": ["keep-A", "keep-B", "keep-C", "keep-D", "keep-E", "keep-F"],
        }
    )
    authored.to_csv(source, index=False)
    assignments = tuple(
        zip(
            authored.columns,
            ("x", "condition", "mean", "lower", "upper", "ignored"),
            strict=True,
        )
    )
    preparation = prepare_scientific(
        source,
        "event_response",
        column_mapping=ScientificColumnMapping(
            assignments,
            plot_mode="supplied_mean_interval",
            scientific_context={"interval_label": INTERVAL_LABEL},
        ),
    )
    frame = load_scientific_frame(source, preparation)
    return source, authored, frame, preparation


def test_native_helpers_preserve_condition_order_irregular_time_asymmetric_bounds_and_source_rows(
    native_case,
) -> None:
    _source, _authored, frame, preparation = native_case

    groups = _renderer()._prepare_event_response_data(frame, preparation)

    assert tuple(condition for condition, _data in groups) == ("01", "02")
    assert list(groups[0][1].columns) == ["SourceTime", "Upper", "Lower", "Mean", "SourceRow"]
    np.testing.assert_array_equal(
        groups[0][1].to_numpy(dtype=float),
        np.asarray(
            [
                [-3.0, 1.4, 0.1, 1.0, 1.0],
                [-0.5, 3.9, 1.2, 2.4, 3.0],
                [2.25, 2.7, 1.6, 1.8, 5.0],
            ]
        ),
    )
    np.testing.assert_array_equal(
        groups[1][1].to_numpy(dtype=float),
        np.asarray(
            [
                [-2.5, 1.8, 0.4, 0.7, 2.0],
                [0.75, 2.1, 1.1, 1.5, 4.0],
                [3.75, 1.3, 0.2, 0.9, 6.0],
            ]
        ),
    )


def test_source_workbook_copy_preserves_ignored_values_and_leading_zero_condition_ids(
    native_case,
) -> None:
    _source, _authored, frame, preparation = native_case
    before = frame.copy(deep=True)

    copied = _renderer()._response_source_copy(frame, preparation.plot_spec.event_response_plan)

    pd.testing.assert_frame_equal(frame, before, check_exact=True)
    assert copied["Condition"].tolist() == ["01", "02", "01", "02", "01", "02"]
    assert isinstance(copied["Condition"].dtype, pd.CategoricalDtype)
    assert list(copied["Condition"].cat.categories) == ["01", "02"]
    assert copied["AcquisitionNote"].tolist() == before["AcquisitionNote"].tolist()


class _NoOriginAccess:
    def __getattr__(self, name: str):
        pytest.fail(f"Origin was accessed before native preflight rejected the input: {name}")


def test_mutated_ignored_source_value_is_rejected_before_origin_access(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    changed = frame.copy(deep=True)
    changed.loc[0, "AcquisitionNote"] = "tampered"

    with pytest.raises(OriginDrawError, match="source"):
        _renderer().build_event_response_graph(_NoOriginAccess(), changed, preparation)


def test_changed_frozen_source_hash_is_rejected_before_origin_access(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    changed = replace(preparation, source_sha256="0" * 64)

    with pytest.raises(OriginDrawError, match="source"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


def test_changed_physical_layout_is_rejected_before_origin_access(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    spec = preparation.plot_spec
    layout = replace(
        spec.event_response_layout,
        interval_label_center=(
            spec.event_response_layout.interval_label_center[0] + 0.5,
            spec.event_response_layout.interval_label_center[1],
        ),
    )
    changed = replace(preparation, plot_spec=replace(spec, event_response_layout=layout))

    with pytest.raises(OriginDrawError, match="layout"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


def test_changed_physical_style_is_rejected_before_origin_access(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    spec = preparation.plot_spec
    style = replace(
        spec.display_plan.figure_style,
        fill_transparency_percent=spec.display_plan.figure_style.fill_transparency_percent - 1.0,
    )
    changed = replace(
        preparation,
        plot_spec=replace(
            spec,
            display_plan=replace(spec.display_plan, figure_style=style),
        ),
    )

    with pytest.raises(OriginDrawError, match="layout"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


def test_changed_axis_extent_is_rejected_before_origin_access(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    spec = preparation.plot_spec
    axis = replace(spec.axis_plan, x_to=spec.axis_plan.x_to + 0.25)
    changed = replace(preparation, plot_spec=replace(spec, axis_plan=axis))

    with pytest.raises(OriginDrawError, match="axis"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


@pytest.mark.parametrize("step_name", ["x_step", "y_step"])
def test_arbitrary_positive_axis_step_drift_is_rejected_before_origin_access(
    native_case,
    step_name: str,
) -> None:
    _source, _authored, frame, preparation = native_case
    spec = preparation.plot_spec
    expected = getattr(spec.axis_plan, step_name)
    assert expected is not None and expected > 0
    axis = replace(spec.axis_plan, **{step_name: expected * 0.73})
    changed = replace(preparation, plot_spec=replace(spec, axis_plan=axis))

    with pytest.raises(OriginDrawError, match="axis"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


@pytest.mark.parametrize(("field", "title"), [("x_title", "Time (s)"), ("y_title", "Response (mV)")])
def test_axis_words_cannot_relabel_the_frozen_units_without_conversion(native_case, field, title) -> None:
    _source, _authored, frame, preparation = native_case
    changed = replace(preparation, plot_spec=replace(preparation.plot_spec, **{field: title}))
    with pytest.raises(OriginDrawError, match="unit"):
        _renderer().build_event_response_graph(_NoOriginAccess(), frame, changed)


def test_helper_readback_accepts_the_exact_source_bound_helper(native_case) -> None:
    _source, _authored, frame, preparation = native_case
    expected = _renderer()._prepare_event_response_data(frame, preparation)[0][1]

    state = _renderer()._verify_response_helper(expected.copy(deep=True), expected)

    assert state == {
        "rows": 3,
        "source_values_exact": True,
        "source_time_exact": True,
        "bounds_exact": True,
        "mean_exact": True,
        "source_row_exact": True,
    }


@pytest.mark.parametrize("column", ["SourceTime", "Upper", "Lower", "Mean", "SourceRow"])
def test_helper_readback_rejects_one_nanounit_change_in_any_bound_mean_time_or_row(
    native_case,
    column: str,
) -> None:
    _source, _authored, frame, preparation = native_case
    expected = _renderer()._prepare_event_response_data(frame, preparation)[0][1]
    actual = expected.copy(deep=True)
    actual.loc[0, column] += 1e-9

    with pytest.raises(OriginDrawError, match="helper"):
        _renderer()._verify_response_helper(actual, expected)
