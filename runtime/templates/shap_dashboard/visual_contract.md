# SHAP dashboard visual contract

The dashboard combines aligned left importance bars and right SHAP beeswarm with
a two-level native doughnut. It is a separate template; the existing overlaid
`shap_summary` profiles remain available and retain their original digests.

- White page, Arial, adaptive physical page based on feature count and label length.
- Left/right plot areas share top, bottom and feature-row centers. Each retains its
  own horizontal numeric range. All category labels and value annotations are editable.
- With at least eight features, short lower bars and compact labels, the rings use
  the vacant right side of the importance panel. Otherwise a separate lower area
  preserves readability. This layout decision is frozen from data in the plan.
- Feature-group hues are stable; each group's feature wedges and bars share a related
  lightness sequence. Color encodes membership, never effect sign.
- The beeswarm uses one of three frozen 101-level ramps: blue–white–wine, Viridis-like
  purple–green–yellow, or red–yellow–blue. Low/High endpoints always describe relative
  feature value, not the SHAP sign. A true dataset-bound Origin Spectrum1 is required.
- Outer ring = feature groups; inner ring = features in group order. Angles, not
  area across rings, represent percentages. Both rings share one total-mean denominator.
- Native Origin PID215 bars, PID201 scatter, and two PID225 doughnuts remain editable.
  Ring view angle must be 90°, thickness 0, and hole/radius/rotation/labels must be read back.
- Geometry, source X, plot bindings, color levels, fonts, axis direction and exports
  must pass. A Python preview is not an Origin result.

Layout is versioned as `shap-dashboard-layout-v1` in the frozen plan. Quantitative
bars, raw contribution distribution and group summaries serve complementary roles.
No screenshot values, phone UI, watermarks or unprovided scientific claims are copied.
