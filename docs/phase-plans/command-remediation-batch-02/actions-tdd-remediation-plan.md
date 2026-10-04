# Q11 — actions: selected workflows and bounded saved-job replay

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

Root scan must assess contained GitHub workflow files; selected-file argv must remain exact. Scope: `rush actions` / `rush_actions`, actionlint adapter, explicit optional workflow inspection and saved-job replay designs. Non-goals: executing arbitrary workflow jobs, trusting user-supplied CI evidence as attestation, rewriting workflows, invoking network or installing engines.

| ID/category | Evidence/current behavior | Concrete change | Task/check and acceptance |
|---|---|---|---|
| A1 defect | Audit Q11 4293–4350; live ContentTool 12–45/global collector routing.py438–475 excludes .github | Actions-only workflow collector; preserve scoped/staged selected bytes; unrelated YAML/action.yml excluded | P1 root/file/staged tests: exact one workflow |
| A2 defect | actionlint.py32 discards args | Remove deletion, append exact args and preserve cwd/ownership | P1 argv assertion |
| A3 ordinary proposal | Audit 4353–4396 | workflow_inspect child permission/pin checks, no CI claim | P2 exact child labels, missing-actionlint partial |
| A4 agent-side proposal | Audit 4403–4520 | saved-job digest+matrix+node checked; one pytest test in pinned isolated image | P2 real OCI reproduced/not_reproduced/stale/runtime mismatch |
| A5 baseline/integration | Phase70 T8–T16/T6/T27 | canonical root, grants, strict schema, result scope, missing readiness; baseline consumer receipts | P3 transport+denial, P4 regression |

## Current source and reproduced evidence

`src/rush/tools/actions.py:6–13` SHA256 `c67a7e207f41493fb555a000982691150022f5856d5997c981ef643d3ec0a091`; `src/rush/engines/actionlint.py:16–85` SHA256 `3f17447ef2a9e255101402414a83b9f6e3149a12311b60a356f2180a2284e59c`; shared `tools/content.py:12–45` SHA256 `1b7a4cb5f97b25a0a0ffce181b1507107cc83472afd37e5f2bc6723aab273a12`. Graft source used from source cwd; no stale delivery-bound Repowise evidence.

2026-10-01, Python 3.12.12, current callable `ActionsTool().run(root)`: root containing only `.github/workflows/ci.yml` returned skipped, engine calls 0. Controlled actual `ActionlintEngine.run(root,[workflow])` subprocess capture ended with root directory instead of workflow. These are observed defects. No optional GREEN/interface/OCI behavior is claimed executed.

## Input, result and permission contract

Public `path: Path` required. `workflow_inspect: StrictBool=False`; `replay_job: str|None=None` root-relative JSON; `runtime_path: str|None=None` approved absolute executable; `image_ref: str|None=None` locally installed digest image; `allow_build: StrictBool=False`, `allow_slow: StrictBool=False`. Shared wrapper supplies project/full/compact options. CLI literal options: `--workflow-inspect`, `--replay-job`, `--runtime-path`, `--image-ref`, existing `--allow-build --allow-slow`. No extra shell arguments. Replay needs build+slow before any engine/version/runtime call or scratch creation; denial returns skipped with `metadata.job_replay={status:"denied",reason:"missing_grants"}` and zero spawns. Inspection needs no grant.

Directory root selects only immediate `.github/workflows/*.yml|*.yaml`, sorted, case-insensitive extension. Direct workflow file accepted only under that exact folder within logical root; action metadata/unrelated YAML returns skipped no_workflows. Selecting workflow directory explicitly selects its immediate workflows. Staged/workspace catalog selection already dispatches explicit staged file paths: use context execution root and exact path, never rescan original root. Every candidate lexically checked using PhysicalRoot before open; symlink/reparse/outside rejects error. Missing target errors, no workflows skipped, missing actionlint skipped; metadata selected_paths includes selections and assessed_paths empty when unexecuted.

Inspection adds children `actionlint`, `permission-pin`; `ci_executed=false`. Parse ruamel YAML safe. Invalid workflow mapping/jobs/steps shape => fail workflow-syntax/shape finding, not crash. Check workflow and job-level permissions `write-all` or any permission value `write`. Check both reusable-job uses and step uses; local ./ refs allowed; external refs must match nonspace owner/repo[/path]@40hex; docker refs need @sha256:64hex, not a false Git-SHA finding. Finding includes logical relative source path/rule/severity/message. Inspection cannot upgrade skipped actionlint to clean: ok inspection+skipped actionlint => warn partial.

Replay JSON exact required keys `job_id,workflow_path,workflow_sha256,test_node,matrix_python,image_ref`, all nonempty strings, ≤64KiB. workflow_sha256 lower hex64; matrix_python exactly 3.12; image equals approved argument; workflow must be selected and digest match. Stale workflow => child stale_job, no spawn. Node exactly contained tests/<safe relative>.py::identifier[::identifier], no parametrization/options/parent traversal; source must exist. Image must contain Python3.12 and pytest; no install. Runtime mismatch reported before pytest. Saved evidence is user-supplied, never authenticated CI attestation.

## P1 — Fix selection and argv on existing callable

