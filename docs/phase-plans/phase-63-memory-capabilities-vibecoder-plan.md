# Phase 63 Implementation Plan: Memory Capabilities and Vibecoder Integrations

**Start with [§9: execution tasks](#9-execution-tasks).** It contains 80 numbered actions across 16 work packets: write the fixture/test, edit named symbols/files, connect the runtime route, assert failure cases, and run verification. Sections 1–8 are supporting contracts, not the work queue.

## 1. Purpose, authority and status

**Phase 63 continues the Phase 61/62 memory development cycle.** Implement every suggested capability in the two assessments, with executable RED/GREEN contracts and measured evaluation, by extending the developed memory foundation and integrations. Planning status: proposed implementation specification. Implementation status: not started for Phase 63; no completion or benchmark improvement is claimed.

The hierarchy is **Phase 63 → workstream MC00–MC15 → task MC00.1–MC15.5**. MC identifiers remain stable so existing requirement, file-ownership and test references still resolve. They are workstreams within this single phase, not additional phases. For example, Phase 63 workstream MC02 owns bounded recall; task MC02.2 adds its scoped candidate query.

**Immediate memory predecessor:** [Phase 62 — Memory Integration Layer](phase-62-memory-integration-layer-plan.md), built on [Phase 61 — Typed-Artifact Schema, Trust Tiers and Transport Dispatcher](phase-61-cross-llm-memory-typed-artifact-schema-plan.md). **New runtime prerequisite:** [Phase 64](phase-64-runtime-correctness-and-safe-execution-plan.md) repairs unsafe invocation, containment, patch and evidence behavior found by the whole-application review before dependent memory work. **Successor:** [Phase 65](phase-65-project-provisioning-scan-and-agent-workflow-plan.md) composes memory with installation, full scanning and agent repair; [Phase 66](phase-66-interactive-tui-and-local-web-plan.md) delivers both required interfaces. Execution order is 64 → 63 → 65 → 66; MC identifiers and all 80 tasks remain unchanged. This is a roadmap phase, not a new remediation-finding phase; it does not reopen or claim closure of an `R-xxx` finding.

Baseline: commit `997b56e`, branch `codex/phase-61-62-review-fixes`, worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes`. Work must stay off `main`. No commit, push, release, model download or paid provider execution is authorized by this planning document.

Binding inputs:

| Input | Identity / role |
|---|---|
| `.scratch/memory-capability-assessment/recommendations.md` | SHA256 `ebe0b0c6090d1d46c0b4f1eab9ce39b3df80cf9108afacfba988835a3687e7a2`; five core improvements, metadata/hybrid trial and measurement requirements |
| `.scratch/memory-capability-assessment/vibecoder-integrations.md` | SHA256 `9d756518ccce4e25300e96d7f650a8307c138cb4896d642b6602a91fe7bb6f26`; five integrations and five contributing capability families |
| `AGENTS.md` | Transport parity, ToolResult, permissions, genuine TDD, engine discovery and scope contract |
| `docs/templates/task-block-template.md` | Task-card schema; SHA256 `10fdb5380f04097258e29327cf74fe474532cdc42747a38310d0befa2107ecc3` |
| [Phase 61 plan](phase-61-cross-llm-memory-typed-artifact-schema-plan.md) and [implementation evidence](phase-61-implementation-evidence.md) | Inherited typed-store, trust, migration, memory-interface and transport contracts; evidence retains its recorded revision |
| [Phase 62 plan](phase-62-memory-integration-layer-plan.md) and [implementation evidence](phase-62-implementation-evidence.md) | Immediate predecessor: cache/review integration, maintenance, handoff diffs, attribution, API freshness, expiry and decision schema; evidence retains its recorded revision |
| [Benchmark strategy](../reports/memory-capabilities-benchmark-strategy.md) | Selected public benchmarks, Rush scenarios, leakage controls, metrics and promotion gates |

The source assessments currently live in untracked scratch space. Their requirements are reproduced in §5 and the contracts below so execution does not depend on preserving scratch files. Preserve the hashes when these inputs are later committed or relocated. Earlier phase plans contain planning-time statements; their implementation evidence, the phase index and the actual source baseline must be distinguished. Phase 63 does not rewrite historical completion statuses or use their recorded test counts as current verification.

### 1.1 Continuation contract: Phase 61 → Phase 62 → Phase 63

| Predecessor contract | Phase 63 extension | Owning workstreams |
|---|---|---|
| Phase 61 typed artifacts, durable origins, trust/promotion rules, defended recall and shared MemoryTool | Add version history, scoped budgeted recall, exact expansion, evidence relationships and derived consolidation while retaining existing IDs, origins, trust boundaries and legacy calls | MC01–03 |
| Phase 62 cache front-end, review citations, API freshness, maintenance and expiry | Remove repeated work, bind cache identity to all relevant inputs and measure actual costs; keep source validation and expiry effective on every new read route | MC04, MC12 |
| Phase 61/62 episodic/failure/skill memory, decision schema and attribution | Link current intent, repair conditions, executable verification, reusable recipes, check selection and scoped last-success evidence | MC05–10 |
| Phase 61 transport dispatcher and Phase 62 handoff diffs | Add bounded versioned deltas, restricted receiving access and exact acknowledged read-back on existing SDK/ACP paths | MC11 |
| Existing phase-plan, CLI/MCP, configuration and verification conventions | Establish inherited baseline, preserve public compatibility, run comparative evaluation and produce a reviewed successor handoff | MC00, MC14, MC13, MC15 |

MC00 starts from the developed source at `997b56e`, not an empty store or a reimplementation of Phases 61/62. Retain predecessor contract tests alongside new Phase 63 tests. A missing or broken inherited behavior must be recorded against its actual source/test evidence and resolved before dependent Phase 63 work; it cannot be hidden by lowering an earlier acceptance contract. The remaining unranked ideas in Phase 61's backlog are not automatically admitted: Phase 63's scope is exactly the two assessments and R01–R20.

## 2. Verified starting point

| Existing surface | Observed behavior at baseline | Implementation consequence |
|---|---|---|
| `src/rush/memory/store.py:290-372` | BM25 search fetches full matching rows; defended recall filters and checks integrity/freshness afterward | Scope before ranking; bounded validated pages; retain existing integrity defenses |
| `src/rush/tools/memory.py:69-206` | Shared memory implementation; ask/list/recall/write/promote/maintain; queries return full artifacts | Add new operations through this implementation; preserve legacy calls |
| `src/rush/token_economy/memory_cache_gate.py:45-109`, `src/rush/tools/review.py:95` | Search precedes defended recall; cache anchored to producer content hash | Remove duplicate work, never remove freshness or producer-read binding |
| `src/rush/codegraph/store.py:11-65` | Derived file/symbol graph, not versioned memory authority | Keep memory relations in the same transactional memory DB; resolve code references through existing graph |
| `src/rush/invocation/executor.py:344-420` | Canonical handler/cache execution; no automatic retry | One opt-in observation seam; keep failures and cache provenance intact |
| `src/rush/patch/verifier.py:46-241` | Contract-bound verification exists; indexed callers are exports/tests | Add a real verification route; do not label unused library code an integration |
| `src/rush/memory/transport.py:74-130` | SDK/ACP delivery; tool access denied and no receiving MCP configuration | Explicit restricted receiver required; sending a capsule cannot count as read-back |
| `src/rush/tools/trace.py:14-72`, `src/rush/tools/blast_radius.py:32-59` | Requirement-tag presence and heuristic reverse-import impact | Candidate evidence only; no tag-derived execution proof or exhaustive-impact claim |
| `src/rush/memory/failure_ledger.py:35-75`, `src/rush/tools/provenance_ai.py:85-170` | Exact patch identity, attribution links, line ages | Add conditions and observed outcomes; no causal proof from revert/fix labels or line survival |
| `scripts/benchmarks/run.py:19-187`, `src/rush/tools/prompt_eval.py:101-286` | Existing probe runner; evaluator of supplied records | Extend runner with actual execution adapters; no parallel framework or fabricated run records |

The earlier review-fix verification records seven pre-existing test failures in `.scratch/phase-61-62-review-fixes/verification.md`. Those are historical baseline evidence, not a permanent allowlist. MC00 must reproduce or explain current baseline before attributing regressions. Source changes here do not establish that all Phase 61/62 specifications were implemented.

## 3. Goals and boundaries

Deliver selective memory, connected evidence and useful cross-session learning. Agent behavior must improve through the loop **observe → retrieve → choose → execute within granted permissions → verify → update**. The system supplies grounded choices and records actual outcomes; the agent remains responsible for choosing actions.

All ten suggested feature groups remain in scope, including an implemented optional hybrid-retrieval trial. Failed benefit thresholds keep a variant experimental; they do not delete its implementation or acceptance requirements.

Rush's interactive TUI and local web application are required product scope, delivered by Phase 66 over shared Phase 65 operations. This memory phase supplies their memory services without duplicating interface implementation. Automatically installed hooks, daemon, autonomous commit/rollback, new general orchestration framework, universal semantic verifier and bundled embedding model remain outside this phase. No changes to release versions. Observations never grant new authority. Missing quality engines remain structured `skipped`, and skipped checks never prove success. Phase 65 P65-07 explicitly adds scoped public memory deletion; Phase 63's existing operation table does not already promise that API.

## 4. Architecture decisions and alternatives

| Decision | Alternatives considered | Selected approach and tradeoff |
|---|---|---|
| Persistence | Existing codegraph edges; separate graph service; memory SQLite relations | SQLite relations beside artifact revisions: atomic trust/version updates and fewer dependencies; bounded traversal, not arbitrary graph analytics |
| Retrieval | Current BM25; enriched BM25 + evidence links; embeddings | Enriched bounded BM25 first, linked retrieval next, optional hybrid route last; compare all against unchanged baseline |
| Exact content | Duplicate blobs; CCR hash store; artifact revision content | Artifact revisions authoritative; reuse CCR storage mechanics only behind artifact authorization and non-touching reads |
| Token budgets | Character heuristic; installed tokenizer | Installed `tiktoken` for declared encodings; explicit estimate plus conservative byte cap otherwise; never call an estimate exact |
| Evaluation | Existing runner; Inspect AI; new harness | Extend existing runner and use native public scorers; new Rush cases cover integration gaps |
| Embedding engine | Bundled ONNX/PyTorch; vector DB; configured service | Optional configured Ollama-compatible embedding endpoint through stdlib HTTP, with explicit model digest and grants; no new runtime dependency or default network use |

SQLite's FTS5 supports ranked queries and snippets. Contextual indexing is an established retrieval technique, but external results do not prove Rush gains. [SQLite FTS5](https://www.sqlite.org/fts5.html#sorting_by_auxiliary_function_results), [Anthropic contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval)

The optional service contract uses `/api/embed` with a string or batch input and `truncate=false`; validate returned vectors and reject silent truncation or changing model identity. [Ollama embedding API](https://docs.ollama.com/api/embed)

## 5. Requirement ledger

Every assessment suggestion is assigned below. Named test files/functions are specified in the owning task. `Mxx` refers to the deterministic scenario contract in the benchmark report. This ledger must be checked against actual files and calls before interpreting green tests.

| ID | Required behavior | Owner | Proof / benchmark |
|---|---|---|---|
| R01 | Scoped, validated, bounded two-stage recall; exact pagination and expansion | MC01–02 | `test_memory_retrieval.py`; M01–07; LongMemEval |
| R02 | Metadata-enriched lexical search, exact identifiers and paraphrases | MC02, MC12 | lexical/hybrid ranking tests; M01–02; held-out retrieval |
| R03 | Explicit versioned evidence links and bounded authorized traversal | MC03 | `test_memory_relations.py`; M04, M12, M15 |
| R04 | Delta handoff of goal, constraints, decisions and references; receiving read-back and replay safety | MC11 | `test_memory_handoff.py`; M24–25; live SDK/ACP lanes |
| R05 | One defended search, per-request shared-file validation, complete cache keys/invalidation | MC04 | `test_memory_efficiency.py`; M09–10; cold/warm profiles |
| R06 | Duplicate episode consolidation preserving originals, exceptions, contradictions and trust | MC03 | `test_memory_consolidation.py`; M04, M08; MemoryAgentBench |
| R07 | Measured token/byte ceilings and complete expansion/handoff/embedding costs | MC02, MC04, MC13 | budget and telemetry tests; M06; cost comparison |
| R08 | Optional embeddings and deterministic reranking evaluated against lexical misses | MC12 | `test_memory_hybrid.py`; M02, M27; held-out ablation |
| R09 | Confirmed user intent linked to executed behavior checks; explicit supersession | MC07 | `test_memory_intent.py`; M14–15; provider transfer |
| R10 | Condition-aware unsuccessful attempts and verified repairs affect next choice | MC05–06, MC13 | `test_memory_repairs.py`; M11–13, M30; SWE-derived episodes |
| R11 | Current project recipes, applicability, exceptions, source/test/dependency references | MC08 | `test_memory_recipes.py`; M16–17; feature-building episodes |
| R12 | Prioritize checks from measured regressions and coverage without dropping required gates | MC09 | `test_memory_check_plan.py`; M18–20; first-detection timing |
| R13 | Per-behavior/environment last-success; code/config/dependency comparison and verified cause | MC10 | `test_memory_last_success.py`; M21–23 |
| R14 | Tests/contracts/snapshots/E2E/mutation contribute observed evidence | MC05, MC09 | typed observation fixtures; executed checks, no tag-only proof |
| R15 | Codegraph/API/coverage inform source context and measured execution links | MC05, MC08–10 | stale API and dynamic-consumer fixtures |
| R16 | Security/dependency/license findings are version-bound and revisited after changes | MC05, MC09–10 | M20, M22; unresolved versus resolved evidence |
| R17 | Sandbox/verifier/provenance, continuity/checkpoints/token utilities participate in real route | MC05–06, MC10–11 | sandbox execution, original receipt identities, handoff trace |
| R18 | Scope/trust/redaction/concurrency/expiry rules survive summaries, caches and transfers | MC01–12 | denial and mutation regressions; M07, M26, M28–29 |
| R19 | Agent uses retrieved evidence to change subsequent action; final task quality measured | MC13 | M30; executable multi-session tasks, no scripted choice claim |
| R20 | CLI/MCP parity, catalog/config/docs, migration compatibility and real installed routes | MC14–15 | installed parity and public operation manifest tests |

## 6. Shared implementation contracts

### 6.1 Versioned authority and migration

Keep `memory.db` as authority. Add `artifact_version` starting at 1 for legacy rows, immutable `memory_artifact_versions`, a monotonically increasing transactional `memory_changes` sequence and deletion tombstones. A version captures content hash, subject/namespace, source, trust, origin and freshness anchors. An edit produces a new version; prior evidence cannot silently acquire new content or authority. Existing external IDs and durable origin uniqueness remain unchanged.

Migrations are explicit writes requiring `cache_write`. Open query-only connections without creating a DB, directory, journal or migrated schema. A legacy store that needs migration returns a structured migration-required result on the new routes; existing maintenance provides the authorized upgrade. Run migration in one transaction, validate existing rows, roll back on failure and preserve the original DB. Backfill does not promote imported content.

All mutation paths participate: `write`, `update_content`, `promote`, `delete`, migration replacement, expiry and maintenance. Compare-and-swap expected versions prevent lost updates. Trust/signature changes and invalidation update change sequence within the same transaction. Use named SQL columns, foreign-key enforcement, parameterized predicates and schema-version checks. Unknown future schema refuses mutation. Expiry hides content from normal retrieval but retains version identity needed for provenance and tombstones. Recovery never requires rewriting Git history.

Reuse existing family/subject vocabulary rather than adding parallel stores for each feature. Observations and repair episodes use `experience` with `episodic`/`failure`; intents use `memory` with `preference`/`architectural_decision`; recipes use `skill` with `skill_pattern`; capsules use `handoff` with `active_context`. Versioned content includes `schema_version=1` and an explicit `kind`, validated in the owning module. Trust values remain the existing `STATED`, `DERIVED`, `EXTERNAL_WRITE`, `IMPORTED`; terms such as candidate, verified and superseded are evidence/lifecycle states, not new trust tiers. Preserve every committed redacted content representation byte-for-byte per version; exact expansion means those stored bytes, not pre-redaction secret input or a reserialized approximation.

### 6.2 Retrieval and expansion

Add bounded mode to `ask`, `recall` and `list`; retain existing default response shape until callers opt into `view=compact`. New integrations always request compact mode. Defaults: `limit=8`, `max_tokens=2048`, `max_bytes=8192`, encoding `cl100k_base`; limits clamp to host configuration. Budgets include the serialized returned memory payload, metadata and cursor. If required envelope alone does not fit, return budget-too-small without content. MCP/JSON-RPC framing outside that payload is separately counted in telemetry.

Query scope includes repository namespace, subject, source allowlist, trust eligibility and expiry before rank/limit. Index contextual fields separately from original content: title/summary, symbol/path, error signature, behavior ID and applicable dependency identity. Do not write model-generated context into authoritative originals. Combine indexed fields using documented fixed BM25 weights, deterministic ID tie-breaking and bound parameters; malformed FTS input produces a validation error, not raw SQL execution.

Read candidate batches of 64. Validate integrity, unsafe characters, permissions and source anchors before selecting excerpts. Continue past rejected candidates until budget/limit is filled or a 512-candidate scan cap is reached. At the scan cap return a continuation cursor and explicit incomplete-search flag; never pretend no eligible result exists. Cursor binds query, source scope, namespace, store generation and ranking version. Any changed binding yields restart-required; no opaque global offset usable across scopes. Cursor is integrity protected using a workspace-local key created only during authorized initialization; permission rejection never creates one.

Compact items contain artifact ID/version, bounded excerpt, source reference, trust, freshness state, relationship IDs and expansion handle. Default retrieval excludes stale/superseded advice from actionable results; explicit historical mode returns labelled history and never satisfies cache/verification checks. Contradictory active records remain visibly unresolved, not silently selected by recency.

`expand(id, version, offset, max_tokens, max_bytes)` rechecks access, expiry, integrity and source freshness. It returns exact UTF-8 content slices with byte offsets, hash, version and continuation; never an inferred summary. Split only at valid UTF-8 boundaries. Version mismatch requires re-retrieval; raw hashes or CCR references do not bypass authorization. A read must use `CCRStore.retrieve(..., touch=False)` if CCR is involved. Revocation between pages blocks later pages. Counting uses the declared tokenizer; unsupported encodings are explicitly estimated and remain byte bounded.

### 6.3 Relations and consolidation

`memory_relations` stores source ID/version, target ID/version, kind, originating observation/user reference and creation sequence. Supported kinds: `supersedes`, `contradicts`, `caused_by`, `fixed_by`, `validated_by`, `implements`, `depends_on`. Direction is explicit; contradictions query both directions. Enforce endpoint existence and namespace policy. `supersedes` must remain acyclic. A claimed cause/fix is tagged claimed until an authorized execution receipt supports it; edge presence is not proof.

`related` defaults to depth 1, maximum depth 2 and 32 nodes, sharing caller token/byte budgets. Validate every endpoint, not just the seed. Changed or revoked endpoints invalidate active traversals. Do not disclose denied neighbor IDs, counts or source names.

`consolidate` creates a derived record with member IDs/versions, common conditions, distinct attempts, observed outcomes and exceptions. Group exact duplicate normalized episodes deterministically; semantic similarity may propose a group but cannot merge contradictory conditions automatically. Preserve originals and contradictory members. Derived trust cannot exceed supported member authority; repetition/model agreement never promotes it. An edited member invalidates the summary. Excerpts of originals remain exactly expandable. No background LLM summarizer or irreversible deletion.

### 6.4 Observed execution, trust and agent choice

Add `record_observation` after canonical execution and eligible special wrappers. It requires explicit `memory_record=true` configuration and host-granted `cache_write`; default is off. Store only normalized redacted fields, evidence references and content hashes. Observation failure is reported as a separate diagnostic without converting the original result or rerunning the tool. Memory/telemetry operations never recursively record themselves. Cached results reference original execution evidence and cannot create a fresh success.

Observation identity includes invocation/request ID, operation, normalized targets, workspace, exact source/patch/config/environment identities, engine/version, commands, result and provenance. Use `InvocationContext` and existing cache policy identity. Preserve ordered arguments and declared ignored inputs. Secret values become `[REDACTED]`; do not emit raw environment variables, credentials or unrestricted logs. Fingerprint relevant non-secret environment declarations and dependency lockfiles, not the entire process environment.

Normalize observations into five explicit capability families from R14–R17. Preserve the difference between structural links, measured coverage, executed results and claimed attribution. Missing fields are represented as absent with an explanatory evidence status; do not fabricate outcomes. ToolResult `ok` alone is insufficient to establish a behavior pass: it needs identified behavior, declared command, expected exit, observed exit and bound revision.

Add `verify-attempt` as a real memory operation. Input: structured JSON PatchContract, patch bytes/reference contained in workspace, attempt ID and declared behavior IDs. Require `artifact_write`, `cache_write` and every execution permission required by the declared checks; never infer permission from memory. Create an isolated sandbox through existing `PatchSandbox`, apply with existing applier, invoke `PatchVerifier`, capture command results and finalize observation. Do not promote the patch, modify source checkout, auto-commit or auto-rollback source. Always close subprocesses; clean sandbox according to existing lifecycle while preserving declared redacted receipt. Dirty-root precondition, drift, failed checks and unavailable commands are explicit non-success results.

Read-only `prepare` assembles task intent, relevant failures, recipes, ordered candidate checks and last-success differences within a shared budget. It does not execute arbitrary commands. A host agent consumes this pack, chooses an experiment and invokes existing tools or `verify-attempt`; `resume` returns the next compact pack from subsequent evidence. Actual provider tests must demonstrate a different next action. Deterministically appending logs or forcing a scripted choice is not an agent improvement result.

### 6.5 Repair, intent, recipe, checks and diagnosis

Repair episodes bind symptom/error signature, exact patch hash, attempted hypothesis, affected symbols, relevant dependency/config/environment identity and observed check outcomes. Exact repeated failure under identical conditions yields a warning plus evidence and a different untested hypothesis if one is explicitly recorded. Similarity yields candidates, never prohibition. Changed conditions permit retrial and explain mismatch. Revert messages and `is_fix` commits remain unverified attribution until supported by before/after execution.

Intent records distinguish confirmed user statement, inferred candidate and superseded statement. Only an explicit user-confirmation reference can establish confirmed intent. Resolve that reference to an existing locally authorized user-statement artifact from the current explicit user-stated promotion workflow; a caller-supplied `confirmed=true`, role label or free-form citation cannot establish authority. The existing content signature checks integrity, not user authorship. This route links established authority and does not manufacture proof of user authorship from model text. Require a behavior ID and current source/check bindings before describing it as verified. Keep rationale and exceptions. An explicit new instruction can supersede an old intent, but an agent preference, new timestamp or model agreement cannot. Tag-only traceability remains structural evidence.

Recipes carry purpose, applicability predicates, source IDs/hashes, dependency requirements, check IDs and exceptions. Resolve current code through graph/context packing at reuse; stale signatures or dependency mismatch return unusable recipe with reason. Reuse existing project library/code where applicable, not a copied frozen blob. A passed adaptation creates evidence for that adaptation, not universal endorsement.

Check planning takes changed targets and an immutable required-check set. Return the union of required checks and additional relevant candidates, deduplicated by command/cwd/environment identity. Order first by direct active intent/confirmed past regression links, then measured coverage, then structural graph proximity, then stable configured order. Historical duration breaks ties only. Never omit required checks because a short check passed. Unknown dynamic consumers remain an explicit coverage gap. Missing engines remain skipped and required coverage unresolved.

Last-success keys are behavior ID plus relevant environment identity, with source/config/dependency fingerprints stored as comparison subjects. A `memory_behavior_success` table maps that key to an exact observation artifact ID/version; it is an index over evidence, not a second source of truth. Only an observed pass of that behavior updates its pointer transactionally. Different code revisions remain comparable; incompatible environments appear separately. Diagnose compares current inputs to last success and lists supported differences, separating code, config, dependencies and engine availability. Correlation is a candidate. Label a cause reproduced only after a controlled sandbox comparison changes the outcome while other declared factors stay fixed.

### 6.6 Delta handoff and restricted receiving route

Envelope fields: schema version, handoff ID, sender/receiver namespace and audience, base receipt/cursor, goal, confirmed constraints, unresolved decisions, selected artifact IDs/versions, authorized changed records/tombstones, source references, budget and expiry. Default maximum envelope uses compact retrieval's 2048 tokens/8192 bytes. Oversize changes page with a stable snapshot and explicit pending tail. Never advance past unsent changes. Scope includes permission/config digest; widening scope requires a new initial snapshot.

Delivery states are `prepared`, `delivered`, `received`, `rehydrated`, `failed`. These are memory operation detail states, not new canonical ToolResult statuses. Only receiver read-back of exact authorized IDs/versions establishes `rehydrated` and advances acknowledged cursor. Delivery acknowledgement is insufficient. Retries are idempotent by handoff ID and page digest. Interrupted imports/receipts roll back atomically; duplicate pages do not duplicate artifacts, promote trust or skip deltas. Edits after snapshot appear in a later delta.

Current SDK/ACP dispatch denies tools. Preserve that default. Add explicit `memory_bridge=true` opt-in that configures a restricted stdio server using `rush mcp serve --memory-session <handoff-id>`. Its `build_server` mode exposes only `rush_memory` with `receive`, `expand`, `related` and `resume`; validates an expiring host-created session descriptor; clamps root, audience, IDs, versions, operations, output budgets and write grants. Receiver arguments cannot widen these. Store descriptors in a `memory_sessions` table in the authorized namespace's memory DB, keyed by handoff ID; pass a random 256-bit session capability through `RUSH_MEMORY_SESSION_TOKEN`, never command-line arguments or output, and store only its hash. Server cwd is the approved root; session ID never selects an arbitrary path. Expiry/revocation is checked for every request. Redact capability values from launch diagnostics. Unrelated tool requests are denied. Enable only this MCP configuration in supported native SDK and ACP adapters; preserve startup/cancellation cleanup and default deny-all behavior.

Same-namespace receive resolves existing versions. Cross-namespace receive imports immutable origin-tagged records at imported/candidate authority, never sender's user-confirmed authority. Missing exact evidence remains unresolved. File fallback produces a pending capsule until a receiver explicitly consumes it through the same route; no simulated receipt. Distinct source allowlists still govern expansion after transfer. Public `receive` without a valid session descriptor is denied.

### 6.7 Optional hybrid retrieval and measurements

Keep lexical default. `retrieval=hybrid` requires configured endpoint, exact model digest and explicit `network` permission, including loopback; persistence additionally requires `cache_write`. The configured endpoint must identify the requested model digest before embedding. No implicit model pull. No configuration/engine returns structured skipped for the hybrid attempt and an explicitly labelled lexical result; do not call it hybrid success.

Embed sanitized authorized scoped chunks in batches, `truncate=false`. Enforce timeout and input/response byte bounds; validate vector count, dimension, finite numbers and nonzero norm. Bind cached embeddings to namespace/source/version/content hash, model digest, dimension and chunking version. Model change invalidates affected vectors. Without cache-write, query may use already-valid vectors and ephemeral authorized embeddings; it must not persist or update LRU. Never send denied content to the embedding endpoint.

Use deterministic reciprocal-rank fusion `1/(60+lexical_rank) + 1/(60+vector_rank)` over bounded authorized candidates, with absent ranks contributing zero and ID tie-break. Bound vector candidates to 512 and report candidate truncation. Metadata and validation rules remain identical to lexical retrieval. No vector database, automatic learned trust or second reranking model. This is a real hybrid/reranking trial; its scope ceiling is measured and documented.

Record genuine call metrics for retrieval, expansions, relations, packing, handoff and embedding. Deduplicate by request/event identity. Separate measured provider usage from tokenizer counts and heuristics; count total episode costs without double counting. Telemetry writes require explicit opt-in/cache-write; response-local timing/counts remain possible on read-only routes.

## 7. Execution and TDD rules

Each task below is a repository-grounded feature task governed by §§5–6 and its own card. Execution order is **MC00 → MC01 → MC02 → MC03 → MC04 → MC05 → MC06 → MC07 → MC08 → MC09 → MC10 → MC11 → MC12 → MC14 → MC13 → MC15**. MC14 deliberately precedes MC13: real provider evaluations require the complete public operations and permission metadata. IDs group subject ownership, not permission to skip prerequisites. Sequence is serial where files overlap; no overlapping writers. Read every owned file before editing, using Graft for code and exact referenced spans. No task author may silently expand write scope; record an amendment to this plan first.

For each card: write the named failing assertions, run RED and capture the real contract failure, implement minimum production path, refactor, freeze exact bytes, run card checks, and review requirements against code/call sites before handoff. Any edit invalidates prior verdict. Missing imports alone are not sufficient RED evidence once the public seam exists. Receipts under `.scratch/memory-capabilities/MCxx.md` contain test command, failure assertion, fix, frozen hashes, GREEN results, review findings and unresolved external blockers. Commit only when explicitly authorized; do not use commits to imply acceptance.

Portable command notation: every `CHECK(file)` below means the following exact command from this worktree, substituting the literal named test path:

```bash
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH PYTHONPATH="$PWD/src" /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest file -q
```

This interpreter was used for baseline verification; verify it is Python 3.12 before execution. An absent/wrong interpreter is a named environment blocker, not permission to use Hermes' PATH environment. On Windows use repository `.venv/Scripts/python.exe` with cleared `VIRTUAL_ENV`/`PYTHONPATH` and current checkout's `src`. Use installed package tests without `PYTHONPATH` for installed-artifact evidence.

## 8. File Writes and ownership

### 8.1 Production and benchmark file map

All paths below are repository-relative. New files are explicitly marked. Shared files have ordered writers; final consistency is MC14's responsibility. No task owns an entire directory by wildcard.

| Owner | Authorized production / benchmark writes |
|---|---|
| MC00 | `scripts/benchmarks/run.py`, `scripts/benchmarks/contracts.py`, `scripts/benchmarks/fixtures.py`; new `scripts/benchmarks/memory.py`; new `tests/fixtures/benchmarks/memory_cases.json` |
| MC01 | `src/rush/memory/store.py`, `src/rush/memory/migration.py`, `src/rush/memory/expiry.py`, `src/rush/memory/maintenance.py` |
| MC02 | `src/rush/memory/store.py`, `src/rush/tools/memory.py`; new `src/rush/memory/retrieval.py` |
| MC03 | `src/rush/tools/memory.py`; new `src/rush/memory/relations.py`, `src/rush/memory/consolidation.py`; schema additions in `src/rush/memory/store.py` |
| MC04 | `src/rush/token_economy/memory_cache_gate.py`, `src/rush/tools/review.py`, `src/rush/continuity/context.py`, `src/rush/token_economy/telemetry.py`, `src/rush/memory/retrieval.py` |
| MC05 | `src/rush/invocation/executor.py`, `src/rush/invocation/models.py`, `src/rush/invocation/resolver.py`, `src/rush/cli_support/rendering.py`, `src/rush/mcp_support/tool_registry.py`, `src/rush/tools/memory.py`, `src/rush/config.py`, `src/rush/catalog.py`, `examples/rush.toml`, `docs/reference/configuration-reference.md` (only observation opt-in configuration); new `src/rush/memory/experience.py`, `src/rush/memory/verification.py` |
| MC06 | `src/rush/memory/experience.py`, `src/rush/memory/failure_ledger.py`, `src/rush/tools/memory.py` |
| MC07 | new `src/rush/memory/intent.py`; `src/rush/tools/memory.py`, `src/rush/memory/experience.py` |
| MC08 | new `src/rush/memory/recipes.py`; `src/rush/tools/memory.py` |
| MC09 | `src/rush/memory/verification.py`, `src/rush/tools/memory.py` |
| MC10 | `src/rush/memory/experience.py`, `src/rush/memory/store.py` for last-success index schema; `src/rush/tools/memory.py` |
| MC11 | new `src/rush/memory/handoff.py`; `src/rush/memory/store.py` for session/receipt schema; `src/rush/memory/transport.py`, `src/rush/mcp.py`, `src/rush/mcp_support/tool_registry.py`, `src/rush/cli.py`, `src/rush/tools/memory.py` |
| MC12 | new `src/rush/memory/embeddings.py`; `src/rush/memory/retrieval.py`, `src/rush/memory/store.py`, `src/rush/tools/memory.py` |
| MC13 | `scripts/benchmarks/run.py`, `scripts/benchmarks/memory.py`, `scripts/benchmarks/providers.py`, `scripts/benchmarks/reporting.py`; new `scripts/benchmarks/memory_datasets.py`, `tests/fixtures/benchmarks/memory_datasets.json` |
| MC14 | `src/rush/cli.py`, `src/rush/tools/memory.py`, `src/rush/mcp.py`, `src/rush/mcp_support/tool_registry.py`, `src/rush/catalog.py`, `src/rush/config.py`, `src/rush/governance/public_operations.py`, `governance/public-operations.toml`, `examples/rush.toml` |
| MC15 | No production writes. Acceptance tests/receipt only; defects return to owning card and invalidate affected verification |

Existing graph, patch, continuity receipt, CCR and prompt evaluation implementations are reuse/read dependencies unless specifically listed above. Do not modify unused legacy prototypes to imitate a missing engine. If reuse requires an actual API change, name its callers, add its literal file/test to this ledger and review that amendment before implementation.

### 8.2 Tests, fixtures and documentation

Each card owns its named `tests/test_memory_*.py` or `tests/test_benchmark_memory*.py` file and may add its assigned Mxx cases to the single shared JSON fixture in serial order. Use `tmp_path` to materialize minimal real Python projects from fixture data. This avoids an unbounded new fixture tree. Preserve existing phase61/62 regression tests; do not replace them with permissive new assertions.

MC14 owns updates to `docs/API_REFERENCE.md`, `docs/CLI_REFERENCE.md`, `docs/reference/cli-reference.md`, `docs/MCP.md`, `docs/MCP_REFERENCE.md`, `docs/TOOL_CATALOG.md`, `docs/reference/configuration-reference.md`, `docs/reference/configuration-cookbook.md` and new `docs/developer/memory-capabilities.md`. User reference updates follow working routes and explain required input, visible output, permission failure/recovery and one executable example. Internal architecture belongs in the developer document. No blanket user-doc rewrite.

MC00/MC13 own benchmark-strategy corrections supported by actual evidence. Every task updates only its status/evidence row in §11 and its receipt. MC15 owns final reconciliation of this plan and benchmark report. `docs/phase-plans/README.md` links the proposed plan without changing other phase status. No dependency additions are planned; `pyproject.toml` and lockfile are protected unless an explicitly reviewed amendment establishes necessity.

## 9. Execution tasks

This is the implementation queue. Execute MC00–MC12, then MC14, MC13, MC15. Each numbered checkbox specifies work to perform. Sections 5–8 supply binding invariants and literal write boundaries; they do not replace these actions.

CHECK(path) means the executable command in §7 with that literal test path. Capture RED before implementation, freeze after edits, then run GREEN and review. Every packet writes .scratch/memory-capabilities/MCxx.md with failing assertion, exact commands/results, frozen hashes and review findings. These are future outputs; writing this plan creates no implementation evidence.

### 9.0 Fixed contracts and fixtures

**Operation envelope.** Add request: dict[str, Any] | None to MemoryTool.__call__ and MemoryTool.run. New operations accept this same object through MCP and CLI --input FILE. Unknown keys, missing required fields and wrong types are errors, not silent coercions. Keep existing calls/output unchanged. New operation payloads occupy existing ToolResult.raw:

    {"schema_version":1,"operation":"expand","code":"OK","data":{}}

Use existing MemoryTool._result and metadata.operation. Status/code pairs: ok/OK; error/E_INPUT; fail/E_PERMISSION; fail/E_NOT_VISIBLE; fail/E_VERSION; warn/E_MIGRATION; warn/E_RESTART; warn/E_BUDGET; warn/E_UNAVAILABLE. Missing and denied artifact IDs return identical E_NOT_VISIBLE bodies. An unavailable hybrid attempt with usable lexical results returns warn/E_EMBEDDING_UNAVAILABLE, data.retrieval="lexical" and data.embedding_status="skipped".

**Ranking constants.** FTS columns in order: title, symbol_path, error_signature, behavior_id, dependency_identity, body. BM25 weights: 4, 8, 8, 6, 3, 1. Lower SQLite score first; artifact ID ascending breaks ties. Hybrid uses §6.7 RRF. These are experimental constants to measure, not asserted optimal weights.

**Condition identity.** Require runtime (implementation and major/minor version), platform (OS and architecture), dependencies (package→resolved-version map), config_digest and source_digest. Hash canonical sorted compact JSON. Repair equality compares every field; missing fields produce match="incomplete", never same-conditions warning. Last-success lookup keys runtime/platform; source/config/dependencies remain comparison dimensions so dependency drift can be diagnosed against previous success. Different runtime/platform cannot silently replace current success.

**Concrete fixtures.** Store definitions in tests/fixtures/benchmarks/memory_cases.json and materialize with pytest tmp_path; no new fixture runner. Use allowed source "allowed", denied source "denied", artifact IDs A1/A2/D1. Hash actual written source/config bytes. Runtime is cpython/3.12, platform test/test, dependency map {"parser":"1.0"}.

| Fixture | Exact source/input and edit | Expected result |
|---|---|---|
| Upload | def upload(size, timeout=30): return size <= 10; check assert upload(20). Patch one changes only timeout to 60. Patch two changes limit to 25. | Original and timeout patch exit 1; size-limit patch exits 0. |
| Guest checkout | def can_buy(has_account): return True; check assert can_buy(False). Regression returns has_account instead. | Original passes; regression fails with unchanged FR/REQ tags. |
| CSV recipe | Existing csv.writer helper using io.StringIO(newline=""); rows [["id","total"],["I-1","12.50"]]. | Exact text id,total followed by CRLF, I-1,12.50 followed by CRLF; unauthorized caller rejected; dependency manifest unchanged. |
| Payload rename | def payload(): return {"customer_id":7}; check assert payload()["customer_id"] == 7. Rename key to client_id. | Contract check fails; all other required checks still execute. |
| Diagnosis | Passing Upload limit 25; independently change limit to 10, parser dependency to 2.0, config digest, or engine availability. | Only changed dimension reported; cause reproduced only after actual controlled execution. |

### MC00 — Add a runnable memory benchmark probe

**Owned writes:** MC00 paths in §8.1; tests/test_benchmark_memory.py.

**Required test functions:** `test_memory_probe_uses_real_store`, `test_memory_baseline_records_over_budget_payload`, `test_memory_probe_keeps_denied_content_out_of_results`, `test_memory_probe_rejects_fixture_path_escape`.

1. [ ] **MC00.1 — Write RED tests.** Add test_memory_probe_uses_real_store and test_memory_baseline_records_over_budget_payload. Seed 100 matching artifacts of 512 ASCII characters; call current MemoryTool. Assert count 100 and serialized payload >8192 bytes. Missing probe fails RED; do not truncate baseline.
2. [ ] **MC00.2 — Create run_memory_probe.** In scripts/benchmarks/memory.py, materialize SQLite/source fixtures, call actual MemoryTool and measure serialized bytes, token method and elapsed time. Produce existing ProbeResult with source/scenario hashes; never copy expected fixture metrics into observed results.
3. [ ] **MC00.3 — Register memory category.** Extend get_probe_runner in scripts/benchmarks/run.py. Add M01/M03/M05/M06/M09/M10 fixture records. Reuse Scenario validation and result writer; keep existing IDs/status schema unchanged.
4. [ ] **MC00.4 — Test denial and capture baseline.** Put denied D1 ahead of allowed A1; assert D1 ID/text absent. Pass ../outside.json to fixture loader; assert rejection before reading. Capture full-suite baseline at frozen 997b56e with exact failures and interpreter identity.
5. [ ] **MC00.5 — Run GREEN and review.** CHECK(tests/test_benchmark_memory.py); CHECK(tests/test_benchmark_runner.py). Verify metrics originate in actual calls. Record baseline command/corpus hash/results in MC00.md.

### MC01 — Version artifacts and make every mutation atomic

**Owned writes:** MC01 paths in §8.1; tests/test_memory_versions.py.

**Required test functions:** `test_legacy_migration_preserves_ids_origins_and_trust`, `test_read_only_open_creates_no_files`, `test_content_promotion_expiry_and_delete_advance_sequence`, `test_migration_failure_rolls_back`, `test_concurrent_expected_version_rejects_lost_update`.

1. [ ] **MC01.1 — Write RED migration/concurrency tests.** Migrate legacy A1 and assert ID/origin/trust preserved at version 1. Two connections read version 1; first writes version 2; second updates with expected_version=1. Assert E_VERSION, unchanged version 2 and no extra change row.
2. [ ] **MC01.2 — Add schema and read-only opening.** In store.py add artifact_version, memory_artifact_versions keyed by artifact ID/version with exact content/provenance, and memory_changes keyed by monotonic sequence. Add TypedArtifactStore.open_readonly using SQLite read-only mode; absent DB creates no directory/file. Old schema on new compact routes yields E_MIGRATION.
3. [ ] **MC01.3 — Route all writes through one transaction.** Add _write_version in store.py. Update write, update_content, promote, delete, promote_stored_artifact, migration.replace_origin_content, expiry and maintenance writes. Increment once per real semantic change; identical import stays no-op; delete creates tombstone.
4. [ ] **MC01.4 — Add rollback/denial assertions.** Implement read-only, migration rollback, mutation-sequence, legacy-origin and concurrent-update tests named in this packet's RED. Inject failure mid-migration and assert original schema/data still usable, with no half-migrated rows. Compare filesystem before/after denied open.
5. [ ] **MC01.5 — Run GREEN and inspect SQL paths.** CHECK(tests/test_memory_versions.py); CHECK(tests/test_memory_compatibility_regressions.py). Check every listed mutation has a transaction/version assertion. Record schema/recovery evidence in MC01.md.

### MC02 — Implement bounded recall and exact expansion

**Owned writes:** MC02 paths in §8.1; tests/test_memory_retrieval.py.

**Required test functions:** `test_authorized_result_survives_denied_rank_prefix`, `test_corrupt_candidates_do_not_starve_page`, `test_scan_cap_returns_continuation`, `test_serialized_payload_obeys_both_caps`, `test_unicode_expansion_reconstructs_exact_original`, `test_revoked_or_changed_version_cannot_expand`, `test_cursor_rejects_scope_or_generation_change`, `test_legacy_memory_response_remains_compatible`.

1. [ ] **MC02.1 — Write RED page tests.** Seed 70 corrupt candidates before valid A1/A2, denied D1, and a separate 513-candidate corpus. Assert valid IDs survive filtering, no D1 content, continuation after scan cap 512, and complete serialized output within requested token/byte limits.
2. [ ] **MC02.2 — Add scoped candidate query.** In store.py add search_candidates with namespace/subject/source/trust/expiry filters before rank/LIMIT. Add §9.0 FTS columns/weights, parameterized query and ID tie-break. Fetch 64 candidates per batch; remove full-row fetchall from compact path.
3. [ ] **MC02.3 — Add recall_page and expand_artifact.** In new retrieval.py return page fields items, next_cursor, complete, tokens, bytes, encoding. Items contain id/version/excerpt/source/trust/freshness/relations. Wire compact query and expand through MemoryTool request. Defaults: 8 results, 2048 tokens, 8192 bytes. Existing legacy calls unchanged.
4. [ ] **MC02.4 — Test exact bytes and revoked access.** Expand stored content containing é, 中 and 🙂 over multiple pages; concatenated bytes must equal stored version bytes. Change version/scope/generation between calls; assert E_VERSION/E_NOT_VISIBLE/E_RESTART without content leakage. Test too-small envelope budget and legacy shape.
5. [ ] **MC02.5 — Run GREEN and inspect outputs.** CHECK(tests/test_memory_retrieval.py); CHECK(tests/test_benchmark_memory.py). Review envelope-inclusive accounting and scope predicates. Record exact page/expansion examples in MC02.md.

### MC03 — Store evidence edges and consolidate duplicate episodes

**Owned writes:** MC03 paths in §8.1; tests/test_memory_relations.py and tests/test_memory_consolidation.py.

**Required test functions:** `test_supersedes_cycle_rejected_atomically`, `test_related_hides_denied_neighbors`, `test_related_depth_node_and_token_caps`, `test_relation_version_change_invalidates_active_evidence`, `test_duplicate_summary_preserves_originals_and_exception`, `test_repetition_cannot_promote_trust`, `test_contradictory_conditions_are_not_merged`.

1. [ ] **MC03.1 — Write RED edge tests.** Insert A1@1 supersedes A2@1; inverse edge must fail atomically. Link to denied D1; related output reveals no ID/count for it. Build chains beyond depth 2 and 32 nodes; assert caps.
2. [ ] **MC03.2 — Implement edge storage/traversal.** Add memory_relations schema in store.py. Implement add_relation and related_artifacts in relations.py with versioned endpoints, provenance, supported kinds, cycle prevention and per-node authorization. Wire link/related in MemoryTool; link requires cache_write.
3. [ ] **MC03.3 — Implement consolidate_episodes.** In consolidation.py group equal canonical symptom/condition/attempt/outcome tuples. Store derived summary with member versions, repetition count and distinct-condition exceptions. Wire consolidate with cache_write; preserve original rows.
4. [ ] **MC03.4 — Test preservation.** Three identical failed timeout episodes plus one changed-condition success must retain all four IDs, report repeat count 3 and retain success as exception. Assert no trust promotion, no contradictory-condition merge, summary invalidation after member edit, and exact original expansion.
5. [ ] **MC03.5 — Run GREEN and review.** CHECK(tests/test_memory_relations.py); CHECK(tests/test_memory_consolidation.py). Inspect version/provenance bindings; record edges/summary/original-byte assertions in MC03.md.

### MC04 — Remove duplicate retrieval work and count actual costs

**Owned writes:** MC04 paths in §8.1; tests/test_memory_efficiency.py.

**Required test functions:** `test_cache_and_review_do_one_defended_search`, `test_shared_source_validated_once_per_request`, `test_same_size_source_edit_invalidates_next_request`, `test_cache_key_changes_with_budget_scope_and_tokenizer`, `test_producer_hash_not_replaced_by_later_read`, `test_expansion_and_handoff_costs_are_not_double_counted`, `test_read_only_recall_never_persists_telemetry`.

1. [ ] **MC04.1 — Write RED work-count tests.** Two artifacts share one source. Exercise check_memory_before_pack and review citation path; assert one defended query and one source read/hash per request while returned evidence stays correct.
2. [ ] **MC04.2 — Replace duplicate paths.** Make cache gate/review consumers use defended retrieval directly instead of search then recall. Add request-local canonical-path→bytes/hash/API-analysis memo in retrieval.py. Discard after request; retain ContextPacker producer-read hash.
3. [ ] **MC04.3 — Complete keys/events.** Include query, target/symbol, source hash, namespace, audience/trust policy, config, view, encoding, budgets and engine/normalizer revisions in cache identity. Add actual retrieval/expansion/packing/handoff/embedding events to TelemetryStore; deduplicate request/event IDs and require opt-in/cache_write for persistence.
4. [ ] **MC04.4 — Add invalidation/accounting tests.** Same-size source edit must invalidate next request. Changed scope/budget/tokenizer must miss cache. Expansion events of 10 and 20 tokens sum to 30; replay does not increase total. Read-only recall leaves telemetry files unchanged; producer hash cannot be replaced by later read.
5. [ ] **MC04.5 — Run GREEN and review counts.** CHECK(tests/test_memory_efficiency.py); CHECK(tests/test_memory_retrieval.py). Record baseline/new SQL/read/token counts in MC04.md; count reduction alone is not a latency claim.

### MC05 — Capture observations and expose real sandbox verification

**Owned writes:** MC05 paths in §8.1; tests/test_memory_observations.py and tests/test_memory_verify_attempt.py.

**Required test functions:** `test_observer_covers_cli_mcp_without_duplicates`, `test_observer_off_or_denied_writes_nothing`, `test_cached_result_keeps_original_execution_identity`, `test_five_capability_families_preserve_evidence_kind`, `test_secret_redaction_precedes_persistence`, `test_failed_observation_preserves_original_tool_failure`, `test_verify_attempt_runs_real_command_in_sandbox`, `test_verify_attempt_rejects_drift_and_missing_permissions`, `test_unavailable_check_never_records_success`.

1. [ ] **MC05.1 — Write RED route tests.** Invoke handlers through _run_tool, make_tool_wrapper and make_custom_wrapper. With recording/cache_write assert one observation each, exact request/operation identity. Recording off or cache_write denied produces none; cache hit produces no new execution-success record.
2. [ ] **MC05.2 — Add one canonical observer and its opt-in input.** Add memory_record: bool = False to InvocationContext in invocation/models.py; populate it in resolver.py from resolved tools.memory configuration, not arbitrary result text. Add that single configuration key/default to config.py, catalog.py, examples/rush.toml and configuration-reference.md now; MC14 adds remaining keys later. In InvocationExecutor.execute capture result after handler returns and before result-cache write; call experience.record_observation once only when context.memory_record and context.permissions.cache_write are true. Cache-hit branch preserves original receipt identity. Rendering/MCP wrappers use this resolver/executor and never record duplicates.
3. [ ] **MC05.3 — Add normalization and verify-attempt.** In experience.py record canonical result, target/engine/version, conditions and real evidence references. In verification.py add verify_attempt accepting attempt_id, behavior_ids, existing PatchContract and patch. Require cache_write/artifact_write/build plus declared check permissions; call existing sandbox, applier and PatchVerifier.verify_patch. Wire MemoryTool; exclude memory operations from generic observer recursion.
4. [ ] **MC05.4 — Execute real checks and negative cases.** Run Upload timeout and size-limit patches: exits 1 then 0, source checkout unchanged, receipt identities exact, children closed. Test secret redaction before storage, write failure preserving original result, drift, missing grant and unavailable command. Plain status=ok without command evidence cannot establish behavior pass.
5. [ ] **MC05.5 — Run GREEN and inspect call path.** CHECK(tests/test_memory_observations.py); CHECK(tests/test_memory_verify_attempt.py). Record actual command→receipt path and exact three transport-entry tests in MC05.md. No route-inventory/discovery task is delegated.

### MC06 — Recall failed repairs by exact conditions

**Owned writes:** MC06 paths in §8.1; tests/test_memory_repairs.py.

**Required test functions:** `test_same_failed_timeout_patch_returns_evidence`, `test_dependency_change_permits_retrial`, `test_verified_size_limit_fix_links_regression_check`, `test_revert_and_fix_label_do_not_prove_cause`, `test_failed_and_successful_conditions_remain_distinct`, `test_prepare_exposes_untested_hypothesis_without_executing`.

1. [ ] **MC06.1 — Write RED repair queries.** Record timeout failure T1 and verified size-limit repair S1 under §9.0 conditions. Query same symptom/conditions; assert warning references T1, verified alternative references S1, neither claims a new execution.
2. [ ] **MC06.2 — Add episode matching.** Implement record_attempt and recall_repair_episodes in experience.py. Require symptom, hypothesis, patch_hash, conditions, receipt_ref and behavior_ids. Same patch plus complete equal conditions gives match=same; missing fields gives incomplete; changed fields gives changed. Preserve FailureLedger's existing exact-hash callers.
3. [ ] **MC06.3 — Wire prepare/resume.** Add prepare_memory returning bounded failures, verified_repairs, untested_hypotheses and evidence_refs. Hypotheses must be explicitly recorded. Wire MemoryTool prepare/resume; execute no commands and never automatically prohibit a patch.
4. [ ] **MC06.4 — Add conditions/attribution tests.** Change parser dependency to 2.0: old failure must be changed and retrial permitted. Revert/fix-labelled commits without receipts remain candidates. Distinct success/failure conditions stay separate. Assert prepare caused zero subprocess calls.
5. [ ] **MC06.5 — Run GREEN and review.** CHECK(tests/test_memory_repairs.py); CHECK(tests/test_memory_verify_attempt.py). Record exact same/changed/incomplete responses and check links in MC06.md.

### MC07 — Store confirmed intent and verify its behavior

**Owned writes:** MC07 paths in §8.1; tests/test_memory_intent.py.

**Required test functions:** `test_inferred_preference_cannot_confirm_itself`, `test_guest_checkout_break_detected_by_execution`, `test_trace_tag_is_not_behavioral_verification`, `test_explicit_user_change_supersedes_old_intent`, `test_agent_timestamp_cannot_supersede_user_intent`, `test_intent_check_bound_to_current_revision`.

1. [ ] **MC07.1 — Write RED intent tests.** Create Guest checkout fixture and authorized local STATED artifact requiring guest purchase. Record intent guest-buy with statement version, behavior ID, source/check refs. Assert confirmation only from that resolvable authorized reference.
2. [ ] **MC07.2 — Implement mutations.** Add record_intent and supersede_intent in intent.py. Fields: intent_id, statement_ref, behavior_id, source_refs, check_refs, exceptions. Inferred record lacks statement_ref and stays candidate. Supersession requires new authorized statement and expected old version; retain prior rationale/evidence.
3. [ ] **MC07.3 — Wire reads into prepare.** Add intent_evidence and MemoryTool intent create/confirm/supersede/check. Check returns exact-revision execution evidence or unresolved; it does not launch a command. Include active relevant intent/check refs in prepare_memory.
4. [ ] **MC07.4 — Execute behavior/authority cases.** Original Guest checkout passes, regression fails despite unchanged tags. Caller confirmed=true, newer agent timestamp and imported role labels cannot confirm/supersede. Explicit new authorized account-required instruction supersedes old requirement without deleting its history.
5. [ ] **MC07.5 — Run GREEN and review.** CHECK(tests/test_memory_intent.py); CHECK(tests/test_memory_relations.py). Record statement refs, real exits and supersession output in MC07.md.

### MC08 — Resolve recipes against current source and dependencies

**Owned writes:** MC08 paths in §8.1; tests/test_memory_recipes.py.

**Required test functions:** `test_csv_export_recipe_uses_current_project_implementation`, `test_api_change_rejects_stale_recipe`, `test_dependency_or_applicability_mismatch_explained`, `test_recipe_keeps_authorization_and_error_handling_checks`, `test_adaptation_pass_does_not_prove_universal_recipe`.

1. [ ] **MC08.1 — Write RED CSV recipe fixture.** Record invoice-csv purpose, helper source/hash, required symbols/dependencies, checks and unauthorized-caller exception. Resolve and assert current helper and authorization/error checks are returned.
2. [ ] **MC08.2 — Implement record/resolve.** Add record_recipe and resolve_recipe in recipes.py. Applicability fields are required_symbols, required_dependencies and required_config_digest. Every declared predicate must match; empty lists/maps impose no predicate. Resolve current code through graph/context pack; source/signature mismatch makes recipe unusable with reason.
3. [ ] **MC08.3 — Wire recipe outcomes.** Add MemoryTool recipe record/resolve/record-outcome and record_recipe_outcome. Outcome requires recipe version, adaptation patch hash and real verifier receipt; bare passed=true is invalid.
4. [ ] **MC08.4 — Execute adaptation/staleness tests.** Adapt helper for invoice rows in sandbox; assert exact §9.0 CSV bytes, unauthorized failure and unchanged dependency manifest. Change API signature and dependency version separately; both reject recipe. One passing adaptation cannot remove exception or promote trust.
5. [ ] **MC08.5 — Run GREEN and review.** CHECK(tests/test_memory_recipes.py); CHECK(tests/test_memory_retrieval.py). Record exact output/manifest hashes and rejection reasons in MC08.md.

### MC09 — Rank checks without dropping required verification

**Owned writes:** MC09 paths in §8.1; tests/test_memory_check_plan.py.

**Required test functions:** `test_past_payload_regression_prioritizes_contract_check`, `test_required_checks_remain_after_early_pass`, `test_dynamic_consumer_gap_is_explicit`, `test_missing_engine_keeps_required_check_unresolved`, `test_security_license_version_change_reopens_finding`, `test_mutation_observation_is_not_invented_coverage`.

1. [ ] **MC09.1 — Write RED order fixture.** Required checks: slow-general, payload-contract, checkout. Prior observed regression links payload-contract to changed field. Assert plan begins payload-contract and retains all three exactly once.
2. [ ] **MC09.2 — Implement plan_checks.** Evidence ranks: active intent/observed regression=0, measured coverage=1, structural relation=2, configured-only=3. Sort by rank, measured duration (missing last), original configured position. Deduplicate exact argv/cwd/environment identity; never change required membership.
3. [ ] **MC09.3 — Wire input/output and evidence.** MemoryTool plan-checks accepts changed_targets, required_checks, environment. Return checks with reasons/refs, required_ids, coverage_gaps. Use observed mutation/coverage links and version-bound security/dependency/license findings; graph heuristics cannot become measured coverage.
4. [ ] **MC09.4 — Execute all checks and gaps.** Payload rename must fail contract check first while later required checks still run. Missing required engine stays unresolved/skipped. Package version change invalidates old security/license resolution. Unmeasured dynamic consumer produces coverage gap.
5. [ ] **MC09.5 — Run GREEN and review.** CHECK(tests/test_memory_check_plan.py); CHECK(tests/test_memory_observations.py). Record order, required set and actual first-detection timing in MC09.md.

### MC10 — Compare current failure to last successful behavior

**Owned writes:** MC10 paths in §8.1; tests/test_memory_last_success.py.

**Required test functions:** `test_success_is_per_behavior_and_environment`, `test_skipped_or_cached_check_cannot_advance_success`, `test_code_dependency_and_config_changes_are_distinguished`, `test_unavailable_engine_is_not_application_regression`, `test_only_controlled_reproduction_confirms_cause`, `test_later_failure_does_not_destroy_last_success`.

1. [ ] **MC10.1 — Write RED pointer tests.** Record Upload pass then failure; pointer stays at pass. Record another behavior and runtime; neither overwrites Upload/runtime's last-success entry.
2. [ ] **MC10.2 — Implement indexed success.** Add memory_behavior_success schema keyed namespace/behavior/runtime-platform digest, holding observation ID/version. Implement record_behavior_success in same transaction as actual executed pass. Cache hit, skip, tag or caller label cannot update pointer.
3. [ ] **MC10.3 — Add diagnosis functions/routes.** Implement compare_last_success and record_cause_experiment; wire last-success/diagnose. Return baseline_ref, code_changes, config_changes, dependency_changes, engine_changes, environment_compatible and cause_state. Default candidate; reproduced requires controlled execution refs.
4. [ ] **MC10.4 — Execute isolated comparison cases.** Change code, dependency, config and availability separately; assert only corresponding delta populated. Run limit 25 versus 10 under identical other conditions; pass/fail evidence permits reproduced cause. Unavailable experiment remains candidate.
5. [ ] **MC10.5 — Run GREEN and review.** CHECK(tests/test_memory_last_success.py); CHECK(tests/test_memory_verify_attempt.py). Record scoped pointers and controlled-run receipts in MC10.md.

### MC11 — Rehydrate bounded deltas through a restricted receiver

**Owned writes:** MC11 paths in §8.1; tests/test_memory_handoff.py.

**Required test functions:** `test_delta_contains_only_changed_authorized_versions`, `test_delivery_ack_does_not_advance_cursor`, `test_receiver_reads_exact_versions_before_ack`, `test_partial_page_and_replay_are_atomic`, `test_scope_change_requires_new_snapshot`, `test_bridge_denies_unrelated_tools_and_scope_widening`, `test_imported_prompt_injection_cannot_widen_permissions`, `test_expired_session_capability_denies_every_operation`, `test_default_transport_still_denies_all_tools`, `test_cross_namespace_import_does_not_copy_authority`, `test_cancelled_receiver_leaks_no_process`, `test_guest_intent_and_last_success_survive_readback`.

1. [ ] **MC11.1 — Write RED delta/ACK tests.** After acknowledged A1@1, add A1@2, A2@1 and denied D1. H1 contains exactly A1@2/A2@1 plus approved goal/constraints. Delivery ACK cannot advance cursor; exact receiver read-back can.
2. [ ] **MC11.2 — Implement transactional sessions/receipts.** Add prepare_handoff, receive_handoff, acknowledge_readback and session/receipt schema. Descriptor expires after 15 minutes; freeze time in tests. Bind root/audience/versions/grants/budgets; store capability hash. Identical replay is idempotent; same ID/different digest fails atomically; partial receipt cannot skip unseen changes.
3. [ ] **MC11.3 — Wire real receiver configuration.** Add dispatch_handoff and MemoryTool handoff actions. Add rush mcp serve --memory-session ID; build_server exposes only restricted rush_memory receive/expand/related/resume. transport.dispatch configures that MCP server for native SDK/ACP only with memory_bridge=true, capability through environment; default still denies all tools.
4. [ ] **MC11.4 — Run actual local stdio cases.** Receiver calls receive and expands exact versions before ACK. Test interrupted imports, replay, expiry, wrong token, scope widening, prompt injection and cancellation cleanup. Transfer Guest intent/last-success refs; cross-namespace statements stay imported. No fake peer result counts as live-provider evidence.
5. [ ] **MC11.5 — Run GREEN and review.** CHECK(tests/test_memory_handoff.py); CHECK(tests/test_phase61_transport.py); CHECK(tests/test_phase62_handoff_diff.py). Record process/read-back/state evidence in MC11.md.

### MC12 — Add configured embeddings and deterministic hybrid ranking

**Owned writes:** MC12 paths in §8.1; tests/test_memory_hybrid.py.

**Required test functions:** `test_hybrid_retrieves_lexical_paraphrase_miss`, `test_rrf_order_is_deterministic`, `test_denied_source_never_sent_to_endpoint`, `test_missing_engine_reports_lexical_fallback_explicitly`, `test_model_digest_change_invalidates_vectors`, `test_nonfinite_wrong_dimension_or_truncated_embedding_rejected`, `test_read_only_hybrid_never_persists_vectors`.

1. [ ] **MC12.1 — Write RED vector cases.** Query [1,0], paraphrase A1 [1,0], lexical A2 [0,1], denied D1 [1,0]. Lexical order A2/A1 and vector order A1/A2 yield equal RRF and A1-first ID tie-break. Separate lexical-miss fixture must recover A1; D1 never reaches adapter.
2. [ ] **MC12.2 — Implement HTTP adapter.** Add embed_chunks/validate_embedding_response in embeddings.py. Use stdlib HTTP, /api/embed, digest-verified configured model, truncate=false, timeout 10 seconds, ≤32 inputs/request, response cap 1 MiB. Require network; no download. Reject wrong count/dimension, non-finite and zero-norm vectors.
3. [ ] **MC12.3 — Persist versioned vectors and fuse.** Key by namespace/artifact version/content hash/model digest/chunking version. Add hybrid_candidates using cosine rank and §6.7 RRF; scope before embedding and validate after selection. Wire retrieval=hybrid; missing engine yields explicit lexical fallback.
4. [ ] **MC12.4 — Test invalidation and denial.** Change model digest/content independently; prior vectors unusable. Test malformed response, timeout, missing engine and denied source. Cache-write false leaves DB/files unchanged. Real configured-engine run is separate evidence from fixed-vector tests.
5. [ ] **MC12.5 — Run GREEN and review.** CHECK(tests/test_memory_hybrid.py); CHECK(tests/test_memory_retrieval.py). Record exact ranking values, denied-source assertion and real engine evidence/blocker in MC12.md.

### MC14 — Expose identical CLI/MCP operations and document them

**Execute before MC13. Owned writes:** MC14 paths in §8.1 and documents in §8.2; tests/test_memory_public_contract.py and tests/test_memory_operation_metadata.py.

**Required test functions:** `test_cli_mcp_operation_payload_and_permissions_match`, `test_all_memory_operations_in_public_manifest`, `test_legacy_cli_and_mcp_calls_remain_valid`, `test_config_rejects_unknown_memory_keys`, `test_read_operations_do_not_gain_write_permission`, `test_stdio_stdout_contains_only_jsonrpc`, `test_documented_examples_execute`.

1. [ ] **MC14.1 — Write RED parity matrix.** Parameterize all 14 new leaves from §9.1. Call each through Click and MCP with same request; assert identical status/raw after excluding duration. Missing mutation grants must fail equally.
2. [ ] **MC14.2 — Add argument wiring.** Add CLI leaves; parse --input FILE once into request and call shared MemoryTool. Simple flags translate into same request. Add required allow_artifact_write/build/slow/network/browser public callable flags to construct existing ExecutionPermissions, all default false. No transport-only business logic.
3. [ ] **MC14.3 — Synchronize registries/config.** Update catalog.py, config.py, public_operations.py and governance/public-operations.toml. Accept exactly §9.1 configuration keys/defaults; reject unknown keys. Update examples/rush.toml in same packet; preserve rush_memory MCP name and legacy calls.
4. [ ] **MC14.4 — Write and execute examples.** Update exact reference/configuration files from §8.2 plus developer document. Run compact recall→expand, isolated repair and restricted handoff examples against fixtures. Assert stdio stdout contains only JSON-RPC. Examples cannot claim unmeasured benefit.
5. [ ] **MC14.5 — Run GREEN and review.** CHECK(tests/test_memory_public_contract.py); CHECK(tests/test_memory_operation_metadata.py); CHECK(tests/test_catalog.py); CHECK(tests/test_config.py); CHECK(tests/test_phase51_public_operations.py); CHECK(tests/test_phase57_public_operations.py). Record manifest diff/examples in MC14.md.

### MC13 — Execute public benchmarks and real agent episodes

**Owned writes:** MC13 paths in §8.1; tests/test_benchmark_memory_datasets.py and tests/test_benchmark_memory_agents.py.

**Required test functions:** `test_longmemeval_gold_fields_never_reach_agent`, `test_dataset_revision_and_hash_required`, `test_independent_cases_reset_namespace`, `test_native_prediction_schema_preserved`, `test_timeout_and_budget_exhaustion_stay_in_denominator`, `test_real_episode_uses_observed_tool_events`, `test_all_expansions_count_toward_episode_budget`, `test_handoff_score_requires_receiver_readback`.

1. [ ] **MC13.1 — Write RED dataset tests.** LongMemEval-shaped fixture includes answer, answer_session_ids and nested has_answer. Assert none reaches agent/ingestion; dates/session IDs remain. Require URL/revision/SHA256/terms/split; hash mismatch fails before execution. Assert native question_id/hypothesis output.
2. [ ] **MC13.2 — Implement adapters and flags.** In memory_datasets.py add LongMemEval, MemoryAgentBench, SWE prediction and LongMemEval-V2 compatibility transforms. Extend existing runner with --suite memory, --variant, --dataset-manifest, --seeds, --max-total-tokens. Reset namespace per independent case; retain only declared within-episode memory; preserve explicit live/model admission.
3. [ ] **MC13.3 — Execute five actual agent episodes.** Add run_memory_episode using existing admitted provider routes: Upload repair, Guest handoff, CSV adaptation, Payload/check order and Diagnosis/handoff. Agent receives task/tool outputs, never expected next action/gold patch. Capture actual selected action, verifier receipt, usage and receiver read-back. Native SWE score uses official evaluator.
4. [ ] **MC13.4 — Implement paired scoring/adverse cases.** Compare none/current/raw/budgeted/linked/full/hybrid with fixed settings/budgets. Count expansions and failed attempts; retain timeout/exhausted cases. Test reset/leakage/replay; emit clustered paired bootstrap and measured/estimated usage separately. Run M01–M30; score actual behavior checks, not success prose.
5. [ ] **MC13.5 — Run GREEN and admitted evaluation.** CHECK(tests/test_benchmark_memory_datasets.py); CHECK(tests/test_benchmark_memory_agents.py); CHECK(tests/test_benchmark_runner.py). Run command below for local suite. External manifests/grants are mandatory for live lanes. Record actual verified/failed/blocked results in MC13.md and benchmark report.

    rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH PYTHONPATH="$PWD/src" /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python scripts/benchmarks/run.py --suite memory --variant full --seeds 11,23,47 --max-total-tokens 16000 --output research/benchmark/memory-full

### MC15 — Execute integrated acceptance and review frozen code

**Owned writes:** tests/test_memory_acceptance.py; plan/report status and MC15.md only. No production edits in review lane.

1. [ ] **MC15.1 — Add end-to-end RED acceptance.** Assemble intent, failed repair, verified sandbox repair, recipe/check evidence and real local receiver. Test fails if expected observation/version/read-back absent. Send implementation defects to owner; refreeze after fixes.
2. [ ] **MC15.2 — Assert actual end state.** Source checkout unchanged; original intent retained; failed attempt still failed; success receipt has actual exit 0; every required check executed; receiver expanded exact versions; replay added no rows; total context within budget.
3. [ ] **MC15.3 — Run final verification.** CHECK(tests/test_memory_acceptance.py), then full pytest/Ruff/installed-artifact checks in §10 on frozen bytes. No new failures. Run required platform/provider/model lanes or name exact external blocker for each.
4. [ ] **MC15.4 — Review R01–R20 against calls.** Record exact implementation symbol/test/runtime evidence per requirement. Review migrations, mutators, reads, permissions, redaction, stale/conflicting data, cache hits, cancellation and actual next-action changes. Cover every lane before verdict.
5. [ ] **MC15.5 — Reconcile and hand off.** Update §11 using separate implementation/integration/benefit states. Record exact changed files, results and blockers in MC15.md. No commit/push without explicit request.

### 9.1 Public request and permission table

Every request has schema_version=1 and rejects unknown fields. ID strings are nonempty; versions positive integers; offsets nonnegative; budgets positive. Empty source allowlist means no sources; omitted means existing policy resolution. Paths must remain in resolved workspace after symlink resolution. Required grants are checked before writes/process/network.

| Operation | Required fields | Optional/default fields | Grants |
|---|---|---|---|
| compact ask/recall/list | existing subject; query for ask/recall | view=compact, limit=8, max_tokens=2048, max_bytes=8192, encoding=cl100k_base, cursor=null, retrieval=lexical | none for lexical; network for hybrid |
| expand | id, version | offset=0, budgets above | none |
| link | source {id,version}, target {id,version}, kind, origin_ref | none | cache_write |
| related | id, version | depth=1, max_nodes=32, budgets above | none |
| consolidate | member_refs [{id,version}] | none | cache_write |
| verify-attempt | attempt_id, behavior_ids, contract, patch | none | cache_write, artifact_write, build plus declared check requirements |
| prepare/resume | task, conditions | behavior_ids=[], query="", budgets above | none |
| intent | action, intent_id | mutation fields from MC07; check only needs ID | cache_write for mutations; none for check |
| recipe | action, recipe_id | record fields from MC08; resolve conditions; outcome recipe_version/patch_hash/receipt_ref | cache_write for record/outcome; none for resolve |
| plan-checks | changed_targets, required_checks, environment | none | none |
| last-success/diagnose | behavior_id, conditions | historical=false | none |
| handoff prepare | action, receiver_namespace, receiver_audience, goal, constraints, unresolved_decisions, selected_refs | memory_bridge=false | cache_write |
| handoff dispatch/status | action, handoff_id | memory_bridge=false for dispatch | dispatch cache_write/build/slow plus network for remote provider; status none |
| receive | handoff_id, page_digest, records | descriptor controls scope/budgets | valid session capability; cache_write only as granted by descriptor |

The handoff row represents one CLI leaf with actions. Dispatch/status resolve receiver identity from saved descriptor; reject replacement identity. Contract uses existing PatchContract fields. Patch is exactly one of {"text":STRING} or {"path":RELATIVE_PATH}. Required-check entries contain id, argv, cwd, expected_exit, timeout_seconds, permissions; declared permissions never grant authority.

Capture routes are fixed: catalog CLI → _run_tool → InvocationExecutor.execute; catalog MCP → make_tool_wrapper → same executor; custom MCP → make_custom_wrapper → same executor; verify-attempt → verification.verify_attempt → authoritative observation once. Generic observer excludes memory operations. Continuity/provenance/graph outputs captured through registered routes preserve their evidence type; a direct library call is not silently represented as an observed CLI/MCP execution.

Normalized families: tests/contracts/snapshots/E2E/mutation keep actual check/fixture/outcome refs; graph/API keep structural refs; coverage keeps measured links; security/dependency/license keep finding+version+resolution refs; continuity/sandbox/provenance keep original receipts/attribution refs. Absent engine-specific evidence stays absent. No inference of executed checks from tags or summary text.

Configuration keys: view, limit, max_tokens, max_bytes, encoding, retrieval, memory_record, embedding_endpoint, embedding_model_digest. Defaults: memory_record=false and retrieval=lexical; budget defaults above. No persistent global bridge grant.

## 10. Final verification and recovery

Before running acceptance, freeze source/test/config/docs subject hashes and check §5 against §8 actual writes and AST/call paths. Resolve discovered omissions in their owning task before restarting affected verification. No more than two identical verification runs on unchanged bytes. Respect repository execution/recenter limits; planning or environment blockers do not justify writing new recovery systems.

Run scoped tests from cards, then full suite and lint with verified project interpreter:

```bash
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH PYTHONPATH="$PWD/src" /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/python -m pytest tests/ -q
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/ruff check src tests scripts
rtk proxy env -u VIRTUAL_ENV -u PYTHONPATH /Users/jamesdsizemore/Developer/rush-cli/.venv/bin/ruff format --check src tests scripts
```

Use existing installed-artifact probes for wheel/sdist CLI/MCP behavior; no source-tree import substitution. Explicitly test SDK/ACP subprocess cleanup on supported platforms and a real configured embedding engine. Run core public benchmark adapters and admitted provider episodes under the report protocol. Absence of credentials, runtime, compatible interpreter or compute blocks only the named evidence lane; it cannot be reported as a pass.

Migration failure must leave original database usable. Permission denial and query-only calls must leave directory trees unchanged. Interrupted handoff must allow replay without duplicate authority or cursor advancement. Unexpected drift invalidates snapshots/cursors and produces restart-required, not guessed content. Engine unavailability remains skipped; required behavior cannot be marked verified from it.

Baseline failures are compared by exact test and cause at frozen revisions. New failures must be fixed. Historical unrelated failures remain visible and prevent a whole-repository-green claim; do not modify them under this feature plan without scope amendment.

## 11. Status and reconciliation ledger

Planning state on 2026-09-08: contracts drafted from current source and primary benchmark documentation. No MC task implemented or benchmark executed by creating this plan.

| Work group | Tasks | Current status | Evidence needed before closure |
|---|---|---|---|
| Baseline and memory foundation | MC00–04 | Planned | Version/migration, scoped budget/expansion, relations/consolidation, measured work/cost tests |
| Vibecoder execution and learning | MC05–10 | Planned | Real observation/verification route, repair/intent/recipe/check/diagnosis fixtures |
| Connected and optional retrieval paths | MC11–12 | Planned | Restricted receiver read-back, lifecycle tests, real optional embedding engine |
| Evaluation and public product contract | MC13–14 | Planned | Native benchmark adapters, actual agent episodes, installed CLI/MCP/config/docs parity |
| Final acceptance | MC15 | Implementation: done (`tests/test_memory_acceptance.py`, new). Integration: verified (real end-to-end scenario assembling MC01–MC14 through one shared store: confirmed intent, failed repair, verified sandbox repair, recipe/check evidence, real restricted MCP handoff receiver; R01–R20 reviewed against real symbols/tests). Benefit: confirmed (cross-packet evidence — recipe outcome bound to the real verify-attempt receipt, intent bound to the real revision, ranked check bound to the real regression finding — not isolated per-packet unit coverage). | Delivered: `tests/test_memory_acceptance.py`, `docs/phase-plans/MC15.md`. Full suite 1827 passed/5 skipped (baseline 1826/5, zero new failures); `ruff check`/`ruff format --check` show only the same pre-existing baseline findings as before this packet, none in this packet's own files. No MC01–MC14 defect found. |

Implementation readiness requires stable source/input identities and an available Python 3.12 environment. Evaluation execution additionally requires explicit route/data/model grants and resources. These are concrete execution prerequisites, not approval gates inserted before preparing reviewable work.

Risks retained in scope: public datasets may poorly predict coding benefit; mutable provider/model versions affect reproducibility; environment identity may omit a causal factor; source graphs miss dynamic consumers; summaries omit exceptions unless tested; read-only guarantees can be violated by lazy DB/cache initialization; token savings can disappear after expansion; receiver access can accidentally broaden sender authority. Named tests and benchmark lanes above address each risk. Unresolved evidence is reported, never simulated.
