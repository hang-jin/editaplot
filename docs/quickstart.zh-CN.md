# 中文快速开始

## 30 秒版本

前提：Windows 10/11 x64 实体电脑、64 位 CPython 3.10–3.12，以及本机已安装
Origin/OriginPro 2021–2026b 范围内的版本。Origin 2024b（10.15）是当前唯一完整实机基线；
其他目标版本会经过本机握手、真实 smoke 和模板能力检查后报告兼容状态。Origin 2020b 及更早版本、
macOS、Linux、WSL、Wine/CrossOver、Parallels 与其他虚拟机不支持。

我当前公开了 40 条 Origin 绘图路线，保留 47 张通过完整验证的 PNG 作为审计资产，其中
45 张用于页面展示。新加入的三维双密度路线只接受用户上游提供的两条密度曲线和每组一个
Z=0 基线焦点，不会自动运行 KDE、找峰或求交点。热力图页面只展示真实 Origin 生成的 30×30 高密度案例；小矩阵和
40×40 案例只留作回归历史，不会重复出现在图库中。

安装时必须下载**完整仓库**，在仓库根目录运行：

```powershell
.\editaplot.cmd setup
```

不要只复制 `skill/editaplot`，那样没有绘图 runtime。会 Git 的用户可以 `git clone`；不会 Git
或没有 GitHub 账号的用户可以下载 Source ZIP 并完整解压。完整步骤见[安装指南](installation.md)。
我让启动器先复用已有的 64 位 CPython 3.10–3.12；若完全没有兼容 Python，Codex 必须先向你
说明这是系统级变更并征得明确同意，才可通过官方 winget 以用户范围安装 Python 3.12。
EditaPlot 永不自动安装 Origin。

给 Codex 的最小权限是：读取完整仓库、数据和可选参考图；写入仓库、当前用户
`$HOME\.codex\skills\editaplot` 及数据父文件夹；运行本地 `editaplot.cmd`、PowerShell、Python
和同一 Windows 用户会话中的 Origin；首次下载/更新时访问 GitHub 与 Python 包源。普通使用不需要
管理员、鼠标、全盘写入或 DCOM/注册表/防火墙修改。目录被 Windows 安全策略或网盘锁定时，只放行
当前仓库和当前数据目录，或明确选择另一个可写输出目录。

如果 Codex 检测到当前命令实际运行在隔离账户中，它会在调用 Origin 前为这一条
精确的 `origin-smoke` 或 `render` 命令申请正式、受限的本地执行权限。只有这条精确申请获批后，
Codex 才会重跑同一条命令并继续；申请可以由你在提示时确认，也可以由已经配置的 Codex 自动审查
评估，但审批不保证通过，也不代表 Origin 命令已经提前获得权限。无需把命令复制到自己的
PowerShell，也无需管理员、DCOM 或注册表修改。这不是绕过沙箱；被本机或组织策略拒绝时，任务会
明确停止。

EditaPlot 本地 runtime 与 Origin 自动化不会主动上传数据；你主动交给 Codex 的文件仍受当前
Codex 账号、组织和数据保留策略约束。医学数据或参考图必须先按机构要求去标识化并检查烧录文字，
不要依赖 EditaPlot 自动发现 PHI。

然后把 CSV、TXT、XLS 或 XLSX 拖进 Codex，只说这一句：

```text
请使用 $editaplot 帮我画这份数据。自动检查环境并只读识别数据，推荐合适图形；
选定候选模板后，逐列说明哪些要画、哪些只作辅助或验证、哪些保留但不画，
再列出最终图形元素和不会自动进行的计算。先让我确认科学目的与这份清单；
不确定列请先问我。不要修改源文件，也不要补造、静默拟合或计算数据。
```

命令行用户可以运行：

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

## 我会让 Skill 替新手处理什么

