# T012: Design gate for 75-T02/EVALUATOR (live-decision route, task manifest, budget)

A goal-judge wrote this read-only gate at `07775f1`. **Status: waiting for owner review (decision D2).** T043 (RED) does not start until the owner answers OD1-OD13 below.

## PM re-checks (run on 07775f1)

1. `.venv/bin/python scripts/benchmarks/run.py --help` raises `ImportError: attempted relative import with no known parent package` at `from .contracts import FixtureError, Outcome, ProbeResult`. The plan's literal command uses this form, so the checkpoint must fix it.
2. Grepping `.venv/bin/python -m scripts.benchmarks.run --help` for `--decision-mode` and `--task-manifest` finds 0 matches. Neither flag exists yet.
3. A case-insensitive grep of `src/rush/memory/verification.py:77-182` for `protect`, `editable`, `apply` and `subprocess` matches only the docstring, `PatchApplier.apply_patch_to_dir` (file line 132) and an apply-failure summary. There is no check-file protection, which supports B9.
4. `_UPLOAD_BUGGY` is a module constant at `scripts/benchmarks/memory.py:627`, outside `build_upload_repair_episode` (`:681`). It is written to `upload.py` at `:672`. This matters for OD12.

verified-by: the commands above. `grep -n "_UPLOAD_BUGGY\|def build_upload_repair_episode\|def _init_upload_repair_repo" scripts/benchmarks/memory.py` printed 627, 672, 663 and 681.

Not re-run by the PM:
- the gate's 52-passed baseline over the 7 benchmark test files;
- the route list in `provider_routes.json`;
- the graft caller map.

The T043 author re-checks the code map at task start (stop_if).

## 1. Checkpoint boundary

**Sources:**
- Phase 72 §3 line 100: "`72-T08` follows T01–T02 and narrow `75-T02/EVALUATOR` live-decision/budget checkpoint for benefit claims, before 75-T02 whole evaluation completion."
- Contract C08: "Phase 75-T02 repairs the existing benchmark runner's scripted-decision/completion-score/budget problems early; other phases consume that bounded component."
- 75-T02: "This early component is independently consumable by Phases 72–74."

**This checkpoint delivers these parts of the 75-T02 text:**
1. `--decision-mode component|live` (default `component`) and `--decision-route <existing route ID>`. Live mode needs an exact `--allow-live-route` grant and real executable support. Live mode without a grant is rejected.
2. `providers.py::run_memory_decision` for `openai-codex-oauth-cli-live` and `anthropic-claude-code-live`:
   - presence and fixture routes are invalid decision routes;
   - `run_provider_probe` is kept, and no `ProbeResult` is passed to `decide_fn`;
   - covers the schema-1 request, answer/action/submit mapping, strict kwargs and the fixture-owned `verify_attempt`.
3. The canonical case or episode root is validated inside the run's isolated workspace, and the decision runs with `cwd=root`. Includes both named containment tests.
4. The argv arrays, prompt capping, executable resolution and recording, Codex JSONL and Claude JSON parsing with every failure mode, and bounded, redacted output.
5. Harness completion is tracked separately from quality. Answers get a declared evaluator id and version. Episodes get real verifier and read-back outcomes.
6. `max_total_tokens` is enforced before and after each real call, with an output reserve:
   - exhausted, timed-out and failed cases stay in the denominator;
   - each request is counted once;
   - unknown usage is non-comparable, never zero;
   - the one-token/202-token regression becomes `budget_exhausted`;
   - F22 ("callback tool calls are not centrally counted") is fixed.
7. A strict `--task-manifest` with schema 1 and a frozen split, in `tests/fixtures/phase75/task_manifest.json`, seeded per OD2.
8. The named tests:
   - `test_live_mode_rejects_missing_route_grant`
   - `test_live_decider_receives_actual_history`
   - `test_dynamic_prompt_argv_and_result_usage`
   - `test_presence_route_cannot_decide`
   - `test_wrong_completed_answer_fails_quality`
   - `test_post_decision_budget_exhaustion`
   - `test_memory_cost_not_double_counted`
   - `test_decision_subprocess_uses_contained_fixture_cwd`
   - `test_source_aware_agent_patch_from_fixture`
