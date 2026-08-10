# 预计算 SHAP 复合图数据合同

- 必需列：特征名、外部预计算 SHAP 值、数值型原始特征值。
- 可选列：Sample ID、Feature Order、Mean absolute SHAP、Feature Group、Group contribution (%)；均兼容中英文列名。
- 每行对应一个样本-特征观测；至少 2 个特征，每个特征至少 3 行完整数据。
- 默认特征显示顺序严格采用输入中首次出现顺序；只有用户明确提供 Feature Order 时才按该列排序。
- SHAP X 值逐项原样保留；确定性纵向 beeswarm 只为减少点遮挡。
- Feature value 只在同一特征内部做 min-max 映射以控制低蓝高红颜色；常数列映射到 0.5。
- 未提供 Mean absolute SHAP 时，只允许对已提供的 SHAP 行执行 `mean(abs(SHAP))`；该派生项会进入语义确认清单，未经确认不冻结绘图计划。
- 分组 Profile 需要每个特征唯一对应 1 个 Feature Group，共支持 2–5 组。若未提供 Group contribution (%)，只允许按组汇总 Mean |SHAP| 并归一到 100%，同样必须确认。
- Feature Order 与 Mean absolute SHAP 可按每个特征只填写 1 个单元格，Group contribution (%) 可按每组只填写 1 个单元格；同一特征或同一组的多个非空值必须一致。
- 纵向防遮挡偏移与特征内颜色归一化都是仅用于显示的 helper，具有明确 lineage，也会进入派生项确认清单；它们不会改写 SHAP 横坐标或原始特征值。
- 用户提供的 Mean absolute SHAP 或组贡献必须与逐行 SHAP 数据一致；不一致时失败关闭，不会悄悄选用其中一套。
- 当前复合布局版本为 `shap-composite-layout-v1`；该版本随 SHAP 计划一同冻结并进入计划摘要，布局合同变化后旧绘图计划不会被静默复用。
- Skill 不训练模型、不调用 SHAP 库、不推断解释、不修改或补造源数据。
