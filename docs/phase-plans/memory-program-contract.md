# Rush memory program: shared contract and four-plan scope ledger

Status: implementation specification; application implementation has not started in this planning task. This is a shared contract, not a fifth phase. Written 2026-09-25. Repository baseline `ddc064117e971b48e29100004052e876e456faf2`.

## 1. Authority and complete scope

The controlling request is to implement the full outcome described by `docs/reports/memory-system-implementation-review-2026-09-25.md`, including all findings, capability proposals, user additions, token/context research, the live adoption failure, and §11's four-phase split. No implementation may erase a requirement to match existing code, replace real behavior with simulated output, or reinterpret a research-labeled mechanism as permission to omit its desired outcome.

Four plans own the work:

| Plan | Product outcome | Primary boundary |
|---|---|---|
| [Phase 72](phase-72-memory-correctness-and-user-control-plan.md) | Trustworthy, searchable, correctable memory with explicit preference scope | Canonical store/read/admin/preference semantics |
| [Phase 73](phase-73-agent-activation-and-continuity-plan.md) | Coding agents discover and dynamically use/write the same memory, then continue across agents | Host adapters, grants, lifecycle, handoff and activity evidence |
| [Phase 74](phase-74-ast-learning-and-workflow-intelligence-plan.md) | Current code and observed outcomes improve reasoning, workflows, skills and design/architecture compliance | AST identity/graph, learning producers/consumers and grounded procedures |
| [Phase 75](phase-75-context-and-token-efficiency-plan.md) | Less irrelevant context and fewer total tokens for correct work, with measured costs and recovery | Packet selection, projection/query, optimization and usage/evaluation |

Binding existing inputs are `AGENTS.md`, `docs/templates/task-block-template.md`, `docs/adr/0010-review-and-remediation-gates.md`, Phase 61/63 memory contracts, Phase 57 invocation grants, and Phase 68/69 ownership/recovery contracts. Phase 70/71 remain intact. Their relevant tasks are reused or extended by named task ownership; no blanket prerequisite requires either entire phase to finish. Existing task behavior remains required even if its files are implemented by one of these four plans.

## 2. Evidence and preservation baseline

Planning started with only `AGENTS.md` tracked changes and existing untracked Phase 70/71/report/review directories plus `src/rush/tools/.rush/`. These belong to prior work. Application source/tests match the baseline commit. Preserve these input files byte-for-byte during plan authoring:

| Input | Bytes | SHA-256 |
|---|---:|---|
| Memory review | 205745 | `c256b70e28c6d6209ec21ea205c49caa39b0e351d41143fc3e75b451a5c8779a` |
| Phase 70 | 142031 | `e431c0d134c3883a8263ab0977b5dcb0b26ff9553be83e49f3a1faf0ee7c3589` |
| Phase 71 | 68703 | `d6f2e9dbd6cca08aa0f45abf908c7f4cee688e4c427359a97c0c527b943b3339` |

Graft discovery and narrowed source spans ground the plans. The review's executed tests and installed MCP probes are historical evidence at their recorded subjects, not new execution of the proposed features. Installed executable identity, Rush package version, MCP SDK/server-reported version, source commit, and host version must be recorded separately. A source test cannot prove installed host adoption.

## 3. Shared implementation contracts

### C01 — Authority, authorization and preference precedence

Reuse `TypedArtifactStore`, `MemoryArtifact`, `OwnerScope`, `legacy_owner_scope`, existing invocation permissions and canonical `MemoryTool` operations. Do not introduce a second memory database, duplicated permission dispatcher, or a transcript-derived authority model. Source allowlists, owner identity, project scope and subject are distinct fields.

Ordinary local MCP/CLI setup grants the local OS user's Rush installation explicitly selected project/worktree/source/operation access. A client-supplied host or session name is attribution, not authenticated identity. There is no claim of isolation against mutually hostile processes running as the same OS user. Non-secret session bindings reference approved policy and its revision; every operation revalidates policy/root/source access. A binding never grants access by itself. Revocation/relink invalidates affected bindings. A remote or restricted recipient uses an explicit capability, never the local-user shortcut.

