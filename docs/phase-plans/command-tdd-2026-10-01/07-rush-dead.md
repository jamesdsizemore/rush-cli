# Q07 — Trustworthy dead-code candidates and runtime reachability
Status: needs-info
Source revision: c78e445ba1e575ca373e35840142cd627b055d6a
Planning only; proposed code/tests unimplemented and unexecuted.
Read AGENTS.md and docs/templates/task-block-template.md. Binding audit: Q07 in
/Users/jamesdsizemore/Developer/rush-cli/docs/reports/cli-mcp-command-audit-2026-09-26.md,
SHA256 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f.
Source revision above binds source grounding; later byte drift requires new review.
Batch scope Q01–Q10 only; next batch requires explicit user approval.
Current authorization is standalone plans only: no implementation, commit or push.
Subagent provenance: gpt-6.1-sol, medium; responsibility: Dead-code protocols, static candidate evidence and runtime reachability.
Preserve shared user baseline: scanner provisioning, connected specialist local
models, selectable voice/live speech and 3D companion. These are requested
baseline capabilities, never this command's novel X1 expansion.

## Goal, scope and non-goals
Separate engine failure from clean scans, qualify static candidates and reject
deletion candidates actually invoked by selected tests. Never delete code,
claim zero calls prove dead code, install engines/hooks, change releases,
fabricate graph evidence or implement downstream W18.

## Evidence and requirement ledger
| ID | Category and requirement | Source | Acceptance |
| --- | --- | --- | --- |
| R1 | Repair exit/output masking | src/rush/engines/vulture.py:36–61; knip.py:18–61 | Nonzero empty/malformed => error |
| R2 | Repair missing child coverage | tools/dead.py:22–58; routing.aggregate_results | Missing Knip remains skipped/partial |
| E1 | Ordinary digest-bound static evidence | Audit Q07:3283,3361–3384 | Dynamic callbacks uncertain, stale exceptions invalid |
| X1 | Expansion: observed runtime reachability | Audit Q07:3399–3517 | Hit rejects deletion; miss remains unknown |

## Required behavior and proposed interface
Add confirm_reachability=False, probe_candidate: str|None=None,
probe_tests: list[str]|None=None, runtime_path: Path|None=None,
image_ref: str|None=None, boolean allow_build=False/allow_slow=False.
CLI --confirm-reachability, --probe-candidate, repeatable --probe-tests,
--runtime-path, --image-ref, --allow-build and --allow-slow; repeatable tests
forward as probe_tests list. MCP identical types/defaults. Preserve run(config=None).

Vulture exit0 with empty valid report => ok; exit3 with parsed findings => warn.
Other exits, truncated/malformed findings and exit/report contradiction => error.
Knip uses --reporter json --no-exit-code; require object with issues list;
normalize unused export by file/name/line. Nonzero or malformed JSON => error.
Capture versioned valid/error fixtures; audit observed Knip6.35.1 only.
Keep deterministic findings and per-engine assessed paths/status/version.

confirm_reachability resolves exact definition path/name/line and SHA256.
Candidate fields symbol/definition_digest/static_refs/dynamic_entrypoint/
confidence/evidence_ids. Dynamic registrations, decorated callbacks, unresolved
imports/reflection and incomplete graph remain uncertain/unknown. AST name
matching alone never proves complete reference graph. Digest-bound exceptions
expire after definition change. No deletion recommendation from absence alone.

Probe requires confirmed contained candidate, nonempty explicit contained tests,
build+slow and real pinned OCI backend. Instrument only that definition in
owned sandbox via generated local pytest plugin; no global hooks.
Record actually calling test IDs. Any hit => deletion_decision="reject";
zero hits => "unknown"; no fabricated test IDs or coverage. Denied grants =>
error/permission_denied; missing backend => reachability_probe.status=skipped,
reason=isolation_unavailable. Parse failures/timeouts => error; source drift
invalidates result. Original source/test/config unchanged.

