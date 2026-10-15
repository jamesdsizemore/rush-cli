"""Phase 73 T07 native packages and protocol adapters.

Primary contracts: https://prod.cursor.com/docs/hooks and /docs/reference/plugins;
https://antigravity.google/docs/hooks?tab=ide and /docs/plugins?tab=cli;
https://zcode.z.ai/en/docs/hooks and /en/docs/mcp-services.
Source fixtures and plugin validation do not certify installed model insertion.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from rush.integrations.agents import materialize_agent_plugins


@pytest.mark.parametrize(
    ("host", "manifest", "mcp_file"),
    [
        ("cursor", ".cursor-plugin/plugin.json", "mcp.json"),
        ("antigravity", "plugin.json", "mcp_config.json"),
        ("zcode", ".zcode-plugin/plugin.json", "mcp.json"),
    ],
)
def test_requested_host_package_materializes_canonical_argv(
    tmp_path: Path, host: str, manifest: str, mcp_file: str
) -> None:
    binary = str(tmp_path / "Rush path with spaces" / "rush")
    roots = materialize_agent_plugins(
        rush_binary=binary, rush_version="0.1.0-t07", data_root=tmp_path / "data"
    )
    assert set(roots) == {"claude", "codex", "cursor", "antigravity", "zcode"}
    plugin = roots[host] / "rush"
    assert json.loads((plugin / manifest).read_text())["name"] == "rush"
    assert json.loads((plugin / mcp_file).read_text())["mcpServers"]["rush"] == {
        "command": binary,
        "args": ["mcp", "serve", "--profile", "core"],
    }
    skill = (plugin / "skills/rush/SKILL.md").read_bytes()
    canonical = (
        files("rush.integrations")
        .joinpath("agent_assets/skills/rush/SKILL.md")
        .read_bytes()
    )
    assert skill == canonical
    if host == "zcode":
        assert (plugin / "AGENTS.md").is_file()


def test_agy_native_hooks_have_only_documented_events() -> None:
    assets = files("rush.integrations").joinpath("agent_assets/antigravity")
    hooks = json.loads(assets.joinpath("hooks.json").read_text())["rush-continuation"]
    assert set(hooks) == {"PreInvocation", "PostToolUse", "Stop"}
    for event, entries in hooks.items():
        entry = entries[0]
        command = entry["hooks"][0] if "hooks" in entry else entry
        assert command == {
            "type": "command",
            "command": f"@RUSH_BINARY_SH@ agent hook antigravity --event {event}",
            "timeout": 10 if event == "Stop" else 5,
        }


def test_zcode_plugin_hooks_use_process_argv_not_project_settings() -> None:
    assets = files("rush.integrations").joinpath("agent_assets/zcode")
    manifest = json.loads(assets.joinpath(".zcode-plugin/plugin.json").read_text())
    assert "hooks" not in manifest
    hooks = json.loads(assets.joinpath("hooks/hooks.json").read_text())["hooks"]
    assert set(hooks) == {
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
    }
    assert hooks["SessionStart"][0]["matcher"] == "startup|clear|compact"
    for event, entries in hooks.items():
        assert entries[0]["hooks"] == [
            {
                "type": "process",
                "command": "@RUSH_BINARY@",
                "args": ["agent", "hook", "zcode", "--event", event],
                "timeoutMs": 10000 if event == "Stop" else 5000,
            }
        ]
    assert not assets.joinpath(".zcode/config.json").is_file()


def test_cursor_hooks_preserve_native_feedback_limits() -> None:
    assets = files("rush.integrations").joinpath("agent_assets/cursor")
    hooks = json.loads(assets.joinpath("hooks/hooks.json").read_text())
    assert hooks["version"] == 1
    assert set(hooks["hooks"]) == {
        "sessionStart",
        "postToolUse",
        "postToolUseFailure",
        "preCompact",
        "stop",
    }
    for event, entries in hooks["hooks"].items():
        assert entries[0]["command"] == (
            f"@RUSH_BINARY_SH@ agent hook cursor --event {event}"
        )


def test_agy_native_validator_accepts_rendered_owned_package(tmp_path: Path) -> None:
    agy = shutil.which("agy")
    rush = shutil.which("rush")
    if agy is None or rush is None:
        pytest.skip("installed agy and Rush required for native package validation")
    roots = materialize_agent_plugins(
        rush_binary=rush, rush_version="0.1.0-t07", data_root=tmp_path / "data"
    )
    result = subprocess.run(
        [agy, "plugin", "validate", str(roots["antigravity"] / "rush")],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "host,event",
    [
        ("antigravity", "PreInvocation"),
        ("zcode", "SessionStart"),
        ("cursor", "sessionStart"),
    ],
)
def test_native_start_without_active_task_is_visible_and_readonly(
    tmp_path: Path, host: str, event: str
) -> None:
    from rush.integrations.agent_hooks import run_native_agent_hook

    payload = (
        {
            "conversationId": "native-session",
            "workspacePaths": [str(tmp_path)],
            "invocationNum": 0,
        }
        if host == "antigravity"
        else {
            "conversation_id": "native-session",
            "workspace_roots": [str(tmp_path)],
            "hook_event_name": event,
        }
        if host == "cursor"
        else {
            "session_id": "native-session",
            "cwd": str(tmp_path),
            "hook_event_name": event,
            "source": "startup",
        }
    )
    before = sorted(tmp_path.rglob("*"))
    raw = run_native_agent_hook(
        host, json.dumps(payload).encode(), event=event, data_root=tmp_path / "data"
    )
    packet = json.loads(raw)
    text = (
        packet["injectSteps"][0]["ephemeralMessage"]
        if host == "antigravity"
        else packet["additional_context"]
        if host == "cursor"
        else packet["hookSpecificOutput"]["additionalContext"]
    )
    assert "activation_required" in text and "bootstrap" in text
    assert sorted(tmp_path.rglob("*")) == before


def test_native_agy_bootstrap_capture_then_real_context_and_revocation(
    tmp_path: Path,
) -> None:
    from test_memory_capsule import ALL_OPS, make_env

    from rush.integrations import agent_hooks, agents
    from rush.memory import authorization as auth

    env = make_env(tmp_path, ops=(*ALL_OPS, "bootstrap"))
    session = "native-agy-session"
    binding = auth.register_memory_binding(
        grant_id=env.grant["grant_id"],
        session_id=session,
        host_id="antigravity",
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    request = {
        "task_id": "task-1",
        "task_kind": "memory_continuation",
        "query": "needle",
        "max_tokens": 16384,
        "session_binding": binding["binding_id"],
    }
    agents.initialize_agent_memory(
        "antigravity",
        session,
        project_root=env.root,
        data_root=env.data_root,
        consent=True,
    )
    agents.acknowledge_agent_connection(
        "antigravity", session, project_root=env.root, data_root=env.data_root
    )
    agent_hooks.set_hook_activation(
        "antigravity",
        env.root,
        enable=True,
        recovery_cache_write=True,
        data_root=env.data_root,
    )
    event = {
        "conversationId": session,
        "workspacePaths": [str(env.root)],
        "toolCall": {
            "name": "rush_memory",
            "args": {"operation": "bootstrap", "request": request},
        },
        "stepIdx": 2,
    }
    assert (
        json.loads(
            agent_hooks.run_native_agent_hook(
                "antigravity",
                json.dumps(event).encode(),
                event="PostToolUse",
                data_root=env.data_root,
            )
        )
        == {}
    )
    observed = agents.read_agent_memory_state_strict(
        project_root=env.root, data_root=env.data_root
    )[f"{session}::antigravity"]["last_observation"]
    assert observed["bootstrap_request"] == request
    start = {
        "conversationId": session,
        "workspacePaths": [str(env.root)],
        "invocationNum": 3,
    }
    raw = agent_hooks.run_native_agent_hook(
        "antigravity",
        json.dumps(start).encode(),
        event="PreInvocation",
        data_root=env.data_root,
    )
    result = json.loads(json.loads(raw)["injectSteps"][0]["ephemeralMessage"])
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["task"]["remaining"] == ["wire the CLI flag"]
    assert result["raw"]["data"]["intent"]["task_id"] == "task-1"
    auth.revoke_memory_scope(
        grant_id=env.grant["grant_id"],
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    denied = agent_hooks.run_native_agent_hook(
        "antigravity",
        json.dumps(start).encode(),
        event="PreInvocation",
        data_root=env.data_root,
    )
    assert b"wire the CLI flag" not in denied and b"needle" not in denied
    assert b"revoked" in denied


def test_native_failed_stdout_is_not_retried(tmp_path: Path) -> None:
    from rush.integrations.agent_hooks import run_native_agent_hook

    writes = []

    def failed(data: bytes) -> None:
        writes.append(data)
        raise OSError("closed native stdout")

    output = run_native_agent_hook(
        "antigravity",
        b'{"conversationId":"s","workspacePaths":["/tmp"],"invocationNum":0}',
        event="PreInvocation",
        data_root=tmp_path / "data",
        emit=failed,
    )
    assert output == b"" and len(writes) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"[]",
        b"{}",
        b'{"conversationId":"a","conversationId":"b"}',
        b"x" * 65537,
        b'{"conversationId":"s","workspacePaths":["relative"],"invocationNum":0}',
        b'{"conversationId":"s","workspacePaths":["/tmp"],"invocationNum":true}',
    ],
)
def test_native_bad_input_never_reads_or_creates_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    from rush.integrations import agent_hooks

    def forbidden(*args, **kwargs):
        pytest.fail("invalid native payload reached project registry")

    monkeypatch.setattr(agent_hooks, "_registered_roots", forbidden)
    result = agent_hooks.run_native_agent_hook(
        "antigravity", payload, event="PreInvocation", data_root=tmp_path / "data"
    )
    assert b"invalid_event" in result and list(tmp_path.iterdir()) == []


def test_native_cli_event_emits_one_utf8_json_line(tmp_path: Path) -> None:
    from click.testing import CliRunner
    from test_memory_capsule import make_env

    from rush.cli import cli

    env = make_env(tmp_path, create_store=False)
    payload = {
        "conversationId": "session",
        "workspacePaths": [str(env.root)],
        "invocationNum": 0,
    }
    result = CliRunner().invoke(
        cli,
        ["agent", "hook", "antigravity", "--event", "PreInvocation"],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.exception
    parsed = json.loads(result.stdout_bytes)
    assert "activation_required" in parsed["injectSteps"][0]["ephemeralMessage"]
    assert result.stdout_bytes.count(b"\n") == 1


@pytest.mark.parametrize(
    "agent,mcp_file", [("antigravity", "mcp_config.json"), ("zcode", "mcp.json")]
)
def test_new_native_host_connect_uses_owned_package_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, agent: str, mcp_file: str
) -> None:
    from test_memory_capsule import make_env

    from rush.integrations import agents
    from rush.permissions import ExecutionPermissions
    from rush.tools.agent_connection import AgentConnectionTool

    env = make_env(tmp_path, create_store=False)
    home = tmp_path / "native-home"
    home.mkdir()
    binary = str(tmp_path / "installed-rush")
    roots = materialize_agent_plugins(rush_binary=binary, data_root=env.data_root)
    agents.record_native_plugin_install(
        host=agent, plugin_root=roots[agent], data_root=env.data_root
    )
    mcp = roots[agent] / "rush" / mcp_file
    original = mcp.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("owned native connect invoked a host command")

    monkeypatch.setattr(agents.subprocess, "run", forbidden)
    result = AgentConnectionTool().run(
        agent,
        action="connect",
        session_id="actual-native-session",
        project_root=env.root,
        rush_binary=binary,
        consent=True,
        acknowledge=True,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        home=home,
        data_root=env.data_root,
    )
    assert result["status"] == "ok", result
    assert result["raw"]["apply"]["method"] == "native_plugin"
    assert result["raw"]["probe"]["config_path"] == str(mcp)
    assert result["raw"]["probe"]["status"] == "registered"
    assert mcp.read_bytes() == original and list(home.iterdir()) == []
    assert result["raw"]["memory"]["connected"] is True


def test_zcode_registration_nested_schema_preserves_compatibility_config(
    tmp_path: Path,
) -> None:
    from rush.integrations.agents import (
        apply_agent_registration,
        plan_agent_registration,
    )

    home = tmp_path / "home"
    native = home / ".zcode/cli/config.json"
    native.parent.mkdir(parents=True)
    native.write_text(
        '{"theme":"dark","mcp":{"servers":{"other":{"command":"other"}}}}\n'
    )
    compat = home / ".agents/mcp.json"
    compat.parent.mkdir()
    compat.write_bytes(b'{"mcpServers":{"rush":{"command":"older-rush"}}}\n')
    before = compat.read_bytes()
    step = plan_agent_registration("zcode", rush_binary="/installed/rush", home=home)
    assert step.config_path == native
    assert apply_agent_registration(step).ok
    data = json.loads(native.read_bytes())
    assert data["theme"] == "dark"
    assert data["mcp"]["servers"] == {
        "other": {"command": "other"},
        "rush": {
            "command": "/installed/rush",
            "args": ["mcp", "serve", "--profile", "core"],
        },
    }
    assert compat.read_bytes() == before


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_existing_packages_wire_native_events_and_keep_legacy_checks(host: str) -> None:
    hooks = json.loads(
        files("rush.integrations")
        .joinpath(f"agent_assets/{host}/hooks/hooks.json")
        .read_text()
    )["hooks"]
    for event in (
        "SessionStart",
        "PreCompact",
        "PostToolUse",
        "PostToolUseFailure",
        "Stop",
    ):
        matches = [
            h
            for entry in hooks[event]
            for h in entry["hooks"]
            if h["command"].endswith(f"agent hook {host} --event {event}")
        ]
        assert len(matches) == 1
        assert matches[0]["timeout"] == (10 if event in ("Stop", "PreCompact") else 5)
    assert (
        hooks["PostToolUse"][0]["hooks"][0]["command"]
        == f"@RUSH_BINARY_SH@ agent hook {host}"
    )
    assert hooks["PostToolUse"][0]["hooks"][0]["timeout"] == 30


@pytest.mark.parametrize(
    ("basis_id", "version", "code"),
    [
        ("cp1", 1, "OK"),
        ("cp1", 2, "E_VERSION"),
        ("absent", 1, "E_NOT_VISIBLE"),
        ("ev1", 1, "E_INPUT"),
        ("cp1", True, "E_INPUT"),
        ("foreign", 1, "E_NOT_VISIBLE"),
    ],
)
def test_public_checkpoint_write_pins_current_basis(
    tmp_path: Path, basis_id: str, version: int, code: str
) -> None:
    import sqlite3
    from contextlib import closing

    from test_memory_capsule import SRC, make_env, tree_state

    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    env = make_env(tmp_path)
    with closing(sqlite3.connect(env.db)) as conn:
        content = json.loads(
            conn.execute(
                "SELECT content FROM memory_artifacts WHERE id='cp1'"
            ).fetchone()[0]
        )
    content["event_id"] = "native-stop-1"
    if basis_id == "foreign":
        with closing(sqlite3.connect(env.db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET source='ungranted' WHERE id='cp1'"
            )
            conn.commit()
        basis_id = "cp1"
    request = {
        "schema_version": 2,
        "subject": "episodic",
        "source": SRC,
        "content": content,
        "apply": True,
        "invocation_id": "native-invocation",
        "effect_id": "checkpoint",
        "expected_basis": {"artifact_id": basis_id, "artifact_version": version},
    }
    before = tree_state(env.root, env.data_root)
    result = MemoryTool().run(
        env.root,
        operation="write",
        request=request,
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert result["raw"]["code"] == code, result
    if code != "OK":
        assert tree_state(env.root, env.data_root) == before
    else:
        replay = MemoryTool().run(
            env.root,
            operation="write",
            request=request,
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert replay["raw"]["code"] == "OK"
        assert replay["raw"]["items"] == result["raw"]["items"]
        assert replay["raw"]["data"] == result["raw"]["data"]


@pytest.mark.parametrize(
    "case", ["replay", "changed", "denied", "missing", "incomplete", "race", "revoked"]
)
def test_native_stop_preserves_complete_basis_and_replays(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    import sqlite3
    from contextlib import closing

    from test_memory_capsule import ALL_OPS, SRC, make_env

    from rush.integrations import agent_hooks, agents
    from rush.memory import authorization as auth
    from rush.memory.store import TypedArtifactStore, v2_operation_id
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    env = make_env(tmp_path, ops=(*ALL_OPS, "bootstrap"))
    with closing(sqlite3.connect(env.db)) as conn:
        content = json.loads(
            conn.execute(
                "SELECT content FROM memory_artifacts WHERE id='cp1'"
            ).fetchone()[0]
        )
    content.update(
        task_lineage_id=v2_operation_id("actual-start", "checkpoint"),
        event_id="actual-start",
        event_kind="task_start",
        requirements=[
            {
                "id": "R1",
                "text": "Wire CLI flag",
                "authority": "user",
                "provenance": "actual-start",
            }
        ],
        implemented=[],
        attempted=[],
        disproved=[],
        checks=[],
        unresolved=["wire CLI flag"],
        origin="agent_report",
    )
    if case == "incomplete":
        del content["task_lineage_id"]
    result = MemoryTool().run(
        env.root,
        operation="write",
        request={
            "schema_version": 2,
            "subject": "episodic",
            "source": SRC,
            "content": content,
            "apply": True,
            "invocation_id": "actual-start",
            "effect_id": "checkpoint",
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert result["raw"]["code"] == "OK", result
    session = "native-stop-session"
    binding = auth.register_memory_binding(
        grant_id=env.grant["grant_id"],
        session_id=session,
        host_id="antigravity",
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    request = {
        "task_id": "task-1",
        "task_kind": "memory_continuation",
        "query": "needle",
        "max_tokens": 16384,
        "session_binding": binding["binding_id"],
    }
    agents.initialize_agent_memory(
        "antigravity",
        session,
        project_root=env.root,
        data_root=env.data_root,
        consent=True,
    )
    agents.acknowledge_agent_connection(
        "antigravity", session, project_root=env.root, data_root=env.data_root
    )
    agents.record_tool_observation(
        "antigravity",
        session,
        {"bootstrap_request": request},
        project_root=env.root,
        data_root=env.data_root,
    )
    agent_hooks.set_hook_activation(
        "antigravity",
        env.root,
        enable=True,
        recovery_cache_write=True,
        data_root=env.data_root,
    )
    payload = {
        "conversationId": session,
        "workspacePaths": [str(env.root)],
        "executionNum": 1,
        "terminationReason": "model_stop",
        "fullyIdle": False,
    }
    if case == "denied":
        agent_hooks.set_hook_activation(
            "antigravity",
            env.root,
            enable=True,
            recovery_cache_write=False,
            data_root=env.data_root,
        )
    elif case == "missing":
        with closing(sqlite3.connect(env.db)) as conn:
            conn.execute("DELETE FROM memory_artifacts WHERE subject='episodic'")
            conn.commit()
    elif case == "revoked":
        auth.revoke_memory_scope(
            grant_id=env.grant["grant_id"],
            expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
            consent=True,
        )
    elif case == "race":
        original = TypedArtifactStore.write

        def racing_write(store, artifact, **kwargs):
            basis = kwargs.get("expected_basis")
            if basis is not None:
                edited = MemoryTool().run(
                    env.root,
                    operation="edit",
                    request={
                        "schema_version": 2,
                        "subject": "episodic",
                        "artifact_id": basis["artifact_id"],
                        "expected_version": basis["artifact_version"],
                        "content": {**content, "description": "Concurrent actual edit"},
                        "apply": True,
                        "invocation_id": "concurrent-edit",
                        "effect_id": "edit",
                    },
                    permissions=ExecutionPermissions(cache_write=True),
                )
                assert edited["raw"]["code"] == "OK", edited
            return original(store, artifact, **kwargs)

        monkeypatch.setattr(TypedArtifactStore, "write", racing_write)
    for attempt in range(2 if case in ("replay", "changed") else 1):
        if case == "changed" and attempt == 1:
            payload["terminationReason"] = "changed_same_execution"
        output = agent_hooks.run_native_agent_hook(
            "antigravity",
            json.dumps(payload).encode(),
            event="Stop",
            data_root=env.data_root,
        )
        assert json.loads(output) == {"decision": "stop"}
    with closing(sqlite3.connect(env.db)) as conn:
        rows = conn.execute(
            "SELECT content FROM memory_artifacts WHERE json_extract(content,'$.native_event.host')='antigravity'"
        ).fetchall()
        receipts = conn.execute(
            "SELECT COUNT(*) FROM mutation_receipts WHERE invocation_id LIKE 'native:%'"
        ).fetchone()[0]
    diagnostic = capfd.readouterr().err
    if case in ("denied", "missing", "incomplete", "race", "revoked"):
        assert len(rows) == 0 and receipts == 0
        expected = {
            "denied": "cache_write_required",
            "missing": "checkpoint_required",
            "incomplete": "checkpoint_required",
            "race": "E_VERSION",
            "revoked": "revoked",
        }[case]
        assert expected in diagnostic
        if case in ("missing", "incomplete"):
            assert "Use rush_memory operation=write" in diagnostic
        return
    assert len(rows) == 1 and receipts == 1
    checkpoint = json.loads(rows[0][0])
    assert checkpoint["event_kind"] == "interrupt"
    assert checkpoint["task_lineage_id"] == content["task_lineage_id"]
    assert checkpoint["requirements"] == content["requirements"]
    assert checkpoint["unresolved"] == ["wire CLI flag"] and checkpoint["checks"] == []
    assert checkpoint["native_event"]["fully_idle"] is False
    assert '"code":"OK"' in diagnostic
    if case == "changed":
        assert '"reason":"event_digest_conflict"' in diagnostic
