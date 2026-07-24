"""Deterministic semantic proposals for ordinary and refined XRD tables.

This module recognizes documented column roles and never identifies phases,
peaks, or fitted results from curve shape.  It does not render or modify data.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .data_loader import LoadedTable
from .semantic_contract import (
    DataDisposition,
    FigureElement,
    SemanticAmbiguity,
    SemanticDataItem,
    SemanticProposal,
)

XrdSourceProfile = Literal[
    "gsas_ii_powder_csv",
    "gsas_ii_publication_csv",
    "generic_rietveld",
    "ordinary_xrd",
]

GSAS_II_POWDER_CSV = "gsas_ii_powder_csv"
GSAS_II_PUBLICATION_CSV = "gsas_ii_publication_csv"


class XrdSemanticError(ValueError):
    """Stable failure for an incomplete or contradictory XRD role contract."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class _ColumnProfile:
    column: str
    index: int
    canonical: str
    numeric_count: int
    nonempty_count: int
    total_count: int
    minimum: float | None
    maximum: float | None

    @property
    def numeric(self) -> bool:
        return bool(self.nonempty_count and self.numeric_count == self.nonempty_count)

    @property
    def dense_numeric(self) -> bool:
        return bool(
            self.numeric
            and self.total_count
            and self.numeric_count >= max(2, math.ceil(self.total_count * 0.8))
        )


_X_ALIASES = frozenset(
    {
        "x",
        "2theta",
        "twotheta",
        "diffractionangle",
        "x2theta",
        "衍射角",
        "两倍衍射角",
    }
)
_OBSERVED_ALIASES = frozenset(
    {
        "obs",
        "yobs",
        "observed",
        "observedintensity",
        "iobs",
        "measured",
        "measuredintensity",
        "experimental",
        "experimentalintensity",
        "实测",
        "实测强度",
        "观察",
        "观察强度",
        "实验强度",
    }
)
_CALCULATED_ALIASES = frozenset(
    {
        "calc",
        "ycalc",
        "calculated",
        "calculatedintensity",
        "icalc",
        "fitted",
        "fittedintensity",
        "计算",
        "计算强度",
        "拟合",
        "拟合强度",
    }
)
_BACKGROUND_ALIASES = frozenset(
    {
        "bkg",
        "ybkg",
        "background",
        "backgroundintensity",
        "baseline",
        "背景",
        "背景强度",
        "基线",
    }
)
_DIFFERENCE_ALIASES = frozenset(
    {
        "diff",
        "difference",
        "residual",
        "residuals",
        "obscalc",
        "observedcalculated",
        "差值",
        "残差",
    }
)
_WEIGHT_ALIASES = frozenset({"weight", "weights", "yweight", "权重"})
_Q_ALIASES = frozenset({"q", "scatteringvector", "散射矢量"})
_USED_ALIASES = frozenset({"used", "use", "fitmask", "included", "使用", "拟合使用"})
_DIFF_SIGMA_ALIASES = frozenset(
    {
        "diffsigma",
        "differencesigma",
        "residualsigma",
        "weightedresidual",
        "差值sigma",
        "加权残差",
    }
)
_AXIS_LIMIT_ALIASES = frozenset({"axislimits", "axislimit", "坐标轴范围", "轴范围"})
_TICK_POSITION_ALIASES = frozenset({"tickpos", "tickposition", "phasetickpos", "刻线位置", "物相刻线位置"})
_ORDINARY_SERIES_TOKENS = (
    "intensity",
    "counts",
    "count",
    "sample",
    "specimen",
    "scan",
    "pattern",
    "intens",
    "强度",
    "计数",
    "样品",
    "试样",
    "图谱",
)
_REFINEMENT_MARKERS = (
    _OBSERVED_ALIASES
    | _CALCULATED_ALIASES
    | _BACKGROUND_ALIASES
    | _DIFFERENCE_ALIASES
    | _WEIGHT_ALIASES
    | _USED_ALIASES
    | _DIFF_SIGMA_ALIASES
    | _AXIS_LIMIT_ALIASES
    | _TICK_POSITION_ALIASES
)


