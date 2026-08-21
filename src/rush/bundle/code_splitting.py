"""Dynamic import route boundary checker."""

from __future__ import annotations

import re
from pathlib import Path


class CodeSplittingValidator:
    """Ensures major page/route components use dynamic React.lazy() or next/dynamic imports."""

    @staticmethod
    def inspect_route_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        findings = []

        if "Routes" in text or "createBrowserRouter" in text:
            for line in text.splitlines():
                if "import " in line and ("Page" in line or "View" in line) and "lazy" not in text:
                    findings.append(f"{file_path.name}: Static page import detected without dynamic lazy() splitting: {line.strip()}")

        return findings
