"""MC14 (Phase 63 plan §9.1): CLI/MCP parity contract tests for the 13 new memory
operations MC02-MC12 added to `MemoryTool` (expand, link, related, consolidate,
verify_attempt, prepare, resume, intent, recipe, plan_checks, last_success_diagnose,
handoff, receive). Every parity assertion drives the real production routes -- `_run_tool`
(catalog CLI) and `make_tool_wrapper` (catalog MCP), both converging on the same
`InvocationExecutor.execute` -- never a hand-rolled comparison standing in for a live call.

Mutation operations run against a *fresh* store per transport (`_two_seeded_roots`), each
seeded with the same two deterministic artifact IDs, rather than the same store twice --
a mutation applied by the first transport would otherwise still be visible (or create a
cycle/duplicate) when the second transport runs the identical request.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.config import RushConfigError, load_config
from rush.governance.public_operations import build_operations_inventory
from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import make_tool_wrapper
from rush.memory.experience import record_attempt
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.tools.memory import MemoryTool

_NEW_OPERATIONS: tuple[tuple[str, str], ...] = (
    ("expand", "expand"),
    ("link", "link"),
    ("related", "related"),
    ("consolidate", "consolidate"),
    ("verify_attempt", "verify-attempt"),
    ("prepare", "prepare"),
    ("resume", "resume"),
    ("intent", "intent"),
    ("recipe", "recipe"),
    ("plan_checks", "plan-checks"),
    ("last_success_diagnose", "last-success-diagnose"),
    ("handoff", "handoff"),
    ("receive", "receive"),
)

_READ_ONLY_OPERATIONS = {
    "expand",
    "related",
    "prepare",
    "resume",
    "plan_checks",
    "last_success_diagnose",
}

_MUTATION_OPERATIONS = ("link", "consolidate", "handoff")

# Operations whose response embeds a fresh, non-reproducible value (a random session
# capability/id, or a wall-clock expiry) that must be excluded from a byte-identical
# comparison the same way `duration_ms` is -- the field's *presence*, not its exact
# value, is what parity means for these.
_NONDETERMINISTIC_DATA_FIELDS: dict[str, tuple[str, ...]] = {
    "handoff": ("handoff_id", "capability", "expires_at"),
}

_ARTIFACT_A, _ARTIFACT_B = "A1", "A2"


def _seed_store(root: Path) -> None:
    store = TypedArtifactStore(root)
    for artifact_id, body in ((_ARTIFACT_A, "seed A"), (_ARTIFACT_B, "seed B")):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"body": body},
                source="s1",
                created_at=time.time(),
            )
        )


def _two_seeded_roots(tmp_path: Path) -> tuple[Path, Path]:
    """Two independent, identically-seeded stores -- one per transport."""
    mcp_root = tmp_path / "mcp_root"
    cli_root = tmp_path / "cli_root"
    mcp_root.mkdir()
    cli_root.mkdir()
    _seed_store(mcp_root)
    _seed_store(cli_root)
    return mcp_root, cli_root


def _request_for(operation: str) -> dict[str, Any]:
    if operation == "expand":
        return {"id": _ARTIFACT_A, "version": 1}
    if operation == "link":
        return {
            "source_id": _ARTIFACT_A,
            "source_version": 1,
            "target_id": _ARTIFACT_B,
            "target_version": 1,
            "kind": "supersedes",
        }
    if operation == "related":
        return {"id": _ARTIFACT_A, "version": 1}
    if operation == "consolidate":
        return {"symptom": {"kind": "timeout"}}
    if operation == "verify_attempt":
        return {
            "attempt_id": "attempt-1",
            "behavior_ids": ["behavior-1"],
            "contract": {},
            "patch": {"text": "print('noop')"},
        }
    if operation in ("prepare", "resume"):
        return {"task": "fix flaky upload", "conditions": {"runtime": "cpython/3.12"}}
    if operation == "intent":
        return {"action": "check", "intent_id": "intent-1"}
    if operation == "recipe":
        return {"action": "resolve", "recipe_id": "recipe-1"}
    if operation == "plan_checks":
        return {
            "changed_targets": [],
            "required_checks": [
                {
                    "id": "chk1",
                    "argv": ["true"],
                    "cwd": ".",
                    "expected_exit": 0,
                    "timeout_seconds": 5,
                    "permissions": [],
                }
            ],
            "environment": {},
        }
    if operation == "last_success_diagnose":
        return {"behavior_id": "behavior-1", "conditions": {"runtime": "cpython/3.12"}}
    if operation == "handoff":
        return {
            "action": "prepare",
            "receiver_audience": "agent_b",
            "goal": "share evidence",
            "selected_refs": [{"id": _ARTIFACT_A, "version": 1}],
        }
    if operation == "receive":
        return {"session_id": "unknown-session", "capability": "unknown-capability"}
    raise AssertionError(f"no fixture request for operation {operation!r}")


_SESSION_SCOPED_OPERATIONS = {"expand", "related", "prepare", "resume"}


def _mcp_call(
    root: Path, operation: str, request: dict[str, Any], **permission_kwargs: bool
) -> dict[str, Any]:
    tool = MemoryTool()
    executor = InvocationExecutor()
    executor.register("memory", tool.__call__)
    wrapper = make_tool_wrapper(tool, executor)
    kwargs: dict[str, Any] = dict(permission_kwargs)
    if operation in _SESSION_SCOPED_OPERATIONS:
        kwargs["session_allowlist"] = ["s1"]
    result = wrapper(path=root, operation=operation, request=request, **kwargs)
    return dict(result)


def _cli_call(
    root: Path,
    cli_name: str,
    operation: str,
    request: dict[str, Any],
    flags: tuple[str, ...] = (),
) -> dict[str, Any]:
    request_file = root / f"{cli_name.replace('-', '_')}_request.json"
    request_file.write_text(json.dumps(request), encoding="utf-8")
    session_flags: tuple[str, ...] = (
        ("--session", "s1") if operation in _SESSION_SCOPED_OPERATIONS else ()
    )
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "memory",
                cli_name,
                "--input",
                str(request_file),
                "--json",
                *session_flags,
                *flags,
            ],
        )
    finally:
        os.chdir(old_cwd)
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.output
    )
    return json.loads(result.output)


def _normalized(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {k: v for k, v in payload.items() if k != "duration_ms"}
    volatile = _NONDETERMINISTIC_DATA_FIELDS.get(operation)
    if volatile and isinstance(normalized.get("raw"), dict):
        raw = dict(normalized["raw"])
        data = dict(raw.get("data") or {})
        for field in volatile:
            data.pop(field, None)
        delta = data.get("delta")
        if isinstance(delta, dict):
            data["delta"] = {k: v for k, v in delta.items() if k != "session_id"}
        raw["data"] = data
        normalized["raw"] = raw
    return normalized


@pytest.mark.parametrize("operation,cli_name", _NEW_OPERATIONS)
def test_cli_mcp_operation_payload_and_permissions_match(
    tmp_path: Path, operation: str, cli_name: str
) -> None:
    """MC14.1 RED->GREEN parity matrix: calling every new §9.1 leaf through Click and MCP
    with the identical request against identically-seeded stores produces identical
    status/raw (excluding duration and, for `handoff`, its freshly-generated
    session_id/capability/expiry)."""
    mcp_root, cli_root = _two_seeded_roots(tmp_path)
    request = _request_for(operation)
    grant_flags = ("--allow-cache-write", "--allow-artifact-write", "--allow-build")

    mcp_out = _mcp_call(
        mcp_root,
        operation,
        request,
        allow_cache_write=True,
        allow_artifact_write=True,
        allow_build=True,
    )
    cli_out = _cli_call(cli_root, cli_name, operation, request, flags=grant_flags)
    assert _normalized(operation, cli_out) == _normalized(operation, mcp_out)


@pytest.mark.parametrize(
    "operation,cli_name",
    [(op, name) for op, name in _NEW_OPERATIONS if op in _MUTATION_OPERATIONS],
)
def test_missing_mutation_grant_fails_equally(
    tmp_path: Path, operation: str, cli_name: str
) -> None:
    """MC14.1: a mutation operation with zero grants must fail identically -- same
    E_PERMISSION code -- on both transports."""
    mcp_root, cli_root = _two_seeded_roots(tmp_path)
    request = _request_for(operation)

    mcp_out = _mcp_call(mcp_root, operation, request)
    cli_out = _cli_call(cli_root, cli_name, operation, request)
    assert _normalized(operation, cli_out) == _normalized(operation, mcp_out)
    assert cli_out["raw"]["code"] == "E_PERMISSION"


def test_all_memory_operations_in_public_manifest() -> None:
    """MC14.3: every new §9.1 leaf resolves through `rush.tools.memory:MemoryTool` in the
    live public operations inventory, same as the pre-existing memory write/promote/maintain
    admin operations."""
    inventory = build_operations_inventory()
    by_cli = {op.cli_command: op for op in inventory if op.cli_command}
    for _operation, cli_name in _NEW_OPERATIONS:
        full_name = f"memory {cli_name}"
        assert full_name in by_cli, (
            f"{full_name} missing from public operations inventory"
        )
        op = by_cli[full_name]
        assert op.canonical_impl == "rush.tools.memory:MemoryTool"
        assert op.kind == "admin"


def test_legacy_cli_and_mcp_calls_remain_valid(tmp_path: Path) -> None:
    """MC14: the pre-MC14 legacy shape (ask/recall/list/write/promote/maintain, called
    without `request=`) is unchanged by this packet on both the CLI and the direct
    MemoryTool call MCP ultimately reaches."""
    tool = MemoryTool()
    write_result = tool(
        path=tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "legacy content"},
        source="legacy-src",
        allow_cache_write=True,
    )
    assert write_result["status"] == "ok"

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "memory",
                "recall",
                "domain_knowledge",
                "legacy",
                "--session",
                "legacy-src",
                "--json",
            ],
        )
    finally:
        os.chdir(old_cwd)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["raw"], "legacy recall must still find the seeded artifact"

    executor = InvocationExecutor()
    executor.register("memory", tool.__call__)
    wrapper = make_tool_wrapper(tool, executor)
    mcp_result = wrapper(
        path=tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="legacy",
        session_allowlist=["legacy-src"],
    )
    assert mcp_result["status"] == "ok"
    assert mcp_result["raw"]


def test_config_rejects_unknown_memory_keys(tmp_path: Path) -> None:
    """MC14.3: `[tools.memory]` accepts exactly the catalog's declared keys (currently
    `record`) and rejects any unknown key -- config.py's existing generic per-tool option
    validation, exercised directly against MemoryTool's ToolSpec."""
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    (good_dir / "rush.toml").write_text(
        "[tools.memory]\nrecord = true\n", encoding="utf-8"
    )
    cfg = load_config(start=good_dir)
    assert cfg.tools["memory"].options["record"] is True

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "rush.toml").write_text(
        "[tools.memory]\nbogus_key = true\n", encoding="utf-8"
    )
    with pytest.raises(RushConfigError, match="bogus_key"):
        load_config(start=bad_dir)


