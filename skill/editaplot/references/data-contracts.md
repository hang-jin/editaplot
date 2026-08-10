# Data contracts

## Accepted source files

- UTF-8 CSV or TXT with comma, tab, or semicolon delimiter.
- XLS or XLSX using the first worksheet containing a valid rectangular table.
- Non-empty unique headers. A verified univariate route may accept one column; multivariate routes
  enforce their own minimum column count.
- Finite numeric values for plotted numeric roles.

Keep the original file read-only.

These contracts cover the 40 registered public plotting routes. The data contract is independent
of the installed Origin version. After semantic confirmation and plan creation, run the isolated
`origin-smoke` before formal rendering. Rendering starts a dedicated EditaPlot-owned Origin
instance and then checks the selected template against the detected host. Target Origin/OriginPro
versions are 2021–2026b; 2024b / 10.15 is the only current fully verified baseline, so never turn
a successful installation discovery into a claim that every route is verified on that host.

For an ordinary render, omit `--output-dir`. Create the formal
`<source_stem>_EditaPlot_<timestamp>` directory beside the original CSV/TXT/XLS/XLSX source and
place the RenderPlan, OPJU, PNG, PDF, TIF, readback, validation, and provenance there. Use another
destination only after an explicit user request.

## Recognized layouts

### Numeric XY wide table

First numeric column is a candidate X; remaining numeric columns are candidate series. Typical
uses: spectra, ordered trends, scatter, CV/LSV, XRD, XAS.

### Category wide table

First category column plus one or more numeric series. Typical uses: grouped bar, horizontal bar,
stacked bar, percent stacked, radar, heatmap, and pie when exactly one numeric series is present.

For radar, require at least three metric rows and two nonnegative object series; different units must
already be made comparable or explicitly confirmed. For heatmap, require at least two row labels and
two numeric columns. EditaPlot does not silently normalize radar values or reorder heatmap rows.
For dense matrices, keep every value and the original row/column order, hide per-cell numbers, thin
only display labels while preserving both endpoints, and place the colorbar outside the data field.
The real Origin-rendered 30×30 case has passed OPJU/PNG/PDF/TIF, axis/colorbar readback, and
hash-bound human visual review and is the only heatmap displayed in the public gallery. The smaller
annotated matrix and 40×40 case remain retained regression evidence. Sizes beyond the verified
contracts must not be described as fully Origin-verified until their complete artifact and human
visual gates pass.

### Error wide table

X or category column plus value/error pairs. Recognize suffixes such as `_SD`, `_SE`, `_SEM`,
`_err`, `标准差`, `标准误`, and `误差`. Require the error meaning to be explicit or confirmed.

### Edge list

`source`, `target`, and positive numeric `value` columns, including Chinese aliases. Use for Sankey.

### Panelled directed weighted edge list

Use one row per directed edge with required `Panel`, `Source`, `Target`, and strictly positive
finite `Weight` columns. Optional `Sign` records only supplied `positive`, `negative`, or `neutral`
semantics; optional `SourceGroup` and `TargetGroup` must appear together and assign every repeated
node to one globally consistent group. At most four node groups are accepted until a verified
redundant shape/texture encoding exists. Optional `EdgeLabel` remains user text; panels with more
than 12 edges retain the source labels but hide them in the figure to avoid unreadable annotation
collisions.

The confirmed first-appearance order fixes 1–4 panels and shared node positions. EditaPlot maps all
weights through one global 1.2–4.2 pt display-width scale without changing the source values. It
rejects self-links and duplicate `Panel + Source + Target` rows and does not calculate causality,
correlation, centrality, significance, missing edges, or a sign from the weight.

### Raw distribution wide table

One or more raw numeric group columns. `raw_summary` preserves every observation and shows the
median; `violin` adds a density-shaped editable Origin object; `histogram` accepts raw continuous
values and uses a frozen Freedman-Diaconis-derived nice-width bin plan shared by preview and Origin.
Do not upload precomputed histogram bar heights as raw observations.

`raincloud` uses the same immutable wide raw observations but requires at least five values per
group. The verified Origin `Box_HalfViolin` object displays a half violin, all raw points, and a
compact mean ± 1 SD. Density and summary are display objects; no source values are overwritten.

