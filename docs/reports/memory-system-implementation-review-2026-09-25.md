# Rush memory implementation review

Date: 2026-09-25. Audience: developer preparing the next memory development plan.

## Verdict

**Rush has a substantial shared memory substrate, but does not yet deliver dependable, continuously active memory across coding agents.** A coding agent can explicitly read and write the same project's memory through CLI or full MCP. That is different from having each supported host activate memory, inject relevant context, continually record useful learning, and demonstrably continue another agent's work.

The most urgent defects are inconsistent read defenses: archived and expired content can be expanded, edited content can retain `STATED` authority in compact recall, cross-owner evidence can promote records, and pagination can hide remaining results. Fix these before expanding automatic consumption. Registration/readiness indicators currently overstate what was observed. Everyday client setup and explicit handoff transports are separate routes, with unequal client coverage.

This document is **review evidence and input to a development plan**, not an approved implementation plan. Findings describe the frozen implementation. Proposed work and acceptance criteria preserve the requested outcome; they do not authorize implementation or remove existing requirements.

## 1. Scope, baseline, and evidence

Reviewed commit: `ddc064117e971b48e29100004052e876e456faf2` in `/Users/jamesdsizemore/Developer/rush-cli`. Tracked source, tests, scripts, governance, package manifest, and lockfile matched that commit during review. Existing changes to `AGENTS.md`, untracked Phase 70/71 documents/reviews, and `src/rush/tools/.rush/` were present before review. They are not implementation delivered by this review.

Scope: durable agent memory, retrieval and mutation, preferences/learning, agent activation and continuation, user access, memory consumers/producers, and the MCP boundaries needed by those routes. Runtime memory profiling (`mem_profile`), unrelated quality-engine correctness, general dashboard design, and unrelated MCP capabilities were excluded. No production code, client configuration, real memory contents, release, or Git commit was changed.

Three non-overlapping, read-only `gpt-6-sol` subagents used high reasoning for difficult review work: memory core; client activation/continuation; app integration. Coordinator reconciled requirements and independently reviewed benchmark/evaluation semantics. Graft provided source/caller discovery; context-mode bounded larger analysis. Local source and supplied corpus controlled the review; no external product capability was assumed from vendor names.

Evidence labels:

| Label | Meaning |
|---|---|
| Reproduced | Current Python 3.12 code executed in isolated temporary projects/homes and exhibited the finding. |
| Source-confirmed | Concrete current call path or exhaustive indexed caller inspection establishes the behavior; interactive host behavior was not executed. |
| Product gap | Required end-to-end behavior is absent/incomplete in reviewed routes; existing components are identified. |
| Unverified | Actual host, platform, model, or performance evidence is missing. This is not proof of failure or success. |

Prior plans/evidence were inspected as contracts and history, not reused as current PASS verdicts. Relevant ledgers: [Phase 61 §5/§8.1](../phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md), [Phase 62 §5](../phase-plans/phase-62-memory-integration-layer-plan.md), and [Phase 63 §5/§8.1](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md). The local, untracked [Phase 70 draft](../phase-plans/phase-70-agent-adoption-and-usability-plan.md) contains overlapping future proposals; it is not shipped behavior or independent approval of scope.

## 2. What is developed today

### 2.1 Storage and memory types

Primary durable store is per-project `.rush/memory.db`, using SQLite WAL, typed artifacts, revisions/change history, source provenance, owner metadata, trust tiers, redaction, lexical indexing, and maintenance. Families are `handoff`, `experience`, `memory`, and `skill`. Subjects are `active_context`, `episodic`, `preference`, `failure`, `architectural_decision`, `domain_knowledge`, and `skill_pattern`. See [store.py](../../src/rush/memory/store.py), lines 24–118 and 610 onward.

| Capability | Current implementation and practical limit |
|---|---|
| Active development context | Checkpoints, continuity receipts, goal/open-work handoffs, source hashes, context packing/cache and explicit prepare/resume/receive operations exist. They require calls; they are not automatically loaded by every connected agent. |
| Project knowledge and episodic memory | Typed writes and source-scoped recall work through `MemoryTool`. Session/flight/checkpoint material can be persisted. Generic session-turn recording is not wired into ordinary production agent interaction. |
| User preferences | A `preference` subject exists. Legacy `PreferenceStore` uses project-local `.rush/preferences.json`, synchronized into project memory. This does not establish a global user preference authority or inheritance/conflict policy across projects. |
| Failures, repairs, patterns and decisions | Failure/mistake records, architectural decisions, skill candidates, confirmed intent, condition-aware repair history, recipes, check planning and last-success diagnosis are implemented components. Their presence does not establish that an ordinary agent discovers or uses them. |
| Search and navigation | FTS5/metadata-aware lexical retrieval, compact recall, exact-version expansion, relation traversal and optional embedding/hybrid paths exist. Pagination, visibility and defense defects remain. No held-out retrieval-quality result was established here. |
| Governance and lifecycle | Entry trust, promotion, signatures, source allowlists, revision checks, expiry, archival/deletion, consolidation and migration exist. Newer routes apply those protections inconsistently. |

Important topology distinction: `agent_memory.json` is connection/consent/session bookkeeping containing one last observation per agent/session. It is **not** the typed knowledge store. Native Claude/Codex/vendor conversation memory is also not automatically unified with Rush. Sharing Rush means resolving the same intended project store and authorized sources, not merely using the same model or installation.

### 2.2 Public surfaces and app integration

| Surface | Developed path | What remains incomplete |
|---|---|---|
| CLI | `rush memory` exposes ask/recall/list/write/promote/maintain plus request-shaped advanced operations. Shared `MemoryTool` is used; operation-specific inputs and permissions apply. [cli.py](../../src/rush/cli.py), 2534–2965. | No complete guided activation → recall → work → write → switch-agent journey was established. Bare registration is insufficient. |
| Full MCP | `rush_memory` is registered through shared tools. [mcp.py](../../src/rush/mcp.py), 41–78, 569–704; [tool_registry.py](../../src/rush/mcp_support/tool_registry.py), 33–60. | Tool availability depends on selected profile/client configuration. Availability does not cause the host to call it or grant writes. |
| Restricted handoff MCP | Receive/expand/related/resume bridge exposes bounded receiving access; exact read-back mechanisms exist. [tool_registry.py](../../src/rush/mcp_support/tool_registry.py), 198–259; [transport.py](../../src/rush/memory/transport.py), 166–254. | Explicit SDK/ACP handoff route differs from normal client registration and CLI session resume. Do not advertise them as equivalent. |
| Dashboard | Backend can query/filter/browse/expand/relate memory and dispatch shared mutations. [server.py](../../src/rush/dashboard/server.py), 2348–2955, 3447–3628. | Frontend presents serialized data and generic mutation forms; usable search/filter/selected expansion is missing. |
| TUI | Real list/search/expand/edit/delete/promote calls exist. [tui.py](../../src/rush/tui.py), 1307–1604. | Search is fixed to `domain_knowledge`; other subjects lack a selection route. |

### 2.3 Producers and consumers

| Flow | Actual integration | Boundary |
|---|---|---|
| Continuity/context | `pack_context` consults defended memory cache and writes cache fills when permitted. [context.py](../../src/rush/continuity/context.py), 125–163. | Requested context-pack call; not an automatic host session-start injection. |
| Review | Recalls failure/architectural-decision evidence and adds citations. [review.py](../../src/rush/tools/review.py), 62–66, 99–128, 243. | Source allowlists are migration-specific; normal user-written memory is not generally consumed. |
| Scan → agent handoff | Writes typed `active_context` and creates bounded receiver access. [project_run.py](../../src/rush/workflows/project_run.py), 2213–2240. | This specific integration is real. It does not prove every scan/fix uses preferences, intent, recipes or repair history. |
| Invocation observations | Opt-in capture exists, requires cache-write permission, and can record actual execution evidence. [config.py](../../src/rush/config.py), 355–374; [executor.py](../../src/rush/invocation/executor.py), 470–483. | Defaults off; capture errors are swallowed. No reliable user-facing distinction among disabled, denied and failed capture. |
| Learning utilities | Mistake mining is callable from CLI/MCP/continuity; failures feed continuity; advanced intent/recipe/check/diagnosis operations are callable through `MemoryTool`. | Ordinary scan/fix/review/suite flows lack general producer/consumer wiring for these advanced operations. |

Memory is categorized as workflow and excluded from scan-engine candidates ([catalog.py](../../src/rush/catalog.py), 127–134; [project_run.py](../../src/rush/workflows/project_run.py), 391–406). That categorization is not itself a defect: the missing behavior is appropriate memory consumption/capture around scan and repair actions, not treating memory as a linter.

## 3. Agent support and “active” status

These are **implemented adapter routes**, not live-client certifications. Adapter inventory: [agents.py](../../src/rush/integrations/agents.py), 128–155; continuation routes: [providers.py](../../src/rush/continuity/providers.py), 32–76, 254–270; transport tiers: [transport.py](../../src/rush/memory/transport.py), 36 onward.

| Client | MCP registration | Continuation route | Review conclusion |
|---|---|---|---|
| Claude Desktop | JSON configuration; restart | No direct provider resume | Registration supported; continuous use unverified. |
| Claude Code | Native `claude mcp add` or JSON | `claude_code` CLI resume; optional Claude SDK bridge | Fresh-install detection and readiness defects; no actual host continuation proof. |
| Codex CLI | TOML configuration | `codex_cli` resume; ACP bridge requires installed ACP and supplied adapter argv | Wrong arguments can pass registration probe; desktop app behavior is not certified by CLI support. |
| Cursor, Windsurf, Zed | Configuration edits; restart | No direct provider resume | MCP access can exist; automatic memory lifecycle is not established. |
| Antigravity / `agy` | No registration adapter | `antigravity_cli` bounded resume; optional ACP bridge | Partial route only. `agy` is interpreted here from the literal executable in source. |
| Z.AI / `zai` | No registration adapter | Explicitly deferred | Requested cross-agent use is not implemented for this identity. |

There is currently **no verified per-client indicator covering the complete meaning of “memory active.”** Existing flags report configuration/acknowledgment/bookkeeping. Proposed status contract must distinguish:

1. **Configured/connected:** exact command/arguments valid; actual host handshake observed, with client/version/project identity.
2. **Accessible:** authorized read succeeds; write capability is separately permitted/denied and verified without silently broadening grants.
3. **Context delivered:** actual record IDs/revisions, freshness, source scope and token cost supplied to the current agent/session.
4. **Used/written:** observed tool receipts identify consumed evidence and committed writes; absence or capture failure remains visible.
5. **Continuation verified:** a different agent reads exact authorized handoff revisions and performs a task-relevant action using that evidence.

A banner cannot prove cognition. “Used” must mean an observable action/evidence relationship, not a claim inferred from prompt delivery. Disabled, unsupported, stale, denied, failed and never-tested states must remain distinct. Display this state through agent-facing responses and human CLI/TUI/dashboard views; respect each host's actual extension capabilities rather than promising a universal native badge.

## 4. Findings

P1 blocks dependable use or violates required safety/continuation behavior. P2 is a material reliability, usability, integration or evidence gap. No P0 catastrophe was established. Related findings share remediation where appropriate; do not create one competing validator per route.

### 4.1 Storage, visibility and trust

| ID / priority / evidence | Finding and impact | Correction and acceptance |
|---|---|---|
| F01 / P1 / reproduced | **Archived artifacts remain readable through newer routes.** `search_candidates` omits archive filtering; expansion does not check it. Archive → legacy search empty, compact recall includes ID, expand returns `OK`. [store.py](../../src/rush/memory/store.py), 799–852; [retrieval.py](../../src/rush/memory/retrieval.py), 571 onward. | Share active visibility checks before ranking and every expansion. Archived item absent from ordinary recall; direct expansion denied. A deliberately historical route must be explicit and labeled. |
| F02 / P1 / reproduced | **Expired artifacts remain expandable.** After expiry sweep, compact recall excludes the item but exact-version expansion still returns `OK`. [retrieval.py](../../src/rush/memory/retrieval.py), 571 onward. | Recheck expiry for every page/expansion. Expiry occurring between pages revokes further ordinary access. |
| F03 / P1 / reproduced | **Content mutation retains authority; compact recall bypasses integrity defense.** Editing promoted content preserves `STATED` and old signature. Defended recall raises `SignatureMismatchError`; compact recall returns altered content as `STATED`. [store.py](../../src/rush/memory/store.py), 2069–2104; [retrieval.py](../../src/rush/memory/retrieval.py), 275–295, 335–498. | Atomically demote/revalidate content authority and apply shared signature, trust and source-freshness defenses to compact/hybrid/expand. Tampered or changed records must never appear as current authoritative evidence. |
| F04 / P1 / reproduced | **Maintenance corroborates across owners.** Candidate selection honors requested owner, corroboration query does not. Alice and Bob each supply one candidate from different sources; Alice sweep promotes Alice's row to `STATED`. [maintenance.py](../../src/rush/memory/maintenance.py), 42 onward, 195 onward. | Corroboration must remain within authorized owner/scope and independent-evidence rules. One candidate per separate owner must not promote either. Source allowlists and owner authorization require an explicit relationship; labels alone are not isolation. |
| F05 / P1 / reproduced | **Result limit truncates pagination permanently.** Three matches with `limit=2` return two items, `complete=True`, `next_cursor=None`; remaining result is unreachable by paging. [retrieval.py](../../src/rush/memory/retrieval.py), 464–498. | Cursor resumes from first unconsumed candidate whenever count or budget stops a page. Collect all results exactly once under small count/token/byte limits; honest completion state. |
| F06 / P2 / source-confirmed | **Related-memory route lacks equivalent defenses.** Traversal checks source/version but omits archive, expiry, integrity and source freshness; relation insertion lacks owner/namespace policy beyond endpoint existence/cycle checks. [relations.py](../../src/rush/memory/relations.py), 88 onward, 149 onward. | Apply authorized visibility to both endpoints and every hop. Changed/revoked/expired neighbors must not reintroduce excluded memory. Preserve graph cycle/version guarantees. |
| F07 / P2 / source-confirmed | **Consolidated summaries can outlive their evidence.** `summary_is_current` checks member versions but has only a test caller; actionable retrieval does not enforce it. [consolidation.py](../../src/rush/memory/consolidation.py), 140 onward. | Check members on retrieval or invalidate derived summaries when members change. Changed, archived and expired members must invalidate or clearly qualify the summary; retain contradictions and originals. |
| F08 / P2 / reproduced | **Fresh-process maintenance import fails.** Import chain reaches tools/memory before `MaintenanceTask` is defined. `from rush.memory.maintenance import run_maintenance_cycle` raises `ImportError: cannot import name 'MaintenanceTask' from partially initialized module`. [maintenance.py](../../src/rush/memory/maintenance.py), 28 onward. | Break import cycle using existing module boundaries. Fresh-interpreter import and a real permitted maintenance operation must work independently of test import order. |

### 4.2 Activation, identity and continuation

| ID / priority / evidence | Finding and impact | Correction and acceptance |
|---|---|---|
| F09 / P1 / reproduced + source-confirmed | **“Registered/active/connected” can mean configuration or caller acknowledgment only.** Codex config with `args=["not","mcp","serve"]` reports registered. Probe compares command path; install maps result to active, and `acknowledge=True` flips connected. [agents.py](../../src/rush/integrations/agents.py), 453–506, 895 onward; [install.py](../../src/rush/tools/install.py), 446–528; [agent_connection.py](../../src/rush/tools/agent_connection.py), 143 onward. | Implement staged status in §3. Wrong args must fail config validation. Only actual host/tool evidence may establish connection/access/use. Keep manual consent distinct from observation. |
| F10 / P1 / reproduced | **Fresh Claude Code can be skipped.** Discovery requires `~/.claude.json`; installed executable alone returns `not_detected`, then installer skips registration. [agents.py](../../src/rush/integrations/agents.py), 92 onward, 453 onward; [install.py](../../src/rush/tools/install.py), 458 onward. | Detect supported installed CLI independently of preexisting config, then perform authorized registration and actual Rush call. Test empty temporary home with installed/fake-discovery CLI and later real-host acceptance. |
| F11 / P1 / product gap | **Activation does not establish an ongoing memory lifecycle.** Connection initializes per-agent CAS bookkeeping, without typed recall/injection. `record_tool_observation` has no production caller. Legacy `SessionMemoryManager.record_turn` and `format_for_mcp` are test-only callers, so their existence does not supply continuous session capture/injection. [agents.py](../../src/rush/integrations/agents.py), 759–892; [agent_connection.py](../../src/rush/tools/agent_connection.py), 143 onward; [session_memory.py](../../src/rush/session_memory.py), 66–145. | Supply discoverable host instructions/adapters for session start, task-sensitive recall, evidence expansion, outcome capture, compaction, end/handoff and subsequent resume. Verify a second host retrieves earlier learning without the user restating it. |
| F12 / P2 / reproduced | **Reconnect erases bookkeeping observation.** Initialization replaces same-session entry. Probe changed connected=true plus last review observation into connected=false plus null observation. [agents.py](../../src/rush/integrations/agents.py), 787 onward; [agent_connection.py](../../src/rush/tools/agent_connection.py), 143 onward. | Make reconnect idempotent and preserve confirmed observations unless explicit reset requested. This finding concerns bookkeeping, not deletion of typed artifacts. |
| F13 / P1 / source-confirmed | **CLI provider resume is weaker than the required memory handoff.** Prompt includes goal/open work/freshness, omits the complete constraints/decisions/references contract; provider execution discards output and accepts exit 0. [providers.py](../../src/rush/continuity/providers.py), 20 onward, 221 onward, 312 onward. | Preserve complete bounded handoff semantics and distinguish process completion from receiver read-back/action. Exercise exact authorized revisions, stale dependencies, replay, interruption and actual receiving-agent use. Keep existing restricted transport rather than duplicating it. |
| F14 / P1 / product gap | **Requested client coverage is incomplete.** No registration adapter for `agy` or `zai`; only bounded `agy` resume and explicit Z.AI deferral. See §3. | Define supported client identities/versions and implement suitable capability-verified adapters. Unsupported clients must report exact missing capability; generic ACP availability cannot stand in for a working client adapter. |
| F15 / P2 / product gap | **User memory is project-local, with no established global preference policy.** Legacy preferences persist under project `.rush/`; a subject named preference does not define cross-project inheritance, precedence or consent. [preference_store.py](../../src/rush/memory/preference_store.py), 17 onward; [migration.py](../../src/rush/memory/migration.py), 205–228. | Plan project-shared preferences first-class and explicitly decide global user overlay. Separate user-confirmed preferences from inferred patterns; support inspect/correct/supersede/reject. Verify cross-agent persistence and project overrides without cross-project leakage. |

### 4.3 App integration and human access

| ID / priority / evidence | Finding and impact | Correction and acceptance |
|---|---|---|
| F16 / P1 / source-confirmed | **Review excludes ordinary user-written memories.** Recall is limited to failure/architectural-decision migration source allowlists. A user writing relevant project knowledge does not establish a route into review citations. [review.py](../../src/rush/tools/review.py), 62–66, 99–128, 243. | Use explicit authorized source/scope policy for relevant user/agent records. A known relevant record affects review evidence with ID/revision citation; unrelated/stale/rejected records do not. Do not replace allowlists with unrestricted recall. |
| F17 / P2 / source-confirmed + product gap | **Learning capabilities are disconnected and capture health is hidden.** Intent, recipes, repair diagnosis and check planning are callable but have no general scan/fix/review/suite consumers. Opt-in invocation capture defaults off and suppresses errors. [memory.py](../../src/rush/tools/memory.py), 1035–1087, 1401–1737, 1804–1853; [executor.py](../../src/rush/invocation/executor.py), 470–483. | Define producer, trigger, consumer and evidence for each memory type. Expose disabled/denied/failed capture. Demonstrate a failed repair changes next choice, a verified success updates appropriate evidence, and required checks remain mandatory. |
| F18 / P1 / source-confirmed | **Dashboard user search is not exposed.** Backend supports memory query/filter/expand/related, but frontend renders `JSON.stringify(data)` and generic mutation forms; section fetch has no query controls. [application.js](../../src/rush/dashboard/application.js), 1186–1220, 1309–1350; [server.py](../../src/rush/dashboard/server.py), 3447–3628. | Add usable query, subject/source/trust/freshness filters, record selection, exact-version expansion and visible mutation feedback. Test real browser behavior using live memory, including empty/denied/stale/error/paginated states. |
| F19 / P1 / source-confirmed | **TUI cannot browse every memory subject.** `memory_subject='domain_knowledge'` is fixed, refresh uses it, key handling offers no subject switch. [tui.py](../../src/rush/tui.py), 446–452, 1319–1367, 1607–1743. | Make every supported subject discoverable/searchable; retain expand/mutation capabilities and keyboard access. Verify actual terminal interaction, not only helper calls. |

