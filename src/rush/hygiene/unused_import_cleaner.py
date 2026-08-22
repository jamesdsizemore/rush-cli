"""AST-based automated unused import statement cleaner."""

from __future__ import annotations

import ast
from pathlib import Path


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

    @classmethod
    def clean_file(cls, file_path: Path) -> tuple[str, int]:
        """Detect and remove unused imports in the target Python file."""
        if not file_path.exists() or file_path.suffix != ".py":
            return "", 0
        source = file_path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return source, 0

        # Find all imported names
        imported_names: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported_names[alias.asname or alias.name] = node

        # Find all referenced names in the rest of AST
        referenced_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced_names.add(node.attr)

        unused = set(imported_names.keys()) - referenced_names
        if not unused:
            return source, 0

        cleaned = cls.clean_unused_imports(source, unused)
        return cleaned, len(unused)
