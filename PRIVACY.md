# Privacy

- EditaPlot's bundled Python runtime and Origin automation process the selected scientific files on
  the Windows computer and do not initiate a network upload of those files.
- A file that the user explicitly attaches or makes available to Codex is handled under the data,
  retention, and organization policies of that Codex account or host. EditaPlot cannot replace or
  override those policies.
- The repository's Star trend stores only a UTC date and the aggregate Star total returned by the
  repository metadata endpoint. It does not request or retain usernames, account IDs, lists, or
  personal Star timestamps, and it is unrelated to user scientific data.
- Source files are opened read-only and protected by SHA-256 checks across planning and rendering.
- Each formal delivery folder contains a provenance copy of the selected source. Protect that folder
  with the same access controls as the original data.
- Public release assets must exclude local absolute paths, logs, unreviewed TIF metadata, tokens,
  credentials, PHI, and undeidentified medical images.
- When Origin activation and cleanup both fail, the structured diagnostic channel retains only the
  four allow-listed primary/cleanup code-and-stage fields. It does not retain a Windows account
  name, local path, raw HRESULT, or raw COM exception text. The public execution-context report also
  exposes only a product-defined status such as `interactive_user`, `codex_sandbox`, or `unknown`,
  never the detected account name.
- Before sharing medical data or reference images with Codex, users must follow their institution's
  rules, deidentify the material, and check burned-in text. Medical panel planning relies on that
  explicit attestation and does not perform automatic PHI detection.
