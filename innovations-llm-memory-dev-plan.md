# Rush LLM + continuity memory development plan

Status: proposed implementation plan  
Authoritative execution document: this file combines the continuity-memory implementation work and the local/remote intelligence implementation work. It is one ordered plan; phases below are delivery boundaries, not separate plans. Research reports and the earlier plans remain decision history and fixtures, but implementation work follows this document when they differ.

## 1. Outcome and scope

Rush will provide a local-first continuity system that lets any authorized agent or provider resume work from grounded state rather than a transcript:

- a redacted, append-only local event archive with explicit capture gaps;
- deterministic continuation state, authority resolution, claims, receipts, freshness, obligations, and recovery;
- reversible, token-budgeted context projections with source handles and deltas;
- portable bundles that survive provider/worktree changes and fail safely on divergence;
- optional local retrieval, reranking, and bounded local LLM assistance on consumer hardware;
- optional direct APIs, provider-supported OAuth, existing-CLI bridges, and named router integrations;
- the same callable implementation through the Rush CLI and stdio-only MCP.

This plan does not create a chat UI, server, daemon, hosted memory product, mandatory model/runtime, automatic model download, Git hook, account pool, provider token importer, or opaque LLM memory authority.

## 2. Fixed architecture and invariants

### 2.1 Ownership boundaries

| Layer | Owner | Rule |
|---|---|---|
| Canonical continuity state | src/rush/memory/ | SQLite events, claims, receipts, policy, and bundles are authoritative. |
| Derived intelligence | src/rush/intelligence/ | Embeddings, ANN indexes, rerank scores, model outputs, provider responses, and CLI responses are removable candidates with provenance. |
| Public operations | src/rush/tools/continuity.py and src/rush/tools/intelligence.py | CLI and MCP invoke these same functions; transport contains no policy, DB, or provider logic. |
| Existing quality tools | src/rush/tools/ and ALL_TOOLS | Existing ToolResult/Findings remain evidence sources; do not duplicate engine logic. |
| Provider integrations | src/rush/intelligence/adapters/ | Do not overload src/rush/providers/base.py::LLMProvider.summarize_findings. |
| Configuration and authorization | src/rush/config.py and src/rush/permissions.py | Strict, disabled-by-default, user-controlled. Secrets are references only. |

### 2.2 Non-negotiable implementation rules

1. Python 3.12; local CLI and stdio-only MCP. No HTTP/SSE transport.
2. ToolResult and Finding remain the canonical public-result shape. An absent optional engine, model, credential, CLI, hardware profile, or provider returns structured skipped.
3. SecretRedactor executes before hashing, persistence, rendering, export, CLI invocation, and remote egress. WorkspaceBoundaryGuard validates all workspace paths.
4. SQLite evidence is canonical; FTS, embeddings, indexes, summaries, and provider/CLI output are derived and deletable.
5. C0 always works without a model file, network, GPU, daemon, account, or new required dependency.
6. No raw transcript is captured by default. Every unavailable/disabled/redacted source is represented as an explicit gap.
7. A model or similarity score may propose a candidate only. It cannot promote a fact, override authority, close an obligation, authorize deletion, execute a tool, or write a rule.
8. Direct egress requires final payload redaction/scan, policy decision, endpoint allowlist, and explicit permission. It is never a fallback for missing local capability.
9. OAuth is user-owned and provider-documented. A CLI bridge uses an installed user-owned CLI and never reads its keychain, browser state, config, or tokens.
10. 9Router and OmniRouter remain named tracks. They are neither rejected nor silently replaced with anonymous generic endpoints.

### 2.3 Canonical state and derived stores

Canonical state uses .rush/memory/rush.db. Large already-redacted blobs use .rush/memory/blobs/sha256/<prefix>/<digest>. Derived cache and model/index artifacts remain outside canonical data and may be deleted without changing facts.

Initial canonical tables:

| Table | Required implementation purpose |
|---|---|
| workspaces, episodes, provider_sessions | local episode identity, source/target attachment, optimistic head |
| events, event_dependencies | immutable ordered archive, idempotency, capture status, invalidation anchors |
| claims, claim_evidence | typed valid/stale/contradicted/unverified propositions with spans |
| obligations, receipts | completion proof and action/result pairing |
| projections, projection_items, consumers | reproducible budget renderings, omissions/recovery, acknowledged deltas |
| tombstones | content-free prevention of re-import after deletion |

SQLite requirements: foreign keys on every connection; short transaction for sequence allocation/write; bounded busy timeout/retry; PRAGMA user_version migrations; rollback-journal default. Enable WAL only after the exact interpreter, filesystem, concurrency, crash recovery, and SQLite patch-level test passes. Never place the canonical DB on a network filesystem.

### 2.4 Core contracts