### Grouped box raw-data wide table

Use one raw-observation column per box and name each header `Category | Group`, for example
`Low LPS | WT` and `Low LPS | Mutant`. Missing tails are allowed, so boxes may have different n.
EditaPlot calculates only the box summary needed by Origin, overlays every supplied raw point,
and labels each box with the exact non-empty count as lowercase `n=`. Category labels and legend
labels are copied verbatim from the two header parts; placeholders such as `N1` are forbidden.
When exact axis wording is needed, pass user-confirmed `--x-title` and `--y-title` values during
planning. These titles are frozen into the plan digest and applied to preview and Origin without
editing the source table. It does not calculate p-values or add significance brackets/stars.

### Precomputed SHAP long table

Use `Feature`, `SHAP value`, and numeric `Feature value`. Optional columns are `Sample ID`,
`Feature Order`, `Mean absolute SHAP`, `Feature Group`, and `Group contribution (%)`; bilingual
aliases are accepted. Provide at least two features and three complete observations per feature.
Without `Feature Order`, figure order is the first appearance order in the source, not a silently
calculated ranking. Every SHAP X value is preserved. Origin-only helper columns add deterministic
vertical collision reduction and within-feature min-max color values; a constant feature maps to
0.5. Both display helpers have explicit lineage and require approval.

The default profile adds Mean |SHAP|. If the summary column is absent, EditaPlot may calculate only
`mean(abs(SHAP))` from the supplied rows and records that exact derivation for confirmation. A
grouped profile requires one Feature Group per feature (2–5 groups); an absent group percentage may
be derived as `100 × sum(group feature Mean|SHAP|) / sum(all feature Mean|SHAP|)`, again only after
confirmation. Summary cells may be sparse—one value per feature or group is enough—but repeated
non-empty values must agree. Provided summaries are checked against the row-level values.
EditaPlot does not train a model, invoke SHAP, invent contributions, or send data to a network.

### Explicit interval table

One label column plus `Estimate`, `CI Low`, and `CI High`, with an optional constant `Reference`
column. Use for forest plots. EditaPlot never invents missing confidence limits or a null value.

### Indexed-size XY table

One numeric X column, one numeric Y/response column, and one strictly positive Size column. Use for
bubble plots. The source Size values remain unchanged; only the editable Origin symbol areas encode
them.

### Medical diagnostic coordinates

ROC uses `FPR` plus one or more precomputed TPR/model columns. Precision-recall uses `Recall`, one
or more precomputed Precision/model columns, and one constant `Prevalence` column. All probability
coordinates stay in 0–1. EditaPlot does not derive curves, AUC/AUPRC, confidence intervals, or
DeLong tests from case-level labels and scores.

### Precomputed calibration bins

Use `Predicted probability`, `Observed fraction`, and nonnegative `Bin count`. Each row is one
upstream-computed bin. The editable Origin helper scales Bin count to the bottom 12% of the plotting
field for display only; the source remains unchanged. EditaPlot does not silently bin, smooth,
or calculate calibration slope, intercept, Brier score, or confidence intervals.

### Precomputed decision curve

Use `Threshold`, at least one model net-benefit column, and explicit `Treat all` and `Treat none`
columns. Thresholds stay in 0–1. The model evidence window may clip an extreme Treat-all tail and
will report that display decision; all source values remain editable in the Origin workbook.

### Classification count matrix

The first categorical column is Actual class; each numeric column is one Predicted class. Counts
must be nonnegative. EditaPlot preserves the orientation and does not normalize rows or columns.

### Agreement and paired trajectories

Bland-Altman V1 requires `Mean`, `Difference`, and constant `Bias`, `Lower LoA`, `Upper LoA`
columns. Paired/longitudinal V1 requires numeric `Visit` and one stable subject per column.
EditaPlot never infers method pairs, LoA, subject identity, missing visits, or interpolation.

### Domain spectroscopy/electrochemistry

Use semantic headers and units, not only numerical range, to distinguish XPS, XRD, XAS, FTIR/IR,
NMR, DSC, PL, UV–Vis, EIS, CV, and LSV. Ask when `Energy + Intensity`, `Temperature + Signal`,
or `Wavelength + Intensity` is scientifically ambiguous.

