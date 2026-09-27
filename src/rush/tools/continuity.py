"""Shared session-continuity tool used by the CLI and MCP transports."""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any, Literal, cast

from ..continuity.context import pack_context, retrieve_context, retrieve_result_view
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
    ContinuityOutput,
    ContinuityResult,
    build_continuity_result,
    valid_name,
)
from ..contracts.results import ToolResultV1
from ..invocation.models import AmbiguousRootError, InvocationError
from ..invocation.targets import RootSelection, select_root
from ..io.physical_paths import ContainmentError, PhysicalRoot
from ..memory.checkpoint_journal import CheckpointJournal
from ..memory.store import (
    MemoryStoreUnreadableError,
    collect_committed_writes,
    collect_memory_reads,
)
from ..permissions import (
    ExecutionPermissions,
    check_permissions,
)
from .base import Finding, ToolFn, ToolResult
from .routing import attach_memory_attribution, memory_block, memory_receipt

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


def state_location(path: Path, project_id: str | None = None) -> tuple[Path, Path]:
    """T10 (R10.1): `(root, base)`. `root` is the logical root that owns this
    call's `.rush` state, never `Path.resolve()` of the given path (a file target
    would become the "root"). `base` is the root-relative directory `path` names
    (its parent for a file), so path-relative arguments keep their meaning.

    1. The ambient `current_invocation_root()` of the executing invocation, when
       `path` lies within it (walked by the T8 no-follow `select_root`).
    2. Else a registered `project_id` (it also serves as the declared root on
       MCP); an unregistered value stays pure telemetry attribution.
    3. Else the T8 logical root of `path`: the deepest marked or registered
       directory on its walk, else the deepest existing directory.
    """
    from ..invocation.executor import current_invocation_root
    from ..invocation.targets import registered_root_index, route_project_reference
    from ..workflows.projects import ProjectNotFoundError, ProjectRootMissingError

    anchor = Path.cwd()
    index = registered_root_index()
    ambient = current_invocation_root()
    if ambient is not None:
        within = _within(path, ambient, anchor, index)
        if within is not None:
            return within
    if project_id:
        try:
            _, registered = route_project_reference(
                project_id, anchor=anchor, index=index
            )
        except ProjectNotFoundError:
            pass
        else:
            if not registered.is_dir():
                raise ProjectRootMissingError(
                    f"registered project root is missing: {registered}"
                )
            return _within(path, registered, anchor, index) or (registered, Path("."))
    return _location(select_root(path, anchor=anchor, index=index))


def _within(
    path: Path, declared: Path, anchor: Path, index: Mapping[str, str]
) -> tuple[Path, Path] | None:
    try:
        return _location(
            select_root(path, anchor=anchor, declared_root=declared, index=index)
        )
    except AmbiguousRootError:
        return None


def _location(selection: RootSelection) -> tuple[Path, Path]:
    base = selection.relative
    if selection.target.is_file():
        base = base.parent
    return selection.root, base


