# Support scope

EditaPlot V1 supports physical Windows 10/11 x64 computers only. Its CLI and locked dependency
layer are covered on 64-bit CPython 3.10, 3.11, and 3.12; the live Origin end-to-end baseline is
CPython 3.10 with Origin/OriginPro 2024b (10.15). Python 3.11/3.12 rendering still requires the
same local full-artifact verification before a route is claimed. macOS (Intel or Apple Silicon),
Linux, WSL, Wine/CrossOver, Parallels, and other virtual machines are outside the supported product
boundary. Other Origin versions, custom templates, new LabTalk
parameters, and new 3D routes require separate verification.

The launcher reuses an existing compatible Python and keeps packages in EditaPlot's project-local
environment. If no compatible Python exists, an agent may offer an official CPython 3.12 user-scope
installation only after the user explicitly approves that system change. This exception never
extends to Origin: environment repair does not install or modify Origin. Doctor performs read-only
discovery only. Before formal rendering, `origin-smoke` starts an EditaPlot-owned isolated Origin
instance and completes the minimal export loop. Formal rendering uses the same default ownership
model and does not require the user to open Origin first. Attaching to a user-owned interactive
Origin window is an explicit advanced mode only; EditaPlot detaches from that session instead of
resetting, overwriting, or closing it.

Codex needs read access to the complete repository and selected inputs, write access to the
repository, the current-user Codex Skill directory, and the source data folder, plus permission to
run the local launcher/Python and start Origin in the same interactive Windows session. Network
access is needed only for download/update and locked dependencies. Administrator rights, mouse
control, whole-drive write access, and DCOM/registry/firewall changes are outside the normal support
path.

A normal Codex command may first run under an isolated account. When EditaPlot reports
`origin_codex_sandbox_context`, the supported continuation is a formal, narrowly scoped Codex
local-execution request for the same exact `origin-smoke` or `render` command. That command is rerun
only if the exact request is approved, either by the user when prompted or by the configured Codex
auto-reviewer. Approval is not guaranteed, and auto-review does not pre-grant unrestricted Origin
access. Users should not be sent to a separate PowerShell window or asked for administrator rights,
DCOM/registry changes, or any sandbox bypass. An unknown Windows execution identity stops before COM
instead of being guessed.

Current EditaPlot workers serialize their active Origin smoke/render sections within one signed-in
Windows session; inspection and planning remain concurrent. Queue progress appears about every 30
seconds, strict FIFO is not guaranteed, and the 30-minute limit stops only the waiting worker. It
does not terminate the active holder. This coordination does not cover manual scripts, older
EditaPlot releases, or unrelated software.

For an ordinary render, omit `--output-dir`. The formal result is written to a unique
`<source_stem>_EditaPlot_<timestamp>` folder in the same directory as the source CSV, TXT, XLS, or
XLSX file. An alternate destination is supported only when the user explicitly requests it.

Support does not include installing, replacing, or modifying the Origin application. The user
remains responsible for scientific meaning, statistics, units, privacy, and final publication review.
When activation and cleanup both fail, support evidence should contain only the four redacted
primary/cleanup code-and-stage fields; do not request account names, local paths, raw HRESULTs, or
raw COM exception text in a public issue.

Community issues and contributions are welcome under the repository's open-source terms. Optional
paid consulting, customization, installation guidance, and support may be offered separately; they
do not restrict Apache-2.0 rights and do not include hosted, remote, or service-bureau automation.
