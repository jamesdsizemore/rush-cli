# Q12 — yaml: syntax coverage, explicit schema and isolated migration trials

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

A YAML syntax pass must never imply the file's application schema was assessed. Scope: `rush yaml` / `rush_yaml`, local safe parsing, explicit OpenAPI/custom-schema dispatch and proposed isolated migration trials. Non-goals: general semantic correctness, arbitrary remote refs, silent schema guessing, source mutation or applying a migration.

| ID/category | Evidence/current behavior | Concrete change | Task/test and acceptance |
|---|---|---|---|
| Y1 defect | Audit4293-adjacent Q12 4535–4699; fixed Rush Spectral OAS rules applied to every YAML | Parse all YAML; generic syntax-only; OpenAPI detected only top-level marker | P1 generic avoids engine; malformed line/column |
| Y2 ordinary continuation | Audit4705–4752 | schema_kind plus contained custom ruleset digest, isolated code execution | P2 two real rulesets produce different diagnostics/digest |
| Y3 agent-side proposal | Audit4754–4907 | clean Git single-file candidate patch, old/new rules, explicit invariant comparison | P2 migration verified_candidate or rejected; source unchanged |
| Y4 integration/baseline | Phase70 T8–T16/T6/T27 | root identity, grants, schema parity, no false readiness | P3 transport; P4 exact regression |

## Current source and reproduced evidence

`src/rush/tools/yaml.py:6–15` SHA256 `d96829e2d2370cc5935fe5de4be5b6b21dabca63a72b1101a338b3817b9ce01e`; `src/rush/engines/spectral.py:18–148` SHA256 `e4ed3c2d6e4cb3c92bd7890cfa3899b486ebc9699b5d617e7903f82d73903e2c`; shared ContentTool as baseline. Built-in `src/rush/engines/_spectral-ruleset.yaml` assesses OAS3 info, not generic YAML. Spectral existing normalizer rejects malformed JSON/exit mismatch; those are preservation GREEN, not new defects.

Observed current Python3.12.12 call `YamlTool().run(generic_file)` containing `foo: bar`: shared engine callback invoked once; returned ok with no schema_status. Full future routing/OCI/migration checks remain proposed, unexecuted.

## Inputs, outputs and trust

`path: Path` required; `schema_kind: Literal["generic","openapi"]|None=None` (None=detect per document), `ruleset_path: str|None=None`, `trial_schema_migration: str|None=None`, `old_ruleset: str|None=None`, `new_ruleset: str|None=None`, `preserve_fields: list[str]|None=None`, `runtime_path: str|None=None`, `image_ref: str|None=None`; strict allow_build/allow_slow booleans false. CLI flags exactly hyphenated names, `--preserve-fields` repeatable; shared project/view/grant options retained. Root-relative document inputs; runtime sole approved external absolute executable.

Safe ruamel parser, no object constructors. Bound file size1MiB, documents1 per file, aliases64 and expanded nodes100000; detect excess before schema engine. Duplicate mapping keys fail. UTF8 errors canonical error. Syntax findings use problem_mark line+1/column+1; do not invent line1 when actual parser marks EOF line2. Empty YAML is valid syntax with generic schema not_assessed, not an empty target scope. Mixed valid/invalid files retains all syntax findings and marks partial schema execution. Generic scalar/sequence/mapping valid syntax only.

Top-level openapi or swagger marks candidate OpenAPI; explicit kind wins. Built-in rules currently support OAS3 only: Swagger2 yields schema_status not_assessed and reason unsupported_openapi_version unless custom ruleset; never imply OAS3 info rule assessed Swagger2. Invalid OpenAPI version marker is a schema finding, not silently generic. Built-in engine missing yields skipped schema child; syntax ok+required schema skipped aggregates warn. Generic syntax-only yields ok and engine ruamel.yaml with real installed version; `schema_kind=generic,syntax_status=ok,schema_status=not_assessed`.

Custom ruleset requires build grant, locally installed pinned Spectral image and P0 runtime; check before parsing/probing external code. Remote ruleset path rejected. Reject remote refs in source and ruleset as preflight, but this is not isolation. Spectral custom functions run only P0, so filesystem traversal/network from code fails in runtime. Metadata records ruleset_digest 64 lowercase hex, isolation_image, syntax_only_paths, syntax_failed_paths, schema_assessed_paths, selected_paths, assessed_paths. Assessed_paths describes syntax assessment; schema_assessed_paths only actual successful schema execution. Canonical child `syntax` and `spectral` preserve mixed status.

## P1 — Syntax/schema separation with meaningful current RED

**Required behavior.** Y1, including generic success without installed Spectral.
**Deliverables.** `src/rush/tools/yaml.py::YamlTool.run/__call__`; new `tests/test_yaml.py`. Existing Spectral normalize preserved.

~~~python
from pathlib import Path
from unittest.mock import patch
from rush.tools.yaml import YamlTool


def test_generic_yaml_syntax_only(tmp_path):
    source = tmp_path / "generic.yml"; source.write_text("foo: bar\n")
    calls = []
    def engine(*args, **kwargs):
        calls.append(args)
        return {"tool": "yaml", "engine": "spectral", "engine_version": "fixture",
                "status": "ok", "duration_ms": 0, "summary": "clean",
                "findings": [], "raw": None}
    with patch("rush.tools.content.run_engine", side_effect=engine), \
         patch("rush.tools.yaml.run_engine", side_effect=engine, create=True):
        result = YamlTool().run(source)
    assert calls == []  # current RED: actual generic input dispatched
    assert result["status"] == "ok"
    assert result["metadata"]["syntax_status"] == "ok"
    assert result["metadata"]["schema_status"] == "not_assessed"


def test_malformed_yaml_has_actual_parser_location(tmp_path):
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
    source = tmp_path / "broken.yml"; text = "foo: [broken\n"
    source.write_text(text)
    try:
        YAML(typ="safe").load(text)
    except YAMLError as exc:
        expected = (exc.problem_mark.line + 1, exc.problem_mark.column + 1)
    else:
        raise AssertionError("fixture must be malformed")
    result = YamlTool().run(source)
    assert result["status"] == "fail"
    syntax = next(f for f in result["findings"] if f["rule"] == "yaml-syntax")
    assert (syntax["line"], syntax["column"]) == expected
    assert result["metadata"]["schema_status"] == "not_assessed"
