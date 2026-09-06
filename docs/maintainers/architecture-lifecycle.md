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



## Flagship Platform Architecture Lifecycle
All 42 core platform engines across Phases 01–50 are verified with continuous SLSA attestation, Merkle caching, and architectural boundary guards.

## Maintainability & Complexity Lifecycle Governance (Phase 60)

1. **McCabe C901 Invariant Enforcement**:
   - Maintainers must ensure CI enforces McCabe cyclomatic complexity C901 <= 10 across all production modules via `.venv/Scripts/ruff.exe check --select C901 --config "lint.mccabe.max-complexity = 10" src/`.
   - Any PR introducing a function or method with C901 > 10 is blocked from merging.

2. **Exemption Lifecycle Governance**:
   - The maintainability exemptions registry `governance/maintainability-exemptions.toml` must maintain 0 exemptions in release branches.
   - Any temporary development exemption must include `symbol`, `value`, `owner`, `rationale`, `compensating_test`, and `expires_at`.
   - Expired exemptions are treated as test failures by `tests/test_phase60_complexity_thresholds.py`.

3. **Subsystem Modularity Invariant**:
   - Central transports (`cli.py`, `mcp.py`) and runtime bridges (`common.py`) must remain thin facades delegating to `rush.cli_support`, `rush.mcp_support`, and `rush.runtime`.
   - Multi-phase domain tools must remain decomposed into dedicated packages (`rush.continuity`, `rush.review`) and standalone graph/rule modules (`blast_radius_graph.py`, `workspace_graph.py`, `db_drift_rules.py`).