| Location | Contract |
|---|---|
| src/rush/memory/models.py | EventAppend, capture statuses, authority, claim status, obligation status, projection target, bundle manifest types |
| src/rush/memory/state.py | ContinuationStateV1: objective, effective instructions, conflicts, frontier, decisions, negative evidence, open obligations, gaps |
| src/rush/memory/event_store.py | append, list_after, episode lookup; immutable sequence/idempotency semantics |
| src/rush/memory/authority.py | resolve destination/runtime, repository, user, portable episode, historical-source, inferred-preference precedence |
| src/rush/memory/claims.py | propose, promote, contradict, invalidate; no destructive overwrite |
| src/rush/memory/projection.py | compile a reproducible mandatory-first projection and omission manifest |
| src/rush/intelligence/models.py | ModelRef with publisher/model/revision/hash/license/format/quantization/runtime/locality |
| src/rush/intelligence/protocols.py | IntelligenceProvider probe, invoke, close; CapabilityStatus; IntelligenceRequest; IntelligenceResult |
| src/rush/intelligence/policy.py | Local/remote/CLI policy, egress decision, capability limits, consent receipt |
| src/rush/intelligence/manifest.py | ModelManifest with immutable artifact identity, compatible consumer profile, runtime and index compatibility |

IntelligenceRequest accepts bounded source IDs/spans, target schema, token/latency budget, privacy policy, and deadline; it does not accept an unbounded arbitrary agent prompt. IntelligenceResult stores structured value, source IDs, confidence, schema result, model/runtime/provider provenance, token/compute metrics, redaction record, and bounded error. It is never a Claim.

## 3. Current repository integration map

| Existing source | Planned use |
|---|---|
| src/rush/tools/base.py::ToolResult and Finding | all public continuity/intelligence operations and evidence receipts |
| src/rush/tools/__init__.py | register an explicit CONTINUITY_TOOLS operational registry or one approved generalized registry; do not create fake quality engines |
| src/rush/cli.py::_run_tool | keep existing catalog behavior; add thin memory/intelligence command groups that call shared operations |
| src/rush/mcp.py::_register_tools and build_server | matching shared calls; resources only after locked-SDK compatibility tests; stdio remains clean |
| src/rush/config.py::RushConfig and _parse | add strict MemoryConfig and IntelligenceConfig; reject unknown fields |
| src/rush/permissions.py::ExecutionPermissions and check_permissions | add scoped capture/read/recover/export/correct/delete/provision/invoke/remote_egress/oauth_connect/cli_bridge permissions |
| src/rush/safety/redactor.py::SecretRedactor | preserve current behavior and add typed redaction findings/pipeline composition |
| src/rush/workspaces/boundary.py::WorkspaceBoundaryGuard | validate all capture/import/export/recovery paths |
| src/rush/session_memory.py::SessionMemoryManager, memory/checkpoint_journal.py::CheckpointJournal, tools/flight_recorder.py::FlightRecorder | explicit low-authority migration/import adapters only |
| src/rush/memory/failure_ledger.py::FailureLedger and merkle_invalidator.py::MerkleInvalidator | migrate sanitized failure history and dependency invalidation inputs |
| src/rush/token_economy/router.py::ContentRouter, ccr_store.py::CCRStore, cache_aligner.py::CacheAligner, stale_sweeper.py::StaleSweeper, telemetry.py::TelemetryStore | token estimates, derived cache, optional cache rendering, and local telemetry; not canonical recovery |
| src/rush/codegraph/context_packer.py::ContextPacker | optional code-oriented projection/retrieval input, not the source of truth |
| src/rush/providers/base.py::LLMProvider | leave current summary API unchanged; remote intelligence adapters are separate |

## 4. Dependency order

| Phase | Delivers | Requires | Enables |
|---|---|---|---|
| 0 | contracts, configuration, registries, fixtures, hardware/capability probe | current ToolResult/CLI/MCP/config/permissions | safe disabled baseline |
| 1 | privacy/parsing boundary and canonical event archive | phase 0 | all continuity persistence and any future egress |
| 2 | deterministic state, evidence, freshness, obligations, recovery policy | phase 1 | grounded resume and completion proof |
| 3 | C0 lexical retrieval and reversible token projection | phases 1-2 | measurable token reduction with no model |
| 4 | portable bundle and generic adapter handshake | phases 1-3 | cross-provider/worktree handoff |
| 5 | local embeddings, index, rerank | phases 1-3 and phase-0 corpus | optional semantic retrieval on consumer hardware |
| 6 | bounded local LLM transforms | phases 1-3 and phase 5 | schema-constrained candidate assistance |
| 7 | direct APIs, OAuth, existing-CLI bridges, named routers | phases 1-4 and privacy gates | optional remote/provider intelligence |
| 8 | migration, reproducibility, docs, hardening | phases 1-7 as selected | experimental release readiness |
| 9 | multi-agent coordination and governed learning | phases 1-4 proven and phase-8 controls | shared evidence without automatic rule mutation |

Phase 9 remains later than the single-agent product, but it is included here as a gated implementation phase. It cannot start early or bypass phases 1-4/8.

## 5. Phase 0 — contracts, disabled capability scaffold, and fixtures

### Objective

Create the shared implementation boundary without running inference, downloading a model, creating an account, or sending data remotely.

### Tasks

