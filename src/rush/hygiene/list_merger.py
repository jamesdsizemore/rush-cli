"""AST list member reconciler (__all__, config arrays)."""

from __future__ import annotations

import ast


class AstListMerger:
    """Merges Python list AST literals while preventing duplicate constants."""

    @staticmethod
    def merge_lists(list_a: ast.List, list_b: ast.List) -> ast.List:
        elts: list[ast.expr] = []
        seen_constants = set()

        for item in list_a.elts:
            if isinstance(item, ast.Constant):
                seen_constants.add(item.value)
            elts.append(item)

        for item in list_b.elts:
            if isinstance(item, ast.Constant):
                if item.value not in seen_constants:
                    seen_constants.add(item.value)
                    elts.append(item)
            else:
                elts.append(item)

        return ast.List(elts=elts, ctx=ast.Load())
