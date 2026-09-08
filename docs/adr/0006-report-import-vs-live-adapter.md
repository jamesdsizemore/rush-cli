Current status: historical decision; The report-import/live-execution distinction remains required. Current mutation, fuzz, load, and contract live paths can report success after version probes without executing the workload; [application review F11](../reports/phase-64-66-application-review.md) and [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) govern correction.

# ADR 0006: Report importer versus live adapter

## Context
A parsed report is not evidence that Rush executed its originating engine.

## Decision
Imported evidence and locally executed adapters are separate maturity classes in results, catalog, and documentation.

## Rejected alternatives
Calling importers live adapters or using configuration/routing as execution proof was rejected.

## Consequences
Future importers must state provenance/freshness and never spawn an engine. Tests must cover no execution and malformed report behavior.

## Compatibility and operations
This protects existing guarded tools from misleading promotion and applies to later phases.
