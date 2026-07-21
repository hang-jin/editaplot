"""Teacher-required fixed Origin page, layer, font, and line parameters."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FixedOriginStyle:
    page_width_cm: float = 22.31
    page_height_cm: float = 16.82
    layer_left_percent: float = 14.0
    layer_top_percent: float = 2.995
    layer_width_percent: float = 85.01
    layer_height_percent: float = 82.51
    layer_fixed: int = 1
    layer_factor: float = 1.0
    font_family: str = "Arial"
    axis_title_size_pt: float = 26.0
    tick_label_size_pt: float = 24.0
    legend_size_pt: float = 24.0
    plot_line_width_pt: float = 5.0
    frame_line_width_pt: float = 3.0
    major_tick_length_pt: float = 7.0
    minor_tick_length_pt: float = 4.0
    x_major_step: float = 2.0
    x_minor_ticks_between_majors: int = 1
    x_title_upshift_page_percent: float = 3.0

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


FIXED_ORIGIN_STYLE = FixedOriginStyle()


def page_size_inches(style: FixedOriginStyle = FIXED_ORIGIN_STYLE) -> tuple[float, float]:
    return style.page_width_cm / 2.54, style.page_height_cm / 2.54


def pt_to_origin_width_units(points: float) -> int:
    """LabTalk ``set -w`` uses 1/500 pt units."""
    return int(round(points * 500))


def origin_points_to_preview_points(
    points: float,
    preview_width_inches: float,
    style: FixedOriginStyle = FIXED_ORIGIN_STYLE,
) -> float:
    """Preserve physical text/line proportions on a narrower preview page."""
    if preview_width_inches <= 0:
        raise ValueError("preview_width_inches must be positive")
    return points * preview_width_inches / page_size_inches(style)[0]
