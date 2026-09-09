"""Sub-millisecond staged Python AST validator."""

from __future__ import annotations

import ast
from pathlib import Path

from rush.hook.staged_scanner import StagedIndexEntry


class FastIncrementalAstLinter:
    """Validates syntax compilation for staged Python files in microseconds."""

    @staticmethod
    def lint_staged_entries(entries: list[StagedIndexEntry]) -> list[str]:
        errors = []
        for entry in entries:
            if (
                entry.status != "staged"
                or entry.content is None
                or entry.relative_path.suffix.lower() != ".py"
            ):
                continue
            try:
                ast.parse(entry.content, filename=str(entry.relative_path))
            except SyntaxError as exc:
                errors.append(
                    f"{entry.relative_path.name}:{exc.lineno}:{exc.offset}: SyntaxError: {exc.msg}"
                )
        return errors

    @staticmethod
    def lint_staged_python(file_paths: list[Path]) -> list[str]:
        errors = []
        for p in file_paths:
            if p.suffix == ".py" and p.exists():
                try:
                    ast.parse(p.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError as e:
                    errors.append(
                        f"{p.name}:{e.lineno}:{e.offset}: SyntaxError: {e.msg}"
                    )
        return errors
