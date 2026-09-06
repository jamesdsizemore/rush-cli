"""Receipt saving, validation, and restoration for session continuity."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..memory.failure_ledger import FailureLedger
from ..memory.merkle_invalidator import MerkleInvalidator
from ..safety.redactor import SecretRedactor


def _extract_failure_receipt(
    project_root: Path, failure_fingerprint: Any
) -> dict[str, Any] | None:
    if not isinstance(failure_fingerprint, str):
        return None
    try:
        return FailureLedger(project_root).get_receipt(failure_fingerprint) or {
            "fingerprint": failure_fingerprint,
            "state": "tombstoned",
        }
    except (OSError, sqlite3.DatabaseError):
        return {
            "fingerprint": failure_fingerprint,
            "state": "unavailable",
        }


def _extract_session_memory(project_root: Path) -> dict[str, Any]:
    try:
        from ..session_memory import SessionMemoryManager

        records = SessionMemoryManager(
            memory_file=project_root / ".rush" / "session_memory.json"
        ).load_records()
        return {
            "authority": "historical_evidence",
            "state": "available" if records else "absent",
            "count": len(records[-5:]),
            "records": [
                {
                    "timestamp": record.timestamp,
                    "tool_name": record.tool_name,
                    "finding_count": record.finding_count,
                    "fixes_applied": record.fixes_applied,
                    "summary": record.summary,
                }
                for record in records[-5:]
            ],
        }
    except (OSError, ValueError, TypeError):
        return {
            "authority": "historical_evidence",
            "state": "unavailable",
            "count": 0,
            "records": [],
        }


def save_receipt(project_root: Path, handoff: dict[str, Any]) -> dict[str, Any]:
    """Create and persist a sanitized handoff receipt."""
    dependencies = [
        value for value in handoff.get("dependencies", []) if isinstance(value, str)
    ]
    historic_instruction = handoff.get("historic_instruction")
    failure_fingerprint = handoff.get("failure_fingerprint")
    failure_receipt = _extract_failure_receipt(project_root, failure_fingerprint)
    session_memory = _extract_session_memory(project_root)

    receipt, redaction_count = SecretRedactor.redact_value(
        {
            "version": 1,
            "current_goal": handoff.get("current_goal") or None,
            "open_work": list(handoff.get("open_work") or []),
            "historic_instruction": {
                "authority": "historical_evidence",
                "state": "quarantined",
                "present": bool(historic_instruction),
            },
            "dependencies": MerkleInvalidator.snapshot_paths(
                project_root, dependencies
            ),
            "freshness": "current",
            "failure_receipt": failure_receipt,
            "session_memory": session_memory,
        }
    )
    receipt["redaction_count"] = redaction_count
    return receipt


def restore_receipt(project_root: Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Restore and assess freshness of a handoff receipt from checkpoint data."""
    saved = checkpoint.get("metadata", {}).get("handoff")
    if not isinstance(saved, dict):
        return {
            "version": 0,
            "freshness": "unknown",
            "state": "legacy_checkpoint",
        }
    dependencies = saved.get("dependencies", {})
    paths = list(dependencies) if isinstance(dependencies, dict) else []
    current = MerkleInvalidator.snapshot_paths(project_root, paths)
    freshness = "current" if current == dependencies else "stale"
    return {**saved, "freshness": freshness}


_save_handoff_receipt = save_receipt
_restore_handoff_receipt = restore_receipt