~~~

Minimum GREEN algorithm/code for generic branch; insert into overriding run after T8 selection/containment and before external engine availability check:

~~~python
from importlib.metadata import version
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from rush.tools.base import ToolResult

def parse_yaml_files(files, root, schema_kind=None):
    from ruamel.yaml.events import AliasEvent
    from rush.workflows.projects import open_contained_file
    import os
    selected, findings = [], []
    for source in files:
        with os.fdopen(open_contained_file(root, source.relative_to(root).as_posix()),
                       "r", encoding="utf-8") as stream:
            text = stream.read(1_048_577)
        if len(text.encode("utf-8")) > 1_048_576:
            raise ValueError("yaml_input_too_large")
        try:
            events = list(YAML(typ="safe").parse(text))
            if len(events) > 100_000 or sum(isinstance(e, AliasEvent) for e in events) > 64:
                raise ValueError("yaml_complexity_limit")
            document = YAML(typ="safe").load(text)
        except YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            finding = {"path": source.relative_to(root).as_posix(),
                       "rule": "yaml-syntax", "severity": "error",
                       "message": str(exc)}
            if mark is not None:
                finding.update(line=mark.line + 1, column=mark.column + 1)
            findings.append(finding)
            continue
        kind = schema_kind or (
            "openapi" if isinstance(document, dict) and
            ("openapi" in document or "swagger" in document) else "generic")
        selected.append((source, kind, document))
    return selected, findings

def syntax_only_result(files, selected, findings, root):
    names = [p.relative_to(root).as_posix() for p in files]
    return ToolResult(
        tool="yaml", engine="ruamel.yaml", engine_version=version("ruamel.yaml"),
        status="fail" if findings else "ok", duration_ms=0,
        summary="YAML syntax assessed; generic schema not assessed",
        findings=findings, raw=None,
        metadata={"selected_paths": names, "assessed_paths": names,
                  "schema_kind": "generic",
                  "syntax_status": "fail" if findings else "ok",
                  "schema_status": "not_assessed",
                  "syntax_failed_paths": [f["path"] for f in findings],
                  "schema_assessed_paths": []})
~~~

Run uses existing `collect_files(path,{"yml","yaml"},strict=True)`; then `PhysicalRoot(root).open_contained(relative)` for every candidate. Empty returns skipped no_yaml_targets. Validate schema_kind before collection. Call above parser; generic/no ruleset returns syntax_only_result. Otherwise dispatch only valid OAS3 sources to existing SpectralEngine/run_engine, merge syntax findings and children. Validate expanded graph with identity-counted DFS bounded100000 nodes (active identity cycle rejects yaml_alias_cycle); event bound alone does not bound alias expansion. Use no-follow reader above for source, rulesets, fixtures and patches. Failure to read/parse/validate any input never becomes clean.

