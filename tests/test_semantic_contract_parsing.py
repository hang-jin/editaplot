from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.semantic_contract import (  # noqa: E402
    DataDisposition,
    DerivedDataItem,
    FigureElement,
    SemanticAmbiguity,
    SemanticContractError,
    SemanticDataItem,
    SemanticProposal,
    parse_confirmed_semantic_contract,
    parse_semantic_proposal,
)

SOURCE_HASH = "a" * 64


def _proposal() -> SemanticProposal:
    return SemanticProposal(
        source_sha256=SOURCE_HASH,
        source_columns=("TwoTheta", "Observed", "Calculated"),
        domain_family="xrd",
        domain_mode="rietveld_refinement",
        domain_confidence=0.97,
        source_adapter_hint="gsas_ii_publication_csv",
        data_items=(
            SemanticDataItem(
                item_id="src:x",
                source_column="TwoTheta",
                semantic_role="two_theta",
                disposition=DataDisposition.RENDER_PRIMARY,
                confidence=0.99,
                evidence_codes=("header_alias",),
            ),
            SemanticDataItem(
                item_id="src:obs",
                source_column="Observed",
                semantic_role="observed_intensity",
                disposition=DataDisposition.RENDER_PRIMARY,
                confidence=0.98,
                evidence_codes=("header_alias",),
                alternatives=("raw_intensity",),
            ),
            SemanticDataItem(
                item_id="src:calc",
                source_column="Calculated",
                semantic_role="calculated_intensity",
                disposition=DataDisposition.RENDER_PRIMARY,
                confidence=0.98,
                evidence_codes=("header_alias",),
            ),
        ),
        derived_items=(
            DerivedDataItem(
                item_id="derived:diff",
                semantic_role="difference_curve",
                disposition=DataDisposition.RENDER_SECONDARY,
                operation_id="difference",
                input_item_ids=("src:obs", "src:calc"),
                confidence=0.95,
                parameters=(("offset", 0.0),),
                evidence_codes=("user_requested",),
            ),
        ),
        figure_elements=(
            FigureElement(
                element_id="observed_points",
                element_kind="markers",
                data_item_ids=("src:x", "src:obs"),
                required=True,
                axis="main_y",
                legend_label="Observed",
            ),
            FigureElement(
                element_id="difference_curve",
                element_kind="line",
                data_item_ids=("src:x", "derived:diff"),
                required=True,
                axis="residual_y",
                legend_label="Difference",
            ),
        ),
        ambiguities=(
            SemanticAmbiguity(
                ambiguity_id="x_axis",
                code="confirm_x_axis",
                question_zh="确认横轴使用 2θ？",
                item_ids=("src:x",),
                options=("two_theta", "q"),
                blocking=True,
            ),
        ),
    )


def _contract():
    return _proposal().confirm(
        user_confirmed=True,
        approved_derived_item_ids=("derived:diff",),
        resolved_ambiguities={"x_axis": "two_theta"},
    )


def _json_clone(value: dict[str, object]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _assert_code(code: str, function) -> SemanticContractError:
    with pytest.raises(SemanticContractError) as caught:
        function()
    assert caught.value.code == code
    return caught.value


def test_proposal_round_trip_rebuilds_public_json_and_hash() -> None:
    original = _proposal()
    payload = _json_clone(original.to_dict())

    rebuilt = parse_semantic_proposal(payload)

    assert rebuilt == original
    assert rebuilt.proposal_hash == original.proposal_hash
    assert rebuilt.to_dict() == original.to_dict()


def test_confirmed_contract_round_trip_reuses_every_confirmation_gate() -> None:
    original = _contract()
    payload = _json_clone(original.to_dict())

    rebuilt = parse_confirmed_semantic_contract(payload)

    assert rebuilt == original
    assert rebuilt.contract_hash == original.contract_hash
    assert rebuilt.to_dict() == original.to_dict()


def test_hash_fields_are_optional_but_verified_when_present() -> None:
    proposal_payload = _json_clone(_proposal().to_dict())
    proposal_payload.pop("proposal_hash")
    assert parse_semantic_proposal(proposal_payload).proposal_hash == (
        _proposal().proposal_hash
    )

    contract_payload = _json_clone(_contract().to_dict())
    contract_payload.pop("proposal_hash")
    contract_payload.pop("contract_hash")
    assert parse_confirmed_semantic_contract(contract_payload).contract_hash == (
        _contract().contract_hash
    )


@pytest.mark.parametrize(
    "target",
    [
        "top",
        "domain",
        "source_item",
        "derived_item",
        "figure_element",
        "ambiguity",
        "confirmation",
    ],
)
def test_unknown_top_level_and_nested_fields_are_rejected(target: str) -> None:
    payload = _json_clone(_contract().to_dict())
    if target == "top":
        payload["unexpected"] = True
    elif target == "domain":
        payload["domain"]["unexpected"] = True
    elif target == "source_item":
        payload["data_items"][0]["unexpected"] = True
    elif target == "derived_item":
        payload["derived_items"][0]["unexpected"] = True
    elif target == "figure_element":
        payload["figure_elements"][0]["unexpected"] = True
    elif target == "ambiguity":
        payload["ambiguities"][0]["unexpected"] = True
    else:
        payload["confirmation"]["unexpected"] = True

    _assert_code(
        "semantic_payload_unknown_fields",
        lambda: parse_confirmed_semantic_contract(payload),
    )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("source_columns", ("TwoTheta", "Observed", "Calculated")),
        ("domain_confidence", True),
        ("source_confidence", "0.99"),
        ("figure_required", 1),
        ("parameters", []),
        ("resolved_ambiguities", []),
    ],
)
def test_json_type_errors_are_not_silently_normalized(
    field: str,
    bad_value: object,
) -> None:
    payload = _json_clone(_contract().to_dict())
    if field == "source_columns":
        payload["source_columns"] = bad_value
    elif field == "domain_confidence":
        payload["domain"]["confidence"] = bad_value
    elif field == "source_confidence":
        payload["data_items"][0]["confidence"] = bad_value
    elif field == "figure_required":
        payload["figure_elements"][0]["required"] = bad_value
    elif field == "parameters":
        payload["derived_items"][0]["parameters"] = bad_value
    else:
        payload["confirmation"]["resolved_ambiguities"] = bad_value

    _assert_code(
        "semantic_payload_schema_invalid",
        lambda: parse_confirmed_semantic_contract(payload),
    )


