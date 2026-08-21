"""Redundant legacy polyfill detector."""

from __future__ import annotations

import re
from pathlib import Path

LEGACY_POLYFILLS = {
    "core-js/features/promise",
    "core-js/features/array/from",
    "core-js/features/object/assign",
    "whatwg-fetch",
}


class PolyfillAuditor:
    """Detects redundant legacy polyfills included for modern browser targets."""

    @staticmethod
    def audit_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        findings = []
        for poly in LEGACY_POLYFILLS:
            if poly in text:
                findings.append(f"{file_path.name}: Redundant polyfill '{poly}' detected.")
        return findings
