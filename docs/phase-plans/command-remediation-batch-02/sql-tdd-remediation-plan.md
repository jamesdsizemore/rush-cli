# Q13 — sql: declared dialect and reversible SQLite evidence

## Authority, baseline and execution boundary

Author: GPT-6 Astra/high; bounded Q11–Q14 command planning lane. Actual work here is document authoring. Production, tests, installation, worktree creation, commits and PR publication are not authorized by this packet.

Implementation source: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch `phase/70-agent-adoption-and-usability`, frozen HEAD `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`; clean tracked/untracked source baseline, no relevant dirty-file hashes. Future dedicated implementation worktree starts this HEAD, not delivery HEAD.

Delivery repository: `/Users/jamesdsizemore/Developer/rush-cli`, branch `codex/codex-cli-mcp-commands-review`, HEAD `c78e445ba1e575ca373e35840142cd627b055d6a`. Its pre-existing modified `AGENTS.md` SHA256 `70252e9068f419b79d88e87b228ce796ae5e61fc0572f06f5354acf209f40617` and unrelated untracked scratch/reports/plans are user-owned. No source changes inferred from delivery checkout. Neither checkout has nested `docs/phase-plans/AGENTS.md`.

Binding inputs, read together: supplied/root `AGENTS.md`; `docs/agents/cli-command-remediation-plan-batch-prompt.md` §§1–6; `docs/templates/task-block-template.md` SHA256 `10fdb5380f04097258e29327cf74fe474532cdc42747a38310d0befa2107ecc3`; source `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` SHA256 `9453032d9411a27b2b7ee2ede074d98d93969fbe85433adacdec1c7bcc89c5c7`; relevant T8/W1/W2/W4 design briefs under source `.scratch/phase-70-design-gate/`. Brief identities: T8 `b15a2c5e9c0fd0cab275c1bd17de78e1975f341048e6df9c403982619f12bfe2`; W1 `5fa3c629ef17c3f7812af1f274df1b23c3c43a00181778950902ae98f81939b3`; W2 `a402ea6ffd4de9c5ca74860d9672cdb834242573ee45b2feb4ca2c2c5da9a0f9`; W4 `47de33a0888a63ee6999a1610577f0e3d0868701642a3a27eb36111d1c1d7204`. Fuller resolutions/test matrices win over shortened packets. Cursor is removed; native host scope is Claude Code and Codex CLI.

Audit input: delivery `docs/reports/cli-mcp-command-audit-2026-09-26.md`, SHA256 `8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f`. Audit proposals are design inputs, not approval or current-source proof. Batch1 failure review supplied lessons only: never mix source baselines, never mistake test counts/schema presence for semantic acceptance, never deliver grounding notes as plans. No Batch1 changes. Owner superseded prior Batch1 approval boundary; that authorizes Batch2 planning, not production execution.

## Phase 70 integration contract

T8 owns target identity. CLI relative targets anchor once at invocation cwd; MCP uses declared registered `project`, otherwise fixed server-start cwd. Preserve lexical containment before resolving, including staged execution substitution, original request and logical root. Internal `context: InvocationContext | None = None` is added to this command's callable and forwarded to run; executor already injects it, `_callable_signature` strips it from MCP. Compute execution root from `context.workspace_root`; direct calls without context use the existing `select_root(str(path), anchor=Path.cwd())` plus `assert_contained(selection)`, then `selection.root`. Do not reconstruct nested-project root from file.parent. Secondary document inputs are **root-relative**, including fixtures, rulesets, patch and SQL config; absolute/parent/symlink/reparse references fail before open. Runtime executable is the sole external absolute-path input and is explicitly approved, never discovered from project PATH. Engine source arguments are contained absolute execution paths; metadata displays logical root-relative POSIX paths. Staged input files are read from staging, never substituted back to live bytes.

T9 missing target: canonical error `TARGET_NOT_FOUND`, CLI exit 2, zero engine calls. Existing target with no supported files: skipped with named reason, exit 0. T10 full read-only analysis creates no `.rush`, DB, journal, registry, cache, cursor key or telemetry. Permission checks for requested code execution precede engine/version probes, temp directories, ruleset code, renderer/import or DB connection.

T11 engines retain `resolve_binary`, verified manifest precedence, project-PATH exclusion and ownership/cancellation through `run_subprocess`. T15 missing engine returns skipped with actual reason; discovery never installs. Scanner provisioning uses existing setup/install route only after explicit download/network/cache-write grants and integrity checks; these commands report readiness, not silently provision.

T16 keep canonical `ToolResult`: `tool, engine, engine_version, status, duration_ms, summary, findings`, optional `raw` and `metadata`. Retain existing `metadata.execution`, `scope`, `engines`, `delivery`. V1 adapter maps metadata to `extensions.metadata`; no new top-level invention. `selected_paths` means selection, `assessed_paths` only successfully executed domain analysis, never a skipped or crashed engine. Distinguish syntax coverage and schema coverage. Existing default scope is honest unavailable where engine does not instrument consumption; do not fabricate matched=consumed. Per-engine child outcome preserves executable identity, version-or-reason, config digest, analysis environment, scope, status and failure reason. Aggregate precedence: error > fail > warn > skipped > ok; executed ok plus required skipped => warn. CLI exits: ok/skipped=0, warn/fail=1, error=2. Full output is complete. Compact uses existing shared delivery, explicit cache-write before execution, 1–50 findings and 4096–65536 bytes; no-cache+compact conflicts before execution. No memory attribution unless an actual memory command read/wrote evidence.

T6 typed schema: top-level object, no top-level combinator; reject unknown fields, wrong enums, string booleans, bool-as-int and null where forbidden before any effects. Typed tool callable and explicit catalog options describe the same inputs. T27 human output shows actual findings, no-work/denied/partial distinction, child execution and recovery, redacted terminal-safe text and copyable full JSON command. Extend existing outcome matrix's command row; do not replace unrelated cases or counts.

Shared-file ownership: **Batch integration owner**, serialized Q11→Q12→Q13→Q14→Q15→Q16→Q17→Q18→Q19→Q20. One writer for `src/rush/catalog.py`, `src/rush/cli_support/catalog_commands.py`, `src/rush/mcp_support/tool_registry.py`, `src/rush/invocation/executor.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_phase60_characterization.py`, `tests/fixtures/phase70/cli-outcomes.json`, `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/configuration-reference.md`, `docs/reference/result-reference.md`, `scripts/sync_docs.py` and generated-doc receipt `docs/reports/phase-64-66-documentation-coverage.md`. Each command's exact consuming delta is specified below. No new command identity/count; update parameter snapshots only. Existing `ContentTool`, global collector ignore rules and unrelated engines stay unchanged.

## Baseline features versus assistant proposals

Scanner provisioning is user baseline: expose actual selected engine missing/ready/integrity state and copyable existing consented setup route; never fake provisioned readiness. Connected specialist models are user baseline but these deterministic checks do not currently invoke one: model may propose a candidate using findings; command consumes explicit immutable inputs, makes no hidden model request, and emits evidence the existing agent can consume. Voice/live speech and 3D companion are user baseline interfaces, not new command engines: command contributes canonical status/findings and child receipts through existing interfaces; this packet adds no speech/model/companion widget or fictitious implementation. Their full product implementation remains separate baseline ownership, not discarded or relabeled as innovation.

Ordinary extensions and distinct agent-side expansions below remain separately labeled assistant proposals. Full designs/tests are provided; landing these optional capabilities needs feature authorization distinct from fixing current defects. This is not an unresolved first-repair prerequisite or permission to silently erase expansion assessment.

## P0 — shared offline isolation prerequisite

Implement owned OCI subprocess execution in rush-cli in future implementation worktree. Read source AGENTS.md, Phase 70 T8/T10/T16 and this contract first.

# Feature: own and confine offline child execution

## Required behavior

New src/rush/runtime/isolated_process.py defines IsolationUnavailable(RuntimeError), IsolationCleanupError(RuntimeError) and:
~~~text
def run_isolated_argv(root: Path, scratch: Path, *, runtime_path: Path,
                      image_ref: str, entrypoint: str, argv: list[str],
                      timeout_s: float, workdir_rel: str = ".",
                      environment: dict[str, str] | None = None,
                      resource_profile: Literal["standard", "analysis"] = "standard"
                      ) -> subprocess.CompletedProcess[str]:
~~~
This is a fully specified proposed interface; absence initially proves missing interface only. Complete implementation algorithm:

1. Caller invokes existing check_permissions(required, granted) BEFORE scratch creation, runtime lookup or version probes. Caller creates fresh tempfile.TemporaryDirectory, chmod 0700, owns final deletion. Provider grants nothing. POSIX only; Windows unavailable. Runtime is explicitly approved absolute executable file; image matches name@sha256:64-lowercase-hex. Validate finite 0<timeout_s<=600; argv NUL-free string list; fixed absolute entrypoint selected by command, never model text. Reject source/scratch symlink/reparse components before resolve; source and scratch must not overlap in either direction; scratch owner is current UID, no group/other mode bits. Reject NUL/comma/CR/LF in mount paths. PhysicalRoot(root).open_contained(workdir_rel) must be directory. Only SOURCE_DATE_EPOCH/TZ/LC_ALL string environment overrides, no control characters.
2. Existing run_subprocess([runtime,"image","inspect",image_ref],timeout=10,env={"PATH":"/usr/bin:/bin"}) must yield exactly one matching locally present RepoDigest and approved native OS/architecture. Missing runtime/image/daemon => IsolationUnavailable before execution, no pulls/installs. Runtime capability tested with actual denial fixture below.
3. Generate uuid4 hex identity and name rush-<identity>. Exact argv: [runtime,"create","--name",name,"--label","io.rush.invocation="+identity,"--pull=never","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges","--pids-limit=64","--memory=512m","--cpus=1","--user",f"{os.getuid()}:{os.getgid()}","--mount",f"type=bind,src={root},dst=/work,readonly","--mount",f"type=bind,src={scratch},dst=/out","--tmpfs","/tmp:rw,nosuid,nodev,size=64m","--workdir",contained_workdir,"--env","PATH=/usr/local/bin:/usr/bin:/bin","--env","HOME=/out","--env","PYTHONDONTWRITEBYTECODE=1","--env","RUSH_CHECK_RECEIPT=/out/checks.json",*sorted_allowed_env_pairs,"--entrypoint",entrypoint,image_ref,*argv]. No HOME/socket/credential mounts. Create stdout must be 64-hex container ID.
4. Start [runtime,"start","--attach",name] with remaining timeout, then inspect container. Matching ID/label, State.Running false, StartedAt nonzero and integer State.ExitCode required. Return CompletedProcess(create_argv,actual_exit,attached.stdout,attached.stderr). The create/start/inspect split distinguishes real target exit125/126/127 from launcher failures, correcting audit run/125 ambiguity.
5. Finally inspect label/ID, rm --force only owned name, inspect known absence on success/error/timeout/cancellation, including create timeout that may already have created container. Cleanup calls use cancel_check=lambda:False so ambient cancellation cannot prevent reaping; timeout10. Existing run_subprocess inherits ambient owner_instance_id/run_id and cancellation, preserving current durable client ownership. Label mismatch, unreachable daemon or remaining container => IsolationCleanupError, never success. Re-raise original timeout/SubprocessCancelled only after confirmed cleanup. Record owned container name in sanitized error metadata for explicit recovery. No host-power-loss cleanup guarantee.

