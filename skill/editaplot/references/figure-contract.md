# Publication-informed Origin figure contract

Define this contract before choosing a renderer.

```text
Core conclusion:
Evidence role: discovery | comparison | mechanism | validation | robustness | composition | relationship
Audience/output:
Data unit and sample definition:
Primary comparison:
Required axes and units:
Series/color semantics:
Statistics and error definition:
Allowed display transforms:
Editable outputs:
Reviewer risk:
```

## Evidence rules

- Write one conclusion containing an action or relationship, not a topic label.
- Give each chart or panel one unique evidentiary job.
- Prefer the fewest views needed to support the conclusion.
- Keep the primary evidence visually dominant; make controls and context quieter.
- If no conclusion is provided, state a provisional one and ask for confirmation before final styling.

## Visual rules for Origin

- Use a white background, Arial, restrained semantic colors, and no decorative grid by default.
- Keep related conditions in one color family and reserve strong accents for the primary comparison.
- Choose a stable palette ID before rendering when color is user-selectable. Record its exact HEX
  values, allowed mode, group limit, and accessibility warnings in the plan. If the group count
  exceeds the safe limit, retain the verified default or add independently readable marker/line/hatch
  encoding rather than cycling invisible pale colors.
- Keep semantic palettes fixed for XPS components, signed effects, diagnostic reference curves,
  confusion matrices, and heatmaps unless that exact override route has been independently verified.
- Avoid rainbow maps, ornamental 3D, shadows, glossy bars, and unjustified smoothing.
- Use direct labels when stable and readable; otherwise keep an editable legend. Legend overlap is
  not a hard failure when the OPJU remains editable.
- Resolve page size, margins, font sizes, line widths, error widths, and symbol sizes together from
  chart type, data density, series count, and label length. General figures are adaptive; only an
  explicitly named fixed profile may retain a fixed page such as 22.31 cm × 16.82 cm.
- Write physical page size through the verified Origin unit conversion route and read it back. Do
  the same for text and line widths; a small on-screen preview is not evidence of correct typography.
- Never shrink Origin text merely to make dense data fit. Recommend another layout or split figure.
- Treat axis binding as a style reset boundary. After every `axis -ps ... T dataset`, reapply and
  read back the visible X/Y/Y2 label font, point size, and color.
- Verify `xb`/`yl`/`yr`, legends, and manual annotations as separate editable text objects. The X
  and Y tick-label font codes must match the registered profile; equal-looking PNG glyphs are not enough.
- General defaults are Arial, 20 pt axis titles, 17 pt tick labels, and 17 pt legends. Registered
  density-specific profiles may vary; grouped-box and percent-composition legends use 18 pt.
- Put a percent-composition legend in a reserved external page column when it cannot fit the data
  field. Grouped-box legends are borderless editable labels, not the framed system-template legend.
- Heatmaps reserve a detached right margin for the colorbar and verify both colorbar and cell-label fonts.

## Scientific integrity

- Record `n`, center statistic, spread/error definition, test, correction, and comparison when relevant.
- Do not calculate statistics from replicates unless the user requests and confirms the method.
- Do not remove observations, normalize, baseline-correct, smooth, fit, or derive peaks silently.
- Keep source columns in the editable Origin workbook; create helper columns only for declared display transforms.

## Medical multi-panel rules

- Use 2–9 panels and give each panel one unique evidence role; panel labels are deterministic A–I.
- Quantitative panels must come from a `verified` route with complete OPJU/PNG/PDF/TIF/readback and
  an explicit human visual-QA pass.
- Image panels must be local PNG/JPEG/TIFF files with user attestations for deidentification and
  burned-in text review, plus modality, plane, and display parameters. The planner does not infer
  that private health information is absent.
- When two or more quantitative panels reuse conditions, freeze one condition-to-color map. Do not
  share a legend until shared semantics are explicitly confirmed.
- The V1 composer is a hash-bound layout plan, not an image-processing tool or merged OPJU renderer.
  Preserve the individual editable Origin subprojects as the quantitative evidence of record.
