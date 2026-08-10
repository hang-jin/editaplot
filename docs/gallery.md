# Origin 2024b 实机生成并复核的图形示例

我从 47 个保留验证资产中精选了 45 个案例放在本页，
让第一次接触 EditaPlot 的读者可以先按科研问题和图形类型判断方向，再用自己的数据定制。
同一路线的历史验证图不会重复占版面；热力图目前只展示真实 30×30 高密度版本。

以下图片均使用本机 Origin/OriginPro 2024b（10.15）生成，并已完成
OPJU/PNG/PDF/TIF、对象反读和人工视觉检查。
全部展示数据均为项目生成的合成教学数据，不代表测量、材料性能或临床结论。
GitHub 源码仓库只保留脱敏 PNG；可编辑项目和其他格式不直接写入源码历史。

## 第一次选图，可以先看这张表

| 你想回答的问题 | 优先考虑 | 最少数据结构 |
|---|---|---|
| 比较多条光谱或随条件变化的曲线 | XPS/XRD/PL/UV-Vis/FTIR/NMR 等谱线 | 共用 X + 一列或多列 Y |
| 比较组间水平并展示不确定性 | 柱状图、折线误差图或森林图 | 类别/X + 数值 + 明确的 SD/SEM/CI |
| 展示原始分布和离群形态 | 原始点、箱线、小提琴或 Raincloud | 组别 + 每个原始观测值 |
| 展示规则矩阵 | 热力图或混淆矩阵 | 行标签 + 多列数值矩阵 |
| 展示正权重流量或组成传递 | 桑基图 | Source + Target + Value |
| 比较多个阶段的定向、正负和权重 | 环形有向加权网络 | Panel + Source + Target + Weight；Sign 可选 |
| 展示医学模型证据 | ROC/PR/校准/DCA/Bland-Altman 等 | 预先计算的坐标或统计量 |

<div align="center">
<img src="../assets/gallery/bar-error-groups.png" alt="分组柱状图与 SD 误差棒" width="31%" />
<img src="../assets/gallery/bubble-indexed-size.png" alt="大小编码气泡关系图" width="31%" />
<img src="../assets/gallery/circular-network.png" alt="多阶段环形有向加权网络图" width="31%" />
<img src="../assets/gallery/cv-cycles.png" alt="CV 循环伏安曲线" width="31%" />
<img src="../assets/gallery/density-ridgeline3d.png" alt="三维双密度曲线与基线焦点" width="31%" />
<img src="../assets/gallery/diverging-effects.png" alt="正负效应发散条形图" width="31%" />
<img src="../assets/gallery/dsc-multi.png" alt="DSC 多样品热流曲线" width="31%" />
<img src="../assets/gallery/eis-nyquist.png" alt="EIS Nyquist 阻抗图" width="31%" />
<img src="../assets/gallery/forest-intervals.png" alt="效应量森林图" width="31%" />
<img src="../assets/gallery/ftir-temperature-series.png" alt="FTIR 温度序列光谱" width="31%" />
<img src="../assets/gallery/heatmap-dense-30x30.png" alt="30×30 高密度热力图" width="31%" />
<img src="../assets/gallery/histogram-frozen-bins.png" alt="固定分箱直方图" width="31%" />
<img src="../assets/gallery/horizontal-long-labels.png" alt="长标签横向条形图" width="31%" />
<img src="../assets/gallery/line-error.png" alt="带 SD / SEM 的趋势图" width="31%" />
<img src="../assets/gallery/lsv-multi.png" alt="LSV 线性扫描曲线" width="31%" />
<img src="../assets/gallery/medical-agreement.png" alt="Bland–Altman 一致性图" width="31%" />
<img src="../assets/gallery/medical-calibration.png" alt="医学模型校准曲线" width="31%" />
<img src="../assets/gallery/medical-confusion.png" alt="医学分类混淆矩阵" width="31%" />
<img src="../assets/gallery/medical-decision.png" alt="医学决策曲线 DCA" width="31%" />
<img src="../assets/gallery/medical-grouped-box.png" alt="医学分组箱线图与原始点" width="31%" />
<img src="../assets/gallery/medical-longitudinal.png" alt="配对纵向医学轨迹" width="31%" />
<img src="../assets/gallery/medical-pr.png" alt="医学模型 PR 曲线" width="31%" />
<img src="../assets/gallery/medical-raincloud.png" alt="医学 Raincloud 原始分布图" width="31%" />
<img src="../assets/gallery/medical-roc.png" alt="医学模型 ROC 曲线" width="31%" />
<img src="../assets/gallery/medical-shap.png" alt="复合 SHAP 特征贡献图" width="31%" />
<img src="../assets/gallery/nmr-comparison.png" alt="19F NMR 光谱对比" width="31%" />
<img src="../assets/gallery/percent-composition.png" alt="百分比堆叠组成图" width="31%" />
<img src="../assets/gallery/pie-five-parts.png" alt="少类别饼图" width="31%" />
<img src="../assets/gallery/pl-steady-state.png" alt="稳态 PL 发射光谱" width="31%" />
<img src="../assets/gallery/pl-temperature-series.png" alt="PL 温度序列光谱" width="31%" />
<img src="../assets/gallery/pl-trpl.png" alt="PL / TRPL 光致发光" width="31%" />
<img src="../assets/gallery/radar-multimetric.png" alt="多指标雷达图" width="31%" />
<img src="../assets/gallery/raw-observations.png" alt="原始观测点与中位数" width="31%" />
<img src="../assets/gallery/sankey-flow.png" alt="多阶段桑基流向图" width="31%" />
<img src="../assets/gallery/scatter-dense.png" alt="多组密集散点图" width="31%" />
<img src="../assets/gallery/stacked-composition.png" alt="绝对值堆叠组成图" width="31%" />
<img src="../assets/gallery/trajectory3d.png" alt="三维多条件 Nyquist 轨迹" width="31%" />
<img src="../assets/gallery/trend-progression.png" alt="多系列进展折线图" width="31%" />
<img src="../assets/gallery/uv-vis-multi.png" alt="UV-Vis 多样品吸收光谱" width="31%" />
<img src="../assets/gallery/uv-vis-tauc.png" alt="UV–Vis 与可选 Tauc 插图" width="31%" />
<img src="../assets/gallery/violin-distributions.png" alt="小提琴分布对比" width="31%" />
<img src="../assets/gallery/xas-profiles.png" alt="XAS 吸收谱对比" width="31%" />
<img src="../assets/gallery/xps-comparison.png" alt="XPS 多样品谱线对比" width="31%" />
<img src="../assets/gallery/xps-fit.png" alt="XPS 峰拟合" width="31%" />
<img src="../assets/gallery/xrd-multi.png" alt="XRD 多谱线对比" width="31%" />
</div>
