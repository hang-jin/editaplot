# Origin safety gate

## Environment

- Support Windows only.
- Require a locally installed, licensed, official Origin/OriginPro environment.
- Require the user to confirm that Origin starts manually before the first automated render.
- Treat Origin 2024b / 10.15 as the V1 supported version. Mark other versions unverified.
- Never troubleshoot cracks, patches, license bypasses, or redistributed Origin binaries.

## Execution

- Use the official external `originpro`/Origin Automation Server route.
- Never use mouse or screen-coordinate automation.
- Keep unverified LabTalk and X-Function experiments outside public renderers.
- Never use `-pfm 4` or unverified More Colors parameters.
- Keep the verified XPS fill route: one fill region, `set_fill_area(..., type=9)`, and `-pfm 3`.
- Preserve the stable XPS negative PlotX and label divide-by route; do not replace it with `x.reverse=1`.
- Do not write right/top-axis label properties known to contaminate the paired bottom/left axes.

## Data

- Hash the source before inspection and check it again before render.
- Never overwrite the source or add fabricated source columns.
- Store helper columns only in memory or the Origin workbook copy and report their purpose.
- Redact private absolute paths and Origin license details from public logs and examples.

## Experimental API rule

Before adding a new Origin graph route:

1. Read the local API playbook and official Origin documentation.
2. Build a minimal isolated experiment.
3. Save to a dedicated test output directory.
4. Require editable OPJU, all exports, object readback, and visual inspection.
5. Promote the route to `verified` only after all checks pass.
