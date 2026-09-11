"""Tests for Phase 63 memory activation over agent connections (P65-05, F35).

Scope model: user/project/session/agent, all four backed by
`rush.integrations.agents`'s own CAS-transaction-based readiness store (never
the real production Rush data root -- every call here passes an explicit
`project_root` or `data_root` under `tmp_path`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.integrations import agents as agents_mod
from rush.integrations.agents import (
    AgentConnectionError,
    acknowledge_agent_connection,
    agent_memory_store_path,
    initialize_agent_memory,
    read_agent_memory_state,
    record_tool_observation,
)
from rush.memory.transactions import CASConflictError, CASMapTransaction

RUSH_BINARY = "/opt/rush/bin/rush"


def test_project_scopes_isolated_across_projects_and_agents(tmp_path: Path) -> None:
    project_a = tmp_path / "proj-a"
    project_a.mkdir()
    project_b = tmp_path / "proj-b"
    project_b.mkdir()

    initialize_agent_memory(
        "claude-code", "sess-1", project_root=project_a, consent=True
    )
    initialize_agent_memory("cursor", "sess-1", project_root=project_a, consent=True)
    initialize_agent_memory(
        "claude-code", "sess-2", project_root=project_b, consent=True
    )

    record_tool_observation(
        "claude-code", "sess-1", {"tool": "lint"}, project_root=project_a
    )
    record_tool_observation(
        "claude-code", "sess-2", {"tool": "review"}, project_root=project_b
    )

    a_state = read_agent_memory_state("claude-code", "sess-1", project_root=project_a)
    b_state = read_agent_memory_state("claude-code", "sess-2", project_root=project_b)
    cursor_a_state = read_agent_memory_state("cursor", "sess-1", project_root=project_a)

    assert a_state is not None and a_state["last_observation"] == {"tool": "lint"}
    assert b_state is not None and b_state["last_observation"] == {"tool": "review"}
    assert cursor_a_state is not None and cursor_a_state["last_observation"] is None

    # Same session ID + agent ID in a *different* project never sees the other's data.
    assert (
        read_agent_memory_state("claude-code", "sess-1", project_root=project_b) is None
    )
    assert (
        read_agent_memory_state("claude-code", "sess-2", project_root=project_a) is None
    )

    assert agent_memory_store_path(project_root=project_a) != agent_memory_store_path(
        project_root=project_b
    )


def test_user_scope_isolated_from_project_scope(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "rush-data"

    initialize_agent_memory("codex", "sess-1", project_root=project, consent=True)
    initialize_agent_memory("codex", "sess-1", data_root=data_root, consent=True)

    record_tool_observation(
        "codex", "sess-1", {"tool": "project-scoped"}, project_root=project
    )
    record_tool_observation(
        "codex", "sess-1", {"tool": "user-scoped"}, data_root=data_root
    )

    project_state = read_agent_memory_state("codex", "sess-1", project_root=project)
    user_state = read_agent_memory_state("codex", "sess-1", data_root=data_root)

    assert project_state is not None
    assert user_state is not None
    assert project_state["last_observation"] == {"tool": "project-scoped"}
    assert user_state["last_observation"] == {"tool": "user-scoped"}
    assert project_state["scope"] == "project"
    assert user_state["scope"] == "user"
    assert agent_memory_store_path(project_root=project) != agent_memory_store_path(
        data_root=data_root
    )


def test_transactional_rollback_leaves_no_synthetic_artifact(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    initialize_agent_memory("codex", "sess-1", project_root=project, consent=False)

    store_path = agent_memory_store_path(project_root=project)
    before_text = store_path.read_text(encoding="utf-8")

    tx = CASMapTransaction(file_path=store_path, root_path=project)
    snapshot = tx.read()
    with pytest.raises(CASConflictError):
        tx.write(
            {"schema_version": 1, "entries": {"synthetic": {"fake": True}}},
            expected_version=snapshot.version + 1,
        )

    after_text = store_path.read_text(encoding="utf-8")
    assert after_text == before_text
    assert "synthetic" not in after_text


def test_record_observation_requires_prior_consent(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    initialize_agent_memory("zed", "sess-1", project_root=project, consent=False)

    with pytest.raises(AgentConnectionError):
        record_tool_observation("zed", "sess-1", {"x": 1}, project_root=project)

    state = read_agent_memory_state("zed", "sess-1", project_root=project)
    assert state is not None
    assert state["last_observation"] is None


def test_record_observation_requires_initialized_scope(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    with pytest.raises(AgentConnectionError):
        record_tool_observation(
            "zed", "unknown-session", {"x": 1}, project_root=project
        )


def test_tool_observation_persists_across_reads(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    initialize_agent_memory("codex", "sess-9", project_root=project, consent=True)
    record_tool_observation(
        "codex", "sess-9", {"tool": "typecheck", "findings": 3}, project_root=project
    )

    reread = read_agent_memory_state("codex", "sess-9", project_root=project)
    assert reread is not None
    assert reread["last_observation"] == {"tool": "typecheck", "findings": 3}


def test_connected_requires_explicit_acknowledgment(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    entry = initialize_agent_memory(
        "cursor", "sess-1", project_root=project, consent=True
    )
    assert entry["connected"] is False

    record_tool_observation("cursor", "sess-1", {"tool": "scan"}, project_root=project)
    still_unconnected = read_agent_memory_state(
        "cursor", "sess-1", project_root=project
    )
    assert still_unconnected is not None
    assert still_unconnected["connected"] is False

    acked = acknowledge_agent_connection("cursor", "sess-1", project_root=project)
    assert acked["connected"] is True
    assert acked["acknowledged_at"] is not None


def test_acknowledge_requires_initialized_scope(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    with pytest.raises(AgentConnectionError):
        acknowledge_agent_connection("cursor", "no-such-session", project_root=project)


def test_cli_agent_connect_and_doctor_acknowledge_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # Force config-edit for claude-code too -- never exec a real 'claude' from PATH here.
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)

    project = tmp_path / "proj"
    project.mkdir()
    runner = CliRunner()

    connect_result = runner.invoke(
        cli,
        [
            "agent",
            "connect",
            "cursor",
            "--session",
            "sess-1",
            "--project",
            str(project),
            "--rush-binary",
            RUSH_BINARY,
            "--consent",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert connect_result.exit_code == 0, connect_result.output
    connect_payload = json.loads(connect_result.output)
    assert connect_payload["status"] == "ok"
    assert connect_payload["raw"]["memory"]["connected"] is False

    doctor_before = runner.invoke(
        cli,
        ["agent", "doctor", "--session", "sess-1", "--project", str(project), "--json"],
    )
    assert doctor_before.exit_code == 0, doctor_before.output
    doctor_payload = json.loads(doctor_before.output)
    cursor_memory = doctor_payload["raw"]["memory"]["cursor"]
    assert cursor_memory["connected"] is False

    ack_result = runner.invoke(
        cli,
        [
            "agent",
            "connect",
            "cursor",
            "--session",
            "sess-1",
            "--project",
            str(project),
            "--rush-binary",
            RUSH_BINARY,
            "--consent",
            "--acknowledge",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert ack_result.exit_code == 0, ack_result.output
    ack_payload = json.loads(ack_result.output)
    assert ack_payload["raw"]["memory"]["connected"] is True
    assert ack_payload["raw"]["probe"]["status"] == "registered"

    doctor_after = runner.invoke(
        cli,
        ["agent", "doctor", "--session", "sess-1", "--project", str(project), "--json"],
    )
    doctor_after_payload = json.loads(doctor_after.output)
    assert doctor_after_payload["raw"]["memory"]["cursor"]["connected"] is True


def test_cli_agent_list_never_touches_real_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    runner = CliRunner()
    result = runner.invoke(cli, ["agent", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    agent_ids = {agent["agent_id"] for agent in payload["raw"]["agents"]}
    assert agent_ids == {
        "claude-desktop",
        "claude-code",
        "cursor",
        "windsurf",
        "zed",
        "codex",
    }
    assert all(agent["status"] == "not_detected" for agent in payload["raw"]["agents"])
