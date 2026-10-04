# Phase 72: Memory correctness and user control

Status: proposed implementation plan; no implementation, ratification or product acceptance claimed. Review baseline, 2026-10-04: primary `/Users/jamesdsizemore/Developer/rush-cli` HEAD `c78e445`; live development `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` HEAD `66c6c799`, including its user-owned dirty changes. Neither revision alone identifies the working bytes. Binding instructions: `AGENTS.md`, `docs/templates/task-block-template.md`, and `docs/adr/0010-review-and-remediation-gates.md`. Evidence: `docs/reports/memory-system-implementation-review-2026-09-25.md` §§2–6, 10–11 and `docs/phase-plans/restarting-rush-development-plan.md`; the old `ddc064117e971b48e29100004052e876e456faf2` snapshot is historical evidence only. Shared interfaces: `docs/phase-plans/memory-program-contract.md` C01–C10. Phase 70 and 71 remain existing obligations, not completed prerequisites. Implementation must carry forward current Phase 70 repairs; do not implement against primary's older helpers and overwrite them.

## 1. Goal, scope, and non-goals

Deliver one trustworthy, versioned memory route. A permitted agent and user can search, page, inspect exact evidence, understand authority and freshness, correct or reject a claim, and see the effect across CLI, TUI, and dashboard. Archive, expiry, changed content, revoked grant, foreign owner, stale source, or unverifiable baseline cannot become current authoritative context through another read path. Project knowledge and consented personal preferences remain available across appropriate agents; task constraints stay task-bound. Optional hybrid retrieval earns use through a measured comparison; lexical retrieval remains functional without an embedding engine.

In scope: F01–F08, F15, F18–F19, F23–F24, A02–A03, B05, E06/E19/E25, R01–R03/R05–R06/R08/R18, AP01, AP07's canonical memory administration and user search, and this phase's AP08 acceptance. This includes ordinary retrieval, historical administration, relations and derived summaries, trust, maintenance, preference migration, permissions, explanation, and live human interfaces. The report's unnumbered authority/applicability/contrary-evidence/lifetime rules (§6.8), corrections (§6.12), subject coverage (§2), and current-versus-proposed documentation (§4.4) also bind this plan.

Other plans own host discovery and lifecycle, AST graph production and dynamic architecture/UI consumers, and token optimization. This plan supplies their safe read and correction substrate; it does not implement those outcomes. No new storage engine, daemon, unprompted Git hook, automatic host capture, inferred user approval, simulated metric, or product-wide readiness claim. No phase-wide dependency on Phase 70, Phase 71, or the other memory plans.

## 2. Verified evidence and decisions

| Current source | Decision for implementation |
|---|---|
| `src/rush/memory/store.py::MemoryArtifact`, `TypedArtifactStore`, `OwnerScope`, `legacy_owner_scope`; project `.rush/memory.db` already stores typed versions, owner, trust, provenance, archive and expiry. `search_candidates` lacks archive predicate; legacy `search` has one. | Extend this schema and its shared read policy. Legacy null owner resolves to that row's project via `legacy_owner_scope`; never infer authorization from owner strings. Migrations remain additive and preserve bytes/history. |
| `retrieval.py::recall_page`, `expand_artifact`, `hybrid_page` use separate filtering/packing; `limit=2` can mark three results complete; expansion returns arbitrary base64 byte slices without Phase 63's UTF-8/hash contract. | One visibility/authority decision precedes ranking and is rechecked for direct expansion, page continuation, hybrid and relation traversal. Reuse bounded cursors and existing byte/token accounting. Preserve old base64 callers through explicit versioned encoding; new UTF-8 representation is character safe and digest verified. |
| `relations.py::add_relation` checks endpoint existence/version/cycles, not owner policy. `consolidation.py::summary_is_current` compares versions only. `maintenance.py` has a fresh-import cycle and cross-owner corroboration. | Same authorized endpoint policy applies to insert/traverse; current summary requires current visible members and contrary evidence remains discoverable. Maintenance scopes corroboration to the requested authorized owner and independent sources. |
| `trust.py::resolve_symbol_ref` resolves outside-root paths; `tools/api_diff.py::diff_symbol` can return `unknown`; defended retrieval can treat unknown as current. | Physically contain path before parse; unknown baseline, unsupported parser, parse failure or missing source hash stay `unknown`/unverified and cannot authorize a current claim. A02 containment is this phase; qualified graph population belongs to Phase 74 T01. |
| `preference_store.py::PreferenceStore` keeps project-local JSON and syncs migrated typed preference rows; `migration.py::migrate_preference_store` reads that legacy file. `setup/provision.py::default_data_root` is existing per-user platform path. | Project memory remains default. An explicit opt-in enables a personal overlay using the **same** `TypedArtifactStore` schema at `default_data_root()/user`, never an unrelated database design. Explicit local-user grant determines access; owner/agent hostname does not. Preserve legacy project preferences and reversible migration. |
| Shared C01 grant producer is Phase 73 `73-T02`'s new `src/rush/memory/authorization.py`: `default_data_root()/user/.rush/memory_authorization.json`, schema 1, monotonic `policy_revision`, consented grants and non-secret bindings. | `73-T02` owns `load_policy_readonly`, `grant_memory_scope`, `revoke_memory_scope`, and `resolve_memory_scope` plus setup consent writes. This phase consumes `resolve_memory_scope`/read-only policy on every eligible read, expansion and admin action; no second grant file or writer. Local OS-user same-user policy is authority; project readiness, host/session/owner claims and model-supplied binding text cannot grant access. A binding is non-secret and never a bearer in model properties. Restricted recipient capabilities retain their separate boundary. |
| `tools/memory.py::MemoryTool.run` is shared CLI/MCP tool; dashboard `server.py::_build_memory_section` has backend query, browse and mutation adapters while `application.js::renderMemorySection` renders generic data; `tui.py::TuiState.memory_subject` is fixed to `domain_knowledge`. | Add missing public operations once in `MemoryTool`/store; adapters pass selected project, owner and grants. Display all seven subjects and real status in all surfaces. Keep JSON-RPC/stdout and ToolResult compatibility. |

The preceding rows describe historical report findings, not all current defects. Current `TypedArtifactStore.edit` already demotes `STATED` to `DERIVED` and clears signature/promoted time (`store.py:1055–1146` primary, `1435–1527` live Phase 70); T01 preserves this behavior and closes bypasses rather than rewriting it. Live Phase 70 adds `TypedArtifactStore.open_readonly_view`, `MemoryTool(readonly_store=...)`, `_list_filtered` and read-only maintenance previews; its TUI already selects subjects and filters and exposes administration. T07 extends those real handlers, preserving useful-memory projection, delayed-response project guards, forms and receipts. Primary `_query` (`535–574`) still requires subject/query and constructs a writable store; live `_query` (`844–883`) still requires subject/query. Live `_list_filtered` is the browse foundation, not a new parallel query path. `panels.js`, `authorization.py`, all new Phase 72 tests, Phase 71's integration test and Phase 75's manifest do **not** exist in either inspected checkout; they are explicitly proposed deliverables. Phase 72 must not wait for `panels.js` to provide usable current dashboard memory controls.

Current behavior probes: primary's existing retrieval/version/relation/consolidation suites: **50 passed**, using Python 3.12 and cleared `PYTHONPATH`; live Phase 70's `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`: **1 passed**. Fresh primary maintenance import fails with `ImportError: cannot import name 'MaintenanceTask' from partially initialized module 'rush.memory.maintenance'`; import chain is maintenance → plugins package/validator → tools package → tools.memory → maintenance. Fresh live Phase 70 import prints `run_maintenance_cycle` and exits0, so preserve its existing repair. The §2.2 actual-function probe fails all four assertions in both checkouts: lost pagination, archived compact recall, archived expansion and outside-root grounding remain reproducible. These component results neither close reported read bypasses nor prove Phase 70 readiness. Commands/evidence belong to the final review receipt; changed live bytes invalidate these observations.

### 2.1 Fixed proposed interfaces and persistent state

All interfaces below are **proposed changes owned by these tasks**, not existing APIs. Reuse current store transactions, version history, relations, CAS receipts and Phase 70 strict-request validation. Do not add a framework or database.

