# XPS Adaptive Data Contract

The public XPS workflow accepts cleaned CSV, TXT, XLS, and XLSX tables with
variable numeric columns. TXT delimiters may be comma, Tab, or semicolon; Excel
loading uses the first non-empty worksheet.

Required:
- At least two numeric columns.
- One binding-energy column. Preferred names include `BindingEnergy`, `Binding Energy (E)`, `Energy`, or similar.
- At least one intensity-like Y column.

Recognized optional columns:
- Raw intensity: `Raw`, `Counts / s`, `Intensity`, `Experimental`.
- Background: `Background`, `Backgnd.`, `BG`, `Baseline`.
- Envelope: `Envelope`, `Fit`, `Fit Total`, `Total`.
- Residuals: `Residuals`, `Residual`.
- Any other numeric Y columns are treated as editable component/series curves.

The template does not add missing peak columns or alter source values. Temporary
Origin worksheet helper columns such as `PlotX` are generated only inside the
Origin project so the source table remains an auditable copy of the measured data.
Fill-baseline helper columns are also Origin-only. Raw curves and component/series
curves fill to the detected background column when it exists; otherwise they fill
to the automatically computed Y-axis floor. These helper columns must never be
written back into the user's cleaned input file.

Residual columns are recognized as residual diagnostics. They are preserved in
the Origin worksheet and verification report, but they are not plotted on the
main counts axis by default because their scale is not comparable with raw
counts, background, envelope, or component curves.

## Instrument-workbook preprocessing notes

Instrument workbooks may contain
metadata, titles, empty spacer columns, and plot objects before the numeric table.
They must first be reduced to one clean rectangular spectrum table; the cleaned
result may remain XLS/XLSX or be saved as CSV/TXT:

- Treat each measured-spectrum sheet as one input table; preserve its spectrum name
  in the file or worksheet name.
- Skip index/empty sheets such as `Titles` and `Sheet1`.
- For the observed workbooks, row 15 contains the semantic series names and
  row 16 contains units or the raw counts label; numeric data starts at row 17.
- Keep only columns that contain numeric data rows. Drop spacer columns and
  acquisition-parameter text.
- Do not create missing peaks, do not normalize values, and do not write helper
  columns into the cleaned input.
- `Kinetic Energy (E)` is accepted as the X column through the monotonic numeric
  fallback. If a future plot must show a kinetic-energy axis title, implement
  axis-title inference in the renderer rather than renaming the source data.
