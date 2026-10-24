# Python dependency inventory

The current secure lock targets physical Windows 10/11 x64 with 64-bit CPython 3.11/3.12 and
Pillow 13.0.0; 3.12 is recommended for new installations. The table records locked versions, not
a newly measured installation or a new Origin live-verification claim. The original installed
metadata snapshot was collected for the 2026-07-21 Windows/Python 3.10 release with Pillow 12.3.0;
that snapshot and its Origin 2024b evidence are historical, not the current secure-runtime policy.
Third-party projects do not endorse EditaPlot merely by appearing here.

The separately verified six-case CPython 3.12.14 / Origin 2024b regression is scoped in
[Support](../SUPPORT.md); it does not turn this lock table into a fresh installed-metadata inventory
or verify every route, Origin version, or Python 3.11 host.

The current repository does not vendor these packages. `doctor --repair` installs exact direct
versions into a project-local virtual environment and constrains transitive resolution with
`requirements-runtime.lock`. Python 3.10 is no longer a supported secure runtime. Setup retains
replaced project environments for recovery records but does not automatically run their old
dependency sets. A release, offline bundle, or executable must verify the inventory and notices
against the exact artifacts being installed or redistributed.

| Package | Locked version | Relationship | Declared license family | Project |
|---|---:|---|---|---|
| NumPy | 1.26.4 | direct | BSD-3-Clause | [numpy.org](https://numpy.org/) |
| pandas | 2.3.3 | direct | BSD-3-Clause | [pandas.pydata.org](https://pandas.pydata.org/) |
| PyYAML | 6.0.3 | direct | MIT | [pyyaml.org](https://pyyaml.org/) |
| jsonschema | 4.26.0 | direct | MIT | [source](https://github.com/python-jsonschema/jsonschema) |
| Matplotlib | 3.10.9 | direct | Matplotlib license (PSF-based) | [matplotlib.org](https://matplotlib.org/) |
| originpro | 1.1.15 | direct | BSD | [OriginLab](https://www.originlab.com/) |
| openpyxl | 3.1.5 | direct | MIT | [documentation](https://openpyxl.readthedocs.io/) |
| xlrd | 2.0.2 | direct | BSD | [python-excel](https://www.python-excel.org/) |
| Pillow | 13.0.0 | direct | MIT-CMU | [documentation](https://pillow.readthedocs.io/) |
| attrs | 26.1.0 | transitive | MIT | [attrs.org](https://www.attrs.org/) |
| contourpy | 1.3.2 | transitive | BSD-3-Clause | [source](https://github.com/contourpy/contourpy) |
| cycler | 0.12.1 | transitive | BSD-3-Clause | [project](https://matplotlib.org/cycler/) |
| et_xmlfile | 2.0.0 | transitive | MIT | [source](https://foss.heptapod.net/openpyxl/et_xmlfile) |
| fonttools | 4.63.0 | transitive | MIT | [source](https://github.com/fonttools/fonttools) |
| jsonschema-specifications | 2025.9.1 | transitive | MIT | [documentation](https://jsonschema-specifications.readthedocs.io/) |
| kiwisolver | 1.5.0 | transitive | BSD-3-Clause | [source](https://github.com/nucleic/kiwi) |
| OriginExt | 1.2.5 | direct | BSD | [OriginLab](https://www.originlab.com/) |
| packaging | 26.2 | transitive | Apache-2.0 OR BSD-2-Clause | [documentation](https://packaging.pypa.io/) |
| pyparsing | 3.3.2 | transitive | MIT | [documentation](https://pyparsing-docs.readthedocs.io/) |
| python-dateutil | 2.9.0.post0 | transitive | Apache-2.0 OR BSD-3-Clause | [source](https://github.com/dateutil/dateutil) |
| pytz | 2026.2 | transitive | MIT | [project](https://pythonhosted.org/pytz/) |
| referencing | 0.37.0 | transitive | MIT | [documentation](https://referencing.readthedocs.io/) |
| rpds-py | 0.30.0 | transitive | MIT | [documentation](https://rpds.readthedocs.io/) |
| six | 1.17.0 | transitive | MIT | [source](https://github.com/benjaminp/six) |
| typing_extensions | 4.16.0 | transitive | PSF-2.0 | [source](https://github.com/python/typing_extensions) |
| tzdata | 2026.3 | transitive | Apache-2.0 | [source](https://github.com/python/tzdata) |

## Declared desktop-UI dependency

`runtime/pyproject.toml` declares the separately verified `PySide6==6.6.3.1` optional desktop dependency;
the corresponding environment used `shiboken6`, `PySide6-Essentials`, and `PySide6-Addons`
`6.6.3.1`. PySide6 is not installed by the Skill's `doctor --repair` route. Qt for Python offers
community LGPLv3/GPLv3 and commercial licensing paths, and its wheels can contain Qt dynamic
libraries. A future EXE, installer, or offline bundle must inventory the exact PySide6, shiboken6,
PySide6-Essentials, PySide6-Addons, Qt modules and DLLs actually redistributed, then include the
required license texts, notices, source/relinking information, or a valid commercial license.

Official references: [Qt for Python licensing](https://doc.qt.io/qtforpython-6/) and
[Qt LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations).

For authoritative terms, use the license file included in the exact installed wheel or source
distribution. The license-family record originates from installed package metadata rather than a
logo, screenshot, or secondary catalog; it does not replace checking the new locked artifacts.
