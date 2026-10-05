# T006: Design gate for 72-T03 (goal-judge report, recorded verbatim)

The text below the line is the goal-judge's T006 report, copied unchanged.

## PM re-checks (run on 07775f1 in a TemporaryDirectory store, using `.venv/bin/python`)

- `add_relation` accepts both a self-supersedes edge (a1@1 -> a1@1) and a cross-owner edge (an alice row -> a bob row); each returned `OK`.
- `summary_is_current(store, {})` and `summary_is_current(store, {"member_versions": {}})` both returned `True`.

The gate's core gaps reproduce.

verified-by: the probe printed `self-supersedes: OK | cross-owner: OK` and `summary_is_current({}): True True`.

**PM reconciliation with T003, binding on T024/T025:** the T003 grant vocabulary is `{ask, bootstrap, expand, list, write, history, overlay_read}`. Grants do not carry operations named `link`, `related` or `consolidate`. Consumers map them through T003 §4: `link` and `consolidate` map to `write`, and `related` maps to `ask`.

So the T03 fixtures grant `["write","ask","expand","list","bootstrap"]`. In `test_t03_memory_tool_threads_grant_for_link_related_consolidate`, the case "a grant without 'link'" becomes "a grant without 'write'".

The gate's stop_if ("73-T02 grants reject 'link'/'related'/'consolidate'") is answered by this mapping. It is not a blocker.

**Owner decision on trust tiers (2026-10-05):** the owner chose "Define full tier order (Recommended)" and then "Provenance order (Recommended)". T03 pins `TRUST_TIER_ORDER = ("IMPORTED", "EXTERNAL_WRITE", "DERIVED", "STATED")`, weakest to strongest. This ranks STATED > DERIVED > EXTERNAL_WRITE > IMPORTED.

- **Source:** the order comes from `trust.py:62-68` `default_entry_tier` and plan §8 ("imported claims never authorize").
- **Summary rule:**
  - `consolidate_episodes` sets the summary tier to the minimum of its members' tiers under this order;
  - a STATED minimum is lowered to DERIVED, so a summary is never STATED.
- **Tests:** T024 adds one matrix row asserting the tier for mixed members:
  - IMPORTED with DERIVED gives IMPORTED;
  - EXTERNAL_WRITE with DERIVED gives EXTERNAL_WRITE;
  - all DERIVED gives DERIVED;
  - all STATED gives DERIVED.
- **Expiry:** the expiry TTL comment (`expiry.py:39-44`) is a separate retention rule and is not changed.

**Not re-run by the PM:** the rest of the report. The T024 RED author re-checks the code map at HEAD (stop_if).

---

## (A) Note body for `notes/T006-design-gate-72-t03.md`