73-T02 owns `src/rush/memory/authorization.py` and the local-user policy at `default_data_root()/user/.rush/memory_authorization.json`, schema 1 with monotonic revision, explicit grants and session bindings. Reuse `AtomicFile`/`PhysicalRoot` and CAS primitives; this is authorization metadata, not another knowledge database. APIs are `load_policy_readonly`, `grant_memory_scope`, `revoke_memory_scope`, `resolve_memory_scope`; only explicit local setup consent creates/enlarges grants. 72-T01 owns defensive artifact eligibility and consumes this module. No project `agent_memory.json`, host/session string or copied binding can authorize access. Opt-in global preferences use `TypedArtifactStore` rooted at `default_data_root()/user`, hence `user/.rush/memory.db`, under a separately approved overlay grant; project reads never silently enable it.

Canonical read policy is shared across legacy/compact/hybrid search, relations, summaries, pages, expansion, learned procedure applicability and caches. Check owner/source access, active/archive state, expiry, integrity, authority and source freshness before delivery. Unknown freshness is not current. Historical inspection is an explicit authorized, labeled route, not ordinary recall. Content changes invalidate prior promoted authority atomically. Store absence is an empty/unavailable read state, never authorization to create a store, migrate a database, or write a key/journal during a read.

Preference decisions are fixed: optional user-wide overlay is opt-in; project and task policies remain separate; explicit applicable current user instruction/correction takes precedence within the host's instruction hierarchy; project choice overrides generic user default for that project; task choice overrides applicable defaults for that task; inferred convention remains advice. Preserve source, approval/correction/rejection, applicability and supersession. No memory can manufacture higher-priority instructions or permissions. User-wide storage uses Rush's existing user data root and the typed artifact schema, with explicit authorized overlay reads; never copy global rows into every project store.

### C02 — Evidence identity, mutation and exact recovery

Extend existing artifact/version models and serializers, preserving old public fields. New evidence references normalize `artifact_id`, `artifact_version`, `content_hash`, canonical `project_id`, `worktree_id` where relevant, `owner_scope`, `source`, `subject`, trust/provenance and freshness. These are references to real records, not generated labels. Wire additions live in the existing versioned result envelope; never repurpose artifact revision as schema version. New strict request variants and legacy adapters must agree on omitted/null semantics and reject mixed forms before effects.

Mutation requires the existing grant/owner/version checks, preview/apply semantics and durable receipts. A fresh promotion follows Phase 71 P07's candidate/policy operation, leaving the inspected original unchanged; it is not an arbitrary edit to trust. Deletes name exact IDs/revisions. Retries are idempotent by invocation/effect identity, not content equality. Cross-owner corroboration cannot promote either owner's evidence. Rejected suggestions and revoked records remain excluded from ordinary recall.

Cursors bind root, owner/source scope, filter, snapshot/generation and first unconsumed item. Every page rechecks current access/visibility. A page/count/token limit does not mean all results were returned. Expansion uses bounded UTF-8-safe slices, version and digest with verifiable reconstruction; existing base64 callers retain an explicit compatibility representation. Missing/expired/revoked source cannot be reconstructed from a summary or falsely labeled recovered.

### C03 — Agent lifecycle and continuation state

Bootstrap is proposed as `rush_memory operation=bootstrap` plus the shared CLI equivalent. It derives scope from consented local policy or restricted continuation capability; it does not make the model guess allowlists. Response includes real project/worktree, binding, access state/reason, memory revision, bounded relevant evidence, omissions and next action. Empty/denied/stale/missing-tool states differ. Scope selection must not leak a private session inventory.

Capture operates at meaningful events: task/subtask start, relevant source change, failed check, user decision/correction, verified outcome, checkpoint, compaction/interruption and handoff. Persist typed observations and unresolved obligations under actual consent. Dedupe event IDs; show capture disabled/denied/failed rather than suppressing errors. Agent-guided checkpointing is labeled differently from native automatic event capture. Mandatory requirements and negative evidence survive compaction and agent changes.

