# Q14 — templates: truthful djLint failures and isolated render evidence

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

A silent djLint failure must return error, never clean. Keep source lint distinct from optional actual rendering and bounded adversarial render trials. Scope: `rush templates`/`rush_templates`, djLint adapter/profile, explicit renderer fixture and generated boundary cases. Non-goals: browser execution, general XSS certification, accessibility claims, source rewrite or project-code execution without build grant.

| ID/category | Evidence/current behavior | Concrete change | Task/test acceptance |
|---|---|---|---|
| T1 defect | Audit5127–5200; TextLintEngine42–61 ignores return code | djLint-specific parser, lint mode, exit/report consistency | P1 silent2 error, location/rule exact |
| T2 ordinary proposal | audit5202–5291 | explicit profile, actual contained fixture renderer in P0 | P2 rendered receipt; denied grant zero import |
| T3 agent-side proposal | audit5293–5418 | isolated one-input boundary variants, HTML/selector predicates, deterministic smallest failing input | P2 real unsafe/escaped renderer outcome |
| T4 integration/baseline | Phase70 T8–T16/T6/T27 | root/grant/coverage/schema/human receipt; baseline interface consumption | P3/P4 |

## Current source and reproduced evidence

`src/rush/tools/templates.py:6–13` SHA256 `0bc62e244e1d9946275964d0c869a066ed1c674443325d5483392b73c15c4010`; `src/rush/engines/djlint.py:6–10` SHA256 `a35d5c9db49ec23b5145cf2f310f7c3f2abb7b510e0991f83e03c1ce76b39b37`; defining normalizer `src/rush/engines/text_lint.py:42–61`. Existing command_prefix --check is formatter check, not requested lint-rule analysis.

Observed Python3.12.12: actual `DjlintEngine().normalize({"exit_code":2,"stdout":"","stderr":""},root,"templates")` returned status ok when version probe patched only. That is executed current defect, not OCI evidence. Audit's renderer subprocess probe used substituted launcher; it never established containment. All future checks here proposed.

## Input, output and limits

`path:Path` required; `template_dialect:Literal["html","jinja","django"]="html"`; `render_fixture:str|None=None`; `challenge_render:StrictBool=False`; `escape_policy:Literal["html"]="html"`; `runtime_path:str|None=None`; `image_ref:str|None=None`; strict allow_build/allow_slow false. CLI literal `--template-dialect --render-fixture --challenge-render --escape-policy --runtime-path --image-ref`, existing grant/project/view flags.

Lint profile html/jinja/django is explicit; default html. Collected .html/.jinja/.j2 files only, shared global ignores retained, strict walk and lexical PhysicalRoot containment. Missing target error, empty skipped no_template_targets, missing djlint skipped. `metadata.rendered=false` on lint-only; selected_paths versus assessed_paths distinguished. `--lint --quiet --linter-output-format RUSH|{filename}|{line}|{code}|{message}` plus explicit profile. Exit0 iff no findings; exit1 iff findings; other exits nonzero_exit error; contradictory output report_exit_mismatch error. Unknown nonempty report text is malformed_output, not ignored success. Findings preserve file, positive line/column, rule, message; pipe in message allowed by split(maxsplit=4). Source filenames with pipe/newline cannot safely use delimiter transport: reject DJLINT_PATH_UNREPRESENTABLE before spawn, name limitation explicitly.

Fixture exact keys `module,callable,template,values,variables,required_selectors`; module dotted Python identifiers, callable identifier, template root-relative selected source, values JSON object; variables object maps names to {type:"string",optional:bool}; required_selectors list1–100 valid selector strings. Fixture ≤64KiB; values finite JSON only; at most2 declared variables for ≤12 challenge cases. Require matching values type except absent optional; reject unknown extra keys, callable/module wrong type, symlink/external template, invalid selector before any engine/version/renderer invocation. Selectors only tag, #id, .class, tag#id, tag.class; no full CSS promise.

Rendering requires build grant, challenge additionally slow. Denied render yields skipped metadata.render.status=denied, rendered=false, zero lint/version/provider calls (preflight whole requested operation). Challenge without fixture errors. P0 read-only source/no-network; fixed image entrypoint /usr/local/bin/python with declared renderer dependencies; no install. Renderer signature `render(template:str,values:dict)->str`. Module imported only inside isolated container. HTML is parsed, never browser-executed.

Metadata render/render_challenge: rendered bool, attempted integer, status passed|failed|skipped|denied|error, failing_input null|{variable,value}, observations[{variable,value,render_error,unsafe_marker,missing_selectors,html_digest}]. Do not store returned full HTML. Marker checks test explicit injected script/event values only; they are not universal XSS detection. Failed render/missing selector/unsafe marker makes child failed and aggregate fail; unavailable runtime skipped/partial, never rendered pass.

## P1 — djLint-specific reliable normalization

**Required behavior.** T1 on current normalizer.
**Deliverables.** Replace `src/rush/engines/djlint.py::DjlintEngine`; add `tests/test_templates.py`. Preserve other TextLintEngine subclasses.

~~~python
from pathlib import Path
from unittest.mock import patch
from rush.engines.djlint import DjlintEngine
from rush.tools.templates import TemplatesTool


def test_silent_nonzero_is_error(tmp_path):
    with patch.object(DjlintEngine, "version", return_value="fixture"):
        result = DjlintEngine().normalize(
            {"exit_code": 2, "stdout": "", "stderr": ""}, tmp_path, "templates")
    assert result["status"] == "error"  # current RED: ok
    assert result["metadata"]["terminal_reason"] == "nonzero_exit"


