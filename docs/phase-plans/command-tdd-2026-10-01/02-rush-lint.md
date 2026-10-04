Implement Q02 full scope in rush-cli when implementation authorized.
Read AGENTS.md, docs/templates/task-block-template.md, README.md,
00-shared-foundation.md and exact audit/report first.

# Feature: Exact lint coverage baseline delta and bounded Ruff reproducer

Authorization: plan remediation only; production patches/tests below proposed,
unimplemented/unexecuted here. No commit/push/release.
Source revision: 66c6c799eaa5b6017776d659e9e0de2b4a8878a5.
Audit source c78e445ba1e575ca373e35840142cd627b055d6a only.
Binding audit docs/reports/cli-mcp-command-audit-2026-09-26.md, SHA256
8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Binding report docs/reports/command-tdd-2026-10-01-plan-remediation.md:
Q02, applicable X/M and C01–C29 (binding C overrides).
Current remediation scope: only this Plan02 Markdown file. Batch Q01–Q10
context remains binding; no other plan edit or next-plan execution authorized.
Provenance: GPT6.1 Sol/high authored bounded concrete packets; GPT6 Luna/high
independently reviews frozen Plan02. Coordinator integrates only this document.

Goal: exact selected-file lint coverage, comparable source/config-bound baseline
deltas and a permission-gated bounded Ruff reproducer with unchanged originals.

## Required behavior

1. Exact Ruff/ESLint/Globstar selected_targets vector, file once/root absent.
   None preserves legacy root+caller args; [] skips inside _run_engine_in_scope,
   retaining engine ledger. Ruff show_files gets same staged vector/config/cwd.
   Preserve _staged_invocation four-tuple; helper _stage_selected_targets maps
   through staging.substitute_arg, logical consumed paths preserved.
   Optional keyword introspection keeps nonparticipating Engine subclasses.
   Ruff format branch vector consumes files, None retains args[2:] (Q03-M2).
2. Aggregate through routing.aggregate_status and routing.aggregate_scope,
   preserving specialized lint counts/excluded-file evidence and factual roots.
   Canonical F2 child scopes use actual consumed-file evidence; assessed_paths
   lists only consumed selected logical paths. Supported inputs with every engine
   unavailable have coverage unavailable; no supported targets retain none.
   Engine ledger scopes retain their existing runtime schema unchanged;
   clean partial warns (D5 proposal), summary no findings in assessed files;
   partial: real skip reason. Findings summary N issue(s), count retained.
3. Malformed/non-list/invalid finding JSON => error; rc2 => error; rc1 empty
   => error; valid findings even rc0 --exit-zero retain exact warn/fail.
4. Contained baseline tool lint plus matching versions/config_digest.
   Engine identity provenance; source_digest finding.extensions, root-relative
   paths for baseline identity; assessed_paths retains absolute logical selected
   paths. Exact new/resolved/unchanged, full findings retained; incomplete
   JS/executable or Ruff extend config closure => delta unassessed.
5. Ruff minimizer unique rule@root-relative-posix-path:line; default trial budget
   12, proposed integer range 1..100 pending James approval. analysis_runs counts
   actual adapter deletion-trial executions; scratch_replay_runs counts initial replay. AST-invalid count separate, decorated full span.
   Scratch replay (one run, excluded from deletion budget) must reproduce same
   rule/message before trials; changed
   extend closure => unreproducible_in_scratch, never fake minimal.
   Complete deletion pass at exact budget => one_deletion_minimal, unfinished
   => budget_limited. Persistent .rush/lint-reproducers/<original-sha256-prefix16>/
   <root-relative-source-path>, exact source/
   rule/path/digests/config/counters, unchanged originals. Non-Ruff ESLint/
   Globstar always skipped/reason isolation_unavailable_for_non_ruff,
   analysis_runs=0, ordinary lint unchanged; no F4/F5 dependency.
   Cancellation/timeout stops reduction with no artifact, preserves ordinary lint
   status/findings/scope, records actual failed child as minimization.last_run,
   and copies actual execution evidence when present. Operation state is
   skipped/cancelled or error/timeout; no invented cause, launch or receipt.
## Phase70 reconciliation and shared contracts

Aligned inputs: revised Plan00 SHA256
12917ade4f88f4d508f2829f55033cb2498638398df7a41be49e519ad2e46275
and revised Plan01 SHA256
773fe54dc1f6d37151ac60f0ea0d2e44c23c99e9f9587c1ffcb21f91d0259caa.
These documents remain unchanged by this remediation. Plan02 consumes their
shared F1–F3/F6 contracts and Foundation ownership; F4/F5 remain reference-only.
Existing execution context, immutable staging snapshots and cancellation
controls remain intact. Hashes bind captured input bytes, never attest a
transient executable. Denied optional work records executed/not_run; cancellation
uses existing ambient cause/disposition and never fabricates completion.


Implementation base: phase/70-agent-adoption-and-usability at
66c6c799eaa5b6017776d659e9e0de2b4a8878a5. c78e445 is audit grounding only.
Phase70 T1–T29/G0–G8 acceptance is required before implementation; clean Git
or commit identity is not acceptance. Copy binding audit/plans byte-identically
or commit only under separate explicit authorization before packets start.

Foundation owner alone applies shared-file patch rows. F1 strict models use
wrapper public_sig, accept project/result_view/limit/max_bytes/no_cache/
allow_cache_write, publish flat properties/additionalProperties=false,
required=[path], no operation/schema_version. Strict MCP rejection:
isError=false, status=error, raw.error.code=INVALID_REQUEST, zero dispatch.
Public __call__ takes StrictBool allow_* and builds ExecutionPermissions once;
run receives permissions:ExecutionPermissions|None. Executor already binds
allow_* from context.permissions; no permission rewrite or config coercion.

metadata.engines records child engines; metadata.scope v1 records coverage.
Lint/format metadata.assessed_paths={engine:[paths]}, skipped child => [].
No new tool-owned metadata.children/metadata.partial/metadata.aggregation in
lint/format. Review existing aggregation retained; workflow children and
error_result terminal_reason/partial retained. aggregate_status governs:
report D5 proposal ok+skipped=warn, CLI exit 1; no local skipped override.
CLI exits ok/skipped=0, warn/fail=1, error=2. Invalid argument carrier:
metadata.error={code:invalid_argument,message:summary}. Pre-dispatch MCP uses
raw.error.code=INVALID_REQUEST instead.

Reference-only F4/F5 contracts below describe other batch consumers. Plan02
Ruff reduction calls the existing adapter in invocation-owned scratch, never
F4/F5; no runtime, image, live OCI or selected-test prerequisite. F6 real
CLI/stdio parity remains required for Plan02.

W18 = audit Command 45/79 rush_mem_profile isolation contract 13810–13889;
Foundation F4 implements provider under README D1. IsolatedRun has returncode,
stdout,stderr,process_launches,receipt. Signature:
run_isolated_argv(root,scratch,*,runtime_path,image_ref,entrypoint,argv,
timeout_s,workdir_rel=".",environment=None,max_process_launches=None,
scratch_on_pythonpath=False).
process_launches counts accepted host subprocess starts, including failed
runtime commands, not target execution attestation. LaunchBudgetExhausted and
IsolationUnavailable preserve factual process_launches and receipt evidence;
refused starts consume no launch. F4-START reserves before Popen, commits only
after successful host creation, aborts failed starts and returns exception receipts.
runtime_path absolute-only, never CLI abspath or _CWD_RELATIVE_ARGS.
F4 check_isolation_inputs(root,*,runtime_path,image_ref) launches nothing;
runtime errors raise IsolationUnavailable first, malformed image ValueError
second. D10 runtime proposal supplied docker/podman final name, symlink target
name irrelevant, resolved regular executable owned root/current user, no
group/world write, supplied directory and realpath outside root, POSIX.
Provider read-only source/private writable scratch, no network, capability/
privilege/resource/time/output bounds, owned cleanup and factual receipts.
Provider cancellation retains factual exception evidence; unconfirmed cleanup
raises OSError-compatible IsolatedCleanupError and is never isolation_unavailable.
No runtime byte hash is presented as proof of transient executable identity.
No host fallback. Missing runtime block skipped/reason isolation_unavailable
under unapproved D6 proposal, no fake successful isolation.

F5 run_selected_tests_isolated(root,scratch,*,nodes,runtime_path,image_ref,
python_entrypoint,timeout_s,max_process_launches=None,extra_pytest_args=(),
scratch_on_pythonpath=False) returns SelectedTestRun(outcome,counts,argv,
process_launches,isolated). pytest argv -m pytest -q --tb=line; outcomes
passed/failed/no_tests/error; counts passed/failed/skipped/error from final
summary, missing summary error. Nodes unique/nonempty/contained/no options/
NUL. F6 tests/transport_parity.py provides real CLI/stdio and real-file errlog;
never duplicate helper across command test files.

oci_isolation marker: unset RUSH_TEST_OCI_RUNTIME deselects, never skips.
Runtime set: every live test asserts own present/digest-pinned image. F4 CI
provisions Python/Rush/compiler images, exports all four variables, runs
pytest tests -m oci_isolation -q. Image owner README D11 unresolved. R/E
checks exclude provider-created modules until F4. Other consumers require live
OCI CI PASS; Q02-X1 has no OCI prerequisite.
ToolSpec.discovery single source in catalog, CLI help and MCP path schema;
mcp_description remains 20–199 chars with Phase70 phrases.

Shared requested baseline remains full scope: scanner provisioning, connected
specialist local models, selectable voice/live speech, 3D companion. Never
count these as command innovation.

## Decisions for James

Plan02 consumes unapproved D3 grant convention, D5 aggregate status and D8
mypy gate. Concrete packets use existing/new run(permissions), Phase70
ok+skipped=warn, and mypy src/rush as conditional proposals. James must ratify
or replace them before dependent implementation; update all affected packets,
assertions and documentation together. No lint-local skipped override permitted.

Audit fixes max_reduction_runs default at 12 and positive integer validation;
report Q02-14 proposes cap 100 with an explicit OWNER DECISION FLAG. Proposed
range 1..100 remains unapproved; this is the fourth Plan02 decision. Boolean,
zero and negative inputs are invalid under either choice. D1/D2/D4/D6/D7/D9/
D10/D11 isolation or Q01 choices are not prerequisites for Ruff-only Plan02.
D12 wider strict-model coverage belongs to Foundation and is tracked there.

## Deliverables

Command owner literal paths: src/rush/tools/lint.py;
src/rush/engines/ruff.py; src/rush/engines/eslint.py;
src/rush/engines/globstar.py; new tests/test_lint.py.
Q02-R1-runtime/scope-probe/staging Foundation rows:
src/rush/runtime/subprocesses.py exact optional selected-target forwarding/
empty guard/staged mapper below. Engine ABC unchanged; common.py re-export
unchanged. Q02-E1-options Foundation row: catalog_commands.py
_TOOL_CLI_OPTIONS lint exact options below; no generic generator/config rewrite.
Q02-parity Foundation tests/test_cli_registry.py/test_mcp.py use F6 once.
Q03-M2 Ruff format branch below applied by Q02 owner after R1.
Command ADR docs/adr/0052-lint-coverage-baseline-and-minimization.md.
Exact docs below Foundation F8 rows Q02-DOC-<subject>, including references,
CHANGELOG and coverage receipt. Historical bodies untouched.

## Constraints

Planning-only current authorization. No production/test/shared-doc writes,
commit/push/release/version/hook/install. Source and tests below proposed,
unimplemented/unexecuted here. Preserve unrelated user edits. Reuse adapters,
PhysicalRoot.open_contained (returns Path), atomic_write_bytes, grants/routing.
No invented API/model executable source/local isolation fallback/simulated PASS.
R/E/X each needs own evidence; repair PASS never closes extensions/expansion.

## Ordered tasks

1. Foundation F1/F2/F3/F6 first; Q02 selected-targets before Q03.
2. Named R/E RED bodies against Phase70, exact failure, minimum GREEN,
   same acceptance and affected regressions. Preserve memory/staging/contracts.
3. X1 after R1/E1, exact selector/config identity and bounded scratch-replay
   prerequisites defined in packets; Q02 Ruff-only has no OCI dependency.
4. Exact user docs and F8 receipt/contracts same packet, serialized Foundation.
5. Freeze final bytes; checks below; R/E/X reconciled separately.

## Concrete implementation packets

Every packet is proposed source/test/doc specification, not an applied patch.
Packet labels identify current corrective content. Shared targets are exact
Foundation patch-row content, applied only by Foundation. Final C overrides
control status, ownership and result carriers; earlier conflicting report
proposals are withdrawn explicitly in the acceptance ledger.

### Q02-01: Partial-engine status and child ledger conflict with Phase 70 S16.3

_assemble_lint_result retains aggregate_status/concat_engine_entries/lint_scope. Add _assessed_paths(child,engine_files): unassessed=>[], assessed=>actual consumed intersection with absolute logical selected vector. Thread engine_files and metadata["assessed_paths"]={c["engine"]:_assessed_paths(c,engine_files) for c in children} beside engines/scope. Clean partial summary after all-skipped branch: f"lint [{engine_str}]: no findings in assessed files; partial: " + "; ".join(skip_reasons); findings summary N issue(s) plus same partial suffix. Revised F2 and D5 govern canonical coverage/status, including clean partial promotion. Acceptance warn, scope partial, {ruff:[a.py],eslint:[]} under report proposal.


Concrete proposed `src/rush/tools/lint.py` change:
```python
from .routing import aggregate_scope, child_scope
from ..runtime.staging import StagingInputError, active_staging


def _lint_consumed_paths(child: ToolResult, targets: list[Path]) -> list[str]:
    metadata = child.get("metadata", {})
    scopes = [
        entry.get("scope", {})
        for entry in metadata.get("engines", [])
        if entry.get("engine") == child["engine"]
    ]
    reported = {
        os.path.abspath(path)
        for scope in scopes
        for path in scope.get("consumed_files", [])
    }
    for scope in scopes:
        if (
            "consumed_files" not in scope
            and scope.get("consumption_source") == "explicit_arguments"
            and scope.get("coverage") == "complete"
            and scope.get("consumed_file_count") == len(targets)
        ):
            reported.update(os.path.abspath(path) for path in targets)
    consumed = []
    staging = active_staging()
    for path in targets:
        alternatives = {os.path.abspath(path)}
        if staging is not None and reported:
            try:
                alternatives.add(os.path.abspath(staging.substitute_arg(str(path))))
            except StagingInputError:
                pass
        if alternatives & reported:
            consumed.append(str(path))
    return consumed


def _lint_child_scope(child: ToolResult, targets: list[Path]) -> dict[str, Any]:
    metadata = child.get("metadata", {})
    scopes = [
        entry.get("scope", {})
        for entry in metadata.get("engines", [])
        if entry.get("engine") == child["engine"]
    ]
    requested = [str(path) for path in targets]
    consumed = len(_lint_consumed_paths(child, targets))
    execution = metadata.get("execution", {})
    if not targets:
        coverage, reason = "none", "no_supported_targets"
    elif execution.get("disposition") in ("cancelled", "not_run"):
        coverage, reason = "none", execution.get("cause")
    elif child["status"] == "error":
        coverage, reason = "unavailable", "engine_error"
    elif any(scope.get("reason") == "engine_not_installed" for scope in scopes):
        coverage, reason = "unavailable", "engine_unavailable"
    elif child["status"] == "skipped":
        coverage = "none"
        reason = metadata.get("terminal_reason") or next(
            (scope["reason"] for scope in scopes if scope.get("reason")), None
        )
    elif consumed == len(targets):
        coverage, reason = "complete", None
    else:
        coverage, reason = "partial", "requested_files_not_consumed"
    return child_scope(
        coverage,
        reason=reason,
        requested_targets=requested,
        matched_file_count=len(targets),
        consumed_file_count=consumed,
    )


def _assessed_paths(
    child: ToolResult, engine_files: dict[str, list[Path]]
) -> list[str]:
    if child["status"] not in ("ok", "warn", "fail"):
        return []
    return _lint_consumed_paths(child, engine_files.get(child["engine"], []))
```
Add keyword-only `engine_files: dict[str, list[Path]] | None = None` to
`_assemble_lint_result`. At its start, before existing lint_scope/count/constructor:
```python
if engine_files is not None:
    for child in children:
        child.setdefault("metadata", {})["scope"] = _lint_child_scope(
            child, engine_files.get(child["engine"], [])
        )
```
This adds Foundation F2 child scope from actual reported consumption without
rewriting nested runtime ledger. Logical or staged selected spellings count
only when reported; missing consumption stays partial. Mapping None preserves
legacy direct assembler callers. After existing specialized scope construction,
before any return branch, merge canonical aggregate fields:
```python
if engine_files is not None:
    factual_scope = dict(scope or {})
    aggregated = aggregate_scope(children)
    if aggregated.get("logical_root") is None and factual_scope.get("logical_root"):
        aggregated["logical_root"] = factual_scope["logical_root"]
    scope = {**factual_scope, **aggregated}
    if scope["coverage"] == "unavailable":
        unavailable_reasons = [
            child["metadata"]["scope"]["reason"]
            for child in children
            if child["metadata"]["scope"]["coverage"] == "unavailable"
            and child["metadata"]["scope"].get("reason")
        ]
        if "engine_error" in unavailable_reasons:
            scope["reason"] = "engine_error"
        elif unavailable_reasons and set(unavailable_reasons) == {"engine_unavailable"}:
            scope["reason"] = "engine_unavailable"
        elif unavailable_reasons:
            scope["reason"] = unavailable_reasons[0]
```
Retain specialized requested/consumed counts and excluded_files. Canonical
aggregate coverage supersedes old report all-skipped none rule; preserve proven
specialized logical_root when aggregate has None. For non-probe explicit-file
adapters, only verified runtime explicit_arguments complete/count evidence
establishes consumed selected vector; Ruff uses actual reported consumed_files.
After `engine_str = "+".join(engines_used)`:
```python
    assessed_paths = {c["engine"]: _assessed_paths(c, engine_files or {}) for c in children}
```
Before existing all-skipped return, assign both
`result["metadata"]["scope"] = scope` and
`result["metadata"]["assessed_paths"] = assessed_paths`.
Replace existing `status = aggregate_status(children)` with:
```python
status = aggregate_status(children)
if status == "ok" and scope and scope.get("coverage") == "partial":
    status = "warn"
```
After existing `summary = (...)` and before normal ToolResult constructor:
```python
partial = any(c["status"] == "skipped" for c in children) or bool(
    scope and scope.get("coverage") == "partial"
)
clean_partial = (
    not n_findings
    and partial
    and any(c["status"] == "ok" for c in children)
    and all(c["status"] in ("ok", "skipped") for c in children)
)
if clean_partial:
    summary = f"lint [{engine_str}]: no findings in assessed files"
if partial and (n_findings or clean_partial):
    partial_reasons = list(skip_reasons or [])
    if not partial_reasons and scope:
        if scope.get("reason"):
            partial_reasons.append(scope["reason"])
        excluded = [entry["path"] for entry in scope.get("excluded_files", [])]
        if excluded:
            partial_reasons.append("excluded files: " + ", ".join(excluded))
    summary += "; partial: " + "; ".join(partial_reasons)
```
Normal metadata becomes
`{"engines": concat_engine_entries(children), "scope": scope,
"assessed_paths": assessed_paths}`. Pass `dispatched` mapping from
`LintTool.run`. Preserve `aggregate_status` and T13 deduplication. All-skipped
supported coverage is `unavailable/engine_unavailable`; unsupported empty
selection remains `none/no_supported_targets`. Canonical clean partial ok is
promoted to warn per revised F2. Assessed paths contain only actual consumed
selected logical paths, matching final C-01 assertion;
baseline finding keys separately use root-relative POSIX paths.
Checks after implementation: `test_selected_files_once_and_partial_engine` and
`test_partial_findings_summary_preserves_count`; exact warn/partial ledger and
F401 count plus skipped ESLint reason. Unexecuted here.
Also run proposed Q02-08 behavior checks after implementation:
```bash
env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_lint.py::test_lint_clean_show_files_omission_is_partial tests/test_lint.py::test_lint_missing_engines_vs_unsupported_scope tests/test_lint.py::test_lint_error_scope_retains_actual_engine_reason -q
```
Expected real clean Ruff main plus controlled probe omission: warn/partial,
actual consumed assessed_paths, exact excluded path/reason and summary. Supported
all-missing: skipped/unavailable; unsupported selection: skipped/none, with
zero launches and empty assessed paths. Real Ruff invalid-option error keeps
status error, unavailable/engine_error, actual child scope and whole runtime
ledger intact, assessed_paths ruff []; missing-only remains engine_unavailable.
Old report Q02-01 none/engine_unavailable
proposal is superseded by revised Foundation F2 for supported all-missing inputs.