def _rebase(base: Path, value: str | None) -> str | None:
    """A `path`-relative argument re-expressed relative to the logical root."""
    if not value or os.path.isabs(value) or base == Path("."):
        return value
    return (base / value).as_posix()


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
        project_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        view: Literal["result", "bytes"] | None = None,
        cursor: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        max_bytes: int | None = None,
    ) -> ToolResult | ToolResultV1:
        result = self.run(
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
            project_id=project_id,
            run_id=run_id,
            session_id=session_id,
            view=view,
            cursor=cursor,
            offset=offset,
            limit=limit,
            max_bytes=max_bytes,
        )
        # FastMCP needs schema-bearing public types; ContinuityResult is the
        # exact legacy ToolResult dictionary with retained conversion methods.
        return cast(ToolResult | ToolResultV1, result)

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
        idempotency_key: str | None = None,
        # M11: public invocation boundary, mirroring `MemoryTool.run`'s own
        # `project_id`/`run_id`/`agent_id`/`session_id` -- pure caller-supplied
        # attribution, threaded unchanged into `pack_context`/`retrieve_context`'s
        # telemetry writes, never invented from `path` (a filesystem path is not
        # a registered project UUID).
        project_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        # T16 §3 item 10: result/bytes views of a stored compact result.
        view: str | None = None,
        cursor: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        max_bytes: int | None = None,
    ) -> ContinuityOutput:
        del config
        self._result_view = {
            "view": view,
            "cursor": cursor,
            "offset": offset,
            "limit": limit,
            "max_bytes": max_bytes,
        }
        self._as_v1 = as_v1
        # P69-07 subsection e: one real per-call identity minted before dispatch, shared
        # by every operation in `dispatch_table` below -- never re-minted per branch. A
        # caller-supplied `idempotency_key` (a genuine retry of this exact call) reuses
        # that same identity instead of minting a new one, so a real retry still dedupes.
        self._invocation_id = idempotency_key or str(uuid.uuid4())
        started = monotonic()
        granted = permissions or ExecutionPermissions()

        if operation not in VALID_OPERATIONS:
            return self._result(
                started,
                "error",
                f"Unsupported session operation: {operation}.",
                operation=operation,
                granted=granted,
            )
        from ..workflows.projects import ProjectError

        try:
            root, base = state_location(path, project_id)
        except (InvocationError, ProjectError, ValueError) as exc:
            return self._result(
                started,
                "error",
                f"Session state root could not be resolved: {exc}",
                operation=operation,
                granted=granted,
            )

        handoff = {**(handoff or {}), "target_provider": provider_id}
        context_path = _rebase(base, context_path)
        coordination_path = _rebase(base, coordination_path)

        dispatch_table = {
            "context_pack": lambda: self._context_pack(
                started,
                root,
                context_path,
                target_symbol,
                token_budget,
                granted,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
            ),
            "context_retrieve": lambda: self._context_retrieve(
                started,
                root,
                context_handle,
                granted,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
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
    ) -> ContinuityOutput:
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
        with collect_committed_writes() as committed:
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
            memory=memory_block(
                written=[
                    memory_receipt(w["id"], w["revision"], w["source"], "checkpoint")
                    for w in committed
                ]
            ),
        )

    def _run_list(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
    ) -> ContinuityOutput:
        # T10 (finding 3): JSON first, then `memory.db` read-only, whether or not
        # `.rush/sessions` exists; `list_checkpoints` never creates anything.
        try:
            with collect_memory_reads() as reads:
                sessions = CheckpointJournal(root).list_checkpoints()
        except MemoryStoreUnreadableError as exc:
            return self._result(
                started,
                "error",
                f"Session checkpoint store is unreadable ({exc.code}): {exc}",
                operation="list",
                granted=granted,
            )
        except ContainmentError:
            return self._result(
                started,
                "error",
                "Session checkpoint path failed physical containment validation.",
                operation="list",
                granted=granted,
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
            memory=memory_block(
                used=[
                    memory_receipt(r["id"], r["revision"], r["source"], "list")
                    for r in reads
                ]
            ),
        )

    def _run_restore(
        self,
        started: float,
        root: Path,
        name: str | None,
        granted: ExecutionPermissions,
    ) -> ContinuityOutput:
        if not self._valid_name(name):
            return self._result(
                started,
                "error",
                "Session checkpoint names must be a single filename.",
                operation="restore",
                granted=granted,
            )
        try:
            # T19: a restore served by the migrated-store fallback reads (and
            # returns) one checkpoint artifact; a JSON-file restore reads none.
            with collect_memory_reads() as reads:
                data = CheckpointJournal(root).restore_checkpoint(name or "")
        except MemoryStoreUnreadableError as exc:
            return self._result(
                started,
                "error",
                f"Session checkpoint store is unreadable ({exc.code}): {exc}",
                operation="restore",
                granted=granted,
            )
        except ContainmentError:
            return self._result(
                started,
                "error",
                "Session checkpoint path failed physical containment validation.",
                operation="restore",
                granted=granted,
            )
        if data is None:
            # CheckpointJournal.restore_checkpoint() is the sole existence authority (its physical
            # `.json` file may already be renamed `.migrated` by migration.migrate_checkpoint_journal(),
            # in which case a store-backed checkpoint would already have been returned above). Only
            # consult the physical file here to distinguish "never existed" (skipped) from "corrupt
            # bytes on disk" (error), never to gate existence itself.
            physical_root = PhysicalRoot(root)
            session_rel = Path(".rush") / "sessions" / f"{name}.json"
            migrated_rel = Path(".rush") / "sessions" / f"{name}.json.migrated"
            try:
                session_file = physical_root.open_contained(session_rel, purpose="read")
                migrated_file = physical_root.open_contained(
                    migrated_rel, purpose="read"
                )
                evidence_file = (
                    session_file
                    if session_file.exists()
                    else (migrated_file if migrated_file.exists() else None)
                )
            except ContainmentError:
                return self._result(
                    started,
                    "error",
                    "Session checkpoint path failed physical containment validation.",
                    operation="restore",
                    granted=granted,
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
                evidence_file = physical_root.open_contained(
                    evidence_file.relative_to(root), purpose="read"
                )
                raw_bytes = evidence_file.read_bytes()
                digest = hashlib.sha256(raw_bytes).hexdigest()
            except ContainmentError:
                return self._result(
                    started,
                    "error",
                    "Session checkpoint path failed physical containment validation.",
                    operation="restore",
                    granted=granted,
                )
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
            memory=memory_block(
                used=[
                    memory_receipt(r["id"], r["revision"], r["source"], "restore")
                    for r in reads
                ]
            ),
        )

    def _context_pack(
        self,
        started: float,
        project_root: Path,
        context_path: str | None,
        target_symbol: str,
        token_budget: int,
        granted: ExecutionPermissions,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> ContinuityOutput:
        return pack_context(
            started,
            project_root,
            context_path,
            target_symbol,
            token_budget,
            granted,
            as_v1=self._as_v1,
            invocation_id=self._invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    def _context_retrieve(
        self,
        started: float,
        root: Path,
        handle: str | None,
        granted: ExecutionPermissions,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> ContinuityOutput:
        view = getattr(self, "_result_view", {})
        if view.get("view") is not None:
            # T16 S16.6: a view reads the stored compact result read-only;
            # no view keeps the legacy full retrieval below.
            return cast(
                ContinuityOutput,
                retrieve_result_view(root, handle or "", **view),
            )
        return retrieve_context(
            started,
            root,
            handle,
            granted,
            as_v1=self._as_v1,
            invocation_id=self._invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
        )

    def _coordination_check(
        self,
        started: float,
        root: Path,
        coordination_path: str | None,
        agent_id: str | None,
        max_age_s: float,
        granted: ExecutionPermissions,
    ) -> ContinuityOutput:
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
    ) -> ContinuityOutput:
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
    ) -> ContinuityOutput:
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
    ) -> ContinuityOutput:
        # T19: a checkpoint served from the migrated store is a real read.
        with collect_memory_reads() as reads:
            result = resume_provider(
                started, root, name, provider_id, granted, as_v1=self._as_v1
            )
        return cast(
            ContinuityOutput,
            attach_memory_attribution(
                result,
                memory_block(
                    used=[
                        memory_receipt(
                            r["id"], r["revision"], r["source"], "provider_resume"
                        )
                        for r in reads
                    ]
                ),
            ),
        )

    def _omniroute_resume(
        self,
        started: float,
        handoff: dict[str, Any],
        granted: ExecutionPermissions,
        required: ExecutionPermissions,
    ) -> ContinuityOutput:
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
        memory: dict[str, Any] | None = None,
    ) -> ContinuityOutput:
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
            memory=memory,
        )
