from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.semantic_analysis import propose_prepared_semantics  # noqa: E402
from origin_sciplot.semantic_contract import (  # noqa: E402
    DataDisposition,
    SemanticContractError,
    SemanticDataItem,
    SemanticProposal,
    parse_confirmed_semantic_contract,
    parse_semantic_proposal,
)

EVENT_CONTEXT = {"interval_label": "95% confidence interval", "time_unit": "s", "response_unit": "mV"}
LEGACY_HASH = "6ca63ccd47e6c8916affec522c13f2bd41e39cd1ee50d3ea87b51c578c60efa8"
LEGACY_CONTRACT_HASH = "318aaa2d7ae1250ef3a3b54d356149f53aca8b3ed9b4cb3eaf08cd43d920f2f8"
LEGACY_JSON = (
    '{"ambiguities":[],"data_items":[{"alternatives":[],"confidence":1.0,'
    '"disposition":"render_primary","evidence_codes":[],"item_id":"src:Time",'
    '"item_type":"source_column","semantic_role":"x","source_column":"Time"},'
    '{"alternatives":[],"confidence":1.0,"disposition":"render_primary",'
    '"evidence_codes":[],"item_id":"src:Response","item_type":"source_column",'
    '"semantic_role":"series","source_column":"Response"}],"derived_items":[],"domain":'
    '{"confidence":1.0,"family":"event_response","mode":"default","source_adapter_hint":null},'
    '"figure_elements":[],"proposal_hash":"6ca63ccd47e6c8916affec522c13f2bd41e39cd1ee50d3ea87b51c578c60efa8",'
    '"proposal_version":"1.0","source_columns":["Time","Response"],'
    '"source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
)


def _proposal(**kwargs: object) -> SemanticProposal:
    return SemanticProposal(
        source_sha256="a" * 64,
        source_columns=("Time", "Response"),
        domain_family="event_response",
        domain_mode="default",
        domain_confidence=1.0,
        data_items=tuple(
            SemanticDataItem(
                item_id=f"src:{column}", source_column=column, semantic_role=role,
                disposition=DataDisposition.RENDER_PRIMARY, confidence=1.0,
            )
            for column, role in (("Time", "x"), ("Response", "series"))
        ),
        **kwargs,
    )


def test_absent_context_preserves_literal_legacy_payload_and_hashes() -> None:
    proposal = _proposal()
    assert proposal.scientific_context == ()
    assert json.dumps(proposal.to_dict(), sort_keys=True, separators=(",", ":")) == LEGACY_JSON
    assert proposal.proposal_hash == LEGACY_HASH
    assert proposal.confirm(user_confirmed=True).contract_hash == LEGACY_CONTRACT_HASH
    assert parse_semantic_proposal(json.loads(LEGACY_JSON)) == proposal
    assert replace(proposal, scientific_context={}).to_dict() == proposal.to_dict()


@pytest.mark.parametrize(
    ("family", "context"),
    [
        ("event_response", EVENT_CONTEXT),
        ("spatial_profile", {"profile_x": 1.25, "profile_y": 2, "x_unit": "mm",
                             "y_unit": "mm", "value_unit": "a.u."}),
        ("ratiometric_response", {"ratio_definition": "I530/I480", "x_unit": "s",
                                  "numerator_unit": "a.u.", "denominator_unit": "a.u.",
                                  "ratio_unit": "dimensionless"}),
    ],
)
def test_context_round_trips_without_inventing_source_columns(
    family: str, context: dict[str, object],
) -> None:
    legacy = replace(_proposal(), domain_family=family)
    proposal = replace(legacy, scientific_context=context)
    proposal.validate()
    assert proposal.scientific_context == tuple(sorted(context.items()))
    assert proposal.to_dict()["scientific_context"] == context
    assert proposal.data_items == legacy.data_items
    assert proposal.source_columns == ("Time", "Response")
    assert proposal.derived_items == ()
    assert len(proposal.data_items) == 2
    assert parse_semantic_proposal(json.loads(json.dumps(proposal.to_dict()))) == proposal
    contract = proposal.confirm(user_confirmed=True)
    assert contract.to_dict()["scientific_context"] == context
    assert parse_confirmed_semantic_contract(json.loads(json.dumps(contract.to_dict()))) == contract


def test_context_is_frozen_and_reordered_input_has_the_same_hash() -> None:
    context = dict(EVENT_CONTEXT)
    proposal = _proposal(scientific_context=context)
    context["time_unit"] = "ms"
    assert dict(proposal.scientific_context)["time_unit"] == "s"
    reordered = _proposal(scientific_context=tuple(reversed(tuple(EVENT_CONTEXT.items()))))
    assert proposal.proposal_hash == reordered.proposal_hash


