# Changelog

## 2026-08-01 — Flexible, verified XPS visual styling

- Split the XPS contract into an immutable scientific layer and an independently confirmed visual
  layer. Users may now choose the verified template default, a confirmed approximation suggested
  by a reference figure, or exact custom values without changing source roles or XPS semantics.
- Added exact XPS controls for visible series colors, physical line width, fill transparency,
  physical page size, and legend visibility, frame, and position. Explicit user choices take
  precedence over reference suggestions; invalid exact fields fail before Origin instead of
  silently reverting to a default.
- Updated both adaptive and fixed C 1s Origin runners and the shared preview to consume the same
  visual contract. The runners read back page/layer geometry, Arial typography, line widths,
  series/fill colors, transparency, and editable legend state before reporting success.
- Kept the scientific and API safety contracts unchanged: immutable source data, high-to-low
  binding-energy display, fixed C 1s `PlotX=-BindingEnergy` with `divideBy=-1`, residual retention,
  and the single-region `type=9` / `-pfm 3` two-color fill route.
- Preserved the physical title margins when a custom page width is requested, and reserved an
  8 cm physical column for a readable 24 pt outside-right legend. Too-narrow combinations fail
  visibly rather than clipping or shrinking contracted fonts.
- Fixed the runner boundary for confirmed retain-not-render columns. Such columns remain unchanged
  in an editable `XPS Source Snapshot` worksheet but never enter plot or helper-series logic.
- Verified both XPS routes with Origin 2024b: an adaptive 19 × 19 cm hidden-legend case completed in
  12.4 seconds, and a fixed C 1s 28 × 19 cm outside-right borderless-legend case completed in
  17.6 seconds; each produced editable OPJU plus PNG/PDF/TIF and passed object readback and visual
  inspection.

## 2026-07-31 — Circular-network route and stage timing

- Added a verified multi-panel circular directed weighted network route for `Panel + Source +
  Target + Weight` edge lists, with optional sign, node-group, and edge-label columns.
- Kept node positions stable across panels, applied one global weight-to-line-width scale, and
  rendered editable Origin curves, terminal arrow objects, direct labels, and a borderless legend.
- Promoted the route only after a real Origin 2024b run produced OPJU, PNG, PDF, and TIF artifacts,
  passed object/font/color/size readback, preserved the source table, and passed image-bound human
  visual review.
- Added monotonic `elapsed_seconds` to worker progress events and documented stage-level diagnosis:
  up to roughly four or five minutes is a reasonable normal range for an already prepared
  ordinary workflow, while a silent 30–60 minute wait is abnormal and should be localized before
  retrying.
- Kept full Origin readback in `origin_verify_report.json` while making the terminal success event
  concise.
- Expanded the public inventory to 39 plotting routes, 46 reviewed verification PNGs, and 44
  displayed examples.

## 2026-07-30 — Scientific understanding, compatibility, and release hardening

- Added a confirmation-first scientific understanding layer that classifies every source column as
  plotted evidence, visible support, calculation/validation only, retained without rendering, or
  unresolved before a RenderPlan can be approved.
- Added safe reference-figure adaptation: local PNG/JPEG/TIFF files may guide compatible figure
  grammar and restrained style choices, but never supply copied data, text, fits, phases, logos,
  watermarks, or a promised 1:1 reproduction.
- Expanded the Origin/OriginPro 2021–2026b compatibility layer with isolated-instance startup,
  live version handshake, per-template capability decisions, stable Automation errors, and explicit
  reporting that 2024b remains the only complete live baseline.
- Added and verified materials routes and data contracts for GSAS/GSAS-II XRD Rietveld, XAS,
  PL/TRPL, DSC, NMR, FTIR/IR, UV–Vis/Tauc, XPS comparison, and high-density heatmaps.
