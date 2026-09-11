"""Authenticated in-memory ephemeral dashboard HTTP server."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import uuid
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, get_args
from urllib.parse import parse_qs, urlparse

from rush.dashboard.auth import DashboardAuth
from rush.dashboard.project_map import build_project_map, expand_group
from rush.dashboard.state import MutationLedger, ProjectRegistry, ScanRunTracker
from rush.dashboard.static_assets import (
    BOOTSTRAP_HTML_TEMPLATE,
    BOOTSTRAP_JS,
    DASHBOARD_CSS,
    DASHBOARD_HTML_TEMPLATE,
    load_dashboard_asset,
)
from rush.dashboard.theme import MOTION, THEME
from rush.memory.store import MemorySubject, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.token_economy.telemetry import TelemetryStore
from rush.tools.base import ToolResult
from rush.tools.memory import MemoryTool
from rush.tools.setup_wizard import run_setup_wizard
from rush.workflows.project_run import (
    build_handoff,
    cancel_scan_run,
    compare_runs,
    dispatch_handoff,
    execute_scan,
    load_run_manifest,
    load_scan_plan,
    plan_scan,
    rescan_project_run,
    resume_scan_run,
    status_handoff,
)
from rush.workflows.projects import (
    ProjectError,
    ProjectInvalidRequestError,
    create_project,
    expand_artifact_reference,
    export_project_data,
    list_project_artifacts,
    project_git_commit_diff,
    project_git_history,
    project_snapshot,
    register_project,
    resolve_project,
)

_IN_MEMORY_ASSETS: dict[str, bytes] = {}


def init_in_memory_assets() -> dict[str, bytes]:
    """Initialize in-memory cached assets."""
    _IN_MEMORY_ASSETS["index.html"] = DASHBOARD_HTML_TEMPLATE.encode("utf-8")
    return _IN_MEMORY_ASSETS


class AuthenticatedDashboardHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for ephemeral authenticated dashboard."""

    auth_token: ClassVar[str] = ""
    cached_results: ClassVar[list[ToolResult]] = []

    def log_message(self, format: str, *args) -> None:
        """Suppress default stderr logging."""

    def do_GET(self) -> None:
        # 1. DNS Rebinding check
        host = self.headers.get("Host", "")
        if not (host.startswith(("127.0.0.1", "localhost"))):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Host header")
            return

        # 2. Origin / CSRF check
        origin = self.headers.get("Origin")
        if origin and not (origin.startswith(("http://127.0.0.1", "http://localhost"))):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Invalid Origin")
            return

        # 3. Auth Token check
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        token_in_query = query.get("token", [None])[0]
        token_in_header = self.headers.get("X-Rush-Auth")

        token = token_in_header or token_in_query
        if not token or token != self.auth_token:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Missing or invalid token")
            return

        # 4. Routing
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/findings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            data = [
                {
                    "tool": r["tool"],
                    "status": r["status"],
                    "summary": r["summary"],
                    "findings_count": len(r["findings"]),
                }
                for r in self.cached_results
            ]
            self.wfile.write(json.dumps(data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def launch_dashboard(
    results: list[ToolResult], port: int = 0, host: str = "127.0.0.1"
) -> tuple[HTTPServer, str]:
    """Initialize assets, generate ephemeral token, and start HTTP server bound to IPv4 loopback."""
    init_in_memory_assets()
    token = secrets.token_urlsafe(32)

    handler = AuthenticatedDashboardHandler
    handler.auth_token = token
    handler.cached_results = results

    server = HTTPServer((host, port), handler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/?token={token}"
    return server, url


# --- Phase 66 P66-01: canonical authenticated per-server API ----------------
#
# create_dashboard_server builds a brand-new DashboardAuth/ProjectRegistry/
# MutationLedger and a brand-new request-handler *type* per call (via the
# _make_handler closure factory below) instead of setting ClassVar attributes
# on a single shared handler class. That is the fix for the legacy handler
# above sharing auth_token/cached_results across every instance: two
# concurrently-running servers each get their own handler class capturing
# their own DashboardContext by closure, so neither can observe or mutate the
# other's auth/session/project state.

MAX_HEADERS_BYTES = 16 * 1024
MAX_HEADER_FIELDS = 64
MAX_BODY_BYTES = 256 * 1024
SOCKET_TIMEOUT_SECONDS = 5

# P66-04: real dispatch to Phase 65's rush_scan/setup_wizard/rush_scan_handoff
# shared operations (see `_dispatch_scan_action` below). P66-05 adds the
# memory_* actions, dispatched through the exact same canonical `MemoryTool`
# edit/archive/delete/promote entry points the CLI/MCP use -- never a
# browser-only reimplementation or a direct SQLite write.
ALLOWED_ACTIONS = frozenset(
    {
        "noop",
        "provision_plan",
        "provision_apply",
        "scan_start",
        "scan_cancel",
        "scan_resume",
        "rescan",
        "handoff_preview",
        "handoff_send",
        "memory_edit",
        "memory_archive",
        "memory_delete",
        "memory_promote",
        "data_export",
    }
)

_MEMORY_SUBJECTS: tuple[MemorySubject, ...] = get_args(MemorySubject)
_MEMORY_SOURCE_KINDS = frozenset({"local_tool", "cross_tool_handoff", "human_derived"})


def _error_body(
    request_id: str,
    project_id: str | None,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "project_id": project_id,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": {},
            },
        }
    ).encode("utf-8")


def _success_body(
    request_id: str, project_id: str | None, sequence: int, data: Any
) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "project_id": project_id,
            "sequence": sequence,
            "data": data,
        }
    ).encode("utf-8")


class DashboardContext:
    """Per-server-instance state bundle: never a class attribute anywhere.

    Constructed fresh by create_dashboard_server() for every server, so two
    running servers can never share auth, sessions, project scope, or
    mutation identities.
    """

    def __init__(
        self, projects: dict[str, dict[str, Any]], *, bound_host: str, bound_port: int
    ) -> None:
        self.auth = DashboardAuth()
        self.projects = ProjectRegistry(projects)
        self.mutations = MutationLedger()
        self.scan_runs = ScanRunTracker()
        self.bound_host = bound_host
        self.bound_port = bound_port
        self.launch_origin = f"http://{bound_host}:{bound_port}"
        self.server_id = self.auth.server_id
        self.pid = os.getpid()
        self.start_nonce = uuid.uuid4().hex


# --- Phase 66 P66-04: full scan triage and repair controls -----------------
#
# Every branch below calls the exact same shared `rush.workflows.
# project_run`/`rush.tools.setup_wizard` functions the CLI uses for
# `rush scan ...`/setup -- never a browser-only reimplementation or a
# dynamic getattr/command-construction path (plan Sec 3.6).


class _ActionDenied(Exception):
    """Carries the exact HTTP status/error code for one denied/invalid
    action, raised from inside `_dispatch_scan_action` and converted to a
    response by its caller."""

    def __init__(
        self, status: int, code: str, message: str, *, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retryable = retryable


_CODE_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "PLAN_STALE": 409,
    "BUSY": 409,
    "RESUME_STALE": 409,
    "SOURCE_CHANGED": 409,
    "E_PERMISSION": 403,
    "INVALID_STATE": 409,
    "PROJECT_NOT_FOUND": 404,
    "PROJECT_DESTINATION_EXISTS": 409,
    "REVISION_CONFLICT": 409,
    "PROJECT_ROOT_CONFLICT": 409,
    "PROJECT_ROOT_MISSING": 400,
    "PROJECT_REQUIRED": 400,
    "SETUP_REQUIRED": 400,
    "INVALID_CURSOR": 400,
}


def _raise_from_project_error(exc: ProjectError) -> None:
    code = getattr(exc, "code", "INVALID_REQUEST")
    raise _ActionDenied(
        _CODE_STATUS.get(code, 400),
        code.lower(),
        str(exc),
        retryable=bool(getattr(exc, "retryable", False)),
    ) from exc


