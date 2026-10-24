# Supplied-event raster: developer acceptance contract

This route has completed the real Origin 2024b / 10.15 evidence gate. Other target hosts still
require their own smoke, capability decision and output evidence. The requirements below do not
imply that every Origin version has passed.

## Source and native objects

Preserve the immutable source table, finite event times, trial IDs, conditions and first-appearance
order. Accept 1–200 explicitly supplied trials and 1–8 conditions, with at least one event overall.
Each trial belongs to exactly one condition. Reject duplicate trial/time events and duplicate
blank-time inventory entries per trial. Blank times declare inventory, never events at zero;
retain empty lanes and conditions without creating placeholder points or plots.

Use one fresh single-layer native Scatter graph. For each condition with events, bind an editable
Scatter plot (PID 201) to helper X=`SourceTime`, Y=`TrialOrdinal`; use symbol kind 10, interior 1,
the frozen physical marker size and 22% edge setting. Do not connect marks or embed a bitmap.
Helpers belong only in memory and OPJU worksheets, never in the source file. `SourceRow` is the
1-based parsed data-row position, excluding the header and fully empty rows removed by the loader;
inventory rows count toward that position but are not plotted. Internal plan row indices are 0-based.

## Coordinates, text and color

Keep source-first trials top-to-bottom with reversed Y limits `(trial_count + 0.5, 0.5)`.
Use source trial IDs as editable direct text outside the left plot edge; hide numeric Y labels
and Y ticks. Sparse trial text must retain the first/last IDs and must never remove lanes or events.
Use a linear time axis with the explicit supplied unit and frozen 5% display padding; constant-time
tables use the planner's finite magnitude-based guard. Do not change source coordinates.

Place editable, borderless colored condition text in a separate top gutter, including conditions
without events. Freeze a compatible selected palette ID and exact condition-to-HEX mapping in
source-first condition order; empty conditions still reserve their colors. Use white background,
Arial 20 pt axis titles, 17 pt ticks/direct text and a 1.1 pt frame. Adapt physical page/layer
dimensions to trial density, multiline labels and condition count instead of shrinking fonts.
Derive marker size from lane height (maximum 6 pt). Keep labels legible, unclipped and outside
the event field; do not add decorative grids, statistics, event detection, PSTH or rates.

Keep the native YL title information hidden and show the same wording as the ordinary editable
page-attached `EventYTitle` object. Axis-owned YL can move on refresh even when unclipped. Verify
the visible object's frozen center and page attachment, and YL's hidden state after export/reopen;
do not alter global graph options to suppress the behavior.

## Evidence required before route promotion or formal success

Verify source-table exact roundtrip and unchanged source values; all helper times, ordinals and
source-row bindings; per-condition and overall event counts; explicit empty-trial inventory;
native plot count/type and worksheet bindings; symbol kind/interior/size/edge; exact condition
colors; axis types, limits, increments and hidden Y ticks; physical page/layer geometry; text
content, font, physical size, position and borderless condition labels. Only inherited objects
in a newly created owned layer may be cleared; never alter user templates or existing projects.

Require complete PNG, PDF, TIF and editable OPJU outputs, readback evidence, saved-project reopen
checks for retained data/objects and export consistency, plus human visual QA of overlap, clipping,
sparse labels, all lanes/events and empty conditions. A preview or mocked test is not a completed
Origin deliverable. Record the tested host/Origin version and evidence separately from route
status; other versions remain capability-gated until their own smoke and full evidence checks pass.
