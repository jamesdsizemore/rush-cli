"""Sub-millisecond staged Python AST validator."""

from __future__ import annotations

import ast
from pathlib import Path


class FastIncrementalAstLinter:
    """Validates syntax compilation for staged Python files in microseconds."""

    @staticmethod
    def lint_staged_python(file_paths: list[Path]) -> list[str]:
        errors = []
        for p in file_paths:
            if p.suffix == ".py" and p.exists():
                try:
                    ast.parse(p.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError as e:
                    errors.append(f"{p.name}:{e.lineno}:{e.offset}: SyntaxError: {e.msg}")
        return errors
