"""ScanTool -- single result-contract entry point over full-project scans.

Phase 65 P65-04 (F34-35). Wraps `rush.workflows.project_run` so CLI, MCP, and
TUI share one scan plan/run/status implementation, mirroring
`rush.tools.project.ProjectTool`'s canonical envelope (`handle_request` ->
`ToolResult.raw={"schema_version":1,"operation":...,"data":...,"error":...}`,
plan §6.1) and its cursor-auth pattern (`ensure_cursor_key` +
`list_projects_page`) as the template for this tool's own paginated `status`
operation.

`run`/`__call__` remain the existing flat-kwarg entry points; `run` requires
explicit cache-write and artifact-write permission -- a scan `run` persists
an immutable run manifest under project storage, the same write gate
`ProjectTool` uses for a project mutation.

CLI (`rush scan --project <id-or-path> --full`) / MCP (`rush_scan`) wiring is
out of this task's allowed files, following the same split P65-03 used for
`ProjectTool` (T204/T097/T015; see that class's own docstring). `cancel` and
`resume` are not registered here -- they belong to P65-08 (progress/
cancellation/restart recovery) per the plan's own execution order and
per-packet ownership (§5, §6.4). Registering them ahead of that packet's
real behavior would be a permissive stub that pretends to cancel/resume
without doing so.

`rescan` (P65-06.3, plan §6.1: `rush_scan.rescan(project,run_id)`) dispatches
to `rush.workflows.project_run.rescan_project_run`, already implemented and
tested by T212; it is reachable only through `handle_request` (the MCP
envelope) -- the CLI's `scan rescan` subcommand calls
`rescan_project_run` directly (see `cli.py`'s own comment on that command).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from rush.permissions import ExecutionPermissions, check_permissions
from rush.workflows.project_run import (
    ScanError,
    ScanInvalidRequestError,
    ScanPlanStaleError,
    execute_scan,
    load_run_manifest,
    load_scan_plan,
    plan_scan,
    rescan_project_run,
)
from rush.workflows.projects import ProjectError, ensure_cursor_key, resolve_project

from .base import Finding, ToolFn, ToolResult, ToolStatus

ScanAction = Literal["plan", "run", "status"]

_WRITE_PERMISSION = ExecutionPermissions(cache_write=True, artifact_write=True)

_PERMISSION_FIELDS = frozenset(
    {
        "allow_network",
        "allow_download",
        "allow_cache_write",
        "allow_build",
        "allow_slow",
        "allow_artifact_write",
        "allow_browser",
    }
)

_REQUEST_FIELDS: dict[str, frozenset[str]] = {
    "plan": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "full",
            "exclude",
            "targets",
            "severity",
            "concurrency",
            "timeout_seconds",
        }
    ),
    "run": frozenset(
        {"schema_version", "operation", "project", "plan_id", "install"}
        | _PERMISSION_FIELDS
    ),
    "status": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "run_id",
            "after_sequence",
            "limit",
            "cursor",
        }
    ),
    "rescan": frozenset(
        {"schema_version", "operation", "project", "run_id"} | _PERMISSION_FIELDS
    ),
}


class ScanTool(ToolFn):
    """Plan, execute, and report a full-project scan through one contract."""

    name = "scan"

    @property
    def mcp_description(self) -> str:
        return (
            "Full-project scan at <path>. action=plan|run|status|rescan. Returns "
            "{status, findings[], summary, raw}. `run`/`rescan` require explicit "
            "cache-write and artifact-write permission; status='skipped' "
            "means denied."
        )

    def __call__(
        self,
        path: str = ".",
        action: ScanAction = "plan",
        plan_id: str | None = None,
        run_id: str | None = None,
        exclude: tuple[str, ...] = (),
        targets: dict[str, Any] | None = None,
        severity: str = "warn",
        concurrency: int = 2,
        timeout_seconds: int = 300,
        limit: int = 50,
        cursor: str | None = None,
        allow_cache_write: bool = False,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            Path(path),
            action=action,
            plan_id=plan_id,
            run_id=run_id,
            exclude=exclude,
            targets=targets,
            severity=severity,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            limit=limit,
            cursor=cursor,
            permissions=ExecutionPermissions(
                cache_write=allow_cache_write, artifact_write=allow_artifact_write
            ),
        )

    def run(
        self,
        path: Path,
        *,
        action: ScanAction = "plan",
        plan_id: str | None = None,
        run_id: str | None = None,
        exclude: tuple[str, ...] = (),
        targets: dict[str, Any] | None = None,
        severity: str = "warn",
        concurrency: int = 2,
        timeout_seconds: int = 300,
        limit: int = 50,
        cursor: str | None = None,
        permissions: ExecutionPermissions | None = None,
        data_root: Path | None = None,
    ) -> ToolResult:
        started = monotonic()
        granted = permissions or ExecutionPermissions()

        if action == "run":
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started, "skipped", f"scan run requires {', '.join(missing)}."
                )

        try:
            raw = self._dispatch(
                action,
                path=path,
                plan_id=plan_id,
                run_id=run_id,
                exclude=exclude,
                targets=targets,
                severity=severity,
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
                limit=limit,
                cursor=cursor,
                permissions=granted,
                data_root=data_root,
            )
        except ScanError as exc:
            return self._result(started, "error", f"scan {action}: {exc}")
        except ValueError as exc:
            return self._result(started, "error", f"scan {action}: {exc}")

        return self._result(started, "ok", f"scan {action}: ok", raw=raw)

    def _dispatch(
        self,
        action: ScanAction,
        *,
        path: Path,
        plan_id: str | None,
        run_id: str | None,
        exclude: tuple[str, ...] | None,
        targets: dict[str, Any] | None,
        severity: str,
        concurrency: int,
        timeout_seconds: int,
        limit: int,
        cursor: str | None,
        permissions: ExecutionPermissions,
        data_root: Path | None,
    ) -> Any:
        if action == "plan":
            plan = plan_scan(
                path,
                exclude=tuple(exclude or ()),
                targets=targets,
                severity=severity,
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
                data_root=data_root,
            )
            return plan.to_dict()

        if action == "run":
            if not plan_id:
                raise ScanInvalidRequestError("run requires plan_id")
            record = resolve_project(path, data_root=data_root)
            staged = load_scan_plan(Path(record["root"]), plan_id)
            if staged is None:
                raise ScanPlanStaleError(f"unknown or stale plan_id: {plan_id}")
            run = execute_scan(staged, permissions=permissions, data_root=data_root)
            return run.to_dict()

        if action == "status":
            if not run_id:
                raise ScanInvalidRequestError("status requires run_id")
            record = resolve_project(path, data_root=data_root)
            root = Path(record["root"])
            manifest = load_run_manifest(root, run_id)
            if manifest is None:
                raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
            return _paginate_status(
                data_root=data_root,
                project_id=record["project_id"],
                run_id=run_id,
                manifest=manifest,
                limit=limit,
                cursor=cursor,
            )

        raise ValueError(f"unknown scan action: {action}")

    def handle_request(self, request: dict[str, Any]) -> ToolResult:
        """Canonical envelope call boundary (plan §6.1), mirroring
        `ProjectTool.handle_request`. `request` is the sole input:
        `{"schema_version": 1, "operation": ..., <operation fields>}`."""
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

        granted = _permissions_from_request(request)
        if operation in ("run", "rescan"):
            _check_scope(_WRITE_PERMISSION, granted)

        if operation == "plan":
            plan = plan_scan(
                project,
                exclude=tuple(request.get("exclude") or ()),
                targets=request.get("targets"),
                severity=request.get("severity", "warn"),
                concurrency=int(request.get("concurrency", 2)),
                timeout_seconds=int(request.get("timeout_seconds", 300)),
            )
            return plan.to_dict()

        if operation == "run":
            plan_id = request.get("plan_id")
            if not plan_id:
                raise ScanInvalidRequestError("run requires plan_id")
            record = resolve_project(project)
            staged = load_scan_plan(Path(record["root"]), plan_id)
            if staged is None:
                raise ScanPlanStaleError(f"unknown or stale plan_id: {plan_id}")
            run = execute_scan(staged, permissions=granted)
            return run.to_dict()

        if operation == "status":
            run_id = request.get("run_id")
            if not run_id:
                raise ScanInvalidRequestError("status requires run_id")
            record = resolve_project(project)
            root = Path(record["root"])
            manifest = load_run_manifest(root, run_id)
            if manifest is None:
                raise ScanInvalidRequestError(f"unknown run_id: {run_id}")
            return _paginate_status(
                data_root=None,
                project_id=record["project_id"],
                run_id=run_id,
                manifest=manifest,
                limit=request.get("limit", 50),
                cursor=request.get("cursor"),
            )

        if operation == "rescan":
            run_id = request.get("run_id")
            if not run_id:
                raise ScanInvalidRequestError("rescan requires run_id")
            return rescan_project_run(project, run_id, permissions=granted)

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
            f"scan {operation}: ok" if error is None else f"scan {operation}: {error}"
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


def _permissions_from_request(request: dict[str, Any]) -> ExecutionPermissions:
    return ExecutionPermissions(
        **{
            field.removeprefix("allow_"): bool(request.get(field, False))
            for field in _PERMISSION_FIELDS
        }
    )


def _check_scope(required: ExecutionPermissions, granted: ExecutionPermissions) -> None:
    allowed, missing = check_permissions(required, granted)
    if not allowed:
        raise _ScopeDenied(f"missing permission(s): {', '.join(missing)}")


class _ScopeDenied(ScanError):
    code = "SCOPE_DENIED"


# --- `status` pagination -----------------------------------------------------
# Mirrors `rush.workflows.projects.list_projects_page`'s mandatory HMAC-signed
# cursor (plan §6.1) over the run's own scheduled-candidate list, keyed by the
# same `cursor.key` `ensure_cursor_key` creates during authorized global
# setup. Not a second envelope/cursor mechanism -- the identical algorithm,
# applied to scan run children instead of project registry rows.


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encode_status_cursor(key: bytes, payload: dict[str, Any]) -> str:
    payload_bytes = _canonical_json(payload)
    signature = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def _decode_status_cursor(key: bytes, cursor: str) -> dict[str, Any] | None:
    if "." not in cursor:
        return None
    payload_part, _, sig_part = cursor.partition(".")
    try:
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(sig_part)
    except (ValueError, Exception):  # noqa: BLE001 - any malformed base64 rejects
        return None
    expected = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(payload_bytes)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


class ScanInvalidCursorError(ScanError):
    code = "INVALID_CURSOR"


def _paginate_status(
    *,
    data_root: Path | None,
    project_id: str,
    run_id: str,
    manifest: dict[str, Any],
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 200):
        raise ScanInvalidRequestError("limit must be an integer in 1..200")

    key = ensure_cursor_key(data_root)
    query_hash = hashlib.sha256(
        _canonical_json({"project_id": project_id, "run_id": run_id, "limit": limit})
    ).hexdigest()

    items = sorted(
        manifest.get("scheduled") or [], key=lambda item: str(item.get("candidate_id"))
    )

    after: str | None = None
    if cursor is not None:
        payload = _decode_status_cursor(key, cursor)
        if (
            payload is None
            or payload.get("schema_version") != 1
            or payload.get("query_hash") != query_hash
        ):
            raise ScanInvalidCursorError("cursor is stale or does not match this query")
        after = payload.get("last_id")
        if not isinstance(after, str):
            raise ScanInvalidCursorError("cursor payload is malformed")
        items = [item for item in items if str(item.get("candidate_id")) > after]

    page = items[:limit]
    has_more = len(items) > limit

    next_cursor: str | None = None
    if has_more:
        next_cursor = _encode_status_cursor(
            key,
            {
                "schema_version": 1,
                "query_hash": query_hash,
                "last_id": str(page[-1].get("candidate_id")),
            },
        )

    return {
        "run_state": manifest.get("run_state"),
        "totals": manifest.get("totals"),
        "scheduled": page,
        "next_cursor": next_cursor,
    }


__all__ = ["ScanTool"]
