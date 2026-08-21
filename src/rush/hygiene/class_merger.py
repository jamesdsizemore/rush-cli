"""AST class body method and attribute reconciler."""

from __future__ import annotations

import ast


class AstClassMerger:
    """Reconciles methods and fields added across multiple branches into a single class AST."""

    @staticmethod
    def merge_classes(class_a: ast.ClassDef, class_b: ast.ClassDef) -> ast.ClassDef:
        methods_a = {n.name: n for n in class_a.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        methods_b = {n.name: n for n in class_b.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

        all_method_names = sorted(set(methods_a.keys()) | set(methods_b.keys()))
        merged_body: list[ast.AST] = []

        docstring = ast.get_docstring(class_a) or ast.get_docstring(class_b)
        if docstring:
            merged_body.append(ast.Expr(value=ast.Constant(value=docstring)))

        for item in class_a.body:
            if isinstance(item, ast.AnnAssign):
                merged_body.append(item)
        for item in class_b.body:
            if isinstance(item, ast.AnnAssign) and item not in merged_body:
                merged_body.append(item)

        for name in all_method_names:
            if name in methods_a:
                merged_body.append(methods_a[name])
            elif name in methods_b:
                merged_body.append(methods_b[name])

        new_class = ast.ClassDef(
            name=class_a.name,
            bases=class_a.bases,
            keywords=class_a.keywords,
            body=merged_body,
            decorator_list=class_a.decorator_list,
        )
        return new_class
