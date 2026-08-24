# EditaPlot 的 Origin 2021–2026b 兼容说明

这份说明回答一个最常见的问题：**我的 Origin 版本能不能用 EditaPlot？**

先给结论：

- EditaPlot 的目标范围是 Windows 上的 Origin / OriginPro 2021 至 2026b。
- Origin 2024b（产品号 10.15）是当前唯一完成全链路实机验证的基线。
- “进入目标范围”不等于“所有模板已经在该版本逐一验证”。其他版本必须以本机握手、能力探针和
  真实输出证据为准。
- 默认由 EditaPlot 启动一个隔离的新 Origin 实例，不需要提前打开 Origin 窗口。
- 这里只判断技术可调用性，不收集与绘图无关的信息。

## 产品版本与产品号

下表的产品号来自 OriginLab 官方版本历史。EditaPlot 用它识别产品代际，但不会只看产品号就宣布
某个模板可用。

| Origin 产品 | 产品号 | EditaPlot 当前口径 |
| --- | ---: | --- |
| Origin 2021 | 9.80 | 目标范围；按本机证据判断 |
| Origin 2021b | 9.85 | 目标范围；按本机证据判断 |
| Origin 2022 | 9.90 | 目标范围；按本机证据判断 |
| Origin 2022b | 9.95 | 目标范围；按本机证据判断 |
| Origin 2023 | 10.00 | 目标范围；按本机证据判断 |
| Origin 2023b | 10.05 | 目标范围；按本机证据判断 |
| Origin 2024 | 10.10 | 目标范围；按本机证据判断 |
| **Origin 2024b** | **10.15** | **当前唯一完整实机基线** |
| Origin 2025 | 10.20 | 目标范围；按本机证据判断 |
| Origin 2025b | 10.25 | 目标范围；按本机证据判断 |
| Origin 2026 | 10.30 | 目标范围；按本机证据判断 |
| Origin 2026b | 10.35 | 目标范围；按本机证据判断 |

Origin 返回的 `@V` 还可能带有更长的构建后缀。产品号和具体构建号是两层信息，EditaPlot 不会把
任意后缀猜成某个官方 Service Release。

## 官方 External Python 边界

OriginLab 的 External Python 文档说明：

- 外部 `originpro` 路线仅适用于 Windows；
- 本机需要安装 Origin 2021 或更高版本；
- `originpro` 通过 Origin Automation Server 与 Origin 交互；
- 使用该包时会启动一个可见或隐藏的 Origin 实例。

因此，macOS 和 Linux 不在当前 Origin Automation 路线内，Origin 2020b 及更早版本也不在本页的
目标范围内。

## 为什么不要求提前打开 Origin

EditaPlot 默认采用隔离实例策略：

1. Skill 请求一个新的、由 EditaPlot 管理的 Origin 实例；
2. 在这个实例中创建工作簿、图页和项目；
3. 根据“完成后保留 Origin 窗口”的选择，显示或关闭这个实例；
4. 不触碰其他已打开的、由使用者管理的 Origin 会话。

OriginLab 的 Automation 文档指出，`Application` 总是创建新实例；`ApplicationSI` 则优先连接
已有实例。EditaPlot 默认使用前一种生命周期语义，因此不需要先打开 Origin。只有在明确选择
`attach_existing` 时，才进入附加已有会话的路线；该路线不会重置项目，也不会关闭已有会话。

## 一个版本怎样被判定为“可用于当前模板”

EditaPlot 不使用“版本号大于某个值，所以肯定兼容”的捷径。一次真实判断分为五层：

1. **Automation 握手**：能否创建隔离实例、读取就绪状态和必要环境信息。
2. **版本风险优先级**：已知产品或构建风险只决定先跑哪些探针。
3. **模板能力探针**：检查当前模板实际需要的轴、文本、误差棒、分类刻度、填充、参考线或三维等
   能力。
4. **真实产物**：必须生成非空、可编辑的 OPJU，以及 PNG、PDF、TIF。
5. **对象与视觉证据**：反读轴和文本等对象状态，并完成人工视觉检查。

只有 PNG、只有版本字符串、或者仅仅能导入 Python 包，都不足以证明完整兼容。

## 2024b 基线与其他版本

Origin 2024b / 10.15 是当前唯一完成上述全链路实机验证的基线。这表示 EditaPlot 已在该环境中
验证过可编辑项目、三种导出、对象反读和视觉结果。

