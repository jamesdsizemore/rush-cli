"""Top-level 3-way AST structural merge solver."""

from __future__ import annotations

import ast
from pathlib import Path
from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.import_merger import AstImportMerger


class ASTConflictMerger:
    """Performs semantic 3-way reconciliation on AST bodies."""

    @staticmethod
    def merge_source_files(base_source: str, branch_a_source: str, branch_b_source: str) -> tuple[bool, str]:
        try:
            tree_a = ast.parse(branch_a_source)
            tree_b = ast.parse(branch_b_source)
        except SyntaxError as e:
            return False, f"Syntax error prevents AST merge: {e}"

        merged_imports = AstImportMerger.merge_import_blocks("", branch_a_source, branch_b_source)

        classes_a = {n.name: n for n in tree_a.body if isinstance(n, ast.ClassDef)}
        classes_b = {n.name: n for n in tree_b.body if isinstance(n, ast.ClassDef)}

        merged_classes = []
        for name in sorted(set(classes_a.keys()) | set(classes_b.keys())):
            if name in classes_a and name in classes_b:
                merged_classes.append(ast.unparse(AstClassMerger.merge_classes(classes_a[name], classes_b[name])))
            elif name in classes_a:
                merged_classes.append(ast.unparse(classes_a[name]))
            elif name in classes_b:
                merged_classes.append(ast.unparse(classes_b[name]))

        result_parts = []
        if merged_imports.strip():
            result_parts.append(merged_imports.strip())
        if merged_classes:
            result_parts.append("\n\n".join(merged_classes))

        return True, "\n\n".join(result_parts) + "\n"