- Consolidated the public gallery around 38 Origin plotting routes, 45 reviewed verification PNGs,
  and 43 displayed cases. The gallery now shows one Origin-rendered 30×30 dense heatmap while
  retaining the smaller and 40×40 cases only as regression evidence.
- Documented the minimum Codex permissions for Windows beginners, source-adjacent delivery folders,
  Python discovery and consent boundaries, and a clearer split between local runtime behavior and
  the user's Codex account or organization data policy.
- Hardened setup, worker launch, GUI subprocess environment inheritance, smoke-output preparation,
  source-adjacent delivery writes, and path redaction so common Windows policy, antivirus, cloud
  sync, missing-executable, and permission failures return short stable errors instead of tracebacks
  or a stalled interface.
- Added final release gates for public-template alignment, hidden regression-gallery entries,
  runtime and asset manifests, provenance exactness, Windows permissions, and dense-heatmap layout.
- Added a final optional “buy me a coffee” section to both READMEs using an author-approved,
  metadata-free WeChat Pay QR image. Tips do not unlock features, change support priority, or alter
  Apache-2.0 rights.

## 2026-07-22 — Beginner onboarding and simplified public release

- Added a Windows launcher that discovers a compatible 64-bit CPython 3.10–3.12 even when the
  user's default `python` command is missing, stale, or points to an unsupported version.
- Added idempotent `editaplot.cmd setup`: it installs or updates the Skill, records the complete
  bundled runtime, prepares an audited project-local environment, and runs a post-setup doctor.
- Added guarded migration for complete pre-bootstrap EditaPlot installations; unrelated or
  incomplete non-empty directories remain protected from overwrite.
- Strengthened doctor with a single Python compatibility policy and read-only Origin Automation
  discovery. Origin readiness is technical only: render performs the actual connection attempt,
  without an additional Origin confirmation gate.
- Added a beginner `start` workflow for read-only data recognition, ranked chart suggestions, and
  plain-language scientific confirmation before any plan or render is created.
- Made the V1 boundary explicit: physical Windows 10/11 x64 only; macOS, Linux, WSL,
  Wine/CrossOver, Parallels, and other VMs are unsupported.
- Added a compact GitHub Star badge and privacy-first daily trend. The updater reads only GitHub's
  aggregate `stargazers_count`, stores date plus total count, and never requests account identities
  or personal Star timestamps.
- Changed the default render destination to a unique `<source_stem>_EditaPlot_<time>` folder beside
  the original table, with the approved RenderPlan copied into the complete artifact set.
- Extended public CI coverage to CPython 3.10, 3.11, and 3.12 while preserving the existing
  `windows-python-310` protected-branch check.

## 2026-07-21 — Initial open-source release

- Adopted the neutral public brand **EditaPlot**, repository slug `editaplot`, and Skill ID
  `editaplot`; released project-owned work under Apache-2.0.
- Added 10 machine-checkable scientific palettes, an eight-palette Chinese launch selector,
  advanced-risk metadata, palette compatibility gates, and RenderPlan/worker palette freezing.
- Added doctor repair tiers and project-local Python dependency repair without installing or
  modifying Origin.
- Bundled a minimal self-contained EditaPlot rendering runtime with a SHA-256 manifest.
- Added bilingual README/quick starts, prompts, privacy/security/support/release boundaries, a
  version-specific dependency inventory, and a GitHub-safe gallery of 37 reviewed Origin PNG examples.
- Added explicit public-versus-commercial release gates for irreversible GitHub disclosure,
  OriginLab commercial-automation/trademark clarification, and PySide6/Qt redistribution.
- Promoted the verified `trajectory3d` route for explicit `Zreal + real third variable with unit +
  -Zimag + Series` long tables after editable OPJU, PNG/PDF/TIF, 3D object readback, source-hash,
  and human visual QA passed.
- Verified the official Origin 3D Waterfall API in isolation; kept it experimental because visible
  OpenGL fill/edge colors did not match successful object-level color-list readback.
