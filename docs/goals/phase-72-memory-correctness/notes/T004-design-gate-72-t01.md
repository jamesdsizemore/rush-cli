# T004: Design gate for 72-T01 (safe reads, authority and symbol containment)

A goal-judge ran this gate read-only against `07775f1` and cross-checked it with the T003 POLICY note. **Status:** approved. OD-1 and OD-3 need owner answers before T018 test 12 and before T019.

## PM re-checks (run on 07775f1)

1. `update_content` (`store.py:2515-2551`) reads `trust_tier` and writes it back unchanged, and its UPDATE touches only `content` and `artifact_version`. `edit` (`store.py:1435-1527`) demotes STATED to DERIVED and clears `signature` and `promoted_at`. The demotion gap is real.
2. `tests/test_benchmark_memory.py:155` asserts `result.metrics["stale_visible_legacy"] is True`. The gate cited line 152.
3. `ApiDiffer.diff_symbol` defaults `base_ref: str = "main"` (`api_diff.py:81`).
4. The OD-3 call sites:
   - `experience.py:359`, `experience.py:581`, `intent.py:341` and `verification.py:207` call `store.search(...)`.
   - Correction to the gate: `experience.py:550` calls `store.get_version_content(...)`, not `search`. It is still a raw read that bypasses the shared decision.

verified-by: `sed -n` on each cited line at 07775f1; `grep -n stale_visible_legacy tests/test_benchmark_memory.py` printed 155; `grep -n main src/rush/tools/api_diff.py` printed 37, 81 and 131.

Not re-run by the PM: the rest of the caller map, the `diff_symbol`-in-non-git probe, and the claim that sqlite supports DROP COLUMN. The T018 author re-checks these at task start (stop_if).

## Owner answers

- **OD-1 (decided 2026-10-05).** Owner answered "Usable, labelled (Recommended)". Backfilled and unbound rows stay in ordinary recall:
  - `reference.integrity` is set to `backfilled` or `unbound`, never the top integrity label.
  - A STATED row is backfilled only when its signature matches.
  - Test 12 asserts `usable_as_current` True for both rows.
- **OD-3 (decided 2026-10-05).** The owner chose "Phase 72 T01 (Recommended)". These call sites are added to T019's allowed_files and must route through `evaluate_artifact_visibility`:
  - `src/rush/memory/experience.py` (359, 550, 581);
  - `src/rush/memory/intent.py` (341);
  - `src/rush/memory/verification.py` (207).

  `recall_repair_episodes` must stop opening a writable store on read. T018 adds RED coverage for these paths.

## Owner decisions needed

### OD-1: rows with no write-time integrity binding

This blocks T018 test 12 and all of T019.

- **Which rows:** rows written before T01 get `payload_hash` from an additive backfill. Rows inserted outside `store.write` have `payload_hash NULL`.
- **Plan gap:** the plan says such rows "cannot become verified" (verified-by: `grep -n "cannot become verified" docs/phase-plans/phase-72-memory-correctness-and-user-control-plan.md` matched line 34). It does not say whether ordinary recall may still use them.
- **Recommended:** keep them usable, with `reference.integrity` labelled `backfilled` or `unbound`. Backfill a STATED row only when its signature matches.
  - The contract (`memory-program-contract.md` L37) does not claim isolation against processes running as the same OS user.
  - Under the strict rule, every row written before T01 would be excluded from ordinary use until it was rewritten through `store.write`. That is the gate's reason for recommending against it.
- **Alternative:** exclude these rows from ordinary use and show them only in historical mode.
- **What the answer changes:** the two `usable_as_current` assertions in test 12.

### OD-2: API-diff baseline ref (not blocking)

- `diff_symbol` compares against `main`. Under T01, `unknown` freshness is never current. In repos with no `main` branch, every symbol-anchored memory therefore drops out of ordinary recall, including pack-cache hits.
- **Default:** keep `main`, which is today's behavior.
- **Alternative:** resolve the repo's default branch.