# T006: Design gate for 72-T03, relations and derived-memory validity

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`. Read-only gate. It was run with T002's PM-verification section as the baseline.

## 0. Evidence: gaps reproduced at 07775f1

I ran a probe in a `TemporaryDirectory` store using `.venv/bin/python`. Each line below is what the current code actually returned:

| Probe | Result at 07775f1 | Gap |
|---|---|---|
| `add_relation(a1@1 -> a1@1, "supersedes")` | `OK` | Self-supersedes is accepted, so the `supersedes` relation can have a one-node cycle. |
| `add_relation(a1 -> b1)` where b1 is owned by `user/bob` | `OK` | No owner check (`relations.py:119-150`). |
| `add_relation(a1@1 -> ...)` after a1 was edited to v2 | `OK` | `_endpoint_exists` (`relations.py:59`) accepts any historical version. |
| `related_artifacts(a1, version=2)` | Returns b1 through the edge recorded at `a1@1` | The root-side edge version is never compared (`relations.py:209-213`). The traversal also crosses owners: Bob's b1 is returned. |
| `summary_is_current(s, {})` and `summary_is_current(s, {"member_versions": {}})` | `True`, `True` | An empty member set certifies the summary as current (`consolidation.py:146`). |
| `related_artifacts(r, max_nodes=2)` with one visible and one denied neighbor | `complete=False` | The node-cap check (`relations.py:225`) runs before the visibility check (`:228-232`), so a hidden neighbor reveals that it exists. |
| Member content tampered in both tables, no version bump | `summary_is_current -> True` | Only versions are compared. |

Facts that shape the design:
- `archive` (`store.py:1529-1606`) and `sweep_reviewed_expired` (`expiry.py:197-207`) both bump `artifact_version`. The version check alone already invalidates summaries and edges after archive or swept expiry. The real gaps are owner, source and policy revocation, tamper, source staleness, malformed refs, the root-side edge version and the count leak.
- Source staleness is computed at read time and does not bump the version (`retrieval.py:162-184`). Only T01's decision can catch it.
- `summary_is_current` has no production caller (`graft callers --depth 2`: only `tests/test_memory_consolidation.py:42`). Today no read path enforces summary currency at all.
- `consolidate_episodes` (`consolidation.py:65-71`) selects members by source only, with no owner filter, and copies member condition, attempt and outcome text into the summary (`:107-116`). Bob's content can therefore end up inside a summary another owner can read.
- No ordering among trust tiers exists anywhere in the repo (`store.py:39`; ARCHITECTURE.md:328; MC03.md:37). Authority is only binary: STATED versus everything else.
- Baseline: `tests/test_memory_relations.py tests/test_memory_consolidation.py` → 7 passed.

## 1. Testable behavior

1. **B1.** `add_relation` with a resolved `access` inserts an edge only when all of these hold:
   - Both endpoints exist in this store, and the access's canonical project/worktree matches it.
   - Both are visible and `usable_as_current` under T01's `evaluate_artifact_visibility(mode="ordinary")`.
   - Both requested versions equal the current versions.
   - The kind is supported.
   - An acyclic kind (`supersedes`) closes no cycle, including a self-loop.

   Every check runs inside the existing `BEGIN IMMEDIATE`. A rejection writes zero rows.
2. **B2.** A missing, foreign-owner, unapproved-source, archived, expired, tampered, source-stale or cross-project endpoint returns the same body, `{"code":"E_NOT_VISIBLE","message":"relation endpoint is not visible"}`. The body names no ID and gives no hint which endpoint failed. Missing and denied cannot be told apart.
3. **B3.** A visible, eligible endpoint whose requested version is not current returns `E_VERSION` and writes zero rows.
4. **B4.** Legacy `add_relation` (no `access`, the cache_write-only path) still links same-owner eligible endpoints. A cross-owner pair returns `E_NOT_VISIBLE`, an ineligible endpoint returns `E_NOT_VISIBLE`, and a self-supersedes returns `E_INPUT`.
5. **B5.** `related_artifacts` applies T01's decision to the root and to every hop, from fresh rows. In addition:
   - In legacy mode, each neighbor's effective owner must equal the root's.
   - An edge is followed only if its node-side version equals that node's current version, and the neighbor-side version equals the neighbor's current version.
   - Invisible or ineligible neighbors never appear and never affect `complete`, `tokens` or `bytes`.
   - An ineligible root, including an invalid derived summary, returns the existing missing-root `E_NOT_VISIBLE` body.
6. **B6.** `related_artifacts(mode="historical")` requires an access carrying T01's historical authorization:
   - It lists visible neighbors even when they are not current. Each such item carries `usable_as_current`, `reason_codes` and `edge_version`.
   - The top level carries `"mode":"historical","actionable":false`.
   - It never returns non-visible (owner/source-denied) neighbors.
   - Ordinary output shape is unchanged: items stay `{id, version, kind, direction}` and no new top-level keys are added.
7. **B7.** `summary_is_current(store, summary_content, *, access, now=None, memo=None)` returns `True` only when all of these hold:
   - `member_versions` is a non-empty dict of non-empty str to strict in-range int (bool rejected).
   - `member_ids`, if present, has the same key set.
   - `member_refs`, if present, agrees with `member_versions`.
   - Every member exists at exactly that current version and is not itself a derived summary.
   - The recorded `payload_hash` and `content_hash` (when recorded) equal the current ones.
   - Every member is visible and `usable_as_current` under the same `access`.

   Empty or malformed input gives `False`.
8. **B8.** For any artifact whose `content["kind"] == "consolidated_episode_summary"`, the decision gives `usable_as_current=False` whenever B7 fails. Reason code is `derived_member_not_current`, or `derived_members_invalid` for empty or malformed refs. Because the check lives in the shared decision, ordinary recall, hybrid recall, expansion, defended recall, relations, review and the cache gate all omit or deny the summary. Historical inspection shows it with the reason code.
9. **B9.** `consolidate_episodes(..., access=...)`:
   - Selects only members that are visible and usable under `access`. In legacy mode it selects only members whose effective owner is the store's legacy owner.
   - Writes the summary with `owner_scope` equal to the access owner (legacy: the default owner).
   - Records `member_refs: {id: {"version", "payload_hash", "content_hash"}}` next to the unchanged `member_versions` and `member_ids`.
   - Never writes `STATED`.
   - A denied, or not write-capable, access returns `E_PERMISSION` and writes nothing.
10. **B10.** `MemoryTool`:
    - `link`, `related` and `consolidate` receive `owner_scope` and resolve access through T01's MemoryTool resolution, using operation names `"link"`, `"related"` and `"consolidate"`.
    - `link` and `consolidate` hold the 73-T02 policy OS lock (identity `memory-policy:<canonical policy path>`) from resolution through commit. Lock order is policy, then SQLite.
    - When resolution is denied, or `access` is not `"write"`, `link` and `consolidate` return `E_PERMISSION` with zero writes.
    - `related` re-resolves after the traversal and before returning. If it is now denied, it returns the `E_NOT_VISIBLE` empty body. If it is still granted but `policy_revision` changed, it returns `E_RESTART` (`{"message":"memory policy changed during related traversal; retry"}`) with no items.
    - The cache_write gate (`E_PERMISSION`) stays the first check.
11. **B11.** Originals, contradiction edges and history persist. No T03 path deletes or rewrites `memory_relations` or version rows.

## 2. Code and caller map (07775f1)

**Production symbols T03 changes:**
- `src/rush/memory/relations.py`: `add_relation` :89-152, `_endpoint_exists` :59, `_supersedes_cycle_exists` :67, `related_artifacts` :160-260 and `_connect` :52.
- `src/rush/memory/consolidation.py`: `consolidate_episodes` :43-137 and `summary_is_current` :140-150.
- `src/rush/memory/retrieval.py`: T01's new `evaluate_artifact_visibility`/`VisibilityDecision` get the derived-summary adapter. `_item_relations` :279-297 gains `access`/`memo` threading. `_candidate_to_item` :300-322 passes them through; it is called at :501 (`recall_page`) and :1011 (`hybrid_page`).
- `src/rush/tools/memory.py`:
  - dispatch at :595-599 (`link`, `related` and `consolidate` currently get no `owner_scope`);
  - `_link` :1157-1224, `_related` :1226-1302, `_consolidate` :1304-1350;
  - key sets `_LINK_REQUEST_KEYS` :182, `_RELATED_REQUEST_KEYS` :190 and `_CONSOLIDATE_REQUEST_KEYS` :199 stay unchanged.

**Callers (`graft callers --depth all`):**
- `add_relation`, depth 1: `_link` (tools/memory.py:1157); tests `test_memory_relations.py` :36, :87, :127, :195; `test_phase70_t19.py` `_case_link_version_overflow` :1142 and `_case_recall_relations_real` :1187.
- `add_relation`, depth 2 and up, through `MemoryTool.run`/`__call__`: scripts/benchmarks/memory.py, memory_datasets.py and run.py; `test_phase70_t28d.py:1456` and `test_windows_import_safety.py:1077`, both linking same-owner endpoints; `test_memory_public_contract.py:118`; `test_phase70_t28d_backend.py`; the dashboard and project journeys.
- `related_artifacts`: `retrieval._item_relations` :279 (feeding `_candidate_to_item` → `recall_page`/`hybrid_page`), `MemoryTool._related` :1226 and the three relations tests.
- Public `related` callers that pass through `MemoryTool.run`:
  - `tui.py:3602` (read-only store, `session_allowlist=sources`);
  - `dashboard/server.py:3863-3885` (read-only view, unfiltered `all_sources`);
  - `mcp_support/tool_registry.py:603-660` (restricted receiver; forces the session's own allowlist);
  - `scripts/benchmarks/run.py:228`;
  - `tests/test_memory_handoff.py:358`.
- `summary_is_current`: only `tests/test_memory_consolidation.py:42`.
- `consolidate_episodes`: `MemoryTool._consolidate` :1304 and `test_memory_consolidation.py` :42, :97, :121.

**Files touched by the operations but missing from the packet (consumed, not edited by T03):**
- `src/rush/memory/authorization.py` (73-T02): `resolve_memory_scope`, the policy path and lock helper, `grant_memory_scope` and `revoke_memory_scope`.
- `src/rush/dashboard/state.py:64` `cross_process_project_lock`.
- `src/rush/memory/store.py`: `get_current` :1670, `_row_to_artifact` :722, `get_version_content` :1684, `write`, `legacy_owner_scope` :290, `OwnerScope` :249, and the `memory_artifact_versions.payload_hash` column added by T01/T02 (plan §2.1 item 2).
- `src/rush/mcp_support/request_models.py:403-425` (strict `link`/`related`/`consolidate` models; T06 owns v2 changes).
- The `tui.py`, `dashboard/server.py` and `tool_registry.py` callers above, which keep their legacy-allowlist behavior.
- `store.py:1376` (`delete_batch` reference count over `memory_relations`; see §4).

**What earlier units change, for the RED author to re-check:**
- **73-T02/POLICY:** creates `authorization.py`. Re-check:
  - the four signatures (phase-73 plan L123);
  - that the operation vocabulary accepts `"link"`, `"related"` and `"consolidate"` in `allowed_operations`;
  - how `access` maps to `read`/`write`;
  - the name of the policy-path/lock helper.
- **72-T01:**
  - adds `retrieval.VisibilityDecision` and `evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary", now=None, memo=None)`. **This is the exact T01 symbol T03 consumes.** Ordinary use requires `decision.visible and decision.usable_as_current`;
  - adds the legacy-allowlist access value it builds inside `recall_page(session_allowlist=...)`, called **T01-LEGACY** below;
  - adds the historical authorization input, called **T01-HIST**;
  - adds MemoryTool access resolution and its policy-versus-legacy trigger, called **T01-RESOLVE**;
  - changes the signatures of `recall_page`, `hybrid_page`, `expand_artifact` and `_candidate_to_item`.
