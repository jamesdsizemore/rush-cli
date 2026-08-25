"""Shared session-continuity tool used by the CLI and MCP transports."""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Literal

from ..memory.checkpoint_journal import CheckpointJournal
from ..permissions import (
    ExecutionPermissions,
    build_execution_metadata,
    check_permissions,
)
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
    ) -> ToolResult:
        return self.run(
            path,
            operation=operation,
            name=name,
            files=files,
            permissions=ExecutionPermissions(cache_write=allow_cache_write),
        )

    def run(
        self,
        path: Path,
        *,
        operation: SessionOperation = "list",
        name: str | None = None,
        files: list[str] | None = None,
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
            journal = CheckpointJournal(root)
            checkpoint = journal.save_checkpoint(
                name or "",
                {"cwd": str(root)},
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
        return self._result(
            started,
            "ok",
            f"Restored session checkpoint '{name}'.",
            operation=operation,
            granted=granted,
            raw=data,
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
            },
        }