### OD-3: raw store read paths outside the plan's file map

- **The paths:** `experience.py:359`, `:550` and `:581`, `intent.py:341` and `verification.py:207` read memory without the shared decision. `recall_repair_episodes` also opens a writable store on a read.
- **The conflict:**
  - Plan §2.1 item 1 requires learned advice and procedure applicability to call the same decision.
  - §3 assigns these files to Phase 74 (`phase-74…plan.md` L205/239/272).
  - No Phase 74 packet line requires the decision.
- **Options, both full scope:**
  - (a) add these call sites to T019's allowed files;
  - (b) amend a Phase 74 packet to own them, with the amendment recorded as a real artifact.
- **Out of scope here:** `consolidation.py:65` belongs to T03, and `tools/memory.py::_list_filtered` (L665-791) belongs to T06/T07.

## 1. Testable behavior

1. **One shared decision.** `retrieval.evaluate_artifact_visibility` returns a `VisibilityDecision`, and every read route uses it:
   - `recall_page`;
   - `hybrid_candidates` and `hybrid_page`, before any embedding call;
   - `expand_artifact`, `defended_recall` and `store.recall`;
   - `_item_relations` neighbors, review citations, and `check_memory_before_pack`.
2. **Ordinary delivery** requires `visible ∧ usable_as_current`.
   - Under the plan fixture (alice, source-a), every route returns ordinary IDs `[a1]` and nothing else.
   - Expanding a2, a3, b1, u1, t1 or a missing ID returns `E_NOT_VISIBLE`. The response bodies are identical except for the echoed `artifact_id`.
3. **Visibility is checked before the version.** An excluded row requested with a wrong version returns `E_NOT_VISIBLE`, never `E_VERSION`.
4. **Historical mode** needs grant op `history` (policy) or the explicit legacy `include_archived`. It shows a2, a3, u1 and t1 with exact reason codes and `usable_as_current=False`. A foreign owner stays invisible in every mode.
5. **Freshness.**
   - **`current`** needs all of: the path is contained, the file exists, the stored `content_hash` equals the current one, the file has a `.py` parser, and `diff_symbol` returns `None`.
   - **`stale`:** the hash differs, or the API broke.
   - **`unknown`:**
     - no stored hash;
     - the path is not contained;
     - the source is missing or unreadable;
     - the parser is unsupported;
     - `diff_symbol` returns `"unknown"` (no baseline, or a base or current parse failure).
   - **`not_applicable`:** the row is unanchored (`symbol_ref` is None). It stays usable.

   Every `unknown` assertion pairs an exact reason code with a positive `current` control (AGENTS.md L91).
6. **Containment.** `resolve_symbol_ref` returns False for an absolute path, `..`, or any symlink component, using `PhysicalRoot.open_contained`. This happens before any read or parse, so an outside file is never read.
7. **Tampering** is any of: a payload-hash mismatch, a STATED signature that is missing or wrong, Trojan characters, or corrupt JSON.
   - Under policy access, the row is excluded.
   - Legacy `store.recall` and `defended_recall` keep their documented raise (`SignatureMismatchError` or `TrojanSourceFoundError`). The raise applies only after the owner and source filters.
8. **Edits drop authority.** `edit` and `update_content` both atomically demote STATED to DERIVED and clear `signature` and `promoted_at`. The version row records DERIVED, and history survives.
9. **Policy.**
   - Every read resolves through `MemoryAccess.resolve`, checked at entry and rechecked just before the result is emitted.
   - If the recheck is denied, pages return `E_PERMISSION` and expand returns `E_NOT_VISIBLE`, with no items and no telemetry.
   - A changed revision or grant returns `E_RESTART`.
   - None of these grants access: forged attribution, a forged binding, a supplied `OwnerScope`, a different root.
   - A missing policy creates nothing.
10. **The legacy explicit-allowlist path is retained.**
    - It has no owner filter unless an owner is declared; a declared owner narrows the result.
    - An empty allowlist fails closed.
    - Passing both `access` and `session_allowlist` raises `ValueError`.
