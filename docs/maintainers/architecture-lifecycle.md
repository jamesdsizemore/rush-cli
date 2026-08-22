# Maintainers/Architecture Lifecycle

## Invariant Graph & Failure Ledger (Phase 43)
Maintain project architectural rules in `.rush/memory/invariants.json` using `InvariantGraph`. Record failed patch attempts in `.rush/memory/failures.db` using `FailureLedger`.

## Architectural Layer Matrix Governance (Phase 46)
Define and maintain layer matrices in `rush.toml` under `[architecture.layers]` and enforce via `rush arch-guard` in CI.



## API Versioning & Breaking Change Gates
Enforce zero breaking changes on minor releases via `rush api-diff` in CI.



## Migration Lifecycle Governance
Enforce continuous schema parity using `rush db-drift` on all PRs that touch database models.



## Requirement Traceability Governance
Enforce requirement tag verification (`rush trace`) across all specifications and PRs.

