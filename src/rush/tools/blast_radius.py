"""Transitive blast radius analyzer determining downstream impact of changes."""

import ast
from pathlib import Path

from pydantic import BaseModel, Field


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
        affected: set[str] = set()
        tests: set[str] = set()
        routes: set[str] = set()

        target_module_names = {p.stem for p in changed_files}

        for py_file in self.project_root.glob("**/*.py"):
            if (
                ".venv" in str(py_file)
                or ".git" in str(py_file)
                or ".rush" in str(py_file)
            ):
                continue
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if any(tm in alias.name for tm in target_module_names):
                                rel = str(py_file.relative_to(self.project_root))
                                affected.add(rel)
                                if "test" in rel:
                                    tests.add(rel)
                                if "route" in rel or "api" in rel or "cli" in rel:
                                    routes.add(rel)
                    elif (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and any(tm in node.module for tm in target_module_names)
                    ):
                        rel = str(py_file.relative_to(self.project_root))
                        affected.add(rel)
                        if "test" in rel:
                            tests.add(rel)
                        if "route" in rel or "api" in rel or "cli" in rel:
                            routes.add(rel)
            except Exception:  # noqa: BLE001, S110
                pass

        risk = "LOW"
        if len(affected) > 10 or len(routes) > 2:
            risk = "HIGH"
        elif len(affected) > 3 or len(routes) > 0:
            risk = "MEDIUM"

        return BlastRadiusReport(
            target_files=[str(p) for p in changed_files],
            max_depth=max_depth,
            affected_files=sorted(affected),
            affected_routes=sorted(routes),
            recommended_tests=sorted(tests),
            risk_score=risk,
        )