def _send_project_error(
    handler: Any, exc: ProjectError, request_id: str, project_id: str
) -> None:
    """GET-path counterpart to `_raise_from_project_error` -- `do_GET` has no
    `_ActionDenied` catch (that exists only around the POST .../actions
    dispatch), so a `ProjectError` from a snapshot section builder is sent
    directly instead of raised."""
    code = getattr(exc, "code", "INVALID_REQUEST")
    handler._send_error(
        _CODE_STATUS.get(code, 400),
        code.lower(),
        str(exc),
        request_id,
        project_id,
        retryable=bool(getattr(exc, "retryable", False)),
    )


def _permissions_from_grants(grants: dict[str, Any]) -> ExecutionPermissions:
    return ExecutionPermissions(
        network=bool(grants.get("network", False)),
        download=bool(grants.get("download", False)),
        cache_write=bool(grants.get("cache_write", False)),
        build=bool(grants.get("build", False)),
        slow=bool(grants.get("slow", False)),
        artifact_write=bool(grants.get("artifact_write", False)),
        browser=bool(grants.get("browser", False)),
    )


def _require_grants(grants: dict[str, Any], *names: str, operation: str) -> None:
    missing = [name for name in names if not grants.get(name)]
    if missing:
        raise _ActionDenied(
            403,
            "grant_denied",
            f"{operation} requires explicit {', '.join(missing)} grant(s)",
        )


def _scan_plan_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if "exclude" in arguments:
        kwargs["exclude"] = tuple(arguments["exclude"] or ())
    if "targets" in arguments:
        kwargs["targets"] = arguments["targets"]
    if "severity" in arguments:
        kwargs["severity"] = arguments["severity"]
    if "concurrency" in arguments:
        kwargs["concurrency"] = arguments["concurrency"]
    if "timeout_seconds" in arguments:
        kwargs["timeout_seconds"] = arguments["timeout_seconds"]
    return kwargs