Mapping: unavailable => skipped plus metadata.reason=isolation_unavailable; cleanup failure => error plus terminal_reason=isolation_cleanup_failed. Provider preserves actual target exit; consumer applies exact domain exit/report consistency (valid finding exit1 is not universally error); unexpected exits error. Timeout/cancel retain exact existing reasons. Combined scanner+unavailable trial retains scanner evidence but incomplete/warn unless fail/error already wins. PatchSandboxManager is Git staging, not isolation; NetworkEgressGuard is interpreter-local monkeypatch, not confinement.

## Deliverables

Batch integration owner owns new src/rush/runtime/isolated_process.py and new tests/test_isolated_process.py. Existing PhysicalRoot, run_subprocess, check_permissions and owned scopes reused without modification. P0 ordered before Q11–Q16/Q18–Q20 isolated consumers (Q17's generated-data scanner challenge needs no P0); cross-reference does not replace this embedded contract.

Proposed tests in tests/test_isolated_process.py: test_missing_image_never_creates_container patches only provider run_subprocess with CompletedProcess(argv,1,"","No such image"); asserts sole call image inspect and IsolationUnavailable. test_closed_mounts_and_environment verifies exact create argv above. test_target_exit_125 supplies valid create/start/inspect lifecycle and asserts returned125. test_timeout_and_cancel_reap verifies cleanup despite ambient cancellation and unrelated container untouched.

Runnable genuine-runtime acceptance; only selected when explicit preinstalled approved runtime/image supplied. Missing environment is failure prerequisite, never successful isolation:
~~~python
def test_real_oci_denials(tmp_path):
    import json, os, subprocess, tempfile
    from pathlib import Path
    from rush.runtime.isolated_process import run_isolated_argv
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image = os.environ["RUSH_TEST_OCI_IMAGE"]
    root = tmp_path / "source"
    root.mkdir()
    (root / "keep").write_bytes(b"unchanged")
    home_secret = tmp_path / "host-only-secret"
    home_secret.write_bytes(b"host-canary")
    probe = (
        "import json,socket,pathlib; out={}\n"
        "try: pathlib.Path('/work/blocked').write_text('x'); out['source_write']=True\n"
        "except OSError: out['source_write']=False\n"
        "try: s=socket.create_connection(('1.1.1.1',80),timeout=1); s.close(); out['network']=True\n"
        "except OSError: out['network']=False\n"
        "try: pathlib.Path(" + repr(str(home_secret)) + ").read_bytes(); out['host_read']=True\n"
        "except OSError: out['host_read']=False\n"
        "pathlib.Path('/out/allowed').write_text('ok')\n"
        "print(json.dumps(out))\n"
    )
    with tempfile.TemporaryDirectory(prefix="rush-denial-") as folder:
        scratch = Path(folder)
        scratch.chmod(0o700)
        result = run_isolated_argv(root, scratch, runtime_path=runtime,
            image_ref=image, entrypoint="/usr/local/bin/python",
            argv=["-c", probe], timeout_s=15)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "source_write": False, "network": False, "host_read": False}
        assert (scratch / "allowed").read_text() == "ok"
        name = result.args[result.args.index("--name") + 1]
        check = subprocess.run([str(runtime), "container", "inspect", name],
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=10)
        assert check.returncode != 0
    assert [p.name for p in root.iterdir()] == ["keep"]
    assert (root / "keep").read_bytes() == b"unchanged"
    assert home_secret.read_bytes() == b"host-canary"
~~~
Add actual infinite-sleep timeout and cancellation variants with same post-cleanup inspect. Image must contain fixed /usr/local/bin/python; approved command images additionally contain their named executables. Mocked launcher cannot satisfy this test.

## Constraints

No network/pull/install, unowned deletion, real credentials, source writes or simulated isolation receipts. Keep hard memory/CPU/PID/tmp limits and current UID/GID. Inspect local image/runtime capability; version banners alone prove no confinement.

## Checks to run before reporting

rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_isolated_process.py -q

## Completion

Exact runtime denials, allowed /out write and cleanup pass with actual local runtime; only two P0 files changed. Missing approved image/runtime blocks runtime acceptance, not beginning scanner repairs.

### P0 fixed resource profiles

The function signature additionally accepts resource_profile: Literal["standard","analysis"]="standard"; import Literal from typing. Validate exact enum before any runtime call (other strings, None/bools invalid). Standard maps to --memory=512m --cpus=1 --pids-limit=64. Analysis maps to --memory=8g --cpus=2 --pids-limit=256. No arbitrary user limits. Replace the three literal standard flags in create argv with values from this fixed mapping; every other flag/environment/mount/cleanup invariant unchanged.

Q15/Q16/Q18 and Q11–Q14 use standard. Q20 CodeQL uses analysis with --ram=6144 --threads=2; Q19 local-model process uses analysis with GGUF≤4GiB/context4096/output2048. CodeQL primary evidence: https://docs.github.com/en/code-security/reference/code-scanning/codeql/hardware-resources-for-codeql — small repositories recommend8GB/2cores; 512MiB cannot satisfy promised real analysis. Host insufficient resources => unavailable before target, never reduce guarantees.

Proposed complete flag test in tests/test_isolated_process.py:
~~~python
def test_resource_profiles_reach_real_argv(tmp_path):
    import json, os, subprocess
    from pathlib import Path
    from unittest.mock import patch
    from rush.runtime import isolated_process as provider
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    for profile,memory,cpu,pids in (("standard","512m","1","64"),
                                    ("analysis","8g","2","256")):
        scratch=tmp_path/profile; scratch.mkdir(mode=0o700)
        real=provider.run_subprocess
        calls=[]
        def observe(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with patch.object(provider,"run_subprocess",side_effect=observe):
            result=provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",
                argv=["-c","print('ready')"],timeout_s=15,resource_profile=profile)
        assert result.returncode==0
        created=[a for a in calls if len(a)>1 and a[1]=="create"]
        assert len(created)==1
        assert "--memory="+memory in created[0]
        assert "--cpus="+cpu in created[0]
        assert "--pids-limit="+pids in created[0]
        assert "--network=none" in created[0] and "--read-only" in created[0]
    with patch.object(provider,"run_subprocess") as execute:
        try:
            provider.run_isolated_argv(root,tmp_path/"standard",runtime_path=runtime,
                image_ref=image,entrypoint="/usr/local/bin/python",argv=["-c","pass"],
                timeout_s=1,resource_profile="unlimited")
        except ValueError:
            pass
        else:
            raise AssertionError("unknown resource profile accepted")
        execute.assert_not_called()
~~~

### P0 executable lifecycle acceptance bodies

Append these complete bodies to proposed tests/test_isolated_process.py. Interface absence is expected initial failure; no current isolation claim.

~~~python
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

def test_missing_image_never_creates_container(tmp_path):
    from rush.runtime.isolated_process import run_isolated_argv, IsolationUnavailable
    root=tmp_path/"root"; root.mkdir()
    scratch=tmp_path/"scratch"; scratch.mkdir(mode=0o700)
    runtime=tmp_path/"docker"; runtime.write_text("#!/bin/sh\nexit 0\n"); runtime.chmod(0o700)
    image="fixture@sha256:"+"0"*64
    calls=[]
    def missing(argv,**kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv,1,"","No such image")
    with patch("rush.runtime.isolated_process.run_subprocess",side_effect=missing):
        try:
            run_isolated_argv(root,scratch,runtime_path=runtime,image_ref=image,
                entrypoint="/usr/local/bin/python",argv=["-c","pass"],timeout_s=1)
        except IsolationUnavailable:
            pass
        else:
            raise AssertionError("missing image launched")
    assert calls==[[str(runtime),"image","inspect",image]]
    assert list(scratch.iterdir())==[]

