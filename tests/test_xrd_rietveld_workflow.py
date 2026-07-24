from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    prepare_scientific,
    role_options,
)


def _write(path: Path, lines: list[str]) -> bytes:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.read_bytes()


def test_xrd_mapping_ui_exposes_refinement_and_nonrendering_roles() -> None:
    options = role_options("xrd")
    keys = tuple(key for key, _label, _unique in options)
    unique = {key for key, _label, is_unique in options if is_unique}

    assert keys == (
        "x",
        "observed",
        "calculated",
        "background",
        "difference",
        "phase_tick",
        "support",
        "series",
        "ignored",
    )
    assert unique == {"x", "observed", "calculated", "background", "difference"}


def test_gsas_powder_workflow_maps_control_columns_without_plotting_them(
    tmp_path: Path,
) -> None:
    source = tmp_path / "powder.csv"
    before = _write(
        source,
        [
            '"Histogram","PWDR sample"',
            '"Instparm: Type","PXC"',
            '"Samparm: Temperature",298.15',
            '"x","y_obs","weight","y_calc","y_bkg","Q"',
            "20,101,0.04,99,12,1.42",
            "21,115,0.04,113,13,1.49",
            "22,120,0.04,118,13,1.56",
            "23,119,0.04,118,13,1.63",
        ],
    )

    prepared = prepare_scientific(source, "xrd")
    spec = prepared.plot_spec
    assignments = dict(prepared.assignments)

    assert prepared.requires_confirmation is False
    assert spec.plot_kind == "rietveld_refinement"
    assert spec.plot_mode == "rietveld_refinement"
    assert spec.source_profile == "gsas_ii_powder_csv"
    assert spec.phase_tick_columns == ()
    assert assignments == {
        "x": "x",
        "y_obs": "observed",
        "weight": "support",
        "y_calc": "calculated",
        "y_bkg": "background",
        "Q": "support",
    }
    assert [item.series_role for item in spec.series] == [
        "observed",
        "calculated",
        "background",
    ]
    assert {item.source_column for item in spec.series} == {
        "y_obs",
        "y_calc",
        "y_bkg",
    }
    assert source.read_bytes() == before


def test_gsas_publication_workflow_preserves_diff_and_freezes_phase_ticks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "publication.csv"
    before = _write(
        source,
        [
            ('Used,"X (2theta, deg)",Obs,Calc,Bkg,Diff,Phase alpha,tick-pos,diff/sigma,Axis-limits'),
            "1,20,101,99,12,-48,20.4,alpha,0.2,20",
            "1,21,115,113,13,-47,21.3,-65,0.3,80",
            "1,22,120,118,13,-46,,,0.1,-70",
            "1,23,119,118,13,-45,,,0.2,130",
        ],
    )

    prepared = prepare_scientific(source, "xrd")
    spec = prepared.plot_spec
    assignments = dict(prepared.assignments)
    series_by_role = {item.series_role: item for item in spec.series}

    assert prepared.requires_confirmation is False
    assert spec.plot_kind == "rietveld_refinement"
    assert spec.plot_mode == "rietveld_refinement"
    assert spec.source_profile == "gsas_ii_publication_csv"
    assert spec.phase_tick_columns == ("Phase alpha",)
    assert assignments["Phase alpha"] == "phase_tick"
    for column in ("Used", "tick-pos", "diff/sigma", "Axis-limits"):
        assert assignments[column] == "support"
        assert column not in {item.source_column for item in spec.series}
    assert series_by_role["observed"].source_column == "Obs"
    assert series_by_role["calculated"].source_column == "Calc"
    assert series_by_role["background"].source_column == "Bkg"
    assert series_by_role["difference"].source_column == "Diff"
    assert series_by_role["difference"].transform == "identity"
    assert spec.display_transform == "identity"
    assert spec.x_title == "2θ (deg)"
    payload = json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True)
    assert "offset_by_constant" not in payload
    assert "normalize_max_and_offset" not in payload
    assert source.read_bytes() == before

    demoted_difference = dict(prepared.assignments)
    demoted_difference["Diff"] = "support"
    with pytest.raises(ScientificWorkflowError) as caught:
        prepare_scientific(
            source,
            "xrd",
            column_mapping=ScientificColumnMapping(
                assignments=tuple(demoted_difference.items()),
                plot_mode="rietveld_refinement",
            ),
        )
    assert caught.value.code == "xrd_publication_difference_missing"


def test_ordinary_xrd_keeps_multi_pattern_display_contract() -> None:
    source = Path(__file__).resolve().parents[1] / "runtime" / "templates" / "xrd" / "example_standard.csv"

    prepared = prepare_scientific(source, "xrd")
    spec = prepared.plot_spec

    assert prepared.requires_confirmation is False
    assert spec.plot_kind == "stacked_line"
    assert spec.plot_mode == "ordinary_scan"
    assert spec.source_profile == "ordinary_xrd"
    assert spec.display_transform == "normalize_max_and_offset"
    assert spec.phase_tick_columns == ()
    assert all(item.series_role == "data" for item in spec.series)


def test_unknown_numeric_xrd_column_requires_mapping_confirmation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unknown-extra.csv"
    _write(
        source,
        [
            "2Theta,Intensity,Temperature",
            "20,101,298",
            "21,115,299",
            "22,120,300",
            "23,119,301",
        ],
    )

    proposed = prepare_scientific(source, "xrd")

    assert proposed.requires_confirmation is True
    assert proposed.confirmation_reasons == ("xrd_unknown_numeric_column",)
    assert dict(proposed.assignments)["Temperature"] == "support"
    assert "Temperature" not in {item.source_column for item in proposed.plot_spec.series}

    confirmed = prepare_scientific(
        source,
        "xrd",
        column_mapping=ScientificColumnMapping(
            assignments=proposed.assignments,
            plot_mode="ordinary_scan",
        ),
    )
    assert confirmed.requires_confirmation is False
    assert confirmed.mapping_confirmed is True
    assert dict(confirmed.assignments)["Temperature"] == "support"


def test_generic_numeric_wide_xrd_reaches_confirmation_instead_of_failing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "generic-series.csv"
    _write(
        source,
        [
            "2Theta,A,B",
            "20,101,98",
            "21,115,112",
            "22,120,117",
            "23,119,116",
        ],
    )

    prepared = prepare_scientific(source, "xrd")

    assert prepared.requires_confirmation is True
    assert dict(prepared.assignments) == {
        "2Theta": "x",
        "A": "series",
        "B": "series",
    }
    assert prepared.plot_spec.plot_kind == "stacked_line"
    assert prepared.plot_spec.display_transform == "normalize_max_and_offset"


def test_generic_rietveld_mapping_stays_behind_confirmation_gate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "generic-rietveld.csv"
    _write(
        source,
        [
            "2Theta,Observed,Calculated,Background,Residual",
            "20,101,99,12,2",
            "21,115,113,13,2",
            "22,120,118,13,2",
            "23,119,118,13,1",
        ],
    )

    prepared = prepare_scientific(source, "xrd")

    assert prepared.plot_spec.plot_kind == "rietveld_refinement"
    assert prepared.plot_spec.source_profile == "generic_rietveld"
    assert prepared.requires_confirmation is True
    assert "xrd_generic_rietveld_requires_confirmation" in prepared.confirmation_reasons
