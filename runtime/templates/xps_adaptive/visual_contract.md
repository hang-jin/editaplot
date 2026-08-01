# XPS Adaptive Visual Contract

## Publication-Informed Audit Boundary

This template targets clean, editable Origin output for routine XPS spectra. It
is publication-informed in palette discipline and scientific clarity. Its verified defaults are a
white chart background, Arial text, no rainbow palette, dark blue raw traces, neutral gray
backgrounds, a restrained red envelope, and soft color-to-white gradient fills.
It is not a final journal composite-page layout by itself. The shared Origin
contract intentionally uses larger labels and heavier borders for the user's
current automated plotting workflow. These values are the verified default profile, not a claim
that every cosmetic field is permanently locked. A separately confirmed user request for exact
series colors, physical line widths, fill transparency, a safe page/aspect ratio, or legend
show/hide, borderless, or position may replace only a field supported and read back by the current
XPS renderer. Unsupported fields retain this profile or are rejected explicitly. A reference image
alone never authorizes an override, and the user may still resize panels or move editable legends
during later manuscript assembly.

- Use the shared verified Origin page, layer, font, line width, and border defaults unless a
  confirmed cosmetic field passes its XPS-specific capability and readback gate.
- Because this template displays real Y-axis count labels, it uses a template-specific
  layer override of left `23%` and width `76.01%` so tick labels and the Y title
  are not clipped. Move the whole layer rather than shifting the Y title alone
  or reducing the verified font size; this preserves title-to-tick spacing. The page
  size, top, height, right edge, font family, line width, and border width still
  follow the shared Origin contract: axis titles `26 pt`, visible tick labels
  `24 pt`, legend `24 pt`, visible curves `5 pt`, and borders `3 pt`. The right
  edge remains `99.01%`.
- Display binding energy in the conventional XPS direction: high eV on the left, low eV on the right.
- Compute X and Y axis limits from the actual input data. Keep the source min/max
  unchanged in the analysis record, but add symmetric X display padding equal to
  the smaller of `0.25 × major step` and `3% × source span` (clamp a non-negative
  lower energy bound at zero). This prevents endpoint tick labels and traces from
  touching the page edge without changing the confirmed page/layer geometry.
- Show Y-axis real count coordinates with major ticks and scientific-format labels
  when the input is a scan/fitted spectrum. Do not inherit the fixed C 1s
  "Y labels hidden" rule for this adaptive template.
- Keep Y minor ticks hidden unless a later measured dataset requires them.
- Show X-axis numbers, major ticks, and minor ticks. Tick labels must sit on major ticks.
- Legend entries must come from the source CSV column names, not hard-coded C 1s chemistry labels.
- Raw/experimental series defaults to a restrained dark blue editable Origin
  line, not open-circle scatter. It keeps the shared `5 pt` curve width unless an explicit width
  override has passed the current XPS renderer/readback gate.
- Raw/experimental curves receive a muted blue-violet single Origin gradient
  fill. The fill baseline is the detected background column when present;
  otherwise it is the automatically computed Y-axis floor. This makes one-line
  and multi-line inputs visually consistent without altering the source CSV.
- Background defaults to a neutral gray line when detected.
- Envelope defaults to a red line when detected.
- Variable component/series columns are drawn as separate colored editable Origin curves, using
  the registered component palette unless a confirmed exact series-to-color mapping is verified.
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
- Cosmetic style requests never alter the input table, detected column roles, component identity,
  high-to-low binding-energy direction, fill baseline semantics, or the single-region
  `set_fill_area(..., type=9)` / `-pfm 3` API route. Exact colors, widths, transparency, page/aspect,
  and legend settings are independent fields and count as applied only after Origin object readback.
- Residuals are optional. They are detected and preserved in the Origin worksheet,
  but they are not plotted on the main counts axis unless a dedicated residuals
  panel/template is added later.
- Success requires an editable non-empty OPJU, PNG/PDF/TIF exports, Origin readback
  of page/layer/axes/text sizes/visible line widths, and human visual inspection for
  clipping, wrong axes, wrong ticks, or anomalous lines. Legend overlap is not a
  failure because the legend remains editable and may be moved later in the OPJU.
