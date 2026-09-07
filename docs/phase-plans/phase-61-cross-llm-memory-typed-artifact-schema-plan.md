# Phase 61 Implementation Plan: Cross-LLM Memory Typed-Artifact Schema, Trust Tiers, and Transport Dispatcher

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 61 — the cross-LLM memory system redesign.
- **Planning Status:** Implementation-ready; verified against repo codebase via three parallel research passes (rush-source re-verification, full `/docs` tree audit, TDD/logging/CLI-wiring convention audit) plus direct verification of every file cited below in this same session — 17 of 17 modules/files cited in §2.2 were opened and re-read directly, none taken on the synthesis doc's earlier word.
- **Implementation Status:** Not started. Authorized for strict TDD execution once accepted.
- **Authority:** `docs/reports/cross-llm-memory-system-synthesis-2026-09-06.md` (the verified design — 7-subject component map, trust/governance layer, transport-tier decision, migration path, write-promotion rule, all independently adversarially reviewed and corrected within that document) and `docs/reports/cross-llm-memory-system-plan-2026-09-06.md` (the original research goal). This is a **roadmap phase**, not a remediation-finding phase — it does not close an `R-xxx` entry in `governance/remediation-contracts.toml` (that ledger's 16 findings are 100% closed, 16 of 16, as of Phase 60). It is authorized the same way Phases 41-50 were authorized: by an accepted design report, not a finding.
- **Predecessors:** Phase 55 (`rush.io.AtomicFile`, `rush.io.PhysicalRoot`, `rush.io.VerifierRecord`), Phase 56 (`rush.plugins.trust_store.PluginTrustStore`, user-owned ledger pattern), Phase 57 (`rush.contracts.operations` adapters, `InvocationContext`), Phase 58 (`rush.memory.transactions.CASMapTransaction` — the current, already-hardened versioned-JSON store this phase migrates off of), Phase 59 (`rush.tools.provenance_ai`), Phase 60 (maintainability baseline — this phase must not regress it).
- **Successor:** Phase 62+ (backlog) — the 35 enhancement ideas catalogued in the synthesis doc's "Enhancement ideas beyond the core 7-subject design" section are explicitly **not** in this phase's scope (see §3.2). This phase builds the foundation those ideas attach to.
- **Security Boundary:**
  1. New memory writes must never enter at trust tier `STATED` by default — only `EXTERNAL_WRITE`, `DERIVED`, or `IMPORTED` (per the synthesis doc's write-promotion rule, §76-78 of that doc).
  2. Every memory write is redacted via `rush.safety.redactor.sanitize_value` before it reaches disk, ahead of (not instead of) the write-time defense gate.
  3. Recall of any memory record scans for Trojan Source Unicode characters (`rush.hook.trojan_source.TrojanSourceDetector`) before the content re-enters an LLM context — closing the gap the synthesis doc identified (no evaluated repo does this).
  4. Promoted (`STATED`) records are signed (SHA-256, `HookTamperDetector` pattern) at promotion time and re-verified at recall; a signature mismatch is a fail-closed tamper signal, never silently ignored.
  5. Read/recall is ungated by `ExecutionPermissions` but scoped by a session allowlist (honcho pattern); write-as-authoritative is gated by the composed hindsight/zettelforge/mnemosyne defense, never by `ExecutionPermissions`.
- **Protected Boundaries:** `governance/remediation-contracts.toml` (all 16 of the ledger's 16 findings stay `completed` — 16/16, this phase adds no new finding rows), `pyproject.toml` dependency list (this phase adds zero third-party dependencies — see §8.3), `docs/adr/` (existing ADRs are never edited in place; superseding an ADR means writing a new one that references the old, per `docs/phase-plans/README.md`'s own guardrail).
- **Zero-Downscope Invariant:** This plan is the implementation contract. A task card's Binary Outcome must be met exactly; a RED task with a test that doesn't actually fail for the stated reason, or a GREEN task that special-cases the test instead of implementing the invariant, does not satisfy the task.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, or release without explicit user instruction, per every other phase plan in this directory.

---

## 2. Authority, Predecessor Artifacts, and Concrete Evidence

Authority order: User instructions → `AGENTS.md` → `docs/reports/cross-llm-memory-system-synthesis-2026-09-06.md` → Phases 55-60 contracts → current memory/continuity/patch/plugin source and test suites.

### 2.1 Concrete Codebase Audit & Semantic Drift Identification

A fresh, direct re-read of every file this phase touches — 17 files/modules, the full list is §2.2, coverage 17 of 17, none reused from the synthesis doc's earlier passes without re-opening it this session — found five drifts between the synthesis doc's assumptions and the current, post-Phase-60 codebase:

1. **Drift 1: `transactions.py` is already CAS-versioned, not primitive flat JSON.** The synthesis doc's Migration Path (line 68) describes `transactions.py` as "CAS-JSON files" to move off of, in a tone that implies primitive unversioned files. Phase 58 (completed, predates this plan) already hardened it: `src/rush/memory/transactions.py` (215 lines) implements `CASMapTransaction` — optimistic-concurrency reads/writes via `rush.io.AtomicFile`, `VersionedSnapshot[T]` (version + data + content_hash), and five typed exceptions (`StoreNotFoundError`, `StoreCorruptionError`, `StoreValidationError`, `StoreIOError`, `CASConflictError`). **What this phase actually replaces** is not "primitive JSON files" — it's this already-hardened but still per-store, still-JSON-file, still-no-SQL-query-surface mechanism. `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` all currently persist through it, one JSON file per store, no cross-store query, no WAL, no relational schema. This phase's `TypedArtifactStore` (§6.1) supersedes `CASMapTransaction`-backed per-store files with one SQLite WAL database.
2. **Drift 2: `session_memory.py` is not under `src/rush/memory/`.** It lives at `src/rush/session_memory.py`, one level up from the other six memory-subsystem files. `src/rush/memory/` contains exactly seven files: `checkpoint_journal.py`, `failure_ledger.py`, `invariant_graph.py`, `merkle_invalidator.py`, `mistake_miner.py`, `preference_store.py`, `transactions.py`. No `engine.py` exists anywhere under `src/rush/memory/`.
3. **Drift 3: No SQLite WAL precedent exists anywhere in this codebase.** `journal_mode` appears zero times across `failure_ledger.py`, `token_economy/ccr_store.py`, `patch/memory.py`, `hook/tamper_detector.py`, and `memory/transactions.py` — 5 of 5 checked files, zero hits in every one. This phase's `TypedArtifactStore` is the first WAL-mode SQLite connection in the codebase — `PRAGMA journal_mode=WAL` must be set explicitly, with no existing pattern to copy from.
4. **Drift 4: ADR-0030 is `Accepted` but describes a different, never-built design.** `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` (Status: Accepted, v0.2.0/Phase 41A-41B) commits to: a 4-tier taxonomy of **Working, Policy, World, Skills** (not this phase's `STATED`/`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` trust tiers — a completely different axis, subject-taxonomy vs. trust-taxonomy), an `src/rush/memory/engine.py` (confirmed not present — Drift 2), a `.rush/memory.db`, SQLite FTS5/BM25 lexical search, an `events.jsonl` audit stream, and `<rush_context_memory>` XML prompt compilation. None of ADR-0030's specific claimed components exist in the current codebase — 0 of the 5 named deliverables (engine.py, memory.db, FTS5/BM25 search, events.jsonl, XML compiler) were found. This phase's design is not an extension of ADR-0030 — it conflicts with ADR-0030's stated (unbuilt) taxonomy on the trust axis and only partially overlaps on the storage axis (both want SQLite; the schema and taxonomy differ). **This phase must supersede ADR-0030 with a new ADR, not silently ignore it** (§9, task P61.11).
5. **Drift 5: the mesh lock manager the synthesis doc cites as `continuity/coordination.py`'s is actually implemented in `src/rush/mcp_mesh/lock_manager.py` (`MeshLockManager`), only imported and used by `continuity/coordination.py`.** Both `src/rush/continuity/` and `src/rush/mcp_mesh/` exist as separate packages; `continuity/coordination.py` is a consumer of `mcp_mesh`'s lock manager (and also directly imports `FailureLedger` and `rush.tools.flight_recorder.FlightRecorder`, calling `.replay_session()` — real existing precedent for continuity code reading memory-subsystem data). Any task card below that touches "the mesh lock manager" targets `src/rush/mcp_mesh/lock_manager.py`, not a file under `continuity/`.

### 2.2 Verified Current API Surfaces (cited exactly, re-read this session — 17 of 17 files below opened directly, coverage complete for this list)

- `src/rush/memory/failure_ledger.py`: table `failure_ledgers` — `fingerprint TEXT PRIMARY KEY, error_message TEXT NOT NULL, failed_patch TEXT NOT NULL, created_at INTEGER NOT NULL`. Real SQLite (not WAL), real concurrent-safe usage via stdlib `sqlite3`.
- `src/rush/memory/mistake_miner.py`: `mine_mistakes()` parses `git log --grep=Revert` — a git-log miner, not a store.
- `src/rush/memory/checkpoint_journal.py`: `save_checkpoint`/`restore_checkpoint`/`list_checkpoints`, `AtomicFile`-backed, explicit schema version `"1.0.0"`, corrupt entries retained with a SHA-256 digest and `status="corrupt"` (Phase 58 hardening).
- `src/rush/patch/memory.py`: `PatchMemoryStore`, SQLite table `patch_memory` — `error_signature TEXT PRIMARY KEY, target_file TEXT NOT NULL, diff_patch TEXT NOT NULL, created_at REAL NOT NULL, success_count INTEGER DEFAULT 1`, DB at `.rush/cache.db`. Redacts via `SecretRedactor.redact_text` before write.
- `src/rush/patch/promoter.py`: `PatchPromoter.promote_sandbox_diff` refuses `review_class in ("policy-changing", "privileged")`.
- `src/rush/plugins/trust_store.py`: `PluginTrustStore`, ledger at `~/.rush/plugin_trust_ledger.json`, `grant_trust()` (line 253) records a SHA-256 closure digest via `AtomicFile`.
- `src/rush/plugins/skills_generator.py`: `AgentSkillGenerator.generate_skill_markdown()` (lines 8-30), emits a SKILL.md pointing at `rush plugin run <name>`.
- `src/rush/safety/redactor.py`: `sanitize_value()` (recursive, fail-closed, handles circular refs, deterministic key-collision suffixing) and `SecretRedactor.redact_text()`.
- `src/rush/score/consensus.py`: `MultiModelConsensusReconciler(min_agreement_ratio=0.5)`, `reconcile_findings(all_findings, total_models)` groups by `(file_path, line_number, rule_id)`.
- `src/rush/tools/flight_recorder.py`: `FlightRecorder`, JSONL events at `.rush/sessions/flights/<session_id>.jsonl`, `record_event()` sanitizes via `sanitize_value` before write, `replay_session()`.
- `src/rush/hook/trojan_source.py`: `TrojanSourceDetector.inspect_file(file_path: Path) -> list[str]`, static method, scans line-by-line for `BIDI_CHARS`.
- `src/rush/hook/tamper_detector.py`: `HookTamperDetector`, `record_signatures()`/`verify_signatures()`, SHA-256 over git hook file bytes, signatures at `.rush/hook_signatures.json`.
- `src/rush/governance/public_operations.py`: `OperationKind` enum, `PublicOperation` dataclass (`effect_class: str`, `safe_probe: str`), `build_operations_inventory()`.
- `src/rush/tools/continuity.py`: `SessionContinuityTool(ToolFn)` (line 71), `name = "continuity"`, `__call__(self, path, operation="list", name=None, files=None, allow_cache_write=False, allow_network=False, current_goal=None, open_work=None, historic_instruction=None, failure_fingerprint=None, dependencies=None, context_path=None, target_symbol="", token_budget=4000, context_handle=None, coordination_path=None, agent_id=None, ...)`, `SessionOperation` Literal: `save/list/restore/context_pack/context_retrieve/coordination_check/coordination_merge_preview/coordination_recovery/provider_resume`.
- `src/rush/mcp_support/tool_registry.py`: `make_tool_wrapper(tool, executor)` (line 15) — wraps a `ToolFn` into an **MCP-only** handler; `register_all_tools()` (same file, line ~70) calls it once per tool in `ALL_TOOLS` and registers the result on the FastMCP server as `rush_<tool.name>` via `server.add_tool()`. **`make_tool_wrapper` produces no CLI surface at all — corrected from an earlier draft of this plan that claimed it did.** The real dual-registration path, verified against `SessionContinuityTool` (`src/rush/tools/continuity.py:71`): (1) the tool instance is added to `ALL_TOOLS` in `src/rush/tools/__init__.py` — `src/rush/mcp.py:327` calls `register_all_tools(server, executor, ALL_TOOLS)` for the MCP side; `src/rush/cli.py:1200-1209` loops `ALL_TOOLS` and calls `cli.add_command(build_catalog_path_command(_catalog_tool))` for every tool name **not** in the hardcoded exclusion set `{"review","format","commit-msg","sbom","fix","benchmark"}` for the CLI side; (2) `build_catalog_path_command` (`cli_support/catalog_commands.py:66`) requires a matching `TOOL_SPECS` entry keyed by `tool.name` (`catalog.py:115`, e.g. the `"continuity"` entry) — it KeyErrors without one, and only produces a generic `PATH [--json]` command; (3) that generic command doesn't fit a multi-operation tool. `SessionContinuityTool` proves this: its real CLI surface is a bespoke `@cli.group(name="session")` (`cli.py:1878`) with hand-written subcommands (`session_save_cmd`/`session_list_cmd`/`session_restore_cmd`, `cli.py:1934-2009`), not the generic catalog command. `MemoryTool`'s planned `ask`/`write`/`promote`/`list`/`recall` operations (§3.1 goal 6) are the same shape, so it needs the same two-part treatment.
- `src/rush/contracts/results.py`: `ToolResultV1` — `schema_version: Literal["1.0.0"]`, `tool`, `engine`, `engine_version`, `status: Literal["ok","warn","fail","error","skipped"]`, `duration_ms`, `summary`, `findings: list[FindingV1]`, `raw`, `extensions`. `ValidationErrorV1(code, message, path, invalid_value)` — frozen dataclass exception, has `.to_dict()`.
- `src/rush/logging.py`: `NdjsonHandler(logging.Handler)` — one redacted JSON object per line to **stderr only** (module docstring: stdout is reserved for MCP JSON-RPC frames, never write there). `setup_logging(level=None)` reads `RUSH_LOG_LEVEL` env (default `"warn"`), attaches under logger `"rush"`, `propagate=False`, idempotent. `get_logger(name)` returns a child logger, e.g. `get_logger("memory.store")` → `"rush.memory.store"`. Every record passes through `SecretRedactor.redact_text` before emission; a broad `except Exception` falls back to `"[LOGGING_FALLBACK: formatting failed]"` — logging itself never raises. `session_memory.py` additionally calls a `log_subsystem(subsystem, level, message)` helper defined in this same module — grep `def log_subsystem` in `src/rush/logging.py` before first use in P61.1 to confirm its exact signature (not fully captured during research; do not guess it).
- **No coverage gate exists.** `pyproject.toml` has zero `coverage`/`fail-under`/`pytest-cov` configuration, no `.coveragerc`. Test completeness in this plan is enforced by the RED-before-GREEN task-pair convention (a red task's test must fail before the green task's implementation, pass after) — not by a coverage percentage. Do not add one; it would be new tooling this phase doesn't need and isn't authorized to add (§8.3).

### 2.3 Root-Level vs. Nested `/docs` Duplication (pre-existing, not created by this phase, must be worked around)

A full grep sweep of all 353 `.md` files under `docs/` (parallel research pass, this session; coverage detailed in §8.2) found a **pre-existing, unresolved duplication**: root-level ALLCAPS docs (`docs/ARCHITECTURE.md`, `docs/SAFETY.md`, `docs/SECURITY.md`, `docs/CLI_REFERENCE.md`, `docs/PRIVACY.md`, `docs/MCP_REFERENCE.md`, and others) coexist with lowercase nested equivalents (`docs/developer/architecture.md`, `docs/safety/safety-overview.md`, `docs/safety/security-model.md`, `docs/reference/cli-reference.md`) that `docs/README.md` treats as canonical. Both files in each pair are real, independently-sized (not symlinks — confirmed via `ls -la`), and both currently carry the same stale boilerplate (§2.4). `scripts/update_phase_docs.py` (the real, current doc-sync script — see §8.2) updates a mix of both conventions in its own fixed file list, meaning current tooling already treats both as live. **This phase does not resolve the duplication** (out of scope — it predates this phase and affects far more than the memory subsystem) but **updates both copies of every affected pair**, never just one, so this phase does not make the drift worse.

### 2.4 Systemic Pre-Existing Drift This Phase Must Fix: the 41-File Boilerplate Block

An identical boilerplate paragraph — beginning `"3. **Atomic Checkpoint Journals & Corrupt Evidence (`rush.memory.checkpoint_journal`)**:"` — is copy-pasted verbatim into 41 files across `/docs` (full enumerated list in §8.2, Group D — 41 of 41 affected files listed there, no sample). This number was wrong twice before landing here: the original research pass reported "34" in its own prose summary while its own enumerated list already had 40 names; this document then propagated "34" unverified. A follow-up review re-ran the actual grep against live `docs/` and found 41 real hits, including `docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md`, which neither the "34" nor the "40" version of this list ever included.. It describes `checkpoint_journal.py` in its pre-this-phase shape. Since `checkpoint_journal.py`'s records become `Handoff`-family rows in the unified schema (§6.1, §9 P61.4), this one paragraph needs one corrected replacement text, applied identically to all 41 files — a single authored replacement, not 41 independent rewrites.

---

## 3. Goals, Non-Goals, and Operational Exclusions

### 3.1 Primary Goals

1. Implement a unified SQLite WAL typed-artifact store (`src/rush/memory/store.py`) covering all 7 memory subjects (active-context, episodic/session, preference, failure/mistake, architectural-decision, domain/project-knowledge, skill/pattern), absorbing `CASMapTransaction`-backed `preference_store.py`/`invariant_graph.py`/`merkle_invalidator.py`, `checkpoint_journal.py`, `failure_ledger.py`'s schema, `patch/memory.py`'s `PatchMemoryStore` (`.rush/cache.db`), `flight_recorder.py`'s JSONL (`.rush/sessions/flights/`), and `hook/tamper_detector.py`'s signature file (`.rush/hook_signatures.json`) — every one of these 8 sources migrates its content into the one database; none remain as separate satellite files afterward.
2. Implement the 4-tier trust taxonomy (`STATED`/`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED`) and the write-promotion rule exactly as specified in the synthesis doc (§76-78): new writes never enter at `STATED`; promotion requires passing a composed ALLOW/REDACT/BLOCK screen + regex pre-filter + full-schema-populated check, and either direct user statement or corroboration ≥ 2 via new, dedicated corroboration-counting code in `trust.py` (not a reuse of `MultiModelConsensusReconciler` — its grouping key is hardcoded and can't represent an Optional `symbol_ref`, see §6.2 correction).
3. Implement recall-time defense: Trojan Source scanning on every recalled record before it re-enters an LLM context, and a session-scoped read allowlist (fails closed on empty input).
4. Implement tamper-evidence on `STATED` records: SHA-256 signature at promotion, re-verified at recall, using the exact record/verify shape already proven in `HookTamperDetector`.
5. Implement the per-tool transport dispatcher (native SDK → ACP → dedicated-file fallback, per-tool tier lookup, not a single blanket protocol) replacing rush's current hardcoded provider dict.
6. Implement one query/write interface (`MemoryTool`, a `ToolFn`) exposing `ask`/`write`/`promote`/`list`/`recall` operations, registered as both a CLI command and an MCP tool (`rush_memory`) via the same two-part path `SessionContinuityTool` uses — `ALL_TOOLS`/`register_all_tools()` for MCP, `TOOL_SPECS` + a bespoke `@cli.group` for CLI (§2.1 correction) — no reuse of hindsight/mem0/zettelforge/etc. source, idea-only per the synthesis doc's methodology.
7. Supersede ADR-0030 with a new ADR describing the actually-built design.
8. Synchronize every `/docs` file this phase's audit identified as stale — 71 of 351 audited files (§8.2 Groups A-D, fully resolved coverage statement, 2 authority docs excluded from the 353 raw count); the remaining 280 (§8.2 Group F) confirmed to need no change.

### 3.2 Non-Goals and Operational Exclusions

1. **No new third-party dependencies.** Pure Python 3.12 standard library `sqlite3`, `hashlib`, `json`, `re`, `dataclasses`, `pathlib`, `time`, `uuid` — matching every predecessor phase's dependency discipline.
2. **The synthesis doc's 35 enhancement-idea bullets are individually triaged below, not bucketed as one undifferentiated deferral.** 9 of the 35 are already inside this phase's scope (§3.2.1); 2 more are data-integrity gaps this phase should close before it ships (§3.2.2 — folded into P61.2, not deferred); 8 more are genuinely Phase 62+ candidates grouped by an objective criterion — they build directly on this phase's own primitives (§3.2.3); the remaining 16 are Phase 62+ candidates with no priority ranking assigned (§3.2.4 — ranking is a product call, not this session's to make). None of this is authorized as a Phase 62 plan — no such plan exists yet — this is an unranked backlog for the next planning pass, not a claim that Phase 62 is scheduled or tracked as a real artifact.

#### 3.2.1 Already implemented by this phase's own task cards (9 of 35) — not deferred
1. Code-anchored memory / merkle staleness anchoring → §6.3 Invariant 6.
2. `rush memory ask` query interface → P61.12, `MemoryTool`'s `ask` operation.
3. Corroboration-threshold counting is new dedicated code, not a reuse of `MultiModelConsensusReconciler` → P61.2, T-61.13 (see §6.2 correction).
4. Episodic/session substrate (`FlightRecorder`) → P61.5.
5. Recall-time Trojan Source injection scanning → §6.3 Invariant 4.
6. Paired fix-store for failure records (`PatchMemoryStore` linkage) → P61.3, T-61.19.
7. Skill/pattern execution path via `PluginTrustStore` → P61.8.
8. Redact-first writes ahead of the external defense gates → §6.3 Invariant 2.
9. Tamper-evident signing on promotion (`HookTamperDetector` pattern) → §6.3 Invariant 3.

#### 3.2.2 Data-integrity gaps this phase should close, not defer (2 of 35)
These are being folded into P61.2's promotion gate (§6.2) rather than left for Phase 62, because they're integrity gaps in this phase's own write-promotion rule, not separable extensions:
1. **Grounding-check before promotion** (catches a fabricated file/symbol citation at write time) — add as a fifth check in `evaluate_promotion()` alongside the ALLOW/REDACT/BLOCK screen, regex pre-filter, schema-completeness check, and corroboration threshold. **Correction:** originally described as reusing `GroundingVerifier` (`src/rush/codegraph/grounding_verifier.py`) — verified this session that class only exposes `verify_code(code: str)`, which checks whether a code snippet's *imports* resolve to stdlib/installed packages. It has no method for resolving a `"path/to/file.py::Symbol"`-shaped `symbol_ref` string to a real file+symbol. This is new, simple code (P61.2.2), not a reuse: split `symbol_ref` on `::`, confirm the file path exists, `ast.parse` it, and confirm the symbol name appears as a top-level `def`/`class`.
2. **Conflict resolution for a new fact contradicting an already-`STATED` record** (mem0-style ADD/UPDATE/DELETE/NONE reconciliation) — the current rule (§6.2) only gates entry of new records; it says nothing about what happens when a later-derived fact conflicts with a promoted one. Add an `evaluate_conflict(new_artifact, existing_stated_artifact) -> Literal["add","update","delete","none"]` function to `trust.py`, wired into `write()` before insert when a matching `(subject, symbol_ref)` `STATED` row already exists.

(These 2 items add scope to P61.2's task cards. Resolved: T-61.35/T-61.36 are in §7's contract test table and P61.2.1/P61.2.2's Actions wire both — see those sections.)

#### 3.2.3 Real Phase 62 candidates — builds directly on this phase's primitives (8 of 35)
Token-savings cache layer (`token_economy/` front-end), review/development actually reading memory before reporting, a maintenance sub-agent using `mcp_mesh`'s lock manager, handoff diffs instead of full blobs, an AI-attribution trail linking commits to decision/failure records, API-diff public-signature staleness (refines Invariant 6's merkle-only staleness check), a per-type expiry/TTL policy (no expiry mechanism exists in this phase's schema), and reusing `remediation-contracts.toml`'s schema shape for architectural-decision/failure records.

#### 3.2.4 Remaining Phase 62+ candidates, not ranked (16 of 35)
Per-tool skill/hook bundles, SLSA provenance signing on memory records, governance-drift detection against ADR sync, memory-driven regression-test suggestions, `BlastRadiusAnalyzer` risk-tagging, `rush trace`'s decision-memory column, provenance/fix-survival correlation, a human-reviewable write-approval diff, a memory-recall benchmark harness, KV-cache-resident memory (the specific unlock for the domain-knowledge embedding upgrade §3.1 Non-Goals item 4 defers), an event-driven (L1→L2→L3) promotion ladder, a Rust-native embedding backend, git-native team memory, decay-and-fuse forgetting, governance `effect_class`/`safe_probe` reuse for write classification, per-operation-type handler dispatch. **Deliberately unranked** — relative priority among these 16 is a product decision, not something this session verified against source; a prior draft of this section assigned "lower priority" / "questionable" labels to a 12/4 split without asking, which was itself the same unilateral-descoping failure this plan already got corrected for once (§3.1 item 2's own history). Ranking, if wanted, is the user's call.
3. **No resolution of the root-level-vs-nested `/docs` duplication** (§2.3) — pre-existing, out of scope, worked around by updating both copies.
4. **No embedding-model dependency for domain/project-knowledge retrieval.** The synthesis doc's domain-knowledge citation (`agentic-box/memora`) is idea-only (no literal source copied, per the doc's own license-handling methodology) and rush's minimal-deps stance rules out adding an embedding library in this phase. Domain/project-knowledge retrieval in this phase is SQLite FTS5 lexical search only; hybrid embedding retrieval (if ever wanted) is a Phase 62+ item, consistent with the synthesis doc's third-pass finding that a no-heavy-deps embedding backend (`StarlightSearch/EmbedAnything`) exists as prior art but adopting it is not part of this phase's scope.
5. **No live network calls, no live provider credentials.** Transport-dispatcher tests use local fixtures/mocks for SDK/ACP presence detection, never real API calls.
6. **No resolution of the ADR-0018/ADR-0020/ADR-0041 content** beyond adding a "Superseded by ADR-0049" pointer note to each (§8.2) — their historical record stays intact, per `docs/phase-plans/README.md`'s guardrail against editing ADRs' substance.

---

## 4. Admission Gate and Predecessor Verification

Verify before starting P61.0:

1. `governance/remediation-contracts.toml` shows all 16 of its 16 findings with `status = "completed"` (16/16).
2. `docs/phase-plans/README.md`'s index table shows Phase 60 as the last completed phase (confirms this plan's "Phase 61" numbering is the next free slot — verify no `docs/phase-plans/phase-61-*.md` file already exists before creating one).
3. `src/rush/memory/transactions.py` exists and exports `CASMapTransaction`, `VersionedSnapshot`, and the five typed store exceptions (§2.1 Drift 1) — this phase's migration tasks (P61.3) read from these exact classes.
4. `src/rush/mcp_mesh/lock_manager.py` exists and exports `MeshLockManager` (§2.1 Drift 5).
5. `src/rush/tools/continuity.py:71`'s `SessionContinuityTool` exists and is importable, confirmed to use the real two-part CLI+MCP registration path (`ALL_TOOLS`/`register_all_tools()` for MCP; `TOOL_SPECS` + a bespoke `@cli.group` for CLI — `make_tool_wrapper` alone is MCP-only, §2.1 correction) — this phase's `MemoryTool` (P61.12) is registered the same two-part way.
6. Run `python -m pytest tests/ -q` and record the exact baseline passing-test count in `docs/phase-plans/phase-61-implementation-evidence.md` (this phase creates that evidence file at P61.0.1 — do not guess the baseline number from an earlier phase's plan; re-run it).

---

## 5. Subject-Ownership Ledger (7 Memory Subjects + Governance + Transport)

| Subject / Concern | Primary Design Source (synthesis doc) | Workstream | Current Code It Migrates |
|---|---|---|---|
| Active context | `oceanbase/powercontext`'s `Handoff` shape (idea only) | P61.4 | `continuity/receipts.py` (`save_receipt`/`restore_receipt`), `memory/checkpoint_journal.py` |
| Episodic/session | `CodeAbra/iai-personal-memory-engine` (idea only) + `FlightRecorder` (real, in-repo) | P61.5 | `session_memory.py`, `tools/flight_recorder.py` |
| Preference | `akitaonrails/ai-memory` (idea only) | P61.3 (migration only — Migration Path specifies `preference_store.py` becomes a filtered view, no new forward-write behavior) | `memory/preference_store.py` |
| Failure/mistake | `riponcm/projectmem` (idea only) + `PatchMemoryStore` (real, in-repo) | P61.6 | `memory/failure_ledger.py`, `memory/mistake_miner.py`, `patch/memory.py` |
| Architectural-decision | `riponcm/projectmem` (idea only) | P61.3 (migration only — Migration Path specifies `invariant_graph.py` becomes tagged `Experience` records, no new forward-write behavior) | `memory/invariant_graph.py` |
| Domain/project knowledge | `agentic-box/memora` (idea only, lexical-only in this phase — §3.2 item 4) | P61.7 | none (new) |
| Skill/pattern | `zilliztech/memsearch` (idea only) + `PluginTrustStore`/`AgentSkillGenerator` (real, in-repo) | P61.8 | none (new; execution path reuses `plugins/trust_store.py` + `plugins/skills_generator.py`) |
| Trust/governance layer | hindsight + zettelforge + mnemosyne + honcho + agentmemory (all idea only) | P61.2, P61.9 | `continuity/receipts.py`'s binary `"quarantined"` flag |
| Cross-tool transport | native SDK / ACP / dedicated-file tiers (verified real: `claude-agent-sdk`, `codex app-server`, `agent-client-protocol`) | P61.10 | rush's current hardcoded provider dict (exact file TBD at P61.10.1 RED — grep for it, do not assume a path) |
| Unified storage engine | this phase's own design (§6.1), informed by `failure_ledger.py`'s real SQLite pattern | P61.1 | `memory/transactions.py`'s `CASMapTransaction` (superseded) |

---

## 6. Shared Architecture, State Invariants, and Data Structures

### 6.1 Unified Typed-Artifact Schema (`src/rush/memory/store.py`)

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MemoryFamily = Literal["handoff", "experience", "memory", "skill"]
MemorySubject = Literal[
    "active_context", "episodic", "preference", "failure",
    "architectural_decision", "domain_knowledge", "skill_pattern",
]
TrustTier = Literal["STATED", "DERIVED", "EXTERNAL_WRITE", "IMPORTED"]

@dataclass(frozen=True)
class MemoryArtifact:
    """One row of the unified typed-artifact schema."""
    id: str                        # uuid4 hex
    family: MemoryFamily           # powercontext's 4-family shape: which container kind
    subject: MemorySubject         # the 7-subject tag (rush's own taxonomy, not powercontext's)
    trust_tier: TrustTier
    content: dict[str, Any]        # redacted via sanitize_value before this dataclass is constructed
    source: str                    # tool/session id that wrote it
    created_at: float
    symbol_ref: str | None = None  # optional "path/to/file.py::Symbol" anchor
    content_hash: str | None = None  # merkle AST hash of symbol_ref at write time
    corroboration_count: int = 0
    promoted_at: float | None = None
    stale: bool = False
    signature: str | None = None   # SHA-256, set only at promotion to STATED
```

`SQL schema` (executed by `TypedArtifactStore._init_db()`):

```sql
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS memory_artifacts (
    id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    subject TEXT NOT NULL,
    trust_tier TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    symbol_ref TEXT,
    content_hash TEXT,
    corroboration_count INTEGER NOT NULL DEFAULT 0,
    promoted_at REAL,
    stale INTEGER NOT NULL DEFAULT 0,
    signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_subject ON memory_artifacts(subject);
CREATE INDEX IF NOT EXISTS idx_memory_trust ON memory_artifacts(trust_tier);
CREATE INDEX IF NOT EXISTS idx_memory_symbol ON memory_artifacts(symbol_ref);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, content='memory_artifacts', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS memory_artifacts_ai AFTER INSERT ON memory_artifacts BEGIN
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_ad AFTER DELETE ON memory_artifacts BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS memory_artifacts_au AFTER UPDATE ON memory_artifacts BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
    INSERT INTO memory_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

These three triggers are the only synchronization mechanism for `memory_fts` — no repo precedent exists to follow (grepped `fts5`/`CREATE VIRTUAL TABLE`/`content_rowid` across all of `src/rush/`: zero hits outside this plan, confirmed 2026-09-07), so `write()`/`recall()` in `store.py` never call an explicit re-index function; every `INSERT`/`UPDATE`/`DELETE` against `memory_artifacts` is kept in sync by SQLite itself, using the delete-then-reinsert idiom FTS5 external-content tables require on `UPDATE` (a bare content-column update does not update the shadow index on its own).

Database path: `.rush/memory.db` (matches ADR-0030's already-accepted path choice — the one part of ADR-0030 this phase keeps; everything else in ADR-0030 is superseded, §9 P61.11).

### 6.2 Trust Tier & Write-Promotion Rule (`src/rush/memory/trust.py`)

```python
from dataclasses import dataclass
from typing import Literal

PromotionDenialReason = Literal[
    "failed_allow_redact_block_screen",
    "failed_regex_prefilter",
    "incomplete_schema_fields",
    "insufficient_corroboration",
]

@dataclass(frozen=True)
class PromotionResult:
    promoted: bool
    new_tier: TrustTier
    denial_reason: PromotionDenialReason | None = None
    corroboration_count: int = 0
```

`default_entry_tier(source_kind: Literal["local_tool", "cross_tool_handoff", "human_derived"]) -> TrustTier` — maps `"cross_tool_handoff"` → `IMPORTED`, `"local_tool"`/`"human_derived"` (not directly user-stated) → `EXTERNAL_WRITE` or `DERIVED` per the synthesis doc's rule; never returns `STATED`.

`evaluate_promotion(artifact: MemoryArtifact, *, user_stated: bool) -> PromotionResult` composes, in order: (a) an ALLOW/REDACT/BLOCK screen (new, rush-own implementation of the hindsight pattern — no hindsight code is copied, per the synthesis doc's methodology), (b) a deterministic regex pre-filter against instruction-override/exfiltration patterns (zettelforge pattern, rush-own implementation), (c) a full-schema-populated check (every non-optional `MemoryArtifact` field set), (d) either `user_stated is True` (promotes immediately) or `corroboration_count >= 2` via new, dedicated corroboration-counting code in `trust.py` — **not** a reuse of `rush.score.consensus.MultiModelConsensusReconciler`: that class's `reconcile_findings()` hardcodes its grouping key inline as `(f.file_path, f.line_number, f.rule_id)` (`src/rush/score/consensus.py`, no grouping parameter exists), and `ModelFinding.rule_id: str` is non-optional while `MemoryArtifact.symbol_ref` is `str | None` (many subjects — `preference`, `active_context` — have no code anchor at all, §6.1), so there's no type-safe, non-hacky mapping from `(subject, symbol_ref)` onto `(file_path, line_number, rule_id)`. P61.2.2's Allowed Writes (§8.1) also exclude `src/rush/score/consensus.py`, so its grouping logic can't be changed either. `count_corroboration(subject: MemorySubject, symbol_ref: str | None, candidate_sources: list[str]) -> int` in `trust.py` is new, dedicated code: groups pending (non-`STATED`) artifacts by `(subject, symbol_ref)`, counts distinct `source` values, returns the count for comparison against the `>= 2` threshold.

### 6.3 State Invariants

1. **No-STATED-on-entry invariant:** `default_entry_tier` never returns `"STATED"`. `TypedArtifactStore.write()` refuses a caller-supplied `trust_tier="STATED"` on initial insert — promotion is the only path to `STATED`, always through `evaluate_promotion`.
2. **Redact-before-store invariant:** every `content` dict passed to `TypedArtifactStore.write()` is run through `sanitize_value()` inside `write()` itself, not left to the caller — a caller cannot bypass redaction by forgetting to call it.
3. **Signature invariant:** `promoted_at is not None` implies `signature is not None`; a record cannot be `STATED` without a signature, and `recall()` must re-verify `hashlib.sha256(content_bytes).hexdigest() == signature` for every `STATED` row it returns, raising (not silently ignoring) on mismatch.
4. **Recall-scan invariant:** `recall()` runs `TrojanSourceDetector`-equivalent scanning (adapted from `inspect_file` to operate on an in-memory string, since recalled content isn't a file — a new `inspect_text(text: str) -> list[str]` variant, not a re-implementation of the character set) on every returned record's `content` before returning it to the caller.
5. **Absorbed-not-satellite invariant:** after P61.3 completes, `.rush/sessions/flights/*.jsonl` (`FlightRecorder`) and `.rush/hook_signatures.json` (`HookTamperDetector`) no longer hold the canonical copy of their data — `TypedArtifactStore` does. `PatchMemoryStore`'s `patch_memory` table rows (previously in `.rush/cache.db`) are migrated into `TypedArtifactStore` (`subject="failure"`) the same way, but the physical `.rush/cache.db` file itself is never renamed, moved, or deleted — it stays live and in place, because `ResultCache` (`src/rush/cache.py:94-99`, instantiated with no `db_path` override at `src/rush/cli.py:581,591`) shares that exact file for its own, unrelated tool-result cache table (`cache_entries`) and has no part in this migration. Renaming `.rush/cache.db` would silently orphan `ResultCache`'s live cache — a fresh empty `.rush/cache.db` gets auto-created by `ResultCache._init_db()` on the next tool run, discarding every prior cache entry with no error. **Decided, not left to task-time discretion: `.rush/sessions/flights/*.jsonl` and `.rush/hook_signatures.json` are retained read-only (renamed with a `.migrated` suffix, e.g. `.rush/hook_signatures.json.migrated`), never deleted, by default. `.rush/cache.db` is excluded from this rename — only its `patch_memory` table's data moves, the file itself stays untouched.** Deletion of the migrated JSONL/JSON files is a separate, explicitly-opt-in cleanup a human runs later — this phase's own migration task never deletes data it just moved, given the blast radius of a migration bug on data that includes tamper-detection signatures. This removes the ambiguity the earlier draft of this invariant left open.
6. **Staleness invariant:** a `symbol_ref`+`content_hash` pair is checked against the current AST content-hash of that symbol on every recall, using the exact same hashing computation as `merkle_invalidator.py`'s `MerkleInvalidator.hash_content()` (`src/rush/memory/merkle_invalidator.py:35-36` — `hashlib.sha256(content.encode("utf-8")).hexdigest()`, a pure, stateless computation with no I/O). `recall()` reuses only this pure hash computation (inline it or call `MerkleInvalidator.hash_content()` directly — never `MerkleInvalidator.check_and_update()` or any other method that touches `self.tx`/`CASMapTransaction`/`.rush/cache/merkle.json`). This is a hard boundary, not a style preference: once P61.3 turns `merkle_invalidator.py` into a thin compatibility view over `TypedArtifactStore` (§8.1 Modified Files 1), `check_and_update()`'s storage will itself route through `TypedArtifactStore` — and `store.py` is not in P61.3.2's Allowed Writes, so `recall()`'s implementation is fixed before that migration runs and cannot be revisited. If `recall()` ever called into `check_and_update()` (directly or transitively), that would create a real circular dependency: `TypedArtifactStore.recall()` calling into a class whose own state, post-P61.3, lives in the store `recall()` is trying to read. Because `content_hash` is already stored on the `memory_artifacts` row itself (§6.1), `recall()` needs nothing from `MerkleInvalidator` beyond the hash algorithm — a mismatch between the row's stored `content_hash` and the freshly-computed hash of the current symbol content sets `stale=True` on that row before returning it, and the caller is told `stale: true` in the result — never silently served as fresh.
7. **FTS-sync invariant:** `memory_fts` is kept current solely by the three `AFTER INSERT`/`AFTER UPDATE`/`AFTER DELETE` triggers on `memory_artifacts` defined in `_init_db()`'s DDL (§6.1) — `write()` never calls a manual FTS re-index function, and never bypasses `INSERT`/`UPDATE`/`DELETE` on `memory_artifacts` in a way that would skip the triggers.

---

## 7. Contract Test Inventory (T-61.01 through T-61.36)

| Test ID | Test File | Test Function | Target Contract & Non-Permissive Assertion |
|---|---|---|---|
| T-61.01 | `tests/test_phase61_store.py` | `test_wal_mode_enabled_on_init` | Asserts `PRAGMA journal_mode` returns `"wal"` after `TypedArtifactStore.__init__`. |
| T-61.02 | `tests/test_phase61_store.py` | `test_write_rejects_stated_on_initial_insert` | Asserts `write(..., trust_tier="STATED")` raises on a record with no prior row — promotion is the only path to STATED. |
| T-61.03 | `tests/test_phase61_store.py` | `test_write_redacts_content_before_persisting` | Writes content containing a fake API key pattern; asserts the persisted row's `content` has it replaced, never the raw secret. |
| T-61.04 | `tests/test_phase61_store.py` | `test_recall_rescans_stated_signature_and_raises_on_mismatch` | Promotes a record, corrupts its stored `signature`, asserts `recall()` raises rather than returning tampered content silently. |
| T-61.05 | `tests/test_phase61_store.py` | `test_recall_scans_content_for_trojan_source_chars` | Writes a record whose content contains a `BIDI_CHARS` character; asserts `recall()` flags it (does not silently pass it through). |
| T-61.06 | `tests/test_phase61_store.py` | `test_staleness_flips_on_symbol_content_hash_mismatch` | Writes a record anchored to a real file symbol, mutates the file, asserts the next `recall()` returns `stale=True`. |
| T-61.07 | `tests/test_phase61_store.py` | `test_fts5_query_matches_indexed_content` | Writes 3 records, queries via FTS5, asserts only the matching row(s) return; then updates one record's content and deletes another, re-queries, and asserts the update is reflected and the deleted row no longer matches — proves the `memory_artifacts_ai`/`_au`/`_ad` triggers (§6.1) keep `memory_fts` in sync on all three write paths, not just initial insert. |
| T-61.08 | `tests/test_phase61_trust.py` | `test_default_entry_tier_never_returns_stated` | Property-style test over all three `source_kind` values; asserts none map to `"STATED"`. |
| T-61.09 | `tests/test_phase61_trust.py` | `test_promotion_requires_allow_redact_block_pass` | A record whose content trips the BLOCK screen; asserts `evaluate_promotion` returns `promoted=False, denial_reason="failed_allow_redact_block_screen"`. |
| T-61.10 | `tests/test_phase61_trust.py` | `test_promotion_requires_regex_prefilter_pass` | A record with an instruction-override-shaped string; asserts denial with `"failed_regex_prefilter"`. |
| T-61.11 | `tests/test_phase61_trust.py` | `test_promotion_requires_full_schema` | A record missing a required field; asserts denial with `"incomplete_schema_fields"`. |
| T-61.12 | `tests/test_phase61_trust.py` | `test_user_stated_promotes_immediately` | `user_stated=True`, all other checks pass; asserts `promoted=True` with `corroboration_count` irrelevant. |
| T-61.13 | `tests/test_phase61_trust.py` | `test_corroboration_threshold_of_two_via_dedicated_counter` | Two independently-derived records with matching `(subject, symbol_ref)`; asserts promotion, and that `count_corroboration()` (new, dedicated `trust.py` code — not `MultiModelConsensusReconciler`, per §6.2 correction) returns 2 and gates the promotion (assert via a spy/mock call, not just the outcome). |
| T-61.14 | `tests/test_phase61_trust.py` | `test_single_uncorroborated_derived_record_stays_unpromoted` | One record, `user_stated=False`; asserts `promoted=False, denial_reason="insufficient_corroboration"`. |
| T-61.35 | `tests/test_phase61_trust.py` | `test_promotion_rejects_fabricated_symbol_citation` | A candidate record whose `symbol_ref` points at a file/symbol that does not exist; asserts `evaluate_promotion` denies it via the new `resolve_symbol_ref()` check (spy the call, not just the outcome), distinct from the 4 existing denial reasons — add `"failed_grounding_check"` to `PromotionDenialReason`. |
| T-61.36 | `tests/test_phase61_trust.py` | `test_conflicting_fact_against_stated_record_resolves_delete` | A new DERIVED record with the same `(subject, symbol_ref)` as an existing STATED row, whose content explicitly negates the STATED row's content (e.g. STATED says `{"uses_wal": true}`, the new record says `{"uses_wal": false}` for the same `symbol_ref`) — per the conflict policy already defined in P61.2.2 Action 7 (§9), an explicit contradiction must resolve to `"delete"`, not any of the other three outcomes; asserts `evaluate_conflict(new, existing) == "delete"` exactly (not merely in `("add","update","delete","none")`) and that `write()` applies it by removing/superseding the old STATED row rather than leaving two conflicting STATED rows for the same `(subject, symbol_ref)`. A second assertion in the same test covers the non-contradicting revision case from the same policy line — same `symbol_ref`, differing `content_hash`, no explicit negation — and asserts `evaluate_conflict() == "update"` exactly, so an implementation returning one constant value cannot pass both assertions. |
| T-61.15 | `tests/test_phase61_migration.py` | `test_preference_store_rows_migrate_with_kind_preference` | Seeds a `CASMapTransaction`-backed preference file, runs migration, asserts equivalent rows exist in `memory_artifacts` with `subject="preference"`. |
| T-61.16 | `tests/test_phase61_migration.py` | `test_invariant_graph_rows_migrate_with_kind_architectural_decision` | Same shape for `invariant_graph.py` → `subject="architectural_decision"`. |
| T-61.17 | `tests/test_phase61_migration.py` | `test_checkpoint_journal_rows_migrate_as_handoff_family` | Seeds checkpoints (including one corrupt entry per Phase 58's retention behavior), asserts migrated rows have `family="handoff"` and the corrupt entry's SHA-256 evidence survives the migration, not silently dropped. |
| T-61.18 | `tests/test_phase61_migration.py` | `test_failure_ledger_rows_migrate_with_kind_failure` | Seeds `failure_ledgers` rows, asserts migrated `subject="failure"` rows preserve `fingerprint` as `symbol_ref` or an equivalent traceable field — not lost. |
| T-61.19 | `tests/test_phase61_migration.py` | `test_patch_memory_rows_migrate_and_pair_with_failure_records` | Seeds `PatchMemoryStore` rows keyed by `error_signature` matching a migrated failure record's fingerprint; asserts the migrated schema links them (queryable join), not two disconnected rows. |
| T-61.20 | `tests/test_phase61_migration.py` | `test_flight_recorder_jsonl_migrates_as_episodic_subject` | Seeds a flights JSONL file, runs migration, asserts equivalent rows exist with `subject="episodic"`, `family="experience"`. |
| T-61.21 | `tests/test_phase61_migration.py` | `test_hook_signatures_migrate_and_satellite_files_no_longer_canonical` | After migration, asserts the unified store, not the old `.rush/hook_signatures.json`, is the source `HookTamperDetector.verify_signatures()` reads from (per Invariant 5, §6.3). |
| T-61.22 | `tests/test_phase61_migration.py` | `test_migration_is_idempotent` | Runs migration twice; asserts no duplicate rows on the second run. |
| T-61.23 | `tests/test_phase61_episodic.py` | `test_episodic_write_uses_flight_recorder_redaction_pattern` | Asserts a new episodic write path calls `sanitize_value` the same way `FlightRecorder.record_event` does (spy the call), not a re-implemented redaction path. |
| T-61.24 | `tests/test_phase61_handoff.py` | `test_receipts_save_restore_now_backed_by_unified_store` | Calls `continuity/receipts.py`'s `save_receipt`/`restore_receipt` (unchanged public signature), asserts the data round-trips through `TypedArtifactStore` instead of the old CAS-JSON path. |
| T-61.25 | `tests/test_phase61_handoff.py` | `test_quarantine_flag_replaced_by_trust_tier` | Asserts `receipts.py` no longer emits the binary `"authority": "historical_evidence", "state": "quarantined"` shape — it emits a `trust_tier` field instead. |
| T-61.26 | `tests/test_phase61_domain_knowledge.py` | `test_fts5_lexical_search_returns_ranked_results` | Writes several `subject="domain_knowledge"` records, queries, asserts BM25-ranked ordering (FTS5's built-in ranking, no embedding call). |
| T-61.27 | `tests/test_phase61_skill_pattern.py` | `test_skill_candidate_requires_trust_store_grant_before_execution_path_exists` | A mined skill candidate with no `PluginTrustStore.grant_trust()` call; asserts `AgentSkillGenerator.generate_skill_markdown()`'s output SKILL.md has no working `rush plugin run` path until trust is explicitly granted (human-gated, matching the synthesis doc's memsearch citation). |
| T-61.28 | `tests/test_phase61_transport.py` | `test_native_sdk_tier_selected_when_available` | Mocks `claude-agent-sdk` as importable; asserts the dispatcher picks tier 1, not ACP or the dedicated-file fallback. |
| T-61.29 | `tests/test_phase61_transport.py` | `test_acp_tier_selected_when_no_native_sdk_but_acp_available` | Mocks a tool with no native SDK but ACP support; asserts tier 2 is selected. |
| T-61.30 | `tests/test_phase61_transport.py` | `test_dedicated_file_fallback_when_neither_available` | Mocks neither native SDK nor ACP; asserts tier 3 (dedicated-file append to `.rush/memory/cross_tool_handoff.md`, gated behind `ExecutionPermissions(artifact_write=True)`) is selected — never `AGENTS.md`/`CLAUDE.md`, which `AgentSafetyGuard` already blocks. |
| T-61.31 | `tests/test_phase61_transport.py` | `test_dispatcher_is_per_tool_not_global` | Two tools with different tier availability in the same run; asserts each gets its own tier independently, not one global tier for the whole session. |
| T-61.32 | `tests/test_phase61_memory_tool.py` | `test_memory_tool_registers_as_both_cli_and_mcp` | Asserts two independent things, matching the real two-part mechanism (`make_tool_wrapper` is MCP-only): (a) `MemoryTool` is present in `rush.tools.ALL_TOOLS` and `rush.catalog.TOOL_SPECS` has a `"memory"` key, and invoking `register_all_tools` with a stub FastMCP server records an `add_tool` call named `rush_memory` (spy the call); (b) `rush.cli.cli.commands` contains a `"memory"` group with `ask`/`write`/`promote`/`list`/`recall` subcommands (introspect Click's command tree) — same two-part shape `SessionContinuityTool`'s `"session"` group/`ALL_TOOLS` entry already has. |
| T-61.33 | `tests/test_phase61_memory_tool.py` | `test_memory_ask_returns_tool_result_v1_with_skipped_on_denied` | A denied/absent-checkpoint-equivalent case for a memory `ask`; asserts `status="skipped"` in the returned `ToolResultV1`, matching the `rush_continuity` precedent, not a different shape. |
| T-61.34 | `tests/test_phase61_adr.py` | `test_adr_0030_marked_superseded_and_0049_exists` | Reads `docs/adr/0030-*.md`'s content, asserts a "Superseded by ADR-0049" line exists; reads `docs/adr/0049-*.md`, asserts its `Status` field is `"Accepted"` and it references 0030. |

Coverage: 36 of 36 contract tests specified above are the complete set for this phase (T-61.01 through T-61.36 — note the numbering runs to .36, not .34, after T-61.35/T-61.36 were added for the grounding-check and conflict-resolution gaps folded in from §3.2.2); §10's final gate re-runs all 36 by name, not a sample.

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

#### New Files
1. `src/rush/memory/store.py` — `MemoryArtifact`, `TypedArtifactStore` (§6.1).
2. `src/rush/memory/trust.py` — `TrustTier`, `PromotionResult`, `default_entry_tier`, `evaluate_promotion` (§6.2).
3. `src/rush/memory/migration.py` — one-shot migration functions, one per source (`migrate_preference_store`, `migrate_invariant_graph`, `migrate_checkpoint_journal`, `migrate_failure_ledger`, `migrate_patch_memory`, `migrate_flight_recorder`, `migrate_hook_signatures`), each idempotent (T-61.22).
4. `src/rush/memory/transport.py` — per-tool transport-tier dispatcher (native SDK / ACP / dedicated-file).
5. `src/rush/tools/memory.py` — `MemoryTool(ToolFn)`, `name = "memory"`, operations `ask`/`write`/`promote`/`list`/`recall`, following `SessionContinuityTool`'s exact shape (§2.2).
6. `tests/test_phase61_store.py`, `tests/test_phase61_trust.py`, `tests/test_phase61_migration.py`, `tests/test_phase61_episodic.py`, `tests/test_phase61_handoff.py`, `tests/test_phase61_domain_knowledge.py`, `tests/test_phase61_skill_pattern.py`, `tests/test_phase61_transport.py`, `tests/test_phase61_memory_tool.py`, `tests/test_phase61_adr.py` — contract tests T-61.01 through T-61.36.
7. `docs/adr/0049-typed-artifact-memory-schema-and-trust-tiers.md` — new ADR superseding 0030 (§9 P61.11).
8. `docs/phase-plans/phase-61-implementation-evidence.md` — baseline and contract test evidence.
9. `governance/remediation-phase-61.toml` — this phase's own completion manifest (matching the Phase 51-60 convention, even though this phase closes no `R-xxx` finding — it documents *this phase's* task/test closure the same structured way).

#### Modified Files
1. `src/rush/memory/preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`, `checkpoint_journal.py`, `failure_ledger.py` — each becomes a thin compatibility view over `TypedArtifactStore` (public function signatures unchanged, per T-61.15/16/17/18 asserting round-trip behavior) so existing callers (`continuity/coordination.py`'s direct `FailureLedger`/`FlightRecorder` imports, §2.1 Drift 5) keep working.
2. `src/rush/patch/memory.py` — `PatchMemoryStore` becomes a thin view over `TypedArtifactStore` for `subject="failure"` rows (T-61.19).
3. `src/rush/tools/flight_recorder.py` — `FlightRecorder.record_event`/`replay_session` write/read through `TypedArtifactStore` instead of the JSONL file (T-61.20, T-61.23).
4. `src/rush/hook/tamper_detector.py` — `HookTamperDetector` reads/writes signatures through `TypedArtifactStore` (T-61.21).
5. `src/rush/continuity/receipts.py` — `save_receipt`/`restore_receipt` write/read through `TypedArtifactStore`, `trust_tier` replaces the binary `"quarantined"` flag (T-61.24, T-61.25).
6. `src/rush/session_memory.py` — becomes the episodic/session write path into `TypedArtifactStore` (`subject="episodic"`).
7. `src/rush/memory/mistake_miner.py` — `mine_mistakes()` output feeds into `TypedArtifactStore` as `subject="failure"` candidate records (`trust_tier="DERIVED"`, pending corroboration).
8. rush's current cross-tool provider dispatch file — **exact path to be confirmed at P61.10.1 RED** (the synthesis doc describes it as "a hardcoded provider dict" but does not cite a file:line; grep for it, do not assume — likely under `src/rush/continuity/providers.py` given that file's name, verify before writing the task's Allowed Writes).
9. `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` — add a "Superseded by ADR-0049" status note (content unchanged otherwise, per the guardrail in §3.2 item 6).
10. `docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md`, `docs/adr/0020-cryptographic-hmac-context-boundary-framing.md`, `docs/adr/0041-bi-temporal-git-revert-mistake-memory-spine.md` — same "Superseded by ADR-0049" pointer note (§8.2).
11. `docs/adr/README.md`, `docs/maintainers/adr/README.md` — add the ADR-0049 index row.
12. `docs/maintainers/adr/015-agent-remediation-and-memory.md` — same superseded-pointer fix as ADR-0018 (this file mirrors 0018 in the maintainers/adr numbering, per the docs-tree audit).
13. `docs/developer/backlog.md` — **this file is currently missing a Phase 60 row entirely** (confirmed by direct read this session — its milestone table stops at Phase 59-era content despite Phase 60 being complete per `docs/phase-plans/README.md` and git history). This phase's doc-sync task must add both the missing Phase 60 row and the new Phase 61 row — a pre-existing gap this phase surfaces and fixes, not a new one it creates.
14. `docs/phase-plans/README.md` — add the Phase 61 row to the master phase sequencing table.

### 8.2 Comprehensive `/docs` Synchronization Inventory

**Coverage statement, corrected and fully resolved:** the original research pass grep-scanned all 353 `.md` files then under `docs/` and reported 90 matches, never independently re-verified against a re-run of its own grep. A follow-up review re-ran it and found the real number is 96 (against 355 files now on disk — 2 more than 353 because this plan document and the Phase 62 plan document, both newly created this session, live under `docs/phase-plans/` and match their own search terms; both are excluded from the corpus being audited, since a plan is not documentation of current behavior going stale, it's the artifact describing the change). Of the 96: 87 were already accounted for somewhere in Groups A-D below. The remaining 9 were individually read this session (not deferred to an implementation-time task) and classified:

- **Needs update, live doc with stale quarantine language** (→ Group B): `docs/AGENTIC_RUSH.md` (L9: "quarantined `historical_evidence`"), `docs/agentic-rush/anti-hallucination.md` (L7: same pattern).
- **Needs update, historical build-plan describing current memory design in depth** (→ Group B, pointer note like phase-41/42/43): `docs/reports/rush-unified-agent-intelligence-development-plan.md`, `docs/reports/rush-unified-agent-intelligence-development-plan-agy.md` — these are the source plans that built `src/rush/continuity/`'s current shape (the "Continuity implementation program" P1-P5 backlog items).
- **Needs update, historical phase-plan citing current memory files' specific behavior** (→ Group B2, one-line note): `docs/phase-plans/phase-53-sanitization-diagnostics-write-boundaries-plan.md` (enumerates memory files' write-boundary status, which changes once they become thin compatibility views), `docs/phase-plans/phase-55-atomic-file-physical-containment-plan.md` (L18/L84: states "Phase 58 owns" memory-writer migration — still true, but incomplete once Phase 61 also touches it), `docs/phase-plans/phase-60-maintainability-hotspot-reduction-plan.md` (L144-166, L440-445: this is the phase that built `continuity/receipts.py`'s current `save_receipt`/`restore_receipt` shape — directly relevant provenance).
- **Confirmed no update needed, false positives**: `docs/user-guide/testing-confidence.md` (L67: "quarantined repetitions" refers to flaky-test isolation, unrelated to the memory subsystem's quarantine flag — same false-positive class as `docs/reports/final-handoff.md`, already excluded in Group F); `docs/phase-plans/phase-52-packaging-artifact-version-contract-plan.md` (mentions `mistake_miner.py` only incidentally in an import-path file list, not a design claim about memory behavior).

**Two further gaps found on a subsequent re-check of this section, both fixed:**
1. **Item-numbering collision.** Adding items to Group B and Group B2 above reused numbers 21-24 that Group C already used — renumbered the entire §8.2 sequence continuously below, no duplicates.
2. **Two categories of file were matched by the grep but never actually classified anywhere in Groups A-F**, discovered by computing the real deduped union of every file cited in Groups A-D (70 unique files before the phase-58 addition below, 71 after — not 94 — the "94" figure was arithmetic done without deduplicating files that appear in both Group D and another group for two different reasons) and diffing it against the 96 real hits:
   - `docs/phase-plans/phase-58-lock-persistence-patch-fail-closed-plan.md` — excluded from the Group D boilerplate re-count (§2.4) as a historical completed plan, but never actually added anywhere as "needs a pointer note" or "confirmed no update" — it does describe `MeshLockManager`/`CASMapTransaction` in depth (the exact primitives Phase 61 builds on) and gets the same one-line pointer treatment as phase-60's plan doc (now Group B2).
   - `docs/reports/cross-llm-memory-system-plan-2026-09-06.md` and `docs/reports/cross-llm-memory-system-synthesis-2026-09-06.md` — the authority documents this entire phase implements. Not documentation of current rush behavior that goes stale; excluded from the audit corpus with this stated reason, same as this plan document's own self-exclusion, not silently absent.

**Final resolved total, recomputed by deduplicating the real file union (not re-adding rough group sizes): 71 unique files need updates** (70 + the newly-added phase-58 plan pointer), **280 need none** (353 total audited corpus, minus the 2 authority docs now explicitly excluded = 351, minus 71 needing updates = 280).

#### Group A — Core memory-subsystem docs (15 files; substantive rewrite; describe the memory model as primary subject)
3. `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` — superseded pointer (§8.1 item 9).
4. `docs/architecture/rush-epistemic-memory-and-agent-substrate.md` — rewrite: replace the `quarantined`/`historical_evidence` binary model description with the 4-tier trust taxonomy and unified schema.
5. `docs/agentic-rush/patch-remediation-and-memory.md` — rewrite: XML-boundary session memory and receipt model both change under the unified store.
6. `docs/ARCHITECTURE.md` and `docs/developer/architecture.md` (both copies, §2.3) — rewrite the module inventory: `.rush/preferences.json`, `.rush/sessions/`, `.rush/memory/invariants.json`, `.rush/memory/failures.db` all become rows in `.rush/memory.db`.
7. `docs/DEVELOPER_GUIDE.md` (line 70) — update the `src/rush/memory/*.py` module-name list to reflect the thin-compatibility-view shape (§8.1 Modified Files 1).
8. `docs/developer/source-tree.md` (lines 43-48) — same module inventory, tree form; add `store.py`, `trust.py`, `migration.py`, `transport.py`.
9. `docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md` — superseded pointer (§8.1 item 10).
10. `docs/adr/0020-cryptographic-hmac-context-boundary-framing.md` — superseded pointer (§8.1 item 10).
11. `docs/adr/0041-bi-temporal-git-revert-mistake-memory-spine.md` — superseded pointer (§8.1 item 10).
12. `docs/adr/README.md` and `docs/maintainers/adr/README.md` — new ADR-0049 index row (§8.1 item 11).
13. `docs/maintainers/adr/015-agent-remediation-and-memory.md` — superseded pointer (§8.1 item 12).
14. `docs/reports/runtime-memory-and-agent-skills.md` — reconcile against the new design.
15. `docs/reports/memory-innovation-enhancement-report.md` — reconcile against the new design; note which of its ideas this phase implements vs. defers to Phase 62+.

#### Group B — Peripheral docs with specific stale facts (16 files; targeted updates)
16. `docs/JSON_SCHEMA.md` (line 9, `metadata.handoff` schema fields) — update to the new `MemoryArtifact` shape.
17. `docs/reference/result-reference.md` (line 13, same schema) — same fix, nested copy.
18. `docs/reference/mcp-tool-reference.md` (line 64, `rush_session_context` XML framing) — update for `rush_memory` tool's actual result shape (T-61.33's `ToolResultV1`/`status="skipped"` pattern).
19. `docs/SAFETY.md`, `docs/SECURITY.md`, `docs/safety/security-model.md` (both copies where applicable, §2.3) — quarantine/XML-framing security claims → trust-tier + tamper-signature security claims.
20. `docs/TROUBLESHOOTING.md`, `docs/user-guide/troubleshooting.md`, `docs/user-guide/working-with-ai-agents.md` — "quarantined historic instruction" UX language → trust-tier language.
21. `docs/developer/repository-remediation-plan.md` (lines 157-158) — reconcile its citation of `invariant_graph.py`/`preference_store.py`/`checkpoint_journal.py`'s unlocked-read-modify-write behavior against this phase's thin-compatibility-view change.
22. `docs/developer/phase-41-*.md`, `phase-42-*.md`, `phase-43-*.md` (`docs/developer/` copies) and `docs/phase-plans/phase-41-*.md`, `phase-42-*.md`, `phase-43-*.md` — add a one-line "superseded by Phase 61 for the memory/mistake-memory portions" pointer; do not rewrite (historical build-plan record).
23. `docs/AGENTIC_RUSH.md` — line 9's "quarantined `historical_evidence`" language updated to the trust-tier model.
24. `docs/agentic-rush/anti-hallucination.md` — line 7's "quarantined evidence" language updated to the trust-tier model.
25. `docs/reports/rush-unified-agent-intelligence-development-plan.md`, `docs/reports/rush-unified-agent-intelligence-development-plan-agy.md` — the source plans that built `src/rush/continuity/`'s current shape; add a one-line "superseded by Phase 61" pointer for their `session_memory`/`checkpoint_journal`/`invariant_graph`/`failure_ledger`/ADR-0030 citations, same treatment as phase-41/42/43 above; do not rewrite (historical build-plan record).

#### Group B2 — Evidence docs (8 files; one-line note only, no rewrite — historical, point-in-time)
26. `docs/developer/phase-52-implementation-evidence.md`, `phase-53-implementation-evidence.md`, `phase-58-implementation-evidence.md`, `phase-60-implementation-evidence.md` — add a one-line note that the memory/persistence files they audited have since migrated under Phase 61.
27. `docs/phase-plans/phase-53-sanitization-diagnostics-write-boundaries-plan.md` — one-line note: the memory files it enumerates (`checkpoint_journal.py`/`failure_ledger.py`/`invariant_graph.py`/`merkle_invalidator.py`/`preference_store.py`) are now thin compatibility views over `TypedArtifactStore`.
28. `docs/phase-plans/phase-55-atomic-file-physical-containment-plan.md` — one-line note at L18/L84: "Phase 58 owns memory-writer migration" is still true but incomplete; Phase 61 also touches these writers.
29. `docs/phase-plans/phase-60-maintainability-hotspot-reduction-plan.md` — one-line note: `continuity/receipts.py`'s `save_receipt`/`restore_receipt` (built by this phase, L440-445) now writes through `TypedArtifactStore` with `trust_tier` replacing the quarantine flag.
30. `docs/phase-plans/phase-58-lock-persistence-patch-fail-closed-plan.md` — one-line note: describes `MeshLockManager`/`CASMapTransaction` (`src/rush/mcp_mesh/lock_manager.py`, `src/rush/memory/transactions.py`) in depth as this phase's own predecessor artifacts — the exact primitives Phase 61 supersedes (§2.1 Drift 1); add a pointer noting `transactions.py`'s `CASMapTransaction` is no longer the canonical store once Phase 61 ships.

#### Group C — Cross-cutting reference/config docs naming the memory subsystem (15 files)
31. `docs/CONFIG_SCHEMA.md`, `docs/CONFIGURATION.md`, `docs/ENVIRONMENT_VARIABLES.md`, `docs/reference/configuration-reference.md`, `docs/reference/environment-variables.md` — add `.rush/memory.db` path, remove references to the now-absorbed satellite file paths.
32. `docs/GLOSSARY.md`, `docs/getting-started/glossary.md` — add terms: Typed Artifact, Trust Tier, Write-Promotion Rule, Transport Dispatcher.
33. `docs/MCP.md`, `docs/MCP_REFERENCE.md` — document the `rush_memory` MCP tool (operations, result shape).
34. `docs/CLI_REFERENCE.md`, `docs/reference/cli-reference.md` (both copies) — document `rush memory ask|write|promote|list|recall`.
35. `docs/TOOL_CATALOG.md` — register `memory` tool.
36. `docs/PRIVACY.md`, `docs/safety/privacy-and-data-handling.md` — update for redact-before-store invariant (§6.3 item 2).
37. `docs/SCOPE.md` — physical containment note for `.rush/memory.db`.

#### Group C2 — Remaining cross-cutting docs (13 files)
38. `docs/SEMANTIC_DRIFT.md` — reconciliation entry for this phase's own drift-fix items (§2.1).
39. `docs/API_REFERENCE.md` — public API for `rush.memory.store`, `rush.memory.trust`, `rush.memory.transport`.
40. `docs/agentic-rush/plugins-and-agent-skills.md` — skill/pattern subject's execution-path wiring (T-61.27).
41. `docs/developer/testing-guide.md` — add `tests/test_phase61_*.py` section.
42. `docs/developer/debugging-guide.md` — troubleshooting for WAL lock contention, staleness flags, signature mismatches.
43. `docs/developer/issues.md`, `docs/developer/tool-development.md` — add a memory-subsystem-specific entry only if this phase's implementation surfaces one; otherwise no change (confirm at P61.13.1, don't pre-decide here).
44. `docs/vibecoding/instant-fix-and-auto-remediation.md` — patch/failure-memory pairing note (T-61.19).
45. `docs/user-guide/advanced-checks.md`, `docs/user-guide/security-and-supply-chain.md` — reference updates for the new trust-tier model.
46. `docs/maintainers/release-playbook.md`, `docs/maintainers/versioning-and-compatibility.md`, `docs/maintainers/incident-and-security.md` — schema-version and incident-triage notes for the new store.

#### Group D — The 41-file duplicated boilerplate fix (§2.4; 41 of 41 affected files, one authored replacement applied uniformly to every one)
47. `docs/CLI_REFERENCE.md`
48. `docs/CONFIG_SCHEMA.md`
49. `docs/CONFIGURATION.md`
50. `docs/ENVIRONMENT_VARIABLES.md`
51. `docs/GLOSSARY.md`
52. `docs/JSON_SCHEMA.md`
53. `docs/MCP.md`
54. `docs/MCP_REFERENCE.md`
55. `docs/PRIVACY.md`
56. `docs/SAFETY.md`
57. `docs/SCOPE.md`
58. `docs/SECURITY.md`
59. `docs/SEMANTIC_DRIFT.md`
60. `docs/TOOL_CATALOG.md`
61. `docs/API_REFERENCE.md`
62. `docs/ARCHITECTURE.md`
63. `docs/agentic-rush/plugins-and-agent-skills.md`
64. `docs/developer/architecture.md`
65. `docs/developer/backlog.md`
66. `docs/developer/debugging-guide.md`
67. `docs/developer/issues.md`
68. `docs/developer/source-tree.md`
69. `docs/developer/testing-guide.md`
70. `docs/developer/tool-development.md`
71. `docs/getting-started/glossary.md`
72. `docs/maintainers/adr/010-tdd-guard-and-continuous-sensors.md`
73. `docs/maintainers/incident-and-security.md`
74. `docs/maintainers/release-playbook.md`
75. `docs/maintainers/versioning-and-compatibility.md`
76. `docs/reference/cli-reference.md`
77. `docs/reference/configuration-reference.md`
78. `docs/reference/environment-variables.md`
79. `docs/reference/result-reference.md`
80. `docs/safety/permissions.md`
81. `docs/safety/privacy-and-data-handling.md`
82. `docs/safety/safety-overview.md`
83. `docs/safety/security-model.md`
84. `docs/user-guide/advanced-checks.md`
85. `docs/user-guide/security-and-supply-chain.md`
86. `docs/vibecoding/instant-fix-and-auto-remediation.md`
87. `docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md` (also carries the boilerplate paragraph, separate from its Group A superseded-pointer edit — both land in this same file)

(Some of these 41 also appear in Groups A/B/C above for a second, file-specific reason — both edits land in the same file in one pass, not a conflict; count them once in the total files-touched tally, twice in the reason list.)

#### Group E — Root-vs-nested pairs requiring both copies updated (§2.3)
Every file above that has both a root ALLCAPS and a nested lowercase form (`ARCHITECTURE.md`/`developer/architecture.md`, `SAFETY.md`/`safety/safety-overview.md`, `SECURITY.md`/`safety/security-model.md`, `CLI_REFERENCE.md`/`reference/cli-reference.md`, `PRIVACY.md`/`safety/privacy-and-data-handling.md`) gets the same content change applied to both copies — already enumerated individually above (Groups A/C/D); called out here so the doc-sync task (§9 P61.13) verifies both were actually touched, not just one, for each of these 5 pairs.

#### Group F — Confirmed, checked, no update needed (280 of 351 audited files — 353 raw total minus 2 authority docs explicitly excluded, §8.2's coverage statement; 257 had zero hits across all 14 search terms, plus 2 of the 9 originally-pending candidates resolved as false positives — `docs/user-guide/testing-confidence.md` and `docs/phase-plans/phase-52-packaging-artifact-version-contract-plan.md`, both cited in the coverage statement above)
`docs/tutorials/*`, `docs/getting-started/installation.md`/`first-run.md`, `docs/user-guide/checking-code.md`/`checking-project-files.md`/`everyday-workflow.md`/`faq.md`/`index.md`/`understanding-results.md`, `docs/specs/*`, `docs/tools/*`, `docs/workflows/*`, `docs/integrations/*`, `docs/vibecoding/*` (beyond the one flagged in Group C2), `docs/maintainers/*` (beyond those flagged in Groups A/C2/D), all `docs/developer/phase-*` and `docs/phase-plans/phase-*` beyond those flagged in Group B, `docs/reports/*` beyond those flagged in Group A, `docs/developer/brainstorm-*`/`master-*`/`rush-integrations-report.md`/`rush-token-innovation-enhancement-report-plan.md`/`token-reduction-innovation-report.md`/`innovation-enhancement-*-report.md`/`benchmarking-report.md` (speculative/aspirational, not authoritative current-state docs) — no action.

### 8.3 Dependency Constraints

- Zero third-party dependencies introduced. `sqlite3`, `hashlib`, `json`, `re`, `dataclasses`, `pathlib`, `time`, `uuid`, `typing` — Python 3.12 standard library only, matching every predecessor phase.
- `governance/engine-support.toml`'s 19-engine-family taxonomy is unaffected — this phase adds no new external engine dependency.

---

## 8.4 File Conflict Ordering

Files written by more than one task card, and the required order (enforced by each task's `Prerequisites`, restated here explicitly per plan-review Pass 2):

| File | Tasks (in required order) | Ordering mechanism |
|---|---|---|
| `src/rush/memory/store.py` | P61.1.2 (create) → P61.2.2 (wire `evaluate_conflict()` call into `write()`) → P61.7.2 (add `search()`) | P61.2.1's Prerequisites names P61.1.2; P61.7.1's Prerequisites already names P61.2.2 (not just P61.1.2), because conflict resolution changes `write()`'s behavior that `search()` reads back — see P61.7.1's own Prerequisites field below |
| `docs/phase-plans/phase-61-implementation-evidence.md` | P61.0.1 (create) → P61.3.2 (migration evidence note) → P61.6.1 (pairing-check result) → P61.13.1 (finalize) | Natural Prerequisites chain: P61.3.2 needs P61.2.2 needs P61.1.2 needs P61.0.1; P61.6.1 needs P61.3.2; P61.13.1 needs everything |
| `src/rush/tools/flight_recorder.py` | P61.3.2 (migration compatibility view) → P61.5.2 (episodic forward-write wiring) | P61.5.1's Prerequisites names P61.3.2 |
| `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` | P61.11.2 only (single task; also referenced generically in §8.1 item 9, same write) | N/A — one task |

This repository's phase-plan convention (Phase 58 template) has no GoalBuddy-style board; there is no `state.yaml` to cross-check against, so plan-review's "board consistency" and "merged/cancelled tasks" checks are not applicable to this document — noted explicitly rather than silently skipped.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P61.0 — Admission Gate & Baseline Evidence

#### P61.0.1 — EVIDENCE: Map Every Current Memory/Continuity Seam, Triage the 9 Unresolved Doc Candidates, Record Baseline
- **Task ID:** P61.0.1
- **Binary Outcome:** `docs/phase-plans/phase-61-implementation-evidence.md` created with the exact current passing-test count and a confirmed file:line map of every one of the 17 files/modules named in §2.2. (The 9 doc candidates §8.2 originally flagged as pending were already individually read and classified during plan review — folded into Groups A-D directly, not deferred to this task.)
- **Prerequisites:** §4 admission gate passed.
- **Allowed Writes:** `docs/phase-plans/phase-61-implementation-evidence.md`.
- **Actions:**
  1. Run `python -m pytest tests/ -q`, record the exact passing count.
  2. Re-confirm all 17 of the 17 file:line citations in §2.2 by opening each file directly (not from this plan's own text) — this plan was written from a same-session but not same-instant read; re-verify before P61.1 begins in case anything changed.
  3. Grep for rush's current provider-dispatch file (§8.1 Modified Files item 8) and record its confirmed path.
  4. Grep `def log_subsystem` in `src/rush/logging.py` and record its exact signature (§2.2, flagged as not fully captured).
  5. (No longer applicable — the 9-file triage this step originally scheduled was completed during plan review; see §8.2's coverage statement and Groups B/B2 for the resolved classifications.)

---

### P61.1 — Unified Typed-Artifact Store

#### P61.1.1 — RED: Define Store Contract Tests
- **Task ID:** P61.1.1
- **Binary Outcome:** `tests/test_phase61_store.py` created with T-61.01 through T-61.07; all fail (RED) — `ModuleNotFoundError` for `rush.memory.store`.
- **Prerequisites:** P61.0.1.
- **Allowed Writes:** `tests/test_phase61_store.py`.
- **Actions:**
  1. Author T-61.01 through T-61.07 (§7).
  2. Run `pytest tests/test_phase61_store.py -v`, confirm all 7 fail with `ModuleNotFoundError`.

#### P61.1.2 — GREEN: Implement `TypedArtifactStore`
- **Task ID:** P61.1.2
- **Binary Outcome:** `src/rush/memory/store.py` implements `MemoryArtifact` and `TypedArtifactStore` per §6.1; all 7 of T-61.01-07 pass.
- **Prerequisites:** P61.1.1 RED.
- **Allowed Writes:** `src/rush/memory/store.py`.
- **Actions:**
  1. Implement `MemoryArtifact` dataclass exactly as specified in §6.1.
  2. Implement `TypedArtifactStore.__init__` — opens `.rush/memory.db`, sets `PRAGMA journal_mode=WAL`, runs the `CREATE TABLE`/`CREATE INDEX`/`CREATE VIRTUAL TABLE`/`CREATE TRIGGER` DDL from §6.1 (the three `memory_artifacts_ai`/`_au`/`_ad` triggers are part of this same `_init_db()` DDL block — no separate FTS-sync step exists elsewhere in `write()` or `recall()`).
  3. Implement `write()` — enforces Invariant 1 (no-STATED-on-entry, §6.3), calls `sanitize_value()` internally (Invariant 2).
  4. Implement `recall()` — enforces Invariants 3 (signature re-verify), 4 (Trojan Source scan via a new `TrojanSourceDetector.inspect_text` or equivalent), 6 (staleness check via the pure `MerkleInvalidator.hash_content()` computation only — `src/rush/memory/merkle_invalidator.py:35-36` — never `check_and_update()` or any other stateful method; see §6.3 Invariant 6 for why this boundary is load-bearing, not stylistic).
  5. Implement `search()`'s FTS5 query path for T-61.07. Do not add any manual FTS insert/delete call inside `write()` — the three sync triggers from §6.1 own that.
  6. Run `pytest tests/test_phase61_store.py -v`, confirm all 7 GREEN.
  7. `ruff check src/rush/memory/store.py && ruff format --check src/rush/memory/store.py`.

---

### P61.2 — Trust Tier & Write-Promotion Rule

#### P61.2.1 — RED: Define Trust-Tier Contract Tests
- **Task ID:** P61.2.1
- **Binary Outcome:** `tests/test_phase61_trust.py` created with T-61.08 through T-61.14 and T-61.35, T-61.36; all 9 fail (RED).
- **Prerequisites:** P61.1.2.
- **Allowed Writes:** `tests/test_phase61_trust.py`.
- **Actions:**
  1. Author T-61.08 through T-61.14 (§7).
  2. Author T-61.35 (grounding-check denial) and T-61.36 (conflict-resolution outcome) per §3.2.2/§7.
  3. Run `pytest tests/test_phase61_trust.py -v`, confirm all 9 RED.

#### P61.2.2 — GREEN: Implement Trust Tier, Promotion Gate, Grounding Check & Conflict Resolution
- **Task ID:** P61.2.2
- **Binary Outcome:** `src/rush/memory/trust.py` implements `default_entry_tier`, `evaluate_promotion` (per §6.2, now with a fifth grounding-check stage), and `evaluate_conflict`; all 9 of T-61.08-14, T-61.35, T-61.36 pass.
- **Prerequisites:** P61.2.1 RED.
- **Allowed Writes:** `src/rush/memory/trust.py`, `src/rush/memory/store.py` (only to call `evaluate_conflict()` from `write()` when a matching `STATED` row exists — no other change to `store.py` in this task).
- **Actions:**
  1. Implement `default_entry_tier` — never returns `"STATED"` (T-61.08).
  2. Implement a rush-own ALLOW/REDACT/BLOCK screen function (new code; do not import or copy any `hindsight` source — idea-only per synthesis doc methodology).
  3. Implement a rush-own regex pre-filter against instruction-override/exfiltration patterns (new code; idea-only, no `zettelforge` source copied).
  4. Implement the full-schema-populated check.
  5. Add a fifth promotion-gate stage, new code (not `GroundingVerifier` reuse — see §3.2.2 correction): `resolve_symbol_ref(symbol_ref: str, project_root: Path) -> bool` splits on `::`, confirms the file exists, `ast.parse`s it, and confirms the symbol name is a top-level `def`/`class`. Wire it into `evaluate_promotion()`; add `"failed_grounding_check"` to `PromotionDenialReason` (T-61.35).
  6. Implement `count_corroboration(subject: MemorySubject, symbol_ref: str | None, candidate_sources: list[str]) -> int` as new, dedicated code in `trust.py` — this is new code, not a reuse of `rush.score.consensus.MultiModelConsensusReconciler` (see §6.2 correction: its grouping key is hardcoded to `(file_path, line_number, rule_id)` with no parameterization, and `ModelFinding.rule_id: str` can't type-safely represent an Optional `symbol_ref`). Wire it into `evaluate_promotion()` for the `corroboration_count >= 2` check (T-61.13 asserts the corroboration-counting outcome directly, not a spy on `MultiModelConsensusReconciler`).
  7. Implement `evaluate_conflict(new_artifact, existing_stated_artifact) -> Literal["add","update","delete","none"]` (§3.2.2 item 2) — an LLM-free, rush-own reconciliation: `"none"` if content is identical, `"update"` if the new record's `content_hash` differs but `symbol_ref` still resolves the same way, `"delete"` if the new record signals the old fact is now false (e.g. explicit contradiction in content), `"add"` otherwise (no real conflict, both stand). Wire it into `store.py`'s `write()` — called before insert whenever a matching `(subject, symbol_ref)` `STATED` row already exists (T-61.36).
  8. Run `pytest tests/test_phase61_trust.py -v`, confirm all 9 GREEN.

---

### P61.3 — Migrate Existing Stores

#### P61.3.1 — RED: Define Migration Contract Tests
- **Task ID:** P61.3.1
- **Binary Outcome:** `tests/test_phase61_migration.py` created with T-61.15 through T-61.22; all 8 fail (RED).
- **Prerequisites:** P61.2.2.
- **Allowed Writes:** `tests/test_phase61_migration.py`.
- **Actions:**
  1. Author T-61.15 through T-61.22 (§7), each seeding real fixture data in the OLD format (`CASMapTransaction` JSON files, `failure_ledgers` SQLite rows, checkpoint JSON, `PatchMemoryStore` SQLite rows, flight JSONL, hook signatures JSON) before asserting the migrated shape.
  2. Run `pytest tests/test_phase61_migration.py -v`, confirm all 8 RED.

#### P61.3.2 — GREEN: Implement Migration Functions & Compatibility Views
- **Task ID:** P61.3.2
- **Binary Outcome:** `src/rush/memory/migration.py` implements all seven migration functions (§8.1 New Files item 3); `preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`, `checkpoint_journal.py`, `failure_ledger.py`, `patch/memory.py`, `tools/flight_recorder.py`, `hook/tamper_detector.py` each become thin compatibility views (§8.1 Modified Files 1-4); all 8 of T-61.15-22 pass.
- **Prerequisites:** P61.3.1 RED.
- **Allowed Writes:** `src/rush/memory/migration.py`, `src/rush/memory/preference_store.py`, `src/rush/memory/invariant_graph.py`, `src/rush/memory/merkle_invalidator.py`, `src/rush/memory/checkpoint_journal.py`, `src/rush/memory/failure_ledger.py`, `src/rush/patch/memory.py`, `src/rush/tools/flight_recorder.py`, `src/rush/hook/tamper_detector.py`.
- **Actions:**
  1. Implement each migration function, idempotent (T-61.22 — check for an existing migrated row before inserting, keyed by original identifier).
  2. Refactor each of the 8 modified-files targets to read/write through `TypedArtifactStore` while preserving public function signatures (existing callers, including `continuity/coordination.py`'s direct `FailureLedger`/`FlightRecorder` imports per §2.1 Drift 5, must keep working unmodified).
  3. Rename `.rush/sessions/flights/*.jsonl` (`FlightRecorder`) and `.rush/hook_signatures.json` (`HookTamperDetector`), and the other satellite JSON/JSONL files, with a `.migrated` suffix (never delete) per Invariant 5 (§6.3). Do **not** rename, move, or delete `.rush/cache.db` — `PatchMemoryStore`'s migration copies its `patch_memory` table rows into `TypedArtifactStore` and leaves the physical file in place and live, because `ResultCache` (`src/rush/cache.py:94-99`) shares that same file for an unrelated tool-result cache and is not part of this migration. Record the exact renamed paths (JSONL/JSON only) in this task's evidence note within `docs/phase-plans/phase-61-implementation-evidence.md`.
  4. Run `pytest tests/test_phase61_migration.py -v`, then run the full existing suite for these 8 modules (`pytest tests/ -k "preference or invariant or merkle or checkpoint or failure_ledger or patch_memory or flight_recorder or tamper" -v`) to confirm zero regression in pre-existing tests for these modules.

---

### P61.4 — Active-Context / Handoff Family

#### P61.4.1 — RED: Define Handoff Contract Tests
- **Task ID:** P61.4.1
- **Binary Outcome:** `tests/test_phase61_handoff.py` created with T-61.24, T-61.25; both fail (RED).
- **Prerequisites:** P61.3.2.
- **Allowed Writes:** `tests/test_phase61_handoff.py`.
- **Actions:** Author T-61.24, T-61.25; run, confirm both RED.

#### P61.4.2 — GREEN: Migrate `receipts.py` Off the Binary Quarantine Flag
- **Task ID:** P61.4.2
- **Binary Outcome:** `continuity/receipts.py` writes/reads through `TypedArtifactStore` with `family="handoff"`, `trust_tier` replacing the old binary flag; both T-61.24-25 pass.
- **Prerequisites:** P61.4.1 RED.
- **Allowed Writes:** `src/rush/continuity/receipts.py`.
- **Actions:**
  1. Replace the `"authority": "historical_evidence", "state": "quarantined"` emission with a `trust_tier` field sourced from `default_entry_tier` (§6.2).
  2. Preserve `save_receipt`/`restore_receipt`'s existing public signatures.
  3. Run `pytest tests/test_phase61_handoff.py -v`, confirm both GREEN; run existing `continuity`-related tests for regression.

---

### P61.5 — Episodic/Session Family

#### P61.5.1 — RED: Define Episodic Contract Test
- **Task ID:** P61.5.1
- **Binary Outcome:** `tests/test_phase61_episodic.py` created with T-61.23 (the forward-write-path contract; T-61.20 already covers old-data migration in P61.3); fails (RED).
- **Prerequisites:** P61.3.2.
- **Allowed Writes:** `tests/test_phase61_episodic.py`.
- **Actions:** Author T-61.23; run; confirm RED.

#### P61.5.2 — GREEN: Wire `session_memory.py` and `FlightRecorder` to the Unified Store
- **Task ID:** P61.5.2
- **Binary Outcome:** New episodic writes from both `session_memory.py` and `FlightRecorder.record_event` land in `TypedArtifactStore` with `subject="episodic"`, `family="experience"`; T-61.23 passes.
- **Prerequisites:** P61.5.1 RED.
- **Allowed Writes:** `src/rush/session_memory.py`, `src/rush/tools/flight_recorder.py`.
- **Actions:**
  1. Confirm `log_subsystem`'s exact signature (recorded at P61.0.1) before modifying `session_memory.py`'s logging calls.
  2. Wire both write paths through the same `sanitize_value`-then-`TypedArtifactStore.write()` sequence.
  3. Run `pytest tests/test_phase61_episodic.py -v`, confirm GREEN.

---

### P61.6 — Failure/Mistake Family

(Architectural-decision is fully covered by P61.3's generic migration — §5 ledger — and needs no dedicated task card here, since the Migration Path specifies migration-only for it, no new forward-write behavior.)

#### P61.6.1 — VERIFY: Confirm the Pairing Contract Is Actually Covered
- **Task ID:** P61.6.1
- **Binary Outcome:** `pytest tests/test_phase61_migration.py::test_patch_memory_rows_migrate_and_pair_with_failure_records -v` result recorded in evidence — pass (if P61.3.2 already satisfied it end-to-end) or fail with a named gap (if the *query* surface, not just migration, needs additional work here).
- **Prerequisites:** P61.3.2.
- **Allowed Writes:** none if passing; `tests/test_phase61_migration.py` only if a genuine gap is found (add the missing assertion, do not silently skip it).
- **Actions:** Run the named test; record the exact result (pass, or fail-with-reason) in `docs/phase-plans/phase-61-implementation-evidence.md` — this task is a verification checkpoint, not assumed-passing.

#### P61.6.2 — GREEN: Wire `mistake_miner.py` Output as Candidate Failure Records
- **Task ID:** P61.6.2
- **Binary Outcome:** `mine_mistakes()`'s output feeds `TypedArtifactStore.write()` calls with `subject="failure"`, `trust_tier="DERIVED"`.
- **Prerequisites:** P61.6.1.
- **Allowed Writes:** `src/rush/memory/mistake_miner.py`.
- **Actions:**
  1. Wire `mine_mistakes()`'s per-revert findings into `TypedArtifactStore.write()`.
  2. Verify no regression in `mine_mistakes()`'s existing git-log-parsing tests.

---

### P61.7 — Domain/Project-Knowledge Family (Lexical Only, §3.2 item 4)

#### P61.7.1 — RED: Define FTS5 Lexical Search Contract Test
- **Task ID:** P61.7.1
- **Binary Outcome:** `tests/test_phase61_domain_knowledge.py` created with T-61.26; fails (RED).
- **Prerequisites:** P61.2.2 (not just P61.1.2 — `search()` reads through `write()`'s post-P61.2.2 conflict-resolution behavior; §8.4 File Conflict Ordering).
- **Allowed Writes:** `tests/test_phase61_domain_knowledge.py`.
- **Actions:** Author T-61.26; run; confirm RED (the store's FTS5 virtual table exists from P61.1.2, but no query API is exposed yet for `subject="domain_knowledge"` specifically).

#### P61.7.2 — GREEN: Expose Domain-Knowledge Query Path
- **Task ID:** P61.7.2
- **Binary Outcome:** A `TypedArtifactStore.search(subject="domain_knowledge", query=...)` method returns BM25-ranked FTS5 results; T-61.26 passes.
- **Prerequisites:** P61.7.1 RED.
- **Allowed Writes:** `src/rush/memory/store.py`.
- **Actions:** Add `search()` method scoped by `subject`; run `pytest tests/test_phase61_domain_knowledge.py -v`, confirm GREEN.

---

### P61.8 — Skill/Pattern Family

#### P61.8.1 — RED: Define Skill-Candidate Admission Test
- **Task ID:** P61.8.1
- **Binary Outcome:** `tests/test_phase61_skill_pattern.py` created with T-61.27; fails (RED).
- **Prerequisites:** P61.2.2 (needs the trust/promotion gate).
- **Allowed Writes:** `tests/test_phase61_skill_pattern.py`.
- **Actions:** Author T-61.27; run; confirm RED.

#### P61.8.2 — GREEN: Wire Skill Mining to `PluginTrustStore`/`AgentSkillGenerator`
- **Task ID:** P61.8.2
- **Binary Outcome:** A mined `subject="skill_pattern"` candidate's generated SKILL.md has no working `rush plugin run` path until `PluginTrustStore.grant_trust()` is explicitly called for it; T-61.27 passes.
- **Prerequisites:** P61.8.1 RED.
- **Allowed Writes:** `src/rush/plugins/skills_generator.py`.
- **Actions:**
  1. Confirm `generate_skill_markdown()`'s current signature (§2.2) is unchanged.
  2. Add the trust-gate check: the generated markdown's `rush plugin run <name>` line is only emitted if `PluginTrustStore.is_trusted(name, digest)` returns true for that candidate.
  3. Run `pytest tests/test_phase61_skill_pattern.py -v`, confirm GREEN.

---

### P61.9 — Read-Side Scoping & Recall-Time Defense

This workstream's contracts are already covered by T-61.04 and T-61.05 (§7, both in `test_phase61_store.py`, already implemented at P61.1.2). **No separate task card** — recorded here so the Subject-Ownership Ledger (§5) row for "Trust/governance layer" has an explicit pointer rather than an implied one: session-scoped read allowlist behavior is verified as part of P61.1's contract tests, not a distinct workstream.

---

### P61.10 — Cross-Tool Transport Dispatcher

#### P61.10.1 — RED: Define Transport-Tier Contract Tests
- **Task ID:** P61.10.1
- **Binary Outcome:** `tests/test_phase61_transport.py` created with T-61.28 through T-61.31; all 4 fail (RED). This task also confirms (per §8.1 Modified Files item 8) the exact current provider-dispatch file path via grep, recorded in evidence before RED tests are authored against it.
- **Prerequisites:** P61.0.1 (path confirmation).
- **Allowed Writes:** `tests/test_phase61_transport.py`.
- **Actions:**
  1. Grep the codebase for rush's current hardcoded provider dict (do not assume `continuity/providers.py` — verify).
  2. Author T-61.28 through T-61.31 (§7) with mocks for SDK-importability and ACP-availability detection.
  3. Run; confirm all 4 RED.

#### P61.10.2 — GREEN: Implement Per-Tool Tier Dispatcher
- **Task ID:** P61.10.2
- **Binary Outcome:** `src/rush/memory/transport.py` implements the native-SDK → ACP → dedicated-file tier selection, per-tool not global; all 4 of T-61.28-31 pass.
- **Prerequisites:** P61.10.1 RED.
- **Allowed Writes:** `src/rush/memory/transport.py`, and the confirmed provider-dispatch file from P61.10.1's grep (exact path recorded in evidence, not guessed here).
- **Actions:**
  1. Implement tier detection: tier 1 if the target tool's native SDK/protocol is importable/reachable (`claude-agent-sdk` for Claude Code, `codex app-server` for Codex); tier 2 if ACP is available for that tool and tier 1 isn't; tier 3 otherwise.
  2. **Tier 3 never writes to `AGENTS.md`/`CLAUDE.md`.** `src/rush/safety/guard.py`'s `PROTECTED_GOVERNANCE_FILES` (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.windsurfrules`, `rush.toml`, `.rush/trust.json`, `.rush/hooks.json`, `SECURITY.md`) and `AgentSafetyGuard.validate_write_target()` already hard-block agent writes to these exact files (raises `PermissionError: "Agent mutation blocked: ... is an immutable governance file."`, wired at `src/rush/cli.py:1380-1383`), and `src/rush/patch/diff_parser.py`'s `GOVERNANCE_BLOCKED_FILES` mirrors the same set for diff application. Appending memory content to those files as originally specified would violate this existing firewall, not just skip a permission check. Tier 3 instead writes to a dedicated, rush-owned file: `.rush/memory/cross_tool_handoff.md` (created if absent). Format: append a fenced, timestamped, source-tagged block per write (`<!-- rush-memory: <source> @ <ISO8601 timestamp> -->` + the artifact content), never freeform.
  3. Gate tier 3 behind an explicit permission check, matching the existing pattern `_validate_provider_access()` uses for `network` (`src/rush/continuity/providers.py:255-292`, `check_permissions()` from `src/rush/permissions.py`): require `ExecutionPermissions(artifact_write=True)` — the same flag/CLI switch (`--allow-artifact-write`, `PERMISSION_FLAG_MAP` in `src/rush/permissions.py:17-25`) other artifact-producing paths already use; deny with a `skipped` result (matching `_validate_provider_access`'s existing denial shape) if not granted.
  4. Deduplicate on write: before appending, check whether a block with the same `(source, content_hash)` already exists in `.rush/memory/cross_tool_handoff.md` and skip the append if so (never re-append identical content).
  5. Provide a cleanup path: `transport.py` exposes a function to prune blocks older than a caller-supplied age or exceeding a caller-supplied max-block count from `.rush/memory/cross_tool_handoff.md` — not automatic, invoked explicitly (mirrors Invariant 5's human-opt-in cleanup pattern, §6.3).
  6. Ensure the dispatcher is called per-tool, not once globally (T-61.31).
  7. Replace the old hardcoded provider dict's call sites with the new dispatcher.
  8. Run `pytest tests/test_phase61_transport.py -v`, confirm all 4 GREEN.

---

### P61.11 — Supersede ADR-0030

#### P61.11.1 — RED: Define ADR Supersession Test
- **Task ID:** P61.11.1
- **Binary Outcome:** `tests/test_phase61_adr.py` created with T-61.34; fails (RED — ADR-0049 doesn't exist yet).
- **Prerequisites:** P61.1.2 through P61.10.2 (the new design must be built before the ADR can accurately describe it).
- **Allowed Writes:** `tests/test_phase61_adr.py`.
- **Actions:** Author T-61.34; run; confirm RED.

#### P61.11.2 — GREEN: Write ADR-0049, Mark ADR-0030 Superseded
- **Task ID:** P61.11.2
- **Binary Outcome:** `docs/adr/0049-typed-artifact-memory-schema-and-trust-tiers.md` exists, `Status: Accepted`, describes the actually-built §6 design; `docs/adr/0030-*.md` has a superseded pointer added; T-61.34 passes.
- **Prerequisites:** P61.11.1 RED.
- **Allowed Writes:** `docs/adr/0049-typed-artifact-memory-schema-and-trust-tiers.md`, `docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md` (append-only pointer note, substance unchanged per §3.2 item 6), `docs/adr/0018-*.md`, `docs/adr/0020-*.md`, `docs/adr/0041-*.md` (same pointer note), `docs/adr/README.md`, `docs/maintainers/adr/README.md`, `docs/maintainers/adr/015-agent-remediation-and-memory.md`.
- **Actions:**
  1. Write ADR-0049 using this exact structure (confirmed directly against ADR-0030's real content this session, §2.1 Drift 4 — the same section/heading shape every ADR in this repo uses):
     ```markdown
     # ADR-0049: Typed-Artifact Memory Schema and Trust Tiers

     ## Status
     Accepted (Phase 61)

     ## Context
     [2-4 sentences: ADR-0030 committed to a Working/Policy/World/Skills taxonomy and an
     src/rush/memory/engine.py that was never built (§2.1 Drift 4). This ADR describes what
     was actually built instead: a 7-subject taxonomy on one axis, a 4-tier trust taxonomy
     (STATED/DERIVED/EXTERNAL_WRITE/IMPORTED) on an orthogonal axis, backed by one SQLite
     WAL database at .rush/memory.db.]

     ## Decision
     1. Implement `TypedArtifactStore` (`src/rush/memory/store.py`) — SQLite WAL, one
        `memory_artifacts` table, FTS5 virtual table for lexical search, schema per
        Phase 61 plan §6.1.
     2. Implement 4-tier trust taxonomy and write-promotion rule (`src/rush/memory/trust.py`),
        composing an ALLOW/REDACT/BLOCK screen, a regex pre-filter, a schema-completeness
        check, and corroboration-threshold-2 (via new, dedicated `count_corroboration()`
        code, not `MultiModelConsensusReconciler`) — per Phase 61 plan §6.2.
     3. Migrate `preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`,
        `checkpoint_journal.py`, `failure_ledger.py`, `PatchMemoryStore`, `FlightRecorder`,
        and `HookTamperDetector` onto this store as thin compatibility views; old satellite
        files renamed `.migrated`, never deleted.
     4. Implement a per-tool transport dispatcher (native SDK → ACP → dedicated-file, never
        `AGENTS.md`/`CLAUDE.md`) and one `MemoryTool` query/write interface registered via the
        real two-part CLI+MCP path (`ALL_TOOLS`/`register_all_tools()` for MCP; `TOOL_SPECS` +
        a bespoke `@cli.group` for CLI — `make_tool_wrapper` alone is MCP-only).

     ## Consequences
     - **Positive:** one relational store instead of eight satellite files/formats; a real
       trust taxonomy replacing a single binary quarantine flag; recall-time tamper and
       injection defense that no prior design in this repo had.
     - **Negative:** adds the repo's first WAL-mode SQLite connection (§2.1 Drift 3, no prior
       pattern existed) — new operational surface (lock contention under concurrent writers)
       to monitor.
     - **Safety:** 100% offline, local-first, zero new third-party dependencies (§8.3).
     ```
  2. Add "Superseded by [ADR-0049](0049-...)" as the first line under ADR-0030's `## Status` section.
  3. Add the same pointer to ADR-0018, ADR-0020, ADR-0041 where each describes now-superseded specifics.
  4. Add the ADR-0049 index row to both `docs/adr/README.md` and `docs/maintainers/adr/README.md`.
  5. Fix `docs/maintainers/adr/015-agent-remediation-and-memory.md`'s mirror of ADR-0018.
  6. Run `pytest tests/test_phase61_adr.py -v`, confirm GREEN.

---

### P61.12 — Memory Query/Write Interface (`MemoryTool`)

#### P61.12.1 — RED: Define `MemoryTool` Contract Tests
- **Task ID:** P61.12.1
- **Binary Outcome:** `tests/test_phase61_memory_tool.py` created with T-61.32, T-61.33; both fail (RED).
- **Prerequisites:** P61.1.2 through P61.11.2 (needs the full store, trust, transport, and ADR groundwork in place, since `MemoryTool` is the surface over all of it).
- **Allowed Writes:** `tests/test_phase61_memory_tool.py`.
- **Actions:** Author T-61.32, T-61.33; run; confirm both RED.

#### P61.12.2 — GREEN: Implement `MemoryTool` and Register via the Real Two-Part CLI+MCP Path
- **Task ID:** P61.12.2
- **Binary Outcome:** `src/rush/tools/memory.py` implements `MemoryTool(ToolFn)` following `SessionContinuityTool`'s exact shape (§2.2); registered as both an MCP tool and a CLI command group; both T-61.32-33 pass.
- **Prerequisites:** P61.12.1 RED.
- **Allowed Writes:** `src/rush/tools/memory.py`, `src/rush/tools/__init__.py` (add `MemoryTool()` to `ALL_TOOLS`, alongside `SessionContinuityTool()`), `src/rush/catalog.py` (add a `"memory": ToolSpec(...)` entry to `TOOL_SPECS`, matching the `"continuity"` entry's shape at `catalog.py:115`), `src/rush/cli.py` (add `"memory"` to the exclusion set at `cli.py:1201-1208`, and add a new `@cli.group(name="memory")` with `ask`/`write`/`promote`/`list`/`recall` subcommands, mirroring `@cli.group(name="session")` at `cli.py:1878` and its subcommands at `cli.py:1934-2009`).
- **Actions:**
  1. Implement `MemoryTool(ToolFn)`, `name = "memory"`, `__call__` accepting `operation: Literal["ask","write","promote","list","recall"]` plus operation-specific kwargs, mirroring `SessionContinuityTool`'s parameter style.
  2. Return `ToolResultV1` from every operation, `status="skipped"` for denied/absent cases (T-61.33).
  3. Add `MemoryTool()` to `ALL_TOOLS` in `src/rush/tools/__init__.py` — wires the MCP side (`register_all_tools` at `mcp.py:327` registers `rush_memory` via `make_tool_wrapper`).
  4. Add a `"memory"` entry to `TOOL_SPECS` in `src/rush/catalog.py`, matching `"continuity"`'s fields (`catalog.py:115`).
  5. Add `"memory"` to the exclusion set at `cli.py:1201-1208`, then add `@cli.group(name="memory")` with `ask`/`write`/`promote`/`list`/`recall` subcommands, each constructing `MemoryTool()` and calling it with the matching `operation=` kwarg — following `@cli.group(name="session")` (`cli.py:1878`, subcommands at `1934-2009`) exactly.
  6. Run `pytest tests/test_phase61_memory_tool.py -v`, confirm both GREEN.

---

### P61.13 — Comprehensive Documentation & Governance Sync

#### P61.13.1 — VERIFY/DOCS: Synchronize All 71 Documentation Files (§8.2)
- **Task ID:** P61.13.1
- **Binary Outcome:** All 71 files listed in §8.2 Groups A through D are updated; Group F's 280 files are confirmed still correctly requiring no change (re-run the grep sweep once more post-implementation, since new code may have introduced new stale references no pre-implementation sweep could have found).
- **Prerequisites:** P61.1.2 through P61.12.2 all GREEN.
- **Allowed Writes:** all 71 files listed in §8.2 Groups A-D, plus `governance/remediation-phase-61.toml`, `docs/phase-plans/phase-61-implementation-evidence.md` (final update), `docs/developer/backlog.md`, `docs/phase-plans/README.md`.
- **Actions:**
  1. Apply Group A's substantive rewrites (13 files).
  2. Apply Group B's targeted fixes (7 files) and Group B2's evidence-doc notes (4 files).
  3. Apply Group C's cross-cutting reference updates (7 files) and Group C2's remaining cross-cutting updates (13 files).
  4. Apply Group D's single boilerplate-paragraph replacement across all 41 files, verifying byte-identical replacement text in each (script this rather than hand-editing 41 times, to guarantee identical text — use a Python script reading the old paragraph, replacing with the new one, across the enumerated file list; this script is throwaway tooling, not a new dependency).
  5. Verify Group E's 5 root/nested pairs both actually changed (diff each pair post-edit).
  6. Re-run the full 353-file grep sweep from §2 with updated search terms (add `TypedArtifactStore`, `trust_tier`, `MemoryTool` alongside the original 14 term list) to catch anything the original sweep couldn't have anticipated; add any newly-found stale file to this task before closing it — do not close with a partial sweep.
  7. Add the missing Phase 60 row and the new Phase 61 row to `docs/developer/backlog.md` (§8.1 item 13).
  8. Add the Phase 61 row to `docs/phase-plans/README.md`'s index table.
  9. Create `governance/remediation-phase-61.toml` documenting this phase's 36 contract tests and their closure, following the schema in §2.2 (`id, title, owner_phase, severity, release_blocker, red_task, green_task, target_seam, test_file, test_function, predecessor, docs_owner, status`) — even though this phase closes no `R-xxx` finding, using the identical schema keeps this phase's own record queryable the same way (and is itself informed by enhancement-idea bullet "Rush's own fix-lifecycle schema is directly reusable for decision/failure memory records" — this phase eats its own dog food here).
  10. Finalize `docs/phase-plans/phase-61-implementation-evidence.md` with all task evidence notes collected during P61.0-P61.13.

---

## 10. Final Verification and Delivery Gate

```bash
# 1. Run all 36 focused Phase 61 contract tests
python -m pytest tests/test_phase61_store.py tests/test_phase61_trust.py tests/test_phase61_migration.py \
  tests/test_phase61_episodic.py tests/test_phase61_handoff.py tests/test_phase61_domain_knowledge.py \
  tests/test_phase61_skill_pattern.py tests/test_phase61_transport.py tests/test_phase61_memory_tool.py \
  tests/test_phase61_adr.py -v

# 2. Run regression suites for every modified module
python -m pytest tests/ -k "preference or invariant or merkle or checkpoint or failure_ledger or \
  patch_memory or flight_recorder or tamper or continuity or session_memory or mistake" -q

# 3. Run complete test suite — record final count against P61.0.1's baseline, confirm baseline + 36
python -m pytest tests/ -q

# 4. Lint and format
ruff check src/rush/memory/ src/rush/tools/memory.py src/rush/hook/tamper_detector.py \
  src/rush/patch/memory.py src/rush/tools/flight_recorder.py src/rush/continuity/receipts.py tests/
ruff format --check src/rush/memory/ src/rush/tools/memory.py tests/

# 5. Git hygiene
git diff --check
git diff --name-only
git status --short --branch
```

---

## 11. Exit Checklist and Successor Evidence

- [ ] Every RED task's test actually failed for the stated reason before its paired GREEN task began.
- [ ] `TypedArtifactStore` runs in WAL mode; `PRAGMA journal_mode` returns `"wal"`.
- [ ] No memory write ever enters at `trust_tier="STATED"` directly; promotion is the only path.
- [ ] Every write passes through `sanitize_value()` inside `TypedArtifactStore.write()` itself.
- [ ] Every `STATED` record is signed at promotion and re-verified at recall; a mismatch raises.
- [ ] Every recalled record is scanned for Trojan Source characters before returning to the caller.
- [ ] Staleness (merkle content-hash mismatch) is flagged on recall, never silently served as fresh.
- [ ] All 8 satellite files/stores (`preference_store.py`, `invariant_graph.py`, `merkle_invalidator.py`, `checkpoint_journal.py`, `failure_ledger.py`, `FlightRecorder`'s flights JSONL, and `HookTamperDetector`'s `.rush/hook_signatures.json`) have their canonical data in the unified store; the old satellite files are renamed `.migrated`, never deleted, per Invariant 5. `PatchMemoryStore`'s data is migrated into the store but its physical file, `.rush/cache.db`, is deliberately left untouched (never renamed) because `ResultCache` shares that same file for an unrelated purpose.
- [ ] `continuity/receipts.py` emits `trust_tier`, not the old binary `"quarantined"` flag.
- [ ] The corroboration-threshold check uses dedicated `count_corroboration()` code in `trust.py`, not `MultiModelConsensusReconciler` (which cannot represent an Optional `symbol_ref` — see §6.2 correction).
- [ ] The transport dispatcher selects tiers per-tool, never one global tier for a whole session.
- [ ] `MemoryTool` is present in `ALL_TOOLS`/`TOOL_SPECS` (MCP side, `rush_memory` via `make_tool_wrapper`) and has a `@cli.group(name="memory")` (CLI side) — the same two-part registration `SessionContinuityTool` uses, not `make_tool_wrapper` alone.
- [ ] ADR-0049 exists, `Status: Accepted`; ADR-0030, ADR-0018, ADR-0020, ADR-0041 each carry a superseded-pointer note; no ADR's original substance was edited.
- [ ] All 71 files from §8.2's Groups A-D are updated; the post-implementation re-sweep (§9 P61.13.1 step 6) found no additional stale files, or found and fixed them before closing.
- [ ] `docs/developer/backlog.md` has both the previously-missing Phase 60 row and the new Phase 61 row.
- [ ] `docs/phase-plans/README.md`'s index table includes Phase 61.
- [ ] `governance/remediation-phase-61.toml` created, documenting all 36 contract tests.
- [ ] Zero third-party dependencies introduced.
- [ ] Full pytest suite passes at baseline + 36 (exact numbers recorded in `docs/phase-plans/phase-61-implementation-evidence.md`).
- [ ] Successor scope (Phase 62+ enhancement-idea backlog, from the synthesis doc's 35 catalogued ideas) is unblocked — this phase's `TypedArtifactStore`, trust tiers, and `MemoryTool` are the foundation those ideas attach to, none of them implemented yet.
