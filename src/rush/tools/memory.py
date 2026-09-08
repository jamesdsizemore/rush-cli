"""Cross-tool memory query/write tool used by the CLI and MCP transports (Phase 61 P61.12)."""

from __future__ import annotations

import dataclasses
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from ..memory.maintenance import MaintenanceTask, run_maintenance_cycle
from ..memory.store import (
    MemoryArtifact,
    MemoryFamily,
    MemorySubject,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
)
from ..memory.trust import default_entry_tier, evaluate_promotion
from ..permissions import ExecutionPermissions, check_permissions
from .base import ToolFn, ToolResult

MemoryOperation = Literal["ask", "write", "promote", "list", "recall", "maintain"]
SourceKind = Literal["local_tool", "cross_tool_handoff", "human_derived"]

VALID_OPERATIONS = {"ask", "write", "promote", "list", "recall", "maintain"}
_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)

# Subject -> family mapping (Phase 61 §6.1): active_context/handoff rows, episodic/experience
# rows, preference/failure/architectural_decision/domain_knowledge/memory rows, skill_pattern/skill rows.
_SUBJECT_FAMILY: dict[str, MemoryFamily] = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}


def _family_for_subject(subject: MemorySubject) -> MemoryFamily:
    return _SUBJECT_FAMILY.get(subject, "memory")


class _MemoryResult(dict):
    """Dict-shaped `ToolResult`, matching every other `ALL_TOOLS` member (`ContinuityResult`
    precedent in `continuity/results.py`). `to_dict()` is a self-return escape hatch for
    `cli.py`'s memory command handlers, which call `result.to_dict()` unconditionally."""

    def to_dict(self) -> dict[str, Any]:
        return dict(self)


