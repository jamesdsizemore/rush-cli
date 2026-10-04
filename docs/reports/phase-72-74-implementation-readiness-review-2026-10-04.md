# Phases 72–74 implementation-readiness review — 2026-10-04

## Verdict and meaning

**READY as implementation specifications**, on the frozen plan and shared-contract hashes below. All 27 task packets retained. Required corrections were applied to the plans, independently reviewed, and integrated. No known plan finding remains open.

This verdict permits implementation planning against these specifications. It does not claim their proposed functionality exists, Phase 70 is accepted, native host adoption succeeds, or token/agent benefit has been demonstrated. New implementation tests in the packets remain proposed until their named implementation exists and those tests execute. No production fixes, release changes, commits, pushes or installations were authorized or performed by this review.

| Authoritative artifact | Frozen SHA256 |
|---|---|
| [Phase 72](../phase-plans/phase-72-memory-correctness-and-user-control-plan.md) | `94d911d7592ffda330d6ca21c990faf7824a8e8a303144395d865ae9b982bff2` |
| [Phase 73](../phase-plans/phase-73-agent-activation-and-continuity-plan.md) | `d11dccfeec400110d1cab9a10cf5dcf06d90f79a4ba776dcf836cc07e55a62ae` |
| [Phase 74](../phase-plans/phase-74-ast-learning-and-workflow-intelligence-plan.md) | `151f96c855238f04c7276a6b23428e27a2c1e8ba82b4ae4ea4e2a0aa13a8e166` |
| [Shared memory contract](../phase-plans/memory-program-contract.md) | `265424c0398816bf854db138d9989000a5a63805c1d088926658cdd52b490249` |

## Controlling scope and current repository

User required deep review of all three plans, current-repository and Phase 70 alignment, issue-by-issue task adequacy, implementation readiness, appropriate subagents, research, verification, full correction and review before handoff. No scope reduction was authorized. Defect fixes, baseline requested features, enhancements, implementation evidence and future acceptance remain separate.

Review began with the supplied local corpus: each complete plan, shared contract, exact [task-block template](../templates/task-block-template.md), [memory implementation review](memory-system-implementation-review-2026-09-25.md), [PAS comparison](pas-agent-portable-memory-comparison-2026-09-25.md), current Phase 70 plan/handoff/restart evidence and Phase 71/75 boundaries. External research was confined to primary protocol/package sources required to verify interfaces named by those plans; it did not replace the local requirements.

Primary planning checkout: `/Users/jamesdsizemore/Developer/rush-cli`, HEAD `c78e445ba1e575ca373e35840142cd627b055d6a`, branch `codex/codex-cli-mcp-commands-review`. Actual developed checkout: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, HEAD `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`, branch `phase/70-agent-adoption-and-usability`, with active uncommitted implementation. HEAD alone does not identify those dirty source bytes.

Existing primary `AGENTS.md`, scratch directories, command plans and untracked reports were user-owned before this work. They were not edited by this review. Review edits are exactly the three plans, shared contract and this report. Phase 70 source/development, Phase 71, Phase 75 and source reports remain outside the write set.

### Phase 70 reconciliation

Current Phase 70 §3.3 owner amendment retains Claude Code and Codex acceptance and supersedes Cursor only for Phase 70. Phase 73 retains all five requested hosts: Claude Code, Codex, Cursor, Antigravity/agy and ZCode/zai. The amendment does not remove those later requirements.

Reuse developed strict MCP request models, canonical invocation/permission paths, dashboard/TUI memory operations, process ownership, Windows lock wait-result checks and installed artifact support. Historical primary line numbers and earlier `ddc...` receipts are not current development truth. Phase 73 handoff spans distinguish primary source from developed source; existing maintenance import and edit-authority repairs are preserved.

Phase 70 restart evidence still requires final frozen G7/full-suite, current Linux/Windows CI, rebuilt wheel/sdist/frozen artifact evidence, native/host/browser journeys and final review. The inspected native evidence recorded successful tokenizer-backed expansion followed by a held-record refresh failure when an external version-2 edit disappeared from the active query. The live TUI changed during this review; the affected source assumptions were rechecked separately below. Neither a local repair nor this plan verdict closes Phase 70 acceptance.

Implementation priority remains current Phase 70 correction and acceptance. Narrow technical checkpoints in C09 do not override that priority or Phase 71's full Phase 70 gate. Shared source writes require explicit reservation and one integration owner; dirty files are not unowned merely because a later task lists them.

## Review coverage and independent gates

Three bounded workers used `gpt-6.1-sol`, high reasoning, one owned phase plan each. Parent owned shared contract, integration and this single report. No worker was authorized to edit source or another phase's plan. Independent peer rotation: Phase 74 reviewer → Phase 72; Phase 72 reviewer → Phase 73 and shared integration; Phase 73 reviewer → Phase 74. Any edit invalidated the previous hash verdict and triggered an affected-byte rereview.

All eight numbered sections and all nine task packets of each plan received full applicable coverage:

| Lane | What was reviewed | Closure |
|---|---|---|
| User outcomes and issue reconciliation | Every assigned finding, baseline feature, enhancement, PAS outcome and app/agent/token contribution; no replacement with counts or headings | Full coverage; detailed rows below |
| Task logic and dependencies | Template fields, owned files, current symbols, producer/consumer schemas, prerequisites, technical DAG, actual execution priority and shared integration | Corrected and closed |
| Runtime and trust | Actual read/write paths, permissions, authority, source freshness, budgets, receiver provenance, lifecycle, routing and store identity | Source-backed; surviving implementation defects retained as work |
| Recovery and adversarial cases | Replay/CAS, revocation races, missing store/no read initialization, graph replacement/WAL, stale receipts, interruption, corrupted/oversized input and migration | Exact proposed transactions and negative fixtures added |
| UX, assets and readiness | All seven memory subjects, CLI/TUI/browser, keyboard/accessibility, native host hooks, parser/package availability, installed routes, gate semantics and docs parity | Required empirical acceptance retained; no simulated closure |

Phase 72 independent PASS: `94d911...`. Phase 73 independent PASS: `d11dcc...`. Phase 74 independent PASS: `151f96...`. Shared integration independent PASS: `265424...`. Hash abbreviations here refer only to full hashes in the verdict table.

## Corrected blocking findings

These are corrections to implementation specifications. Code and verification described in the plans are proposed unless explicitly identified as executed in the empirical section.