## Deliverables, dependencies and ownership
Own src/rush/tools/dead.py::DeadTool.__call__/run plus local
_build_candidate_evidence and _probe_candidate;
src/rush/engines/vulture.py::VultureEngine.normalize;
src/rush/engines/knip.py::KnipEngine.run/normalize; tests/test_dead.py.
Foundation owns shared routing child receipts, catalog/generic CLI forwarding
and tests/test_cli_registry.py/tests/test_mcp.py parity.
After executable routes, documentation owner updates docs/reference/
cli-reference.md, mcp-tool-reference.md/result-reference.md.

Graph evidence provider/coverage schema must be verified before accepting
evidence_ids. W18 requires local digest-pinned pytest image with dependencies,
read-only originals, owned writable instrumented copy, network/home-write
denial, process/resource/time/output bounds, owner/run receipts and cleanup.
Real tests/test_isolated_process.py acceptance; mocks insufficient.

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
1. test_nonzero_empty_is_error: each normalizer exit2/empty => exact error.
   Vulture stdout "src/app.py:1: unused function 'callback' (60% confidence)\n"
   with exit3 => status warn, one finding at src/app.py:1, rule vulture.
   Knip exit0 JSON {"issues":[{"file":"lib.js","exports":[{"name":"unused",
   "line":1}]}]} => status warn, one finding at lib.js:1, rule knip.
   Malformed/exit mismatch errors.
   Implement strict versioned adapters.
2. test_missing_knip_partial: successful Vulture plus missing Knip retains
   both children, otherwise-clean aggregate skipped/partial.
3. test_dynamic_entrypoint_never_auto_delete: decorator-registered callback
   has dynamic_entrypoint=true/confidence=uncertain; no deletion action.
   Definition edit invalidates prior exception. Implement qualified evidence.
4. test_runtime_hit_rejects_static_dead_candidate: actual
   tests/test_route.py::test_route calls callback once => exact hit list and
   reject. Uncalled definition => []/unknown. User tree hashes unchanged.
   Test grant denial, absent backend, malformed receipt, timeout and cleanup.
5. test_dead_options_cli_mcp_parity proves actual selector/grant transmission
   and same shared result, not registry-field presence.

## Runnable proposed RED bodies and transport acceptance

All following code is proposed for the named tests/test_dead.py,
unimplemented and unexecuted. Copy both blocks into that existing test module;
all helpers/imports are defined here. pytest is already installed by dev extra.
Captured adapter reports below test parser/controller boundaries; they do not
prove live engines or OCI isolation. Live tests require captured engine versions,
Git and W18's real local digest-pinned images. RUSH_TEST_OCI_RUNTIME is an
absolute installed runtime path; RUSH_TEST_RUSH_IMAGE pins the current Rush image;
Q06 additionally requires RUSH_TEST_COMPILER_IMAGE with matching TSC/source.
Missing prerequisites block acceptance; do not skip these cases into a PASS.

Static candidate fixture injection below isolates caller-evidence/probe controller;
it does not count as live Vulture/Knip acceptance. Adapter bodies independently
exercise captured protocols. Runtime call IDs come from actual OCI execution,
not the injected scanner. Fresh source SHA invalidates prior digest-bound evidence.