State labels are separate facts: configured; fresh server reachable; actual-host callable observed; scope authorized; context returned; model context insertion observed when host instrumentation exists; evidence applied with action link; permitted write persisted. `acknowledge=True` is not observed use. Avoid one boolean that turns all these states active.

Handoff uses existing `prepare_handoff`, `dispatch_handoff`, `receive_handoff`, restricted bridge and store. Capability travels only in the owned receiver's `RUSH_MEMORY_CAPABILITY` environment, not prompts/argv/logs. Sender prepare's local initial delta is not receiver recall. States are prepared, dispatched, receiver_recalled from validated receiver-channel activity, receiver_checkpointed as agent-reported work, and continuation_verified only with an independent task-specific result. Expose error/cancelled/expired/revoked. Legitimate duplicate delivery/read is idempotent; forged/revoked/foreign-scope access fails. Current code/source revision is revalidated on receipt; historical passing checks never become current proof.

Current public prepare/receive exports and accepts a bearer capability; retain a compatibility route only with unverified receipt semantics. A proof-bearing dispatch instead mints a non-exported capability inside the owned launcher, binds it to the managed child/private channel, and validates receiver activity there. Sender-submitted acknowledgements through public receive—even with a legitimate legacy capability—cannot advance `receiver_recalled`. This proves managed-channel provenance within the stated local-user trust boundary, not isolation from a hostile same-user process.

### C04 — AST and code evidence

Parsers belong to Rush's runtime; project initialization creates project/worktree indexes without editing target dependency manifests or installing parser packages into every project. Python AST and tree-sitter grammars provide syntax; optional semantic backends may require the project's normal compiler/dependencies, which are detected and disclosed separately. Regex extraction cannot advertise AST or semantic coverage.

Code identity combines project/worktree/revision, canonical relative path, language/parser/grammar version, qualified symbol, exact source hash and separate structural fingerprint. Structural similarity proposes applicability, not equivalence or behavioral proof. Edges carry kind, source location/revision, extractor and confidence/coverage. Unknown dynamic dispatch, missing imports/baselines and parse failure remain explicit. Populate and update the production graph; classes and tests alone do not establish a live graph.

Phase 74 owns canonical parsing/identity/edge generation; Phase 75 consumes that interface for graph-aware selection, not another parser or graph. Phase 72 owns shared visibility and containment. Invalidation follows recorded dependencies with cycle handling; evidence missing from the graph cannot be confidently declared unaffected. Do not propagate a previous verification pass to a new revision.

### C05 — Context, budgets and recovery

74-T03 `learning_context.py::rank_advice` owns memory applicability tiers, immediate failure/correction demotion and outcome ordering. 75-T07 consumes that ordered record stream without rescoring/reordering or restoring excluded advice; its bounded learned utility applies only to nonmemory code/tool candidates. Both use the same receipt IDs. Packet allocation preserves mandatory facts and memory-relative order and reports omitted suffixes/recovery. Outcome ranking and token allocation must not implement competing memory policies.

Use one budget contract: model/encoding/tokenizer version, maximum UTF-8 bytes, maximum rendered tokens, selected/omitted counts, provenance and continuation. Count the complete delivered representation including instructions, frame, IDs and recovery handles. Preserve status/errors/required constraints; if their minimum envelope cannot fit, return a bounded explicit minimum-budget failure rather than invalid/truncated markup or false completeness. Unknown host tokenization is an estimate with a stated bound/margin, not an exact guarantee.

Select relevant evidence before serializing. Canonical full results remain available through existing authorized artifacts/CCR; agent and user views are projections with omission/recovery evidence. Exact diagnostics/code/requirements are never rewritten by a prose compressor. A handle's short length proves deferral only; measure subsequent retrieval, rereads and repair calls. MCP JSON-RPC and canonical machine schemas remain valid; optional encodings apply only to negotiated presentation fields.

