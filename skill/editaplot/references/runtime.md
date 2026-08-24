# Runtime and launcher

## Contents

- [Supported environment](#supported-environment)
- [Permission preflight](#permission-preflight)
- [Use the launcher](#use-the-launcher)
- [Installation and diagnostics](#installation-and-diagnostics)
- [Origin connection policy](#origin-connection-policy)
- [Beginner entry point](#beginner-entry-point)
- [Advanced commands](#advanced-commands)
- [Timing and stall diagnosis](#timing-and-stall-diagnosis)
- [Expected artifacts](#expected-artifacts)

## Supported environment

Support the CLI and locked dependency layer on physical Windows 10/11 x64 computers with 64-bit
CPython 3.10, 3.11, or 3.12. Target Origin/OriginPro 2021 and later; Origin 2020b and earlier are
unsupported by the current external `originpro` route. The fully verified live baseline is
CPython 3.10 with Origin 2024b / 10.15. Other 2021+ versions are capability-gated, and
Python 3.11/3.12 rendering needs the same full-artifact verification before it is claimed.
Do not attempt setup on macOS (Intel or Apple Silicon), Linux, WSL, Wine/CrossOver, Parallels,
or other virtual machines. A local Origin/OriginPro application must expose a working Automation
entry when rendering is requested.
`doctor` cannot reliably detect every virtual machine, so ask the user to confirm a physical
Windows host whenever that fact is unknown. VMs remain unsupported in V1.

## Permission preflight

Request only the permissions needed for the current local workflow:

1. Read the complete EditaPlot repository, selected table, and optional reference image.
2. Write to the repository for `.editaplot-venv`, to the current user's Codex Skill directory for
   setup/update, and to the source data folder for the timestamped delivery directory.
3. Run the local batch launcher, PowerShell/Python subprocesses, and an EditaPlot-owned Origin
   process in the same active interactive Windows user session.
4. Use network access only for repository download/update and the locked dependency source.
   Obtain separate explicit consent before any user-scope winget Python installation.

Do not request administrator rights, mouse control, whole-drive access, private-data upload, or
DCOM, registry, firewall, user-group, or Origin-installation changes. When a protected folder,
organization policy, cloud-sync client, or security tool blocks writing, request access only to the
specific repository/data folder or ask the user for an explicit writable destination.

A normal Codex desktop command may initially run under an isolated account even when inherited
profile variables look like the signed-in user. The Origin worker checks its real Windows token and
stops before COM with `origin_codex_sandbox_context` when the current process is the Codex sandbox.
Codex must then submit a formal, narrowly scoped local-execution request for the same exact
`origin-smoke` or `render` command. Rerun it only if that exact request is approved, either by the
user when prompted or by the configured Codex auto-reviewer. Approval is not guaranteed; auto-review
evaluates one request and does not pre-grant unrestricted Origin access. This is not a sandbox
bypass. Do not send a beginner to a separate PowerShell window, request administrator rights, or
change DCOM, the registry, or other system configuration.

The bundled runtime and Origin process do not initiate a network upload of selected files. A file
explicitly supplied through Codex remains subject to the user's Codex account, organization, and
retention policies. Require deidentification and burned-in-text confirmation before inspecting
medical data or reference images; EditaPlot does not automatically detect PHI.

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
```

`setup` installs or updates the Skill, writes an untracked local runtime pointer, selects a compatible
Python, creates the project-local managed environment when required, installs only the locked audited
dependencies, and runs doctor again. The launcher itself does not install Python; the agent follows
the explicit-consent process above if Python is absent. Environment setup never installs or modifies
Origin. Users do not need to launch Origin before requesting a figure.

`--diagnose` reports launcher/Python discovery. Doctor separately reports Windows, engine, dependency,
and local Origin Automation registration discovery. It is read-only and never launches Origin.
`ready_for_render` means that the prerequisites for attempting the default isolated launch were
found; it is not a live-connection result. If it is true, continue to the real smoke without asking
the user to open or reconfirm Origin. Summarize the result in one to three sentences and retain
registry, candidate, and stage details in JSON.

Doctor also reports a redacted `origin_execution_context` status and
`requires_current_user_approval`. `ready_for_render=true` may appear together with
`origin_execution_context.status=codex_sandbox`: static prerequisites are present, but the real
Origin command still needs the exact-command approval handoff above. The approval may be rejected.
`origin_execution_context.status=unknown` is fail-closed and is not an approval request; stop before
COM and report that the Windows execution identity could not be verified. Never infer an account
name from `USERNAME`, `USERPROFILE`, or other inherited environment variables.

Use `.\editaplot.cmd doctor --repair` only when Doctor explicitly reports a missing or damaged
project-managed Python dependency. It is not part of the ordinary per-workflow command sequence and
does not repair, install, register, or modify Origin.

## Origin connection policy

Use this internal sequence:

1. Doctor discovers `Origin.Application`, `Origin.ApplicationSI`, installed candidates,
   `originpro`, and `OriginExt` without starting Origin.
2. Immediately before an Origin worker calls COM, it verifies the real Windows execution context.
   A detected Codex sandbox stops before COM and exposes the one-request approval recovery above;
   an unknown Windows context stops fail-closed.
3. Current EditaPlot workers acquire one session-local Origin job slot for their active smoke/render
   section. Data inspection, recommendation, and planning remain outside this slot.
4. The pre-render smoke uses `launch_isolated` to start an EditaPlot-owned dedicated instance,
   reads the actual version, waits for initialization, and verifies the minimum editable artifacts.
5. The capability layer reports the selected template as `verified`, `compatible_unverified`, or
   `blocked` for that host; a successful connection alone does not prove every template works.
6. Render proceeds only when the template route and host capability decision allow it.

`attach_existing` is an explicit advanced mode only. Never reset, overwrite, or close a user-owned
project; detach from that session instead. Only an EditaPlot-owned instance may create a fresh
project automatically or be closed by the runtime.

The Origin job slot is shared by current EditaPlot workers within one signed-in Windows session.
Waiting workers emit `origin_job_queue` immediately and then about every 30 seconds; acquisition is
not guaranteed to be strict FIFO. After 30 minutes, only the waiting worker stops with
`origin_job_queue_timeout`. The active holder is neither killed nor interrupted, and a completed
Origin window intentionally kept open does not retain the slot. Windows releases the slot when its
holder exits, including an unexpected exit. Manual scripts, older EditaPlot releases, and unrelated
programs are outside this boundary, so do not submit a duplicate smoke or render while a queue
message is visible.

If primary activation and cleanup both fail, the worker exposes only four stable diagnostic fields:
`primary_activation_code`, `primary_activation_stage`, `cleanup_error_code`, and
`cleanup_error_stage`. The structured payload must not contain a Windows account name, local path,
raw HRESULT, or raw COM text. Both pairs are evidence for diagnosis, not permission for another
automatic retry.

## Beginner entry point

```powershell
.\editaplot.cmd start <file>
.\editaplot.cmd start <file> --intent "compare groups with uncertainty" --output start-session.json
.\editaplot.cmd understand <file> --template-id <template-id> --output data-understanding.json
```

`start` combines read-only inspection and ranked chart recommendation. Treat its JSON as agent-facing
state. Summarize recognition, up to three candidates, and confirmation questions in natural language;
do not expose the internal pipeline to a beginner.

`understand` is the mandatory pre-plan semantic gate. It classifies every source column, proposes
visible figure elements and explicitly lists derived helpers and unresolved questions. If a corrected
column mapping is required, pass the same `--mapping-json` to both `understand` and `plan`. Ask the
user to confirm the short checklist, then pass the exact hash-bound
`confirmation_payload_template` back as `--semantic-confirmation-json`. A source or mapping change
invalidates that confirmation.

## Advanced commands

```powershell
.\editaplot.cmd catalog
.\editaplot.cmd palettes
.\editaplot.cmd palettes --all
.\editaplot.cmd inspect <file> --output inspection.json
.\editaplot.cmd recommend <file> --intent "compare groups" --output recommendations.json
.\editaplot.cmd understand <file> --template-id bar --output data-understanding.json
.\editaplot.cmd plan <file> --template-id bar --claim "Groups differ in response" --evidence-role comparison --semantic-confirmation-json <confirmed-json> --palette-id ocean_coral --output render-plan.json
.\editaplot.cmd reference-inspect <reference-image>
.\editaplot.cmd reference-review <reference-image> <reference-spec-json> --output reference-review.json
.\editaplot.cmd origin-smoke --output-dir <unique-smoke-directory>
.\editaplot.cmd render render-plan.json
.\editaplot.cmd verify <output-directory>
.\editaplot.cmd panel-plan medical-panels.json --claim "The model is accurate, calibrated, and anatomically plausible" --output medical-panel-plan.json
```

The launcher forwards engine JSON to stdout. `--output` writes the same payload to disk where the
command supports it. Render forwards the engine worker's JSON-lines progress protocol. Use
`--engine-home <root>` only when an engine developer intentionally overrides runtime discovery.
After `plan`, the required formal sequence is `origin-smoke → render → verify`; never skip the smoke
because Doctor reported `ready_for_render`.

Reference-image adaptation uses three separate inputs at plan time: the local image, the reviewed
strict ReferenceFigureSpec JSON, and its exact confirmation JSON. Codex constructs the declarative
grammar from visual inspection; the runtime does not OCR the image and never executes model-generated
Python, LabTalk, shell, or commands. Use `template_adaptation` for supported registered templates.
`controlled_composition` remains experimental and blocked until its exact Origin route is verified.

## Exact XPS visual choices

Before planning XPS, ask one short question: keep the template default, use a confirmed approximate
style suggested by the reference, or use exact custom values? The exact route is a separate,
user-confirmed visual contract; it does not weaken the frozen scientific contract.

A beginner can say this in natural language:

```text
请按我的精确样式画 XPS：Raw 用 #173F5F，Envelope 用 #C94C4C，所有数据线宽 2.4 pt，
填充透明度 38%，画幅 18 × 18 cm，隐藏图例。数据列、结合能方向、峰组分和拟合含义保持不变。
若有字段不支持或数值越界，请直接告诉我并停止，不要悄悄改回模板默认。
```

Translate only the confirmed visual values into a JSON file such as `xps-visual-style.json`:

```json
{
  "series_colors": {
    "raw": "#173F5F",
    "envelope": "#C94C4C",
    "Peak A": "#2A9D8F"
  },
  "line_width_pt": 2.4,
  "fill_transparency_percent": 38,
  "page_size_cm": {"width": 18, "height": 18},
  "legend_visible": false,
  "legend_position": "none",
  "legend_frame": false
}
```

`series_colors` maps an XPS role (`raw`, `background`, `envelope`, `residual`, `component`, or
`components`) or an actual visible source-column name to `#RRGGBB`. `line_width_pt` accepts 0.9–6.4,
`fill_transparency_percent` accepts 0–85, and each `page_size_cm` dimension accepts 12–40. The
verified `legend_position` values are `inside`, `outside_right`, `none`, and `adaptive`; legend
visibility and frame are booleans. `outside_right` keeps the contracted 24 pt legend readable by
reserving an 8 cm physical page column; pair it with a sufficiently wide page. A page/legend
combination that cannot keep both the plot and legend on the page fails visibly instead of
shrinking the font or moving the legend over the data. Then freeze the request at plan time:

```powershell
.\editaplot.cmd plan <xps-data.csv> --template-id xps --claim "<confirmed scientific claim>" --evidence-role "fit decomposition" --semantic-confirmation-json semantic-confirmation.json --visual-style-json xps-visual-style.json --output render-plan.json
```

Explicit values have precedence over a conflicting reference suggestion. Invalid explicit JSON,
unknown series keys, unsafe numeric values, or unsupported fields fail fast before Origin. A
confirmed reference approximation is evaluated field by field and may be applied, retain the
template default, or be rejected with a reason. In every mode, keep source values and column roles,
the high-to-low binding-energy axis, component identity, residual policy, and the verified
single-region `set_fill_area(..., type=9)` / `-pfm 3` fill route unchanged.

## Timing and stall diagnosis

Treat elapsed time as a sequence of independently observable stages, not one undifferentiated
"drawing time." The following triage bands are user-experience guidance, not a hardware-independent
service-level promise:

- On an already prepared environment, for an ordinary dataset after the required scientific
  confirmations have been supplied, local execution of the complete analysis, smoke, render,
  export, and verification sequence taking up to roughly **4–5 minutes** can be treated as normal.
- First-time repository download, `setup`, dependency installation, `doctor --repair`, time spent
  waiting for a user confirmation, and Codex conversation latency are separate. Do not charge them
  to Origin rendering.
- Time reported by `origin_job_queue` is also separate from the active holder's Origin execution.
  Its 30-minute bound is only the maximum wait for the queued worker; it is not a render timeout and
  never authorizes terminating the active holder.
- **30–60 minutes** without a pending user question and without a new local progress event is
  abnormal. Stop and identify the last completed stage instead of silently retrying the whole
  workflow.

Do not diagnose "slow network" from total time alone. Repository/dependency download uses the
network; ordinary `--diagnose`, `doctor`, `start`, `understand`, `origin-smoke`, `render`, and
`verify` are local engine operations. Codex service or network latency can delay when a command is
started or when its result reaches the conversation, but that is outside the EditaPlot runtime.

Keep these six timing groups separate:

| Timing group | Commands/events | What it measures |
| --- | --- | --- |
| Download and dependencies | repository update, `setup`, `doctor --repair` | Network transfer, package source, local environment creation |
| Environment diagnosis | `--diagnose`, `doctor` | Python discovery, runtime/dependency checks, read-only Origin registration discovery |
| Data understanding | `start`, `understand`, `plan`; render event `analyze_data` | Local file reading, role inference, recommendation, semantic-contract creation; exclude time waiting for the user's answer |
| Origin job queue | `origin_job_queue` | Time this worker waits for another current EditaPlot smoke/render section; 30 minutes limits only this waiter |
| Origin startup and connection | `origin-smoke`, `origin_smoke` progress event | Dedicated process activation, version handshake, initialization, minimum export loop |
| Drawing, export, and verification | render events `load_template`, `create_output_dir`, `validate_csv`, `launch_origin_draw_export_verify`, and `verify_outputs` | Local validation, dedicated Origin startup, workbook/graph construction, OPJU/PNG/PDF/TIF export, readback and artifact checks |

Smoke and render workers emit one JSON object per line. Every worker event contains
`elapsed_seconds`, measured with a monotonic clock from the start of that worker. It resets between
the smoke worker and the render worker; it is not the total Codex task duration. Terminal events are
bounded to 32 KiB, with compact scientific summaries only; complete plot specifications and Origin
readback remain in the output reports. Capture render
output without changing the data or plan:

```powershell
.\editaplot.cmd render .\render-plan.json 2>&1 |
  Tee-Object -FilePath .\render-progress.jsonl
```

Interpret the last event before a long pause:

- no launcher output: first run `--diagnose` directly; distinguish a command that never started
  from a slow worker;
- `setup` or dependency repair: inspect the package/download result and local environment lock;
- `origin_smoke`: the delay is in local Origin activation, handshake, initialization, or its
  minimum export loop;
- `load_template`, `create_output_dir`, or `validate_csv`: the delay is before scientific analysis
  or Origin startup;
- `analyze_data`: the delay is in local table loading, semantic preparation, layout, or plot-plan
  construction;
- `origin_job_queue`: another current EditaPlot worker owns the Origin slot. Keep waiting while
  progress arrives, do not submit a duplicate, and do not treat the 30-minute queue maximum as a
  render timeout or permission to kill the active holder;
- `launch_origin_draw_export_verify`: the runner is inside the Origin-owned combined operation.
  This honest coarse stage covers activation, workbook/graph construction, export, and Origin
  object readback because the worker cannot safely claim finer checkpoints it cannot observe;
- `verify_outputs`: Origin returned and the worker is checking the final artifact bundle, source
  hash, and compact terminal summary. Inspect write permissions, security scanning, and cloud-sync
  contention if this stage stalls.

Do not promise that every computer will finish inside five minutes, and do not blame the network
when local events show an Origin or filesystem stage. Report the command, last event type/step,
its `elapsed_seconds`, whether a confirmation was pending, and whether this was first-time setup.

For an ordinary render, omit `--output-dir`. The runtime creates a unique folder named
`<source_stem>_EditaPlot_YYYYMMDD_HHMMSS` directly beside the original CSV/TXT/XLS/XLSX file. This
keeps one dataset and all of its deliverables together instead of writing to the repository, Skill
directory, current working directory, or a shared global output location. Honor an explicit
`--output-dir` only when the user asks for a different destination. If the host exposes only a
temporary copy of an attachment, obtain the intended original folder from the user before rendering;
the temporary filename alone cannot reveal that folder safely.

## Expected artifacts

- `start-session.json`: source identity, recognized roles, ranked candidates, confidence, and gates.
- `inspection.json`: file identity, layout, and column profiles.
- `recommendations.json`: ranked candidates, confidence, reasons, and auto-selection gate.
- `data-understanding.json`: every source column's use, proposed figure elements, ambiguities,
  derived-item lineage, and a hash-bound confirmation template.
- `reference-review.json` when applicable: abstract reference grammar, adopted/rejected features,
  safety boundary, and a separate confirmation hash.
- `render-plan.json`: source hash, confirmed semantic contract, optional confirmed reference
  adaptation, figure contract, template, mapping, digest, and transform.
- Source-adjacent Origin output directory: copied `render-plan.json`, editable project,
  PNG/PDF/TIF exports, validation, provenance, and readback.
- `medical-panel-plan.json`: verified quantitative subproject hashes, attested image panels, distinct
  evidence roles, adaptive layout, shared color semantics, and blocking gates.

Never hand-edit an approved plan; regenerate it so the digest and decisions remain traceable.
`panel-plan` freezes layout only. It performs no medical image processing, automatic PHI detection,
or merged Origin rendering; individual verified OPJU files remain the editable evidence sources.
