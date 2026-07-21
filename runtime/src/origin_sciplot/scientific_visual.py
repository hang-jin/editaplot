"""Adaptive visual profiles for general-purpose scientific figures.

The fixed XPS contract remains available in :mod:`base_style_contract`.  This
module is deliberately separate: general statistical/scientific charts need a
page that responds to label length, series count and data density instead of a
single physical size inherited from one teaching task.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable

from .palette_catalog import list_palettes


PALETTES: dict[str, tuple[str, ...]] = {
    # Verified direct ``set -c`` colors for 1–6 editable 3D trajectories.
    "trajectory3d_family": (
        "#17304C",
        "#1F6F78",
        "#D5A44C",
        "#9B5C76",
        "#557A46",
        "#76548D",
    ),
    # Related method families: cool baselines, restrained rose hero variants.
    "comparison_family": (
        "#484878",
        "#7884B4",
        "#B4C0E4",
        "#E4E4F0",
        "#E4CCD8",
        "#F0C0CC",
    ),
    # Same-hue sequences for ablation and long-label horizontal bars.
    "ablation_blue": (
        "#234F7D",
        "#4777A5",
        "#7099BF",
        "#9AB9D2",
        "#C7D9E8",
        "#E1EBF3",
    ),
    # Signed effects: cool negative values, warm positive values, with a
    # neutral centre.  Row-level assignment is magnitude aware in the
    # categorical renderer; this palette is never used as a rainbow ramp.
    "diverging_effect": (
        "#3F67A8",
        "#86A5D2",
        "#D9E0E8",
        "#E9C2BE",
        "#C6534E",
    ),
    "stacked_blue": (
        "#DCE8F2",
        "#BCD2E5",
        "#91B6D4",
        "#6395BE",
        "#3B74A5",
        "#214F7D",
    ),
    "composition_teal": (
        "#DCEFED",
        "#B8DDD8",
        "#8FC8C1",
        "#61AFA6",
        "#3B9188",
        "#236F69",
    ),
    # Single-family lilac sequence for normalized compositions.  It preserves
    # ordering without turning one composition into a rainbow.
    "composition_lilac": (
        "#ECEBF5",
        "#D2D0E8",
        "#B4B0D8",
        "#928BC2",
        "#6E65A8",
        "#494277",
    ),
    "trend_family": (
        "#245B9A",
        "#76A0CC",
        "#D98782",
        "#E7B7B3",
        "#3C9D94",
        "#8CCDC5",
    ),
    "flow_family": (
        "#355F8A",
        "#5E8FB7",
        "#89B7C9",
        "#7DBFB5",
        "#A89BCD",
        "#D2A3AE",
        "#D6B66F",
    ),
    "distribution_family": (
        "#285D7A",
        "#4F829B",
        "#79A8B9",
        "#A7CDD3",
        "#D5E8E7",
        "#8A719B",
    ),
    "evidence_family": (
        "#2C5F85",
        "#5D88A5",
        "#91B1C4",
        "#C5D9E2",
        "#8A6F9D",
        "#B39DBD",
    ),
    "medical_ai": (
        "#244A73",
        "#3F7197",
        "#67A0B3",
        "#9BC8C8",
        "#C8DEE0",
        "#B65C67",
    ),
    "paired_neutral": (
        "#385A73",
        "#4C6C84",
        "#607E94",
        "#7490A4",
        "#88A2B4",
        "#9CB4C4",
    ),
    "grouped_box_medical": (
        "#6C78D6",
        "#E3848A",
        "#5FA6A0",
        "#C59A62",
    ),
    "spectroscopy_jewel": (
        "#245B9A",
        "#B24B5A",
        "#1E7A67",
        "#6E5AA8",
        "#3E7C91",
        "#A06D3F",
    ),
}

# User-selectable palettes are registered by stable ID.  Internal semantic
# palettes above remain available for signed effects, heatmaps, and other
# routes where colour meaning must not be replaced by a cosmetic override.
PALETTES.update({palette.palette_id: palette.colors for palette in list_palettes()})


@dataclass(frozen=True)
class AdaptiveOriginStyle:
    """Resolved physical/style contract carried by a frozen plot plan."""

    profile_name: str
    page_width_cm: float
    page_height_cm: float
    layer_left_percent: float
    layer_top_percent: float
    layer_width_percent: float
    layer_height_percent: float
    layer_fixed: int = 1
    layer_factor: float = 1.0
    font_family: str = "Arial"
    axis_title_size_pt: float = 20.0
    tick_label_size_pt: float = 17.0
    legend_size_pt: float = 17.0
    plot_line_width_pt: float = 2.6
    frame_line_width_pt: float = 1.8
    major_tick_length_pt: float = 5.5
    minor_tick_length_pt: float = 3.0
    x_major_step: float = 2.0
    x_minor_ticks_between_majors: int = 1
    x_title_upshift_page_percent: float = 1.5
    error_bar_width_pt: float = 1.8
    bar_border_width_pt: float = 1.4
    fill_transparency_percent: float = 12.0
    palette_name: str = "comparison_family"
    heatmap_palette: str = "Viridis.PAL"
    inset_axis_title_size_pt: float = 15.0
    inset_tick_label_size_pt: float = 13.0
    inset_frame_line_width_pt: float = 1.3

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def palette_colors(name: str) -> tuple[str, ...]:
    try:
        return PALETTES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scientific palette: {name}") from exc


def interpolate_hex_colors(start: str, end: str, count: int) -> tuple[str, ...]:
    """Return a deterministic same-family color ramp with ``count`` entries."""
    if count < 1:
        raise ValueError("Color ramp count must be positive")

    def _rgb(value: str) -> tuple[int, int, int]:
        text = value.lstrip("#")
        if len(text) != 6:
            raise ValueError(f"Expected a six-digit hex color, got {value!r}")
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))

    start_rgb = _rgb(start)
    end_rgb = _rgb(end)
    if count == 1:
        return (f"#{start_rgb[0]:02X}{start_rgb[1]:02X}{start_rgb[2]:02X}",)
    colors: list[str] = []
    for index in range(count):
        fraction = index / (count - 1)
        rgb = tuple(
            round(source + (target - source) * fraction)
            for source, target in zip(start_rgb, end_rgb, strict=True)
        )
        colors.append(f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
    return tuple(colors)


def signed_effect_colors(values: Iterable[float]) -> tuple[str, ...]:
    """Map signed effect magnitudes to a restrained cool-neutral-warm palette."""
    numeric = [float(value) for value in values]
    finite = [value for value in numeric if math.isfinite(value)]
    negative_scale = max((abs(value) for value in finite if value < 0), default=0.0)
    positive_scale = max((value for value in finite if value > 0), default=0.0)
    deep_cool, soft_cool, neutral, soft_warm, deep_warm = palette_colors(
        "diverging_effect"
    )
    cool_ramp = interpolate_hex_colors(soft_cool, deep_cool, 101)
    warm_ramp = interpolate_hex_colors(soft_warm, deep_warm, 101)
    colors: list[str] = []
    for value in numeric:
        if not math.isfinite(value) or abs(value) < 1e-12:
            colors.append(neutral)
        elif value < 0:
            index = min(100, round(abs(value) / negative_scale * 100))
            colors.append(cool_ramp[index])
        else:
            index = min(100, round(value / positive_scale * 100))
            colors.append(warm_ramp[index])
    return tuple(colors)


def resolve_adaptive_style(
    *,
    template_id: str,
    plot_kind: str,
    row_count: int,
    series_count: int,
    max_label_length: int = 0,
    category_rotation_deg: float = 0.0,
    signed_values: bool = False,
) -> AdaptiveOriginStyle:
    """Resolve a readable physical page without locking every chart to one size."""

    rows = max(1, int(row_count))
    series = max(1, int(series_count))
    label_len = max(0, int(max_label_length))

    width = 23.5
    height = 16.0
    left = 17.0
    top = 5.5
    layer_height = 80.0
    axis_title = 20.0
    tick = 17.0
    legend = 17.0
    line = 2.6
    frame = 1.8
    palette = "trend_family"
    transparency = 8.0
    heatmap_palette = "RedWhiteBlue.PAL" if signed_values else "Viridis.PAL"
    layer_width_override: float | None = None

    if plot_kind == "bar_error":
        width = min(42.0, max(22.0, 15.0 + rows * 1.55 + series * 0.85))
        height = 16.5 if rows <= 6 else 18.0
        left = 16.0
        palette = "comparison_family"
        transparency = 14.0
    elif plot_kind == "horizontal_bar":
        width = min(46.0, max(27.0, 22.0 + label_len * 0.38 + series * 0.8))
        height = min(30.0, max(15.5, 10.5 + rows * 1.15))
        left = min(57.0, max(35.0, 31.0 + label_len * 0.72))
        top = 5.0
        # Reserve a real bottom gutter for tick labels and the value-axis title.
        layer_height = 77.0
        palette = "diverging_effect" if signed_values else "ablation_blue"
        transparency = 16.0
    elif plot_kind in {"stacked_bar", "percent_stacked_bar"}:
        width = min(38.0, max(22.0, 16.0 + rows * 1.65 + series * 0.35))
        height = 16.5
        left = 17.0
        palette = "stacked_blue" if plot_kind == "stacked_bar" else "composition_lilac"
        transparency = 5.0
        if plot_kind == "percent_stacked_bar":
            # Keep a dedicated right-side legend column.  The wider page
            # preserves the physical data-field width instead of shrinking
            # typography to force the legend inside the bars.
            width = min(44.0, max(31.0, width + 7.0) + 0.01)
            left = 14.0
            layer_width_override = 62.0
            legend = 18.0
    elif plot_kind == "pie":
        width = min(34.0, max(22.0, 20.0 + rows * 0.6))
        height = min(24.0, max(16.0, 14.0 + rows * 0.4))
        palette = "composition_teal"
    elif plot_kind == "sankey":
        width = min(46.0, max(30.0, 27.0 + rows * 0.22))
        height = min(28.0, max(17.0, 15.0 + rows * 0.12))
        axis_title = 18.0
        tick = 16.0
        legend = 15.0
        palette = "flow_family"
        transparency = 18.0
    elif plot_kind == "radar":
        width = min(36.0, max(28.0, 24.0 + rows * 0.70))
        height = min(26.0, max(18.5, 15.0 + rows * 0.70))
        left = 20.0
        top = 8.0
        layer_height = 76.0
        layer_width_override = 54.0
        palette = "comparison_family"
        transparency = 82.0
    elif plot_kind == "heatmap":
        # Origin's official heatmap templates include an attached color scale
        # and enforce a practical minimum page extent.  Start above that
        # threshold, then grow with matrix dimensions and label length.
        width = min(48.0, max(28.0, 19.0 + series * 1.55 + label_len * 0.24))
        height = min(36.0, max(21.0, 12.0 + rows * 0.72))
        left = min(35.0, max(17.0, 15.0 + label_len * 0.55))
        top = 5.0
        layer_height = 82.0
        layer_width_override = max(52.0, 89.0 - left)
        axis_title = 18.0
        tick = 15.0 if rows > 12 or series > 10 else 17.0
        legend = tick
    elif plot_kind in {"raw_summary", "violin", "raincloud"}:
        width = min(42.0, max(23.5, 17.0 + series * 3.1 + label_len * 0.20))
        if plot_kind == "raincloud":
            # Origin stores page extent on a discrete internal grid.  This
            # 0.01 cm nudge keeps the frozen physical contract within the
            # existing strict 0.01 cm readback gate for common three-group
            # Raincloud pages instead of weakening verification tolerance.
            width = min(42.0, width + 0.01)
        height = 17.0 if rows <= 60 else 18.5
        left = 17.0
        top = 5.0
        layer_height = 80.0
        palette = "distribution_family"
        transparency = 42.0 if plot_kind == "violin" else 34.0 if plot_kind == "raincloud" else 18.0
    elif plot_kind == "histogram":
        width = min(36.0, max(24.0, 22.0 + series * 1.4))
        height = 17.0
        left = 17.0
        palette = "distribution_family"
        transparency = 28.0
    elif plot_kind == "forest":
        width = min(48.0, max(28.0, 23.0 + label_len * 0.48))
        height = min(32.0, max(16.5, 10.5 + rows * 1.25))
        left = min(48.0, max(25.0, 22.0 + label_len * 0.75))
        top = 5.0
        layer_height = 82.0
        palette = "evidence_family"
        transparency = 5.0
    elif plot_kind == "bubble":
        width = 27.0
        height = 18.0
        left = 17.0
        palette = "evidence_family"
        transparency = 25.0
    elif plot_kind == "trajectory3d":
        # Verified Origin 2024b glTraject geometry and physical typography.
        width = 24.0
        height = 18.0
        left = 18.0
        top = 5.0
        layer_height = 70.0
        layer_width_override = 64.0
        axis_title = 22.0
        tick = 18.0
        legend = 17.0
        line = 2.2
        palette = "trajectory3d_family"
        transparency = 0.0
    elif plot_kind == "diagnostic_curve":
        width = min(34.0, max(23.5, 22.5 + series * 0.85))
        height = width
        left = 17.0
        top = 5.0
        layer_height = 79.0
        palette = "medical_ai"
        line = 2.4
        transparency = 5.0
    elif plot_kind == "calibration_curve":
        width = 25.5
        height = 25.5
        left = 17.0
        top = 5.0
        layer_height = 79.0
        palette = "medical_ai"
        line = 2.2
        transparency = 68.0
    elif plot_kind == "decision_curve":
        width = min(34.0, max(27.0, 24.0 + series * 0.8))
        height = 18.0
        left = 17.0
        palette = "medical_ai"
        line = 2.2
        transparency = 5.0
    elif plot_kind == "bland_altman":
        width = 27.0
        height = 18.0
        left = 17.0
        palette = "medical_ai"
        line = 1.8
        transparency = 22.0
    elif plot_kind == "paired_trajectory":
        width = min(34.0, max(25.0, 23.0 + min(series, 20) * 0.34))
        height = 17.0
        left = 17.0
        palette = "paired_neutral"
        line = 1.25
        transparency = 34.0
    elif plot_kind == "grouped_box":
        width = min(44.0, max(27.0, 22.0 + series * 1.25 + label_len * 0.18))
        height = 18.0
        left = 17.0
        top = 5.0
        layer_height = 78.0
        palette = "grouped_box_medical"
        line = 1.8
        legend = 18.0
        transparency = 28.0
    elif plot_kind == "pl_decay":
        width = min(36.0, max(27.0, 25.0 + series * 0.85))
        height = 18.5
        left = 17.0
        palette = "spectroscopy_jewel"
        line = 2.0
        transparency = 4.0
    elif plot_kind == "pl_spectrum":
        width = min(36.0, max(26.0, 24.0 + series * 0.80))
        height = 17.5
        left = 17.0
        palette = "spectroscopy_jewel"
        line = 2.2
        transparency = 4.0
    elif plot_kind == "uv_vis":
        width = min(38.0, max(29.0, 27.0 + series * 0.75))
        height = 20.0
        left = 17.0
        top = 5.0
        layer_height = 81.0
        palette = "spectroscopy_jewel"
        line = 2.2
        transparency = 4.0
    elif plot_kind == "shap_summary":
        width = min(48.0, max(28.0, 23.0 + label_len * 0.52))
        width = min(48.0, width + 0.01)
        height = min(32.0, max(17.0, 10.5 + rows * 1.30))
        left = min(50.0, max(25.0, 22.0 + label_len * 0.78))
        top = 7.0
        layer_height = 78.0
        palette = "medical_ai"
        transparency = 18.0
    elif plot_kind in {"line", "line_error", "scatter", "nyquist", "stacked_line"}:
        width = min(34.0, max(23.5, 22.0 + series * 0.75))
        height = 16.5 if series <= 5 else 18.0
        palette = "trend_family"
        transparency = 8.0

    if category_rotation_deg:
        height = max(height, 18.5)
        layer_height = min(layer_height, 68.0)

    layer_width = layer_width_override or max(34.0, 96.0 - left)
    return AdaptiveOriginStyle(
        profile_name=f"adaptive-{template_id}-{plot_kind}",
        page_width_cm=round(width, 2),
        page_height_cm=round(height, 2),
        layer_left_percent=round(left, 2),
        layer_top_percent=top,
        layer_width_percent=round(layer_width, 2),
        layer_height_percent=layer_height,
        axis_title_size_pt=axis_title,
        tick_label_size_pt=tick,
        legend_size_pt=legend,
        plot_line_width_pt=line,
        frame_line_width_pt=frame,
        major_tick_length_pt=5.5,
        minor_tick_length_pt=3.0,
        error_bar_width_pt=1.8,
        bar_border_width_pt=1.4,
        fill_transparency_percent=transparency,
        palette_name=palette,
        heatmap_palette=heatmap_palette,
    )


__all__ = [
    "AdaptiveOriginStyle",
    "PALETTES",
    "interpolate_hex_colors",
    "palette_colors",
    "resolve_adaptive_style",
    "signed_effect_colors",
]
