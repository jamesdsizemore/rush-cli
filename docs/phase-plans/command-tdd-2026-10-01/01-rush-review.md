Implement Q01 full scope in rush-cli when implementation authorized.
Read AGENTS.md, docs/templates/task-block-template.md, README.md,
00-shared-foundation.md and exact audit/report first.

# Feature: Permission-safe source-bound review with isolated counterexamples

Authorization: plan remediation only; production patches/tests below proposed,
unimplemented/unexecuted here. No commit/push/release.
Source revision: 66c6c799eaa5b6017776d659e9e0de2b4a8878a5.
Audit source c78e445ba1e575ca373e35840142cd627b055d6a only.
Binding audit docs/reports/cli-mcp-command-audit-2026-09-26.md, SHA256
8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Binding report docs/reports/command-tdd-2026-10-01-plan-remediation.md:
Q01, applicable X/M and C01–C29 (binding C overrides).
Current remediation: Plan 01 alone. Plans 02–10 remain unchanged until James
reviews this document and authorizes another plan. Prior GPT6.1 Sol/high agent
work remains proposed implementation content.

## Goal, scope and non-goals

Repair empty assessment and unauthorized model calls. Preserve heuristics,
Graft and changed-file containment. Separate repairs, ordinary evidence
extension and behavioral-counterexample expansion. No production edits during
planning, model-supplied executable source, installation, release change,
commit, push, or implementation of downstream W18. Connected specialists are
user-requested baseline, not counted as this command's novel expansion.
Shared baseline also preserves scanner provisioning, connected specialist local
models, selectable voice/live speech and the 3D companion. Shared integration
owns their applicable provider/permission contracts; these requested features
cannot be relabeled command innovation or silently removed from project scope.

## Evidence and requirement ledger

Current source: Phase 70 at 66c6c799eaa5b6017776d659e9e0de2b4a8878a5.
Audit revision c78e445 remains historical grounding.

| ID | Literal requirement | Current source/reconciliation | Acceptance |
| --- | --- | --- | --- |
| R1 | Empty Python scope: skipped, assessed_files=0 | review/results.py:29–56,168–186: keep scope v1, add audit fields | test_empty_python_scope_skipped and both test_tools empty-scope cases |
| R2 | Denied network: zero provider calls, retained heuristics/memory | review/llm.py:121–134 hardcodes grant; tools/review.py:256–312 has no permissions input | test_llm_network_denial_preserves_heuristics plus provider/transport cases |
| R3 | Fresh import orders and ordered registrations preserved | Phase 70 already fixes the cycle; lazy registry remains D7 | test_review_import_orders and existing test_import_order regressions |
| E1 | Digest-bound claims, current scope/citations, prior invalidation | New 12-key schema supplements existing findings | test_claim_source_digest_invalidation, changed_files and citation tests |
| X1 | Data-only counterexample under real OCI isolation | Specialist request and F4 provider do not exist at this base | test_probe_claim_counterexample in OCI CI and zero-call rejection tests |

## Required behavior

1. Empty Python scope => skipped, assessed_files=0,
   unassessed_reason=no_python_targets beside unchanged scope v1 coverage none,
   reason no_reviewable_python_files; update two existing test_tools expectations.
2. use_llm denied network => zero provider calls, preserved heuristics/memory
   attribution, review_kind heuristic, metadata.llm skipped/permission_denied.
   Granted calls retain approved-origin/completed-response checks; specialist
   calls patchable module review_llm.request_probe_candidate.
3. Fresh imports preserve Phase70 56-tool registry order, no Git-history lookup.
   Existing cycle fix is regression; lazy import contract conditional on D7.
4. Exact 12-field source-bound claims, contained 1 MiB UTF-8 JSON arrays;
   citation_ids from evidence.memory_artifact_id only. changed_files limits
   claims. Prior source changed/missing/outside scope invalidates old receipt.
5. Probe only current supplied return_predicate. Grants and F4 no-launch input
   check precede specialist. Imported fixed harness constant verifies module
   __file__, passes JSON args, exact eq/ne/ge/gt/le/lt predicate in OCI.
   False => falsified, true => not_falsified and unverified; source drift =>
   stale_source; process/receipt errors => error. Preserve factual IsolatedRun or
   exception receipt, launch count and cleanup evidence when supplied. Confirmed
   cancellation => skipped with execution.disposition=cancelled and original
   findings/scope retained; unconfirmed cleanup => error, never unavailable.
## Phase70 reconciliation and shared contracts

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

W18 = audit Command 45/79 rush_mem_profile isolation contract 13810–13889;
Foundation F4 implements provider under README D1. IsolatedRun has returncode,
stdout,stderr,process_launches,receipt. Signature:
run_isolated_argv(root,scratch,*,runtime_path,image_ref,entrypoint,argv,
timeout_s,workdir_rel=".",environment=None,max_process_launches=None,
scratch_on_pythonpath=False).
LaunchBudgetExhausted.process_launches counts accepted host child starts before
next refused, including an owned bootstrap (F4-START); it does not attest a
container target or transient runtime executable. F4 owns the private
run_subprocess start_evidence patch and tests/test_subprocess_contract.py gate;
accept that prerequisite before Q01's unchanged provider call signature.
runtime_path absolute-only, never CLI abspath or _CWD_RELATIVE_ARGS.
F4 check_isolation_inputs(root,*,runtime_path,image_ref) launches nothing;
runtime errors raise IsolationUnavailable first, malformed image ValueError
second. D10 runtime proposal supplied docker/podman final name, symlink target
name irrelevant, resolved regular executable owned root/current user, no
group/world write, supplied directory and realpath outside root, POSIX.
Provider read-only source/private writable scratch, no network, capability/
privilege/resource/time/output bounds, owned cleanup and factual receipts.
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
checks exclude provider-created modules until F4; X1 requires live OCI CI PASS.
ToolSpec.discovery single source in catalog, CLI help and MCP path schema;
mcp_description remains 20–199 chars with Phase70 phrases.

Shared requested baseline remains full scope: scanner provisioning, connected
specialist local models, selectable voice/live speech, 3D companion. Never
count these as command innovation.

## Decisions for James

Applicable README D1–D12 choices remain unapproved; report defaults in code
are conditional proposals, not decisions. D3 permissions, D5 aggregate warn,
D8 mypy src/rush apply to all three. Q01/Q03 also D1,D2,D6,D10,D11; Q01 D7;
Q03 D4 timeout=300 versus 180. Change all dependent code/tests/docs uniformly
after decision. Do not implement dependent choices silently.
Q01 claim-model decision: audit derives behavioral claims from heuristics;
proposal adds supplied return_predicate contracts, keeps every audit field plus
kind/predicate, makes heuristic_observation unprobeable. James must confirm or
replace before E1/X1. Current contract outside changed_files rejects
invalid_claim_input, prior outside scope invalidates; confirm that decision.
D7 regression-only option cannot claim lazy registry acceptance: choose actual
lazy split or explicitly reconcile acceptance, retaining import/order guarantees.

## Constraints

Planning-only current authorization. No production/test/shared-doc writes,
commit/push/release/version/hook/install. Source and tests below proposed,
unimplemented/unexecuted here. Preserve unrelated user edits. Reuse adapters,
PhysicalRoot.open_contained (returns Path), atomic_write_bytes, grants/routing.
No invented API/model executable source/local isolation fallback/simulated PASS.
R/E/X each needs own evidence; repair PASS never closes extensions/expansion.

## Deliverables

Command owner literal paths: src/rush/tools/review.py;
src/rush/review/llm.py; src/rush/review/results.py;
src/rush/review/probe_harness.py; src/rush/providers/base.py;
src/rush/providers/openai.py; src/rush/providers/anthropic.py;
tests/test_review.py; tests/test_tools.py (review cases only);
tests/test_providers.py; tests/test_phase57_provider_egress.py (review grants);
existing tests/test_import_order.py (regression-only).
D7 optional src/rush/tools/__init__.py/registry.py serialization Foundation.
Q01-R2-transport Foundation row: exact handwritten cli.py::review options below,
F1 strict models and tests/test_mcp.py transport bodies; F6 shared helper.
Q01-R2-description row: catalog review last clause external LLM only with
allow_network, mcp instructions explicit grant/no-call, exact three t5 tests.
Q01-M3-paths row: review _CWD_RELATIVE_ARGS only behavioral_claims_path/
prior_claims_path; NEVER runtime_path. Lexical absolute-inside-root conversion
then PhysicalRoot relative open, reject symlinks/../escapes, cap1MiB.
Q01-OCI-marker/CI rows use F4 runtime-only marker, all images/jobs and Q01
RUSH_TEST_PYTHON_IMAGE with /usr/bin/python3 checked inside image.
Command ADR docs/adr/0051-review-source-bound-claims-and-isolated-probes.md;
all exact docs clauses in Q01-19 are Foundation F8 doc patch rows
Q01-DOC-<subject>, including shared reference docs, CHANGELOG and receipt.
Historical ADR bodies untouched, leading Current status only.

## Ordered TDD packets

1. R1/R2: test_empty_python_scope_skipped and
   test_llm_network_denial_preserves_heuristics; both existing test_tools
   empty-scope cases and provider-intending direct callers. Preserve scope v1,
   attach_memory_attribution and approved-origin checks.
2. R3: test_review_import_orders and existing test_import_order regressions.
   The lazy assertion/registry extraction below is D7's lazy option. Its
   alternative preserves import-order regressions without claiming lazy loading.
   Record James's choice before dependent implementation.
3. E1: test_claim_source_digest_invalidation, heuristic eligibility,
   changed_files scope and structured citation tests. Invalid current/prior
   inputs fail before any provider call.
4. X1: provider prompt/request tests and zero-call rejection tests first;
   test_probe_claim_counterexample after F4 and live image acceptance.
   F5 selected pytest is not used by the fixed behavioral harness.
5. Real CLI/stdio tests via F1/F6 and exact F8 documentation rows; freeze,
   run listed implementation checks and reconcile R1/R2/R3/E1/X1 separately.
   This document edit executes none of these implementation packets.

## Runnable RED bodies restored from original plan

Merge these proposed bodies into tests/test_review.py; do not implement them
during plan remediation. Retain existing imports; add hashlib/json/os/
subprocess/sys/Path/pytest as used, ExecutionPermissions and
rush.tools.base.Finding. REVIEW_REPO = Path(__file__).resolve().parents[1].
The command and transport modules each need _review_contract; command tests
must not import tests/test_mcp.py.

```python
def _review_contract(root):
    (root / "src").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    source = root / "src/a.py"
    source.write_text("def f(value):\n    return value\n", encoding="utf-8")
    record = {
        "kind": "return_predicate",
        "path": "src/a.py",
        "module": "src.a",
        "function": "f",
        "source_digest": hashlib.sha256(source.read_bytes()).hexdigest(),
        "predicate": {"op": "ge", "value": 0},
    }
    contracts = root / "contracts.json"
    contracts.write_text(json.dumps([record]), encoding="utf-8")
    return source, contracts, record


def test_empty_python_scope_skipped(tmp_path):
    (tmp_path / "x.js").write_text("const x=1;\n", encoding="utf-8")
    empty = ReviewTool().run(tmp_path)
    assert empty["status"] == "skipped"
    assert empty["metadata"]["assessed_files"] == 0
    assert empty["metadata"]["unassessed_reason"] == "no_python_targets"
    assert empty["metadata"]["scope"]["coverage"] == "none"
    assert empty["metadata"]["scope"]["reason"] == "no_reviewable_python_files"


def test_llm_network_denial_preserves_heuristics(tmp_path, monkeypatch):
    (tmp_path / "x.py").write_text("# TODO repair\nx=1\n", encoding="utf-8")
    calls = []

    def provider(findings, **kwargs):
        calls.append(kwargs["allow_network"])
        return {
            "review_kind": "llm",
            "provider": "fixture",
            "summary": "Reviewed current source",
        }

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", provider)
    denied = ReviewTool().run(tmp_path, use_llm=True)
    assert calls == []
    assert denied["review_kind"] == "heuristic"
    assert denied["metadata"]["llm"] == {
        "status": "skipped",
        "reason": "permission_denied",
    }
    assert any(f["rule"] == "todo-density" for f in denied["findings"])
    granted = ReviewTool().run(
        tmp_path, use_llm=True, permissions=ExecutionPermissions(network=True)
    )
    assert calls == [True]
    assert granted["review_kind"] == "llm"
    assert any(f["rule"] == "todo-density" for f in granted["findings"])


def test_claim_source_digest_invalidation(tmp_path):
    source, contracts, record = _review_contract(tmp_path)
    first = ReviewTool().run(
        tmp_path, claim_evidence=True, behavioral_claims_path=contracts
    )
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps(first["metadata"]["claims"]), encoding="utf-8")
    old = next(
        c for c in first["metadata"]["claims"] if c["kind"] == "return_predicate"
    )
    assert old["symbol"] == "f"
    assert old["source_digest"] == record["source_digest"]
    assert old["status"] == "unverified"
    source.write_text("def f(value):\n    return abs(value)\n", encoding="utf-8")
    record["source_digest"] = hashlib.sha256(source.read_bytes()).hexdigest()
    contracts.write_text(json.dumps([record]), encoding="utf-8")
    second = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        prior_claims_path=prior,
    )
    new = next(
        c for c in second["metadata"]["claims"] if c["kind"] == "return_predicate"
    )
    assert new["claim_id"] != old["claim_id"]
    assert new["source_digest"] == record["source_digest"]
    stale = next(
        c
        for c in second["metadata"]["invalidated_claims"]
        if c["claim_id"] == old["claim_id"]
    )
    assert stale["reason"] == "source_changed"
    assert stale["status"] == "unverified"


@pytest.mark.oci_isolation
def test_probe_claim_counterexample(tmp_path, monkeypatch):
    required = ("RUSH_TEST_OCI_RUNTIME", "RUSH_TEST_PYTHON_IMAGE")
    assert all(os.environ.get(k) for k in required), (
        "Genuine F4 runtime/image prerequisite unmet"
    )
    image = os.environ["RUSH_TEST_PYTHON_IMAGE"]
    assert "@sha256:" in image and len(image.rsplit("@sha256:", 1)[1]) == 64
    assert all(c in "0123456789abcdefABCDEF" for c in image.rsplit("@sha256:", 1)[1])
    source, contracts, record = _review_contract(tmp_path)
    original = source.read_bytes()
    calls = []

    def specialist(findings, **kwargs):
        calls.append(kwargs["allow_network"])
        claim = json.loads(findings[0]["message"])["claims"][0]
        candidate = {
            "claim_id": claim["claim_id"],
            "source_digest": claim["source_digest"],
            "module": "src.a",
            "function": "f",
            "args": [-1],
            "predicate": claim["predicate"],
        }
        return {"review_kind": "llm", "summary": json.dumps(candidate)}

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", specialist)
    result = ReviewTool().run(
        tmp_path,
        behavioral_claims_path=contracts,
        probe_claims=True,
        permissions=ExecutionPermissions(
            network=True, build=True, slow=True, artifact_write=True
        ),
        runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
        image_ref=os.environ["RUSH_TEST_PYTHON_IMAGE"],
    )
    probe = result["metadata"]["probe"]
    assert calls == [True]
    assert probe["status"] == "falsified"
    assert probe["observed"] == -1
    assert probe["input"] == [-1]
    assert probe["predicate"] == {"op": "ge", "value": 0}
    assert probe["source_digest"] == record["source_digest"]
    assert probe["executed_source_digest"] == record["source_digest"]
    assert probe["isolation_receipt"]["exit_code"] == 0
    assert (
        probe["isolation_receipt"]["image_ref"] == os.environ["RUSH_TEST_PYTHON_IMAGE"]
    )
    assert source.read_bytes() == original
```

Source-change test asserts actual digest/claim-ID invalidation. OCI test executes
the fixed harness via F4; provider doubles supply data only. Q01-16 retains
additional branch tests, with denial following C11.

## Concrete implementation packets

Every packet is proposed source/test/doc specification, not an applied patch.
Each section retains its Claude finding ID. Proposed shared-file changes are
Q01 rows applied solely by the Foundation owner. Binding C resolutions govern
conflicts; all source/test changes below remain unimplemented specifications.

### Q01-01: R3 import-order regressions

1. Replace R3 tests/test_review.py::test_review_import_orders with:
```text
R3 lazy option (D7): test_review_import_orders in fresh `python -B` children (a) `import rush.tools`
   leaves `rush.tools.review` and `rush.tools.registry` out of sys.modules
   (D7 lazy-registry option); (b) `import rush.review.results; import rush.tools` and the
   reverse both exit 0; (c) `[type(t).__name__ for t in rush.tools.ALL_TOOLS]`
   equals REVIEW_BASE_REGISTRY in both orders. Implementation base is 66c6c79,
   where (b) and (c) already pass and (a) is the RED. Re-pin REVIEW_BASE_REGISTRY in
   the same commit if development adds a tool before merge.
   GREEN: lazy registry extraction (src/rush/tools/registry.py plus `__getattr__`
   in src/rush/tools/__init__.py).
```
  3. Replace R3 tests/test_review.py::test_review_import_orders with:
```python
REVIEW_BASE_REGISTRY = [
    "ReviewTool",
    "LintTool",
    "FormatTool",
    "TestTool",
    "SecurityTool",
    "TypecheckTool",
    "DeadTool",
    "ComplexityTool",
    "SlopTool",
    "MarkdownTool",
    "ActionsTool",
    "YamlTool",
    "SqlTool",
    "TemplatesTool",
    "ContainerfileTool",
    "IacTool",
    "SecretsTool",
    "SbomTool",
    "CoverageTool",
    "CodeqlTool",
    "E2eTool",
    "SnapshotTool",
    "VisualTool",
    "PbtTool",
    "MutationTool",
    "FlakyTool",
    "ContractTool",
    "FuzzTool",
    "LoadTool",
    "CommitMsgTool",
    "SessionContinuityTool",
    "MemoryTool",
    "CiTool",
    "ReleaseTool",
    "SemanticDriftTool",
    "AiEvalTool",
    "TddGuardTool",
    "FixTool",
    "PatchApplyTool",
    "DoctorTool",
    "AttestationTool",
    "LicenseMatrixTool",
    "IamAuditTool",
    "PromptEvalTool",
    "MemProfileTool",
    "ColdStartTool",
    "MediaOptTool",
    "OfflineReviewTool",
    "TuiDiffTool",
    "BenchmarkTool",
    "ErrorCatalogTool",
    "ProvenanceAiTool",
    "DeadAssetTool",
    "PrSynthesizeTool",
    "CheckTool",
    "StatusTool",
]


def _fresh_child(script):
    return subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=REVIEW_REPO,
        env={**os.environ, "PYTHONPATH": str(REVIEW_REPO / "src")},
        text=True,
        capture_output=True,
        check=False,
    )


def test_review_import_orders():
    lazy = _fresh_child(
        "import sys, json, rush.tools; print(json.dumps(['rush.tools.review' in sys.modules, 'rush.tools.registry' in sys.modules]))"
    )
    assert lazy.returncode == 0, lazy.stderr
    assert json.loads(lazy.stdout) == [False, False]
    for imports in (
        "import rush.review.results; import rush.tools",
        "import rush.tools; import rush.review.results",
    ):
        child = _fresh_child(
            imports
            + "; import json; print(json.dumps([type(t).__name__ for t in rush.tools.ALL_TOOLS]))"
        )
        assert child.returncode == 0, child.stderr
        assert json.loads(child.stdout) == REVIEW_BASE_REGISTRY
```
Regression: test_review_import_orders; actual stdio tools/list registrations and order unchanged.

Concrete D7 lazy option, still conditional on James's choice. Foundation owner
copies the exact existing `src/rush/tools/__init__.py` bytes at the implementation
base into new `src/rush/tools/registry.py`, preserving imports, `ALL_TOOLS` order,
instances and exports. Replace only `src/rush/tools/__init__.py` with:

```python
from importlib import import_module


def __getattr__(name: str):
    if name.startswith("__") and name != "__all__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    registry = import_module(".registry", __name__)
    try:
        value = getattr(registry, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = value
    return value


def __dir__():
    registry = import_module(".registry", __name__)
    return sorted(set(globals()) | set(registry.__all__))
```

`import_module` avoids recursive `from . import registry` calls inside
`__getattr__`. Attribute access loads the single registry and caches the same
object; plain `import rush.tools` loads neither review nor registry. Existing
`__all__` resolves from registry for explicit star imports. Run the proposed
fresh-child test above and existing import-order/CLI/MCP tests. If D7 chooses
regression-only, retain the two ordered-import assertions and omit the lazy
assertion and extraction; record the acceptance difference explicitly.



### Q01-02: R1 empty-scope result and existing expectations

- Replace R1 review/results.py::build_empty_review_result and the two named test_tools cases with:
```text
R1: empty Python scope returns status "skipped" with metadata.assessed_files=0 and
metadata.unassessed_reason="no_python_targets" (audit literal), added beside the
unchanged phase/70 metadata.scope v1 block (coverage "none", reason
"no_reviewable_python_files"). It applies to a directory with no Python file and to
explicit changed_files that select no Python file. summary and findings stay as today.
```
Proposed exact patch to `src/rush/review/results.py::build_empty_review_result`
at Phase 70 `66c6c799`; retain every other field:

```diff
@@
         engine_version=None,
-        status="ok",
+        status="skipped",
         duration_ms=elapsed_ms(start_ms),
         summary=f"review: no Python files found under {path}",
         findings=[],
         raw=None,
-        metadata={"graft": "not-requested", "scope": scope},
+        metadata={
+            "graft": "not-requested",
+            "scope": scope,
+            "assessed_files": 0,
+            "unassessed_reason": "no_python_targets",
+        },
         review_kind="heuristic",
```

  - Add to "Command ownership" after R1 review/results.py::build_empty_review_result and the two named test_tools cases: `- tests/test_tools.py::test_review_skip_on_non_python and ::test_review_preserves_empty_explicit_scope_metadata (existing tests, updated in the same commit).`
  - Update `tests/test_tools.py` in the same commit:
```diff
     result = tool.run(repo)
-    assert result["status"] == "ok"
+    assert result["status"] == "skipped"
     assert result["findings"] == []
+    assert result["metadata"]["assessed_files"] == 0
+    assert result["metadata"]["unassessed_reason"] == "no_python_targets"
```
```diff
-    assert result["status"] == "ok"
+    assert result["status"] == "skipped"
     assert result["metadata"] == {
+        "assessed_files": 0,
+        "unassessed_reason": "no_python_targets",
         "graft": "not-requested",
```


### Q01-03: Clean-review CLI exit code

replace tests/test_mcp.py::test_review_claim_options_cli_mcp_parity with the three lines below. The corrected full body, relocated by Q01-22, is under Q01-22.
```python
assert invocation.exit_code == 0, invocation.output
cli_result = json.loads(invocation.output)
assert cli_result["status"] == "ok"
```


### Q01-04: Patchable specialist request entrypoint

replace review/llm.py::request_probe_candidate and ReviewTool.run with `- src/rush/review/llm.py::apply_llm_review and new request_probe_candidate.` Insert after review/llm.py::request_probe_candidate and ReviewTool.run:
```text
Call-site rule: ReviewTool.run asks the specialist only through
rush.review.llm.request_probe_candidate(claims, *, allow_network), imported as
`from rush.review import llm as review_llm` and called as
`review_llm.request_probe_candidate(...)`. That function calls the module-global
`_maybe_call_llm([probe_finding], allow_network=allow_network)`, so
`monkeypatch.setattr("rush.review.llm._maybe_call_llm", ...)` intercepts it. Never call
the `_maybe_call_llm` name imported into src/rush/tools/review.py.
```
  Add to `src/rush/review/llm.py` (add `import json` at the top; export in `__all__`):
```python
def request_probe_candidate(
    claims: list[dict[str, Any]], *, allow_network: bool
) -> dict[str, Any] | None:
    """Ask the configured specialist for one counterexample candidate."""
    from rush.tools.base import Finding

    request = Finding(
        path="",
        line=0,
        rule="probe-request",
        severity="info",
        message=json.dumps(
            {"task": "propose_counterexample", "claims": claims}, sort_keys=True
        ),
    )
    return _maybe_call_llm([request], allow_network=allow_network)
```


### Q01-05: Specialist prompt and provider acceptance

Specialist input is one Finding with rule="probe-request" and JSON message
{"task":"propose_counterexample","claims":<eligible current contracts>}.
Reply is data-only JSON with exactly claim_id, source_digest, module, function,
args and predicate. No returned source is executed. Q01-04 supplies the request
entrypoint. Approved origins remain api.openai.com and api.anthropic.com;
connected local specialists require shared provider integration and otherwise
report specialist_unavailable.

Proposed providers/base.py addition before LLMProvider; add import json:

```python
COUNTEREXAMPLE_PROMPT = (
    "You are a counterexample proposer. Reply with ONE JSON object and nothing "
    "else, with exactly the keys claim_id, source_digest, module, function, args, "
    "predicate, naming one claim from this request:\n\n"
)


def build_review_prompt(findings: list[dict[str, Any]]) -> str:
    """The provider prompt: a counterexample request, else the review summary."""
    if len(findings) == 1 and findings[0].get("rule") == "probe-request":
        return COUNTEREXAMPLE_PROMPT + str(findings[0].get("message", ""))
    return (
        f"You are Rush AI Code Reviewer. Summarize and suggest remediations for the following {len(findings)} findings:\n\n"
        + json.dumps(findings[:50], indent=2)
    )
```

In providers/openai.py and providers/anthropic.py import build_review_prompt
from .base; replace only their summary prompt expression with
`prompt = build_review_prompt(findings)`. Keep n_findings for denied branches,
safe_provider_post and completed/nonempty/approved-origin checks. Ordinary
review prompt bytes stay unchanged.

Proposed tests/test_providers.py additions; retain existing OpenAIProvider
import and add json. These specifications are unexecuted:

```python
_PROBE_REQUEST = {
    "path": "",
    "line": 0,
    "rule": "probe-request",
    "severity": "info",
    "message": '{"claims": [], "task": "propose_counterexample"}',
}


def test_probe_request_prompt_is_json_only_and_review_prompt_unchanged():
    from rush.providers.base import COUNTEREXAMPLE_PROMPT, build_review_prompt

    assert build_review_prompt([_PROBE_REQUEST]) == (
        COUNTEREXAMPLE_PROMPT + _PROBE_REQUEST["message"]
    )
    finding = {"rule": "r", "message": "m"}
    assert build_review_prompt([finding]) == (
        "You are Rush AI Code Reviewer. Summarize and suggest remediations for "
        "the following 1 findings:\n\n" + json.dumps([finding], indent=2)
    )


def test_openai_probe_request_reaches_transport_and_content_is_returned(
    monkeypatch,
):
    from rush.providers.base import COUNTEREXAMPLE_PROMPT

    sent = {}

    def fake_post(url, headers, data, **kwargs):
        sent.update(json.loads(data))
        body = {
            "model": "gpt-4o",
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        }
        return 200, json.dumps(body).encode()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("rush.providers.openai.safe_provider_post", fake_post)
    result = OpenAIProvider().summarize_findings([_PROBE_REQUEST], allow_network=True)
    assert result is not None
    assert result.content == "{}"
    assert sent["messages"][-1]["content"] == (
        COUNTEREXAMPLE_PROMPT + _PROBE_REQUEST["message"]
    )


def test_request_probe_candidate_calls_patched_module_entrypoint(monkeypatch):
    from rush.review.llm import request_probe_candidate

    seen = []

    def specialist(findings, **kwargs):
        seen.append((findings[0]["rule"], kwargs["allow_network"]))
        return {"review_kind": "llm", "summary": "{}"}

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", specialist)
    assert request_probe_candidate([], allow_network=True)["summary"] == "{}"
    assert seen == [("probe-request", True)]
```

Compatibility requires these three new tests plus existing provider and
phase57_provider_egress tests to pass after implementation.


### Q01-06: Gated-provider descriptions and discovery

Foundation Q01-DISC row sets ToolSpec.discovery to:
"Review Python files at <path> with local heuristics; claim_evidence=true binds
claims to source digests, probe_claims=true runs one specialist-proposed
counterexample in an isolated OCI container and needs allow_network,
allow_build, allow_slow, allow_artifact_write plus runtime_path and image_ref;
a denied probe makes zero specialist/target calls and records
metadata.probe.status='denied'."
Join these lines with spaces as one catalog string. C11 governs the denial
clause; preserve ordinary review status/findings. F1 publishes that identical
string as path.description; handwritten cli.py::review includes it in --help.
mcp_description stays 20–199 characters with the gated-provider clause.
Foundation tests compare catalog, tools/list schema and CLI help byte-for-byte.

add to Deliverables after Foundation Q01-R2-description row:
```text
R2 truthful-description updates:
- src/rush/catalog.py TOOL_SPECS["review"].mcp_description: change the last string
  "external LLM; no Rush grant gates it." to "external LLM only with allow_network."
  (total length 190, must stay < 200).
- src/rush/mcp.py build_server_instructions: change "provider; no Rush grant gates that
  call." to "provider only with allow_network=true; without it no provider call is made."
- tests/test_phase70_t5.py: Foundation Q01-R2-description row phrase becomes "use_llm=true sends the heuristic
  findings to a configured external LLM provider only with allow_network=true; without it
  no provider call is made."; Foundation Q01-R2-description row phrase "no Rush grant gates it" becomes "only with
  allow_network"; test_review_description_discloses_ungated_llm_egress (Foundation Q01-R2-description row)
  becomes test_review_description_discloses_gated_llm_egress and its last assertion
  becomes `assert "only with allow_network" in text` plus
  `assert "no rush grant" not in text.lower()`.
- docs/user-guide/working-with-ai-agents.md:102-104 and
  docs/reference/mcp-tool-reference.md:20: the exact replacements are in the Q01-19 table.
```


### Q01-07: Direct-call grant compatibility

Proposed R2 change in review/llm.py::apply_llm_review: add keyword-only
allow_network: bool = False; its first condition becomes
`if not use_llm or not allow_network: return "heuristic", None, []`, and its
_maybe_call_llm call forwards allow_network instead of hardcoding True.
ReviewTool.run resolves permissions or ExecutionPermissions(), passes its
network field into apply_llm_review, and sets metadata.llm only for
use_llm=True with network denied. Assemble llm/claims/probe before existing
attach_memory_attribution; preserve memory and scope.
__call__ alone converts public allow_* fields into ExecutionPermissions.

Proposed exact R2 patch to `src/rush/review/llm.py::apply_llm_review`:

```diff
@@
 def apply_llm_review(
     findings: Sequence[Finding],
     use_llm: bool,
+    *,
+    allow_network: bool = False,
 ) -> tuple[LlmStatus, str | None, list[Finding]]:
@@
-    if not use_llm:
+    if not use_llm or not allow_network:
         return "heuristic", None, []
@@
-    llm_summary = _maybe_call_llm(findings, allow_network=True)
+    llm_summary = _maybe_call_llm(findings, allow_network=allow_network)
```


insert after provider-intending callers in the three named test modules:
```text
Update every existing direct provider-intending call to pass the grant:
tests/test_review.py provider-intending callers in the three named test modules, 167, 195; tests/test_tools.py provider-intending callers in the three named test modules, 246;
tests/test_phase57_provider_egress.py provider-intending callers in the three named test modules, 332 (66c6c79 numbers). Each
`run(<root>, use_llm=True)` becomes
`run(<root>, use_llm=True, permissions=ExecutionPermissions(network=True))`;
add the ExecutionPermissions import in each affected test module.
assertions stay unchanged. Add tests/test_review.py, tests/test_tools.py and
tests/test_phase57_provider_egress.py to "Command ownership".
```


### Q01-08: Typed transport forwarding and strict validation

Proposed target content:
```text
Typed forwarding for review: src/rush/cli.py::review declares explicit Click options after
--changed-file and before @permission_options, forwards them in extra_kwargs, and keeps
@result_view_options last:
  @click.option("--claim-evidence", "claim_evidence", is_flag=True)
  @click.option("--behavioral-claims-path", "behavioral_claims_path", type=click.Path(path_type=Path, dir_okay=False), default=None)
  @click.option("--prior-claims-path", "prior_claims_path", type=click.Path(path_type=Path, dir_okay=False), default=None)
  @click.option("--probe-claims", "probe_claims", is_flag=True)
  @click.option("--runtime-path", "runtime_path", type=click.Path(path_type=Path, dir_okay=False), default=None)
  @click.option("--image-ref", "image_ref", default=None)
MCP schema is reflected from ReviewTool.__call__ by make_tool_wrapper. TOOL_SPECS["review"]
gains no option_specs, src/rush/config.py::resolve_tool_options and
src/rush/invocation/resolver.py are unchanged by Q01. Strict booleans: in
src/rush/tools/review.py add `from typing import Annotated`, `from pydantic import Field`
and `_StrictBool = Annotated[bool, Field(strict=True)]`; ReviewTool.__call__ declares
    use_llm: _StrictBool = False, use_graft: _StrictBool = False, changed_files: list[str] | None = None,
    claim_evidence: _StrictBool = False, behavioral_claims_path: Path | None = None,
    prior_claims_path: Path | None = None, probe_claims: _StrictBool = False,
    runtime_path: Path | None = None, image_ref: str | None = None,
    allow_network: _StrictBool = False, allow_build: _StrictBool = False,
    allow_slow: _StrictBool = False, allow_artifact_write: _StrictBool = False
and forwards ordinary options plus permissions=ExecutionPermissions(network=allow_network,build=allow_build,slow=allow_slow,artifact_write=allow_artifact_write). F1's strict public-signature model rejects "false", 0, 1 and "yes" with a
validation error before dispatch (isError false; raw.error.code INVALID_REQUEST); the executor binds allow_* from the
granted permission set.
```
  Test (`tests/test_mcp.py`; body in the Q01-17 fix block): `test_review_rejects_non_boolean_flags_over_stdio`.

Proposed complete `ReviewTool.__call__` replacement, using `_StrictBool` and
`ExecutionPermissions` imports specified above. F1 alone supplies wrapper fields
such as `project` and `result_view`; this command does not duplicate them.

```python
def __call__(
    self,
    path: Path,
    use_llm: _StrictBool = False,
    use_graft: _StrictBool = False,
    changed_files: list[str] | None = None,
    claim_evidence: _StrictBool = False,
    behavioral_claims_path: Path | None = None,
    prior_claims_path: Path | None = None,
    probe_claims: _StrictBool = False,
    runtime_path: Path | None = None,
    image_ref: str | None = None,
    allow_network: _StrictBool = False,
    allow_build: _StrictBool = False,
    allow_slow: _StrictBool = False,
    allow_artifact_write: _StrictBool = False,
) -> ToolResult:
    return self.run(
        path,
        use_llm=use_llm,
        use_graft=use_graft,
        changed_files=changed_files,
        claim_evidence=claim_evidence,
        behavioral_claims_path=behavioral_claims_path,
        prior_claims_path=prior_claims_path,
        probe_claims=probe_claims,
        runtime_path=runtime_path,
        image_ref=image_ref,
        permissions=ExecutionPermissions(
            network=allow_network,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
        ),
    )
```



### Q01-09: Executor permission binding stays unchanged

src/rush/invocation/executor.py::_resolve_context_val already maps public
allow_* fields from context.permissions. It requires no Q01 source change.
Configuration parsing and resolve_tool_options also remain unchanged: review
uses its handwritten route and F1's public-signature model. Catalog changes
are Foundation rows Q01-R2-description and Q01-DISC, not Q01-exclusive writes.

### Q01-10: Shared isolation ownership

Isolation provider: 00-shared-foundation.md F4 (README D1). W18 audit Command45/79 rush_mem_profile, isolation contract13810–13889. Q01 does not implement provider; R/E independent, X1 after F4 acceptance.


### Q01-11: Canonical isolation invocation and receipt