**Constraints.** No replacing Spectral parser; no generic OAS claim. No dependency addition (ruamel.yaml installed).
**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_yaml.py -q`.
**Completion.** Generic avoids engine, malformed line/column exact, OAS3 missing info produces existing rule, Swagger2 scope explicit; all selected documents accounted for.

## P2 — Custom rules and candidate migration

**Required behavior.** Y2/Y3 remain distinct ordinary/agent-side proposals; build grant for custom code, build+slow for trial. Rejection/denial before any scanner/version/temp/worktree.

**Deliverables.** `src/rush/tools/yaml.py::_isolated_spectral` and `trial_schema_migration` controller; `tests/test_yaml.py`. External owned candidate code below uses existing run_subprocess/open_contained_file and local Git. PatchSandboxManager is deliberately excluded: its source .rush/.gitignore and worktree registry writes violate this packet's no-source-write contract. P0 provider new shared files specified here.

Complete isolated helper:

~~~python
def _isolated_spectral(root, sources, ruleset, *, runtime_path, image_ref):
    import json, tempfile
    from pathlib import Path
    from rush.io.physical_paths import PhysicalRoot
    from rush.engines.spectral import SpectralEngine
    from rush.runtime.isolated_process import run_isolated_argv
    from rush.tools.common import error_result
    selected = {p.relative_to(root).as_posix() for p in sources}
    relative_rule = ruleset.relative_to(root).as_posix()
    with tempfile.TemporaryDirectory(prefix="rush-spectral-") as directory:
        process = run_isolated_argv(
            root, Path(directory), runtime_path=runtime_path, image_ref=image_ref,
            entrypoint="/usr/local/bin/spectral",
            argv=["lint", "--ruleset", "/work/" + relative_rule, "--format", "json",
                  "--fail-severity", "warn", "--ignore-unknown-format",
                  *["/work/" + p for p in sorted(selected)]], timeout_s=120)
    try:
        report = json.loads(process.stdout)
        if not isinstance(report, list):
            raise ValueError("report must be array")
        for item in report:
            if not isinstance(item, dict) or not isinstance(item.get("source"), str):
                raise ValueError("finding source required")
            raw_source = item["source"]
            relative = (Path(raw_source).relative_to("/work").as_posix()
                        if raw_source.startswith("/work/") else raw_source)
            if relative not in selected:
                raise ValueError("finding outside selected schema sources")
            item["source"] = str(PhysicalRoot(root).open_contained(relative))
        raw = {"exit_code": process.returncode, "stdout": json.dumps(report),
               "stderr": process.stderr, "duration_ms": 0}
        result = SpectralEngine().normalize(raw, root, "yaml", probe_version=False)
        result.setdefault("metadata", {}).update(
            isolation_image=image_ref,
            engine_version_unavailable_reason="isolated_engine_version_unprobed")
        return result
    except (TypeError, ValueError) as exc:
        return error_result("yaml", "spectral", str(exc),
                            terminal_reason="malformed_output")
~~~

Migration input: exactly one YAML file, root-relative old/new rulesets and patch, nonempty dotted preserve_fields. Complete external candidate controller below is authoritative: clean Git HEAD and tracked inputs, original rules check, external copied snapshot with independent Git metadata, exact one-file changed set, new rules check, type-and-value invariants, unconditional cleanup and whole-source/worktree-registry comparison. No source worktree registration or .rush/.gitignore edit. Cleanup/source drift errors suppress verified_candidate.

Runnable custom-rule acceptance (real pinned Spectral image; env prerequisites hard fail if absent):

~~~python
def test_local_ruleset_digest(tmp_path):
    import os
    from rush.permissions import ExecutionPermissions
    (tmp_path / "rush.toml").write_text("")
    source = tmp_path / "api.yaml"
    source.write_text("openapi: 3.0.0\ninfo:\n  title: Demo\n")
    rules = tmp_path / "rules"; rules.mkdir()
    for field in ("title", "version"):
        (rules / (field + ".yaml")).write_text(
            "extends: []\nrules:\n  require-" + field + ":\n"
            "    given: '$.info'\n    severity: error\n    then:\n"
            "      field: " + field + "\n      function: truthy\n")
    kwargs = dict(schema_kind="openapi",
                  runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
                  image_ref=os.environ["RUSH_TEST_SPECTRAL_IMAGE"],
                  permissions=ExecutionPermissions(build=True))
    good = YamlTool().run(source, ruleset_path="rules/title.yaml", **kwargs)
    bad = YamlTool().run(source, ruleset_path="rules/version.yaml", **kwargs)
    assert good["status"] == "ok"
    assert bad["status"] == "fail"
    assert [f["rule"] for f in bad["findings"]] == ["require-version"]
    assert good["metadata"]["ruleset_digest"] != bad["metadata"]["ruleset_digest"]
~~~

Runnable migration acceptance (append to tests/test_yaml.py):

~~~python
def test_schema_migration_preserves_version_field(tmp_path):
    import os, subprocess
    from pathlib import Path
    from rush.permissions import ExecutionPermissions
    from rush.tools.yaml import YamlTool
    # External prerequisites: RUSH_TEST_OCI_RUNTIME absolute executable path,
    # RUSH_TEST_SPECTRAL_IMAGE immutable locally installed sha256 image with
    # /usr/local/bin/spectral. Missing prerequisites fail this acceptance test.
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    image = os.environ["RUSH_TEST_SPECTRAL_IMAGE"]
    root = tmp_path
    (root/"rules").mkdir(); (root/"fixes").mkdir()
    (root/"api.yaml").write_text(
        "openapi: 3.0.0\ninfo:\n  title: Demo\n  version: '1.2'\n")
    (root/"rules/v1.yaml").write_text(
        "extends: []\nrules:\n  has-info:\n    given: '$'\n"
        "    severity: error\n    then:\n      field: info\n      function: truthy\n")
    (root/"rules/v2.yaml").write_text(
        "extends: []\nrules:\n  has-contact:\n    given: '$.info'\n"
        "    severity: error\n    then:\n      field: contact\n      function: truthy\n")
    (root/"fixes/add-contact.diff").write_text(
        "--- a/api.yaml\n+++ b/api.yaml\n@@ -2,3 +2,4 @@\n info:\n"
        "   title: Demo\n   version: '1.2'\n+  contact: team\n")
    (root/"fixes/change-version.diff").write_text(
        "--- a/api.yaml\n+++ b/api.yaml\n@@ -2,3 +2,4 @@\n info:\n"
        "   title: Demo\n-  version: '1.2'\n+  version: '2.0'\n"
        "+  contact: team\n")
    for argv in (["git","init","-q"],["git","add","."],
                 ["git","-c","user.name=Rush Test","-c","user.email=rush@example.invalid",
                  "commit","-qm","fixture"]):
        subprocess.run(argv, cwd=root, check=True)
    from rush.tools.yaml import _yaml_tree
    snapshot = _yaml_tree(root)
    git_env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    worktrees = subprocess.run(["git", "worktree", "list", "--porcelain"],
        cwd=root, env=git_env, capture_output=True, text=True, check=True).stdout
    original = (root/"api.yaml").read_bytes()
    result = YamlTool().run(root/"api.yaml",
        trial_schema_migration="fixes/add-contact.diff",
        old_ruleset="rules/v1.yaml", new_ruleset="rules/v2.yaml",
        preserve_fields=["info.version"],
        runtime_path=runtime, image_ref=image,
        permissions=ExecutionPermissions(build=True, slow=True))
    trial = result["metadata"]["migration_trial"]
    assert trial["status"] == "verified_candidate"
    assert trial["old_status"] == trial["new_status"] == "ok"
    assert trial["preserved_fields"] == [{"field":"info.version","intact":True}]
    assert (root/"api.yaml").read_bytes() == original
    assert _yaml_tree(root) == snapshot
    assert subprocess.run(["git", "worktree", "list", "--porcelain"],
        cwd=root, env=git_env, capture_output=True, text=True, check=True).stdout == worktrees
    # Second committed fixture patch changes info.version; invariant rejects it.
    bad = YamlTool().run(root/"api.yaml",
        trial_schema_migration="fixes/change-version.diff",
        old_ruleset="rules/v1.yaml", new_ruleset="rules/v2.yaml",
        preserve_fields=["info.version"],
        runtime_path=runtime, image_ref=image,
        permissions=ExecutionPermissions(build=True, slow=True))
    assert bad["metadata"]["migration_trial"]["status"] == "rejected"
    assert _yaml_tree(root) == snapshot
    assert subprocess.run(["git", "worktree", "list", "--porcelain"],
        cwd=root, env=git_env, capture_output=True, text=True, check=True).stdout == worktrees
~~~

Full fixture above uses actual Git sandbox and real isolated Spectral. Add tests for extra patch target, dirty Git, changed invariant type, omitted field, symlink/remote rules, source drift during trial, failed cleanup and denied grants; each asserts exact rejected/error/denied and no candidate application.

**Constraints.** No network; local Spectral functions are executable code; no host fallback. Patch worktree is a disposable candidate, not production application.
**Checks.** P1 module plus P0 real runtime suite.
**Completion.** Two real rulesets differ diagnostically; candidate preserves info.version and source bytes; violating candidate rejected; cleanup/readback verified.

### Complete bounded graph and external candidate implementation

Add these complete functions to src/rush/tools/yaml.py. They replace PatchSandboxManager use; that manager changes source .rush/.gitignore/worktree registry and cannot satisfy this packet's no-source-write contract. Candidate has its own external temporary Git repository; source Git metadata is read with optional locks disabled.

~~~python
import hashlib
import os
import re
import tempfile
from pathlib import Path
from ruamel.yaml import YAML
from rush.permissions import ExecutionPermissions, check_permissions
from rush.runtime.binaries import resolve_binary
from rush.runtime.subprocesses import run_subprocess
from rush.workflows.projects import open_contained_file

def _yaml_bytes(root, relative, limit=1_048_576):
    with os.fdopen(open_contained_file(root, str(relative)), "rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("yaml_input_too_large")
    return value

def validate_expanded_yaml(document):
    active = set()
    count = 0
    def visit(value, depth):
        nonlocal count
        count += 1
        if count > 100_000 or depth > 64:
            raise ValueError("yaml_complexity_limit")
        if not isinstance(value, (dict, list, tuple)):
            return
        identity = id(value)
        if identity in active:
            raise ValueError("yaml_alias_cycle")
        active.add(identity)
        try:
            if isinstance(value, dict):
                for key, child in value.items():
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in value:
                    visit(child, depth + 1)
        finally:
            active.remove(identity)
    # Repeated aliases count each expansion, not merely each object identity.
    visit(document, 0)

def _yaml_tree(root):
    entries, total = {}, 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError("source_symlink")
        if path.is_dir():
            entries[relative + "/"] = None
        elif path.is_file():
            data = _yaml_bytes(root, relative, 16_777_216)
            total += len(data)
            if len(entries) >= 100_000 or total > 1_073_741_824:
                raise ValueError("source_inventory_limit")
            entries[relative] = data
        else:
            raise ValueError("source_special_file")
    return entries

def trial_schema_migration(root, source, patch_path, old_ruleset, new_ruleset,
                           preserve_fields, *, runtime_path, image_ref, permissions):
    allowed, _ = check_permissions(ExecutionPermissions(build=True, slow=True), permissions)
    if not allowed:
        return {"status": "denied", "reason": "missing_grants"}
    if (not isinstance(preserve_fields, list) or not preserve_fields or
        any(type(f) is not str or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", f)
            for f in preserve_fields)):
        raise ValueError("invalid_preserve_fields")
    relative = source.relative_to(root).as_posix()
    original = _yaml_bytes(root, relative)
    patch_bytes = _yaml_bytes(root, patch_path)
    old_bytes = _yaml_bytes(root, old_ruleset)
    new_bytes = _yaml_bytes(root, new_ruleset)
    old_document = YAML(typ="safe").load(original.decode("utf-8"))
    validate_expanded_yaml(old_document)
    binary = resolve_binary("git")
    if binary is None:
        raise ValueError("git_unavailable")
    env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_OPTIONAL_LOCKS": "0"}
    def git(where, arguments):
        result = run_subprocess([binary, "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=" + os.devnull, "-C", str(where), *arguments],
            env=env, timeout=30)
        if result.returncode:
            raise ValueError("candidate_git_failed")
        return result.stdout
    # Snapshot includes .git, .rush, ignored files, directory identities by name.
    before = _yaml_tree(root)
    registry = git(root, ["worktree", "list", "--porcelain"])
    if git(root, ["status", "--porcelain=v1", "--untracked-files=all"]).strip():
        raise ValueError("dirty_source")
    git(root, ["rev-parse", "--verify", "HEAD"])
    git(root, ["ls-files", "--error-unmatch", "--",
               relative, patch_path, old_ruleset, new_ruleset])
    fields = list(dict.fromkeys(preserve_fields))
    def lookup(document, field):
        value = document
        for segment in field.split("."):
            if not isinstance(value, dict) or segment not in value:
                raise ValueError("missing_preserved_field")
            value = value[segment]
        return value
    wanted = {field: lookup(old_document, field) for field in fields}
    def digest(data):
        return hashlib.sha256(data).hexdigest()
    try:
        old = _isolated_spectral(root, [source], root / old_ruleset,
            runtime_path=runtime_path, image_ref=image_ref)
        if old["status"] != "ok":
            return {"status": "rejected", "old_status": old["status"],
                    "new_status": "not_run", "preserved_fields": [],
                    "source_digest": digest(original), "candidate_digest": None}
        with tempfile.TemporaryDirectory(prefix="rush-yaml-candidate-") as directory:
            candidate = Path(directory) / "tree"; candidate.mkdir(mode=0o700)
            for name, data in before.items():
                parts = Path(name).parts
                if parts[0] in {".git", ".rush"}:
                    continue
                target = candidate / name.rstrip("/")
                if data is None:
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            candidate_before = _yaml_tree(candidate)
            git(candidate, ["init", "-q"])
            owned_patch = Path(directory) / "change.patch"
            owned_patch.write_bytes(patch_bytes)
            git(candidate, ["apply", "--check", str(owned_patch)])
            git(candidate, ["apply", str(owned_patch)])
            candidate_after = {k: v for k, v in _yaml_tree(candidate).items()
                               if Path(k).parts[0] != ".git"}
            changed = {k for k in set(candidate_before) | set(candidate_after)
                       if candidate_before.get(k) != candidate_after.get(k)}
            if changed != {relative} or relative not in candidate_after:
                raise ValueError("candidate_changed_other_paths")
            if (_yaml_bytes(candidate, old_ruleset) != old_bytes or
                _yaml_bytes(candidate, new_ruleset) != new_bytes):
                raise ValueError("candidate_changed_rules")
            edited = _yaml_bytes(candidate, relative)
            new_document = YAML(typ="safe").load(edited.decode("utf-8"))
            validate_expanded_yaml(new_document)
            preserved = []
            for field in fields:
                try:
                    actual = lookup(new_document, field)
                    intact = type(actual) is type(wanted[field]) and actual == wanted[field]
                except ValueError:
                    intact = False
                preserved.append({"field": field, "intact": intact})
            new = _isolated_spectral(candidate, [candidate / relative], candidate / new_ruleset,
                runtime_path=runtime_path, image_ref=image_ref)
            return {"status": "verified_candidate" if new["status"] == "ok" and
                    all(row["intact"] for row in preserved) else "rejected",
                    "old_status": old["status"], "new_status": new["status"],
                    "preserved_fields": preserved, "source_digest": digest(original),
                    "candidate_digest": digest(edited)}
    finally:
        if _yaml_tree(root) != before or git(root, ["worktree", "list", "--porcelain"]) != registry:
            raise ValueError("source_changed_during_trial")
~~~

Insert validate_expanded_yaml(document) immediately after safe load in parse_yaml_files. Any cycle/limit error maps canonical error yaml_complexity_limit before engine calls. Migration run dispatch before ordinary lint invokes this helper with exactly one selected source and returns metadata.migration_trial; status verified_candidate→ok, rejected→fail, denied→skipped. Invalid input or cleanup/source-drift exception→error with fixed reason; P0 exceptions retain unavailable/cleanup mapping. No candidate helper uses source Git worktree registration.

Runnable structural/adversarial tests, appended to tests/test_yaml.py:

~~~python
def test_expanded_alias_budget_and_cycle():
    from rush.tools.yaml import validate_expanded_yaml
    shared = "leaf"
    for _ in range(18):
        shared = [shared, shared]
    for document, reason in ((shared, "yaml_complexity_limit"),):
        try:
            validate_expanded_yaml(document)
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError("expanded alias bomb accepted")
    cycle = []; cycle.append(cycle)
    try:
        validate_expanded_yaml(cycle)
    except ValueError as error:
        assert str(error) == "yaml_alias_cycle"
    else:
        raise AssertionError("alias cycle accepted")
~~~

Strengthen the complete real migration test above: after its fixture commit and before first call capture _yaml_tree(root) and run git worktree list --porcelain with GIT_OPTIONAL_LOCKS=0; after each good/bad trial assert both exact snapshots unchanged. Concrete insertion (same test scope):

~~~python
from rush.tools.yaml import _yaml_tree
snapshot = _yaml_tree(root)
git_env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
worktrees = subprocess.run(["git", "worktree", "list", "--porcelain"],
    cwd=root, env=git_env, capture_output=True, text=True, check=True).stdout
# Place these exact assertions immediately after each existing good/bad call.
assert _yaml_tree(root) == snapshot
assert subprocess.run(["git", "worktree", "list", "--porcelain"],
    cwd=root, env=git_env, capture_output=True, text=True, check=True).stdout == worktrees
~~~

### Exact migration dispatch insertion

In YamlTool.run, after T8 root/path validation and strict selected file collection, before ordinary syntax/schema dispatch, use this complete branch. Existing method keywords match the public signature below; globals lookup distinguishes public patch argument from helper function.

~~~python
if trial_schema_migration is not None:
    from rush.permissions import ExecutionPermissions, check_permissions
    from rush.tools.base import ToolResult
    from rush.tools.common import error_result, skipped_result
    allowed, _ = check_permissions(ExecutionPermissions(build=True, slow=True), permissions)
    if not allowed:
        return skipped_result("yaml", None, "missing_grants",
            metadata={"reason": "missing_grants", "migration_trial": {"status": "denied"}})
    if len(files) != 1 or not old_ruleset or not new_ruleset or not runtime_path or not image_ref:
        return error_result("yaml", None, "Migration requires one source and complete inputs",
                            terminal_reason="MIGRATION_INPUT_INVALID")
    trial = globals()["trial_schema_migration"](
        root, files[0], trial_schema_migration, old_ruleset, new_ruleset,
        list(preserve_fields or []), runtime_path=runtime_path,
        image_ref=image_ref, permissions=permissions)
    return ToolResult(tool="yaml", engine="spectral", engine_version=None,
        status="ok" if trial["status"] == "verified_candidate" else "fail",
        duration_ms=0, summary="Candidate schema migration assessed",
        findings=[], raw=None, metadata={"migration_trial": trial,
            "isolation_image": image_ref, "selected_paths": [
                files[0].relative_to(root).as_posix()],
            "engine_version_unavailable_reason": "isolated_engine_version_unprobed"})
~~~

Place branch inside command's existing exception boundary: ValueError/OSError/YAMLError becomes MIGRATION_INPUT_INVALID error; P0 IsolationUnavailable becomes skipped reason isolation_unavailable, IsolationCleanupError becomes error reason isolation_cleanup_failed, cancellation propagates after cleanup. No error branch publishes verified_candidate.

### Complete YamlTool.run dispatcher

This exact replacement assembles syntax, built-in schema, custom rules and candidate migration through the declared helpers. Existing public __call__ below forwards all fields. Use imports defined in prior complete blocks.

~~~python
def run(self, path, *, config=None, context=None, schema_kind=None, ruleset_path=None,
        trial_schema_migration=None, old_ruleset=None, new_ruleset=None,
        preserve_fields=None, runtime_path=None, image_ref=None, permissions=None):
    from pathlib import Path
    from rush.engines import ENGINES
    from rush.engines.spectral import _REMOTE_REF
    from rush.invocation.targets import select_root, assert_contained
    from rush.io.physical_paths import PhysicalRoot, ContainmentError
    from rush.permissions import ExecutionPermissions, check_permissions
    from rush.runtime.isolated_process import IsolationUnavailable, IsolationCleanupError
    from rush.tools.common import error_result, skipped_result, run_engine
    from rush.tools.routing import collect_files, aggregate_results
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
        if schema_kind not in {None, "generic", "openapi"}:
            raise ValueError("schema_kind_invalid")
        effectful = ruleset_path is not None or trial_schema_migration is not None
        if effectful:
            allowed, _ = check_permissions(ExecutionPermissions(
                build=True, slow=trial_schema_migration is not None), permissions)
            if not allowed:
                return skipped_result(self.name, None, "missing_grants",
                    metadata={"reason": "missing_grants", "migration_trial": {"status": "denied"}})
            if not runtime_path or not image_ref:
                raise IsolationUnavailable("approved runtime and image required")
        physical = PhysicalRoot(root)
        files = [physical.open_contained(p.relative_to(root))
                 for p in collect_files(path, {"yml", "yaml"}, strict=True)]
        if not files:
            return skipped_result(self.name, None, "no_yaml_targets")
        if trial_schema_migration is not None:
            if len(files) != 1 or not old_ruleset or not new_ruleset:
                raise ValueError("migration_inputs_invalid")
            trial = globals()["trial_schema_migration"](root, files[0],
                trial_schema_migration, old_ruleset, new_ruleset, list(preserve_fields or []),
                runtime_path=runtime_path, image_ref=image_ref, permissions=permissions)
            return ToolResult(tool=self.name, engine="spectral", engine_version=None,
                status="ok" if trial["status"] == "verified_candidate" else "fail",
                duration_ms=0, summary="Candidate schema migration assessed",
                findings=[], raw=None, metadata={"migration_trial": trial,
                    "isolation_image": image_ref,
                    "selected_paths": [files[0].relative_to(root).as_posix()],
                    "engine_version_unavailable_reason": "isolated_engine_version_unprobed"})
        selected, findings = parse_yaml_files(files, root, schema_kind)
        for _, _, document in selected:
            validate_expanded_yaml(document)
        syntax = syntax_only_result(files, selected, findings, root)
        schema_sources, unsupported = [], []
        if ruleset_path is not None:
            rule = physical.open_contained(ruleset_path)
            rule_bytes = _yaml_bytes(root, ruleset_path)
            if _REMOTE_REF.search(rule_bytes.decode("utf-8")):
                raise ValueError("remote_ruleset_reference")
            schema_sources = [source for source, _, _ in selected]
        else:
            for source, kind, document in selected:
                if kind == "generic":
                    continue
                if isinstance(document, dict) and document.get("swagger") == "2.0":
                    unsupported.append(source.relative_to(root).as_posix())
                    continue
                if (not isinstance(document, dict) or type(document.get("openapi")) is not str
                    or not re.fullmatch(r"3\.\d+\.\d+", document["openapi"])):
                    syntax["findings"].append({"path": source.relative_to(root).as_posix(),
                        "rule": "openapi-version", "severity": "error",
                        "message": "OAS3 version marker required"})
                    syntax["status"] = "fail"
                    continue
                schema_sources.append(source)
        if not schema_sources:
            syntax["metadata"].update(schema_kind=schema_kind or "generic")
            if unsupported:
                syntax["metadata"].update(schema_status="not_assessed",
                    reason="unsupported_openapi_version", unsupported_schema_paths=unsupported)
            return syntax
        for source in schema_sources:
            if _REMOTE_REF.search(_yaml_bytes(root, source.relative_to(root)).decode("utf-8")):
                raise ValueError("remote_document_reference")
        if ruleset_path is not None:
            schema = _isolated_spectral(root, schema_sources, rule,
                runtime_path=runtime_path, image_ref=image_ref)
            schema.setdefault("metadata", {})["ruleset_digest"] = hashlib.sha256(rule_bytes).hexdigest()
        else:
            schema = run_engine(ENGINES["spectral"], root, list(map(str, schema_sources)),
                tool_name=self.name, consumed_paths=list(map(str, schema_sources)), project_root=root)
        result = aggregate_results(self.name, [syntax, schema])
        facts = dict(syntax["metadata"])
        facts.update(schema.get("metadata", {}))
        facts.update(schema_kind=schema_kind or "openapi", syntax_status=syntax["metadata"]["syntax_status"],
            schema_status=schema["status"],
            selected_paths=[p.relative_to(root).as_posix() for p in files],
            assessed_paths=[p.relative_to(root).as_posix() for p in files],
            schema_assessed_paths=[p.relative_to(root).as_posix() for p in schema_sources]
                if schema["status"] in {"ok", "warn", "fail"} else [])
        # Aggregate retains its combined provenance; copy domain facts only.
        for key in ("engines", "execution", "scope"):
            facts.pop(key, None)
        result["metadata"].update(facts)
        return result
    except IsolationUnavailable:
        return skipped_result(self.name, None, "isolation_unavailable",
                              metadata={"reason": "isolation_unavailable"})
    except IsolationCleanupError:
        return error_result(self.name, None, "Schema cleanup failed",
                            terminal_reason="isolation_cleanup_failed")
    except (ValueError, OSError, ContainmentError, YAMLError):
        return error_result(self.name, None, "YAML input or candidate invalid",
                            terminal_reason="YAML_INPUT_INVALID")
~~~

## P3 — Real CLI and initialized stdio MCP parity

**Required behavior.** Explicit options reach shared tool implementation on both transports. Matching domain projection below is equal; target identities and grants cannot be inferred from tools/list alone. Test-owned engine below proves forwarding/parser behavior only; P2 real-engine/OCI tests separately prove runtime behavior.

**Deliverables.** Add following complete module to `tests/test_yaml_transport.py`; Batch integration owner adds command's explicit options to `_TOOL_CLI_OPTIONS` and exact `ToolOptionSpec` tuple to existing `TOOL_SPECS["yaml"]`. Preserve existing `make_tool_wrapper`/executor; context is internal. No generic introspection factory, MCP-only implementation or new CLI route.

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

COMMAND = "yaml"
BINARY = "spectral"
SOURCE = "generic.yml"
BODY = "foo: bar\n"
OPTIONS = {"schema_kind":"generic"}
CLI_OPTIONS = ["--schema-kind","generic"]
EXPECTED = {"status":"ok","schema_kind":"generic","syntax_status":"ok","schema_status":"not_assessed"}
PROJECTION = ["schema_kind","syntax_status","schema_status"]


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
    assert not marker.exists()


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
`rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_yaml_transport.py tests/test_yaml.py tests/test_cli_registry.py tests/test_mcp.py -q`

**Completion.** Real process CLI and initialized stdio call agree on stated domain values, missing/denied input produces zero analysis/state effects, parameter schema is exact, source bytes unchanged, and separate runtime checks pass.


Append this complete denied-request case to the same transport module. Permission denial is preflight for the whole explicitly requested operation, returning skipped with metadata.reason="missing_grants"; no engine/version/runtime call occurs.

~~~python
def test_cli_stdio_denied_request_zero_effects(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(BODY)
    for relative, text in {"rules.yaml": "extends: []\nrules: {}\n"}.items():
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
    options = {"schema_kind": "generic", "ruleset_path": "rules.yaml"}
    options.update(runtime_path=runtime, image_ref=image)
    flags = ["--schema-kind", "generic", "--ruleset-path", "rules.yaml"] + ["--runtime-path", runtime, "--image-ref", image]
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

Add `probe_version: bool = True` keyword-only parameter to `src/rush/engines/spectral.py::SpectralEngine.normalize`. Its only field change is:
~~~text
engine_version=self.version() if probe_version else None,
~~~
This is an exact keyword-expression replacement, not a standalone module. Default preserves all current callers and parser/exit consistency. In isolated path call `normalize(raw,root,"yaml",probe_version=False)`; never call host version to label container execution. Result records `engine_version=None`, `metadata.engine_version_unavailable_reason="isolated_engine_version_unprobed"` and actual approved `isolation_image`. A later optional image version probe is unnecessary for this packet; no version is invented.

Populate isolated child `metadata.engines` with engine="spectral", executable.path="/usr/local/bin/spectral", executable.sha256=null, executable.reason="image_scoped_identity", version=null, version_unavailable_reason="isolated_engine_version_unprobed", config.path="/work/<ruleset-or-config>", config.sha256=<actual bytes digest>, config.reason=null, analysis_environment={mode:"oci",image_ref:<approved digest>}, status/summary copied from normalized child, cwd="/work", recorded main invocation, and actual selected-file scope. This is container identity, not host executable identity. The adapter parser still validates every reported selected path; metadata survives parent aggregation.

Add this complete preservation/security test to tests/test_yaml.py; normalization can occur without any host engine:
~~~python
def test_isolated_normalize_never_probes_host_version(tmp_path):
    from rush.engines.spectral import SpectralEngine
    with patch.object(SpectralEngine, "version",
                      side_effect=AssertionError("host version probe forbidden")):
        result = SpectralEngine().normalize(
            {"exit_code": 0, "stdout": "[]", "stderr": ""},
            tmp_path, "yaml", probe_version=False)
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
GRANTED_SCHEMA = exact_schema(json.loads(r'''{"schema_kind":{"anyOf":[{"enum":["generic","openapi"],"type":"string"},{"type":"null"}],"default":null},"ruleset_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"trial_schema_migration":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"old_ruleset":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"new_ruleset":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"preserve_fields":{"anyOf":[{"type":"array","items":{"type":"string"}},{"type":"null"}],"default":null},"runtime_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"image_ref":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"allow_build":{"type":"boolean","default":false},"allow_slow":{"type":"boolean","default":false}}'''))

def test_granted_migration_cli_stdio_foreign_cwd(tmp_path):
    import json, os, subprocess
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "api.yaml").write_text("openapi: 3.0.0\ninfo:\n  version: '1'\n")
    (root / "old.yaml").write_text("extends: []\nrules:\n  info:\n    given: '$'\n    then:\n      field: info\n      function: truthy\n")
    (root / "new.yaml").write_text("extends: []\nrules:\n  title:\n    given: '$.info'\n    then:\n      field: title\n      function: truthy\n")
    (root / "change.patch").write_text("--- a/api.yaml\n+++ b/api.yaml\n@@ -1,3 +1,4 @@\n openapi: 3.0.0\n info:\n   version: '1'\n+  title: Demo\n")
    env, foreign, project = granted_environment(tmp_path, root)
    for args in (["init", "-q"], ["add", "."],
                 ["-c", "user.name=Rush", "-c", "user.email=test@example.invalid",
                  "-c", "core.hooksPath=" + os.devnull, "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, env=env, check=True)
    before = entire_tree(root)
    image = os.environ["RUSH_TEST_SPECTRAL_IMAGE"]
    runtime = os.environ["RUSH_TEST_OCI_RUNTIME"]
    left = granted_cli(foreign, env, "yaml", root / "api.yaml",
        ["--trial-schema-migration", "change.patch", "--old-ruleset", "old.yaml",
         "--new-ruleset", "new.yaml", "--preserve-fields", "info.version",
         "--runtime-path", runtime, "--image-ref", image, "--allow-build", "--allow-slow"], 0)
    right = granted_stdio(foreign, env, "yaml",
        {"project": project, "path": "api.yaml", "trial_schema_migration": "change.patch",
         "old_ruleset": "old.yaml", "new_ruleset": "new.yaml",
         "preserve_fields": ["info.version"], "runtime_path": runtime, "image_ref": image,
         "allow_build": True, "allow_slow": True, "no_cache": True}, GRANTED_SCHEMA)
    assert left["status"] == right["status"] == "ok"
    assert left["metadata"]["migration_trial"] == right["metadata"]["migration_trial"]
    trial = right["metadata"]["migration_trial"]
    assert trial["status"] == "verified_candidate"
    assert trial["old_status"] == trial["new_status"] == "ok"
    assert trial["preserved_fields"] == [{"field": "info.version", "intact": True}]
    assert trial["source_digest"] != trial["candidate_digest"]
    assert entire_tree(root) == before

~~~

## Literal transport/configuration edits and future PR scope

Batch integration owner appends only this command's tuple to existing `src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS` (factory already forwards `**tool_options`). Existing permission options are not redeclared:

~~~python
"yaml": (
    click.Option(["--schema-kind"], type=click.Choice(["generic","openapi"]), default=None),
    click.Option(["--ruleset-path"], type=str, default=None),
    click.Option(["--trial-schema-migration"], type=str, default=None),
    click.Option(["--old-ruleset"], type=str, default=None),
    click.Option(["--new-ruleset"], type=str, default=None),
    click.Option(["--preserve-fields"], type=str, multiple=True, default=()),
    click.Option(["--runtime-path"], type=str, default=None),
    click.Option(["--image-ref"], type=str, default=None),
),
~~~

In `src/rush/catalog.py`, replace this command's `option_specs` with the following complete tuple, retaining canonical name/category/maturity/engine mapping. Each local document parameter intentionally uses default path_kind="none" because tool validates it root-relatively through PhysicalRoot; do not add it to cwd-relative `_CWD_RELATIVE_ARGS`. External runtime is never interpreted as project file. This explicit anchor decision prevents nested cwd rebasing.

~~~python
option_specs=(
    ToolOptionSpec("schema_kind", str, default=None, choices=("generic", "openapi",), description="schema kind; see command contract"),
    ToolOptionSpec("ruleset_path", str, default=None, description="ruleset path; see command contract"),
    ToolOptionSpec("trial_schema_migration", str, default=None, description="trial schema migration; see command contract"),
    ToolOptionSpec("old_ruleset", str, default=None, description="old ruleset; see command contract"),
    ToolOptionSpec("new_ruleset", str, default=None, description="new ruleset; see command contract"),
    ToolOptionSpec("preserve_fields", tuple, default=None, description="preserve fields; see command contract"),
    ToolOptionSpec("runtime_path", str, default=None, description="runtime path; see command contract"),
    ToolOptionSpec("image_ref", str, default=None, description="image ref; see command contract"),
)
~~~

Add exact typed callable to `src/rush/tools/yaml.py::YamlTool` (imports supplied; place method inside class). Its `run` accepts same domain options plus `permissions,context,config`, with all defaults identical; list/tuple preserve_fields normalize once to list. Strict booleans preserve invalid-type rejection.

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
    schema_kind: Literal["generic", "openapi"] | None = None,
    ruleset_path: str | None = None,
    trial_schema_migration: str | None = None,
    old_ruleset: str | None = None,
    new_ruleset: str | None = None,
    preserve_fields: list[str] | None = None,
    runtime_path: str | None = None,
    image_ref: str | None = None,
    allow_build: StrictBool = False,
    allow_slow: StrictBool = False,
    context: InvocationContext | None = None,
) -> ToolResult:
    if any(type(value) is not bool for value in (allow_build, allow_slow,)):
        return error_result("yaml", None, "boolean arguments must be booleans",
                            terminal_reason="INVALID_REQUEST")
    return self.run(
        path,
        schema_kind=schema_kind,
        ruleset_path=ruleset_path,
        trial_schema_migration=trial_schema_migration,
        old_ruleset=old_ruleset,
        new_ruleset=new_ruleset,
        preserve_fields=preserve_fields,
        runtime_path=runtime_path,
        image_ref=image_ref,
        permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        context=context,
    )
~~~

Tracked configuration guide is `docs/CONFIGURATION.md` (uppercase Git path), and existing conservative example is `examples/rush.toml`; both are shared integration-owner writes. Existing `ToolOptionSpec` tuple is configuration schema. Preserve existing tables; append only this command's single safe-default table described below. Update command section in `docs/reference/configuration-reference.md` with literal `[tools.yaml]` keys/defaults and root-relative semantics, corresponding sections in `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/result-reference.md`. Add one clean, one no-work, one denied, one failed example with actual result/exit. Update `tests/test_cli_registry.py` exact help/flags and `tests/test_mcp.py` emitted parameter assertions; `tests/test_phase60_characterization.py` retains tool count and updates this command's fields only. `scripts/sync_docs.py` is check-only. Edit existing reference rows and serialized coverage receipt/hash rows in `docs/reports/phase-64-66-documentation-coverage.md` directly using final exact doc bytes; then run `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check`. Never claim this command generates or repairs documentation. `tests/fixtures/phase70/cli-outcomes.json` receives this command's populated/empty/denied/failure/side-effects domain assertions. Existing shared renderer/delivery consumes metadata; preserve full result, visible partial/no-work and terminal escaping.

Future PR scope: first command repair files/tests and exactly necessary shared catalog/docs delta; optional ordinary and agent-side features remain separately reviewable later commits/PR scopes when authorized. Shared provider prerequisite lands before any consumer feature; no separate command identity or duplicate transport implementation.

### Complete installed-engine acceptance

Append to tests/test_yaml.py. Genuine engine resolved through existing resolver; no doubles. These future tests were not executed during planning. Missing executable/image is failed prerequisite, never successful skip. Run with same approved runtime environment as granted transport node.


~~~python
def test_real_builtin_openapi_spectral(tmp_path):
    from pathlib import Path
    from rush.runtime.binaries import resolve_binary
    from rush.tools.yaml import YamlTool
    assert resolve_binary("spectral"), "approved Spectral must be preinstalled"
    (tmp_path / "rush.toml").write_text("")
    source = tmp_path / "api.yaml"
    source.write_text("openapi: 3.0.0\npaths: {}\n")
    result = YamlTool().run(source, schema_kind="openapi")
    assert result["status"] == "warn"
    assert result["metadata"]["syntax_status"] == "ok"
    assert result["metadata"]["schema_status"] == "warn"
    assert result["metadata"]["schema_assessed_paths"] == ["api.yaml"]
    assert [f["rule"] for f in result["findings"]] == ["rush-openapi-info"]
    assert Path(result["findings"][0]["path"]).resolve() == source.resolve()
~~~

### Literal conservative configuration example

Append this exact table once to examples/rush.toml and mirror it in docs/CONFIGURATION.md and docs/reference/configuration-reference.md. No runtime path, image, effectful operation, or grant is persisted by the example. Other new operation fields stay explicit invocation examples in command references.

~~~toml
[tools.yaml]
schema_kind = "generic"
~~~

## P4 — Regression, failure recovery and completion gate

**Required behavior.** Close every ledger row and preserve Phase70 contracts. Test source/installed engine/runtime boundaries separately. Freeze changed bytes before verification; read-only reviewer checks exact hash. Any edit invalidates previous verdict.

**Deliverables.** Only literal files named in P1–P3/shared delta; command tests create fixtures in tmp_path, no permanent unrelated fixture corpus. Runtime prerequisites are already-installed approved executables/images; missing prerequisite blocks that acceptance lane and must be named, never silently skipped as passing.

**Constraints.** No install/network/build during planning. Future tests clear inherited PYTHONPATH, use project Python3.12. No duplicate runs beyond two unchanged-byte attempts, global broad suite, new harness, source rewrite, production DB/service, Git hooks, commit/push/release without explicit authorization. Cleanup failure exposes owned residue and exact restore/delete ownership; never claim clean.

**Checks to run before reporting.** From future implementation worktree based on frozen source:
~~~sh
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_yaml.py tests/test_yaml_transport.py tests/test_content_infra_tools.py tests/test_staged_scan_bytes.py tests/test_phase57_invocation_context.py tests/test_phase54_result_schema.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_module_boundaries.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
~~~
Expected Python3.12.x; exact changed-behavior assertions pass; Ruff exit0. Existing correct malformed-report/permission/root cases are preservation GREEN, not manufactured RED. Refactor only after behavior passes, then run affected checks once on new frozen bytes.

**Completion.** First repair packet is development-ready only after frozen plan review resolves all code/test/interface inconsistencies. Entire optional capability completion additionally requires real engine/OCI or SQLite proof, exact CLI+stdio parity, strict-schema adversarial input rejection, denied zero effects, source-byte/readback verification, approved scope and completed ledger. This authored plan is not an implementation PASS, installation verification, batch ratification or future runtime execution claim. Planning observed reproductions are listed separately above; every proposed GREEN check remains unexecuted.
