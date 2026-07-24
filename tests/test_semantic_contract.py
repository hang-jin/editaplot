from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.semantic_contract import (  # noqa: E402
    ALLOWED_DERIVED_OPERATIONS,
    ConfirmedSemanticContract,
    DataDisposition,
    DerivedDataItem,
    FigureElement,
    SemanticAmbiguity,
    SemanticContractError,
    SemanticDataItem,
    SemanticProposal,
)

SOURCE_HASH = "a" * 64


def _source_item(
    item_id: str,
    column: str,
    role: str,
    disposition: DataDisposition = DataDisposition.RENDER_PRIMARY,
) -> SemanticDataItem:
    return SemanticDataItem(
        item_id=item_id,
        source_column=column,
        semantic_role=role,
        disposition=disposition,
        confidence=0.98,
        evidence_codes=("exact_header_alias",),
    )


def _base_proposal() -> SemanticProposal:
    return SemanticProposal(
        source_sha256=SOURCE_HASH,
        source_columns=("X", "Obs", "Calc", "Used"),
        domain_family="xrd",
        domain_mode="rietveld_refinement",
        domain_confidence=0.97,
        source_adapter_hint="gsas_ii_publication_csv",
        data_items=(
            _source_item("src:x", "X", "x_coordinate"),
            _source_item("src:obs", "Obs", "observed_intensity"),
            _source_item("src:calc", "Calc", "calculated_intensity"),
            _source_item(
                "src:used",
                "Used",
                "fit_mask",
                DataDisposition.SUPPORT_ONLY,
            ),
        ),
        figure_elements=(
            FigureElement("x_axis", "axis", ("src:x",), required=True, axis="x"),
            FigureElement(
                "observed_points",
                "markers",
                ("src:obs",),
                required=True,
                axis="main_y",
                legend_label="Observed",
            ),
            FigureElement(
                "calculated_curve",
                "line",
                ("src:calc",),
                required=True,
                axis="main_y",
                legend_label="Calculated",
            ),
        ),
    )


def _assert_error(code: str, function) -> SemanticContractError:
    with pytest.raises(SemanticContractError) as caught:
        function()
    assert caught.value.code == code
    return caught.value


def test_basic_proposal_is_json_serializable_and_hash_stable() -> None:
    first = _base_proposal()
    second = _base_proposal()

    first.validate()
    assert first.proposal_hash == second.proposal_hash
    assert first.stable_hash() == first.proposal_hash
    assert json.loads(json.dumps(first.to_dict(), ensure_ascii=False))["proposal_hash"] == (
        first.proposal_hash
    )

    payload = first.to_dict()
    assert "source_path" not in payload
    assert "timestamp" not in payload
    assert "confirmed_at" not in payload
    assert "E:" + chr(92) not in json.dumps(payload, ensure_ascii=False)


def test_every_source_column_must_be_classified_exactly_once() -> None:
    missing = replace(
        _base_proposal(),
        data_items=_base_proposal().data_items[:-1],
    )
    error = _assert_error("semantic_source_classification_incomplete", missing.validate)
    assert error.details["missing_columns"] == ["Used"]

    duplicate_items = (*_base_proposal().data_items, _source_item("src:obs2", "Obs", "duplicate"))
    duplicate = replace(_base_proposal(), data_items=duplicate_items)
    error = _assert_error("semantic_source_classification_incomplete", duplicate.validate)
    assert error.details["duplicate_columns"] == ["Obs"]


def test_uncertain_source_item_blocks_confirmation() -> None:
    proposal = _base_proposal()
    uncertain_obs = replace(
        proposal.data_items[1],
        disposition=DataDisposition.UNCERTAIN,
    )
    proposal = replace(
        proposal,
        data_items=(proposal.data_items[0], uncertain_obs, *proposal.data_items[2:]),
    )

    proposal.validate()
    error = _assert_error(
        "semantic_uncertain_items",
        lambda: proposal.confirm(user_confirmed=True),
    )
    assert error.details["item_ids"] == ["src:obs"]


def test_confirmation_must_be_explicit() -> None:
    proposal = _base_proposal()
    _assert_error(
        "semantic_user_confirmation_required",
        lambda: proposal.confirm(user_confirmed=False),
    )


def test_derived_operation_is_restricted_to_the_public_allowlist() -> None:
    assert "difference" in ALLOWED_DERIVED_OPERATIONS
    derived = DerivedDataItem(
        item_id="derived:diff",
        semantic_role="difference_curve",
        disposition=DataDisposition.RENDER_SECONDARY,
        operation_id="execute_arbitrary_python",
        input_item_ids=("src:obs", "src:calc"),
        confidence=0.91,
    )
    proposal = replace(_base_proposal(), derived_items=(derived,))

    _assert_error("semantic_derived_operation_not_allowed", proposal.validate)


def test_derived_lineage_must_reference_known_items_and_be_acyclic() -> None:
    unknown = DerivedDataItem(
        item_id="derived:diff",
        semantic_role="difference_curve",
        disposition=DataDisposition.RENDER_SECONDARY,
        operation_id="difference",
        input_item_ids=("src:obs", "src:missing"),
        confidence=0.91,
    )
    _assert_error(
        "semantic_derived_lineage_unknown",
        replace(_base_proposal(), derived_items=(unknown,)).validate,
    )

    first = replace(unknown, item_id="derived:first", input_item_ids=("derived:second",))
    second = replace(unknown, item_id="derived:second", input_item_ids=("derived:first",))
    _assert_error(
        "semantic_derived_cycle",
        replace(_base_proposal(), derived_items=(first, second)).validate,
    )


