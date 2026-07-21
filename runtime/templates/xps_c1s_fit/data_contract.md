# XPS C 1s CSV 数据合同

第一版固定列名，不做自动识别。CSV 必须包含以下数值列：

| 列名 | 含义 |
|---|---|
| `BindingEnergy` | 结合能，单位 eV |
| `Raw` | 原始实验散点 |
| `Background` | 背景曲线 |
| `Envelope` | 总拟合曲线 |
| `Peak_CC` | C-C / C=C 分峰 |
| `Peak_CO` | C-O 分峰 |
| `Peak_CeqO` | C=O 分峰 |
| `Peak_OCeqO` | O-C=O 分峰 |

规则：

- 所有列必须为数值。
- 不允许重复列名。
- 允许完整空行，程序会清理并在 `validation_report.json` 记录 warning。
- `BindingEnergy` 会按升序整理后写入 Origin；Origin 图中使用反向 XPS 显示。
- C 1s 典型范围建议覆盖约 280–292 eV；明显超出时给 warning。
