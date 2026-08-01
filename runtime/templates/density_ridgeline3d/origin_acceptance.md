# Origin route acceptance — verified 2026-08-01

`density_ridgeline3d` 已在隔离的 EditaPlot-owned Origin 2024b（10.15）、
`originpro 1.1.15` 实例中完成对象级、产物级和人工视觉验收。实现只使用官方
`plotxyz` / `glTraject`（plot 240）路线；不使用 Waterfall、`-pf` / `-pfm 4`、填充或未经验证的
More Colors 参数。

## 探针历史

三轮探针均保存在仓库忽略目录 `artifacts/density-ridgeline3d-api-lab/`，失败轮次仅用于记录边界，
不作为通过证据。

1. `output/`：首次直接绘图在视觉上生成了实线、虚线、焦点与标签，但严格验证失败。原因是
   LabTalk 临时变量名过长导致部分对象反读为 NaN，同时 PDF 字体嵌入检查失败，图例位置也超出页面。
2. `output-v2/`：改用官方 `-so` 访问 3D 原始 plot、短变量名、显式 Arial 与页内图例后，大多数反读
   通过；焦点 `-k 20` 写入后反读仍为 `0`，因此该轮失败，并证明焦点 shape 不能作为稳定契约。
3. `output-v3/`：移除焦点 shape 的写入与断言，仅验证可见 3D 基线标记的连接、大小、颜色、
   Z=0 数据绑定、X 值标签和无下垂线。严格程序验证在 15.3 秒内通过，随后 PNG 人工检查通过。

第三轮探针的四个核心产物均非空：

| 产物 | SHA-256 |
| --- | --- |
| `output-v3/result.opju` | `825aec6c62ab58b1e3ad51952e3612de650548917abe072aa73ca19ee5ec398f` |
| `output-v3/result.png` | `7b37e2a27b9ab46d6382aadcb22e4295be143b4681762a1b81e011b9a106a859` |
| `output-v3/result.pdf` | `8aa84bc8757a5ead9e461eea18f362a3277754427809db4a903220d901f58dbb` |
| `output-v3/result.tif` | `4596a6db68495e730d29f3dba3be32e8404d60d4b480dfc30c8496cbc49e9fe4` |

## 四组正式验收

正式证据位于 `artifacts/density-ridgeline3d-formal-origin-20260801/`，输入为
`runtime/templates/density_ridgeline3d/example_standard.csv`。完整流程显式确认唯一允许的派生语义
`derived_density_focus_baseline_zero`，源文件 SHA-256
`47adc68fa01caf5cae6cbd6fd45e502a04edba93c6d3b44aa7d8b1999282c40f` 在渲染前后不变。

对象级反读结果：

- 4 个有序条件生成 12 个 plot 和 36 个 helper 列：每组一条实线、一条同色虚线和一个基线焦点；
- 曲线 `connection=1`，线型分别为 `0` / `1`，物理线宽 `1200`，`symbol=0`，全部下垂线关闭；
- 焦点 `connection=0`、`size=9 pt`、Z 数据严格为 0、标签模式为 X 值，Arial 字体码 `71`、
  `15 pt`，全部下垂线关闭；
- 3D layer 反读为 `is3D=1`、`is3DGL=1`、`coortype=16`、`maxpts=0`；相机为
  `azimuth=310.0`、`inclination=15.8`、`roll=0.2`；
- X/Y/Z 轴标题与刻度均为 Arial；页尺寸约 `28.3972 × 20.50288 cm`，layer 位于页面内；
- 页附着无框语义图例的文本、Arial `18 pt`、`frame=0`、`showframe=0` 与页内位置均精确反读；
- 验证报告确认 `waterfall_used=false`、`fill_used=false`、未修改源数据。

