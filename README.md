<div align="center">
  <img src="runtime/src/origin_sciplot/resources/app_icon.png" width="96" alt="EditaPlot 图标">
  <h1>EditaPlot · 艾迪图</h1>
  <p><strong>AI 驱动的可编辑科研绘图工作流</strong><br>AI-guided editable scientific figures</p>
  <p>
    <img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-4c6ef5">
    <img alt="Platform: Windows 10/11 x64 only" src="https://img.shields.io/badge/platform-Windows%2010%2F11%20x64%20only-0078d4">
    <img alt="Python 3.10–3.12" src="https://img.shields.io/badge/Python-3.10%E2%80%933.12-3776ab">
    <img alt="Codex Skill" src="https://img.shields.io/badge/Codex-Skill-7c3aed">
    <img alt="Tested with Origin 2024b" src="https://img.shields.io/badge/tested%20with-Origin%202024b-0f766e">
  </p>
  <p><a href="README.en.md">English</a> · 中文为主要说明语言</p>
</div>

EditaPlot 是面向 Codex 的 Windows 本地科研绘图 Skill。它把“理解数据、选择图形、冻结规则、调用 Origin、验证结果”连成一条可审计工作流，让用户自己的实验数据生成**可编辑 OPJU**，并同步导出 PNG、PDF、TIF。

它不是一套只能替换数字的静态模板，也不会用 Python 位图冒充 Origin 成图。用户仍然掌握科学含义与最终选择；低置信度时，Skill 会先请求确认，而不是擅自补列、拟合或推断结论。

> [!WARNING]
> **V1 只支持 Windows 10/11 x64 实体电脑。** macOS（Intel 与 Apple Silicon）、Linux、WSL、Wine/CrossOver、Parallels 及其他虚拟机均不受支持。Mac 用户请不要照着 Windows 步骤硬装；当前版本无法在 macOS 上调用 Origin。

> [!IMPORTANT]
> EditaPlot 按 [Apache License 2.0](LICENSE) 开源。运行绘图需要用户自行合法安装、激活并能手动启动 Origin/OriginPro；仓库不包含 Origin、许可证、破解补丁或授权绕过。

## 一眼看懂

```mermaid
flowchart LR
    A["用户数据<br>CSV / TXT / XLS / XLSX"] --> B["Inspect<br>识别列角色、单位与风险"]
    B --> C["Recommend<br>建议图形与科研配色"]
    C --> D["确认一句科学目的"]
    D --> E{"置信度足够？"}
    E -- 否 --> F["追加确认<br>列义、误差、顺序或第三轴"]
    F --> G["冻结 RenderPlan"]
    E -- 是 --> G
    G --> H["本地 Origin / OriginPro"]
    H --> I["OPJU + PNG + PDF + TIF"]
    I --> J["对象反读 + 源数据 hash + 人工视觉 QA"]
```

正式成功不是“看见一张 PNG”，而是同时满足：可编辑 Origin 项目、四格式输出、源数据 hash 不变、轴/字体/图层/对象反读，以及人工视觉检查。

## 能力覆盖

| 领域 | 已覆盖图形与证据 |
|---|---|
| 材料与光谱 | XPS、XRD、XAS、PL/TRPL、UV–Vis/Tauc、EIS、CV、LSV、三维多条件 Nyquist |
| 通用统计 | 柱状/条形、误差棒、堆叠/百分比堆叠、饼图、桑基、折线、趋势、散点、气泡、雷达、热力图 |
| 分布与效应 | 原始点汇总、箱线、小提琴、Raincloud、直方图、森林效应图 |
| 医学与深度学习 | ROC、PR、校准、DCA、混淆矩阵、Bland–Altman、配对纵向轨迹、分组箱线、预计算 SHAP、医学多面板规划 |

绘图层不会静默平滑、拟合、删异常值、补峰、计算误差、识别物相、训练模型、调用 SHAP，或计算寿命与带隙。只有用户明确提供的测量值、拟合结果、参考峰、误差、SHAP 或 Tauc 数据才会进入图中。

## 真实 Origin 示例

以下图片来自中性合成教学数据，已在 Origin/OriginPro 2024b（10.15）中生成并人工复核；公开 PNG 已清理元数据并由清单锁定 hash。

