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
