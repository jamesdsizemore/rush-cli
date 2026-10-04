# Q06 — Configuration-faithful typecheck and diagnostic experiments
Status: needs-info
Source revision: c78e445ba1e575ca373e35840142cd627b055d6a
Planning proposal; implementation and checks unexecuted.
Read AGENTS.md and docs/templates/task-block-template.md. Binding audit: Q06 in
/Users/jamesdsizemore/Developer/rush-cli/docs/reports/cli-mcp-command-audit-2026-09-26.md,
SHA256 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Source revision above binds source grounding; later byte drift requires new review.
Batch scope Q01–Q10 only; next batch requires explicit user approval.
Current authorization is standalone plans only: no implementation, commit or push.
Subagent provenance: gpt-6.1-sol, medium; responsibility: Typecheck configuration, checker coverage and diagnostic experiments.
Preserve shared user baseline: scanner provisioning, connected specialist local
models, selectable voice/live speech and 3D companion. These are requested
baseline capabilities, never this command's novel X1 expansion.

## Goal, scope and non-goals
Preserve owning checker configuration, expose real requested/dependency scope,
qualify caller evidence, and explain observed configuration sensitivity.
No source fixes, weakening project policy, installation, hooks, releases,
fabricated graph completeness or downstream W18 implementation.

## Evidence and requirement ledger
| ID | Category and requirement | Source | Exact acceptance |
| --- | --- | --- | --- |
| R1 | Repair config-bypassing file operands | src/rush/tools/typecheck.py:25–65; engines/tsc.py:18–38 | --project/--listFiles, no TS file operands |
| R2 | Repair duplicate root/file cwd | engines/pyrefly.py:18–55 | Selected vector once; directory cwd |
| R3 | Repair child coverage | tools/routing.py::aggregate_results | Missing applicable checker stays partial |
| E1 | Ordinary override/caller evidence | Audit Q06:2990–2992,3134–3160 | Contained override, current complete graph only |
| X1 | Expansion: diagnostic option trials | Audit Q06:3167–3245 | Actual suppressing option, unchanged policy |

## Required behavior and proposed interface
Add typecheck_config: Path|None=None, caller_graph_path: Path|None=None,
explain_config_effect: str|None=None, runtime_path: Path|None=None,
image_ref: str|None=None, boolean allow_build=False/allow_slow=False.
CLI --typecheck-config, --caller-graph-path, --explain-config-effect,
--runtime-path, --image-ref, --allow-build and --allow-slow; MCP identical
validated inputs. Path/string options default None; grant flags default false.
Existing run(config=None) preserved. Invalid grant type/config escape => error.

Group TS targets by nearest contained tsconfig.json; explicit contained
typecheck_config overrides. Invoke TSC --noEmit --project CONFIG --listFiles
without file operands. Record requested paths and actual dependency file list
separately; off-request diagnostics remain dependency diagnostics, not invented
requested-file coverage. Parse emitted file-list evidence without treating path
lines as diagnostics. Unsupported/no owning config is explicit unassessed,
never silent loss of aliases/options.

Group Python targets by verified owning mypy/Pyrefly config protocol. Directory
cwd, selected operands once, direct-call fallback preserved. Installed checker
protocol must be captured before claiming accepted config dispatch.
Shared child receipts preserve missing engines and error/finding severity.

Caller graph schema version1, complete=true, sources relative path→SHA256,
edges diagnostic/caller/evidence_id. Validate containment, IDs and every digest.
Stale/incomplete graph => diagnostic_callers={status:"unassessed",edges:[]}.
Explicit override wins only for requested invocation; original config unchanged.

Experiment target diagnostic ID e.g. TS2322@src/null.ts:1 must be reproduced.
Build+slow and genuine OCI required. One-option false trials for exactly
strictNullChecks/noUnusedLocals/noImplicitAny/exactOptionalPropertyTypes;
max eight checker processes including baseline/trials/confirmation. Record each
actual result, unchanged source/config hashes, suppressing_options and
policy_recommendation="none". Incomplete/error trials remain unassessed.
Missing OCI => skipped/isolation_unavailable, no direct subprocess fallback.

## Deliverables, dependencies and ownership
Own src/rush/tools/typecheck.py::TypecheckTool.__call__/run and new local
_group_checker_targets, _validate_caller_graph, _experiment_config;
src/rush/engines/pyrefly.py::PyreflyEngine.run;
src/rush/engines/tsc.py::TscEngine.run/normalize for project/file-list evidence;
tests/test_typecheck.py. Change mypy adapter only if captured protocol requires
it; declare that literal path before implementation, never improvise during fix.
Foundation exclusively owns routing.py aggregate child receipts and catalog/
generic CLI forwarding, plus actual CLI/MCP parity tests.
After executable routes, documentation owner updates docs/reference/
cli-reference.md, mcp-tool-reference.md/result-reference.md.

