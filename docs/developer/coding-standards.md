# Coding standards

- Python 3.12, typed public contracts, frozen configuration/catalog records.
- Keep transport, tool intent, routing, adapter, and parser responsibilities separate.
- Prefer structured native reports and deterministic ordering.
- Return canonical errors/skips; never invent findings or silently install.
- Keep edits scope-tight; no drive-by refactors.
- Tests precede behavior changes and mock only the right boundary.
- Ruff and formatter are authoritative for style.
- Redact sensitive material and avoid raw secrets in fixtures.
- User docs use outcome language; internal terms belong in developer docs.
- New capability must include honest maturity and safety boundaries.
