from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RUNTIME_SRC = Path(__file__).resolve().parents[1] / "runtime" / "src"
sys.path.insert(0, str(RUNTIME_SRC))

from origin_sciplot.origin_backend.safe_errors import OriginDrawError  # noqa: E402
from origin_sciplot.origin_backend.scientific_renderer import (  # noqa: E402
    _prepare_origin_table,
    _verify_axis_numeric_contract,
)
from origin_sciplot.scientific_preview import render_scientific_preview_png  # noqa: E402
from origin_sciplot.scientific_visual import series_palette_colors  # noqa: E402
from origin_sciplot.scientific_workflow import (  # noqa: E402
    ScientificColumnMapping,
    ScientificWorkflowError,
    load_scientific_frame,
    prepare_scientific,
    series_values,
)
from origin_sciplot.template_registry import TemplateRegistry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "runtime" / "templates"


@pytest.mark.parametrize(
    "template_id",
    ["dsc", "nmr", "ftir", "xps_compare", "pl", "uv_vis"],
)
def test_material_template_manifest_is_public_and_complete(template_id: str) -> None:
    manifest = TemplateRegistry(TEMPLATE_ROOT).get(template_id)

    assert manifest.status == "implemented"
    assert manifest.visibility == "public"
    assert manifest.workflow == "scientific_table"
    assert manifest.example_path.is_file()
    assert manifest.schema_path.is_file()
    assert manifest.runner_path.is_file()
    assert manifest.service_path is not None and manifest.service_path.is_file()
    assert manifest.blank_template_path is not None and manifest.blank_template_path.is_file()
    assert (manifest.directory / "data_contract.md").is_file()
    assert (manifest.directory / "visual_contract.md").is_file()


def test_dsc_example_preserves_heat_flow_direction_and_units() -> None:
    source = TEMPLATE_ROOT / "dsc" / "example_standard.csv"
    before = source.read_bytes()

    preparation = prepare_scientific(source, "dsc")

    assert preparation.requires_confirmation is False
    assert preparation.plot_spec.plot_mode == "overlay"
    assert preparation.plot_spec.x_title == "Temperature (°C)"
    assert preparation.plot_spec.y_title == "Heat flow (W/g)"
    assert preparation.plot_spec.display_transform == "identity"
    assert all(series.display_offset == 0.0 for series in preparation.plot_spec.series)
    assert preparation.plot_spec.display_plan.figure_style is not None
    assert preparation.plot_spec.display_plan.figure_style.palette_name == "thermal_analysis"
    assert source.read_bytes() == before


def test_nmr_example_uses_isotope_label_and_descending_axis_without_reverse_flag() -> None:
    source = TEMPLATE_ROOT / "nmr" / "example_standard.csv"

    preparation = prepare_scientific(source, "nmr")
    axis = preparation.plot_spec.axis_plan

    assert preparation.plot_spec.x_title == "¹⁹F Chemical shift (ppm)"
    assert preparation.plot_spec.y_title == "Intensity (a.u.)"
    assert axis.x_from is not None and axis.x_to is not None
    assert axis.x_from > axis.x_to
    assert axis.x_step is not None and axis.x_step < 0
    assert "descending_spectral_axis" in preparation.warnings
    assert preparation.plot_spec.display_transform == "identity"


def test_ftir_temperature_series_are_line_only_and_have_unique_ordered_colors() -> None:
    source = TEMPLATE_ROOT / "ftir" / "example_standard.csv"
    preparation = prepare_scientific(source, "ftir")
    style = preparation.plot_spec.display_plan.figure_style

    assert style is not None
    assert preparation.plot_spec.x_title == "Wavenumber (cm⁻¹)"
    assert preparation.plot_spec.y_title == "Transmittance (%)"
    assert preparation.plot_spec.display_plan.marker_size_pt == 0.0
    assert style.palette_name == "spectroscopy_temperature"
    colors = series_palette_colors(style.palette_name, len(preparation.plot_spec.series))
    assert len(colors) == 6
    assert len(set(colors)) == 6
    assert colors[0] != colors[-1]


