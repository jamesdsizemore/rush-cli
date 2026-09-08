Current status: historical decision; The accepted interactive outcomes remain required. Current `rush ui` is a one-shot Rich snapshot, the stdlib dashboard is incomplete, and `[dashboard]` is not a supported central configuration table. [Application review F36–F41](../../reports/phase-64-66-application-review.md) records current behavior; [Phase 66](../../phase-plans/phase-66-interactive-tui-and-local-web-plan.md) supplies the persistent-interface implementation contract and selected dependencies.

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