1. 只读检查平台、兼容 Python、项目级依赖和本机 Origin 注册；缺 Python 时先征得明确同意。
2. 只读识别列名、列数、单位、数据类型、缺失值和可能的科研语义。
3. 根据问题与数据结构推荐最多三种图，并展示合适的中文配色选择。
4. 把每列归入“主要绘图、可见辅助、仅作支持/验证、保留不画、仍不确定”，并列出图形元素。
5. 请你确认科学目的和元素清单；只在列角色、误差、归一化、排序、双轴等含义不明确时追加问题。
6. 冻结不改源数据的绘图计划；真实 smoke 自动启动专用 Origin 实例，连接和能力通过后再绘制。
7. 导出 OPJU、PNG、PDF、TIF，并检查源 hash、轴、字体、图层、对象反读和人工视觉效果。

你不需要看到一串 `inspect → recommend → understand → plan` 的工程术语。我让 Codex 把它们
放在后台，对你只说清楚：“识别到了什么、哪些要画、哪些不画、建议怎么画、还有哪一点需要你决定”。

## 预计算 SHAP 数据

如果你已经在 Python、R 或模型训练流程中算好了逐样本 SHAP，最省事的长表至少包含三列：
`Feature`、`SHAP value`、`Feature value`。还可以提供 `Sample ID`、`Feature Order`、
`Mean absolute SHAP`、`Feature Group` 和 `Group contribution (%)`。中文等价列名也会参与识别。

我会根据实际列自动选择：仅蜂群、蜂群加顶部 Mean |SHAP|，或再加入分组贡献的复合图。
如果表中没有 Mean |SHAP| 或分组占比，但你希望显示它们，我会先列出从已提供 SHAP 值计算的
公式和数据来源，等你明确批准派生项后才继续。Feature value 的组内颜色归一化和确定性蜂群偏移
也会在理解清单中说明。源文件始终只读，可先照着
[`medical_shap_summary.csv`](../examples/gallery/medical_shap_summary.csv) 准备数据。

## GSAS / GSAS-II XRD 精修数据

对 Powder CSV 或 Publication CSV，我会让 Skill 区分：

- 要画：2θ、Observed、Calculated，以及文件实际提供的 Background、Difference 和明确 Phase 刻线；
- 只作辅助或保留：`weight`、`Q`、`Used`、`diff/sigma`、`Axis-limits` 等控制列；
- 不自动做：背景/差值计算、Rwp/χ² 计算、物相识别和峰归属。

Publication CSV 的 `Diff` 若已含显示位置，会按源值直接绘制，不会再偏移一次。你可以用
[`example_gsas_powder.csv`](../runtime/templates/xrd/example_gsas_powder.csv) 和
[`example_gsas_publication.csv`](../runtime/templates/xrd/example_gsas_publication.csv)
先熟悉格式。

## 想参考一张现有图片

把本地 PNG、JPEG 或 TIFF 一起交给 Codex，再说：

```text
请把参考图只当作视觉简报，提取它的图形元素、布局、数据编码和可安全采用的风格。
不要复制图中数据、文字、拟合结果、物相、Logo 或水印，也不要嵌入参考图片。
请另外问我是否要明确指定系列颜色、线宽、填充透明度、画幅比例，以及图例显示/无框/位置。
我的明确选择优先于参考图。请分别列出采用、保留模板默认、拒绝和仍需确认的内容；
只有当前模板已经验证并能反读的样式才算采用，等我确认后再适配。
```

这不是任意图片 1:1 复刻功能。参考图不能补出你的数据里没有的证据，也不能让仅用于验证或保留的
列突然出现在图中；当前模板不能可靠表达的关键元素会明确停止，而不是悄悄近似。对于 XPS，
外观选择也不能修改原始数据、列用途、结合能轴方向、峰组分身份或经过验证的单区域渐变填充路线。

### XPS 精确样式的最短用法

我建议你先说：“这次选精确自定义；Raw 用 `#173F5F`、Envelope 用 `#C94C4C`，线宽
`2.4 pt`、填充透明度 `38%`、画幅 `18 × 18 cm`，隐藏无框图例。”确认后，我会生成一个
小型 JSON，并在计划命令中加入 `--visual-style-json xps-visual-style.json`：

```json
{"series_colors":{"raw":"#173F5F","envelope":"#C94C4C"},"line_width_pt":2.4,"fill_transparency_percent":38,"page_size_cm":{"width":18,"height":18},"legend_visible":false,"legend_position":"none","legend_frame":false}
```

