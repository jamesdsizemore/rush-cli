# Phase 06 — review intelligence, evidence lifecycle, and scanner governance

> **Depends on:** Phases 00–05. **Excludes:** browser/runtime implementation.

**Objective:** Make completed non-browser scanners coherent without hiding focused results: capability detection, deterministic scan planning, review coordination, finding identity/dedupe/freshness, governance and repair evidence.

## Mandatory tool-efficient execution

Start/end with RTK Git. **Graft** discovers `review.py`, `common.py`, routing, tool registry, result models, config/CLI/MCP, and aggregation tests/callers. **context-mode** indexes these with the master ADRs and queries plan/order/fingerprint/freshness/error semantics. **RTK** supplies exact reads, diff, fixtures and project-vnv gates. Every slice uses RED→GREEN→docs→two independent reviews→targeted repair→re-review.

## Owned contracts and tasks

1. **Capabilities:** RED tests for read-only project-marker/config/report/PATH-version/permission detection. Implement `rush capabilities PATH --json` with installed/configured/applicable/blocked/missing distinctions and no engine execution.
2. **Planner:** RED tests for `rush plan PATH --profile` deterministic selection/order, dependency prerequisites, rejected/blocked reasons, and no hidden opt-in. Implement profile expansion only for completed phases; browser candidates remain absent/blocked until Phase 08.
3. **Coordinator:** preserve focused tool implementations; RED aggregation tests for per-tool result retention, deterministic concurrent/serial policy, timeout/cancellation, partial result labelling, summaries and no clean-overwrite of skipped/error.
4. **Finding lifecycle:** implement ADR-0002 fingerprints, dedupe with provenance retained, baseline/freshness state, diff-aware scope only on explicit input, severity normalization and repair packet links. Baseline creation/update is explicit contained action, never default.
5. **Governance:** maturity/capability docs, engine compatibility version warnings, deprecation policy, scanner selection audit record, error budget and evidence retention/redaction policy.
6. **Docs/parity/review:** update review CLI/MCP/config/user examples, architecture/ADR, catalog and troubleshooting; dual review must inspect ordering/dedupe data loss, concurrency/subprocess safety and misleading claims.

## Tests and acceptance

Add fixture repositories covering mixed languages, missing engines, duplicate cross-engine findings, stale reports, blocked slow/network flags, cancellation, planner order and CLI/MCP parity. CI remains fixture-first. **Exit:** review is evidence-backed orchestration of real non-browser tools, not a second implementation path; Program 8 remains unavailable. **Non-goals:** any URL launch, browser process, DOM/visual/a11y/performance/DAST integration. Rollback isolates coordinator/governance commits without removing focused scanner results.

## Implementation reconciliation — 2026-08-19

1. **Capabilities:** completed read-only local marker/config/report/PATH
   inventory. Tests cover report applicability, configuration, PATH discovery,
   blocked browser/feasibility states, missing prerequisites, and malformed
   configuration without engine execution or version probing.
2. **Planner:** completed deterministic completed-phase profiles with stable
   selected state, reason, and catalog-derived report/engine prerequisite text.
   Browser-runtime work remains absent from `nonbrowser`.
3. **Coordinator:** completed serial review aggregation evidence: stable child
   status summaries, partial labels for skipped/error children, worst-status
   preservation, provenance, metrics/artifacts, deterministic fingerprints, and
   no clean overwrite. Existing subprocess timeout/cancellation mapping remains
   the canonical structured-error boundary.
4. **Finding lifecycle:** completed shared fingerprints, provenance-preserving
   dedupe, explicit in-memory baseline freshness, direct source-location repair
   evidence, and opt-in target-contained changed-file scope. Rush never infers
   a Git diff or persists/updates a baseline.
5. **Governance:** completed compatibility/CLI/MCP/user/developer/ADR/catalog
   documentation plus the scanner selection, deprecation, evidence-retention,
   redaction, and zero-untriaged-error-budget policy in
   `docs/maintainers/scanner-governance.md`.