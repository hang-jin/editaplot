# 安装与环境自检 / Installation

## 先看兼容范围

EditaPlot V1 **只支持 Windows 10/11 x64 实体电脑**。macOS（Intel 与 Apple Silicon）、
Linux、WSL、Wine/CrossOver、Parallels 及其他虚拟机均不支持。当前没有 Mac 绘图模式，
也不建议用兼容层尝试调用 Origin。

`doctor` 会硬性检查 Windows 版本和 x64 架构，但无法可靠识别所有虚拟机；如果机器类型
不明确，请由用户确认它是实体 Windows 电脑。V1 对虚拟机仍不提供支持承诺。

你还需要：

- 64 位 CPython 3.10、3.11 或 3.12；CLI/依赖覆盖这三个版本，真实 Origin 端到端基线为 CPython 3.10；
- 本机已安装且可供 Automation 调用的 Origin/OriginPro；测试基线为 2024b / 10.15；
- 完整的 EditaPlot 仓库，而不只是 `skill/editaplot` 子目录。

> `editaplot.cmd` 会优先使用电脑上已有的兼容 Python。Python 依赖只进入项目目录的
> `.editaplot-venv`。完全没有兼容 Python 时，Skill 必须先说明并取得明确确认，才可安装官方
> Python；环境修复不会安装或修改 Origin，render 会在绘图开始时直接测试本机 Automation 连接。

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
哪些项目已就绪、哪些仍需要我手动处理。
```

## 第一次把数据交给它

最省心的方式是把 CSV、TXT、XLS 或 XLSX 拖进 Codex，然后说：

```text
请使用 $editaplot 帮我画这份数据。先检查环境并只读识别数据，最多推荐 3 种合适的图。
先让我确认一句科学目的；如果含义不明确再追加问题。不要修改源文件，也不要静默拟合或补造数据。
```

命令行入口等价于：

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

Skill 会在后台完成环境检查、数据识别和图形推荐。新手不需要理解 `inspect`、`recommend`
或 `RenderPlan` 这些内部步骤；它总会请你确认一句科学目的，只有列含义、误差、归一化、
排序等科学选择存在歧义时才会追加问题。

## Doctor：知道哪里还没准备好

```powershell
.\editaplot.cmd --diagnose
.\editaplot.cmd doctor
```

Doctor 会把 Python、Windows、runtime、依赖和 Origin 应用分别报告：

- `ready_for_analysis`：可以只读分析数据；
- `ready_for_render`：已具备尝试连接本机 Origin Automation 的技术前提；真正连接由 render 测试；
- `manual_blockers`：只能由用户处理的事项，不会被伪造为成功。

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
宣称 Origin 已可调用。Doctor 只报告 Automation 入口，真正连接由 render 阶段测试。

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
CLI/dependency coverage spans all three Python minors; the current live
Origin end-to-end baseline is CPython 3.10 with Origin 2024b.

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
data read-only. Recommend no more than three charts and ask me to confirm a one-sentence scientific
purpose; ask additional questions only when meaning is ambiguous. Do not modify the source or silently
fit, normalize, or invent data.
```
