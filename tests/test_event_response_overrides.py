from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SRC = ROOT / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.palette_catalog import get_palette  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    apply_scientific_palette_override,
    apply_scientific_text_overrides,
    prepare_scientific,
)

INTERVAL = "Upstream asymmetric interval (not CI)"


def _source(tmp_path: Path, *, condition_count: int = 2) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(condition_count):
        condition = f"Condition {index + 1}"
        rows.extend(
            (
                {
                    "Time(s)": -1.0,
                    "Condition": condition,
                    "Mean(uV)": 1.0 + index,
                    "Lower(uV)": 0.6 + index,
                    "Upper(uV)": 1.8 + index,
                    "Note": "retained",
                },
                {
                    "Time(s)": 1.5 + index * 0.1,
                    "Condition": condition,
                    "Mean(uV)": 1.6 + index,
                    "Lower(uV)": 1.1 + index,
                    "Upper(uV)": 2.7 + index,
                    "Note": "retained",
                },
            )
        )
    path = tmp_path / f"event-{condition_count}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _prepare(tmp_path: Path, *, condition_count: int = 2):
    source = _source(tmp_path, condition_count=condition_count)
    mapping = ScientificColumnMapping(
        (
            ("Time(s)", "x"),
            ("Condition", "condition"),
            ("Mean(uV)", "mean"),
            ("Lower(uV)", "lower"),
            ("Upper(uV)", "upper"),
            ("Note", "ignored"),
        ),
        scientific_context={"interval_label": INTERVAL},
    )
    return source, prepare_scientific(source, "event_response", column_mapping=mapping)


def test_unit_preserving_titles_rebuild_shared_layout_style_and_digest(tmp_path: Path) -> None:
    source, original = _prepare(tmp_path)
    source_bytes = source.read_bytes()
    changed = apply_scientific_text_overrides(
        original,
        x_title="Elapsed time from declared event origin (s)",
        y_title="Upstream mean voltage response (uV)",
    )

    assert changed.plot_spec.x_title == "Elapsed time from declared event origin (s)"
    assert changed.plot_spec.y_title == "Upstream mean voltage response (uV)"
    assert changed.plot_spec.event_response_layout != original.plot_spec.event_response_layout
    assert changed.plot_spec.display_plan.figure_style == changed.plot_spec.event_response_layout.style
    assert any(
        changed_value > original_value
        for changed_value, original_value in (
            (
                changed.plot_spec.event_response_layout.style.page_width_cm,
                original.plot_spec.event_response_layout.style.page_width_cm,
            ),
            (
                changed.plot_spec.event_response_layout.style.page_height_cm,
                original.plot_spec.event_response_layout.style.page_height_cm,
            ),
        )
    )
    assert changed.plan_digest != original.plan_digest
    assert source.read_bytes() == source_bytes


def test_text_reflow_preserves_source_context_and_source_bound_event_plan(tmp_path: Path) -> None:
    _source_path, original = _prepare(tmp_path)
    changed = apply_scientific_text_overrides(
        original,
        x_title="Event-aligned acquisition time (s)",
        y_title="Mean fluorescence response (uV)",
    )

    assert changed.source_sha256 == original.source_sha256
    assert changed.source_path == original.source_path
    assert changed.scientific_context == original.scientific_context
    assert changed.plot_spec.event_response_plan == original.plot_spec.event_response_plan
    assert changed.plot_spec.axis_plan == original.plot_spec.axis_plan
    assert changed.plot_spec.event_response_layout.condition_colors == (
        original.plot_spec.event_response_layout.condition_colors
    )


@pytest.mark.parametrize(
    ("kwargs", "expected_unit"),
    [
        ({"x_title": "Elapsed event time (ms)"}, "s"),
        ({"y_title": "Mean voltage response (mV)"}, "uV"),
    ],
)
def test_title_override_cannot_silently_change_declared_units(
    tmp_path: Path,
    kwargs: dict[str, str],
    expected_unit: str,
) -> None:
    _source_path, prepared = _prepare(tmp_path)
    with pytest.raises(ScientificWorkflowError, match="unit") as caught:
        apply_scientific_text_overrides(prepared, **kwargs)
    assert expected_unit in str(caught.value)


def test_blue_coral_freezes_catalog_colors_into_layout_style_and_digest(tmp_path: Path) -> None:
    source, original = _prepare(tmp_path)
    source_bytes = source.read_bytes()
    palette = get_palette("blue_coral")
    expected_colors = tuple(
        zip(
            original.plot_spec.event_response_plan.condition_order,
            palette.colors[:2],
            strict=True,
        )
    )
    changed = apply_scientific_palette_override(original, palette_id=palette.palette_id)

    assert changed.plot_spec.event_response_layout.condition_colors == expected_colors
    assert changed.plot_spec.event_response_layout.style.palette_name == "blue_coral"
    assert changed.plot_spec.display_plan.figure_style == changed.plot_spec.event_response_layout.style
    assert changed.plan_digest != original.plan_digest
    assert changed.plot_spec.event_response_plan == original.plot_spec.event_response_plan
    assert changed.scientific_context == original.scientific_context
    assert source.read_bytes() == source_bytes


def test_palette_limit_counts_eight_conditions_not_the_single_mean_series(tmp_path: Path) -> None:
    _source_path, prepared = _prepare(tmp_path, condition_count=8)
    palette = get_palette("blue_coral")
    assert len(prepared.plot_spec.series) == 1
    assert len(prepared.plot_spec.event_response_plan.condition_order) == 8
    assert palette.max_qualitative_categories == 5

    with pytest.raises(ScientificWorkflowError) as caught:
        apply_scientific_palette_override(prepared, palette_id=palette.palette_id)
    assert caught.value.code == "palette_category_limit_exceeded"
