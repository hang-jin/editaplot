# 安装与环境自检 / Installation

## 先看兼容范围

我目前把 EditaPlot V1 的完整支持范围限定为 **Windows 10/11 x64 实体电脑**。macOS（Intel 与 Apple Silicon）、
Linux、WSL、Wine/CrossOver、Parallels 及其他虚拟机均不支持。当前没有 Mac 绘图模式，
也不建议用兼容层尝试调用 Origin。

我让 `doctor` 硬性检查 Windows 版本和 x64 架构，但它无法可靠识别所有虚拟机；如果机器类型
不明确，请你确认它是实体 Windows 电脑。V1 对虚拟机仍不提供支持承诺。

你还需要：

- 64 位 CPython 3.10、3.11 或 3.12；CLI/依赖覆盖这三个版本，真实 Origin 端到端基线为 CPython 3.10；
- 本机已安装兼容目标范围内的 Origin/OriginPro 2021–2026b；2024b / 10.15 是当前唯一
  完整实机基线，其他目标版本会按本机握手、真实 smoke 和模板能力报告兼容状态；
- 完整的 EditaPlot 仓库，而不只是 `skill/editaplot` 子目录。

Origin 2020b 及更早版本不在当前外部 `originpro` 路线的支持范围内。
各版本怎样从“目标范围”进入“当前模板可用”状态，见
[Origin 2021–2026b 兼容说明](origin-2021-2026-compatibility.md)。

> `editaplot.cmd` 会优先使用电脑上已有的兼容 Python。Python 依赖只进入项目目录的
> `.editaplot-venv`。完全没有兼容 Python 时，我会要求 Codex 先说明并取得你的明确确认，才可安装官方
> Python；环境修复不会安装或修改 Origin。你无需提前打开 Origin，正式绘图前的真实 smoke
> 会自动启动一个由 EditaPlot 独占的专用实例并验证连接。

## 先给 Codex 哪些权限

我建议只批准完成当前任务必需的范围。不同 Codex 客户端显示的权限名称可能略有不同，但实际用途
应当能对应到下面五项：

| 最小权限 | 具体范围 | 为什么需要 |
|---|---|---|
| 读取文件 | 完整仓库、你选中的 CSV/TXT/XLS/XLSX、可选参考图 | 安装、数据理解与计划 |
| 写入项目 | EditaPlot 仓库目录 | 创建 `.editaplot-venv`、锁文件和项目配置 |
| 写入 Skill | 当前用户的 `$HOME\.codex\skills\editaplot` | 安装或原子更新 `$editaplot` |
| 写入交付目录 | 原始数据的父文件夹 | 在源文件旁新建 `<source_stem>_EditaPlot_<时间>` |
| 本地执行 | `editaplot.cmd`、PowerShell、Python，以及同一交互式 Windows 用户会话中的 Origin Automation | 体检、smoke、绘图、导出和对象反读 |

联网权限只在下载/更新仓库和安装锁定 Python 包时需要。完全没有兼容 Python 时，winget 安装属于
单独的系统级变更，必须再次解释并征得明确同意。普通运行不需要管理员权限、鼠标控制、整个磁盘
写权限，也不需要改 DCOM、注册表、防火墙、用户组或 Origin 安装。

如果仓库仍在 ZIP 压缩包里、位于 `Program Files` 等只读目录，先完整解压或移动到当前用户可写
目录。若 Windows“受控文件夹访问”、单位安全策略、OneDrive/网盘同步或杀毒软件阻止在数据旁
创建文件夹，请只放行当前仓库和当前数据目录，或由你明确指定另一个可写输出目录。不要为了省事
把 Codex、PowerShell 或 Origin 全部改成管理员运行。

Codex 桌面版的普通命令可能由隔离账户执行，即使 `USERNAME` / `USERPROFILE` 看起来仍是你的
资料。EditaPlot 会读取进程真实的 Windows 安全令牌；若识别为 Codex 沙箱，它会在调用 Origin
COM 前停止，并请 Codex 只为当前这条 `origin-smoke` 或 `render` 命令发起正式、受限的本地执行
申请。只有这条精确申请获批后，Codex 才会重新执行同一条命令并继续当前任务；申请可以由你在
提示时确认，也可以由已经配置的 Codex 自动审查评估，但审批不保证通过，自动审查也不代表所有
Origin 命令预先获得权限。无需复制到自己的 PowerShell，也无需管理员、DCOM、注册表或所谓
“绕过沙箱”。本机或组织策略拒绝申请时，任务会明确停止。

