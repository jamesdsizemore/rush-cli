# Rush continuity development plan

Status: implementation plan. This document contains no exploratory comparisons, model selection, or external-product selection. Its inputs are the fixed D1–D6 technical decision record.

## 1. Start condition

Do not begin implementation until the technical decision record has completed D1–D6. Copy the chosen values and artifact IDs into this section before the first code change.

| Required input | Fixed decision / artifact ID |
|---|---|
| D1 schema and authority | Pending technical decision record |
| D2 model/rendering policy | Pending technical decision record |
| D3 retrieval stack | Pending technical decision record |
| D4 token projection contract | Pending technical decision record |
| D5 bundle/protocol scope | Pending technical decision record |
| D6 privacy/storage policy | Pending technical decision record |

## 2. Implementation invariants

- Python 3.12; local CLI and stdio-only MCP; no web server, daemon, hook, hosted dependency, or provider credential in the default path.
- CLI and MCP invoke the same implementation in `src/rush/tools/`; every public operation returns canonical `ToolResult` and uses structured `skipped` for unavailable optional capability.
- `SecretRedactor`, `WorkspaceBoundaryGuard`, and permissions run before persistence/export/import.
- SQLite event data is canonical. Summaries, embeddings, external retrieval, and provider responses are derived, labelled, and removable.
- Existing session/checkpoint/preference state enters only through an explicit low-authority migration path; it is never silently upgraded to canonical evidence.

## 3. Implementation phases

### D0 — package boundary and configuration

Add one shared `src/rush/tools/continuity.py` operation layer; register thin CLI and MCP bindings. Add the D6-approved strict local configuration surface in `src/rush/config.py`, catalog, documentation, and example together.

Deliverables: capability errors as `skipped`; no new transport-specific logic; config rejects unknown/unsafe settings.

### D1 — canonical store and capture

Create `src/rush/continuity/models.py`, `database.py`, `event_store.py`, and migrations using the D1 schema. Persist redacted immutable events, source spans/gaps, idempotency keys, consent, and hashes. Implement inspection and deletion/tombstones specified by D6.

Deliverables: transactional SQLite store, deterministic event IDs, migration path, inspect/delete commands, and repository/workspace boundary enforcement.

### D2 — reducer and current frontier

Create `reducer.py`, `authority.py`, and `repository_frontier.py`. Apply the fixed D1 precedence order to derive current goal, constraints, completed work, open work, and repository state. Integrate current governance symbols, not the obsolete paths in the prior plan.

Deliverables: deterministic reducer, historical-instruction quarantine, current frontier renderer, and explicit contradiction representation.

### D3 — claims, receipts, invalidation, and obligations

Create `claims.py`, `receipts.py`, `dependencies.py`, `freshness.py`, `obligations.py`, `failures.py`, `retry_policy.py`, and `completion.py`. Bridge existing `ToolResult`/`Finding`, Merkle invalidation, failure ledger, and flight-recorder data through explicit adapters.

Deliverables: evidence-backed claims, dependency invalidation, obligation closure requiring fresh admissible receipts, and persistent failure/recovery state.

### D4 — token-budgeted projection

Create `projection.py`, `selection.py`, `renderers.py`, `recovery.py`, and `token_metrics.py` according to D2–D4. Reuse `ContentRouter`, `CCRStore`, `CacheAligner`, `StaleSweeper`, `TelemetryStore`, and `ContextPacker` as inputs or telemetry where their fixed interfaces fit; do not create a competing store.

Deliverables: mandatory-first projection, exact target-budget rendering, omission manifest, stable recovery handles, acknowledgement delta, and required telemetry fields.

### D5 — portable bundle and lifecycle boundary

Create `bundle.py`, `schema.py`, `divergence.py`, and versioned schemas under `src/rush/continuity/schemas/`. Implement only D5-approved JSONL/Markdown/protocol forms. Preserve checksums, schema versions, authority labels, consent, redaction, tombstones, and import receipts.

Deliverables: export/import commands, fail-closed version handling, cross-worktree divergence object, and complete retention/export/delete policy behavior.

### D6 — approved optional adapters

Create `continuity/adapters/base.py`, `capabilities.py`, and only the D3/D5/D7-approved adapters. MCP remains stdio. Every adapter is read-only unless the fixed decision record explicitly authorizes a different operation; adapter removal cannot damage canonical data.

Deliverables: capability probe, generic fallback bundle, permissions, local-only behavior, and `skipped` results for unavailable optional components.

### D7 — documentation, migration, and release readiness

Write operator/security/schema/configuration documentation and a versioned example bundle. Add an opt-in migration assistant for existing session/checkpoint/preference artifacts using the D1 authority labels. Do not create hooks, tags, releases, or publish packages.

Deliverables: docs/test parity, migration receipts, no secrets in logs/output, and stated recovery procedures.

## 4. Fixed verification suite

These are implementation acceptance tests against D1–D6, not exploration:

- CLI/MCP parity and stdio cleanliness.
- Deterministic replay and idempotent write behavior.
- Authority precedence, historical-instruction quarantine, and contradiction display.
- Dependency invalidation and stale-completion denial.
- D4 target-budget projection and omission/recovery contract.
- D5 bundle checksum/version/import/tombstone behavior.
- Secret redaction, permission, workspace, and deletion behavior.
- SQLite interruption/lock recovery and optional-adapter `skipped` behavior.

## 5. Explicit exclusions

- No technical comparison of LLMs, providers, vector stores, graph stores, or external memory products.
- No research spike, benchmark selection, or “monitor” backlog item.
- No F9 multi-agent learning/coordination until a separately authorized implementation plan exists.
- No external project is introduced unless the completed technical decision record names it and the adapter phase above includes it.

## 6. Completion condition

The implementation is complete when D0–D7 deliverables and the fixed verification suite pass under the approved D1–D6 decision record. A changed technical decision requires revising that decision record before modifying this plan.