class MemoryTool(ToolFn):
    """Query, write, and promote cross-LLM memory artifacts through one result contract."""

    name = "memory"

    @property
    def mcp_description(self) -> str:
        return (
            "Query, write, or promote a cross-tool memory artifact in the typed artifact "
            "store. Returns {status, findings[], summary}; write/promote require explicit "
            "cache-write permission."
        )

    def __call__(
        self,
        path: Path,
        operation: MemoryOperation = "ask",
        subject: MemorySubject | None = None,
        query: str = "",
        session_allowlist: list[str] | None = None,
        content: dict[str, Any] | None = None,
        source: str = "",
        symbol_ref: str | None = None,
        source_kind: SourceKind = "local_tool",
        user_stated: bool = False,
        candidate_sources: list[str] | None = None,
        task: MaintenanceTask | None = None,
        batch_size: int = 500,
        allow_cache_write: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            operation=operation,
            subject=subject,
            query=query,
            session_allowlist=session_allowlist,
            content=content,
            source=source,
            symbol_ref=symbol_ref,
            source_kind=source_kind,
            user_stated=user_stated,
            candidate_sources=candidate_sources,
            task=task,
            batch_size=batch_size,
            permissions=ExecutionPermissions(cache_write=allow_cache_write),
        )

    def run(
        self,
        path: Path,
        *,
        operation: MemoryOperation = "ask",
        subject: MemorySubject | None = None,
        query: str = "",
        session_allowlist: list[str] | None = None,
        content: dict[str, Any] | None = None,
        source: str = "",
        symbol_ref: str | None = None,
        source_kind: SourceKind = "local_tool",
        user_stated: bool = False,
        candidate_sources: list[str] | None = None,
        task: MaintenanceTask | None = None,
        batch_size: int = 500,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        started = time.monotonic()
        root = Path(path).resolve()
        granted = permissions or ExecutionPermissions()

        if operation not in VALID_OPERATIONS:
            return self._result(
                started,
                "error",
                f"Unsupported memory operation: {operation}.",
                operation=str(operation),
            )

        dispatch_table = {
            "ask": lambda: self._query(
                started, root, subject, query, session_allowlist, "ask"
            ),
            "recall": lambda: self._query(
                started, root, subject, query, session_allowlist, "recall"
            ),
            "list": lambda: self._list(started, root, subject, query),
            "write": lambda: self._run_write(
                started,
                root,
                subject,
                content,
                source,
                symbol_ref,
                source_kind,
                granted,
            ),
            "promote": lambda: self._run_promote(
                started,
                root,
                subject,
                content,
                source,
                symbol_ref,
                source_kind,
                user_stated,
                candidate_sources,
                granted,
            ),
            "maintain": lambda: self._run_maintain(started, task, batch_size),
        }
        return dispatch_table[operation]()

    def _query(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        query: str,
        session_allowlist: list[str] | None,
        operation: str,
    ) -> ToolResult:
        if not subject or not query:
            return self._result(
                started,
                "error",
                f"memory {operation} requires subject and query.",
                operation=operation,
            )
        if not session_allowlist:
            return self._result(
                started,
                "skipped",
                f"memory {operation} requires a non-empty session_allowlist "
                "(fail-closed, no default cross-session access).",
                operation=operation,
            )
        store = TypedArtifactStore(root)
        try:
            artifacts = store.recall(subject, query, session_allowlist)
        except (SignatureMismatchError, TrojanSourceFoundError) as exc:
            return self._result(started, "error", str(exc), operation=operation)
        return self._result(
            started,
            "ok",
            f"Found {len(artifacts)} memory artifact(s) for '{query}'.",
            operation=operation,
            raw=[self._artifact_dict(a) for a in artifacts],
        )

    def _list(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        query: str,
    ) -> ToolResult:
        if not subject or not query:
            return self._result(
                started,
                "error",
                "memory list requires subject and query.",
                operation="list",
            )
        store = TypedArtifactStore(root)
        artifacts = store.search(subject, query)
        return self._result(
            started,
            "ok",
            f"Listed {len(artifacts)} memory artifact(s) for '{query}'.",
            operation="list",
            raw=[self._artifact_dict(a) for a in artifacts],
        )

    def _run_write(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        content: dict[str, Any] | None,
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Memory write requires {', '.join(missing)}.",
                operation="write",
            )
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory write requires subject, content, and source.",
                operation="write",
            )
        store = TypedArtifactStore(root)
        stored = store.write(
            self._build_artifact(subject, content, source, symbol_ref, source_kind)
        )
        return self._result(
            started,
            "ok",
            f"Wrote memory artifact to subject '{subject}'.",
            operation="write",
            raw=self._artifact_dict(stored),
        )

    def _run_promote(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        content: dict[str, Any] | None,
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
        user_stated: bool,
        candidate_sources: list[str] | None,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Memory promote requires {', '.join(missing)}.",
                operation="promote",
            )
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory promote requires subject, content, and source.",
                operation="promote",
            )
        artifact = self._build_artifact(
            subject, content, source, symbol_ref, source_kind
        )
        decision = evaluate_promotion(
            artifact,
            user_stated=user_stated,
            candidate_sources=candidate_sources,
            project_root=root,
        )
        store = TypedArtifactStore(root)
        stored = store.write(artifact)
        summary = (
            f"Promotion approved for subject '{subject}' "
            "(STATED-tier persistence pending — no store API elevates a stored row to "
            "STATED yet; the underlying candidate is persisted at its entry trust tier)."
            if decision.promoted
            else f"Promotion denied for subject '{subject}': {decision.denial_reason}."
        )
        return self._result(
            started,
            "ok",
            summary,
            operation="promote",
            raw={
                "promoted": decision.promoted,
                "new_tier": decision.new_tier,
                "denial_reason": decision.denial_reason,
                "corroboration_count": decision.corroboration_count,
                "artifact": self._artifact_dict(stored),
            },
        )

    def _run_maintain(
        self,
        started: float,
        task: MaintenanceTask | None,
        batch_size: int,
    ) -> ToolResult:
        if task is None:
            return self._result(
                started,
                "error",
                "memory maintain requires task.",
                operation="maintain",
            )
        result = run_maintenance_cycle(task, batch_size=batch_size)
        return self._result(
            started,
            "ok",
            f"Maintenance cycle '{task}' processed {result.processed} row(s), "
            f"changed {result.changed}.",
            operation="maintain",
            raw=dataclasses.asdict(result),
        )

    @staticmethod
    def _build_artifact(
        subject: MemorySubject,
        content: dict[str, Any],
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
    ) -> MemoryArtifact:
        return MemoryArtifact(
            id=str(uuid.uuid4()),
            family=_family_for_subject(subject),
            subject=subject,
            trust_tier=default_entry_tier(source_kind),
            content=content,
            source=source,
            created_at=time.time(),
            symbol_ref=symbol_ref,
        )

    @staticmethod
    def _artifact_dict(artifact: MemoryArtifact) -> dict[str, Any]:
        return dataclasses.asdict(artifact)

    def _result(
        self,
        started: float,
        status: Literal["ok", "warn", "fail", "error", "skipped"],
        summary: str,
        *,
        operation: str,
        raw: Any = None,
    ) -> ToolResult:
        return _MemoryResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            summary=summary,
            findings=[],
            raw=raw,
            metadata={"operation": operation},
        )
