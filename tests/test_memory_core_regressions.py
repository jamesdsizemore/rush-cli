"""Behavioral regressions for Phase 61/62 core review findings."""

import dataclasses
import json
import sqlite3
import time

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.codegraph.context_packer import ContextPacker
from rush.continuity.context import pack_context, retrieve_context
from rush.memory.expiry import sweep_expired
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    compute_content_signature,
    legacy_owner_scope,
)
from rush.permissions import ExecutionPermissions
from rush.token_economy.ccr_store import CCRStore
from rush.token_economy.memory_cache_gate import check_memory_before_pack
from rush.token_economy.telemetry import TelemetryStore
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

GRANTED = ExecutionPermissions(cache_write=True)


def test_legacy_cache_without_hash_misses_and_refills(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 2\n")
    store = TypedArtifactStore(tmp_path)
    store.write(
        dataclasses.replace(
            artifact("legacy", source="context_pack", symbol_ref="module.py::hello"),
            content={
                "cache_key": "module.py:hello",
                "packed_text": "return 1",
                "tokens": 2,
            },
        )
    )
    assert not check_memory_before_pack("module.py", "hello", project_root=tmp_path).hit
    result = pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10000, GRANTED
    )
    assert "return 2" in json.dumps(result)
    gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    assert gate.hit
    assert "return 2" in gate.content["packed_text"]


