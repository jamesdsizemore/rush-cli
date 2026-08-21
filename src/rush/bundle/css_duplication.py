"""Duplicate CSS rule block detector."""

from __future__ import annotations

import re
from pathlib import Path


class CssDuplicationScanner:
    """Finds exact duplicate CSS rule declaration blocks across stylesheets."""

    @staticmethod
    def scan_stylesheet(css_file: Path) -> list[str]:
        if not css_file.exists():
            return []
        text = css_file.read_text(encoding="utf-8", errors="replace")
        blocks = re.findall(r"([^{]+)\{([^}]+)\}", text)

        seen_bodies: dict[str, str] = {}
        duplicates = []

        for selector, body in blocks:
            norm_body = " ".join(body.split()).strip()
            norm_sel = selector.strip()
            if norm_body in seen_bodies and len(norm_body) > 30:
                duplicates.append(
                    f"Duplicate CSS block between '{norm_sel}' and '{seen_bodies[norm_body]}': {{{norm_body}}}"
                )
            else:
                seen_bodies[norm_body] = norm_sel

        return duplicates
