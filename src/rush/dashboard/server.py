"""Authenticated in-memory ephemeral dashboard HTTP server."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import secrets
import socket
import threading
import time
import uuid
import weakref
from collections import OrderedDict
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast, get_args
from urllib.parse import parse_qs, urlparse

from rush.dashboard.auth import DashboardAuth
from rush.dashboard.project_map import (
    CursorRejected,
    build_project_map,
    expand_group,
    expand_group_edge,
)
from rush.dashboard.state import (
    MutationLedger,
    OwnerLock,
    PendingOutcomeQueue,
    ProjectRecord,
    ProjectRegistry,
    ScanConflictError,
    ScanRunTracker,
    reconcile_admissions,
)
from rush.dashboard.static_assets import (
    BOOTSTRAP_HTML_TEMPLATE,
    BOOTSTRAP_JS,
    DASHBOARD_CSS,
    DASHBOARD_HTML_TEMPLATE,
    load_dashboard_asset,
)
from rush.dashboard.theme import MOTION, THEME
from rush.discovery.stack import detect_project_stacks
from rush.memory.maintenance import MaintenanceTask
from rush.memory.store import (
    MemorySubject,
    OwnerScope,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
    is_internal_memory_source,
    readonly_view_reason,
)
from rush.permissions import ExecutionPermissions
from rush.runtime.filesystem import atomic_write_bytes
from rush.setup.engine_packages import ENGINE_PACKAGES
from rush.setup.provision import build_provision_plan
from rush.token_economy.telemetry import TelemetryStore
from rush.tools.agent_connection import AgentConnectionTool
from rush.tools.base import ToolResult
from rush.tools.memory import MemoryOperation, MemoryTool
from rush.tools.project import ProjectTool
from rush.tools.setup_wizard import run_setup_wizard
from rush.workflows import projects as wp
from rush.workflows.project_run import (
    _MANIFEST_RELATIVE,
    ScanHandoff,
    ScanInvalidRequestError,
    _cancel_requested,
    _capture_artifact_snapshots,
    _finding_id,
    _source_identity,
    _write_attempt_header,
    build_handoff,
    cancel_scan_run,
    compare_runs,
    dispatch_handoff,
    execute_scan,
    latest_attempt_id,
    load_run_manifest,
    load_scan_events,
    load_scan_plan,
    plan_scan,
    rescan_project_run,
    resume_scan_run,
    status_handoff,
)
from rush.workflows.projects import (
    ProjectError,
    ProjectInvalidRequestError,
    _scan_file_inventory,
    create_project,
    expand_artifact_reference,
    export_project_data,
    git_link_matches_commit,
    list_project_artifacts,
    project_git_commit_diff,
    project_git_history,
    project_snapshot,
    register_project,
    resolve_project,
)
from rush.workflows.suites import CHECK_SUITE, run_workflow_suite

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
# Lingering close after a rejected request (`_linger_discard`).
_LINGER_SECONDS = 2.0
_LINGER_MAX_BYTES = 4 * MAX_BODY_BYTES
SOCKET_TIMEOUT_SECONDS = 5
MAX_CONCURRENT_REQUESTS = 8
BOOTSTRAP_FAILURE_LIMIT = 10
BOOTSTRAP_FAILURE_WINDOW_SECONDS = 60.0
ACTION_RATE_LIMIT = 60
ACTION_RATE_WINDOW_SECONDS = 60.0
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)

# S13: the one shared source of these four security headers -- every normal
# response (JSON, HTML, JS, CSS, errors) and the pre-thread admission 503
# built before any handler exists all emit exactly these values, so no
# response route can silently omit or diverge from another's.
SECURITY_RESPONSE_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
)

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
        "handoff_status",
        "configure",
        "memory_edit",
        "memory_archive",
        "memory_delete",
        "memory_promote",
        "memory_query",
        "memory_expand",
        "memory_propose",
        "memory_maintain",
        "data_export",
        "artifact_export",
    }
)

# P69-01.2m: each action's own named argument set (Phase 66 Sec 3.6: "arguments
# are validated by corresponding shared operation metadata and unknown keys
# rejected") -- derived from exactly the keys each dispatcher below reads out of
# `arguments`, not top-level schema/grant validation.
_ARGUMENT_ALLOWLIST: dict[str, frozenset[str]] = {
    "noop": frozenset(),
    "provision_plan": frozenset(
        {"exclude", "targets", "severity", "concurrency", "timeout_seconds"}
    ),
    "provision_apply": frozenset({"plan_id"}),
    "scan_start": frozenset({"plan_id"}),
    "scan_cancel": frozenset({"run_id", "operation_id"}),
    "scan_resume": frozenset({"run_id"}),
    "rescan": frozenset({"run_id", "expected_attempt_id"}),
    "handoff_preview": frozenset(
        {"run_id", "attempt_id", "agent_id", "finding_ids", "max_tokens", "max_bytes"}
    ),
    "handoff_send": frozenset(
        {
            "run_id",
            "attempt_id",
            "agent_id",
            "finding_ids",
            "max_tokens",
            "max_bytes",
            "handoff_id",
        }
    ),
    "handoff_status": frozenset({"handoff_id"}),
    "configure": frozenset({"settings", "expected_revision", "apply", "plan_id"}),
    "memory_edit": frozenset(
        {"scope", "id", "expected_version", "content", "apply", "owner_scope"}
    ),
    "memory_archive": frozenset(
        {"scope", "id", "expected_version", "apply", "archived", "owner_scope"}
    ),
    "memory_delete": frozenset(
        {"artifact_ids", "expected_revisions", "scope", "apply", "owner_scope"}
    ),
    "memory_promote": frozenset(
        {
            "subject",
            "content",
            "source",
            "source_kind",
            "symbol_ref",
            "user_stated",
            "candidate_sources",
            "owner_scope",
        }
    ),
    "memory_query": frozenset(
        {
            "mode",
            "subject",
            "query",
            "session_allowlist",
            "retrieval",
            "limit",
            "max_tokens",
            "max_bytes",
            "encoding",
            "cursor",
        }
    ),
    "memory_expand": frozenset(
        {
            "id",
            "version",
            "session_allowlist",
            "offset",
            "max_tokens",
            "max_bytes",
            "encoding",
        }
    ),
    "memory_propose": frozenset(
        {"subject", "content", "source", "source_kind", "symbol_ref", "owner_scope"}
    ),
    "memory_maintain": frozenset({"task", "batch_size", "owner_scope"}),
    "data_export": frozenset(),
    "artifact_export": frozenset({"artifact_id"}),
}

# P69-01.2o: strict boolean coercion -- every argument/grant field that must be a
# genuine JSON boolean (`isinstance(value, bool)`), never a truthy/falsy coercion
# of e.g. the string "false". Checked before `_classify_mutating`/`_dispatch_scan_action`
# reads any of them (below in `_handle_action`).
_BOOLEAN_ARGUMENT_FIELDS = frozenset({"apply", "archived", "user_stated"})
_BOOLEAN_GRANT_FIELDS = frozenset(
    {"network", "download", "cache_write", "build", "slow", "artifact_write", "browser"}
)

# P69-01.2l: an action with no `apply` field uses fixed-name classification; only
# these two are genuinely read-only/preview (never mutate) among the fixed-name set --
# every other fixed-name action (including "noop", which the duplicate-mutation-id
# idempotency contract already depends on) stays mutating, matching its current
# ledger-tracked behavior.
_READ_ONLY_FIXED_ACTIONS = frozenset(
    {
        "provision_plan",
        "data_export",
        "handoff_status",
        "memory_query",
        "memory_expand",
        "artifact_export",
    }
)
_APPLY_GATED_ACTIONS = frozenset(
    {"memory_edit", "memory_archive", "memory_delete", "configure"}
)

# M08: the five memory-artifact mutation forms plus owner-scoped maintenance --
# every operation `_validate_memory_owner_scope` requires a real owner_scope for
# before dispatch. memory_query/memory_expand are plain reads and stay outside
# this set.
_MEMORY_OWNER_SCOPED_OPERATIONS = frozenset(
    {
        "memory_edit",
        "memory_archive",
        "memory_delete",
        "memory_promote",
        "memory_propose",
        "memory_maintain",
    }
)


def _schema_version_error(payload: dict[str, Any]) -> tuple[str, str] | None:
    """S14: shared validation for both action boundaries (`_handle_action`
    and `_handle_control_check_suite`) -- require schema_version presence
    and `type(value) is int` (an identity check, since `bool` is an `int`
    subclass in Python and must not silently pass as 1/0) before accepting
    the one supported value 1. Returns `(code, message)` for the caller to
    send as a 400, or None if the payload's schema_version is exactly the
    supported integer 1. Missing/null/string/bool all return
    malformed_request; a well-typed but unsupported integer (e.g. 2) uses
    the established unsupported_schema_version code instead."""
    if "schema_version" not in payload:
        return "malformed_request", "schema_version required"
    value = payload["schema_version"]
    if type(value) is not int:
        return (
            "malformed_request",
            f"schema_version must be an integer, got {value!r}",
        )
    if value != 1:
        return "unsupported_schema_version", f"schema_version must be 1, got {value!r}"
    return None


def _classify_mutating(operation: str, arguments: dict[str, Any]) -> bool:
    """P69-01.2l: classify the validated operation plus its arguments -- never the
    operation name alone. `memory_edit`/`memory_archive`/`memory_delete` branch on
    their own `apply` argument (preview writes no durable ledger entry); every other
    action uses fixed-name classification."""
    if operation in _APPLY_GATED_ACTIONS:
        return bool(arguments.get("apply"))
    return operation not in _READ_ONLY_FIXED_ACTIONS


# S04: operations sharing the scan-manifest/snapshot-publish effect pair
# (`_dispatch_scan_action` routes all four through the same publish path).
_SCAN_PUBLISH_OPERATIONS = frozenset(
    {"scan_start", "scan_resume", "rescan", "check_suite"}
)


def _s04_effect_ids(
    operation: str, arguments: dict[str, Any], project_id: str | None = None
) -> dict[str, str]:
    """S04 fix bullet 3: the proposed per-effect identity map (review doc
    §S04 table), preallocated before reservation so `MutationLedger.reserve()`
    persists it in the same transaction as the operation_id (never reminted
    later by a builder). A non-mutating call (`_classify_mutating` already
    decided) never reaches `MutationLedger.reserve()` at all, so returning a
    non-empty map here for e.g. `apply=False` is harmless dead data, but
    every branch below still matches the table's explicit "no domain effect
    keys" cases for clarity and cheap testability."""
    if operation in _SCAN_PUBLISH_OPERATIONS:
        return {
            "scan_manifest_write": uuid.uuid4().hex,
            "snapshot_publish": uuid.uuid4().hex,
        }
    if operation == "scan_cancel":
        return {"cancellation_intent": uuid.uuid4().hex}
    if operation == "handoff_send":
        return {
            key: uuid.uuid4().hex
            for key in (
                "artifact_create",
                "session_create",
                "descriptor_prepare",
                "delivery_transition",
            )
        }
    if operation == "provision_apply":
        keys = {
            "cursor_key_ensure": uuid.uuid4().hex,
            "toolchain_manifest": uuid.uuid4().hex,
        }
        # S04 table: one `install:<engine_id>` key per validated plan entry.
        # `run_setup_wizard`'s own return dict never exposes `ProvisionPlan`
        # entries (only `plan_id`), so the plan is rebuilt directly here via
        # `build_provision_plan`, mirroring `run_setup_wizard`'s internal
        # stack-detection + `ENGINE_PACKAGES` filter exactly. This reservation
        # runs before `_dispatch_provision_apply`'s own accept-time re-check
        # of `arguments.plan_id`, so a stale/changed plan here just leaves an
        # unused reserved key -- harmless dead data, same as the non-mutating
        # case above -- never a wrong install.
        if project_id is not None:
            try:
                root = Path(resolve_project(project_id)["root"])
                stacks = detect_project_stacks(root)
                suggested = {e for stack in stacks for e in stack.suggested_engines}
                known_engine_ids = sorted(e for e in suggested if e in ENGINE_PACKAGES)
                plan = build_provision_plan(root, known_engine_ids)
            except Exception:  # noqa: BLE001, S110 -- reservation must never
                # crash admission; fall back to the two operation-wide keys.
                pass
            else:
                keys.update(
                    {
                        f"install:{entry.engine_id}": uuid.uuid4().hex
                        for entry in plan.entries
                    }
                )
        return keys
    if operation == "configure":
        return {"config_write": uuid.uuid4().hex} if arguments.get("apply") else {}
    if operation == "memory_propose":
        return {"artifact_create": uuid.uuid4().hex}
    if operation == "memory_edit":
        return {"artifact_edit": uuid.uuid4().hex} if arguments.get("apply") else {}
    if operation == "memory_archive":
        return {"artifact_archive": uuid.uuid4().hex} if arguments.get("apply") else {}
    if operation == "memory_delete":
        if not arguments.get("apply"):
            return {}
        target_ids = arguments.get("artifact_ids")
        if not isinstance(target_ids, list):
            return {}
        return {
            f"delete:{target_id}": uuid.uuid4().hex
            for target_id in sorted({str(t) for t in target_ids})
        }
    if operation == "memory_promote":
        return {"candidate_create": uuid.uuid4().hex, "promotion": uuid.uuid4().hex}
    if operation == "memory_maintain":
        # S04 table: `<task>:<artifact_id>` subkeys are execution-time-only
        # information (which artifacts a maintenance sweep touches is not
        # knowable from `task`/`batch_size` alone) -- the operation-wide key
        # is the reservable part.
        return {"maintenance_run": uuid.uuid4().hex}
    # noop, provision_plan, handoff_preview, handoff_status, memory_query,
    # memory_expand, data_export, artifact_export: no domain effect keys.
    return {}


_MEMORY_SUBJECTS: tuple[MemorySubject, ...] = get_args(MemorySubject)
_MEMORY_SOURCE_KINDS = frozenset({"local_tool", "cross_tool_handoff", "human_derived"})


def _redact_known_secrets(value: Any, secrets_to_redact: tuple[str, ...]) -> Any:
    """Recursively replace any exact occurrence of a currently-live secret
    (bootstrap token, session cookie/CSRF values, control capability)
    inside message/finding text, so an interpolated exception or finding
    string can never leak a real secret into a response body."""
    if isinstance(value, str):
        for secret in secrets_to_redact:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {
            k: _redact_known_secrets(v, secrets_to_redact) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_known_secrets(v, secrets_to_redact) for v in value]
    return value


def _error_body(
    request_id: str,
    project_id: str | None,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    redact: tuple[str, ...] = (),
    details: dict[str, Any] | None = None,
) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "project_id": project_id,
            "error": {
                "code": code,
                "message": _redact_known_secrets(message, redact),
                "retryable": retryable,
                "details": details or {},
            },
        }
    ).encode("utf-8")


def _success_body(
    request_id: str,
    project_id: str | None,
    sequence: int,
    data: Any,
    *,
    redact: tuple[str, ...] = (),
) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "request_id": request_id,
            "project_id": project_id,
            "sequence": sequence,
            "data": _redact_known_secrets(data, redact),
        }
    ).encode("utf-8")


class _RateLimiter:
    """Per-key token bucket: `capacity` tokens, refilled continuously back
    to `capacity` over `period_seconds`. Thread-safe."""

    def __init__(self, capacity: int, period_seconds: float) -> None:
        self._capacity = float(capacity)
        self._period = period_seconds
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def _available(self, key: str, now: float) -> float:
        tokens, last = self._state.get(key, (self._capacity, now))
        return min(
            self._capacity, tokens + (now - last) * (self._capacity / self._period)
        )

    def try_consume(self, key: str) -> bool:
        """Consume one token if available. Returns whether it was allowed."""
        with self._lock:
            now = time.monotonic()
            tokens = self._available(key, now)
            if tokens < 1.0:
                self._state[key] = (tokens, now)
                return False
            self._state[key] = (tokens - 1.0, now)
            return True

    def peek_blocked(self, key: str) -> bool:
        """True if no token is currently available, without consuming."""
        with self._lock:
            return self._available(key, time.monotonic()) < 1.0


# T027: every `DashboardContext` ever constructed, tracked weakly so test
# teardown can stop its background recovery/outcome-retry threads without
# every call site (there are dozens, across production and tests) having to
# remember to do it itself. A daemon thread costs nothing at real process
# exit, but a short test `recovery_interval` left running for the rest of
# one pytest process's life is exactly how these accumulate into the T027
# hang -- see `stop_all_dashboard_contexts` below.
_live_dashboard_contexts: weakref.WeakSet = weakref.WeakSet()


def stop_all_dashboard_contexts() -> None:
    """Test-support: stop every live `DashboardContext`'s background
    threads. Never called from production code -- a real server process
    wants its recovery sweep running for its whole lifetime."""
    for ctx in list(_live_dashboard_contexts):
        ctx.stop_background_workers()