1. **One defensive decision, T01.** Add `retrieval.py::VisibilityDecision` and `evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary", now=None, memo=None)`. `access` is the resolved scope from 73-T02, never an `OwnerScope` masquerading as permission. Return `visible`, `usable_as_current`, `freshness` (`current`, `stale`, `unknown`, `not_applicable`), `reason_codes` and `reference`. Ordinary delivery requires both booleans true. A physically contained, exact source hash/revision and supported parser establish `current`; missing baseline/hash, unsupported parser, missing source or parse failure establish `unknown`, never current. Unanchored explicit preferences have `not_applicable` source freshness and remain usable only when their own authority, applicability, expiry and access pass. Authorized inspection may show stale/unknown content with qualification; denied owner/source never exposes content, IDs, counts or existence. Source-dependent learned advice, cached memory, graph consumers, summaries and procedure applicability call the same decision before use.
2. **Identity and digest, T01/T02.** Reference contains exact `artifact_id`, `artifact_version`, canonical `project_id`, `worktree_id`, `owner_scope`, `source`, `subject`, trust/provenance and freshness. Preserve current `MemoryArtifact.content_hash` meaning: **source file hash**, not memory payload hash. Add `payload_hash` for SHA-256 of exact persisted `memory_artifact_versions.content.encode("utf-8")`; compute once on authorized writes and version it. Add nullable `payload_hash` to current/version rows and a write-authorized additive backfill. Read-only old schemas return `migration_required` with explicit upgrade action; no backfill, key creation, journal or migration on read. An unsafely unbound old version cannot become verified by hashing its currently tampered bytes. Reopening an old schema for historical inspection reports missing integrity evidence. `source_ref` retains path/symbol, revision, source digest, worktree dirty digest and parser coverage supplied by Phase 74; unsupported coverage remains unknown. No path or externally supplied digest establishes permission or truth.
3. **Strict requests, T06.** Extend Phase 70 `src/rush/mcp_support/request_models.py` operation variants, `MemoryOperation`, dispatch and registry together. `request` has `schema_version:2`; reject unknown keys, boolean-as-integer, omitted/null mismatches and simultaneous legacy + strict fields before effects. Read common fields: `subjects` (nonempty subset of the seven existing subjects), `query` (default empty for list), `owner_scope`, `sources` (nonempty subset of resolved grant), `trust_tiers`, `freshness`, `archive_mode` (`active` default or explicitly authorized `historical`), `limit` (1–100, default 20), `max_tokens` (omitted → existing `DEFAULT_MAX_TOKENS=2048`), `max_bytes` (omitted → existing `DEFAULT_MAX_BYTES=8192`), `cursor`. Both budgets are strict Python/JSON integers ≥1 (boolean, float, string, null, zero and negative rejected `E_INPUT` before effects); no new upper cap is introduced because current request validators have none. Positive integers are type-valid, then admission preflight computes minimum bytes and tokens for a complete canonical `E_BUDGET`/error envelope plus transport framing through the existing serializer and token counter, before extracting content or opening a writable store. If either cap is below that computed minimum (including `max_bytes=1` or `max_tokens=1`), reject `E_INPUT` before effects: its bounded protocol-validation error is counted separately as admission failure, never labeled in-budget or context-success. Admitted requests guarantee their complete success or `E_BUDGET` response fits both caps, including envelope/cursor/framing; no hidden extra allowance. If the required-size diagnostics themselves would exceed either admitted cap, emit only the complete canonical minimum error fields permitted by the serializer, with no content, cursor or false completion; preserve detailed required-size diagnostics only when they fit. `limit` is strict integer1–100 (omitted20; explicit null invalid). Omitted `owner_scope` resolves only the current canonical project's authorized owner from the resolved policy; when multiple owner grants could match, return `E_INPUT` requiring explicit owner instead of combining them. Explicit owner null is invalid. Omitted `sources` uses exactly that resolved grant's approved source set; empty/null/non-string entries are invalid, supplied sources must be a nonempty subset, and no grant means denied rather than an ambient wildcard. `cursor` omitted/null starts first page; supplied cursor must be nonempty string. Legacy adapters preserve prior omitted/null semantics and cannot broaden a v2 request. `history` requires `artifact_id` plus historical permission; `explain` requires exactly one of `artifact_id` or nonempty `query`. Explain returns `supporting`, `contrary`, `attempted`, `affected` evidence refs and `unknowns`; it performs no model call. Results retain ToolResult and existing fields, add schema version/refs/exclusion reasons and continuation, and retain existing error codes `E_OWNER`, `E_SCOPE`, `E_VERSION`, `E_RESTART`, `E_BUDGET`, `E_NOT_VISIBLE`.
4. **Mutation transaction, T06.** Extend current `edit`, `archive`, `delete`, `promote`, `link`, `maintain` variants rather than add browser-specific operations. All previews are read-only; apply requires `apply:true`, explicit execution permissions, current resolved policy, exact owner and current expected revisions. `archive` with `archived:false` is restore. Correction uses `edit` with `correction:{kind:"correct"|"reject"|"supersede", reason, supersedes:[{artifact_id,artifact_version}]}`; rejection appends a version with non-actionable applicability, supersession creates current replacement plus version-bound `supersedes` edge, preserving originals. Add versioned `applicability` (`pending`, `active`, `rejected`, `superseded`) and task-binding metadata to existing rows/versions, not new subjects. One `BEGIN IMMEDIATE` validates all versions, owner and scope, writes replacement/history/relations/receipt and commits atomically; any failure rolls back all effects. Acquire the existing policy CAS/physical-root serialization boundary through commit, so revoke and apply cannot interleave unchecked; lock order policy then store, shared with 73-T02. Generation advances on content/visibility changes; dependent summaries, embeddings, cached guidance and continuations are invalidated by exact ref/revision on their next read, not merely UI refresh. Receipt identity `(invocation_id,effect_id)` is persistent; same identity + same request digest returns original result, different digest conflicts, independent same-content writes remain distinct. On lock timeout or conflict return no effects, retaining user form/preview for fresh review; never blind retry with broader grant.
5. **UTF-8 and preferences, T02/T05.** Expansion selects `representation:"base64"|"utf8"` (base64 default for legacy calls). Offset/next offset are **byte offsets into exact persisted UTF-8 JSON**, never character indexes. UTF-8 mode returns `content_utf8`, `payload_hash`, artifact/version, total bytes and next offset; reject non-boundary/negative/out-of-range offsets (`E_OFFSET`), never clamp. Each slice is scalar-safe; combining marks may span slices but concatenation reconstructs exact original bytes. Apply the same preflight admission minimum before expansion; a cap below that minimum is `E_INPUT`, not an oversized purportedly in-budget `E_BUDGET`. Test both caps1, each computed minimum−1, each exact minimum and one-scalar required size: no extraction or mutation before admission, exact canonical serialized/error and transport byte/token measurements, no successful-context receipt for admission failures, and admitted error output within both caps. If full envelope plus one scalar cannot fit, return `E_BUDGET`, no cursor/false completion; provide required minimum byte/token envelope, without bypassing caps. Preference content schema keeps `{key,value}` compatibility and adds `scope` (`personal`, `project`, `task`), `authority` (`explicit`, `inferred`), `applicability`, task/project/worktree IDs, `expires_at`, source and correction refs. Same-scope explicit conflicting records remain unresolved unless a user-reviewed supersession edge establishes order; timestamps alone cannot manufacture approval. Task end excludes task record only. Personal overlay stays a distinct consented store root, using exactly the same schema.

**Implementation prerequisite route:** first integrate/rebase the reviewed Phase 70 memory/read-only/request-model changes through its normal reviewed handoff; if development remains unaccepted, implement Phase 72 in an isolated branch based on exact live source snapshot and record dirty-source digests. This authorizes no merge or source edit during plan review. Stage T01 pure defensive logic/T04 import fix independently; final grant acceptance consumes only 73-T02's policy component. Pure parser/visibility tests may run without hosts; user-visible/transport claims require their real routes. Do not substitute mock grants for final acceptance.

Authority policy: current host instruction hierarchy and current explicit user direction govern; Rush memory never manufactures instructions or grants. Within authorized memory at a task: explicit task constraint > explicit project decision/preference > consented explicit personal preference > inferred project/agent pattern. Later explicit correction supersedes earlier same-scope content, with history retained; conflicting same-priority claims are shown unresolved until user/evidence resolves them. An inference cannot promote itself to a user rule. Trust tier, source integrity, owner permission and applicability are independent; passing one never bypasses another. Personal overlay is off until consented; project overrides do not rewrite personal originals. A task record is bound to project/worktree/task identity and is not inherited by unrelated tasks. Historical/admin reads are explicit, labeled, permissioned and excluded from ordinary agent recall.


### 2.2 Runnable baseline falsification and repaired-route check

Run this exact bounded probe at either reviewed checkout root. It creates only a temporary Git project/store. Current primary observation was: first page p0/p1, complete true/no cursor; archive still returns p2; expansion OK; outside reference accepted. Those are reproduced failures, not acceptance. After T01/T02, the final assertion must pass, proving actual functions rather than fabricated predicate. Grant-integrated tests above remain separately required; this probe retains existing explicitly allowlisted legacy compatibility route.