def test_context_edits_change_hashes_and_reject_stale_confirmation_payloads() -> None:
    proposal = _proposal(scientific_context=EVENT_CONTEXT)
    edited = replace(proposal, scientific_context={**EVENT_CONTEXT, "time_unit": "ms"})
    original_contract = proposal.confirm(user_confirmed=True)
    edited_contract = edited.confirm(user_confirmed=True)
    assert proposal.proposal_hash != edited.proposal_hash
    assert original_contract.contract_hash != edited_contract.contract_hash
    stale = copy.deepcopy(original_contract.to_dict())
    stale["scientific_context"]["time_unit"] = "ms"
    with pytest.raises(SemanticContractError) as caught:
        parse_confirmed_semantic_contract(stale)
    assert caught.value.code == "semantic_proposal_hash_mismatch"
    stale.pop("proposal_hash")
    with pytest.raises(SemanticContractError) as caught:
        parse_confirmed_semantic_contract(stale)
    assert caught.value.code == "semantic_contract_hash_mismatch"


def test_context_does_not_infer_missing_values_or_bypass_confirmation() -> None:
    proposal = _proposal(scientific_context={"interval_label": "range"})
    assert proposal.to_dict()["scientific_context"] == {"interval_label": "range"}
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(user_confirmed=False)
    assert caught.value.code == "semantic_user_confirmation_required"


@pytest.mark.parametrize(
    "context",
    [
        {"unexpected": "value"}, {"time_unit": {"unit": "s"}},
        {"time_unit": ["s"]}, {"time_unit": True}, {"time_unit": 1},
        {"time_unit": None}, {"time_unit": ""},
    ],
)
def test_context_schema_errors_are_semantic_contract_errors(context: object) -> None:
    with pytest.raises(SemanticContractError) as caught:
        _proposal(scientific_context=context).validate()
    assert caught.value.code == "semantic_payload_schema_invalid"
    assert caught.value.details["field"] == "$.scientific_context"


@pytest.mark.parametrize(
    "context",
    [None, [], (), "s", True, 1, {"time_unit": False}, {"unknown": "s"},
     {"time_unit": {"nested": "s"}}, {"time_unit": ["s"]}, {"time_unit": 1}],
)
@pytest.mark.parametrize("confirmed", [False, True])
def test_public_parsers_require_context_to_be_a_strict_object(context: object, confirmed: bool) -> None:
    proposal = _proposal()
    payload = proposal.confirm(user_confirmed=True).to_dict() if confirmed else proposal.to_dict()
    payload.pop("proposal_hash", None)
    payload.pop("contract_hash", None)
    payload["scientific_context"] = context
    parser = parse_confirmed_semantic_contract if confirmed else parse_semantic_proposal
    with pytest.raises(SemanticContractError) as caught:
        parser(payload)
    assert caught.value.code == "semantic_payload_schema_invalid"


@pytest.mark.parametrize("bad_value", [True, "1.25", None, float("nan"), float("inf")])
def test_spatial_coordinate_declarations_must_be_finite_numbers(bad_value: object) -> None:
    with pytest.raises(SemanticContractError):
        replace(_proposal(), domain_family="spatial_profile", scientific_context={"profile_x": bad_value})


def test_unsupported_family_rejects_nonempty_context() -> None:
    with pytest.raises(SemanticContractError):
        replace(_proposal(), domain_family="xrd", scientific_context=EVENT_CONTEXT)


def test_scientific_analysis_passes_context_without_new_classification_items() -> None:
    payload = SimpleNamespace(
        source_sha256="a" * 64,
        assignments=(("Time", "x"), ("Response", "series")),
        mapping_confirmed=True,
        scientific_context=tuple(EVENT_CONTEXT.items()),
        plot_spec=SimpleNamespace(
            plot_kind="line", plot_mode="default", x_column="Time",
            series=(SimpleNamespace(source_column="Response", label="Response", axis="left"),),
        ),
    )
    prepared = SimpleNamespace(
        template_id="event_response", source_columns=("Time", "Response"), confidence=1.0,
        requires_confirmation=False, confirmation_reasons=(), payload=payload,
    )
    proposal = propose_prepared_semantics(prepared)
    assert proposal.to_dict()["scientific_context"] == EVENT_CONTEXT
    assert tuple(item.source_column for item in proposal.data_items) == ("Time", "Response")
    assert len(proposal.data_items) == 2
    assert proposal.derived_items == ()
    del payload.scientific_context
    assert "scientific_context" not in propose_prepared_semantics(prepared).to_dict()
