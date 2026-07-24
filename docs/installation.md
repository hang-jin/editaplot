# 安装与环境自检 / Installation

## 先看兼容范围

EditaPlot V1 **只支持 Windows 10/11 x64 实体电脑**。macOS（Intel 与 Apple Silicon）、
Linux、WSL、Wine/CrossOver、Parallels 及其他虚拟机均不支持。当前没有 Mac 绘图模式，
也不建议用兼容层尝试调用 Origin。

`doctor` 会硬性检查 Windows 版本和 x64 架构，但无法可靠识别所有虚拟机；如果机器类型
不明确，请由用户确认它是实体 Windows 电脑。V1 对虚拟机仍不提供支持承诺。

你还需要：

- 64 位 CPython 3.10、3.11 或 3.12；CLI/依赖覆盖这三个版本，真实 Origin 端到端基线为 CPython 3.10；
- 本机已安装兼容目标范围内的 Origin/OriginPro 2021–2026b；2024b / 10.15 是当前唯一
  完整实机基线，其他目标版本会按本机握手、真实 smoke 和模板能力报告兼容状态；
- 完整的 EditaPlot 仓库，而不只是 `skill/editaplot` 子目录。

Origin 2020b 及更早版本不在当前外部 `originpro` 路线的支持范围内。
各版本怎样从“目标范围”进入“当前模板可用”状态，见
[Origin 2021–2026b 兼容说明](origin-2021-2026-compatibility.md)。

> `editaplot.cmd` 会优先使用电脑上已有的兼容 Python。Python 依赖只进入项目目录的
> `.editaplot-venv`。完全没有兼容 Python 时，Skill 必须先说明并取得明确确认，才可安装官方
> Python；环境修复不会安装或修改 Origin。用户无需提前打开 Origin，正式绘图前的真实 smoke
> 会自动启动一个由 EditaPlot 独占的专用实例并验证连接。

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

我让 Skill 在后台完成环境检查、数据识别和图形推荐。新手不需要理解 `inspect`、`recommend`、
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

PNG、JPEG 或 TIFF 参考图只作为视觉简报。我让 Codex 先总结它的面板、插图、点线柱等元素、
数据编码和有限的视觉风格，再分别告诉你哪些可以采用、哪些保持模板默认、哪些必须拒绝、哪些仍需
确认。只有已经通过数据语义确认、且当前模板能够安全表达的部分，才会进入绘图计划。

这项功能不会从像素提取实验数值，不复制参考图中的文字、拟合、物相、Logo 或水印，不把图片嵌入
OPJU，也不承诺任意图 1:1 复刻。你可以直接这样说：

```text
请把这张参考图只当作视觉简报，先总结可安全采用的图形语法和风格，不要复制图中数据或文字。
把“采用、保留模板默认、拒绝、仍需确认”分别列给我，等我确认后再适配到我的数据。
```

## Doctor：知道哪里还没准备好

```powershell
.\editaplot.cmd --diagnose
.\editaplot.cmd doctor
```

Doctor 会把 Python、Windows、runtime、依赖和 Origin 应用分别报告：

- `ready_for_analysis`：可以只读分析数据；
- `registration_detected`：只读发现了至少一个 Origin Automation 注册，不代表已经连接；
- `launch_registration_detected`：发现默认独立启动入口 `Origin.Application`；
- `attach_registration_detected`：发现显式连接已有窗口的 `Origin.ApplicationSI`；
- `live_connection_tested`：Doctor 中固定为 `false`，真实连接只由后续 smoke 验证；
- `ready_for_render`：已具备尝试默认独立启动的技术前提，不代表连接或模板能力已通过；
- `manual_blockers`：只能由用户处理的事项，不会被伪造为成功。

普通用户不需要阅读 CLSID、注册表视图或多版本候选列表。Codex 应只用一到三句说明
“能否分析、是否发现默认启动入口、下一步是什么”；完整字段保留在 JSON 诊断中。

如仅缺项目级 Python 依赖，可运行：

```powershell
.\editaplot.cmd doctor --repair
```

修复只使用锁定的依赖清单和项目级环境。Python 版本不兼容、非 Windows、runtime 缺失、
Origin Automation 入口未检测到或实际连接失败，都不能由 Python 依赖修复伪造成成功。

## 如果电脑完全没有兼容 Python

Skill 应先用中文告诉用户：接下来可能安装一个**用户范围的官方 Python 3.12**，这是系统级变更。
先用 Windows 官方包管理器 winget 只读查看准确的软件包信息：

```powershell
winget show --exact --id Python.Python.3.12 --source winget
```

向用户说明发布者、来源与协议，并再次得到明确同意后，才可执行：

```powershell
winget install --exact --id Python.Python.3.12 --source winget --scope user --architecture x64 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
```

安装完成后重新运行：

```powershell
.\editaplot.cmd setup
.\editaplot.cmd doctor
```

若 winget 不存在或安装失败，停止自动安装并引导用户使用
[python.org 官方 Windows 下载页](https://www.python.org/downloads/windows/)安装 64 位 Python
3.12，然后重跑 `setup`。winget 的参数含义可查阅
[Microsoft 官方 install 文档](https://learn.microsoft.com/windows/package-manager/winget/install)。

不得在未确认时安装 Python，不得改用来历不明的镜像或安装包，也不得因为 Python 已就绪而
宣称 Origin 已可调用。Doctor 只读枚举 `Origin.Application`、`Origin.ApplicationSI` 和安装
候选；真实 smoke 才会启动专用实例、读取实际版本并验证连接。

## 常见问题

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

The Skill reuses a compatible Python first. If none exists, it must explain the system-level change
and obtain explicit consent before running official winget to install `Python.Python.3.12` in user
scope. If winget is unavailable, it provides only the official python.org Windows installation
instructions. Locked dependencies still go into `.editaplot-venv`; Origin is never installed or
modified automatically.

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

For a GSAS/GSAS-II XRD refinement table, this understanding stage separates Observed, Calculated,
optional Background, supplied Difference, explicit Phase ticks, and non-rendering control columns.
For a supplied reference image, EditaPlot abstracts only safe figure grammar and style, asks for a
separate confirmation, and neither copies reference content nor promises an arbitrary one-to-one replica.