### 4.4 Evaluation and documentation

| ID / priority / evidence | Finding and impact | Correction and acceptance |
|---|---|---|
| F20 / P1 / source-confirmed | **“Real agent episodes” do not exercise real model decisions.** Named episodes select hard-coded patches/actions from Python callbacks. Memory suite always appends a missing-live-provider blocker and invokes scripted builders; its live decision path is not wired merely by supplying credentials. [memory.py](../../scripts/benchmarks/memory.py), 539–622, 681–736, 1034–1052; [run.py](../../scripts/benchmarks/run.py), 389–414. | Retain these as component scenarios. Wire admitted real provider decisions into the existing runner, then execute cross-agent continuation with observed choices. Do not mark agent benefit confirmed from scripted fixtures. |
| F21 / P2 / source-confirmed | **Benchmark comparison measures completion, not answer/task quality.** `none` yields empty text, `raw` concatenates input; `_case_completion_score` gives 1.0 to any `scored` result. Episode fallback accepts all ok/warn calls without task-specific outcome proof. [run.py](../../scripts/benchmarks/run.py), 176–254, 362–377; [memory.py](../../scripts/benchmarks/memory.py), 508–536. | Separate harness completion, retrieval relevance, task correctness and continuation benefit. Score held-out answers/behavior with proper evaluators and matched agent/budget settings; empty or incorrect answers cannot establish benefit. |
| F22 / P2 / reproduced | **Dataset token ceiling is not enforced after decision; recall costs are incomplete.** `run_longmemeval_case` checks ingestion budget, then adds hypothesis tokens and returns scored without checking again; callback tool calls are not centrally counted. One-token budget produced 202 tokens, outcome scored, score 1.0. [memory_datasets.py](../../scripts/benchmarks/memory_datasets.py), 190–259. Episode loop separately counts serialized tool results but not full provider input/output. | Count all retrieval/expansion/handoff and model usage, enforce after each step, preserve exhausted cases in denominator. The same one-token probe must return budget_exhausted; reports distinguish tokenizer counts from provider billing/usage. |
| F23 / P2 / source-confirmed | **Docs mix architecture proposals and completion claims with current implementation.** Architecture text describes mandatory epistemic classes, scopes/watchers and capsules not equivalent to actual typed schema; Phase 63 says not started/planned while final ledger says benefit confirmed. [architecture document](../architecture/rush-epistemic-memory-and-agent-substrate.md), 30–108; [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md), 7, 500–514; [MC13](../phase-plans/MC13.md). | Reconcile current API/storage/host behavior and separate implemented, integrated, evaluated and proposed states. Preserve historical receipts with revision labels. A plan cannot use these conflicting statements as current acceptance. |
| F24 / P2 / source-confirmed contract gap | **Expansion representation differs from the specified receiving contract.** Phase 63 §6.2 requires UTF-8 content slices, valid character boundaries, hash, version and continuation. Implementation returns base64 slices of arbitrary bytes without the required hash. Base64 itself is valid encoding; the issue is contract mismatch and missing verification metadata. [retrieval.py](../../src/rush/memory/retrieval.py), 633–698; [Phase 63](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md), 120–130. | Implement the promised expansion contract with version/digest and bounded Unicode-safe continuation; preserve existing callers through explicit compatibility. Test multibyte content, reconstruction, tampering and receiver verification. Do not silently rewrite the requirement to match current output. |

## 5. Requirement reconciliation

The user's intended outcome controls scope. Phase 63 R01–R20 provides a useful existing ledger, but does not narrow agent-side activation, preferences, human access or integration requested here.

| User requirement | Current assessment | Planning references |
|---|---|---|
| Active, accessible, usable, writable by coding agent | Explicit CLI/full-MCP calls exist; continuous host lifecycle and trustworthy status missing. Writes remain permission-gated. | F09–F11, F14; §3 |
| Switch coding agent and continue same development | Shared project store and bounded handoff mechanics exist; actual cross-host context use not demonstrated, resume route weaker, client support incomplete. | F13–F14, F20 |
| Current context and continuous development memory | Checkpoint/cache/receipt/observation components exist; task-start/compaction/end triggers and full learned-outcome use are incomplete. | F11, F17 |
| User preferences, patterns/antipatterns, project knowledge, agent learning | Typed subjects and advanced operations exist; user-confirmed authority, global/project policy and producer/consumer wiring need completion. | F03–F04, F07, F15–F17 |
| Searchable and manageable by user; integrated with rest of app | Shared backends exist; dashboard/TUI access and review/general workflow consumption are incomplete. | F16–F19 |

Phase 63 coverage against current implementation and reviewed file map:

| Requirement | Developed surface | Current evidence/verdict |
|---|---|---|
| R01 scoped bounded recall/expansion | store/retrieval/MemoryTool | Partial; F01–F05. |
| R02 lexical/metadata/paraphrase retrieval | FTS + optional hybrid | Implemented routes; quality/paraphrase benefit unverified. |
| R03 versioned evidence links | relations/store | Partial; F06. |
| R04 delta handoff/read-back/replay | handoff/transport/restricted MCP | Component mechanisms tested; ordinary provider continuation incomplete, F13/F20. |
| R05 defended efficient search/cache | defended lookup + context cache | Defense not shared by newer recall routes, F03. No whole-workload performance claim. |
| R06 consolidation preserving evidence | consolidation | Partial; missing retrieval invalidation, F07. |
| R07 complete token/byte ceilings | retrieval and benchmark accounting | Local bounds exist; total evaluation accounting and expansion contract incomplete, F22/F24. |
| R08 evaluated optional hybrid retrieval | embeddings/retrieval | Code/test coverage exists; no real endpoint or held-out evaluation in this review. |
| R09 confirmed intent and checks | intent + verification operations | Components exist; general agent/workflow use incomplete, F17. |
| R10 failed repairs affect next choice | experience/failure/verification | Real sandbox mechanics tested; autonomous next-choice evidence missing, F17/F20. |
| R11 current recipes and references | recipes | Callable; broad production consumer integration incomplete, F17. |
| R12 evidence-ranked mandatory checks | verification/plan_checks | Callable; no general workflow selection proof, F17. Required gates must remain. |
| R13 last-success comparison | experience/store diagnosis | Callable; lifecycle integration/actual causal benefit unverified, F17. |
| R14 actual test/security execution evidence | opt-in invocation observation | Implemented with defaults/permission/failure-visibility limits, F17. |
| R15 graph/API/coverage context | associated source/recipe/check mechanisms | Supporting components reviewed through memory paths; full dynamic-consumer/coverage matrix not executed. Retain acceptance obligation. |
| R16 security/dependency/license evidence refreshed | versioned observation/check mechanisms | Retain engine-linked freshness/resolution acceptance; no end-to-end multi-engine proof from this review. |
| R17 sandbox/provenance/continuity/token route | verify_attempt/context/handoff | Component acceptance passes; full real-host participation absent, F13/F20/F22. |
| R18 trust/scope/redaction/expiry through all routes | core store/defenses | Not met across newer retrieval paths, F01–F07. |
| R19 agent action changes and task quality measured | benchmark callbacks | Not established; F20–F22. |
| R20 CLI/MCP/config/docs/installed parity | shared MemoryTool + manifests | Shared route exists; client activation, docs and live installed host matrix incomplete, F09–F14/F23. |

Phase 61's seven subjects and shared transport remain present. Phase 62's cache, review, maintenance, receipt, attribution, API-staleness and expiry extensions are present as components; F03/F04/F08/F13/F16/F17 explain why component presence cannot close the integrated contract. Phase 63 production/benchmark paths were reconciled by responsibility across the three review lanes; this is not an exhaustive AST audit of unrelated app code.

## 6. Inputs for the development plan

### 6.1 Dependency order and bounded work packages

These are proposed groupings, not assigned or approved tasks. Preserve every finding and required outcome when producing the actual plan.

| Order / package | Ownership and existing surfaces | Depends on | Required exit evidence |
|---|---|---|---|
| 1. Safe canonical memory reads/writes | `memory/store.py`, retrieval, relations, consolidation, maintenance; F01–F08/F24 | Explicit active/historical, owner/source and authority rules | Shared defensive route; reproduced defects fail before fix and pass afterward; cross-owner/stale/tampered/revoked/expired/paged and multibyte expansion cases covered. |
| 2. Shared agent lifecycle and honest status | integrations/agents, agent_connection/install, continuity, transport, host guidance; F09–F15 | Safe reads; exact supported client and scope contracts | Host-originated activation/read/write receipts; idempotent reconnect; correct project identity; real two-agent continuation; unsupported states named. |
| 3. Useful learning and app consumption | invocation observations, review, memory operations, scan/fix/suite integration; F16–F17 | Packages 1–2; explicit consent/provenance rules | Each memory type has actual producer/consumer; bounded relevant recall; observable failed-attempt avoidance; verified outcomes; capture health; required checks retained. |
| 4. Human search, control and visibility | dashboard/TUI/CLI memory presentation; F18–F19 and §3 | Canonical read/status contracts; can develop alongside package 3 | Browse/search all subjects, inspect exact versions/provenance/relationships, correct/reject/supersede/archive, recover from permission/error states in actual browser/terminal. |
| 5. Real evaluation and truthful docs | existing benchmark runner/tests/docs; F20–F23 | Real lifecycle/integration; evaluation instrumentation should be defined before implementation | Matched real-agent trials, exact receiver read-back plus task result, full cost accounting, current client/platform matrix, reconciled docs and frozen-source review. |

### 6.2 Design choices that must remain explicit

| Decision | Alternatives and tradeoff | Review recommendation |
|---|---|---|
| Host integration | MCP offers shared tools/access control but does not trigger host behavior. Native instructions/lifecycle adapters improve discovery/injection but differ by client. Dedicated files are broadly readable but need explicit freshness/version and write/import handling. | Reuse MCP as shared service and add small capability-specific host guidance/adapters. Keep file transfer an explicit supported fallback, not a claim of equivalent dynamic operation. Do not introduce Git hooks. |
| Preference scope | Project-only is simple and isolated; global user overlay preserves preferences across repositories but requires precedence, ownership and consent. | The requested cross-agent project continuation must work regardless. Define whether global cross-project preferences are also required before choosing overlay storage; do not silently infer this from `preference` subject. |
| Capture policy | Explicit event writes are auditable but easy to omit; supported host/invocation capture improves continuity but can collect noise/private content and consume tokens. | Event-driven bounded capture of decisions, verified outcomes, failures, changed constraints and handoff state. Preserve permissions and show capture health; do not store every tool result by default. |
| Retrieval | Existing lexical search is inexpensive and deterministic; optional hybrid can improve paraphrases but adds engine availability/cost/freshness dependencies. | Repair canonical defenses/pagination first. Evaluate hybrid on actual lexical misses; do not add a mandatory external model to make baseline memory work. |
| Evidence of use | Configuration is cheap to inspect; prompt delivery is observable; actual usage requires tool/action/verification relationships. | Separate these states. Report IDs/revisions/costs without exposing secret contents or capabilities. No “learning succeeded” inferred solely from row count. |

### 6.3 Enhancements beyond defect repair

**Clarified target: an innovative, creative, dynamic and powerful development-memory system, including meaningful use of AST.** The original five enhancement rows were insufficient: they described supporting infrastructure without developing the learning and reasoning capabilities it should enable. This expansion preserves those requirements and develops a substantive capability portfolio.

The target is memory that helps the current coding agent maintain an evolving account of **what the user wants, what the code currently does, what has been tried, what evidence is missing, and which next action would resolve that uncertainty**. Another agent inherits that account with its authority, conditions and unresolved questions intact. Rush supplies grounded evidence and controlled execution surfaces; the coding agent still reasons and chooses actions. This does not require replacing the user's coding agent with a separate orchestrator.

Innovation here means a useful new behavior in Rush, not an unverified claim of market novelty. A capability earns its place when it changes an agent decision, preserves an important user requirement, avoids a known failure under matching conditions, or produces a better verified outcome. More stored rows, a vector index, a graph visualization, or a new tool name is not enough.

The local corpus already contains relevant ideas: [practical memory assessment](../../.scratch/memory-capability-assessment/recommendations.md), [vibecoder integrations](../../.scratch/memory-capability-assessment/vibecoder-integrations.md), [earlier synthesis](cross-llm-memory-system-synthesis-2026-09-06.md), and [innovation report](memory-innovation-enhancement-report.md). Those are proposal/history sources, not evidence that their named modules or benefits exist. The portfolio below distinguishes current code from new behavior. It does not inherit unsupported claims such as guaranteed zero repeated mistakes, automatic causal truth from Git reverts, or fixed percentage token savings.

#### Functional alternatives

| Approach | Primary function and tradeoff | Assessment |
|---|---|---|
| Searchable notes plus session summaries | Good explicit recall and inexpensive implementation; agents must independently discover relevant history and reconstruct what to do. | Necessary baseline, insufficient for the stated target. |
| Code-linked evidence and event-triggered context | Relates intent, symbols, attempts and verification; code changes and task events retrieve/revalidate the relevant evidence. Requires trustworthy identity and producer/consumer integration. | Recommended foundation for dynamic memory. Reuse typed store, relations, recipes, observations and verification. |
| Outcome-adaptive learning on that foundation | Learns conditional patterns, adapts successful procedures, selects discriminating experiments and improves context allocation from measured outcomes. Adds attribution and evaluation difficulty. | Recommended capability direction, with individually falsifiable experiments; not an already demonstrated benefit. |
| Separate general-purpose autonomous memory service | Broad independent scheduling/reasoning, but duplicates ownership, permission, transport and state already present in Rush. | No need established. First implement the concrete loops through the existing agent and shared Rush runtime. |

### 6.4 AST: current implementation, gaps, and role in memory

**Current implementation is local Python syntax inspection plus file/source hashing, not a fully connected AST-backed memory system.** AST can identify code structure and candidate relationships. It cannot by itself prove runtime behavior, causation, user intent, or completeness of dynamic call coverage.

| Current surface | Verified behavior | Limit relevant to memory |
|---|---|---|
| `memory/merkle_invalidator.py`, 12 onward | SHA-256 of supplied text or full file bytes. | Despite AST/Merkle naming, it does not parse symbol ASTs. An unrelated edit can invalidate file-bound memory; the hash says nothing about behavior. |
| `memory/trust.py::resolve_symbol_ref`, 108–127 | Python `ast.parse`, top-level function/class lookup. | No qualified nested-member resolution or equivalent non-Python grounding in this path; containment defect A02 below. |
| `memory/recipes.py`, 38–85, 214–302 | Python AST resolves dotted function/class inside one file; exact source segment is hashed. Recipe resolution rechecks helper/symbol/dependency/config references. | Useful existing applicability primitive. Formatting changes alter exact hash; it does not discover all dependencies, re-exports or inheritance relationships. |
| `tools/api_diff.py`, 13–86; defended retrieval, 109–182 | Parses public Python definition parameter names, compares against `main`, participates in freshness checks. | Not a behavioral/API compatibility proof. Positional parameter names omit defaults, keyword-only arguments, annotations and runtime effects. Unknown-baseline problem A03 applies. |
| `codegraph/context_packer.py`, 32–78; `token_economy/ast_skeletonizer.py`, 14–75 | Packs one file; Python AST removes nonfocused bodies and `ast.unparse` renders the result. | Focus matches simple names, not qualified identity; output is not verbatim. Packer omits language selection, so non-Python/parse-failing input can fall back to full text. It does not rank adjacent graph nodes. |
| `codegraph/python_ast.py`, 15–57; `codegraph/traverser.py`, 17 onward | Stores Python definitions and traverses stored `CALLS` edges. | Indexed production code has no caller of `index_python_file`; `insert_edge` appears in traversal test, not an observed production population route. Do not infer a current complete call graph merely from these classes. |
| `tools/blast_radius_graph.py`, 10–79 | Python import parsing with module-stem substring matching. | Coarse candidate impact, not exact symbol/call edges. Same-name modules and dynamic consumers require explicit uncertainty. |
| `memory/intent.py`, 81–178, 268–319; `verification.py`, 216–419; `experience.py`, 440–575 | Store supplied source/check refs, compare supplied condition digests, rank supplied checks and recognize exact revision-bound execution. | These operations do not derive their own AST relationships, changed symbols or complete required-check set. Agent/app integration must supply grounded inputs. |

Additional findings discovered during this focused AST/continuation pass are source-confirmed, not new runtime reproductions. They supplement F01–F24:

| ID / priority | Evidence and consequence | Required correction/acceptance |
|---|---|---|
| A01 / P1 | Public handoff `action=dispatch` and `action=status` unconditionally return `E_UNAVAILABLE`. [memory.py](../../src/rush/tools/memory.py), 1904–1913. Direct transport helpers and restricted receive/read-back code exist separately. | Connect public lifecycle to real permitted dispatch/status. Distinguish prepared, launched, delivered, read-back and resumed; test through CLI/MCP. This is an implementation gap, not merely a missing credential or unexecuted live test. |
| A02 / P1 | `resolve_symbol_ref` resolves `root / path` without checking final containment. An absolute or `../` Python path can satisfy this grounding helper outside the intended project. [trust.py](../../src/rush/memory/trust.py), 108–127. | Apply physical containment before parsing and promotion grounding, reusing established recipe path checks. Exercise absolute, traversal and symlink cases through the promotion boundary. Public exploitability was not executed in this pass. |
| A03 / P1 | `ApiDiffer` can return `unknown` when baseline unavailable; defended recall marks API stale only for a dict result. An artifact with `symbol_ref` but no `content_hash` can therefore lack validated freshness without being marked stale. [api_diff.py](../../src/rush/tools/api_diff.py), 80 onward; [retrieval.py](../../src/rush/memory/retrieval.py), 166 onward. | Preserve unknown/unverifiable as distinct from current. Missing baseline, parse failure and unsupported language must not establish current evidence. Test both hash-bound and symbol-only records. |
| A04 / P2 | Context packer's default-Python, simple-name selection and full-text fallback do not deliver qualified, language-aware AST context. Continuity requests a million-token pack then spills/returns skipped when over budget, rather than selecting relevant nodes. [context_packer.py](../../src/rush/codegraph/context_packer.py), 32–78; [context.py](../../src/rush/continuity/context.py), 98–236. | Use explicit language/parser and qualified target identity; bound selection before returning. Test duplicate method names, nested symbols, syntax errors, non-Python sources and honest fallback labels. Avoid describing generated skeleton text as verbatim source. |
| A05 / P2 | AST/graph primitives are not connected into a production memory-to-symbol-to-consumer pipeline; current recipes/intent/check planning do not call the codegraph. See implementation table above. | Establish actual graph population/version/coverage contracts and memory references before relying on impact-driven recall. Verify real source edit → impacted memory → agent action, including unresolved dynamic edges. |

The AST development direction should be **symbol-aware learning**, not hashing more files. Retain both exact source identity and a separately versioned structural fingerprint. Exact identity supports reproducibility; structural similarity can suggest applicability after refactors. Neither grants current behavioral proof. Preserve prose/user instructions separately: they cannot be recovered from code AST alone.

#### AST installation and project initialization boundary

**AST support must not require adding parser dependencies to every analyzed project.** Parser runtimes and supported language grammars belong to the Rush installation and are reused across projects. Each project needs its own authorized index, source fingerprints and memory state; those are data, not application dependencies.

Current evidence: Python's `ast` is part of the Python standard library; Rush's Python 3.12 runtime provides it. [pyproject.toml](../../pyproject.toml), lines 29–30, already declares `tree-sitter` and `tree-sitter-typescript` as Rush dependencies. Declaration does not prove every packaged build includes working grammars or that current memory paths use them correctly; those remain installation/integration acceptance checks.

| Layer | Installation/configuration responsibility | Required behavior |
|---|---|---|
| Python AST | Rush's Python runtime | No separate `ast` installation in target projects. |
| Supported language parsers/grammars | Rush package or explicitly managed Rush parser installation | Available by default for declared supported languages; select by source language. Additional grammars must not be injected into target project environments. |
| Project index and memory | Per-project state initialized with required write permission | Record parser/grammar/schema version and source identity; update affected entries incrementally and rebuild incompatible indexes. Read-only queries must not initialize state. |
| Deeper compiler/type analysis | Optional integration with project's actual compiler, language server, configuration and installed dependencies | Distinguish syntax parsing from type/module resolution and runtime evidence. Missing toolchain limits that deeper analysis, not basic supported-language AST parsing. |

Development acceptance: analyze two clean projects using one Rush installation; verify their manifests, lockfiles, virtual environments and application dependencies remain unchanged. Verify supported parsers in installed distribution, authorized project-local index creation, parser-version invalidation, and explicit unsupported/unknown states. Installing a parser alone must not be reported as completing AST-backed memory integration.

### 6.5 Required operating foundation

These are completion requirements, not the innovative capabilities themselves. They make the portfolio usable across agents.