| Defect in prior specification | Concrete correction and exact location | Check / disposition |
|---|---|---|
| Historical checkout treated as developed source | Each §2 and file map names primary versus dirty Phase 70; Phase 73 T05 distinguishes live handoff span | Exact HEAD/source checks; closed |
| Task packets lacked independently executable obligations | All 27 packets use the exact template's Implement/read, behavior, deliverables, constraints, checks and completion fields; Handoff is included when an artifact is required | Packet-by-packet substantive reread; closed |
| Reads could initialize stores or bypass eligibility | 72-T01 canonical eligibility and read-only store access cover legacy/search/pages/expansion/relations/cache/learned consumers; absent/old schema cannot migrate on read | Actual source probe exposes current defects; proposed public-route negative checks specified |
| Root, authority and hash semantics conflated | 72-T01 rejects traversal/absolute/symlink escape, separates source hash from payload integrity, invalidates promoted authority on content change | Concrete outside-root and mutation fixtures; closed specification |
| Pagination and UTF-8 recovery could fabricate completeness | 72-T02 specifies exhaustion, signed revisions, scalar-safe byte offsets, digest/version checking and no-progress failure | Three-record/two-item pages, 513 candidates, corrupt/revoked/stale cursor and multibyte fixtures |
| Policy CAS protected only one process or left revocation gap | Shared C01/73-T02 acquire existing OS policy lock before CAS; 72 mutators retain policy lock through canonical SQLite commit | Two-process revision-0 race → exactly one grant; revoke/apply serialization; closed |
| Positive budgets too small even for error envelope | Shared C05/72-T02 admission preflights complete error/framing minimum; admitted responses must fit both caps; rejected admission is counted separately | Cap 1 and minimum−1 reject before effects; no mandatory facts dropped |
| Inferred task/project preference could overrule explicit personal instruction | 72-T05 authority first; applicability/default precedence within explicit authority only; global overlay remains opt-in | Explicit personal compact beats inferred project wide/task plain; closed |
| Bootstrap/binding and host acknowledgements overstated proof | 73-T01/T02/T05 separate configured, reachable, callable, authorized, returned, inserted, applied and persisted; bootstrap cannot create consent | Wrong argv/empty home/reconnect/forged ack/managed receiver fixtures |
| Local worktree cursor could not observe another worktree's store | 73-T06 defines strict `delta`/`delta_ack`, `read_source_deltas`, approved purpose-specific source/destination mappings, source-qualified vector and acknowledgement transaction | Actual two-worktree probe confirms separate stores and IDs; proposed producer-through-consumer fixture |
| Host hook fields/events were generic or wrong | 73-T03/T04/T07 and C07 use exact supported host events/insertion fields; failed-tool capture and compaction refresh are explicit | Primary official sources verified; all five actual host journeys remain required |
| Capsule replay, nullable PAS fields, side effects and authority were underspecified | 73-T09/C10 bind preview/apply to invocation UUID, digest, selected scope, current grants and target prestate; pinned PAS Serde/default/Option/loss rules | Replay conflict/no-write preview/atomic import/byte-preserving bridge fixtures |
| Graph claimed semantic edges without an indexing producer | 74-T01 defines qualified Python/TS/TSX/Rust producer, package/parser contracts, persisted edges and actual public consumer | Existing graph probe finds zero CALLS and stale nodes; exact new graph fixtures retained |
| Graph migration/replacement could lose WAL writes or stale readers | 74 §3.6/T01/T02 serialize all graph writers with existing OS lock, use SQLite backup, self-contained staging, generation CAS and fresh opens; invalidation outbox bridges stores | Required concurrent writer/crash/WAL/stale-generation tests; closed |
| Learning `max_items` could truncate mandatory requirements | 74-T03/T06 limits optional advice only; complete obligations retained behind recoverable bounded handles and C05 admission | More obligations than advice cap must all remain accessible |
| Compaction/session changes could manufacture successful workflow examples | 73-T04/C03/74-T06 require originating `task_lineage_id`; exact suspend/resume/cancel translator, scoped continuation ref and explicit cancellation receipt | Copied sender/receiver/worktree/session count one lineage; two actual independent successes required |
| Failure memory and learned recipes had no exact effect on next action | 74-T03–T07 define versioned receipts, discriminating hypotheses, applicability/abstention, current helper adaptation, actual check obligations and user-controlled skill export | Negative and changed-condition cases exercise production paths after implementation |
| Final gates omitted slow tests/type/docs or relied on unavailable browser runner | 72-T09/73-T08/74-T09 retain `-m ""`, mypy/docs parity and native routes; 74-T08 uses available CUA DOM/viewport API, without installing a runner | Proposed full gates/native PTY/DOM journeys retained; closed specification |
| Report attached valid corrections to incorrect original issue IDs | This report's Phase 72/73 tables replaced from every canonical source row; six Phase 74 rows corrected for review integration, capture, AST pipeline, strategy advice and measured adaptation/reuse | All 89 original issue meanings rechecked; substantive mapping and proposed oracles reviewed independently, not inferred from counts |

## Issue-by-issue reconciliation

The source memory review contains 116 numbered IDs: 24 F, 5 A, 5 B, 25 E, 20 R, 4 AD, 14 TC, 8 AP and 11 TR. These plans own 87 phase-specific IDs plus shared AP07/AP08 = 89 reviewed rows below. Remaining 27 IDs retain Phase 75 ownership: `F20 F21 F22 A04 E16 R07 R19 TC01 TC02 TC03 TC04 TC06 TC07 TC10 TC11 TC12 TR01 TR02 TR03 TR04 TR05 TR06 TR07 TR08 TR09 TR10 TR11`. Phase 75 was not downscoped, modified or certified ready by this review. PAS01–PAS04 and unnumbered §6.7/§6.10–§6.13 outcomes remain additional requirements.

Each row identifies substantive planned change and concrete behavioral oracle. Packet verification commands and implementation file/symbol maps are authoritative in the linked plans; new fixture checks below are proposed, not reported as passing.

### Phase 72 — 27 owned IDs