def test_real_timeout_and_cancel_reap(tmp_path):
    from rush.runtime import isolated_process as provider
    from rush.runtime.subprocesses import cancel_scope, SubprocessCancelled
    runtime=Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image=os.environ["RUSH_TEST_OCI_IMAGE"]
    root=tmp_path/"root"; root.mkdir()
    (root/"keep").write_bytes(b"unchanged")
    for mode in ("timeout","cancel"):
        calls=[]
        real=provider.run_subprocess
        def observed(argv,**kwargs):
            calls.append(list(argv))
            return real(argv,**kwargs)
        with tempfile.TemporaryDirectory(prefix="rush-reap-") as folder:
            scratch=Path(folder); scratch.chmod(0o700)
            code="import pathlib,time; pathlib.Path('/out/started').write_text('yes'); time.sleep(60)"
            with patch.object(provider,"run_subprocess",side_effect=observed):
                try:
                    with cancel_scope((lambda:(scratch/"started").exists()) if mode=="cancel" else None):
                        provider.run_isolated_argv(root,scratch,runtime_path=runtime,
                            image_ref=image,entrypoint="/usr/local/bin/python",
                            argv=["-c",code],timeout_s=10)
                except subprocess.TimeoutExpired:
                    assert mode=="timeout"
                except SubprocessCancelled:
                    assert mode=="cancel"
                else:
                    raise AssertionError("sleeping child completed")
            assert (scratch/"started").read_text()=="yes"
            created=[a for a in calls if len(a)>1 and a[1]=="create"]
            assert len(created)==1
            name=created[0][created[0].index("--name")+1]
            assert [str(runtime),"rm","--force",name] in calls
            remaining=subprocess.run([str(runtime),"container","inspect",name],
                env={"PATH":"/usr/bin:/bin"},capture_output=True,text=True,timeout=10)
            assert remaining.returncode!=0
    assert (root/"keep").read_bytes()==b"unchanged"
    assert [p.name for p in root.iterdir()]==["keep"]
~~~


## P0A — Raw MCP catalog validation before SDK coercion

**Required behavior.** Shared prerequisite, Batch integration owner, implemented once with Q11 before new options. Applies only registered rush_actions, rush_yaml, rush_sql, rush_templates, rush_containerfile, rush_iac, rush_secrets, rush_sbom, rush_coverage, rush_codeql. Preserve unregistered/unknown SDK errors, existing request-model tools, and restricted memory server. Parent's current Python3.12 SDK probe proved unknown fields discarded and string "true" coerced to True before make_tool_wrapper. Wrapper-only validation is insufficient. This fixes current contract; additional options are still future interfaces.

**Deliverables.** `src/rush/mcp_support/tool_registry.py` adds two finite helpers/constants below; `src/rush/mcp.py::RushFastMCP.call_tool/list_tools` consumes them before super call; `tests/test_mcp.py::test_catalog_raw_invalid_before_sdk`, `::test_catalog_raw_type_matrix`. No dependency or validation framework.

~~~python
# src/rush/mcp_support/tool_registry.py
import math

RAW_CATALOG_TOOLS = frozenset({
    "rush_actions", "rush_yaml", "rush_sql", "rush_templates",
    "rush_containerfile", "rush_iac", "rush_secrets", "rush_sbom",
    "rush_coverage", "rush_codeql",
})

def catalog_raw_invalid_fields(arguments, schema):
    if not isinstance(arguments, dict) or any(type(k) is not str for k in arguments):
        return ["$"]
    properties = schema.get("properties", {})
    definitions = schema.get("$defs", {})

    def matches(value, shape, depth=0):
        if depth > 16:
            return False
        reference = shape.get("$ref")
        if reference is not None:
            prefix = "#/$defs/"
            return (isinstance(reference, str) and reference.startswith(prefix)
                    and reference[len(prefix):] in definitions
                    and matches(value, definitions[reference[len(prefix):]], depth + 1))
        alternatives = shape.get("anyOf")
        if alternatives is not None:
            return any(matches(value, branch, depth + 1) for branch in alternatives)
        kind = shape.get("type")
        if kind == "null":
            return value is None
        if kind == "boolean":
            return type(value) is bool
        if kind == "integer":
            return type(value) is int
        if kind == "number":
            return type(value) is int or (type(value) is float and math.isfinite(value))
        if kind == "string":
            return type(value) is str
        if kind == "array":
            return type(value) is list and all(
                matches(item, shape.get("items", {}), depth + 1) for item in value)
        if kind == "object":
            return type(value) is dict and all(type(key) is str for key in value)
        if "enum" in shape:
            return any(type(value) is type(item) for item in shape["enum"])
        if not shape:
            return (value is None or type(value) in (str, bool, int)
                    or (type(value) is float and math.isfinite(value))
                    or (type(value) is list and all(matches(v, {}, depth + 1) for v in value))
                    or (type(value) is dict and all(
                        type(k) is str and matches(v, {}, depth + 1)
                        for k, v in value.items())))
        return False

    invalid = set(arguments) - set(properties)
    invalid.update(set(schema.get("required", [])) - set(arguments))
    invalid.update(key for key, value in arguments.items()
                   if key in properties and not matches(value, properties[key]))
    return sorted(invalid)
~~~

This guard validates raw JSON types, nullable branches, required/unknown fields and array element types. Semantic choice values, bounds, path containment and grants stay existing command/shared validators. It rejects JSON-stringified arrays for these ten catalog tools; legacy JSON-string container compatibility on request-model project/scan/memory is unchanged. No expansion to other tools.

Exact insertion at the start of existing `RushFastMCP.call_tool`, before its current REQUEST_MODEL_TOOLS condition:

~~~text
from .mcp_support.tool_registry import RAW_CATALOG_TOOLS, catalog_raw_invalid_fields
from .tools.common import error_result

registered = self._tool_manager.get_tool(name)
if name in RAW_CATALOG_TOOLS and registered is not None:
    invalid = catalog_raw_invalid_fields(arguments, registered.parameters)
    if invalid:
        envelope = error_result(
            name.removeprefix("rush_"), None, "Invalid request",
            terminal_reason="INVALID_REQUEST",
            metadata={"reason": "invalid_request", "invalid_fields": invalid})
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, indent=2))],
            structuredContent=envelope, isError=False)
~~~

The insertion is a method-body fragment: indentation belongs inside async method. Imports json/CallToolResult/TextContent already exist in defining module. Existing method body follows untouched. In `list_tools` existing loop, add independent `if tool.name in RAW_CATALOG_TOOLS: tool.inputSchema={**tool.inputSchema,"additionalProperties":False}`, importing same constant. Do not change registered.parameters or low-level SDK manager internals.

Complete current regression body, appended to existing tests/test_mcp.py:

~~~python
def test_catalog_raw_invalid_before_sdk(tmp_path):
    import asyncio, json
    from rush.mcp import build_server
    from mcp.types import CallToolResult
    server = build_server(profile="full")
    raw = asyncio.run(server.call_tool("rush_actions", {
        "path": str(tmp_path / "missing"),
        "unexpected": 1, "allow_cache_write": "true"}))
    if isinstance(raw, CallToolResult):
        value = raw.structuredContent
        if value is None:
            value = json.loads(next(c.text for c in raw.content if c.type == "text"))
    elif isinstance(raw, tuple):
        value = raw[1]
    else:
        value = json.loads(next(c.text for c in raw if c.type == "text"))
    assert value["status"] == "error"
    assert value.get("metadata", {}).get("invalid_fields") == [
        "allow_cache_write", "unexpected"]
    assert value["metadata"]["reason"] == "invalid_request"
    assert list(tmp_path.iterdir()) == []


def test_catalog_raw_type_matrix():
    from rush.mcp_support.tool_registry import catalog_raw_invalid_fields
    schema = {"type": "object", "required": ["path"], "properties": {
        "path": {"type": "string"},
        "allow_build": {"type": "boolean", "default": False},
        "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None},
        "names": {"type": "array", "items": {"type": "string"}, "default": []}}}
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": False, "limit": None, "names": ["a"]}, schema) == []
    assert catalog_raw_invalid_fields(
        {"path": ".", "allow_build": "false", "limit": True, "names": ["a", 2]}, schema
    ) == ["allow_build", "limit", "names"]
    assert catalog_raw_invalid_fields({"path": ".", "limit": 1.0}, schema) == ["limit"]
    assert catalog_raw_invalid_fields({"path": ".", "names": '["a"]'}, schema) == ["names"]
    assert catalog_raw_invalid_fields({"path": None}, schema) == ["path"]
    assert catalog_raw_invalid_fields({}, schema) == ["path"]
    assert catalog_raw_invalid_fields([], schema) == ["$"]
~~~

First test runs current real server path with missing target, so no engine needed; current RED reaches invalid_fields assertion, not new helper import. Second checks future helper only after implementation. To prove early rejection itself, after implementation wrap `_standard_context` with a raising spy while calling each invalid case; zero calls plus unchanged root/tree. Full stdio consumer test below exercises raw wire arguments, not only SDK metadata.

**Constraints.** Guard has no root/config/permissions/runtime/engine reads; registration lookup/schema inspection only. Unknown/unregistered tools remain SDK errors. Do not reject valid nulls or coerce strings to bool/int/list.

