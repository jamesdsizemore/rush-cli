"""Shared session-continuity tool used by the CLI and MCP transports."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from ..continuity.context import pack_context, retrieve_context
from ..continuity.coordination import (
    check_coordination,
    preview_merge,
    recover_coordination,
)
from ..continuity.providers import (
    provider_command,
    provider_handoff,
    provider_prompt,
    resume_omniroute,
    resume_provider,
    windows_cmd_command,
)
from ..continuity.receipts import restore_receipt, save_receipt
from ..continuity.results import (
    ContinuityResult,
    build_continuity_result,
    valid_name,
)
from ..contracts.results import ToolResultV1
from ..memory.checkpoint_journal import CheckpointJournal
from ..permissions import (
    ExecutionPermissions,
    check_permissions,
)
from .base import Finding, ToolFn, ToolResult

SessionOperation = Literal[
    "save",
    "list",
    "restore",
    "context_pack",
    "context_retrieve",
    "coordination_check",
    "coordination_merge_preview",
    "coordination_recovery",
    "provider_resume",
]
_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)

VALID_OPERATIONS = {
    "save",
    "list",
    "restore",
    "context_pack",
    "context_retrieve",
    "coordination_check",
    "coordination_merge_preview",
    "coordination_recovery",
    "provider_resume",
}

__all__ = [
    "ContinuityResult",
    "SessionContinuityTool",
    "os",
]


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
        allow_network: bool = False,
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
        provider_id: str | None = None,
        as_v1: bool = False,
    ) -> ToolResult | ToolResultV1:
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
            permissions=ExecutionPermissions(
                cache_write=allow_cache_write, network=allow_network
            ),
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
            provider_id=provider_id,
            as_v1=as_v1,
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
        provider_id: str | None = None,
        permissions: ExecutionPermissions | None = None,
        config: Any = None,
        as_v1: bool = False,
    ) -> ToolResult | ToolResultV1:
        del config
        self._as_v1 = as_v1
        started = monotonic()
        root = path.resolve()
        granted = permissions or ExecutionPermissions()

        if operation not in VALID_OPERATIONS:
            return self._result(
                started,
                "error",
                f"Unsupported session operation: {operation}.",
                operation=operation,
                granted=granted,
            )

        handoff = {**(handoff or {}), "target_provider": provider_id}

        dispatch_table = {
            "context_pack": lambda: self._context_pack(
                started, root, context_path, target_symbol, token_budget, granted
            ),
            "context_retrieve": lambda: self._context_retrieve(
                started, root, context_handle, granted
            ),
            "coordination_check": lambda: self._coordination_check(
                started,
                root,
                coordination_path,
                agent_id,
                coordination_max_age_s,
                granted,
            ),
            "coordination_merge_preview": lambda: self._coordination_merge_preview(
                started, base_code, ours_code, theirs_code, granted
            ),
            "coordination_recovery": lambda: self._coordination_recovery(
                started,
                root,
                flight_session_id,
                failure_fingerprint or (handoff or {}).get("failure_fingerprint"),
                granted,
            ),
            "provider_resume": lambda: self._provider_resume(
                started, root, name, provider_id, granted
            ),
            "save": lambda: self._run_save(
                started, root, name, files, handoff, granted
            ),
            "list": lambda: self._run_list(started, root, granted),
            "restore": lambda: self._run_restore(started, root, name, granted),
        }
        return dispatch_table[operation]()

    def _run_save(
        self,
        started: float,
        root: Path,
        name: str | None,
        files: list[str] | None,
        handoff: dict[str, Any] | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        if not self._valid_name(name):
            return self._result(
                started,
                "error",
                "Session checkpoint names must be a single filename.",
                operation="save",
                granted=granted,
            )
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Session save requires {', '.join(missing)}.",
                operation="save",
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
            operation="save",
            granted=granted,
            requested=_WRITE_PERMISSION,
            raw=data,
            artifacts=[str(checkpoint)],
            handoff=handoff_receipt,
        )

    def _run_list(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        session_dir = root / ".rush" / "sessions"
        sessions = (
            CheckpointJournal(root).list_checkpoints() if session_dir.exists() else []
        )
        corrupt_count = sum(1 for s in sessions if s.get("status") == "corrupt")
        findings: list[Finding] = []
        for s in sessions:
            if s.get("status") == "corrupt":
                cid = s.get("checkpoint_id") or s.get("name") or "unknown"
                digest = str(s.get("raw_bytes_digest") or "")
                findings.append(
                    {
                        "path": f".rush/sessions/{cid}.json",
                        "line": 0,
                        "column": 0,
                        "rule": "corrupt_checkpoint_journal",
                        "rule_id": "CORRUPT_CHECKPOINT_JOURNAL",
                        "severity": "warn",
                        "message": (
                            f"Corrupt checkpoint journal entry '{cid}': "
                            f"{s.get('error_message', 'invalid JSON')}"
                        ),
                        "fingerprint": (
                            digest
                            if len(digest) == 64
                            else hashlib.sha256(cid.encode("utf-8")).hexdigest()
                        ),
                        "evidence": digest,
                    }
                )
        summary = (
            f"Listed {len(sessions)} session checkpoint(s)."
            if corrupt_count == 0
            else f"Listed {len(sessions)} session checkpoint(s) ({corrupt_count} corrupt)."
        )
        list_status: Literal["ok", "warn"] = "warn" if corrupt_count > 0 else "ok"
        return self._result(
            started,
            list_status,
            summary,
            operation="list",
            granted=granted,
            raw=sessions,
            findings=findings,
        )

    def _run_restore(
        self,
        started: float,
        root: Path,
        name: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        if not self._valid_name(name):
            return self._result(
                started,
                "error",
                "Session checkpoint names must be a single filename.",
                operation="restore",
                granted=granted,
            )
        data = CheckpointJournal(root).restore_checkpoint(name or "")
        if data is None:
            # CheckpointJournal.restore_checkpoint() is the sole existence authority (its physical
            # `.json` file may already be renamed `.migrated` by migration.migrate_checkpoint_journal(),
            # in which case a store-backed checkpoint would already have been returned above). Only
            # consult the physical file here to distinguish "never existed" (skipped) from "corrupt
            # bytes on disk" (error), never to gate existence itself.
            session_dir = root / ".rush" / "sessions"
            session_file = session_dir / f"{name}.json"
            migrated_file = session_dir / f"{name}.json.migrated"
            evidence_file = (
                session_file
                if session_file.exists()
                else (migrated_file if migrated_file.exists() else None)
            )
            if evidence_file is None:
                return self._result(
                    started,
                    "skipped",
                    f"Session checkpoint '{name}' was not found.",
                    operation="restore",
                    granted=granted,
                )
            try:
                raw_bytes = evidence_file.read_bytes()
                digest = hashlib.sha256(raw_bytes).hexdigest()
            except OSError:
                digest = ""
            return self._result(
                started,
                "error",
                f"Session checkpoint '{name}' is corrupt or unreadable.",
                operation="restore",
                granted=granted,
                findings=[
                    {
                        "path": f".rush/sessions/{name}.json",
                        "line": 0,
                        "column": 0,
                        "rule": "corrupt_checkpoint_journal",
                        "rule_id": "CORRUPT_CHECKPOINT_JOURNAL",
                        "severity": "error",
                        "message": f"Corrupt checkpoint journal '{name}' cannot be restored",
                        "fingerprint": (
                            digest
                            if len(digest) == 64
                            else hashlib.sha256(
                                (name or "").encode("utf-8")
                            ).hexdigest()
                        ),
                        "evidence": digest,
                    }
                ],
            )
        handoff_receipt = self._restore_handoff_receipt(root, data)
        return self._result(
            started,
            "ok",
            f"Restored session checkpoint '{name}'.",
            operation="restore",
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
    ) -> ToolResult | ToolResultV1:
        return pack_context(
            started,
            project_root,
            context_path,
            target_symbol,
            token_budget,
            granted,
            as_v1=self._as_v1,
        )

    def _context_retrieve(
        self,
        started: float,
        root: Path,
        handle: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return retrieve_context(started, root, handle, granted, as_v1=self._as_v1)

    def _coordination_check(
        self,
        started: float,
        root: Path,
        coordination_path: str | None,
        agent_id: str | None,
        max_age_s: float,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return check_coordination(
            started,
            root,
            coordination_path,
            agent_id,
            max_age_s,
            granted,
            as_v1=self._as_v1,
        )

    def _coordination_merge_preview(
        self,
        started: float,
        base_code: str | None,
        ours_code: str | None,
        theirs_code: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return preview_merge(
            started, base_code, ours_code, theirs_code, granted, as_v1=self._as_v1
        )

    def _coordination_recovery(
        self,
        started: float,
        root: Path,
        session_id: str | None,
        failure_fingerprint: Any,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return recover_coordination(
            started,
            root,
            session_id,
            failure_fingerprint,
            granted,
            as_v1=self._as_v1,
        )

    def _provider_resume(
        self,
        started: float,
        root: Path,
        name: str | None,
        provider_id: str | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return resume_provider(
            started, root, name, provider_id, granted, as_v1=self._as_v1
        )

    def _omniroute_resume(
        self,
        started: float,
        handoff: dict[str, Any],
        granted: ExecutionPermissions,
        required: ExecutionPermissions,
    ) -> ToolResult | ToolResultV1:
        return resume_omniroute(started, handoff, granted, required, as_v1=self._as_v1)

    def _provider_handoff(self, root: Path, name: str | None) -> dict[str, Any] | None:
        return provider_handoff(root, name)

    @staticmethod
    def _windows_cmd_command(
        executable: str,
        command: list[str],
        prompt: str,
        environment: dict[str, str] | None = None,
    ) -> tuple[list[str], dict[str, str]]:
        return windows_cmd_command(executable, command, prompt, environment)

    @staticmethod
    def _provider_command(
        provider: str, handoff: dict[str, Any]
    ) -> tuple[str, list[str]]:
        return provider_command(provider, handoff)

    @staticmethod
    def _provider_prompt(handoff: dict[str, Any]) -> str:
        return provider_prompt(handoff)

    @staticmethod
    def _save_handoff_receipt(
        project_root: Path, handoff: dict[str, Any]
    ) -> dict[str, Any]:
        return save_receipt(project_root, handoff)

    @staticmethod
    def _restore_handoff_receipt(
        project_root: Path, checkpoint: dict[str, Any]
    ) -> dict[str, Any]:
        return restore_receipt(project_root, checkpoint)

    @staticmethod
    def _valid_name(name: str | None) -> bool:
        return valid_name(name)

    def _result(
        self,
        started: float,
        status: Literal["ok", "error", "skipped", "warn", "fail"],
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
        provider_route: dict[str, Any] | None = None,
        findings: list[Finding] | None = None,
        as_v1: bool | None = None,
    ) -> ToolResult | ToolResultV1:
        effective_v1 = as_v1 if as_v1 is not None else getattr(self, "_as_v1", False)
        return build_continuity_result(
            started,
            status,
            summary,
            operation=operation,
            granted=granted,
            requested=requested,
            raw=raw,
            artifacts=artifacts,
            handoff=handoff,
            context_envelope=context_envelope,
            coordination=coordination,
            provider_route=provider_route,
            findings=findings,
            as_v1=effective_v1,
            tool_name=self.name,
        )