Verification requirement: original report Q02-01 at line 2304; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-02: `selected_targets` design ignores the Phase 70 `run_engine` split and the scope probe

```
Base revision for implementation: phase/70 (66c6c79 or later), not c78e445 (see "Source revision"
line and ledger citations, updated to that revision).
`selected_targets: list[Path] | None = None` is a keyword-only parameter of
src/rush/runtime/subprocesses.py::run_engine, ::_run_engine_in_scope and ::_run_scope_probe, and of
RuffEngine.run, RuffEngine.show_files, EslintEngine.run and GlobstarEngine.run.
Forwarding: run_engine passes it to _run_engine_in_scope and to _run_scope_probe (run_engine, not
_run_engine_in_scope, calls the probe). Each applies Q02-03 staging substitution first, then
passes it to engine.run / show_files through the Q02-04 helper.
Semantics. None: every adapter keeps today's argv byte for byte (root operand plus caller args,
including caller-supplied operands; options-only calls retain the root; cwd preserved).
Non-empty vector: the operands are exactly that vector and the root operand is absent.
Empty vector: _run_engine_in_scope returns, before the PATH probe,
_skipped(tool_name, engine.name, "no selected targets", metadata={"execution":
build_execution_metadata("executed", requested=required_permissions, granted=permissions,
producer=engine.name)}) so run_engine still records its metadata.engines entry
(reason "engine_skipped") and nothing spawns.
Argv with a vector (operands = [str(p) for p in selected_targets]):
  RuffEngine.run check branch:  [bin, "check", "--output-format=json", "--no-cache", *operands, *args]
  RuffEngine.show_files:        [bin, "check", "--show-files", "--output-format=json", "--no-cache", *operands, *args]
  EslintEngine.run:             [bin, *operands, "--format=json", "--no-error-on-unmatched-pattern", *args]
  GlobstarEngine.run:           [bin, "check", "--format=json", *operands, *args]
Argv with None is unchanged: Ruff/show_files `... str(path), *args`; ESLint `[bin, str(path),
"--format=json", "--no-error-on-unmatched-pattern", *args]`; Globstar `[bin, "check",
"--format=json", *args, str(path)]`. RuffEngine's format branch keeps None legacy args[2:]; selected vector is Q03-M2 exact patch below.
src/rush/tools/lint.py::_run_selected_engines passes selected_targets=files (ruff, eslint) and
selected_targets=targets (globstar) with args=list(engine_args or []); consumed_paths unchanged.
Do not use args truthiness.
```
    - R1: `src/rush/tools/lint.py:82-137; src/rush/engines/ruff.py:35-98,102-129; src/rush/engines/eslint.py:49-56; src/rush/engines/globstar.py:29; src/rush/runtime/subprocesses.py:1258-1336,1533-1566,1569-1760`
    - R2: `src/rush/tools/lint.py:274-343`
    - R3: `src/rush/engines/ruff.py:165-181`
  - Add RED tests to tests/test_lint.py. Both run on a pytest `tmp_path` and currently fail with `TypeError … selected_targets`:
```python
def test_scope_probe_uses_selected_targets(tmp_path):
    import rush.engines.ruff as ruff_module
    from rush.runtime.subprocesses import run_engine

    a = tmp_path / "a.py"
    a.write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    real_run = ruff_module.run_subprocess
    argvs = []

    def spy(argv, **kw):
        argvs.append(list(argv))
        return real_run(argv, **kw)

    with patch("rush.engines.ruff.run_subprocess", side_effect=spy):
        result = run_engine(
            RuffEngine(),
            tmp_path,
            [],
            tool_name="lint",
            selected_targets=[a],
            consumed_paths=[str(a)],
            scope_probe=True,
        )
    main = [x for x in argvs if "check" in x and "--show-files" not in x]
    probe = [x for x in argvs if "--show-files" in x]
    assert len(main) == 1 and len(probe) == 1
    for argv in (main[0], probe[0]):
        assert argv.count(str(a)) == 1 and str(tmp_path) not in argv
    scope = result["metadata"]["engines"][0]["scope"]
    assert scope["consumed_files"] == [str(a)] and scope["consumed_file_count"] == 1


def test_empty_selected_targets_launches_nothing(tmp_path):
    from rush.runtime.subprocesses import run_engine

    def boom(argv, **kw):
        raise AssertionError(f"spawned {argv}")

    with patch("rush.engines.ruff.run_subprocess", side_effect=boom):
        result = run_engine(
            RuffEngine(), tmp_path, [], tool_name="lint", selected_targets=[]
        )
    assert result["status"] == "skipped"
    assert result["summary"] == "skipped: no selected targets"
    assert result["metadata"]["engines"][0]["reason"] == "engine_skipped"
```
Exact patch locations for Foundation `Q02-R1-runtime` row:
add `selected_targets: list[Path] | None = None` keyword-only to
`run_engine`, `_run_engine_in_scope`, `_run_scope_probe`.
Pass `selected_targets=selected_targets` in both `run_engine` calls:
`_run_engine_in_scope(...)` and `_run_scope_probe(...)`.
Immediately before existing `if not _engine_on_path(engine.binary):` in
`_run_engine_in_scope` (after permission refusal), insert:
```python
    if selected_targets == []:
        return _skipped(
            tool_name,
            engine.name,
            "no selected targets",
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_permissions,
                    granted=permissions,
                    producer=engine.name,
                    extra={"disposition": "not_run", "cause": "no_selected_targets"},
                )
            },
        )
```
This is an engine not-run result, not an executed assessment. `run_engine`
still attaches factual engine entry; PATH/version/main/probe never launch.

In `LintTool._run_selected_engines`, replace both generated argument vectors
with `args = list(engine_args or [])` / `globstar_args = list(engine_args or [])`.
Add `selected_targets=files` to Ruff/ESLint dispatch and
`selected_targets=targets` to Globstar dispatch; keep consumed_paths exactly.

In `RuffEngine.run/show_files`, `EslintEngine.run`, `GlobstarEngine.run`,
add keyword-only `selected_targets: list[Path] | None = None`.
Ruff ordinary branch replaces only `str(path),` with
`*([str(path)] if selected_targets is None else [str(p) for p in selected_targets]),`;
show_files and ESLint same. Globstar replaces argv assignment with:
```python
        argv = (
            [binary_path, *default_args, *args, str(path)]
            if selected_targets is None
            else [binary_path, *default_args, *map(str, selected_targets), *args]
        )
```
Q03-M2 patch owned by Q02 Ruff owner, after R1: in existing format-check argv,
define `format_operands` before format-branch argv assembly, then replace
`*args[2:],` with `*format_operands,`:
```python
format_operands = (
    args[2:]
    if selected_targets is None
    else [*(str(p) for p in selected_targets), *args[2:]]
)
```
Thus vector adds exact files once, None preserves legacy args[2:] byte-for-byte.
No change to abstract Engine.run or common.py re-export.
Concrete tests `test_options_only_adapter_retains_root` and
`test_ruff_format_selected_vector_and_legacy_args` below verify exact argv/cwd;
runtime tests above verify main/probe agreement and no-launch empty vector.


Verification requirement: original report Q02-02 at line 2370; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-03: `selected_targets` bypasses staged-path substitution

insert after the operand-rule paragraph from Q02-02:
```
Staging. Keep _staged_invocation's signature and 4-tuple return unchanged (tests unpack it). Add
src/rush/runtime/subprocesses.py::
  def _stage_selected_targets(staging: Any, selected_targets: list[Path] | None) -> list[Path] | None:
      if selected_targets is None or staging is None:
          return selected_targets
      return [Path(staging.substitute_arg(str(p))) for p in selected_targets]
and call it immediately after `staging, run_path, run_cwd, extra_args = _staged_invocation(...)` in
_run_engine_in_scope (inside the same try, so StagingInputError becomes the existing "staging input
rejected" error result) and in _run_scope_probe (inside its try; StagingInputError already returns
None). The result is what engine.run / show_files receive. Output remapping (_remap_paths,
map_staged_path) is unchanged.
```
  Add RED test (currently `TypeError … selected_targets`; GREEN asserts below):
```python
def test_selected_targets_are_staged(tmp_path):
    from rush.engines.staging import stage_inventory, staging_scope
    from rush.runtime.subprocesses import run_engine

    base = tmp_path.resolve()
    root = base / "project"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    staging = stage_inventory(root, base / "staged", ["a.py"])
    calls = []

    def capture(argv, **kw):
        calls.append(list(argv))
        return CompletedProcess(argv, 0, "[]", "")

    with (
        staging_scope(staging),
        patch("rush.engines.ruff.run_subprocess", side_effect=capture),
    ):
        run_engine(
            RuffEngine(),
            root,
            [],
            tool_name="lint",
            selected_targets=[root / "a.py"],
            consumed_paths=[str(root / "a.py")],
        )
    staged_a = str(staging.staged_root / "a.py")
    assert calls[0].count(staged_a) == 1
    assert str(root / "a.py") not in calls[0]
    assert str(staging.staged_root) not in calls[0]
```
Verification requirement: original report Q02-03 at line 2466; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-04: Engine protocol/forwarding for non-participating engines undefined

```
Do not change the abstract Engine.run signature (src/rush/engines/base.py is unchanged). Add
src/rush/runtime/subprocesses.py::
  def _selected_targets_kwargs(call: Any, owner: str, selected_targets: list[Path] | None) -> dict[str, Any]:
      if selected_targets is None:
          return {}
      if "selected_targets" not in inspect.signature(call).parameters:
          raise TypeError(f"{owner} does not accept selected_targets")
      return {"selected_targets": selected_targets}
and call engine.run(run_path, extra_args, cwd=run_cwd, **_engine_run_ownership(engine,
owner_instance_id, run_id), **_selected_targets_kwargs(engine.run, engine.name, staged_targets)); and
show_files(run_path, extra_args, cwd=run_cwd, **_selected_targets_kwargs(show_files, engine.name,
staged_targets)). A vector given to an engine that lacks the keyword is a programming error,
surfaced as the existing "engine crashed" error result; lint passes vectors only to ruff, eslint
and globstar.
```
  Add test:
```python
def test_selected_targets_unsupported_engine_is_error(tmp_path):
    from rush.runtime.subprocesses import run_engine

    class Legacy(RuffEngine):
        name = "legacy"

        def run(self, path, args, cwd=None, *, owner_instance_id=None, run_id=None):
            raise AssertionError("must not be called")

    with patch("rush.tools.common.engine_on_path", return_value=True):
        result = run_engine(
            Legacy(),
            tmp_path,
            [],
            tool_name="lint",
            selected_targets=[tmp_path / "a.py"],
        )
    assert result["status"] == "error" and result["summary"].startswith(
        "error: engine crashed"
    )
```
Verification requirement: original report Q02-04 at line 2516; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-05: Globstar root widening not addressed

