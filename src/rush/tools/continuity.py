"""Shared session-continuity tool used by the CLI and MCP transports."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Literal

from ..memory.checkpoint_journal import CheckpointJournal
from ..memory.failure_ledger import FailureLedger
from ..memory.merkle_invalidator import MerkleInvalidator
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
from ..safety.redactor import SecretRedactor
from .base import ToolFn, ToolResult

SessionOperation = Literal["save", "list", "restore"]
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
        )

    def run(
        self,
        path: Path,
        *,
        operation: SessionOperation = "list",
        name: str | None = None,
        files: list[str] | None = None,
        handoff: dict[str, Any] | None = None,
        permissions: ExecutionPermissions | None = None,
        config: Any = None,
    ) -> ToolResult:
        del config
        started = monotonic()
        root = path.resolve()
        granted = permissions or ExecutionPermissions()

        if operation not in {"save", "list", "restore"}:
            return self._result(
                started,
                "error",
                f"Unsupported session operation: {operation}.",
                operation=operation,
                granted=granted,
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