```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python - <<'PY'
import hashlib, json, subprocess, tempfile, time
from pathlib import Path
from rush.memory.retrieval import recall_page, expand_artifact
from rush.memory.store import MemoryArtifact, TypedArtifactStore, legacy_owner_scope
from rush.memory.trust import resolve_symbol_ref
with tempfile.TemporaryDirectory() as d:
    root = Path(d) / "project"
    root.mkdir()
    outside = Path(d) / "outside.py"
    outside.write_text("def Known():\n    return 1\n", encoding="utf-8")
    source = root / "source.py"
    source.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
    for args in (["init", "--initial-branch=main"], ["add", "source.py"],
                 ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                  "commit", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    store = TypedArtifactStore(root)
    owner = legacy_owner_scope(root)
    for i in range(3):
        store.write(MemoryArtifact(
            id=f"p{i}", family="memory", subject="domain_knowledge", trust_tier="DERIVED",
            content={"text": "needle"}, source="allowed", created_at=time.time(),
            symbol_ref="source.py::Known",
            content_hash=hashlib.sha256(source.read_bytes()).hexdigest(), owner_scope=owner))
    page = recall_page(store, subject="domain_knowledge", query="needle",
                       session_allowlist=["allowed"], limit=2)
    paging_ok = (page["complete"] is False and bool(page["next_cursor"]))
    store.archive("p2", expected_version=1, scope="domain_knowledge", owner_scope=owner,
                  apply=True)
    active = recall_page(store, subject="domain_knowledge", query="needle",
                         session_allowlist=["allowed"], limit=10)
    archived = store.get_current("p2")
    expansion = expand_artifact(store, artifact_id="p2", version=archived.artifact_version,
                                session_allowlist=["allowed"])
    results = {
        "paging": paging_ok,
        "archive_hidden": [item["id"] for item in active["items"]] == ["p0", "p1"],
        "expansion_denied": expansion["code"] == "E_NOT_VISIBLE",
        "outside_denied": resolve_symbol_ref(str(outside) + "::Known", root) is False,
    }
    print(json.dumps(results, sort_keys=True))
    assert results == dict.fromkeys(results, True), results
PY
```

Expected repaired output: `{"archive_hidden": true, "expansion_denied": true, "outside_denied": true, "paging": true}`. Existing probes before correction returned false in each field. Every T01/T02 test must retain owner/source policy, exact source freshness and tamper cases in addition to this minimum check.

## 3. Dependencies, file map, and ownership

`73-T02/POLICY` first implements/independently verifies the authorization producer. `72-T01` defensive predicates can start immediately; final grant-integrated acceptance consumes that checkpoint, not completed73-T02 or host bootstrap/adapters. `72-T01` → `72-T02` then gates `73-T02/BOOTSTRAP` automatic content delivery. Both checkpoints retain original73-T02 identity and its entire outcome; this is an acyclic producer/consumer order. `72-T01` safe read/authority then gates any new automatic delivery. `72-T02` follows T01 for consistent page visibility. `72-T03` follows T01. `72-T04` can repair import independently; its promotion acceptance follows T01's authority rule. `72-T05` follows T01 for project-local work and the same narrow `73-T02` policy functions plus separately consented user-overlay grant for cross-project reads; it has no host-adapter dependency. `72-T06` follows T01–T05 for operations it exposes; a verified subset may integrate before optional hybrid. `72-T07` follows T06's exact operations, not completed Phase 70/71. `72-T08` follows T01–T02 and narrow `75-T02/EVALUATOR` live-decision/budget checkpoint for benefit claims, before75-T02 whole evaluation completion. `72-T09` follows only implemented routes and exact live lanes it claims. `74-T01` supplies qualified symbols only where this phase displays code-linked references; `75-T01` supplies shared usage receipts only for actual-use labels. Until those producers exist, this phase displays `unavailable` with reason and does not fabricate values. No whole-plan wait.

| Owner | Literal implementation files and boundary |
|---|---|
| Store/read | `src/rush/memory/store.py`, `retrieval.py`, `trust.py`, `src/rush/tools/api_diff.py`; consume `src/rush/memory/authorization.py` from 73-T02 without editing its policy loader/writers; one writer serialized with other plans. `src/rush/tools/review.py` and `src/rush/token_economy/memory_cache_gate.py` only consume same defensive/read-only adapter. |
| Relations/maintenance | `src/rush/memory/relations.py`, `consolidation.py`, `maintenance.py`, `expiry.py` only where shared visibility needs its predicate. |
| Preference | `src/rush/memory/preference_store.py`, `migration.py`, `src/rush/setup/provision.py` only to reuse `default_data_root`, `src/rush/tools/memory.py`; no platform data-root rewrite. |
| Public/app integration | `src/rush/tools/memory.py`, `src/rush/cli.py`, `src/rush/tui.py`, `src/rush/dashboard/server.py`, `src/rush/dashboard/application.js`, `src/rush/dashboard/panels.js` only if existing renderer needs a memory component, `src/rush/cli_support/rendering.py` for human output. Shared `store.py`, `memory.py`, `cli.py` edits queue behind one integration owner; no simultaneous agent writes. |
| Tests/docs | Named tests below; `docs/user-guide/working-with-ai-agents.md`, `docs/user-guide/interactive-tui.md`, `docs/reference/cli-reference.md`, `docs/architecture/rush-epistemic-memory-and-agent-substrate.md`, `docs/phase-plans/phase-63-memory-capabilities-vibecoder-plan.md`, `docs/phase-plans/MC13.md` only for truth labels, plus `docs/reports/phase-72-memory-acceptance.md`. Historical receipts stay intact and revision labeled. |

Every packet below means: implement the named change in this repository; read `AGENTS.md`, shared contract and this plan first; change only its listed paths and symbols; write failing behavior checks before production edits; run every named command; report changed paths and exact evidence. The given test names are deliverables, not assertions that files or tests already exist. Commands run at repo root with Python 3.12 and `PYTHONPATH` cleared. No implementation may treat a plan example as a current PASS. Every task's §2.1 interfaces and ordered implementation paragraph supply exact proposed contracts; all named new tests are to be written then executed. Estimates (implementation plus verification, excluding externally blocked time): T01 12–18h; T02 8–12h; T03 6–10h; T04 4–6h; T05 10–16h; T06 12–18h; T07 14–22h; T08 8–12h; T09 8–14h; total **82–128 hours**, PAS work included in T01/T06/T07/T09. These planning estimates authorize no reduced acceptance.

## 4. Requirement ledger

| Requirement | Owner and decisive result |
|---|---|
| F01–F03, A03, R01/R05/R18, AP01 | T01: archived/expired/tampered/edited/unverifiable records absent from ordinary and hybrid recall, denied on direct expansion; safe historical view labeled. |
| F05/F24, R01 | T02: exact-once continuation under count/byte/token caps; UTF-8-safe version/digest expansion plus explicit base64 compatibility. |
| F06–F07, R03/R06 | T03: owner-safe current-version edges and traversal; changed/revoked members invalidate derived summary; contradictions and originals remain. |
| F04/F08 | T04: fresh import and owner-isolated, independently corroborated maintenance without cross-owner promotion. |
| F15/B05/E06/E25 | T05: opt-in personal/project/task policy, migration and correction precedence; no cross-project private record exposure. |
| A02, AP01/AP07 canonical admin | T01/T06: promotion symbol containment; public create/edit/archive/restore/delete/propose/promote/history/relations/maintenance with consent, owner, version and exact recovery. |
| F18–F19, E19, AP07 canonical search, Phase 70 T28-D, Phase 71 P07 | T07: all-subject search, explanation, inspection and correction through live CLI/TUI/dashboard using T06, with actual keyboard/browser proof. |
| R02/R08 | T08: lexical/metadata stays complete, optional hybrid labeled and measured on held-out lexical misses with availability/cost/staleness. |
| F23, AP08 and cross-phase documentation | T09: current/proposed/evaluated claims reconciled and frozen-source acceptance, including every required phase-specific live lane. |

## 5. Ordered executable task packets

### 72-T01 — Safe read, authority and symbol containment

Implement `72-T01 safe reads, authority and symbol containment` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Current authorized evidence through every read path

Current authorized evidence through every read path.


