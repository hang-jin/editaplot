---
name: editaplot
description: Analyze local scientific CSV, TXT, XLS, or XLSX data; recommend publication-informed charts and Chinese scientific palettes; freeze a reproducible plan; and automate editable figures through a callable local Origin/OriginPro installation on physical Windows 10/11 x64. Use for beginner “drop in a file and draw it” requests; XPS, XRD, XAS, PL/TRPL, DSC, NMR, FTIR/IR, UV-Vis, electrochemistry, medical/AI evidence, distribution, relationship, error-bar, bar, stacked, pie, Sankey, radar, heatmap, or verified 3D workflows; project-local Python setup; palette selection; and OPJU/PNG/PDF/TIF verification. Do not use on macOS, Linux, WSL, Wine/CrossOver, Parallels, or other VMs; to install or modify Origin; to redistribute reference images; or to claim an unverified Origin route.
---

# EditaPlot

Turn a scientific question and a read-only table into an auditable, editable Origin figure. Keep
the beginner experience conversational; use the deterministic engine for inspection, planning,
rendering, exporting, and readback.

## Request only scoped Windows permissions

- Read the complete repository, selected table, and optional local reference image.
- Write only to the EditaPlot repository, the current user's Codex Skill directory, and the selected
  source file's parent folder for source-adjacent deliverables.
- Run the local launcher, PowerShell/Python subprocesses, and an EditaPlot-owned Origin instance in
  the same active interactive Windows user session.
- A normal Codex command may first run under an isolated account. If the Origin worker returns
  `origin_codex_sandbox_context`, submit a formal, narrowly scoped local-execution request for that
  exact `origin-smoke` or `render` command. Rerun it only if that exact request is approved, either
  by the user when prompted or by the configured Codex auto-reviewer. Approval is not guaranteed,
  and this handoff is not a sandbox bypass. Never ask the user to copy the command into a separate
  PowerShell window or broaden the request to administrator or system-configuration access.
- Use network access only for repository download/update and locked dependency retrieval. Treat a
  user-scope winget Python installation as a separate system change that still requires explicit
  consent.
- Do not request administrator rights, mouse control, whole-drive write access, cloud upload of
  private inputs, or DCOM, registry, firewall, user-group, or Origin-installation changes. When
  Controlled Folder Access, an organization policy, cloud sync, or a read-only location blocks
  writes, request access only to the affected folder or ask for an explicit alternate output folder.

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
   Treat style inferred from the reference as a suggestion, not as the user's instruction. Ask
   the user to choose one of three modes: keep the verified template default; use a confirmed,
   allow-listed approximation suggested by the reference; or provide exact custom values. For the
   exact mode, ask separately for colors, physical line width, fill transparency, page size, and
   legend visibility, frame, or position. An explicit user choice has precedence over a conflicting
   reference token. Freeze each reference suggestion as `applied`,
   `retained_template_default`, or `rejected`; never claim a request was applied unless the selected
   template has the same verified preview/Origin route and the required Origin object readback.
11. When color is user-selectable, run `editaplot.cmd palettes`, show
   `assets/palettes/palette-selector-public.zh-CN.png`, and recommend no more than two compatible
   `palette_id` values. Read `references/palettes.md` before freezing one.
12. Internally freeze the confirmed choice with `editaplot.cmd plan`; never hand-edit a plan or write
   a decision back to the source file. For an exact XPS request, write the confirmed values to a
   separate JSON object and pass its path with `--visual-style-json`. The supported exact fields are
   `series_colors`, `line_width_pt`, `fill_transparency_percent`, `page_size_cm`, `legend_visible`,
   `legend_position`, and `legend_frame`. Invalid explicit fields or values must fail fast and be
   corrected with the user; never silently discard them or fall back to a reference/default style.
   The render command copies this approved plan into the final output folder as `render-plan.json`.
13. Treat Origin readiness as technical state only. Doctor performs read-only discovery of
    `Origin.Application`, `Origin.ApplicationSI`, installed candidates, Python, `originpro`, and
    `OriginExt`; it never launches Origin and `ready_for_render` never means a live connection
    succeeded. If the default launch registration is present, proceed to the real pre-render smoke
    without asking the user to open Origin or confirm it again. Keep beginner output to one to three
    plain-language sentences; leave CLSIDs, registry views, candidates, and stages in JSON.
    Read the redacted `origin_execution_context` separately from `ready_for_render`. A
    `codex_sandbox` status requires the exact-command approval handoff above before COM is called;
    only an approved request may be rerun. Auto-review evaluates that individual request and does
    not pre-grant Origin access. An `unknown` Windows execution context is fail-closed and is not an
    approval request: stop before COM and report that the current Windows identity could not be
    verified.
