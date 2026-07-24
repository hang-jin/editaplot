"""Isolated, evidence-producing Origin compatibility smoke test."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origin_sciplot.scientific_visual import AdaptiveOriginStyle

from .base_style_contract import pt_to_origin_width_units
from .capabilities import ConnectionMode
from .export_utils import export_graph
from .safe_errors import (
    OriginDrawError,
    OriginEnvironmentError,
    OriginExportError,
)
from .session import OriginSession
from .template_capabilities import (
    CapabilityProbeResult,
    OriginCapability,
)
from .verify_utils import (
    require_nonempty,
    verify_page_and_layer,
    verify_plot_color,
    verify_plot_line_widths,
    verify_text_fonts,
    verify_text_sizes,
)

READY_COMMAND = "sec -poc 3;"
SMOKE_STYLE = AdaptiveOriginStyle(
    profile_name="origin-compatibility-smoke",
    page_width_cm=18.0,
    page_height_cm=12.0,
    layer_left_percent=17.0,
    layer_top_percent=6.0,
    layer_width_percent=78.0,
    layer_height_percent=80.0,
    axis_title_size_pt=18.0,
    tick_label_size_pt=15.0,
    legend_size_pt=15.0,
    plot_line_width_pt=2.4,
    frame_line_width_pt=1.6,
    major_tick_length_pt=5.0,
    minor_tick_length_pt=3.0,
)
SMOKE_STAGES = (
    "activate",
    "read_version",
    "read_program_path",
    "ready",
    "create_book",
    "create_graph",
    "style_graph",
    "save_project",
    "export",
    "readback",
    "cleanup",
)
SMOKE_AVAILABLE_CAPABILITIES = frozenset(
    {
        OriginCapability.CORE_2D,
        OriginCapability.EDITABLE_OPJU,
        OriginCapability.PNG_EXPORT,
        OriginCapability.PDF_EXPORT,
        OriginCapability.TIF_EXPORT,
        OriginCapability.AXIS_READBACK,
        OriginCapability.TEXT_READBACK,
    }
)


@dataclass(frozen=True)
class _SmokePaths:
    output_dir: Path
    result_opju: Path
    result_png: Path
    result_pdf: Path
    result_tif: Path
    environment_report: Path
    origin_verify_report: Path
    compatibility_report: Path

    @classmethod
    def create(cls, output_dir: str | Path) -> _SmokePaths:
        target = Path(output_dir).resolve()
        if target.exists() and not target.is_dir():
            raise OriginEnvironmentError(
                "Origin smoke output must be a directory",
                code="smoke_output_not_directory",
                stage="prepare_output",
            )
        target.mkdir(parents=True, exist_ok=True)
        paths = cls(
            output_dir=target,
            result_opju=target / "result.opju",
            result_png=target / "result.png",
            result_pdf=target / "result.pdf",
            result_tif=target / "result.tif",
            environment_report=target / "environment_report.json",
            origin_verify_report=target / "origin_verify_report.json",
            compatibility_report=target / "compatibility-report.json",
        )
        conflicts = [
            path.name
            for path in paths.artifact_paths()
            if path.exists()
        ]
        if conflicts:
            error = OriginEnvironmentError(
                "Origin smoke output directory already contains smoke artifacts",
                code="smoke_output_conflict",
                stage="prepare_output",
            )
            if not paths.compatibility_report.exists():
                _write_json(
                    paths.compatibility_report,
                    {
                        "schema_version": 1,
                        "status": "failed",
                        "connection_mode": ConnectionMode.NEW_ISOLATED.value,
                        "stages": _new_stage_records(),
                        "error": _safe_error_payload(error),
                    },
                )
            raise error
        return paths

    def artifact_paths(self) -> tuple[Path, ...]:
        return (
            self.result_opju,
            self.result_png,
            self.result_pdf,
            self.result_tif,
            self.environment_report,
            self.origin_verify_report,
            self.compatibility_report,
        )

    def required_origin_artifacts(self) -> tuple[Path, ...]:
        return (
            self.result_opju,
            self.result_png,
            self.result_pdf,
            self.result_tif,
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _new_stage_records() -> dict[str, dict[str, Any]]:
    return {
        name: {"status": "pending"}
        for name in SMOKE_STAGES
    }


def _mark_passed(
    stages: dict[str, dict[str, Any]],
    stage: str,
    **details: Any,
) -> None:
    stages[stage] = {"status": "passed", **details}


def _mark_failed(
    stages: dict[str, dict[str, Any]],
    stage: str,
    error: BaseException,
) -> None:
    stages[stage] = {
        "status": "failed",
        "error_code": str(getattr(error, "code", "origin_smoke_failed")),
    }


def _safe_identifier(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value)
    if not text or any(not (character.isalnum() or character == "_") for character in text):
        return fallback
    return text[:80]


def _stable_stage_error(stage: str, cause: Exception) -> Exception:
    if isinstance(cause, OriginEnvironmentError):
        messages = {
            "activate": "Origin Automation could not be activated",
            "read_version": "Origin version could not be read",
            "read_program_path": "Origin program path could not be read",
            "ready": "Origin did not become ready",
        }
        return OriginEnvironmentError(
            messages.get(stage, "Origin smoke environment check failed"),
            code=_safe_identifier(
                getattr(cause, "code", None),
                f"origin_smoke_{stage}_failed",
            ),
            stage=_safe_identifier(getattr(cause, "stage", None), stage),
        )

    if stage in {"activate", "read_version", "read_program_path", "ready"}:
        messages = {
            "activate": "Origin Automation could not be activated",
            "read_version": "Origin version could not be read",
            "read_program_path": "Origin program path could not be read",
            "ready": "Origin did not become ready",
        }
        return OriginEnvironmentError(
            messages[stage],
            code=f"origin_smoke_{stage}_failed",
            stage=stage,
        )
    if stage == "export":
        return OriginExportError(
            "Origin smoke exports were not completed",
            code="origin_smoke_export_failed",
            stage=stage,
        )
    if stage == "save_project":
        return OriginDrawError(
            "Origin smoke project could not be saved",
            code="origin_smoke_save_project_failed",
            stage=stage,
        )
    if stage == "readback":
        return OriginDrawError(
            "Origin smoke object readback failed",
            code="origin_smoke_readback_failed",
            stage=stage,
        )
    if stage == "style_graph":
        return OriginDrawError(
            "Origin smoke graph styling failed",
            code="origin_smoke_style_graph_failed",
            stage=stage,
        )
    if stage == "cleanup":
        return OriginEnvironmentError(
            "Origin smoke session cleanup failed",
            code="origin_smoke_cleanup_failed",
            stage=stage,
        )
    return OriginDrawError(
        "Origin smoke graph could not be created",
        code=f"origin_smoke_{stage}_failed",
        stage=stage,
    )


def _safe_error_payload(error: BaseException) -> dict[str, str]:
    return {
        "type": type(error).__name__,
        "code": str(getattr(error, "code", "origin_smoke_failed")),
        "stage": str(getattr(error, "stage", "origin_smoke")),
        "message": str(error).replace("\r", " ").replace("\n", " ")[:240],
    }


def _artifact_evidence(
    candidates: tuple[Path, ...],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in candidates:
        exists = path.is_file()
        result[path.name] = {
            "generated": exists,
            "size_bytes": path.stat().st_size if exists else 0,
        }
    return result


def _version_advisory_payload(
    environment_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize non-blocking version evidence for every smoke report."""

    source = environment_payload or {}
    version_status = str(source.get("version_status", "")).strip().lower()
    if version_status not in {"recognized", "unknown"}:
        product = str(source.get("origin_product", "unknown")).strip().lower()
        compatibility = str(
            source.get("origin_compatibility_status", "unknown")
        ).strip().lower()
        version_status = (
            "unknown"
            if product == "unknown" or compatibility == "unknown"
            else "recognized"
        )

    risks = source.get("known_version_risks", [])
    if not isinstance(risks, list):
        risks = []
    probe_priority = str(source.get("probe_priority", "")).strip().lower()
    if probe_priority not in {"high", "normal"}:
        probe_priority = (
            "high"
            if version_status == "unknown"
            or any(
                isinstance(risk, dict) and risk.get("probe_priority") == "high"
                for risk in risks
            )
            else "normal"
        )

    return {
        "version_status": version_status,
        "known_version_risks": risks,
        "probe_priority": probe_priority,
        "requires_full_capability_probe": version_status == "unknown",
        "advisory_only": True,
        "blocks_render": False,
    }


