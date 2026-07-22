---
name: editaplot
description: Analyze local scientific CSV, TXT, XLS, or XLSX data; recommend publication-informed charts and Chinese scientific palettes; freeze a reproducible plan; and automate editable figures through a legally licensed local Origin/OriginPro installation on physical Windows 10/11 x64. Use for beginner “drop in a file and draw it” requests; XPS, XRD, XAS, PL/TRPL, UV-Vis, electrochemistry, medical/AI evidence, distribution, relationship, error-bar, bar, stacked, pie, Sankey, radar, heatmap, or verified 3D workflows; project-local Python setup; palette selection; and OPJU/PNG/PDF/TIF verification. Do not use on macOS, Linux, WSL, Wine/CrossOver, Parallels, or other VMs; to install or bypass Origin licensing; to redistribute reference images; or to claim an unverified Origin route.
---

# EditaPlot

Turn a scientific question and a read-only table into an auditable, editable Origin figure. Keep
the beginner experience conversational; use the deterministic engine for inspection, planning,
rendering, exporting, and readback.

## Start with the beginner path

1. Reject unsupported platforms before installing anything. Support the CLI/dependency layer only
   on physical Windows 10/11 x64 with 64-bit CPython 3.10–3.12. The live Origin end-to-end baseline
   is CPython 3.10 + Origin 2024b; require full-artifact verification before claiming rendering on
   another Python minor. State plainly that macOS (Intel/Apple Silicon), Linux, WSL,
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
   project-local Python dependency repair. Keep all Python packages in `.editaplot-venv`. Never
   install, modify, activate, patch, or license Origin.
6. Run `editaplot.cmd start <data-file>` for a new table. Add `--intent "<user intent>"` when the
   user states a goal. Treat its inspection and recommendation payload as internal working state.
7. Tell a beginner only: what was recognized, the best one to three chart choices, why they fit,
   and the smallest scientific decision still required. Do not dump an `inspect → recommend → plan`
   pipeline or raw JSON on them unless they ask for technical detail.
8. Always ask the user to confirm a one-sentence scientific purpose. When confidence is low,
   candidate margins are small, column roles or units are ambiguous, or a transformation such as
   percentage normalization is proposed, ask only the additional focused questions needed.
9. When color is user-selectable, run `editaplot.cmd palettes`, show
   `assets/palettes/palette-selector-public.zh-CN.png`, and recommend no more than two compatible
   `palette_id` values. Read `references/palettes.md` before freezing one.
10. Internally freeze the confirmed choice with `editaplot.cmd plan`; never hand-edit a plan or write
   a decision back to the source file.
11. Ask the user to confirm that their official, legally licensed Origin installation starts
    manually. Never use mouse automation, silently launch Origin, or handle installation, activation,
    cracks, patches, or license bypasses.
12. Render only through a verified route with `editaplot.cmd render <plan> --confirm-origin-started`.
    Keep Origin open unless the user requests otherwise.
13. Run `editaplot.cmd verify <output-directory>` and perform human visual QA. Do not report success
    from a PNG alone.

Before any render, read `references/origin-safety.md`, `references/figure-contract.md`, and
`references/verification.md`. For a new table or chart decision, read
`references/data-contracts.md` and `references/chart-selection.md`.

## Keep scientific decisions with the user

- Treat the original data file as immutable. Never overwrite it, fill missing source columns, or
  invent measurements. Permit helper columns only in memory or the editable Origin project.
- Distinguish scientific analysis from display transformation. Never silently normalize, smooth,
  fit, remove outliers, calculate error bars, identify phases, or infer material peaks.
- For SHAP, accept only externally precomputed per-sample contributions. Never train a model,
  invoke SHAP, infer feature importance, or silently reorder features inside the drawing workflow.
- Confirm unknown units, error semantics, percentage denominators, meaningful order, dual axes,
  and any other choice that can change the claim.
- Recommend from the scientific question and data structure, not aesthetics alone. Refuse a
  misleading chart even when technically renderable.
- Mark routes `verified`, `experimental`, or `unsupported`. Render automatically only through a
  verified Origin route.
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
transformations, plan path, OPJU/PNG/PDF/TIF paths, validation/readback paths, and any remaining human
check. For a beginner, translate internal identifiers into natural language and put technical paths
after the concise outcome.

## Load detailed references only as needed

- `references/runtime.md`: launcher, setup, Python discovery, CLI commands, and artifacts.
- `references/chart-selection.md`: chart families, ranking rules, and support levels.
- `references/data-contracts.md`: accepted layouts, column semantics, and repair guidance.
- `references/figure-contract.md`: evidence logic, visual hierarchy, typography, and color rules.
- `references/origin-safety.md`: licensed-environment and verified-API guardrails.
- `references/verification.md`: mandatory artifacts, readback, and visual QA.
- `references/showcase.md`: neutral demonstration data and gallery policy.
- `references/palettes.md`: Chinese palette selector, compatibility, and accessibility limits.
