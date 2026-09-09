"""Contract tests T-61.28 through T-61.31 for the Cross-Tool Transport Dispatcher
(Phase 61 §9 P61.10). Wholly new code — never exercises
`rush.continuity.providers.provider_command()`/`resume_provider()`, which is session-resume
CLI dispatch, a separate concern (§2.1 Drift 6)."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from rush.memory import transport
from rush.permissions import ExecutionPermissions


def test_native_sdk_tier_selected_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.28: native SDK importable for a tool -> dispatcher picks tier 1, not ACP or the
    dedicated-file fallback."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: True)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: True)

    assert transport.select_tier("claude_code") == "native_sdk"


def test_acp_tier_selected_when_no_native_sdk_but_acp_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.29: no native SDK but ACP support available -> tier 2 selected."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: False)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: True)

    assert transport.select_tier("codex_cli", acp_command=("adapter",)) == "acp"


def test_dedicated_file_fallback_when_neither_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.30: neither native SDK nor ACP available -> tier 3 dedicated-file fallback to
    `.rush/memory/cross_tool_handoff.md`, gated behind `ExecutionPermissions(artifact_write=True)`
    — never `AGENTS.md`/`CLAUDE.md`. Also covers dedupe on `(source, content_hash)` and the
    explicit (non-automatic) cleanup function."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: False)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: False)

    denied = transport.dispatch(
        tmp_path, "antigravity_cli", "claude_code", "fact: x uses WAL"
    )
    assert denied.tier == "dedicated_file"
    assert denied.status == "skipped"
    assert not (tmp_path / transport.HANDOFF_FILE).exists()

    granted_result = transport.dispatch(
        tmp_path,
        "antigravity_cli",
        "claude_code",
        "fact: x uses WAL",
        granted=ExecutionPermissions(artifact_write=True),
    )
    assert granted_result.tier == "dedicated_file"
    assert granted_result.status == "ok"

    handoff_path = tmp_path / transport.HANDOFF_FILE
    assert handoff_path.exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()

    before = handoff_path.read_text(encoding="utf-8")
    duplicate_result = transport.dispatch(
        tmp_path,
        "antigravity_cli",
        "claude_code",
        "fact: x uses WAL",
        granted=ExecutionPermissions(artifact_write=True),
    )
    assert duplicate_result.status == "ok"
    assert "Duplicate" in duplicate_result.detail
    assert handoff_path.read_text(encoding="utf-8") == before

    removed = transport.cleanup_handoff_file(tmp_path, max_blocks=0)
    assert removed == 1
    assert "content_hash=" not in handoff_path.read_text(encoding="utf-8")


def test_dispatcher_is_per_tool_not_global(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.31: two tools with different tier availability in the same run each get their own
    tier independently, not one global tier for the whole session."""
    native_sdk_tools = {"claude_code"}
    acp_tools = {"codex_cli"}
    monkeypatch.setattr(
        transport, "_native_sdk_available", lambda tool: tool in native_sdk_tools
    )
    monkeypatch.setattr(transport, "_acp_available", lambda tool: tool in acp_tools)

    result_a = transport.dispatch(
        tmp_path, "claude_code", "antigravity_cli", "content a"
    )
    result_b = transport.dispatch(
        tmp_path, "codex_cli", "antigravity_cli", "content b", acp_command=("adapter",)
    )
    result_c = transport.dispatch(
        tmp_path, "antigravity_cli", "claude_code", "content c"
    )

    assert result_a.tier == "native_sdk"
    assert result_b.tier == "acp"
    assert result_c.tier == "dedicated_file"


def test_remote_permission_required(monkeypatch, tmp_path):
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: True)
    result = transport.dispatch(tmp_path, "claude_code", "codex_cli", "private")
    assert result.status == "skipped"
    assert "--allow-network" in result.detail
    assert not (tmp_path / transport.HANDOFF_FILE).exists()


