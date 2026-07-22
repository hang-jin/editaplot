# Third-party runtime notices

The Skill repair route may install NumPy, pandas, PyYAML, jsonschema, Matplotlib, originpro,
openpyxl, xlrd, Pillow, and their Python dependencies. The optional desktop runtime additionally
declares PySide6. Each dependency remains governed by its own license and notice. The verified
2026-07-21 Windows/Python 3.10 environment and declared-only UI boundary are recorded in
[the version-specific dependency inventory](docs/dependency-inventory.md).

`originpro` and `OriginExt` are supplied by OriginLab for automating a separately installed Origin
application. This repository does not redistribute Origin.

The repository does not vendor third-party Python wheels or source archives. If a future binary,
offline dependency bundle, EXE, or installer redistributes those packages, the release process must
include the corresponding full license texts and notices from the exact redistributed artifacts.
PySide6 community wheels include Qt libraries; any future frozen EXE or installer must separately
verify the chosen Qt modules and satisfy the applicable LGPL/GPL obligations or use a valid Qt
commercial license.
