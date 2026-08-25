# Rush five-phase live execution plan

Resolved target path: docs/reports/rush-unified-agent-intelligence-development-plan.md  
Status: execution manual only; this document does not implement a feature.

## 1. Plan-level goal and completion contract

### Overall development goal

Deliver a local, privacy-controlled continuity capability that lets Rush users and coding agents save, inspect, validate, compact, hand off, and safely resume repository work through the same ToolResult-backed CLI and stdio MCP contract.

### Why this matters

Users lose work when a session or provider changes. Agents repeat repository discovery, reuse stale test assumptions, consume unnecessary context, and can leak secrets or treat historic instructions as current authority. The repository needs inspectable provenance, bounded recovery, local-first privacy, deterministic token control, CLI/MCP parity, and safe coordination without a hosted agent platform.

### Final observable outcome after Phase 5

A user can create an approved redacted continuity handoff, inspect its current frontier and evidence, retrieve a bounded context envelope with recovery handles, resume it through an approved provider route, and see structured skipped behavior when a capability is unavailable. An agent can discover the same state through MCP, prove a closure with fresh receipts, detect stale or conflicting work, and never receive provider credentials or historic instruction as live authority.

### Plan-level definition of done

- All five phase checklists, work packages, atomic tasks, documentation audits, backlog updates, issue updates, verification runs, diff reviews, and phase commits are complete.
- Every public CLI/MCP operation uses a shared src/rush/tools implementation and canonical ToolResult with tool, engine/version, status, duration, summary, and findings.
- Existing session, checkpoint, failure, token, context, lock, replay, and provider surfaces are connected only through approved contracts and preserve redaction, permissions, provenance, invalidation and skipped behavior.
- Benchmark-gated choices have completed decision records in docs/reports/rush-benchmark-plan.md; no uncertain dependency, model, runtime, provider, router, or protocol is treated as approved.
- Required configuration/migration state is documented; no raw secret, credential, transcript by default, or historic provider instruction is persisted as current authority.
- The canonical backlog and issue files are reconciled, every completed item has its phase commit, deferred work is explicit, and no blocker is hidden.
- Each phase has one reviewed, tested, documented commit and no do-not-touch file changed.

### Live plan-level checklist

- [ ] PL-01 All five phase definitions of done are verified.
- [ ] PL-02 Benchmark gates required by implemented tasks have decision records.
- [ ] PL-03 Full tests and Ruff commands pass from the project interpreter.
- [ ] PL-04 Every docs/ audit is recorded and all required updates are complete.
- [ ] PL-05 Backlog, issues, worktree review, and five commits are reconciled.
- [ ] PL-06 Final privacy, provenance, invalidation, skipped-capability and token evidence is recorded.

## 2. Operating rules for every phase

### Worktree, commit, and scope discipline

Before each phase, verify repository/worktree state; use a dedicated worktree and one branch only. Current checkout availability is a prerequisite: if Git worktree creation cannot be verified, open a blocking local issue and do not initialize, rewrite history, tag, publish, or alter versions. Preserve unrelated changes by working only in the phase worktree and by reviewing the final diff against the allowed-file list.

Every phase ends only after: task checklists are current; required tests/quality commands pass; docs/ inventory is audited; backlog and issue records are reconciled; allowed-file review passes; and one clean commit is made. Commit format: feat(continuity-pN): short outcome, except docs(continuity-pN): when a phase only changes documentation.

### Required TDD order

For every behavior-changing task:

1. [ ] Add the smallest focused test.
2. [ ] Run it and record the expected red failure in docs/developer/issues.md.
3. [ ] Make the smallest implementation change.
4. [ ] Re-run focused and neighboring tests.
5. [ ] Refactor only while green.
6. [ ] Update task checklist, backlog and issue state.
7. [ ] Run phase verification before commit.

Use:

    unset VIRTUAL_ENV PYTHONPATH
    .venv/Scripts/python.exe -m pytest tests/ -q
    .venv/Scripts/ruff.exe check src tests scripts
    .venv/Scripts/ruff.exe format --check src tests scripts

### Mandatory token-efficient discovery and verification matrix

Every T00 must execute and record commands from all three tool surfaces. **RTK file and code discovery:** `rtk find -name PATTERN`, `rtk tree PATH`, `rtk ls PATH`, `rtk grep PATTERN PATH` (or `rtk rg PATTERN PATH` where ripgrep semantics matter), `rtk read --line-numbers PATH`, and `rtk smart PATH` only for an orientation summary. **RTK repository and quality evidence:** `rtk git status --short`, `rtk git diff`, `rtk diff`, `rtk log`, `rtk pytest …`, `rtk ruff …`, `rtk format …`, and `rtk uv …` as applicable. Use `rtk err`, `rtk test`, `rtk json`, `rtk deps`, and `rtk env` only for their stated error, test, structured-output, dependency, and environment evidence. Do not use `rtk run` or `rtk proxy` for discovery because they bypass filtering. The installed RTK command is `find` for file discovery; no `rtk glob` subcommand is present in its help.

**Graft graph discovery:** `graft check .` first; `graft build .` only if the graph is absent or stale and the T00 record authorizes local derived state; `graft map .` for orientation; `graft skeleton FILE .` for a file API; `graft grep PATTERN .` for indexed symbol-grouped search; `graft callers SYMBOL .` for callers/callees; and `graft ask QUERY .` only when the result is linked back to exact file:line evidence. `graft mcp`, `graft init`, `graft viz`, `graft upgrade`, and `graft --api-key` are outside this plan.

**Context-mode retrieval:** `context-mode doctor` first; `context-mode index PATH --project . --ext .py,.md` to create or refresh the bounded FTS5 project index; `context-mode search QUERY --project . --source LABEL --type code|prose --limit N` to retrieve selective evidence; and `context-mode` only when the stdio MCP server is explicitly being exercised. `context-mode upgrade`, `context-mode hook`, and `context-mode statusline` are outside this plan. T00 records the exact command, scope, and reusable source references; refresh after an allowed source file changes.

Derived Graft and context-mode state is local to the phase worktree and is never committed unless an explicit task authorizes it. Neither tool substitutes for repository evidence; do not use compression to hide evidence needed for review.

### Continuous backlog and issue workflow

Canonical backlog: docs/developer/backlog.md. Canonical issue tracker: docs/developer/issues.md.

Backlog fields required for this program: Backlog ID, title, status, priority, planned phase, related task IDs, dependencies, user/agent value, priority reason, deferral rationale, linked issue IDs, linked commit. Issue fields: Issue ID, title, status, severity/impact, discovery phase/task, evidence, affected files/capabilities, owner role, blocking status, proposed resolution, related backlog ID, test coverage, resolution commit or deferral decision.

At phase start mark scheduled work active and confirm blockers. Before an atomic task recheck priority/blocking state. After it mark completed, blocked, deferred, split or superseded and record new work/defects/conflicts/security concerns. Before and after commit reconcile task checklist, IDs, commit, deferrals and blocking issues. The backlog tracks future priority; this plan is the sequence; issues record defects/blockers/decisions.

## 3. Five-phase overview

| Phase | Beginning goal | Entry criteria | User and agent outcome | End outcome | Worktree / branch | Required commit |
|---|---|---|---|---|---|---|
| 1 Shared execution contract and live control | Give existing session/context entry points shared ToolResult, permission and tracking discipline. | Clean dedicated worktree; no unresolved scope blocker. | User receives consistent structured results; agent can invoke parity-tested tools and read live trackers. | Shared tool seam and canonical tracker schema exist. | ../rush-cli-continuity-p1 / codex/continuity-p1-contract | feat(continuity-p1): establish shared continuity contract |
| 2 Provenance-aware handoff | Make existing session/checkpoint evidence inspectable, redacted, stale-aware and authority-labeled. | P1 commit; BG-AUTH and BG-PRIV decision records for any persisted schema. | User saves/restores bounded state; agent sees current evidence, not raw historic instruction. | Receipts/failure/invalidation evidence participates in handoff. | ../rush-cli-continuity-p2 / codex/continuity-p2-handoff | feat(continuity-p2): add provenance-aware handoff |
| 3 Grounded context envelope | Produce a bounded, recoverable evidence envelope from existing context/token components. | P2 commit; BG-CTX approved; BG-RET/BG-LOCAL only if optional semantic path is selected. | User receives inspectable context budget result; agent gets selected IDs and recovery handles. | Deterministic envelope and token telemetry are parity-tested. | ../rush-cli-continuity-p3 / codex/continuity-p3-context | feat(continuity-p3): add grounded context envelope |
| 4 Coordination and recovery | Connect existing locks, replay and failure signals to explicit handoff ownership/recovery. | P3 commit; BG-COORD for new protocol semantics. | User sees conflicts/stale work; agents coordinate or recover without silent overwrite. | Local coordination/replay state is evidenced and bounded. | ../rush-cli-continuity-p4 / codex/continuity-p4-coordination | feat(continuity-p4): add coordination recovery evidence |
| 5 Approved interoperability | Add only benchmark-approved named provider/CLI routes and complete operational hardening. | P4 commit; BG-PROV per route, BG-9R/BG-OMNI where applicable, BG-PROTO for renderer/import. | User deliberately selects an approved route; agent sees capability/provenance/skipped state. | Cross-provider handoff is explicit, redacted, documented and hardened. | ../rush-cli-continuity-p5 / codex/continuity-p5-adapters | feat(continuity-p5): add approved continuity adapters |

## 3A. Exact required documentation updates by phase

These are the documents that must be changed when the corresponding phase ships. Their row in the audit matrix is **U-Pn**. No other document may be marked updated merely because it was read; any newly affected document requires a linked issue explaining the new effect and a matrix amendment.