def _dispatch_provision_plan(
    project_id: str, arguments: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """Read-only readiness/provision-plan review (plan Sec 3.1 Overview
    "readiness" + Sec 3.6 Scans review-before-start): a fresh, immutable
    `rush_scan.plan` (staged to disk by `plan_scan` itself) plus the
    approved shared `run_setup_wizard(install=True, permissions=None)`
    engine-provisioning preview -- never a browser-only planner."""
    root = Path(resolve_project(project_id)["root"])
    readiness = run_setup_wizard(root, install=True, permissions=None)
    plan = plan_scan(project_id, **_scan_plan_kwargs(arguments))
    return 200, {"readiness": readiness, "scan_plan": plan.to_dict()}


def _dispatch_provision_apply(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """Install action: calls the exact approved `run_setup_wizard`/
    `apply_provision_plan` shared plan -- no browser-specific package
    manager logic. Refuses to apply a plan that changed since it was
    reviewed (its content-hashed `plan_id` no longer matches)."""
    _require_grants(
        grants, "cache_write", "artifact_write", operation="provision_apply"
    )
    reviewed_plan_id = arguments.get("plan_id")
    if not isinstance(reviewed_plan_id, str) or not reviewed_plan_id:
        raise _ActionDenied(
            400,
            "malformed_request",
            "provision_apply requires arguments.plan_id from a reviewed readiness plan",
        )
    root = Path(resolve_project(project_id)["root"])
    fresh = run_setup_wizard(root, install=True, permissions=None)
    if fresh.get("plan_id") != reviewed_plan_id:
        raise _ActionDenied(
            409,
            "conflict",
            "provision plan changed since review; re-review before applying",
        )
    permissions = _permissions_from_grants(grants)
    applied = run_setup_wizard(
        root, install=True, permissions=permissions, project_id=project_id
    )
    return 200, {"provision": applied.get("provision", {})}


def _dispatch_scan_start(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Starts a full scan from an explicitly reviewed, currently-staged
    plan (never a silently recomputed one) on a background thread; a
    refresh/reconnect that calls scan_start again for the same project
    attaches to the already-running job instead of spawning a duplicate."""
    _require_grants(grants, "cache_write", "artifact_write", operation="scan_start")
    plan_id = arguments.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id:
        raise _ActionDenied(
            400,
            "malformed_request",
            "scan_start requires arguments.plan_id from a reviewed plan",
        )
    root = Path(resolve_project(project_id)["root"])
    staged_plan = load_scan_plan(root, plan_id)
    if staged_plan is None:
        raise _ActionDenied(
            409, "conflict", "plan_id is not a currently staged reviewed plan"
        )
    permissions = _permissions_from_grants(grants)
    run_id = str(uuid.uuid4())

    def _run() -> None:
        with suppress(Exception):
            execute_scan(staged_plan, run_id=run_id, permissions=permissions)

    thread = threading.Thread(target=_run, daemon=True)
    attached_run_id, attached_plan_id, started = ctx.scan_runs.start_or_attach(
        project_id, run_id=run_id, plan_id=plan_id, thread=thread
    )
    return 202, {
        "run_id": attached_run_id,
        "plan_id": attached_plan_id,
        "attached_to_existing": not started,
    }


def _dispatch_scan_cancel(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """Calls the exact shared `cancel_scan_run` cooperative marker -- the
    running job's own candidate loop stops at its next boundary and its
    already-executed candidates remain as real partial evidence."""
    _require_grants(grants, "cache_write", operation="scan_cancel")
    run_id = arguments.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise _ActionDenied(
            400, "malformed_request", "scan_cancel requires arguments.run_id"
        )
    payload = cancel_scan_run(project_id, run_id)
    return 202, {"run_id": run_id, "cancel_requested_at": payload["requested_at"]}


def _dispatch_scan_resume(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    _require_grants(grants, "cache_write", "artifact_write", operation="scan_resume")
    run_id = arguments.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise _ActionDenied(
            400, "malformed_request", "scan_resume requires arguments.run_id"
        )
    permissions = _permissions_from_grants(grants)

    def _run() -> None:
        with suppress(Exception):
            resume_scan_run(project_id, run_id, permissions=permissions)

    thread = threading.Thread(target=_run, daemon=True)
    attached_run_id, _plan_id, started = ctx.scan_runs.start_or_attach(
        project_id, run_id=run_id, plan_id="", thread=thread
    )
    return 202, {"run_id": attached_run_id, "attached_to_existing": not started}


def _dispatch_rescan(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Re-executes `run_id`'s own staged plan and compares the fresh run
    against it via the shared `rescan_project_run`/`compare_runs` -- the
    comparison itself is read back through the scans snapshot section
    (`compare_with=<run_id>`) once the background job completes."""
    _require_grants(grants, "cache_write", "artifact_write", operation="rescan")
    baseline_run_id = arguments.get("run_id")
    if not isinstance(baseline_run_id, str) or not baseline_run_id:
        raise _ActionDenied(
            400, "malformed_request", "rescan requires arguments.run_id"
        )
    permissions = _permissions_from_grants(grants)

    def _run() -> None:
        with suppress(Exception):
            rescan_project_run(project_id, baseline_run_id, permissions=permissions)

    thread = threading.Thread(target=_run, daemon=True)
    attached_run_id, _plan_id, started = ctx.scan_runs.start_or_attach(
        project_id, run_id=baseline_run_id, plan_id="", thread=thread
    )
    return 202, {
        "baseline_run_id": attached_run_id,
        "attached_to_existing": not started,
    }


def _dispatch_handoff_preview(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`rush_scan_handoff.prepare` (agent selection + bounded handoff
    preview): returns the immutable packet plus the one-time
    `session_capability` the browser must echo back to `handoff_send`."""
    _require_grants(
        grants, "cache_write", "artifact_write", operation="handoff_preview"
    )
    run_id = arguments.get("run_id")
    agent_id = arguments.get("agent_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(agent_id, str)
        or not agent_id
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "handoff_preview requires arguments.run_id and arguments.agent_id",
        )
    handoff = build_handoff(
        project_id,
        run_id,
        agent_id,
        finding_ids=tuple(arguments.get("finding_ids") or ()),
        max_tokens=int(arguments.get("max_tokens", 2048)),
        max_bytes=int(arguments.get("max_bytes", 8192)),
    )
    return 200, handoff.to_dict()


def _dispatch_handoff_send(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`rush_scan_handoff.dispatch` (delivery/read-back state): requires the
    exact `session_capability` a prior `handoff_preview` returned."""
    _require_grants(grants, "cache_write", "artifact_write", operation="handoff_send")
    handoff_id = arguments.get("handoff_id")
    session_capability = arguments.get("session_capability")
    if (
        not isinstance(handoff_id, str)
        or not handoff_id
        or not isinstance(session_capability, str)
        or not session_capability
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "handoff_send requires arguments.handoff_id and arguments.session_capability",
        )
    dispatch_handoff(project_id, handoff_id, session_capability)
    return 200, status_handoff(project_id, handoff_id)


# --- Phase 66 P66-05: memory administration mutations -----------------------
#
# Every branch below is a thin pass-through onto `MemoryTool().run()` --
# request-key validation, compare-and-swap version checks, and the
# apply=False/True preview-then-approve split all live in that one canonical
# dispatch (`rush.tools.memory`), never reimplemented or hand-rolled as a
# direct `TypedArtifactStore`/SQLite write here. `apply=True` additionally
# requires this dashboard's own `cache_write` grant *before* the call, so a
# denial is visible as a 403 at the action boundary, not only buried inside
# the tool's own envelope; a preview (`apply=False`, the default) never
# requires a grant and never mutates anything.


def _dispatch_memory_edit(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    if bool(arguments.get("apply")):
        _require_grants(grants, "cache_write", operation="memory_edit")
    root = Path(resolve_project(project_id)["root"])
    request: dict[str, Any] = {
        key: arguments[key]
        for key in ("scope", "id", "expected_version", "content", "apply")
        if key in arguments
    }
    result = MemoryTool().run(
        root,
        operation="edit",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    return 200, dict(result)


def _dispatch_memory_archive(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    if bool(arguments.get("apply")):
        _require_grants(grants, "cache_write", operation="memory_archive")
    root = Path(resolve_project(project_id)["root"])
    request: dict[str, Any] = {
        key: arguments[key]
        for key in ("scope", "id", "expected_version", "apply", "archived")
        if key in arguments
    }
    result = MemoryTool().run(
        root,
        operation="archive",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    return 200, dict(result)


def _dispatch_memory_delete(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """P65-07's batch delete, previewed then approved: `apply=False` (the
    default) returns exactly the candidate `affected` records and writes
    nothing; only an explicit `apply=True` with a `cache_write` grant removes
    exactly the `artifact_ids` given -- never a broader cross-project or
    cross-scope mass action."""
    if bool(arguments.get("apply")):
        _require_grants(grants, "cache_write", operation="memory_delete")
    root = Path(resolve_project(project_id)["root"])
    request: dict[str, Any] = {
        key: arguments[key]
        for key in ("artifact_ids", "expected_revisions", "scope", "apply")
        if key in arguments
    }
    result = MemoryTool().run(
        root,
        operation="delete",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    return 200, dict(result)


def _dispatch_memory_promote(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """Always requires `cache_write` -- unlike edit/archive/delete, `promote`
    has no read-only preview mode (it always writes a fresh candidate
    artifact and evaluates it for trust-tier promotion in one step, matching
    `MemoryTool`'s own `promote` CLI/MCP semantics)."""
    _require_grants(grants, "cache_write", operation="memory_promote")
    subject = arguments.get("subject")
    content = arguments.get("content")
    source = arguments.get("source")
    if (
        not isinstance(subject, str)
        or subject not in _MEMORY_SUBJECTS
        or not isinstance(content, dict)
        or not isinstance(source, str)
        or not source
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "memory_promote requires a valid subject, content, and source",
        )
    source_kind = arguments.get("source_kind", "local_tool")
    if source_kind not in _MEMORY_SOURCE_KINDS:
        raise _ActionDenied(400, "malformed_request", "invalid source_kind")
    candidate_sources = arguments.get("candidate_sources")
    if candidate_sources is not None and not (
        isinstance(candidate_sources, list)
        and all(isinstance(s, str) for s in candidate_sources)
    ):
        raise _ActionDenied(
            400, "malformed_request", "candidate_sources must be a list of strings"
        )
    root = Path(resolve_project(project_id)["root"])
    result = MemoryTool().run(
        root,
        operation="promote",
        subject=subject,
        content=content,
        source=source,
        symbol_ref=arguments.get("symbol_ref"),
        source_kind=source_kind,
        user_stated=bool(arguments.get("user_stated", False)),
        candidate_sources=candidate_sources,
        permissions=_permissions_from_grants(grants),
    )
    return 200, dict(result)


def _dispatch_scan_action(
    ctx: DashboardContext,
    project_id: str,
    operation: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        if operation == "provision_plan":
            return _dispatch_provision_plan(project_id, arguments)
        if operation == "provision_apply":
            return _dispatch_provision_apply(project_id, arguments, grants)
        if operation == "scan_start":
            return _dispatch_scan_start(ctx, project_id, arguments, grants)
        if operation == "scan_cancel":
            return _dispatch_scan_cancel(project_id, arguments, grants)
        if operation == "scan_resume":
            return _dispatch_scan_resume(ctx, project_id, arguments, grants)
        if operation == "rescan":
            return _dispatch_rescan(ctx, project_id, arguments, grants)
        if operation == "handoff_preview":
            return _dispatch_handoff_preview(project_id, arguments, grants)
        if operation == "handoff_send":
            return _dispatch_handoff_send(project_id, arguments, grants)
        if operation == "memory_edit":
            return _dispatch_memory_edit(project_id, arguments, grants)
        if operation == "memory_archive":
            return _dispatch_memory_archive(project_id, arguments, grants)
        if operation == "memory_delete":
            return _dispatch_memory_delete(project_id, arguments, grants)
        if operation == "memory_promote":
            return _dispatch_memory_promote(project_id, arguments, grants)
        if operation == "data_export":
            return _dispatch_data_export(project_id, grants)
    except ProjectError as exc:
        _raise_from_project_error(exc)
    raise _ActionDenied(400, "unknown_operation", f"unhandled operation: {operation}")


def _dispatch_data_export(
    project_id: str, grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """P66-06.3 per-project data export: the exact same redacted snapshot the
    Overview/Git/Artifacts sections already render, packaged as one
    downloadable document -- requires an explicit `download` grant (this is
    the one action here whose entire purpose is producing a file for the
    user to save off the local machine)."""
    _require_grants(grants, "download", operation="data_export")
    return 200, export_project_data(project_id)


# --- Phase 66 P66-04: scans snapshot section --------------------------------

_MAX_EXCERPT_LINES = 200
_MAX_EXCERPT_BYTES = 64 * 1024
_GROUP_KEYS = frozenset({"severity", "rule", "path"})


def _split_csv(values: list[str]) -> list[str]:
    return [v for entry in values for v in entry.split(",") if v]


def _decode_offset_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, UnicodeDecodeError):
        return 0


def _encode_offset_cursor(offset: int) -> str:
    return (
        base64.urlsafe_b64encode(str(offset).encode("ascii"))
        .decode("ascii")
        .rstrip("=")
    )


def _list_run_ids(root: Path) -> list[str]:
    runs_dir = root / ".rush" / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(p.name for p in runs_dir.iterdir() if p.is_dir())


def _run_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    totals = manifest.get("totals") or {}
    scheduled = manifest.get("scheduled") or []
    candidates = manifest.get("candidates") or []
    executed = sum(1 for item in scheduled if item.get("outcome") == "executed")
    blocked = sum(
        1
        for item in scheduled
        if item.get("outcome") in ("permission_blocked", "failed", "cancelled")
    )
    missing = sum(
        1 for item in scheduled if item.get("outcome") == "unavailable"
    ) + sum(1 for c in candidates if c.get("disposition") != "applicable")
    run_state = str(manifest.get("run_state") or "")
    outcome = {"completed": "clean", "cancelled": "cancelled"}.get(
        run_state, "incomplete"
    )
    return {
        "run_id": manifest.get("run_id"),
        "plan_id": manifest.get("plan_id"),
        "run_state": run_state,
        "created_at": manifest.get("created_at"),
        "executed_count": executed,
        "blocked_count": blocked,
        "missing_count": missing,
        "candidate_count": totals.get("candidate_count", len(candidates)),
        "finding_count": totals.get("finding_count", 0),
        "outcome": outcome,
    }


def _read_excerpt(root: Path, rel_path: str, *, start: int, end: int) -> dict[str, Any]:
    """Bounded, path-traversal-safe source excerpt (plan Sec 3.6: at most
    200 lines / 64KiB, explicit remaining-range control)."""
    try:
        target = (root / rel_path).resolve()
        target.relative_to(root.resolve())
    except (ValueError, OSError):
        return {"path": rel_path, "error": "invalid_path", "lines": []}
    if not target.is_file():
        return {"path": rel_path, "error": "not_found", "lines": []}
    start = max(1, start)
    end = max(start, min(end, start + _MAX_EXCERPT_LINES - 1))
    lines: list[str] = []
    total_bytes = 0
    truncated = False
    try:
        with target.open("r", encoding="utf-8", errors="replace") as handle:
            for lineno, line in enumerate(handle, start=1):
                if lineno < start:
                    continue
                if lineno > end:
                    break
                total_bytes += len(line.encode("utf-8"))
                if total_bytes > _MAX_EXCERPT_BYTES:
                    truncated = True
                    break
                lines.append(line.rstrip("\n"))
    except OSError:
        return {"path": rel_path, "error": "read_failed", "lines": []}
    return {
        "path": rel_path,
        "start": start,
        "end": (start + len(lines) - 1) if lines else start,
        "lines": lines,
        "truncated": truncated,
    }


def _build_scans_section(
    ctx: DashboardContext, project_id: str, query: dict[str, list[str]]
) -> dict[str, Any]:
    """`section=scans` (plan Sec 3.1): complete per-tool statuses, grouped
    findings with original provenance, filters, and handoff/rescan history.
    A finding is never dropped just because its owning engine didn't run in
    the *current* run -- when `compare_with` names a baseline run, every
    baseline finding stays visible (status `resolved`/`persisting`/
    `unverified`) alongside every current-only `new` finding."""
    root = Path(resolve_project(project_id)["root"])
    run_ids = _list_run_ids(root)
    manifests: list[dict[str, Any]] = []
    for run_id in run_ids:
        manifest = load_run_manifest(root, run_id)
        if manifest is not None:
            manifests.append(manifest)
    manifests.sort(key=lambda m: str(m.get("created_at") or ""))
    runs_summary = [_run_summary(m) for m in manifests]
    active_run_id = ctx.scan_runs.active_run_id(project_id)

    result: dict[str, Any] = {
        "runs": runs_summary,
        "active_run_id": active_run_id,
        "candidates": [],
        "findings": {"items": [], "next_cursor": None, "total": 0, "groups": None},
    }

    requested_run_id = query.get("run_id", [None])[0]
    if requested_run_id:
        manifest = next(
            (m for m in manifests if m.get("run_id") == requested_run_id), None
        )
    else:
        manifest = manifests[-1] if manifests else None
    if manifest is None:
        return result

    run_id = manifest["run_id"]
    result["candidates"] = manifest.get("candidates", [])
    result["run"] = _run_summary(manifest)

    compare_with = query.get("compare_with", [None])[0]
    current_findings_by_id = {
        str(f["finding_id"]): f
        for f in manifest.get("aggregate", {}).get("findings") or []
        if f.get("finding_id")
    }
    if compare_with:
        try:
            comparison = compare_runs(project_id, compare_with, run_id)
        except ProjectError:
            comparison = None
        if comparison is not None:
            baseline_manifest = next(
                (m for m in manifests if m.get("run_id") == compare_with), None
            ) or load_run_manifest(root, compare_with)
            baseline_findings_by_id = {
                str(f["finding_id"]): f
                for f in (baseline_manifest or {}).get("aggregate", {}).get("findings")
                or []
                if f.get("finding_id")
            }
            findings: list[dict[str, Any]] = []
            for finding_id, verdict in comparison["verdicts"].items():
                source = current_findings_by_id.get(
                    finding_id
                ) or baseline_findings_by_id.get(finding_id)
                if source is None:
                    continue
                item = dict(source)
                item["status"] = verdict
                findings.append(item)
        else:
            findings = [
                dict(f, status="current") for f in current_findings_by_id.values()
            ]
    else:
        findings = [dict(f, status="current") for f in current_findings_by_id.values()]

    severity_filter = set(_split_csv(query.get("severity", [])))
    status_filter = set(_split_csv(query.get("status", [])))
    rule_filter = set(_split_csv(query.get("rule", [])))
    path_filter = set(_split_csv(query.get("path", [])))
    if severity_filter:
        findings = [f for f in findings if f.get("severity") in severity_filter]
    if status_filter:
        findings = [f for f in findings if f.get("status") in status_filter]
    if rule_filter:
        findings = [
            f for f in findings if (f.get("rule") or f.get("rule_id")) in rule_filter
        ]
    if path_filter:
        findings = [f for f in findings if f.get("path") in path_filter]

    group_by = query.get("group_by", [None])[0]
    groups: dict[str, list[Any]] | None = None
    if group_by in _GROUP_KEYS:
        groups = {}
        for item in findings:
            key = str(
                item.get(group_by)
                or (item.get("rule_id") if group_by == "rule" else None)
                or "unknown"
            )
            groups.setdefault(key, []).append(item.get("finding_id"))

    cursor = query.get("cursor", [None])[0]
    try:
        limit = int(query.get("limit", ["50"])[0])
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 100))
    offset = _decode_offset_cursor(cursor)
    page = findings[offset : offset + limit]
    next_cursor = (
        _encode_offset_cursor(offset + limit)
        if offset + limit < len(findings)
        else None
    )

    result["findings"] = {
        "items": page,
        "next_cursor": next_cursor,
        "total": len(findings),
        "groups": groups,
    }

    excerpt_path = query.get("excerpt_path", [None])[0]
    if excerpt_path:
        result["excerpt"] = _read_excerpt(
            root,
            excerpt_path,
            start=int(query.get("excerpt_start", ["1"])[0]),
            end=int(query.get("excerpt_end", ["200"])[0]),
        )
    return result


# --- Phase 66 P66-05: memory administration snapshot section ----------------
#
# Reads only ever go through `TypedArtifactStore`'s existing public read
# methods (`list_artifact_refs`/`scope_artifacts`) or `MemoryTool`'s own
# `list`/`expand`/`related` dispatch -- never a hand-rolled SQL query.


def _all_known_sources(store: TypedArtifactStore) -> list[str]:
    """Every distinct `source` this project's memory store has ever recorded.
    This dashboard is the project's own local admin surface, so it sees
    everything the project has, never a narrower cross-tool allowlist --
    Phase 61's fail-closed `session_allowlist` gate is satisfied by naming
    every source that's actually there."""
    return sorted({row["source"] for row in store.list_artifact_refs()})


def _scope_artifact_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "family": row["family"],
        "subject": row["subject"],
        "trust_tier": row["trust_tier"],
        "content": json.loads(row["content"]),
        "source": row["source"],
        "created_at": row["created_at"],
        "symbol_ref": row["symbol_ref"],
        "content_hash": row["content_hash"],
        "corroboration_count": row["corroboration_count"],
        "promoted_at": row["promoted_at"],
        "stale": bool(row["stale"]),
        "origin_kind": row["origin_kind"],
        "origin_id": row["origin_id"],
        "expired": row["expired_at"] is not None,
        "artifact_version": row["artifact_version"],
        "dynamic_freshness_checked": False,
    }


def _build_memory_section(
    project_id: str, query: dict[str, list[str]]
) -> dict[str, Any]:
    """`section=memory` (plan Sec 3.1): scope/type/trust/source/freshness
    filters, text search, and exact expansion/relationship navigation. A
    non-empty `query` searches via `MemoryTool`'s own `list` dispatch --
    the same `TypedArtifactStore.recall()` path the CLI/MCP use, including
    its dynamic per-row staleness re-check (a memory whose cited symbol
    changed since it was written surfaces `stale: true` here). An empty
    `query` browses via `TypedArtifactStore.scope_artifacts()` instead
    (`dynamic_freshness_checked: false` -- only the persisted `stale`
    column, no live re-check)."""
    root = Path(resolve_project(project_id)["root"])
    store = TypedArtifactStore(root)
    all_sources = _all_known_sources(store)

    requested_subjects = _split_csv(query.get("subject", []))
    subjects = [s for s in requested_subjects if s in _MEMORY_SUBJECTS] or list(
        _MEMORY_SUBJECTS
    )
    trust_filter = set(_split_csv(query.get("trust", [])))
    source_filter = set(_split_csv(query.get("source", [])))
    freshness = query.get("freshness", [None])[0]
    include_archived = query.get("include_archived", ["false"])[0] == "true"
    query_text = query.get("query", [""])[0]

    items: list[dict[str, Any]] = []
    if query_text and all_sources:
        for subject in subjects:
            result = MemoryTool().run(
                root,
                operation="list",
                subject=subject,
                query=query_text,
                session_allowlist=all_sources,
                include_archived=include_archived,
            )
            for artifact in result.get("raw") or []:
                item = dict(artifact)
                item["dynamic_freshness_checked"] = True
                items.append(item)
        if trust_filter:
            items = [i for i in items if i.get("trust_tier") in trust_filter]
    elif all_sources:
        for subject in subjects:
            rows = store.scope_artifacts(
                subject,
                source_allowlist=all_sources,
                trust_tiers=trust_filter or None,
                include_expired=include_archived,
            )
            items.extend(_scope_artifact_row(row) for row in rows)

    if source_filter:
        items = [i for i in items if i.get("source") in source_filter]
    if freshness == "stale":
        items = [i for i in items if i.get("stale")]
    elif freshness == "fresh":
        items = [i for i in items if not i.get("stale")]
    elif freshness == "expired":
        items = [i for i in items if i.get("expired")]

    cursor = query.get("cursor", [None])[0]
    try:
        limit = int(query.get("limit", ["50"])[0])
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 100))
    offset = _decode_offset_cursor(cursor)
    page = items[offset : offset + limit]
    next_cursor = (
        _encode_offset_cursor(offset + limit) if offset + limit < len(items) else None
    )

    section_data: dict[str, Any] = {
        "items": page,
        "next_cursor": next_cursor,
        "total": len(items),
        "subjects": list(_MEMORY_SUBJECTS),
        "known_sources": all_sources,
    }

    expand_id = query.get("expand_id", [None])[0]
    if expand_id:
        try:
            expand_version = int(query.get("expand_version", ["0"])[0])
        except ValueError:
            expand_version = 0
        expand_result = MemoryTool().run(
            root,
            operation="expand",
            request={"id": expand_id, "version": expand_version},
            session_allowlist=all_sources,
        )
        section_data["expand"] = dict(expand_result)

    related_id = query.get("related_id", [None])[0]
    if related_id:
        try:
            related_version = int(query.get("related_version", ["0"])[0])
        except ValueError:
            related_version = 0
        related_result = MemoryTool().run(
            root,
            operation="related",
            request={"id": related_id, "version": related_version},
            session_allowlist=all_sources,
        )
        section_data["related"] = dict(related_result)

    return section_data


# --- Phase 66 P66-05: token use snapshot section -----------------------------

_MEMORY_EVENT_KINDS = ("retrieval", "expansion", "packing", "handoff", "embedding")


def _list_project_handoffs(root: Path) -> list[dict[str, Any]]:
    """Real Phase 65 handoff-packet evidence (`.rush/handoffs/*.json`,
    `ScanHandoff.to_dict()` shape written by `build_handoff`) -- each packet
    carries its own real `tiktoken`-measured `tokens`/`bytes`/`encoding`
    (`_build_packet` in `rush.workflows.project_run`), never an estimate."""
    handoffs_dir = root / ".rush" / "handoffs"
    if not handoffs_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(handoffs_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            results.append(payload)
    return results


def _build_tokens_section(
    project_id: str, query: dict[str, list[str]]
) -> dict[str, Any]:
    """`section=tokens` (plan Sec 3.1): actual usage kept separate from
    estimated/avoided payload, per project/run/agent/session, sharing the
    exact same `TelemetryStore.get_summary()` computation the live gain TUI
    panel reads (`token_economy/tui_gain.py::build_gain_panel`) -- never a
    second, possibly-drifting savings calculator. Rush's local telemetry
    ledger never observes a provider-billed usage report, so `provider_usage`
    stays explicitly `available: false` rather than fabricating a number."""
    root = Path(resolve_project(project_id)["root"])
    telemetry = TelemetryStore(root)
    summary = telemetry.get_summary()
    by_kind = {
        kind: telemetry.get_memory_event_total(kind) for kind in _MEMORY_EVENT_KINDS
    }
    store = TypedArtifactStore(root)
    cache_fill_count = sum(
        1 for row in store.list_artifact_refs() if row["source"] == "context_pack"
    )

    handoffs = _list_project_handoffs(root)
    run_filter = query.get("run_id", [None])[0]
    agent_filter = query.get("agent_id", [None])[0]
    if run_filter:
        handoffs = [h for h in handoffs if h.get("run_id") == run_filter]
    if agent_filter:
        handoffs = [h for h in handoffs if h.get("agent_id") == agent_filter]

    rows = [
        {
            "run_id": h.get("run_id"),
            "agent_id": h.get("agent_id"),
            "session_id": h.get("memory_session_id"),
            "handoff_id": h.get("handoff_id"),
            "state": h.get("state"),
            "tokens": (h.get("packet") or {}).get("tokens"),
            "bytes": (h.get("packet") or {}).get("bytes"),
            "encoding": (h.get("packet") or {}).get("encoding"),
            "truncated": bool((h.get("packet") or {}).get("remainder_ids")),
        }
        for h in handoffs
    ]

    return {
        "actual": {
            "raw_tokens": summary["total_raw_tokens"],
            "sent_tokens": summary["total_compressed_tokens"],
            "events_count": summary["events_count"],
            "by_memory_event_kind": by_kind,
        },
        "estimated_avoided": {
            "tokens_saved": summary["net_tokens_saved"],
            "compression_ratio": summary["compression_ratio"],
            "dollar_savings_est": summary["dollar_savings_est"],
        },
        "provider_usage": {
            "available": False,
            "reason": (
                "Rush's local telemetry ledger records packed/compressed "
                "payload size, never a provider-billed usage report; no LLM "
                "billing integration is wired."
            ),
        },
        "cache": {"warm_fill_count": cache_fill_count},
        "runs": rows,
        "export_rows": rows,
    }


# --- Phase 66 P66-06: Git history and every generated artifact section ------
#
# Every Git call here is read-only (`log`/`status`/`show` via
# `rush.workflows.projects`'s bounded, argv-based helpers) -- never a mutation
# of the branch or index. A hostile commit subject or scanner-output value is
# only ever delivered as a plain JSON string field, never interpolated into
# HTML server-side; `application.js`/`project_map.js` (not owned by this
# packet) render every value via `textContent`, never `innerHTML`.


def _build_git_section(project_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    """`section=git` (plan §3/§6.4 P66-06): bounded paginated commit history,
    working-tree/index status, and an optional single-commit diff. Linking a
    commit to scan-output evidence only ever uses an exact literal path match
    between the commit's changed files and an artifact's recorded path --
    never a fabricated or inferred association (plan: "Link commits/source
    revisions to scans... only where actual identity matches")."""
    status = project_snapshot(project_id)["git"]

    try:
        limit = int(query.get("limit", ["20"])[0])
    except ValueError:
        limit = 20
    try:
        skip = int(query.get("skip", ["0"])[0])
    except ValueError:
        skip = 0
    history_page = project_git_history(project_id, limit=limit, skip=skip)

    result: dict[str, Any] = {
        "has_git": status["has_git"],
        "head": status["head"],
        "dirty": status["dirty"],
        "dirty_files": status["dirty_files"],
        "history": history_page["commits"],
        "next_skip": history_page["next_skip"],
    }

    commit = query.get("commit", [None])[0]
    if commit:
        diff = project_git_commit_diff(project_id, commit)
        changed = set(diff.get("changed_paths") or [])
        linked: list[str] = []
        if changed:
            artifacts = list_project_artifacts(project_id)
            linked = [
                a["artifact_ref"]
                for a in artifacts.get("scan_outputs") or []
                if changed.intersection(a.get("paths") or [])
            ]
        diff["linked_scan_outputs"] = linked
        result["diff"] = diff
    return result


def _build_artifacts_section(
    project_id: str, query: dict[str, list[str]]
) -> dict[str, Any]:
    """`section=artifacts` (plan §3.1/§6.4 P66-06): every category
    `list_project_artifacts` returns, paginated the same bounded offset-
    cursor way as `scans`/`memory`, plus optional single-reference expansion.
    A category/kind this dashboard has never seen before is never filtered
    out or special-cased -- it lists and expands exactly like any other
    (plan: "Display unknown types generically with metadata"). Expansion
    only ever adds a bounded, path-traversal-safe raw excerpt (`_read_excerpt`,
    the same one `scans` uses) for entries that carry a real on-disk path;
    memory/handoff entries never get a raw content view (plan: "no
    executable HTML preview of arbitrary scanner output" / never expose raw
    finding evidence or memory content)."""
    payload = list_project_artifacts(project_id)
    items: list[dict[str, Any]] = []
    for bucket in ("scan_outputs", "handoffs", "memory"):
        items.extend(payload.get(bucket) or [])

    category_filter = set(_split_csv(query.get("category", [])))
    kind_filter = set(_split_csv(query.get("kind", [])))
    if category_filter:
        items = [i for i in items if i.get("category") in category_filter]
    if kind_filter:
        items = [i for i in items if i.get("kind") in kind_filter]

    cursor = query.get("cursor", [None])[0]
    try:
        limit = int(query.get("limit", ["50"])[0])
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 100))
    offset = _decode_offset_cursor(cursor)
    page = items[offset : offset + limit]
    next_cursor = (
        _encode_offset_cursor(offset + limit) if offset + limit < len(items) else None
    )

    result: dict[str, Any] = {
        "items": page,
        "next_cursor": next_cursor,
        "total": len(items),
        "categories": sorted({str(i.get("category", "unknown")) for i in items}),
    }

    expand_ref = query.get("expand_ref", [None])[0]
    if expand_ref:
        expanded = expand_artifact_reference(project_id, expand_ref)
        entry = expanded.get("entry") or {}
        paths = entry.get("paths") or []
        raw_excerpt = None
        if paths:
            root = Path(resolve_project(project_id)["root"])
            raw_excerpt = _read_excerpt(root, paths[0], start=1, end=200)
        result["expand"] = {**expanded, "raw_excerpt": raw_excerpt}
    return result


def _make_handler(ctx: DashboardContext) -> type[BaseHTTPRequestHandler]:
    """Build a fresh handler class closing over this server's DashboardContext."""

    class _CanonicalHandler(BaseHTTPRequestHandler):
        server_version = "RushDashboard/1"
        timeout = SOCKET_TIMEOUT_SECONDS

        def log_message(self, format: str, *args: Any) -> None:
            """Suppress default logging -- never log session/CSRF secrets."""

        # --- shared helpers ---------------------------------------------
        def _request_id(self) -> str:
            return self.headers.get("X-Request-Id") or uuid.uuid4().hex

        def _send_json(
            self,
            status: int,
            body: bytes,
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_js(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_css(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_error(
            self,
            status: int,
            code: str,
            message: str,
            request_id: str,
            project_id: str | None = None,
            *,
            retryable: bool = False,
        ) -> None:
            self._send_json(
                status,
                _error_body(request_id, project_id, code, message, retryable=retryable),
            )

        def _valid_host(self) -> bool:
            hosts = self.headers.get_all("Host")
            if not hosts or len(hosts) != 1:
                return False
            host = hosts[0]
            if not host or any(ch.isspace() for ch in host) or "@" in host:
                return False
            return host in (
                f"127.0.0.1:{ctx.bound_port}",
                f"localhost:{ctx.bound_port}",
            )

        def _cookie(self) -> str | None:
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            prefix = f"{ctx.auth.cookie_name}="
            for part in raw.split(";"):
                part = part.strip()
                if part.startswith(prefix):
                    return part[len(prefix) :]
            return None

        def _bearer(self) -> str | None:
            header = self.headers.get("Authorization")
            if header and header.startswith("Bearer "):
                return header[len("Bearer ") :]
            return None

        def _check_request_limits(self) -> int | None:
            """Validate header/body-size limits; return declared body length
            (0 if none) or None after already sending an error response."""
            request_id = self._request_id()
            if len(self.headers) > MAX_HEADER_FIELDS:
                self._send_error(
                    400, "malformed_request", "too many header fields", request_id
                )
                return None
            headers_size = sum(len(k) + len(v) for k, v in self.headers.items())
            if headers_size > MAX_HEADERS_BYTES:
                self._send_error(
                    400, "malformed_request", "headers too large", request_id
                )
                return None
            if self.headers.get("Transfer-Encoding"):
                self._send_error(
                    400, "malformed_request", "chunked transfer rejected", request_id
                )
                return None
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                return 0
            try:
                length = int(length_header)
            except ValueError:
                self._send_error(
                    400, "malformed_request", "invalid Content-Length", request_id
                )
                return None
            if length < 0:
                self._send_error(
                    400, "malformed_request", "invalid Content-Length", request_id
                )
                return None
            if length > MAX_BODY_BYTES:
                self._send_error(
                    413, "body_too_large", "request body exceeds limit", request_id
                )
                return None
            return length

        def _read_json_body(
            self, length: int, request_id: str
        ) -> dict[str, Any] | None:
            content_type = (
                (self.headers.get("Content-Type") or "").split(";")[0].strip()
            )
            if length and content_type != "application/json":
                self._send_error(
                    400,
                    "malformed_request",
                    "Content-Type must be application/json",
                    request_id,
                )
                return None
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                payload = json.loads(raw)
            except ValueError:
                self._send_error(
                    400, "malformed_request", "invalid JSON body", request_id
                )
                return None
            if not isinstance(payload, dict):
                self._send_error(
                    400, "malformed_request", "JSON body must be an object", request_id
                )
                return None
            return payload

        def _authenticate_session(
            self, request_id: str, project_id: str | None, *, require_csrf: bool
        ) -> Any:
            cookie = self._cookie()
            session = ctx.auth.get_session(cookie)
            if session is None:
                self._send_error(
                    401, "unauthorized", "no active session", request_id, project_id
                )
                return None
            if require_csrf and not ctx.auth.verify_csrf(
                cookie, self.headers.get("X-Rush-CSRF")
            ):
                self._send_error(
                    403,
                    "csrf_denied",
                    "missing or invalid CSRF token",
                    request_id,
                    project_id,
                )
                return None
            return session

        def _check_origin(self, request_id: str, *, require_exact: bool) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None:
                if origin != ctx.launch_origin:
                    self._send_error(
                        403, "invalid_origin", "Origin rejected", request_id
                    )
                    return False
                return True
            if require_exact:
                self._send_error(403, "invalid_origin", "Origin required", request_id)
                return False
            sec_fetch_site = self.headers.get("Sec-Fetch-Site")
            if sec_fetch_site not in (None, "same-origin", "none"):
                self._send_error(
                    403, "invalid_origin", "cross-site request rejected", request_id
                )
                return False
            return True

        # --- routing ------------------------------------------------------
        def do_GET(self) -> None:
            request_id = self._request_id()
            if not self._valid_host():
                self._send_error(
                    403, "invalid_host", "Host header rejected", request_id
                )
                return
            path = urlparse(self.path).path

            if path == "/api/health":
                self._send_json(
                    200,
                    json.dumps({"ready": True, "schema_version": 1}).encode("utf-8"),
                )
                return
            if path == "/api/control/health":
                self._handle_control_health(request_id)
                return
            if path == "/":
                self._send_html(200, BOOTSTRAP_HTML_TEMPLATE.encode("utf-8"))
                return
            if path == "/assets/bootstrap.js":
                self._send_js(200, BOOTSTRAP_JS.encode("utf-8"))
                return
            if path == "/assets/project_map.js":
                self._send_js(
                    200, load_dashboard_asset("project_map.js").encode("utf-8")
                )
                return
            if path == "/assets/application.js":
                self._send_js(
                    200, load_dashboard_asset("application.js").encode("utf-8")
                )
                return
            if path == "/assets/dashboard.css":
                self._send_css(200, DASHBOARD_CSS.encode("utf-8"))
                return

            if not self._check_origin(request_id, require_exact=False):
                return

            if path == "/api/session":
                self._handle_session_get(request_id)
                return
            if path == "/api/theme":
                self._handle_theme(request_id)
                return
            if path == "/api/projects":
                self._handle_projects_list(request_id)
                return
            if path.startswith("/api/projects/") and path.endswith("/snapshot"):
                project_id = path[len("/api/projects/") : -len("/snapshot")]
                self._handle_snapshot(project_id, request_id)
                return

            self._send_error(404, "not_found", "unknown route", request_id)

        def do_POST(self) -> None:
            request_id = self._request_id()
            if not self._valid_host():
                self._send_error(
                    403, "invalid_host", "Host header rejected", request_id
                )
                return
            declared_length = self._check_request_limits()
            if declared_length is None:
                return
            path = urlparse(self.path).path

            if path == "/api/session/bootstrap":
                self._handle_reconnect_bootstrap(request_id)
                return

            if path == "/api/session":
                if not self._check_origin(request_id, require_exact=False):
                    return
                self._handle_session_exchange(request_id)
                return

            if not self._check_origin(request_id, require_exact=True):
                return

            if path == "/api/projects":
                self._handle_projects_create(request_id, declared_length)
                return
            if path.startswith("/api/projects/") and path.endswith("/actions"):
                project_id = path[len("/api/projects/") : -len("/actions")]
                self._handle_action(project_id, request_id, declared_length)
                return

            self._send_error(404, "not_found", "unknown route", request_id)

        # --- handlers -------------------------------------------------
        def _handle_control_health(self, request_id: str) -> None:
            if self.headers.get("Origin") is not None:
                self._send_error(
                    403, "invalid_origin", "control endpoint rejects Origin", request_id
                )
                return
            if not ctx.auth.verify_control(self.headers.get("X-Rush-Control")):
                self._send_error(
                    401, "unauthorized", "control capability required", request_id
                )
                return
            body = json.dumps(
                {
                    "schema_version": 1,
                    "server_id": ctx.server_id,
                    "pid": ctx.pid,
                    "start_nonce": ctx.start_nonce,
                }
            ).encode("utf-8")
            self._send_json(200, body)

        def _handle_reconnect_bootstrap(self, request_id: str) -> None:
            if self.headers.get("Origin") is not None or self._cookie() is not None:
                self._send_error(
                    401,
                    "unauthorized",
                    "reconnect control rejects browser credentials",
                    request_id,
                )
                return
            if not ctx.auth.verify_control(self.headers.get("X-Rush-Control")):
                self._send_error(
                    401, "unauthorized", "control capability required", request_id
                )
                return
            token = ctx.auth.issue_bootstrap()
            self._send_json(
                200,
                json.dumps({"schema_version": 1, "bootstrap_token": token}).encode(
                    "utf-8"
                ),
            )

        def _handle_session_exchange(self, request_id: str) -> None:
            bearer = self._bearer()
            session = ctx.auth.exchange_bootstrap(bearer)
            if session is None:
                self._send_error(
                    401,
                    "unauthorized",
                    "invalid or expired bootstrap token",
                    request_id,
                )
                return
            body = json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "csrf_token": session.csrf_token,
                }
            ).encode("utf-8")
            cookie_header = f"{ctx.auth.cookie_name}={session.cookie_value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"
            self._send_json(200, body, extra_headers={"Set-Cookie": cookie_header})

        def _handle_session_get(self, request_id: str) -> None:
            session = ctx.auth.get_session(self._cookie())
            if session is None:
                self._send_error(401, "unauthorized", "no active session", request_id)
                return
            body = json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "csrf_token": session.csrf_token,
                }
            ).encode("utf-8")
            self._send_json(200, body)

        def _handle_snapshot(self, project_id: str, request_id: str) -> None:
            if (
                self._authenticate_session(request_id, project_id, require_csrf=False)
                is None
            ):
                return
            record = ctx.projects.get(project_id)
            if record is None:
                self._send_error(
                    404, "not_found", "unknown project", request_id, project_id
                )
                return

            query = parse_qs(urlparse(self.path).query)
            section = query.get("section", [None])[0]
            data: Any
            if section == "map":
                node_types = tuple(
                    v
                    for entry in query.get("node_types", [])
                    for v in entry.split(",")
                    if v
                )
                severity = tuple(
                    v
                    for entry in query.get("severity", [])
                    for v in entry.split(",")
                    if v
                )
                status = tuple(
                    v
                    for entry in query.get("status", [])
                    for v in entry.split(",")
                    if v
                )
                query_text = query.get("query", [""])[0]
                cursor = query.get("cursor", [None])[0]
                group_id = query.get("group", [None])[0]
                if group_id:
                    data = expand_group(
                        record.snapshot,
                        group_id,
                        node_types=node_types,
                        severity=severity,
                        status=status,
                        query=query_text,
                        cursor=cursor,
                    )
                else:
                    data = build_project_map(
                        record.snapshot,
                        node_types=node_types,
                        severity=severity,
                        status=status,
                        query=query_text,
                        center_id=query.get("center_id", [None])[0],
                        cursor=cursor,
                    )
            elif section == "scans":
                data = _build_scans_section(ctx, project_id, query)
            elif section == "memory":
                try:
                    data = _build_memory_section(project_id, query)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except Exception as exc:  # noqa: BLE001 -- plan Sec 3.1
                    # "render failures as errors with retry, not empty
                    # memory": any failure here must reach the browser/TUI
                    # as a structured, retryable error, never a silently
                    # emptied section or an unhandled 500 traceback.
                    self._send_error(
                        500,
                        "section_error",
                        f"failed to build memory section: {exc}",
                        request_id,
                        project_id,
                        retryable=True,
                    )
                    return
            elif section == "tokens":
                try:
                    data = _build_tokens_section(project_id, query)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except Exception as exc:  # noqa: BLE001 -- see section == "memory"
                    self._send_error(
                        500,
                        "section_error",
                        f"failed to build tokens section: {exc}",
                        request_id,
                        project_id,
                        retryable=True,
                    )
                    return
            elif section == "git":
                try:
                    data = _build_git_section(project_id, query)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except Exception as exc:  # noqa: BLE001 -- see section == "memory"
                    self._send_error(
                        500,
                        "section_error",
                        f"failed to build git section: {exc}",
                        request_id,
                        project_id,
                        retryable=True,
                    )
                    return
            elif section == "artifacts":
                try:
                    data = _build_artifacts_section(project_id, query)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except Exception as exc:  # noqa: BLE001 -- see section == "memory"
                    self._send_error(
                        500,
                        "section_error",
                        f"failed to build artifacts section: {exc}",
                        request_id,
                        project_id,
                        retryable=True,
                    )
                    return
            else:
                data = record.snapshot

            try:
                body = _success_body(request_id, project_id, record.sequence, data)
            except (TypeError, ValueError):
                self._send_error(
                    500,
                    "serialization_error",
                    "failed to serialize snapshot",
                    request_id,
                    project_id,
                )
                return
            self._send_json(200, body)

        def _handle_theme(self, request_id: str) -> None:
            if self._authenticate_session(request_id, None, require_csrf=False) is None:
                return
            body = _success_body(
                request_id, None, 1, {"theme": THEME, "motion": MOTION}
            )
            self._send_json(200, body)

        def _handle_projects_list(self, request_id: str) -> None:
            if self._authenticate_session(request_id, None, require_csrf=False) is None:
                return
            query = parse_qs(urlparse(self.path).query)
            cursor = query.get("cursor", [None])[0]
            try:
                limit = int(query.get("limit", ["50"])[0])
            except ValueError:
                limit = 50
            limit = max(1, min(limit, 100))
            records, next_cursor = ctx.projects.list_page(cursor=cursor, limit=limit)
            items = [
                {
                    "project_id": record.project_id,
                    "root": record.snapshot.get("root"),
                    "source_identity": record.source_identity,
                }
                for record in records
            ]
            body = _success_body(
                request_id, None, 1, {"items": items, "next_cursor": next_cursor}
            )
            self._send_json(200, body)

        def _handle_projects_create(
            self, request_id: str, declared_length: int
        ) -> None:
            if self._authenticate_session(request_id, None, require_csrf=True) is None:
                return
            payload = self._read_json_body(declared_length, request_id)
            if payload is None:
                return
            operation = payload.get("operation")
            if operation not in ("add", "create"):
                self._send_error(
                    400,
                    "unknown_operation",
                    "operation must be add or create",
                    request_id,
                )
                return
            grants = payload.get("grants") or {}
            if not (
                isinstance(grants, dict)
                and grants.get("cache_write")
                and grants.get("artifact_write")
            ):
                self._send_error(
                    403,
                    "grant_denied",
                    "add/create requires explicit cache_write and artifact_write grants",
                    request_id,
                )
                return

            try:
                if operation == "add":
                    path_value = payload.get("path")
                    if not isinstance(path_value, str) or not path_value:
                        raise ProjectInvalidRequestError("add requires path")
                    record = register_project(path_value, name=payload.get("name"))
                    created = False
                else:
                    parent_value = payload.get("parent")
                    name_value = payload.get("name")
                    if not isinstance(parent_value, str) or not isinstance(
                        name_value, str
                    ):
                        raise ProjectInvalidRequestError(
                            "create requires parent and name"
                        )
                    record = create_project(
                        parent_value,
                        name_value,
                        init_git=bool(payload.get("git_init", False)),
                    )
                    created = True
            except ProjectError as exc:
                status = (
                    409
                    if getattr(exc, "code", "") == "PROJECT_DESTINATION_EXISTS"
                    else 400
                )
                code = "project_exists" if status == 409 else "invalid_request"
                self._send_error(status, code, str(exc), request_id)
                return

            empty_snapshot = {
                "schema_version": 1,
                "project_id": record.project_id,
                "source_identity": record.root,
                "root": record.root,
                "files": [],
                "findings": [],
                "memories": [],
                "agents": [],
            }
            ctx.projects.register(record.project_id, empty_snapshot)

            body = json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "project_id": None,
                    "sequence": 1,
                    "data": {
                        "project_id": record.project_id,
                        "root": record.root,
                        "created": created,
                        "next": "configure",
                    },
                }
            ).encode("utf-8")
            self._send_json(201, body)

        def _handle_action(
            self, project_id: str, request_id: str, declared_length: int
        ) -> None:
            if (
                self._authenticate_session(request_id, project_id, require_csrf=True)
                is None
            ):
                return
            payload = self._read_json_body(declared_length, request_id)
            if payload is None:
                return
            operation = payload.get("operation")
            mutation_id = payload.get("request_id")
            if not isinstance(operation, str) or operation not in ALLOWED_ACTIONS:
                self._send_error(
                    400,
                    "unknown_operation",
                    "operation not allowlisted",
                    request_id,
                    project_id,
                )
                return
            if not isinstance(mutation_id, str) or not mutation_id:
                self._send_error(
                    400,
                    "malformed_request",
                    "request_id required",
                    request_id,
                    project_id,
                )
                return
            record = ctx.projects.get(project_id)
            if record is None:
                self._send_error(
                    404, "not_found", "unknown project", request_id, project_id
                )
                return

            arguments = payload.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            grants = payload.get("grants")
            if not isinstance(grants, dict):
                grants = {}

            body_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()

            def _build() -> tuple[int, bytes]:
                if operation == "noop":
                    run_id = ctx.mutations.next_run_id()
                    data: dict[str, Any] = {"operation": operation, "run_id": run_id}
                    return 202, _success_body(
                        request_id, project_id, record.sequence, data
                    )
                try:
                    status_code, data = _dispatch_scan_action(
                        ctx, project_id, operation, arguments, grants
                    )
                except _ActionDenied as exc:
                    return exc.status, _error_body(
                        request_id,
                        project_id,
                        exc.code,
                        str(exc),
                        retryable=exc.retryable,
                    )
                return status_code, _success_body(
                    request_id, project_id, record.sequence, data
                )

            try:
                (status_code, body), conflict = ctx.mutations.commit(
                    mutation_id, body_hash, _build
                )
            except (TypeError, ValueError):
                self._send_error(
                    500,
                    "serialization_error",
                    "failed to serialize result",
                    request_id,
                    project_id,
                )
                return
            if conflict:
                self._send_error(
                    409,
                    "conflict",
                    "request_id reused with a different body",
                    request_id,
                    project_id,
                )
                return
            self._send_json(status_code, body)

    return _CanonicalHandler


def create_dashboard_server(
    projects: dict[str, dict[str, Any]], *, host: str = "127.0.0.1", port: int = 0
) -> tuple[ThreadingHTTPServer, DashboardContext, str]:
    """Start a canonical per-server authenticated dashboard API.

    Returns the running server, its DashboardContext (auth/session/project
    state) and the initial one-use bootstrap token. Each call builds an
    entirely fresh context and handler class, so two concurrently-running
    servers never share auth, session, or project state. Use
    bootstrap_launch_url() to format the returned token for display.
    """
    server = ThreadingHTTPServer((host, port), BaseHTTPRequestHandler)
    actual_port = server.server_address[1]

    ctx = DashboardContext(projects, bound_host=host, bound_port=actual_port)
    bootstrap_token = ctx.auth.issue_bootstrap()
    # Swap in the real per-instance handler class after the port is known,
    # rather than closing and rebinding (which would race another process
    # for the freed port).
    server.RequestHandlerClass = _make_handler(ctx)
    return server, ctx, bootstrap_token


def bootstrap_launch_url(ctx: DashboardContext, token: str) -> str:
    """Format the one-use launch URL carrying the bootstrap token in the
    fragment. The fragment is never transmitted to the server by a browser,
    so it never appears in server logs, API/query URLs, or a Referer header."""
    return f"{ctx.launch_origin}/#token={token}"


def reconnect_dashboard(base_url: str, control_token: str) -> str:
    """Exchange a private control capability for a fresh one-use bootstrap
    token. Used by `rush dashboard --reconnect`, wired to the CLI in a later
    packet. Never sends a cookie or ordinary Bearer credential."""
    import urllib.request

    health_request = urllib.request.Request(
        f"{base_url}/api/control/health", headers={"X-Rush-Control": control_token}
    )
    with urllib.request.urlopen(health_request, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("dashboard control health check failed")

    bootstrap_request = urllib.request.Request(
        f"{base_url}/api/session/bootstrap",
        data=b"",
        method="POST",
        headers={"X-Rush-Control": control_token, "Content-Length": "0"},
    )
    with urllib.request.urlopen(bootstrap_request, timeout=5) as response:
        payload = json.loads(response.read())
    return payload["bootstrap_token"]