| ID | Packet / concrete planned change | Behavioral oracle |
|---|---|---|
| F01 | Archived artifacts remain readable through compact recall/expansion → T01 shared active visibility | Under Alice policy, archived a2 absent from ordinary recall; direct expansion E_NOT_VISIBLE; only separately authorized, labeled historical inspection may expose it |
| F02 | Expired artifacts remain expandable → T01 expiry eligibility and T02 page revalidation | Expired a3 expansion E_NOT_VISIBLE; expiry between pages prevents subsequent ordinary page/expansion access |
| F03 | Promoted content mutation retains STATED/signature and compact recall bypasses integrity → T01 authority demotion and shared defenses | Preserve current edit demotion STATED→DERIVED and cleared signature/promoted time; close update_content bypass; altered signed t1 never ordinary compact/hybrid/expanded authoritative evidence |
| F04 | Maintenance corroboration crosses owners → T04 same-owner independent-evidence promotion | Alice/Bob one candidate each: Alice processed1, changed0; duplicate provenance changed0; Alice two independent allowed sources may promote1; foreign source adds0 corroboration |
| F05 | Result limit permanently truncates pagination → T02 exhaustion-aware continuation | p1/p2 at limit2 returns complete:false plus cursor; next page p3 then complete:true; all3 recovered exactly once under count/byte/token caps |
| F06 | Relation insertion/traversal lacks equivalent owner/namespace/archive/expiry/integrity/freshness defenses → T03 endpoint/hop eligibility | Alice s1→Bob m2 returns E_NOT_VISIBLE and writes0 edges; invalid neighbor exposes no ID/count; valid s1→m1 writes1 edge; inverse supersedes cycle E_INPUT leaves1 |
| F07 | Consolidated summaries outlive member evidence; currentness not enforced on actionable retrieval → T03 member validity | Edit/archive/expire/revoke/tamper m1 makes summary member_versions={m1:1} unusable and ordinary recall omits s1; permissioned history retains original members and contrary evidence |
| F08 | Fresh-process maintenance import fails circular initialization → T04 import boundary, retaining live70 repair | Fresh interpreter prints run_maintenance_cycle before tools.memory import; real permitted maintenance operation works independently of test import order; preview remains read-only |
| F15 | Project-local preferences lack established global scope/inheritance/consent policy → T05 scoped preference resolver and corrections | Separate consented personal overlay, explicit task/project/personal precedence, inference advice-only; personal compact/project wide/task plain resolve plain→wide on task end; unrelated project/private rows excluded; inspect/correct/supersede/reject persist |
| F18 | Dashboard user search absent behind generic JSON rendering → T07 real browser query/filter/record journey | Browser query needle, all subject/source/trust/freshness/owner/archive filters, selection/page/exact-version expansion and mutation feedback match persisted MemoryTool IDs/versions; empty/denied/stale/error states distinct |
| F19 | TUI cannot browse every subject → T07 extend live70 terminal controls | Real key events select/search every one of seven subjects, expand and perform authorized mutation; keyboard focus retained and project switch discards foreign late result; current live70 controls reused |
| F23 | Architecture/proposal/completion docs conflict with actual implementation/evaluation → T09 documentation reconciliation | Architecture/API/storage/host claims and Phase63/MC13 benefit claims carry implemented/integrated/evaluated/proposed states and exact revisions; historical receipts preserved; plan/test inventory never closes current host or benefit acceptance |
| F24 | Expansion violates promised UTF-8/version/hash/continuation receiver contract → T02 explicit UTF-8 mode with base64 compatibility | Stored JSON containing 🙂é𐍈 reconstructs exact UTF-8 bytes/SHA-256/version; interior scalar offsets E_OFFSET; altered digest or stale version rejected by receiver; bounded continuation and legacy base64 preserved |
| A02 | Symbol grounding permits absolute/traversal/symlink paths outside project → T01 contained symbol resolution at promotion boundary | Absolute external Known, ../ escape and symlink escape cannot establish promotion grounding; contained qualified symbol allowed only with exact source evidence |
| A03 | Missing API baseline or symbol-only artifact lacks verified freshness yet may be treated current → T01 shared API/source freshness | Missing main baseline, symbol_ref without content_hash, parse failure or unsupported language yields unknown, never usable_as_current; exact contained hash/revision/parser-qualified source yields current; historical inspection remains qualified |
| B05 | Shared-project and optional user-wide memory need explicit scope/consent/precedence/correction → T05 overlay/resolution/migration | Same-project agents share authorized choice; separate overlay consent required; unrelated projects retain private rules; task/project/personal exact precedence and correction provenance; migration inserts1 then0 and deleted key never resurrects |
| E06 | Learn equivalent corrections/rejections without inventing inferred preferences → T05 applicability and correction retrieval | Equivalent verbose panels proposal retrieves applicable rejection while unrelated wide integer stays allowed; later explicit reversal retained; explicit personal compact wins inferred project wide/task plain |
| E19 | Evidence-grounded why/what tried/what stale and correction impact beyond basic search → T06 history/explain/correction, T07 views | Actual explain returns exact supporting/contrary/attempted/affected refs and unknowns; correction retains original/history and invalidates affected downstream advice/relations before future recall; no invented rationale |
| E25 | Layer personal/project/task guidance across agents without overriding hierarchy or unrelated projects → T05 resolver, T06 correction propagation | Explicit task plain/project wide/consented personal compact apply only in correct scopes; task end returns wide; inferred advice cannot override any explicit rule; correction propagates without copying global rows or widening grants |
| R01 | Scoped bounded recall and exact expansion recovery → T01/T02 authorization, admission and continuation | Ordinary IDs exactly [a1], excluded refs E_NOT_VISIBLE; p1/p2→p3 exactly once; complete serialized output fits admitted byte/token caps; Unicode version/hash reconstruction exact; expired/revoked/drifted cursor refused |
| R02 | Lexical/metadata/paraphrase retrieval → T02 complete lexical/metadata path and T08 optional hybrid | Fixed literal and metadata queries recover all eligible records; held-out paraphrase-only positives retrieve judged relevant authorized evidence; denied/stale/revoked negatives never returned; missing hybrid endpoint retains truthful lexical fallback |
| R03 | Versioned evidence links → T03 current-version authorized relations | s1→m1 binds exact versions; changed/revoked/expired endpoint cannot remain current evidence; foreign s1→m2 writes0 edges; cycle denial preserves existing graph |
| R05 | Defended efficient search/cache not shared by newer routes → T01 canonical defense and cache consumer reuse | Existing defended lookup, compact/hybrid/expand and memory cache gate apply identical access/integrity/source-freshness decisions; tampered t1 or source-unknown u1 cannot reenter through cached advice; no unmeasured whole-workload efficiency claim |
| R06 | Consolidation must preserve evidence while invalidating unsupported summaries → T03 retrieval/member validity | Changed/archived/expired member invalidates actionable summary; original members and contradictions remain inspectable under historical permission; stale derived summary cannot replace evidence |
| R08 | Optional hybrid requires real endpoint and held-out quality/cost evaluation → T08 matched alternative evaluation | Frozen48 cases (12 literal,12 paraphrase,12 near-neighbor,4 denied,4 stale,4 revoked) compare lexical/hybrid/reranked with fixed judgments/budgets; actual endpoint/availability/cost recorded; worse or unavailable arm retained truthfully without fabricated benefit |
| R18 | Trust/scope/redaction/expiry must hold through every route → T01/T02/T03/T04/T06 canonical policy | Alice ordinary IDs exactly [a1]; archived/expired/tampered/foreign/unknown records denied across legacy/compact/hybrid/pages/expand/cache/relations/summary; corroboration stays owner-authorized, canonical redaction retained and export/import cannot transfer secrets or authority |
| AP01 | Automatically delivered memory trustworthy and recoverable → T01–T04 canonical integrity foundation plus T06 shared public path | One policy across ranking/relations/summary/pages/expansion; promoted mutation invalidates authority; excluded refs never reenter; every remaining eligible result has cursor; receiver reconstructs exact Unicode/version/hash with explicit legacy compatibility |