F4 IsolatedRun return, receipt=proc.receipt. run_isolated_argv(root,scratch,runtime_path=runtime_path,image_ref=image_ref,entrypoint="/usr/bin/python3",argv=["/out/probe.py","/out/candidate.json"],timeout_s=30,max_process_launches=4,workdir_rel=".",environment=None). Four reserves image inspection, target run and timeout removal/inspection; actual launches remain counted by F4. Keep LaunchBudgetExhausted; entrypoint must pass in-image version check; no host fallback. F4's named launch-budget/timeout-reaping tests remain required.


### Q01-12: Runtime/image preflight before specialist

The D10 runtime rule is supplied by F4 once; do not add a local runtime-trust
implementation. Proposed command regression using Q01-16 constants:

```python
def test_probe_rejects_non_oci_runtime(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    _, contracts, _ = _review_contract(root)
    calls = []
    monkeypatch.setattr(
        "rush.review.llm._maybe_call_llm",
        lambda findings, **kwargs: calls.append(kwargs) or None,
    )
    result = ReviewTool().run(
        root,
        behavioral_claims_path=contracts,
        probe_claims=True,
        runtime_path=Path(sys.executable),
        image_ref=_IMAGE,
        permissions=_PERMS,
    )
    assert calls == []
    assert result["metadata"]["probe"] == {
        "status": "skipped",
        "reason": "isolation_unavailable",
    }
```

With a trusted runtime but malformed image, assert aggregate status=error,
metadata.error.code=invalid_argument, provider_calls=0 and process_launches=0.
If both runtime and image are invalid, C09 classifies runtime first.

Call F4 check_isolation_inputs(root,runtime_path=runtime_path,image_ref=image_ref) before specialist. IsolationUnavailable gives probe skipped/isolation_unavailable, zero specialist/target calls. ValueError gives error metadata.error.code invalid_argument. Keep test_probe_rejects_non_oci_runtime sys.executable case, all grants, calls=[]; add malformed pinned-image error test. Runtime trust check shared once in F4 D10.


### Q01-13: Trusted packaged harness and scratch lifecycle

Proposed replacements only. No host implementation or target execution. Add
this constant to src/rush/review/probe_harness.py; import its value from the
package, never read loose package source by filesystem path. Candidate JSON
contains data only. The harness runs only inside F4's read-only /work and
private /out mounts. It rejects non-finite input and output JSON. Read and hash
target source once before parent imports; the exact-target captured-byte loader
executes those bytes through normal import machinery. Parent-first and circular
imports, package __path__, __package__, __file__ and sys.modules semantics remain
standard. Cached module/source/loader mismatch rejects before function invocation.
Normal stdout carries executed_source_digest; a mismatched capture emits only
the explicit stale_source envelope and invokes no target.

```python
PROBE_HARNESS_SOURCE = r"""
import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import operator
import sys
from pathlib import Path


def reject_constant(value):
    raise ValueError("non-finite JSON constant: " + value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


OPS = {
    "eq": operator.eq, "ne": operator.ne, "ge": operator.ge,
    "gt": operator.gt, "le": operator.le, "lt": operator.lt,
}
candidate = json.loads(
    Path(sys.argv[1]).read_text(encoding="utf-8"),
    parse_constant=reject_constant, object_pairs_hook=unique_object,
)
source = (Path("/work") / candidate["source_path"]).resolve()
if not source.is_relative_to(Path("/work")):
    raise ValueError("candidate source escape")
source_bytes = source.read_bytes()
captured_digest = hashlib.sha256(source_bytes).hexdigest()
if captured_digest != candidate["source_digest"]:
    print(json.dumps(
        {"status": "stale_source", "source_path": candidate["source_path"],
         "captured_source_digest": captured_digest},
        sort_keys=True, allow_nan=False,
    ))
    raise SystemExit(0)

executed_source_digest = None


class CapturedLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        global executed_source_digest
        exec(compile(source_bytes, str(source), "exec", dont_inherit=True),
             module.__dict__)
        executed_source_digest = captured_digest


loader = CapturedLoader()


class CapturedFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != candidate["module"]:
            return None
        return importlib.util.spec_from_file_location(
            fullname, source, loader=loader,
            submodule_search_locations=(
                [str(source.parent)] if source.name == "__init__.py" else None
            ),
        )


if candidate["module"] in sys.modules:
    raise ValueError("cached candidate module cannot bind captured source")
finder = CapturedFinder()
sys.path.insert(0, "/work")
sys.meta_path.insert(0, finder)
try:
    # Normal import machinery initializes parents, package attributes and the
    # sys.modules entry; only this exact target uses the captured-byte loader.
    module = importlib.import_module(candidate["module"])
finally:
    sys.meta_path.remove(finder)
if (
    Path(module.__file__).resolve() != source
    or module.__loader__ is not loader
    or executed_source_digest != captured_digest
):
    raise ValueError("candidate module/source mismatch")
function = getattr(module, candidate["function"])
if not callable(function):
    raise ValueError("candidate target not callable")
observed = function(*candidate["args"])
holds = OPS[candidate["predicate"]["op"]](observed, candidate["predicate"]["value"])
print(json.dumps(
    {"predicate_holds": bool(holds), "observed": observed,
     "source_path": candidate["source_path"],
     "executed_source_digest": executed_source_digest},
    sort_keys=True, allow_nan=False,
))
"""
```

Proposed additions to src/rush/tools/review.py. Keep module-level provider
bindings patchable. Q01-14 supplies every _claim_* helper used below; existing
ExecutionPermissions/check_permissions/build_execution_metadata, atomic write
and Phase70 review APIs retain their actual signatures. F4 owns the proposed
check_isolation_inputs/run_isolated_argv/IsolatedRun/exception implementations.
Missing grants and no-launch runtime preflight precede both ordinary and
specialist LLM providers. ReviewTool.run computes that result once; the probe
helper consumes it without repeating preflight. No local fallback or simulated
receipt is allowed.

```python
import operator
import subprocess
from tempfile import TemporaryDirectory

from rush.permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
from rush.review import llm as review_llm
from rush.review.probe_harness import PROBE_HARNESS_SOURCE
from rush.runtime.filesystem import atomic_write_bytes
from rush.runtime.isolated_process import (
    IsolatedCleanupError,
    IsolationUnavailable,
    LaunchBudgetExhausted,
    check_isolation_inputs,
    run_isolated_argv,
)

from rush.runtime.subprocesses import SubprocessCancelled, _CANCEL_CHECK

_PROBE_OPERATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "ge": operator.ge,
    "gt": operator.gt,
    "le": operator.le,
    "lt": operator.lt,
}


def _preflight_claim_probe(
    root: Path,
    *,
    permissions: ExecutionPermissions,
    runtime_path: Path | None,
    image_ref: str | None,
) -> tuple[dict | None, dict | None]:
    required = ExecutionPermissions(
        network=True,
        build=True,
        slow=True,
        artifact_write=True,
    )
    allowed, missing = check_permissions(required, permissions)
    if not allowed:
        execution = build_execution_metadata(
            "executed",
            requested=required,
            granted=permissions,
            producer="review_probe",
            extra={
                "disposition": "not_run",
                "cause": "permission_denied",
                "missing_permissions": missing,
            },
        )
        return {"status": "denied", "reason": "build_or_slow_denied"}, execution
    if runtime_path is None or image_ref is None:
        return {"status": "skipped", "reason": "isolation_unavailable"}, None
    try:
        check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
    except IsolationUnavailable:
        return {"status": "skipped", "reason": "isolation_unavailable"}, None
    except ValueError as exc:
        return {
            "status": "error",
            "reason": "invalid_argument",
            "message": str(exc),
        }, None
    return None, build_execution_metadata(
        "executed", requested=required, granted=permissions, producer="review_probe"
    )


def _probe_exception_evidence(exc: Exception) -> dict:
    return {
        key: getattr(exc, attribute)
        for attribute, key in (
            ("receipt", "isolation_receipt"),
            ("process_launches", "process_launches"),
        )
        if hasattr(exc, attribute)
    }


def _run_claim_probe(
    root: Path,
    claims: list[dict],
    *,
    preflight: tuple[dict | None, dict | None],
    runtime_path: Path | None,
    image_ref: str | None,
) -> tuple[dict, dict | None]:
    state, execution = preflight
    if state is not None:
        return state, execution
    eligible = [claim for claim in claims if claim["kind"] == "return_predicate"]
    if not eligible:
        return {"status": "skipped", "reason": "no_source_bound_claims"}, None
    try:
        if any(
            _claim_source_digest(root, _claim_path(c["path"])) != c["source_digest"]
            for c in eligible
        ):
            return {"status": "stale_source"}, None
    except (OSError, ValueError, ContainmentError):
        return {"status": "stale_source"}, None
    response = review_llm.request_probe_candidate(eligible, allow_network=True)
    # request_probe_candidate uses the existing completed/nonempty/approved-origin
    # validation in _maybe_call_llm; ordinary prose is never executable input.
    if (
        not isinstance(response, dict)
        or response.get("review_kind") != "llm"
        or not isinstance(response.get("summary"), str)
        or not response["summary"].strip()
    ):
        return {"status": "skipped", "reason": "specialist_unavailable"}, None
    try:
        candidate = _claim_json_loads(response["summary"])
    except (ValueError, RecursionError):
        return {"status": "error", "reason": "invalid_candidate"}, None
    candidate, state = _validate_probe_candidate(candidate, claims)
    if state is not None:
        return state, None
    try:
        if (
            _claim_source_digest(root, _claim_path(candidate["source_path"]))
            != candidate["source_digest"]
        ):
            return {"status": "stale_source"}, None
        with TemporaryDirectory(
            prefix=".rush-probe-", dir=root.resolve().parent
        ) as name:
            scratch = Path(name)
            expected_runtime_path = str(runtime_path)
            with Path(runtime_path).open("rb") as runtime_file:
                expected_runtime_digest = hashlib.file_digest(
                    runtime_file, "sha256"
                ).hexdigest()
            expected_mounts = [
                {
                    "source": str(root.resolve()),
                    "destination": "/work",
                    "read_only": True,
                },
                {
                    "source": str(scratch.resolve()),
                    "destination": "/out",
                    "read_only": False,
                },
            ]
            atomic_write_bytes(scratch, "candidate.json", _claim_json_bytes(candidate))
            atomic_write_bytes(
                scratch, "probe.py", PROBE_HARNESS_SOURCE.encode("utf-8")
            )
            proc = run_isolated_argv(
                root,
                scratch,
                runtime_path=runtime_path,
                image_ref=image_ref,
                entrypoint="/usr/bin/python3",
                argv=["/out/probe.py", "/out/candidate.json"],
                timeout_s=30,
                max_process_launches=4,
                workdir_rel=".",
                environment=None,
            )
    except IsolationUnavailable as exc:
        return {
            "status": "skipped",
            "reason": "isolation_unavailable",
            **_probe_exception_evidence(exc),
        }, None
    except LaunchBudgetExhausted as exc:
        return {
            "status": "error",
            "reason": "probe_process_failed",
            "failure": "launch_budget_exhausted",
            **_probe_exception_evidence(exc),
        }, None
    except IsolatedCleanupError as exc:
        return {
            "status": "error",
            "reason": "probe_process_failed",
            "failure": "cleanup_failed",
            "message": str(exc),
            **_probe_exception_evidence(exc),
        }, None
    except SubprocessCancelled as exc:
        cancel = _CANCEL_CHECK.get()
        cause = cancel.cause if cancel is not None else "cancelled"
        if cancel is not None:
            cancel.hit = True
        return {
            "status": "skipped",
            "reason": "cancelled",
            **_probe_exception_evidence(exc),
        }, {**(execution or {}), "disposition": "cancelled", "cause": cause}
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "reason": "probe_process_failed",
            "failure": "timeout",
            **_probe_exception_evidence(exc),
        }, None
    except (OSError, ValueError, ContainmentError) as exc:
        return {
            "status": "error",
            "reason": "probe_process_failed",
            "message": str(exc),
            **_probe_exception_evidence(exc),
        }, None
    receipt = proc.receipt
    if proc.returncode != 0:
        return {
            "status": "error",
            "reason": "probe_process_failed",
            "isolation_receipt": receipt,
        }, None
    invalid_receipt = {
        "status": "error",
        "reason": "invalid_receipt",
        "isolation_receipt": receipt,
    }
    try:
        with Path(runtime_path).open("rb") as runtime_file:
            current_runtime_digest = hashlib.file_digest(
                runtime_file, "sha256"
            ).hexdigest()
        payload = _claim_json_loads(proc.stdout)
        if (
            not isinstance(payload, dict)
            or not _json_literal(payload)
            or payload.get("source_path") != candidate["source_path"]
            or not isinstance(receipt, dict)
            or not {
                "runtime_path",
                "runtime_sha256",
                "image_ref",
                "image_digest",
                "mounts",
                "network",
                "run_id",
                "owner_instance_id",
                "exit_code",
                "output_sha256",
                "process_launches",
            }.issubset(receipt)
            or not _json_literal(receipt)
            or receipt.get("runtime_path") != expected_runtime_path
            or receipt.get("runtime_sha256") != expected_runtime_digest
            or current_runtime_digest != expected_runtime_digest
            or receipt.get("image_digest") != image_ref.rsplit("@", 1)[1]
            or type(receipt.get("mounts")) is not list
            or receipt["mounts"] != expected_mounts
            or any(
                type(mount.get("read_only")) is not bool for mount in receipt["mounts"]
            )
            or any(
                not isinstance(receipt.get(key), str)
                or not receipt[key].strip()
                or any(char in receipt[key] for char in "\n\r\0")
                for key in ("run_id", "owner_instance_id")
            )
            or receipt.get("image_ref") != image_ref
            or receipt.get("network") != "none"
            or type(proc.returncode) is not int
            or type(receipt.get("exit_code")) is not int
            or receipt["exit_code"] != proc.returncode
            or receipt.get("output_sha256")
            != hashlib.sha256((proc.stdout + proc.stderr).encode("utf-8")).hexdigest()
            or type(proc.process_launches) is not int
            or not 1 <= proc.process_launches <= 4
            or type(receipt.get("process_launches")) is not int
            or receipt["process_launches"] != proc.process_launches
        ):
            return invalid_receipt, None
        if payload.get("status") == "stale_source":
            if (
                set(payload) != {"status", "source_path", "captured_source_digest"}
                or not isinstance(payload["captured_source_digest"], str)
                or _DIGEST.fullmatch(payload["captured_source_digest"]) is None
                or payload["captured_source_digest"] == candidate["source_digest"]
            ):
                return invalid_receipt, None
            return {"status": "stale_source", "isolation_receipt": receipt}, None
        if (
            set(payload)
            != {
                "predicate_holds",
                "observed",
                "source_path",
                "executed_source_digest",
            }
            or type(payload["predicate_holds"]) is not bool
            or payload["executed_source_digest"] != candidate["source_digest"]
        ):
            return invalid_receipt, None
        holds = bool(
            _PROBE_OPERATORS[candidate["predicate"]["op"]](
                payload["observed"],
                candidate["predicate"]["value"],
            )
        )
        if holds is not payload["predicate_holds"]:
            return invalid_receipt, None
    except (OSError, ValueError, TypeError, RecursionError):
        return invalid_receipt, None
    try:
        current_digest = _claim_source_digest(
            root, _claim_path(candidate["source_path"])
        )
    except (OSError, ValueError, ContainmentError):
        current_digest = None
    if current_digest != candidate["source_digest"]:
        return {"status": "stale_source", "isolation_receipt": receipt}, None
    return {
        "status": "not_falsified" if holds else "falsified",
        "claim_id": candidate["claim_id"],
        "input": candidate["args"],
        "predicate": candidate["predicate"],
        "observed": payload["observed"],
        "source_digest": candidate["source_digest"],
        "executed_source_digest": payload["executed_source_digest"],
        "isolation_receipt": receipt,
    }, None
```

Proposed replacement of ReviewTool.run below (indent as a class method; retain
existing __call__ forwarding specified in Q01-08). Current and prior input
validation precedes any provider call. Current contracts outside changed_files
reject; old records are invalidated separately. Claims are derived from source
heuristics/citations before external summaries, with no memory-policy bypass.
Falsification attaches only to exact matching claim_id; not_falsified stays
unverified. Existing memory attribution wraps the assembled/enriched result.