#### Required behavior

 Implement one canonical-policy-plus-store eligibility decision for ordinary agent reads: canonical project/worktree, local grant and owner scope, explicit source allowlist, non-archived, non-expired, integrity-valid, current version, source-current or explicitly source-independent `not_applicable`, and applicable trust. Call `authorization.load_policy_readonly`/`resolve_memory_scope` against schema-1 policy before access and again on every page, direct expansion and mutation; compare monotonic `policy_revision`, canonical root/worktree, approved owner/sources/operations and revocation. A non-secret binding references policy but never grants access by itself. No policy/missing-store read creates files. A host/session string or supplied `OwnerScope` cannot grant access. Legacy explicit allowlist calls retain their established permission path without silently becoming ambient access; restricted receiver still requires its capability. Thread resolved owner/source scope from `MemoryTool` to store and retrieval; `legacy_owner_scope` handles only historical null owner rows, not a new caller's missing authorization. Apply before ranking and on each `recall_page`, `hybrid_page`, direct `expand_artifact`, and defended legacy recall. `E_NOT_VISIBLE` has indistinguishable missing/denied bodies. Both `TypedArtifactStore.edit` and legacy `update_content` atomically drop prior `STATED` authority/signature unless re-promoted from new evidence. Existing immutable history survives; only explicit historical admin mode can read excluded versions and labels why ordinary use rejects them. `resolve_symbol_ref` rejects absolute, `..`, and in-root symlink to outside before AST parse. `ApiDiffer` unknown baseline and missing/unparseable source cannot establish current evidence; distinguish unknown from stale, retain both in results.

#### Deliverables

 `src/rush/memory/store.py::search_candidates`, `scope_artifacts`, `recall`, `edit`, `update_content`, `_write_version`, `open_readonly_view` and shared eligibility helper; `src/rush/memory/retrieval.py::recall_page`, `hybrid_page`, `expand_artifact` and freshness helper; `src/rush/tools/memory.py::MemoryTool.run`, `_query`, `_compact_query` owner/source threading; `src/rush/memory/trust.py::resolve_symbol_ref`; `src/rush/tools/api_diff.py::ApiDiffer.diff_symbol`; `tests/test_phase72_memory_correctness.py::test_t01_denied_current_routes_and_authority`, `::test_t01_symbol_containment_and_unknown_freshness`. Import and consume `73-T02`'s `src/rush/memory/authorization.py::load_policy_readonly`/`resolve_memory_scope` without editing its policy file, grant/revoke writers or module. Preserve public envelope and legacy owner mapping. Do not implement a second validator in each UI.

#### Constraints

No new grant writer, duplicated policy, unsafe path parse, read constructor or implicit historical access; preserve Phase 70 demotion and all existing grant paths.

**Ordered implementation and dependencies:** T01 unit logic may precede policy integration; final policy/revocation checks require only 73-T02 authorization APIs. Extend `evaluate_artifact_visibility`/`VisibilityDecision` exactly as §2.1; `defended_recall`, legacy `recall`, compact/hybrid/expand, review citations and `token_economy/memory_cache_gate.py::check_memory_before_pack` must consume it. Add `src/rush/tools/review.py` and `src/rush/token_economy/memory_cache_gate.py` only for read-only store/access threading; reuse Phase 70 `open_readonly_view`, do not reimplement it.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Seed `a1` active, `a2` archived, `a3` expired, `b1` foreign-owner, `u1` unknown source baseline, `t1` altered signed payload. Under Alice/source-a policy ordinary IDs are exactly `[a1]`; expansion of each excluded ID is `E_NOT_VISIBLE`. Authorized historical inspection may expose `a2/a3/u1/t1` only with exact reasons, never current authority. Missing DB stays absent; old schema returns migration-required without key/journal/DDL. Pause before response, revoke policy, then release: no payload leaves old scope. Test `review` citations and cache selection, not only low-level helper.

**RED → GREEN:** Create two owners/two source scopes, archived and expired records, edited promoted and physically tampered content, bad signature, unavailable Git baseline, missing content hash, symlink/absolute/traversal references. Assert exact row IDs never enter ordinary/compact/hybrid result or expansion, old authority is gone after edit, historical inspection marks exclusion, unknown remains unknown, and denied response leaks no ID/existence. Use 73-T02/POLICY's proposed exact fixture call `grant_memory_scope(project_root=root, owner_scope=owner, approved_sources=["source-a"], allowed_operations=["write","ask","expand","list","bootstrap"], expected_policy_revision=0, consent=True, data_root=tmp_path/"user-data")`; call `resolve_memory_scope(project_root=root, operation="ask", owner_scope=owner, requested_sources=["source-a"], data_root=tmp_path/"user-data")`. Resolved fields are `access` (`read`, `write`, `denied`), `reason`, `grant_id`, `policy_revision`, canonical `project_id/worktree_id`, owner, approved sources and operations; rejected binding has no usable grant. Do not override OS identity. Call real grant/revoke writers in test setup; change `policy_revision` or revoke between pages and prove next read closes. Forge host/session/binding, change project/worktree, omit policy and inspect missing-store read; assert zero content and no file creation. Check via `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t01 -q` and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_retrieval.py tests/test_phase61_trust.py tests/test_memory_versions.py -q`.

#### Completion

 Every listed route uses same current eligibility, adversarial cases pass, and only listed files change for T01.

### 72-T02 — Honest pagination and exact UTF-8 recovery

Implement `72-T02 exact-once paging and UTF-8 recovery` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Every eligible record and exact byte sequence remains recoverable

Every eligible record and exact byte sequence remains recoverable.


#### Required behavior

 `recall_page` cursor records first unconsumed candidate when item count, token or byte limit stops output; `complete` means no eligible candidate remains, not merely scan cap exhausted. Bind cursor to project, worktree, subject/query, allowed sources/owner, ranking version and store generation; changed visibility/generation returns restart instead of duplicate/missed/foreign rows. Preserve bounded scan and truthful truncation. Add versioned `utf8` expansion mode returning complete Unicode scalar slices, artifact ID/version, offset/next offset, stored-content SHA-256, length and completion; reassemble exact original bytes and verify hash. Keep existing `content_base64` mode explicitly selectable for current callers; do not silently change its shape. `E_BUDGET` leaves no misleading complete page. Every page rechecks T01 eligibility.

#### Deliverables

 `src/rush/memory/retrieval.py::recall_page`, `_encode_cursor`, `_decode_cursor`, `expand_artifact`; `src/rush/tools/memory.py::_compact_query` request/response validation; `src/rush/memory/transport.py` only receiver decode/verification for the new mode, coordinated with 73-T05/T09 under C09; `tests/test_phase72_memory_correctness.py::test_t02_exact_once_paging_and_utf8_recovery`; `tests/test_memory_handoff.py::test_t02_receiver_digest_reconstruction`. Preserve base64 callers and token/byte caps.

#### Constraints

Preserve legacy base64 shape and byte-offset semantics; no skipped oversized candidate, clamped offset, false completion, scope restart hidden as empty, or read-side key creation.

**Ordered implementation and dependencies:** Follow T01. Cursor includes resolved `policy_revision`, project/worktree, owner/sources/subjects/all filters, ranking and store generation; expiry eligibility time is rechecked on each response. Hold stable store snapshot for one page, revalidate revision/generation before emitting; mismatch returns `E_RESTART` without items. Advance scan offset only for candidates consumed, including rejected corrupt rows; first eligible oversized item returns `E_BUDGET` with same resume position and required minimum, so retry with adequate approved budget recovers it. Never emit repeating zero-progress OK pages. Add `representation`/`payload_hash`/boundary validation exactly §2.1.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Seed IDs `p1,p2,p3` all containing `needle`. `limit=2` returns p1/p2 in deterministic rank/ID order with `complete:false`, next page p3 then `complete:true`; concatenated IDs equal all3 with no repeats. Seed 513 matches and two interleaved corrupt rows; all 513 recovered exactly once. Stored JSON text contains `🙂é𐍈`; every allowed byte offset yields exact UTF-8 reconstruction and SHA-256; offsets inside scalar fail `E_OFFSET`, digest alteration fails receiver validation. Grant revocation/expiry or any filter/source/generation drift refuses continuation. Envelope-plus-scalar shortage yields no-progress `E_BUDGET`, later adequate budget retrieves same record.

**RED → GREEN:** Three matches at `limit=2`; >512 candidates; one record larger than budget; changed grant/source/store between pages; malformed/foreign cursor; emoji, combining mark and four-byte characters at every page boundary; altered page digest and stale version. Assert exact-once IDs, truthful next cursor/complete, bounded output, exact bytes/hash, denial after revocation and receiver rejection of altered content. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t02 -q` and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_handoff.py tests/test_memory_retrieval.py -q`.

#### Completion

 Every eligible match can be recovered once, exact artifact bytes reconstruct in both declared modes, and only listed files change for T02.

### 72-T03 — Relations and derived-memory validity

Implement `72-T03 authorized relations and current derived summaries` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: A derived claim cannot outlive visible supporting evidence

A derived claim cannot outlive visible supporting evidence.


#### Required behavior

 `add_relation` checks both endpoint versions, same canonical namespace, owner/scope authorization and T01 eligibility under an explicit grant inside the existing transaction; preserve cycle prevention. `related_artifacts` checks root and each hop immediately before return, including archive, expiry, integrity, freshness, version, owner and source. An invisible neighbor exposes neither ID nor count. `summary_is_current` and actionable retrieval require every member's current visible exact version; change, archive, expiry or revocation invalidates or qualifies derived summary before use. Contradictions, counterexamples and originals persist in history; a summary cannot increase member authority.

