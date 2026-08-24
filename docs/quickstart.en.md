# English quick start

## The 30-second version

Requirements: a physical Windows 10/11 x64 computer, 64-bit CPython 3.10–3.12, and a local
Origin/OriginPro version in the 2021–2026b compatibility target. Origin 2024b (10.15) is the only
current fully verified live baseline; other target versions receive a compatibility result after a
local handshake, real smoke test, and template capability check. Origin 2020b and earlier, macOS,
Linux, WSL, Wine/CrossOver, Parallels, and other VMs are unsupported.

I currently publish 40 Origin plotting routes and retain 47 fully reviewed PNGs as verification
assets. The public page displays 45 cases. The new 3D dual-density route accepts only upstream
supplied density profiles and one Z=0 baseline focal locator per group; it does not run KDE or infer
peaks or intersections. For heatmaps, the page shows only the real Origin-rendered
30×30 dense example; the smaller matrix and 40×40 cases remain regression history rather than
additional gallery entries.

Download the **complete repository** and run this from its root:

```powershell
.\editaplot.cmd setup
```

Do not copy only `skill/editaplot`; it does not contain the rendering runtime. Git users can clone
the repository. Everyone else can download the Source ZIP without a GitHub account and extract it
in full. See the [installation guide](installation.md).

The launcher reuses an existing 64-bit CPython 3.10–3.12 first. If none exists, the Skill must
explain the system-level change and obtain explicit consent before installing official Python 3.12
in user scope with winget. It never installs Origin automatically.

Codex needs only scoped access: read the complete repository, selected table, and optional reference
image; write to the repository, the current user's `$HOME\.codex\skills\editaplot`, and the source
data folder; run local `editaplot.cmd`, PowerShell, Python, and Origin in the same interactive
Windows user session; and use the network only for initial download/update and locked dependencies.
Normal use requires no administrator rights, mouse control, whole-drive write access, or DCOM,
registry, firewall, or Origin-installation changes.

If Codex detects that the current command is actually running under an isolated account, it stops
before Origin and submits a formal, narrowly scoped local-execution request for that exact
`origin-smoke` or `render` command. Codex may rerun the command only if that exact request is
approved. You may evaluate it when prompted, or the configured Codex auto-reviewer may evaluate it,
but approval is not guaranteed and auto-review does not pre-grant Origin access. You do not need to
copy it into your own PowerShell, use administrator rights, or change DCOM or the registry. This is
not a sandbox bypass; if a machine or organization policy rejects the request, the task stops
explicitly.

The local EditaPlot runtime and Origin automation do not initiate a network upload of selected data.
Files explicitly provided through Codex remain subject to the user's Codex account, organization,
and retention policies. Deidentify medical data and reference images and check burned-in text
before providing them; EditaPlot does not automatically detect PHI.

Then attach a CSV, TXT, XLS, or XLSX file in Codex and say:

```text
Use $editaplot to make an appropriate figure from this file. Check the environment and inspect the
data read-only. Recommend suitable charts, then classify every column as drawn, support/validation
only, retained without rendering, or uncertain. List the final figure elements and calculations that
will not be performed. Ask me to confirm the scientific purpose and this checklist; ask about uncertain
roles instead of guessing. Do not modify the source or silently invent, fit, normalize, or calculate data.
```

The equivalent command-line entry point is:

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

## What the Skill handles for a beginner

1. Discover the platform, compatible Python, project-local dependencies, and local Origin
   registration read-only; ask permission before installing Python when none is compatible.
2. Read column names, shape, units, types, missing values, and likely scientific roles without edits.
3. Recommend at most three charts from the question and data, with suitable palette choices.
4. Classify every column as primary render, visible support, support/validation only, retain without
   rendering, or uncertain, then list the proposed figure elements.
5. Confirm the scientific purpose and element checklist; ask additional questions only for real
   ambiguity such as column roles, error meaning, normalization, order, or dual axes.
6. Freeze an immutable-source plotting plan; a real smoke test starts a dedicated Origin instance,
   then rendering proceeds only after connection and capability checks pass.
7. Export OPJU, PNG, PDF, and TIF, then verify source hash, axes, fonts, layers, readback, and visual QA.

I keep the `inspect → recommend → understand → plan` pipeline behind the scenes. A beginner should
hear only what was detected, what will and will not be drawn, what is recommended, and what decision
still belongs to them.

## Precomputed SHAP data

When per-sample SHAP values already exist from Python, R, or a model-training workflow, the smallest
accepted long table has `Feature`, `SHAP value`, and `Feature value`. Optional roles are `Sample ID`,
`Feature Order`, `Mean absolute SHAP`, `Feature Group`, and `Group contribution (%)`; equivalent
Chinese column names are also recognized.

EditaPlot selects beeswarm-only, beeswarm with a top Mean |SHAP| axis, or the full grouped composite
from the roles actually present. If Mean |SHAP| or grouped percentages are absent but requested, I
first list the formula and lineage and wait for explicit approval of those derived items. The
within-feature color normalization and deterministic beeswarm offset are also disclosed in the
understanding checklist. The source file stays read-only. Use
[`medical_shap_summary.csv`](../examples/gallery/medical_shap_summary.csv) as a starting table.

## GSAS / GSAS-II XRD refinement data

For Powder or Publication CSV files, EditaPlot distinguishes:

- visible elements: 2θ, Observed, Calculated, plus supplied Background, Difference, and explicitly
  identified Phase ticks;
- support or retained columns: controls such as `weight`, `Q`, `Used`, `diff/sigma`, and `Axis-limits`;
- calculations it will not perform: deriving a background or difference, calculating Rwp/χ²,
  identifying phases, or assigning peaks.

