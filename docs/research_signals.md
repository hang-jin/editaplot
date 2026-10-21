# 我怎样用 EditaPlot 展示荧光与脑电相关数据

这部分我正在逐步扩充。现在已能使用荧光寿命相量和时间–频率物理矩阵两条独立路线；
其余研究信号模板还在开发、验证中，我不会把候选清单写成已经完成的功能。

## 时间–频率图：先有时频表，再来画图

我提供的[教学数据](../examples/gallery/time_frequency.csv)有81×121个单元，共9801行。
它完全由我拟定，不是某位受试者的脑电，也不是任何算法性能结果。

| Time (s) | Frequency (Hz) | Power (dB) |
|---|---|---|
| 每格的时间坐标 | 每格的频率坐标 | 上游提供的数值 |

你可以直接告诉 Codex：

> 使用 EditaPlot，为这个已经处理好的时频长表绘图。时间单位是s，频率单位是Hz，数值是上游给出的dB；请保留全部单元和原值，不做FFT、滤波或基线处理。先告诉我识别的列和绘图元素，确认后再绘制。

中文列名也可以，例如“时间 (ms)、频率 (Hz)、功率 (dB)”。单位写在括号或方括号里，
我不会自行把毫秒改成秒。两个坐标需要等距、单调，而且所有时间×频率组合都要齐全。
缺格、重复坐标或不等距时，程序会停下来说明原因，不偷偷补值或插值。递增和递减方向均保留。

数值用连续色阶展示，色条在数据区外，坐标轴和字号独立反读。负dB只是提供的数值，
我不会自动把它解读为“相对基线下降”，也不会加事件箭头、显著性区域或逐格数字。
正式输出仍是可以编辑的OPJU，以及PNG、PDF、TIF。源CSV不修改。

### 我的设计参考与边界

我参考了 Nature Communications 的[Time-frequency super-resolution with superlets](https://www.nature.com/articles/s41467-020-20539-9)
所用的时间–频率表达方式，独立设计了教学数据和Origin实现。这里没有复用论文图片或实验数值，
也没有在Skill里实现superlet。当前完整等距网格合同不等于支持论文里的所有时频分析流程。
矩阵实现使用Origin官方的[Matrix Heatmap示例](https://docs.originlab.com/python/examples/graphing/)
和[Layer.CMap接口](https://docs.originlab.com/labtalk/ref/layer-cmap-obj/)。

## 荧光寿命相量：坐标请由上游提供

我接受G、S、Group三列，例如[相量教学表](../examples/gallery/flim_phasor.csv)。
模板保留全部观测，包括参考半圆外的点，G与S使用相同物理比例。
参考半圆只是数学几何，不是拟合结果；我不会据此自动推算寿命、组分比例或做聚类。

## English summary

I provide two verified research-signal routes here: supplied FLIM G/S coordinates with explicit
groups, and complete uniform time–frequency cells with units in their headers. The examples are
my own synthetic teaching data, not reproduced measurements or algorithm results. The latter
uses native editable matrix marks, numeric physical axes and a detached sequential color scale.
It preserves every cell and either source-coordinate direction. It does not compute FFT, STFT,
wavelets, interpolation, baseline correction or dB conversion. Raw EEG needs upstream processing.
Both routes retain source data and require real OPJU/PNG/PDF/TIF, object readback and visual QA.