### Phase 73 — 29 owned IDs

| ID | Packet / concrete planned change | Behavioral oracle |
|---|---|---|
| F09 | 73-T01/T08: eliminate configuration/acknowledgement masquerading as registered-ready, connected or memory-active; validate complete executable/argv and project evidence stages | `test_wrong_argv_not_registered` rejects `["not","mcp","serve"]`; acknowledgement and independent server probe produce no actual-host call/recall evidence; registered-only never renders active |
| F10 | 73-T01/T03/T08: detect installed Claude Code independently of preexisting `~/.claude.json`, then perform consented registration and actual host adoption | `test_installed_claude_without_config` detects CLI in empty temporary home; consented setup creates one valid registration; fresh real Claude session subsequently calls Rush |
| F11 | 73-T02/T03/T04/T07/T08: add ongoing typed recall, delivery, outcome capture, compaction and subsequent resume beyond connection bookkeeping | Authorized lifecycle produces exact typed record/write receipts; later supported host retrieves applicable earlier learning without user restating it; absent consent produces no capture |
| F12 | 73-T01: make same-session reconnect idempotent and preserve confirmed bookkeeping observations | `test_reconnect_preserves_observation` reconnects after confirmed tool observation and preserves connected/observation fields; explicit reset remains separate; no claim that typed artifacts were deleted |
| F13 | 73-T04/T05/T08: preserve complete bounded CLI-provider handoff contract and observe receiving-agent read/action instead of accepting discarded output plus exit zero | Transfer retains constraints, decisions, evidence refs, failed approaches and next validation; exit 0 alone creates neither receiver-recalled nor continuation-verified; real receiver detects stale revision and continues required work |
| F14 | 73-T07/T08: implement and verify missing requested coding-host adapters, retaining Antigravity `agy` and actual ZCode Agent host identity rather than provider labels or generic ACP | Installed AGY and ZCode lanes exercise exact manifests/protocols, actual callable/bootstrap/capture/receiver evidence; all five host lanes remain required and unsupported capabilities remain explicit blockers |
| A01 | 73-T05: connect public handoff dispatch/status to existing permitted transport and receipt-derived lifecycle instead of unconditional `E_UNAVAILABLE` | CLI and full MCP public dispatch launch configured recipient; status reports prepared/dispatched/receiver-recalled/checkpointed/verified from actual receipts; permitted supported dispatch/status no longer unconditionally return unavailable |
| B01 | 73-T02/T03/T08: supported host starts with bounded authorized project/task brief and discoverable recall/write operations | Real host bootstrap returns exact current `req-A@2` and `attempt-A@1`, excludes unauthorized records, exposes permitted operations; wrong project/client argv fails visibly without full-history dump |
| B02 | 73-T04/T07/T08: wire task start, relevant edit, failed check, correction and verified outcome to appropriate recall/capture through actual supported events | Public event fixtures produce exact artifact IDs/revisions and write receipts; failed check remains negative evidence; denied capture writes zero; unsupported event is disclosed and never simulated |
| B03 | 73-T04/T05/T08: preserve full continuation through compaction, interruption and handoff | Compact/interrupt→`task_resume` retains goal, constraints, attempted/disproved paths, source identity, unresolved checks and next action under same lineage; replay duplicates no write; stale source requires revalidation |
| B04 | 73-T01/T08: project distinct configured, connected/callable, permitted, context-delivered, evidence-used and verified-write states across agent/human surfaces | `test_receipt_projection_agrees` yields matching CLI/TUI/dashboard stages; registered-only is not active; disabled/denied/failed/unverified states and recovery remain visible |
| E01 | 73-T02/T04: maintain evolving task state with explicit obligation/attempt/evidence relationships, rebuilding bounded current view instead of accumulating summaries | Resume retains active requirements, implemented work, failed attempt and unresolved proof distinctly; correction supersedes only target; unsupported completion claim cannot move failed/unverified obligation to completed |
| E13 | 73-T04/T05/T08: receiving agent reconciles and challenges sender’s work/evidence delta before selecting next necessary action | Deliberately stale proof or omitted obligation is discovered by actual receiver; receiver expands exact refs, identifies missing check and performs required next validation; text delivery/read-back alone does not close continuation |
| E14 | 73-T06/T08: send relevant authorized discoveries at supported event boundaries using interests, source-qualified delta cursors and acknowledged positions | A disproves `attempt-A@2`; B receives exact qualified revision once at next event and avoids duplicate failed experiment; private/unrelated record excluded; no entire-session replay or daemon |
| E15 | 73-T06/T08: reconcile selected knowledge across distinct physical worktrees while preserving branch-specific APIs/results and merge revalidation | Two registered roots keep distinct IDs/stores under approved association; shared requirement survives, conflicting code/check evidence remains worktree/branch/hash-qualified; merge revalidates affected anchors; unrelated repository receives nothing |
| R04 | 73-T05/T08: complete ordinary delta handoff/read-back/replay route using existing restricted transport, not merely component helpers | Public sender→restricted receiver returns exact authorized IDs/versions and read receipt; legitimate replay is idempotent, forged/revoked access fails; real provider continuation performs observable next task action |
| R17 | 73-T05/T08 with Phase72 canonical evidence and Phase74/75 sandbox/context/usage dependencies: complete real-host sandbox→provenance→context→handoff route | Actual sandbox action/check receipt remains revision-qualified through returned context and receiver reconciliation; actual host uses evidence and continues task; complete route usage/cost recorded, unavailable telemetry labeled unknown |
| R20 | 73-T01/T03/T07/T08: complete CLI/MCP/config/docs/installed parity for activation and continuation using shared implementations | Identical valid scope/task inputs produce equivalent CLI/full-MCP evidence; installed resources/config/schema examples work outside checkout; documented supported route is exercised in each claimed host; no checkout-only or configuration-only pass |
| AD01 | 73-T01/T03/T08: replace configured/connected-as-adoption inference with automatic project discovery and observed native bootstrap/use | Fresh real project task never names Rush; installed integration causes genuine discovery/bootstrap and applicable operation; registration, handshake, skill load or coordinator-forced call alone fails adoption gate |
| AD02 | 73-T02/T03: provide discoverable host-to-project authorization and continuation bootstrap without guessing prior session IDs | Setup creates explicit scoped grant/binding; bootstrap consumes it read-only and returns exact permitted IDs; missing/forged/revoked binding returns precise scope recovery with zero unauthorized content or policy writes |
| AD03 | 73-T02/T04/T07/T08: establish permissioned ongoing recall/capture of explicit decisions, corrections and agent outcomes beyond opt-in tool observation | Real UI/architecture decision and correction are persisted with provenance and later recalled; inferred preference remains candidate; failed repair retained; capture denial/failure and last successful write visible |
| AD04 | 73-T01/T03/T08: repair operation-specific prerequisites, typed failure reasons and actionable discovery recovery instead of generic engine-install advice | Missing scope/allowlist yields correct setup/scope action rather than engine installation; emitted examples match accepted schemas; embedded ToolResult error/skipped remains failure even when MCP `isError=false` |
| TC05 | 73-T03/T08: make catalog-backed discovery/bootstrap task-sensitive while preserving mandatory instructions and operation/schema parity | Memory-continuation and test-repair discover exact applicable catalog operations in each claimed host; record retries, aliases, schema/startup tokens and fallback; applicable operation executes successfully without unrelated schemas or fabricated callability |
| TC09 | 73-T04/T05/T07/T08: preserve portable structured continuation while using only verified native compaction mechanisms | Real Claude→Codex and additional requested-host transition retain requirements, failures, workflow and next validation; changed source/stale memory detected; receiving agent acknowledges and resumes without transcript dump or invented automatic injection |
| AP02 | 73-T01/T08: diagnose actual host boundary using full launch/configuration and independently identified installed artifact; preserve reconnect observations | Wrong argv rejected; independent handshake remains exposure-unverified without actual-host receipt; empty config CLI detected; embedded failure, bounded timeout and exact native recovery visible; installed path/digest/version recorded |
| AP03 | 73-T02: implement authorized bounded useful bootstrap through shared MemoryTool/CLI/MCP contracts | Correct grant/project yields known current IDs and expansion refs; wrong worktree, forged binding, revoked grant and unapproved prior session yield no content; tiny budget rejects before extraction/effects; CLI/MCP select identical evidence |
| AP04 | 73-T03/T07/T08: make fresh and existing hosts load canonical usage contract and actually discover/call bootstrap through owned reversible native assets | Normal real-host task without Rush prompt causes genuine bootstrap; packaged examples execute outside checkout; decline writes nothing, repeated upgrade stays single, concurrent edits survive, and resource loading alone grants no capture |
| AP05 | 73-T04/T07/T08: connect task-sensitive recall, source refresh, explicit corrections and permissioned learning to ordinary work | Relevant user-written architecture/UI record appears by exact ID; unrelated preference excluded; correction targets only prior item; failure stays failed, changed anchor refreshes, duplicate event writes once, revoked capture writes zero |
| AP06 | 73-T04/T05/T08: complete public proof-bearing receiving-agent continuation with bounded full semantics, existing restricted bridge and private capability delivery | Sender prepare is not receiver recall; capability stays owned-channel only; forged receipt/exit 0 cannot advance state; valid read yields scoped receipt, checkpoint stays agent-reported, independent task-specific result alone verifies continuation; real host pair resumes correctly |

