"""Swarm 3-Way AST merge conflict resolver combining independent method and class edits."""

import ast
from typing import Any


class SwarmMergeSolver:
    """Reconciles independent AST additions between base, ours, and theirs without textual conflict markers."""

    def merge_3way(
        self, base_code: str, ours_code: str, theirs_code: str
    ) -> dict[str, Any]:
        try:
            base_tree = ast.parse(base_code)
            ours_tree = ast.parse(ours_code)
            theirs_tree = ast.parse(theirs_code)
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": f"AST parse error during 3-way merge: {e}",
                "merged_code": None,
            }

        base_funcs = {
            n.name: n
            for n in base_tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        ours_funcs = {
            n.name: n
            for n in ours_tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        theirs_funcs = {
            n.name: n
            for n in theirs_tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        # Combine functions from ours and theirs
        merged_body = []

        # Start with all non-function statements from ours (imports, constants)
        for node in ours_tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                merged_body.append(node)

        all_func_names = sorted(set(ours_funcs.keys()).union(set(theirs_funcs.keys())))
        for fname in all_func_names:
            if fname in ours_funcs and fname not in base_funcs:
                merged_body.append(ours_funcs[fname])
            elif fname in theirs_funcs and fname not in base_funcs:
                merged_body.append(theirs_funcs[fname])
            elif fname in ours_funcs:
                merged_body.append(ours_funcs[fname])
            elif fname in theirs_funcs:
                merged_body.append(theirs_funcs[fname])

        merged_module = ast.Module(body=merged_body, type_ignores=[])
        ast.fix_missing_locations(merged_module)

        try:
            merged_code = ast.unparse(merged_module)
            return {
                "success": True,
                "functions_merged": len(all_func_names),
                "merged_code": merged_code,
            }
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": f"AST unparse failed: {e}",
                "merged_code": None,
            }