### C06 — Receipts, measurement and cost

Phase 75-T01 extends `TelemetryStore` and normalized provider results; other phases emit the shared producer records as soon as their features run. Retain request/invocation/project/run/agent/session identity, artifact/version/hash, event kind, recipient, source revision, selected transform/version, tokenization basis, timestamp, parent call and observed/estimated/unavailable status. Native provider IDs are preserved where supplied; local invocation IDs distinguish repeated same-content calls. Existing consumers remain compatible through an explicitly versioned projection; correct the misleading cache-cost category without relabeling old observations as actual hits.

Keep local work, returned/delivered context and provider usage distinct. Provider input/output counts, cache-read/cache-write semantics, embedding units, duration, pricing source/version and monetary cost are normalized per provider; unavailable is not zero. Cached input may be a subset of total input and must not be added twice. Query returned to a client is not proof of model insertion or application. Cache fills and memory retrieval costs are not savings.

No fixed universal dollar rate, zero-floor clamp, or invented whole-repository baseline. Actual net difference counts all model calls once, including construction, compression, subagents, retries and repair; retrieval already in input is not separately added again. Local model resources/latency and embedding charges are separately reported. Negative or inconclusive results remain visible. Tokenizer estimates across incompatible models are not summed into a fictitious comparable saving; use per-model vectors and normalized cost where known.

### C07 — Host capabilities and supported modes

Native host contracts include version-tested ZCode plugin `hooks/hooks.json` (`SessionStart` startup/clear/compact, `UserPromptSubmit`, `PostToolUse`, `Stop`; project hook files ignored) and Antigravity CLI `PreInvocation` with `injectSteps.ephemeralMessage`, `PostToolUse`, `Stop`. Antigravity has no claimed compaction event; next `PreInvocation` refresh bridges context loss. Hook metadata alone cannot prove transcript semantic capture or a model-used memory. 73-T03 supplies catalog-backed task/operation discovery beyond static core/full profiles, with host-native discovery where supported and an explicit callable fallback, tested on all five hosts.

Phase 73 owns the versioned host capability matrix and packaged guidance, including Claude Code, Codex, Cursor, Antigravity/`agy`, and the Z.AI coding-host lane. The plan resolves that last lane to Z.AI's first-party ZCode host/CLI; Z.AI models used through another host remain a distinct provider capability, not fulfillment of native host coverage. Exact documented mechanisms and real-call tests determine supported modes.

Treat MCP registration, instructions/skills, startup hooks, edit/check events, compaction events, tool-result injection, provider usage visibility and handoff transport as independent capabilities. Do not invent an event or native protocol to fill a matrix cell. Provide the documented usable cooperative/CLI route when that is the actual supported mode and retain an unmet automatic-native guarantee as an explicit limitation/acceptance blocker. No Git hooks, default permission escalation, arbitrary event-payload shell, or automatic host trust approval.

### C08 — Evaluation and completion

Every phase must execute real public routes, relevant negative cases and actual task outcomes. Phase 75-T02 repairs the existing benchmark runner's scripted-decision/completion-score/budget problems early; other phases consume that bounded component without waiting for all Phase 75 optimization. Keep deterministic unit fixtures as component evidence, separate from live agent episodes. Real host absence, credentials, native trust or missing provider support cannot be faked by callbacks.

For each new decision/selection policy, freeze a held-out task set before tuning, covering successful and failed/cancelled/corrected workflows, incompatible applicability and unknown evidence. Baseline is a competent ordinary workflow or existing fixed lexical policy, under the same task/revision/model/tools/grants. Required constraints/security/correctness must all pass; wrong/stale/unauthorized evidence is a failure, not an averageable tradeoff. Report trial counts, task IDs, outcome criteria, retries, latency, token/cost dimensions and uncertainty. Performance claims are limited to the observed workload; no imported upstream percentages.