```python
import hashlib, json, os, subprocess
from pathlib import Path
import rush.tools.dead as module
from rush.tools.dead import DeadTool
from rush.engines.vulture import VultureEngine
from rush.engines.knip import KnipEngine

def git_fixture(root):
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Fixture", "-c", "user.email=f@example.test",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

def test_nonzero_empty_is_error(tmp_path, monkeypatch):
    for engine in (VultureEngine(), KnipEngine()):
        monkeypatch.setattr(engine, "version", lambda: "fixture-protocol")
        assert engine.normalize({"exit_code":2, "stdout":"", "stderr":"crashed"},
                                tmp_path, "dead")["status"] == "error"
    vulture = VultureEngine(); monkeypatch.setattr(vulture, "version", lambda: "fixture")
    text = "app.py:1: unused function 'callback' (60% confidence)\n"
    result = vulture.normalize({"exit_code":3,"stdout":text,"stderr":""}, tmp_path,"dead")
    assert result["status"] == "warn"
    assert [(f["path"],f["line"],f["rule"]) for f in result["findings"]] == [
        ("app.py",1,"vulture")]
    knip = KnipEngine(); monkeypatch.setattr(knip, "version", lambda: "6.35.1")
    report = {"issues":[{"file":"lib.js","exports":[{"name":"unused","line":1}]}]}
    result = knip.normalize({"exit_code":0,"stdout":json.dumps(report),"stderr":""},
                            tmp_path,"dead")
    assert result["status"] == "warn"
    assert [(f["path"],f["line"],f["rule"]) for f in result["findings"]] == [
        ("lib.js",1,"knip")]
    assert knip.normalize({"exit_code":0,"stdout":"{","stderr":""},
                          tmp_path,"dead")["status"] == "error"

def test_missing_knip_partial(tmp_path, monkeypatch):
    (tmp_path/"app.py").write_text("answer = 7\n")
    (tmp_path/"lib.js").write_text("export const answer = 7;\n")
    def scan(engine, *args, **kwargs):
        return dict(tool="dead",engine=engine.name,engine_version=None,
            status="skipped" if engine.name=="knip" else "ok",
            duration_ms=0,summary="controlled availability",findings=[])
    monkeypatch.setattr(module,"run_engine",scan)
    result = DeadTool().run(tmp_path)
    assert {c["engine"]:c["status"] for c in result["metadata"]["children"]} == {
        "vulture":"ok","knip":"skipped"}
    assert result["status"] == "skipped"
    assert result["metadata"]["partial"] is True

def test_dynamic_entrypoint_never_auto_delete(tmp_path, monkeypatch):
    source = tmp_path/"app.py"
    source.write_text("def register(f):\n    return f\n@register\ndef callback():\n    return 7\n")
    def scan(engine, *args, **kwargs):
        return dict(tool="dead",engine="vulture",engine_version="fixture",status="warn",
            duration_ms=0,summary="static candidate",findings=[dict(path=str(source),
            line=4,rule="vulture",severity="warn",message="unused function 'callback'")])
    monkeypatch.setattr(module,"run_engine",scan)
    row = DeadTool().run(tmp_path,confirm_reachability=True)["metadata"]["reachability"][0]
    assert row["dynamic_entrypoint"] is True
    assert row["confidence"] == "uncertain"
    assert row["definition_digest"] == hashlib.sha256(source.read_bytes()).hexdigest()
    before = row["definition_digest"]
    source.write_text(source.read_text().replace("return 7","return 8"))
    row = DeadTool().run(tmp_path,confirm_reachability=True)["metadata"]["reachability"][0]
    assert row["definition_digest"] != before

def test_runtime_hit_rejects_static_dead_candidate(tmp_path, monkeypatch):
    source = tmp_path/"app.py"
    source.write_text("def callback():\n    return 7\ndef other():\n    return 2\n")
    tests = tmp_path/"tests"; tests.mkdir()
    route = tests/"test_route.py"
    route.write_text("import app\ndef test_route():\n    assert app.callback() == 7\n")
    def scan(engine,*args,**kwargs):
        return dict(tool="dead",engine="vulture",engine_version="fixture",status="warn",
            duration_ms=0,summary="static candidate",findings=[dict(path=str(source),
            line=1,rule="vulture",severity="warn",message="unused function 'callback'")])
    monkeypatch.setattr(module,"run_engine",scan)
    git_fixture(tmp_path)
    args = dict(confirm_reachability=True,probe_candidate="app.py::callback",
        probe_tests=["tests/test_route.py"],runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
        image_ref=os.environ["RUSH_TEST_RUSH_IMAGE"],allow_build=True,allow_slow=True)
    before = (source.read_bytes(),route.read_bytes())
    hit = DeadTool().run(tmp_path,**args)["metadata"]["reachability_probe"]
    assert hit["deletion_decision"] == "reject"
    assert hit["hit_test_ids"] == ["tests/test_route.py::test_route"]
    assert (source.read_bytes(),route.read_bytes()) == before
    route.write_text("import app\ndef test_route():\n    assert app.other() == 2\n")
    subprocess.run(["git","add","."],cwd=tmp_path,check=True)
    subprocess.run(["git","-c","user.name=Fixture","-c","user.email=f@example.test",
                    "commit","-qm","different actual workload"],cwd=tmp_path,check=True)
    before = (source.read_bytes(),route.read_bytes())
    miss = DeadTool().run(tmp_path,**args)["metadata"]["reachability_probe"]
    assert miss["deletion_decision"] == "unknown"
    assert miss["hit_test_ids"] == []
    assert (source.read_bytes(),route.read_bytes()) == before
```

