"""AST-safe Python import statement reconciler."""

from __future__ import annotations

import ast


class AstImportMerger:
    """Merges two conflicting sets of Python import statements into a single unified AST."""

    @staticmethod
    def merge_import_blocks(base_imports: str, branch_a: str, branch_b: str) -> str:
        def extract_imports(source: str) -> tuple[set[str], dict[str, set[str]]]:
            direct = set()
            from_imports: dict[str, set[str]] = {}
            try:
                tree = ast.parse(source)
            except SyntaxError:
                return direct, from_imports

            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        as_part = f" as {alias.asname}" if alias.asname else ""
                        direct.add(f"{alias.name}{as_part}")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod not in from_imports:
                        from_imports[mod] = set()
                    for alias in node.names:
                        as_part = f" as {alias.asname}" if alias.asname else ""
                        from_imports[mod].add(f"{alias.name}{as_part}")
            return direct, from_imports

        dir_a, from_a = extract_imports(branch_a)
        dir_b, from_b = extract_imports(branch_b)

        merged_direct = sorted(dir_a | dir_b)
        merged_from_modules = sorted(set(from_a.keys()) | set(from_b.keys()))

        lines = []
        for imp in merged_direct:
            lines.append(f"import {imp}")

        for mod in merged_from_modules:
            names = sorted(from_a.get(mod, set()) | from_b.get(mod, set()))
            lines.append(f"from {mod} import {', '.join(names)}")

        return "\n".join(lines)
