"""AST dictionary key-value pair reconciler."""

from __future__ import annotations

import ast


class AstDictMerger:
    """Merges dictionary AST definitions containing distinct keys."""

    @staticmethod
    def merge_dicts(dict_a: ast.Dict, dict_b: ast.Dict) -> ast.Dict:
        keys: list[ast.expr] = []
        values: list[ast.expr] = []

        seen_keys = set()
        for k, v in zip(dict_a.keys, dict_a.values):
            if k is not None and isinstance(k, ast.Constant):
                seen_keys.add(k.value)
                keys.append(k)
                values.append(v)

        for k, v in zip(dict_b.keys, dict_b.values):
            if k is not None and isinstance(k, ast.Constant):
                if k.value not in seen_keys:
                    keys.append(k)
                    values.append(v)

        return ast.Dict(keys=keys, values=values)
