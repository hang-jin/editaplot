# Third-party runtime notices

The Skill repair route may install NumPy, pandas, PyYAML, jsonschema, Matplotlib, originpro,
openpyxl, xlrd, Pillow, and their Python dependencies. The optional desktop runtime additionally
declares PySide6. Each dependency remains governed by its own license and notice. The current
Pillow 13.0.0 lock, historical 2026-07-21 Windows/Python 3.10 metadata provenance, and declared-only
UI boundary are recorded in [the dependency inventory](docs/dependency-inventory.md). The current
lock is not itself evidence of a newly verified installation or a redistributed binary bundle.
The separate six-case live-regression scope is recorded in [Support](SUPPORT.md), not inferred
from this dependency notice.

`originpro` and `OriginExt` are supplied by OriginLab for automating a separately installed Origin
application. This repository does not redistribute Origin.

The repository does not vendor third-party Python wheels or source archives. If a future binary,
offline dependency bundle, EXE, or installer redistributes those packages, the release process must
include the corresponding full license texts and notices from the exact redistributed artifacts.
PySide6 community wheels include Qt libraries; any future frozen EXE or installer must separately
verify the chosen Qt modules and satisfy the applicable LGPL/GPL obligations or use a valid Qt
commercial license.

The voluntary-support image at `assets/support/wechat-tip.png` includes WeChat/WeChat Pay
interface branding only to identify the payment method. WeChat and WeChat Pay names and marks
belong to their respective owner. Their appearance does not imply affiliation, sponsorship, or
endorsement of EditaPlot. The author-provided payment QR is intentionally published as support
contact information; it is not offered as a general-purpose reusable project asset.
