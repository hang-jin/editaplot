# Time–frequency visual contract

One native editable PID105 matrix, numeric physical axes, all supplied cell values, and a detached
101-level viridis scale. No categorical relabelling, smoothing, interpolation, event arrows,
per-cell numbers, significance masks, or synthetic baseline/reference are added.

Freeze the actual cell-edge limits, numeric tick steps, exact HEX ramp, and physical page/layer
geometry in the shared preview/Origin plan. Keep Arial on both axes independently; default title
20pt, tick17pt, colorbar15pt, value title17pt. The scale has a reserved page gutter and editable
numbers; its full measured bounds must fit. Units remain verbatim, without inferred conversions.
Measure axis/value titles in physical font units before freezing geometry, expanding the data
area and page as needed. Keep the detached scale gutter in physical units on expanded pages.
Boolean and datetime Excel cells are rejected before the numeric working-copy conversion.

The original workbook, matrix values, coordinate mapping, native plot binding, color levels,
labels, font codes, physical page/layer size, and complete OPJU/PNG/PDF/TIF are checked. A new host
must pass smoke and the required matrix/color-scale capabilities. A saved OPJU is reopened in a
fresh worker for release QA. A Python preview never substitutes for real Origin evidence.