def _write_compatibility_report(
    paths: _SmokePaths,
    *,
    status: str,
    keep_open: bool,
    stages: dict[str, dict[str, Any]],
    environment_payload: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "connection_mode": ConnectionMode.NEW_ISOLATED.value,
        "keep_open": bool(keep_open),
        "stages": [dict(name=name, **stages[name]) for name in SMOKE_STAGES],
        "capability_probe": _capability_probe_from_stages(stages).to_dict(),
        "version_advisory": _version_advisory_payload(environment_payload),
        # A report cannot truthfully include its own final byte count while it
        # is being serialized, so evidence covers every other fixed artifact.
        "artifacts": _artifact_evidence(
            tuple(
                path
                for path in paths.artifact_paths()
                if path != paths.compatibility_report
            )
        ),
        "privacy": {
            "raw_exception_included": False,
            "hresult_included": False,
            "program_path_included": False,
        },
    }
    if error is not None:
        payload["error"] = _safe_error_payload(error)
    _write_json(paths.compatibility_report, payload)


def _capability_probe_from_stages(
    stages: dict[str, dict[str, Any]],
) -> CapabilityProbeResult:
    """Report only capabilities that this minimal smoke actually exercised."""

    available: set[OriginCapability] = set()
    unavailable: set[OriginCapability] = set()
    if stages["create_graph"]["status"] == "passed":
        available.add(OriginCapability.CORE_2D)
    if stages["style_graph"]["status"] == "passed":
        available.add(OriginCapability.TEXT_READBACK)
    if stages["save_project"]["status"] == "passed":
        available.add(OriginCapability.EDITABLE_OPJU)
    if stages["export"]["status"] == "passed":
        available.update(
            {
                OriginCapability.PNG_EXPORT,
                OriginCapability.PDF_EXPORT,
                OriginCapability.TIF_EXPORT,
            }
        )
    if stages["readback"]["status"] == "passed":
        available.add(OriginCapability.AXIS_READBACK)

    failed_stage = next(
        (
            name
            for name in SMOKE_STAGES
            if stages[name]["status"] == "failed"
        ),
        None,
    )
    failure_capability = {
        "create_graph": OriginCapability.CORE_2D,
        "style_graph": OriginCapability.TEXT_READBACK,
        "save_project": OriginCapability.EDITABLE_OPJU,
        "readback": OriginCapability.AXIS_READBACK,
    }.get(failed_stage)
    if failure_capability is not None and failure_capability not in available:
        unavailable.add(failure_capability)
    return CapabilityProbeResult(
        available_capabilities=frozenset(available),
        unavailable_capabilities=frozenset(unavailable),
        probe_complete=False,
    )


