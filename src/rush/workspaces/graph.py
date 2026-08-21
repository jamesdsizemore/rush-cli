"""Dependency DAG builder and topological sort."""

from __future__ import annotations

from collections import defaultdict, deque
from rush.workspaces.models import WorkspaceGraph, WorkspacePackage


class DependencyGraphBuilder:
    """Builds DAG and computes topological execution order."""

    @staticmethod
    def build_graph(packages: list[WorkspacePackage]) -> WorkspaceGraph:
        pkg_map = {p.name: p for p in packages}
        in_degree: dict[str, int] = {p.name: 0 for p in packages}
        adj_list: dict[str, list[str]] = defaultdict(list)

        for p in packages:
            for dep in p.dependencies:
                if dep in pkg_map:
                    adj_list[dep].append(p.name)
                    in_degree[p.name] += 1

        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        has_cycles = len(order) != len(packages)
        return WorkspaceGraph(
            packages=pkg_map,
            topological_order=tuple(order),
            has_cycles=has_cycles,
        )