1. Add src/rush/memory/ package boundary and src/rush/intelligence/ package boundary with no import-time runtime/model/provider side effects.
2. Add MemoryConfig and IntelligenceConfig to RushConfig. Default memory and intelligence disabled; reject unknown sections/fields; keep intelligence distinct from environment-discovered tools tables.
3. Add CONTINUITY_TOOLS metadata: name, input schema, shared callable, mutation class, required permission. Reuse a generalized registry only if it preserves existing catalog schemas and tests.
4. Add src/rush/tools/continuity.py and src/rush/tools/intelligence.py. CLI/MCP bind only these operations; no DB connection or redaction in transport.
5. Define all core data contracts in section 2.4 and serialize/deserialize them with explicit version fields.
6. Add HardwareProfile C0, C1a, C1b, C2, Apple16, Apple24_32, C3, and HigherMemory; probe available RAM/VRAM/runtime without starting a model.
7. Check in a 100+ private/synthetic fixture corpus containing continuation facts, conflicts, stale dependency cases, multilingual input, prompt injection, secret-bearing blobs, retrieval labels, and schema-output cases.
8. Add a manifest validator that rejects model identity missing revision, SHA-256, license, runtime, or hardware compatibility.
9. Publish command skeletons: rush memory status and rush intelligence status/recommend return disabled/skipped truthfully.

### Files

Modify: src/rush/config.py, src/rush/tools/__init__.py, src/rush/cli.py, src/rush/mcp.py, src/rush/permissions.py, examples/rush.toml, docs/CONFIGURATION.md, docs/CONFIG_SCHEMA.md.

Add: src/rush/memory/__init__.py, src/rush/memory/models.py, src/rush/intelligence/__init__.py, src/rush/intelligence/models.py, protocols.py, hardware.py, registry.py, manifest.py, benchmark/corpus.py, benchmark/runner.py, src/rush/tools/continuity.py, src/rush/tools/intelligence.py, tests/test_memory_config.py, tests/test_intelligence_registry.py, tests/test_intelligence_cli_mcp_parity.py, tests/fixtures/continuity/.

### Acceptance gate

- Default installation remains behaviorally unchanged.
- CLI/MCP operation parity passes and MCP stdout remains valid JSON-RPC only.
- Missing model/runtime/credentials return skipped.
- No dependency, model, artifact, provider account, network client, or secret is added.
- Hardware classification and manifest validation are deterministic fixture tests.

### Rollback

Disable memory/intelligence config and remove generated benchmark cache only. No user continuity data exists yet.

## 6. Phase 1 — deterministic privacy, parsing, canonical archive, and control

### Objective

Build the safe local foundation: redaction before persistence, explicit capture gaps, SQLite archive, inspection, and deletion.

### Tasks

1. Implement the bounded ingestion sequence: bytes and source metadata -> deterministic parser -> first-party secret/PII spans -> optional discovered Gitleaks scan -> policy decision -> redacted blob/event -> final rendered payload re-scan before any egress.
2. Implement parsers for bounded text, JSON, YAML, TOML, Markdown, and PDF; enforce byte/page/decompression/time limits and source-offset maps. Pydantic/jsonschema additions require exact-pin review; Gitleaks is discovered, never bundled.
3. Implement MemoryDatabase, migrations/0001_core.sql, EventStore, BlobStore, MemoryPolicy, MemoryInspector, RetentionPlanner, and DeletionService.
4. Use transaction-assigned sequence and UUID4 event IDs. Enforce unique episode sequence and source-session/idempotency key. Events are immutable; correction appends a superseding event.
5. Persist capture states captured_redacted, captured_metadata_only, source_unavailable, capture_disabled, redacted_secret, adapter_error, and projection_omitted.
6. Implement rush memory episode start/capture/inspect/close, policy, delete, and redaction preview. Add matching MCP tools; destructive deletion has a dedicated permission and preview.
7. Store only redacted blob handles in events. Tombstones use salted local hashes; exports do not expose absolute paths, raw secret values, reversible secret hashes, or salts.
8. Integrate FlightRecorder, SessionMemoryManager, and CheckpointJournal only through explicit, low-authority migration/import records. Do not silently treat legacy entries as evidence.

### Files

Modify: src/rush/safety/redactor.py, src/rush/permissions.py, src/rush/tools/flight_recorder.py, src/rush/cli.py, src/rush/mcp.py, docs/PRIVACY.md.

Add: src/rush/memory/database.py, event_store.py, blob_store.py, policy.py, inspection.py, retention.py, deletion.py, migrations/0001_core.sql, src/rush/intelligence/sensitive.py, secret_scan.py, pii_rules.py, parse.py, schemas.py, egress.py.

Tests: test_memory_database.py, test_event_store.py, test_redaction_persistence.py, test_memory_permissions.py, test_episode_deletion.py, test_retention_dependencies.py, test_parse_bounds.py, test_egress_scan.py, test_continuity_transport_parity.py.

### Acceptance gate

- A secret is absent from DB, blobs, logs, ToolResult, telemetry, export, and remote payload fixture.
- Redaction happens before payload hash; malformed input has no partial blob.
- Concurrent idempotent append, monotonic sequence, DB reopen/migration, crash between temporary blob write and DB commit, and path traversal tests pass.
- Gitleaks absence still leaves first-party deterministic rules operating; no parser makes a network request.
- Deletion removes eligible content, preserves shared references, survives reopen, and blocks re-import.

### Rollback

Disable optional scanner/parser adapters. Canonical content is retained only if it already passed the redaction policy; deleting an episode uses the normal preview/tombstone path.

## 7. Phase 2 — deterministic state, evidence, freshness, and bounded recovery

### Objective

Make a handoff grounded: derive current intent, authority, repository frontier, valid evidence, failures, and required proof without an LLM.