#### Deliverables

 `src/rush/memory/relations.py::add_relation`, `related_artifacts`; `src/rush/memory/consolidation.py::summary_is_current`; `src/rush/memory/retrieval.py` derived-summary eligibility adapter; `src/rush/tools/memory.py` relation-operation grant threading; `tests/test_phase72_memory_correctness.py::test_t03_owner_safe_edges_and_summary_invalidation`; `tests/test_memory_relations.py`, `tests/test_memory_consolidation.py` only if existing assumptions must change. No new graph store.

#### Constraints

No extra graph/database, foreign edge leak or authority increase. Root and every hop share T01 eligibility; historical traversal never supplies actionable context.

**Ordered implementation and dependencies:** Follow T01. Extend `add_relation`/`related_artifacts` and `summary_is_current` with resolved `access`; canonical public `link` passes it. Recheck policy under shared mutation lock and both endpoints under transaction. Empty/malformed `member_versions` cannot certify a derived summary as current. Bind summary member refs to exact payload/source versions; derived authority cannot exceed weakest supported member. Correction/rejection invalidates all dependent consumers on next read.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Alice owns s1/m1, Bob owns m2. Alice linking s1→m2 returns `E_NOT_VISIBLE` and SQL edge count remains0. s1→m1 succeeds once; inverse supersedes cycle returns existing `E_INPUT` and edge count remains1. Archive/expire/revoke/tamper/edit m1: summary `member_versions={m1:1}` is unusable; ordinary recall omits s1 and relations omit m1 with no invisible count. Permissioned history retains original members plus contrary evidence.

**RED → GREEN:** Two owners each with same subject, foreign edge, cross-project ID, stale endpoint, cycle, revoked source, tampered/archived/expired neighbor, changed member and contradiction. Assert rejected insert writes zero edges, traversal leaks no excluded IDs, invalid summary cannot be ordinary evidence, original/contradiction still inspectable under historical permission. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t03 -q` and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_relations.py tests/test_memory_consolidation.py -q`.

#### Completion

 Edge insertion and traversal obey same eligibility as recall, current summary cannot outlive eligible evidence, and only listed files change for T03.

### 72-T04 — Maintenance import and owner-isolated corroboration

Implement `72-T04 fresh maintenance imports and owner-scoped corroboration` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Maintenance imports independently and changes only authorized evidence

Maintenance imports independently and changes only authorized evidence.


#### Required behavior

 Break `maintenance.py` import cycle within existing modules so fresh interpreter imports `run_maintenance_cycle` directly. `run_maintenance_cycle` continues to require `OwnerScope`; pass the caller's explicit source allowlist into candidate and corroboration queries, both using identical authorized owner/namespace and independent-source criteria. Never promote from agent/user name equality, duplicate source, foreign owner or a source denied by grant. Row failure remains isolated and reported; lock lease/loss semantics and expiry sweep remain intact. No maintenance read creates unrelated store.

#### Deliverables

 `src/rush/memory/maintenance.py::run_maintenance_cycle`, `_mutate_row`, `_SELECT_SQL` and import boundary; `src/rush/tools/memory.py::_run_maintain` to pass the permitted source allowlist; `src/rush/memory/store.py` only shared owner predicate required by maintenance; `tests/test_phase72_memory_correctness.py::test_t04_fresh_import_and_scoped_promotion`; `tests/test_phase62_maintenance.py` only to adjust existing contract. No alternate maintenance runner.

#### Constraints

No alternate runner, wildcard owner, foreign corroboration, source-label-only independence, swallowed lease loss or hidden preview writes.

**Ordered implementation and dependencies:** Import regression can start independently. Preserve live Phase 70's import-order repair, which already passes fresh-process import; if integrating primary's older chain, define `MaintenanceTask` before plugin imports or use local `PluginTrustStore` import at `_mutate_skill_admission_check`. Do not add redundant refactor when existing repair is present. Preserve real Phase 70 preview/selected-ID/expected-revision/grant adapters. Candidate and `_candidate_sources` SQL bind exact owner/root/source grant plus active/current/payload checks. Independent source means distinct grounded source identity/provenance, not two agent labels or duplicate imported copies. Lock loss stops further rows and reports unprocessed IDs; already committed row receipts remain accurate. Add policy-lock before existing mesh lease then SQLite lock in fixed order.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Fresh interpreter import prints exactly `run_maintenance_cycle`. Alice and Bob each have one candidate anchored to same real contained symbol: Alice promotion processed1 changed0; Alice two duplicate provenance copies still changed0; Alice two independently grounded allowed sources may promote1; denied or foreign source adds0 corroboration. Corrupt Alice row reports its exact ID, other valid rows preserve truthful counts; lease loss commits no later row. Preview leaves missing DB absent and apply expected-version drift changes0 rows.

**RED → GREEN:** Fresh `python -c` import before `tools.memory`; Alice/Bob one candidate each; Alice two records from one source; Alice two independent allowed sources; legacy owner; denied source; one corrupt row; lease interruption. Assert only eligible same-owner independent evidence promotes and exact processed/changed/errors remain truthful. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c 'from rush.memory.maintenance import run_maintenance_cycle; print(run_maintenance_cycle.__name__)'`, `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t04 -q`, and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase62_maintenance.py -q`.

#### Completion

 Fresh import and permitted real maintenance operation pass; no cross-owner authority gain; only listed files change for T04.

### 72-T05 — Consented layered preferences and migration

Implement `72-T05 consented layered preferences and reversible migration` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Correct guidance reaches authorized tasks without cross-project leakage

Correct guidance reaches authorized tasks without cross-project leakage.


#### Required behavior

  Keep project preferences in current project store. Personal overlay is opt-in under a **separate** `73-T02` local-user grant whose approved operations/sources expressly include overlay read for this canonical project/worktree; project-memory grant alone cannot expose it. Back overlay at literal `default_data_root()/"user"/".rush"/"memory.db"` through `TypedArtifactStore(default_data_root()/"user")`, reusing its schema and APIs, not introducing another memory implementation. `OwnerScope("user", str((default_data_root()/"user").resolve()))` labels rows but does not authorize reads; `authorization.resolve_memory_scope` rechecks user overlay grant/revision on each read and expansion. No global row is copied into project DBs. Only explicitly user-confirmed personal rules may enter overlay; project/task preferences never migrate upward automatically. Enforce instruction hierarchy and authority before scope: every inferred convention is advice only and cannot override any applicable explicit rule. Among applicable explicit rules, task > project > personal; same-scope conflict needs later user-reviewed supersession, otherwise remains unresolved and surfaced. Task constraint key includes project/worktree/task ID and expiry or explicit end. Agent host string is attribution, never authority. Existing `PreferenceStore` reads remain compatible; migration from `.rush/preferences.json` and `.migrated` is idempotent, compare-and-swap safe, and retains originals/backups until verified. Denied/disabled overlay yields project-only result, not leakage or a hidden write. Correction/rejection retains original, reason, source and affected downstream references.

#### Deliverables

 `src/rush/memory/preference_store.py::PreferenceStore` and scoped resolution; `src/rush/memory/migration.py::migrate_preference_store`; `src/rush/memory/store.py` only owner/version fields needed by existing schema; `src/rush/tools/memory.py` preference/correction operation; `tests/test_phase72_preferences.py::test_t05_scope_precedence_consent_and_migration`. Consume `73-T02`'s `authorization.py::resolve_memory_scope` and use `src/rush/setup/provision.py::default_data_root` unchanged; their source and consent writers belong to `73-T02`. No automatic personal import from native host memory.

#### Constraints

No overlay reads before separate consent, task leakage, inferred personal preference, upward migration or overwrite of user originals. Preserve PreferenceStore key/value compatibility.

**Ordered implementation and dependencies:** Follow T01; consume only 73-T02 narrow policy component. Use §2.1 versioned preference schema and canonical correction transaction. Migration writes all selected rows in one authorized CAS transaction, verifies count/content, then renames original atomically to `.migrated`; failure leaves original usable, already present backup never overwritten. Record migration source digest/id and existing tombstones. Replaying same origin changes0 rows and cannot resurrect deleted key. Read `PreferenceStore` without `_ensure_file` write on absent path; write initializer remains explicit.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Personal explicit `format=compact`, ProjectA explicit `format=wide`, ProjectB no override, TaskA explicit `format=plain`: chosen values plain/wide/compact at applicable task/project scopes; ended TaskA returns wide. Personal explicit compact plus inferred project wide and inferred task plain still selects compact, with both inferences advice only; inferred wide also cannot replace explicit compact at equal scope. Alice correction reject/reversal is retained; held-out wording `verbose panels` retrieves applicable rejection while unrelated `wide integer` stays allowed. Disabled/revoked overlay yields project-only; foreign B private row never returned to A. Legacy `{format:compact}` replay inserts1 then0, deletion plus backup replay stays absent; concurrent edit returns exact `E_VERSION` and original stays intact.

