# F00: Shared foundation for the Q01-Q10 plans

Audit: docs/reports/cli-mcp-command-audit-2026-09-26.md, sha256 8ff7a75c35b8c9794b95725dbe76cf36a0056ef6b5863518065d9669439a077f (sections 3, 4, 6, 8; Command 45/79 isolation contract at 13810-13889; Q18 at 6559).
Implementation base: phase/70-agent-adoption-and-usability at 66c6c79 or its merge commit. Start gate: Phase 70 T1-T29 and G0-G8 complete.
Authorization: planning only; no implementation, commit or push. Executed by the Foundation owner (README Roles). Each Q plan restates the text it consumes, so a plan is readable alone.

## Goal, scope and non-goals
Provide every shared Q01-Q10 dependency with Phase70 transport/result compatibility and full audit scope. Preserve user-requested scanner/model/voice/companion baseline. No release, network-enabled launcher or implementation authorized during remediation. Ordered packets and file map: README Order/Roles. Stop implementation before RED on unresolved decisions, missing binding inputs, byte drift or unproved Phase70 start gate. Runtime absence never authorizes host execution.

## Requirement ledger
| Packet | Concrete change | Acceptance |
|---|---|---|
| F1 | Flat strict command models from wrapper public_sig; typed CLI options | Ten-tool invalid grant/unknown-key rejection; six transport fields preserved |
| F2 | routing.child_scope, existing aggregate_scope/status | complete+unavailable partial, only-none none, ok+skipped warn at D5 default |
| F3 | Canonical grants/error/empty/operation vocabulary | Zero-spawn denial and exact command carrier assertions |
| F4 | Local OCI provider and no-launch preflight | Real read-only/network-denied run, launch cap, cleanup, receipt |
| F5 | Selected-node pytest adapter | Exact return-code/count parsing; unique contained nodes |
| F6 | Shared real CLI/stdio MCP helper | Meaningful result parity, Windows errlog, exact exit codes |
| F7 | Digest-verified contained CycloneDX consumer | Matching digest accepted; malformed/mismatch/escape rejected |
| F8 | Serialized same-packet docs and historical receipts | sync_docs exit 0; historical bodies byte-identical |
| F9 | Fail-closed config error at three wrapper callers | Malformed rush.toml: CLI exit 2, MCP error, zero dispatch |
| F10 | ToolSpec.discovery in schema path and CLI help | Ten exact descriptions; bounded mcp_description preserved |
| F11 | Exhaustive forwarding acceptance | Every typed option reaches real route after signatures exist |

## Binding baseline and decision gates
This remediation changes only this Markdown file. Delivery checkout: /Users/jamesdsizemore/Developer/rush-cli at c78e445ba1e575ca373e35840142cd627b055d6a; implementation evidence checkout: /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70, branch phase/70-agent-adoption-and-usability, clean HEAD 66c6c799eaa5b6017776d659e9e0de2b4a8878a5. Clean Git state proves provenance, not Phase70 acceptance. Original Plan00 SHA256: 02d20fedb2ba10032014d330a324d02557897e7776c969ad96cf713510dd0fbf. Claude report SHA256: 362dae4489fbe8f6322217e30ae69ed3ad8a888732a37029641a0040cd8ef633. Audit SHA256 is recorded above. Final file SHA256 belongs in the review receipt outside these bytes, avoiding a self-referential hash.

Authority: James's scope and corrections; final C-01–C-29 resolutions over earlier conflicting report text; audit's full required behavior; current Phase70 source and design briefs for existing interfaces. A current implementation shortfall cannot remove audit behavior. Defaults below are report proposals, not James's approval. Guide's Plans02–10 audience does not narrow James's explicit Plan00 instruction.

Phase70 reconciliation: use docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md and its .scratch/phase-70-design-gate/W1-T1-T7-T23.md (T1–T7/T23 prerequisites), T8.md, W2-T9-T17.md, W3-T18-T22.md and W4-T23-T29.md. Packet and fuller brief requirements both apply. Preserve T9 invalid-target zero-dispatch, T11/T12 typecheck grants/config, T14 security coverage, T16 compact delivery/aggregate status, T17 target/applicability and T23–T29 lifecycle/trust boundaries. Fully qualified future source/test changes below are proposed, unexecuted.

| Open choice | Affected route and full-scope alternatives | Required decision before affected implementation |
|---|---|---|
| D1 | F4/F7 inside Foundation (report default) or identical content in two separately authorized plans | Plan00 includes complete design under either ownership choice; this edit authorizes no new files |
| D2 | Tool kwargs runtime_path/image_ref (default) or isolation_runtime/isolation_image; provider kwargs unchanged | F1/F11 command registration names and consumer signatures agree |
| D3 | Preserve existing run() grant conventions (default) or migrate all ten to run(permissions) | F3 adapters and exact compatibility tests; Typecheck currently differs |
| D4 | Q03/Q05 timeout_s=300 (default) or 180 | F4 caller timeout rows; Q10 remains30 under C-04 |
| D5 | Existing aggregate ok+skipped→warn, CLI1 (default) or shared aggregate skipped, CLI0 | F2 shared aggregation/tests; never tool-local override |
| D6 | Missing-runtime operation skipped/reason isolation_unavailable (default) or status isolation_unavailable | F3 command block carrier; tool result retains canonical status vocabulary |
| D7 | Q01 import-cycle acceptance regression-only (default) or proposed lazy registry | Consumer-owned; no registry invented in F00 |
| D8 | mypy src/rush (default) or mypy . | Same selected gate in checks/CI; not chosen by this edit |
| D9 | Q07 scratch_on_pythonpath=True (default) or fully specified python -c bootstrap | F4/F5 transport and Q07 plugin import; generic helper default remains False |
| D10 | POSIX docker/podman runtime rule (a); add nerdctl (b); operator-config runtime/image (c) | F4 trust preflight and tests follow approved branch; no host fallback |
| D11 | Q10 owns Rush/compiler Containerfile/build/version checks (a) or F4 owns them (b) | Exact pinned image build/provisioning and OCI CI owner needed; no fabricated image |
| D12 | Extend strict unknown-key rejection beyond ten/REQUEST_MODEL_TOOLS here (a) or separately authorized plan (b) | Remaining-tools scope preserved, not silently omitted or drafted here |
| Q06 X1 | PatchSandboxManager worktree + run_engine from audit3195–3209, or W18 OCI | Separate choice from D2; compiler image/runtime only OCI branch |

Consumer-specific choices remain in their owning plans; this single-plan remediation neither approves nor deletes them. Development readiness remains blocked at the affected entry point until choices are recorded and Phase70 T1–T29/G0–G8 acceptance evidence exists.

## Shared ownership, deliverables and ordered integration
Foundation owner is sole writer of shared implementation files; Command owner supplies an exact patch row and never writes those paths. Separate worktrees do not solve shared ownership. Foundation owner is batch merge/integration owner, distinct from memory-program-contract.md's integration owner. All paths below are future implementation deliverables, not files edited during remediation.

| Owner / packet | Literal paths and responsibility |
|---|---|
| Foundation F1/F9/F10/F11 | src/rush/cli.py; src/rush/catalog.py; src/rush/config.py; src/rush/cli_support/catalog_commands.py; src/rush/cli_support/options.py; src/rush/mcp.py; src/rush/mcp_support/tool_registry.py; src/rush/mcp_support/request_models.py; src/rush/invocation/executor.py; tests/test_cli_registry.py; tests/test_mcp.py |
| Foundation F2/F3 and serialized Q02/Q04/F4 rows | src/rush/tools/routing.py; tests/test_routing.py; src/rush/tools/common.py; src/rush/engines/base.py; src/rush/runtime/subprocesses.py (Q02 selected_targets, Q04 preflight and F4-START opted-in host-child start evidence; preserve default ownership/cancel controls) |
| Foundation F4/F5 | src/rush/runtime/isolated_process.py; src/rush/runtime/isolated_tests.py; tests/test_subprocess_contract.py (F4-START); tests/test_isolated_process.py; tests/test_isolated_tests.py; tests/conftest.py; tests/test_no_skips.py; pyproject.toml markers; .github/workflows/ci.yml oci-isolation job |
| Foundation F6/F7 | tests/transport_parity.py; tests/test_transport_parity.py; src/rush/tools/sbom.py; tests/test_sbom.py |
| Foundation F8 | Every literal shared documentation/ADR/receipt path listed in F8, scripts/sync_docs.py for verified inventory integration only; command-authored doc content serialized in same packet |
| Command owner Q02 | src/rush/engines/ruff.py and src/rush/engines/globstar.py; Q03 Ruff-format M2 row applied here after Q02 R1 |
| Command owner Q03 | src/rush/runtime/filesystem.py; tests/test_format_parity.py; tests/test_prettier_honest.py; tests/test_format_oci.py; own format tool/engine/tests |
| Command owner Q07 | src/rush/tools/dead_probe_plugin.py; tests/test_vulture_reference.py; tests/test_knip_reference.py; tests/test_static_tools.py; tests/fixtures/engine_reports/knip-6.35.1.json; obsolete tests/fixtures/engine_reports/knip.txt deletion only under Q07 authorization |
| Other Command owners | Literal command-owned production/engine/test/ADR paths in README Roles and their own plans; none are edited by F00 remediation |

Ordered implementation route after separate authorization and resolved entry gates:
1. Verify Phase70 acceptance and selected shared choices. Apply F1–F3/F6 to current public signatures first; RED exact invalid grant/unknown-key/current-option tests, GREEN shared implementation and real parity. Future typed options are integrated only with their command signature patch, never registered before it exists.
2. Serialize Q02 R1 selected_targets shared rows through Foundation and Ruff implementation through Q02; Q03 M2 follows on that same Ruff owner. Run each packet's exact current-engine regressions. Preserve already-grounded Phase70 engine behavior rather than duplicating it.
3. Command owners apply R/E packets in separate worktrees with exact shared rows serialized. Consumer check sets are union of X-13 plus C-20, never replaced by F00's shorter shared set. F4/format OCI modules are absent until their owning packet creates them; do not name absent modules in earlier gates.
4. Apply F4/F5/F7 after their trust/runtime/image/ownership choices. Apply F4-START's exact src/rush/runtime/subprocesses.py patch and tests/test_subprocess_contract.py checks before isolated_process consumers pass start_evidence; default None calls retain the existing route. RED deterministic preflight/budget/timeout/cancellation/cleanup/count/digest branches; GREEN bodies here; run real OCI marker acceptance only with approved runtime and each pinned locally provisioned image.
5. Apply dependent X1 packets (Q09 has no OCI call); Q06 follows selected worktree/OCI route. Integrate F8 docs in each packet rather than deferring docs until batch end. Complete F9–F11 after signatures/options/catalog exist, then full shared, consumer and real OCI acceptance.

Required risks and stop conditions: unresolved user-owned behavior/owner; missing Phase70 acceptance; conflicting shared row/signature; unsupported annotation; untrusted runtime/malformed digest; launch budget insufficient for reserved cleanup; post-launch cleanup uncertainty; stale or escaping SBOM/artifact; missing/unpinned required image; docs inventory/historical-body drift; frozen reviewed bytes changed. These block affected implementation; they never authorize host execution, fake metrics, skipped live tests or scope reduction.

## F1 Typed option forwarding
CLI options for catalog commands are declared per tool in src/rush/cli_support/catalog_commands.py::_TOOL_CLI_OPTIONS (line 271), one click.Option per new typed __call__ parameter that is not a grant. The handwritten routes src/rush/cli.py::review (566) and ::format (615) declare theirs on the command. The seven --allow-* flags come only from cli_support/options.py::permission_options and are never redeclared. MCP schemas come from inspect.signature(tool.__call__) through mcp_support/tool_registry.py::make_tool_wrapper. Strict validation extends Phase 70 T6: mcp_support/request_models.py gains one pydantic model per command tool (create_model from the signature; extra forbidden; strict; booleans StrictBool, paths StrictStr, lists list[StrictStr], enums Literal), the ten tool names join REQUEST_MODEL_TOOLS through a new non-operation _ToolSpec kind. Build each model from make_tool_wrapper's public_sig (tool_registry.py:333-335), preserving project, result_view, limit, max_bytes, no_cache and allow_cache_write. _published emits flat properties, additionalProperties false, required ["path"], no operation/schema_version. validate_and_normalize returns ValidationOutcome(arguments=fields), as memory currently does (request_models.py:1071). Existing _reject non-memory envelope remains status error, raw.error.code INVALID_REQUEST, isError false. RushFastMCP.list_tools/call_tool (mcp.py:268-317) publish and validate through them; a rejected call uses that existing envelope with isError false. On the frozen implementation base config.py::resolve_tool_options is not used by these tools (only mutation, load, fuzz and contract call it). Q09's proposed project-style config route adds an explicit call after Q09-DOC-options registers rule_config_path; this is future behavior, grounded in report11908-12260, not a claim about current SlopTool.
Tests: tests/test_mcp.py::test_command_tools_reject_unknown_arguments sends {"__unknown": 1} to all ten commands and asserts rejection before dispatch; tests/test_mcp.py::test_command_tools_preserve_transport_options supplies project, result_view, limit, max_bytes, no_cache and allow_cache_write to each command and asserts accepted typed forwarding. tests/test_cli_registry.py::test_tool_cli_options_forward_typed_values drives each new option through real Click and asserts the typed value reaches the tool callable, with invalid values exiting 2 and zero tool calls; tests/test_mcp.py::test_command_tools_reject_non_boolean_grants sends "false", 0, 1, null, a list and an object for each grant and asserts rejection before dispatch.

## F2 Result contract
Per-engine evidence is metadata.engines; assessed coverage is metadata.scope v1; aggregate status is routing.aggregate_status (error > fail > warn > skipped > ok; ok with skipped is warn); CLI exit codes ok 0, skipped 0, warn 1, fail 1, error 2. Command evidence uses one command key per plan. metadata.aggregation exists only for review and is unchanged. No Q01-Q10 tool adds metadata.children or tool-owned metadata.partial. Existing workflows keep metadata.children (workflows/suites.py:314, workflows/project_run.py:1323); runtime/result_helpers.py::error_result preserves metadata.terminal_reason plus metadata.partial when terminal_reason is supplied. Lint and format record metadata.assessed_paths = {engine: [paths]} separately from engines/scope.
Helper, added to src/rush/tools/routing.py beside no_target_scope:
```python
def child_scope(
    coverage: str,
    *,
    reason: str | None = None,
    requested_targets: Sequence[str] = (),
    matched_file_count: int = 0,
    consumed_file_count: int = 0,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "files",
        "coverage": coverage,
        "reason": reason,
        "requested_targets": list(requested_targets),
        "matched_file_count": matched_file_count,
        "consumed_file_count": consumed_file_count,
    }
```
Each aggregating tool gives every child metadata["scope"] = child_scope(...) (complete for an engine that ran over its files, unavailable with reason engine_unavailable for a skipped engine, none with the row reason for a suite or input never assessed) and sets metadata["scope"] = routing.aggregate_scope(children). SecurityTool keeps its dependencies list: metadata["scope"] = {**routing.aggregate_scope(children), "dependencies": dependencies}.
An engine discovering its own inputs gets child_scope("unavailable", reason="engine_discovers_directory_contents") (runtime/subprocesses.py:1473), not invented scope. TestTool sets suite scopes itself: complete if at least one test collected; none with row reason if never run, zero collection or suite error. Slop error child gets unavailable/engine_error. Security inputs audited or resolved-for-this-audit contribute complete children; others contribute none with row state. Assessed plus unassessed gives partial and promotes clean ok to warn; only unassessed gives none/skipped. Knip directory discovery stays unavailable; Vulture explicit-file run is complete. Tests: tests/test_routing.py::test_child_scope_complete_plus_unavailable_aggregates_to_partial and command-owned exact input ledgers.

## F3 Grants, denials, empty scope, missing runtime
Grant convention: __call__ takes bool allow_* parameters (default False) and builds ExecutionPermissions once; run() keeps the convention it has on the base (SecurityTool, TestTool and SlopTool: permissions: ExecutionPermissions | None = None; TypecheckTool: allow_build and allow_cache_write, plus allow_slow) and every tool without grants gains permissions: ExecutionPermissions | None = None.
Whole-call missing grant: status skipped; summary "requires permission: --allow-<flag>[, ...]"; metadata.execution = build_execution_metadata("executed", requested=..., granted=..., extra={"disposition": "not_run", "cause": "permission_denied"}); zero spawns and writes; the operation block has status denied and reason build_or_slow_denied for build/slow refusal. Q02 minimization, Q05 trial and Q10 verification rows preserve base status/findings/scope on denied optional work, zero operation spawns. Q03 verify_preview_id, Q06 experiments, Q07 probe, Q08 trial and Q10 repair whole-call refusals return skipped. Preserve operation-specific network/artifact/cache grant requirements. Import function from rush.permissions; no ExecutionPermissions instance method exists.
Missing OCI runtime or image: aggregate status unchanged; the operation block has status skipped and reason isolation_unavailable; no host fallback.
Invalid argument: status error, metadata.error = {"code": "invalid_argument", "message": <summary text>}; routing.child_entry reports error.code as reason. MCP pre-dispatch rejection instead retains raw.error.code INVALID_REQUEST.
Empty scope: status skipped, metadata.scope.coverage none, metadata.scope.reason = the tool's existing reason (review no_reviewable_python_files, lint no_supported_targets) or no_dependency_inputs (security) or no_supported_targets (markdown).


