"""Cognitive complexity refactoring decomposer isolating complex logic into helper functions."""

import ast
from pathlib import Path
from typing import Any


class ComplexityDecomposer:
    """Calculates cognitive/cyclomatic complexity of functions and proposes modular decompositions."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def calculate_complexity(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        visitor = _FunctionComplexityVisitor()
        for statement in node.body:
            visitor.visit(statement)
        return visitor.score

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


class _FunctionComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.score = 1

    def visit_If(self, node: ast.If) -> None:
        self.score += 1
        self.generic_visit(node)

    visit_While = visit_If
    visit_For = visit_If
    visit_AsyncFor = visit_If
    visit_With = visit_If
    visit_AsyncWith = visit_If
    visit_Assert = visit_If

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.score += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.score += len(node.values) - 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return