EditaPlot 的本地 runtime 与 Origin 自动化不会主动上传数据，但交给 Codex 的文件仍受你当前
Codex 账号、组织和数据保留策略约束。医学数据或参考图在交给 Codex 前必须先按所在机构要求
去标识化并检查烧录文字；EditaPlot 不会自动识别 PHI。

## 路线 A：会使用 GitHub / Git

在 PowerShell 中运行：

```powershell
git clone https://github.com/hang-jin/editaplot.git
Set-Location editaplot
.\editaplot.cmd setup
```

`setup` 会把 Skill 安装到当前 Codex 用户目录、记录本地 runtime 位置、选择兼容 Python，
并完成一次项目级依赖准备。关闭并重新打开一个 Codex 任务后即可使用 `$editaplot`。
安装后请保留完整仓库且不要随意移动；本地配置会指向其中的 `runtime/`。若移动了目录，
回到新的仓库根目录重新运行 `.\editaplot.cmd setup` 即可更新指向。

## 路线 B：不会 GitHub，也没有 GitHub 账号

GitHub 账号不是必需的。任选一种方式：

1. 在仓库网页点击 **Code → Download ZIP**，下载 Source ZIP；
2. 完整解压 ZIP，不要只拖出 `skill/editaplot` 文件夹；
3. 在解压后的仓库根目录打开 PowerShell；
4. 运行：

```powershell
.\editaplot.cmd setup
```

以后下载新版或执行 `git pull` 后，再运行一次 `.\editaplot.cmd setup` 即可安全更新已安装 Skill
和项目级依赖；不会覆盖其他非 EditaPlot 目录。

也可以把下面这段直接交给 Codex，让它在得到你的确认后完成下载与项目级配置：

```text
请从 https://github.com/hang-jin/editaplot 下载完整仓库到一个新文件夹。
不要只复制 skill/editaplot 子目录。阅读 README.md 和 docs/installation.md，
先复用已有的 64 位 CPython 3.10–3.12；若完全没有兼容版本，请先说明安装官方 Python 3.12
是系统级变更并等我明确同意。之后在仓库根目录运行 editaplot.cmd setup，Python 包只进入
项目环境。不要安装或修改 Origin。完成后运行 editaplot.cmd doctor，并用中文告诉我
是否可以分析、是否发现默认独立启动入口，以及最简洁的下一步。
```

## 第一次把数据交给它

最省心的方式是把 CSV、TXT、XLS 或 XLSX 拖进 Codex，然后说：

```text
请使用 $editaplot 帮我画这份数据。先检查环境并只读识别数据，最多推荐 3 种合适的图。
选定候选模板后，请逐列说明哪些要画、哪些只作辅助或验证、哪些保留但不画，并列出最终图形元素
和不会自动进行的计算。先让我确认科学目的和这份清单；不确定列必须先问我，不要修改源文件，
也不要静默拟合或补造数据。
```

命令行入口等价于：

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

我会让 EditaPlot 在后台完成环境检查、数据识别和图形推荐。你不需要理解 `inspect`、`recommend`、
`understand` 或 `RenderPlan` 这些内部步骤；Codex 会用大白话汇总数据类型、每列用途、要画的
图形元素、保留但不画的内容和不会自动进行的计算。你确认科学目的与这份清单后才能进入绘图；
列含义、误差、归一化、排序等科学选择存在歧义时，它只追问会改变图意的部分。

## 列很多时，EditaPlot 怎样避免“全部画上去”

我把每个源列分为五类：主要绘图证据、可见辅助元素、仅用于计算或验证、保留但不绘制、仍不确定。
每列必须且只能出现一次；不确定列会阻止绘图计划，不会自动变成另一条曲线。

GSAS / GSAS-II XRD Rietveld 是一个典型例子。对 Powder CSV 或 Publication CSV，Skill 会区分
Observed、Calculated、可选 Background、文件提供的 Difference、明确命名的 Phase 刻线，以及
`weight`、`Q`、`Used`、`diff/sigma`、`Axis-limits` 等非绘图控制列。Publication `Diff` 已有
显示位置时会按源值直接绘制，不会重复偏移；缺少的背景、差值或物相刻线也不会补造。

