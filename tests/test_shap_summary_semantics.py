from __future__ import annotations

import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    prepare_scientific,
)
from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402
from origin_sciplot.semantic_contract import (  # noqa: E402
    DataDisposition,
    SemanticContractError,
    parse_semantic_proposal,
)
from origin_sciplot.shap_composite import (  # noqa: E402
    SHAP_COMPOSITE_LAYOUT_VERSION,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _legacy_rows() -> list[dict[str, object]]:
    return [
        {"Feature": "Texture", "SHAP value": -2.0, "Feature value": 0.1},
        {"Feature": "Texture", "SHAP value": 0.0, "Feature value": 0.5},
        {"Feature": "Texture", "SHAP value": 2.0, "Feature value": 0.9},
        {"Feature": "Shape", "SHAP value": -1.0, "Feature value": 0.2},
        {"Feature": "Shape", "SHAP value": 1.0, "Feature value": 0.6},
        {"Feature": "Shape", "SHAP value": 3.0, "Feature value": 1.0},
    ]


def _grouped_rows(
    *,
    include_mean_abs: bool,
    include_group_contribution: bool,
) -> list[dict[str, object]]:
    definitions = (
        ("Age", "Clinical", 4.0, (-6.0, 2.0, 4.0)),
        ("Texture", "Imaging", 2.0, (-3.0, 1.0, 2.0)),
        ("Shape", "Imaging", 1.0, (-1.0, 0.0, 2.0)),
    )
    rows: list[dict[str, object]] = []
    for order, (feature, group, mean_abs, shap_values) in enumerate(definitions, start=1):
        contribution = (4.0 if group == "Clinical" else 3.0) / 7.0 * 100.0
        for sample_index, shap_value in enumerate(shap_values, start=1):
            row: dict[str, object] = {
                "Feature": feature,
                "SHAP value": shap_value,
                "Feature value": sample_index / 3.0,
                "Sample ID": f"S{sample_index:02d}",
                "Feature Order": order,
                "Feature Group": group,
            }
            if include_mean_abs:
                row["Mean absolute SHAP"] = mean_abs
            if include_group_contribution:
                row["Group contribution (%)"] = contribution
            rows.append(row)
    return rows


def _wrapped(preparation):
    return SimpleNamespace(
        template_id="shap_summary",
        source_columns=preparation.source_columns,
        confidence=preparation.confidence,
        requires_confirmation=preparation.requires_confirmation,
        confirmation_reasons=preparation.confirmation_reasons,
        payload=preparation,
    )


def _items_by_column(proposal) -> dict[str, object]:
    return {item.source_column: item for item in proposal.data_items}


def _elements_using(proposal, item_id: str) -> tuple[object, ...]:
    return tuple(
        element for element in proposal.figure_elements if item_id in element.data_item_ids
    )


VISUAL_HELPER_IDS = (
    "derived_shap_feature_value_relative_color",
    "derived_shap_beeswarm_y_offset",
)


def test_legacy_input_declares_all_visual_derivations_with_complete_lineage(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "legacy.csv", _legacy_rows())
    preparation = prepare_scientific(source, "shap_summary")

    assert preparation.plot_spec.shap_plan.layout_version == (
        SHAP_COMPOSITE_LAYOUT_VERSION
    )

    proposal = propose_prepared_semantics(_wrapped(preparation))

    items = _items_by_column(proposal)
    derived = {item.item_id: item for item in proposal.derived_items}
    assert set(derived) == {
        *VISUAL_HELPER_IDS,
        "derived_mean_absolute_shap_by_feature",
    }

    mean_abs = derived["derived_mean_absolute_shap_by_feature"]
    assert mean_abs.semantic_role == "mean_absolute_shap_by_feature"
    assert mean_abs.operation_id == "mean_absolute_by_category"
    assert mean_abs.input_item_ids == (
        items["Feature"].item_id,
        items["SHAP value"].item_id,
    )
    assert mean_abs.disposition is DataDisposition.RENDER_SECONDARY
    assert "shap_composite_mean_abs_contract" in mean_abs.evidence_codes
    assert _elements_using(proposal, mean_abs.item_id)

    relative_color = derived["derived_shap_feature_value_relative_color"]
    assert relative_color.operation_id == "normalize_within_category_minmax"
    assert relative_color.input_item_ids == (
        items["Feature"].item_id,
        items["Feature value"].item_id,
    )
    color_parameters = dict(relative_color.parameters)
    assert color_parameters["constant_value"] == pytest.approx(0.5)
    assert color_parameters["minimum"] == pytest.approx(0.0)
    assert color_parameters["maximum"] == pytest.approx(1.0)
    assert relative_color.disposition is DataDisposition.RENDER_SECONDARY

    y_offset = derived["derived_shap_beeswarm_y_offset"]
    assert y_offset.operation_id == "deterministic_binned_symmetric_offset"
    assert y_offset.input_item_ids == (
        items["Feature"].item_id,
        items["SHAP value"].item_id,
    )
    assert dict(y_offset.parameters)["rule"] == "deterministic_binned_symmetric_v1"
    assert y_offset.disposition is DataDisposition.RENDER_SECONDARY

    elements = {element.element_id: element for element in proposal.figure_elements}
    assert relative_color.item_id in elements["shap_feature_value_colorbar"].data_item_ids
    assert relative_color.item_id in elements["shap_beeswarm"].data_item_ids
    assert y_offset.item_id in elements["shap_beeswarm"].data_item_ids


def test_every_shap_derivation_requires_explicit_user_approval(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "legacy.csv", _legacy_rows())
    proposal = propose_prepared_semantics(
        _wrapped(prepare_scientific(source, "shap_summary"))
    )

    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=True)
    assert caught.value.code == "semantic_derived_approval_required"
    derived_ids = tuple(item.item_id for item in proposal.derived_items)
    assert set(caught.value.details["item_ids"]) == set(derived_ids)

    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(
            user_confirmed=True,
            approved_derived_item_ids=("derived_mean_absolute_shap_by_feature",),
        )
    assert caught.value.code == "semantic_derived_approval_required"
    assert set(caught.value.details["item_ids"]) == set(VISUAL_HELPER_IDS)

    contract = proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=derived_ids,
    )
    contract.validate()
    assert contract.approved_derived_item_ids == derived_ids


