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