- **P1 — contract and controls:** docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/API_REFERENCE.md; docs/CLI_REFERENCE.md; docs/CLI_COOKBOOK.md; docs/MCP.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/CONFIG_SCHEMA.md; docs/JSON_SCHEMA.md; docs/TOOL_CATALOG.md; docs/DEVELOPER_GUIDE.md; docs/TESTING.md; docs/TROUBLESHOOTING.md; docs/reference/cli-reference.md; docs/reference/configuration-reference.md; docs/reference/mcp-tool-reference.md; docs/reference/result-reference.md; docs/developer/architecture.md; docs/developer/configuration-development.md; docs/developer/mcp-development.md; docs/developer/coding-standards.md; docs/developer/testing-guide.md; docs/developer/tool-development.md; docs/integrations/ci-overview.md; docs/integrations/mcp-client-setup.md; docs/developer/backlog.md; docs/developer/issues.md; this plan.
- **P2 — handoff evidence:** docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/API_REFERENCE.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/JSON_SCHEMA.md; docs/PRIVACY.md; docs/SECURITY.md; docs/SAFETY.md; docs/LIMITATIONS.md; docs/TROUBLESHOOTING.md; docs/user-guide/working-with-ai-agents.md; docs/user-guide/security-and-supply-chain.md; docs/user-guide/troubleshooting.md; docs/agentic-rush/patch-remediation-and-memory.md; docs/agentic-rush/anti-hallucination.md; docs/architecture/rush-epistemic-memory-and-agent-substrate.md; docs/safety/privacy-and-data-handling.md; docs/safety/security-model.md; docs/safety/safety-overview.md; docs/reference/result-reference.md; docs/developer/debugging-guide.md; docs/developer/backlog.md; docs/developer/issues.md; this plan.
- **P3 — context envelope:** docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/API_REFERENCE.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/JSON_SCHEMA.md; docs/agentic-rush/token-economy-and-context.md; docs/agentic-rush/token-efficiency.md; docs/workflows/context_packing_and_budgeting.md; docs/specs/context-compression-and-recovery-spec.md; docs/specs/prompt-cache-alignment-spec.md; docs/specs/stale-sweeper-spec.md; docs/specs/telemetry-ledger-spec.md; docs/architecture/rush-epistemic-memory-and-agent-substrate.md; docs/safety/privacy-and-data-handling.md; docs/reference/result-reference.md; docs/user-guide/working-with-ai-agents.md; docs/user-guide/understanding-results.md; docs/user-guide/troubleshooting.md; docs/developer/backlog.md; docs/developer/issues.md; this plan.
- **P4 — coordination/recovery:** docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/API_REFERENCE.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/JSON_SCHEMA.md; docs/SECURITY.md; docs/SAFETY.md; docs/TROUBLESHOOTING.md; docs/workflows/multi_agent_mesh_and_traceability.md; docs/workflows/bi-temporal-mistake-pre-mortem.md; docs/specs/flight-recorder-spec.md; docs/specs/swarm-3way-ast-merge-spec.md; docs/agentic-rush/codebase-hygiene-and-ast-merging.md; docs/agentic-rush/patch-remediation-and-memory.md; docs/agentic-rush/ai-safety-and-sandboxing.md; docs/safety/security-model.md; docs/safety/safety-overview.md; docs/reference/result-reference.md; docs/user-guide/working-with-ai-agents.md; docs/user-guide/troubleshooting.md; docs/developer/backlog.md; docs/developer/issues.md; this plan.
- **P5 — interoperability:** docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/API_REFERENCE.md; docs/CLI_REFERENCE.md; docs/CLI_COOKBOOK.md; docs/MCP.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/CONFIG_SCHEMA.md; docs/INTEGRATIONS.md; docs/COMPATIBILITY.md; docs/ENGINE_COMPATIBILITY.md; docs/PRIVACY.md; docs/SECURITY.md; docs/SAFETY.md; docs/integrations/mcp-overview.md; docs/integrations/mcp-client-setup.md; docs/reference/cli-reference.md; docs/reference/configuration-reference.md; docs/reference/mcp-tool-reference.md; docs/reference/compatibility.md; docs/reference/result-reference.md; docs/safety/permissions.md; docs/safety/privacy-and-data-handling.md; docs/safety/security-model.md; docs/user-guide/working-with-ai-agents.md; docs/user-guide/security-and-supply-chain.md; docs/developer/mcp-development.md; docs/developer/configuration-development.md; docs/developer/backlog.md; docs/developer/issues.md; this plan.

## 4. Phase execution packages

### Phase 1 — shared execution contract and live control

Beginning goal: establish one parity-tested, permission-aware continuity tool boundary and bring the existing local trackers to the required live schema.

Entry criteria: worktree exists from execution-time base revision; T00 compact context exists; no unrelated diff is included. In scope: shared tools, catalog/CLI/MCP/config parity and tracker schema. Deferred: persistence redesign, model/provider work, benchmarks, hooks, UI. Do-not-touch: pyproject.toml, uv.lock, rush.toml, release/version files.

Dependency graph: P1-T00 -> P1-WP1 -> P1-WP2 -> P1 verification -> P1 commit.

Checklist:

- [x] P1-T00 token-efficient discovery completed.
- [x] P1-WP1 shared contract package complete.
- [x] P1-WP2 tracker/workflow package complete.
- [x] P1-DOC full docs audit complete.
- [x] P1-BI backlog/issues reconciled.
- [x] P1-V verification complete.
- [x] P1-C commit recorded.

P1-WP1 — shared continuity command contract  
Goal: move only the selected existing session/context wrappers to one ToolResult-backed implementation seam. Why now: every later phase needs CLI/MCP parity. Dependencies: P1-T00. Deliverable: approved shared implementation registration and parity tests. Stop: an existing registry/config pattern cannot represent the capability without breaking compatibility.

P1-T00 — discovery and context record  
Objective: use verified rtk discovery to map session/context wrapper symbols, tests, catalog and docs before edits. Preconditions: clean worktree. Before: context is dispersed. After: compact findings record is linked from backlog entry BL-P1-00. Allowed: docs/developer/backlog.md, docs/developer/issues.md. Do-not-touch: src/, tests/, configuration. New files: none. Symbols: cli.py session/context wrappers, mcp.py _register_tools, tools/base.py. TDD: none; discovery only. Negative case: a stale graph or unavailable local index is recorded as unavailable evidence; use repository paths/tests rather than inventing syntax. Docs: record audit start. Backlog: mark BL-P1-00 complete. Issue: no issue unless unavailable command. Verify: rtk git status --short; rtk grep session_memory src tests; rtk read --line-numbers src/rush/tools/base.py. Accept: reusable path/symbol evidence exists. Non-goal: implementation. Checklist: P1-T00.

P1-T01 — ToolResult continuity seam  
Objective: add the smallest shared tool seam for existing session/context operations. Preconditions: T00. Before: direct CLI/MCP wrappers have transport-specific results. After: selected operation reaches one src/rush/tools implementation and returns ToolResult. Allowed: src/rush/tools/__init__.py, src/rush/tools/continuity.py, src/rush/catalog.py, src/rush/cli.py, src/rush/mcp.py, tests/test_cli_registry.py, tests/test_mcp.py. Do-not-touch: providers/, token_economy/, pyproject.toml. New: src/rush/tools/continuity.py only after T00 confirms no equivalent. Symbols: ToolFn, ToolResult, ALL_TOOLS, TOOL_SPECS, _run_tool, _register_tools. TDD first: focused CLI/MCP parity test; initial failure is no registered ToolFn/shared canonical result. Implement: minimal operation, catalog registration, thin transports. Refactor: only transport duplication in touched wrappers. Negative: missing capability returns skipped; MCP stdout stays clean. Docs: CLI/MCP reference update in phase audit. Backlog: BL-P1-01. Issue: ISS-P1-01 only for incompatibility. Verify: focused pytest selectors confirmed by pytest collection, then full suite/Ruff. Accept: parity and skipped tests green. Non-goal: new provider or persistence. Checklist: P1-WP1 and P1-T01.

P1-T02 — permission/config/catalog contract  
Objective: attach ExecutionPermissions metadata and strict opt-in configuration only if required by the confirmed seam. Preconditions: P1-T01 green. Before: continuity has no governed capability declaration. After: permissions/config/catalog agree. Allowed: src/rush/config.py, src/rush/permissions.py, src/rush/catalog.py, src/rush/tools/continuity.py, tests/test_config.py, tests/test_permissions.py. Do-not-touch: rush.toml, dependencies, provider files. New: none. TDD: config rejects unsafe/unknown field and permission denial returns structured result; initial failure absent contract. Implement minimal parser/catalog changes. Refactor only contract-local helpers. Negative: absent config stays disabled/skipped. Docs: configuration/reference update. Backlog BL-P1-02; issue only if config compatibility conflicts. Verify focused tests, full suite/Ruff. Accept: tests prove disabled default and denied permission. Non-goal: credential storage. Checklist: P1-WP1/P1-T02.

P1-WP2 — canonical tracker and phase controls  
Goal: extend, do not replace, canonical backlog/issues with program fields and current five-phase rows. Why now: live execution cannot start without honest state. Dependencies: P1-WP1. Deliverable: documented schemas and active Phase 1 records. Stop: historical tracker content would be overwritten rather than preserved.

P1-T03 — tracker schema and lifecycle records  
Objective: add the required program tables/fields and P1 records to existing trackers. Preconditions: P1-T02. Before: historical milestone tables lack live fields. After: required backlog/issue fields and five-phase program records coexist with history. Allowed: docs/developer/backlog.md, docs/developer/issues.md, docs/reports/rush-unified-agent-intelligence-development-plan.md. Do-not-touch: all source/config/test files. New: none. TDD: documentation structural assertion only if an existing docs-parity test can be extended; otherwise no behavior test. Negative: no hosted issue creation; historical entries unchanged. Docs: document workflow in this plan. Backlog BL-P1-03; issue ISS-P1-TRACK only if migration ambiguity. Verify Markdown link/format audit and git diff --check. Accept: every mandated field exists and P1 records link task IDs. Non-goal: duplicate tracker creation. Checklist: P1-WP2/P1-T03.

Phase definition of done: P1 tasks/checklists green, tracker schema live, permitted docs updated/audited, full test/Ruff passes, allowed-file diff reviewed, commit recorded. Rollback: revert only the phase commit; disabled continuity config remains skipped.

### Phase 2 — provenance-aware session handoff

Beginning goal: turn existing session/checkpoint/failure state into explicit redacted evidence with authority and stale-state behavior. Entry: P1 commit plus passed BG-PRIV. BG-AUTH is deliberately produced by P2-T01’s red/green authority test before P2-T02; B-D01 is not an authority gate because B1 proves only harness foundations. In scope: SessionMemoryManager, CheckpointJournal, FailureLedger, MerkleInvalidator, SecretRedactor adapters. Deferred: transcript import, semantic model, provider rendering. Allowed source: src/rush/session_memory.py, src/rush/memory/checkpoint_journal.py, failure_ledger.py, merkle_invalidator.py, invariant_graph.py, src/rush/safety/redactor.py, src/rush/tools/continuity.py; named tests below. Do-not-touch: provider adapters, dependencies, external accounts.

Checklist: [x] P2-T00 discovery [x] P2-WP1 evidence contract [x] P2-WP2 save/restore integration [x] P2-DOC audit [x] P2-BI reconciliation [x] P2-V checks [x] P2-C commit.

P2-WP1 — redacted authority and freshness records  
P2-T00: create compact rtk findings for session/checkpoint/failure symbols and refresh if touched files change; allowed tracker files only; verify rtk grep SessionMemoryManager src tests and rtk read --line-numbers source; run `graft check .` and `context-mode search SessionMemoryManager --project .`; record any stale/unavailable derived index as non-authoritative; checklist P2-T00.  
P2-T01: test first that saved handoff excludes a synthetic secret, labels historic instruction as evidence, and detects changed dependency. Preconditions BG-PRIV and T00. Allowed src/rush/session_memory.py, src/rush/memory/checkpoint_journal.py, failure_ledger.py, merkle_invalidator.py, safety/redactor.py, tools/continuity.py, tests/test_session_memory.py, tests/test_phase41_memory_ship.py. Do-not-touch providers/token runtime. New files none unless T00 creates a fixture under existing tests/fixtures/ path. Initial failure: no redaction/authority/stale receipt in output. Implement smallest provenance fields/adapters; refactor only touched persistence code. Negative: raw transcript remains absent; missing evidence is explicit; secret is never stored/logged. After green, write passed BG-AUTH from the focused replay/tombstone/instruction-quarantine evidence. Docs: privacy, user agent workflow, result reference as audit directs. Backlog BL-P2-01; issue ISS-P2-01 if schema migration is unsafe. Verify focused tests/full suite/Ruff. Accept: redaction, quarantine and stale cases green. Checklist P2-WP1/P2-T01.