def test_pack_context_and_retrieve_context_persist_caller_attribution_not_a_path(
    tmp_path,
):
    """M11: `pack_context`/`retrieve_context`'s own telemetry writes must
    persist caller-supplied project/run/agent/session attribution -- never
    invent `project_id` from `str(project_root)` (a filesystem path is not
    a registered project UUID), mirroring `memory/retrieval.py`'s
    hybrid/recall/expand boundary T010 already fixed."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n")
    pack_context(
        time.monotonic(),
        tmp_path,
        "module.py",
        "hello",
        10000,
        GRANTED,
        project_id="proj-real-uuid",
        run_id="run-1",
        agent_id="agent-1",
        session_id="session-1",
    )
    db_path = TelemetryStore(tmp_path).db_path
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id, run_id, agent_id, session_id FROM memory_events "
            "WHERE kind = 'packing'"
        ).fetchone()
    assert row == ("proj-real-uuid", "run-1", "agent-1", "session-1")
    assert row[0] != str(tmp_path)

    tag = CCRStore(tmp_path).store_chunk("cached content for a handoff")
    handle = tag.removeprefix("<!-- ccr:chunk:").removesuffix(" -->")
    retrieve_context(
        time.monotonic(),
        tmp_path,
        handle,
        GRANTED,
        project_id="proj-real-uuid",
        run_id="run-2",
        agent_id="agent-2",
        session_id="session-2",
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT project_id, run_id, agent_id, session_id FROM memory_events "
            "WHERE kind = 'handoff'"
        ).fetchone()
    assert row == ("proj-real-uuid", "run-2", "agent-2", "session-2")
    assert row[0] != str(tmp_path)


def test_cache_hash_covers_same_read_as_packed_payload(tmp_path, monkeypatch):
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n")
    original_pack = ContextPacker.pack

    def edit_after_pack(self, *args, **kwargs):
        packed = original_pack(self, *args, **kwargs)
        target.write_text("def hello():\n    return 2\n")
        return packed

    monkeypatch.setattr(ContextPacker, "pack", edit_after_pack)
    first = pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10000, GRANTED
    )
    assert "return 1" in json.dumps(first)
    assert not check_memory_before_pack("module.py", "hello", project_root=tmp_path).hit
    monkeypatch.setattr(ContextPacker, "pack", original_pack)
    second = pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10000, GRANTED
    )
    assert "return 2" in json.dumps(second)
    gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    assert gate.hit
    assert "return 2" in gate.content["packed_text"]


def artifact(key, *, source="allowed", tier="DERIVED", age=0, **kwargs):
    return MemoryArtifact(
        id=key,
        family="memory",
        subject="domain_knowledge",
        trust_tier=tier,
        content={"fact": "needle"},
        source=source,
        created_at=time.time() - age,
        **kwargs,
    )


@pytest.mark.parametrize(
    "task",
    ["expiry_sweep", "staleness_sweep", "promotion_sweep", "skill_admission_check"],
)
def test_maintenance_denied_creates_no_resources(tmp_path, monkeypatch, task):
    decoy = tmp_path / "decoy"
    requested = tmp_path / "requested"
    decoy.mkdir()
    requested.mkdir()
    monkeypatch.chdir(decoy)
    result = MemoryTool().run(requested, operation="maintain", task=task)
    assert result["status"] == "skipped"
    assert not (requested / ".rush").exists()
    assert not (decoy / ".rush").exists()


@pytest.mark.parametrize("task", ["expiry_sweep", "staleness_sweep", "promotion_sweep"])
def test_maintenance_uses_requested_root(tmp_path, monkeypatch, task):
    requested = tmp_path / "requested"
    decoy = tmp_path / "decoy"
    requested.mkdir()
    decoy.mkdir()
    store = TypedArtifactStore(requested)
    target = requested / "module.py"
    target.write_text("def hello():\n    return 1\n")
    digest = MerkleInvalidator(requested).hash_content(target.read_text())
    store.write(
        artifact(
            "target", age=20 * 86400, symbol_ref="module.py::hello", content_hash=digest
        )
    )
    if task == "staleness_sweep":
        target.write_text("def hello():\n    return 2\n")
    if task == "promotion_sweep":
        store.write(
            artifact("second", source="independent", symbol_ref="module.py::hello")
        )
    monkeypatch.chdir(decoy)
    result = MemoryTool().run(
        requested,
        operation="maintain",
        task=task,
        permissions=GRANTED,
        owner_scope=legacy_owner_scope(requested),
    )
    assert result["status"] == "ok"
    assert result["raw"]["changed"] >= 1
    assert result["raw"]["errors"] == ()
    assert not (decoy / ".rush").exists()
    assert (requested / ".rush" / "locks").is_dir()


@pytest.mark.parametrize("symbol", ["hello", ""])
@pytest.mark.parametrize("change", ["body", "delete", "unreadable", "untouched"])
def test_real_pack_cache_tracks_whole_file(tmp_path, symbol, change):
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n")
    result = pack_context(
        time.monotonic(), tmp_path, "module.py", symbol, 10000, GRANTED
    )
    assert result["status"] == "ok"
    assert check_memory_before_pack("module.py", symbol, project_root=tmp_path).hit
    if change == "body":
        target.write_text("def hello():\n    return 2\n")
    elif change == "delete":
        target.unlink()
    elif change == "unreadable":
        target.write_bytes(b"\xff")
    gate = check_memory_before_pack("module.py", symbol, project_root=tmp_path)
    assert gate.hit is (change == "untouched")
    recalled = TypedArtifactStore(tmp_path).recall(
        "domain_knowledge", f'"module.py:{symbol}"', ["context_pack"]
    )
    assert recalled[0].stale is (change != "untouched")
    if change == "body" and symbol:
        fresh = pack_context(
            time.monotonic(), tmp_path, "module.py", symbol, 10000, GRANTED
        )
        assert "return 2" in json.dumps(fresh)


@pytest.mark.parametrize("user_stated", [True, False])
def test_public_promotion_persists_signed_sanitized_record(tmp_path, user_stated):
    result = MemoryTool().run(
        tmp_path,
        operation="promote",
        subject="domain_knowledge",
        content={"fact": "needle", "api_key": "sk-" + "a" * 40},
        source="allowed",
        user_stated=user_stated,
        source_kind="human_derived",
        permissions=GRANTED,
    )
    record = result["raw"]["artifact"]
    assert record["trust_tier"] == ("STATED" if user_stated else "DERIVED")
    assert record["content"]["api_key"] == "[REDACTED_OPENAI_KEY]"
    assert record["signature"] == (
        compute_content_signature(record["content"]) if user_stated else None
    )
    assert (record["promoted_at"] is not None) is user_stated
    recalled = MemoryTool().run(
        tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
    )
    assert recalled["status"] == "ok"
    assert recalled["raw"] == [record]


def test_promotion_update_is_transactional(tmp_path):
    store = TypedArtifactStore(tmp_path)
    store.write(artifact("candidate"))
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "CREATE TRIGGER reject_promotion BEFORE UPDATE ON memory_artifacts WHEN NEW.trust_tier = 'STATED' BEGIN SELECT RAISE(ABORT, 'reject promotion'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="reject promotion"):
        store.promote("candidate", user_stated=True)
    stored = store.search("domain_knowledge", "needle")[0]
    assert stored.trust_tier == "DERIVED"
    assert stored.signature is None
    assert stored.promoted_at is None
    assert stored.corroboration_count == 0


@pytest.mark.parametrize("attack", ["none", "signature", "trojan"])
def test_list_enforces_recall_defenses(tmp_path, attack):
    store = TypedArtifactStore(tmp_path)
    store.write(artifact("allowed"))
    store.write(artifact("unauthorized", source="other"))
    denied = MemoryTool().run(
        tmp_path, operation="list", subject="domain_knowledge", query="needle"
    )
    assert denied["status"] == "skipped"
    assert denied["raw"] is None
    if attack != "none":
        with sqlite3.connect(store.db_path) as conn:
            if attack == "signature":
                conn.execute(
                    "UPDATE memory_artifacts SET trust_tier='STATED', signature='bad' WHERE id='allowed'"
                )
            else:
                conn.execute(
                    "UPDATE memory_artifacts SET content=? WHERE id='allowed'",
                    (json.dumps({"fact": "needle\u202e"}),),
                )
    result = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
    )
    assert result["status"] == ("ok" if attack == "none" else "error")
    if attack == "none":
        assert [row["id"] for row in result["raw"]] == ["allowed"]
    else:
        assert result["raw"] is None


def test_expiry_selects_due_rows_before_limit(tmp_path):
    store = TypedArtifactStore(tmp_path)
    store.write(artifact("immortal", age=100 * 86400))
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET trust_tier='STATED' WHERE id='immortal'"
        )
    store.write(artifact("not_due", tier="IMPORTED", age=40 * 86400))
    store.write(artifact("due_first", age=30 * 86400))
    store.write(artifact("due_second", age=20 * 86400))
    owner_scope = legacy_owner_scope(tmp_path)
    assert sweep_expired(tmp_path, batch_size=1, owner_scope=owner_scope) == 1
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute(
            "SELECT id FROM memory_artifacts WHERE expired_at IS NOT NULL"
        ).fetchall() == [("due_first",)]
    assert sweep_expired(tmp_path, batch_size=1, owner_scope=owner_scope) == 1
    assert sweep_expired(tmp_path, batch_size=1, owner_scope=owner_scope) == 0


def test_cli_maintenance_permission_and_list_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    denied = runner.invoke(
        cli, ["memory", "maintain", "--task", "expiry_sweep", "--json"]
    )
    assert json.loads(denied.output)["status"] == "skipped"
    assert not (tmp_path / ".rush").exists()
    allowed = runner.invoke(
        cli,
        [
            "memory",
            "maintain",
            "--task",
            "expiry_sweep",
            "--allow-cache-write",
            "--json",
        ],
    )
    assert allowed.exit_code == 0
    assert json.loads(allowed.output)["status"] == "ok"
    store = TypedArtifactStore(tmp_path)
    store.write(artifact("allowed"))
    listed = runner.invoke(
        cli,
        [
            "memory",
            "list",
            "domain_knowledge",
            "needle",
            "--session",
            "allowed",
            "--json",
        ],
    )
    assert listed.exit_code == 0
    assert json.loads(listed.output)["raw"][0]["id"] == "allowed"


def test_tui_and_cli_maintenance_reach_the_registered_projects_uuid_owned_row_not_path_owner(
    tmp_path, monkeypatch
):
    """M09: TUI's `_default_owner_scope_id("project", ...)` and CLI `memory
    maintain`'s auto-resolved default owner both reach a registered project's
    UUID-owned row -- never the raw-path legacy owner a path-only default
    would touch instead."""
    from rush.tui import ProjectState, _default_owner_scope_id

    data_root = tmp_path / "rush-data"
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    root = tmp_path / "project"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    # TUI half: a resolved project_id wins over the raw root path.
    project = ProjectState(name="p", root=root, project_id=record.project_id)
    assert _default_owner_scope_id("project", project) == record.project_id
    assert _default_owner_scope_id("project", project) != str(root)

    # CLI half: `memory maintain` with no --owner-* flags, run from inside a
    # registered root, auto-resolves that same UUID -- a staleness_sweep
    # touches the UUID-owned row and leaves an identically-drifted
    # legacy-path-owned row alone.
    store = TypedArtifactStore(root)
    target = root / "module.py"
    target.write_text("def hello():\n    return 1\n")
    digest = MerkleInvalidator(root).hash_content(target.read_text())
    store.write(
        artifact(
            "uuid-owned",
            symbol_ref="module.py::hello",
            content_hash=digest,
            owner_scope=OwnerScope("project", record.project_id),
        )
    )
    store.write(
        artifact(
            "path-owned",
            symbol_ref="module.py::hello",
            content_hash=digest,
            owner_scope=legacy_owner_scope(root),
        )
    )
    target.write_text("def hello():\n    return 2\n")  # drift both rows' symbol

    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "memory",
            "maintain",
            "--task",
            "staleness_sweep",
            "--allow-cache-write",
            "--json",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.output)["status"] == "ok"

    with sqlite3.connect(store.db_path) as conn:
        stale_rows = dict(
            conn.execute("SELECT id, stale FROM memory_artifacts").fetchall()
        )
    assert stale_rows["uuid-owned"] == 1
    assert stale_rows["path-owned"] == 0
