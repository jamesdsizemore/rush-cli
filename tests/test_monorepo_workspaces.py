"""Tests for Phase 26: Monorepo & Workspace Boundaries."""

from __future__ import annotations

from pathlib import Path

from rush.workspaces.affected import AffectedCalculator
from rush.workspaces.boundary import WorkspaceBoundaryGuard
from rush.workspaces.discovery import WorkspaceDiscovery
from rush.workspaces.graph import DependencyGraphBuilder
from rush.workspaces.matrix import WorkspaceMatrixGenerator
from rush.workspaces.models import WorkspacePackage


def test_workspace_discovery_python(tmp_path: Path) -> None:
    pkg1 = tmp_path / "packages" / "core"
    pkg1.mkdir(parents=True)
    (pkg1 / "pyproject.toml").write_text('[project]\nname = "core"\n', encoding="utf-8")

    pkg2 = tmp_path / "packages" / "cli"
    pkg2.mkdir(parents=True)
    (pkg2 / "pyproject.toml").write_text('[project]\nname = "cli"\n', encoding="utf-8")

    discovery = WorkspaceDiscovery(tmp_path)
    packages = discovery.discover_all()
    names = {p.name for p in packages}
    assert "core" in names
    assert "cli" in names


def test_dependency_graph_topological_sort() -> None:
    p1 = WorkspacePackage(
        name="core",
        kind="python",
        root_path=Path("/core"),
        relative_path="packages/core",
    )
    p2 = WorkspacePackage(
        name="cli",
        kind="python",
        root_path=Path("/cli"),
        relative_path="packages/cli",
        dependencies=("core",),
    )

    graph = DependencyGraphBuilder.build_graph([p2, p1])
    assert graph.has_cycles is False
    assert graph.topological_order == ("core", "cli")


def test_affected_calculator_transitive(tmp_path: Path) -> None:
    p1 = WorkspacePackage(
        name="core",
        kind="python",
        root_path=tmp_path / "packages/core",
        relative_path="packages/core",
    )
    p2 = WorkspacePackage(
        name="cli",
        kind="python",
        root_path=tmp_path / "packages/cli",
        relative_path="packages/cli",
        dependencies=("core",),
    )
    p3 = WorkspacePackage(
        name="docs",
        kind="python",
        root_path=tmp_path / "packages/docs",
        relative_path="packages/docs",
    )

    graph = DependencyGraphBuilder.build_graph([p1, p2, p3])
    calc = AffectedCalculator(tmp_path, graph)

    # Core was changed -> both core and cli are affected
    changed = [tmp_path / "packages/core/src/util.py"]
    affected = calc.get_affected_packages(changed)
    assert "core" in affected
    assert "cli" in affected
    assert "docs" not in affected


def test_boundary_guard_illegal_relative_import(tmp_path: Path) -> None:
    pkg = tmp_path / "packages" / "cli"
    pkg.mkdir(parents=True)
    bad_file = pkg / "main.py"
    bad_file.write_text(
        'from "../../core/secret" import internal_val\n', encoding="utf-8"
    )

    p = WorkspacePackage(
        name="cli", kind="python", root_path=pkg, relative_path="packages/cli"
    )
    guard = WorkspaceBoundaryGuard(tmp_path)
    res = guard.check_package_boundaries([p])
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "workspace-boundary-violation"


def test_workspace_matrix_generator() -> None:
    p1 = WorkspacePackage(
        name="core",
        kind="python",
        root_path=Path("/core"),
        relative_path="packages/core",
    )
    graph = DependencyGraphBuilder.build_graph([p1])
    matrix_str = WorkspaceMatrixGenerator.generate_github_matrix(["core"], graph)
    assert '"package": "core"' in matrix_str
    assert '"kind": "python"' in matrix_str
