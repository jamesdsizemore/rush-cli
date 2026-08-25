# Limitations

- Review currently analyzes Python with deterministic heuristics; `--llm` is a stub and makes no model provider calls.
- Advanced tests, mutation, fuzz, load, and browser tools require explicit permissions (`--allow-*`) or local report paths to execute.
- Parsed configuration fields (`rush.toml`) are consumed selectively per tool; unconsumed fields are ignored gracefully.
- External engine availability, version, configuration, and behavior remain environment-dependent (missing engines return `skipped`).
- Rush is not an OS sandbox or complete penetration testing suite.
- `skipped` exits 0 and requires JSON policy handling when a check is mandatory.
- Platform CI is Linux-focused; Windows/macOS behavior is verified through local tests and project isolation guidance.
- Continuity freshness covers only caller-declared repository-relative dependencies; an unchanged receipt is not a proof that all repository state is current.
- Redaction is pattern-based and receipt-focused; Rush does not retain provider credentials, raw historic instructions, transcripts, or failed patches for handoff.