| ID | Required behavior | Concrete acceptance |
|---|---|---|
| B01 | Supported host starts a session with a bounded, authorized task brief and discoverable recall/write operations. | Real host loads the selected project's context; wrong project/client args fail visibly; no full-history dump. |
| B02 | Task start, relevant source edit, failed check, explicit correction and verified outcome trigger appropriate recall/capture through supported host or Rush events. | Actual IDs/revisions and write receipts appear; unsupported host event is disclosed rather than simulated. No Git hooks. |
| B03 | Compaction, interruption and handoff preserve goal, constraints, attempted/disproved approaches, source identity, unfinished work and next evidence needed. | Restart/second host restores this state; replay does not duplicate writes; stale source requires revalidation. |
| B04 | Agent-facing and human-facing views distinguish configured, connected, permitted, context delivered, evidence used and verified write. | Status agrees across surfaces and reports disabled/denied/failed/unverified conditions. |
| B05 | Shared project memory and optional user-wide memory have explicit scope, consent, precedence and correction behavior. | Same-project agents share authorized learning; unrelated projects do not inherit private records; user can inspect and change applicable preferences. |

### 6.6 Capability portfolio: what a powerful memory system should enable

**Core** means a proposed mechanism for delivering the user's requested dynamic behavior, not a claim that the user selected this exact design. **Research** means promising additional behavior whose benefit needs an experiment. Every row identifies an increment beyond the current primitive. No proposed effect is represented as measured today.

#### A. Remember investigations and improve the next decision

| ID / class | Scenario and new agent behavior | Existing foundation; missing increment | Tradeoff and decisive acceptance |
|---|---|---|---|
| E01 / Core — Evolving task state | Agent resumes a feature knowing which requirements are active, what is implemented, what failed, what remains unverified, and the next unresolved question. New evidence updates those distinctions instead of appending another summary. | `experience.prepare_memory`, intent, receipts, checkpoints. Add explicit relationships among obligations, attempts and evidence; rebuild bounded task view on relevant events. | Transcript summaries are easier but collapse attempted into completed. After compaction/agent switch, preserve all unresolved obligations and reject an unsupported completion claim. |
| E02 / Core — Choose discriminating experiments | Code and dependency changed before a failure. Agent carries competing explanations and selects a permitted check that distinguishes them, then revises the next action from its result. | Last-success deltas, relations and sandbox `verify_attempt`. Add candidate experiments linked to hypotheses, predicted distinguishing outcomes and actual receipts. | A changed-file list is cheaper but not diagnostic. Seed two plausible causes: correct cause found with fewer redundant trials; unrun/correlated cause never becomes proven. |
| E03 / Core — Condition-aware failure memory | Agent recognizes that an earlier timeout-only fix failed under the same payload/configuration conditions, avoids repeating it, and tries a different explanation. A changed condition permits retry. | Repair episodes, failure ledger, recipe outcomes. Add matching across symptom, relevant AST change, environment and attempted strategy, with explicit counterexamples. | Exact patch hashes miss equivalent mistakes; broad semantic bans reject valid retries. Measure repeated failed strategies and successful retries under changed conditions. |
| E04 / Research — Investigate contradictions | Two agents report conflicting facts about the same API. Memory preserves both with their versions/conditions and directs the next agent to inspect the difference or run a distinguishing check. | `contradicts` relations, trust/conflict code, observations. Add claim grouping and condition-aware comparison; expose uncertainty instead of silently taking newest/highest-ranked text. | More context than last-write-wins, but avoids false certainty. Conflicting facts remain unresolved until attributable evidence distinguishes them; repetition/model agreement cannot promote truth. |

#### B. Learn intent, preferences and reusable behavior

| ID / class | Scenario and new agent behavior | Existing foundation; missing increment | Tradeoff and decisive acceptance |
|---|---|---|---|
| E05 / Core — Preserve evolving product intent | “Guest checkout must work” remains attached to affected behavior through refactors and agent changes. Agent recalls why it matters and reopens its check when relevant code changes; explicit user reversal supersedes it. | `record_intent`, `check_intent`, versioned relations, AST refs. Add task/edit/scan consumers and symbol→behavior→check linkage. | Tags alone cannot prove behavior. Seed a regression with unchanged tags: current executed check catches it; earlier green revision does not close it. |
| E06 / Core — Learn corrections without inventing preferences | User rejects a framework or says to avoid a particular pattern. Another agent recognizes an equivalent reworded proposal in the same scope and chooses an allowed alternative. Inferred habits remain candidates. | Preference store, intent source references, supersession. Add correction/rejection reason, applicability and precedence over derived suggestions; retrieve before planning. | Keyword blacklists are simpler but overbroad. Catch equivalent rejected approach, allow unrelated uses, preserve later explicit reversal and original provenance. |
| E07 / Research — Induce conditional patterns and antipatterns | Repeated verified fixes reveal that one helper works and a common AST edit fails under a specific condition. Agent proposes a reusable rule with supporting and opposing examples. | Consolidation, before/after source, repair receipts, recipes. Add contrastive candidate extraction and applicability checks, not automatic promotion from frequency. | Manual recipes are safer but miss discoveries. A candidate must predict held-out applicability and abstain on exceptions; a revert or popular pattern alone proves neither defect nor correctness. |
| E08 / Core — Adapt a successful repair | Prior CSV repair becomes useful in another function with different names. Agent resolves current helper/signature, proposes bounded adaptation, tests it in sandbox, and records success or failure against that recipe version. | `resolve_recipe`, `record_recipe_outcome`, AST symbol extraction, verifier. Add structural matching and adaptation loop beyond exact-hash lookup. | Exact replay is cheaper but brittle; adaptation costs verification. Compare compatible/incompatible APIs, renamed symbols and altered dependencies; no application/promotion based solely on similarity. |

#### C. Make memory responsive to code structure and change

| ID / class | Scenario and new agent behavior | Existing foundation; missing increment | Tradeoff and decisive acceptance |
|---|---|---|---|
| E09 / Core — AST-triggered relevant recall | Before changing `Serializer.encode`, agent receives that symbol's applicable failures, decisions, callers and checks, not every record mentioning serialization. After a failed check, diagnostic evidence changes the selection. | Python AST, packer, retrieval and codegraph scaffolding. Add qualified identity, actual populated edges and event→query derivation with explicit graph coverage. | Whole-file keyword search is simpler but noisy. Duplicate names/nested methods must not mix evidence; relevant caller memory arrives within budget; dynamic callers remain unresolved where unknown. |
| E10 / Core — Revalidate dependent knowledge | An auth helper changes. Memory reopens dependent recipe advice, derived summaries, task assumptions and behavior proofs before another agent acts on them. | Source hashes, relations, consolidation freshness. Add typed dependency edges and bounded invalidation to the affected revisions, with reasons. | Full-project invalidation is safe but wastes work; inferred dependency graphs can miss effects. Test direct/transitive links, unrelated edits, cycles and missing graph coverage; no silent freshness claim. |
| E11 / Research — Preserve identity through refactors | Function moves/renames without an established behavior change. Agent can find its prior learning as a candidate and see precisely what did or did not carry forward. | Exact hashes, dotted recipe refs and AST parsing. Add repository/worktree/revision identity plus structural fingerprints and explicit alias/move evidence. | Exact path identity fragments history; similarity can merge unrelated functions. Ambiguous matches require resolution. Formatting-only edits do not erase history; old execution proof never becomes a new-revision pass. |
| E12 / Core — Derive verification obligations from change | API edit affects caller, schema and security expectation. Agent sees which obligations are covered, which require checks and which dynamic consumer lacks evidence; it chooses next check from those gaps. | Intent, `plan_checks`, API/import analysis and existing test/scan evidence. Add real symbol/consumer/behavior mapping as inputs instead of relying on caller-supplied IDs alone. | Static structure cannot supply complete runtime coverage. Preserve mandatory gates; seed a dynamic consumer and unavailable engine, both must remain unresolved rather than “all verified.” |

#### D. Transfer useful understanding across agents and worktrees

| ID / class | Scenario and new agent behavior | Existing foundation; missing increment | Tradeoff and decisive acceptance |
|---|---|---|---|
| E13 / Core — Receiving agent challenges the handoff | Sender says fix is ready; receiving agent sees exact changed symbols, checked behaviors, unresolved hypotheses and missing proof, then independently selects the next necessary action. | Handoff refs, restricted receiver, receipts, AST context. Add complete public dispatch, structured work/evidence delta and receiver reconciliation, beyond text delivery/read-back. | Larger than a summary but avoids inherited false completion. Receiver must detect a deliberately stale proof or omitted obligation and act on it; hidden model reasoning need not be stored. |
| E14 / Core — Share discoveries during parallel work | Agent A disproves a diagnosis relevant to agent B's current task. B receives a small authorized delta at its next supported event and changes its investigation without replaying A's entire session. | Version/change records, coordination and scoped retrieval. Add task interests, per-session acknowledged change position and relevance filtering. | Broadcasting every write creates noise; a new daemon is unnecessary for event-boundary polling. Two agents avoid a duplicate failed experiment; unrelated/private discoveries stay out. |
| E15 / Core — Reconcile branch-specific knowledge | Two worktrees share product requirements but carry different APIs and verification results. After merge, agent sees which lessons still apply and which need revalidation. | Per-root stores, ownership, revision refs and receipts. Add stable project identity and explicit sharing/reconciliation of selected records across worktrees. | Fully isolated stores lose learning; naive shared state contaminates branches. Concurrent conflicting results remain branch-qualified; unrelated repository receives nothing; no automatic code merge. |
| E16 / Research — Improve context allocation from actual use | Agent gets a small evidence pack, expands only where uncertainty remains, and future selection learns which records helped verified work or were explicitly rejected. Mandatory constraints remain present. | Compact retrieval, expansion, telemetry, observations. Add shown→selected action→result attribution and cost-aware ranking with exploration for new evidence. | Fixed ranking avoids feedback bias but cannot adapt. Compare equal-budget held-out tasks; require no loss of correctness/constraints and fewer useless expansions. Usefulness affects ranking, never authority. |

#### E. Integrate development evidence and make memory understandable

| ID / class | Scenario and new agent behavior | Existing foundation; missing increment | Tradeoff and decisive acceptance |
|---|---|---|---|
| E17 / Core — Explain recurrence rather than repeat fixes | Previously resolved finding reappears. Agent distinguishes actual regression, changed dependency/configuration, stale check and missing engine, then selects an appropriate investigation. | Scan new/persisting/resolved/unverified states, last-success comparison and repair records. Link finding identity/conditions to repair, current AST delta and verification. | A recurrence counter loses causal context. Dependency-only change must not be blamed on code; skipped engine remains unverified; reproduced cause needs controlled evidence. |
| E18 / Core — Reconsider advice when its conditions change | Dependency/API/security change invalidates a remembered recommendation or accepted exception. Agent recalls the original rationale, sees changed conditions and checks whether it remains acceptable. | Versioned decisions, API diff, dependency/security/license findings and expiry. Add condition-bound decision dependencies and change consumers. | Age-based expiry is easier but misses immediate change and needlessly expires stable advice. Changing package/config version reopens only applicable advice; acceptance of an old exception does not silently authorize a new one. |
| E19 / Core — Ask and correct project memory by evidence | User asks “Why did we choose this?”, “What have agents already tried?” or “Which advice is stale?” and receives cited records, alternatives, contrary evidence and affected code. Correcting a claim shows its downstream impact. | Memory queries, relations, dashboard actions and artifact versions. Add evidence-grounded question views and correction/impact workflow beyond basic search controls. | Generated explanations can invent rationale; exact citations and an explicit unknown answer are required. Correction affects future agent recall while retaining auditable history and scope. |
| E20 / Research — Rehearse and evaluate learned procedures | After relevant code evolution, an important recipe can be replayed in an admitted isolated scenario before it misleads a future agent. Results update applicability and evaluation records. | Existing benchmark scenarios, verification sandbox, recipes and receipts. Add bounded opt-in rehearsal selection and real-provider comparisons, not another execution framework. | Rehearsal costs compute and fixtures can overfit. Cap resources; preserve counterexamples; passing historical case does not claim current production success or universal generalization. |

### 6.7 One integrated target experience

This is an illustrative acceptance scenario, **not current working behavior**:

1. Claude starts an upload fix. Rush supplies confirmed file-size intent, current `UploadService.validate` source identity, and a prior timeout-only failure under matching conditions. Agent avoids repeating that attempt.
2. Agent finds two plausible causes: changed validator logic and changed dependency behavior. Memory exposes the last successful conditions and unresolved hypotheses. Agent runs a permitted distinguishing test; only its actual result updates the causal claim.
3. Codex takes over after compaction. It receives the changed-symbol delta, preserved intent, disproved attempt, latest receipts and unfinished obligations. It rechecks current source and performs the missing compatibility check instead of trusting “nearly done.”
4. Another agent works in a second branch with a different dependency version. Shared requirement carries across; branch-specific success does not. A structural recipe is offered as a candidate with the changed precondition, not applied as a known-good patch.
5. Verified outcome records what worked and under which conditions. User can inspect why it was chosen and correct a preference. A later matching task recalls that lesson; a different condition prompts revalidation rather than blind reuse.

This combines intent continuity, AST-aware context, experimental learning, conditional transfer, agent handoff and user control. A sequence of fixed tool calls alone cannot prove this experience: the receiving agents must make observed evidence-dependent decisions on varied tasks.

### 6.8 Shared contracts that make the capabilities coherent

Extend existing typed artifacts/relations where they fit; do not create twenty independent memory systems or one new store per capability. Preserve these five dimensions across ingestion, derived memory, recall and transport:

| Dimension | Required information and behavior |
|---|---|
| Meaning and authority | User-confirmed requirement/preference, agent proposal, observation, hypothesis, derived pattern, rejection and supersession remain distinguishable. Working hypotheses can be stored/recalled as hypotheses without waiting for promotion. |
| Applicability | Authorized audience/project, worktree/revision, qualified symbol/path, source and structural fingerprints, behavior, relevant dependency/configuration/environment and exceptions. Missing information stays unknown; it is not guessed. |
| Evidence and contrary evidence | Statement origins, exact artifact versions, test/engine receipts, attempts, controlled experiments and counterexamples. A receipt proves its observed scope, not all claims linked to it. |
| Action and feedback | Which evidence was delivered, what the agent selected, what it tried, what happened, which obligation remains and what later changed. Capture observable decisions/rationale, not private chain-of-thought. |
| Lifetime and delivery | Current/stale/unknown/superseded/rejected status, invalidation reason, bounded summary, authorized expansion and acknowledged handoff. Compaction and derived summaries must not drop exceptions or promote authority. |

AST-specific acceptance must cover qualified/nested/duplicate symbols, formatting-only versus body/signature/dependency changes, moved/renamed code, generated sources, decorators/inheritance/dynamic dispatch, parse errors and unsupported languages. The exact supported language set is a development decision backed by parsers and tests; the current Python-centric path cannot be advertised as universal AST memory. Preserve exact source alongside generated skeletons and label each representation.

### 6.9 Recommended capability sequence and evaluation

Prioritize **working slices through the whole memory loop**, not completion of storage modules in isolation. Dependencies below augment §6.1 rather than replace its defect repairs or human interfaces.

| Sequence | Capability slice | Why it comes here | Evidence required to expand |
|---|---|---|---|
| 1 | Safe symbol-bound recall plus observable two-agent continuation: B01–B04, E01/E09/E13 | Repairs F/A blockers while proving the minimum real agent-side path. | Sender record → receiving host read → evidence-dependent action → verified write, with stale/denied/unsupported cases. |
| 2 | Conditional failed-repair learning and discriminating experiments: E02/E03/E17 | Strongest near-term differentiation: directly changes next action using existing failure/verification code. | Held-out repeated-failure tasks improve correct resolution or reduce redundant attempts under matched budgets. |
| 3 | Product intent and correction continuity through code changes: E05/E06/E10/E12/E18 | Preserves user outcome and reopens proof when AST/dependency conditions change. | Seeded requirement regressions caught across agents; explicit requirement reversal honored; unrelated changes avoid unnecessary invalidation. |
| 4 | Adaptable project learning and shared branch knowledge: E07/E08/E11/E14/E15 | Builds on dependable identity/evidence; makes accumulated experience reusable beyond one exact patch/session. | Correct transfer on compatible cases; abstention on incompatible/ambiguous cases; parallel scope isolation and conflict preservation. |
| 5 | Adaptive selection, contradiction work and rehearsal: E04/E16/E20, with E19 throughout | Most uncertain benefits; needs usable curation and measured outcomes to avoid self-reinforcing noise. | Real-agent comparison against fixed lexical/graph recall with matched tasks, grants, models and budgets; report quality, costs, false interruptions and unverified cases. |

E19 user inspection/correction and §3 activity visibility accompany every slice; they are not postponed until the end. All twenty capabilities remain visible plan inputs; sequencing is not approval to omit later outcomes. Research mechanisms may be replaced if experiments disprove their value, while preserving the user's desired behavior and recording the decision.

Evaluate more than token savings: task correctness, repeated failed attempts, intent preservation, useful versus harmful transfer, time to first discriminating evidence, stale/unauthorized recall, false interruptions, unresolved obligations lost at handoff, total context/model/verification cost, and scope leakage. Use the existing benchmark/verification framework after fixing F20–F22. Do not compare a scripted or intentionally empty baseline against a live memory-assisted agent and call it learning benefit.

### 6.10 Learn the user's persistent workflows and suggest useful skills

**Explicit user requirement:** recognize recurring workflows, retain project-related learning, and suggest skill creation. This is more than remembering a repeated command.

Current source has useful pieces but not the learning loop. [FlightRecorder](../../src/rush/tools/flight_recorder.py), 14–76, records/replays sanitized events; indexed callers do not establish a production capture lifecycle. Opt-in invocation observation records individual results. [AgentSkillGenerator](../../src/rush/plugins/skills_generator.py), 15–71, formats an existing `PluginSpec` and emits executable instructions only when plugin closure is trusted. It does **not** infer a user's workflow or turn repeated task successes into a proposed skill. [Recipe operations](../../src/rush/memory/recipes.py), 100–382, model helper applicability and verified outcomes, not general multi-step personal workflows.

| ID / class | New capability and concrete behavior | Evidence, constraints and acceptance |
|---|---|---|
| E21 / Core — Persistent workflow learning | Across separate tasks, learn a recurring sequence such as investigate current source → reproduce failure → bounded fix → targeted checks → full required gates → review. Retain order, conditional branches, user interventions, tool/environment requirements and what counted as completion. On a comparable task, agent proposes or follows the applicable learned procedure within existing authorization. | Segment consented events by task/outcome; normalize volatile IDs while retaining conditions and permissions. Compare successful traces with failed/cancelled/overridden examples. Repeated calls alone are insufficient. Test a matching task, a changed environment and a negative example; agent adapts or abstains appropriately. |
| E22 / Core — Evidence-backed skill suggestions and evolution | Detect that a learned procedure would be useful again and suggest a named project or personal skill, explaining which prior outcomes support it and what it would save. Draft includes inputs, applicability, steps, checks, exceptions and stop conditions. Accepted skill remains linked to evidence and learns from later uses. | User can accept/edit/reject; an explicit request to create authorizes creation without another redundant confirmation. No silent installation, privilege grant or promotion of generated code. Deduplicate rejected suggestions. Version canonical procedure and host-specific exports; replay positive/negative cases and revalidate when dependencies change. |

Examples worth investigating are a repeated scan→triage→targeted review→handoff→rescan workflow, a condition-specific repair procedure, or the user's source-first architecture review process. The distinctive capability is **discovering and refining the user's successful procedure**, not generating another generic checklist. Preserve legitimate human judgment steps; do not claim they were automated. Skill candidates must offer benefit beyond an existing skill/helper, and comparable independent outcomes matter more than an arbitrary repetition count.

A learned skill is both a consumer and producer of memory: recall its current conditions, execute only permitted steps, associate real outcomes with its version, then revise applicability or propose a correction. A failed use is retained as a counterexample rather than omitted from its apparent success rate. Generated skill files remain a delivery form; canonical provenance, user corrections and outcome history stay shared across agents.

### 6.11 Remember project UI systems, architecture and inferred conventions

**Explicit user requirement:** preserve user-specified UI systems, user-preferred architecture, and architecture inferred by the system, without confusing their authority.

Current [DecisionRecordFields](../../src/rush/memory/decision_schema.py), 9 onward, describes red/green task/seam evidence rather than a complete architecture-choice record. [InvariantGraph](../../src/rush/memory/invariant_graph.py), 12 onward, stores description/rationale/active state. Preferences are project-local, and confirmed-intent primitives exist. These foundations do not currently deliver a resolved UI/architecture contract at agent task start.

