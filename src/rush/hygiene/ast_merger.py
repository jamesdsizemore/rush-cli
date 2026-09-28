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

        # T27: the merged module keeps its source statement order (docstring,
        # imports, then every other top-level statement interleaved with the
        # definitions), so a `__main__` guard still follows the function it
        # calls. Nothing is dropped; only a real conflict refuses the merge.
        units_a, units_b = _units(tree_a), _units(tree_b)
        order = _merge_order(list(units_a), list(units_b))
        rendered: dict[_Key, str] = {}
        for key in order:
            a, b = units_a.get(key), units_b.get(key)
            if isinstance(a, ast.ClassDef) and isinstance(b, ast.ClassDef):
                rendered[key] = ast.unparse(AstClassMerger.merge_classes(a, b))
                continue
            text_a = ast.unparse(a) if a is not None else None
            text_b = ast.unparse(b) if b is not None else None
            if text_a is not None and text_b is not None and text_a != text_b:
                return False, _conflict(key)
            rendered[key] = text_a or text_b or ""
        clash = sorted(
            _one_sided_assignments(units_a, units_b)
            & _one_sided_assignments(units_b, units_a)
        )
        if clash:
            return False, f"conflicting top-level assignments to {clash[0]!r}"

        result_parts = []
        if _DOC in rendered:
            result_parts.append(rendered[_DOC])
        if merged_imports.strip():
            result_parts.append(merged_imports.strip())
        result_parts.extend(rendered[key] for key in order if key != _DOC)
        return True, "\n\n".join(result_parts) + "\n"


_Key = tuple[str, ...]
_DOC: _Key = ("doc",)
_MAIN: _Key = ("main",)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_main_guard(node: ast.stmt) -> bool:
    test = node.test if isinstance(node, ast.If) else None
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _units(tree: ast.Module) -> dict[_Key, ast.stmt]:
    """Every non-import top-level statement in source order, keyed so the
    same unit in both files pairs up: the docstring, each definition by name,
    the `__main__` guard, and any other statement by its source text and
    occurrence."""
    units: dict[_Key, ast.stmt] = {}
    seen: dict[str, int] = {}
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        key: _Key
        if index == 0 and ast.get_docstring(tree, clean=False) is not None:
            key = _DOC
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            key = ("def", node.name)
        elif _is_main_guard(node):
            key = _MAIN
        else:
            text = ast.unparse(node)
            seen[text] = seen.get(text, 0) + 1
            key = ("stmt", text, str(seen[text]))
        units[key] = node
    return units


def _merge_order(keys_a: list[_Key], keys_b: list[_Key]) -> list[_Key]:
    """File A's order, with each unit only in file B placed right after the
    unit that precedes it in file B."""
    order = list(keys_a)
    for index, key in enumerate(keys_b):
        if key in order:
            continue
        anchor = next((k for k in reversed(keys_b[:index]) if k in order), None)
        order.insert(order.index(anchor) + 1 if anchor is not None else 0, key)
    return order


def _conflict(key: _Key) -> str:
    if key == _DOC:
        return "the module docstrings differ between the two files"
    if key == _MAIN:
        return 'the `if __name__ == "__main__"` blocks differ between the two files'
    return f"conflicting definitions of top-level function {key[1]!r}"


def _one_sided_assignments(
    units: dict[_Key, ast.stmt], other: dict[_Key, ast.stmt]
) -> set[str]:
    """Names assigned by a top-level statement present only in `units`."""
    names: set[str] = set()
    for key, node in units.items():
        if key in other:
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        else:
            continue
        names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names
