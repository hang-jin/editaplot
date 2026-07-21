"""Copy only reviewed PNG showcase assets into the GitHub-safe public gallery."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "showcase" / "gallery"
OUTPUT = ROOT / "assets" / "gallery"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "gallery-manifest.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    titles = {item["id"]: item["title_zh"] for item in existing["cases"]}
    selected = sorted(args.only or titles)
    unknown = sorted(set(selected) - set(titles))
    if unknown:
        raise RuntimeError(f"Unknown public gallery case(s): {', '.join(unknown)}")

    for case_id in selected:
        source = SOURCE / case_id / "origin-output" / "result.png"
        if not source.is_file():
            raise RuntimeError(f"Missing reviewed Origin PNG: {case_id}")
        shutil.copy2(source, OUTPUT / f"{case_id}.png")

    records = []
    for case_id in sorted(titles):
        destination = OUTPUT / f"{case_id}.png"
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
    (OUTPUT / "gallery-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "asset_policy": (
                    "reviewed Origin PNG from synthetic teaching data only; local logs, plans, "
                    "OPJU, PDF and TIF excluded"
                ),
                "case_count": len(records),
                "cases": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    lines = [
        "# Origin 2024b 实机生成并复核的图形示例",
        "",
        "以下图片均使用用户本机合法安装的 Origin/OriginPro 2024b（10.15）生成，并已完成",
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
    (ROOT / "docs" / "gallery.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