### Tasks

1. Implement StateReducer, InstructionResolver, RepositoryFrontier, ClaimLedger, ReceiptRecorder, DependencyIndex, FreshnessEvaluator, ObligationStore, FailureClassifier, RetryPolicy, and CompletionEvaluator.
2. Enforce authority order: current destination runtime/developer policy; current scoped repository instructions; current user corrections; portable episode instructions; historical provider instructions as evidence only; inferred preferences/proposed learning last.
3. Capture repository frontier using safe Git porcelain-v2 -z parsing and workspace boundaries. Record changed AGENTS instructions as new observations; do not rewrite governance files.
4. Convert ToolResult/Findings into sanitized receipts with engine/version, command hash, exit code, artifact metadata, permission result, and repository anchor.
5. Represent claims as valid, stale, contradicted, unverified, or invalid. Preserve support/opposition/qualification spans and contradictions.
6. Invalidate dependent claims on file/symbol/config/tool/engine/instruction/upstream-claim digest changes; never erase stale evidence.
7. Require fresh admissible receipts before closing an obligation. A user waiver is append-only and visible.
8. Classify failures as code, test_assertion, environment, permission, dependency_missing, transport, conflict, stale_context, or unknown. Reject an exact retry unless a material condition changed.
9. Implement rush memory state/evidence/obligations/attempt/verify/correct and resume_prepare/recover/completion_check shared operations.

### Files

Add: src/rush/memory/state.py, reducer.py, authority.py, repository_frontier.py, claims.py, receipts.py, dependencies.py, freshness.py, obligations.py, failures.py, retry_policy.py, completion.py.

Modify: src/rush/memory/merkle_invalidator.py, failure_ledger.py, src/rush/tools/common.py integration points, src/rush/permissions.py, src/rush/tools/continuity.py.

Tests: test_state_reducer.py, test_instruction_authority.py, test_claim_ledger.py, test_receipts.py, test_dependency_invalidation.py, test_git_frontier.py, test_obligations.py, test_retry_policy.py, test_completion_evidence.py.

### Acceptance gate

- Golden replay produces the same ContinuationStateV1.
- Destination/repository/user authority wins over historical provider text.
- Corrections preserve history; contradictions render; stale instructions force explicit conflict/abstention.
- Unrelated changes do not stale a claim; relevant file/tool/dependency changes do.
- Permission denial is not a code failure; completion fails with stale/missing required receipts.
- No inspection runs a command; retries terminate at configured bound.

### Rollback

Derived state can be rebuilt from immutable events. Disable retry suggestion/verification operations without deleting evidence.

## 8. Phase 3 — C0 retrieval and reversible token-budget projection

### Objective

Deliver token reduction before semantic models: lexical retrieval and mandatory-first, recoverable context projections.

### Tasks

1. Add feature-detected SQLite FTS5 lexical index with exact-field and bounded LIKE fallback. Index redacted canonical content only; store source IDs/spans and invalidation generation.
2. Implement ProjectionCompiler, ContextSelector, typed renderers, RecoveryResolver, and ProjectionTelemetry.
3. Select mandatory content first: objective, effective instructions, conflicts, repository frontier, open obligations, active blockers, recent user corrections, and valid negative evidence.
4. Rank optional supporting claims/events by relevance, freshness, authority, dependency proximity, and token estimate. Every omission receives a reason and recovery handle.
5. Render target-generic content under a fixed budget. If mandatory items do not fit, return a budget finding; never truncate silently.
6. Implement acknowledgement cursor: an unacknowledged projection does not advance; an acknowledged consumer receives only changed state and events after ack_sequence; repository divergence forces bootstrap.
7. Use ContentRouter and ContextPacker as token/retrieval helpers; use CCRStore only for derived cache; use TelemetryStore for local no-content metrics.
8. Implement rush memory project/tokens/recover/resume ack and rush context retrieve compatibility delegation.

### Files

Add: src/rush/memory/projection.py, selection.py, renderers.py, recovery.py, token_metrics.py; src/rush/intelligence/lexical.py, retrieval.py.

Modify: src/rush/token_economy/router.py, telemetry.py, ccr_store.py integration boundary, cache_aligner.py helper boundary, stale_sweeper.py integration boundary, src/rush/codegraph/context_packer.py, src/rush/tools/continuity.py.

Tests: test_projection_compiler.py, test_projection_budget.py, test_projection_delta.py, test_recovery_permissions.py, test_lexical_retrieval.py, fixtures/continuity/projections/.

### Acceptance gate

- A no-model C0 installation retrieves exact/lexical evidence and generates a projection.
- All included/omitted items have provenance; every recovery handle returns the intended sanitized object under permission.
- Mandatory overflow fails closed; stale evidence is excluded or labelled.
- Acknowledged delta contains only change; unacknowledged replay remains available.
- Report archive/projection estimate, actual tokens when an adapter reports them, recovery rate, and continuation-task correctness.
- Do not claim a token win until corpus measurement shows at least 50% median continuation-input reduction with zero labelled critical-fact loss and no P95 regression.

### Rollback

Disable projection/retrieval derived indexes and caches. Events, claims, receipts, and blobs remain intact.

## 9. Phase 4 — portable bundles and generic cross-provider handoff

### Objective