14. Run `editaplot.cmd origin-smoke --output-dir <unique-smoke-directory>` with
    `launch_isolated`: start and own a dedicated Origin instance, perform the live smoke and version
    handshake, then apply the template capability decision. This command is mandatory after planning
    and before formal rendering. `attach_existing` is an explicit advanced mode only; never reset,
    overwrite, or close a user-owned project, and detach instead of exiting. Report failures by
    technical stage and next step without speculation.
    Never use mouse automation or provide application patches or bypass instructions. The runtime
    must attempt to clean a partial EditaPlot-owned activation and may try one fresh isolated
    instance for a retryable startup code only if cleanup succeeds. Cleanup failure returns
    `origin_activation_cleanup_failed` and stops. It must then wait with `sec -poc 30` and confirm
    `run.isOCready()` before reading the version or creating a project. Never loop, switch to
    `ApplicationSI`, edit DCOM/registry permissions, or tell a beginner to run the whole workflow as
    administrator. After the automatic attempt is exhausted, request approval for at most one retry
    in the same active Windows-user context and use a fresh empty sibling smoke directory so the
    first report remains intact. `origin_com_class_not_registered` and
    `origin_com_activation_access_denied` stop without automatic retry. Do not force-terminate a
    Python worker merely because it has run for a long time: it may own a hidden Origin instance.
    Preserve diagnostics and report the last progress stage before proposing any user-controlled
    cancellation.
    Keep the sandbox approval handoff distinct from an activation retry: the former happens before
    COM, while the latter is available only after the bounded activation/cleanup policy has run.
    When primary activation and cleanup both fail, expose only
    `primary_activation_code`, `primary_activation_stage`, `cleanup_error_code`, and
    `cleanup_error_stage`. Never include a Windows account name, local path, raw HRESULT, or raw COM
    text in that structured diagnostic payload, and never retry because both pairs are present.
    Current EditaPlot workers serialize only their active `origin-smoke` / `render` Origin section
    within one signed-in Windows session; data inspection, recommendation, and planning may remain
    concurrent. Respect `origin_job_queue` progress, which is emitted immediately when waiting and
    then about every 30 seconds. Ordering is not guaranteed to be strict FIFO. The 30-minute limit
    applies only to the waiting job: it stops that waiter without killing or interrupting the active
    holder. Do not submit a duplicate while a queue message is visible. Manual scripts, older
    EditaPlot releases, and unrelated programs are outside this coordination boundary.
15. Only after that smoke passes, render an allowed template route with
    `editaplot.cmd render <plan>`. Keep an EditaPlot-owned Origin instance open after success unless
    the user requests otherwise. By default, let the runtime create a direct sibling of the source
    file named `<source_stem>_EditaPlot_YYYYMMDD_HHMMSS`; keep all formal artifacts in that folder.
    Do not redirect ordinary runs to the repository, Skill directory, current working directory, or
    a shared global output folder. Use `--output-dir` only when the user explicitly requests another
    location.
16. Run `editaplot.cmd verify <output-directory>` against that source-adjacent folder and perform
    human visual QA. If smoke or render fails, a Python preview or standalone PNG/PDF/SVG is only
    a preview and must not be presented as completed Origin work. Formal success requires the
    editable OPJU, PNG, PDF, TIF, object readback, and human visual QA together.

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
- For XPS, keep cosmetic preferences separate from the scientific contract. A user may explicitly
  request exact series colors, physical line widths, fill transparency, a safe page/aspect ratio,
  and legend show/hide, borderless, or position choices. Apply only fields supported and read back
  by the selected verified XPS renderer; otherwise retain the default or reject the field visibly.
  Neither a user style request nor a reference image may change source values or column roles, the
  high-to-low binding-energy axis contract, component identity, residual disposition, or the
  verified single-region `set_fill_area(..., type=9)` / `-pfm 3` fill implementation.
- For SHAP, accept only externally precomputed per-sample contributions. Never train a model or
  invoke SHAP. Mean |SHAP| and optional group percentages may only summarize those supplied rows
  with the allow-listed formulas recorded in the semantic proposal and explicitly approved; never
  invent contributions or silently reorder features.
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
- 对于已验证的 `density_ridgeline3d`，我只接受 2–6 个真实带单位条件的 mixed-wide
  六角色表：上游提供同语义同单位的实线/虚线预计算密度，并为每组提供恰好一个 `Focal X`。
  焦点固定为 Z=0 基线 locator；不要计算 KDE、峰值、阈值、交点或焦点。当前主机还必须先通过
  实时 smoke 与 `OPEN_GL_3D` 能力检查，不能只凭模板已验证就跳过主机门禁。
- Do not send selected files to any additional network service or include them in public artifacts.
  A file explicitly provided through Codex remains subject to the user's Codex account,
  organization, and retention policies; do not claim the Skill can override those policies.
- Before inspecting medical data or reference images, require the user to confirm that the material
  follows their institution's rules, is deidentified, and has been checked for burned-in text.
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
- Let an explicit user style request outrank a style token inferred from a reference image. Color,
  line-width, transparency, page/aspect, and legend requests are still capability-gated and must be
  classified as applied, retained default, or rejected before rendering.
- Do not let a reference image or unverified cosmetic preference silently redefine semantic color
  mappings for XPS components, signed effects, heatmaps, diagnostic lines, confusion matrices, or
  similar evidence. An explicit replacement is allowed only through that route's independently
  verified override with exact series mapping and readback.
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