2021、2021b、2022、2022b、2023、2023b、2024、2025、2025b、2026 和 2026b 都是兼容目标，
但不能笼统写成“全部已经验证”。同一个产品的不同构建、不同 `originpro` / `OriginExt` 组合，
以及不同模板所需能力都可能不同，所以最终结论来自本机证据。

## 2026b SR1 出现“17 读成 70.06”时

我们已经收到并定位了这一类真实反馈：Origin 2026b SR1 可以正常启动、建表和建图，但旧版
EditaPlot 在 `style_graph` 阶段把应为 `17%` 的左边距读成约 `70.06%`，于是安全停止。这个数字
很像图层宽度；现有证据把问题范围收敛到 `originpro` Automation bridge 与 Origin 原生图层几何
读回的分歧，而不是数据文件格式或普通操作步骤。

新版不再把单一 bridge 数值当成几何真值，也没有简单忽略错误。它会同时检查：

1. `layer.unit` 必须为 `1`，也就是以图页百分比表示；
2. LabTalk 的 `layer.left/top/width/height`；
3. 官方 `layer -x` 返回值，顺序严格解释为 `width、height、left、top`；
4. 两条 Origin 原生路径必须互相一致，并且仍要符合当前模板的页面与边距合同。

只有第 2、3 条一致时，异常 bridge 值才会作为诊断信息保留而不再误伤绘图。任一原生路径缺失、
非有限、单位错误或彼此矛盾，EditaPlot 仍会停止，不会用“兼容模式”掩盖真实布局问题。

如果你之前遇到同样报错，请在仓库根目录更新最新版并重新同步 Skill：

```powershell
git pull --ff-only origin main
.\editaplot.cmd setup
.\editaplot.cmd doctor
```

然后用同一份原始数据重新运行。不要修改 Origin、注册表或 DCOM，也不需要管理员权限。如果仍然
失败，请停止重复尝试，只把 EditaPlot 显示的失败阶段、短错误代码和 Origin 产品版本发给我；
公开截图前请遮住所有与技术故障无关的信息和本地路径。

本修复已经在 2024b / 10.15 完成新的隔离 smoke 回归，OPJU、PNG、PDF、TIF、图层/轴反读和视觉
检查均通过。它解决的是已定位的跨版本读回问题，但在 2026b 主机重新产出完整证据前，我不会把
2026b 写成新的“完整实机基线”。

## 已知风险、未知构建和无法解析的版本

版本风险表是一个**探针建议表**，不是黑名单：

- 已知受影响构建会把相关探针提高到高优先级；
- 已知已修复构建仍可在普通优先级运行必要探针；
- 风险记录不会仅凭版本号自动阻断绘图；
- 真正决定能否运行的是实际能力和输出证据。

如果构建号未知，或者 Automation 可调用但版本返回值无法解析，EditaPlot 会报告
`version_status=unknown`，并运行完整、高优先级能力探针。它不会把未知环境静默写成“已支持”或
“已验证”。

如果连 Automation 握手或版本读取调用本身都失败，则按技术连接失败报告稳定阶段和错误代码，
而不是猜测原因。

## 先区分 Codex 沙箱预检与真实 COM 启动错误

如果新版首先返回 `origin_codex_sandbox_context`，说明当前 Codex 命令运行在隔离账户中，
EditaPlot 已在调用 Origin COM 前停止；这不能证明 Origin、版本、Python 包或数据有问题。我让
Codex 只针对原来的精确 `origin-smoke` 或 `render` 命令发起正式、受限的本地执行申请。只有这次
精确申请获批后，Codex 才可重跑同一条命令；申请可以由你在提示时确认，也可以由已经配置的 Codex
自动审查评估，但审批不保证通过，自动审查也不等于预先授予所有 Origin 命令权限。

这条路线不是绕过沙箱。无需把命令复制到自己的 PowerShell，也不要使用管理员权限、修改 DCOM/
注册表或改走未验证的 Automation 接口。审批被本机或组织策略拒绝时应停止。若报告
`origin_execution_context_unknown`，说明 Windows 执行身份无法验证；它不是一个待审批状态，
同样必须在 COM 前停止，不能根据 `USERNAME` 或 `USERPROFILE` 猜测身份。

只有精确申请获批、命令已经处于可验证的当前用户上下文后，仍然发生的 COM 错误才进入下面的启动
恢复流程。沙箱预检发生在 COM 之前，不消耗后续“瞬时启动错误自动重试”或“用户批准再试”的次数。