A Publication CSV `Diff` that already contains its display position is drawn directly without a
second offset. Use [`example_gsas_powder.csv`](../runtime/templates/xrd/example_gsas_powder.csv) and
[`example_gsas_publication.csv`](../runtime/templates/xrd/example_gsas_publication.csv) to inspect
the accepted structures.

## When you want to follow a reference figure

Attach a local PNG, JPEG, or TIFF and add:

```text
Treat this reference figure only as a visual brief. Abstract its marks, layout, data encodings, and
safely adaptable style. Do not copy its data, labels, fits, phase assignments, logos, or watermarks,
and do not embed the bitmap. Ask separately whether I want exact series colors, line widths, fill
transparency, a page/aspect ratio, and legend show/hide, borderless, or position choices. My explicit
choice takes precedence over the reference. List each field as applied, template default retained,
rejected, or still unclear; call it applied only when the selected renderer can verify and read it
back. Then wait for my confirmation.
```

This is not an arbitrary one-to-one image replication feature. A reference cannot create evidence
missing from your data or promote support-only columns into visible marks. An essential feature that
the selected template cannot express safely blocks adaptation instead of being silently approximated.
For XPS, cosmetic choices also cannot change source data, column roles, the binding-energy direction,
component identity, or the verified single-region gradient-fill route.

### Shortest exact-style route for XPS

I suggest saying: “Use exact custom style: Raw `#173F5F`, Envelope `#C94C4C`, `2.4 pt` lines,
`38%` fill transparency, an `18 × 18 cm` page, and no legend or legend frame.” After confirmation,
I create a small JSON file and add `--visual-style-json xps-visual-style.json` to the plan command:

```json
{"series_colors":{"raw":"#173F5F","envelope":"#C94C4C"},"line_width_pt":2.4,"fill_transparency_percent":38,"page_size_cm":{"width":18,"height":18},"legend_visible":false,"legend_position":"none","legend_frame":false}
```

Exact values take precedence over the reference. I stop for correction when a field name, series,
or value is invalid; reference suggestions are instead reported field by field as applied, template
default retained, or rejected. None of these visual choices changes the scientific contract.

## When you are ready to render

If you use the command line directly, run the confirmed RenderPlan in this order:

```powershell
$smokeDir = Join-Path $env:TEMP ("EditaPlot-origin-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.\editaplot.cmd origin-smoke --output-dir $smokeDir
.\editaplot.cmd render .\render-plan.json
.\editaplot.cmd verify "<formal-output-directory>"
```

Inside Codex, you do not have to copy and run those PowerShell commands yourself. When the task is
sandboxed, Codex should submit one narrowly scoped request for the exact Origin command. If you
are prompted you may evaluate it, or the configured auto-reviewer may do so, but approval is not
guaranteed. Codex reruns that same command only after the exact request is approved; if policy
rejects it, Codex stops and explains instead of switching to administrator mode, editing DCOM/the
registry, or routing through an external PowerShell session.

I put `origin-smoke` before render so an EditaPlot-owned isolated Origin instance completes the
minimal graph-and-export loop first; Doctor's read-only discovery is never treated as a successful
live connection.

With the environment ready and necessary confirmation complete, finishing the local workflow within
about four or five minutes is a reasonable range. If no reply or permission is pending and no new
progress appears for 30–60 minutes, stop looped retries and use the
[installation and stage-diagnosis guide](installation.md#runtime-duration).
After a safely recoverable transient startup failure, the current runtime attempts to clean up the
EditaPlot-owned partial instance and makes one fresh-instance attempt only if cleanup succeeds.
Cleanup failure or a failed second activation stops the run; any approved retry must use a new empty
sibling output directory so the first report is preserved. Do not force-kill a Python worker merely
because it has run for a long time: it may be managing a hidden Origin instance. Preserve the
diagnostics and identify the last stage first.
When both activation and cleanup fail, the report keeps separate redacted code/stage pairs for the
primary activation and the cleanup. It contains no account name, local path, or raw COM text and
does not trigger another automatic retry.

Multiple Codex tasks may analyze data and prepare plans concurrently, but current EditaPlot workers
serialize their active `origin-smoke` / `render` sections within one signed-in Windows session.
Waiting tasks emit `origin_job_queue` progress about every 30 seconds; strict FIFO order is not
guaranteed. At 30 minutes only the waiter stops—the active holder is not killed. Windows releases
the lock when that process ends, and a completed Origin window kept open does not retain it. The
queue cannot coordinate manual scripts, older EditaPlot releases, or unrelated programs, so do not
submit a duplicate render when a queue message is visible.

```text
Use the confirmed plan. I do not need to open Origin first: run the real smoke test, start a
dedicated Origin instance, and continue according to the detected version and template capabilities.
Keep the editable Origin window open after success, export OPJU/PNG/PDF/TIF, and complete axis,
font, layer, data mapping readback, and human visual QA. If anything fails, summarize the technical
stage and next step. Do not report success from a PNG alone.
If the command stops only because it is in the Codex sandbox, submit a formal, narrowly scoped
local-execution request for that exact Origin command and rerun it only if the request is approved;
approval is not guaranteed. Do not ask me to copy PowerShell, use administrator rights, or change
DCOM or the registry.
```

The source file stays read-only. Missing measurements are never invented; helper columns may exist
only in memory or in the editable Origin workbook.
For an ordinary render, omit `--output-dir`. I have EditaPlot create
`<source_stem>_EditaPlot_<timestamp>` beside the original CSV, TXT, XLS, or XLSX file and keep the
RenderPlan, OPJU, PNG, PDF, TIF, object readback, and verification files together in that folder.
