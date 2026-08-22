"""AST Environment Variable Parity Linter comparing codebase usage vs .env.example."""

import ast
from pathlib import Path
from typing import Any


class EnvParityLinter:
    """Detects environment variable drift and missing declarations."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def lint(self) -> dict[str, Any]:
        code_vars: set[str] = set()
        for py_file in self.project_root.glob("**/*.py"):
            if (
                ".venv" in str(py_file)
                or "tests" in str(py_file)
                or ".git" in str(py_file)
            ):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("getenv", "get")
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        code_vars.add(node.args[0].value)
            except Exception:  # noqa: BLE001, S112
                continue

        example_file = self.project_root / ".env.example"
        declared_vars: set[str] = set()
        if example_file.exists():
            for line in example_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    declared_vars.add(line.split("=", 1)[0].strip())

        missing_in_example = sorted(code_vars - declared_vars)
        return {
            "codebase_vars": sorted(code_vars),
            "declared_vars": sorted(declared_vars),
            "missing_in_example": missing_in_example,
            "passed": len(missing_in_example) == 0,
        }