P2-WP2 — inspectable save/restore receipts  
P2-T02: test first that save/restore reports current goal, receipts, failed attempt pointer and open work without claiming completion. Preconditions P2-T01 and passed BG-AUTH. Allowed same P2 source plus cli.py/mcp.py only through P1 seam, tests/test_session_memory.py and tests/test_phase41_memory_ship.py. Do-not-touch catalog/config unless P1 contract cannot expose a required result field. Initial failure: restore lacks bounded receipt/frontier behavior. Implement minimal adapter and ToolResult findings. Negative: unavailable record returns skipped/not-found; no auto migration of historic summaries. Docs: CLI/MCP/session/privacy reference. Backlog BL-P2-02; issue only new defect/blocker. Verify focused/full/Ruff. Accept: user and MCP retrieve equivalent redacted handoff. Checklist P2-WP2/P2-T02.

P2 definition of done: users can save/restore an inspectable redacted handoff, agents receive authority/freshness evidence, and no raw secret or historic instruction becomes current authority. Commit after docs/ audit, tracker reconciliation and verification. Recovery: disable the new operation; existing checkpoint format remains readable.

### Phase 3 — grounded context envelope and token controls

Beginning goal: create one deterministic, evidence-carrying context result from existing pack/recovery/token components. Entry: P2 commit and BG-CTX decision; BG-RET/BG-LOCAL only for optional semantic/model work, which remains deferred unless approved. In scope: ContextPacker, ContentRouter, AstSkeletonizer, CCRStore, CacheAligner, StaleSweeper, TelemetryStore, GroundingVerifier/HalluGuard through P1 seam. Deferred: model download, index adoption, benchmark execution, provider trial.

Checklist: [x] P3-T00 discovery [x] P3-WP1 envelope [x] P3-WP2 recovery/telemetry [x] P3-DOC audit [x] P3-BI reconciliation [x] P3-V checks [x] P3-C commit.

P3-WP1 — deterministic selected-context result  
P3-T00: rtk-map packer/token/grounding symbols and source sections; record reused evidence/refresher rule; run `graft check .` and `context-mode search ContextPacker --project .`; record any stale/unavailable derived index as non-authoritative; checklist P3-T00.  
P3-T01: test first that a requested budget returns selected evidence IDs, actual/estimated token fields, mandatory omission reason, and recovery handle or insufficient-budget. Preconditions BG-CTX. Allowed src/rush/codegraph/context_packer.py, src/rush/token_economy/router.py, ccr_store.py, cache_aligner.py, stale_sweeper.py, telemetry.py, src/rush/tools/continuity.py, tests/test_phase43_ccr_grounding.py, tests/test_phase44_context_pack_cache.py. Do-not-touch model/provider/dependency files. Initial failure: existing pack result lacks provenance/omission contract. Implement adapter only; do not duplicate store. Negative: mandatory overflow fails closed; secret-bearing input follows redaction policy. Docs: context/token/result reference. Backlog BL-P3-01; issue on estimator ambiguity. Verify focused/full/Ruff. Accept: deterministic envelope tests green. Checklist P3-WP1/P3-T01.

P3-WP2 — recovery and token telemetry  
P3-T02: test first that omitted context is retrievable by stable CCR handle and savings telemetry does not claim unmeasured provider cost. Preconditions P3-T01. Allowed CCRStore, TelemetryStore, tools/continuity.py, tests/test_phase43_ccr_grounding.py, tests/test_phase45_telemetry_gain.py. Do-not-touch external index/model paths. Initial failure: omission cannot be recovered or telemetry lacks provenance. Implement smallest result metadata; refactor only telemetry adapter. Negative: missing handle returns structured not-found/skipped. Docs: token workflow/troubleshooting. Backlog BL-P3-02; issue only new failure. Verify focused/full/Ruff. Accept: recovery and accounting assertions pass. Checklist P3-WP2/P3-T02.

P3 definition of done: deterministic context is inspectable/recoverable/redacted; token claims are evidence-backed; optional semantic/model work remains blocked until gate decision. Recovery: keep existing pack command, disable envelope registration.

### Phase 4 — coordination and failure recovery

Beginning goal: make local ownership, stale work, replay and known failures visible during handoff. Entry: P3 commit; BG-COORD for any new protocol semantics. In scope: MeshLockManager, SwarmMergeSolver, FlightRecorder, FailureLedger, MerkleInvalidator, MistakeMiner. Deferred: daemon, auction, auto-merge authority, external protocol.

Checklist: [x] P4-T00 discovery (RTK proxy limitation and unavailable context-mode query recorded; source/test evidence used) [x] P4-WP1 ownership/staleness [x] P4-WP2 replay/recovery [x] P4-DOC audit [x] P4-BI reconciliation [x] P4-V checks [x] P4-C completion commit.

P4-WP1 — ownership and conflict evidence  
P4-T00: create rtk finding of lock/merge/recorder/failure paths and tests; refresh after any source change; run `graft check .` and `context-mode search MeshLockManager --project .`; checklist P4-T00.  
P4-T01: test first that acquisition conflict, expired/stale evidence, and merge conflict produce structured handoff findings rather than overwrite. Preconditions BG-COORD only for new protocol form. Allowed src/rush/mcp_mesh/lock_manager.py, src/rush/tools/swarm_merge.py, src/rush/memory/merkle_invalidator.py, src/rush/tools/continuity.py, tests/test_phase49_trace_swarm_recorder.py. Do-not-touch provider/model/config/dependencies. Initial failure: handoff cannot surface ownership/conflict. Implement adapter; no daemon. Negative: lock failure returns unavailable/conflict; no automatic merge. Docs: coordination/workflow/security. Backlog BL-P4-01; issue ISS-P4-01 on conflict semantics. Verify focused/full/Ruff. Accept: conflict/staleness assertions green. Checklist P4-WP1/P4-T01.

P4-WP2 — replay and failure receipt  
P4-T02: test first that known failure and replay pointer are presented as evidence and never as a command to execute. Preconditions P4-T01. Allowed src/rush/tools/flight_recorder.py, src/rush/memory/failure_ledger.py, mistake_miner.py, tools/continuity.py, tests/test_phase49_trace_swarm_recorder.py, tests/test_mistake_miner.py. Do-not-touch CLI/MCP except P1 seam. Initial failure: attempt/failure state is unlinked. Implement bounded receipt adapter. Negative: missing recorder returns skipped; historic failed patch is not retried automatically. Docs: recovery/troubleshooting. Backlog BL-P4-02; issue on corrupt record. Verify focused/full/Ruff. Accept: replay/failure tests green. Checklist P4-WP2/P4-T02.

P4 definition of done: handoff exposes owner/conflict/stale/replay/failure evidence; agents cannot silently overwrite or auto-retry. Recovery: disable coordination view and retain existing lock/merge behavior.

### Phase 5 — approved interoperability and hardening

Beginning goal: add named provider routes under one permission/redaction/provenance contract. The implementation inventory is fixed: Claude Code, Codex CLI, Antigravity (`agy`), 9Router CLI/gateway, and OmniRoute CLI/API are enabled routes; Z.AI is explicitly deferred. Entry: P4 commit; route evidence is repaired and recorded per enabled route. In scope: existing LLMProvider and existing OpenAI/Anthropic providers; only approved adapter seams. Deferred: Z.AI, automatic routing, credential store, generic endpoint substitution, model selection.

Checklist: [ ] P5-T00 discovery [ ] P5-WP1 capability boundary [ ] P5-WP2 named routes [ ] P5-DOC audit [ ] P5-BI reconciliation [ ] P5-V checks [ ] P5-C commit.

Current execution record: `claude_code`, `codex_cli`, and `antigravity_cli` have bounded shared CLI/MCP adapters. `omniroute_api` has a fixed-loopback, no-Rush-credential adapter at `127.0.0.1:20128/v1/chat/completions`, with `model: auto`, one bounded projection, and semantic response validation. Z.AI is deferred without invocation. 9Router CLI/gateway remains the only unimplemented enabled route because its documented API requires a user-selected model and API-key contract; its records are `BL-P5-02`/`ISS-P5-9ROUTER`. The P5 checklist remains open until that route and the final audit are complete.

P5-WP1 — approved capability boundary  
P5-T00: rtk-map providers/base.py, existing provider modules, permissions, config and provider tests; verify current CLI help; record exact approved decision IDs; checklist P5-T00.  
P5-T01: test first that an unapproved/missing provider returns skipped with redacted provenance and no credential path. Preconditions BG-PROV for any enabled route. Allowed src/rush/providers/base.py, src/rush/providers/openai.py, src/rush/providers/anthropic.py, src/rush/permissions.py, src/rush/tools/continuity.py, tests/test_providers.py, tests/test_permissions.py. Do-not-touch credentials/config/dependencies until explicit approved task. Initial failure: route leaks/assumes credential or lacks fallback. Implement smallest capability policy seam. Negative: no automatic cross-provider retry or token/keychain read. Docs: provider/privacy/permissions. Backlog BL-P5-01; issue per unapproved route. Verify focused/full/Ruff. Accept: skipped/redaction/provenance tests green. Checklist P5-WP1/P5-T01.

P5-WP2 — named route integration  
P5-T02: for one route at a time, test the enabled user-owned CLI or API contract for Codex, Claude Code, Antigravity, 9Router, and OmniRoute. Z.AI is deferred and must not be invoked. Preconditions are the route’s exact command/profile/endpoint evidence, not an inferred absence. Allowed files are exactly the benchmark-approved existing provider module or a new adapter path named in the route record, src/rush/tools/continuity.py, permissions.py, config.py, tests/test_providers.py and a focused test path. Do-not-touch credentials/keychain/home files, dependencies, or router substitution. Initial failure: no declared capability or unsafe request boundary. Implement bounded redacted adapter; refactor only route-local code. Negative: unavailable profile/timeouts/output limit returns skipped/error; Rush never signs in, opens browser or moves OAuth material. Docs: exact route, retention/privacy, fallback and configuration. Backlog one entry per route; issue one per blocked/failed route, otherwise no issue. Verify route contract tests/full/Ruff. Accept: production behavior tests are linked to exact local route evidence. Checklist P5-WP2/P5-T02.

P5 definition of done: approved routes are explicit, redacted, permission-gated and non-authoritative; unapproved routes remain visible skipped; provider docs, tracker and commits are complete. Recovery: disable individual adapter without damaging local continuity data.

## 4A. Mandatory task-specific discovery commands

Run the row for the atomic task immediately before its focused test or edit. These are required evidence, not optional examples.

