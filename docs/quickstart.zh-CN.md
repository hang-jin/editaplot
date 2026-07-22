# 中文快速开始

## 30 秒版本

前提：Windows 10/11 x64 实体电脑、64 位 CPython 3.10–3.12，以及本机可由 Automation 调用的
Origin/OriginPro。CLI/依赖覆盖三个 Python 版本，真实 Origin 端到端基线为 CPython 3.10
和 Origin 2024b。macOS、Linux、WSL、Wine/CrossOver、Parallels 与其他虚拟机不支持。

安装时必须下载**完整仓库**，在仓库根目录运行：

```powershell
.\editaplot.cmd setup
```

不要只复制 `skill/editaplot`，那样没有绘图 runtime。会 Git 的用户可以 `git clone`；不会 Git
或没有 GitHub 账号的用户可以下载 Source ZIP 并完整解压。完整步骤见[安装指南](installation.md)。
启动器会先复用已有的 64 位 CPython 3.10–3.12；若完全没有兼容 Python，Skill 必须说明这是
系统级变更并征得明确同意，才可通过官方 winget 以用户范围安装 Python 3.12。Origin 永不自动安装。

然后把 CSV、TXT、XLS 或 XLSX 拖进 Codex，只说这一句：

```text
请使用 $editaplot 帮我画这份数据。自动检查环境并只读识别数据，推荐合适图形；
先让我确认一句科学目的，只有含义不明确时再追加问题。不要修改源文件，也不要补造、
静默拟合或计算数据。
```

命令行用户可以运行：

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

## Skill 会替新手处理什么

1. 检查平台、兼容 Python、项目级依赖和本机 Origin 应用；缺 Python 时先征得安装许可。
2. 只读识别列名、列数、单位、数据类型、缺失值和可能的科研语义。
3. 根据问题与数据结构推荐最多三种图，并展示合适的中文配色选择。
4. 总会请你确认一句科学目的；只在列角色、误差、归一化、排序、双轴等含义不明确时追加问题。
5. 冻结不改源数据的绘图计划；render 直接测试本机 Origin Automation 连接并绘制。
6. 导出 OPJU、PNG、PDF、TIF，并检查源 hash、轴、字体、图层、对象反读和人工视觉效果。

你不需要看到一串 `inspect → recommend → plan` 的工程术语。Codex 应把它们放在后台，
对你只说清楚：“识别到了什么、建议怎么画、还有哪一点需要你决定”。

## 需要正式绘图时

```text
请使用已确认的方案直接调用本机 Origin 绘制，保留可编辑 Origin 窗口，导出 OPJU、PNG、PDF、
TIF，并完成轴、字体、图层、数据映射反读和人工视觉检查。若连接失败，只报告技术错误；不要只看
PNG 就汇报成功。
```

原始文件始终只读。缺少的数据列不会被补造；helper columns 只能存在于内存或可编辑 Origin 工作簿。
