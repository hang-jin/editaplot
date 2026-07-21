# 三维多条件 Nyquist 轨迹视觉合同

- 使用 Origin 2024b 官方 `plotxyz ... plot:=240 ogl:=<new template:=glTraject>` 路线。
- X 为 `Zreal`，Y 为用户提供且带单位的真实实验变量，Z 为用户提供的 `-Zimag`；三轴标题直接保留输入表头。
- 1–6 条轨迹使用克制的定性配色；颜色只通过已验证的 `set -c` 设置，线宽只通过已验证单位的 `set -w` 设置。
- 默认保留 `glTraject` 的可编辑轨迹对象；不写入未经隔离验证的符号、填充、More Colors 或 LabTalk 属性。
- 页面约 24 × 18 cm，Arial；轴标题 22 pt、刻度 18 pt、线宽 2.2 pt，并进行 Origin 对象反读。
- Y 轴本身编码条件值，因此默认移除冗余图例。相机角度沿用已通过视觉验收的官方模板默认值，不伪造二维投影。
- 交付必须包含可编辑 OPJU、PNG、PDF、TIF、三轴/相机/XYZ 映射/颜色/线宽反读与人工视觉检查。
