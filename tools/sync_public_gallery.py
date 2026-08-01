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


def _registered_case_metadata() -> dict[str, dict[str, object]]:
    """Load display metadata from the showcase builder, not from the previous manifest."""
    from build_showcase import CASES  # Imported lazily for direct script execution.

    result: dict[str, dict[str, object]] = {}
    for case in CASES:
        case_id = str(case.id)
        title_zh = getattr(case, "title_zh", None) or getattr(case, "intent", None) or case_id
        title_en = getattr(case, "intent", None) or case_id
        if case_id in result:
            raise RuntimeError(f"Duplicate showcase case ID: {case_id}")
        result[case_id] = {
            "title_zh": str(title_zh),
            "title_en": str(title_en),
            "display_in_gallery": bool(getattr(case, "display_in_gallery", True)),
        }
    return result


def _registered_case_titles() -> dict[str, str]:
    """Return the legacy title-only registry used by focused tests and callers."""
    return {case_id: str(metadata["title_zh"]) for case_id, metadata in _registered_case_metadata().items()}


def _existing_case_metadata(manifest_path: Path) -> dict[str, dict[str, object]]:
    if not manifest_path.is_file():
        return {}
    manifest = _load_json(manifest_path, label="public gallery manifest")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError(f"Invalid public gallery manifest cases: {manifest_path}")
    metadata: dict[str, dict[str, object]] = {}
    for item in cases:
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid public gallery manifest case: {manifest_path}")
        case_id = item.get("id")
        title = item.get("title_zh")
        title_en = item.get("title_en", case_id)
        if not isinstance(case_id, str) or not case_id or not isinstance(title, str) or not title:
            raise RuntimeError(f"Invalid public gallery manifest case: {manifest_path}")
        if not isinstance(title_en, str) or not title_en:
            raise RuntimeError(f"Invalid public gallery English title: {manifest_path}")
        display_in_gallery = item.get("display_in_gallery", True)
        if not isinstance(display_in_gallery, bool):
            raise RuntimeError(f"Invalid public gallery display flag: {manifest_path}")
        if case_id in metadata:
            raise RuntimeError(f"Duplicate public gallery case ID: {case_id}")
        metadata[case_id] = {
            "title_zh": title,
            "title_en": title_en,
            "display_in_gallery": display_in_gallery,
        }
    return metadata


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
    registered_visibility: Mapping[str, bool] | None = None,
) -> list[dict[str, object]]:
    root = root.resolve()
    source_root = root / "showcase" / "gallery"
    output_root = root / "assets" / "gallery"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "gallery-manifest.json"
    existing_metadata = _existing_case_metadata(manifest_path)
    registry_metadata = (
        {
            case_id: {
                "title_zh": title,
                "title_en": title,
                "display_in_gallery": (
                    registered_visibility.get(case_id, True) if registered_visibility is not None else True
                ),
            }
            for case_id, title in registered_titles.items()
        }
        if registered_titles is not None
        else _registered_case_metadata()
    )
    if registered_visibility is not None:
        unknown_visibility = sorted(set(registered_visibility) - set(registry_metadata))
        invalid_visibility = sorted(
            case_id for case_id, visible in registered_visibility.items() if not isinstance(visible, bool)
        )
        if unknown_visibility or invalid_visibility:
            raise RuntimeError(
                "Invalid registered gallery visibility mapping: "
                f"unknown={unknown_visibility}; non_boolean={invalid_visibility}"
            )
    known_ids = set(existing_metadata) | set(registry_metadata)
    selected = sorted(set(selected_ids) if selected_ids else set(existing_metadata))
    if not selected and not existing_metadata:
        selected = sorted(registry_metadata)
    unknown = sorted(set(selected) - known_ids)
    if unknown:
        raise RuntimeError(f"Unknown public gallery case(s): {', '.join(unknown)}")

    visual_qa_path = root / "showcase" / "visual-qa.json"
    visual_qa = (
        _load_json(visual_qa_path, label="manual visual review register")
        if visual_qa_path.is_file()
        else None
    )
    case_metadata = {case_id: dict(metadata) for case_id, metadata in existing_metadata.items()}
    for case_id in sorted(set(case_metadata) & set(registry_metadata)):
        registered = registry_metadata[case_id]
        case_metadata[case_id]["display_in_gallery"] = bool(registered["display_in_gallery"])
        if not case_metadata[case_id].get("title_zh"):
            case_metadata[case_id]["title_zh"] = str(registered["title_zh"])
        case_metadata[case_id]["title_en"] = str(registered.get("title_en") or case_id)
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
        registered = registry_metadata.get(
            case_id,
            {
                "title_zh": case_id,
                "title_en": case_id,
                "display_in_gallery": True,
            },
        )
        case_metadata.setdefault(
            case_id,
            {
                "title_zh": str(registered["title_zh"]),
                "title_en": str(registered.get("title_en") or case_id),
                "display_in_gallery": bool(registered["display_in_gallery"]),
            },
        )

    records: list[dict[str, object]] = []
    for case_id in sorted(case_metadata):
        destination = output_root / f"{case_id}.png"
        if not destination.is_file():
            raise RuntimeError(f"Missing public PNG: {case_id}")
        metadata = case_metadata[case_id]
        records.append(
            {
                "id": case_id,
                "title_zh": str(metadata["title_zh"]),
                "title_en": str(metadata.get("title_en") or case_id),
                "display_in_gallery": bool(metadata["display_in_gallery"]),
                "sha256": sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )
    display_case_count = sum(bool(record["display_in_gallery"]) for record in records)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "asset_policy": (
                    "programmatically verified and explicitly manually reviewed Origin PNG "
                    "from synthetic teaching data only; local logs, plans, OPJU, PDF and TIF excluded"
                ),
                "case_count": len(records),
                "display_case_count": display_case_count,
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
        f"我从 {len(records)} 个保留验证资产中精选了 {display_case_count} 个案例放在本页，",
        "让第一次接触 EditaPlot 的读者可以先按科研问题和图形类型判断方向，再用自己的数据定制。",
        "同一路线的历史验证图不会重复占版面；热力图目前只展示真实 30×30 高密度版本。",
        "",
        "以下图片均使用本机 Origin/OriginPro 2024b（10.15）生成，并已完成",
        "OPJU/PNG/PDF/TIF、对象反读和人工视觉检查。",
        "全部展示数据均为项目生成的合成教学数据，不代表测量、材料性能或临床结论。",
        "GitHub 源码仓库只保留脱敏 PNG；可编辑项目和其他格式不直接写入源码历史。",
        "",
        "## 第一次选图，可以先看这张表",
        "",
        "| 你想回答的问题 | 优先考虑 | 最少数据结构 |",
        "|---|---|---|",
        "| 比较多条光谱或随条件变化的曲线 | XPS/XRD/PL/UV-Vis/FTIR/NMR 等谱线 | 共用 X + 一列或多列 Y |",
        "| 比较组间水平并展示不确定性 | 柱状图、折线误差图或森林图 | 类别/X + 数值 + 明确的 SD/SEM/CI |",
        "| 展示原始分布和离群形态 | 原始点、箱线、小提琴或 Raincloud | 组别 + 每个原始观测值 |",
        "| 展示规则矩阵 | 热力图或混淆矩阵 | 行标签 + 多列数值矩阵 |",
        "| 展示正权重流量或组成传递 | 桑基图 | Source + Target + Value |",
        "| 比较多个阶段的定向、正负和权重 | 环形有向加权网络 | Panel + Source + Target + Weight；Sign 可选 |",
        "| 展示医学模型证据 | ROC/PR/校准/DCA/Bland-Altman 等 | 预先计算的坐标或统计量 |",
        "",
        '<div align="center">',
    ]
    for record in records:
        if not record["display_in_gallery"]:
            continue
        lines.append(
            f'<img src="../assets/gallery/{record["id"]}.png" alt="{record["title_zh"]}" width="31%" />'
        )
    lines.extend(["</div>", ""])
    docs_path = root / "docs" / "gallery.md"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    english_lines = [
        "# Origin 2024b figures generated and reviewed on a live installation",
        "",
        f"I selected {display_case_count} public examples from {len(records)} retained verification assets.",
        "Use the question and minimum-table guide below to choose a direction before adapting a route",
        "to your own data. Historical verification images do not occupy duplicate gallery slots;",
        "the heatmap section displays only the live Origin-rendered 30×30 dense case.",
        "",
        "Every displayed image was generated with Origin/OriginPro 2024b (10.15) and passed",
        "OPJU/PNG/PDF/TIF generation, object readback, and human visual review. All examples use",
        "project-generated synthetic teaching data and make no measurement, material-performance,",
        "or clinical claim. The public source tree retains only sanitized PNGs.",
        "",
        "## A quick first-choice guide",
        "",
        "| Question | Start with | Minimum table |",
        "|---|---|---|",
        "| Compare spectra or condition-dependent curves | "
        "XPS/XRD/PL/UV-Vis/FTIR/NMR spectral routes | shared X + one or more Y columns |",
        "| Compare group levels with uncertainty | bar, line-error, or forest | "
        "category/X + value + explicit SD/SEM/CI |",
        "| Show raw distributions and outlier shape | raw points, box, violin, or Raincloud | "
        "group + every raw observation |",
        "| Show a regular numeric matrix | heatmap or confusion matrix | "
        "row labels + numeric matrix columns |",
        "| Show positive flow or composition transfer | Sankey | Source + Target + Value |",
        "| Compare directed, signed, weighted relations across panels | circular network | "
        "Panel + Source + Target + Weight; optional Sign |",
        "| Present medical-model evidence | ROC/PR/calibration/DCA/Bland-Altman | "
        "precomputed coordinates or statistics |",
        "",
        '<div align="center">',
    ]
    for record in records:
        if not record["display_in_gallery"]:
            continue
        english_lines.append(
            f'<img src="../assets/gallery/{record["id"]}.png" alt="{record["title_en"]}" width="31%" />'
        )
    english_lines.extend(["</div>", ""])
    (root / "docs" / "gallery.en.md").write_text(
        "\n".join(english_lines),
        encoding="utf-8",
        newline="\n",
    )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    sync_gallery(selected_ids=args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
