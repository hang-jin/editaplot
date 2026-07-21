"""Curated, machine-checkable scientific colour palettes.

The catalogue deliberately stores only independently normalized colour values
and usage metadata.  It does not depend on, or expose, any reference image.
Rendering code can therefore freeze a ``palette_id`` in a figure contract and
recreate the same colours without consulting external assets.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Final, Mapping


_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^#[0-9A-F]{6}$")
_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED_MODES: Final[frozenset[str]] = frozenset(
    {"qualitative", "sequential", "diverging", "accent"}
)
_RISK_LEVELS: Final[frozenset[str]] = frozenset({"low", "medium", "high"})
_PUBLIC_DEFAULT_COUNT: Final[int] = 8


@dataclass(frozen=True, slots=True)
class ScientificPalette:
    """A reusable scientific palette plus its publication guardrails."""

    palette_id: str
    name_zh: str
    name_en: str
    colors: tuple[str, ...]
    background: str
    neutral_text: str
    allowed_modes: tuple[str, ...]
    recommended_charts: tuple[str, ...]
    max_qualitative_categories: int
    requires_redundant_encoding: bool
    cvd_risk: str
    grayscale_risk: str
    public_default: bool
    source_note: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of the palette contract."""

        return {
            "palette_id": self.palette_id,
            "name_zh": self.name_zh,
            "name_en": self.name_en,
            "colors": list(self.colors),
            "background": self.background,
            "neutral_text": self.neutral_text,
            "allowed_modes": list(self.allowed_modes),
            "recommended_charts": list(self.recommended_charts),
            "max_qualitative_categories": self.max_qualitative_categories,
            "requires_redundant_encoding": self.requires_redundant_encoding,
            "cvd_risk": self.cvd_risk,
            "grayscale_risk": self.grayscale_risk,
            "public_default": self.public_default,
            "source_note": self.source_note,
        }


_SOURCE_NOTE: Final[str] = (
    "Independently normalized from user-provided scientific colour references; "
    "validate contrast and redundant encoding against the final figure."
)


def _palette(
    palette_id: str,
    name_zh: str,
    name_en: str,
    colors: tuple[str, ...],
    *,
    background: str,
    neutral_text: str,
    allowed_modes: tuple[str, ...],
    recommended_charts: tuple[str, ...],
    max_qualitative_categories: int,
    requires_redundant_encoding: bool,
    cvd_risk: str,
    grayscale_risk: str,
    public_default: bool,
) -> ScientificPalette:
    return ScientificPalette(
        palette_id=palette_id,
        name_zh=name_zh,
        name_en=name_en,
        colors=colors,
        background=background,
        neutral_text=neutral_text,
        allowed_modes=allowed_modes,
        recommended_charts=recommended_charts,
        max_qualitative_categories=max_qualitative_categories,
        requires_redundant_encoding=requires_redundant_encoding,
        cvd_risk=cvd_risk,
        grayscale_risk=grayscale_risk,
        public_default=public_default,
        source_note=_SOURCE_NOTE,
    )


