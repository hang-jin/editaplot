# 森林图数据合同

- 每行一个对象，必须显式提供 Label、Estimate、CI Low、CI High。
- 每行必须满足 `CI Low <= Estimate <= CI High`。
- 可选 Reference 列的非空值必须完全一致；缺失时不画参考线。
- 区间 helper 只在 Origin 工作簿中生成，源文件保持不变。
