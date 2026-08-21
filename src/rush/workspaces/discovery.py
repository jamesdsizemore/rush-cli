"""Polyglot workspace discovery engine."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

from rush.workspaces.models import WorkspacePackage


class WorkspaceDiscovery:
    """Discovers sub-packages across Python, Rust, Node, and Go workspaces."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_all(self) -> list[WorkspacePackage]:
        packages: list[WorkspacePackage] = []
        packages.extend(self._discover_cargo_workspaces())
        packages.extend(self._discover_pnpm_workspaces())
        packages.extend(self._discover_python_workspaces())
        packages.extend(self._discover_go_workspaces())
        return packages

    def _discover_cargo_workspaces(self) -> list[WorkspacePackage]:
        cargo_root = self.repo_root / "Cargo.toml"
        if not cargo_root.exists():
            return []

        packages = []
        try:
            data = tomllib.loads(cargo_root.read_text(encoding="utf-8"))
            members = data.get("workspace", {}).get("members", [])
            for pattern in members:
                for member_path in self.repo_root.glob(pattern):
                    if member_path.is_dir() and (member_path / "Cargo.toml").exists():
                        pkg_data = tomllib.loads((member_path / "Cargo.toml").read_text(encoding="utf-8"))
                        pkg_name = pkg_data.get("package", {}).get("name", member_path.name)
                        rel_path = member_path.relative_to(self.repo_root).as_posix()
                        packages.append(
                            WorkspacePackage(
                                name=pkg_name,
                                kind="rust",
                                root_path=member_path,
                                relative_path=rel_path,
                            )
                        )
        except Exception:
            pass
        return packages

    def _discover_pnpm_workspaces(self) -> list[WorkspacePackage]:
        packages = []
        for pkg_json in self.repo_root.glob("packages/*/package.json"):
            if "node_modules" not in pkg_json.parts:
                try:
                    data = json.loads(pkg_json.read_text(encoding="utf-8"))
                    name = data.get("name", pkg_json.parent.name)
                    rel_path = pkg_json.parent.relative_to(self.repo_root).as_posix()
                    packages.append(
                        WorkspacePackage(
                            name=name,
                            kind="node",
                            root_path=pkg_json.parent,
                            relative_path=rel_path,
                        )
                    )
                except Exception:
                    pass
        return packages

    def _discover_python_workspaces(self) -> list[WorkspacePackage]:
        packages = []
        for pyproject in self.repo_root.glob("packages/*/pyproject.toml"):
            if ".venv" not in pyproject.parts:
                try:
                    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                    name = data.get("project", {}).get("name", pyproject.parent.name)
                    rel_path = pyproject.parent.relative_to(self.repo_root).as_posix()
                    packages.append(
                        WorkspacePackage(
                            name=name,
                            kind="python",
                            root_path=pyproject.parent,
                            relative_path=rel_path,
                        )
                    )
                except Exception:
                    pass
        return packages

    def _discover_go_workspaces(self) -> list[WorkspacePackage]:
        go_work = self.repo_root / "go.work"
        if not go_work.exists():
            return []

        packages = []
        try:
            content = go_work.read_text(encoding="utf-8")
            in_use_block = False
            for line in content.splitlines():
                line_clean = line.strip()
                if line_clean.startswith("use ("):
                    in_use_block = True
                    continue
                elif line_clean == ")" and in_use_block:
                    in_use_block = False
                    continue
                elif (in_use_block or line_clean.startswith("use ")) and line_clean:
                    mod_path_str = line_clean.replace("use ", "").strip().strip("()")
                    mod_path = (self.repo_root / mod_path_str).resolve()
                    if mod_path.is_dir() and (mod_path / "go.mod").exists():
                        packages.append(
                            WorkspacePackage(
                                name=mod_path.name,
                                kind="go",
                                root_path=mod_path,
                                relative_path=mod_path.relative_to(self.repo_root).as_posix(),
                            )
                        )
        except Exception:
            pass
        return packages