_PALETTES: Final[dict[str, ScientificPalette]] = {
    "blue_coral": _palette(
        "blue_coral",
        "远海蓝珊瑚",
        "Blue Coral",
        ("#1E3A66", "#4F8FD6", "#8FA6E3", "#F2D6A6", "#C5B5E8", "#E76B6B", "#F7F8FB"),
        background="#F7F8FB",
        neutral_text="#1E3A66",
        allowed_modes=("qualitative", "diverging", "accent"),
        recommended_charts=("grouped_bar", "line", "scatter", "box", "medical_comparison"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "ocean_coral": _palette(
        "ocean_coral",
        "深海珊瑚",
        "Ocean Coral",
        ("#17304C", "#1F6F78", "#79B8C9", "#8A7DB3", "#E07A5F", "#D5A44C", "#D9E1E8"),
        background="#D9E1E8",
        neutral_text="#17304C",
        allowed_modes=("qualitative", "diverging", "accent"),
        recommended_charts=("line", "grouped_bar", "scatter", "decision_curve", "bland_altman"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "plum_rose": _palette(
        "plum_rose",
        "梅紫玫瑰",
        "Plum Rose",
        ("#5B1061", "#9B2D6F", "#F06A99", "#FFC2D6", "#9A88C9", "#D9CDEA", "#2A1A4A", "#FAFAFC"),
        background="#FAFAFC",
        neutral_text="#2A1A4A",
        allowed_modes=("sequential", "qualitative", "accent"),
        recommended_charts=("heatmap", "density", "violin", "box", "single_family_bar"),
        max_qualitative_categories=4,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="high",
        public_default=True,
    ),
    "navy_cyan_gold": _palette(
        "navy_cyan_gold",
        "海军蓝青金",
        "Navy Cyan Gold",
        ("#0B1533", "#1E4FBE", "#00E5FF", "#6B2FA6", "#B88CF2", "#D4A247", "#F6F7FA"),
        background="#F6F7FA",
        neutral_text="#0B1533",
        allowed_modes=("qualitative", "accent"),
        recommended_charts=("spectra", "xrd", "line", "scatter", "grouped_bar"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "navy_ember": _palette(
        "navy_ember",
        "藏蓝余烬",
        "Navy Ember",
        ("#0E1A2B", "#4A6FA5", "#7B6BB2", "#E24C3B", "#F08A1A", "#F6D48A", "#DFE8F6"),
        background="#DFE8F6",
        neutral_text="#0E1A2B",
        allowed_modes=("qualitative", "diverging", "accent"),
        recommended_charts=("bar", "line", "forest", "volcano", "model_comparison"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "forest_amber": _palette(
        "forest_amber",
        "森林琥珀",
        "Forest Amber",
        ("#1F5A3A", "#6BAF45", "#A8D23B", "#EACB22", "#F28C18", "#D35400", "#1E2A39"),
        background="#FFFFFF",
        neutral_text="#1E2A39",
        allowed_modes=("sequential", "accent"),
        recommended_charts=("spectra", "line", "heatmap", "composition", "trend"),
        max_qualitative_categories=1,
        requires_redundant_encoding=True,
        cvd_risk="high",
        grayscale_risk="medium",
        public_default=False,
    ),
    "violet_lime": _palette(
        "violet_lime",
        "紫罗兰青柠",
        "Violet Lime",
        ("#0D1020", "#3B1E5A", "#7A2E83", "#E23D8A", "#FF688E", "#A6CC55", "#6E8A6A", "#F6F4F1"),
        background="#F6F4F1",
        neutral_text="#0D1020",
        allowed_modes=("qualitative", "accent"),
        recommended_charts=("network", "sankey", "scatter", "feature_importance"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="high",
        grayscale_risk="high",
        public_default=False,
    ),
    "deep_sea_gold": _palette(
        "deep_sea_gold",
        "深海鎏金",
        "Deep Sea Gold",
        ("#0B1D2A", "#1F6F7A", "#5BA9A6", "#A7D5C9", "#F2B848", "#F7E9C6"),
        background="#F7E9C6",
        neutral_text="#0B1D2A",
        allowed_modes=("sequential", "qualitative", "accent"),
        recommended_charts=("spectra", "xps", "line", "area", "heatmap"),
        max_qualitative_categories=4,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "sky_terra": _palette(
        "sky_terra",
        "天青陶土",
        "Sky Terra",
        ("#4FA3D9", "#2FA3A3", "#D96A4A", "#6A8F3F", "#1B2333", "#B6BCC4", "#F3E9D5"),
        background="#F3E9D5",
        neutral_text="#1B2333",
        allowed_modes=("qualitative", "diverging", "accent"),
        recommended_charts=("grouped_bar", "scatter", "line", "box", "multi_panel"),
        max_qualitative_categories=5,
        requires_redundant_encoding=True,
        cvd_risk="medium",
        grayscale_risk="medium",
        public_default=True,
    ),
    "amber_lavender": _palette(
        "amber_lavender",
        "琥珀薰衣草",
        "Amber Lavender",
        ("#F1B84B", "#F28C3A", "#E45A2A", "#7A2D1E", "#F6D7C2", "#B7BDE3", "#FAFAFA"),
        background="#FAFAFA",
        neutral_text="#7A2D1E",
        allowed_modes=("sequential", "diverging", "qualitative", "accent"),
        recommended_charts=("bar", "trend", "distribution", "heatmap", "annotation"),
        max_qualitative_categories=4,
        requires_redundant_encoding=True,
        cvd_risk="high",
        grayscale_risk="high",
        public_default=True,
    ),
}

PALETTE_IDS: Final[tuple[str, ...]] = tuple(_PALETTES)


def _rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[index : index + 2], 16) / 255.0 for index in (1, 3, 5))  # type: ignore[return-value]


def _relative_luminance(hex_color: str) -> float:
    def linearize(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = _rgb(hex_color)
    return 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)


def _contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def validate_palette(palette: ScientificPalette) -> ScientificPalette:
    """Validate one contract and return it, or raise a descriptive error."""

    if not isinstance(palette, ScientificPalette):
        raise TypeError("palette must be a ScientificPalette")
    if not _ID_RE.fullmatch(palette.palette_id):
        raise ValueError(f"Invalid palette_id: {palette.palette_id!r}")
    if not palette.name_zh.strip() or not palette.name_en.strip():
        raise ValueError(f"{palette.palette_id}: bilingual names are required")
    if len(palette.colors) < 3 or len(set(palette.colors)) != len(palette.colors):
        raise ValueError(f"{palette.palette_id}: colors must contain at least three unique values")
    for field_name, values in (
        ("colors", palette.colors),
        ("background", (palette.background,)),
        ("neutral_text", (palette.neutral_text,)),
    ):
        invalid = [value for value in values if not _HEX_RE.fullmatch(value)]
        if invalid:
            raise ValueError(f"{palette.palette_id}: invalid {field_name} HEX value(s): {invalid}")
    if palette.background == palette.neutral_text:
        raise ValueError(f"{palette.palette_id}: background and neutral_text must differ")
    if _relative_luminance(palette.neutral_text) >= 0.45:
        raise ValueError(f"{palette.palette_id}: neutral_text is too light for reliable publication text")
    if _contrast_ratio(palette.neutral_text, palette.background) < 4.5:
        raise ValueError(f"{palette.palette_id}: neutral_text/background contrast is below 4.5:1")
    modes = set(palette.allowed_modes)
    if not modes or not modes.issubset(_ALLOWED_MODES) or len(modes) != len(palette.allowed_modes):
        raise ValueError(f"{palette.palette_id}: invalid or duplicate allowed_modes")
    if not palette.recommended_charts or any(not chart.strip() for chart in palette.recommended_charts):
        raise ValueError(f"{palette.palette_id}: recommended_charts must not be empty")
    if len(set(palette.recommended_charts)) != len(palette.recommended_charts):
        raise ValueError(f"{palette.palette_id}: recommended_charts must be unique")
    if not 1 <= palette.max_qualitative_categories <= len(palette.colors):
        raise ValueError(f"{palette.palette_id}: invalid max_qualitative_categories")
    if palette.cvd_risk not in _RISK_LEVELS or palette.grayscale_risk not in _RISK_LEVELS:
        raise ValueError(f"{palette.palette_id}: risk levels must be low, medium, or high")
    if not palette.source_note.strip():
        raise ValueError(f"{palette.palette_id}: source_note is required")
    return palette


def validate_catalog() -> tuple[ScientificPalette, ...]:
    """Validate catalogue-wide invariants, including the eight launch defaults."""

    validated = tuple(validate_palette(palette) for palette in _PALETTES.values())
    if tuple(palette.palette_id for palette in validated) != PALETTE_IDS:
        raise ValueError("Palette identifiers and catalogue order are inconsistent")
    public_count = sum(palette.public_default for palette in validated)
    if public_count != _PUBLIC_DEFAULT_COUNT:
        raise ValueError(
            f"Expected {_PUBLIC_DEFAULT_COUNT} public-default palettes, found {public_count}"
        )
    return validated


def get_palette(palette_id: str) -> ScientificPalette:
    """Return a palette by stable ID and reject unknown identifiers."""

    try:
        return _PALETTES[palette_id]
    except (KeyError, TypeError) as exc:
        available = ", ".join(PALETTE_IDS)
        raise KeyError(f"Unknown palette_id {palette_id!r}. Available: {available}") from exc


def list_palettes(
    *, public_only: bool = False, allowed_mode: str | None = None
) -> tuple[ScientificPalette, ...]:
    """List palettes in stable display order with optional launch/mode filters."""

    if allowed_mode is not None and allowed_mode not in _ALLOWED_MODES:
        raise ValueError(f"Unknown palette mode {allowed_mode!r}")
    palettes = validate_catalog()
    return tuple(
        palette
        for palette in palettes
        if (not public_only or palette.public_default)
        and (allowed_mode is None or allowed_mode in palette.allowed_modes)
    )


def palette_to_dict(palette: ScientificPalette | str) -> dict[str, Any]:
    """Serialize a palette object or ID to a detached JSON-ready dictionary."""

    resolved = get_palette(palette) if isinstance(palette, str) else validate_palette(palette)
    return resolved.to_dict()


# Compact aliases are convenient for Skill scripts while the explicit names remain
# the preferred public Python API.
get = get_palette
validate = validate_palette


# Fail fast during import if catalogue edits break a publication guardrail.
validate_catalog()


__all__ = [
    "PALETTE_IDS",
    "ScientificPalette",
    "get",
    "get_palette",
    "list_palettes",
    "palette_to_dict",
    "validate",
    "validate_catalog",
    "validate_palette",
]