可以先查看仓库内的两个中性示例：

- [`example_gsas_powder.csv`](../runtime/templates/xrd/example_gsas_powder.csv)
- [`example_gsas_publication.csv`](../runtime/templates/xrd/example_gsas_publication.csv)

## 如果还上传了一张参考图

PNG、JPEG 或 TIFF 参考图只作为视觉简报。我会让 Codex 先总结它的面板、插图、点线柱等元素、
数据编码和有限的视觉风格，再分别告诉你哪些可以采用、哪些保持模板默认、哪些必须拒绝、哪些仍需
确认。只有已经通过数据语义确认、且当前模板能够安全表达的部分，才会进入绘图计划。

参考图中的样式只是候选，不替你做决定。你可以另外明确选择系列颜色、线宽、填充透明度、画幅
比例，以及图例是否显示、是否无框和放置位置；你的明确选择优先。Codex 会把每一项标为采用、
保留模板默认或拒绝。只有当前模板已经实现、通过 Origin 实机验证并能对象反读的字段才会标为采用。
对 XPS，这些外观请求也不能改写原始数据、列用途、结合能轴方向、峰组分身份或稳定的单区域渐变
填充 API。

这项功能不会从像素提取实验数值，不复制参考图中的文字、拟合、物相、Logo 或水印，不把图片嵌入
OPJU，也不承诺任意图 1:1 复刻。你可以直接这样说：

```text
请把这张参考图只当作视觉简报，先总结可安全采用的图形语法和风格，不要复制图中数据或文字。
另外询问并记录我明确选择的系列颜色、线宽、填充透明度、画幅比例和图例显示/无框/位置；
我的明确选择优先于参考图。把“采用、保留模板默认、拒绝、仍需确认”分别列给我，只有当前模板
已验证并能反读的字段才算采用，等我确认后再适配到我的数据。
```

## Doctor：知道哪里还没准备好

```powershell
.\editaplot.cmd --diagnose
.\editaplot.cmd doctor
```

我让 Doctor 把 Python、Windows、runtime、依赖和 Origin 应用分别报告：

- `ready_for_analysis`：可以只读分析数据；
- `registration_detected`：只读发现了至少一个 Origin Automation 注册，不代表已经连接；
- `launch_registration_detected`：发现默认独立启动入口 `Origin.Application`；
- `attach_registration_detected`：发现显式连接已有窗口的 `Origin.ApplicationSI`；
- `live_connection_tested`：Doctor 中固定为 `false`，真实连接只由后续 smoke 验证；
- `ready_for_render`：已具备尝试默认独立启动的技术前提，不代表连接或模板能力已通过；
- `origin_execution_context`：只公开 `interactive_user`、`codex_sandbox`、`non_windows` 或
  `unknown`，不会显示 Windows 用户名；
- `requires_current_user_approval`：当前 Origin 命令是否需要先走 Codex 的受限本地执行审批；
- `current_process_has_interactive_origin_context`：当前进程是否已经处于可尝试启动 Origin 的
  交互用户上下文；
- `manual_blockers`：只能由用户处理的事项，不会被伪造为成功。

`ready_for_render=true` 可以和 `requires_current_user_approval=true` 同时出现：前者表示 Python、
runtime 和默认启动入口等静态前提已找到，后者只说明当前 Doctor 进程仍在沙箱。这不是 Origin
安装故障，也不进入 `manual_blockers`；下一步是让 Codex 为真实 smoke 命令发起受限审批。
若 `origin_execution_context.status=unknown`，则 Windows 执行身份无法验证；它不是待审批状态，
即使静态前提已找到也必须在 COM 前停止，不能根据 `USERNAME` 或 `USERPROFILE` 猜测身份。

你不需要阅读 CLSID、注册表视图或多版本候选列表。我会让 Codex 只用一到三句说明
“能否分析、是否发现默认启动入口、下一步是什么”；完整字段保留在 JSON 诊断中。

如仅缺项目级 Python 依赖，可运行：

```powershell
.\editaplot.cmd doctor --repair
```

修复只使用锁定的依赖清单和项目级环境。Python 版本不兼容、非 Windows、runtime 缺失、
Origin Automation 入口未检测到或实际连接失败，都不能由 Python 依赖修复伪造成成功。

## 真实 smoke、正式绘图与输出目录

Doctor 只读发现环境，不代替真实连接。等你确认 RenderPlan 后，命令顺序必须是
`origin-smoke → render → verify`：