W18 contract: local digest-pinned compiler image, read-only original source/
config, owned writable sandbox, denied network/home writes, bounded resources/
time/output/process count, runtime/owner/run receipts and cleanup. Real
tests/test_isolated_process.py denial acceptance; fake launcher insufficient.

Local shared-transport acceptance: every listed CLI option must reach the typed
callable unchanged; actual CLI and MCP invocations return equivalent semantic
findings, assessment scope, grants and explicit unavailable-child evidence.
Permission values require real booleans; invalid values return canonical error.
Shared routing preserves each child's engine/version/status/assessed paths and
findings; complexity children additionally preserve producer-qualified unit/value
rows. Missing applicable assessment marks partial coverage; otherwise-clean
partial aggregate is skipped; existing error/fail/warn severity remains intact.
Slop retains its own language assessment rows; shared routing cannot replace them.

Required proposed isolation interface, supplied by separate W18 ownership:
src/rush/runtime/isolated_process.py::run_isolated_argv(source_root, output_dir,
*, runtime_path, image_ref, entrypoint, argv, timeout_s) returns real
returncode/stdout/stderr. Use timeout_s=300, explicit executable and argv list,
never shell text; require local digest-pinned image, network disabled and owned
scratch. Backend absence raises IsolationUnavailable and follows this plan's
skipped/isolation_unavailable rule. Accept only after real denial/cleanup tests;
this API is a prerequisite proposal, not claimed existing implementation.

## Ordered RED/GREEN tasks
1. test_tsconfig_aliases_survive_file_target: src/a.ts imports alias "@/b";
   owning config maps alias. Assert no TS2307, project argv/no file operands,
   actual requested/dependency lists. test_explicit_config_precedence uses two
   configs and selected override. Minimum config-grouping/parser fix.
2. test_pyrefly_file_cwd_is_directory captures file-target argv/cwd; file once,
   no duplicate root. test_missing_checker_is_partial preserves skipped child.
3. test_diagnostic_callers_refuse_stale_graph changes source after graph creation
   => unassessed/empty edges; escaped graph/config => error.
4. test_config_experiment_identifies_strict_null_checks: strict fixture
   "const value: string = null;" => actual TS2322; only strictNullChecks=false
   suppresses it. Assert exact list ["strictNullChecks"], policy none, original
   bytes unchanged and total checker runs <=8. Denial/unavailable/timeout tested.
5. test_typecheck_options_cli_mcp_parity exercises actual transmitted options,
   configuration precedence and same semantic child coverage.

## Runnable proposed RED bodies and transport acceptance

All following code is proposed for the named tests/test_typecheck.py,
unimplemented and unexecuted. Copy both blocks into that existing test module;
all helpers/imports are defined here. pytest is already installed by dev extra.
Captured adapter reports below test parser/controller boundaries; they do not
prove live engines or OCI isolation. Live tests require captured engine versions,
Git and W18's real local digest-pinned images. RUSH_TEST_OCI_RUNTIME is an
absolute installed runtime path; RUSH_TEST_RUSH_IMAGE pins the current Rush image;
Q06 additionally requires RUSH_TEST_COMPILER_IMAGE with matching TSC/source.
Missing prerequisites block acceptance; do not skip these cases into a PASS.

Proposed exact result fields: metadata.requested_paths and dependency_paths
contain absolute paths; diagnostic_scopes maps RULE@project-relative-path:line
to requested/dependency. metadata.children/partial follow local foundation
contract. File targets inside Git use verified git rev-parse --show-toplevel
as containment/config-search root; non-Git file targets use parent directory.
Config experiment records checker_process_count including baseline/confirmation.