```python
def run(
    self,
    path: Path,
    *,
    use_llm: bool = False,
    use_graft: bool = False,
    changed_files: list[str] | None = None,
    graft_provider=None,
    config=None,
    claim_evidence: bool = False,
    behavioral_claims_path: Path | None = None,
    prior_claims_path: Path | None = None,
    probe_claims: bool = False,
    runtime_path: Path | None = None,
    image_ref: str | None = None,
    permissions: ExecutionPermissions | None = None,
) -> ToolResult:
    max_lines, use_graft, markers, exclude = _extract_review_config(config, use_graft)
    start = now_ms()
    root = path if path.is_dir() else path.parent
    try:
        targets, scope = collect_reviewable_files(path, changed_files=changed_files)
    except ValueError as error:
        return build_error_review_result(str(error), start)
    scope = review_scope_v1(
        scope,
        root=root,
        targets=targets,
        requested_file_count=len(targets)
        if changed_files is None
        else len(changed_files),
    )

    def claim_error(message, existing=None):
        result = (
            existing
            if existing is not None
            else build_error_review_result(message, start)
        )
        result["status"] = "error"
        result["summary"] = "review: " + message
        metadata = result.setdefault("metadata", {})
        metadata["scope"] = scope
        metadata["error"] = {"code": "invalid_argument", "message": result["summary"]}
        metadata["probe"] = {"status": "error", "reason": "invalid_claim_input"}
        return result

    claims_requested = (
        claim_evidence
        or probe_claims
        or behavioral_claims_path is not None
        or prior_claims_path is not None
    )
    try:
        contracts = (
            _load_claim_records(behavioral_claims_path, root, current=True)
            if behavioral_claims_path is not None
            else []
        )
        prior = (
            _load_claim_records(prior_claims_path, root, current=False)
            if prior_claims_path is not None
            else []
        )
        selected = {
            Path(os.path.abspath(p))
            .relative_to(PhysicalRoot(root).root_path)
            .as_posix()
            for p in targets
        }
        if any(record["path"] not in selected for record in contracts):
            raise ValueError("current contract is outside changed_files review scope")
    except (ValueError, OSError, ContainmentError) as error:
        return claim_error(str(error))
    granted = permissions or ExecutionPermissions()
    probe_preflight = (
        _preflight_claim_probe(
            root,
            permissions=granted,
            runtime_path=runtime_path,
            image_ref=image_ref,
        )
        if probe_claims
        else (None, None)
    )
    if not targets:
        result = build_empty_review_result(path, scope, start)
        result["status"] = "skipped"
        metadata = result.setdefault("metadata", {})
        metadata.update(assessed_files=0, unassessed_reason="no_python_targets")
        if claims_requested:
            metadata["claims"] = []
            metadata["invalidated_claims"] = _invalidate_prior_claims(
                prior, root, targets
            )
        if probe_claims:
            state, execution = _run_claim_probe(
                root,
                [],
                preflight=probe_preflight,
                runtime_path=runtime_path,
                image_ref=image_ref,
            )
            metadata["probe"] = state
            if execution is not None:
                metadata["execution"] = execution
                result["status"] = "skipped"
                if execution.get("disposition") == "cancelled":
                    result["summary"] = (
                        f"cancelled ({execution['cause']}) before review probe finished"
                    )
                else:
                    result["summary"] = "requires permission: " + ", ".join(
                        execution["missing_permissions"]
                    )
            if state["status"] == "error":
                result["status"] = "error"
                message = state.get("message", state["reason"])
                result["summary"] = "review: " + message
                metadata["error"] = {
                    "code": state["reason"],
                    "message": result["summary"],
                }
        return result

    findings = _evaluate_target_heuristics(targets, root, max_lines, markers, exclude)
    citations, used = _recall_memory_citations(targets, _memory_root(path))
    findings.extend(citations)
    graft_findings, graft_state = _resolve_graft_findings(
        path, use_graft, graft_provider
    )
    findings.extend(graft_findings)
    result = assemble_review_result(
        findings,
        start_ms=start,
        scope=scope,
        graft_state=graft_state,
        review_kind="heuristic",
        review_provider=None,
    )
    metadata = result.setdefault("metadata", {})
    try:
        claims = (
            _build_claim_evidence(findings, targets, root, contracts)
            if claims_requested
            else []
        )
        invalidated = (
            _invalidate_prior_claims(prior, root, targets) if claims_requested else []
        )
    except (ValueError, OSError, ContainmentError) as error:
        return attach_memory_attribution(
            claim_error(str(error), result), memory_block(used=used)
        )
    if use_llm and probe_claims and probe_preflight[0] is not None:
        early_state = probe_preflight[0]
        metadata["llm"] = {
            "status": "skipped",
            "reason": (
                "permission_denied"
                if early_state["status"] == "denied"
                else early_state["reason"]
            ),
        }
    elif use_llm and not granted.network:
        metadata["llm"] = {"status": "skipped", "reason": "permission_denied"}
    elif use_llm:
        # Q01-07 preserves provider validation and adds explicit grant forwarding.
        review_kind, review_provider, llm_findings = review_llm.apply_llm_review(
            findings, True, allow_network=granted.network
        )
        result = assemble_review_result(
            [*findings, *llm_findings],
            start_ms=start,
            scope=scope,
            graft_state=graft_state,
            review_kind=review_kind,
            review_provider=review_provider,
        )
        metadata = result.setdefault("metadata", {})
    if claims_requested:
        metadata["claims"] = claims
        metadata["invalidated_claims"] = invalidated
    if probe_claims:
        state, execution = _run_claim_probe(
            root,
            claims,
            preflight=probe_preflight,
            runtime_path=runtime_path,
            image_ref=image_ref,
        )
        metadata["probe"] = state
        if execution is not None:
            metadata["execution"] = execution
            result["status"] = "skipped"
            if execution.get("disposition") == "cancelled":
                result["summary"] = (
                    f"cancelled ({execution['cause']}) before review probe finished"
                )
            else:
                result["summary"] = "requires permission: " + ", ".join(
                    execution["missing_permissions"]
                )
        if state["status"] == "error":
            result["status"] = "error"
            message = state.get("message", state["reason"])
            result["summary"] = "review: " + message
            metadata["error"] = {"code": state["reason"], "message": result["summary"]}
        elif state["status"] == "falsified":
            for claim in claims:
                if claim["claim_id"] == state["claim_id"]:
                    claim["status"] = "falsified"
                    claim["counterexample"] = state
                    break
    return attach_memory_attribution(result, memory_block(used=used))
```

C03/C06–C11/C13 constraints integrated: canonical runtime_path/image_ref,
runtime stays unanchored, 30-second provider call and actual process accounting.
Probe launch budget is four: inspect, run, timeout rm, then inspect; F4 records
only launches actually performed. In combined mode, denied/skipped/error
preflight suppresses ordinary LLM calls as well as the specialist. The existing
four-grant denial preserves ordinary review findings/scope while aggregate
status becomes skipped per C-11/F3; invalid image
returns error with metadata.error.message exactly equal to summary. No runtime
launch, specialist call or scratch creation occurs on denied/preflight states.
Process/receipt errors retain factual IsolatedRun.receipt or supplied exception
receipt/process_launches, including nullable target/exit and cleanup state; source drift after
launch retains receipt but cannot falsify current evidence. Receipt consistency
requires finite JSON, exact selected runtime path and pre/post runtime digest,
pinned image digest, exact invocation mounts, nonempty control-free owner/run
IDs, integer launch/exit counts, output digest and matching source_path, an
executed_source_digest equal to the candidate's verified source_digest, a
post-run source digest check and a host recomputation of the allowed comparison;
true ge0 with observed -1 is rejected. Capture-time drift returns stale_source
with the factual receipt and cannot supply a predicate result.

Required proposed F4 receipt serialization for this invocation (not an existing
implemented API): mounts is exactly the ordered list below; runtime_path is the
supplied absolute path (retain an approved symlink spelling), runtime_sha256 is
a snapshot SHA256 of the supplied runtime path bytes, image_digest is image_ref's
sha256: suffix, and
owner_instance_id/run_id are nonempty strings supplied by F4's execution owner.
Q01 validates their type/content; F4 owns their factual provenance and cleanup.
No caller-known ownership pair, getter, or new run_isolated_argv argument is
required by this packet. Q01 compares runtime_sha256 with supplied-path hashes
captured before and after launch. These snapshots reject persistent byte drift;
equality does not attest transiently swapped executable bytes. F4-START proves
accepted host child starts only; its private marker never becomes a Q01 argument
or a claim about runtime-binary/container-target execution. Target source has its
separate captured-byte loader and executed_source_digest binding above.

Confirmed cleanup re-raises timeout/cancellation/OSError with factual receipt and
launch count. Preserve both when supplied; IsolatedCleanupError retains its
cleanup_confirmed=false receipt as error/cleanup_failed. Neither maps to
isolation_unavailable. Cancellation uses existing ambient _CANCEL_CHECK, marks
CancelScope.hit, preserves cause, and returns skipped with execution.disposition
cancelled. Denial instead uses executed/not_run with permission_denied. An
exception before F4 attaches evidence has no invented receipt or launch count.
LaunchBudgetExhausted preserves its count; IsolationUnavailable may retain image
inspection counts while still proving no target ran. No failure falsifies claims.

```json
[
  {"source": "<resolved root>", "destination": "/work", "read_only": true},
  {"source": "<resolved private scratch>", "destination": "/out", "read_only": false}
]
```

Proposed behavioral acceptance remains unexecuted: after Q01/F4 implementation,
run the Q01-16 state tests and marked real test_probe_claim_counterexample using
the plan's pytest command. The pinned image must verify /usr/bin/python3 before
live acceptance. Static syntax/API checks do not close that gate or approve
Q01-D1/D2, README D1/D2/D3/D10/D11.


### Q01-14: Claim-model decisions and exact identity

Evidence input contract (E1, Q01-14/15/M3): each current record has exactly
kind, path, module, function, source_digest and predicate. kind=return_predicate;
predicate has exactly op and value, with op in eq/ne/ge/gt/le/lt. Accept JSON
literals only; reject non-finite values, unknown keys, duplicates, malformed
symbols/modules, source escapes and stale current digests before provider use.
Only contained top-level functions are supported. Dotted module is the
repository-relative .py path; __init__.py maps to its parent package. Imported
module.__file__ must equal that contained source before the harness call.
A target exception is an execution error, not falsification.

Prior input contains the emitted 12-key records. Validate its shape but allow
missing/changed source solely for invalidation: source_changed, source_missing
or outside_current_scope. Keep old ID, set status=unverified and never reuse an
old counterexample as current proof. New records start unverified with null
counterexample; not_falsified never becomes proven.

The following Q01-D1–D4 decision record controls GREEN packet 3:
```text
## Decision record (owner confirmation required before GREEN packet 3)

Q01-D1. The audit (Q01 audit source-bound claim contract) probes claims derived from heuristic
findings. This plan probes only supplied return_predicate contracts, because a docstring,
TODO or size observation carries no behavioral predicate. Every audit field is kept
(claim_id, symbol, path, line, source_digest, claim, citation_ids, counterexample, status,
rule); the plan adds kind, predicate and the inputs behavioral_claims_path and
prior_claims_path. Confirm or replace before packet 3.
Q01-D2. A current contract whose path is a contained file that is not among the review targets
(outside changed_files) is rejected with invalid_claim_input; it is never silently dropped.
Q01-D3/Q01-D4 follow README D1/D10; no independent owner/runtime choice.

Every record has the 12 keys: claim_id, kind, path, line, symbol, source_digest, claim,
predicate, rule, citation_ids, counterexample, status (counterexample null, status
"unverified" on emission).
- heuristic record: kind="heuristic_observation", rule=<finding rule>, line=<finding line or
  0>, symbol=<innermost enclosing def/class name or null>, claim=<finding message>,
  predicate=null.
- behavioral record: kind="return_predicate", rule=null, line=<ast FunctionDef.lineno>,
  symbol=<function>, claim="<function> returns a value satisfying <op> <value>",
  predicate=<the contract predicate object>.
- claim_id = SHA256 hexdigest of UTF-8 json.dumps(identity, sort_keys=True,
  separators=(",",":")), where identity is a dict mapping kind, path, symbol,
  line, source_digest, rule, claim and predicate to their exact record values.
```

Concrete proposed replacement for the signature-only block above: add these
module-level helpers to src/rush/tools/review.py. This implements the supplied
contract option for review; Q01-D1/D2 remain unapproved decisions. Current
input has exactly six fields; emitted/prior current records exactly twelve.
Invalidated records live only in metadata.invalidated_claims (reason added
there), retain old claim_id and clear counterexample. Malformed records raise
ValueError; _validate_probe_candidate returns exactly one non-None tuple member.

```python
import ast
import hashlib
import json
import keyword
import math
import os
import re
from pathlib import Path, PurePosixPath

from rush.io.physical_paths import ContainmentError, PhysicalRoot

_CLAIM_INPUT_LIMIT = 1024 * 1024
_CLAIM_FIELDS = {
    "claim_id",
    "kind",
    "path",
    "line",
    "symbol",
    "source_digest",
    "claim",
    "predicate",
    "rule",
    "citation_ids",
    "counterexample",
    "status",
}
_CLAIM_IDENTITY = (
    "kind",
    "path",
    "symbol",
    "line",
    "source_digest",
    "rule",
    "claim",
    "predicate",
)
_PREDICATE_OPS = {"eq", "ne", "ge", "gt", "le", "lt"}
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _json_literal(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_literal(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_literal(v) for k, v in value.items())
    return False


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def _claim_json_loads(text):
    value = json.loads(
        text,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )
    if not _json_literal(value):
        raise ValueError("only finite JSON literals are permitted")
    return value


def _claim_json_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _claim_path(value):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError("claim path must be a relative POSIX Python path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
        or relative.suffix != ".py"
        or any(":" in p for p in relative.parts)
    ):
        raise ValueError("claim path must be a canonical relative Python path")
    return relative


def _claim_module(relative):
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if not parts or any(not p.isidentifier() or keyword.iskeyword(p) for p in parts):
        raise ValueError("source does not map to an unambiguous dotted module")
    return ".".join(parts)


def _claim_input_path(path, root):
    raw = Path(path)
    if ".." in raw.parts:
        raise ValueError("claim input parent traversal is forbidden")
    lexical_root = Path(os.path.abspath(root))
    lexical = Path(os.path.abspath(raw if raw.is_absolute() else lexical_root / raw))
    try:
        relative = lexical.relative_to(lexical_root)
    except ValueError as exc:
        raise ValueError("claim input must be inside review root") from exc
    return PhysicalRoot(lexical_root).open_contained(relative, purpose="read")


def _claim_source(root, relative):
    source = PhysicalRoot(root).open_contained(str(relative), purpose="read")
    if not source.is_file():
        raise ValueError("claim source must be a regular file")
    return source


def _claim_source_digest(root, relative):
    with _claim_source(root, relative).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _valid_predicate(value):
    return (
        isinstance(value, dict)
        and set(value) == {"op", "value"}
        and isinstance(value["op"], str)
        and value["op"] in _PREDICATE_OPS
        and _json_literal(value["value"])
    )


def _claim_id(record):
    identity = {key: record[key] for key in _CLAIM_IDENTITY}
    return hashlib.sha256(_claim_json_bytes(identity)).hexdigest()


def _load_claim_records(path: Path, root: Path, *, current: bool) -> list[dict]:
    try:
        source = _claim_input_path(path, root)
        if not source.is_file():
            raise ValueError("claim input must be a regular file")
        with source.open("rb") as handle:
            encoded = handle.read(_CLAIM_INPUT_LIMIT + 1)
        if len(encoded) > _CLAIM_INPUT_LIMIT:
            raise ValueError("claim input exceeds 1 MiB")
        records = _claim_json_loads(encoded.decode("utf-8"))
        if not isinstance(records, list):
            raise ValueError("claim input must be a JSON array")
        seen = set()
        identities = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("claim record must be an object")
            relative = _claim_path(record.get("path"))
            digest = record.get("source_digest")
            if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                raise ValueError("source_digest must be lowercase SHA256")
            if current:
                if (
                    set(record)
                    != {
                        "kind",
                        "path",
                        "module",
                        "function",
                        "source_digest",
                        "predicate",
                    }
                    or record["kind"] != "return_predicate"
                ):
                    raise ValueError("current contract has invalid fields or kind")
                name = record["function"]
                if (
                    not isinstance(name, str)
                    or not name.isidentifier()
                    or keyword.iskeyword(name)
                ):
                    raise ValueError("only top-level function names are supported")
                if record["module"] != _claim_module(relative):
                    raise ValueError("module must match repository-relative source")
                if not _valid_predicate(record["predicate"]):
                    raise ValueError("invalid return predicate")
                source_bytes = _claim_source(root, relative).read_bytes()
                if hashlib.sha256(source_bytes).hexdigest() != digest:
                    raise ValueError("current source digest is stale")
                definitions = [
                    node
                    for node in ast.parse(source_bytes).body
                    if isinstance(node, ast.FunctionDef) and node.name == name
                ]
                if len(definitions) != 1:
                    raise ValueError(
                        "target must be one unambiguous top-level function"
                    )
            else:
                if set(record) != _CLAIM_FIELDS:
                    raise ValueError("prior record must have exactly 12 fields")
                if (
                    record["kind"] not in ("heuristic_observation", "return_predicate")
                    or type(record["line"]) is not int
                    or record["line"] < 0
                    or not isinstance(record["claim"], str)
                    or (
                        record["symbol"] is not None
                        and not isinstance(record["symbol"], str)
                    )
                    or (
                        record["rule"] is not None
                        and not isinstance(record["rule"], str)
                    )
                    or record["status"] not in ("unverified", "falsified")
                    or not isinstance(record["citation_ids"], list)
                    or not all(isinstance(c, str) and c for c in record["citation_ids"])
                    or len(set(record["citation_ids"])) != len(record["citation_ids"])
                    or (
                        record["counterexample"] is not None
                        and not isinstance(record["counterexample"], dict)
                    )
                ):
                    raise ValueError("malformed prior claim")
                if record["kind"] == "return_predicate":
                    symbol = record["symbol"]
                    if (
                        not isinstance(symbol, str)
                        or not symbol.isidentifier()
                        or keyword.iskeyword(symbol)
                        or record["rule"] is not None
                        or not _valid_predicate(record["predicate"])
                    ):
                        raise ValueError("malformed prior behavioral claim")
                    _claim_module(relative)
                elif record["predicate"] is not None:
                    raise ValueError("heuristic claim cannot have a predicate")
                if record["claim_id"] != _claim_id(record):
                    raise ValueError("prior claim identity does not match its fields")
                if record["claim_id"] in identities:
                    raise ValueError("duplicate prior claim identity")
                identities.add(record["claim_id"])
                # Deliberately do not open the old source: missing/drifted sources
                # are admitted for explicit invalidation, never as current proof.
            encoded_record = _claim_json_bytes(record)
            if encoded_record in seen:
                raise ValueError("duplicate claim record")
            seen.add(encoded_record)
        return records
    except (
        OSError,
        UnicodeError,
        SyntaxError,
        ContainmentError,
        RecursionError,
    ) as exc:
        raise ValueError(f"invalid claim input: {exc}") from exc


def _build_claim_evidence(findings, targets, root, contracts: list[dict]) -> list[dict]:
    physical_root = PhysicalRoot(root).root_path
    sources = {}
    for target in targets:
        lexical = Path(os.path.abspath(target))
        try:
            relative = lexical.relative_to(physical_root).as_posix()
        except ValueError as exc:
            raise ValueError("review target escapes claim scope") from exc
        source_bytes = _claim_source(physical_root, _claim_path(relative)).read_bytes()
        try:
            tree = ast.parse(source_bytes)
        except SyntaxError:
            tree = None
        sources[relative] = (hashlib.sha256(source_bytes).hexdigest(), tree)
    citations = {relative: set() for relative in sources}
    selected_findings = []
    for finding in findings:
        raw_path = finding.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        lexical = Path(
            os.path.abspath(
                raw_path if Path(raw_path).is_absolute() else physical_root / raw_path
            )
        )
        try:
            relative = lexical.relative_to(physical_root).as_posix()
        except ValueError:
            continue
        if relative not in sources:
            continue
        selected_findings.append((relative, finding))
        artifact = (finding.get("evidence") or {}).get("memory_artifact_id")
        if isinstance(artifact, str) and artifact:
            citations[relative].add(artifact)
    records = {}

    def emit(record):
        record["citation_ids"] = sorted(citations[record["path"]])
        record["counterexample"] = None
        record["status"] = "unverified"
        record["claim_id"] = _claim_id(record)
        records[record["claim_id"]] = record

    for relative, finding in selected_findings:
        digest, tree = sources[relative]
        line = finding.get("line")
        line = line if type(line) is int and line >= 0 else 0
        enclosing = (
            [
                node
                for node in ast.walk(tree)
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
                and node.lineno <= line <= getattr(node, "end_lineno", node.lineno)
            ]
            if tree is not None
            else []
        )
        symbol = (
            min(
                enclosing,
                key=lambda node: (node.end_lineno - node.lineno, -node.lineno),
            ).name
            if enclosing
            else None
        )
        emit(
            {
                "kind": "heuristic_observation",
                "path": relative,
                "line": line,
                "symbol": symbol,
                "source_digest": digest,
                "claim": finding.get("message", ""),
                "predicate": None,
                "rule": finding.get("rule"),
            }
        )
    for contract in contracts:
        relative = contract["path"]
        if relative not in sources:
            raise ValueError("current contract is outside changed_files review scope")
        digest, tree = sources[relative]
        if digest != contract["source_digest"] or tree is None:
            raise ValueError("current contract source changed or cannot be parsed")
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == contract["function"]
        ]
        if len(definitions) != 1:
            raise ValueError("current contract function changed")
        emit(
            {
                "kind": "return_predicate",
                "path": relative,
                "line": definitions[0].lineno,
                "symbol": contract["function"],
                "source_digest": digest,
                "claim": f"{contract['function']} returns a value satisfying {contract['predicate']['op']} {contract['predicate']['value']}",
                "predicate": contract["predicate"],
                "rule": None,
            }
        )
    return [records[key] for key in sorted(records)]


def _invalidate_prior_claims(prior, root, targets):
    scope = {
        Path(os.path.abspath(p)).relative_to(PhysicalRoot(root).root_path).as_posix()
        for p in targets
    }
    invalidated = []
    for record in prior:
        try:
            digest = _claim_source_digest(root, _claim_path(record["path"]))
        except ContainmentError:
            reason = "outside_current_scope"
        except (OSError, ValueError):
            reason = "source_missing"
        else:
            reason = (
                "source_changed"
                if digest != record["source_digest"]
                else "outside_current_scope"
                if record["path"] not in scope
                else None
            )
        if reason is not None:
            invalidated.append(
                {
                    **record,
                    "status": "unverified",
                    "counterexample": None,
                    "reason": reason,
                }
            )
    return invalidated


def _validate_probe_candidate(
    candidate: object, claims: list[dict]
) -> tuple[dict | None, dict | None]:
    invalid = {"status": "error", "reason": "invalid_candidate"}
    if not isinstance(candidate, dict):
        return None, invalid
    claim = next(
        (c for c in claims if c["claim_id"] == candidate.get("claim_id")), None
    )
    if claim is not None and claim["kind"] != "return_predicate":
        return None, {"status": "skipped", "reason": "unsupported_claim_kind"}
    if (
        set(candidate)
        != {"claim_id", "source_digest", "module", "function", "args", "predicate"}
        or not all(
            isinstance(candidate[k], str)
            for k in ("claim_id", "source_digest", "module", "function")
        )
        or not _DIGEST.fullmatch(candidate["claim_id"])
        or not _DIGEST.fullmatch(candidate["source_digest"])
        or not isinstance(candidate["args"], list)
        or not _json_literal(candidate["args"])
        or not _valid_predicate(candidate["predicate"])
    ):
        return None, invalid
    if claim is None or candidate["source_digest"] != claim["source_digest"]:
        return None, {"status": "stale_source"}
    if (
        candidate["module"] != _claim_module(_claim_path(claim["path"]))
        or candidate["function"] != claim["symbol"]
        or _claim_json_bytes(candidate["predicate"])
        != _claim_json_bytes(claim["predicate"])
    ):
        return None, invalid
    return {**candidate, "source_path": claim["path"]}, None
```

