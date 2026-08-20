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
