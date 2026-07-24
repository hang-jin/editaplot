from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_workflow import prepare_scientific  # noqa: E402
from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402
from origin_sciplot.semantic_contract import SemanticContractError  # noqa: E402


def _scientific_prepared(*, confirm: bool = False, percent: bool = False):
    series = (
        SimpleNamespace(
            source_column="Control",
            label="Control",
            axis="left",
            series_role="data",
            error_column="Control SD",
            size_column=None,
            lower_column=None,
            upper_column=None,
            color_column=None,
        ),
        SimpleNamespace(
            source_column="Treatment",
            label="Treatment",
            axis="left",
            series_role="data",
            error_column=None,
            size_column=None,
            lower_column=None,
            upper_column=None,
            color_column=None,
        ),
    )
    payload = SimpleNamespace(
        source_sha256="a" * 64,
        assignments=(
            ("Group", "category"),
            ("Control", "series"),
            ("Control SD", "error"),
            ("Treatment", "series"),
            ("Notes", "ignored"),
        ),
        mapping_confirmed=confirm,
        plot_spec=SimpleNamespace(
            plot_kind="percent_stacked_bar" if percent else "bar_error",
            plot_mode="default",
            x_column=None,
            category_column="Group",
            source_column=None,
            target_column=None,
            y_column=None,
            series=series,
        ),
    )
    return SimpleNamespace(
        template_id="percent_stacked_bar" if percent else "bar",
        source_columns=("Group", "Control", "Control SD", "Treatment", "Notes"),
        confidence=1.0 if confirm else 0.67,
        requires_confirmation=not confirm,
        confirmation_reasons=("category_role_inferred",) if not confirm else (),
        payload=payload,
    )


def _wrapped_xrd(preparation):
    return SimpleNamespace(
        template_id="xrd",
        source_columns=preparation.source_columns,
        confidence=preparation.confidence,
        requires_confirmation=preparation.requires_confirmation,
        confirmation_reasons=preparation.confirmation_reasons,
        payload=preparation,
    )


def test_generic_semantics_classifies_every_column_and_lists_visible_elements() -> None:
    proposal = propose_prepared_semantics(_scientific_prepared(confirm=True))

    assert proposal.source_columns == ("Group", "Control", "Control SD", "Treatment", "Notes")
    assert {item.source_column for item in proposal.data_items} == set(proposal.source_columns)
    dispositions = {item.source_column: item.disposition.value for item in proposal.data_items}
    assert dispositions["Control"] == "render_primary"
    assert dispositions["Control SD"] == "render_secondary"
    assert dispositions["Notes"] == "retain_not_render"
    assert len(proposal.figure_elements) == 2
    proposal.confirm(user_confirmed=True)


def test_unconfirmed_mapping_remains_uncertain_and_cannot_be_frozen() -> None:
    proposal = propose_prepared_semantics(_scientific_prepared(confirm=False))

    assert any(item.disposition.value == "uncertain" for item in proposal.data_items)
    assert proposal.ambiguities[0].blocking is True
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(
            user_confirmed=True,
            resolved_ambiguities={"column_role_confirmation": "confirm_current_roles"},
        )
    assert caught.value.code == "semantic_uncertain_items"


def test_percent_display_helper_requires_explicit_approval() -> None:
    proposal = propose_prepared_semantics(_scientific_prepared(confirm=True, percent=True))

    assert len(proposal.derived_items) == 2
    assert {item.operation_id for item in proposal.derived_items} == {"fraction_of_row_total"}
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=True)
    assert caught.value.code == "semantic_derived_approval_required"
    proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=tuple(item.item_id for item in proposal.derived_items),
    )


