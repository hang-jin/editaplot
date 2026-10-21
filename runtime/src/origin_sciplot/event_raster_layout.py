"""Physical event-raster layout; sparse labels never remove source trials."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .event_raster import EventRasterPlan
from .scientific_visual import AdaptiveOriginStyle, text_span_cm


@dataclass(frozen=True)
class EventRasterLayout:
    style: AdaptiveOriginStyle
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    y_step: float
    marker_size_pt: float
    marker_edge_percent: float
    trial_labels: tuple[tuple[str, int, float, float], ...]  # text, ordinal, right %, center Y %
    condition_labels: tuple[tuple[str, float, float], ...]  # text, left %, center Y %
    y_title_x_percent: float
    y_title_y_percent: float


def build_event_raster_layout(
    plan: EventRasterPlan, x_title: str, y_title: str
) -> EventRasterLayout:
    """Keep event coordinates and source order; allocate page-attached label gutters."""
    count = len(plan.trial_order)
    if not 1 <= count <= 200 or not plan.condition_order:
        raise ValueError("Event-raster layout requires a validated trial/condition inventory.")
    if not x_title.strip() or not y_title.strip():
        raise ValueError("Event-raster axis titles must not be empty.")
    label_height = max(len(label.splitlines()) for label in plan.trial_order) * 17 * 2.54 / 72 * 1.4
    legend_height = max(len(label.splitlines()) for label in plan.condition_order) * 17 * 2.54 / 72 * 1.4
    legend_columns = min(2, len(plan.condition_order))
    legend_rows = math.ceil(len(plan.condition_order) / legend_columns)
    legend_row_height = max(1.0, legend_height + 0.4)
    left = max(3.5, max(text_span_cm(label, 17) for label in plan.trial_order) + 2.8)
    plot_width = max(
        20.0, text_span_cm(x_title, 20, bold=True) + 1,
        legend_columns * (max(text_span_cm(label, 17) for label in plan.condition_order) + 0.8),
    )
    plot_height = max(
        14.8, min(28.0, count * 0.37), text_span_cm(y_title, 20, bold=True) + 1,
        min(count, 12) * (label_height + 0.3),
    )
    row_height = plot_height / count
    # Sparse endpoint labels remain centred on the first/last real trial.
    # Reserve their half-height beyond the first/last lane, not just the legend.
    endpoint_gutter = max(0.0, (label_height - row_height) / 2) + 0.6
    top = max(1.0 + legend_rows * legend_row_height, endpoint_gutter)
    bottom = max(3.2, endpoint_gutter)
    width, height = left + plot_width + 1.0, top + plot_height + bottom
    style = AdaptiveOriginStyle(
        profile_name="research-event-raster", page_width_cm=width, page_height_cm=height,
        layer_left_percent=left / width * 100, layer_top_percent=top / height * 100,
        layer_width_percent=plot_width / width * 100, layer_height_percent=plot_height / height * 100,
        frame_line_width_pt=1.1, x_title_upshift_page_percent=0.0, palette_name="publication_signal",
    )
    minimum_separation = max(1, math.ceil((label_height + 0.3) / row_height))
    stride = max(math.ceil(count / 12), minimum_separation)
    ordinals = list(range(1, count + 1, stride))
    if ordinals[-1] != count:
        # Keep the final real ID without squeezing it against the prior label.
        while len(ordinals) > 1 and count - ordinals[-1] < minimum_separation:
            ordinals.pop()
        ordinals.append(count)
    return EventRasterLayout(
        style=style,
        x_range=plan.x_range,
        y_range=(plan.y_range[1], plan.y_range[0]),
        y_step=float(max(1, math.ceil(count / 8))),
        marker_size_pt=min(6.0, row_height * 72 / 2.54 * 0.65),
        marker_edge_percent=22.0,
        trial_labels=tuple(
            (plan.trial_order[ordinal - 1], ordinal, (left - 0.5) / width * 100,
             (top + (ordinal - 0.5) * row_height) / height * 100)
            for ordinal in ordinals
        ),
        condition_labels=tuple(
            (condition, (left + (index % legend_columns) * plot_width / legend_columns) / width * 100,
             (0.4 + (index // legend_columns + 0.5) * legend_row_height) / height * 100)
            for index, condition in enumerate(plan.condition_order)
        ),
        y_title_x_percent=1.0 / width * 100,
        y_title_y_percent=(top + plot_height / 2) / height * 100,
    )
