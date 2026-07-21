# Runtime commands

The skill wrapper locates the source engine from `--engine-home`, the preferred
`EDITAPLOT_ENGINE_HOME`, or the legacy `EDITAPLOT_ENGINE_HOME` environment variable. A later commercial package may provide a frozen
engine executable without changing the Skill workflow.

## Commands

```powershell
python scripts/editaplot.py doctor --engine-home <root>
python scripts/editaplot.py doctor --repair --engine-home <root>
python scripts/editaplot.py catalog --engine-home <root>
python scripts/editaplot.py palettes --engine-home <root>
python scripts/editaplot.py palettes --all --engine-home <root>
python scripts/editaplot.py inspect <file> --engine-home <root> --output inspection.json
python scripts/editaplot.py recommend <file> --intent "compare groups" --engine-home <root> --output recommendations.json
python scripts/editaplot.py plan <file> --template-id bar --claim "Groups differ in response" --evidence-role comparison --palette-id ocean_coral --engine-home <root> --output render-plan.json
python scripts/editaplot.py render render-plan.json --confirm-origin-started --engine-home <root>
python scripts/editaplot.py verify <output-directory>
python scripts/editaplot.py panel-plan medical-panels.json --claim "The model is accurate, calibrated, and anatomically plausible" --output medical-panel-plan.json
```

All analysis commands write JSON to stdout. `--output` writes the same payload to disk. Render
forwards the engine worker's JSON-lines progress protocol.

`doctor --repair` is intentionally narrow. It creates `<root>/.editaplot-venv` and installs only
the audited Python dependency allowlist. It never installs, modifies, activates, patches, or licenses
Origin. Run doctor again with the returned managed Python before analysis or rendering.

## Expected artifacts

- `inspection.json`: file identity, layout, and column profiles.
- `recommendations.json`: ranked candidates, confidence, reasons, and auto-selection gate.
- `render-plan.json`: source hash, figure contract, template, mapping, plan digest, and transform.
- Origin output directory: editable project, exports, validation, provenance, and readback.
- `medical-panel-plan.json`: hashes of verified quantitative subprojects and attested image panels,
  unique A/B/C evidence roles, adaptive physical layout, shared color semantics, and blocking gates.

Do not hand-edit a plan after approval. Regenerate it so the digest and user decisions remain traceable.
`panel-plan` freezes layout only. It performs no medical image processing, automatic PHI detection,
or merged Origin rendering; the individual verified OPJU files remain the editable evidence sources.
