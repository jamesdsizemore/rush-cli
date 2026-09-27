"""Top-level 3-way AST structural merge solver."""

from __future__ import annotations

import ast

from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.import_merger import AstImportMerger


class ASTConflictMerger:
    """Performs semantic 3-way reconciliation on AST bodies."""

    @staticmethod
    def merge_source_files(
        base_source: str, branch_a_source: str, branch_b_source: str
    ) -> tuple[bool, str]:
        try:
            tree_a = ast.parse(branch_a_source)
            tree_b = ast.parse(branch_b_source)
        except SyntaxError as e:
            return False, f"Syntax error prevents AST merge: {e}"

        merged_imports = AstImportMerger.merge_import_blocks(
            "", branch_a_source, branch_b_source
        )

        classes_a = {n.name: n for n in tree_a.body if isinstance(n, ast.ClassDef)}
        classes_b = {n.name: n for n in tree_b.body if isinstance(n, ast.ClassDef)}

        merged_classes = []
        for name in sorted(set(classes_a.keys()) | set(classes_b.keys())):
            if name in classes_a and name in classes_b:
                merged_classes.append(
                    ast.unparse(
                        AstClassMerger.merge_classes(classes_a[name], classes_b[name])
                    )
                )
            elif name in classes_a:
                merged_classes.append(ast.unparse(classes_a[name]))
            elif name in classes_b:
                merged_classes.append(ast.unparse(classes_b[name]))

        # T27: every other top-level statement is carried or refused, never
        # silently dropped from a result reported as a successful merge.
        merged_functions = _merge_functions(tree_a, tree_b)
        if isinstance(merged_functions, str):
            return False, merged_functions
        other_a = [ast.unparse(n) for n in tree_a.body if not isinstance(n, _MERGED)]
        other_b = [ast.unparse(n) for n in tree_b.body if not isinstance(n, _MERGED)]
        if other_a and other_b and other_a != other_b:
            return False, (
                "top-level statements other than imports, classes and functions "
                "differ between the two files; refusing to drop either side"
            )

        result_parts = []
        if merged_imports.strip():
            result_parts.append(merged_imports.strip())
        if other_a or other_b:
            result_parts.append("\n".join(other_a or other_b))
        if merged_classes:
            result_parts.append("\n\n".join(merged_classes))
        if merged_functions:
            result_parts.append("\n\n".join(merged_functions))

        return True, "\n\n".join(result_parts) + "\n"


_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_MERGED = (ast.Import, ast.ImportFrom, ast.ClassDef, *_FUNCTIONS)


def _merge_functions(tree_a: ast.Module, tree_b: ast.Module) -> list[str] | str:
    """Union of top-level functions by name, or the conflict message when one
    name has two different definitions."""
    funcs_a = {n.name: ast.unparse(n) for n in tree_a.body if isinstance(n, _FUNCTIONS)}
    funcs_b = {n.name: ast.unparse(n) for n in tree_b.body if isinstance(n, _FUNCTIONS)}
    merged: list[str] = []
    for name in sorted(funcs_a.keys() | funcs_b.keys()):
        a, b = funcs_a.get(name), funcs_b.get(name)
        if a is not None and b is not None and a != b:
            return f"conflicting definitions of top-level function {name!r}"
        merged.append(a or b or "")
    return merged
