# XPS Adaptive Visual Contract

## Publication-Informed Audit Boundary

This template targets clean, editable Origin output for routine XPS spectra. It
is publication-informed in palette discipline and scientific clarity: white chart
background, Arial text, no rainbow palette, dark blue raw traces, neutral gray
backgrounds, restrained red envelope, and soft color-to-white gradient fills.
It is not a final journal composite-page layout by itself. The shared Origin
contract intentionally uses larger labels and heavier borders for the user's
current automated plotting workflow. Program output must keep the locked sizes;
the user may independently resize panels or move legends during later manuscript assembly.

- Use the shared fixed Origin page, layer, font, line width, and border contract.
- Because this template displays real Y-axis count labels, it uses a template-specific
  layer override of left `23%` and width `76.01%` so tick labels and the Y title
  are not clipped. Move the whole layer rather than shifting the Y title alone
  or reducing the locked font size; this preserves title-to-tick spacing. The page
  size, top, height, right edge, font family, line width, and border width still
  follow the shared Origin contract: axis titles `26 pt`, visible tick labels
  `24 pt`, legend `24 pt`, visible curves `5 pt`, and borders `3 pt`. The right
  edge remains `99.01%`.
- Display binding energy in the conventional XPS direction: high eV on the left, low eV on the right.
- Compute X and Y axis limits from the actual input data. Keep the source min/max
  unchanged in the analysis record, but add symmetric X display padding equal to
  the smaller of `0.25 × major step` and `3% × source span` (clamp a non-negative
  lower energy bound at zero). This prevents endpoint tick labels and traces from
  touching the page edge without changing the locked page/layer geometry.
- Show Y-axis real count coordinates with major ticks and scientific-format labels
  when the input is a scan/fitted spectrum. Do not inherit the fixed C 1s
  "Y labels hidden" rule for this adaptive template.
- Keep Y minor ticks hidden unless a later measured dataset requires them.
- Show X-axis numbers, major ticks, and minor ticks. Tick labels must sit on major ticks.
- Legend entries must come from the source CSV column names, not hard-coded C 1s chemistry labels.
- Raw/experimental series is drawn as a restrained dark blue editable Origin
  line, not as open-circle scatter. It keeps the shared `5 pt` curve width.
- Raw/experimental curves receive a muted blue-violet single Origin gradient
  fill. The fill baseline is the detected background column when present;
  otherwise it is the automatically computed Y-axis floor. This makes one-line
  and multi-line inputs visually consistent without altering the source CSV.
- Background is drawn as a neutral gray line when detected.
- Envelope is drawn as a red line when detected.
- Variable component/series columns are drawn as separate colored editable Origin curves.
  Component line colors and component fill colors are intentionally separate:
  darker muted line colors identify each component, while paler related fill
  colors reduce visual mud where fitted peaks overlap. Each component uses an
  internal Origin-only fill baseline and applies a single Origin gradient fill
  to that baseline, with an opaque component line drawn on top. The baseline
  is the detected background column when present and the Y-axis floor otherwise.
  The source CSV is not changed.
- Origin fills follow the fixed `xps_c1s_fit` route: one visible upper curve and
  one invisible `*_FillBase` curve, `set_fill_area(..., type=9)`, `set -pfm 3`,
  `set -p2fm 3`, and `set -paaf 0`. For adaptive measured spectra, explicitly set
  both gradient starts to the target fill color (`set -pfb color`, `set -p2fb color`)
  and both gradient ends to white (`set -pff white`, `set -p2ff white`) so the upper
  side of the filled region keeps color and the lower side retreats toward white.
  The inverse command order makes the visual gradient appear reversed in Origin.
  Do not use
  `*_FillBand###` layered helper columns in this V1 template unless the user
  explicitly re-approves that route after visual inspection.
- Residuals are optional. They are detected and preserved in the Origin worksheet,
  but they are not plotted on the main counts axis unless a dedicated residuals
  panel/template is added later.
- Success requires an editable non-empty OPJU, PNG/PDF/TIF exports, Origin readback
  of page/layer/axes/text sizes/visible line widths, and human visual inspection for
  clipping, wrong axes, wrong ticks, or anomalous lines. Legend overlap is not a
  failure because the legend remains editable and may be moved later in the OPJU.