11. **Reads create nothing.**
    - Read routes use `open_readonly_view`. A missing DB gives an empty result, OK or `E_NOT_VISIBLE`, and creates no `.rush`.
    - An old schema without the payload columns gives `migration_required`: compact returns `E_MIGRATION`, legacy returns error text.
    - No DDL, key, journal or WAL file is created.
12. **§2.2 probe.** After T01, `archive_hidden`, `expansion_denied` and `outside_denied` are true. `paging` waits for T02.

## 2. Code and caller map (07775f1)

**Edit `src/rush/memory/store.py`:**

| Symbol | Lines | Change |
|---|---|---|
| `MemoryArtifact` | L324-352 | Add trailing field `freshness: str\|None=None` |
| `_write_version` | L630-687 | Write the payload hash (§3) |
| `_row_to_artifact` | L722 | |
| `_init_db` | L973 | Run the payload migration |
| `search_candidates` | L1175-1228 | Add the archive predicate, `owner_scope` and `now` |
| `scope_artifacts` | L1230-1273 | |
| `get_current` | L1670 | Add `get_current_row` |
| `open_readonly_view` | L1844-1878 | Require the payload columns |
| `upgrade` | L1964-2026 | |
| `_insert_row` | L2167-2212 | |
| `update_content` | L2515-2551 | Demote STATED |
| `recall` | L2697-2768 | |
| `promote_stored_artifact` | L2771-2833 | Row hash set through `_write_version` |

**Edit `src/rush/memory/retrieval.py`:** `SourceValidationMemo` L79-111, `defended_recall` L114-186, `_item_relations` L279-297, `_candidate_to_item` L300-322, `recall_page` L399-569, `expand_artifact` L612-769, `hybrid_candidates` L790-920, `hybrid_page` L923-1055.

**Edit, other files:**
- `trust.py`: `resolve_symbol_ref` L108-128.
- `tools/api_diff.py`: `diff_symbol` L80-125, plus a private parse-or-None helper. `diff_file` and `_extract_public_signatures` keep their behavior.
- `tools/memory.py`: `run` L401-630, `_query` L844-883, `_compact_query` L885-1057, `_expand` L1059-1155.

**Consume only,** editing only if threading needs it: `tools/review.py::_recall_memory_citations` L120-170 and `token_economy/memory_cache_gate.py::check_memory_before_pack` L64-137. Both already use `open_readonly_view`.

**Callers (graft `--depth all`):**
- `recall_page`, `expand_artifact`, `_query` and `_compact_query` are reached through `MemoryTool.run/__call__`. Their callers are the `scripts/benchmarks/memory.py` probes, `memory_datasets.py:190`, the `run.py` journeys, and 36 to 74 test callers.
- `defended_recall` is reached two ways: through the cache gate from `pack_context` (`continuity/context.py:138`) and `tools/continuity.py`, and through review from `ReviewTool`.
- `resolve_symbol_ref` is reached via `evaluate_promotion` and `promote_stored_artifact`, from `store.promote`, maintenance and `_run_promote`.
- `store.recall` is called from `tools/memory.py:872` and `dashboard/server.py:3944`.
- `scope_artifacts` is called from `dashboard/server.py:3922`, `hybrid_candidates` and `_list_filtered`.
- `update_content` is called from `intent.py:164/252` and `recipes.py:196/370`.
- `_write_version` is called from store L1390, 1492, 1578, 2110, 2538 and 2804, and from `maintenance.py:441/483`, `expiry.py:196` and `migration.py:122`. All of these get the hashes inside `_write_version` without being edited.
- Other `open_readonly_view` callers see the new migration requirement: `tui.py:3158/3503/3653/4268`, `dashboard/server.py:1628/3764/4035`, and `tools/memory.py:705/1536/1662`.