The input reader caps UTF-8 evidence at 1 MiB, rejects duplicate object keys,
duplicate records/IDs, non-finite literals, unknown fields, source escapes,
symlinks, stale current digests and ambiguous/nested/async targets. Prior shape
validation deliberately does not open old source. The run integration in
Q01-13 separately yields source_changed/source_missing/outside_current_scope
invalidations and never imports a target module on the host. Evidence IDs bind
exact canonical JSON values; predicates distinguish JSON booleans and numbers.

Proposed behavioral checks remain unexecuted: Q01-16 input/state bodies,
test_contract_outside_changed_files_scope_is_rejected,
test_claim_citation_ids_come_from_structured_evidence and
test_claim_source_digest_invalidation after source implementation. No source
fix, production acceptance or decision ratification is claimed by these fences.


### Q01-15: Memory evidence and changed_files scope

add to "Command ownership" (after review.py::_format_memory_citation and _build_claim_evidence): `- src/rush/tools/review.py::_format_memory_citation (adds evidence).` Insert after review.py::_format_memory_citation and _build_claim_evidence:
```text
_format_memory_citation adds evidence={"memory_artifact_id": artifact.id} to its Finding(...).
citation_ids of a record = sorted memory_artifact_id values of findings whose resolved path
equals the record's path (structured evidence, never parsed prose). Claims are emitted only for
review targets (so changed_files bounds them); a contract outside that scope follows Q01-D2.
```
Proposed exact patch to `src/rush/tools/review.py::_format_memory_citation`,
preserving existing message and recall behavior:

```diff
@@
         message=f"{target.name}: {detail} (memory artifact {artifact.id})",
+        evidence={"memory_artifact_id": artifact.id},
     )
```

  Append to `tests/test_review.py`:
```python
def test_contract_outside_changed_files_scope_is_rejected(tmp_path):
    source, contracts, record = _review_contract(tmp_path)
    other = tmp_path / "src/b.py"
    other.write_text("def g(value):\n    return value\n", encoding="utf-8")
    outside = {
        **record,
        "path": "src/b.py",
        "module": "src.b",
        "function": "g",
        "source_digest": hashlib.sha256(other.read_bytes()).hexdigest(),
    }
    contracts.write_text(json.dumps([record, outside]), encoding="utf-8")
    full = ReviewTool().run(
        tmp_path, claim_evidence=True, behavioral_claims_path=contracts
    )
    assert sorted(
        (
            c["path"]
            for c in full["metadata"]["claims"]
            if c["kind"] == "return_predicate"
        )
    ) == ["src/a.py", "src/b.py"]
    scoped = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        changed_files=["src/a.py"],
    )
    assert scoped["status"] == "error"
    assert scoped["metadata"]["probe"]["reason"] == "invalid_claim_input"
    contracts.write_text(json.dumps([record]), encoding="utf-8")
    only = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        changed_files=["src/a.py"],
    )
    assert {c["path"] for c in only["metadata"]["claims"]} == {"src/a.py"}
    assert source.is_file()


def test_claim_citation_ids_come_from_structured_evidence(tmp_path):
    from types import SimpleNamespace
    from rush.tools.review import _build_claim_evidence, _format_memory_citation

    source, _, _ = _review_contract(tmp_path)
    artifact = SimpleNamespace(id="mem-1", content={"fix_commit": "abc123"})
    citation = _format_memory_citation(source, "failure", artifact)
    assert citation["evidence"] == {"memory_artifact_id": "mem-1"}
    docstring = Finding(
        path=str(source),
        line=1,
        rule="missing-docstring",
        severity="info",
        message="missing docstring",
    )
    claims = _build_claim_evidence([docstring, citation], [source], tmp_path, [])
    claim = next((c for c in claims if c["rule"] == "missing-docstring"))
    assert claim["citation_ids"] == ["mem-1"]
    assert claim["symbol"] == "f"
```


### Q01-16: Named RED bodies and probe branches
Named packet tests are the restored original bodies above, with Claude's corrected names and binding APIs.
  2. Add helpers after `_review_contract` in `tests/test_review.py`:
```python
from rush.permissions import ExecutionPermissions


def _fake_runtime(tmp_path):
    runtime = tmp_path / "docker"
    runtime.write_text(f"#!/bin/sh\ntouch '{runtime}.ran'\nexit 0\n", encoding="utf-8")
    runtime.chmod(493)
    return runtime


_PERMS = ExecutionPermissions(network=True, build=True, slow=True, artifact_write=True)
_IMAGE = "python@sha256:" + "0" * 64
```
  3. Append these bodies to `tests/test_review.py`:
```python
from rush.permissions import ExecutionPermissions


@pytest.mark.posix_only
def test_heuristic_claim_not_probe_eligible(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.py").write_text("def f(value):\n    return value\n", encoding="utf-8")
    runtime = _fake_runtime(tmp_path)
    calls = []
    monkeypatch.setattr(
        "rush.review.llm._maybe_call_llm",
        lambda findings, **kwargs: calls.append(kwargs) or None,
    )
    result = ReviewTool().run(
        root,
        probe_claims=True,
        runtime_path=runtime,
        image_ref=_IMAGE,
        permissions=_PERMS,
    )
    assert calls == []
    assert result["metadata"]["probe"] == {
        "status": "skipped",
        "reason": "no_source_bound_claims",
    }
    claims = result["metadata"]["claims"]
    assert claims
    assert all((c["kind"] == "heuristic_observation" for c in claims))
    assert not (tmp_path / "docker.ran").exists()


@pytest.mark.posix_only
def test_probe_candidate_for_heuristic_claim_is_unsupported(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    _, contracts, _ = _review_contract(root)
    runtime = _fake_runtime(tmp_path)

    def specialist(findings, **kwargs):
        claims = json.loads(findings[0]["message"])["claims"]
        assert all((c["kind"] == "return_predicate" for c in claims))
        full = ReviewTool().run(root, claim_evidence=True)["metadata"]["claims"]
        heuristic = next((c for c in full if c["kind"] == "heuristic_observation"))
        candidate = {
            "claim_id": heuristic["claim_id"],
            "source_digest": heuristic["source_digest"],
            "module": "src.a",
            "function": "f",
            "args": [-1],
            "predicate": {"op": "ge", "value": 0},
        }
        return {"review_kind": "llm", "summary": json.dumps(candidate)}

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", specialist)
    result = ReviewTool().run(
        root,
        behavioral_claims_path=contracts,
        probe_claims=True,
        runtime_path=runtime,
        image_ref=_IMAGE,
        permissions=_PERMS,
    )
    assert result["metadata"]["probe"] == {
        "status": "skipped",
        "reason": "unsupported_claim_kind",
    }
    assert result["status"] == "ok"
    assert not (tmp_path / "docker.ran").exists()


@pytest.mark.parametrize("use_llm", [False, True])
def test_probe_grant_denied_makes_zero_calls(tmp_path, monkeypatch, use_llm):
    _, contracts, _ = _review_contract(tmp_path)
    base = ReviewTool().run(
        tmp_path, claim_evidence=True, behavioral_claims_path=contracts
    )
    calls = {"provider": 0, "launcher": 0}

    def provider(*args, **kwargs):
        calls["provider"] += 1
        return None

    def launch(*args, **kwargs):
        calls["launcher"] += 1
        raise AssertionError("launcher must not run")

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", provider)
    monkeypatch.setattr("rush.tools.review.run_isolated_argv", launch)
    result = ReviewTool().run(
        tmp_path,
        behavioral_claims_path=contracts,
        probe_claims=True,
        use_llm=use_llm,
        permissions=ExecutionPermissions(network=True),
    )
    assert calls == {"provider": 0, "launcher": 0}
    assert result["metadata"]["probe"] == {
        "status": "denied",
        "reason": "build_or_slow_denied",
    }
    assert result["metadata"]["execution"] == {
        "mode": "executed",
        "requested_permissions": _PERMS.to_dict(),
        "granted_permissions": ExecutionPermissions(network=True).to_dict(),
        "producer": "review_probe",
        "disposition": "not_run",
        "cause": "permission_denied",
        "missing_permissions": [
            "--allow-build",
            "--allow-slow",
            "--allow-artifact-write",
        ],
    }
    assert result["status"] == "skipped"
    assert result["summary"] == (
        "requires permission: --allow-build, --allow-slow, --allow-artifact-write"
    )
    assert result["findings"] == base["findings"]
    assert result["metadata"]["scope"] == base["metadata"]["scope"]


def test_invalid_claim_input_rejected_before_provider(tmp_path, monkeypatch):
    _, contracts, record = _review_contract(tmp_path)
    calls = []
    monkeypatch.setattr(
        "rush.review.llm._maybe_call_llm",
        lambda findings, **kwargs: calls.append(kwargs) or None,
    )
    for bad in (
        {**record, "extra": 1},
        {**record, "path": "../a.py"},
        {**record, "function": "Outer.f"},
    ):
        contracts.write_text(json.dumps([bad]), encoding="utf-8")
        result = ReviewTool().run(
            tmp_path,
            claim_evidence=True,
            behavioral_claims_path=contracts,
            probe_claims=True,
            permissions=_PERMS,
        )
        assert result["status"] == "error"
        assert result["metadata"]["probe"]["reason"] == "invalid_claim_input"
    contracts.write_text(json.dumps([record, record]), encoding="utf-8")
    dup = ReviewTool().run(
        tmp_path, claim_evidence=True, behavioral_claims_path=contracts
    )
    assert dup["metadata"]["probe"]["reason"] == "invalid_claim_input"
    assert calls == []
```
Proposed runnable branch bodies for `tests/test_review.py`, after the helpers
above. These use the documented future `ReviewTool.run` API and F4 `IsolatedRun`
only after their proposed implementations land. Preflight/launcher doubles
exercise orchestration; their receipts are fixture data, not real OCI evidence.
The marked `test_probe_claim_counterexample` remains mandatory real OCI acceptance.

