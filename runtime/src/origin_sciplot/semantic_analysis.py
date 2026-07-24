"""Project a prepared EditaPlot route into a user-confirmable semantic contract.

This bridge deliberately operates on an already audited preparation.  It does
not inspect values, fit models, infer phases, or mutate the source table.  Its
job is narrower: classify every source column, describe the visible marks that
will consume those columns, and expose any approved display helper as an
explicit derived item.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .semantic_contract import (
    DataDisposition,
    DerivedDataItem,
    FigureElement,
    SemanticAmbiguity,
    SemanticDataItem,
    SemanticProposal,
)

_PRIMARY_ROLES = frozenset(
    {
        "x",
        "category",
        "series",
        "raw",
        "component",
        "z_real",
        "z_imag",
        "magnitude",
        "phase",
        "source",
        "target",
        "value",
        "estimate",
        "mean",
        "difference",
        "feature",
        "shap",
        "x3d",
        "y3d",
        "z3d",
        "series_id",
        "photon_energy",
        "tauc",
    }
)
_SECONDARY_ROLES = frozenset(
    {
        "error",
        "background",
        "envelope",
        "lower",
        "upper",
        "reference",
        "size",
        "bias",
        "loa_lower",
        "loa_upper",
        "treat_all",
        "treat_none",
        "feature_value",
        "fit",
        "tauc_fit",
        "bandgap",
    }
)
_SUPPORT_ROLES = frozenset({"frequency", "count"})
_XRD_RIETVELD_DISPOSITIONS = {
    "observed": DataDisposition.RENDER_PRIMARY,
    "calculated": DataDisposition.RENDER_PRIMARY,
    "background": DataDisposition.RENDER_SECONDARY,
    "difference": DataDisposition.RENDER_SECONDARY,
    "phase_tick": DataDisposition.RENDER_SECONDARY,
    "support": DataDisposition.SUPPORT_ONLY,
}


def _source_item_id(index: int) -> str:
    return f"source_{index:03d}"


def _element_kind(plot_kind: str, series_role: str) -> str:
    if series_role in {"fit", "calculated", "background"}:
        return "line"
    return {
        "scatter": "symbol",
        "bar_error": "bar",
        "horizontal_bar": "bar",
        "stacked_bar": "stacked_bar",
        "percent_stacked_bar": "stacked_bar",
        "pie": "sector",
        "heatmap": "heatmap_cell",
        "violin": "violin",
        "grouped_box": "box",
        "histogram": "bar",
        "sankey": "flow",
        "paired_trajectory": "line_symbol",
        "trajectory3d": "line_symbol",
    }.get(plot_kind, "line")


def _disposition_for_role(
    role: str,
    *,
    requires_confirmation: bool,
) -> DataDisposition:
    if role == "ignored":
        return DataDisposition.RETAIN_NOT_RENDER
    if requires_confirmation:
        return DataDisposition.UNCERTAIN
    if role in _PRIMARY_ROLES:
        return DataDisposition.RENDER_PRIMARY
    if role in _SECONDARY_ROLES:
        return DataDisposition.RENDER_SECONDARY
    if role in _SUPPORT_ROLES:
        return DataDisposition.SUPPORT_ONLY
    return DataDisposition.UNCERTAIN


def _scientific_disposition_for_role(
    role: str,
    *,
    requires_confirmation: bool,
    template_id: str,
    plot_kind: str,
) -> DataDisposition:
    if requires_confirmation or role == "ignored":
        return _disposition_for_role(
            role,
            requires_confirmation=requires_confirmation,
        )
    if template_id == "xrd" and plot_kind == "rietveld_refinement":
        disposition = _XRD_RIETVELD_DISPOSITIONS.get(role)
        if disposition is not None:
            return disposition
    if template_id == "xrd" and role == "support":
        return DataDisposition.SUPPORT_ONLY
    return _disposition_for_role(role, requires_confirmation=False)


def _unique_existing(
    columns: Iterable[str | None],
    item_ids: dict[str, str],
) -> tuple[str, ...]:
    result: list[str] = []
    for value in columns:
        if value is None or value not in item_ids:
            continue
        item_id = item_ids[value]
        if item_id not in result:
            result.append(item_id)
    return tuple(result)


def _ambiguities(prepared: Any, item_ids: dict[str, str]) -> tuple[SemanticAmbiguity, ...]:
    if not bool(getattr(prepared, "requires_confirmation", False)):
        return ()
    reasons = tuple(str(item) for item in getattr(prepared, "confirmation_reasons", ()))
    return (
        SemanticAmbiguity(
            ambiguity_id="column_role_confirmation",
            code="column_roles_need_confirmation",
            question_zh=(
                "请确认每列的科研含义和绘图角色；如有不符，请先修正列映射，再重新生成元素清单。"
            ),
            item_ids=tuple(item_ids.values()),
            options=("confirm_current_roles", "provide_corrected_mapping"),
            blocking=True,
        ),
        *(
            (
                SemanticAmbiguity(
                    ambiguity_id=f"mapping_reason_{index:02d}",
                    code=reason,
                    question_zh=f"自动识别提示：{reason}。请确认对应列角色。",
                    item_ids=tuple(item_ids.values()),
                    options=("confirm_current_roles", "provide_corrected_mapping"),
                    blocking=False,
                ),
            )
            for index, reason in enumerate(reasons)
        ),
    )


def _flatten_ambiguities(
    values: Iterable[SemanticAmbiguity | tuple[SemanticAmbiguity, ...]],
) -> tuple[SemanticAmbiguity, ...]:
    result: list[SemanticAmbiguity] = []
    for value in values:
        if isinstance(value, tuple):
            result.extend(value)
        else:
            result.append(value)
    return tuple(result)


def _scientific_proposal(prepared: Any) -> SemanticProposal:
    payload = prepared.payload
    assignments = dict(payload.assignments)
    requires_confirmation = bool(prepared.requires_confirmation)
    spec = payload.plot_spec
    template_id = str(prepared.template_id)
    plot_kind = str(getattr(spec, "plot_kind", ""))
    is_xrd_rietveld = template_id == "xrd" and plot_kind == "rietveld_refinement"
    item_ids = {
        column: _source_item_id(index) for index, column in enumerate(prepared.source_columns)
    }
    data_items = tuple(
        SemanticDataItem(
            item_id=item_ids[column],
            source_column=column,
            semantic_role=assignments.get(column, "unassigned"),
            disposition=_scientific_disposition_for_role(
                assignments.get(column, "unassigned"),
                requires_confirmation=requires_confirmation,
                template_id=template_id,
                plot_kind=plot_kind,
            ),
            confidence=float(prepared.confidence),
            evidence_codes=(
                "user_confirmed_column_mapping"
                if bool(getattr(payload, "mapping_confirmed", False))
                else "template_role_inference",
            ),
            alternatives=(
                ("provide_corrected_mapping",)
                if requires_confirmation and assignments.get(column) != "ignored"
                else ()
            ),
        )
        for column in prepared.source_columns
    )

    anchor_columns = (
        getattr(spec, "x_column", None),
        getattr(spec, "category_column", None),
        getattr(spec, "source_column", None),
        getattr(spec, "target_column", None),
        getattr(spec, "y_column", None),
    )
    anchor_ids = _unique_existing(anchor_columns, item_ids)
    derived_items: list[DerivedDataItem] = []
    elements: list[FigureElement] = []
    percent_mode = getattr(spec, "plot_kind", "") == "percent_stacked_bar"
    percent_inputs = _unique_existing(
        (getattr(series, "source_column", None) for series in spec.series),
        item_ids,
    )
    phase_tick_columns = tuple(
        str(column)
        for column in getattr(spec, "phase_tick_columns", ())
    )

    for index, series in enumerate(spec.series):
        source_column = str(series.source_column)
        if source_column not in item_ids:
            continue
        series_role = str(getattr(series, "series_role", "data"))
        if is_xrd_rietveld and (
            series_role == "phase_tick" or source_column in phase_tick_columns
        ):
            continue
        y_binding = item_ids[source_column]
        if percent_mode:
            derived_id = f"derived_fraction_{index:03d}"
            derived_items.append(
                DerivedDataItem(
                    item_id=derived_id,
                    semantic_role=f"row_fraction_for_{source_column}",
                    disposition=DataDisposition.RENDER_PRIMARY,
                    operation_id="fraction_of_row_total",
                    input_item_ids=percent_inputs,
                    confidence=1.0,
                    parameters=(("numerator_item_id", y_binding),),
                    evidence_codes=("template_percent_display_contract",),
                )
            )
            y_binding = derived_id
        auxiliary = _unique_existing(
            (
                getattr(series, "error_column", None),
                getattr(series, "size_column", None),
                getattr(series, "lower_column", None),
                getattr(series, "upper_column", None),
                getattr(series, "color_column", None),
            ),
            item_ids,
        )
        elements.append(
            FigureElement(
                element_id=f"series_{index:03d}",
                element_kind=_element_kind(
                    str(spec.plot_kind),
                    series_role,
                ),
                data_item_ids=(*anchor_ids, y_binding, *auxiliary),
                required=True,
                axis=str(getattr(series, "axis", "left")),
                legend_label=str(getattr(series, "label", source_column)),
            )
        )

    if is_xrd_rietveld:
        for index, column in enumerate(phase_tick_columns):
            if column not in item_ids:
                continue
            elements.append(
                FigureElement(
                    element_id=f"xrd_phase_tick_{index:03d}",
                    element_kind="phase_tick",
                    data_item_ids=(item_ids[column],),
                    required=False,
                    visible_by_default=True,
                    axis="phase_ticks",
                    legend_label=column,
                )
            )

    proposal = SemanticProposal(
        source_sha256=str(payload.source_sha256),
        source_columns=tuple(prepared.source_columns),
        domain_family=template_id,
        domain_mode=str(getattr(spec, "plot_mode", getattr(spec, "plot_kind", "default"))),
        domain_confidence=float(prepared.confidence),
        source_adapter_hint=f"editaplot_{prepared.template_id}",
        data_items=data_items,
        derived_items=tuple(derived_items),
        figure_elements=tuple(elements),
        ambiguities=_flatten_ambiguities(_ambiguities(prepared, item_ids)),
    )
    proposal.validate()
    return proposal


def _xps_proposal(prepared: Any) -> SemanticProposal:
    payload = prepared.payload
    roles = payload.roles
    requires_confirmation = bool(prepared.requires_confirmation)
    item_ids = {
        column: _source_item_id(index) for index, column in enumerate(prepared.source_columns)
    }
    role_by_column: dict[str, str] = {column: "component" for column in roles.components}
    role_by_column[roles.x] = "x"
    for role, column in (
        ("raw", roles.raw),
        ("background", roles.background),
        ("envelope", roles.envelope),
        ("residual", roles.residual),
    ):
        if column is not None:
            role_by_column[column] = role
    for column in roles.ignored:
        role_by_column[column] = "ignored"

    data_items: list[SemanticDataItem] = []
    for column in prepared.source_columns:
        role = role_by_column.get(column, "unassigned")
        if role == "residual" and not requires_confirmation:
            disposition = DataDisposition.RETAIN_NOT_RENDER
        else:
            disposition = _disposition_for_role(
                role,
                requires_confirmation=requires_confirmation,
            )
        data_items.append(
            SemanticDataItem(
                item_id=item_ids[column],
                source_column=column,
                semantic_role=role,
                disposition=disposition,
                confidence=float(prepared.confidence),
                evidence_codes=(
                    "user_confirmed_column_mapping"
                    if bool(payload.mapping_confirmed)
                    else "xps_role_inference",
                ),
                alternatives=(
                    ("provide_corrected_mapping",)
                    if requires_confirmation and role != "ignored"
                    else ()
                ),
            )
        )

    x_binding = item_ids[roles.x]
    derived_items: tuple[DerivedDataItem, ...] = ()
    if payload.plot_spec.axis.transform == "negate":
        derived_x = DerivedDataItem(
            item_id="derived_plot_x",
            semantic_role="display_x_with_descending_binding_energy_labels",
            disposition=DataDisposition.RENDER_PRIMARY,
            operation_id="negate",
            input_item_ids=(x_binding,),
            confidence=1.0,
            evidence_codes=("xps_verified_axis_contract",),
        )
        derived_items = (derived_x,)
        x_binding = derived_x.item_id

    elements: list[FigureElement] = []
    for index, series in enumerate(payload.plot_spec.series):
        if series.role == "residual" or series.column not in item_ids:
            continue
        elements.append(
            FigureElement(
                element_id=f"xps_{series.role}_{index:02d}",
                element_kind="area" if series.role == "component" else "line",
                data_item_ids=(x_binding, item_ids[series.column]),
                required=series.role == "raw",
                axis="counts",
                legend_label=series.label,
            )
        )

    proposal = SemanticProposal(
        source_sha256=str(payload.source_sha256),
        source_columns=tuple(prepared.source_columns),
        domain_family="xps",
        domain_mode=str(payload.detection.mode),
        domain_confidence=float(prepared.confidence),
        source_adapter_hint="editaplot_xps",
        data_items=tuple(data_items),
        derived_items=derived_items,
        figure_elements=tuple(elements),
        ambiguities=_flatten_ambiguities(_ambiguities(prepared, item_ids)),
    )
    proposal.validate()
    return proposal


def propose_prepared_semantics(prepared: Any) -> SemanticProposal:
    """Return a stable semantic proposal for a prepared public template."""

    payload = getattr(prepared, "payload", None)
    if payload is None:
        raise TypeError("prepared template payload is required")
    if hasattr(payload, "roles") and hasattr(payload, "detection"):
        return _xps_proposal(prepared)
    if hasattr(payload, "assignments") and hasattr(payload, "plot_spec"):
        return _scientific_proposal(prepared)
    raise TypeError("unsupported prepared template payload")


__all__ = ["propose_prepared_semantics"]