def test_template_defect_has_path(tmp_path):
    source = tmp_path / "page.html"; source.write_text("<img>\n")
    with patch.object(DjlintEngine, "version", return_value="fixture"):
        result = DjlintEngine().normalize(
            {"exit_code": 1,
             "stdout": "RUSH|page.html|1:0|H006|img missing height|width\n",
             "stderr": ""}, tmp_path, "templates")
    assert result["status"] == "warn"
    assert result["findings"] == [{
        "path": str(source), "line": 1, "column": 1, "rule": "H006",
        "severity": "warn", "message": "img missing height|width"}]
~~~

Complete replacement parser class (proposed):

~~~python
import re
from pathlib import Path
from .text_lint import TextLintEngine
from ..io.physical_paths import PhysicalRoot, ContainmentError
from ..tools.base import ToolResult
from ..tools.common import error_result

class DjlintEngine(TextLintEngine):
    name = "djlint"
    binary = "djlint"
    file_extensions = ("html", "jinja", "j2")
    command_prefix = (
        "--lint", "--quiet", "--linter-output-format",
        "RUSH|{filename}|{line}|{code}|{message}",
    )

    def __init__(self, *, profile="html"):
        if profile not in {"html", "jinja", "django"}:
            raise ValueError("unsupported template profile")
        self.command_prefix = (*type(self).command_prefix,
                               *(() if profile == "html" else ("--profile", profile)))

    def normalize(self, raw, path: Path, tool_name: str):
        root = path if path.is_dir() else path.parent
        code = raw.get("exit_code")
        if type(code) is not int or code not in (0, 1):
            return error_result(tool_name, self.name, "djlint invocation failed",
                                terminal_reason="nonzero_exit")
        findings = []
        for line in raw.get("stdout", "").splitlines():
            if not line.strip():
                continue
            fields = line.split("|", 4)
            if len(fields) != 5 or fields[0] != "RUSH":
                return error_result(tool_name, self.name, "malformed djlint finding",
                                    terminal_reason="malformed_output")
            _, filename, location, rule, message = fields
            match = re.fullmatch(r"([1-9]\d*)(?::(\d+))?", location.strip())
            target = Path(filename)
            try:
                relative = target.relative_to(root) if target.is_absolute() else target
                checked = PhysicalRoot(root).open_contained(relative)
            except (ContainmentError, ValueError, OSError):
                return error_result(tool_name, self.name, "djlint path outside target",
                                    terminal_reason="malformed_output")
            if not match or not rule or not message:
                return error_result(tool_name, self.name, "invalid djlint location",
                                    terminal_reason="malformed_output")
            finding = {"path": str(checked), "line": int(match[1]),
                       "rule": rule, "severity": "warn", "message": message}
            if match[2] is not None:
                finding["column"] = int(match[2]) + 1
            findings.append(finding)
        if (code == 1) != bool(findings) or (not findings and raw.get("stderr", "").strip()):
            return error_result(tool_name, self.name, "djlint exit/report mismatch",
                                terminal_reason="report_exit_mismatch")
        return ToolResult(tool=tool_name, engine=self.name,
                          engine_version=self.version(),
                          status="warn" if findings else "ok",
                          duration_ms=raw.get("duration_ms", 0),
                          summary=f"djlint: {len(findings)} template findings",
                          findings=findings, raw=None)
~~~

Tool validates command path delimiter before engine. Override run with exact selected file argv plus --profile profile (html profile uses djlint documented default, jinja/django explicit); metadata rendered false. Preserve timeout/ownership. Real installed djLint contract acceptance must verify no unstructured banner under --quiet; if version emits a known banner, parser consumes only exact documented banner lines and tests them; never generic ignored output.

