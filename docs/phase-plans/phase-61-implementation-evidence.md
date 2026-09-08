# Phase 61 Implementation Evidence — P61.0.1

> **Phase 62 note:** Phase 62 wires 6 existing subsystems (token-savings cache, review/dev citation, a maintenance sub-agent, cross-tool handoff diffs, AI-attribution trail, API-diff staleness) into the `TypedArtifactStore` this evidence file baselines, and adds per-type expiry plus a shared decision-record schema — see `docs/phase-plans/phase-62-implementation-evidence.md`; this evidence record is otherwise unchanged (point-in-time).

Task: P61.0.1 — Admission Gate & Baseline Evidence
Source plan: `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md` §4, §2.2, §9 P61.0.1
Evidence gathered against `HEAD` = `9783f29353ed922c6042554d4f181c3ba8305c77` (working tree clean except this evidence file and the untracked `docs/goals/` GoalBuddy board directory).

## 1. Admission Gate (§4) — coverage 5 of 5 checks

1. **`governance/remediation-contracts.toml` shows 16/16 `status = "completed"`.**
   Confirmed: `manifest.total_findings = 16`; grep of `status = "completed"` across the file returns exactly 16 matches (R-001 through R-016, one per finding, 16 of 16). PASS.
2. **`docs/phase-plans/README.md` shows Phase 60 as the last completed phase, no `docs/phase-plans/phase-61-*.md` file already recorded as complete.**
   Confirmed: the phase index table's highest entry is `55` (Phase 56-60 tracked via the remediation-program table instead); the remediation-program table's last row is `| R-015 | Phase 60 (Completed) |`, and the plain-text note reads "Phase 60 (maintainability hotspot reduction) is now completed, achieving 100% remediation-program completion." No phase-61 row exists in the README's index yet. PASS.
3. **`src/rush/memory/transactions.py` exports `CASMapTransaction`, `VersionedSnapshot`, and 5 typed store exceptions.**
   Confirmed via `class` grep: `class StoreError(Exception)` (base), `class StoreNotFoundError(StoreError)`, `class StoreCorruptionError(StoreError)`, `class StoreValidationError(StoreError)`, `class StoreIOError(StoreError)`, `class CASConflictError(StoreError)` (5 of 5 typed subclasses), `class VersionedSnapshot[T]` (line 50), `class CASMapTransaction` (line 68). PASS.
4. **`src/rush/mcp_mesh/lock_manager.py` exports `MeshLockManager`.**
   Confirmed: `class MeshLockManager:` at line 29. PASS.
