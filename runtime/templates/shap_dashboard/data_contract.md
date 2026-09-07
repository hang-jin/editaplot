# SHAP dashboard data contract

Accept a precomputed long table: `Feature`, `SHAP value`, `Feature value`, and
`Feature Group`. Equivalent Chinese names are supported. Optional `Sample ID`,
`Feature Order`, `Mean absolute SHAP`, and `Group contribution (%)` have the same
meaning and validation as `shap_summary`. Summary/order cells may appear once per
feature/group with blanks in repeated rows. Each feature needs at least three
complete observations. Support 2–20 features and 2–5 explicitly supplied groups.

The left bars and right beeswarm keep first-appearance feature order, or the explicit
unique `Feature Order`. The ring alone places members of each group contiguously.
All SHAP X values are preserved. Color is min-max normalized within each feature;
a constant feature uses 0.5. Vertical offsets reduce overlap without dropping points.

Mean absolute importance is `mean(abs(SHAP))` within each feature. A feature's share
is `100 * feature_mean / sum(all_feature_means)`. The outer ring sums these same
means by group and uses the identical denominator; the inner ring shows feature
shares. Thus corresponding group boundaries align. A supplied group percentage
is retained and checked using the existing ±0.5 percentage-point rounding tolerance;
the displayed rings use the exact common denominator. These calculations and
display transformations are explicit, source-bound derived items requiring approval.

No model training, SHAP computation, fitting, smoothing, significance tests,
automatic group inference, or screenshot digitization occurs. CSV is immutable.
Use the included synthetic example; it does not describe a real study.

Choose a mapping `plot_mode`: `dashboard_blue_red` (default), `dashboard_viridis`,
or `dashboard_red_blue`. Palette choice is frozen with the scientific plan.