def _read_axis(axis: Any) -> dict[str, Any]:
    limits = tuple(float(value) for value in axis.limits)
    if len(limits) != 3 or not all(math.isfinite(value) for value in limits):
        raise ValueError("axis limits are incomplete")
    return {
        "limits": list(limits),
        "scale": int(axis.scale),
    }


def _position_smoke_titles(
    op: Any,
    layer: Any,
    labels: dict[str, Any],
) -> tuple[float, float]:
    """Place the two axis titles inside the physical page, independent of templates."""

    page_width = float(op.lt_float("page.width"))
    page_height = float(op.lt_float("page.height"))
    layer_left = float(layer.get_float("left"))
    layer_top = float(layer.get_float("top"))
    layer_width = float(layer.get_float("width"))
    layer_height = float(layer.get_float("height"))
    padding_x = page_width * 0.005
    padding_y = page_height * 0.005

    x_title = labels["x_title"]
    x_width = float(x_title.get_float("width"))
    x_height = float(x_title.get_float("height"))
    x_left = page_width * (layer_left + layer_width / 2.0) / 100.0 - x_width / 2.0
    x_top = (
        page_height * (layer_top + layer_height + (100.0 - layer_top - layer_height) / 2.0)
        / 100.0
        - x_height / 2.0
    )
    x_title.set_float(
        "left",
        min(max(x_left, padding_x), page_width - x_width - padding_x),
    )
    x_title.set_float(
        "top",
        min(max(x_top, padding_y), page_height - x_height - padding_y),
    )

    y_title = labels["y_title"]
    y_width = float(y_title.get_float("width"))
    y_height = float(y_title.get_float("height"))
    y_left = page_width * layer_left * 0.26 / 100.0 - y_width / 2.0
    y_top = page_height * (layer_top + layer_height / 2.0) / 100.0 - y_height / 2.0
    y_title.set_float(
        "left",
        min(max(y_left, padding_x), page_width - y_width - padding_x),
    )
    y_title.set_float(
        "top",
        min(max(y_top, padding_y), page_height - y_height - padding_y),
    )
    return page_width, page_height