**Test files missing from the packet.** Each encodes a defect T01 fixes:
- `tests/test_memory_efficiency.py` (L57, 143, 184, 208, 325, 345): cache hits in non-git roots, where "unknown" is treated as current.
- `tests/test_memory_core_regressions.py` (L33, 109, 202).
- `tests/test_phase62_cache_gate.py:52`.
- `tests/test_phase70_t19.py`: `_case_pack_gate_hit_exact_receipt` L384 and `_case_typed_gate_hit_vs_result_cache_hit_differ` L672.
- `tests/test_benchmark_memory.py:155`: `stale_visible_legacy is True` is the expired-legacy leak. It flips to `False`.

Only two kinds of fix are allowed: git-baseline fixtures (init plus a commit on `main`), and flipping assertions that encode a leak. No other assertion may be weakened.

## 3. Design of the hard parts

```python
# retrieval.py
@dataclass(frozen=True)
class MemoryAccess:
    kind: Literal["policy","legacy_allowlist"]; project_root: Path; operation: str
    sources: tuple[str, ...]; owner_scope: OwnerScope | None
    grant_id: str|None=None; policy_revision: int|None=None; project_id: str|None=None
    worktree_id: str|None=None; session_binding: str|None=None; data_root: Path|None=None
    requested_sources: tuple[str, ...]=()
    @classmethod
    def legacy(cls, project_root, session_allowlist, *, owner_scope=None, operation="ask") -> "MemoryAccess"
    @classmethod
    def resolve(cls, project_root, *, operation, owner_scope=None, requested_sources=(),
                session_binding=None, data_root=None) -> "MemoryAccess | None"
    def recheck(self) -> Literal["ok","changed","denied"]
    @property
    def historical_allowed(self) -> bool  # legacy, or policy operation == "history"

@dataclass(frozen=True)
class VisibilityDecision:
    visible: bool; usable_as_current: bool
    freshness: Literal["current","stale","unknown","not_applicable"]
    reason_codes: tuple[str, ...]; reference: dict[str, Any] | None

def evaluate_artifact_visibility(store, artifact: sqlite3.Row | MemoryArtifact, *, access: MemoryAccess,
        mode: Literal["ordinary","inspect","historical"]="ordinary", now: float|None=None,
        memo: SourceValidationMemo|None=None) -> VisibilityDecision
```

### `MemoryAccess.resolve`

- Lazily imports `rush.memory.authorization.resolve_memory_scope`. Never edits that module.
- When the result's access is `read` or `write`, it builds the object from the result keys `grant_id`, `policy_revision`, `project_id`, `worktree_id`, `project_root` and `owner_scope` (through `OwnerScope.from_value`).
- `sources` is the requested set if one was given, otherwise `approved_sources`.
- A denial returns None.
- Operations map to grant ops as in T003 §4:

  | Memory operation | Grant op |
  |---|---|
  | ask, recall, related, explain | `ask` |
  | list | `list` |
  | expand | `expand` |
  | historical | `history` |

- `recheck` resolves again with the same inputs. It returns `denied` if denied, and `changed` if the grant, revision, ids, owner or sources differ.

### `evaluate_artifact_visibility`

A private `_classify_row` keeps every reason. Steps, in order:

1. **Load the row.** For a `MemoryArtifact`, use `store.get_current_row(id)`.
2. **Access gate.** Deny if any of these hold:
   - `access.project_root != store.project_root`;
   - the source is not in `access.sources`;
   - `access.owner_scope` is set and differs from `owner_scope_for_row(row, store.project_root)` (a NULL owner maps to `legacy_owner_scope`);
   - the mode is historical without `historical_allowed`.

   A denial returns `NOT = (False, False, "unknown", ("not_visible",), None)`.
3. **Lifecycle.**
   - `archived`: `archived_at` is set.
   - `expired`: `expired_at` is set, or `expires_at <= now`.

   An elapsed TTL alone is not expiry; that stays the sweep's job. `test_memory_retrieval.py` seeds IMPORTED rows with `created_at=1.0`.