Make the canonical state transferable before provider-specific integrations.

### Tasks

1. Implement BundleWriter, BundleReader, schema negotiation, DivergenceAnalyzer, versioned JSON schemas, and continuation-bundle-v1 specification.
2. Emit deterministic bundle layout: manifest, core events/state/claims/obligations JSONL or JSON, consented blobs, optional adapter envelopes, checksums.
3. Validate path safety, sizes, decompression limits, schemas, hashes, duplicate IDs, tombstones, consent classes, authority labels, and required version before one import transaction.
4. Import source-provider instructions as historical/nonportable. Compile fresh projection on the destination; never treat exported projection as truth.
5. Compare export and current repository anchors; return exact, compatible, diverged, or unavailable. Divergence identifies stale claims and required proof refresh.
6. Implement generic-jsonl ingest and generic-markdown render adapters plus AdapterCapabilitiesV1. Each adapter declares capture, context/tokenizer, structured data, cache, native resume, telemetry, and export restrictions.
7. Add read-only MCP resources only if the locked FastMCP API compatibility test passes. Tools remain universal fallback.
8. Implement rush memory export/import/resume/adapters and matching MCP tools.

### Files

Add: src/rush/memory/bundle.py, schema.py, divergence.py; src/rush/memory/adapters/base.py, capabilities.py, generic_jsonl.py, generic_markdown.py; schemas/continuity/v1/; docs/specs/continuation-bundle-v1.md.

Modify: src/rush/memory/checkpoint_journal.py only for legacy import, src/rush/mcp.py, src/rush/tools/continuity.py.

Tests: test_bundle_roundtrip.py, test_bundle_security.py, test_bundle_forward_compatibility.py, test_adapter_contract.py, test_mcp_continuity_resources.py.

### Acceptance gate

- Export/import/re-export preserves canonical semantics, capture gaps, redaction, contradictions, tombstones, and consent.
- Corrupt hash, unknown required schema, path traversal, decompression bomb, unsafe absolute path, and malformed provider data fail closed.
- Native/provider adapter failure falls back to generic bundle projection.
- No adapter can elevate authority, store raw credentials, or turn MCP into a network server.

### Rollback

Disable individual adapter modules. Generic markdown and JSONL bundle remain available; canonical archive is unaffected.

## 10. Phase 5 — optional local embedding, index, and reranking

### Objective

Add semantic retrieval only where it improves the locked corpus on declared consumer hardware over the C0 baseline.

### Tasks

1. Implement user-confirmed artifact provisioning, checksum verification, offline artifact cache, manifest record, and artifact/index deletion. No auto-download and no trust_remote_code.
2. Implement ONNX Runtime/FastEmbed candidate adapter after exact dependency/version/license review. Evaluate Granite Embedding 278M as initial CPU baseline and BGE-small as English control.
3. Implement hybrid lexical/semantic retrieval with reciprocal-rank fusion. SQLite remains canonical; vector index stores only derived references and manifest ID.
4. Implement model/index invalidation for artifact revision, chunking, config, source deletion/tombstone, and dependency changes.
5. Add optional Qwen3 0.6B embedding/reranker comparison. Rerank only top-k lexical/semantic candidates and only after it lowers final context without losing evidence.
6. Compare hnswlib, USearch, and sqlite-vec only as removable indexes; no default vector database. Persist a selected index only after the corpus gate.
7. Expose rush intelligence provision/status/inspect/retrieve and continuity_retrieve with ranking source, spans, manifest, token estimate, and fallback reason.

### Consumer profile policy

| Profile | Allowed default intelligence | Fallback |
|---|---|---|
| C0 CPU, 8-16 GB RAM | FTS5; optional measured small int8 embedding | lexical projection |
| C1a 16 GB RAM or C1b 8 GB VRAM | small embedding; bounded top-k rerank if measured | disable rerank then semantic |
| C2 12-16 GB VRAM or 24-32 GB Apple unified | enhanced embedding/rerank | C1/C0 |
| C3 24 GB VRAM or 48-64 GB unified/RAM | advanced comparator only | C2 |

### Files

Add: src/rush/intelligence/embedding.py, fusion.py, index.py, artifacts.py, provisioning.py, rerank.py, ann.py, metrics.py, adapters/onnx.py.

Modify: src/rush/intelligence/retrieval.py, src/rush/memory/dependencies.py, projection selection/token metrics, config, docs.

Tests: test_embedding_manifest.py, test_retrieval_quality.py, test_index_invalidation.py, test_offline_egress.py, test_consumer_profiles.py.

### Acceptance gate

- C0 stays fully functional with all intelligence disabled.
- Artifact provenance has revision/hash/license/runtime/quantization/hardware profile.
- Recall@k, nDCG, evidence-span precision, stale rate, p50/p95 latency, RSS/VRAM, disk, build/rebuild, and token impact are recorded on the locked corpus.
- No secret/deleted content is retrievable from the derived index.
- Rerank/index configuration is enabled only if it improves evidence relevance and meets the phase-3 token gate; otherwise remove it from runtime scope.

### Rollback

Disable capability and delete derived model/index cache. Render lexical recovery rather than comparing incompatible vectors.

## 11. Phase 6 — bounded local LLM candidate assistance

### Objective

