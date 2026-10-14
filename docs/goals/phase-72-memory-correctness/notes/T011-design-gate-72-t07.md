# T011: Design gate for 72-T07 (goal-judge report, recorded verbatim)

Below the line is the goal-judge's T011 report, copied unchanged. It contains the note body (A) and the receipt (B).

## PM re-checks (run on 07775f1)

The dashboard Content-Security-Policy is `"default-src 'none'; script-src 'self'; style-src 'self'; "` (`src/rush/dashboard/server.py:229`, header set at `:240`). Injected styles are blocked, so memory-panel layout CSS has to ship as a static asset. That supports adding `src/rush/dashboard/static_assets.py` to T040.

verified-by: `grep -n "Content-Security-Policy\|style-src" src/rush/dashboard/server.py src/rush/dashboard/static_assets.py` printed server.py:229 and :240.

**Owner decision D-T07-1** (the consent path for "denied" screens) is pending. T039 does not start until it is answered.

Not re-run by the PM: the rest of the report. The T039 RED author re-checks the code map at HEAD (stop_if).

---

## Summary

The T011 gate result is **approved**, with one open question for James, D-T07-1. The note body is in (A) below, for the PM to write to `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/notes/T011-design-gate-72-t07.md`. The receipt is in (B). I edited, created and deleted no files.

**D-T07-1 (needs James).** Once the screens move to the policy-checked memory query, anyone without a memory grant sees "denied" in the CLI, terminal UI and dashboard. The only way to create a grant on this board is the 73-T02 Python API. The setup/connect consent command (73-T02/BOOTSTRAP) stays in Phase 73. So the "denied" message has no real command to point the user to. Both options below deliver everything:
- **(a)** Add a 73-T02/BOOTSTRAP checkpoint unit (the setup consent command) on this board before 72-T07.
- **(b)** Have 72-T07 add an explicit in-app consent control to the CLI, terminal UI and dashboard. It shows the exact project, owner, sources and operations, needs the config-mutation permission, and calls `grant_memory_scope(consent=True)`.

**Board changes the PM needs to make:**
- T039 (test author) needs more files: five existing Phase 70 test files, for listed migration-only edits. Every assertion is kept.
- T040 (implementer) needs `src/rush/dashboard/static_assets.py`. The memory panel's desktop/mobile layout and reduced-motion styling can only go there, because the page's security policy blocks injected styles.
- `panels.js` comes off T040's list. It must not be created, because the Phase 71 shell does not exist.
- T039 cannot start until D-T07-1 is answered.

---

### (A) Note body: notes/T011-design-gate-72-t07.md

