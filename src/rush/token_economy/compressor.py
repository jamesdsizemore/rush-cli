"""Python AST structural outline compressor."""

from __future__ import annotations

import ast
from pathlib import Path


class PythonAstOutlineCompressor:
    """Strips implementation bodies from Python ASTs to produce minimal outlines."""

    @staticmethod
    def compress_source(source_code: str) -> str:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code

        class OutlineTransformer(ast.NodeTransformer):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

            def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
                docstring = ast.get_docstring(node)
                new_body = []
                if docstring:
                    new_body.append(ast.Expr(value=ast.Constant(value=docstring)))
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        new_body.append(self.visit(item))
                    elif isinstance(item, ast.AnnAssign):
                        new_body.append(item)
                if not new_body:
                    new_body.append(ast.Expr(value=ast.Constant(value=...)))
                node.body = new_body
                return node

        transformer = OutlineTransformer()
        transformed_tree = transformer.visit(tree)
        ast.fix_missing_locations(transformed_tree)
        return ast.unparse(transformed_tree)
