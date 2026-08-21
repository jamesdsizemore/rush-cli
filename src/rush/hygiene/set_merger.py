"""AST set literal member reconciler."""

from __future__ import annotations

import ast


class AstSetMerger:
    """Merges Python set AST literals while preventing duplicate constants."""

    @staticmethod
    def merge_sets(set_a: ast.Set, set_b: ast.Set) -> ast.Set:
        elts: list[ast.expr] = []
        seen = set()

        for item in list(set_a.elts) + list(set_b.elts):
            if isinstance(item, ast.Constant):
                if item.value not in seen:
                    seen.add(item.value)
                    elts.append(item)
            else:
                elts.append(item)

        return ast.Set(elts=elts)