- **72-T02:** adds `payload_hash` (per §2.1 item 2) and may modify `_candidate_to_item` and the page loop.

## 3. Design of the hard parts

**Interfaces** (all keyword-only additions; `access: Mapping[str, Any] | None` is exactly the dict `resolve_memory_scope` returns):

```python
# relations.py
def add_relation(store, *, source_id, source_version, target_id, target_version, kind,
                 origin_ref=None, access=None, now=None, memo=None) -> dict[str, Any]
def related_artifacts(store, *, artifact_id, version, session_allowlist, access=None,
                      mode: Literal["ordinary", "historical"] = "ordinary", now=None, memo=None,
                      depth=1, max_nodes=32, max_tokens=DEFAULT_MAX_TOKENS,
                      max_bytes=DEFAULT_MAX_BYTES, encoding=DEFAULT_ENCODING) -> dict[str, Any]
# consolidation.py
DERIVED_SUMMARY_KIND = "consolidated_episode_summary"
def is_derived_summary(content: object) -> bool
def summary_invalid_reason(store, summary_content, *, access, now=None, memo=None) -> str | None
def summary_is_current(store, summary_content, *, access, now=None, memo=None) -> bool  # = reason is None
def consolidate_episodes(store, *, symptom, session_allowlist, source="consolidation",
                         access=None, now=None, memo=None) -> dict[str, Any]
```