def _style_smoke_graph(
    op: Any,
    graph: Any,
    layer: Any,
    plot: Any,
) -> dict[str, Any]:
    """Make the smoke image deterministic despite user template defaults."""

    graph.activate()
    if not graph.obj.LT_execute("page.updatetoprinter=0;page.kar=0;doc -uw;"):
        raise RuntimeError("page setup failed")
    graph.obj.PutWidth(SMOKE_STYLE.page_width_cm / 2.54)
    graph.obj.PutHeight(SMOKE_STYLE.page_height_cm / 2.54)
    expected_background = int(op.ocolor("#FFFFFF"))
    graph.set_int("background", expected_background)
    layer.set_int("unit", 1)
    layer.set_float("left", SMOKE_STYLE.layer_left_percent)
    layer.set_float("top", SMOKE_STYLE.layer_top_percent)
    layer.set_float("width", SMOKE_STYLE.layer_width_percent)
    layer.set_float("height", SMOKE_STYLE.layer_height_percent)
    layer.set_int("fixed", SMOKE_STYLE.layer_fixed)
    layer.set_float("factor", SMOKE_STYLE.layer_factor)

    font_code = int(round(float(op.lt_float(f"font({SMOKE_STYLE.font_family})"))))
    for axis_name in ("x", "y"):
        layer.set_int(f"{axis_name}.showGrids", 0)
        layer.set_int(f"{axis_name}.showAxes", 3)
        layer.set_int(f"{axis_name}.atZero", 0)
        layer.set_int(f"{axis_name}.ticks", 5)
        layer.set_int(f"{axis_name}.showLabels", 1)
        layer.set_int(f"{axis_name}.showlabel", 1)
        layer.set_int(f"{axis_name}.label.show", 1)
        layer.set_int(f"{axis_name}.label.type", 1)
        layer.set_int(f"{axis_name}.label.numFormat", 1)
        layer.set_int(f"{axis_name}.label.align", 1)
        layer.set_int(f"{axis_name}.label.table", 0)
        # A few installations inherit "label minor ticks" from the user's
        # Line template.  The smoke does not need minor ticks, so disabling
        # them is the clearest cross-version baseline.
        layer.set_int(f"{axis_name}.minorTicks", 0)
        layer.set_int(f"{axis_name}.label.font", font_code)
        layer.set_int(f"{axis_name}.label.color", 1)
        layer.set_float(f"{axis_name}.label.pt", SMOKE_STYLE.tick_label_size_pt)
        layer.set_float(f"{axis_name}.label.rotate", 0.0)
        layer.set_float(f"{axis_name}.thickness", SMOKE_STYLE.frame_line_width_pt)
        layer.set_float(
            f"{axis_name}.tickthickness",
            SMOKE_STYLE.frame_line_width_pt,
        )
        layer.set_float(f"{axis_name}.mtickthickness", 1.0)
        layer.set_float(f"{axis_name}.ticklength", SMOKE_STYLE.major_tick_length_pt)
        layer.set_float(f"{axis_name}.mticklength", SMOKE_STYLE.minor_tick_length_pt)

    # Do not write shared x2/y2 showLabels or minorTicks properties.  On
    # Origin 10.15 those can alter the visible bottom/left axes.
    for axis_name in ("x2", "y2"):
        layer.set_int(f"{axis_name}.ticks", 0)
        layer.set_int(f"{axis_name}.showlabel", 0)
        layer.set_int(f"{axis_name}.label.show", 0)
        layer.set_int(f"{axis_name}.label.table", 0)
    layer.set_int("x.showLabels", 1)
    layer.set_int("x.showlabel", 1)
    layer.set_int("x.label.show", 1)
    layer.set_int("y.showLabels", 1)
    layer.set_int("y.showlabel", 1)
    layer.set_int("y.label.show", 1)
    layer.axis("x").set_limits(0.0, 3.0, 1.0)
    layer.axis("y").set_limits(0.0, 10.0, 2.0)
    if not layer.obj.LT_execute(
        f"layer.x.label.font=font({SMOKE_STYLE.font_family});"
        f"layer.x.label.color=color(black);"
        f"layer.x.label.pt={SMOKE_STYLE.tick_label_size_pt};"
        f"layer.y.label.font=font({SMOKE_STYLE.font_family});"
        f"layer.y.label.color=color(black);"
        f"layer.y.label.pt={SMOKE_STYLE.tick_label_size_pt};"
    ):
        raise RuntimeError("axis font setup failed")

    layer.axis("x").title = "Independent variable"
    layer.axis("y").title = "Response"
    layer.axis("x2").title = ""
    layer.axis("y2").title = ""
    labels = {
        "x_title": layer.label("xb"),
        "y_title": layer.label("yl"),
    }
    for name, text in (
        ("x_title", "Independent variable"),
        ("y_title", "Response"),
    ):
        label = labels[name]
        if label is None:
            raise RuntimeError(f"{name} is missing")
        label.text = rf"\b({text})"
        label.set_int("show", 1)
        label.set_int("attach", 1)
        label.set_int("font", font_code)
        label.set_int("bold", 1)
        label.set_int("color", 1)
        label.set_float("fsize", SMOKE_STYLE.axis_title_size_pt)
    # Object-property assignment commands can return False on Origin 10.15
    # even when the properties are applied.  The readback gates below are the
    # source of truth.
    layer.obj.LT_execute(
        f"xb.font=font({SMOKE_STYLE.font_family});xb.bold=1;"
        f"xb.color=color(black);xb.fsize={SMOKE_STYLE.axis_title_size_pt};"
        f"yl.font=font({SMOKE_STYLE.font_family});yl.bold=1;"
        f"yl.color=color(black);yl.fsize={SMOKE_STYLE.axis_title_size_pt};"
    )

    legend_present_before = False
    for legend_name in ("legend", "Legend"):
        legend = None
        with suppress(Exception):
            legend = layer.label(legend_name)
        if legend is not None:
            legend.remove()
            legend_present_before = True

    line_color = "#245B9A"
    plot.color = line_color
    plot.set_cmd(
        f"-c color({line_color})",
        f"-w {pt_to_origin_width_units(SMOKE_STYLE.plot_line_width_pt)}",
        "-d 0",
    )
    if not graph.obj.LT_execute("doc -uw;"):
        raise RuntimeError("graph update failed")
    page_width, page_height = _position_smoke_titles(op, layer, labels)
    if not graph.obj.LT_execute("doc -uw;"):
        raise RuntimeError("title position update failed")
    for legend_name in ("legend", "Legend"):
        remaining = None
        with suppress(Exception):
            remaining = layer.label(legend_name)
        if remaining is not None:
            raise RuntimeError("inherited legend was not removed")

    page_state = verify_page_and_layer(
        graph,
        layer,
        style=SMOKE_STYLE,
    )
    text_sizes = verify_text_sizes(
        labels,
        {
            "x_title": SMOKE_STYLE.axis_title_size_pt,
            "y_title": SMOKE_STYLE.axis_title_size_pt,
        },
    )
    text_fonts = verify_text_fonts(
        op,
        labels,
        SMOKE_STYLE.font_family,
    )
    title_objects: dict[str, dict[str, Any]] = {}
    for name, expected_text in (
        ("x_title", r"\b(Independent variable)"),
        ("y_title", r"\b(Response)"),
    ):
        label = labels[name]
        state = {
            "text": str(label.text),
            "show": int(label.get_int("show")),
            "attach": int(label.get_int("attach")),
            "color": int(label.get_int("color")),
        }
        if (
            state["text"] != expected_text
            or state["show"] != 1
            or state["attach"] != 1
            or state["color"] != 1
        ):
            raise RuntimeError(f"{name} visibility readback failed")
        title_objects[name] = state
    plot_width = verify_plot_line_widths(
        op,
        {"smoke_line": plot},
        SMOKE_STYLE.plot_line_width_pt,
    )
    plot_color = verify_plot_color(
        op,
        plot,
        line_color,
        variable_name="__osc_smoke_color",
    )
    if not plot.layer.LT_execute(
        f"{{range __osc_smoke_plot={plot.lt_range()};"
        "get __osc_smoke_plot -d __osc_smoke_line_style;}"
    ):
        raise RuntimeError("line-style readback failed")
    line_style = float(op.lt_float("__osc_smoke_line_style"))
    if abs(line_style) > 0.05:
        raise RuntimeError("smoke line is not solid")
    background = int(graph.get_int("background"))
    # Origin 10.15 canonicalizes explicit white to the page-default code 0.
    if background not in {0, expected_background}:
        raise RuntimeError(
            "graph background readback failed"
        )

    title_geometry: dict[str, float] = {
        "page.width": page_width,
        "page.height": page_height,
    }
    for name, label in labels.items():
        attachment = int(label.get_int("attach"))
        title_geometry[f"{name}.attach"] = float(attachment)
        if attachment != 1:
            raise RuntimeError(f"{name} is not attached to the page")
        for prop in ("left", "top", "width", "height"):
            title_geometry[f"{name}.{prop}"] = float(label.get_float(prop))
        left = title_geometry[f"{name}.left"]
        top = title_geometry[f"{name}.top"]
        right = left + title_geometry[f"{name}.width"]
        bottom = top + title_geometry[f"{name}.height"]
        if left < 0 or top < 0 or right > page_width or bottom > page_height:
            raise RuntimeError(f"{name} is clipped")

    axis_style: dict[str, float | int] = {"font_code_expected": font_code}
    for axis_name in ("x", "y"):
        axis_style[f"{axis_name}.label.font"] = int(
            layer.get_int(f"{axis_name}.label.font")
        )
        axis_style[f"{axis_name}.label.pt"] = float(
            layer.get_float(f"{axis_name}.label.pt")
        )
        axis_style[f"{axis_name}.label.rotate"] = float(
            layer.get_float(f"{axis_name}.label.rotate")
        )
        axis_style[f"{axis_name}.label.table"] = int(
            layer.get_int(f"{axis_name}.label.table")
        )
        axis_style[f"{axis_name}.minorTicks"] = int(
            layer.get_int(f"{axis_name}.minorTicks")
        )
        axis_style[f"{axis_name}.thickness"] = float(
            layer.get_float(f"{axis_name}.thickness")
        )
        if axis_style[f"{axis_name}.label.font"] != font_code:
            raise RuntimeError(f"{axis_name} font readback failed")
        if (
            abs(
                float(axis_style[f"{axis_name}.label.pt"])
                - SMOKE_STYLE.tick_label_size_pt
            )
            > 0.05
        ):
            raise RuntimeError(f"{axis_name} point-size readback failed")
        if abs(float(axis_style[f"{axis_name}.label.rotate"])) > 0.05:
            raise RuntimeError(f"{axis_name} rotation readback failed")
        if int(axis_style[f"{axis_name}.label.table"]) != 0:
            raise RuntimeError(f"{axis_name} inherited a label table")
        if int(axis_style[f"{axis_name}.minorTicks"]) != 0:
            raise RuntimeError(f"{axis_name} inherited minor ticks")
        if (
            abs(
                float(axis_style[f"{axis_name}.thickness"])
                - SMOKE_STYLE.frame_line_width_pt
            )
            > 0.05
        ):
            raise RuntimeError(f"{axis_name} frame readback failed")
    return {
        "style_profile": SMOKE_STYLE.to_dict(),
        "page_layer": page_state,
        "axis_style": axis_style,
        "title_sizes": text_sizes,
        "title_fonts": text_fonts,
        "title_objects": title_objects,
        "title_geometry": title_geometry,
        "plot_width": plot_width,
        "plot_color": plot_color,
        "line_style": line_style,
        "background_color_code": background,
        "legend_present_before": legend_present_before,
        "legend_absent_after": True,
    }


