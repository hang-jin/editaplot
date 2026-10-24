<div align="center">
  <img src="runtime/src/origin_sciplot/resources/app_icon.png" width="64" alt="EditaPlot 图标">
  <h1>EditaPlot · 艾迪图</h1>
  <p><strong>先看懂数据，再生成可编辑的 Origin 科研图</strong></p>
  <p>给 Codex 一份表格，确认数据用途，拿到 OPJU 与 PNG / PDF / TIF。</p>
  <p>
    <img alt="Apache-2.0 开源" src="https://img.shields.io/badge/license-Apache--2.0-0f766e?style=flat-square">
    <img alt="Windows 10/11 x64" src="https://img.shields.io/badge/Windows-10%2F11%20x64-315b7d?style=flat-square">
    <img alt="Python 3.11–3.12" src="https://img.shields.io/badge/Python-3.11%E2%80%933.12-315b7d?style=flat-square">
    <a href="https://github.com/hang-jin/editaplot"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/hang-jin/editaplot?style=social"></a>
  </p>
  <p><a href="#开始使用">开始使用</a> · <a href="docs/gallery.md">看图选模板</a> · <a href="docs/quickstart.zh-CN.md">中文教程</a> · <a href="README.en.md">English</a></p>
</div>

我把 EditaPlot 做成了一个面向 Codex 的科研绘图 Skill：先说明每列数据的作用，再选图、确认、调用本机 Origin，最后检查交付结果。你负责科学判断，程序负责把确认过的表达落到可继续编辑的图里。

**适用环境：Windows 10/11 x64 实体电脑 + Codex + 本机 Origin/OriginPro。** Mac、Linux、WSL 和虚拟机暂不支持。日常使用不需要先手动打开 Origin。

## 先看看能画什么

<table>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="assets/gallery/xps-fit.png"><img src="assets/gallery/xps-fit.png" width="420" alt="真实 Origin XPS 原始谱与已提供分峰，合成教学数据"></a><br>
      <strong>XPS 原始谱与已提供分峰</strong><br>
      <sub>按实际列展示背景、包络和组分，不补造缺失峰。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="assets/gallery/medical-grouped-box.png"><img src="assets/gallery/medical-grouped-box.png" width="420" alt="真实 Origin 分组箱线图与原始观测点，合成教学数据"></a><br>
      <strong>分组箱线与原始点</strong><br>
      <sub>同时看组间分布和每个观测，而不只看一根柱子。</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center" valign="top">
      <a href="assets/gallery/time-frequency.png"><img src="assets/gallery/time-frequency.png" width="420" alt="真实 Origin 预处理时频矩阵及独立数值色标，合成教学数据"></a><br>
      <strong>预处理时频矩阵</strong><br>
      <sub>保留全部网格、物理坐标和单位，使用独立色标。</sub>
    </td>
    <td width="50%" align="center" valign="top">
      <a href="assets/gallery/flim-phasor.png"><img src="assets/gallery/flim-phasor.png" width="420" alt="真实 Origin FLIM G-S 相量点云及数学参考半圆，合成教学数据"></a><br>
      <strong>FLIM G–S 相量</strong><br>
      <sub>显示上游提供的相量坐标，不从原图反演寿命。</sub>
    </td>
  </tr>
</table>

这些示例都用**合成教学数据，由真实 Origin 生成**，不代表实验或临床结论。点击图片可以看原图。

**[浏览全部 45 条绘图路线 →](docs/gallery.md)**　[English gallery](docs/gallery.en.md)

## 开始使用

### 1. 让 Codex 安装完整仓库

不会 GitHub 也没关系，把下面这段话复制给 Codex：

~~~text
请帮我安装最新 main 版 EditaPlot：
仓库：https://github.com/hang-jin/editaplot
请下载并保留完整仓库（包括 runtime），运行根目录 editaplot.cmd setup 和 doctor。
优先复用已有的 64 位 Python 3.11/3.12；需要安装 Python 时先问我。
不要安装或修改 Origin，不要修改注册表、DCOM，也不要申请管理员权限或控制鼠标。
完成后用中文告诉我环境是否就绪，再让我提供数据。
~~~

