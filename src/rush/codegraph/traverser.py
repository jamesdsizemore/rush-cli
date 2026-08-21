"""Cycle-safe forward and reverse call graph traversal engine."""

from __future__ import annotations

from dataclasses import dataclass
from rush.codegraph.store import CodeGraphStore, GraphNode


@dataclass(frozen=True)
class CallPathStep:
    caller: GraphNode
    callee: GraphNode
    depth: int


class CallGraphTraverser:
    """Traverses call graph edges with strict cycle detection and bounded recursion."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def trace_callees(self, root_symbol: str, max_depth: int = 3) -> list[CallPathStep]:
        root_nodes = self.store.find_nodes_by_symbol(root_symbol)
        if not root_nodes:
            return []

        visited_ids = set()
        paths: list[CallPathStep] = []

        def dfs(current_node: GraphNode, current_depth: int):
            if current_depth >= max_depth or current_node.id in visited_ids:
                return
            visited_ids.add(current_node.id)

            with self.store._get_conn() as conn:
                cur = conn.execute(
                    """
                    SELECT n.id, n.file_path, n.symbol_name, n.kind, n.start_line, n.end_line, n.content
                    FROM edges e
                    JOIN nodes n ON e.target_id = n.id
                    WHERE e.source_id = ? AND e.edge_type = 'CALLS'
                    """,
                    (current_node.id,),
                )
                for row in cur.fetchall():
                    callee_node = GraphNode(*row)
                    paths.append(CallPathStep(caller=current_node, callee=callee_node, depth=current_depth + 1))
                    dfs(callee_node, current_depth + 1)

        for rn in root_nodes:
            dfs(rn, 0)

        return paths

    def trace_callers(self, target_symbol: str, max_depth: int = 3) -> list[CallPathStep]:
        target_nodes = self.store.find_nodes_by_symbol(target_symbol)
        if not target_nodes:
            return []

        visited_ids = set()
        paths: list[CallPathStep] = []

        def dfs(current_node: GraphNode, current_depth: int):
            if current_depth >= max_depth or current_node.id in visited_ids:
                return
            visited_ids.add(current_node.id)

            with self.store._get_conn() as conn:
                cur = conn.execute(
                    """
                    SELECT n.id, n.file_path, n.symbol_name, n.kind, n.start_line, n.end_line, n.content
                    FROM edges e
                    JOIN nodes n ON e.source_id = n.id
                    WHERE e.target_id = ? AND e.edge_type = 'CALLS'
                    """,
                    (current_node.id,),
                )
                for row in cur.fetchall():
                    caller_node = GraphNode(*row)
                    paths.append(CallPathStep(caller=caller_node, callee=current_node, depth=current_depth + 1))
                    dfs(caller_node, current_depth + 1)

        for tn in target_nodes:
            dfs(tn, 0)

        return paths
