# Chart selection and support levels

Select from the scientific question first, then check that the data layout supports the choice.
The route list below records template verification on the fully verified Origin 2024b / 10.15
baseline. It is separate from compatibility with the user's current Origin host. After the live
smoke, require the template capability decision for that host; a connected 2021+ installation does
not automatically support every route.

## Verified V1 routes

| Question/evidence | Candidate | Required shape | Cautions |
|---|---|---|---|
| XPS scan or peak fit | `xps` | energy + raw; optional background/envelope/components/residual | Do not invent peaks |
| Diffraction pattern or Rietveld refinement | `xrd` | ordinary: 2theta + intensity series; refinement: X + Obs + Calc, optional Bkg/Diff/explicit Phase positions | Do not add phases or peaks; GSAS Publication Diff is already positioned and must not be offset twice |
| Absorption spectrum | `xas` | energy + absorption series | Do not auto-normalize |
| Impedance response | `eis` | Z real/imag or frequency/magnitude/phase | Confirm Nyquist/Bode and signs |
| Cyclic/linear sweep | `cv`, `lsv` | potential + current series | Preserve acquisition order |
| Category comparison | `bar`, `horizontal_bar` | category + numeric series | Prefer horizontal for long labels |
| Absolute/relative composition | `stacked_bar`, `percent_stacked_bar` | category + >=2 nonnegative series | Confirm denominator for percent |
| Small part-to-whole | `pie` | category + one nonnegative series | Prefer bar when categories are many |
| Relationship | `scatter` | numeric X + numeric Y series | Do not auto-fit or delete outliers |
| Trend with uncertainty | `line_error` | X + value/error pairs | Define SD/SE/SEM/custom |
| Ordered progression without uncertainty | `trend` | ordered numeric X + one or more numeric series | Preserve source order; do not smooth |
| Comparable multimetric profile | `radar` | metric labels + >=2 nonnegative series; >=3 metrics | Confirm scales are comparable; never auto-normalize |
| Category × series result matrix | `heatmap` | row labels + >=2 numeric columns; >=2 rows | Use continuous/diverging color scale and retain color bar |
| Flow | `sankey` | source + target + positive value | Avoid self-links and excessive nodes |
| Preserve every observation | `raw_summary` | one or more raw numeric group columns | Show raw points and an explicit median; do not infer error bars |
| Compare distribution shape | `violin` | one or more raw numeric group columns | Use only when sample density supports a distribution view |
| One-variable frequency distribution | `histogram` | one raw continuous numeric column | Freeze the bin rule; do not add an unrequested fitted curve |
| Effect estimates with intervals | `forest` | label + estimate + CI low + CI high; optional reference | Never infer missing intervals or a null value |
| Relationship with a third magnitude | `bubble` | numeric X + Y + positive Size | Area, not radius, represents Size; preserve a readable mapping note |
| Diagnostic discrimination | `diagnostic_curve` | ROC: FPR + TPR series; PR: Recall + Precision series + constant Prevalence | Use precomputed coordinates; do not silently calculate AUC, CI, DeLong, or smooth |
| Model reliability | `calibration_curve` | Predicted probability + Observed fraction + Bin count | Use precomputed bins; do not silently bin, fit, or calculate calibration statistics |
| Clinical utility | `decision_curve` | Threshold + model net benefit + Treat all + Treat none | Use precomputed net benefit; model evidence window may clip extreme Treat-all tail with warning |
| Classification errors | `confusion_matrix` | Actual-class row label + predicted-class count columns | Do not silently normalize or swap actual/predicted orientation |
| Measurement agreement | `bland_altman` | Mean + Difference + constant Bias + Lower/Upper LoA | Do not infer pairs or calculate limits in the drawing layer |
| Paired/longitudinal stability | `paired_trajectory` | numeric Visit + one stable subject per column | Preserve subject identity; do not pair by row number or interpolate |
| Grouped raw distributions | `grouped_box` | raw columns named `Category | Group` | Preserve category/group text verbatim; show every point and exact n; never invent p-values, brackets, or stars |
| Distribution with raw evidence and compact summary | `raincloud` | one or more raw numeric group columns, at least 5 observations/group | Half violin + all raw points + mean ± 1 SD; do not remove outliers |
| Model feature contribution | `shap_summary` | Feature + precomputed SHAP value + numeric Feature value | Never run SHAP or reorder features; normalize feature value for color only |
| Steady-state or time-resolved photoluminescence | `pl` | Wavelength or Time + PL series; optional explicitly paired Fit columns | TRPL uses log Y; never calculate lifetime or fit curves |
| UV–Vis spectrum with optional Tauc evidence | `uv_vis` | Wavelength + Absorbance/Transmittance; optional Photon energy + Tauc value/fit/Eg | Never calculate photon energy, exponent, fit, or band gap |
| Multi-condition 3D Nyquist trajectory | `trajectory3d` | Long table: explicit Zreal + real third variable with meaning/unit + explicit -Zimag + Series; 1–6 groups | Never create decorative depth, fit circuits, or infer the third variable |

