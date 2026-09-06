"""Monorepo workspace discovery, path boundary validation, and topological sorting."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from rush.logging import get_logger, log_subsystem

logger = get_logger("discovery.workspace_graph")


@dataclass(frozen=True)
class WorkspacePackage:
    """Represents a discovered package within a monorepo."""

    name: str
    path: Path
    dependencies: list[str] = field(default_factory=list)


def _validate_confinement(pattern: str, root_resolved: Path, label: str) -> None:
    """Enforce that workspace pattern does not escape the repository boundary."""
    if ".." in pattern:
        log_subsystem(
            "workspace",
            "SECURITY_ERROR",
            f"{label} '{pattern}' resolves outside repository root '{root_resolved}'",
        )
        raise ValueError(
            f"Security Error: {label} '{pattern}' resolves outside repository root"
        )


def _extract_pnpm_patterns(pnpm_ws: Path) -> list[str]:
    """Parse patterns from pnpm-workspace.yaml."""
    if not pnpm_ws.is_file():
        return []
    patterns: list[str] = []
    for line in pnpm_ws.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            pat = stripped.lstrip("- '\"").rstrip("'\"")
            patterns.append(pat)
    return patterns


def _extract_pkg_json_patterns(pkg_json: Path) -> list[str]:
    """Parse workspace patterns from package.json."""
    if not pkg_json.is_file():
        return []
    patterns: list[str] = []
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        ws_entry = data.get("workspaces")
        if isinstance(ws_entry, list):
            patterns.extend(ws_entry)
        elif isinstance(ws_entry, dict):
            patterns.extend(ws_entry.get("packages", []))
    except Exception:  # noqa: BLE001, S110
        pass
    return patterns


def _parse_js_package(pkg_dir: Path) -> WorkspacePackage | None:
    """Extract WorkspacePackage from a directory containing package.json."""
    pkg_file = pkg_dir / "package.json"
    if not pkg_file.is_file():
        return None
    try:
        data = json.loads(pkg_file.read_text(encoding="utf-8"))
        name = data.get("name", pkg_dir.name)
        deps = list(data.get("dependencies", {}).keys()) + list(
            data.get("devDependencies", {}).keys()
        )
        return WorkspacePackage(name=name, path=pkg_dir, dependencies=deps)
    except Exception:  # noqa: BLE001
        return None


def _discover_js_packages(root_resolved: Path) -> list[WorkspacePackage]:
    """Discover all packages defined in JS/TS monorepos."""
    patterns = _extract_pnpm_patterns(
        root_resolved / "pnpm-workspace.yaml"
    ) + _extract_pkg_json_patterns(root_resolved / "package.json")
    packages: list[WorkspacePackage] = []
    for pat in patterns:
        _validate_confinement(pat, root_resolved, "Workspace pattern")
        target_dir = root_resolved / pat.rstrip("/*")
        if not target_dir.is_dir():
            continue
        for child in target_dir.iterdir():
            if child.is_dir():
                pkg = _parse_js_package(child)
                if pkg is not None:
                    packages.append(pkg)
    return packages


def _parse_cargo_package(crate_dir: Path) -> WorkspacePackage | None:
    """Extract WorkspacePackage from a directory containing Cargo.toml."""
    cargo_file = crate_dir / "Cargo.toml"
    if not cargo_file.is_file():
        return None
    try:
        crate_data = tomllib.loads(cargo_file.read_text(encoding="utf-8"))
        crate_name = crate_data.get("package", {}).get("name", crate_dir.name)
        return WorkspacePackage(name=crate_name, path=crate_dir, dependencies=[])
    except Exception:  # noqa: BLE001
        return None


def _discover_cargo_packages(root_resolved: Path) -> list[WorkspacePackage]:
    """Discover all packages defined in Cargo monorepos."""
    cargo_toml = root_resolved / "Cargo.toml"
    if not cargo_toml.is_file():
        return []
    try:
        cargo_data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []

    members = cargo_data.get("workspace", {}).get("members", [])
    packages: list[WorkspacePackage] = []
    for member in members:
        _validate_confinement(member, root_resolved, "Cargo workspace member")
        target_dir = root_resolved / member.rstrip("/*")
        if not target_dir.is_dir():
            continue
        for child in target_dir.iterdir():
            if child.is_dir():
                pkg = _parse_cargo_package(child)
                if pkg is not None:
                    packages.append(pkg)
    return packages


def discover_workspace_packages(root: Path) -> list[WorkspacePackage]:
    """Discover all packages across JS/TS and Rust (Cargo) monorepos."""
    root_resolved = root.resolve()
    packages = _discover_js_packages(root_resolved) + _discover_cargo_packages(
        root_resolved
    )
    log_subsystem(
        "workspace", "INFO", f"Discovered {len(packages)} workspace package(s)"
    )
    return packages


def topological_sort_workspace_packages(
    packages: list[WorkspacePackage],
) -> list[WorkspacePackage]:
    """Sort workspace packages in dependency-first topological order."""
    pkg_by_name = {p.name: p for p in packages}
    visited: set[str] = set()
    visiting: set[str] = set()
    result: list[WorkspacePackage] = []

    def visit(name: str) -> None:
        if name in visiting:
            # Cycle detected; skip to avoid infinite loop
            return
        if name not in visited and name in pkg_by_name:
            visiting.add(name)
            pkg = pkg_by_name[name]
            for dep in pkg.dependencies:
                if dep in pkg_by_name:
                    visit(dep)
            visiting.remove(name)
            visited.add(name)
            result.append(pkg)

    for pkg in packages:
        if pkg.name not in visited:
            visit(pkg.name)

    return result
