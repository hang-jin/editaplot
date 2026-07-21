# 三维多条件 Nyquist 轨迹数据合同

- 只接受长表：每行必须包含一个 `Zreal`、一个真实第三变量、一个 `-Zimag` 和一个 `Series`。
- `Zreal` 与 `-Zimag` 是数值坐标；软件不改变符号、不拟合、不平滑、不插值。
- 第三变量必须来自用户数据，并在表头同时写明科学含义与单位，例如
  `Condition Position (mm)`、`Temperature (K)` 或 `Concentration (mg/mL)`；`Y`、`Index`、
  `Condition 1` 等无单位装饰性坐标不合格。
- `Series` 是稳定的轨迹标识，按源表首次出现顺序保留，支持 1–6 组；每组至少两个完整 XYZ 点。
- 原文件保持只读。渲染器只在 Origin 工作簿中按 Series 创建 XYZ helper columns，并在验收报告中列出映射。
- 任何角色、第三轴语义或单位不明确时都需要人工确认或修改一份工作副本。