**Constraints.** No shared text-parser behavior change, format/reformat flags or source writes.
**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_templates.py -q`.
**Completion.** Silent crash error, structured rule/location exact, ordinary lint rendered=false, actual lint/profile output verified.

## P2 — Real render and adversarial variants

**Required behavior.** T2 ordinary render checks one values object; T3 derives boundary cases from declared variables without mutating source.
**Deliverables.** `src/rush/tools/templates.py::run_template_render`, `TemplatesTool.__call__/run`; tests `tests/test_templates.py`; P0 shared provider.

Complete algorithm: validate fixture/grants first. Trial0 original values. For each variable in sorted name order add empty string, script marker `<script data-rush-probe>1</script>`, quote/event marker `" onmouseover="rushProbe`, Unicode `é漢🙂`; if optional, missing-variable case. Each varies exactly one variable. Max12 total otherwise error FIXTURE_CASE_LIMIT. For each, fresh TemporaryDirectory and P0 fixed /usr/local/bin/python, timeout30, read-only /work, cwd/work. Copy fixture request only to /out/request.json. Program below returns explicit finite receipt:

~~~python
RENDER_PROGRAM = r'''import importlib, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

job = json.loads(Path("/out/request.json").read_text())
sys.path.insert(0, "/work")
renderer = getattr(importlib.import_module(job["module"]), job["callable"])
html = renderer(job["template"], job["values"])
if not isinstance(html, str) or len(html.encode("utf-8")) > 1_048_576:
    raise ValueError("renderer must return bounded HTML string")

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.unsafe = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.nodes.append((tag, attrs))
        self.unsafe |= "data-rush-probe" in attrs or any(
            name.lower().startswith("on") and "rushProbe" in value
            for name, value in attrs.items() if isinstance(value, str))
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

page = Page(); page.feed(html)
def matches(selector):
    m = re.fullmatch(r"([a-zA-Z][\w-]*)?(?:([.#])([\w-]+))?", selector)
    if not m or not any(m.groups()):
        raise ValueError("unsupported selector")
    wanted_tag, op, name = m.groups()
    return any(
        (wanted_tag is None or tag == wanted_tag.lower()) and
        (op is None or (attrs.get("id") == name if op == "#"
                        else name in (attrs.get("class") or "").split()))
        for tag, attrs in page.nodes)

import hashlib
Path("/out/result.json").write_text(json.dumps({
    "unsafe_marker": bool(page.unsafe),
    "missing_selectors": [s for s in job["required_selectors"] if not matches(s)],
    "html_digest": hashlib.sha256(html.encode("utf-8")).hexdigest()}))
'''
~~~

Controller checks returned process code and no-follow regular result.json ≤64KiB, exact keys/types/digest; any missing/malformed output -> child error, never a passing render. Nonzero renderer exit produces render_error observation, no HTML digest. Successful rows carry variable/value, render_error false and validated receipt. `rendered=true` means actual renderer ran; `attempted` counts invoked renderer processes only. Aggregate failed if any render_error/unsafe/missing selector. Select smallest failing input by UTF8 length of canonical JSON `{"variable":name,"value":value}`, then variable name, then generated index; original failing happy path represented variable=None,value=None. This replaces audit's first-failing claim with an explicit reproducible minimum over generated cases, not global input minimization.

Wrapper `run_template_render(root,render_fixture,*,runtime_path,image_ref,permissions,challenge=False)` returns that receipt; export `run_isolated_argv` import at defining module so denial spies are valid. Full command checks no lint/version spawn before required grant. Recheck source SHA after trials, then cleanup; unexpected source drift error. No output HTML/log body is retained; bounded redacted error category.

~~~python
def test_render_challenge_finds_unescaped_delimiter(tmp_path):
    import json, os
    from rush.permissions import ExecutionPermissions
    (tmp_path / "rush.toml").write_text("")
    (tmp_path / "page.html").write_text('<p id="name">{name}</p>')
    (tmp_path / "fixture_renderer.py").write_text(
        "from pathlib import Path\n"
        "def render(template, values):\n"
        "    return Path(template).read_text().format(**values)\n")
    (tmp_path / "safe_renderer.py").write_text(
        "from pathlib import Path\nimport html\n"
        "def render(template, values):\n"
        "    return Path(template).read_text().format("
        "**{k:html.escape(v) for k,v in values.items()})\n")
    fixture = {"module": "fixture_renderer", "callable": "render",
               "template": "page.html", "values": {"name": "sample"},
               "variables": {"name": {"type": "string", "optional": False}},
               "required_selectors": ["p#name"]}
    (tmp_path / "fixture.json").write_text(json.dumps(fixture))
    before = (tmp_path / "page.html").read_bytes()
    kwargs = dict(render_fixture="fixture.json", challenge_render=True,
                  runtime_path=Path(os.environ["RUSH_TEST_OCI_RUNTIME"]),
                  image_ref=os.environ["RUSH_TEST_RENDER_IMAGE"],
                  permissions=ExecutionPermissions(build=True, slow=True))
    bad = TemplatesTool().run(tmp_path / "page.html", **kwargs)
    trial = bad["metadata"]["render_challenge"]
    assert trial["attempted"] == 5
    assert trial["status"] == "failed"
    assert trial["failing_input"] == {
        "variable": "name", "value": "<script data-rush-probe>1</script>"}
    fixture["module"] = "safe_renderer"
    (tmp_path / "fixture.json").write_text(json.dumps(fixture))
    good = TemplatesTool().run(tmp_path / "page.html", **kwargs)
    assert good["metadata"]["render_challenge"]["status"] == "passed"
    assert good["metadata"]["render_challenge"]["failing_input"] is None
    assert (tmp_path / "page.html").read_bytes() == before
~~~

Actual pinned image with Python3.12 required; this test invokes genuine P0 provider. Additional exact tests: missing build/slow denial and zero provider/version calls; malformed fixture selectors/vars before spawn; missing optional value renderer failure; missing selector fails; nullable class attr does not crash parser; malformed receipt error; symlink output rejected; timeout/cancel container reaped; unavailable runtime skipped rendered=false. Actual installed djLint must also lint invalid template with expected source rule. A fake engine alone cannot pass this runtime acceptance.

**Constraints.** No browser/DOM-execution/accessibility or universal XSS claim, no project code imported on host.
**Checks.** P1 module plus P0 real runtime checks.
**Completion.** Real unsafe renderer fails, escaped renderer passes finite predicate, failure input deterministic, source unchanged, deny/missing/failed render never represented as passed.

### Complete isolated render controller

Add this full function to src/rush/tools/templates.py. Store the preceding complete isolated render program as RENDER_PROGRAM (verbatim module string). Import run_isolated_argv at module scope for the already specified denial spy. Every helper below is defined locally or names an existing source API.

~~~python
from rush.runtime.isolated_process import IsolationUnavailable, run_isolated_argv

def run_template_render(root, render_fixture, *, runtime_path, image_ref,
                        permissions, challenge=False, selected_paths=None):
    import hashlib, json, os, re, tempfile
    from pathlib import Path
    from rush.permissions import ExecutionPermissions, check_permissions
    from rush.workflows.projects import open_contained_file
    allowed, _ = check_permissions(
        ExecutionPermissions(build=True, slow=challenge), permissions)
    if not allowed:
        return {"rendered": False, "attempted": 0, "status": "denied",
                "reason": "missing_grants", "failing_input": None, "observations": []}
    if not runtime_path or not image_ref:
        raise IsolationUnavailable("approved runtime and image required")
    def read(relative, limit):
        with os.fdopen(open_contained_file(root, relative), "rb") as stream:
            value = stream.read(limit + 1)
        if len(value) > limit:
            raise ValueError("render_input_too_large")
        return value
    raw = read(render_fixture, 65_536)
    fixture = json.loads(raw)
    fields = {"module", "callable", "template", "values", "variables", "required_selectors"}
    if not isinstance(fixture, dict) or set(fixture) != fields:
        raise ValueError("render_fixture_invalid")
    for key, pattern in (("module", r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"),
                         ("callable", r"[A-Za-z_]\w*")):
        if type(fixture[key]) is not str or not re.fullmatch(pattern, fixture[key]):
            raise ValueError("render_fixture_invalid")
    if type(fixture["template"]) is not str:
        raise ValueError("render_fixture_invalid")
    if selected_paths is not None and fixture["template"] not in selected_paths:
        raise ValueError("render_template_not_selected")
    template = read(fixture["template"], 1_048_576)
    values, variables = fixture["values"], fixture["variables"]
    selectors = fixture["required_selectors"]
    if (not isinstance(values, dict) or not isinstance(variables, dict) or
        len(variables) > 2 or set(values) - set(variables) or
        not isinstance(selectors, list) or not 1 <= len(selectors) <= 100):
        raise ValueError("render_fixture_invalid")
    for selector in selectors:
        if (type(selector) is not str or not selector or
            not re.fullmatch(r"(?:[a-zA-Z][\w-]*)?(?:[.#][\w-]+)?", selector)):
            raise ValueError("render_selector_invalid")
    for name, spec in variables.items():
        if (type(name) is not str or not re.fullmatch(r"[A-Za-z_]\w*", name) or
            not isinstance(spec, dict) or set(spec) != {"type", "optional"} or
            spec["type"] != "string" or type(spec["optional"]) is not bool or
            (name not in values and not spec["optional"]) or
            (name in values and type(values[name]) is not str)):
            raise ValueError("render_variable_invalid")
    cases = [(None, None, dict(values))]
    if challenge:
        for name in sorted(variables):
            for value in ("", "<script data-rush-probe>1</script>",
                          '" onmouseover="rushProbe', "é漢🙂"):
                cases.append((name, value, {**values, name: value}))
            if variables[name]["optional"]:
                absent = dict(values); absent.pop(name, None)
                cases.append((name, None, absent))
    if len(cases) > 12:
        raise ValueError("FIXTURE_CASE_LIMIT")
    # Snapshot all actual source bytes, including renderer dependencies.
    source = {}
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root).as_posix()
        if item.is_symlink():
            raise ValueError("render_source_symlink")
        if item.is_file():
            source[relative] = hashlib.sha256(read(relative, 16_777_216)).hexdigest()
            if len(source) > 100_000:
                raise ValueError("render_source_limit")
    observations = []
    try:
        for name, value, selected_values in cases:
            with tempfile.TemporaryDirectory(prefix="rush-render-") as directory:
                scratch = Path(directory); scratch.chmod(0o700)
                job = {**fixture, "values": selected_values}
                (scratch / "request.json").write_text(json.dumps(job), encoding="utf-8")
                process = run_isolated_argv(root, scratch, runtime_path=Path(runtime_path),
                    image_ref=image_ref, entrypoint="/usr/local/bin/python",
                    argv=["-c", RENDER_PROGRAM], timeout_s=30)
                if process.returncode != 0:
                    observations.append({"variable": name, "value": value, "render_error": True,
                        "unsafe_marker": False, "missing_selectors": [], "html_digest": None})
                    continue
                with os.fdopen(open_contained_file(scratch, "result.json"), "rb") as stream:
                    raw_receipt = stream.read(65_537)
                if len(raw_receipt) > 65_536:
                    raise ValueError("render_receipt_too_large")
                receipt = json.loads(raw_receipt)
                if (not isinstance(receipt, dict) or set(receipt) !=
                    {"unsafe_marker", "missing_selectors", "html_digest"} or
                    type(receipt["unsafe_marker"]) is not bool or
                    not isinstance(receipt["missing_selectors"], list) or
                    any(type(s) is not str or s not in selectors
                        for s in receipt["missing_selectors"]) or
                    type(receipt["html_digest"]) is not str or
                    not re.fullmatch(r"[0-9a-f]{64}", receipt["html_digest"])):
                    raise ValueError("render_receipt_invalid")
                observations.append({"variable": name, "value": value,
                                     "render_error": False, **receipt})
    finally:
        current = {}
        for item in sorted(root.rglob("*")):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                raise ValueError("render_source_changed")
            if item.is_file():
                current[relative] = hashlib.sha256(read(relative, 16_777_216)).hexdigest()
        if current != source or read(render_fixture, 65_536) != raw:
            raise ValueError("render_source_changed")
    failed = [(index, row) for index, row in enumerate(observations)
              if row["render_error"] or row["unsafe_marker"] or row["missing_selectors"]]
    def key(pair):
        index, row = pair
        encoded = json.dumps({"variable": row["variable"], "value": row["value"]},
                             sort_keys=True, ensure_ascii=False).encode("utf-8")
        return len(encoded), row["variable"] or "", index
    smallest = min(failed, key=key)[1] if failed else None
    return {"rendered": bool(observations), "attempted": len(observations),
            "status": "failed" if failed else "passed",
            "failing_input": None if smallest is None else
                {"variable": smallest["variable"], "value": smallest["value"]},
            "observations": observations}
~~~

Exact run insertion before normal lint when fixture is present: check helper's required permissions first and return skipped with metadata.render denied/rendered=false on refusal. Validate fixture.template belongs to actual selected source vector before calling helper (no renderer may widen target selection). After normal lint and helper result, insert:

~~~python
receipt = run_template_render(root, render_fixture, runtime_path=runtime_path,
    image_ref=image_ref, permissions=permissions, challenge=challenge_render)
result.setdefault("metadata", {})["render_challenge" if challenge_render else "render"] = receipt
result["metadata"]["rendered"] = receipt["rendered"]
if receipt["status"] == "failed" and result["status"] != "error":
    result["status"] = "fail"
~~~

Validate fixture before normal lint by executing its validation through the helper before scanner dispatch; store receipt once, and the insertion above consumes that stored receipt instead of rerunning it. Tool maps invalid fixture/receipt/containment to canonical error, and P0 unavailability to skipped rendered=false/incomplete aggregate. Rendered means renderer process ran; nonzero processes never count as a passing render. Whole-source drift recheck runs in finally around the case loop, including timeout and cancellation. TemporaryDirectory and P0 cleanup remain unconditional.

### Complete TemplatesTool.run after P2

Exact method replacement consumes the already defined controller once, before lint, with selected source identities. Retain metadata.engines from run_engine.

~~~python
def run(self, path, *, config=None, context=None, template_dialect="html",
        render_fixture=None, challenge_render=False, escape_policy="html",
        runtime_path=None, image_ref=None, permissions=None):
    from pathlib import Path
    from rush.engines.djlint import DjlintEngine
    from rush.invocation.targets import select_root, assert_contained
    from rush.io.physical_paths import PhysicalRoot, ContainmentError
    from rush.runtime.isolated_process import IsolationUnavailable, IsolationCleanupError
    from rush.tools.common import error_result, skipped_result, run_engine
    from rush.tools.routing import collect_files
    try:
        if context is None:
            selected = select_root(str(path), anchor=Path.cwd())
            assert_contained(selected)
            root = selected.root; path = root / selected.relative
        else:
            root = context.workspace_root
        if not path.exists():
            return error_result(self.name, None, "target does not exist",
                                terminal_reason="TARGET_NOT_FOUND")
        if template_dialect not in {"html", "jinja", "django"} or escape_policy != "html":
            raise ValueError("template_options_invalid")
        if challenge_render and render_fixture is None:
            raise ValueError("challenge_requires_fixture")
        physical = PhysicalRoot(root)
        files = [physical.open_contained(p.relative_to(root))
                 for p in collect_files(path, {"html", "jinja", "j2"}, strict=True)]
        names = [p.relative_to(root).as_posix() for p in files]
        if any(any(c in name for c in "|\r\n") for name in names):
            raise ValueError("DJLINT_PATH_UNREPRESENTABLE")
        if not files:
            return skipped_result(self.name, "djlint", "no_template_targets",
                                  metadata={"rendered": False, "selected_paths": []})
        receipt = None
        if render_fixture is not None:
            receipt = run_template_render(root, render_fixture, runtime_path=runtime_path,
                image_ref=image_ref, permissions=permissions, challenge=challenge_render,
                selected_paths=names)
            if receipt["status"] == "denied":
                return skipped_result(self.name, None, "missing_grants",
                    metadata={"reason": "missing_grants", "rendered": False,
                              "render": receipt, "selected_paths": names, "assessed_paths": []})
        result = run_engine(DjlintEngine(profile=template_dialect), root,
            [str(p) for p in files], tool_name=self.name,
            consumed_paths=[str(p) for p in files], project_root=root)
        result.setdefault("metadata", {}).update(
            rendered=False, selected_paths=names,
            assessed_paths=names if result["status"] in {"ok", "warn", "fail"} else [])
        if receipt is not None:
            result["metadata"]["render_challenge" if challenge_render else "render"] = receipt
            result["metadata"]["rendered"] = receipt["rendered"]
            if receipt["status"] == "failed" and result["status"] != "error":
                result["status"] = "fail"
        return result
    except IsolationUnavailable:
        return skipped_result(self.name, None, "isolation_unavailable",
            metadata={"reason": "isolation_unavailable", "rendered": False,
                      "render": {"status": "skipped", "rendered": False, "attempted": 0}})
    except IsolationCleanupError:
        return error_result(self.name, None, "Render cleanup failed",
                            terminal_reason="isolation_cleanup_failed")
    except (ValueError, OSError, ContainmentError):
        return error_result(self.name, None, "Template input or render receipt invalid",
                            terminal_reason="TEMPLATE_INPUT_INVALID")
~~~

## P3 — Real CLI and initialized stdio MCP parity

**Required behavior.** Explicit options reach shared tool implementation on both transports. Matching domain projection below is equal; target identities and grants cannot be inferred from tools/list alone. Test-owned engine below proves forwarding/parser behavior only; P2 real-engine/OCI tests separately prove runtime behavior.

**Deliverables.** Add following complete module to `tests/test_templates_transport.py`; Batch integration owner adds command's explicit options to `_TOOL_CLI_OPTIONS` and exact `ToolOptionSpec` tuple to existing `TOOL_SPECS["templates"]`. Preserve existing `make_tool_wrapper`/executor; context is internal. No generic introspection factory, MCP-only implementation or new CLI route.

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

COMMAND = "templates"
BINARY = "djlint"
SOURCE = "page.html"
BODY = "<p>hello</p>\n"
OPTIONS = {"template_dialect":"jinja"}
CLI_OPTIONS = ["--template-dialect","jinja"]
EXPECTED = {"status":"ok","rendered":False,"assessed_paths":["page.html"]}
PROJECTION = ["rendered","assessed_paths"]


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
        "print('')\n",
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
    assert all('--lint' in json.loads(line) and '--check' not in json.loads(line) for line in marker.read_text().splitlines())


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
`rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_templates_transport.py tests/test_templates.py tests/test_cli_registry.py tests/test_mcp.py -q`

**Completion.** Real process CLI and initialized stdio call agree on stated domain values, missing/denied input produces zero analysis/state effects, parameter schema is exact, source bytes unchanged, and separate runtime checks pass.


Append this complete denied-request case to the same transport module. Permission denial is preflight for the whole explicitly requested operation, returning skipped with metadata.reason="missing_grants"; no engine/version/runtime call occurs.

~~~python
def test_cli_stdio_denied_request_zero_effects(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(BODY)
    for relative, text in {"fixture.json": "{\"module\":\"fixture_renderer\",\"callable\":\"render\",\"template\":\"page.html\",\"values\":{\"name\":\"ok\"},\"variables\":{\"name\":{\"type\":\"string\",\"optional\":false}},\"required_selectors\":[\"p\"]}", "fixture_renderer.py": "def render(template, values):\n    return '<p>ok</p>'\n"}.items():
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
    options = {"render_fixture": "fixture.json"}
    options.update(runtime_path=runtime, image_ref=image)
    flags = ["--render-fixture", "fixture.json"] + ["--runtime-path", runtime, "--image-ref", image]
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
    assert local["metadata"]["render"]["status"] == remote["metadata"]["render"]["status"] == "denied"
    assert not marker.exists()
    assert {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()} == before
    assert not (root / ".rush").exists()
~~~


### Exact engine scope and version provenance

The existing shared `run_engine` is defined in `src/rush/runtime/subprocesses.py:1258–1335` and accepts `consumed_paths,project_root`. Every host static dispatch in this command passes `consumed_paths=[str(p) for p in files], project_root=root` together with the exact same selected argv. This binds recorded main spawns to actual explicit source inputs; missing/denied/error scopes remain whatever the real run records. Never call a scope probe that is absent on the adapter or infer dependency closure. Caller-owned config identity updates the corresponding engine entry's `config={path,sha256,reason:None}` from the actual fixed/explicit config; dependency instrumentation unavailable remains disclosed separately.


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

def granted_stdio(foreign, env, command, arguments, expected_schema, *, startup_prefix=""):
    import json, queue, subprocess, sys, tempfile, threading
    def semantic(value):
        if isinstance(value, dict):
            return {k: semantic(v) for k, v in value.items()
                    if k not in {"title", "description"}}
        if isinstance(value, list):
            return [semantic(v) for v in value]
        return value
    code = startup_prefix + ("import sys; print('rush-test-diagnostic', file=sys.stderr); "
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
GRANTED_SCHEMA = exact_schema(json.loads(r'''{"template_dialect":{"enum":["html","jinja","django"],"type":"string","default":"html"},"render_fixture":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"challenge_render":{"type":"boolean","default":false},"escape_policy":{"const":"html","type":"string","default":"html"},"runtime_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"image_ref":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"allow_build":{"type":"boolean","default":false},"allow_slow":{"type":"boolean","default":false}}'''))

def test_granted_render_cli_stdio_foreign_cwd(tmp_path):
    import json, os
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "page.html").write_text('<!DOCTYPE html>\n<html lang="en">\n    <head>\n        <title>Test</title>\n    </head>\n    <body>\n        <p id="name">{name}</p>\n    </body>\n</html>\n')
    (root / "renderer.py").write_text(
        "from pathlib import Path\nimport html\n"
        "def render(template, values):\n"
        "    return Path(template).read_text().format(**{k:html.escape(v) for k,v in values.items()})\n")
    fixture = {"module":"renderer","callable":"render","template":"page.html",
               "values":{"name":"sample"},"variables":{"name":{"type":"string","optional":False}},
               "required_selectors":["p#name"]}
    (root / "fixture.json").write_text(json.dumps(fixture))
    runtime = os.environ["RUSH_TEST_OCI_RUNTIME"]
    image = os.environ["RUSH_TEST_RENDER_IMAGE"]
    env, foreign, project = granted_environment(tmp_path, root)
    before = entire_tree(root)
    left = granted_cli(foreign, env, "templates", root / "page.html",
        ["--render-fixture", "fixture.json", "--challenge-render", "--runtime-path", runtime,
         "--image-ref", image, "--allow-build", "--allow-slow"], 0)
    right = granted_stdio(foreign, env, "templates",
        {"project":project,"path":"page.html","render_fixture":"fixture.json",
         "challenge_render":True,"runtime_path":runtime,"image_ref":image,
         "allow_build":True,"allow_slow":True,"no_cache":True}, GRANTED_SCHEMA)
    assert left["status"] == right["status"] == "ok"
    assert left["metadata"]["render_challenge"] == right["metadata"]["render_challenge"]
    trial = right["metadata"]["render_challenge"]
    assert trial["status"] == "passed" and trial["rendered"] is True
    assert trial["attempted"] == 5 and trial["failing_input"] is None
    assert all(row["render_error"] is False and row["unsafe_marker"] is False
               and row["missing_selectors"] == [] for row in trial["observations"])
    assert entire_tree(root) == before

~~~

### Missing runtime is unavailable before any render effect

The controller guard follows grant validation and precedes fixture reads, source snapshots, engine/version probes and temporary-directory creation. Missing either explicit runtime input raises `IsolationUnavailable`; the complete tool dispatcher above returns `skipped`, `metadata.reason="isolation_unavailable"`, and `rendered=false`. This preserves denied-grant precedence. The following complete future tests require the proposed controller/dispatcher/P0 exception definitions, but require no installed engine or runtime. They have not passed against current production code.

Add to `tests/test_templates.py`:

~~~python
def test_render_missing_runtime_precedes_all_effects(tmp_path, monkeypatch):
    import tempfile
    import pytest
    import rush.tools.templates as module
    import rush.tools.common as common
    import rush.runtime.binaries as binaries
    import rush.workflows.projects as projects
    from rush.permissions import ExecutionPermissions
    from rush.runtime.isolated_process import IsolationUnavailable
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "page.html").write_text("<p>sample</p>")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("missing runtime reached an effect boundary")
    monkeypatch.setattr(module, "run_isolated_argv", forbidden)
    monkeypatch.setattr(common, "run_engine", forbidden)
    monkeypatch.setattr(binaries, "resolve_binary", forbidden)
    monkeypatch.setattr(projects, "open_contained_file", forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    permissions = ExecutionPermissions(build=True, slow=True)
    for runtime_path, image_ref in (
        (None, None), (None, "fixture@sha256:" + "0" * 64), ("/missing/runtime", None)
    ):
        with pytest.raises(IsolationUnavailable, match="^approved runtime and image required$"):
            module.run_template_render(root, "missing-fixture.json",
                runtime_path=runtime_path, image_ref=image_ref,
                permissions=permissions, challenge=True)
        result = module.TemplatesTool().run(root / "page.html",
            render_fixture="missing-fixture.json", challenge_render=True,
            runtime_path=runtime_path, image_ref=image_ref, permissions=permissions)
        assert result["tool"] == "templates"
        assert result["status"] == "skipped" and result["findings"] == []
        assert result["metadata"]["reason"] == "isolation_unavailable"
        assert result["metadata"]["rendered"] is False
        assert result["metadata"]["render"] == {
            "status": "skipped", "rendered": False, "attempted": 0}
    assert calls == []
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
~~~

Add to `tests/test_templates_transport.py`, beside the complete `granted_stdio`, `GRANTED_SCHEMA`, and `entire_tree` definitions above. The optional `startup_prefix` argument is test startup only. It replaces effect boundaries with rejecting observers inside the real server process; it does not replace the tool, request validation, MCP SDK or stdio transport. A missing fixture proves runtime availability wins before fixture reads. Any attempted provider/probe/read/temp/engine operation creates a marker and fails the test.

~~~python
def test_missing_runtime_granted_initialized_stdio_has_zero_effects(tmp_path):
    import json, os
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    (root / "page.html").write_text("<p>sample</p>")
    foreign = tmp_path / "foreign"; foreign.mkdir()
    home = tmp_path / "home"; home.mkdir()
    marker = tmp_path / "forbidden-effect"
    env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
           "LOCALAPPDATA": str(home / "local"), "NO_COLOR": "1"}
    env.pop("PYTHONPATH", None)
    setup = (
        "from pathlib import Path\nfrom unittest.mock import patch\n"
        "def forbidden(*args, **kwargs):\n"
        "    Path(" + repr(str(marker)) + ").write_text('effect attempted')\n"
        "    raise AssertionError('missing runtime reached an effect boundary')\n"
        "guards = [patch(target, forbidden).start() for target in (\n"
        "    'rush.tools.templates.run_isolated_argv',\n"
        "    'rush.tools.common.run_engine',\n"
        "    'rush.runtime.binaries.resolve_binary',\n"
        "    'rush.workflows.projects.open_contained_file',\n"
        "    'tempfile.TemporaryDirectory')]\n")
    before = entire_tree(root)
    for options in ({}, {"image_ref": "fixture@sha256:" + "0" * 64},
                    {"runtime_path": "/missing/runtime"}):
        result = granted_stdio(foreign, env, "templates", {
            "path": str(root / "page.html"), "render_fixture": "missing-fixture.json",
            "challenge_render": True, "allow_build": True, "allow_slow": True,
            "no_cache": True, **options}, GRANTED_SCHEMA,
            startup_prefix="exec(" + repr(setup) + "); ")
        assert result["tool"] == "templates"
        assert result["status"] == "skipped" and result["findings"] == []
        assert result["metadata"]["reason"] == "isolation_unavailable"
        assert result["metadata"]["rendered"] is False
        assert result["metadata"]["render"] == {
            "status": "skipped", "rendered": False, "attempted": 0}
        assert not marker.exists()
        assert entire_tree(root) == before
        assert list(foreign.iterdir()) == []
~~~

Future focused check: `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest tests/test_templates.py::test_render_missing_runtime_precedes_all_effects tests/test_templates_transport.py::test_missing_runtime_granted_initialized_stdio_has_zero_effects -q`. The actual CLI/MCP positive runtime lane remains separate and still requires genuine runtime/image inputs.

## Literal transport/configuration edits and future PR scope

Batch integration owner appends only this command's tuple to existing `src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS` (factory already forwards `**tool_options`). Existing permission options are not redeclared:

~~~python
"templates": (
    click.Option(["--template-dialect"], type=click.Choice(["html","jinja","django"]), default="html"),
    click.Option(["--render-fixture"], type=str, default=None),
    click.Option(["--challenge-render"], is_flag=True, default=False),
    click.Option(["--escape-policy"], type=click.Choice(["html"]), default="html"),
    click.Option(["--runtime-path"], type=str, default=None),
    click.Option(["--image-ref"], type=str, default=None),
),
~~~

In `src/rush/catalog.py`, replace this command's `option_specs` with the following complete tuple, retaining canonical name/category/maturity/engine mapping. Each local document parameter intentionally uses default path_kind="none" because tool validates it root-relatively through PhysicalRoot; do not add it to cwd-relative `_CWD_RELATIVE_ARGS`. External runtime is never interpreted as project file. This explicit anchor decision prevents nested cwd rebasing.

~~~python
option_specs=(
    ToolOptionSpec("template_dialect", str, default="html", choices=("html", "jinja", "django",), description="template dialect; see command contract"),
    ToolOptionSpec("render_fixture", str, default=None, description="render fixture; see command contract"),
    ToolOptionSpec("challenge_render", bool, default=False, description="challenge render; see command contract"),
    ToolOptionSpec("escape_policy", str, default="html", choices=("html",), description="escape policy; see command contract"),
    ToolOptionSpec("runtime_path", str, default=None, description="runtime path; see command contract"),
    ToolOptionSpec("image_ref", str, default=None, description="image ref; see command contract"),
)
~~~

Add exact typed callable to `src/rush/tools/templates.py::TemplatesTool` (imports supplied; place method inside class). Its `run` accepts same domain options plus `permissions,context,config`, with all defaults identical; list/tuple preserve_fields normalize once to list. Strict booleans preserve invalid-type rejection.

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
    template_dialect: Literal["html", "jinja", "django"] = "html",
    render_fixture: str | None = None,
    challenge_render: StrictBool = False,
    escape_policy: Literal["html"] = "html",
    runtime_path: str | None = None,
    image_ref: str | None = None,
    allow_build: StrictBool = False,
    allow_slow: StrictBool = False,
    context: InvocationContext | None = None,
) -> ToolResult:
    if any(type(value) is not bool for value in (allow_build, allow_slow, challenge_render,)):
        return error_result("templates", None, "boolean arguments must be booleans",
                            terminal_reason="INVALID_REQUEST")
    return self.run(
        path,
        template_dialect=template_dialect,
        render_fixture=render_fixture,
        challenge_render=challenge_render,
        escape_policy=escape_policy,
        runtime_path=runtime_path,
        image_ref=image_ref,
        permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        context=context,
    )
~~~

Tracked configuration guide is `docs/CONFIGURATION.md` (uppercase Git path), and existing conservative example is `examples/rush.toml`; both are shared integration-owner writes. Existing `ToolOptionSpec` tuple is configuration schema. Preserve existing tables; append only this command's single safe-default table described below. Update command section in `docs/reference/configuration-reference.md` with literal `[tools.templates]` keys/defaults and root-relative semantics, corresponding sections in `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/result-reference.md`. Add one clean, one no-work, one denied, one failed example with actual result/exit. Update `tests/test_cli_registry.py` exact help/flags and `tests/test_mcp.py` emitted parameter assertions; `tests/test_phase60_characterization.py` retains tool count and updates this command's fields only. `scripts/sync_docs.py` is check-only. Edit existing reference rows and serialized coverage receipt/hash rows in `docs/reports/phase-64-66-documentation-coverage.md` directly using final exact doc bytes; then run `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check`. Never claim this command generates or repairs documentation. `tests/fixtures/phase70/cli-outcomes.json` receives this command's populated/empty/denied/failure/side-effects domain assertions. Existing shared renderer/delivery consumes metadata; preserve full result, visible partial/no-work and terminal escaping.

Future PR scope: first command repair files/tests and exactly necessary shared catalog/docs delta; optional ordinary and agent-side features remain separately reviewable later commits/PR scopes when authorized. Shared provider prerequisite lands before any consumer feature; no separate command identity or duplicate transport implementation.

### Complete installed-engine acceptance

Append to tests/test_templates.py. Genuine engine resolved through existing resolver; no doubles. These future tests were not executed during planning. Missing executable/image is failed prerequisite, never successful skip. Run with same approved runtime environment as granted transport node.


~~~python
def test_real_djlint_lint_flags_and_report(tmp_path):
    from pathlib import Path
    from rush.engines.djlint import DjlintEngine
    from rush.runtime.binaries import resolve_binary
    assert resolve_binary("djlint"), "approved djLint must be preinstalled"
    source = tmp_path / "page.html"
    source.write_text("<html>\n<body>\n<p>Hello</p>\n</body>\n</html>\n")
    engine = DjlintEngine(profile="html")
    raw = engine.run(tmp_path, [str(source)], cwd=tmp_path)
    assert raw["exit_code"] == 1
    lines = [line for line in raw["stdout"].splitlines() if line.strip()]
    assert lines and all(line.startswith("RUSH|") for line in lines)
    result = engine.normalize(raw, tmp_path, "templates")
    assert result["status"] == "warn"
    assert result["engine_version"]
    doctype = [f for f in result["findings"] if f["rule"] == "H001"]
    assert len(doctype) == 1
    assert Path(doctype[0]["path"]).resolve() == source.resolve()
    assert doctype[0]["line"] == 1
~~~

### Literal conservative configuration example

Append this exact table once to examples/rush.toml and mirror it in docs/CONFIGURATION.md and docs/reference/configuration-reference.md. No runtime path, image, effectful operation, or grant is persisted by the example. Other new operation fields stay explicit invocation examples in command references.

~~~toml
[tools.templates]
template_dialect = "html"
escape_policy = "html"
~~~

## P4 — Regression, failure recovery and completion gate

**Required behavior.** Close every ledger row and preserve Phase70 contracts. Test source/installed engine/runtime boundaries separately. Freeze changed bytes before verification; read-only reviewer checks exact hash. Any edit invalidates previous verdict.

**Deliverables.** Only literal files named in P1–P3/shared delta; command tests create fixtures in tmp_path, no permanent unrelated fixture corpus. Runtime prerequisites are already-installed approved executables/images; missing prerequisite blocks that acceptance lane and must be named, never silently skipped as passing.

**Constraints.** No install/network/build during planning. Future tests clear inherited PYTHONPATH, use project Python3.12. No duplicate runs beyond two unchanged-byte attempts, global broad suite, new harness, source rewrite, production DB/service, Git hooks, commit/push/release without explicit authorization. Cleanup failure exposes owned residue and exact restore/delete ownership; never claim clean.

**Checks to run before reporting.** From future implementation worktree based on frozen source:
~~~sh
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_templates.py tests/test_templates_transport.py tests/test_content_infra_tools.py tests/test_staged_scan_bytes.py tests/test_phase57_invocation_context.py tests/test_phase54_result_schema.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_module_boundaries.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
~~~
Expected Python3.12.x; exact changed-behavior assertions pass; Ruff exit0. Existing correct malformed-report/permission/root cases are preservation GREEN, not manufactured RED. Refactor only after behavior passes, then run affected checks once on new frozen bytes.

**Completion.** First repair packet is development-ready only after frozen plan review resolves all code/test/interface inconsistencies. Entire optional capability completion additionally requires real engine/OCI or SQLite proof, exact CLI+stdio parity, strict-schema adversarial input rejection, denied zero effects, source-byte/readback verification, approved scope and completed ledger. This authored plan is not an implementation PASS, installation verification, batch ratification or future runtime execution claim. Planning observed reproductions are listed separately above; every proposed GREEN check remains unexecuted.
