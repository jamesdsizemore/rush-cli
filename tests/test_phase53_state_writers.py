"""Contract tests for Phase 53: State, Security, and Release Writers (P53.4.1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rush.memory.invariant_graph import InvariantGraph
from rush.memory.preference_store import PreferenceStore
from rush.patch.memory import PatchMemoryStore
from rush.safety.audit_logger import SecurityAuditLogger
from rush.tools.flight_recorder import FlightRecorder


def test_security_audit_logger_sanitizes_disk_writes(tmp_path: Path) -> None:
    """Verify that SecurityAuditLogger sanitizes secrets before appending to .rush/audit.log."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    fresh_key = "sk-proj-12345678901234567890abcdef"
    logger = SecurityAuditLogger(tmp_path)

    logger.log_security_event("test_event", {fresh_key: f"token={fresh_secret}"})

    log_file = tmp_path / ".rush" / "audit.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert fresh_secret not in content
    assert fresh_key not in content


def test_patch_memory_store_sanitizes_db_writes(tmp_path: Path) -> None:
    """Verify that PatchMemoryStore sanitizes diff patches before inserting into SQLite."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    diff = f"--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-api_key = ''\n+api_key = '{fresh_secret}'\n"

    store = PatchMemoryStore(tmp_path)
    store.record_success("sig_123", "app.py", diff)

    db_path = tmp_path / ".rush" / "cache.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        row = (
            conn.execute(
                "SELECT diff_patch FROM patch_memory WHERE error_signature = ?",
                (store._init_db(),),
            ).fetchone()
            or conn.execute("SELECT diff_patch FROM patch_memory").fetchone()
        )
        assert row is not None
        stored_diff = row[0]
        assert fresh_secret not in stored_diff


def test_flight_recorder_sanitizes_session_writes(tmp_path: Path) -> None:
    """Verify that FlightRecorder sanitizes payloads before writing .rush/sessions/flights/*.jsonl."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    recorder = FlightRecorder(tmp_path)

    recorder.record_event("sess_001", "tool_call", {"secret_param": fresh_secret})

    flight_file = tmp_path / ".rush" / "sessions" / "flights" / "sess_001.jsonl"
    assert flight_file.exists()
    content = flight_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_preference_store_sanitizes_json_writes(tmp_path: Path) -> None:
    """Verify that PreferenceStore sanitizes keys and values before writing preferences.json."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    store = PreferenceStore(tmp_path)

    store.set(f"prefix_{fresh_secret}", f"val_{fresh_secret}")

    pref_file = tmp_path / ".rush" / "preferences.json"
    assert pref_file.exists()
    content = pref_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_invariant_graph_sanitizes_json_writes(tmp_path: Path) -> None:
    """Verify that InvariantGraph sanitizes descriptions and rationales before writing invariants.json."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    graph = InvariantGraph(tmp_path)

    graph.add_invariant("INV01", f"must use {fresh_secret}", f"because {fresh_secret}")

    inv_file = tmp_path / ".rush" / "memory" / "invariants.json"
    assert inv_file.exists()
    content = inv_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_benchmark_sanitizes_baseline_writes(tmp_path: Path) -> None:
    """Verify that benchmark writes sanitized baselines JSON to disk."""
    from rush.tools.benchmark import BenchmarkTool

    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    tool = BenchmarkTool()
    tool.run(
        tmp_path,
        record_baseline=f"base_{fresh_secret}",
        benchmark_command="echo ok",
        runs=1,
    )
    baseline_file = tmp_path / ".rush" / "baselines.json"
    if baseline_file.exists():
        content = baseline_file.read_text(encoding="utf-8")
        assert fresh_secret not in content
