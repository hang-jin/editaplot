from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.data_loader import LoadedTable  # noqa: E402
from origin_sciplot.semantic_contract import (  # noqa: E402
    DataDisposition,
    SemanticContractError,
)
from origin_sciplot.xrd_semantics import (  # noqa: E402
    GSAS_II_POWDER_CSV,
    GSAS_II_PUBLICATION_CSV,
    XrdSemanticError,
    detect_xrd_source_profile,
    propose_xrd_semantics,
)

SOURCE_HASH = "b" * 64
WINDOWS_SEPARATOR = chr(92)
WINDOWS_SOURCE_PATH = WINDOWS_SEPARATOR.join(("C:", "data", "xrd.csv"))
WINDOWS_SOURCE_PATH_OTHER = WINDOWS_SEPARATOR.join(("D:", "another-machine", "same-data.csv"))


def _loaded(
    rows: dict[str, list[object]],
    *,
    source_profile: str | None = None,
    source_path: str = WINDOWS_SOURCE_PATH,
) -> LoadedTable:
    frame = pd.DataFrame(rows)
    return LoadedTable(
        source_path=source_path,
        source_sha256=SOURCE_HASH,
        source_size_bytes=1234,
        source_format="csv",
        delimiter=",",
        sheet_name=None,
        columns=tuple(str(column) for column in frame.columns),
        frame=frame,
        ignored_empty_rows=0,
        source_profile=source_profile,
    )


def _items_by_column(proposal) -> dict[str, object]:
    return {item.source_column: item for item in proposal.data_items}


def _elements_by_id(proposal) -> dict[str, object]:
    return {element.element_id: element for element in proposal.figure_elements}


def test_gsas_ii_powder_csv_roles_are_not_all_rendered_as_curves() -> None:
    loaded = _loaded(
        {
            "x": [10, 20, 30, 40],
            "y_obs": [100, 150, 130, 90],
            "weight": [0.1, 0.1, 0.1, 0.1],
            "y_calc": [98, 148, 131, 91],
            "y_bkg": [10, 11, 11, 10],
            "Q": [1.0, 2.0, 3.0, 4.0],
        },
        source_profile=GSAS_II_POWDER_CSV,
    )

    assert detect_xrd_source_profile(loaded) == GSAS_II_POWDER_CSV
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)
    elements = _elements_by_id(proposal)

    assert proposal.domain_mode == "rietveld_refinement"
    assert proposal.source_adapter_hint == GSAS_II_POWDER_CSV
    assert items["x"].semantic_role == "x_coordinate"
    assert items["y_obs"].disposition is DataDisposition.RENDER_PRIMARY
    assert items["y_calc"].disposition is DataDisposition.RENDER_PRIMARY
    assert items["y_bkg"].disposition is DataDisposition.RENDER_SECONDARY
    assert items["weight"].disposition is DataDisposition.SUPPORT_ONLY
    assert items["Q"].disposition is DataDisposition.RETAIN_NOT_RENDER
    assert elements["background_curve"].required is False
    assert elements["background_curve"].visible_by_default is True
    bound_item_ids = {item_id for element in proposal.figure_elements for item_id in element.data_item_ids}
    assert items["weight"].item_id not in bound_item_ids
    assert items["Q"].item_id not in bound_item_ids
    assert proposal.derived_items == ()
    proposal.confirm(user_confirmed=True).validate()


def test_refinement_background_column_is_optional_but_visible_when_present() -> None:
    without_background = _loaded(
        {
            "x": [10, 20, 30, 40],
            "y_obs": [100, 150, 130, 90],
            "weight": [0.1, 0.1, 0.1, 0.1],
            "y_calc": [98, 148, 131, 91],
            "Q": [1.0, 2.0, 3.0, 4.0],
        },
        source_profile=GSAS_II_POWDER_CSV,
    )
    proposal = propose_xrd_semantics(without_background)

    assert "background_curve" not in _elements_by_id(proposal)
    proposal.confirm(user_confirmed=True).validate()


def _publication_table() -> LoadedTable:
    return _loaded(
        {
            "Used": [1, 1, 1, 1, 1, 0],
            "X (2theta, deg)": [10, 20, 30, 40, 50, 60],
            "Obs": [100, 150, 130, 90, 70, 50],
            "Calc": [98, 148, 131, 91, 69, 0],
            "Bkg": [10, 11, 11, 10, 9, 0],
            "Diff": [-42, -40, -43, -44, -41, -90],
            "Phase alpha": [20, 40, None, None, None, None],
            "Phase beta": [30, None, None, None, None, None],
            "tick-pos": ["alpha", "-65", "beta", "-72", None, None],
            "diff/sigma": [0.2, 0.1, -0.1, -0.2, 0.1, None],
            "Axis-limits": [10, 60, -100, 170, None, None],
        },
        source_profile=GSAS_II_PUBLICATION_CSV,
    )


