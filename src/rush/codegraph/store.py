"""SQLite-backed Code Property Graph (CPG) index store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphNode:
    id: str
    file_path: str
    symbol_name: str
    kind: str
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: str


class CodeGraphStore:
    """Manages SQLite storage for symbols, classes, functions, and call graph edges."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, edge_type)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON nodes(symbol_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file ON nodes(file_path)")

    def insert_node(self, node: GraphNode) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, file_path, symbol_name, kind, start_line, end_line, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node.id,
                    node.file_path,
                    node.symbol_name,
                    node.kind,
                    node.start_line,
                    node.end_line,
                    node.content,
                ),
            )

    def insert_edge(self, edge: GraphEdge) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO edges (source_id, target_id, edge_type)
                VALUES (?, ?, ?)
                """,
                (edge.source_id, edge.target_id, edge.edge_type),
            )

    def find_nodes_by_symbol(self, symbol_name: str) -> list[GraphNode]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT id, file_path, symbol_name, kind, start_line, end_line, content FROM nodes WHERE symbol_name = ?",
                (symbol_name,),
            )
            rows = cur.fetchall()
            return [GraphNode(*row) for row in rows]