**RED → GREEN:** Two projects/agents share consented personal rule but conflicting UI/project rules remain isolated; explicit user reversal; inferred repeated pattern; task end; declined consent; separate project-versus-overlay grant; revoked overlay policy revision; foreign host identity; legacy file and replayed `.migrated` backup; concurrent correction. Assert selected rule and provenance/why, zero foreign content, exact versions, no resurrection/duplication, and no file creation on read-only paths. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_preferences.py tests/test_memory_compatibility_regressions.py -q`.

#### Completion

 Same-project agents resolve same permitted choices, authorized personal preferences cross projects without private leakage, migrations replay safely, and only listed files change for T05.

### 72-T06 — Canonical public query and administration

Implement `72-T06 canonical memory query, correction and administration` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: All public surfaces share real scoped state and transaction results

All public surfaces share real scoped state and transaction results.


#### Required behavior

 Complete shared `MemoryTool` operations for all seven subjects. Extend existing `list`/`ask`/`expand`/`related`/`write`/`edit`/`archive`/`delete`/`promote`/`maintain`; add strict `history` and `explain` request variants, and use versioned `edit` plus `link` for correction/rejection/supersession. Empty-query `list` browses; nonempty `list` searches. Its request accepts subject(s), owner kind/ID, source, trust, freshness, archive mode and bounded cursor; result names exact `artifact_id`, `artifact_version`, `content_hash`, canonical project/worktree, provenance, current/unknown/stale reason, exclusion labels and next cursor. `history` takes exact ID and authorized historical mode; `explain` takes a cited selected ID or query and returns structured supporting/contrary/attempted records and unknowns, never generated rationale. Historical view requires explicit permission. Mutation requires exact selected owner, ID, expected version/revisions, reviewed `apply:true`, and existing grant; refusal/conflict leaves original bytes and user-entered form content. Repeated invocation/effect ID is idempotent; matching content alone does not dedupe independent writes. Promotion creates new candidate/decision and preserves immutable original. Schema2 result `raw` is an object with `schema_version`, `items` (each carries `reference` plus existing compatible identity fields), `next_cursor`, `complete`, `code` and `unknowns`; history/explain/import result variants have their named evidence/version/mapping fields and use same outer ToolResult. Correction reports affected relations/summaries/task guidance and invalidates future ordinary recall as applicable. Run through same `MemoryTool` for CLI/full MCP/dashboard/TUI; restricted memory-session MCP stays restricted. Retain ToolResult and existing operation compatibility; no browser-only rows or independent admin database.

#### Deliverables

 `src/rush/tools/memory.py::MemoryTool.run`, `_query`, `_compact_query`, `_run_maintain`, edit/archive/delete/promote dispatch; `src/rush/memory/store.py::scope_artifacts`, `search_candidates`, `apply_import_records` (new), version/mutation adapters; `src/rush/mcp_support/request_models.py` strict variants and validators plus `src/rush/mcp_support/tool_registry.py` full-profile registration/schema for added operations; `tests/test_phase72_memory_public.py::test_t06_query_admin_permissions_and_versions`; `tests/test_memory_public_contract.py` for compatibility. C01 grants from Phase 73 T02 are consumed, never reinvented.

#### Constraints

No duplicated permission/admin dispatcher, trust retagging, mixed strict/legacy forms, content-equality dedupe or restricted-profile administration.

**Ordered implementation and dependencies:** Follow T01–T05 for exposed operations; optional hybrid does not block admin. Implement §2.1 request/result and transaction contracts in `src/rush/mcp_support/request_models.py` (Phase 70 dynamic `_memory_spec`, `_memory_tag`, `memory_request_model_keys`), tool dispatch/registry and store. Existing seven subjects are active_context, episodic, preference, failure, architectural_decision, domain_knowledge, skill_pattern; advanced repair/procedure operations remain content kinds, not undeclared subjects. History returns exact immutable versions with owner/source permission before content. For PAS import expose `TypedArtifactStore.apply_import_records` proposed seam through one existing SQLite transaction; capsule codec/import orchestration remains73-T09.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Seed each seven subjects1 record Alice plus Bob7. Alice browse across subjects returns exactly7; query `needle` returns exact matching IDs; owner filter never grants Bob. Edit selected r1@1 applies→r1@2 with old version retained, retry identical effect returns same receipt and no r1@3; different request digest under same effect returns conflict. Restore uses archive archived=false. Delete {r1:2,r2:1} with stale r2 version rolls back both. Promotion creates separate candidate/decision IDs and original r1 content/version/trust unchanged. Explain absent rationale returns unknowns, not invented text. Restricted-session MCP admin request rejects and DB digest stays unchanged. Full stdio MCP and CLI return same serialized refs/error codes. Omitting budgets selects2048/8192; each of true,1.5,"2048",null,0,-1 for either budget returns `E_INPUT` with no filesystem/SQLite changes. Omitted sources/owner resolve exactly one approved policy scope; null/empty source and ambiguous owner reject, denied grant never widens scope.

**RED → GREEN:** Empty store/no DB, each subject, two owners, historical selection, conflicting edit, denied grant, archive/restore, delete with two expected revisions, promotion without changing selected original, rejection, correction downstream impact, restricted receiver attempting admin, CLI/MCP parity. Assert no file creation on read, exact changed version/receipt only on approved apply, same errors/body across public transports. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_public.py tests/test_memory_public_contract.py tests/test_phase61_memory_tool.py tests/test_mcp.py -q`.

#### Completion

 Canonical operation covers every named action and scope; all transports use it without broadened grants; only listed files change for T06.

### 72-T07 — Search, correction and explanation in CLI, TUI and dashboard

Implement `72-T07 complete user memory search, correction and explanation` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: CLI, keyboard TUI and browser expose same authorized evidence

CLI, keyboard TUI and browser expose same authorized evidence.


#### Required behavior

 CLI human and JSON output show subject, owner, source, trust, freshness, version, citation and next action; `rush memory` can browse without query and follow page/inspect/history/related/correction. TUI offers all seven subjects, owner and filter controls, list/selection/expansion/history/correction, preserved keyboard focus and entered content on conflict. Dashboard renders actual search/owner/archive/freshness filters, paginated selection, exact UTF-8 expansion, relation/evidence explanation and canonical mutation forms instead of JSON dump. For “why,” “what tried,” and “what stale,” show cited exact records, contrary evidence, alternatives, unknown gaps and affected code refs where real; absent rationale says unknown. Render hostile content as text. Each interface distinguishes absent store, empty, denied, stale, expired, revoked, partial, server error, and conflict, with a concrete retry/refresh/review action. No auto-approval or read-side initialization.

#### Deliverables

 `src/rush/cli.py` memory commands; `src/rush/cli_support/rendering.py`; `src/rush/tui.py::TuiState`, `_memory_refresh`, `_render_memory_admin`, `_handle_memory_key` and existing memory handlers; `src/rush/dashboard/server.py::_build_memory_section`, `_dispatch_memory_query` and existing memory action adapters; `src/rush/dashboard/application.js::renderMemorySection`, `switchSection` memory query path; `src/rush/dashboard/panels.js` only memory panel composition; `tests/test_phase72_memory_ui.py::test_t07_shared_user_journey`; `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`; `tests/test_phase71_dashboard_integration.py::test_memory_panel_owner_version_lifecycle`; `tests/test_dashboard_memory_tokens.py` memory-specific cases. Use T06 API, not parallel frontend semantics.

#### Constraints

Reuse Phase 70 TUI controls/read-only adapters and current dashboard render path. No generic JSON as final UX, unsafe HTML, inaccessible form, synthetic status or reliance on unimplemented Phase71 panel.

**Ordered implementation and dependencies:** Follow T06; consume receipt APIs only as available, with unavailable status otherwise. Current files are `application.js`/`server.py`; create `panels.js` only as Phase71 P07 integration when its shell lands, keeping current route usable first. Add bounded accessible controls with associated labels, status/live-error region, stable focus after paging/conflict, escape/cancel, keyboard-only submit/selection, text-safe hostile content, desktop/mobile responsive layout and reduced-motion behavior. Current test_t28d journey is baseline, extend its real keyboard/backend assertions; separate `_MemoryRunSpy` layout checks cannot prove mutation persistence.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Seed both owners and seven subjects; select every subject by real key events, query needle, next page, inspect exact version, correct/reject and reload: CLI/TUI/browser displayed IDs/versions equal persisted MemoryTool results. Concurrent edit keeps form text and emits version conflict; project switch during request discards foreign late response. Tab reaches search/filter/list/inspect/edit controls, Enter submits and Escape cancels with0 writes; focus returns to selected record. Hostile `<img onerror=...>` visible as literal text and no event fires. Mobile 390×844 and desktop1280×800 retain controls; reduced motion preserves progress state. Missing/denied/corrupt/empty/unknown/expired/revoked states have distinct reason and concrete action.