**Required behavior.** A1/A2; first RED reaches current run/normalize behavior without new keyword arguments or engine dependence.

**Deliverables.** `src/rush/tools/actions.py::ActionsTool.run`, `src/rush/engines/actionlint.py::ActionlintEngine.run`, new `tests/test_actions.py`. Full initial RED module:

~~~python
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rush.engines.actionlint import ActionlintEngine
from rush.tools.actions import ActionsTool


def test_root_workflow_selection(tmp_path):
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\non: push\njobs: {}\n")
    (tmp_path / "config.yml").write_text("unrelated: true\n")
    seen = []
    def engine(_engine, path, args, *, tool_name, **kwargs):
        seen.append((path, args))
        return {"tool": tool_name, "engine": "actionlint",
                "engine_version": "fixture", "status": "ok",
                "duration_ms": 0, "summary": "clean", "findings": [], "raw": None}
    # Patch current defining module; future override imports same common helper.
    with patch("rush.tools.content.run_engine", side_effect=engine), \
         patch("rush.tools.actions.run_engine", side_effect=engine, create=True):
        result = ActionsTool().run(tmp_path)
    assert len(seen) == 1  # current RED: 0
    assert seen[0][1] == [str(workflow)]
    assert result["metadata"]["assessed_paths"] == [".github/workflows/ci.yml"]


def test_engine_uses_selected_vector(tmp_path):
    a = tmp_path / "a.yml"; a.write_text("jobs: {}\n")
    b = tmp_path / "b.yml"; b.write_text("jobs: {}\n")
    with patch("rush.engines.actionlint.resolve_binary",
               return_value="/fixture/actionlint"), \
         patch("rush.engines.actionlint.run_subprocess",
               return_value=SimpleNamespace(returncode=0, stdout="[]", stderr="")) as run:
        ActionlintEngine().run(tmp_path, [str(a), str(b)], cwd=tmp_path)
    assert run.call_args.args[0][-2:] == [str(a), str(b)]
    assert run.call_args.kwargs["cwd"] == tmp_path
~~~

Minimum GREEN core (add imports; code is proposed, not applied):

~~~python
# src/rush/tools/actions.py
from pathlib import Path
from rush.invocation.targets import select_root, assert_contained
from rush.io.physical_paths import PhysicalRoot
from rush.engines import ENGINES
from rush.tools.common import run_engine, skipped_result, error_result

def selected_workflows(path, root):
    physical = PhysicalRoot(root)
    workflow_dir = root / ".github" / "workflows"
    if path.is_file():
        candidates = [path]
    elif path == root or path == workflow_dir:
        physical.open_contained(".github/workflows")
        candidates = list(workflow_dir.iterdir()) if workflow_dir.is_dir() else []
    else:
        candidates = []
    result = []
    for candidate in sorted(candidates):
        if candidate.parent != workflow_dir or candidate.suffix.lower() not in {".yml", ".yaml"}:
            continue
        checked = physical.open_contained(candidate.relative_to(root))
        if checked.is_file():
            result.append(checked)
    return result

# Replace inherited run for the first repair; P2 extends this exact method.
def run(self, path: Path, *, config=None, context=None):
    if context is None:
        selection = select_root(str(path), anchor=Path.cwd())
        assert_contained(selection)
        root = selection.root
        path = root / selection.relative
    else:
        root = context.workspace_root
    if not path.exists():
        return error_result(self.name, None, "target does not exist",
                            terminal_reason="TARGET_NOT_FOUND")
    files = selected_workflows(path, root)
    if not files:
        return skipped_result(self.name, "actionlint", "no_workflows",
                              metadata={"selected_paths": [], "assessed_paths": []})
    result = run_engine(ENGINES["actionlint"], root, list(map(str, files)),
                        tool_name=self.name, consumed_paths=list(map(str, files)),
                        project_root=root)
    selected = [p.relative_to(root).as_posix() for p in files]
    result.setdefault("metadata", {}).update(
        selected_paths=selected,
        assessed_paths=selected if result["status"] in {"ok", "warn", "fail"} else [])
    return result
~~~

The class method must call `selected_workflows`; its signature is preserved as above and `__call__(path, *, context=None)` returns `self.run(path,context=context)`. Catch contained-file/OS failures at the tool boundary as canonical error without resuming scan. Exact adapter delta: delete `del args,cwd` and `source=path`; replace final `str(source)` argv element with `*args`; replace cwd with `cwd or (path.parent if path.is_file() else path)`. Keep timeout 120, fixed config, disabled shellcheck/pyflakes and ownership unchanged. No empty-args default scan: empty args returns engine error before spawn.

**Constraints.** No global collector change; no backward allowance for action.yml as workflow; no symlink-following collector.
**Checks.** `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_actions.py -q`.
**Completion.** RED assertions turn GREEN; direct root/file/workflow-dir selections and exact engine args verified; empty/missing/engine-missing paths distinguish results.

## P2 — Explicit inspection and saved-job replay

**Required behavior.** A3/A4 input and output contract above. Preserve independent actionlint result while exposing separately typed children. Aggregate with Phase70 precedence.

