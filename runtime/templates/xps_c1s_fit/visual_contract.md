# XPS C 1s 视觉合同

本模板继承 `origin_sciplot.origin_backend.base_style_contract.FixedOriginStyle` 中老师固定的页面、
图层、字体、线宽、边框和刻度要求。

固定值为：页面 `22.31 cm × 16.82 cm`；图层左 `14%`、上 `2.995%`、
宽 `85.01%`、高 `82.51%`；全部字体 Arial；轴标题 `26 pt` 加粗；
坐标轴数字 `24 pt`；图例 `24 pt` 加粗；图内线条 `5 pt`；边框 `3 pt`。

这些数值是“固定 C 1s”特殊 profile 当前通过实机验收的默认基线，不等于拒绝用户表达外观偏好。
用户可以明确提出精确系列颜色、线宽、填充透明度、画幅比例，以及图例显示/无框/位置；但只有该
字段已在当前 XPS renderer 中实现、完成 Origin 写入与对象反读并通过视觉验收时，才可标记为
采用。尚未验证的字段必须写成保留本 profile 默认值或拒绝，不能因为参考图看起来相似就自动套用。
本特殊固定 profile 的上述画幅仍是默认基线，但用户确认的精确 `page_size_cm` 已可覆盖该默认值；
宽、高各限 `12–40 cm`，通过现有 `graph.PutWidth` / `graph.PutHeight` 物理尺寸 API 写入，并以
Origin 页面对象反读确认。未给出精确尺寸时继续使用默认画幅；参考图只提供建议，必须经过单独确认
和同一反读门禁后才可改变尺寸。

XPS 专属规则：

- X 轴显示真实 `Binding Energy (eV)`，高结合能在左、低结合能在右。
- 使用 `PlotX = -BindingEnergy` 与 `x.label.divideBy=-1`，不直接依赖 `x.reverse=1`。
- X 轴主刻度间隔 2 eV，两个主刻度之间 1 个次刻度；次刻度只显示短刻度线，不显示数字。
- X 轴首个主刻度固定在 `292 eV`，主刻度标签必须居中在主刻度上；可见主刻度标签固定为 `292, 290, 288, 286, 284, 282`，不得重叠。
- Y 轴保留标题 `Intensity (a.u.)` 和左边框；不显示 Y 轴数字、主刻度或次刻度。不得为了调试或 UI 预览重新打开 `y.ticks`、`y.minorTicks`、`y.showLabels` 或 `y.showlabel`。
- Raw 默认：中性灰空心圆散点，尺寸 7 pt；`set/get -kh=50`，即边框为符号半径的 50%。
- Envelope 默认：红色实线，5 pt。
- Background 默认：灰紫色实线，5 pt。
- Peak components 默认：蓝、绿、粉、橙低饱和颜色；用户明确的精确系列颜色只有通过当前
  XPS renderer 与反读门禁后才能替换。曲线与填充均可在 Origin 中编辑；每个分峰填充在
  `Background + Peak` 与 `Background` 之间，并向白色渐变，不能填到零基线或铺满背景下方区域。
- 图例为手工增强图例，Arial 24 pt 粗体，不依赖 Origin 自动图例。
- OPJU、PNG、嵌入字体 PDF、TIFF 均为必需且非空；OPJU 是最终可编辑结果。
- 成功还必须包括页面/图层/轴/字号/关键曲线线宽/Raw 符号对象反读和人工视觉检查。
  图例遮挡不作为失败项，允许在 OPJU 中手动移动。
- `preview.png` 是 UI 中显示的样例图，不是成功证据；但它必须遵守同一视觉合同：Y 轴无数字/主刻度/次刻度，X 轴显示 2 eV 主刻度和 1 eV 次刻度，图例文字使用 `Envelope` 而不是旧名 `Fit total`。
- 用户明确样式请求优先于参考图建议，但两者都不能修改原始数据、列用途、组分身份、结合能轴
  方向、`PlotX=-BindingEnergy` / `x.label.divideBy=-1` 轴实现，或以单块区域
  `set_fill_area(..., type=9)` 与 `-pfm 3` 完成的稳定填充 API。颜色、线宽、透明度、画幅和图例
  必须作为独立能力逐项采用、保留默认或拒绝。

已确认的 X 轴错位事故规则：

- 不得使用手工文本贴数字，也不得使用 tick-indexed string 人工拼标签。
- 不得沿用模板继承的 `x.label.align=2`。该值表示数字居中到主刻度之间，会让 X 轴数字看起来落在次刻度或主刻度间隔上。
- 不得把 `x.firstTick` 留给默认/继承状态后只看 PNG 判断成功。当前稳定值必须反读为 `x.firstTick=-292`，并和 `x.label.align=1`、`x.label.divideBy=-1` 同时成立。
- 之前出现的 `282` 跑到图中间、与 `288` 一类标签重叠，属于继承轴标签格式未清理和标签对齐方式错误的组合症状。有效方案是清理 Origin C Format Tree 的 inherited minor-label table / special ticks，再显式设置主刻度和标签对齐。
