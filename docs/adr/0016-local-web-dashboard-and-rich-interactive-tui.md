Current status: implemented, with unresolved acceptance findings; current contract: [Phase 66 interactive TUI and local web](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md) and [Phase 69 dashboard/TUI contract remediation](../phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md); evidence: [dashboard/TUI codex implementation review](../reports/69-dashboard-tui-codex-implementation-review.md). `rush ui` launches a persistent Rich terminal UI and `rush dashboard` launches an authenticated, CSRF-hardened local web dashboard; several ownership, admission, and header findings remain open per the linked review. The aliases and `[dashboard]` configuration below are historical design claims, not confirmation that every named alias/config key is currently wired.

# ADR-0016: Local Web Dashboard and Rich Interactive Terminal UI

## Status
Accepted

## Context
When inspecting multi-engine findings across deeply nested repositories, standard terminal scrolling can become visually overwhelming. Developers require both a high-efficiency interactive terminal interface and an optional local web dashboard for deep visual exploration, historical tracking, and architecture inspection.

## Decision
1. Implement an interactive terminal interface (`rush ui` / `rush tui`) using Rich interactive layouts for keyboard-driven finding exploration, severity filtering, and editor jumping.
2. Implement a zero-dependency local web dashboard (`rush dashboard` / `rush serve`) using the Python standard library HTTP server to render interactive visual graphs, finding triage tables, and scan history.
3. Keep the web dashboard entirely local, offline, and user-configurable via `rush.toml` `[dashboard]`.

## Consequences
- Rich visual finding exploration for human engineers.
- Zero extra external runtime dependencies for the web dashboard.
- Maintained offline privacy guarantees.
