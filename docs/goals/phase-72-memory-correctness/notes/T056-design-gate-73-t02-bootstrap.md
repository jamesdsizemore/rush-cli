# T056: Design gate for the 73-T02/BOOTSTRAP checkpoint (goal-judge report, recorded verbatim)

Everything below the line is the goal-judge's T056 report, copied unchanged.

This unit exists because of owner decision D-T07-1 (2026-10-05). T057 and T058 cannot start until the owner answers OD-B1, OD-B3, OD-B4 and OD-B5.

**PM reconciliation.** The CODEC gate (T010 §4.6) and this gate disagree on what `--approve` means:
- T010 uses `--approve` as both the consent and the permission.
- Plan 73 L111 and contract C01 require two separate things: the existing invocation permission and the consent.

This gate follows the plan text, and so does the CODEC unit. T036/T037 align the capsule mapping create and revoke flags to permission flags plus `--approve` plus `--expected-policy-revision`.

**Not re-run by the PM:** this report's claims. The T057 RED author re-greps every §3.2 symbol at start HEAD (stop_if).

---

T056 gate is finished, read-only. I edited, created and deleted no files and ran no tests. Result: **approved**, but T057 and T058 cannot start until James answers four owner decisions (OD-B1, OD-B3, OD-B4, OD-B5). The command surface and file list depend on OD-B1. The packages below are for the recommended answer, option (a).

The bytes I mapped are 07775f1 plus the uncommitted `src/rush/memory/authorization.py` (1272 lines). Every symbol from earlier units that this checkpoint depends on is listed in §3.2 so the RED author can check for drift.

Things you need to know before routing this:
- **Boundary.** Plan L117 and L499 put the bootstrap dispatcher, the CLI/MCP schema and the plan's lifecycle tests in BOOTSTRAP. None of that is needed for the consent command, so under D-T07-1 it stays with Phase 73. This checkpoint alone is not a 73-T02 PASS.
- **Overlay grant included.** The 72-T05 overlay grant has the same gap D-T07-1 fixes: only the Python API can create it. I included `--overlay` in the grant command rather than drop it. Say if that should come out.
- **Conflict with the CODEC gate.** T010 §4.6 makes `--approve` both the consent and the permission. Plan L111 and C01 need two separate things, an existing permission plus consent. I settled BOOTSTRAP on the plan text; T010/T036 need to be aligned.
- **Screens stay with 72-T07.** BOOTSTRAP adds the structured pointer on every policy denial. 72-T07 renders it on the terminal UI (TUI) and dashboard screens. Today a denied maintain preview in the TUI is hidden completely.
- **Plan files with no change.** `integrations/agents.py` and `tools/install.py` need no change; tests guard install. `setup_wizard.py` changes only under option (c).

---

## (A) Note body for `docs/goals/phase-72-memory-correctness/notes/T056-design-gate-73-t02-bootstrap.md`

# T056: design gate for the 73-T02/BOOTSTRAP checkpoint (the memory consent command)

Worktree `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`. Code bytes: `07775f1` plus the uncommitted `src/rush/memory/authorization.py` (1272 lines). Read-only gate.

This unit runs after 73-T09/CODEC and before 72-T07. By then 73-T02/POLICY and 72-T01 through T06 have landed. Every symbol from those units that this design uses is listed in §3.2. T057 greps each one at its start HEAD and stops on any drift.

## 1. Checkpoint boundary

**What the plan says** (phase-73 plan):
- L111: "Explicit connect/setup owns proposed `authorization.py::register_memory_binding(...)`. It uses the same policy OS-lock/CAS writer, requiring current config-mutation permission and consent; host/session values only attribute an already approved grant."
- L115: "Explicit local setup/disconnect owns `grant_memory_scope`/`revoke_memory_scope`; `load_policy_readonly` and `resolve_memory_scope` serve read paths."
- L117: "POLICY checkpoint implements standalone authorization.py and tests/test_memory_authorization.py before72-T01; then72 defensive consumer; BOOTSTRAP checkpoint implements dispatcher/CLI/MCP/lifecycle tests. Both required for T02 PASS."
- L499: "BOOTSTRAP implements shared dispatcher, CLI/MCP schema and tests/test_memory_activation_lifecycle.py."
- L121: "Public bootstrap/session text cannot mint grants."
- C01: "only explicit local setup consent creates/enlarges grants". C01 also says to reuse "existing invocation permissions" and not to add a "duplicated permission dispatcher".
- T003 §4 item 4: "The setup and connect callers enforce the config-mutation permission before calling `grant_memory_scope` or `register_memory_binding`."

**Owner decision D-T07-1 (goal.md):** this checkpoint adds "the real setup/connect consent command that calls `grant_memory_scope(consent=True)`, with the config-mutation permission check. Denied memory screens and maintain point to this command."

L499 does not make the dispatcher a prerequisite of the consent command. The consent command calls only the POLICY writers and `load_policy_readonly`.

**This checkpoint delivers:**
1. The explicit local consent command, with preview → permission → consent → `grant_memory_scope(consent=True)`. It covers the project grant and the separately approved 72-T05 overlay grant.
2. Revoke through `revoke_memory_scope`.
3. Binding registration in connect through `register_memory_binding`.
4. The config-mutation permission check in all three.
5. Proof that MCP cannot reach any of them.
6. One canonical pointer helper.
7. A structured `next_action` on every policy denial that `MemoryTool` returns, including maintain, so the CLI, MCP and dashboard JSON name the command.
8. The new `tests/test_memory_activation_lifecycle.py`, holding the consent tests only.
9. The governance, T27 matrix, count-test, doc-coverage and user-guide updates that the new CLI surface requires.