XPS has separate single-spectrum fitting and multi-spectrum comparison routes. `xps_compare`
requires one Binding Energy column and at least two independently named measured
Intensity/Counts/Experimental series on the same sampling axis. Background/Baseline, Envelope/Fit,
Residual, Component, and Peak columns are not independent samples: send a fit table to the XPS fit
route, or retain those columns without rendering after confirmation. Comparison uses direct overlay
by default; any new vertical offset requires explicit confirmation and may exist only as an
Origin helper column. Keep the source values and row order unchanged, and display binding energy
from high to low.

XRD has two modes. Ordinary scans use one 2θ/X coordinate and one or more intensity series.
Rietveld refinement requires X plus explicit Observed and Calculated columns; Background,
Difference, and sparse Phase reflection-position columns are optional visible elements. GSAS-II
Powder CSV may contain metadata records before `x,y_obs,weight,y_calc,y_bkg,Q`. GSAS-II Publication
CSV may contain `Used,Obs,Calc,Bkg,Diff`, named Phase columns, `tick-pos`, `diff/sigma`, and
`Axis-limits`. Preserve `weight`, Q/alternative coordinates, masks, diagnostics, and control
columns without drawing them as intensity curves. Publication `Diff` is already positioned by the
exporter and must be drawn directly without another offset. Never infer phases, reflections, fit
metrics, a missing difference, or background.

FTIR/IR requires `Wavenumber` with a unit such as `cm^-1` plus one or more comparable Absorbance or
Transmittance series. Preserve series order and show wavenumber from high to low. Do not correct
baselines, smooth, normalize, label peaks, calculate peak areas, or infer functional groups.

NMR requires `Chemical Shift (ppm)` plus one or more already processed intensity series. Preserve
series order and show chemical shift from high to low. Do not perform Fourier transform, phase or
baseline correction, solvent removal, integration, peak picking, coupling analysis, assignment, or
quantitation.

DSC requires `Temperature` with a unit plus one or more comparable `Heat Flow` series. Confirm the
endothermic/exothermic up/down convention and retain the source sign. Do not infer Tg, Tm, Tc,
onset, peak temperature, enthalpy, or crystallinity. Temperature alone does not establish DSC.

PL accepts either `Wavelength` plus one or more PL intensity columns, or `Time` plus observed
decay columns. Multi-sample and ordered multi-condition wide tables preserve source column order.
A fit column must repeat the observed-series name and add `Fit`/`拟合`; it remains a user-supplied
curve. TRPL uses a logarithmic Y axis and rejects nonpositive plotted values.

UV–Vis accepts `Wavelength` plus one or more comparable Absorbance or Transmittance series and
preserves their source order. Do not mix Absorbance and Transmittance on one Y axis without an
explicit user-approved axis contract. A Tauc inset is added only when the table also supplies
Photon energy and Tauc value. Optional Tauc fit and Band gap columns are drawn exactly as supplied.
EditaPlot does not convert wavelength to photon energy, choose a Tauc exponent, fit a line, or
calculate Eg.

### Verified 3D multi-condition Nyquist trajectory

Use one immutable long table with exactly four plotted roles: explicit `Zreal`, a numeric real
experimental variable whose header includes both meaning and unit (for example `Condition Position
(mm)` or `Temperature (K)`), explicit supplied `-Zimag`, and `Series`. Each row is one XYZ point;
Series preserves first-appearance order and identifies 1–6 trajectories, each with at least two
complete points. EditaPlot may split the long table into XYZ helper triplets only inside the
editable Origin workbook. It does not invent a third axis, negate a generic Z column, fit an
equivalent circuit, interpolate, or add resistance annotations. Generic `X/Y/Z`, an index-only Y,
or a third-axis header without a unit is insufficient.

### 我已验证的三维双密度 mixed-wide 表

对于 `density_ridgeline3d`，我只接受六个明确角色：`Condition ID`、带科学含义和单位的
`Condition Position`、带科学含义和单位的 `Density X`、同为非负有限数且使用一致密度语义/
单位的 `Solid Density` 与 `Dashed Density`，以及稀疏 `Focal X`。同一行同时提供两列密度；
不接受拆成 `Profile`/`Line Role` 的另一套长表格式。