@pytest.mark.parametrize(
    "operation,cli_name",
    [(op, name) for op, name in _NEW_OPERATIONS if op in _READ_ONLY_OPERATIONS],
)
def test_read_operations_do_not_gain_write_permission(
    tmp_path: Path, operation: str, cli_name: str
) -> None:
    """MC14: a read-only §9.1 leaf must never require a mutation grant, and its governance
    classification must say `read-only` -- a read operation can never gain write permission
    through this wiring. (Every read-only op here is called with a valid session_allowlist
    where relevant, so a resulting E_PERMISSION can only mean a mutation-grant gate, not the
    unrelated fail-closed empty-session-scope gate.)"""
    root = tmp_path
    _seed_store(root)
    request = _request_for(operation)
    result = _mcp_call(root, operation, request)  # zero allow_* permission kwargs
    code = result["raw"]["code"] if isinstance(result.get("raw"), dict) else None
    assert code != "E_PERMISSION", (
        f"{operation} unexpectedly required a permission grant"
    )

    inventory = build_operations_inventory()
    by_cli = {op.cli_command: op for op in inventory if op.cli_command}
    manifest_op = by_cli[f"memory {cli_name}"]
    assert manifest_op.effect_class == "read-only"


def _rush_bin() -> str:
    candidate = Path(sys.executable).with_name("rush")
    assert candidate.exists(), (
        "expected a sibling rush console script for this interpreter"
    )
    return str(candidate)


