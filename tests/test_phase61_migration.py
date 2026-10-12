"""Contract tests T-61.15 through T-61.22, T-61.37 for migrating pre-P61.3 satellite stores
into the unified `TypedArtifactStore` (Phase 61 §6.3 Invariant 5, §9 P61.3.1-2)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from rush.hook.tamper_detector import HookTamperDetector
from rush.memory import authorization
from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.failure_ledger import FailureLedger
from rush.memory.invariant_graph import InvariantGraph
from rush.memory.migration import (
    migrate_checkpoint_journal,
    migrate_failure_ledger,
    migrate_flight_recorder,
    migrate_hook_signatures,
    migrate_invariant_graph,
    migrate_patch_memory,
    migrate_preference_store,
    read_origin,
    read_origin_kind,
    read_origin_kind_by_symbol,
)
from rush.memory.preference_store import PreferenceStore
from rush.memory.store import MemoryArtifact, TypedArtifactStore, legacy_owner_scope
from rush.patch.memory import PatchMemoryStore
from rush.session_memory import SessionMemoryManager
from rush.setup.provision import default_data_root
from rush.tools.flight_recorder import FlightRecorder
from rush.workflows.projects import register_project


def _rows(store: TypedArtifactStore, **where: str) -> list[sqlite3.Row]:
    clauses = " AND ".join(f"{k} = ?" for k in where)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT * FROM memory_artifacts WHERE {clauses}", tuple(where.values())
        ).fetchall()


def test_preference_store_rows_migrate_with_kind_preference(tmp_path: Path):
    """T-61.15: seeds a CASMapTransaction-backed preference file, runs migration, asserts
    equivalent rows exist in memory_artifacts with subject='preference'."""
    old_file = tmp_path / ".rush" / "preferences.json"
    PreferenceStore(tmp_path).set("editor.theme", "dark")
    assert old_file.exists()

    migrated_count = migrate_preference_store(tmp_path)
    assert migrated_count == 1

    store = TypedArtifactStore(tmp_path)
    rows = _rows(store, origin_kind="preference", origin_id="editor.theme")
    assert len(rows) == 1
    assert rows[0]["subject"] == "preference"
    content = json.loads(rows[0]["content"])
    assert content == {"key": "editor.theme", "value": "dark"}

    assert not old_file.exists()
    assert old_file.with_name("preferences.json.migrated").exists()


def test_invariant_graph_rows_migrate_with_kind_architectural_decision(tmp_path: Path):
    """T-61.16: same shape for invariant_graph.py -> subject='architectural_decision'."""
    old_file = tmp_path / ".rush" / "memory" / "invariants.json"
    InvariantGraph(tmp_path).add_invariant(
        "INV-001",
        "FastMCP stdio output must not have logs",
        "Prevents transport corruption",
    )
    assert old_file.exists()

    migrated_count = migrate_invariant_graph(tmp_path)
    assert migrated_count == 1

    store = TypedArtifactStore(tmp_path)
    rows = _rows(store, origin_kind="invariant_graph", origin_id="INV-001")
    assert len(rows) == 1
    assert rows[0]["subject"] == "architectural_decision"
    content = json.loads(rows[0]["content"])
    assert content["description"] == "FastMCP stdio output must not have logs"
    assert content["status"] == "active"

    assert not old_file.exists()
    assert old_file.with_name("invariants.json.migrated").exists()


def test_checkpoint_journal_rows_migrate_as_handoff_family(tmp_path: Path):
    """T-61.17: seeds checkpoints (including one corrupt entry per Phase 58's retention
    behavior), asserts migrated rows have family='handoff' and the corrupt entry's SHA-256
    evidence survives the migration, not silently dropped."""
    journal = CheckpointJournal(tmp_path)
    journal.save_checkpoint("good_ckpt", {"stage": "p61"}, ["src/app.py"])

    sessions_dir = tmp_path / ".rush" / "sessions"
    corrupt_bytes = b'{"schema_version": "1.0.0", "truncated": [1, 2,\x80\xff'
    corrupt_path = sessions_dir / "bad_ckpt.json"
    corrupt_path.write_bytes(corrupt_bytes)

    migrated_count = migrate_checkpoint_journal(tmp_path)
    assert migrated_count == 2

    store = TypedArtifactStore(tmp_path)
    good_rows = _rows(store, origin_kind="checkpoint", origin_id="good_ckpt")
    assert len(good_rows) == 1
    assert good_rows[0]["family"] == "handoff"
    assert good_rows[0]["subject"] == "active_context"

    corrupt_rows = _rows(store, origin_kind="checkpoint", origin_id="bad_ckpt")
    assert len(corrupt_rows) == 1
    assert corrupt_rows[0]["family"] == "handoff"
    corrupt_content = json.loads(corrupt_rows[0]["content"])
    assert corrupt_content["status"] == "corrupt"
    assert (
        corrupt_content["raw_bytes_digest"] == hashlib.sha256(corrupt_bytes).hexdigest()
    )

    assert not (sessions_dir / "good_ckpt.json").exists()
    assert (sessions_dir / "good_ckpt.json.migrated").exists()
    assert not corrupt_path.exists()
    assert corrupt_path.with_name("bad_ckpt.json.migrated").exists()


def test_failure_ledger_rows_migrate_with_kind_failure(tmp_path: Path):
    """T-61.18: seeds failure_ledgers rows, asserts migrated subject='failure' rows preserve
    fingerprint as symbol_ref or an equivalent traceable field, not lost."""
    ledger = FailureLedger(tmp_path)
    fingerprint = ledger.record_failure(
        "--- a/src/rush/cli.py\n+++ b/src/rush/cli.py\n- old\n+ broken",
        "SyntaxError on line 42",
    )

    migrated_count = migrate_failure_ledger(tmp_path)
    assert migrated_count == 1

    store = TypedArtifactStore(tmp_path)
    rows = _rows(store, origin_kind="failure_ledger", origin_id=fingerprint)
    assert len(rows) == 1
    assert rows[0]["subject"] == "failure"
    assert rows[0]["symbol_ref"] == fingerprint

    db_path = tmp_path / ".rush" / "memory" / "failures.db"
    assert db_path.exists()


def test_patch_memory_rows_migrate_and_pair_with_failure_records(tmp_path: Path):
    """T-61.19: seeds PatchMemoryStore rows keyed by error_signature matching a migrated
    failure record's fingerprint; asserts the migrated schema links them (queryable join)."""
    patch_text = "--- a/src/rush/cli.py\n+++ b/src/rush/cli.py\n- old\n+ broken"
    ledger = FailureLedger(tmp_path)
    fingerprint = ledger.record_failure(patch_text, "SyntaxError on line 42")

    patch_store = PatchMemoryStore(tmp_path)
    patch_store.record_success(patch_text, "src/rush/cli.py", "--- fix ---")

    migrate_failure_ledger(tmp_path)
    migrate_patch_memory(tmp_path)

    store = TypedArtifactStore(tmp_path)
    joined = _rows(store, symbol_ref=fingerprint)
    assert len(joined) == 2
    origin_kinds = {row["origin_kind"] for row in joined}
    assert origin_kinds == {"failure_ledger", "patch_memory"}

    cache_db = tmp_path / ".rush" / "cache.db"
    assert cache_db.exists()


