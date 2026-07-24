# Origin delivery verification

Do not report success from a rendered preview or PNG alone.

## Live connection smoke

Doctor discovery is never connection evidence. Before the first render in an environment, or after
its Python, Origin, or Automation target changes, run the real smoke through an EditaPlot-owned
isolated instance. The smoke must complete:

- Automation activation and initialization;
- actual Origin version and executable-path readback;
- a minimal editable workbook and graph;
- non-empty OPJU, PNG, PDF, and TIF outputs in an isolated test directory;
- minimum axis-object readback.

A smoke failure is a staged technical failure, not a reason to ask the user to open Origin manually.
A successful smoke proves the current connection and minimum core capabilities only; it does not
prove that every template is available. Apply the selected template's capability decision next.

## Mandatory files

- non-empty editable `result.opju`;
- non-empty `result.png`;
- non-empty `result.pdf` with usable text/fonts;
- non-empty `result.tif`;
- validation and provenance reports;
- `origin_verify_report.json` with page/graph/axis/style readback.

## Programmatic checks

- Confirm every reported artifact resolves inside the run output directory.
- Confirm the input copy hash matches the inspected source hash.
- Confirm `data_understanding.status` is `confirmed`, its source hash matches the render source,
  every source column is classified exactly once, no item remains `uncertain`, and every visible
  element binds only primary/secondary source data or an explicitly approved allow-listed helper.
- For a reference-driven plan, confirm the image/spec hashes, essential mark bindings, applied and
  rejected style tokens, and that no reference pixels, OCR text, code, source values, author marks,
  logos, or watermarks entered the plan or output folder.
- Confirm page dimensions and registered layer geometry.
- Confirm required axes, titles, label tables, scale direction, tick visibility, text sizes and font codes,
  plot widths, frame widths, and special plot labels where applicable.
- Confirm the X and Y tick-label font codes are identical to the registered profile after any
  dataset-backed label binding. Confirm Y-axis typography independently; do not infer it from X.
- Confirm legends, direct labels, notes, heatmap cell text, and colorbar labels have their own
  point-size and font readback whenever those objects exist.
- Treat missing readback as a rendering failure even if exports exist.
- For Rietveld figures, confirm Observed/Calculated/optional Background/Difference source bindings,
  that Publication `Diff` uses identity display values, and that every phase-tick plot reads its X
  range from the original sparse Phase column while only its Y lane is a helper. Confirm the
  documented point-sized vertical-bar symbol kind `10` when phase ticks exist. Symbol `58` is a
  full-height X-position line and must not be accepted as a Rietveld reflection tick.

## Human visual checks

- Open the PNG or TIF and inspect axes, titles, X/Y font consistency, labels, colors, line weights,
  colorbar separation, clipping, and unexpected objects.
- Check that scientific direction and transforms match the figure contract.
- Check that the figure remains readable at its intended physical size.
- Allow legend overlap only when the legend remains editable and no data meaning is lost.
- Record visual QA as pending until a human or Codex with image inspection has reviewed an export.
