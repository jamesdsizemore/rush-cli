"""Bi-temporal Git revert mistake memory miner parsing past reverts."""

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rush.memory.decision_schema import DecisionRecordFields
from rush.tools.common import run_subprocess


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


def shape_failure_candidates(
    mistakes: list[dict[str, Any]], source: str = "mistake_miner"
) -> list[dict[str, Any]]:
    """Pure shaping (Phase 61 §9 P61.6.2): maps `mine_mistakes()`'s per-revert findings to
    `subject="failure"`, `trust_tier="DERIVED"` candidate dicts (`family="memory"`, matching
    `migration.py`'s existing `subject="failure"` convention). Never persists.

    `mine_mistakes()` is called unconditionally, with no permission check, by
    `continuity/coordination.py:185`'s `recover_coordination()`. Persisting these candidates is
    the caller's responsibility via `MemoryTool.write()` (P61.12), gated the same way
    `_run_save` gates `_WRITE_PERMISSION` (`tools/continuity.py:233`) — this function must never
    import `TypedArtifactStore` or call `write()` itself.
    """
    return [
        {
            "family": "memory",
            "subject": "failure",
            "trust_tier": "DERIVED",
            "content": {
                "reverted_subject": item.get("reverted_subject", "unknown"),
                "rationale": item.get("rationale", "No explanation provided"),
                "guard_status": item.get("guard_status", "unknown"),
                **asdict(
                    DecisionRecordFields(
                        target_seam=item.get("reverted_subject", "unknown")
                    )
                ),
            },
            "source": source,
        }
        for item in mistakes
    ]


if (
    __name__ == "__main__"
):  # ponytail: pure-shaping self-check, no test framework needed
    shaped = shape_failure_candidates(
        [{"reverted_subject": "x", "rationale": "y", "guard_status": "active"}],
        source="test",
    )
    assert shaped == [
        {
            "family": "memory",
            "subject": "failure",
            "trust_tier": "DERIVED",
            "content": {
                "reverted_subject": "x",
                "rationale": "y",
                "guard_status": "active",
                "red_task": None,
                "green_task": None,
                "target_seam": "x",
                "test_file": None,
                "test_function": None,
                "predecessor": None,
                "status": "in_progress",
            },
            "source": "test",
        }
    ]
    assert shape_failure_candidates([]) == []
    print("mistake_miner self-check OK")
