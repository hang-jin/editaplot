---
name: editaplot
description: Analyze local scientific CSV, TXT, XLS, or XLSX data; recommend publication-informed charts and Chinese scientific palettes; freeze a reproducible plan; and automate editable figures through a callable local Origin/OriginPro installation on physical Windows 10/11 x64. Use for beginner “drop in a file and draw it” requests; XPS, XRD, XAS, PL/TRPL, UV-Vis, electrochemistry, medical/AI evidence, distribution, relationship, error-bar, bar, stacked, pie, Sankey, radar, heatmap, or verified 3D workflows; project-local Python setup; palette selection; and OPJU/PNG/PDF/TIF verification. Do not use on macOS, Linux, WSL, Wine/CrossOver, Parallels, or other VMs; to install or modify Origin; to redistribute reference images; or to claim an unverified Origin route.
---

# EditaPlot

Turn a scientific question and a read-only table into an auditable, editable Origin figure. Keep
the beginner experience conversational; use the deterministic engine for inspection, planning,
rendering, exporting, and readback.

## Start with the beginner path

1. Reject unsupported platforms before installing anything. Support the CLI/dependency layer only
   on physical Windows 10/11 x64 with 64-bit CPython 3.10–3.12. Target Origin/OriginPro 2021 and
   later through external `originpro`; Origin 2020b and earlier are unsupported by this route.
   The fully verified live baseline is CPython 3.10 + Origin 2024b / 10.15. Treat another 2021+
   version as capability-gated, not automatically verified, until its smoke and complete artifacts
   pass. State plainly that macOS (Intel/Apple Silicon), Linux, WSL,
   Wine/CrossOver, Parallels, and other VMs are unsupported in V1. `doctor` cannot reliably detect
   every VM, so ask the user to confirm a physical Windows host when that fact is unknown.
2. Locate `editaplot.cmd` in the installed Skill directory; when working from a cloned repository,
   use the repository-root `editaplot.cmd`. Use an absolute launcher path in commands. Do not make
   beginners select a Python executable or invoke `scripts/editaplot.py` directly.
3. Require the complete repository for first installation. Run repository-root
   `editaplot.cmd setup`; never instruct users to copy only `skill/editaplot`, because that omits
   the runtime. Read `references/runtime.md` for setup, discovery, and command details.
4. Reuse an existing compatible Python. If none exists, explain in Chinese that installing Python
   is a system-level change. Run `winget show` first and explain the exact publisher, source, and
   agreements. Only explicit user confirmation permits a later non-interactive installation of
   `Python.Python.3.12` with user scope and x64 architecture. If winget is unavailable, provide the
   official python.org Windows installation instructions and wait for the user; never use an
   untrusted mirror or silently install Python.
5. Run `editaplot.cmd doctor` for each new workflow. Allow `doctor --repair` only for the reported
   project-local Python dependency repair. Keep all Python packages in `.editaplot-venv`. Treat
   Origin as a locally installed user-managed application; never install or modify it during repair.
6. Run `editaplot.cmd start <data-file>` for a new table. Add `--intent "<user intent>"` when the
   user states a goal. Treat its inspection and recommendation payload as internal working state.
   Use the original local source path exposed by the attachment. If the host provides only a
   temporary copied attachment and the original folder cannot be recovered, ask once for the intended
   local source/output folder before rendering; never guess an unrelated workspace destination.
7. After selecting a candidate template, run `editaplot.cmd understand <data-file>
   --template-id <id>` with the same confirmed mapping that will be used for planning. Group its
   result into a short checklist: data type; columns to draw; columns used only for support or
   validation; columns retained but not drawn; proposed figure elements; and calculations that
   will **not** be performed. Every source column must appear exactly once. If any item is
   `uncertain`, ask for a corrected mapping and run `understand` again; do not confirm or plan it.
8. Tell a beginner only: what was recognized, the best one to three chart choices, why they fit,
   and the smallest scientific decision still required. Do not dump an
   `inspect → recommend → understand → plan` pipeline or raw JSON unless they ask for technical
   detail.