`access` is **required** on `summary_is_current`. Visibility and revocation cannot be decided without a reader's access (B7, C01). `None` everywhere else means the established legacy path, evaluated with T01-LEGACY.

**`add_relation` algorithm:**
1. Validate kind and version ranges (existing `E_INPUT`).
2. If `kind in _ACYCLIC_KINDS and source_id == target_id`, return `E_INPUT` with "would create a cycle". This runs before any DB read, so nothing about existence leaks.
3. If `access is not None and access.get("access") != "write"`, return `E_PERMISSION` with "memory link requires an approved write grant".
4. Open the connection and run `BEGIN IMMEDIATE`. For each endpoint, run `SELECT * FROM memory_artifacts WHERE id=?` on that connection.
   - A missing row returns the identical `E_NOT_VISIBLE` body.
   - Otherwise build the artifact with `_row_to_artifact(row, default_owner_scope=store._owner_scope_default)`.
   - Evaluate access. With `access=None`, use T01-LEGACY built from the two endpoints' own sources. Legacy linking never had a source scope, so this adds restriction and does not widen it.
   - Get the decision with `evaluate_artifact_visibility(..., mode="ordinary")`.
   - If not `visible and usable_as_current`, return `E_NOT_VISIBLE`. In legacy mode, if the endpoints have different effective `owner_scope`, return `E_NOT_VISIBLE`.
5. Only after both endpoints pass, check versions. A requested version that is not current returns `E_VERSION`; the message names only the caller-supplied ID and version.
6. Run the cycle BFS (existing), insert, and return `OK` plus `sequence`.

Every early return happens inside the transaction before any INSERT, so zero rows are written.

**`related_artifacts`:**
- `mode` must be `"ordinary"` or `"historical"`; anything else is `E_INPUT`.
- `historical` with `access is None` returns the missing-root body.
- `access` given with `access` not in `{"read","write"}` returns the missing-root body.
- Root: run `get_current`, check the exact version, then get the decision. Ordinary needs visible and usable; historical needs visible. The anchor owner is the root's effective owner.
- BFS edges: `WHERE (source_id=? AND source_version=?) OR (target_id=? AND target_version=?)`, binding the node's current version. In historical mode, use all edges of the node.
- Per neighbor, in this order:
  1. `get_current`, then the decision. In legacy mode also require owner == anchor.
  2. In ordinary mode require usable, and the edge version must equal the current version. In historical mode require visible.
  3. Failing neighbors are skipped silently, with no truncated flag.
  4. **Only then** apply the node cap (`truncated=True`) and the token/byte budget.
- Historical items add `usable_as_current`, `reason_codes` and `edge_version`; the top level adds `mode` and `actionable: False`. Pass one `memo` through the whole call.