```python
from rush.runtime.isolated_process import IsolatedRun


def _probe_run_result(
    tmp_path,
    monkeypatch,
    *,
    stdout,
    returncode=0,
    value=1,
    candidate_update=None,
    mutate_source=False,
    receipt_update=None,
    launch_error_factory=None,
    mutate_runtime=False,
):
    source, contracts, record = _review_contract(tmp_path)
    source_before = source.read_bytes()
    try:
        payload = json.loads(stdout)
    except ValueError:
        pass
    else:
        if isinstance(payload, dict):
            if "captured_source_digest" not in payload:
                payload.setdefault("executed_source_digest", record["source_digest"])
            stdout = json.dumps(payload)
    runtime_dir = tmp_path.parent / (tmp_path.name + "-runtime")
    runtime_dir.mkdir(exist_ok=True)
    runtime_path = _fake_runtime(runtime_dir)
    calls = {"provider": 0, "launcher": 0}
    stderr = "boom" if returncode else ""
    receipt = {
        "runtime_path": str(runtime_path),
        "runtime_sha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
        "image_ref": _IMAGE,
        "image_digest": "sha256:" + "0" * 64,
        "mounts": [],
        "network": "none",
        "run_id": "unit-test-run",
        "owner_instance_id": "unit-test-owner",
        "exit_code": returncode,
        "output_sha256": hashlib.sha256((stdout + stderr).encode()).hexdigest(),
        "process_launches": 2,
    }
    isolated = IsolatedRun(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        process_launches=2,
        receipt=receipt,
    )
    monkeypatch.setattr(
        "rush.tools.review.check_isolation_inputs", lambda root, **kwargs: None
    )

    def launch(root, scratch, **kwargs):
        calls["launcher"] += 1
        assert kwargs["max_process_launches"] == 4
        receipt["mounts"] = [
            {"source": str(root.resolve()), "destination": "/work", "read_only": True},
            {
                "source": str(scratch.resolve()),
                "destination": "/out",
                "read_only": False,
            },
        ]
        receipt.update(receipt_update or {})
        if mutate_source:
            source.write_text(
                "def f(value):\n    return abs(value)\n", encoding="utf-8"
            )
        if mutate_runtime:
            runtime_path.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
        if launch_error_factory is not None:
            raise launch_error_factory(receipt)
        return isolated

    monkeypatch.setattr("rush.tools.review.run_isolated_argv", launch)

    def provider(findings, **kwargs):
        calls["provider"] += 1
        assert kwargs["allow_network"] is True
        claims = json.loads(findings[0]["message"])["claims"]
        claim = next(c for c in claims if c["kind"] == "return_predicate")
        candidate = {
            "claim_id": claim["claim_id"],
            "source_digest": claim["source_digest"],
            "module": "src.a",
            "function": "f",
            "args": [value],
            "predicate": {"op": "ge", "value": 0},
        }
        candidate.update(candidate_update or {})
        return {"review_kind": "llm", "summary": json.dumps(candidate)}

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", provider)
    result = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        probe_claims=True,
        permissions=_PERMS,
        runtime_path=runtime_path,
        image_ref=_IMAGE,
    )
    return result, calls, source, source_before, record, receipt


def test_probe_provider_unavailable_preserves_base_review(tmp_path, monkeypatch):
    _, contracts, _ = _review_contract(tmp_path)
    base = ReviewTool().run(
        tmp_path, claim_evidence=True, behavioral_claims_path=contracts
    )
    assert base["status"] == "ok"
    calls = {"provider": 0, "launcher": 0}

    def provider(*args, **kwargs):
        calls["provider"] += 1
        return None

    def launch(*args, **kwargs):
        calls["launcher"] += 1
        raise AssertionError("launcher must not run")

    monkeypatch.setattr(
        "rush.tools.review.check_isolation_inputs", lambda root, **kwargs: None
    )
    monkeypatch.setattr("rush.review.llm._maybe_call_llm", provider)
    monkeypatch.setattr("rush.tools.review.run_isolated_argv", launch)
    result = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        probe_claims=True,
        permissions=_PERMS,
        runtime_path=Path("/usr/bin/docker"),
        image_ref=_IMAGE,
    )
    assert calls == {"provider": 1, "launcher": 0}
    assert result["metadata"]["probe"] == {
        "status": "skipped",
        "reason": "specialist_unavailable",
    }
    assert result["status"] == "ok"
    assert result["summary"] == base["summary"]
    assert result["findings"] == base["findings"]
    assert "execution" not in result["metadata"]


@pytest.mark.parametrize(
    "receipt_update",
    [
        {"runtime_path": "/other/docker"},
        {"runtime_sha256": "f" * 64},
        {"runtime_sha256": 1},
        {"image_digest": "sha256:" + "f" * 64},
        {"image_ref": "other@sha256:" + "0" * 64},
        {"mounts": []},
        {"mounts": [{"source": "/", "destination": "/work", "read_only": False}]},
        {"run_id": ""},
        {"run_id": 1},
        {"owner_instance_id": None},
        {"owner_instance_id": "\n"},
        {"network": "host"},
        {"exit_code": False},
        {"exit_code": 1},
        {"process_launches": True},
        {"process_launches": 3},
        {"output_sha256": "f" * 64},
    ],
)
def test_probe_invocation_identity_receipt_mismatch_is_error(
    tmp_path, monkeypatch, receipt_update
):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout=json.dumps(
            {"predicate_holds": True, "observed": 1, "source_path": "src/a.py"}
        ),
        receipt_update=receipt_update,
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_receipt",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "error"
    assert result["summary"] == "review: invalid_receipt"
    assert result["metadata"]["error"] == {
        "code": "invalid_receipt",
        "message": "review: invalid_receipt",
    }


@pytest.mark.parametrize(
    "stdout",
    [
        "[]",
        '{"predicate_holds":"true","observed":1,"source_path":"src/a.py"}',
        '{"predicate_holds":true,"observed":1,"source_path":"src/other.py"}',
        '{"predicate_holds":true,"observed":-1,"source_path":"src/a.py"}',
    ],
)
def test_probe_invalid_receipts_retain_isolation_receipt(tmp_path, monkeypatch, stdout):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path, monkeypatch, stdout=stdout
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_receipt",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "error"


def test_probe_process_failure_retains_isolation_receipt(tmp_path, monkeypatch):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path, monkeypatch, stdout="", returncode=17
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "probe_process_failed",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "error"


def test_probe_detects_source_change_after_execution(tmp_path, monkeypatch):
    result, calls, source, original, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout='{"predicate_holds":true,"observed":1,"source_path":"src/a.py"}',
        mutate_source=True,
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert source.read_bytes() != original
    assert result["metadata"]["probe"] == {
        "status": "stale_source",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "ok"


@pytest.mark.parametrize(
    ("value", "holds", "status"),
    [
        (-1, False, "falsified"),
        (1, True, "not_falsified"),
    ],
)
def test_probe_predicate_outcomes_are_exact(
    tmp_path, monkeypatch, value, holds, status
):
    payload = json.dumps(
        {
            "predicate_holds": holds,
            "observed": value,
            "source_path": "src/a.py",
        }
    )
    result, calls, _, _, record, receipt = _probe_run_result(
        tmp_path, monkeypatch, stdout=payload, value=value
    )
    assert calls == {"provider": 1, "launcher": 1}
    claim = next(
        c for c in result["metadata"]["claims"] if c["kind"] == "return_predicate"
    )
    assert result["metadata"]["probe"] == {
        "claim_id": claim["claim_id"],
        "status": status,
        "input": [value],
        "predicate": {"op": "ge", "value": 0},
        "observed": value,
        "source_digest": record["source_digest"],
        "executed_source_digest": record["source_digest"],
        "isolation_receipt": receipt,
    }
    assert result["status"] == "ok"
    if status == "not_falsified":
        claim = next(
            c for c in result["metadata"]["claims"] if c["kind"] == "return_predicate"
        )
        assert claim["status"] == "unverified"
        assert claim["counterexample"] is None
    else:
        assert claim["status"] == "falsified"
        assert claim["counterexample"] == result["metadata"]["probe"]


@pytest.mark.parametrize(
    "candidate_update",
    [
        {"unexpected": True},
        {"args": None},
        {"predicate": {"op": "eval", "value": 0}},
        {"module": "src.other"},
        {"args": [float("nan")]},
    ],
)
def test_invalid_candidate_rejected_without_launch(
    tmp_path, monkeypatch, candidate_update
):
    result, calls, _, _, _, _ = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout='{"predicate_holds":true,"observed":1,"source_path":"src/a.py"}',
        candidate_update=candidate_update,
    )
    assert calls == {"provider": 1, "launcher": 0}
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_candidate",
    }
    assert result["status"] == "error"


def test_stale_candidate_rejected_without_launch(tmp_path, monkeypatch):
    result, calls, _, _, _, _ = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout='{"predicate_holds":true,"observed":1,"source_path":"src/a.py"}',
        candidate_update={"source_digest": "f" * 64},
    )
    assert calls == {"provider": 1, "launcher": 0}
    assert result["metadata"]["probe"] == {"status": "stale_source"}
    assert result["status"] == "ok"


@pytest.mark.parametrize("use_llm", [False, True])
def test_malformed_image_fails_before_provider_or_launcher(
    tmp_path, monkeypatch, use_llm
):
    _, contracts, _ = _review_contract(tmp_path)
    calls = {"provider": 0, "preflight": 0, "launcher": 0}

    def preflight(root, **kwargs):
        calls["preflight"] += 1
        raise ValueError("Malformed image reference")

    def provider(*args, **kwargs):
        calls["provider"] += 1
        return None

    def launch(*args, **kwargs):
        calls["launcher"] += 1
        raise AssertionError("launcher must not run")

    monkeypatch.setattr("rush.tools.review.check_isolation_inputs", preflight)
    monkeypatch.setattr("rush.review.llm._maybe_call_llm", provider)
    monkeypatch.setattr("rush.tools.review.run_isolated_argv", launch)
    result = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=contracts,
        probe_claims=True,
        use_llm=use_llm,
        permissions=_PERMS,
        runtime_path=Path("/usr/bin/docker"),
        image_ref="python:latest",
    )
    assert calls == {"provider": 0, "preflight": 1, "launcher": 0}
    assert result["status"] == "error"
    assert result["summary"] == "review: Malformed image reference"
    assert result["metadata"]["error"] == {
        "code": "invalid_argument",
        "message": "review: Malformed image reference",
    }
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_argument",
        "message": "Malformed image reference",
    }
```




These proposed tests bind receipt interpretation to executed bytes, then
exercise the actual captured-loader path in OCI. The race restores host bytes
before the final host digest check, so a before/after-only check would miss it.
Neither body is executed during plan remediation.

```python
def test_probe_rejects_different_executed_source_digest(tmp_path, monkeypatch):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout=json.dumps(
            {
                "predicate_holds": True,
                "observed": 1,
                "source_path": "src/a.py",
                "executed_source_digest": "f" * 64,
            }
        ),
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_receipt",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "error"


def test_probe_reports_stale_capture_without_falsifying_claim(tmp_path, monkeypatch):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout=json.dumps(
            {
                "status": "stale_source",
                "source_path": "src/a.py",
                "captured_source_digest": "f" * 64,
            }
        ),
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == {
        "status": "stale_source",
        "isolation_receipt": receipt,
    }
    claim = next(
        c for c in result["metadata"]["claims"] if c["kind"] == "return_predicate"
    )
    assert claim["status"] == "unverified"
    assert claim["counterexample"] is None
    assert result["status"] == "ok"
```

```python
@pytest.mark.oci_isolation
def test_probe_executes_digest_captured_source_during_host_mutation(
    tmp_path, monkeypatch
):
    import threading
    import time

    from rush.runtime.isolated_process import run_isolated_argv

    required = ("RUSH_TEST_OCI_RUNTIME", "RUSH_TEST_PYTHON_IMAGE")
    assert all(os.environ.get(key) for key in required), (
        "Real F4 OCI prerequisites unmet"
    )
    runtime = os.environ["RUSH_TEST_OCI_RUNTIME"]
    image = os.environ["RUSH_TEST_PYTHON_IMAGE"]
    assert Path(runtime).is_absolute()
    assert "@sha256:" in image
    digest_part = image.rsplit("@sha256:", 1)[1]
    assert len(digest_part) == 64
    assert all(c in "0123456789abcdef" for c in digest_part)
    source, contracts, record = _review_contract(tmp_path)
    (tmp_path / "src/__init__.py").write_text(
        "from pathlib import Path\nimport time\n"
        "def _wait(path):\n"
        "    deadline = time.monotonic() + 10\n"
        "    while not Path(path).exists():\n"
        "        if time.monotonic() >= deadline: raise TimeoutError(path)\n"
        "        time.sleep(0.01)\n"
        "Path('/out/parent_ready').write_text('ready')\n"
        "_wait('/out/continue')\n",
        encoding="utf-8",
    )

    def target_source(return_line):
        return (
            "from pathlib import Path\nimport time\n"
            "def f(value):\n"
            "    Path('/out/target_ready').write_text('ready')\n"
            "    deadline = time.monotonic() + 10\n"
            "    while not Path('/out/restored').exists():\n"
            "        if time.monotonic() >= deadline: raise TimeoutError('restore')\n"
            "        time.sleep(0.01)\n"
            f"    {return_line}\n"
        )

    original = target_source("return value").encode()
    changed = target_source("return abs(value)").encode()
    source.write_bytes(original)
    record["source_digest"] = hashlib.sha256(original).hexdigest()
    contracts.write_text(json.dumps([record]), encoding="utf-8")
    scratch_ready = threading.Event()
    state = {"scratch": None, "errors": []}

    def wait_for(path):
        deadline = time.monotonic() + 10
        while not path.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError(str(path))
            time.sleep(0.01)

    def mutate_at_import_boundary():
        scratch_ready.wait(timeout=10)
        scratch = state["scratch"]
        try:
            if scratch is None:
                raise TimeoutError("launcher never exposed private scratch")
            wait_for(scratch / "parent_ready")
            source.write_bytes(changed)
            (scratch / "continue").write_text("go")
            wait_for(scratch / "target_ready")
        except BaseException as exc:
            state["errors"].append(exc)
        finally:
            source.write_bytes(original)
            if scratch is not None:
                (scratch / "continue").write_text("go")
                (scratch / "restored").write_text("done")

    mutator = threading.Thread(target=mutate_at_import_boundary, daemon=True)
    mutator.start()
    runs = []

    def synchronized_run(root, scratch, **kwargs):
        state["scratch"] = scratch
        scratch_ready.set()
        isolated = run_isolated_argv(root, scratch, **kwargs)
        runs.append(isolated)
        return isolated

    monkeypatch.setattr("rush.tools.review.run_isolated_argv", synchronized_run)

    def specialist(findings, **kwargs):
        assert kwargs["allow_network"] is True
        claim = next(
            c
            for c in json.loads(findings[0]["message"])["claims"]
            if c["kind"] == "return_predicate"
        )
        return {
            "review_kind": "llm",
            "summary": json.dumps(
                {
                    "claim_id": claim["claim_id"],
                    "source_digest": claim["source_digest"],
                    "module": "src.a",
                    "function": "f",
                    "args": [-1],
                    "predicate": {"op": "ge", "value": 0},
                }
            ),
        }

    monkeypatch.setattr("rush.review.llm._maybe_call_llm", specialist)
    try:
        result = ReviewTool().run(
            tmp_path,
            claim_evidence=True,
            behavioral_claims_path=contracts,
            probe_claims=True,
            permissions=_PERMS,
            runtime_path=Path(runtime),
            image_ref=image,
        )
    finally:
        mutator.join(timeout=12)
        source.write_bytes(original)
    assert not mutator.is_alive()
    assert state["errors"] == []
    assert len(runs) == 1
    assert runs[0].returncode == 0
    payload = json.loads(runs[0].stdout)
    assert payload["executed_source_digest"] == record["source_digest"]
    assert payload["source_path"] == "src/a.py"
    assert payload["predicate_holds"] is False
    assert source.read_bytes() == original
    probe = result["metadata"]["probe"]
    assert probe["status"] == "falsified"
    assert probe["observed"] == -1
    assert probe["source_digest"] == record["source_digest"]
    assert probe["isolation_receipt"]["image_ref"] == image
    assert result["status"] == "ok"
```


These proposed exception tests exercise the defining launcher binding through
ReviewTool.run. Receipts/counts are explicit fixture evidence, not real OCI
acceptance. Real F4 cleanup/cancellation/budget tests remain mandatory separately.
No new consumer argument exposes F4-START's provider-private evidence marker.

```python
import subprocess
from rush.runtime.isolated_process import (
    IsolatedCleanupError,
    IsolationUnavailable,
    LaunchBudgetExhausted,
)
from rush.runtime.subprocesses import SubprocessCancelled, cancel_scope


@pytest.mark.parametrize(
    "failure,count,has_receipt",
    [
        ("timeout", 4, True),
        ("os_error", 3, True),
        ("cleanup_failed", 4, True),
        ("launch_budget_exhausted", 0, False),
        ("launch_budget_exhausted", 1, False),
        ("isolation_unavailable", 0, False),
        ("isolation_unavailable", 1, False),
    ],
)
def test_probe_launcher_exception_preserves_factual_evidence(
    tmp_path, monkeypatch, failure, count, has_receipt
):
    captured = {}

    def error_factory(receipt):
        receipt.update(
            exit_code=None,
            process_launches=count,
            container_name="rush-fixture",
            target_started=None,
            target_launch_attempted=True,
            cleanup_confirmed=failure != "cleanup_failed",
        )
        if failure == "timeout":
            exc = subprocess.TimeoutExpired(["docker", "run"], 30)
        elif failure == "os_error":
            exc = OSError("runtime call failed")
        elif failure == "cleanup_failed":
            exc = IsolatedCleanupError("rush-fixture", receipt)
        elif failure == "launch_budget_exhausted":
            exc = LaunchBudgetExhausted(count)
        else:
            exc = IsolationUnavailable("image unavailable", process_launches=count)
        if has_receipt:
            exc.receipt = receipt
            exc.process_launches = count
        captured["exception"] = exc
        return exc

    result, calls, source, original, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout="",
        launch_error_factory=error_factory,
    )
    # Baseline uses exactly the same current contracts/source without a probe.
    base = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=tmp_path / "contracts.json",
    )
    expected = {
        "status": "skipped" if failure == "isolation_unavailable" else "error",
        "reason": (
            "isolation_unavailable"
            if failure == "isolation_unavailable"
            else "probe_process_failed"
        ),
        "process_launches": count,
    }
    if failure in {"timeout", "cleanup_failed", "launch_budget_exhausted"}:
        expected["failure"] = failure
    if failure in {"os_error", "cleanup_failed"}:
        expected["message"] = str(captured["exception"])
    if has_receipt:
        expected["isolation_receipt"] = receipt
        assert receipt["cleanup_confirmed"] is (failure != "cleanup_failed")
        assert receipt["target_started"] is None
        assert receipt["exit_code"] is None
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == expected
    assert result["findings"] == base["findings"]
    assert result["metadata"]["scope"] == base["metadata"]["scope"]
    assert result["metadata"]["claims"] == base["metadata"]["claims"]
    assert source.read_bytes() == original
    assert "execution" not in result["metadata"]
    if failure == "isolation_unavailable":
        assert result["status"] == base["status"] == "ok"
        assert result["summary"] == base["summary"]
        assert "error" not in result["metadata"]
    else:
        message = expected.get("message", "probe_process_failed")
        assert result["status"] == "error"
        assert result["summary"] == "review: " + message
        assert result["metadata"]["error"] == {
            "code": "probe_process_failed",
            "message": "review: " + message,
        }


@pytest.mark.parametrize("has_receipt", [False, True])
@pytest.mark.parametrize("cause", [None, "user_requested"])
def test_probe_cancelled_preserves_scope_and_ambient_cause(
    tmp_path, monkeypatch, has_receipt, cause
):
    def error_factory(receipt):
        exc = SubprocessCancelled(["docker", "run"], pid=123)
        if has_receipt:
            receipt.update(
                exit_code=None,
                process_launches=4,
                target_started=None,
                target_launch_attempted=True,
                cleanup_confirmed=True,
                container_name="rush-fixture",
            )
            exc.receipt = receipt
            exc.process_launches = 4
        return exc

    expected_cause = cause or "cancelled"
    with cancel_scope(
        (lambda: True) if cause is not None else None, cause=expected_cause
    ) as scope:
        result, calls, source, original, _, receipt = _probe_run_result(
            tmp_path,
            monkeypatch,
            stdout="",
            launch_error_factory=error_factory,
        )
        if cause is None:
            assert scope is None
        else:
            assert scope is not None and scope.hit is True
    base = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=tmp_path / "contracts.json",
    )
    expected = {"status": "skipped", "reason": "cancelled"}
    if has_receipt:
        expected.update(isolation_receipt=receipt, process_launches=4)
        assert receipt["cleanup_confirmed"] is True
        assert receipt["target_started"] is None
    assert calls == {"provider": 1, "launcher": 1}
    assert result["metadata"]["probe"] == expected
    assert result["status"] == "skipped"
    assert result["summary"] == (
        f"cancelled ({expected_cause}) before review probe finished"
    )
    assert result["metadata"]["execution"] == {
        "mode": "executed",
        "requested_permissions": _PERMS.to_dict(),
        "granted_permissions": _PERMS.to_dict(),
        "producer": "review_probe",
        "disposition": "cancelled",
        "cause": expected_cause,
    }
    assert "error" not in result["metadata"]
    assert result["findings"] == base["findings"]
    assert result["metadata"]["scope"] == base["metadata"]["scope"]
    assert result["metadata"]["claims"] == base["metadata"]["claims"]
    assert source.read_bytes() == original


def test_probe_runtime_path_byte_drift_is_invalid_receipt(tmp_path, monkeypatch):
    result, calls, _, _, _, receipt = _probe_run_result(
        tmp_path,
        monkeypatch,
        stdout=json.dumps(
            {"predicate_holds": True, "observed": 1, "source_path": "src/a.py"}
        ),
        mutate_runtime=True,
    )
    base = ReviewTool().run(
        tmp_path,
        claim_evidence=True,
        behavioral_claims_path=tmp_path / "contracts.json",
    )
    assert calls == {"provider": 1, "launcher": 1}
    assert (
        hashlib.sha256(Path(receipt["runtime_path"]).read_bytes()).hexdigest()
        != (receipt["runtime_sha256"])
    )
    assert result["metadata"]["probe"] == {
        "status": "error",
        "reason": "invalid_receipt",
        "isolation_receipt": receipt,
    }
    assert result["status"] == "error"
    assert result["summary"] == "review: invalid_receipt"
    assert result["metadata"]["error"] == {
        "code": "invalid_receipt",
        "message": "review: invalid_receipt",
    }
    assert result["findings"] == base["findings"]
    assert result["metadata"]["scope"] == base["metadata"]["scope"]
    assert result["metadata"]["claims"] == base["metadata"]["claims"]
```

