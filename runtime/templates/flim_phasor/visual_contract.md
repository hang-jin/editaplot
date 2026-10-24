# FLIM 相量图视觉合同 / FLIM phasor visual contract

## 布局与视觉语义

- 白底、Arial；横纵轴标题、刻度和图例使用同一字体体系。字号和线宽按实际
  导出物理尺寸换算，不将 Origin 内部单位直接当作点数。
- `G` 为横坐标，`S` 为纵坐标，均为数值轴。保留全部观测和参考半圆，
  不为美观裁去圈外点。参考灰线弱于观测点，不使用面积填充暗示有效区域。
- 每组使用可辨识颜色和原生空心散点；颜色表示用户给定的组，不表示推算寿命。
  组序保持源表首次出现顺序。图例保留用户组名，包含独立数学参考线条目，
  不混入并不存在的荧光团或科学结论。
- 图例外置、无边框，为长标签和多个组预留空间。页面和图层尺寸根据数据
  范围、组数和标签宽度调整，不锁死为其他模板的固定画幅。
- **G 与 S 的每单位实际物理长度必须相等，相对差不超过 0.3%。**
  比较图层实际宽高除以对应坐标跨度，而不是只比较像素尺寸或轴范围。
  允许横纵范围不同；禁止把参考半圆拉成椭圆。
- 不默认增加寿命标签、阈值、聚类边界、置信椭圆、箭头或显著性标注。
  用户后续需要其他视觉表达时，应明确数据来源并重新确认绘图计划。

## 原生对象与验收

数学参考用 Origin 原生线图，观测用原生散点；G/S、组信息、数学参考及绘图
helper 表均保留在可编辑 OPJU 中，原始 CSV 不变。必须逐值反读组内坐标、
数量和源行对应关系，数学参考的 181 点不计入实验点数。

在图例和标题刷新之后恢复冻结坐标，再检查轴范围、每单位物理长度、颜色、
空心符号、字号和线宽。完成原生 OPJU、PNG/PDF/TIF 导出，人工视觉检查
圈外点、图例、坐标和完整半圆，并重开工程验证后，才能宣称正式通过。
Python 预览和隔离构建器成功不替代正式 CLI 验收。

当前原生基线为 Origin 2024b（10.15）；其他版本仍按主机能力和完整产物决定是否通过。

English summary: use a white Arial figure with native grouped hollow scatter,
a restrained mathematical semicircle and a frameless external legend. Preserve
equal physical G/S units within 0.3%, adapt the page to data and labels, and verify
all source coordinates and editable Origin outputs before release.