正式四产物及其验收时大小、SHA-256：

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| `result.opju` | 69,710 | `c4055eda8306554b681a7a9eda2356fb502833b521b56ed63bdb39ac3df5e59c` |
| `result.png` | 156,687 | `222be3ac4933aead43c13f7cc164a46a38819a1bd61a94ba48da69d662139440` |
| `result.pdf` | 764,510 | `3abdaebd0bc1a1198a1272730e8f14f72ff42f671c51fcf66d49d3963be406dd` |
| `result.tif` | 194,728 | `8c8735f31448d6396fa6d0e02e5b493504b538d8c2c99dfc500282843c20650a` |

人工 PNG QA 与上述 PNG 哈希绑定，记录在 `visual-review.json`：4 组同色实/虚线、4 个基线焦点及
`0.49` / `0.52` / `0.55` / `0.58` 标签、三轴和页内无框图例均清晰；没有裁切、曲线符号、
下垂线、填充、Waterfall 或意外对象。程序化 helper 回归另覆盖 2 组和 6 组边界。

## Origin 数据绑定门禁复验

2026-08-01 进一步补齐了“图确实绑定到哪个工作表/哪一列”的对象门禁。实现按 Origin 官方
Graph Data Range 路线，对每个 plot 分别执行 `range -wx`、`range -wy`、`range -wz`，再用
`NameOf(range)$` 将实际数据集和 helper mapping 指定列解析为同一种内部数据集名；有效点数同时
由 `count(range, 1)` 与 `count(plotdata(plot_index, X/Y/Z), 1)` 两条反读得到。原始 range 文本、
规范数据集名、helper 内部列名、列号、工作表 Long Name / Unit / Comments 和三类点数均写入
`origin_data_binding_state`，任一错列、空反读或点数差异都会使渲染失败。

隔离语法探针位于
`artifacts/density-ridgeline3d-binding-lab-20260801/output/binding-probe.opju`：一条 7 点曲线和
一个 1 点焦点的 X/Y/Z 共 6 项绑定全部通过。修改后的正式 renderer 复验位于
`artifacts/density-ridgeline3d-binding-gate-origin-20260801-1605/`，运行 11.9 秒，结果为：

- 12/12 个 plot、36/36 个 X/Y/Z 组件的实际 Origin 数据集与冻结 helper 列完全一致；
- 8 条密度曲线的 X/Y/Z 均为 31 个有效点，4 个焦点的 X/Y/Z 均为 1 个有效点；
- X/Y/Z 的 `showAxes/showLabels/showlabel/ticks/minorTicks` 均精确为 `3/3/1/10/1`；
- 相机被显式写入并反读为 `azimuth=310.0`、`inclination=15.8`、`roll=0.2`，同时通过允许范围与
  目标容差断言；`is3D=1`、`is3DGL=1`、`coortype=16`、`maxpts=0`；
- `verify` 返回 `programmatic_pass=true`，源 SHA-256 在渲染前后保持
  `fc63e0e391b4c220282c30e3ad3bbbecee2cb508b01720e08fd87ea75bcb411f`；
- PNG 人工视觉检查通过，记录在同目录 `visual-review.json`，并绑定 PNG SHA-256
  `f136147599d56924c23072dfb306dbd848776aa0393bb6a8fa709302894e8d62`。

复验四产物：

| 产物 | 字节 | SHA-256 |
| --- | ---: | --- |
| `result.opju` | 72,266 | `c791d4f85c27ce837e3961076d3d8532af446b730b7eee15dc2eb1a633eeb873` |
| `result.png` | 164,155 | `f136147599d56924c23072dfb306dbd848776aa0393bb6a8fa709302894e8d62` |
| `result.pdf` | 778,542 | `a4792ec3e18d79c979756fca117fb945b5adbbe9dcb99dee5d4330eda68a42bd` |
| `result.tif` | 207,891 | `77ca5074731453fbdb5c46ec6e135629bcfa028628f9016551dccfd0a856474b` |

## 契约边界

焦点 marker 的具体 shape 既不写入也不反读断言，不能宣称为已验证属性；Origin 当前显示的默认
shape 不属于兼容性承诺。已验证的焦点契约仅为：单点、`connection=0`、`size=9 pt`、固定颜色、
源 focal X、派生 Z=0、X 值标签以及所有下垂线关闭。