class DashboardContext:
    """Per-server-instance state bundle: never a class attribute anywhere.

    Constructed fresh by create_dashboard_server() for every server, so two
    running servers can never share auth, sessions, project scope, or
    mutation identities.
    """

    def __init__(
        self,
        projects: dict[str, dict[str, Any]],
        *,
        bound_host: str,
        bound_port: int,
        recovery_interval: float = 5.0,
        data_root: Path | None = None,
    ) -> None:
        # T027: every real on-disk piece below (`ProjectRegistry`'s
        # mutation lock, `MutationLedger`'s durable db, `OwnerLock`, and
        # `reconcile_admissions` below) already accepts an explicit
        # `data_root` -- this context just never threaded one through
        # before, so every one of them silently fell back to the real
        # shared `default_data_root()` and never a caller-isolated root.
        self.data_root = data_root
        self.auth = DashboardAuth()
        self.projects = ProjectRegistry(projects, data_root=data_root)
        self.mutations = MutationLedger(
            db_path=(data_root / "dashboard" / "mutation_ledger.db")
            if data_root is not None
            else None
        )
        self.scan_runs = ScanRunTracker()
        # (key, snapshot) of the last reusable historical map view; see
        # `_historical_map_snapshot_reused`.
        self.historical_map_memo: tuple[tuple[Any, ...], dict[str, Any]] | None = None
        self.bound_host = bound_host
        self.bound_port = bound_port
        self.launch_origin = f"http://{bound_host}:{bound_port}"
        self.server_id = self.auth.server_id
        self.pid = os.getpid()
        self.start_nonce = uuid.uuid4().hex
        # P69-01 subsection h: owner-liveness lock, keyed by this instance's
        # own immutable identity, held for this process's entire lifetime.
        self.owner_instance_id = f"{self.server_id}:{self.start_nonce}"
        self._owner_lock = OwnerLock(self.owner_instance_id, data_root=data_root)
        self.bootstrap_failure_limiter = _RateLimiter(
            BOOTSTRAP_FAILURE_LIMIT, BOOTSTRAP_FAILURE_WINDOW_SECONDS
        )
        self.action_limiter = _RateLimiter(
            ACTION_RATE_LIMIT, ACTION_RATE_WINDOW_SECONDS
        )
        # S11: bootstrap single-use is now enforced by DashboardAuth's own
        # owning lock (auth.py) -- no route-only lock needed here.
        # P69-02.2g: this server process owns retrying every worker's terminal
        # outcome (the durable pending-outcome write, then the idempotent
        # terminalize-and-release transaction) -- never the exiting worker.
        self.outcomes = PendingOutcomeQueue(
            self.mutations, owner_instance_id=self.owner_instance_id
        )
        # P69-02.2h: recovery runs at startup *and* on a bounded recurring
        # interval, for as long as this process stays alive -- otherwise a
        # server that outlives a since-crashed peer would return busy/conflict
        # against that dead server's admission row indefinitely.
        self.recovery_interval = recovery_interval
        self._recovery_stop = threading.Event()
        with suppress(Exception):
            reconcile_admissions(
                self.mutations,
                data_root=self.data_root,
                recovering_owner_instance_id=self.owner_instance_id,
            )
        self._recovery_thread = threading.Thread(
            target=self._recovery_loop, daemon=True, name="rush-dashboard-recovery"
        )
        self._recovery_thread.start()
        _live_dashboard_contexts.add(self)

    def _recovery_loop(self) -> None:
        while not self._recovery_stop.wait(self.recovery_interval):
            with suppress(Exception):
                reconcile_admissions(
                    self.mutations,
                    data_root=self.data_root,
                    recovering_owner_instance_id=self.owner_instance_id,
                )

    def stop_background_workers(self) -> None:
        """Stop this context's recovery sweep and outcome-retry queue. Both
        are daemon threads, so this is a courtesy for long-lived embedders,
        never a correctness requirement for process exit."""
        self._recovery_stop.set()
        self.outcomes.stop()

    def live_secrets(self) -> tuple[str, ...]:
        """Every currently-live secret value this server can still redact by
        exact match -- the control capability and each active session's CSRF
        token (legitimately re-served in plaintext on `GET /api/session`
        reload). The bootstrap token and session cookie value are no longer
        held in plaintext once minted (P69-01.3 CONNECT digest storage), so
        there is nothing left here to redact them against -- a request's own
        presented bootstrap/cookie value is redacted separately, by hash
        match, via `DashboardAuth.match_presented_secret` (S12).

        S12 point 1: sourced from `DashboardAuth`'s own lock-protected
        snapshot rather than iterating its mutable private session dict
        directly, so a concurrent session mint/expiry can never be observed
        half-mutated."""
        return self.auth.live_secret_values()


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
    "CURSOR_REJECTED": 409,
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


def _check_expected_identity(
    record: ProjectRecord | None, expected: dict[str, Any] | None
) -> str | None:
    """P69-02.2b: an optional top-level `expected` envelope's
    `source_identity` compared against the project's *current*
    `source_identity`. Returns a conflict message (caller turns this into a
    409) or `None` when `expected` is absent/empty or matches -- a request
    that never sends `expected` opts out of this check entirely."""
    if not expected or record is None:
        return None
    expected_identity = expected.get("source_identity")
    if expected_identity is not None and expected_identity != record.source_identity:
        return (
            f"expected.source_identity {expected_identity!r} is stale; "
            f"current source_identity is {record.source_identity!r}"
        )
    return None


def _validate_memory_owner_scope(
    operation: str,
    arguments: dict[str, Any],
    *,
    project_id: str,
    session_owner_scope_id: str,
) -> None:
    """M08: reject an omitted, malformed, or cross-project/cross-session
    `owner_scope` on every memory mutation before any reservation, row,
    version, or receipt change -- called from `_handle_action` before
    `body_hash`/`MutationLedger.commit`, never left to a dispatch function's
    own later validation. A no-op for every operation outside
    `_MEMORY_OWNER_SCOPED_OPERATIONS`.

    Identity rules (P69-07 subsection b): a `project`-kind owner must equal
    this request's own URL-selected project id; a `session`-kind owner must
    equal this request's own authenticated session's `owner_scope_id`;
    `user`/`agent`-kind ids are opaque, non-blank, and structurally validated
    only (`OwnerScope.__post_init__` already enforces non-blank).

    Normalizes `arguments["owner_scope"]` in place to the validated
    `{"kind", "id"}` dict so every dispatch function downstream sees exactly
    the same, already-validated owner."""
    if operation not in _MEMORY_OWNER_SCOPED_OPERATIONS:
        return
    try:
        owner = OwnerScope.from_value(arguments.get("owner_scope"))
    except ValueError as exc:
        raise _ActionDenied(
            400, "malformed_request", f"{operation} requires a valid owner_scope: {exc}"
        ) from exc
    if owner.kind == "project" and owner.id != project_id:
        raise _ActionDenied(
            400,
            "malformed_request",
            f"owner_scope project id {owner.id!r} does not name this request's "
            f"own project {project_id!r}",
        )
    if owner.kind == "session" and owner.id != session_owner_scope_id:
        raise _ActionDenied(
            400,
            "malformed_request",
            "owner_scope session id must match this request's own authenticated session",
        )
    arguments["owner_scope"] = owner.as_dict()


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


def _run_terminal_supervised(
    ctx: DashboardContext, operation_id: str, body: Callable[[], dict[str, Any]]
) -> None:
    """P69-02.2n: a lighter-weight counterpart to `_run_supervised` for long
    actions that don't participate in the scan admission table
    (`handoff_send`, `provision_apply`) -- records a real terminal status
    transition on any exit (success or failure), through the same shared
    `MutationLedger.record_status_transition()` primitive `scan_start`
    polls through, never a bare unconditional finally with nothing
    recorded."""
    payload: dict[str, Any] = {
        "status": "error",
        "code": "worker_exited",
        "message": "worker exited without recording a terminal outcome",
    }
    try:
        payload = body()
    except Exception as exc:  # noqa: BLE001 -- must terminalize on any failure.
        payload = {
            "status": "error",
            "code": "worker_failed",
            "message": str(exc) or exc.__class__.__name__,
        }
    finally:
        ctx.mutations.record_status_transition(operation_id, "terminal", payload)


def _dispatch_provision_apply(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    operation_id: str,
) -> tuple[int, dict[str, Any]]:
    """Install action: calls the exact approved `run_setup_wizard`/
    `apply_provision_plan` shared plan -- no browser-specific package
    manager logic. Refuses to apply a plan that changed since it was
    reviewed (its content-hashed `plan_id` no longer matches). P69-02.2n:
    returns 202 immediately with a run id and completes asynchronously,
    matching `scan_start`'s existing long-action lifecycle -- the status
    lookup polls the same `GET .../operations/{operation_id}` route."""
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
    # S16: provisioning allocates its own durable run/attempt job identity
    # before the effect, distinct from scan admission -- returned through
    # 202/status/receipts so a crash immediately after 202 recovers without
    # reminting or substituting an attempt (the ledger's own idempotent
    # request-id replay already returns this exact cached 202 body).
    run_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())

    def _body() -> dict[str, Any]:
        # S07: revalidate the reviewed plan immediately before the real
        # effect -- the check above ran synchronously before this thread was
        # even launched; this is the independent, second check from inside
        # the worker, closing the gap during which the project's real
        # readiness/provision plan can change.
        recheck = run_setup_wizard(root, install=True, permissions=None)
        if recheck.get("plan_id") != reviewed_plan_id:
            return {
                "status": "conflict",
                "code": "stale_expected_identity",
                "message": (
                    "provision plan changed between accept and execution; "
                    "re-review before applying"
                ),
            }
        applied = run_setup_wizard(
            root, install=True, permissions=permissions, project_id=project_id
        )
        return {
            "status": "success",
            "run_id": run_id,
            "attempt_id": attempt_id,
            "provision": applied.get("provision", {}),
        }

    thread = threading.Thread(
        target=_run_terminal_supervised, args=(ctx, operation_id, _body), daemon=True
    )
    thread.start()
    return 202, {
        "operation_id": operation_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": reviewed_plan_id,
    }


