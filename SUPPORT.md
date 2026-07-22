# Support scope

EditaPlot V1 supports physical Windows 10/11 x64 computers only. Its CLI and locked dependency
layer are covered on 64-bit CPython 3.10, 3.11, and 3.12; the live Origin end-to-end baseline is
CPython 3.10 with Origin/OriginPro 2024b (10.15). Python 3.11/3.12 rendering still requires the
same local full-artifact verification before a route is claimed. macOS (Intel or Apple Silicon),
Linux, WSL, Wine/CrossOver, Parallels, and other virtual machines are outside the supported product
boundary. Other Origin versions, custom templates, new LabTalk
parameters, and new 3D routes require separate verification.

The launcher reuses an existing compatible Python and keeps packages in EditaPlot's project-local
environment. If no compatible Python exists, an agent may offer an official CPython 3.12 user-scope
installation only after the user explicitly approves that system change. This exception never
extends to Origin: environment repair does not install or modify Origin. The render worker connects
to the existing local Automation application only when a render is requested.

Support does not include installing, replacing, or modifying the Origin application. The user
remains responsible for scientific meaning, statistics, units, privacy, and final publication review.

Community issues and contributions are welcome under the repository's open-source terms. Optional
paid consulting, customization, installation guidance, and support may be offered separately; they
do not restrict Apache-2.0 rights and do not include hosted, remote, or service-bureau automation.
