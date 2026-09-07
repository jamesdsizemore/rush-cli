# Phase 62 Implementation Plan: Memory Integration Layer (Cache Front-End, Review/Dev Hooks, Attribution, Expiry, Decision Schema)

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 62 — the memory-system integration layer built on top of Phase 61's `TypedArtifactStore`.
- **Planning Status:** Implementation-ready for 8 of 8 items scoped below (P62.1-P62.8). P62.7 (per-type expiry) previously had an open sub-decision — `DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` TTL durations had no cited source anywhere — now resolved via a documented rush-own rationale (§6.3: 14/30/90 days respectively, grounded in `src/rush/hotspots/time_decay.py:12`'s existing 90-day half-life precedent for non-authoritative data relevance decay). Not implementation-ready for anything beyond these 8 — this document covers exactly the 8 candidates from `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` §3.2.3 ("builds directly on this phase's primitives"), not the other 16 unranked candidates in that plan's §3.2.4, which are still just names with no task-card plan and are explicitly **not** in this document.
- **Implementation Status:** Not started. Authorized for strict TDD execution once accepted. Hard-blocked on Phase 61 being complete (every task card below reads or writes through `TypedArtifactStore`, `MemoryArtifact`, or `MemoryTool` — none of which exist until Phase 61 ships).
- **Authority:** `docs/reports/cross-llm-memory-system-synthesis-2026-09-06.md` (source of all 8 ideas, "Enhancement ideas beyond the core 7-subject design" section) and `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` (the foundation this phase integrates with — every file:line citation below that references `TypedArtifactStore`/`MemoryArtifact`/`trust.py`/`MemoryTool` is to Phase 61's own §6 design, not independently re-verified against running code, since Phase 61 hasn't been implemented yet as of this writing).
- **Predecessors:** Phase 61 (`TypedArtifactStore`, `MemoryArtifact`, trust tiers, `MemoryTool`) — hard prerequisite for all 8 workstreams.
- **Successor:** none scoped yet. The 16 items in Phase 61's §3.2.4 remain unranked backlog beyond this phase.
- **Security Boundary:** Every new read of memory content goes through `TypedArtifactStore.recall()`, inheriting Phase 61's Trojan Source scan and staleness/signature checks (§6.3 of the Phase 61 plan) — this phase adds no new read path that bypasses those checks.
- **Protected Boundaries:** `governance/remediation-contracts.toml` (unchanged — this phase closes no `R-xxx` finding), Phase 61's own schema (`memory_artifacts` table) is extended via new nullable columns only, never a breaking migration of existing Phase 61 rows.
- **Zero-Downscope Invariant:** Same as Phase 61 — a task card's Binary Outcome must be met exactly.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, or release without explicit user instruction.

---

## 2. Authority and Concrete Evidence

### 2.1 Verified Current API Surfaces (re-read this session, cited exactly)

- `src/rush/token_economy/ccr_store.py`, `cache_aligner.py`, `stale_sweeper.py` — real, cited in the synthesis doc's original enhancement-idea bullet 3 ("Memory as a token-savings layer"). `CacheAligner.align_prompt()` confirmed this session (`src/rush/token_economy/cache_aligner.py:8-58`).
- `src/rush/tools/api_diff.py` — `ApiDiffer.diff_file(self, file_path: Path, base_ref: str = "main") -> list[dict[str, Any]]` (line 36) and `ApiDiffer.diff_public_api(base_ref="main")`, returns `{"base_ref", "passed", "breaking_changes_count", "breaking_changes"}`.
- `src/rush/tools/provenance_ai.py` — `GitTrailerParser.parse_commit_records(raw_log)` (lines 32-82, confirmed this session), classifies `is_ai_generated`/`is_ai_assisted`/`is_fix`; `ProvenanceAiTool` (lines 155-350) computes code-survival correlation.
- `src/rush/mcp_mesh/lock_manager.py` — `MeshLockManager`, confirmed this session (Phase 61 plan §2.1 Drift 5).
- `src/rush/continuity/receipts.py`, `providers.py` — files confirmed to exist this session; their **current** (pre-Phase-61) behavior is `receipts.py` reading/writing `.rush/session_memory.json` with `historical_evidence`/`quarantined` fields. The `TypedArtifactStore`/`family="handoff"` shape is Phase 61's own target design (its plan §6.1/P61.4), not yet built or independently confirmed — this phase's P62.4 work depends on Phase 61 actually landing that shape first (§4 admission gate).
- `governance/remediation-contracts.toml` — confirmed uniform schema this session: `id, title, owner_phase, severity, release_blocker, red_task, green_task, target_seam, test_file, test_function, predecessor, docs_owner, status`.
- `rush.review` package exists (confirmed via this repo's own git history: commit `febc09a feat(phase60): extract review pipeline into rush.review`) — the review pipeline's exact entry-point function is **not** independently re-verified this session; P62.2's RED task must grep it directly before writing tests against it (do not assume a function name).
- **Not independently verified this session, assumed from the Phase 61 plan only (flagged, not silently trusted as if re-checked):** `TypedArtifactStore`, `MemoryArtifact`, `trust.py`'s `evaluate_promotion`/`evaluate_conflict`, `MemoryTool` — none of these exist yet. Every task below that imports from `rush.memory.store`/`rush.memory.trust`/`rush.tools.memory` is trusting Phase 61's plan document, not running code. Each task's RED step must re-confirm the actual signature against Phase 61's real implementation (which may drift slightly from its own plan during implementation) before writing assertions against it.

### 2.2 Codebase Integration Points Requiring Confirmation Before RED (not guessed here)

1. The AST-pack insertion point is confirmed (§6.1): `pack_context()` in `src/rush/continuity/context.py:68-158`, the sole caller of `ContextPacker.pack()` (`context.py:97`) — no separate grep needed at P62.1.1.
2. `rush.review`'s exact finding-reporting entry point (P62.2's insertion point) — grep at P62.2.1.
3. `session_memory.py`'s post-Phase-61 write signature for episodic records (P62.5's linkage point) — re-confirm at P62.5.1, since Phase 61's P61.5.2 modifies this file.

---

## 3. Goals, Non-Goals

### 3.1 Primary Goals (the 8 items from Phase 61 §3.2.3, one workstream each)

1. **P62.1 — Token-savings cache front-end.** A durable-memory check ("do we already have an answer for this") runs before an expensive AST-pack, querying `TypedArtifactStore` first.
2. **P62.2 — Review/development reading memory.** A review finding checks failure/mistake memory before reporting ("this pattern already caused a fix in commit X"). Architectural-decision memory is reused by the same `rush.review` recall call — no separate planning surface exists anywhere in this codebase (verified: `src/rush/tools/*.py`, 45 `ToolFn` subclasses, none is a planning tool) — so this phase does not promise a planning-step insertion point; adding one is out of this phase's scope.
3. **P62.3 — Maintenance sub-agent.** Uses `MeshLockManager` to own the write-promotion rule's periodic re-evaluation, the skill-candidate admission gate, and staleness sweeps as bounded, reversible background work.
4. **P62.4 — Handoff diffs, not blobs.** Cross-provider handoff sends a diff against the *last* handoff to that same tool instead of a full snapshot.
5. **P62.5 — AI-attribution trail.** Links a git commit/diff hunk back to the specific decision-memory and failure-memory records that informed it, using `GitTrailerParser`'s existing `is_fix`/`is_ai_generated` classification.
6. **P62.6 — API-diff staleness.** A memory record citing a specific public API signature is flagged stale by `ApiDiffer.diff_symbol()` (new, per-symbol; §6.5 Invariant 5) when that exact signature breaks — narrower than Phase 61's merkle content-hash staleness (Invariant 6), which doesn't distinguish public-API breaks from internal edits, and narrower than `diff_public_api()`'s repo-wide scan, which this phase does not call from `recall()`.
7. **P62.7 — Per-type expiry/TTL policy.** `STATED` defaults to never-expire; `DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` get a real, per-subject TTL, auditable (`expired_at`/`expired_by` stamped on an explicit sweep, never silently recomputed on read).
8. **P62.8 — Remediation-contract-schema reuse.** `failure`/mistake `MemoryArtifact.content` gains the same shape as `remediation-contracts.toml`'s findings: `red_task`/`green_task`/`target_seam`/`test_file`/`test_function`/`predecessor`/`status`, wired into the one real candidate-shaping site (`mistake_miner.py`'s pure shaping function, per §6.4 — not a write call site; persistence happens through whatever caller invokes `MemoryTool.write()`). `DecisionRecordFields` is defined for `architectural_decision` too, but this phase writes it into no `architectural_decision` record, new or migrated — Phase 61's migrated `InvariantGraph` rows (`description`/`rationale`/`status` only, `src/rush/memory/invariant_graph.py:36-41`) are not normalized to this shape by this phase; see §3.2 Non-Goal 4.

