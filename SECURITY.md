# Security policy

Report suspected command-injection, path-disclosure, credential, unsafe dependency-installation, or
local automation issues through
[GitHub private vulnerability reporting](https://github.com/hang-jin/editaplot/security/advisories/new)
before public disclosure. Do not put credentials, private data, PHI, local paths, or exploit details
in a public issue.

The runtime never accepts arbitrary package names during repair, never uses shell command strings for
pip installation, and never installs or modifies Origin. Render plans are source-hash and plan-hash
bound. Do not publish `.env`, credentials, private paths, patient data, or raw development logs.

Grant Codex only repository-, current-user Codex Skill (`$HOME\.codex\skills\editaplot`)-, and
selected-data-folder access. Normal use does not require administrator rights, mouse control,
whole-drive access, or DCOM, registry, firewall, or Origin-installation changes. A request for those
privileges is not part of the supported recovery workflow and should be stopped and reviewed.

If an Origin worker identifies the Codex sandbox, it must stop before COM. The supported handoff is
a formal, narrowly scoped local-execution request for the same exact `origin-smoke` or `render`
command. The command may be rerun only after that exact request is approved; either a user prompt or
the configured Codex auto-reviewer may evaluate it, but approval is not guaranteed and does not
pre-grant broader Origin access. This is not a sandbox bypass. Do not replace it with a copied manual
PowerShell command, administrator execution, or DCOM/registry changes. An unverified Windows
execution identity is fail-closed.

The cross-process Origin job slot coordinates only current EditaPlot workers in one signed-in
Windows session. It does not authorize terminating the active process, and its 30-minute limit
applies only to a waiting worker. Manual scripts, older releases, and unrelated programs remain
outside that boundary.

Structured dual-stage startup diagnostics are allow-listed to
`primary_activation_code`, `primary_activation_stage`, `cleanup_error_code`, and
`cleanup_error_stage`. Do not add Windows account names, local paths, raw HRESULTs, raw COM text, or
arbitrary exception fields to this public channel.
