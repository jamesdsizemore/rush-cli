"""Monorepo workspace discovery, path boundary validation, and topological sorting.

Architecture §8, Phase 26.
Enforces Control 2: Path Confinement on workspace definitions.
"""

from __future__ import annotations

from pathlib import Path

from rush.discovery.workspace_graph import (
    WorkspacePackage,
    discover_workspace_packages,
    topological_sort_workspace_packages,
)


def discover_workspaces(root: Path) -> list[WorkspacePackage]:
    """Discover all packages across JS/TS (pnpm, npm, yarn, turborepo), Rust (Cargo), and Go monorepos.

    Raises ValueError if any workspace definition escapes the repository boundary.
    """
    return discover_workspace_packages(root)


def topological_sort_workspaces(
    packages: list[WorkspacePackage],
) -> list[WorkspacePackage]:
    """Sort workspace packages in dependency-first topological order."""
    return topological_sort_workspace_packages(packages)


__all__ = [
    "WorkspacePackage",
    "discover_workspace_packages",
    "discover_workspaces",
    "topological_sort_workspace_packages",
    "topological_sort_workspaces",
]