**Phase 73 keeps (under 73-T02, plan L117/L119/L499):**
- the `bootstrap` operation and its shared dispatcher (`MemoryTool.run`, `MemoryOperation`, `request_models.py`, `tool_registry.py`), `rush memory bootstrap`, and the §2 bounded result;
- `session_binding` on reads (`_read_access`), and binding-selection recovery (`scope_required`);
- the binding inside native guidance and bootstrap requests;
- the plan's nine lifecycle tests (`test_bootstrap_known_current_ids` … `test_restricted_receiver_unchanged`), which Phase 73 appends to the file created here;
- the authorization adversarial tests that come before auto delivery;
- automatic content delivery, host-specific activation, and installed-host acceptance;
- the handoff to `docs/reports/memory-agent-adoption-acceptance.md` (same split as the CODEC checkpoint).

**Owned by 72-T07 (T039/T040), not here:** rendering `next_action` in the TUI and dashboard screens. D-T07-1 option (b), an in-app grant control, was not chosen. No screen mints grants.

## 2. Testable behavior

1. **Preview writes nothing.** `rush memory grant --project P` without `--approve`, in a non-interactive run, prints the exact proposed grant and returns `raw.state="consent_required"` with status `ok`. It creates no data root, `user/.rush`, policy file, `dashboard/project_locks` lock, project `.rush/`, `-wal` or `-shm` file. The project store reads through `TypedArtifactStore.open_readonly_view` only.
2. **Permission.** Apply needs both `--allow-cache-write` and `--allow-artifact-write`. This is the existing `_CONNECT_PERMISSION`, checked with `check_permissions`. A missing flag gives status `skipped`, a summary naming each missing flag, and zero effects. Preview needs no permission.
3. **Consent.** A grant is applied only after either:
   - an interactive `y` to `Grant this Rush memory access? [y/N]: ` (through `cli._ask_yes`, fd 0, with the same `interactive` test that connect uses); or
   - non-interactive `--approve` together with `--expected-policy-revision N`.

   `--approve` without `--expected-policy-revision` is a Click usage error (exit 2) with zero effects. `n`, EOF or Ctrl-C gives `state="declined"` with zero effects. `--consent`, `--acknowledge`, `--yes` and `--install-guidance` never imply memory consent.
4. **Exact grant.** The apply calls `grant_memory_scope(project_root=P, owner_scope, approved_sources, allowed_operations, expected_policy_revision=N, consent=True, expires_at)`. `raw.grant` is its 7-key result. Afterwards `load_policy_readonly` shows revision N+1, and `resolve_memory_scope` gives the granted access.
5. **CAS.** A stale N with a changed scope gives `E_VERSION`, status `fail`, and unchanged policy bytes, with no retry. An identical active grant gives `state="unchanged"` with no write, even at a stale N. A changed scope for the same scope key shows `preview.replaces={grant_id, approved_sources, allowed_operations, expires_at}`, and the apply supersedes that grant.
6. **Unregistered project.** Status `skipped`, `state="project_not_registered"`, and `next_action.command` = `rush project add <quoted root> --allow-cache-write --allow-artifact-write`. Zero effects.
7. **Invalid input** gives status `error`, exit 2, zero effects. This covers `*`, empty or duplicate sources, an unknown operation, `overlay_read` without `--overlay`, a naive or past `--expires-at`, a malformed `--owner`, and `--owner` together with `--overlay`.
8. **Overlay grant.** `--overlay` is a separate consent. Its owner is `user_overlay_owner_scope(data_root)`, its sources default to `[PERSONAL_PREFERENCE_SOURCE]`, and its operations are `["overlay_read","write"]`. It never changes the project grant.
9. **Revoke.** `rush memory revoke --grant-id G` previews the grant view plus the bindings it will revoke. Apply needs the same permission and consent rules and calls `revoke_memory_scope`. A second run gives `state="unchanged"`. An unknown id gives `E_GRANT_NOT_FOUND`, status `error`.
10. **Binding.**
    - `rush agent connect AGENT --session S --project P --memory-binding [--memory-grant-id G] [--approve-memory-binding --expected-policy-revision N]` runs `connect_agent` first, unchanged.
    - After that returns, and outside `_ledger_lock`, it registers `register_memory_binding(grant_id, session_id=S, host_id=AGENT, expected_policy_revision, consent=True)`.
    - `raw.memory_binding` is the 9-key binding view. A retry returns the identical record with unchanged bytes.
    - No eligible grant: `{state:"no_grant", next_action}`, status `warn`, no policy write.
    - More than one eligible grant without `--memory-grant-id`: `{state:"grant_required", grant_ids:[...]}`, status `warn`.
    - `--memory-binding` without `--project` is a usage error.
11. **MCP cannot grant, revoke or bind.**
    - `rush_agent_connection` with operation `memory_grant` or `memory_revoke` is rejected by the existing unknown-operation check.
    - A connect request carrying any of `memory_binding`, `memory_grant_id`, `approve_memory_binding`, `expected_policy_revision` or `approve` is rejected as an invalid request.
    - The policy file stays absent in every case.
12. **Install and observation consent never grant.** `connect --consent --acknowledge` and `InstallTool._process_agents(memory="on")` leave the policy file absent.
13. **Denial pointer.**
    - Every `MemoryTool` result denied by policy carries `raw.next_action={kind, reason, command, text}`, and its summary ends with `" " + text`.
    - This covers the 72-T01 read routes, 72-T06 v2 list/history/explain/edit, expand, maintain (72-T04), the preference overlay (72-T05) and capsule import (73-T09).
    - A missing-permission `skipped` result has no `next_action`.
    - The pointer comes from the policy resolve for the operation, never from whether an item is visible, so `E_NOT_VISIBLE` reveals nothing more.
    - No content appears in a denial.