def test_gsas_ii_publication_csv_preserves_upstream_difference_and_phase_ticks() -> None:
    loaded = _publication_table()
    assert detect_xrd_source_profile(loaded) == GSAS_II_PUBLICATION_CSV

    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)
    elements = _elements_by_id(proposal)

    assert proposal.source_adapter_hint == GSAS_II_PUBLICATION_CSV
    assert items["Used"].semantic_role == "fit_mask"
    assert items["Used"].disposition is DataDisposition.SUPPORT_ONLY
    assert items["Diff"].semantic_role == "difference_curve"
    assert items["Diff"].disposition is DataDisposition.RENDER_SECONDARY
    assert "upstream_display_offset_preserved" in items["Diff"].evidence_codes
    assert proposal.derived_items == ()
    assert elements["difference_curve"].data_item_ids == (items["Diff"].item_id,)
    assert elements["difference_curve"].axis == "residual_y"

    assert items["Phase alpha"].semantic_role == "phase_reflection_positions"
    assert items["Phase beta"].semantic_role == "phase_reflection_positions"
    assert items["tick-pos"].semantic_role == "phase_tick_position_control"
    assert items["tick-pos"].disposition is DataDisposition.SUPPORT_ONLY
    assert items["diff/sigma"].disposition is DataDisposition.RETAIN_NOT_RENDER
    assert items["Axis-limits"].disposition is DataDisposition.SUPPORT_ONLY
    assert {"phase_ticks_006", "phase_ticks_007"}.issubset(elements)
    proposal.confirm(user_confirmed=True).validate()


def test_publication_diff_is_not_recreated_or_given_a_second_offset() -> None:
    proposal = propose_xrd_semantics(_publication_table())
    payload = proposal.to_dict()

    assert payload["derived_items"] == []
    diff = next(item for item in payload["data_items"] if item["source_column"] == "Diff")
    assert diff["item_type"] == "source_column"
    assert diff["semantic_role"] == "difference_curve"
    assert "upstream_display_offset_preserved" in diff["evidence_codes"]
    assert "offset_by_constant" not in json.dumps(payload, ensure_ascii=False)


def test_diff_sigma_alone_is_not_misclassified_as_publication_difference() -> None:
    loaded = _loaded(
        {
            "Used": [1, 1, 1, 1],
            "X": [10, 20, 30, 40],
            "Obs": [100, 150, 130, 90],
            "Calc": [98, 148, 131, 91],
            "Bkg": [10, 11, 11, 10],
            "diff/sigma": [0.2, 0.1, -0.1, -0.2],
        }
    )

    assert detect_xrd_source_profile(loaded) == "generic_rietveld"
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)

    assert "difference_curve" not in _elements_by_id(proposal)
    assert items["diff/sigma"].semantic_role == "weighted_residual_diagnostic"
    assert items["diff/sigma"].disposition is DataDisposition.RETAIN_NOT_RENDER


def test_ordinary_xrd_supports_one_or_multiple_named_intensity_series() -> None:
    loaded = _loaded(
        {
            "2Theta (degree)": [10, 20, 30, 40],
            "Sample A": [8, 14, 28, 16],
            "Sample B": [10, 18, 31, 19],
            "Intensity C": [9, 16, 29, 18],
        },
        source_profile=None,
    )
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)

    assert detect_xrd_source_profile(loaded) == "ordinary_xrd"
    assert proposal.domain_mode == "ordinary_scan"
    assert proposal.source_adapter_hint is None
    assert items["2Theta (degree)"].semantic_role == "x_coordinate"
    assert all(
        items[column].disposition is DataDisposition.RENDER_PRIMARY
        for column in ("Sample A", "Sample B", "Intensity C")
    )
    assert len(proposal.figure_elements) == 4
    proposal.confirm(user_confirmed=True).validate()