```powershell
$smokeDir = Join-Path $env:TEMP ("EditaPlot-origin-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.\editaplot.cmd origin-smoke --output-dir $smokeDir
.\editaplot.cmd render .\render-plan.json
.\editaplot.cmd verify "<正式输出目录>"
```

`origin-smoke` 默认启动一个由 EditaPlot 所有的隔离 Origin 实例，并完成最小建图与导出闭环。
只有 smoke 通过后才能运行正式 render。普通 render 不要指定 `--output-dir`：runtime 会在
原始 CSV、TXT、XLS 或 XLSX 所在目录中新建
`<source_stem>_EditaPlot_<timestamp>` 同级文件夹，将 RenderPlan、OPJU、PNG、PDF、TIF、
对象反读、验证与 provenance 集中保存。源文件不会被覆盖。只有你明确要求其他目的地时，
才可为 render 指定 `--output-dir`。

如果 smoke 或 render 返回 `origin_codex_sandbox_context`，说明它尚未调用 COM，也不能据此判断
Origin、版本或数据有问题。Codex 应为原来的精确命令发起一次受限本地执行审批；只有这条精确
申请获批后才可重跑。申请可以由你在提示时确认，也可以由已经配置的 Codex 自动审查评估，但
审批不保证通过。被本机或组织策略拒绝时应
停止，不能让你复制 PowerShell、切换管理员、修改 DCOM/注册表或改走未验证的接口。

多个 Codex 任务可以并行完成读取数据、理解列和制定 RenderPlan。真正进入新版 EditaPlot 的
`origin-smoke` 或 `render` 时，同一 Windows 登录会话只允许一个任务占用 Origin 自动化阶段；
其余任务报告 `origin_job_queue`，约每 30 秒更新一次，且不保证严格 FIFO。等待满 30 分钟时只
停止等待者，不会杀掉或打断持有者。持有进程结束或异常退出后由 Windows 释放锁；成功后保留的
Origin 窗口不会继续占锁。该保护不覆盖手动 Origin 脚本、旧版 EditaPlot 或其他程序，看到排队
状态时不要重复启动相同任务。

如果旧版本曾在 `style_graph` 阶段提示左边距应为 `17`、却读回约 `70.06`，请先更新仓库的
`main`，再重新运行 `setup` 和同一条 smoke。这个问题来自旧版几何反读兼容层，不需要改 Origin、
注册表或 DCOM，也不需要管理员权限。新版会用两条 Origin 原生 LabTalk 路径交叉确认图层几何；
两条路径不一致时仍会安全停止。若更新后仍失败，只需记录失败阶段、短错误代码和 Origin 产品版本，
公开截图前遮住所有与技术故障无关的信息和本地路径。

## 如果电脑完全没有兼容 Python

如果电脑完全没有兼容 Python，我会要求 Codex 先用中文告诉你：接下来可能安装一个
**用户范围的官方 Python 3.12**，这是系统级变更。
先用 Windows 官方包管理器 winget 只读查看准确的软件包信息：

```powershell
winget show --exact --id Python.Python.3.12 --source winget
```

Codex 会先向你说明发布者、来源与协议，并再次得到你的明确同意后，才可执行：

```powershell
winget install --exact --id Python.Python.3.12 --source winget --scope user --architecture x64 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
```

安装完成后重新运行：

```powershell
.\editaplot.cmd setup
.\editaplot.cmd doctor
```

