# 科研配色选择合同

配色是绘图合同的一部分，不是渲染后的装饰。先运行：

```powershell
python scripts/editaplot.py palettes --engine-home <root>
```

向中文用户展示 `assets/palettes/palette-selector-public.zh-CN.png`，让用户回复稳定的
`palette_id`。需要完整目录时才运行 `palettes --all` 并展示
`assets/palettes/palette-selector-all.zh-CN.png`。

## 首发推荐

| palette_id | 中文名 | 主要用途 | 分类安全上限 |
|---|---|---|---:|
| `blue_coral` | 远海蓝珊瑚 | 分组比较、折线、箱线 | 5 |
| `ocean_coral` | 深海珊瑚 | 通用科研、医学比较 | 5 |
| `plum_rose` | 梅紫玫瑰 | 顺序状态、同色系分布 | 4 |
| `navy_cyan_gold` | 海军蓝青金 | 光谱、XRD、高对比折线 | 5 |
| `navy_ember` | 藏蓝余烬 | 材料、冷暖对照 | 5 |
| `deep_sea_gold` | 深海鎏金 | 光谱、面积、三维透明层 | 4 |
| `sky_terra` | 天青陶土 | 3–5 组工程/医学比较 | 5 |
| `amber_lavender` | 琥珀薰衣草 | 暖色顺序、暖冷对照 | 4 |

高级受限项：`forest_amber` 只用于有序数据；`violet_lime` 的色盲与灰度风险高，必须同时
使用点型、线型、纹理或直接标签。

## 冻结与拒绝规则

- `plan --palette-id <id>` 将 palette ID、精确 HEX、允许模式、分类上限和风险写入计划摘要与
  plan digest；worker 必须从同一计划重建配色。
- 用户参考图只用于内部抽取明确列出的 HEX。不要复制、展示或分发带期刊封面、品牌或水印的原图。
- 不要称这些色组为 Nature、Science 或任何期刊的“官方配色”；使用
  `publication-informed scientific palette` / `科研绘图参考配色`。
- XPS、正负效应、热力图、诊断参考线、混淆矩阵等语义色合同默认不可覆盖。
- 超过 palette 的分类安全上限时，换回模板已验证默认色，或在已经验证的 renderer 中增加可独立
  识别的点型、线型或纹理；不能只循环相近颜色。
- 浅色只作面积填充和背景。轴、标题、数字、注释必须使用 catalog 中的深色 `neutral_text`
  或模板默认深色。
- 每次由 Origin/OriginPro 生成的输出都要检查彩色、灰度、图例语义、组别一致性和打印可读性。