14. **Pointer exactness.** When the denied request named an explicit owner, the command includes `--owner kind:id`. An overlay denial includes `--overlay`. Quoting is PowerShell single quotes on Windows and `shlex.quote` elsewhere, the same rule as `setup_wizard._quote`.
15. **Disconnect.** For `--project P`, disconnect adds `raw.memory={grants:[...], bindings:[...], revoke_commands:[...]}` for this host's active bindings. It never revokes, and the policy bytes are unchanged.

## 3. Code and caller map

### 3.1 At 07775f1 (plus the uncommitted authorization.py)

| File | Symbols (line) | Role |
|---|---|---|
| `src/rush/cli.py` | `memory_group` 3380 (invoke_without_command; overview options gate subcommands); maintain 3661 (owner default: project-id, or legacy owner if unregistered, ~3705-3720); `project add` 3896; `agent_group` 4676; `agent connect` 4691-4865 (`interactive` 4815); `_profile_consent` 4868; `_is_terminal` 4895; `_confirm_guidance` 4902; `_ask_yes` 4915; `agent disconnect` 4936-4961 (no permission flags); `install` 5027; `setup` 939 | Add the `memory grant` and `memory revoke` leaves; add connect and disconnect options |
| `src/rush/cli_support/options.py` | `permission_options` 64 | Reused |
| `src/rush/cli_support/rendering.py` | `exit_code_for` 70 | ok/skipped→0, warn/fail→1, error→2 |
| `src/rush/tools/agent_connection.py` | `AgentAction` 60; `_CONNECT_PERMISSION` 62; `_DISCONNECT_FIELDS` 64-73; `run` 125 (connect permission 153-158); `_dispatch` 318; `handle_request` 383; `_handle_request_unsafe` 408 (operation allowlist 415, connect permission 426-433); `_handle_disconnect_request` 452 | Holds the consent implementation (AGENTS.md: CLI implementations live in `src/rush/tools/`) |
| `src/rush/integrations/agents.py` | `initialize_agent_memory` 1006 (agent_memory.json bookkeeping, never authority); `_ledger_lock` 1487; `connect_agent` 2431; `disconnect_agent` 2870 | No change. The binding runs after `connect_agent` returns. |
| `src/rush/tools/install.py` | `_process_agents` 926 (user scope, `consent=(memory=="on")` at 986); `run_install_command` 1132 | No change. Test-guarded. |
| `src/rush/tools/setup_wizard.py` | `_quote` 1142; `setup_resume_command` 1150 | Quoting precedent. No change (unless OD-B1 is (c)). |
| `src/rush/memory/authorization.py` | `GRANT_OPERATIONS` 48; `POLICY_RELATIVE_PATH` 51; `MemoryPolicyError` 97; `_now` 121; `policy_path` 197; `user_overlay_owner_scope` 214; `hold_policy_lock` 220; `_worktree_id` 230; `_registry_lookup` 235; `load_policy_readonly` 653; `grant_memory_scope` 836 (supersedes the same scope key; identical grant is a no-op); `revoke_memory_scope` 942; `register_memory_binding` 999; `resolve_memory_scope` 1085 | Writers and readers called as they are. Only additive helpers are added (§4.6). |
| `src/rush/tools/memory.py` | `MemoryOperation` 72; `_WRITE_PERMISSION` 129; `_CODE_STATUS` 141; `run` 401; `_parse_owner_scope` 1431 (owner None stores NULL, which reads as the legacy path owner); `_run_maintain` 1791; `memory_overview` 3441 | Where the denial `next_action` is attached |
| `src/rush/memory/store.py` | `OwnerScope` 249; `legacy_owner_scope` 290; `owner_scope_for_row` 309; `open_readonly_view` (~1844) | Owner parsing; read-only inventory |
| `src/rush/workflows/projects.py` | `register_project` 413; `read_registry_strict` 293 | Test fixtures; identity |
| `src/rush/dashboard/server.py` | `_tool_result_response` 2607 (passes `raw` through unchanged); `_dispatch_memory_maintain` 3158 | No change; `next_action` reaches the JSON |
| `src/rush/tui.py` | `_memory_maintain_preview` 4057 (a `fail` denial is not shown: only `error` is surfaced, 4089) | 72-T07 territory; no change here |
| `src/rush/governance/public_operations.py` | `build_operations_inventory` 42; agent rows 447-490 | New leaf rows |
| `governance/public-operations.toml` | generated by `scripts/build_remediation_manifests.py --operations` | Regenerate; never hand-edit (`tests/test_phase51_public_operations.py:101`) |
| `tests/fixtures/phase70/cli-outcomes.json` | 181 cases at 07775f1; `agent.connect` and `agent.disconnect` case shapes | Two new cases; T27 needs set equality with the live Click registry |
| `tests/test_phase54_operation_adapters.py` | 118-126 (total and admin counts) | +2 total, +2 admin over the start-HEAD values |
| `scripts/sync_docs.py` | `_cli_contracts` 279; `check_docs` 646 | `docs/reports/phase-64-66-documentation-coverage.md` records CLI parameters and doc hashes |
| `docs/user-guide/working-with-ai-agents.md` | connect section L52-L130 | Document the consent commands |
| `tests/conftest.py` | `posix_only` / `windows_only` 64-80 | The only platform markers allowed |

Files the packet names but that need no change: `integrations/agents.py`, `tools/install.py`.

Files the packet is missing:
- `src/rush/memory/authorization.py` (additive helpers only);
- governance, T27 fixture, count-test and doc-coverage files;
- the user guide is named in the plan only "after route passes", which it will.

