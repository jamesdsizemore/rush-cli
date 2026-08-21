"""Python AST cyclomatic complexity calculator."""

from __future__ import annotations

import ast
from pathlib import Path


class AstComplexityVisitor(ast.NodeVisitor):
    """Calculates McCabe cyclomatic complexity score for a Python AST module."""

    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


class CyclomaticComplexityCalculator:
    """Measures source code cyclomatic complexity."""

    @staticmethod
    def calculate_file(file_path: Path) -> int:
        if not file_path.exists() or file_path.suffix != ".py":
            return 1
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return 1

        visitor = AstComplexityVisitor()
        visitor.visit(tree)
        return visitor.complexity
