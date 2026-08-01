# Showcase policy

Create demonstration data and figures that show capability without copying manuscript-specific
data, labels, conclusions, or private template assets.

## Rules

- Use neutral deterministic synthetic data and label it as teaching data.
- Include English and Chinese header examples.
- Cover sparse/dense, realistic small series counts, long labels, error definitions, and ambiguous cases.
- Keep the source table next to each gallery output.
- Generate gallery figures through the same Origin renderer used by customers.
- Run the isolated pre-render `origin-smoke` before a formal gallery render.
- Keep OPJU, PNG, PDF, TIF, plan, validation, and readback for every verified showcase entry.
- Do not use a Python-only mock image as evidence that an Origin route works.

## Current verified public gallery scope

The retained verification inventory contains 47 reviewed, metadata-sanitized PNGs across 40 public
plotting routes. The public page displays 45 cases. Keep inventory count, display count, and route
count separate: a case enters the inventory only after Origin artifacts, object readback, human
visual QA, sanitized PNG, provenance record, and asset manifest all pass. Display visibility is a
separate decision and does not delete retained verification evidence.

1. XPS scan and multi-component fit.
2. XRD multi-series spectrum.
3. EIS Nyquist example.
4. Dense scatter with several groups.
5. Grouped bars with explicit error columns, horizontal bars with long labels, and signed diverging effects.
6. Absolute and percent stacked compositions.
7. Error trend with explicit SD/SEM.
8. A four-stage Sankey flow.
9. Flat pie with a small category count.
10. Ordered multi-series progression trend.
11. Comparable multimetric radar profile.
12. Dense 30×30 category × series heatmap with sparse labels and a detached colorbar.
13. Raw observations with deterministic jitter and median lines.
14. Violin distributions with editable box summaries.
15. Frozen-bin univariate histogram.
16. Forest effect estimates with explicit intervals and a reference line.
17. Indexed-size bubble relationship with a verified 16 pt mapping note.
18. CV, LSV, XAS, steady-state PL, TRPL with user-supplied fits, and UV-vis with a user-supplied Tauc inset.
19. Medical ROC, PR, calibration, DCA, confusion matrix, Bland-Altman, paired trajectories,
    grouped box/raw observations, Raincloud, and precomputed SHAP evidence.
20. A multi-panel circular directed weighted network with shared node positions, signed edges, one
    global weight scale, and a borderless editable legend; the current showcase fixture uses two
    periods.
21. A 3D dual-density ridgeline over four real, unit-bearing follow-up conditions, with paired
    upstream density profiles and one supplied Z=0 baseline locator per condition.

## Newly verified materials and dense-matrix cases

On the Origin 2024b baseline, DSC, NMR, FTIR/IR, XPS multi-spectrum comparison, multi-condition PL,
multi-sample UV–Vis, and the dense 30×30 heatmap have produced editable OPJU plus PNG/PDF/TIF and
passed programmatic readback, SHA-bound human visual QA, and the sanitized public-asset audit.

The public gallery displays only the real Origin-rendered 30×30 dense heatmap. It keeps the full
900-value matrix, hides cell numbers, thins only axis labels, and detaches the colorbar. The smaller
annotated matrix and 40×40 teaching case remain in the retained verification inventory for
regression and audit history, but they are not public-page showcase cards.

The all-in-one poster is an archived promotion asset. It is not embedded in the live bilingual
gallery and is not required to include every newly added verified case.

## 我已验证的三维双密度教学案例

我已经准备了一份原创、确定性的 mixed-wide 教学表：
`examples/gallery/density_ridgeline3d.csv`。四个带单位随访条件各自包含同行、同密度语义和单位的
实线/虚线预计算密度，并且每组只有一个上游提供的 `Focal X`；它只作为 Z=0 基线 locator。
生成器可以重复产生完全相同的数据，不会运行用户数据的 KDE、阈值或交点计算。

该案例已经完成真实 Origin OPJU、PNG/PDF/TIF、完整对象反读和与导出哈希绑定的人工视觉检查，
现登记在 `CASES`，进入公开 verified 路线与页面展示。公开图必须来自同一 Origin renderer；
我仍不会用 Python mock 图代替 Origin 成果。

Add experimental chart images only under an explicit experimental label.

Keep high-series-count cases in automated pressure tests, not in the public hero gallery.
