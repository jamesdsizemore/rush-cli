"""Receipt saving, validation, and restoration for session continuity."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..memory.checkpoint_journal import CheckpointJournal
from ..memory.failure_ledger import FailureLedger
from ..memory.merkle_invalidator import MerkleInvalidator
from ..memory.trust import default_entry_tier
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


def last_handoff_for_provider(
    project_root: Path, target_provider: str | None
) -> dict[str, Any] | None:
    """Return the most recent saved handoff receipt sent to `target_provider`, or None."""
    if not target_provider:
        return None
    for checkpoint in CheckpointJournal(project_root).list_checkpoints():
        handoff = checkpoint.get("metadata", {}).get("handoff")
        if (
            isinstance(handoff, dict)
            and handoff.get("target_provider") == target_provider
        ):
            return handoff
    return None


def save_receipt(project_root: Path, handoff: dict[str, Any]) -> dict[str, Any]:
    """Create and persist a sanitized handoff receipt.

    When `handoff["target_provider"]` is set, the receipt's `diff` field holds only the
    fields that changed since the last saved handoff to that same provider (a plain
    dict-diff, no new diff library) — or the full snapshot when no prior handoff exists.
    """
    target_provider = handoff.get("target_provider")
    dependencies = [
        value for value in handoff.get("dependencies", []) if isinstance(value, str)
    ]
    historic_instruction = handoff.get("historic_instruction")
    failure_fingerprint = handoff.get("failure_fingerprint")
    failure_receipt = _extract_failure_receipt(project_root, failure_fingerprint)
    session_memory = _extract_session_memory(project_root)

    snapshot = {
        "current_goal": handoff.get("current_goal") or None,
        "open_work": list(handoff.get("open_work") or []),
        "historic_instruction": {
            "trust_tier": default_entry_tier("local_tool"),
            "present": bool(historic_instruction),
        },
        "dependencies": MerkleInvalidator.snapshot_paths(project_root, dependencies),
        "failure_receipt": failure_receipt,
        "session_memory": session_memory,
    }
    diff: dict[str, Any] | None = None
    if target_provider:
        prior = last_handoff_for_provider(project_root, target_provider)
        if prior is None:
            diff = dict(snapshot)
        else:
            diff = {
                field: value
                for field, value in snapshot.items()
                if prior.get(field) != value
            }

    receipt, redaction_count = SecretRedactor.redact_value(
        {
            "version": 1,
            "target_provider": target_provider,
            **snapshot,
            "freshness": "current",
            "diff": diff,
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
