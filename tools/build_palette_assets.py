"""Build original Chinese palette selector assets from the frozen engine catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MODE_ZH = {
    "qualitative": "分类",
    "sequential": "顺序",
    "diverging": "发散",
    "accent": "强调",
}
CHART_ZH = {
    "bar": "柱状图",
    "grouped_bar": "分组柱状图",
    "line": "折线图",
    "scatter": "散点图",
    "box": "箱线图",
    "violin": "小提琴图",
    "spectra": "光谱图",
    "xrd": "XRD",
    "heatmap": "热力图",
    "trend": "趋势图",
    "composition": "组成图",
    "area": "面积图",
    "density": "分布图",
    "distribution": "分布图",
    "sankey": "桑基图",
    "multi_panel": "多面板",
    "medical_comparison": "医学分组比较",
    "decision_curve": "决策曲线",
    "bland_altman": "一致性图",
    "single_family_bar": "同色系柱状图",
    "forest": "森林图",
    "volcano": "火山图",
    "model_comparison": "模型比较",
    "xps": "XPS",
    "annotation": "重点标注",
}
RISK_ZH = {"low": "低", "medium": "中", "high": "高"}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    raise RuntimeError("A Chinese-capable system font is required to build palette assets.")


def _text_color(hex_color: str) -> str:
    r, g, b = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#FFFFFF" if luminance < 145 else "#17212B"


def _gray(hex_color: str) -> str:
    r, g, b = (int(hex_color[index : index + 2], 16) for index in (1, 3, 5))
    value = round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    return f"#{value:02X}{value:02X}{value:02X}"


def _card(palette: dict[str, object], width: int = 1080, height: int = 430) -> Image.Image:
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, width - 3, height - 3), radius=28, outline="#D8DEE6", width=3)
    name_zh = str(palette["name_zh"])
    palette_id = str(palette["palette_id"])
    public = bool(palette["public_default"])
    draw.text((38, 28), name_zh, fill="#17212B", font=_font(36, bold=True))
    draw.text((38, 82), palette_id, fill="#667281", font=_font(23))
    badge = "首发推荐" if public else "高级选项"
    badge_fill = "#E8F4F2" if public else "#F4EEF9"
    badge_text = "#246C63" if public else "#6C4D88"
    badge_box = draw.textbbox((0, 0), badge, font=_font(22, bold=True))
    badge_width = badge_box[2] - badge_box[0] + 36
    draw.rounded_rectangle((width - badge_width - 38, 30, width - 38, 72), radius=18, fill=badge_fill)
    draw.text((width - badge_width - 20, 36), badge, fill=badge_text, font=_font(22, bold=True))

    colors = [str(value) for value in palette["colors"]]
    left, top, gap = 38, 128, 8
    swatch_width = max(72, (width - 76 - gap * (len(colors) - 1)) // len(colors))
    for index, color in enumerate(colors):
        x0 = left + index * (swatch_width + gap)
        x1 = x0 + swatch_width
        draw.rounded_rectangle((x0, top, x1, top + 96), radius=12, fill=color)
        draw.text((x0 + 8, top + 62), color[1:], fill=_text_color(color), font=_font(15, bold=True))
        draw.rounded_rectangle((x0, top + 110, x1, top + 138), radius=7, fill=_gray(color))

    modes = " · ".join(MODE_ZH.get(str(mode), str(mode)) for mode in palette["allowed_modes"])
    max_groups = int(palette["max_qualitative_categories"])
    group_text = f"建议用途：{modes}    分类色安全上限：{max_groups} 组"
    draw.text((38, 288), group_text, fill="#253342", font=_font(23, bold=True))
    charts = [CHART_ZH.get(str(item), str(item)) for item in palette["recommended_charts"]][:5]
    risks = (
        f"推荐：{'、'.join(charts)}    "
        f"色盲风险：{RISK_ZH.get(str(palette['cvd_risk']), palette['cvd_risk'])}    "
        f"灰度风险：{RISK_ZH.get(str(palette['grayscale_risk']), palette['grayscale_risk'])}"
    )
    draw.text((38, 335), risks, fill="#536170", font=_font(20))
    draw.text(
        (38, 380),
        "浅色只用于填充/背景；组数较多时必须叠加点型、线型或纹理。",
        fill="#7A4D35",
        font=_font(19),
    )
    return image


def _selector(palettes: list[dict[str, object]], title: str, subtitle: str) -> Image.Image:
    columns = 2
    card_width, card_height, gap = 1080, 430, 36
    rows = (len(palettes) + columns - 1) // columns
    width = columns * card_width + (columns + 1) * gap
    header = 250
    height = header + rows * card_height + (rows + 1) * gap + 95
    image = Image.new("RGB", (width, height), "#F5F7FA")
    draw = ImageDraw.Draw(image)
    draw.text((gap, 38), title, fill="#13273A", font=_font(54, bold=True))
    draw.text((gap, 112), subtitle, fill="#506273", font=_font(26))
    draw.text(
        (gap, 164),
        "回复稳定 palette_id 即可冻结配色；最终仍需按数据组数、色盲和灰度输出复核。",
        fill="#6D4E3C",
        font=_font(23),
    )
    for index, palette in enumerate(palettes):
        row, column = divmod(index, columns)
        x = gap + column * (card_width + gap)
        y = header + gap + row * (card_height + gap)
        image.paste(_card(palette, card_width, card_height), (x, y))
    footer_y = height - 72
    draw.text(
        (gap, footer_y),
        "EditaPlot · 原创色卡资产 · 参考图原件、期刊封面与水印均未收录",
        fill="#697887",
        font=_font(20),
    )
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-home", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    engine = Path(args.engine_home).resolve()
    sys.path.insert(0, str(engine / "src"))
    from origin_sciplot.palette_catalog import list_palettes, palette_to_dict

    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    palettes = [palette_to_dict(item) for item in list_palettes()]
    public = [item for item in palettes if item["public_default"]]
    (output / "palette-catalog.json").write_text(
        json.dumps({"schema_version": "1.0", "palettes": palettes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    _selector(
        public,
        "科研配色选择 · 首发推荐 8 套",
        "面向论文折线、柱状、分布、光谱、组成与多面板图；强色只服务于核心证据。",
    ).save(output / "palette-selector-public.zh-CN.png", dpi=(220, 220))
    _selector(
        palettes,
        "科研配色选择 · 完整目录 10 套",
        "含 8 套首发推荐与 2 套高级受限选项；不是任何期刊的官方配色。",
    ).save(output / "palette-selector-all.zh-CN.png", dpi=(220, 220))
    cards = output / "cards"
    cards.mkdir(exist_ok=True)
    for item in palettes:
        _card(item).save(cards / f"{item['palette_id']}.png", dpi=(220, 220))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