## 获批后仍遇到 0x80080005 等启动错误时会怎样

`0x80080005` 表示 COM Server 没有在规定时间内完成启动注册；它本身不能证明是 Origin 版本、
Python 包或数据文件的问题。EditaPlot 会把常见启动错误收敛成短代码：

- `origin_com_unspecified_failure`：对应 `0x80004005`；
- `origin_com_call_rejected` / `origin_com_server_busy`：Origin 暂时拒绝或延后调用；
- `origin_com_disconnected` / `origin_com_server_unavailable`：连接中断或服务暂不可达；
- `origin_com_server_execution_failed`：对应 `0x80080005`；
- `origin_com_class_not_registered`：对应 `0x80040154`；
- `origin_com_activation_access_denied`：对应 `0x80070005`。

对通用或明确可重试的瞬时启动错误，EditaPlot 会先尝试退出可能存在的半启动自有实例；只有清理
调用成功，才自动创建一个全新的隔离实例，最多一次。清理失败会返回
`origin_activation_cleanup_failed` 并停止。成功激活后，它执行 `sec -poc 30` 并用
`run.isOCready()` 确认 Origin C 已就绪，未就绪时不会读取版本或新建项目。类别入口不存在和访问
被拒绝不会自动循环。

如果最初启动与清理同时失败，我只让报告保留四个脱敏字段：
`primary_activation_code`、`primary_activation_stage`、`cleanup_error_code` 和
`cleanup_error_stage`。这些字段不包含 Windows 账户名、本地路径、原始 HRESULT 或原始 COM
异常文本，也不会因为同时存在两组诊断而继续自动重试。

如果两次自动尝试都失败，EditaPlot 会停止并保留脱敏兼容报告。只有用户同意后，才允许在同一
活动 Windows 用户上下文再执行一次；新的 smoke 必须使用新的空白同级输出目录，不能覆盖第一次
的诊断。它不会切换到 `ApplicationSI`、自动改 DCOM/注册表或把管理员模式作为普通用法。它也不会
仅凭经过时间就强杀可能正在管理隐藏 Origin 的 Python worker；长时间无进度时应先保留报告并定位
最后阶段。

smoke 或正式绘图失败时，Python 预览以及单独生成的 PNG/PDF/SVG 只能算预览，不能写成
“Origin 已完成”。正式完成仍须同时具备 OPJU、PNG、PDF、TIF、对象反读和人工视觉检查。

## 为什么 2025b 以后更需要反读

OriginLab 官方说明，Origin 2025b 调整了图页比例、边距、字体呈现、轴框、线宽和刻度标签自动旋转
等默认值。因此 EditaPlot 对关键尺寸和文本采用显式合同，并以对象反读和最终视觉结果验收，而不是
依赖某个版本的默认主题。

## 公开 GitHub 项目调研结论

本轮公开项目调研中，最直接、可核查的参考是 OriginLab 的
[`originlab/Python-Samples`](https://github.com/originlab/Python-Samples)。它提供使用
`originpro` 控制 Origin 的代码示例，适合核对调用方式。

但示例仓库不是一个替代实机验证的通用跨版本兼容层。本轮没有找到能够跳过握手、模板能力探针和
真实产物验证、同时可靠覆盖 2021–2026b 的公开方案。这个结论只描述本轮可核查调研结果，并不声称
互联网上绝对不存在其他实验项目。

## 普通用户只需要看什么

运行前不必自己判断构建号。把数据交给 EditaPlot 后，重点看三类结果：

- `verified`：当前环境与路线拥有完整证据；
- `compatible_unverified`：握手和所需能力通过，但尚未成为完整实机基线；
- `unknown`：产品或构建无法可靠归类，正在或需要运行完整探针。

如果探针失败，报告应指出失败阶段和受影响能力；不会用一大段版本术语淹没初次使用者。

## 官方与公开来源

- OriginLab External Python：
  <https://docs.originlab.com/externalpython/>
- OriginLab Automation 实例差异：
  <https://docs.originlab.com/com/difference-of-application-applicationsi-and-applicationcomsi/>
- Origin / OriginPro 官方版本与构建历史：
  <https://www.originlab.com/index.aspx?pid=3325>
- Origin 2025b 图形默认值变化：
  <https://docs.originlab.com/quick-help/why-graph-looks-different-in-2025b/>
- OriginLab Python Samples：
  <https://github.com/originlab/Python-Samples>