def _environment_payload(environment: Any) -> dict[str, Any]:
    to_dict = getattr(environment, "to_dict", None)
    if not callable(to_dict):
        raise ValueError("session environment is not serializable")
    payload = to_dict()
    if not isinstance(payload, dict):
        raise ValueError("session environment is invalid")
    result = dict(payload)
    advisory_to_dict = getattr(environment, "version_advisory_to_dict", None)
    if callable(advisory_to_dict):
        advisory = advisory_to_dict()
        if not isinstance(advisory, dict):
            raise ValueError("session version advisory is invalid")
        result.update(advisory)
    result.update(_version_advisory_payload(result))
    return result


def _require_origin_artifacts(paths: _SmokePaths) -> None:
    for path in paths.required_origin_artifacts():
        require_nonempty(path)


def _session_failure_stage(
    stages: dict[str, dict[str, Any]],
    error: OriginEnvironmentError,
) -> str:
    if error.stage in {"read_version", "validate_version"}:
        _mark_passed(stages, "activate")
        return "read_version"
    return "activate"


def run_origin_smoke(
    output_dir: str | Path,
    keep_open: bool = False,
    session_factory: Callable[..., Any] = OriginSession,
) -> dict[str, Any]:
    """Run a minimal isolated Origin workflow and produce auditable evidence.

    The function never attaches to a user-owned Origin session.  It creates a
    fresh session, a two-column workbook, and a Line graph, then requires a
    non-empty editable project plus PNG/PDF/TIF exports and X/Y axis readback.
    """

    paths = _SmokePaths.create(output_dir)
    stages = _new_stage_records()
    current_stage = "activate"
    environment_payload: dict[str, Any] | None = None
    verify_report: dict[str, Any] | None = None

    try:
        session_context = session_factory(
            keep_open=keep_open,
            connection_mode=ConnectionMode.NEW_ISOLATED,
        )
        with session_context as session:
            op = getattr(session, "op", None)
            environment = getattr(session, "environment", None)
            if op is None or environment is None:
                raise RuntimeError("session did not initialize")
            environment_payload = _environment_payload(environment)
            version_advisory = _version_advisory_payload(environment_payload)
            _mark_passed(
                stages,
                "activate",
                connection_mode=ConnectionMode.NEW_ISOLATED.value,
            )
            _mark_passed(
                stages,
                "read_version",
                origin_version=str(environment_payload.get("origin_version", "unknown")),
                origin_version_raw=environment_payload.get("origin_version_raw"),
                origin_product=str(environment_payload.get("origin_product", "unknown")),
                version_status=version_advisory["version_status"],
                known_version_risks=version_advisory["known_version_risks"],
                probe_priority=version_advisory["probe_priority"],
                advisory_only=True,
                blocks_render=False,
            )

            current_stage = "read_program_path"
            program_path = op.path("e")
            if not isinstance(program_path, str) or not program_path.strip():
                raise ValueError("Origin returned an empty program path")
            _mark_passed(stages, current_stage, detected=True)

            current_stage = "ready"
            if not op.lt_exec(READY_COMMAND):
                raise RuntimeError("Origin readiness command failed")
            _mark_passed(stages, current_stage, command=READY_COMMAND)

            current_stage = "create_book"
            book = op.new_book("w", "EditaPlot Compatibility Smoke")
            if book is None:
                raise RuntimeError("Origin returned no workbook")
            sheet = book[0]
            sheet.from_list(0, [0.0, 1.0, 2.0, 3.0], lname="X", axis="X")
            sheet.from_list(1, [0.0, 1.0, 4.0, 9.0], lname="Y", axis="Y")
            _mark_passed(stages, current_stage, rows=4, columns=2)

            current_stage = "create_graph"
            graph = op.new_graph("EditaPlot Compatibility Smoke", template="Line")
            if graph is None:
                raise RuntimeError("Origin returned no graph")
            layer = graph[0]
            plot = layer.add_plot(sheet, "Y", "X", type="l")
            if plot is None:
                raise RuntimeError("Origin returned no data plot")
            layer.rescale()
            _mark_passed(stages, current_stage, template="Line", plot_count=1)

            current_stage = "style_graph"
            style_state = _style_smoke_graph(op, graph, layer, plot)
            _mark_passed(
                stages,
                current_stage,
                font_family=SMOKE_STYLE.font_family,
                axis_title_size_pt=SMOKE_STYLE.axis_title_size_pt,
                tick_label_size_pt=SMOKE_STYLE.tick_label_size_pt,
                line_width_pt=SMOKE_STYLE.plot_line_width_pt,
            )

            current_stage = "save_project"
            if not op.save(str(paths.result_opju)):
                raise RuntimeError("Origin save returned false")
            require_nonempty(paths.result_opju)
            _mark_passed(stages, current_stage)

            current_stage = "export"
            exports = export_graph(
                op,
                graph,
                paths.result_png,
                paths.result_pdf,
                paths.result_tif,
            )
            _require_origin_artifacts(paths)
            _mark_passed(stages, current_stage, **exports)

            current_stage = "readback"
            axis_state = {
                "x": _read_axis(layer.axis("x")),
                "y": _read_axis(layer.axis("y")),
            }
            verify_report = {
                "smoke_test": True,
                "capability_probe": CapabilityProbeResult(
                    available_capabilities=SMOKE_AVAILABLE_CAPABILITIES,
                    probe_complete=False,
                ).to_dict(),
                "program_path_readback": {
                    "detected": bool(program_path.strip()),
                    "value_included": False,
                },
                "origin_axis_state": axis_state,
                "origin_style_state": style_state,
                "exports": exports,
                "required_artifacts": _artifact_evidence(
                    paths.required_origin_artifacts()
                ),
            }
            _write_json(
                paths.environment_report,
                {
                    "backend": "Origin",
                    "smoke_test": True,
                    "program_path_readback": True,
                    **environment_payload,
                },
            )
            _write_json(paths.origin_verify_report, verify_report)
            require_nonempty(paths.environment_report)
            require_nonempty(paths.origin_verify_report)
            _mark_passed(
                stages,
                current_stage,
                x_axis_object=True,
                y_axis_object=True,
                program_path=True,
            )

            # A context-exit lifecycle failure must still fail the smoke test.
            current_stage = "cleanup"

        _mark_passed(stages, "cleanup")
        _write_compatibility_report(
            paths,
            status="passed",
            keep_open=keep_open,
            stages=stages,
            environment_payload=environment_payload,
        )
        require_nonempty(paths.compatibility_report)
    except Exception as cause:  # noqa: BLE001 - normalize and redact every local failure
        if isinstance(cause, OriginEnvironmentError) and current_stage == "activate":
            current_stage = _session_failure_stage(stages, cause)
        stable_error = _stable_stage_error(current_stage, cause)
        _mark_failed(stages, current_stage, stable_error)
        with suppress(Exception):
            _write_compatibility_report(
                paths,
                status="failed",
                keep_open=keep_open,
                stages=stages,
                environment_payload=environment_payload,
                error=stable_error,
            )
        if stable_error is cause:
            raise
        raise stable_error from cause

    if environment_payload is None or verify_report is None:
        raise OriginDrawError("Origin smoke result was incomplete")
    return {
        "status": "passed",
        "opju": str(paths.result_opju),
        "png": str(paths.result_png),
        "pdf": str(paths.result_pdf),
        "tif": str(paths.result_tif),
        "environment_report": str(paths.environment_report),
        "origin_verify_report": str(paths.origin_verify_report),
        "compatibility_report": str(paths.compatibility_report),
        "verify": verify_report,
    }


__all__ = [
    "READY_COMMAND",
    "SMOKE_AVAILABLE_CAPABILITIES",
    "SMOKE_STAGES",
    "SMOKE_STYLE",
    "run_origin_smoke",
]