### Phase 74 — 31 owned IDs

| ID | Packet / concrete planned change | Behavioral oracle |
|---|---|---|
| F16 | T03 routes ordinary user-written and agent project knowledge into review through scoped source policy; T01 supplies graph context | Relevant current artifact/version changes review citations/action; unrelated, stale, rejected and denied records omitted |
| F17 | T03/T04/T09 connect lifecycle producer→trigger→scan/fix/review/suite consumer and expose enabled/disabled/denied/failed capture | Actual failure changes next choice; verified outcome updates version; all mandatory checks retained |
| A05 | T01/T02/T03 populate real AST→symbol-bound memory→public consumer rather than callable graph scaffolding alone | Source edit changes impacted current advice/check and observed action; dynamic coverage remains unknown |
| E02 | T04 competing hypotheses | Actual timeout/payload check receipt refutes only matching hypothesis |
| E03 | T04 remembers conditioned failed strategies and informs next-choice suggestions | Matching failed strategy warned/excluded from suggested next choice; cited changed-condition delta permits justified retry, without inventing execution permission denial |
| E04 | T05 contradiction preservation | Competing evidence retained until discriminating receipt resolves applicability |
| E05 | T02/T03 approved intent/version lineage | Rename candidate reopens checks; old passing result remains historical |
| E07 | T05 contrastive useful pattern | Two independent verified successes plus negative cases narrow applicability; unmatched case abstains |
| E08 | T05 adapted recipe/current helper | Complete current PatchContract/helper adaptation verified; signature mismatch abstains |
| E09 | T01/T03 qualified call context | A.encode/B.encode/nested definitions distinct; dynamic dispatch unknown explicit |
| E10 | T02 dependency traversal | Direct/transitive/cycle traversal terminates; unrelated D current, missing coverage unknown |
| E11 | T02 refactor continuity candidates | Unique structural fingerprint/import move gives candidate; formatting cannot create new verification |
| E12 | T03 full check-obligation union | Intent/repo/schema/security/impacted/dynamic obligations retained; skipped remains unverified |
| E17 | T04 recurrence classification | Code/config/dependency/engine change distinguished from stale receipt |
| E18 | T02/T04 exception re-evaluation | Changed condition reopens advice; original rationale/history retained |
| E20 | T05 consented rehearsal | Real `verify_attempt` fixture pass/fail/timeout/denial; target unchanged, no production-pass promotion |
| E21 | T06 recurring conditional workflows | Two distinct completed originating lineages required; copies/cancelled/suspended/wrong environment excluded |
| E22 | T07 user-controlled skill lifecycle | Draft/accept/edit/reject/CAS/rejection dedupe; pure preview and owned export exactly exercised |
| E23 | T08 selected UI system | Explicit approved references/tokens/components applied by second agent; inferred conflict never authority |
| E24 | T08 architecture lineage | Explicit ADR versus inference distinct; approved affected seam shared by second agent |
| R09 | T02/T03 intent revision binding | Required behavior/checks follow exact current approved intent revision |
| R10 | T04 repair decision changes | Actual next repair action differs based on verified failure evidence |
| R11 | T05 current recipe adaptation | Existing helper/signature exercised, not duplicated or invented |
| R12 | T03 complete required checks | Every mandatory obligation retained despite advice/item budget |
| R13 | T04 last-success delta | Actual last-success versus current condition identifies relevant change |
| R14 | T03/T04 execution receipt capture | Command/result/revision/action link match actual invocation; missing link unverified |
| R15 | T01/T03 graph coverage honesty | Measured versus inferred/API/dynamic unknown distinguished |
| R16 | T03/T04 security/dependency/license evidence | Current relevant engine receipt required; unavailable engine leaves obligation open |
| TC08 | T06/T07/T09 bounded workflows | Max eight procedure steps retains all obligations; cold/first/repeated/negative costs measured |
| TC13 | T03/T09 adapt outcome-ranked advice within applicability, immediately suppress user-corrected advice and retain fixed order | Delivery→action→outcome plus later expansion/correction costs compared held-out; missing link zero, corrections suppressed, contrary/rare evidence retained |
| TC14 | T02/T09 reuse dependency-complete derived analysis with complete source/parser/config/environment/dependency references | Unchanged complete refs avoid repeating discovery; changed/partial/unknown refs stale/unknown; source equality never runtime pass |