Proposed executable focused gate, after F3/F4 and Q01 implementation (unexecuted):
`rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_review.py -q -k 'probe_launcher_exception or probe_cancelled or runtime_path_byte_drift or probe_grant_denied'`.
Expected: every selected parameter case passes, no skipped cases. This gate
proves mocked review orchestration and snapshot drift rejection only; separate
marked real OCI acceptance still proves isolation/cleanup/target execution.

### Q01-17: CLI and stdio grant/type acceptance

Foundation Q01-R2-transport row in tests/test_mcp.py. Reuse F6
tests/transport_parity.py::run_cli/run_mcp; its real-file errlog is required
on Windows. No command-local stdio implementation. Import json and the shared
helpers; Click imports remain inside the provider sentinel test.

```python
def test_review_llm_grant_cli_mcp_parity(tmp_path, monkeypatch):
    import transport_parity
    from click.testing import CliRunner
    from rush.cli import cli

    (tmp_path / "x.py").write_text("# TODO repair\nx = 1\n", encoding="utf-8")
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        transport_parity,
        "ENV",
        {
            key: value
            for key, value in transport_parity.ENV.items()
            if key not in {"ANTHROPIC_API_KEY", "OPENAI_API_KEY"}
        },
    )
    calls = []
    monkeypatch.setattr(
        "rush.review.llm._maybe_call_llm",
        lambda findings, **kwargs: calls.append(kwargs["allow_network"]) or None,
    )
    runner = CliRunner()
    denied = runner.invoke(cli, ["review", str(tmp_path), "--llm", "--json"])
    assert denied.exit_code == 0, denied.output
    assert json.loads(denied.output)["metadata"]["llm"] == {
        "status": "skipped",
        "reason": "permission_denied",
    }
    assert calls == []
    granted = runner.invoke(
        cli,
        ["review", str(tmp_path), "--llm", "--allow-network", "--json"],
    )
    assert granted.exit_code == 0, granted.output
    assert "llm" not in json.loads(granted.output)["metadata"]
    assert calls == [True]

    for allowed in (False, True):
        options = ("--llm", "--allow-network") if allowed else ("--llm",)
        exit_code, cli_result = run_cli("review", tmp_path, options)
        mcp_result = run_mcp(
            "rush_review",
            {"path": str(tmp_path), "use_llm": True, "allow_network": allowed},
        )
        assert exit_code == 0
        for result in (cli_result, mcp_result):
            assert result["review_kind"] == "heuristic"
            if allowed:
                assert "llm" not in result["metadata"]
            else:
                assert result["metadata"]["llm"] == {
                    "status": "skipped",
                    "reason": "permission_denied",
                }


def test_review_rejects_non_boolean_flags_over_stdio(tmp_path):
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    names = (
        "use_llm",
        "use_graft",
        "allow_network",
        "allow_build",
        "allow_slow",
        "allow_artifact_write",
        "claim_evidence",
        "probe_claims",
    )
    for name in names:
        for value in ("false", 0, 1, "yes"):
            payload = run_mcp("rush_review", {"path": str(tmp_path), name: value})
            assert payload["status"] == "error"
            assert payload["raw"]["error"]["code"] == "INVALID_REQUEST"
    payload = run_mcp("rush_review", {"path": str(tmp_path), "unknown_argument": 1})
    assert payload["status"] == "error"
    assert payload["raw"]["error"]["code"] == "INVALID_REQUEST"
```

run_mcp asserts response.isError is False; invalid requests are ToolResult
errors, not protocol tool errors. Provider-count assertions above cover the
in-process CLI boundary; credential-free subprocess tests prove transport
grant forwarding, not an external provider request. Provider tests Q01-05/07
separately exercise approved-origin/completed-response behavior.

### Q01-18: Live OCI marker and CI prerequisites

Foundation Q01-OCI-marker/CI: oci_isolation registered; has_oci=bool(RUSH_TEST_OCI_RUNTIME) only; unset runtime deselects, never skips. test_probe_claim_counterexample marked, asserts pinned RUSH_TEST_PYTHON_IMAGE when runtime set. CI provisions all Python/Rush/compiler images and runs pytest tests -m oci_isolation. Tests/test_no_skips add has_oci False/True rows. Image owner D11 unresolved.


### Q01-19: Exact documentation patch rows

Proposed target content:
```text
Documentation deliverables (after executable routes pass). Each row replaces the exact old
substring on that line with the new one (paths under docs/ unless noted):
| file:line | old substring | new substring |
| user-guide/faq.md:21 | `--llm` is a stub that makes no provider call. | `--llm` calls a configured provider only with `--allow-network`; without it the review stays heuristic and `metadata.llm` is `{status: skipped, reason: permission_denied}`. |
| reference/environment-variables.md:12 | Note: `--llm` is a development stub making zero network requests. | Note: `--llm` sends findings to the provider only with `--allow-network`. |
| reference/environment-variables.md:13 | Development stub making zero network requests. | Used only when `--llm` is combined with `--allow-network`. |
| ENVIRONMENT_VARIABLES.md:15 | `--llm` can make a provider request. | `--llm` makes a provider request only with `--allow-network`. |
| ENVIRONMENT_VARIABLES.md:16 | The configured provider can receive findings. | The configured provider receives findings only with `--allow-network`. |
| FAQ.md:33 | when requested with `rush review --llm` and a provider is configured, Rush can send findings to Anthropic/OpenAI. | when requested with `rush review --llm --allow-network` and a provider is configured, Rush can send findings to Anthropic/OpenAI; without `--allow-network` no provider call is made. |
| PRIVACY.md:18 | `review --llm` can send findings to a configured provider. | `review --llm` can send findings to a configured provider only with `--allow-network`. |
| PRIVACY.md:19 | can call a configured provider and send findings. | can call a configured provider and send findings only with `--allow-network`. |
| safety/privacy-and-data-handling.md:23 | configured Anthropic/OpenAI provider; | configured Anthropic/OpenAI provider only with `--allow-network`; |
| README.md:87 | configured Anthropic/OpenAI provider; | configured Anthropic/OpenAI provider only with `--allow-network`; |
| DESIGN_PRINCIPLES.md:35 | to summarize findings. | to summarize findings, only with `--allow-network`. |
| DOCUMENTATION_BRIEF.md:30 | configured Anthropic/OpenAI provider with findings | configured Anthropic/OpenAI provider with findings only with `--allow-network` |
| MCP.md:35 | `--llm` can call a configured provider. | `--llm` can call a configured provider only with `--allow-network`. |
| LIMITATIONS.md:3, SAFETY.md:15, safety/safety-overview.md:14 | `--llm` can send findings to a configured provider. | `--llm` can send findings to a configured provider only with `--allow-network`. |
| KNOWN_ISSUES.md:11 | can call a configured provider and send findings; | can call a configured provider and send findings only with `--allow-network`; |
| CLI_REFERENCE.md:69 | repeatable `--changed-file`; | repeatable `--changed-file`, `--claim-evidence`, `--behavioral-claims-path`, `--prior-claims-path`, `--probe-claims`, `--runtime-path`, `--image-ref`; |
| CLI_REFERENCE.md:73 | [--changed-file RELATIVE_PATH]... [--json] | [--changed-file RELATIVE_PATH]... [--claim-evidence] [--behavioral-claims-path FILE] [--prior-claims-path FILE] [--probe-claims] [--runtime-path FILE] [--image-ref REF] [--json] |
| CLI_REFERENCE.md:87 | `--llm` can call a configured provider; | `--llm` can call a configured provider only with `--allow-network`; |
| reference/cli-reference.md:78 | `--llm` is a no-call stub; | `--llm` calls a configured provider only with `--allow-network`; `--probe-claims` needs `--allow-network --allow-build --allow-slow --allow-artifact-write`, `--runtime-path` and `--image-ref`; |
| MCP_REFERENCE.md:86 and reference/mcp-tool-reference.md:47 | `changed_files=null`. / `changed_files=[]`. | the same token followed by `, claim_evidence=false, behavioral_claims_path=null, prior_claims_path=null, probe_claims=false, runtime_path=null, image_ref=null, allow_network=false, allow_build=false, allow_slow=false, allow_artifact_write=false.` |
| reference/mcp-tool-reference.md:20 | with no Rush grant gating that call; | only when `allow_network` is granted (without it no provider call is made); |
| user-guide/working-with-ai-agents.md:102-104 | `use_llm=true` sends findings to a configured external LLM; no Rush grant gates it." Turning on `use_llm` is a data-egress decision the caller makes explicitly, not a permission Rush enforces. | `use_llm=true` sends findings to a configured external LLM only with allow_network." Sending findings to a model is a data-egress decision that Rush gates behind the `allow_network` grant. |
| reference/result-reference.md:64 | provider remains null unless the stub path is activated. | provider is `null` unless `--llm` ran with `--allow-network` and a provider returned a completed response. |
| safety/permissions.md:11 | Semgrep registry) | Semgrep registry, `review --llm` provider calls) |
Additions: (a) docs/reference/result-reference.md new review subsection: status `skipped`
with metadata.assessed_files and metadata.unassessed_reason (R1), metadata.llm, the 12-key
metadata.claims record, metadata.invalidated_claims reasons, and the Probe states table of
this plan verbatim. (b) docs/safety/permissions.md: new paragraph under the table "review
--probe-claims needs network, build, slow and artifact-write together, the D10-accepted OCI
runtime and a digest-pinned local image". (c) docs/user-guide/checking-code.md section 1:
new subsection "Source-bound claims and behavioral probes" with the Worked case of this plan.
(d) New docs/adr/0051-review-source-bound-claims-and-isolated-probes.md (Context; decisions
Q01-D1–D4 of the Decision record; W18 dependency; consequences). Historical ADRs
(docs/adr/*) change only their leading "Current status:" paragraph: append to
docs/adr/0012-pluggable-llm-provider-abstraction.md Foundation Q01-DOC-* rows the sentence "`review --llm`
calls the provider only with `--allow-network` (ADR 0051)." only if it
has an existing leading Current status paragraph. Preserve every historical body.
F8's docs/adr/README.md row edits only its leading Current status paragraph,
listing ADR 0050 (F4) and ADR 0051 (Q01), plus approved batch ADRs 0052–0057.
ADR 0007 only points from its leading Current status paragraph to the
permissions table; do not insert a grant table into its historical body. (e) CHANGELOG.md: entry
under "## [0.3.0]" for R1/R2/R3/E1/X1. (f) Update the coverage receipt per M1.
```


### Q01-20: Proposed test merge and formatting

Merge proposed command bodies into tests/test_review.py rather than appending
duplicate imports/helpers. Required additions used by the bodies: hashlib,
json, os, subprocess, sys, Path, pytest, ExecutionPermissions and Finding.
Any belongs in review/llm.py for its new signature, not in the command tests.
Provider tests retain OpenAIProvider and add json; transport tests import F6
run_cli/run_mcp and their fixture dependencies. Format only touched files
before the implementation ruff checks; no production formatter ran here.

### Q01-21: Template, allowed paths and quality gates

This plan follows docs/templates/task-block-template.md through Required
behavior, Deliverables, Constraints, Checks, Completion and Handoff, while
retaining original R1/R2/R3/E1/X1 ledger and explicit unapproved decisions.

Command-owned allowed paths:
src/rush/tools/review.py; src/rush/review/llm.py; src/rush/review/results.py;
src/rush/review/probe_harness.py; src/rush/providers/base.py;
src/rush/providers/openai.py; src/rush/providers/anthropic.py;
tests/test_review.py; tests/test_tools.py (review cases);
tests/test_providers.py; tests/test_phase57_provider_egress.py (review grants);
docs/adr/0051-review-source-bound-claims-and-isolated-probes.md.
tests/test_import_order.py is regression-only unless D7 explicitly changes it.

Foundation patch rows, applied only by its owner:
Q01-R3-registry (tools/__init__.py and tools/registry.py under D7);
Q01-R2-transport (cli.py::review, F1 request_models/tool_registry, test_mcp and
test_cli_registry); Q01-R2-description (catalog.py, mcp.py, test_phase70_t5);
Q01-DISC (catalog discovery, CLI help, F1 schema and matching tests);
Q01-M3-paths (tool_registry _CWD_RELATIVE_ARGS);
Q01-OCI-marker/CI (conftest.py, test_no_skips.py, pyproject.toml marker and
.github/workflows/ci.yml); Q01-DOC-* (exact Q01-19/F8 docs, CHANGELOG and
docs/reports/phase-64-66-documentation-coverage.md).
F4 owns isolated_process.py/test_isolated_process.py and F4-START's
src/rush/runtime/subprocesses.py/tests/test_subprocess_contract.py patch row;
F6 owns
tests/transport_parity.py/test_transport_parity.py. Q01 consumes their accepted
interfaces and does not become a second writer.

### Q01-22: Sole shared-file writer and actual transport parity

Foundation owner alone applies Q01-R2-transport and Q01-M3-paths (C16).
Transport tests reside in tests/test_mcp.py; command tests remain in
tests/test_review.py. F6 owns run_cli/run_mcp in tests/transport_parity.py.
Use its Python-3.12 environment, stdout assertions and Windows-safe errlog.

Proposed test_mcp.py fixture/body, importing hashlib/json/Path as used and
`from transport_parity import run_cli, run_mcp` under pytest's tests-directory
import path (F6). No copied stdio client:

```python
def _review_contract(root):
    (root / "src").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    source = root / "src/a.py"
    source.write_text("def f(value):\n    return value\n", encoding="utf-8")
    record = {
        "kind": "return_predicate",
        "path": "src/a.py",
        "module": "src.a",
        "function": "f",
        "source_digest": hashlib.sha256(source.read_bytes()).hexdigest(),
        "predicate": {"op": "ge", "value": 0},
    }
    contracts = root / "contracts.json"
    contracts.write_text(json.dumps([record]), encoding="utf-8")
    return source, contracts, record


def test_review_claim_options_cli_mcp_parity(tmp_path):
    source, contracts, record = _review_contract(tmp_path)
    exit_code, cli_result = run_cli(
        "review",
        tmp_path,
        ("--claim-evidence", "--behavioral-claims-path", str(contracts)),
    )
    assert exit_code == 0
    assert cli_result["status"] == "ok"

    def check_schema(schema):
        assert schema["properties"]["claim_evidence"]["default"] is False
        assert schema["additionalProperties"] is False
        assert "operation" not in schema["properties"]
        assert "schema_version" not in schema["properties"]
        assert set(schema["required"]) == {"path"}
        for name in (
            "project",
            "result_view",
            "limit",
            "max_bytes",
            "no_cache",
            "allow_cache_write",
        ):
            assert name in schema["properties"]

    mcp_result = run_mcp(
        "rush_review",
        {
            "path": str(tmp_path),
            "claim_evidence": True,
            "behavioral_claims_path": str(contracts),
            "project": str(tmp_path),
            "result_view": "full",
            "limit": 50,
            "max_bytes": 65536,
            "no_cache": True,
            "allow_cache_write": False,
        },
        schema_check=check_schema,
    )
    assert mcp_result["status"] == "ok"
    for result in (cli_result, mcp_result):
        claim = next(
            c for c in result["metadata"]["claims"] if c["kind"] == "return_predicate"
        )
        assert claim["source_digest"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert claim["predicate"] == record["predicate"]
        assert claim["status"] == "unverified"
    assert cli_result["metadata"]["claims"] == mcp_result["metadata"]["claims"]
```

### Q01-23: Phase 70 source/memory compatibility

Source revision in this plan is Phase 70
66c6c799eaa5b6017776d659e9e0de2b4a8878a5; c78e445 remains the audit snapshot.
Keep ReviewTool.run's attach_memory_attribution wrapper and the handwritten
review route's @result_view_options. Add options before that decorator;
assemble metadata.llm, claims and probe before memory attribution.

### Q01-24: Probe states and aggregate result

