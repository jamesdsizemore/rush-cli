"""Multi-agent coordination and conflict recovery operations for session continuity."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ..mcp_mesh.lock_manager import MeshLockManager
from ..memory.failure_ledger import FailureLedger
from ..permissions import ExecutionPermissions
from ..safety.redactor import SecretRedactor
from .results import ContinuityOutput, build_continuity_result, valid_name


def check_coordination(
    started: float,
    root: Path,
    coordination_path: str | None,
    agent_id: str | None,
    max_age_s: float,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Inspect mesh lock state for a coordination target."""
    target = (root / (coordination_path or "")).resolve()
    if root not in target.parents or not target.is_file() or max_age_s < 0:
        return build_continuity_result(
            started,
            "skipped",
            "Coordination target was not found inside the project.",
            operation="coordination_check",
            granted=granted,
            coordination={"state": "unavailable", "owner": None},
            as_v1=as_v1,
        )
    lock = MeshLockManager.inspect(root, target)
    owner = lock.get("owner")
    acquired_at = lock.get("acquired_at")
    if lock["state"] == "held" and not isinstance(acquired_at, (int, float)):
        return build_continuity_result(
            started,
            "skipped",
            "Local ownership evidence was unavailable.",
            operation="coordination_check",
            granted=granted,
            coordination={"state": "unavailable", "owner": None},
            as_v1=as_v1,
        )
    if (
        lock["state"] == "held"
        and isinstance(acquired_at, (int, float))
        and time.time() - acquired_at > max_age_s
    ):
        coordination = {
            "state": "stale",
            "owner": owner,
            "action": "manual_recovery_required",
        }
        return build_continuity_result(
            started,
            "skipped",
            "Stale local ownership evidence requires manual recovery.",
            operation="coordination_check",
            granted=granted,
            coordination=coordination,
            as_v1=as_v1,
        )
    coordination = {
        "state": "conflict"
        if lock["state"] == "held" and owner != agent_id
        else lock["state"],
        "owner": owner,
    }
    return build_continuity_result(
        started,
        "skipped" if coordination["state"] in {"conflict", "unavailable"} else "ok",
        "Local ownership conflict; no change was made."
        if coordination["state"] == "conflict"
        else "No conflicting local owner."
        if coordination["state"] == "available"
        else "Local ownership is held by this agent."
        if coordination["state"] == "held"
        else "Local ownership evidence is unavailable.",
        operation="coordination_check",
        granted=granted,
        coordination=coordination,
        as_v1=as_v1,
    )


def preview_merge(
    started: float,
    base_code: str | None,
    ours_code: str | None,
    theirs_code: str | None,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Preview 3-way merge outcome without applying modifications."""
    from ..tools.swarm_merge import SwarmMergeSolver

    if (
        not isinstance(base_code, str)
        or not isinstance(ours_code, str)
        or not isinstance(theirs_code, str)
    ):
        return build_continuity_result(
            started,
            "skipped",
            "Merge preview requires all three source revisions.",
            operation="coordination_merge_preview",
            granted=granted,
            coordination={"state": "unavailable", "owner": None},
            as_v1=as_v1,
        )
    preview = SwarmMergeSolver().merge_3way(base_code, ours_code, theirs_code)
    conflicts = preview.get("conflicts", [])
    if not preview.get("success"):
        return build_continuity_result(
            started,
            "skipped",
            "Merge conflict requires manual reconciliation.",
            operation="coordination_merge_preview",
            granted=granted,
            coordination={
                "state": "merge_conflict",
                "action": "manual_reconciliation_required",
                "conflicts": conflicts,
            },
            as_v1=as_v1,
        )
    return build_continuity_result(
        started,
        "ok",
        "Merge preview found no overlapping edits.",
        operation="coordination_merge_preview",
        granted=granted,
        coordination={"state": "merge_preview", "owner": None},
        as_v1=as_v1,
    )


def _fetch_replay_events(
    root: Path, session_id: str | None
) -> tuple[str, list[dict[str, Any]]]:
    if not session_id:
        return "not_found", []
    try:
        from ..tools.flight_recorder import FlightRecorder

        events = FlightRecorder(root, create=False).replay_session(session_id)
        return ("recorded" if events else "not_found"), events
    except (OSError, ValueError):
        return "unavailable", []


def _fetch_failure_receipt(
    root: Path, failure_fingerprint: Any
) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(failure_fingerprint, str):
        return None, False
    try:
        return FailureLedger(root).get_receipt(failure_fingerprint), False
    except (OSError, sqlite3.DatabaseError):
        return None, True


def recover_coordination(
    started: float,
    root: Path,
    session_id: str | None,
    failure_fingerprint: Any,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Gather coordination recovery evidence across flight recorder, failure ledger, and mistake miner."""
    if session_id is not None and not valid_name(session_id):
        return build_continuity_result(
            started,
            "skipped",
            "Replay session was not found.",
            operation="coordination_recovery",
            granted=granted,
            coordination={
                "state": "unavailable",
                "recovery": {
                    "replay": {
                        "state": "not_found",
                        "session_id": None,
                        "event_count": 0,
                    },
                    "failure": {"state": "not_requested"},
                },
            },
            as_v1=as_v1,
        )
    replay_state, events = _fetch_replay_events(root, session_id)
    failure, failure_unavailable = _fetch_failure_receipt(root, failure_fingerprint)

    from ..memory.mistake_miner import MistakeMiner

    mined_mistakes, _ = SecretRedactor.redact_value(MistakeMiner(root).mine_mistakes())
    mistakes = [
        {
            "authority": "historical_evidence",
            "reverted_subject": item.get("reverted_subject", "unknown"),
            "rationale": item.get("rationale", "No explanation provided"),
            "guard_status": item.get("guard_status", "unknown"),
        }
        for item in mined_mistakes[:3]
        if isinstance(item, dict)
    ]
    recovery = {
        "replay": {
            "state": replay_state,
            "session_id": session_id,
            "event_count": len(events),
            **({"last_event_type": events[-1].get("event_type")} if events else {}),
        },
        "failure": (
            {"fingerprint": failure_fingerprint, "state": "unavailable"}
            if failure_unavailable and isinstance(failure_fingerprint, str)
            else failure
            or (
                {"fingerprint": failure_fingerprint, "state": "tombstoned"}
                if isinstance(failure_fingerprint, str)
                else {"state": "not_requested"}
            )
        ),
        "mistakes": mistakes,
    }
    available = bool(events or failure or mistakes)
    return build_continuity_result(
        started,
        "ok" if available else "skipped",
        "Recovery evidence is available; no retry was performed."
        if available
        else "No replay, failure, or mistake evidence was found.",
        operation="coordination_recovery",
        granted=granted,
        coordination={
            "state": "recovery_evidence" if available else "unavailable",
            "recovery": recovery,
        },
        as_v1=as_v1,
    )


_coordination_check = check_coordination
_coordination_merge_preview = preview_merge
_coordination_recovery = recover_coordination