### 3.2 Earlier-unit symbols this depends on (T057 re-greps; stop on drift)

- **POLICY:** the 8 public functions and signatures above; `MemoryPolicyError.code` values `E_CONSENT`, `E_INPUT`, `E_VERSION`, `E_PROJECT_NOT_REGISTERED`, `E_GRANT_NOT_FOUND`, `E_GRANT_INACTIVE`, `E_PRINCIPAL`, `E_POLICY_INVALID`, `E_LOCK`, `E_POLICY_IO`, `E_POLICY_REDACTION`; and the 21 resolve reasons: `invalid_request`, `policy_missing`, `policy_invalid`, `principal_unavailable`, `project_missing`, `project_registry_invalid`, `binding_unknown`, `binding_revoked`, `binding_scope_mismatch`, `project_not_registered`, `no_grant`, `principal_mismatch`, `relinked`, `worktree_mismatch`, `revoked`, `expired`, `owner_not_granted`, `owner_required`, `operation_not_granted`, `source_not_granted`, `binding_stale`.
- **72-T01:** `retrieval.MemoryAccess.resolve` (returns None on denial), `tools/memory.py::_read_access(root, op, allowlist, owner)` and its fallback outputs (`skipped`, `E_PERMISSION`, and `E_NOT_VISIBLE` for expand).
- **72-T04:** `maintenance.MaintenanceAccessDenied(.reason)`. `_run_maintain` maps it to `fail` with raw `{"code":"E_PERMISSION","reason":...}`. Preview resolves `list`; apply resolves `write`.
- **72-T05:** `PERSONAL_PREFERENCE_SOURCE`, `PROJECT_PREFERENCE_SOURCE`, `LEGACY_PREFERENCE_SOURCE`; the denied reason from `PreferenceStore.resolve`; the `preference` MemoryTool operation.
- **72-T06:** v2 `E_SCOPE`/`E_OWNER` results carrying `reason`; the `history`/`explain` leaves; the count values and toml at start HEAD.
- **73-T09/CODEC:** the `capsule` operation's write-grant denial; the `rush memory capsule mapping create|revoke` flags; CODEC's additive mapping functions in `authorization.py`, which must not collide with §4.6 names.

## 4. Design

### 4.1 Command surface (recommended OD-B1 option (a))

**`rush memory grant` (new, CLI-only, admin, stateful-mutation).** Options:

| Option | Meaning |
|---|---|
| `--project PATH` | Default `.` |
| `--owner KIND:ID` | Split on the first `:`; kind is one of user/project/session/agent; default per OD-B5 |
| `--overlay` | Overlay grant; excludes `--owner` |
| `--source S` (repeatable) or `--all-current-sources` | Mutually exclusive |
| `--operation OP` (repeatable) | Default per OD-B4; `overlay_read` only with `--overlay` |
| `--expires-at ISO8601` | Timezone offset required |
| `--expected-policy-revision N` | |
| `--approve` | |
| `permission_options` | |
| `--json` | |

**`rush memory revoke` (new, CLI-only, admin, stateful-mutation).** Options: `--grant-id ID` (required), `--expected-policy-revision N`, `--approve`, `permission_options`, `--json`.

**`rush agent connect` (existing leaf).** Adds `--memory-binding`, `--memory-grant-id ID`, `--approve-memory-binding` and `--expected-policy-revision N`. The binding question is separate and never merged with the guidance or profile questions.

**`rush agent disconnect`.** Adds no new options. It adds the read-only `raw.memory` listing.

**Implementation.** `AgentConnectionTool.run` gains actions `memory_grant` and `memory_revoke` (and `AgentAction` gains them), plus connect's binding step. `handle_request` keeps its allowlist `("list","connect","doctor","disconnect")`, so MCP rejects the new actions. `__call__` and `mcp_description` are unchanged. No new MCP tool, MemoryTool operation, request model or tool-registry entry.

**Pointer target:** `rush memory grant --project <q>`. It runs in preview form, so a model that runs it in a shell only previews.

### 4.2 Flow

The grant and revoke apply flow, in order:
1. Validate inputs (pure). Click usage errors come first.
2. Read-only state: `load_policy_readonly(data_root)`; a new `authorization.project_identity(project_root=P)`; existing grants for this canonical root and principal; `replaces`; and the store inventory (OD-B3) from `open_readonly_view`.
3. Build the preview.
4. If neither interactive nor `--approve`: return `consent_required`.
5. Permission check. Missing gives `skipped`.
6. Consent: interactive `_ask_yes` on the preview, or `--approve`.
7. Expected revision: the preview's `policy_revision` when interactive, otherwise `--expected-policy-revision`.
8. Call the POLICY writer with `consent=True`.
9. Map the result.

The binding apply runs after `connect_agent` succeeds:
- Select the grant: from `--memory-grant-id`, or the single active, unexpired, non-overlay grant for this principal, root and current worktree.
- Preview `{grant, host_id, session_id, policy_revision}`, then the permission check (connect has already checked it), then consent, then `register_memory_binding`.
- A binding failure never rolls back connect. It sets `memory_binding.state` and status `warn`.

Lock rules: no `_ledger_lock` and no dashboard project lock is held while the policy lock is held (T003 lock order).

The preview carries these keys:

```
{project_root, project_id, owner_scope, approved_sources, allowed_operations,
 expires_at, policy_path, policy_revision, replaces, store_sources, store_owners}
```

`raw.state` is one of `consent_required`, `declined`, `granted`, `unchanged`, `sources_required`, `project_not_registered`, `revoked`.

`MemoryPolicyError` maps to status and exit code like this:

| Code | Status (exit) |
|---|---|
| `E_INPUT`, `E_GRANT_NOT_FOUND`, `E_POLICY_INVALID`, `E_LOCK`, `E_POLICY_IO`, `E_POLICY_REDACTION` | `error` (2) |
| `E_VERSION`, `E_PRINCIPAL`, `E_GRANT_INACTIVE` | `fail` (1) |
| `E_PROJECT_NOT_REGISTERED` | `skipped` (0), with `next_action` |

`raw` carries `{"code","reason"}`.

### 4.3 The config-mutation permission check

The check is the existing `_CONNECT_PERMISSION` (cache_write plus artifact_write) through `rush.permissions.check_permissions`. This is the "existing invocation permissions" that C01 requires. It runs before consent and before any writer call. Preview and disconnect listing are read-only and need no permission.

### 4.4 Denied-state pointer

The helper `authorization.memory_next_action(*, reason, project_root, owner_scope=None, overlay=False, policy_path=None) -> dict | None` is total over the 21 reasons:

| Reasons | kind | command | text |
|---|---|---|---|
| `policy_missing`, `no_grant`, `principal_mismatch`, `relinked`, `worktree_mismatch`, `revoked`, `expired`, `owner_not_granted`, `operation_not_granted`, `source_not_granted` | `memory_grant` | `memory_grant_command(project_root, owner_scope, overlay)` | `To grant memory access, run: <command>` |
| `project_not_registered` | `project_add` | `rush project add <q> --allow-cache-write --allow-artifact-write` | `Register the project first: <command>` |
| `policy_invalid` | `policy_invalid` | grant command | `The memory policy file <path> is invalid; Rush will not read or change it. Move it aside, then run: <command>` |
| `owner_required` | `owner_required` | grant command | `Several owners are granted; pass an explicit owner scope. <command> lists this project's grants.` |
| `invalid_request`, `principal_unavailable`, `project_missing`, `project_registry_invalid`, and the four `binding_*` reasons | — | — | None (no runnable command; binding reads arrive with the Phase 73 dispatcher) |

`memory_grant_command(*, project_root, owner_scope=None, overlay=False) -> str` builds `rush memory grant --project <q>`, adding `--owner <kind:id quoted>` when an owner was given and `--overlay` for the overlay. It uses the platform quoting rule. Both helpers are stdlib-only, so `test_module_import_is_cycle_free` still holds.

**Attachment point** (`tools/memory.py`): one private `_attach_policy_next_action(result, *, root, grant_operation, owner_scope, sources, overlay=False)`. It runs only on policy-denial paths:
- the 72-T01 `_read_access` None branch;
- the 72-T04 `MaintenanceAccessDenied` path;
- the 72-T06 `E_SCOPE`/`E_OWNER` results;
- the 72-T05 overlay denial;
- the CODEC capsule write-grant denial.

When the reason is not already present (the T01 None branch), it re-runs read-only `resolve_memory_scope` with the same arguments. The CLI shows the pointer through the summary. MCP returns the same `raw`. The dashboard passes `raw` through (`server.py:2607`). 72-T07 renders `next_action` in the TUI and browser.

### 4.5 How maintain and reads reference it

- **CLI maintain.** `rush memory maintain --task T --allow-cache-write` with no grant: status `fail` (exit 1), raw `{"code":"E_PERMISSION","reason":"policy_missing","next_action":{...}}`, and stdout contains the command. The owner shown is the one the CLI resolved, project-id or legacy.
- **Dashboard `memory_maintain`.** Same `raw`.
- **Reads** (ask/recall/list/v2 list/expand/history/explain): same rule.

### 4.6 Additive `authorization.py` helpers (writers, loader and resolve unchanged)

- `project_identity(*, project_root, data_root=None) -> {project_root, project_id|None, worktree_id|None, registry_state}`. It is read-only, uses `_registry_lookup` and `_worktree_id`, and creates nothing.
- `memory_grant_command(...)`, described in §4.4.
- `memory_next_action(...)`, described in §4.4.

## 5. Cross-task conflicts

1. **72-T04 (T027/T028).** Maintain's denial `raw` gains `next_action` and its summary gains a suffix. Any T04 or Phase 70 retained test that asserts exact equality on that `raw` or summary needs a migration-only edit. T057 enumerates them; the PM adds them to T058.
2. **72-T07 (T039/T040).**
   - `ui_state.action` for denied, revoked, expired and policy-missing states must come from `raw.next_action.text`, with the command shown verbatim. Keep one source of truth.
   - The TUI maintain preview must surface `fail`/`E_PERMISSION` plus `next_action`; at `tui.py:4084-4105` it is hidden today.
   - No in-app grant control.
3. **73-T09/CODEC (T010/T036).** §4.6 of the CODEC note makes `--approve` both consent and permission. This design follows plan L111 and C01: permission flags plus `--approve` plus `--expected-policy-revision`. Align the CODEC mapping commands, or record the divergence. CODEC also edits `authorization.py`; the helper names in §4.6 must not collide.
4. **72-T06.** The count tests move again by +2 total and +2 admin. Its v2 denials gain `next_action`.
5. **72-T05.** The overlay grant gets a real consent path through `--overlay`. Its default sources are T05's constant.
6. **Phase 70 retained fixtures.**
   - `cli-outcomes.json` gains `memory.grant` and `memory.revoke` cases (success, denied, failure; side effects `<data-root>/user/.rush/memory_authorization.json` and `<data-root>/dashboard/project_locks/*`).
   - The `agent.connect` and `agent.disconnect` argv are unchanged.
   - The `memory.maintain` substring expectations still hold.
   - The doc-coverage contracts block must record the new leaves and the new connect options.
7. **Phase 73.** It consumes the commands, the helpers and the lifecycle file, and adds the dispatcher, binding-aware reads and the guidance binding (§1).