### 3.2 Non-Goals

1. The 16 unranked items in Phase 61's §3.2.4 are not in this plan.
2. No new third-party dependencies (same discipline as every predecessor phase).
3. No change to Phase 61's `memory_artifacts` table shape beyond additive nullable columns (P62.7 adds `expires_at`, `expired_at`, `expired_by`; P62.6 adds no new column, reuses `stale`/`content_hash`; P62.8 stores its schema inside the existing `content` JSON blob, no new column).
4. Backfilling `DecisionRecordFields` onto the `architectural_decision` rows Phase 61's P61.3.2 already migrated from `invariant_graph.py` (`description`/`rationale`/`status` only) is not in this phase — normalizing already-migrated data is a separate, explicitly-scoped migration task a future phase can add against this same schema, not invented here.

---

## 4. Admission Gate

1. Phase 61's exit checklist is 100% checked (`docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` §11) — `TypedArtifactStore`, trust tiers, `MemoryTool` all exist and pass their own 39 contract tests.
2. Run `python -m pytest tests/ -q`, record baseline (Phase 61's final count) in `docs/phase-plans/phase-62-implementation-evidence.md`.
3. Confirm the 3 integration points in §2.2 via grep before any RED task authors an assertion against them.

---

## 5. Workstream-Ownership Ledger

| Workstream | Depends On (Phase 61) | New/Modified Files |
|---|---|---|
| P62.1 Cache front-end | `TypedArtifactStore.search()` (P61.7.2, existence check) + `recall()` (P61.1.2, defended fetch) | `src/rush/token_economy/memory_cache_gate.py` (new), `src/rush/continuity/context.py` (`pack_context()`, confirmed §6.1) |
| P62.2 Review/dev reads memory | `TypedArtifactStore.recall()` (P61.1.2) | `rush.review`'s entry point (confirmed at P62.2.1) |
| P62.3 Maintenance sub-agent | `TypedArtifactStore`, `trust.evaluate_promotion`, `MeshLockManager` | `src/rush/memory/maintenance.py` (new) |
| P62.4 Handoff diffs | `continuity/receipts.py` (post-Phase-61 shape) | `src/rush/continuity/receipts.py`, `providers.py` |
| P62.5 Attribution trail | `session_memory.py` (post-Phase-61 shape), `GitTrailerParser` | `src/rush/tools/provenance_ai.py`, `src/rush/session_memory.py` |
| P62.6 API-diff staleness | `TypedArtifactStore` staleness fields | `src/rush/memory/store.py` (additive), `src/rush/tools/api_diff.py` |
| P62.7 Per-type expiry | `TypedArtifactStore` schema | `src/rush/memory/store.py`, `src/rush/memory/expiry.py` (new) |
| P62.8 Decision-record schema | `MemoryArtifact.content` shape | `src/rush/memory/decision_schema.py` (new) |

---

## 6. Shared Architecture and Data Structures

### 6.1 Cache Gate (`src/rush/token_economy/memory_cache_gate.py`)

The only real call site for an AST-pack today is `pack_context()` in `src/rush/continuity/context.py:68-158`, the sole caller of `ContextPacker.pack()` (verified: `grep -rn '\.pack(' src/rush` returns exactly one hit, `context.py:97`). `ContextPacker.pack(self, target_file: Path, target_symbol: str = "", max_tokens: int = 4000) -> dict[str, Any]` (`src/rush/codegraph/context_packer.py:29-32`) takes a file path and a symbol name, never a free-text query — `pack_context()` resolves its own `context_path: str` argument to an absolute `Path` and calls `ContextPacker(project_root).pack(target, target_symbol=target_symbol, max_tokens=1_000_000)` at `context.py:97-99`. The cache gate wraps exactly that call.

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class CacheGateResult:
    hit: bool
    artifact_id: str | None
    content: dict[str, Any] | None
```

`check_memory_before_pack(context_path: str, target_symbol: str, subject: str = "domain_knowledge") -> CacheGateResult` — the cache key is `f"{context_path}:{target_symbol}"`, built from the exact two arguments `pack_context()` already holds (no free-text query, no separate normalization step); passed as `query` to `TypedArtifactStore.search(subject=subject, query=cache_key)` to locate a candidate match only — `search()`'s FTS5 hit is never handed to the caller as `content` (Phase 61 §6.3 Invariant 8 binds `recall()`, not `search()`). On a `search()` match, the gate re-resolves the identical `(subject, cache_key)` pair through `TypedArtifactStore.recall(subject=subject, query=cache_key)`, which applies signature re-verification, Trojan-source scanning, and staleness checking to the matched row before returning it. `check_memory_before_pack()` catches any `recall()` raise (signature mismatch, Trojan-source detection) internally and a `stale=True` result is also treated as `hit=False` — never re-raised to `pack_context()`'s caller, since a defensive cache-lookup failure must fall through to a real pack, not break the caller. On a hit, `content` is shaped identically to `ContextPacker.pack()`'s real return value — `{"target_file": str, "target_symbol": str, "max_tokens": int, "tokens": int, "packed_text": str}` — so `pack_context()`'s downstream code (`estimated = int(packed.get("tokens", 0))` at `context.py:100`, the redaction/envelope logic after) runs unmodified on a cache hit vs. a real `pack()` call. On a miss, `pack_context()` calls `ContextPacker(project_root).pack(...)` exactly as today — this call is never gated on cache-write permission, so an ungranted caller still gets their real, uncached answer. The write-back into `TypedArtifactStore` (`write(subject=subject, trust_tier="DERIVED", content=packed, source="context_pack", symbol_ref=f"{context_path}::{target_symbol}" if target_symbol else None)`, keyed by the identical `cache_key` used on the read side) is a second, separately-gated step: it runs only when `granted.cache_write` is `True` — the same `ExecutionPermissions(cache_write=True)` flag `pack_context()` already imports as `_WRITE_PERMISSION` from `continuity/results.py` for its unrelated CCR-overflow gate at `context.py:103`, reused rather than a new flag. Without `cache_write`, `pack_context()` still returns the real `pack()` result; it just skips the `TypedArtifactStore.write()` call, and the next call for that key misses again. `trust_tier="DERIVED"` (never `"STATED"` — Phase 61 §6.3 Invariant 1 forbids `write()` accepting `STATED` on initial insert) means a cache-filled row is subject to `evaluate_promotion()`/corroboration like any other `DERIVED` write, not silently authoritative because it originated from a cache-fill.

### 6.2 Maintenance Sub-Agent (`src/rush/memory/maintenance.py`)

```python
from dataclasses import dataclass
from typing import Literal

MaintenanceTask = Literal["promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"]

@dataclass(frozen=True)
class MaintenanceRunResult:
    task: MaintenanceTask
    processed: int
    changed: int
    errors: tuple[str, ...] = ()  # row `id` values whose per-row mutation raised; that row is skipped, cycle continues
```

`run_maintenance_cycle(task: MaintenanceTask, *, batch_size: int = 500) -> MaintenanceRunResult` acquires a `MeshLockManager` lease via `MeshLockManager().acquire(Path(".rush/memory-maintenance.lock"), agent_id="memory-maintenance", timeout_s=5.0, ttl_s=60.0, return_capability=True)` before running — `return_capability=True` is required, not optional: `release()`'s legacy `agent_id`-only path (`lock_manager.py:313-321`) checks only `owner_agent_id`, which this task uses as a fixed literal string shared by every cycle, so a stale cycle's legacy release could delete a different, live cycle's freshly-reclaimed lock (same `owner_agent_id`, different generation/verifier). `run_maintenance_cycle()` retains the returned `LockCapabilityInput` and releases with it (`MeshLockManager().release(path, capability=capability)`), which verifies the token against the *current* lock file's `verifier_record` — a stale cycle's capability fails that check and correctly does nothing once a newer cycle has reclaimed the lock. Mid-cycle, the loop renews the lease every 50 rows via `MeshLockManager().renew(path, capability, ttl_s=60.0)`; if `renew()` returns `False` (lease already lost to expiry+reclaim), the cycle stops processing further rows immediately, returns the partial `MaintenanceRunResult` accumulated so far, and does not call `release()` (nothing to release — the lock is no longer this cycle's). Bounded per call by `batch_size` (default 500, keyword parameter, rush's own arbitrary safety bound — not sourced from anywhere — same category as Phase 29's `RemediationCircuitBreaker(max_attempts=3)`, a plainly-stated design default, not a claimed fact). Each row-level mutation runs in its own `try/except`; a row that raises has its `id` appended to `errors` and is skipped — it does not abort the cycle and is not counted in `changed`. A failure that prevents the cycle itself from running (lock not acquired, DB connection error) is not caught at this level — it propagates as a raised exception out of `run_maintenance_cycle()`, with the lock released via the held capability in a `finally` block.

All four task types read `memory_artifacts` through `TypedArtifactStore`'s existing SQLite connection (`.rush/memory.db`; columns per Phase 61 §6.1: `id, family, subject, trust_tier, content, source, created_at, symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature`):

**`"promotion_sweep"`** — re-evaluates already-written non-`STATED` rows (corroboration may have increased since they were written).
- Select: `SELECT id, family, subject, trust_tier, content, source, created_at, symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature FROM memory_artifacts WHERE trust_tier != 'STATED' AND promoted_at IS NULL ORDER BY created_at ASC LIMIT :batch_size`.
- Mutation: for each row, query `SELECT source FROM memory_artifacts WHERE subject = :subject AND symbol_ref IS :symbol_ref AND trust_tier != 'STATED'` (same `(subject, symbol_ref)` grouping key `trust.py`'s `count_corroboration()` uses, Phase 61 §6.2) to build `candidate_sources`, call `trust.py`'s `count_corroboration(subject, symbol_ref, candidate_sources)`, and set the reconstructed `MemoryArtifact.corroboration_count` to that freshly-computed value — never the row's stale stored column — before calling `evaluate_promotion(artifact, user_stated=False)` (a maintenance sweep is never itself the user, so `user_stated` is always `False` here). If `PromotionResult.promoted` is `True`: `UPDATE memory_artifacts SET trust_tier = :new_tier, promoted_at = :now, signature = :signature, corroboration_count = :recomputed_count WHERE id = :id`; counts toward `changed`. Otherwise, if the recomputed count differs from the stored one, `UPDATE ... SET corroboration_count = :recomputed_count WHERE id = :id` still runs (counts toward `changed`) so the next sweep isn't recomputing from the same stale baseline; if the count is unchanged, no mutation — row is `processed` but not `changed`.

**`"staleness_sweep"`** — periodically re-checks symbol-anchored rows against the current merkle hash, catching drift between writes (distinct from Phase 61's per-`recall()` merkle check, which only fires on read).
- Select: `SELECT id, symbol_ref, content_hash FROM memory_artifacts WHERE symbol_ref IS NOT NULL AND stale = 0 ORDER BY created_at ASC LIMIT :batch_size`.
- Mutation: recompute the current merkle AST hash of `symbol_ref` via `merkle_invalidator.py`'s `MerkleInvalidator.hash_content()` — the same pure hashing function Phase 61's recall-time check uses (§6.3 Invariant 6 there), no new hashing added. If it no longer matches the stored `content_hash`: `UPDATE memory_artifacts SET stale = 1 WHERE id = :id`; counts toward `changed`. Otherwise no mutation.

**`"skill_admission_check"`** — checks whether a pending `skill_pattern` candidate has since been explicitly trust-granted by a human (Phase 61 T-61.27: a generated SKILL.md stays non-executable until `PluginTrustStore.grant_trust()` is explicitly called; this task never calls `grant_trust()` itself — granting trust is human-gated, not automated by a sweep).
- Select: `SELECT id, family, subject, trust_tier, content, source, created_at, symbol_ref, content_hash, corroboration_count, promoted_at, stale, signature FROM memory_artifacts WHERE subject = 'skill_pattern' AND trust_tier != 'STATED' AND promoted_at IS NULL ORDER BY created_at ASC LIMIT :batch_size`.
- Mutation: for each row, call `PluginTrustStore().is_trusted(plugin_name, closure_digest)` (`src/rush/plugins/trust_store.py:158`) using the plugin identity recorded in the row's `content`. If trust was granted since the row was written: run the same `evaluate_promotion(artifact, user_stated=False)` path as `"promotion_sweep"` and apply the same `UPDATE` on success; counts toward `changed`. If still untrusted: no mutation — the row stays a pending candidate.

**`"expiry_sweep"`** — dispatches to `expiry.py`'s `sweep_expired()` (§6.3), wired once P62.7.2 lands (§8.2b ordering already covers this).

For all four: `processed` is the row count the `SELECT` returned (bounded by `batch_size`); `changed` is the count actually mutated; `errors` is the `id`s whose per-row `try/except` caught an exception (counted in `processed`, not in `changed`).

Note: T-62.05/T-62.06 (§7) verify lock lifecycle and the `batch_size` bound only — neither asserts per-task-type mutation correctness (no test seeds a corroboration-eligible row and asserts `promotion_sweep` actually promotes it, for example). That gap is separate from this section's ask (task-card detail sufficient for implementation, not test coverage) and is flagged here rather than left silently implicit.

### 6.3 Expiry Policy (`src/rush/memory/expiry.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExpiryPolicy:
    subject: str
    trust_tier: str
    ttl_seconds: int | None  # None = never expires

DEFAULT_POLICIES: tuple[ExpiryPolicy, ...] = (
    ExpiryPolicy(subject="*", trust_tier="STATED", ttl_seconds=None),
    # Resolved (not left open — the synthesis doc's line 208 named no duration,
    # so rush needed its own rationale per P62.7.1's escape hatch). Grounded in
    # this codebase's own existing precedent for "how long does non-authoritative
    # data stay relevant": src/rush/hotspots/time_decay.py:12's
    # `half_life_days: float = 90.0` for git-commit-churn weighting — the closest
    # same-repo analog to memory-record relevance decay. Tiered by trust
    # confidence, shortest for the least-vetted tier:
    ExpiryPolicy(subject="*", trust_tier="DERIVED", ttl_seconds=14 * 86400),        # 14 days — agent-inferred, lowest confidence, most likely to be corroborated or superseded quickly
    ExpiryPolicy(subject="*", trust_tier="EXTERNAL_WRITE", ttl_seconds=30 * 86400), # 30 days — another tool wrote it, unvetted by this tool
    ExpiryPolicy(subject="*", trust_tier="IMPORTED", ttl_seconds=90 * 86400),       # 90 days — cross-tool handoff, already passed some vetting; matches time_decay.py's own 90-day precedent exactly
)
```

First-match-wins against `(subject, trust_tier)`, `"*"` as wildcard — same first-match-wins shape the synthesis doc cited from `moorcheh-ai/memanto`'s `MemoryPolicyService` (idea only, no literal source copied). `sweep_expired() -> int` runs as a `MaintenanceTask`, stamps `expired_at`/`expired_by="expiry_sweep"` on an explicit pass — never silently recomputed on read (matches Phase 61's own Invariant-writing style: no silent state changes on a read path). `MemoryArtifact` (`src/rush/memory/store.py`, Phase 61 §6.1 — currently `stale: bool = False`, no expiry field) gains a fourth field, `expired: bool = False`, set from the row's `expired_at IS NOT NULL` at hydration time — the same computed-at-read pattern `stale` already uses. `TypedArtifactStore.recall()` is extended to compute and return `expired` on every result exactly as it already does for `stale` (Phase 61's staleness invariant: "the caller is told `stale: true` in the result — never silently served as fresh"): an expired record is still returned, with `expired=True`, never silently filtered out of `recall()`'s result set — filtering is the caller's own responsibility, applied after `recall()` returns, same as `stale`.

### 6.4 Decision-Record Schema Extension (`src/rush/memory/decision_schema.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DecisionRecordFields:
    """Embedded inside MemoryArtifact.content for subject in {"architectural_decision", "failure"}."""
    red_task: str | None = None
    green_task: str | None = None
    target_seam: str | None = None
    test_file: str | None = None
    test_function: str | None = None
    predecessor: str | None = None
    status: str = "in_progress"  # rush's own choice, not borrowed from remediation-contracts.toml — that file's vocabulary is a closed, finished ledger (verified: all 16 of 16 entries use "completed", grepped directly, zero other value has ever appeared there) with no in-progress state to reuse, since its program is done. A live decision-record store needs a real default for a record that's just been written and not yet validated; "completed" would be actively false for that case, and the earlier "open" default was invented with no source at all. "completed" itself remains a valid non-default value this field can be set to once a decision's red/green tasks both land.
```

Wiring is scoped to the one real candidate-shaping call site that exists for either subject by the time this phase runs: `src/rush/memory/mistake_miner.py`'s pure shaping function (added by Phase 61's P61.6.2, `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md`, §9 P61.6.2 task card — corrected to stay pure, no inline `TypedArtifactStore.write()` call; persisting the shaped candidate happens only through whatever permissioned caller invokes `MemoryTool.write()` with it, gated the same way `_run_save` gates `_WRITE_PERMISSION`). P62.8.2 extends that shaping function's output dict to include a `DecisionRecordFields` instance (serialized via `dataclasses.asdict`), populated from what `mine_mistakes()` already returns (`src/rush/memory/mistake_miner.py`): `reverted_subject` → `target_seam`; `rationale` folded into `content` alongside the typed fields; `red_task`/`green_task`/`test_file`/`test_function`/`predecessor` stay at their declared `None` defaults — `mine_mistakes()`'s git-revert-log source has no such data to populate them with, so nothing is invented to fill them.

**`architectural_decision` is schema-only in this phase, not wired.** Phase 61 explicitly scoped `architectural_decision` to migration-only (`phase-61-cross-llm-memory-typed-artifact-schema-plan.md`, §9 P61.6.2's preceding note: "Architectural-decision is fully covered by P61.3's generic migration... no new forward-write behavior") and this plan adds none either — there is no call site anywhere in Phase 61 or Phase 62 that writes a new `subject="architectural_decision"` record going forward, only the one-time migration of old `invariant_graph.py` rows. `DecisionRecordFields` remains usable for that subject (the dataclass doesn't gate on `subject`), but nothing in either phase produces a live `architectural_decision` write to wire it into; a future phase that adds one can reuse this schema unchanged.

### 6.5 State Invariants

1. **Cache-gate invariant:** `check_memory_before_pack()` itself never mutates state — read-only, calls `TypedArtifactStore.search()` then `recall()` only (§6.1), never `write()`. The cache-*gate* read and `pack_context()`'s post-miss cache-*fill* write are two distinct calls with two distinct authorization requirements — see §6.1's write-back gating.
2. **Maintenance-lock invariant:** every `run_maintenance_cycle()` call acquires and releases a `MeshLockManager` lease; a crash mid-cycle must not leave a stale held lock (verify `MeshLockManager`'s own expiry semantics, don't reinvent one).
3. **Diff-not-blob invariant:** a handoff to a tool that already received a prior handoff sends only the delta (fields changed since the last handoff to that same tool), computed via a plain dict-diff — no new diff library. Enabled by a new `target_provider: str | None` field threaded through the existing handoff path: `SessionContinuityTool.__call__()` (`src/rush/tools/continuity.py:84`) already takes a `provider_id: str | None = None` parameter (line 107) but its `handoff={...}` dict literal (lines 115-120: `current_goal`, `open_work`, `historic_instruction`, `failure_fingerprint`, `dependencies`) never includes it; `save_receipt()` (`src/rush/continuity/receipts.py:62-90`) never receives or stores it either. "Last handoff to the same tool" is answered from `CheckpointJournal.list_checkpoints()` (`src/rush/memory/checkpoint_journal.py:61-91`, already returns every saved checkpoint sorted newest-first by `created_at`), filtering on `metadata["handoff"]["target_provider"] == target_provider` and taking the first match — no new storage or `TypedArtifactStore` dependency required for this lookup. `target_provider` must be threaded at `run()`'s dispatch level (`continuity.py:208-210`), not only inside `__call__()`'s `handoff={...}` dict literal: `run()` itself has an independent `provider_id: str | None = None` parameter (line 160) that its `"save"` dispatch branch currently drops entirely (`_run_save()` never receives it, line 216-224), and `src/rush/cli.py`'s `rush session save` command (`cli.py:1936-1957`) calls `SessionContinuityTool().run()` directly — bypassing `__call__()` completely — with a hand-built `handoff={...}` dict that has no provider field and no `--provider` CLI option to set one. The fix merges `provider_id` into `handoff` inside `run()` itself (`handoff = {**(handoff or {}), "target_provider": provider_id}` before dispatch), so every caller of `run()` — `__call__()`, `cli.py`, `mcp.py`, and any future caller — gets the merge for free regardless of whether it goes through `__call__()`.
4. **Attribution-trail invariant:** a linked commit reference stores the commit SHA, never the full commit content — the trail is a pointer, not a duplicate copy of git history.
5. **API-diff-staleness invariant:** distinct from Invariant 6 (merkle content-hash) in Phase 61, not because the two checks can disagree about whether a file's bytes changed (identical bytes always produce an identical AST-derived signature and an identical sha256 hash — they read the same file content, so "signature broke, hash didn't" cannot happen from a real edit) but because they compare against different baselines. `ApiDiffer.diff_file()` (`src/rush/tools/api_diff.py:36-63`) always diffs the current working-tree file against `git show {base_ref}:{rel_path}` with `base_ref` defaulting to `"main"` (line 38) — a fixed, git-ref-relative baseline. `MerkleInvalidator.check_and_update(symbol_key, content)` (`src/rush/memory/merkle_invalidator.py:59-75`) compares against whatever content was last hashed under that `symbol_key` — an arbitrary, caller-controlled baseline with no relationship to `main`, typically "the content this `MemoryArtifact` was last checked against." A `MemoryArtifact` citing a signature that already differed from `main` before the record was ever written (e.g., written against an uncommitted local edit) has a merkle baseline that already reflects the broken signature — `check_and_update()` reports no drift on every subsequent call — while `ApiDiffer.diff_file()` against `main` reports a real breaking change on every call, since `main` never had it. `stale=True` fires from the `ApiDiffer` path in that case even though the merkle path reports no change; the reverse (merkle-only staleness with no cited signature broken) is the ordinary case Invariant 6 already covers.
6. **Expiry-is-explicit invariant:** `stale`≠`expired`. Staleness (Phase 61) means "the code changed, this may be wrong now." Expiry (P62.7) means "this record's TTL ran out, regardless of whether the code changed." A record can be stale-but-not-expired or expired-but-not-stale; these are independent booleans, never conflated into one field.

---

## 7. Contract Test Inventory (T-62.01 through T-62.26)

| Test ID | Test File | Test Function | Target Contract |
|---|---|---|---|
| T-62.01 | `tests/test_phase62_cache_gate.py` | `test_cache_hit_returns_stored_content_without_new_pack` | Seeds a `domain_knowledge` record under cache key `f"{context_path}:{target_symbol}"` for a given `(context_path, target_symbol)` pair; calls `pack_context()` with that same pair; asserts `check_memory_before_pack()` returns `hit=True`, the result matches the seeded content, and `ContextPacker.pack()` (spied at `context.py:97`'s call site) is never invoked. |
| T-62.02 | `tests/test_phase62_cache_gate.py` | `test_cache_miss_falls_through_to_pack` | No record exists for the `(context_path, target_symbol)` key; asserts `hit=False` and `pack_context()` proceeds to call `ContextPacker.pack()` normally (spy shows exactly one call). |
| T-62.03 | `tests/test_phase62_review_memory.py` | `test_review_finding_cites_prior_failure_memory` | Seeds a `STATED` failure record matching a new review finding's pattern; asserts the review's reported output references it ("this pattern already caused a fix in commit X"). |
| T-62.04 | `tests/test_phase62_review_memory.py` | `test_review_cites_architectural_decision` | Seeds a `STATED` architectural-decision record matching a review target; asserts `ReviewTool.run()` (the same call T-62.03 exercises for failure records — no separate planning surface exists in this codebase, §3.1) recalls it via `TypedArtifactStore.recall(subject="architectural_decision", ...)` and surfaces the citation in its output. |
| T-62.05 | `tests/test_phase62_maintenance.py` | `test_maintenance_cycle_acquires_and_releases_lock` | Asserts `run_maintenance_cycle()` calls `MeshLockManager.acquire`/`release` (spy), releases even when the cycle body raises. |
| T-62.06 | `tests/test_phase62_maintenance.py` | `test_maintenance_cycle_respects_batch_size_parameter` | Seeds 600 candidate rows, calls `run_maintenance_cycle(task, batch_size=500)` explicitly (not relying on the default); asserts exactly 500 processed in this cycle, remainder left for the next; a second test in the same function calls with `batch_size=50` and asserts exactly 50 processed, proving the bound is a real parameter, not a hardcoded constant. |
| T-62.07 | `tests/test_phase62_handoff_diff.py` | `test_second_handoff_to_same_tool_sends_delta_only` | Saves a checkpoint via `SessionContinuityTool.__call__(operation="save", provider_id="codex_cli", ...)`, then a second with the same `provider_id="codex_cli"` and one changed field; asserts the second saved receipt's diff (against the prior checkpoint found via `CheckpointJournal.list_checkpoints()` filtered on `metadata["handoff"]["target_provider"] == "codex_cli"`) contains only the changed field, not the full snapshot. |
| T-62.08 | `tests/test_phase62_handoff_diff.py` | `test_first_handoff_to_a_tool_sends_full_snapshot` | No prior saved checkpoint has `metadata["handoff"]["target_provider"] == "codex_cli"`; asserts the full snapshot is sent (no delta base to diff against). |
| T-62.09 | `tests/test_phase62_attribution.py` | `test_fix_commit_links_to_originating_failure_record` | Seeds a failure record, a matching `is_fix=True` commit from `GitTrailerParser`; asserts a queryable link exists from the commit SHA back to the failure record's id. |
| T-62.10 | `tests/test_phase62_attribution.py` | `test_attribution_stores_sha_not_full_commit_content` | Asserts the stored link contains a commit SHA string, not the full diff/commit body (Invariant 4). |
| T-62.11 | `tests/test_phase62_api_staleness.py` | `test_signature_break_flags_stale_via_main_diff_when_merkle_baseline_predates_it` | Seeds a `MemoryArtifact` citing a function signature and merkle-hashes it (via `MerkleInvalidator.check_and_update`) against its *current* on-disk content, so the merkle baseline matches with zero drift going forward. Sets up a real git repo where `main`'s committed version of that file has the pre-break signature and the working-tree version (already merkle-hashed) has the post-break signature — no mocked hash output. Calls `ApiDiffer.diff_symbol(path, symbol, base_ref="main")`; asserts it reports the symbol broken (not `None`/`"unknown"`). Asserts `TypedArtifactStore.recall()` flags `stale=True` via the `ApiDiffer` path, and separately asserts `MerkleInvalidator.check_and_update()` for that symbol returns `False` (no drift) — proving the two checks fire independently off different baselines, not off a rigged hash. |
| T-62.12 | `tests/test_phase62_expiry.py` | `test_stated_records_never_expire` | A `STATED` record, TTL sweep run repeatedly; asserts never expired. |
| T-62.13 | `tests/test_phase62_expiry.py` | `test_derived_record_expires_after_configured_ttl` | A `DERIVED` record older than its configured 14-day TTL (§6.3, resolved); asserts `sweep_expired()` stamps `expired_at`/`expired_by` once that TTL elapses. |
| T-62.14 | `tests/test_phase62_expiry.py` | `test_expiry_and_staleness_are_independent` | A record that is stale but not expired, and one that is expired but not stale; asserts both booleans independently correct (Invariant 6). |
| T-62.15 | `tests/test_phase62_decision_schema.py` | `test_architectural_decision_record_carries_remediation_shaped_fields` | Writes an `architectural_decision` record with `DecisionRecordFields`; asserts round-trip through `content` JSON preserves all 7 fields. |
| T-62.16 | `tests/test_phase62_decision_schema.py` | `test_status_defaults_in_progress_and_accepts_completed` | Asserts a new `DecisionRecordFields` defaults `status="in_progress"`, and that setting `status="completed"` round-trips correctly. `remediation-contracts.toml`'s own vocabulary (verified: `"completed"` only, all 16 of 16 entries, no other value ever observed) does not define an in-progress state to match against — this test is against rush's own default, not a borrowed vocabulary. |
| T-62.17 | `tests/test_phase62_decision_schema.py` | `test_mistake_miner_failure_write_carries_decision_schema_round_trip` | Runs `mine_mistakes()` against a seeded revert commit, gets the shaped candidate dict from `mistake_miner.py`'s pure shaping function (`DecisionRecordFields`-populated per §6.4); calls `TypedArtifactStore.write(subject="failure", trust_tier="DERIVED", content=candidate, ...)` directly in the test (simulating the real, permissioned caller — `mistake_miner.py` itself never calls `write()`, per P61.6.2's correction); asserts the stored row recalls with the `DecisionRecordFields`-shaped `content` intact — an end-to-end shape-then-write-then-recall, not dataclass serialization in isolation. |
| T-62.18 | `tests/test_phase62_cache_gate.py` | `test_cache_hit_with_failed_recall_defense_falls_through_to_pack` | Seeds a `domain_knowledge` row under the exact cache key with a corrupted `signature` (or Trojan-source `content`); asserts `check_memory_before_pack()` returns `hit=False` (not a propagated exception) and `pack_context()` proceeds to call the real `ContextPacker.pack()`. |
| T-62.19 | `tests/test_phase62_cache_gate.py` | `test_cache_miss_write_back_requires_cache_write_permission` | Calls `pack_context()` on a miss with `granted.cache_write=False`; asserts the real `pack()` result is still returned, and that no row was written to `TypedArtifactStore` (spy `write()`, assert never called). |
| T-62.20 | `tests/test_phase62_cache_gate.py` | `test_cache_miss_write_back_uses_derived_trust_tier_and_exact_key` | Calls `pack_context()` on a miss with `granted.cache_write=True`; asserts the written row's `trust_tier == "DERIVED"` and its stored key exactly matches `f"{context_path}:{target_symbol}"` (not a fuzzy/partial FTS match) — a second, different `(context_path, target_symbol)` pair must still miss. |
| T-62.21 | `tests/test_phase62_maintenance.py` | `test_expired_lease_reclaimed_by_second_cycle_survives_first_cycles_stale_release` | Starts cycle A with `ttl_s` set to expire before its 500-row batch finishes; lets cycle B acquire the reclaimed lock (different generation, same `agent_id` literal); asserts cycle A's stale `release()` call (via its own now-stale capability) returns `False` and does NOT delete cycle B's live lock — `MeshLockManager.inspect()` still reports `state="held"` with cycle B's generation after cycle A's cleanup runs. |
| T-62.22 | `tests/test_phase62_maintenance.py` | `test_memory_tool_maintain_operation_dispatches_to_run_maintenance_cycle` | Calls `MemoryTool()(operation="maintain", task="promotion_sweep")` (spy on `run_maintenance_cycle`); asserts it is invoked with `task="promotion_sweep"` and the operation is reachable via the registered CLI/MCP path (`rush memory maintain`), not only by direct import in a test. |
| T-62.23 | `tests/test_phase62_handoff_diff.py` | `test_direct_run_caller_without_call_still_threads_provider_id` | Calls `SessionContinuityTool().run(root, operation="save", name=..., handoff={...no target_provider key...}, provider_id="codex_cli")` directly (bypassing `__call__()`, matching `cli.py:1936`'s real call shape); asserts the persisted receipt's `metadata["handoff"]["target_provider"] == "codex_cli"`. |
| T-62.24 | `tests/test_phase62_expiry.py` | `test_external_write_record_expires_after_configured_ttl` | An `EXTERNAL_WRITE` record older than its configured 30-day TTL (§6.3, resolved); asserts `sweep_expired()` stamps `expired_at`/`expired_by` once that TTL elapses. |
| T-62.25 | `tests/test_phase62_expiry.py` | `test_imported_record_expires_after_configured_ttl` | An `IMPORTED` record older than its configured 90-day TTL (§6.3, resolved); asserts `sweep_expired()` stamps `expired_at`/`expired_by` once that TTL elapses. |
| T-62.26 | `tests/test_phase62_api_staleness.py` | `test_unavailable_base_ref_reports_unknown_not_fresh` | Seeds a `MemoryArtifact` citing a symbol, merkle-hashed with no drift; calls `ApiDiffer.diff_symbol()` against a `base_ref` that does not exist in the test repo (simulating a missing/renamed default branch); asserts it returns `"unknown"`, not `None`; asserts `recall()` does not clear an existing merkle-set `stale=True` on the strength of that unknown result. |

Coverage: 26 of 26 contract tests specified above are the complete set for this phase (T-62.01 through T-62.26 — T-62.18/19/20 added for the cache-gate defended-read and write-back-gating corrections, T-62.21 for maintenance lease-expiry-during-cycle, T-62.22 for the `MemoryTool` "maintain" dispatch, T-62.23 for the direct `run()`-caller provider-id regression, T-62.24/25 for `EXTERNAL_WRITE`/`IMPORTED` expiry coverage, T-62.26 for API-diff-staleness unknown-baseline handling); §10 re-runs all 26 by name.

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

**New:** `src/rush/token_economy/memory_cache_gate.py`, `src/rush/memory/maintenance.py`, `src/rush/memory/expiry.py`, `src/rush/memory/decision_schema.py`, `tests/test_phase62_cache_gate.py`, `tests/test_phase62_review_memory.py`, `tests/test_phase62_maintenance.py`, `tests/test_phase62_handoff_diff.py`, `tests/test_phase62_attribution.py`, `tests/test_phase62_api_staleness.py`, `tests/test_phase62_expiry.py`, `tests/test_phase62_decision_schema.py`, `docs/phase-plans/phase-62-implementation-evidence.md`, `governance/remediation-phase-62.toml`.

**Modified:** `src/rush/memory/store.py` (additive columns for P62.7: `expires_at`, `expired_at`, `expired_by`), `src/rush/continuity/context.py` (`pack_context()`, confirmed §6.1), `rush.review`'s entry point (confirmed at P62.2.1), `src/rush/tools/continuity.py` + `src/rush/continuity/receipts.py` + `providers.py` (diff-not-blob, `target_provider` threading), `src/rush/tools/provenance_ai.py` + `src/rush/session_memory.py` (attribution linkage), `src/rush/tools/api_diff.py` (emits a staleness signal `TypedArtifactStore` consumes), `src/rush/memory/mistake_miner.py` (extended by P62.8.2 to embed `DecisionRecordFields`).

### 8.2 Documentation Synchronization

This phase reuses Phase 61's doc-inventory methodology (full grep sweep, not a guess). At P62-implementation time, re-run a grep sweep for all 19 of these terms — the 14 base terms from Phase 61's §8.2 (`session_memory`, `preference_store`, `invariant_graph`, `failure_ledger`, `mistake_miner`, `checkpoint_journal`, `continuity/receipts`, `continuity/coordination`, `continuity/providers`, `ADR-0030`, `quarantined`, `typed-artifact`, `agent memory`, `memory subsystem`, `epistemic memory`) plus 5 more specific to this phase's own new surface: `memory_cache_gate`, `run_maintenance_cycle`, `ExpiryPolicy`, `DecisionRecordFields`, `attribution trail`. **This document does not pre-enumerate the resulting file list** — unlike Phase 61, where the sweep was actually run this session (71 of 353 files confirmed needing updates, after correction — see Phase 61's own §8.2 coverage statement for the full history of that number). Running that sweep now, before Phase 61 even exists, would classify files against code that doesn't exist yet and go stale the moment Phase 61 lands. P62.9 (below) runs the real sweep at P62's own implementation time, against the real post-Phase-61-and-P62 codebase — named as a task, not skipped.

#### P62.9 — VERIFY/DOCS: Run the Real Doc Sweep and Synchronize

##### P62.9.1 — DISCOVERY: Run the Sweep and Freeze the File List
- **Task ID:** P62.9.1
- **Binary Outcome:** Grep sweep run against the actual post-implementation `/docs` tree (not guessed here); each hit classified individually (needs update / already correct / out of scope, same 3-way split as Phase 61's §8.2); the resulting file list frozen — written once, not revised by P62.9.2.
- **Prerequisites:** P62.1 through P62.8 all GREEN.
- **Allowed Writes:** `docs/phase-plans/phase-62-implementation-evidence.md` only — this task classifies and records, it does not edit any `/docs` content file.
- **Actions:**
  1. Run the grep sweep (§8.2's term list) against the real `/docs` tree at this point in time.
  2. Classify each hit; record the frozen file list, per-file classification, and total count in `docs/phase-plans/phase-62-implementation-evidence.md` — this list becomes P62.9.2's exact `Allowed Writes`, no file added or removed after this point.

##### P62.9.2 — SYNCHRONIZE: Apply Fixes to the Frozen List
- **Task ID:** P62.9.2
- **Binary Outcome:** Coverage: the number of files fixed here equals P62.9.1's recorded "needs update" count exactly, name for name against that frozen list, same rigor as Phase 61's §8.2; `docs/phase-plans/README.md` and `docs/developer/backlog.md` gain a Phase 62 row; `governance/remediation-phase-62.toml` documents all contract tests.
- **Prerequisites:** P62.9.1.
- **Allowed Writes:** exactly the files listed in P62.9.1's frozen evidence-note file list, plus `docs/phase-plans/README.md` (add Phase 62 row), `docs/developer/backlog.md` (add Phase 62 row), `governance/remediation-phase-62.toml`.
- **Actions:**
  1. Fix the files named in P62.9.1's frozen list, one for one against its recorded count — none skipped, nothing outside it touched.
  2. Add the Phase 62 row to `docs/phase-plans/README.md` and `docs/developer/backlog.md`.
  3. Create `governance/remediation-phase-62.toml` documenting all contract tests.

### 8.2b File Conflict Ordering

`src/rush/memory/store.py` is touched by two tasks: P62.6.2 (additive staleness check in `recall()`) and P62.7.2 (additive `expires_at`/`expired_at`/`expired_by` columns). Both are purely additive with no overlapping fields, but ordering is fixed to avoid a merge surprise: **P62.6.2 before P62.7.2** (staleness logic lands first since P62.6 has no dependency on expiry fields; P62.7's migration runs against the already-updated file).

`docs/phase-plans/phase-62-implementation-evidence.md` is touched by three tasks: P62.0.1 (create, baseline), P62.7.1 (record the resolved TTL durations before authoring T-62.13/T-62.24/T-62.25), P62.9.1 (frozen doc-sweep file list and classification — the record P62.9.2's `Allowed Writes` reads from, not a completion note). Order: **P62.0.1 → P62.7.1 → P62.9.1**, already enforced by each task's own Prerequisites chain (P62.7.1 depends on P62.0.1; P62.9.1 depends on P62.1 through P62.8 all being GREEN, which is downstream of P62.7.1) — restated here explicitly per plan-review Pass 2, same as Phase 61's §8.4 convention. P62.9.2 depends on P62.9.1 and writes only the frozen file list plus `docs/phase-plans/README.md`, `docs/developer/backlog.md`, `governance/remediation-phase-62.toml` — it never touches the evidence file.

`src/rush/memory/maintenance.py` is touched by two tasks: P62.3.2 (create, implements `run_maintenance_cycle` and the base `MaintenanceTask` Literal) and P62.7.2 (add the `"expiry_sweep"` value and its dispatch case). Order: **P62.3.2 → P62.7.2**, already enforced by P62.7.2's own Prerequisites (P62.3.2) — restated here per plan-review Pass 2.

### 8.3 Dependency Constraints

Zero third-party dependencies. Python 3.12 standard library only.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P62.0 — Admission Gate & Baseline

#### P62.0.1 — EVIDENCE: Confirm Phase 61 Complete, Confirm 3 Integration Points
- **Task ID:** P62.0.1
- **Binary Outcome:** `docs/phase-plans/phase-62-implementation-evidence.md` created; Phase 61's exit checklist confirmed 100%; the 3 integration points in §2.2 confirmed via grep, exact paths recorded.
- **Prerequisites:** §4 admission gate.
- **Allowed Writes:** `docs/phase-plans/phase-62-implementation-evidence.md`.
- **Actions:** Run `pytest tests/ -q`, record baseline. Grep for the context-pack entry point, `rush.review`'s finding-report entry point, and `session_memory.py`'s post-Phase-61 episodic write signature; record all 3 exact locations.

### P62.1 — Token-Savings Cache Front-End

#### P62.1.1 — RED
- **Binary Outcome:** `tests/test_phase62_cache_gate.py` with T-62.01, T-62.02, T-62.18, T-62.19, T-62.20; all 5 fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_cache_gate.py`.
- **Actions:** Author all 5 tests against `pack_context()` in `src/rush/continuity/context.py:68-158` (the confirmed, sole caller of `ContextPacker.pack()` — `context.py:97`, per §6.1); run, confirm RED.

#### P62.1.2 — GREEN
- **Binary Outcome:** `src/rush/token_economy/memory_cache_gate.py` implements `check_memory_before_pack(context_path, target_symbol, subject="domain_knowledge")` per §6.1 — `search()`-then-`recall()` defended lookup on read, `cache_write`-gated `DERIVED` write-back on miss; all 5 tests pass; `pack_context()` calls it before line 97's `ContextPacker(project_root).pack(...)`, reusing its `(context_path, target_symbol)` arguments unchanged as the cache key inputs.
- **Prerequisites:** P62.1.1 RED.
- **Allowed Writes:** `src/rush/token_economy/memory_cache_gate.py`, `src/rush/continuity/context.py`.
- **Actions:** Implement `check_memory_before_pack()` per §6.1 (search for a match, `recall()` it defensively, `hit=False` on any defense failure or `stale=True`); wire it into `pack_context()` immediately before the `ContextPacker(...).pack(...)` call at `context.py:97-99`, short-circuiting to the cached `content` dict on a hit and, on a miss, writing the real `pack()` result back to `TypedArtifactStore` only when `granted.cache_write` is `True`; run, confirm GREEN.

### P62.2 — Review/Development Reading Memory

#### P62.2.1 — RED
- **Binary Outcome:** `tests/test_phase62_review_memory.py` with T-62.03, T-62.04; both fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_review_memory.py`.
- **Actions:** Confirm `rush.review`'s entry point (`src/rush/tools/review.py:144`, `ReviewTool.run()`) from P62.0.1's evidence; author T-62.03 (failure-record citation) and T-62.04 — retargeted to `subject="architectural_decision"` recalled by the same `ReviewTool.run()` call, not a separate planning step (no planning surface exists in this codebase — see §3.1); run, confirm RED.

#### P62.2.2 — GREEN
- **Binary Outcome:** `ReviewTool.run()` (`src/rush/tools/review.py`) calls `TypedArtifactStore.recall(subject="failure", query=...)` and `recall(subject="architectural_decision", query=...)` for matching records before `assemble_review_result()` (line 180); both tests pass.
- **Prerequisites:** P62.2.1 RED.
- **Allowed Writes:** `src/rush/tools/review.py`.
- **Actions:** Wire both recall calls between `_evaluate_target_heuristics()` (line 168) and `assemble_review_result()` (line 180); format citations into `findings`; run, confirm GREEN.

### P62.3 — Maintenance Sub-Agent

#### P62.3.1 — RED
- **Binary Outcome:** `tests/test_phase62_maintenance.py` with T-62.05, T-62.06, T-62.21, T-62.22; all 4 fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_maintenance.py`.
- **Actions:** Author all 4; run; confirm RED.

#### P62.3.2 — GREEN
- **Binary Outcome:** `src/rush/memory/maintenance.py` implements `run_maintenance_cycle()` per §6.2 — 3 of the 4 `MaintenanceTask` variants' select/mutation/failure-handling as specified there (`"promotion_sweep"`, `"staleness_sweep"`, `"skill_admission_check"`; `"expiry_sweep"` is a valid `Literal` value here but its dispatch body is added later, by P62.7.2 — this task does not implement it, matching §6.2's own text), including lease renewal and capability-scoped release (§6.2 correction); `src/rush/tools/memory.py`'s reserved `"maintain"` CLI/MCP leaf (Phase 61's P61.12.2 — real, registered, previously `status="skipped"`) now dispatches to `run_maintenance_cycle()`, accepting a `task: MaintenanceTask` kwarg; T-62.05, T-62.06, T-62.21, T-62.22 all pass.
- **Prerequisites:** P62.3.1 RED.
- **Allowed Writes:** `src/rush/memory/maintenance.py`, `src/rush/tools/memory.py` (wire the `"maintain"` operation's dispatch to `run_maintenance_cycle()` — the operation itself and its `Literal` slot already exist per Phase 61 P61.12.2, only the dispatch body is added here).
- **Actions:** Implement with `MeshLockManager` lease acquire/release (try/finally, fixed `agent_id="memory-maintenance"` per §6.2), `batch_size` keyword parameter (default 500, not hardcoded), per-row `try/except` isolating row failures into `MaintenanceRunResult.errors` without aborting the cycle, and the four per-task select/mutation bodies specified in §6.2 (`"expiry_sweep"` is a valid `Literal` value with no dispatch case until P62.7.2 adds `expiry.py`, per that task's own Prerequisites); wire `MemoryTool`'s `"maintain"` operation to call it; run, confirm GREEN.

### P62.4 — Handoff Diffs

#### P62.4.1 — RED
- **Binary Outcome:** `tests/test_phase62_handoff_diff.py` with T-62.07, T-62.08, T-62.23; all 3 fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_handoff_diff.py`.
- **Actions:** Author all 3; run; confirm RED.

#### P62.4.2 — GREEN
- **Binary Outcome:** `continuity/receipts.py` sends a delta on the second-and-later handoff to the same tool, for every caller of `SessionContinuityTool.run(operation="save", ...)` — not only callers that go through `__call__()`; both tests plus T-62.23 pass.
- **Prerequisites:** P62.4.1 RED.
- **Allowed Writes:** `src/rush/tools/continuity.py` (merge `provider_id` into `handoff` inside `run()`'s `"save"` dispatch branch at lines 208-210 — `handoff = {**(handoff or {}), "target_provider": provider_id}` — before calling `_run_save()`; `_run_save()`'s signature gains no new parameter, it reads `target_provider` off the already-merged `handoff` dict it already receives), `src/rush/continuity/receipts.py` (`save_receipt()` persists `target_provider`; add a `last_handoff_for_provider(project_root, target_provider)` lookup over `CheckpointJournal.list_checkpoints()`), `src/rush/continuity/providers.py` (`provider_handoff()` propagates `target_provider` through instead of dropping it), `src/rush/cli.py` (add a `--provider` / `provider_id` option to `session_save_cmd`, lines 1933-1958, mirroring `session_resume_cmd`'s existing `--provider` option at lines 1988-1993; pass it through to `.run(..., provider_id=provider_id, ...)`).
- **Actions:** Merge `target_provider` into `handoff` at `run()`'s single dispatch point rather than only in `__call__()`'s dict literal, so `cli.py`'s direct `.run()` caller and any other direct caller get it too; add `--provider` to `rush session save`; persist `target_provider` in the receipt schema; implement `last_handoff_for_provider()` as a filter over `CheckpointJournal.list_checkpoints()` on `metadata["handoff"]["target_provider"]`; compute a plain dict-diff between the new handoff and that prior handoff's fields; run, confirm GREEN.

### P62.5 — AI-Attribution Trail

#### P62.5.1 — RED
- **Binary Outcome:** `tests/test_phase62_attribution.py` with T-62.09, T-62.10; both fail.
- **Prerequisites:** P62.0.1 (confirms `session_memory.py`'s post-Phase-61 signature).
- **Allowed Writes:** `tests/test_phase62_attribution.py`.
- **Actions:** Author both against the confirmed signature; run; confirm RED.

#### P62.5.2 — GREEN
- **Binary Outcome:** A commit classified `is_fix=True` by `GitTrailerParser` links to the failure record it fixed; both tests pass.
- **Prerequisites:** P62.5.1 RED.
- **Allowed Writes:** `src/rush/tools/provenance_ai.py`, `src/rush/session_memory.py`.
- **Actions:** Implement the link (commit SHA stored, per Invariant 4); run, confirm GREEN.

### P62.6 — API-Diff Staleness

#### P62.6.1 — RED
- **Binary Outcome:** `tests/test_phase62_api_staleness.py` with T-62.11, T-62.26; both fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_api_staleness.py`.
- **Actions:** Author both; run; confirm RED.

#### P62.6.2 — GREEN
- **Binary Outcome:** `ApiDiffer` gains `diff_symbol(file_path: Path, symbol: str, base_ref: str = "main") -> dict[str, Any] | None` — a bounded, per-symbol wrapper around `_extract_public_signatures()`/`diff_file()`'s existing comparison logic (`src/rush/tools/api_diff.py:36-63`) returning exactly the one breaking-change dict for `symbol` (or `None`) instead of `diff_file()`'s whole-file list, so `recall()` never filters a file-wide or repo-wide (`diff_public_api()`) result down to one symbol. `TypedArtifactStore.recall()` flags `stale=True` when `diff_symbol()` reports the cited symbol broken against `base_ref="main"` (the repo's default branch name, not configurable in this phase — a repo without a `main` branch is out of scope, named here rather than silently assumed), evaluated independently of `MerkleInvalidator.check_and_update()` (`src/rush/memory/merkle_invalidator.py:59-75`) — the two checks compare against different baselines (git `main` vs. last-hashed content, per Invariant 5) and either can fire without the other. When `git show main:{rel_path}` fails for a reason other than the file being new at `base_ref` (detached HEAD, no `main` branch, shallow clone missing the ref), `diff_symbol()` returns `"unknown"` (distinct from `None`/no-break), and `recall()` leaves `stale` exactly as the merkle check already set it — an unknown API-diff result is never treated as evidence of freshness; tests pass.
- **Prerequisites:** P62.6.1 RED.
- **Allowed Writes:** `src/rush/memory/store.py` (additive check in `recall()`), `src/rush/tools/api_diff.py` (expose a query-by-symbol helper if one doesn't already exist — confirm at this task's start, don't assume).
- **Actions:** Implement `ApiDiffer.diff_symbol()` per the Binary Outcome above, splitting `diff_file()`'s existing `res.returncode != 0 or not res.stdout` check (`api_diff.py:44`) into its two real causes — a genuinely new file (no break, current behavior) vs. `base_ref`/the file at `base_ref` being unavailable for any other git reason (return `"unknown"`, not `[]`) — since today's `diff_file()` conflates both into an empty, no-break result; wire `diff_symbol()`'s output into `recall()`, evaluated as its own check alongside — not gated by — the existing merkle check; run, confirm GREEN.

### P62.7 — Per-Type Expiry

#### P62.7.1 — RED
- **Binary Outcome:** `tests/test_phase62_expiry.py` with T-62.12, T-62.13, T-62.14, T-62.24, T-62.25; all 5 fail. TTL durations for `DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` are already resolved (§6.3: 14/30/90 days, rush-own rationale grounded in `time_decay.py:12`'s 90-day precedent) — this task records that resolution in its evidence note, it does not invent or re-derive the numbers.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_expiry.py`, `docs/phase-plans/phase-62-implementation-evidence.md` (record the resolved TTL durations — 14/30/90 days — and their source, §6.3).
- **Actions:** Author all 5 tests against the resolved values (T-62.13 for `DERIVED` at 14 days, T-62.24 for `EXTERNAL_WRITE` at 30 days, T-62.25 for `IMPORTED` at 90 days); run; confirm RED.

#### P62.7.2 — GREEN
- **Binary Outcome:** `src/rush/memory/expiry.py` implements `ExpiryPolicy`/`DEFAULT_POLICIES`/`sweep_expired()` per §6.3; `store.py` gains `expires_at`/`expired_at`/`expired_by` columns, a `MemoryArtifact.expired: bool = False` field, and `recall()` computes/returns `expired` on every result per §6.3; `maintenance.py` dispatches the new `"expiry_sweep"` `MaintenanceTask` value to `sweep_expired()`; T-62.12, T-62.13, T-62.14, T-62.24, T-62.25 all pass.
- **Prerequisites:** P62.3.2 (needs `run_maintenance_cycle` and the `MaintenanceTask` Literal to already exist before this task can add a value to it and wire a dispatch case), P62.7.1 RED.
- **Allowed Writes:** `src/rush/memory/expiry.py`, `src/rush/memory/store.py` (additive columns, migration for existing Phase 61 rows to default `expires_at=NULL`), `src/rush/memory/maintenance.py` (add the `"expiry_sweep"` dispatch case).
- **Actions:** Implement `expiry.py`; add the `expired` field and `recall()` computation to `store.py` per §6.3; add `"expiry_sweep"` to `MaintenanceTask` and wire `run_maintenance_cycle()`'s dispatch to call `sweep_expired()` for it; run, confirm GREEN.

### P62.8 — Decision-Record Schema Reuse

#### P62.8.1 — RED
- **Binary Outcome:** `tests/test_phase62_decision_schema.py` with T-62.15, T-62.16, T-62.17; all 3 fail.
- **Prerequisites:** P62.0.1.
- **Allowed Writes:** `tests/test_phase62_decision_schema.py`.
- **Actions:** Author all 3 tests per §7's corrected T-62.15/T-62.16/T-62.17 (status defaults `"in_progress"`, is rush's own default, not borrowed from `remediation-contracts.toml`'s closed `"completed"`-only vocabulary); run; confirm RED.

#### P62.8.2 — GREEN
- **Binary Outcome:** `src/rush/memory/decision_schema.py` implements `DecisionRecordFields` per §6.4; `src/rush/memory/mistake_miner.py`'s pure candidate-shaping function (added by Phase 61's P61.6.2, corrected to stay pure) is extended to include a populated `DecisionRecordFields` in its output dict; all 3 tests pass.
- **Prerequisites:** P62.8.1 RED, Phase 61's P61.6.2 (the shaping function this task extends must already exist).
- **Allowed Writes:** `src/rush/memory/decision_schema.py`, `src/rush/memory/mistake_miner.py`.
- **Actions:** Implement `DecisionRecordFields`; extend `mistake_miner.py`'s existing pure candidate-shaping function (P61.6.2) to populate its output dict with a serialized `DecisionRecordFields` per §6.4's field mapping — the function still returns a dict, it still performs no `TypedArtifactStore` I/O itself (P61.6.2's correction: persistence is caller-invoked, never inline in `mistake_miner.py`); add no `architectural_decision` wiring — no forward-write call site for that subject exists in either phase (§6.4); run, confirm GREEN.

---

## 10. Final Verification and Delivery Gate

```bash
# 1. All 26 focused Phase 62 contract tests
python -m pytest tests/test_phase62_cache_gate.py tests/test_phase62_review_memory.py \
  tests/test_phase62_maintenance.py tests/test_phase62_handoff_diff.py \
  tests/test_phase62_attribution.py tests/test_phase62_api_staleness.py \
  tests/test_phase62_expiry.py tests/test_phase62_decision_schema.py -v

# 2. Regression: full Phase 61 suite still green
python -m pytest tests/test_phase61_*.py -q

# 3. Full suite — baseline (Phase 61's final count) + 26
python -m pytest tests/ -q

# 4. Lint/format
ruff check src/rush/token_economy/memory_cache_gate.py src/rush/memory/ src/rush/tools/api_diff.py \
  src/rush/tools/provenance_ai.py src/rush/continuity/ tests/test_phase62_*.py
ruff format --check src/rush/memory/ tests/test_phase62_*.py

# 5. Git hygiene
git diff --check
git status --short --branch
```

---

## 11. Exit Checklist

- [ ] Every RED task's test failed for the stated reason before its GREEN task began.
- [ ] Cache gate never mutates state (Invariant 1).
- [ ] Every maintenance cycle acquires and releases its lock, even on exception (Invariant 2).
- [ ] Handoff diffs send deltas only after a first full snapshot per tool (Invariant 3).
- [ ] Attribution links store a commit SHA, never full commit content (Invariant 4).
- [ ] API-diff staleness is independently checked from merkle staleness (Invariant 5).
- [ ] `stale` and `expired` are independent booleans, never conflated (Invariant 6).
- [ ] All 26 contract tests pass; full suite at Phase-61-baseline + 26.
- [ ] Zero third-party dependencies introduced.
- [ ] P62.9's real doc sweep run and every hit fixed (not the placeholder term-list in §8.2 — the actual post-implementation sweep).
- [ ] `docs/phase-plans/README.md` and `docs/developer/backlog.md` both have a Phase 62 row.
- [ ] The 16 unranked items from Phase 61's §3.2.4 remain explicitly unplanned — this phase does not silently claim to cover them.