# T011: design gate for 72-T07 (search, correction and explanation in the CLI, TUI and dashboard)

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`, HEAD `07775f1`.

Sources read:
- Plan §2, §2.1, §3, §4, §5 (T06 and T07 packets), §6, §7 and §8.
- `memory-program-contract.md` C01, C02, C08 and C09.
- Phase 70 T28-D and Phase 71 P07 (L193-204).
- The T002 PM-verification section.
- The T003 POLICY gate note (it was present as an untracked file).
- The real code at 07775f1.

Baseline: `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows` passes (1 passed, 0.24 s).

#### 0. Drift that earlier units cause (the RED author re-checks this first)

T07 consumes contracts that do not exist yet at 07775f1. T039 must grep each item at its start HEAD. Stop and return to the PM if any of them differs.

- **73-T02/POLICY.** The real API is `rush.memory.authorization`:
  - `grant_memory_scope(*, project_root, owner_scope, approved_sources, allowed_operations, expected_policy_revision, consent, expires_at=None, data_root=None)`
  - `revoke_memory_scope(*, grant_id, expected_policy_revision, consent, data_root=None)`
  - `resolve_memory_scope(...)`
  - Denial reasons include `policy_missing`, `no_grant`, `owner_not_granted`, `owner_required`, `operation_not_granted`, `source_not_granted`, `revoked`, `expired` and `relinked`.
  - Operation mapping: list→`list`, expand→`expand`, ask/recall/related/explain→`ask`, history/historical→`history`, any mutation→`write`.
  - No consent CLI exists (BOOTSTRAP stays in Phase 73). That is D-T07-1.
- **72-T01.** It adds `VisibilityDecision` reason codes, with freshness values `current`, `stale`, `unknown` and `not_applicable`. T07 classifies only from those codes and never evaluates policy in the UI. A distinct `revoked` and a distinct `expired` reason must reach the MemoryTool result. If they do not, stop: that is a T01/T06 gap.
- **72-T02.** Expand gains `representation:"utf8"`, with result fields `content_utf8`, `payload_hash`, `total_bytes`, `offset`, `next_offset` and `complete`, plus `E_OFFSET`.
- **72-T06.** It defines the strict v2 forms (schema_version 2) and is the shape T07 sends:
  - **List.** Request: `subjects`, `query`, `owner_scope`, `sources`, `trust_tiers`, `freshness`, `archive_mode`, `limit` (1-100, default 20), `max_tokens`, `max_bytes`, `cursor`. Result `raw`: `{schema_version, items[{reference:{artifact_id, artifact_version, project_id, worktree_id, owner_scope, source, subject, trust/provenance, freshness}, ...the existing identity fields id/artifact_version/source/owner_scope/trust_tier/stale/content}], next_cursor, complete, code, unknowns}` plus exclusion reasons.
  - **history** and **explain.** Explain returns `supporting`, `contrary`, `attempted`, `affected` and `unknowns`.
  - **Edit with correction.** `correction:{kind:"correct"|"reject"|"supersede", reason, supersedes:[{artifact_id,artifact_version}]}`, plus `applicability`.
  - T06 may add `("history","history")` and `("explain","explain")` to the MC14 command loop in `cli.py` (L3863-3883). T07 extends that same builder and must not register a second command with either name.
- **73-T09/CODEC.** It adds the MemoryTool `capsule` operation (preview_import/import), the `rush memory capsule` command, and preview fields (records, mapping, collisions, redactions, unresolved anchors, required consent, binding digest, imported-state fields). T07 only renders them.
- **Symbols at 07775f1 that earlier units may change:**
  - `tools/memory.py`: `MemoryTool.run` (401), `_list_filtered` (665), `_EDIT_REQUEST_KEYS`/`_ARCHIVE_REQUEST_KEYS`/`_PROMOTE_REQUEST_KEYS` (261-293), `memory_overview` (3441).
  - `store.py`: `open_readonly_view` (1844), `read_artifact_receipts_readonly` (~1146).
  - `token_economy/telemetry.py:358` `read_artifact_expansion_receipts_readonly`.

#### 1. Testable behavior

1. **One query route for every screen.** The terminal UI (`MemoryTool().run`), the dashboard (both the GET `section=memory&v=2` route and the `memory_query` action with schema_version 2) and the CLI (`rush memory list` with no positional arguments) all call the T06 strict list. Each screen shows the same IDs and versions that `MemoryTool` returns for the same request. That holds after a reload too.
2. **Seven subjects.** The TUI default is `memory_subject="all"`, which sends all seven subjects. `S` cycles all → active_context → episodic → preference → failure → architectural_decision → domain_knowledge → skill_pattern → all. The dashboard offers a seven-subject multiselect, defaulting to all. The CLI takes `--subject` (repeatable, default all).
3. **Row fields.** Every row on every screen shows id, `v<version>`, subject, owner `kind:id`, source, trust tier, freshness (`current`/`stale`/`unknown`/`not_applicable`), citation and the next actions. Citation is `reference.source_ref` path::symbol if present, else `symbol_ref`, else `none`.
   - CLI human output prints those row fields plus runnable `next:` commands.
   - CLI JSON is the canonical ToolResult, unchanged. Its next action is `raw.next_cursor`/`complete` plus each item's `reference`. No CLI-only keys are added, so it stays identical to MCP.
4. **Bare `rush memory` overview.** Its JSON keeps the Phase 70 T20 contract byte for byte. `test_phase70_t20.py:326` pins the exact six row keys, and T07's completion requires Phase 70's acceptance to hold. Its human output adds `next: rush memory history --id <id>` per row and `next: rush memory list` for the full-field browse.
5. **Paging is server-side.** Pages come from the cursor, 20 rows each.
   - TUI: `]` past the last row fetches `next_cursor`, and `[` goes back through a cursor stack.
   - Dashboard: Next/Previous buttons.
   - CLI: prints the exact `--cursor` command.
   - Paging-cursor drift shows `restart`. A revoked grant blocks the next page.
6. **Inspect the exact version.** Expansion uses UTF-8 with byte offsets. The client joins the pages and checks SHA-256 against `payload_hash`. The TUI and dashboard show `sha256 verified` (label text; verified-by: plan L18 requires the representation to be 'digest verified'). On a mismatch they hold back the content and show the `digest_mismatch` state.
7. **History and explanation.**
   - History lists immutable versions labelled `HISTORICAL — not current`, and an old version can be inspected in historical mode.
   - Explanation shows five sections: Why (supporting), Contrary evidence, What was tried (attempted alternatives), What is stale / affected code, and Unknown.
   - With no recorded rationale it prints `unknown: no recorded rationale`, taken from `unknowns`. No text is generated.
8. **Correction.**
   - Correct, reject or supersede goes through the versioned `edit` operation. The preview names ids, versions, owner, grants and consequences, and writes nothing.
   - Apply needs `y` (TUI), the Apply button (dashboard) or `--apply --allow-cache-write` (CLI).
   - The result shows the new version and the affected relations, summaries and guidance. The original stays in history.
9. **Other mutations.**
   - Archive, restore (archive with `archived:false`), delete, promote and propose behave as before on every screen.
   - Mutations use the row's own subject as `scope`. A multi-row delete whose selection spans subjects is refused, with 0 writes and the message "selection spans subjects X,Y; delete one subject at a time", because one delete transaction covers one subject.
   - Promote takes its corroborating `candidate_refs` only from rows the v2 list can see. It never scans the raw store.
10. **Conflicts.** A concurrent edit keeps the typed form text and shows the `conflict` state. The TUI `r` key, or the dashboard's "Refresh and review" button, reopens the editor with the kept text on the fresh version. The dashboard never auto-reloads on a memory 409.
11. **Project switch.** A response that arrives late for a previous project is discarded on both the TUI and the dashboard.
12. **Keyboard.**
    - TUI: Tab and Shift+Tab cycle `memory_focus` through search → filters → owner → list → inspect → edit. Enter activates the focused control. Escape leaves any sub-mode with 0 writes and returns focus to `list` with the selected index unchanged.
    - Browser: native DOM tab order follows that sequence. Every control has a label, Enter submits, and Escape cancels the form with 0 POSTs and returns focus to the selected row button.
    - Focus stays put after paging (on the Next button) and after a conflict (in the textarea, with the text kept).
13. **Hostile content is literal text.**
    - `<img src=x onerror=alert(1)>`, ANSI escapes and Rich markup show as literal text in the CLI (`safe_terminal_text`), the TUI (`_safe`) and the browser (`textContent` only).
    - The browser creates no IMG element, never assigns `innerHTML`, and no handler runs.
14. **Distinct states.** Each screen shows a distinct reason and a concrete action for each of 17 states: absent, empty, denied, revoked, migration_required, corrupt, busy, stale, unknown, expired, partial, restart, conflict, not_visible, invalid, server_error and digest_mismatch.
15. **Reads write nothing.** No read path creates a `.rush` directory, a DB, a policy file or a lock. With no store, every screen shows `absent`. Nothing is auto-approved.
16. **Screen sizes and motion.** At a 390×844 mobile viewport and 1280×800 desktop, all controls stay present and reachable in the existing inspector or drawer. With reduced motion on (`RUSH_REDUCED_MOTION=1` in the TUI, `state.reducedMotion` in the browser), the progress text (`working: list...` / `Loading page N…`) still shows.
17. **PAS import review (§8).**
    - The preview shows the proposed records, destination mapping, collisions, redactions, unresolved anchors, required consent and binding digest. CLI human/JSON, TUI (`I` form) and dashboard (`memory_import_preview`) show the same values.
    - After apply, all three show the same local IDs and versions with these labels: claimed progress, locally verified progress, pending constraint, stale anchor, unavailable original. (verified-by: grep matched plan L469 for this label list)
    - A forged "verified" claim stays labelled "claimed". (verified-by: plan L435 and L471 require forged verification claims to stay imported/pending)
    - Confirming a constraint on one screen shows the same result on the other two after a reload.

#### 2. Code and caller map (07775f1)

**`src/rush/tui.py`**
- `TuiState` memory fields: L921-965. `memory_subject` (L926) currently defaults to `domain_knowledge`, and the L922 comment saying it is fixed is stale.
- `_memory_sources_and_state` (3147): the store-state pre-check. Keep it; `test_phase70_t20::test_tui_memory_refresh_reports_migration_required` needs `calls == []`.
- Core flow:
  - `_memory_refresh` (3173): today it sends a legacy single-subject list with `session_allowlist` and `*_filter` arguments.
  - `_memory_submit` (3276) and `_apply_memory_result` (3320): the delayed-response guard. Keep them.
  - `_memory_list_kwargs` (3380).
  - `_MEMORY_PAGE_ROWS=20` (3366): today it pages on the client.
- Expand, promote and preview:
  - `_memory_expand_selected` (3488-3636): sends base64 (3556) and reads receipts (3612-3617).
  - `_memory_promote_selected` (3639): scans the raw store for peers (3681).
  - `_memory_write_preview` (3750), `_memory_create_commit` (3815).
- Delete, archive and maintenance:
  - `_memory_delete_preview` (3883) and `_memory_archive_selected` (3995): they use `state.memory_subject` as scope at 3905, 3926 and 4017.
  - `_memory_maintain_preview`/`_memory_maintain_apply` (4057/4114).
- Edit and conflict:
  - `_memory_mutation_apply` (4210), `_memory_edit_commit` (4308, scope at 4321).
  - `_memory_edit_refresh_and_rereview` (4358): a legacy list with `source_filter`/`owner_filter`.
- Key handling and rendering:
  - `_handle_memory_key` (4426-4588): `S` cycles subjects (4507-4512); Tab is not handled; keys v, c, E, A and I are free.
  - The other key handlers: search (4591), filter (4606), owner (4647), edit (4691).
  - `_dispatch_key_inner` (6490): the memory modal at 6523; F3, `+`/`-` (6533-6555).
  - `_reduced_motion` (253) reads `RUSH_REDUCED_MOTION`. `_safe` (6796) uses `theme.safe_terminal_text` (80).
  - `_memory_detail_lines` (7491), `_render_memory_admin` (7532-7714).
- Production wiring: `default_scan_actions` (525; `memory_run=MemoryTool().run` at 582).
- Callers (graft, depth all):
  - `_render_memory_admin` ← `_render_body` (8178) ← `render_app` (8220) ← `run_interactive_tui` (8307) ← `cli.ui_cmd` (1522).
  - `_handle_memory_key` ← `_dispatch_key_inner` ← `_dispatch_key` (6449) ← `run_interactive_tui`.
  - `_memory_refresh` ← delete_apply, edit_outcome, maintain_apply, mutation_apply, edit_commit, plus function references through `_memory_submit` (`S`, `/`, section entry at 5736). graft misses those references; grep finds them.

**`src/rush/dashboard/server.py`**
- Operation set (L250-275) and argument allowlists (283-357).
- `_BOOLEAN_ARGUMENT_FIELDS` (363), `_READ_ONLY_FIXED_ACTIONS` (373), `_APPLY_GATED_ACTIONS` (385), `_MEMORY_OWNER_SCOPED_OPERATIONS` (392).
- Mutation classification (~495-515).
- `_tool_result_response` (2607): a conflict code returns 409.
- Memory adapters:
  - edit (2626), archive (2666), delete (2703).
  - promote (2754): the legacy `candidate_sources` path only.
  - `_dispatch_scan_action` (2816-2903).
  - `_dispatch_memory_query` (2976): legacy only. `_dispatch_memory_expand` (3034): base64 plus `session_allowlist`.
  - propose (3112), maintain (3158).
- `_all_known_sources` (3718).
- `_build_memory_section` (3749-3893): legacy parameters; it serves items through `_fetch_memory_browse_items` (3922).
- Snapshot handler: section memory at 5209.
- CSP (229): `style-src 'self'`.
- Callers:
  - `_build_memory_section` ← `_handle_snapshot` (5040) ← `do_GET` (4559).
  - `_dispatch_memory_query` ← `_dispatch_scan_action` ← the action `_build` (5737).

**`src/rush/dashboard/application.js`**
- `state` (40), `fetchJson` (95; CSRF header).
- `dispatchAction` (355): a 409 triggers the generic reload at 383-386. That would wipe a memory form's text, so memory forms must pass `{reloadOn409:false}`.
- Memory `ACTION_FORMS` (514-583), `labelWrap` (586), `buildOwnerScopeControl` (604), `buildActionForm` (668).
- `downloadArtifactContentPages` (1023): SHA-256 through `crypto.subtle` at ~1080. Reuse that pattern for the `payload_hash` check (T002 item 6).
- `renderSectionWithActions` (1212): a JSON dump in `<pre data-role="section-summary">`. Nothing in `scripts`, `tests` or `src` depends on it.
- `renderMemorySection` (1230), `SECTION_RENDERERS` (1247), `isMobileViewport` (1259), `trapFocus`/drawers (1272-1335), `switchSection` (1337).

**`src/rush/dashboard/static_assets.py`** (missing from the packet): the inspector is 360 px on desktop and an 85vw drawer on mobile (205-330), and the reduced-motion block is at 273. The panel's CSS has to go here.

**`src/rush/cli.py`**
- `_MEMORY_SUBJECTS` (77), `_memory_logical_root` (3335), `_echo_memory_overview` (3349), `memory_group` (3382).
- ask (3441) and recall (3470) use `_render_session_result`.
- `list` (3499-3532): SUBJECT and QUERY are required positionals.
- write (3535) has no owner flags. promote (3591), maintain (3661).
- `_memory_input_request` (3784), `_build_memory_operation_command` (3797): `--input` is required, and `--max-bytes`/`--limit` come from `result_view_options`.
- The MC14 loop (3863-3883) has expand, related, edit, archive and delete.
- `dashboard_cmd` (1779), `mcp serve` (~811), `ui_cmd` (1522).

**`src/rush/cli_support/rendering.py`**
- `exit_with_result` (187): uses the generic `theme.render_result`, whose memory projection is "collection" (`theme.py:443`) and drops row detail.
- `_run_tool` (353).
- `_render_session_result` (386): about 20 commands call it, so do not change it.
- This module imports neither `rush.tui` nor `dashboard.server` (checked), so the shared state classifier can live here.

**Files missing from the packet:**
- `src/rush/dashboard/static_assets.py` (the CSS).
- Migration-only test edits in:
  - `tests/test_phase70_t28d.py`
  - `tests/test_phase70_t28d_review1.py`
  - `tests/test_memory_versions.py` (only the TUI tests at L832-919)
  - `tests/test_phase70_t28a_fixes.py::test_memory_panel_escapes_hostile_rows`
  - `tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory`
- `docs/reports/phase-72-memory-acceptance.md` (live lane).
- `panels.js` is **not** created: the Phase 71 shell has not landed (plan §2, §5).

#### 3. Design of the hard parts

**3.1 The shared state classifier** (in `rendering.py`, imported lazily by `tui.py` and `server.py`)

`MEMORY_UI_STATES: dict[str, tuple[str, str]]` maps each state to a (label, action) pair.

`memory_ui_state(result: Mapping | None, *, store_state: str | None = None, exc: BaseException | None = None) -> dict` returns `{state, reason, action}`. It checks these in order:
1. An exception, or a result with no code and status `error` → `server_error`.
2. A store state of None with no DB → `absent`; `migration_required` → `migration_required`, with `readonly_view_reason` text; `corrupt` → `corrupt`; `busy` → `busy`.
3. The result code:
   - `E_VERSION` or a 409 → `conflict`
   - `E_RESTART` → `restart`
   - `E_BUDGET` → `partial`
   - `E_NOT_VISIBLE` → `not_visible`
   - `E_INPUT` or `E_OFFSET` → `invalid`
   - `E_SCOPE` or `E_OWNER` → `revoked` if the reason is `revoked`, `expired` if it is `expired`, else `denied`
   - a digest mismatch the client found → `digest_mismatch`
4. OK with zero items → `empty`. OK with `complete=false` → `partial` (the action names the next page).
5. Per row: freshness `stale`/`unknown` and the expired label in historical mode → row badges.

The dashboard GET v2 response carries a server-computed `ui_state`. The browser renders `ui_state.label/reason/action` and keeps no separate mapping table, so there is one source of truth.

The denied and revoked action text is set by D-T07-1.

**3.2 The TUI**

New `TuiState` fields:
- `memory_subject` now allows `"all"`, which becomes the default.
- `memory_archive_mode: str = "active"`, toggled by `A`, which also mirrors `memory_filter_archived`.
- `memory_cursor: str | None`, `memory_cursor_stack: list[str | None]`, `memory_complete: bool`, `memory_ui_state: dict | None`.
- `memory_focus: str = "list"`, cycling through `_MEMORY_FOCUS = ("search","filters","owner","list","inspect","edit")`.
- `memory_history: dict | None` (`{id, versions, selected}`), `memory_explained: dict | None`.
- `memory_correct_buffer: dict[str,str] | None` (kind, reason, content) and `memory_correct_field`.
- `memory_import_buffer`/`memory_import_preview`.

Request building:
- `_memory_list_request(state, cursor)` builds `{"schema_version":2, "subjects": [s] or all seven, "query": buffer, "archive_mode", "limit": 20}`. It adds `cursor`, `owner_scope` (from `memory_filter_owner` "kind:id"), `sources` (`[source]`), `trust_tiers` (`[trust]`) and `freshness` (csv) only when set.
- `_memory_refresh` keeps the store-state pre-check, then calls `actions.memory_run(root, operation="list", request=req)`. A raw list (the legacy shape) is not accepted. Items are `raw["items"]`. It sets the cursor, `complete` and `ui_state`.

Keys:
- `]`/`[`: page using the cursor stack, in place of client-side slicing.
- `x`: `operation="expand"`, `request={id, version, offset, representation:"utf8", max_bytes:4096, max_tokens:1024}`, without `session_allowlist`. It accumulates `content_bytes` and computes `hashlib.sha256` when complete. A mismatch withholds the content (`digest_mismatch`). It keeps the existing `memory_expanded` display keys (`pages`, `content`, `relationships`, `receipts`) so tests that only render keep passing. related and receipts work as they do today.
- `v`: history. `E`: explain. `c`: correction form (Tab moves between fields; space cycles the kind; Enter runs the preview `edit apply:false` with `correction`; `y` applies; `n`/Escape gives 0 writes). Supersede uses the space-marked rows as `supersedes` refs, or the cursor row if none are marked.
- `I`: the import path form → capsule preview → `y` applies with grants.
- Tab/Shift+Tab ("tab"/"shift+tab"): handled at the top of `_handle_memory_key`. Enter on a focus routes to `/`, `f`, `o`, `x`, `x` and `e` respectively.

Other rules:
- Mutation scope is `item.get("subject") or (state.memory_subject if it is not "all")`. If neither is available, refuse.
- Promote peers come from a v2 list with `subjects=[subject]` and `owner_scope=<row owner>`, filtered with the same equality rules as today.
- Refresh-and-review re-fetches the row through a paged v2 list filtered by subject, owner and source, until it finds the id or the list is complete.

Rendering:
- The table shows marker, id, v, subject, owner, trust and freshness.
- A selected-row line shows source, citation, state badges and `next:` key hints.
- The header shows `subject=<all|s> archive=<mode> page N` and `[focus: <name>]`.
- The `ui_state` line shows the label, reason and action.
- History, explain and import views are panels, and every value goes through `_safe`.

**3.3 The dashboard**

GET `section=memory&v=2`, with csv parameters:
- List: `subjects`, `query`, `owner` (kind:id), `sources`, `trust`, `freshness`, `archive_mode`, `limit`, `cursor`.
- Sub-requests: `inspect_id`+`inspect_version`+`offset`, `related_id`+`related_version`, `history_id`, and `explain_id` or `explain_query`.

Handling:
- It opens a read-only view (`open_readonly_view`, which never creates anything) and runs `MemoryTool(readonly_store=view).run(root, operation=..., request=...)`. Values are passed through unchanged; for example a non-digit `limit` stays a string, so MemoryTool returns `E_INPUT`. The server keeps no validation of its own.
- It returns `{schema_version:2, subjects:[7], store_state?, store_reason?, list:<ToolResult>, ui_state, inspect?, inspect_ui_state?, receipts?, related?, history?, explain?}`.
- `receipts` reuses `TypedArtifactStore.read_artifact_receipts_readonly` and `read_artifact_expansion_receipts_readonly`.

Legacy GET parameters (no `v=2`) keep today's exact response. They remain a compatibility route covered by T01's store-level checks (plan: "retain existing operation compatibility"), and the browser no longer uses them.

Action changes:
- `memory_query` with `schema_version:2` forwards exactly the v2 keys; the allowlist adds `schema_version, subjects, owner_scope, sources, trust_tiers, freshness, archive_mode`. The legacy branch is unchanged.
- `memory_edit` allowlist adds `correction`.
- `memory_promote` allowlist adds `source_id, expected_version, candidate_refs`. When `source_id` is present, it calls `MemoryTool.run(..., request={"apply":True,"required_grants":["cache_write"],"source_id","expected_version","candidate_refs"})`.
- New `memory_import_preview` (read-only fixed) and `memory_import` (apply-gated) forward the CODEC capsule request unchanged: bytes if CODEC accepts bytes, otherwise a path. Stop if neither.

`application.js`:
- `renderMemorySection` builds `<section class="rush-memory-panel" data-role="memory-panel">` containing:
  - The search form, with labelled `query`, a subjects multiselect, owner kind/id, sources, trust, freshness, archive_mode and Search.
  - `<div data-role="memory-status" role="status" aria-live="polite">` and `<div data-role="memory-error" role="alert">`.
  - The row list (`<ul data-role="memory-rows">` of `<button data-artifact-id data-version aria-pressed>`).
  - Pager buttons, and an inspect region (`<pre data-role="memory-content">` via `textContent`, refs, receipts, a digest badge).
  - History and explain sections.
  - The correction, edit, archive/restore, delete (preview names the exact IDs), promote and propose forms built from canonical arguments.
  - The import-review form.
- All memory `dispatchAction` calls pass `{reloadOn409:false}`.
- A generation guard (`isCurrentGeneration` plus a project-id check) drops late responses.
- UTF-8 joining uses `TextDecoder` with `fatal:true`, and `crypto.subtle.digest` is compared with `payload_hash`.
- Escape on any memory form resets it and focuses the selected row button.
- No `innerHTML`, `insertAdjacentHTML` or `setAttribute("style")`.

`static_assets.py`: `.rush-memory-panel` rules with `max-width:100%`, `min-width:0` on controls, `pre{white-space:pre-wrap;overflow-wrap:anywhere}`, a scrollable row list, and the panel added to the existing reduced-motion block using the existing MOTION tokens.

**3.4 The CLI**

`rush memory list`:
- `subject` and `query` become optional positionals. With positionals or `--session`/`--include-archived`, the command runs the legacy path unchanged.
- New strict options: `--subject` (multiple), `--query`, `--owner KIND:ID`, `--source` (multiple), `--trust` (multiple), `--freshness` (multiple), `--archive-mode active|historical`, `--limit`, `--cursor`, `--max-bytes`, `--max-tokens`, `--json`.
- Mixing the two forms raises a UsageError ("cannot mix legacy positional/--session/--include-archived with strict options") with exit 2 before anything runs.

The MC14 builder:
- For `expand`, `related`, `history`, `explain`, `edit`, `archive` and `delete`, `--input` becomes optional and is mutually exclusive with these typed flags:
  - `--id`, `--version`
  - `--offset`, `--representation utf8|base64` (default utf8), `--budget-bytes`/`--budget-tokens` (these names avoid the existing `--max-bytes` view option)
  - `--query` (explain)
  - `--expected-version`, `--subject`, `--owner`, `--content JSON`
  - `--correction`, `--reason`, `--supersedes ID@V` (multiple)
  - `--restore`, `--target ID@V` (multiple, delete), `--apply`
- A command whose leaf does not exist yet (history/explain) is added to the loop only if T06 has not added it.

Human output: `exit_with_result` and the ask/recall/list commands route memory results to `render_memory_result()`, which prints rows, the state, the reason, the action and exact `next:` commands, using `safe_terminal_text`. JSON stays unchanged, and so do exit codes (`session_exit_code_for`).

#### 4. Cross-task conflicts

1. **The v2 list needs a grant.** Under C01 and §2.1(3), a missing policy means denied. Existing TUI and dashboard tests that use a real MemoryTool with no grant, or that pin the legacy list shape or base64 expansion, will break. T039 migrates these tests, keeping every assertion:
   - **Shape:** `test_t28d_browse_on_entry_shows_items_without_a_query`, `test_t28d_query_includes_trust_filter`, `test_t28d_query_includes_owner_source_freshness_archived_filters`, `test_t28d_edit_conflict_offers_refresh_and_rereview`, `test_t28d_r_key_refreshes_recorded_conflict`, `test_t28d_expand_renders_relationships_and_receipts_as_structured_sections`. The kwarg assertions become request-field assertions, for example `trust_filter` becomes `request["trust_tiers"]==[...]`.
   - **Grant fixture:**
     - `test_phase70_t28d.py` tests at 1368, 1426, 1517 and 1591.
     - Every `_RealMemoryRun` test in `test_phase70_t28d_review1.py`.
     - `test_dashboard_memory_tokens.py` TUI tests at 1780-1930.
     - `test_phase70_tui_usability::test_t28d_memory_workflows`.
     - `test_memory_versions.py` TUI tests at 832-919, if their fake returns the legacy shape.
   - **Expand shape:** `test_phase70_t28f_review1::test_plus_minus_...` and `test_phase70_t28a_fixes::test_memory_panel_escapes_hostile_rows`. The latter should keep passing, since rendering keeps the same keys.
   - If any other test fails because of these documented mechanisms during T040, return to the PM for a T039 delta. It is not a fix round, and the test is never weakened.
2. **T06** owns the request and result shapes and the `cli.py` history/explain leaves. Units run in sequence, so `cli.py` has one writer at a time: CODEC's `rush memory capsule` lands before T07. T06's CLI/MCP parity test must stay green, so T07 adds no CLI-only JSON keys.
3. **T01 and 73-T02** supply the reason codes T07 classifies, and the denied/revoked action text depends on D-T07-1. The legacy GET and `memory_query` routes rely only on T01's store-level checks.
4. **T02:** UTF-8 fields. The dashboard memory check uses `payload_hash`; the artifact-export `expectedSha256` path is unchanged.
5. **T03:** the `supersedes` edge and summary-invalidation display in the "affected" section. **T05:** shows preference `scope`/`authority`/`applicability` and correction lineage (plan §6), and never turns on the personal overlay.
6. **73-T09:** the capsule request and preview fields. T07 only renders them. If the operation is missing at T039 start, the import-review test cannot be written; stop.
7. **T08** later labels hybrid retrieval. T07 renders a `retrieval` field when it is present.
8. **T09** owns the docs and report. T041 adds only the "72-T07 live lanes" section of `docs/reports/phase-72-memory-acceptance.md` (it creates the file if T09 has not), plus the T07 share of the PAS walkthrough.
9. **Phase 70:** T20's overview contract is preserved. T28-D's terminal admin is delivered here. T28-F's gates are not implied.
10. **Phase 71:** `panels.js` is not created. P07's P02 Node command stays open and is named in the T09 report. Phase 71 will extend `tests/test_phase71_dashboard_integration.py`, which this unit creates.
11. **Phase 75:** no conflict.

#### 5. Test matrix (every new test must FAIL at RED)

Every test is designed to fail at RED; the T039 verify command proves it. Symbols that do not exist yet are imported inside each test body. Fixtures:
- **G**: `register_project(root, data_root=tmp/"user-data")`, then `grant_memory_scope(consent=True)` for Alice (`project:<pid>`, all five operations, all sources), plus a separate Bob (`user:bob`) grant where a row says so.
- **S7**: one Alice row per subject (one contains "needle") and seven Bob rows.
- **P25**: 25 more Alice `domain_knowledge` rows.

**`tests/test_phase72_memory_ui.py`**

| # | Test id | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|---|
| 1 | `test_t07_shared_user_journey` | G, S7, P25 | CLI `list --json`/human; TUI keys F3 4, S×8, `/needle`, `]`, `x`, `c`+reason, `y`; dashboard GET v2; reload all three | IDs/versions on all three equal MemoryTool v2; r1@2 shown everywhere; v1 kept in history | `ImportError: memory_ui_state`, or a missing CLI option |
| 2 | `test_t07_cli_list_browse_without_query_human_fields` | G, S7 | `rush memory list` | each row has id, `v1`, subject, owner, source, trust, freshness, citation; `next:` lines for expand/history/related/edit | Click "Missing argument SUBJECT" |
| 3 | `test_t07_cli_list_json_is_canonical_v2` | G, S7 | `list --json --subject preference --query needle` | `raw` equals `MemoryTool.run(list v2).raw` | no such option |
| 4 | `test_t07_cli_mixed_legacy_and_v2_rejected_before_effects` | absent store | `list preference q --session s --subject failure` | exit 2, exact mix message, no `.rush` created | message assertion |
| 5 | `test_t07_cli_paging_follow_next_cursor` | G, P25 | run the printed `--cursor` command | 20+5 unique rows, complete | no option |
| 6 | `test_t07_cli_expand_utf8_digest_verified` | G, multibyte and combining content | `expand --id --version --budget-bytes N`, following `next:` | the joined bytes are exact; `sha256 verified` (label text; verified-by: plan L18 requires the representation to be 'digest verified'); a non-boundary offset gives `invalid` | `--input` is required |
| 7 | `test_t07_cli_history_explain_related_followable` | G, edited r1 | `history --id`, `explain --id`, `related --id --version` | HISTORICAL v1/v2; five explain sections; `unknown: no recorded rationale` | `--input` is required |
| 8 | `test_t07_cli_correction_preview_then_apply` | G | `edit --id r1 --expected-version 1 --correction reject --reason x --owner ..` with and without `--apply --allow-cache-write` | the preview writes nothing (DB digest unchanged); apply → r1@2 rejected; JSON equals MemoryTool | `--input` is required |
| 9 | `test_t07_cli_states_distinct_reason_and_action[state]` | parametrized over all 17 states | CLI list/expand/edit | `state: <name>`, reason and action each distinct; expected exit code | ImportError |
| 10 | `test_t07_cli_hostile_content_literal` | G, hostile rows | `list`, `expand` | literal `<img src=x onerror=alert(1)>`; no `\x1b` | missing argument |
| 11 | `test_t07_memory_ui_state_table_is_shared` | none | import | the table has all 17 keys; `rush.tui` and the server use the same function object | ImportError |
| 12 | `test_t07_tui_all_subjects_by_real_keys` | G, S7 | F3 4, then S×8 | each subject shows exactly its row; `all` shows 7 | subject is `domain_knowledge` and `all` is missing |
| 13 | `test_t07_tui_query_page_inspect_exact_version` | G, P25 | `/needle`, `]`, `[`, `x` | `page 2` shows rows 21-25 exactly; `sha256 verified` (label text; verified-by: plan L18 requires the representation to be 'digest verified') | the label is missing |
| 14 | `test_t07_tui_history_and_explain_views` | G, edited r1 | `v`, `j`, `x`, Esc, `E` | HISTORICAL v1 content; the five sections | keys do nothing |
| 15 | `test_t07_tui_correction_reject_supersede_preview_apply` | G | `c`, kind, reason, Enter, `n`; then again with `y`; supersede with a marked row | `n`: 0 writes; reject → applicability recorded; a `supersedes` edge appears in related | `c` does nothing |
| 16 | `test_t07_tui_concurrent_edit_keeps_text_and_conflict` | G | `e` + text; an external edit; Enter; `r` | buffer kept; `state: conflict` action; the editor reopens on the fresh version | conflict-state text is missing |
| 17 | `test_t07_tui_tab_focus_ring_enter_escape` | G, S7 | Tab×6, Shift+Tab, Enter on edit, Escape | the focus sequence; edit opens; Escape → focus `list`, index unchanged, 0 writes | `memory_focus` is missing (via `getattr` → assertion) |
| 18 | `test_t07_tui_project_switch_discards_late_response` | two projects; a blocking `memory_run` | list A, switch to B, release | A's items are never shown; the sent request is schema_version 2 | request-shape assertion |
| 19 | `test_t07_tui_states_distinct` | the 17-state fixtures | render | label and action per state | ImportError, or text missing |
| 20 | `test_t07_tui_hostile_and_reduced_motion` | hostile rows; `RUSH_REDUCED_MOTION=1` | list, `x`, `E`; a list in flight | literal text everywhere; `working: list...` visible | explain view is missing |
| 21 | `test_t07_tui_interrupted_refresh_keeps_rows` | G; a blocking run | `/q` Enter, then Esc | `list cancelled`; earlier rows intact; 0 writes | v2 request assertion |
| 22 | `test_t07_tui_two_owners_owner_filter` | S7; Alice grant only, then also Bob | filter `user:bob` | first `denied` with no Bob IDs; then exactly Bob's 7 rows | denied state is missing |
| 23 | `test_t07_tui_mutations_use_item_subject_in_all_mode` | G, S7 | `a` on a preference row; `d` on a mixed selection | `scope=="preference"`; mixed delete refused with 0 writes | scope is `domain_knowledge` |
| 24 | `test_t07_tui_promote_candidates_from_visible_list` | G; an identical Bob row | `p` | `candidate_refs` exclude Bob | the raw store scan includes it |
| 25 | `test_t07_read_paths_create_nothing` | absent store | CLI list; TUI browse/x/v/E; GET v2 | the file tree is unchanged; no policy file | CLI usage error |
| 26 | `test_t07_dashboard_get_v2_list_matches_memorytool` | G, S7, P25 | GET v2, following the cursor | `list.raw` equals the read-only MemoryTool; `ui_state` present | `KeyError: list` |
| 27 | `test_t07_dashboard_get_v2_inspect_history_explain_receipts` | G, edited, expanded | GET sub-requests | UTF-8 with `payload_hash`; history; explain; mutation and expansion receipts | missing keys |
| 28 | `test_t07_dashboard_actions_v2_query_correction_promote_refs` | G | `memory_query` v2; `memory_edit` with correction; `memory_promote` with `source_id`/`candidate_refs`; an unknown key | forwarded; the unknown key still returns 400 | 400 for each new key |

**`tests/test_phase70_tui_usability.py`**

| # | Test id | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|---|
| 29 | `test_t28d_memory_workflows` (extended) | add G, S7 | the existing journey, plus: browse with no query across all seven; every filter and subject; relations/receipts; each mutation's success, decline, denial and conflict; multi-select; archive/restore; maintenance; missing and corrupt store; a cross-project delayed response | exact committed versions; zero unauthorized changes | `v1`/`subject=all` not rendered |

**`tests/test_phase71_dashboard_integration.py`** (new; Node plus the real dashboard server)

Harness: copy `application.js` into a `tmp_path` directory, add an extended mini-DOM (focus/activeElement, keyboard events, `querySelectorAll`, an `innerHTML` setter that records calls, a matchMedia stub), and point `global.fetch` at the real server with the cookie and CSRF token. Assert `shutil.which("node")`; never skip.

| # | Test id | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|---|
| 30 | `test_memory_panel_owner_version_lifecycle` | G, S7, and an absent-store project | the P07 sequence: missing store; two owners on one subject; wrong owner/version → inline 409 with text kept and no reload; propose, edit, archive, restore, delete (preview names the IDs), each reread; denied grant; promote → a new candidate with the original unchanged; stale inspector; hostile content; archived count/search equals the overview | every value equals MemoryTool and the DB | `memory-panel` is missing (JSON dump only) |
| 31 | `test_memory_panel_keyboard_focus_and_escape` | G, P25 | walk the tab order; Enter; Escape; Next; a conflict | the order; every control labelled; 0 POSTs on Escape; focus on the row, Next button or textarea | panel is missing |
| 32 | `test_memory_panel_hostile_content_text_only` | hostile rows | render, inspect, explain | literal text; no IMG created; no `innerHTML` call | panel is missing |
| 33 | `test_memory_panel_utf8_expansion_digest` | multibyte content over several pages; one tampered page | inspect | exact join and `sha256 verified` (label text; verified-by: plan L18 requires the representation to be 'digest verified'); the tampered case shows `digest_mismatch` with content held back | panel is missing |
| 34 | `test_memory_panel_states_and_actions` | 9+ states | load | distinct `memory-status` text and action label | panel is missing |
| 35 | `test_memory_panel_mobile_desktop_reduced_motion` | CSS; 390 and 1280 stubs; `reducedMotion` | render; a fetch in flight | the `.rush-memory-panel` CSS rules are present; all controls in the drawer and inspector; progress text shown | CSS and panel missing |
| 36 | `test_memory_panel_project_switch_discards_late_response` | two projects, slow fetch | switch | A is ignored | panel is missing |
| 37 | `test_memory_panel_explain_history_sections` | G, edited | inspect history/explain | the five sections and versions, exact refs | panel is missing |

**`tests/test_dashboard_memory_tokens.py`**

| # | Test id | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|---|
| 38 | `test_t07_memory_section_v2_two_owner_isolation_http` | S7, Alice grant | GET v2 with `owner=user:bob` | denied `ui_state`; no Bob IDs or counts in the body | no `v=2` support |
| 39 | `test_t07_memory_section_v2_revocation_blocks_next_page_http` | G, P25 | page 1, revoke, page 2 | revoked; no rows | no `v=2` support |
| 40 | `test_t07_memory_edit_correction_conflict_409_no_write_http` | G | `memory_edit` with correction at a stale version | 409; DB digest unchanged | 400 for the unknown `correction` key |
| 41 | `test_t07_memory_section_get_v2_creates_nothing_absent_store` | absent store | GET v2 | absent; tree unchanged | no `v=2` support |

**`tests/test_phase72_portable_memory_policy.py`**

| # | Test id | Fixture | Action | Assertion | Expected RED failure |
|---|---|---|---|---|---|
| 42 | `test_import_review_cli_tui_dashboard_same_state` | G; a CODEC capsule fixture with a forged verified claim (verified-by: plan L471 case name) and a constraint | preview via CLI JSON/human, TUI `I`, dashboard `memory_import_preview`; apply; list on all three; confirm the constraint in the TUI; reload | same records, labels, collisions and digest; preview creates nothing; same IDs and labels after apply; the forged claim stays claimed; the confirmation shows everywhere | the import-review renderer and actions are missing |

#### 6. Worker packages

These are the receipt's `worker_package` values (red, implement, live). They also answer the expected-output list on T039 and T040.

### (B) Receipt

```json
{"goalbuddy_receipt_v1":{"result":"done","task_id":"T011","board_path":"/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml","decision":"approved","full_outcome_complete":false,"rationale":"T07 is designable to full plan scope against 07775f1. The screens use one strict list route: the TUI calls MemoryTool directly, the dashboard GET adds a v=2 mode and memory_query takes schema_version 2, and the CLI list gains strict options. One shared state classifier lives in rendering.py, expansion checks the UTF-8 digest, and the browser panel is built on application.js without panels.js. Legacy routes and Phase 70 T20 contracts are preserved. Files missing from the packet: static_assets.py and migration-only edits to Phase 70 tests. One owner decision, D-T07-1 (which consent route the denied state points to), is open because 73-T02 BOOTSTRAP is not on this board.","worker_package":{"red":{"objective":"Write the full T011 test matrix (rows 1-42) and the listed migration-only edits to Phase 70 tests, keeping every assertion; prove each new test FAILS by execution before any production change.","allowed_files":["tests/test_phase72_memory_ui.py","tests/test_phase70_tui_usability.py","tests/test_phase71_dashboard_integration.py","tests/test_dashboard_memory_tokens.py","tests/test_phase72_portable_memory_policy.py","tests/test_phase70_t28d.py","tests/test_phase70_t28d_review1.py","tests/test_memory_versions.py","tests/test_phase70_t28f_review1.py","tests/test_phase70_t28a_fixes.py"],"verify":["rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_ui.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase70_tui_usability.py','-k','t28d','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase71_dashboard_integration.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_dashboard_memory_tokens.py','-k','t07','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_portable_memory_policy.py','-k','test_import_review_cli_tui_dashboard_same_state','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\""],"stop_if":["The note §0 drift check finds a changed or missing consumed symbol at HEAD: the T06 v2 list/history/explain/correction shapes, the T02 utf8 fields, T01 revoked/expired reason codes, 73-T02 grant_memory_scope, or the 73-T09 capsule operation and preview fields.","Owner decision D-T07-1 is unresolved (needed for the denied/revoked action assertions).","A migration edit would remove or weaken an existing assertion.","Need files outside allowed_files.","Behavior is ambiguous against the gate note.","Verification fails twice."]},"implement":{"objective":"Implement 72-T07 per T011 §3 until every RED test and every migrated legacy test passes, with the full suite, ruff, format and mypy green. Dispatch on Opus (hostile content and trust boundary).","allowed_files":["src/rush/cli.py","src/rush/cli_support/rendering.py","src/rush/tui.py","src/rush/dashboard/server.py","src/rush/dashboard/application.js","src/rush/dashboard/static_assets.py"],"verify":["rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_ui.py tests/test_phase70_tui_usability.py -k 't07 or t28d' -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase71_dashboard_integration.py tests/test_dashboard_memory_tokens.py -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_portable_memory_policy.py -k test_import_review_cli_tui_dashboard_same_state -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_dashboard_memory_tokens.py tests/test_memory_versions.py tests/test_phase70_memory_visibility.py tests/test_phase71_dashboard_integration.py -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase70_t28d.py tests/test_phase70_t28d_review1.py tests/test_phase70_t28a_fixes.py tests/test_phase70_t28f_review1.py tests/test_phase70_t20.py tests/test_tui.py tests/test_tui_terminal.py tests/test_dashboard_projects.py tests/test_dashboard_http_contract.py tests/test_dashboard_motion_contract.py tests/test_phase72_memory_public.py tests/test_memory_public_contract.py tests/test_mcp.py -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import rush.tui, rush.dashboard.server, rush.cli, pathlib, sys; sys.exit(int(pathlib.Path('src/rush/dashboard/panels.js').exists()))\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/ -q -m '' -p no:cacheprovider","rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts","rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts","rtk proxy uv run --python 3.12 --extra dev mypy src/rush","rtk proxy git diff --check"],"stop_if":["A RED test looks wrong: return it to the PM; never edit it.","A legacy test fails through a documented migration mechanism (legacy list shape, base64 expand, or missing grant) but was not migrated: return to the PM for a T039 delta (not a fix round).","A T06/T02/T01/CODEC contract field the note consumes is absent.","panels.js would be needed.","Need files outside allowed_files.","Verification fails twice."]},"live":{"objective":"72-T07 live lanes against the T040 build. CLI: two owners, seven subjects, every listed action. Stdio MCP: the rush_memory v2 list refs match CLI JSON. PTY keyboard at 120x40 and 80x24. Browser at 1280x800 and 390x844 (browser-qa-agent). The T07 share of the PAS import walkthrough. Record identities, actions, states and observed results in the report's '72-T07 live lanes' section.","allowed_files":["docs/reports/phase-72-memory-acceptance.md"],"verify":["rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev rush --version; rtk proxy git rev-parse HEAD; node --version","Fixture script, run with `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python - <<'PY' ... PY`: tempfile.TemporaryDirectory HOME; git project; `rush project add <p> --allow-cache-write`; the D-T07-1 grant route; seed 7 Alice + 7 Bob rows via MemoryTool write (owner_scope); then subprocess `rush memory list`, `list --subject preference --query needle --json`, `--cursor`, `expand --id --version`, `history --id`, `explain --id`, `related --id --version`, `edit --correction reject|correct|supersede` preview then `--apply --allow-cache-write`, `archive` / `archive --restore`, `delete --target`, no-grant denial, revoke then next page","Stdio MCP: spawn `rush mcp serve` with JSON-RPC initialize and tools/call rush_memory list schema_version 2; compare refs with the CLI JSON","PTY: pty.fork `rush ui <p>` at 120x40 and 80x24. Send F3 (\\x1bOR), 4, S x8, /needle\\r, ], x, v, E, c..., Tab and Shift-Tab (\\x1b[Z), Escape, y/n, then q. Capture output with ANSI stripped, and record exit code 0","Browser: start `rush dashboard <p> --no-open --json --port 0` in the temp HOME (record its PID). browser-qa-agent opens the launch URL at 1280x800 and 390x844 and performs search, owner filter, archive toggle, paging, inspect (sha256 verified label, verified-by: plan L18), history, explain, correct, archive/restore, delete, promote, hostile row, keyboard-only Tab/Enter/Escape, and reduced motion. Do not use Kapture","PAS: preview and import one capsule through the CLI, TUI `I` and dashboard review; reject a forged verified claim (verified-by: plan L471); confirm only the intended constraint","Capture the PIDs of the dashboard and TUI processes, stop them, and confirm with `ps -p <pid>` that none remain. Delete the temp HOME before reporting"],"stop_if":["A lane cannot run its exact route. Record it as open with one exact blocker (for example browser-qa-agent unavailable, with the verbatim error, or the 73-T09 capsule operation absent at <sha>). Never simulate output.","A product assertion fails: return to the PM for a fix round. That is not an open lane.","Need credentials or a route not granted.","Need files outside allowed_files.","Verification fails twice."]}},"owner_decisions_needed":["D-T07-1: Once the screens move to the strict policy-checked list, any user with no memory grant sees 'denied' in the CLI, terminal UI and dashboard. On this board the only way to grant is the 73-T02 POLICY Python API; the setup/connect consent command is 73-T02 BOOTSTRAP, which stays in Phase 73. Which consent route should the 'denied' and 'revoked' states point to, and which should the live lanes use? (a) Add a 73-T02/BOOTSTRAP checkpoint unit (the setup consent command and its callers) on this board before 72-T07. (b) Have 72-T07 add an explicit in-app consent control to the CLI, terminal UI and dashboard: it shows the exact project, owner, sources and operations, needs the config-mutation permission, and calls grant_memory_scope(consent=True). Both deliver the full plan scope."],"evidence":["tui.py:926/4507-4512 (subject default; S cycle), 3205-3212 (legacy list), 3556 (base64 expand), 3681 (raw store peer scan), 3905/3926/4017/4321 (scope from memory_subject), 4426-4588 (no Tab handling)","server.py:283-357 (allowlists), 2607-2623 (409 mapping), 2754-2815 (legacy promote), 2976-3031 (legacy memory_query), 3749-3893 (_build_memory_section legacy path), 229 (CSP style-src 'self')","application.js:383-386 (generic reload on 409), 1212-1232 (memory JSON dump), 1023-1084 (sha256 pattern)","cli.py:3499-3532 (list requires SUBJECT QUERY), 3797-3883 (MC14 leaves require --input); rendering.py:187-212, 386-397","tests/test_phase70_t20.py:326 pins the overview row keys exactly; test_phase70_t28d.py:283-347 pin legacy filter kwargs","T003 note: grant API signatures and reason codes; BOOTSTRAP CLI stays in Phase 73 (state.yaml:207)","Baseline: test_t28d_memory_workflows 1 passed; node v26.7.0 present; the Node DOM-shim harness precedent is test_dashboard_projects.py:668-800"],"subgoal_contract":null,"parallel_safety":null,"blocked_tasks":["T039 waits on D-T07-1 for its denied/revoked action assertions."],"missing_evidence":["T06/T02/T01/CODEC gate notes are not written yet; the consumed shapes are pinned from plan §2.1 and §8 and must be re-checked at T039 start."],"required_board_updates":["T039 allowed_files: add tests/test_phase70_t28d.py, tests/test_phase70_t28d_review1.py, tests/test_memory_versions.py, tests/test_phase70_t28f_review1.py and tests/test_phase70_t28a_fixes.py (migration-only edits, every assertion kept). Replace verify with the five RED commands above.","T040 allowed_files: add src/rush/dashboard/static_assets.py (memory panel CSS; CSP blocks injected styles); remove panels.js (must not be created). Replace verify with the implement list.","T041 verify and stop_if: replace with the live list above.","Record D-T07-1 as an open owner decision that blocks T039."],"summary":"Approved design gate for 72-T07. Every screen uses the T06 strict list. One shared state classifier with 17 distinct states and concrete actions. UTF-8 expansion checks the digest; history and explain have dedicated views; correction goes through the versioned edit; the TUI gets a Tab focus ring; the browser panel is built on application.js with no innerHTML. Legacy and Phase 70 T20 contracts are kept. The matrix has 42 tests. Files missing from the packet: static_assets.py, plus migration-only edits to Phase 70 tests. One owner decision (D-T07-1, the consent route) is open.","note":"notes/T011-design-gate-72-t07.md"}}
```

graft saved roughly 1.13 million tokens this turn.