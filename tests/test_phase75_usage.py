"""Final delivered memory receipts: real producers, transport ownership and readonly readers."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_phase72_memory_public import (
    PERM_NONE,
    PERM_W,
    PROJECT_ROOT,
    _t06_isolated_home,  # noqa: F401 -- pytest discovers imported autouse fixture
    code,
    make_env,
    r_list,
)

from rush.tools.memory import MemoryTool


@pytest.mark.parametrize(
    "transport", ["in_process", "cli_json", "cli_human", "mcp_stdio"]
)
def test_phase75_admission_rejection_counts_actual_delivery(
    tmp_path, monkeypatch, transport
):
    import hashlib
    import io
    from threading import Lock

    from mcp.types import CallToolResult
    from test_memory_activation_lifecycle import bootstrap_world
    from test_phase72_memory_public import _cli_result

    from rush import mcp as server
    from rush.delivery import compact
    from rush.mcp_support.tool_registry import _memory_frame
    from rush.memory.retrieval import _count_tokens

    env, request = bootstrap_world(tmp_path, create_store=False)
    request = {**request, "max_tokens": 1}
    if transport == "cli_human":
        from rich.console import Console

        from rush import theme

        monkeypatch.setattr(
            theme,
            "_shared_console",
            Console(
                force_terminal=True,
                no_color=False,
                color_system="truecolor",
                width=43,
                theme=theme.RUSH_THEME,
            ),
        )
    produced = []
    run = MemoryTool.run

    def actual_result(self, *args, **kwargs):
        result = run(self, *args, **kwargs)
        produced.append(result)
        return result

    monkeypatch.setattr(MemoryTool, "run", actual_result)
    frames = []
    finalize = compact.finalize_memory_events

    def measured(frame, body, **kwargs):
        finalize(frame, body, **kwargs)
        frames.append(frame)

    monkeypatch.setattr(compact, "finalize_memory_events", measured)
    if transport in {"cli_json", "cli_human"}:
        outcome = _cli_result(
            env.root,
            [
                "memory",
                "bootstrap",
                "--project",
                str(env.root),
                "--task-id",
                request["task_id"],
                "--task-kind",
                request["task_kind"],
                "--query",
                request["query"],
                "--max-tokens",
                "1",
            ]
            + (["--json"] if transport == "cli_json" else []),
        )
        delivered = outcome.stdout_bytes
        result = json.loads(delivered) if transport == "cli_json" else produced[-1]
    elif transport == "in_process":
        frame = compact.FrameContext(transport, None, pending_memory_events=[])
        result = MemoryTool().run(
            env.root, operation="bootstrap", request=request, frame=frame
        )
        delivered = compact.canonical_json(result)
        compact.finalize_memory_events(
            frame,
            delivered,
            accepted=compact.accepted_memory_result(result),
            outcome=compact.memory_delivery_outcome(result),
        )
    else:
        state = ({}, Lock())
        token = compact.MCP_PENDING_FRAMES.set(state)
        monkeypatch.setattr(compact, "current_request_id", lambda: "admission-7")
        sink = io.BytesIO()
        writer = server._ReceiptStdout(server._Utf8Stdout(sink), state)
        try:
            compact.reserve_mcp_request("admission-7")
            frame = _memory_frame(
                lambda: (
                    lambda value: CallToolResult(
                        content=[], structuredContent=dict(value)
                    )
                ),
                dict,
            )
            result = MemoryTool().run(
                env.root, operation="bootstrap", request=request, frame=frame
            )

            async def emit():
                await writer.write(frame.emit(result).decode("utf-8"))
                await writer.flush()

            asyncio.run(emit())
            delivered = sink.getvalue()
        finally:
            compact.MCP_PENDING_FRAMES.reset(token)
    assert result["raw"]["code"] == "E_INPUT"
    assert result["raw"]["data"]["admission_failure"] is True
    assert not compact.accepted_memory_result(result)
    assert len(frames) == 1
    assert frames[0].delivery_usage == {
        "outcome": "admission_failure",
        "tokens": _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
        "frame_bytes": len(delivered),
        "frame_sha256": hashlib.sha256(delivered).hexdigest(),
        "transport": transport,
        "count_basis": "transport_frame:cl100k_base",
        "persisted": False,
        "context_inserted": False,
    }
    assert not (env.root / ".rush/telemetry/tokens.db").exists()
    assert not (env.root / ".rush/memory.db").exists()
    if transport == "cli_human":
        assert b"\x1b[" in delivered
        assert compact.frame_bytes(frames[0], result) == delivered
        minimum = result["raw"]["data"]["required"]["max_tokens"]
        budget_query = (
            "Find verified checkpoints, unresolved errors, permission decisions, "
            "and evidence needed to continue this memory task. "
        ) * 16
        next_output = _cli_result(
            env.root,
            [
                "memory",
                "bootstrap",
                "--project",
                str(env.root),
                "--task-id",
                request["task_id"],
                "--task-kind",
                request["task_kind"],
                "--query",
                budget_query,
                "--session-binding",
                request["session_binding"],
                "--max-tokens",
                str(minimum),
            ],
        )
        admitted = produced[-1]
        assert admitted["raw"]["code"] == "E_BUDGET", admitted
        assert admitted["raw"]["data"]["admission_failure"] is False
        assert admitted["raw"]["data"]["required"]["max_tokens"] > minimum
        assert frames[-1].delivery_usage["outcome"] == "budget_failure"
        assert frames[-1].delivery_usage["tokens"] <= minimum
        assert frames[-1].delivery_usage["frame_bytes"] == len(next_output.stdout_bytes)
        assert compact.frame_bytes(frames[-1], admitted) == next_output.stdout_bytes


@pytest.mark.parametrize("route", ["direct_call", "executor"])
def test_phase75_rejection_inprocess_owner(tmp_path, monkeypatch, route):
    import hashlib

    from test_memory_activation_lifecycle import bootstrap_world

    from rush.contracts.results import ToolResultV1
    from rush.delivery import compact
    from rush.invocation import InvocationExecutor, resolve_invocation
    from rush.memory.retrieval import _count_tokens

    env, request = bootstrap_world(tmp_path, create_store=False)
    request = {**request, "max_tokens": 1}
    context = resolve_invocation(
        {
            "operation_id": "memory",
            "path": str(env.root),
            "operation": "bootstrap",
            "request": request,
        },
        "cli",
        workspace_root=env.root,
        permissions=PERM_NONE,
    )
    frames = []
    finalize = compact.finalize_memory_events

    def measured(frame, body, **kwargs):
        finalize(frame, body, **kwargs)
        frames.append(frame)

    monkeypatch.setattr(compact, "finalize_memory_events", measured)
    tool = MemoryTool()
    if route == "executor":
        executor = InvocationExecutor()
        executor.register("memory", tool)
        result = executor.execute(context)
    else:
        result = tool(env.root, operation="bootstrap", request=request, context=context)
    projection = result.to_dict() if isinstance(result, ToolResultV1) else result
    assert projection["raw"]["code"] == "E_INPUT"
    delivered = compact.canonical_json(projection)
    assert len(frames) == 1
    usage = frames[0].delivery_usage
    assert usage["tokens"] == _count_tokens(delivered.decode(), "cl100k_base")
    assert usage["frame_bytes"] == len(delivered)
    assert usage["frame_sha256"] == hashlib.sha256(delivered).hexdigest()
    assert usage["outcome"] == "admission_failure" and usage["persisted"] is False
    assert usage["context_inserted"] is False
    assert not (env.root / ".rush/telemetry/tokens.db").exists()
    assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("failure", ["write", "flush", "cancel"])
def test_phase75_cli_rejection_failed_emit_has_no_usage(
    tmp_path, monkeypatch, failure, as_json
):
    import io

    from test_memory_activation_lifecycle import bootstrap_world
    from test_phase72_memory_public import _cli_result

    from rush.cli_support import rendering
    from rush.delivery import compact

    env, request = bootstrap_world(tmp_path, create_store=False)
    frames = []
    prepare = compact.prepare_memory_delivery

    def prepared(encoding):
        prepare(encoding)
        frames.append(compact.RECEIPT_FRAME.get())

    class Sink(io.BytesIO):
        def write(self, body):
            if failure == "write":
                return super().write(body[:-1])
            return super().write(body)

        def flush(self):
            if failure == "flush":
                raise OSError("fixture flush refused")
            if failure == "cancel":
                raise asyncio.CancelledError()

    monkeypatch.setattr(compact, "prepare_memory_delivery", prepared)
    sink = Sink()
    monkeypatch.setattr(rendering.click, "get_binary_stream", lambda name: sink)
    arguments = [
        "memory",
        "bootstrap",
        "--project",
        str(env.root),
        "--task-id",
        request["task_id"],
        "--task-kind",
        request["task_kind"],
        "--query",
        request["query"],
        "--max-tokens",
        "1",
    ] + (["--json"] if as_json else [])
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            _cli_result(env.root, arguments)
    else:
        outcome = _cli_result(env.root, arguments)
        assert isinstance(outcome.exception, OSError)
    assert len(frames) == 1 and frames[0].delivery_usage == {}
    assert not (env.root / ".rush/telemetry/tokens.db").exists()
    assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("ending", ["emitted", "revoked", "no_grant"])
def test_phase75_admitted_budget_failure_cost(tmp_path, ending):
    import hashlib
    import uuid

    from test_memory_capsule import (
        make_env as capsule_env,
    )
    from test_memory_capsule import (
        perms,
        put_checkpoint,
        put_evidence,
    )

    from rush.delivery import compact
    from rush.memory import authorization as auth
    from rush.memory.retrieval import _count_tokens
    from rush.token_economy.telemetry import (
        memory_frame_usage,
        read_memory_frame_receipts_readonly,
    )

    env = capsule_env(tmp_path, seed=False)
    put_evidence(env, "ev1", body={"claim": "required correctness evidence " * 3000})
    put_evidence(env, "ev2")
    put_checkpoint(env, "cp1")
    frame = compact.FrameContext("in_process", None, pending_memory_events=[])
    result = MemoryTool().run(
        env.root,
        operation="capsule",
        request={
            "action": "preview_export",
            "output": str(env.outside / "unused.json"),
            "invocation_id": str(uuid.uuid4()),
            "max_tokens": 1024,
        },
        permissions=perms(cache=ending != "no_grant", artifact=False),
        frame=frame,
    )
    assert result["raw"]["code"] == "E_BUDGET", result
    assert result["raw"]["data"]["admission_failure"] is False
    assert not compact.accepted_memory_result(result)
    assert len(frame.pending_memory_events) == (ending != "no_grant")
    db = env.root / ".rush/telemetry/tokens.db"
    assert not db.exists()
    if ending == "revoked":
        auth.revoke_memory_scope(
            grant_id=env.grant["grant_id"],
            expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
            consent=True,
        )
    delivered = compact.canonical_json(result)
    compact.finalize_memory_events(
        frame,
        delivered,
        accepted=False,
        outcome=compact.memory_delivery_outcome(result),
    )
    expected_tokens = _count_tokens(delivered.decode(), "cl100k_base")
    assert frame.delivery_usage["tokens"] == expected_tokens
    assert frame.delivery_usage["frame_sha256"] == hashlib.sha256(delivered).hexdigest()
    assert frame.delivery_usage["outcome"] == "budget_failure"
    assert frame.delivery_usage["context_inserted"] is False
    assert frame.delivery_usage["persisted"] is (ending == "emitted")
    assert db.exists() is (ending == "emitted")
    if ending == "emitted":
        rows = read_memory_frame_receipts_readonly(env.root)
        assert len(rows) == 1 and rows[0]["kind"] == "budget_failure"
        assert rows[0]["tokens"] == expected_tokens
        summary = memory_frame_usage(rows)
        assert summary["failures_by_count_basis"] == {
            "transport_frame:cl100k_base": {
                "budget_failure": {
                    "events": 1,
                    "tokens": expected_tokens,
                    "bytes": len(delivered),
                }
            }
        }
        compact.finalize_memory_events(
            frame, delivered, accepted=False, outcome="budget_failure"
        )
        assert len(read_memory_frame_receipts_readonly(env.root)) == 1


@pytest.mark.parametrize("failure", ["write", "flush", "cancel", "error_response"])
def test_phase75_rejection_failed_emit_has_no_usage(tmp_path, monkeypatch, failure):
    import io
    from threading import Lock

    from mcp.types import CallToolResult, ErrorData, JSONRPCError
    from test_memory_activation_lifecycle import bootstrap_world

    from rush import mcp as server
    from rush.delivery import compact
    from rush.mcp_support.tool_registry import _memory_frame

    env, request = bootstrap_world(tmp_path, create_store=False)
    state = ({}, Lock())
    token = compact.MCP_PENDING_FRAMES.set(state)
    monkeypatch.setattr(compact, "current_request_id", lambda: 7)

    class Sink(io.BytesIO):
        def write(self, body):
            if failure == "write":
                return super().write(body[:-1])
            return super().write(body)

        def flush(self):
            if failure == "flush":
                raise OSError("fixture flush refused")
            if failure == "cancel":
                raise asyncio.CancelledError()

    writer = server._ReceiptStdout(server._Utf8Stdout(Sink()), state)
    try:
        compact.reserve_mcp_request(7)
        frame = _memory_frame(
            lambda: (
                lambda value: CallToolResult(content=[], structuredContent=dict(value))
            ),
            dict,
        )
        result = MemoryTool().run(
            env.root,
            operation="bootstrap",
            request={**request, "max_tokens": 1},
            frame=frame,
        )
        assert result["raw"]["code"] == "E_INPUT"
        line = frame.emit(result).decode()
        if failure == "error_response":
            line = (
                JSONRPCError(
                    jsonrpc="2.0", id=7, error=ErrorData(code=0, message="cancelled")
                ).model_dump_json()
                + "\n"
            )

        async def emit():
            await writer.write(line)
            await writer.flush()

        if failure == "error_response":
            asyncio.run(emit())
        else:
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else OSError
            ):
                asyncio.run(emit())
        assert frame.delivery_usage == {}
        assert not (env.root / ".rush/telemetry/tokens.db").exists()
    finally:
        compact.MCP_PENDING_FRAMES.reset(token)


def test_phase75_dashboard_receipt_matches_flushed_body(tmp_path, monkeypatch):
    import hashlib
    import sqlite3
    import uuid
    from threading import Event

    from test_phase72_memory_ui import SUBJECT, _dashboard, _http, _world

    from rush.memory.retrieval import _count_tokens
    from rush.token_economy.telemetry import TelemetryStore

    done = Event()
    original = TelemetryStore.record_memory_event

    def recorded(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        done.set()
        return result

    monkeypatch.setattr(TelemetryStore, "record_memory_event", recorded)
    world = _world(tmp_path)
    dash = _dashboard(world)
    try:
        payload = json.dumps(
            {
                "schema_version": 1,
                "operation": "memory_query",
                "arguments": {
                    "schema_version": 2,
                    "subjects": [SUBJECT],
                    "query": "needle",
                    "mode": "list",
                },
                "grants": {"cache_write": True},
                "expected": {},
                "request_id": str(uuid.uuid4()),
            }
        ).encode("utf-8")
        response = _http(
            "POST",
            f"{dash.base}/api/projects/{dash.project_id}/actions",
            {
                "Cookie": dash.cookie,
                "X-Rush-CSRF": dash.csrf,
                "Origin": dash.base,
                "Content-Type": "application/json",
            },
            payload,
        )
        delivered = response.read()
        assert response.status == 200
        assert code(json.loads(delivered)["data"]) == "OK"
        assert done.wait(3), "successful HTTP delivery never finalized its receipt"
        db = world.root / ".rush/telemetry/tokens.db"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT tokens,frame_bytes,frame_sha256,transport,count_basis FROM memory_events"
            ).fetchall()
        assert rows == [
            (
                _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
                len(delivered),
                hashlib.sha256(delivered).hexdigest(),
                "dashboard",
                "transport_frame:cl100k_base",
            )
        ]
    finally:
        dash.stop()


@pytest.mark.parametrize("create_store", [True, False])
def test_phase75_inprocess_receipt_is_delivered_frame(
    tmp_path: Path, create_store: bool
) -> None:
    import hashlib
    import sqlite3

    from rush.delivery import compact
    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path, create_store=create_store)
    result = MemoryTool().run(
        env.root, operation="list", request=r_list(), permissions=PERM_W
    )
    assert code(result) == "OK"
    delivered = compact.canonical_json(result)
    db = env.root / ".rush/telemetry/tokens.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT tokens,frame_bytes,frame_sha256,transport,count_basis FROM memory_events WHERE kind='retrieval'"
        ).fetchall()
    assert rows == [
        (
            _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
            len(delivered),
            hashlib.sha256(delivered).hexdigest(),
            "in_process",
            "transport_frame:cl100k_base",
        )
    ]
    if not create_store:
        assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("route", ["direct_call", "executor"])
@pytest.mark.parametrize("create_store", [True, False])
@pytest.mark.parametrize("granted", [True, False])
def test_phase75_context_bound_inprocess_receipt(
    tmp_path: Path,
    route: str,
    create_store: bool,
    granted: bool,
) -> None:
    import hashlib
    import sqlite3

    from rush.contracts.results import ToolResultV1
    from rush.delivery import compact
    from rush.invocation.executor import InvocationExecutor
    from rush.invocation.resolver import resolve_invocation
    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path, create_store=create_store)
    permissions = PERM_W if granted else PERM_NONE
    context = resolve_invocation(
        {
            "operation_id": "memory",
            "path": str(env.root),
            "operation": "list",
            "request": r_list(),
        },
        "cli",
        workspace_root=env.root,
        permissions=permissions,
    )
    assert compact.RECEIPT_FRAME.get() is None
    assert compact.MEMORY_FRAME.get() is None
    tool = MemoryTool()
    if route == "executor":
        executor = InvocationExecutor()
        executor.register("memory", tool)
        result = executor.execute(context)
    else:
        result = tool(
            env.root,
            operation="list",
            request=r_list(),
            allow_cache_write=granted,
            context=context,
        )
    projection = result.to_dict() if isinstance(result, ToolResultV1) else result
    assert code(projection) == "OK"
    assert compact.RECEIPT_FRAME.get() is None
    assert compact.MEMORY_FRAME.get() is None
    db = env.root / ".rush/telemetry/tokens.db"
    if granted:
        delivered = compact.canonical_json(projection)
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT tokens,frame_bytes,frame_sha256,transport,count_basis "
                "FROM memory_events WHERE kind='retrieval'"
            ).fetchall()
        assert rows == [
            (
                _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
                len(delivered),
                hashlib.sha256(delivered).hexdigest(),
                "in_process",
                "transport_frame:cl100k_base",
            )
        ]
    else:
        assert not (env.root / ".rush/telemetry").exists()
    if not create_store:
        assert not (env.root / ".rush/memory.db").exists()


def test_phase75_stdio_receipt_matches_stdout(tmp_path: Path) -> None:
    import hashlib
    import queue
    import sqlite3
    import threading

    from mcp.types import LATEST_PROTOCOL_VERSION

    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path)
    proc = subprocess.Popen(
        [sys.executable, "-m", "rush.cli", "mcp", "serve"],
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=dict(os.environ),
    )
    assert proc.stdin is not None and proc.stdout is not None
    lines: queue.Queue[bytes] = queue.Queue()

    def read_lines() -> None:
        for line in proc.stdout:
            lines.put(line)

    threading.Thread(target=read_lines, daemon=True).start()

    def send(message: dict[str, Any]) -> None:
        proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def receive(rid: int | str) -> tuple[dict[str, Any], bytes]:
        while True:
            line = lines.get(timeout=30)
            message = json.loads(line)
            if type(message.get("id")) is type(rid) and message.get("id") == rid:
                return message, line

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "phase75-receipt", "version": "1"},
                },
            }
        )
        initialized, _ = receive(0)
        assert "result" in initialized
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": "receipt-7",
                "method": "tools/call",
                "params": {
                    "name": "rush_memory",
                    "arguments": {
                        "path": str(env.root),
                        "operation": "list",
                        "request": r_list(),
                        "allow_cache_write": True,
                    },
                },
            }
        )
        response, delivered = receive("receipt-7")
        assert not response["result"].get("isError", False)
        assert code(response["result"]["structuredContent"]) == "OK"
        proc.stdin.close()
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        proc.stdout.close()
    db = env.root / ".rush/telemetry/tokens.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT tokens,frame_bytes,frame_sha256,transport,count_basis FROM memory_events WHERE kind='retrieval'"
        ).fetchall()
    assert rows == [
        (
            _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
            len(delivered),
            hashlib.sha256(delivered).hexdigest(),
            "mcp_stdio",
            "transport_frame:cl100k_base",
        )
    ]


@pytest.mark.parametrize("collision_after_write", [False, True])
def test_mcp_duplicate_id_slot_retires_after_flush(
    monkeypatch: pytest.MonkeyPatch,
    collision_after_write: bool,
) -> None:
    import asyncio
    import io
    from threading import Lock

    from mcp.types import CallToolResult, JSONRPCRequest, JSONRPCResponse

    from rush import mcp as server
    from rush.delivery import compact

    recorded: list[tuple[compact.FrameContext, bytes, bool]] = []

    def record(
        frame: compact.FrameContext,
        body: bytes,
        *,
        accepted: bool,
        outcome: compact.MemoryDeliveryOutcome | None = None,
    ) -> None:
        assert outcome is None
        recorded.append((frame, body, accepted))

    monkeypatch.setattr(compact, "finalize_memory_events", record)

    def reply(rid: int | str) -> str:
        result = CallToolResult(
            content=[],
            isError=False,
            structuredContent={"tool": "memory", "status": "ok", "raw": {"code": "OK"}},
        )
        return (
            JSONRPCResponse(
                jsonrpc="2.0",
                id=rid,
                result=result.model_dump(mode="json", by_alias=True, exclude_none=True),
            ).model_dump_json(by_alias=True, exclude_none=True)
            + "\n"
        )

    async def trace() -> None:
        state: compact.MCPReceiptState = ({}, Lock())
        writer = server._ReceiptStdout(server._Utf8Stdout(io.BytesIO()), state)
        token = compact.MCP_PENDING_FRAMES.set(state)
        key = (int, 7)
        try:
            a = compact.FrameContext("mcp_stdio", 7, pending_memory_events=[])
            b = compact.FrameContext("mcp_stdio", 7, pending_memory_events=[])
            compact.reserve_mcp_request(7)
            compact.register_mcp_receipt_frame(a)
            if collision_after_write:
                await writer.write(reply(7))
            compact.reserve_mcp_request(7)
            compact.register_mcp_receipt_frame(b)
            if not collision_after_write:
                await writer.write(reply(7))
            await writer.flush()
            slot = state[0][key]
            assert slot.frame is None
            assert slot.outstanding == 1 and slot.queued == 0
            assert recorded == []

            c = compact.FrameContext("mcp_stdio", 7, pending_memory_events=[])
            compact.reserve_mcp_request(7)
            compact.register_mcp_receipt_frame(c)
            assert state[0][key] is slot and slot.outstanding == 2
            await writer.write(reply(7) + reply(7))
            await writer.flush()
            assert key not in state[0]
            assert recorded == []

            d = compact.FrameContext("mcp_stdio", 7, pending_memory_events=[])
            compact.reserve_mcp_request(7)
            compact.register_mcp_receipt_frame(d)
            assert state[0][key] is not slot
            new_slot = state[0][key]
            request_line = (
                JSONRPCRequest(
                    jsonrpc="2.0", id=7, method="roots/list", params={}
                ).model_dump_json(by_alias=True, exclude_none=True)
                + "\n"
            )
            await writer.write(request_line)
            await writer.flush()
            assert state[0][key] is new_slot
            assert new_slot.outstanding == 1 and new_slot.queued == 0
            assert recorded == []
            await writer.write(reply(7))
            await writer.flush()
            assert key not in state[0]
            assert len(recorded) == 1 and recorded[0][0] is d and recorded[0][2] is True

            e = compact.FrameContext("mcp_stdio", 7, pending_memory_events=[])
            f = compact.FrameContext("mcp_stdio", "7", pending_memory_events=[])
            compact.reserve_mcp_request(7)
            compact.register_mcp_receipt_frame(e)
            compact.reserve_mcp_request("7")
            compact.register_mcp_receipt_frame(f)
            await writer.write(reply("7") + reply(7))
            await writer.flush()
            assert state[0] == {}
            assert len(recorded) == 3
            assert recorded[1][0] is f and recorded[2][0] is e
        finally:
            writer.discard()
            compact.MCP_PENDING_FRAMES.reset(token)

    asyncio.run(trace())


@pytest.mark.parametrize("duplicate_kind", ["nonmemory", "invalid_params"])
def test_phase75_mcp_foreign_id_collision_cannot_steal_memory_receipt(
    tmp_path: Path,
    duplicate_kind: str,
) -> None:
    import hashlib
    import io
    import sqlite3
    from threading import Lock
    from typing import cast

    from anyio.streams.memory import MemoryObjectReceiveStream
    from mcp.shared.message import SessionMessage
    from mcp.types import LATEST_PROTOCOL_VERSION, CallToolRequest, JSONRPCMessage

    from rush import mcp as server_module
    from rush.delivery import compact
    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path)

    async def trace() -> bytes:
        import anyio

        server = server_module.build_server()
        core = server._mcp_server
        original = core.request_handlers[CallToolRequest]
        started = {"receipt-a": anyio.Event(), "receipt-b": anyio.Event()}
        release = {"receipt-a": anyio.Event(), "receipt-b": anyio.Event()}

        async def gated(req):
            response = await original(req)
            invocation = (req.params.arguments or {}).get("invocation_id")
            if req.params.name == "rush_memory" and invocation in started:
                started[invocation].set()
                await release[invocation].wait()
            return response

        core.request_handlers[CallToolRequest] = gated

        incoming_send, incoming_read = anyio.create_memory_object_stream(0)
        outgoing_send, outgoing_read = anyio.create_memory_object_stream(0)
        seen_send, seen_read = anyio.create_memory_object_stream(16)
        state: compact.MCPReceiptState = ({}, Lock())
        token = compact.MCP_PENDING_FRAMES.set(state)
        writer = server_module._ReceiptStdout(
            server_module._Utf8Stdout(io.BytesIO()), state
        )

        async def serve() -> None:
            await core.run(
                cast(
                    MemoryObjectReceiveStream[SessionMessage | Exception],
                    server_module._ReceiptReadStream(incoming_read),
                ),
                outgoing_send,
                core.create_initialization_options(),
            )

        async def output() -> None:
            async with outgoing_read:
                async for message in outgoing_read:
                    line = (
                        message.message.model_dump_json(
                            by_alias=True, exclude_none=True
                        )
                        + "\n"
                    )
                    await writer.write(line)
                    await writer.flush()
                    await seen_send.send(
                        (
                            message.message.root,
                            line.replace("\n", os.linesep).encode("utf-8"),
                        )
                    )

        async def send(value: dict[str, Any]) -> None:
            await incoming_send.send(
                SessionMessage(JSONRPCMessage.model_validate(value))
            )

        async def receive(rid: int | str):
            while True:
                message, body = await seen_read.receive()
                if (
                    type(getattr(message, "id", None)) is type(rid)
                    and message.id == rid
                ):
                    return message, body

        async def memory(invocation: str) -> None:
            await send(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "rush_memory",
                        "arguments": {
                            "path": str(env.root),
                            "operation": "list",
                            "request": r_list(),
                            "allow_cache_write": True,
                            "invocation_id": invocation,
                        },
                    },
                }
            )

        try:
            with anyio.fail_after(30):
                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(serve)
                    tasks.start_soon(output)
                    await send(
                        {
                            "jsonrpc": "2.0",
                            "id": 0,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": LATEST_PROTOCOL_VERSION,
                                "capabilities": {},
                                "clientInfo": {
                                    "name": "phase75-id-collision",
                                    "version": "1",
                                },
                            },
                        }
                    )
                    await receive(0)
                    await send(
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    )
                    await memory("receipt-a")
                    await started["receipt-a"].wait()
                    duplicate = {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/list",
                        "params": {},
                    }
                    if duplicate_kind == "invalid_params":
                        duplicate = {
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {"arguments": {}},
                        }
                    await send(duplicate)
                    await receive(7)
                    slot = state[0][(int, 7)]
                    assert slot.invalid is True and slot.outstanding == 1
                    await memory("receipt-b")
                    await started["receipt-b"].wait()
                    assert state[0][(int, 7)] is slot and slot.outstanding == 2
                    release["receipt-a"].set()
                    await receive(7)
                    assert state[0][(int, 7)] is slot and slot.outstanding == 1
                    release["receipt-b"].set()
                    await receive(7)
                    assert (int, 7) not in state[0]
                    assert not (env.root / ".rush/telemetry/tokens.db").exists()
                    await memory("receipt-c")
                    result, body = await receive(7)
                    assert code(result.result["structuredContent"]) == "OK"
                    assert (int, 7) not in state[0]
                    tasks.cancel_scope.cancel()
            return body
        finally:
            writer.discard()
            compact.MCP_PENDING_FRAMES.reset(token)

    delivered = asyncio.run(trace())
    db = env.root / ".rush/telemetry/tokens.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT invocation_id,tokens,frame_bytes,frame_sha256 FROM memory_events WHERE kind='retrieval'"
        ).fetchall()
    assert rows == [
        (
            "receipt-c",
            _count_tokens(delivered.decode("utf-8"), "cl100k_base"),
            len(delivered),
            hashlib.sha256(delivered).hexdigest(),
        )
    ]


def test_phase75_frame_reader_preserves_bytes_and_basis(tmp_path: Path) -> None:
    import hashlib
    import sqlite3

    from rush.token_economy.telemetry import (
        memory_frame_usage,
        read_memory_frame_receipts_readonly,
    )

    env = make_env(tmp_path)
    result = MemoryTool().run(
        env.root, operation="list", request=r_list(), permissions=PERM_W
    )
    assert code(result) == "OK"
    db = env.root / ".rush/telemetry/tokens.db"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        schema = conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    rows = read_memory_frame_receipts_readonly(env.root)
    assert len(rows) == 1 and rows[0]["transport"] == "in_process"
    assert rows[0]["count_basis"] == "transport_frame:cl100k_base"
    summary = memory_frame_usage(rows)
    assert summary == {
        "available": True,
        "by_count_basis": {
            "transport_frame:cl100k_base": {
                "events": 1,
                "tokens": rows[0]["tokens"],
                "bytes": rows[0]["frame_bytes"],
            },
        },
        "unmeasured_events": 0,
        "invalid_events": 0,
    }
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        assert (
            conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
            == schema
        )


@pytest.mark.parametrize("create_store", [True, False])
def test_phase75_denied_telemetry_never_initializes_store(
    tmp_path: Path, create_store: bool
) -> None:
    env = make_env(tmp_path, create_store=create_store)
    result = MemoryTool().run(
        env.root, operation="list", request=r_list(), permissions=PERM_NONE
    )
    assert code(result) == "OK"
    assert not (env.root / ".rush/telemetry").exists()
    if not create_store:
        assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("operation", ["ask", "list"])
@pytest.mark.parametrize("create_store", [True, False])
@pytest.mark.parametrize("granted", [True, False])
def test_phase75_legacy_read_delivery(tmp_path, operation, create_store, granted):
    import hashlib
    import sqlite3

    from test_phase72_memory_public import ALICE

    from rush.delivery import compact
    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path, create_store=create_store, bob=False)
    options = (
        {"owner_filter": "user:alice"}
        if operation == "list"
        else {"owner_scope": ALICE}
    )
    result = MemoryTool().run(
        env.root,
        operation=operation,
        subject="domain_knowledge",
        query="needle" if operation == "ask" else "",
        session_allowlist=["s1"],
        permissions=PERM_W if granted else PERM_NONE,
        **options,
    )
    assert result["status"] == "ok", result
    db = env.root / ".rush/telemetry/tokens.db"
    if granted:
        delivered = compact.canonical_json(result)
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT tokens,frame_bytes,frame_sha256,count_basis FROM memory_events"
            ).fetchone()
        assert row == (
            _count_tokens(delivered.decode(), "cl100k_base"),
            len(delivered),
            hashlib.sha256(delivered).hexdigest(),
            "transport_frame:cl100k_base",
        )
    else:
        assert not db.exists()
    if not create_store:
        assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("encoding", ["cl100k_base", "o200k_base"])
def test_phase75_expansion_metadata_and_reader(tmp_path, encoding):
    import hashlib
    import sqlite3

    from test_phase72_memory_public import r_expand

    from rush.delivery import compact
    from rush.memory.retrieval import _count_tokens
    from rush.token_economy.telemetry import read_artifact_expansion_receipts_readonly

    env = make_env(tmp_path)
    result = MemoryTool().run(
        env.root,
        operation="expand",
        request=r_expand(encoding=encoding),
        permissions=PERM_W,
    )
    assert code(result) == "OK", result
    delivered = compact.canonical_json(result)
    db = env.root / ".rush/telemetry/tokens.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT tokens,frame_bytes,frame_sha256,transport,artifact_version,offset,payload_hash,count_basis FROM memory_events"
        ).fetchone()
    assert row[:6] == (
        _count_tokens(delivered.decode(), encoding),
        len(delivered),
        hashlib.sha256(delivered).hexdigest(),
        "in_process",
        1,
        0,
    )
    persisted_payload = env.store.get_version_payload("r1", 1)[0]
    assert row[6] == hashlib.sha256(persisted_payload.encode("utf-8")).hexdigest()
    assert row[7] == "transport_frame:" + encoding
    receipt = read_artifact_expansion_receipts_readonly(env.root, "r1", 1)[0]
    assert (
        receipt["artifact_version"] == 1
        and receipt["frame_receipt_state"] == "measured"
    )
    assert receipt["frame_receipt"] == dict(
        zip(
            (
                "frame_bytes",
                "frame_sha256",
                "transport",
                "artifact_version",
                "offset",
                "payload_hash",
                "count_basis",
            ),
            row[1:],
        )
    )


@pytest.mark.parametrize("ending", ["accepted", "denied", "revoked"])
def test_phase75_external_emitter_owns_finalization(tmp_path, ending):
    from rush.delivery import compact
    from rush.memory import authorization as auth

    env = make_env(tmp_path, create_store=False)
    frame = compact.FrameContext("in_process", None, pending_memory_events=[])
    result = MemoryTool().run(
        env.root, operation="list", request=r_list(), permissions=PERM_W, frame=frame
    )
    assert code(result) == "OK" and len(frame.pending_memory_events) == 1
    db = env.root / ".rush/telemetry/tokens.db"
    assert not db.exists()
    if ending == "revoked":
        auth.revoke_memory_scope(
            grant_id=env.grants["alice"]["grant_id"],
            expected_policy_revision=auth.load_policy_readonly(data_root=env.data_root)[
                "policy_revision"
            ],
            consent=True,
            data_root=env.data_root,
        )
    compact.finalize_memory_events(
        frame, compact.canonical_json(result), accepted=ending != "denied"
    )
    assert frame.pending_memory_events == []
    assert db.exists() is (ending == "accepted")
    compact.finalize_memory_events(frame, compact.canonical_json(result), accepted=True)
    assert not (env.root / ".rush/memory.db").exists()


@pytest.mark.parametrize("granted", [True, False])
def test_phase75_cli_receipt_is_stdout(tmp_path, granted):
    import hashlib
    import sqlite3

    from test_phase72_memory_public import _cli_result, r_expand, write_input

    from rush.memory.retrieval import _count_tokens

    env = make_env(tmp_path)
    path = write_input(env.root, "receipt-expand", r_expand())
    outcome = _cli_result(
        env.root,
        ["memory", "expand", "--input", str(path), "--json"]
        + (["--allow-cache-write"] if granted else []),
    )
    assert outcome.exit_code == 0, outcome.output
    assert code(json.loads(outcome.stdout_bytes)) == "OK"
    db = env.root / ".rush/telemetry/tokens.db"
    if granted:
        delivered = outcome.stdout_bytes
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT tokens,frame_bytes,frame_sha256,transport,count_basis FROM memory_events"
            ).fetchall()
        assert rows == [
            (
                _count_tokens(delivered.decode(), "cl100k_base"),
                len(delivered),
                hashlib.sha256(delivered).hexdigest(),
                "cli_json",
                "transport_frame:cl100k_base",
            )
        ]
    else:
        assert not db.exists()


def test_memory_event_frame_receipt_columns(tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from rush.token_economy.telemetry import (
        MEMORY_FRAME_RECEIPT_COLUMNS,
        TelemetryStore,
    )

    root = tmp_path / "migration"
    db = root / ".rush/telemetry/tokens.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE memory_events(request_id TEXT,event_id TEXT,kind TEXT,tokens INTEGER,timestamp INTEGER,PRIMARY KEY(request_id,event_id))"
        )
        conn.execute("INSERT INTO memory_events VALUES('old','page','retrieval',37,1)")
    barrier = Barrier(2)

    def initialize(_):
        barrier.wait()
        return TelemetryStore(root).db_path

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(initialize, [0, 1])) == [db, db]
    with sqlite3.connect(db) as conn:
        columns = {
            row[1]: row[2] for row in conn.execute("PRAGMA table_info(memory_events)")
        }
        assert {k: columns[k] for k in MEMORY_FRAME_RECEIPT_COLUMNS} == {
            "frame_bytes": "INTEGER",
            "frame_sha256": "TEXT",
            "transport": "TEXT",
            "artifact_version": "INTEGER",
            "offset": "INTEGER",
            "payload_hash": "TEXT",
            "count_basis": "TEXT",
        }
        assert conn.execute(
            "SELECT tokens,frame_bytes,frame_sha256,count_basis FROM memory_events"
        ).fetchall() == [(37, None, None, None)]


def test_phase75_old_reader_preserves_database(tmp_path):
    import hashlib
    import sqlite3

    from rush.token_economy.telemetry import (
        memory_frame_usage,
        read_artifact_expansion_receipts_readonly,
        read_memory_frame_receipts_readonly,
    )

    db = tmp_path / ".rush/telemetry/tokens.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE memory_events(invocation_id TEXT,event_id TEXT,kind TEXT,tokens INTEGER,timestamp INTEGER,request_id TEXT)"
        )
        conn.execute(
            "INSERT INTO memory_events VALUES('old','page','expansion',37,1,'r1:1:0')"
        )
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    rows = read_memory_frame_receipts_readonly(tmp_path)
    assert (
        len(rows) == 1
        and rows[0]["frame_bytes"] is None
        and rows[0]["count_basis"] is None
    )
    assert memory_frame_usage(rows) == {
        "available": False,
        "by_count_basis": {},
        "unmeasured_events": 1,
        "invalid_events": 0,
    }
    receipt = read_artifact_expansion_receipts_readonly(tmp_path, "r1", 1)[0]
    assert receipt["frame_receipt_state"] == "unavailable"
    assert all(value is None for value in receipt["frame_receipt"].values())
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert (
        not db.with_name(db.name + "-wal").exists()
        and not db.with_name(db.name + "-shm").exists()
    )


@pytest.mark.parametrize("failure", ["write", "flush", "cancel", "error_response"])
def test_phase75_stdio_failed_emit_consumes_actual_candidate(
    tmp_path, monkeypatch, failure
):
    import io
    from threading import Lock

    from mcp.types import CallToolResult, ErrorData, JSONRPCError

    from rush import mcp as server
    from rush.delivery import compact
    from rush.mcp_support.tool_registry import _memory_frame

    env = make_env(tmp_path)
    state = ({}, Lock())
    token = compact.MCP_PENDING_FRAMES.set(state)
    monkeypatch.setattr(compact, "current_request_id", lambda: 7)

    class Sink(io.BytesIO):
        def write(self, body):
            if failure == "write":
                super().write(body[:-1])
                return len(body) - 1
            return super().write(body)

        def flush(self):
            if failure == "flush":
                raise OSError("fixture flush refused")
            if failure == "cancel":
                raise asyncio.CancelledError()
            return super().flush()

    sink = Sink()
    writer = server._ReceiptStdout(server._Utf8Stdout(sink), state)
    try:
        compact.reserve_mcp_request(7)
        frame = _memory_frame(
            lambda: (
                lambda value: CallToolResult(content=[], structuredContent=dict(value))
            ),
            dict,
        )
        result = MemoryTool().run(
            env.root,
            operation="list",
            request=r_list(),
            permissions=PERM_W,
            frame=frame,
        )
        assert code(result) == "OK" and len(frame.pending_memory_events) == 1
        line = frame.emit(result).decode("utf-8")
        if failure == "error_response":
            line = (
                JSONRPCError(
                    jsonrpc="2.0",
                    id=7,
                    error=ErrorData(code=0, message="Request cancelled"),
                ).model_dump_json(by_alias=True, exclude_none=True)
                + "\n"
            )

        async def emit():
            await writer.write(line)
            await writer.flush()

        if failure == "error_response":
            asyncio.run(emit())
        else:
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else OSError
            ):
                asyncio.run(emit())
        assert state[0] == {} and frame.pending_memory_events == []
        assert not (env.root / ".rush/telemetry/tokens.db").exists()
        writer.discard()
        assert not sink.closed
    finally:
        compact.MCP_PENDING_FRAMES.reset(token)


def test_phase75_invocation_dedup_and_basis_stats(tmp_path):
    import hashlib

    from test_phase72_memory_public import ALICE

    from rush.delivery import compact
    from rush.memory.retrieval import MemoryAccess
    from rush.token_economy.telemetry import (
        memory_frame_usage,
        read_memory_frame_receipts_readonly,
    )
    from rush.workflows.projects import root_token_usage

    env = make_env(tmp_path)
    first = MemoryTool().run(
        env.root,
        operation="list",
        request=r_list(),
        permissions=PERM_W,
        invocation_id="receipt-repeat",
    )
    assert code(first) == "OK"
    replay = MemoryTool().run(
        env.root,
        operation="list",
        request=r_list(),
        permissions=PERM_W,
        invocation_id="receipt-repeat",
    )
    assert code(replay) == "OK"
    second = MemoryTool().run(
        env.root,
        operation="list",
        request=r_list(encoding="o200k_base"),
        permissions=PERM_W,
        invocation_id="receipt-other",
    )
    assert code(second) == "OK"
    access, reason = MemoryAccess.resolve_with_reason(
        env.root, operation="list", owner_scope=ALICE
    )
    assert reason == "granted" and access is not None
    rows = read_memory_frame_receipts_readonly(env.root, access=access)
    assert len(rows) == 2
    by_id = {row["invocation_id"]: row for row in rows}
    assert (
        by_id["receipt-repeat"]["frame_sha256"]
        == hashlib.sha256(compact.canonical_json(first)).hexdigest()
    )
    assert (
        by_id["receipt-other"]["frame_sha256"]
        == hashlib.sha256(compact.canonical_json(second)).hexdigest()
    )
    groups = memory_frame_usage(rows)["by_count_basis"]
    assert set(groups) == {"transport_frame:cl100k_base", "transport_frame:o200k_base"}
    assert all(group["events"] == 1 for group in groups.values())
    usage = root_token_usage(env.root, access=access)
    assert usage["memory_frame_usage"]["by_count_basis"] == groups
    assert usage["cache_hits"]["count_basis"] is None


def test_phase75_dashboard_revocation_after_tool_emits_no_receipt(
    tmp_path, monkeypatch
):
    import uuid
    from threading import Event

    from test_phase72_memory_ui import SUBJECT, _dashboard, _http, _world

    from rush.delivery import compact
    from rush.memory import authorization as auth

    world = _world(tmp_path)
    original_run = MemoryTool.run
    original_finalize = compact.finalize_memory_events
    finished = Event()
    observed = []
    revoked = []
    calls = []

    def run(self, *args, **kwargs):
        result = original_run(self, *args, **kwargs)
        receipt = compact.RECEIPT_FRAME.get()
        calls.append(
            (
                kwargs.get("operation"),
                code(result),
                None if receipt is None else len(receipt.pending_memory_events or ()),
            )
        )
        if not revoked and receipt is not None and receipt.pending_memory_events:
            assert code(result) == "OK"
            revoked.append(True)
            auth.revoke_memory_scope(
                grant_id=world.grant["grant_id"],
                expected_policy_revision=auth.load_policy_readonly(
                    data_root=world.data_root
                )["policy_revision"],
                consent=True,
                data_root=world.data_root,
            )
        return result

    def finalize(frame, body, *, accepted, outcome=None):
        assert outcome is None
        observed.append((len(frame.pending_memory_events), accepted))
        try:
            return original_finalize(frame, body, accepted=accepted, outcome=outcome)
        finally:
            finished.set()

    monkeypatch.setattr(MemoryTool, "run", run)
    monkeypatch.setattr(compact, "finalize_memory_events", finalize)
    dash = _dashboard(world)
    try:
        payload = json.dumps(
            {
                "schema_version": 1,
                "operation": "memory_query",
                "arguments": {
                    "schema_version": 2,
                    "subjects": [SUBJECT],
                    "query": "needle",
                    "mode": "list",
                },
                "grants": {"cache_write": True},
                "expected": {},
                "request_id": str(uuid.uuid4()),
            }
        ).encode("utf-8")
        response = _http(
            "POST",
            f"{dash.base}/api/projects/{dash.project_id}/actions",
            {
                "Cookie": dash.cookie,
                "X-Rush-CSRF": dash.csrf,
                "Origin": dash.base,
                "Content-Type": "application/json",
            },
            payload,
        )
        delivered = json.loads(response.read())
        # Shared adapter maps a completed domain refusal to HTTP 200.
        assert response.status == 200, (calls, revoked, observed)
        assert code(delivered["data"]) == "E_PERMISSION"
        assert delivered["data"]["raw"]["items"] == []
        assert finished.wait(3)
        assert observed == [(1, False)]
        assert not (world.root / ".rush/telemetry/tokens.db").exists()
    finally:
        dash.stop()