| Task | RTK command set | Graft command set | Context-mode command set |
|---|---|---|---|
| P1-T00 | `rtk git status --short`; `rtk find -name "*.py"`; `rtk grep "session_memory" src tests`; `rtk read --line-numbers src/rush/tools/base.py` | `graft check .`; `graft map .`; `graft callers _register_tools .` | `context-mode doctor`; `context-mode index src --project . --ext .py`; `context-mode search "session memory" --project . --type code` |
| P1-T01 | `rtk grep "ToolResult\|ToolFn\|ALL_TOOLS" src tests`; `rtk read --line-numbers src/rush/tools/__init__.py src/rush/mcp.py`; `rtk pytest tests/test_cli_registry.py tests/test_mcp.py` | `graft skeleton src/rush/tools/__init__.py .`; `graft callers ToolResult .`; `graft grep "_register_tools" .` | `context-mode search "ToolResult MCP registration" --project . --type code --limit 10` |
| P1-T02 | `rtk grep "ExecutionPermissions\|TOOL_SPECS" src tests`; `rtk read --line-numbers src/rush/config.py src/rush/permissions.py`; `rtk pytest tests/test_config.py tests/test_permissions.py` | `graft skeleton src/rush/permissions.py .`; `graft callers ExecutionPermissions .` | `context-mode search "permission configuration catalog" --project . --type code` |
| P1-T03 | `rtk read --line-numbers docs/developer/backlog.md docs/developer/issues.md`; `rtk diff` | `graft grep "ToolResult" docs .` | `context-mode search "backlog issue tracker" --project . --type prose` |
| P2-T00 | `rtk grep "SessionMemoryManager\|CheckpointJournal\|FailureLedger" src tests`; `rtk read --line-numbers src/rush/session_memory.py` | `graft check .`; `graft callers SessionMemoryManager .`; `graft map .` | `context-mode search "session checkpoint failure" --project . --type code` |
| P2-T01 | `rtk grep "SecretRedactor\|MerkleInvalidator" src tests`; `rtk read --line-numbers src/rush/safety/redactor.py`; `rtk pytest tests/test_session_memory.py tests/test_phase41_memory_ship.py` | `graft skeleton src/rush/safety/redactor.py .`; `graft callers MerkleInvalidator .` | `context-mode search "redaction authority freshness" --project . --type code` |
| P2-T02 | `rtk grep "save\|restore\|checkpoint" src tests`; `rtk read --line-numbers src/rush/session_memory.py`; `rtk pytest tests/test_session_memory.py` | `graft callers CheckpointJournal .`; `graft grep "restore" src .` | `context-mode search "save restore receipt" --project . --type code` |
| P3-T00 | `rtk grep "ContextPacker\|ContentRouter\|CCRStore" src tests`; `rtk read --line-numbers src/rush/codegraph/context_packer.py` | `graft check .`; `graft callers ContextPacker .`; `graft map .` | `context-mode search "context pack token CCR" --project . --type code` |
| P3-T01 | `rtk grep "budget\|token\|omission" src tests`; `rtk read --line-numbers src/rush/token_economy/router.py`; `rtk pytest tests/test_phase43_ccr_grounding.py tests/test_phase44_context_pack_cache.py` | `graft skeleton src/rush/codegraph/context_packer.py .`; `graft callers ContentRouter .` | `context-mode search "token budget selected evidence omission" --project . --type code` |
| P3-T02 | `rtk grep "TelemetryStore\|recovery\|CCR" src tests`; `rtk read --line-numbers src/rush/token_economy/telemetry.py`; `rtk pytest tests/test_phase45_telemetry_gain.py` | `graft callers TelemetryStore .`; `graft grep "CCRStore" src .` | `context-mode search "CCR recovery telemetry" --project . --type code` |
| P4-T00 | `rtk grep "MeshLockManager\|FlightRecorder\|SwarmMerge" src tests`; `rtk read --line-numbers src/rush/mcp_mesh/lock_manager.py` | `graft check .`; `graft callers MeshLockManager .`; `graft map .` | `context-mode search "lock merge recorder" --project . --type code` |
| P4-T01 | `rtk grep "lock\|conflict\|stale" src tests`; `rtk read --line-numbers src/rush/tools/swarm_merge.py`; `rtk pytest tests/test_phase49_trace_swarm_recorder.py` | `graft skeleton src/rush/mcp_mesh/lock_manager.py .`; `graft callers SwarmMergeSolver .` | `context-mode search "ownership conflict stale handoff" --project . --type code` |
| P4-T02 | `rtk grep "FailureLedger\|MistakeMiner\|FlightRecorder" src tests`; `rtk read --line-numbers src/rush/tools/flight_recorder.py`; `rtk pytest tests/test_mistake_miner.py` | `graft callers FlightRecorder .`; `graft grep "FailureLedger" src .` | `context-mode search "failure replay attempt receipt" --project . --type code` |
| P5-T00 | `rtk grep "LLMProvider\|OpenAIProvider\|AnthropicProvider" src tests`; `rtk read --line-numbers src/rush/providers/base.py` | `graft check .`; `graft callers LLMProvider .`; `graft map .` | `context-mode search "provider capability route" --project . --type code` |
| P5-T01 | `rtk grep "provider\|skipped\|permission" src tests`; `rtk read --line-numbers src/rush/providers/openai.py src/rush/providers/anthropic.py`; `rtk pytest tests/test_providers.py tests/test_permissions.py` | `graft skeleton src/rush/providers/base.py .`; `graft callers LLMProvider .` | `context-mode search "provider skipped redaction permission" --project . --type code` |
| P5-T02 | `rtk grep "provider\|OAuth\|CLI" src tests`; `rtk read --line-numbers src/rush/providers/base.py src/rush/config.py`; `rtk pytest tests/test_providers.py` | `graft grep "LLMProvider" src .`; `graft callers LLMProvider .`; `graft check .` | `context-mode search "provider CLI profile OAuth route" --project . --type code` |

## 5. Complete task inventory

| Task | Phase | Status | Allowed files | Do-not-touch | Test / docs | Backlog / issue | Dependencies / acceptance |
|---|---|---|---|---|---|---|---|
| P1-T00 | 1 | [x] | tracker files | src/, tests/ | discovery record | BL-P1-00 / issue only for actual discovery defect | rtk, graft, and context-mode evidence recorded |
| P1-T01/T02 | 1 | [x] | tools, catalog, cli, mcp, config, permissions, named tests | providers, token, dependencies | registry/MCP/config/permission tests; CLI/MCP/config docs | BL-P1-01/02 | ToolResult parity, disabled/denied behavior |
| P1-T03 | 1 | [x] | canonical tracker files, plan | source/config/tests | docs structural audit | BL-P1-03 / ISS-P1-TRACK if needed | required tracker fields preserved |
| P2-T00/T01/T02 | 2 | [x] | named session/memory/redactor/seam files and tests | providers/token/dependencies | session/checkpoint tests; privacy/session docs | BL-P2-01/02 | BG-AUTH, BG-PRIV; redaction/authority/freshness |
| P3-T00/T01/T02 | 3 | [x] | named context/token/seam files and tests | models/providers/dependencies | CCR/context/telemetry tests; context docs | BL-P3-00 / ISS-P3-RECOVERY | BG-CTX; selected IDs/recovery/accounting |
| P4-T00/T01/T02 | 4 | [x] | named lock/merge/recorder/memory/seam files and tests | providers/models/config | recorder/mistake tests; recovery docs | BL-P4-00 / ISS-P4-MISTAKES | BG-COORD where protocol changes; conflict/replay safe |
| P5-T00/T01/T02 | 5 | [ ] | benchmark-approved provider files/seam/permission/tests | credentials, unapproved routes, dependencies | provider/permission tests; route docs | BL-P5-01 + route items | route gate passes; skipped/redacted behavior |

## 6. Test inventory

| Test path | Behavior | Phase | Fixture/mock | Focused verification | Full verification |
|---|---|---|---|---|---|
| tests/test_cli_registry.py, tests/test_mcp.py | shared registration and transport parity | 1 | no network | confirmed pytest selectors | project pytest |
| tests/test_permissions.py, tests/test_config.py | denied/disabled configuration | 1/5 | local config | confirmed selectors | project pytest |
| tests/test_session_memory.py, tests/test_phase41_memory_ship.py | redacted handoff/checkpoint | 2 | synthetic secret and stale record | confirmed selectors | project pytest |
| tests/test_phase43_ccr_grounding.py, tests/test_phase44_context_pack_cache.py, tests/test_phase45_telemetry_gain.py | envelope/recovery/token provenance | 3 | deterministic context fixtures | confirmed selectors | project pytest |
| tests/test_phase49_trace_swarm_recorder.py, tests/test_mistake_miner.py | conflict, replay, known failure | 4 | local lock/failure fixtures | confirmed selectors | project pytest |
| tests/test_providers.py | capability/skipped/redaction route policy | 5 | no-secret provider mock | confirmed selectors | project pytest |

## 7. Backlog, issue, worktree and commit ledger

| Phase | Worktree / branch | Tracker events | Required checks | Commit / expected contents |
|---|---|---|---|---|
| 1 | ../rush-cli-continuity-p1 / codex/continuity-p1-contract | start, before/after each task, pre/post commit | pytest, Ruff, format, diff review, docs audit | shared tool seam, tracker schema, docs |
| 2 | ../rush-cli-continuity-p2 / codex/continuity-p2-handoff | same | pytest, Ruff, format, diff review, docs audit | redacted provenance handoff |
| 3 | ../rush-cli-continuity-p3 / codex/continuity-p3-context | same | pytest, Ruff, format, diff review, docs audit | deterministic context envelope |
| 4 | ../rush-cli-continuity-p4 / codex/continuity-p4-coordination | same | pytest, Ruff, format, diff review, docs audit | ownership/replay evidence |
| 5 | ../rush-cli-continuity-p5 / codex/continuity-p5-adapters | same | pytest, Ruff, format, diff review, docs audit | approved route adapter/hardening |

## 8. Complete docs audit matrix

Every current docs/ file is listed below. **U-Pn** is an update required by the exact phase document pack in §3A; **R** is reviewed unchanged in that phase because the shipped behavior does not affect its subject. Historical ADRs, research reports, prompts, and retired phase plans remain R unless a specific compatibility/supersession issue changes that judgment.