| ID / class | New capability and example | Applicability, action and acceptance |
|---|---|---|
| E23 / Core — Project design-system memory | User chooses a UI system and reference artifacts. Memory retains exact approved references, tokens, component conventions, interaction/responsive/accessibility requirements, surface-specific exceptions and rejected directions. A second agent builds a new page from that system instead of inventing a style. | Trigger for affected UI tasks/files; serve compact contract plus current component/token references and expandable originals. Source repetition or a screenshot alone is not approval. Test a new page and a deliberate conflicting suggestion; agent follows explicit direction and verifies rendered behavior. Existing Python AST cannot prove React/UI semantics; supported parsers and actual UI checks are separate requirements. |
| E24 / Core — Architecture decision lineage and inferred models | Preserve user decisions, rationale, alternatives and rejected approaches; separately infer a revisable subsystem model from code/AST/calls and observations. Agent adding a feature gets both “shared CLI/MCP logic is required” and “these current modules appear to implement that boundary,” with evidence and discrepancies. | Explicit choice/approved ADR remains distinct from inferred convention. Trigger on affected seam, new module or contradictory implementation. Resolve current symbols before reuse; report architecture drift rather than rewriting intent to match code. After handoff, agent uses the shared seam and recognizes later explicit supersession. |
| E25 / Core — Layered personal/project/task guidance | User's general working preferences, project architecture/UI contracts and immediate task constraints form a compact applicable view. A correction propagates to relevant future tasks and agents without overwriting unrelated projects. | Current explicit instruction/correction governs within the host's existing instruction hierarchy; scoped approved decisions and preferences are resolved by provenance/applicability; inferred conventions remain advice. Two projects share authorized personal preferences while retaining different UI/architecture rules. No memory entry can manufacture higher-priority instructions or new permissions. |

This provides more than a static preferences file: decisions are connected to the code and work they govern, recalled when relevant, checked against current reality, corrected by the user, and transported with their scope. The agent can say “this matches your chosen system” versus “this is a pattern inferred from these modules.” Those are different claims and must remain different after summarization and handoff.

### 6.12 Use memory to improve agent behavior

**Explicit user requirement:** agent improvement. Here that means better subsequent decisions from persistent evidence and learned procedures; it does not imply retraining the underlying foundation model.

The loop is **observe task/conditions → recall applicable experience → choose action → observe result/correction → update conditional guidance → test on a later task**. Record the agent/host/version when known for reproducibility, not to declare a vendor generally superior from a small sample. Improve observable strategies, not an opaque “agent intelligence” score.

| Behavior to improve | Feedback memory should retain | What later changes | Proof |
|---|---|---|---|
| Repeated user corrections | Exact correction, prior proposal, scope and relevant contrary examples | Planner stops reintroducing the rejected approach; E06/E25 | Held-out rewording is handled correctly across hosts, without overbroad rejection. |
| Ineffective diagnosis/repair | Conditions, hypotheses, attempted strategy, actual check results and failed variants | Agent selects a more useful experiment or different applicable repair; E02/E03/E08 | Fewer redundant failures with equal or better final task correctness. |
| Missed requirements or verification | Which obligation was omitted, affected symbols and check that exposed it | Agent recalls relevant intent and includes missing check on matching tasks; E05/E12 | Seeded regression detected; required gates never removed to improve speed. |
| Excessive exploration/context | Evidence delivered versus selected, expansions, source reads, useful outcome and total cost | Agent starts with relevant evidence and expands only where needed; E09/E16 | Lower total task token cost without more omissions or worse decisions. |
| Recurring successful workflows | Conditional procedure, user interventions, exceptions and outcome-linked versions | Agent reuses or offers an appropriate skill; E21/E22 | Transfer succeeds on new comparable tasks and abstains on incompatible ones. |

Mere temporal proximity between recall and success is not causal proof. Explicit user feedback, action references and matched evaluation supply stronger evidence. Negative outcomes, uncertainty and exceptions must survive consolidation. Recommendations may change; historical observations do not. A learned strategy must never weaken permissions, ignore current user instructions, or omit required verification.

### 6.13 Make context reduction and net token savings first-class outcomes

**Explicit user priority: token savings.** Optimize the whole development task and repeated sessions, not just the size of one recall response. Reducing a context window while increasing retries, re-exploration or downstream expansion is not a saving.

| Mechanism | Current foundation and missing increment | Saving to test; failure to guard against |
|---|---|---|
| Avoid rediscovering stable facts/decisions | Typed knowledge, recipes, source validation and proposed project contracts | Recall compact applicable evidence instead of rereading multiple files/plans. Revalidate changed dependencies; do not save tokens by trusting stale facts. |
| Task-sized evidence briefs | Compact retrieval, context packing and AST skeletons | Select goal, constraints, qualified changed symbols, decisive failures and unresolved checks before rendering. Current full-text parse fallback and unqualified focus must be fixed; never hide omitted essential context. |
| Two-stage retrieval and artifact handles | Existing recall/expand/CCR mechanisms | Return small previews plus exact authorized handles, expand selectively. Count actual later expansions; a small initial page followed by full expansion is deferred cost. |
| Delta continuation across agents | Existing version/change records and restricted receiver; public dispatch gap A01 | Transfer what changed since acknowledged state, retaining critical requirements and unresolved evidence. Include receiver reconstruction/read-back cost, not only sender payload bytes. |
| Reusable workflows and conditional skills | E21/E22 plus recipes/skill formatting | Replace repeated planning/setup explanation with relevant versioned procedure. Count skill-generation, revision and per-use context; avoid bloated universal skills and automatic full-skill injection. |
| Separate stable context from changing task evidence | Preferences/design/architecture records, source/version identities | Where host supports it, reuse stable brief/prefix and send changing evidence separately. Provider prompt-cache discounts are billing behavior, not proof tokens were avoided; invalidate corrected rules immediately. |
| Outcome-aware recall and earlier useful checks | E02/E03/E16 and observation/verification | Reduce irrelevant evidence and failed attempts. Preserve rare critical constraints and new/conflicting evidence; popularity-only ranking can reinforce mistakes. |

**Accounting contract:** sum each actual model call's reported input/output usage once across sender, receiver, subagents and any summarization/learning calls. This includes repeated prompt history, memory/tool results when injected, expansions, compaction, retries and generated output. Retrieval/AST byte counts are diagnostics; do not add their tokens again if already included in a measured prompt. Report embedding usage separately by model/tokenizer and include its monetary cost. Label tokenizer estimates and unavailable host usage rather than inventing measured totals.

For matched completed tasks, report `net_generation_tokens_saved = baseline_generation_tokens - memory_generation_tokens` and `net_model_cost_saved = baseline_total_model_cost - memory_total_model_cost`. Total model cost includes embedding and background learning/rehearsal calls, actual cached/uncached billing categories where available, and failed/retried calls. Report local CPU, storage and elapsed time separately. No dollar saving is established by a fixed local token-price estimate.

Learning has an initial cost. Measure cold-start task, first reuse and repeated reuse separately; a useful skill or memory may pay back only after several tasks. Report the observed break-even point, not an assumed one. Retention and compression policy should consider reuse probability and cost **without deleting explicit constraints or their evidence**. Prefer deterministic extraction where sufficient; invoke an additional model for interpretation only when its measured utility justifies the cost.

Use paired task sets with the same permitted source, required outcomes, model settings and verification. Compare current behavior, fixed bounded recall, AST/evidence-aware recall, and adaptive workflow/skill memory. Include no-reuse tasks, misleading memories, changed dependencies and long handoffs. Promotion requires equivalent or better correctness and constraint retention, lower total cost in the target workload, and explicit reporting of cases where memory costs more. F20–F22 must be corrected before existing benchmark reports can establish this.

### 6.14 Coverage and sequence for the expanded requirements

| User-stated outcome | Required capability coverage | Planning dependency |
|---|---|---|
| Innovative/dynamic agent memory | E01–E20; evidence-dependent reasoning and action, not storage counts | Safe F/A boundaries and working B01–B04 lifecycle |
| AST as part of memory | §6.4; E07–E12/E13/E24 | Real parser/identity/graph population contracts; honest unknown/dynamic coverage |
| Persistent workflows and skill suggestions | E21/E22, with E03/E08/E20 | Production event capture, conditional sequence evidence, canonical skill version/provenance |
| Project, UI-system and architecture memory | E05/E06/E15/E23–E25 | Confirmed versus inferred authority; scoped contract resolution and current references |
| Agent improvement and especially token savings | §6.12–§6.13; E02/E03/E09/E16/E21/E22 | Exact use/outcome attribution and full cost accounting; preserve task quality |

Add workflow learning and design/architecture contracts to the vertical slices in §6.9: explicit preferences/UI/architecture recall belongs in the first real-agent slice; outcome capture and recurring workflow detection in the repair-learning slice; inferred architecture and skill adaptation depend on validated AST identity and verified outcomes. User inspection/correction and token measurement accompany every slice. None of these explicit requirements is an optional exclusion simply because a proposed implementation is difficult or initially unevaluated.

### 6.15 Revision evidence and boundaries

The expansion contains **25 capability proposals, five operating-foundation requirements, and five additional AST/continuation findings**, plus explicit agent-improvement and net-token-savings contracts. Original F01–F24, requirement ledger and recorded test results are preserved. The `orchestrate` skill coordinated three non-overlapping read-only subagents (`gpt-6-sol`, high reasoning for capability/architecture review): workflow/skill learning; UI/architecture memory; agent improvement/context/token savings, following the earlier AST lanes. Coordinator integrated results and directly verified public handoff dispatch/status.

No new runtime tests or real-client runs were performed in this expansion; earlier test counts belong to the original review. A01–A05 are source-confirmed; proposed E01–E25 benefits remain to be evaluated. No production code, skill artifact, agent installation or user memory was changed. The document is planning input; development must preserve the complete user-stated outcome and distinguish implementation, integration, observed agent behavior and measured benefit.

## 7. Verification and limits

Python verified: **3.12.12**. Commands used `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest ... -q`. Separate review lanes returned:

| Lane | Executed result | Meaning |
|---|---|---|
| Core | 58 passed: `tests/test_memory_retrieval.py`, `tests/test_memory_versions.py`, `tests/test_memory_relations.py`, `tests/test_memory_consolidation.py`, `tests/test_memory_hybrid.py` | Component regressions pass; isolated probes still reproduce F01–F05/F08. |
| Agent/continuation | 102 passed: `tests/test_agent_connection.py`, `tests/test_install_memory_activation.py`, `tests/test_memory_handoff.py`, `tests/test_providers.py`, `tests/test_phase61_transport.py` | Temporary configurations and transport components tested; not certification of actual vendor clients. |
| App integration | 48 passed, 1 deselected: `tests/test_dashboard_memory_tokens.py`, `tests/test_memory_observations.py`, `tests/test_phase61_memory_tool.py` | Backend/component evidence; captured output did not identify deselected test/reason. Interactive human workflow not exercised. |
| Coordinator | 27 passed: `tests/test_benchmark_memory.py`, `tests/test_benchmark_memory_agents.py`, `tests/test_benchmark_memory_datasets.py`, `tests/test_memory_acceptance.py` | Existing benchmark/component acceptance remains green; does not negate F20–F22. |

Reproduction recipes for defects (use temporary stores/configs only):

| Finding | Minimal observed sequence |
|---|---|
| F01/F02 | Write known artifact → archive or expire it → compare legacy/compact recall → request exact-version expansion. Active routes disagree. |
| F03 | Promote known artifact → update its content → compare defended recall with compact recall. Signature error versus changed `STATED` result. |
| F04 | Two owners, one candidate each, distinct sources → maintenance promotion for one owner. Other owner's record supplies corroboration. |
| F05 | Three eligible matches → compact recall with limit two. Complete=true and missing cursor hide remaining match. |
| F08/F09/F10/F12 | Fresh-process maintenance import; wrong-argument Codex config probe; Claude executable with no config discovery; same-session connect after recording observation. |

Coordinator's reproduced budget failure:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.benchmarks.memory_datasets import run_longmemeval_case
from scripts.benchmarks.run import _case_completion_score

with TemporaryDirectory() as directory:
    result = run_longmemeval_case(
        {"question_id": "review-budget", "question": "What was learned?",
         "haystack_sessions": []},
        decide_fn=lambda *args: "recalled context " * 100,
        max_total_tokens=1,
        workspace_root=Path(directory),
    )
    print(result.outcome, result.total_tokens, _case_completion_score(result))
