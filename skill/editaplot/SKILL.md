---
name: editaplot
description: Analyze local scientific CSV, TXT, XLS, or XLSX data; recommend publication-informed charts and Chinese scientific palettes; freeze a reproducible render plan; and automate editable figures in a licensed Windows Origin/OriginPro installation. Use when Codex needs to inspect tables; choose XPS, XRD, XAS, PL/TRPL, UV-Vis, electrochemistry, medical/AI evidence, distribution, relationship, error-bar, bar, stacked, pie, Sankey, radar, heatmap, or verified 3D workflows; invoke the EditaPlot engine; choose a palette; repair project-local Python dependencies; explain supported data formats; or verify OPJU/PNG/PDF/TIF outputs. Do not use to install or bypass Origin licensing, redistribute reference images, or claim an unverified Origin route.
---

# EditaPlot

Turn a scientific question and a read-only table into an auditable Origin figure. Let Codex
reason about intent and evidence; delegate parsing, rendering, exporting, and readback to the
deterministic EditaPlot engine.

## Run the workflow

1. Read `references/origin-safety.md`, `references/figure-contract.md`, and
   `references/verification.md` before any render.
2. Read `references/data-contracts.md` and `references/chart-selection.md` when inspecting a
   new table or recommending a chart.
3. Run `python scripts/editaplot.py doctor --engine-home <engine-root>` before every new workflow.
4. If doctor is not ready and `automatic_repair.available=true`, run
   `python scripts/editaplot.py doctor --repair --engine-home <engine-root>`. This may create only
   `<engine-root>/.editaplot-venv` and install the fixed audited Python allowlist. Re-run doctor
   with the returned `python_executable`. Never install, patch, activate, or license Origin.
5. If doctor reports Python, Windows, engine, Origin application, or licensing as a manual blocker,
   explain the exact blocker and stop before rendering.
6. Run `python scripts/editaplot.py inspect <data-file> --engine-home <engine-root>`.
7. State a provisional figure contract: conclusion, evidence role, comparison, axes,
   transformations, statistics, final outputs, and reviewer risk.
8. Run `python scripts/editaplot.py recommend <data-file> --intent "<user intent>" \
   --engine-home <engine-root>` and present up to three candidates with reasons.
9. Ask for confirmation when the recommendation reports low confidence, a small score margin,
   ambiguous column roles, or a display transformation such as percentage normalization.
10. When color is user-selectable, run `python scripts/editaplot.py palettes --engine-home
    <engine-root>`, show `assets/palettes/palette-selector-public.zh-CN.png`, and let the user choose
    a stable `palette_id`. Use `--all` only when advanced palettes are useful. Read
    `references/palettes.md` before freezing a palette.
11. Run `python scripts/editaplot.py plan <data-file> --template-id <id> \
    --claim "<one-sentence claim>" --evidence-role <role> --engine-home <engine-root> \
    --output <render-plan.json>`. Add user-confirmed `--x-title` and `--y-title` when exact axis
   wording is required. Add a confirmed `--palette-id <id>` only for a compatible route. These
   values are frozen into the plan and never written back to the source.
12. Confirm that the user has manually started their official Origin installation successfully.
13. Run `python scripts/editaplot.py render <render-plan.json> --confirm-origin-started \
    --engine-home <engine-root>`. Keep Origin open unless the user requests otherwise.
14. Run `python scripts/editaplot.py verify <output-directory>` and perform human visual QA.
15. For a medical multi-panel figure, verify every quantitative subfigure first, attest that each
    image panel is deidentified and checked for burned-in text, then run
    `python scripts/editaplot.py panel-plan <panel-config.json> --claim "<claim>" \
    --output <medical-panel-plan.json>`.

Use absolute paths in commands. Never use mouse automation.

## Enforce the decision gates

- Treat the original data file as immutable. Never overwrite it, fill missing source columns, or
  invent measurements. Allow helper columns only in memory or inside the editable Origin project.
- Distinguish scientific analysis from visual transformation. Do not silently normalize, smooth,
  fit, remove outliers, calculate error bars, or infer material peaks.
- For SHAP, accept only externally precomputed per-sample contributions. Never train a model,
  invoke SHAP, infer feature importance, or silently reorder features inside the drawing workflow.
- Prefer automatic recognition, but require the user to confirm low-confidence roles, unknown
  units, error semantics, percentage denominators, dual axes, or scientifically meaningful order.
- Recommend a chart from the question and data structure, not from aesthetics alone. Refuse a
  misleading chart even when it is technically renderable.
- Mark routes as `verified`, `experimental`, or `unsupported`. Render automatically only through
  a `verified` Origin route.
- Do not recommend decorative 3D. A third axis must encode a real experimental variable. Keep a
  new 3D route experimental until Z-axis, camera, OpenGL type, source mapping, four exports,
  editable OPJU, and human visual QA all pass.
- Never send private data to the network. Use local inspection and local Origin automation.
- Treat `panel-plan` as a deidentification-aware layout and evidence gate. It does not OCR or
  modify medical images, does not automatically detect PHI, and does not claim a merged editable
  Origin project. Keep every quantitative subproject and its verification evidence available.

## Apply the publication-informed contract

- Make every chart defend one explicit conclusion or evidence role.
- Use a white background, Arial, restrained color families, clear hierarchy, and no decorative
  3D, rainbow palette, or unjustified grid.
- Freeze an adaptive physical Origin contract from the chart type, data density, series count, and
  label length. Keep fixed dimensions only for profiles that explicitly require them, such as the
  legacy fixed C 1s contract. Do not substitute small journal-page font values directly for Origin
  API values; respect and read back the documented point, line-width, and page-size units.
- Keep the same scientific condition in the same color across related panels.
- Freeze palette IDs and exact HEX values in the render plan. Respect each palette's allowed mode,
  maximum safe qualitative group count, color-vision risk, and redundant-encoding requirement.
  XPS, signed-effect, heatmap, diagnostic, and other semantic color contracts are not cosmetic overrides.
- Give every medical panel one distinct evidence role. Multiple quantitative panels must freeze
  one shared condition-to-color map before composition; shared legends require explicit semantic
  confirmation.
- Prefer editable labels and Origin objects. A Python preview or embedded bitmap is not a valid
  Origin deliverable.
- Call the result “publication-informed,” not “Nature compliant” or journal-approved.

## Report the result

Return:

- detected data shape and column roles;
- the chosen chart and rejected alternatives;
- confidence, confirmation decisions, and display transformations;
- the figure contract and plan path;
- OPJU, PNG, PDF, TIF, validation report, and Origin readback paths;
- remaining human visual checks or unsupported requests.

Do not report success from a PNG alone.

## Load detailed references only as needed

- `references/runtime.md`: CLI commands, JSON artifacts, exit behavior, and engine discovery.
- `references/chart-selection.md`: chart families, ranking rules, and support levels.
- `references/data-contracts.md`: accepted layouts, column semantics, and repair guidance.
- `references/figure-contract.md`: evidence logic, visual hierarchy, typography, and color rules.
- `references/origin-safety.md`: licensed-environment and verified-API guardrails.
- `references/verification.md`: mandatory artifacts, readback, and visual QA.
- `references/showcase.md`: neutral demonstration dataset and gallery policy.
- `references/palettes.md`: Chinese palette selector, compatibility, and accessibility limits.
