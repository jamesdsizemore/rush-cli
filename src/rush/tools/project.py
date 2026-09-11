"""ProjectTool -- single result-contract entry point over the project registry.

Phase 65 P65-03 (F32-33). Wraps `rush.workflows.projects` so CLI, MCP, and
TUI share one project add/list/show/select/configure/create/relink
implementation. `list`/`show` are read-only; every mutating action requires
explicit cache-write permission, matching the rest of the workflow tools.

`handle_request` is the canonical dict-in/envelope-out call boundary from
plan §6.1: `request={"schema_version":1,"operation":...,...}` in,
`ToolResult.raw={"schema_version":1,"operation":...,"data":...,"error":...}`
out. `run`/`__call__` remain the existing flat-kwarg entry points used by the
frozen `cli.py`/`mcp.py` wiring (their raw shape is unchanged) -- exposing
`expected_revision`/`plan_id`/`apply` as CLI flags is out of this task's
allowed files; see the T014 receipt.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from rush.permissions import ExecutionPermissions, check_permissions
from rush.workflows.projects import (
    ProjectError,
    ProjectInvalidRequestError,
    configure_project,
    create_project,
    list_project_artifacts,
    list_projects,
    project_snapshot,
    register_project,
    relink_project,
    resolve_active_project,
    resolve_project,
    select_project,
)

from .base import Finding, ToolFn, ToolResult, ToolStatus

ProjectAction = Literal[
    "add",
    "list",
    "show",
    "select",
    "configure",
    "create",
    "relink",
    "snapshot",
    "artifacts",
]

_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)
_ARTIFACT_WRITE_PERMISSION = ExecutionPermissions(cache_write=True, artifact_write=True)
_WRITE_ACTIONS = frozenset({"add", "create", "select", "configure", "relink"})
_ARTIFACT_WRITE_ACTIONS = frozenset({"add", "create", "relink"})

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
    "list": frozenset({"schema_version", "operation", "limit", "cursor"}),
    "add": frozenset(
        {"schema_version", "operation", "path", "name"} | _PERMISSION_FIELDS
    ),
    "show": frozenset({"schema_version", "operation", "project", "session_id"}),
    "select": frozenset({"schema_version", "operation", "project", "session_id"}),
    "create": frozenset(
        {"schema_version", "operation", "parent", "name", "git_init"}
        | _PERMISSION_FIELDS
    ),
    "relink": frozenset(
        {"schema_version", "operation", "project", "path", "expected_revision"}
        | _PERMISSION_FIELDS
    ),
    "configure": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "settings",
            "expected_revision",
            "apply",
            "plan_id",
        }
        | _PERMISSION_FIELDS
    ),
    "snapshot": frozenset({"schema_version", "operation", "project", "session_id"}),
    "artifacts": frozenset(
        {
            "schema_version",
            "operation",
            "project",
            "session_id",
            "categories",
            "limit",
            "offset",
        }
    ),
}

# `project` is only ID-or-path resolvable for `show`; select/relink/configure
# bind a project by its UUID only (plan §6.1: malformed UUID -> INVALID_REQUEST
# before any effect).
_UUID_ONLY_PROJECT_OPS = frozenset({"select", "relink", "configure"})


class ProjectTool(ToolFn):
    """Register, discover, and configure Rush projects through one contract."""

    name = "project"

    @property
    def mcp_description(self) -> str:
        return (
            "Manage Rush project registration at <path>. action="
            "add|list|show|select|configure|create|relink. Returns "
            "{status, findings[], summary, raw}. Mutating actions require "
            "explicit cache-write permission; status='skipped' means denied."
        )

    def __call__(
        self,
        path: str = ".",
        action: ProjectAction = "list",
        name: str | None = None,
        parent: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        init_git: bool = False,
        settings: dict[str, Any] | None = None,
        allow_cache_write: bool = False,
    ) -> ToolResult:
        return self.run(
            Path(path),
            action=action,
            name=name,
            parent=parent,
            project_id=project_id,
            session_id=session_id,
            init_git=init_git,
            settings=settings,
            permissions=ExecutionPermissions(cache_write=allow_cache_write),
        )

    def run(
        self,
        path: Path,
        *,
        action: ProjectAction = "list",
        name: str | None = None,
        parent: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        init_git: bool = False,
        settings: dict[str, Any] | None = None,
        expected_revision: int | None = None,
        apply: bool = False,
        plan_id: str | None = None,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        started = monotonic()
        granted = permissions or ExecutionPermissions()

        if action in _WRITE_ACTIONS and (action != "configure" or apply):
            required = (
                _ARTIFACT_WRITE_PERMISSION
                if action in _ARTIFACT_WRITE_ACTIONS or action == "configure"
                else _WRITE_PERMISSION
            )
            allowed, missing = check_permissions(required, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"project {action} requires {', '.join(missing)}.",
                )

        try:
            raw = self._dispatch(
                action,
                path=path,
                name=name,
                parent=parent,
                project_id=project_id,
                session_id=session_id,
                init_git=init_git,
                settings=settings,
                expected_revision=expected_revision,
                apply=apply,
                plan_id=plan_id,
            )
        except ProjectError as exc:
            return self._result(started, "error", f"project {action}: {exc}")
        except ValueError as exc:
            return self._result(started, "error", f"project {action}: {exc}")

        return self._result(started, "ok", f"project {action}: ok", raw=raw)

    def _dispatch(
        self,
        action: ProjectAction,
        *,
        path: Path,
        name: str | None,
        parent: str | None,
        project_id: str | None,
        session_id: str | None,
        init_git: bool,
        settings: dict[str, Any] | None,
        expected_revision: int | None = None,
        apply: bool = False,
        plan_id: str | None = None,
    ) -> Any:
        if action == "list":
            return {"projects": list_projects()}
        if action == "show":
            return resolve_project(project_id or path)
        if action == "add":
            record = register_project(path, name=name)
            return resolve_project(record.project_id)
        if action == "create":
            if not name:
                raise ValueError("create requires name")
            record = create_project(
                Path(parent) if parent else path, name, init_git=init_git
            )
            return resolve_project(record.project_id)
        if action == "select":
            if not project_id or not session_id:
                raise ValueError("select requires project_id and session_id")
            return select_project(session_id, project_id)
        if action == "configure":
            if not project_id:
                raise ValueError("configure requires project_id")
            return configure_project(
                project_id,
                settings,
                expected_revision=expected_revision,
                apply=apply,
                plan_id=plan_id,
            )
        if action == "relink":
            if not project_id:
                raise ValueError("relink requires project_id")
            if expected_revision is None:
                raise ValueError("relink requires expected_revision")
            return relink_project(project_id, path, expected_revision=expected_revision)
        raise ValueError(f"unknown project action: {action}")

    def handle_request(
        self, request: dict[str, Any], *, lock_timeout: float = 5.0
    ) -> ToolResult:
        """Canonical envelope call boundary (plan §6.1).

        `request` is the sole input: `{"schema_version": 1, "operation": ...,
        <operation fields>}`. Unknown top-level keys, a malformed UUID `project`
        for select/relink/configure, and out-of-range bounds are rejected with
        INVALID_REQUEST before any effect.
        """
        started = monotonic()
        operation = request.get("operation") if isinstance(request, dict) else None

        try:
            data = self._handle_request_unsafe(request, lock_timeout=lock_timeout)
        except ProjectError as exc:
            return self._envelope_result(
                started, str(operation), status="error", error=exc
            )
        except _ScopeDenied as denied:
            return self._envelope_result(
                started, str(operation), status="skipped", error=denied
            )

        return self._envelope_result(started, str(operation), status="ok", data=data)

    def _handle_request_unsafe(
        self, request: dict[str, Any], *, lock_timeout: float
    ) -> Any:
        if not isinstance(request, dict):
            raise ProjectInvalidRequestError("request must be an object")
        if request.get("schema_version") != 1:
            raise ProjectInvalidRequestError("schema_version must be 1")

        operation = request.get("operation")
        allowed_fields = (
            _REQUEST_FIELDS.get(operation) if isinstance(operation, str) else None
        )
        if allowed_fields is None:
            raise ProjectInvalidRequestError(f"unknown operation: {operation!r}")

        unknown_keys = set(request) - allowed_fields
        if unknown_keys:
            raise ProjectInvalidRequestError(
                f"unknown request field(s): {sorted(unknown_keys)}"
            )

        project = request.get("project")
        if operation in _UUID_ONLY_PROJECT_OPS and project is not None:
            _require_valid_uuid(project)

        granted = ExecutionPermissions(
            **{
                field.removeprefix("allow_"): bool(request.get(field, False))
                for field in _PERMISSION_FIELDS
            }
        )

        if operation in _ARTIFACT_WRITE_ACTIONS or (
            operation == "configure" and request.get("apply", False)
        ):
            _check_scope(_ARTIFACT_WRITE_PERMISSION, granted)
        elif operation == "select":
            _check_scope(_WRITE_PERMISSION, granted)

        if operation == "list":
            limit = request.get("limit", 50)
            cursor = request.get("cursor")
            from rush.workflows.projects import list_projects_page

            return list_projects_page(limit=limit, cursor=cursor)
        if operation == "show":
            return resolve_active_project(project, session_id=request.get("session_id"))
        if operation == "snapshot":
            active = resolve_active_project(
                project, session_id=request.get("session_id")
            )
            return project_snapshot(active["project_id"])
        if operation == "artifacts":
            categories = request.get("categories")
            if categories is not None and (
                not isinstance(categories, list)
                or not all(isinstance(c, str) for c in categories)
            ):
                raise ProjectInvalidRequestError("categories must be a list of strings")
            limit = request.get("limit", 100)
            offset = request.get("offset", 0)
            _require_int_in_range(limit, "limit", minimum=1, maximum=1000)
            _require_int_in_range(offset, "offset", minimum=0)
            active = resolve_active_project(
                project, session_id=request.get("session_id")
            )
            payload = list_project_artifacts(active["project_id"])
            return _filter_artifacts(
                payload, categories=categories, limit=limit, offset=offset
            )
        if operation == "select":
            session_id = request.get("session_id")
            if not project or not session_id:
                raise ProjectInvalidRequestError(
                    "select requires project and session_id"
                )
            return select_project(session_id, project)
        if operation == "add":
            path = request.get("path")
            if not path:
                raise ProjectInvalidRequestError("add requires path")
            record = register_project(path, name=request.get("name"))
            return resolve_project(record.project_id)
        if operation == "create":
            parent = request.get("parent")
            name = request.get("name")
            if not parent or not name:
                raise ProjectInvalidRequestError("create requires parent and name")
            record = create_project(
                parent, name, init_git=bool(request.get("git_init", False))
            )
            return resolve_project(record.project_id)
        if operation == "relink":
            path = request.get("path")
            expected_revision = request.get("expected_revision")
            if not project or not path or expected_revision is None:
                raise ProjectInvalidRequestError(
                    "relink requires project, path, and expected_revision"
                )
            _require_int_in_range(expected_revision, "expected_revision", minimum=0)
            return relink_project(
                project,
                path,
                expected_revision=expected_revision,
                lock_timeout=lock_timeout,
            )
        if operation == "configure":
            if not project:
                raise ProjectInvalidRequestError("configure requires project")
            expected_revision = request.get("expected_revision")
            if expected_revision is not None:
                _require_int_in_range(expected_revision, "expected_revision", minimum=0)
            return configure_project(
                project,
                request.get("settings"),
                expected_revision=expected_revision,
                apply=bool(request.get("apply", False)),
                plan_id=request.get("plan_id"),
                lock_timeout=lock_timeout,
            )
        raise ProjectInvalidRequestError(f"unknown operation: {operation!r}")

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
            f"project {operation}: ok"
            if error is None
            else f"project {operation}: {error}"
        )
        return self._result(started, status, summary, raw=raw)

    def _result(
        self,
        started: float,
        status: ToolStatus,
        summary: str,
        *,
        raw: Any = None,
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


class _ScopeDenied(Exception):
    code = "SCOPE_DENIED"
    retryable = False


def _check_scope(required: ExecutionPermissions, granted: ExecutionPermissions) -> None:
    allowed, missing = check_permissions(required, granted)
    if not allowed:
        raise _ScopeDenied(f"missing permission(s): {', '.join(missing)}")


def _require_valid_uuid(value: Any) -> None:
    if not isinstance(value, str):
        raise ProjectInvalidRequestError("project must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProjectInvalidRequestError(f"malformed UUID: {value!r}") from exc
    if parsed.version != 4:
        raise ProjectInvalidRequestError(f"malformed UUID (not v4): {value!r}")


def _require_int_in_range(
    value: Any, field: str, *, minimum: int, maximum: int | None = None
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProjectInvalidRequestError(f"{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ProjectInvalidRequestError(f"{field} out of range")


def _filter_artifacts(
    payload: dict[str, Any],
    *,
    categories: list[str] | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """P65-07.3: project-scoped filter/pagination over `list_project_artifacts`'s three
    categorized reference lists. `categories` (when given) keeps only items whose
    `category` field matches; `limit`/`offset` then slice each filtered list
    independently -- never merges the three kinds into one ambiguous cursor."""

    def _select(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if categories is not None:
            items = [item for item in items if item.get("category") in categories]
        return items[offset : offset + limit]

    return {
        "project_id": payload["project_id"],
        "scan_outputs": _select(payload["scan_outputs"]),
        "handoffs": _select(payload["handoffs"]),
        "memory": _select(payload["memory"]),
    }


__all__ = ["ProjectTool"]
