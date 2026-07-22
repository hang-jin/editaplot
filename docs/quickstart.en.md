# English quick start

## The 30-second version

Requirements: a physical Windows 10/11 x64 computer, 64-bit CPython 3.10–3.12, and a local
Origin/OriginPro application reachable through Automation. CLI/dependency coverage spans
all three Python minors; the current live Origin end-to-end baseline is CPython 3.10 + Origin 2024b.
macOS, Linux, WSL, Wine/CrossOver, Parallels, and other VMs are unsupported.

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

Then attach a CSV, TXT, XLS, or XLSX file in Codex and say:

```text
Use $editaplot to make an appropriate figure from this file. Check the environment and inspect the
data read-only. Recommend suitable charts and ask me to confirm a one-sentence scientific purpose;
ask additional questions only when meaning is ambiguous. Do not modify the source or silently invent,
fit, normalize, or calculate data.
```

The equivalent command-line entry point is:

```powershell
.\editaplot.cmd start "$HOME\Documents\my-data.csv"
```

## What the Skill handles for a beginner

1. Check the platform, compatible Python, project-local dependencies, and local Origin application;
   ask permission before installing Python when none is compatible.
2. Read column names, shape, units, types, missing values, and likely scientific roles without edits.
3. Recommend at most three charts from the question and data, with suitable palette choices.
4. Always confirm a one-sentence scientific purpose; ask additional questions only for real ambiguity
   such as error meaning, normalization, order, or dual axes.
5. Freeze an immutable-source plotting plan; render tests the local Origin Automation connection
   directly and then draws the figure.
6. Export OPJU, PNG, PDF, and TIF, then verify source hash, axes, fonts, layers, readback, and visual QA.

Do not make beginners operate an `inspect → recommend → plan` pipeline themselves. Keep those
steps behind the scenes and explain only what was detected, what is recommended, and what decision
still belongs to the user.

## When you are ready to render

```text
Use the confirmed plan and call the local Origin application directly. Keep the editable Origin
window open, export OPJU/PNG/PDF/TIF, and complete axis, font, layer, data mapping readback, and
human visual QA. If the connection fails, report only the technical error. Do not report success
from a PNG alone.
```

The source file stays read-only. Missing measurements are never invented; helper columns may exist
only in memory or in the editable Origin workbook.
