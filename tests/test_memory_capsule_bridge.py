"""Portable bridge exercises real public preview/apply/replay and readonly codecs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_memory_capsule import call, export_file, make_env, new_uuid, sha, tree_state

from rush.integrations import agents
from rush.memory import authorization as auth


@pytest.mark.parametrize("action", ["bridge", "export", "import"])
def test_capsule_transport_wrapper_budget_before_write(tmp_path: Path, action):
    from mcp.types import CallToolResult

    from rush.delivery import compact
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    env = make_env(tmp_path)
    path = export_file(env)
    if action == "bridge":
        target = env.root / "AGENTS.md"
        target.write_bytes(b"original instructions\n")
        request = bridge_request(env, path, target)
    elif action == "export":
        request = {
            "action": "preview_export",
            "output": str(env.root / "second.json"),
            "invocation_id": new_uuid(),
        }
    else:
        request = {
            "action": "preview_import",
            "input": str(path),
            "invocation_id": new_uuid(),
        }
    cap = len(path.read_bytes()) + 5000
    request["max_bytes"] = cap
    preview = call("inproc", env.root, request)
    assert preview.code == "OK"
    request.update(action=action, expected_digest=preview.data["digest"])
    if action in {"bridge", "import"}:
        request["apply"] = True
    if action == "import":
        request["expected_store_revision"] = preview.data["store_revision"]
    frame = compact.FrameContext(
        "mcp_stdio",
        "r" * (70000 if action == "export" else cap - 1000),
        emit=lambda value: compact.mcp_frame_bytes(
            CallToolResult(content=[], structuredContent=dict(value)),
            "r" * (70000 if action == "export" else cap - 1000),
        ),
    )
    before = tree_state(env.root)
    policy = auth.load_policy_readonly()["content_sha256"]
    result = MemoryTool().run(
        env.root,
        operation="capsule",
        request=request,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        frame=frame,
    )
    assert result["raw"]["code"] == ("E_INPUT" if action == "export" else "E_BUDGET")
    assert result["raw"]["data"]["reason"] == (
        "budget_below_minimum" if action == "export" else "response_blocked"
    )
    assert result["raw"]["data"]["admission_failure"] is (action == "export")
    assert result["raw"]["data"]["required"]["bytes"] > cap
    assert tree_state(env.root) == before
    assert auth.load_policy_readonly()["content_sha256"] == policy


def bridge_request(env, capsule: Path, target: Path):
    return {
        "action": "bridge",
        "input": str(capsule),
        "instructions": str(target),
        "invocation_id": new_uuid(),
        "max_bytes": 65536,
        "max_tokens": 16384,
    }


@pytest.mark.parametrize(
    "original",
    [
        None,
        b"",
        b"abc",
        b"abc\r\n",
        b"<!-- rush:capsule:begin -->\r\n\r\n<!-- rush:capsule:end -->",
    ],
)
def test_bridge_public_bytes_and_replay(tmp_path: Path, monkeypatch, original):
    env = make_env(tmp_path)
    capsule = export_file(env)
    target = env.root / "AGENTS.md"
    if original is not None:
        target.write_bytes(original)
    base = bridge_request(env, capsule, target)
    before = tree_state(env.root, env.data_root)
    calls = []
    real = agents.cas_replace_file

    def replacement(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(agents, "cas_replace_file", replacement)
    preview = call("inproc", env.root, base)
    assert preview.code == "OK" and preview.data["stage"] == "preview"
    assert preview.data["before_sha256"] == (
        None if original is None else sha(original)
    )
    assert calls == [] and tree_state(env.root, env.data_root) == before
    request = {**base, "apply": True, "expected_digest": preview.data["digest"]}
    written = call("inproc", env.root, request)
    assert written.code == "OK" and written.data["stage"] == "written" and calls == [1]
    current = target.read_bytes()
    from rush.memory.capsule import _bridge_outside

    if original is not None and b"<!-- rush:capsule:begin -->" in original:
        assert _bridge_outside(current) == _bridge_outside(original)
    else:
        assert current.startswith(original or b"")
    assert written.data["after_sha256"] == sha(current)
    after = tree_state(env.root, env.data_root)
    replay = call("inproc", env.root, request)
    assert replay.code == "OK" and replay.data["stage"] == "replayed"
    assert (
        replay.data["replayed"] is True
        and replay.data["effect_id"] == written.data["effect_id"]
    )
    assert replay.data["preview_digest"] == preview.data["digest"]
    assert replay.data["reread"]["state"] == "required"
    assert calls == [1] and tree_state(env.root, env.data_root) == after


@pytest.mark.parametrize("transport", ["cli", "mcp"])
def test_bridge_cli_mcp_existing_target_shared_apply(tmp_path: Path, transport):
    env = make_env(tmp_path)
    capsule = export_file(env, transport="mcp")
    target = env.root / "AGENTS.md"
    target.write_bytes(b"user instructions\r\n")
    request = bridge_request(env, capsule, target)
    before = tree_state(env.root, env.data_root)
    preview = call(transport, env.root, request)
    assert preview.code == "OK" and preview.data["stage"] == "preview"
    assert tree_state(env.root, env.data_root) == before
    request.update(apply=True, expected_digest=preview.data["digest"])
    written = call(transport, env.root, request)
    assert written.code == "OK" and written.data["stage"] == "written"
    after = tree_state(env.root, env.data_root)
    replay = call(transport, env.root, request)
    assert replay.code == "OK" and replay.data["stage"] == "replayed"
    assert tree_state(env.root, env.data_root) == after


def test_bridge_changed_authority_conflicts_before_replay(tmp_path: Path):
    env = make_env(tmp_path)
    capsule = export_file(env)
    target = env.root / "AGENTS.md"
    target.write_bytes(b"user instructions\n")
    base = bridge_request(env, capsule, target)
    preview = call("inproc", env.root, base)
    assert preview.code == "OK"
    request = {**base, "apply": True, "expected_digest": preview.data["digest"]}
    assert call("inproc", env.root, request).code == "OK"
    auth.register_memory_binding(
        grant_id=env.grant["grant_id"],
        session_id="new-authority",
        host_id="codex",
        expected_policy_revision=auth.load_policy_readonly()["policy_revision"],
        consent=True,
    )
    before = tree_state(env.root, env.data_root)
    failure = call("inproc", env.root, request)
    assert (
        failure.code == "E_VERSION"
        and failure.data["reason"] == "effect_digest_conflict"
    )
    assert tree_state(env.root, env.data_root) == before


def test_bridge_target_edit_and_missing_artifact_permission_no_write(tmp_path: Path):
    env = make_env(tmp_path)
    capsule = export_file(env)
    target = env.root / "AGENTS.md"
    target.write_bytes(b"user instructions\n")
    base = bridge_request(env, capsule, target)
    preview = call("inproc", env.root, base)
    assert preview.code == "OK"
    request = {**base, "apply": True, "expected_digest": preview.data["digest"]}
    denied = call("inproc", env.root, request, artifact=False)
    assert denied.status == "skipped"
    target.write_bytes(b"concurrent user edit\n")
    before = tree_state(env.root)
    policy_sha = auth.load_policy_readonly()["content_sha256"]
    failure = call("inproc", env.root, request)
    assert failure.code == "E_VERSION"
    assert (
        target.read_bytes() == b"concurrent user edit\n"
        and tree_state(env.root) == before
    )
    assert auth.load_policy_readonly()["content_sha256"] == policy_sha


@pytest.mark.parametrize(
    "original",
    [
        b"<!-- rush:capsule:begin -->\n",
        b"<!-- rush:capsule:end -->\n<!-- rush:capsule:begin -->\n",
        b"prefix <!-- rush:capsule:begin -->\n<!-- rush:capsule:end -->\n",
        b"<!-- rush:capsule:begin -->\n<!-- rush:capsule:begin -->\n<!-- rush:capsule:end -->\n",
    ],
)
def test_bridge_malformed_markers_no_write(tmp_path: Path, original):
    env = make_env(tmp_path)
    capsule = export_file(env)
    target = env.root / "AGENTS.md"
    target.write_bytes(original)
    before = tree_state(env.root, env.data_root)
    result = call("inproc", env.root, bridge_request(env, capsule, target))
    assert (
        result.code == "E_INPUT"
        and result.data["reason"] == "capsule_bridge_marker_conflict"
    )
    assert tree_state(env.root, env.data_root) == before


def test_snapshot_restores_ordered_constraints_without_writes(tmp_path: Path):
    from rush.memory.capsule import read_snapshot

    env = make_env(tmp_path)
    path = export_file(env)
    doc = json.loads(path.read_bytes())
    before = tree_state(env.root, env.data_root, env.outside)
    result = read_snapshot(env.root, path, "rush_v1", doc["payload_sha256"], 16384)
    assert result["code"] == "OK" and result["progress_state"] == "unverified_snapshot"
    assert result["task"]["constraints"] == doc["task"]["constraints"]
    assert [c["constraint_id"] for c in result["task"]["constraints"]] == ["c1", "c2"]
    assert result["task"]["remaining"] == ["wire the CLI flag"]
    assert result["authority"] == "imported_unverified"
    assert tree_state(env.root, env.data_root, env.outside) == before


def test_snapshot_complete_evidence_without_origin_store(tmp_path: Path):
    from rush.memory.capsule import read_snapshot

    env = make_env(tmp_path)
    exported = export_file(env)
    document = json.loads(exported.read_bytes())
    recipient = tmp_path / "offline-recipient"
    recipient.mkdir()
    path = recipient / "approved.json"
    path.write_bytes(exported.read_bytes())
    env.db.unlink()  # Origin deliberately unavailable; copied capsule is sole input.
    before = tree_state(recipient, env.root, env.data_root)
    snapshot = read_snapshot(
        recipient, path, "rush_v1", document["payload_sha256"], 16384
    )
    assert snapshot["code"] == "OK"
    assert snapshot["authority"] == "imported_unverified"
    assert snapshot["task"]["remaining"] == document["task"]["remaining"]
    records = {r["foreign_origin_id"]: r["content"] for r in snapshot["records"]}
    for evidence in document["evidence"]:
        assert (
            records[f"evidence:{evidence['artifact_id']}@{evidence['version']}"]
            == evidence["body"]
        )
    assert snapshot["task"]["constraints"] == document["task"]["constraints"]
    assert not env.db.exists() and not (recipient / ".rush").exists()
    assert tree_state(recipient, env.root, env.data_root) == before


def test_snapshot_budget_counts_normalized_task_and_records(tmp_path: Path):
    from rush.delivery.compact import canonical_json
    from rush.memory.capsule import read_snapshot
    from rush.memory.retrieval import DEFAULT_ENCODING, _count_tokens

    payload = {
        "id": new_uuid(),
        "project_name": "offline",
        "created_at": "2017-01-01T00:00:00Z",
        "updated_at": "2017-01-01T00:00:00Z",
        "task": {"objective": "required offline objective " * 300},
    }
    original = json.dumps(payload).encode()
    path = tmp_path / "pas.json"
    path.write_bytes(original)
    snapshot = read_snapshot(tmp_path, path, "pas_v1", sha(original), 16384)
    assert snapshot["code"] == "OK"
    input_tokens = _count_tokens(original.decode(), DEFAULT_ENCODING)
    rendered_tokens = _count_tokens(canonical_json(snapshot).decode(), DEFAULT_ENCODING)
    assert rendered_tokens > input_tokens + 10
    budget = (rendered_tokens + input_tokens) // 2
    before = tree_state(tmp_path)
    refusal = read_snapshot(tmp_path, path, "pas_v1", sha(original), budget)
    assert refusal["code"] == "E_BUDGET" and refusal["reason"] == "snapshot_blocked"
    assert refusal["required"]["tokens"] == rendered_tokens
    assert "task" not in refusal and "records" not in refusal
    assert tree_state(tmp_path) == before


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2017-01-01T00:00:00UTC", 1483228800.0),
        ("2016-12-31T23:59:60Z", 1483228800.0),
        ("2017-01-01 00:00:00z", 1483228800.0),
        ("2017-01-01t00:00:00Z", 1483228800.0),
        ("2017-01-01T01:00:00+0100", 1483228800.0),
        ("2017-01-01T01:00:00+01:00", 1483228800.0),
        ("2017-01-01T00:00:00.125Z", 1483228800.125),
        ("2016-12-31T23:59:60.5Z", 1483228800.5),
    ],
)
def test_pas_snapshot_preserves_timestamp_grammar(tmp_path: Path, stamp, expected):
    from rush.memory.capsule import read_snapshot

    data = json.dumps(
        {
            "id": new_uuid(),
            "project_name": "timestamp-fixture",
            "created_at": stamp,
            "updated_at": stamp,
            "task": {},
        }
    ).encode("utf-8")
    path = tmp_path / "session.json"
    path.write_bytes(data)
    result = read_snapshot(tmp_path, path, "pas_v1", sha(data), 16384)
    assert result["code"] == "OK" and result["created_at"] == expected
    assert result["progress_state"] == "limited_unverified_snapshot"
    assert (
        result["task"]["last_verified_checkpoint"] is None
        and result["task"]["next_action"] is None
    )
    assert (
        result["task"]["constraints"] == []
        and not (tmp_path / ".rush/memory.db").exists()
    )
    assert path.read_bytes() == data