**Derived-summary adapter (retrieval.py, inside T01's `evaluate_artifact_visibility`):**
- After T01's own checks, if `decision.visible` and `is_derived_summary(artifact.content)`, call `summary_invalid_reason(store, artifact.content, access=access, now=now, memo=memo)`. This is a deferred import, following the precedent at retrieval.py:288.
- A non-None result sets `usable_as_current=False` and appends the reason code. `freshness` stays as T01 computed it.
- There is no recursion: a member that is itself a derived summary makes the refs invalid (`derived_members_invalid`), so member evaluation never re-enters the adapter.
- Import graph: consolidation imports retrieval at the top level; retrieval imports consolidation only lazily. No cycle.

**`summary_invalid_reason`:**
- Parse refs:
  - `member_versions` must be a dict and non-empty;
  - keys must be non-empty `str`;
  - values must be `int`, not `bool`, and `sqlite_integer_in_range`;
  - `member_ids`, if present, must equal the key set;
  - each `member_refs[id]`, if present, needs `version` equal to the `member_versions` value, `payload_hash` of type `str|None` and `content_hash` of type `str|None`.

  Any failure returns `derived_members_invalid`.
- Then, per member:
  - `get_current` exists and its version is exact;
  - not `is_derived_summary`;
  - a recorded `payload_hash` must equal `SELECT payload_hash FROM memory_artifact_versions WHERE artifact_id=? AND artifact_version=?`;
  - a recorded `content_hash` must equal the current `content_hash`;
  - the decision under the same `access` is visible and usable.

  Any failure returns `derived_member_not_current`.

**`consolidate_episodes`:**
- Keep `store.search("episodic", symptom)` for enumeration.
- Filters:
  - legacy: the existing empty-allowlist `E_PERMISSION`, the source in the allowlist, and the effective owner equal to `legacy_owner_scope(store.project_root)`;
  - with access: `access["access"]=="write"`, otherwise `E_PERMISSION`. When `session_allowlist` is non-None it narrows the source set, never widens it.
  - In both modes, the T01 decision must be visible and usable.
- Grouping, majority, exceptions and trust are unchanged: one tier is inherited, mixed becomes DERIVED, STATED becomes DERIVED.
- The summary gets `owner_scope=OwnerScope.from_value(access["owner_scope"])`; legacy uses `None`, which becomes the default owner. `member_refs` reads `payload_hash` from the member's exact version row.

**MemoryTool:**
- Dispatch passes `owner_scope` to `_link`, `_related` and `_consolidate`.
- `_link` and `_consolidate`:
  1. cache_write check;
  2. request validation;
  3. if T01-RESOLVE engages policy: take the policy lock, resolve under the lock, call the function with `access`, release after the function returns (the commit happens inside).
- `_related`: resolve, call, re-resolve, then apply the denied → `E_NOT_VISIBLE` and changed-revision → `E_RESTART` rules.
- If T01 has no shared resolver helper, call `authorization.resolve_memory_scope(project_root=root, operation=<op>, owner_scope=<OwnerScope|None>, requested_sources=session_allowlist or ())` directly under T01's same trigger rule.

**Error codes:** existing `E_INPUT`, `E_NOT_VISIBLE`, `E_VERSION`, `E_PERMISSION` and `E_RESTART`. No new code.

## 4. Cross-task conflicts

- **72-T01:** T03 depends on these, and the RED author must bind each to committed T01 code:
  - T01-LEGACY, T01-HIST and T01-RESOLVE;
  - the decision working on read-only stores (TUI and dashboard `related`);
  - **unanchored rows (`symbol_ref is None`) staying ordinary-usable.** If T01 classifies them `unknown`, then `test_memory_relations.py:121,148,154,215` and `test_memory_consolidation.py:83` flip. That would be a T01 change and must go back to the PM.
- **72-T02:** owns `payload_hash` population and backfill. T03 reads the column only. `_candidate_to_item` is edited by T01, then T02, then T03 in order.
- **73-T02/POLICY:** grants must accept `"link"`, `"related"` and `"consolidate"` in `allowed_operations`, and resolution must yield `access=="write"` for link and consolidate. If its vocabulary differs, the PM reconciles before RED.
- **72-T04:** maintenance and promotion must evaluate candidates through the shared decision, so an invalid summary cannot corroborate or be promoted.
- **72-T06:**
  - The strict v2 `link`/`related` models (`request_models.py:403-425`) must add `owner_scope` and historical `mode`. Public historical related is exposed there, not in T03.
  - The correction kinds `reject` and `supersede` must make the member's decision non-usable, so summaries invalidate on next read. T06 adds those rows.
  - The supersedes edge written by a correction must be inserted while both endpoints are still eligible, or through an in-transaction path with the same checks. `add_relation` refuses a non-usable endpoint.
  - New finding, not in T03's files: `store.py:1376` `delete_batch` preview counts **every** `memory_relations` row, including edges to foreign or invisible artifacts. That count leak belongs to the T06 mutation preview.
- **72-T07:** the UI must show historical related labels and must not read `complete` as "nothing hidden".
- **75-T06:** typed graph joins must not infer completeness from ordinary `related`; invisible neighbors are hidden by design.
- **Phase 70:** `tui.py:3602`, `server.py:3863` and the restricted receiver keep the legacy allowlist path. The same-owner-as-root rule matches every existing same-owner fixture checked: t28d :1426-1465, windows_import_safety :1040-1090 and public_contract :86.
- **Pre-existing bug, outside T03:** `scripts/benchmarks/run.py:235` reads `related_data.get("related")`, but the tool returns `data["items"]`, so the "linked" variant never adds related text. Route it to T08 or Phase 75.

## 5. Existing-test changes required (proven)

1. `tests/test_memory_relations.py:83`: `assert missing_endpoint["code"] == "E_INPUT"` becomes `"E_NOT_VISIBLE"`. If a missing ID returned E_INPUT while a foreign ID returns E_NOT_VISIBLE (plan T03 fixture), the response would distinguish nonexistent from denied. That is an existence oracle, forbidden by T01 ("indistinguishable missing/denied bodies") and C01.
2. `tests/test_memory_consolidation.py:83` and `:94`: `summary_is_current(store, summary)` gains `access=<T01-LEGACY for ["allowed"]>`. B7 needs a reader access to decide visibility and revocation. Both expected values (`True`, then `False`) stay the same.

No other existing assertion changes.

## 6. Test matrix (`tests/test_phase72_memory_correctness.py`; every name contains `t03`)

**Shared fixture (`_t03_world`):**
- `root=tmp_path/"project"`. Set HOME, XDG_DATA_HOME and LOCALAPPDATA to tmp_path subdirectories, then compute `data_root` by calling `default_data_root()`.
- Grants, via the real writers:
  - Alice `OwnerScope("user","alice")`: G1 with sources `["source-a","source-s"]` and ops `["write","ask","expand","list","bootstrap","link","related","consolidate"]`;
  - Bob: a matching grant over `["source-a"]`.
- Artifacts:
  - m1: Alice, source-a, episodic `{symptom:"timeout",condition:{"env":"ci"},attempt:"retry",outcome:"failed"}`, DERIVED;
  - m2: Bob, source-a, same subject and symptom;
  - c1: Alice, source-a, domain_knowledge `{"text":"timeout retry succeeds on ci"}`;
  - s1 = `consolidate_episodes(store, symptom="timeout", session_allowlist=None, access=alice, source="source-s")`, giving `member_versions=={"m1":1}`.

| Test ID | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|
| test_t03_owner_safe_edges_and_summary_invalidation | world | link s1→m2; s1→m1 supersedes; m1→s1 supersedes; c1→m1 contradicts; then `update_content(m1)` | Codes in order: E_NOT_VISIBLE (edges 0), OK (1), E_INPUT (1), OK (2). After the edit: `summary_is_current(...,access)` is False; recall ordinary IDs == [c1]; `related(c1)` items == []; `get_version_content(m1,1)` is the original bytes; edge count is 2 | TypeError: unexpected kwarg `access` (consolidate_episodes) |
| test_t03_link_missing_and_foreign_endpoint_bodies_identical | world plus second store `tmp_path/"p2"` holding id "p2x" | link s1→m2, s1→"ghost", s1→"p2x" under Alice | The three result dicts are equal to `{"code":"E_NOT_VISIBLE","message":"relation endpoint is not visible"}`; no target ID in the serialized result; edge count 0 | TypeError `access` |
| test_t03_link_rejects_ineligible_endpoints[archived,expired,tampered,source_stale] | world plus x1 (Alice, source-a). archived: `store.archive(apply=True)`. expired: patch `rush.memory.expiry.time.time` past 14 days, then `sweep_expired(root, owner_scope=alice, candidate_ids=["x1"])`. tampered: raw sqlite UPDATE of the current version content without a version bump. source_stale: x1 has `symbol_ref="mod.py::f"` and `content_hash` from T01's source hash, then mod.py is rewritten | link c1→x1 at x1's **current** version | E_NOT_VISIBLE with the identical body; edge count unchanged | TypeError `access` |
| test_t03_link_noncurrent_version_conflict | x1 edited to v2 | link c1→x1@1, then c1→x1@2 | E_VERSION with 0 edges, then OK with 1 edge | TypeError `access` |
| test_t03_link_self_supersedes_rejected | legacy store a1, plus world s1 | `add_relation(a1@1→a1@1,"supersedes")` legacy; s1→s1 with Alice | Both E_INPUT; edges 0 | AssertionError (legacy returns OK) |
| test_t03_link_access_project_mismatch | Alice access for root; separate store p2 with two Alice-owned rows | add_relation on p2 store with root's access | E_NOT_VISIBLE; p2 edge count 0 | TypeError `access` |
| test_t03_legacy_link_cross_owner_rejected | legacy store: a1 (default owner), b1 (`user/bob`), a2 (default) | legacy link a1→b1, then a1→a2 | E_NOT_VISIBLE (0 edges), then OK (1 edge) | AssertionError (OK returned) |
| test_t03_related_hides_foreign_and_ineligible_without_count | world plus edges s1→m1 (link) and raw-SQL legacy edge s1→m2 | `related(s1, access=alice, max_nodes=2)` | items == [{id:m1, version:1, kind:"supersedes", direction:"outgoing"}]; `complete is True`; "m2" and Bob's content absent from JSON | TypeError `access` |
| test_t03_legacy_related_same_owner_as_root | legacy store: r (default owner), n1 (default), b1 (bob); same source "allowed"; edges r→n1, r→b1 | `related(r, session_allowlist=["allowed"], max_nodes=2)` | IDs == {n1}; complete True | AssertionError (b1 returned, complete False) |
| test_t03_related_ignores_edges_from_noncurrent_root_version | legacy a1→b edge at a1@1 (same owner); a1 edited to v2 | `related(a1, version=2, session_allowlist=["allowed"])` | items == [] | AssertionError (b returned) |
| test_t03_related_ineligible_root_not_visible[archived,invalid_summary,foreign] | archived: c1 archived, queried at its current version. invalid_summary: s1 after m1 edit. foreign: m2 under Alice | `related(root, access=alice)` | Result equals the missing-root body `{"code":"E_NOT_VISIBLE","items":[],"complete":True,"tokens":0,"bytes":0,"encoding":"cl100k_base"}` | TypeError `access` |
| test_t03_summary_invalidation_matrix[archive,expire,tamper,bound_tamper,edit,revoke_source] | world; positive control first: s1 current True, recall IDs ⊇ {s1,m1}, `related(s1)` == [m1]. revoke_source: revoke G1, grant G2 sources ["source-s"], re-resolve. bound_tamper: rewrite m1 content **and** its `payload_hash` consistently | apply the action | `summary_is_current` False; ordinary `recall_page` IDs exclude s1; `expand_artifact(s1)` E_NOT_VISIBLE; `related(c1)` excludes m1, except bound_tamper, where m1 stays and only s1 is excluded | TypeError `access` |
| test_t03_summary_malformed_refs_never_current[empty_dict,missing,list,str_version,bool_version,overflow,ids_mismatch,refs_mismatch,summary_member] | world | `summary_is_current(store, content, access=alice)`; also write a forged Alice artifact `{kind:"consolidated_episode_summary", member_versions:{}}` with source-s | Always False; forged summary absent from ordinary recall | TypeError `access` |
| test_t03_consolidation_selects_only_authorized_owner_members | world | inspect s1 and its stored row | `member_ids==["m1"]`; `get_current(s1).owner_scope==alice`; `member_refs["m1"]["payload_hash"]` equals m1 v1 `payload_hash`; `trust_tier=="DERIVED"`; Bob's text absent | TypeError `access` |
| test_t03_history_retains_originals_contradiction_labels_invalid_summary | world plus c1→m1 contradicts; m1 edited | T01 decision for s1 under T01-HIST; `related(c1, access=hist, mode="historical")`; ordinary `related(c1)` | s1 visible True, usable False, `"derived_member_not_current"` in reason_codes; historical items include m1 with `usable_as_current` False and `edge_version` 1, top level `actionable` False; ordinary items == []; v1 bytes intact; edge count unchanged | TypeError `mode` / `access` |
| test_t03_recall_item_relations_omit_invisible_neighbors | world plus raw edge m1→m2 | ordinary `recall_page` under Alice | `item["relations"]` for m1 has no m2 entry | AssertionError or TypeError, per T01 signature |
| test_t03_memory_tool_threads_grant_for_link_related_consolidate | world, policy via env-HOME | `MemoryTool().run(root, operation="link", owner_scope=alice, permissions=cache_write, request={s1→m2})`; a grant without "link" (Bob variant); `consolidate`; `related` | `raw["code"]` is E_NOT_VISIBLE, E_PERMISSION, OK (members ["m1"]), OK (items [m1]); edge count exact | AssertionError (legacy link returns OK) |
| test_t03_memory_tool_related_revoked_mid_call | world; monkeypatch `TypedArtifactStore.get_current` to call the real `revoke_memory_scope` once on first neighbor fetch | `MemoryTool.run(operation="related", owner_scope=alice)` | `raw["code"]=="E_NOT_VISIBLE"`; items == []; "m1" absent | AssertionError |
| test_t03_link_holds_policy_lock_through_commit | world; monkeypatch `rush.memory.relations` endpoint fetch to set Event A and wait 0.3 s | thread 1: MemoryTool link s1→c1; thread 2 after Event A: `revoke_memory_scope` | Revoke returns after link commit (timestamps); link OK; edge count 1; next link E_PERMISSION | AssertionError (no lock) |

RED verify passes only when every selected `t03` test fails. Matrix size: 19 test functions with parametrization. No test may be skipped.

## 7. Worker packages

These are given in the receipt below. The implement `allowed_files` are copied verbatim from the plan's T03 Deliverables. `expiry.py` is left out: T03 needs no expiry predicate, because expiry visibility comes from T01's decision and swept expiry bumps the version. The card's prep-time list included it.

## (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T006",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "Gaps reproduced at 07775f1: self-supersedes accepted, cross-owner and stale-version links accepted, related crosses owners and follows root edges from old versions, node cap leaks hidden neighbors through complete=false, empty or tampered summaries pass as current, and summary_is_current has no production caller. The design routes add_relation, related_artifacts, summary_is_current, consolidate_episodes and a derived-summary adapter through T01's evaluate_artifact_visibility under a resolved access, with policy lock, then SQLite transaction, for link. Two existing assertions change, with proof. 19 RED tests.",
    "worker_package": {
      "red": {
        "objective": "Write the T006 test matrix (19 functions, all names containing t03) in tests/test_phase72_memory_correctness.py. Apply exactly the two proven existing-test edits: test_memory_relations.py:83 E_INPUT->E_NOT_VISIBLE; test_memory_consolidation.py:83,:94 add access=<T01 legacy allowlist access for ['allowed']>. Bind T01-LEGACY, T01-HIST, T01-RESOLVE and the recall_page/expand_artifact signatures to committed T01/T02 code. Use only real 73-T02 grant/revoke writers. Use tmp_path for every temp path, including env HOME.",
        "allowed_files": ["tests/test_phase72_memory_correctness.py", "tests/test_memory_relations.py", "tests/test_memory_consolidation.py"],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_correctness.py','-k','t03','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "rtk proxy git diff -U0 -- tests/test_memory_relations.py tests/test_memory_consolidation.py  # expect only lines 83 (relations) and 83/94 (consolidation) changed"
        ],
        "stop_if": [
          "Committed T01 lacks evaluate_artifact_visibility, a legacy-allowlist access form, or historical authorization (return to PM; T03 cannot bind).",
          "73-T02 grants reject 'link'/'related'/'consolidate' in allowed_operations, or never resolve access=='write' for them.",
          "T01 classifies symbol_ref=None rows as not usable_as_current (existing relations/consolidation fixtures would flip).",
          "payload_hash column absent from memory_artifact_versions after T02.",
          "Need files outside allowed_files, or any selected t03 test passes, skips or errors at collection.",
          "Verification fails twice."
        ]
      },
      "implement": {
        "objective": "Implement 72-T03 per notes/T006-design-gate-72-t03.md §1 and §3: access-aware add_relation (identical E_NOT_VISIBLE body, E_VERSION, self-supersedes E_INPUT, in-transaction T01 checks); related_artifacts (per-hop T01 decision, current-version edges, legacy same-owner-as-root, cap after visibility, historical mode); summary_invalid_reason/summary_is_current with required access and member_refs binding; owner-scoped consolidate_episodes; derived-summary adapter in evaluate_artifact_visibility; _item_relations access threading; MemoryTool link/related/consolidate owner_scope plus grant threading, policy lock through commit for link/consolidate, post-traversal re-resolution for related. Run on Opus (trust boundary).",
        "allowed_files": ["src/rush/memory/relations.py", "src/rush/memory/consolidation.py", "src/rush/memory/retrieval.py", "src/rush/tools/memory.py"],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py -k t03 -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_relations.py tests/test_memory_consolidation.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_correctness.py tests/test_memory_retrieval.py tests/test_phase70_t19.py tests/test_memory_public_contract.py tests/test_memory_handoff.py tests/test_phase70_t28d.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider  # no failure beyond T001 baseline, zero SKIPPED",
          "rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "rtk proxy git diff --check"
        ],
        "stop_if": [
          "Need files outside allowed_files (expiry.py, store.py, request_models.py, authorization.py edits go to PM).",
          "A RED test appears wrong; do not edit tests, return to PM.",
          "T01's decision cannot run on a read-only store, or opens a writer inside add_relation's transaction.",
          "73-T02 exposes no policy-path or lock helper usable with identity memory-policy:<policy path>.",
          "Any existing test beyond the three cited lines fails because of the T03 change.",
          "Max two fix rounds; after round 2 the PM finishes directly."
        ]
      }
    },
    "evidence": [
      "Probe at 07775f1 (TemporaryDirectory): self-supersedes OK; cross-owner link OK; stale-version link OK; related(a1@2) followed a1@1 edge to Bob's b1; summary_is_current({}) True; max_nodes=2 with a hidden neighbor gives complete False; tampered member gives summary current True",
      "relations.py:59,89-152,160-260; consolidation.py:43-150; retrieval.py:114-184,279-322,501,1011; tools/memory.py:182-199,595-599,1157-1350",
      "store.py:1529-1606 archive and expiry.py:197-207 sweep both bump artifact_version; store.py:1670 get_current returns archived and expired rows",
      "graft callers: summary_is_current has only a test caller; related_artifacts reached from retrieval._item_relations, MemoryTool._related, tui.py:3602, dashboard/server.py:3863, tool_registry.py:603",
      "No trust-tier ordering in repo: store.py:39, ARCHITECTURE.md:328, MC03.md:37",
      "Baseline: tests/test_memory_relations.py and tests/test_memory_consolidation.py, 7 passed"
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": [],
    "missing_evidence": [
      "T01 (T004) gate note is not yet written: the T01-LEGACY, T01-HIST and T01-RESOLVE symbol names and the unanchored-row freshness classification must be bound against committed T01 code before RED",
      "73-T02 operation vocabulary and lock or path helper are not yet implemented"
    ],
    "required_board_updates": [
      "Replace T024 and T025 allowed_files/verify/stop_if with this worker_package; drop src/rush/memory/expiry.py from T025 (not in the plan's T03 Deliverables, not needed)",
      "Reconcile with the T004 note: T01 must expose a legacy-allowlist access form and historical authorization usable by evaluate_artifact_visibility, and must keep symbol_ref=None rows ordinary-usable",
      "Add to T009 (72-T06 gate) inputs: store.py:1376 delete_batch reference count includes foreign or invisible edges; correction supersedes edge vs add_relation eligibility; strict v2 link/related owner_scope and historical mode; reject/supersede must make the decision non-usable",
      "Add to the 72-T08/Phase 75 benchmark card: scripts/benchmarks/run.py:235 reads data['related'] but related returns data['items']"
    ],
    "owner_decisions_needed": [
      "Plan T03 says 'derived authority cannot exceed weakest supported member', but the repo defines no ordering among DERIVED/EXTERNAL_WRITE/IMPORTED (only STATED vs non-STATED). Current MC03 rule: an agreeing tier is inherited, mixed becomes DERIVED, never STATED. Choose either (a) keep binary authority, which the existing rule is consistent with, or (b) define a full tier order and take the minimum. T03 keeps the existing rule and adds no mixed-tier assertion until decided; (b) is a one-expression change in consolidate_episodes plus one test row."
    ],
    "summary": "Approved with full design. Real gaps were reproduced. T03 routes link, related, summary currency and consolidation through T01's evaluate_artifact_visibility under a resolved access, using identical E_NOT_VISIBLE bodies, current-version edges, cap-after-visibility, member_refs hash binding and a derived-summary adapter that every read path shares. Two existing assertions change, with proof. 19 RED tests. One owner decision is open: trust-tier ordering.",
    "note": "notes/T006-design-gate-72-t03.md"
  }
}
```

Relevant paths:
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/relations.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/consolidation.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/retrieval.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/tools/memory.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/tests/test_memory_relations.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/tests/test_memory_consolidation.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml