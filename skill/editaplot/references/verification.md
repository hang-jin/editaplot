# Origin delivery verification

Do not report success from a rendered preview or PNG alone.

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
- Confirm page dimensions and registered layer geometry.
- Confirm required axes, titles, label tables, scale direction, tick visibility, text sizes and font codes,
  plot widths, frame widths, and special plot labels where applicable.
- Confirm the X and Y tick-label font codes are identical to the registered profile after any
  dataset-backed label binding. Confirm Y-axis typography independently; do not infer it from X.
- Confirm legends, direct labels, notes, heatmap cell text, and colorbar labels have their own
  point-size and font readback whenever those objects exist.
- Treat missing readback as a rendering failure even if exports exist.

## Human visual checks

- Open the PNG or TIF and inspect axes, titles, X/Y font consistency, labels, colors, line weights,
  colorbar separation, clipping, and unexpected objects.
- Check that scientific direction and transforms match the figure contract.
- Check that the figure remains readable at its intended physical size.
- Allow legend overlap only when the legend remains editable and no data meaning is lost.
- Record visual QA as pending until a human or Codex with image inspection has reviewed an export.
