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
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.config import RushConfigError, load_config
from rush.dashboard.server import (
    DashboardContext,
    _ActionDenied,
    _dispatch_memory_archive,
    _dispatch_memory_delete,
    _dispatch_memory_edit,
    _dispatch_memory_promote,
    _s04_effect_ids,
    _validate_memory_owner_scope,
)
from rush.governance.public_operations import build_operations_inventory
from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import make_tool_wrapper
from rush.memory.experience import record_attempt
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

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


# Phase 70 T16: the executor's default scope names each transport's own
# root (cli_root vs mcp_root); only those root-bearing fields are dropped.
_ROOT_BEARING_SCOPE_FIELDS = (
    "logical_root",
    "invocation_start_cwd",
    "original_requested_targets",
    "execution_cwds",
)


def _normalized(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {k: v for k, v in payload.items() if k != "duration_ms"}
    metadata = normalized.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("scope"), dict):
        scope = {
            k: v
            for k, v in metadata["scope"].items()
            if k not in _ROOT_BEARING_SCOPE_FIELDS
        }
        normalized["metadata"] = {**metadata, "scope": scope}
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


# --- M07/M08 (69-dashboard-tui-codex-implementation-review.md): dashboard
# memory-mutation publication refresh and owner-scope authorization -------


@pytest.fixture
def _isolated_projects_data_root(tmp_path, monkeypatch):
    """Isolates the global project registry (`register_project`/
    `resolve_project`) so these tests never touch this OS user's real Rush
    data directory."""
    isolated = tmp_path / "rush-data-default"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: isolated)
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: isolated)
    return isolated


def _registered_ctx(
    tmp_path: Path, data_root: Path, name: str = "proj"
) -> tuple[DashboardContext, str, Path]:
    root = tmp_path / name
    root.mkdir()
    record = register_project(root, data_root=data_root)
    ctx = DashboardContext(
        {record.project_id: {"root": str(root), "name": record.name}},
        bound_host="127.0.0.1",
        bound_port=0,
    )
    return ctx, record.project_id, root