9. Ask the user to confirm both a one-sentence scientific purpose and the concise element checklist.
   Freeze the exact `proposal_hash`, approved derived-item IDs, and resolved ambiguity choices in
   `--semantic-confirmation-json`. Never reuse a confirmation after the source, mapping, purpose, or
   proposal hash changes. When confidence is low, candidate margins are small, roles or units are
   ambiguous, or a display transformation is proposed, ask only the additional focused questions
   needed.
10. If the user supplies a reference figure, first run `reference-inspect`. Codex may then describe
   only its panel/mark/encoding/layout/style grammar in the strict ReferenceFigureSpec JSON and run
   `reference-review`; the runtime performs no OCR or model inference. Show the adopted and rejected
   features, bind every essential mark to confirmed renderable user data, and obtain a separate
   hash-bound confirmation. Never copy reference values, labels, fits, phase assignments, author
   text, logos, watermarks, or the bitmap into the Origin project. Prefer verified
   `template_adaptation`; keep `controlled_composition` blocked until that exact composition has
   passed the full Origin evidence gate. A reference cannot add missing evidence or change the
   confirmed scientific element list.
11. When color is user-selectable, run `editaplot.cmd palettes`, show
   `assets/palettes/palette-selector-public.zh-CN.png`, and recommend no more than two compatible
   `palette_id` values. Read `references/palettes.md` before freezing one.
12. Internally freeze the confirmed choice with `editaplot.cmd plan`; never hand-edit a plan or write
   a decision back to the source file. The render command copies this approved plan into the final
   output folder as `render-plan.json`.
13. Treat Origin readiness as technical state only. Doctor performs read-only discovery of
    `Origin.Application`, `Origin.ApplicationSI`, installed candidates, Python, `originpro`, and
    `OriginExt`; it never launches Origin and `ready_for_render` never means a live connection
    succeeded. If the default launch registration is present, proceed to the real pre-render smoke
    without asking the user to open Origin or confirm it again. Keep beginner output to one to three
    plain-language sentences; leave CLSIDs, registry views, candidates, and stages in JSON.
14. Use `launch_isolated` by default: start and own a dedicated Origin instance, perform the live
    smoke and version handshake, then apply the template capability decision. `attach_existing` is
    an explicit advanced mode only; never reset, overwrite, or close a user-owned project, and
    detach instead of exiting. Report failures by technical stage and next step without speculation.
    Never use mouse automation or provide application patches or bypass instructions.
15. Render an allowed template route with `editaplot.cmd render <plan>`. Keep an EditaPlot-owned
    Origin instance open after success unless the user requests otherwise. By default, let the
    runtime create a direct sibling of the source
    file named `<source_stem>_EditaPlot_YYYYMMDD_HHMMSS`; keep all formal artifacts in that folder.
    Do not redirect ordinary runs to the repository, Skill directory, current working directory, or
    a shared global output folder. Use `--output-dir` only when the user explicitly requests another
    location.
16. Run `editaplot.cmd verify <output-directory>` against that source-adjacent folder and perform
    human visual QA. Do not report success from a PNG alone.

Before any render, read `references/origin-safety.md`, `references/figure-contract.md`, and
`references/verification.md`. For a new table or chart decision, read
`references/data-contracts.md`, `references/chart-selection.md`, and
`references/semantic-understanding.md`. When a reference image is supplied, also read
`references/reference-figures.md`.

## Keep scientific decisions with the user

- Treat the original data file as immutable. Never overwrite it, fill missing source columns, or
  invent measurements. Permit helper columns only in memory or the editable Origin project.
- Classify every source column before planning as primary render, secondary render, support-only,
  retain-not-render, or uncertain. Support-only and retained columns cannot become visible through
  a reference image. An unknown numeric column is a question, not another automatic curve.
