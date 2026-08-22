"""Function-level AST churn mapper."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FunctionChurnFinding:
    function_name: str
    start_line: int
    end_line: int
    churn_lines: int


class FunctionChurnMapper:
    """Maps git diff change lines to specific AST function definitions."""

    @staticmethod
    def map_file_function_churn(
        file_path: Path, changed_lines: set[int]
    ) -> list[FunctionChurnFinding]:
        if not file_path.exists() or file_path.suffix != ".py":
            return []
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            return []

        findings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 10)
                fn_lines = set(range(start, end + 1))
                intersect = fn_lines & changed_lines
                if intersect:
                    findings.append(
                        FunctionChurnFinding(
                            function_name=node.name,
                            start_line=start,
                            end_line=end,
                            churn_lines=len(intersect),
                        )
                    )
        return findings
