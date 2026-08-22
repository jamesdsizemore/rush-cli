"""AST-based automated unused import statement cleaner."""

from __future__ import annotations

import ast


class UnusedImportCleaner:
    """Removes unused imports from Python source text without changing formatting unnecessarily."""

    @staticmethod
    def clean_unused_imports(source_code: str, unused_names: set[str]) -> str:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code

        class ImportCleaner(ast.NodeTransformer):
            def visit_Import(self, node: ast.Import) -> ast.AST | None:
                new_names = [
                    alias
                    for alias in node.names
                    if alias.asname or alias.name not in unused_names
                ]
                if not new_names:
                    return None
                node.names = new_names
                return node

            def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
                new_names = [
                    alias
                    for alias in node.names
                    if alias.asname or alias.name not in unused_names
                ]
                if not new_names:
                    return None
                node.names = new_names
                return node

        cleaner = ImportCleaner()
        new_tree = cleaner.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
