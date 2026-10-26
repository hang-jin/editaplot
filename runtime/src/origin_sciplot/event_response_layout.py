"""Physical layout for supplied means and intervals; no statistical inference."""

from __future__ import annotations

from dataclasses import dataclass

from .event_response import EventResponsePlan
from .scientific_visual import AdaptiveOriginStyle, palette_colors, text_span_cm


@dataclass(frozen=True)
class EventResponseLayout:
    style: AdaptiveOriginStyle
    condition_colors: tuple[tuple[str, str], ...]
    condition_labels: tuple[tuple[str, float, float], ...]
    interval_label_center: tuple[float, float]
    y_title_center: tuple[float, float]


def _text_height_cm(text: str, size: float) -> float:
    return max(1, len(text.splitlines())) * size * 2.54 / 72 * 1.4


def build_event_response_layout(
    plan: EventResponsePlan, x_title: str, y_title: str, *, palette_name: str = "publication_comparison"
) -> EventResponseLayout:
    """Reserve physical space without truncating declarations or shrinking type."""
    if not 1 <= len(plan.condition_order) <= 8 or not plan.interval_label.strip():
        raise ValueError("Event-response layout requires a validated inventory and interval label.")
    if (
        not isinstance(x_title, str)
        or not isinstance(y_title, str)
        or not x_title.strip()
        or not y_title.strip()
    ):
        raise ValueError("Event-response axis titles must not be empty.")
    colors = palette_colors(palette_name)
    if len(colors) < len(plan.condition_order):
        raise ValueError("The palette needs a distinct color for every condition.")
    columns = min(2, len(plan.condition_order))
    rows = [
        plan.condition_order[index : index + columns]
        for index in range(0, len(plan.condition_order), columns)
    ]
    column_widths = [
        max(text_span_cm(row[column], 17) for row in rows if column < len(row)) + 1.0
        for column in range(columns)
    ]
    row_heights = [max(_text_height_cm(label, 17) for label in row) + 0.4 for row in rows]
    y_title_thickness = _text_height_cm(y_title, 20)
    left = max(3.8, y_title_thickness + 2.5)
    plot_width = max(
        20.0,
        sum(column_widths),
        text_span_cm(x_title, 20, bold=True) + 1.0,
        text_span_cm(plan.interval_label, 17) + 1.0,
    )
    plot_height = max(12.0, text_span_cm(y_title, 20, bold=True) + 1.0)
    interval_height = _text_height_cm(plan.interval_label, 17)
    legend_bottom = 0.5 + sum(row_heights)
    interval_center = legend_bottom + 0.3 + interval_height / 2
    top = interval_center + interval_height / 2 + 0.8
    bottom = max(3.2, _text_height_cm(x_title, 20) + 2.0)
    width, height = left + plot_width + 1.0, top + plot_height + bottom
    style = AdaptiveOriginStyle(
        profile_name="research-event-response",
        page_width_cm=width,
        page_height_cm=height,
        layer_left_percent=left / width * 100,
        layer_top_percent=top / height * 100,
        layer_width_percent=plot_width / width * 100,
        layer_height_percent=plot_height / height * 100,
        frame_line_width_pt=1.1,
        plot_line_width_pt=2.0,
        fill_transparency_percent=75.0,
        x_title_upshift_page_percent=0.0,
        palette_name=palette_name,
    )
    labels = []
    row_top = 0.5
    for row, row_height in zip(rows, row_heights, strict=True):
        column_left = left
        for column, label in enumerate(row):
            labels.append((label, column_left / width * 100, (row_top + row_height / 2) / height * 100))
            column_left += column_widths[column]
        row_top += row_height
    return EventResponseLayout(
        style=style,
        condition_colors=tuple(zip(plan.condition_order, colors[: len(labels)], strict=True)),
        condition_labels=tuple(labels),
        interval_label_center=((left + plot_width / 2) / width * 100, interval_center / height * 100),
        y_title_center=((0.5 + y_title_thickness / 2) / width * 100, (top + plot_height / 2) / height * 100),
    )