def test_grouped_input_declares_both_mean_abs_and_group_fraction_lineage(
    tmp_path: Path,
) -> None:
    rows = _grouped_rows(
        include_mean_abs=False,
        include_group_contribution=False,
    )
    source = _write_csv(tmp_path / "grouped_derived.csv", rows)
    proposal = propose_prepared_semantics(
        _wrapped(prepare_scientific(source, "shap_summary"))
    )

    items = _items_by_column(proposal)
    derived = {item.item_id: item for item in proposal.derived_items}
    assert set(derived) == {
        *VISUAL_HELPER_IDS,
        "derived_mean_absolute_shap_by_feature",
        "derived_shap_group_contribution_fraction",
    }
    assert (
        derived["derived_mean_absolute_shap_by_feature"].operation_id
        == "mean_absolute_by_category"
    )
    contribution = derived["derived_shap_group_contribution_fraction"]
    assert contribution.operation_id == "fraction_of_group_total"
    assert contribution.input_item_ids == (
        items["Feature Group"].item_id,
        "derived_mean_absolute_shap_by_feature",
    )
    assert contribution.disposition is DataDisposition.RENDER_SECONDARY
    assert "shap_composite_group_fraction_contract" in contribution.evidence_codes
    assert _elements_using(proposal, contribution.item_id)

    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(
            user_confirmed=True,
            approved_derived_item_ids=(
                "derived_mean_absolute_shap_by_feature",
                "derived_shap_group_contribution_fraction",
            ),
        )
    assert caught.value.code == "semantic_derived_approval_required"
    assert set(caught.value.details["item_ids"]) == set(VISUAL_HELPER_IDS)

    proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=tuple(derived),
    ).validate()


