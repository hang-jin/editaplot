# Chart selection and support levels

Select from the scientific question first, then check that the data layout supports the choice.
The route list below records template verification on the fully verified Origin 2024b / 10.15
baseline. It is separate from compatibility with the user's current Origin host. After the live
smoke, require the template capability decision for that host; a connected 2021+ installation does
not automatically support every route. Rendering starts a dedicated Origin instance, so do not ask
the user to open Origin first. Origin/OriginPro 2021–2026b is the compatibility target; only 2024b
is the current fully verified baseline.

## Verified V1 routes

The registry exposes 40 public plotting routes. Some table rows group closely related candidates,
so the number of rows is not the route count.
我已验证 `density_ridgeline3d` 的完整 Origin 路线；它仍只接受冻结的六角色表，并遵守下面的
数据与焦点边界。

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
| Category × series result matrix | `heatmap` | row labels + >=2 numeric columns; >=2 rows | Keep all matrix values; dense plans hide cell numbers, thin labels, and detach the colorbar. The public gallery displays the verified real-Origin 30×30 case only; the smaller and 40×40 cases are retained regression history |
| Flow | `sankey` | source + target + positive value | Avoid self-links and excessive nodes |
| Directed relationships across panels | `circular_network` | Panel + Source + Target + positive Weight; optional Sign/up to four groups/EdgeLabel | Preserve shared node positions and one global width scale; panels above 12 edges retain but hide edge labels; do not infer causality, correlation, centrality, or missing edges |
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
| Model feature contribution | `shap_summary` | Feature + precomputed SHAP value + numeric Feature value; optional order, Mean\|SHAP\|, group, group % | Never run SHAP; preserve SHAP X; confirm every display/helper summary derivation |
| Steady-state or time-resolved photoluminescence | `pl` | Wavelength or Time + one or more PL series; optional explicitly paired Fit columns | Preserve multi-condition order; TRPL uses log Y; never calculate lifetime or fit curves |
| UV–Vis spectrum with optional Tauc evidence | `uv_vis` | Wavelength + one or more comparable Absorbance or Transmittance series; optional Photon energy + Tauc value/fit/Eg | Do not mix signal definitions without an explicit axis contract; never calculate photon energy, exponent, fit, or band gap |
| Multi-condition 3D Nyquist trajectory | `trajectory3d` | Long table: explicit Zreal + real third variable with meaning/unit + explicit -Zimag + Series; 1–6 groups | Never create decorative depth, fit circuits, or infer the third variable |
| Ordered 3D dual-density comparison with supplied baseline locators | `density_ridgeline3d` | Mixed-wide six-role table: Condition ID + unit-bearing Condition Position + unit-bearing Density X + paired nonnegative Solid/Dashed Density + one Focal X per group; 2–6 groups | Density profiles and focal values must be supplied upstream; never run KDE, infer peaks/intersections/thresholds, or lift focal markers off Z=0 |

## Verified materials routes

These routes have generated Origin 2024b OPJU/PNG/PDF/TIF files and passed programmatic object
readback, SHA-bound human visual QA, and the sanitized public-gallery audit.

| Question/evidence | Candidate | Required shape | Cautions |
|---|---|---|---|
| Compare independent measured XPS spectra | `xps_compare` | Binding Energy + at least two measured Intensity/Counts/Experimental series | Overlay by default; fit/background/residual/component columns are not samples; stacked offset requires explicit confirmation |
| Infrared spectrum or ordered IR series | `ftir` | Wavenumber + one or more comparable Absorbance/Transmittance series | Decreasing wavenumber axis; never correct, smooth, label, or assign peaks |
| Processed NMR spectrum comparison | `nmr` | Chemical Shift (ppm) + one or more processed intensity series | Decreasing chemical-shift axis; never phase-correct, integrate, pick, or assign peaks |
| DSC heat-flow comparison | `dsc` | Temperature + one or more comparable Heat Flow series | Confirm endothermic/exothermic direction; never infer Tg/Tm/Tc or enthalpy |

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
- `source/target/value` without a panel dimension strongly favors `sankey`.
- `Panel/Source/Target/Weight` strongly favors `circular_network`; preserve panel, direction,
  optional sign, and stable node-position semantics instead of collapsing it into Sankey.
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
  X values are immutable. First-appearance order remains the default, while an explicit Feature
  Order may select another verified order. Feature Group enables the optional grouped contribution
  profile after the summary lineage is confirmed.
- `Category | Group` raw-observation headers strongly favor `grouped_box` over generic distribution
  routes.
- Time plus explicit PL semantics favors TRPL; paired Fit columns remain user-supplied evidence.
- Wavelength plus Absorbance/Transmittance favors `uv_vis`; a Tauc inset requires complete explicit
  Photon-energy and Tauc-value columns.
- Binding Energy plus at least two independently named measured XPS series favors `xps_compare`.
  Background, envelope, residual, fit, component, and peak semantics instead favor the XPS fit route
  or an explicit retained-without-rendering role.
- Wavenumber plus Absorbance/Transmittance favors `ftir`; Chemical Shift/ppm favors `nmr`.
- Temperature plus explicit Heat Flow/DSC semantics favors `dsc`; temperature alone is not enough
  because PL, electrical, and other ordered measurements may use the same X column.
- Recommend `trajectory3d` only when all four long-table roles are explicit, the third-axis header
  includes scientific meaning and unit, `-Zimag` is supplied rather than inferred, and Series has
  1–6 groups. Otherwise require mapping confirmation or reject the 3D route.
- 我只在六个 mixed-wide 角色全部明确、两条密度曲线同行且单位一致、每组恰好一个 `Focal X`
  时推荐 `density_ridgeline3d`。缺角色、缺单位、焦点数量冲突或焦点越界时停止自动选择。

## Automatic selection gate

Allow automatic selection only when the first candidate is high confidence, clearly separated from
the second candidate, and its internal column mapping needs no confirmation. Otherwise present up
to three choices and wait.

## Pre-render execution gate

After semantic confirmation and RenderPlan creation, execute
`editaplot.cmd origin-smoke --output-dir <unique-smoke-directory>` before `editaplot.cmd render`.
The smoke must start an EditaPlot-owned isolated Origin instance and pass its minimal export loop.
Doctor discovery is not a substitute for this live gate. For an ordinary render, omit
`--output-dir`; the runtime must create a unique `<source_stem>_EditaPlot_<timestamp>` folder in the
same directory as the original data file. Use another destination only on explicit user request.

## Experimental backlog

Raman, TGA, GCD/Tafel, ECDF/KDE, correlation matrix,
regression, volcano, waterfall/diverging bars, and multi-panel layouts remain experimental
until their Origin routes pass the full verification contract.
