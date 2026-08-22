"""Polyglot AST Skeletonizer preserving signatures, types, and docstrings while eliding bodies."""

import ast
from pathlib import Path
from typing import Any


class AstSkeletonizer:
    """Extracts structural AST skeleton definitions for Python, TypeScript, and Rust."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def skeletonize_python(self, code: str, focus_symbol: str | None = None) -> str:
        """Parses Python AST and replaces function bodies with '...' unless matching focus_symbol."""
        try:
            tree = ast.parse(code)
        except Exception:  # noqa: BLE001
            return code

        class SkeletonTransformer(ast.NodeTransformer):
            def __init__(self, target: str | None):
                self.target = target

            def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
                if self.target and node.name == self.target:
                    return node

                # Preserve docstring if present
                docstring = ast.get_docstring(node)
                new_body: list[ast.stmt] = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

                node.body = new_body
                return node

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
                if self.target and node.name == self.target:
                    return node

                docstring = ast.get_docstring(node)
                new_body: list[ast.stmt] = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

                node.body = new_body
                return node

        transformer = SkeletonTransformer(focus_symbol)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)

    def skeletonize(
        self, code: str, language: str = "python", focus_symbol: str | None = None
    ) -> str:
        if language.lower() in ("python", "py"):
            return self.skeletonize_python(code, focus_symbol=focus_symbol)
        # Polyglot fallback: regex line stripper for TS / Rust
        lines = code.splitlines()
        skeleton_lines = []
        in_fn = False
        for line in lines:
            if any(
                kw in line
                for kw in (
                    "function ",
                    "fn ",
                    "pub fn ",
                    "def ",
                    "class ",
                    "interface ",
                    "struct ",
                )
            ):
                skeleton_lines.append(line)
                in_fn = True
            elif in_fn and line.strip().startswith(("}", "};", "end")):
                skeleton_lines.append("    // ...")
                skeleton_lines.append(line)
                in_fn = False
            elif not in_fn:
                skeleton_lines.append(line)
        return "\n".join(skeleton_lines)