def test_upstream_summary_columns_are_source_items_not_rederived(tmp_path: Path) -> None:
    rows = _grouped_rows(
        include_mean_abs=True,
        include_group_contribution=True,
    )
    source = _write_csv(tmp_path / "grouped_upstream.csv", rows)
    proposal = propose_prepared_semantics(
        _wrapped(prepare_scientific(source, "shap_summary"))
    )

    items = _items_by_column(proposal)
    derived = {item.item_id: item for item in proposal.derived_items}
    assert set(derived) == set(VISUAL_HELPER_IDS)
    assert {item.operation_id for item in derived.values()} == {
        "normalize_within_category_minmax",
        "deterministic_binned_symmetric_offset",
    }
    assert items["Mean absolute SHAP"].semantic_role == "mean_abs_shap"
    assert items["Mean absolute SHAP"].disposition is DataDisposition.RENDER_SECONDARY
    assert items["Group contribution (%)"].semantic_role == "group_contribution"
    assert items["Group contribution (%)"].disposition is DataDisposition.RENDER_SECONDARY
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=True)
    assert caught.value.code == "semantic_derived_approval_required"
    assert set(caught.value.details["item_ids"]) == set(VISUAL_HELPER_IDS)
    proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=VISUAL_HELPER_IDS,
    ).validate()


def test_support_columns_are_retained_but_not_bound_as_visible_measurements(
    tmp_path: Path,
) -> None:
    rows = _grouped_rows(
        include_mean_abs=True,
        include_group_contribution=True,
    )
    source = _write_csv(tmp_path / "support_columns.csv", rows)
    proposal = propose_prepared_semantics(
        _wrapped(prepare_scientific(source, "shap_summary"))
    )

    items = _items_by_column(proposal)
    assert items["Feature"].disposition is DataDisposition.RENDER_PRIMARY
    assert items["SHAP value"].disposition is DataDisposition.RENDER_PRIMARY
    assert items["Feature value"].disposition is DataDisposition.RENDER_SECONDARY
    assert items["Sample ID"].disposition is DataDisposition.SUPPORT_ONLY
    assert items["Feature Order"].disposition is DataDisposition.SUPPORT_ONLY
    assert items["Feature Group"].disposition is DataDisposition.RENDER_SECONDARY

    bound = {
        item_id
        for element in proposal.figure_elements
        for item_id in element.data_item_ids
    }
    assert items["Sample ID"].item_id not in bound
    assert items["Feature Order"].item_id not in bound


def test_proposal_hash_changes_with_profile_and_summary_lineage(tmp_path: Path) -> None:
    rows = _grouped_rows(
        include_mean_abs=True,
        include_group_contribution=True,
    )
    source = _write_csv(tmp_path / "same_source.csv", rows)
    columns = list(rows[0])
    all_roles = {
        "Feature": "feature",
        "SHAP value": "shap",
        "Feature value": "feature_value",
        "Sample ID": "sample_id",
        "Feature Order": "feature_order",
        "Feature Group": "feature_group",
        "Mean absolute SHAP": "mean_abs_shap",
        "Group contribution (%)": "group_contribution",
    }

    def proposal_for(*, profile: str, ignore_summaries: bool = False):
        roles = dict(all_roles)
        if ignore_summaries:
            roles["Mean absolute SHAP"] = "ignored"
            roles["Group contribution (%)"] = "ignored"
        mapping = ScientificColumnMapping(
            assignments=tuple((column, roles[column]) for column in columns),
            plot_mode=profile,
        )
        preparation = prepare_scientific(
            source,
            "shap_summary",
            column_mapping=mapping,
        )
        return propose_prepared_semantics(_wrapped(preparation))

    beeswarm = proposal_for(profile="beeswarm_only")
    provided = proposal_for(profile="beeswarm_mean_abs_grouped")
    derived = proposal_for(
        profile="beeswarm_mean_abs_grouped",
        ignore_summaries=True,
    )

    assert len({beeswarm.proposal_hash, provided.proposal_hash, derived.proposal_hash}) == 3
    assert beeswarm.source_sha256 == provided.source_sha256 == derived.source_sha256

    stale_payload = derived.to_dict()
    stale_payload["proposal_hash"] = provided.proposal_hash
    with pytest.raises(SemanticContractError) as caught:
        parse_semantic_proposal(stale_payload)
    assert caught.value.code == "semantic_proposal_hash_mismatch"