Concrete F3 consumer contract (C10-C13). Current APIs are ExecutionPermissions, check_permissions, build_execution_metadata and skipped_result; no new permission API is proposed. F7's full SbomTool.run guard and test_sbom_denial_runs_nothing below are executable shared-policy example: check grants before mkdir/engine call, overwrite skipped_result's "skipped:" prefix with exact required summary, attach canonical executed/not_run metadata. Command owners put that same guard before their first denied operation effect, retaining their existing run signature and operation key.

| Consumer/cause | Aggregate status | Operation state/carrier | Effect |
| --- | --- | --- | --- |
| Q01 probe, Q03 verify_preview_id, Q04 minimization, Q06 experiments, Q07 probe, Q08 trial, Q10 repair: required grant missing | skipped | operation status denied; build/slow reason build_or_slow_denied; exact missing flag summary and execution cause permission_denied | zero denied-operation spawns, writes or provider calls; Q01 combined LLM/probe preflight precedes both providers |
| Q02 minimization, Q05 trial, Q10 verification: required grant missing | original base status | denied operation state; same grant carrier; base findings/scope unchanged | zero denied-operation spawns/writes |
| Any OCI operation: unsupported/untrusted runtime or unavailable verified local image before target | original base status | status skipped, reason isolation_unavailable | no host fallback; no target launch |
| Any OCI operation: post-launch cleanup cannot be confirmed | error for whole operation; optional consumer preserves base only when its explicit packet contract requires it | OSError-compatible IsolatedCleanupError; operation error, factual exc.receipt/container_name/process_launches | no isolation_unavailable claim or host fallback |
| Invalid public argument after transport normalization | error | metadata.error.code invalid_argument; metadata.error.message exactly result summary | zero operation effects after rejection |
| Malformed grants/unknown keys before dispatch | error ToolResult, MCP isError=False | raw.error.code INVALID_REQUEST | zero executor dispatch |
| No relevant inputs | skipped | scope.coverage none; existing per-tool reason retained | no assessed-count fabrication |

Grant sets remain command-owned, including network/artifact/cache requirements; this table does not approve new defaults or replace command-specific invalidation order. Missing runtime policy D6, aggregate/exit policy D5 and Q06 isolation choice remain unapproved. F2's actual routing test checks partial/warn under D5 proposal; a different approval requires one shared routing change, never ten local overrides. Detailed public behavior tests remain each command packet's responsibility; F7 denial test proves shared-policy implementation example only.
## F4 Isolation provider
File: src/rush/runtime/isolated_process.py (new).
```python
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.io.physical_paths import PhysicalRoot
from rush.runtime.subprocesses import (
    SubprocessCancelled,
    _OWNED_EXECUTION,
    _bounded_redacted_output,
    run_subprocess,
)


class IsolationUnavailable(RuntimeError):
    def __init__(self, message: str, *, process_launches: int = 0):
        super().__init__(message)
        self.process_launches = process_launches


class LaunchBudgetExhausted(RuntimeError):
    def __init__(self, process_launches: int):
        super().__init__("Isolated process launch budget exhausted")
        self.process_launches = process_launches


class IsolatedCleanupError(OSError):
    def __init__(
        self,
        container_name: str,
        receipt: dict[str, Any],
        *,
        stdout: str = "",
        stderr: str = "",
    ):
        super().__init__(f"Could not confirm removal of container {container_name}")
        self.container_name = container_name
        self.receipt = receipt
        self.process_launches = receipt["process_launches"]
        self.output = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class IsolatedRun:
    returncode: int
    stdout: str
    stderr: str
    process_launches: int
    receipt: dict[str, Any]


def check_isolation_inputs(root: Path, *, runtime_path: Path, image_ref: str) -> None:
    if os.name != "posix":
        raise IsolationUnavailable("OCI isolation requires POSIX")
    root = Path(root).resolve(strict=True)
    runtime_path = Path(runtime_path)
    if not runtime_path.is_absolute() or runtime_path.name not in {"docker", "podman"}:
        raise IsolationUnavailable("Runtime must be an absolute docker or podman path")
    try:
        resolved = runtime_path.resolve(strict=True)
        supplied_parent = runtime_path.parent
        physical_parent = supplied_parent.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise IsolationUnavailable(str(exc)) from exc
    if (
        supplied_parent.is_relative_to(root)
        or physical_parent.is_relative_to(root)
        or resolved.is_relative_to(root)
        or not stat.S_ISREG(info.st_mode)
        or not os.access(runtime_path, os.X_OK)
        or info.st_uid not in {0, os.getuid()}
        or info.st_mode & 0o022
    ):
        raise IsolationUnavailable("Runtime path is not trusted")
    if (
        not isinstance(image_ref, str)
        or re.fullmatch(r"[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}", image_ref) is None
    ):
        raise ValueError("Malformed image reference")


def run_isolated_argv(
    root: Path,
    scratch: Path,
    *,
    runtime_path: Path,
    image_ref: str,
    entrypoint: str,
    argv: list[str],
    timeout_s: int,
    workdir_rel: str = ".",
    environment: dict[str, str] | None = None,
    max_process_launches: int | None = None,
    scratch_on_pythonpath: bool = False,
) -> IsolatedRun:
    check_isolation_inputs(root, runtime_path=runtime_path, image_ref=image_ref)
    root, scratch = Path(root).resolve(strict=True), Path(scratch).resolve(strict=True)
    if not root.is_dir() or not scratch.is_dir():
        raise ValueError("root and scratch must be directories")
    if root.is_relative_to(scratch) or scratch.is_relative_to(root):
        raise ValueError("root and scratch must be physically disjoint")
    info = scratch.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("scratch must be caller-owned with mode 0700")
    if any(c in str(p) for p in (root, scratch) for c in ",\n\r"):
        raise ValueError("Mount paths cannot contain comma, newline or CR")
    workdir = PhysicalRoot(root).open_contained(workdir_rel)
    if not workdir.is_dir():
        raise ValueError("workdir must be a contained directory")
    if (
        not isinstance(entrypoint, str)
        or not entrypoint.startswith("/")
        or any(c in entrypoint for c in "\n\r\0")
        or not isinstance(argv, list)
        or any(not isinstance(a, str) or "\0" in a for a in argv)
        or type(timeout_s) is not int
        or timeout_s <= 0
        or type(scratch_on_pythonpath) is not bool
    ):
        raise ValueError("Invalid isolated invocation")
    env = {} if environment is None else environment
    if not isinstance(env, dict) or any(
        k not in {"SOURCE_DATE_EPOCH", "TZ", "LC_ALL"}
        or not isinstance(v, str)
        or any(c in v for c in "\n\r\0")
        for k, v in env.items()
    ):
        raise ValueError("Invalid isolated environment")
    if max_process_launches is not None and (
        type(max_process_launches) is not int or max_process_launches < 0
    ):
        raise ValueError("Invalid process launch budget")
    launches = 0
    name = "rush-" + uuid.uuid4().hex
    ambient = _OWNED_EXECUTION.get()
    owner, run_id = ambient if ambient is not None else (f"process:{os.getpid()}", name)
    runtime_sha = hashlib.sha256(Path(runtime_path).read_bytes()).hexdigest()
    mounts = [
        {"source": str(root), "destination": "/work", "read_only": True},
        {"source": str(scratch), "destination": "/out", "read_only": False},
    ]

    def receipt(
        code: int | None, stdout: str, stderr: str, cleaned: bool | None
    ) -> dict[str, Any]:
        return {
            "runtime_path": str(runtime_path),
            "runtime_sha256": runtime_sha,
            "image_ref": image_ref,
            "image_digest": image_ref.split("@", 1)[1],
            "mounts": mounts,
            "network": "none",
            "run_id": run_id,
            "owner_instance_id": owner,
            "exit_code": code,
            "output_sha256": hashlib.sha256((stdout + stderr).encode()).hexdigest(),
            "process_launches": launches,
            "container_name": name,
            "target_started": None,
            "target_launch_attempted": True,
            "cleanup_confirmed": cleaned,
            "ownership_source": "ambient" if ambient is not None else "caller_process",
        }

    def launch(args: list[str], *, cleanup: bool = False):
        nonlocal launches
        if (
            not cleanup
            and max_process_launches is not None
            and launches >= max_process_launches
        ):
            raise LaunchBudgetExhausted(launches)
        started = {"started": False}
        try:
            result = run_subprocess(
                [str(runtime_path), *args],
                cwd=root,
                timeout=10 if cleanup else timeout_s,
                env={"PATH": "/usr/bin:/bin"},
                start_evidence=started,
                **({"cancel_check": lambda: False} if cleanup else {}),
            )
        finally:
            launches += int(started["started"])
        if not started["started"] and not cleanup:
            raise IsolationUnavailable(
                "Runtime child did not start", process_launches=launches
            )
        return result

    try:
        inspected = launch(["image", "inspect", image_ref])
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsolationUnavailable(str(exc), process_launches=launches) from exc
    if inspected.returncode != 0:
        raise IsolationUnavailable(
            "Pinned local image is unavailable", process_launches=launches
        )
    try:
        images = json.loads(inspected.stdout)
        verified = (
            isinstance(images, list)
            and len(images) == 1
            and isinstance(images[0], dict)
            and image_ref in images[0].get("RepoDigests", [])
        )
    except (ValueError, TypeError):
        verified = False
    if not verified:
        raise IsolationUnavailable(
            "Local image digest could not be verified", process_launches=launches
        )
    # One run plus two unconditional cleanup calls must fit before target launch.
    if max_process_launches is not None and launches + 3 > max_process_launches:
        raise LaunchBudgetExhausted(launches)
    args = [
        "run",
        "--rm",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=512m",
        "--cpus=1",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={root},dst=/work,readonly",
        "--mount",
        f"type=bind,src={scratch},dst=/out",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--workdir",
        "/work"
        + ("/" + workdir.relative_to(root).as_posix() if workdir != root else ""),
    ]
    fixed_env = {
        "HOME": "/out",
        "PYTHONDONTWRITEBYTECODE": "1",
        "RUSH_CHECK_RECEIPT": "/out/checks.json",
        **({"PYTHONPATH": "/out"} if scratch_on_pythonpath else {}),
        **env,
    }
    for key, value in sorted(fixed_env.items()):
        args += ["--env", f"{key}={value}"]
    args += ["--entrypoint", entrypoint, image_ref, *argv]
    try:
        completed = launch(args)
    except (subprocess.TimeoutExpired, SubprocessCancelled, OSError) as exc:
        out, err = [
            _bounded_redacted_output(
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else (value or "")
            )
            for value in (getattr(exc, "output", ""), getattr(exc, "stderr", ""))
        ]
        exc.output, exc.stderr = out, err
        removed = absent = None
        try:
            removed = launch(["rm", "--force", name], cleanup=True)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            absent = launch(["container", "inspect", name], cleanup=True)
        except (OSError, subprocess.TimeoutExpired):
            pass
        # Missing inspect alone could mean an unavailable daemon. Require both.
        cleaned = (
            removed is not None
            and removed.returncode == 0
            and absent is not None
            and absent.returncode != 0
        )
        evidence = receipt(None, out, err, cleaned)
        if not cleaned:
            raise IsolatedCleanupError(name, evidence, stdout=out, stderr=err) from exc
        exc.receipt = evidence
        exc.process_launches = launches
        raise
    evidence = receipt(completed.returncode, completed.stdout, completed.stderr, None)
    # A runtime exit number alone does not establish whether target code started.
    evidence["target_started"] = None
    return IsolatedRun(
        completed.returncode, completed.stdout, completed.stderr, launches, evidence
    )
```
No-launch preflight: add check_isolation_inputs(root, *, runtime_path, image_ref) -> None. Runtime acceptance follows README D10; platform/runtime failures raise IsolationUnavailable first, malformed image raises ValueError second. No subprocess and no image inspect. run_isolated_argv calls it first; Q01 calls it before specialist invocation. Relative runtime values stay relative through CLI/MCP and raise IsolationUnavailable; runtime_path never joins _CWD_RELATIVE_ARGS or CLI abspath callbacks.