# Observed at reviewed commit: scored 202 1.0
```

No live Claude/Codex/Antigravity/Z.AI session, external embedding endpoint, paid provider, public benchmark corpus, machine-wide installation, Windows/Linux execution, interactive browser or terminal QA was run. Operation-by-operation schema/help usability and root resolution across all cwd/worktree/client combinations were not exhaustively verified; retain those acceptance lanes, including missing-store reads that must not initialize state. Those lanes remain required evidence for claims concerning them. Existing test success is not a substitute. Real-host evaluation is blocked both by missing tested integrations and missing admitted live runs; supplying credentials alone does not repair F20.

This review identifies confirmed issues and material gaps across the requested surfaces; it cannot establish absence of every possible defect. Before a plan declares readiness, bind every finding and requested outcome to owner/files/dependencies/acceptance, reconcile overlapping Phase 70 proposals without deleting scope, and require a frozen-source review plus real receiving-agent evidence.

## 8. App-wide token and context reduction: implementation assessment, current research, and development opportunities

### 8.1 Scope, evidence, and conclusion

**Rush has useful context-reduction components, but does not yet have an integrated, measured token-reduction system across its app, memory, and external coding agents.** Context packing, Python outlines, derived memory caching, CCR recovery, and some bounded operation responses are reachable. Many named compression components are implemented utilities with test callers only. Provider consumption, actual delivery into an external agent's context, and quality-preserving net savings are not established by the existing gain dashboard.

This section adds the explicitly requested overall token strategy assessment to the memory review. It retains the memory, AST, workflow, skill, preference, architecture, UI-system, agent-improvement, and cross-agent requirements above. It is development-planning input, not authorization to install dependencies or implement these proposals. No source code was changed for this addition.

Repository evidence remains frozen at `ddc064117e971b48e29100004052e876e456faf2`. Three additional read-only `orchestrate` lanes used `gpt-6-sol`, low reasoning, no inherited conversation: token internals; CLI/MCP delivery boundaries; telemetry and agent usage. Coordinator owned external research, provider-path inspection, integration, and this appendix. Research accessed September 25, 2026, local date. Repository results and external-product capabilities are separate evidence classes; an upstream feature does not prove Rush or every coding-agent host supports it.

**Comparison criteria, established before recommendations:** reduction in actual model input/output and occupied context; retained task correctness and recoverability; integration with current Rush primitives; compatibility across coding-agent hosts; total latency, local resources, provider cost, permissions, and maintenance. Compare alternatives on the same workload and tokenizer. No external percentage is adopted as a Rush target or measured result.

### 8.2 Current implementation: what runs, what it saves, and what remains disconnected

| Surface | Current implementation and exact source | Actual contribution and limit |
|---|---|---|
| Explicit context packing | `src/rush/codegraph/context_packer.py:12–78`; public shared route `src/rush/tools/continuity.py:485–512` → `src/rush/continuity/context.py:98–236` | Python AST skeleton plus token accounting. User must call the route; this does not establish automatic context injection into the current agent. Budget and focus problems below restrict its value. |
| AST outlines | `src/rush/token_economy/ast_skeletonizer.py:8–87`; MCP `src/rush/mcp.py:116–124`; separate CLI compressor `src/rush/token_economy/compressor.py:8–55`, CLI `src/rush/cli.py:1884–1920` | Can expose signatures while removing other bodies. CLI/MCP use different implementations. A skeleton is a lossy view, not sufficient evidence of behavior or a substitute for reading the relevant body. |
| Derived memory cache | `src/rush/token_economy/memory_cache_gate.py:60–172`; context packing cache integration `src/rush/continuity/context.py:98–236` | Validates reusable derived rows and can avoid local repacking. Re-delivering identical cached text can still consume the same model input tokens. Local cache hit, provider prompt-cache hit, and omitted agent reread are different events. |
| CCR storage and retrieval | `src/rush/token_economy/ccr_store.py:9–68`; `src/rush/continuity/context.py:239–296` | Full packed JSON can be retained behind a hash and recovered. A short handle defers context consumption; retrieving the full value can erase that saving and add a round trip. Current retrieval is not symbol-selective restoration. |
| CLI display | `src/rush/cli_support/rendering.py:43–78`; `src/rush/theme.py:63–108` | JSON route pretty-prints the sanitized result. Human route shows summary and first 50 findings, omitting other result fields without a general recovery pointer. Small display is not proof of adequate agent context. |
| MCP delivery | `src/rush/mcp.py:22–39,573–578`; `src/rush/mcp_support/tool_registry.py:40–57,96–118` | Normal startup registers the full catalog and includes all tool names/maturity in instructions. Wrappers return shared executor results without a common task-specific projection. Actual model schema exposure depends on the receiving host. |
| Restricted receiver and bounded scan operations | `src/rush/mcp.py:41–78`; `src/rush/tools/scan.py:475–529`; `src/rush/tools/scan_handoff.py:104–113` | Restricted memory-session server narrows to `rush_memory`; scan status has signed cursors and bounded page size; handoff defaults to 2,048 tokens/8,192 bytes. Useful existing building blocks, not a general host-wide budget policy. |
| Direct provider review | `src/rush/providers/openai.py:54–72,101–108`; `src/rush/providers/anthropic.py:54–70`; `src/rush/review/llm.py:35–86` | Both providers serialize first 50 findings with indentation and cap output at 1,024 tokens. This is item-count truncation, not task-aware token allocation. OpenAI stores raw response data locally in `ProviderResult`; review projection does not propagate provider usage fields into its returned dictionary. |
| Manual token count and cache alignment | `src/rush/token_economy/counter.py:10–28`; `src/rush/cli.py:1867–1879,4165–4173`; `src/rush/token_economy/cache_aligner.py:28–47` | CLI count is heuristic; packer uses `cl100k_base`. Manual align-prompt prints counts/padding status, without delivering the transformed prompt to a provider. Neither count is universal across models. |
| Gain and project totals | `src/rush/token_economy/telemetry.py:125–183,252–296`; `src/rush/token_economy/tui_gain.py:12–37`; `src/rush/dashboard/server.py:3655–3733`; `src/rush/workflows/projects.py:1212–1265` | Ledger-derived payload estimates, memory-event costs, and scan-child token totals exist. General coding-agent consumption and provider billing are unavailable; some labels incorrectly imply delivery/reuse. |

**Implemented helpers with no production callers found in indexed code:** `OutputShaper` (`src/rush/token_economy/output_shaper.py:7–27`), `ContentRouter` (`router.py:16–81`), `TokenChunkPaginator` (`paginator.py:16–38`), command distiller dispatcher (`distillers/__init__.py:27–32`) and its pytest/ruff/cargo/vitest implementations, `PromptCompressor` (`prompt_compressor.py:8–17`), `StaleSweeper` (`stale_sweeper.py:6–34`), `PolyglotAstCompressor` (`polyglot_compressor.py:6–68`), and TOON encoder/decoder under `src/rush/token_economy/toon/`. These are reusable candidates, not evidence of savings on normal commands. Exhaustive indexed reference checks covered 866 code files; this conclusion does not claim absence of external consumers or unindexed dynamic loading.

Existing documentation already contains corrections worth preserving: `docs/adr/0038-context-intelligence-engine-and-ccr-architecture.md:1` marks historical savings as design targets and recovery as conditional on retained chunks; `docs/adr/0039-toon-format-wire-serialization-for-fastmcp.md:1` says TOON remains planned, does not replace MCP JSON-RPC, and lacks a universal `--format toon`. Historical body text must not be mistaken for shipped behavior.

### 8.3 Additional findings for the development plan

Prior memory findings remain open. IDs below add token-specific evidence; they do not replace F01–F24 or A01–A05. Priority denotes planning impact, not an already approved implementation order.

#### TR01 — P1: context budget is not a reliable hard bound

`ContextPacker.pack(max_tokens=1)` returned **40 tokens** and duplicate closing `</rush_context>` tags in the bounded probe. Truncation at `src/rush/codegraph/context_packer.py:65–69` can leave invalid framing and still exceed the requested budget. Public `pack_context` first requests an internal cap of **1,000,000**, then returns a skipped/CCR recovery response when the selected payload exceeds the user budget (`src/rush/continuity/context.py:151–209`). That omission behavior is intentional in the CCR contract, but does not construct the most useful smaller evidence packet. These are two different issues: broken direct cap enforcement and missing budget-aware selection.

**Required outcome:** account for framing, metadata, and recovery pointer overhead; select evidence before serializing; return an explicit minimum-budget error when even the mandatory envelope cannot fit. Never remove status, error, provenance, or permission information merely to satisfy a size target. Acceptance must count the actual delivered representation, not just inner text, and cover tiny budgets, Unicode, long identifiers, and malformed input.

#### TR02 — P1: advertised compression architecture is mostly outside normal execution

Router, distillers, output shaper, paginator, prompt compressor, polyglot compressor, TOON, and stale sweeper have test references but no production caller found in the indexed corpus. Their test success cannot establish automatic reduction in CLI/MCP output, external agent context, or provider requests. Shared invocation returns results without this general projection layer (`src/rush/invocation/executor.py:423–485`; `src/rush/mcp_support/tool_registry.py:40–57`).

**Required outcome:** document a producer → transform → delivery → consumption path for each enabled feature. Reuse suitable helpers after fidelity review; do not wire lossy utilities indiscriminately. Acceptance must call public CLI/MCP routes and demonstrate selected transforms execute, with original evidence retrievable under the same authorization.

#### TR03 — P1: savings display lacks a production savings producer and billing basis

No production caller of `TelemetryStore.record_savings` was found in indexed `src/rush`; tests explicitly populate it. Summary computes `max(0, sum(raw) - sum(compressed))` and estimated dollars at a fixed **$3 per million tokens** (`src/rush/token_economy/telemetry.py:252–296`). Clamping also hides negative net reduction. Dashboard presents ledger values as `actual.raw_tokens` and `actual.sent_tokens` while correctly declaring provider usage unavailable (`src/rush/dashboard/server.py:3711–3729`). Recorded payload sizes alone do not prove the agent saw them or that its bill changed.

**Required outcome:** distinguish observed bytes, tokenizer estimates, delivered context, provider usage, and matched-run counterfactuals. Preserve negative results and unknowns. Price only provider-reported units with model/date-specific rates when available; never turn missing usage into zero cost. Label pre-integration ledgers as such instead of presenting a live savings success.

#### TR04 — P1: cache metrics misclassify memory costs as reuse

`src/rush/workflows/projects.py:1240–1263` aggregates retrieval, expansion, packing, handoff, and embedding costs into `cache_hits.total_tokens`. Those are cost events, and packing is recorded on a miss (`src/rush/continuity/context.py:209–222`). Dashboard `warm_fill_count` counts stored context-pack artifacts (`src/rush/dashboard/server.py:3681–3683`), not observed hits. Existing test at `tests/test_project_token_usage.py:83–108` encodes this label rather than validating its meaning.

**Required outcome:** independent fill, lookup, validated reuse, delivery, expansion, and model-cache events. A cache artifact is not a consumed hit. A consumed hit is not automatically reduced model input. Tests must start from the real producing event and assert the correct semantic category, not manually write the desired total.

#### TR05 — P1: bounded human output can hide the useful result

Human `render_result` omits raw/metadata/metrics/artifacts and limits findings to 50 (`src/rush/theme.py:63–108`). Scan status and scan-handoff put their operation payloads in `raw` with empty findings (`src/rush/tools/scan.py:180–203,387–400`; `src/rush/tools/scan_handoff.py:180–194,408–420`). Human output can therefore reduce to a generic status while concealing continuation or scan information. Full JSON avoids that omission but transmits much more content.

**Required outcome:** operation-aware compact views with required fields, omitted counts, and a usable recovery handle. Token reduction must reduce redundancy, not remove the user/agent's next action. Reconcile with Phase 70 T16 (`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md:74–78`), which is a proposal rather than implemented proof.

#### TR06 — P2: recovery and retrieval can postpone rather than avoid tokens

CCR retrieval emits the stored redacted value in full (`src/rush/continuity/context.py:239–296`). AST packing is not yet a populated, task-aware memory dependency graph, as A04–A05 establish. Calling pack, reading a handle, restoring everything, and rereading original source can cost more than one direct read. Local cache reuse saves computation but does not establish provider prefix reuse.

**Required outcome:** selective retrieval by qualified symbol, evidence ID, section, or authorized range; revision-bound handles; explicit missing/expired recovery. Measure cumulative expansion, requests, retries, and rereads across completed tasks. Keep full recovery available when necessary rather than optimizing a single response at the expense of correctness.

#### TR07 — P2: MCP catalog exposure is not task-sized

Default instructions enumerate all tools and default registration exposes the full catalog (`src/rush/mcp.py:22–39,573–578`; `src/rush/mcp_support/tool_registry.py:96–118`). Restricted memory-session mode is a useful exception (`src/rush/mcp.py:41–78`). Actual schema tokens depend on host discovery behavior; this review did not measure every host's rendered prompt.

**Required outcome:** catalog-derived capability profiles and discovery support, tested per host. Measure names, descriptions, schemas, instruction duplication, and tool-search round trips separately. Do not expose multiple aliases or repeat full descriptions in bootstrap context without a measured need. Do not hide necessary tools in a way that strands an agent without discovery or fallback.

#### TR08 — P2: cache alignment currently adds tokens without demonstrated benefit

`CacheAligner(min_prefix_tokens=100).align_prompt("hi")` produced **161 aligned tokens**. Padding occurs in `src/rush/token_economy/cache_aligner.py:36–47`; CLI prints metrics only (`src/rush/cli.py:4165–4173`). No production provider use of this aligned prompt was found. Artificial padding is therefore not evidence of a saving and increases context if sent.

**Required outcome:** prefer naturally reusable stable prefixes and provider-native cache semantics. Only consider padding if a supported provider's complete measured cost/latency experiment justifies it; do not make it the default strategy. Unsupported clients report unavailable cache control.

#### TR09 — P2: inconsistent tokenizers and transforms weaken budget claims

CLI heuristic counting (`src/rush/token_economy/counter.py:10–28`), `cl100k_base` packing (`src/rush/codegraph/context_packer.py:12–78`), and differing CLI/MCP Python outline implementations do not define a single actual-model budget contract. Polyglot compressor existence does not establish semantic language coverage. Source-backed AST grounding limitations are detailed in §6.4.

**Required outcome:** carry model/tokenizer/encoding version and estimate provenance. Use a calibrated margin when host tokenization is unavailable, with explicit limits on the guarantee. Share canonical outline semantics; preserve qualified symbol identity, decorators, signatures, relevant constants, and required dependencies. Report parser failures and fallback behavior instead of claiming semantic compression.

#### TR10 — P1: direct provider review silently selects a fixed first 50 findings

Both provider paths build a prompt describing `len(findings)` findings but serialize `findings[:50]` (`src/rush/providers/openai.py:38–57`; `src/rush/providers/anthropic.py:38–57`). No task-aware input token budget is applied there. Large messages in the first 50 can remain large; important later findings are omitted. `_maybe_call_llm` returns summary/provider metadata without normalized provider usage (`src/rush/review/llm.py:35–86`), although OpenAI's `ProviderResult.raw` retains the response (`src/rush/providers/openai.py:101–108`).

**Required outcome:** explicit selected/omitted counts, deterministic relevance/severity policy, recoverable finding IDs, and a real input allocation. Extract usage at the provider boundary and retain it through result projection. Acceptance includes a critical 51st finding and oversized individual findings; an output-token cap must not be presented as an input cap.

#### TR11 — P1: end-to-end savings and agent improvement remain unproven

Local mechanics tests do not show a coding agent completing the same task with fewer tokens. F20–F22 already identify benchmark wiring and quality/budget deficiencies. `project_token_usage` only aggregates available `child.metrics.total_tokens` from scan-run manifests (`src/rush/workflows/projects.py:1212–1265`), not all external coding-agent activity. Connected MCP, a stored memory, a successful retrieval, and an agent actually applying that memory are four separate observations.

**Required outcome:** matched task evaluations and real receiving-agent sessions; completion correctness, regressions, and correction effort beside usage. Show precisely where observability ends for opaque CLI clients. Do not claim autonomous context editing, automatic memory use, or successful provider switching until a receiving host demonstrates it.

### 8.4 Current strategies and developed resources: head-to-head assessment

The following are mechanisms to compare, not a shopping list. Reuse Rush where it already has the required storage, permissions, identity, and result contract. Evaluate an external implementation only where it supplies a material missing capability. No resource below was installed or benchmarked during this review.

| Strategy and primary resource | What it reduces | Fit, limitation, and assessment for Rush |
|---|---|---|
| CLI result filtering: [RTK savings explanation](https://github.com/rtk-ai/rtk/blob/develop/docs/guide/resources/savings-explained.md) | Bash output before it becomes model input. Upstream explicitly distinguishes output reduction from whole-session/bill reduction and labels token counts as estimates. | Useful baseline for Rush's dormant command distillers. Compare actual rendered diagnostics, exit status, required failure evidence, recovery cost, and total task tokens. Avoid double-counting an output already reduced by RTK. Reuse native engine JSON whenever it is more reliable than text parsing. |
| Output isolation and indexed recall: [context-mode](https://github.com/mksglu/context-mode) | Keeps bulk output in a subprocess/index and returns derived answers or matching excerpts. | Closest developed reference for making Rush CCR/query retrieval useful before bytes enter context. Adopt the selective-result mechanism through existing permissions and artifact storage; do not copy its headline reduction into Rush. Its process boundary alone is not evidence of a security sandbox suitable for arbitrary untrusted code. |
| Budgeted repository maps: [Aider repository map](https://aider.chat/docs/repomap.html) | Selects important code structure using dependency ranking and a context-sensitive map budget. | Strong reference for replacing full-pack-then-spill with ranked symbol selection. Structural relevance is useful but does not establish task completeness. Rush should add memory/decision/test relationships and freshness checks, using existing AST work rather than requiring Aider. |
| Semantic symbol retrieval: [Serena retrieval capabilities](https://github.com/oraios/serena) | Symbol lookup, references, and other language-aware queries reduce whole-file reads. | Compare AST-only indexing against an optional language-server backend. Language servers offer semantic facts but vary by language and may require project toolchains/dependencies. Keep cheap syntax-level operation available and disclose semantic capability gaps; no per-project parser install should be assumed. |
| Deferred tool schemas: [OpenAI tool search](https://developers.openai.com/api/docs/guides/tools-tool-search), [Anthropic tool-context controls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context) | Loads a relevant subset of tool definitions, reducing upfront schema context. | Use generated workflow profiles and host discovery capabilities. Search itself has cost and wrong-tool risk. Provider API support is not proof the Claude/Codex/Antigravity/Z.AI host allows Rush to configure it. Maintain tested compatibility routes and observe actual schema delivery. |
| Local/programmatic tool composition: [Anthropic code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp) | Filters intermediate data outside model history and can combine operations before returning a small result. | Prefer bounded typed Rush query operations over unrestricted execution. Reuse shared invocation authorization and audit per operation. Measure fewer model round trips against local execution cost and retained evidence; a batch does not authorize its constituent writes. |
| Provider prefix caching: [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) | Reuses a stable prompt prefix to reduce eligible processing cost/latency. It does not remove those tokens from context. | Stable policy/project prefixes followed by changing task evidence are a better starting point than padding. Track provider-reported cache usage and model support. Prefixes and provider KV state cannot be assumed portable across agents/providers. Compaction may change cache hits while still improving total cost. |
| Provider-native compaction: [OpenAI compaction](https://developers.openai.com/api/docs/guides/compaction); tool-result editing in [Anthropic tool-context controls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context) | Shrinks retained history or removes obsolete tool-result content. | Use only through supported host/API adapters. OpenAI compaction includes an opaque encrypted item and retained context, so it cannot serve as Rush's portable, user-searchable memory representation. Keep structured, source-backed Rush continuation memory alongside it. Honor provider-specific handling instead of manually pruning returned compaction structures. |
| Compact structured representation: [TOON specification, implementations, and benchmarks](https://github.com/toon-format/toon) | Removes repeated structure, especially for uniform arrays/maps of primitive records. | Compare compact JSON, TOON, and a task-specific projection. Irregular deeply nested data is not a universal TOON win. Keep canonical structured results and MCP framing; enable optional representations only after conformance, model comprehension, and full token-cost checks. Existing Rush utilities require comparison against upstream fixtures. |
| Learned prompt compression: [Microsoft LLMLingua](https://github.com/microsoft/LLMLingua) | Uses a smaller model to remove predicted low-value tokens; LLMLingua-2 uses a token-classification approach. | Optional experiment for verbose prose/log context after deterministic selection. Adds local model/runtime, latency, memory, and fidelity costs. Do not use as default for executable code, exact diagnostics, user instructions, numbers, negative constraints, or authoritative decisions. Keep source pointers and measure missed facts and repair cost. |
| Structured results and resource links: [MCP tools specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Enables structured responses and references to larger resources; reduction depends on host rendering and fetching. | Keep valid JSON-RPC and output-schema conformance. The spec recommends serialized text alongside structured results for compatibility, so blindly deleting one representation is not a safe universal optimization. Test each host's presentation for duplication and negotiate a compact projection without breaking clients. |

**Comparative judgment:** start with task selection, source-level queries, lossless projection, and explicit recovery because they fit Rush's existing implementation and are testable without another inference model. Add host-specific discovery, history management, and prefix caching where capability probes establish control. Treat TOON as a shape-dependent representation choice and learned compression as an evaluated optional route. Neither a bigger context window nor a local response cache alone solves repeated irrelevant context.

### 8.5 Proposed integrated design: memory chooses evidence, agents consume it, outcomes improve selection

The valuable addition is a closed feedback loop around evidence consumption: task and current code state determine a bounded packet; the agent can request missing detail; actual edits/tests reveal whether the packet was sufficient; memory records reusable results and corrections; the next agent receives only the relevant, still-valid evidence. This is more than naming a compressor “agentic.” Rush must expose the operations and feedback needed for the agent to notice missing evidence and correct its selection.

Proposals TC01–TC14 extend §6 rather than supersede it. Each identifies a concrete behavior, reuse point, tradeoff, and acceptance condition. They are candidate work packages for the later plan, not claims of developed functionality.

#### TC01 — Compile a task-specific context packet from current evidence

**Behavior:** a request to repair a named function obtains the applicable user constraints, relevant project decisions, qualified symbol body/signature, callers or tests needed for that repair, recent failed approaches, and unresolved work. Unrelated preferences and historical transcripts stay searchable outside the prompt. Each item carries revision, provenance, scope, and a reason for inclusion; the packet exposes omitted categories and expansion handles.

**Reuse/integration:** evolve `ContextPacker`, memory query APIs, continuity envelopes, and AST indexes. Maintain exact user instructions as authoritative records; an inferred preference or agent-generated summary cannot override them. Separate global preferences, project architecture/UI decisions, task state, and hypotheses. Hard requirements remain present even when a learned relevance score is low.

**Tradeoff/acceptance:** ranking can omit a necessary dependency. Require correctness on tasks with off-path callers, duplicate symbol names, migrations, and contradictory old memory. Budget includes the entire rendered packet. When required facts cannot fit, return a clear constrained result plus safe expansion path, not a falsely complete packet.

#### TC02 — Make retrieval an explicit, reversible evidence ladder

**Behavior:** overview → relevant fact/signature → exact symbol or diagnostic → larger source range, with each level retrieved from the same immutable artifact/revision. A test log initially returns failed tests and representative causes; the agent can retrieve one failure's full traceback without restoring the full suite output.

**Reuse/integration:** extend CCR and existing memory expansion rather than create another blob store. Add typed section/symbol/range selectors, token/byte estimates, retained-until state, and verified source hashes. A user can inspect the same original from the dashboard. Permission, retention, revocation, redaction, and project ownership apply at every expansion.

**Tradeoff/acceptance:** extra requests can erase savings. Compare full read against realistic expansion sequences. Missing or expired originals are explicit failures; a summary is not presented as recovered exact source. Verify no unauthorized content crosses a handle boundary.

#### TC03 — Deliver operation-aware compact results through all app interfaces

**Behavior:** shared scan, memory, review, and handoff results have projections that preserve status, counts, next action, errors, required findings, source IDs, and an omission manifest. CLI, TUI, dashboard, and MCP render these consistently; full canonical results remain available.

**Reuse/integration:** canonical `ToolResult`, shared invocation executor, existing output shaper/distillers after fidelity review, scan cursor implementation, and artifact storage. Apply the projection near delivery so full results remain available to internal workflows. Prefer engine-native structured output over regex parsing; a parser error selects a faithful fallback and reports degraded reduction.

**Tradeoff/acceptance:** smaller output is unsafe if it hides evidence. Assert status/exit semantics, required findings, unknown fields needed by consumers, Unicode, duplicate diagnostics, and end-to-end recovery through public routes. Compare compact JSON before adding another encoding. Human and agent next actions must remain usable.

#### TC04 — Return changes since an acknowledged result instead of repeated full reports

**Behavior:** after an edit, an agent receives new, resolved, and changed findings plus the current overall status; unchanged findings remain referenced. File and symbol changes invalidate affected memory/context entries. Unchanged code navigation reuses a current evidence reference instead of asking the agent to reread a full map.

**Reuse/integration:** scan snapshots, signed cursors, content hashes, memory revisions, run identity, AST source anchors. Delta responses name both baseline and current snapshot. Distinguish “agent received baseline” from “baseline exists in storage”; send a full compact snapshot if the receiving agent cannot acknowledge the baseline.

**Tradeoff/acceptance:** incorrect invalidation can conceal regressions. Test renames, worktrees, branches, tool/config/version changes, suppressed findings, expired snapshots, and a second agent with no prior baseline. Never infer a finding is resolved merely because it was not returned in a page.

#### TC05 — Make tool discovery and bootstrap context match the active task

**Behavior:** initial agent context contains a short Rush capability description, active memory scope/status, and the means to discover relevant operations. A memory continuation task does not need every quality-engine schema immediately. An agent entering test repair discovers that workflow's tools without receiving unrelated tool descriptions repeatedly.

**Reuse/integration:** canonical catalog plus restricted memory-session registration; adapters expose host-supported discovery or explicit profiles. Generate profiles from one catalog so CLI/MCP permissions and schemas do not diverge. Bootstrap files point to durable state instead of accumulating session history. Applicable mandatory user instructions remain available and are not silently dropped to meet a budget.

**Tradeoff/acceptance:** minimal bootstraps can impair tool discovery. Test task success, discovery retries, schema token counts, alias duplication, and fallback in each client. Report configured, connected, callable, and actually consumed status separately. No blanket claim that MCP connection means memory is active in the model.

#### TC06 — Support bounded local queries over large tool results

**Behavior:** an agent asks for “new high-severity findings in changed files, grouped by rule” or “failed tests touching this symbol.” Rush evaluates a typed filter/join/projection against retained results and returns the answer with counts and source handles. The model need not ingest and mentally join every raw result.

**Reuse/integration:** existing scan/memory stores, canonical IDs, AST relationships, and invocation authorization. Begin with a small typed query surface, not a general execution runtime. Include exact query and data snapshot in provenance; failed joins or missing relations are visible rather than fabricated.

**Tradeoff/acceptance:** the query planner becomes a correctness boundary. Compare results against canonical records; test omitted pages, stale graphs, unavailable engines, and permission-filtered records. Savings include schema/query overhead and follow-up expansions. Keep state-changing tool execution separate from read-only data reduction.

#### TC07 — Allocate context across a task and its subagents, not one response at a time

**Behavior:** a coordinator gives each agent a bounded relevant packet and stable evidence IDs; workers return decisions, changed symbols, findings, and unresolved evidence needs. Shared mandatory instructions are preserved while unrelated history is not copied to every worker. The next packet changes when test feedback or user correction changes the task.

**Reuse/integration:** run/agent/session identity, memory scopes, continuity receipts, TC01/TC02. Keep a per-recipient record of delivered evidence and revision. A reference is usable only if the receiver can retrieve it; do not assume model context is shared across agents.

**Tradeoff/acceptance:** coordination itself consumes tokens and can lose context. Compare equivalent single-agent and multi-agent tasks, count every worker call, and measure correctness and latency. Mandatory facts, failed approaches, and open questions survive handoffs; controller summaries are not treated as proof of the worker's outcome.

#### TC08 — Learn reusable workflow context without expanding permanent instructions

**Behavior:** repeated successful task sequences suggest a project workflow or skill candidate. For example, repeated UI work with an explicitly chosen design system yields a compact recipe pointing to current tokens/components and relevant acceptance checks. Repeated architecture decisions yield scoped constraints and rationale; learned patterns remain distinguished from user decisions. Only the relevant skill fragment is loaded for the current task.

**Reuse/integration:** §6 workflow/skill and user preference proposals, memory provenance, AST anchors, test outcomes, TC01. A candidate records evidence, frequency, project/version scope, failure conditions, and estimated break-even reuse. User confirmation governs promotion of an inferred preference into a user rule. Skill creation suggestion and skill activation are separate states.

**Tradeoff/acceptance:** an automatically learned recipe can institutionalize a mistake or bloat prompts. Replay held-out similar tasks, negative cases, and user corrections; compare acquisition/maintenance cost against later tokens and correction rate. Invalidate instructions tied to removed components or changed architecture. Do not copy whole transcripts into every agent's instruction file.

#### TC09 — Preserve portable continuation while using host-native compaction where available

**Behavior:** before a supported host compacts or switches agents, Rush persists a bounded structured continuation state: current goal, exact accepted requirements, code/revision anchors, completed evidence, failed attempts, unresolved hypotheses, active workflow, and next validation. A receiving agent verifies current state, selectively expands evidence, and acknowledges receipt.

**Reuse/integration:** existing memory/continuity envelopes and adapter work from §3/§6; resolve public handoff blockers first. Provider-native compaction is a separate optimization within a host. The portable Rush representation remains human-searchable and does not rely on encrypted provider internals.

**Tradeoff/acceptance:** hosts differ in lifecycle events and context control. Publish per-adapter capability states, including manual fallback and unavailable telemetry. Run real Claude→Codex and another independently supported adapter transition with changed code and stale memory. The receiver must resume correctly without a transcript dump or an invented claim of automatic injection.

#### TC10 — Add real stable-prefix caching where Rush owns the provider request

**Behavior:** direct provider review separates stable policy/project context from changing findings, avoids unstable timestamps/order in reusable prefixes, and records actual cache usage. Relevant memory changes invalidate the relevant prefix; stale content is never retained merely to preserve a hit.

**Reuse/integration:** existing provider adapters, cache adviser/alignment code only where correct, normalized usage receipts. For external coding agents, advertise guidance/capability and record actual support rather than pretending Rush controls their prompt assembly. Keep provider cache metadata out of portable memory semantics.

**Tradeoff/acceptance:** reordering can change meaning and cache writes may cost more on one-shot tasks. Evaluate cold/warm/invalidated cases with complete cost and latency. No artificial padding or cross-provider KV reuse assumption. Cached input remains part of context accounting.

#### TC11 — Choose representation based on payload shape and required fidelity

**Behavior:** use compact JSON or a concise typed view for general responses; consider TOON for large uniform result rows; use source-backed AST views for code navigation; experiment with learned compression only for suitable prose. Include enough format description for accurate consumption without repeatedly injecting an entire specification.

**Reuse/integration:** dormant serializers, router, distillers, shared result schemas. Add conformance and model-comprehension evidence before activating a representation. Canonical storage and machine contracts remain stable. Selection must consider encoding instructions and later recovery overhead, not just standalone payload size.

**Tradeoff/acceptance:** smaller serialization can increase model errors. Test escaped strings, nulls, numeric precision, nested irregular records, truncated records, and exact diagnostic identifiers across representative tokenizers/models. If a transform expands total tokens or lowers correctness, retain the simpler representation for that class.

#### TC12 — Make the savings ledger evidence-based and user-explainable

**Behavior:** Tokens view separates delivered context, provider-reported usage, local retrieval/embedding work, cache events, and estimated avoidance. A user can open “why this memory was selected,” “what was omitted,” “what did the receiver consume,” and the exact comparison behind a savings claim. Unknown host usage remains unknown.

**Reuse/integration:** telemetry store, `project_token_usage`, dashboard/TUI, invocation IDs, provider adapters, agent-session receipts. Attach artifact hash, recipient, tokenizer/model, transform/version, parent invocation, and measurement provenance. Deduplicate event retries. Embedding usage has its own unit/category.

**Tradeoff/acceptance:** detailed telemetry can itself be expensive or sensitive. Store minimal metadata by default and reference protected artifacts. Reconcile known provider fixtures exactly; replay events without double-counting; preserve negative savings and unknowns. A successful memory query is not sufficient evidence the model used its result.

#### TC13 — Improve retrieval from observed outcomes and correction cost

**Behavior:** when a chosen memory or code packet leads to a failed edit, the agent records what fact was missing or wrong. When a later expansion resolves the issue, Rush can prefer that evidence for similar tasks. Repeated unhelpful memories are demoted or revised; successful reasoning remains scoped to the circumstances that validated it.

**Reuse/integration:** §6 agent-improvement proposals, failure memories, stable source IDs, tests/scan results, and TC12 receipts. Start with explainable rules and offline evaluation before any adaptive ranking. Treat success attribution as uncertain when multiple changes intervene; user correction outranks historical popularity.

**Tradeoff/acceptance:** more retrieval is not always better and a passing test is not universal correctness. Evaluate held-out tasks, contradictory memories, changed project architecture, and agent/model differences. Track avoided repeat mistakes and total successful-task tokens, not memory hit rate alone. No model-weight training is implied.

#### TC14 — Avoid repeating discovery and analysis when dependencies are unchanged

**Behavior:** Rush can answer that a prior symbol map, architecture check, or selected workflow evidence remains valid when its complete dependency set is unchanged; only affected derived artifacts refresh after edits. The agent receives the validated result and the reason it remains current, rather than recomputing and rereading the same evidence.

**Reuse/integration:** content-addressed artifacts, AST relationships, configuration/engine versions, memory invalidation, scan snapshots. Cache keys include relevant source, settings, environment/tool identity, permissions, and query/transform version. External state and nondeterministic tests require separate freshness policies; do not reuse test success merely because one source file is unchanged.

**Tradeoff/acceptance:** incomplete dependency capture makes reuse wrong. Compare cold/warm runs, changed transitive dependencies, generated files, config changes, and toolchain changes. Measure local work, model calls avoided, and stale-result rate separately. This is a proposal to reuse verified analysis, not a claim Rush currently skips all redundant work safely.

### 8.6 AST deployment and semantic depth: explicit decision for the plan

**No: syntax-level AST use should not require installing an AST dependency into every target project by default.** Rush's own environment supplies its parsers; projects supply source files and their own generated indexes. Python uses the standard library AST; Rush declares tree-sitter dependencies in `pyproject.toml:29–30`. Installing a package does not establish language coverage: current TypeScript/Rust regex extraction limitations and graph integration defects remain in §6.4.

Choose capability levels explicitly. Syntax parsing and symbol outlines can operate without changing a project's dependency manifest. Deeper references/types may require a language server and the project's normal dependencies, compiler configuration, generated code, or workspace environment. Those are optional semantic capabilities to detect and explain, not an excuse for silently modifying every project. Compare AST-only retrieval with optional semantic retrieval using TC01/TC14 accuracy and token criteria.

Index per project/worktree identity and revision, retain source hashes and parser versions, and invalidate derived memory when its anchors change. Index existence is not proof of freshness. A memory item tied to a removed symbol or UI component should trigger refresh or an explicit stale result, not confident injection. Full code and exact errors remain recoverable when the outline is insufficient.

### 8.7 Measurement contract: optimize successful work, not the smallest response

Use three separate ledgers, linked by request/artifact identity:

1. **Local evidence ledger:** raw bytes, transformed bytes, tokenizer-specific counts, transformation/indexing/embedding cost, selected/omitted evidence, cache fill/hit, and latency. This proves local work and representation changes only.
2. **Delivery ledger:** actual payload/hash presented to a named host/agent, discovery and expansion steps, acknowledgement where available, compaction/handoff lineage, and retries. A server response proves it was returned to the client; only host instrumentation can establish what was inserted into model context.
3. **Provider ledger:** reported input/output and provider-defined cache usage/cost dimensions for every actual model request, including subordinate agents, summarizers, retries, and memory construction. Unavailable usage stays unavailable. Do not add cache-read counts to total input when the provider defines them as a subset; normalize each provider's semantics first.

For matched runs:

`net token reduction = baseline total actual model tokens - candidate total actual model tokens`

Count each request once, including memory extraction, retrieval planning, compression-model calls, extra expansions, and repairs if they invoke models. Tokens already present in that request's input must not be counted again as a separate retrieval charge. Record embedding units separately. Compare token totals only with consistent model/tokenizer definitions, or report a per-model vector when models differ. Monetary comparison uses actual eligible rates and cache charges, not a single dollars-per-token constant. Savings may be negative.

**Required comparison arms:** ordinary agent workflow; existing Rush public routes; repaired deterministic projection/retrieval; optional encoding/learned compression or native caching where supported. Same repository revision, task, permissions, available tools, model configuration, and outcome criteria; separate cold/warm caches. Repeated trials account for nondeterminism. Baseline should be a competent normal workflow, not an invented whole-repository read that artificially inflates savings.

**Quality gates:** correct patch and tests, preserved explicit user requirements, no missing critical diagnostic, accurate citations, stale-memory rejection, valid recovery, and correct cross-agent continuation. Measure task success, correction/retry count, peak context, total provider usage, wall time, local CPU/RAM, expansion rate, and attributable spend. Token reduction cannot compensate for failed quality gates. Negative and inconclusive results belong in the report.

Use realistic tasks covering repeated bug repair, new code, architecture changes, UI-system compliance, large failure logs, search miss, stale memory, duplicate symbols, unsupported languages, branch/worktree changes, a critical late finding, contradictory preferences, and agent switching. Specifically test a useful fact that initially appears irrelevant: the system must enable the agent to notice the gap and expand. §7's benchmark deficits must be repaired before using its current scores as this evidence.

### 8.8 Development-plan reconciliation and dependencies

These work packages preserve all requested outcomes. Detailed scheduling should follow dependency and acceptance mapping rather than declaring the currently easiest subset complete.

| Planning package | Findings and proposals | Dependency and required evidence |
|---|---|---|
| Correctness and honest accounting | TR01, TR03–TR05, TR09–TR11; TC12 | Valid output/budgets, preserved required findings, event semantics and normalized provider usage. Existing passing tests must be corrected where they encode misleading labels. |
| Shared result delivery and selective recovery | TR02, TR05–TR06; TC02–TC04, TC06 | Public CLI/MCP routes, canonical artifact ownership, revision-bound handles, permission-safe recovery. Include TUI/dashboard usability; reconcile Phase 70 without removing its requirements. |
| AST- and memory-driven context selection | TR01, TR06, TR09; TC01, TC08, TC13–TC14 | Repair AST/graph and memory defects in earlier sections; connect source/test/decision/workflow evidence; validate held-out quality and invalidation. Preserve user-specified UI/architecture preferences and searchable provenance. |
| Cross-agent lifecycle and provider capabilities | TR07–TR08, TR11; TC05, TC07, TC09–TC10 | Real capability checks, receiving-agent acknowledgement, actual host lifecycle support, public handoff repairs, and cold/warm provider receipts. Agent-neutral memory remains canonical. |
| Evidence-based optimization and acceptance | TC11 plus §8.7 across every package | Head-to-head realistic workloads; no global savings claim from helper tests, simulated episodes, estimates, or a connected MCP server. Optional dependencies require a demonstrated net benefit and supported installation path. |

Do not create a parallel memory database, a second permission model, or a new generic agent runtime solely for these proposals. Build on current shared implementations. Do not activate every dormant helper as a shortcut: each transform must prove its output remains useful. No unrequested Git hooks are part of this design.

### 8.9 Verification performed for this appendix and remaining evidence

Source audits used Graft discovery and exhaustive indexed references, followed by exact missing spans. Source/tests remained unchanged at the frozen commit; pre-existing `AGENTS.md` edits and untracked work were preserved. The original report's first **92,041 bytes**, SHA-256 **`3779a35ab9c8f2732a128105fce50c5eb28534325256bef676b54f0105b6d371`**, are the preservation baseline for this additive section.

Additional targeted verification, Python **3.12.12**:

| Verification lane | Executed command or scope | Result and meaning |
|---|---|---|
| Core mechanics | `rtk proxy env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 uv run --python 3.12 --extra dev python -m pytest tests/test_token_economy.py tests/test_phase42_toon_skeleton.py tests/test_phase44_context_pack_cache.py -q` | **20 passed**. Existing helper tests do not establish production wiring or total savings. |
| Project/memory telemetry | `rtk env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_project_token_usage.py tests/test_phase45_telemetry_gain.py tests/test_memory_efficiency.py -q` | **18 passed**. Includes synthetic ledger fixtures; passing does not validate misleading metric semantics. |
| Dashboard token view | Three selected tests in `tests/test_dashboard_memory_tokens.py` | **3 passed, 33 deselected**. Display contract coverage only; no real provider/agent consumption observed. |
| Bounded direct probes | Temporary Python source with two functions; `ContextPacker.pack(max_tokens=1)`; `CacheAligner(min_prefix_tokens=100).align_prompt("hi")` | **40-token** packed output with duplicate closing tags; **161-token** padded prefix. Temporary workspace removed; no project implementation changed. |
| CLI/MCP boundary audit | Registrations, shared executor return, renderer, scan paging/handoff source | Source inspection only; no additional native host run claimed. |

The direct probe can be reproduced in the project Python environment without touching project source:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from rush.codegraph.context_packer import ContextPacker
from rush.token_economy.cache_aligner import CacheAligner

with TemporaryDirectory() as directory:
    source = Path(directory) / "x.py"
    source.write_text("def a():\n    return 1\n\ndef b():\n    return 2\n")
    packed = ContextPacker(Path(directory)).pack(source, max_tokens=1)
    print(packed["tokens"], repr(packed["packed_text"]))
print(CacheAligner(min_prefix_tokens=100).align_prompt("hi")["system"]["aligned_tokens"])
```

