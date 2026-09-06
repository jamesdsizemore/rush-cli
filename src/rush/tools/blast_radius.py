"""Transitive blast radius analyzer determining downstream impact of changes."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from rush.tools.blast_radius_graph import (
    build_reverse_import_graph,
    walk_impacted_paths,
)


class BlastRadiusReport(BaseModel):
    """Structured report of downstream impacted files, routes, and tests."""

    target_files: list[str] = Field(default_factory=list)
    max_depth: int = 5
    affected_files: list[str] = Field(default_factory=list)
    affected_routes: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)
    risk_score: str = "LOW"


class BlastRadiusAnalyzer:
    """Traverses AST imports to identify all files that import the target modules."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def analyze(
        self, changed_files: list[Path], max_depth: int = 5
    ) -> BlastRadiusReport:
        target_stems = {p.stem for p in changed_files}
        graph = build_reverse_import_graph(self.project_root, target_stems)
        affected = walk_impacted_paths(graph, target_stems, max_depth)

        tests = {p for p in affected if "test" in p}
        routes = {p for p in affected if "route" in p or "api" in p or "cli" in p}

        risk = self._calculate_risk(len(affected), len(routes))

        return BlastRadiusReport(
            target_files=[str(p) for p in changed_files],
            max_depth=max_depth,
            affected_files=sorted(affected),
            affected_routes=sorted(routes),
            recommended_tests=sorted(tests),
            risk_score=risk,
        )

    @staticmethod
    def _calculate_risk(affected_count: int, routes_count: int) -> str:
        if affected_count > 10 or routes_count > 2:
            return "HIGH"
        if affected_count > 3 or routes_count > 0:
            return "MEDIUM"
        return "LOW"