9. Both `python scripts/benchmarks/run.py --help` and `python -m scripts.benchmarks.run --help` work and show the new flags.

**Stays with Phase 75, in the 75-T02 packet** (`phase-75-context-and-token-efficiency-plan.md:145-165`):
- the 10 remaining base families and all 11 variants;
- the declared 12-task live matrix;
- reuse curves, break-even and `test_reuse_break_even_counts_acquisition_and_maintenance`;
- single- and multi-agent arms, and the raw, fixed, AST and adaptive delivery arms;
- normalization into 75-T01 `TelemetryStore`. 75-T01 does not exist yet, so field names are chosen to migrate later.
- the Phase 75 PAS additions.

**Unchanged:**
- `src/rush/tools/benchmark.py`, which has no `scripts.benchmarks` import;
- `rush benchmark run` (`cli.py:374-412`, scenario-only).

## 2. Testable behavior

- **B1, flags.**
  - `--decision-mode {component,live}` defaults to `component`.
  - `--decision-route STR` and `--task-manifest PATH` default to None.
  - Both help forms list the three flags.
- **B2, validation.** Checks run before any spawn, ingestion or case. A failure raises `ValueError` in `run_memory_suite`; `main` then returns 1 and prints the message on stderr. The exact messages:
  - `--decision-route requires --decision-mode live`
  - `live decision mode requires --decision-route`
  - `decision route <id> is not a decision-capable route`
  - `live decision mode requires --allow-live-route <id>`
  - `live decision mode requires --task-manifest`
  - `provider-executable-not-found: <path or name>`
  - a FixtureError message
  - `--decision-mode/--task-manifest require --suite memory`, raised by `main`
- **B3, component mode without a manifest.** Behavior is unchanged: the 7-variant sweep, 5 episodes and `case_scores`. The run adds:
  - `"decision_mode":"component"`;
  - `per_variant[*].score_kind="harness_completion"`.

  The "real agent decision-making … was not exercised" blocker stays.
- **B4, dataset budget fix (all modes).**
  - `run_longmemeval_case` counts every `MemoryTool.run` call that `decide_fn` makes through the tool it was handed, as `len(cl100k(json.dumps(result, separators=(",",":"))))`.
  - After the decision, `total_tokens > max_total_tokens` means `budget_exhausted` with `prediction=None`.
  - The F22 repro (empty haystack, `"recalled context "*100`, max 1) must give `budget_exhausted`, 202 tokens and a score of 0.0.
- **B5, manifest mode.**
  - Only manifest cases run, once per seed.
  - `dataset_answer` cases use `--variant`; episodes ignore it.
  - Every case is counted in the denominator.
- **B6, live answers.**
  - The history is `[{"source":"variant_retrieval","variant":v,"text":<_variant_hypothesis output>}]`, or `[]`.
  - One call is made, and its `text` is the hypothesis.
  - The request never contains `answer`, `answer_session_ids`, `has_answer` or the gold string.
- **B7, live episodes.** Each step sends the real `EpisodeObservation.history` and maps the reply strictly to `EpisodeAction`. Scripted decide functions are never called in live mode.
- **B8, action strictness.**
  - The operation must be in `permitted_actions`.
  - kwargs must be a subset of `{subject, query, session_allowlist, content, source, symbol_ref, request}`.
  - Any of `permissions, path, owner_scope, user_stated, source_kind, include_archived, task, batch_size, candidate_sources`, or any unknown key, gives `decision_error: forbidden_kwarg` and no tool call.
