# Origin 10.15 route acceptance

The route was promoted from an isolated Origin 2024b probe only after the following evidence passed:

- official `plotxyz` plot type 240 with `glTraject`;
- editable OPJU and non-empty PNG/PDF/TIF;
- `is3D=1`, `is3DGL=1`, `coortype=16`, camera readback;
- X/Y/Z scale, title, Arial font and point-size readback;
- three independent XYZ source mappings and direct `set -c` / `set -w` readback;
- unchanged source SHA-256 and human visual QA.

Local development evidence is retained outside the public source archive under the isolated probe
`test_outputs/origin_api_lab/trajectory3d_20260721/` and the formal high-density worker acceptance
`test_outputs/origin_api_lab/trajectory3d_showcase_20260721/`. The template reuses only those
verified operations. It performs no fit, equivalent-circuit calculation, resistance annotation, or
Waterfall integration.
