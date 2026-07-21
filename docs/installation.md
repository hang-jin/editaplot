# 安装与环境自检

## 人工前置条件

1. Windows 10/11。
2. Python 3.10 或更高版本。
3. 用户自行合法安装、激活的 Origin/OriginPro；项目测试基线为 2024b / 10.15。
4. 用户必须先手动正常启动 Origin。Codex 不代替用户处理安装、授权或激活。

## Doctor

```powershell
<python-3.10+> skill/editaplot/scripts/editaplot.py doctor --engine-home <engine-root>
```

Doctor 将 Python、Windows、引擎和每个 Python 包分开报告。`ready_for_analysis` 与
`ready_for_render` 不能混为一谈；`originpro` Python 包存在也不等于 Origin 程序和许可证有效。

## 项目级自动修复

仅当 `automatic_repair.available=true` 时运行：

```powershell
<python-3.10+> skill/editaplot/scripts/editaplot.py doctor --repair --engine-home <engine-root>
```

修复过程：

- 在 `<engine-root>/.editaplot-venv` 创建隔离环境；
- 只安装 `requirements-runtime.txt` 的精确直接版本，并使用 `requirements-runtime.lock` 约束
  全部传递依赖；
- 不使用 shell 拼接，不接受任意包名，不做全局 pip 安装；
- 不安装、启动、修改、破解或激活 Origin；
- 返回 managed `python_executable`，调用方必须用它再次运行 doctor。

自动修复锁已在 CPython 3.10.x / Windows 验证。更高 Python 版本仍可在依赖完全匹配时运行分析，
但不会自动安装未单独验证的环境。Python 版本过低、非 Windows、引擎缺失、Origin 应用缺失、
许可证或人工启动失败都需要人工处理；Codex 不得伪造 ready 状态。
