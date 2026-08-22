"""SemVer API contract differ detecting breaking changes in public symbols."""

import ast
from pathlib import Path


class SemverLinter:
    """Compares exported module signatures to detect breaking API changes."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def extract_public_symbols(self, code: str) -> dict[str, list[str]]:
        """Extracts public functions and their parameter lists."""
        symbols: dict[str, list[str]] = {}
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and not node.name.startswith("_"):
                    params = [arg.arg for arg in node.args.args]
                    symbols[node.name] = params
        except Exception:  # noqa: BLE001, S110
            pass
        return symbols

    def diff_apis(self, old_code: str, new_code: str) -> list[str]:
        old_syms = self.extract_public_symbols(old_code)
        new_syms = self.extract_public_symbols(new_code)
        breaking = []

        # Check removed symbols
        for sym in old_syms:
            if sym not in new_syms:
                breaking.append(f"Breaking change: Public symbol '{sym}' was removed.")
            else:
                old_params = old_syms[sym]
                new_params = new_syms[sym]
                if len(new_params) < len(old_params):
                    breaking.append(
                        f"Breaking change: Function '{sym}' reduced parameters from {old_params} to {new_params}."
                    )

        return breaking
