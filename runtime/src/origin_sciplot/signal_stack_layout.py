"""Physical layout shared by preview and Origin; no invented time-axis padding."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .scientific_visual import AdaptiveOriginStyle, text_span_cm
from .signal_stack import SignalStackPlan


@dataclass(frozen=True)
class SignalStackLayout:
    x_range: tuple[float, float]
    y_range: tuple[float, float]
    channel_labels: tuple[tuple[str, float, float], ...]  # label, right page %, center Y page %
    reference_x: float
    reference_y_from: float
    reference_y_to: float
    reference_text: str
    reference_text_x_percent: float
    reference_text_y_percent: float
    y_title_x_percent: float
    y_title_y_percent: float
    reference_height_cm: float


def build_signal_stack_layout(
    plan: SignalStackPlan, style: AdaptiveOriginStyle, *, y_range: tuple[float, float]
) -> SignalStackLayout:
    y0, y1 = y_range
    if not all(math.isfinite(value) for value in y_range) or y0 >= y1:
        raise ValueError("Signal display bounds must be finite and increasing.")
    if y0 > plan.display_y_range[0] or y1 < plan.display_y_range[1]:
        raise ValueError("The frozen bounds must include all source amplitudes and declared offsets.")
    plot_width = style.page_width_cm * style.layer_width_percent / 100
    plot_height = style.page_height_cm * style.layer_height_percent / 100
    if min(plot_width, plot_height) <= 0:
        raise ValueError("Signal physical data dimensions must be positive.")
    left = style.page_width_cm * style.layer_left_percent / 100
    right = left + plot_width
    x0, x1 = plan.time_range
    ruler_x_cm = right + 0.7
    ruler_x = x1 + (x1 - x0) * 0.7 / plot_width
    ruler_from = y0 + 0.15 * (y1 - y0)
    ruler_to = ruler_from + plan.amplitude_scale_length
    if ruler_to > y1 - 0.08 * (y1 - y0):
        raise ValueError("The frozen bounds must leave room for the common amplitude ruler.")
    center = (plan.source_value_range[0] + plan.source_value_range[1]) / 2

    def page_y(y: float) -> float:
        return style.layer_top_percent + (y1 - y) / (y1 - y0) * style.layer_height_percent

    text = f"{plan.amplitude_scale_length:g} {plan.value_unit}"
    return SignalStackLayout(
        x_range=plan.time_range,
        y_range=y_range,
        channel_labels=tuple(
            (name, (left - 0.5) / style.page_width_cm * 100, page_y(center + offset))
            for name, offset in plan.offsets
        ),
        reference_x=ruler_x,
        reference_y_from=ruler_from,
        reference_y_to=ruler_to,
        reference_text=text,
        reference_text_x_percent=(ruler_x_cm + 0.4 + text_span_cm(text, 17.0) / 2)
        / style.page_width_cm
        * 100,
        reference_text_y_percent=page_y((ruler_from + ruler_to) / 2),
        y_title_x_percent=1.0 / style.page_width_cm * 100,
        y_title_y_percent=style.layer_top_percent + style.layer_height_percent / 2,
        reference_height_cm=plan.amplitude_scale_length / (y1 - y0) * plot_height,
    )
