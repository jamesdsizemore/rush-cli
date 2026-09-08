"""Behavioral regressions for Phase 61/62 core review findings."""

import dataclasses
import json
import sqlite3
import time

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.codegraph.context_packer import ContextPacker
from rush.continuity.context import pack_context
from rush.memory.expiry import sweep_expired
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    TypedArtifactStore,
    compute_content_signature,
)
from rush.permissions import ExecutionPermissions
from rush.token_economy.memory_cache_gate import check_memory_before_pack
from rush.tools.memory import MemoryTool

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
        requested, operation="maintain", task=task, permissions=GRANTED
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
    assert sweep_expired(tmp_path, batch_size=1) == 1
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute(
            "SELECT id FROM memory_artifacts WHERE expired_at IS NOT NULL"
        ).fetchall() == [("due_first",)]
    assert sweep_expired(tmp_path, batch_size=1) == 1
    assert sweep_expired(tmp_path, batch_size=1) == 0


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
