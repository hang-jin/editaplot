# XPS C 1s 视觉合同

本模板继承 `origin_sciplot.origin_backend.base_style_contract.FixedOriginStyle` 中老师固定的页面、
图层、字体、线宽、边框和刻度要求。

固定值为：页面 `22.31 cm × 16.82 cm`；图层左 `14%`、上 `2.995%`、
宽 `85.01%`、高 `82.51%`；全部字体 Arial；轴标题 `26 pt` 加粗；
坐标轴数字 `24 pt`；图例 `24 pt` 加粗；图内线条 `5 pt`；边框 `3 pt`。

XPS 专属规则：

- X 轴显示真实 `Binding Energy (eV)`，高结合能在左、低结合能在右。
- 使用 `PlotX = -BindingEnergy` 与 `x.label.divideBy=-1`，不直接依赖 `x.reverse=1`。
- X 轴主刻度间隔 2 eV，两个主刻度之间 1 个次刻度；次刻度只显示短刻度线，不显示数字。
- X 轴首个主刻度固定在 `292 eV`，主刻度标签必须居中在主刻度上；可见主刻度标签固定为 `292, 290, 288, 286, 284, 282`，不得重叠。
- Y 轴保留标题 `Intensity (a.u.)` 和左边框；不显示 Y 轴数字、主刻度或次刻度。不得为了调试或 UI 预览重新打开 `y.ticks`、`y.minorTicks`、`y.showLabels` 或 `y.showlabel`。
- Raw：中性灰空心圆散点，尺寸 7 pt；`set/get -kh=50`，即边框为符号半径的 50%。
- Envelope：红色实线，5 pt。
- Background：灰紫色实线，5 pt。
- Peak components：蓝、绿、粉、橙低饱和颜色，曲线与填充均可在 Origin 中编辑；每个分峰填充在 `Background + Peak` 与 `Background` 之间，并向白色渐变，不能填到零基线或铺满背景下方区域。
- 图例为手工增强图例，Arial 24 pt 粗体，不依赖 Origin 自动图例。
- OPJU、PNG、嵌入字体 PDF、TIFF 均为必需且非空；OPJU 是最终可编辑结果。
- 成功还必须包括页面/图层/轴/字号/关键曲线线宽/Raw 符号对象反读和人工视觉检查。
  图例遮挡不作为失败项，允许在 OPJU 中手动移动。
- `preview.png` 是 UI 中显示的样例图，不是成功证据；但它必须遵守同一视觉合同：Y 轴无数字/主刻度/次刻度，X 轴显示 2 eV 主刻度和 1 eV 次刻度，图例文字使用 `Envelope` 而不是旧名 `Fit total`。

已确认的 X 轴错位事故规则：

- 不得使用手工文本贴数字，也不得使用 tick-indexed string 人工拼标签。
- 不得沿用模板继承的 `x.label.align=2`。该值表示数字居中到主刻度之间，会让 X 轴数字看起来落在次刻度或主刻度间隔上。
- 不得把 `x.firstTick` 留给默认/继承状态后只看 PNG 判断成功。当前稳定值必须反读为 `x.firstTick=-292`，并和 `x.label.align=1`、`x.label.divideBy=-1` 同时成立。
- 之前出现的 `282` 跑到图中间、与 `288` 一类标签重叠，属于继承轴标签格式未清理和标签对齐方式错误的组合症状。有效方案是清理 Origin C Format Tree 的 inherited minor-label table / special ticks，再显式设置主刻度和标签对齐。