def test_generic_rietveld_headers_do_not_require_a_gsas_name() -> None:
    loaded = _loaded(
        {
            "2Theta": [10, 20, 30, 40],
            "Observed": [100, 150, 130, 90],
            "Calculated": [98, 148, 131, 91],
            "Background": [10, 11, 11, 10],
            "Residual": [2, 2, -1, -1],
        }
    )
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)

    assert detect_xrd_source_profile(loaded) == "generic_rietveld"
    assert proposal.domain_mode == "rietveld_refinement"
    assert proposal.source_adapter_hint is None
    assert items["Observed"].semantic_role == "observed_intensity"
    assert items["Calculated"].semantic_role == "calculated_intensity"
    assert items["Residual"].semantic_role == "difference_curve"


def test_unknown_numeric_column_is_uncertain_and_blocks_confirmation() -> None:
    loaded = _loaded(
        {
            "2Theta": [10, 20, 30, 40],
            "Intensity": [100, 150, 130, 90],
            "Temperature": [300, 310, 320, 330],
        }
    )
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)

    assert items["Temperature"].disposition is DataDisposition.UNCERTAIN
    assert items["Temperature"].semantic_role == "unclassified_numeric"
    assert proposal.domain_confidence == 0.62
    assert proposal.ambiguities[0].code == "xrd_unknown_numeric_column"
    with pytest.raises(SemanticContractError) as caught:
        proposal.confirm(
            user_confirmed=True,
            resolved_ambiguities={proposal.ambiguities[0].ambiguity_id: "support_only"},
        )
    assert caught.value.code == "semantic_uncertain_items"


def test_phase_column_needs_an_explicit_identity_and_sparse_positions() -> None:
    loaded = _loaded(
        {
            "Used": [1, 1, 1, 1],
            "X": [10, 20, 30, 40],
            "Obs": [100, 150, 130, 90],
            "Calc": [98, 148, 131, 91],
            "Bkg": [10, 11, 11, 10],
            "Diff": [-20, -18, -21, -22],
            "Phase": [10, 20, 30, 40],
            "tick-pos": ["phase", "-30", None, None],
            "diff/sigma": [0.2, 0.1, -0.1, -0.2],
            "Axis-limits": [10, 40, -30, 160],
        },
        source_profile=GSAS_II_PUBLICATION_CSV,
    )
    proposal = propose_xrd_semantics(loaded)
    items = _items_by_column(proposal)

    assert items["Phase"].disposition is DataDisposition.UNCERTAIN
    assert items["tick-pos"].disposition is DataDisposition.RETAIN_NOT_RENDER
    with pytest.raises(SemanticContractError, match="Uncertain"):
        proposal.confirm(
            user_confirmed=True,
            resolved_ambiguities={proposal.ambiguities[0].ambiguity_id: "retain_not_render"},
        )


def test_proposal_hash_uses_source_identity_and_classifies_all_columns_once() -> None:
    first = propose_xrd_semantics(_publication_table())
    second_loaded = replace(
        _publication_table(),
        source_path=WINDOWS_SOURCE_PATH_OTHER,
    )
    second = propose_xrd_semantics(second_loaded)

    assert first.source_sha256 == SOURCE_HASH
    assert first.source_columns == tuple(item.source_column for item in first.data_items)
    assert len({item.source_column for item in first.data_items}) == len(first.source_columns)
    assert first.proposal_hash == second.proposal_hash
    payload = json.dumps(first.to_dict(), ensure_ascii=False)
    assert WINDOWS_SOURCE_PATH.rsplit(WINDOWS_SEPARATOR, 1)[0] not in payload
    assert WINDOWS_SOURCE_PATH_OTHER.rsplit(WINDOWS_SEPARATOR, 1)[0] not in payload


@pytest.mark.parametrize(
    ("source_profile", "rows", "missing_role"),
    [
        (
            GSAS_II_POWDER_CSV,
            {
                "x": [10, 20],
                "y_obs": [100, 120],
                "weight": [0.1, 0.1],
                "y_bkg": [10, 10],
                "Q": [1, 2],
            },
            "calculated_intensity",
        ),
        (
            GSAS_II_PUBLICATION_CSV,
            {
                "Used": [1, 1],
                "X": [10, 20],
                "Calc": [98, 118],
                "Bkg": [10, 10],
                "Diff": [-20, -18],
            },
            "observed_intensity",
        ),
    ],
)
def test_refinement_profile_missing_observed_or_calculated_is_blocked(
    source_profile: str,
    rows: dict[str, list[object]],
    missing_role: str,
) -> None:
    loaded = _loaded(rows, source_profile=source_profile)

    with pytest.raises(XrdSemanticError) as caught:
        propose_xrd_semantics(loaded)
    assert caught.value.code == "xrd_required_role_missing"
    assert caught.value.details["role"] == missing_role