```python
import hashlib, json, os, shutil, subprocess
from pathlib import Path
from types import SimpleNamespace
import rush.tools.typecheck as module
from rush.tools.typecheck import TypecheckTool
from rush.engines.pyrefly import PyreflyEngine

def git_fixture(root):
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Fixture", "-c", "user.email=f@example.test",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

def test_tsconfig_aliases_survive_file_target(tmp_path, monkeypatch):
    assert shutil.which("tsc"), "Acceptance prerequisite: installed version-pinned tsc"
    src = tmp_path / "src"; src.mkdir()
    a = src / "a.ts"; b = src / "b.ts"
    a.write_text('import {value} from "@/b"; export const answer = value;\n')
    b.write_text('export const value: number = "wrong";\n')
    config = tmp_path / "tsconfig.json"
    config.write_text(json.dumps({"compilerOptions": {"strict": True,
        "baseUrl": ".", "paths": {"@/*": ["src/*"]}}, "include": ["src/*.ts"]}))
    git_fixture(tmp_path)
    calls = []; actual = module.run_engine
    def observe(engine, path, args, **kwargs):
        calls.append((engine.name, list(args)))
        return actual(engine, path, args, **kwargs)
    monkeypatch.setattr(module, "run_engine", observe)
    result = TypecheckTool().run(a, typecheck_config=Path("tsconfig.json"))
    assert [args for name, args in calls if name == "tsc"] == [
        ["--project", str(config), "--listFiles"]]
    assert [f["rule"] for f in result["findings"]] == ["TS2322"]
    assert result["metadata"]["requested_paths"] == [str(a)]
    assert str(b) in result["metadata"]["dependency_paths"]
    assert result["metadata"]["diagnostic_scopes"]["TS2322@src/b.ts:1"] == "dependency"
    override = tmp_path / "override.json"
    override.write_text(config.read_text())
    calls.clear()
    TypecheckTool().run(a, typecheck_config=Path("override.json"))
    assert [args for name, args in calls if name == "tsc"] == [
        ["--project", str(override), "--listFiles"]]

def test_pyrefly_file_cwd_is_directory(tmp_path, monkeypatch):
    import rush.engines.pyrefly as adapter
    source = tmp_path / "a.py"; source.write_text("answer: int = 7\n")
    calls = []
    def child(argv, **kwargs):
        calls.append((argv, kwargs["cwd"]))
        return SimpleNamespace(returncode=0, stdout='{"errors":[]}', stderr="")
    monkeypatch.setattr(adapter, "run_subprocess", child)
    PyreflyEngine().run(source, [str(source)])
    assert calls[0][0].count(str(source)) == 1
    assert calls[0][1] == tmp_path

def test_missing_checker_is_partial(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("answer: int = 7\n")
    def child(engine, *args, **kwargs):
        return dict(tool="typecheck", engine=engine.name, engine_version=None,
            status="skipped" if engine.name == "pyrefly" else "ok",
            duration_ms=0, summary="controlled availability", findings=[])
    monkeypatch.setattr(module, "run_engine", child)
    result = TypecheckTool().run(tmp_path)
    assert {c["engine"]: c["status"] for c in result["metadata"]["children"]} == {
        "mypy": "ok", "pyrefly": "skipped"}
    assert result["status"] == "skipped"
    assert result["metadata"]["partial"] is True

def test_diagnostic_callers_refuse_stale_graph(tmp_path):
    assert shutil.which("tsc"), "Installed tsc required; skip is not acceptance"
    src = tmp_path / "src"; src.mkdir()
    a = src / "a.ts"; b = src / "b.ts"
    a.write_text("export const value: string = null;\n")
    b.write_text('import {value} from "./a"; export const caller = value;\n')
    (tmp_path / "tsconfig.json").write_text(json.dumps({
        "compilerOptions": {"strict": True}, "include": ["src/*.ts"]}))
    edges = [{"diagnostic": "TS2322@src/a.ts:1", "caller": "src/b.ts::caller",
              "evidence_id": "fixture-edge-1"}]
    graph = {"version": 1, "complete": True, "sources": {
        f"src/{p.name}": hashlib.sha256(p.read_bytes()).hexdigest() for p in (a,b)},
        "edges": edges}
    (tmp_path / "callers.json").write_text(json.dumps(graph))
    git_fixture(tmp_path)
    args = dict(typecheck_config=Path("tsconfig.json"),
                caller_graph_path=Path("callers.json"))
    assert TypecheckTool().run(a, **args)["metadata"]["diagnostic_callers"] == {
        "status": "assessed", "edges": edges}
    b.write_text("// changed\n" + b.read_text())
    assert TypecheckTool().run(a, **args)["metadata"]["diagnostic_callers"] == {
        "status": "unassessed", "edges": []}

def test_config_experiment_identifies_strict_null_checks(tmp_path):
    assert shutil.which("tsc"), "Version-pinned tsc required"
    source = tmp_path / "a.ts"; source.write_text("const value: string = null;\n")
    config = tmp_path / "tsconfig.json"
    config.write_text(json.dumps({"compilerOptions": {"strict": True},
                                  "include": ["a.ts"]}))
    git_fixture(tmp_path)
    before = {p: p.read_bytes() for p in (source, config)}
    options = dict(typecheck_config=Path("tsconfig.json"),
        explain_config_effect="TS2322@a.ts:1",
        runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
        image_ref=os.environ["RUSH_TEST_COMPILER_IMAGE"])
    denied = TypecheckTool().run(tmp_path, **options)
    assert denied["status"] == "error"
    result = TypecheckTool().run(tmp_path, **options, allow_build=True, allow_slow=True)
    trial = result["metadata"]["config_experiment"]
    assert trial["suppressing_options"] == ["strictNullChecks"]
    assert trial["policy_recommendation"] == "none"
    assert trial["checker_process_count"] <= 8
    assert {p: p.read_bytes() for p in before} == before
```

