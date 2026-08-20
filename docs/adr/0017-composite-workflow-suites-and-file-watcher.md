# ADR-0017: Composite Workflow Suites and Real-Time File Watcher

## Status
Accepted

## Context
Developers and CI pipelines frequently need to run groups of related tools rather than issuing 10+ distinct CLI commands. Furthermore, active refactoring requires instant, real-time feedback when files change.

## Decision
1. Implement composite workflow suites: `rush check` (pre-commit quality loop), `rush audit` (security & supply chain), `rush gate` (PR & CI release gate), and `rush doctor` (environment health & engine setup).
2. Implement `rush watch` providing debounced file change monitoring and fast targeted re-execution of relevant lint, typecheck, and test tools.

## Consequences
- Single memorable commands for standard developer workflows.
- Continuous real-time feedback loops during active coding.
