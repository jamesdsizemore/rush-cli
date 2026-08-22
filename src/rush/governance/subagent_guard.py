"""Acyclic subagent invocation DAG validator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentInvocation:
    parent_agent: str
    child_agent: str


class SubagentHierarchyValidator:
    """Ensures subagent invocation trees form a strict DAG with no cycles and bounded depth."""

    def __init__(self, max_depth: int = 3) -> None:
        self.max_depth = max_depth

    def validate_invocations(
        self, invocations: list[SubagentInvocation]
    ) -> tuple[bool, str | None]:
        adj: dict[str, list[str]] = {}
        for inv in invocations:
            adj.setdefault(inv.parent_agent, []).append(inv.child_agent)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, depth: int) -> tuple[bool, str | None]:
            if depth > self.max_depth:
                return (
                    False,
                    f"Subagent call depth exceeded maximum allowed ({depth} > {self.max_depth}).",
                )
            visited.add(node)
            rec_stack.add(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    ok, err = dfs(neighbor, depth + 1)
                    if not ok:
                        return False, err
                elif neighbor in rec_stack:
                    return (
                        False,
                        f"Cyclic subagent invocation detected: '{node}' -> '{neighbor}'.",
                    )

            rec_stack.remove(node)
            return True, None

        for root in list(adj.keys()):
            if root not in visited:
                ok, err = dfs(root, 1)
                if not ok:
                    return False, err

        return True, None