**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_mcp.py::test_catalog_raw_invalid_before_sdk tests/test_mcp.py::test_catalog_raw_type_matrix -q`; each command transport invalid-input case and existing request-model/restricted-server regression.

**Completion.** Actual raw MCP invalid fields produce canonical error with sorted names before effects; every advertised new/default field follows current published type; ordinary valid calls and unaffected profiles remain compatible.


## Goal and requirement ledger

SQL analysis must disclose and honor dialect/templater, never silently treating vendor syntax as ANSI. Scope: `rush sql`/`rush_sql`, SQLfluff selection/config, read-only migration identity and proposed disposable SQLite rehearsal. Non-goals: production DB access, query-plan analysis, external dialect execution through SQLite, applying migrations or uploading query text.

| ID/category | Evidence/current behavior | Change | Task/test acceptance |
|---|---|---|---|
| S1 defect/limit | Q13 audit4929–4990; adapter hardcoded ANSI/raw | explicit dialect, allowlisted templater, contained config, raw template guard | P1 no-declaration RED; actual postgres argv |
| S2 ordinary proposal | audit4992–5017 | contained SQL migration context path+SHA256, no connection | P2 zero DB connect while reading identity |
| S3 agent-side proposal | audit5019–5125 | fixture→migration→rollback in disposable SQLite, typed schema/row snapshot | P2 reversible vs data_loss_or_drift |
| S4 integration/baseline | T8–T16/T6/T27 | root/grants/typed schema/coverage/readiness; baseline consumer receipts | P3/P4 |

## Current source and observed reproduction

`src/rush/tools/sql.py:6–13` SHA256 `59ea7de810b4462ab2eac9732ab1ce3ce152735c946074bd3c08b2cc13e866a5`; `src/rush/engines/sqlfluff.py:16–84` SHA256 `893a252efba1336d2882d61ae53def61ce975b7040d09f4952c2abc37a114702`; SQLfluff argv hardcodes ANSI/raw and ignores ambient config intentionally. Current normalize already rejects malformed JSON and exit mismatch; preserve it.

Observed Python3.12.12: `SqlTool().run(query.sql)` with SELECT1::integer reaches shared engine and returns fixture ok with no dialect declaration. This is current missing-choice defect; a test passing new dialect keyword now would only raise TypeError and is not first RED. Proposed dialect/config/rehearsal interface does not exist yet.

## Input/output contract and concrete options

`path:Path` required; `dialect:Literal["ansi","postgres","sqlite"]|None=None`; `templater:Literal["raw","jinja"]="raw"`; `config_path:str|None=None`; `migration_context:str|None=None`; `rehearse_migration:StrictBool=False`; `db_fixture:str|None=None`; `rollback:str|None=None`; strict allow_build/allow_slow false. Jinja/config code additionally uses `runtime_path:str|None=None,image_ref:str|None=None` for P0. CLI names exactly `--dialect --templater --config-path --migration-context --rehearse-migration --db-fixture --rollback --runtime-path --image-ref`; grant options existing. Root-relative documents, approved absolute runtime. No arbitrary engine args.

Missing dialect: error terminal_reason DIALECT_REQUIRED, no scanner; known set only. Raw selected text containing "{{" or "{%" returns error TEMPLATER_REQUIRED before scanner. Empty file still assessed under declared dialect; empty directory skipped no_sql_targets; missing input T9 error. Config selected local regular file, ≤1MiB, digest actual bytes. Ambient SQLfluff config ignored. Raw built-in Rush config can use trusted host engine without grant. Custom config/Jinja can load macros/libraries: require build, P0 pinned image with SQLfluff and intended dependencies, fixed entrypoint /usr/local/bin/sqlfluff; never execute project configuration on host. Image missing/unapproved yields skipped; no implicit installation. This closes audit's host-Jinja trust gap without dropping requested Jinja/config capability.

Metadata `dialect,templater,config_digest,selected_paths,assessed_paths`; config_digest SHA25664hex. Normalized findings retain templated source coordinates. Missing/scanner-error assessed_paths empty. Migration_context reads one contained .sql file and records digest/path only; it is saved identity, not a verified live db-drift result. No database connection. Rehearsal needs SQLite dialect, exactly one migration SQL file, fixture+rollback, build+slow; missing grant skipped reason missing_grants, zero engine/version/connect/temp. Other dialects error REHEARSAL_DIALECT_UNSUPPORTED; never translate silently.

## P1 — Declare dialect and retain correct engine semantics

**Required behavior.** S1, before optional execution.
**Deliverables.** `src/rush/tools/sql.py::SqlTool.__call__/run`; `src/rush/engines/sqlfluff.py::SqlfluffEngine.__init__/run`; new `tests/test_sql.py`.

~~~python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from rush.tools.sql import SqlTool


def test_undeclared_dialect_never_claims_ansi_clean(tmp_path):
    source = tmp_path / "query.sql"; source.write_text("SELECT 1::integer;\n")
    calls = []
    def engine(*a, **kw):
        calls.append(a)
        return {"tool": "sql", "engine": "sqlfluff", "engine_version": "fixture",
                "status": "ok", "duration_ms": 0, "summary": "clean",
                "findings": [], "raw": None}
    with patch("rush.tools.content.run_engine", side_effect=engine), \
         patch("rush.tools.sql.run_engine", side_effect=engine, create=True):
        result = SqlTool().run(source)
    assert result["status"] == "error"  # current RED: ok
    assert calls == []
    assert result["metadata"]["terminal_reason"] == "DIALECT_REQUIRED"


def test_postgres_dialect_argv(tmp_path):
    from rush.engines.sqlfluff import SqlfluffEngine
    source = tmp_path / "query.sql"; source.write_text("SELECT 1::integer;\n")
    with patch("rush.engines.sqlfluff.resolve_binary",
               return_value="/fixture/sqlfluff"), \
         patch("rush.engines.sqlfluff.run_subprocess",
               return_value=SimpleNamespace(returncode=0, stdout="[]", stderr="")) as run:
        SqlfluffEngine(dialect="postgres").run(tmp_path, [str(source)], cwd=tmp_path)
    argv = run.call_args.args[0]
    assert argv[argv.index("--dialect") + 1] == "postgres"
    assert argv[argv.index("--templater") + 1] == "raw"
    assert "--ignore-local-config" in argv
    assert argv[-1] == str(source)
~~~

First test is current bug RED. Second tests absent future interface after P1 implementation, not a current reproduction.

Minimum GREEN core replacement algorithm (complete values/imports; initial raw branch):

~~~python
# src/rush/engines/sqlfluff.py, inside SqlfluffEngine
def __init__(self, *, dialect="ansi", templater="raw", config_path=DEFAULT_CONFIG):
    if dialect not in {"ansi", "postgres", "sqlite"} or templater not in {"raw", "jinja"}:
        raise ValueError("unsupported dialect/templater")
    self.dialect = dialect
    self.templater = templater
    self.config_path = config_path
# Existing run argv replaces DEFAULT_CONFIG -> self.config_path,
# "ansi" -> self.dialect, "raw" -> self.templater. All other argv,
# ownership, cwd, timeout, normalize remain byte-equivalent.

# src/rush/tools/sql.py, overriding run body after T8 root selection.
import hashlib
from rush.engines.sqlfluff import SqlfluffEngine, DEFAULT_CONFIG
from rush.io.physical_paths import PhysicalRoot
from rush.tools.routing import collect_files
from rush.tools.common import error_result, skipped_result, run_engine

def lint_declared_sql(path, root, *, dialect, templater="raw", config_path=None):
    if dialect is None:
        return error_result("sql", None, "dialect required for SQL assessment",
                            terminal_reason="DIALECT_REQUIRED")
    if dialect not in {"ansi", "postgres", "sqlite"} or templater not in {"raw", "jinja"}:
        return error_result("sql", None, "unsupported dialect/templater",
                            terminal_reason="SQL_OPTIONS_INVALID")
    physical = PhysicalRoot(root)
    files = [physical.open_contained(p.relative_to(root))
             for p in collect_files(path, {"sql"}, strict=True)]
    if not files:
        return skipped_result("sql", "sqlfluff", "no_sql_targets")
    if templater == "raw" and any(
        "{{" in p.read_text(encoding="utf-8") or "{%" in p.read_text(encoding="utf-8")
        for p in files):
        return error_result("sql", "sqlfluff", "template requires declared templater",
                            terminal_reason="TEMPLATER_REQUIRED")
    selected_config = physical.open_contained(config_path) if config_path else DEFAULT_CONFIG
    if not selected_config.is_file():
        return error_result("sql", None, "SQL config must be contained local file")
    engine = SqlfluffEngine(dialect=dialect, templater=templater,
                            config_path=selected_config)
    result = run_engine(engine, root, [str(p) for p in files], tool_name="sql",
                        consumed_paths=[str(p) for p in files], project_root=root)
    names = [p.relative_to(root).as_posix() for p in files]
    result.setdefault("metadata", {}).update(
        dialect=dialect, templater=templater,
        config_digest=hashlib.sha256(selected_config.read_bytes()).hexdigest(),
        selected_paths=names,
        assessed_paths=names if result["status"] in {"ok", "warn", "fail"} else [])
    return result
~~~

This minimum raw path is not called for custom config/Jinja. Full run dispatch selects it only when templater=raw and config_path=None. For other branch: after build permission and input containment, copy fixed Rush config into scratch if none explicitly supplied; use P0 sqlfluff argv `lint --ignore-local-config --config /out/rush.ini|/work/<selected_config> --dialect DIALECT --templater TEMPLATER --format json --processes 1 /work/<sources>...`. Map only returned /work selected paths back to logical source then existing normalize. Reject all other reported paths and malformed/exit-mismatch as current normalizer does. Runtime/isolation metadata retained. Explicit default config remains source-owned, not a hidden project config. Replace read_text source/config reads with existing no-follow `open_contained_file` at boundary before passing bytes to isolation; limits1MiB each.

**Constraints.** Never mutate singleton ENGINES["sqlfluff"] dialect; instantiate configured engine per invocation. Retain default constructor compatibility for existing callers. No production connections.
**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_sql.py -q`.
**Completion.** Missing dialect RED fixed; postgres receives declared value and actual cast fixture parses with installed SQLfluff; raw templates rejected; Jinja/custom config execute only isolated.

### Complete isolated SQLfluff branch

Add this function to src/rush/tools/sql.py. Invoke it instead of lint_declared_sql exactly when config_path is supplied or templater=jinja. Existing raw/default branch stays unchanged. Permissions check occurs before collection, scanner/version/runtime or scratch. Argument values are validated before constructing argv; custom configuration executes solely inside P0.