精确值优先于参考图；字段名错误、系列不存在或数值越界时，我会停止并请你修正。参考图提供的
近似建议则会逐项标明采用、保留模板默认或拒绝。无论选择哪种样式，科学语义合同都不会改变。
如果选择 `outside_right`，我会为 24 pt 图例预留 8 cm 的物理栏位；请同时选择足够宽的画幅。
画幅与图例放不下时会明确停止，不会缩小字号、裁切图例或把它压到数据曲线上。

## 需要正式绘图时

如果你直接使用命令行，确认 RenderPlan 后请按下面的顺序运行：

```powershell
$smokeDir = Join-Path $env:TEMP ("EditaPlot-origin-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.\editaplot.cmd origin-smoke --output-dir $smokeDir
.\editaplot.cmd render .\render-plan.json
.\editaplot.cmd verify "<正式输出目录>"
```

在 Codex 中不需要你自己复制执行这些 PowerShell 命令。若当前任务处于沙箱，Codex 应为精确的
Origin 命令发起一次受限审批；只有这条精确申请获批后，它才会重新执行同一条命令并继续。申请可
由你在提示时确认，也可由已经配置的自动审查评估，但审批不保证通过。被策略拒绝时应停止并解释，
不能改用管理员权限、DCOM/注册表修改或外部 PowerShell 旁路。

我把 `origin-smoke` 放在 render 前面，是为了先用 EditaPlot 自有的隔离 Origin 实例完成
最小建图和导出闭环，而不是把 Doctor 的只读发现当成已经连接成功。

环境已经配好且必要确认已经完成时，完整本地流程在 4–5 分钟内完成可视为合理；若没有等待你的
回复或权限、也没有新进度，却持续 30–60 分钟，请停止循环重试并按
[安装与分阶段排障指南](installation.md#runtime-duration)定位当前阶段。
新版会在可安全恢复的瞬时启动故障后尝试清理自有实例，并且只在清理成功时自动再试一次。清理失败
或第二次启动仍失败都会停止；再次运行要使用新的空白同级输出目录，以保留首次报告。不要仅因耗时
较长就强杀可能正在管理隐藏 Origin 的 Python worker；先保留诊断并确认最后停留的阶段。
若启动和清理都失败，报告会分别保存脱敏的最初启动代码/阶段和清理代码/阶段，不包含账户名、路径
或原始 COM 文本，也不会继续自动重试。

多个 Codex 任务可以同时分析数据和准备方案，但同一 Windows 登录会话中的新版 EditaPlot 会把
真正的 `origin-smoke` / `render` 阶段自动串行。等待时会看到 `origin_job_queue`，约每 30 秒更新
一次；顺序不保证严格先来先服务。等待达到 30 分钟时只停止等待者，不会杀掉占用者；进程结束后
Windows 会释放锁，成功后保留的 Origin 窗口也不继续占锁。该队列不能协调手动脚本、旧版
EditaPlot 或第三方程序，因此看到等待提示时不要重复提交同一绘图任务。

```text
请使用已确认的方案绘图。我不需要提前打开 Origin；请先运行真实 smoke，自动启动专用 Origin
实例并按当前版本和模板能力继续。成功后保留可编辑 Origin 窗口，导出 OPJU、PNG、PDF、TIF，
并完成轴、字体、图层、数据映射反读和人工视觉检查。若失败，只简要告诉我技术阶段和下一步；
不要只看 PNG 就汇报成功。
若只因 Codex 沙箱上下文停止，请为原来的精确 Origin 命令发起正式、受限的本地执行申请；只有
申请获批后才重跑，审批不保证通过。不要让我复制 PowerShell、使用管理员权限或修改 DCOM/注册表。
```

原始文件始终只读。缺少的数据列不会被补造；helper columns 只能存在于内存或可编辑 Origin 工作簿。
普通 render 不指定 `--output-dir`。我会让 EditaPlot 在源 CSV、TXT、XLS 或 XLSX 所在目录中，
新建与原文件同级的 `<source_stem>_EditaPlot_<timestamp>` 文件夹，把 RenderPlan、OPJU、
PNG、PDF、TIF、对象反读和验证文件全部放在里面。