**RED → GREEN:** Run two real owners and all seven subjects through CLI, terminal keyboard and browser. Search/paginate, select exact version, expand/historical inspect, correct/reject/supersede, archive/restore/delete, deny grant, stale selected version, revoked source, hostile HTML and interrupted refresh. Compare displayed IDs/versions and persisted state to `MemoryTool`; verify no query falls to false empty or JSON-only output. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_ui.py tests/test_phase70_tui_usability.py -k 't07 or t28d' -q` and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase71_dashboard_integration.py tests/test_dashboard_memory_tokens.py -q`. Complete actual PTY keyboard and browser desktop/mobile walkthrough on installed/current app; capture identities, actions, states and observed results in T09 report.

#### Completion

 User can perform every listed action through each applicable interface; Phase 70 T28-D's canonical+terminal requirements and Phase 71 P07's dashboard requirements retain their own full acceptance, including their additional conditions; only listed files change for T07.

### 72-T08 — Evaluate optional hybrid retrieval

Implement `72-T08 scope-safe optional hybrid retrieval and honest paired evaluation` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Optional retrieval earns benefit claim through matched real tasks

Optional retrieval earns benefit claim through matched real tasks.


#### Required behavior

 Reuse `retrieval.py::hybrid_candidates`/`hybrid_page` and installed embedding configuration. Apply T01 eligibility before vector scoring; exact version/content hash invalidates stale embeddings. No engine, network denial, invalid vectors or timeout returns labeled lexical fallback with precise reason, not hybrid success. Compare lexical, metadata and optional hybrid on predeclared held-out paraphrase/lexical-miss tasks using identical corpus, allowlist, grants, item/token/byte budget and relevance judgments. Record recall@k, false inclusion, unauthorized/stale inclusion, latency and full embedding/retrieval cost; no automatic promotion of hybrid or new mandatory model. A hybrid candidate cap or no cursor stays an explicitly labeled incomplete result until a real paged route proves completeness; never claim exhaustive retrieval from capped pool.

#### Deliverables

 `src/rush/memory/retrieval.py::hybrid_candidates`, `hybrid_page`; `src/rush/memory/store.py` embedding invalidation only if missing; `tests/test_phase72_memory_hybrid.py::test_t08_scope_fallback_and_heldout_relevance`; `scripts/benchmarks/memory.py` existing scenario harness only, after Phase 75 T02 real-decision/budget repair; add Phase 72 held-out paraphrase/lexical-miss, irrelevant-neighbor and scope/freshness cases to `tests/fixtures/phase75/task_manifest.json` without removing or changing its other required base families or variants; results in `docs/reports/phase-72-memory-acceptance.md`. No new benchmark framework.

#### Constraints

No mandatory embeddings/provider/model, network without grant, synthetic relevance or promotion from capped retrieval. No invented successful benchmark route.

**Ordered implementation and dependencies:** Follow T01/T02, then only75-T02 real-decision/budget repair for quality claims. Declare dataset freeze before observations; task manifest adds Phase72 cases without replacing75 baseline. Existing `scripts/benchmarks.run` flags shown below are proposed75-T02 deliverables, NOT runnable current runner capabilities. Before executing, assert runner help includes each planned flag and select real provider route consented in both arms. Missing route leaves benchmark evidence open; policy/unit implementation still completes.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Frozen corpus:12 literal positives,12 paraphrase-only positives,12 irrelevant near-neighbors,4 denied-owner,4 stale-hash and4 revoked-source negatives. Hold relevance judgments and budgets fixed; recall@k = judged relevant returned / judged relevant total, unauthorized/stale inclusion must0 in every arm. Record each case result/cost/latency/fallback, including worse/equal results; never label lexical fallback hybrid. No engine/NaN/wrong vector dimension/timeout returns lexical with reason. Edit version invalidates old embedding;512+ pool reports incomplete until real paged recovery. Evaluation arms differ only retrieval strategy, route/model/seeds/grants/corpus fixed.

**RED → GREEN:** Seed paraphrases absent from lexical FTS, irrelevant near neighbors, changed version, denied source, missing engine, timeout and 512+ pool. Assert eligibility first, fallback status, no stale embedding use, exact budget, negative/neutral/positive measured comparisons all retained. Run `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_hybrid.py tests/test_memory_hybrid.py -q`. After `75-T02` supplies its actual-decision route and held-out manifest, run paired commands on identical frozen corpus/model/grants/seeds: `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route openai-codex-oauth-cli-live --allow-live-route openai-codex-oauth-cli-live --task-manifest tests/fixtures/phase75/task_manifest.json --variant current --seeds 1,2,3 --output .scratch/phase-72-memory-eval/current` and `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route openai-codex-oauth-cli-live --allow-live-route openai-codex-oauth-cli-live --task-manifest tests/fixtures/phase75/task_manifest.json --variant hybrid --seeds 1,2,3 --output .scratch/phase-72-memory-eval/hybrid`. `anthropic-claude-code-live` is the alternate only when that route is explicitly granted and the same route is used in both arms. Record route/executable, exact commands, manifest/dataset digest, evaluator, quality, cost and unknowns in T09 report. Component fixtures test policy but cannot close retrieval-quality benefit.

#### Completion

 Hybrid remains optional with measured benefit/cost and honest failure/truncation states; unexecuted real-provider lane remains open, not a pass; only listed files change for T08.

### 72-T09 — Truthful docs and live acceptance

Implement `72-T09 truthful documentation and frozen live acceptance` in `rush-cli` in the current working directory.

Read `AGENTS.md`, this plan §2.1, `docs/phase-plans/memory-program-contract.md` and `docs/user-guide/working-with-ai-agents.md` first; they are binding.

#### Feature: Every published claim names route, revision and actual observed evidence

Every published claim names route, revision and actual observed evidence.


#### Required behavior

 Reconcile architecture proposal, Phase 63/MC13 historical claims, current API/transport/client matrix and this phase's actual implemented/evaluated routes. Mark each claim proposed, implemented, integrated, evaluated, or live-verified with revision. Preserve old receipts and explain superseded verdicts; do not rewrite history into success. Document user goal, minimum consent/input, all-subject search and correction, visible authority/provenance, denied/stale/recovery states, exact CLI/MCP/TUI/dashboard examples only after executing them. Freeze source bytes before final verification. Real acceptance uses two permitted agents on same project and two projects with consented personal overlay; one agent writes/corrects, another recalls exact authorized revision, acts on it and identifies stale/denied evidence. E06/E25 live cases include held-out rewording of an explicitly rejected approach, an unrelated lexical lookalike and later explicit reversal: second agent selects allowed alternative only in affected scope, cites rejection ref, permits unrelated case and honors reversal. Retrieval hits alone do not close that behavior. Test actual browser and PTY states; existing Phase 70/71 broader acceptance remains separately open unless its full contract passes.

#### Deliverables

 `docs/reports/phase-72-memory-acceptance.md` with source hash, commands, test results, platform/client versions, consent/grants, redacted IDs/versions, screenshot/terminal observation references only if captured, failures and exact blockers; user/documentation paths in §3; `tests/test_phase72_memory_acceptance.py::test_t09_integrated_route_and_scope` for local integration. No agent-secret content in receipts.

#### Constraints

No product readiness from plan bytes/unit suite, no erased historical receipts, unavailable native route counted as pass or unsupported installed version silently tested.

**Ordered implementation and dependencies:** Follow all owned implemented routes including §8 PAS. Freeze source tree digests, build/installed executable hash and versions before tests. Resolve source versus installed parity explicitly; changed dirty70 bytes invalidate affected observations. Record platform/client grants/commands/results/errors and independent plan-vs-code check. Run current supported macOS/Linux/Windows native lanes demanded by consumed Phase70/71 contracts; absent runner stays exact external blocker, not closed. Capture screenshot evidence only if separately requested; text browser/PTY receipts are sufficient when capture unrequested.

#### Checks to run before reporting

**Concrete fixture and exact acceptance:** Two agents A/B in same authorized project: A writes r1@1, B receives exact1 and acts on it; A corrects to2, B subsequent read returns2 and rejects cached1. Two projects share only consented personal key; each project's private row absent from other. Actual stdio MCP init/tools/call, installed CLI, PTY and desktop/mobile browser use same IDs/versions; revoked grant blocks next use. PAS forged verification remains imported/pending until local applicability review; confirming intended constraint never confirms source test success. Full test/ruff gates preserve native Phase70/71 open results and report one exact blocker per unavailable lane.