def _proposal_with_derived_difference() -> SemanticProposal:
    base = _base_proposal()
    derived = DerivedDataItem(
        item_id="derived:diff",
        semantic_role="difference_curve",
        disposition=DataDisposition.RENDER_SECONDARY,
        operation_id="difference",
        input_item_ids=("src:obs", "src:calc"),
        confidence=0.96,
        evidence_codes=("user_requested_difference",),
    )
    difference_element = FigureElement(
        "difference_curve",
        "line",
        ("derived:diff",),
        required=True,
        axis="residual_y",
        legend_label="Obs − Calc",
    )
    return replace(
        base,
        derived_items=(derived,),
        figure_elements=(*base.figure_elements, difference_element),
    )


def test_every_derived_item_needs_explicit_approval() -> None:
    proposal = _proposal_with_derived_difference()
    proposal.validate()

    _assert_error(
        "semantic_derived_approval_required",
        lambda: proposal.confirm(user_confirmed=True),
    )
    contract = proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=("derived:diff",),
    )
    assert isinstance(contract, ConfirmedSemanticContract)
    contract.validate()
    assert contract.to_dict()["confirmation"]["approved_derived_item_ids"] == ["derived:diff"]


def test_unknown_derived_approval_is_rejected() -> None:
    proposal = _proposal_with_derived_difference()
    _assert_error(
        "semantic_derived_approval_unknown",
        lambda: proposal.confirm(
            user_confirmed=True,
            approved_derived_item_ids=("derived:diff", "derived:not_declared"),
        ),
    )


def test_required_figure_element_must_have_a_binding() -> None:
    proposal = replace(
        _base_proposal(),
        figure_elements=(FigureElement("main_curve", "line", (), required=True),),
    )
    _assert_error("semantic_required_element_unbound", proposal.validate)


def test_required_figure_element_cannot_render_support_only_data() -> None:
    base = _base_proposal()
    proposal = replace(
        base,
        figure_elements=(
            *base.figure_elements,
            FigureElement("used_curve", "line", ("src:used",), required=True),
        ),
    )
    proposal.validate()
    _assert_error(
        "semantic_required_element_not_renderable",
        lambda: proposal.confirm(user_confirmed=True),
    )


def test_required_figure_element_cannot_reference_an_unknown_item() -> None:
    base = _base_proposal()
    proposal = replace(
        base,
        figure_elements=(
            *base.figure_elements,
            FigureElement("unknown", "line", ("src:not_declared",), required=True),
        ),
    )
    _assert_error("semantic_figure_binding_unknown", proposal.validate)


def test_blocking_ambiguities_need_valid_resolutions() -> None:
    ambiguity = SemanticAmbiguity(
        ambiguity_id="x_coordinate",
        code="multiple_x_coordinates",
        question_zh="横轴使用 2θ 还是 Q？",
        item_ids=("src:x",),
        options=("two_theta", "q"),
    )
    proposal = replace(_base_proposal(), ambiguities=(ambiguity,))
    proposal.validate()

    _assert_error(
        "semantic_ambiguity_resolution_required",
        lambda: proposal.confirm(user_confirmed=True),
    )
    _assert_error(
        "semantic_ambiguity_resolution_invalid",
        lambda: proposal.confirm(
            user_confirmed=True,
            resolved_ambiguities={"x_coordinate": "d_spacing"},
        ),
    )
    contract = proposal.confirm(
        user_confirmed=True,
        resolved_ambiguities={"x_coordinate": "two_theta"},
    )
    assert contract.to_dict()["confirmation"]["resolved_ambiguities"] == {"x_coordinate": "two_theta"}


def test_nonblocking_ambiguity_does_not_require_a_resolution() -> None:
    proposal = replace(
        _base_proposal(),
        ambiguities=(
            SemanticAmbiguity(
                ambiguity_id="background_visibility",
                code="optional_background",
                question_zh="是否显示背景线？",
                options=("show", "hide"),
                blocking=False,
            ),
        ),
    )
    contract = proposal.confirm(user_confirmed=True)
    contract.validate()


def test_contract_hash_is_stable_and_changes_with_a_scientific_decision() -> None:
    proposal = _base_proposal()
    first = proposal.confirm(user_confirmed=True)
    second = proposal.confirm(user_confirmed=True)
    assert first.contract_hash == second.contract_hash
    assert first.stable_hash() == first.contract_hash

    changed_items = list(proposal.data_items)
    changed_items[-1] = replace(
        changed_items[-1],
        disposition=DataDisposition.RETAIN_NOT_RENDER,
    )
    changed = replace(proposal, data_items=tuple(changed_items)).confirm(user_confirmed=True)
    assert changed.proposal.proposal_hash != proposal.proposal_hash
    assert changed.contract_hash != first.contract_hash


def test_hash_payload_rejects_absolute_runtime_paths() -> None:
    proposal = replace(
        _base_proposal(),
        source_adapter_hint=chr(92).join(("C:", "Users", "Researcher", "GSAS-II", "export.csv")),
    )
    _assert_error("semantic_unstable_path", proposal.validate)

    derived = replace(
        _proposal_with_derived_difference().derived_items[0],
        parameters=(("cache_path", chr(92).join(("C:", "Temp", "difference.csv"))),),
    )
    proposal = replace(_base_proposal(), derived_items=(derived,))
    _assert_error("semantic_unstable_path", proposal.validate)


def test_confirmed_contract_is_fully_json_serializable() -> None:
    proposal = _proposal_with_derived_difference()
    contract = proposal.confirm(
        user_confirmed=True,
        approved_derived_item_ids=("derived:diff",),
    )
    payload = contract.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    assert json.loads(encoded)["status"] == "confirmed"
    assert payload["proposal_hash"] == proposal.proposal_hash
    assert payload["contract_hash"] == contract.contract_hash