Behavior (audit 13824-13888):
- A non-POSIX platform, a non-absolute or non-executable runtime path, or a missing local image raises IsolationUnavailable before any target process. The image is inspected with `<runtime> image inspect <image_ref>` and never pulled.
- image_ref must match `[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}`; entrypoint must be an absolute path without newline, CR or NUL; argv must be a list of NUL-free strings; environment keys are limited to SOURCE_DATE_EPOCH, TZ and LC_ALL with newline-free values; violations raise ValueError.
- root and scratch must be physically disjoint directories: neither resolved path may contain the other. Reject root == scratch, scratch.is_relative_to(root), and root.is_relative_to(scratch) before image inspection. A writable /out parent must never expose the read-only project through another mount. scratch must be owned by caller with mode 0700 (no group/other bits); mount paths must contain no comma, newline or CR; workdir_rel is resolved with PhysicalRoot(root).open_contained (returns a validated Path, not an opened file).
- The run command is `<runtime> run --rm --name rush-<uuid> --pull=never --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=64 --memory=512m --cpus=1 --user <uid>:<gid> --mount type=bind,src=<root>,dst=/work,readonly --mount type=bind,src=<scratch>,dst=/out --tmpfs /tmp:rw,nosuid,nodev,size=64m --workdir <container workdir> --env HOME=/out --env PYTHONDONTWRITEBYTECODE=1 --env RUSH_CHECK_RECEIPT=/out/checks.json [--env PYTHONPATH=/out when scratch_on_pythonpath] <sorted env overrides> --entrypoint <entrypoint> <image_ref> <argv>`, executed with the Rush run_subprocess (no shell) with PATH=/usr/bin:/bin.
- On timeout, cancellation or runtime-call OSError after launch attempt, removal and inspection run with cancellation suppressed and reserved capacity. Confirmed removal re-raises original exception with receipt/process_launches attached; failed confirmation raises IsolatedCleanupError (OSError), carrying receipt and container name. No host fallback. Runtime exits 125-127 remain returned failures: number alone proves neither target execution nor nonexecution. Reconciles audit 13878-13884 with governing pre-target definition at 13810 and C09. Plan01 _run_claim_probe already catches OSError as probe_process_failed; other callers catch this OSError as operation error, retain exc.receipt, never relabel isolation_unavailable. target_started=None records uncertainty; target_launch_attempted=True records runtime run-call attempt, not proof of target invocation.
- Accounting: process_launches counts accepted host child starts proved by F4-START (image inspect, run, and timeout/cancellation rm and container inspect), including an owned bootstrap. This is not runtime-binary or container-target execution attestation. Failed Popen attempts count zero; exit 127 alone never identifies a failed start. Before target launch, reserve capacity for timeout rm plus inspect so a spent budget cannot leave a live container; unused cleanup reservations are released and only actual launches count. Each launch is reserved before it starts; if the next launch would exceed max_process_launches the call raises LaunchBudgetExhausted before launching it (never IsolationUnavailable). IsolationUnavailable means no target process ran.
- receipt keys: runtime_path, runtime_sha256, image_ref, image_digest, mounts, network "none", run_id, owner_instance_id, exit_code, output_sha256, process_launches. Mounts serialize exactly as Plan01 /work read_only=True and /out read_only=False rows. Hash preimage: exact returned bounded/redacted stdout+stderr, UTF-8. runtime_sha256 is a path-byte snapshot, accepted against explicit pre/post runtime-path hashes; equality does not attest transient executed binary bytes. Existing run_subprocess bounds returned text after capture; no capture-memory limit claimed. Ambient _OWNED_EXECUTION supplies executor identity when present; process:<pid>/container name otherwise identify caller process and invocation only, never durable executor registration. ownership_source makes distinction explicit. Proposed extras target_launch_attempted, target_started, cleanup_confirmed and container_name preserve factual cleanup state; nullable exit_code reserved for exceptions without observed exit.
Tests (real runtime and image from RUSH_TEST_OCI_RUNTIME and the plan's image variable; absence fails the gate, never skips): tests/test_isolated_process.py::test_container_denies_worktree_write_and_network, ::test_unavailable_runtime_runs_nothing, ::test_unpinned_image_rejected, ::test_launch_budget_exhausted_before_launch, ::test_receipt_fields, ::test_scratch_must_be_private, ::test_timeout_reaps_container, ::test_cancellation_reaps_container, ::test_runtime_name_allowlist, ::test_runtime_symlink_uses_supplied_name, ::test_runtime_group_world_writable_rejected, ::test_runtime_owner_rejected, ::test_runtime_inside_root_rejected (docs/docker), ::test_check_launches_nothing.
Marker patch rows (tests/conftest.py, pyproject.toml, tests/test_no_skips.py): add oci_isolation; _deselected_by gains has_oci bool and (oci_isolation, not has_oci), computed only from RUSH_TEST_OCI_RUNTIME. Unset runtime deselects, never skips; set runtime with missing/unpinned image fails. Every live OCI test has @pytest.mark.oci_isolation and asserts its image env var. CI .github/workflows/ci.yml oci-isolation job provisions pinned Python/Rush/compiler images, exports all four RUSH_TEST_* runtime/image vars and runs pytest tests -m oci_isolation -q. Image owner is README D11; no placeholder image/build step satisfies acceptance. Runtime absence locally does not close X1.


### F4-START — proposed opt-in child-start evidence
Prerequisite owned by F4 shared-runtime row: exact patch below in src/rush/runtime/subprocesses.py, grounded at Phase70 66c6c799 source SHA dc6b132dcfea7b5f00369b8df6dbb419d3d551754486105c416c31fb82611154. Apply before isolated_process.py consumers. Existing blocking FileNotFoundError returns CompletedProcess 127 without starting a child; proposed start_evidence distinguishes that from a child returning 127. Reset False on entry; set True only after successful direct or POSIX/Windows owned-gate Popen. None preserves existing blocking/cancellation/ownership behavior and call signatures. Opt-in uses existing cancellable route, not a new runner. Accepted owned-bootstrap start counts even if target execution never follows.
```diff
--- a/src/rush/runtime/subprocesses.py
+++ b/src/rush/runtime/subprocesses.py
@@ -587,6 +587,7 @@
     env: dict[str, str] | None,
     owner_instance_id: str,
     run_id: str,
+    start_evidence: dict[str, bool] | None = None,
 ) -> subprocess.Popen[str]:
     """Spawn the bootstrap gate in place of the real engine command, persist
     the `.procs` record, then release the gate -- in exactly that order.
@@ -608,6 +609,7 @@
             env=env,
             owner_instance_id=owner_instance_id,
             run_id=run_id,
+            **({"start_evidence": start_evidence} if start_evidence is not None else {}),
         )
 
     read_fd: int | None = None
@@ -621,6 +623,8 @@
             [_GATE_SHELL, "-c", _GATE_SCRIPT, "sh", *exec_argv],
             **{**popen_kwargs, "stdin": read_fd},
         )
+        if start_evidence is not None:
+            start_evidence["started"] = True
         # `start_new_session=True` makes the gate shell its own process-group
         # leader, and its pid survives its own later `exec`.
         _record_owned_process(owner_instance_id, run_id, proc.pid)
@@ -646,6 +650,7 @@
     env: dict[str, str] | None,
     owner_instance_id: str,
     run_id: str,
+    start_evidence: dict[str, bool] | None = None,
 ) -> subprocess.Popen[str]:
     """S03: there is no POSIX `exec`-equivalent process-image replacement on
     Windows, so the gate wrapper (`_WINDOWS_GATE_SCRIPT`, run under this same
@@ -699,6 +704,8 @@
                 "startupinfo": startupinfo,
             },
         )
+        if start_evidence is not None:
+            start_evidence["started"] = True
         job_name = _windows_job_name(proc.pid)
         job_handle = _create_kill_on_close_job(job_name)
         assigned = job_handle is not None and _assign_process_to_job(
@@ -864,6 +871,7 @@
     poll_interval: float = 0.05,
     owner_instance_id: str | None = None,
     run_id: str | None = None,
+    start_evidence: dict[str, bool] | None = None,
 ) -> subprocess.CompletedProcess[str]:
     """Run a list-only local child process without inheriting stdin.
 
@@ -885,6 +893,8 @@
     another process can reap it by. An unowned blocking call keeps today's
     exact `subprocess.run`-based kwargs and behavior, unchanged.
     """
+    if start_evidence is not None:
+        start_evidence["started"] = False
     if not argv or any(not isinstance(arg, str) for arg in argv):
         raise ValueError("argv must be a non-empty list of strings")
     if (owner_instance_id is None) != (run_id is None):
@@ -902,7 +912,7 @@
     exec_argv = _resolve_exec_argv(argv)
     _record_spawn(exec_argv, cwd)
 
-    if cancel_check is None and owner_instance_id is None:
+    if cancel_check is None and owner_instance_id is None and start_evidence is None:
         return _run_subprocess_blocking(
             exec_argv, argv, cwd=cwd, timeout=timeout, env=env
         )
@@ -916,6 +926,7 @@
         poll_interval=poll_interval,
         owner_instance_id=owner_instance_id,
         run_id=run_id,
+        **({"start_evidence": start_evidence} if start_evidence is not None else {}),
     )
 
 
@@ -1041,6 +1052,7 @@
     poll_interval: float,
     owner_instance_id: str | None = None,
     run_id: str | None = None,
+    start_evidence: dict[str, bool] | None = None,
 ) -> subprocess.CompletedProcess[str]:
     """P65-08: `Popen`-based poll loop used when a caller opts in with
     `cancel_check`, and (P69-01.2i) for every *owned* call, cancellable or
@@ -1058,10 +1070,13 @@
             env=env,
             owner_instance_id=owner_instance_id,
             run_id=run_id,
+            **({"start_evidence": start_evidence} if start_evidence is not None else {}),
         )
     else:
         try:
             proc = subprocess.Popen(exec_argv, **popen_kwargs)
+            if start_evidence is not None:
+                start_evidence["started"] = True
         except FileNotFoundError:
             return subprocess.CompletedProcess(
                 argv, 127, stdout="", stderr=f"{argv[0]}: command not found"
```
Proposed body added to existing tests/test_subprocess_contract.py; unexecuted. Existing subprocess-contract/ownership regressions remain required. F4 timeout/cancellation tests below assert four accepted starts including reserved cleanup.
```python
def test_start_evidence_distinguishes_missing_executable_and_exit127(
    tmp_path, monkeypatch
):
    import sys
    from contextvars import ContextVar
    from rush.runtime import subprocesses as sp

    monkeypatch.setattr(sp, "_OWNED_EXECUTION", ContextVar("test_owner", default=None))
    monkeypatch.setattr(sp, "_CANCEL_CHECK", ContextVar("test_cancel", default=None))
    evidence = {"started": True}
    missing = sp.run_subprocess(
        [str(tmp_path / "missing")],
        timeout=2,
        start_evidence=evidence,
    )
    assert missing.returncode == 127 and evidence == {"started": False}
    real = sp.run_subprocess(
        [sys.executable, "-c", "import sys; sys.exit(127)"],
        timeout=2,
        start_evidence=evidence,
    )
    assert real.returncode == 127 and evidence == {"started": True}
```
Exact proposed checks after both patches: env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_subprocess_contract.py::test_start_evidence_distinguishes_missing_executable_and_exit127 tests/test_isolated_process.py::test_receipt_fields tests/test_isolated_process.py::test_timeout_reaps_container tests/test_isolated_process.py::test_cancellation_reaps_container -q

Proposed tests for tests/test_isolated_process.py. Unit doubles exercise helper logic; real OCI body exercises actual container boundary. Unexecuted; F4 module and runtime-only deselection prerequisites.
```python
import subprocess
import sys
from pathlib import Path

import pytest

from rush.io.physical_paths import ContainmentError
from rush.runtime import isolated_process as ip
from rush.runtime import isolated_tests as it


@pytest.fixture
def isolated_case(tmp_path, monkeypatch):
    root, scratch = tmp_path / "root", tmp_path / "scratch"
    root.mkdir()
    scratch.mkdir(mode=0o700)
    runtime = tmp_path / "docker"
    runtime.symlink_to(sys.executable)
    image = "local/python@sha256:" + "a" * 64
    calls = []

    def fake(argv, **kwargs):
        kwargs["start_evidence"]["started"] = True
        calls.append((argv, kwargs))
        if argv[1:3] == ["image", "inspect"]:
            import json

            return subprocess.CompletedProcess(
                argv, 0, json.dumps([{"RepoDigests": [image]}]), ""
            )
        return subprocess.CompletedProcess(argv, 0, "1 passed in 0.01s\n", "")

    monkeypatch.setattr(ip, "run_subprocess", fake)
    return (
        root,
        scratch,
        dict(
            runtime_path=runtime,
            image_ref=image,
            entrypoint="/usr/local/bin/python",
            argv=["-c", "print(1)"],
            timeout_s=2,
            max_process_launches=4,
        ),
        calls,
    )


def test_check_launches_nothing(isolated_case):
    root, _, args, calls = isolated_case
    ip.check_isolation_inputs(
        root, runtime_path=args["runtime_path"], image_ref=args["image_ref"]
    )
    assert calls == []


def test_receipt_fields(isolated_case):
    import hashlib

    root, scratch, args, calls = isolated_case
    before_sha = hashlib.sha256(args["runtime_path"].read_bytes()).hexdigest()
    result = ip.run_isolated_argv(root, scratch, **args)
    after_sha = hashlib.sha256(args["runtime_path"].read_bytes()).hexdigest()
    assert result.receipt["runtime_sha256"] == before_sha == after_sha
    assert (
        len(calls) == result.process_launches == result.receipt["process_launches"] == 2
    )
    assert (
        result.receipt["output_sha256"]
        == hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest()
    )
    assert result.receipt["mounts"] == [
        {"source": str(root), "destination": "/work", "read_only": True},
        {"source": str(scratch), "destination": "/out", "read_only": False},
    ]
    assert result.receipt["image_digest"] == "sha256:" + "a" * 64
    assert result.receipt["network"] == "none"
    assert "--pull=never" in calls[1][0]
    assert calls[1][1]["env"] == {"PATH": "/usr/bin:/bin"}


@pytest.mark.parametrize("budget,expected_calls", [(0, 0), (1, 1), (2, 1), (3, 1)])
def test_launch_budget_exhausted_before_launch(isolated_case, budget, expected_calls):
    root, scratch, args, calls = isolated_case
    with pytest.raises(ip.LaunchBudgetExhausted) as caught:
        ip.run_isolated_argv(root, scratch, **{**args, "max_process_launches": budget})
    assert caught.value.process_launches == len(calls) == expected_calls


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("relative", ip.IsolationUnavailable),
        ("inside", ip.IsolationUnavailable),
        ("writable", ip.IsolationUnavailable),
        ("bad_name", ip.IsolationUnavailable),
        ("image", ValueError),
        ("scratch_mode", ValueError),
        ("overlap", ValueError),
    ],
)
def test_preflight_rejections_launch_nothing(isolated_case, mutation, error):
    root, scratch, args, calls = isolated_case
    if mutation == "relative":
        args["runtime_path"] = Path("docker")
    elif mutation == "inside":
        runtime = root / "docker"
        runtime.write_text("#!/bin/sh\nexit 0\n")
        runtime.chmod(0o700)
        args["runtime_path"] = runtime
    elif mutation == "writable":
        runtime = args["runtime_path"].parent / "podman"
        runtime.write_text("#!/bin/sh\nexit 0\n")
        runtime.chmod(0o777)
        args["runtime_path"] = runtime
    elif mutation == "bad_name":
        args["runtime_path"] = Path(sys.executable)
    elif mutation == "image":
        args["image_ref"] = "python:latest"
    elif mutation == "scratch_mode":
        scratch.chmod(0o755)
    else:
        scratch = root
    with pytest.raises(error):
        ip.run_isolated_argv(root, scratch, **args)
    assert calls == []


@pytest.mark.parametrize("cleanup_ok", [True, False])
@pytest.mark.parametrize(
    "payload", [b"caf\xc3\xa9\n", b"caf\xc3\xa9\n" + b"x" * 1_000_000]
)
def test_timeout_reaps_container(isolated_case, monkeypatch, cleanup_ok, payload):
    import hashlib

    root, scratch, args, calls = isolated_case
    base = ip.run_subprocess

    def timed(argv, **kwargs):
        kwargs["start_evidence"]["started"] = True
        if argv[1] == "run":
            calls.append((argv, kwargs))
            raise subprocess.TimeoutExpired(
                argv, 2, output=payload, stderr=b"err\xff\n"
            )
        if argv[1] in {"rm", "container"}:
            calls.append((argv, kwargs))
            assert kwargs["cancel_check"]() is False
            code = (
                (0 if cleanup_ok else 1)
                if argv[1] == "rm"
                else (1 if cleanup_ok else 0)
            )
            return subprocess.CompletedProcess(argv, code, "", "")
        return base(argv, **kwargs)

    monkeypatch.setattr(ip, "run_subprocess", timed)
    expected = subprocess.TimeoutExpired if cleanup_ok else ip.IsolatedCleanupError
    with pytest.raises(expected) as caught:
        ip.run_isolated_argv(root, scratch, **args)
    expected_out = ip._bounded_redacted_output(
        payload.decode("utf-8", errors="replace")
    )
    expected_err = "err\ufffd\n"
    assert len(calls) == caught.value.process_launches == 4
    assert caught.value.receipt["cleanup_confirmed"] is cleanup_ok
    assert caught.value.receipt["exit_code"] is None
    assert caught.value.receipt["target_started"] is None
    assert caught.value.output == expected_out and caught.value.stderr == expected_err
    assert expected_out.startswith("café\n")
    if len(payload) > 1_000_000:
        assert len(expected_out) < len(payload.decode("utf-8", errors="replace"))
    else:
        assert expected_out == "café\n"
    assert (
        caught.value.receipt["output_sha256"]
        == hashlib.sha256((expected_out + expected_err).encode("utf-8")).hexdigest()
    )


@pytest.mark.parametrize("cleanup_ok", [True, False])
def test_cancellation_reaps_container(isolated_case, monkeypatch, cleanup_ok):
    root, scratch, args, calls = isolated_case
    base = ip.run_subprocess

    def cancelled(argv, **kwargs):
        kwargs["start_evidence"]["started"] = True
        if argv[1] == "run":
            calls.append((argv, kwargs))
            raise ip.SubprocessCancelled(argv, 321)
        if argv[1] in {"rm", "container"}:
            calls.append((argv, kwargs))
            assert kwargs["cancel_check"]() is False
            code = (
                (0 if cleanup_ok else 1)
                if argv[1] == "rm"
                else (1 if cleanup_ok else 0)
            )
            return subprocess.CompletedProcess(argv, code, "", "")
        return base(argv, **kwargs)

    monkeypatch.setattr(ip, "run_subprocess", cancelled)
    expected = ip.SubprocessCancelled if cleanup_ok else ip.IsolatedCleanupError
    with pytest.raises(expected) as caught:
        ip.run_isolated_argv(root, scratch, **args)
    assert len(calls) == caught.value.process_launches == 4
    assert caught.value.receipt["cleanup_confirmed"] is cleanup_ok
    assert caught.value.receipt["exit_code"] is None
    assert caught.value.receipt["target_started"] is None
    assert caught.value.output == caught.value.stderr == ""


def test_unavailable_runtime_runs_nothing(isolated_case, monkeypatch):
    test_preflight_rejections_launch_nothing(
        isolated_case, "relative", ip.IsolationUnavailable
    )
    root, _, args, calls = isolated_case
    monkeypatch.setattr(ip.os, "name", "nt")
    with pytest.raises(ip.IsolationUnavailable):
        ip.check_isolation_inputs(
            root, runtime_path=args["runtime_path"], image_ref="bad"
        )
    assert calls == []


def test_unpinned_image_rejected(isolated_case):
    test_preflight_rejections_launch_nothing(isolated_case, "image", ValueError)


def test_scratch_must_be_private(isolated_case):
    test_preflight_rejections_launch_nothing(isolated_case, "scratch_mode", ValueError)


def test_runtime_name_allowlist(isolated_case):
    test_preflight_rejections_launch_nothing(
        isolated_case, "bad_name", ip.IsolationUnavailable
    )


def test_runtime_group_world_writable_rejected(isolated_case):
    test_preflight_rejections_launch_nothing(
        isolated_case, "writable", ip.IsolationUnavailable
    )


def test_runtime_inside_root_rejected(isolated_case):
    root, scratch, args, calls = isolated_case
    trusted_runtime = args["runtime_path"]
    external_target = trusted_runtime.resolve()
    assert not external_target.is_relative_to(root.resolve())
    test_preflight_rejections_launch_nothing(
        isolated_case, "inside", ip.IsolationUnavailable
    )
    args["runtime_path"] = trusted_runtime
    directory = root / "docs"
    directory.mkdir()
    supplied = directory / "docker"
    supplied.symlink_to(external_target)
    # Also reject an outside spelling whose supplied parent resolves into root.
    alias = root.parent / "runtime-parent-alias"
    alias.symlink_to(directory, target_is_directory=True)
    for runtime in (supplied, alias / "docker"):
        assert runtime.resolve() == external_target
        with pytest.raises(
            ip.IsolationUnavailable, match="Runtime path is not trusted"
        ):
            ip.check_isolation_inputs(
                root, runtime_path=runtime, image_ref=args["image_ref"]
            )
        with pytest.raises(
            ip.IsolationUnavailable, match="Runtime path is not trusted"
        ):
            ip.run_isolated_argv(root, scratch, **{**args, "runtime_path": runtime})
        assert calls == []


def test_runtime_symlink_uses_supplied_name(isolated_case):
    root, scratch, args, _ = isolated_case
    result = ip.run_isolated_argv(root, scratch, **args)
    assert result.receipt["runtime_path"] == str(args["runtime_path"])
    assert args["runtime_path"].name == "docker"


def test_runtime_owner_rejected(isolated_case, monkeypatch):
    import os
    from types import SimpleNamespace

    root, _, args, calls = isolated_case
    resolved = args["runtime_path"].resolve()
    original = Path.stat

    def stat_path(path, *a, **kw):
        info = original(path, *a, **kw)
        if path == resolved:
            return SimpleNamespace(st_mode=info.st_mode, st_uid=os.getuid() + 100000)
        return info

    monkeypatch.setattr(Path, "stat", stat_path)
    with pytest.raises(ip.IsolationUnavailable):
        ip.check_isolation_inputs(
            root, runtime_path=args["runtime_path"], image_ref=args["image_ref"]
        )
    assert calls == []


@pytest.mark.oci_isolation
def test_container_denies_worktree_write_and_network(tmp_path):
    import json
    import os

    root, scratch = tmp_path / "work", tmp_path / "out"
    root.mkdir()
    scratch.mkdir(mode=0o700)
    image = os.environ["RUSH_TEST_PYTHON_IMAGE"]
    runtime = Path(os.environ["RUSH_TEST_OCI_RUNTIME"])
    script = """
import json, socket
from pathlib import Path
denied = False
try:
    Path('/work/forbidden').write_text('must not appear')
except OSError:
    denied = True
Path('/out/permitted').write_text('owned output')
print(json.dumps({'write_denied': denied, 'interfaces': [name for _, name in socket.if_nameindex()]}))
"""
    result = ip.run_isolated_argv(
        root,
        scratch,
        runtime_path=runtime,
        image_ref=image,
        entrypoint="/usr/local/bin/python",
        argv=["-c", script],
        timeout_s=30,
        max_process_launches=4,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"write_denied": True, "interfaces": ["lo"]}
    assert not (root / "forbidden").exists()
    assert (scratch / "permitted").read_text() == "owned output"
```

Concrete marker/CI rows (proposed, unexecuted). _deselected_by keeps default has_oci=False for existing callers; collection passes runtime presence explicitly. tests/test_no_skips.py retains existing _Item/_CONFTEST/pytest fixtures. No image availability participates in deselection.
```diff
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ _deselected_by keyword parameters
     which: Callable[[str], str | None],
+    has_oci: bool = False,
@@ _deselected_by marker loop
         ("posix_nonroot", is_windows or is_root),
+        ("oci_isolation", not has_oci),
@@ _DESELECT_REASONS
     "posix_nonroot": "Windows or root",
+    "oci_isolation": "RUSH_TEST_OCI_RUNTIME is unset",
@@ pytest_collection_modifyitems
             which=which,
+            has_oci=bool(os.environ.get("RUSH_TEST_OCI_RUNTIME")),
--- a/pyproject.toml
+++ b/pyproject.toml
@@
 markers = [
+    "oci_isolation: real OCI acceptance; deselect only when RUSH_TEST_OCI_RUNTIME is unset",
```
```python
@pytest.mark.parametrize(
    "runtime_present,expected",
    [
        (False, "oci_isolation"),
        (True, None),
    ],
)
def test_oci_deselection_depends_only_on_runtime(runtime_present, expected):
    from conftest import _deselected_by

    item = _Item("oci_isolation")
    assert (
        _deselected_by(
            item,
            is_windows=False,
            is_linux_x86_64=True,
            is_root=False,
            which=lambda _: None,
            has_oci=runtime_present,
        )
        == expected
    )


def test_runtime_present_missing_image_fails(pytester, monkeypatch):
    monkeypatch.setenv("RUSH_TEST_OCI_RUNTIME", "/usr/bin/docker")
    monkeypatch.delenv("RUSH_TEST_PYTHON_IMAGE", raising=False)
    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile("""
import os, pytest
@pytest.mark.oci_isolation
def test_requires_image():
    assert os.environ["RUSH_TEST_PYTHON_IMAGE"]
""")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-q")
    result.assert_outcomes(failed=1)
    assert "KeyError" in result.stdout.str()
```
Add following job under existing jobs in .github/workflows/ci.yml only after D11 supplies approved immutable images. Those images must contain verified /usr/local/bin/python+pytest, Rush CLI, and Q06 toolchain respectively. Registry pulls occur only in explicit CI provisioning; runtime never pulls. Values below are required repository variables, not placeholders or approved selections. This job remains blocked by D11 and compiler-image/Q06 choice; if Q06 selects worktree, remove only compiler provisioning requirement through that decision's recorded patch. Existing action versions retained.
```yaml
  oci-isolation:
    name: Real OCI isolation acceptance
    runs-on: ubuntu-latest
    env:
      RUSH_TEST_OCI_RUNTIME: /usr/bin/docker
      RUSH_TEST_PYTHON_IMAGE: ${{ vars.RUSH_TEST_PYTHON_IMAGE }}
      RUSH_TEST_RUSH_IMAGE: ${{ vars.RUSH_TEST_RUSH_IMAGE }}
      RUSH_TEST_COMPILER_IMAGE: ${{ vars.RUSH_TEST_COMPILER_IMAGE }}
    steps:
      - uses: actions/checkout@v7.0.1
      - uses: actions/setup-python@v7.0.0
        with:
          python-version-file: .python-version
      - uses: astral-sh/setup-uv@v10.0.1
      - run: uv sync --all-extras --frozen
      - name: Provision approved immutable images
        shell: bash
        run: |
          set -euo pipefail
          for image in "$RUSH_TEST_PYTHON_IMAGE" "$RUSH_TEST_RUSH_IMAGE" "$RUSH_TEST_COMPILER_IMAGE"; do
            [[ "$image" =~ ^[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]
            docker pull "$image"
            docker image inspect "$image" >/dev/null
          done
      - name: Run every real OCI acceptance test
        run: env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests -m oci_isolation -q
```
## F5 Selected-test helper
File: src/rush/runtime/isolated_tests.py (new).
```python
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rush.io.physical_paths import PhysicalRoot
from rush.runtime.isolated_process import IsolatedRun, run_isolated_argv


@dataclass(frozen=True)
class SelectedTestRun:
    outcome: Literal["passed", "failed", "no_tests", "error"]
    counts: dict[str, int]
    argv: list[str]
    process_launches: int
    isolated: IsolatedRun


def run_selected_tests_isolated(
    root: Path,
    scratch: Path,
    *,
    nodes: list[str],
    runtime_path: Path,
    image_ref: str,
    python_entrypoint: str,
    timeout_s: int,
    max_process_launches: int | None = None,
    extra_pytest_args: tuple[str, ...] = (),
    scratch_on_pythonpath: bool = False,
) -> SelectedTestRun:
    physical = PhysicalRoot(Path(root))
    if (
        not isinstance(nodes, list)
        or not nodes
        or any(
            not isinstance(n, str) or not n or n.startswith("-") or "\0" in n
            for n in nodes
        )
        or len(set(nodes)) != len(nodes)
    ):
        raise ValueError("nodes must be unique contained pytest node IDs")
    for node in nodes:
        path = physical.open_contained(node.split("::", 1)[0])
        if not path.is_file():
            raise ValueError("Each pytest node must name an existing file")
    if not isinstance(extra_pytest_args, tuple) or any(
        not isinstance(arg, str) or "\0" in arg for arg in extra_pytest_args
    ):
        raise ValueError("Invalid extra pytest arguments")
    argv = ["-m", "pytest", "-q", "--tb=line", *extra_pytest_args, *nodes]
    isolated = run_isolated_argv(
        root,
        scratch,
        runtime_path=runtime_path,
        image_ref=image_ref,
        entrypoint=python_entrypoint,
        argv=argv,
        timeout_s=timeout_s,
        max_process_launches=max_process_launches,
        scratch_on_pythonpath=scratch_on_pythonpath,
    )
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    summary = None
    for line in reversed(isolated.stdout.splitlines()):
        stripped = line.strip("= ")
        if re.search(r"\bin \d+(?:\.\d+)?s\b", stripped):
            if re.search(
                r"\b(?:passed|failed|skipped|errors?|no tests ran)\b", stripped
            ):
                summary = stripped
                break
    outcome = {0: "passed", 1: "failed", 5: "no_tests"}.get(
        isolated.returncode, "error"
    )
    if summary is None:
        outcome = "error"
    else:
        for number, name in re.findall(
            r"(\d+)\s+(passed|failed|skipped|errors?)\b", summary
        ):
            counts["error" if name in {"error", "errors"} else name] += int(number)
    return SelectedTestRun(outcome, counts, argv, isolated.process_launches, isolated)
```
argv = ["-m", "pytest", "-q", "--tb=line", *extra_pytest_args, *nodes] (Q04's oracle argv). SelectedTestRun carries outcome (passed | failed | no_tests | error), counts {passed, failed, skipped, error} parsed from pytest's final -q summary line, argv, process_launches and the IsolatedRun. Outcome from the return code: 0 passed (skipped tests are reported in counts), 1 failed, 5 no_tests, anything else or a missing summary line error. nodes are validated: non-empty list of strings, unique, none starting with "-", no NUL, each path component contained in root. python_entrypoint is the image's verified absolute Python path.
Users: Q03 (verification_tests), Q04 (_run_target_oracle), Q05 (dependency_tests), Q07 (probe_tests with extra_pytest_args plus scratch_on_pythonpath for its plugin), Q08 (verification_tests).
Tests: tests/test_isolated_tests.py::test_outcome_by_exit_code, ::test_node_validation_rejects_options_and_escapes. Counts are asserted in every parameterized test_outcome_by_exit_code case.


Proposed tests for tests/test_isolated_tests.py (unexecuted; F4/F5 prerequisites):
```python
import pytest
from pathlib import Path
from rush.io.physical_paths import ContainmentError
from rush.runtime import isolated_process as ip
from rush.runtime import isolated_tests as it


@pytest.mark.parametrize(
    "code,summary,outcome,counts",
    [
        (
            0,
            "2 passed, 1 skipped in 0.02s",
            "passed",
            {"passed": 2, "failed": 0, "skipped": 1, "error": 0},
        ),
        (
            1,
            "1 failed, 2 passed in 0.02s",
            "failed",
            {"passed": 2, "failed": 1, "skipped": 0, "error": 0},
        ),
        (
            5,
            "no tests ran in 0.02s",
            "no_tests",
            {"passed": 0, "failed": 0, "skipped": 0, "error": 0},
        ),
        (
            2,
            "1 error in 0.02s",
            "error",
            {"passed": 0, "failed": 0, "skipped": 0, "error": 1},
        ),
        (0, "", "error", {"passed": 0, "failed": 0, "skipped": 0, "error": 0}),
    ],
)
def test_outcome_by_exit_code(tmp_path, monkeypatch, code, summary, outcome, counts):
    (tmp_path / "test_a.py").write_text("def test_a(): assert True\n")
    seen = []

    def fake(root, scratch, **kwargs):
        seen.append(kwargs)
        return ip.IsolatedRun(code, summary + "\n", "", 2, {})

    monkeypatch.setattr(it, "run_isolated_argv", fake)
    result = it.run_selected_tests_isolated(
        tmp_path,
        tmp_path.parent / "scratch",
        nodes=["test_a.py::test_a"],
        runtime_path=Path("/usr/bin/docker"),
        image_ref="pin",
        python_entrypoint="/usr/bin/python",
        timeout_s=30,
        extra_pytest_args=("-p", "probe_plugin"),
        scratch_on_pythonpath=True,
    )
    assert result.outcome == outcome and result.counts == counts
    assert seen[0]["argv"] == [
        "-m",
        "pytest",
        "-q",
        "--tb=line",
        "-p",
        "probe_plugin",
        "test_a.py::test_a",
    ]
    assert seen[0]["scratch_on_pythonpath"] is True


@pytest.mark.parametrize(
    "nodes",
    [
        [],
        ["--collect-only"],
        ["../escape.py"],
        ["/tmp/test.py"],
        ["test_a.py", "test_a.py"],
        ["test_a.py\0"],
    ],
)
def test_node_validation_rejects_options_and_escapes(tmp_path, monkeypatch, nodes):
    (tmp_path / "test_a.py").write_text("def test_a(): assert True\n")
    calls = []
    monkeypatch.setattr(it, "run_isolated_argv", lambda *a, **kw: calls.append(kw))
    with pytest.raises((ValueError, ContainmentError)):
        it.run_selected_tests_isolated(
            tmp_path,
            tmp_path.parent / "scratch",
            nodes=nodes,
            runtime_path=Path("/usr/bin/docker"),
            image_ref="pin",
            python_entrypoint="/usr/bin/python",
            timeout_s=30,
        )
    assert calls == []
```
## F6 Transport parity helper
Files: tests/transport_parity.py (helper module) and tests/test_transport_parity.py (self-test running one real command through both transports). Command test modules use `from transport_parity import run_cli, run_mcp` under pytest's tests-directory import path; do not assume tests is an importable package.
```python
import asyncio, json, os, subprocess, sys, tempfile
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[1]


def _transport_env():
    # Fresh per call: tests set/delete credentials after importing this module.
    return {**os.environ, "PYTHONPATH": str(REPO / "src")}


def run_cli(command, path, cli_options=(), timeout=180):
    proc = subprocess.run(
        [sys.executable, "-m", "rush.cli", command, str(path), *cli_options, "--json"],
        cwd=REPO,
        env=_transport_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.stdout.strip(), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def run_mcp(tool, arguments, timeout=180, schema_check=None, expect_tool_error=False):
    async def go():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"],
            cwd=str(REPO),
            env=_transport_env(),
        )
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as err:
            async with stdio_client(params, errlog=err) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    if schema_check:
                        schemas = {
                            t.name: t.inputSchema
                            for t in (await session.list_tools()).tools
                        }
                        schema_check(schemas[tool])
                    response = await session.call_tool(tool, arguments)
                    assert response.isError is expect_tool_error
                    return json.loads(response.content[0].text)

    return asyncio.run(asyncio.wait_for(go(), timeout))
```
Exit codes by status: ok 0, skipped 0, warn 1, fail 1, error 2. A real-file errlog is required on Windows (tests/test_mcp.py:258-262).


Proposed tests/test_transport_parity.py bodies. Unexecuted; F1/F6 and proposed review behavior must exist. SDK initialize/list_tools/call_tool route remains real stdio with real-file errlog. Environment test proves call-time credential control; real review test separately checks CLI/MCP behavior, excluding nondeterministic duration.
```python
import json
import subprocess

from transport_parity import _transport_env, run_cli, run_mcp


def test_transport_env_uses_current_controlled_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    assert _transport_env()["OPENAI_API_KEY"] == "test-only"
    monkeypatch.delenv("OPENAI_API_KEY")
    assert "OPENAI_API_KEY" not in _transport_env()
    assert "PYTHONPATH" in _transport_env()


def test_transport_parity_real_review(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    target = tmp_path / "sample.py"
    target.write_text(
        '"""Small fixture."""\ndef increment(value):\n    """Increment input."""\n    return value + 1\n'
    )
    exit_code, cli = run_cli("review", target)
    mcp = run_mcp("rush_review", {"path": str(target)})
    assert exit_code == 0
    assert cli["status"] == mcp["status"] == "ok"
    assert cli["findings"] == mcp["findings"] == []
    for key in ("tool", "engine", "engine_version", "status", "summary", "findings"):
        assert cli[key] == mcp[key]
```
## F7 SBOM consumer (Q18, audit 6664-6683)
src/rush/tools/sbom.py gains read_verified_sbom(path, expected_sha256, *, root): open the path with PhysicalRoot(root).open_contained(relative, purpose="read"); require expected_sha256 to match [0-9a-f]{64}; compare the sha256 of the bytes and raise ValueError on mismatch; parse JSON and require bomFormat "CycloneDX", specVersion in {"1.5","1.6"} and a components list of dicts each with a non-empty string name, else ValueError. SbomTool returns metadata.sbom = {path, sha256, component_count, unversioned_components, inventory_empty, fresh_output}. Q05 reads sbom_path and sbom_sha256 only through this function; any ValueError makes the SBOM-based reachability rows unknown_reachability.
Tests: tests/test_sbom.py::test_read_verified_sbom_accepts_matching_digest, ::test_read_verified_sbom_rejects_mismatch_and_malformed.


Concrete F7 patch: add reader/decoder at module scope and replace only SbomTool.run with body below (retain current __call__, module imports and grant forwarding). Current Phase70 run publishes stale/failed output; audit Q18 producer is required same F7 packet, not a new feature. Decoder shared by producer and consumer. Existing .common supplies now_ms, elapsed_ms, error_result and run_engine. Unexecuted.
```python
import hashlib
import json
import re
from pathlib import Path

from rush.io.physical_paths import PhysicalRoot


def _decode_sbom(raw: bytes) -> dict:
    document = json.loads(raw)
    components = document.get("components") if isinstance(document, dict) else None
    if (
        not isinstance(document, dict)
        or document.get("bomFormat") != "CycloneDX"
        or document.get("specVersion") not in {"1.5", "1.6"}
        or not isinstance(components, list)
        or any(
            not isinstance(c, dict)
            or not isinstance(c.get("name"), str)
            or not c["name"]
            for c in components
        )
    ):
        raise ValueError("unsupported or malformed CycloneDX")
    return document


def read_verified_sbom(path, expected_sha256, *, root):
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise ValueError("Invalid SBOM digest")
    root = Path(root).resolve(strict=True)
    relative = Path(path)
    if relative.is_absolute():
        relative = relative.relative_to(root)
    contained = PhysicalRoot(root).open_contained(relative, purpose="read")
    raw = contained.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("SBOM digest mismatch")
    return _decode_sbom(raw)
```
```python
def run(
    self, path, *, output_path=None, overwrite=False, config=None, permissions=None
):
    import hashlib, os, tempfile
    from ..engines import ENGINES
    from .common import skipped_result
    from ..permissions import (
        ExecutionPermissions,
        check_permissions,
        build_execution_metadata,
    )
    from ..io.physical_paths import ContainmentError, PhysicalRoot

    required = ExecutionPermissions(artifact_write=True)
    start = now_ms()
    allowed, missing = check_permissions(required, permissions)
    if not allowed:
        result = skipped_result(self.name, "cdxgen", ", ".join(missing))
        result["summary"] = "requires permission: " + ", ".join(missing)
        result["metadata"] = {
            "execution": build_execution_metadata(
                "executed",
                requested=required,
                granted=permissions,
                extra={"disposition": "not_run", "cause": "permission_denied"},
            )
        }
        return result
    if type(overwrite) is not bool:
        return error_result(self.name, "cdxgen", "overwrite must be boolean")
    root = (path if path.is_dir() else path.parent).absolute()
    physical = PhysicalRoot(root)
    requested = Path(output_path) if output_path is not None else Path("rush-sbom.json")
    try:
        # Preserve the existing public absolute-path contract while validating
        # only a root-relative path through PhysicalRoot.
        if requested.is_absolute():
            requested = requested.relative_to(root)
        output = physical.open_contained(requested, purpose="write")
        if output.exists() and not overwrite:
            return error_result(self.name, "cdxgen", "output already exists")
        if not output.parent.is_dir():
            return error_result(self.name, "cdxgen", "output parent absent")
        runs = physical.open_contained(".rush/runs", purpose="write")
        runs.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sbom-", dir=runs) as folder:
            fresh = Path(folder) / "bom.json"
            result = run_engine(
                ENGINES["cdxgen"],
                path,
                [
                    "--output",
                    str(fresh),
                    "--spec-version",
                    "1.6",
                    "--no-install-deps",
                    "--fail-on-error",
                ],
                tool_name=self.name,
                permissions=permissions,
                required_permissions=required,
            )
            result.pop("artifacts", None)
            if result["status"] != "ok":
                return result
            if fresh.is_symlink() or not fresh.is_file():
                return error_result(self.name, "cdxgen", "fresh output missing")
            raw = fresh.read_bytes()
            document = _decode_sbom(raw)
            components = document["components"]
            if (
                document.get("bomFormat") != "CycloneDX"
                or document.get("specVersion") not in {"1.5", "1.6"}
                or not isinstance(components, list)
                or any(
                    not isinstance(c, dict)
                    or not isinstance(c.get("name"), str)
                    or not c["name"]
                    for c in components
                )
            ):
                return error_result(
                    self.name, "cdxgen", "unsupported or malformed CycloneDX"
                )
            # Unknown versions remain explicit; an SBOM component may legitimately
            # omit version. Never manufacture one or call it verified.
            unidentified = sum(
                not isinstance(c.get("version"), str) or not c["version"]
                for c in components
            )
            output = physical.open_contained(requested, purpose="write")
            if overwrite:
                os.replace(fresh, output)
            else:
                # Atomic no-clobber publish; another writer cannot be overwritten.
                os.link(fresh, output)
                fresh.unlink()
            result["artifacts"] = [str(output)]
            result.setdefault("metadata", {})["execution"] = build_execution_metadata(
                "artifact",
                requested=required,
                granted=permissions,
                producer="cdxgen",
                producer_version=result.get("engine_version"),
                declared_artifact=str(output),
            )
            result.setdefault("metadata", {})["sbom"] = {
                "path": str(output),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "component_count": len(components),
                "unversioned_components": unidentified,
                "inventory_empty": not components,
                "fresh_output": True,
            }
            result["status"] = "warn" if unidentified or not components else "ok"
            result["summary"] = f"SBOM validated: {len(components)} components"
            result["duration_ms"] = elapsed_ms(start)
            return result
    except (ContainmentError, OSError, ValueError, TypeError, AttributeError) as exc:
        return error_result(
            self.name, "cdxgen", f"SBOM output rejected: {type(exc).__name__}"
        )
```
Proposed tests/test_sbom.py additions, including F3 real public-tool denial route:
```python
import hashlib
import json
from pathlib import Path

import pytest

from rush.io.physical_paths import ContainmentError
from rush.permissions import ExecutionPermissions
from rush.tools import sbom


@pytest.fixture
def sbom_case(tmp_path, monkeypatch):
    calls = []
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [{"name": "sample", "version": "1.0"}],
    }

    def produce(engine, path, argv, **kwargs):
        calls.append(argv)
        Path(argv[argv.index("--output") + 1]).write_text(json.dumps(document))
        return {
            "tool": "sbom",
            "engine": "cdxgen",
            "engine_version": "1",
            "status": "ok",
            "duration_ms": 0,
            "summary": "generated",
            "findings": [],
            "raw": None,
        }

    monkeypatch.setattr(sbom, "run_engine", produce)
    return tmp_path, calls, document


def test_read_verified_sbom_accepts_matching_digest(sbom_case):
    root, calls, _ = sbom_case
    result = sbom.SbomTool().run(
        root, permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "ok" and len(calls) == 1
    record = result["metadata"]["sbom"]
    output = Path(record["path"])
    assert record == {
        "path": str(root / "rush-sbom.json"),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "component_count": 1,
        "unversioned_components": 0,
        "inventory_empty": False,
        "fresh_output": True,
    }
    assert sbom.read_verified_sbom(output, record["sha256"], root=root)[
        "components"
    ] == [{"name": "sample", "version": "1.0"}]


@pytest.mark.parametrize(
    "contents,digest",
    [
        (b"not json", None),
        (b"{}", None),
        (b'{"bomFormat":"CycloneDX","specVersion":"1.6","components":[{}]}', None),
        (b'{"bomFormat":"CycloneDX","specVersion":"1.6","components":[]}', "0" * 64),
    ],
)
def test_read_verified_sbom_rejects_mismatch_and_malformed(tmp_path, contents, digest):
    output = tmp_path / "bom.json"
    output.write_bytes(contents)
    with pytest.raises(ValueError):
        sbom.read_verified_sbom(
            output, digest or hashlib.sha256(contents).hexdigest(), root=tmp_path
        )


def test_sbom_denial_runs_nothing(sbom_case):
    root, calls, _ = sbom_case
    result = sbom.SbomTool().run(root)
    assert result["status"] == "skipped"
    assert result["summary"] == "requires permission: --allow-artifact-write"
    execution = result["metadata"]["execution"]
    assert execution["mode"] == "executed"
    assert (
        execution["disposition"] == "not_run"
        and execution["cause"] == "permission_denied"
    )
    assert execution["requested_permissions"]["artifact_write"] is True
    assert execution["granted_permissions"]["artifact_write"] is False
    assert calls == [] and not (root / ".rush").exists()


def test_sbom_no_clobber_race_preserves_existing_output(sbom_case, monkeypatch):
    root, calls, _ = sbom_case
    original = sbom.run_engine
    output = root / "rush-sbom.json"

    def racing(*args, **kwargs):
        result = original(*args, **kwargs)
        output.write_bytes(b"other writer")
        return result

    monkeypatch.setattr(sbom, "run_engine", racing)
    result = sbom.SbomTool().run(
        root, permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "error"
    assert output.read_bytes() == b"other writer"
    assert "artifacts" not in result and len(calls) == 1


@pytest.mark.parametrize("fresh,status", [(False, "ok"), (True, "error")])
def test_sbom_never_publishes_stale_or_failed_output(
    sbom_case, monkeypatch, fresh, status
):
    root, calls, _ = sbom_case

    def engine(engine, path, argv, **kwargs):
        calls.append(argv)
        if fresh:
            Path(argv[argv.index("--output") + 1]).write_bytes(b"{}")
        return {
            "tool": "sbom",
            "engine": "cdxgen",
            "engine_version": None,
            "status": status,
            "duration_ms": 0,
            "summary": "engine error",
            "findings": [],
            "raw": None,
            "artifacts": ["stale"],
        }

    monkeypatch.setattr(sbom, "run_engine", engine)
    result = sbom.SbomTool().run(
        root, permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "error" and "artifacts" not in result
    assert not (root / "rush-sbom.json").exists()


@pytest.mark.parametrize("components,unversioned", [([], 0), ([{"name": "sample"}], 1)])
def test_sbom_incomplete_inventory_is_explicit(sbom_case, components, unversioned):
    root, _, document = sbom_case
    document["components"] = components
    result = sbom.SbomTool().run(
        root, permissions=ExecutionPermissions(artifact_write=True)
    )
    assert result["status"] == "warn"
    assert result["metadata"]["sbom"]["unversioned_components"] == unversioned
    assert result["metadata"]["sbom"]["inventory_empty"] is (not components)


def test_sbom_reader_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"{}")
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked.json").symlink_to(outside)
    with pytest.raises(ContainmentError):
        sbom.read_verified_sbom(
            "linked.json", hashlib.sha256(b"{}").hexdigest(), root=root
        )
```
## F8 Foundation-owned documentation (same packet as the change)
- docs/safety/permissions.md: Foundation applies all table rows 11-17 together, using command-owned doc patch rows. Per-operation grant table (review LLM network; probe, minimization and trial build+slow plus artifact_write or network where stated; format preview and apply artifact_write; Q06 cache_write) and the F3 vocabulary.
- docs/adr/0050-oci-isolation-provider.md (new): F4 contract and why Git worktree is not process isolation (audit 13810). Foundation F8-HISTORY row changes only leading Current status paragraph of docs/adr/README.md to list ADRs 0050-0057 and subjects from README Order; only leading Current status paragraph of docs/adr/0007-slow-network-and-destructive-permissions.md gains pointer to permissions table. Historical bodies remain byte-identical. Each new ADR gains current/maintainers coverage entry via Q01-21 receipt-regeneration patch. No appended historical index/table row.
- docs/safety/security-model.md: the OCI boundary (--pull=never, --network=none, read-only /work, writable /out, 64 pids, 512m, 1 cpu).
- docs/reference/environment-variables.md: RUSH_TEST_OCI_RUNTIME, RUSH_TEST_PYTHON_IMAGE, RUSH_TEST_RUSH_IMAGE, RUSH_TEST_COMPILER_IMAGE (Q06 OCI choice only), RUSH_TEST_VITEST_PROJECT.
- docs/developer/{testing-guide,tool-development,mcp-development,source-tree}.md: real-OCI acceptance and the no-skip rule, tests/transport_parity.py, the F2 contract and child_scope, request_models strict models, new runtime modules.
- docs/user-guide/understanding-results.md: operation blocks and their statuses.
- Every packet that changes an option, parameter, ToolSpec or engine updates docs/reference/{cli,mcp-tool,result}-reference.md, the contract block in docs/reports/phase-64-66-documentation-coverage.md, and CHANGELOG.md so `scripts/sync_docs.py --check` exits 0. These overlapping files and shared user guides are serialized Foundation-owned patch rows; command owner supplies exact content and integration remains in the same packet.


Concrete F8 documentation rows (proposed; apply only in packet that implements accepted behavior). Existing docs keep current content; historical ADR changes remain only F8-HISTORY leading status sentences below. New ADR 0050 does not claim implemented/ratified behavior. Names/experiment descriptions remain contingent on D2/Q06 decisions.
Target docs/adr/0050-oci-isolation-provider.md (new file, exact proposed body):
```markdown
# 0050: OCI process isolation

Current status: Proposed; implementation and live OCI acceptance pending.

Git worktrees separate files but cannot fence target process effects. Mutating verification uses a caller-owned Docker/Podman executable and locally available digest-pinned image. Provider never pulls images or falls back to host execution. Project mounts read-only at /work; caller-owned private scratch mounts writable at /out. Network disabled; no-new-privileges, dropped capabilities, 64 PIDs, 512 MiB memory and one CPU bound execution.

Runtime trust/containment validation happens before image inspection and before target execution. Timeout/cancellation triggers owned removal and inspection. Failure to confirm cleanup is an operation error carrying factual receipt, never isolation_unavailable. Output digest covers returned bounded/redacted stdout plus stderr; helper does not claim a capture-memory bound.

Acceptance: tests/test_isolated_process.py::test_container_denies_worktree_write_and_network and ::test_receipt_fields; all oci_isolation tests run in provisioned CI. Image owner/provisioning remains D11 decision.
```

Target docs/safety/security-model.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## Isolated verification

Verification container uses --pull=never, --network=none, read-only /work and writable private /out. It drops capabilities, prohibits privilege escalation, limits PIDs to 64, memory to 512 MiB and CPUs to 1. Unsupported runtime/image returns structured skipped operation; no host fallback. Failure to confirm post-launch cleanup returns error with owned container identity.
```

Target docs/developer/testing-guide.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## OCI acceptance and transport parity

Set RUSH_TEST_OCI_RUNTIME to approved absolute Docker/Podman path. Unset runtime deselects oci_isolation tests; it never proves live acceptance. With runtime set, each test requires its digest-pinned RUSH_TEST_PYTHON_IMAGE, RUSH_TEST_RUSH_IMAGE or conditional RUSH_TEST_COMPILER_IMAGE; absent/unpinned image fails. Run `uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests -m oci_isolation -q` in provisioned CI.

Command tests import run_cli/run_mcp from transport_parity. Helper initializes real stdio MCP session and uses real-file errlog on Windows; credentials are controlled per test before each subprocess starts.
```

Target docs/developer/tool-development.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## Command result and isolation contracts

Preserve canonical ToolResult and routing aggregate status. Child file coverage uses routing.child_scope; aggregate preserves per-engine evidence, partial coverage and existing terminal/workflow metadata. OCI operations use runtime.isolated_process; selected pytest nodes use runtime.isolated_tests. Never launch denied operation or substitute host execution for missing isolation.
```

Target docs/developer/mcp-development.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## Strict command forwarding

Command request models derive from published wrapper signatures, forbid unknown keys and reject malformed grants before InvocationExecutor dispatch. Transport fields project/result_view/limit/max_bytes/no_cache/allow_cache_write remain valid; view fields are consumed by wrapper. Runtime paths stay absolute caller inputs without invocation-CWD anchoring. Malformed selected-root rush.toml yields status error and metadata.error.code invalid_config before dispatch.
```

Target docs/developer/source-tree.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## Shared command foundation

src/rush/runtime/isolated_process.py provides OCI preflight, argv launch and factual receipts. isolated_tests.py provides selected-node pytest outcome/count mapping. mcp_support/request_models.py owns strict public command schemas. tests/transport_parity.py owns real CLI/initialized-stdio parity helper.
```

Target docs/user-guide/understanding-results.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
## Optional work and refused actions

Missing required permission returns skipped and names flag needed to continue. Some optional checks preserve original findings while reporting refused work separately. Unavailable isolated runtime/image reports skipped operation; Rush does not run that work on host. Check requested flags and runtime/image settings, then retry. Invalid input or malformed project configuration returns error.
```

Target docs/reference/environment-variables.md (append exact current-document subsection/rows; retain all existing bytes):
```markdown
| Variable | Value | Use |
| --- | --- | --- |
| RUSH_TEST_OCI_RUNTIME | Approved absolute Docker/Podman executable | Real OCI test selection and launch |
| RUSH_TEST_PYTHON_IMAGE | Digest-pinned local image with verified Python/pytest | Python probe/oracle acceptance |
| RUSH_TEST_RUSH_IMAGE | Digest-pinned local image with Rush CLI | Markdown example acceptance |
| RUSH_TEST_COMPILER_IMAGE | Digest-pinned compiler image, only if Q06 selects OCI | Typecheck experiment acceptance |
| RUSH_TEST_VITEST_PROJECT | Explicit JavaScript fixture project | Real Vitest acceptance |
```

Target docs/safety/permissions.md: append exact operation table below only after command-owned grants/signatures are implemented; existing rows11-17 updated in same serialized packet from those owners' exact grant rows. No grant is inferred from this table: it repeats F10 interface proposal, including conditional Q06 choice.
```markdown
## Command permission gates

| Command | Public operation contract |
| --- | --- |
| review | Review Python files at <path> with local heuristics; claim_evidence=true binds claims to source digests, probe_claims=true runs one specialist-proposed counterexample in an isolated OCI container and needs allow_network, allow_build, allow_slow, allow_artifact_write plus runtime_path and image_ref; a denied grant returns status 'skipped' naming the missing flag. |
| lint | Lint at <path>; baseline_result_path returns new, resolved and unchanged findings, minimize_finding reduces one Ruff finding and needs allow_build, allow_slow and allow_artifact_write; all engines unavailable returns status 'skipped'; assessed inputs mixed with unavailable engine coverage returns 'warn', with unavailable engines listed as skipped in metadata.engines. |
| format | Format at <path>; check=true (default) never writes; mode='preview' and mode='apply' need allow_artifact_write; verify_preview_id additionally needs allow_build, allow_slow, runtime_path and image_ref. |
| test | Run project tests at <path>; suite python\|javascript\|all runs every detected suite and needs allow_build; minimize_order_failure additionally needs allow_slow, runtime_path and image_ref and returns metadata.interaction_reproducer. |
| security | Audit dependency inputs at <path>; every manifest and lockfile gets one row in metadata.inputs; trial_candidate with target_advisory and dependency_tests needs allow_build, allow_slow, runtime_path and image_ref. |
| typecheck | Typecheck at <path>; typecheck_config selects the owning config, caller_graph_path validates diagnostic callers, explain_config_effect runs bounded config experiments in isolation selected by Q06 X1 decision and needs allow_build, allow_slow, allow_cache_write plus runtime_path and image_ref only when OCI is selected. |
| dead | Find dead-code candidates at <path>; confirm_reachability with probe_candidate and probe_tests runs the named tests in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref; a hit rejects deletion, a miss stays unknown. |
| complexity | Measure complexity at <path>; view='hotspots' ranks units by observed history; trial_refactor with verification_tests verifies a patch in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref. |
| slop | Detect AI-slop markers at <path>; rule_profile='project_style' with rule_config_path applies explicit rules; calibrate_rule with calibration_fixture reports TP, FP, TN and FN without writing; metadata.assessed lists one row per language. |
| markdown | Check Markdown at <path>; verify_examples=true checks fenced Rush command lines against the current CLI without running them; repair_example with candidate_argv runs one candidate in an isolated Rush image and needs allow_build, allow_slow, runtime_path and image_ref. |
```
Reference docs/reference/cli-reference.md and docs/reference/mcp-tool-reference.md consume each implemented command's identical F10 discovery sentence plus that command owner's exact option/schema patch rows in same packet; defaults/options remain blocked by D2. Result reference addition, target docs/reference/result-reference.md:
```markdown
## Optional operations and assessed scope

Each command keeps one command-specific operation block and canonical findings. Per-engine evidence remains metadata.engines; assessed coverage remains metadata.scope. Complete and unavailable children yield partial coverage; only unassessed inputs yield none. Existing workflow children, review aggregation and terminal partial evidence remain unchanged. Denied operation records missing permissions; unavailable OCI operation never falls back to host execution.
```
CHANGELOG.md exact future row under current Unreleased changes (only after implementation):
```markdown
- Add shared strict command forwarding, explicit assessed coverage and permission-denial carriers, digest-pinned OCI verification, selected-test outcomes, real CLI/stdio parity, fail-closed MCP configuration and fresh verified SBOM publication/consumption.
```
F8 coverage registration gate: reuse exact settled Plan01 Q01-M1 body below, not a new registry/receipt API. Prerequisites: Q01-21 proposed inventory allowlist patch implemented; its exact14 copied prerequisites frozen and present in destination; all cited acceptance tests passed; new ADR bodies and shared docs finished. Source identity is settled Plan01 SHA42be071461fda7353aaf25cc813030ba6606e577dfc9da0d96220a9fd17b2828, lines3275-3338. Run in Phase70 implementation checkout with distinct frozen primary corpus argument; missing/mismatched file fails before receipt write. Other command ADRs extend owned_new_docs only through same-packet command-owned evidence rows, never inferred evidence. This script remains proposed/unexecuted.
```python
import hashlib, importlib.util, json, sys
from pathlib import Path

root = Path(".")
frozen_source = Path(sys.argv[1]).resolve(strict=True)
if frozen_source == root.resolve():
    raise ValueError("Frozen source must differ from destination checkout")
copied_prerequisites = {
    f"docs/phase-plans/command-tdd-2026-10-01/{name}"
    for name in (
        "README.md",
        "00-shared-foundation.md",
        "01-rush-review.md",
        "02-rush-lint.md",
        "03-rush-format.md",
        "04-rush-test.md",
        "05-rush-security.md",
        "06-rush-typecheck.md",
        "07-rush-dead.md",
        "08-rush-complexity.md",
        "09-rush-slop.md",
        "10-rush-markdown.md",
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
spec = importlib.util.spec_from_file_location(
    "sync_docs", root / "scripts/sync_docs.py"
)
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
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
                audience="maintainers",
                authority="current",
                evidence=[
                    f"Byte-identical prerequisite: {e['path']} sha256={transfer_sha256[e['path']]}"
                ],
            )
        elif e["path"] in owned_new_docs:
            e.update(
                audience="maintainers",
                authority="current",
                evidence=owned_new_docs[e["path"]],
            )
        else:
            raise ValueError(f"Unowned new documentation: {e['path']}")
        receipt["documents"].append(e)
payload = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
report.write_text(
    text[: m.start("payload")] + payload + text[m.end("payload") :], encoding="utf-8"
)
```
Exact proposed invocation after prerequisites: `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python - /absolute/frozen/source/root` with this script on stdin, then `rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check`; expected exit0. Historical body hashes remain unchanged. Supplied /absolute/frozen/source/root is explicit caller argument, never an approved path default.
## F9 MCP config-error policy (audit section 4.1)
mcp_support/tool_registry.py::_load_config_or_none is replaced at its callers (lines 294, 407, 436) by a policy that returns an error ToolResult (status error, metadata.error = {"code": "invalid_config", "message": <RushConfigError text>}, message from RushConfigError; CLI parity: rendering.py prints the message and exits 2) instead of None. Test: tests/test_mcp.py::test_malformed_rush_toml_is_error_on_mcp.


Proposed exact F9 patch, unexecuted. Existing RushConfigError/load_config imports remain. Three load sites fail closed; both wrapper families retain target-error handling. Unit bodies invoke actual wrappers; CLI body separately exercises existing rendered exit2.
```diff
--- a/src/rush/mcp_support/tool_registry.py
+++ b/src/rush/mcp_support/tool_registry.py
@@
-def _load_config_or_none(root: Path) -> Any:
-    """Best-effort `rush.toml` load for MCP invocations.
-
-    MC05: MCP invocations must resolve real `[tools.memory]` config (same as the
-    CLI in `cli_support/rendering.py`) so `memory_record` is populated
-    identically on both transports. T8: discovery starts at the selected
-    logical root, after containment. A malformed `rush.toml` fails open to no
-    config here (unchanged pre-MC05 MCP behavior) rather than newly breaking
-    every MCP tool call over a config error MCP never validated before.
-    """
-    try:
-        return load_config(start=root)
-    except RushConfigError:
-        return None
+def _load_config(root: Path) -> Any:
+    """Load selected root config; propagate malformed config before dispatch."""
+    return load_config(start=root)
+
+
+def _invalid_config_result(tool_name: str, exc: RushConfigError) -> dict[str, Any]:
+    from rush.runtime.result_helpers import error_result
+
+    result = dict(error_result(tool_name, None, str(exc)))
+    result["summary"] = str(exc)
+    result["metadata"] = {
+        "error": {"code": "invalid_config", "message": result["summary"]}
+    }
+    return result
@@ _standard_context
-        config=_load_config_or_none(selection.root),
+        config=_load_config(selection.root),
@@ make_tool_wrapper.prepare
         except InvalidTargetError as exc:
             # T9/R9.2: malformed input is a result, never a traceback.
             return invalid_target_result(tool.name, exc)
+        except RushConfigError as exc:
+            return _invalid_config_result(tool.name, exc)
@@ _custom_context (path_key is None)
-            config=_load_config_or_none(server_anchor),
+            config=_load_config(server_anchor),
@@ _custom_context (path branch)
-        config=_load_config_or_none(selection.root),
+        config=_load_config(selection.root),
@@ make_custom_wrapper.custom_mcp_wrapper
         except InvalidTargetError as exc:
             # T9/R9.2: malformed input is a result, never a traceback.
             return invalid_target_result(tool_id, exc)
+        except RushConfigError as exc:
+            return _invalid_config_result(tool_id, exc)
```
Proposed tests/test_mcp.py additions (unexecuted):
```python
import pytest
from pathlib import Path

from rush.config import RushConfigError, load_config
from rush.mcp_support.tool_registry import make_custom_wrapper, make_tool_wrapper


@pytest.mark.parametrize("route", ["catalog", "custom_path", "custom_request"])
def test_malformed_rush_toml_is_error_on_mcp(tmp_path, route):
    (tmp_path / "rush.toml").write_text("[tools.lint\n")
    calls = []

    class Executor:
        def execute(self, context):
            calls.append(context)
            raise AssertionError("Malformed config must stop before executor")

    class Tool:
        name = "lint"

        def __call__(self, path: Path):
            raise AssertionError("Malformed config must stop before tool")

    def custom_path(path: Path):
        raise AssertionError("Malformed config must stop before handler")

    def custom_request(request: dict):
        raise AssertionError("Malformed config must stop before request handler")

    executor = Executor()
    if route == "catalog":
        wrapper = make_tool_wrapper(Tool(), executor=executor, anchor_cwd=tmp_path)
        arguments = {"path": str(tmp_path)}
    elif route == "custom_path":
        wrapper = make_custom_wrapper(
            custom_path, "rush_custom", executor=executor, anchor_cwd=tmp_path
        )
        arguments = {"path": str(tmp_path)}
    else:
        wrapper = make_custom_wrapper(
            custom_request, "rush_custom", executor=executor, anchor_cwd=tmp_path
        )
        arguments = {"request": {}}
    with pytest.raises(RushConfigError) as expected:
        load_config(start=tmp_path)
    result = wrapper(**arguments)
    assert result["status"] == "error"
    assert result["summary"] == str(expected.value)
    assert result["metadata"]["error"] == {
        "code": "invalid_config",
        "message": str(expected.value),
    }
    assert calls == []


def test_malformed_rush_toml_cli_exit_two(tmp_path):
    from click.testing import CliRunner
    from rush.cli import cli

    (tmp_path / "rush.toml").write_text("[tools.lint\n")
    with pytest.raises(RushConfigError) as expected:
        load_config(start=tmp_path)
    result = CliRunner().invoke(cli, ["lint", str(tmp_path), "--json"])
    assert result.exit_code == 2
    assert str(expected.value) in result.output
```
## F10 Discovery text (audit section 4.3)
Keep TOOL_SPECS[...].mcp_description at 20-199 characters with Phase70 key phrases. Add ToolSpec.discovery: str = "" in src/rush/catalog.py as single source for sentences below (names contingent on README D2). F1 publishes inputSchema.properties.path.description; build_catalog_path_command (catalog_commands.py:308) and handwritten review/format help append discovery. tests/test_mcp.py asserts exact schema path description; tests/test_cli_registry.py asserts exact sentence in CLI --help. Neither route overloads bounded mcp_description.
- review: "Review Python files at <path> with local heuristics; claim_evidence=true binds claims to source digests, probe_claims=true runs one specialist-proposed counterexample in an isolated OCI container and needs allow_network, allow_build, allow_slow, allow_artifact_write plus runtime_path and image_ref; a denied grant returns status 'skipped' naming the missing flag."
- lint: "Lint at <path>; baseline_result_path returns new, resolved and unchanged findings, minimize_finding reduces one Ruff finding and needs allow_build, allow_slow and allow_artifact_write; all engines unavailable returns status 'skipped'; assessed inputs mixed with unavailable engine coverage returns 'warn', with unavailable engines listed as skipped in metadata.engines."
- format: "Format at <path>; check=true (default) never writes; mode='preview' and mode='apply' need allow_artifact_write; verify_preview_id additionally needs allow_build, allow_slow, runtime_path and image_ref."
- test: "Run project tests at <path>; suite python|javascript|all runs every detected suite and needs allow_build; minimize_order_failure additionally needs allow_slow, runtime_path and image_ref and returns metadata.interaction_reproducer."
- security: "Audit dependency inputs at <path>; every manifest and lockfile gets one row in metadata.inputs; trial_candidate with target_advisory and dependency_tests needs allow_build, allow_slow, runtime_path and image_ref."
- typecheck: "Typecheck at <path>; typecheck_config selects the owning config, caller_graph_path validates diagnostic callers, explain_config_effect runs bounded config experiments in isolation selected by Q06 X1 decision and needs allow_build, allow_slow, allow_cache_write plus runtime_path and image_ref only when OCI is selected."
- dead: "Find dead-code candidates at <path>; confirm_reachability with probe_candidate and probe_tests runs the named tests in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref; a hit rejects deletion, a miss stays unknown."
- complexity: "Measure complexity at <path>; view='hotspots' ranks units by observed history; trial_refactor with verification_tests verifies a patch in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref."
- slop: "Detect AI-slop markers at <path>; rule_profile='project_style' with rule_config_path applies explicit rules; calibrate_rule with calibration_fixture reports TP, FP, TN and FN without writing; metadata.assessed lists one row per language."
- markdown: "Check Markdown at <path>; verify_examples=true checks fenced Rush command lines against the current CLI without running them; repair_example with candidate_argv runs one candidate in an isolated Rush image and needs allow_build, allow_slow, runtime_path and image_ref."


Concrete F10 rows (proposed, contingent on D2 naming). Append following initialization immediately after TOOL_SPECS is constructed in src/rush/catalog.py, using F10-CATALOG dataclass field below. Leaves bounded descriptions unchanged. Exact same sentences feed all three discovery surfaces.
```python
from dataclasses import replace

_DISCOVERY = {
    "review": "Review Python files at <path> with local heuristics; claim_evidence=true binds claims to source digests, probe_claims=true runs one specialist-proposed counterexample in an isolated OCI container and needs allow_network, allow_build, allow_slow, allow_artifact_write plus runtime_path and image_ref; a denied grant returns status 'skipped' naming the missing flag.",
    "lint": "Lint at <path>; baseline_result_path returns new, resolved and unchanged findings, minimize_finding reduces one Ruff finding and needs allow_build, allow_slow and allow_artifact_write; all engines unavailable returns status 'skipped'; assessed inputs mixed with unavailable engine coverage returns 'warn', with unavailable engines listed as skipped in metadata.engines.",
    "format": "Format at <path>; check=true (default) never writes; mode='preview' and mode='apply' need allow_artifact_write; verify_preview_id additionally needs allow_build, allow_slow, runtime_path and image_ref.",
    "test": "Run project tests at <path>; suite python|javascript|all runs every detected suite and needs allow_build; minimize_order_failure additionally needs allow_slow, runtime_path and image_ref and returns metadata.interaction_reproducer.",
    "security": "Audit dependency inputs at <path>; every manifest and lockfile gets one row in metadata.inputs; trial_candidate with target_advisory and dependency_tests needs allow_build, allow_slow, runtime_path and image_ref.",
    "typecheck": "Typecheck at <path>; typecheck_config selects the owning config, caller_graph_path validates diagnostic callers, explain_config_effect runs bounded config experiments in isolation selected by Q06 X1 decision and needs allow_build, allow_slow, allow_cache_write plus runtime_path and image_ref only when OCI is selected.",
    "dead": "Find dead-code candidates at <path>; confirm_reachability with probe_candidate and probe_tests runs the named tests in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref; a hit rejects deletion, a miss stays unknown.",
    "complexity": "Measure complexity at <path>; view='hotspots' ranks units by observed history; trial_refactor with verification_tests verifies a patch in an isolated container and needs allow_build, allow_slow, runtime_path and image_ref.",
    "slop": "Detect AI-slop markers at <path>; rule_profile='project_style' with rule_config_path applies explicit rules; calibrate_rule with calibration_fixture reports TP, FP, TN and FN without writing; metadata.assessed lists one row per language.",
    "markdown": "Check Markdown at <path>; verify_examples=true checks fenced Rush command lines against the current CLI without running them; repair_example with candidate_argv runs one candidate in an isolated Rush image and needs allow_build, allow_slow, runtime_path and image_ref.",
}
for _name, _sentence in _DISCOVERY.items():
    TOOL_SPECS[_name] = replace(TOOL_SPECS[_name], discovery=_sentence)
```
```diff
--- a/src/rush/cli_support/catalog_commands.py
+++ b/src/rush/cli_support/catalog_commands.py
@@ build_catalog_path_command help
-            f"{TOOL_SPECS[tool.name].maturity.replace('_', ' ')}."
+            f"{TOOL_SPECS[tool.name].maturity.replace('_', ' ')}. "
+            f"{TOOL_SPECS[tool.name].discovery}"
--- a/src/rush/cli.py
+++ b/src/rush/cli.py
@@
-cli.add_command(build_help_command(cli))
+for _name in ("review", "format"):
+    _command = cli.commands[_name]
+    _command.help = (_command.help or "") + " " + TOOL_SPECS[_name].discovery
+cli.add_command(build_help_command(cli))
```
Phase70 cli.py has no TOOL_SPECS import. Add exact top-level import row before existing catalog_commands import:
```diff
@@
+from .catalog import TOOL_SPECS
 from .cli_support.catalog_commands import (
```
Runnable discovery body is in F11's tests/test_mcp.py fence below.
## F11 Forwarding acceptance
tests/test_cli_registry.py::test_tool_cli_options_forward_typed_values and tests/test_mcp.py::test_command_tools_reject_non_boolean_grants (F1) plus tests/test_mcp.py::test_command_tools_reject_unknown_arguments and ::test_command_tools_preserve_transport_options run for all ten command tools; unknown key or malformed grant causes zero dispatch; valid transport options survive normalization. Forwarding checks run for every new option of every plan; route spies are accepted as evidence only after the typed signatures and forwarding calls exist.


Concrete F1/F11 tests/test_mcp.py additions (proposed, unexecuted). Invoke real RushFastMCP.call_tool and actual public normalizer; invalid inputs must stop before InvocationExecutor.execute. Valid view fields are normalized and consumed by wrapper, not falsely asserted as tool kwargs. Discovery test invokes actual SDK listing and Click help. Requires concrete updated command signatures plus F1/F10.
```python
import asyncio
import json
from pathlib import Path

import pytest

from rush.mcp import build_server
from rush.mcp_support.request_models import validate_and_normalize

COMMANDS = (
    "review",
    "lint",
    "format",
    "test",
    "security",
    "typecheck",
    "dead",
    "complexity",
    "slop",
    "markdown",
)
GRANTS = (
    "allow_network",
    "allow_download",
    "allow_cache_write",
    "allow_build",
    "allow_slow",
    "allow_artifact_write",
    "allow_browser",
)


@pytest.mark.parametrize("name", COMMANDS)
@pytest.mark.parametrize("grant", GRANTS)
@pytest.mark.parametrize("value", ["false", 0, 1, None, [], {}])
def test_command_tools_reject_non_boolean_grants(
    tmp_path, monkeypatch, name, grant, value
):
    from rush.invocation.executor import InvocationExecutor

    server = build_server()
    calls = []
    monkeypatch.setattr(
        InvocationExecutor, "execute", lambda *a, **kw: calls.append((a, kw))
    )
    response = asyncio.run(
        server.call_tool("rush_" + name, {"path": str(tmp_path), grant: value})
    )
    result = json.loads(response.content[0].text)
    assert response.isError is False
    assert (
        result["status"] == "error"
        and result["raw"]["error"]["code"] == "INVALID_REQUEST"
    )
    assert calls == []


@pytest.mark.parametrize("name", COMMANDS)
def test_command_tools_reject_unknown_arguments(tmp_path, monkeypatch, name):
    from rush.invocation.executor import InvocationExecutor

    server = build_server()
    calls = []
    monkeypatch.setattr(
        InvocationExecutor, "execute", lambda *a, **kw: calls.append((a, kw))
    )
    response = asyncio.run(
        server.call_tool(
            "rush_" + name, {"path": str(tmp_path), "unknown_option": True}
        )
    )
    result = json.loads(response.content[0].text)
    assert response.isError is False
    assert (
        result["status"] == "error"
        and result["raw"]["error"]["code"] == "INVALID_REQUEST"
    )
    assert calls == []


@pytest.mark.parametrize("name", COMMANDS)
def test_command_tools_preserve_transport_options(tmp_path, monkeypatch, name):
    from rush.invocation.executor import InvocationExecutor

    arguments = {
        "path": str(tmp_path),
        "project": None,
        "result_view": "full",
        "limit": 5,
        "max_bytes": 4096,
        "no_cache": True,
        "allow_cache_write": False,
    }
    normalized = validate_and_normalize("rush_" + name, arguments)
    assert normalized.rejected is False
    for key, value in arguments.items():
        assert normalized.arguments[key] == value
        assert type(normalized.arguments[key]) is type(value)
    server = build_server()
    calls = []
    views = []
    from rush.mcp_support import tool_registry

    original_deliver = tool_registry.compact.deliver

    def deliver(tool, options, **kwargs):
        views.append((tool, options, kwargs["cache_write"]))
        return original_deliver(tool, options, **kwargs)

    monkeypatch.setattr(tool_registry.compact, "deliver", deliver)

    def execute(self, context):
        calls.append(context)
        return {
            "tool": name,
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "forwarding probe",
            "findings": [],
            "raw": None,
        }

    monkeypatch.setattr(InvocationExecutor, "execute", execute)
    response = asyncio.run(server.call_tool("rush_" + name, arguments))
    result = json.loads(response.content[0].text)
    assert response.isError is False and result["status"] == "ok"
    assert len(calls) == 1
    context = calls[0]
    assert context.transport == "mcp" and context.operation_id == name
    assert context.workspace_root == tmp_path.resolve()
    assert context.original_requested_targets == (str(tmp_path),)
    assert context.declared_root is None and context.permissions == ()
    assert context.cache_policy == "bypass"
    assert len(views) == 1
    tool, options, cache_write = views[0]
    assert tool == name and cache_write is False
    assert options.result_view == "full"
    assert type(options.limit) is int and options.limit == 5
    assert type(options.max_bytes) is int and options.max_bytes == 4096
    assert options.no_cache is True


@pytest.mark.parametrize("name", COMMANDS)
def test_command_discovery_schema_and_help(name):
    from click.testing import CliRunner
    from rush.catalog import TOOL_SPECS
    from rush.cli import cli

    spec = TOOL_SPECS[name]
    assert 20 <= len(spec.mcp_description) <= 199
    assert spec.discovery
    listed = asyncio.run(build_server().list_tools())
    schema = next(tool.inputSchema for tool in listed if tool.name == "rush_" + name)
    assert schema["properties"]["path"]["description"] == spec.discovery
    result = CliRunner().invoke(cli, [name, "--help"])
    assert result.exit_code == 0
    assert " ".join(spec.discovery.split()) in " ".join(result.output.split())
```
Concrete tests/test_cli_registry.py additions (proposed, unexecuted). Enumerates every registered generic command option; unsupported type/nargs fails with exact missing fixture rather than skipping. Every command packet additionally owns explicit complete option-name assertion plus any structured/multi-value fixture. Existing handwritten --llm and --check routes tested directly; each packet must append its new handwritten cases to this same parameterization after D2/signatures/options settle. Route spies prove typed forwarding only, not feature behavior.
```python
import click
import pytest
from click.testing import CliRunner
from pathlib import Path

from rush.cli import cli
from rush.cli_support import catalog_commands


def test_tool_cli_options_forward_typed_values(tmp_path, monkeypatch):
    # Enumerate registered command-specific options. Missing registration cannot
    # be hidden: each command packet separately asserts its complete option names.
    names = {
        "lint",
        "test",
        "security",
        "typecheck",
        "dead",
        "complexity",
        "slop",
        "markdown",
    }
    registered = {
        name: options
        for name, options in catalog_commands._TOOL_CLI_OPTIONS.items()
        if name in names
    }
    assert "typecheck" in registered
    seen = []
    monkeypatch.setattr(
        catalog_commands, "_run_tool", lambda *a, **kw: seen.append(kw["extra_kwargs"])
    )
    fixture = tmp_path / "fixture.txt"
    fixture.write_text("fixture\n")
    for name, options in registered.items():
        for option in options:
            if option.is_flag:
                values, expected = [], option.flag_value
            elif isinstance(option.type, click.Choice):
                values, expected = [option.type.choices[0]], option.type.choices[0]
            elif isinstance(option.type, click.Path):
                values = [str(fixture)]
                expected = Path(fixture) if option.type.type is Path else str(fixture)
            elif isinstance(option.type, click.types.IntParamType):
                number = getattr(option.type, "min", None) or 1
                values, expected = [str(number)], number
            elif isinstance(option.type, click.types.FloatParamType):
                number = getattr(option.type, "min", None) or 1.5
                values, expected = [str(number)], float(number)
            elif isinstance(option.type, click.types.StringParamType):
                values, expected = ["sample"], "sample"
            else:
                raise AssertionError(
                    f"Add concrete typed case for {name}.{option.name}"
                )
            if option.nargs != 1:
                raise AssertionError(
                    f"Add concrete multi-value case for {name}.{option.name}"
                )
            args = [name, str(tmp_path), option.opts[0], *values, "--json"]
            if option.multiple:
                expected = (expected,)
            outcome = CliRunner().invoke(cli, args)
            assert outcome.exit_code == 0, outcome.output
            assert seen[-1][option.name] == expected
            assert type(seen[-1][option.name]) is type(expected)


@pytest.mark.parametrize(
    "name,flag,key,expected",
    [
        ("review", "--llm", "use_llm", True),
        ("format", "--check", "check", True),
    ],
)
def test_handwritten_command_options_forward(
    tmp_path, monkeypatch, name, flag, key, expected
):
    import importlib

    module = importlib.import_module("rush.cli")
    seen = []
    monkeypatch.setattr(
        module, "_run_tool", lambda *a, **kw: seen.append(kw["extra_kwargs"])
    )
    outcome = CliRunner().invoke(module.cli, [name, str(tmp_path), flag, "--json"])
    assert outcome.exit_code == 0, outcome.output
    assert seen[-1][key] is expected
```
## Constraints
Plan edits only during remediation. Source/test/docs/CI changes below are proposed implementation deliverables, not applied. All user decisions remain unapproved unless explicitly recorded. Changed implementation files belong to README Roles; commands supply exact shared-file patch rows. No hooks, implicit installs/network, commit, push or release change.

## Checks to run before reporting
All commands in this section are **proposed implementation acceptance**, unexecuted during Markdown remediation. Run from the separately authorized implementation checkout with inherited PYTHONPATH cleared; verify Python3.12. Apply required packet source/tests first. A missing future module is an ordering failure, not a failed behavior proof and not permission to skip that requirement.

Shared current-signature gate after F1–F3/F6, and again only for affected interfaces when command signatures/F9–F11 integrate:
```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_transport_parity.py tests/test_routing.py tests/test_cli_registry.py tests/test_mcp.py tests/test_import_order.py tests/test_phase70_result_trust.py tests/test_phase70_t16.py -q
```
Expected Python3.12; exact packet assertions pass; zero skipped. F6 helper/self-tests are created before this gate. Tests for future command options run only after corresponding real signatures and serialized option rows exist; F11 freezes that complete typed forwarding set.

After F4/F5/F7 create provider/helper/consumer and tests:
```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_subprocess_contract.py tests/test_isolated_process.py tests/test_isolated_tests.py tests/test_transport_parity.py tests/test_routing.py tests/test_sbom.py tests/test_cli_registry.py tests/test_mcp.py tests/test_import_order.py tests/test_phase70_result_trust.py -m 'not oci_isolation' -q
```
Expected all selected deterministic branch tests pass, zero skipped. This is not live isolation acceptance. Each command integration runs the union of its own new/changed tests, X-13 row and C-20 additions, including its engine/applicability/subprocess/Phase70 regressions. F00's shared set never replaces those commands. Earlier R/E gates exclude tests/test_isolated_process.py and Q03 tests/test_format_oci.py until their owning packets create them; X1 gates include them afterwards. Q06 provider/compiler-image gates apply only if Q06 X1 selects OCI.

Same-packet quality/docs checks:
```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy git diff --check
```
Expected each exit0. mypy src/rush is D8 default proposal; replace only that command with mypy . if approved. Docs check uses current sync_docs runtime contracts/inventory, not text presence. New module/test/source-tree, current reference and historical receipt changes ship in the same affected packet.

Final real OCI gate after F4/images and dependent X1 packets, and final whole-suite integration:
```sh
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests -m oci_isolation -q
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider -q
```
oci-isolation CI supplies RUSH_TEST_OCI_RUNTIME and pinned RUSH_TEST_PYTHON_IMAGE/RUSH_TEST_RUSH_IMAGE, plus RUSH_TEST_COMPILER_IMAGE under OCI Q06; local image provisioning/version ownership depends on D11. RUSH_TEST_VITEST_PROJECT is real Q04 fixture input where required. Marker policy: when runtime unset, tests are deselected, never skipped; with runtime present a missing/unpinned required image fails that test. CI runtime/images are mandatory. Deselection count is evidence of omitted acceptance, never live PASS. No live OCI assertion can report BLOCKED as success.

C-19 preserves exact reported baseline exceptions, not a general failure allowance:
- tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[core]
- tests/test_phase70_t5.py::test_check_example_warns_with_denied_test_step_and_runs_it_when_granted[full]
- tests/test_no_skips.py::test_no_collected_test_carries_a_live_skip_marker
- tests/test_phase70_t12.py::test_t12_pyrefly_argv_no_directory_arg_when_explicit_files
- tests/test_phase70_t12.py::test_t12_typecheck_config_routes_python_family

Report70–74 is historical evidence, not a current run. Before/after authorized implementation must show each allowed node fails identically on pristine66c6c79 and changed checkout; retain all modules. Any new/different failure or skipped test fails acceptance. Report unchanged baseline failures explicitly and separately from packet success; never issue unqualified full-suite PASS while they remain. Recheck engine availability in that environment; reported pyrefly/runtime absence is not current verified availability.

During this remediation: no future pytest/full suite/OCI check executes. Static fence syntax/format, literal file-map/coverage and frozen hash preservation prove only those properties. Proposed behavior tests remain unexecuted; clean source HEAD cannot substitute for Phase70 T1–T29/G0–G8 acceptance.

## Completion
Proposed shared rows below are serialized Foundation deliverables. Completion/readiness criteria and substantive X/C/M reconciliation follow; this heading records no implementation PASS.
## Concrete shared patch rows (proposed; not applied)

F10-CATALOG, target src/rush/catalog.py::ToolSpec; append after scope_kind:
```diff
@@
     scope_kind: Literal["file", "operation"] = "file"
+    discovery: str = ""
```
F1-KIND, target src/rush/mcp_support/request_models.py::_ToolSpec; append after legacy_adapter:
```diff
@@
     legacy_adapter: Any = None
+    kind: Literal["operation", "command"] = "operation"
```
F1-MODEL, same module; define before _SPECS using existing inspect/create_model/TypeAdapter/_STRICT. New stdlib imports Path, types.UnionType and typing get_args/get_origin/Literal/Union; retain existing imports. Reuse existing StrictBool/StrictInt/StrictFloat/StrictStr (add missing Pydantic imports only). All signatures below are proposed additions, not existing APIs:
```python
def _command_annotation(annotation):
    from pathlib import Path
    from types import UnionType
    from typing import Annotated, Literal, Union, get_args, get_origin

    origin, args = get_origin(annotation), get_args(annotation)
    scalar = {
        bool: StrictBool,
        int: StrictInt,
        float: StrictFloat,
        str: StrictStr,
        Path: StrictStr,
        type(None): type(None),
    }
    if annotation in scalar:
        return scalar[annotation]
    if origin is Annotated:
        return Annotated[_command_annotation(args[0]), *args[1:]]
    if origin is Literal:
        return annotation
    if origin in (Union, UnionType):
        return _union(_command_annotation(item) for item in args)
    if origin is list:
        return list[_command_annotation(args[0])]
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        return tuple[_command_annotation(args[0]), ...]
    raise TypeError(f"unsupported command annotation: {annotation!r}")


def _command_spec(tool):
    from typing import Annotated, Literal
    from pydantic import Field
    from rush.mcp_support.tool_registry import make_tool_wrapper

    public_sig = inspect.signature(make_tool_wrapper(tool))
    # Phase70 wrapper publishes these three as Annotated[Any, WithJsonSchema].
    # Preserve exact public contracts, with real strict validation instead of Any.
    view_types = {
        "result_view": Literal["full", "compact"] | None,
        "limit": Annotated[StrictInt, Field(ge=1, le=50)] | None,
        "max_bytes": Annotated[StrictInt, Field(ge=4096, le=65536)] | None,
    }
    fields = {
        name: (
            view_types[name]
            if name in view_types
            else _command_annotation(parameter.annotation),
            _REQUIRED
            if parameter.default is inspect.Parameter.empty
            else parameter.default,
        )
        for name, parameter in public_sig.parameters.items()
    }
    model = create_model(f"Command_{tool.name}", __config__=_STRICT, **fields)
    return _ToolSpec(
        tool=tool.name,
        named={"command": model},
        named_adapter=TypeAdapter(model),
        kind="command",
    )
```
F1-REGISTER: after existing _SPECS literal, import ALL_TOOLS and register exactly ten selected tools. Existing project/scan/memory specs remain untouched:
```python
from rush.tools import ALL_TOOLS

_COMMAND_TOOLS = frozenset(
    {
        "review",
        "lint",
        "format",
        "test",
        "security",
        "typecheck",
        "dead",
        "complexity",
        "slop",
        "markdown",
    }
)
for _tool in ALL_TOOLS:
    if _tool.name in _COMMAND_TOOLS:
        _SPECS[f"rush_{_tool.name}"] = _command_spec(_tool)
REQUEST_MODEL_TOOLS = frozenset(_SPECS)
```
F1-PUBLISH: insert immediately after spec = _SPECS[tool_name] inside _published; uses new ToolSpec.discovery single source and leaves operation schemas intact:
```python
if spec.kind == "command":
    from rush.catalog import TOOL_SPECS

    schema = spec.named["command"].model_json_schema()
    schema["required"] = ["path"]
    schema["additionalProperties"] = False
    schema["properties"]["path"]["description"] = TOOL_SPECS[spec.tool].discovery
    return schema
```
F1-NORMALIZE, target validate_and_normalize, replace its memory-only flat-return condition:
```diff
@@
-    if spec.tool == "memory":
+    if spec.tool == "memory" or spec.kind == "command":
         return ValidationOutcome(arguments=fields)
```
This replacement targets the condition immediately after model_dump, not _reject's memory envelope branch. Public signature creation must occur after command signatures are updated; unsupported annotations are an explicit integration error, never silently accepted Any. D12 extends _COMMAND_TOOLS only after James selects scope.

F2-CHILD: code in F2 is the exact routing.py addition. Append child_scope to existing __all__; tests/test_routing.py proposed behavior check:
```python
def test_child_scope_complete_plus_unavailable_aggregates_to_partial():
    from rush.tools.routing import aggregate_scope, aggregate_status, child_scope

    complete = {
        "metadata": {
            "scope": child_scope(
                "complete",
                requested_targets=("a.py",),
                matched_file_count=1,
                consumed_file_count=1,
            )
        }
    }
    missing = {
        "metadata": {"scope": child_scope("unavailable", reason="engine_unavailable")}
    }
    assert aggregate_scope([complete, missing])["coverage"] == "partial"
    assert aggregate_status(["ok", "skipped"]) == "warn"
    assert (
        aggregate_scope(
            [{"metadata": {"scope": child_scope("none", reason="no_tests")}}]
        )["coverage"]
        == "none"
    )
```
Expected: 1 passed under README D5 default after F2 applied; no production helper exists yet. Alternative D5 changes status assertion at shared routing acceptance, never a tool-local override.

F8-HISTORY exact leading status sentence additions (retain each file's existing paragraph and all later bytes):
- docs/adr/README.md: "Current implementations are covered by ADR 0050 OCI isolation, 0051 review, 0052 lint, 0053 test, 0054 security, 0055 typecheck, 0056 dead-code reachability and 0057 Markdown examples."
- docs/adr/0007-slow-network-and-destructive-permissions.md: "Current per-operation grants and denial vocabulary are in docs/safety/permissions.md."
Both additions remain on leading Current status paragraph; coverage receipt preserves immutable_body_sha256. Test command after implementation: rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check; expected exit 0. Proposed test command F1: rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest -p no:cacheprovider tests/test_mcp.py::test_command_tools_reject_non_boolean_grants tests/test_mcp.py::test_command_tools_reject_unknown_arguments tests/test_mcp.py::test_command_tools_preserve_transport_options tests/test_cli_registry.py::test_tool_cli_options_forward_typed_values -q; expected all selected scenarios pass, zero rejected valid transport inputs and zero dispatch for invalid grants/unknown keys. These tests are F1/F11 implementation deliverables, not tests executed during plan remediation.

## Defined terms and evidence handles
- Public signature: make_tool_wrapper(tool).__signature__; model construction consumes wrapper public_sig including project and T16 view options, not the raw Tool.run signature.
- IsolatedRun/LaunchBudgetExhausted/IsolationUnavailable/IsolatedCleanupError: proposed F4 bodies; last means target may have run and cleanup failed, never skipped/no-target. F4-START counts one actual host child start per run_subprocess invocation, including owned bootstrap; it does not attest container/target or transient executable execution. output_sha256 preimage is exact bounded/redacted returned stdout+stderr; no claim of bounded live capture RAM.
- Selected tests: proposed F5 helper delegates to F4; contained unique pytest node IDs and extra pytest args are literal inputs, not an unspecified discovery algorithm.
- PhysicalRoot.open_contained returns a Path on Phase70; safe F7 reader and fresh producer specify actual bytes/digest/artifact flow. A Path return alone is not an opened-file or race-safety proof.
- Foundation patch row: exact command-supplied shared-file edit serialized by Foundation owner; no first-writer rule and no implied production authorization.

Evidence shorthand for coverage rows (source checkout66c6c79 unless stated):
E1: src/rush/mcp_support/tool_registry.py::make_tool_wrapper318–388, _load_config_or_none31–44, _standard_context247–298, _custom_context391–440, registration491–523→src/rush/mcp.py978–995. E2: src/rush/mcp_support/request_models.py::validate_and_normalize1025–1076, current operation/memory model/spec paths preserved. E3: src/rush/tools/routing.py::aggregate_status275–285, aggregate_scope377–395, child_entry398–435; child_scope proposed. E4: src/rush/runtime/subprocesses.py::run_subprocess857–919 and _bounded_redacted_output843–854; explicit/ambient cancellation and ownership retained. F4/F5 runtime modules proposed, not existing. E5: scripts/sync_docs.py::_mcp_contracts320–347 and collect_runtime_contracts427–437, existing immutable-body/inventory rules. E6: src/rush/tools/sbom.py::SbomTool.run50–106, PhysicalRoot Path contract; producer safety/read_verified_sbom proposed. Graft span receipts and exact report anchors are source evidence; they do not execute future patches.

## Finding reconciliation
All checks in this table are concrete **proposed acceptance** in referenced F packets, not executed behavior results. Corrected means a plan correction, not accepted implementation. Consumer-only means no authority to edit another plan; shared dependency stays complete here. External means an unapproved decision or missing acceptance/provisioning evidence, not ordinary unfinished drafting. Literal final C resolutions override earlier conflicting X/packet text.
| Finding | Literal requirement | Current evidence | Exact corrected section/change | Concrete input / expected state | Disposition / remaining gate |
|---|---|---|---|---|---|
| X-01 | Phase70 rather than c78-only assumptions | E1–E4; briefs | Baseline/order; F1–F11 existing-vs-proposed | 66c6c79 interfaces retained; selected Phase70 gates required | Corrected; acceptance evidence external |
| X-02 | Scope, aggregation, trusted results | E3 | F2/F3 child coverage + unchanged workflow carriers | complete+unavailable→partial; none-only→none; D5 controls exit | Corrected; D5 unapproved |
| X-03 | Complete W18/Q18 prerequisite design | E4/E6; modules absent | F4/F7 concrete bodies and ownership | preflight zero launches; real isolation; exact digest/contained SBOM | Corrected; D1/D11 entry gates |
| X-04 | Single provider/helper interface, budgets/timeouts | E4 | F4/F5 canonical return and launch accounting | actual launches include inspect/run/rm/inspect; reserve cleanup first | Corrected; D4/D9/D10 branches |
| X-05 | Shared file exclusivity | README Roles/C16 | Literal ownership/order above | same shared path has one writer; exact row before integration | Corrected; no consumer writes |
| X-06 | Typed CLI/MCP argument forwarding | E1/E2 | F1/F11 exact public_sig models and forwarding | ten commands; strict grants/unknown keys; six transport fields preserved | Corrected; D2/D3/D12 gates |
| X-07 | Keep current grant calling conventions | E1; Typecheck differs | F3 compatibility adapters | permissions=None/granted/denied reach existing run signatures | Retained; D3 remains choice |
| X-08 | Exact status/reason/error carriers | E3 | F3 canonical state matrix | denial zero spawn; empty scope none; runtime block per D6 | Corrected; D6 unapproved |
| X-09 | Shared selected-node pytest route | E4; helper absent | F5 body, count parser, contained unique nodes | exact counts/exit; wrong/malformed nodes rejected before launch | Corrected; Q07 D9 gated |
| X-10 | No undefined terms/dependencies | E1–E6 | Terms, packet bodies, file map/order | every referenced new helper defined; existing APIs grounded | Corrected; final review checks substance |
| X-11 | Task-block schema and concrete acceptance | Local task-block template | Deliverables/order/constraints/checks/completion | literal files, concrete RED/GREEN inputs, proposed-only labels | Corrected; decisions not removed |
| X-12 | Real module/image/environment prerequisites | E4; report environment facts | Stage checks; F4/F5/F6/F7 file creation | earlier checks omit absent future modules; no skipped OCI gate | Corrected; provisioning external |
| X-13 | Exact regression/quality gate union | E1–E6; X13/C20 | Checks and per-consumer union rule | targeted shared + all consumer modules; mypy/docs/full-suite later | Corrected; D8 and known failures explicit |
| X-14 | One actual CLI/initialized stdio parity helper | E1/E2/E4 | F6 per-call env/errlog/bodies/tests | real result fields equal; exact CLI exit; named API keys read per call under helper's explicit policy | Corrected; future real paths unexecuted |
| X-15 | Docs in same packet, immutable history | E5 | F8 literal docs/receipt rows | sync_docs exit0; allowed Current status changes only; body hashes equal | Corrected; no docs applied now |
| X-16 | Config fail-closed, discovery, forwarding | E1/E2/E5 | F9/F10/F11 bodies/tests | all3 config callers zero dispatch; bounded desc; exact typed fields | Corrected; no schema-only completion |
| X-17 | Binding input identities remain authoritative | Recorded report/audit hashes | Baseline/authority; no Git mutation | same input corpus; no commit/tag/push/release | Retained; no baseline rewriting |
| X-18 | Remove only misleading owned boilerplate | Original Plan00 completion text | Completion/readiness distinctions | no plan-only PASS represented as implementation accepted | Corrected; other plans untouched |
| C-01 | F2 aggregation exceptions | E3; final C01 | F2 review/workflow carriers retained | terminal partial and children retain metadata/findings, no invented review aggregate | Retained with exact acceptance |
| C-02 | Shared aggregate ok+skipped rule | E3 | F2 D5 alternatives | default warn/CLI1 or approved shared skipped/CLI0, no local override | External D5 |
| C-03 | IsolatedRun and process budget contract | E4; audit W18 | F4/F5 concrete interface/receipt/taxonomy | return .returncode/.stdout/.stderr/.process_launches/.receipt; cleanup error after start | Corrected |
| C-04 | Q10 timeout30, consumer-specific timeouts | Audit Q10/final C04 | F4 timeout caller table | Q10 timeout_s=30; D4 only Q03/Q05; no consumer edit | Retained/conditional |
| C-05 | All selected pytest consumers use F5 | Audit selected-node routes | F5 canonical adapter and fixtures | Q03/Q04/Q05/Q07/Q08 call same selected-node helper with exact extra args | Corrected shared route; consumers own integration |
| C-06 | Global tool option naming choice | E1/E2 | F1 D2 mapping; provider kwargs fixed | approved spelling forwards to runtime_path/image_ref without root anchor | External D2 |
| C-07 | Absolute runtime is not source-contained | E4; final C07 | F4 preflight and F1 forwarding | absolute trusted runtime outside project accepted; relative path rejected | Retained/concretized |
| C-08 | Runtime trust rule and operator ownership | Audit W18; final C08 | F4 explicit D10 conditional preflight | runtime validation before any launch; supplied basename/realpath ownership rule per choice | External D10; no implicit approval |
| C-09 | Unavailable runtime vs malformed image | E4 | F4 no-launch preflight taxonomy | bad runtime→IsolationUnavailable first; malformed pinned image→ValueError; zero launches | Corrected |
| C-10 | run grant signatures remain compatible | E1; T11/T12 | F3 D3 adapters | existing Typecheck convention preserved unless approved migration | Retained/external D3 |
| C-11 | Whole-call denial and explicit optional exceptions | E3; final C11 | F3/F2 exact command state contract | skipped whole call on required denial; named review/security/dead exceptions preserved | Retained/concretized |
| C-12 | Missing provider block vocabulary | E3; final C12 | F3 D6 conditional status | default skipped/reason isolation_unavailable or approved block status alternative | External D6 |
| C-13 | Tool metadata error vs raw MCP invalid request | E1/E2 | F3/F9 carrier distinction | canonical metadata.error.code; transport INVALID_REQUEST remains raw transport code | Retained/concretized |
| C-14 | Flat strict models from public wrapper sig | E1/E2 | F1 model/publish/normalize patches | additionalProperties false; strict boolean rejected before dispatch; view options preserved | Corrected |
| C-15 | Full discovery and bounded MCP description | E1/E5 | F10 catalog→schema→CLI flow | all ten descriptions exposed; mcp_description bound unchanged | Corrected |
| C-16 | Foundation sole shared writer | README Roles/C16 | Literal file map/order, F8 serialized rows | Q02 owns Ruff; Foundation owns runtime/subprocesses/config/catalog/docs | Corrected; consumer rows not applied |
| C-17 | OCI marker/deselection/image CI policy | Phase70 conftest/CI; final C17 | F4/F8 and stage checks | no runtime→deselected, never skipped; runtime+bad image→failure; CI all pinned images | Corrected; D11/image assets external |
| C-18 | mypy scope decision | Phase70 CI94; final C18 | Checks D8 variants | mypy src/rush default vs approved mypy .; no silent broader choice | External D8 |
| C-19 | Exact historical baseline failures | Report70–74; final C19 | Exact-node baseline policy in checks | only five named nodes may remain identical before/after; no other failure/skip | Corrected; historical facts not current PASS |
| C-20 | X13 plus per-plan check union | Final C20 literal module lists | Stage/consumer integration checks | neither set replaces other; future OCI files only after creation | Retained; consumer commands not edited |
| C-21 | Q08 stale CI/marker references | Phase70 CI/conftest | Current baseline references above | source CI94/97/143/146; deselection not skip | Consumer-only Q08 correction; F00 current evidence retained |
| C-22 | Unique ADR map and history receipts | E5; final C22 | F8 ADR0050–0057 ownership/receipt | new ADR registrations accepted; immutable historical bodies equal | Corrected; no appended historical index rows |
| C-23 | Shared docs exact variables/same packet | E5 | F8 environment/docs path map | runtime/python/Rush/compiler/Vitest variables correctly scoped; docs exit0 | Corrected |
| C-24 | Unapproved choices survive boilerplate cleanup | Original decisions/final C24 | Decisions/header/completion | no deleted choice or claimed approval; no Status boilerplate added | Retained; Q10 extra removed choice consumer-owned |
| C-25 | Q07 misleading term boilerplate | Final C25 | Defined terms below | shared terms have exact APIs; Q07 boilerplate not edited here | Consumer-only Q07 |
| C-26 | Q08 ownership/runtime anchoring | Final C26 | Shared ownership and C07 preflight | Foundation owns shared rows; no invented Q08 Foundation integration owner | Consumer-only Q08; shared rule retained |
| C-27 | Child coverage and security dependencies | E3; T14/T16 | F2 child_scope/security coverage acceptance | nested unavailable child preserves partial, static findings and exact dependencies | Corrected |
| C-28 | Q06 worktree/OCI remains open | Audit3195–3209/final C28 | Decision table/F4/F10/F11/F8 | worktree route has no isolation/image call; OCI route uses compiler image | External Q06 X1; not D2 |
| C-29 | Ten-tool unknown-key rejection, remaining-tool choice | E1/E2/final C29 | F1/F11 ten-tool tests + D12 | unknown property rejected before dispatch; remaining scope preserved | Corrected ten-tool scope; external D12 |
| M1 | Do not lose dependency/child coverage | E3; report M1 | F2 exact aggregation/security retention | complete+unavailable remains partial; existing findings/dependencies preserved | Corrected |
| M2 | Same-packet docs and CI checks | E5; Phase70 CI97 | F8/checks | sync_docs exit0 after each applied packet; immutable body digest stable | Corrected |
| M3 | Actual isolated entrypoint/argv route | E4; audit selected tests/Q06 | F4/F5/F10 interfaces | selected pytest route specified; Q06 worktree vs OCI conditional | Shared design corrected; consumer-owned calls |
| M4 | Python scratch plugin and extra pytest args | E4; audit Q07 | F4 scratch_on_pythonpath/F5 extra args | Q07 option(a) explicitly True or option(b) bootstrap; generic False | Corrected; external D9 |
| M5 | Aggregate warn means CLI1 | E3; T16 | F2/F6 exact status/exit | ok+skipped→warn/1 at default; approved D5 alternative shared | External D5 |
| M6 | Typecheck config currently str\|None | E1/T11/T12 | F1 typed forwarding compatibility | string config forwarded as string; no invented Path contract | Consumer-only Q06 design retained |
| M7 | Current engines are not missing implementations | Phase70 engine evidence/briefs | Phase70/order/source-proposed distinctions | Q02/Q05/Q09 preserve existing engines; only proven repair/additions | Consumer-owned; no duplicate engine design |

## Completion criteria
Plan remediation closes only when every applicable X/C/M row has substantive proposed corrections or justified retained/consumer-owned/external disposition, complete concrete packets and checks exist, frozen integrated bytes receive independent full coverage review, and preservation is verified. Another plan requires James's explicit authorization.

Development-ready is a separate verdict: an implementer can begin the first ordered packet only after affected choices in the decision table are approved and Phase70 T1–T29/G0–G8 acceptance is established. Defined future dependencies are ordered implementation work; unapproved choices or undefined prerequisites cannot be silently treated as ready. Required runtime/image provisioning and D11 ownership remain entry gates for OCI acceptance.

Implementation accepted requires separately authorized source/test/config/doc changes, exact packet checks, complete consumer integration and real OCI CI behavior. No production/test/config change or implementation acceptance occurred during this Markdown-only task.

## Remediation boundary receipt
Authorized output: this Plan00 only; Sol High owns difficult F1–F11 corrections, coordinator owns scope/global integration, Luna High owns read-only frozen review; no leaf delegation. Original Plan00 and corpus/source identities are above. Other eleven plan files, source/tests/config, existing AGENTS.md edits and both checkout HEADs are protected by baseline hash inventory; compare exact final fingerprints in coordinator handoff. Final SHA256 is reported outside file bytes.

Checks are distinguished explicitly: proposed behavior/quality commands above are unexecuted; code-fence/embedded-source syntax and formatting, coverage semantics and byte preservation are plan-only validation. Historical Grounded model experiment receipt below is retained with its narrow original evidentiary limit; it does not establish new option, transport or future patch acceptance.

Executed plan-only checks: all 21 Python fences parse with Python 3.12 and pass Ruff formatting; unchanged passing fence evidence is reused. F4-START's exact unified diff passes `git apply --check` against the named Phase70 source SHA, and its virtually patched source parses without writing source files. Formatting preserves ASTs, comments and surrounding Markdown; F7 additionally removes its unused local `json` import. Proposed implementation/behavior commands remain unexecuted.

Preserved useful work: original F1 model/spec/normalize design and experiment receipt, F2 child_scope/result invariants, F3 command conventions, F6 shared transport interface, F8 historical/docs rules, F10 descriptions and F5/D9 choices. Corrections target undefined bodies/test routes and contradictions (notably F4 post-launch unavailable and return125–127 inference); no series restart or consumer rewrite. Returned-output cap remains Phase70's bounded/redacted return contract; unsupported live-RAM capture extension is withdrawn.

External readiness gates: literal D1–D12 and Q06 X1 choices above where affected; Phase70 acceptance proof; approved locally pinned runtime/image provisioning for OCI stage. No ordinary incomplete authoring/review item qualifies as an external blocker. Handoff stops for James's Plan00 review; no implicit implementation or next-plan authorization.

## Grounded model experiment receipt
Earlier F1-MODEL snippet (AST-equivalent to its current formatted body) executed in memory with proposed _ToolSpec.kind against all ten real Phase70 wrapper signatures. Initial primitive-only assumption failed because project carries Annotated metadata and result_view/limit/max_bytes carry Annotated[Any, WithJsonSchema]. Corrected snippet preserves Annotated metadata and uses real strict view types/bounds. Final experiment accepted six valid transport fields, rejected string/number/null/list/object grants, unknown key, invalid result_view, boolean/zero limit and max_bytes below4096. PASS is limited to model construction and validation in current Pydantic environment. No production patch, future option schema, MCP transport or complete F1/F11 acceptance was executed.

F5/D9 clarification: helper defaults scratch_on_pythonpath=False for generic selected tests. Q07 explicitly passes True under D9 option(a), False plus bootstrap under option(b); it never relies on helper default. Q04 uses False. D9 remains James's choice.

Follow-up alignment (2026-10-02): the preceding Plan00-only receipt records the earlier remediation. The subsequent Plan00/Plan01 review corrects C08 in F4's proposed preflight and matching no-launch test: both the supplied runtime directory (lexical and resolved) and executable realpath must lie outside root. The symlink regression preserves the trusted external target before the original inside-file fixture mutates its arguments. Plan01's alignment reconciliation records all six follow-up issues. Proposed behavior remains unexecuted; final frozen review/static/preservation results are reported outside file bytes.