### Shared app and PAS outcomes

| Requirement | Exact owning integration | Proposed behavior/check |
|---|---|---|
| AP07 | 72-T07, 73-T08, 74-T08; C06 | Same approved/inferred/history states across CLI, real PTY 80×24 and actual DOM at 1280×800/390×844; keyboard/focus/conflict/no-init/persisted mutation |
| AP08 | 72-T09, 73-T08, 74-T09; C05/C08 | Full frozen gates, installed routes, actual agents/hosts and paired held-out successful-work/cost experiment; all required native lanes remain open until executed |
| PAS01 | 73-T09 producer; 72-T01/T06 consumers | Portable requirements/progress/attempts/checks/source/lineage/next action; digest-bound selected import, loss accounting, pending imported authority |
| PAS02 | 73-T03/T09 | Explicit host instructions bridge; preview no-write, exact original bytes/digest checked, reread proves approved output and current checkpoint |
| PAS03 | 73-T08/T09, 72-T07 | Understandable actual export/import/bridge journeys, correction/conflict/recovery and truthful observed versus claimed state |
| PAS04 | 73-T09 pinned codec, 72-T06 atomic apply | PAS schema-1 required/default/nullable fields and FileStatus exact; paired loss sidecar, contained approved mapping, atomic replay-safe import |

Unnumbered outcomes remain operational requirements: investigations improve decisions (74-T04/T05); persistent workflows and suggested skills (74-T06/T07); selected UI systems/architecture and inferred conventions (74-T08); agent behavior and actual successful-work comparison (73-T08/74-T09); integrated human control (72-T07); app-wide token/context measurement through C05/C08 and retained Phase 75 consumers. Assistant-originated innovation was not substituted for requested baseline features.

## All 27 task packets: implementation entry and acceptance

The linked packet contains exact read set, proposed interface/data shape, ordered changes, completion criteria and handoff. This table records why each task is executable rather than an acceptance wish.

| Task | Concrete implementation entry | Required RED → GREEN / independent check |
|---|---|---|
| 72-T01 | Shared eligibility/read-only store/symbol containment plus authorization consumer | Archive/expiry/integrity/owner/source/root negatives through actual read and expand paths |
| 72-T02 | Strict page/expand request, signed cursor, UTF-8 offsets, dual-budget admission | Actual three-record paging, >512 candidates, corruption/drift/no-progress and minimum-envelope rejection |
| 72-T03 | Relation/summary dependency invalidation in existing stores | Foreign/stale endpoints, cycles, changed member and retained contradiction/history |
| 72-T04 | Current maintenance import/corroboration/preview/apply seams | Fresh-process import, owner-isolated 0/0/1 corroboration and lease/conflict failures |
| 72-T05 | Existing PreferenceStore plus opted-in typed user overlay/migration | Explicit versus inferred authority, scoped expiry, rejection and replay/tombstone |
| 72-T06 | Canonical MemoryTool strict operation dispatch and versioned store mutations/import | All seven subjects, history/explain/correction, atomic multi-record apply, conflicts and no-read init |
| 72-T07 | Existing CLI/TUI/dashboard query/admin adapters | Actual persisted correction, late project refresh, rejected concurrent edit and accessible recovery |
| 72-T08 | Optional hybrid page/candidate evaluator | 48-case matched lexical/metadata/hybrid comparison, unavailable fallback and held-out negative cases |
| 72-T09 | Docs/catalog/help and complete live acceptance | Slow-inclusive suite/type/docs/installed/native/two-agent routes on final revision |
| 73-T01 | Existing discover/probe/agent-readiness implementation | Wrong argv, stale registration, missing installed tool and embedded failure |
| 73-T02 | New authorization metadata APIs consuming existing physical root/CAS/OS lock | No-write missing-policy read; explicit revision-0 two-process grant race; revoke/reconnect |
| 73-T03 | Existing host installer/catalog/instructions paths | Empty-home plus existing install upgrade, restore bytes, real callable operation |
| 73-T04 | Existing episodic write with strict checkpoint/event/lineage schema | Meaningful failure/correction capture; compact/interrupt→resume and explicit cancellation; no duplicate independence |
| 73-T05 | Existing prepare/dispatch/receive plus managed receiver bridge | Private receiver recall versus sender forgery, source/revision expiry and independent continuation result |
| 73-T06 | MemoryTool delta/delta_ack, source mapping configuration, source read-only vector | Physical A/B stores, approved source federation, revocation, cursor/ack CAS and unavailable source without creation |
| 73-T07 | Five exact host-native adapters with capability matrix | Real supported insertion/event fields, failure capture and compact-next-event recovery on each host |
| 73-T08 | Current CLI/TUI/dashboard adoption states plus frozen full gates | Actual unprompted host use, two-way continuation/third pair/offline machine and honest recovery |
| 73-T09 | Canonical capsule action codec/CLI, mapping and explicit bridge | Bounded parse, exact preview digest/UUID, nullable PAS fields, loss sidecar, replay and atomic import |
| 74-T01 | Qualified four-language indexing producer and current graph store/traverser | Duplicate names/TSX arrows/Rust imports/calls; reindex removes stale edges; actual public graph consumer |
| 74-T02 | Graph generations, OS-locked WAL-safe replacement and invalidation outbox | Concurrent writer/crash recovery, source/refactor candidate changes and no stale current verification |
| 74-T03 | Intent/check obligations/learning context in ordinary shared tools | Actual action/receipt linkage, full required-check union, feedback order and missing-link zero |
| 74-T04 | Versioned hypothesis/failure/strategy records and next-choice consumer | Matching receipt refutes one cause, same failed strategy suppressed, changed condition justified |
| 74-T05 | Contrastive patterns/current-helper recipe/rehearsal consumer | Independent success/negative applicability, contradiction preservation, complete patch and actual sandbox verify_attempt |
| 74-T06 | Exact translated lifecycle events and conditional workflow induction | Two distinct originating completed lineages; copied/resumed/cancelled/intervened cases cannot qualify |
| 74-T07 | Proposed pure skill formatter plus existing OwnedResource/AgentConnection export | Approval/edit/reject/version conflict, no-write preview, exact owned export and later failure history |
| 74-T08 | Project contracts/ADR/UI lineage plus existing real TUI/browser adapters | Second-agent approved UI/architecture behavior, true PTY/DOM responsive accessibility and conflicting inferred advice |
| 74-T09 | Reuse evaluator checkpoint and held-out matched experiment/docs gates | Two arms/three seeds/independent task oracle, all costs/failures counted, complete final gates |

