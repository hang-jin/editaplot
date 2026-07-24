# XRD 数据合同

## 普通扫描

- 一列 `2Theta/TwoTheta/2θ/衍射角`，加一个或多个强度系列。
- 单系列保留原始强度；多系列只在 Origin 工作簿 helper 列中按最大绝对强度归一化并垂直错开。
- 不自动寻峰、物相匹配，也不添加 Miller 指数、材料参考峰或来源表中没有的谱线。

## Rietveld 精修

支持通用精修列名，以及 GSAS-II 官方 Powder CSV / Publication CSV：

- 必需：X/2θ、实测强度 `Obs/y_obs`、计算强度 `Calc/y_calc`。
- 可选绘图元素：背景 `Bkg/y_bkg`、文件中已提供的 `Diff`、具有明确物相身份的稀疏 Phase 刻线列。
- 只作辅助或保留、不作为强度曲线：`weight`、`Q`、`Used`、`tick-pos`、`diff/sigma`、`Axis-limits` 及已确认的其他控制列。
- Publication CSV 的 `Diff` 已包含上游显示位置，必须按源值直接绘制，不得再次偏移。
- 缺少背景、差值或物相刻线时明确报告“文件未提供”，不得补造。
- 未识别数值列和通用精修格式必须先由用户确认列用途。

所有源列和源文件字节均保持不变。允许的 helper 只能创建在 Origin 工作簿中，并在语义合同和验证报告中记录来源与用途。
