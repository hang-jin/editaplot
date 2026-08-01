# 三维双轮廓密度曲线与基线焦点 mixed-wide 数据合同

## 一行代表什么

源表必须是 mixed-wide 六角色表。每一行表示某一真实条件在一个横轴位置上的两种**上游预计算密度值**：

- `Condition ID`：稳定的条件名称或编号；
- `Condition Position`：三维条件轴，必须为有限数值，表头必须同时写明真实实验含义与单位；
- `Density X`：密度曲线横轴，必须为有限数值，表头必须同时写明科学含义与单位；
- `Solid Density`：上游提供的非负有限实线密度；表头必须明确包含 `Density/密度` 与单位；
- `Dashed Density`：上游提供的非负有限虚线密度；表头必须明确包含 `Density/密度` 与单位；
- `Focal X`：用户提供的基线定位横坐标；每个 `Condition ID` 必须恰好一行非空，其余行留空。

表头示例是 `Response Score (a.u.)` 与 `Follow-up Time (month)`。`X (unit)`、`Condition`、
`Index`、`序号` 等不能证明坐标的科学含义，不满足自动识别合同。`Year`、`年份`、`年度` 可作为
有明确日历语义的条件轴，单位按 `year` 处理，不要求再写括号单位。

两列密度必须使用同一个规范化单位，例如同时为 `Solid Density (a.u.)` 与
`Dashed Density (a.u.)`。也可以同时明确写成 `dimensionless/unitless/无量纲`；不得一列有单位、
另一列缺失，或一列为 `a.u.`、另一列为 `counts`。冻结后的 Z 轴标题是
`Density (<规范化共同单位>)`，两列明确无量纲时为 `Density (dimensionless)`。

## 分组与顺序

- 支持 2–6 个不同的 `Condition ID`。每个 ID 必须只对应一个 `Condition Position`，每个位置也只能对应一个 ID。
- 六个冻结角色键是 `condition_id`、`condition_position`、`density_x`、`density_solid`、
  `density_dashed`、`focal_x`；人类可读表头可以使用合同列出的中英文别名。
- 每个条件至少 5 行；同一行必须同时提供完整、非负、同单位的 `Solid Density` 和 `Dashed Density`，不接受拆成长表的 Profile/Line Role 两列。
- `Density X` 在每个条件中必须按源表顺序严格单调，而且所有条件的递增/递减方向必须一致；软件保留这个顺序，不替用户排序。
- 各 `Condition ID` 按其在源表中第一次出现的顺序排列；对应的 `Condition Position` 必须严格递增。
- `Focal X` 每组必须恰好一个非空有限值，并落在对应条件的 `Density X` 范围内。渲染时只在 `(Focal X, Condition Position, 0)`
  放置一个可编辑焦点符号；它是基线定位点，不自动代表峰、交点、分界点、最优点或统计阈值。

## 明确不做的计算

EditaPlot 不从原始观测计算 KDE/概率密度，不平滑、不插值、不归一化，也不计算峰值、交点、
阈值或 `Focal X`。如用户只有原始样本，必须先在上游完成并确认这些科学计算，再上传符合本合同
的工作副本。原文件保持只读；只允许在可编辑 Origin 工作簿中建立绘图所需的 helper columns。

若六个角色不唯一、任一坐标或密度列缺少语义/单位、两列密度单位不一致、Condition ID 与 Position 对应冲突、焦点数目不为每组一个，或焦点语义不明确，自动
选择必须停止并请用户确认，不能按列位置猜测。`Threshold X/阈值点`、峰值、交点等列名不作为
高置信度 `Focal X` 同义词；即使数值布局相似，也必须先由用户确认它是否就是要显示的基线定位点。