Use a local model only for structured candidate work that is independently validated and evidence-linked.

### Tasks

1. Implement generation.py, structured.py, candidate.py, review.py, and local runtime adapters for user-managed llama.cpp, Ollama, and MLX. Do not bundle a runtime or start a public listener.
2. Limit capabilities to taxonomy classification, metadata extraction with span IDs, relevance/candidate labels, contradiction triage, and derived projection alternatives.
3. Require an approved ModelManifest, selected hardware profile, bounded source spans, schema, output cap, deadline, cancellation, and deterministic validator for every invoke.
4. Evaluate Qwen3-4B, Phi-4-mini, and SmolLM3 as C1 candidate set. Evaluate 7-8B candidates only on C2 after their profile gate.
5. Reject schema-invalid, untraceable, secret-bearing, authority-conflicting, budget-exceeding, or unreproducible output. Persist allowed output only as a proposed candidate with transform provenance.
6. Exclude free-form chat, hidden reasoning retention, autonomous promotion, model tool execution, model-controlled retries, and raw transcript persistence.
7. Expose rush intelligence extract/classify/propose and matching MCP operations; every result is structured candidate or skipped.

### Files

Add: src/rush/intelligence/generation.py, structured.py, candidate.py, review.py, adapters/llama_cpp.py, adapters/ollama.py, adapters/mlx.py, schemas/intelligence/.

Modify: intelligence registry/policy/manifest, memory claims/projection integration, docs.

Tests: test_structured_generation.py, test_candidate_provenance.py, test_local_model_abstention.py, test_local_model_privacy.py, fixture corpus local-LLM cases.

### Acceptance gate

- C0 has no local LLM path.
- C1 runs only an approved 3-4B Q4 profile at tested context; C2 7-8B follows a passing hardware gate.
- Schema validity, evidence span precision/recall, contradiction retention, hallucinated-claim rate, output cap, cancellation, and no-egress behavior pass thresholds.
- Candidate model improves locked handoff tasks without authority, privacy, latency, or token regression.

### Rollback

Disable the runtime profile and delete only derived candidate cache. Canonical archive/claims remain unchanged.

## 12. Phase 7 — remote APIs, OAuth, existing-CLI bridges, 9Router, and OmniRouter

### Objective

Add explicitly authorized remote intelligence without becoming a credential broker or silently changing provider.

### Common safety tasks

1. Implement RemoteEgressDecision and final render -> secret/PII re-scan -> policy -> explicit confirmation -> allowed request sequence.
2. Store provider/model/version/policy/capability/usage provenance, never raw credentials, raw payloads, browser state, CLI config path, token, or full CLI trajectory.
3. Use exact endpoint allowlists, timeout, cancellation, output-size bounds, no automatic retry to another provider, and SSRF defenses.
4. Add remote_egress, oauth_connect, and cli_bridge permissions. Agents cannot select an unapproved provider or receive its credentials.
5. Return skipped for absent credentials, unsupported official capability, unsigned CLI, policy denial, or failed verification.

### Direct API and OAuth tasks

| Track | Implementation |
|---|---|
| OpenAI | direct Responses adapter with policy receipt; optional provider-owned Codex OAuth CLI route, not token extraction |
| Anthropic | direct Messages adapter; optional provider-owned Claude Code OAuth CLI route |
| Gemini | direct API/OAuth only through documented user flow; keep Antigravity separate |
| Mistral | direct optional adapter after current terms/retention preflight |
| Z.AI / GLM | direct Bearer adapter plus supported user-owned coding-tool profile; do not claim Rush-owned OAuth without official evidence |
| DeepSeek | direct API-key/Anthropic-compatible adapter plus supported user-owned coding-tool profile; do not claim Rush-owned OAuth without official evidence |

### Existing-CLI bridge tasks

1. Implement cli_bridge.py with explicit executable path, version probe, approved command profile, bounded input over stdin/arguments, documented JSON/JSONL output parser, cancellation, output cap, and sanitized provenance receipt.
2. Implement Codex bridge using the user-completed Codex sign-in and noninteractive structured profile; implement Claude bridge with bounded print JSON/stream-JSON profile; implement Antigravity bridge with user-owned agy sign-in/ADC/key and scoped headless profile.
3. Add Z.AI and DeepSeek coding-tool profile adapters only through their documented supported CLI configuration.
4. The bridge must not open a browser, log in, edit a provider CLI setting, inspect home/config/keychain files, carry sessions across users, or imply subscription API rights.
5. Start with read-only/no-write/no-shell command profiles. Any broader provider-CLI capability requires an explicit later approval and a separate sandbox/conformance gate.

### Named router tasks

1. Add router_verification.py and versioned records under .rush/intelligence/providers/.
2. Preserve separate records for 9Router and the user-selected OmniRouter product/vendor. Do not conflate same-name products.
3. Require exact legal entity/product, official domain, API/OAuth/CLI contract, terms, data retention, provider authorization, endpoint/TLS behavior, credential boundary, model routing behavior, user consent flow, and redaction test result.
4. Build adapters/nine_router.py and adapters/omni_router.py from the approved record, not a generic compatible endpoint fallback.
5. Each record visibly remains ready, blocked, or needs_user_selection; neither route is silently removed from the roadmap.

### Files

