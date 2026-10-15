"""Phase 73 bootstrap: real scoped checkpoints, strict input and read-only delivery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from test_memory_capsule import ALL_OPS, COMMIT, make_env, put_checkpoint, tree_state
from test_phase72_memory_acceptance import DIMENSIONS as _BOOTSTRAP_DIMENSIONS

from rush.memory import authorization as auth
from rush.memory.retrieval import DEFAULT_ENCODING, _count_tokens
from rush.tools.memory import MemoryTool


def bootstrap_world(tmp_path: Path, *, create_store: bool = True):
    env = make_env(tmp_path, ops=(*ALL_OPS, "bootstrap"), create_store=create_store)
    binding = auth.register_memory_binding(
        grant_id=env.grant["grant_id"],
        session_id="bootstrap-lifecycle",
        host_id="codex",
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
    return env, request


def bootstrap(env, request):
    return MemoryTool().run(env.root, operation="bootstrap", request=request)


def test_bootstrap_recovers_scoped_checkpoint_without_writes(tmp_path: Path):
    env, request = bootstrap_world(tmp_path)
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, request)
    assert result["tool"] == "memory" and result["status"] == "ok"
    raw = result["raw"]
    assert raw["operation"] == "bootstrap" and raw["code"] == "OK"
    data = raw["data"]
    assert data["intent"] == {
        "task_id": "task-1",
        "task_kind": "memory_continuation",
        "query": "needle",
    }
    assert data["scope"]["session_binding"] == request["session_binding"]
    assert data["progress_state"] == "checkpoint_available"
    assert data["checkpoint"]["reference"] == {
        "artifact_id": "cp1",
        "artifact_version": 1,
        "source": "capsule-src",
    }
    assert data["task"]["remaining"] == ["wire the CLI flag"]
    assert data["next_action"] == {"text": "Wire the CLI flag and rerun the suite"}
    assert data["task"]["last_verified_checkpoint"] == {
        "command": ["pytest", "-q", "tests/x.py"],
        "status": "passed",
        "source_revision": COMMIT,
    }
    assert tree_state(env.root, env.data_root) == before
    emitted = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert len(emitted) <= 65536
    assert _count_tokens(emitted.decode(), DEFAULT_ENCODING) <= request["max_tokens"]


def test_bootstrap_no_store_is_unknown_progress_not_completion(tmp_path: Path):
    env, request = bootstrap_world(tmp_path, create_store=False)
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, request)
    assert result["raw"]["code"] == "OK"
    data = result["raw"]["data"]
    assert data["state"] == "empty" and data["items"] == []
    assert data["complete"] is True and data["next_cursor"] is None
    assert (
        data["task"] is None
        and data["checkpoint"] is None
        and data["unresolved"] is None
    )
    assert data["progress_state"] == "no_verified_checkpoint"
    assert data["intent"]["task_id"] == "task-1" and data["next_action"]["text"]
    assert not env.db.exists() and tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize(
    "change",
    [
        {"unknown": "field"},
        {"task_id": None},
        {"task_id": ""},
        {"query": "\x00"},
        {"query": "\ud800"},
        {"task_kind": "other"},
        {"max_tokens": True},
        {"max_tokens": 0},
        {"session_binding": None},
    ],
)
def test_bootstrap_rejects_invalid_request_before_effects(tmp_path: Path, change):
    env, request = bootstrap_world(tmp_path, create_store=False)
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, {**request, **change})
    assert result["raw"]["code"] == "E_INPUT" and result["raw"]["data"]["items"] == []
    assert tree_state(env.root, env.data_root) == before


def test_bootstrap_tiny_budget_refuses_complete_packet(tmp_path: Path):
    env, request = bootstrap_world(tmp_path, create_store=False)
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, {**request, "max_tokens": 1})
    assert result["raw"]["code"] == "E_INPUT"
    assert result["raw"]["data"]["admission_failure"] is True
    assert result["raw"]["data"]["items"] == []
    assert result["raw"]["data"]["required"]["max_tokens"] > 1
    assert tree_state(env.root, env.data_root) == before


def test_bootstrap_revoked_binding_exposes_no_checkpoint(tmp_path: Path):
    env, request = bootstrap_world(tmp_path)
    auth.revoke_memory_scope(
        grant_id=env.grant["grant_id"],
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, request)
    assert result["raw"]["code"] == "E_PERMISSION"
    data = result["raw"]["data"]
    assert data["items"] == [] and data["scope"] is None
    assert data["task"] is None and data["checkpoint"] is None
    assert tree_state(env.root, env.data_root) == before


def test_bootstrap_ambiguous_implicit_binding_needs_scope(tmp_path: Path):
    env, request = bootstrap_world(tmp_path)
    auth.register_memory_binding(
        grant_id=env.grant["grant_id"],
        session_id="second-session",
        host_id="claude-code",
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    request.pop("session_binding")
    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, request)
    assert result["raw"]["code"] == "E_PERMISSION"
    assert result["raw"]["data"]["state"] == "scope_required"
    assert (
        result["raw"]["data"]["scope"] is None and result["raw"]["data"]["items"] == []
    )
    assert tree_state(env.root, env.data_root) == before


def test_bootstrap_projection_generation_race_restarts(tmp_path: Path, monkeypatch):
    from rush.tools import memory as module

    env, request = bootstrap_world(tmp_path)
    original = module._bootstrap_task

    def changed(store, access, req):
        packet = original(store, access, req)
        put_checkpoint(
            env,
            "cp2",
            unresolved=["newer work"],
            next_action="Inspect newer checkpoint",
        )
        return packet

    monkeypatch.setattr(module, "_bootstrap_task", changed)
    result = bootstrap(env, request)
    assert result["raw"]["code"] == "E_RESTART"
    data = result["raw"]["data"]
    assert data["state"] == "restart" and data["items"] == []
    assert data["scope"] is None and data["task"] is None and data["checkpoint"] is None
    assert data["unresolved"] is None


def test_bootstrap_cli_shared_packet(tmp_path: Path):
    from rush.cli import cli

    env, request = bootstrap_world(tmp_path)
    outcome = CliRunner().invoke(
        cli,
        [
            "memory",
            "bootstrap",
            "--project",
            str(env.root),
            "--task-id",
            "task-1",
            "--task-kind",
            "memory_continuation",
            "--query",
            "needle",
            "--max-tokens",
            "16384",
            "--session-binding",
            request["session_binding"],
            "--json",
        ],
    )
    assert outcome.exit_code == 0, outcome.output
    result = json.loads(outcome.stdout)
    assert result["raw"]["code"] == "OK" and result["raw"]["operation"] == "bootstrap"
    assert result["raw"]["data"]["task"]["remaining"] == ["wire the CLI flag"]


def test_bootstrap_cli_budget_counts_pretty_frame(tmp_path: Path):
    from rush.cli import cli

    env, request = bootstrap_world(tmp_path, create_store=False)
    argv = [
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
        "--session-binding",
        request["session_binding"],
        "--json",
        "--max-tokens",
    ]
    before = tree_state(env.root, env.data_root)
    runner = CliRunner()
    initial = runner.invoke(cli, [*argv, "16384"])
    assert initial.exit_code == 0
    packet = json.loads(initial.stdout)
    canonical_tokens = _count_tokens(
        json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        DEFAULT_ENCODING,
    )
    rendered_tokens = _count_tokens(initial.stdout, DEFAULT_ENCODING)
    assert rendered_tokens > canonical_tokens + 2
    budget = (rendered_tokens + canonical_tokens) // 2
    refused = runner.invoke(cli, [*argv, str(budget)])
    result = json.loads(refused.stdout)
    assert result["raw"]["code"] == "E_BUDGET"
    assert result["raw"]["data"]["required"]["max_tokens"] > budget
    assert result["raw"]["data"]["items"] == []
    assert tree_state(env.root, env.data_root) == before


def test_bootstrap_public_nested_schema():
    from rush.mcp_support.request_models import (
        memory_request_model_keys,
        published_schema,
    )

    assert memory_request_model_keys("bootstrap") == {
        "task_id",
        "task_kind",
        "query",
        "max_tokens",
        "session_binding",
    }
    assert (
        "bootstrap"
        in published_schema("rush_memory")["properties"]["operation"]["enum"]
    )


def test_bootstrap_mcp_shared_packet(tmp_path: Path):
    from test_memory_capsule import _mcp_call

    env, request = bootstrap_world(tmp_path)
    before = tree_state(env.root, env.data_root)
    result = _mcp_call(
        {"path": str(env.root), "operation": "bootstrap", "request": request}
    )
    assert result["raw"]["code"] == "OK"
    data = result["raw"]["data"]
    assert data["scope"]["project_id"] == env.project_id
    assert data["scope"]["session_binding"] == request["session_binding"]
    assert data["task"]["remaining"] == ["wire the CLI flag"]
    assert data["next_action"] == {"text": "Wire the CLI flag and rerun the suite"}
    assert tree_state(env.root, env.data_root) == before


@pytest.mark.parametrize(
    ("dimension", "value"),
    [
        pytest.param(dimension, value, id=f"inproc.bootstrap-{dimension}-{value}")
        for dimension, values in _BOOTSTRAP_DIMENSIONS.items()
        for value in values
    ],
)
def test_bootstrap_route_mode_matrix(tmp_path: Path, dimension: str, value: str):
    """R8: bootstrap's actual policy/store states and strict unsupported controls."""
    import contextlib
    import sqlite3
    import time

    from test_memory_capsule import set_applicability
    from test_phase72_memory_hybrid import drop_payload_columns, tamper

    from rush.memory.retrieval import memory_policy_decision
    from rush.memory.store import next_row_mac

    env, request = bootstrap_world(
        tmp_path, create_store=(dimension, value) != ("store", "absent")
    )
    unsupported = {
        ("access", "legacy_allowlist"): ("session_allowlist", ["capsule-src"]),
        ("mode", "inspect"): ("mode", "inspect"),
        ("mode", "historical"): ("archive_mode", "historical"),
        ("representation", "base64"): ("representation", "base64"),
        ("representation", "utf8"): ("representation", "utf8"),
        ("retrieval", "hybrid"): ("retrieval", "hybrid"),
        ("apply", "apply"): ("apply", True),
        ("cache_write", "on"): ("cache_write", True),
        ("cache_write", "off"): ("cache_write", False),
        ("ack", "ack"): ("ack", "approved"),
        ("capability_ids", "selected"): ("capability_ids", ["cap-ungranted"]),
    }
    key = (dimension, value)
    if key in unsupported:
        field, supplied = unsupported[key]
        request[field] = supplied
    if key == ("access", "legacy_allowlist") or (
        dimension == "policy_state" and value.startswith("missing_")
    ):
        auth.policy_path(data_root=env.data_root).unlink()
        if value in ("legacy_allowlist", "missing_no_marker"):
            (env.root / ".rush" / auth.REGISTRATION_MARKER).unlink()
            assert memory_policy_decision(env.root) == ("legacy", None)
    elif key == ("policy_state", "invalid"):
        auth.policy_path(data_root=env.data_root).write_bytes(b"{")
    elif dimension == "grant_ops" or key == ("access", "overlay"):
        overlay = key == ("access", "overlay")
        operations = ["ask"] if value == "missing_one" else ["bootstrap"]
        if overlay:
            project_request = dict(request)
            operations.extend(("overlay_read", "list"))
        owner = (
            auth.user_overlay_owner_scope(data_root=env.data_root)
            if overlay
            else env.owner
        )
        grant = auth.grant_memory_scope(
            project_root=env.root,
            owner_scope=owner,
            approved_sources=env.grant["approved_sources"],
            allowed_operations=operations,
            expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
            consent=True,
        )
        binding = auth.register_memory_binding(
            grant_id=grant["grant_id"],
            session_id="bootstrap-matrix",
            host_id="codex",
            expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
            consent=True,
        )
        request["session_binding"] = binding["binding_id"]
        if overlay:
            overlay_before = tree_state(env.root, env.data_root)
            resolved = auth.resolve_memory_scope(
                project_root=env.root,
                operation="overlay_read",
                owner_scope=owner,
                session_binding=request["session_binding"],
            )
            assert resolved["access"] == "read", resolved
            assert resolved["grant_id"] == grant["grant_id"]
            assert resolved["owner_scope"] == owner.as_dict()
            assert tree_state(env.root, env.data_root) == overlay_before
    elif key == ("store", "old_schema"):
        drop_payload_columns(env.db)
    elif dimension == "row_state" and value != "active":
        if value == "archived":
            env.store.archive(
                "cp1",
                expected_version=1,
                scope="episodic",
                owner_scope=env.owner,
                apply=True,
            )
        elif value in ("rejected", "pending"):
            set_applicability(env, "cp1", value)
        elif value == "tampered":
            tamper(env.root, "cp1")
        else:
            assert value == "expired"
            with contextlib.closing(sqlite3.connect(env.db)) as conn:
                expired = time.time() - 10
                mac = next_row_mac(conn, env.root, "cp1", {"expires_at": expired})
                conn.execute(
                    "UPDATE memory_artifacts SET expires_at = ?, row_mac = ? "
                    "WHERE id = ?",
                    (expired, mac, "cp1"),
                )
                conn.commit()

    before = tree_state(env.root, env.data_root)
    result = bootstrap(env, request)
    raw = result["raw"]
    data = raw["data"]
    assert raw["operation"] == "bootstrap"
    assert tree_state(env.root, env.data_root) == before
    if key in unsupported:
        assert raw["code"] == "E_INPUT", result
        assert data == {"state": "invalid", "field": unsupported[key][0], "items": []}
    elif dimension == "policy_state" and value != "ok":
        assert raw["code"] == "E_PERMISSION", result
        assert data["reason"] == (
            "policy_invalid" if value == "invalid" else "policy_missing"
        )
        assert data["state"] == ("denied" if value == "invalid" else "scope_required")
        assert data["items"] == [] and data["scope"] is None
        assert data["task"] is None and data["checkpoint"] is None
    elif key == ("grant_ops", "missing_one"):
        assert raw["code"] == "E_PERMISSION", result
        assert data["reason"] == "operation_not_granted" and data["state"] == "denied"
        assert data["items"] == [] and data["scope"] is None
        assert data["task"] is None and data["checkpoint"] is None
    elif key == ("store", "old_schema"):
        assert raw["code"] == "E_MIGRATION", result
        assert data["state"] == "migration_required"
        assert data["items"] == [] and data["scope"] is None
        assert data["task"] is None and data["checkpoint"] is None
    elif key == ("access", "overlay"):
        assert raw["code"] == "E_PERMISSION", result
        assert data["reason"] == "owner_not_granted" and data["state"] == "denied"
        assert data["items"] == [] and data["scope"] is None
        assert data["task"] is None and data["checkpoint"] is None
        project = bootstrap(env, project_request)
        assert project["raw"]["code"] == "OK", project
        project_data = project["raw"]["data"]
        assert (
            project_data["scope"]["session_binding"]
            == (project_request["session_binding"])
        )
        assert project_data["scope"]["grant_id"] == env.grant["grant_id"]
        assert project_data["checkpoint"]["reference"] == {
            "artifact_id": "cp1",
            "artifact_version": 1,
            "source": "capsule-src",
        }
        assert project_data["task"]["remaining"] == ["wire the CLI flag"]
        assert tree_state(env.root, env.data_root) == before
    elif key == ("store", "absent"):
        assert raw["code"] == "OK", result
        assert data["state"] == "empty" and data["items"] == []
        assert data["progress_state"] == "no_verified_checkpoint"
        assert data["task"] is None and data["checkpoint"] is None
        assert not env.db.exists()
    elif dimension == "row_state" and value != "active":
        assert raw["code"] == "OK", result
        assert data["progress_state"] == "no_verified_checkpoint"
        assert data["task"] is None and data["checkpoint"] is None
    else:
        assert raw["code"] == "OK", result
        assert data["state"] == "ready" and "retrieval" not in data
        assert data["progress_state"] == "checkpoint_available"
        assert data["scope"]["session_binding"] == request["session_binding"]
        assert data["checkpoint"]["reference"] == {
            "artifact_id": "cp1",
            "artifact_version": 1,
            "source": "capsule-src",
        }
        assert data["task"]["remaining"] == ["wire the CLI flag"]
        assert data["task"]["last_verified_checkpoint"] == {
            "command": ["pytest", "-q", "tests/x.py"],
            "status": "passed",
            "source_revision": COMMIT,
        }
        assert data["next_action"] == {"text": "Wire the CLI flag and rerun the suite"}
        return
    emitted = json.dumps(result, ensure_ascii=False)
    assert "Portable capsule work" not in emitted
    assert "wire the CLI flag" not in emitted