def _revalidate_expected_at_execution(
    ctx: DashboardContext,
    project_id: str,
    expected: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """P69-02.2c: acceptance-vs-execution split. `_check_expected_identity`
    already ran once at acceptance (subsection b, inside `_handle_action`'s
    `_build`); this is the *second*, independent check, run from inside the
    background thread immediately before the real effect executes -- closing
    the gap between an HTTP handler returning 202 and the queued work
    actually running, during which `expected` can go stale. Returns None if
    it's still safe to run the real effect; otherwise the terminal conflict
    payload the worker must terminalize with. It never writes the transition
    itself: the terminal write and the admission-row release are one
    transaction (P69-02.2g), owned by the outcome queue."""
    current = ctx.projects.get(project_id)
    conflict_reason = _check_expected_identity(current, expected)
    if conflict_reason is None:
        return None
    return {
        "status": "conflict",
        "code": "stale_expected_identity",
        "message": conflict_reason,
    }


def _run_supervised(
    ctx: DashboardContext,
    slot_id: str,
    operation_id: str,
    body: Callable[[], dict[str, Any]],
) -> None:
    """P69-02.2g: run one dispatched background job's real work and hand its
    terminal outcome to this server's retry queue from a `finally` that does
    nothing else.

    The outcome is pre-seeded with a real terminal error before `body()` runs,
    so an exit that bypasses `except Exception` -- `SystemExit`, or any other
    `BaseException` -- still terminalizes through the same idempotent
    transaction instead of freeing the admission row with no terminal state
    recorded. A bare, unconditional `finally: <release>` is exactly what this
    must never be: if the terminalize-and-release transaction itself fails,
    the admission row stays put for recovery to retry, never independently
    deleted.
    """
    payload: dict[str, Any] = {
        "status": "error",
        "code": "worker_exited",
        "message": "worker exited without recording a terminal outcome",
    }
    try:
        payload = body()
    except Exception as exc:  # noqa: BLE001 -- a worker must terminalize on
        # *any* failure of the real work; a narrower catch would leave the
        # admission row occupied forever with no terminal state recorded.
        payload = {
            "status": "error",
            "code": "worker_failed",
            "message": str(exc) or exc.__class__.__name__,
        }
    finally:
        ctx.outcomes.submit(slot_id, operation_id=operation_id, payload=payload)


def _admit_and_launch(
    ctx: DashboardContext,
    project_id: str,
    *,
    execution_identity: str,
    slot_id: str,
    operation_id: str,
    run_id: str,
    plan_id: str,
    thread: Any,
    attempt_id: str = "",
) -> tuple[str, str, str, bool]:
    """P69-02.2f/g: durable admission, then launch -- in that order.

    `ctx.mutations.admit()` only returns once its own transaction has
    committed, so no thread is ever launched and no 202 ever sent on the back
    of an uncommitted admission. A `thread.start()` failure happens outside
    any worker closure (the closure never runs), so it is caught here and
    terminalized through the same idempotent transaction every other exit
    path uses.

    S09: `attempt_id` is this request's own preallocated attempt, minted
    before this call. Returns `(run_id, plan_id, attempt_id, started)` --
    on attach, the returned `attempt_id` is the *admitted executor's own*
    stored attempt (durable, never a best-effort disk lookup or the losing
    request's own minted value)."""
    admission = ctx.mutations.admit(
        project_id,
        execution_identity=execution_identity,
        slot_id=slot_id,
        operation_id=operation_id,
        run_id=run_id,
        plan_id=plan_id,
        owner_instance_id=ctx.owner_instance_id,
        attempt_id=attempt_id,
    )
    if admission.conflict:
        raise ScanConflictError(
            project_id, admission.execution_identity, admission.run_id
        )
    if not admission.started:
        return admission.run_id, admission.plan_id, admission.attempt_id, False
    ctx.scan_runs.register(project_id, run_id=run_id, plan_id=plan_id, thread=thread)
    try:
        thread.start()
    except BaseException:  # noqa: BLE001 -- a launch failure is re-raised as
        # a structured 503 below; the admission row it already committed must
        # be terminalized first, whatever the failure was.
        ctx.outcomes.submit(
            slot_id,
            operation_id=operation_id,
            payload={
                "status": "error",
                "code": "thread_launch_failed",
                "message": "background worker thread could not be launched",
            },
        )
        raise _ActionDenied(
            503,
            "unavailable",
            "background worker thread could not be launched",
        ) from None
    return run_id, plan_id, attempt_id, True


def _resolved_operation_id(ctx: DashboardContext, operation_id: str) -> str:
    """Follow the durable attachment chain to the real executing
    operation_id (P69-02.2e/f); an operation_id with no attachment record
    resolves to itself."""
    return ctx.mutations.resolve_attachment(operation_id)


def _operation_project_id(ctx: DashboardContext, operation_id: str) -> str | None:
    """The project the (attachment-resolved) operation_id actually belongs
    to, or None if unknown -- used to 404 an operation_id requested through
    the wrong project without distinguishing that case from unknown."""
    return ctx.mutations.operation_project_id(_resolved_operation_id(ctx, operation_id))


# --- P69-03.2a-c: unify every scan producer into one publication path -------


_UNAVAILABLE_SOURCE_IDENTITY = "source-identity-unavailable"


def _manifest_scan_provenance(
    manifest: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """M02 bullet 1: the scalar `ProjectRecord.source_identity` a publish or
    hydrate uses must be a deterministic aggregate digest derived from the
    manifest's own content-derived `source_identity` object (set by
    `_finalize_attempt`'s `_source_identity(digests, root)` in
    `project_run.py`), never a live re-scan of the current tree at publish
    time -- `_source_signature(root)` is deliberately the *pre-execution*
    cheap guard, not a provenance certificate (project_run.py's own
    docstring). A manifest with no persisted identity object (a legacy
    attempt, or CHECK_SUITE before this fix) has genuinely unavailable
    provenance -- it gets the fixed unavailable sentinel rather than a live
    substitute, per Fix bullet 1's `Remove live _source_signature(root)
    fallback for completed attempts`. Returns `(scalar_identity,
    full_provenance_object)`; the full object is persisted separately as
    `scan_provenance` (never assigned into the scalar identity field)."""
    provenance = dict((manifest or {}).get("source_identity") or {})
    if not provenance:
        return _UNAVAILABLE_SOURCE_IDENTITY, {}
    digest = hashlib.sha256(
        json.dumps(provenance, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest, provenance


def _manifest_file_inventory(
    manifest: dict[str, Any], root: Path
) -> tuple[list[dict[str, str]], bool]:
    """M03 Fix bullet 3: a manifest with the `file_inventory` key present --
    even an empty list, a real if empty persisted inventory -- keeps today's
    behavior unchanged (`or _scan_file_inventory(root)`, since an empty list
    is falsy). A manifest with the key genuinely absent (a legacy attempt
    written before this field existed) has no known inventory and must
    expose that rather than silently substituting a live rewalk of whatever
    files happen to be present now -- the same missing-vs-substituted
    distinction `_manifest_scan_provenance` already applies to
    `source_identity`. Returns `(inventory, missing)`."""
    if "file_inventory" not in manifest:
        return [], True
    return manifest.get("file_inventory") or _scan_file_inventory(root), False


def _content_digests(root: Path, inventory: list[dict[str, str]]) -> dict[str, str]:
    """M02 bullet 2: per-file sha256 digests of `inventory`'s live tree,
    for `_source_identity`'s aggregate content identity -- CHECK_SUITE has
    no staged copy to read digests back from (unlike the real scan
    pipeline's `_finalize_attempt`), so this hashes the exact files just
    consumed at manifest-write time. A file that vanishes between listing
    and hashing is skipped rather than failing the whole publish."""
    digests: dict[str, str] = {}
    for entry in inventory:
        path = root / entry["path"]
        try:
            digests[entry["path"]] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
    return digests


def _snapshot_from_scan_result(
    project_id: str,
    result: Any,
    *,
    file_inventory: list[dict[str, str]],
    existing_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """P69-03.2a: one adapter unifying every producer's return shape into the
    map's snapshot contract (`project_map._build_full_graph`'s
    `files`/`findings`/`memories`/`agents`) -- `execute_scan`/`resume_scan_run`
    hand back a `ScanRun` (`.aggregate` attribute), `rescan_project_run` hands
    back `{"run": ScanRun.to_dict(), "comparison": ...}`, and CHECK_SUITE's
    initial-launch scan hands back a bare aggregate `ToolResult` -- one
    conversion path for all three, not a special case per call site. Memory
    and agent data are never derived from a scan result; they carry forward
    from whatever this project's snapshot already published (a scan doesn't
    touch them, per the snapshot lifecycle: `sequence` still bumps even when
    only `memories`/`agents` change, via `bump_sequence`/`refresh_memories`,
    never through this function)."""
    if isinstance(result, dict) and "run" in result:
        aggregate = dict((result["run"] or {}).get("aggregate") or {})
    elif hasattr(result, "aggregate"):
        aggregate = dict(result.aggregate)
    else:
        aggregate = dict(result)
    # `project_map._build_full_graph` reads each finding's opaque `id`
    # (matching `tests/fixtures/dashboard/project_a.json`'s own contract);
    # the real scan pipeline's own finding identity field is `finding_id`
    # (`_finding_id()`, `_build_scans_section`'s `if f.get("finding_id")`
    # filter) -- alias it in, never a second identity scheme.
    findings = [
        dict(finding, id=finding.get("finding_id") or finding.get("id"))
        for finding in aggregate.get("findings") or []
    ]
    prior = existing_snapshot or {}
    # M01 bullet 3: `memories`/`agents` are deliberately never carried
    # forward from `existing_snapshot` here (a pre-lock read) -- they are
    # scan-owned-field-disjoint data `ProjectRegistry.publish_scan_result`
    # merges from its own lock-current record instead, so a concurrent
    # `refresh_memories` between this adapter running and the eventual
    # publish is never lost. This function returns scan-owned fields only.
    return {
        "schema_version": 1,
        "project_id": project_id,
        "root": prior.get("root"),
        "files": file_inventory,
        "findings": findings,
    }


def _publish_scan_snapshot(
    ctx: DashboardContext,
    project_id: str,
    root: Path,
    result: Any,
    *,
    generation: int | None = None,
    run_id: str = "",
    attempt_id: str = "",
    file_inventory: list[dict[str, str]] | None = None,
) -> None:
    """P69-03.2c glue shared by `scan_start`/`scan_resume`/`rescan` (and
    CHECK_SUITE's own initial-launch scan via `publish_check_suite_scan`
    below): adapts the producer's result, computes the file inventory (or
    reuses `file_inventory` when the caller already walked the tree, so one
    publish walks it once), and publishes both atomically through `ProjectRegistry.publish_scan_result` --
    a failed or partial `run_state` is still published here (the map must
    render what actually completed, never silently drop the publish just
    because the run wasn't a full clean pass).

    P69-03m: `generation` is the value this job's dispatcher allocated at
    acceptance. Recording the durable published pointer happens *only* after
    the in-memory publish actually won its generation check -- allocation (at
    acceptance) and pointer recording (after a real publish) are two different
    operations at two different times, never one upsert."""
    record = ctx.projects.get(project_id)
    existing = record.snapshot if record is not None else None
    manifest = (
        load_run_manifest(root, run_id, attempt_id=attempt_id or None)
        if run_id
        else None
    )
    if run_id and attempt_id:
        # M04 bullets 1-2: real producer connection -- catch up this
        # project's durable `/events` stream with every candidate progress
        # event already durable in this attempt's own `events.json`
        # (`load_scan_events`, the existing event sink), instead of the
        # dashboard ledger only ever receiving status transitions. Reads
        # the full attempt log every time (not just a tail), so a restart
        # between a candidate's log write and this ingestion still catches
        # up idempotently on the next publish.
        ctx.mutations.ingest_attempt_events(
            project_id,
            run_id,
            attempt_id,
            load_scan_events(root, run_id, attempt_id).get("events") or [],
        )
    source_identity, scan_provenance = _manifest_scan_provenance(manifest)
    snapshot = _snapshot_from_scan_result(
        project_id,
        result,
        file_inventory=(
            file_inventory if file_inventory is not None else _scan_file_inventory(root)
        ),
        existing_snapshot=existing,
    )
    snapshot["scan_provenance"] = scan_provenance
    published = ctx.projects.publish_scan_result(
        project_id,
        snapshot=snapshot,
        source_identity=source_identity,
        generation=generation,
    )
    if generation is not None and run_id and attempt_id:
        _record_manifest_publication(
            root, run_id, attempt_id, "published" if published else "superseded"
        )
    if published and generation is not None and run_id:
        ctx.mutations.record_published_scan(project_id, generation, run_id, attempt_id)


def _record_manifest_publication(
    root: Path, run_id: str, attempt_id: str, outcome: str
) -> None:
    """P69-03v: the per-attempt publication outcome -- a cross-phase
    requirement Phase 68's P68-04 depends on -- written directly into that
    attempt's own manifest, not `ProjectRegistry` (per-process, in-memory,
    lost on restart). `load_run_manifest` is already the mechanism every
    server process serving this project reads from, so this manifest write
    is what makes the outcome visible to every other process, including one
    that only attached via the durable admission table and never executed
    the work itself. `outcome` is `"published"` (this attempt's generation
    won `publish_scan_result`'s existing check) or `"superseded"` (this
    attempt reached `publish_scan_result` but a different, later-accepted
    attempt had already published first) -- an attempt that never reaches
    `publish_scan_result` correctly stays absent from its own manifest
    (`"not_yet"`, resolved by the reader from the missing field, never
    written here)."""
    manifest = load_run_manifest(root, run_id, attempt_id=attempt_id)
    if manifest is None:
        return
    manifest["publication"] = outcome
    manifest["published_at"] = datetime.now(UTC).isoformat()
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    atomic_write_bytes(
        root,
        _MANIFEST_RELATIVE.format(run_id=run_id, attempt_id=attempt_id),
        manifest_bytes,
    )


def _hydrate_published_scan(ctx: DashboardContext, project_id: str) -> None:
    """P69-03o: a second server process (or this one after a restart) that
    never executed the currently-published run still serves its own stale or
    empty `record.snapshot` through `section=map` -- the attempt's own
    `publication` field being correct on disk hydrates nothing in *this*
    registry.

    Reads the durable pointer first to learn which `(run_id, attempt_id)` is
    actually published (never scanning run directories, never "whichever
    attempt is latest" -- a later unpublished attempt of the same run, a
    resume still in progress or one that failed, would otherwise shadow the
    published one), reconstructs the snapshot through the exact same
    `_snapshot_from_scan_result` adapter a live execution result goes
    through, and republishes locally via `publish_scan_result`. A hydration
    that has fallen behind a newer local publish loses that publish's own
    existing generation check -- no separate staleness mechanism."""
    record = ctx.projects.get_published(project_id)
    if record is None:
        return
    pointer = ctx.mutations.published_pointer(project_id)
    if pointer is None or pointer["published_generation"] <= record.scan_generation:
        return
    root = Path(resolve_project(project_id)["root"])
    manifest = load_run_manifest(
        root, pointer["run_id"], attempt_id=pointer["attempt_id"] or None
    )
    if manifest is None:
        return
    # `file_inventory` is persisted into the manifest by P69-03b; until that
    # lands, the hydrating server reads the same project root off the shared
    # disk it already reads the manifest from.
    source_identity, scan_provenance = _manifest_scan_provenance(manifest)
    inventory, inventory_missing = _manifest_file_inventory(manifest, root)
    snapshot = _snapshot_from_scan_result(
        project_id,
        {"run": manifest},
        file_inventory=inventory,
        existing_snapshot=record.snapshot,
    )
    snapshot["scan_provenance"] = scan_provenance
    snapshot["file_inventory_missing"] = inventory_missing
    ctx.projects.publish_scan_result(
        project_id,
        snapshot=snapshot,
        source_identity=source_identity,
        generation=pointer["published_generation"],
    )


def _sync_current_map(ctx: DashboardContext, project_id: str) -> None:
    """P69-03o: current-map staleness against mutation this registry never
    saw -- a standalone TUI invocation, a bare CLI memory command, a second
    dashboard server, or this server's own restart. Both drifts are checked
    on the current-map request path: the memory store's real committed
    generation against the published `memory_generation`, and the durable
    published scan pointer against this server's own `scan_generation`.
    Failures here never break the map request -- a drift check that cannot
    run leaves the last-published data in place, which is exactly today's
    behaviour."""
    with suppress(Exception):
        _hydrate_published_scan(ctx, project_id)
    with suppress(Exception):
        record = ctx.projects.get_published(project_id)
        if record is None:
            return
        root = Path(resolve_project(project_id)["root"])
        # R20.G8: a drift check reads only; it never creates or migrates memory.db.
        view, _state = TypedArtifactStore.open_readonly_view(root)
        if view is None:
            return
        try:
            generation = view.current_generation()
        finally:
            view.close()
        if generation > record.memory_generation:
            _refresh_project_memories(ctx, project_id, root)


def _historical_map_snapshot(
    root: Path,
    project_id: str,
    record: ProjectRecord,
    run_id: str,
    attempt_id: str | None,
) -> dict[str, Any] | None:
    """`_build_historical_map_snapshot`'s snapshot alone."""
    snapshot, _reusable = _build_historical_map_snapshot(
        root, project_id, record, run_id, attempt_id
    )
    return snapshot


def _historical_map_snapshot_reused(
    ctx: DashboardContext,
    root: Path,
    project_id: str,
    record: ProjectRecord,
    run_id: str,
    attempt_id: str | None,
) -> dict[str, Any] | None:
    """`_historical_map_snapshot`, reusing this server's last reusable view
    while its manifest file is unchanged (same mtime/size) and the record's
    root is the same -- so paging a historical group does not reload and
    rebuild the attempt on every page. The key is taken after the build,
    which may itself persist the frozen memory/agent data into the manifest.
    The reused snapshot is shared: map callers only read it."""
    manifest_path = root / _MANIFEST_RELATIVE.format(
        run_id=run_id, attempt_id=attempt_id
    )

    def _key() -> tuple[Any, ...] | None:
        try:
            stat = manifest_path.stat()
        except OSError:
            return None
        return (
            project_id,
            run_id,
            attempt_id,
            stat.st_mtime_ns,
            stat.st_size,
            record.snapshot.get("root"),
        )

    memo = ctx.historical_map_memo
    key = _key()
    if memo is not None and key is not None and memo[0] == key:
        return memo[1]
    snapshot, reusable = _build_historical_map_snapshot(
        root, project_id, record, run_id, attempt_id
    )
    key = _key()
    if snapshot is not None and reusable and key is not None:
        ctx.historical_map_memo = (key, snapshot)
    return snapshot


def _build_historical_map_snapshot(
    root: Path,
    project_id: str,
    record: ProjectRecord,
    run_id: str,
    attempt_id: str | None,
) -> tuple[dict[str, Any] | None, bool]:
    """P69-03r/s: a caller-selected historical run, pinned to that run's
    exact attempt (subsection r -- never bare `run_id`, since a later resume
    mints a new attempt under the same `run_id`), with memory/agent data
    frozen as of the first request for this exact `(run_id, attempt_id)`
    (subsection s), never a live merge of whatever the registry currently
    holds -- a later memory edit/delete or a later resume changes neither
    this historical view nor the current map. The frozen data is persisted
    into the attempt's own manifest (the same cross-process-readable record
    subsection v's publication outcome uses), so a restart or cache eviction
    reconstructs the identical graph rather than freezing a second, later
    moment. `(None, False)` if the run/attempt is unknown.

    The flag says whether the view may be reused while the manifest file is
    unchanged: a present but empty `file_inventory` is rewalked from the
    live tree on every build (`_manifest_file_inventory`), so it never is."""
    manifest = load_run_manifest(root, run_id, attempt_id=attempt_id)
    if manifest is None:
        return None, False
    reusable = "file_inventory" not in manifest or bool(manifest["file_inventory"])
    frozen = manifest.get("historical_memory_agent_snapshot")
    if frozen is None:
        # First request for this exact attempt: freeze whatever this
        # registry's current view of memory/agent data holds right now (the
        # attempt's own completion-time data isn't separately captured
        # anywhere upstream of here) and persist it so every subsequent
        # request -- including after a restart -- reads the identical frozen
        # copy rather than re-deriving from live state.
        frozen = {
            "memories": list(record.snapshot.get("memories") or []),
            "agents": list(record.snapshot.get("agents") or []),
        }
        manifest["historical_memory_agent_snapshot"] = frozen
        manifest_bytes = (
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        atomic_write_bytes(
            root,
            _MANIFEST_RELATIVE.format(
                run_id=manifest["run_id"], attempt_id=manifest["attempt_id"]
            ),
            manifest_bytes,
        )
    # A memory deleted from the live store after freezing stays visible here
    # unchanged -- `frozen["memories"]` is a persisted copy, not a live
    # reference, so it never silently vanishes from this historical view.
    inventory, inventory_missing = _manifest_file_inventory(manifest, root)
    snapshot = _snapshot_from_scan_result(
        project_id,
        {"run": manifest},
        file_inventory=inventory,
        existing_snapshot=None,
    )
    snapshot["memories"] = frozen["memories"]
    snapshot["agents"] = frozen["agents"]
    snapshot["root"] = record.snapshot.get("root")
    snapshot["file_inventory_missing"] = inventory_missing
    return snapshot, reusable


def capture_initial_scan_provenance(root: Path, project_id: str) -> tuple[str, str]:
    """P69-03k: `run_workflow_suite()` (the CHECK_SUITE initial-launch path
    `dashboard_cmd`'s `_run_initial_scan` drives) calls no attempt-header/
    provenance capture at all -- unlike `execute_scan`/`resume_scan_run`/
    `rescan_project_run`, which all persist `_write_attempt_header()`'s
    pre-execution `source_signature` before their first candidate runs
    (`_execute_attempt_locked`, project_run.py). CHECK_SUITE bypasses that
    pipeline entirely, so it never got this. Mints the run/attempt identity
    this launch will use and writes the identical header *before* the
    caller invokes `run_workflow_suite` -- pass the returned
    `(run_id, attempt_id)` into `publish_check_suite_scan` so the terminal
    manifest names the exact same attempt this header describes."""
    run_id = str(uuid.uuid4())
    attempt_id = "1"
    _write_attempt_header(root, run_id, attempt_id, "check_suite", project_id)
    return run_id, attempt_id


def publish_check_suite_scan(
    ctx: DashboardContext,
    project_id: str,
    root: Path,
    aggregate: ToolResult,
    *,
    run_id: str | None = None,
    attempt_id: str | None = None,
    scan_generation: int | None = None,
    artifact_snapshots: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> tuple[str, str]:
    """P69-03.2: CHECK_SUITE's initial-launch scan (`dashboard_cmd`) has no
    `ScanPlan`/manifest of its own -- `run_workflow_suite()` returns a bare
    aggregate `ToolResult` with no run/attempt identity. Mints one here (or
    reuses the pair `capture_initial_scan_provenance` already minted before
    execution, per P69-03k -- pass it through so the pre-execution header and
    this terminal manifest agree on the same attempt; existing callers that
    pass neither keep today's mint-here behavior), assigns each finding a
    real `finding_id` (`aggregate_results()` only ever sets `provenance`,
    never `finding_id` -- without this, every CHECK_SUITE finding is
    silently invisible to `_build_scans_section`'s `if f.get("finding_id")`
    filter), persists a minimal terminal manifest through the exact same
    `atomic_write_bytes`/`_MANIFEST_RELATIVE` path every other scan's
    manifest lands at (so `_build_scans_section` finds it via
    `_list_run_ids`/`load_run_manifest`), and publishes through the exact
    same `_publish_scan_snapshot` path `scan_start`/`scan_resume`/`rescan`
    use -- never a second, divergent publication route.

    P69-03m: `scan_generation` is this launch's acceptance-allocated ordering
    number (`cli.py::_run_initial_scan` allocates it before
    `run_workflow_suite` starts, so a slow initial scan can never overwrite a
    faster user-requested scan that was accepted after it). A caller that
    passes none allocates here instead -- still ordered, just from publish
    time rather than launch time.

    M12 Fix item 2 (CHECK_SUITE per-child capture parity): `artifact_snapshots`
    is `{tool_name: {declared_path: snapshot_entry}}`, already captured by
    the caller's own `on_tool_complete` closure (mirroring `project_run.py`'s
    `_capture_artifact_snapshots`) as each child finished -- folded here into
    a `scheduled` list shaped exactly like a real scan manifest's own
    (`candidate_id`/`artifact_snapshots`), so the artifact-download route's
    manifest lookup (`_read_artifact_content_page`) works identically for a
    CHECK_SUITE-produced artifact reference."""
    run_id = run_id or str(uuid.uuid4())
    attempt_id = attempt_id or "1"
    if scan_generation is None:
        scan_generation = ctx.mutations.allocate_scan_generation(project_id)
    for finding in aggregate.get("findings") or []:
        provenance = str(finding.get("provenance") or "")
        tool, _sep, engine_part = provenance.partition("/")
        engine = None if engine_part in ("", "no-engine") else engine_part
        cast(dict[str, Any], finding)["finding_id"] = _finding_id(tool, engine, finding)
    # M02 bullet 2 / M03: CHECK_SUITE's own manifest previously carried no
    # content identity, inventory, or Git provenance at all (unlike
    # `_build_manifest`'s real scan pipeline) -- it has no staged tree to
    # read digests back from, so this captures the live tree's content
    # identity/inventory at this exact moment, the actual bytes CHECK_SUITE
    # just consumed.
    file_inventory = _scan_file_inventory(root)
    digests = _content_digests(root, file_inventory)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "run_state": _check_suite_run_state(aggregate),
        "created_at": datetime.now(UTC).isoformat(),
        "aggregate": dict(aggregate),
        "totals": {"finding_count": len(aggregate.get("findings") or [])},
        "file_inventory": file_inventory,
        "source_identity": _source_identity(digests, root),
        "scan_generation": scan_generation,
        # M12 Fix item 2: same "scheduled"/"candidate_id"/"artifact_snapshots"
        # shape a real scan manifest's own `CandidateResult.to_dict()`
        # produces, so `_read_artifact_content_page` resolves a CHECK_SUITE
        # artifact reference exactly like any other.
        "scheduled": [
            {"candidate_id": tool_name, "artifact_snapshots": dict(snapshots)}
            for tool_name, snapshots in (artifact_snapshots or {}).items()
            if snapshots
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    atomic_write_bytes(
        root,
        _MANIFEST_RELATIVE.format(run_id=run_id, attempt_id=attempt_id),
        manifest_bytes,
    )
    _publish_scan_snapshot(
        ctx,
        project_id,
        root,
        aggregate,
        generation=scan_generation,
        run_id=run_id,
        attempt_id=attempt_id,
        file_inventory=file_inventory,
    )
    return run_id, attempt_id


def _check_suite_run_state(aggregate: ToolResult) -> str:
    """T17 R17.4: `cancelled` for a cancelled run, `incomplete` when any step
    did not execute (not_run/cancelled) or ended skipped or error, else
    `completed` -- never a clean completion for partial work."""
    metadata = aggregate.get("metadata") or {}
    if metadata.get("cancelled"):
        return "cancelled"
    for child in metadata.get("children") or []:
        disposition = (child.get("execution") or {}).get("disposition", "executed")
        if disposition != "executed" or child.get("status") in ("skipped", "error"):
            return "incomplete"
    return "completed"


def _dispatch_check_suite(
    ctx: DashboardContext,
    project_id: str,
    *,
    operation_id: str = "",
) -> tuple[int, dict[str, Any]]:
    """P69-06e: run `CHECK_SUITE` inside *this* dashboard process, on behalf
    of a TUI/CLI caller that reached us through the private control channel.

    A same-process function call cannot cross a process boundary -- calling
    an "internal dashboard-server function" from `tui.py` would execute in
    the TUI's own process against no `DashboardContext` at all. `scan_start`
    is equally wrong for this: it demands an explicitly-reviewed staged
    `plan_id` plus `cache_write`/`artifact_write` grants, none of which this
    lighter suite has, so routing through it means either fabricating both or
    silently substituting a full scan.

    So this is its own operation, but never its own *mechanism*: admission
    (`_admit_and_launch` -> `ctx.mutations.admit()`), supervision
    (`_run_supervised`), terminal outcome (`ctx.outcomes`), and publication
    (`publish_check_suite_scan`) are the exact shared primitives every other
    async operation uses. Its execution identity is
    `check_suite:<suite name>`, so a concurrent full scan conflicts (rather
    than silently attaching to a different operation) through that same one
    admission check, and a second CHECK_SUITE request attaches to the
    already-running one.
    """
    root = Path(resolve_project(project_id)["root"])
    # P69-03k: the pre-execution provenance header lands before a single
    # tool runs, exactly as `cli.py::_run_initial_scan` already does.
    run_id, attempt_id = capture_initial_scan_provenance(root, project_id)
    scan_generation = ctx.mutations.allocate_scan_generation(project_id)
    slot_id = operation_id or uuid.uuid4().hex
    identity = f"check_suite:{CHECK_SUITE.name}"
    cancelled = threading.Event()

    def _cancel_check() -> bool:
        # T044: nothing ever sets `cancelled` -- also consult the same
        # attempt-scoped filesystem cooperative-cancel marker normal scans
        # already use, so `scan_cancel` (which writes that marker for any
        # run_id/attempt_id, including this suite's) actually reaches a
        # dashboard-owned CHECK_SUITE run.
        return cancelled.is_set() or _cancel_requested(root, run_id, attempt_id)

    # M12 Fix item 2: CHECK_SUITE per-child capture parity -- snapshot each
    # child's declared artifact bytes the moment it completes, before the
    # next tool in the suite can run and physically overwrite the same path.
    check_suite_snapshots: dict[str, dict[str, dict[str, Any]]] = {}

    def _on_tool_complete(child: ToolResult) -> None:
        # P69-06f: each completed tool is durable before the suite finishes,
        # so a cancel or a kill leaves a reconstructable partial result.
        with suppress(Exception):
            ctx.mutations.record_status_transition(
                operation_id,
                "running",
                {
                    "suite": CHECK_SUITE.name,
                    "tool": child.get("tool"),
                    "status": child.get("status"),
                    # T17: executed, or cancelled mid-step.
                    "disposition": (
                        (child.get("metadata") or {}).get("execution") or {}
                    ).get("disposition", "executed"),
                },
            )
        tool_name = str(child.get("tool") or "")
        if tool_name:
            check_suite_snapshots[tool_name] = _capture_artifact_snapshots(
                root, run_id, attempt_id, tool_name, child
            )

    def _body() -> dict[str, Any]:
        aggregate = run_workflow_suite(
            suite=CHECK_SUITE,
            path=root,
            # CHECK_SUITE negotiates no grants of its own -- denied by
            # default, never `scan_start`'s cache_write/artifact_write.
            permissions=ExecutionPermissions(),
            cancel_check=_cancel_check,
            on_tool_complete=_on_tool_complete,
            owner_instance_id=ctx.owner_instance_id,
            run_id=run_id,
        )
        payload = {
            "status": "success",
            "suite": CHECK_SUITE.name,
            "run_id": run_id,
            "cancelled": bool((aggregate.get("metadata") or {}).get("cancelled")),
        }
        # T037: release this project's admission slot (and terminalize the
        # ledger) *before* the snapshot below becomes client-visible, not
        # after this thread returns -- closes the window where a same-project
        # rescan/scan_start admitted right after publish sees this row still
        # occupied (spurious 409), and where a reader's active_run_id still
        # names this run after its snapshot is already visible.
        # `_run_supervised`'s own `finally` still calls this again on exit;
        # both `ctx.outcomes.submit` and the ledger release it wraps are
        # idempotent, so the repeat is a safe no-op, not a double-release.
        ctx.outcomes.submit(slot_id, operation_id=operation_id, payload=payload)
        publish_check_suite_scan(
            ctx,
            project_id,
            root,
            aggregate,
            run_id=run_id,
            attempt_id=attempt_id,
            scan_generation=scan_generation,
            artifact_snapshots=check_suite_snapshots,
        )
        return payload

    thread = threading.Thread(
        target=_run_supervised,
        args=(ctx, slot_id, operation_id, _body),
        daemon=True,
    )
    attached_run_id, attached_plan_id, attached_attempt_id, started = _admit_and_launch(
        ctx,
        project_id,
        execution_identity=identity,
        slot_id=slot_id,
        operation_id=operation_id,
        run_id=run_id,
        plan_id=identity,
        thread=thread,
        attempt_id=attempt_id,
    )
    return 202, {
        "operation_id": operation_id,
        "suite": CHECK_SUITE.name,
        "run_id": attached_run_id,
        "plan_id": attached_plan_id,
        "attempt_id": attached_attempt_id or attempt_id,
        "attached_to_existing": not started,
    }


def _dispatch_scan_start(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    *,
    operation_id: str = "",
    expected: dict[str, Any] | None = None,
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
    attempt_id = str(uuid.uuid4())
    slot_id = operation_id or uuid.uuid4().hex
    # P69-03m: allocated at acceptance, from the durable cross-process
    # counter -- a scan has no other natural sequence, and a per-process
    # counter could not order this publish against another server's.
    scan_generation = ctx.mutations.allocate_scan_generation(project_id)

    def _body() -> dict[str, Any]:
        conflict = _revalidate_expected_at_execution(ctx, project_id, expected)
        if conflict is not None:
            return conflict
        run = execute_scan(
            staged_plan, run_id=run_id, attempt_id=attempt_id, permissions=permissions
        )
        payload = {
            "status": "success",
            "run_id": run.run_id,
            "attempt_id": run.attempt_id,
        }
        # T037: release before publish -- see _dispatch_check_suite._body.
        ctx.outcomes.submit(slot_id, operation_id=operation_id, payload=payload)
        _publish_scan_snapshot(
            ctx,
            project_id,
            Path(run.root),
            run,
            generation=scan_generation,
            run_id=run.run_id,
            attempt_id=run.attempt_id,
        )
        return payload

    thread = threading.Thread(
        target=_run_supervised,
        args=(ctx, slot_id, operation_id, _body),
        daemon=True,
    )
    attached_run_id, attached_plan_id, attached_attempt_id, started = _admit_and_launch(
        ctx,
        project_id,
        execution_identity=f"scan_start:{plan_id}",
        slot_id=slot_id,
        operation_id=operation_id,
        run_id=run_id,
        plan_id=plan_id,
        thread=thread,
        attempt_id=attempt_id,
    )
    # S09: the admission table now durably tracks the winning executor's own
    # attempt_id, so an attach resolves to that stored value -- never a
    # best-effort disk read of "whatever the latest attempt happens to be".
    resolved_attempt_id = attached_attempt_id or attempt_id
    return 202, {
        "operation_id": operation_id,
        "run_id": attached_run_id,
        "plan_id": attached_plan_id,
        "attempt_id": resolved_attempt_id,
        "attached_to_existing": not started,
    }


def _dispatch_scan_cancel(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Calls the exact shared `cancel_scan_run` cooperative marker -- the
    running job's own candidate loop stops at its next boundary and its
    already-executed candidates remain as real partial evidence.

    S10: `arguments.operation_id` (an accepted/attached caller's own logical
    operation id) resolves through the durable attachment chain to its real
    executor, then to that executor's currently-admitted run/attempt --
    never a bare `run_id` guess. `arguments.run_id` alone is retained as
    explicit legacy compatibility. An `operation_id` naming a different
    project, or no known operation at all, 404s uniformly rather than
    revealing which."""
    _require_grants(grants, "cache_write", operation="scan_cancel")
    run_id = arguments.get("run_id")
    operation_id = arguments.get("operation_id")
    attempt_id: str | None = None
    if operation_id is not None:
        if not isinstance(operation_id, str) or not operation_id:
            raise _ActionDenied(
                400,
                "malformed_request",
                "scan_cancel arguments.operation_id must be a non-empty string",
            )
        if _operation_project_id(ctx, operation_id) != project_id:
            raise _ActionDenied(404, "not_found", "unknown operation_id")
        resolved_operation_id = _resolved_operation_id(ctx, operation_id)
        status = ctx.mutations.get_operation_status(resolved_operation_id)
        if status is not None and status.get("status") == "terminal":
            # Already terminal: return its stored outcome rather than
            # attempting a fresh cancel against work that is already over.
            return 202, {
                "operation_id": operation_id,
                "run_id": run_id or "",
                "already_terminal": True,
                "cancel_requested_at": None,
            }
        admission = ctx.mutations.admission_for_project(project_id)
        if (
            admission is not None
            and admission.get("operation_id") == resolved_operation_id
        ):
            run_id = admission.get("run_id") or run_id
            attempt_id = admission.get("attempt_id") or None
    if not isinstance(run_id, str) or not run_id:
        raise _ActionDenied(
            400,
            "malformed_request",
            "scan_cancel requires arguments.run_id or arguments.operation_id",
        )
    payload = cancel_scan_run(project_id, run_id, attempt_id=attempt_id)
    return 202, {
        "operation_id": operation_id,
        "run_id": run_id,
        "attempt_id": payload.get("attempt_id"),
        "cancel_requested_at": payload["requested_at"],
    }


def _dispatch_scan_resume(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    *,
    operation_id: str = "",
    expected: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    _require_grants(grants, "cache_write", "artifact_write", operation="scan_resume")
    run_id = arguments.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise _ActionDenied(
            400, "malformed_request", "scan_resume requires arguments.run_id"
        )
    # P69-02j: captured synchronously here, before any background thread
    # runs, so a stale value discovered only later (a concurrent resume)
    # rejects with a real conflict instead of silently applying against a
    # baseline this request never actually reviewed. `None` means run_id is
    # unknown -- reject now rather than after the background thread's own
    # error handling swallows it.
    captured_attempt_id = latest_attempt_id(project_id, run_id)
    if captured_attempt_id is None:
        raise _ActionDenied(400, "malformed_request", f"unknown run_id: {run_id}")
    permissions = _permissions_from_grants(grants)
    new_attempt_id = str(uuid.uuid4())
    slot_id = operation_id or uuid.uuid4().hex
    scan_generation = ctx.mutations.allocate_scan_generation(project_id)

    def _body() -> dict[str, Any]:
        conflict = _revalidate_expected_at_execution(ctx, project_id, expected)
        if conflict is not None:
            return conflict
        run = resume_scan_run(
            project_id,
            run_id,
            permissions=permissions,
            attempt_id=new_attempt_id,
            expected_attempt_id=captured_attempt_id,
            owner_instance_id=ctx.owner_instance_id,
        )
        payload = {
            "status": "success",
            "run_id": run.run_id,
            "attempt_id": run.attempt_id,
        }
        # T037: release before publish -- see _dispatch_check_suite._body.
        ctx.outcomes.submit(slot_id, operation_id=operation_id, payload=payload)
        _publish_scan_snapshot(
            ctx,
            project_id,
            Path(run.root),
            run,
            generation=scan_generation,
            run_id=run.run_id,
            attempt_id=run.attempt_id,
        )
        return payload

    thread = threading.Thread(
        target=_run_supervised,
        args=(ctx, slot_id, operation_id, _body),
        daemon=True,
    )
    attached_run_id, _plan_id, attached_attempt_id, started = _admit_and_launch(
        ctx,
        project_id,
        # P69-02j: reuses round-8's precedent of repurposing the admission
        # table's plan_id-adjacent identity field for a non-plan execution
        # identity (there, CHECK_SUITE's suite id; here, `run_id` plus the
        # captured attempt id) -- a resume's real identity is which specific
        # run *and attempt* is being acted on, never bare run_id, and the
        # op-type prefix keeps a resume/rescan sharing a run_id from
        # colliding.
        execution_identity=f"scan_resume:{run_id}:{captured_attempt_id}",
        slot_id=slot_id,
        operation_id=operation_id,
        run_id=run_id,
        plan_id="",
        thread=thread,
        attempt_id=new_attempt_id,
    )
    resolved_attempt_id = attached_attempt_id or new_attempt_id
    return 202, {
        "operation_id": operation_id,
        "run_id": attached_run_id,
        "attempt_id": resolved_attempt_id,
        "attached_to_existing": not started,
    }


def _dispatch_rescan(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    *,
    operation_id: str = "",
    expected: dict[str, Any] | None = None,
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
    root = Path(resolve_project(project_id)["root"])
    # P69-02j: captured synchronously here, before any background thread
    # runs -- the same baseline-manifest read rescan_project_run performs
    # internally, done once by the dispatcher first so a stale value is
    # rejected as a real conflict rather than silently re-derived later.
    baseline_manifest = load_run_manifest(root, baseline_run_id)
    if baseline_manifest is None:
        raise _ActionDenied(
            400, "malformed_request", f"unknown run_id: {baseline_run_id}"
        )
    captured_attempt_id = baseline_manifest.get("attempt_id")
    # T28-B: a client that reviewed a specific attempt names it; a newer
    # attempt published since that review refuses the rescan before any effect.
    reviewed_attempt_id = arguments.get("expected_attempt_id")
    if reviewed_attempt_id is not None and reviewed_attempt_id != captured_attempt_id:
        raise _ActionDenied(
            409,
            "RESUME_STALE",
            f"run {baseline_run_id} changed since review: reviewed attempt "
            f"{reviewed_attempt_id}, current attempt {captured_attempt_id}",
        )
    permissions = _permissions_from_grants(grants)
    new_run_id = str(uuid.uuid4())
    new_attempt_id = str(uuid.uuid4())
    slot_id = operation_id or uuid.uuid4().hex
    scan_generation = ctx.mutations.allocate_scan_generation(project_id)

    def _body() -> dict[str, Any]:
        conflict = _revalidate_expected_at_execution(ctx, project_id, expected)
        if conflict is not None:
            return conflict
        result = rescan_project_run(
            project_id,
            baseline_run_id,
            permissions=permissions,
            new_run_id=new_run_id,
            attempt_id=new_attempt_id,
            expected_attempt_id=captured_attempt_id,
            owner_instance_id=ctx.owner_instance_id,
        )
        new_run = result.get("run") or {}
        payload = {
            "status": "success",
            "run_id": new_run.get("run_id"),
            "attempt_id": new_run.get("attempt_id"),
        }
        # T037: release before publish -- see _dispatch_check_suite._body.
        ctx.outcomes.submit(slot_id, operation_id=operation_id, payload=payload)
        _publish_scan_snapshot(
            ctx,
            project_id,
            root,
            result,
            generation=scan_generation,
            run_id=str(new_run.get("run_id") or new_run_id),
            attempt_id=str(new_run.get("attempt_id") or new_attempt_id),
        )
        return payload

    thread = threading.Thread(
        target=_run_supervised,
        args=(ctx, slot_id, operation_id, _body),
        daemon=True,
    )
    attached_run_id, _plan_id, attached_attempt_id, started = _admit_and_launch(
        ctx,
        project_id,
        # P69-02j: same op-type-prefixed, attempt-pinned identity pattern as
        # scan_resume -- a rescan's real identity is which specific baseline
        # run *and attempt* is being re-evaluated, never bare run_id.
        execution_identity=f"rescan:{baseline_run_id}:{captured_attempt_id}",
        slot_id=slot_id,
        operation_id=operation_id,
        run_id=baseline_run_id,
        plan_id="",
        thread=thread,
        attempt_id=new_attempt_id,
    )
    resolved_attempt_id = attached_attempt_id or new_attempt_id
    return 202, {
        "operation_id": operation_id,
        "baseline_run_id": attached_run_id,
        "run_id": new_run_id,
        "attempt_id": resolved_attempt_id,
        "attached_to_existing": not started,
    }


def _handoff_preview_hash(handoff: ScanHandoff) -> str:
    """P69-02.2n/S06: canonical hash binding the *complete* reviewed handoff
    envelope -- project, run, exact attempt, agent, exact selected findings
    and the packet content built from them (so an evidence artifact's
    version changing between preview and send changes the packet, and so
    the hash), current source identity, session allowlist, and budgets --
    not `_build_packet()`'s own top-level fields alone. `handoff_preview`
    returns this as the response's `handoff_id`; `handoff_send` recomputes
    it server-side from the identical inputs and rejects with 409 if it no
    longer matches (tamper/staleness detection)."""
    envelope = {
        "project_id": handoff.project_id,
        "run_id": handoff.run_id,
        "attempt_id": handoff.attempt_id,
        "agent_id": handoff.agent_id,
        "finding_ids": sorted(handoff.finding_ids),
        "packet": handoff.packet,
        "source_signature": handoff.source_signature,
        "session_allowlist": [handoff.root],
        "max_tokens": handoff.packet.get("max_tokens"),
        "max_bytes": handoff.packet.get("max_bytes"),
        "granted_actions": sorted(handoff.granted_actions),
        "acceptance_checks": sorted(handoff.acceptance_checks),
    }
    return hashlib.sha256(
        json.dumps(envelope, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _dispatch_handoff_preview(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`rush_scan_handoff.prepare` (agent selection + bounded handoff
    preview). P69-02.2n: genuinely read-only -- `build_handoff(persist=
    False)` writes no `MemoryArtifact` and persists no session/descriptor,
    so no mutation grant is required. The response's `handoff_id` is the
    content hash `handoff_send` must echo back."""
    run_id = arguments.get("run_id")
    agent_id = arguments.get("agent_id")
    # S06: an explicit `attempt_id` pins the exact manifest the preview's
    # packet/hash is built from; omitted, `build_handoff` keeps its legacy
    # latest-attempt behavior (a pre-S06 caller that never sends one).
    attempt_id = arguments.get("attempt_id") or ""
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(agent_id, str)
        or not agent_id
        or not isinstance(attempt_id, str)
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
        persist=False,
        attempt_id=attempt_id,
    )
    body = handoff.to_dict()
    body["handoff_id"] = _handoff_preview_hash(handoff)
    return 200, body


def _dispatch_handoff_send(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    operation_id: str,
) -> tuple[int, dict[str, Any]]:
    """`rush_scan_handoff.dispatch`. P69-02.2n: takes the same
    (run_id/agent_id/finding_ids/max_tokens/max_bytes) a prior
    `handoff_preview` used, plus that preview's content-hash `handoff_id`;
    recomputes the identical preview server-side and rejects with 409 if
    the hash no longer matches (tamper/staleness), then persists for real
    and dispatches asynchronously, returning 202 immediately -- matching
    `scan_start`'s existing long-action lifecycle."""
    _require_grants(grants, "cache_write", "artifact_write", operation="handoff_send")
    run_id = arguments.get("run_id")
    agent_id = arguments.get("agent_id")
    # S06: optional for the same legacy-compatibility reason as
    # `_dispatch_handoff_preview` above -- when supplied it must exactly
    # match what the accepted preview was built from (enforced by the hash
    # comparison below, since it's part of the hashed envelope).
    attempt_id = arguments.get("attempt_id") or ""
    claimed_hash = arguments.get("handoff_id")
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(agent_id, str)
        or not agent_id
        or not isinstance(attempt_id, str)
        or not isinstance(claimed_hash, str)
        or not claimed_hash
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "handoff_send requires arguments.run_id, arguments.agent_id, and "
            "arguments.handoff_id from a prior handoff_preview",
        )
    finding_ids = tuple(arguments.get("finding_ids") or ())
    max_tokens = int(arguments.get("max_tokens", 2048))
    max_bytes = int(arguments.get("max_bytes", 8192))

    def _build_preview() -> ScanHandoff:
        return build_handoff(
            project_id,
            run_id,
            agent_id,
            finding_ids=finding_ids,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            persist=False,
            attempt_id=attempt_id,
        )

    preview = _build_preview()
    if _handoff_preview_hash(preview) != claimed_hash:
        raise _ActionDenied(
            409,
            "conflict",
            "handoff preview is stale or was tampered with; re-preview before sending",
        )
    root = Path(resolve_project(project_id)["root"])

    def _body() -> dict[str, Any]:
        # S07: revalidate the pinned attempt/envelope immediately before the
        # real effect -- the accept-time check above ran in the HTTP thread;
        # this is the independent, second check from inside the worker,
        # closing the gap during which the source/evidence backing this
        # exact attempt can go stale.
        try:
            fresh_preview = _build_preview()
        except ScanInvalidRequestError:
            return {
                "status": "conflict",
                "code": "stale_expected_identity",
                "message": "pinned run/attempt no longer exists at execution time",
            }
        if _handoff_preview_hash(fresh_preview) != claimed_hash:
            return {
                "status": "conflict",
                "code": "stale_expected_identity",
                "message": (
                    "handoff envelope changed between accept and execution; "
                    "re-preview before sending"
                ),
            }
        # S04: consume this operation's already-reserved effect ids rather
        # than letting `build_handoff` mint fresh receipt ids per sub-effect.
        reservation = ctx.mutations.get_reservation(operation_id)
        effect_ids = reservation["effect_ids"] if reservation else {}
        handoff = build_handoff(
            project_id,
            run_id,
            agent_id,
            finding_ids=finding_ids,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            persist=True,
            attempt_id=attempt_id,
            operation_id=operation_id,
            effect_ids=effect_ids,
            # T038: the only linkage from a dead owner_instance_id (S02's
            # reconcile_admissions) to this handoff if this process crashes
            # between prepare and dispatch.
            owner_instance_id=ctx.owner_instance_id,
        )
        # S05 bullet 3: this operation's already-reserved delivery receipt
        # id -- shared with `recover_prepared_handoff`'s claimed-recovery
        # path so the two never mint independent, conflicting receipts.
        dispatch_handoff(
            project_id,
            handoff.handoff_id,
            handoff.session_capability,
            delivery_receipt_id=effect_ids.get("delivery_transition", ""),
        )
        _refresh_project_memories(ctx, project_id, root)
        return {
            "status": "success",
            "handoff_id": handoff.handoff_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
        }

    thread = threading.Thread(
        target=_run_terminal_supervised, args=(ctx, operation_id, _body), daemon=True
    )
    thread.start()
    return 202, {
        "operation_id": operation_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "agent_id": agent_id,
    }


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

_TOOL_RESULT_UNAVAILABLE_STATUSES = frozenset({"skipped"})
# P69-02.2n: a stale-version memory edit/archive must return HTTP 409, never
# 200 with `data.status="fail"`.
_TOOL_RESULT_CONFLICT_CODES = frozenset({"E_VERSION"})


def _tool_result_response(result: ToolResult) -> tuple[int, dict[str, Any]]:
    """P69-02.2n: the shared HTTP-adapter-boundary mapping from a
    `ToolResult` to an HTTP response -- `status`/`findings`/`raw`/`metadata`
    stay exactly as `MemoryTool().run()` returned them (never re-wrapped or
    flattened), but a `skipped` `ToolResult` (the underlying engine/operation
    never actually ran) is never reported as an HTTP success, and a stale
    compare-and-swap version conflict is reported as a real 409."""
    body: dict[str, Any] = dict(result)
    raw = result.get("raw")
    code = raw.get("code") if isinstance(raw, dict) else None
    if code in _TOOL_RESULT_CONFLICT_CODES:
        status_code = 409
    elif result.get("status") in _TOOL_RESULT_UNAVAILABLE_STATUSES:
        status_code = 503
    else:
        status_code = 200
    return status_code, body


def _dispatch_memory_edit(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    effect_ids: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    if bool(arguments.get("apply")):
        _require_grants(grants, "cache_write", operation="memory_edit")
    root = Path(resolve_project(project_id)["root"])
    request: dict[str, Any] = {
        key: arguments[key]
        for key in (
            "scope",
            "id",
            "expected_version",
            "content",
            "apply",
            "owner_scope",
        )
        if key in arguments
    }
    # S04: consume the reserved `artifact_edit` effect id preallocated in
    # the same ledger transaction as this operation's reservation, never a
    # separate generic operation_id (which risks a mutation_receipts
    # PRIMARY-KEY clobber with an unrelated receipt).
    reserved = (effect_ids or {}).get("artifact_edit")
    if reserved:
        request["receipt_operation_id"] = reserved
    result = MemoryTool().run(
        root,
        operation="edit",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    status_code, body = _tool_result_response(result)
    _refresh_project_memories_if_store_exists(ctx, project_id, root)
    return status_code, body


def _dispatch_memory_archive(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    effect_ids: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    if bool(arguments.get("apply")):
        _require_grants(grants, "cache_write", operation="memory_archive")
    root = Path(resolve_project(project_id)["root"])
    request: dict[str, Any] = {
        key: arguments[key]
        for key in (
            "scope",
            "id",
            "expected_version",
            "apply",
            "archived",
            "owner_scope",
        )
        if key in arguments
    }
    # S04: reserved `artifact_archive` effect id, not a generic operation_id.
    reserved = (effect_ids or {}).get("artifact_archive")
    if reserved:
        request["receipt_operation_id"] = reserved
    result = MemoryTool().run(
        root,
        operation="archive",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    status_code, body = _tool_result_response(result)
    _refresh_project_memories_if_store_exists(ctx, project_id, root)
    return status_code, body


def _dispatch_memory_delete(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    effect_ids: dict[str, str] | None = None,
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
        for key in (
            "artifact_ids",
            "expected_revisions",
            "scope",
            "apply",
            "owner_scope",
        )
        if key in arguments
    }
    # S04: `_s04_effect_ids` reserves one `delete:<artifact_id>` id per
    # validated target (review doc's per-artifact spec). Thread the full
    # target_id -> reserved-id mapping through so `delete_batch` (memory/
    # store.py) writes one real receipt per target, not just a single
    # batch-wide one.
    target_ids = arguments.get("artifact_ids")
    receipt_ids: dict[str, str] = {}
    if isinstance(target_ids, list):
        for target_id in {str(t) for t in target_ids}:
            candidate = (effect_ids or {}).get(f"delete:{target_id}")
            if candidate:
                receipt_ids[target_id] = candidate
    if receipt_ids:
        request["receipt_operation_ids"] = receipt_ids
    result = MemoryTool().run(
        root,
        operation="delete",
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    status_code, body = _tool_result_response(result)
    _refresh_project_memories_if_store_exists(ctx, project_id, root)
    return status_code, body


def _dispatch_memory_promote(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    effect_ids: dict[str, str] | None = None,
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
    # S04: `MemoryTool.run`'s promote path consumes two independently-reserved
    # effect ids -- `candidate_create` for the candidate-write receipt and
    # `promotion` for the separate promotion-decision receipt -- never one
    # shared base id derived into two suffixed strings.
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
        owner_scope=arguments.get("owner_scope"),
        permissions=_permissions_from_grants(grants),
        receipt_operation_ids=effect_ids or None,
    )
    status_code, body = _tool_result_response(result)
    _refresh_project_memories_if_store_exists(ctx, project_id, root)
    return status_code, body


def _dispatch_scan_action(
    ctx: DashboardContext,
    project_id: str,
    operation: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
    *,
    operation_id: str = "",
    expected: dict[str, Any] | None = None,
    effect_ids: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    try:
        if operation == "provision_plan":
            return _dispatch_provision_plan(project_id, arguments)
        if operation == "provision_apply":
            return _dispatch_provision_apply(
                ctx, project_id, arguments, grants, operation_id
            )
        if operation == "scan_start":
            return _dispatch_scan_start(
                ctx,
                project_id,
                arguments,
                grants,
                operation_id=operation_id,
                expected=expected,
            )
        if operation == "scan_cancel":
            return _dispatch_scan_cancel(ctx, project_id, arguments, grants)
        if operation == "scan_resume":
            return _dispatch_scan_resume(
                ctx,
                project_id,
                arguments,
                grants,
                operation_id=operation_id,
                expected=expected,
            )
        if operation == "rescan":
            return _dispatch_rescan(
                ctx,
                project_id,
                arguments,
                grants,
                operation_id=operation_id,
                expected=expected,
            )
        if operation == "handoff_preview":
            return _dispatch_handoff_preview(project_id, arguments, grants)
        if operation == "handoff_send":
            return _dispatch_handoff_send(
                ctx, project_id, arguments, grants, operation_id
            )
        if operation == "handoff_status":
            return _dispatch_handoff_status(project_id, arguments, grants)
        if operation == "configure":
            return _dispatch_configure(ctx, project_id, arguments, grants)
        if operation == "memory_edit":
            return _dispatch_memory_edit(ctx, project_id, arguments, grants, effect_ids)
        if operation == "memory_archive":
            return _dispatch_memory_archive(
                ctx, project_id, arguments, grants, effect_ids
            )
        if operation == "memory_delete":
            return _dispatch_memory_delete(
                ctx, project_id, arguments, grants, effect_ids
            )
        if operation == "memory_promote":
            return _dispatch_memory_promote(
                ctx, project_id, arguments, grants, effect_ids
            )
        if operation == "memory_query":
            return _dispatch_memory_query(project_id, arguments, grants)
        if operation == "memory_expand":
            return _dispatch_memory_expand(project_id, arguments, grants)
        if operation == "memory_propose":
            return _dispatch_memory_propose(ctx, project_id, arguments, grants)
        if operation == "memory_maintain":
            return _dispatch_memory_maintain(ctx, project_id, arguments, grants)
        if operation == "data_export":
            return _dispatch_data_export(project_id, grants)
        if operation == "artifact_export":
            return _dispatch_artifact_export(project_id, arguments, grants)
    except ProjectError as exc:
        _raise_from_project_error(exc)
    except ScanConflictError as exc:
        raise _ActionDenied(409, "conflict", str(exc)) from exc
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


def _dispatch_artifact_export(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """P69-02.2n: export one artifact reference's full manifest entry (never
    raw finding evidence/tool stdout/memory content -- same redaction rule
    `expand_artifact_reference` already enforces)."""
    _require_grants(grants, "download", operation="artifact_export")
    artifact_ref = arguments.get("artifact_id")
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise _ActionDenied(
            400, "malformed_request", "artifact_export requires arguments.artifact_id"
        )
    result = expand_artifact_reference(project_id, artifact_ref)
    if not result.get("found"):
        raise _ActionDenied(404, "not_found", f"unknown artifact_id: {artifact_ref}")
    return 200, result


def _dispatch_configure(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """`rush_project configure`: a preview (`apply=False`, the default)
    requires no grant; an actual apply requires `cache_write` and
    `artifact_write`, mirroring `memory_edit`'s apply-gated pattern."""
    apply = bool(arguments.get("apply", False))
    if apply:
        _require_grants(grants, "cache_write", "artifact_write", operation="configure")
    root = Path(resolve_project(project_id)["root"])
    result = ProjectTool().run(
        root,
        action="configure",
        project_id=project_id,
        settings=arguments.get("settings"),
        expected_revision=arguments.get("expected_revision"),
        apply=apply,
        plan_id=arguments.get("plan_id"),
        permissions=_permissions_from_grants(grants),
        data_root=ctx.data_root,
    )
    return _tool_result_response(result)


def _dispatch_handoff_status(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`rush_scan_handoff.status`: a plain read, never re-authenticates and
    never requires a mutation grant."""
    handoff_id = arguments.get("handoff_id")
    if not isinstance(handoff_id, str) or not handoff_id:
        raise _ActionDenied(
            400, "malformed_request", "handoff_status requires arguments.handoff_id"
        )
    return 200, status_handoff(project_id, handoff_id)


def _dispatch_memory_query(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`memory_query`: dispatches ask/recall/list per `arguments.mode`
    (default 'list') through `MemoryTool`'s own `view=compact` request
    contract (Phase 63 defaults: 2048 tokens, 8192 bytes, cl100k_base,
    limit 8) -- `list` alone among the three needs no `query`. A plain read
    with lexical retrieval requires no grant; `retrieval=hybrid` requires a
    `network` grant."""
    mode = arguments.get("mode", "list")
    if mode not in ("ask", "recall", "list"):
        raise _ActionDenied(
            400, "malformed_request", "memory_query mode must be ask, recall, or list"
        )
    subject = arguments.get("subject")
    if not isinstance(subject, str) or subject not in _MEMORY_SUBJECTS:
        raise _ActionDenied(
            400, "malformed_request", "memory_query requires a valid subject"
        )
    query = arguments.get("query", "")
    if mode in ("ask", "recall") and not query:
        raise _ActionDenied(
            400,
            "malformed_request",
            f"memory_query mode={mode} requires arguments.query",
        )
    session_allowlist = arguments.get("session_allowlist")
    if not (
        isinstance(session_allowlist, list)
        and session_allowlist
        and all(isinstance(s, str) for s in session_allowlist)
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "memory_query requires a non-empty arguments.session_allowlist "
            "(fail-closed, no default cross-session access)",
        )
    retrieval = arguments.get("retrieval", "lexical")
    if retrieval == "hybrid":
        _require_grants(grants, "network", operation="memory_query")
    request: dict[str, Any] = {"view": "compact", "retrieval": retrieval}
    for key in ("limit", "max_tokens", "max_bytes", "encoding", "cursor"):
        if key in arguments:
            request[key] = arguments[key]
    root = Path(resolve_project(project_id)["root"])
    result = MemoryTool().run(
        root,
        operation=mode,
        subject=subject,
        query=query,
        session_allowlist=session_allowlist,
        request=request,
        permissions=_permissions_from_grants(grants),
    )
    return _tool_result_response(result)


def _dispatch_memory_expand(
    project_id: str, arguments: dict[str, Any], grants: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    """`memory_expand`: exact-byte expansion of one stored artifact
    version. A plain read -- never requires a mutation grant."""
    artifact_id = arguments.get("id")
    version = arguments.get("version")
    if (
        not isinstance(artifact_id, str)
        or not artifact_id
        or not isinstance(version, int)
        or isinstance(version, bool)
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "memory_expand requires arguments.id and arguments.version",
        )
    session_allowlist = arguments.get("session_allowlist")
    if not (
        isinstance(session_allowlist, list)
        and session_allowlist
        and all(isinstance(s, str) for s in session_allowlist)
    ):
        raise _ActionDenied(
            400,
            "malformed_request",
            "memory_expand requires a non-empty arguments.session_allowlist "
            "(fail-closed, no default cross-session access)",
        )
    request: dict[str, Any] = {"id": artifact_id, "version": version}
    for key in ("offset", "max_tokens", "max_bytes", "encoding"):
        if key in arguments:
            request[key] = arguments[key]
    root = Path(resolve_project(project_id)["root"])
    result = MemoryTool().run(
        root,
        operation="expand",
        request=request,
        session_allowlist=session_allowlist,
        permissions=_permissions_from_grants(grants),
    )
    return _tool_result_response(result)


def _refresh_project_memories(
    ctx: DashboardContext, project_id: str, root: Path
) -> None:
    """P69-02.2o: `memory_propose`/`memory_maintain`/a successful
    `handoff_send` all persist real memory content, so all three must
    republish the project's live memory data (never bare `bump_sequence()`,
    which drops the ordering/staleness check `refresh_memories()` exists
    for)."""
    memories, generation = TypedArtifactStore(root).snapshot_memories()
    ctx.projects.refresh_memories(project_id, memories, generation)


def _refresh_project_memories_if_store_exists(
    ctx: DashboardContext, project_id: str, root: Path
) -> None:
    """M07: shared post-commit refresh for edit/archive/delete/promote, which
    (unlike propose/maintain) have a genuine read-only preview mode and can
    fail before writing anything -- so this must never itself spring a
    `.rush/memory.db` into existence just to check for updates. Only calls
    the write-adjacent `TypedArtifactStore(root)` (and hence
    `_refresh_project_memories`) once a store already exists on disk;
    `refresh_memories()`'s own generation gate (state.py) still rejects a
    non-newer generation, so a preview or a zero-write failure against an
    *existing* store still publishes no fabricated sequence bump. A
    promotion that writes a candidate before its trust decision is later
    denied still refreshes, since the store now carries that real commit."""
    opened = TypedArtifactStore.open_readonly(root)
    if not opened.available or opened.connection is None:
        return
    opened.connection.close()
    _refresh_project_memories(ctx, project_id, root)


def _dispatch_memory_propose(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """`memory_propose` maps to `MemoryTool`'s `write` -- creates a
    candidate artifact only, never promotes it. Always requires
    `cache_write`, matching `memory_promote`'s always-write semantics."""
    _require_grants(grants, "cache_write", operation="memory_propose")
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
            "memory_propose requires a valid subject, content, and source",
        )
    source_kind = arguments.get("source_kind", "local_tool")
    if source_kind not in _MEMORY_SOURCE_KINDS:
        raise _ActionDenied(400, "malformed_request", "invalid source_kind")
    root = Path(resolve_project(project_id)["root"])
    result = MemoryTool().run(
        root,
        operation="write",
        subject=subject,
        content=content,
        source=source,
        symbol_ref=arguments.get("symbol_ref"),
        source_kind=source_kind,
        owner_scope=arguments.get("owner_scope"),
        permissions=_permissions_from_grants(grants),
    )
    status_code, body = _tool_result_response(result)
    if body.get("status") == "ok":
        _refresh_project_memories(ctx, project_id, root)
    return status_code, body


def _dispatch_memory_maintain(
    ctx: DashboardContext,
    project_id: str,
    arguments: dict[str, Any],
    grants: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """`memory_maintain` maps to `MemoryTool`'s `maintain` -- validates
    `task` against the shared `MaintenanceTask` enum, never an arbitrary
    string. Always requires `cache_write`.

    S04/T034 investigation: unlike edit/archive/delete/promote, this
    dispatcher does NOT need the identical reserved-effect-id fix.
    `MemoryTool.run`'s `maintain` operation (tools/memory.py) has no
    `receipt_operation_id` parameter on its dispatch-table lambda or on
    `_run_maintain` at all -- there is no write site here to thread the
    reserved `maintenance_run` id into. Adding one would mean editing
    tools/memory.py, outside this task's allowed_files."""
    _require_grants(grants, "cache_write", operation="memory_maintain")
    task = arguments.get("task")
    if task not in get_args(MaintenanceTask):
        raise _ActionDenied(
            400, "malformed_request", "memory_maintain requires a valid task"
        )
    batch_size = arguments.get("batch_size", 500)
    if not isinstance(batch_size, int) or isinstance(batch_size, bool):
        raise _ActionDenied(
            400, "malformed_request", "memory_maintain batch_size must be an integer"
        )
    root = Path(resolve_project(project_id)["root"])
    result = MemoryTool().run(
        root,
        operation="maintain",
        task=task,
        batch_size=batch_size,
        owner_scope=arguments.get("owner_scope"),
        permissions=_permissions_from_grants(grants),
    )
    status_code, body = _tool_result_response(result)
    if body.get("status") == "ok":
        _refresh_project_memories(ctx, project_id, root)
    return status_code, body


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


class _CursorError(Exception):
    """P69-03u: raised by a non-map section's revision-bound cursor decode.
    Carries the exact HTTP status/code `_handle_snapshot` sends -- 400 for a
    genuinely malformed cursor, 409 when it's well-formed but was issued
    against a different revision of that section's own backing store."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _encode_revision_cursor(offset: int, *, revision: str) -> str:
    """P69-03u: each non-map section's cursor is bound to an authoritative
    revision of its OWN backing store -- a real per-store counter where one
    exists (`TypedArtifactStore.current_generation()` for memory), or a
    content digest of the resolved manifest/item list taken fresh on every
    request otherwise (scans/artifacts) -- never a bare offset that silently
    resets to 0 when the underlying store has moved on."""
    raw = json.dumps(
        {"offset": offset, "revision": revision}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_revision_cursor(cursor: str | None, *, revision: str) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise _CursorError(400, "invalid_cursor", "malformed cursor") from exc
    if (
        not isinstance(payload, dict)
        or "offset" not in payload
        or "revision" not in payload
    ):
        raise _CursorError(400, "invalid_cursor", "malformed cursor")
    offset = payload["offset"]
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise _CursorError(400, "invalid_cursor", "malformed cursor")
    if payload["revision"] != revision:
        raise _CursorError(
            409,
            "cursor_rejected",
            "cursor was issued against a different snapshot revision of "
            "this section's backing store",
        )
    return offset


def _content_revision(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()[:16]


def _list_run_ids(root: Path) -> list[str]:
    runs_dir = root / ".rush" / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(p.name for p in runs_dir.iterdir() if p.is_dir())


def _latest_pending_attempt(root: Path) -> tuple[str, str] | None:
    """The latest run's latest attempt, when its terminal manifest has not
    yet recorded a publication outcome (`_record_manifest_publication`)."""
    manifests = [
        manifest
        for manifest in (
            load_run_manifest(root, run_id) for run_id in _list_run_ids(root)
        )
        if manifest is not None
    ]
    if not manifests:
        return None
    latest = max(manifests, key=lambda m: str(m.get("created_at") or ""))
    if latest.get("publication"):
        return None
    run_id, attempt_id = latest.get("run_id"), latest.get("attempt_id")
    if not run_id or not attempt_id:
        return None
    return str(run_id), str(attempt_id)


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


_MAX_ARTIFACT_PAGE_BYTES = 1024 * 1024


def _read_artifact_content_page(
    root: Path,
    entry: dict[str, Any],
    rel_path: str,
    *,
    offset: int,
    limit: int,
    project_id: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """M12: bounded byte-range content page for the artifact-download route
    (plan §3.6: artifact reads paginate at 1MiB/page), resolved only from
    this exact run/attempt's own captured immutable snapshot
    (`CandidateResult.artifact_snapshots`, `project_run.py`), never from the
    live/staged current-project tree. T28-E: a thin adapter over the shared
    `workflows/projects.py::read_project_artifact_page` (containment,
    identity and cursor validation live there, so CLI/TUI/web cannot
    diverge): it only finds this run/attempt/tool's recorded snapshot
    sha256 for `rel_path`, builds the reader's cursor, and maps
    `next_cursor` back to this route's `next_offset`. A manifest that
    predates snapshot capture (or a candidate that never captured this path)
    is reported as `immutable_content_unavailable`, never a live-file
    fallback. Raw bytes travel base64-encoded (`content_base64`)."""
    run_id = entry.get("run_id")
    attempt_id = entry.get("attempt_id")
    tool_id = entry.get("tool_id")
    manifest = (
        load_run_manifest(root, run_id, attempt_id=attempt_id)
        if run_id and attempt_id
        else None
    )
    snapshot = None
    if manifest is not None and tool_id is not None:
        for item in manifest.get("scheduled") or []:
            if item.get("candidate_id") == tool_id:
                snapshot = (item.get("artifact_snapshots") or {}).get(rel_path)
                break
    if manifest is None or not isinstance(snapshot, dict):
        return {
            "path": rel_path,
            "error": "immutable_content_unavailable",
            "content_base64": None,
        }
    # The reader re-resolves `root` and refuses a cursor naming any other
    # project, so an id taken from the route or the manifest is only a hint;
    # a CHECK_SUITE manifest records none and resolves through the registry.
    project_id = (
        project_id
        or manifest.get("project_id")
        or wp.resolve_project(root, data_root=data_root)["project_id"]
    )
    cursor = wp._b64url_encode(
        json.dumps(
            {
                "project_id": project_id,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "tool_id": tool_id,
                "path": rel_path,
                "sha256": snapshot.get("sha256"),
                "offset": 0,
            }
        ).encode("utf-8")
    )
    page = wp.read_project_artifact_page(
        root, cursor, data_root=data_root, offset=max(0, offset), limit=limit
    )
    if page.get("error"):
        return page
    next_cursor = page.get("next_cursor")
    return {
        "path": page.get("path"),
        "offset": page.get("offset"),
        "size": page.get("size"),
        "content_base64": page.get("content_base64"),
        "next_offset": (
            json.loads(wp._b64url_decode(next_cursor))["offset"]
            if next_cursor
            else None
        ),
        "sha256": page.get("sha256"),
        "media_type": page.get("media_type"),
    }


def _build_overview_section(project_id: str, record: ProjectRecord) -> dict[str, Any]:
    """`section=overview` (P69-02.2n, row 6): a curated summary -- identity
    and counts -- never the full snapshot's raw findings/agents/memories
    arrays."""
    snapshot = record.snapshot
    return {
        "project_id": project_id,
        "root": snapshot.get("root"),
        "source_identity": record.source_identity,
        "sequence": record.sequence,
        "finding_count": len(snapshot.get("findings") or []),
        "memory_count": len(snapshot.get("memories") or []),
        "agent_count": len(snapshot.get("agents") or []),
    }


def _build_setup_section(project_id: str) -> dict[str, Any]:
    """`section=setup` (P69-02.2n, row 6): the same provisioning readiness
    `provision_plan` already computes, never the full snapshot."""
    root = Path(resolve_project(project_id)["root"])
    readiness = run_setup_wizard(root, install=True, permissions=None)
    return {"project_id": project_id, "readiness": readiness}


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
    # T037: authoritative from the durable `scan_admission` row, not
    # `ScanRunTracker.active_run_id`'s `thread.is_alive()` -- the admission
    # row is released (see the `_body` closures above) no later than the
    # moment a terminal snapshot becomes visible, while the thread itself
    # stays alive a little longer, unwinding through `_run_supervised`.
    admission = ctx.mutations.admission_for_project(project_id)
    active_run_id = (admission or {}).get("run_id") or None

    result: dict[str, Any] = {
        "runs": runs_summary,
        "active_run_id": active_run_id,
        "candidates": [],
        "findings": {"items": [], "next_cursor": None, "total": 0, "groups": None},
        # P69-03v: no attempt matching the requested (run_id, attempt_id)
        # has reached `publish_scan_result` yet -- overwritten below once a
        # real manifest is resolved.
        "publication": "not_yet",
    }

    requested_run_id = query.get("run_id", [None])[0]
    requested_attempt_id = query.get("attempt_id", [None])[0]
    if requested_run_id:
        if requested_attempt_id:
            # P69-03r: a caller holding a specific historical attempt id is
            # pinned to that exact attempt, never whichever is currently
            # latest for this run_id.
            manifest = load_run_manifest(
                root, requested_run_id, attempt_id=requested_attempt_id
            )
        else:
            manifest = next(
                (m for m in manifests if m.get("run_id") == requested_run_id), None
            )
    else:
        manifest = manifests[-1] if manifests else None
    if manifest is None:
        return result
    # T037/T8.md §4: an attempt is presented as a finished `run` only once
    # its admission is released. `execute_scan` writes the terminal manifest
    # before the dashboard releases the admission, so without this a caller
    # could see the run while the project still reports it active (a follow-up
    # resume/rescan then conflicts). Released-but-unpublished candidate events
    # are covered by `/events`' pending-publication catch-up.
    if admission is not None and (
        admission.get("run_id"),
        admission.get("attempt_id"),
    ) == (manifest.get("run_id"), manifest.get("attempt_id")):
        return result

    run_id = manifest["run_id"]
    result["candidates"] = manifest.get("candidates", [])
    result["run"] = _run_summary(manifest)
    # P69-03v: the map/snapshot's own publication marker only ever exposes
    # "most recently published" -- this answers "has *this specific*
    # (run_id, attempt_id) ever been incorporated," independent of whether a
    # later, unrelated run is now the current snapshot.
    result["publication"] = manifest.get("publication") or "not_yet"
    if manifest.get("published_at"):
        result["published_at"] = manifest["published_at"]

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
    # P69-03u: Scans' cursor binds to the resolved manifest's own content --
    # an (attempt_id, manifest_digest) pair -- not a bare offset against
    # whatever `load_run_manifest()` currently resolves as latest. An
    # external resume landing between two page requests changes this
    # digest, so the second page is rejected rather than silently mixing
    # findings from two different attempts under one accepted cursor.
    revision = f"{run_id}:{_content_revision(manifest)}"
    offset = _decode_revision_cursor(cursor, revision=revision)
    page = findings[offset : offset + limit]
    next_cursor = (
        _encode_revision_cursor(offset + limit, revision=revision)
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


# P69-07 subsection g: `scope_artifacts()`'s own default `scan_limit` (512) once capped
# browse to whatever fit in one call; this batches past it, one `_MEMORY_BROWSE_BATCH`
# chunk at a time, until a batch comes back shorter than requested (exhausted) -- M14:
# no iteration-count ceiling, so a subject with more than 10,240 rows no longer gets
# silently truncated with a wrong `total`.
_MEMORY_BROWSE_BATCH = 512
# Perf: `_build_memory_section` is called once per page-request HTTP call, and the
# browse branch (empty query) below re-derives the full matching-row set from scratch
# every time -- O(N^2/P) row-fetches across a full N-row/P-page-size traversal (root
# cause of a real slow-test/full-suite-runtime bug, .scratch/dashboard-memory-pagination-perf/).
# Cache the raw (pre source_filter/freshness) browse item list per (root, subjects,
# trust filter, include_archived, known sources, store generation) -- a write bumps
# `current_generation()`, which is part of the key, so a stale cache entry is never
# served across a mutation; it just ages out of the bounded LRU unused. Query-mode
# (non-empty query text) is deliberately NEVER cached here -- its live per-row staleness
# re-check against the current codebase must run on every request, not just the first
# page of a traversal. This adds no new filter/SQL logic (correctness-neutral by
# construction), only reuses work across sequential browse-page requests against an
# unchanged store -- the common client pattern.
_MEMORY_BROWSE_CACHE: OrderedDict[tuple[Any, ...], list[dict[str, Any]]] = OrderedDict()
_MEMORY_BROWSE_CACHE_MAXSIZE = 32


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
    non-empty `query` searches via the same `TypedArtifactStore.recall()`
    path `MemoryTool`'s `list` and the CLI/MCP use (over a read-only view), including
    its dynamic per-row staleness re-check (a memory whose cited symbol
    changed since it was written surfaces `stale: true` here). An empty
    `query` browses via `TypedArtifactStore.scope_artifacts()` instead
    (`dynamic_freshness_checked: false` -- only the persisted `stale`
    column, no live re-check)."""
    root = Path(resolve_project(project_id)["root"])
    # R20.G8: a GET never creates or migrates memory.db. No DB = empty; an
    # unreadable one (old schema, corrupt, busy) is reported as `store_state`.
    store, store_state = TypedArtifactStore.open_readonly_view(root)
    all_sources = _all_known_sources(store) if store is not None else []
    browse_revision = str(store.current_generation() if store is not None else 0)

    requested_subjects = _split_csv(query.get("subject", []))
    subjects = [s for s in requested_subjects if s in _MEMORY_SUBJECTS] or list(
        _MEMORY_SUBJECTS
    )
    trust_filter = set(_split_csv(query.get("trust", [])))
    source_filter = set(_split_csv(query.get("source", [])))
    freshness = query.get("freshness", [None])[0]
    include_archived = query.get("include_archived", ["false"])[0] == "true"
    # T18 R18.2: bookkeeping sources are excluded from the default browse/query
    # allowlist and `known_sources`. `include_internal` restores exactly the
    # pre-T18 set. Expand/related-by-ID (below) keep the unfiltered `all_sources`.
    include_internal = query.get("include_internal", ["false"])[0] == "true"
    browse_sources = (
        all_sources
        if include_internal
        else [s for s in all_sources if not is_internal_memory_source(s)]
    )
    query_text = query.get("query", [""])[0]

    # Only the browse (empty-query) path is cache-eligible: its own docstring
    # documents it as static (`dynamic_freshness_checked: false`, persisted
    # `stale` column only). Query-mode's `list` dispatch does a genuinely live
    # per-row staleness re-check against the current codebase on every call --
    # caching it would silently skip that re-check for a file that changes
    # mid-traversal, which a subsequent page's request would otherwise catch.
    browse_cache_key = (
        str(root),
        tuple(subjects),
        frozenset(trust_filter),
        include_archived,
        tuple(sorted(browse_sources)),
        browse_revision,
    )
    cached_items = None if query_text else _MEMORY_BROWSE_CACHE.get(browse_cache_key)
    if cached_items is not None:
        _MEMORY_BROWSE_CACHE.move_to_end(browse_cache_key)
        items = list(cached_items)
    elif store is None:
        items = []
    else:
        items = _fetch_memory_browse_items(
            store,
            root=root,
            all_sources=browse_sources,
            subjects=subjects,
            trust_filter=trust_filter,
            include_archived=include_archived,
            query_text=query_text,
        )
        if not query_text:
            _MEMORY_BROWSE_CACHE[browse_cache_key] = list(items)
            _MEMORY_BROWSE_CACHE.move_to_end(browse_cache_key)
            while len(_MEMORY_BROWSE_CACHE) > _MEMORY_BROWSE_CACHE_MAXSIZE:
                _MEMORY_BROWSE_CACHE.popitem(last=False)

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
    # P69-03u: memory's cursor binds to the store's own real commit order
    # (`TypedArtifactStore.current_generation()`) -- a write between two
    # page requests advances it, rejecting the second page rather than
    # silently splicing pre- and post-mutation results into one response.
    revision = browse_revision
    offset = _decode_revision_cursor(cursor, revision=revision)
    page = items[offset : offset + limit]
    next_cursor = (
        _encode_revision_cursor(offset + limit, revision=revision)
        if offset + limit < len(items)
        else None
    )

    section_data: dict[str, Any] = {
        "items": page,
        "next_cursor": next_cursor,
        "total": len(items),
        "subjects": list(_MEMORY_SUBJECTS),
        "known_sources": browse_sources,
    }
    if store_state is not None:
        section_data["store_state"] = store_state
        section_data["store_reason"] = readonly_view_reason(store_state)

    # R20.G8: expand/related read through the same read-only view (never a
    # writable store); R18.2: both keep the UNFILTERED `all_sources` allowlist.
    for operation, id_key, version_key in (
        ("expand", "expand_id", "expand_version"),
        ("related", "related_id", "related_version"),
    ):
        target_id = query.get(id_key, [None])[0]
        if not target_id:
            continue
        try:
            target_version = int(query.get(version_key, ["0"])[0])
        except ValueError:
            target_version = 0
        if store is None:
            section_data[operation] = dict(
                _unreadable_memory_envelope(operation, store_state)
            )
            continue
        section_data[operation] = dict(
            MemoryTool(readonly_store=store).run(
                root,
                operation=cast(MemoryOperation, operation),
                request={"id": target_id, "version": target_version},
                session_allowlist=all_sources,
            )
        )

    # ponytail: an exception above leaves the view to GC; it is read-only (no
    # sidecars, no locks held past the statement), so that only delays the close.
    if store is not None:
        store.close()
    return section_data


_UNREADABLE_STORE_CODES = {
    "migration_required": "E_MIGRATION",
    "corrupt": "E_STORE_CORRUPT",
    "busy": "E_STORE_BUSY",
}


def _unreadable_memory_envelope(operation: str, store_state: str | None) -> ToolResult:
    """expand/related when no readable store exists: no DB at all is `E_NOT_VISIBLE`
    (nothing to see, same code a missing id returns), an unreadable one carries its
    state's code and reason. Never constructs a store."""
    if store_state is None:
        return MemoryTool()._envelope_result(
            time.monotonic(),
            operation,
            "E_NOT_VISIBLE",
            {"message": "no memory store exists for this project"},
        )
    return MemoryTool()._envelope_result(
        time.monotonic(),
        operation,
        _UNREADABLE_STORE_CODES[store_state],
        {"message": readonly_view_reason(store_state), "state": store_state},
    )


def _fetch_memory_browse_items(
    store: TypedArtifactStore,
    *,
    root: Path,
    all_sources: list[str],
    subjects: list[MemorySubject],
    trust_filter: set[str],
    include_archived: bool,
    query_text: str,
) -> list[dict[str, Any]]:
    """The actual (uncached) row-fetch this section's browse/query branches
    used to run on every single page request -- factored out so
    `_build_memory_section`'s per-generation cache can skip it entirely on a
    cache hit. Behavior is unchanged from before the cache was added."""
    items: list[dict[str, Any]] = []
    if query_text and all_sources:
        for subject in subjects:
            # R20.G8: the same `recall()` (signature, Trojan-source and live
            # staleness checks) `MemoryTool`'s `list` runs, but over this
            # read-only view -- a GET never constructs a writable store. A
            # rejected subject yields no rows, exactly as `list`'s error did.
            try:
                artifacts = store.recall(
                    subject,
                    query_text,
                    all_sources,
                    include_archived=include_archived,
                )
            except (SignatureMismatchError, TrojanSourceFoundError):
                continue
            for artifact in artifacts:
                item = dataclasses.asdict(artifact)
                item["dynamic_freshness_checked"] = True
                items.append(item)
        if trust_filter:
            items = [i for i in items if i.get("trust_tier") in trust_filter]
    elif all_sources:
        for subject in subjects:
            # P69-07 subsection g: batch past scope_artifacts()'s own scan_limit default
            # instead of one capped call, and exclude archived rows by default (matching
            # search()'s existing include_archived precedent) -- both real leaks in the
            # pre-P69-07 browse path.
            subject_offset = 0
            while True:
                batch = store.scope_artifacts(
                    subject,
                    source_allowlist=all_sources,
                    trust_tiers=trust_filter or None,
                    include_expired=include_archived,
                    include_archived=include_archived,
                    scan_offset=subject_offset,
                    scan_limit=_MEMORY_BROWSE_BATCH,
                )
                items.extend(_scope_artifact_row(row) for row in batch)
                if len(batch) < _MEMORY_BROWSE_BATCH:
                    break
                subject_offset += len(batch)

    return items


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
    # M10: one selection, parsed once, applied identically to token totals,
    # memory-event-by-kind totals, and handoff rows -- never filtering only
    # the handoff rows while leaving the displayed totals project-wide.
    run_filter = query.get("run_id", [None])[0]
    agent_filter = query.get("agent_id", [None])[0]
    session_filter = query.get("session_id", [None])[0]
    # R20.G8: a GET never springs `.rush/telemetry/tokens.db` into existence;
    # a project with no ledger yet reports the ledger's own all-zero totals.
    if (root / ".rush" / "telemetry" / "tokens.db").exists():
        telemetry = TelemetryStore(root)
        summary = telemetry.get_summary(
            run_id=run_filter, agent_id=agent_filter, session_id=session_filter
        )
        by_kind = {
            kind: telemetry.get_memory_event_total(
                kind,
                run_id=run_filter,
                agent_id=agent_filter,
                session_id=session_filter,
            )
            for kind in _MEMORY_EVENT_KINDS
        }
    else:
        summary = {
            "events_count": 0,
            "total_raw_tokens": 0,
            "total_compressed_tokens": 0,
            "net_tokens_saved": 0,
            "compression_ratio": 0.0,
            "dollar_savings_est": 0.0,
        }
        by_kind = dict.fromkeys(_MEMORY_EVENT_KINDS, 0)
    # R20.G8: read-only view; never creates or migrates memory.db.
    store, _store_state = TypedArtifactStore.open_readonly_view(root)
    cache_fill_count = 0
    if store is not None:
        try:
            cache_fill_count = sum(
                1
                for row in store.list_artifact_refs()
                if row["source"] == "context_pack"
            )
        finally:
            store.close()

    handoffs = _list_project_handoffs(root)
    if run_filter:
        handoffs = [h for h in handoffs if h.get("run_id") == run_filter]
    if agent_filter:
        handoffs = [h for h in handoffs if h.get("agent_id") == agent_filter]
    if session_filter:
        handoffs = [h for h in handoffs if h.get("memory_session_id") == session_filter]

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
    working-tree/index status, and an optional single-commit diff. History
    pages by an opaque, revision-bound cursor (P69-03u's non-map-section
    cursor contract, reused verbatim) with a 50-commit default page size --
    never the old default offset (`skip`) pagination. Linking a commit to
    scan-output evidence requires an exact source-revision match (P69-03.2's
    Git-link predicate) -- never a merely intersecting file path (plan:
    "Link commits/source revisions to scans... only where actual identity
    matches")."""
    status = project_snapshot(project_id)["git"]
    revision = str(status["head"])

    try:
        limit = int(query.get("limit", ["50"])[0])
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 50))
    cursor = query.get("cursor", [None])[0]
    offset = _decode_revision_cursor(cursor, revision=revision)
    history_page = project_git_history(project_id, limit=limit, skip=offset)
    next_skip = history_page["next_skip"]
    next_cursor = (
        _encode_revision_cursor(next_skip, revision=revision)
        if next_skip is not None
        else None
    )

    result: dict[str, Any] = {
        "has_git": status["has_git"],
        "head": status["head"],
        "dirty": status["dirty"],
        "dirty_files": status["dirty_files"],
        "history": history_page["commits"],
        "next_cursor": next_cursor,
    }

    commit = query.get("commit", [None])[0]
    if commit:
        diff = project_git_commit_diff(project_id, commit)
        artifacts = list_project_artifacts(project_id)
        root = Path(resolve_project(project_id)["root"])
        linked = [
            a["artifact_ref"]
            for a in artifacts.get("scan_outputs") or []
            if git_link_matches_commit(root, a.get("git_link"), commit)
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
    # P69-03u: no real per-store counter exists for artifacts today -- bind
    # to a content digest of the resolved (filtered) item list instead, the
    # plan's documented fallback ("an immutable paginated result snapshot
    # taken at first-page request"). Recomputed fresh from live storage on
    # every request, so an unchanged store still yields a matching digest
    # across pages, while any real mutation rejects the next page.
    revision = _content_revision(items)
    offset = _decode_revision_cursor(cursor, revision=revision)
    page = items[offset : offset + limit]
    next_cursor = (
        _encode_revision_cursor(offset + limit, revision=revision)
        if offset + limit < len(items)
        else None
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
            for key, value in SECURITY_RESPONSE_HEADERS:
                self.send_header(key, value)
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in SECURITY_RESPONSE_HEADERS:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_js(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in SECURITY_RESPONSE_HEADERS:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_css(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in SECURITY_RESPONSE_HEADERS:
                self.send_header(key, value)
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
            extra_headers: dict[str, str] | None = None,
            details: dict[str, Any] | None = None,
        ) -> None:
            self._send_json(
                status,
                _error_body(
                    request_id,
                    project_id,
                    code,
                    message,
                    retryable=retryable,
                    redact=self._redact_secrets(),
                    details=details,
                ),
                extra_headers=extra_headers,
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

        def _redact_secrets(self) -> tuple[str, ...]:
            """S12 point 2/3: every secret this response's body may redact --
            the server's always-live plaintext secrets (control capability,
            active CSRF tokens) plus this request's own presented bootstrap
            token and/or session cookie, included only if each hash-matches
            a currently-live secret via `DashboardAuth.match_presented_secret`.
            A presented value that fails that match is never added -- this
            never blanket-replaces an arbitrary caller-supplied substring."""
            secrets_to_redact = list(ctx.live_secrets())
            bearer = self._bearer()
            if bearer and ctx.auth.match_presented_secret(bearer):
                secrets_to_redact.append(bearer)
            cookie = self._cookie()
            if cookie and ctx.auth.match_presented_secret(cookie):
                secrets_to_redact.append(cookie)
            return tuple(secrets_to_redact)

        def _linger_discard(self) -> None:
            """Lingering close after a rejection that leaves the request body
            unread. Closing a socket with unread input makes the kernel send
            RST, which can destroy the error response before the client reads
            it -- a client still sending an oversized body typically sees
            ECONNRESET/EPIPE instead of the 413. Half-close, then discard at
            most `_LINGER_MAX_BYTES` for at most `_LINGER_SECONDS` in total:
            the deadline bounds the whole drain, not each read, so a client
            trickling its body cannot hold the handler thread open."""
            self.close_connection = True
            try:
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_WR)
                deadline = time.monotonic() + _LINGER_SECONDS
                read = getattr(self.rfile, "read1", self.rfile.read)
                remaining = _LINGER_MAX_BYTES
                while remaining > 0:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        break
                    self.connection.settimeout(left)
                    chunk = read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass

        def _check_request_limits(
            self, *, require_content_length: bool = False
        ) -> int | None:
            """Validate header/body-size limits; return declared body length
            (0 if none) or None after already sending an error response."""
            request_id = self._request_id()
            if len(self.headers) > MAX_HEADER_FIELDS:
                self._send_error(
                    400, "malformed_request", "too many header fields", request_id
                )
                self._linger_discard()
                return None
            # Count request-line bytes and header framing (": " + CRLF per
            # header, plus the terminating CRLF) alongside names/values --
            # names-plus-values alone undercounts the real bytes-on-the-wire.
            request_line_bytes = len(self.requestline.encode("utf-8", "replace")) + 2
            framing_bytes = len(self.headers.items()) * 4 + 2
            headers_size = (
                request_line_bytes
                + framing_bytes
                + sum(len(k) + len(v) for k, v in self.headers.items())
            )
            if headers_size > MAX_HEADERS_BYTES:
                self._send_error(
                    400, "malformed_request", "headers too large", request_id
                )
                self._linger_discard()
                return None
            if self.headers.get("Transfer-Encoding"):
                self._send_error(
                    400, "malformed_request", "chunked transfer rejected", request_id
                )
                self._linger_discard()
                return None
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                if require_content_length:
                    self._send_error(
                        400, "malformed_request", "Content-Length required", request_id
                    )
                    self._linger_discard()
                    return None
                return 0
            try:
                length = int(length_header)
            except ValueError:
                self._send_error(
                    400, "malformed_request", "invalid Content-Length", request_id
                )
                self._linger_discard()
                return None
            if length < 0:
                self._send_error(
                    400, "malformed_request", "invalid Content-Length", request_id
                )
                self._linger_discard()
                return None
            if length > MAX_BODY_BYTES:
                self._send_error(
                    413, "body_too_large", "request body exceeds limit", request_id
                )
                self._linger_discard()
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
                self._linger_discard()
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
            if self._check_request_limits() is None:
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
            if path == "/api/agents":
                self._handle_agents_list(request_id)
                return
            if path.startswith("/api/projects/") and path.endswith("/snapshot"):
                project_id = path[len("/api/projects/") : -len("/snapshot")]
                self._handle_snapshot(project_id, request_id)
                return
            if path.startswith("/api/projects/") and path.endswith("/events"):
                project_id = path[len("/api/projects/") : -len("/events")]
                self._handle_events(project_id, request_id)
                return
            if path.startswith("/api/projects/") and "/operations/" in path:
                remainder = path[len("/api/projects/") :]
                project_id, _sep, operation_id = remainder.partition("/operations/")
                if project_id and operation_id:
                    self._handle_operation_status(project_id, operation_id, request_id)
                    return
            if path.startswith("/api/projects/") and "/artifacts/" in path:
                remainder = path[len("/api/projects/") :]
                project_id, _sep, artifact_id = remainder.partition("/artifacts/")
                if project_id and artifact_id:
                    self._handle_artifact(project_id, artifact_id, request_id)
                    return

            self._send_error(404, "not_found", "unknown route", request_id)

        def do_POST(self) -> None:
            request_id = self._request_id()
            if not self._valid_host():
                self._send_error(
                    403, "invalid_host", "Host header rejected", request_id
                )
                return
            declared_length = self._check_request_limits(require_content_length=True)
            if declared_length is None:
                return
            path = urlparse(self.path).path

            if path == "/api/session/bootstrap":
                self._handle_reconnect_bootstrap(request_id)
                return

            # P69-06e: control-channel CHECK_SUITE dispatch -- authenticated
            # by the same private `X-Rush-Control` capability as the other
            # control endpoints above, never the browser session/CSRF pair,
            # so it is routed before the browser-facing origin check below.
            if path == "/api/control/check-suite":
                self._handle_control_check_suite(request_id, declared_length)
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
            if path == "/api/agents/actions":
                self._handle_agents_action(request_id, declared_length)
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

        def _handle_control_check_suite(
            self, request_id: str, declared_length: int
        ) -> None:
            """P69-06e: dispatch `CHECK_SUITE` inside this server process for
            a control-channel caller (the TUI/CLI at startup).

            Same credential boundary as `_handle_reconnect_bootstrap`: a
            browser cookie or an `Origin` header is rejected outright rather
            than accepted alongside the control capability. Idempotency,
            operation-id minting, and status transitions go through the exact
            `ctx.mutations.commit()` path the browser action route uses, so
            the returned operation id is pollable and cancellable through the
            same `/api/projects/{id}/operations/{op}` surface as any other
            async operation.
            """
            if self.headers.get("Origin") is not None or self._cookie() is not None:
                self._send_error(
                    401,
                    "unauthorized",
                    "control endpoint rejects browser credentials",
                    request_id,
                )
                return
            if not ctx.auth.verify_control(self.headers.get("X-Rush-Control")):
                self._send_error(
                    401, "unauthorized", "control capability required", request_id
                )
                return
            payload = self._read_json_body(declared_length, request_id)
            if payload is None:
                return
            schema_error = _schema_version_error(payload)
            if schema_error is not None:
                code, message = schema_error
                self._send_error(400, code, message, request_id)
                return
            project_id = payload.get("project_id")
            mutation_id = payload.get("request_id")
            if not isinstance(project_id, str) or not project_id:
                self._send_error(
                    400, "malformed_request", "project_id required", request_id
                )
                return
            if not isinstance(mutation_id, str) or not mutation_id:
                self._send_error(
                    400, "malformed_request", "request_id required", request_id
                )
                return
            record = ctx.projects.get(project_id)
            if record is None:
                self._send_error(
                    404, "not_found", "unknown project", request_id, project_id
                )
                return

            body_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()

            def _build(operation_id: str) -> tuple[int, bytes]:
                try:
                    status_code, data = _dispatch_check_suite(
                        ctx, project_id, operation_id=operation_id
                    )
                except ScanConflictError as exc:
                    return 409, _error_body(
                        request_id,
                        project_id,
                        "conflict",
                        str(exc),
                        retryable=True,
                        redact=self._redact_secrets(),
                    )
                except _ActionDenied as exc:
                    return exc.status, _error_body(
                        request_id,
                        project_id,
                        exc.code,
                        str(exc),
                        retryable=exc.retryable,
                        redact=self._redact_secrets(),
                    )
                except ProjectError as exc:
                    return 404, _error_body(
                        request_id,
                        project_id,
                        "not_found",
                        str(exc),
                        redact=self._redact_secrets(),
                    )
                return status_code, _success_body(
                    request_id,
                    project_id,
                    record.sequence,
                    data,
                    redact=self._redact_secrets(),
                )

            try:
                (status_code, body), conflict = ctx.mutations.commit(
                    project_id,
                    mutation_id,
                    body_hash,
                    _build,
                    operation_type="check_suite",
                    mutating=True,
                    validated_arguments=payload,
                    effect_ids=_s04_effect_ids("check_suite", payload),
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

        def _handle_session_exchange(self, request_id: str) -> None:
            client_key = self.client_address[0]
            if ctx.bootstrap_failure_limiter.peek_blocked(client_key):
                self._send_error(
                    429,
                    "rate_limited",
                    "too many bootstrap failures",
                    request_id,
                    retryable=True,
                    extra_headers={"Retry-After": "1"},
                )
                return
            bearer = self._bearer()
            # S11: DashboardAuth.exchange_bootstrap holds its own owning
            # lock across verify-then-consume-then-mint, so two concurrent
            # requests presenting the same bootstrap token can never both
            # mint a session from it -- no route-level lock needed here.
            exchanged = ctx.auth.exchange_bootstrap(bearer)
            if exchanged is None:
                ctx.bootstrap_failure_limiter.try_consume(client_key)
                self._send_error(
                    401,
                    "unauthorized",
                    "invalid or expired bootstrap token",
                    request_id,
                )
                return
            session, cookie_value = exchanged
            body = json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "csrf_token": session.csrf_token,
                    "owner_scope_id": session.owner_scope_id,
                }
            ).encode("utf-8")
            cookie_header = f"{ctx.auth.cookie_name}={cookie_value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"
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
                    "owner_scope_id": session.owner_scope_id,
                }
            ).encode("utf-8")
            self._send_json(200, body)

        def _handle_operation_status(
            self, project_id: str, operation_id: str, request_id: str
        ) -> None:
            """P69-02.2e: `GET /api/projects/{project_id}/operations/
            {operation_id}`. An attached operation_id follows to its real
            executing operation's status. An unregistered project_id, an
            unknown operation_id, and a real operation_id belonging to a
            different project all 404 identically -- this route never
            reveals which of the three actually happened."""
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
            if _operation_project_id(ctx, operation_id) != project_id:
                self._send_error(
                    404, "not_found", "unknown operation_id", request_id, project_id
                )
                return
            status = ctx.mutations.get_operation_status(
                _resolved_operation_id(ctx, operation_id)
            )
            if status is None:
                self._send_error(
                    404, "not_found", "unknown operation_id", request_id, project_id
                )
                return
            self._send_json(
                200,
                _success_body(
                    request_id,
                    project_id,
                    record.sequence,
                    status,
                    redact=self._redact_secrets(),
                ),
            )

        def _handle_events(self, project_id: str, request_id: str) -> None:
            """P69-03p: `GET /api/projects/{project_id}/events?after=<sequence>`
            -- durable read path over `MutationLedger`'s per-project event
            log (written by `record_status_transition` on every 202-returning
            dispatch's transitions), not a volatile in-memory ring buffer.
            Capped at 100 events/response; a cursor outside this project's
            2,000-retained window is rejected with `409
            event_cursor_expired` and a snapshot-reload instruction, never
            silently reset to whatever's oldest."""
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
            # M04 bullets 1-2: while a scan is actively admitted, catch up
            # this project's durable `/events` stream with whatever real
            # candidate progress its attempt has already written to its own
            # `events.json` -- otherwise a caller polling this route mid-scan
            # only ever sees status transitions until the run's own
            # completion flush (`_publish_scan_snapshot`) ingests the rest.
            # T8.md §4: the same catch-up also covers the latest attempt whose
            # publication is still pending. The admission is released
            # (T037) before `_publish_scan_snapshot` ingests, so between the
            # two a caller can already see the run on disk with neither path
            # having ingested its events; this closes that window without
            # reordering release and publish.
            admission = ctx.mutations.admission_for_project(project_id)
            admitted_run_id = admission.get("run_id") if admission else None
            admitted_attempt_id = admission.get("attempt_id") if admission else None
            try:
                project_root: Path | None = Path(resolve_project(project_id)["root"])
            except ProjectError:
                project_root = None
            if project_root is not None:
                catch_up: list[tuple[str, str]] = []
                if admitted_run_id and admitted_attempt_id:
                    catch_up.append((admitted_run_id, admitted_attempt_id))
                pending = _latest_pending_attempt(project_root)
                if pending is not None and pending not in catch_up:
                    catch_up.append(pending)
                for catch_run_id, catch_attempt_id in catch_up:
                    ctx.mutations.ingest_attempt_events(
                        project_id,
                        catch_run_id,
                        catch_attempt_id,
                        load_scan_events(
                            project_root, catch_run_id, catch_attempt_id
                        ).get("events")
                        or [],
                    )
            query = parse_qs(urlparse(self.path).query)
            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError:
                after = 0
            after = max(after, 0)
            result = ctx.mutations.list_events(project_id, after=after)
            if result is None:
                self._send_error(
                    409,
                    "event_cursor_expired",
                    "events cursor is outside this project's retained history; "
                    "reload the snapshot and resume polling from its sequence",
                    request_id,
                    project_id,
                    details={"recovery": "reload_snapshot"},
                )
                return
            events, next_after, has_more = result
            self._send_json(
                200,
                _success_body(
                    request_id,
                    project_id,
                    record.sequence,
                    {"events": events, "after": next_after, "has_more": has_more},
                    redact=self._redact_secrets(),
                ),
            )

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
                # P69-03o: the current map is served against live state, so
                # drift this registry never saw (another server's published
                # scan, an external memory mutation, this server's own
                # restart) is reconciled before the response is built, not
                # left showing stale data until this dashboard happens to run
                # its own scan.
                _sync_current_map(ctx, project_id)
                # Read-only from here on: the map is built from the stored
                # record itself, never a per-request deep copy of it.
                record = ctx.projects.get_published(project_id) or record
                requested_run_id = query.get("run_id", [None])[0]
                requested_attempt_id = query.get("attempt_id", [None])[0]
                map_snapshot = record.snapshot
                # M06 bullet 1: a historical view requires both `run_id` and
                # `attempt_id` supplied together -- `run_id` alone let
                # `_historical_map_snapshot` (and `load_run_manifest`'s own
                # latest-attempt fallback) silently resolve whichever attempt
                # happens to be latest, changing what a caller-selected
                # historical URL shows out from under it.
                if requested_run_id and not requested_attempt_id:
                    self._send_error(
                        400,
                        "invalid_request",
                        "a historical map request requires both run_id and attempt_id",
                        request_id,
                        project_id,
                    )
                    return
                view_id: tuple[Any, ...] = (
                    ("current",)
                    if not requested_run_id
                    else ("run", requested_run_id, requested_attempt_id)
                )
                if requested_run_id:
                    # P69-03r/s: a caller-selected historical run, pinned to
                    # its exact attempt with frozen memory/agent data --
                    # never the live current snapshot.
                    historical = _historical_map_snapshot_reused(
                        ctx,
                        Path(resolve_project(project_id)["root"]),
                        project_id,
                        record,
                        requested_run_id,
                        requested_attempt_id,
                    )
                    if historical is None:
                        self._send_error(
                            404,
                            "not_found",
                            "unknown run_id/attempt_id for this project",
                            request_id,
                            project_id,
                        )
                        return
                    map_snapshot = historical
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
                edge_id = query.get("edge", [None])[0]
                try:
                    if edge_id:
                        if not cursor:
                            self._send_error(
                                400,
                                "invalid_cursor",
                                "expanding a group-edge requires its own cursor",
                                request_id,
                                project_id,
                            )
                            return
                        data = expand_group_edge(
                            map_snapshot,
                            edge_id,
                            node_types=node_types,
                            severity=severity,
                            status=status,
                            query=query_text,
                            cursor=cursor,
                            view_id=view_id,
                        )
                    elif group_id:
                        data = expand_group(
                            map_snapshot,
                            group_id,
                            node_types=node_types,
                            severity=severity,
                            status=status,
                            query=query_text,
                            cursor=cursor,
                            view_id=view_id,
                        )
                    else:
                        data = build_project_map(
                            map_snapshot,
                            run_id=requested_run_id,
                            attempt_id=requested_attempt_id,
                            node_types=node_types,
                            severity=severity,
                            status=status,
                            query=query_text,
                            center_id=query.get("center_id", [None])[0],
                            cursor=cursor,
                        )
                except CursorRejected as exc:
                    self._send_error(
                        409, "cursor_rejected", str(exc), request_id, project_id
                    )
                    return
            elif section == "overview":
                data = _build_overview_section(project_id, record)
            elif section == "setup":
                try:
                    data = _build_setup_section(project_id)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except Exception as exc:  # noqa: BLE001 -- see section == "memory"
                    self._send_error(
                        500,
                        "section_error",
                        f"failed to build setup section: {exc}",
                        request_id,
                        project_id,
                        retryable=True,
                    )
                    return
            elif section == "scans":
                try:
                    data = _build_scans_section(ctx, project_id, query)
                except _CursorError as exc:
                    self._send_error(
                        exc.status, exc.code, str(exc), request_id, project_id
                    )
                    return
            elif section == "memory":
                try:
                    data = _build_memory_section(project_id, query)
                except ProjectError as exc:
                    _send_project_error(self, exc, request_id, project_id)
                    return
                except _CursorError as exc:
                    self._send_error(
                        exc.status, exc.code, str(exc), request_id, project_id
                    )
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
                except _CursorError as exc:
                    self._send_error(
                        exc.status, exc.code, str(exc), request_id, project_id
                    )
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
                except _CursorError as exc:
                    self._send_error(
                        exc.status, exc.code, str(exc), request_id, project_id
                    )
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
            elif section is None:
                data = record.snapshot
            else:
                # P69-03.3 CONNECT: an unrecognized `section` value is
                # rejected outright, never silently served the full
                # snapshot -- distinct from, and not a substitute for, a
                # dedicated section builder for a real name.
                self._send_error(
                    400,
                    "invalid_section",
                    f"unrecognized section: {section}",
                    request_id,
                    project_id,
                )
                return

            try:
                body = _success_body(
                    request_id,
                    project_id,
                    record.sequence,
                    data,
                    redact=self._redact_secrets(),
                )
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
                request_id,
                None,
                1,
                {"theme": THEME, "motion": MOTION},
                redact=self._redact_secrets(),
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
                request_id,
                None,
                1,
                {"items": items, "next_cursor": next_cursor},
                redact=self._redact_secrets(),
            )
            self._send_json(200, body)

        def _handle_agents_list(self, request_id: str) -> None:
            if self._authenticate_session(request_id, None, require_csrf=False) is None:
                return
            result = AgentConnectionTool().run(None, action="list")
            body = _success_body(
                request_id, None, 1, dict(result), redact=self._redact_secrets()
            )
            self._send_json(200, body)

        def _handle_agents_action(self, request_id: str, declared_length: int) -> None:
            if self._authenticate_session(request_id, None, require_csrf=True) is None:
                return
            payload = self._read_json_body(declared_length, request_id)
            if payload is None:
                return
            action = payload.get("action")
            if action not in ("list", "connect", "doctor"):
                self._send_error(
                    400,
                    "unknown_operation",
                    "action must be list, connect, or doctor",
                    request_id,
                )
                return
            grants = payload.get("grants")
            if not isinstance(grants, dict):
                grants = {}
            if action == "connect" and not (
                grants.get("cache_write") is True
                and grants.get("artifact_write") is True
            ):
                self._send_error(
                    403,
                    "grant_denied",
                    "agent connect requires explicit cache_write and artifact_write grants",
                    request_id,
                )
                return
            result = AgentConnectionTool().run(
                payload.get("agent_id"),
                action=action,
                session_id=payload.get("session_id"),
                consent=bool(payload.get("consent", False)),
                acknowledge=bool(payload.get("acknowledge", False)),
                permissions=_permissions_from_grants(grants),
            )
            body = _success_body(
                request_id, None, 1, dict(result), redact=self._redact_secrets()
            )
            self._send_json(200, body)

        def _handle_artifact(
            self, project_id: str, artifact_id: str, request_id: str
        ) -> None:
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
            result = expand_artifact_reference(project_id, artifact_id)
            if not result.get("found"):
                self._send_error(
                    404, "not_found", "unknown artifact_id", request_id, project_id
                )
                return
            entry = result.get("entry") or {}
            paths = entry.get("paths") or []
            if paths:
                query = parse_qs(urlparse(self.path).query)
                rel_path = query.get("path", [None])[0] or paths[0]
                if rel_path in paths:
                    try:
                        offset = int(query.get("offset", ["0"])[0])
                    except ValueError:
                        offset = 0
                    try:
                        limit = int(
                            query.get("limit", [str(_MAX_ARTIFACT_PAGE_BYTES)])[0]
                        )
                    except ValueError:
                        limit = _MAX_ARTIFACT_PAGE_BYTES
                    root = Path(resolve_project(project_id)["root"])
                    result["content"] = _read_artifact_content_page(
                        root,
                        entry,
                        rel_path,
                        offset=offset,
                        limit=limit,
                        project_id=project_id,
                    )
            body = _success_body(
                request_id,
                project_id,
                record.sequence,
                result,
                redact=self._redact_secrets(),
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
            grants = payload.get("grants")
            if not isinstance(grants, dict):
                grants = {}
            # P69-02.2n: require actual JSON booleans for `grants`/`git_init`
            # -- reject a present-but-non-bool value (`bool("false")` is
            # `True` in Python) instead of silently coercing it.
            bad_bools = [
                name
                for name in ("cache_write", "artifact_write")
                if name in grants and not isinstance(grants[name], bool)
            ]
            git_init_value = payload.get("git_init", False)
            if not isinstance(git_init_value, bool):
                bad_bools.append("git_init")
            if bad_bools:
                self._send_error(
                    400,
                    "malformed_request",
                    f"must be a boolean, not a string/other type: "
                    f"{', '.join(bad_bools)}",
                    request_id,
                )
                return
            if not (
                grants.get("cache_write") is True
                and grants.get("artifact_write") is True
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
                        init_git=git_init_value,
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

            # P69-02.2n: `register_project`/`create_project` are themselves
            # idempotent by canonical root (same identity in twice returns the
            # same project_id) and `ProjectRegistry.register` below is
            # idempotent too -- an "add" whose identity was already present in
            # *this* server's registry reports 200 (nothing new happened),
            # never 201.
            already_registered = ctx.projects.get(record.project_id) is not None
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
            self._send_json(200 if already_registered else 201, body)

        def _handle_action(
            self, project_id: str, request_id: str, declared_length: int
        ) -> None:
            session = self._authenticate_session(
                request_id, project_id, require_csrf=True
            )
            if session is None:
                return
            if not ctx.action_limiter.try_consume(session.cookie_digest):
                self._send_error(
                    429,
                    "rate_limited",
                    "too many actions",
                    request_id,
                    project_id,
                    retryable=True,
                    extra_headers={"Retry-After": "1"},
                )
                return
            payload = self._read_json_body(declared_length, request_id)
            if payload is None:
                return
            # P69-02.2a/S14: structural validation first -- schema_version
            # must be explicitly present as the supported integer 1; missing,
            # null, string, and bool values are all rejected, never defaulted.
            schema_error = _schema_version_error(payload)
            if schema_error is not None:
                code, message = schema_error
                self._send_error(400, code, message, request_id, project_id)
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
            expected = payload.get("expected")
            if expected is not None and not isinstance(expected, dict):
                self._send_error(
                    400,
                    "malformed_request",
                    "expected must be an object",
                    request_id,
                    project_id,
                )
                return

            # P69-01.2m: operation-specific argument field allowlist -- reject
            # an unsupported key before any dispatch/grant/preview logic reads it.
            unsupported = set(arguments) - _ARGUMENT_ALLOWLIST.get(
                operation, frozenset()
            )
            if unsupported:
                self._send_error(
                    400,
                    "unsupported_argument",
                    f"{operation} does not accept argument(s): "
                    f"{', '.join(sorted(unsupported))}",
                    request_id,
                    project_id,
                )
                return

            # P69-02.2a: reject an unsupported top-level grant key instead of
            # silently ignoring it -- mirrors the argument allowlist above.
            unsupported_grants = set(grants) - _BOOLEAN_GRANT_FIELDS
            if unsupported_grants:
                self._send_error(
                    400,
                    "unsupported_grant",
                    f"unsupported grant(s): {', '.join(sorted(unsupported_grants))}",
                    request_id,
                    project_id,
                )
                return

            # P69-01.2o: `bool("false")` is `True` in Python -- reject a
            # present-but-non-bool grant/apply/archived/user_stated value (400)
            # before any preview classification, permission check, or dispatch
            # reads the coerced value; a genuinely absent field still defaults.
            bad_bools = [
                name
                for name in _BOOLEAN_ARGUMENT_FIELDS
                if name in arguments and not isinstance(arguments[name], bool)
            ] + [
                f"grants.{name}"
                for name in _BOOLEAN_GRANT_FIELDS
                if name in grants and not isinstance(grants[name], bool)
            ]
            if bad_bools:
                self._send_error(
                    400,
                    "malformed_request",
                    f"must be a boolean, not a string/other type: "
                    f"{', '.join(bad_bools)}",
                    request_id,
                    project_id,
                )
                return

            # M08: reject an omitted/malformed/cross-project/cross-session
            # owner_scope before any reservation -- strictly before body_hash
            # and MutationLedger.commit, never left to a dispatch function's
            # own later validation.
            try:
                _validate_memory_owner_scope(
                    operation,
                    arguments,
                    project_id=project_id,
                    session_owner_scope_id=session.owner_scope_id,
                )
            except _ActionDenied as exc:
                self._send_error(exc.status, exc.code, str(exc), request_id, project_id)
                return

            body_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()

            def _build(operation_id: str) -> tuple[int, bytes]:
                # P69-02.2f: every minted operation_id is already scoped to
                # its project by the durable ledger row `reserve()` inserted,
                # so GET .../operations/{operation_id} can 404 a real
                # operation_id requested through the wrong project without
                # any second, in-memory copy of that mapping.
                if operation == "noop":
                    run_id = ctx.mutations.next_run_id()
                    data: dict[str, Any] = {"operation": operation, "run_id": run_id}
                    return 202, _success_body(
                        request_id,
                        project_id,
                        record.sequence,
                        data,
                        redact=self._redact_secrets(),
                    )
                # S08: the check (against `expected`) and the effect it gates
                # share one per-project exclusion window from here on -- a
                # second concurrent request for the same project can no
                # longer pass an identical, now-invalidated `expected` while
                # this one's effect is still in flight, closing the
                # check-then-act race between `_check_expected_identity` and
                # dispatch. Never held nested with any run-level lock.
                with ctx.projects.mutation_lock(project_id):
                    # P69-02.2b: the MutationLedger reservation above already
                    # decided this is a genuinely new request_id -- `_build` is
                    # never called for a cached replay -- so it's now safe to
                    # compare `expected` against current state exactly once.
                    conflict_reason = _check_expected_identity(record, expected)
                    if conflict_reason is not None:
                        return 409, _error_body(
                            request_id,
                            project_id,
                            "stale_expected_identity",
                            conflict_reason,
                            retryable=True,
                            redact=self._redact_secrets(),
                        )
                    try:
                        status_code, data = _dispatch_scan_action(
                            ctx,
                            project_id,
                            operation,
                            arguments,
                            grants,
                            operation_id=operation_id,
                            expected=expected,
                            effect_ids=effect_ids,
                        )
                    except _ActionDenied as exc:
                        return exc.status, _error_body(
                            request_id,
                            project_id,
                            exc.code,
                            str(exc),
                            retryable=exc.retryable,
                            redact=self._redact_secrets(),
                        )
                    except Exception:  # noqa: BLE001 -- P69-01.2m exception
                        # boundary: any exception dispatch itself doesn't
                        # already convert to a structured error (a raw
                        # ActionDenied/ProjectError) must still return the
                        # envelope, never a raw exception body/stack trace.
                        return 500, _error_body(
                            request_id,
                            project_id,
                            "internal_error",
                            f"unexpected error handling {operation}",
                            redact=self._redact_secrets(),
                        )
                return status_code, _success_body(
                    request_id,
                    project_id,
                    record.sequence,
                    data,
                    redact=self._redact_secrets(),
                )

            mutating = _classify_mutating(operation, arguments)
            # S04: preallocate this operation's proposed effect-key map
            # before reservation so it's persisted in the same transaction
            # as the operation_id -- never reminted by a builder afterward.
            effect_ids = (
                _s04_effect_ids(operation, arguments, project_id) if mutating else {}
            )
            try:
                (status_code, body), conflict = ctx.mutations.commit(
                    project_id,
                    mutation_id,
                    body_hash,
                    _build,
                    operation_type=operation,
                    mutating=mutating,
                    validated_arguments=arguments,
                    effect_ids=effect_ids,
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


# S13: built once from the same shared header source normal responses use.
# The pre-thread admission gate below rejects a connection before any
# handler is allocated, so it cannot call `_send_json` -- it must carry the
# exact same security headers by hand.
_PRE_THREAD_503_RESPONSE = (
    "HTTP/1.1 503 Service Unavailable\r\n"
    "Content-Length: 0\r\n"
    "Retry-After: 1\r\n"
    + "".join(f"{key}: {value}\r\n" for key, value in SECURITY_RESPONSE_HEADERS)
    + "Connection: close\r\n\r\n"
).encode("ascii")


class _AdmissionControlledServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that gates worker-thread creation on a bounded
    admission semaphore.

    Stdlib ThreadingMixIn.process_request() spawns a new thread for every
    accepted connection before any handler code runs -- a semaphore
    acquired inside a handler only rejects work a thread has already been
    created to run. Acquire here instead, before super().process_request()
    ever starts that thread; release in shutdown_request(), which every
    worker thread calls in a `finally` on every exit path (normal
    completion, an unhandled exception, or a client disconnect mid-request)."""

    def __init__(
        self, *args: Any, max_concurrent: int = MAX_CONCURRENT_REQUESTS, **kwargs: Any
    ) -> None:
        self._admission = threading.Semaphore(max_concurrent)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._admission.acquire(blocking=False):
            with suppress(OSError):
                request.sendall(_PRE_THREAD_503_RESPONSE)
            with suppress(OSError):
                request.close()
            return
        super().process_request(request, client_address)

    def shutdown_request(self, request: Any) -> None:
        try:
            super().shutdown_request(request)
        finally:
            self._admission.release()


def create_dashboard_server(
    projects: dict[str, dict[str, Any]],
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    data_root: Path | None = None,
) -> tuple[ThreadingHTTPServer, DashboardContext, str]:
    """Start a canonical per-server authenticated dashboard API.

    Returns the running server, its DashboardContext (auth/session/project
    state) and the initial one-use bootstrap token. Each call builds an
    entirely fresh context and handler class, so two concurrently-running
    servers never share auth, session, or project state. Use
    bootstrap_launch_url() to format the returned token for display.
    """
    server = _AdmissionControlledServer((host, port), BaseHTTPRequestHandler)
    actual_port = server.server_address[1]

    ctx = DashboardContext(
        projects, bound_host=host, bound_port=actual_port, data_root=data_root
    )
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


def dispatch_control_check_suite(
    base_url: str,
    control_token: str,
    project_id: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """P69-06e: client side of `POST /api/control/check-suite`.

    The TUI process holds the control capability (read from the running
    server's own descriptor), never a browser session -- so this sends no
    cookie, no CSRF token, and no `Origin`, exactly like
    `reconnect_dashboard` above. Returns the 202 payload, whose
    `operation_id` polls/cancels through the ordinary operation surface.
    """
    import urllib.request

    body = json.dumps(
        {
            "schema_version": 1,
            "project_id": project_id,
            "request_id": request_id or uuid.uuid4().hex,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/control/check-suite",
        data=body,
        method="POST",
        headers={
            "X-Rush-Control": control_token,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read())
    return dict(payload.get("data") or {})


def _control_session(base_url: str, control_token: str) -> tuple[str, str]:
    """Exchange a control capability for a real browser-shaped session
    (cookie + CSRF token). The action routes below are deliberately
    browser-facing -- a local control-capability holder reaches them by
    minting a genuine session through the same public exchange, never by
    bypassing that boundary."""
    import urllib.request

    token = reconnect_dashboard(base_url, control_token)
    request = urllib.request.Request(
        f"{base_url}/api/session",
        data=b"",
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Length": "0"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        cookie = (response.headers.get("Set-Cookie") or "").split(";")[0]
        payload = json.loads(response.read())
    return cookie, payload["csrf_token"]


def dispatch_dashboard_action(
    base_url: str,
    control_token: str,
    project_id: str,
    operation: str,
    *,
    arguments: dict[str, Any] | None = None,
    grants: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """P69-06d: dispatch one real scan-lifecycle action (`scan_start`,
    `scan_resume`, `rescan`) into an already-running dashboard server.

    Used by the TUI when a live dashboard server owns the project at
    scan-*start* time: that process is the executor from the first moment,
    so nothing is ever transferred to it mid-flight."""
    import urllib.request

    cookie, csrf = _control_session(base_url, control_token)
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "request_id": request_id or uuid.uuid4().hex,
            "arguments": arguments or {},
            "grants": grants or {},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/projects/{project_id}/actions",
        data=body,
        method="POST",
        headers={
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    return dict(payload.get("data") or {})


def dispatch_dashboard_operation_status(
    base_url: str,
    project_id: str,
    operation_id: str,
    *,
    session: tuple[str, str],
) -> dict[str, Any]:
    """U02: client side of `GET /api/projects/{project_id}/operations/
    {operation_id}`, using an already-exchanged `(cookie, csrf)` session
    pair -- this function never bootstraps; the caller (`DashboardOwner`)
    owns session acquisition/caching/renewal across repeated polls. The
    route itself never requires CSRF for a plain read."""
    import urllib.request

    cookie, _csrf = session
    request = urllib.request.Request(
        f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
        method="GET",
        headers={"Cookie": cookie, "Origin": base_url},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read())
    return dict(payload.get("data") or {})
