from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

PRODUCT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PRODUCT_ROOT / "skill" / "editaplot" / "scripts"
RUNTIME = PRODUCT_ROOT / "runtime"
sys.path.insert(0, str(SCRIPTS))

import editaplot as editaplot_cli  # noqa: E402
from editaplot_core import (  # noqa: E402
    EditaPlotError,
    build_plan,
    start_session,
    understand_data,
    validate_plan,
)


def test_beginner_start_includes_column_dispositions_and_element_confirmation() -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"

    result = start_session(
        source,
        intent="XRD diffraction comparison",
        engine_home=RUNTIME,
    )

    understanding = result["semantic_understanding"]
    assert understanding["ok"] is True
    assert understanding["confirmation_gate"]["required"] is True
    assert len(understanding["understanding"]["column_decisions"]) == 4
    assert understanding["understanding"]["figure_elements"]
    assert any(
        item["id"] == "semantic_element_checklist"
        for item in result["confirmation_questions"]
    )
    assert result["execution"]["origin_called"] is False


def test_plan_requires_hash_bound_semantic_confirmation() -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"

    with pytest.raises(EditaPlotError) as missing:
        build_plan(
            source,
            template_id="xrd",
            claim="The supplied patterns differ.",
            evidence_role="comparison",
            engine_home=RUNTIME,
        )
    assert missing.value.code == "semantic_confirmation_required"

    understanding = understand_data(source, template_id="xrd", engine_home=RUNTIME)
    confirmation = dict(
        understanding["confirmation_gate"]["confirmation_payload_template"]
    )
    confirmation["proposal_hash"] = "0" * 64
    with pytest.raises(EditaPlotError) as stale:
        build_plan(
            source,
            template_id="xrd",
            claim="The supplied patterns differ.",
            evidence_role="comparison",
            semantic_confirmation=confirmation,
            engine_home=RUNTIME,
        )
    assert stale.value.code == "semantic_proposal_hash_mismatch"


def test_confirmed_plan_carries_a_complete_semantic_contract() -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    understanding = understand_data(source, template_id="xrd", engine_home=RUNTIME)

    plan = build_plan(
        source,
        template_id="xrd",
        claim="The supplied patterns differ.",
        evidence_role="comparison",
        semantic_confirmation=understanding["confirmation_gate"][
            "confirmation_payload_template"
        ],
        engine_home=RUNTIME,
    )

    contract = plan["data_understanding"]
    assert contract["status"] == "confirmed"
    assert contract["source_sha256"] == plan["source"]["sha256"]
    assert {item["source_column"] for item in contract["data_items"]} == set(
        plan["source"]["columns"]
    )
    assert not any(
        item["disposition"] == "uncertain" for item in contract["data_items"]
    )
    validate_plan(plan)


def test_plan_validation_strictly_rejects_unknown_semantic_fields() -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    understanding = understand_data(source, template_id="xrd", engine_home=RUNTIME)
    plan = build_plan(
        source,
        template_id="xrd",
        claim="The supplied patterns differ.",
        evidence_role="comparison",
        semantic_confirmation=understanding["confirmation_gate"][
            "confirmation_payload_template"
        ],
        engine_home=RUNTIME,
    )
    tampered = copy.deepcopy(plan)
    tampered["data_understanding"]["data_items"][0]["origin_command"] = "run anything"
    contract_payload = dict(tampered["data_understanding"])
    contract_payload.pop("contract_hash")
    tampered["data_understanding"]["contract_hash"] = hashlib.sha256(
        json.dumps(
            contract_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    plan_payload = dict(tampered)
    plan_payload.pop("plan_hash")
    tampered["plan_hash"] = hashlib.sha256(
        json.dumps(
            plan_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(EditaPlotError) as caught:
        validate_plan(tampered)

    assert caught.value.code == "semantic_payload_unknown_fields"


def test_understand_cli_writes_agent_facing_confirmation_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = RUNTIME / "templates" / "xrd" / "example_standard.csv"
    output = tmp_path / "understanding.json"

    returncode = editaplot_cli.main(
        [
            "understand",
            str(source),
            "--template-id",
            "xrd",
            "--output",
            str(output),
            "--engine-home",
            str(RUNTIME),
        ]
    )

    assert returncode == 0
    stdout = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert stdout == saved
    assert saved["state"] == "awaiting_semantic_confirmation"
    assert saved["confirmation_gate"]["confirmation_payload_template"]["confirmed"] is True


def test_confirmed_xrd_mapping_replaces_raw_detector_ambiguity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "generic-rietveld.csv"
    source.write_text(
        "\n".join(
            (
                "2Theta,Observed,Calculated,Temperature",
                "20,101,99,298",
                "21,115,113,299",
                "22,120,118,300",
                "23,119,118,301",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    mapping = {
        "plot_mode": "rietveld_refinement",
        "assignments": {
            "2Theta": "x",
            "Observed": "observed",
            "Calculated": "calculated",
            "Temperature": "support",
        },
    }

    understanding = understand_data(
        source,
        template_id="xrd",
        mapping=mapping,
        engine_home=RUNTIME,
    )

    decisions = {
        item["source_column"]: item
        for item in understanding["understanding"]["column_decisions"]
    }
    assert understanding["state"] == "awaiting_semantic_confirmation"
    assert understanding["confirmation_gate"]["can_confirm_now"] is True
    assert decisions["Observed"]["disposition"] == "render_primary"
    assert decisions["Calculated"]["disposition"] == "render_primary"
    assert decisions["Temperature"]["disposition"] == "support_only"


def test_gsas_publication_understanding_lists_draw_and_nonrender_columns() -> None:
    source = (
        RUNTIME
        / "templates"
        / "xrd"
        / "example_gsas_publication.csv"
    )

    understanding = understand_data(
        source,
        template_id="xrd",
        engine_home=RUNTIME,
    )

    decisions = {
        item["source_column"]: item
        for item in understanding["understanding"]["column_decisions"]
    }
    elements = {
        item["element_id"]: item
        for item in understanding["understanding"]["figure_elements"]
    }
    assert decisions["Obs"]["disposition"] == "render_primary"
    assert decisions["Calc"]["disposition"] == "render_primary"
    assert decisions["Diff"]["disposition"] == "render_secondary"
    assert decisions["Phase alpha"]["disposition"] == "render_secondary"
    assert decisions["Used"]["disposition"] == "support_only"
    assert decisions["diff/sigma"]["disposition"] == "retain_not_render"
    assert elements["observed_points"]["element_kind"] == "markers"
    assert elements["calculated_curve"]["element_kind"] == "line"
    assert elements["difference_curve"]["axis"] == "residual_y"
    assert elements["phase_ticks_006"]["axis"] == "phase_ticks"