- **B9, `verify_attempt` in live mode.**
  - The model may supply only `request.patch` (str) and `request.behavior_ids` (list[str]).
  - The runner injects everything else:
    - `base_commit` and `base_tree_digest` from the fixture repo;
    - the fixture-owned `required_commands`;
    - `patch_content_digest=sha256(patch)`, `config_digest="live-fixture-cfg-1"`, `review_class="standard"` and `attempt_id=f"live-attempt-{step}"`.
  - Every patch path must be in the episode's `editable_paths`; for upload-repair that is `["upload.py"]`.
  - Otherwise the result is `decision_error: patch_touches_protected_path`, and `verify_attempt` is not called (PM re-check 3).
- **B10, containment.**
  - A symlink root, an out-of-workspace root or a `..` escape gives `root_not_contained`, with no spawn.
  - A missing root gives `root_missing`.
  - Episodes use `cwd=root`. Answers use `cwd=root/"decision-cwd"`, created empty (OD6).
- **B11, argv.** No shell is used.
  - Codex: `[exe,"exec","--ephemeral","--json","--sandbox","read-only",prompt]`.
  - Claude: `[exe,"-p","--output-format","json","--max-turns","1","--permission-mode","plan",prompt]`.
  - Both go through `_cli_invocation`.
  - `--provider-executable` wins if `is_file()` (realpath). Otherwise `shutil.which(route.command[0])` is used.
  - One preflight `--version` call (10 s) is recorded, or `null` plus a reason.
- **B12, parsing.**
  - **Codex:**
    - Allowed event types: `thread.started, turn.started, item.started, item.updated, item.completed, turn.completed, turn.failed, error`. Any other type, or a non-JSON line, is `unsupported_event`.
    - `turn.failed` or `error` is `provider_error`.
    - Exactly one `item.completed` with `agent_message` is required. Zero, or no `turn.completed`, is `missing_final_message`; more than one is `ambiguous_final_message`.
    - Reasoning items are ignored. Other item types count as `tool_items`.
    - Usage comes from the final `turn.completed.usage`.
  - **Claude:**
    - Output is one JSON object with `type=="result"`.
    - `is_error`, or a subtype other than `success`, is `provider_error`.
    - A non-str `result` is `missing_final_message`.
    - The model is the single key in `modelUsage`, else `null`.
  - **Both:**
    - a nonzero exit is `nonzero_exit`, and exit 0 is never treated as success on its own;
    - `timeout`;
    - stdout over 1 MiB is `output_too_large`;
    - one optional ```` ```json ```` fence is stripped, then the text must be one JSON object with exact keys, or it is `malformed_decision` or `unknown_decision_field`;
    - an answer with `tool_items>0` is `decision_used_tools`.
- **B13, usage.**
  - Codex `input_tokens` already includes cached tokens.
  - Claude input is `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
  - Raw usage is kept.
  - Missing usage gives `status="unavailable"` and `usage_comparable=false`, charged by a local cl100k estimate (`"basis":"local_estimate_cl100k_base"`).
- **B14, live budget (a `DecisionBudget` per case).**
  - Before a call: if `prompt + reserve > max - used`, nothing spawns, and the case is `budget_exhausted` with `exhausted_at="pre_call"`.
  - After a call, the usage is charged. Going over the budget discards the decision with `exhausted_at="post_call"`.
  - Tool-result and ingestion tokens are recorded but not charged (OD3).
  - The effective budget is `min(--max-total-tokens, case budget)` (OD4).
- **B15, quality.**
  - Each case records `harness_completed` and `quality{evaluator,evaluator_version,passed}`.
  - `passed` is false for exhausted, timed-out and `decision_error` cases.
  - Evaluators (all v1):
    - `normalized_contains`: NFKC, casefold, whitespace collapse, then a non-empty substring match;
    - `normalized_exact`;
    - `verifier_receipt_completed`: outcome completed with the fixture-owned commands;
    - `receiver_readback_acknowledged`.
  - A wrong finished answer fails quality.
