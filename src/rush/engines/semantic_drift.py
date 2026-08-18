"""Parser contract for optional semantic-drift engine JSON reports."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import Finding
from .base import Engine, EngineResult


class SemanticDriftEngine(Engine):
    name = "semantic-drift"
    binary = "semantic-drift"
    file_extensions = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        return {"exit_code": 0, "summary": "semantic drift requires configured target"}

    def parse_report(self, payload: str) -> list[Finding]:
        report = json.loads(payload)
        return [
            Finding(
                path=str(item.get("path", "")),
                line=int(item.get("line", 0)),
                rule="semantic-drift",
                severity="warn",
                message=str(item.get("message", "drift detected")),
            )
            for item in report.get("findings", [])
        ]