No paid provider comparison, external resource installation, full cross-platform client matrix, live compaction lifecycle, or real multi-agent savings benchmark was executed. Primary-source research establishes available mechanisms and constraints; it does not establish performance in Rush. The later development plan must retain these acceptance lanes and the earlier memory review's unresolved functionality requirements.

## 9. Live acceptance incident: Rush enabled, but not adopted during its own memory review

### 9.1 User outcome and observed failure

The user reported that Rush MCP had been active in this session and project throughout the day's discussion. The expected outcome is reasonable and central to the product: the coding agent should discover Rush, establish its current project memory access, recall relevant context, use Rush where appropriate, and maintain permitted development memory without repeated user reminders.

**This review session failed that end-to-end adoption outcome.** Before the user's explicit challenge, the reviewing agent used Graft, context-mode, shell/source inspection, and its separately supplied Codex memory without establishing Rush's live tools or current Rush memory. The agent should have performed that check at the start. External tool use is not inherently wrong, but it cannot be presented as successful integration of Rush itself. A document about Rush memory is a particularly strong real-world case for detecting this failure.

The incident indicates a material product integration/adoption gap. It does **not** establish that all Rush implementations are nonfunctional: a fresh direct protocol test successfully started the configured server and listed its tools. The distinction matters for the fix: transport availability, model-visible tools, authorized memory scope, useful recall, and ongoing agent use need separate acceptance evidence. “Enabled” alone is insufficient.

### 9.2 Live evidence collected after the challenge

Tests ran September 25, 2026, approximately 17:42–17:43 America/Los_Angeles. They used the **installed configured executable**, not an assumption that the frozen source checkout represented the running installation. This is an additional runtime evidence lane after §8.9's source/helper verification.

| Layer | Observed result | What this establishes |
|---|---|---|
| Configured client entry | `codex mcp list --json`, filtered to Rush, returned `name="rush"`, `enabled=true`, transport `stdio`, command `/Users/jamesdsizemore/Library/Application Support/Rush/bin/rush`, args `["mcp", "serve"]`, auth status `unsupported`. | Rush is enabled in inspected Codex configuration. `unsupported` is the CLI's auth-status field, not proof of transport failure. This point-in-time check does not independently reconstruct the entire day's connection history. |
| This assistant's tool exposure | Complete available-tool metadata search found no Rush callable and no tool-search callable. MCP resource/template discovery returned no Rush resource/template. | A model-facing exposure gap exists in this current tool surface. Absence of resources alone would not prove absence of a tool server. Exact cause of missing callable exposure—host loading, bridge behavior, configuration scope, or another integration failure—was not diagnosed. |
| Configured server protocol | A fresh stdio MCP client launched the configured executable, completed `initialize`, and completed `tools/list`: server name `rush`, reported version `1.28.1`, **79 tools**, including `rush_memory`. | Server initialization and tool discovery work in this fresh connection. It does not prove that the original desktop task had received these tools or consumed the initialization instructions. |
| Public memory list | Called `rush_memory` with this project path and `operation="list"`. ToolResult: `status="error"`, summary **`memory list requires subject and query.`** MCP wrapper `isError=false`. | The seemingly natural memory inventory operation has additional undisclosed-to-the-user prerequisites; its schema accepts the request, then the implementation rejects it. No memory was returned. |
| Public current-context query | Called `rush_memory` with project path, `operation="ask"`, `subject="active_context"`, and query `memory system review cross agent continuation token reduction`. ToolResult: `status="skipped"`, summary **`memory ask requires a non-empty session_allowlist (fail-closed, no default cross-session access).`** MCP wrapper `isError=false`. | The agent lacks an established authorized session allowlist and cannot retrieve current development memory through this call. Scope protection is appropriate; the missing usable scope-bootstrap path is the product problem. |

The calls used default false write/network/build flags. No client configuration was changed, no consent or session allowlist was fabricated, and no memory write/promotion was requested. The fresh stdio connection was closed after testing. Current Rush memory was **not retrieved**; this report must not imply otherwise. The earlier Codex memory guidance is a separate system, not proof of Rush recall.

### 9.3 Source-backed causes and remaining uncertainty

**AD01 — P1: configured/connected state is not verified agent adoption.** `build_server_instructions` advertises names, maturity, and generic result shape (`src/rush/mcp.py:22–38`). Registration writes the command and arguments (`src/rush/integrations/agents.py:158–162,590–665`). Neither supplies a project-specific memory startup packet or an explicit recall/use/write lifecycle. `agent_readiness.any_connected` is based on registration (`src/rush/integrations/agents.py:895–908`), not an observed model call. The live server's initialization instructions enumerate tools but do not provide an authorized current memory scope or a startup recall sequence. Missing model-facing exposure remains an additional host-boundary issue; fixing descriptions alone does not resolve it.

**AD02 — P1: memory authorization exists without a discoverable continuation bootstrap.** `AgentConnectionTool.connect` requires session identity, grants, and consent/acknowledgement (`src/rush/tools/agent_connection.py:47–165`). Memory initialization creates a disconnected entry (`src/rush/integrations/agents.py:789–833`), acknowledgement flips connected state (`:870–893`), and recall requires subject/query/allowlist (`src/rush/cli.py:2578–2594`). This session had no verified route from the enabled MCP entry to a supplied, authorized scope. A new agent cannot safely guess prior session IDs. Default-deny scope behavior should remain; Rush needs an explicit host-to-project/session authorization and continuation handshake.

**AD03 — P1: ongoing learning is opt-in tool observation, not continuous agent memory.** `[tools.memory] record` defaults false (`src/rush/config.py:355–372`), is resolved separately (`src/rush/invocation/resolver.py:320–339`), and executor observation additionally requires cache-write permission (`src/rush/invocation/executor.py:473–485`). This captures eligible tool execution, not arbitrary user decisions, agent discoveries, corrections, or session startup context. Review-specific recall (`src/rush/tools/review.py:99–128`) is useful but not a general agent bootstrap. Phase 70 D1–D3 proposals (`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md:50–62`) are not implementation evidence.

**AD04 — P2: generic discovery guidance can misdirect recovery.** The live initialization text says skipped status means an engine is not installed, but the actual memory query was skipped because a session allowlist was missing. Installing an engine would not solve this. Likewise, the `rush_memory` schema defaults subject to null and query to an empty string even though the tested list operation requires both. Add operation-specific prerequisites, typed reasons, and the correct recovery action. Keep canonical ToolResult status handling consistent with each client's MCP error presentation; `isError=false` must not be interpreted as successful memory retrieval when embedded status is error/skipped.

### 9.4 Required product behavior and acceptance gate

The plan needs a first-class **agent adoption and memory activation gate**, tied to TC05/TC09/TC12 and the earlier memory requirements. It must observe behavior from the receiving agent, rather than infer it from installation/configuration.

1. **Discover and diagnose.** A fresh supported coding-agent session identifies Rush for the project without a user reminder. Rush/host integration verifies registered → server initialized → required tool callable. If the model-facing tool is absent, status identifies that boundary and its recovery instead of claiming memory is active. Provide a supported CLI route where appropriate, while reporting it as CLI use rather than MCP integration success.
2. **Establish scope and recall.** Resolve canonical project/worktree and active agent/session identity, apply existing user-authorized scope and consent, and return a bounded current-context packet or an honest empty/blocked state with an actionable reason. Expose allowed continuation selection without leaking unauthorized session contents. No default cross-session access, fabricated session ID, or permission bypass.
3. **Demonstrate use and permitted learning.** The agent uses an applicable Rush operation and cites at least one relevant current memory when such memory exists. Capture actual delivered evidence and observable task application. When user consent/grants permit recording, persist scoped decisions, corrections, or learned patterns with provenance; otherwise show read-only state. An explicit user decision must not require the user to separately retype it into a memory UI.
4. **Continue in another agent.** A second supported coding-agent host obtains the authorized continuation and resumes the task from current repository state, including active constraints, failed approaches, UI/architecture preferences, and outstanding validation. Test a stale code anchor, an empty store, and unavailable model tools. Verify successful scoped write/read across hosts when permitted, rather than stopping at registration success.
5. **Expose truthful state and cost.** User and agent can distinguish configured, reachable, callable, scoped, recalled, applied, writable/read-only, and last persisted. Show the selected memory/provenance and current failure boundary. Count bootstrap, retrieval, expansion, and writes in token/cost evaluation; demonstrate that integration reduces repeated discovery and correction work.

