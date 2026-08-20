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
