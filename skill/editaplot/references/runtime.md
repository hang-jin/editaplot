# Runtime and launcher

## Contents

- [Supported environment](#supported-environment)
- [Use the launcher](#use-the-launcher)
- [Installation and diagnostics](#installation-and-diagnostics)
- [Beginner entry point](#beginner-entry-point)
- [Advanced commands](#advanced-commands)
- [Expected artifacts](#expected-artifacts)

## Supported environment

Support the CLI and locked dependency layer on physical Windows 10/11 x64 computers with 64-bit
CPython 3.10, 3.11, or 3.12. The live Origin end-to-end baseline is CPython 3.10 with Origin 2024b;
Python 3.11/3.12 rendering needs the same full-artifact verification before it is claimed.
Do not attempt setup on macOS (Intel or Apple Silicon), Linux, WSL, Wine/CrossOver, Parallels,
or other virtual machines. A local Origin/OriginPro application must expose a working Automation
entry when rendering is requested.
`doctor` cannot reliably detect every virtual machine, so ask the user to confirm a physical
Windows host whenever that fact is unknown. VMs remain unsupported in V1.

## Use the launcher

Prefer `editaplot.cmd` in the installed Skill directory. When operating in a cloned or extracted
repository, use the repository-root `editaplot.cmd`. Pass an absolute launcher path from Codex.
Do not ask a beginner to choose a Python executable or call `scripts/editaplot.py` directly.

The launcher first honors an explicitly configured compatible interpreter, then reuses an existing
valid EditaPlot managed environment. If neither is available, it probes Windows `py`, PATH, standard
installation locations, and the Python registry entries together, then selects the highest compatible
64-bit CPython from 3.10–3.12. It does not modify the selected base interpreter.

If no compatible candidate exists, explain that Python installation is a system-level change.
Inspect the exact package first:

```powershell
winget show --exact --id Python.Python.3.12 --source winget
```

Explain the selected publisher, source, and agreements. Only after the user explicitly approves
them, install the user-scope x64 package without an unattended prompt:

```powershell
winget install --exact --id Python.Python.3.12 --source winget --scope user --architecture x64 --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
```

These flags follow the [official WinGet install documentation](https://learn.microsoft.com/windows/package-manager/winget/install).

If winget is unavailable or fails, stop automatic installation and direct the user to the official
`https://www.python.org/downloads/windows/` page for 64-bit Python 3.12. Then run setup again. Never
use an untrusted mirror. This permission applies only to Python; never install or alter Origin.

## Installation and diagnostics

Run setup from a **complete repository**, never from a copied `skill/editaplot` folder:

```powershell
.\editaplot.cmd setup
.\editaplot.cmd --diagnose
.\editaplot.cmd doctor
.\editaplot.cmd doctor --repair
```

`setup` installs or updates the Skill, writes an untracked local runtime pointer, selects a compatible
Python, creates the project-local managed environment when required, installs only the locked audited
dependencies, and runs doctor again. The launcher itself does not install Python; the agent follows
the explicit-consent process above if Python is absent. Environment setup never installs or modifies
Origin; the render worker may connect to the existing application when a figure is requested.

`--diagnose` reports launcher/Python discovery. Doctor separately reports Windows, engine, dependency,
and local Origin Automation discovery. If `ready_for_render` is true, continue without asking for
another Origin confirmation. Actual callability is tested by the render worker. If the connection
fails, report the technical failure without guessing its cause.

## Beginner entry point

```powershell
.\editaplot.cmd start <file>
.\editaplot.cmd start <file> --intent "compare groups with uncertainty" --output start-session.json
```

`start` combines read-only inspection and ranked chart recommendation. Treat its JSON as agent-facing
state. Summarize recognition, up to three candidates, and confirmation questions in natural language;
do not expose the internal pipeline to a beginner.

## Advanced commands

```powershell
.\editaplot.cmd catalog
.\editaplot.cmd palettes
.\editaplot.cmd palettes --all
.\editaplot.cmd inspect <file> --output inspection.json
.\editaplot.cmd recommend <file> --intent "compare groups" --output recommendations.json
.\editaplot.cmd plan <file> --template-id bar --claim "Groups differ in response" --evidence-role comparison --palette-id ocean_coral --output render-plan.json
.\editaplot.cmd render render-plan.json
.\editaplot.cmd verify <output-directory>
.\editaplot.cmd panel-plan medical-panels.json --claim "The model is accurate, calibrated, and anatomically plausible" --output medical-panel-plan.json
```

The launcher forwards engine JSON to stdout. `--output` writes the same payload to disk where the
command supports it. Render forwards the engine worker's JSON-lines progress protocol. Use
`--engine-home <root>` only when an engine developer intentionally overrides runtime discovery.

## Expected artifacts

- `start-session.json`: source identity, recognized roles, ranked candidates, confidence, and gates.
- `inspection.json`: file identity, layout, and column profiles.
- `recommendations.json`: ranked candidates, confidence, reasons, and auto-selection gate.
- `render-plan.json`: source hash, figure contract, template, mapping, digest, and transform.
- Origin output directory: editable project, PNG/PDF/TIF exports, validation, provenance, and readback.
- `medical-panel-plan.json`: verified quantitative subproject hashes, attested image panels, distinct
  evidence roles, adaptive layout, shared color semantics, and blocking gates.

Never hand-edit an approved plan; regenerate it so the digest and decisions remain traceable.
`panel-plan` freezes layout only. It performs no medical image processing, automatic PHI detection,
or merged Origin rendering; individual verified OPJU files remain the editable evidence sources.
