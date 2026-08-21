"""Staged merge conflict marker detector."""

from __future__ import annotations

import re
from pathlib import Path

CONFLICT_MARKERS = [
    re.compile(r"^<{7}\s+", re.MULTILINE),
    re.compile(r"^={7}$", re.MULTILINE),
    re.compile(r"^>{7}\s+", re.MULTILINE),
]


class ConflictMarkerGuard:
    """Detects unresolved Git merge conflict markers in staged files."""

    @staticmethod
    def inspect_file(file_path: Path) -> list[str]:
        if not file_path.exists() or not file_path.is_file():
            return []
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = []
        for idx, line in enumerate(text.splitlines(), start=1):
            for pat in CONFLICT_MARKERS:
                if pat.search(line):
                    findings.append(f"{file_path.name}:{idx}: Unresolved merge conflict marker: '{line.strip()}'")
        return findings
