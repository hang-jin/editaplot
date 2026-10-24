# FLIM 相量图数据合同 / FLIM phasor data contract

## 当前状态

原生图构建器已在 Origin 2024b（10.15）完成四格式、逐值反读、视觉和工程重开验证。
正式运行仍须检查当前主机能力并确认本次数据与数学参考；模板可用不等于任意输入都已通过验收。

## 输入与映射

使用上游已计算的长表，每行一个观测：

| 标准列 | 角色 | 含义 |
| --- | --- | --- |
| `G` | `x` | 实部相量坐标，有限实数 |
| `S` | `series` | 虚部相量坐标，有限实数 |
| `Group` | `category` | 用户明确给出的组名，不可为空 |

可将 `相量G`、`相量S`、`分组` 或 `组别` 确认为对应源列；不要求用户重命名
原文件。必须确认 G/S 来自适合比较的上游处理，并明确两列方向，不从文件名或
点云位置推断实验条件。重复列名、缺失/无穷坐标或含糊的组标签应先提示处理，
不静默丢行。

支持 1–8 个显式组，组内观测数可以不同；保留组首次出现顺序和组内源行顺序。
保留重复点。额外列在源表中保留，先确认其用途，未确认的列不映射到颜色、大小、
坐标或其他图形元素。组名和 G/S 数值不被教学示例替换。

## 数学参考与审批

参考为圆心 `(0.5, 0)`、半径 `0.5` 的上半圆：
`G_ref = 0.5 + 0.5*cos(theta)`，`S_ref = 0.5*sin(theta)`，
`theta` 从 0 到 π，包含端点共 181 个等角度点。它是独立的
`mathematical_reference_not_experimental_data`，不是新造实验观测。
绘图前将生成该参考线作为派生项明确声明并取得审批；参考数据只进入 Origin
helper 工作表，不写回用户原始文件，也不计入实验样本数。

全部 G/S 点原值保留，包括半圆外和负 S 的点；圈外计数仅作为提示，不能用作
自动筛选、质量评级或删除理由。坐标范围覆盖所有观测及完整参考半圆。

本模板不从原始衰减曲线计算 G/S，不推算荧光寿命、进行仪器响应校正、拟合、
聚类或估计混合比例；这些属于另行确认的上游分析。

## 示例来源

`example_standard.csv` 和 `examples/gallery/flim_phasor.csv` 是同一份独立生成的
synthetic 教学数据：`Demo A/B/C` 三组各 180 点，共 540 点。
它们来自 `tools/generate_research_data.py` 中的 `flim_phasor_data()` 固定种子
函数。组名不代表真实荧光团，点云位置不代表测得或拟合的寿命。
`data_template.csv` 只有 `G,S,Group` 标题，供用户整理自己的数据。

English summary: display upstream-calculated G/S coordinates without changing the
source table. Explicit groups control membership only. The approved 181-point
universal semicircle is mathematical reference geometry, not measured data.
Keep outside points; do not infer lifetimes, fit, cluster, or estimate mixtures.
