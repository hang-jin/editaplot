# Origin Automation safety gate

## Compatibility scope and evidence

- The external route is Windows-only and targets a locally installed Origin or OriginPro 2021 or
  later. The current target matrix is 2021, 2021b, 2022, 2022b, 2023, 2023b, 2024, 2024b, 2025,
  2025b, 2026, and 2026b. Origin 2020b and earlier remain outside this route.
- Origin 2024b / 10.15 is the current complete end-to-end real-machine baseline. It is not a hard
  upper-version gate.
- Do not describe every other target version as verified. For any non-baseline build, compatibility
  is decided by the actual Automation handshake, the capabilities required by the selected
  template, and real output evidence from that machine.
- Real output evidence means a non-empty editable OPJU, PNG/PDF/TIF exports, required axis/text
  object readback, and human visual inspection. A successful import, version string, or PNG alone
  is insufficient.
- A recognized product or build may carry `known_version_risks`. These records only raise or
  normalize `probe_priority`; they never block a render by version number alone.
- If the product/build is unknown or the returned version value cannot be parsed while Automation
  remains callable, report `version_status=unknown`, use high probe priority, and run the complete
  capability probe. Never silently label that environment supported or verified.
- A genuine Automation handshake/readback failure remains a technical failure. Report the stable
  stage and error code without guessing why it failed.

## Environment boundary

- Readiness means technical callability only: package import, Automation connection, version
  readback when available, program-path readback, ready-state command, capability probes, and
  evidence production.
- Do not ask the user to confirm any non-technical product or account state. Those questions are
  outside the Skill's diagnostics.
- Doctor performs read-only discovery and does not launch Origin. The real pre-render smoke starts
  the dedicated instance and validates the live route.
- Never install, replace, patch, or modify the Origin application. Runtime dependency setup is
  limited to the project-local Python environment.

## Instance lifecycle

- Use the external `originpro` / Origin Automation Server route.
- Use `launch_isolated` / `new_isolated` by default. The Skill starts and owns a dedicated Origin
  instance, visible or hidden as needed; the user does not need to open an Origin window in advance.
- The isolated route follows the official `Application` behavior, which creates a new instance.
- Allow `attach_existing` only when explicitly requested. Do not create a project, call `new`, reset
  state, overwrite work, hide the window, or call `exit()` in a user-owned session; detach instead.
- Only an EditaPlot-owned instance may create a fresh project automatically or be closed by the
  runtime.
- Never use mouse or screen-coordinate automation.

## Version-sensitive rendering

- Treat graph defaults as version-sensitive. Origin 2025b changed page geometry, margins, text
  sizing, frames, line widths, and tick-label rotation defaults; write explicit style contracts and
  verify object state instead of relying on defaults.
- Keep version-risk records advisory. They prioritize focused probes such as label geometry,
  categorical ticks, error bars, secondary-axis titles, and reference-line rescaling.
- A known fixed build still receives its required probe at normal priority. A known affected or
  unknown build receives the probe at high priority.
- Never modify global Graph Options, system themes, or `@GGO` to make one render pass.

## Stable execution routes

- Keep unverified LabTalk and X-Function experiments outside public renderers.
- Never use `-pfm 4` or unverified More Colors parameters.
- Keep the verified XPS fill route: one fill region, `set_fill_area(..., type=9)`, and `-pfm 3`.
- Preserve the stable XPS negative PlotX and label divide-by route; do not replace it with
  `x.reverse=1`.
- Do not write right/top-axis label properties known to contaminate the paired bottom/left axes.

## Data and diagnostics

- Hash the source before inspection and check it again before render.
- Never overwrite the source or add fabricated source columns.
- Store helper columns only in memory or the Origin workbook copy and report their purpose.
- Redact private absolute paths and local Origin environment details from public logs and examples.
- Keep beginner-facing environment output to one to three plain-language sentences. Store detailed
  stages, detected Automation entries, candidates, risks, probes, and failures in local structured
  diagnostics.

## Experimental API rule

Before adding a new Origin graph route:

1. Read the local API playbook and the relevant official Origin documentation.
2. Build a minimal isolated experiment.
3. Save to a dedicated test output directory.
4. Require editable OPJU, PNG/PDF/TIF, object readback, and human visual inspection.
5. Promote the route to `verified` only after all checks pass.

## Official technical references

- External Python requirements and instance launch behavior:
  <https://docs.originlab.com/externalpython/>
- `Application`, `ApplicationSI`, and `ApplicationCOMSI` lifecycle differences:
  <https://docs.originlab.com/com/difference-of-application-applicationsi-and-applicationcomsi/>
- Official product/service-release and build table:
  <https://www.originlab.com/index.aspx?pid=3325>
- Origin 2025b graph-default changes:
  <https://docs.originlab.com/quick-help/why-graph-looks-different-in-2025b/>
