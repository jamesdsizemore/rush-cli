# Rush continuity, memory, and token-efficiency execution plan

Status: implementation plan, not implemented behavior  
Repository inspected: `C:/Users/james/developer/rush-cli`  
Research cut-off: 2026-08-23  
Companion strategy: `research/rush-strategic-opportunity-map-2026-08-23.md` (left unchanged)

## 1. How to read this document

This plan uses four evidence labels deliberately:

- **[Repo]** verified in the current repository or project environment.
- **[External]** verified in a directly linked primary source.
- **[Proposed]** architecture or product behavior recommended here but not yet implemented.
- **[Assumption]** a decision that must be confirmed by the maintainer or a spike.

The word **must** describes an acceptance condition for proposed work, not current behavior. Exact paths are relative to the repository root unless an absolute path is shown.

## 2. Executive decision

**[Proposed] Rush should build a Universal Continuation Engine whose unit of value is a resumable engineering objective, not a provider transcript.** Any cooperating agent or provider should be able to take over an episode with the objective, governing instructions, repository frontier, decisions, attempted work, evidence, blockers, proof obligations, and authorized recovery handles needed to continue correctly.

The engine has three deliberately separate layers:

1. **Session Archive** — the durable, provider-neutral, ordered record of all *available and permitted* events and evidence. It is lossless after mandatory secret redaction, and it records explicit gaps when a source cannot be captured.
2. **Continuation State** — the provider-neutral materialized frontier: what is currently true, decided, attempted, unresolved, and required next. It is derived from archive events and can always be rebuilt.
3. **Resume Projection** — a target-specific, token-budgeted rendering for the next provider or agent. It contains stable prefixes, selected evidence, delta events since the target's acknowledged cursor, recovery handles, and an omission manifest.

This resolves the strategic report's largest inconsistency. Rush does **not** choose between complete history and token reduction. It preserves a canonical local archive, then sends the smallest defensible projection by default. Full replay is a diagnostic or recovery mode, never the default prompt.

### Product outcomes

- A user can stop in one provider and resume in another without manually reconstructing the task.
- The receiving agent can tell what is authoritative, what is inferred, what changed in the repository, what failed, and what evidence is missing.
- Repeated resumes and long sessions consume fewer tokens through stable prefixes, delta delivery, typed compression, and lazy recovery.
- Memory is inspectable, correctable, exportable, and deletable from the CLI and through the same shared MCP implementation.
- A resumed agent must prove alignment with current repository state before it acts on stale conclusions.

### Non-goals

- No UI or hosted-only control plane.
- No attempt to extract hidden chain-of-thought or provider-private state.
- No claim that every provider exposes complete transcripts, tool calls, or native session IDs.
- No replacement for provider-native session resume. Native resume may be used by an adapter, but cross-provider continuation remains Rush-owned.
- No automatic Git hooks, history rewriting, tags, publishing, or package upload.
- No vector database or new model dependency in the first four phases.

## 3. Consistency corrections to the strategic report

| Report ambiguity | Binding interpretation for implementation |
|---|---|
| “Full observable session record” versus selective context | Archive every available, permitted, redacted event; project selectively. A projection never claims to be the archive. |
| Provider-neutral bundle versus provider-specific content | A `ContinuationBundle` contains a provider-neutral core plus optional named adapter envelopes. Target-specific prompt syntax is never stored in the core. |
| Session, episode, and bundle used interchangeably | A provider session is one native interaction stream. An episode is one objective and may span many provider sessions. A bundle is an immutable export of one episode at one archive cursor. |
| Source instructions moved unchanged between providers | Instruction text and provenance are preserved, but source `system`/`developer` authority is marked `historical_nonportable`. The destination provider's system policy remains authoritative. |
| Complete history versus redaction before persistence | “Complete” is qualified as complete among provider-exposed, locally observable, user-permitted, non-secret content. Redactions and unavailable spans become typed gap events. |
| Rejection/failure evidence versus aggressive compaction | Negative evidence is structured and pinned in continuation state; verbose payloads move behind recovery handles. Rejection identity, reason, scope, and invalidation condition stay visible. |
| Adapter-first roadmap | The archive, state reducer, projection compiler, and conformance fixtures land before provider adapters. Adapters map into a stable core, not vice versa. |
| Handoff quality missing from kill criteria | Continuation accuracy, stale-action rate, recovery rate, token reduction, and time-to-first-correct-action are release gates. |

## 4. Verified repository baseline

### 4.1 Contracts and transport

- **[Repo]** `pyproject.toml` declares Python `>=3.12,<3.13`, Click, Rich, MCP, `tiktoken`, `tree-sitter`, `sqlglot`, Pillow, Cryptography, and ruamel.yaml. The checked environment reports MCP `1.29.0`, while the project declaration currently pins `1.28.1`; compatibility tests must use the declared lock and report the runtime mismatch rather than silently depending on 1.29 behavior.
- **[Repo]** `src/rush/tools/base.py::Finding`, `ToolResult`, and `ToolFn` define the canonical result contract. `ToolResult` supports `ok`, `warn`, `fail`, `error`, and `skipped`, plus findings, metrics, artifacts, and metadata.
- **[Repo]** `src/rush/tools/__init__.py::ALL_TOOLS` is the catalog-backed executable registry used by both transports.
- **[Repo]** `src/rush/cli.py::_run_tool` calls a tool's shared `run` implementation and renders the result.
- **[Repo]** `src/rush/mcp.py::build_server` registers `ALL_TOOLS`, but also defines many session/context/memory wrappers inline. Those wrappers duplicate transport logic and contradict `docs/ARCHITECTURE.md`'s “two transports, one implementation layer” claim.
- **[Repo]** `tests/test_mcp.py` executes the real stdio server and checks tool discovery, schemas, payloads, and stdout cleanliness. It is the model for all new MCP parity tests.

### 4.2 Existing state and memory components

| Current component | Verified behavior | Reuse decision |
|---|---|---|
| `src/rush/session_memory.py::SessionMemoryManager` | Stores up to 50 tool summaries in `.rush/session-memory.json`; renders XML for MCP. No provenance, episode identity, dependency invalidation, or secret redaction. | Read-only migration source; replace as canonical continuity store after parity. |
| `src/rush/memory/checkpoint_journal.py::CheckpointJournal` | Saves named JSON snapshots under `.rush/sessions` containing metadata and file contents. | Keep as legacy import source; do not call it cross-provider memory. |
| `src/rush/tools/flight_recorder.py::FlightRecorder` | Appends timestamp, event type, and arbitrary payload to `.rush/sessions/flights/<id>.jsonl`. | Refactor behind typed event ingestion; prohibit raw arbitrary payload persistence. |
| `src/rush/memory/failure_ledger.py::FailureLedger` | Stores patch, error, and fingerprint in SQLite. Raw patch/error text is not passed through `SecretRedactor`. | Migrate records through redaction; preserve negative evidence semantics. |
| `src/rush/memory/invariant_graph.py::InvariantGraph` | Stores rule descriptions/rationales/status in JSON. | Promote valid entries to typed instruction/claim records with provenance. |
| `src/rush/memory/merkle_invalidator.py::MerkleInvalidator` | Hashes file content and reports whether one path changed. | Reuse hashing idea; replace flat manifest with evidence dependency edges. |
| `src/rush/memory/preference_store.py::PreferenceStore` | Provides `get`, `set`, `delete`, and `list_all` over `.rush/preferences.json`. | Keep user preferences distinct from episode memory; fix callers before integration. |
| `src/rush/memory/mistake_miner.py::MistakeMiner` | Parses revert commits and recent Git messages. | Treat output as proposed learning evidence, never authoritative memory. |
| `src/rush/cache.py::ResultCache` | SQLite cache keyed by tool/config/content hashes. | Keep separate: an evictable result cache is not durable memory. |
| `src/rush/token_economy/ccr_store.py::CCRStore` | Content-addressed chunk storage in `.rush/cache/ccr.db`; returns recovery markers. | Reuse recovery-handle format concept, not the evictable cache as durable archive. |

### 4.3 Existing token capabilities and gaps

- **[Repo]** `src/rush/token_economy/content_router.py::ContentRouter` classifies content and counts tokens; `FastBPETokenCounter`, AST compressors, `PromptCompressor`, `ToonEncoder`, `Paginator`, and result distillers provide useful local primitives.
- **[Repo]** `src/rush/token_economy/stale_sweeper.py::StaleSweeper` destructively replaces older text with its first line and character count. It has no recovery handle and therefore cannot be used for trustworthy continuation.
- **[Repo]** `src/rush/token_economy/context_packer.py::ContextPacker` reads one file, applies AST skeletonization, wraps XML, and truncates by lines. It does not implement the graph/PageRank behavior claimed by its documentation.
- **[Repo]** `src/rush/token_economy/telemetry.py::TokenTelemetry` stores raw/compressed counts and duration, but has no provider, model, episode, projection, cache-read, quality, recovery, or actual usage dimensions. Its cost calculation is hard-coded.
- **[Repo]** `src/rush/token_economy/cache_aligner.py::CacheAligner` pads a prefix to a fixed threshold. That is not sufficient for provider caching because provider rules differ and cache success must be read from provider usage telemetry.
- **[External]** OpenAI prompt caching requires exact prefix matches and recommends stable instructions/tools/context before variable content: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
- **[External]** Anthropic caching operates on the full ordered prefix and has provider-specific breakpoints, lookback, TTL, minimum, and usage fields: [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching).
- **[Proposed]** Rush must optimize projections in a provider-neutral way first, then let adapters arrange stable prefixes and record actual cache telemetry. It must never promise cache hits from padding alone.

### 4.4 Configuration, docs, safety, and current inconsistencies

- **[Repo]** `src/rush/config.py::RushConfig` parses only project, tool, review, cache, and log-level fields. `docs/CONFIGURATION.md` and `docs/CONFIG_SCHEMA.md` document memory/context tables that the parser ignores.
- **[Repo]** `src/rush/safety/redactor.py::SecretRedactor.redact_text` is the mandatory existing primitive for text before persistence or rendering.
- **[Repo]** `src/rush/permissions.py::ExecutionPermissions`, `check_permissions`, and `build_execution_metadata` cover execution capabilities, but not memory capture/export/delete or recovery access.
- **[Repo]** `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard` should remain the authority for repository-local paths.
- **[Repo]** `src/rush/cli.py::context_persona_cmd` calls `PreferenceStore.set_preference/get_preference`, but the store exposes `set/get`. This is a verified defect and a warning against building new memory behavior in transport wrappers.
- **[Repo]** the test suite baseline observed during research was 749 passed and one unrelated version assertion failure: `tests/test_skeleton.py::test_version_string` expects 0.2.0 while `pyproject.toml` declares 0.3.0. The continuity work must not alter release versions to hide that failure.

## 5. Canonical domain model

### 5.1 Boundaries and cardinality

