"""Bi-temporal Git revert mistake memory miner parsing past reverts."""

import re
from pathlib import Path
from typing import Any

from src.rush.tools.common import run_subprocess


class MistakeMiner:
    """Mines git history for revert commits to extract guard rails against repeating mistakes."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def parse_revert_message(
        self, commit_subject: str, commit_body: str
    ) -> dict[str, Any] | None:
        if not re.match(r"(?i)^revert\b", commit_subject.strip()):
            return None

        # Extract reverted feature
        m = re.search(r'Revert\s+"([^"]+)"', commit_subject, re.IGNORECASE)
        reverted_target = m.group(1) if m else commit_subject

        return {
            "reverted_subject": reverted_target,
            "rationale": (
                commit_body.strip() if commit_body else "No explanation provided"
            ),
            "guard_status": "active",
        }

    def mine_mistakes(self) -> list[dict[str, Any]]:
        mistakes: list[dict[str, Any]] = []
        try:
            res = run_subprocess(
                [
                    "git",
                    "log",
                    "--grep=Revert",
                    "-n",
                    "20",
                    "--pretty=format:%s%x00%b%x1e",
                ],
                cwd=self.project_root,
            )
            if res.returncode != 0 or not res.stdout:
                return []
            entries = res.stdout.split("\x1e")
            for entry in entries:
                if not entry.strip():
                    continue
                parts = entry.split("\x00", 1)
                subject = parts[0]
                body = parts[1] if len(parts) > 1 else ""
                parsed = self.parse_revert_message(subject, body)
                if parsed:
                    mistakes.append(parsed)
        except Exception:  # noqa: BLE001, S110
            pass
        return mistakes