~~~python
def lint_isolated_sql(path, root, *, dialect, templater, config_path,
                      runtime_path, image_ref, permissions):
    import hashlib, json, os, tempfile
    from pathlib import Path
    from rush.engines.sqlfluff import SqlfluffEngine, DEFAULT_CONFIG
    from rush.permissions import ExecutionPermissions, check_permissions
    from rush.runtime.isolated_process import run_isolated_argv
    from rush.tools.common import error_result, skipped_result
    from rush.tools.routing import collect_files
    from rush.workflows.projects import open_contained_file
    allowed, _ = check_permissions(ExecutionPermissions(build=True), permissions)
    if not allowed:
        return skipped_result("sql", "sqlfluff", "missing_grants",
                              metadata={"reason": "missing_grants"})
    if dialect not in {"ansi", "postgres", "sqlite"} or templater not in {"raw", "jinja"}:
        return error_result("sql", None, "unsupported dialect/templater",
                            terminal_reason="SQL_OPTIONS_INVALID")
    if not runtime_path or not image_ref:
        return skipped_result("sql", "sqlfluff", "isolation_unavailable",
                              metadata={"reason": "isolation_unavailable"})
    def read(base, relative):
        with os.fdopen(open_contained_file(base, str(relative)), "rb") as stream:
            value = stream.read(1_048_577)
        if len(value) > 1_048_576:
            raise ValueError("sql_input_too_large")
        value.decode("utf-8")
        return value
    files = sorted(collect_files(path, {"sql"}, strict=True))
    if not files:
        return skipped_result("sql", "sqlfluff", "no_sql_targets")
    names = [p.relative_to(root).as_posix() for p in files]
    before = {name: read(root, name) for name in names}
    config_bytes = (read(root, config_path) if config_path is not None else
                    read(DEFAULT_CONFIG.parent, DEFAULT_CONFIG.name))
    with tempfile.TemporaryDirectory(prefix="rush-sqlfluff-") as directory:
        scratch = Path(directory); scratch.chmod(0o700)
        if config_path is None:
            (scratch / "rush.ini").write_bytes(config_bytes)
            config_argument = "/out/rush.ini"
        else:
            config_argument = "/work/" + Path(config_path).as_posix()
        process = run_isolated_argv(root, scratch, runtime_path=Path(runtime_path),
            image_ref=image_ref, entrypoint="/usr/local/bin/sqlfluff",
            argv=["lint", "--ignore-local-config", "--config", config_argument,
                  "--dialect", dialect, "--templater", templater, "--format", "json",
                  "--processes", "1", *["/work/" + name for name in names]], timeout_s=120)
    if {name: read(root, name) for name in names} != before:
        raise ValueError("sql_source_changed")
    if config_path is not None and read(root, config_path) != config_bytes:
        raise ValueError("sql_config_changed")
    if len(process.stdout.encode("utf-8")) > 4_194_304:
        raise ValueError("sql_report_too_large")
    report = json.loads(process.stdout)
    if not isinstance(report, list):
        raise ValueError("sql_report_invalid")
    for item in report:
        if not isinstance(item, dict) or not isinstance(item.get("filepath"), str):
            raise ValueError("sql_report_invalid")
        supplied = item["filepath"]
        relative = (Path(supplied).relative_to("/work").as_posix()
                    if supplied.startswith("/work/") else supplied)
        if relative not in before:
            raise ValueError("sql_report_outside_selected_files")
        item["filepath"] = str(root / relative)
    result = SqlfluffEngine().normalize(
        {"exit_code": process.returncode, "stdout": json.dumps(report),
         "stderr": "", "duration_ms": 0}, root, "sql", probe_version=False)
    result.setdefault("metadata", {}).update(
        dialect=dialect, templater=templater,
        config_digest=hashlib.sha256(config_bytes).hexdigest(),
        selected_paths=names,
        assessed_paths=names if result["status"] in {"ok", "warn", "fail"} else [],
        isolation_image=image_ref,
        engine_version_unavailable_reason="isolated_engine_version_unprobed")
    return result
~~~

Full run branch insertion after root resolution and before normal lint/rehearsal dispatch:

~~~python
if config_path is not None or templater == "jinja":
    result = lint_isolated_sql(path, root, dialect=dialect, templater=templater,
        config_path=config_path, runtime_path=runtime_path, image_ref=image_ref,
        permissions=permissions)
else:
    result = lint_declared_sql(path, root, dialect=dialect, templater=templater)
~~~

Wrap bounded parsing/containment exceptions as canonical SQL_INPUT_INVALID with fixed summary; preserve P0 unavailable/cleanup/timeout mappings. Existing probe_version=False normalizer change below prevents host executable access after isolated execution. Migration context/rehearsal append their defined fields to this result only after their whole-operation grants were checked before either branch.

## P2 — Read-only migration identity and bounded rehearsal

**Required behavior.** S2 context identity separately from S3 agent operation. Source/context/fixture/rollback remain byte-identical.
**Deliverables.** Same SqlTool file adds `rehearse_sqlite(fixture_sql,migration_sql,rollback_sql)`; same test module. No database service or new dependency.

Concrete rehearsal engine below replaces audit's loose snapshot/connection lifetime; executed SQL confined to in-memory connection with extension/attachment/pragma denial and bounded operations:

~~~python
def rehearse_sqlite(fixture_sql, migration_sql, rollback_sql):
    import hashlib, json, sqlite3, time
    from contextlib import closing
    def digest(connection):
        schema = connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        rows = {}
        for kind, name, _ in schema:
            if kind != "table":
                continue
            values = connection.execute(
                'SELECT * FROM "' + name.replace('"', '""') + '"').fetchmany(10001)
            if len(values) > 10000:
                raise ValueError("rehearsal_row_limit")
            encoded = []
            for row in values:
                encoded.append([(type(v).__name__, v.hex() if isinstance(v, bytes) else v)
                                for v in row])
            rows[name] = sorted(encoded, key=lambda r: json.dumps(r, sort_keys=True))
        data = json.dumps({"schema": schema, "rows": rows},
                          sort_keys=True, ensure_ascii=True, allow_nan=False)
        return hashlib.sha256(data.encode()).hexdigest()
    deadline = time.monotonic() + 5
    ticks = 0
    def progress():
        nonlocal ticks
        ticks += 1
        return int(ticks > 100000 or time.monotonic() > deadline)
    def authorize(action, first, second, *_):
        if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and str(second).lower() in {
                "load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.enable_load_extension(False)
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1048576)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 1048576)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 128)
        connection.set_progress_handler(progress, 1000)
        connection.set_authorizer(authorize)
        connection.executescript(fixture_sql)
        original = digest(connection)
        connection.executescript(migration_sql)
        forward = digest(connection)
        connection.executescript(rollback_sql)
        after = digest(connection)
    return {"fixture_digest": hashlib.sha256(fixture_sql.encode()).hexdigest(),
            "original_digest": original, "forward_digest": forward,
            "rollback_digest": after, "rollback_restored": after == original,
            "status": "reversible" if after == original else "data_loss_or_drift"}
~~~

Call only after build+slow, SQLite declaration, one selected migration file and contained UTF8 SQL fixture/rollback ≤1MiB. Catch sqlite3.Error/ValueError as canonical error `REHEARSAL_FAILED`; never mislabel interrupted/error as reversible. State result `metadata.migration_rehearsal`; data_loss_or_drift raises overall fail; reversible cannot override lint error/warn. Static lint with missing SQLfluff plus completed rehearsal remains partial warn. Schema snapshots compare exact SQL as SQLite stores it plus typed rows, not a claim of semantic equivalence for every possible DB. Reject >10000 rows rather than silently sample; active memory guard and provider are not conflated. Restore bytes checked in finally.

~~~python
def test_migration_rehearsal_detects_row_loss(tmp_path):
    from rush.permissions import ExecutionPermissions
    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "base.sql").write_text(
        "CREATE TABLE items(id INTEGER PRIMARY KEY,value TEXT);"
        "INSERT INTO items VALUES(1,'a'),(2,'b');")
    (tmp_path / "up.sql").write_text("CREATE INDEX ix_value ON items(value);")
    (tmp_path / "down.sql").write_text("DROP INDEX ix_value;")
    (tmp_path / "loss.sql").write_text(
        "DROP INDEX ix_value;DELETE FROM items WHERE id=2;")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    kwargs = dict(dialect="sqlite", rehearse_migration=True,
                  db_fixture="base.sql",
                  permissions=ExecutionPermissions(build=True, slow=True))
    good = SqlTool().run(tmp_path / "up.sql", rollback="down.sql", **kwargs)
    bad = SqlTool().run(tmp_path / "up.sql", rollback="loss.sql", **kwargs)
    assert good["metadata"]["migration_rehearsal"]["status"] == "reversible"
    assert good["metadata"]["migration_rehearsal"]["rollback_restored"] is True
    assert bad["metadata"]["migration_rehearsal"]["status"] == "data_loss_or_drift"
    assert bad["metadata"]["migration_rehearsal"]["rollback_restored"] is False
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_migration_context_is_read_only(tmp_path):
    import hashlib
    source = tmp_path / "query.sql"; source.write_text("SELECT 1;\n")
    context = tmp_path / "001.sql"; context.write_text("CREATE TABLE t(x INT);\n")
    (tmp_path / "rush.toml").write_text("")
    with patch("sqlite3.connect", side_effect=AssertionError("unexpected DB connection")):
        result = SqlTool().run(source, dialect="ansi", migration_context="001.sql")
    assert result["metadata"]["migration_context_digest"] == hashlib.sha256(
        context.read_bytes()).hexdigest()
    assert result["metadata"]["migration_context_path"] == "001.sql"
~~~

Add denied-grant sentinels for engine/version/sqlite3.connect before input effects; unsupported postgres rehearsal error; ATTACH and VACUUM INTO cannot create external DB; PRAGMA temp_store_directory denied; recursive-query budget error; malformed SQL error; row-limit error; BLOB/integer/string values differentiated; cleanup connection closed after every path. Actual SQLite tests above exercise real stdlib engine, not fake digest arithmetic.

**Constraints.** Rehearsal does execute supplied SQL locally in restricted memory DB; never describe plain static lint that way. No network, filesystem DB URI, extension loading or hidden installation.
**Checks.** P1 module and P0 actual runtime tests for custom config/Jinja branch.
**Completion.** Exact context digest with zero connections; actual rehearsal proves row loss and rollback restoration independently of scanner presence; all denial/error paths preserve input bytes.

### Complete SqlTool.run dispatcher

Use exact method below after helpers above land. Input bytes and grants precede scanner/version/SQLite effects; readback remains in finally for rehearsal.

