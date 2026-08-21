"""Affected workspace package calculator based on Git diffs."""

from __future__ import annotations

from pathlib import Path
from rush.workspaces.models import WorkspaceGraph, WorkspacePackage


class AffectedCalculator:
    """Computes minimal set of affected packages and downstream dependents."""

    def __init__(self, repo_root: Path, graph: WorkspaceGraph) -> None:
        self.repo_root = repo_root.resolve()
        self.graph = graph

    def get_affected_packages(self, changed_files: list[Path]) -> list[str]:
        direct_affected: set[str] = set()

        for f in changed_files:
            rel = f.relative_to(self.repo_root).as_posix() if f.is_absolute() and f.is_relative_to(self.repo_root) else f.as_posix()
            for name, pkg in self.graph.packages.items():
                if rel.startswith(pkg.relative_path):
                    direct_affected.add(name)

        # Transitive expansion
        all_affected = set(direct_affected)
        changed = True
        while changed:
            changed = False
            for name, pkg in self.graph.packages.items():
                if name not in all_affected:
                    if any(dep in all_affected for dep in pkg.dependencies):
                        all_affected.add(name)
                        changed = True

        return [name for name in self.graph.topological_order if name in all_affected]
