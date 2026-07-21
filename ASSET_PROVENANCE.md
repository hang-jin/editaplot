# Asset and data provenance

This open-source release contains only project-created teaching/verification fixtures and original
project assets.

The 2026-07-21 public-release review covered every listed CSV and PNG, including synthetic/generated
status, patient/clinical identifiers, labels, embedded PNG text/EXIF, and redistribution boundaries.
The manifest also binds the inventory builder and gallery fixture generator by SHA-256; changing
either script requires regenerating and manually reviewing the manifest.

- Every distributed CSV is synthetic. It is not experimental, patient, clinical, or production
  data and must not be interpreted as a scientific result.
- Gallery PNG files were exported by the verified local editable-figure workflow from those
  synthetic fixtures. The repository does not include the corresponding local logs, plans, OPJU,
  PDF, or TIF evidence.
- The PL/TRPL example uses neutral project-generated sample names and lifetimes; it does not copy
  the material labels or numeric values from the visual reference that motivated the chart family.
- The palette cards and selectors are original layouts generated from the machine-readable palette
  catalog. Reference covers, watermarks, logos, screenshots, and journal layouts are not included.
- The application icon is an original generic chart icon. The fixed XPS preview is generated from a
  synthetic template fixture.
- No distributed asset is presented as a Nature, Science, ACS, OriginLab, clinical, or journal
  specification or endorsement.

[`assets/provenance-manifest.json`](assets/provenance-manifest.json) freezes the SHA-256, size,
classification, synthetic-data status, and PNG text metadata for every tracked CSV and PNG. Rebuild
it with `tools/build_asset_provenance.py` and review the diff before each release.