insert after ReviewTool.run probe-state mapping:
```text
Probe evaluation order and states (metadata.probe; aggregate = ToolResult.status):
1 current claim input invalid (any of claim_evidence, probe_claims, behavioral_claims_path, prior_claims_path set) | {"status":"error","reason":"invalid_claim_input"} | error
2 any of the four grants missing | {"status":"denied","reason":"build_or_slow_denied"}, metadata.execution.mode=executed, disposition=not_run, cause=permission_denied; summary names every missing flag; findings/scope preserved | skipped (C-11/F3)
3a runtime/image absent or untrusted runtime | {"status":"skipped","reason":"isolation_unavailable"} | unchanged; no invented receipt/count
3c F4 IsolationUnavailable after inspection | {"status":"skipped","reason":"isolation_unavailable", process_launches: exc.process_launches} | unchanged; no target ran, no fabricated receipt
3b runtime passed but image reference malformed (ValueError) | metadata.probe={"status":"error","reason":"invalid_argument","message":str(error)}, metadata.error={"code":"invalid_argument","message":summary}; summary="review: "+str(error) | error; neither ordinary nor specialist provider called
4 no return_predicate record | {"status":"skipped","reason":"no_source_bound_claims"} | unchanged
5 provider None or not completed | {"status":"skipped","reason":"specialist_unavailable"} | unchanged
6 candidate targets a heuristic record | {"status":"skipped","reason":"unsupported_claim_kind"} | unchanged
7 candidate not a JSON object, bad keys, op outside eq/ne/ge/gt/le/lt, args not a list, or module/function/predicate differs from the contract | {"status":"error","reason":"invalid_candidate"} | error
8 candidate claim_id unknown or source_digest differs from current | {"status":"stale_source"} | unchanged
9a nonzero exit | {"status":"error","reason":"probe_process_failed","isolation_receipt":proc.receipt} | error
9b timeout | error/probe_process_failed/failure=timeout, preserve supplied exc.receipt as isolation_receipt and exc.process_launches | error
9c exhausted launch budget | error/probe_process_failed/failure=launch_budget_exhausted, process_launches=exc.process_launches; no fabricated receipt | error
9d IsolatedCleanupError | error/probe_process_failed/failure=cleanup_failed, message=str(exc), preserve exc.receipt/process_launches with cleanup_confirmed=false | error; never unavailable
9e runtime-call OSError or filesystem/containment/ValueError | error/probe_process_failed, message=str(exc), preserve receipt/count only if supplied | error
9f SubprocessCancelled | skipped/cancelled, preserve receipt/count only if supplied, execution.mode=executed/disposition=cancelled/cause=ambient cause or cancelled, mark existing ambient CancelScope.hit | skipped; findings/scope/current claims preserved, no metadata.error or counterexample
10 malformed/non-finite stdout, non-bool predicate_holds, mismatched source_path/executed_source_digest, inconsistent predicate result or invalid invocation-bound F4 receipt (runtime path/hash, pinned image digest, mounts, owner/run strings, integer counts, network/output) | {"status":"error","reason":"invalid_receipt","isolation_receipt":proc.receipt} | error
11 valid stale-capture envelope or source digest after the run differs | {"status":"stale_source","isolation_receipt":proc.receipt} | unchanged
12 predicate false / true | {"status":"falsified"|"not_falsified", claim_id, input, predicate, observed, source_digest, executed_source_digest, isolation_receipt} | unchanged
```

Q01-13 runs no-launch preflight once before either provider when probe_claims
is enabled, including use_llm+probe_claims. The fixed OCI harness captures and
hashes target bytes once, installs its target-only captured loader, then uses
normal package imports; execution compiles those bytes. Normal stdout has
exactly predicate_holds, observed, source_path and executed_source_digest.
A source mismatch before loading emits exactly status=stale_source,
source_path and captured_source_digest, invokes no target, and retains its
validated F4 receipt. Host validates both envelopes and the executed digest;
ordinary before/after host hashing alone does not bind executed bytes.

Timeout, cleanup failure, exhausted launch budget and filesystem/containment
exceptions use Q01-13's explicit `probe_process_failed` variants. Preserve
proc.receipt or exc.receipt whenever supplied; exception exit_code may be null,
cleanup_confirmed is factual, and target_started=null means unknown. Preserve
actual supplied process_launches; never manufacture zero for missing evidence.
Cancelled target cleanup retains skipped/cancelled execution carrier and ambient
cause; failed cleanup overrides cancellation with error/cleanup_failed. Counts
refer to accepted host child starts, not container-target execution. Runtime hash
is pre/post supplied-path snapshot only, no transient binary attestation. Target
source executed_source_digest binding remains required. Success binds `claim_id` to the exact current
record: falsified attaches its counterexample; not_falsified leaves that
record unverified with counterexample=null. Neither changes ordinary review status.


### Q01-25: Worked behavioral counterexample

insert after checking-code.md worked-case row:
```text
Worked case. Before: `rush review . --json` reports missing-docstring on src/a.py::f; nothing
challenges f's documented contract. After: with contracts.json containing
[{"kind":"return_predicate","path":"src/a.py","module":"src.a","function":"f",
"source_digest":"<sha256 of src/a.py>","predicate":{"op":"ge","value":0}}],
`rush review . --behavioral-claims-path contracts.json --probe-claims --allow-network
--allow-build --allow-slow --allow-artifact-write --runtime-path "$(command -v docker)"
--image-ref python@sha256:<64 hex> --json` returns metadata.probe
{"status":"falsified","input":[-1],"observed":-1,"predicate":{"op":"ge","value":0},
"source_digest":"<sha256>","isolation_receipt":{"network":"none","image_ref":"python@sha256:<64 hex>",
"exit_code":0,"output_sha256":"<sha256>"}}. Editing f changes the digest and the claim_id and
turns the old record into metadata.invalidated_claims reason source_changed. Why new: existing
Rush review and commodity linters or reviewers report static observations only; this is absent from current Rush review. A static lint/review invocation alone does not
provide this digest-bound candidate, isolation receipt and source-invalidation loop.
```


### Q01-M1: The documentation and runtime-contract gate (`scripts/sync_docs.py --check`) is not planned

add to Deliverables a final step and to Checks the `sync_docs.py --check` command (Q01-21 item 4):
```text
Final step after code and docs are frozen: regenerate docs/reports/phase-64-66-documentation-coverage.md
with `uv run --python 3.12 --extra dev python - /absolute/frozen/source/root` over this script
(pass this script on stdin), then add audience/authority/evidence for every new doc
(docs/adr/0051-*.md: audience "maintainers", authority "current"). Historical docs keep their
immutable_body_sha256 untouched.
    import hashlib, importlib.util, json, sys
    from pathlib import Path
    root = Path(".")
    frozen_source = Path(sys.argv[1]).resolve(strict=True)
    if frozen_source == root.resolve():
        raise ValueError("Frozen source must differ from destination checkout")
    copied_prerequisites = {
        f"docs/phase-plans/command-tdd-2026-10-01/{name}"
        for name in (
            "README.md", "00-shared-foundation.md", "01-rush-review.md",
            "02-rush-lint.md", "03-rush-format.md", "04-rush-test.md",
            "05-rush-security.md", "06-rush-typecheck.md", "07-rush-dead.md",
            "08-rush-complexity.md", "09-rush-slop.md", "10-rush-markdown.md",
        )
    } | {
        "docs/reports/cli-mcp-command-audit-2026-09-26.md",
        "docs/reports/command-tdd-2026-10-01-plan-remediation.md",
    }
    transfer_sha256 = {
        path: hashlib.sha256((frozen_source / path).read_bytes()).hexdigest()
        for path in sorted(copied_prerequisites)
    }
    for path, expected in transfer_sha256.items():
        copied = hashlib.sha256((root / path).read_bytes()).hexdigest()
        unchanged = hashlib.sha256((frozen_source / path).read_bytes()).hexdigest()
        if copied != expected or unchanged != expected:
            raise ValueError(f"Prerequisite copy differs or source changed: {path}")
    spec = importlib.util.spec_from_file_location("sync_docs", root / "scripts/sync_docs.py")
    sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
    report = root / sd.REPORT_PATH
    text = report.read_text(encoding="utf-8")
    m = sd.BLOCK_RE.search(text)
    receipt = json.loads(m.group("payload"))
    receipt["contracts"] = sd.collect_runtime_contracts(root)
    owned_new_docs = {
        "docs/adr/0050-oci-isolation-provider.md": [
            "tests/test_isolated_process.py::test_receipt_fields",
            "tests/test_isolated_process.py::test_container_denies_worktree_write_and_network",
        ],
        "docs/adr/0051-review-source-bound-claims-and-isolated-probes.md": [
            "tests/test_review.py::test_claim_source_digest_invalidation",
            "tests/test_review.py::test_probe_claim_counterexample",
            "tests/test_review.py::test_probe_executes_digest_captured_source_during_host_mutation",
        ],
    }
    for entry in receipt["documents"]:
        if entry["path"] != sd.REPORT_PATH:
            entry["sha256"] = sd.document_digest(root / entry["path"])
    have = {e["path"] for e in receipt["documents"]}
    for e in sd.build_document_inventory(root):
        if e["path"] not in have:
            if e["path"] in copied_prerequisites:
                e.update(
                    audience="maintainers", authority="current",
                    evidence=[f"Byte-identical prerequisite: {e['path']} sha256={transfer_sha256[e['path']]}"],
                )
            elif e["path"] in owned_new_docs:
                e.update(audience="maintainers", authority="current",
                         evidence=owned_new_docs[e["path"]])
            else:
                raise ValueError(f"Unowned new documentation: {e['path']}")
            receipt["documents"].append(e)
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    report.write_text(text[: m.start("payload")] + payload + text[m.end("payload"):], encoding="utf-8")
```

Foundation F8 executes this packet only after its cited acceptance tests pass
and the exact 14 prerequisite files above have been frozen and copied to the
Phase 70 checkout byte-for-byte. Its source-root argument identifies that frozen
corpus; a missing file, changed source, or differing destination stops before
the receipt is written. Transfer evidence records raw SHA256; inventory hashes
still use `sync_docs.py`'s document-digest rules. The final `sync_docs.py --check`
must exit 0 with no missing documentation or contract drift. This registration
does not establish implementation acceptance for the copied planning corpus.
The concrete map above owns F4 ADR 0050 and Q01 ADR 0051. Each later approved
ADR packet extends `owned_new_docs` with its exact filename and executed test
references before using this same regeneration code (C22); no wildcard ADR
approval or rejection of already registered prior packet entries.


### Q01-M2: The packaged harness is read by filesystem path; the frozen binary does not ship it

applied inside the Q01-13 fix (`probe_harness.py` holds one `PROBE_HARNESS_SOURCE` constant imported as a normal module, which PyInstaller bundles by import analysis). No data-file entry is needed.


### Q01-M3: Relative-path anchoring and containment of the new Path inputs are unspecified

add to Deliverables:
```text
src/rush/mcp_support/tool_registry.py::_CWD_RELATIVE_ARGS gains
"review": ("behavioral_claims_path", "prior_claims_path"), anchoring
relative values like the target (declared root, else server-start cwd). In ReviewTool,
behavioral_claims_path and prior_claims_path must resolve inside the review root: an absolute
value is made relative with Path.relative_to(root) (failure -> invalid_claim_input), then opened
with PhysicalRoot(root).open_contained(rel, purpose="read"); the file must be a regular file of
at most 1 MiB holding a UTF-8 JSON array, else invalid_claim_input. runtime_path is the one
absolute host path and follows Q01-12.
```


### Q01-M4: Cross-plan exclusivity conflict on shared files

README Roles/C16 govern: Foundation sole shared-file writer; exact Q01 rows, no first-writer rule. Q04 consumes same Foundation; no executor/config adaptation.


## Checks to run before reporting

All implementation checks must pass. C19's only exceptions are the five
Claude-reported baseline nodes below, and only if failure is identical before
and after the packet; none was rerun or independently certified here:
- test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[core]
- test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[full]
- test_no_skips.py::test_no_collected_test_carries_a_live_skip_marker
- test_phase70_t12.py::test_t12_pyrefly_argv_no_directory_arg_when_explicit_files
- test_phase70_t12.py::test_t12_typecheck_config_routes_python_family
Zero SKIPPED; only declared marker-based deselection is allowed outside OCI CI.
Every packet report verification command remains acceptance requirement;
implementation-dependent commands run only after named source/tests exist.

```text
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_review.py tests/test_tools.py tests/test_engines.py tests/test_import_order.py tests/test_providers.py tests/test_phase57_provider_egress.py tests/test_cli_registry.py tests/test_mcp.py tests/test_transport_parity.py tests/test_phase70_t5.py tests/test_phase70_t16.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy git diff --check
```

Use union X13+C20+per-packet module lists, never replace narrower lists.
R/E exclude F4-created modules until F4; X1 adds tests/test_isolated_process.py,
tests/test_isolated_tests.py and command live OCI files after creation, plus the
existing tests/test_subprocess_contract.py regression gate for F4-START.
After F4 and the Q01 exception tests exist, run the targeted exception/runtime
alignment command in Q01-16 and the shared subprocess-contract module:
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_subprocess_contract.py -q.
OCI CI: rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python
-m pytest -p no:cacheprovider tests -m oci_isolation -q.

## Completion, failure, recovery, stop conditions and risks

Invalid schema/identity/containment rejects unsafe operation. Grant/runtime/
engine absence explicit branches, never fallback. Preserve ordinary findings
where binding contract requires. Persistent artifacts only specified paths;
clean invocation-owned scratch only. Partial apply factual changed paths/hashes,
never rollback. Drift invalidates prior receipts. Unapproved decisions block
dependent implementation choice, not remediation.

Current deliverable only this plan. Implementation completion requires full
R/E/X behavior, named tests, exact real CLI/stdio parity, live OCI where needed,
docs gate, frozen hash and declared-path diff. Literal Command-owner paths
Deliverables above; every shared file via Q01-<packet> or
Q01-DOC-<subject> exact Foundation row. No next batch/commit/push authorized.

## Handoff

One authoritative plan, no auxiliary runner/report. Receipt includes hash,
finding IDs/status, exact verification/results and unresolved James decisions/
external prerequisites. No future behavior PASS from plan static checks.

## Review reconciliation

Q01-01–25 and Q01-M1–M4 retain their own implementation sections above.
No production/test execution is claimed. Binding changes explicitly replace
earlier report checks: Q01-11's zero budget-field grep is overridden by C03;
Q01-19's ADR 0050 grep is overridden by C22 (Q01 ADR 0051);
Q01-22/M4 first-writer wording is overridden by C16 (Foundation sole writer).
Q01-17/22 use F6's shared transport helpers instead of a local stdio session.
All implementation-dependent report commands remain proposed until their
named source, tests, Foundation contracts and approved decisions exist.

### Plan00 alignment reconciliation (2026-10-02)

Local alignment IDs below identify this follow-up, not additional Claude finding IDs. Frozen starting Plan00 SHA256: f1c2ab2fb48597f8c6f5131f440e2a3337e6dfbe626bc67b55340be51c0c46c6; Plan01 SHA256: 42be071461fda7353aaf25cc813030ba6606e577dfc9da0d96220a9fd17b2828. Current grounding remains Phase70 66c6c799eaa5b6017776d659e9e0de2b4a8878a5, with the binding audit/final resolutions and T1–T29/G0–G8/design briefs above. APIs introduced by F4/F5 and Q01 remain proposed; current ReviewTool.run has no probe/permission interface.

| Alignment issue / controlling evidence | Concrete correction | Proposed executable acceptance / exact effect |
| --- | --- | --- |
| A01: F4/C03/C09 factual exception evidence; old Q01-13 handlers discarded it | Q01-13 copies supplied exception receipt and process_launches; cleanup_failed/timeout/process failures remain error, with factual cleanup state retained inside receipt. No receipt/count fabricated when absent. | Q01-16 test_probe_launcher_exception_preserves_factual_evidence: raised timeout/OSError/cleanup failure, budget and unavailable branches reach ReviewTool.run's launcher binding; assert exact state/count/receipt/error and preserved findings/scope/claims/source. |
| A02: F4 path-byte snapshots do not attest transient runtime execution | Q01-13 removes actually-launched-binary claim; retains runtime path pre/post hash comparison and independent target-source executed_source_digest validation. | test_probe_runtime_path_byte_drift_is_invalid_receipt mutates runtime bytes during launcher call; expect error/invalid_receipt with original receipt retained. |
| A03: F5 SelectedTestRun field is isolated | Shared-contract summary now names isolated; fixed Q01 harness still does not call F5. | Compare declared dataclass field and consumer summary; no selected-pytest behavior or new consumer introduced. |
| A04: Phase70 T17 cancellation and F4 exception cleanup | Q01-13 catches actual SubprocessCancelled; uses existing CancelScope cause/hit and execution.disposition=cancelled. Confirmed cancellation is skipped, not crash/clean success. Unconfirmed cleanup remains error. | test_probe_cancelled_preserves_scope_and_ambient_cause covers receipt present/absent and ambient scope present/absent; exact summary/execution/status, preserved findings/scope/claims/source, no fabricated receipt/count. |
| A05: F3 executed/not_run denial; permissions.py only copies supplied extras | Q01-13 includes disposition=not_run; Q01-16 denial assertion checks complete execution dictionary. | test_probe_grant_denied_makes_zero_calls asserts exact requested/granted permissions, cause, missing flags, producer and disposition, with zero provider/launcher calls. |
| A06: final C08 supplied-directory plus executable-realpath containment | Plan00 F4 rejects lexical supplied parent, resolved supplied parent and resolved executable inside root. Plan01 retains the binding containment requirement. | Plan00 test_runtime_inside_root_rejected preserves ordinary inside-file rejection, adds inside-root symlink to trusted external runtime and outside spelling whose parent resolves inside root; both preflight/provider reject with zero launches. Existing valid external supplied-name symlink regression retained. |

Shared-contract coverage: F1/F11 typed public-signature models, malformed grants/unknown fields, view/cache/context forwarding and real route parity remain Foundation-owned; F2 preserves scope/aggregation/error and conditional D5; F3 includes A01/A04/A05 carriers; F4 includes A01/A02/A04/A06 and the F4-START prerequisite; F5 has no Q01 execution consumer beyond its corrected summary; F6 real CLI/initialized stdio helper is reused; F7 SBOM is outside Q01 scope; F8 retains exact doc/ADR/history/14-file transfer and inventory rows; F9 malformed-config policy is inherited through Foundation transport handling, with no new Q01 config parser/option; F10 discovery/help/schema has one Foundation owner. No other shared-contract/source, ownership, ordering, documentation, quality-route or readiness conflict was found in the reviewed coverage.

Verification is plan-only: inspect changed bodies/test routes, parse and format changed Python fences, independently review frozen integrated bytes and compare protected hashes. Proposed behavior tests above and live F4/OCI gates remain unexecuted under this Markdown-only task. Final hashes and executed static/preservation results belong in coordinator handoff, outside self-hashed file bytes.

Alignment remediation does not approve D1–D12/Q06 X1 defaults or Q01 claim-model decisions, establish Phase70 acceptance, provision runtime/images, or accept implementation. Ordered entry gates and James's existing decision ownership remain binding. Only Plan00's C08 F4 correction and Plan01 compatibility corrections are authorized here; source/tests/config, other plans and user-owned edits remain protected. Stop for James's review.