## 6. Test matrix (`tests/test_memory_activation_lifecycle.py`, new)

Fixture rules:
- `tmp_path` only.
- Patch `HOME`, `XDG_DATA_HOME` and `LOCALAPPDATA` so that `default_data_root()` resolves under `tmp_path`; delete any temp HOME.
- Register the project with `register_project(proj, data_root=default_data_root())`.
- Seed the store with `TypedArtifactStore(proj).write`: two rows from `src-a` (owner project:<id>), one from `src-b` (legacy owner).
- Agent connect uses `claude-code` in a tmp home with an explicit fake `--rush-binary`, following `tests/test_agent_connection.py::_home_with`.
- `_tree(path)` snapshots the tree.
- Interactive tests monkeypatch `rush.cli.os.isatty`, `rush.cli._is_terminal` and `rush.cli._ask_yes`.
- Import authorization inside each test body.
- No skips. Platform tests use `posix_only` or `windows_only` only.

| Test | Setup | Action | Exact assertions |
|---|---|---|---|
| `test_grant_preview_writes_nothing` | seeded store | `memory grant --project P --source src-a --json` | status ok; state `consent_required`; preview keys and values exact (sources `["src-a"]`, operations per OD-B4, `policy_revision` 0, `replaces` None); data-root and project tree unchanged; no policy file and no lock |
| `test_grant_sources_required_preview_lists_store_sources` | seeded / empty store | no `--source`; `--all-current-sources` | state `sources_required`, `store_sources==[{"source":"src-a","rows":2},{"source":"src-b","rows":1}]`, DB bytes and mtime unchanged, no wal/shm; empty store with `--all-current-sources` gives `E_INPUT` `no_sources` |
| `test_grant_requires_config_mutation_permission` | — | `--approve --expected-policy-revision 0` with neither flag, then each single flag | `skipped`, summary names exactly the missing flags, no policy file |
| `test_grant_requires_explicit_consent_and_expected_revision` | — | permission only; `--approve` without revision; `connect --consent --acknowledge --yes` | `consent_required`; exit 2 usage error; no file |
| `test_grant_applies_exact_scope` | — | permission, approve, revision 0 | state `granted`; 7-key grant exact; load gives revision 1; resolve `list` gives read/granted/`["src-a"]`; resolve `write` gives write |
| `test_grant_stale_revision_refused_identical_is_noop` | grant at revision 1 | changed sources at 0; identical at 0 | `fail`/`E_VERSION`, bytes unchanged; `unchanged`, bytes unchanged |
| `test_grant_supersede_preview_names_replaced_grant` | revision 1 | new sources at 1 | `preview.replaces` exact; old grant revoked with `superseded_by` the new id |
| `test_grant_unregistered_project_points_to_project_add` | unregistered dir | preview and apply | `skipped`, state `project_not_registered`, exact project-add command, no file |
| `test_grant_invalid_inputs_zero_effect[...]` | — | `*`; duplicate source; bogus operation; `overlay_read` without `--overlay`; past or naive expiry; `--owner bad`; `--owner` with `--overlay` | each exit 2, no file |
| `test_grant_interactive_prompt_yes_and_no` | interactive patches | answer n, then y, no revision flag | prompt text exact; `declined` with no file; `granted` at the preview revision |
| `test_overlay_grant_is_separate_consent` | project grant | `--overlay --approve` | new grant id, owner `user_overlay_owner_scope`, operations `["overlay_read","write"]`; the project grant is unchanged and still active |
| `test_revoke_preview_apply_and_noop` | grant and binding | preview; apply; repeat; unknown id | preview lists the bindings; `revoked_bindings` exact; resolve gives `revoked`; `unchanged`; `E_GRANT_NOT_FOUND` |
| `test_connect_memory_binding_registers_and_retries_idempotently` | grant at revision 1 | connect with `--memory-binding --approve-memory-binding --expected-policy-revision 1`; repeat | 9-key view (host `claude-code`, session `s1`, `policy_revision` 2); resolve with the binding gives `session_binding==binding_id`; retry identical, bytes unchanged |
| `test_connect_binding_without_grant_points_to_grant` | no grant | connect with `--memory-binding` | registration ok; `memory_binding.state` `no_grant`; `next_action.command` exact; status warn; no policy file |
| `test_connect_binding_multiple_grants_requires_grant_id` | two owner grants | without, then with `--memory-grant-id` | `grant_required` with exact ids; then the binding's `grant_id` equals the one given |
| `test_observation_consent_and_install_never_grant` | — | `connect --consent --acknowledge`; `InstallTool._process_agents(memory="on")`; then `memory grant` preview | no policy file; preview `policy_revision` 0 and no existing grants |
| `test_mcp_cannot_grant_revoke_or_bind` | — | `rush_agent_connection` with operation `memory_grant` and `memory_revoke`, and connect with each memory key | each invalid-request error; no policy file |
| `test_policy_denials_carry_grant_pointer[list_v2, ask, expand, maintain_cli, maintain_dashboard, preference_overlay, capsule_import]` | no policy | each route | `raw.next_action` exact (`memory_grant`, `policy_missing`, command); summary ends with the text; no row content |
| `test_denial_pointer_follows_reason_changes` | grant with operations `["list"]` | maintain apply; revoke; expired grant (patched `_now`) | reasons `operation_not_granted`, `revoked`, `expired`, same command |
| `test_permission_skip_has_no_grant_pointer` | no policy | maintain without, then with `--allow-cache-write` | `skipped` with no `next_action`; `fail` with `next_action` |
| `test_next_action_mapping_covers_every_resolve_reason` | — | `memory_next_action` for all 21 reasons | exact kind, command and text table of §4.4; None for the 8 non-actionable reasons |
| `test_grant_command_quoting_posix` (posix_only) | root with a space and `'` | helper | `shlex.quote` form, with `--owner` and `--overlay` variants |
| `test_grant_command_quoting_windows` (windows_only) | same | helper | PowerShell form |
| `test_new_consent_leaves_in_public_manifest` | — | `build_operations_inventory()` | `memory grant` and `memory revoke` present: MCP name None, impl `rush.tools.agent_connection:AgentConnectionTool`, `stateful-mutation`, `admin` |
| `test_disconnect_lists_memory_grants_without_revoking` | grant and binding | `agent disconnect claude-code --project P --json` | `raw.memory` exact (grants, bindings, `revoke_commands`); policy bytes unchanged |