| Object | Definition | Cardinality and identity |
|---|---|---|
| Workspace | The validated Git/project root and its Rush-local state. | Stable local `workspace_id`; current root and Git common-dir fingerprint are attributes, not identity by themselves. |
| Objective | The user's requested outcome and acceptance conditions. | Versioned within one episode; user correction appends a new version. |
| Episode | The durable unit another agent resumes. | One objective lineage; spans one or more provider sessions; `episode_id` is Rush-generated. |
| Provider session | One source-native conversation/run connection. | Belongs to at most one episode attachment at a time; provider/native ID may be absent. |
| Event | One ordered observation, instruction, action, result, decision, correction, or gap. | Immutable; monotonic per-episode `sequence`; UUID4 `event_id`; idempotency key for adapter retries. |
| Continuation state | Deterministic materialized frontier at an archive cursor. | One rebuildable snapshot per `(episode_id, cursor, reducer_version)`. |
| Projection | Token-budgeted rendering for a target capability profile. | Immutable per compiler version, cursor, target, budget, and policy hash. |
| Bundle | Portable export of the core plus optional adapter envelopes. | Immutable, checksummed snapshot of an episode at one cursor. |

Python 3.12 does not provide `uuid.uuid7`; UUID4 plus a transaction-assigned sequence avoids a new dependency. Ordering is defined only by the sequence, never by timestamps or UUID lexical order.

### 5.2 Capture truth states

Every potential source span is represented by exactly one status:

- `captured_redacted`: available content stored after secret redaction.
- `captured_metadata_only`: policy permits metadata but not content.
- `source_unavailable`: the provider/transport did not expose it.
- `capture_disabled`: the user or repository policy disabled the class.
- `redacted_secret`: content was replaced with a typed redaction marker before persistence.
- `adapter_error`: expected capture failed; error is sanitized and retryable.
- `projection_omitted`: content exists in the archive but was intentionally left out of one projection. This is projection metadata, not an archive gap.

These states prevent “full history” from becoming a false claim.

### 5.3 Instruction authority

**[Proposed]** Each instruction record has `authority`, `scope`, `source`, `portable`, `effective_from`, `supersedes`, and optional `expires_when` fields.

Precedence for a resumed task is:

1. destination system and developer policy supplied by the current runtime;
2. current repository instructions such as `AGENTS.md`, resolved for the target path;
3. current explicit user objective/corrections;
4. portable task instructions from the episode;
5. historical non-portable source-system instructions, retained as evidence only;
6. inferred preferences and proposed learnings, which may never override 1–4.

The projection compiler emits instruction conflicts instead of silently choosing when precedence is not sufficient (for example, two current user requirements that cannot both be satisfied).

### 5.4 Storage and transaction rules