- **B16, report (`memory-suite-report.json`).**
  - **Top-level keys:**
    - `decision_mode`;
    - `decision_route`: null or `{route_id, protocol, executable_realpath, executable_version}`;
    - `task_manifest`: null or `{path, schema_version, manifest_id, cases_sha256, case_count, families, variants}`;
    - `runner_argv`, `seeds`, `seed_semantics`, `manifest_results`, `summary_by_seed`;
    - `phase75_family_coverage{declared, open, owner:"75-T02"}`;
    - `blockers`.
  - **Case records:** `case_id, family, variant, kind, seed, outcome, harness_completed, quality, budget{...}, usage_comparable, invocations[...], decision_error`.
  - **Invocations:**
    - fields: `invocation_id, step, route_id, argv_redacted, cwd, exit_code, duration_ms, model, usage{...}, local_prompt_tokens, local_response_tokens, tool_items, error`;
    - in `argv_redacted`, the prompt is replaced by `<prompt sha256=… chars=N>`;
    - stdout and stderr excerpts are redacted with `route.redaction_patterns` and capped at 4096.
  - The "not exercised" blocker is removed only after a real parsed decision.

## 3. Code and caller map (07775f1)

**`scripts/benchmarks/run.py`:**
- `build_parser` (77-173), called by `main`, `test_benchmark_runner.py::test_parser_options` and a cross-variant test.
- `_variant_hypothesis` (176-241).
- `_case_completion_score` (247-254), kept.
- `_run_variant_cases` (257-286).
- `run_memory_suite` (289-460).
- `main` (1359-1425), also reached from `cli.py:388` on the scenario path.
- Phase 70's `run_dashboard_user_journey` (725-1249) is not touched.

**`scripts/benchmarks/memory.py`:**
- the episode types (420-474);
- `_score_episode` (508-536);
- `run_memory_episode` (539-622);
- the upload-repair builders (663-736), the only users of `verify_attempt`;
- `EPISODE_BUILDERS` (1026-1032);
- `run_named_episode` (1034-1052).

**`scripts/benchmarks/memory_datasets.py`:**
- `CaseOutcome` and `DatasetCaseResult` (62-71);
- `run_longmemeval_case` (190-259), which does no budget check after the decision (around line 250);
- `aggregate_dataset_results` (262-271);
- `strip_longmemeval_gold` (120-153).

**`scripts/benchmarks/providers.py`:**
- `redact_text` (28-37);
- `_authorized_route_ids` (45-53);
- `_cli_invocation` (56-66);
- `run_provider_probe` (361-533), unchanged.

**`scripts/benchmarks/contracts.py`:** `RouteDescriptor` (67-77) and `require_exact_keys` (113).

**`scripts/benchmarks/fixtures.py`:**
- `load_provider_routes`, with exact keys;
- `fixture_path` (26-31), which is contained to `tests/fixtures/benchmarks`, so the manifest is loaded from an explicit CLI path.

**Fixtures:**
- `tests/fixtures/benchmarks/provider_routes.json` has 12 routes. The two decision routes are `oauth_cli`. The rest are not decision routes: `antigravity-cli-presence`, `zai-claude-code-live`, `antigravity-agy-oauth-cli-live`, `deepseek-openai-api-live` and every `*-fixture` route.
- `tests/fixtures/benchmarks/memory_datasets.json` has `lme-q-001` (`2023-05-10`) and `lme-q-002` (`db-widen-ids`).

**Reused:**
- `src/rush/io/physical_paths.py::PhysicalRoot.open_contained`;
- `src/rush/memory/verification.py:77-182`.

**Absent at HEAD:** `tests/test_phase75_live_evaluation.py` and `tests/fixtures/phase75/`.

## 4. Design