75-T02 repairs decision execution using actual Codex/Claude structured CLI responses, not presence-probe `ProbeResult` or hard-coded success prompts. Full workload includes no reuse, misleading memory, missed/late-needed evidence, unsupported language, duplicate symbols, branch/worktree/rename/suppression/expiry and long handoff. Report cold acquisition, first reuse, uses 2–5, observed cumulative break-even or `not_observed_through_5`, plus matched single-agent/multiple-agent arms with every coordinator/worker call. 75-T05 delivers compact scan/memory/review/handoff projections through all four interfaces. 75-T06 implements bounded typed graph joins as well as filtering, with stale/missing relations visibly incomplete.

Research-labeled behavior is implemented as a bounded explainable proposal/selection/evaluation loop with abstention, provenance and user control. Candidate algorithms that fail benefit/quality tests remain unadmitted to automatic use; the required capability, UI and evaluation stay in scope and the failure is recorded. No experiment's “completed” state implies correctness or useful learning. Claims of cross-agent continuity require sender/receiver activity and independent result checks, not copied summaries or exit zero.

### C09 — Parallelism, ownership and phase reconciliation

No whole-phase completion dependency. Named prerequisites are: 72-T01/T02 safe canonical delivery, 73-T02 grants/bootstrap when using the new host path, 74-T01 qualified graph identity for graph selection, 75-T01 receipts and 75-T02 live outcome evaluation. Existing correct public routes can support development/real tests while other adapters are incomplete. Safety and required behavior cannot be waived to declare independence.

Serialize edits to `tools/memory.py`, `memory/store.py`, `integrations/agents.py`, `tools/agent_connection.py`, `cli.py`, `mcp.py`, dashboard shared adapters and shared tests through one integration owner. Other workers own disjoint bounded modules/assets. Producer and consumer task ledgers identify the exact contract/version and acceptance case; never build duplicate stores, parsers, receipt databases or permission rules to avoid coordination.

Phase 70 T1–T7/T26 native setup is reused by 73; T18–T22/T28-D canonical memory/admin by 72/73; Phase 71 P07 user memory by 72 with 74 evidence views; P08 token UI by 75; P10 setup by 73. Each phase plan states literal additive implementation writes for its subset. Source plan files themselves stay unchanged here. Missing relevant underlying operations are in-scope tasks, not hidden prerequisites. Full unrelated dashboard/terminal surfaces remain in their original plans and are not falsely marked complete by memory work.

## 4. Complete report-ID ownership ledger

Each family below is owned in full. Per-task acceptance is in the linked phase's requirement ledger; shared contributions do not remove primary ownership. AP08 is integrated into each phase's acceptance, not a fifth phase.

| Report IDs | Primary phase | Delivery/acceptance owner |
|---|---|---|
| F01–F08, F15, F18–F19, F23–F24; A02–A03; B05; E06/E19/E25; R01–R03/R05–R06/R08/R18; AP01 | 72 | Canonical safe memory, preference policy, user controls and truthful documentation |
| F09–F14; A01; B01–B04; E01/E13–E15; R04/R17/R20; AD01–AD04; TC05/TC09; AP02–AP06 | 73 | Native discovery, scope, lifecycle, capture, independent receiver continuation; 74 contributes learning to AP05 |
| F16–F17; A05; E02–E05/E07–E12/E17–E18/E20–E24; R09–R16; TC08/TC13–TC14 | 74 | Production AST and reasoning/workflow/skill/design/architecture behaviors |
| F20–F22; A04; E16; R07/R19; TR01–TR11; TC01–TC04/TC06–TC07/TC10–TC12 | 75 | Token/context implementation, real evaluation, usage and recovery; 73 supplies TR07's host profile/discovery |
| AP07 | 72 canonical/user-memory UI; 73 activation; 75 tokens; 74 learned-evidence views | Each owns its actual producer/consumer and native view checks |
| AP08 | All four; benchmark mechanics 75-T02 | Each feature's public/real-host outcome plus combined frozen integration receipt |