def test_stdio_stdout_contains_only_jsonrpc(tmp_path: Path) -> None:
    """MC14.4: a real `rush mcp serve` stdio transport, driven by a hand-framed JSON-RPC
    handshake over its actual stdin/stdout pipes, emits nothing but newline-delimited
    JSON-RPC on stdout -- logging/warnings land on stderr instead, never interleaved."""
    from mcp import types

    proc = subprocess.Popen(
        [_rush_bin(), "mcp", "serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        text=True,
        bufsize=1,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        init_params = types.InitializeRequestParams(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ClientCapabilities(),
            clientInfo=types.Implementation(name="mc14-contract-test", version="0"),
        )
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": json.loads(
                        init_params.model_dump_json(by_alias=True, exclude_none=True)
                    ),
                }
            )
            + "\n"
        )
        proc.stdin.flush()
        init_response = json.loads(proc.stdout.readline())
        assert init_response["jsonrpc"] == "2.0"
        assert "result" in init_response

        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        proc.stdin.flush()

        call_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "rush_memory",
                "arguments": {
                    "path": str(tmp_path),
                    "operation": "plan_checks",
                    "request": {
                        "changed_targets": [],
                        "required_checks": [],
                        "environment": {},
                    },
                },
            },
        }
        proc.stdin.write(json.dumps(call_request) + "\n")
        proc.stdin.flush()
        call_response = json.loads(proc.stdout.readline())
        assert call_response["jsonrpc"] == "2.0"
        assert call_response["id"] == 2
        tool_payload = json.loads(call_response["result"]["content"][0]["text"])
        assert tool_payload["raw"]["operation"] == "plan_checks"
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    leftover_stdout = proc.stdout.read()
    for line in leftover_stdout.splitlines():
        if not line.strip():
            continue
        json.loads(line)  # every remaining stdout line must itself be valid JSON-RPC


