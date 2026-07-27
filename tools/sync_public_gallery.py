"""Copy only verified and explicitly reviewed Origin PNGs into the public gallery."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "showcase" / "gallery"
OUTPUT = ROOT / "assets" / "gallery"

_OUTPUT_DIRECTORY_PATTERN = re.compile(r"origin-output(?:_[0-9]+)?\Z")
_MANUAL_PASS_VALUES = {"approved", "pass", "passed"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Missing {label}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid {label}: {path}")
    return payload


def _registered_case_titles() -> dict[str, str]:
    """Load case IDs from the showcase builder, not from the previous manifest."""
    from build_showcase import CASES  # Imported lazily for direct script execution.

    result: dict[str, str] = {}
    for case in CASES:
        case_id = str(case.id)
        title = getattr(case, "title_zh", None) or getattr(case, "intent", None) or case_id
        if case_id in result:
            raise RuntimeError(f"Duplicate showcase case ID: {case_id}")
        result[case_id] = str(title)
    return result


def _existing_titles(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.is_file():
        return {}
    manifest = _load_json(manifest_path, label="public gallery manifest")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError(f"Invalid public gallery manifest cases: {manifest_path}")
    titles: dict[str, str] = {}
    for item in cases:
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid public gallery manifest case: {manifest_path}")
        case_id = item.get("id")
        title = item.get("title_zh")
        if not isinstance(case_id, str) or not case_id or not isinstance(title, str) or not title:
            raise RuntimeError(f"Invalid public gallery manifest case: {manifest_path}")
        if case_id in titles:
            raise RuntimeError(f"Duplicate public gallery case ID: {case_id}")
        titles[case_id] = title
    return titles


def _resolve_recorded_path(raw_path: object, *, root: Path, case_directory: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise RuntimeError(f"Verification PNG path is missing: {case_directory.name}")
    recorded = Path(raw_path)
    if recorded.is_absolute():
        return recorded.resolve()
    candidates = ((case_directory / recorded).resolve(), (root / recorded).resolve())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _verified_png(
    case_id: str,
    *,
    root: Path,
    source_root: Path,
) -> tuple[Path, dict[str, Any]]:
    case_directory = (source_root / case_id).resolve()
    verification = _load_json(
        case_directory / "verification.json",
        label=f"verification record for {case_id}",
    )
    if verification.get("programmatic_pass") is not True:
        raise RuntimeError(f"Programmatic verification did not pass: {case_id}")
    artifacts = verification.get("artifacts")
    png_record = artifacts.get("png") if isinstance(artifacts, dict) else None
    if not isinstance(png_record, dict) or png_record.get("ok") is not True:
        raise RuntimeError(f"Verified PNG artifact is missing or failed: {case_id}")
    png_path = _resolve_recorded_path(
        png_record.get("path"),
        root=root,
        case_directory=case_directory,
    )
    if not png_path.is_relative_to(case_directory):
        raise RuntimeError(f"Verified PNG escapes its showcase case directory: {case_id}")
    if (
        not _OUTPUT_DIRECTORY_PATTERN.fullmatch(png_path.parent.name)
        or png_path.name != "result.png"
        or not png_path.is_file()
    ):
        raise RuntimeError(f"Verified Origin PNG path is invalid: {case_id}")
    expected_size = png_record.get("size_bytes")
    if isinstance(expected_size, int) and png_path.stat().st_size != expected_size:
        raise RuntimeError(f"Verified PNG size changed after verification: {case_id}")
    output_directory = verification.get("output_directory")
    if output_directory:
        recorded_output = _resolve_recorded_path(
            str(Path(str(output_directory)) / "result.png"),
            root=root,
            case_directory=case_directory,
        ).parent
        if recorded_output != png_path.parent:
            raise RuntimeError(f"Verification output directory does not match its PNG: {case_id}")
    return png_path, verification


def _embedded_manual_review_passes(
    verification: Mapping[str, Any],
    *,
    png_path: Path,
) -> bool:
    review = verification.get("human_visual_qa")
    if not isinstance(review, Mapping):
        return False
    status = str(review.get("status", "")).strip().casefold()
    reviewer = str(review.get("reviewer", "")).strip()
    reviewed_on = str(review.get("reviewed_on", "")).strip()
    note = str(review.get("visual_note") or review.get("notes") or "").strip()
    digest = str(review.get("png_sha256", "")).strip().casefold()
    return (
        status in _MANUAL_PASS_VALUES
        and bool(reviewer)
        and bool(reviewed_on)
        and bool(note)
        and digest == sha256(png_path)
    )


def _legacy_manual_review_passes(
    case_id: str,
    *,
    root: Path,
    case_directory: Path,
    png_path: Path,
    visual_qa: Mapping[str, Any] | None,
) -> bool:
    """Accept the existing path-bound visual-qa record for old gallery cases."""
    if visual_qa is None or not isinstance(visual_qa.get("cases"), list):
        return False
    for record in visual_qa["cases"]:
        if not isinstance(record, Mapping) or record.get("id") != case_id:
            continue
        artifacts = record.get("artifacts")
        recorded_png = artifacts.get("png") if isinstance(artifacts, Mapping) else None
        if not recorded_png:
            return False
        review_path = _resolve_recorded_path(
            recorded_png,
            root=root,
            case_directory=case_directory,
        )
        return (
            record.get("programmatic_status") == "pass"
            and record.get("manual_visual_review") == "pass"
            and bool(str(record.get("reviewer", "")).strip())
            and bool(str(record.get("visual_note", "")).strip())
            and review_path == png_path
        )
    return False


def _require_manual_review(
    case_id: str,
    *,
    root: Path,
    source_root: Path,
    png_path: Path,
    verification: Mapping[str, Any],
    visual_qa: Mapping[str, Any] | None,
) -> None:
    if _embedded_manual_review_passes(verification, png_path=png_path):
        return
    if _legacy_manual_review_passes(
        case_id,
        root=root,
        case_directory=(source_root / case_id).resolve(),
        png_path=png_path,
        visual_qa=visual_qa,
    ):
        return
    raise RuntimeError(
        f"Explicit manual visual review is missing or is not bound to the verified PNG: {case_id}"
    )


def sync_gallery(
    *,
    root: Path = ROOT,
    selected_ids: Sequence[str] = (),
    registered_titles: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    root = root.resolve()
    source_root = root / "showcase" / "gallery"
    output_root = root / "assets" / "gallery"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "gallery-manifest.json"
    existing_titles = _existing_titles(manifest_path)
    registry = dict(registered_titles or _registered_case_titles())
    known_ids = set(existing_titles) | set(registry)
    selected = sorted(set(selected_ids) if selected_ids else set(existing_titles))
    if not selected and not existing_titles:
        selected = sorted(registry)
    unknown = sorted(set(selected) - known_ids)
    if unknown:
        raise RuntimeError(f"Unknown public gallery case(s): {', '.join(unknown)}")

    visual_qa_path = root / "showcase" / "visual-qa.json"
    visual_qa = (
        _load_json(visual_qa_path, label="manual visual review register")
        if visual_qa_path.is_file()
        else None
    )
    titles = dict(existing_titles)
    for case_id in selected:
        png_path, verification = _verified_png(
            case_id,
            root=root,
            source_root=source_root,
        )
        _require_manual_review(
            case_id,
            root=root,
            source_root=source_root,
            png_path=png_path,
            verification=verification,
            visual_qa=visual_qa,
        )
        shutil.copy2(png_path, output_root / f"{case_id}.png")
        titles.setdefault(case_id, registry.get(case_id, case_id))

    records: list[dict[str, object]] = []
    for case_id in sorted(titles):
        destination = output_root / f"{case_id}.png"
        if not destination.is_file():
            raise RuntimeError(f"Missing public PNG: {case_id}")
        records.append(
            {
                "id": case_id,
                "title_zh": titles[case_id],
                "sha256": sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "asset_policy": (
                    "programmatically verified and explicitly manually reviewed Origin PNG "
                    "from synthetic teaching data only; local logs, plans, OPJU, PDF and TIF excluded"
                ),
                "case_count": len(records),
                "cases": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    lines = [
        "# Origin 2024b 实机生成并复核的图形示例",
        "",
        "以下图片均使用本机 Origin/OriginPro 2024b（10.15）生成，并已完成",
        "OPJU/PNG/PDF/TIF、对象反读和人工视觉检查。",
        "全部展示数据均为项目生成的合成教学数据，不代表测量、材料性能或临床结论。",
        "GitHub 源码仓库只保留脱敏 PNG；可编辑项目和其他格式不直接写入源码历史。",
        "",
        '<div align="center">',
    ]
    for record in records:
        lines.append(
            f'<img src="../assets/gallery/{record["id"]}.png" alt="{record["title_zh"]}" width="31%" />'
        )
    lines.extend(["</div>", ""])
    docs_path = root / "docs" / "gallery.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    sync_gallery(selected_ids=args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
