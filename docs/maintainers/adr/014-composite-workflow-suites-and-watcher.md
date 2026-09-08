Current status: historical decision; Composite commands and watcher primitives exist, but current suite aggregation loses child-result detail and has permission-retry defects. [Application review F34–F35](../../reports/phase-64-66-application-review.md) and [Phase 65](../../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md) govern the required coherent scan/repair/rescan workflow.

# ADR-014: Composite Workflow Suites and Real-Time File Watcher

## Status
Accepted

## Context
Running individual tools for every development stage creates CLI invocation friction.

## Decision
1. Provide composite workflow commands: `rush check`, `rush audit`, `rush gate`, `rush doctor`.
2. Provide `rush watch` for automatic background re-execution upon file modifications.

## Consequences
- Streamlined developer CLI ergonomics.
