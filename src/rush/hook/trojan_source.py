"""Unicode bidi / homoglyph injection detector."""

from __future__ import annotations

from pathlib import Path

# Dangerous Trojan Source Unicode Bidirectional characters
BIDI_CHARS = {
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",
    "\u2066", "\u2067", "\u2068", "\u2069", "\u200E", "\u200F",
}


class TrojanSourceDetector:
    """Detects invisible or reversing Unicode bidirectional override characters."""

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
            for ch in BIDI_CHARS:
                if ch in line:
                    findings.append(
                        f"{file_path.name}:{idx}: Dangerous Trojan Source Unicode character detected (U+{ord(ch):04X})."
                    )
        return findings