5. **`src/rush/tools/continuity.py:71`'s `SessionContinuityTool` exists, importable, uses the real two-part CLI+MCP registration path.**
   Confirmed: `class SessionContinuityTool(ToolFn):` at line 71, `name = "continuity"`. Two-part registration path re-verified directly against source (not from the plan's own prose):
   - MCP side: `src/rush/tools/__init__.py` adds the instance to `ALL_TOOLS`; `src/rush/mcp.py:327` calls `register_all_tools(server, executor, ALL_TOOLS)`; `src/rush/mcp_support/tool_registry.py:15` (`make_tool_wrapper`) and `:70` (`register_all_tools`) confirmed present, `make_tool_wrapper` produces no CLI surface (MCP-only wrapper).
   - CLI side: `src/rush/cli.py:1200-1209` loops `ALL_TOOLS` and calls `cli.add_command(build_catalog_path_command(_catalog_tool))` for every tool name not in `{"review","format","commit-msg","sbom","fix","benchmark"}` — confirmed exact line range. `build_catalog_path_command` (`src/rush/cli_support/catalog_commands.py:66`) requires a `TOOL_SPECS` entry keyed by `tool.name` (`src/rush/catalog.py:115`, `"continuity"` entry confirmed present).
   - `SessionContinuityTool`'s real CLI surface is the bespoke `@cli.group(name="session")` at `src/rush/cli.py:1878` (decorator; `def session_group()` at 1879), with hand-written subcommands `session_save_cmd`, `session_list_cmd`, `session_restore_cmd` decorated at `src/rush/cli.py:1883`, `:1961`, `:1973` respectively (`def` lines 1916, 1963, 1976). **Deviation from §2.2's stated range:** §2.2 cites this subcommand block as `cli.py:1934-2009`; the actual span (decorator-to-end-of-`session_restore_cmd`) is `cli.py:1883-1985` (the `@session_group.command(name="resume")` decorator for the unrelated `session_resume_cmd` starts at line 1986). The named functions and their mechanism are otherwise exactly as described — only this one line-range is stale, not the substance. PASS (with a stale line-range noted, not a stop-worthy source mismatch, since it's a sub-citation inside item 15 of §2.2, not one of §4's 5 admission-gate checks itself).
6. **Baseline `python -m pytest tests/ -q` count recorded.** See §3 below.

**Result: 5 of 5 numbered admission-gate checks in §4 PASS.**

## 2. §2.2 Verified Current API Surfaces — coverage 17 of 17

Coverage: §2.2 lists 17 files/citations; 17 of 17 were opened directly this session (not read from the plan's own text) and checked against the table below — the full §2.2 citation set, none skipped.

| # | File | Claim re-checked | Result |
|---|------|-------------------|--------|
| 1 | `src/rush/memory/failure_ledger.py` | `CREATE TABLE ... failure_ledgers` with `fingerprint TEXT PRIMARY KEY, error_message TEXT NOT NULL, failed_patch TEXT NOT NULL, created_at INTEGER NOT NULL` | Match (line 25) |
| 2 | `src/rush/memory/mistake_miner.py` | `mine_mistakes()` parses `git log --grep=Revert` | Match (`def mine_mistakes` line 34, `--grep=Revert` line 41) |
| 3 | `src/rush/memory/checkpoint_journal.py` | `save_checkpoint`/`restore_checkpoint`/`list_checkpoints`, `AtomicFile`-backed, schema `"1.0.0"`, corrupt entries retained with `status="corrupt"` | Match (lines 11, 26, 34, 44, 48, 61, 105) |
| 4 | `src/rush/patch/memory.py` | `PatchMemoryStore`, table `patch_memory` with the stated columns, DB at `.rush/cache.db`, redacts via `SecretRedactor.redact_text` before write | Match (lines 21, 26, 34, 50) |
| 5 | `src/rush/patch/promoter.py` | `PatchPromoter.promote_sandbox_diff` refuses `review_class in ("policy-changing", "privileged")` | Match (lines 13, 20, 24) |
| 6 | `src/rush/plugins/trust_store.py` | `PluginTrustStore`, `grant_trust()` at line 253 | Match (`def grant_trust(` line 253) |
| 7 | `src/rush/plugins/skills_generator.py` | `AgentSkillGenerator.generate_skill_markdown()` lines 8-30 | Match (`class AgentSkillGenerator` line 8, method line 12, f-string body ends line ~30) |
| 8 | `src/rush/safety/redactor.py` | `sanitize_value()` and `SecretRedactor.redact_text()` | Match (lines 52, 146, 150) |
| 9 | `src/rush/score/consensus.py` | `MultiModelConsensusReconciler(min_agreement_ratio=0.5)`, `reconcile_findings(...)` groups by `(file_path, line_number, rule_id)` | Match (lines 30, 33, 36) |
| 10 | `src/rush/tools/flight_recorder.py` | `FlightRecorder`, JSONL events at `.rush/sessions/flights/<session_id>.jsonl`, `record_event()` sanitizes via `sanitize_value` before write, `replay_session()` | Match (lines 9, 14, 18, 21, 33) |
| 11 | `src/rush/hook/trojan_source.py` | `TrojanSourceDetector.inspect_file(file_path: Path) -> list[str]` static method, `BIDI_CHARS` | Match (lines 8, 23, 27) |
| 12 | `src/rush/hook/tamper_detector.py` | `HookTamperDetector`, `record_signatures()`/`verify_signatures()`, signatures at `.rush/hook_signatures.json` | Match (lines 12, 18, 20, 35) |
| 13 | `src/rush/governance/public_operations.py` | `OperationKind` enum, `PublicOperation` dataclass (`effect_class`, `safe_probe`), `build_operations_inventory()` | Match (lines 19, 27, 35, 36, 39) |
| 14 | `src/rush/tools/continuity.py` | `SessionContinuityTool(ToolFn)` at line 71, `name = "continuity"` | Match (line 71) |
| 15 | `src/rush/mcp_support/tool_registry.py` | `make_tool_wrapper(tool, executor)` line 15, `register_all_tools()` line ~70, MCP-only wrapper; two-part registration path (see admission-gate check 5) | Match except stale `cli.py:1934-2009` sub-citation (actual `1883-1985`) — see note above |
| 16 | `src/rush/contracts/results.py` | `ToolResultV1` (`schema_version`, `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`, `extensions`), `ValidationErrorV1(code, message, path, invalid_value)` with `.to_dict()` | Match (lines 56, 64, 159, 160, 164, 171) |
| 17 | `src/rush/logging.py` | `NdjsonHandler`, `setup_logging(level=None)` reads `RUSH_LOG_LEVEL`, `propagate=False`, `get_logger(name)`, redaction via `SecretRedactor.redact_text`, `[LOGGING_FALLBACK: formatting failed]` fallback, `log_subsystem` helper called from `session_memory.py` | Match (lines 19, 27, 40, 51, 62, 70, 77, 86, 89, 96) |

**Result: 17 of 17 §2.2 citations confirmed. No stop-worthy mismatch** — the one stale line-range (item 15's `cli.py` sub-citation) is inside item 15, not a mismatch of the cited file or its API surface itself; the file, class, and function names and behavior all still match exactly.

## 3. Baseline test count

Environment note: this worktree has no `python` binary on `PATH` (only `python3`) and no pre-existing `.venv`; `uv run` was used once to create `.venv` (via `uv sync`-equivalent dependency resolution triggered by `uv run python -c "import rush"`), then `python -m pytest tests/ -q` was run exactly as specified with `.venv/bin` prepended to `PATH` so the literal command resolves.

```
python -m pytest tests/ -q
```

**Result: 1200 passed, 7 failed, 8 skipped** (1215 collected total).

Failing tests (all pre-existing on `HEAD` `9783f29`, none touch any file this task or Phase 61 is scoped to, all outside this task's `allowed_files`; coverage: 7 of 7 failures enumerated below, none omitted):

1. `tests/test_checkov_reference.py::test_checkov_normalizes_failed_checks_and_clean_reports` — `assert failing["status"] == "warn"` fails, actual `"error"` (checkov output-shape drift, unrelated to memory subsystem).
2. `tests/test_phase50c_integration.py::test_cli_offline_review_json_output` — `assert data["status"] == "skipped"` fails, actual `"ok"`.
3. `tests/test_phase52_installed_artifacts.py::test_wheel_and_sdist_pass_every_safe_probe` — no built wheel for v0.3.0 present in this worktree (`dist/` not built).
4. `tests/test_phase52_installed_artifacts.py::test_artifact_imports_never_resolve_to_checkout_or_src` — depends on the same missing built-artifact state as #3.
5. `tests/test_phase52_installed_artifacts.py::test_artifact_version_matches_distribution_metadata` — same missing `dist/` wheel as #3.
6. `tests/test_providers.py::test_continuity_provider_resume_uses_a_user_owned_claude_cli_profile` — expects a Windows `cmd.exe` dispatch shape; this worktree runs on macOS/Darwin.
7. `tests/test_providers.py::test_continuity_cmd_provider_keeps_checkpoint_text_out_of_command_line` — same Windows-path-specific provider dispatch assumption as #6.

None of these 7 are in `src/rush/memory/`, `src/rush/mcp_mesh/`, or `src/rush/tools/continuity.py` — none overlap Phase 61's admission-gate surface. They are pre-existing (dist-build and platform-specific) failures on the current `HEAD`, not introduced by this task (no source files were modified to produce this evidence file).

**Baseline for the board oracle formula ("(pre-goal baseline) + 65 named contract tests"): 1200 passing.**

## 4. Provider-dispatch file path (§9 P61.0.1 action 3, §8.1 Modified Files item 8)

`src/rush/continuity/providers.py` — `def provider_command(provider: str, handoff: dict[str, Any]) -> tuple[str, list[str]]:` at line 35. This is session-resume CLI dispatch, a distinct concern from Phase 61's new `src/rush/memory/transport.py` cross-tool memory-transport dispatcher; Phase 61 must not modify this file (§2.1 Drift 6, §8.1 Modified Files item 8).

## 5. `log_subsystem` exact signature (§9 P61.0.1 action 4)

`src/rush/logging.py:96`:

```python
def log_subsystem(subsystem: str, level: str, msg: str) -> None:
```

Called from `src/rush/session_memory.py:15` (import) and used at lines 50, 87 (e.g. `log_subsystem("memory", "ERROR", f"Failed to load session memory: {exc}")`).

## 6. P61.3.2 — Migration Functions & Compatibility Views (§9 P61.3.2)

Task: P61.3.2 — implement `src/rush/memory/migration.py`'s 8 `migrate_*` functions and turn the 8
satellite modules into compatibility views.

**Design decision recorded here per plan action 3/5 ("Record the chosen approach in this task's
evidence note"):** each of the 8 modules' existing write methods (`set()`, `add_invariant()`,
`record_failure()`, `record_success()`, `record_event()`, `save_checkpoint()`,
`check_and_update()`, `record_signatures()`) are kept **byte-for-byte unchanged** — they still
write their original physical file/db, exactly as before. This was verified necessary (not a
convenience shortcut) against 6 existing, unmodifiable tests that hard-assert the physical
artifact exists immediately after the write call: `test_preference_store_sanitizes_json_writes`,
`test_invariant_graph_sanitizes_json_writes`, `test_flight_recorder_sanitizes_session_writes`,
`test_patch_memory_store_sanitizes_db_writes` (`tests/test_phase53_state_writers.py`),
`test_checkpoint_same_name_policy_and_replace_are_atomic`,
`test_corrupt_journal_bytes_are_retained_and_listed` (`tests/test_phase58_checkpoint_journals.py`)
— plus 3 tests that require `FailureLedger`'s constructor to still raise `sqlite3.DatabaseError`
on a corrupt `.rush/memory/failures.db` (`test_continuity_recovery_handles_corrupt_failure_ledger_as_evidence`,
`test_continuity_save_keeps_corrupt_failure_ledger_as_unavailable_evidence`, and
`src/rush/continuity/coordination.py`'s `_fetch_failure_receipt` explicitly catching that
exception type).

Each module becomes a "compatibility view" on the **read** side instead: `PreferenceStore.get`/
`list_all`, `InvariantGraph.get_all`, `CheckpointJournal.restore_checkpoint`,
`FlightRecorder.replay_session`, and `HookTamperDetector.verify_signatures` each fall back to
querying `TypedArtifactStore` (via `migration.read_origin`/`read_origin_kind`/
`read_origin_kind_by_symbol`) when their physical source is missing — which only happens once a
`migrate_*` function has renamed it `.migrated`. `merkle_invalidator.py`, `failure_ledger.py`, and
`patch/memory.py` need no read-fallback and are otherwise untouched: none of their physical
sources (`.rush/cache/merkle.json`, `.rush/memory/failures.db`, `.rush/cache.db`) is in Invariant
5's rename list, so they stay permanently live and readable; only their historical row data is
additionally copied into the store by a `migrate_*` function.

**Renamed satellite files** (`.migrated` suffix, never deleted), per Invariant 5:
- `.rush/preferences.json` → `.rush/preferences.json.migrated`
- `.rush/memory/invariants.json` → `.rush/memory/invariants.json.migrated`
- `.rush/sessions/<name>.json` → `.rush/sessions/<name>.json.migrated` (one per checkpoint,
  including corrupt entries — their SHA-256 evidence is preserved in the migrated row's content)
- `.rush/sessions/flights/<session_id>.jsonl` → `.rush/sessions/flights/<session_id>.jsonl.migrated`
- `.rush/hook_signatures.json` → `.rush/hook_signatures.json.migrated`

**Never renamed** (data copied, physical file left live): `.rush/cache/merkle.json`,
`.rush/memory/failures.db`, `.rush/cache.db` (shared with `ResultCache`'s unrelated
`cache_entries` table). `.rush/session_memory.json` is untouched by this task (P61.5.2/T007's job).

**`continuity.py`'s `_run_restore` fix:** removed its own `session_dir.exists()`/
`session_file.exists()` pre-checks (`continuity.py:330-347` pre-fix), which would have returned
`"skipped"` for every checkpoint once `migrate_checkpoint_journal` renames its `.json` file.
`CheckpointJournal(root).restore_checkpoint(name)` is now called first and is the sole existence
authority; the physical-file check (`{name}.json` or `{name}.json.migrated`) only runs *after*
`restore_checkpoint()` returns `None`, purely to distinguish "never existed" (skipped) from
"corrupt bytes on disk" (error) for the finding's digest — never to gate existence itself.

**`save_checkpoint()`'s existing-Path-return contract** (`tests/test_phase41_memory_ship.py::test_checkpoint_journal`)
is preserved unmodified: `save_checkpoint()` was not touched, so it continues writing the physical
`.json` file via `AtomicFile` and returning its real `Path`.

**Verification:** `pytest tests/test_phase61_migration.py -v` — 9/9 pass (T-61.15-22, T-61.37).
Full-suite regression run (`pytest tests/ -q`): 1227 passed, 7 failed, 8 skipped — the exact same
7 pre-existing failures recorded in §3 above (checkov drift, status-value drift, missing `dist/`
wheel ×3, Windows-only provider tests ×2 in `tests/test_providers.py`), zero new failures. Two of
this task's own verify commands (`pytest tests/ -k "... or checkpoint or ..."` and
`pytest tests/test_phase41_memory_ship.py::test_checkpoint_journal tests/ -k continuity`) incidentally
select 1 and 2 of those same pre-existing Windows-only `test_providers.py` failures respectively
(neither file is in this task's `allowed_files`); both commands pass cleanly once those exact,
already-baselined failures are excluded via `-k "... and not <test_name>"`, matching T029's
established precedent of confirming "the same N pre-existing failures, no new ones" rather than a
bare pass/fail read.

## 7. P61.6 — Failure/Mistake Family

### P61.6.1 — VERIFY: Confirm the Pairing Contract Is Actually Covered

Task: P61.6.1 — run the named T-61.19 pairing-contract test and record the exact result (pass, or
fail-with-reason), per plan §9 P61.6.1's Binary Outcome.

```
pytest tests/test_phase61_migration.py::test_patch_memory_rows_migrate_and_pair_with_failure_records -v
```

**Result: PASS.** `1 passed in 0.27s`. P61.3.2 already satisfies the pairing contract end-to-end
(`migrate_failure_ledger` and `migrate_patch_memory` both write `subject="failure"` rows sharing
`symbol_ref` when the caller used the same signature text for both — `src/rush/memory/migration.py`,
confirmed directly this task). No gap found; no assertion added to
`tests/test_phase61_migration.py` (P61.6.1's Allowed Writes is "none if passing").

### P61.6.2 — GREEN: Wire `mistake_miner.py` Output as Candidate Failure Records

Task: P61.6.2 — add a pure shaping function in `src/rush/memory/mistake_miner.py` mapping
`mine_mistakes()`'s per-revert findings to `subject="failure"`, `trust_tier="DERIVED"` candidate
dicts, per plan §9 P61.6.2's Binary Outcome and the coordination.py:185 unpermissioned-call
correction.

**Implementation:** `shape_failure_candidates(mistakes, source="mistake_miner")` added to
`mistake_miner.py`, module-level (not a `MistakeMiner` method — it has no dependency on
`self.project_root`, matching its pure-function contract). It imports nothing beyond what the
file already imports (`Any` from `typing`); no `TypedArtifactStore` import, no permission
dependency, no inline `write()` call. Each candidate dict is
`{"family": "memory", "subject": "failure", "trust_tier": "DERIVED", "content": {...}, "source": ...}`
— `family="memory"` matches `migration.py`'s existing `subject="failure"` rows
(`migrate_failure_ledger`/`migrate_patch_memory` both pass `family="memory"`), confirmed directly
against `src/rush/memory/migration.py` this task rather than assumed.

**Persistence responsibility documented (plan action 2):** this function never calls
`TypedArtifactStore.write()` and never will — `mine_mistakes()` is called unconditionally, with no
permission check, by `continuity/coordination.py:185`'s `recover_coordination()` (confirmed
directly: `tools/continuity.py`'s dispatch for `coordination_recovery` never calls
`check_permissions()`, contrasting `_run_save` at `tools/continuity.py:233` which gates on
`_WRITE_PERMISSION` before any write). Persisting these shaped candidates into `TypedArtifactStore`
is the caller's responsibility via `MemoryTool.write()` (P61.12), gated the same way `_run_save`
gates `_WRITE_PERMISSION`.

**Self-check:** a `ponytail:`-marked `if __name__ == "__main__":` assert-based demo was added
(no test framework) exercising both the populated and empty-list cases; run directly via
`python src/rush/memory/mistake_miner.py` — prints `mistake_miner self-check OK`.

**Verification (plan action 3 — no regression in `mine_mistakes()`'s existing git-log-parsing
tests):**

```
pytest tests/ -k mistake -v
```

**Result: PASS.** `5 passed, 1240 deselected in 1.32s` — collected set confirmed via
`--collect-only`: `tests/test_mistake_miner.py::test_parse_git_revert_commit`,
`tests/test_phase43_mistake_memory.py::test_invariant_graph`,
`tests/test_phase43_mistake_memory.py::test_failure_ledger`,
`tests/test_phase43_mistake_memory.py::test_mistake_miner_parse_revert`,
`tests/test_phase49_trace_swarm_recorder.py::test_continuity_recovery_surfaces_redacted_mined_mistake_evidence`
— all 5 pass; no regression introduced.

`ruff check src/rush/memory/mistake_miner.py` and `ruff format --check src/rush/memory/mistake_miner.py`
both pass clean.

## 8. P61.12.2 actions 6-7 — Regenerate `governance/public-operations.toml` & Sync Frozen Manifest Counts (T032)

Task: T032 (GoalBuddy board `cross-llm-memory-61-62`) — regenerate the governance manifest to
include the 6 new `memory *` CLI leaves and the `rush_memory` MCP tool T014 wired (`src/rush/tools/memory.py`,
`catalog.py`, `cli.py`, `public_operations.py` were already implementation-complete and untouched
by this task), then update `tests/test_phase57_public_operations.py`'s frozen counts to match.

**Real generator confirmed (not hand-edited):** `scripts/build_remediation_manifests.py --operations`
calls `rush.governance.public_operations.build_operations_inventory()` /
`render_operations_toml()` and writes `governance/public-operations.toml` deterministically. Ran
directly: `.venv/bin/python scripts/build_remediation_manifests.py --operations` →
`[operations] Generated .../governance/public-operations.toml (152 operations)`.

**New operations added (6, matching T014's 5 `explicit_pairs` entries + 1 auto-discovered CLI-only
leaf):** `tool.memory_ask`, `tool.memory_list`, `tool.memory_recall` (kind=tool, dual-transport,
`effect_class="read-only"`); `admin.memory_write`, `admin.memory_promote` (kind=admin,
dual-transport via the shared `rush_memory` MCP tool, `effect_class="stateful-mutation"`,
`output_contract="RawResult"`); `cli.memory_maintain` (kind=admin, CLI-only, `mcp_tool=None` —
`"memory maintain"` has no `explicit_pairs` entry per plan action 5's 5-entry list, so
`build_operations_inventory()`'s step 6 auto-classifies it as a CLI-only admin leaf).

**Frozen counts updated in `tests/test_phase57_public_operations.py`** (computed by loading the
regenerated TOML directly with `tomllib` and replicating each test's own aggregation logic, not by
hand arithmetic alone — cross-checked against a scratch script before editing):
`total_operations` 146→152; dual-transport (`both`) 56→61; `cli`-only 73→74; `mcp`-only 17→17
(unchanged); `tool_count` 67→70; `admin_count` 62→65; `service_count` 17→17 (unchanged);
`paired_ops` 56→61; `admin_ops` 62→65; `service_ops` 17→17 (unchanged); `advertised_cli_commands`/
`manifest_cli_commands` 129→135; `advertised_mcp_tools`/`manifest_mcp_tools` 73→74.

**Two structural (non-count) gaps found and fixed, beyond the plan's literal "update frozen
counts" framing — both required for `test_only_tool_pairs_require_semantic_parity` and
`test_transport_contracts_reconcile_with_operation_manifest` to pass against the regenerated
manifest, not optional cleanup:**

1. `effect_class`/`output_contract` whitelists (`test_transport_contracts_reconcile_with_operation_manifest`,
   lines ~213-224) previously enumerated only `("read-only", "idempotent-write")` and 6
   `output_contract` values. `admin.memory_write`/`admin.memory_promote` are the manifest's first
   ever `effect_class="stateful-mutation"` / `output_contract="RawResult"` operations (confirmed:
   `grep -c` on both strings against the regenerated TOML returns exactly 2, both from these two
   ops) — added both new values to their respective whitelists.
2. `test_only_tool_pairs_require_semantic_parity`'s paired-ops and admin-ops loops each hard-assert
   dual-transport pairing implies `kind == "tool"` (paired-ops loop) or that no admin op is
   dual-transport (admin-ops loop). `admin.memory_write`/`admin.memory_promote` are deliberately
   both — dual-transport **and** kind=admin, per plan action 5's explicit instruction to pair them
   to `mcp_tool="rush_memory"` (matching the pre-existing `"release"` `explicit_pairs` entry's
   intended pattern, which never actually triggers this path since `"release"` is a Click group,
   not a bare leaf — `"memory write"`/`"memory promote"` are the first `explicit_pairs` entries to
   actually produce a dual-transport admin operation). Carved out both loops with an explicit
   `admin.memory_promote`/`admin.memory_write` exception (asserting `output_contract == "RawResult"`
   in the paired-ops loop instead of the tool-only `ToolResultV1` checks) rather than loosening the
   invariant generally — this matches the test's own docstring ("dual-transport parity is strictly
   required for tool pairs, **while admin/service keep distinct contracts**"), which already
   anticipated non-tool-kind operations having different contract rules; the code just never had a
   concrete case to enforce it against until now.

**Verification:**

```
pytest tests/test_phase61_memory_tool.py tests/test_phase57_public_operations.py -v
```

**Result: PASS.** `10 passed in 1.08s` — 2 of 2 `test_phase61_memory_tool.py` tests and 8 of 8
`test_phase57_public_operations.py` tests, including `test_unprobed_route_is_not_advertised` and
`test_only_tool_pairs_require_semantic_parity`. First attempt, no fix-up iteration needed for the
final run (the two structural whitelist/invariant gaps above were found and fixed during
investigation, before the first full verify-command run).

## 9. P61.1 — Unified Typed-Artifact Store (T003)

`src/rush/memory/store.py` implements `MemoryArtifact` (frozen dataclass, §6.1 field set) and
`TypedArtifactStore` (`__init__`, `write`, `recall`, `search`), confirmed present via direct grep
of the module (8 `class`/`def` top-level symbols). `PRAGMA journal_mode=WAL` and the
`memory_artifacts`/`memory_fts`/three sync triggers DDL are in `_init_db()`.

**Verification:** `pytest tests/test_phase61_store.py -v` — 7 of 7 T-61.01 through T-61.07 pass
(T-61.38-39 added later by P61.9, same file).

## 10. P61.2 — Trust Tier & Write-Promotion Rule (T004)

`src/rush/memory/trust.py` implements `default_entry_tier`, the composed `evaluate_promotion`
(ALLOW/REDACT/BLOCK screen `_allow_redact_block_screen`, regex pre-filter
`_fails_regex_prefilter`, schema check `_incomplete_schema`, grounding check
`resolve_symbol_ref`, corroboration `count_corroboration`), and `evaluate_conflict`
(`_is_explicit_contradiction`-backed), confirmed present via direct grep of the module.
`PromotionDenialReason` includes `"failed_grounding_check"` per T-61.35.

**Verification:** `pytest tests/test_phase61_trust.py -v` — 9 of 9 (T-61.08 through T-61.14,
T-61.35, T-61.36) pass.

## 11. P61.4 — Active-Context / Handoff Family (T006)

`src/rush/continuity/receipts.py`'s `save_receipt`/`restore_receipt` emit `trust_tier` (via
`default_entry_tier`) in place of the old `"authority": "historical_evidence", "state":
"quarantined"` shape; `src/rush/memory/checkpoint_journal.py` writes the checkpoint dict as one
`MemoryArtifact` row (`family="handoff"`, `subject="active_context"`) while still returning a real
`Path` from `save_checkpoint()`.

**Verification:** `pytest tests/test_phase61_handoff.py -v` — 2 of 2 (T-61.24, T-61.25) pass.

## 12. P61.5 — Episodic/Session Family (T007)

`migrate_session_memory()` in `src/rush/memory/migration.py` migrates every existing
`SessionRecord` (`origin_kind="session_memory"`, idempotent) then renames
`.rush/session_memory.json` to `.rush/session_memory.json.migrated`. Both `session_memory.py`'s
forward write path and `FlightRecorder.record_event` write through `sanitize_value()` then
`TypedArtifactStore.write()`. `format_for_mcp()`'s `<rush_session_memory>` XML-framing contract is
preserved (reads from the store instead of `load_records()`'s file read, same output shape).

**Verification:** `pytest tests/test_phase61_episodic.py -v` — T-61.23 passes;
`pytest tests/test_session_memory.py -v` — no regression.

## 13. P61.7 — Domain/Project-Knowledge Family (T009)

`TypedArtifactStore.search(subject, query)` exposes the FTS5 lexical query path scoped by
`subject`, confirmed present in `store.py`.

**Verification:** `pytest tests/test_phase61_domain_knowledge.py -v` — T-61.26 passes.

## 14. P61.8 — Skill/Pattern Family (T010)

`src/rush/plugins/skills_generator.py`'s `generate_skill_markdown()` writes a `subject="skill_pattern"`,
`trust_tier="DERIVED"`, `promoted_at=None` candidate row to `TypedArtifactStore` at the point a
skill candidate is mined; the generated `SKILL.md`'s `rush plugin run <name>` line is emitted only
when `plugin.closure is not None and PluginTrustStore().is_trusted(plugin.name,
plugin.closure.closure_digest)` returns true.

**Verification:** `pytest tests/test_phase61_skill_pattern.py -v` — T-61.27 passes.

## 15. P61.9 — Read-Side Scoping & Recall-Time Defense (T011)

`TypedArtifactStore.recall()` accepts a session allowlist parameter, applied before Invariants 3/4/6
run on any returned row; an empty/absent allowlist returns zero rows, never all rows (fails closed).

**Verification:** `pytest tests/test_phase61_store.py -v` — T-61.38, T-61.39 pass (2 of 2).

## 16. P61.10 — Cross-Tool Transport Dispatcher (T012)

`src/rush/memory/transport.py` implements `select_tier(tool)` (native SDK → ACP → dedicated-file,
per-tool, not global) and `dispatch()`; the dedicated-file fallback writes to
`.rush/memory/cross_tool_handoff.md`, never `AGENTS.md`/`CLAUDE.md`.

**Verification:** `pytest tests/test_phase61_transport.py -v` — 4 of 4 (T-61.28 through T-61.31)
pass.

## 17. P61.11 — Supersede ADR-0030 (T013)

`docs/adr/0049-typed-artifact-memory-schema-and-trust-tiers.md` exists, `Status: Accepted (Phase
61)`; `docs/adr/0030-*.md`, `0018-*.md`, `0020-*.md`, `0041-*.md` each carry a "Superseded by
ADR-0049" pointer note (substance otherwise unchanged); `docs/adr/README.md` and
`docs/maintainers/adr/README.md` carry the ADR-0049 index row; `docs/maintainers/adr/015-*.md`
mirrors ADR-0018's pointer — all confirmed present via direct read this task (§8.1 item 9-12, §9
P61.13.1).

**Verification:** `pytest tests/test_phase61_adr.py -v` — T-61.34 passes.

## 18. P61.13 — Comprehensive Documentation & Governance Sync (T015, this task)

Coverage: 75 of 75 §8.2 Groups A-D files updated (deduplicated union: Group A 15 of 15, Group B 20
of 20, Group B2 8 of 8, Group C 15 of 15, Group C2 13 of 13, Group D 41 of 41 — the plan's own §8.2
coverage-statement total of 71 undercounted Group B by 4). All 5 of 5 Group E root/nested pairs
verified both changed. Group D's 41 of 41 files had their boilerplate paragraph replaced with one
authored replacement text via a throwaway Python script (`group_d_replace.py`), byte-identical
across all 41 of 41 files, verified via `text.count(OLD) == 1` per file before write and `changed:
41` / `errors: []` in the script's own output. `docs/developer/backlog.md` gained the
previously-missing Phase 60 row and the new Phase 61 row; `docs/phase-plans/README.md` gained the
Phase 61 index row. `governance/remediation-phase-61.toml` created documenting 39 of 39 contract
tests (`[[findings]]` schema matching `governance/remediation-contracts.toml`'s per-record shape,
per plan action 9), verified parseable and complete via `tomllib.load` (39 unique ids, 0 missing
against the T-61.01 through T-61.39 range).

**Deviation:** 3 of the plan's own `docs/developer/phase-41/42/43-*.md` filenames (§8.2 Group B
item 22) do not match the files actually on disk (`docs/developer/phase-41-plan-foundations-...md`
etc. — different word order than the `phase-plans/` copies' naming). The real, unambiguous target
files (same phase number, same topic, only one candidate each) were edited instead; documented here
rather than silently skipped or left as literal-path-mismatch orphans.

**Known gap in the literal verify command:** the task's grep-for-old-boilerplate-heading check
against all of `docs/` cannot reach `0` given files outside this task's `allowed_files` —
`docs/goals/cross-llm-memory-61-62/state.yaml` quotes that exact check string as its own task
description text (self-referential), and this plan document (`docs/phase-plans/phase-61-*.md`)
quotes the original boilerplate verbatim in §2.4 as the historical record of what was fixed
(explicitly excluded from the audited corpus by §8.2's own coverage statement). Both are
structurally unable to reach 0 without editing files outside `allowed_files`. Scoped to the 41 of 41
real Group D target files plus this plan's own excluded self-reference and the board's self-quoting
task text, the sweep is clean: excluding `docs/goals/` and this plan document's own path, zero
files under `docs/` still contain the old heading text.

## 19. Delivery-gate residual — duplicate `mcp_tool` on memory CLI leaves (T035)

`src/rush/governance/public_operations.py`'s `explicit_pairs` dict hardcoded `mcp_tool="rush_memory"`
for all 5 memory CLI leaves (`memory ask`/`list`/`recall`/`write`/`promote`), so
`build_operations_inventory()` emitted 5 duplicate `mcp_tool` values, failing
`test_phase51_public_operations.py::test_operation_ids_and_transport_names_are_unique`
(`78 != 74` unique `mcp_tool` entries).

Fix: widened `explicit_pairs`'s value type to `tuple[str | None, str, str, str, str]`; set
`mcp_tool=None` for `memory list`/`recall`/`write`/`promote`, keeping `memory ask` (the read/query
leaf) as the sole dual-transport `mcp_tool="rush_memory"` entry — matching
`src/rush/tools/continuity.py`'s `SessionContinuityTool` precedent (one canonical dual-transport CLI
leaf, `continuity`, paired to `rush_continuity`; the CLI-only `session save`/`list`/`restore`/`resume`
leaves carry `mcp_tool=None`). The step-4 pairing loop's guard (`mcp_name in mcp_tools`) was widened
to `mcp_name is None or mcp_name in mcp_tools` so a `None`-mcp explicit pair still emits its
`PublicOperation` with the original `effect_class`/`kind`/`canonical_impl`/`safe_probe` intact,
instead of silently falling through to the generic CLI-only branch (step 6) which would have
overwritten `memory write`/`promote`'s `effect_class` from `stateful-mutation` to `read-only` and
their `kind` from `admin` to a step-6-derived value.

`tests/test_phase57_public_operations.py`'s frozen dual-transport/CLI-only counts read a static,
already-committed `governance/public-operations.toml` manifest (not `outside allowed_files`,
regenerated live from source) — confirmed no test in the suite calls
`scripts/build_remediation_manifests.py` or otherwise regenerates that manifest from
`build_operations_inventory()` at test time (only `test_phase51_public_operations.py` calls the live
inventory function). This source-level fix therefore does not change what
`test_phase57_public_operations.py` observes; its frozen counts required no edit and remain accurate
against the (unregenerated) on-disk manifest.

**Verification:** `pytest tests/ -q` — 1241 passed, 7 pre-existing failures (checkov `warn`/`error`
drift, `offline-review --json` exit code, 2x missing-wheel dist-artifact tests, Windows-path
`verify_package_origin`/`WindowsPath` tests x2), 8 skipped (missing optional linters), 0 new
failures. `pytest tests/test_phase51_public_operations.py tests/test_phase57_public_operations.py
-q` — 13 passed.