Acceptance must include this exact class of task: ask a fresh agent to assess or develop Rush with existing project memory and do not separately remind it that Rush exists. Pass requires observable discovery, scoped recall/use, permitted persistence, and successful subsequent continuation. A merely enabled server, successful handshake, or manually forced memory call does not pass that end-to-end test. This is a blocking product outcome for the user's intended dynamic cross-agent memory system, alongside the underlying correctness findings—not an optional onboarding polish item.

## 10. Executable remediation plan: make agents discover, activate, use, and continue Rush memory

### 10.1 Goal, scope, and implementation authority

**Goal:** after the user completes a supported, consented Rush setup once, a fresh coding-agent session in that project discovers Rush without a reminder, obtains authorized current memory, applies relevant context, persists permitted learning, and allows another supported agent to continue the work. Existing installations must receive the same capability through a reversible upgrade; reconnecting must not erase earlier activity.

This is the concrete remediation plan for §9, not another finding or a claim of implementation. It adds executable work to the existing Phase 70 plan and preserves the broader memory/token proposals in §§6–8. Writing this plan does not install integrations, edit user instruction files, activate capture, or implement application changes. All tasks below are **not started**. User-owned Phase 70/71 files remain unchanged.

Binding inputs: repository `AGENTS.md`; `docs/templates/task-block-template.md`; `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`, especially T1–T7, T18–T24, T26, and T29; this report's F01–F24, TR01–TR11, and AD01–AD04. Implementation starts from reviewed HEAD `ddc064117e971b48e29100004052e876e456faf2`, with a fresh dirty-state inventory. Installed runtime identity must be recorded independently: the MCP handshake's reported server version is not sufficient identification of the Rush package or executable build.

**Scope:** actual host exposure and repair diagnostics; safe memory reads; project/session authorization; session bootstrap; task-sensitive recall; consented capture; real cross-agent handoff; visible/searchable activation and memory state; behavior and token evidence. Integrate shared CLI/MCP/TUI/dashboard paths. Agent guidance is a delivery mechanism, not a replacement memory store.

**Non-goals for this remediation:** replacing the typed store, inventing another agent runtime, training model weights, making every token proposal a prerequisite for first activation, or claiming external host defects can be repaired inside Rush. No Git hooks, automatic trust approval, silent global configuration edits, permission escalation, or release/publish operation. These boundaries do not remove any broader requested memory capability from the later full development plan.

### 10.2 Concrete agent and user interaction contract

The new behavior must have one coherent path. Names in this subsection are **proposed interfaces**, not current commands to run:

1. **One setup/upgrade choice establishes policy.** Existing `rush agent connect`/setup paths preview exact registration, project guidance, and supported native resources. User chooses permitted project-memory read scope and whether agent observations may be written. Guidance installation, host trust, read authorization, and write consent are separate recorded facts. Declining writes creates a useful read-only integration. Existing consent is reused until changed or revoked; agents do not ask permission every turn.
2. **Fresh agent calls `rush_memory` with proposed `operation="bootstrap"`.** Request names canonical project, host/session identity if available, task text, and context budget. It does not require the model to guess `session_allowlist`. Shared Rush logic derives access from stored authorization or a valid continuation capability. An explicit CLI counterpart, `rush memory bootstrap`, calls the same logic for shell-based adapters. It is reported as CLI use when MCP exposure is unavailable.
3. **Bootstrap returns a bounded useful result or a precise block.** Result contains project/worktree identity, server-issued session binding, read/write state, selected memory IDs/revisions and content, provenance/freshness, budget/omissions, and exact next operation. Missing read authorization returns `scope_required` with the setup action; no authorized memory returns `empty`; stale-only results return `stale_only`; unavailable tools are a host-exposure issue. No fake populated context or guessed authorization.
4. **Agent refreshes and records at meaningful boundaries.** Task start, a new subtask, relevant source changes, a contradictory memory, failure feedback, and continuation trigger selective recall/refresh. User decisions, corrections, and verified outcomes generate scoped typed writes only within prior consent. Task checkpoints capture goal, constraints, changes, validation, failures, and next work. Do not serialize every conversation turn into permanent instructions.
5. **Switching agents uses the same store and an authorized handoff.** Receiver verifies project/revision and granted evidence, acknowledges actual recall, then proceeds. Handoff status reflects receiver actions, not process exit zero. User can see current access state, last recall/write, selected records, and any failed boundary, and can search/edit/revoke memory through existing app surfaces.

Bootstrap response fields to implement in the existing versioned result envelope: `schema_version`, `project_id`, `worktree_id`, `session_binding`, `access` (`read`/`write` with reason), `activation_state`, `memory_revision`, `items` (ID/version/subject/content/provenance/freshness), `budget` (encoding, delivered count, omitted count), `continuation`, and `next_action`. Use existing identity/version/cursor/artifact types where they exist. The session binding is a server-issued reference, scoped to project and the local authorization policy; it is not an authentication credential. Do not put a reusable bearer credential into model-visible prose or logs.

**Authorization decision for ordinary local MCP and CLI:** setup grants the local OS user's Rush installation access to a selected canonical project/worktree and explicit approved memory sources/operations. It does **not** cryptographically authenticate Claude versus Codex or isolate mutually hostile processes running as that same OS user. Native stdio clients and the CLI use that same local principal and stored policy; host/session strings provide attribution only. Every call resolves the canonical root, checks policy revision/revocation and source/owner access, and enforces read/write grants independently of those strings. No grant is inferred from repository instructions, executable presence, or an agent's self-description. Record this trust boundary in setup's consent preview. Separate users or remote receivers need the existing explicit capability path; do not silently reinterpret them as local-user access.

**Binding lifecycle:** after an authorized local bootstrap, Rush issues a non-secret random binding ID referencing canonical project/worktree, local grant revision, source allowlist, and access mode in existing connection state. Subsequent native or CLI invocations revalidate local policy and the binding; the binding cannot widen access and never replaces the policy check. Reconnect is idempotent for the same live binding. Revocation, a source-grant change, or project relink invalidates earlier bindings. A forged or foreign-project binding is rejected; a supplied host name cannot create a grant. Authorized local agents can intentionally share project memory under that policy. Capability-based cross-agent delivery remains separately bounded as specified in AP06.

Compatibility: preserve explicit source allowlists and all existing valid memory operations. Add bootstrap to the shared operation metadata, schemas, CLI, and dispatch tests together. Legacy request forms keep their contract. Ordinary/bootstrap access must not broaden restricted `--memory-session` receiver capabilities. A compact list may have an optional query under its existing contract; fix the actual operation branch, not the false generalization that every list requires a query.

### 10.3 Dependencies, ownership, and allowed implementation files

Implement in four waves: **AP01 + AP02** can run independently; **AP03 → AP04 → AP05** follow in order; **AP06 → AP07** follow sequentially because canonical memory/receipt files overlap; **AP08** validates the integrated result. AP07 may consume read-only interface contracts earlier but must not invent competing activation state. One integration owner controls shared `cli.py`, `mcp.py`, `tools/memory.py`, and memory-store changes; concurrent agents must not edit them.

| Task / owner | Literal implementation files and existing starting points | Dependency |
|---|---|---|
| AP01 / memory integrity owner | `src/rush/memory/store.py`, `retrieval.py`, `relations.py`, `consolidation.py`; existing `search_candidates`, `recall_page`, expansion, update, `summary_is_current` | None; blocks automatic delivery of unsafe memory |
| AP02 / host diagnostics owner | `src/rush/integrations/agents.py` (`_discover_one`, `discover_agents`, `probe_agent_connection`, `agent_readiness`); `src/rush/tools/agent_connection.py`; `src/rush/tools/install.py` | None; source and installed-runtime identity remain distinct |
| AP03 / memory activation owner | `src/rush/integrations/agents.py` (`initialize_agent_memory`, `acknowledge_agent_connection`); `src/rush/tools/agent_connection.py`; `src/rush/tools/memory.py` (`MemoryTool.run`); `src/rush/cli.py`; `src/rush/mcp_support/tool_registry.py`; Phase 70's proposed `src/rush/mcp_support/request_models.py` | AP01/AP02; reuse Phase 70 T6 validation contract |
| AP04 / host integration owner | `src/rush/integrations/agents.py`, `src/rush/tools/install.py`, `src/rush/tools/agent_connection.py`, `src/rush/mcp.py` (`build_server_instructions`); Phase 70's proposed `src/rush/integrations/agent_assets/skills/rush/SKILL.md` and finite native asset matrix in its §8.1 | AP03; reuse Phase 70 T1–T5/T26 packaging and rollback |
| AP05 / capture and recall integration owner | `src/rush/invocation/executor.py`, `src/rush/invocation/resolver.py`, `src/rush/config.py`, `src/rush/tools/memory.py`, `src/rush/tools/review.py`; `src/rush/integrations/agents.py`; Phase 70's proposed `src/rush/integrations/agent_hooks.py` only for documented, supported native lifecycle events | AP04; same permission checks for explicit and adapter calls |
| AP06 / continuation owner | `src/rush/tools/memory.py` (`_handoff`, receive paths), `src/rush/memory/handoff.py`, `src/rush/memory/transport.py`, `src/rush/memory/store.py` (existing session/receipt persistence), `src/rush/mcp_support/tool_registry.py` (restricted receiver), `src/rush/continuity/providers.py` | AP05; no independent public dispatcher or store |
| AP07 / app visibility owner | `src/rush/dashboard/server.py`, `src/rush/dashboard/application.js`, `src/rush/tui.py`, `src/rush/cli_support/rendering.py`, `src/rush/workflows/projects.py`, `src/rush/token_economy/telemetry.py`; `src/rush/tools/memory.py` and `src/rush/memory/store.py` only for Phase 70 T28-D's missing canonical memory operations | AP06 and T28-D canonical operations; consumes shared grants, does not redefine them |
| AP08 / integration acceptance owner | Existing test modules listed below; new `tests/test_memory_activation_lifecycle.py`; existing `scripts/benchmarks/memory.py` and `scripts/benchmarks/run.py` only when wiring admitted live decisions; `docs/user-guide/working-with-ai-agents.md` after routes work | AP01–AP07; frozen integrated source and installed artifacts |

All filenames abbreviated within a directory in the first row resolve under `src/rush/memory/`. Proposed Phase 70 assets remain governed by its finite file matrix; this plan does not authorize inventing additional host package layouts. New tests named below are proposed additions, not reported existing checks. Before implementation edits each named source file, read its current contents and callers; this file map assigns ownership rather than freezing stale line numbers.

### 10.4 Ordered implementation task packets

#### AP01 — Make automatically delivered memory trustworthy and recoverable

**Required behavior:** apply one shared active visibility/integrity/freshness policy before ranking, relation traversal, summary use, pagination, and expansion. Archived, expired, tampered, revoked, or stale authoritative records cannot re-enter through another read route. Updating promoted content must atomically invalidate/revalidate authority. Page limits preserve a cursor to every remaining eligible result. Expansion carries verified version/hash and Unicode-safe reconstruction with explicit compatibility for existing consumers.

**Deliverables:** AP01 source files; extend `tests/test_memory_retrieval.py`, `tests/test_memory_versions.py`, `tests/test_memory_relations.py`, and `tests/test_memory_consolidation.py`. Concrete assertions: archive then expand is denied; expiry between pages removes future access; edited signed record never returns as valid `STATED`; three rows at limit two require a second page; a changed/expired summary member invalidates the summary; multibyte reconstruction matches original bytes and digest. Close F01–F03, F05–F07, and F24 for paths used by bootstrap.

**Constraints:** no bypass based on “trusted agent” labels; no authorization widening; no automatic promotion or maintenance enablement. F04/F08 remain separately required before enabling those affected capabilities. Read-only discovery of a missing store must not initialize durable memory as a side effect.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_retrieval.py tests/test_memory_versions.py tests/test_memory_relations.py tests/test_memory_consolidation.py -q`.

**Completion:** exact negative cases fail on baseline and pass after the shared fix; all read routes used by AP03 enforce the same policy. No “automatic recall” rollout precedes this gate.

#### AP02 — Diagnose the actual host boundary and stop false connected states

**Required behavior:** validate executable, full argv/profile, selected project/configuration scope, and installed artifact identity. Expose independent states for configured, fresh-server initialize/list success, actual-host tool-call observed, scoped recall, and write permission. Existing `acknowledge=True` remains consent/acknowledgement only. It must not synthesize evidence of host exposure or memory use. Detect an installed supported CLI even without an existing config file; reconnect preserves earlier observations.

**Deliverables:** AP02 files; extend `tests/test_agent_connection.py`, `tests/test_install_memory_activation.py`; use Phase 70 `tests/test_phase70_adoption.py` for packaged registration cases. Add a bounded diagnostic probe through existing `rush agent doctor`, not a separate diagnostic framework. It must distinguish wrong argv, wrong executable, startup failure, missing required tool, host trust/reload required when evidenced, unverified exposure, and scope-required memory errors. Native host observation can supply an inventory/call receipt; when unavailable, return `host_exposure_unverified` and the supported host-specific inspection/reload action. Never infer the cause solely from a fresh server handshake.

**Concrete assertions:** argv `not mcp serve` cannot be registered-ready; server exposes memory but no actual-host receipt yields exposure-unverified; embedded ToolResult error/skipped overrides any misleading interpretation of MCP `isError=false`; empty config plus installed host is discoverable; reconnect preserves last confirmed recall/write. A fake host acknowledgement cannot grant memory scope. Probe timeout is reported without blocking ordinary work indefinitely.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_agent_connection.py tests/test_install_memory_activation.py tests/test_phase70_adoption.py -q` after adding the Phase 70 test module if absent.

**Completion:** the §9 mismatch is expressible and actionable using the real installed executable and actual client evidence. Fix a demonstrated Rush registration/packaging defect in the owned files; if the defect is external host exposure, retain that exact external blocker and its native recovery action. Neither the task nor release may claim the current desktop integration repaired without a subsequent successful call from that desktop session.

#### AP03 — Implement authorized bootstrap and useful first recall

**Required behavior:** implement §10.2's bootstrap through shared business logic and its explicit local-user/project authorization boundary. Resolve canonical project/worktree and stored grants; host/session strings are attribution, not authenticated principals. Consent granted in setup is reusable; no manual session-ID guessing. Existing explicit allowlists remain supported and validated. With valid access, return relevant current records and stable expansion references under the complete-envelope budget. Tiny budgets return an actionable minimum-budget failure. An empty store returns empty, not a fabricated context.

**Deliverables:** AP03 files; add `tests/test_memory_activation_lifecycle.py` and extend `tests/test_memory_public_contract.py`, `tests/test_memory_operation_metadata.py`, `tests/test_agent_connection.py`, `tests/test_mcp.py`. Implement `bootstrap` metadata/schema/dispatch and `rush memory bootstrap` together. Use existing connection policy/state to persist explicit grants with revision checks; use typed memory storage for context, not `agent_memory.json` bookkeeping as a competing memory authority. Return access-state reasons and a next action without exposing private session inventories.

**Concrete assertions:** correct project and valid grant return known IDs/versions; wrong project/worktree, forged binding, revoked grant, and unapproved prior session yield no content; missing permission identifies the relevant setup choice; retries are idempotent; consented current-project read does not expose another project; user-stated constraints retain provenance. MCP and CLI produce equivalent selected evidence from identical scope/task/budget. Request validation and tool schema agree on missing fields and accepted types.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_activation_lifecycle.py tests/test_memory_public_contract.py tests/test_memory_operation_metadata.py tests/test_agent_connection.py tests/test_mcp.py -q`.

**Completion:** a newly authorized agent obtains real current project memory without supplying guessed legacy source/session identifiers. Authorization revocation takes effect on subsequent recall and expansion. This closes the missing scope/bootstrap outcome of AD02; it does not claim the receiving model already applied the result.

#### AP04 — Make fresh hosts actually discover and call bootstrap

**Required behavior:** ship one canonical small usage contract in supported native assets and consented project guidance. It tells an agent when to use Rush, how to call bootstrap, what read-only/blocked/empty means, how to refresh relevant evidence, and how to record only permitted outcomes. Initialization descriptions match executable status semantics, including `skipped` for missing authorization. Existing installations receive a previewed, idempotent asset/guidance upgrade even when registration already exists.

**Deliverables:** AP04 files and Phase 70 T1–T5/T26 asset/test matrix. Add concrete bootstrap examples to the installed skill; make every example executable against the emitted schema. Preserve the existing core/full compatibility contract by extending the existing `rush_memory` operation rather than adding an unplanned bootstrap tool. Resolve instruction-file ownership with digests/markers and rollback, preserving concurrent user edits. Package resources must work outside the checkout.

**Host contract:** for Claude Code, Codex, and Cursor, implement the native supported loading routes already required by Phase 70 and verify actual versions. For Antigravity/`agy` and Z.AI/`zai`, record the actual host product/executable/version and supported extension/CLI/MCP mechanism before choosing adapter details; provider name alone is not a host protocol. These remain required coverage lanes, not presumed supported through generic ACP. Use the same bootstrap contract when their verified mechanism is available; a specific unavailable host capability remains an explicit blocker to that host's acceptance. Do not invent lifecycle events or install Git hooks.

**Concrete assertions:** fresh and existing installations load identical canonical instructions; user decline causes no instruction/config write; repeated upgrade does not duplicate servers or blocks; conflicting edits survive; restricted receiver cannot be widened; native package load alone does not enable writes/capture. In each real host, a normal project task with no mention of Rush results in a genuine bootstrap call, or fails that host's adoption gate.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase70_adoption.py tests/test_install_memory_activation.py tests/test_agent_connection.py tests/test_mcp.py -q`, plus Phase 70's installed native-package checks and actual host calls. Fixtures do not satisfy the last condition.

**Completion:** observed automatic discovery and bootstrap in the supported real host, with correct project scope. MCP initialization instructions alone, a packaged skill alone, or CLI fallback alone does not establish native MCP adoption. User-facing instructions are updated only for routes that pass.

#### AP05 — Connect memory to ongoing work, corrections, and permitted learning

**Required behavior:** trigger task-sensitive recall at task/subtask boundaries and refresh stale evidence after relevant changes. Integrate authorized user/agent records into review instead of limiting recall to migration sources. Record explicit user decisions/corrections and verified agent outcomes through existing typed writes. Capture mode, failures, denial, and last successful write are visible. Distinguish user-stated preferences, inferred patterns, candidate skills, and observed facts; an agent's inference cannot become a user rule automatically.

**Deliverables:** AP05 files; extend `tests/test_memory_observations.py`, `tests/test_phase61_memory_tool.py`, and `tests/test_memory_activation_lifecycle.py`. Reuse existing invocation observation for Rush tool outcomes. Add supported native lifecycle adapters only where their event/prompt delivery is documented and tested; otherwise canonical guidance calls explicit checkpoint/write at meaningful boundaries. This fallback is labeled and tested as agent-cooperative capture, not claimed automatic transcript observation. No writes if capture consent or grant is absent.