Actual stdio MCP body uses repository's established ClientSession/stdio_client
pattern (tests/test_mcp.py:234–282), not in-process FastMCP calls or registry-only
checks. Both subprocesses use same checkout src and real command fixture.

```python
def test_typecheck_options_cli_actual_stdio_mcp_parity(tmp_path):
    import json, os, shutil, subprocess, sys, tempfile
    from pathlib import Path
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    project = Path(__file__).resolve().parents[1]
    env = {**os.environ,"PYTHONPATH":str(project/"src")}
    assert shutil.which("tsc"), "Installed version-pinned tsc required"
    (tmp_path/"a.ts").write_text("export const value: string = null;\n")
    (tmp_path/"tsconfig.json").write_text(json.dumps({
        "compilerOptions":{"strict":True},"include":["a.ts"]}))
    proc = subprocess.run([sys.executable,"-m","rush.cli","typecheck",str(tmp_path),
        *["--typecheck-config","tsconfig.json"],"--json"],cwd=project,env=env,capture_output=True,text=True,timeout=180)
    left = json.loads(proc.stdout)
    async def exchange():
        params = StdioServerParameters(command=sys.executable,
            args=["-m","rush.cli","mcp","serve"],cwd=project,env=env)
        with tempfile.TemporaryFile(mode="w+",encoding="utf-8") as errlog:
            with anyio.fail_after(180):
                async with stdio_client(params,errlog=errlog) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        response = await session.call_tool("rush_typecheck",{"path":str(tmp_path),"typecheck_config":"tsconfig.json"})
                        assert response.isError is False
                        assert response.content
                        return json.loads(response.content[0].text)
    right = anyio.run(exchange)
    assert (left["tool"],left["status"]) == (right["tool"],right["status"])
    keys = ("path","line","column","rule","severity","message","rule_id","source_config_digest")
    assert [{k:f.get(k) for k in keys} for f in left["findings"]] == [
        {k:f.get(k) for k in keys} for f in right["findings"]]
    assert left["status"] == "fail"
    assert [f["rule"] for f in left["findings"]] == ["TS2322"]
    assert left["metadata"]["requested_paths"] == [str(tmp_path/"a.ts")]
    assert left["metadata"]["requested_paths"] == right["metadata"]["requested_paths"]
    assert left["metadata"]["diagnostic_scopes"] == right["metadata"]["diagnostic_scopes"]
```

## GREEN, refactor and regression gates

Run this module first on frozen baseline and retain specific failing assertion,
not import/environment failure, as RED evidence. For each preceding ordered
packet: implement only its named shared path, rerun corresponding named body,
then regression-check all earlier passing bodies. After every packet, refactor
only duplication introduced by that packet; repeat the full module once on
changed bytes. Retain CLI + actual stdio body in the final regression run.
Complete selected parser/config/coverage/ordinary-extension tests before X1;
X1's real execution tests and external denial/cleanup acceptance remain required.
Never label mocked availability/scanner/controller checks as real engine/isolation
verification. Timeout, invalid receipt, path escape and denied grants must retain
original files and failure receipts; no relaxed assertion or status-membership pass.


## Checks, failure/recovery, stops and reconciliation
Capture real installed mypy/Pyrefly/TSC clean/error/config fixtures before
protocol acceptance. Unproved configuration ownership blocks affected packet.
Freeze bytes before verification; preserve original policy and failure evidence,
cleanup owned scratch only; source drift invalidates trial.

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_typecheck.py tests/test_cli_registry.py tests/test_mcp.py tests/test_isolated_process.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts

Reconcile R1–R3/E1/X1 with actual protocol/version evidence, executed assertions,
frozen hash and declared-file diff. No commit/push, automatic recommendation or
completion claim while configuration/OCI prerequisites remain unresolved.
