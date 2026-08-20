# Engine development

1. Research a pinned upstream version, output format, exit semantics, license, configuration discovery, downloads, credentials, writes, and child integrations.
2. Add an `EngineSpec`: exact binary, honest install hint, extensions, project markers, and capability.
3. Implement the adapter with deterministic argv. Use structured JSON where available, owned config where containment requires it, no implicit fixes/downloads, bounded timeout/output, and `stdin=DEVNULL` through shared subprocess code.
4. Normalize to ToolResult/Findings. Treat malformed or exit/report inconsistency as `error`; never fabricate clean results.
5. Add native fixture reports: clean, findings, malformed/partial, and special-version cases. Mock only the subprocess boundary for invocation tests.
6. Prove missing executable returns `skipped` and messages are redacted.
7. Wire the engine in `ENGINES`, the owning ToolSpec, routing, parser-fixture registry, engine directory, and compatibility docs.
8. Run installed-engine tests only in a bounded representative environment.

Install hints must be actionable without claiming Rush installs anything. Standalone binaries should point users to verified upstream platform packages rather than invented commands.