<div align="center">
  <img src="assets/gallery/xps-fit.png" alt="XPS 峰拟合" width="31%">
  <img src="assets/gallery/medical-grouped-box.png" alt="医学分组箱线图" width="31%">
  <img src="assets/gallery/uv-vis-tauc.png" alt="UV–Vis 与 Tauc 插图" width="31%">
  <img src="assets/gallery/percent-composition.png" alt="百分比堆叠组成图" width="31%">
  <img src="assets/gallery/medical-roc.png" alt="医学模型 ROC" width="31%">
  <img src="assets/gallery/trajectory3d.png" alt="三维多条件 Nyquist 轨迹" width="31%">
</div>

➡️ [浏览全部 37 个图形案例与简要用途](docs/gallery.md)

## 中文科研配色

![EditaPlot 中文科研配色选择](assets/palettes/palette-selector-public.zh-CN.png)

首屏提供 8 套推荐色组，完整目录另含 2 套进阶色组。用户确认 `palette_id` 后，精确 HEX、允许模式、安全类别上限、色盲与灰度风险都会冻结进 RenderPlan。XPS component、正负效应、热力图、诊断参考线与混淆矩阵等语义色不会被普通美化偏好覆盖。

配色来自项目原创重绘与抽象，不包含参考目录中的期刊封面、水印或版式，也不代表任何期刊官方认可。详见[配色指南](docs/palette-guide.md)。

## 开始使用

### 1. 准备环境

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10/11 x64 实体电脑；不支持 macOS、Linux、WSL 或虚拟机 |
| Origin | 用户自行合法安装、激活，并已确认可以手动正常启动 |
| Origin 验证范围 | 已验证 Origin/OriginPro 2024b（10.15）；其他版本必须逐版本重新验证 |
| Python | CLI/依赖在 64 位 CPython 3.10–3.12 上覆盖；真实 Origin 端到端基线为 CPython 3.10 + Origin 2024b |
| 数据 | CSV、TXT、XLS 或 XLSX；支持中文列名与中文路径 |

根目录的 `editaplot.cmd` 会优先发现用户已有的兼容 Python，再创建项目级 `.editaplot-venv` 并安装经过锁定的依赖。若完全没有兼容 Python，Skill 会先用中文说明这是系统级变更并取得明确确认，再优先通过官方 winget 以用户范围安装 Python 3.12；没有 winget 时只提供 python.org 官方安装指引。它不会静默改变系统，且永远不会安装、修改、激活或启动 Origin。

### 2. 安装 Codex Skill

```powershell
git clone https://github.com/hang-jin/editaplot.git
Set-Location editaplot
.\editaplot.cmd setup
```

必须保留完整仓库；**不要只复制 `skill/editaplot` 子目录**，否则绘图 runtime 不在，最终会报 `engine_not_found`。不会 GitHub 也没关系：可以下载仓库的 Source ZIP，完整解压后在该目录运行同一条 `setup` 命令。详见[安装指南](docs/installation.md)。

重新打开一个 Codex 任务后使用 `$editaplot`。第一次处理数据，只需：

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

更简单的做法是把文件拖进 Codex，然后说：“请使用 `$editaplot` 帮我画这份数据。”Skill 会在后台完成环境检查、只读识别与候选图推荐；它总会请你确认一句科学目的，低置信度时才追加询问列义、误差或变换等关键问题。熟悉命令行后，也可以使用确定性 CLI：

```powershell
.\editaplot.cmd doctor
.\editaplot.cmd inspect <data.csv>
.\editaplot.cmd recommend <data.csv> --intent "比较模型并展示误差"
.\editaplot.cmd palettes
.\editaplot.cmd plan <data.csv> --template-id bar --claim "模型 A 指标更高" --evidence-role comparison --palette-id ocean_coral --output render-plan.json
.\editaplot.cmd render render-plan.json --confirm-origin-started
.\editaplot.cmd verify <Origin-output-directory>
```

仓库包含经过清理的自包含 `runtime/`。只有开发者替换内置引擎时才需要 `--engine-home <engine-root>`。

### 3. 直接复制给 Codex 的提示词