4. **Integrity reasons:**
   - `integrity_content_corrupt`;
   - `integrity_signature_missing` or `integrity_signature_mismatch` (STATED rows);
   - `integrity_trojan_source`;
   - `integrity_payload_mismatch`, when `payload_hash` is set and differs from `sha256(row.content.encode())`.

   `reference.integrity` takes the gate's three labels (OD-1).
5. **Apply mode.** In ordinary and inspect modes, any lifecycle or integrity reason returns `NOT`. Historical mode returns the row as visible but not usable, with sorted reasons.
6. **Freshness for anchored rows.** The first matching check wins:

   | Check | Freshness | Reason |
   |---|---|---|
   | Malformed ref | unknown | `symbol_ref_malformed` |
   | `trust.contained_source_path` returns None | unknown | `source_not_contained` |
   | No stored hash | unknown | `source_hash_missing` |
   | File missing | unknown | `source_missing` |
   | File unreadable | unknown | `source_unreadable` |
   | Hash differs | stale | `source_hash_mismatch` |
   | Not a `.py` file | unknown | `parser_unsupported` |
   | `memo.api_diff` returns a dict | stale | `api_changed` |
   | `memo.api_diff` returns `"unknown"` | unknown | `api_baseline_unknown` |
   | `memo.api_diff` returns None | current | none |

   Rows that are current or `not_applicable` have `reason_codes=()`.
7. **Usability.** `usable_as_current` means no reasons and freshness of `current` or `not_applicable`. Ordinary delivery drops rows that are not usable. Inspect returns them with `MemoryArtifact.freshness` set, and sets `stale=True` only when freshness is `stale`.
8. **Reference.** `reference` is `{artifact_id, artifact_version, project_id, worktree_id, owner_scope, source, subject, trust_tier, origin_kind, origin_id, freshness, integrity, payload_hash}`.

### Containment and API diff

- `trust.contained_source_path(project_root, path_part) -> Path|None` wraps `PhysicalRoot(root).open_contained(path_part)` and returns None on `ContainmentError` or `ValueError`. `resolve_symbol_ref` calls it before `ast.parse`.
- `ApiDiffer.diff_symbol` keeps its return type. It returns `"unknown"` for:
  - a file that is not `.py`;
  - a path outside `project_root`;
  - a base parse failure (`SyntaxError`, `ValueError` or `RecursionError`, caught by a parse-or-None helper);
  - a missing or unreadable current file;
  - a current parse failure (today this returns `REMOVED_SYMBOL`).
- `SourceValidationMemo` keeps calling `diff_symbol` and `MerkleInvalidator.hash_content`, so `test_memory_efficiency.py:143` keeps its call counts.

### Store

- **New columns.** Add `payload_hash TEXT` and `payload_hash_origin TEXT` to both `memory_artifacts` and `memory_artifact_versions`.
  - `_migrate_payload_hash_columns` runs from `_init_db` and inside the `upgrade()` transaction.
  - The backfill runs only in the step that adds the columns, with `origin='backfill'`. A STATED row is backfilled only when its signature matches.
- **`_write_version`** hashes `json.dumps(content)` and inserts it with `origin='write'`. The current row's hash is set in the same transaction.
  - Callers that re-serialize `json.loads(row.content)` produce equal bytes only for rows Rush wrote. This gets a `ponytail:` comment.
- **`_insert_row`** sets the hash on both rows.
- **`open_readonly_view`** returns `migration_required` when either table lacks `payload_hash`.
- **`search_candidates` and `scope_artifacts`** gain `include_archived=False`, `owner_scope=None` and `now=None` as SQL prefilters. The Python decision stays authoritative.
- **`store.recall`** becomes `store.recall(subject, query, session_allowlist=None, *, include_archived=False, access=None, mode="inspect")`. `include_archived` uses historical mode.
- **`update_content`** gets the same demotion and UPDATE as `edit`.

### Retrieval routes