**Deliverables.** Same ActionsTool file adds `inspect_workflows(files,root)` and `replay_saved_job(root,files,job_path,runtime_path,image_ref,permissions)`; tests remain `tests/test_actions.py`. No additional framework.

**Concrete inspection algorithm.** Iterate each safe-loaded document; append `workflow-write-permission` for workflow/job grants, `unpinned-action` for each unpinned uses occurrence with explicit path; malformed YAML includes parser mark+1. Record actionlint child before adding own findings. Record permission-pin child status fail for parse/shape errors, warn for findings, ok for assessed clean; it is never CI execution. Example unpinned actions/checkout@v4 + permissions contents:write yields both rules and children actionlint plus permission-pin; ci_executed remains false.


Append ordinary-extension behavior test to tests/test_actions.py. This executes workflow analysis; engine double isolates installed-actionlint availability only.

~~~python
def test_workflow_inspect_child_labels(tmp_path):
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    (tmp_path / "rush.toml").write_text("")
    workflow.write_text(
        "name: CI\non: push\npermissions:\n  contents: write\njobs:\n"
        "  build:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n")
    clean = {"tool": "actions", "engine": "actionlint",
             "engine_version": "fixture", "status": "ok", "duration_ms": 0,
             "summary": "clean", "findings": [], "raw": None}
    with patch("rush.tools.actions.run_engine", return_value=clean):
        result = ActionsTool().run(tmp_path, workflow_inspect=True)
    assert result["status"] == "warn"
    assert result["metadata"]["children"] == [
        {"name": "actionlint", "status": "ok"},
        {"name": "permission-pin", "status": "warn"}]
    assert result["metadata"]["ci_executed"] is False
    assert sorted(f["rule"] for f in result["findings"]) == [
        "unpinned-action", "workflow-write-permission"]
    assert {f["path"] for f in result["findings"]} == {".github/workflows/ci.yml"}
~~~

**Concrete replay controller.** Validate grant/input/digest/schema before spawning. Use P0 provider, temporary mode0700 scratch, fixed entrypoint /usr/local/bin/python and argv `["-c", PROGRAM, node]`. PROGRAM is:

~~~python
REPLAY_PROGRAM = r'''import json
import subprocess
import sys
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    Path("/out/replay.json").write_text(json.dumps({"status": "runtime_mismatch"}))
    raise SystemExit(0)
node = sys.argv[1]
completed = subprocess.run(
    [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", node,
     "--junitxml=/out/junit.xml", "-q"],
    cwd="/work", capture_output=True, text=True, timeout=180, check=False)
Path("/out/replay.json").write_text(json.dumps({
    "status": "observed", "python": "3.12", "node": node,
    "exit_code": completed.returncode}))
'''
~~~

Provider timeout210. Controller reads no-follow regular `replay.json` ≤64KiB and `junit.xml` ≤1MiB; parse ElementTree; reject DOCTYPE and malformed/extra fields. Exactly one testcase and tests=1, errors=0, skipped=0 required. Match classname/name against selected module/class/function (tests/test_a.py::TestA::test_a → tests.test_a.TestA/test_a). Exit1 and exactly one failure => reproduced; exit0 and no failure => not_reproduced; pytest collection/usage/import/timeout errors => error, never not_reproduced. pytest skip => child unassessed. Tests are project code: receipts are observations from isolated untrusted project, not attestation. Recheck original workflow+test bytes after run; drift => stale_job; cleanup always, no workflow shell executed. Return job_replay {job_id,matrix:{python:"3.12"},test_node,status,workflow_sha256,image_ref,test_count:1}; runtime mismatch carries no test_count claim. This resolves audit's absent Q04 selected-test dependency using same exact single-node replay semantics.

**Runnable runtime acceptance** (append to same test module; requires P0 and explicit locally installed Python3.12/pytest image):

~~~python
def test_saved_matrix_job_replays_exact_node(tmp_path):
    import hashlib, json, os
    from rush.permissions import ExecutionPermissions
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\non: push\njobs: {}\n")
    (tmp_path / "rush.toml").write_text("")
    tests = tmp_path / "tests"; tests.mkdir()
    target = tests / "test_a.py"
    target.write_text("def test_a():\n    assert 1 == 2\n"
                      "def test_other():\n    raise RuntimeError('must not execute')\n")
    image = os.environ["RUSH_TEST_RUSH_IMAGE"]
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    job = {"job_id": "ci/3.12", "workflow_path": ".github/workflows/ci.yml",
           "workflow_sha256": hashlib.sha256(workflow.read_bytes()).hexdigest(),
           "test_node": "tests/test_a.py::test_a", "matrix_python": "3.12",
           "image_ref": image}
    (tmp_path / "job.json").write_text(json.dumps(job))
    options = dict(replay_job="job.json", runtime_path=runtime, image_ref=image,
                   permissions=ExecutionPermissions(build=True, slow=True))
    result = ActionsTool().run(tmp_path, **options)
    replay = result["metadata"]["job_replay"]
    assert replay["status"] == "reproduced"
    assert replay["test_count"] == 1
    assert replay["test_node"] == job["test_node"]
    job["workflow_sha256"] = "0" * 64
    (tmp_path / "job.json").write_text(json.dumps(job))
    with patch("rush.tools.actions.run_isolated_argv") as spawn:
        stale = ActionsTool().run(tmp_path, **options)
    assert stale["metadata"]["job_replay"]["status"] == "stale_job"
    spawn.assert_not_called()