## Ranking signals

- Strong domain headers and units outrank generic positional matches.
- `Obs/Calc` or `y_obs/y_calc` plus X/2theta strongly favors XRD Rietveld mode. `weight`,
  `Q`, `Used`, `diff/sigma`, and axis-control columns are not intensity series. Unknown numeric
  refinement columns require a corrected mapping before planning.
- Explicit user intent can disambiguate compatible layouts but cannot make invalid data valid.
- Long category labels favor horizontal bars.
- Multiple nonnegative components plus a composition intent favor stacked or percent stacked.
- More than eight pie slices should trigger a bar-chart recommendation.
- Non-monotonic potential can support CV; monotonic sweep plus explicit LSV intent supports LSV.
- Error suffixes strongly favor `line_error`.
- Ordered numeric X plus explicit progression intent favors `trend`; generic numeric XY remains
  ambiguous between line and scatter without scientific intent.
- A metric-wide table plus radar intent favors `radar`, but scale comparability must be confirmed.
- A rectangular category × numeric matrix plus heatmap intent favors `heatmap`.
- `source/target/value` strongly favors `sankey`.
- A single raw numeric column plus histogram intent strongly favors `histogram`.
- A numeric group-wide table favors `raw_summary` for small evidence sets and `violin` when
  distribution shape is the explicit question.
- Explicit estimate/lower/upper semantics strongly favor `forest` over generic bars or heatmaps.
- A positive Size column alongside X and Y strongly favors `bubble` over ordinary scatter.
- Explicit FPR/Recall probability coordinates favor `diagnostic_curve`; PR also requires prevalence.
- Predicted probability, observed fraction, and bin count favor `calibration_curve`.
- Threshold plus explicit Treat-all/Treat-none columns favor `decision_curve`.
- Actual-class rows plus predicted-class columns favor `confusion_matrix` over a generic heatmap.
- Mean/Difference/Bias/LoA semantics favor `bland_altman`; Visit plus stable subject columns favors
  `paired_trajectory`.
- A numeric group-wide table plus explicit Raincloud intent favors `raincloud`; it retains every
  observation while Origin's verified half-violin object supplies the density and mean ± 1 SD.
- Feature + SHAP value + Feature value semantics strongly favor `shap_summary`; the original SHAP
  X values and first-appearance feature order are immutable.
- `Category | Group` raw-observation headers strongly favor `grouped_box` over generic distribution
  routes.
- Time plus explicit PL semantics favors TRPL; paired Fit columns remain user-supplied evidence.
- Wavelength plus Absorbance/Transmittance favors `uv_vis`; a Tauc inset requires complete explicit
  Photon-energy and Tauc-value columns.
- Recommend `trajectory3d` only when all four long-table roles are explicit, the third-axis header
  includes scientific meaning and unit, `-Zimag` is supplied rather than inferred, and Series has
  1–6 groups. Otherwise require mapping confirmation or reject the 3D route.

## Automatic selection gate

Allow automatic selection only when the first candidate is high confidence, clearly separated from
the second candidate, and its internal column mapping needs no confirmation. Otherwise present up
to three choices and wait.

## Experimental backlog

Raman, FTIR, TGA/DSC, GCD/Tafel, ECDF/KDE, correlation matrix,
regression, volcano, waterfall/diverging bars, and multi-panel layouts remain experimental
until their Origin routes pass the full verification contract.