~~~python
def run(self, path, *, config=None, context=None, dialect=None, templater="raw",
        config_path=None, migration_context=None, rehearse_migration=False,
        db_fixture=None, rollback=None, runtime_path=None, image_ref=None, permissions=None):
    import hashlib, os, sqlite3
    from pathlib import Path
    from rush.invocation.targets import select_root, assert_contained
    from rush.io.physical_paths import ContainmentError
    from rush.permissions import ExecutionPermissions, check_permissions
    from rush.runtime.isolated_process import IsolationUnavailable, IsolationCleanupError
    from rush.tools.common import error_result, skipped_result
    from rush.tools.routing import collect_files
    from rush.workflows.projects import open_contained_file
    def read(relative):
        with os.fdopen(open_contained_file(root, relative), "rb") as stream:
            data = stream.read(1_048_577)
        if len(data) > 1_048_576:
            raise ValueError("sql_input_too_large")
        data.decode("utf-8")
        return data
    try:
        if context is None:
            selection = select_root(str(path), anchor=Path.cwd())
            assert_contained(selection)
            root = selection.root; path = root / selection.relative
        else:
            root = context.workspace_root
        if not path.exists():
            return error_result(self.name, None, "target does not exist",
                                terminal_reason="TARGET_NOT_FOUND")
        if dialect is None:
            return error_result(self.name, None, "dialect required",
                                terminal_reason="DIALECT_REQUIRED")
        required = ExecutionPermissions(
            build=rehearse_migration or config_path is not None or templater == "jinja",
            slow=rehearse_migration)
        allowed, _ = check_permissions(required, permissions)
        if not allowed:
            return skipped_result(self.name, None, "missing_grants",
                                  metadata={"reason": "missing_grants"})
        files = collect_files(path, {"sql"}, strict=True)
        if rehearse_migration:
            if dialect != "sqlite":
                return error_result(self.name, None, "SQLite rehearsal required",
                                    terminal_reason="REHEARSAL_DIALECT_UNSUPPORTED")
            if len(files) != 1 or not db_fixture or not rollback:
                raise ValueError("rehearsal_inputs_invalid")
            names = [files[0].relative_to(root).as_posix(), db_fixture, rollback]
            before = {name: read(name) for name in names}
        context_bytes = read(migration_context) if migration_context is not None else None
        if config_path is not None or templater == "jinja":
            result = lint_isolated_sql(path, root, dialect=dialect, templater=templater,
                config_path=config_path, runtime_path=runtime_path, image_ref=image_ref,
                permissions=permissions)
        else:
            result = lint_declared_sql(path, root, dialect=dialect, templater=templater)
        if context_bytes is not None:
            result.setdefault("metadata", {}).update(
                migration_context_path=migration_context,
                migration_context_digest=hashlib.sha256(context_bytes).hexdigest())
        if rehearse_migration:
            try:
                trial = rehearse_sqlite(before[db_fixture].decode(),
                    before[names[0]].decode(), before[rollback].decode())
            finally:
                if {name: read(name) for name in names} != before:
                    raise ValueError("sql_source_changed")
            result.setdefault("metadata", {})["migration_rehearsal"] = trial
            if trial["status"] == "data_loss_or_drift" and result["status"] != "error":
                result["status"] = "fail"
            elif result["status"] == "skipped":
                result["status"] = "warn"
        return result
    except IsolationUnavailable:
        return skipped_result(self.name, None, "isolation_unavailable",
                              metadata={"reason": "isolation_unavailable"})
    except IsolationCleanupError:
        return error_result(self.name, None, "SQL isolated cleanup failed",
                            terminal_reason="isolation_cleanup_failed")
    except (ValueError, OSError, ContainmentError, sqlite3.Error):
        return error_result(self.name, None, "SQL input or rehearsal invalid",
                            terminal_reason="REHEARSAL_FAILED" if rehearse_migration else "SQL_INPUT_INVALID")
~~~

## P3 — Real CLI and initialized stdio MCP parity

**Required behavior.** Explicit options reach shared tool implementation on both transports. Matching domain projection below is equal; target identities and grants cannot be inferred from tools/list alone. Test-owned engine below proves forwarding/parser behavior only; P2 real-engine/OCI tests separately prove runtime behavior.

**Deliverables.** Add following complete module to `tests/test_sql_transport.py`; Batch integration owner adds command's explicit options to `_TOOL_CLI_OPTIONS` and exact `ToolOptionSpec` tuple to existing `TOOL_SPECS["sql"]`. Preserve existing `make_tool_wrapper`/executor; context is internal. No generic introspection factory, MCP-only implementation or new CLI route.

~~~python
import asyncio
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

COMMAND = "sql"
BINARY = "sqlfluff"
SOURCE = "query.sql"
BODY = "SELECT 1::integer;\n"
OPTIONS = {"dialect":"postgres"}
CLI_OPTIONS = ["--dialect","postgres"]
EXPECTED = {"status":"ok","dialect":"postgres","templater":"raw","assessed_paths":["query.sql"]}
PROJECTION = ["dialect","templater","assessed_paths"]


def projection(result):
    metadata = result.get("metadata", {})
    return {"status": result["status"],
            **{name: metadata.get(name) for name in PROJECTION}}


async def mcp_call(root, env, arguments):
    server = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from rush.cli import cli; cli()", "mcp", "serve",
              "--profile", "full"],
        cwd=str(root), env=env,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            schema = next(t.inputSchema for t in listed.tools
                          if t.name == "rush_" + COMMAND)
            assert schema["type"] == "object"
            assert "context" not in schema.get("properties", {})
            assert "project" in schema["properties"]
            assert set(OPTIONS) <= set(schema["properties"])
            response = await session.call_tool("rush_" + COMMAND, arguments)
            assert response.isError is False, response
            if response.structuredContent is not None:
                return response.structuredContent
            payloads = [json.loads(c.text) for c in response.content
                        if c.type == "text"]
            assert len(payloads) == 1
            return payloads[0]