我要求 2–6 个条件；每个 ID 与一个真实 position 一一对应，每组至少 5 行，X 按源顺序严格
单调。每组 `Focal X` 必须恰好一行非空并落在本组 X 范围内，其余行留空。焦点只显示在
`Z=0` 基线上，不代表软件推断的峰、阈值、交点或最优点。用户必须在上游提供两列预计算密度
和焦点；我不会在绘图流程中运行 KDE、平滑、插值、归一化或焦点计算。该路线已在 Origin
2024b / 10.15 基线上完成 OPJU、PNG/PDF/TIF、对象反读和人工视觉验收；其他主机仍须通过
实时 smoke 与 `OPEN_GL_3D` 能力检查。

## Repair guidance

When a file is invalid, explain the smallest source-side change the user should make, but do not
edit the source without explicit permission. Provide a new working copy or blank example when requested.

- Duplicate/empty headers: rename columns uniquely.
- Mixed notes and data: move notes outside the rectangular table.
- Unknown XRD numeric/control columns: explain their scientific purpose and confirm an explicit
  `support` or `ignored` mapping; do not let them become ordinary intensity series by position.
- Unknown error columns: rename with an explicit SD/SE/SEM/custom suffix.
- Sankey wide matrix: convert to source-target-value edge rows in a new copy.
- Panelled network without explicit Weight or with negative Weight: provide a positive magnitude in
  `Weight` and, if scientifically supplied, put relationship polarity in a separate `Sign` column.
  Do not collapse panels into one Sankey or infer a sign from a negative line width.
- Radar with mixed physical units: provide a user-approved normalized copy or choose small multiples.
- Heatmap in long form: pivot to one row-label column plus numeric series in a new working copy.
- Dense heatmap with unreadable text: keep the matrix unchanged and let the dense layout thin axis
  labels and hide cell numbers; do not downsample or manually delete rows/columns just for display.
- Histogram bar heights: provide the underlying raw numeric observations instead.
- Forest table without interval limits: calculate and label the limits upstream; EditaPlot will not
  infer them.
- Bubble table with zero/negative Size: provide a scientifically valid positive magnitude or choose
  ordinary scatter.
- PR table without Prevalence: calculate and add the cohort prevalence upstream.
- Calibration case-level predictions: bin and validate them upstream, then export the three-column
  calibration contract.
- Decision data without Treat-all/Treat-none: calculate all net-benefit curves upstream and label
  the two reference strategies explicitly.
- Confusion matrix already normalized: label the values clearly; EditaPlot will not infer whether
  percentages are row- or column-normalized.
- Bland-Altman raw method pairs: calculate Mean, Difference, Bias and LoA upstream.
- Long paired table: pivot a working copy to Visit × stable-subject wide format without changing the
  source file.
- Precomputed group means instead of raw observations: provide the underlying values for Raincloud,
  or choose a bar/interval route with explicitly defined uncertainty.
- Grouped-box headers without `Category | Group`: rename a working copy so category and subgroup
  semantics are explicit; do not infer significance from the observations.
- PL observed traces without paired fit columns: draw the observations only, or provide upstream
  fit columns whose names pair unambiguously with the observed series.
- UV–Vis without complete precomputed Tauc inputs: draw the main spectrum without an inset, or add
  upstream Photon energy and Tauc value columns; add a user-supplied Tauc fit/Eg only when available.
- XPS comparison with fit/background/residual/component columns: use the XPS fit route or confirm
  those columns as retained without rendering; do not rename them into samples.
- FTIR/IR or NMR with unknown numeric metadata: give those columns explicit experimental meaning
  and units, or confirm them as retained without rendering.
- DSC without a clear heat-flow convention: state the endothermic/exothermic direction and unit
  before planning; do not let the drawing layer infer it from curve shape.
- Missing SHAP values or feature values: calculate/export a complete long table upstream; the
  drawing layer will not run a model or impute explanations.
- Raw instrument binary: export or preprocess to a supported rectangular table first.
- 3D trajectory without a meaningful/unit-bearing third axis: add the real experimental variable
  and unit to a working copy; never use Series order or row number as decorative depth.
