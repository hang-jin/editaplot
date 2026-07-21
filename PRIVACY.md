# Privacy

- User-selected scientific data is processed locally by default.
- The Skill does not upload private tables or medical images to a network.
- Source files are opened read-only and protected by SHA-256 checks across planning and rendering.
- Public release assets must exclude local absolute paths, logs, unreviewed TIF metadata, tokens,
  credentials, PHI, and undeidentified medical images.
- Medical panel planning relies on explicit user deidentification and burned-in-text attestations;
  it does not perform automatic PHI detection.
