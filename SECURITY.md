# Security policy

Report suspected command-injection, path-disclosure, credential, unsafe dependency-installation, or
local automation issues through
[GitHub private vulnerability reporting](https://github.com/hang-jin/editaplot/security/advisories/new)
before public disclosure. Do not put credentials, private data, PHI, local paths, or exploit details
in a public issue.

The runtime never accepts arbitrary package names during repair, never uses shell command strings for
pip installation, and never installs or modifies Origin. Render plans are source-hash and plan-hash
bound. Do not publish `.env`, credentials, private paths, patient data, or raw development logs.
