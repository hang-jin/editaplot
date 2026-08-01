# Asset and data provenance

This open-source release contains project-created teaching/verification fixtures, original project
assets, and one author-provided support-payment QR image that the author explicitly approved for
public display.

The 2026-07-30 public-release review covered every listed CSV and PNG, including synthetic/generated
status, patient/clinical identifiers, labels, embedded PNG text/EXIF, payment-identifier intent, and
redistribution boundaries.
The manifest also binds the inventory builder and gallery fixture generator by SHA-256; changing
either script requires regenerating and manually reviewing the manifest.

The promoted release inventory retains 47 verified PNG assets across 40 public plotting routes. The public
page displays 45 cases. The two non-displayed heatmap PNGs remain only as regression and audit
history; they are not alternate public showcase entries.

- Every distributed CSV is synthetic. It is not experimental, patient, clinical, or production
  data and must not be interpreted as a scientific result.
- The two GSAS/GSAS-II XRD fixtures are project-authored teaching tables. They contain no patient,
  clinical, instrument-account, or third-party experimental records.
- Gallery PNG files were exported by the verified local editable-figure workflow from those
  synthetic fixtures. The repository does not include the corresponding local logs, plans, OPJU,
  PDF, or TIF evidence.
- The PL/TRPL example uses neutral project-generated sample names and lifetimes; it does not copy
  the material labels or numeric values from the visual reference that motivated the chart family.
- The DSC, NMR, FTIR/IR, XPS comparison, UV–Vis, PL temperature-series, 3D trajectory,
  3D dual-density baseline-locator, and dense
  matrix fixtures are deterministic project-authored teaching data. The public gallery displays
  the real Origin-rendered 30×30 matrix only; the smaller annotated matrix and 40×40 matrix remain
  in the retained verification inventory. None reproduces values, labels, conclusions, arrows,
  logos, or layouts from supplied paper screenshots.
- The palette cards and selectors are original layouts generated from the machine-readable palette
  catalog. Scientific gallery and palette assets do not include reference covers, watermarks, logos,
  screenshots, or journal layouts.
- `assets/support/wechat-tip.png` is an author-provided WeChat Pay support QR image, intentionally
  published as the voluntary support destination shown at the end of both READMEs. It is not
  scientific data, a user upload, or a reusable plotting asset. It contains a masked payee display
  name and payment-interface branding by design, but no EXIF or PNG text metadata and no PHI.
  WeChat/WeChat Pay names and marks remain the property of their respective owner and are shown only
  to identify the payment method.
- The application icon is an original generic chart icon. The fixed XPS preview is generated from a
  synthetic template fixture.
- No distributed asset is presented as a Nature, Science, ACS, OriginLab, WeChat, clinical, or
  journal specification, affiliation, or endorsement.

[`assets/provenance-manifest.json`](assets/provenance-manifest.json) freezes the SHA-256, size,
classification, synthetic-data status, and PNG text metadata for every tracked CSV and PNG. Rebuild
it with `tools/build_asset_provenance.py` and review the diff before each release.