**Concrete assertions:** a relevant user-written architecture/UI preference appears in authorized review evidence with exact ID; unrelated preference does not; user correction supersedes the appropriate earlier item while retaining provenance; failed repair informs a subsequent decision without being mislabeled success; changed source anchor triggers refresh; duplicated event IDs do not duplicate observations; capture failure is visible and does not silently erase the successful coding action; write revocation prevents future persistence. Checkpoint must include unresolved failures and required validation, not only achievements.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_observations.py tests/test_phase61_memory_tool.py tests/test_memory_activation_lifecycle.py -q` and actual host milestone/correction runs in AP08.

**Completion:** the agent uses and contributes meaningful typed memory during ordinary work, with current scope and consent, rather than producing only connection bookkeeping. Close F11/F12/F16/F17 for the implemented lifecycle. Broader workflow mining, skill admission, and adaptive ranking in §6/TC08/TC13 remain separate full-plan tasks, not falsely declared complete here.

#### AP06 — Complete public handoff and verify receiving-agent continuation

**Required behavior:** wire public handoff dispatch/status to the existing permitted transport instead of unconditional `E_UNAVAILABLE`. Keep `prepare_handoff` capability bounds, source allowlists, expiration/revocation, source hashes, and restricted receiver. Pass current goal, authoritative constraints, decisions, code/test references, failed attempts, unresolved work, and next validation in a bounded envelope. Restore only authorized evidence needed by the receiver. Track prepared, dispatched, receiver-recalled, and receiver-continued separately; exit zero is not recall or continuation.

**Deliverables:** AP06 files; extend `tests/test_memory_handoff.py`, `tests/test_phase61_handoff.py`, `tests/test_memory_activation_lifecycle.py`, and `tests/test_mcp.py`. Receiver calls produce a scoped receipt through existing handoff state; do not add an unrequested network service. Preserve current grant/transport ownership and cancellation behavior. CLI provider continuation must retain the same memory contract as MCP continuation.

**Recipient and secret-delivery contract:** public dispatch names a configured recipient adapter ID and canonical project, plus selected permitted artifact IDs/source grants, budget, and invocation ID. Resolve the recipient ID to the consented executable/SDK or configured ACP argv; never accept arbitrary shell from the model. `MemoryTool._handoff` calls `rush.memory.transport.dispatch_handoff`, which selects the supported tier and uses `prepare_handoff`/`receive_handoff`. Preserve its current restricted bridge: `rush mcp serve --memory-session <id>`, with `RUSH_MEMORY_CAPABILITY` supplied only to the owned receiver subprocess environment. The capability's hash is persisted, not its raw value; keep it out of argv, prompts, logs, general telemetry, and sibling subprocesses. Dedicated-file tier remains an explicit unsupported memory transport; it cannot silently become a successful handoff. Apply existing network/transport grants. Revocation or expiration rejects future receiver calls.

**Receipt and state contract:** persist stage receipts through existing handoff-session/store machinery, keyed by handoff ID, invocation ID, receiver connection nonce, source scope/revision, artifact IDs/versions, and timestamp. `prepared` means the bounded session exists; `dispatched` means the owned adapter accepted launch/delivery; `receiver_recalled` requires a successful capability-checked call arriving through the restricted receiver connection. Sender-side preparation currently calls `receive_handoff` to obtain an initial delta: that local call must **not** generate a receiver-recalled receipt. The restricted MCP wrapper records the connection-bound read receipt server-side after successful validation. A model-provided text receipt, copied nonce, SDK return, or process exit cannot produce that transition. Replays are idempotent and never widen scope.

`receiver_checkpointed` requires a permitted receiver write containing current goal, accepted constraints, evidence IDs, and next work; treat its assertions as agent-reported. `continuation_verified` requires an independently observed task-specific result attached by the shared execution/acceptance path, such as a source change plus the required check result for the named acceptance task. If no independent verifier exists for an arbitrary task, stop at checkpointed/unverified—do not invent verification. Error, cancelled, expired, and revoked are explicit states. Status derives these receipts and distinguishes claimed work from observed work. Extend `tests/test_phase61_handoff.py` with `test_prepare_delta_is_not_receiver_recall`, `test_forged_receipt_cannot_advance_state`, `test_receiver_read_requires_owned_channel`, and `test_checkpoint_is_not_verified_continuation`.

**Concrete assertions:** forged/revoked/expired/foreign-worktree capability fails; legitimate duplicate delivery/read is idempotent, does not widen scope, and does not repeat state effects; stale source prompts revalidation; receiver can reconstruct authorized content and verify digest; sender cancellation is visible; unavailable transport returns exact recovery without claiming dispatch; receiver read without task continuation is not complete; reconnect does not erase handoff status. Two real different hosts retrieve the same permitted project state and continue without restating the project history.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_handoff.py tests/test_phase61_handoff.py tests/test_memory_activation_lifecycle.py tests/test_mcp.py -q`, followed by AP08's real transfer cases.

**Completion:** a public supported handoff route produces receiver recall and observable correct continuation. SDK-only success, copied text, or generic ACP availability does not close F13/F14/A01.

#### AP07 — Show usable activation, memory, and recovery across app surfaces

**Required behavior:** CLI/TUI/dashboard consume the same access and activity receipts. Show configured/reachable/callable/scoped/last recalled/last written as separate facts, with read-only and blocked states. Show which memories were selected, why, their freshness and provenance, and how to inspect/search/correct them. The connection badge must not turn green merely because configuration exists. Failed bootstrap offers the correct setup/scope/host action, not “install an engine.”

**Deliverables:** AP07 files; extend `tests/test_dashboard_memory_tokens.py`; add `tests/test_memory_activation_ui.py` for shared status projection and supported TUI/dashboard routes. Reconcile F18/F19 and Phase 70 T19–T24/T27–T28 with Phase 71's dashboard scope. Shared backend status and useful CLI/TUI behavior are part of this remediation; dashboard acceptance is a real dependency, not permission to omit the requested user-searchable memory surface.

**Canonical-operation dependency and ownership:** Phase 70 T28-D owns full terminal memory administration, including missing shared operations in `src/rush/tools/memory.py` and `src/rush/memory/store.py`. Before AP07 UI acceptance, its canonical query/subject selection/expand/edit/delete/archive/history/promotion routes must exist and pass their ownership, version, consent, and recovery contracts. If T28-D is implemented, reuse it. If it is not, execute its required canonical work under this shared-file owner before wiring UI controls; do not create frontend-only mutations or call the missing operation complete. AP07 follows AP06 to avoid concurrent store/tool edits. Phase 71 owns the corresponding dashboard implementation/acceptance; AP07 remains incomplete for the dashboard until those live user-memory routes pass. Projection-only tests cannot close F18/F19 or full memory administration.

**Concrete assertions:** registered-only never renders memory-active; stale recall is labeled; read-only state prevents write controls from implying permission; every supported memory subject is selectable; search/expansion uses exact IDs and authorized scope; revoked access disappears on refresh; generic human rendering does not discard useful raw activation results. Telemetry distinguishes returned-to-client from inserted-into-model context and actual provider usage. A cache fill is not a consumed memory hit.

**Checks to run:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_activation_ui.py tests/test_dashboard_memory_tokens.py -q`; complete existing Phase 70/71 terminal/browser acceptance on live seeded records, including empty, denied, stale, partial, and error states. No screenshots are required by this plan.

**Completion:** user and agent can diagnose, use, search, and recover memory through the applicable interface without reading raw JSON or inferring meaning from an ambiguous “connected” label.

#### AP08 — Prove adoption and continuation in real agents before declaring success

**Required behavior:** run the acceptance matrix below on frozen integrated source and packaged artifacts. Use actual agent decisions; repair the existing benchmark's scripted-success and post-decision-budget defects before using its scores. Do not build a parallel benchmark framework. Preserve correctness and user requirements while measuring total bootstrap/recall/write/expansion/agent costs.

**Deliverables:** lifecycle test module and existing benchmark integration where applicable; a durable `docs/reports/memory-agent-adoption-acceptance.md` populated with exact revision, executable digest/package version, host/model/version, scopes/consent, redacted actual calls, memory IDs/revisions, outcomes, costs/unknowns, and per-cell pass/fail/blocker. Update `docs/user-guide/working-with-ai-agents.md` only after executable routes pass. Never include private memory content or bearer capabilities in public-facing receipts.

**Checks to run:** task-specific commands from AP01–AP07, then `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q`; `rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts`; `rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts`; installed-distribution/native-host checks required by Phase 70. Stop on byte drift, resolve the issue, refreeze, and rerun only affected checks plus unresolved acceptance. Do not repeat passing unchanged checks without cause.

**Completion:** all claimed host capabilities have actual evidence, required cross-agent pairs pass, and user-visible search/state works. Failed/blocked host lanes remain named and open. Unit tests or one successful host do not authorize a universal “works across agents” claim.

### 10.5 Required acceptance matrix and exact success criteria

| Scenario | Required setup/action | Pass condition |
|---|---|---|
| This incident, reproduced | Existing enabled Rush; fresh real agent asked to review this memory system without mentioning Rush in the task prompt | Agent discovers Rush from installed integration, bootstraps correct project, retrieves relevant permitted memory, uses an applicable Rush operation, and cites actual memory evidence. Direct coordinator forcing of the call is not a pass. |
| Fresh installation and existing upgrade | Supported installed host with empty config; separately an existing manual Rush registration with prior observations | Consented setup supplies usable guidance and one registration; upgrade preserves unrelated configuration and prior observations; actual host calls Rush after documented activation/reload. |
| Read-only and denied access | Read-only consent, no consent, revoked grant, wrong worktree, and forged session binding | Useful read-only operation when authorized; exact blocked state otherwise; zero unauthorized content or writes; no repeated permission prompt for unchanged approved access. |
| Current memory lifecycle | User specifies a UI system and architecture constraint, corrects an agent assumption, then agent completes/validates a change | Exact user decisions and correction are preserved with provenance; subsequent relevant task retrieves them; inferred preference remains distinguishable; last successful write and any capture failure are visible. |
| Agent switch and code drift | Claude Code→Codex and Codex→Claude Code; one additional independently implemented requested host pair; modify a referenced symbol before receiving | Receiver obtains permitted current context, detects stale anchor, revalidates it, and continues required work without repeating history or reviving failed approaches. Each supported host also passes its individual bootstrap lane. |
| User control and failure recovery | Search/edit/revoke memory in applicable UI; missing store, expired artifact, server unreachable, missing model-callable tool | Correct shared state and recovery action; no fake memory, no blanket engine-install advice, no concealed loss, and no active badge based only on configuration. |
| Token/correctness comparison | Same task/revision/model with competent normal workflow versus integrated Rush; cold and warm runs | Correct task outcome and requirements in both arms; full request/expansion/capture costs counted once; no savings percentage from an invented whole-repository baseline; negative/unknown savings retained. |

Claude Code, Codex, and Cursor retain Phase 70's existing required native coverage. Antigravity/`agy` and Z.AI/`zai` remain explicit requested implementation/acceptance lanes; obtain exact client identity and capabilities rather than equating a model/provider label with a client. A host lacking a necessary native lifecycle mechanism may support a tested cooperative/CLI mode, but that does not satisfy a claim of automatic native MCP lifecycle support. Do not silently delete the lane or substitute another product.

### 10.6 Stop conditions, recovery, risks, and reconciliation

**Stop conditions:** unauthorized or cross-project memory exposure; corrupted/inaccurate authority; hidden memory writes; host instructions overwriting user edits; missing callable exposure misreported as active; fabricated provider usage; public handoff accepting exit zero as success; changed subject bytes during verification. Resolve the corresponding task before proceeding to an acceptance claim. External host trust/login/reload limits are reported with the exact missing step and observable evidence; they are not converted into a pass.

**Recovery:** preserve prior working registration until replacement succeeds. Use Phase 70's owned-resource digests and conditional rollback so concurrent user edits survive. Disable/disconnect revokes scoped activation and future capture without deleting user memory. Grant revocation invalidates subsequent recall/expansion/handoff; expired snapshots remain explicit missing evidence. Keep existing explicit CLI/MCP routes compatible during migration. No cleanup of user memory or configuration is implicit in this plan.

**Principal risks:** MCP alone cannot force a host to expose tools or a model to call them; instructions alone cannot observe arbitrary host events; stored identity strings alone cannot authorize scope; broad automatic recall can amplify existing trust/staleness bugs; excessive bootstrap/skill text can increase token use. AP02/AP04 establish real host control; AP01/AP03 protect evidence and scope; AP05/AP06 establish capture and continuation; AP07/AP08 expose and test the result.

| Existing scope / finding | Concrete closure work | Evidence required before closure |
|---|---|---|
| AD01, F09–F10; Phase 70 T1–T5/T26 | AP02/AP04 | Correct registration plus actual native tool call and automatic discovery |
| AD02; F01–F03/F05–F07/F24; Phase 70 T6/T20 | AP01/AP03 | Safe current-context bootstrap without guessed scopes, with useful bounded recall |
| AD03, F11–F12/F16–F17; Phase 70 T19/T21 | AP05 | Relevant recall, correction capture, visible permissioned writes and later reuse |
| F13–F14/A01; cross-agent requirement | AP06/AP08 | Public handoff plus actual distinct receiver continuation and required host coverage |
| AD04, F18–F19, TR03–TR05/TR11; Phase 70 T22–T24/T27–T29 and Phase 71 | AP02/AP07/AP08 | Actionable recovery, user-searchable memory, truthful state, real task/usage evidence |

This plan adds missing memory lifecycle requirements to Phase 70; it does not approve or replace that plan, remove its CLI/TUI/packaging tasks, or declare Phase 71 implemented. Wider global-preference policy, workflow/skill intelligence, AST graph depth, and adaptive token optimization remain in §§6–8 with their original scope. Their foundational activation, delivery, correction, and continuation paths are made concrete here.

**First implementation work:** AP01's archived/expired/tampered-record regression cases and AP02's registered-but-not-host-exposed diagnostic cases can start in parallel with disjoint owners. The remediation is complete only after AP08's real-agent evidence, not when this plan or its unit tests exist.

## 11. Recommended development split: four substantial phases with narrow dependencies

### 11.1 Recommendation and comparison

**Use four substantial development phases.** Treat them as parallel product workstreams, not a four-step waterfall. Each plan owns a usable outcome, its application integration, real behavior checks, documentation, and necessary measurement. These are proposed boundaries; no release/phase numbers are assigned and Phase 70/71 are not edited by this recommendation.

Three phases would merge distinct agent-integration, learning, or token work into an oversized plan with more shared-file contention. Five or more would encourage separating UI, prerequisites, or testing into phases that other plans must wait for. Four provides clear ownership without turning each capability into a miniature phase.

| Proposed phase | Complete outcome and retained scope | Independently useful delivery |
|---|---|---|
| **A. Memory correctness and user control** | Reliable storage, authorization/visibility enforcement, trust, versioning, expiry, archive, pagination, relations, consolidation, maintenance, exact recovery, optional evaluated hybrid retrieval, personal/project/task preference policy, and usable memory search/inspection/correction across CLI/TUI/dashboard. | Users and existing permitted agents can store, find, inspect, correct, and reuse trustworthy memory through current public routes. Does not wait for new host adapters, workflow induction, or the token optimizer. |
| **B. Agent activation and cross-agent continuity** | Actual discovery and callable exposure; authorized bootstrap; consented ongoing capture and recall; truthful activation; compaction/restart continuity; public handoff and receiver verification; concurrent-agent updates and worktree-qualified continuation; all requested host coverage. | A real supported agent uses current project memory without reminders, records permitted learning, and another supported agent continues. Does not wait for advanced AST learning, every workflow feature, or all token optimizations. |
| **C. AST-grounded learning and workflow intelligence** | Production parser/symbol/relationship integration; current versus inferred architecture; UI-system and product-intent contracts tied to code; conditional failures and successful repairs; competing hypotheses; change-driven revalidation/check selection; persistent workflow learning; skill suggestions/evolution; contradiction handling and bounded rehearsal. | Agent changes its next action using grounded past evidence, applies project design/architecture requirements, and reuses or suggests an applicable workflow/skill. Exercise real existing public memory/verification routes while new host adapters develop. |
| **D. Context and token efficiency** | Real token budgets; selective packets and expansion; compact CLI/MCP output; command distillers; local result queries; delta delivery; task/subagent context allocation; provider caching/compaction integration; evaluated encodings/compression; actual usage and cost attribution; quality-preserving savings evaluation. | Existing Rush operations and provider/agent workflows deliver less irrelevant context with recoverable evidence and defensible measurements. Output shaping, provider accounting, budget repairs, and selective retrieval do not wait for all learning or host integration. |

These scopes remain substantial. Phase C is expected to contain the most experimental capability work; keep its internal task packages and evaluations explicit rather than splitting each proposed innovation into a separate development phase. Research-labeled ideas retain their desired outcomes and required experiments; unproven mechanisms are not declared implemented or quietly dropped.

### 11.2 Scope ownership and reconciliation

The following assigns primary ownership for planning. Contributions through shared interfaces remain required; primary ownership does not authorize omitting an end-to-end requirement from another phase's acceptance.

| Phase | Primary finding/capability ownership | Existing execution packets to reuse |
|---|---|---|
| A | F01–F08, F15, F18–F19, F23–F24; A02–A03; B05; E06/E19/E25; R01–R03/R05–R06/R08/R18 | AP01; AP07's canonical memory administration and user search; Phase 70 T18/T20/T28-D and relevant Phase 71 memory UI requirements |
| B | F09–F14; A01; B01–B04; E01/E13–E15; R04/R17/R20; AD01–AD04; TC05/TC09 | AP02–AP06's host/lifecycle/continuation work; AP07's activation/connection views; native Phase 70 adoption/setup requirements |
| C | F16–F17; A05; E02–E05/E07–E12/E17–E18/E20–E24; R09–R16; TC08/TC13–TC14 | AP05's meaningful evidence producers/consumers, extended by §6's full learning, workflow, skill, UI-system, and architecture requirements |
| D | F20–F22; A04; E16; R07/R19; TR01–TR11; TC01–TC04/TC06–TC07/TC10–TC12 | §8's implementation/research packages; AP07's truthful token display; repair existing evaluation mechanisms and supply common accounting contracts |

AP08 is **distributed acceptance within all four plans**, not a fifth phase or a separate final QA project. Benchmark repairs in D must be delivered as an early bounded component where another phase needs them; no plan waits for every D optimization before testing its own outcome. F23's documentation correction is coordinated by A, while each phase updates the claims it changes.

E23/E24 belong to C because their full outcome includes task-triggered current code/design references and inferred-versus-explicit architectural knowledge. A supplies the ordinary preference, authority, and correction substrate; B delivers those records to agents. This division preserves both explicit user choices and the requested dynamic application of them. User search and meaningful visibility accompany each phase's feature; they are never postponed to the end.

### 11.3 Reduce dependencies to specific capabilities, not completed plans

Agree one small shared contract before parallel implementation: project/worktree identity; authority and source scope; local-user grants and binding semantics; version/provenance/freshness; bounded query/expansion; lifecycle/usage receipts; and handoff states. Put the same versioned contract references in all four plans. This is a planning agreement and a few owned integration tasks, **not another foundation phase**. Preserve existing valid APIs while adding required fields/operations.

| Necessary dependency | Minimum prerequisite | Work that must remain independent |
|---|---|---|
| Automatic recall must not expose unsafe memory | A's shared defensive-read/expansion fixes and B's approved scope binding | B host discovery, packaging, diagnostics, and task authoring can proceed before A's user UI, hybrid search, or maintenance work finishes. |
| Learning and cross-agent capture need trustworthy evidence | Shared grant/provenance/version rules and the particular producer/consumer being used | C can build and test real AST indexing, recipe matching, workflow analysis, and public-tool consumers without every B host adapter. B handoff must not wait for complete C learning. |
| Graph-aware context must reference current symbols | C's qualified-symbol, source-revision, and graph-coverage interface | D budgets, distillers, result projection, provider usage, caching, and local queries can proceed independently. Only the graph-dependent selection task waits for that specific C component. |
| UI and accounting need real producers | The exact canonical operation or receipt producer displayed, with native acceptance for that feature | Status/search work does not wait for completed handoff; usage instrumentation does not wait for the full token optimizer; completed existing producers can be integrated immediately. |

All four plans can therefore be authored and started in parallel. **Do not promise that every task or release gate is independent.** Unsafe recall cannot ship merely to avoid a dependency; a receiver test cannot pass without a sender/receiver route; combined savings cannot be measured without real request producers. Record these as named task/contract edges. Never write “depends on Phase A/B/C/D completion” where the actual need is one shared operation or invariant.

A plan's acceptance uses the real compatible capabilities available in the integrated repository. Fakes may test a contract, but do not establish a working product feature. If a required integration component is still absent, only that acceptance lane remains open; do not substitute simulated metrics, placeholders, silent degradation, or an unsupported readiness claim. Final whole-system confirmation runs within the concluding integration task of the participating plans, with responsibility explicitly assigned; it is not an extra development phase.

### 11.4 Parallel execution and existing plans

Start independently with A's read/integrity repairs, B's host discovery/diagnostics and consented guidance design, C's real parser/index population and conditional-learning consumers, and D's measurement correction plus output/budget paths. Agree shared contracts first, then merge their small prerequisite changes as soon as independently verified; do not hold them until an entire phase finishes.

Give one integration owner serialized changes to `src/rush/tools/memory.py`, `src/rush/memory/store.py`, `src/rush/integrations/agents.py`, `src/rush/tools/agent_connection.py`, `src/rush/cli.py`, and `src/rush/mcp.py`. Give distinct owners AST, token algorithms, host assets, and app views, with narrow integration patches queued against those shared files. Parallel plans do not authorize simultaneous conflicting edits or duplicate implementations of permissions, storage, and receipts.

This recommendation replaces **phase-wide interpretations** of earlier proposed sequences, not their required behavior. In particular, AP06 need not wait for all of AP05's learning/capture features when its actual grant/receipt/transport prerequisites are ready; AP07 search/status tasks need not wait for completed handoff when their canonical operations exist. Shared-file edits still serialize. AP08 real-agent and whole-system evidence remains mandatory.

Phase 70/71 overlap must be reconciled by exact task and acceptance ownership when the four plans are authored. Reuse their adopted contracts and required outcomes rather than duplicate them or add a blanket “finish Phase 70/71 first” dependency. Existing required native packaging, full terminal memory administration, and live dashboard memory acceptance remain in scope. No Phase 70/71 file or previously written report section was changed to create this proposed split.