def test_flight_recorder_jsonl_migrates_as_episodic_subject(tmp_path: Path):
    """T-61.20: seeds a flights JSONL file, runs migration, asserts equivalent rows exist
    with subject='episodic', family='experience'."""
    recorder = FlightRecorder(tmp_path)
    recorder.record_event("session-abc", "TOOL_CALL", {"tool": "rush_context_pack"})
    recorder.record_event("session-abc", "TOOL_RESULT", {"status": "success"})

    flight_file = tmp_path / ".rush" / "sessions" / "flights" / "session-abc.jsonl"
    assert flight_file.exists()

    migrated_count = migrate_flight_recorder(tmp_path)
    assert migrated_count == 2

    store = TypedArtifactStore(tmp_path)
    rows = _rows(store, origin_kind="flight_event", symbol_ref="session-abc")
    assert len(rows) == 2
    for row in rows:
        assert row["subject"] == "episodic"
        assert row["family"] == "experience"

    assert not flight_file.exists()
    assert flight_file.with_name("session-abc.jsonl.migrated").exists()


def test_hook_signatures_migrate_and_satellite_files_no_longer_canonical(
    tmp_path: Path,
):
    """T-61.21: after migration, asserts the unified store, not the old
    .rush/hook_signatures.json, is the source HookTamperDetector.verify_signatures() reads from."""
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    detector = HookTamperDetector(tmp_path)
    detector.record_signatures()
    sig_file = tmp_path / ".rush" / "hook_signatures.json"
    assert sig_file.exists()

    migrated_count = migrate_hook_signatures(tmp_path)
    assert migrated_count == 1
    assert not sig_file.exists()
    assert sig_file.with_name("hook_signatures.json.migrated").exists()

    ok, errors = detector.verify_signatures()
    assert ok is True, errors

    (hooks_dir / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    tampered_ok, tampered_errors = detector.verify_signatures()
    assert tampered_ok is False
    assert len(tampered_errors) == 1


def test_migration_is_idempotent(tmp_path: Path):
    """T-61.22: runs migration twice; asserts no duplicate rows on the second run."""
    PreferenceStore(tmp_path).set("editor.theme", "dark")
    PreferenceStore(tmp_path).set("editor.font", "mono")
    ledger = FailureLedger(tmp_path)
    ledger.record_failure("patch-a", "err-a")

    first_pref = migrate_preference_store(tmp_path)
    first_failure = migrate_failure_ledger(tmp_path)
    assert first_pref == 2
    assert first_failure == 1

    second_pref = migrate_preference_store(tmp_path)
    second_failure = migrate_failure_ledger(tmp_path)
    assert second_pref == 0
    assert second_failure == 0

    store = TypedArtifactStore(tmp_path)
    with sqlite3.connect(str(store.db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM memory_artifacts").fetchone()[0]
    assert total == 3


def test_migration_rerun_after_partial_completion_does_not_duplicate_or_drop_rows(
    tmp_path: Path,
):
    """T-61.37: runs migration once, deletes one already-migrated row directly (simulating an
    interrupted/partial run), reruns the same migration function, and asserts (a) the deleted
    row is re-inserted exactly once, (b) every already-committed row is not duplicated.

    Uses failure_ledger as the subject: its source (.rush/memory/failures.db) is never renamed
    by migration, so a rerun always has the same source data available to re-read from.
    """
    ledger = FailureLedger(tmp_path)
    fp_a = ledger.record_failure("patch-a", "err-a")
    fp_b = ledger.record_failure("patch-b", "err-b")

    first_run = migrate_failure_ledger(tmp_path)
    assert first_run == 2

    store = TypedArtifactStore(tmp_path)
    with sqlite3.connect(str(store.db_path)) as conn:
        conn.execute(
            "DELETE FROM memory_artifacts WHERE origin_kind = 'failure_ledger' AND origin_id = ?",
            (fp_a,),
        )
        conn.commit()

    rerun = migrate_failure_ledger(tmp_path)
    assert rerun == 1

    rows_a = _rows(store, origin_kind="failure_ledger", origin_id=fp_a)
    rows_b = _rows(store, origin_kind="failure_ledger", origin_id=fp_b)
    assert len(rows_a) == 1
    assert len(rows_b) == 1


def _session_row(store: TypedArtifactStore, name: str, summary: str) -> None:
    store.write(
        MemoryArtifact(
            id=name,
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={
                "timestamp": "2026-01-01T00:00:00",
                "tool_name": "tool",
                "finding_count": 1,
                "fixes_applied": 0,
                "summary": summary,
            },
            source="migration:session_memory",
            created_at=time.time(),
            symbol_ref="sym",
            origin_kind="session_memory",
            origin_id=f"{name}-id",
        )
    )


def test_origin_readers_omit_tampered_derived_payload_keep_unbound_rows(
    tmp_path: Path,
) -> None:
    """security-4: a DERIVED row whose content no longer matches its payload_hash is
    never delivered by a compatibility reader; an unbound row (payload_hash NULL, as
    an old schema leaves it) stays readable."""
    data_root = default_data_root()
    root = tmp_path / "project"
    root.mkdir()
    register_project(root, data_root=data_root)
    root = root.resolve()
    policy = authorization.load_policy_readonly(data_root=data_root)
    authorization.grant_memory_scope(
        project_root=root,
        owner_scope=legacy_owner_scope(root),
        approved_sources=["migration:session_memory"],
        allowed_operations=["ask"],
        expected_policy_revision=int(policy["policy_revision"] or 0),
        consent=True,
        data_root=data_root,
    )
    store = TypedArtifactStore(root)
    _session_row(store, "clean", "CLEAN-OK")
    _session_row(store, "tampered", "ORIGINAL")
    _session_row(store, "legacy", "LEGACY")
    with contextlib.closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = "
            "json_set(content, '$.summary', 'INJECTED-PAYLOAD') WHERE id = 'tampered'"
        )
        conn.execute(
            "UPDATE memory_artifacts SET payload_hash = NULL, payload_hash_origin = NULL,"
            " content = json_set(content, '$.summary', 'LEGACY-OK') WHERE id = 'legacy'"
        )
        conn.commit()

    assert read_origin(root, "session_memory", "tampered-id") is None
    legacy = read_origin(root, "session_memory", "legacy-id")
    assert legacy is not None and legacy["summary"] == "LEGACY-OK"
    kind = read_origin_kind(root, "session_memory")
    assert sorted(r["summary"] for r in kind) == ["CLEAN-OK", "LEGACY-OK"]
    by_symbol = read_origin_kind_by_symbol(root, "session_memory", "sym")
    assert sorted(r["summary"] for r in by_symbol) == ["CLEAN-OK", "LEGACY-OK"]
    manager = SessionMemoryManager(root / ".rush" / "session_memory.json")
    framed = manager.format_for_mcp()
    assert "INJECTED-PAYLOAD" not in framed
    assert "CLEAN-OK" in framed and "LEGACY-OK" in framed