def test_memory_edit_immediately_updates_map_content_and_generation(
    tmp_path, _isolated_projects_data_root
) -> None:
    ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    owner = OwnerScope("project", project_id)
    TypedArtifactStore(root).write(
        MemoryArtifact(
            id="m1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"note": "before"},
            source="s",
            created_at=time.time(),
            owner_scope=owner,
        )
    )
    before = ctx.projects.get(project_id)
    assert before.memory_generation == 0
    assert before.sequence == 1

    status_code, body = _dispatch_memory_edit(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": "m1",
            "expected_version": 1,
            "content": {"note": "after"},
            "apply": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert status_code == 200
    assert body["status"] == "ok"

    after = ctx.projects.get(project_id)
    assert after.memory_generation > before.memory_generation
    assert after.sequence > before.sequence
    memories_by_id = {m["id"]: m for m in after.snapshot["memories"]}
    assert memories_by_id["m1"]["artifact_version"] == 2


def test_memory_archive_delete_promote_each_publish_a_new_generation(
    tmp_path, _isolated_projects_data_root
) -> None:
    ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    for artifact_id in ("m-archive", "m-delete"):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": artifact_id},
                source="s",
                created_at=time.time(),
                owner_scope=owner,
            )
        )
    generation_before = ctx.projects.get(project_id).memory_generation

    _, body = _dispatch_memory_archive(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": "m-archive",
            "expected_version": 1,
            "apply": True,
            "archived": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["status"] == "ok"
    gen_after_archive = ctx.projects.get(project_id).memory_generation
    assert gen_after_archive > generation_before

    _, body = _dispatch_memory_delete(
        ctx,
        project_id,
        {
            "artifact_ids": ["m-delete"],
            "expected_revisions": {"m-delete": 1},
            "scope": "domain_knowledge",
            "apply": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["status"] == "ok"
    gen_after_delete = ctx.projects.get(project_id).memory_generation
    assert gen_after_delete > gen_after_archive

    _, body = _dispatch_memory_promote(
        ctx,
        project_id,
        {
            "subject": "domain_knowledge",
            "content": {"note": "promoted"},
            "source": "s",
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["status"] == "ok"
    gen_after_promote = ctx.projects.get(project_id).memory_generation
    assert gen_after_promote > gen_after_delete


def test_memory_mutations_thread_reserved_effect_ids_into_receipts(
    tmp_path, _isolated_projects_data_root
) -> None:
    """S04 (T034): `_dispatch_memory_edit/_archive/_delete/_promote` must
    persist the ledger-reserved `_s04_effect_ids` sub-key as the receipt
    operation id -- never a separate, generic top-level operation_id (the
    exact bug T017's residual flagged: a reminted id risks a
    mutation_receipts PRIMARY-KEY clobber with an unrelated receipt)."""
    ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    for artifact_id in ("m-edit", "m-archive", "m-delete", "m-delete2"):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": artifact_id},
                source="s",
                created_at=time.time(),
                owner_scope=owner,
            )
        )
    generic_operation_id = "generic-op-should-never-be-used"
    assert store.get_receipt(generic_operation_id) is None

    edit_effect_ids = _s04_effect_ids("memory_edit", {"apply": True})
    _, body = _dispatch_memory_edit(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": "m-edit",
            "expected_version": 1,
            "content": {"note": "after"},
            "apply": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
        edit_effect_ids,
    )
    assert body["status"] == "ok"
    assert store.get_receipt(edit_effect_ids["artifact_edit"]) is not None

    archive_effect_ids = _s04_effect_ids("memory_archive", {"apply": True})
    _, body = _dispatch_memory_archive(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": "m-archive",
            "expected_version": 1,
            "apply": True,
            "archived": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
        archive_effect_ids,
    )
    assert body["status"] == "ok"
    assert store.get_receipt(archive_effect_ids["artifact_archive"]) is not None

    # T040/S04 residual: two targets in one batch prove per-target receipt
    # ids, never one shared id for the whole batch (the gap T034 left).
    delete_args = {
        "artifact_ids": ["m-delete", "m-delete2"],
        "expected_revisions": {"m-delete": 1, "m-delete2": 1},
        "scope": "domain_knowledge",
        "apply": True,
        "owner_scope": owner.as_dict(),
    }
    delete_effect_ids = _s04_effect_ids("memory_delete", delete_args)
    assert set(delete_effect_ids) == {"delete:m-delete", "delete:m-delete2"}
    _, body = _dispatch_memory_delete(
        ctx, project_id, delete_args, {"cache_write": True}, delete_effect_ids
    )
    assert body["status"] == "ok"
    delete_receipt_1 = store.get_receipt(delete_effect_ids["delete:m-delete"])
    delete_receipt_2 = store.get_receipt(delete_effect_ids["delete:m-delete2"])
    assert delete_receipt_1 is not None
    assert delete_receipt_2 is not None
    # Two genuinely distinct receipts, each addressed to its own artifact --
    # never one receipt for the whole batch reused under two lookup keys.
    assert delete_receipt_1["operation_id"] != delete_receipt_2["operation_id"]
    assert delete_receipt_1["artifact_id"] == "m-delete"
    assert delete_receipt_2["artifact_id"] == "m-delete2"

    promote_effect_ids = _s04_effect_ids("memory_promote", {})
    _, body = _dispatch_memory_promote(
        ctx,
        project_id,
        {
            "subject": "domain_knowledge",
            "content": {"note": "promoted"},
            "source": "s",
            "user_stated": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
        promote_effect_ids,
    )
    assert body["status"] == "ok"
    assert body["raw"]["promoted"] is True, (
        "user_stated=True must force promotion for this assertion to be meaningful"
    )
    # T040/S04 residual: promote consumes the two independently-reserved
    # `candidate_create`/`promotion` ids directly -- never a shared base id
    # suffixed into two derived strings (the gap T034 left).
    create_receipt = store.get_receipt(promote_effect_ids["candidate_create"])
    promote_receipt = store.get_receipt(promote_effect_ids["promotion"])
    assert create_receipt is not None
    assert promote_receipt is not None
    assert create_receipt["operation_id"] != promote_receipt["operation_id"]
    base = promote_effect_ids["candidate_create"]
    assert store.get_receipt(f"{base}:create") is None
    assert store.get_receipt(f"{base}:promote") is None

    # None of the above ever wrote a receipt keyed by the generic id.
    assert store.get_receipt(generic_operation_id) is None


def test_promotion_denial_after_candidate_write_still_refreshes_the_real_candidate_commit(
    tmp_path, _isolated_projects_data_root
) -> None:
    ctx, project_id, _root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    owner = OwnerScope("project", project_id)
    generation_before = ctx.projects.get(project_id).memory_generation

    _, body = _dispatch_memory_promote(
        ctx,
        project_id,
        {
            "subject": "domain_knowledge",
            "content": {"note": "candidate"},
            "source": "only-source",
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["status"] == "ok"
    assert body["raw"]["promoted"] is False, (
        "a single-source candidate with user_stated=False must be denied "
        "promotion for this assertion to be meaningful"
    )

    after = ctx.projects.get(project_id)
    assert after.memory_generation > generation_before
    memory_ids = {m["id"] for m in after.snapshot["memories"]}
    assert body["raw"]["artifact"]["id"] in memory_ids


def test_preview_and_zero_write_failure_publish_no_fabricated_sequence_bump(
    tmp_path, _isolated_projects_data_root
) -> None:
    ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    owner = OwnerScope("project", project_id)

    # A preview against a project with no memory store yet must never spring
    # one into existence, and must publish nothing.
    _dispatch_memory_edit(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": "does-not-exist",
            "expected_version": 1,
            "content": {"note": "x"},
            "apply": False,
            "owner_scope": owner.as_dict(),
        },
        {},
    )
    assert not (root / ".rush" / "memory.db").exists()
    record = ctx.projects.get(project_id)
    assert record.memory_generation == 0
    assert record.sequence == 1

    # Seed a real row through a real apply=True dispatch first, so the
    # registry's cached generation is already caught up to the store's real
    # generation -- then a zero-write failure (a stale expected_version)
    # against the now-existing store must publish no *additional* bump.
    _, body = _dispatch_memory_promote(
        ctx,
        project_id,
        {
            "subject": "domain_knowledge",
            "content": {"note": "v1"},
            "source": "s",
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["status"] == "ok"
    artifact_id = body["raw"]["artifact"]["id"]
    seeded = ctx.projects.get(project_id)
    generation_before = seeded.memory_generation
    sequence_before = seeded.sequence

    _, body = _dispatch_memory_edit(
        ctx,
        project_id,
        {
            "scope": "domain_knowledge",
            "id": artifact_id,
            "expected_version": 999,
            "content": {"note": "v2"},
            "apply": True,
            "owner_scope": owner.as_dict(),
        },
        {"cache_write": True},
    )
    assert body["raw"]["code"] == "E_VERSION"
    record_after = ctx.projects.get(project_id)
    assert record_after.memory_generation == generation_before
    assert record_after.sequence == sequence_before


_MEMORY_MUTATION_OPS_FOR_OWNER_TEST = (
    "memory_edit",
    "memory_archive",
    "memory_delete",
    "memory_promote",
    "memory_propose",
    "memory_maintain",
)


@pytest.mark.parametrize("operation", _MEMORY_MUTATION_OPS_FOR_OWNER_TEST)
@pytest.mark.parametrize(
    "bad_owner",
    [
        None,
        {},
        {"kind": "project"},
        {"kind": "bogus", "id": "x"},
        {"kind": "user", "id": ""},
    ],
    ids=["omitted", "empty", "incomplete", "bad_kind", "blank_id"],
)
def test_write_edit_promote_archive_delete_reject_omitted_or_incomplete_owner_before_any_row_change(
    tmp_path, _isolated_projects_data_root, operation, bad_owner
) -> None:
    _ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    arguments = {"owner_scope": bad_owner}

    with pytest.raises(_ActionDenied):
        _validate_memory_owner_scope(
            operation,
            arguments,
            project_id=project_id,
            session_owner_scope_id="sess-1",
        )
    assert not (root / ".rush" / "memory.db").exists()


def test_foreign_project_uuid_owner_rejected_before_reservation(
    tmp_path, _isolated_projects_data_root
) -> None:
    _ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    with pytest.raises(_ActionDenied) as exc_info:
        _validate_memory_owner_scope(
            "memory_edit",
            {"owner_scope": {"kind": "project", "id": "some-other-project-uuid"}},
            project_id=project_id,
            session_owner_scope_id="sess-1",
        )
    assert exc_info.value.status == 400
    assert not (root / ".rush" / "memory.db").exists()


def test_wrong_session_id_owner_rejected(
    tmp_path, _isolated_projects_data_root
) -> None:
    _ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    with pytest.raises(_ActionDenied):
        _validate_memory_owner_scope(
            "memory_edit",
            {"owner_scope": {"kind": "session", "id": "someone-elses-session"}},
            project_id=project_id,
            session_owner_scope_id="this-requests-session",
        )
    assert not (root / ".rush" / "memory.db").exists()


def test_arbitrary_nonempty_user_agent_labels_accepted_structurally_and_persist_unchanged(
    tmp_path, _isolated_projects_data_root
) -> None:
    _ctx, project_id, root = _registered_ctx(tmp_path, _isolated_projects_data_root)
    arguments = {
        "subject": "domain_knowledge",
        "content": {"note": "x"},
        "source": "s",
        "owner_scope": {"kind": "agent", "id": "some-arbitrary-agent-label-123"},
    }
    _validate_memory_owner_scope(
        "memory_propose",
        arguments,
        project_id=project_id,
        session_owner_scope_id="sess-1",
    )
    assert arguments["owner_scope"] == {
        "kind": "agent",
        "id": "some-arbitrary-agent-label-123",
    }

    result = MemoryTool().run(
        root,
        operation="write",
        subject="domain_knowledge",
        content={"note": "x"},
        source="s",
        owner_scope=arguments["owner_scope"],
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert result["status"] == "ok"
    stored_id = result["raw"]["id"]

    with sqlite3.connect(TypedArtifactStore(root).db_path) as conn:
        row = conn.execute(
            "SELECT owner_scope_kind, owner_scope_id FROM memory_artifacts WHERE id = ?",
            (stored_id,),
        ).fetchone()
    assert row == ("agent", "some-arbitrary-agent-label-123")
