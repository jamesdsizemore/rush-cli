"""ScanHandoffTool -- bounded agent handoff over one scan run (F35).

Phase 65 P65-06. Mirrors `rush.tools.scan.ScanTool`'s canonical envelope
(`handle_request` -> `ToolResult.raw={"schema_version":1,"operation":...,
"data":...,"error":...}`, plan §6.1) exactly, over
`rush.workflows.project_run`'s `build_handoff`/`dispatch_handoff`/
`status_handoff`/`acknowledge_handoff`/`complete_handoff` -- the plan §6.1
`rush_scan_handoff` operation row: `prepare(project,run_id,agent_id,
finding_ids=[],max_tokens=2048,max_bytes=8192)`; `dispatch(project,
handoff_id,session_capability)`; `status(project,handoff_id)`; `acknowledge(
project,handoff_id,delivery_nonce)`; `complete(project,handoff_id,
delivery_nonce,artifact_ids=[])`.

CLI (`rush scan handoff <run-id> --agent <id>`) / MCP (`rush_scan_handoff`)
wiring follows the same split P65-03/P65-04 used for `ProjectTool`/
`ScanTool`. `rescan` is NOT an action on this tool: the plan's own frozen
table (§6.1) places `rescan(project,run_id)` on `rush_scan`/`ScanTool`
(`src/rush/tools/scan.py`), which is outside this packet's allowed files
(that file's own docstring already anticipates P65-06 adding it: "`rescan`
... belong[s] to ... P65-06"). `rush.workflows.project_run.rescan_project_run`
implements the real re-execute-and-compare behavior and is wired into the
`rush scan rescan <run-id>` CLI subcommand directly; its `rush_scan.rescan`
MCP counterpart is a disclosed gap pending a follow-up task with
`src/rush/tools/scan.py` in its allowed files.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Literal

from rush.permissions import ExecutionPermissions, check_permissions
from rush.workflows.project_run import (
    ScanError,
    ScanInvalidRequestError,
    acknowledge_handoff,
    build_handoff,
    complete_handoff,
    dispatch_handoff,
    status_handoff,
)
from rush.workflows.projects import ProjectError

from .base import Finding, ToolFn, ToolResult, ToolStatus

ScanHandoffAction = Literal["prepare", "dispatch", "status", "acknowledge", "complete"]

_WRITE_PERMISSION = ExecutionPermissions(cache_write=True, artifact_write=True)

_REQUEST_FIELDS: dict[str, frozenset[str]] = {
    "prepare": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "run_id",
            "agent_id",
            "finding_ids",
            "max_tokens",
            "max_bytes",
            "acceptance_checks",
            "granted_actions",
        }
    ),
    "dispatch": frozenset(
        {"schema_version", "operation", "project", "handoff_id", "session_capability"}
    ),
    "status": frozenset({"schema_version", "operation", "project", "handoff_id"}),
    "acknowledge": frozenset(
        {"schema_version", "operation", "project", "handoff_id", "delivery_nonce"}
    ),
    "complete": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "handoff_id",
            "delivery_nonce",
            "artifact_ids",
        }
    ),
}

_WRITE_OPERATIONS = frozenset({"prepare", "dispatch", "acknowledge", "complete"})


class ScanHandoffTool(ToolFn):
    """Prepare, dispatch, and acknowledge a bounded agent handoff (F35)."""

    name = "scan-handoff"

    @property
    def mcp_description(self) -> str:
        return (
            "Bounded agent handoff over a scan run. action=prepare|dispatch|"
            "status|acknowledge|complete. Returns {status, findings[], "
            "summary, raw}. prepare/dispatch/acknowledge/complete require "
            "explicit cache-write and artifact-write permission; "
            "status='skipped' means denied. Never marks a finding verified -- "
            "only a rescan comparison can."
        )

    def __call__(
        self,
        path: str = ".",
        action: ScanHandoffAction = "status",
        run_id: str | None = None,
        agent_id: str | None = None,
        handoff_id: str | None = None,
        finding_ids: tuple[str, ...] = (),
        max_tokens: int = 2048,
        max_bytes: int = 8192,
        acceptance_checks: tuple[str, ...] = (),
        granted_actions: tuple[str, ...] = (),
        session_capability: str | None = None,
        delivery_nonce: str | None = None,
        artifact_ids: tuple[str, ...] = (),
        allow_cache_write: bool = False,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            Path(path),
            action=action,
            run_id=run_id,
            agent_id=agent_id,
            handoff_id=handoff_id,
            finding_ids=finding_ids,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            acceptance_checks=acceptance_checks,
            granted_actions=granted_actions,
            session_capability=session_capability,
            delivery_nonce=delivery_nonce,
            artifact_ids=artifact_ids,
            permissions=ExecutionPermissions(
                cache_write=allow_cache_write, artifact_write=allow_artifact_write
            ),
        )

    def run(
        self,
        path: Path,
        *,
        action: ScanHandoffAction = "status",
        run_id: str | None = None,
        agent_id: str | None = None,
        handoff_id: str | None = None,
        finding_ids: tuple[str, ...] = (),
        max_tokens: int = 2048,
        max_bytes: int = 8192,
        acceptance_checks: tuple[str, ...] = (),
        granted_actions: tuple[str, ...] = (),
        session_capability: str | None = None,
        delivery_nonce: str | None = None,
        artifact_ids: tuple[str, ...] = (),
        permissions: ExecutionPermissions | None = None,
        data_root: Path | None = None,
    ) -> ToolResult:
        started = monotonic()
        granted = permissions or ExecutionPermissions()

        if action in _WRITE_OPERATIONS:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"scan-handoff {action} requires {', '.join(missing)}.",
                )

        try:
            raw = self._dispatch(
                action,
                path=path,
                run_id=run_id,
                agent_id=agent_id,
                handoff_id=handoff_id,
                finding_ids=finding_ids,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                acceptance_checks=acceptance_checks,
                granted_actions=granted_actions,
                session_capability=session_capability,
                delivery_nonce=delivery_nonce,
                artifact_ids=artifact_ids,
                data_root=data_root,
            )
        except ScanError as exc:
            return self._result(started, "error", f"scan-handoff {action}: {exc}")
        except ValueError as exc:
            return self._result(started, "error", f"scan-handoff {action}: {exc}")

        return self._result(started, "ok", f"scan-handoff {action}: ok", raw=raw)

    def _dispatch(
        self,
        action: ScanHandoffAction,
        *,
        path: Path,
        run_id: str | None,
        agent_id: str | None,
        handoff_id: str | None,
        finding_ids: tuple[str, ...],
        max_tokens: int,
        max_bytes: int,
        acceptance_checks: tuple[str, ...],
        granted_actions: tuple[str, ...],
        session_capability: str | None,
        delivery_nonce: str | None,
        artifact_ids: tuple[str, ...],
        data_root: Path | None,
    ) -> Any:
        if action == "prepare":
            if not run_id:
                raise ScanInvalidRequestError("prepare requires run_id")
            if not agent_id:
                raise ScanInvalidRequestError("prepare requires agent_id")
            handoff = build_handoff(
                path,
                run_id,
                agent_id,
                finding_ids=tuple(finding_ids or ()),
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                acceptance_checks=tuple(acceptance_checks or ()),
                granted_actions=tuple(granted_actions or ()),
                data_root=data_root,
            )
            return handoff.to_dict()

        if action == "dispatch":
            if not handoff_id:
                raise ScanInvalidRequestError("dispatch requires handoff_id")
            if not session_capability:
                raise ScanInvalidRequestError("dispatch requires session_capability")
            handoff = dispatch_handoff(
                path, handoff_id, session_capability, data_root=data_root
            )
            return status_handoff(path, handoff.handoff_id, data_root=data_root)

        if action == "status":
            if not handoff_id:
                raise ScanInvalidRequestError("status requires handoff_id")
            return status_handoff(path, handoff_id, data_root=data_root)

        if action == "acknowledge":
            if not handoff_id:
                raise ScanInvalidRequestError("acknowledge requires handoff_id")
            if not delivery_nonce:
                raise ScanInvalidRequestError("acknowledge requires delivery_nonce")
            handoff = acknowledge_handoff(
                path, handoff_id, delivery_nonce, data_root=data_root
            )
            return status_handoff(path, handoff.handoff_id, data_root=data_root)

        if action == "complete":
            if not handoff_id:
                raise ScanInvalidRequestError("complete requires handoff_id")
            if not delivery_nonce:
                raise ScanInvalidRequestError("complete requires delivery_nonce")
            handoff = complete_handoff(
                path,
                handoff_id,
                delivery_nonce,
                artifact_ids=tuple(artifact_ids or ()),
                data_root=data_root,
            )
            return status_handoff(path, handoff.handoff_id, data_root=data_root)

        raise ValueError(f"unknown scan-handoff action: {action}")

    def handle_request(self, request: dict[str, Any]) -> ToolResult:
        """Canonical envelope call boundary (plan §6.1), mirroring
        `ScanTool.handle_request`. `request` is the sole input."""
        started = monotonic()
        operation = request.get("operation") if isinstance(request, dict) else None

        try:
            data = self._handle_request_unsafe(request)
        except ScanError as exc:
            return self._envelope_result(
                started, str(operation), status="error", error=exc
            )
        except ProjectError as exc:
            return self._envelope_result(
                started, str(operation), status="error", error=exc
            )

        return self._envelope_result(started, str(operation), status="ok", data=data)

    def _handle_request_unsafe(self, request: dict[str, Any]) -> Any:
        if not isinstance(request, dict):
            raise ScanInvalidRequestError("request must be an object")
        if request.get("schema_version") != 1:
            raise ScanInvalidRequestError("schema_version must be 1")

        operation = request.get("operation")
        allowed_fields = (
            _REQUEST_FIELDS.get(operation) if isinstance(operation, str) else None
        )
        if allowed_fields is None:
            raise ScanInvalidRequestError(f"unknown operation: {operation!r}")

        unknown_keys = set(request) - allowed_fields
        if unknown_keys:
            raise ScanInvalidRequestError(
                f"unknown request field(s): {sorted(unknown_keys)}"
            )

        project = request.get("project")
        if not project:
            raise ScanInvalidRequestError(f"{operation} requires project")

        if operation == "prepare":
            run_id = request.get("run_id")
            agent_id = request.get("agent_id")
            if not run_id:
                raise ScanInvalidRequestError("prepare requires run_id")
            if not agent_id:
                raise ScanInvalidRequestError("prepare requires agent_id")
            handoff = build_handoff(
                project,
                run_id,
                agent_id,
                finding_ids=tuple(request.get("finding_ids") or ()),
                max_tokens=int(request.get("max_tokens", 2048)),
                max_bytes=int(request.get("max_bytes", 8192)),
                acceptance_checks=tuple(request.get("acceptance_checks") or ()),
                granted_actions=tuple(request.get("granted_actions") or ()),
            )
            return handoff.to_dict()

        if operation == "dispatch":
            handoff_id = request.get("handoff_id")
            session_capability = request.get("session_capability")
            if not handoff_id:
                raise ScanInvalidRequestError("dispatch requires handoff_id")
            if not session_capability:
                raise ScanInvalidRequestError("dispatch requires session_capability")
            handoff = dispatch_handoff(project, handoff_id, session_capability)
            return status_handoff(project, handoff.handoff_id)

        if operation == "status":
            handoff_id = request.get("handoff_id")
            if not handoff_id:
                raise ScanInvalidRequestError("status requires handoff_id")
            return status_handoff(project, handoff_id)

        if operation == "acknowledge":
            handoff_id = request.get("handoff_id")
            delivery_nonce = request.get("delivery_nonce")
            if not handoff_id:
                raise ScanInvalidRequestError("acknowledge requires handoff_id")
            if not delivery_nonce:
                raise ScanInvalidRequestError("acknowledge requires delivery_nonce")
            handoff = acknowledge_handoff(project, handoff_id, delivery_nonce)
            return status_handoff(project, handoff.handoff_id)

        if operation == "complete":
            handoff_id = request.get("handoff_id")
            delivery_nonce = request.get("delivery_nonce")
            if not handoff_id:
                raise ScanInvalidRequestError("complete requires handoff_id")
            if not delivery_nonce:
                raise ScanInvalidRequestError("complete requires delivery_nonce")
            handoff = complete_handoff(
                project,
                handoff_id,
                delivery_nonce,
                artifact_ids=tuple(request.get("artifact_ids") or ()),
            )
            return status_handoff(project, handoff.handoff_id)

        raise ScanInvalidRequestError(f"unknown operation: {operation!r}")

    def _envelope_result(
        self,
        started: float,
        operation: str,
        *,
        status: ToolStatus,
        data: Any = None,
        error: Exception | None = None,
    ) -> ToolResult:
        error_payload: dict[str, Any] | None = None
        if error is not None:
            code = getattr(error, "code", "INVALID_REQUEST")
            retryable = bool(getattr(error, "retryable", False))
            error_payload = {
                "code": code,
                "message": str(error),
                "retryable": retryable,
            }
        raw = {
            "schema_version": 1,
            "operation": operation,
            "data": data,
            "error": error_payload,
        }
        summary = (
            f"scan-handoff {operation}: ok"
            if error is None
            else f"scan-handoff {operation}: {error}"
        )
        return self._result(started, status, summary, raw=raw)

    def _result(
        self, started: float, status: ToolStatus, summary: str, *, raw: Any = None
    ) -> ToolResult:
        findings: list[Finding] = []
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=int((monotonic() - started) * 1000),
            summary=summary,
            findings=findings,
            raw=raw,
        )


__all__ = ["ScanHandoffTool"]
