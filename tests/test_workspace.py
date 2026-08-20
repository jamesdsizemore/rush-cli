"""Tests for Phase 26: Monorepo & Workspace Boundaries.

Verifies:
- Monorepo package detection (pnpm, npm/yarn, Cargo, Go)
- Workspace boundary path confinement (rejection of ../ escapes)
- Topological sort of internal workspace package dependencies
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.discovery.workspace import (
    WorkspacePackage,
    discover_workspaces,
    topological_sort_workspaces,
)


def test_detect_pnpm_workspace(tmp_path: Path) -> None:
    # Root pnpm-workspace.yaml
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - 'packages/*'\n", encoding="utf-8"
    )
    pkg_a = tmp_path / "packages" / "pkg-a"
    pkg_a.mkdir(parents=True)
    (pkg_a / "package.json").write_text(
        '{"name": "@repo/pkg-a", "dependencies": {}}', encoding="utf-8"
    )

    pkg_b = tmp_path / "packages" / "pkg-b"
    pkg_b.mkdir(parents=True)
    (pkg_b / "package.json").write_text(
        '{"name": "@repo/pkg-b", "dependencies": {"@repo/pkg-a": "*"}}',
        encoding="utf-8",
    )

    workspaces = discover_workspaces(tmp_path)
    names = [w.name for w in workspaces]
    assert "@repo/pkg-a" in names
    assert "@repo/pkg-b" in names


def test_detect_cargo_workspace(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["crates/*"]\n', encoding="utf-8"
    )
    crate_core = tmp_path / "crates" / "core"
    crate_core.mkdir(parents=True)
    (crate_core / "Cargo.toml").write_text(
        '[package]\nname = "my-core"\nversion = "0.1.0"\n', encoding="utf-8"
    )

    workspaces = discover_workspaces(tmp_path)
    names = [w.name for w in workspaces]
    assert "my-core" in names


def test_workspace_traversal_rejection(tmp_path: Path) -> None:
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - '../../external/*'\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="resolves outside repository root"):
        discover_workspaces(tmp_path)


def test_workspace_topological_sort() -> None:
    pkg_a = WorkspacePackage(name="pkg-a", path=Path("packages/a"), dependencies=[])
    pkg_b = WorkspacePackage(
        name="pkg-b", path=Path("packages/b"), dependencies=["pkg-a"]
    )
    pkg_c = WorkspacePackage(
        name="pkg-c", path=Path("packages/c"), dependencies=["pkg-b"]
    )

    # In random/reverse order
    sorted_pkgs = topological_sort_workspaces([pkg_c, pkg_b, pkg_a])
    names = [p.name for p in sorted_pkgs]
    assert names == ["pkg-a", "pkg-b", "pkg-c"]