Add: src/rush/intelligence/remote.py, credentials.py, oauth.py, cli_bridge.py, router_verification.py, remote_audit.py; adapters/openai.py, anthropic.py, gemini.py, mistral.py, zai.py, deepseek.py, codex_cli.py, claude_cli.py, antigravity_cli.py, zai_cli.py, deepseek_cli.py, nine_router.py, omni_router.py.

Modify: intelligence policy/registry/config, permissions, tools/intelligence.py, CLI/MCP bindings, operator/privacy docs.

Tests: test_remote_egress.py, test_oauth_policy.py, test_cli_bridge.py, test_provider_contract.py, test_router_verification.py, test_endpoint_allowlist.py, test_no_secret_telemetry.py, mock HTTP/subprocess fixtures.

### Acceptance gate

- Each named provider/router record has a current source, security/privacy/terms result, and explicit status.
- OAuth is a user-controlled documented flow; CLI bridge tests prove no credential/config/keychain access.
- Final payload scan catches injected/retrieved secret fixtures.
- Direct and CLI routes pass structured-output, cancellation, allowlist, policy, and no-cross-provider-failover tests.
- Missing/denied route is skipped, not silently replaced with cloud or another provider.
- 9Router and OmniRouter retain named records until a concrete approved adapter/bridge decision is recorded.

### Rollback

Disable one provider/profile, revoke it in the provider or its CLI, and remove derived remote/CLI receipt cache. Canonical continuity data does not depend on its response.

## 13. Phase 8 — migration, reproducibility, documentation, and release hardening

### Tasks

1. Add opt-in import assistants for SessionMemoryManager, CheckpointJournal, FailureLedger, preference/invariant sources. Every imported record is labelled with low authority/source provenance and has an import receipt.
2. Add memory/intelligence inspect, doctor, usage, export-manifest, artifact-cache management, and reproducibility reports with no content telemetry.
3. Publish configuration, privacy, architecture, bundle schema, CLI/MCP contract, hardware profile, artifact manifest, provider/CLI/router verification, deletion/recovery, and incident rollback documentation.
4. Add reproducibility fixtures recording selected/rejected model/provider/index route, source URL/date, revision/SHA-256/license, runtime/version, quantization, hardware, context length, privacy policy, and corpus metrics.
5. Run platform capability tests on Windows, Linux, macOS, Apple Silicon, CPU-only, 8 GB VRAM, 12-16 GB VRAM, and 24 GB VRAM / higher-memory profiles when hardware is available; unsupported hardware remains skipped.
6. Confirm disabled intelligence cannot change existing quality-tool behavior.
7. Do not create tags, releases, publish packages, install hooks, or upload artifacts as part of this plan.

### Files

Add: src/rush/intelligence/inspect.py, usage.py, export.py, doctor.py; migration package; operator docs; reproducibility fixtures.

Modify: examples/rush.toml, docs/CONFIGURATION.md, docs/CONFIG_SCHEMA.md, docs/PRIVACY.md, architecture docs, CLI/MCP documentation.

### Acceptance gate

- A clean machine can reproduce a selected optional route from a manifest or report exactly why it is skipped.
- Deleting optional artifacts/runtimes leaves C0 and canonical continuity data correct.
- Migration is explicit, reversible at source, and never auto-promotes legacy facts.
- Documentation, configuration example, runtime behavior, CLI, MCP, and tests agree.
## 14. Phase 9 — multi-agent coordination and governed durable learning

### Objective

Let multiple agents share evidence-backed progress without turning locks, summaries, or mined mistakes into automatic durable memory.

### Entry gate

Start only after phases 1-4 pass: single-agent replay, authority, invalidation, projection, bundle, and generic cross-provider handoff must be proven. Phase 9 does not relax any privacy, deletion, or user-authority rule.

### Tasks

1. Implement CoordinationService with episode-scoped optimistic compare-and-swap, bounded advisory leases, acknowledged cursors, and declared file/symbol/dependency footprints.
2. Implement overlap checks that warn on materially overlapping work without blocking read/inspection or evidence append.
3. Add obligation claim/release/expiry operations. A stale expected sequence returns the current head; it does not overwrite another agent.
4. Implement LearningLedger and PromotionPolicy. A learning proposal is typed repository invariant, user preference, failed approach, tool/environment fact, or external fact; it has evidence spans, scope, contradiction links, invalidators, and expiry.
5. Allow promotion only through the existing authority/evidence rules. A model output, MistakeMiner result, or agent summary remains a proposal until promoted by the required evidence/actor.
6. Use MeshLockManager only as a migration/input reference; replace file-lock semantics with advisory continuity leases. Keep SwarmMergeSolver in its existing three-way merge domain.
7. Expose rush memory agents/learn/overlap and matching MCP tools. Never auto-write AGENTS.md, preferences, or governance documents.
8. Add continuation evaluation fixtures with multi-agent contention, conflict, stale claim, and learning-promotion cases. Any selector/retry-policy update is code- and fixture-reviewed, never online self-modification.

### Files

Modify: src/rush/mcp_mesh/lock_manager.py migration boundary, src/rush/memory/mistake_miner.py proposal adapter only, src/rush/tools/continuity.py, config, permissions, CLI/MCP bindings.