def test_cli_stdio_exact_domain_and_no_state(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("", encoding="utf-8")
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(BODY, encoding="utf-8")
    binaries = tmp_path / "engines"; binaries.mkdir()
    marker = tmp_path / "argv.jsonl"
    binary = binaries / BINARY
    binary.write_text(
        "#!" + sys.executable + "\n"
        "import json,sys\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv:\n"
        " print('fixture 1.0');raise SystemExit(0)\n"
        "with Path(" + repr(str(marker)) + ").open('a') as f:\n"
        " f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "print('[]')\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    env["NO_COLOR"] = "1"
    before = {p.relative_to(root).as_posix(): p.read_bytes()
              for p in root.rglob("*") if p.is_file()}
    call = subprocess.run(
        [sys.executable, "-c", "from rush.cli import cli; cli()",
         COMMAND, SOURCE, *CLI_OPTIONS, "--json"],
        cwd=root, env=env, text=True, capture_output=True, timeout=30,
        check=False,
    )
    assert call.returncode == 0, (call.stdout, call.stderr)
    cli_result = json.loads(call.stdout)
    mcp_result = asyncio.run(mcp_call(
        root, env, {"path": SOURCE, **OPTIONS}))
    assert projection(cli_result) == EXPECTED
    assert projection(mcp_result) == EXPECTED
    after = {p.relative_to(root).as_posix(): p.read_bytes()
             for p in root.rglob("*") if p.is_file()}
    assert after == before
    assert not (root / ".rush").exists()
    assert not (root / ".rush").is_symlink()
    assert len(marker.read_text().splitlines()) == 2
    assert all(json.loads(line)[json.loads(line).index('--dialect') + 1] == 'postgres' for line in marker.read_text().splitlines())


def test_missing_target_cli_stdio_zero_engine(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    env = os.environ.copy(); env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "from rush.cli import cli; cli()",
         COMMAND, "missing.file", *CLI_OPTIONS, "--json"],
        cwd=root, env=env, text=True, capture_output=True, timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "error"
    remote = asyncio.run(mcp_call(
        root, env, {"path": "missing.file", **OPTIONS}))
    assert remote["status"] == "error"
    assert list(root.iterdir()) == []
~~~

**Constraints.** Mark fake engine lane explicitly as transport/normalizer proof. Do not claim installation, real engine semantics, native host adoption or OCI security from it. Test against installed editable project environment with inherited PYTHONPATH removed. No global suite.

**Checks to run before reporting.**
`rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_sql_transport.py tests/test_sql.py tests/test_cli_registry.py tests/test_mcp.py -q`

**Completion.** Real process CLI and initialized stdio call agree on stated domain values, missing/denied input produces zero analysis/state effects, parameter schema is exact, source bytes unchanged, and separate runtime checks pass.


Append this complete denied-request case to the same transport module. Permission denial is preflight for the whole explicitly requested operation, returning skipped with metadata.reason="missing_grants"; no engine/version/runtime call occurs.

~~~python
def test_cli_stdio_denied_request_zero_effects(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("SELECT 1;\n")
    for relative, text in {"base.sql": "CREATE TABLE t(x INT);", "down.sql": "SELECT 1;"}.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    # All request data is present before the byte snapshot.
    binaries = tmp_path / "engines"; binaries.mkdir()
    marker = tmp_path / "forbidden-spawn"
    program = ("#!" + sys.executable + "\nfrom pathlib import Path\n"
               "Path(" + repr(str(marker)) + ").write_text('spawned')\n")
    for filename in (BINARY, "fixture-runtime"):
        binary = binaries / filename
        binary.write_text(program)
        binary.chmod(0o700)
    env = os.environ.copy(); env.pop("PYTHONPATH", None)
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    runtime = str(binaries / "fixture-runtime")
    image = "fixture/image@sha256:" + "d" * 64
    options = {"dialect": "sqlite", "rehearse_migration": True, "db_fixture": "base.sql", "rollback": "down.sql"}
    options.update(runtime_path=runtime, image_ref=image)
    flags = ["--dialect", "sqlite", "--rehearse-migration", "--db-fixture", "base.sql", "--rollback", "down.sql"] + ["--runtime-path", runtime, "--image-ref", image]
    before = {p.relative_to(root).as_posix(): p.read_bytes()
              for p in root.rglob("*") if p.is_file()}
    result = subprocess.run(
        [sys.executable, "-c", "from rush.cli import cli; cli()",
         COMMAND, SOURCE, *flags, "--json"], cwd=root, env=env,
        capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    local = json.loads(result.stdout)
    remote = asyncio.run(mcp_call(root, env, {"path": SOURCE, **options}))
    assert local["status"] == remote["status"] == "skipped"
    assert local["metadata"]["reason"] == remote["metadata"]["reason"] == "missing_grants"
    assert "migration_rehearsal" not in local.get("metadata", {})
    assert not marker.exists()
    assert {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()} == before
    assert not (root / ".rush").exists()
~~~


### Exact engine scope and version provenance

The existing shared `run_engine` is defined in `src/rush/runtime/subprocesses.py:1258–1335` and accepts `consumed_paths,project_root`. Every host static dispatch in this command passes `consumed_paths=[str(p) for p in files], project_root=root` together with the exact same selected argv. This binds recorded main spawns to actual explicit source inputs; missing/denied/error scopes remain whatever the real run records. Never call a scope probe that is absent on the adapter or infer dependency closure. Caller-owned config identity updates the corresponding engine entry's `config={path,sha256,reason:None}` from the actual fixed/explicit config; dependency instrumentation unavailable remains disclosed separately.


### Isolated normalizer must not probe host executable

Add `probe_version: bool = True` keyword-only parameter to `src/rush/engines/sqlfluff.py::SqlfluffEngine.normalize`. Its only field change is:
~~~text
engine_version=self.version() if probe_version else None,
~~~
This is an exact keyword-expression replacement, not a standalone module. Default preserves all current callers and parser/exit consistency. In isolated path call `normalize(raw,root,"sql",probe_version=False)`; never call host version to label container execution. Result records `engine_version=None`, `metadata.engine_version_unavailable_reason="isolated_engine_version_unprobed"` and actual approved `isolation_image`. A later optional image version probe is unnecessary for this packet; no version is invented.

Populate isolated child `metadata.engines` with engine="sqlfluff", executable.path="/usr/local/bin/sqlfluff", executable.sha256=null, executable.reason="image_scoped_identity", version=null, version_unavailable_reason="isolated_engine_version_unprobed", config.path="/work/<ruleset-or-config>", config.sha256=<actual bytes digest>, config.reason=null, analysis_environment={mode:"oci",image_ref:<approved digest>}, status/summary copied from normalized child, cwd="/work", recorded main invocation, and actual selected-file scope. This is container identity, not host executable identity. The adapter parser still validates every reported selected path; metadata survives parent aggregation.

Add this complete preservation/security test to tests/test_sql.py; normalization can occur without any host engine:
~~~python
def test_isolated_normalize_never_probes_host_version(tmp_path):
    from rush.engines.sqlfluff import SqlfluffEngine
    with patch.object(SqlfluffEngine, "version",
                      side_effect=AssertionError("host version probe forbidden")):
        result = SqlfluffEngine().normalize(
            {"exit_code": 0, "stdout": "[]", "stderr": ""},
            tmp_path, "sql", probe_version=False)
    assert result["status"] == "ok"
    assert result["engine_version"] is None
~~~


Append to the same command transport module; complete actual initialized stdio raw-input check:

~~~python
def test_stdio_rejects_raw_unknown_and_string_grant(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    env = os.environ.copy(); env.pop("PYTHONPATH", None)
    result = asyncio.run(mcp_call(root, env, {
        "path": "missing.file", "unexpected": 1, "allow_cache_write": "true"}))
    assert result["status"] == "error"
    assert result["metadata"]["reason"] == "invalid_request"
    assert result["metadata"]["invalid_fields"] == ["allow_cache_write", "unexpected"]
    assert list(root.iterdir()) == []
~~~

### Granted operation through both real transports

Append complete bodies below to this command's existing proposed transport module. Prerequisites are approved, already installed engines plus pinned P0 image; absent environment values fail, never skip. Both subprocesses run from unrelated directory. Project is registered using real existing register_project under test-owned HOME before snapshot; relative document options must resolve to declared project. Stdout is parsed solely as JSON/JSON-RPC; injected startup diagnostic must remain stderr. No runtime/engine mock satisfies this lane.

~~~python
def granted_environment(tmp_path, root):
    import json, os, subprocess, sys
    from pathlib import Path
    home = tmp_path / "granted-home"; home.mkdir()
    foreign = tmp_path / "foreign"; foreign.mkdir()
    bindir = Path(os.environ["RUSH_TEST_ENGINE_BIN_DIR"])
    assert bindir.is_dir()
    env = {**os.environ, "HOME": str(home),
           "XDG_DATA_HOME": str(home / "data"), "LOCALAPPDATA": str(home / "local"),
           "PATH": str(bindir) + os.pathsep + os.defpath, "NO_COLOR": "1"}
    env.pop("PYTHONPATH", None)
    registration = subprocess.run([sys.executable, "-c",
        "import sys; from rush.workflows.projects import register_project; "
        "print(register_project(sys.argv[1]).project_id)", str(root)],
        cwd=foreign, env=env, capture_output=True, text=True, check=True)
    return env, foreign, registration.stdout.strip()

def exact_schema(domain):
    nullable = lambda kind: {"anyOf": [{"type": kind}, {"type": "null"}], "default": None}
    props = {
        "path": {"type": "string", "format": "path"},
        "project": nullable("string"),
        "allow_cache_write": {"type": "boolean", "default": False},
        "no_cache": {"type": "boolean", "default": False},
        "result_view": {"anyOf": [{"type": "string", "enum": ["full", "compact"]},
                                  {"type": "null"}], "default": None},
        "limit": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 50},
                            {"type": "null"}], "default": None},
        "max_bytes": {"anyOf": [{"type": "integer", "minimum": 4096, "maximum": 65536},
                                {"type": "null"}], "default": None}}
    props.update(domain)
    return {"type": "object", "properties": props, "required": ["path"],
            "additionalProperties": False}

def granted_stdio(foreign, env, command, arguments, expected_schema):
    import json, queue, subprocess, sys, tempfile, threading
    def semantic(value):
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in value.items()
                    if k not in {"title", "description"}}
        if isinstance(value, list):
            return [semantic(v) for v in value]
        return value
    code = ("import sys; print('rush-test-diagnostic', file=sys.stderr); "
            "from rush.cli import cli; cli()")
    with tempfile.TemporaryFile(mode="w+") as errors:
        child = subprocess.Popen([sys.executable, "-c", code, "mcp", "serve",
            "--profile", "full"], cwd=foreign, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=errors, text=True, bufsize=1)
        replies = queue.Queue()
        def read():
            for line in child.stdout:
                replies.put(line)
        thread = threading.Thread(target=read, daemon=True); thread.start()
        def send(value):
            child.stdin.write(json.dumps(value) + "\n"); child.stdin.flush()
        def receive(identity):
            while True:
                value = json.loads(replies.get(timeout=300))
                assert value["jsonrpc"] == "2.0", value
                if value.get("id") == identity:
                    assert "error" not in value, value
                    return value["result"]
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "granted-acceptance", "version": "1"}}})
            assert receive(1)["protocolVersion"]
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tool = next(t for t in receive(2)["tools"] if t["name"] == "rush_" + command)
            assert semantic(tool["inputSchema"]) == expected_schema
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "rush_" + command, "arguments": arguments}})
            result = receive(3)
            assert result.get("isError", False) is False
            value = result.get("structuredContent")
            if value is None:
                value = json.loads(next(c["text"] for c in result["content"] if c["type"] == "text"))
            return value
        finally:
            child.terminate(); child.wait(timeout=10)
            child.stdin.close(); child.stdout.close()
            errors.seek(0)
            assert "rush-test-diagnostic" in errors.read()

def granted_cli(foreign, env, command, target, options, expected_exit):
    import json, subprocess, sys
    code = ("import sys; print('rush-test-diagnostic', file=sys.stderr); "
            "from rush.cli import cli; cli()")
    result = subprocess.run([sys.executable, "-c", code, command, str(target),
        *options, "--no-cache", "--json"], cwd=foreign, env=env,
        capture_output=True, text=True, timeout=300)
    assert result.returncode == expected_exit, result.stderr + result.stdout
    assert "rush-test-diagnostic" in result.stderr
    return json.loads(result.stdout)

def entire_tree(root):
    import hashlib
    return {p.relative_to(root).as_posix(): (
        "directory" if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest())
        for p in root.rglob("*")}
~~~

~~~python
GRANTED_SCHEMA = exact_schema(json.loads(r'''{"dialect":{"anyOf":[{"enum":["ansi","postgres","sqlite"],"type":"string"},{"type":"null"}],"default":null},"templater":{"enum":["raw","jinja"],"type":"string","default":"raw"},"config_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"migration_context":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"rehearse_migration":{"type":"boolean","default":false},"db_fixture":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"rollback":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"runtime_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"image_ref":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"allow_build":{"type":"boolean","default":false},"allow_slow":{"type":"boolean","default":false}}'''))

def test_granted_sql_jinja_cli_stdio_foreign_cwd(tmp_path):
    import hashlib, os
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "query.sql").write_text("SELECT {{ amount }}::integer;\n")
    config = b"[sqlfluff]\ndialect = postgres\ntemplater = jinja\nrules = LT01\n[sqlfluff:templater:jinja:context]\namount = 1\n"
    (root / "rules.ini").write_bytes(config)
    image = os.environ["RUSH_TEST_SQLFLUFF_IMAGE"]
    runtime = os.environ["RUSH_TEST_OCI_RUNTIME"]
    env, foreign, project = granted_environment(tmp_path, root)
    before = entire_tree(root)
    left = granted_cli(foreign, env, "sql", root / "query.sql",
        ["--dialect", "postgres", "--templater", "jinja", "--config-path", "rules.ini",
         "--runtime-path", runtime, "--image-ref", image, "--allow-build"], 0)
    right = granted_stdio(foreign, env, "sql",
        {"project": project, "path": "query.sql", "dialect": "postgres",
         "templater": "jinja", "config_path": "rules.ini", "runtime_path": runtime,
         "image_ref": image, "allow_build": True, "no_cache": True}, GRANTED_SCHEMA)
    fields = ("dialect", "templater", "config_digest", "selected_paths", "assessed_paths",
              "isolation_image", "engine_version_unavailable_reason")
    assert left["status"] == right["status"] == "ok"
    assert left["findings"] == right["findings"] == []
    assert {k:left["metadata"][k] for k in fields} == {k:right["metadata"][k] for k in fields}
    assert right["metadata"]["config_digest"] == hashlib.sha256(config).hexdigest()
    assert right["metadata"]["assessed_paths"] == ["query.sql"]
    assert entire_tree(root) == before