**4.1 Placement.**
- **`contracts.py`:** `DecisionUsage`, `DecisionBudget` (`admit`, `charge`), `DecisionBudgetExhausted(exhausted_at)`, `DecisionTimeout`, `DecisionFailed(code)`, and `RouteDescriptor.decision_protocol: str | None = None`.
- **`fixtures.py`:** accepts an optional `decision_protocol` in `{"codex-exec-jsonl","claude-print-json"}`.
- **`providers.py`:**
  - `DecisionRoute` (`route`, `protocol`, `executable`, `version`);
  - `resolve_decision_route(route_id, *, allow_live_route, provider_executable)`, which raises the B2 errors;
  - `build_decision_prompt`;
  - `DecisionInvocation`;
  - `run_memory_decision(request, *, decision_route, root, workspace_root, decision_kind, max_prompt_tokens) -> DecisionInvocation`. It never raises on a provider failure, and it does not spawn on a containment or `prompt_over_budget` error.
- **`memory_datasets.py`:**
  - `CaseOutcome` gains `"decision_error"`, and the aggregate counts it;
  - `run_longmemeval_case(..., budget_ledger=None)` adds a counting `MemoryTool` proxy, a check after the decision, and catches for the three exceptions.
- **`memory.py`:**
  - `run_memory_episode(..., budget_ledger=None)`;
  - `EpisodeResult` defaults `decision_error=None` and `invocations=()`;
  - registries `TASK_KINDS`, `EVALUATORS` and `EPISODE_LIVE_FIXTURES`;
  - `load_task_manifest`, `cases_digest`, `run_manifest_case`, `live_episode_decider` and `live_answer_decider`;
  - `_variant_hypothesis` is passed in as a callable, so `memory.py` never imports `run.py`.
- **`run.py`:**
  - the flags, `_validate_decision_args` and the manifest branch;
  - a script-form bootstrap: when `__package__` is empty, insert `Path(__file__).resolve().parents[2]` into `sys.path` and set `__package__="scripts.benchmarks"` before the relative imports.
- **Extension path for 72-T08:** dispatch goes through the registries, so 72-T08 extends behavior by editing only `memory.py` and the manifest.

**4.2 Request schema 1.**

```
{"schema_version":1,"decision_kind":"answer"|"episode","case_id","task","step","history":[…],
 "remaining_budget_tokens","requirements":[str],"allowed_operations":[{"operation","kwargs":[…]}],
 "response_schema":{…}}
```

- Answer requests: `allowed_operations=[]` and `response_schema={"answer":{"kind":"answer","text":"string"}}`.
- Episode requests: the response is `action` (`operation`, `kwargs`) or `submit` (`final`).
- The prompt is the preamble `"Rush memory benchmark decision. Reply with exactly one JSON object matching response_schema in REQUEST. Do not modify files.\nREQUEST:\n"` followed by `json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",",":"), default=str)`.

**4.3 Budget.** Covered by B4 and B14.

**4.4 Offline and live.**
- Component mode never spawns a process. Live mode never calls a scripted decider.
- Tests use only fake executables: a `#!{sys.executable}` script in `tmp_path` that emits canned Codex or Claude output and logs its cwd and argv.
- No test or verify command calls a real provider route.

**4.5 Containment.** In order:
1. reject if `is_symlink()`;
2. compute the path relative to the workspace;
3. pass it through `PhysicalRoot(workspace_root).open_contained`;
4. require `is_dir()`;
5. spawn.

All case roots live under the suite's `TemporaryDirectory("memory-suite-")`.

**4.6 Manifest schema 1** (`tests/fixtures/phase75/task_manifest.json`, exact keys at every level).

```
{"schema_version":1,"manifest_id":"phase75-task-manifest",
 "families":[{"id","origin"}],"variants":[{"id","origin"}],
 "freeze":{"split":"heldout","cases_sha256":"<sha256>"},
 "cases":[{"case_id","family","variant","kind":"dataset_answer"|"episode","split":"heldout",
   "inputs":{…},"fixture_revision","grants":{"cache_write","artifact_write","build"},
   "requirements":[str],"acceptance":{"evaluator","evaluator_version":1},
   "permitted_actions":[…],"budget":{"max_total_tokens","output_reserve_tokens","max_steps","timeout_s"}}]}
```

