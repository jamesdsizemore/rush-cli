"""Cognitive complexity refactoring decomposer isolating complex logic into helper functions."""

import ast
from pathlib import Path
from typing import Any


class ComplexityDecomposer:
    """Calculates cognitive/cyclomatic complexity of functions and proposes modular decompositions."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def calculate_complexity(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        score = 1
        for sub in ast.walk(node):
            if isinstance(
                sub,
                (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With, ast.Assert),
            ):
                score += 1
            elif isinstance(sub, ast.BoolOp):
                score += len(sub.values) - 1
        return score

    def decompose_file(
        self, file_path: Path, max_complexity: int = 10
    ) -> dict[str, Any]:
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        code = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code)

        candidates: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self.calculate_complexity(node)
                if complexity > max_complexity:
                    candidates.append(
                        {
                            "function": node.name,
                            "line": node.lineno,
                            "complexity": complexity,
                            "recommendation": f"Extract helper functions for nested conditional blocks in '{node.name}' (complexity {complexity}).",
                        }
                    )

        return {
            "file": str(
                file_path.relative_to(self.project_root)
                if file_path.is_relative_to(self.project_root)
                else file_path
            ),
            "needs_simplification": len(candidates) > 0,
            "complex_functions_count": len(candidates),
            "candidates": candidates,
        }
