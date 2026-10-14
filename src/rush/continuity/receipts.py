"""Receipt saving, validation, and restoration for session continuity."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..memory.checkpoint_journal import CheckpointJournal
from ..memory.failure_ledger import FailureLedger
from ..memory.merkle_invalidator import MerkleInvalidator
from ..memory.store import MemoryStoreUnreadableError
from ..memory.trust import default_entry_tier
from ..safety.redactor import SecretRedactor


def _extract_failure_receipt(
    project_root: Path, failure_fingerprint: Any
) -> dict[str, Any] | None:
    if not isinstance(failure_fingerprint, str):
        return None
    try:
        return FailureLedger.read_receipt(project_root, failure_fingerprint) or {
            "fingerprint": failure_fingerprint,
            "state": "tombstoned",
        }
    except (OSError, sqlite3.DatabaseError, MemoryStoreUnreadableError):
        return {
            "fingerprint": failure_fingerprint,
            "state": "unavailable",
        }


def _extract_session_memory(project_root: Path) -> dict[str, Any]:
    from ..memory.retrieval import RouteDenial, reader_route

    # 72-T01 D1 (§2.3 Continuity package): a denied `ask` route reads nothing.
    access = reader_route(
        project_root,
        "ask",
        ["session_memory:record_turn", "migration:session_memory"],
    )
    if isinstance(access, RouteDenial):
        return {
            "authority": "historical_evidence",
            "state": "unavailable",
            "count": 0,
            "records": [],
        }
    try:
        from ..memory.migration import read_origin_kind_refs_readonly
        from ..memory.retrieval import evaluate_artifact_visibility
        from ..memory.store import TypedArtifactStore
        from ..session_memory import SessionMemoryManager, SessionRecord

        if access.kind == "policy":
            # Policy mode never trusts the ambient JSON file: only the grant owner's
            # approved, visible store rows are read, and nothing is emitted once the
            # grant stops holding.
            records = []
            # A store the view cannot open (migration required) reads nothing: the
            # shared visibility decision cannot run, so no row is shown (a row the
            # view rejected as tampered never turns visible by removing columns).
            view, _state = TypedArtifactStore.open_readonly_view(project_root)
            if view is None:
                raise OSError("session memory store is not readable")
            try:
                for content, ref in read_origin_kind_refs_readonly(
                    project_root, "session_memory"
                ):
                    if ref is None:
                        continue
                    row = view.get_current_row(ref[0])
                    if (
                        row is None
                        or not evaluate_artifact_visibility(
                            view, row, access=access
                        ).visible
                    ):
                        continue
                    records.append(
                        SessionRecord(
                            timestamp=content["timestamp"],
                            tool_name=content["tool_name"],
                            finding_count=content["finding_count"],
                            fixes_applied=content["fixes_applied"],
                            summary=content["summary"],
                        )
                    )
            finally:
                view.close()
            if access.recheck() != "ok":
                raise OSError("session memory access changed")
        else:
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
    except (OSError, ValueError, TypeError, KeyError):
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
    from ..memory.retrieval import RouteDenial, reader_route

    # 72-T01 D1 (§2.3 Continuity package): a denied `ask` route reads nothing.
    if isinstance(
        reader_route(
            project_root,
            "ask",
            ["checkpoint_journal:save_checkpoint", "migration:checkpoint_journal"],
        ),
        RouteDenial,
    ):
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