若 winget 不存在或安装失败，我会让 Codex 停止自动安装并带你使用
[python.org 官方 Windows 下载页](https://www.python.org/downloads/windows/)安装 64 位 Python
3.12，然后重跑 `setup`。winget 的参数含义可查阅
[Microsoft 官方 install 文档](https://learn.microsoft.com/windows/package-manager/winget/install)。

我不会让 Codex 在未确认时安装 Python，不会改用来历不明的镜像或安装包，也不会因为 Python 已就绪而
宣称 Origin 已可调用。Doctor 只读枚举 `Origin.Application`、`Origin.ApplicationSI` 和安装
候选；真实 smoke 才会启动专用实例、读取实际版本并验证连接。

## 常见问题

<a id="runtime-duration"></a>

### 一次绘图要多久？为什么有人会等三四十分钟甚至一个小时？

我把“首次下载与安装”和“已经配置好以后画一张图”分开看。环境已经准备好、普通数据的科学含义
也已经确认后，从本地数据识别、Origin smoke、正式绘图导出到验证，完整流程在 **4–5 分钟内**
可以视为正常范围；这是一条排障参考线，不是对所有电脑和所有复杂数据的硬性承诺。

首次克隆或更新仓库、`setup` 下载锁定依赖、`doctor --repair`、等待用户回答科学含义，以及
Codex 对话受网络影响的等待时间，都要单独统计。EditaPlot 正常的 `--diagnose`、`doctor`、
`start`、`understand`、`origin-smoke`、`render` 和 `verify` 是本地流程；因此不能只看到总时间长，
就直接认定是网络慢。

如果在没有等待你确认的情况下，**30–60 分钟**都没有新的本地进度，这属于异常。不要连续重跑，
也不要只因经过时间较长就强杀 Python worker：它可能正在管理一个隐藏的 Origin 实例，强杀反而
可能留下无人管理的后台进程。先保留已有输出并看最后停在哪一类：

| 最后阶段 | 主要检查对象 |
| --- | --- |
| 仓库下载、`setup`、依赖修复 | 网络、包源、项目环境锁 |
| `--diagnose`、`doctor` | Python 发现、runtime、依赖和只读注册发现 |
| `start`、`understand`、`plan`、render 的 `analyze_data` | 数据读取、列用途、语义确认与绘图计划；不要把等待回复算作程序耗时 |
| `origin_smoke` | Origin 独立实例启动、握手、初始化和最小导出闭环 |
| `load_template` / `create_output_dir` / `validate_csv` | Origin 启动前的模板、目录或数据校验 |
| `launch_origin_draw_export_verify` | Origin 启动、工作簿/图形创建、导出和对象反读的诚实组合阶段 |
| `verify_outputs` | Origin 已返回，正在核对产物、源文件哈希和终端摘要 |

smoke 和 render 的 JSONL 进度事件会包含从各自 worker 启动起计算的 `elapsed_seconds`。两个 worker
会分别从零计时，这个值也不包含 Codex 对话和人工确认。终端单条事件限制在 32 KiB 内，完整
绘图计划和 Origin 对象反读保存在输出报告中，不会为了“看起来详细”把数万字符塞回对话。
瞬时实例启动失败会先尝试清理半启动实例，并且只在清理成功时自动再试一次；清理失败或第二次仍
失败都会停止。若用户批准再试，必须改用新的空白同级输出目录并保留第一次的报告，不能复用已经
含有诊断产物的目录。
如果第一次启动和清理步骤都失败，报告会同时保留脱敏的
`primary_activation_code` / `primary_activation_stage` 与
`cleanup_error_code` / `cleanup_error_stage`。它不会保存账户名、本地路径或原始 COM 文本，
也不会因拥有两组信息而继续自动重试。
需要保留现场时，可以运行：

```powershell
.\editaplot.cmd render .\render-plan.json 2>&1 |
  Tee-Object -FilePath .\render-progress.jsonl
```

反馈问题时，请一并提供运行的命令、最后一条事件的 `type`、`step` 和 `elapsed_seconds`、是否首次
安装，以及当时是否正在等待确认。这样我能判断是下载、环境、数据理解、Origin 连接，还是绘图
导出阶段，而不是靠猜测。

### 为什么不能只复制 Skill 文件夹？

Skill 是“操作说明与入口”，`runtime/` 才包含经过验证的绘图引擎。只复制子目录会失去
runtime，通常得到 `engine_not_found`。请保留完整仓库，并用根目录 `editaplot.cmd setup` 安装。

### 我装了 Python，为什么仍然不能运行？

可能是命令行指向旧版 Python，或只安装了不受支持的 3.13。直接运行
`.\editaplot.cmd --diagnose`；启动器会搜索 64 位 CPython 3.10–3.12，并优先复用兼容版本。

### Mac 能不能先用分析功能？

V1 不支持。为避免“分析能跑、Origin 绘图不能跑”的半成品体验，macOS（Intel/Apple Silicon）
被明确列为不支持；Parallels、Wine/CrossOver 和其他虚拟化方案也不在支持范围。

---

## English summary

EditaPlot V1 supports **physical Windows 10/11 x64 computers only**. macOS (Intel or Apple
Silicon), Linux, WSL, Wine/CrossOver, Parallels, and other VMs are unsupported. Use 64-bit
CPython 3.10–3.12 and a local Origin/OriginPro application reachable through Automation.
The compatibility target is Origin/OriginPro 2021–2026b; Origin 2024b (10.15) with CPython 3.10
is the only current fully verified live baseline. Other target versions are reported after a local
handshake, real smoke test, and template capability check. Doctor performs read-only discovery and never proves a live
connection. Users do not need to open Origin first: the smoke test starts an EditaPlot-owned,
dedicated instance. Attaching to an existing window is an explicit advanced mode only.

A normal Codex desktop command may run under an isolated account even when inherited profile
variables look familiar. EditaPlot checks the process's real Windows token and stops before COM
when it detects the Codex sandbox. Codex then submits a formal, narrowly scoped local-execution
request for the same `origin-smoke` or `render` command. Codex may rerun it only if that exact
request is approved. A user prompt or the configured Codex auto-reviewer may evaluate the request,
but approval is not guaranteed and auto-review does not pre-grant unrestricted access. Users do not
copy the command into their own PowerShell, use administrator rights, change DCOM/the registry, or
bypass the sandbox. A machine or organization policy may reject the request. An `unknown` Windows
execution context is not an approval request and stops fail-closed before COM.

Current EditaPlot workers also serialize their active smoke/render sections within one signed-in
Windows session while data analysis and planning remain concurrent. Waiting jobs report progress
about every 30 seconds; strict FIFO is not guaranteed. A 30-minute limit stops only the waiter, not
the active holder. Windows releases the lock when the holder exits, including an unexpected exit;
an Origin window kept open after completion does not retain the lock. Manual scripts, older
EditaPlot releases, and unrelated programs are outside this queue.

The Skill reuses a compatible Python first. If none exists, it must explain the system-level change
and obtain explicit consent before running official winget to install `Python.Python.3.12` in user
scope. If winget is unavailable, it provides only the official python.org Windows installation
instructions. Locked dependencies still go into `.editaplot-venv`; Origin is never installed or
modified automatically.

The bundled runtime and Origin automation do not initiate a network upload of selected data.
Files explicitly provided through Codex remain subject to the user's Codex account, organization,
and retention policies. Medical data and reference images must be deidentified and checked for
burned-in text before they are provided; EditaPlot does not automatically detect PHI.

With Git:

```powershell
git clone https://github.com/hang-jin/editaplot.git
Set-Location editaplot
.\editaplot.cmd setup
```

Without Git or a GitHub account, download **Code → Download ZIP**, extract the entire repository,
open PowerShell in its root, and run `.\editaplot.cmd setup`. Never copy only `skill/editaplot`,
because the runtime would be missing. Keep the repository after setup; if it is moved or updated,
run `.\editaplot.cmd setup` again from its new root. Then attach a data file in Codex and ask:

```text
Use $editaplot to make an appropriate figure from this file. Check the environment and inspect the
data read-only. Recommend no more than three charts, then classify every source column as drawn,
support/validation only, retained without rendering, or uncertain. List the final figure elements and
calculations that will not be performed. Ask me to confirm the scientific purpose and element checklist;
ask about uncertain roles instead of guessing. Do not modify the source or silently fit, normalize,
or invent data.
```

After the RenderPlan is confirmed, run the live gate and formal workflow in this order:

```powershell
$smokeDir = Join-Path $env:TEMP ("EditaPlot-origin-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.\editaplot.cmd origin-smoke --output-dir $smokeDir
.\editaplot.cmd render .\render-plan.json
.\editaplot.cmd verify "<formal-output-directory>"
```

Omit `render --output-dir` for ordinary work. The runtime creates a unique
`<source_stem>_EditaPlot_<timestamp>` folder in the same directory as the original CSV, TXT, XLS,
or XLSX file and keeps all formal artifacts there.

For a GSAS/GSAS-II XRD refinement table, this understanding stage separates Observed, Calculated,
optional Background, supplied Difference, explicit Phase ticks, and non-rendering control columns.
For a supplied reference image, EditaPlot abstracts only safe figure grammar and style, asks for a
separate confirmation, and neither copies reference content nor promises an arbitrary one-to-one
replica. A separately confirmed user choice of colors, widths, transparency, page/aspect ratio, and
legend behavior takes precedence; every field remains capability-gated and is reported as applied,
default retained, or rejected.