def test_documented_examples_execute(tmp_path: Path) -> None:
    """MC14.4: the three documented usage examples (compact recall->expand, isolated
    repair, restricted handoff) run against real fixtures and report measured results --
    recorded verbatim in docs/phase-plans/MC14.md, never claimed unmeasured."""
    tool = MemoryTool()

    # Example 1: compact recall -> expand exact bytes.
    write_result = tool(
        path=tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "csv export helper uses io.StringIO"},
        source="csv-helper",
        allow_cache_write=True,
    )
    artifact_id = write_result["raw"]["id"]
    recall_result = tool(
        path=tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="csv",
        request={"view": "compact", "limit": 8},
        session_allowlist=["csv-helper"],
    )
    assert recall_result["status"] == "ok", recall_result
    items = recall_result["raw"]["data"]["items"]
    assert any(item["id"] == artifact_id for item in items)

    expand_out = _cli_call(
        tmp_path,
        "expand",
        "expand",
        {"id": artifact_id, "version": 1},
        flags=("--session", "csv-helper"),
    )
    assert expand_out["status"] == "ok", expand_out
    decoded = base64.b64decode(expand_out["raw"]["data"]["content_base64"]).decode(
        "utf-8"
    )
    assert decoded == json.dumps({"body": "csv export helper uses io.StringIO"})

    # Example 2: isolated repair -- a recorded failed attempt surfaces through `prepare`.
    conditions = {
        "runtime": "cpython/3.12",
        "platform": "test/test",
        "dependencies": {"parser": "1.0"},
        "config_digest": "cfg-1",
        "source_digest": "src-1",
    }
    record_attempt(
        project_root=tmp_path,
        symptom="fix upload timeout",
        hypothesis="timeout too low",
        patch_hash="patch-1",
        conditions=conditions,
        receipt_ref="receipt-1",
        behavior_ids=["upload-behavior"],
        outcome="failed",
    )
    prepare_out = _cli_call(
        tmp_path,
        "prepare",
        "prepare",
        {"task": "fix upload timeout", "conditions": conditions},
        flags=("--session", "repair_attempt:fix upload timeout"),
    )
    assert prepare_out["status"] in ("ok", "warn"), prepare_out
    assert prepare_out["raw"]["data"]["failures"], (
        "prepare must surface the recorded failed attempt"
    )

    # Example 3: restricted handoff -- prepare a session, then receive its exact delta.
    handoff_out = _cli_call(
        tmp_path,
        "handoff",
        "handoff",
        {
            "action": "prepare",
            "receiver_audience": "agent_b",
            "goal": "share the csv helper evidence",
            "selected_refs": [{"id": artifact_id, "version": 1}],
        },
        flags=("--allow-cache-write",),
    )
    assert handoff_out["status"] == "ok", handoff_out
    session_id = handoff_out["raw"]["data"]["handoff_id"]
    capability = handoff_out["raw"]["data"]["capability"]
    receive_out = _cli_call(
        tmp_path,
        "receive",
        "receive",
        {"session_id": session_id, "capability": capability},
    )
    assert receive_out["status"] == "ok", receive_out
    changes = receive_out["raw"]["data"]["changes"]
    assert any(change["id"] == artifact_id for change in changes)