| Path | Purpose | P1 / P2 / P3 / P4 / P5 action |
|---|---|---|
| docs/AGENTIC_RUSH.md | Agentic Rush: The AI Agent Copilot & Quality Control Engine | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/ALTERNATIVES.md | Alternatives, Comparisons, and Complements | R / R / R / R / R |
| docs/API_REFERENCE.md | Python Internal API Reference | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/ARCHITECTURE.md | Rush architecture | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/BUNDLE_DIAGRAMS.md | Rush Subsystem & Bundle Architecture Diagrams | R / R / R / R / R |
| docs/CI_INTEGRATION.md | Continuous Integration (CI) Integration Guide | R / R / R / R / R |
| docs/CLI_COOKBOOK.md | CLI Cookbook & Command Recipes | U-P1 / R / R / R / U-P5 |
| docs/CLI_REFERENCE.md | CLI reference | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/COMPATIBILITY.md | Platform & Ecosystem Compatibility | R / R / R / R / U-P5 |
| docs/CONFIGURATION.md | Rush Configuration Overview | U-P1 / R / R / R / U-P5 |
| docs/CONFIG_SCHEMA.md | Configuration Schema Specification (`rush.toml`) | U-P1 / R / R / R / U-P5 |
| docs/DECISIONS.md | Architectural Decisions Index | R / R / R / R / R |
| docs/DEPENDENCY_POLICY.md | Dependency & Engine Discovery Policy | R / R / R / R / R |
| docs/DESIGN_PRINCIPLES.md | Rush Design Principles & Architecture Invariants | R / R / R / R / R |
| docs/DEVELOPER_GUIDE.md | Developer guide | U-P1 / R / R / R / R |
| docs/DISTRIBUTION.md | Package Packaging & Distribution | R / R / R / R / R |
| docs/DOCUMENTATION_BRIEF.md | Rush Documentation Rewrite Brief | R / R / R / R / R |
| docs/EDITOR_INTEGRATION.md | Editor & IDE Integration Guide | R / R / R / R / R |
| docs/ENGINES.md | Engine directory | R / R / R / R / R |
| docs/ENGINE_COMPATIBILITY.md | Engine compatibility and integration contract | R / R / R / R / U-P5 |
| docs/ENVIRONMENT_VARIABLES.md | Environment Variables Reference | R / R / R / R / R |
| docs/EXAMPLES.md | Practical Examples & Common Workflows | R / R / R / R / R |
| docs/FAQ.md | Frequently Asked Questions (FAQ) | R / R / R / R / R |
| docs/GLOSSARY.md | Glossary of Terms | R / R / R / R / R |
| docs/INTEGRATIONS.md | Ecosystem Integrations Hub | R / R / R / R / U-P5 |
| docs/JSON_SCHEMA.md | JSON Schema & Output Specification | U-P1 / U-P2 / U-P3 / U-P4 / R |
| docs/KNOWN_ISSUES.md | Known issues | R / R / R / R / R |
| docs/LIMITATIONS.md | Limitations | R / U-P2 / R / R / R |
| docs/MAINTAINER_PLAYBOOK.md | Maintainer Playbook & Operational Governance | R / R / R / R / R |
| docs/MCP.md | Rush with coding assistants | U-P1 / R / R / R / U-P5 |
| docs/MCP_REFERENCE.md | MCP tool reference | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/MIGRATION_GUIDE.md | Migration & Version Upgrade Guide | R / R / R / R / R |
| docs/PRE_COMMIT.md | Git Pre-Commit Hook Integration | R / R / R / R / R |
| docs/PRIVACY.md | Privacy & Data Handling Guarantees | R / U-P2 / R / R / U-P5 |
| docs/README.md | Rush documentation | R / R / R / R / R |
| docs/RECIPE_BOOK.md | Recipe Book & Advanced Engineering Scenarios | R / R / R / R / R |
| docs/RELEASE.md | Release Management & Publishing Operations | R / R / R / R / R |
| docs/SAFETY.md | Safety overview | R / U-P2 / R / U-P4 / U-P5 |
| docs/SCOPE.md | Rush Scope & Architectural Boundaries | R / R / R / R / R |
| docs/SECURITY.md | Security Policy & Vulnerability Reporting | R / U-P2 / R / U-P4 / U-P5 |
| docs/SEMANTIC_DRIFT.md | Semantic-drift detection | R / R / R / R / R |
| docs/SUPPORT.md | Support & Issue Triage Guidelines | R / R / R / R / R |
| docs/TESTING.md | Testing Architecture & Verification Protocols | U-P1 / R / R / R / R |
| docs/TOOL_CATALOG.md | Tool catalog | U-P1 / R / R / R / R |
| docs/TROUBLESHOOTING.md | Troubleshooting Guide & Common Resolutions | U-P1 / U-P2 / R / U-P4 / R |
| docs/TROUBLESHOOTING_MATRIX.md | Troubleshooting matrix | R / R / R / R / R |
| docs/TUTORIALS.md | Rush tutorials | R / R / R / R / R |
| docs/USER_GUIDE.md | The Friendly Rush User Guide | R / R / R / R / R |
| docs/V0_2_SCOPE.md | Rush v0.2 Scope and Engine Policy | R / R / R / R / R |
| docs/VERSIONING.md | Versioning Policy & Compatibility Contracts | R / R / R / R / R |
| docs/VIBECODING.md | Vibecoding with Rush: Code at the Speed of Thought Without the Hangover | R / R / R / R / R |
| docs/adr/0001-external-engine-boundary.md | ADR 0001: External engine boundary | R / R / R / R / R |
| docs/adr/0002-normalized-finding-and-evidence-model.md | ADR 0002: Normalized finding and evidence model | R / R / R / R / R |
| docs/adr/0003-tool-catalog-cli-mcp-parity.md | ADR 0003: Tool catalog, CLI, and MCP parity | R / R / R / R / R |
| docs/adr/0004-subprocess-timeout-cancellation-and-redaction.md | ADR 0004: Bounded subprocess execution | R / R / R / R / R |
| docs/adr/0005-optional-engine-version-compatibility.md | ADR 0005: Optional engine version compatibility | R / R / R / R / R |
| docs/adr/0006-report-import-vs-live-adapter.md | ADR 0006: Report importer versus live adapter | R / R / R / R / R |
| docs/adr/0007-slow-network-and-destructive-permissions.md | ADR 0007: Slow, network, and destructive permissions | R / R / R / R / R |
| docs/adr/0008-browser-evidence-final-program.md | ADR 0008: Browser evidence is the final program | R / R / R / R / R |
| docs/adr/0009-testing-fixtures-and-optional-ci.md | ADR 0009: Fixture-first tests and optional CI | R / R / R / R / R |
| docs/adr/0010-review-and-remediation-gates.md | ADR 0010: Review and remediation gates | R / R / R / R / R |
| docs/adr/0011-html-and-sarif-artifact-export.md | ADR 0011: Standalone HTML & SARIF 2.1.0 Artifact Exporters | R / R / R / R / R |
| docs/adr/0012-pluggable-llm-provider-abstraction.md | ADR 0012: Pluggable LLM Provider Abstraction Layer | R / R / R / R / R |
| docs/adr/0013-tdd-guard-and-continuous-architectural-sensors.md | ADR 0013: TDD Guard & Continuous Architectural Sensors | R / R / R / R / R |
| docs/adr/0014-incremental-content-hash-result-cache.md | ADR-0014: Incremental Content-Hash Result Caching and Git Scoping | R / R / R / R / R |
| docs/adr/0015-extensible-plugin-architecture-and-agent-skills.md | ADR-0015: Extensible Plugin Architecture and AI Agent Plugin Skills | R / R / R / R / R |
| docs/adr/0016-local-web-dashboard-and-rich-interactive-tui.md | ADR-0016: Local Web Dashboard and Rich Interactive Terminal UI | R / R / R / R / R |
| docs/adr/0017-composite-workflow-suites-and-file-watcher.md | ADR-0017: Composite Workflow Suites and Real-Time File Watcher | R / R / R / R / R |
| docs/adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md | ADR-0018: Closed-Loop AI Agent Patch Remediation and Session Context Memory | R / R / R / R / R |
| docs/adr/0019-native-graft-semantic-slicing-and-tree-sitter.md | ADR-0019: Native Graft Semantic Slicing and Tree-Sitter AST Engine | R / R / R / R / R |
| docs/adr/0020-cryptographic-hmac-context-boundary-framing.md | ADR-0020: Cryptographic HMAC Context Boundary Framing | R / R / R / R / R |
| docs/adr/0021-ephemeral-git-worktree-sandboxing.md | ADR-0021: Ephemeral Git Worktree Sandboxing | R / R / R / R / R |
| docs/adr/0022-offline-bpe-token-accounting.md | ADR-0022: Offline BPE Token Accounting via tiktoken | R / R / R / R / R |
| docs/adr/0023-async-local-model-bridge.md | ADR-0023: Async Local Model Bridge via httpx | R / R / R / R / R |
| docs/adr/0024-hardened-subprocess-git-invocations.md | ADR-0024: Hardened Subprocess Git Invocations | R / R / R / R / R |
| docs/adr/0025-polyglot-grammar-expansion.md | ADR-0025: Polyglot Grammar Expansion via tree-sitter-language-pack | R / R / R / R / R |
| docs/adr/0026-multi-ide-agent-governance-and-canonical-rule-compilation.md | ADR-0026: Multi-IDE Agent Governance and Canonical Rule Compilation | R / R / R / R / R |
| docs/adr/0027-sub-second-git-pre-commit-intelligence-and-hook-guard.md | ADR-0027: Sub-Second Git Pre-Commit Intelligence and Hook Guard | R / R / R / R / R |
| docs/adr/0028-multi-model-consensus-reconciliation-and-quality-scorecard.md | ADR-0028: Multi-Model Consensus Reconciliation and Quality Scorecard | R / R / R / R / R |
| docs/adr/0029-unified-vibecoder-toolkit-and-sub-second-feedback-loop.md | ADR-0029: Unified Vibe-Coder Toolkit and Sub-Second Feedback Loop | R / R / R / R / R |
| docs/adr/0030-unified-dual-layer-agent-context-memory-subsystem.md | ADR-0030: Unified Dual-Layer Agent Context Memory Subsystem | R / R / R / R / R |
| docs/adr/0031-pre-flight-ship-readiness-cockpit-and-zero-downtime-gates.md | ADR-0031: Pre-Flight Ship-Readiness Cockpit and Zero-Downtime Gates | R / R / R / R / R |
| docs/adr/0032-code-property-graph-pruned-context-packing-and-token-budgeting.md | ADR-0032: Code Property Graph Pruned Context Packing and Token Budgeting | R / R / R / R / R |
| docs/adr/0033-real-time-ast-package-hallucination-and-phantom-import-guard.md | ADR-0033: Real-Time AST Package Hallucination and Phantom Import Guard | R / R / R / R / R |
| docs/adr/0034-autonomous-flaky-test-stress-perturbation-and-self-healing.md | ADR-0034: Autonomous Flaky Test Stress Perturbation and Self-Healing | R / R / R / R / R |
| docs/adr/0035-multi-agent-fastmcp-mesh-lock-daemon-and-3-way-ast-reconciliation.md | ADR-0035: Multi-Agent FastMCP Mesh Lock Daemon and 3-Way AST Reconciliation | R / R / R / R / R |
| docs/adr/0036-air-gapped-slm-local-onnx-runtime-and-slsa-attestation.md | ADR-0036: Air-Gapped SLM Local ONNX Runtime and SLSA Attestation | R / R / R / R / R |
| docs/adr/0037-polyglot-ast-grammars-tree-sitter-dependency-pinning.md | ADR-0037: Polyglot AST Grammars and Tree-sitter Dependency Pinning | R / R / R / R / R |
| docs/adr/0038-context-intelligence-engine-and-ccr-architecture.md | ADR-0038: Context Intelligence Engine and CCR Architecture | R / R / R / R / R |
| docs/adr/0039-toon-format-wire-serialization-for-fastmcp.md | ADR-0039: TOON Format Wire Serialization for FastMCP | R / R / R / R / R |
| docs/adr/0040-command-output-distillation-and-test-log-pruning.md | ADR-0040: Command-Output Distillation and Test Log Pruning | R / R / R / R / R |
| docs/adr/0041-bi-temporal-git-revert-mistake-memory-spine.md | ADR-0041: Bi-Temporal Git-Revert Mistake Memory Spine | R / R / R / R / R |
| docs/adr/0042-ast-grounding-and-phantom-symbol-verification.md | ADR-0042: AST Grounding and Phantom Symbol Verification | R / R / R / R / R |
| docs/adr/0043-stale-tool-result-deduplication-and-not-modified-hashes.md | ADR-0043: Stale Tool Result Deduplication and Continuity Hashes | R / R / R / R / R |
| docs/adr/0044-clean-room-implementation-of-codebase-indexing-algorithms.md | ADR-0044: Clean-Room Implementation of Codebase Indexing Algorithms | R / R / R / R / R |
| docs/adr/0045-real-time-terminal-gain-hud-and-telemetry.md | ADR-0045: Real-Time Terminal Gain HUD and Telemetry | R / R / R / R / R |
| docs/adr/0046-pre-flight-ship-readiness-cockpit.md | ADR-0046: Pre-Flight Ship-Readiness Cockpit | R / R / R / R / R |
| docs/adr/0047-multi-agent-fastmcp-mesh-and-ast-3way-merge.md | ADR-0047: Multi-Agent FastMCP Mesh and AST 3-Way Merge | R / R / R / R / R |
| docs/adr/0048-hybrid-dual-engine-architecture-graft-and-codegraph.md | ADR-0048: Hybrid Dual-Engine Architecture (Graft Semantic Graph + CodeGraph AST Engine) | R / R / R / R / R |
| docs/adr/README.md | ADR index and implementation cross-reference | R / R / R / R / R |
| docs/agentic-rush/README.md | Agentic Rush Documentation | R / R / R / R / R |
| docs/agentic-rush/ai-safety-and-sandboxing.md | AI Safety & Worktree Sandboxing | R / R / R / U-P4 / R |
| docs/agentic-rush/anti-hallucination.md | Agentic Rush/Anti Hallucination | R / U-P2 / R / R / R |
| docs/agentic-rush/codebase-hygiene-and-ast-merging.md | Codebase Hygiene & 3-Way AST Merges | R / R / R / U-P4 / R |
| docs/agentic-rush/codegraph-and-semantic-slicing.md | CodeGraph & Semantic Slicing | R / R / R / R / R |
| docs/agentic-rush/governance-and-multi-ide-rules.md | Agent Governance & Multi-IDE Rules | R / R / R / R / R |
| docs/agentic-rush/multi-model-consensus-and-scoring.md | Multi-Model Consensus & Quality Scorecards | R / R / R / R / R |
| docs/agentic-rush/patch-remediation-and-memory.md | Patch Remediation & Session Memory | R / U-P2 / R / U-P4 / R |
| docs/agentic-rush/plugins-and-agent-skills.md | Plugins & Agent Skills | R / R / R / R / R |
| docs/agentic-rush/pre-commit-intelligence.md | Pre-Commit Intelligence & Hook Guard | R / R / R / R / R |
| docs/agentic-rush/token-economy-and-context.md | Token Economy & Context Optimization | R / R / U-P3 / R / R |
| docs/agentic-rush/token-efficiency.md | Agentic Rush/Token Efficiency | R / R / U-P3 / R / R |
| docs/architecture/rush-epistemic-memory-and-agent-substrate.md | Rush Epistemic Memory & Coding Agent Substrate | R / U-P2 / U-P3 / R / R |
| docs/benchmarking-report.md | Rush CLI Comprehensive Benchmarking Report & Execution Framework | R / R / R / R / R |
| docs/developer/architecture.md | Rush architecture | U-P1 / R / R / R / R |
| docs/developer/backlog.md | Rush Platform Master Backlog & Feature Tracker | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/developer/benchmarking-report.md | Rush CLI Comprehensive Benchmarking Report & Execution Framework | R / R / R / R / R |
| docs/developer/brainstorm-agentic-coding-support-plan.md | Rush Agentic Coding Support Architecture Plan | R / R / R / R / R |
| docs/developer/brainstorm-git-intelligence-plan.md | Rush Git Intelligence Architecture Plan | R / R / R / R / R |
| docs/developer/brainstorm-innovation-custom-plan.md | Rush Innovation Plan: 28+ Custom Tools for Developers & Vibe-Coders | R / R / R / R / R |
| docs/developer/ci-and-packaging.md | Contributor CI, Packaging & Build Engineering | R / R / R / R / R |
| docs/developer/coding-standards.md | Contributor Coding Standards & Architecture Invariants | U-P1 / R / R / R / R |
| docs/developer/configuration-development.md | Configuration Subsystem Development Guide | U-P1 / R / R / R / U-P5 |
| docs/developer/contributor-onboarding.md | Contributor onboarding | R / R / R / R / R |
| docs/developer/debugging-guide.md | Contributor Debugging & Diagnostics Guide | R / U-P2 / R / R / R |
| docs/developer/engine-development.md | Engine Adapter Development & Integration Guide | R / R / R / R / R |
| docs/developer/headrushtoolsurls.txt | documentation record | R / R / R / R / R |
| docs/developer/innovation-enhancement-funcionality-report.md | Rush CLI: Master Innovation, Functionality & Strategic Workflow Blueprint | R / R / R / R / R |
| docs/developer/innovation-enhancement-functionality-report.md | Rush CLI: Master Innovation, Functionality & Strategic Workflow Blueprint | R / R / R / R / R |
| docs/developer/innovation-remediation-plan.md | Master Innovation & Remediation Plan: 77 Advanced Scanners, Evaluators, Mutation Tools, UI | R / R / R / R / R |
| docs/developer/integrations-scope-plan.md | Rush Integration Scope & Repository Evaluation Plan | R / R / R / R / R |
| docs/developer/issues.md | Rush Platform Issue & Bug Tracker | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/developer/master-brainstorm-innovation-plan.md | Master Innovation & Architecture Build Plan: Rush Agent-Native Platform (Phases 31–40) | R / R / R / R / R |
| docs/developer/master-innovation-remediation-build-plan.md | Master Innovation & Remediation Build Plan: 86-Engine Phased Implementation Guide (Phases  | R / R / R / R / R |
| docs/developer/master-pm-build-plan.md | Master Product Management Build Plan: Rush Platform Evolution (Phases 21–30) | R / R / R / R / R |
| docs/developer/mcp-development.md | Model Context Protocol (MCP) Server Architecture & Development | U-P1 / R / R / R / U-P5 |
| docs/developer/phase-07-08-coding-agent-handoff.md | Phase 07–08 coding-agent handoff | R / R / R / R / R |
| docs/developer/phase-09-19-coding-agent-handoff.md | Phase 09–19 Coding Agent Handoff & Architecture Completion Ledger | R / R / R / R / R |
| docs/developer/phase-20-plan-ai-anti-slop-modular-boundaries-and-continuous-sensors.md | Phase 20 Implementation Plan: AI Anti-Slop, Modular Boundaries & Continuous Intelligence | R / R / R / R / R |
| docs/developer/phase-21-plan-incremental-cache-and-git-scoping.md | Phase 21 Implementation Plan: Flag-Salted Cryptographic Cache & Git Scoping | R / R / R / R / R |
| docs/developer/phase-22-plan-unified-automated-remediation.md | Phase 22 Implementation Plan: Confined Automated Remediation (`rush fix`) | R / R / R / R / R |
| docs/developer/phase-23-plan-sanitized-stack-onboarding-and-config-init.md | Phase 23 Implementation Plan: Sanitized Stack Onboarding & Configuration Initialization (` | R / R / R / R / R |
| docs/developer/phase-24-plan-hardened-workflow-suites-and-environment-doctor.md | Phase 24 Implementation Plan: Hardened Workflow Suites & Environment Doctor (`rush check`  | R / R / R / R / R |
| docs/developer/phase-25-plan-real-time-file-system-watcher.md | Phase 25 Implementation Plan: Real-Time File System Watcher (`rush watch`) | R / R / R / R / R |
| docs/developer/phase-26-plan-monorepo-and-workspace-boundaries.md | Phase 26 Implementation Plan: Monorepo & Workspace Boundaries (`rush workspace`) | R / R / R / R / R |
| docs/developer/phase-27-plan-authenticated-in-memory-dashboard-and-tui.md | Phase 27 Implementation Plan: Authenticated In-Memory Dashboard & TUI (`rush dashboard` /  | R / R / R / R / R |
| docs/developer/phase-28-plan-trust-gated-plugin-system-and-agent-skills.md | Phase 28 Implementation Plan: Trust-Gated Plugin System & Agent Skills (`rush trust` / `ru | R / R / R / R / R |
| docs/developer/phase-29-plan-isolated-ai-patch-remediation-and-memory.md | Phase 29 Implementation Plan: Isolated AI Patch Remediation & Memory (`rush patch`) | R / R / R / R / R |
| docs/developer/phase-30-plan-standalone-packaging-versioning-and-ci.md | Phase 30 Implementation Plan: Standalone Packaging, Versioning & CI (`rush release` / `rus | R / R / R / R / R |
| docs/developer/phase-31-plan-agent-safety-and-worktree-sandboxing.md | Phase 31 Implementation Plan: Agent Safety & Worktree Sandboxing (`rush sandbox` / `rush g | R / R / R / R / R |
| docs/developer/phase-32-plan-token-economy-and-context-optimization.md | Phase 32 Implementation Plan: Token Economy & Context Optimization (`rush token`) | R / R / R / R / R |
| docs/developer/phase-33-plan-full-stack-sync-and-type-safety-gates.md | Phase 33 Implementation Plan: Full-Stack Sync & Type Safety Gates (`rush sync`) | R / R / R / R / R |
| docs/developer/phase-34-plan-codebase-hygiene-and-merge-resolution.md | Phase 34 Implementation Plan: Codebase Hygiene & AST Merge Resolution (`rush hygiene` / `r | R / R / R / R / R |
| docs/developer/phase-35-plan-polyglot-ast-slicing-and-semantic-codegraph.md | Phase 35 Implementation Plan: Polyglot AST Slicing & Semantic CodeGraph (`rush codegraph`) | R / R / R / R / R |
| docs/developer/phase-36-plan-frontend-asset-and-bundle-optimization.md | Phase 36 Implementation Plan: Frontend Asset & Bundle Optimization (`rush bundle`) | R / R / R / R / R |
| docs/developer/phase-37-plan-git-hotspots-churn-and-code-velocity.md | Phase 37 Implementation Plan: Git Hotspots, Churn & Code Velocity (`rush hotspots`) | R / R / R / R / R |
| docs/developer/phase-38-plan-agent-governance-and-repo-scaffolding.md | Phase 38 Implementation Plan: Agent Governance & Repo Scaffolding (`rush governance` / `ru | R / R / R / R / R |
| docs/developer/phase-39-plan-git-pre-commit-intelligence-and-hook-guard.md | Phase 39 Implementation Plan: Git Pre-Commit Intelligence & Hook Guard (`rush hook`) | R / R / R / R / R |
| docs/developer/phase-40-plan-multi-model-consensus-and-quality-scorecard.md | Phase 40 Implementation Plan: Multi-Model Consensus & Quality Scorecard (`rush score` / `r | R / R / R / R / R |
| docs/developer/phase-41-plan-foundations-bpe-distillers-and-base-ship.md | Phase 41: Foundations, BPE Accounting, Command Distillers & Base Ship Vectors | R / R / R / R / R |
| docs/developer/phase-42-plan-toon-ast-skeletons-and-ship-gate.md | Phase 42: Compact Serialization (TOON), Polyglot AST Skeletons & Ship Gate | R / R / R / R / R |
| docs/developer/phase-43-plan-ccr-grounding-and-mistake-memory.md | Phase 43: Reversibility (CCR), Grounding Verification & Pre-Mortem Mistake Memory | R / R / R / R / R |
| docs/developer/phase-44-plan-context-pack-and-prompt-cache-alignment.md | Phase 44: Graph-Pruned Context Packing & Prompt Cache Prefix Alignment | R / R / R / R / R |
| docs/developer/phase-45-plan-gain-tui-telemetry-and-terse-persona.md | Phase 45: Observability, Session Deduplication & Flagship Context Gain TUI | R / R / R / R / R |
| docs/developer/phase-46-plan-blast-radius-and-architecture-guard.md | Phase 46: Transitive Blast Radius & Declarative Architectural Guard | R / R / R / R / R |
| docs/developer/phase-47-plan-test-heal-and-api-diff.md | Phase 47: Flaky Test Healer & Zero-Shot API Breaking Change Detector | R / R / R / R / R |
| docs/developer/phase-48-plan-db-drift-simplify-and-strictify.md | Phase 48: Database Migration Hazard Auditor & Cognitive Complexity Decomposer | R / R / R / R / R |
| docs/developer/phase-49-plan-traceability-flight-recorder-and-swarm-merge.md | Phase 49: Spec-to-Code Traceability, Agent Flight Recorder & Swarm 3-Way Merge | R / R / R / R / R |
| docs/developer/phase-50-plan-slsa-attestation-security-suite-and-flagship-release.md | Phase 50: Supply Chain SLSA Attestation, Security Audit Suite & Flagship Release | R / R / R / R / R |
| docs/developer/pm-review.md | Product Management Review: Rush CLI & FastMCP Platform | R / R / R / R / R |
| docs/developer/release-process.md | Contributor Release Process & Verification Protocol | R / R / R / R / R |
| docs/developer/routing-development.md | Routing and language support | R / R / R / R / R |
| docs/developer/rush-integrations-report.md | Rush Integrations & Deep Repository Research Report | R / R / R / R / R |
| docs/developer/rush-token-innovation-enhancement-report-plan.md | Rush CLI: Master Token Reduction, Context Intelligence & Innovation Enhancement Implementa | R / R / R / R / R |
| docs/developer/ship-readiness-deep-research-report.md | Deep Research Report: Open-Source GitHub Repositories & Architectural Blueprint for Rush S | R / R / R / R / R |
| docs/developer/source-tree.md | Source tree responsibilities | R / R / R / R / R |
| docs/developer/testing-guide.md | Developer Testing Guide & Test Architecture | U-P1 / R / R / R / R |
| docs/developer/token-reduction-innovation-report.md | Rush CLI: Token Reduction & Context Intelligence Innovation Report | R / R / R / R / R |
| docs/developer/tool-development.md | Tool Development & Registration Guide | U-P1 / R / R / R / R |
| docs/developer/vibecoder-toolkit-plan.md | Rush Vibe-Coder Toolkit Architecture Plan | R / R / R / R / R |
| docs/developer/vibers-code-review.md | Vibers Comprehensive Code Review: Rush CLI & MCP Architecture | R / R / R / R / R |
| docs/getting-started/first-run.md | Your first ten minutes with Rush | R / R / R / R / R |
| docs/getting-started/glossary.md | Glossary | R / R / R / R / R |
| docs/getting-started/installation.md | Install Rush | R / R / R / R / R |
| docs/innovation-enhancement-funcionality-report.md | Rush CLI: Master Innovation, Functionality & Strategic Workflow Blueprint | R / R / R / R / R |
| docs/innovation-enhancement-report.md | Rush CLI: Comprehensive Architectural Review & 28-Feature Innovation Blueprint | R / R / R / R / R |
| docs/integrations/ci-overview.md | Continuous Integration (CI) Architecture & Strategy | U-P1 / R / R / R / R |
| docs/integrations/github-actions.md | GitHub Actions Integration Guide | R / R / R / R / R |
| docs/integrations/mcp-client-setup.md | Model Context Protocol (MCP) Client Configuration Guide | U-P1 / R / R / R / U-P5 |
| docs/integrations/mcp-overview.md | Model Context Protocol (MCP) Overview | R / R / R / R / U-P5 |
| docs/integrations/scripts-and-automation.md | Shell Scripts, Automation & Tooling Integration | R / R / R / R / R |
| docs/maintainers/adr/001-stdio-only-mcp.md | ADR-001: stdio-only MCP | R / R / R / R / R |
| docs/maintainers/adr/002-external-engine-discovery.md | ADR-002: external engine discovery | R / R / R / R / R |
| docs/maintainers/adr/003-catalog-driven-metadata.md | ADR-003: catalog-driven metadata | R / R / R / R / R |
| docs/maintainers/adr/004-explicit-safety-gates.md | ADR-004: explicit safety gates | R / R / R / R / R |
| docs/maintainers/adr/005-fixture-first-adapter-tests.md | ADR-005: fixture-first adapter tests | R / R / R / R / R |
| docs/maintainers/adr/006-bounded-ci.md | ADR-006: bounded CI | R / R / R / R / R |
| docs/maintainers/adr/007-git-root-bounded-configuration.md | ADR-007: Git-root-bounded configuration discovery | R / R / R / R / R |
| docs/maintainers/adr/008-html-and-sarif-artifact-export.md | ADR-008: Standalone HTML & SARIF 2.1.0 Artifact Export | R / R / R / R / R |
| docs/maintainers/adr/009-pluggable-llm-providers.md | ADR-009: Pluggable LLM Providers Architecture | R / R / R / R / R |
| docs/maintainers/adr/010-tdd-guard-and-continuous-sensors.md | ADR-010: TDD Guard & Continuous Architectural Sensors | R / R / R / R / R |
| docs/maintainers/adr/011-incremental-content-hash-cache.md | ADR-011: Incremental Content-Hash Result Caching and Git Scoping | R / R / R / R / R |
| docs/maintainers/adr/012-extensible-plugin-architecture.md | ADR-012: Extensible Plugin Architecture and AI Agent Plugin Skills | R / R / R / R / R |
| docs/maintainers/adr/013-local-web-dashboard-and-tui.md | ADR-013: Local Web Dashboard and Rich Interactive Terminal UI | R / R / R / R / R |
| docs/maintainers/adr/014-composite-workflow-suites-and-watcher.md | ADR-014: Composite Workflow Suites and Real-Time File Watcher | R / R / R / R / R |
| docs/maintainers/adr/015-agent-remediation-and-memory.md | ADR-015: Closed-Loop AI Agent Patch Remediation and Session Context Memory | R / R / R / R / R |
| docs/maintainers/adr/README.md | Architecture decision records | R / R / R / R / R |
| docs/maintainers/architecture-lifecycle.md | Maintainers/Architecture Lifecycle | R / R / R / R / R |
| docs/maintainers/documentation-style-guide.md | Maintainer Documentation Style & Synchronization Guide | R / R / R / R / R |
| docs/maintainers/incident-and-security.md | Incident & Security Handling Protocol | R / R / R / R / R |
| docs/maintainers/release-playbook.md | Maintainers/Release Playbook | R / R / R / R / R |
| docs/maintainers/scanner-governance.md | Scanner governance | R / R / R / R / R |
| docs/maintainers/support-runbook.md | Maintainer Support & Issue Triage Runbook | R / R / R / R / R |
| docs/maintainers/versioning-and-compatibility.md | Maintainer Versioning & Compatibility Contracts | R / R / R / R / R |
| docs/phase-plans/README.md | Rush Context Intelligence & Ship-Readiness Phase Implementation Plans | R / R / R / R / R |
| docs/phase-plans/phase-41-foundations-bpe-distillers-base-ship-plan.md | Phase 41: Foundations, BPE Accounting, Command Distillers & Base Ship Vectors | R / R / R / R / R |
| docs/phase-plans/phase-42-toon-ast-skeletons-ship-gate-plan.md | Phase 42: Compact Serialization (TOON), Polyglot AST Skeletons & Ship Gate | R / R / R / R / R |
| docs/phase-plans/phase-43-ccr-grounding-mistake-memory-plan.md | Phase 43: Reversibility (CCR), Grounding Verification & Pre-Mortem Mistake Memory | R / R / R / R / R |
| docs/phase-plans/phase-44-context-pack-prompt-cache-alignment-plan.md | Phase 44: Graph-Pruned Context Packing & Prompt Cache Prefix Alignment | R / R / R / R / R |
| docs/phase-plans/phase-45-gain-tui-telemetry-terse-persona-plan.md | Phase 45: Observability, Session Deduplication & Flagship Context Gain TUI | R / R / R / R / R |
| docs/phase-plans/phase-46-blast-radius-architecture-guard-plan.md | Phase 46: Transitive Blast Radius & Declarative Architectural Guard | R / R / R / R / R |
| docs/phase-plans/phase-47-test-heal-api-diff-plan.md | Phase 47: Flaky Test Healer & Zero-Shot API Breaking Change Detector | R / R / R / R / R |
| docs/phase-plans/phase-48-db-drift-simplify-strictify-plan.md | Phase 48: Database Migration Hazard Auditor & Cognitive Complexity Decomposer | R / R / R / R / R |
| docs/phase-plans/phase-49-traceability-flight-recorder-swarm-merge-plan.md | Phase 49: Spec-to-Code Traceability, Agent Flight Recorder & Swarm 3-Way Merge | R / R / R / R / R |
| docs/phase-plans/phase-50-slsa-attestation-security-suite-flagship-plan.md | Phase 50: Supply Chain SLSA Attestation, Security Audit Suite & Flagship Release | R / R / R / R / R |
| docs/prompts/AGENTIC_INNOVATION_MASTER_PROMPT.md | MISSION: Architect 30+ Practical Breakthroughs for Rush (Memory, Context & MCP Agent Layer | R / R / R / R / R |
| docs/reference/cli-reference.md | CLI reference | U-P1 / R / R / R / U-P5 |
| docs/reference/compatibility.md | Compatibility Reference Specification | R / R / R / R / U-P5 |
| docs/reference/configuration-cookbook.md | Configuration cookbook | R / R / R / R / R |
| docs/reference/configuration-reference.md | Configuration reference | U-P1 / R / R / R / U-P5 |
| docs/reference/engine-directory.md | Engine directory | R / R / R / R / R |
| docs/reference/environment-variables.md | Environment Variables Specification | R / R / R / R / R |
| docs/reference/mcp-tool-reference.md | MCP tool reference | U-P1 / R / R / R / U-P5 |
| docs/reference/research-repo-inventory.md | Master Research Repository Inventory & Pinned Commit Manifest | R / R / R / R / R |
| docs/reference/result-reference.md | Result and exit-code reference | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/reports/memory-innovation-enhancement-report.md | Rush: Memory, Agent Context, and Systemic Intelligence Report | R / R / R / R / R |
| docs/reports/runtime-memory-and-agent-skills.md | Runtime State, Vertical Coherence, and Agent Memory in Rush | R / R / R / R / R |
| docs/reports/rush-benchmark-plan.md | Rush benchmark and validation plan | R / R / R / R / R |
| docs/reports/rush-frontier-unclaimed-opportunities-report.md | Rush: The Unclaimed Opportunities & Frontier Innovations Report | R / R / R / R / R |
| docs/reports/rush-unified-agent-intelligence-development-plan-agy.md | Rush Memory, Context & Tool Implementation Plan | R / R / R / R / R |
| docs/reports/rush-unified-agent-intelligence-development-plan.md | Rush five-phase live execution plan | U-P1 / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/research/claw-github-top3-deep-review.md | Comprehensive Deep Review: CLAW Top-3 Repositories for Rush Integration | R / R / R / R / R |
| docs/rush-token-innovation-enhancement-report-plan.md | Rush CLI: Master Token Reduction, Context Intelligence & Innovation Enhancement Implementa | R / R / R / R / R |
| docs/safety/permissions.md | Permissions | R / R / R / R / U-P5 |
| docs/safety/privacy-and-data-handling.md | Privacy and data handling | R / U-P2 / U-P3 / R / U-P5 |
| docs/safety/safety-overview.md | Safety overview | R / U-P2 / R / U-P4 / R |
| docs/safety/security-model.md | Security model | R / U-P2 / R / U-P4 / U-P5 |
| docs/specs/arch-guard-spec.md | Specification: Declarative Architecture Boundary Guard | R / R / R / R / R |
| docs/specs/blast-radius-spec.md | Specification: Transitive Blast Radius Analyzer | R / R / R / R / R |
| docs/specs/cognitive-complexity-decomposition-spec.md | Specification: Cognitive Complexity Decomposer | R / R / R / R / R |
| docs/specs/context-compression-and-recovery-spec.md | Specification: Context Compression & Restoration (CCR) | R / R / U-P3 / R / R |
| docs/specs/db-migration-drift-spec.md | Specification: Database Migration Schema Drift Auditor | R / R / R / R / R |
| docs/specs/flaky-test-healer-spec.md | Specification: Autonomous Flaky Test Healer | R / R / R / R / R |
| docs/specs/flight-recorder-spec.md | Specification: Agent Flight Recorder & Session Replayer | R / R / R / U-P4 / R |
| docs/specs/iam-policy-synthesis-spec.md | Specification: Least-Privilege Cloud IAM Policy Synthesizer | R / R / R / R / R |
| docs/specs/license-compliance-spec.md | Specification: Open-Source License Compliance & Copyleft Auditor | R / R / R / R / R |
| docs/specs/prompt-cache-alignment-spec.md | Specification: Multi-Provider Prompt Cache Prefix Alignment | R / R / U-P3 / R / R |
| docs/specs/public-api-diff-spec.md | Specification: Zero-Server Public API Contract Differ | R / R / R / R / R |
| docs/specs/slsa-attestation-spec.md | Specification: SLSA Level 3 Cryptographic Build Attestation | R / R / R / R / R |
| docs/specs/spec-to-code-traceability-spec.md | Specification: Spec-to-Code Traceability Scanner | R / R / R / R / R |
| docs/specs/stale-sweeper-spec.md | Specification: Multi-Turn Stale Read Sweeper (TokenTamer) | R / R / U-P3 / R / R |
| docs/specs/swarm-3way-ast-merge-spec.md | Specification: Swarm 3-Way AST Merge Conflict Resolver | R / R / R / U-P4 / R |
| docs/specs/telemetry-ledger-spec.md | Specification: Token Economy Telemetry Ledger | R / R / U-P3 / R / R |
| docs/specs/terse-persona-spec.md | Specification: Terse Persona Mode | R / R / R / R / R |
| docs/specs/toon-serialization-spec.md | Specification: TOON v4.1 (Token-Oriented Object Notation) Wire Format | R / R / R / R / R |
| docs/specs/type-guard-synthesis-spec.md | Specification: Runtime Type Guard Synthesizer | R / R / R / R / R |
| docs/token-reduction-innovation-report.md | Rush CLI: Token Reduction & Context Intelligence Innovation Report | R / R / R / R / R |
| docs/tutorials/ai-coding-assistant.md | Tutorial: Connecting an AI Coding Assistant via MCP | R / R / R / R / R |
| docs/tutorials/before-a-pull-request.md | Tutorial: use Rush before every pull request | R / R / R / R / R |
| docs/tutorials/ci-integration.md | Tutorial: Adding Rush to Continuous Integration | R / R / R / R / R |
| docs/tutorials/first-10-minutes.md | Tutorial: your first 10 minutes | R / R / R / R / R |
| docs/tutorials/mixed-language-project.md | Tutorial: Multi-Language & Polyglot Repository Verification | R / R / R / R / R |
| docs/tutorials/python-project.md | Tutorial: set up a Python project | R / R / R / R / R |
| docs/tutorials/team-adoption.md | Tutorial: Adopting Rush Across an Engineering Team | R / R / R / R / R |
| docs/tutorials/typescript-project.md | Tutorial: set up a JavaScript/TypeScript project | R / R / R / R / R |
| docs/user-guide/advanced-checks.md | Advanced Checks & Monorepos | R / R / R / R / R |
| docs/user-guide/checking-code.md | Checking Your Code: Linters, Formatters, & Typecheckers | R / R / R / R / R |
| docs/user-guide/checking-project-files.md | Checking project files | R / R / R / R / R |
| docs/user-guide/everyday-workflow.md | The Everyday Developer Workflow | R / R / R / R / R |
| docs/user-guide/faq.md | Frequently asked questions | R / R / R / R / R |
| docs/user-guide/index.md | Rush User Guide Directory | R / R / R / R / R |
| docs/user-guide/security-and-supply-chain.md | Security & Supply Chain Protection | R / U-P2 / R / R / U-P5 |
| docs/user-guide/testing-confidence.md | Testing with Confidence: TDD, Coverage, & Reliability | R / R / R / R / R |
| docs/user-guide/troubleshooting.md | Troubleshooting Guide & FAQs | R / U-P2 / U-P3 / U-P4 / R |
| docs/user-guide/understanding-results.md | Understanding Rush Results | R / R / U-P3 / R / R |
| docs/user-guide/working-with-ai-agents.md | Pair Programming with AI Agents | R / U-P2 / U-P3 / U-P4 / U-P5 |
| docs/vibecoding/README.md | Vibecoding with Rush: Guides & Tutorials | R / R / R / R / R |
| docs/vibecoding/cheat-sheet.md | Vibecoder Cheat Sheet & Golden Prompts | R / R / R / R / R |
| docs/vibecoding/instant-fix-and-auto-remediation.md | Instant Fix & Auto-Remediation | R / R / R / R / R |
| docs/vibecoding/setting-up-your-agent.md | Setting Up Your AI Agent with Rush | R / R / R / R / R |
| docs/vibecoding/shipping-with-swagger.md | Shipping with Swagger: From Vibes to Production Release | R / R / R / R / R |
| docs/vibecoding/slop-busting-and-hallucination-defense.md | Slop-Busting & Hallucination Defense | R / R / R / R / R |
| docs/vibecoding/the-vibecoder-workflow.md | The Vibecoder Workflow: The Frictionless Build Loop | R / R / R / R / R |
| docs/vibecoding/token-diet-for-vibecoders.md | Token Diet for Vibecoders: Slash LLM Costs & Latency | R / R / R / R / R |
| docs/vibecoding/what-is-vibecoding-with-rush.md | What is Vibecoding with Rush? | R / R / R / R / R |
| docs/workflows/agent_grounding.md | Workflow: Real-Time AST Import Grounding Verification | R / R / R / R / R |
| docs/workflows/bi-temporal-mistake-pre-mortem.md | Workflow: Bi-Temporal Git Revert Mistake Pre-Mortem | R / R / R / U-P4 / R |
| docs/workflows/blast_radius_and_architecture_governance.md | Workflow: Blast Radius & Architectural Governance | R / R / R / R / R |
| docs/workflows/context_packing_and_budgeting.md | Workflow: Graph-Pruned Context Packing & Budgeting | R / R / U-P3 / R / R |
| docs/workflows/database_drift_and_code_simplification.md | Workflow: Database Schema Drift & Code Simplification | R / R / R / R / R |
| docs/workflows/flaky_test_healing_and_api_contracts.md | Workflow: Autonomous Test Healing & API Contract Governance | R / R / R / R / R |
| docs/workflows/gain_tui_and_telemetry.md | Workflow: Context Gain TUI & Real-Time Telemetry | R / R / R / R / R |
| docs/workflows/multi_agent_mesh_and_traceability.md | Workflow: Multi-Agent Mesh Coordination & Traceability | R / R / R / U-P4 / R |
| docs/workflows/supply_chain_security_and_flagship_release.md | Workflow: Supply Chain Security & Flagship Release | R / R / R / R / R |
Matrix complete: every non-U phase is an explicit review-only audit. A changed effect outside §3A requires an issue, matrix amendment, and phase-document-pack update before implementation.

P5 matrix amendment: `docs/JSON_SCHEMA.md` was changed by the initial P5 implementation although it had a review-only matrix cell. `ISS-P5-DOC-SCOPE` records that scope exception; its content remains reviewed and no further JSON-schema change is authorized by P5 without a linked task and matrix update.
## 9. Unresolved decisions that block implementation

| Decision | Blocked task | Issue / backlog | Smallest evidence required |
|---|---|---|---|
| Benchmark authority and persistence decision | P2-T02 | ISS-BG-AUTH / BL-P2-01 | BG-AUTH decision record with replay/tombstone/instruction quarantine result, generated by P2-T01. |
| Benchmark privacy/parser decision | P2-T01, P3-T01, P5-T01 | ISS-BG-PRIV / BL-P2-01 | BG-PRIV decision record and sanitized fixture evidence. |
| Projection/token decision | P3-T01 | ISS-BG-CTX / BL-P3-01 | BG-CTX renderer/token/recovery decision. |
| Semantic/index/model/runtime decision | P3 optional extension | ISS-BG-RET or ISS-BG-LOCAL / deferred backlog item | Passed gate naming exact candidate/version/fallback. |
| Coordination protocol decision | P4 protocol extension | ISS-BG-COORD / BL-P4-01 | BG-COORD stale/conflict/ownership evidence. |
| Provider route decision | P5-T02 | one route issue and backlog per route | BG-PROV, plus BG-9R/BG-OMNI where applicable, with policy/contract record. |
| Derived-index freshness | each phase T00 | phase discovery record | `graft check .` passes, or T00 marks graph/index output unavailable and uses repository evidence. |