## 7. Worker packages

These are for OD-B1 option (a). Under (b): drop the two new leaves and their governance, fixture and count edits; add `--grant-memory`/`--approve-memory-grant` to connect and `--revoke-memory` with permission flags to disconnect. Under (c): add `src/rush/tools/setup_wizard.py` and the Phase 70 T24/T26 setup tests whose review digests change.

**T057 RED.**
- allowed_files: `tests/test_memory_activation_lifecycle.py`.
- verify: the RED form on `tests/test_memory_activation_lifecycle.py`.
- The receipt lists every existing test that asserts exact equality on a policy-denial `raw` or summary, or on a disconnect `raw`, at start HEAD.

**T058 implement (Opus).** The files are in the receipt. The verify set is the full gate.

## Owner decisions needed

- **OD-B1, command surface.**
  - (a) `rush memory grant` and `rush memory revoke` leaves, plus `agent connect --memory-binding`, plus a disconnect listing. The pointer is directly runnable. *Recommended.*
  - (b) Plan-literal routing: grant and binding via `agent connect --grant-memory`, revoke via `agent disconnect --revoke-memory`. The pointer is the connect command with AGENT/SESSION placeholders.
  - (c) The grant as a separately consented, digest-bound stage of `rush setup PATH --grant-memory`, with binding in connect and revoke in disconnect. The pointer is `rush setup <root> --grant-memory`.
- **OD-B3, store inventory in the preview.**
  - (a) The CLI preview (text and JSON) lists the distinct source labels and owner scopes with row counts, read-only. *Recommended.*
  - (b) Labels are listed only on an interactive terminal. JSON and non-interactive runs require explicit `--source`/`--owner` and print no labels.
- **OD-B4, default operations when `--operation` is omitted.**
  - (a) `ask`, `bootstrap`, `expand`, `history`, `list`, `write`. *Recommended.*
  - (b) `--operation` is required, with no default.
- **OD-B5, default owner when `--owner` is omitted.** In both options, denial pointers always carry the denied request's explicit owner.
  - (a) `legacy_owner_scope(root)`, which matches rows written by agents with no owner and the 72-T05 project grant.
  - (b) `OwnerScope("project", project_id)`, which matches the maintain CLI and TUI defaults.

---

## (B) Receipt