Actual stdio MCP body uses repository's established ClientSession/stdio_client
pattern (tests/test_mcp.py:234–282), not in-process FastMCP calls or registry-only
checks. Both subprocesses use same checkout src and real command fixture.

```python
def test_dead_options_cli_actual_stdio_mcp_parity(tmp_path):
    import json, os, shutil, subprocess, sys, tempfile
    from pathlib import Path
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    project = Path(__file__).resolve().parents[1]
    env = {**os.environ,"PYTHONPATH":str(project/"src")}
    assert shutil.which("vulture"), "Installed captured Vulture protocol required"
    (tmp_path/"app.py").write_text("def callback():\n    return 7\n")
    proc = subprocess.run([sys.executable,"-m","rush.cli","dead",str(tmp_path),
        *["--confirm-reachability"],"--json"],cwd=project,env=env,capture_output=True,text=True,timeout=180)
    left = json.loads(proc.stdout)
    async def exchange():
        params = StdioServerParameters(command=sys.executable,
            args=["-m","rush.cli","mcp","serve"],cwd=project,env=env)
        with tempfile.TemporaryFile(mode="w+",encoding="utf-8") as errlog:
            with anyio.fail_after(180):
                async with stdio_client(params,errlog=errlog) as (read,write):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        response = await session.call_tool("rush_dead",{"path":str(tmp_path),"confirm_reachability":True})
                        assert response.isError is False
                        assert response.content
                        return json.loads(response.content[0].text)
    right = anyio.run(exchange)
    assert (left["tool"],left["status"]) == (right["tool"],right["status"])
    keys = ("path","line","column","rule","severity","message","rule_id","source_config_digest")
    assert [{k:f.get(k) for k in keys} for f in left["findings"]] == [
        {k:f.get(k) for k in keys} for f in right["findings"]]
    assert left["status"] == "warn"
    assert left["metadata"]["reachability"][0]["symbol"] == "callback"
    keys = ("symbol","definition_digest","static_refs","dynamic_entrypoint","confidence")
    assert [{k:r.get(k) for k in keys} for r in left["metadata"]["reachability"]] == [
        {k:r.get(k) for k in keys} for r in right["metadata"]["reachability"]]
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
Freeze definition and engine protocol fixtures before verification. Missing
graph coverage blocks E1's completeness claims; missing real OCI blocks X1.
Retain originals and actual call/error receipts; clean owned artifacts only.

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_dead.py tests/test_cli_registry.py tests/test_mcp.py tests/test_isolated_process.py -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts

Reconcile R1/R2/E1/X1 with actual versions/call evidence, byte preservation,
frozen hash, executed checks and declared-file diff. No commit/push; no blanket
dead-code certification or completion while prerequisites unresolved.