The loader rejects all of these before any call:
- unknown or missing keys, and duplicate `case_id`s;
- an unknown kind, family or variant;
- an evaluator that does not match its kind;
- invalid `permitted_actions` for the kind (`dataset_answer` must be exactly `["answer"]`);
- non-positive integers, or a reserve that is not below the budget;
- a missing record or episode;
- a `fixture_revision` mismatch. For datasets this is the section manifest sha256; for episodes it is `sha256(inspect.getsource(builder))` (OD12);
- a `cases_sha256` mismatch.

**Shipped cases (OD2).** All five use variant `base` and budget `{16000, 1024, 12, 600}`.

| case_id | family | kind | evaluator | permitted_actions |
|---|---|---|---|---|
| `lme-q-001` | `longmemeval_sample` | dataset_answer | `normalized_contains` | `["answer"]` |
| `lme-q-002` | `longmemeval_sample` | dataset_answer | `normalized_contains` | `["answer"]` |
| `upload-repair` | `bug_repair` | episode | `verifier_receipt_completed` | `["verify_attempt","submit"]` |
| `guest-handoff` | `agent_handoff` | episode | `receiver_readback_acknowledged` | `["write","handoff","receive","expand","submit"]` |
| `diagnosis-handoff` | `agent_handoff` | episode | `receiver_readback_acknowledged` | `["last_success_diagnose","write","handoff","receive","expand","submit"]` |

`csv-adaptation` and `payload-check-order` are left out, because their only acceptance today is "all statuses ok". `phase75_family_coverage.open` lists the other 10 Phase 75 families.

**4.7 How 72-T08 consumes this (T013, T046-T048).**
- New kinds and evaluators are added to the `memory.py` registries.
- Phase 72 families, variants and cases are appended without changing the 5 shipped cases.
- `cases_sha256` is refrozen before any observation.
- T048 writes to `docs/reports/phase-72-memory-eval/{current,hybrid}` (D1).

## 5. Cross-task conflicts

- **72-T08 (T013, T046-T049):**
  - It owns `memory.py` and the manifest after T044, so T044 must land before T046.
  - `_variant_hypothesis` drops the hybrid fallback status and reason. **Flag to T013:** either justify adding `run.py` to 72-T08's files, or route the status and reason through `memory.py`.
  - The `cases_sha256` refreeze is mandatory.
- **72-T01/T02** change recall eligibility. The new tests must not assert recall content strings.
- **Phase 70:** `run_dashboard_user_journey` is not touched.
- **75-T01:** migrates `invocations` later. The field names follow C06.
- **The rest of Phase 75** extends schema 1 and the registries; it does not redefine them.
- **Phase 73:** no file overlap.

## 6. Test matrix

RED failures come from ImportError or AttributeError on symbols that do not exist yet, imported inside test bodies, or from assertions on current behavior.

**New file `tests/test_phase75_live_evaluation.py`:**

