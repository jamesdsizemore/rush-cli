# Architecture decision records

ADRs explain durable choices and their consequences.

- [ADR-001: stdio-only MCP](001-stdio-only-mcp.md)
- [ADR-002: external engine discovery](002-external-engine-discovery.md)
- [ADR-003: catalog-driven metadata](003-catalog-driven-metadata.md)
- [ADR-004: explicit safety gates](004-explicit-safety-gates.md)
- [ADR-005: fixture-first adapter tests](005-fixture-first-adapter-tests.md)
- [ADR-006: bounded CI](006-bounded-ci.md)
- [ADR-007: Git-root-bounded configuration](007-git-root-bounded-configuration.md)
- [ADR-008: HTML and SARIF artifact export](008-html-and-sarif-artifact-export.md)
- [ADR-009: pluggable LLM providers](009-pluggable-llm-providers.md)
- [ADR-010: TDD guard and continuous sensors](010-tdd-guard-and-continuous-sensors.md)
- [ADR-011: incremental content-hash cache](011-incremental-content-hash-cache.md)
- [ADR-012: extensible plugin architecture](012-extensible-plugin-architecture.md)
- [ADR-013: local web dashboard and TUI](013-local-web-dashboard-and-tui.md)
- [ADR-014: composite workflow suites and watcher](014-composite-workflow-suites-and-watcher.md)
- [ADR-015: agent remediation and memory](015-agent-remediation-and-memory.md)

The implementation program also maintains detailed phase and evidence ADRs in
the [program ADR index](../../adr/README.md). Those records complement rather
than replace these product-level decisions.

Format: context, decision, consequences, status. Amend with a superseding ADR rather than rewriting history once committed.