**Checks:** Run T01–T08 affected commands on frozen bytes, then `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version` (must print 3.12), `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m ''`, `rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts`, and `rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts`. Also run `rtk proxy uv run --python 3.12 --extra dev mypy src/rush`, `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check`, and `rtk git diff --check`; preserve exact failed checks as blockers rather than substituting a narrower command. Run installed CLI/MCP, PTY, browser desktop/mobile and personal-overlay cases named above. Review plan ledger against actual files and AST calls before accepting green tests. Do not repeat unchanged passing checks without a concrete failure or drift.

#### Completion

 Each claim has current evidence and every owned requirement has a passing exact route; unmet native, benchmark, Windows, browser or cross-agent lane stays named open. Only listed docs/test files change for T09.

## 6. Failure, recovery, risks, and stop conditions

Read errors never initialize a missing DB, silently retry with broader scope, or substitute a stale/currently excluded item. Cursor drift returns restart with filters preserved; version conflict retains entered edits for review; tampered evidence is quarantined from ordinary use while historical inspection remains permissioned; unavailable embedding engine returns labeled lexical result; failed migration retains original file and exposes exact retry. Revocation blocks subsequent pages and direct expansion. A denied personal overlay remains off without changing project records. Maintenance row error reports exact affected ID without promoting from partial evidence.

Stop an acceptance claim on unauthorized or cross-owner exposure, stale/tampered `STATED` output, lost page, incorrect UTF-8/digest reconstruction, hidden write, changed source bytes during verification, or a UI claim without actual browser/terminal evidence. Repair offending route, refreeze and rerun affected checks. External provider/host availability blocks only its named lane. Do not turn unavailable into passed, delete user memory for recovery, or weaken permissions to make a demo work.

Main risk is divergent policy across old/new reads. T01 makes eligibility shared and T03/T06 reuse it. Second risk is authority confusion across personal/project/task layers; T05 records source and correction lineage, T07 shows it. Third is apparent retrieval benefit from unfair baseline or partial pool; T08 uses held-out matched tasks and reports costs/truncation. Concurrent plan edits to `store.py`, `memory.py` or `cli.py` require one integration writer and rerun of affected contract tests.

## 7. Reconciliation with existing work and readiness

Phase 70 T18/T20 supply useful-memory projection and permission/result semantics. T28-D's full terminal memory administration is implemented by T06 canonical operations plus T07 terminal route; its broader T28-F/Phase 70 gates are not implied by this plan's narrower checks. Phase 71 P07 owns the dashboard memory UX and live browser acceptance; T07 performs that exact memory work against T06, retaining its owner/version, promote, hostile-content and reload checks. AP07 activation/connection status belongs to Phase 73; this phase displays its real receipt producer once present and shows unavailable until then. AP08 is distributed: T09 verifies this phase's whole route, while other phases verify their own host/learning/token claims. F23 is coordinated here; each other phase documents only its actual new claims.

This plan can start at T01 and T04 on current source. Release/readiness requires all T01–T09 behavior and owned live evidence; plan authorship itself changes no product behavior. Cross-phase whole-system confirmation is recorded by participating concluding tasks under shared C08/C09, not delegated to an unspecified later phase.

## 8. PAS integration: imported evidence and user control

User-requested addition, 2026-09-25, implementing recommendations PAS01/PAS04 from the [PAS comparison](../reports/pas-agent-portable-memory-comparison-2026-09-25.md). This section extends T01/T06/T07/T09; it removes none of their original requirements. Phase 73-T09 owns the portable format, codec, export/import orchestration and managed bridge. This phase owns canonical eligibility, mutation and user review; no duplicate importer or permission store.

**Required behavior:** Every Rush/PAS import is external evidence. The current local grant determines destination owner, project/worktree and permitted operation; source owner, author, timestamps, asserted completion and claimed trust remain provenance only. Imported explicit constraints/decisions appear as pending applicability until the current user confirms them through existing review/promotion semantics. An imported `verified`, `completed` or `STATED` assertion never grants local verified authority. Source anchors are unknown until validated against exact local content/revision; matching paths, branch names or a digest supplied by the same external file are insufficient. Confirming a constraint does not also certify its source's test outcomes.

`preview_import` performs read-only schema/hash/containment/policy validation and returns exact proposed records, destination mapping, collisions, redactions, unresolved source anchors and required consent. It creates no database, lock, key or journal. Bind preview to capsule bytes/digest, destination root/worktree, current policy revision, selected record set and relevant existing artifact versions. `import` with explicit apply uses that binding, rechecks current grant and source bytes, and applies one atomic version-checked transaction through the canonical store. Drift returns conflict with zero partial writes; keep preview/user choices for refresh. Repeated invocation/effect ID is idempotent; a distinct import never silently replaces an existing local constraint or evidence version. Preserve foreign origin IDs in provenance and use separate local artifact IDs. Corrections and contradictions remain inspectable instead of last-writer-wins merging.

Export applies the same owner/source/subject/visibility policy before selecting records. User-wide preferences require their existing separate overlay grant and explicit inclusion in this export; there is no blanket personal-memory export. Grants, capability tokens and credentials never enter a capsule or managed block. Exported selections remain unchanged in canonical storage. If redaction removes mandatory continuation evidence, report an incomplete/blocked export with exact safe reason; do not claim a self-contained continuation or mutate the original to make export pass. An explicitly redacted derivative gets its own digest and redaction manifest, never the original content hash. Historical, expired, rejected or revoked artifacts retain T01's restrictions.

**Deliverables/allowed files:** Extend T01/T06's existing `src/rush/memory/store.py`, `src/rush/tools/memory.py` policy/transaction seams and T07's `src/rush/cli_support/rendering.py`, `src/rush/tui.py`, `src/rush/dashboard/server.py`, `application.js` and Phase 71 `panels.js` import-review projections. Phase 73 owns `src/rush/memory/capsule.py` and capsule transport/CLI request definitions; changes to shared `memory.py` are serialized under C09. Add `tests/test_phase72_portable_memory_policy.py` and extend `tests/test_memory_public_contract.py`; document authority and conflict handling in T09's existing user guides and `docs/reports/phase-72-memory-acceptance.md` only after the routes work.

**Constraints:** No imported instruction hierarchy, hidden global import, read-side setup, inferred consent, grant widening, independent import database or automatic promotion. User-facing imported-state labels distinguish claimed progress, locally verified progress, pending constraint, stale anchor and unavailable original. Imported source content renders as text. Preview/list/history remain usable when apply is denied.

**Checks:** `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_portable_memory_policy.py tests/test_memory_public_contract.py -q`. Required cases are `test_foreign_owner_and_verified_claim_do_not_authorize`, `test_imported_constraint_needs_local_applicability_review`, `test_preview_no_files_then_atomic_apply`, `test_changed_capsule_policy_and_artifact_version_conflict`, `test_replay_and_distinct_import_identity`, `test_export_personal_scope_and_required_secret_redaction`, and `test_import_review_cli_tui_dashboard_same_state`. Assert exact local owner/trust/freshness, unchanged prior versions, transaction rollback and persisted receipt identity. Use fresh stores, two owners, moved worktrees, contradictory constraints and concurrent edits. T09 live walkthrough imports one PAS session and one Rush capsule through CLI and app review, rejects a forged verification claim, confirms only an intended constraint and preserves the unrelated local choice.

**Atomic import seam:** T06 adds `TypedArtifactStore.apply_import_records(*, records, preview_binding, expected_versions, invocation_id, effect_id, access)`; all inputs are validated73-T09 codec output. `preview_binding` contains capsule digest/selection/destination/policy revision/existing-version map, and `expected_versions` covers every colliding local ID. Under policy lock then one SQLite transaction recheck binding, allocate local IDs distinct from foreign IDs, sanitize content, insert imported/pending versions/provenance/receipt, and commit all or nothing. Persist capsule origin `(capsule_digest, foreign_origin_id)` plus effect request digest in existing receipt/version storage: replay returns original mapped IDs; differing bytes under same effect conflicts. Separate import retains local choices and exposes unresolved collision instead of replacing them. Crash before commit leaves0 rows/receipt, crash after commit recovers same mapping. Export policy is checked immediately before emission, and receiver validation never restores source permissions.

**Completion and dependencies:** T01's policy and T06's transaction behavior can be developed on canonical record fixtures independently. Real portable-route closure consumes only 73-T09's codec/public operation and 73-T02's existing grant API, not all Phase 73. T07/T09 must demonstrate searchable imported provenance and user review on that route. These acceptance cases are additional to T01–T09, not a substitute for their existing gates.
