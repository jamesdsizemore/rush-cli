Current status: implemented, with unresolved acceptance findings. The accepted interactive outcomes remain required. `rush ui` launches a persistent Rich terminal UI and `rush dashboard` launches an authenticated, CSRF-hardened local web dashboard; `[dashboard]` is not a supported central configuration table. [Dashboard/TUI codex implementation review](../../reports/69-dashboard-tui-codex-implementation-review.md) records current behavior and unresolved findings; [Phase 66](../../phase-plans/phase-66-interactive-tui-and-local-web-plan.md) and [Phase 69](../../phase-plans/phase-69-dashboard-tui-contract-remediation-plan.md) supply the implementation contract and selected dependencies.

# ADR-013: Local Web Dashboard and Rich Interactive Terminal UI

## Status
Accepted

## Context
Developers navigating complex multi-engine finding reports benefit from interactive visual exploration and hierarchical filtering.

## Decision
1. Provide `rush ui` interactive terminal interface built on Rich layouts.
2. Provide `rush dashboard` lightweight local web interface running on stdlib HTTP server.
3. Configure dashboard settings through `rush.toml` `[dashboard]`.

## Consequences
- Enhanced developer triage efficiency without adding heavy framework dependencies.