def test_explicit_stacked_offset_uses_helpers_and_never_changes_source(tmp_path: Path) -> None:
    source = tmp_path / "nmr.csv"
    source.write_text(
        "19F Chemical Shift (ppm),Sample A (a.u.),Sample B (a.u.)\n"
        "-120,0.10,0.08\n"
        "-130,0.80,0.62\n"
        "-140,0.12,0.10\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    mapping = ScientificColumnMapping(
        assignments=(
            ("19F Chemical Shift (ppm)", "x"),
            ("Sample A (a.u.)", "series"),
            ("Sample B (a.u.)", "series"),
        ),
        plot_mode="stacked_offset",
    )

    preparation = prepare_scientific(source, "nmr", column_mapping=mapping)
    frame = load_scientific_frame(source, preparation)
    frame_snapshot = frame.copy(deep=True)
    first, second = preparation.plot_spec.series
    plan = _prepare_origin_table(frame, preparation)

    assert first.display_offset == 0.0
    assert second.display_offset > 0.0
    np.testing.assert_allclose(
        series_values(frame, second),
        frame[second.source_column].to_numpy(dtype=float) + second.display_offset,
    )
    assert plan.helper_columns
    assert second.source_column != plan.series[1].plot_column
    assert plan.series[1].plot_column in plan.helper_columns
    assert all(name not in frame.columns for name in plan.helper_columns)
    pd.testing.assert_frame_equal(frame, frame_snapshot)
    assert source.read_bytes() == before
    assert "display_vertical_offset_helper_only" in preparation.warnings


def test_overlay_mode_does_not_create_display_helpers() -> None:
    source = TEMPLATE_ROOT / "dsc" / "example_standard.csv"
    preparation = prepare_scientific(source, "dsc")
    frame = load_scientific_frame(source, preparation)

    plan = _prepare_origin_table(frame, preparation)

    assert plan.helper_columns == ()
    assert plan.source_frame_unchanged is True
    assert all(item.plot_column == item.source_column for item in plan.series)


def test_xps_compare_example_uses_measured_series_and_descending_binding_energy() -> None:
    source = TEMPLATE_ROOT / "xps_compare" / "example_standard.csv"

    preparation = prepare_scientific(source, "xps_compare")
    axis = preparation.plot_spec.axis_plan

    assert preparation.requires_confirmation is False
    assert len(preparation.plot_spec.series) == 3
    assert preparation.plot_spec.x_title == "Binding Energy (eV)"
    assert preparation.plot_spec.y_title == "Counts"
    assert axis.x_from is not None and axis.x_to is not None
    assert axis.x_from > axis.x_to
    assert axis.x_step is not None and axis.x_step < 0
    assert preparation.plot_spec.display_plan.marker_size_pt == 0.0
    assert preparation.plot_spec.display_plan.figure_style is not None
    assert preparation.plot_spec.display_plan.figure_style.palette_name == "materials_comparison"


def test_xps_fit_table_is_not_misrouted_as_independent_spectra(tmp_path: Path) -> None:
    source = tmp_path / "xps_fit.csv"
    source.write_text(
        "Binding Energy (eV),Raw Counts,Background,Envelope Fit,Component 1,Residual\n"
        "290,120,30,118,62,2\n"
        "285,420,35,415,300,5\n"
        "280,150,32,151,78,-1\n",
        encoding="utf-8",
    )

    with pytest.raises(ScientificWorkflowError) as raised:
        prepare_scientific(source, "xps_compare")

    assert raised.value.code == "xps_fit_table_requires_fit_template"


def test_xps_compare_keeps_fit_columns_hidden_and_requires_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "xps_compare_with_support.csv"
    source.write_text(
        "结合能 (eV),样品A 强度,样品B 强度,Background,Residual\n"
        "290,120,100,22,1\n"
        "285,420,365,25,-2\n"
        "280,150,132,23,1\n",
        encoding="utf-8",
    )

    preparation = prepare_scientific(source, "xps_compare")
    assignments = dict(preparation.assignments)

    assert assignments["样品A 强度"] == "series"
    assert assignments["样品B 强度"] == "series"
    assert assignments["Background"] == "ignored"
    assert assignments["Residual"] == "ignored"
    assert preparation.requires_confirmation is True
    assert "xps_fit_columns_ignored_use_fit_template" in preparation.confirmation_reasons


@pytest.mark.parametrize(
    ("template_id", "example_name"),
    [
        ("nmr", "example_standard.csv"),
        ("ftir", "example_standard.csv"),
        ("xps_compare", "example_standard.csv"),
    ],
)
def test_descending_spectral_axis_readback_is_a_hard_gate(
    template_id: str,
    example_name: str,
) -> None:
    preparation = prepare_scientific(TEMPLATE_ROOT / template_id / example_name, template_id)
    plan = preparation.plot_spec.axis_plan
    state = {
        "x.from": float(plan.x_from),
        "x.to": float(plan.x_to),
        "x.inc": float(plan.x_step),
        "y.from": float(plan.y_from),
        "y.to": float(plan.y_to),
        "y.inc": float(plan.y_step),
    }

    _verify_axis_numeric_contract(state, preparation)
    wrong_direction = dict(state)
    wrong_direction["x.from"], wrong_direction["x.to"] = (
        wrong_direction["x.to"],
        wrong_direction["x.from"],
    )
    wrong_direction["x.inc"] = abs(wrong_direction["x.inc"])

    with pytest.raises(OriginDrawError, match="descending direction"):
        _verify_axis_numeric_contract(wrong_direction, preparation)


