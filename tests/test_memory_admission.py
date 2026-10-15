"""C05 portable producers reject impossible budgets before reads/effects."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from test_memory_activation_lifecycle import bootstrap_world
from test_memory_capsule import _mcp_call, call, cli_args, cli_invoke, tree_state

from rush.delivery.compact import canonical_json
from rush.memory.retrieval import DEFAULT_ENCODING, _count_tokens
from rush.tools.memory import MemoryTool


def bootstrap_wire(env, request, transport):
    if transport == "cli":
        from rush.cli import cli

        argv = ["memory", "bootstrap", "--project", str(env.root), "--json"]
        for key in ("task_id", "task_kind", "query", "max_tokens", "session_binding"):
            argv += ["--" + key.replace("_", "-"), str(request[key])]
        result = CliRunner().invoke(cli, argv)
        return json.loads(result.stdout), result.stdout.encode()
    if transport == "mcp":
        result = _mcp_call(
            {"path": str(env.root), "operation": "bootstrap", "request": request}
        )
    else:
        result = MemoryTool().run(env.root, operation="bootstrap", request=request)
    return result, canonical_json(result)


def capsule_wire(env, request, transport):
    if transport == "cli":
        result = cli_invoke(cli_args(env.root, request, cache=False))
        return json.loads(result.stdout), result.stdout.encode()
    result = call(transport, env.root, request, cache=False).result
    return result, canonical_json(result)


def test_bootstrap_admission_precedes_scope_resolution(tmp_path: Path, monkeypatch):
    from rush.tools import memory

    env, request = bootstrap_world(tmp_path, create_store=False)
    before = tree_state(env.root, env.data_root)
    monkeypatch.setattr(
        memory,
        "_bootstrap_access",
        lambda *a, **k: pytest.fail("admission must precede scope read"),
    )
    result = MemoryTool().run(
        env.root, operation="bootstrap", request={**request, "max_tokens": 1}
    )
    assert result["raw"]["code"] == "E_INPUT"
    data = result["raw"]["data"]
    assert data["admission_failure"] is True and data["items"] == []
    assert data["required"]["max_tokens"] > 1
    assert tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize("transport", ["inproc", "cli", "mcp"])
def test_bootstrap_minimum_minus_one_and_admitted_packet(tmp_path: Path, transport):
    env, request = bootstrap_world(tmp_path, create_store=False)
    request["query"] = "mandatory current task objective " * 300
    before = tree_state(env.root, env.data_root)
    rejected, _ = bootstrap_wire(env, {**request, "max_tokens": 1}, transport)
    assert rejected["raw"]["code"] == "E_INPUT"
    minimum = rejected["raw"]["data"]["required"]["max_tokens"]
    below, _ = bootstrap_wire(env, {**request, "max_tokens": minimum - 1}, transport)
    assert (
        below["raw"]["code"] == "E_INPUT"
        and below["raw"]["data"]["admission_failure"] is True
    )
    assert below["raw"]["data"]["required"]["max_tokens"] == minimum
    admitted, emitted = bootstrap_wire(
        env, {**request, "max_tokens": minimum}, transport
    )
    data = admitted["raw"]["data"]
    assert admitted["raw"]["code"] == "E_BUDGET" and data["admission_failure"] is False
    assert data["required"]["max_tokens"] > minimum
    assert "task" not in data and "intent" not in data and data["items"] == []
    assert _count_tokens(emitted.decode(), DEFAULT_ENCODING) <= minimum
    assert len(emitted) <= 65536
    success, emitted = bootstrap_wire(env, request, transport)
    assert (
        success["raw"]["code"] == "OK"
        and success["raw"]["data"]["intent"]["query"] == request["query"]
    )
    assert _count_tokens(emitted.decode(), DEFAULT_ENCODING) <= request["max_tokens"]
    assert tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize("transport", ["inproc", "cli", "mcp"])
@pytest.mark.parametrize(
    "axis,required_key", [("max_bytes", "bytes"), ("max_tokens", "tokens")]
)
@pytest.mark.parametrize("elapsed_ms", [0, 11], ids=["zero-ms", "two-digit-ms"])
def test_capsule_minimum_and_complete_required_recovery(
    tmp_path: Path, monkeypatch, transport, axis, required_key, elapsed_ms
):
    # Compare identical frames: elapsed-time digit width otherwise changes the floor.
    monkeypatch.setattr(
        "rush.tools.memory._frozen_duration", lambda started: elapsed_ms
    )
    env, _ = bootstrap_world(tmp_path)
    request = {
        "action": "preview_export",
        "output": str(env.root / "bounded.json"),
        "max_tokens": 16384,
        "max_bytes": 65536,
    }
    before = tree_state(env.root, env.data_root)
    rejection, _ = capsule_wire(env, {**request, axis: 1}, transport)
    assert rejection["raw"]["code"] == "E_INPUT"
    assert rejection["duration_ms"] == elapsed_ms
    minimum = rejection["raw"]["data"]["required"][required_key]
    below, _ = capsule_wire(env, {**request, axis: minimum - 1}, transport)
    assert (
        below["raw"]["code"] == "E_INPUT"
        and below["raw"]["data"]["admission_failure"] is True
    )
    assert below["raw"]["data"]["required"][required_key] == minimum
    admitted, emitted = capsule_wire(env, {**request, axis: minimum}, transport)
    data = admitted["raw"]["data"]
    assert admitted["raw"]["code"] == "E_BUDGET" and data["admission_failure"] is False
    assert data["required"][required_key] > minimum
    assert "records" not in data and "selected" not in data
    assert len(emitted) <= (minimum if axis == "max_bytes" else request["max_bytes"])
    assert _count_tokens(emitted.decode(), DEFAULT_ENCODING) <= (
        minimum if axis == "max_tokens" else request["max_tokens"]
    )
    success, emitted = capsule_wire(env, request, transport)
    assert success["raw"]["code"] == "OK" and success["raw"]["data"]["selected"]
    assert len(emitted) <= request["max_bytes"]
    assert _count_tokens(emitted.decode(), DEFAULT_ENCODING) <= request["max_tokens"]
    assert tree_state(env.root, env.data_root) == before


def test_offline_admission_precedes_scope_and_snapshot(tmp_path: Path, monkeypatch):
    from rush.integrations.agent_hooks import deliver_continuation
    from rush.tools import memory

    env, request = bootstrap_world(tmp_path, create_store=False)
    packet = MemoryTool().run(env.root, operation="bootstrap", request=request)
    scope = packet["raw"]["data"]["scope"]
    before = tree_state(env.root, env.data_root)
    monkeypatch.setattr(
        memory,
        "_bootstrap_access",
        lambda *a, **k: pytest.fail("admission must precede scope"),
    )
    result = deliver_continuation(
        env.root,
        {**request, "max_tokens": 1},
        "unavailable",
        env.root / "missing-rush",
        scope,
    )
    assert result["mode"] == "unavailable" and result["data"] == {}
    action = result["recovery"]["action"]
    assert action["code"] == "E_INPUT" and action["admission_failure"] is True
    assert action["required"]["tokens"] > 1
    assert tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize("transport", ["inproc", "cli", "mcp"])
def test_capsule_admission_precedes_input_extraction(
    tmp_path: Path, monkeypatch, transport
):
    from rush.memory import capsule

    env, _ = bootstrap_world(tmp_path, create_store=False)
    before = tree_state(env.root, env.data_root)
    monkeypatch.setattr(
        capsule,
        "_read_input",
        lambda *a, **k: pytest.fail("admission must precede capsule read"),
    )
    result = call(
        transport,
        env.root,
        {
            "action": "bridge",
            "input": str(env.root / "unread.json"),
            "instructions": str(env.root / "AGENTS.md"),
            "max_tokens": 1,
        },
    )
    assert result.code == "E_INPUT"
    assert result.data["admission_failure"] is True
    assert result.data["required"]["tokens"] > 1
    assert tree_state(env.root, env.data_root) == before
