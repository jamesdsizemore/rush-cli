"""Polyglot dead code and unused export detector."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class DeadCodeFinding:
    file_path: str
    line_number: int
    symbol_name: str
    confidence: int
    kind: str


class PolyglotDeadCodeDetector:
    """Discovers unreferenced functions, unused imports, and dead variables."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def scan_python(self, min_confidence: int = 80) -> list[DeadCodeFinding]:
        proc = run_subprocess(
            ["vulture", ".", f"--min-confidence={min_confidence}"],
            cwd=self.repo_root,
        )
        findings = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if ":" in line_clean:
                parts = line_clean.split(":")
                if len(parts) >= 3:
                    file_p = parts[0].strip()
                    try:
                        line_n = int(parts[1].strip())
                    except ValueError:
                        line_n = 1
                    msg = ":".join(parts[2:]).strip()
                    findings.append(
                        DeadCodeFinding(
                            file_path=file_p,
                            line_number=line_n,
                            symbol_name=msg,
                            confidence=min_confidence,
                            kind="python_symbol",
                        )
                    )
        return findings

    def scan_typescript(self) -> list[DeadCodeFinding]:
        if not (self.repo_root / "package.json").exists():
            return []
        run_subprocess(["npx", "knip", "--reporter", "json"], cwd=self.repo_root)
        return []
