# 中文快速开始

1. 让用户说明图想证明什么，并提供只读数据文件。
2. 运行 doctor；仅在允许时修复项目级 Python 依赖。
3. inspect 数据：列数、列名、数值/分类、缺失值、单位和 domain signals。
4. recommend 最多三种图，说明推荐理由、被拒绝方案和需要确认的歧义。
5. 运行 palettes 并展示中文卡片；结合组数、色盲、灰度打印推荐两套。
6. 用户确认图形、列映射、轴标题、误差、顺序、显示变换、palette ID 和一句核心结论。
7. 生成 hash-bound RenderPlan，禁止手改计划文件。
8. 用户确认官方 Origin 已手动正常启动后再 render。
9. verify OPJU/PNG/PDF/TIF、源 hash、对象反读和字体；最后人工查看图。

推荐提示词：

```text
请使用 $editaplot。先 doctor，再只读检查我的数据。最多推荐 3 种图，并把列角色、
单位、误差和低置信度问题说清楚。展示中文科研配色卡，结合组数和灰度打印推荐 2 个 palette_id。
我确认后再冻结计划；不要修改源数据，不要静默拟合或计算。Origin 成图必须保留可编辑窗口、
OPJU/PNG/PDF/TIF、对象反读和人工视觉检查。
```
