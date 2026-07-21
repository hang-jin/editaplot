# 直方图数据合同

- 输入为原始连续数值，不接收已经汇总的柱高冒充原始分布。
- 使用冻结的 `freedman_diaconis_nice_step_v1` 规则计算等宽 bin；预览与 Origin 使用同一
  begin/end/size，Origin 可编辑统计图对象中的三项属性必须反读一致。
- 不自动叠加正态、KDE 或其他拟合曲线。
