# 我怎样用 EditaPlot 展示荧光与脑电相关数据

这部分我正在逐步扩充。现在已能使用荧光寿命相量、时间–频率物理矩阵和多通道信号三条独立路线；
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
标题比较长时，画幅会按文字的实际物理尺寸扩展，不靠缩小字号塞进去；µ、²等单位符号原样保留。
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

## 多通道信号：同一个幅度尺，逐条看清楚

我提供了[八通道教学表](../examples/gallery/signal_stack.csv)，一共8008个观测。它有随时间变化的
活动和自拟波动，仍然是合成数据，不是实际EEG记录。数据结构是 `Time (s)、Channel、Amplitude (uV)`；
荧光轨迹也可以用 `Time (s)、ROI、Intensity (a.u.)`。

> 使用EditaPlot绘制这个多通道信号表。请保留全部观测和通道顺序，使用共同幅度单位，只做明确说明的纵向显示偏移，通道名和幅度尺放到图外。请先让我确认列的含义与显示偏移，不要滤波或逐通道归一化。

我保留原始时间范围，支持1–16个明确通道，每个通道至少两个点且时间已递增。不同通道的
采样时间可以不同。名字长、通道多时，页面会扩展；“01”这样的文本编号也会保留前导零。
右侧标尺代表一个幅度单位长度，不是误差棒。源文件保持不变，Origin内部另存可编辑显示数据。

我参考了[这项Nature Neuroscience神经信号研究](https://www.nature.com/articles/s41593-023-01260-4)
中的多通道时间轴与幅度表达方式，使用独立拟定的示例。模板不会进行设备文件解码、滤波、
去伪迹、重参考、插值或事件检测。

## English summary

I provide three verified research-signal routes here: supplied FLIM G/S coordinates with explicit
groups, complete uniform time–frequency cells, and multichannel waveform tables. Units are explicit. The examples are
my own synthetic teaching data, not reproduced measurements or algorithm results. The latter
uses native editable matrix marks, numeric physical axes and a detached sequential color scale.
It preserves every cell and either source-coordinate direction. It does not compute FFT, STFT,
wavelets, interpolation, baseline correction or dB conversion. Raw EEG needs upstream processing.
The signal stack preserves every sample and channel name, uses approved additive display offsets,
and places a common unit ruler beside the true time range. It performs no filtering, alignment,
centering or normalization. All three routes retain source data and require real OPJU/PNG/PDF/TIF,
object readback and visual QA.