- Each route takes `access: MemoryAccess|None=None` and `session_allowlist=None`.
  - Passing both raises `ValueError`.
  - Passing neither, or an empty source list, fails closed.
- Each route rechecks access at entry, and again after it builds the result and runs the final `_measure_page`/`_measure_expand`, before telemetry.
- `expand_artifact` gains `mode`, `"ordinary"` or `"historical"`. Historical mode:
  - may expand a non-current version (`version_superseded`);
  - integrity-checks the version row's hash;
  - adds `"historical": True` and `"reason_codes"` to the result.
- `hybrid_candidates` filters `rows_by_id` through the decision before building any embedding text.
- `_item_relations` drops neighbors that are not visible or not usable. T03 takes this over later.
- Compact item `freshness` changes to the decision vocabulary. No consumer reads `"fresh"`.

### `MemoryTool`

- **`_read_access(root, op, allowlist, owner)` helper:**
  - a non-empty allowlist gives `MemoryAccess.legacy`;
  - otherwise it calls `MemoryAccess.resolve(…, data_root=None)`;
  - a None result keeps today's fail-closed outputs: skipped, or `E_PERMISSION`, and `E_NOT_VISIBLE` for expand.
- **`_query` modes:**
  - ask and recall use ordinary mode;
  - list uses inspect mode, or historical when `include_archived` is set.
- **Stores:** `_query`, `_compact_query` and `_expand` open `open_readonly_view`. They open a writable store only for hybrid with `cache_write` on an existing DB.
- **Unchanged:** `_list_filtered` and `receive` (the restricted receiver).

## 4. Cross-task conflicts

- **73-T02/POLICY** runs before T01. T01 relies on:
  - T003's signatures, result keys, and `GRANT_OPERATIONS` (which includes `history`);
  - resolve never raising;
  - fixtures calling `register_project(root, data_root=…)`.

  `authorization.py` is imported only, never edited.
- **72-T02:**
  - binds the cursor to `access.policy_revision`, owner, project and worktree;
  - reuses `MemoryAccess.recheck`, the version-row `payload_hash`, and visibility-before-version;
  - fixes the probe's `paging`;
  - owns the `utf8` representation.
- **72-T03:** owns neighbor filtering in `related_artifacts` and `add_relation`, and `consolidation.py:65`.
- **72-T04:**
  - containment inside `evaluate_promotion` changes maintenance promotion results;
  - owns the cross-owner `_candidate_sources`.
- **72-T05:**
  - owns `not_applicable` applicability;
  - the overlay `MemoryAccess` uses `operation="overlay_read"` with `user_overlay_owner_scope`.
- **72-T06:**
  - builds `MemoryAccess` from v2 requests;
  - adds the mutation recheck under `hold_policy_lock`, with T01 supplying only `recheck`;
  - runs `_list_filtered` and `history` through the decision;
  - adds exclusion-reason fields;
  - covers PAS cases 2-6.
- **72-T07:**
  - the dashboard and TUI read `MemoryArtifact.freshness` and the inspect labels;
  - covers PAS case 7.
- **73-T02/BOOTSTRAP:** reuses `_read_access` and adds `session_binding`.
- **Phase 74:** see OD-3.
- **Phase 70:** `open_readonly_view` reports `migration_required` for DBs created before T01, until any write.
- **75-T02:** benchmark M03 `stale_visible_legacy` flips to False.
- **Phase 71:** none.

## 5. Test matrix

Tests import the T01 symbols inside the test body. Test files:
- **MC:** `tests/test_phase72_memory_correctness.py`.
- **PP:** `tests/test_phase72_portable_memory_policy.py`.

§8 PAS assignment: case 1 to T01, cases 2-6 to T06, case 7 to T07.