def test_proposal_and_contract_hash_mismatches_are_rejected() -> None:
    proposal_payload = _json_clone(_proposal().to_dict())
    proposal_payload["proposal_hash"] = "0" * 64
    _assert_code(
        "semantic_proposal_hash_mismatch",
        lambda: parse_semantic_proposal(proposal_payload),
    )

    contract_payload = _json_clone(_contract().to_dict())
    contract_payload["contract_hash"] = "0" * 64
    _assert_code(
        "semantic_contract_hash_mismatch",
        lambda: parse_confirmed_semantic_contract(contract_payload),
    )


@pytest.mark.parametrize("status", ["draft", "pending", "unconfirmed"])
def test_unconfirmed_status_cannot_be_loaded_as_a_contract(status: str) -> None:
    payload = _json_clone(_contract().to_dict())
    payload["status"] = status

    _assert_code(
        "semantic_contract_not_confirmed",
        lambda: parse_confirmed_semantic_contract(payload),
    )


@pytest.mark.parametrize(
    ("target", "absolute_path"),
    [
        ("legend", chr(92).join(("C:", "Users", "Researcher", "reference.png"))),
        ("question", "/private/research/question.txt"),
        ("resolution", chr(92) * 2 + chr(92).join(("server", "private", "decision.txt"))),
        ("resolution_key", chr(92).join(("C:", "private", "ambiguity"))),
    ],
)
def test_absolute_paths_are_rejected_anywhere_in_public_payload(
    target: str,
    absolute_path: str,
) -> None:
    payload = _json_clone(_contract().to_dict())
    if target == "legend":
        payload["figure_elements"][0]["legend_label"] = absolute_path
    elif target == "question":
        payload["ambiguities"][0]["question_zh"] = absolute_path
    elif target == "resolution":
        payload["confirmation"]["resolved_ambiguities"]["x_axis"] = absolute_path
    else:
        payload["confirmation"]["resolved_ambiguities"][absolute_path] = "two_theta"
    payload.pop("proposal_hash", None)
    payload.pop("contract_hash", None)

    _assert_code(
        "semantic_unstable_path",
        lambda: parse_confirmed_semantic_contract(payload),
    )


def test_parser_does_not_bypass_derived_approval_or_uncertainty_gates() -> None:
    missing_approval = _json_clone(_contract().to_dict())
    missing_approval["confirmation"]["approved_derived_item_ids"] = []
    missing_approval.pop("contract_hash")
    _assert_code(
        "semantic_derived_approval_required",
        lambda: parse_confirmed_semantic_contract(missing_approval),
    )

    uncertain = copy.deepcopy(missing_approval)
    uncertain["data_items"][1]["disposition"] = "uncertain"
    uncertain.pop("proposal_hash")
    _assert_code(
        "semantic_uncertain_items",
        lambda: parse_confirmed_semantic_contract(uncertain),
    )


def test_non_object_payload_is_rejected_with_a_stable_error() -> None:
    _assert_code(
        "semantic_payload_schema_invalid",
        lambda: parse_semantic_proposal([]),  # type: ignore[arg-type]
    )