```json
{"goalbuddy_receipt_v1":{"result":"done","task_id":"T056","board_path":"/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml","decision":"approved","full_outcome_complete":false,"rationale":"Designable at 07775f1 plus uncommitted authorization.py. Per D-T07-1 this checkpoint delivers the CLI-only consent command (preview, existing _CONNECT_PERMISSION check, consent, grant/revoke/binding writers, overlay grant), MCP non-reachability, and a single next_action pointer on every MemoryTool policy denial. L499's dispatcher, bootstrap op, CLI/MCP schema, binding-aware reads and the plan's nine lifecycle tests stay with Phase 73 (L117/L499); this is not a 73-T02 PASS. agents.py and install.py need no change (test-guarded). Governance, T27 fixture, count, doc-coverage and user-guide files are added. T057/T058 are gated on OD-B1/B3/B4/B5.","worker_package":{"red":{"card":"T057","objective":"Write the T056 section 6 matrix in tests/test_memory_activation_lifecycle.py for OD-B1 option (a) as answered by James, after re-grepping every section 3.2 symbol at start HEAD. Prove every test FAILS by execution before any production change. In the receipt list every existing test that asserts exact equality on a policy-denial raw/summary or an agent disconnect raw.","allowed_files":["tests/test_memory_activation_lifecycle.py"],"verify":["rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_memory_activation_lifecycle.py','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\""],"stop_if":["Any OD-B1/B3/B4/B5 still unanswered.","Any section 3.2 symbol, signature, reason code or error code differs at start HEAD.","A test can only be written by editing a non-test file or another test file.","A test passes before implementation and cannot be made to assert new behavior.","Temp dirs not via tmp_path/TemporaryDirectory, a real data root touched, or any skip marker other than posix_only/windows_only needed.","Verification fails twice."]},"implement":{"card":"T058","model":"Opus","objective":"Implement T056 section 4 (option a) until every T057 test passes: AgentConnectionTool memory_grant/memory_revoke actions and the connect binding step; rush memory grant/revoke leaves and the connect --memory-binding/--memory-grant-id/--approve-memory-binding/--expected-policy-revision options in cli.py; the disconnect raw.memory listing; additive authorization.py helpers project_identity, memory_grant_command and memory_next_action; tools/memory.py _attach_policy_next_action on every policy-denial path; governance rows plus regenerated toml; cli-outcomes cases; count update; user guide and doc-coverage receipt. Do not edit RED tests. Max two fix rounds.","allowed_files":["src/rush/tools/agent_connection.py","src/rush/cli.py","src/rush/memory/authorization.py","src/rush/tools/memory.py","src/rush/governance/public_operations.py","governance/public-operations.toml","tests/fixtures/phase70/cli-outcomes.json","tests/test_phase54_operation_adapters.py","docs/user-guide/working-with-ai-agents.md","docs/reports/phase-64-66-documentation-coverage.md","existing test files enumerated in the T057 receipt (migration-only exact-assertion edits; PM amends with that list)"],"verify":["rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_memory_activation_lifecycle.py tests/test_memory_authorization.py tests/test_agent_connection.py tests/test_mcp.py tests/test_bootstrap_install.py tests/test_memory_public_contract.py tests/test_memory_operation_metadata.py tests/test_phase54_operation_adapters.py tests/test_phase51_public_operations.py tests/test_phase70_t27.py -q -p no:cacheprovider","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys,re; r=subprocess.run([sys.executable,'-m','pytest','tests/','-q','-m','','-p','no:cacheprovider'],capture_output=True,text=True); out=r.stdout; print(out[-3000:]); fails=set(re.findall(r'^(?:FAILED|ERROR) (\\S+)',out,re.M)); base={'tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory','tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts'}; last=(out.strip().splitlines() or [''])[-1]; print('NEW FAILURES:',sorted(fails-base)); sys.exit(0 if fails<=base and 'skipped' not in last and ' error' not in last else 1)\"","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush","rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check","rtk proxy git diff --check"],"stop_if":["Need files outside allowed_files (PM amends only with gate-note justification).","Any change to authorization.py loader, writers or resolve, or a helper-name collision with CODEC's mapping functions.","Any path lets MCP, model text, --consent/--acknowledge/--yes/--install-guidance, install --memory, or a dashboard/TUI control create, revoke or bind a grant.","A policy write occurs on preview, on a declined or permission-skipped run, or while the ledger or a dashboard project lock is held.","Doc text would match tests/test_phase70_t25.py _CURSOR_RE.","Verification fails twice."]}},"evidence":["docs/phase-plans/phase-73-agent-activation-and-continuity-plan.md:111,115,117,119,121,123,499","docs/phase-plans/memory-program-contract.md:36-40 (C01)","notes/T003-design-gate-policy.md:53,116,287-290","notes/T011-design-gate-72-t07.md:21-24,226","notes/T007-design-gate-72-t04.md:132-178","notes/T008-design-gate-72-t05.md:304-306","src/rush/tools/agent_connection.py:60-73,153-158,383-433","src/rush/cli.py:3661-3720,4691-4961","src/rush/tools/install.py:926-986","src/rush/memory/authorization.py:836-940,999,1085 (21 denial reasons)","src/rush/tools/memory.py:1431-1453 (owner None stored as legacy owner)","src/rush/dashboard/server.py:2607-2623,3158-3200","src/rush/tui.py:4057-4105","src/rush/tools/setup_wizard.py:1142-1153","src/rush/governance/public_operations.py:447-490","tests/test_phase54_operation_adapters.py:118-126","scripts/sync_docs.py:279,646"],"subgoal_contract":null,"parallel_safety":null,"blocked_tasks":["T057","T058"],"missing_evidence":["Post-72-T01..T06 and CODEC bytes for every section 3.2 symbol (unbuilt; T057 re-greps)","The exact-assertion test list affected by next_action (T057 enumerates)"],"required_board_updates":["T057/T058: replace prep-time allowed_files/verify/stop_if with this worker_package; gate both on OD-B1/B3/B4/B5.","goal.md: record the checkpoint boundary. BOOTSTRAP-consent is delivered here; the dispatcher, bootstrap op, CLI/MCP schema, session_binding reads, guidance binding, the plan's nine lifecycle tests and the acceptance report stay with Phase 73 under 73-T02 (plan L117/L499). Not a 73-T02 PASS.","T039/T040 (72-T07): ui_state.action for denied, revoked, expired and policy-missing comes from raw.next_action.text; the TUI maintain preview surfaces fail/E_PERMISSION plus next_action (tui.py:4084-4105); the dashboard renders next_action; no in-app grant control.","T010/T036 (CODEC): align the capsule mapping create/revoke flags with permission flags plus --approve plus --expected-policy-revision (plan L111/C01), or record the divergence; avoid helper-name collisions in authorization.py.","T027/T028 and the Phase 70 retained-fixture owners: maintain denial raw/summary gains next_action; exact-assertion edits are migration-only."],"owner_decisions_needed":[{"id":"OD-B1","topic":"Consent command surface","options":["(a) rush memory grant / rush memory revoke CLI-only leaves + agent connect --memory-binding + disconnect read-only listing; pointer `rush memory grant --project <root>` (recommended)","(b) grant and binding via agent connect --grant-memory, revoke via agent disconnect --revoke-memory; pointer is the connect command with AGENT/SESSION placeholders","(c) grant as a separately consented, digest-bound stage of rush setup PATH --grant-memory, binding in connect, revoke in disconnect; pointer `rush setup <root> --grant-memory`"]},{"id":"OD-B3","topic":"Store inventory in the grant preview","options":["(a) the CLI preview (text and JSON) lists distinct source labels and owner scopes with row counts, read-only (recommended)","(b) labels listed only on an interactive terminal; JSON and non-interactive runs require explicit --source/--owner and print no labels"]},{"id":"OD-B4","topic":"Default operations when --operation is omitted","options":["(a) ask, bootstrap, expand, history, list, write (recommended)","(b) --operation required, no default"]},{"id":"OD-B5","topic":"Default owner when --owner is omitted (denial pointers always carry the denied request's owner)","options":["(a) legacy_owner_scope(root): matches agent-written rows and the 72-T05 project grant","(b) OwnerScope('project', project_id): matches the maintain CLI and TUI defaults"]}]}}
```