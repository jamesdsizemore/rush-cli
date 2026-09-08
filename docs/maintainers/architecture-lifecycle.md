# Maintainers/Architecture Lifecycle

## Invariant Graph & Failure Ledger (Phase 43, migrated Phase 61)
Maintain project architectural rules via `InvariantGraph` and record failed patch attempts via `FailureLedger`. Both were migrated onto the Phase 61 `TypedArtifactStore` (`.rush/memory.db`), the canonical durable store other tools (including cross-LLM/MCP memory queries) read from:
- `InvariantGraph` (`.rush/memory/invariants.json`) is a thin compatibility view: `get_all()` merges any live entries in `invariants.json` with rows already migrated into the store. After a one-shot migration run the file is renamed `invariants.json.migrated` and the store's copy becomes the sole source for pre-migration rules; new invariants added afterward still land in a fresh `invariants.json` until migrated again.
- `FailureLedger` (`.rush/memory/failures.db`) keeps writing and reading `failures.db` directly and unchanged for its own duplicate-error-loop checks; `.rush/memory/failures.db` is never renamed. `migration.py`'s `migrate_failure_ledger()` additionally copies its rows into the store, so the store — not `failures.db` — is the canonical source other tools query for failure history.

## Architectural Layer Matrix Governance (Phase 46)
Keep architectural rules in the supported architecture engine inputs. The current `RushConfig` parser does not load `[architecture.layers]`; adding that table does not configure enforcement. Run `rush arch-guard` and inspect its findings alongside architecture tests. The [Phase 64 plan](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) retains the required engine corrections.



## API Versioning & Breaking Change Gates
Run `rush api-diff --base main` in CI and review reported changes against the public compatibility contract; a successful heuristic check alone does not prove zero breaking changes.



## Migration Lifecycle Governance
Run `rush db-drift` on PRs touching database models and verify migrations with database tests. Current table-identity and missing-migration gaps remain assigned to Phase 64 P64-15.



## Requirement Traceability Governance
Run requirement tag checks (`rush trace`) across specifications and reconcile each requirement with executable acceptance evidence. Tags alone do not establish implementation.



## Flagship Platform Architecture Lifecycle
Historical phase plans describe intended platform coverage. Current verification must exercise live engine registrations and their prerequisites; unsigned provenance does not certify a SLSA level. The [application review](../reports/phase-64-66-application-review.md) records unresolved engine and integration gaps.

## Maintainability & Complexity Lifecycle Governance (Phase 60)

1. **McCabe C901 Invariant Enforcement**:
   - Maintainers must ensure CI enforces McCabe cyclomatic complexity C901 <= 10 across all production modules via `uv run --python 3.12 --extra dev ruff check --select C901 --config "lint.mccabe.max-complexity = 10" src/`.
   - Any PR introducing a function or method with C901 > 10 is blocked from merging.

2. **Exemption Lifecycle Governance**:
   - The maintainability exemptions registry `governance/maintainability-exemptions.toml` must maintain 0 exemptions in release branches.
   - Any temporary development exemption must include `symbol`, `value`, `owner`, `rationale`, `compensating_test`, and `expires_at`.
   - Expired exemptions are treated as test failures by `tests/test_phase60_complexity_thresholds.py`.

3. **Subsystem Modularity Invariant**:
   - Central transports (`cli.py`, `mcp.py`) and runtime bridges (`common.py`) must remain thin facades delegating to `rush.cli_support`, `rush.mcp_support`, and `rush.runtime`.
   - Multi-phase domain tools must remain decomposed into dedicated packages (`rush.continuity`, `rush.review`) and standalone graph/rule modules (`blast_radius_graph.py`, `workspace_graph.py`, `db_drift_rules.py`).