- **[Proposed]** Canonical state lives in `.rush/memory/rush.db`; durable large redacted blobs live under `.rush/memory/blobs/sha256/<prefix>/<digest>`. Cache artifacts remain under `.rush/cache` and may be deleted without damaging memory.
- **[Proposed]** `PRAGMA foreign_keys=ON` is set on every connection. SQLite disables foreign-key enforcement by default unless enabled per connection: [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html).
- **[Proposed]** schema migrations use `PRAGMA user_version`, canonical JSON text, `BEGIN IMMEDIATE` only around short sequence-allocation/write transactions, a bounded busy timeout, and retry with jitter. See [SQLite transactions](https://www.sqlite.org/lang_transaction.html) and [application-owned `user_version`](https://www.sqlite.org/pragma.html#pragma_user_version).
- **[Repo]** the project interpreter currently reports SQLite 3.50.4.
- **[External]** WAL permits concurrent readers but only one writer, requires same-host shared memory, and SQLite documents a rare corruption bug fixed in 3.51.3 with backports: [SQLite WAL](https://www.sqlite.org/wal.html).
- **[Proposed]** phase 1 uses rollback-journal mode by default. A WAL spike may enable it only after testing the exact runtime version, backport status, filesystem type, multi-process writer load, crash recovery, and checkpoint policy. Never use this DB on a network filesystem.
- **[Proposed]** FTS5 is feature-detected at runtime; exact fields and bounded `LIKE` fallback remain functional if unavailable. FTS is an index, never the source of truth: [SQLite FTS5](https://www.sqlite.org/fts5.html).

### 5.5 Core persisted schema

The first migration creates these tables. Field names are part of the proposed v1 bundle contract even if Python types change during review.

| Table | Required fields | Purpose |
|---|---|---|
| `workspaces` | `workspace_id`, `created_at`, `root_hint`, `git_common_dir_hash` | Local identity without exporting absolute paths by default. |
| `episodes` | `episode_id`, `workspace_id`, `status`, `created_at`, `updated_at`, `head_sequence`, `objective_version` | Resume unit and optimistic-concurrency head. |
| `provider_sessions` | `session_id`, `episode_id`, `provider`, `adapter`, `native_id`, `capabilities_json`, `started_at`, `ended_at` | Source/target attachment and capability evidence. |
| `events` | `event_id`, `episode_id`, `sequence`, `type`, `actor`, `authority`, `capture_status`, `payload_json`, `payload_hash`, `source_session_id`, `idempotency_key`, `created_at` | Immutable ordered archive. Unique `(episode_id, sequence)` and `(source_session_id, idempotency_key)`. |
| `event_dependencies` | `event_id`, `dependency_kind`, `dependency_key`, `observed_digest` | Files, symbols, config, tools, engines, instructions, or upstream claims that affect validity. |
| `claims` | `claim_id`, `episode_id`, `claim_type`, `statement`, `status`, `confidence`, `authority`, `valid_from_sequence`, `invalidated_at_sequence` | Typed propositions; never overwrite contradictions. |
| `claim_evidence` | `claim_id`, `event_id`, `span_json`, `support` | Source spans supporting, opposing, or qualifying claims. |
| `obligations` | `obligation_id`, `episode_id`, `description`, `status`, `required_evidence_json`, `owner_session_id`, `updated_sequence` | What must be proven before completion. |
| `projections` | `projection_id`, `episode_id`, `cursor`, `target_json`, `policy_hash`, `compiler_version`, `budget_tokens`, `estimated_tokens`, `manifest_json`, `created_at` | Reproducible resume rendering metadata. |
| `projection_items` | `projection_id`, `ordinal`, `source_kind`, `source_id`, `render_mode`, `estimated_tokens`, `omission_reason`, `recovery_handle` | Exact inclusion/omission accounting. |
| `receipts` | `receipt_id`, `episode_id`, `action_event_id`, `result_event_id`, `command_hash`, `exit_code`, `artifact_json`, `environment_json` | Verifiable action/result pairing. |
| `consumers` | `consumer_id`, `episode_id`, `adapter`, `ack_sequence`, `last_projection_id`, `updated_at` | Delta resume cursor; scoped to one target identity. |
| `tombstones` | `object_type`, `object_id_hash`, `deleted_at`, `reason` | Prevent accidental re-import after user deletion without retaining content. |

Large content is stored only after redaction. Event payloads reference it by a `rush-blob://sha256/<digest>` handle. Export rewrites local handles into bundle-relative paths and never exposes `.rush` absolute paths.

## 6. Feature specifications

### F1. Session Archive and capture gateway

**Classification:** **[Proposed]**, with primitives in `FlightRecorder`, `SessionMemoryManager`, and `SecretRedactor` **[Repo]**.

**User problem and users.** Developers switching providers, machines, worktrees, or agents lose the actual work trail or receive an unverifiable summary. The user needs one local record they control and can inspect.

**Agent problem.** A receiving agent cannot distinguish observed actions from narration, retries from new actions, unavailable history from omitted context, or old repository facts from current facts.

**User interaction.** `rush memory episode start --objective <text>` starts an explicit episode; `rush memory capture --episode <id> --from <adapter|jsonl>` imports exposed events; `rush memory inspect <id> --timeline` shows sanitized events and gaps; `rush memory episode close <id>` closes capture but does not declare success. Capture is opt-in by configuration and explicit episode start in the first release.

**Agent interaction.** MCP tools `rush_episode_start`, `rush_event_append`, `rush_episode_inspect`, and `rush_episode_close` call the same functions as the CLI. Agents append structured event types such as `objective.set`, `instruction.observed`, `plan.updated`, `tool.called`, `tool.result`, `decision.made`, `claim.proposed`, `obligation.updated`, `correction.user`, and `capture.gap`. MCP resources `rush://episodes/{episode_id}/state` and `rush://episodes/{episode_id}/events{?after,limit}` are added only after an SDK compatibility test.

**Exact behavior and lifecycle.** Input is validated against an event-type schema; repository paths pass `WorkspaceBoundaryGuard`; text passes `SecretRedactor` before hashing or persistence; the store allocates a sequence in one transaction; idempotency keys turn adapter retries into the existing event; the reducer is notified after commit. Events are immutable. Corrections append superseding events. A failed append returns a canonical `ToolResult` with `status=error` and no partial blob.

**Token efficiency and correctness.** The archive itself does not reduce tokens; it makes aggressive projection safe. Exact event types eliminate repeated prose, payload blobs are lazy, and consumer cursors allow delta delivery. Correctness improves because the projection can cite ordered source IDs and report capture gaps.

**Roles.** Rush owns validation, ordering, redaction, persistence, and inspection. Adapters own mapping exposed source events into the schema. Providers remain the source for native IDs and usage. Users own capture policy, correction, export, and deletion.

**Differentiation.** This is not transcript ingestion marketed as memory. It is an auditable engineering event archive whose incomplete visibility is explicit and whose state can be rebuilt.

**Current files and symbols.** Extend `src/rush/safety/redactor.py::SecretRedactor`; read and migrate `src/rush/tools/flight_recorder.py::FlightRecorder`, `src/rush/session_memory.py::SessionMemoryManager`, and `src/rush/memory/checkpoint_journal.py::CheckpointJournal`; use `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard`; return `src/rush/tools/base.py::ToolResult`; call from `src/rush/cli.py` and `src/rush/mcp.py::build_server`; update `tests/test_mcp.py` without weakening stdout assertions. `src/rush/cache.py::ResultCache` remains unchanged and non-authoritative.

**New files and APIs.** `src/rush/memory/models.py` defines validated dataclasses/enums and `EventAppend`; `src/rush/memory/database.py::MemoryDatabase` owns connections/migrations; `src/rush/memory/event_store.py::EventStore.append/list_after/get_episode`; `src/rush/memory/blob_store.py::BlobStore.put/read/delete_unreferenced`; `src/rush/memory/migrations/0001_core.sql`; `src/rush/tools/continuity.py` exposes shared ToolResult-returning operations; `tests/test_memory_database.py`, `tests/test_event_store.py`, `tests/test_continuity_transport_parity.py`, and `tests/fixtures/continuity/events-v1.jsonl` validate them.

**Dependencies.** `SecretRedactor`, workspace boundary, config, canonical result, SQLite migration. F1 is the prerequisite for every later feature.

**Validation.** Redaction-before-hash test; idempotent concurrent append test; monotonic sequence test; crash between blob temp write and DB commit; malformed adapter payload; source-unavailable gap; CLI/MCP semantic parity; stdio stdout cleanliness; database reopen/migrate; Windows path traversal; deletion of an unreferenced blob.

**Risks and controls.** Sensitive persistence is controlled by mandatory redaction and capture allowlists. DB contention uses short transactions and bounded retry. Provider incompleteness produces gaps. Disk growth uses visible retention metrics and user-triggered pruning, never silent archive eviction.

### F2. Continuation State and instruction/intent compiler

**Classification:** **[Proposed]**; current partial rule/preference stores are **[Repo]**.

**User problem and users.** A handoff that merely repeats chat leaves the next agent to rediscover the objective, constraints, acceptance tests, and current point of work.

**Agent problem.** Models need a compact, unambiguous frontier and authority order. They must not treat source-provider system prompts, inferred preferences, or stale `AGENTS.md` contents as current commands.

**User interaction.** `rush memory state <episode>` displays objective, constraints, decisions, rejected paths, blockers, proof obligations, repository frontier, and conflicts. `rush memory correct <episode> --field objective --value ...` appends a correction. `rush memory rules <episode> --explain` shows effective authority and excluded historical instructions.

**Agent interaction.** `rush_state_get` returns structured JSON plus source event IDs. `rush_state_ack` records the consumer cursor without changing facts. Before acting, an agent calls `rush_resume_prepare`; a hard instruction conflict returns `warn` with findings and an abstention recommendation.

**Exact behavior and lifecycle.** A deterministic reducer consumes immutable events in sequence. Each reducer version emits `ContinuationStateV1` with objective versions, effective instructions, plans, decisions, attempts, negative evidence, open obligations, worktree/repo anchors, and gap summary. State is cached by cursor but rebuildable. Corrections supersede fields; contradictions coexist until a higher-authority event resolves them. Repository instructions are reread at resume time and recorded as new observations if their digest changed.

**Token efficiency and correctness.** Typed frontier fields replace transcript recap. Only current values and pinned negative evidence enter the core projection; superseded detail remains recoverable. The stable instruction/objective prefix receives its own digest so adapters can preserve cacheable ordering. Correctness comes from deterministic reduction and authority-aware conflicts.

**Roles.** Rush reduces and resolves formal precedence; users correct objectives and conflicts; repository files supply current scoped instructions; adapters cannot upgrade source authority.

**Differentiation.** The state is a reproducible materialized view over evidence, not an LLM-generated summary silently promoted to truth.

**Current files and symbols.** Read `AGENTS.md`; extend `src/rush/agent_governance/agents_sync.py::AgentsMdSynchronizer` only for scoped discovery, not rewriting; extend `src/rush/agent_governance/rule_parity.py::RuleParityChecker`; migrate valid `src/rush/memory/invariant_graph.py::InvariantGraph` entries; keep `src/rush/memory/preference_store.py::PreferenceStore` as lower-authority user preferences and fix `src/rush/cli.py::context_persona_cmd`; use `src/rush/codegraph/grounding.py::GroundingVerifier` only as optional repository evidence, not as the reducer.

**New files and APIs.** `src/rush/memory/state.py::ContinuationStateV1`; `src/rush/memory/reducer.py::StateReducer.reduce`; `src/rush/memory/authority.py::InstructionResolver.resolve`; `src/rush/memory/repository_frontier.py::RepositoryFrontier.capture/compare`; `tests/test_state_reducer.py`, `tests/test_instruction_authority.py`, and fixtures covering correction, conflict, stale rules, and missing history.

**Dependencies.** F1 archive; Git snapshot parsing; rule discovery; no model call.

**Validation.** Golden replay is deterministic; correction never deletes the old event; destination policy outranks historical source policy; nested repository instruction scopes resolve correctly; changed rules invalidate the state cache; contradictory user instructions cause explicit abstention; state rebuild equals cached state.

**Risks and controls.** An overly rigid schema can omit nuance, so fields retain source handles and `notes` with strict size limits. Authority bugs are high impact, so resolver fixtures are release gates and no adapter-specific authority enters core code.

### F3. Evidence ledger, receipts, freshness, and dependency invalidation

**Classification:** **[Proposed]**, consolidating partial repository capabilities **[Repo]**.

**User problem and users.** Users cannot trust a resumed agent that says “tests passed” or “this symbol behaves this way” without knowing when, where, and against which repository state that was true.

**Agent problem.** A claim can become stale after a file, configuration, dependency, tool, engine, or instruction change. Transcript recency is not validity.

**User interaction.** `rush memory evidence <episode> [--claim <id>]` shows supporting/opposing spans, receipts, freshness, and invalidators. `rush memory verify <episode> --open` reruns only authorized proof obligations through existing Rush tools. No action is rerun without normal permissions.

**Agent interaction.** Tool results can append a `receipt.recorded` event with sanitized command hash, engine/version, exit code, artifacts, and repository anchor. `rush_claim_get` returns `valid`, `stale`, `contradicted`, `unverified`, or `invalid`, never a bare confidence score. `rush_claim_refresh` produces a plan or structured `skipped` result when an engine is absent.

**Exact behavior and lifecycle.** Claims are proposed with typed authority and evidence spans. Promotion rules differ by type: user decisions require a user event; repository facts require current file/symbol evidence; test claims require a matching receipt; external claims require URL and retrieval time; inferred preferences stay proposed. Dependency edges store observed digests. A changed dependency appends invalidation events and marks affected claims stale; it never erases them. Contradictory claims remain linked and visible.

**Token efficiency and correctness.** Projections carry compact claim IDs, status, short statements, and only the evidence necessary for the next action. Verbose logs stay behind handles. Invalidation prevents wasted tokens and actions based on obsolete summaries. Selective proof refresh avoids rerunning the whole suite.

**Roles.** Existing Rush quality tools create canonical results; the evidence ledger indexes them; Git and filesystem observations anchor repository facts; users authorize reruns; receiving agents must abstain when required evidence is stale or unavailable.

**Differentiation.** This is evidence-bearing operational memory, not semantic recall based on similarity alone.

**Current files and symbols.** Extend `src/rush/tools/base.py::ToolResult` usage through metadata rather than changing required fields; integrate `src/rush/tools/common.py::run_engine`, `skipped_result`, and `normalize_findings`; extend `src/rush/memory/merkle_invalidator.py::MerkleInvalidator`; migrate `src/rush/memory/failure_ledger.py::FailureLedger` after redaction; use `src/rush/codegraph/store.py::CodeGraphStore` and `src/rush/codegraph/grounding.py::GroundingVerifier` when `.codegraph` exists; parse Git with `git status --porcelain=v2 -z`, whose stable machine format is documented by [Git status](https://git-scm.com/docs/git-status).

**New files and APIs.** `src/rush/memory/claims.py::ClaimLedger.propose/promote/contradict`; `src/rush/memory/receipts.py::ReceiptRecorder.from_tool_result`; `src/rush/memory/dependencies.py::DependencyIndex.changed/affected_claims`; `src/rush/memory/freshness.py::FreshnessEvaluator.evaluate`; `tests/test_claim_ledger.py`, `tests/test_receipts.py`, `tests/test_dependency_invalidation.py`, and `tests/test_git_frontier.py`.

**Dependencies.** F1 events, F2 state, existing tool results, Git and optional CodeGraph. Missing quality engines remain structured `skipped` evidence.

**Validation.** File edit stales dependent claim but not unrelated claim; tool-version change stales a receipt; deleted file becomes invalid, not merely stale; contradictory claims both render; secret output is redacted before receipt storage; `-z` filenames with spaces/newlines parse safely; missing engine returns `skipped`; no command is run during read-only inspection.

**Risks and controls.** Dependency graphs can over-invalidate, so edges record cause and metrics track false refreshes. They can under-invalidate, so completion-critical claims require explicit dependency coverage or an `unverified` status.

### F4. Proof obligations, failure classification, and closed-loop recovery

**Classification:** **[Proposed]**, using existing tools and failure history **[Repo]**.

**User problem and users.** A different agent may repeat failed fixes, declare completion from narration, or continue after an environment/permission failure as if the code were wrong.

**Agent problem.** It needs durable negative evidence, typed failure classes, bounded retry policy, and explicit proof still required for the objective.

**User interaction.** `rush memory obligations <episode>` shows open, satisfied, waived-by-user, and blocked obligations. `rush memory attempt <episode> --explain <id>` shows why a retry is allowed or rejected. Waiving a proof requires an explicit user event and stays visible in exports.

**Agent interaction.** Before a materially similar retry, `rush_attempt_check` compares the proposed action with prior failures and their invalidation conditions. After an action, `rush_receipt_record` updates obligations. `rush_completion_check` returns `ok` only if mandatory obligations have fresh evidence; otherwise it returns `warn` or `fail` with next allowed actions.

**Exact behavior and lifecycle.** Failures are classified as `code`, `test_assertion`, `environment`, `permission`, `dependency_missing`, `transport`, `conflict`, `stale_context`, or `unknown`. A retry is allowed when inputs, relevant repository dependencies, environment capability, permissions, or strategy materially changed. Exact repetition without a changed condition is rejected and cited. Recovery is a bounded perceive-plan-act-observe loop whose maximum attempts and allowed actions come from configuration. Rush never grants permissions to itself.

**Token efficiency and correctness.** Compact failure fingerprints and invalidation conditions keep failed paths visible without replaying logs. The agent fetches the full receipt only when planning a materially different recovery. Proof obligations prevent token-saving summaries from dropping acceptance criteria.

**Roles.** Rush classifies deterministic metadata and enforces retry bounds; an agent proposes a recovery; the existing permission system authorizes execution; users waive or change acceptance conditions.

**Differentiation.** Closed-loop correction is grounded in observed state transitions and proof, not an “autonomous” label on a retry script.

**Current files and symbols.** Refactor `src/rush/memory/failure_ledger.py::FailureLedger`; use `src/rush/permissions.py::ExecutionPermissions`, `check_permissions`, and `build_execution_metadata`; use all catalog tools through `src/rush/tools/__init__.py::ALL_TOOLS`; keep `src/rush/tools/common.py::run_subprocess` redaction and output bounds; use `src/rush/capabilities.py::inspect_capabilities` and `build_plan` for engine availability.

**New files and APIs.** `src/rush/memory/obligations.py::ObligationStore`; `src/rush/memory/failures.py::FailureClassifier`; `src/rush/memory/retry_policy.py::RetryPolicy.evaluate`; `src/rush/memory/completion.py::CompletionEvaluator.evaluate`; `tests/test_obligations.py`, `tests/test_retry_policy.py`, `tests/test_completion_evidence.py`.

**Dependencies.** F1–F3, canonical tools, permissions, capabilities.

**Validation.** Same patch/same state is rejected; changed file permits reconsideration with reason; permission denial is not learned as a code failure; missing engine stays retryable after capability change; waived proof is visible; completion cannot pass on stale receipts; retry loop terminates at configured bound.

**Risks and controls.** Bad fingerprints could block valid work, so users can inspect and override with an append-only reason. Automated reruns may cost time, so default mode proposes and waits for normal authorization; no background or network action is introduced.

### F5. Reversible context projection and token accounting

**Classification:** **[Proposed]**, assembling existing token primitives **[Repo]**.

**User problem and users.** Long sessions and repeated handoffs are expensive and slow when each provider receives the entire transcript, yet opaque summaries can omit the exact fact that prevents a mistake.

**Agent problem.** A receiving agent needs the smallest context that preserves the objective, effective rules, repository frontier, negative evidence, and next proof obligations—and a safe way to retrieve omitted detail.

**User interaction.** `rush memory project <episode> --target generic --budget 12000` previews a projection, estimated tokens, coverage, and omissions. `--mode full` is an explicit diagnostic. `rush memory tokens <episode>` reports archive tokens, projection tokens, reduction ratio, recovery reads, provider cache reads/writes when available, and handoff-quality results; it does not fabricate dollar cost.

**Agent interaction.** `rush_resume_prepare` accepts a target capability profile and budget, returning structured sections plus text. `rush_recover <handle>` retrieves one authorized source object with provenance. `rush_resume_ack` advances the consumer cursor only after the receiving agent confirms that the projection was accepted.

**Exact behavior and lifecycle.** The compiler selects mandatory items first: objective, effective instructions, unresolved conflicts, current repo frontier, open proof obligations, active blockers, recent user corrections, and still-valid negative evidence. It then ranks supporting claims and recent events by task relevance, freshness, authority, dependency proximity, and estimated token cost. Type-specific renderers skeletonize code, tabulate findings, compact structured data, and summarize prose while retaining source IDs. Every omitted item receives a reason and recovery handle. A projection is immutable and reproducible from its compiler version and policy hash.

After the first projection, a consumer receives only events after `ack_sequence`, plus state fields whose digest changed. An unacknowledged projection never advances the cursor. If the repository frontier diverged, a new bootstrap section is forced even when the consumer cursor is current.

**Token efficiency and correctness.** The target is measurable reduction, not shorter-looking text: `(archive_estimated_tokens - projection_estimated_tokens) / archive_estimated_tokens`, actual input tokens when an adapter reports them, recovery frequency, and task-quality deltas. Stable instruction/tool/schema prefixes are separated from variable state to support provider caching. Full source remains recoverable locally. A projection fails closed if mandatory items exceed budget; it returns a budget finding rather than truncating them.

**Roles.** Rush selects and renders provider-neutral content; adapters report target tokenizer/capabilities and arrange provider-specific cache syntax; providers report actual usage when exposed; users set budgets and recovery permissions; agents choose recovery handles when evidence is insufficient.

**Differentiation.** Compression is reversible, evidence-addressed, and evaluated against continuation correctness. It is not destructive transcript summarization or padding marketed as optimization.

**Current files and symbols.** Refactor `src/rush/token_economy/content_router.py::ContentRouter`, `src/rush/token_economy/context_packer.py::ContextPacker`, `src/rush/token_economy/stale_sweeper.py::StaleSweeper`, `src/rush/token_economy/telemetry.py::TokenTelemetry`, and the result distillers. Reuse `src/rush/token_economy/ccr_store.py::CCRStore` only for derived cache chunks; durable recovery resolves through F1's blob/event stores. Replace claims in `docs/specs/context-compression-and-recovery-spec.md` that exceed implementation. `src/rush/token_economy/cache_aligner.py::CacheAligner` becomes an adapter helper or is deprecated after measurement.

**New files and APIs.** `src/rush/continuity/projection.py::ProjectionCompiler.compile`; `src/rush/continuity/selection.py::ContextSelector.select`; `src/rush/continuity/renderers.py` with typed renderers; `src/rush/continuity/recovery.py::RecoveryResolver.resolve`; `src/rush/continuity/token_metrics.py::ProjectionTelemetry.record`; `tests/test_projection_compiler.py`, `tests/test_projection_budget.py`, `tests/test_projection_delta.py`, `tests/test_recovery_permissions.py`, and golden fixtures under `tests/fixtures/continuity/projections/`.

**Dependencies.** F1 archive, F2 state, F3 evidence/freshness, token counters, F8 authorization policy. Adapter-specific caching waits for F7.

**Validation.** Mandatory-field budget overflow abstains; no renderer silently drops source IDs; all handles recover the intended sanitized object; stale claims are excluded or labelled; delta after ack contains only changes; no ack means replay remains available; token estimate is compared with actual provider usage where exposed; projection quality is tested by continuation tasks, not compression ratio alone.

**Risks and controls.** Token estimates vary by target, so generic estimates are labelled and adapters may supply exact counters. Ranking can omit useful context, so omission manifests, recovery, and quality gates are mandatory. Recovery could defeat token savings, so repeated recoveries become selector training/evaluation signals rather than hidden failures.

### F6. Portable continuation bundle and divergence-safe resume

**Classification:** **[Proposed]**.

**User problem and users.** Local state is not enough when a user changes provider, worktree, or machine. They need a portable artifact without leaking absolute paths, secrets, or provider-only instructions.

**Agent problem.** The receiver needs a stable schema, checksums, declared omissions, capability requirements, and a clear response when the current repository differs from the exported anchor.

**User interaction.** `rush memory export <episode> --output <path> [--include-source selected]` creates a consented bundle; `rush memory import <path> --inspect` validates without writing; a second explicit import attaches it to the current workspace. `rush memory resume <episode> --target <adapter>` compares repository state and returns `exact`, `compatible`, `diverged`, or `unavailable`.

**Agent interaction.** `rush_bundle_export`, `rush_bundle_inspect`, `rush_bundle_import`, and `rush_resume_compare` call the same shared functions. An agent cannot auto-import instructions with elevated authority. On divergence it receives changed dependencies, stale claims, and required refresh obligations before a new projection.

**Exact behavior and lifecycle.** A bundle is a deterministic directory or ZIP with `manifest.json`, `core/events.jsonl`, `core/state.json`, `core/claims.jsonl`, `core/obligations.jsonl`, consented `blobs/`, optional `adapters/<name>/envelope.json`, and `checksums.sha256`. The manifest declares schema version, cursor, capture gaps, redaction policy, included/excluded object classes, required capabilities, source workspace fingerprint, and absolute-path policy. Import validates path safety, sizes, schemas, hashes, duplicate IDs, tombstones, and authority before one transaction records imported objects. Unknown optional fields are preserved; unknown required versions fail closed.

**Token efficiency and correctness.** Bundles transfer canonical structured state once; target projections are compiled locally and are not embedded as truth. Delta bundles may start after a verified parent checksum. Source blobs are excluded by default and recoverable only if explicitly consented.

**Roles.** Rush defines and validates the portable core; adapters own optional envelopes; users consent to classes and destination; the receiving agent handles divergence through proof refresh, not blind replay.

**Differentiation.** Portability is at the context/evidence layer, independent of model identity. Provider-native resume remains an optimization, not the continuity contract.

**Current files and symbols.** Extend `src/rush/memory/checkpoint_journal.py::CheckpointJournal` only with a legacy importer; use `src/rush/safety/workspace_boundary.py::WorkspaceBoundaryGuard`, `src/rush/safety/redactor.py::SecretRedactor`, and Git worktree inspection. Git provides stable porcelain output for worktree discovery: [Git worktree](https://git-scm.com/docs/git-worktree.html). Do not write into `src/rush/providers/base.py::LLMProvider`, whose current concern is finding summaries.

**New files and APIs.** `src/rush/continuity/bundle.py::BundleWriter/BundleReader`; `src/rush/continuity/schema.py` for version negotiation; `src/rush/continuity/divergence.py::DivergenceAnalyzer.compare`; `docs/specs/continuation-bundle-v1.md`; JSON schemas under `schemas/continuity/v1/`; `tests/test_bundle_roundtrip.py`, `tests/test_bundle_security.py`, `tests/test_bundle_forward_compatibility.py`, and fixtures with gaps, redactions, contradictions, and divergent repos.

**Dependencies.** F1–F5. Export/delete permissions from F8. Provider adapters are optional.

**Validation.** Byte-stable manifest with normalized timestamps excluded from identity; hash corruption rejected; ZIP traversal rejected; oversized/decompression-bomb limits; unknown required version rejected; source system instructions import as historical/nonportable; absolute paths stripped; redacted data cannot reappear; export/import/re-export preserves core semantics; divergent repo forces invalidation.

**Risks and controls.** Bundles can exfiltrate source, so content classes are deny-by-default and inspectable before write. Schema ossification is controlled with versioned core and adapter envelopes. A bundle is never executable and may not contain hooks or commands to run automatically.

### F7. Provider adapter and capability handshake

**Classification:** **[Proposed]**, informed by external protocols.

**User problem and users.** “Works with any provider” is meaningless unless Rush can state what each integration can capture, render, resume, and measure—and degrade honestly when it cannot.

**Agent problem.** The continuity compiler needs target context limits, tokenizer availability, structured-context support, cache rules, native-session support, tool/resource support, and telemetry fields without contaminating the core schema.

**User interaction.** `rush memory adapters` lists installed adapters and capabilities; `rush memory adapter inspect <name>` shows capture gaps and privacy implications; `rush memory resume ... --target generic-markdown` always provides a baseline that can be pasted into any text-capable agent.

**Agent interaction.** Adapters implement `probe`, `ingest`, `render`, `ack`, and optional `native_resume`. The core calls only declared capabilities. Unsupported operations return canonical `skipped` results with a reason.

**Exact behavior and lifecycle.** Phase 4 ships `generic-jsonl` ingestion and `generic-markdown` rendering first. An adapter emits `AdapterCapabilitiesV1`: observable event classes, max/context budget, tokenizer identity, structured payload support, MCP resources/tools, cache semantics, native resume, usage telemetry, and export restrictions. Capability evidence is recorded per provider session. Adapter envelopes may include opaque native IDs but never redefine core authority or claims.

**Token efficiency and correctness.** A target adapter may count tokens exactly and place stable prefixes according to provider rules. It records estimated versus actual input, cached-read/write tokens, and invalidation reasons when exposed. No shared code assumes OpenAI or Anthropic caching behavior.

**Roles.** Core owns semantics; adapters translate; providers expose capabilities; users choose and authorize. Provider-specific native session state is transient and replaceable.

**Differentiation.** Rush provides a capability-negotiated continuity substrate, not a brittle set of transcript scrapers.

**Current files and symbols.** Keep `src/rush/providers/base.py::LLMProvider.summarize_findings` and `src/rush/providers/registry.py` unchanged until a later naming refactor; they are model-call providers, not continuation adapters. Extend `src/rush/mcp.py::build_server` using installed FastMCP resource APIs only behind tests. The environment exposes `FastMCP.add_resource`, `resource`, `list_resources`, and `read_resource` **[Repo]**, but the declared/runtime MCP version mismatch requires testing against the locked dependency.

**External constraints.** MCP resources are application-controlled, URI-addressed context while tools are model-controlled actions: [official MCP Python SDK resource guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/resources.md). MCP Tasks are experimental durable state machines, so Rush must not make them a core dependency: [MCP Tasks](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks). ACP v1 defines session creation/loading and updates, and 2026 updates add native session resume; that is a useful adapter mapping, not a substitute for cross-provider state: [ACP v1 overview](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v1/overview.mdx) and [ACP updates](https://agentclientprotocol.com/updates). A2A exposes tasks, history, and artifacts and is a future bundle mapping, not a reason to add a network server: [A2A specification](https://a2a-protocol.org/dev/specification/).

**New files and APIs.** `src/rush/continuity/adapters/base.py::ContinuationAdapter`; `src/rush/continuity/adapters/capabilities.py::AdapterCapabilitiesV1`; `src/rush/continuity/adapters/generic_jsonl.py`; `src/rush/continuity/adapters/generic_markdown.py`; later, only after spikes, `acp.py` or provider-native adapters; `tests/test_adapter_contract.py` supplies a reusable conformance suite; `tests/test_mcp_continuity_resources.py` tests the declared MCP version.

**Dependencies.** Stable F1–F6 schemas. No adapter blocks the generic baseline.

**Validation.** Conformance suite for partial capabilities; unsupported capture creates gaps; tokenizer mismatch labelled; cache metrics use provider results; native resume failure falls back to bundle projection; adapter cannot elevate authority; malformed provider data is bounded/redacted; locked MCP stdio behavior remains clean.

**Risks and controls.** Provider APIs change, so adapters are optional modules with recorded versions and fixtures. Scraping undocumented local state is rejected. MCP/ACP/A2A version churn is contained at adapter boundaries.

### F8. Memory control, privacy, permissions, retention, and deletion

**Classification:** **[Proposed]**, extending existing safety and permissions **[Repo]**.

**User problem and users.** Cross-session memory becomes dangerous if users cannot see what was retained, correct it, restrict recovery, or delete it reliably.

**Agent problem.** Agents need machine-readable permission denials, sensitivity classes, retention rules, and tombstones so deleted or restricted context is not silently reintroduced.

**User interaction.** `rush memory policy`, `inspect`, `correct`, `export`, `prune`, and `delete` are local CLI commands with `--json`. Destructive deletion previews exact episode/blob counts and requires the explicit command; no background retention job. `rush memory delete <episode>` removes core records and unreferenced blobs transactionally, writes content-free tombstones, and reports whether legacy files remain.

**Agent interaction.** MCP read tools expose only policy-permitted projections. Export, raw recovery, correction, and delete each have separate permissions. Delete is not available through a broad generic mutation tool. Agents receive `skipped` or `error` ToolResults without secret paths/content.

**Exact behavior and lifecycle.** Configuration defines enabled event classes, retention days by class, maximum local bytes, export defaults, recovery permissions, and path disclosure. `SecretRedactor` runs before persistence and again before rendering as defense in depth. Secrets are replaced with category markers; Rush does not retain reversible encryption keys or secret hashes. Corrections append; deletions remove content. Tombstones contain only salted local object-ID hashes and deletion time to prevent re-import. Pruning cannot delete events required by a retained claim, receipt, bundle parent, or open obligation until the dependent object is pruned or exported.

**Token efficiency and correctness.** Retention removes unused local evidence only under explicit policy; projection omission is independent and reversible. Inspection reports memory bytes, estimated tokens, and dependency pinning so users understand why an object remains.

**Roles.** Users define policy and authorize destructive/export actions; Rush enforces it; adapters may reduce capabilities but never expand permission; agents cannot self-authorize.

**Differentiation.** Privacy controls are part of the memory semantics and transport result, not a settings afterthought.

**Current files and symbols.** Extend `src/rush/config.py::RushConfig` with parsed `MemoryConfig` and reject unknown invalid fields; extend `src/rush/permissions.py::ExecutionPermissions` and `check_permissions`; reuse `src/rush/safety/redactor.py::SecretRedactor`; update `examples/rush.toml`, `docs/CONFIGURATION.md`, `docs/CONFIG_SCHEMA.md`, and `docs/PRIVACY.md` together. Do not add a `[tools.memory]` table because memory is an internal operational subsystem, not an environment-discovered quality engine.

**New files and APIs.** `src/rush/memory/policy.py::MemoryPolicy`; `src/rush/memory/retention.py::RetentionPlanner`; `src/rush/memory/deletion.py::DeletionService`; `src/rush/memory/inspection.py::MemoryInspector`; `tests/test_memory_config.py`, `tests/test_memory_permissions.py`, `tests/test_retention_dependencies.py`, `tests/test_episode_deletion.py`, and `tests/test_redaction_persistence.py`.

**Dependencies.** Cross-cutting dependency for F1–F7; minimum capture policy lands with F1, complete management before bundle export.

**Validation.** Unknown config fails clearly; disabled event classes create gaps; secrets absent from DB, blobs, logs, exports, and ToolResults; deletion survives reopen and blocks re-import; shared blobs remain until last reference; dry-run counts match deletion; path hints obey export policy; permission matrix is covered for CLI and MCP.

**Risks and controls.** Perfect secret detection is impossible, so capture is allowlisted, defense-in-depth redaction is mandatory, raw transcript capture is off by default, and export preview is required. Tombstones must not become tracking identifiers, so salts stay workspace-local and are not exported.

### F9. Multi-agent coordination, durable learning, and evaluation feedback

**Classification:** **[Proposed, later phase]**. Current mesh locks and mistake mining are insufficient for this claim **[Repo]**.

**User problem and users.** Parallel agents duplicate work, overwrite assumptions, and turn one episode's accidental workaround into permanent “memory.” Users need coordinated evidence and controlled learning, not more opaque automation.

**Agent problem.** Agents need overlap awareness, claim/obligation ownership, compare-and-swap updates, and a way to propose durable learning with support, contradiction, scope, and expiry.

**User interaction.** `rush memory agents <episode>` shows attached sessions, acknowledged cursors, claimed obligations, overlap warnings, and stale leases. `rush memory learn <episode> --proposals` shows candidate rule/preference/failure knowledge; promotion requires configured authority and is reversible.

**Agent interaction.** `rush_obligation_claim` uses expected state version and a bounded lease; `rush_evidence_publish` appends findings to the shared archive; `rush_overlap_check` compares dependency footprints; `rush_learning_propose` creates a claim, never edits `AGENTS.md` or preferences directly.

**Exact behavior and lifecycle.** Multiple writers append events through F1. Ownership is advisory and expires; no global “agent lock” blocks inspection. Optimistic concurrency rejects stale updates with the new head sequence. Overlap is computed from declared file/symbol/dependency footprints. Learning proposals are typed as repository invariant, user preference, failed approach, tool/environment fact, or external fact. Promotion requires type-specific evidence and authority; contradictions remain; file/tool/environment changes invalidate dependent learning. Evaluation outcomes feed selector/retry policy versions only through reviewed fixtures and code changes, not online self-modification.

**Token efficiency and correctness.** Agents exchange claim IDs, obligation deltas, and dependency footprints instead of full chats. Each consumer receives only events after its cursor. Overlap warnings prevent duplicated token spend. Pinned rejected approaches stay compact and recoverable.

**Roles.** Rush coordinates durable state; agents own temporary leases and evidence; users approve durable preference/rule changes; repository changes invalidate facts; maintainers ship policy/model-free selector improvements through tests.

**Differentiation.** This is closed-loop multi-agent coordination around shared evidence, not file locks or an automatic notes file presented as collective intelligence.

**Current files and symbols.** Refactor or retire `src/rush/multi_agent/mesh_locks.py::MeshLockManager` after migration; use `src/rush/multi_agent/swarm_merge.py::SwarmMergeSolver` only for its current merge domain, not memory concurrency; treat `src/rush/memory/mistake_miner.py::MistakeMiner` output as proposals; use `src/rush/agent_governance/agents_sync.py::AgentsMdSynchronizer` only on an explicit user-approved sync, never automatically.

**New files and APIs.** `src/rush/continuity/coordination.py::CoordinationService`; `src/rush/memory/learning.py::LearningLedger`; `src/rush/memory/promotion.py::PromotionPolicy`; `src/rush/evals/continuation.py` and fixture corpus under `tests/fixtures/continuity/evals/`; tests for leases, stale CAS, overlap, promotion, contradiction, and invalidation.

**Dependencies.** F1–F8 and proven single-agent continuation quality. Defer until cross-provider MVP gates pass.

**Validation.** Two-process append/claim contention; expired lease recovery; stale expected sequence rejected; disjoint footprints do not warn; contradictory learnings remain visible; preferences require user authority; no automatic `AGENTS.md` write; evaluation regression blocks selector policy release.

**Risks and controls.** Coordination can create false contention, so ownership is advisory and evidence append remains available. Learning can fossilize mistakes, so promotion is typed, evidence-backed, invalidatable, inspectable, and reversible.

## 7. Shared service and transport architecture

**[Proposed]** All CLI commands and MCP registrations call functions in `src/rush/tools/continuity.py`; neither transport opens the database, constructs domain objects, or applies redaction directly. This repairs the current manual-wrapper inconsistency before expanding it.

```text
Click command ─┐
               ├─> src/rush/tools/continuity.py ─> continuity services
FastMCP tool ──┘          │                         │
                          └─ canonical ToolResult   ├─ MemoryDatabase/EventStore
FastMCP resource ─> read-only resource adapter ────┤─ StateReducer/ClaimLedger
                                                    └─ Projection/Bundle/Policy
```

Operational memory tools do not pretend to be external quality engines. They use canonical `ToolResult`, but they are registered in a new explicit `CONTINUITY_TOOLS` registry rather than forcing fake engine metadata into every `TOOL_SPECS` entry. The registry holds name, description, input schema, shared callable, mutation class, and required memory permission. `src/rush/mcp.py::build_server` and the Click command builders consume it. **[Assumption]** Maintainer approval is required for this second registry; the fallback is to generalize `ToolSpec` with `kind=quality|operation` and keep one registry.

Read-only MCP resources expose state/projection content only after the declared MCP dependency passes a compatibility spike. Tools remain the universal fallback. Rush stays stdio-only; no HTTP/SSE transport is added.

## 8. Complete dependency map

| Dependency category | Current source | Proposed owner | Features |
|---|---|---|---|
| Canonical results | `src/rush/tools/base.py` | unchanged contract; metadata conventions documented | all |
| Shared transport calls | `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/tools/__init__.py` | `src/rush/tools/continuity.py`, `CONTINUITY_TOOLS` | all |
| Configuration | `src/rush/config.py` | `MemoryConfig`, strict parser | F1, F4–F9 |
| Redaction | `src/rush/safety/redactor.py` | capture and render gates | all persisted/rendered data |
| Workspace boundary | `src/rush/safety/workspace_boundary.py` | path validation and export rewriting | F1, F3, F6, F8 |
| Permissions | `src/rush/permissions.py` | capture/read/recover/export/correct/delete permissions | F4–F9 |
| Durable database | scattered JSON/SQLite | `.rush/memory/rush.db`, migrations | F1–F9 |
| Durable blobs | none | `.rush/memory/blobs/` | F1, F5, F6, F8 |
| Cache | `src/rush/cache.py`, `CCRStore` | remains evictable/derived | F5 |
| Legacy memory | session, checkpoint, flight, invariant, failure, preference stores | import adapters with rollback | F1–F4, F8 |
| Repository state | Git commands, Merkle invalidator, optional CodeGraph | `RepositoryFrontier`, `DependencyIndex` | F2–F4, F6, F9 |
| Tokenization/rendering | `src/rush/token_economy/*` | projection compiler and telemetry | F5, F7 |
| Provider integration | `src/rush/providers/*` summarization only | separate `src/rush/continuity/adapters/*` | F7 |
| Protocols | MCP 1.28.1 declared/1.29.0 observed; ACP/A2A external | compatibility layer and conformance fixtures | F6, F7 |
| Documentation | architecture/config/privacy/MCP/token spec | synchronized current/proposed docs | every phase |
| Evaluation | current unit tests only | continuation fixtures and end-to-end quality gates | F5–F9 |

### Feature dependency matrix

| Feature | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| F1 Archive | — |  |  |  |  |  |  | minimum policy |  |
| F2 State | required | — |  |  |  |  |  | policy |  |
| F3 Evidence | required | required | — |  |  |  |  | policy |  |
| F4 Recovery | required | required | required | — |  |  |  | permissions |  |
| F5 Projection | required | required | required | useful | — |  |  | recovery policy |  |
| F6 Bundle | required | required | required | useful | required | — | optional | required |  |
| F7 Adapters | required | required | required | useful | required | required | — | required |  |
| F8 Control | cross-cutting | cross-cutting | cross-cutting | required | required | required | required | — |  |
| F9 Coordination | required | required | required | required | required | required | required | required | — |

## 9. Implementation phases

Each phase must be independently useful and may ship without the later phases.

### Phase 0 — Contract repair and compatibility baseline

**Outcome.** New continuity work has one implementation path, reproducible dependency facts, and honest documentation.

**Scope.** Move existing session/context MCP wrapper logic behind shared tool functions without behavioral expansion; fix `context_persona_cmd`'s invalid method names; add a test that declared and installed MCP versions are reported; add a SQLite capability probe; correct unsupported configuration/docs claims and ContextPacker/CCR overclaims. Do not migrate data yet.

**Exact current files.** Modify `src/rush/cli.py`, `src/rush/mcp.py::build_server`, `src/rush/tools/__init__.py`, `src/rush/config.py`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`, `docs/CONFIG_SCHEMA.md`, `docs/MCP_REFERENCE.md`, `docs/specs/context-compression-and-recovery-spec.md`, `examples/rush.toml`, `tests/test_mcp.py`, `tests/test_cli_registry.py`, and focused current feature tests. Add `src/rush/tools/continuity.py` initially as the shared home for existing operations and `tests/test_existing_memory_transport_parity.py`.

**Entry criteria.** Current baseline recorded; unrelated version failure acknowledged; dirty user files left untouched.

**Exit criteria.** No session/context implementation lives only inside a Click or FastMCP wrapper; CLI/MCP parity tests pass; stdout remains JSON-RPC-clean; docs distinguish implemented behavior from proposals; no release version change.

**Risks/rollback.** Registration changes can alter schemas. Preserve current public names and golden schemas; rollback is registry wiring only.

### Phase 1 — Safe event kernel and user inspection (F1 + minimum F8)

**Outcome.** A user or agent can create an episode, append sanitized typed events concurrently, inspect them, and close the episode through CLI or MCP.

**Deliverables.** Add core model/database/blob/event files, migration 0001, memory config, capture permissions, shared operations, CLI/MCP registrations, and timeline inspection. Store rollback-journal SQLite by default. Add explicit capture gaps. Add legacy discovery report but no automatic import.

**Entry criteria.** Phase 0 parity and SDK/SQLite probes pass.

**Exit criteria.** All F1 validation cases pass; secret fixtures are absent from database bytes, blob files, logs, exports, and results; two processes append without duplicate sequence/idempotency violations; reopen and migration work on Windows; an episode can be inspected without a model.

**Metrics.** Append latency p50/p95, busy retries, bytes/event, redaction counts by category, gap counts, duplicate adapter retries.

**Rollback/migration.** New DB is additive. On failure, disable `[memory].enabled`; legacy files remain untouched. Migration table records importer version and source digest.

### Phase 2 — Deterministic continuation state and repository alignment (F2)

**Outcome.** Rush produces a reproducible, authority-aware state frontier and tells a receiving agent when repository instructions or files diverged.

**Deliverables.** State model/reducer, instruction resolver, objective correction, scoped repository instruction discovery, Git frontier capture using porcelain v2, state inspection, consumer acknowledgements.

**Entry criteria.** Phase 1 event schema stable under replay fixtures.

**Exit criteria.** Rebuilding from events equals cached state; authority fixtures pass; historical provider instructions cannot become destination system policy; repo changes trigger new observations; conflicts cause explicit warnings/abstention.

**Metrics.** State build time, state/token size, unresolved conflicts, stale instruction detections, deterministic replay hash.

**Rollback/migration.** State snapshots are derived and disposable. Changing reducer version creates a new cache namespace; events remain canonical.

### Phase 3 — Evidence, obligations, and bounded self-correction (F3 + F4)

**Outcome.** Handoffs carry proof rather than claims, repeated failures are recognized, and completion requires fresh evidence.

**Deliverables.** Claims, evidence spans, receipts, dependency index, freshness evaluator, obligations, failure classifier, retry policy, completion evaluator; importers for sanitized FailureLedger and InvariantGraph records.

**Entry criteria.** Phase 2 state and repository anchors stable.

**Exit criteria.** Changed dependencies stale the right claims; missing engines produce `skipped`; permissions are not misclassified as code defects; same-state retries are blocked with evidence; completion cannot pass with open mandatory obligations.

**Metrics.** stale-claim precision sample, duplicate attempts prevented, proof refresh count/cost, completion reversals, failure-class `unknown` rate.

**Rollback/migration.** Imported legacy records retain source tags and never delete originals. Claims/receipts can be rebuilt or invalidated; migrations are forward-only with backup/restore instructions.

### Phase 4 — Reversible token reduction (F5)

**Outcome.** Rush emits a compact, evidence-linked resume projection with deltas and authorized recovery, independent of a provider adapter.

**Deliverables.** Selector, typed renderers, projection compiler, omission manifest, recovery resolver, consumer cursors, generic tokenizer profile, revised telemetry, continuation evaluation corpus.

**Entry criteria.** Required state/evidence fields known; recovery permission model complete.

**Exit criteria.** Mandatory content never truncates silently; every omitted durable item is classified; recovery is correct and permissioned; delta resumes work; golden continuation tasks retain or improve correctness while reducing median input tokens by at least **40%** versus sanitized full replay. **[Assumption]** The 40% threshold is an initial gate to revise from fixture results, not a market claim.

**Quality gates.** No more than 2 percentage-point regression in correct next-action selection; zero acceptance-criterion omissions; stale-action rate below full replay; recovery requested in fewer than 25% of first actions on the fixture corpus. Report confidence intervals once the corpus is large enough.

**Rollback.** `--mode full` remains available; projections are derived and deletable; selector versions are pinned in metadata.

### Phase 5 — Portable bundle and generic cross-provider MVP (F6 + generic F7)

**Outcome.** A user exports an episode from one environment and another provider resumes through generic Markdown/JSONL with divergence checks.

**Deliverables.** Bundle v1 schemas/spec, secure writer/reader, generic adapters, adapter capability contract/conformance suite, target projection, import preview/consent, divergence analyzer.

**Entry criteria.** Projection correctness gates pass; privacy/export policy complete.

**Exit criteria.** Bundle security/round-trip fixtures pass; source-system authority is not elevated; target acts correctly on exact and divergent repository fixtures; unsupported capabilities create gaps/skips; no network service is introduced.

**Primary success metric.** Median time from bundle import to the receiving agent's first correct repository-grounded action, compared with a user-authored handoff and sanitized full transcript. Secondary: tokens, manual corrections, stale actions, recovery reads.

**Rollback.** Import is staged and transactional; failed import writes nothing. Bundle schema remains `experimental` until two independent target harnesses pass conformance.

### Phase 6 — Protocol/provider adapters and cache-aware rendering (remaining F7)

**Outcome.** At least two independently implemented target adapters pass the same continuation conformance suite; native resume and provider cache telemetry are optional accelerators.

**Deliverables.** First adapter chosen from an approved spike (ACP is preferable if available end-to-end); second independent adapter; MCP read-only resources where locked SDK supports them; provider cache layout/usage telemetry; fallback to generic projection.

**Entry criteria.** Bundle core frozen for experimental v1; adapter legal/API access confirmed; no undocumented scraping.

**Exit criteria.** Both adapters pass capture-gap, authority, divergence, token, recovery, native-resume-failure, and privacy tests. Cache claims use actual usage fields. Adapter removal leaves generic continuation intact.

**Rollback.** Disable one adapter by config/capability; no core migration. Provider-native IDs remain optional envelopes.

### Phase 7 — Multi-agent coordination and governed learning (F9)

**Outcome.** Multiple local agents share evidence/deltas safely, avoid duplicate work, and propose—not silently install—durable learning.

**Entry criteria.** Single-agent cross-provider MVP meets quality gates across a meaningful corpus; contention data justifies coordination complexity.

**Exit criteria.** Multi-process CAS/lease tests pass; overlap warnings reduce duplicate actions without blocking disjoint work; no online self-modifying policies; every promoted learning has authority, evidence, scope, contradiction handling, and invalidators.

**Rollback.** Coordination and learning registries are feature flags. Append-only archive/evidence continues without them.

## 10. Recommended first PR

**PR title:** `memory: add redacted episode event kernel with CLI/MCP parity`

This is the smallest vertical slice that creates real continuation value without pretending the projection or adapters already exist.

### Exact files

Create:

- `src/rush/memory/models.py` — `CaptureStatus`, `EventType`, `EpisodeRecord`, `EventAppend`, `EventRecord`.
- `src/rush/memory/database.py` — `MemoryDatabase.connect`, `migrate`, `transaction`.
- `src/rush/memory/event_store.py` — `create_episode`, `append`, `list_after`, `close_episode`.
- `src/rush/memory/migrations/0001_core.sql` — only `workspaces`, `episodes`, `provider_sessions`, and `events` for this PR.
- `src/rush/tools/continuity.py` — shared `episode_start`, `event_append`, `episode_inspect`, `episode_close`, all returning `ToolResult`.
- `tests/test_event_store.py`.
- `tests/test_continuity_transport_parity.py`.
- `tests/fixtures/continuity/events-v1.jsonl`.

Modify:

- `src/rush/config.py` — minimal `MemoryConfig(enabled=False, database_path='.rush/memory/rush.db', capture_classes=...)`; parse and validate it.
- `src/rush/permissions.py` — `memory_capture` and `memory_read`; no export/delete yet.
- `src/rush/tools/__init__.py` — register shared operational callables through the agreed registry shape.
- `src/rush/cli.py` — thin `rush memory episode start|inspect|close` and `rush memory event append` commands.
- `src/rush/mcp.py::build_server` — thin registrations of the same callables.
- `src/rush/safety/redactor.py::SecretRedactor` — expose a structured redaction count without returning matched secret text.
- `tests/test_mcp.py` — tool discovery/schema/stdout checks.
- `tests/test_config.py` and `tests/test_permissions.py`.
- `examples/rush.toml`, `docs/CONFIGURATION.md`, `docs/CONFIG_SCHEMA.md`, `docs/PRIVACY.md`, `docs/ARCHITECTURE.md`, and `docs/MCP_REFERENCE.md`.

### Deliberately excluded

No blobs, claims, reducer, token projection, bundle, legacy migration, resources, provider adapter, WAL, FTS, background capture, or automatic tool instrumentation. Event payload size is capped so inline redacted JSON is sufficient for this slice.

### Smallest decisive test

`tests/test_continuity_transport_parity.py::test_redacted_event_has_same_semantics_via_cli_and_mcp` should:

1. enable memory in a temporary workspace;
2. start one episode through the shared service;
3. append a payload containing a fixture secret through the CLI;
4. inspect the episode through the real stdio MCP server;
5. assert identical event ID/type/sequence/capture status, absence of the secret from response, database bytes, and stderr, and clean JSON-RPC stdout;
6. retry with the same idempotency key and assert one stored event.

Then run the full project contract commands with the project interpreter:

```powershell
$env:VIRTUAL_ENV = $null
$env:PYTHONPATH = $null
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
```

The pre-existing version assertion must be reported separately, not “fixed” by changing a release version in this PR.

## 11. Research spikes before irreversible decisions

### Spike A — SQLite concurrency mode

Run multi-process append, crash, reopen, and checkpoint tests on Windows with the project interpreter's exact SQLite build. Compare rollback journal with WAL only after establishing whether 3.50.4 includes the relevant backport. Record filesystem type and `PRAGMA compile_options`. Decision: remain rollback-journal unless WAL demonstrates a material latency benefit and passes corruption/recovery tests.

### Spike B — MCP locked-version resources

Create a throwaway server using the dependency resolved from the lock, not the ambient 1.29.0 environment. Verify static/template resources, `resources/list`, `resources/read`, structured tool outputs, and stdout cleanliness. Decision: add read-only resources only if supported without changing the transport or dependency outside normal project update policy.

### Spike C — Continuation quality corpus

Build at least 30 sanitized episodes across implementation, debugging, configuration, and review. For each, define the correct next action, forbidden stale actions, required instructions, and proof obligations. Compare full replay, user summary, and Rush projection using the same target harness. Decision: tune budgets/ranking and replace the initial 40%/25% thresholds with observed baselines before claiming product performance.

### Spike D — First protocol adapter

Test ACP session/update/resume availability in a real supported client and whether the exposed events cover user messages, assistant messages, tool calls/results, plan changes, usage, and native IDs. Do not infer support from protocol documentation alone. If coverage is inadequate, ship only generic JSONL/Markdown and wait.

### Spike E — Token counters and provider telemetry

Compare `tiktoken` estimates with actual reported usage for supported OpenAI targets and adapter-supplied counters for other providers. Record cache read/write fields and invalidation behavior. The current `tiktoken` package is specifically an OpenAI BPE tokenizer: [official tiktoken repository](https://github.com/openai/tiktoken). Generic projections must label estimates rather than imply universal exactness.

## 12. Legacy migration and compatibility

Migration is explicit, inspectable, and non-destructive:

1. `rush memory migrate --inspect` discovers `.rush/session-memory.json`, `.rush/sessions/*.json`, flight JSONL, failure DB, invariant JSON, and preferences; reports counts, invalid rows, estimated bytes, and redaction categories without writing.
2. `rush memory migrate --apply` imports supported records into a dedicated episode or user-preference scope with `legacy_source` metadata and source digests.
3. Every text field is redacted before persistence. Invalid or ambiguous rows become capture-gap events, not guessed facts.
4. Checkpoints and flight events import as historical evidence; they do not become current instructions or verified claims automatically.
5. Preferences remain in preference scope and require explicit authority when used in continuation state.
6. Source files remain unchanged through at least one stable release and until the user explicitly deletes them. Imported source digests make reruns idempotent.
7. Downgrade means disabling new memory and continuing to read legacy stores; it does not attempt a destructive reverse migration.

## 13. What to defer or reject

### Defer

- Provider-native adapters until the bundle and generic projection pass quality gates.
- MCP resources until locked-version compatibility is proven; tools suffice for MVP.
- WAL until the exact SQLite runtime and concurrency tests are safe.
- FTS5 until episode volume makes exact/filter search insufficient; feature-detect it.
- Multi-agent leases, overlap detection, and durable learning until single-agent continuation works.
- Model-assisted claim extraction. Deterministic explicit events come first; later extraction may only propose claims with source spans.
- Cross-machine automatic synchronization. Manual consented bundles meet the local-first contract first.

### Reject

- Raw transcript ingestion as default “memory.”
- Sending full history on every resume.
- Destructive summaries without recovery handles and omission manifests.
- Treating source-provider system/developer instructions as portable authority.
- A provider-specific transcript format as the canonical schema.
- A hosted memory service, network daemon, or non-stdio MCP transport.
- Scraping undocumented provider databases/session files.
- Vector search as the authority or first retrieval layer.
- Online self-editing of Rush policy, `AGENTS.md`, or preferences.
- Git hooks, automatic commits, history rewriting, tags, releases, or uploads.
- Calling file locks, test runners, or generic retries “agentic memory.”
- Hard-coded token prices or cache-hit claims without provider usage evidence.

## 14. End-to-end acceptance scenarios

1. **Provider switch, same worktree.** Agent A records objective, plan, edits, a failed test, correction, and fresh passing receipt. Agent B receives a compact projection, identifies the next open obligation, does not repeat the failed patch, and can recover the exact sanitized failure evidence.
2. **Provider switch, divergent worktree.** A bundle is imported where a depended-on file changed. The claim becomes stale, the projection states the divergence, and the receiver refreshes proof before editing.
3. **Incomplete capture.** An adapter cannot expose assistant tool results. Rush records `source_unavailable`; the projection states the gap and does not claim complete history.
4. **Instruction conflict.** Historical source system text conflicts with current repository instructions. Current destination/repository authority wins; historical text is visible only as evidence.
5. **Token pressure.** Mandatory state exceeds budget. Rush returns a budget finding and suggested higher minimum; it never truncates acceptance criteria.
6. **Recovery denied.** An agent requests a restricted blob. Rush returns a permission result without content; the projection remains valid and notes unavailable evidence.
7. **Concurrent agents.** Two processes append with the same idempotency key and claim one obligation. One event is stored; one lease wins; the losing agent receives the new head and can choose other work.
8. **Deletion.** User previews and deletes an episode. Shared referenced blobs remain; unique blobs are removed; re-import is blocked by a content-free local tombstone; no secret appears in diagnostics.

## 15. Evaluation and observability

### Correctness metrics

- first correct action rate and time-to-first-correct-action;
- acceptance-criterion retention;
- instruction conflict detection and false resolution rate;
- stale action rate after repository divergence;
- repeated rejected-attempt rate;
- obligation completion precision;
- unsupported/unavailable capture reported as gaps.

### Token and performance metrics

- sanitized archive estimated tokens;
- projection estimated and actual input tokens;
- reduction ratio by renderer/target/budget;
- stable-prefix size and actual cache read/write tokens;
- delta size after acknowledged cursor;
- recovery request rate and recovered tokens;
- compile/append/rebuild latency and database busy retries.

### Privacy and control metrics

- redaction markers by category, never match values;
- capture-disabled and source-unavailable counts;
- export included/excluded object counts;
- deletion/pruning bytes and dependency-pinned bytes;
- permission-denied operations.

Telemetry stays local by default. Reports use event/claim IDs and sanitized paths. No metric may contain prompt text, source content, secrets, native provider tokens, or raw command output.

## 16. Phase checklists

### Foundation

- [ ] Record baseline test/ruff results and dependency/runtime versions.
- [ ] Repair shared CLI/MCP implementation paths.
- [ ] Correct docs/config/current-code inconsistencies.
- [ ] Approve operational registry design.

### Archive and control

- [ ] Land schema/migrations/event store.
- [ ] Enforce redaction before hash/persistence.
- [ ] Add capture gaps, idempotency, sequence ordering, and concurrency tests.
- [ ] Add inspect and minimum capture/read permissions.
- [ ] Keep legacy stores unchanged.

### State and evidence

- [ ] Land deterministic reducer and authority resolver.
- [ ] Capture Git/repository frontier safely.
- [ ] Add claims, source spans, receipts, dependencies, and invalidation.
- [ ] Add obligations, failure classes, retry bounds, and completion proof.

### Token reduction

- [ ] Compile mandatory-first projections.
- [ ] Add typed renderers, omission manifest, and recovery.
- [ ] Add consumer acknowledgement and deltas.
- [ ] Replace hard-coded cost claims with target telemetry.
- [ ] Pass continuation-quality and token gates.

### Portability

- [ ] Publish experimental bundle v1 schema/spec.
- [ ] Add secure inspect/export/import and consent projection.
- [ ] Add divergence analysis.
- [ ] Pass generic JSONL/Markdown end-to-end handoff.
- [ ] Add adapters only through conformance tests.

### Later coordination

- [ ] Demonstrate need from real contention data.
- [ ] Add optimistic concurrency, bounded leases, and overlap footprints.
- [ ] Add proposed learning with typed promotion/invalidation.
- [ ] Prohibit automatic governance-file edits and online policy mutation.

## 17. Feature inventory

| ID | Feature | User-visible outcome | Earliest phase | Core success gate |
|---|---|---|---:|---|
| F1 | Session Archive | Inspectable local episode history with explicit gaps | 1 | redacted, ordered, idempotent, concurrent capture |
| F2 | Continuation State | Clear objective/instructions/frontier for takeover | 2 | deterministic replay and authority correctness |
| F3 | Evidence and freshness | Claims linked to current proof | 3 | dependency changes invalidate correctly |
| F4 | Proof and recovery loop | No blind retries or evidence-free completion | 3 | fresh obligations gate completion |
| F5 | Reversible projection | Smaller resumes with recovery | 4 | quality retained with measured token reduction |
| F6 | Portable bundle | Move an episode between environments/providers | 5 | secure roundtrip and divergence handling |
| F7 | Adapter handshake | Honest capability-dependent integration | 5–6 | two independent targets pass conformance |
| F8 | User control | Inspect/correct/export/delete/retain safely | 1–5 | secrets absent and permissions enforced |
| F9 | Coordination/learning | Parallel evidence sharing without fossilized mistakes | 7 | contention/learning tests and human authority |

## 18. Open decisions requiring maintainer approval

1. Should operational memory tools use a second `CONTINUITY_TOOLS` registry, or should `ToolSpec` gain a `kind` field and remain the only registry? Recommendation: one generalized registry if it can preserve all existing schemas; otherwise a small explicit second registry is safer than fake engines.
2. Is memory capture explicitly started per episode in the first release, or enabled automatically for all Rush tool calls when `[memory].enabled=true`? Recommendation: explicit start for v1; add automatic structured tool-result capture only after privacy fixtures pass.
3. What is the default retention policy? Recommendation: no silent age-based deletion in experimental releases; cap by warning and require explicit prune until real usage is known.
4. May bundles include selected source blobs? Recommendation: metadata/state/evidence only by default; require explicit `--include-source selected` and preview.
5. What constitutes a target consumer identity for delta acknowledgements? Recommendation: user-supplied stable name plus adapter, not a provider secret or opaque fingerprint.
6. Which first real adapter has documented, supported event access? Recommendation: decide from Spike D; do not promise Codex/Claude-specific ingestion before evidence.
7. Should user preferences remain in `.rush/preferences.json` through the experimental period or migrate immediately? Recommendation: keep separate and add a read-through adapter; migrate only with correction/delete parity.
8. What fixture corpus and threshold are sufficient to call bundle schema v1 stable? Recommendation: at least 30 varied episodes, two independent target harnesses, zero authority/acceptance omissions, and published median/token/recovery results.

## 19. Primary external references

- [MCP 2026-07-28 release candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) — current protocol direction and compatibility risk.
- [MCP Tasks 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks) — experimental task durability; not a core dependency.
- [MCP resources specification](https://modelcontextprotocol.io/specification/draft/server/resources) and [official Python SDK resource guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/resources.md) — application-controlled context.
- [ACP v1 overview](https://github.com/agentclientprotocol/agent-client-protocol/blob/main/docs/protocol/v1/overview.mdx) and [ACP updates](https://agentclientprotocol.com/updates) — session/update/native-resume adapter mapping.
- [A2A specification](https://a2a-protocol.org/dev/specification/) — future task/history/artifact mapping.
- [SQLite WAL](https://www.sqlite.org/wal.html), [transactions](https://www.sqlite.org/lang_transaction.html), [foreign keys](https://www.sqlite.org/foreignkeys.html), [FTS5](https://www.sqlite.org/fts5.html), and [`user_version`](https://www.sqlite.org/pragma.html#pragma_user_version) — local persistence constraints.
- [Git status porcelain v2](https://git-scm.com/docs/git-status) and [Git worktree porcelain](https://git-scm.com/docs/git-worktree.html) — repository frontier inputs.
- [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching), [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), and [tiktoken](https://github.com/openai/tiktoken) — adapter-specific token/cache behavior.

## 20. Final consistency audit

- The plan does not rewrite the strategic report and does not present proposals as current code.
- Token reduction is a first-class feature with architecture, files, APIs, metrics, tests, phase gates, and failure behavior—not an incidental benefit.
- Lossless local archive and compact model context are separated, so there is no full-history/selective-retrieval contradiction.
- Provider-neutral core, target-specific projection, and optional native envelopes are separated.
- Session, episode, event, projection, consumer, and bundle boundaries are defined.
- Source-system instructions retain provenance but cannot outrank destination/repository/user authority.
- Redaction gaps qualify completeness; secrets are never made recoverable.
- Negative evidence survives projection while verbose payloads remain lazy.
- Repository changes invalidate dependent claims and force divergence handling.
- Users can inspect, correct, export, prune, and delete; agents cannot self-authorize.
- CLI and MCP use the same implementation and canonical ToolResult; stdio remains clean.
- Existing engines remain environment-discovered with structured `skipped` results.
- No UI, hosted-only service, Git hooks, release mutation, undocumented scraping, or automatic governance rewrite is introduced.
- The first PR is a small, testable vertical slice; adapters and multi-agent learning come only after the core proves useful.


## 21. F10 amendment — local-first intelligence and optional remote provider use

This amendment incorporates the decisions in [local-model research](innovations-memory-local-models-research-report.md) and the implementation workstream in [local-model plan](innovations-memory-local-models-plan.md). It changes only sequencing, dependencies, and feature recommendations; F1–F9 remain the continuity system of record.

### F10. Local-first intelligence

**Classification:** **[Proposed, gated workstream]**. This is not a new autonomous memory authority. It is a provider-neutral capability layer that can improve parsing, redaction, retrieval, reranking, and tightly bounded transformations while preserving the existing canonical archive, evidence ledger, authority rules, and reversible projections.

**Required architecture.** Add a single `IntelligenceService` boundary behind `src/rush/tools/continuity.py`; local engines, model artifacts, and remote providers are optional implementations. Every request carries an explicit capability, maximum input/output token budget, source-span requirement, privacy policy, cancellation deadline, and `ToolResult` evidence. The deterministic C0 path (bounded parser, `SecretRedactor`, allowlisted PII rules, SQLite FTS5/BM25, source spans) is mandatory and remains the full offline fallback. A missing runtime, disabled model, insufficient hardware, unsupported provider capability, or failed policy check returns structured `skipped`/fallback output—never an invented result or silent remote upload.

**Feature recommendation.** Begin with model-free safety/parsing and lexical retrieval; add a small local embedding/reranking profile only after the benchmark gate; add a small local LLM only for schema-constrained extraction, contradiction triage, candidate labels, and compression proposals with deterministic validation. Do not make a local model the source of truth, autonomous writer, background daemon, raw-transcript store, or universal agent runtime. Remote capability includes direct provider APIs, provider-supported OAuth, and user-authorized existing-CLI bridges. Codex, Claude Code, Antigravity, Z.AI, DeepSeek, 9Router, and OmniRouter are named workstreams, not rejected or silently generalized: each gets its own auth/privacy/security/capability verification record and concrete adapter/bridge decision. Rush never extracts or forwards a CLI/OAuth token, pools accounts, or selects/reroutes a provider automatically.

**New dependencies and interfaces.** F10 depends on F1's redacted capture boundary, F2/F3 source spans and evidence/freshness, F5's token accounting and reversible projection, F7's capability handshake, and F8's permissions/consent. It adds optional, environment-discovered runtimes and artifacts only; it must not add a mandatory model package, model download, hosted service, or unpinned dependency to Rush's base install. Configuration must separate `[memory.intelligence]` policy from `[tools.*]` quality-engine discovery and must reject unknown fields.

### Sequencing amendment

| Gate | Placement relative to F1–F9 | Decision required to proceed |
|---|---|---|
| F10.P0 corpus/capability scaffold | Phase 0, before durable capture changes | Typed capability/result and auth-source/CLI-bridge contract; no executable provider integration |
| F10.P1 deterministic parsing, secret/PII controls | Completes with Phase 1/F8 minimum; required before any durable source blob or remote payload | Redaction, source-map, deletion, and offline-fallback fixtures pass |
| F10.P2 local embedding baseline | After F1–F3 establish redacted evidence and source spans; benchmark alongside Phase 4/F5 | Consumer CPU/Apple/8–16 GB profiles meet retrieval quality, latency, and token-reduction thresholds |
| F10.P3 local reranking/index comparison | After F10.P2; may enhance F5 retrieval, never replace lexical fallback | Relevance gain justifies artifact/runtime footprint on declared consumer tiers |
| F10.P4 bounded local LLM transforms | After F5 proves reversible projection and F3/F4 prove evidence/obligation behavior | Schema validation, abstention, privacy, and task-quality gates beat deterministic-only baseline |
| F10.P5 direct APIs, OAuth, existing-CLI, and named-router adapters | Only during/after F7 and after F8 consent/privacy gates | Per-route official auth/OAuth/CLI contract, credential boundary, retention/security evidence, redaction and conformance tests pass; 9Router/OmniRouter retain named verification records |
| F10.P6 reproducibility/performance pack | Before promoting any profile beyond experimental | Pinned artifact manifest, hardware matrix, benchmark corpus, and rollback evidence are published |

F10 does not block the safe F1–F6 generic cross-provider MVP: a no-model/offline installation remains supported throughout. It does block three things: durable raw capture before F10.P1, remote payload transmission before F10.P1/F8/F10.P5, and any claim that semantic retrieval or token reduction is available before its benchmark gate. F9 remains later than proven single-agent continuation; it may consume F10's redacted, evidence-linked retrieval results but cannot promote model output into durable learning without F3/F8/F9 authority rules.

### F10 acceptance gates

- Consumer profiles are explicit: CPU/8–16 GB RAM, 16/32 GB RAM, Apple Silicon unified memory, 8 GB VRAM, 12–16 GB VRAM, 24 GB VRAM, and higher-memory; each profile has an enabled path and a model-free fallback.
- Retrieval reports recall/precision, p50/p95 latency, memory footprint, artifact size, startup behavior, abstention/fallback rate, and net input/output token reduction against FTS5/BM25.
- Any local LLM output is bounded, structured, cited to source spans, deterministically validated, and persisted only as a proposed claim or projection candidate.
- Final local and remote payloads are independently re-scanned for secrets/PII; policy failure is a visible refusal/skipped result.
- OAuth/CLI bridges use only a user-controlled provider flow or user-installed signed-in executable; Rush never reads provider keychains/configuration, copies tokens, opens a login browser implicitly, or changes CLI settings. Named 9Router and OmniRouter adapters remain in the roadmap pending their specific verification records—not a generic-router downgrade.
- CLI and MCP call the same implementation and return canonical `ToolResult`; no server, daemon, UI, account, model download, or router integration is implicit.

The authoritative first PR, model shortlist, scorecard, benchmark corpus, provider verification checklist, and rollback design are specified in the dedicated F10 documents rather than duplicated here.