| # | Test | Assertion | RED failure |
|---|---|---|---|
| 1 | `test_live_mode_rejects_missing_route_grant` | `main` returns 1 with the exact grant message and spawns nothing | Unknown flag gives SystemExit 2 |
| 2 | `test_live_decider_receives_actual_history` | Step-n history equals the first n raw tool results, with no gold answer or scripted patch | ImportError |
| 3 | `test_dynamic_prompt_argv_and_result_usage` | Exact argv (B11); the prompt embeds the request; usage is parsed (B13) | ImportError |
| 4 | `test_presence_route_cannot_decide` | ValueError for the presence, zai, fixture and api routes | ImportError |
| 5 | `test_wrong_completed_answer_fails_quality` | `harness_completed` is true, quality is false, evaluator is `normalized_contains`/1 | ImportError |
| 6 | `test_post_decision_budget_exhaustion` | `budget_exhausted` at `post_call`, and the case stays in the totals | ImportError |
| 7 | `test_memory_cost_not_double_counted` | `model_tokens_used` equals input plus output; tool tokens are local only; cached tokens are not added | ImportError |
| 8 | `test_decision_subprocess_uses_contained_fixture_cwd` | Episode cwd is the root; answer cwd is `root/decision-cwd` | ImportError |
| 9 | `test_source_aware_agent_patch_from_fixture` | A correct patch completes with the fixture commands; a timeout-only patch fails quality | ImportError |
| 10 | `test_runner_help_lists_decision_flags` | Both help forms exit 0 and list 3 flags | Flags absent / ImportError |
| 11 | `test_component_mode_is_default_and_labeled` | Component is the default, `score_kind` is set, and the blocker is kept | AttributeError/KeyError |
| 12 | `test_decision_route_requires_live_mode` | Exact message, exit code 1 | SystemExit 2 |
| 13 | `test_live_mode_requires_task_manifest` | Exact message, exit code 1 | SystemExit 2 |
| 14 | `test_live_mode_missing_executable_fails_before_spawn` | `provider-executable-not-found`, no spawn | SystemExit 2 |
| 15 | `test_task_manifest_rejects_invalid[unknown_top_key, unknown_case_key, missing_acceptance, duplicate_case_id, unknown_kind, undeclared_family, cases_digest_mismatch, fixture_revision_mismatch, action_not_permitted_for_kind, reserve_not_below_budget]` | FixtureError, and the decision spy is not called | ImportError |
| 16 | `test_shipped_task_manifest_is_frozen_and_exact` | Schema 1; the digest verifies; ids and families exactly as in §4.6 | File missing |
| 17 | `test_codex_output_failures_fail_case[no_agent_message, two_agent_messages, missing_turn_completed, unsupported_event, non_json_line, nonzero_exit, malformed_decision_json, unknown_decision_field]` | Exact error code; the case outcome is `decision_error` | ImportError |
| 18 | `test_claude_output_failures_fail_case[is_error_true, non_success_subtype, missing_result, non_json_stdout, nonzero_exit]` | Exact error codes | ImportError |
| 19 | `test_claude_result_usage_and_model` | Input is the sum of 3 fields; the model comes from `modelUsage`; raw usage is kept | ImportError |
| 20 | `test_decision_timeout_retained_in_denominator` | Outcome `timeout`, still counted | ImportError |
| 21 | `test_pre_call_budget_refuses_spawn` | `budget_exhausted` at `pre_call`; the fake executable writes no log | ImportError |
| 22 | `test_unavailable_usage_is_non_comparable` | Status unavailable, non-comparable, charged by the local estimate | ImportError |
| 23 | `test_action_decision_rejects_override_kwargs[permissions, path, owner_scope, user_stated, unknown_operation]` | `decision_error` and no tool event | ImportError |
| 24 | `test_verify_attempt_contract_is_fixture_owned[model_required_commands, patch_touches_check_file]` | `decision_error`, and `verify_attempt` is not called | ImportError |
| 25 | `test_answer_decision_tool_use_rejected` | `decision_used_tools` | ImportError |
| 26 | `test_report_redacts_prompt_and_credentials` | The prompt appears only as its sha; excerpts are redacted and at most 4096 characters | ImportError |
| 27 | `test_manifest_component_run_reports_every_case` | 5 cases × 2 seeds; B16 keys present; no sweep key | Flag absent |
| 28 | `test_decision_root_containment_rejects_before_spawn[symlink_escape, foreign_root, missing_root]` | `root_not_contained` or `root_missing`, no spawn | ImportError |

**Extensions to existing test files:**

