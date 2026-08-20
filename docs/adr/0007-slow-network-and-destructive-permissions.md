# ADR 0007: Slow, network, and destructive permissions

## Context
Some scans can mutate baselines, consume resources, or reach external systems.

## Decision
Local-safe defaults are mandatory. Slow, network-sensitive, destructive, baseline-mutating, or expensive operations require named explicit opt-in and path containment.

## Rejected alternatives
Implicit network access, default baseline updates, and broad project mutation were rejected.

## Consequences
Guarded quality tools remain skipped until a future adapter proves its explicit permission contract.

## Compatibility and operations
This protects source projects and is enforced by focused configuration/tool tests in the owning phase.