也可以[下载完整 ZIP](https://github.com/hang-jin/editaplot/archive/refs/heads/main.zip)，完整解压后让 Codex 在该文件夹里安装。**不要只复制 <code>skill/editaplot</code> 子目录**，它需要仓库中的绘图引擎。

<details>
<summary>我会用 Git，直接给我安装命令</summary>

~~~powershell
git clone https://github.com/hang-jin/editaplot.git
Set-Location editaplot
.\editaplot.cmd setup
~~~

首次运行缺少兼容 Python 时，先按[安装指南](docs/installation.md)完成确认与配置。项目依赖只进入本项目环境，不修改全局 Python。

</details>

### 2. 附上表格，说清楚想表达什么

在新的 Codex 对话中使用 <code>$editaplot</code>，附上 CSV、TXT、XLS 或 XLSX。可以先这样说：

~~~text
请用 $editaplot 处理这份数据，不要修改原文件。
先用中文说明每列用途，推荐 1–3 种合适的图，并列出需要我确认的单位、误差和图形元素。
我确认后，再调用 Origin 绘图，交付可编辑 OPJU、PNG、PDF、TIF，并检查轴、字体和视觉结果。
~~~

支持中文列名和中文路径。不确定该画哪种图，就让它先推荐；已经有目标，也可以直接说“分组箱线图”“XPS 多谱线对比”或“预计算 SHAP”。

医学数据和参考图请先按机构要求去标识化，并检查图像中的身份文字。EditaPlot **不承诺自动发现 PHI**。

### 3. 确认表达，收下可编辑结果

确认清单会说明：**哪些列画出来，哪些只作辅助，哪些保留但不画，哪些还需要问清楚**。原文件没有的测量值、分峰和误差不会被补造。

正式结果默认集中保存在原始数据旁的新文件夹中：

~~~text
我的数据.csv
我的数据_EditaPlot_<时间>/
  render-plan.json
  result.opju
  result.png
  result.pdf
  result.tif
  ……反读与验证报告
~~~

完成后可以保留 Origin 可编辑窗口，继续调整图例等细节。图例遮挡允许后续手动调整；缺轴、错字体、色标重叠或文字裁切仍需要修正。完整教程见[中文快速开始](docs/quickstart.zh-CN.md)。

<details>
<summary>已经安装旧版，怎样更新？</summary>

让 Codex 检查本地改动、保留你的文件，再安全更新完整仓库并重新运行 <code>editaplot.cmd setup</code> 和 <code>doctor</code>。

当前安全运行时使用 Python 3.11/3.12 与 Pillow 13，新建环境优先 3.12；Python 3.10 不再承载当前依赖。旧项目环境和替换下来的 Skill 会保留为备份，不会悄悄退回旧依赖。旧方案若提示 <code>analysis_changed</code>，请重新理解、确认并生成方案，不要手改 JSON。

</details>

## 按你的数据选择模板

我目前维护 **45 条公开绘图路线**。同一路线可适配不同系列数、列名或已支持的显示模式，不需要为每种材料重新做一个模板。先看格式，再把自己的数据交给 Codex。

| 你的数据 | 常见表达 | 格式与示例 |
|---|---|---|
| 材料、光谱与电化学 | XPS、XRD/GSAS、PL/TRPL、UV–Vis/Tauc、FTIR、NMR、DSC、XAS、EIS、CV、LSV | [XPS 表格](runtime/templates/xps/data_template.csv) · [XRD 精修](runtime/templates/xrd/example_gsas_publication.csv) |
| 分组观测、误差与组成 | 柱/条形、原始点、箱线、小提琴、Raincloud、堆叠、百分比组成、森林图 | [分组箱线](runtime/templates/grouped_box/data_template.csv) · [带误差柱图](runtime/templates/bar/data_template.csv) |
| 医学与模型评估 | ROC、PR、校准、DCA、混淆矩阵、Bland–Altman、配对轨迹、预计算 SHAP | [分栏 SHAP 表格](runtime/templates/shap_dashboard/data_template.csv) · [图库](docs/gallery.md) |
| 荧光、EEG 与研究信号 | G–S 相量、共幅度多通道轨迹、时频矩阵、事件栅格 | [数据合同与用法](docs/research_signals.md) |
| 关系、流向与三维 | 散点、气泡、趋势、雷达、桑基、环形有向网络、具有真实第三轴的三维曲线 | [真实案例与数据](docs/gallery.md) |
| 分类矩阵 | 热力图与高密度矩阵；保留源值和顺序 | [输入格式](runtime/templates/heatmap/data_template.csv) |

XPS、GSAS、SHAP、寿命或带隙等有专门的科学边界。绘图层不会擅自做拟合、找峰、训练模型、重建影像或计算原始 EEG 的频谱；需要上游结果时会先说明。具体能力以对应模板和本机检查为准。

## 参考图和配色，也可以自己定

可以选择**模板默认、参考图建议、精确自定义**三种方式。你的明确选择优先；参考图只提供可采用的图形语法与风格，不复制它的数据、结论、样品名或水印。

例如：“Raw 用 <code>#173F5F</code>、线宽 <code>2.4 pt</code>、填充透明度 <code>38%</code>、画幅 <code>18 × 18 cm</code>，隐藏图例。”Codex 会核对该模板是否支持，并逐项记录采用、保留默认或拒绝，不把不支持的参数装成已经生效。

[查看中文配色卡](docs/palette-guide.md) · [参考图与精确样式规则](skill/editaplot/references/reference-figures.md)

## 环境与权限

| 项目 | 当前范围 |
|---|---|
| 系统 | Windows 10/11 x64 实体电脑；Mac、Linux、WSL、Wine/CrossOver、Parallels 和其他虚拟机暂不支持 |
| Python | 64 位 CPython 3.11 / 3.12；优先 3.12，安装器自动发现兼容版本 |
| Origin | 2021–2026b 是兼容目标；不是全部版本、全部模板组合都已验证 |
| 当前实机基线 | Python 3.12.14 + Pillow 13.0.0 + Origin 2024b（10.15.132），已完成 6 个代表案例回归；其他环境需先过 smoke 与模板能力检查 |
| 安装内容 | 完整仓库与项目隔离依赖；不捆绑、安装或修改 Origin |

**只给当前任务需要的权限**：读取仓库和选定数据；写入仓库、当前用户的 <code>$HOME\.codex\skills\editaplot</code> 及原始数据父文件夹；运行本地命令与自有 Origin 实例。联网主要用于下载、更新和锁定依赖安装。

普通使用不需要管理员权限、鼠标控制、全盘写入或 DCOM、注册表、防火墙修改。遇到输出目录受保护时，只处理当前文件夹或明确指定另一个可写位置。

<details>
<summary>Codex 提示隔离上下文或权限不足时</summary>

让 Codex 为**原来的精确 Origin 命令**发起正式、受限的本地执行申请；只有获批才重跑，自动审查不保证批准，也不等于授权所有后续命令。不要把任务转到管理员 PowerShell，不要修改 DCOM/注册表或无限重试。

详细步骤和排队/耗时诊断见[安装与排障](docs/installation.md)。

</details>

本地 runtime 与 Origin 自动化**不会主动把你的数据上传到网络**；但你交给 Codex 的文件仍受当前账号、组织和数据保留政策约束。详见[隐私说明](PRIVACY.md)。

## 继续了解

| 我想做什么 | 从这里开始 |
|---|---|
| 看所有图形，找适合的数据格式 | [中文图库](docs/gallery.md) · [English gallery](docs/gallery.en.md) |
| 完整跑通第一张图 | [中文教程](docs/quickstart.zh-CN.md) · [English quick start](docs/quickstart.en.md) |
| 安装、升级、权限或运行慢 | [安装与排障](docs/installation.md) |
| 绘制荧光与研究信号 | [输入规范和使用说明](docs/research_signals.md) |
| 查 Origin 版本适配边界 | [2021–2026b 兼容说明](docs/origin-2021-2026-compatibility.md) |
| 了解源码、依赖与公开范围 | [发布边界](docs/release-boundaries.md) · [依赖清单](docs/dependency-inventory.md) |

## Star 趋势

如果它帮你省下了调图时间，欢迎点个 Star，让更多有需要的人找到它。我只按日记录仓库 Star 总数，**不保存或展示用户名单、账号 ID 或个人加星时间**。

<div align="center">
  <a href="https://github.com/hang-jin/editaplot"><img src="https://raw.githubusercontent.com/hang-jin/editaplot/metrics/assets/star-trend/stars.svg" width="760" alt="EditaPlot GitHub Star 总数趋势"></a>
</div>

## 开源、贡献与支持

我以 [Apache License 2.0](LICENSE) 开源并独立维护 EditaPlot。项目与 OriginLab Corporation 没有隶属、赞助或背书关系，相关名称仅说明兼容性。

欢迎提供可公开的最小示例和清楚的复现步骤；请勿在 Issue 放病历、私有数据、凭据或完整私人路径。

[贡献说明](CONTRIBUTING.md) · [支持范围](SUPPORT.md) · [安全报告](SECURITY.md) · [隐私](PRIVACY.md)

## 请我喝杯咖啡 ☕

如果 EditaPlot 对你有用，可以随意请我喝杯咖啡。一毛、两毛或几块钱，对我来说都是鼓励，也支持我继续维护模板和教程。

赞赏完全自愿，不会解锁任何额外功能，不改变问题处理顺序或 Apache-2.0 权利。不赞赏也没关系，分享项目和一条有用的反馈同样帮得上忙。

<details>
<summary>微信赞赏码</summary>

<p align="center"><a href="assets/support/wechat-tip.png"><img src="assets/support/wechat-tip.png" width="280" alt="作者提供的微信赞赏码"></a></p>

请勿在付款备注中填写实验数据、病历、账号等敏感信息。

</details>
