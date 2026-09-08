# Limitations

- Review currently analyzes Python with deterministic heuristics; `--llm` can send findings to a configured provider.
- Mutation, fuzz, load and contract live modes currently probe versions without running workloads (F11). Imported-report modes remain separate; real execution is planned in P64-08–P64-11.
- Parsed configuration fields (`rush.toml`) are consumed selectively per tool; unconsumed fields are ignored gracefully.
- External engine availability, version, configuration, and behavior remain environment-dependent (missing engines return `skipped`).
- Rush is not an OS sandbox or complete penetration testing suite.
- `skipped` exits 0 and requires JSON policy handling when a check is mandatory.
- Clean-platform installation and complete CI acceptance remain unverified; repairs are planned in P64-20/P65-01. See [Known issues](KNOWN_ISSUES.md).
- Continuity freshness covers only caller-declared repository-relative dependencies; an unchanged receipt is not a proof that all repository state is current.
- Redaction is pattern-based and receipt-focused; Rush does not retain provider credentials, raw historic instructions, transcripts, or failed patches for handoff.