@pytest.mark.parametrize(
    ("template_id", "example_name"),
    [
        ("pl", "example_temperature_series.csv"),
        ("uv_vis", "example_multi_spectrum.csv"),
    ],
)
def test_material_multiseries_examples_use_noncycling_publication_palette(
    template_id: str,
    example_name: str,
) -> None:
    source = TEMPLATE_ROOT / template_id / example_name
    preparation = prepare_scientific(source, template_id)
    style = preparation.plot_spec.display_plan.figure_style

    assert style is not None
    colors = series_palette_colors(style.palette_name, len(preparation.plot_spec.series))
    assert len(colors) == len(preparation.plot_spec.series)
    assert len(set(colors)) == len(colors)
    assert preparation.plot_spec.display_plan.marker_size_pt == 0.0
    assert preparation.plot_spec.display_transform == "identity"
    frame = load_scientific_frame(source, preparation)
    plan = _prepare_origin_table(frame, preparation)
    assert all(item.plot_type == "l" for item in plan.series)
    assert all(item.marker_size_pt == 0.0 for item in plan.series)


def test_dsc_numeric_program_metadata_is_not_silently_plotted(tmp_path: Path) -> None:
    source = tmp_path / "dsc_metadata.csv"
    source.write_text(
        "Temperature (°C),Time (min),Cycle,Heat Flow (W/g)\n30,0,1,0.12\n60,2,1,0.08\n90,4,1,-0.04\n",
        encoding="utf-8",
    )

    preparation = prepare_scientific(source, "dsc")
    assignments = dict(preparation.assignments)

    assert assignments["Heat Flow (W/g)"] == "series"
    assert assignments["Time (min)"] == "ignored"
    assert assignments["Cycle"] == "ignored"
    assert preparation.requires_confirmation is True
    assert "material_numeric_metadata_ignored" in preparation.confirmation_reasons


def test_uv_vis_numeric_time_metadata_is_not_silently_plotted(tmp_path: Path) -> None:
    source = tmp_path / "uv_metadata.csv"
    source.write_text(
        "Wavelength (nm),Absorbance (a.u.),Time (s)\n300,0.91,0\n400,0.44,1\n500,0.18,2\n",
        encoding="utf-8",
    )

    preparation = prepare_scientific(source, "uv_vis")
    assignments = dict(preparation.assignments)

    assert assignments["Absorbance (a.u.)"] == "series"
    assert assignments["Time (s)"] == "ignored"
    assert preparation.requires_confirmation is True
    assert "material_numeric_metadata_ignored" in preparation.confirmation_reasons


def test_wavelength_pl_with_user_fit_remains_steady_state(tmp_path: Path) -> None:
    source = tmp_path / "steady_pl_fit.csv"
    source.write_text(
        "Wavelength (nm),Sample PL Intensity (a.u.),Sample PL Intensity Fit\n"
        "450,0.12,0.11\n"
        "500,0.92,0.90\n"
        "550,0.18,0.19\n",
        encoding="utf-8",
    )

    preparation = prepare_scientific(source, "pl")

    assert preparation.plot_spec.plot_mode == "steady_state"
    assert preparation.plot_spec.plot_kind == "pl_spectrum"
    assert preparation.plot_spec.x_title == "Wavelength (nm)"
    assert preparation.plot_spec.y_scale == "linear"
    assert dict(preparation.assignments)["Sample PL Intensity Fit"] == "fit"


@pytest.mark.parametrize(
    ("template_id", "example_name"),
    [
        ("dsc", "example_standard.csv"),
        ("nmr", "example_standard.csv"),
        ("ftir", "example_standard.csv"),
        ("xps_compare", "example_standard.csv"),
        ("pl", "example_temperature_series.csv"),
        ("uv_vis", "example_multi_spectrum.csv"),
    ],
)
def test_material_preview_pipeline_returns_a_nonempty_png(
    template_id: str,
    example_name: str,
) -> None:
    preparation = prepare_scientific(TEMPLATE_ROOT / template_id / example_name, template_id)

    png = render_scientific_preview_png(preparation)

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000
