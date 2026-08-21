"""AST-based non-tree-shakeable barrel import auditor."""

from __future__ import annotations

import re
from pathlib import Path

HEAVY_BARRELS = {
    "@mui/material",
    "@mui/icons-material",
    "lodash",
    "rxjs",
    "lucide-react",
}


class BarrelImportAuditor:
    """Detects broad barrel imports that defeat tree-shaking."""

    @staticmethod
    def audit_source_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        findings = []

        for idx, line in enumerate(lines, start=1):
            line_clean = line.strip()
            for pkg in HEAVY_BARRELS:
                pattern = rf'import\s+\{{.*\}}\s+from\s+[\'"]{re.escape(pkg)}[\'"]'
                if re.search(pattern, line_clean):
                    findings.append(
                        f"{file_path.name}:{idx}: Non-tree-shakeable barrel import from '{pkg}'. Use deep import path instead."
                    )

        return findings
