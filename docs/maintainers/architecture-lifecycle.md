# Maintainers/Architecture Lifecycle

## Invariant Graph & Failure Ledger (Phase 43)
Maintain project architectural rules in `.rush/memory/invariants.json` using `InvariantGraph`. Record failed patch attempts in `.rush/memory/failures.db` using `FailureLedger`.

## Architectural Layer Matrix Governance (Phase 46)
Define and maintain layer matrices in `rush.toml` under `[architecture.layers]` and enforce via `rush arch-guard` in CI.

