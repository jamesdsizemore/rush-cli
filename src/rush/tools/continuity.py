"""Shared session-continuity tool used by the CLI and MCP transports."""

from __future__ import annotations

import time
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from ..codegraph.context_packer import ContextPacker
from ..mcp_mesh.lock_manager import MeshLockManager
from ..memory.checkpoint_journal import CheckpointJournal
from ..memory.failure_ledger import FailureLedger
from ..memory.merkle_invalidator import MerkleInvalidator
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
from ..safety.redactor import SecretRedactor
from ..token_economy.ccr_store import CCRStore
from ..tools.flight_recorder import FlightRecorder
from .base import ToolFn, ToolResult

SessionOperation = Literal[
    "save",
    "list",
    "restore",
    "context_pack",
    "context_retrieve",
    "coordination_check",
    "coordination_merge_preview",
    "coordination_recovery",
]
_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)


class SessionContinuityTool(ToolFn):
    """Persist or inspect a local session checkpoint through one result contract."""

    name = "continuity"

    @property
    def mcp_description(self) -> str:
        return (
            "Save, list, or restore a local Rush session checkpoint. Returns "
            "{status, findings[], summary}; saving requires explicit cache-write permission."
        )

    def __call__(
        self,
        path: Path,
        operation: SessionOperation = "list",
        name: str | None = None,
        files: list[str] | None = None,
        allow_cache_write: bool = False,
        current_goal: str | None = None,
        open_work: list[str] | None = None,
        historic_instruction: str | None = None,
        failure_fingerprint: str | None = None,
        dependencies: list[str] | None = None,
        context_path: str | None = None,
        target_symbol: str = "",
        token_budget: int = 4000,
        context_handle: str | None = None,
        coordination_path: str | None = None,
        agent_id: str | None = None,
        coordination_max_age_s: float = 300.0,
        base_code: str | None = None,
        ours_code: str | None = None,
        theirs_code: str | None = None,
        flight_session_id: str | None = None,
    ) -> ToolResult:
        return self.run(
            path,
            operation=operation,
            name=name,
            files=files,
            handoff={
                "current_goal": current_goal,
                "open_work": open_work or [],
                "historic_instruction": historic_instruction,
                "failure_fingerprint": failure_fingerprint,
                "dependencies": dependencies or [],
            },
            permissions=ExecutionPermissions(cache_write=allow_cache_write),
            context_path=context_path,
            target_symbol=target_symbol,
            token_budget=token_budget,
            context_handle=context_handle,
            coordination_path=coordination_path,
            agent_id=agent_id,
            coordination_max_age_s=coordination_max_age_s,
            base_code=base_code,
            ours_code=ours_code,
            theirs_code=theirs_code,
            flight_session_id=flight_session_id,
        )

    def run(
        self,
        path: Path,
        *,
        operation: SessionOperation = "list",
        name: str | None = None,
        files: list[str] | None = None,
        handoff: dict[str, Any] | None = None,
        context_path: str | None = None,
        target_symbol: str = "",
        token_budget: int = 4000,
        context_handle: str | None = None,
        coordination_path: str | None = None,
        agent_id: str | None = None,
        coordination_max_age_s: float = 300.0,
        base_code: str | None = None,
        ours_code: str | None = None,
        theirs_code: str | None = None,
        flight_session_id: str | None = None,
        failure_fingerprint: str | None = None,
        permissions: ExecutionPermissions | None = None,
        config: Any = None,
    ) -> ToolResult:
        del config
        started = monotonic()
        root = path.resolve()
        granted = permissions or ExecutionPermissions()

        if operation not in {
            "save",
            "list",
            "restore",
            "context_pack",
            "context_retrieve",
            "coordination_check",
            "coordination_merge_preview",
            "coordination_recovery",
        }:
            return self._result(
                started,
                "error",
                f"Unsupported session operation: {operation}.",
                operation=operation,
                granted=granted,
            )

        if operation == "context_pack":
            return self._context_pack(
                started, root, context_path, target_symbol, token_budget, granted
            )
        if operation == "context_retrieve":
            return self._context_retrieve(started, root, context_handle, granted)
        if operation == "coordination_check":
            return self._coordination_check(
                started,
                root,
                coordination_path,
                agent_id,
                coordination_max_age_s,
                granted,
            )
        if operation == "coordination_merge_preview":
            return self._coordination_merge_preview(
                started, base_code, ours_code, theirs_code, granted
            )
        if operation == "coordination_recovery":
            return self._coordination_recovery(
                started,
                root,
                flight_session_id,
                failure_fingerprint or (handoff or {}).get("failure_fingerprint"),
                granted,
            )

        if operation in {"save", "restore"} and not self._valid_name(name):
            return self._result(
                started,
                "error",
                "Session checkpoint names must be a single filename.",
                operation=operation,
                granted=granted,
            )

        if operation == "save":
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"Session save requires {', '.join(missing)}.",
                    operation=operation,
                    granted=granted,
                    requested=_WRITE_PERMISSION,
                )
            handoff_receipt = self._save_handoff_receipt(root, handoff or {})
            journal = CheckpointJournal(root)
            checkpoint = journal.save_checkpoint(
                name or "",
                {"cwd": str(root), "handoff": handoff_receipt},
                list(files or []),
            )
            data = journal.restore_checkpoint(name or "")
            return self._result(
                started,
                "ok",
                f"Saved session checkpoint '{name}'.",
                operation=operation,
                granted=granted,
                requested=_WRITE_PERMISSION,
                raw=data,
                artifacts=[str(checkpoint)],
                handoff=handoff_receipt,
            )

        session_dir = root / ".rush" / "sessions"
        if operation == "list":
            sessions = (
                CheckpointJournal(root).list_checkpoints()
                if session_dir.exists()
                else []
            )
            return self._result(
                started,
                "ok",
                f"Listed {len(sessions)} session checkpoint(s).",
                operation=operation,
                granted=granted,
                raw=sessions,
            )

        if not session_dir.exists():
            return self._result(
                started,
                "skipped",
                f"Session checkpoint '{name}' was not found.",
                operation=operation,
                granted=granted,
            )
        data = CheckpointJournal(root).restore_checkpoint(name or "")
        if data is None:
            return self._result(
                started,
                "skipped",
                f"Session checkpoint '{name}' was not found.",
                operation=operation,
                granted=granted,
            )
        handoff_receipt = self._restore_handoff_receipt(root, data)
        return self._result(
            started,
            "ok",
            f"Restored session checkpoint '{name}'.",
            operation=operation,
            granted=granted,
            raw=data,
            handoff=handoff_receipt,
        )

    def _context_pack(
        self,
        started: float,
        project_root: Path,
        context_path: str | None,
        target_symbol: str,
        token_budget: int,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        if not context_path or token_budget < 1:
            return self._result(
                started,
                "error",
                "Context pack requires a repository-relative path and positive token budget.",
                operation="context_pack",
                granted=granted,
            )
        target = (project_root / context_path).resolve()
        if project_root not in target.parents or not target.is_file():
            return self._result(
                started,
                "skipped",
                "Context target was not found inside the project.",
                operation="context_pack",
                granted=granted,
            )
        packed = ContextPacker(project_root).pack(
            target, target_symbol=target_symbol, max_tokens=1_000_000
        )
        estimated = int(packed.get("tokens", 0))
        if estimated > token_budget:
            envelope = {
                "selected_evidence": [],
                "tokens": {
                    "estimated": estimated,
                    "actual": None,
                    "budget": token_budget,
                },
                "omissions": [{"reason": "insufficient_budget", "mandatory": True}],
                "recovery": {"state": "not_created"},
            }
            return self._result(
                started,
                "skipped",
                "Context pack requires a larger token budget.",
                operation="context_pack",
                granted=granted,
                context_envelope=envelope,
            )
        safe_packed, redactions = SecretRedactor.redact_value(packed)
        envelope = {
            "selected_evidence": [{"path": context_path, "selection": "target_file"}],
            "tokens": {"estimated": estimated, "actual": None, "budget": token_budget},
            "omissions": [],
            "recovery": {"state": "not_needed"},
            "redaction_count": redactions,
        }
        return self._result(
            started,
            "ok",
            "Packed bounded context evidence.",
            operation="context_pack",
            granted=granted,
            raw=safe_packed,
            context_envelope=envelope,
        )

    def _context_retrieve(
        self,
        started: float,
        root: Path,
        handle: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        content = CCRStore(root).retrieve_chunk(handle or "") if handle else None
        recovery = {
            "state": "recovered" if content is not None else "not_found",
            "handle": handle,
        }
        return self._result(
            started,
            "ok" if content is not None else "skipped",
            "Recovered context handle."
            if content is not None
            else "Context handle was not found.",
            operation="context_retrieve",
            granted=granted,
            raw={"content": content} if content is not None else None,
            context_envelope={
                "selected_evidence": [],
                "tokens": {"estimated": None, "actual": None, "budget": None},
                "omissions": [],
                "recovery": recovery,
            },
        )

    def _coordination_check(
        self,
        started: float,
        root: Path,
        coordination_path: str | None,
        agent_id: str | None,
        max_age_s: float,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        target = (root / (coordination_path or "")).resolve()
        if root not in target.parents or not target.is_file() or max_age_s < 0:
            return self._result(
                started,
                "skipped",
                "Coordination target was not found inside the project.",
                operation="coordination_check",
                granted=granted,
                coordination={"state": "unavailable", "owner": None},
            )
        lock = MeshLockManager.inspect(root, target)
        owner = lock.get("owner")
        if lock["state"] == "held":
            acquired_at = float(lock["acquired_at"])
            if time.time() - acquired_at > max_age_s:
                coordination = {
                    "state": "stale",
                    "owner": owner,
                    "action": "manual_recovery_required",
                }
                return self._result(
                    started,
                    "skipped",
                    "Stale local ownership evidence requires manual recovery.",
                    operation="coordination_check",
                    granted=granted,
                    coordination=coordination,
                )
        coordination = {
            "state": "conflict"
            if lock["state"] == "held" and owner != agent_id
            else lock["state"],
            "owner": owner,
        }
        return self._result(
            started,
            "skipped" if coordination["state"] in {"conflict", "unavailable"} else "ok",
            "Local ownership conflict; no change was made."
            if coordination["state"] == "conflict"
            else "No conflicting local owner."
            if coordination["state"] == "available"
            else "Local ownership evidence is unavailable.",
            operation="coordination_check",
            granted=granted,
            coordination=coordination,
        )

    def _coordination_merge_preview(
        self,
        started: float,
        base_code: str | None,
        ours_code: str | None,
        theirs_code: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        from .swarm_merge import SwarmMergeSolver

        if not all(
            isinstance(code, str) for code in (base_code, ours_code, theirs_code)
        ):
            return self._result(
                started,
                "skipped",
                "Merge preview requires all three source revisions.",
                operation="coordination_merge_preview",
                granted=granted,
                coordination={"state": "unavailable", "owner": None},
            )
        preview = SwarmMergeSolver().merge_3way(base_code, ours_code, theirs_code)
        conflicts = preview.get("conflicts", [])
        if not preview.get("success"):
            return self._result(
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
            )
        return self._result(
            started,
            "ok",
            "Merge preview found no overlapping edits.",
            operation="coordination_merge_preview",
            granted=granted,
            coordination={"state": "merge_preview", "owner": None},
        )

    def _coordination_recovery(
        self,
        started: float,
        root: Path,
        session_id: str | None,
        failure_fingerprint: Any,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        if session_id is not None and not self._valid_name(session_id):
            return self._result(
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
            )
        replay_state = "not_found"
        events: list[dict[str, Any]] = []
        if session_id:
            try:
                events = FlightRecorder(root, create=False).replay_session(session_id)
                replay_state = "recorded" if events else "not_found"
            except (OSError, ValueError):
                replay_state = "unavailable"
        failure = (
            FailureLedger(root).get_receipt(failure_fingerprint)
            if isinstance(failure_fingerprint, str)
            else None
        )
        recovery = {
            "replay": {
                "state": replay_state,
                "session_id": session_id,
                "event_count": len(events),
                **({"last_event_type": events[-1].get("event_type")} if events else {}),
            },
            "failure": failure
            or (
                {"fingerprint": failure_fingerprint, "state": "tombstoned"}
                if isinstance(failure_fingerprint, str)
                else {"state": "not_requested"}
            ),
        }
        available = bool(events or failure)
        return self._result(
            started,
            "ok" if available else "skipped",
            "Recovery evidence is available; no retry was performed."
            if available
            else "No replay or failure evidence was found.",
            operation="coordination_recovery",
            granted=granted,
            coordination={
                "state": "recovery_evidence" if available else "unavailable",
                "recovery": recovery,
            },
        )

    @staticmethod
    def _valid_name(name: str | None) -> bool:
        return bool(name) and Path(name).name == name and name not in {".", ".."}

    def _result(
        self,
        started: float,
        status: Literal["ok", "error", "skipped"],
        summary: str,
        *,
        operation: str,
        granted: ExecutionPermissions,
        requested: ExecutionPermissions | None = None,
        raw: Any = None,
        artifacts: list[str] | None = None,
        handoff: dict[str, Any] | None = None,
        context_envelope: dict[str, Any] | None = None,
        coordination: dict[str, Any] | None = None,
    ) -> ToolResult:
        return {
            "tool": self.name,
            "engine": "checkpoint-journal",
            "engine_version": None,
            "status": status,
            "duration_ms": int((monotonic() - started) * 1000),
            "summary": summary,
            "findings": [],
            "raw": raw,
            "artifacts": artifacts,
            "metadata": {
                "operation": operation,
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=requested,
                    granted=granted,
                    producer="checkpoint-journal",
                ),
                **({"handoff": handoff} if handoff is not None else {}),
                **(
                    {"context_envelope": context_envelope}
                    if context_envelope is not None
                    else {}
                ),
                **({"coordination": coordination} if coordination is not None else {}),
            },
        }

    @staticmethod
    def _save_handoff_receipt(
        project_root: Path, handoff: dict[str, Any]
    ) -> dict[str, Any]:
        dependencies = [
            value for value in handoff.get("dependencies", []) if isinstance(value, str)
        ]
        historic_instruction = handoff.get("historic_instruction")
        failure_fingerprint = handoff.get("failure_fingerprint")
        failure_receipt = None
        if isinstance(failure_fingerprint, str):
            failure_receipt = FailureLedger(project_root).get_receipt(
                failure_fingerprint
            ) or {"fingerprint": failure_fingerprint, "state": "tombstoned"}
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
            }
        )
        receipt["redaction_count"] = redaction_count
        return receipt

    @staticmethod
    def _restore_handoff_receipt(
        project_root: Path, checkpoint: dict[str, Any]
    ) -> dict[str, Any]:
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