~~~

## Literal transport/configuration edits and future PR scope

Batch integration owner appends only this command's tuple to existing `src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS` (factory already forwards `**tool_options`). Existing permission options are not redeclared:

~~~python
"sql": (
    click.Option(["--dialect"], type=click.Choice(["ansi","postgres","sqlite"]), default=None),
    click.Option(["--templater"], type=click.Choice(["raw","jinja"]), default="raw"),
    click.Option(["--config-path"], type=str, default=None),
    click.Option(["--migration-context"], type=str, default=None),
    click.Option(["--rehearse-migration"], is_flag=True, default=False),
    click.Option(["--db-fixture"], type=str, default=None),
    click.Option(["--rollback"], type=str, default=None),
    click.Option(["--runtime-path"], type=str, default=None),
    click.Option(["--image-ref"], type=str, default=None),
),
~~~

In `src/rush/catalog.py`, replace this command's `option_specs` with the following complete tuple, retaining canonical name/category/maturity/engine mapping. Each local document parameter intentionally uses default path_kind="none" because tool validates it root-relatively through PhysicalRoot; do not add it to cwd-relative `_CWD_RELATIVE_ARGS`. External runtime is never interpreted as project file. This explicit anchor decision prevents nested cwd rebasing.

~~~python
option_specs=(
    ToolOptionSpec("dialect", str, default=None, choices=("ansi", "postgres", "sqlite",), description="dialect; see command contract"),
    ToolOptionSpec("templater", str, default="raw", choices=("raw", "jinja",), description="templater; see command contract"),
    ToolOptionSpec("config_path", str, default=None, description="config path; see command contract"),
    ToolOptionSpec("migration_context", str, default=None, description="migration context; see command contract"),
    ToolOptionSpec("rehearse_migration", bool, default=False, description="rehearse migration; see command contract"),
    ToolOptionSpec("db_fixture", str, default=None, description="db fixture; see command contract"),
    ToolOptionSpec("rollback", str, default=None, description="rollback; see command contract"),
    ToolOptionSpec("runtime_path", str, default=None, description="runtime path; see command contract"),
    ToolOptionSpec("image_ref", str, default=None, description="image ref; see command contract"),
)
~~~

Add exact typed callable to `src/rush/tools/sql.py::SqlTool` (imports supplied; place method inside class). Its `run` accepts same domain options plus `permissions,context,config`, with all defaults identical; list/tuple preserve_fields normalize once to list. Strict booleans preserve invalid-type rejection.

~~~python
from typing import Literal
from pathlib import Path
from pydantic import StrictBool
from rush.invocation.models import InvocationContext
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolResult
from rush.tools.common import error_result

def __call__(
    self, path: Path, *,
    dialect: Literal["ansi", "postgres", "sqlite"] | None = None,
    templater: Literal["raw", "jinja"] = "raw",
    config_path: str | None = None,
    migration_context: str | None = None,
    rehearse_migration: StrictBool = False,
    db_fixture: str | None = None,
    rollback: str | None = None,
    runtime_path: str | None = None,
    image_ref: str | None = None,
    allow_build: StrictBool = False,
    allow_slow: StrictBool = False,
    context: InvocationContext | None = None,
) -> ToolResult:
    if any(type(value) is not bool for value in (allow_build, allow_slow, rehearse_migration,)):
        return error_result("sql", None, "boolean arguments must be booleans",
                            terminal_reason="INVALID_REQUEST")
    return self.run(
        path,
        dialect=dialect,
        templater=templater,
        config_path=config_path,
        migration_context=migration_context,
        rehearse_migration=rehearse_migration,
        db_fixture=db_fixture,
        rollback=rollback,
        runtime_path=runtime_path,
        image_ref=image_ref,
        permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        context=context,
    )
~~~

Tracked configuration guide is `docs/CONFIGURATION.md` (uppercase Git path), and existing conservative example is `examples/rush.toml`; both are shared integration-owner writes. Existing `ToolOptionSpec` tuple is configuration schema. Preserve existing tables; append only this command's single safe-default table described below. Update command section in `docs/reference/configuration-reference.md` with literal `[tools.sql]` keys/defaults and root-relative semantics, corresponding sections in `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/result-reference.md`. Add one clean, one no-work, one denied, one failed example with actual result/exit. Update `tests/test_cli_registry.py` exact help/flags and `tests/test_mcp.py` emitted parameter assertions; `tests/test_phase60_characterization.py` retains tool count and updates this command's fields only. `scripts/sync_docs.py` is check-only. Edit existing reference rows and serialized coverage receipt/hash rows in `docs/reports/phase-64-66-documentation-coverage.md` directly using final exact doc bytes; then run `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check`. Never claim this command generates or repairs documentation. `tests/fixtures/phase70/cli-outcomes.json` receives this command's populated/empty/denied/failure/side-effects domain assertions. Existing shared renderer/delivery consumes metadata; preserve full result, visible partial/no-work and terminal escaping.

Future PR scope: first command repair files/tests and exactly necessary shared catalog/docs delta; optional ordinary and agent-side features remain separately reviewable later commits/PR scopes when authorized. Shared provider prerequisite lands before any consumer feature; no separate command identity or duplicate transport implementation.

### Complete installed-engine acceptance

Append to tests/test_sql.py. Genuine engine resolved through existing resolver; no doubles. These future tests were not executed during planning. Missing executable/image is failed prerequisite, never successful skip. Run with same approved runtime environment as granted transport node.


~~~python
def test_real_postgres_and_isolated_jinja(tmp_path):
    import os
    from pathlib import Path
    from rush.permissions import ExecutionPermissions
    from rush.runtime.binaries import resolve_binary
    from rush.tools.sql import SqlTool
    assert resolve_binary("sqlfluff"), "approved SQLfluff must be preinstalled"
    (tmp_path / "rush.toml").write_text("")
    source = tmp_path / "query.sql"; source.write_text("SELECT 1::integer;\n")
    raw = SqlTool().run(source, dialect="postgres")
    assert raw["status"] == "ok" and raw["findings"] == []
    assert raw["metadata"]["assessed_paths"] == ["query.sql"]
    assert raw["engine_version"]
    source.write_text("SELECT {{ amount }}::integer;\n")
    (tmp_path / "rules.ini").write_text(
        "[sqlfluff]\ndialect = postgres\ntemplater = jinja\nrules = LT01\n"
        "[sqlfluff:templater:jinja:context]\namount = 1\n")
    templated = SqlTool().run(source, dialect="postgres", templater="jinja",
        config_path="rules.ini", runtime_path=os.environ["RUSH_TEST_OCI_RUNTIME"],
        image_ref=os.environ["RUSH_TEST_SQLFLUFF_IMAGE"],
        permissions=ExecutionPermissions(build=True))
    assert templated["status"] == "ok" and templated["findings"] == []
    assert templated["metadata"]["templater"] == "jinja"
    assert templated["metadata"]["assessed_paths"] == ["query.sql"]
    assert templated["engine_version"] is None
    assert templated["metadata"]["engine_version_unavailable_reason"] == "isolated_engine_version_unprobed"
~~~

### Literal conservative configuration example

Append this exact table once to examples/rush.toml and mirror it in docs/CONFIGURATION.md and docs/reference/configuration-reference.md. No runtime path, image, effectful operation, or grant is persisted by the example. Other new operation fields stay explicit invocation examples in command references.

~~~toml
[tools.sql]
dialect = "postgres"
templater = "raw"
~~~

## P4 — Regression, failure recovery and completion gate

**Required behavior.** Close every ledger row and preserve Phase70 contracts. Test source/installed engine/runtime boundaries separately. Freeze changed bytes before verification; read-only reviewer checks exact hash. Any edit invalidates previous verdict.

**Deliverables.** Only literal files named in P1–P3/shared delta; command tests create fixtures in tmp_path, no permanent unrelated fixture corpus. Runtime prerequisites are already-installed approved executables/images; missing prerequisite blocks that acceptance lane and must be named, never silently skipped as passing.

**Constraints.** No install/network/build during planning. Future tests clear inherited PYTHONPATH, use project Python3.12. No duplicate runs beyond two unchanged-byte attempts, global broad suite, new harness, source rewrite, production DB/service, Git hooks, commit/push/release without explicit authorization. Cleanup failure exposes owned residue and exact restore/delete ownership; never claim clean.

**Checks to run before reporting.** From future implementation worktree based on frozen source:
~~~sh
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_sql.py tests/test_sql_transport.py tests/test_content_infra_tools.py tests/test_staged_scan_bytes.py tests/test_phase57_invocation_context.py tests/test_phase54_result_schema.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_module_boundaries.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
~~~
Expected Python3.12.x; exact changed-behavior assertions pass; Ruff exit0. Existing correct malformed-report/permission/root cases are preservation GREEN, not manufactured RED. Refactor only after behavior passes, then run affected checks once on new frozen bytes.

**Completion.** First repair packet is development-ready only after frozen plan review resolves all code/test/interface inconsistencies. Entire optional capability completion additionally requires real engine/OCI or SQLite proof, exact CLI+stdio parity, strict-schema adversarial input rejection, denied zero effects, source-byte/readback verification, approved scope and completed ledger. This authored plan is not an implementation PASS, installation verification, batch ratification or future runtime execution claim. Planning observed reproductions are listed separately above; every proposed GREEN check remains unexecuted.
