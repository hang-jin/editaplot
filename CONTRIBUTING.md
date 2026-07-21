# Contributing

Thank you for helping improve this local, editable scientific-figure workflow.

## License

Unless you explicitly state otherwise, a contribution intentionally submitted for inclusion in this
project is provided under the Apache License 2.0, without additional terms. Submit only material you
have the right to contribute. Do not add journal artwork, proprietary templates, patient data,
Origin/OriginPro binaries, license files, activation material, or other third-party assets without a
documented redistribution right.

## Before a pull request

1. Open an issue before introducing a new chart family, dependency, Origin API, LabTalk parameter,
   statistical transformation, or data contract.
2. Use synthetic or fully deidentified test data. Never commit local paths, logs, credentials, PHI,
   private Origin project metadata, or user files.
3. Preserve input files byte-for-byte. Helper columns may exist only in memory or inside the editable
   project output.
4. Keep unverified Origin routes isolated. Consult official documentation first; do not use
   unverified `-pfm 4` or unsafe automation parameters in a production template.
5. For a verified render route, provide editable OPJU, PNG/PDF/TIF exports, object readback, source
   hashes, automated checks, and human visual QA. Only reviewed, metadata-safe PNG files belong in
   Git history.
6. Run the product tests and Skill validation. Describe the scientific claim, data contract, rejected
   alternatives, accessibility considerations, and version-specific Origin evidence in the PR.

## Scope and conduct

Keep changes focused and reviewable. Be respectful, evidence-led, and explicit about uncertainty.
This project does not support license bypasses, cracked software, fabricated measurements, hidden
normalization, or claims of journal endorsement.