def test_acp_package_without_adapter_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: False)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: True)
    result = transport.dispatch(
        tmp_path,
        "codex_cli",
        "claude_code",
        "payload",
        ExecutionPermissions(artifact_write=True),
    )
    assert result.tier == "dedicated_file"
    assert "payload" in (tmp_path / transport.HANDOFF_FILE).read_text()


@pytest.mark.parametrize("stage", ["version", "initialization"])
def test_native_startup_timeout_reaps_child(monkeypatch, tmp_path, stage):
    sdk = pytest.importorskip("claude_agent_sdk")
    pidfile = tmp_path / "startup.pid"
    peer = tmp_path / "startup-peer"
    peer.write_text(
        f"#!{sys.executable}\n"
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        f"if {stage!r} == 'initialization' and '-v' in sys.argv:\n"
        "    print('2.2.0')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    peer.chmod(0o700)
    options_type = sdk.ClaudeAgentOptions
    monkeypatch.setattr(
        sdk,
        "ClaudeAgentOptions",
        lambda **kwargs: options_type(**kwargs, cli_path=str(peer)),
    )
    start = time.monotonic()
    result = transport.dispatch(
        tmp_path,
        "claude_code",
        "source",
        "payload",
        ExecutionPermissions(network=True),
        # Cold spawned interpreter + optional SDK imports belong inside this deadline.
        timeout_seconds=10,
    )
    assert result.status == "error"
    assert time.monotonic() - start < 14
    assert pidfile.is_file(), f"Peer never reached {stage} before dispatch deadline"
    pid = int(pidfile.read_text())
    try:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _peer(tmp_path, protocol, outcome):
    """Local stdio peer: receives SDK wire payload, records it, sends protocol reply."""
    path = tmp_path / "peer"
    path.write_text(
        f"#!{sys.executable}\n"
        + f"protocol={protocol!r}\noutcome={outcome!r}\n"
        + r"""
import json, os, signal, sys, time
from pathlib import Path
if "-v" in sys.argv:
    print("2.2.0")
    sys.exit(0)
Path("peer.pid").write_text(str(os.getpid()))
def send(message):
    print(json.dumps(message), flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    with open("received.jsonl", "a") as f:
        f.write(json.dumps(msg) + "\n")
    if protocol == "acp":
        method = msg.get("method")
        if method == "initialize":
            response = {"protocolVersion": 1, "agentCapabilities": {}}
        elif method == "session/new":
            response = {"sessionId": "local-session"}
        elif method == "session/prompt":
            if outcome == "timeout":
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                time.sleep(60)
            if outcome == "missing":
                break
            if outcome == "error":
                send({"jsonrpc":"2.0", "id":msg["id"], "error":{"code":-32603,"message":"secret-value"}})
                continue
            if outcome == "permission":
                send({"jsonrpc":"2.0", "id":"permission", "method":"session/request_permission", "params":{"sessionId":"local-session","toolCall":{"toolCallId":"tool","title":"Shell","kind":"execute","status":"pending"},"options":[{"optionId":"yes","name":"Allow","kind":"allow_once"}]}})
                permission = json.loads(sys.stdin.readline())
                Path("permission.json").write_text(json.dumps(permission))
            if outcome == "filesystem":
                send({"jsonrpc":"2.0", "id":"filesystem", "method":"fs/read_text_file", "params":{"sessionId":"local-session","path":"outside-secret.txt"}})
                Path("filesystem.json").write_text(sys.stdin.readline())
            if outcome == "terminal":
                send({"jsonrpc":"2.0", "id":"terminal", "method":"terminal/create", "params":{"sessionId":"local-session","command":"cat","args":["outside-secret.txt"]}})
                Path("terminal.json").write_text(sys.stdin.readline())
            response = {"stopReason": "cancelled" if outcome == "cancelled" else "end_turn"}
        else:
            continue
        send({"jsonrpc":"2.0","id":msg["id"],"result":response})
    else:
        if msg.get("type") == "control_request":
            send({"type":"control_response","response":{"subtype":"success","request_id":msg["request_id"],"response":{}}})
        elif msg.get("type") == "user":
            if outcome == "timeout":
                time.sleep(60)
            if outcome == "missing":
                break
            if outcome == "permission":
                send({"type":"control_request","request_id":"permission","request":{"subtype":"can_use_tool","tool_name":"Bash","input":{"command":"touch bad"},"tool_use_id":"tool"}})
                permission = json.loads(sys.stdin.readline())
                Path("permission.json").write_text(json.dumps(permission))
            send({"type":"result","subtype":"error_during_execution" if outcome == "error" else "success","duration_ms":1,"duration_api_ms":1,"is_error":outcome == "error","num_turns":1,"session_id":"local-session","result":"secret-value"})
"""
    )
    path.chmod(0o700)
    return path


@pytest.mark.parametrize(
    "protocol,outcome",
    [
        (protocol, outcome)
        for protocol in ("native_sdk", "acp")
        for outcome in (
            "success",
            "error",
            "missing",
            "timeout",
            "permission",
            "cancelled",
            "filesystem",
            "terminal",
        )
        if protocol == "acp" or outcome not in {"cancelled", "filesystem", "terminal"}
    ],
)
def test_real_sdk_local_peer(monkeypatch, tmp_path, protocol, outcome):
    sdk = pytest.importorskip("claude_agent_sdk" if protocol == "native_sdk" else "acp")
    peer = _peer(tmp_path, "claude" if protocol == "native_sdk" else "acp", outcome)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("synthetic-secret")
    if protocol == "native_sdk":
        options_type = sdk.ClaudeAgentOptions

        def options(**kwargs):
            assert kwargs["tools"] == []
            assert kwargs["setting_sources"] == []
            return options_type(**kwargs, cli_path=str(peer))

        monkeypatch.setattr(sdk, "ClaudeAgentOptions", options)
    monkeypatch.setattr(
        transport, "_native_sdk_available", lambda tool: protocol == "native_sdk"
    )
    result = transport.dispatch(
        tmp_path,
        "claude_code" if protocol == "native_sdk" else "codex_cli",
        "source-tool",
        "exact handoff\nUnicode: café",
        ExecutionPermissions(network=True),
        acp_command=(str(peer),),
        timeout_seconds=2 if outcome == "timeout" else 5,
    )
    assert result.tier == protocol
    assert result.status == ("ok" if outcome == "success" else "error"), result.detail
    assert "secret-value" not in result.detail
    received = [
        json.loads(line)
        for line in (tmp_path / "received.jsonl").read_text().splitlines()
    ]
    message = next(
        m
        for m in received
        if m.get("method") == "session/prompt" or m.get("type") == "user"
    )
    payload = (
        message["params"]["prompt"][0]["text"]
        if protocol == "acp"
        else message["message"]["content"]
    )
    assert json.loads(payload) == {
        "source": "source-tool",
        "content": "exact handoff\nUnicode: café",
    }
    if protocol == "acp":
        new = next(m for m in received if m.get("method") == "session/new")
        assert new["params"]["cwd"] == str(tmp_path)
        assert new["params"]["mcpServers"] == []
    if outcome == "permission":
        permission = json.loads((tmp_path / "permission.json").read_text())
        if protocol == "acp":
            assert permission["result"]["outcome"]["outcome"] == "cancelled"
        else:
            assert permission["response"]["response"]["behavior"] == "deny"
    if outcome in {"filesystem", "terminal"}:
        denial = json.loads((tmp_path / f"{outcome}.json").read_text())
        assert denial["id"] == outcome
        assert "error" in denial
        assert outside.read_text() == "synthetic-secret"
    pid = int((tmp_path / "peer.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not (tmp_path / transport.HANDOFF_FILE).exists()