~~~

Add exact cases to this module: denied build and denied slow each zero engine/version/provider calls; Python3.11 image runtime_mismatch, passing test not_reproduced, skipped test unassessed, collect-error error, digest drift stale_job, malformed/outside/symlink JSON error, cancellation cleans runtime/scratch. Include actual actionlint installed lane using invalid `runs-on` type fixture and source path; unavailable engine does not pass runtime acceptance.

**Constraints.** P0 runtime acceptance prerequisite for optional replay, not first repair. No network/installation, arbitrary steps, external shell, durable receipt or source writes.
**Checks.** Same test module command plus P0 real suite. All optional bodies proposed and unexecuted at planning time.
**Completion.** Inspection reports separate checks; replay proves selected testcase identity and precise outcome with grants and cleanup. No CI-success claim.

### Complete P2 controller insertion

Proposed additions to src/rush/tools/actions.py below supersede controller-only prose. REPLAY_PROGRAM is the complete P2 Python program above stored verbatim as a module string. It invokes exactly one pytest node.

~~~python
import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from rush.permissions import ExecutionPermissions, check_permissions
from rush.runtime.isolated_process import run_isolated_argv
from rush.tools.base import ToolResult
from rush.workflows.projects import open_contained_file

def _action_bytes(root, relative, limit):
    with os.fdopen(open_contained_file(root, str(relative)), "rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError("action_input_too_large")
    return value

def inspect_workflows(files, root):
    findings = []
    malformed = False
    for source in files:
        relative = source.relative_to(root).as_posix()
        def finding(rule, message, line=None):
            item = dict(path=relative, rule=rule, severity="warn", message=message)
            if line is not None:
                item["line"] = line
            findings.append(item)
        def permissions(value):
            if value == "write-all" or (
                isinstance(value, dict) and "write" in value.values()
            ):
                finding("workflow-write-permission", "Workflow permits writes")
        def uses(value):
            if not isinstance(value, str):
                raise ValueError("uses must be string")
            pinned = (value.startswith("./") or
                re.fullmatch(r"docker://[^\s]+@sha256:[0-9a-f]{64}", value) or
                re.fullmatch(r"[^@\s/]+/[^@\s]+@[0-9a-fA-F]{40}", value))
            if not pinned:
                finding("unpinned-action", "External action lacks immutable pin")
        try:
            document = YAML(typ="safe").load(
                _action_bytes(root, relative, 1_048_576).decode("utf-8"))
            if not isinstance(document, dict) or not isinstance(document.get("jobs"), dict):
                raise ValueError("workflow requires jobs mapping")
            permissions(document.get("permissions"))
            for job in document["jobs"].values():
                if not isinstance(job, dict):
                    raise ValueError("job must be mapping")
                permissions(job.get("permissions"))
                if "uses" in job:
                    uses(job["uses"])
                if "steps" in job:
                    if not isinstance(job["steps"], list):
                        raise ValueError("steps must be list")
                    for step in job["steps"]:
                        if not isinstance(step, dict):
                            raise ValueError("step must be mapping")
                        if "uses" in step:
                            uses(step["uses"])
        except (YAMLError, ValueError, UnicodeError) as exc:
            malformed = True
            mark = getattr(exc, "problem_mark", None)
            finding("workflow-syntax", "Workflow mapping or YAML invalid",
                    mark.line + 1 if mark is not None else None)
    return ToolResult(tool="actions", engine="permission-pin", engine_version=None,
        status="fail" if malformed else "warn" if findings else "ok",
        duration_ms=0, summary="Workflow permissions and pins assessed",
        findings=findings, raw=None, metadata={"ci_executed": False})

def replay_saved_job(root, files, job_path, runtime_path, image_ref, permissions):
    allowed, _ = check_permissions(ExecutionPermissions(build=True, slow=True), permissions)
    if not allowed:
        return {"status": "denied", "reason": "missing_grants"}
    job = json.loads(_action_bytes(root, job_path, 65_536))
    keys = {"job_id", "workflow_path", "workflow_sha256", "test_node",
            "matrix_python", "image_ref"}
    if (not isinstance(job, dict) or set(job) != keys or
        any(type(v) is not str or not v for v in job.values()) or
        not re.fullmatch(r"[0-9a-f]{64}", job["workflow_sha256"]) or
        job["matrix_python"] != "3.12" or job["image_ref"] != image_ref):
        raise ValueError("saved_job_invalid")
    if job["workflow_path"] not in {p.relative_to(root).as_posix() for p in files}:
        raise ValueError("saved_job_workflow_not_selected")
    node = job["test_node"]
    if not re.fullmatch(r"tests/(?:[A-Za-z_]\w*/)*[A-Za-z_]\w*\.py"
                        r"::[A-Za-z_]\w*(?:::[A-Za-z_]\w*)?", node):
        raise ValueError("saved_job_node_invalid")
    source_name, *identifiers = node.split("::")
    workflow = _action_bytes(root, job["workflow_path"], 1_048_576)
    test = _action_bytes(root, source_name, 1_048_576)
    common = {"job_id": job["job_id"], "matrix": {"python": "3.12"},
              "test_node": node, "workflow_sha256": job["workflow_sha256"],
              "image_ref": image_ref}
    if hashlib.sha256(workflow).hexdigest() != job["workflow_sha256"]:
        return {**common, "status": "stale_job"}
    with tempfile.TemporaryDirectory(prefix="rush-replay-") as folder:
        scratch = Path(folder); scratch.chmod(0o700)
        process = run_isolated_argv(root, scratch, runtime_path=Path(runtime_path),
            image_ref=image_ref, entrypoint="/usr/local/bin/python",
            argv=["-c", REPLAY_PROGRAM, node], timeout_s=210)
        if process.returncode != 0:
            raise ValueError("replay_child_failed")
        receipt = json.loads(_action_bytes(scratch, "replay.json", 65_536))
        if receipt == {"status": "runtime_mismatch"}:
            return {**common, "status": "runtime_mismatch"}
        if (not isinstance(receipt, dict) or set(receipt) !=
            {"status", "python", "node", "exit_code"} or
            receipt["status"] != "observed" or receipt["python"] != "3.12" or
            receipt["node"] != node or type(receipt["exit_code"]) is not int):
            raise ValueError("replay_receipt_invalid")
        junit = _action_bytes(scratch, "junit.xml", 1_048_576)
        if b"<!DOCTYPE" in junit.upper() or b"<!ENTITY" in junit.upper():
            raise ValueError("replay_junit_invalid")
        report = ET.fromstring(junit)
        cases = list(report.iter("testcase")); suites = list(report.iter("testsuite"))
        if len(cases) != 1 or len(suites) != 1 or suites[0].get("tests") != "1":
            raise ValueError("replay_test_identity_invalid")
        case = cases[0]
        classname = source_name[:-3].replace("/", ".")
        if len(identifiers) == 2:
            classname += "." + identifiers[0]
        if case.get("classname") != classname or case.get("name") != identifiers[-1]:
            raise ValueError("replay_test_identity_invalid")
        if list(case.iter("error")) or suites[0].get("errors") != "0":
            raise ValueError("replay_test_error")
        if list(case.iter("skipped")):
            status = "unassessed"
        else:
            failures = list(case.iter("failure"))
            if len(failures) > 1 or receipt["exit_code"] != (1 if failures else 0):
                raise ValueError("replay_exit_report_mismatch")
            status = "reproduced" if failures else "not_reproduced"
        if (_action_bytes(root, job["workflow_path"], 1_048_576) != workflow or
            _action_bytes(root, source_name, 1_048_576) != test):
            return {**common, "status": "stale_job"}
        return {**common, "status": status, "test_count": 1}
~~~

Exact ActionsTool.run integration: add P2 keywords with declared defaults. Before run_engine, call replay_saved_job once when requested and store replay. Denied returns skipped metadata.reason=missing_grants/job_replay denied. Stale returns warn with job_replay stale_job, selected_paths and assessed_paths=[] before lint. Controller performs no engine invocation on stale input. Preserve normal scanner path for successful replay; append following complete insertion after normal result.

~~~python
from rush.tools.routing import aggregate_results

if workflow_inspect:
    inspection = inspect_workflows(files, root)
    scanner_status = result["status"]
    original_metadata = dict(result.get("metadata", {}))
    result = aggregate_results("actions", [result, inspection])
    result["metadata"].update(original_metadata)
    result["metadata"]["children"] = [
        {"name": "actionlint", "status": scanner_status},
        {"name": "permission-pin", "status": inspection["status"]}]
    result["metadata"]["ci_executed"] = False
if replay_job is not None:
    result.setdefault("metadata", {})["job_replay"] = replay
    if replay["status"] == "reproduced" and result["status"] != "error":
        result["status"] = "fail"
    elif replay["status"] in {"runtime_mismatch", "unassessed", "stale_job"}:
        if result["status"] == "ok":
            result["status"] = "warn"
~~~

Tool boundary catches ValueError/OSError/ElementTree.ParseError as canonical error reason invalid_replay; isolation exceptions retain P0 mappings. Saved job_id is caller label, not authenticated CI job identity; exact workflow digest and testcase identity are verified.

### Complete ActionsTool.run after P2

This replaces the earlier first-repair-only run when P2 is implemented; __call__ below forwards these exact named fields.

~~~python
def run(self, path, *, config=None, context=None, workflow_inspect=False,
        replay_job=None, runtime_path=None, image_ref=None, permissions=None):
    from rush.tools.routing import aggregate_results
    from rush.io.physical_paths import ContainmentError
    from rush.runtime.isolated_process import IsolationUnavailable, IsolationCleanupError
    try:
        if context is None:
            selection = select_root(str(path), anchor=Path.cwd())
            assert_contained(selection)
            root = selection.root
            path = root / selection.relative
        else:
            root = context.workspace_root
        if not path.exists():
            return error_result(self.name, None, "target does not exist",
                                terminal_reason="TARGET_NOT_FOUND")
        files = selected_workflows(path, root)
        names = [p.relative_to(root).as_posix() for p in files]
        if not files:
            return skipped_result(self.name, "actionlint", "no_workflows",
                metadata={"selected_paths": [], "assessed_paths": []})
        replay = None
        if replay_job is not None:
            allowed, _ = check_permissions(ExecutionPermissions(build=True, slow=True), permissions)
            if not allowed:
                return skipped_result(self.name, None, "missing_grants",
                    metadata={"reason": "missing_grants", "assessed_paths": [],
                              "selected_paths": names, "job_replay": {
                                  "status": "denied", "reason": "missing_grants"}})
            if not runtime_path or not image_ref:
                return skipped_result(self.name, None, "isolation_unavailable",
                    metadata={"reason": "isolation_unavailable", "assessed_paths": []})
            replay = replay_saved_job(root, files, replay_job, runtime_path, image_ref, permissions)
            if replay["status"] == "stale_job":
                return ToolResult(tool=self.name, engine=None, engine_version=None,
                    status="warn", duration_ms=0, summary="Saved workflow changed",
                    findings=[], raw=None, metadata={"selected_paths": names,
                        "assessed_paths": [], "job_replay": replay, "ci_executed": False})
        result = run_engine(ENGINES["actionlint"], root, list(map(str, files)),
            tool_name=self.name, consumed_paths=list(map(str, files)), project_root=root)
        result.setdefault("metadata", {}).update(selected_paths=names,
            assessed_paths=names if result["status"] in {"ok", "warn", "fail"} else [])
        if workflow_inspect:
            inspection = inspect_workflows(files, root)
            scanner_status = result["status"]
            original_scope = {key: result["metadata"][key]
                              for key in ("selected_paths", "assessed_paths")}
            result = aggregate_results(self.name, [result, inspection])
            result["metadata"].update(original_scope)
            result["metadata"]["children"] = [
                {"name": "actionlint", "status": scanner_status},
                {"name": "permission-pin", "status": inspection["status"]}]
            result["metadata"]["ci_executed"] = False
        if replay is not None:
            result["metadata"]["job_replay"] = replay
            if replay["status"] == "reproduced" and result["status"] != "error":
                result["status"] = "fail"
            elif replay["status"] in {"runtime_mismatch", "unassessed"} and result["status"] == "ok":
                result["status"] = "warn"
        return result
    except IsolationUnavailable:
        return skipped_result(self.name, None, "isolation_unavailable",
                              metadata={"reason": "isolation_unavailable"})
    except IsolationCleanupError:
        return error_result(self.name, None, "Isolated replay cleanup failed",
                            terminal_reason="isolation_cleanup_failed")
    except (ValueError, OSError, ContainmentError, ET.ParseError):
        return error_result(self.name, None, "Workflow or saved replay input invalid",
                            terminal_reason="invalid_replay")
~~~

SubprocessCancelled/TimeoutExpired retain existing runtime terminal handling and never become clean. P0 performs owned runtime cleanup before either propagates.

## P3 — Real CLI and initialized stdio MCP parity

**Required behavior.** Explicit options reach shared tool implementation on both transports. Matching domain projection below is equal; target identities and grants cannot be inferred from tools/list alone. Test-owned engine below proves forwarding/parser behavior only; P2 real-engine/OCI tests separately prove runtime behavior.

**Deliverables.** Add following complete module to `tests/test_actions_transport.py`; Batch integration owner adds command's explicit options to `_TOOL_CLI_OPTIONS` and exact `ToolOptionSpec` tuple to existing `TOOL_SPECS["actions"]`. Preserve existing `make_tool_wrapper`/executor; context is internal. No generic introspection factory, MCP-only implementation or new CLI route.

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

COMMAND = "actions"
BINARY = "actionlint"
SOURCE = ".github/workflows/ci.yml"
BODY = "name: CI\non: push\njobs: {}\n"
OPTIONS = {}
CLI_OPTIONS = []
EXPECTED = {"status":"ok","assessed_paths":[".github/workflows/ci.yml"]}
PROJECTION = ["assessed_paths"]


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
    assert all(str(source) in json.loads(line) for line in marker.read_text().splitlines())


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
`rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_actions_transport.py tests/test_actions.py tests/test_cli_registry.py tests/test_mcp.py -q`

**Completion.** Real process CLI and initialized stdio call agree on stated domain values, missing/denied input produces zero analysis/state effects, parameter schema is exact, source bytes unchanged, and separate runtime checks pass.


Append this complete denied-request case to the same transport module. Permission denial is preflight for the whole explicitly requested operation, returning skipped with metadata.reason="missing_grants"; no engine/version/runtime call occurs.

~~~python
def test_cli_stdio_denied_request_zero_effects(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(BODY)
    for relative, text in {"job.json": "{\"job_id\":\"ci/3.12\",\"workflow_path\":\".github/workflows/ci.yml\",\"workflow_sha256\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"test_node\":\"tests/test_a.py::test_a\",\"matrix_python\":\"3.12\",\"image_ref\":\"fixture/image@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\"}", "tests/test_a.py": "def test_a():\n    assert True\n"}.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    import hashlib
    saved = json.loads((root / "job.json").read_text())
    saved["workflow_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    (root / "job.json").write_text(json.dumps(saved))
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
    options = {"replay_job": "job.json"}
    options.update(runtime_path=runtime, image_ref=image)
    flags = ["--replay-job", "job.json"] + ["--runtime-path", runtime, "--image-ref", image]
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
    assert local["metadata"]["job_replay"]["status"] == remote["metadata"]["job_replay"]["status"] == "denied"
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
GRANTED_SCHEMA = exact_schema(json.loads(r'''{"workflow_inspect":{"type":"boolean","default":false},"replay_job":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"runtime_path":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"image_ref":{"anyOf":[{"type":"string"},{"type":"null"}],"default":null},"allow_build":{"type":"boolean","default":false},"allow_slow":{"type":"boolean","default":false}}'''))

def test_granted_replay_cli_stdio_foreign_cwd(tmp_path):
    import hashlib, json, os
    root = tmp_path / "project"; root.mkdir()
    (root / "rush.toml").write_text("")
    workflow = root / ".github/workflows/ci.yml"; workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python -m pytest tests/test_case.py::test_case\n")
    tests = root / "tests"; tests.mkdir()
    (tests / "test_case.py").write_text("def test_case():\n    assert False\n")
    image = os.environ["RUSH_TEST_RUSH_IMAGE"]
    runtime = os.environ["RUSH_TEST_OCI_RUNTIME"]
    job = {"job_id": "test/3.12", "workflow_path": ".github/workflows/ci.yml",
           "workflow_sha256": hashlib.sha256(workflow.read_bytes()).hexdigest(),
           "test_node": "tests/test_case.py::test_case", "matrix_python": "3.12",
           "image_ref": image}
    (root / "job.json").write_text(json.dumps(job))
    env, foreign, project = granted_environment(tmp_path, root)
    before = entire_tree(root)
    left = granted_cli(foreign, env, "actions", root,
        ["--replay-job", "job.json", "--runtime-path", runtime, "--image-ref", image,
         "--allow-build", "--allow-slow"], 1)
    right = granted_stdio(foreign, env, "actions",
        {"project": project, "path": ".", "replay_job": "job.json",
         "runtime_path": runtime, "image_ref": image, "allow_build": True,
         "allow_slow": True, "no_cache": True}, GRANTED_SCHEMA)
    expected = {"job_id": "test/3.12", "matrix": {"python": "3.12"},
                "test_node": job["test_node"], "status": "reproduced",
                "workflow_sha256": job["workflow_sha256"], "image_ref": image,
                "test_count": 1}
    assert left["status"] == right["status"] == "fail"
    assert left["metadata"]["job_replay"] == right["metadata"]["job_replay"] == expected
    assert entire_tree(root) == before

~~~

## Literal transport/configuration edits and future PR scope

Batch integration owner appends only this command's tuple to existing `src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS` (factory already forwards `**tool_options`). Existing permission options are not redeclared:

~~~python
"actions": (
    click.Option(["--workflow-inspect"], is_flag=True, default=False),
    click.Option(["--replay-job"], type=str, default=None),
    click.Option(["--runtime-path"], type=str, default=None),
    click.Option(["--image-ref"], type=str, default=None),
),
~~~

In `src/rush/catalog.py`, replace this command's `option_specs` with the following complete tuple, retaining canonical name/category/maturity/engine mapping. Each local document parameter intentionally uses default path_kind="none" because tool validates it root-relatively through PhysicalRoot; do not add it to cwd-relative `_CWD_RELATIVE_ARGS`. External runtime is never interpreted as project file. This explicit anchor decision prevents nested cwd rebasing.

~~~python
option_specs=(
    ToolOptionSpec("workflow_inspect", bool, default=False, description="workflow inspect; see command contract"),
    ToolOptionSpec("replay_job", str, default=None, description="replay job; see command contract"),
    ToolOptionSpec("runtime_path", str, default=None, description="runtime path; see command contract"),
    ToolOptionSpec("image_ref", str, default=None, description="image ref; see command contract"),
)
~~~

Add exact typed callable to `src/rush/tools/actions.py::ActionsTool` (imports supplied; place method inside class). Its `run` accepts same domain options plus `permissions,context,config`, with all defaults identical; list/tuple preserve_fields normalize once to list. Strict booleans preserve invalid-type rejection.

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
    workflow_inspect: StrictBool = False,
    replay_job: str | None = None,
    runtime_path: str | None = None,
    image_ref: str | None = None,
    allow_build: StrictBool = False,
    allow_slow: StrictBool = False,
    context: InvocationContext | None = None,
) -> ToolResult:
    if any(type(value) is not bool for value in (allow_build, allow_slow, workflow_inspect,)):
        return error_result("actions", None, "boolean arguments must be booleans",
                            terminal_reason="INVALID_REQUEST")
    return self.run(
        path,
        workflow_inspect=workflow_inspect,
        replay_job=replay_job,
        runtime_path=runtime_path,
        image_ref=image_ref,
        permissions=ExecutionPermissions(build=allow_build, slow=allow_slow),
        context=context,
    )
~~~

Tracked configuration guide is `docs/CONFIGURATION.md` (uppercase Git path), and existing conservative example is `examples/rush.toml`; both are shared integration-owner writes. Existing `ToolOptionSpec` tuple is configuration schema. Preserve existing tables; append only this command's single safe-default table described below. Update command section in `docs/reference/configuration-reference.md` with literal `[tools.actions]` keys/defaults and root-relative semantics, corresponding sections in `docs/reference/cli-reference.md`, `docs/MCP_REFERENCE.md`, `docs/reference/mcp-tool-reference.md`, `docs/reference/result-reference.md`. Add one clean, one no-work, one denied, one failed example with actual result/exit. Update `tests/test_cli_registry.py` exact help/flags and `tests/test_mcp.py` emitted parameter assertions; `tests/test_phase60_characterization.py` retains tool count and updates this command's fields only. `scripts/sync_docs.py` is check-only. Edit existing reference rows and serialized coverage receipt/hash rows in `docs/reports/phase-64-66-documentation-coverage.md` directly using final exact doc bytes; then run `rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python scripts/sync_docs.py --check`. Never claim this command generates or repairs documentation. `tests/fixtures/phase70/cli-outcomes.json` receives this command's populated/empty/denied/failure/side-effects domain assertions. Existing shared renderer/delivery consumes metadata; preserve full result, visible partial/no-work and terminal escaping.

Future PR scope: first command repair files/tests and exactly necessary shared catalog/docs delta; optional ordinary and agent-side features remain separately reviewable later commits/PR scopes when authorized. Shared provider prerequisite lands before any consumer feature; no separate command identity or duplicate transport implementation.

### Complete installed-engine acceptance

Append to tests/test_actions.py. Genuine engine resolved through existing resolver; no doubles. These future tests were not executed during planning. Missing executable/image is failed prerequisite, never successful skip. Run with same approved runtime environment as granted transport node.


~~~python
def test_real_actionlint_workflow(tmp_path):
    from pathlib import Path
    from rush.runtime.binaries import resolve_binary
    from rush.tools.actions import ActionsTool
    assert resolve_binary("actionlint"), "approved actionlint must be preinstalled"
    (tmp_path / "rush.toml").write_text("")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: CI\non: push\njobs: []\n")
    result = ActionsTool().run(tmp_path)
    assert result["status"] == "warn"
    assert result["engine"] == "actionlint"
    assert result["engine_version"]
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "syntax-check"
    assert Path(finding["path"]).resolve() == workflow.resolve()
    assert finding["line"] == 3
    assert result["metadata"]["assessed_paths"] == [".github/workflows/ci.yml"]
~~~

### Literal conservative configuration example

Append this exact table once to examples/rush.toml and mirror it in docs/CONFIGURATION.md and docs/reference/configuration-reference.md. No runtime path, image, effectful operation, or grant is persisted by the example. Other new operation fields stay explicit invocation examples in command references.

~~~toml
[tools.actions]
workflow_inspect = false
~~~

## P4 — Regression, failure recovery and completion gate

**Required behavior.** Close every ledger row and preserve Phase70 contracts. Test source/installed engine/runtime boundaries separately. Freeze changed bytes before verification; read-only reviewer checks exact hash. Any edit invalidates previous verdict.

**Deliverables.** Only literal files named in P1–P3/shared delta; command tests create fixtures in tmp_path, no permanent unrelated fixture corpus. Runtime prerequisites are already-installed approved executables/images; missing prerequisite blocks that acceptance lane and must be named, never silently skipped as passing.

**Constraints.** No install/network/build during planning. Future tests clear inherited PYTHONPATH, use project Python3.12. No duplicate runs beyond two unchanged-byte attempts, global broad suite, new harness, source rewrite, production DB/service, Git hooks, commit/push/release without explicit authorization. Cleanup failure exposes owned residue and exact restore/delete ownership; never claim clean.

**Checks to run before reporting.** From future implementation worktree based on frozen source:
~~~sh
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_actions.py tests/test_actions_transport.py tests/test_content_infra_tools.py tests/test_staged_scan_bytes.py tests/test_phase57_invocation_context.py tests/test_phase54_result_schema.py tests/test_phase60_complexity_thresholds.py tests/test_phase60_module_boundaries.py -q
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --offline --python 3.12 --extra dev ruff format --check src tests scripts
~~~
Expected Python3.12.x; exact changed-behavior assertions pass; Ruff exit0. Existing correct malformed-report/permission/root cases are preservation GREEN, not manufactured RED. Refactor only after behavior passes, then run affected checks once on new frozen bytes.

**Completion.** First repair packet is development-ready only after frozen plan review resolves all code/test/interface inconsistencies. Entire optional capability completion additionally requires real engine/OCI or SQLite proof, exact CLI+stdio parity, strict-schema adversarial input rejection, denied zero effects, source-byte/readback verification, approved scope and completed ledger. This authored plan is not an implementation PASS, installation verification, batch ratification or future runtime execution claim. Planning observed reproductions are listed separately above; every proposed GREEN check remains unexecuted.