```text
请使用 $editaplot。先检查本机环境并优先复用已有的兼容 Python；若完全没有，请先用中文说明
安装官方 Python 3.12 是系统级变更并等我明确同意。Python 包只装进项目环境，不要安装或修改 Origin。
然后只读分析我提供的数据，说明列角色、单位与歧义，最多推荐 3 种合适图形并展示中文配色选择。
先让我确认一句科学目的；低置信度时再追问必要细节。确认后冻结 RenderPlan，不修改原始数据；
我会在手动启动 Origin 后再授权绘制与验证。
```

需要正式绘图时：

```text
我已手动正常启动官方 Origin。请按已确认的 RenderPlan 绘制，保留可编辑 Origin 窗口，
导出 OPJU、PNG、PDF、TIF，并完成轴、字体、图层、数据映射反读和人工视觉检查。不要只看 PNG 报成功。
```

## 公开仓库与本地私有证据

公开源码是一套完整可运行的软件；本地私有层只保存发布审计不应携带的证据，不是隐藏功能或“付费完整版”。

| 进入公开仓库 | 仅保留在开发者/用户本地 |
|---|---|
| Apache-2.0 源码、完整 Skill、清理后的 runtime | `DEVELOPMENT_LEDGER.md`、内部计划与开发日志 |
| 中性合成示例数据、原创配色资产 | 用户原始数据、参考截图、未获再分发许可的材料 |
| 37 个已复核且清理元数据的 PNG | OPJU/PDF/TIF、RenderPlan、对象反读与验证 JSON |
| 双语文档、测试、依赖锁、资产与 runtime 校验清单 | 本机绝对路径、缓存、虚拟环境、临时输出、私钥与 token |

所有公开文件由默认拒绝式白名单、扩展名/体积限制、路径与密钥扫描、PNG 结构与元数据检查、资产 provenance 和 SHA-256 清单共同约束。完整规则见[发布与许可边界](docs/release-boundaries.md)。

## 科学与安全边界

- 原始文件只读；helper columns 只进入内存或可编辑 Origin 工作簿。
- 缺少列时给出修复说明，不补造不存在的测量值。
- 3D 只在第三轴具有真实实验含义且能改善证据表达时使用，拒绝装饰性 3D。
- 图例可在 OPJU 中手动移动；坐标轴缺失、字体不一致、色条重叠或文字裁切属于失败。
- 新 Origin API 必须先查官方文档并做隔离实验；禁止未经验证的 LabTalk 参数。

## 独立项目声明

EditaPlot 需要用户另行获得、在本机安装并合法许可的 Origin 或 OriginPro。项目不捆绑、不安装、不激活、不破解该软件，也不通过网络或云端开放其 Automation Server。EditaPlot 与 OriginLab Corporation 无隶属、赞助或背书关系；相关名称仅用于说明兼容性。

## 开源、贡献与支持

### Star 趋势

<a href="https://github.com/hang-jin/editaplot/stargazers">
  <img src="https://raw.githubusercontent.com/hang-jin/editaplot/metrics/stars.svg" alt="EditaPlot GitHub Star 趋势图">
</a>

趋势图由 GitHub Actions 在检测到 Star 总数变化时保留观测点，并发布到独立 `metrics` 分支；实线从首次采集开始且可升可降，公开 Star 时间仅作为虚线上下文。GitHub 不提供取消 Star 的时间，也无法还原首次采集前的历史峰值。仓库首次运行该工作流后图片才会出现。点击图片可查看当前 stargazers。

- 许可证：[Apache License 2.0](LICENSE)
- 安装与故障处理：[安装指南](docs/installation.md)
- 中文快速开始：[docs/quickstart.zh-CN.md](docs/quickstart.zh-CN.md)
- 贡献说明：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全报告：[SECURITY.md](SECURITY.md)
- 支持范围：[SUPPORT.md](SUPPORT.md)
- 依赖与许可证清单：[docs/dependency-inventory.md](docs/dependency-inventory.md)

维护者以后可以另行提供咨询、安装协助、定制或支持服务，但不会限制 Apache-2.0 已授予的权利。若未来改为收费软件许可、托管/远程服务、多租户运行，或把第三方商标用于产品名称与宣传，必须重新完成许可和商标审计。
