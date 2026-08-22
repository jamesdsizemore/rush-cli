# ADR-0045: Real-Time Terminal Gain HUD and Telemetry

## Status
Accepted (v0.3.0 / Phase 45)

## Context
Developers and engineering teams lack visibility into whether token reduction and context intelligence systems are actively saving money and improving model performance.

## Decision
1. Implement a persistent **Telemetry Ledger** in `src/rush/token_economy/telemetry.py` recording pre- and post-compression token counts, estimated dollar savings, and latency deltas.
2. Build an interactive Rich full-screen terminal TUI dashboard accessible via `rush context gain`.
3. Support exportable telemetry JSON summaries for CI/CD and engineering management dashboards.

## Consequences
- **Positive**: Provides undeniable, visual proof of token savings and cost efficiency directly in the developer terminal.
- **Negative**: Adds local SQLite telemetry database `.rush/telemetry/tokens.db`.
- **Safety**: Stores purely numerical performance and token metrics; zero source code or private data logged.
