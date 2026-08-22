"""AST syntax validation guard for patched files."""

from __future__ import annotations

import ast
from pathlib import Path


class PatchSyntaxGuard:
    """Verifies that patched source files are syntactically valid before executing test suites."""

    @staticmethod
    def validate_file_syntax(file_path: Path) -> tuple[bool, str | None]:
        if not file_path.exists() or not file_path.is_file():
            return True, None

        if file_path.suffix == ".py":
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                ast.parse(source, filename=str(file_path))
                return True, None
            except SyntaxError as e:
                return (
                    False,
                    f"Python syntax error at line {e.lineno}, col {e.offset}: {e.msg}",
                )
            except (ValueError, OSError) as e:
                return False, f"AST parse failure: {e}"

        return True, None