Explicit unnumbered user outcomes are also binding: active/accessible/usable/writable agent memory; coding-agent switching without restating development history; current context and ongoing development; user preferences; project-specific and user-wide scopes; patterns/antipatterns; learned facts; user search; integration with the app; AST installation boundary; innovative conditional learning; persistent workflows and skill suggestions; user-specified UI/architecture and inferred architecture; agent improvement; context/token reduction and current resource research. The named E/B/TC tasks implement these outcomes, not merely mention their keywords.

## 5. Verification rules for implementation and for these plans

Implementation: Python 3.12 through `uv`, clear inherited `PYTHONPATH`, RED→GREEN concrete cases, relevant public/installed/native checks, then repository lint/format. No version bump, commit, push, release, paid call or user configuration write is implied by authoring or approving these plans. Existing explicit action grants govern execution. User docs are published only after their described route works.

Before implementation readiness is reported, independently review frozen plan bytes for (a) full requirement meaning and ownership, (b) source/template/command alignment, (c) authority/permissions/recovery, and (d) task-level dependency and shared-file safety. Resolve defects in the actual documents; a count-only ledger check is insufficient. Verify links/files, original-input hashes and complete ID coverage after corrections. Record review evidence and any unresolved external host-support facts honestly; planning readiness is not implementation completion or native acceptance.

## 6. C10 — PAS recommendations adopted into the existing phases

The user's subsequent request to add the [PAS review recommendations](../reports/pas-agent-portable-memory-comparison-2026-09-25.md) makes all four recommendations implementation-plan scope. The report remains a historical research artifact; its earlier “not approved changes” and “assess demand” language no longer defers these plan additions. PAS compatibility remains opt-in at runtime, with required implementation and conformance/real-use acceptance. There is no fifth phase, PAS runtime dependency, replacement memory engine or reduction of the original 116 report requirements.

| Added requirement | Primary implementation owner | Supporting contract and acceptance |
|---|---|---|
| PAS01: self-contained portable continuation capsule | 73-T09, extending T05's continuation path | 72-T01/T06 authority and atomic import; 75-T03/T04 full-frame budgets, offline evidence and recovery; second-checkout/machine receiver acceptance |
| PAS02: minimal managed instruction bridge | 73-T09 and T03 activation assets | 75-T03 budget including wrapper; byte-identical surrounding instructions, malformed-marker refusal and actual reread/consumption receipts |
| PAS03: visible start → checkpoint → continue journey | 73-T09/T08 using existing session/continuity implementation | 72-T07 searchable imported provenance and constraint review; 75-T10 honest native/CLI/offline delivery and usage states; interrupted/missing-adapter acceptance |
| PAS04: format conformance and optional PAS import/export | 73-T09, one codec in `src/rush/memory/capsule.py` | 72-T06 canonical import transaction, no foreign authority; 75-T02 matched round-trip/negative/real-agent cases; loss manifest and rejected unsupported formats |

One proposed `MemoryTool` operation, `capsule`, owns the portable public route; its exact request/CLI contract is defined in 73-T09. Export is a projection of authorized canonical artifacts; import creates provenance-bearing local artifacts through existing transactions. No portable file can transfer permissions, receiver credentials, signing capability or verified authority. External instructions/constraints need local applicability review. Offline usability requires embedded required evidence, not inaccessible machine-local handles. A valid checksum proves byte identity, not honesty or freshness of the author's claim.

Use C09 shared-file serialization. Phase 73 exclusively owns codec/bridge serialization and transport; Phase 72 owns defensive eligibility, canonical mutation and user review; Phase 75 owns shared counting/selection/receipts and workload economics. Phase 74's existing qualified source identity and invalidation contract is reused where available; offline basic continuation uses exact source hashes and explicit unknown coverage without waiting for all AST/learning work. No whole-phase dependency is added. Exact task prerequisites and completion gates appear in each additive section.

The original Phase 72/73/75/shared-contract bytes remain preserved as prefixes beneath these additive requirements. Earlier frozen readiness hashes describe the prior package; the PAS-inclusive package requires a new frozen review receipt. Phases 70, 71 and 74 and both source reports remain unchanged by this integration.
