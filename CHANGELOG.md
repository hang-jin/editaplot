# Changelog

## 2026-07-22 — Beginner onboarding and public repository metrics

- Added a Windows launcher that discovers a compatible 64-bit CPython 3.10–3.12 even when the
  user's default `python` command is missing, stale, or points to an unsupported version.
- Added idempotent `editaplot.cmd setup`: it installs or updates the Skill, records the complete
  bundled runtime, prepares an audited project-local environment, and runs a post-setup doctor.
- Added guarded migration for complete pre-bootstrap EditaPlot installations; unrelated or
  incomplete non-empty directories remain protected from overwrite.
- Strengthened doctor with a single Python compatibility policy and read-only Origin COM
  registration discovery; Origin licensing and manual startup remain explicit user confirmations.
- Added a beginner `start` workflow for read-only data recognition, ranked chart suggestions, and
  plain-language scientific confirmation before any plan or render is created.
- Made the V1 boundary explicit: physical Windows 10/11 x64 only; macOS, Linux, WSL,
  Wine/CrossOver, Parallels, and other VMs are unsupported.
- Added a privacy-preserving GitHub Star history generator and scheduled workflow that publishes
  only aggregate metrics to a separate `metrics` branch and does not request the access-restricted
  stargazer listing during automated runs.
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