Shared API paths are implementation ownership, not permission to write simultaneously. C09 resolves the former 72↔73 cycle using named POLICY → safe-read → BOOTSTRAP checkpoints. Evaluator infrastructure checkpoint may precede the final benefit experiment; no completed-phase cycle is introduced. Phase 75 memory consumer retains Phase 74's fixed advice order/suppression rather than rescoring it.

## Empirical evidence executed during review

Commands below were executed by the assigned review lanes against existing code. No new implementation test files were installed or production defects fixed.

### Existing regression runs

Primary checkout, Python 3.12 project environment with inherited PYTHONPATH cleared:

```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_retrieval.py tests/test_memory_versions.py tests/test_memory_relations.py tests/test_memory_consolidation.py -q --disable-warnings -p no:cacheprovider
```

Observed **50 passed in 5.78s**. This covers selected existing retrieval/version/relation/consolidation behavior at the primary source; it did not catch the four source-probe defects and does not establish developed Phase 70 readiness.

Developed Phase 70 checkout:

```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase70_tui_usability.py::test_t28d_memory_workflows -q --disable-warnings -p no:cacheprovider
```

Observed **1 passed in 1.51s**, at TUI SHA256 `053bfa5f49bff15b0b5804b7519e7b2707534d01318d33cd7ea5bb7169872491`. A subsequent external TUI edit changed that hash; this pass is historical for the changed TUI and is not reused as final current behavioral acceptance.

```sh
rtk proxy env -u PYTHONPATH UV_NO_SYNC=1 uv run --python 3.12 --extra dev --no-sync python -m pytest tests/test_agent_connection.py tests/test_install_memory_activation.py tests/test_phase61_handoff.py -q
```

Observed **54 passed in 3.85s**. Selected existing connection/install/handoff tests pass; wrong-argv/bootstrap probes below expose behavior not established by those tests.

```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_polyglot_codegraph.py tests/test_memory_verify_attempt.py tests/test_memory_public_contract.py -q
```

Observed **74 passed in 9.03s**. An initial command naming nonexistent `tests/test_codegraph.py` failed collection (exit 4); corrected selectors above ran once. No passing claim attaches to that failed collection or to new Phase 74 behavior.

### Actual-function probes

| Probe / reproduction location | Exact expected state | Observed result and implication |
|---|---|---|
| 72 §2.2 runnable fixture uses real recall_page/expand_artifact/resolve_symbol_ref in both checkouts; embedded script SHA256 `34eae561d2305c112b3627fae45da88564cd23133f15195b5cba5ed159058ed7` | `archive_hidden=true, expansion_denied=true, outside_denied=true, paging=true` | All four false, AssertionError: ordinary compact recall leaks archived artifact, expansion accepts it, outside-root reference accepted, limit-2 of 3 claims complete |
| Fresh-process maintenance import | `run_maintenance_cycle` imports successfully | Primary ImportError on partially initialized MaintenanceTask; developed Phase 70 exits 0. Preserve developed repair |
| 73 existing registered-host launch probe | Incorrect argv must not register actual Rush endpoint | Current code reports registered; T01 negative route required |
| 73 actual same-session initialization | Existing observation retained on reconnect | Observed state true→false; T02/T04 reconnect capture repair required |
| Real Git main + peer worktree, actual registration and stores | Distinct stores/IDs, explicitly approved source route needed for B to observe A | `a_record_present=true,b_record_present=false,physical_store_paths_distinct=true,project_ids_equal=false`; exit 0. T06 cannot route only to B's local store |
| Real Phase 70 qualified graph fixture | Qualified calls/paths, TSX arrow nodes, stale records removed after reindex | Duplicate encode nodes 2, CALLS 0, caller paths 0, TSX arrow nodes 0, stale encode after reindex 2 |
| Read-only absent graph/store fixture | No directories created | No directory created for absent read-only view; reuse this existing property |

Temporary fixtures invoked actual repository implementations; arithmetic, mocked status membership and AST/text existence were not used as behavior proof. These results demonstrate why current passing tests do not close the proposed defects.

### Required future final gates

Each phase's final packet retains the following commands and relevant native/installed/agent/behavioral tests. They were **not run as a final whole-phase gate by this review**:

```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m ""
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk git diff --check
```

Python version must be 3.12. New task-specific tests require their exact implementations and realistic fixtures first. Native hosts, installed artifacts, browser downloads, PTY accessibility, measured cost/benefit and independent continuation require their actual environment; unavailable evidence remains an exact open acceptance item, never substituted with source/lint checks.

## Primary-source research and resulting interface corrections

Host documentation is protocol evidence, not proof a host journey executed:

| Primary source | Verified contract used |
|---|---|
| [Claude Code hooks](https://code.claude.com/docs/en/hooks), [MCP](https://code.claude.com/docs/en/mcp) | Supported lifecycle/failed-tool events and hook-specific context insertion |
| [Codex hooks](https://learn.chatgpt.com/docs/hooks), [MCP](https://developers.openai.com/codex/mcp/) | SessionStart startup/resume/clear/compact additionalContext; PreCompact stdout cannot be claimed inserted; refresh on supported subsequent event |
| [Cursor hooks](https://prod.cursor.com/docs/hooks) | SessionStart additional_context is fire-and-forget, not blocking bootstrap; preCompact user_message does not replace model context |
| [Antigravity hooks](https://antigravity.google/docs/hooks?tab=ide) | PreInvocation injectSteps.ephemeralMessage; Stop decision stop and outstanding/fullyIdle state; no invented compact event |
| [ZCode hooks](https://zcode.z.ai/en/docs/hooks) | Plugin hooks rather than ignored project setting; supported SessionStart/failed-tool payload fields |
| [Pinned PAS SessionContext schema](https://github.com/gfirik/pas-agent/blob/0c9515a6ec9bb32c3f33a93b3f981e283d211abd/crates/pas-agent-core/src/session.rs) | Required/default/nullable Option fields and FileStatus; no invented stronger schema-1 requirement |
| [tree-sitter Rust package](https://pypi.org/project/tree-sitter-rust/0.24.2/), [Python binding](https://github.com/tree-sitter/py-tree-sitter) | Pinned grammar availability/wheels and actual Parser/Language API; installed four-language ABI probe remains required before release |

Browser verification contract uses available `mcp__cua_repl.js` tab Playwright DOM methods and viewport capability. API documentation was checked in an isolated blank tab, then closed; no dashboard journey, responsive acceptance or screenshot was claimed. Required T08 real DOM/native outcomes remain in the plan.

## Provenance, drift and preservation

Parent integration compared 27 named developed source fingerprints with lane receipts: 26 stayed byte-identical; TUI changed externally and received the bounded affected-plan recheck recorded below. Project identity probe additionally uses `src/rush/workflows/projects.py`. Selected fingerprints are included for reproducibility; a hash establishes bytes, not behavior.

| Developed source, relative to Phase 70 checkout | SHA256 at reviewed receipt |
|---|---|
| src/rush/memory/store.py | `0caea9fc34dbc6bfe88c47f1bb0d1b3e98ad073443e8ed9ca459f4e1d6eb4e23` |
| src/rush/memory/retrieval.py | `17146721dfc36cd22538dc07735b97a7f20abcceb0fc96c76c9720cff66079f1` |
| src/rush/mcp_support/request_models.py | `ab1670f474b06aa61cd3a9459650811caa4171bdfb5206020edb3efc36705750` |
| src/rush/memory/transactions.py | `be9041dc1f804feabdedc455d69b480e46cb99b52a447da7258f5974444e5a3b` |
| src/rush/dashboard/state.py | `e87c314dfdd95fab6bd8588e3f301ae918deecfb7035206112fd2d9926eae1c0` |
| src/rush/workflows/projects.py | `41feec73bef3d4aff7570ebf9c4aebeae1a647261e66373fd6c16e62a899f511` |
| src/rush/codegraph/store.py | `f006f3ded9edd774aa7fd56075ef28f3f4e12512f2750264aff593332cc13fc7` |
| src/rush/codegraph/python_ast.py | `2cc68e5b2efd9f09d0155f51de620e59d27b95159ec38eaeebb3a6f0e5540edf` |
| src/rush/codegraph/tree_sitter_poly.py | `038fecc40dc10a469c5631519b702746e334b94ccab703a0b0a199f9883fb13d` |
| src/rush/tui.py, final external development snapshot | `249d775dce4ca4e3a2e63e7a93cd18a7701bee2e31b16f8d00efd9f3325ab9a3` |

Affected TUI rereview verified the final hash unchanged at start/end. Current reuse spans: `_memory_refresh` 3173–3226, `_memory_clear_held` 3229–3238, `_memory_held_for_other_project` 3241–3256, `_memory_submit` 3276–3317, `_apply_memory_result` 3320–3346, `_memory_list_kwargs` 3380–3397, `_memory_edit_commit` 4308–4355, conflict recovery 4358–4423, `_handle_memory_key` 4426–4588, project switch 5695–5726 and `_render_memory_admin` 7521–7703. Held-preview clearing, exact ID/version/owner/grants, project guards, filter refresh and late-result rejection remain valid reuse targets for 72-T07/73-T08/74-T08. Those plans cite symbols rather than frozen TUI line numbers, so no plan amendment was necessary. This affected-source review establishes planning alignment only; it did not rerun Phase 70 acceptance.

Preserved reference checks:

| Unmodified input | SHA256 |
|---|---|
| Primary Phase 70 plan | `f13ba50a34326b524bcfe746f522125e3f1717db2d8bad4ae19181f2f2d2eeac` |
| Phase 71 plan | `d6f2e9dbd6cca08aa0f45abf908c7f4cee688e4c427359a97c0c527b943b3339` |
| Phase 75 plan | `6e8cee335b280cc71fc1d2d26bcacd61b990c7977b2799165203223847e7d63e` |
| Source memory review | `c256b70e28c6d6209ec21ea205c49caa39b0e351d41143fc3e75b451a5c8779a` |
| Source PAS comparison | `f2a3c437bf93baf5b399fe6fe3221ce9a99e081e830acf61132e760f9bc64a2a` |

Initial plan hashes before corrections: 72 `79f5b1740199e8258e1751d5ec6d46bd2be4f96117368c23c746d5b15267dff5`; 73 `e57e5a1ef04d568905dd5a17e00e3368d833c2ffe1a7c6f02aa54ea9402a59c3`; 74 `3583b00556fb86a19a96ac16c4c2176a0db4c03a69d0a70f9cbc9a9ecf2db5e4`; shared `29fc0380b4fe13aea27a8c36876c1be5792bbf64e41c617c3e7aa510ea9e7887`. Those verdicts are superseded. Correcting identified defective content did not authorize deleting valid surrounding requirements.

## Handoff conditions

No remaining user decision blocks these plan specifications. Full scope, negative cases, exact interfaces, file ownership, dependencies, recovery and verification now reside in the authoritative plans.

Implementation starts only under the existing Phase 70 priority and named C09 checkpoints, with live source reread/reservation for every touched dirty/shared file. It must implement every retained requirement and execute the task's real behavior checks before claiming completion. Existing passing regression tests, this review report, native protocol documentation and frozen plan hashes cannot substitute for that acceptance.