| Test | Assertion | RED failure |
|---|---|---|
| `tests/test_benchmark_memory_datasets.py::test_callback_tool_calls_count_toward_case_budget` | Recall calls count toward the case budget | Recall is not counted |
| `tests/test_benchmark_memory_datasets.py::test_one_token_review_repro_is_budget_exhausted` | The F22 repro gives `budget_exhausted`, 202 tokens, score 0.0 and no prediction | The case is currently scored |
| `tests/test_benchmark_memory_agents.py::test_episode_budget_exhaustion_from_decider_stays_in_denominator` | An episode that exhausts its budget stays in the denominator | TypeError on `budget_ledger` |
| `tests/test_benchmark_memory_agents.py::test_episode_decision_error_fails_episode` | A decision error fails the episode | TypeError on `budget_ledger` |
| `tests/test_benchmark_providers.py::test_route_loader_accepts_decision_protocol_only_on_decision_routes` | `decision_protocol` is accepted only on the decision routes | Attribute missing |

## 7. Worker packages

The packages for T043 (RED) and T044 (implementation) are recorded in the T012 receipt in `state.yaml`. The PM copies them onto the cards after the owner reviews D2.

**T043 allowed_files:**
- `tests/test_phase75_live_evaluation.py`
- `tests/test_benchmark_memory_datasets.py`
- `tests/test_benchmark_memory_agents.py`
- `tests/test_benchmark_providers.py`

**T044 allowed_files:**
- `scripts/benchmarks/{run,memory,memory_datasets,providers,contracts,fixtures}.py`
- `tests/fixtures/benchmarks/provider_routes.json`
- `tests/fixtures/phase75/task_manifest.json`

## Owner decisions needed (D2)

- **OD1, boundary.** Approve §1 items 1-9 for this checkpoint. Everything else stays in the 75-T02 packet.
- **OD2, manifest seed.** Seed the manifest with the 5 cases that have real executors and independent acceptance. The other 10 Phase 75 families are reported open. The alternative is to author all 12 families and 11 variants in T044, which moves the 75-T02 corpus into Phase 72.
- **OD3, live budget.** The live budget counts provider model tokens only, once per call. Ingestion and tool tokens are reported separately.
- **OD4, case budget.** The effective case budget is `min(--max-total-tokens, case max_total_tokens)`.
- **OD5, manifest in live mode.** Live mode requires `--task-manifest`. With a manifest, only manifest cases run.
- **OD6, answer working directory.** Answer decisions run in an empty, contained `root/decision-cwd`, and any tool use in an answer fails the case. Episodes use `cwd=root`.
- **OD7, scoring.** The LongMemEval sample is scored with `normalized_contains` v1. This is not the official LongMemEval judge.
- **OD8, Codex parsing.** Parsing is strict: exactly one `agent_message`, any unknown event type fails, and one optional fence is stripped.
- **OD9, where `decision_protocol` lives.** The gate puts it in `provider_routes.json`. That requires editing `contracts.py` and `fixtures.py`, which are outside the 75-T02 §4 file list. The alternative is a constant in `providers.py`.
- **OD10, seeds.** In live mode, `--seeds` are repetition labels only. The provider CLIs take no sampling seed, and the report says so.
- **OD11, EVALUATOR live lane.** There is none: the first real-provider run is T048 (72-T08). Confirm this, or add an EVALUATOR live smoke task.
- **OD12, episode fixture revision.** An episode's `fixture_revision` is `sha256(inspect.getsource(builder))`. That hash input is the builder's source text only. `_UPLOAD_BUGGY` is a module constant defined outside `build_upload_repair_episode` (PM re-check 4), so editing it leaves the revision unchanged. Upgrade path: hash the files the builder writes.
- **OD13, patch paths.** The runner rejects any patch path outside `editable_paths` (PM re-check 3).

**Missing evidence:**
- No live route was executed, by design.
- The Codex `exec` JSONL event set in B12 was designed from the 75-T02 text. T048 must confirm it against a live run, or report the mismatch as a blocker.
