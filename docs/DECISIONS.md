# Architectural Decisions Index

This document records the foundational Architectural Decision Records (ADRs) that govern Rush CLI and its Model Context Protocol (MCP) server architecture across all 19 phases of development.

---

## 1. Core Architectural Decision Records (ADR 0001–0010)

| ADR | Title | Decision Summary | Affected Area |
|---|---|---|---|
| [ADR 0001](adr/0001-external-engine-boundary.md) | External Engine Boundary | External tools are discovered from the host environment; missing tools return structured `skipped` results without failing or installing binaries. | `src/rush/engines/` |
| [ADR 0002](adr/0002-normalized-finding-and-evidence-model.md) | Canonical ToolResult & Finding Model | All CLI commands and MCP endpoints return a normalized `ToolResult` dictionary with SHA-256 fingerprints, freshness, and redacted values. | `src/rush/tools/base.py` |
| [ADR 0003](adr/0003-tool-catalog-cli-mcp-parity.md) | Tool Catalog & Transport Parity | The catalog in `catalog.py` is the single source of truth; CLI and MCP call the exact same `ToolFn` objects. | `src/rush/catalog.py`, `cli.py`, `mcp.py` |
| [ADR 0004](adr/0004-subprocess-timeout-cancellation-and-redaction.md) | Subprocess Timeout, Cancellation & Redaction | Subprocesses execute with `stdin=DEVNULL`, `shell=False`, 120s timeout, and regex secret redaction (`[REDACTED]`). | `src/rush/tools/common.py` |
| [ADR 0005](adr/0005-optional-engine-version-compatibility.md) | Optional Engine Version Compatibility | Engine version detection is non-fatal; output parsing discrepancies return structured `error` without fabricating results. | `src/rush/engines/` |
| [ADR 0006](adr/0006-report-import-vs-live-adapter.md) | Dual-Mode Report Import vs. Live Execution | Tools support dual modes: importing existing JSON/XML/SARIF reports or executing live binaries under permission flags. | `src/rush/tools/` |
| [ADR 0007](adr/0007-slow-network-and-destructive-permissions.md) | Explicit Execution Permission Boundary | Network, slow, build, browser, and artifact-write operations require explicit permission flags (`--allow-*`) and are denied by default. | `src/rush/permissions.py` |
| [ADR 0008](adr/0008-browser-evidence-final-program.md) | Browser Evidence Runtime Isolation | Headless browser engines (Playwright, axe-core) require `--allow-browser` and strict process boundaries detached from MCP stdio. | `src/rush/engines/playwright.py` |
| [ADR 0009](adr/0009-testing-fixtures-and-optional-ci.md) | Fixture-First Testing & Bounded CI | Real engine execution is proven via deterministic fixture reports in tests rather than bundling all 77 binaries in CI. | `tests/fixtures/engine_reports/` |
| [ADR 0010](adr/0010-review-and-remediation-gates.md) | Review & Remediation Gates | Heuristic review is deterministic; LLM review is a development stub; finding freshness uses in-memory baselines. | `src/rush/tools/quality.py` |

---

## 2. Maintainer Architectural Decision Records (ADR 001–007)

For operational and governance ADRs, see [Maintainer ADRs](maintainers/adr/README.md).