| # | Test id | Fixture | Action | Assertion | Expected RED |
|---|---|---|---|---|---|
| 1 | MC::test_t01_denied_current_routes_and_authority | Registered git repo on `trunk` (no `main`). Plan fixture call with `data_root=tmp_path/"user-data"`. Owners alice and bob. Rows: a1; a2 archived; a3 backdated and swept; b1 owned by bob in source-a; u1 anchored with the correct hash; t1 promoted, then raw content edited. Each row has a unique marker. | Resolve ask access. Call `recall_page`, `hybrid_page` (spy on `embed_fn`), `defended_recall` and `view.recall(mode="ordinary")`. Call `expand_artifact` on each excluded row, on "zz-missing", and on b1 with a wrong version. Grant `history` (revision 1) and evaluate historical. | Ordinary is `["a1"]` on every route, and the embed spy sees a1 only. The `E_NOT_VISIBLE` bodies are equal apart from the id. Historical reasons: a2 `("archived",)`; a3 `("expired",)`; u1 unknown `("api_baseline_unknown",)`; t1 `("integrity_payload_mismatch","integrity_signature_mismatch")`. b1 is `NOT` in every mode, and historical under ask access is `NOT`. No excluded id or marker appears in any JSON. | ImportError (`MemoryAccess`) |
| 2 | MC::test_t01_symbol_containment_and_unknown_freshness | Git repo on `main` with `pkg/mod.py` (Known, Other), `bad_base.py` (invalid at `main`, valid now), `pkg/broken.py` (valid at `main`, invalid now), `web/app.js`, a sibling `outside.py`, and `link.py` symlinked to it. Plus a non-git second root. | Run the `resolve_symbol_ref` and `diff_symbol` matrices. Evaluate each anchored row in legacy historical mode. Call ordinary `recall_page` and `defended_recall`. Call `evaluate_promotion` on the outside ref. Spy on memo `source_hash`, `diff_symbol` and `Path.read_text`. | Contained refs are True. Absolute, `..` and symlink refs are False, and the outside file is never read. `diff_symbol` returns `"unknown"` for js, broken, bad_base and outside, a dict for the removed symbol, and None for the current control. Each row has its exact freshness and reason. Ordinary is exactly {c1, unanchored}. Promotion is denied with `failed_grounding_check`. | The outside ref returns True today |
| 3 | MC::test_t01_edit_and_update_content_drop_stated_authority | Two promoted rows | Apply `edit`; call `update_content`; call `recall(mode="ordinary")`; read the version rows | Trust is DERIVED and `signature`/`promoted_at` are None. The version row records DERIVED and the old version is kept. Nothing raises. `payload_hash == sha256(json.dumps(content))`. | `update_content` keeps STATED |
| 4 | MC::test_t01_payload_hash_written_and_tamper_excluded | Write a DERIVED row, then edit its content with raw SQL | Read the columns; call the ordinary routes; evaluate historical | Both rows have a hash with origin `write`. The tampered row is excluded from ordinary, and historical shows `integrity_payload_mismatch`. | Column missing |
| 5 | MC::test_t01_policy_revocation_and_revision_change_close_reads | Registered root, a grant at `default_data_root()`, 3 rows | MemoryTool compact ask with limit 1 and no allowlist. Revoke, then ask and expand. Bump the revision with a second grant while an access is held. Pause `_measure_page`/`_measure_expand` (thread plus Event), revoke, then release. | The first ask is OK with 1 item. After revoking: `E_PERMISSION` with 0 items, and `E_NOT_VISIBLE`. The held access gets `E_RESTART`. The paused call returns `E_PERMISSION`/`E_NOT_VISIBLE` with no items and no telemetry row. | Today, no allowlist gives `E_PERMISSION` |
| 6 | MC::test_t01_forged_identity_moved_root_and_missing_policy_create_nothing | No policy. Then a grant on root A. Then root B registered with a copy of A's DB. | Ask with a forged `project_id`, `session_id`, `agent_id` and owner. Resolve with `session_binding="forged"`. Run MemoryTool on B. Use A's access against B's view. Use bob's owner under alice's grant. | Zero content. The policy file and `data_root/user` are absent before the grant. Resolve returns None. B is empty, and expand returns `E_NOT_VISIBLE`. | ImportError |
| 7 | MC::test_t01_missing_store_and_old_schema_create_nothing | A root with no `.rush`; a DB with both payload columns dropped | Legacy ask; compact ask and recall; expand; queried list | No `.rush` is created. On the old schema, legacy returns error text from `readonly_view_reason` and compact returns `E_MIGRATION`. DB bytes, mtime and the directory listing are unchanged. No `-wal`, `-shm` or `-journal` file. The cursor-key row count is unchanged. | `_query` creates `.rush` |
| 8 | MC::test_t01_review_citations_and_cache_selection_use_shared_decision | Git `main` repo with `module.py`. `migration:failure_ledger` rows: current, archived, expired, payload-tampered, and `.js`-anchored. A real cache fill. | Run `ReviewTool` and `check_memory_before_pack`. Archive or tamper the hit row, then run both again. | Only the current row gets a citation and a receipt. The cache hits only the current row, then misses after the change. | The archived row is cited today |
| 9 | MC::test_t01_legacy_allowlist_route_retained | No policy. Alice and bob rows in source s. A tampered STATED row in source t. | Legacy `recall_page`; MemoryTool with bob's owner; an empty allowlist; `store.recall` and `defended_recall` on t; both `access` and an allowlist | Both owners are returned without an owner filter, and bob's owner narrows to bob. The empty allowlist fails closed. The tampered row raises `SignatureMismatchError`. Passing both raises `ValueError`. | No owner narrowing |
| 10 | MC::test_t01_baseline_probe_t01_fields | The §2.2 probe, verbatim | Run it | `archive_hidden`, `expansion_denied` and `outside_denied` are True. `paging` is not asserted. | All False today |
| 11 | MC::test_t01_relations_and_hybrid_never_disclose_excluded_neighbors | a1 related to a2 (archived) and to b1 | Call `recall_page` and `hybrid_page` | The `relations` ids exclude a2 and b1. The embed spy sees a1 only. | Relations leak today |
| 12 | MC::test_t01_unbound_and_backfilled_integrity_labels | A DB with the payload columns dropped, reopened writable; a raw-inserted row with a NULL hash | Read the origins; evaluate | Origin is `backfill`. The integrity label is `backfilled` or `unbound`. `usable_as_current` follows the OD-1 answer. | Column missing |
| 13 | PP::test_foreign_owner_and_verified_claim_do_not_authorize (plan §8 case 1) | IMPORTED rows whose content claims trust, completion and STATED, plus a claimed owner. The capsule digest differs from the local file. One unanchored import. | Grant to bob; grant to alice; call `evaluate_promotion(user_stated=False)` | Alice's row is `NOT` for bob. The anchored import is stale and not usable. The unanchored import is usable with trust IMPORTED, never STATED. Promotion is denied. | ImportError |

## 6. Worker packages

These are recorded in the T004 receipt in `state.yaml`. They replace the prep-time scopes on T018 (RED) and T019 (implement, Opus).

**T018:**
- **allowed_files:** `tests/test_phase72_memory_correctness.py` and `tests/test_phase72_portable_memory_policy.py`.
- **stop_if:** includes "OD-1 has no recorded owner answer when writing test 12".

**T019:**
- **allowed_files:**
  - `src/rush/memory/{store,retrieval,trust}.py`;
  - `src/rush/tools/{api_diff,memory,review}.py`;
  - `src/rush/token_economy/memory_cache_gate.py`;
  - the five named test files;
  - the OD-3 files, if option (a) is chosen.
- **stop_if:**
  - OD-1 or OD-3 is unanswered;
  - the authorization API differs from T003 §3;
  - a fix needs a file outside the allowed list;
  - a read path creates `.rush`, a DB, a key, a journal or policy files;
  - after T01, any of the three T01 probe fields is not true.

**Missing evidence:**
- The full-suite impact comes from static analysis only. T019 runs the full suite.
- Windows symlink creation in test 2 has not been checked on Windows CI.
