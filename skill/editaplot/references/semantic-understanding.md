# Scientific data understanding and element confirmation

Use this gate after selecting a candidate template and before creating a render plan.

## The five data dispositions

Every source column must appear exactly once:

- `render_primary`: the main evidence shown in the figure;
- `render_secondary`: background, fit, residual, reference, phase tick, or another visible aid;
- `support_only`: used for validation, filtering, weighting, coordinate choice, or layout control,
  but not drawn as a curve or mark;
- `retain_not_render`: preserved for provenance/editability and not used by the visible figure;
- `uncertain`: scientific meaning is unresolved; planning is blocked.

Do not use `ignored` as an unexplained wastebasket. Explain why each non-rendered numeric column is
support-only or retained.

## Required sequence

1. Prepare the selected template with the proposed or corrected column mapping.
2. Run `understand` using that exact mapping.
3. Summarize in natural language:
   - what kind of experiment/table this appears to be;
   - what will be drawn;
   - what is retained or used only as support;
   - what approved display helpers are proposed;
   - what the drawing layer will not calculate;
   - any focused unresolved scientific questions.
4. If an item is uncertain, obtain a corrected mapping and return to step 2.
5. Ask the user to confirm the concise summary.
6. Pass the exact proposal hash, approved helper IDs, and ambiguity resolutions to `plan`.

A different source hash, mapping, or proposal hash invalidates the confirmation. Never edit a
confirmed JSON plan by hand.

## Derived data

Source columns and derived helpers are separate objects. A helper requires:

- an allow-listed deterministic operation;
- complete source-item lineage;
- explicit user approval;
- a stated scientific/display purpose;
- a renderable disposition when visible.

Do not silently fit, smooth, remove outliers, calculate error bars, identify phases, calculate
background, derive band gaps, calculate SHAP, or create statistics. Simple display helpers such as
an X-axis sign transform, percentage-of-row total, or a phase-tick Y lane remain explicit and never
overwrite source values.

## GSAS/GSAS-II Rietveld example

A suitable short confirmation is:

> 我理解这是 XRD Rietveld 精修结果。要画：2θ、实测点、计算线、文件中已提供的背景/差值和两组物相刻线。只保留不画：weight、Q、Used、diff/sigma 与轴控制列。不会自动计算背景、差值、Rwp、χ²、物相或峰归属。Publication Diff 将按源值直接绘制，不再偏移。这个理解是否正确？

If a numeric column such as Temperature is not part of a recognized contract, do not guess. Ask
whether it is a plotted condition, support metadata, an alternative coordinate, or a column that
should be retained without display, then regenerate the proposal.

## Conversation contract

Keep the first response compact. The full JSON is audit evidence for Codex and advanced users, not
the default beginner explanation. Ask only questions that can change the scientific meaning or
visible elements.
