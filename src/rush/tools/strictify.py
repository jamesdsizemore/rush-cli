"""Algebraic type narrowing and runtime type guard synthesizer."""

import ast
from pathlib import Path
from typing import Any


class TypeSynthesizer:
    """Inspects untyped function signatures and synthesizes runtime type guards and assertions."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def audit_and_synthesize(self, file_path: Path) -> dict[str, Any]:
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        code = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code)

        untyped_args: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args:
                    if (
                        arg.arg != "self"
                        and arg.arg != "cls"
                        and arg.annotation is None
                    ):
                        untyped_args.append(
                            {
                                "function": node.name,
                                "argument": arg.arg,
                                "line": node.lineno,
                                "suggested_guard": f"assert isinstance({arg.arg}, (str, int, dict)), f'Expected valid type for {arg.arg}'",
                            }
                        )

        return {
            "file": str(
                file_path.relative_to(self.project_root)
                if file_path.is_relative_to(self.project_root)
                else file_path
            ),
            "untyped_count": len(untyped_args),
            "untyped_arguments": untyped_args,
        }