Add: src/rush/memory/coordination.py, learning.py, promotion.py; src/rush/evals/continuation.py; tests/test_coordination.py, test_learning_ledger.py, test_promotion_policy.py, test_overlap.py, fixtures/continuity/evals/.

### Acceptance gate

- Two-process contention preserves exactly one append/claim state and exposes the new head to the loser.
- Lease expiry recovers safely; disjoint footprints do not warn; overlap never blocks evidence append.
- Contradictory learnings remain visible; invalidation stales dependent learning; user preference needs user authority.
- No automatic AGENTS.md/preference/governance write, no online policy mutation, and no agent self-authorization.
- Token measurements show agents exchange IDs/deltas/footprints rather than full chats.

### Rollback

Disable coordination/learning operations; retain the underlying event archive and evidence. Existing file locks stay only in their original domain until explicit migration cleanup is approved.

## 15. Required command and MCP surface

| Capability | CLI | Shared implementation/MCP |
|---|---|---|
| archive lifecycle | rush memory episode start/capture/inspect/close | continuity operations; episode MCP tools |
| continuity state/evidence | rush memory state/evidence/obligations/attempt/verify/correct | state, claim, receipt, completion tools |
| projection/recovery | rush memory project/tokens/recover/resume/ack | resume_prepare, recover, resume_ack |
| portability | rush memory export/import/adapters | bundle export/inspect/import/compare |
| C0 intelligence | rush intelligence status/recommend/scan/parse/retrieve | intelligence status, scan, parse, retrieve |
| local artifacts/LLM | rush intelligence provision/inspect/extract/classify/propose | explicit capability invoke only |
| providers and routers | rush intelligence provider status/connect/invoke; rush intelligence router verify 9router or omnirouter | same explicit actions; no hidden connect/egress |

All mutation commands require the relevant scoped permission. MCP resources remain read-only and optional; tools are the fallback.

## 16. Verification matrix and release gates

| Area | Required proof |
|---|---|
| transport | CLI/MCP semantic parity; no stdout corruption while MCP serves stdio |
| archive | redaction-before-hash, idempotency/concurrency, migration/reopen, path and blob crash safety |
| authority/state | golden deterministic replay, precedence/conflict fixtures, historical instruction quarantine |
| evidence/recovery | receipt sanitization, invalidation precision, stale-completion denial, bounded retry |
| token reduction | budget overflow abstention, omission/recovery correctness, delta ack, actual token reconciliation, continuation-quality corpus |
| privacy/control | no secret across every persisted/rendered/exported/remote surface; delete/tombstone/retention permission fixtures |
| portability | checksum/schema/path safety, semantic roundtrip, divergence handling, generic adapter fallback |
| local intelligence | manifest provenance, no auto-download/egress, hardware gate, retrieval/LLM quality and resource metrics |
| remote/CLI/router | explicit consent, no credential access, final payload scan, endpoint allowlist, mock OAuth/CLI protocol, named router evidence record |
| reproducibility | selected route can be reproduced or truthfully skipped from versioned manifest and hardware profile |

Release progression:

- Phases 0-3 must pass before any bundle/provider/model feature is presented as usable.
- Phase 4 must pass before claiming cross-provider continuity.
- Phase 5 and 6 are optional and may ship only as disabled capability profiles after their corpus gates.
- Phase 7 is optional per named route; no provider route blocks C0 or generic bundle handoff.
- Phase 8 is required before a single-agent experimental release.
- Phase 9 is a later, separately released capability but is fully specified here; it cannot bypass its entry gate.

## 17. First pull request

Title: feat(memory-intelligence): add disabled continuity and capability contracts

Include only phase-0 work:

- strict disabled MemoryConfig and IntelligenceConfig;
- contract dataclasses/protocols, hardware probe, manifest validation, and CONTINUITY_TOOLS registration;
- shared no-op/status CLI/MCP operations;
- fixture corpus schema and CLI/MCP/config tests.

Exclude: database writes, model/runtime dependencies, artifact download, parser/PII engine, embedding, LLM inference, HTTP client, provider account/OAuth, CLI launch, router implementation, bundle import/export, and migration.

The first PR is accepted only when a default install remains unchanged, invalid config fails clearly, all new capability requests return structured skipped, CLI/MCP parity holds, and stdio is clean.

## 18. Explicit non-goals and stop conditions

- Do not build a general chat UI, hosted service, public listener, model marketplace, background updater, or generic model runner.
- Do not store raw transcripts, chain-of-thought, secrets, OAuth tokens, provider CLI state, or browser state.
- Do not treat vector/LLM/provider/CLI output as canonical memory, a governance rule, or completion evidence.
- Do not silently upload when a local capability is absent.
- Do not automatically select, reroute, fail over, or pool providers/accounts.
- Do not remove or genericize 9Router or OmniRouter; use their named verification records.
- Do not start Phase 9 before its entry gate, or add Git hooks, automatic governance-file edits, automatic commits, history rewrites, tags, releases, or publishing.

## 19. Completion condition

The C0 continuity product is complete when phases 0-4 and 8 pass, enabled optional local/provider/CLI/router routes pass their own gates, and unavailable routes truthfully return skipped. The complete combined roadmap additionally requires Phase 9 to pass its entry and acceptance gates. In both cases, the verification matrix must prove no regression of canonical evidence, authority, privacy, portability, or token-reduction correctness.
