Current status: historical decision; Composite commands and watcher primitives exist, but current suite aggregation loses child-result detail and has permission-retry defects. [Application review F34–F35](../reports/phase-64-66-application-review.md) and [Phase 65](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md) govern the required coherent scan/repair/rescan workflow.

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
