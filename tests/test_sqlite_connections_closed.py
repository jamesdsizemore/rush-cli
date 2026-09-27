"""Every writable SQLite connection closes when its `with` block ends.

A bare `with sqlite3.connect(...) as conn:` commits or rolls back but leaves the
connection open until garbage collection (CPython 3.12: its statement cache is
a reference cycle). Each case records every connection `sqlite3.connect` hands
out during one representative operation, holding a strong reference so garbage
collection can never close it on the code's behalf, then asserts each one is
closed.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from rush.cache import ResultCache
from rush.codegraph.store import CodeGraphStore, GraphEdge, GraphNode
from rush.codegraph.traverser import CallGraphTraverser
from rush.dashboard.state import MutationLedger
from rush.delivery.compact import purge_compact_results
from rush.memory.failure_ledger import FailureLedger
from rush.patch.memory import PatchMemoryStore
from rush.runtime.sqlite_util import ClosingConnection
from rush.token_economy.ccr_store import CCRStore
from rush.token_economy.telemetry import TelemetryStore


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


def _open_after(
    monkeypatch: pytest.MonkeyPatch, operation: Callable[[], Any]
) -> list[str]:
    """Run `operation`; return the database of every connection it opened and
    left open. Fails if it opened none (the case would prove nothing)."""
    real_connect = sqlite3.connect
    opened: list[tuple[str, sqlite3.Connection]] = []

    def _recording_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        conn = real_connect(database, *args, **kwargs)
        opened.append((str(database), conn))
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", _recording_connect)
        operation()
    assert opened, "operation opened no SQLite connection"
    still_open = []
    for database, conn in opened:
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            continue
        still_open.append(database)
        conn.close()
    return still_open


def _ledger_ops(tmp_path: Path) -> None:
    ledger = MutationLedger(db_path=tmp_path / "ledger.db")
    ledger.reserve("project", "request", "body-hash")
    ledger.list_admissions()


def _cache_ops(tmp_path: Path) -> None:
    cache = ResultCache(db_path=tmp_path / "cache.db")
    cache.stats()
    cache.get("a" * 64)
    cache.clear()


def _codegraph_ops(tmp_path: Path) -> None:
    store = CodeGraphStore(tmp_path / "graph.db")
    store.insert_node(GraphNode("a", "a.py", "caller", "function", 1, 2, "a()"))
    store.insert_node(GraphNode("b", "b.py", "callee", "function", 1, 2, "b()"))
    store.insert_edge(GraphEdge("a", "b", "calls"))
    store.find_nodes_by_symbol("caller")
    traverser = CallGraphTraverser(store)
    traverser.trace_callees("caller")
    traverser.trace_callers("callee")


def _patch_memory_ops(tmp_path: Path) -> None:
    store = PatchMemoryStore(tmp_path)
    store.record_success("sig", "a.py", "--- a\n+++ b\n")
    store.lookup_patch("sig")
    store.list_records()
    store.clear_memory()


def _failure_ledger_ops(tmp_path: Path) -> None:
    ledger = FailureLedger(tmp_path)
    fingerprint = ledger.record_failure("patch", "boom")
    ledger.is_known_failure("patch")
    ledger.get_receipt(fingerprint)


def _telemetry_ops(tmp_path: Path) -> None:
    store = TelemetryStore(tmp_path)
    store.record_memory_event("retrieval", 5, request_id="req", event_id="evt")
    store.get_memory_event_total()
    store.record_savings("lint", 100, 10)
    store.get_summary()


def _ccr_ops(tmp_path: Path) -> None:
    store = CCRStore(tmp_path)
    tag = store.store_chunk("content")
    chunk_hash = tag.removeprefix("<!-- ccr:chunk:").removesuffix(" -->")
    store.retrieve_chunk(chunk_hash)
    store.retrieve_chunk(chunk_hash, touch=False)


def _compact_purge_ops(tmp_path: Path) -> None:
    CCRStore(tmp_path).store_chunk("content")
    purge_compact_results(tmp_path)


@pytest.mark.parametrize(
    "operation",
    [
        _ledger_ops,
        _cache_ops,
        _codegraph_ops,
        _patch_memory_ops,
        _failure_ledger_ops,
        _telemetry_ops,
        _ccr_ops,
        _compact_purge_ops,
    ],
)
def test_every_connection_is_closed_after_the_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: Callable[[Path], None],
) -> None:
    assert _open_after(monkeypatch, lambda: operation(tmp_path)) == []


def test_closing_connection_commits_then_closes(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    with sqlite3.connect(db, factory=ClosingConnection) as conn:
        conn.execute("CREATE TABLE t (v INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with sqlite3.connect(db, factory=ClosingConnection) as check:
        assert check.execute("SELECT v FROM t").fetchall() == [(1,)]


def test_closing_connection_rolls_back_then_closes_on_error(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    with sqlite3.connect(db, factory=ClosingConnection) as conn:
        conn.execute("CREATE TABLE t (v INTEGER)")
    with (
        pytest.raises(RuntimeError, match="boom"),
        sqlite3.connect(db, factory=ClosingConnection) as conn,
    ):
        conn.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("boom")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
    with sqlite3.connect(db, factory=ClosingConnection) as check:
        assert check.execute("SELECT v FROM t").fetchall() == []