def _canonical(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("2θ", "2theta").replace("θ", "theta")
    text = text.replace("−", "-")
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _column_profiles(loaded: LoadedTable) -> tuple[_ColumnProfile, ...]:
    profiles: list[_ColumnProfile] = []
    for index, column in enumerate(loaded.columns):
        raw = loaded.frame[column]
        text = raw.astype("string").str.strip()
        nonempty = text.notna() & text.ne("")
        numeric = pd.to_numeric(raw.where(nonempty), errors="coerce")
        valid = numeric.notna()
        values = numeric.loc[valid]
        profiles.append(
            _ColumnProfile(
                column=column,
                index=index,
                canonical=_canonical(column),
                numeric_count=int(valid.sum()),
                nonempty_count=int(nonempty.sum()),
                total_count=len(raw),
                minimum=float(values.min()) if not values.empty else None,
                maximum=float(values.max()) if not values.empty else None,
            )
        )
    return tuple(profiles)


def _item_id(index: int) -> str:
    return f"src:{index:03d}"


def _matches_alias(canonical: str, aliases: frozenset[str]) -> bool:
    if canonical in aliases:
        return True
    return any(
        len(alias) >= 4 and (canonical.startswith(alias) or canonical.endswith(alias)) for alias in aliases
    )


def _is_publication_x(canonical: str) -> bool:
    return canonical in _X_ALIASES or canonical.startswith(("x2theta", "xq", "xd", "xtof"))


def _is_ordinary_series(canonical: str) -> bool:
    return any(token in canonical for token in _ORDINARY_SERIES_TOKENS)


def _phase_identity(canonical: str) -> str | None:
    for prefix in ("phase", "bragg", "reflection", "物相", "相"):
        if canonical.startswith(prefix):
            identity = canonical[len(prefix) :]
            return identity or None
    return None


def _profile_by_alias(
    profiles: tuple[_ColumnProfile, ...],
    aliases: frozenset[str],
) -> list[_ColumnProfile]:
    return [profile for profile in profiles if _matches_alias(profile.canonical, aliases)]


def _unique_role(
    profiles: tuple[_ColumnProfile, ...],
    aliases: frozenset[str],
    role: str,
    *,
    required: bool,
    exclude_aliases: frozenset[str] | None = None,
) -> _ColumnProfile | None:
    candidates = _profile_by_alias(profiles, aliases)
    if exclude_aliases:
        candidates = [
            profile for profile in candidates if not _matches_alias(profile.canonical, exclude_aliases)
        ]
    if len(candidates) > 1:
        raise XrdSemanticError(
            "xrd_role_ambiguous",
            f"Multiple columns match the required XRD role {role!r}.",
            role=role,
            columns=[item.column for item in candidates],
        )
    if not candidates:
        if required:
            raise XrdSemanticError(
                "xrd_required_role_missing",
                f"XRD refinement data is missing the required role {role!r}.",
                role=role,
            )
        return None
    return candidates[0]


def _has_signature(
    profiles: tuple[_ColumnProfile, ...],
    aliases: tuple[frozenset[str], ...],
) -> bool:
    return all(bool(_profile_by_alias(profiles, group)) for group in aliases)


def detect_xrd_source_profile(loaded: LoadedTable) -> XrdSourceProfile:
    """Classify a documented XRD table without using its filename or path."""

    if loaded.source_profile in {GSAS_II_POWDER_CSV, GSAS_II_PUBLICATION_CSV}:
        return loaded.source_profile
    profiles = _column_profiles(loaded)
    powder_signature = _has_signature(
        profiles,
        (
            frozenset({"x"}),
            frozenset({"yobs"}),
            frozenset({"weight"}),
            frozenset({"ycalc"}),
            frozenset({"ybkg"}),
            frozenset({"q"}),
        ),
    )
    if powder_signature:
        return GSAS_II_POWDER_CSV
    publication_difference = [
        profile
        for profile in _profile_by_alias(profiles, _DIFFERENCE_ALIASES)
        if not _matches_alias(profile.canonical, _DIFF_SIGMA_ALIASES)
    ]
    publication_signature = (
        _has_signature(
            profiles,
            (
                _USED_ALIASES,
                _OBSERVED_ALIASES,
                _CALCULATED_ALIASES,
                _BACKGROUND_ALIASES,
            ),
        )
        and bool(publication_difference)
        and any(_is_publication_x(profile.canonical) for profile in profiles)
    )
    if publication_signature:
        return GSAS_II_PUBLICATION_CSV
    if any(profile.canonical in _REFINEMENT_MARKERS for profile in profiles):
        return "generic_rietveld"
    return "ordinary_xrd"


def _phase_column_is_explicit_and_sparse(
    phase: _ColumnProfile,
    x_profile: _ColumnProfile,
) -> bool:
    identity = _phase_identity(phase.canonical)
    if identity is None or not phase.numeric or phase.numeric_count < 1:
        return False
    if phase.numeric_count >= max(2, math.ceil(x_profile.numeric_count * 0.8)):
        return False
    if (
        x_profile.minimum is None
        or x_profile.maximum is None
        or phase.minimum is None
        or phase.maximum is None
    ):
        return False
    span = max(x_profile.maximum - x_profile.minimum, 1.0)
    tolerance = span * 1e-6
    return bool(
        phase.minimum >= x_profile.minimum - tolerance and phase.maximum <= x_profile.maximum + tolerance
    )


def _data_item(
    profile: _ColumnProfile,
    semantic_role: str,
    disposition: DataDisposition,
    confidence: float,
    *evidence_codes: str,
) -> SemanticDataItem:
    return SemanticDataItem(
        item_id=_item_id(profile.index),
        source_column=profile.column,
        semantic_role=semantic_role,
        disposition=disposition,
        confidence=confidence,
        evidence_codes=tuple(evidence_codes),
    )


def _unknown_item(
    profile: _ColumnProfile,
    ambiguities: list[SemanticAmbiguity],
) -> SemanticDataItem:
    numeric = profile.numeric_count > 0
    if numeric:
        ambiguity_id = f"unknown_numeric_column_{profile.index:03d}"
        ambiguities.append(
            SemanticAmbiguity(
                ambiguity_id=ambiguity_id,
                code="xrd_unknown_numeric_column",
                question_zh=f"请确认数值列“{profile.column}”在 XRD 图中的科学角色。",
                item_ids=(_item_id(profile.index),),
                options=(
                    "intensity_series",
                    "support_only",
                    "retain_not_render",
                ),
                blocking=True,
            )
        )
        return _data_item(
            profile,
            "unclassified_numeric",
            DataDisposition.UNCERTAIN,
            0.0,
            "numeric_role_not_identified",
        )
    return _data_item(
        profile,
        "unclassified_metadata",
        DataDisposition.RETAIN_NOT_RENDER,
        0.8,
        "non_numeric_metadata_preserved",
    )


def _role_map(
    profiles: tuple[_ColumnProfile, ...],
    profile_kind: XrdSourceProfile,
) -> tuple[
    dict[int, SemanticDataItem],
    list[FigureElement],
    list[SemanticAmbiguity],
]:
    items: dict[int, SemanticDataItem] = {}
    elements: list[FigureElement] = []
    ambiguities: list[SemanticAmbiguity] = []

    if profile_kind == GSAS_II_PUBLICATION_CSV:
        x_candidates = [profile for profile in profiles if _is_publication_x(profile.canonical)]
        if len(x_candidates) != 1:
            raise XrdSemanticError(
                "xrd_required_role_missing" if not x_candidates else "xrd_role_ambiguous",
                "GSAS-II Publication CSV needs exactly one documented X column.",
                role="x_coordinate",
                columns=[item.column for item in x_candidates],
            )
        x_profile = x_candidates[0]
    else:
        x_profile = _unique_role(profiles, _X_ALIASES, "x_coordinate", required=True)
        if x_profile is None:
            raise XrdSemanticError(
                "xrd_required_role_missing",
                "XRD data is missing the required x-coordinate column.",
                role="x_coordinate",
            )

    items[x_profile.index] = _data_item(
        x_profile,
        "x_coordinate",
        DataDisposition.RENDER_PRIMARY,
        0.99 if profile_kind.startswith("gsas_ii") else 0.96,
        "documented_x_header",
    )
    elements.append(
        FigureElement(
            "x_axis",
            "axis",
            (_item_id(x_profile.index),),
            required=True,
            axis="x",
        )
    )

    if profile_kind == "ordinary_xrd":
        for profile in profiles:
            if profile.index == x_profile.index:
                continue
            if profile.dense_numeric and _is_ordinary_series(profile.canonical):
                items[profile.index] = _data_item(
                    profile,
                    "intensity_series",
                    DataDisposition.RENDER_PRIMARY,
                    0.92,
                    "ordinary_xrd_series_header",
                    "dense_numeric_on_x_grid",
                )
                elements.append(
                    FigureElement(
                        f"intensity_series_{profile.index:03d}",
                        "line",
                        (_item_id(profile.index),),
                        required=True,
                        axis="main_y",
                        legend_label=profile.column,
                    )
                )
            else:
                items[profile.index] = _unknown_item(profile, ambiguities)
        return items, elements, ambiguities

    observed = _unique_role(profiles, _OBSERVED_ALIASES, "observed_intensity", required=True)
    calculated = _unique_role(
        profiles,
        _CALCULATED_ALIASES,
        "calculated_intensity",
        required=True,
    )
    if observed is None or calculated is None:
        missing_role = "observed_intensity" if observed is None else "calculated_intensity"
        raise XrdSemanticError(
            "xrd_required_role_missing",
            f"XRD refinement data is missing the required role {missing_role!r}.",
            role=missing_role,
        )
    if observed.index == calculated.index:
        raise XrdSemanticError(
            "xrd_role_conflict",
            "Observed and calculated intensities must use different source columns.",
        )
    for profile, role, element_id, kind, label in (
        (observed, "observed_intensity", "observed_points", "markers", "Observed"),
        (calculated, "calculated_intensity", "calculated_curve", "line", "Calculated"),
    ):
        items[profile.index] = _data_item(
            profile,
            role,
            DataDisposition.RENDER_PRIMARY,
            0.99,
            "documented_refinement_header",
        )
        elements.append(
            FigureElement(
                element_id,
                kind,
                (_item_id(profile.index),),
                required=True,
                axis="main_y",
                legend_label=label,
            )
        )

    background = _unique_role(
        profiles,
        _BACKGROUND_ALIASES,
        "background_intensity",
        required=False,
    )
    if background is not None:
        items[background.index] = _data_item(
            background,
            "background_intensity",
            DataDisposition.RENDER_SECONDARY,
            0.99,
            "documented_background_header",
            "optional_secondary_curve",
        )
        elements.append(
            FigureElement(
                "background_curve",
                "line",
                (_item_id(background.index),),
                required=False,
                visible_by_default=True,
                axis="main_y",
                legend_label="Background",
            )
        )

    difference = _unique_role(
        profiles,
        _DIFFERENCE_ALIASES,
        "difference_curve",
        required=profile_kind == GSAS_II_PUBLICATION_CSV,
        exclude_aliases=_DIFF_SIGMA_ALIASES,
    )
    if difference is not None:
        evidence = (
            ("documented_publication_difference", "upstream_display_offset_preserved")
            if profile_kind == GSAS_II_PUBLICATION_CSV
            else ("supplied_difference_column",)
        )
        items[difference.index] = _data_item(
            difference,
            "difference_curve",
            DataDisposition.RENDER_SECONDARY,
            0.99 if profile_kind == GSAS_II_PUBLICATION_CSV else 0.9,
            *evidence,
        )
        elements.append(
            FigureElement(
                "difference_curve",
                "line",
                (_item_id(difference.index),),
                required=False,
                visible_by_default=True,
                axis="residual_y",
                legend_label="Difference",
            )
        )

    support_roles = (
        (_WEIGHT_ALIASES, "statistical_weight", DataDisposition.SUPPORT_ONLY),
        (_Q_ALIASES, "alternative_q_coordinate", DataDisposition.RETAIN_NOT_RENDER),
        (_USED_ALIASES, "fit_mask", DataDisposition.SUPPORT_ONLY),
        (_DIFF_SIGMA_ALIASES, "weighted_residual_diagnostic", DataDisposition.RETAIN_NOT_RENDER),
        (_AXIS_LIMIT_ALIASES, "upstream_axis_limits", DataDisposition.SUPPORT_ONLY),
    )
    for aliases, role, disposition in support_roles:
        matches = _profile_by_alias(profiles, aliases)
        if len(matches) > 1:
            raise XrdSemanticError(
                "xrd_role_ambiguous",
                f"Multiple columns match XRD support role {role!r}.",
                role=role,
                columns=[item.column for item in matches],
            )
        if matches:
            profile = matches[0]
            items[profile.index] = _data_item(
                profile,
                role,
                disposition,
                0.99 if profile_kind.startswith("gsas_ii") else 0.9,
                "documented_support_column",
                "not_a_curve",
            )

    valid_phase_count = 0
    for profile in profiles:
        if profile.index in items:
            continue
        if _phase_identity(profile.canonical) is not None:
            if _phase_column_is_explicit_and_sparse(profile, x_profile):
                valid_phase_count += 1
                items[profile.index] = _data_item(
                    profile,
                    "phase_reflection_positions",
                    DataDisposition.RENDER_SECONDARY,
                    0.95,
                    "explicit_phase_identity",
                    "sparse_positions_within_x_range",
                    "source_phase_label_preserved",
                )
                elements.append(
                    FigureElement(
                        f"phase_ticks_{profile.index:03d}",
                        "phase_ticks",
                        (_item_id(profile.index),),
                        required=False,
                        visible_by_default=True,
                        axis="phase_ticks",
                        legend_label=profile.column,
                    )
                )
            else:
                items[profile.index] = _unknown_item(profile, ambiguities)

    tick_matches = _profile_by_alias(profiles, _TICK_POSITION_ALIASES)
    if len(tick_matches) > 1:
        raise XrdSemanticError(
            "xrd_role_ambiguous",
            "Multiple tick-position control columns were found.",
            role="phase_tick_position_control",
            columns=[item.column for item in tick_matches],
        )
    if tick_matches:
        tick = tick_matches[0]
        items[tick.index] = _data_item(
            tick,
            ("phase_tick_position_control" if valid_phase_count else "unbound_phase_tick_metadata"),
            (DataDisposition.SUPPORT_ONLY if valid_phase_count else DataDisposition.RETAIN_NOT_RENDER),
            0.98,
            "documented_tick_position_control",
            "not_a_curve",
        )

    for profile in profiles:
        if profile.index not in items:
            items[profile.index] = _unknown_item(profile, ambiguities)
    return items, elements, ambiguities


def propose_xrd_semantics(loaded: LoadedTable) -> SemanticProposal:
    """Return a source-bound XRD interpretation without modifying the table."""

    if not loaded.columns:
        raise XrdSemanticError("xrd_columns_missing", "XRD data has no source columns.")
    profile_kind = detect_xrd_source_profile(loaded)
    profiles = _column_profiles(loaded)
    items, elements, ambiguities = _role_map(profiles, profile_kind)
    ordered_items = tuple(items[index] for index in range(len(profiles)))
    confidence = {
        GSAS_II_POWDER_CSV: 0.99,
        GSAS_II_PUBLICATION_CSV: 0.99,
        "generic_rietveld": 0.92,
        "ordinary_xrd": 0.9,
    }[profile_kind]
    if any(item.disposition is DataDisposition.UNCERTAIN for item in ordered_items):
        confidence = min(confidence, 0.62)
    proposal = SemanticProposal(
        source_sha256=loaded.source_sha256,
        source_columns=loaded.columns,
        domain_family="xrd",
        domain_mode=("rietveld_refinement" if profile_kind != "ordinary_xrd" else "ordinary_scan"),
        domain_confidence=confidence,
        source_adapter_hint=(profile_kind if profile_kind.startswith("gsas_ii") else None),
        data_items=ordered_items,
        derived_items=(),
        figure_elements=tuple(elements),
        ambiguities=tuple(ambiguities),
    )
    proposal.validate()
    return proposal


__all__ = [
    "GSAS_II_POWDER_CSV",
    "GSAS_II_PUBLICATION_CSV",
    "XrdSemanticError",
    "XrdSourceProfile",
    "detect_xrd_source_profile",
    "propose_xrd_semantics",
]
