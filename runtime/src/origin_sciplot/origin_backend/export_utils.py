"""Origin graph export helpers."""

from __future__ import annotations

from pathlib import Path

from .safe_errors import OriginExportError
from .verify_utils import require_nonempty


def export_graph(
    origin,
    graph,
    output_png: Path,
    output_pdf: Path,
    output_tif: Path | None = None,
    *,
    raster_width: int = 2100,
) -> dict[str, bool]:
    outputs = {
        "png": (output_png, {"width": raster_width}),
    }
    result: dict[str, bool] = {}
    for key, (target, options) in outputs.items():
        ok = graph.save_fig(str(target), type=target.suffix[1:].lower(), **options)
        if not ok:
            raise OriginExportError(f"Origin did not export {target.name}")
        try:
            require_nonempty(target)
        except RuntimeError as exc:
            raise OriginExportError(str(exc)) from exc
        result[key] = True

    output_pdf.unlink(missing_ok=True)
    graph.activate()
    pdf_command = (
        f'expGraph type:=pdf export:=page filename:="{output_pdf.stem}" '
        f'path:="{output_pdf.parent.as_posix()}" overwrite:=replace sysopts:=0 keepsize:=1 '
        "tr.Margin:=2 tr2.PDF.Fonts.Embed:=1 tr2.PDF.Fonts.TrueType:=1;"
    )
    if not origin.lt_exec(pdf_command):
        raise OriginExportError(f"Origin did not export {output_pdf.name} with embedded fonts")
    try:
        require_nonempty(output_pdf)
    except RuntimeError as exc:
        raise OriginExportError(str(exc)) from exc
    if b"/FontFile" not in output_pdf.read_bytes():
        raise OriginExportError(f"Origin PDF does not contain embedded fonts: {output_pdf.name}")
    result["pdf"] = True

    if output_tif is not None:
        ok = graph.save_fig(str(output_tif), type="tif", width=raster_width)
        if not ok:
            raise OriginExportError(f"Origin did not export {output_tif.name}")
        try:
            require_nonempty(output_tif)
        except RuntimeError as exc:
            raise OriginExportError(str(exc)) from exc
        result["tif"] = True
    return result
