"""CI/CD Matrix generator for parallelized monorepo execution."""

from __future__ import annotations

import json
from pathlib import Path
from rush.workspaces.models import WorkspaceGraph, WorkspacePackage


class WorkspaceMatrixGenerator:
    """Generates JSON build matrices for GitHub Actions / GitLab CI from affected packages."""

    @staticmethod
    def generate_github_matrix(affected_packages: list[str], graph: WorkspaceGraph) -> str:
        entries = []
        for name in affected_packages:
            pkg = graph.packages.get(name)
            if pkg:
                entries.append({
                    "package": pkg.name,
                    "kind": pkg.kind,
                    "path": pkg.relative_path,
                })
        return json.dumps({"include": entries}, indent=2)
