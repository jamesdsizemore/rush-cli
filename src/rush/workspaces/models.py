"""Data models for monorepo workspace packages and dependency graphs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePackage:
    name: str
    kind: str  # "python", "rust", "node", "go"
    root_path: Path
    relative_path: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkspaceGraph:
    packages: dict[str, WorkspacePackage]
    topological_order: tuple[str, ...]
    has_cycles: bool = False
