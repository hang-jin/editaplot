# Data contracts

## Accepted source files

- UTF-8 CSV or TXT with comma, tab, or semicolon delimiter.
- XLS or XLSX using the first worksheet containing a valid rectangular table.
- Non-empty unique headers. A verified univariate route may accept one column; multivariate routes
  enforce their own minimum column count.
- Finite numeric values for plotted numeric roles.

Keep the original file read-only.

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

### Error wide table

X or category column plus value/error pairs. Recognize suffixes such as `_SD`, `_SE`, `_SEM`,
`_err`, `标准差`, `标准误`, and `误差`. Require the error meaning to be explicit or confirmed.

### Edge list

`source`, `target`, and positive numeric `value` columns, including Chinese aliases. Use for Sankey.

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

Use `Feature`, `SHAP value`, and numeric `Feature value`; `Sample ID` is optional and ignored by
the drawing route. Provide at least two features and three complete observations per feature.
Figure order is the first appearance order in the source, not a silently calculated importance
ranking. Every SHAP X value is preserved. Origin-only helper columns add deterministic vertical
collision reduction and within-feature min-max color values; a constant feature maps to 0.5.
EditaPlot does not train a model, invoke SHAP, infer contributions, or send data to a network.

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

Use semantic headers and units, not only numerical range, to distinguish XPS, XRD, XAS, EIS,
CV, and LSV. Ask when `Energy + Intensity` is scientifically ambiguous.

XRD has two modes. Ordinary scans use one 2θ/X coordinate and one or more intensity series.
Rietveld refinement requires X plus explicit Observed and Calculated columns; Background,
Difference, and sparse Phase reflection-position columns are optional visible elements. GSAS-II
Powder CSV may contain metadata records before `x,y_obs,weight,y_calc,y_bkg,Q`. GSAS-II Publication
CSV may contain `Used,Obs,Calc,Bkg,Diff`, named Phase columns, `tick-pos`, `diff/sigma`, and
`Axis-limits`. Preserve `weight`, Q/alternative coordinates, masks, diagnostics, and control
columns without drawing them as intensity curves. Publication `Diff` is already positioned by the
exporter and must be drawn directly without another offset. Never infer phases, reflections, fit
metrics, a missing difference, or background.

PL accepts either `Wavelength` plus one or more PL intensity columns, or `Time` plus observed
decay columns. A fit column must repeat the observed-series name and add `Fit`/`拟合`; it remains a
user-supplied curve. TRPL uses a logarithmic Y axis and rejects nonpositive plotted values.

UV–Vis accepts `Wavelength` plus Absorbance or Transmittance series. A Tauc inset is added only
when the table also supplies Photon energy and Tauc value. Optional Tauc fit and Band gap columns
are drawn exactly as supplied. EditaPlot does not convert wavelength to photon energy, choose a
Tauc exponent, fit a line, or calculate Eg.

### Verified 3D multi-condition Nyquist trajectory

Use one immutable long table with exactly four plotted roles: explicit `Zreal`, a numeric real
experimental variable whose header includes both meaning and unit (for example `Condition Position
(mm)` or `Temperature (K)`), explicit supplied `-Zimag`, and `Series`. Each row is one XYZ point;
Series preserves first-appearance order and identifies 1–6 trajectories, each with at least two
complete points. EditaPlot may split the long table into XYZ helper triplets only inside the
editable Origin workbook. It does not invent a third axis, negate a generic Z column, fit an
equivalent circuit, interpolate, or add resistance annotations. Generic `X/Y/Z`, an index-only Y,
or a third-axis header without a unit is insufficient.

## Repair guidance

When a file is invalid, explain the smallest source-side change the user should make, but do not
edit the source without explicit permission. Provide a new working copy or blank example when requested.

- Duplicate/empty headers: rename columns uniquely.
- Mixed notes and data: move notes outside the rectangular table.
- Unknown XRD numeric/control columns: explain their scientific purpose and confirm an explicit
  `support` or `ignored` mapping; do not let them become ordinary intensity series by position.
- Unknown error columns: rename with an explicit SD/SE/SEM/custom suffix.
- Sankey wide matrix: convert to source-target-value edge rows in a new copy.
- Radar with mixed physical units: provide a user-approved normalized copy or choose small multiples.
- Heatmap in long form: pivot to one row-label column plus numeric series in a new working copy.
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
- Missing SHAP values or feature values: calculate/export a complete long table upstream; the
  drawing layer will not run a model or impute explanations.
- Raw instrument binary: export or preprocess to a supported rectangular table first.
- 3D trajectory without a meaningful/unit-bearing third axis: add the real experimental variable
  and unit to a working copy; never use Series order or row number as decorative depth.