- Distinguish scientific analysis from display transformation. Never silently normalize, smooth,
  fit, remove outliers, calculate error bars, identify phases, or infer material peaks.
- For GSAS/GSAS-II Rietveld data, distinguish Observed, Calculated, optional Background, supplied
  Difference, explicit Phase positions, and non-rendering control/diagnostic columns. Preserve an
  upstream Publication `Diff` exactly; never apply a second display offset.
- For SHAP, accept only externally precomputed per-sample contributions. Never train a model,
  invoke SHAP, infer feature importance, or silently reorder features inside the drawing workflow.
- Confirm unknown units, error semantics, percentage denominators, meaningful order, dual axes,
  and any other choice that can change the claim.
- Recommend from the scientific question and data structure, not aesthetics alone. Refuse a
  misleading chart even when technically renderable.
- Keep template route status (`verified`, `experimental`, or `unsupported`) separate from current
  host compatibility (`verified`, `compatible_unverified`, or `blocked`). Never relabel a
  `compatible_unverified` Origin version as verified; continue only when its smoke succeeds and the
  selected template's required capabilities are available.
- Reject decorative 3D. Require a scientifically meaningful third axis; keep a new 3D route
  experimental until Z-axis, camera, OpenGL type, source mapping, four exports, editable OPJU,
  readback, and visual QA pass.
- Keep private data local. Do not upload it to a network service.
- Treat `panel-plan` as a deidentification-aware layout and evidence gate, not an OCR, PHI detector,
  medical image editor, or merged editable Origin project. Preserve every verified subproject.

## Apply the publication-informed contract

- Make every chart defend one explicit conclusion or evidence role.
- Use a white background, Arial, restrained color families, clear hierarchy, and no rainbow palette,
  decorative 3D, or unjustified grid.
- Derive physical Origin dimensions from chart type, data density, series count, and label length.
  Keep fixed size only for a profile that explicitly requires it, such as legacy fixed C 1s.
- Convert documented point, line-width, and page-size units correctly. Never copy small journal-page
  font values directly into Origin API fields; read back the resulting axis and text objects.
- Keep each condition's color consistent across related panels. Freeze palette IDs and exact HEX
  values, allowed modes, safe category count, and accessibility constraints into the plan.
- Do not let cosmetic preferences override semantic color contracts for XPS components, signed
  effects, heatmaps, diagnostic lines, confusion matrices, or similar evidence.
- Give every medical panel one distinct evidence role. Freeze a shared condition-to-color map before
  composing quantitative panels; require explicit semantic confirmation for a shared legend.
- Prefer editable labels and Origin objects. A Python preview or embedded bitmap is not an Origin
  deliverable.
- Call the result “publication-informed,” never “Nature compliant” or journal-approved.

## Report the result in plain language

Return the recognized data shape and roles, selected chart and alternatives, confidence and confirmed
transformations, source-adjacent output folder, copied plan, OPJU/PNG/PDF/TIF paths,
validation/readback paths, and any remaining human check. For a beginner, translate internal
identifiers into natural language, summarize environment state in one to three sentences, and put
technical paths after the concise outcome.

## Load detailed references only as needed

- `references/runtime.md`: launcher, setup, Python discovery, CLI commands, and artifacts.
- `references/chart-selection.md`: chart families, ranking rules, and support levels.
- `references/data-contracts.md`: accepted layouts, column semantics, and repair guidance.
- `references/semantic-understanding.md`: per-column use, element checklist, derived-data lineage,
  and the hash-bound confirmation gate.
- `references/reference-figures.md`: safe reference grammar, bindings, adaptation limits, and
  separate confirmation.
- `references/figure-contract.md`: evidence logic, visual hierarchy, typography, and color rules.
- `references/origin-safety.md`: local Automation and verified-API guardrails.
- `references/verification.md`: mandatory artifacts, readback, and visual QA.
- `references/showcase.md`: neutral demonstration data and gallery policy.
- `references/palettes.md`: Chinese palette selector, compatibility, and accessibility limits.
