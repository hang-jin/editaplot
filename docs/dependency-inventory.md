# Verified Python dependency inventory

This is the dependency snapshot used for the 2026-07-21 EditaPlot open-source release
verification on Windows with Python 3.10. It records installed package metadata; it is not a claim
that third-party projects endorse EditaPlot.

The current repository does not vendor these packages. `doctor --repair` installs exact direct
versions into a project-local virtual environment and constrains transitive resolution with
`requirements-runtime.lock`. A future update, offline bundle, or executable must regenerate this
inventory from the exact artifacts being installed or redistributed.

| Package | Verified version | Relationship | Declared license family | Project |
|---|---:|---|---|---|
| NumPy | 1.26.4 | direct | BSD-3-Clause | [numpy.org](https://numpy.org/) |
| pandas | 2.3.3 | direct | BSD-3-Clause | [pandas.pydata.org](https://pandas.pydata.org/) |
| PyYAML | 6.0.3 | direct | MIT | [pyyaml.org](https://pyyaml.org/) |
| jsonschema | 4.26.0 | direct | MIT | [source](https://github.com/python-jsonschema/jsonschema) |
| Matplotlib | 3.10.9 | direct | Matplotlib license (PSF-based) | [matplotlib.org](https://matplotlib.org/) |
| originpro | 1.1.15 | direct | BSD | [OriginLab](https://www.originlab.com/) |
| openpyxl | 3.1.5 | direct | MIT | [documentation](https://openpyxl.readthedocs.io/) |
| xlrd | 2.0.2 | direct | BSD | [python-excel](https://www.python-excel.org/) |
| Pillow | 12.3.0 | direct | MIT-CMU | [documentation](https://pillow.readthedocs.io/) |
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
distribution. Package metadata was read from the verified environment rather than inferred from a
logo, screenshot, or secondary catalog.