def test_rietveld_preparation_preserves_curve_and_support_dispositions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "publication.csv"
    source.write_text(
        "\n".join(
            (
                'Used,"X (2theta, deg)",Obs,Calc,Bkg,Diff,Phase alpha,'
                "tick-pos,diff/sigma,Axis-limits",
                "1,20,101,99,12,-48,20.4,alpha,0.2,20",
                "1,21,115,113,13,-47,21.3,-65,0.3,80",
                "1,22,120,118,13,-46,,,0.1,-70",
                "1,23,119,118,13,-45,,,0.2,130",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    preparation = prepare_scientific(source, "xrd")

    proposal = propose_prepared_semantics(_wrapped_xrd(preparation))

    dispositions = {
        item.source_column: item.disposition.value
        for item in proposal.data_items
    }
    assert dispositions['X (2theta, deg)'] == "render_primary"
    assert dispositions["Obs"] == "render_primary"
    assert dispositions["Calc"] == "render_primary"
    assert dispositions["Bkg"] == "render_secondary"
    assert dispositions["Diff"] == "render_secondary"
    assert dispositions["Phase alpha"] == "render_secondary"
    for column in ("Used", "tick-pos", "diff/sigma", "Axis-limits"):
        assert dispositions[column] == "support_only"
    proposal.confirm(user_confirmed=True)


def test_rietveld_phase_ticks_are_independent_elements_not_profile_series(
    tmp_path: Path,
) -> None:
    source = tmp_path / "publication.csv"
    source.write_text(
        "\n".join(
            (
                'Used,"X (2theta, deg)",Obs,Calc,Bkg,Diff,Phase alpha,'
                "tick-pos,diff/sigma,Axis-limits",
                "1,20,101,99,12,-48,20.4,alpha,0.2,20",
                "1,21,115,113,13,-47,21.3,-65,0.3,80",
                "1,22,120,118,13,-46,,,0.1,-70",
                "1,23,119,118,13,-45,,,0.2,130",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    preparation = prepare_scientific(source, "xrd")

    proposal = propose_prepared_semantics(_wrapped_xrd(preparation))

    phase_elements = [
        element
        for element in proposal.figure_elements
        if element.element_kind == "phase_tick"
    ]
    assert len(phase_elements) == 1
    phase = phase_elements[0]
    assert phase.axis == "phase_ticks"
    assert phase.legend_label == "Phase alpha"
    assert phase.required is False
    item_by_id = {item.item_id: item for item in proposal.data_items}
    assert [item_by_id[item_id].source_column for item_id in phase.data_item_ids] == [
        "Phase alpha"
    ]
    assert all(
        element.legend_label != "Phase alpha"
        for element in proposal.figure_elements
        if element is not phase
    )
    assert len(proposal.figure_elements) == len(preparation.plot_spec.series) + 1


def test_ordinary_xrd_semantic_bridge_does_not_gain_rietveld_elements() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "runtime"
        / "templates"
        / "xrd"
        / "example_standard.csv"
    )
    preparation = prepare_scientific(source, "xrd")

    proposal = propose_prepared_semantics(_wrapped_xrd(preparation))

    roles = dict(preparation.assignments)
    dispositions = {
        item.source_column: item.disposition.value
        for item in proposal.data_items
    }
    for column, role in roles.items():
        if role in {"x", "series"}:
            assert dispositions[column] == "render_primary"
        elif role == "ignored":
            assert dispositions[column] == "retain_not_render"
    assert all(
        element.element_kind != "phase_tick"
        for element in proposal.figure_elements
    )
    assert len(proposal.figure_elements) == len(preparation.plot_spec.series)
    proposal.confirm(user_confirmed=True)


def test_xps_residual_is_retained_and_binding_energy_transform_is_explicit() -> None:
    roles = SimpleNamespace(
        x="Binding Energy",
        raw="Raw",
        background="Background",
        envelope="Envelope",
        residual="Residual",
        components=("C-C",),
        ignored=(),
    )
    plot_series = tuple(
        SimpleNamespace(column=column, label=column, role=role)
        for column, role in (
            ("Raw", "raw"),
            ("Background", "background"),
            ("Envelope", "envelope"),
            ("C-C", "component"),
            ("Residual", "residual"),
        )
    )
    payload = SimpleNamespace(
        source_sha256="b" * 64,
        roles=roles,
        detection=SimpleNamespace(mode="fit_with_residual"),
        mapping_confirmed=True,
        plot_spec=SimpleNamespace(
            axis=SimpleNamespace(transform="negate"),
            series=plot_series,
        ),
    )
    prepared = SimpleNamespace(
        template_id="xps",
        source_columns=("Binding Energy", "Raw", "Background", "Envelope", "C-C", "Residual"),
        confidence=1.0,
        requires_confirmation=False,
        confirmation_reasons=(),
        payload=payload,
    )

    proposal = propose_prepared_semantics(prepared)

    dispositions = {item.source_column: item.disposition.value for item in proposal.data_items}
    assert dispositions["Residual"] == "retain_not_render"
    assert proposal.derived_items[0].operation_id == "negate"
    assert all("Residual" != element.legend_label for element in proposal.figure_elements)
    contract = proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=("derived_plot_x",),
    )
    assert contract.proposal.source_sha256 == "b" * 64
