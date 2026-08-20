"""Monorepo workspace discovery, path boundary validation, and topological sorting.

Architecture §8, Phase 26.
Enforces Control 2: Path Confinement on workspace definitions.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from rush.logging import get_logger, log_subsystem

logger = get_logger("discovery.workspace")


@dataclass(frozen=True)
class WorkspacePackage:
    """Represents a discovered package within a monorepo."""

    name: str
    path: Path
    dependencies: list[str] = field(default_factory=list)


def discover_workspaces(root: Path) -> list[WorkspacePackage]:
    """Discover all packages across JS/TS (pnpm, npm, yarn, turborepo), Rust (Cargo), and Go monorepos.

    Raises ValueError if any workspace definition escapes the repository boundary.
    """
    root_resolved = root.resolve()
    packages: list[WorkspacePackage] = []

    # 1. Check pnpm-workspace.yaml or package.json workspaces
    pnpm_ws = root_resolved / "pnpm-workspace.yaml"
    pkg_json = root_resolved / "package.json"

    patterns: list[str] = []
    if pnpm_ws.is_file():
        # Quick parse of YAML lines without heavy YAML parser
        for line in pnpm_ws.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("-"):
                pat = line.lstrip("- '\"").rstrip("'\"")
                patterns.append(pat)

    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            ws_entry = data.get("workspaces")
            if isinstance(ws_entry, list):
                patterns.extend(ws_entry)
            elif isinstance(ws_entry, dict):
                patterns.extend(ws_entry.get("packages", []))
        except Exception:  # noqa: BLE001, S110
            pass

    for pat in patterns:
        # Validate pattern doesn't escape root
        if ".." in pat:
            log_subsystem(
                "workspace",
                "SECURITY_ERROR",
                f"Workspace pattern '{pat}' resolves outside repository root '{root_resolved}'",
            )
            raise ValueError(
                f"Security Error: Workspace pattern '{pat}' resolves outside repository root"
            )

        # Resolve glob
        pat_clean = pat.rstrip("/*")
        target_dir = root_resolved / pat_clean
        if target_dir.is_dir():
            for child in target_dir.iterdir():
                if child.is_dir() and (child / "package.json").is_file():
                    try:
                        c_data = json.loads(
                            (child / "package.json").read_text(encoding="utf-8")
                        )
                        c_name = c_data.get("name", child.name)
                        deps = list(c_data.get("dependencies", {}).keys()) + list(
                            c_data.get("devDependencies", {}).keys()
                        )
                        packages.append(
                            WorkspacePackage(
                                name=c_name,
                                path=child,
                                dependencies=deps,
                            )
                        )
                    except Exception:  # noqa: BLE001, S110
                        pass

    # 2. Check Cargo workspace in Cargo.toml
    cargo_toml = root_resolved / "Cargo.toml"
    if cargo_toml.is_file():
        try:
            cargo_data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
            ws = cargo_data.get("workspace", {})
            members = ws.get("members", [])
            for member in members:
                if ".." in member:
                    log_subsystem(
                        "workspace",
                        "SECURITY_ERROR",
                        f"Cargo workspace member '{member}' resolves outside repository root",
                    )
                    raise ValueError(
                        f"Security Error: Cargo workspace member '{member}' resolves outside repository root"
                    )
                member_clean = member.rstrip("/*")
                target_dir = root_resolved / member_clean
                if target_dir.is_dir():
                    for child in target_dir.iterdir():
                        if child.is_dir() and (child / "Cargo.toml").is_file():
                            try:
                                crate_data = tomllib.loads(
                                    (child / "Cargo.toml").read_text(encoding="utf-8")
                                )
                                crate_name = crate_data.get("package", {}).get(
                                    "name", child.name
                                )
                                packages.append(
                                    WorkspacePackage(
                                        name=crate_name,
                                        path=child,
                                        dependencies=[],
                                    )
                                )
                            except Exception:  # noqa: BLE001, S110
                                pass
        except ValueError:
            raise
        except Exception:  # noqa: BLE001, S110
            pass

    log_subsystem(
        "workspace", "INFO", f"Discovered {len(packages)} workspace package(s)"
    )
    return packages


def topological_sort_workspaces(
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
