"""Python AST Symbol and Call Graph Indexer."""

from __future__ import annotations

import ast
from pathlib import Path
from rush.codegraph.store import CodeGraphStore, GraphEdge, GraphNode


class PythonCodeGraphBuilder:
    """Builds nodes and edges from Python source files."""

    @staticmethod
    def index_python_file(file_path: Path, source_code: str, store: CodeGraphStore) -> None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return

        lines = source_code.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 5)
                content = "\n".join(lines[start - 1 : end])
                node_id = f"{file_path}:{node.name}:{start}"
                store.insert_node(
                    GraphNode(
                        id=node_id,
                        file_path=str(file_path),
                        symbol_name=node.name,
                        kind="function",
                        start_line=start,
                        end_line=end,
                        content=content,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 10)
                content = "\n".join(lines[start - 1 : end])
                node_id = f"{file_path}:{node.name}:{start}"
                store.insert_node(
                    GraphNode(
                        id=node_id,
                        file_path=str(file_path),
                        symbol_name=node.name,
                        kind="class",
                        start_line=start,
                        end_line=end,
                        content=content,
                    )
                )