in the R1 location cell add `src/rush/engines/globstar.py:29`. The Globstar argv is already specified in the Q02-02 operand block. Add tests to tests/test_lint.py (`CompletedProcess` and `patch` are imported at the top of the plan's test block). Both currently fail with `TypeError … selected_targets` except the `None` assertions, which already hold:
```python
def test_globstar_selected_targets_exclude_root(tmp_path):
    from rush.engines.globstar import GlobstarEngine

    a = tmp_path / "a.py"
    a.write_text("x = 1\n")
    calls = []

    def capture(argv, **kw):
        calls.append((list(argv), kw))
        return CompletedProcess(argv, 0, "[]", "")

    with (
        patch("rush.engines.globstar.resolve_binary", return_value="/bin/globstar"),
        patch("rush.engines.globstar.run_subprocess", side_effect=capture),
    ):
        GlobstarEngine().run(tmp_path, ["--x"], cwd=tmp_path, selected_targets=[a])
        GlobstarEngine().run(tmp_path, ["--x"], cwd=tmp_path)
    assert calls[0][0] == ["/bin/globstar", "check", "--format=json", str(a), "--x"]
    assert calls[1][0] == [
        "/bin/globstar",
        "check",
        "--format=json",
        "--x",
        str(tmp_path),
    ]
    assert calls[0][1]["cwd"] == tmp_path


def test_eslint_selected_targets_exclude_root(tmp_path):
    from rush.engines.eslint import EslintEngine

    b = tmp_path / "b.ts"
    b.write_text("export const y = 1;\n")
    calls = []

    def capture(argv, **kw):
        calls.append(list(argv))
        return CompletedProcess(argv, 0, "[]", "")

    with (
        patch("rush.engines.eslint.resolve_binary", return_value="/bin/eslint"),
        patch("rush.engines.eslint.run_subprocess", side_effect=capture),
    ):
        EslintEngine().run(
            tmp_path, ["--max-warnings", "0"], cwd=tmp_path, selected_targets=[b]
        )
        EslintEngine().run(tmp_path, ["--max-warnings", "0"], cwd=tmp_path)
    tail = ["--format=json", "--no-error-on-unmatched-pattern", "--max-warnings", "0"]
    assert calls[0] == ["/bin/eslint", str(b), *tail]
    assert calls[1] == ["/bin/eslint", str(tmp_path), *tail]
```
Verification requirement: original report Q02-05 at line 2556; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-06: Deviation from the audit's fix is not recorded

```
Recorded deviation from the audit's Q02 fix specification (AUDIT:1515, 1538-1549: "no new run_engine
argument", `*(args or [str(path)])`): that form drops the root operand for options-only direct calls
(args=["--select", "E402"]), cannot tell file operands from option values, and would fail the existing
direct-adapter reference tests (tests/test_ruff_reference.py and tests/test_eslint_reference.py assert
root plus caller operands). This plan therefore adds the explicit selected_targets keyword. Every audit
outcome is preserved: selected files once, no root operand, direct no-target fallback, project cwd.
```

Verification requirement: original report Q02-06 at line 2596; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-07: Missing RED body for the audit acceptance test; test-name drift

  - Add this body to the RED section:
```python
def test_selected_files_once_and_partial_engine(tmp_path, monkeypatch):
    import inspect

    import rush.engines.ruff as ruff_module
    import rush.tools.common as common
    import rush.tools.lint as lint_module

    real_assemble = lint_module._assemble_lint_result
    captured_children = []

    def assemble(*args, **kwargs):
        bound = inspect.signature(real_assemble).bind(*args, **kwargs)
        result = real_assemble(*args, **kwargs)
        captured_children.extend(bound.arguments["children"])
        return result

    monkeypatch.setattr(lint_module, "_assemble_lint_result", assemble)
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.ts").write_text("export const y = 1;\n")
    real_run = ruff_module.run_subprocess
    real_on_path = common.engine_on_path
    argvs = []

    def spy(argv, **kwargs):
        argvs.append(list(argv))
        return real_run(argv, **kwargs)

    def on_path(name):
        return False if name in ("eslint", "globstar") else real_on_path(name)

    monkeypatch.setattr(ruff_module, "run_subprocess", spy)
    monkeypatch.setattr(common, "engine_on_path", on_path)
    monkeypatch.setattr("rush.tools.lint.engine_on_path", on_path)
    result = LintTool().run(tmp_path)
    main = [a for a in argvs if "check" in a and "--show-files" not in a]
    probe = [a for a in argvs if "--show-files" in a]
    a_py = str(tmp_path / "a.py")
    assert len(main) == 1 and len(probe) == 1
    for argv in (main[0], probe[0]):
        assert argv.count(a_py) == 1
        assert str(tmp_path) not in argv
    assert result["status"] == "warn"
    metadata = result["metadata"]
    assert metadata["scope"]["coverage"] == "partial"
    assert {c["engine"]: c["status"] for c in metadata["engines"]} == {
        "ruff": "ok",
        "eslint": "skipped",
    }
    assert metadata["assessed_paths"] == {"ruff": [a_py], "eslint": []}
    assert len(captured_children) == 2
    child_scopes = {
        child["engine"]: child["metadata"]["scope"] for child in captured_children
    }
    assert child_scopes == {
        "ruff": {
            "version": 1,
            "kind": "files",
            "coverage": "complete",
            "reason": None,
            "requested_targets": [a_py],
            "matched_file_count": 1,
            "consumed_file_count": 1,
        },
        "eslint": {
            "version": 1,
            "kind": "files",
            "coverage": "unavailable",
            "reason": "engine_unavailable",
            "requested_targets": [str(tmp_path / "b.ts")],
            "matched_file_count": 1,
            "consumed_file_count": 0,
        },
    }
    ledger_scopes = {entry["engine"]: entry["scope"] for entry in metadata["engines"]}
    expected_ruff = {
        "requested_file_count": 1,
        "consumed_file_count": 1,
        "consumption_source": "engine_show_files",
        "consumed_files": [a_py],
        "configuration_files": [],
        "coverage": "complete",
        "reason": None,
    }
    expected_eslint = {
        "requested_file_count": 1,
        "consumption_source": "explicit_arguments",
        "consumed_file_count": 0,
        "coverage": "none",
        "reason": "engine_not_installed",
    }
    assert {key: ledger_scopes["ruff"][key] for key in expected_ruff} == expected_ruff
    assert {
        key: ledger_scopes["eslint"][key] for key in expected_eslint
    } == expected_eslint
    assert {e["engine"]: e["status"] for e in result["metadata"]["engines"]} == {
        "ruff": "ok",
        "eslint": "skipped",
    }
    assert result["metadata"]["scope"]["coverage"] == "partial"
    assert (
        result["summary"]
        == "lint [ruff+eslint]: no findings in assessed files; partial: eslint not on PATH (install: npm install -g eslint)"
    )
```
  - Add a plan note: "Tests that need the scope probe must delegate to the real `run_subprocess`; a pure fake disables it."


Proposed `tests/test_lint.py` imports (shared by all packet test bodies):
```python
import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from rush.engines.ruff import RuffEngine
from rush.permissions import ExecutionPermissions
from rush.tools.lint import LintTool
from transport_parity import run_cli, run_mcp


@pytest.fixture(autouse=True)
def deterministic_optional_backends(monkeypatch):
    import rush.tools.common as common

    original = common.engine_on_path

    def available(name):
        return False if name in ("eslint", "globstar") else original(name)

    monkeypatch.setattr(common, "engine_on_path", available)
    monkeypatch.setattr("rush.tools.lint.engine_on_path", available)


def test_options_only_adapter_retains_root(tmp_path):
    calls = []

    def capture(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return CompletedProcess(argv, 0, "[]", "")

    with (
        patch("rush.engines.ruff.resolve_binary", return_value="/bin/ruff"),
        patch("rush.engines.ruff.run_subprocess", side_effect=capture),
    ):
        RuffEngine().run(tmp_path, ["--select", "E402"], cwd=tmp_path)
    assert calls[0][0] == [
        "/bin/ruff",
        "check",
        "--output-format=json",
        "--no-cache",
        str(tmp_path),
        "--select",
        "E402",
    ]
    assert calls[0][1]["cwd"] == tmp_path


def test_ruff_format_selected_vector_and_legacy_args(tmp_path):
    selected = tmp_path / "a.py"
    calls = []

    def capture(argv, **kwargs):
        calls.append((list(argv), kwargs))
        return CompletedProcess(argv, 0, "", "")

    with (
        patch("rush.engines.ruff.resolve_binary", return_value="/bin/ruff"),
        patch("rush.engines.ruff.run_subprocess", side_effect=capture),
    ):
        engine = RuffEngine()
        engine.run(
            tmp_path,
            ["format", "--check", "--line-length", "99"],
            cwd=tmp_path,
            selected_targets=[selected],
        )
        engine.run(tmp_path, ["format", "--check", str(selected)], cwd=tmp_path)
    prefix = ["/bin/ruff", "format", "--check", "--output-format=json", "--no-cache"]
    assert calls[0][0] == [*prefix, str(selected), "--line-length", "99"]
    assert calls[1][0] == [*prefix, str(selected)]
    assert [entry[1]["cwd"] for entry in calls] == [tmp_path, tmp_path]


def test_lint_cli_stdio_options_and_denial(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    original = b"print(1)\nimport os\n"
    source.write_bytes(original)
    monkeypatch.setenv("PATH", str(Path(__import__("sys").executable).parent))
    exit_code, cli = run_cli("lint", source, ["--minimize-finding", "E402@a.py:2"])
    mcp = run_mcp("rush_lint", {"path": str(source), "minimize_finding": "E402@a.py:2"})
    assert exit_code == 1
    for result in (cli, mcp):
        assert result["status"] == "warn"
        assert [f["rule"] for f in result["findings"]] == ["E402"]
        operation = result["metadata"]["minimization"]
        assert operation["status"] == "denied"
        assert operation["reason"] == "build_or_slow_denied"
        assert operation["analysis_runs"] == operation["scratch_replay_runs"] == 0
        assert operation["execution"]["disposition"] == "not_run"
        assert operation["execution"]["cause"] == "permission_denied"
    for key in ("tool", "engine", "engine_version", "status", "summary", "findings"):
        assert cli[key] == mcp[key]
    assert cli["metadata"]["minimization"] == mcp["metadata"]["minimization"]
    assert source.read_bytes() == original
    assert not (tmp_path / ".rush").exists()
    invalid_exit, invalid_cli = run_cli("lint", source, ["--max-reduction-runs", "0"])
    invalid_mcp = run_mcp("rush_lint", {"path": str(source), "max_reduction_runs": 0})
    assert invalid_exit == 2
    for result in (invalid_cli, invalid_mcp):
        assert result["status"] == "error"
        assert result["metadata"]["error"]["code"] == "invalid_argument"
        assert result["metadata"]["error"]["message"] == result["summary"]
```
F6 prerequisite `tests/transport_parity.py` is Foundation-created, existing
real CLI / initialized stdio SDK / real-file errlog contract; command module
imports helper, never duplicates it. New test module requires real Ruff. Autouse
fixture suppresses optional engines only in this process; subprocess parity
fixture is Python-only, so optional Globstar if installed remains an environment
prerequisite: set child PATH to Rush runtime/OS-only PATH excluding optional
Globstar before parity launches, retaining Rush's Python/Ruff. Exact setup:
`monkeypatch.setenv("PATH", str(Path(__import__("sys").executable).parent))`.
No fake receipts/probe; main/probe tests delegate to real run_subprocess.


Verification requirement: original report Q02-07 at line 2616; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-08: Stated scenarios lack runnable bodies

add these bodies (with the Q02-07 `selected_files…`, Q02-03 staging, Q02-05 Globstar/ESLint and Q02-02 probe/empty bodies they complete the matrix). Names must appear in the tasks and in the Checks pytest node list.
```python
from rush.permissions import ExecutionPermissions


def test_ruff_output_shapes(tmp_path):
    finding = '[{"code":"F401","message":"`os` imported but unused","filename":"a.py","location":{"row":1,"column":8}}]'
    cases = [
        (0, "[{}]", "error"),
        (
            0,
            '[{"code":"F401","filename":"a.py","message":"fixture","location":"bad"}]',
            "error",
        ),
        (0, "[]", "ok"),
        (0, '{"a":1}', "error"),
        (0, "[{", "error"),
        (0, "[1]", "error"),
        (2, "", "error"),
        (1, "[]", "error"),
        (1, finding, "fail"),
        (0, finding, "fail"),
    ]
    engine = RuffEngine()
    for code, out, expected in cases:
        with (
            patch(
                "rush.engines.ruff.run_subprocess",
                return_value=CompletedProcess(
                    ["ruff"], code, out, "boom" if code == 2 else ""
                ),
            ),
            patch.object(engine, "_version_str", return_value="fixture"),
        ):
            result = engine.normalize(engine.run(tmp_path, []), tmp_path, "lint")
        assert result["status"] == expected, (code, out)


def test_baseline_rejections(tmp_path, tmp_path_factory):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    src = tmp_path / "a.py"
    src.write_text("import os\n")
    outside = tmp_path_factory.mktemp("outside") / "prior.json"
    outside.write_text('{"tool":"lint","findings":[]}')
    (tmp_path / "wrong.json").write_text('{"tool":"format","findings":[]}')
    (tmp_path / "bad.json").write_text("{")

    def boom(argv, **kw):
        raise AssertionError(f"engine spawned: {argv}")

    for baseline in (tmp_path / "wrong.json", tmp_path / "bad.json", outside):
        with patch("rush.engines.ruff.run_subprocess", side_effect=boom):
            r = LintTool().run(src, baseline_result_path=baseline)
        assert (
            r["status"] == "error"
            and r["metadata"]["error"]["code"] == "invalid_argument"
        )


def test_baseline_config_mismatch_is_error(tmp_path):
    cfg = tmp_path / "ruff.toml"
    cfg.write_text('lint.select = ["F401"]\n')
    src = tmp_path / "a.py"
    src.write_text("import os\n")
    before = LintTool().run(src)
    (tmp_path / "prior.json").write_text(json.dumps(before))
    cfg.write_text('lint.select = ["F401", "E402"]\n')
    r = LintTool().run(src, baseline_result_path=tmp_path / "prior.json")
    assert (
        r["status"] == "error" and r["metadata"]["error"]["code"] == "invalid_argument"
    )


def test_changed_digest_changes_identity(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    src = tmp_path / "a.py"
    src.write_text("import os\n")
    before = LintTool().run(src)
    (tmp_path / "p.json").write_text(json.dumps(before))
    src.write_text("import os\n\n")
    after = LintTool().run(src, baseline_result_path=tmp_path / "p.json")
    d = after["metadata"]["delta"]
    assert d["new"] == 1 and d["resolved"] == 1 and (d["unchanged"] == 0)
    assert (
        before["findings"][0]["extensions"]["source_digest"]
        != after["findings"][0]["extensions"]["source_digest"]
    )


def test_baseline_delta_unassessed_for_js_selection(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    (tmp_path / "a.py").write_text("import os\n")
    (tmp_path / "b.ts").write_text("export const y = 1;\n")
    (tmp_path / "prior.json").write_text('{"tool":"lint","findings":[]}')
    r = LintTool().run(tmp_path, baseline_result_path=tmp_path / "prior.json")
    assert r["metadata"]["delta"] == {
        "status": "unassessed",
        "reason": "imported_eslint_config_closure_unverified",
    }
    assert [f["rule"] for f in r["findings"]] == ["F401"]
    assert r["metadata"]["config_identity_complete"] is False


def test_minimize_invalid_and_denied(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    src = tmp_path / "a.py"
    src.write_bytes(b"print(1)\nimport os\n")
    grants = {
        "permissions": ExecutionPermissions(build=True, slow=True, artifact_write=True)
    }

    def boom(argv, **kw):
        raise AssertionError("engine spawned")

    with patch("rush.engines.ruff.run_subprocess", side_effect=boom):
        for kwargs in (
            {"max_reduction_runs": 0},
            {"max_reduction_runs": 101},
            {"minimize_finding": "not-an-id"},
        ):
            r = LintTool().run(
                src, **{"minimize_finding": "E402@a.py:2", **grants, **kwargs}
            )
            assert (
                r["status"] == "error"
                and r["metadata"]["error"]["code"] == "invalid_argument"
            ), kwargs
    r = LintTool().run(src, minimize_finding="E999@a.py:9", **grants)
    assert (
        r["status"] == "error" and r["metadata"]["error"]["code"] == "invalid_argument"
    )
    r = LintTool().run(src, minimize_finding="E402@a.py:2")
    denial = r["metadata"]["minimization"]
    assert denial["status"] == "denied"
    assert denial["reason"] == "build_or_slow_denied"
    assert denial["analysis_runs"] == denial["scratch_replay_runs"] == 0
    assert denial["missing_permissions"] == ["build", "slow", "artifact_write"]
    assert denial["execution"]["disposition"] == "not_run"
    assert denial["execution"]["cause"] == "permission_denied"
    assert [f["rule"] for f in r["findings"]] == ["E402"]
    assert not (tmp_path / ".rush").exists()


def test_minimize_budget_limited(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    src = tmp_path / "a.py"
    src.write_bytes(b"unused = 1\nprint(1)\nimport os\ntrailer = 2\n")
    r = LintTool().run(
        src,
        minimize_finding="E402@a.py:3",
        max_reduction_runs=2,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    m = r["metadata"]["minimization"]
    assert m["status"] == "budget_limited"
    assert (
        m["analysis_runs"] == 2
        and m["rejected_runs"] == 1
        and (m["invalid_trials"] == 0)
    )
    assert (
        Path(m["reproducer_path"]).read_bytes() == b"print(1)\nimport os\ntrailer = 2\n"
    )
    assert src.read_bytes() == b"unused = 1\nprint(1)\nimport os\ntrailer = 2\n"


def test_minimize_complete_pass_at_exact_budget_is_minimal(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    src = tmp_path / "a.py"
    src.write_bytes(b"unused = 1\nprint(1)\nimport os\ntrailer = 2\n")
    r = LintTool().run(
        src,
        minimize_finding="E402@a.py:3",
        max_reduction_runs=6,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    m = r["metadata"]["minimization"]
    assert m["status"] == "one_deletion_minimal" and m["analysis_runs"] == 6


def test_minimize_skips_syntactically_invalid_deletion(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    src = tmp_path / "a.py"
    original = b"x = 1; y = [\n    2]\nprint(1)\nimport os\n"
    src.write_bytes(original)
    r = LintTool().run(
        src,
        minimize_finding="E402@a.py:4",
        max_reduction_runs=12,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    m = r["metadata"]["minimization"]
    assert m["status"] == "one_deletion_minimal"
    assert (m["analysis_runs"], m["rejected_runs"], m["invalid_trials"]) == (3, 2, 1)
    assert Path(m["reproducer_path"]).read_bytes() == b"print(1)\nimport os\n"
    assert src.read_bytes() == original


def test_minimize_unreproducible_when_config_extends_outside_copy(tmp_path):
    (tmp_path / "base.toml").write_text('lint.select = ["E402"]\n')
    (tmp_path / "ruff.toml").write_text('extend = "base.toml"\n')
    src = tmp_path / "a.py"
    src.write_bytes(b"print(1)\nimport os\n")
    r = LintTool().run(
        src,
        minimize_finding="E402@a.py:2",
        max_reduction_runs=12,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    m = r["metadata"]["minimization"]
    assert m["status"] == "unreproducible_in_scratch" and m["analysis_runs"] == 0
    assert m["scratch_replay_runs"] == 1
    assert "reproducer_path" not in m and (not (tmp_path / ".rush").exists())
    assert [f["rule"] for f in r["findings"]] == ["E402"]


def test_eslint_minimization_isolation_unavailable(tmp_path, monkeypatch):
    import rush.tools.common as common
    from rush.engines.eslint import EslintEngine

    target = tmp_path / "b.ts"
    target.write_text("const x = 1;\n")
    eslint_json = json.dumps(
        [
            {
                "filePath": str(target),
                "messages": [
                    {
                        "ruleId": "no-unused-vars",
                        "severity": 2,
                        "line": 1,
                        "column": 7,
                        "message": "'x' is assigned a value but never used.",
                    }
                ],
            }
        ]
    )
    calls = []

    def fake_run(argv, **kw):
        calls.append(list(argv))
        return CompletedProcess(argv, 1, eslint_json, "")

    monkeypatch.setattr(common, "engine_on_path", lambda name: name == "eslint")
    monkeypatch.setattr("rush.tools.lint.engine_on_path", lambda name: False)
    monkeypatch.setattr("rush.engines.eslint.resolve_binary", lambda b: "/bin/eslint")
    monkeypatch.setattr("rush.engines.eslint.run_subprocess", fake_run)
    monkeypatch.setattr(EslintEngine, "version", lambda self, **kw: "9.0.0")
    r = LintTool().run(
        tmp_path,
        minimize_finding="no-unused-vars@b.ts:1",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert len(calls) == 1
    assert r["metadata"]["minimization"] == {
        "status": "skipped",
        "reason": "isolation_unavailable_for_non_ruff",
        "analysis_runs": 0,
    }
    assert [f["rule"] for f in r["findings"]] == ["no-unused-vars"]
```
Additional required bodies, appended to same proposed `tests/test_lint.py`:
```python
def test_malformed_output_is_error(tmp_path):
    engine = RuffEngine()
    with (
        patch(
            "rush.engines.ruff.run_subprocess",
            return_value=CompletedProcess(["ruff"], 0, "[{", ""),
        ),
        patch.object(engine, "_version_str", return_value="fixture"),
    ):
        result = engine.normalize(engine.run(tmp_path, []), tmp_path, "lint")
    assert result["status"] == "error"
    assert result["findings"] == []
    assert "unreadable" in result["summary"]


def test_baseline_delta_preserves_full_result(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    source = tmp_path / "a.py"
    source.write_text("import os\n")
    prior = LintTool().run(tmp_path)
    baseline = tmp_path / "prior.json"
    baseline.write_text(json.dumps(prior))
    baseline_bytes = baseline.read_bytes()
    source.write_text("import sys\n")
    current = LintTool().run(tmp_path, baseline_result_path="prior.json")
    assert current["metadata"]["delta"] == {"new": 1, "resolved": 1, "unchanged": 0}
    assert [f["rule"] for f in current["findings"]] == ["F401"]
    assert (
        prior["findings"][0]["extensions"]["source_digest"]
        != current["findings"][0]["extensions"]["source_digest"]
    )
    assert baseline.read_bytes() == baseline_bytes


def test_baseline_path_forms_and_symlink_rejection(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    source = tmp_path / "a.py"
    source.write_text("import os\n")
    baseline = tmp_path / "prior.json"
    baseline.write_text(json.dumps(LintTool().run(source)))
    for value in ("prior.json", baseline):
        result = LintTool().run(source, baseline_result_path=value)
        assert result["metadata"]["delta"] == {"new": 0, "resolved": 0, "unchanged": 1}
    link = tmp_path / "linked.json"
    link.symlink_to(baseline)
    with patch(
        "rush.engines.ruff.run_subprocess",
        side_effect=AssertionError("engine launched"),
    ):
        result = LintTool().run(source, baseline_result_path=link)
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "invalid_argument"


def test_baseline_extend_identity_changes(tmp_path):
    base = tmp_path / "base.toml"
    base.write_text('lint.select = ["F401"]\n')
    (tmp_path / "ruff.toml").write_text('extend = "base.toml"\n')
    source = tmp_path / "a.py"
    source.write_text("import os\n")
    prior = LintTool().run(source)
    (tmp_path / "prior.json").write_text(json.dumps(prior))
    base.write_text('lint.select = ["F401", "E402"]\n')
    current = LintTool().run(source)
    assert current["metadata"]["config_digest"] != prior["metadata"]["config_digest"]
    compared = LintTool().run(source, baseline_result_path="prior.json")
    assert compared["status"] == "error"
    assert compared["metadata"]["error"]["code"] == "invalid_argument"


@pytest.mark.parametrize("content", ['tool = "x"\n', '[tool]\nruff = "x"\n'])
def test_baseline_wrong_toml_table_shape_is_unassessed(tmp_path, content):
    config = tmp_path / "pyproject.toml"
    config.write_text("[tool.ruff]\n")
    source = tmp_path / "a.py"
    source.write_text("x = 1\n")
    # Real Ruff ignores malformed configuration; identity still examines bytes.
    ordinary = LintTool().run(source, engine_args=["--isolated"])
    assert ordinary["status"] == "ok"
    assert ordinary["findings"] == []
    assert ordinary["metadata"]["config_identity_complete"] is True
    baseline = tmp_path / "prior.json"
    baseline.write_text(json.dumps(ordinary))
    config.write_text(content)
    result = LintTool().run(
        source,
        engine_args=["--isolated"],
        baseline_result_path=baseline,
    )
    assert result["tool"] == "lint"
    assert result["status"] == "ok"
    assert result["findings"] == []
    assert result["summary"] == ordinary["summary"]
    assert result["metadata"]["config_identity_complete"] is False
    assert (
        result["metadata"]["config_identity_reason"] == "ruff_config_closure_unverified"
    )
    assert result["metadata"]["delta"] == {
        "status": "unassessed",
        "reason": "ruff_config_closure_unverified",
    }
    assert "error" not in result["metadata"]


def test_baseline_extend_cycle_escape_and_unreadable(tmp_path):
    source = tmp_path / "a.py"
    source.write_text("import os\n")
    config = tmp_path / "ruff.toml"
    for content in (
        'extend = "ruff.toml"\n',
        'extend = "../outside.toml"\n',
        'extend = "missing.toml"\n',
    ):
        config.write_text(content)
        result = LintTool().run(source)
        assert result["metadata"]["config_identity_complete"] is False
        assert (
            result["metadata"]["config_identity_reason"]
            == "ruff_config_closure_unverified"
        )


def test_minimize_decorated_span(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    original = b"@decorator\ndef f():\n    return 1\nprint(1)\nimport os\n"
    source.write_bytes(original)
    result = LintTool().run(
        source,
        minimize_finding="E402@a.py:5",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    receipt = result["metadata"]["minimization"]
    assert receipt["status"] == "one_deletion_minimal"
    assert (
        receipt["analysis_runs"],
        receipt["rejected_runs"],
        receipt["invalid_trials"],
        receipt["scratch_replay_runs"],
    ) == (3, 2, 0, 1)
    assert Path(receipt["reproducer_path"]).read_bytes() == b"print(1)\nimport os\n"
    assert source.read_bytes() == original


def test_minimize_artifact_retention_and_collision(tmp_path):
    config = tmp_path / "ruff.toml"
    config.write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    original = b"unused = 1\nprint(1)\nimport os\ntrailer = 2\n"
    source.write_bytes(original)
    kwargs = {
        "minimize_finding": "E402@a.py:3",
        "permissions": ExecutionPermissions(build=True, slow=True, artifact_write=True),
    }
    first = LintTool().run(source, **kwargs)
    artifact = Path(first["metadata"]["minimization"]["reproducer_path"])
    expected = (
        tmp_path
        / ".rush/lint-reproducers"
        / hashlib.sha256(original).hexdigest()[:16]
        / "a.py"
    )
    assert artifact == expected
    before_stat = artifact.stat().st_mtime_ns
    assert artifact.read_bytes() == b"print(1)\nimport os\n"
    assert (artifact.parent / "ruff.toml").read_bytes() == config.read_bytes()
    second = LintTool().run(source, **kwargs)
    assert second["metadata"]["minimization"]["reproducer_path"] == str(artifact)
    assert artifact.stat().st_mtime_ns == before_stat
    artifact.write_bytes(b"caller-owned different artifact\n")
    collision = LintTool().run(source, **kwargs)
    assert collision["status"] == "error"
    assert collision["metadata"]["error"]["code"] == "invalid_argument"
    assert artifact.read_bytes() == b"caller-owned different artifact\n"
    assert source.read_bytes() == original


@pytest.mark.parametrize("terminal", ["cancelled", "timeout"])
@pytest.mark.parametrize("stop_at", [1, 2], ids=["replay", "trial"])
def test_minimize_terminal_child_preserves_runtime_evidence(
    tmp_path, monkeypatch, terminal, stop_at
):
    from subprocess import TimeoutExpired

    import rush.tools.lint as lint_module
    from rush.runtime.subprocesses import SubprocessCancelled, cancel_scope

    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    original = b"unused = 1\nprint(1)\nimport os\n"
    source.write_bytes(original)
    permissions = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    ordinary = LintTool().run(source, permissions=permissions)
    assert ordinary["status"] == "warn"
    real = lint_module.run_engine
    children = []
    scratch_calls = 0

    def dispatch(engine, path, *args, **kwargs):
        nonlocal scratch_calls
        if kwargs.get("cwd") is not None:
            scratch_calls += 1
            if scratch_calls == stop_at:
                failure = (
                    SubprocessCancelled(["ruff"], pid=0)
                    if terminal == "cancelled"
                    else TimeoutExpired(["ruff"], 120)
                )
                with patch("rush.engines.ruff.run_subprocess", side_effect=failure):
                    child = real(engine, path, *args, **kwargs)
                children.append(child)
                return child
        return real(engine, path, *args, **kwargs)

    monkeypatch.setattr(lint_module, "run_engine", dispatch)
    with cancel_scope(lambda: False, cause="fixture_cancelled") as scope:
        result = LintTool().run(
            source,
            minimize_finding="E402@a.py:3",
            permissions=permissions,
        )
        assert scope.hit is (terminal == "cancelled")
    assert len(children) == 1
    child = children[0]
    receipt = result["metadata"]["minimization"]
    assert receipt["status"] == ("skipped" if terminal == "cancelled" else "error")
    assert receipt["reason"] == terminal
    assert receipt["last_run"] is child
    assert result["metadata"]["execution"] == child["metadata"]["execution"]
    if terminal == "cancelled":
        assert child["status"] == "skipped"
        assert child["metadata"]["execution"]["disposition"] == "cancelled"
        assert child["metadata"]["execution"]["cause"] == "fixture_cancelled"
    else:
        assert child["status"] == "error"
        assert child["metadata"]["terminal_reason"] == "timeout"
        assert child["metadata"]["partial"] is False
    assert result["status"] == ordinary["status"]
    assert result["findings"] == ordinary["findings"]
    assert (
        result["metadata"]["analysis_scope"] == ordinary["metadata"]["analysis_scope"]
    )
    assert (receipt["analysis_runs"], receipt["scratch_replay_runs"]) == (
        stop_at - 1,
        1,
    )
    assert child["summary"] in result["summary"]
    assert source.read_bytes() == original
    assert not (tmp_path / ".rush").exists()


def test_minimize_trial_error_retains_original(tmp_path, monkeypatch):
    import rush.tools.lint as lint_module

    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    original = b"unused = 1\nprint(1)\nimport os\n"
    source.write_bytes(original)
    real = lint_module.run_engine
    scratch_calls = []

    def dispatch(engine, path, *args, **kwargs):
        if kwargs.get("cwd") is not None:
            scratch_calls.append(path)
            if len(scratch_calls) == 2:
                with patch(
                    "rush.engines.ruff.run_subprocess",
                    return_value=CompletedProcess(
                        ["ruff"], 2, "", "fixture config error"
                    ),
                ):
                    return real(engine, path, *args, **kwargs)
        return real(engine, path, *args, **kwargs)

    monkeypatch.setattr(lint_module, "run_engine", dispatch)
    result = LintTool().run(
        source,
        minimize_finding="E402@a.py:3",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    receipt = result["metadata"]["minimization"]
    assert receipt["status"] == "unreproducible_in_scratch"
    assert (receipt["analysis_runs"], receipt["scratch_replay_runs"]) == (1, 1)
    assert "fixture config error" in receipt["error"]
    assert receipt["failed_child"]["status"] == "error"
    assert receipt["failed_child"]["summary"] == receipt["error"]
    assert source.read_bytes() == original
    assert not (tmp_path / ".rush").exists()


def test_minimize_source_drift_rejected(tmp_path, monkeypatch):
    import rush.tools.lint as lint_module

    (tmp_path / "ruff.toml").write_text('lint.select = ["E402"]\n')
    source = tmp_path / "a.py"
    source.write_bytes(b"print(1)\nimport os\n")
    real = lint_module.run_engine

    def dispatch(engine, path, *args, **kwargs):
        if kwargs.get("cwd") is not None:
            source.write_bytes(b"caller changed source\n")
        return real(engine, path, *args, **kwargs)

    monkeypatch.setattr(lint_module, "run_engine", dispatch)
    result = LintTool().run(
        source,
        minimize_finding="E402@a.py:2",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "invalid_argument"
    assert source.read_bytes() == b"caller changed source\n"
    assert not (tmp_path / ".rush").exists()


def test_minimize_selector_ambiguity(tmp_path):
    from rush.tools.lint import _select_lint_finding

    findings = [
        {
            "path": str(tmp_path / "one/a.py"),
            "rule": "E402",
            "line": 2,
            "column": 1,
            "message": "fixture",
        },
        {
            "path": str(tmp_path / "two/a.py"),
            "rule": "E402",
            "line": 2,
            "column": 1,
            "message": "fixture",
        },
    ]
    result = {"findings": findings}
    with pytest.raises(ValueError, match="ambiguous finding basename"):
        _select_lint_finding(result, tmp_path, ("E402", "a.py", 2))
    assert (
        _select_lint_finding(result, tmp_path, ("E402", "one/a.py", 2)) is findings[0]
    )
    result["findings"] = [findings[0], {**findings[0], "column": 3}]
    with pytest.raises(ValueError, match="ambiguous finding"):
        _select_lint_finding(result, tmp_path, ("E402", "one/a.py", 2))


def test_lint_error_scope_retains_actual_engine_reason(tmp_path, monkeypatch):
    import inspect
    from copy import deepcopy

    import rush.tools.lint as lint_module

    source = tmp_path / "a.py"
    source.write_text("x = 1\n")
    real_assemble = lint_module._assemble_lint_result
    captured = []
    ledger_before = []

    def assemble(*args, **kwargs):
        bound = inspect.signature(real_assemble).bind(*args, **kwargs)
        children = bound.arguments["children"]
        ledger_before.extend(
            deepcopy(entry)
            for child in children
            for entry in child["metadata"]["engines"]
        )
        result = real_assemble(*args, **kwargs)
        captured.extend(children)
        return result

    monkeypatch.setattr(lint_module, "_assemble_lint_result", assemble)
    result = LintTool().run(source, engine_args=["--definitely-not-a-ruff-option"])
    assert result["status"] == "error"
    assert result["findings"] == []
    assert result["metadata"]["scope"]["coverage"] == "unavailable"
    assert result["metadata"]["scope"]["reason"] == "engine_error"
    assert result["metadata"]["assessed_paths"] == {"ruff": []}
    assert len(captured) == 1
    assert captured[0]["status"] == "error"
    assert captured[0]["metadata"]["scope"]["coverage"] == "unavailable"
    assert captured[0]["metadata"]["scope"]["reason"] == "engine_error"
    assert result["metadata"]["engines"] == ledger_before
    assert captured[0]["metadata"]["engines"] == ledger_before


def test_lint_clean_show_files_omission_is_partial(tmp_path, monkeypatch):
    import inspect

    import rush.engines.ruff as ruff_module
    import rush.tools.lint as lint_module

    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    real_run = ruff_module.run_subprocess
    real_assemble = lint_module._assemble_lint_result
    captured = []
    main_results = []

    def subprocess_spy(argv, **kwargs):
        if "--show-files" in argv:
            return CompletedProcess(argv, 0, str(a) + "\n", "")
        result = real_run(argv, **kwargs)
        if "check" in argv:
            main_results.append(result)
        return result

    def assemble(*args, **kwargs):
        bound = inspect.signature(real_assemble).bind(*args, **kwargs)
        result = real_assemble(*args, **kwargs)
        captured.extend(bound.arguments["children"])
        return result

    monkeypatch.setattr(ruff_module, "run_subprocess", subprocess_spy)
    monkeypatch.setattr(lint_module, "_assemble_lint_result", assemble)
    result = LintTool().run(tmp_path)
    assert len(main_results) == 1
    assert main_results[0].returncode == 0
    assert result["status"] == "warn"
    assert result["findings"] == []
    assert result["metadata"]["scope"]["coverage"] == "partial"
    assert result["metadata"]["scope"]["reason"] == "requested_files_not_consumed"
    assert result["metadata"]["scope"]["excluded_files"] == [
        {"path": str(b), "reason": "engine_excluded"}
    ]
    assert result["metadata"]["assessed_paths"] == {"ruff": [str(a)]}
    assert len(captured) == 1
    assert captured[0]["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "partial",
        "reason": "requested_files_not_consumed",
        "requested_targets": [str(a), str(b)],
        "matched_file_count": 2,
        "consumed_file_count": 1,
    }
    assert result["summary"] == (
        "lint [ruff]: no findings in assessed files; partial: "
        "requested_files_not_consumed; excluded files: " + str(b)
    )


def test_lint_missing_engines_vs_unsupported_scope(tmp_path, monkeypatch):
    monkeypatch.setattr("rush.tools.lint.engine_on_path", lambda name: False)
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda name: False)
    supported = tmp_path / "a.py"
    supported.write_text("x = 1\n")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("plain text\n")
    with patch(
        "rush.engines.ruff.run_subprocess",
        side_effect=AssertionError("missing engine must not launch"),
    ):
        missing = LintTool().run(supported)
        empty = LintTool().run(unsupported)
    assert missing["status"] == "skipped"
    assert missing["findings"] == []
    assert missing["metadata"]["scope"]["coverage"] == "unavailable"
    assert missing["metadata"]["scope"]["reason"] == "engine_unavailable"
    assert missing["metadata"]["assessed_paths"] == {"ruff": []}
    assert empty["status"] == "skipped"
    assert empty["findings"] == []
    assert empty["metadata"]["scope"]["coverage"] == "none"
    assert empty["metadata"]["scope"]["reason"] == "no_supported_targets"
    assert empty["metadata"]["assessed_paths"] == {}


def test_partial_findings_summary_preserves_count(tmp_path):
    (tmp_path / "ruff.toml").write_text('lint.select = ["F401"]\n')
    (tmp_path / "a.py").write_text("import os\n")
    (tmp_path / "b.ts").write_text("export const x = 1;\n")
    result = LintTool().run(tmp_path)
    assert result["status"] == "fail"
    assert (
        result["summary"]
        == "lint [ruff+eslint]: 1 issue(s); partial: eslint not on PATH (install: npm install -g eslint)"
    )
    assert [f["rule"] for f in result["findings"]] == ["F401"]
    assert result["metadata"]["assessed_paths"] == {
        "ruff": [str(tmp_path / "a.py")],
        "eslint": [],
    }


def test_staged_source_digest_binds_snapshot(tmp_path):
    from rush.engines.staging import stage_inventory, staging_scope

    root = tmp_path / "project"
    root.mkdir()
    source = root / "a.py"
    source.write_bytes(b"import os\n")
    (root / "ruff.toml").write_text('lint.select = ["F401"]\n')
    staged = stage_inventory(root, tmp_path / "staged", ["a.py", "ruff.toml"])
    source.write_bytes(b"import sys\n")
    with staging_scope(staged):
        result = LintTool().run(source)
    assert (
        result["findings"][0]["extensions"]["source_digest"]
        == hashlib.sha256(b"import os\n").hexdigest()
    )
    assert result["metadata"]["assessed_paths"] == {"ruff": [str(source)]}
    assert source.read_bytes() == b"import sys\n"
```
Symlink test runs in environment permitting symlink creation; OS denial is an
external fixture prerequisite, never a skipped acceptance claim. Ambiguity unit
test invokes actual proposed selector (not a toy predicate), while end-to-end
real-Ruff minimizer tests exercise parser and selector from LintTool.


Verification requirement: original report Q02-08 at line 2675; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-09: Baseline containment dropped; absolute paths incompatible with `open_contained`

```
Baseline containment, validated before any engine runs. Reject caller '..' components before lexical normalization. root = the nearest ancestor (the selection
itself when it is a directory, else its parent; including itself) containing pyproject.toml,
package.json, ruff.toml or .ruff.toml, else the selection directory (resolved). 
  lexical = Path(os.path.abspath(baseline_result_path if absolute else root / baseline_result_path))
  rel = lexical.relative_to(root) (on ValueError retry lexical.relative_to(root.resolve()); on a
        second ValueError: invalid_argument)
  baseline_file = PhysicalRoot(root).open_contained(rel, "read")   # rush.io.physical_paths
A relative baseline_result_path is interpreted relative to root. ContainmentError (absolute-after-
normalization escape, "..", symlink component), a non-file, non-UTF-8 content, non-object JSON, or
tool != "lint" returns status error with metadata.error.code "invalid_argument" and zero engine spawns.
Lexical normalization (not resolve()) is deliberate: symlinks must still be seen by open_contained.
Baseline bytes are only read, never written.
```


Concrete proposed source, same `src/rush/tools/lint.py` module. Imports used by
Q02-09–14/M2: `ast`, `hashlib`, `json`, `os`, `re`, `tempfile`, `tomllib`,
`Path`, `Any`, `ToolResult`, `Finding`, `ExecutionPermissions`,
`check_permissions`, `build_execution_metadata`,
`PhysicalRoot`/`ContainmentError` from `rush.io.physical_paths`, and
`atomic_write_bytes` from `rush.runtime.filesystem`. Existing lint imports
already provide `run_engine`, `error_result`, `now_ms`, `elapsed_ms`.
Helpers below are defined proposed implementations, not live APIs.
Add exact imports at module top:
```python
import ast
import hashlib
import json
import os
import re
import tempfile
import tomllib

from ..engines.staging import StagingInputError
from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
from ..runtime.filesystem import atomic_write_bytes
```
Existing lint module already supplies Path/Any/Finding/ToolResult and shared runtime functions.
Add local imports of `active_staging` and `StagingInputError` from `rush.engines.staging`.

```python
def _lint_invalid(message: str) -> ToolResult:
    result = error_result("lint", None, message)
    result.setdefault("metadata", {})["error"] = {
        "code": "invalid_argument",
        "message": result["summary"],
    }
    return result


def _lint_root(path: Path) -> Path:
    selection = (path if path.is_dir() else path.parent).resolve()
    from ..engines.staging import active_staging

    staging = active_staging()
    markers = ("pyproject.toml", "package.json", "ruff.toml", ".ruff.toml")
    return next(
        (
            directory
            for directory in (selection, *selection.parents)
            if any(
                (
                    (staging.stage_path(directory) if staging else directory) / marker
                ).is_file()
                for marker in markers
            )
        ),
        selection,
    )


def _lint_relative(root: Path, value: str | Path) -> Path:
    supplied = Path(value)
    if ".." in supplied.parts:
        raise ValueError("parent traversal is forbidden")
    lexical = Path(
        os.path.abspath(supplied if supplied.is_absolute() else root / supplied)
    )
    return lexical.relative_to(root)


def _lint_input_file(root: Path, value: str | Path) -> Path:
    from ..engines.staging import active_staging

    relative = _lint_relative(root, value)
    logical = root / relative
    staging = active_staging()
    if staging is not None:
        rewritten = Path(staging.substitute_arg(str(logical)))
        if rewritten != logical:
            staged_file = PhysicalRoot(staging.staged_root).open_contained(
                rewritten.relative_to(staging.staged_root), "read"
            )
            if not staged_file.is_file():
                raise ValueError("selected input absent from staged inventory")
            staging.record_consumption(staged_file)
            return staged_file
    return PhysicalRoot(root).open_contained(relative, "read")


def _read_lint_baseline(root: Path, value: str | Path) -> dict[str, Any]:
    relative = _lint_relative(root, value)
    baseline_file = PhysicalRoot(root).open_contained(relative, "read")
    if not baseline_file.is_file():
        raise ValueError("baseline must be a contained regular file")
    baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
    if not isinstance(baseline, dict) or baseline.get("tool") != "lint":
        raise ValueError("baseline must be a lint result object")
    findings = baseline.get("findings")
    if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
        raise ValueError("baseline findings must be an object list")
    for finding in findings:
        if any(
            not isinstance(finding.get(k), str) for k in ("path", "rule", "message")
        ):
            raise ValueError("baseline finding path/rule/message must be strings")
        _lint_relative(root, finding["path"])
        extensions = finding.get("extensions", {})
        if not isinstance(extensions, dict):
            raise ValueError("baseline finding extensions must be an object")
        digest = extensions.get("source_digest")
        if digest is not None and (
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(
                "baseline source_digest must be a SHA256 hex digest or null"
            )
    if not isinstance(baseline.get("metadata", {}), dict):
        raise ValueError("baseline metadata must be an object")
    return baseline
```
Relative and contained absolute baselines both work. Reject lexical traversal
before normalization; validate components through `PhysicalRoot` before read.
No `resolve()` on caller baseline path that would hide symlinks. Validation runs
before ordinary engine dispatch; read errors (`OSError`, `UnicodeError`,
`ContainmentError`, `ValueError`) become `_lint_invalid(str(exc))`.
Proposed check: `tests/test_lint.py::test_baseline_rejections` plus
`::test_baseline_path_forms_and_symlink_rejection`; exact state: invalid input
error/code `invalid_argument`, zero Ruff subprocesses; valid relative/absolute
contained baseline gives same delta and unchanged baseline bytes.


Verification requirement: original report Q02-09 at line 2848; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-10: Finding identity fields do not exist on findings

```
Each current finding gets finding["extensions"]["source_digest"] (extensions is Phase 70's single open
field on Finding; no new top-level key) = sha256 hex of the bytes of the finding's file, where the file
is Path(finding["path"]) if absolute else root / finding["path"], resolved; None unless it is a regular
file inside root. Identity key = (finding["provenance"], finding["rule"], that file's POSIX path
relative to root, finding["message"], finding["extensions"]["source_digest"]). provenance is the
Phase 70 producer label ("lint/ruff", "lint/eslint", "lint/globstar", routing.finding_provenance);
there is no new `engine` finding field. Findings read from the baseline use the same key (a missing
extensions or source_digest compares as None).
```


Concrete proposed source beside Q02-09 helpers:
```python
def _bind_lint_sources(result: ToolResult, root: Path) -> None:
    for finding in result["findings"]:
        digest = None
        try:
            relative = _lint_relative(root, finding["path"])
            source = _lint_input_file(root, relative)
            if source.is_file():
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except (ContainmentError, StagingInputError, OSError, ValueError):
            pass
        finding.setdefault("extensions", {})["source_digest"] = digest


def _lint_finding_keys(result: dict[str, Any], root: Path) -> set[tuple[Any, ...]]:
    return {
        (
            finding.get("provenance"),
            finding["rule"],
            _lint_relative(root, finding["path"]).as_posix(),
            finding["message"],
            finding.get("extensions", {}).get("source_digest"),
        )
        for finding in result["findings"]
    }


def _apply_lint_delta(
    result: ToolResult, baseline: dict[str, Any] | None, root: Path
) -> ToolResult:
    if baseline is None:
        return result
    metadata = result["metadata"]
    if not metadata["config_identity_complete"]:
        metadata["delta"] = {
            "status": "unassessed",
            "reason": metadata["config_identity_reason"],
        }
        return result
    if baseline.get("metadata", {}).get("config_digest") != metadata["config_digest"]:
        return _lint_invalid("baseline tool/config mismatch")
    current = _lint_finding_keys(result, root)
    prior = _lint_finding_keys(baseline, root)
    metadata["delta"] = {
        "new": len(current - prior),
        "resolved": len(prior - current),
        "unchanged": len(current & prior),
    }
    return result
```
Prior keys use prior recorded source digest; never rehash current files for prior
findings. Canonical findings, producer provenance and full current result remain.
Proposed checks: `test_baseline_delta_preserves_full_result`,
`test_changed_digest_changes_identity`, `test_baseline_config_mismatch_is_error`
in `tests/test_lint.py`; prior `import os\n` versus current `import sys\n`
returns exact `{new:1,resolved:1,unchanged:0}` and current F401 preserved.


Verification requirement: original report Q02-10 at line 2873; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-11: Configuration identity undefined

```
Configuration identity (every LintTool.run result, with or without a baseline), computed after the
engines ran, with root as in baseline containment; concrete closure below replaces this ancestor-only sketch:
  config_names = ("pyproject.toml", "ruff.toml", ".ruff.toml", "eslint.config.js",
                  "eslint.config.mjs", "eslint.config.cjs", "package.json")
  principal_config_files = sorted({d / n for t in targets for d in (t.resolve().parent, *t.resolve().parent.parents)
                         if d == root or d.is_relative_to(root) for n in config_names if (d / n).is_file()})
  record = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in principal_config_files}
  record["engines"] = {c["engine"]: c.get("engine_version") for c in children}
  metadata.config_digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
  metadata.config_identity_complete = the closure completeness from _lint_configuration below
Comparison: with a baseline and config_identity_complete true, baseline.metadata.config_digest must
equal the current digest, else status error / metadata.error.code "invalid_argument" (config mismatch).
With config_identity_complete false, metadata.delta = {"status": "unassessed", "reason":
"imported_eslint_config_closure_unverified"} and findings are unchanged (the baseline is still
containment-validated first).
```


Concrete proposed source; principal Ruff configuration list also feeds scratch
copy/persistent artifact. Baseline identity binds contained `extend` references
recursively; scratch intentionally copies ancestor configurations only, so
missing extend content fails first replay honestly (M1).

```python
def _lint_configuration(
    root: Path,
    targets: list[Path],
    engine_files: dict[str, list[Path]],
    children: list[ToolResult],
    engine_args: list[str] | None,
) -> tuple[dict[str, Any], list[Path]]:
    names = (
        "pyproject.toml",
        "ruff.toml",
        ".ruff.toml",
        "eslint.config.js",
        "eslint.config.mjs",
        "eslint.config.cjs",
        "package.json",
    )
    principal = sorted(
        {
            directory / name
            for target in targets
            for directory in (target.resolve().parent, *target.resolve().parent.parents)
            if directory == root or directory.is_relative_to(root)
            for name in names
            if (directory / name).is_file()
        }
    )
    record: dict[str, Any] = {}
    complete = not bool(engine_files.get("eslint"))
    reason = None if complete else "imported_eslint_config_closure_unverified"
    pending = [(p, frozenset()) for p in principal]
    visited: set[Path] = set()
    while pending:
        config_file, ancestors = pending.pop()
        if config_file in ancestors:
            complete = False
            reason = reason or "ruff_config_closure_unverified"
            continue
        if config_file in visited:
            continue
        visited.add(config_file)
        try:
            relative = _lint_relative(root, config_file)
            input_file = _lint_input_file(root, relative)
            data = input_file.read_bytes()
            record[relative.as_posix()] = hashlib.sha256(data).hexdigest()
            if config_file.name in ("pyproject.toml", "ruff.toml", ".ruff.toml"):
                parsed = tomllib.loads(data.decode("utf-8"))
                if config_file.name == "pyproject.toml":
                    tool_config = parsed.get("tool", {})
                    if not isinstance(tool_config, dict):
                        raise ValueError("TOML tool must be a table")
                    ruff_config = tool_config.get("ruff", {})
                    if not isinstance(ruff_config, dict):
                        raise ValueError("TOML tool.ruff must be a table")
                else:
                    ruff_config = parsed
                extended = ruff_config.get("extend")
                if extended is not None:
                    if not isinstance(extended, str):
                        raise ValueError("Ruff extend must be a string")
                    extended_path = Path(os.path.abspath(config_file.parent / extended))
                    extended_relative = extended_path.relative_to(root)
                    _lint_input_file(root, extended_relative)
                    pending.append((extended_path, ancestors | {config_file}))
        except (ContainmentError, StagingInputError, OSError, UnicodeError, ValueError):
            complete = False
            if reason is None:
                reason = "ruff_config_closure_unverified"
    record["engines"] = {c["engine"]: c.get("engine_version") for c in children}
    record["engine_args"] = list(engine_args or [])
    return (
        {
            "config_digest": hashlib.sha256(
                json.dumps(record, sort_keys=True).encode()
            ).hexdigest(),
            "config_identity_complete": complete,
            "config_identity_reason": reason,
        },
        [
            p
            for p in principal
            if p.name in ("pyproject.toml", "ruff.toml", ".ruff.toml")
        ],
    )
```
Cycle, escape, unreadable/missing configuration and invalid TOML each make closure
unverified; no outside-root read and no infinite traversal. This strengthens report's raw ancestor-hash sketch: changing contained
`base.toml` used by Ruff `extend` changes digest; inaccessible/uncontained
closure makes delta unassessed, never fabricated identity completeness.
ESLint selections always retain exact
`imported_eslint_config_closure_unverified` reason. `engine_args` included
because `--select`/`--config` changes effective invocation even with identical
principal bytes. Arbitrary explicit `--config`/settings-file operands require
bounded declaration: when `engine_args` includes `--config` or `--settings`
(any `--name=value` form included), set complete False and reason
`explicit_engine_config_closure_unverified` unless ESLint reason already applies;
ordinary lint remains unchanged. Exact addition before return:
```python
    if any(
        arg == option or arg.startswith(option + "=")
        for arg in engine_args or []
        for option in ("--config", "--settings")
    ):
        complete = False
        reason = reason or "explicit_engine_config_closure_unverified"
```
Proposed checks: `test_baseline_config_mismatch_is_error`,
`test_baseline_delta_unassessed_for_js_selection`,
`test_baseline_extend_identity_changes`; exact extend-config edit invalidates
baseline, no findings suppression. Original principal config copied with same
relative layout for minimizer; arbitrary extend closure is not claimed copied.


Proposed check: `test_baseline_wrong_toml_table_shape_is_unassessed` in
`tests/test_lint.py` (Q02-08), run after implementation with
`env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_lint.py -q -k wrong_toml_table_shape`.
Expected two valid-TOML wrong-table cases preserve canonical ordinary lint and
return delta unassessed/reason ruff_config_closure_unverified; no AttributeError.

Verification requirement: original report Q02-11 at line 2897; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-12: `minimize_finding` ID syntax undefined

replace the first sentence of `:155` ("Minimization selects exactly one existing rule/location identity.") with:
```
minimize_finding grammar: "<RULE>@<path>:<line>". <RULE> is a finding rule; <path> is the finding's
file path relative to the lint root in POSIX form (root as defined in the baseline-containment rule),
or a bare basename accepted only when exactly one file among the current findings has that basename;
<line> is a positive integer. A string that does not match the grammar returns invalid_argument
(malformed). After the ordinary lint run, zero matching findings returns invalid_argument ("finding
not found") and more than one matching finding (same rule, path and line, different columns) returns
invalid_argument ("ambiguous finding"). Minimization then operates on exactly that one finding.
```
  The `invalid_argument` shape is the Q02-14/Q02-15 shape: `error_result("lint", None, message, metadata={"error": {"code": "invalid_argument", "message": message}})`.


Concrete proposed source:
```python
_FINDING_ID = re.compile(r"([^@\s]+)@([^:\x00]+):([1-9][0-9]*)")


def _parse_lint_finding_id(value: str) -> tuple[str, str, int]:
    if not isinstance(value, str) or (match := _FINDING_ID.fullmatch(value)) is None:
        raise ValueError("malformed minimize_finding")
    rule, path, line = match.groups()
    named = Path(path)
    if named.is_absolute() or ".." in named.parts or "\\" in path:
        raise ValueError("minimize_finding path must be root-relative POSIX")
    return rule, path, int(line)


def _select_lint_finding(
    result: ToolResult, root: Path, selector: tuple[str, str, int]
) -> Finding:
    rule, named, line = selector
    candidates = [
        finding
        for finding in result["findings"]
        if finding["rule"] == rule and finding.get("line") == line
    ]
    if "/" not in named:
        matching_paths = {
            _lint_relative(root, finding["path"]).as_posix()
            for finding in result["findings"]
            if _lint_relative(root, finding["path"]).name == named
        }
        if len(matching_paths) > 1:
            raise ValueError("ambiguous finding basename")
        candidates = [
            f for f in candidates if _lint_relative(root, f["path"]).name == named
        ]
    else:
        candidates = [
            f for f in candidates if _lint_relative(root, f["path"]).as_posix() == named
        ]
    if len(candidates) != 1:
        raise ValueError("finding not found" if not candidates else "ambiguous finding")
    return candidates[0]
```
Proposed checks: `test_minimize_invalid_and_denied` and
`test_minimize_selector_ambiguity`. Two same-basename source files reject bare
basename; qualified path chooses one; same rule/path/line with different columns
rejects ambiguity. Malformed ID rejects before ordinary engine spawn; unmatched
ID rejects after ordinary lint with zero reduction/replay/artifact effects.


Verification requirement: original report Q02-12 at line 2925; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-13: Reproducer artifact location, retention and cleanup undefined

```
Reduction trials run inside tempfile.TemporaryDirectory(prefix="rush-lint-reduce-") (removed on exit).
The scratch tree holds the source copy at its path relative to root plus every Ruff configuration file
(pyproject.toml, ruff.toml, .ruff.toml) in the file's ancestor chain up to root, at the same relative
layout. The final reproducer and a copy of those config files are written only with
allow_artifact_write, under rel = Path(".rush/lint-reproducers") / sha256(original bytes).hexdigest()[:16]
/ <source path relative to root> via atomic_write_bytes(root, rel, data) (config files beside it, same
relative layout); an existing different file at the same rel is an error, identical bytes are rewritten
as a no-op. metadata.minimization = {"status", "rule", "message", "source" (reduced text),
"reproducer_path" (absolute str), "analysis_runs", "rejected_runs", "invalid_trials",
"source_sha256", "config_sha256"}; source_sha256 = sha256 of the original bytes, config_sha256 =
sha256 of the sorted {relative config path: sha256} JSON.
```


Concrete proposed publication helper; `configs` contains the exact principal
configuration bytes copied to scratch, keyed by root-relative POSIX path.

```python
def _publish_lint_reproducer(
    root: Path,
    relative: Path,
    original: bytes,
    reduced: bytes,
    configs: dict[str, bytes],
) -> Path:
    folder = Path(".rush/lint-reproducers") / hashlib.sha256(original).hexdigest()[:16]
    outputs = {folder / relative: reduced}
    outputs.update({folder / Path(name): data for name, data in configs.items()})
    physical = PhysicalRoot(root)
    for rel, data in outputs.items():
        destination = physical.open_contained(rel, "write")
        if destination.exists() and (
            not destination.is_file() or destination.read_bytes() != data
        ):
            raise ValueError(f"reproducer collision: {rel.as_posix()}")
    for rel, data in outputs.items():
        destination = physical.open_contained(rel, "write")
        if not destination.exists():
            atomic_write_bytes(root, rel, data)
    return physical.open_contained(folder / relative, "read")
```
Persistent artifact is exactly
`.rush/lint-reproducers/<sha256(original bytes)[:16]>/<root-relative source>`;
config copies retain same relative layout. Identical existing bytes are untouched;
different existing bytes return error before any publication. No implicit cleanup
of retained reproducer; caller may remove this exact digest directory when finished.
Transient `TemporaryDirectory` removed on every exit. No artifact directory
before successful/limited reduction and all grants.

Proposed checks: `test_minimize_budget_limited`,
`test_minimize_artifact_retention_and_collision`; exact retained text/config
readable after helper returns, same invocation leaves bytes unchanged, colliding
different text returns error/code `invalid_argument` and existing artifact stays.


Verification requirement: original report Q02-13 at line 2956; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-14: Denied/invalid result semantics contradict "preserve ordinary lint status"

```
CLI flags --baseline-result, --minimize-finding, --max-reduction-runs; MCP equivalent typed inputs.
Validated before any engine runs (zero engine spawns): max_reduction_runs must be an int (not a bool)
in 1..100 (conditional owner-approved bound); minimize_finding must match "<RULE>@<path>:<line>"; baseline_result_path must satisfy the
containment, parse and tool == "lint" rules. A violation returns
error_result("lint", None, message, metadata={"error": {"code": "invalid_argument", "message": message}}) (status error, findings
[], no minimizer execution). After the ordinary lint run (still zero reduction trials), a
minimize_finding matching no finding or more than one, and a baseline whose metadata.config_digest
differs, return the same error shape.
Minimization without all of allow_build, allow_slow and allow_artifact_write runs ordinary lint
unchanged (status, findings, ledger preserved) and adds metadata.minimization = {"status": "denied",
"analysis_runs": 0, "missing_permissions": [the missing ones of "build", "slow", "artifact_write", in
that order]}; no scratch directory and no artifact are created.
OWNER DECISION FLAG: the 1..100 bound is proposed (the plan says "invalid budget" without a range);
the denied branch keeps the ordinary lint status because findings must never be hidden (audit F08).
```
  Update the ledger and tests to match (`test_minimize_invalid_and_denied`, Q02-08).


Concrete proposed `LintTool.__call__` replacement; keep positional compatibility
for existing `path`, `engine_args`, `owner_instance_id`, `run_id`.
F1 public request models enforce strict booleans/unknown-key rejection before
dispatch; this callable constructs one permissions instance (C-10).
```python
    def __call__(
        self,
        path: Path,
        engine_args: list[str] | None = None,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
        *,
        baseline_result_path: str | None = None,
        minimize_finding: str | None = None,
        max_reduction_runs: int = 12,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            engine_args=engine_args,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
            baseline_result_path=baseline_result_path,
            minimize_finding=minimize_finding,
            max_reduction_runs=max_reduction_runs,
            permissions=ExecutionPermissions(
                build=allow_build, slow=allow_slow, artifact_write=allow_artifact_write
            ),
        )
```
Proposed `LintTool.run` signature adds
`baseline_result_path: str | Path | None = None`,
`minimize_finding: str | None = None`,
`max_reduction_runs: int = 12`,
`permissions: ExecutionPermissions | None = None` as keyword-only parameters;
existing `engine_args`, `config`, ownership remain unchanged.
Insert before `targets, engine_files, languages = _select_engines(path, config)`:
```python
        root = _lint_root(path)
        try:
            if type(max_reduction_runs) is not int or not 1 <= max_reduction_runs <= 100:
                raise ValueError("max_reduction_runs must be an integer in 1..100")
            selector = (
                _parse_lint_finding_id(minimize_finding)
                if minimize_finding is not None
                else None
            )
            baseline = (
                _read_lint_baseline(root, baseline_result_path)
                if baseline_result_path is not None
                else None
            )
        except (ContainmentError, StagingInputError, OSError, UnicodeError, ValueError) as exc:
            return _lint_invalid(str(exc))
```
Replace final `return _assemble_lint_result(...)` with `result =` that same
call. Preserve existing selection-directory `scope_scope_root = path if path.is_dir()
else path.parent` for `lint_scope` rather than overwriting baseline project root. Replace existing root assignment with scope_root and pass scope_root to lint_scope(requested, dispatched, children, scope_root).
Pass `engine_files=dispatched` to Q02-01 assembly; append:
```python
        identity, config_files = _lint_configuration(
            root, targets, engine_files, children, engine_args
        )
        result.setdefault("metadata", {}).update(identity)
        _bind_lint_sources(result, root)
        result = _apply_lint_delta(result, baseline, root)
        if result["status"] == "error" or selector is None:
            return result
        try:
            finding = _select_lint_finding(result, root, selector)
        except (ContainmentError, StagingInputError, OSError, ValueError) as exc:
            return _lint_invalid(str(exc))
        return _minimize_lint_finding(
            result,
            root,
            finding,
            config_files,
            permissions,
            max_reduction_runs,
            engine_args,
            owner_instance_id,
            run_id,
        )
```
Empty-selection / no-engine early returns must also receive computed config identity
and `_bind_lint_sources` before optional delta; with minimization selector, reject
`finding not found` after ordinary skipped result. Concrete common local closure,
placed after prevalidation and called by those two existing return branches:
```python
def finish_unassessed(result: ToolResult) -> ToolResult:
    identity, _ = _lint_configuration(root, targets, engine_files, [], engine_args)
    metadata = result.setdefault("metadata", {})
    metadata.update(identity)
    supported = any(engine_files.values())
    metadata.setdefault("scope", {}).update(
        {
            "coverage": "unavailable" if supported else "none",
            "reason": "engine_unavailable" if supported else "no_supported_targets",
        }
    )
    metadata["assessed_paths"] = {
        engine: [] for engine, files in engine_files.items() if files
    }
    _bind_lint_sources(result, root)
    if selector is not None:
        return _lint_invalid("finding not found")
    return _apply_lint_delta(result, baseline, root)
```
Both existing `return _build_skipped_result(...)` and
`return _check_missing_engines_result(...)` become
`return finish_unassessed(<same existing result expression>)`.
No duplicate lint selection/aggregation implementation.

OWNER DECISION: `1..100` upper bound conditional report proposal, default12
audit1650/reportQ02-17. James must approve cap or supply replacement before
implementation; update this guard, Click help, ToolOptionSpec and invalid-budget
tests uniformly. Current planning authorization settles neither cap nor D3/D5/D8.
Proposed checks: `test_minimize_invalid_and_denied`, baseline-delta/containment
tests, F6 CLI/stdio parity; malformed input zero ordinary spawns, denied optional
work preserves ordinary status/findings/scope and zero replay/trial/artifact effects.


Verification requirement: original report Q02-14 at line 2980; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-15: `invalid_argument` reason is not an existing contract

add to Required behavior:
```
Invalid-input metadata.error.code value "invalid_argument" (introduced by this task), set via
error_result("lint", None, message, metadata={"error": {"code": "invalid_argument", "message": message}}) (error_result from
rush.tools.common). It covers: wrong-tool, malformed, non-file or escaping baseline; baseline config
mismatch; bad max_reduction_runs; malformed, unmatched or ambiguous minimize_finding. Document it in
docs/reference/result-reference.md beside target_invalid.
```

Verification requirement: original report Q02-15 at line 3005; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-16: "W18" undefined; stop-on-missing-OCI contradicts audit

Non-Ruff minimization unconditionally {status:skipped,reason:isolation_unavailable_for_non_ruff,analysis_runs:0}, ordinary result retained. W18 audit Command45/79, F4 under D1; Ruff minimizer no F4/F5 dependency and missing OCI never stop.

Verification requirement: original report Q02-16 at line 3020; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-17: CLI option mechanism unspecified and conflicts with current development

```
Foundation Q02-E1-options patch row: add a "lint" entry to src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS (phase/70):
  "lint": (
      click.Option(["--baseline-result", "baseline_result_path"],
                   type=click.Path(dir_okay=False, path_type=Path), default=None,
                   help="Prior `rush lint --json` result to compare against (read only; must lie "
                        "inside the project root; relative paths resolve against the root)."),
      click.Option(["--minimize-finding", "minimize_finding"], type=str, default=None,
                   help="RULE@path:LINE of an existing Ruff finding to reduce (requires "
                        "--allow-build --allow-slow --allow-artifact-write)."),
      click.Option(["--max-reduction-runs", "max_reduction_runs"], type=int, default=None,
                   help="Reduction analysis budget, 1-100 (default 12)."),
  ),
type=int (not click.IntRange) is deliberate: LintTool.run validates the range so CLI and MCP return
the identical invalid_argument ToolResult instead of a Click usage error.
Grants use the existing --allow-build/--allow-slow/--allow-artifact-write options; LintTool.__call__
declares allow_build/allow_slow/allow_artifact_write as keyword-only bools (bound by the executor from
context.permissions); no new grant flags.
Foundation Q02-R4-catalog patch row, src/rush/catalog.py: TOOL_SPECS["lint"] gains option_specs=(
  ToolOptionSpec(name="baseline_result_path", value_type=str, default=None, path_kind="file",
                 description="Prior lint result JSON for delta comparison."),
  ToolOptionSpec(name="minimize_finding", value_type=str, default=None,
                 description="RULE@path:LINE of a Ruff finding to reduce."),
  ToolOptionSpec(name="max_reduction_runs", value_type=int, default=12, minimum=1, maximum=100,
                 description="Reduction analysis budget."),
) and its mcp_description is:
"Lint Python/JS/TS files at <path>; ruff, eslint, optional globstar. No grant needed for linting. status='skipped' means no inputs/engines. See discovery for baseline/minimization."
F10 full discovery separately carries exact grants; keep mcp_description 20-199 chars.

```

Verification requirement: original report Q02-17 at line 3033; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-18: Checks omit required suites

```
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_lint.py tests/test_engines.py tests/test_tools.py tests/test_language_routing.py tests/test_phase60_characterization.py tests/test_phase60_refactor.py tests/test_phase60_complexity_thresholds.py tests/test_ruff_reference.py tests/test_eslint_reference.py tests/test_globstar_reference.py tests/test_phase70_t5.py tests/test_phase70_t9.py tests/test_phase70_t13.py tests/test_phase70_t16.py tests/test_cli_registry.py tests/test_mcp.py tests/test_capabilities.py tests/test_phase70_engine_applicability.py tests/test_full_project_scan.py tests/test_dashboard_map.py tests/test_project_run_lifecycle.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/ -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
```

Verification requirement: original report Q02-18 at line 3075; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-19: Docs work vague, deferred and incomplete


Foundation F8 applies exact doc patch rows in same implemented packet;
command owner authors content, never writes Foundation-owned docs directly.
One command-owned new ADR only:
`docs/adr/0052-lint-coverage-baseline-and-minimization.md`.
F8-HISTORY changes historical index leading Current status paragraph only;
never appends index row. All behavior future/proposed until implementation passes.

Q02-DOC-options, targets docs/reference/cli-reference.md,
docs/reference/mcp-tool-reference.md, docs/MCP_REFERENCE.md; add exact rows:
```markdown
| CLI option | MCP input | Default | Behavior |
| --- | --- | --- | --- |
| --baseline-result PATH | baseline_result_path | null | Read contained prior lint JSON; full findings plus new/resolved/unchanged counts. |
| --minimize-finding RULE@path:LINE | minimize_finding | null | Reduce one unique Ruff finding; requires allow_build, allow_slow and allow_artifact_write. |
| --max-reduction-runs N | max_reduction_runs | 12 | Integer deletion-trial budget; proposed range 1..100 requires owner approval. |
```

Q02-DOC-selector, targets docs/reference/cli-reference.md lint engine cell,
docs/user-guide/checking-code.md section2, docs/reference/engine-directory.md
Ruff/ESLint/Globstar rows: replace lint's Ruff-or-Flake8/ESLint-or-Biome/Stylelint
claims with exact sentence:
`Lint selects Ruff for .py/.pyi, ESLint for JS/TS extensions and optional Globstar
when available; each receives selected files once with no directory operand.`
Keep other tools' independent supported engines unchanged.

Q02-DOC-examples, docs/user-guide/checking-code.md, append:
```markdown
### Compare lint findings and reduce one Ruff finding

Save `rush lint src --json` output as prior-lint.json inside project root.
Run `rush lint src --baseline-result prior-lint.json --json` after edits.
Result retains every current finding and reports new, resolved and unchanged counts.
JavaScript/TypeScript config-import identity remains unassessed.
If baseline tool/config differs, rerun ordinary lint and save new baseline explicitly.

Run `rush lint src/a.py --minimize-finding E402@src/a.py:88 --max-reduction-runs 12 --allow-build --allow-slow --allow-artifact-write --json`.
Use actual rule/path/line from current result. Read reduced source at
.rush/lint-reproducers/<first 16 hex characters of original SHA256>/src/a.py.
Original source stays unchanged. budget_limited means candidates remain;
increase budget within approved range and retry. Scratch config error reports
unreproducible_in_scratch and writes no reproducer. ESLint/Globstar minimization
reports skipped with isolation_unavailable_for_non_ruff.
```

Q02-DOC-results, docs/reference/result-reference.md, append:
```markdown
### Lint evidence

metadata.engines retains each engine; metadata.scope reports coverage;
metadata.assessed_paths maps engine to absolute logical selected paths or [] for
unassessed child. Clean Ruff plus missing ESLint returns warn under proposed
D5 policy, partial scope and summary naming missing ESLint. Finding summary
retains issue count and partial reason.

metadata.config_digest binds selected config bytes, contained Ruff extend
closure, engine versions and caller engine_args. config_identity_complete=false
makes delta unassessed with explicit reason. findings[].extensions.source_digest
binds selected source bytes, including staged snapshot bytes.
metadata.delta contains exact new/resolved/unchanged counts without suppression.

metadata.minimization records status, rule, message, source_path, source,
source_sha256, config_sha256, reproducer_path, analysis_runs, rejected_runs,
invalid_trials and scratch_replay_runs when applicable. Cancellation/timeout
retain actual complete child result in last_run, propagate supplied execution
evidence and preserve ordinary status/findings/scope. Cancellation is
skipped/reason cancelled; timeout is error/reason timeout. Other unsuccessful
scratch analyses use failed_child under unreproducible_in_scratch.
Statuses: one_deletion_minimal, budget_limited, denied, skipped, error,
unreproducible_in_scratch.
Denied optional work retains ordinary findings/scope and records execution
disposition not_run/cause permission_denied. Non-Ruff skipped reason is
isolation_unavailable_for_non_ruff. Invalid input uses metadata.error.code
invalid_argument and metadata.error.message equal to result summary.
```

Q02-DOC-permissions, docs/safety/permissions.md artifact-write row, append exact:
`Lint minimization also needs build and slow grants; final artifacts only under
.rush/lint-reproducers/<digest prefix>/. Ordinary lint and baseline comparison
need no minimization grants.` Foundation updates existing permission rows in
one serialized F8 edit, preserving unrelated operations.

Q02-DOC-partial, docs/user-guide/understanding-results.md, append exact:
`For a.py plus b.ts with Ruff available and ESLint missing, lint reports warn
under proposed D5 policy, partial scope, Ruff ok and ESLint skipped; summary
says no findings in assessed files and names missing ESLint. Supply ESLint
through explicit existing engine workflow, then rerun; Ruff success alone does
not assess TypeScript.`

Q02-DOC-history, docs/CLI_COOKBOOK.md and docs/KNOWN_ISSUES.md:
after R1–R3 behavioral PASS, replace only combined
`lint/format can falsely report success` clause with
`format can falsely report success`; preserve format limitation until Q03
acceptance. Do not remove history before executable route.

Q02-DOC-changelog, CHANGELOG.md, add exact:
`Lint uses exact selected engine targets, preserves partial engine evidence,
compares contained source/config-bound baselines, and reduces one Ruff finding
without changing original source.` No version bump.

Command-owned ADR new exact body:
```markdown
# 0052: Lint coverage, baseline identity and minimization

Current status: Proposed; implementation and behavioral acceptance pending.

Lint sends selected operands through explicit selected_targets, preserving legacy
direct-adapter args/root behavior when keyword is None. Main Ruff check and
show-files probe use same staged targets/config/cwd. Partial evidence remains
metadata.engines, metadata.scope and metadata.assessed_paths; status uses shared
aggregate_status and D5 decision, never lint-local override.

Baseline reads contained prior lint JSON and compares producer/rule/root-relative
path/message/source-digest keys under matching config/version identity.
Full findings remain; unresolved config-import closure makes delta unassessed.

Ruff minimization replays source/config in private temporary scratch, then deletes
whole top-level statement spans including decorators. Records actual trial,
rejected, AST-invalid and replay counts; distinguishes complete minimal pass from
budget exhaustion; retains artifacts under deterministic original digest prefix.
Grants required before scratch/replay/publication. Source/config drift or artifact
collision returns error; scratch nonreproduction returns factual operation error
summary without artifact. Non-Ruff findings retain ordinary result and skipped operation.

Acceptance: tests/test_lint.py::test_selected_files_once_and_partial_engine,
::test_malformed_output_is_error, ::test_baseline_delta_preserves_full_result,
::test_minimize_complete_pass_at_exact_budget_is_minimal,
::test_minimize_artifact_retention_and_collision and ::test_lint_cli_stdio_options_and_denial.
D3/D5/D8 and upper budget bound remain owner decisions.
```


### Q02-20: "Reconcile broad catalog engine claims" dropped

add ledger row and deliverables:
```
| R4 | Reconcile catalog/docs engine claims with the actual selector | catalog.py TOOL_SPECS["lint"]; docs/reference/cli-reference.md lint row; docs/user-guide/checking-code.md section 2 | TOOL_SPECS["lint"].engine_names == ("ruff", "eslint", "globstar") and mcp_description names "ruff, eslint, optional globstar"; the docs list exactly those engines |
```
  Behavior consequence stated in the plan: because lint then owns globstar, `plan_scan` no longer lists globstar as a separate engine-only candidate (the engine already runs inside lint when on PATH, so a full scan stops running it twice), and capability text for lint lists the globstar binary. Add test `test_lint_catalog_engines_match_selector` asserting `TOOL_SPECS["lint"].engine_names == ("ruff", "eslint", "globstar")`; add `tests/test_cli_registry.py`, `tests/test_capabilities.py`, `tests/test_phase70_engine_applicability.py` and `tests/test_full_project_scan.py` to the expected-diff and Checks lists (already in the Q02-18 command).


Concrete proposed Foundation Q02-R4-catalog row:
set lint engine_names=("ruff", "eslint", "globstar"); preserve canonical
name/category/identity and F10 short mcp_description. Existing
project_run._owned_engine_names/_build_candidates already suppress owned engines.

Proposed tests/test_lint.py body invoking real scanner/capability code:
```python
def test_lint_catalog_engines_match_selector(tmp_path, monkeypatch):
    from rush.capabilities import inspect_capabilities
    from rush.catalog import TOOL_SPECS
    from rush.config import RushConfig
    from rush.workflows.project_run import _build_candidates

    assert TOOL_SPECS["lint"].engine_names == ("ruff", "eslint", "globstar")
    candidates = _build_candidates([LintTool()])
    assert [
        (c.candidate_id, c.kind) for c in candidates if c.candidate_id == "lint"
    ] == [("lint", "tool")]
    assert not [
        c for c in candidates if c.candidate_id == "globstar" and c.kind == "engine"
    ]
    monkeypatch.setattr(
        "rush.capabilities.shutil.which",
        lambda binary: "/bin/globstar" if binary == "globstar" else None,
    )
    monkeypatch.setattr("rush.capabilities.resolve_binary", lambda binary: None)
    capability = inspect_capabilities(tmp_path, config=RushConfig())["tools"]["lint"]
    assert capability["state"] == "installed"
    assert capability["reason"] == "local engine on PATH: globstar"
```
No process/network/install; actual catalog-driven candidate suppression and
capability reason. Retain scanner/application regressions in Q02-18/C20 union.
Proposed command selects this node plus tests/test_capabilities.py,
tests/test_phase70_engine_applicability.py and tests/test_full_project_scan.py;
exact tuple, no engine-only Globstar and installed capability reason required.


Verification requirement: original report Q02-20 at line 3126; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-21: X1 expansion lacks required assessment content

add a "Worked cases" subsection after the ledger:
```
Worked cases.
E1 before: `rush lint src/python --json` run before and after an edit gives two unrelated findings lists; the
caller diffs them by hand. After: `rush lint src/python --baseline-result prior-lint.json --json` (MCP:
{"path":"src/python","baseline_result_path":"prior-lint.json"}) returns the complete current findings and
metadata.delta == {"new":1,"resolved":1,"unchanged":0}; the baseline is read only and nothing is suppressed.
lines matter. After: `rush lint src/a.py --minimize-finding E402@src/a.py:88 --allow-build --allow-slow
--allow-artifact-write --json` (MCP: {"path":"src/a.py","minimize_finding":"E402@src/a.py:88",
"allow_build":true,"allow_slow":true,"allow_artifact_write":true}) returns metadata.minimization with
status "one_deletion_minimal", reproducer_path under .rush/lint-reproducers/<16 hex>/src/a.py containing
the reduced text (for the plan fixture "print(1)\nimport os\n"), and observed analysis_runs/rejected_runs.
Why not existing tooling: Ruff has no reduction mode (`ruff check --help` at 0.16.3 has no
minimize/reduce/bisect option); Rush has no reducer (no deletion-based minimization in src at 66c6c79);
generic delta-debugging reducers such as C-Reduce need a hand-written interestingness script that
reproduces the Ruff invocation, the project configuration and the exact rule/message match, and know
nothing of Rush grants, run budgets or owned artifacts. This operation binds all of them in one call.
Adoption stays the owner's assessment; X1 is not removed.
```

Verification requirement: original report Q02-21 at line 3141; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-22: Template nonconformance and organization

Implementation packet conforms to binding task template through plan's Required behavior,
Deliverables, Constraints, Checks and Completion sections. No instruction to edit
missing earlier draft. Implement R1-R4, E1, X1 through concrete packets above;
root controls global structure and complete literal file map.
Partial status follows Foundation F2/D5; never asks for lint-local skipped override.
First callable boundary: live LintTool.run -> _run_selected_engines -> runtime.run_engine.
Foundation applies Q02-R1-runtime before command adapter keyword calls; Q02 Ruff
owner applies Q03-M2 selected format vector after R1. Immutable contracts:
Engine.run ABC, tools/common.py re-export, _staged_invocation four-tuple.
Future completion requires actual lint/baseline/minimizer behavior and named checks,
not Markdown structural inventory. No OCI prerequisite for Ruff-only X1.


### Q02-23: Ambiguous compressed terms

```
RuffEngine.normalize returns status error with findings [] when: the exit code is not 0 or 1 (existing);
the exit code is 0 or 1 and stdout is non-empty but not a JSON list whose items are all objects
(truncated "[{", {"a":1}, [1]); or the exit code is 1 with zero findings (existing). Exit 0 with a
non-empty valid finding list is not contradictory (`ruff --exit-zero` passed through engine_args) and
keeps exact warn/fail. Exit 0 with empty stdout is unchanged (ok).
```
```python
assert (m["analysis_runs"], m["rejected_runs"], m["invalid_trials"]) == (6, 4, 0)
assert m["scratch_replay_runs"] == 1
```
Concrete proposed ordinary-check parse guard in `RuffEngine.run`, after JSON
parsing, before EngineResult construction:
```python
        invalid_output = (
            not format_check
            and bool(proc.stdout.strip())
            and (
                not isinstance(parsed, list)
                or any(
                    not isinstance(item, dict)
                    or any(
                        not isinstance(item.get(key), str) or not item[key]
                        for key in ("filename", "code", "message")
                    )
                    or not isinstance(item.get("location"), dict)
                    or any(
                        type(item["location"].get(key)) is not int or item["location"][key] < 1
                        for key in ("row", "column")
                    )
                    for item in parsed
                )
            )
        )
        if invalid_output:
            findings_raw = []
```
EngineResult `summary=` becomes
`"ruff: unreadable findings JSON" if invalid_output else self._summary(...)`.
In `RuffEngine.normalize`, immediately before finding comprehension:
```python
        if raw.get("summary") == "ruff: unreadable findings JSON":
            return ToolResult(
                tool=tool_name,
                engine=self.name,
                engine_version=self._version_str(),
                status="error",
                duration_ms=raw.get("duration_ms", elapsed_ms(0)),
                summary="ruff: unreadable findings JSON",
                findings=[],
                raw=raw.get("parsed"),
            )
```
Guard excludes format branch, preserving its existing non-JSON output semantics.
Ordinary rc0/1 malformed JSON, non-list, scalar items, missing/invalid fields each
returns canonical error before `.get`/normalization can crash. rc2 and rc1 empty
keep existing exact error route. rc0 with valid findings (`--exit-zero`) keeps
exact severity; F401 fail, E402 warn per live `_ruff_severity` at ruff.py205–217.
Proposed checks `test_ruff_output_shapes` / `test_malformed_output_is_error`;
extend matrix with `[{"code":"F401","filename":"a.py","message":"fixture","location":"bad"}]`
and `[{}]`, both exact error/findings[].


Verification requirement: original report Q02-23 at line 3223; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-24: Ownership contradictions

Foundation sole shared-file writer. Exact patch rows supplied here:
Q02-R1-runtime: runtime/subprocesses.py::run_engine/_run_engine_in_scope/_run_scope_probe,
_stage_selected_targets/_selected_targets_kwargs; Q02-E1-options:
cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS["lint"]; Q02-R4-catalog:
catalog.py::TOOL_SPECS["lint"]; Q02-parity: Foundation CLI/MCP parity suites.
Foundation F1/F2/F3/F6 first, selected-target runtime row then Q02 adapters;
Q02 Ruff owner applies Q03-M2 format row, frozen handoff before Q03 consumes.
Command writes only tools/lint.py, engines/{ruff,eslint,globstar}.py,
tests/test_lint.py and docs/adr/0052-lint-coverage-baseline-and-minimization.md.
Foundation F8 owns overlapping documentation/receipt patch rows Q02-DOC-*.
tools/common.py and engines/base.py unchanged; no provider ownership transferred.
Reviewer read-only on frozen bytes.


### Q02-25: Summary-count / partial-in-summary requirement dropped

Summary rules are defined in Q02-01 and Required behavior items 2–3 (`no findings in assessed files; partial: …` and `…; partial: <reasons>` suffix). Add the sentence: `Summary: lint [<engines>]: N issue(s) when findings exist, else "no findings in assessed files"; when any applicable child is skipped the summary ends with "; partial: " + "; ".join(skip_reasons).` The assertion is the exact `summary` equality inside `test_selected_files_once_and_partial_engine` (Q02-07).

Verification requirement: original report Q02-25 at line 3269; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-26: Minimizer metadata renamed without a record

```
Recorded rename from the audit: minimal_reproducer.{attempts, rejected, original_digest, source} become
minimization.{analysis_runs, rejected_runs, source_sha256, reproducer_path}; `rule` and `message` are kept
and the reduced source text is also returned inline as minimization.source.
```

Verification requirement: original report Q02-26 at line 3277; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-M1: Ruff `extend` configs break the scratch copy, and the plan would report a false `one_deletion_minimal`

```
Scratch fidelity: if any trial analysis returns status error (for example a config using
`extend = "base.toml"` whose target is not copied), reduction stops at once:
metadata.minimization.status = "unreproducible_in_scratch", the original file is unchanged, no
reproducer is written, analysis_runs counts the trials that ran, and the failing child's summary is
returned in metadata.minimization.error.
```
  Test: `test_minimize_unreproducible_when_config_extends_outside_copy` (Q02-08).
Mandatory first replay correction: missing extend fails replay with analysis_runs=0,
scratch_replay_runs=1; old first-deletion expectation analysis_runs=1 superseded.
Successful fixture remains six deletion trials/four rejected/zero invalid,
plus one separately recorded replay; replay never consumes deletion budget.

Verification requirement: original report Q02-M1 at line 3298; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-M2: The deletion operator's span, invalid-trial handling and budget label are not defined, and the audit formulas are wrong

```
Deletion unit: each top-level statement's whole physical lines, from min(node.lineno, *(d.lineno for d in
node.decorator_list)) through node.end_lineno (ast reports a decorated def/class at its `def` line).
A trial that fails ast.parse (for example `x = 1; y = [\n    2]`, where the first statement shares its
line with the second) is not analyzed; it counts in invalid_trials, not in analysis_runs.
`one_deletion_minimal` means the last complete pass over the remaining statements found no parse-valid
single deletion that keeps the rule and message. `budget_limited` is reported only when the budget ran
out while at least one candidate of the current pass was still untried.
```
  Tests: `test_minimize_skips_syntactically_invalid_deletion`, `test_minimize_complete_pass_at_exact_budget_is_minimal` (Q02-08).


Concrete proposed reduction implementation in `src/rush/tools/lint.py`;
uses Q02-09/13 definitions and existing `rush.engines.ENGINES`.

```python
def _minimization_terminal(
    result: ToolResult, child: ToolResult, receipt: dict
) -> bool:
    child_metadata = child.get("metadata", {})
    execution = child_metadata.get("execution", {})
    cancelled = execution.get("disposition") == "cancelled"
    timeout = child_metadata.get("terminal_reason") == "timeout"
    if not cancelled and not timeout:
        return False
    reason = "cancelled" if cancelled else "timeout"
    metadata = result.setdefault("metadata", {})
    metadata["minimization"] = {
        **receipt,
        "status": "skipped" if cancelled else "error",
        "reason": reason,
        "last_run": child,
    }
    if "execution" in child_metadata:
        metadata["execution"] = child_metadata["execution"]
    result["summary"] += f"; minimization {reason}: {child['summary']}"
    return True


def _minimize_lint_finding(
    result: ToolResult,
    root: Path,
    finding: Finding,
    config_files: list[Path],
    permissions: ExecutionPermissions | None,
    max_reduction_runs: int,
    engine_args: list[str] | None,
    owner_instance_id: str | None,
    run_id: str | None,
) -> ToolResult:
    from ..engines import ENGINES

    metadata = result.setdefault("metadata", {})
    if finding.get("provenance") != "lint/ruff":
        metadata["minimization"] = {
            "status": "skipped",
            "reason": "isolation_unavailable_for_non_ruff",
            "analysis_runs": 0,
        }
        return result
    required = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    allowed, missing = check_permissions(required, permissions)
    if not allowed:
        metadata["minimization"] = {
            "status": "denied",
            "reason": "build_or_slow_denied"
            if {"build", "slow"} & set(missing)
            else "artifact_write_denied",
            "analysis_runs": 0,
            "scratch_replay_runs": 0,
            "missing_permissions": missing,
        }
        # Keep ordinary execution evidence; denied operation has its own execution record.
        metadata["minimization"]["execution"] = build_execution_metadata(
            "executed",
            requested=required,
            granted=permissions,
            extra={"disposition": "not_run", "cause": "permission_denied"},
        )
        return result

    try:
        relative = _lint_relative(root, finding["path"])
        source = _lint_input_file(root, relative)
        live_source = PhysicalRoot(root).open_contained(relative, "read")
        live_original = live_source.read_bytes()
        original = source.read_bytes()
        current = original.decode("utf-8")
        configs = {
            _lint_relative(root, p).as_posix(): _lint_input_file(root, p).read_bytes()
            for p in config_files
        }
        live_configs = {
            name: PhysicalRoot(root).open_contained(name, "read").read_bytes()
            for name in configs
        }
        receipt: dict[str, Any] = {
            "rule": finding["rule"],
            "message": finding["message"],
            "source_path": relative.as_posix(),
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "config_sha256": hashlib.sha256(
                json.dumps(
                    {
                        name: hashlib.sha256(data).hexdigest()
                        for name, data in configs.items()
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            "analysis_runs": 0,
            "rejected_runs": 0,
            "invalid_trials": 0,
            "scratch_replay_runs": 0,
        }
        with tempfile.TemporaryDirectory(prefix="rush-lint-reduce-") as scratch_name:
            scratch = Path(scratch_name)
            target = scratch / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            for name, data in configs.items():
                copied = scratch / name
                copied.parent.mkdir(parents=True, exist_ok=True)
                copied.write_bytes(data)

            def analyze(text: str) -> ToolResult:
                target.write_text(text, encoding="utf-8")
                return run_engine(
                    ENGINES["ruff"],
                    scratch,
                    list(engine_args or []),
                    cwd=scratch,
                    project_root=root,
                    tool_name="lint",
                    selected_targets=[target],
                    consumed_paths=[str(target)],
                    owner_instance_id=owner_instance_id,
                    run_id=run_id,
                )

            def retains(child: ToolResult) -> bool:
                return child["status"] in ("warn", "fail") and any(
                    f["rule"] == finding["rule"] and f["message"] == finding["message"]
                    for f in child["findings"]
                )

            receipt["scratch_replay_runs"] = 1
            replay = analyze(current)
            if _minimization_terminal(result, replay, receipt):
                return result
            if not retains(replay):
                metadata["minimization"] = {
                    **receipt,
                    "status": "unreproducible_in_scratch",
                    "error": replay["summary"],
                    "failed_child": replay,
                }
                return result

            limited = False
            failed = None
            while True:
                tree = ast.parse(current)
                lines = current.splitlines(keepends=True)
                changed = False
                for node in tree.body:
                    first = min(
                        [
                            node.lineno,
                            *(d.lineno for d in getattr(node, "decorator_list", [])),
                        ]
                    )
                    trial = "".join(lines[: first - 1] + lines[node.end_lineno :])
                    if not trial.strip():
                        continue
                    try:
                        ast.parse(trial)
                    except SyntaxError:
                        receipt["invalid_trials"] += 1
                        continue
                    if receipt["analysis_runs"] >= max_reduction_runs:
                        limited = True
                        break
                    receipt["analysis_runs"] += 1
                    child = analyze(trial)
                    if _minimization_terminal(result, child, receipt):
                        return result
                    if child["status"] == "error" or child["status"] == "skipped":
                        failed = child
                        break
                    if retains(child):
                        current = trial
                        changed = True
                        break
                    receipt["rejected_runs"] += 1
                if failed is not None or limited or not changed:
                    break
            if failed is not None:
                metadata["minimization"] = {
                    **receipt,
                    "status": "unreproducible_in_scratch",
                    "error": failed["summary"],
                    "failed_child": failed,
                }
                return result
        if live_source.read_bytes() != live_original or any(
            PhysicalRoot(root).open_contained(name, "read").read_bytes() != data
            for name, data in live_configs.items()
        ):
            return _lint_invalid("source/config changed during reduction")
        reproducer = _publish_lint_reproducer(
            root, relative, original, current.encode("utf-8"), configs
        )
        metadata["minimization"] = {
            **receipt,
            "status": "budget_limited" if limited else "one_deletion_minimal",
            "source": current,
            "reproducer_path": str(reproducer),
        }
        return result
    except (
        ContainmentError,
        StagingInputError,
        OSError,
        UnicodeError,
        ValueError,
        SyntaxError,
    ) as exc:
        return _lint_invalid(str(exc))
```
No undefined trial runner. Each `analyze` invokes actual shared adapter with
exact selected scratch target/config/cwd, preserving owner/run IDs. First
mandatory replay excluded from deletion budget, recorded separately
`scratch_replay_runs=1`; ordinary lint excluded from both counters. Actual
trial error/skipped ends reduction with actual child summary and no publication.
Before replay rejection or trial handling, cancellation execution.disposition
and timeout terminal_reason stop reduction with no artifact. Cancellation
minimization is skipped/reason cancelled; timeout is error/reason timeout.
minimization.last_run retains complete actual child ToolResult; actual
metadata.execution propagates when supplied. Ordinary status/findings/scope
remain intact; summary appends actual child summary/cause. Ambient CancelScope.hit
belongs to existing runtime scope, never an invented ToolResult field. Config
errors retain unreproducible_in_scratch with actual failed_child. No retry,
receipt manufacture or isolation claim.
Proposed executable test `test_minimize_terminal_child_preserves_runtime_evidence`
above runs actual run_engine with controlled adapter exceptions for replay/trial.
It verifies canonical child carrier and ambient hit, not physical termination.
Run after implementation:
```bash
env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_lint.py -q -k terminal_child_preserves_runtime_evidence
```
Expected four cases pass, no publication, ordinary findings/status/scope retained,
counter pairs (0,1)/(1,1), actual last_run/execution and cancellation cause copied.
Existing T17 real-child termination test remains separate required regression.
Runtime reference: _cancelled_engine_result and run_engine, plus existing
tests/test_subprocess_contract.py cancellation regressions in global check union.

Counter correction: report fixture with four top-level statements yields six
deletion analyses, four rejected, zero AST-invalid; first replay adds one
`scratch_replay_runs`. Complete last pass at budget6 is minimal; pending candidate
at budget2 is limited. Invalid shared-line deletion counts before budget check
without Ruff spawn. Decorator's first physical line included.

Proposed checks:
`test_minimize_complete_pass_at_exact_budget_is_minimal`,
`test_minimize_skips_syntactically_invalid_deletion`,
`test_minimize_decorated_span`, `test_minimize_budget_limited`,
`test_minimize_trial_error_retains_original`, `test_minimize_source_drift_rejected`.
Concrete expected fixtures and bodies in Q02-08; real Ruff required, future checks
unexecuted. Ruff-only operation has no F4/F5/live OCI prerequisite.


Verification requirement: original report Q02-M2 at line 3315; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-M3: Minimizing a Globstar finding is undefined



Complete proposed `tests/test_lint.py` body:
```python
def test_globstar_minimization_isolation_unavailable(tmp_path, monkeypatch):
    import rush.tools.common as common
    import rush.tools.lint as lint_module
    from rush.engines.globstar import GlobstarEngine

    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    original = target.read_bytes()
    real_on_path = common.engine_on_path
    monkeypatch.setattr(
        common,
        "engine_on_path",
        lambda name: True if name == "globstar" else real_on_path(name),
    )
    monkeypatch.setattr(lint_module, "engine_on_path", lambda name: name == "globstar")
    monkeypatch.setattr(
        "rush.engines.globstar.resolve_binary", lambda name: "/bin/globstar"
    )
    monkeypatch.setattr(GlobstarEngine, "version", lambda self, **kwargs: "fixture")
    calls = []
    output = json.dumps(
        [
            {
                "file": str(target),
                "line": 1,
                "column": 1,
                "pattern_id": "fixture",
                "severity": "warning",
                "message": "fixture pattern",
            }
        ]
    )

    def execute(argv, **kwargs):
        calls.append(list(argv))
        return CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr("rush.engines.globstar.run_subprocess", execute)
    result = LintTool().run(
        target,
        minimize_finding="globstar/fixture@a.py:1",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert len(calls) == 1
    assert result["metadata"]["minimization"] == {
        "status": "skipped",
        "reason": "isolation_unavailable_for_non_ruff",
        "analysis_runs": 0,
    }
    assert [(f["rule"], f["provenance"]) for f in result["findings"]] == [
        ("globstar/fixture", "lint/globstar")
    ]
    assert target.read_bytes() == original
    assert not (tmp_path / ".rush").exists()
```
Adapter normalization/provenance and LintTool dispatch remain real; only external
Globstar process output is controlled. No reduction trial/replay/artifact write.
Proposed command: `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev
python -m pytest -p no:cacheprovider tests/test_lint.py::test_globstar_minimization_isolation_unavailable
tests/test_lint.py::test_eslint_minimization_isolation_unavailable -q`; both
ordinary findings preserved and exact non-Ruff block above.


Verification requirement: original report Q02-M3 at line 3339; implementation-dependent commands unexecuted, require proposed source/new tests. Plan-only structural/contract verification is ledgered below; it does not replace behavioral acceptance.

### Q02-M4: The documentation coverage receipt and `sync_docs.py --check` are not part of the plan


Concrete Foundation Q02-DOC-receipt row, same packet AFTER named behavior checks
pass. Reuse revised Q01-M1 sync_docs.BLOCK_RE/build_document_inventory/
document_digest/collect_runtime_contracts mechanism; no new validator.
Planning corpus already transferred/frozen/registered by Q01-M1 prerequisite
packet; missing/unknown new doc blocks regeneration.

Execute body from Phase70 root with
`rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -`:
```python
import importlib.util
import json
import sys
from pathlib import Path

root = Path(".").resolve()
spec = importlib.util.spec_from_file_location(
    "sync_docs", root / "scripts/sync_docs.py"
)
assert spec is not None and spec.loader is not None
sd = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sd
spec.loader.exec_module(sd)
report = root / sd.REPORT_PATH
text = report.read_text(encoding="utf-8")
match = sd.BLOCK_RE.search(text)
assert match is not None, "coverage receipt block missing"
receipt = json.loads(match.group("payload"))
previous = {entry["path"]: entry for entry in receipt["documents"]}
new_adr = "docs/adr/0052-lint-coverage-baseline-and-minimization.md"
evidence = [
    "tests/test_lint.py::test_selected_files_once_and_partial_engine",
    "tests/test_lint.py::test_baseline_delta_preserves_full_result",
    "tests/test_lint.py::test_minimize_artifact_retention_and_collision",
    "tests/test_lint.py::test_lint_cli_stdio_options_and_denial",
]
documents = []
for mechanical in sd.build_document_inventory(root):
    relative = mechanical["path"]
    if relative not in previous and relative != new_adr:
        raise ValueError(f"Unowned new documentation: {relative}")
    old = previous.get(relative, {})
    if old.get("immutable_body_sha256") is not None:
        if old["immutable_body_sha256"] != mechanical.get("immutable_body_sha256"):
            raise ValueError(f"Historical body changed: {relative}")
    entry = {**old, **mechanical}
    if relative == new_adr:
        entry.update(audience="maintainers", authority="current", evidence=evidence)
    documents.append(entry)
receipt["documents"] = documents
receipt["contracts"] = sd.collect_runtime_contracts(root)
payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
report.write_text(
    text[: match.start("payload")] + payload + text[match.end("payload") :],
    encoding="utf-8",
)
```
Existing audience/authority/evidence retained; new ADR owns exact evidence.
Mechanical hashes/source-state/referrers regenerated; historical body digests
must match before write. Leading-status-only historical changes allowed.
Check `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python
scripts/sync_docs.py --check` must exit0 after options/docs/runtime exist.
Unexecuted here; syntax validation cannot prove documentation parity.

## Checks to run before reporting

Implementation checks below are proposed and unexecuted during remediation.
Run from accepted Phase70 implementation checkout after packet production/test
prerequisites exist. Version must be Python3.12. Clear inherited PYTHONPATH.

Pass criterion: zero failures except these five reported 66c6c79 baseline nodes;
each allowed failure must fail identically before and after the packet. New or
changed failures never enter this list. Zero SKIPPED; unavailable environment
markers may be deselected under existing conftest policy.

- tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[core]
- tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[full]
- tests/test_no_skips.py::test_no_collected_test_carries_a_live_skip_marker
- tests/test_phase70_t12.py::test_t12_pyrefly_argv_no_directory_arg_when_explicit_files
- tests/test_phase70_t12.py::test_t12_typecheck_config_routes_python_family

Exact X13 + C20 + changed-packet regression union:

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_lint.py tests/test_engines.py tests/test_tools.py tests/test_language_routing.py tests/test_phase70_t9.py tests/test_phase70_t13.py tests/test_phase70_t16.py tests/test_phase70_result_trust.py tests/test_transport_parity.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase60_characterization.py tests/test_phase60_refactor.py tests/test_phase60_complexity_thresholds.py tests/test_ruff_reference.py tests/test_eslint_reference.py tests/test_globstar_reference.py tests/test_phase70_t5.py tests/test_capabilities.py tests/test_phase70_engine_applicability.py tests/test_full_project_scan.py tests/test_dashboard_map.py tests/test_project_run_lifecycle.py tests/test_routing.py tests/test_subprocess_contract.py tests/test_sync_docs.py tests/test_catalog.py tests/test_phase70_t17.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy git diff --check
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider -q
```

Every packet command and named assertion remains required, including F1
test_command_tools_reject_unknown_arguments,
test_command_tools_preserve_transport_options,
test_command_tools_reject_non_boolean_grants and
test_tool_cli_options_forward_typed_values. F6 real CLI/stdio parity uses one
helper and real error-log files; statuses map to exits0/1/2.

X13 lists tests/test_isolated_process.py for the shared provider. C17 excludes
that provider-created module until F4 exists; if Foundation has integrated it,
include it in the regression union and full-suite gate. Its live OCI acceptance
remains Foundation-owned. Q02's Ruff-only X1 never requires F4/F5, an OCI image
or an OCI CI job. Do not fabricate missing provider-module success.
D8 selection remains unapproved; a different approved target changes both
command and acceptance uniformly.

## Failure and recovery

Invalid schema/identity/containment rejects unsafe operation. Grant/runtime/
engine absence explicit branches, never fallback. Preserve ordinary findings
where binding contract requires. Persistent artifacts only specified paths;
clean invocation-owned scratch only. Partial apply factual changed paths/hashes,
never rollback. Drift invalidates prior receipts. Unapproved decisions block
dependent implementation choice, not remediation.

## Completion

Current deliverable only this plan. Implementation completion requires full
R/E/X behavior, named tests, exact real CLI/stdio parity,
docs gate, frozen hash and declared-path diff. Literal Command-owner paths
Deliverables above; every shared file via Q02-<packet> or
Q02-DOC-<subject> exact Foundation row. No next batch/commit/push authorized.

## Handoff

One authoritative plan, no auxiliary runner/report. Receipt includes hash,
finding IDs/status, exact verification/results and unresolved James decisions/
external prerequisites. No future behavior PASS from plan static checks.

## Remediation acceptance ledger

Current grounding: Phase70 HEAD66c6c799eaa5b6017776d659e9e0de2b4a8878a5;
audit c78e445 remains historical. Graft/source evidence used for LintTool,
runtime main/probe/staging, participating adapters, containment, permissions,
catalog and documentation contracts. These are source observations, not future
implementation acceptance. All production patches and behavioral tests below
remain proposed and unexecuted.

| Finding | Concrete disposition and corrected section | Source/contract evidence | Exact required behavior evidence |
| --- | --- | --- | --- |
| Q02-01 | Repair: Q02-01/25 assembler uses canonical engines/scope and absolute assessed_paths; clean partial keeps D5 warn proposal | Phase70 lint.py::LintTool.run; routing.aggregate_status/aggregate_scope | Partial Ruff ok + ESLint skipped => warn, scope partial, ESLint paths []; D5 approval; proposed/unexecuted |
| Q02-02 | Repair: Q02-02 forwards selected_targets through main call and coverage probe; empty vector guard | runtime/subprocesses.py::run_engine main/probe split | Selected file once, no root, show-files identical vector/config/cwd; [] zero adapter calls; proposed/unexecuted |
| Q02-03 | Repair: Q02-03 maps selected files without changing four-tuple; logical consumed paths retained | _staged_invocation and staging.substitute_arg | Staged argv contains staged file; assessed_paths original logical file; proposed/unexecuted |
| Q02-04 | Repair: Q02-04 keyword introspection and optional selected_targets only participating engines | Engine.run abstract API; participating adapter run signatures | Legacy adapter receives no new keyword; None retains legacy args; proposed/unexecuted |
| Q02-05 | Repair: Q02-05 exact selected vector replaces root positional argument | Globstar adapter argv construction | Globstar selected file once, root absent; proposed/unexecuted |
| Q02-06 | Repair: Q02-06 records deviation: typed selected_targets instead of reusing args as file carrier | Audit Q02 argv proposal vs current runtime/config staging | Caller flags preserved; staged exact paths and scope probe consistent; proposed/unexecuted |
| Q02-07 | Repair: Q02-07 preserves audit test name with executable deterministic adapter body | Audit named Ruff accepted-path check | Real LintTool selects matched Python file and asserts exact argv; proposed/unexecuted |
| Q02-08 | Repair: Q02-08 runnable tests for status/shape/scope/baseline/grants/minimizer/parity | Report scenarios and current LintTool transport routes | Concrete fixtures assert exact outputs; prerequisites explicitly ordered; proposed/unexecuted |
| Q02-09 | Extension: Q02-09 validates contained baseline and lint identity before read | PhysicalRoot.open_contained returns Path; ToolResult baseline JSON | Escape/non-lint/malformed input => metadata.error.code invalid_argument, no unsafe read; proposed/unexecuted |
| Q02-10 | Extension: Q02-10 derives engine/version from child provenance; POSIX path and source_digest identity | Finding fields/extensions; Engine metadata | Same finding/source unchanged; changed source new/resolved; full findings retained; proposed/unexecuted |
| Q02-11 | Extension: Q02-11 hashes verified config closure + args; incomplete closure unassessed | Ruff ancestor/extend configs and JS executable config gaps | Changed contained extend bytes differ; unresolved closure never comparable; proposed/unexecuted |
| Q02-12 | Expansion: Q02-12 validates unique rule@root-relative-posix-path:line | Ruff finding rule/path/location | Missing/ambiguous/unsupported/outside-root selector rejected before scratch/artifact; proposed/unexecuted |
| Q02-13 | Expansion: Q02-13 writes source and config layout under original digest16 path | Report digest16 retention and atomic_write_bytes | Original unchanged; conflict rejects; identical artifact bytes no-op; proposed/unexecuted |
| Q02-14 | Expansion: Q02-14 strict budget validation and optional-operation denial preserves ordinary result | ExecutionPermissions and report OWNER DECISION FLAG | No grants => denied/not_run, zero reduction/writes; invalid budget => canonical error; cap approval; proposed/unexecuted |
| Q02-15 | Repair: Q02-15 canonical invalid-argument envelope; no metadata.reason substitute | child_entry extracts metadata.error.code | CLI error exit2 and strict MCP pre-dispatch INVALID_REQUEST remain distinct; proposed/unexecuted |
| Q02-16 | Expansion: Q02-16 Ruff adapter scratch route; other engines structured skipped | Audit Ruff-only minimizer; Foundation F4/F5 separate | ESLint/Globstar analysis_runs0 reason isolation_unavailable_for_non_ruff; no OCI dependency; proposed/unexecuted |
| Q02-17 | Extension: Q02-17 exact typed options/default12 and Foundation option row | _TOOL_CLI_OPTIONS; wrapper public_sig strict flat F1 | CLI typed forwarding and strict MCP flat fields/unknown keys before dispatch; proposed/unexecuted |
| Q02-18 | Preservation: Q02-18 + final Checks union packet/shared regression modules; explicit five baseline nodes | X13/C19/C20 and current Phase70 test paths | Before/after identical only named baseline failures; zero SKIPPED; no fabricated PASS; proposed/unexecuted |
| Q02-19 | Extension: Q02-19 literal doc text/ADR0052 and Foundation patch rows | sync_docs.py historical body and coverage receipt contract | sync_docs --check plus immutable historical-body digests; proposed/unexecuted |
| Q02-20 | Extension: Q02-20 grounded catalog engine claims and actual scanner selection consequences | Lint selector/engine_names/discovery/capabilities | Capabilities reflect configured eligible engine, not claimed execution; proposed/unexecuted |
| Q02-21 | Expansion: Q02-21 worked before/after reproducer with inputs/state/new operation/commodity comparison | Audit requirement assessment categories | Exact selector, digest16 artifact, counters and factual limit; proposed/unexecuted |
| Q02-22 | Preservation: Q02-22 fully specified task sections; remove only stale report-edit/override instructions | Local task-block schema; stale review-editor text | Defined helpers/imports/fixtures/file ownership, no TODO or signature-only substitute; proposed/unexecuted |
| Q02-23 | Repair: Q02-23 explicit selected vector, deletion-trial counters and separate scratch_replay_runs | Report analysis_runs definition and fixture6/4/0 | Replay excluded from deletion budget; errored/rejected trials count; AST invalid no run; proposed/unexecuted |
| Q02-24 | Preservation: Q02-24 literal command paths vs exact Foundation shared rows | C16 Foundation sole shared-file writer | No overlapping runtime/catalog/parity/doc writes; proposed/unexecuted |
| Q02-25 | Repair: Q02-25 assembler retains N issue(s), scope and actual skip cause | Audit issue-count/partial-reason summary contract | Empty partial summary not success over unassessed files; counts retained; proposed/unexecuted |
| Q02-26 | Expansion: Q02-26 retained minimization metadata with explicit naming reconciliation | Audit/report minimizer evidence naming | Rule/path/digests/config/counters present; no false minimal claim; proposed/unexecuted |
| Q02-M1 | Expansion: Q02-M1 mandatory scratch replay before deletion; failure no persistent artifact | Ruff extend scratch config behavior | Missing extend => unreproducible_in_scratch, analysis_runs0, scratch_replay_runs1, original unchanged; proposed/unexecuted |
| Q02-M2 | Expansion: Q02-M2 full decorated deletion, invalid AST count and final-pass completion flag | AST decorated-node spans and audit budget-label defect | Complete pass at exact budget => one_deletion_minimal; unfinished => budget_limited; terminal cancellation/timeout retains actual last_run/execution and forbids publication; proposed/unexecuted |
| Q02-M3 | Expansion: Q02-M3 explicit non-Ruff skip preserves ordinary lint | Globstar findings unsupported by Ruff reduction | Globstar finding remains, analysis_runs0, no scratch artifact; proposed/unexecuted |
| Q02-M4 | Preservation: Q02-M4 coverage regeneration + exact documentation gate | Phase70 docs coverage receipt/sync_docs check | Current entries cover ADR0052; historical body unchanged; proposed/unexecuted |

| Shared finding/override | Corrected section | Substantive disposition and acceptance |
| --- | --- | --- |
| X-01 | Phase70 reconciliation | 66c6c799 is implementation base; c78e445 historical audit only; T1–T29/G0–G8 acceptance evidence required |
| X-02 | Required behavior 2; Q02-01/25 | Canonical engines/scope/assessed_paths and shared aggregate_status; no lint-local metadata forks |
| X-05 | Deliverables; Q02-24 | Foundation sole shared writer; exact command paths and serialized patch rows |
| X-06 | Q02-17 | Typed _TOOL_CLI_OPTIONS lint; existing permission options only; wrapper public_sig |
| X-07 | Q02-14/17 | StrictBool public grants build ExecutionPermissions once; run(permissions) |
| X-08 | Q02-09/14/15/16 | Canonical denial/invalid/empty-scope vocabulary; optional denial preserves base |
| X-10 | Required behavior 5; Q02-23 | Unique selector, counters, replay and W18 glossary precisely distinguished |
| X-11 | Q02-22; top-level template sections | Concrete required behavior/deliverables/constraints/checks/completion; no absent draft instructions |
| X-12 | Checks; packet prerequisites | New test_lint.py and F6 modules created before gates; Python3.12 dev environment explicit |
| X-13 | Checks; Q02-18 | Exact union plus full suite, mypy/sync_docs/diff; conditional proposals remain unexecuted |
| X-14 | Q02-07/08; F6 | One Foundation transport helper; real CLI/stdio/error-log checks and exits0/1/2 |
| X-15 | Q02-19/M4 | Exact doc text and F8 serialized rows; immutable historical body retained |
| X-16 | Q02-20; F1/F9/F10 | Catalog/scanner/capability consistency and strict forwarding preserved; requested user baseline retained |
| X-17 | Intro; Ordered tasks; reconciliation | Frozen audit/report/Phase70 inputs; copy byte-identically under separate implementation authorization |
| X-18 | Decisions; Q02-22 | Copied Q01 decisions/OCI dependencies removed from Plan02 requirements; only grounded Q02 content |
| M1 | F2 reference; Q02-01 | Existing lint scope preserved; security-specific child overwrite belongs Foundation/security |
| M2 | Q02-18/19/M4; Checks | CI/doc gates and same-packet timing included |
| M5 | Q02-01/25; Checks | D5 default ok+skipped=warn; CLI exit1 conditional on James ratification |
| M7 | Phase70 reconciliation; Q02-02–06/20 | Current engine implementations retained; only source-grounded repairs/additions |
| C-01 | Q02-01/25 | engines/scope plus absolute logical assessed_paths; skipped child []; workflow/runtime metadata retained |
| C-02 | Q02-01/22 | Shared D5 only; obsolete local-skipped proposal removed |
| C-10 | Q02-14/17 | Existing/new run permissions convention; no permission rewrite |
| C-11 | Q02-14; Foundation F3 | Denied minimization reason build_or_slow_denied; execution executed/not_run; original status/findings/scope; zero denied effects |
| C-13 | Q02-09/14/15 | metadata.error.code invalid_argument and message summary; predispatch raw INVALID_REQUEST distinct |
| C-14 | Q02-17; F1 | Flat public_sig strict model, StrictBool grants, transport fields preserved |
| C-15 | Q02-19/20; F10 | Discovery catalog single source, short20–199 MCP description |
| C-16 | Deliverables; Q02-24 | Foundation shared runtime/catalog/parity/docs; Q02 Ruff-format Q03-M2 after R1 |
| C-17 | Ordered tasks; Checks | No Q02 OCI prerequisite; provider-only test modules excluded until created; broader OCI consumers retain live CI gate |
| C-18 | Checks; D8 | mypy src/rush proposal per current CI; alternative requires uniform update |
| C-19 | Checks | Exactly five reported baseline nodes; identical before/after failures only; zero SKIPPED |
| C-20 | Checks; Q02-18 | Union X13/Q02/report/packet module lists, never narrower substitution |
| C-22 | Q02-19/M4 | ADR0052 exact basename; ADR index only leading Current status plus receipt regeneration |
| C-23 | Q02-19/24 | F8 sole shared docs writer; immutable ADR0007 body never rewritten |
| C-24 | Q02-22; reconciliation | No unapproved readiness from Status label; source and acceptance gates separated |
| C-27 | Q02-01/07/08/14; Foundation F2 | Attach canonical internal child scope from actual consumption, overlay aggregate fields while retaining specialized facts; unavailable engines differ from empty targets; clean partial consumption warns with actual excluded-path reason. test_lint_clean_show_files_omission_is_partial and test_lint_missing_engines_vs_unsupported_scope require exact state; nested runtime ledger remains intact. |
| C-29 | Q02-17; Foundation F1 | test_command_tools_reject_unknown_arguments before dispatch for lint; wider D12 remains Foundation decision |
| Q03-M2 | Q02-02 and Ruff adapter packet | Ruff format selected_targets branch consumes files; None retains args[2:]; no Q03 edit |

Reference-only dispositions: X-03/X-04/X-09 and C-03/C-05/C-06/C-07/C-08/
C-09/C-12 are F4/F5/OCI contracts for other consumers. Their preserved reference
signatures/vocabulary align revised Foundation/Plan01; none becomes a Q02
runtime/image/selected-test prerequisite. Shared M1 security-specific correction
belongs Foundation/security; Q02 preserves lint scope. Shared M3/M4/M6 concern
Q06 isolation, Q07 plugin and typecheck config respectively, excluded from Q02.
C-04 Q10 timeout, C-21 Q08 line citations, C-25 Q07 boilerplate, C-26 Q08
ownership and C-28 Q06 isolation are outside Q02. C-29 wider strict-model choice
D12 remains Foundation-owned; lint's unknown-key rejection is explicitly required.

Binding reconciliation: default budget12 verified in audit and Q02-17 report.
Report cap1..100 is an unapproved owner choice; old1..128 removed. Digest16
artifact layout follows Q02-13/21; unsupported UUID residue removed. Mandatory
first scratch replay is counted separately as scratch_replay_runs=1, not a
deletion trial. Q02-M1 old analysis_runs1 assertion becomes analysis_runs0 on
replay failure. Report Q02-23 deletion fixture remains6/4/0. This corrects
counter ambiguity while retaining exact audit trial budget and total-run truth.

Plan remediation and development readiness are distinct. No implementation
acceptance is claimed. Development starts only after James ratifies D3 grant
convention, D5 aggregation, D8 mypy target and the proposed max_reduction_runs
cap, and supplies Phase70 T1–T29/G0–G8 acceptance evidence. Source revision and
clean Git do not prove that acceptance. Foundation F1/F2/F3/F6 ordered
prerequisites have concrete implementations in revised Plan00; accepting their
implementation is required before dependent Q02 packets. F4/F5 are not needed.
Next boundary: James reviews Plan02; no other plan execution authorized.

## Plan-only reconciliation receipt

Authorization/output: only
/Users/jamesdsizemore/Developer/rush-cli/docs/phase-plans/command-tdd-2026-10-01/02-rush-lint.md,
Markdown remediation. No production/test/config edits, implementation, other
plan edits, commit or push.

Baseline Plan02 SHA256:
94eaa787d58e1e202ebb9c94bf38ac3627b3d2119f163be92df3c1464f9049d0.
Source baselines: main c78e445ba1e575ca373e35840142cd627b055d6a;
Phase70 66c6c799eaa5b6017776d659e9e0de2b4a8878a5. Main's pre-existing
AGENTS.md change and untracked inputs remain user-owned and unchanged.
The final frozen whole-file hash accompanies the review handoff.

Plan-only checks: balanced61 code fences;35 dedented Python source/insertion
fragments AST-parse successfully. Dedenting validates insertion syntax only,
not imports, placement, runtime behavior or implementation acceptance.
Author checked changed Python fences with Ruff formatting and retained prior
unchanged-fence evidence. git diff --check passed; target is untracked, so
independent content fingerprints establish its boundary.

Preservation: all18 prior named test bodies remain represented; their count is
inventory evidence only. Author preserved exact outside-region bytes; coordinator
preserved author region SHA256
9a6a971d22697da3be935bc962906271f9a55f8c5aae7a230c610291f5e324af
during integration. Protected main tree1633 files SHA256
8454fd186a4032343ff07885ab05187aa372a701af4cc6002d8e39ec8434a64b;
Phase70 tree1615 files SHA256
b437d5e0308a9b5c2a5cd750488a2429f2b0ac052eab63a2aaaec15f4fbff224.
HEAD/status and all11 other plan/index hashes match baseline, including revised
Plan00/01 hashes stated in reconciliation. Coverage decisions and alignment
are integrated in this one plan; no companion artifact.

Development readiness: blocked by unratified D3/D5/D8 and proposed cap1..100,
plus Phase70 T1–T29/G0–G8 acceptance evidence. These are external entry decisions/
evidence, not missing packet authoring. Foundation prerequisites have an ordered
concrete route. Implementation acceptance: none during this Markdown task.
Next boundary: James reviews this Plan02; another plan needs explicit authorization.
