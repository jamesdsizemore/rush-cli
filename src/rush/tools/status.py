"""Phase 70 T23: the shared, read-only project status.

`rush status`, bare `rush` and MCP `rush_status` all run `StatusTool`. One
call reports the selected root and its registration, configuration, engine
readiness (no version probe), the current scan activity and latest attempt,
the published result, agent registration and activation evidence, and the
useful memory count. It writes nothing and spawns nothing: every reader is
the strict or zero-write variant (strict registry, `read_ledger_view`,
`observe_owner`, `read_sqlite_readonly`, plain agent-memory JSON).

`operation="result"` reads a stored result through the continuity retrieval
behind `rush context retrieve`; the stored analysis status is returned as it
was recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import time
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

from rush.invocation.models import InvocationContext, InvocationError
from rush.tools.base import ToolFn, ToolResult, ToolResultV1

StatusOperation = Literal["status", "result"]
_ACTIVITY = {"alive": "running", "dead": "owner_dead"}
_WARN_ACTIVITY = frozenset({"activity_unverified", "owner_dead"})
_WARN_ATTEMPT = frozenset({"latest_unresolved", "chronology_ambiguous"})
_ATTEMPT_PHRASES = {
    "none": "no analysis has run",
    "resolved": "latest run {run_id} completed",
    "incomplete": "latest run {run_id} is incomplete",
    "latest_unresolved": "latest run is unresolved",
    "chronology_ambiguous": "latest run is ambiguous",
}


class StatusTool(ToolFn):
    """Read-only status of the selected project (T23)."""

    name = "status"
    # Test/embedding seams, never published over MCP (`make_tool_wrapper`).
    internal_parameters: ClassVar[frozenset[str]] = frozenset({"data_root", "home"})

    @property
    def mcp_description(self) -> str:
        from rush.catalog import TOOL_SPECS

        return TOOL_SPECS["status"].mcp_description

    def __call__(
        self,
        path: Path | str | None = None,
        operation: StatusOperation = "status",
        session_id: str | None = None,
        result_handle: str | None = None,
        view: Literal["result", "bytes"] | None = None,
        cursor: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        max_bytes: int | None = None,
        *,
        context: InvocationContext | None = None,
        data_root: Path | None = None,
        home: Path | None = None,
    ) -> ToolResult:
        from rush.setup.provision import DataRootUnavailableError, default_data_root

        started = time.monotonic()
        raw, source, anchor = _requested_target(path, context)
        try:
            base = data_root if data_root is not None else default_data_root()
        except DataRootUnavailableError as exc:
            return _envelope(
                started, operation, None, _error("DATA_ROOT_UNAVAILABLE", exc)
            )
        if operation == "result":
            from rush.workflows.projects import read_registry_state

            return _result_operation(
                raw,
                anchor,
                _index(read_registry_state(base).registry),
                result_handle,
                {"view": view, "cursor": cursor, "offset": offset, "limit": limit},
                max_bytes,
                started,
            )
        return collect_status(
            raw,
            source,
            anchor,
            session_id=session_id,
            data_root=base,
            home=home if home is not None else Path.home(),
            started=started,
        )


# --- selection -------------------------------------------------------------------


def _requested_target(
    path: Path | str | None, context: InvocationContext | None
) -> tuple[str | None, str, Path]:
    """`(raw target, source, anchor)`. Through a transport the bound `path`
    is always the walked target, so explicit input is read from the verbatim
    original (T8: omitted means unavailable) and a declared project root."""
    if context is None:
        return (
            (None, "cwd", Path.cwd())
            if path is None
            else (str(path), "path", Path.cwd())
        )
    anchor = (
        context.declared_root or context.invocation_start_cwd or context.workspace_root
    )
    if context.original_requested_targets:
        return context.original_requested_targets[0], "path", anchor
    if context.declared_root is not None:
        return ".", "project", anchor
    return None, "cwd", anchor


def _index(registry: dict[str, Any] | None) -> dict[str, str]:
    projects = (registry or {}).get("projects") or {}
    return {
        str(pid): str(entry["root"])
        for pid, entry in projects.items()
        if isinstance(entry, dict) and isinstance(entry.get("root"), str)
    }


def _select(
    raw: str | None,
    source: str,
    anchor: Path,
    session_id: str | None,
    data_root: Path,
    index: dict[str, str],
) -> dict[str, Any]:
    """Explicit target > `session_id` binding > the invocation cwd. A bound
    session names a registered root directly; everything else takes the T8
    ROOT-ENTRY walk. Raises `InvocationError` for an unusable target."""
    from rush.invocation.targets import select_root
    from rush.workflows.projects import read_session_selections_strict

    selection: dict[str, Any] = {
        "source": source,
        "requested_path": raw,
        "original_input": raw,
        "observed_root": None,
        "logical_root": None,
        "session_id": session_id,
        "session_state": None,
    }
    if raw is None and session_id is not None:
        sessions = read_session_selections_strict(data_root)
        selection["session_state"] = sessions["state"]
        bound = (sessions["selections"] or {}).get(session_id)
        if isinstance(bound, str) and bound in index:
            selection.update(source="session", logical_root=index[bound])
            return selection
    walked = select_root("." if raw is None else raw, anchor=anchor, index=index)
    selection.update(observed_root=str(walked.root), logical_root=str(walked.root))
    return selection


def _project(
    root: Path, index: dict[str, str], registry: dict[str, Any] | None
) -> dict[str, Any]:
    """Registered only when a registry root equals the logical root; a second
    registered root containing it (nested registrations) is `ambiguous`."""
    containing = sorted(
        pid for pid, r in index.items() if Path(r) == root or Path(r) in root.parents
    )
    exact = [pid for pid in containing if Path(index[pid]) == root]
    view: dict[str, Any] = {
        "registration": "unregistered",
        "project_id": None,
        "name": None,
        "root": str(root),
        "revision": None,
        "configured": False,
        "root_exists": root.is_dir(),
        "ambiguous_ids": [],
    }
    if exact and len(containing) > 1:
        view.update(registration="ambiguous", ambiguous_ids=containing)
    elif exact:
        entry = ((registry or {}).get("projects") or {})[exact[0]]
        view.update(
            registration="registered",
            project_id=exact[0],
            name=entry.get("name", root.name),
            revision=entry.get("revision"),
            configured=bool(entry.get("configured", False)),
        )
    return view


# --- readers ---------------------------------------------------------------------


def _config(root: Path) -> dict[str, Any]:
    """`missing | valid | invalid | unreadable` for `<root>/rush.toml`; a
    symlinked config is never followed."""
    from rush.config import RushConfigError, load_config

    path = root / "rush.toml"
    view: dict[str, Any] = {
        "state": "missing",
        "path": str(path),
        "sha256": None,
        "diagnostic": None,
    }
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("rush.toml is not a regular file")
        data = path.read_bytes()
    except FileNotFoundError:
        return view
    except OSError as exc:
        return {**view, "state": "unreadable", "diagnostic": str(exc)}
    view.update(state="valid", sha256=hashlib.sha256(data).hexdigest())
    try:
        load_config(start=root)
    except RushConfigError as exc:
        view.update(state="invalid", diagnostic=str(exc))
    return view


def _manifest_version(engine_id: str, root: Path) -> str | None:
    """The version recorded in the verified provision manifest the resolver
    selected (never an executable probe)."""
    from rush.runtime.binaries import read_manifest

    try:
        selection = json.loads((root / ".rush" / "toolchains.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    entry = selection.get(engine_id) if isinstance(selection, dict) else None
    manifest_path = entry.get("manifest") if isinstance(entry, dict) else None
    manifest = (
        read_manifest(Path(manifest_path)) if isinstance(manifest_path, str) else None
    )
    return manifest.version if manifest is not None else None


_ENGINE_REASONS = {
    "installed": "resolved by the secure resolver ({source})",
    "missing": "not found by the secure resolver",
    "unsupported": "no Rush-managed package; install manually if needed",
}


def _engines(root: Path) -> dict[str, Any]:
    """T15 readiness with `probe=False`: nothing is executed."""
    from rush.tools.doctor import build_engine_inventory

    if not root.is_dir():
        return {"state": "unavailable", "items": []}
    items = []
    for entry in build_engine_inventory(root, probe=False):
        version = (
            _manifest_version(entry["engine"], root)
            if entry["source"] == "manifest"
            else None
        )
        items.append(
            {
                "engine_id": entry["engine"],
                "required": entry["required"],
                "disposition": entry["disposition"],
                "executable": entry["executable"],
                "version": version,
                "version_source": "manifest" if version is not None else "unprobed",
                "reason": _ENGINE_REASONS[entry["disposition"]].format(
                    source=entry["source"]
                ),
                "setup_action": entry["action"] or None,
            }
        )
    missing = any(i["required"] and i["disposition"] == "missing" for i in items)
    return {
        "state": "missing" if missing else ("ready" if items else "none"),
        "items": items,
    }


def _memory(root: Path) -> dict[str, Any]:
    """T18's useful-memory count over the zero-write reader."""
    from rush.memory.store import (
        MemoryStoreUnreadableError,
        read_sqlite_readonly,
        useful_memory_count,
    )

    db = root / ".rush" / "memory.db"
    if db.parent.is_symlink() or db.is_symlink():
        return {
            "state": "unavailable",
            "useful_count": None,
            "reason": "memory.db is behind a symlink",
        }
    if not db.exists():
        return {"state": "absent", "useful_count": None, "reason": "no memory store"}

    def read(conn: Any) -> int | None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if not {"source", "artifact_version", "archived_at", "expired_at"} <= columns:
            return None
        return useful_memory_count(conn)

    try:
        count = read_sqlite_readonly(db, read)
    except MemoryStoreUnreadableError as exc:
        state = "corrupt" if exc.code == "E_STORE_CORRUPT" else "unavailable"
        return {"state": state, "useful_count": None, "reason": str(exc)}
    if count is None:
        return {
            "state": "migration_required",
            "useful_count": None,
            "reason": "memory.db predates the current schema",
        }
    return {"state": "available", "useful_count": count, "reason": None}


def _agents(
    home: Path, data_root: Path, root: Path, session_id: str | None
) -> list[dict[str, Any]]:
    """Registration from the host configs, activation only from an
    acknowledged readiness entry -- never "connected" or "live"."""
    from rush.integrations.agents import (
        AgentConnectionError,
        discover_agents,
        read_agent_memory_state_strict,
        resolve_rush_binary,
    )

    try:
        rush_binary: str | None = resolve_rush_binary()
    except AgentConnectionError:
        rush_binary = None
    scopes = (
        read_agent_memory_state_strict(data_root=data_root),
        read_agent_memory_state_strict(project_root=root) if root.is_dir() else {},
    )
    entries = [
        e for scope in scopes for e in (scope or {}).values() if isinstance(e, dict)
    ]
    rows = []
    for status in discover_agents(home=home, rush_binary=rush_binary):
        acknowledged = [
            e
            for e in entries
            if e.get("agent_id") == status.agent_id
            and e.get("connected") is True
            and (session_id is None or e.get("session_id") == session_id)
        ]
        rows.append(
            {
                "agent_id": status.agent_id,
                "state": status.status,
                "config_path": str(status.config_path) if status.config_path else None,
                "activation": "acknowledged" if acknowledged else "unverified",
                "acknowledged_at": max(
                    (e.get("acknowledged_at") or 0 for e in acknowledged), default=None
                ),
                "restart_required": status.restart_required,
                "capability_verified": False,
            }
        )
    return rows


def _source_changed(header: dict[str, Any], root: Path) -> bool | None:
    """Compare the attempt's pre-execution signature with the tree now; `None`
    when the header carries no comparable signature."""
    from rush.workflows.project_run import _signature_comparable, _source_signature

    signature = header.get("source_signature")
    if not isinstance(signature, str) or not _signature_comparable(
        header.get("source_signature_format")
    ):
        return None
    return _source_signature(root) != signature


def _published(chronology: Any, ledger: dict[str, Any], root: Path) -> dict[str, Any]:
    """The ledger's published attempt when recorded, else the most recently
    started completed attempt. Its counts are that attempt's only."""
    row = ledger.get("published") or {}
    run_id = row.get("latest_published_run_id")
    if run_id:
        attempt_id = row.get("latest_published_attempt_id")
        attempt = next(
            (
                a
                for a in chronology.attempts
                if a.run_id == run_id and attempt_id in (None, a.attempt_id)
            ),
            None,
        )
        source, generation = "ledger", row.get("published_generation")
        state = (
            "resolved"
            if attempt is not None and attempt.completed
            else "missing_evidence"
        )
    else:
        attempt, source, state = (
            chronology.published,
            "attempt_chronology",
            chronology.published_state,
        )
        attempt_id = attempt.attempt_id if attempt else None
        run_id = attempt.run_id if attempt else None
        generation = attempt.attempt_generation if attempt else None
    view: dict[str, Any] = {
        "state": state,
        "source": source,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "generation": generation,
        "run_state": None,
        "finding_count": None,
        "stale": None,
        "source_changed": None,
    }
    if attempt is None or attempt.manifest is None:
        return view
    changed = _source_changed(attempt.header, root)
    newer = any(a.started_at > attempt.started_at for a in chronology.attempts)
    view.update(
        run_state=attempt.manifest.get("run_state"),
        finding_count=len(
            (attempt.manifest.get("aggregate") or {}).get("findings") or []
        ),
        source_changed=changed,
        stale=True
        if newer or changed
        else ("unverifiable" if changed is None else False),
    )
    return view


def _latest_attempt(
    chronology: Any, admission: dict[str, Any] | None
) -> dict[str, Any]:
    """The chronology's latest attempt, unless the ledger admission names a
    validated attempt: that is the current one."""
    latest = chronology.to_dict()
    if not admission:
        return latest
    current = next(
        (
            a
            for a in chronology.attempts
            if a.run_id == admission.get("run_id")
            and a.attempt_id == admission.get("attempt_id")
        ),
        None,
    )
    if current is None:
        return latest
    return {
        **latest,
        "state": "resolved" if current.completed else "incomplete",
        "run_id": current.run_id,
        "attempt_id": current.attempt_id,
        "started_at": current.started_at.isoformat(),
        "attempt_generation": current.attempt_generation,
        "ordering": "scan_admission",
        "affected_ids": [],
    }


def _activity(ledger: dict[str, Any], data_root: Path) -> dict[str, Any]:
    from rush.dashboard.state import observe_owner

    admission = ledger.get("admission")
    if ledger["state"] in ("corrupt", "busy"):
        return {"state": "unavailable", "admission": None}
    if not admission:
        return {"state": "idle", "admission": None}
    observed = observe_owner(admission.get("owner_instance_id") or "", data_root)
    return {
        "state": _ACTIVITY.get(observed, "activity_unverified"),
        "admission": admission,
    }


# --- assembly --------------------------------------------------------------------


def _next_actions(data: dict[str, Any]) -> list[dict[str, Any]]:
    project = data["project"]
    root = shlex.quote(project["root"])
    actions: list[dict[str, Any]] = []
    if data["registry"]["state"] in ("corrupt", "unreadable"):
        actions.append(
            {
                "reason": f"project registry is {data['registry']['state']}: {data['registry']['path']}",
                "command": None,
            }
        )
    if project["registration"] == "unregistered":
        actions.append(
            {"reason": "project is not registered", "command": f"rush setup {root}"}
        )
    elif project["registration"] == "registered" and not project["configured"]:
        actions.append(
            {"reason": "project is not configured", "command": f"rush setup {root}"}
        )
    actions.extend(
        {
            "reason": f"{item['engine_id']} is not installed",
            "command": item["setup_action"],
        }
        for item in data["engines"]["items"]
        if item["required"] and item["disposition"] == "missing"
    )
    if project["registration"] == "registered" and (
        data["latest_attempt"]["state"] == "none" or data["published"]["stale"] is True
    ):
        actions.append(
            {
                "reason": "no current analysis result",
                "command": f"rush scan --project {root}",
            }
        )
    return actions


def _problems(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings) per the §3.2 envelope: corrupt/unreadable
    authoritative state is an error; missing setup, unresolved chronology,
    unverified activity and a stale result are warnings."""
    errors, warnings = [], []
    registry, project = data["registry"]["state"], data["project"]["registration"]
    if registry in ("corrupt", "unreadable"):
        errors.append(f"project registry is {registry}")
    if data["selection"]["session_state"] in ("corrupt", "unreadable"):
        errors.append(f"session selection file is {data['selection']['session_state']}")
    if project == "ambiguous":
        errors.append(
            "nested registered roots: " + ", ".join(data["project"]["ambiguous_ids"])
        )
    if data["ledger_state"] == "corrupt":
        errors.append("mutation ledger is corrupt")
    if data["memory"]["state"] == "corrupt":
        errors.append("memory store is corrupt")
    if project == "unregistered":
        warnings.append("project is not registered")
    elif project == "registered" and not data["project"]["configured"]:
        warnings.append("project is not configured")
    if data["config"]["state"] in ("invalid", "unreadable"):
        warnings.append(f"rush.toml is {data['config']['state']}")
    if data["engines"]["state"] == "missing":
        warnings.append("a required engine is missing")
    if data["latest_attempt"]["state"] in _WARN_ATTEMPT:
        warnings.append(_ATTEMPT_PHRASES[data["latest_attempt"]["state"]])
    if data["activity"]["state"] in _WARN_ACTIVITY:
        warnings.append(f"scan activity is {data['activity']['state']}")
    if data["published"]["stale"] is True:
        warnings.append("published result is stale")
    return errors, warnings


def collect_status(
    raw: str | None,
    source: str,
    anchor: Path,
    *,
    session_id: str | None,
    data_root: Path,
    home: Path,
    started: float,
) -> ToolResult:
    """Every T23 reader, assembled into the status envelope."""
    from rush.dashboard.state import read_ledger_view
    from rush.workflows.projects import read_registry_state, select_attempt_chronology

    registry = read_registry_state(data_root)
    index = _index(registry.registry)
    try:
        selection = _select(raw, source, anchor, session_id, data_root, index)
    except (InvocationError, OSError) as exc:
        return _envelope(started, "status", None, _selection_error(exc))
    root = Path(selection["logical_root"])
    project = _project(root, index, registry.registry)
    project_id = project["project_id"]
    chronology = select_attempt_chronology(root, project_id)
    ledger = (
        read_ledger_view(project_id, data_root)
        if project_id
        else {"state": "absent", "admission": None, "published": None, "error": None}
    )
    activity = _activity(ledger, data_root)
    data: dict[str, Any] = {
        "selection": selection,
        "registry": {
            "state": registry.state,
            "path": registry.path,
            "error": registry.error,
            "sha256": registry.sha256,
        },
        "project": project,
        "config": _config(root),
        "engines": _engines(root),
        "ledger_state": ledger["state"],
        "activity": activity,
        "published": _published(chronology, ledger, root),
        "latest_attempt": _latest_attempt(chronology, activity["admission"]),
        "agents": _agents(home, data_root, root, session_id),
        "memory": _memory(root),
    }
    data["next_actions"] = _next_actions(data)
    errors, warnings = _problems(data)
    error = _error("STATUS_STATE_UNREADABLE", "; ".join(errors)) if errors else None
    return _envelope(started, "status", data, error, warnings)


def _summary(
    data: dict[str, Any] | None, error: dict[str, Any] | None, warnings: list[str]
) -> str:
    if data is None:
        return f"status unavailable: {error['message'] if error else 'unknown'}"
    project = data["project"]
    who = project["name"] or project["root"]
    latest = data["latest_attempt"]
    phrase = _ATTEMPT_PHRASES[latest["state"]].format(run_id=latest["run_id"])
    parts = [f"{project['registration']} project {who}", phrase]
    if error:
        parts.append(error["message"])
    parts.extend(w for w in warnings if w != phrase)
    return "; ".join(parts) + "."


def _error(code: str, message: object) -> dict[str, Any]:
    return {"code": code, "message": str(message), "retryable": False}


def _selection_error(exc: Exception) -> dict[str, Any]:
    """An unusable target (`TARGET_INVALID` for malformed input, T9) or a
    walk that cannot select a root (containment, missing anchor)."""
    return _error(getattr(exc, "code", "ROOT_SELECTION_FAILED"), exc)


def _envelope(
    started: float,
    operation: str,
    data: dict[str, Any] | None,
    error: dict[str, Any] | None,
    warnings: list[str] | None = None,
) -> ToolResult:
    warnings = warnings or []
    status = "error" if error else ("warn" if warnings else "ok")
    return cast(
        ToolResult,
        {
            "tool": "status",
            "engine": None,
            "engine_version": None,
            "status": status,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "summary": _summary(data, error, warnings),
            "findings": [],
            "raw": {
                "schema_version": 1,
                "operation": operation,
                "data": data,
                "error": error,
            },
        },
    )


def _result_operation(
    raw: str | None,
    anchor: Path,
    index: dict[str, str],
    handle: str | None,
    page: dict[str, Any],
    max_bytes: int | None,
    started: float,
) -> ToolResult:
    """The stored result through the continuity retrieval behind `rush
    context retrieve --view` (T16). Never reruns anything; a delivery error
    also carries the status envelope's `raw.error`."""
    from rush.invocation.targets import select_root
    from rush.tools.continuity import SessionContinuityTool

    if not handle:
        return _envelope(
            started,
            "result",
            None,
            _error("RESULT_HANDLE_REQUIRED", "operation=result needs result_handle"),
        )
    try:
        root = select_root("." if raw is None else raw, anchor=anchor, index=index).root
    except (InvocationError, OSError) as exc:
        return _envelope(started, "result", None, _selection_error(exc))
    page_result = SessionContinuityTool().run(
        root,
        operation="context_retrieve",
        context_handle=handle,
        view=page["view"] or "result",
        cursor=page["cursor"],
        offset=page["offset"],
        limit=page["limit"],
        max_bytes=max_bytes,
    )
    result: dict[str, Any] = (
        page_result.to_dict()
        if isinstance(page_result, ToolResultV1)
        else dict(page_result)
    )
    failure = (result.get("metadata") or {}).get("error")
    if result.get("status") == "error" and isinstance(failure, dict):
        result["raw"] = {
            "schema_version": 1,
            "operation": "result",
            "data": None,
            "error": _error(
                failure.get("code", "RESULT_ERROR"), failure.get("message", "")
            ),
        }
    return cast(ToolResult, result)


# --- CLI ---------------------------------------------------------------------------


def run_status_cli(
    path: Path | None,
    *,
    session_id: str | None,
    result_handle: str | None,
    view: str | None,
    cursor: str | None,
    offset: int | None,
    limit: int | None,
    max_bytes: int | None,
) -> Any:
    """`rush status` / bare `rush`: one invocation through the shared executor
    with no config gate (`config=None`), anchored at the invocation cwd."""
    from rush.invocation import InvocationExecutor, resolve_invocation

    anchor = Path.cwd()
    request: dict[str, Any] = {
        "operation_id": "status",
        "path": ".",
        "operation": "result" if result_handle is not None else "status",
        "session_id": session_id,
        "result_handle": result_handle,
        "view": view,
        "cursor": cursor,
        "offset": offset,
        "limit": limit,
        "max_bytes": max_bytes,
    }
    context = resolve_invocation(
        {k: v for k, v in request.items() if v is not None},
        transport="cli",
        workspace_root=anchor,
        config=None,
        original_requested_targets=None if path is None else (str(path),),
        invocation_start_cwd=anchor,
    )
    executor = InvocationExecutor()
    executor.register("status", StatusTool().__call__)
    return executor.execute(context)


def _terminal_safe(value: object) -> str:
    """C0 (except newline/tab), DEL and C1 controls as visible `\\xNN`."""
    return "".join(
        f"\\x{ord(ch):02x}"
        if (ord(ch) < 32 and ch not in "\n\t") or 127 <= ord(ch) <= 159
        else ch
        for ch in str(value)
    )


def render_status(result: dict[str, Any]) -> str:
    """Human status: Project, Config, Engines, Activity, Latest attempt,
    Published result, Agents, Memory, Next actions."""
    from rush.safety.redactor import sanitize_value

    clean = sanitize_value(result).value
    data = (clean.get("raw") or {}).get("data")
    lines = [f"rush status: {clean.get('status')} -- {clean.get('summary')}"]
    if data:
        lines.extend(_status_sections(data))
    return "\n".join(_terminal_safe(line) for line in lines) + "\n"


def _status_sections(data: dict[str, Any]) -> list[str]:
    project, config, engines = data["project"], data["config"], data["engines"]
    activity, latest, published, memory = (
        data["activity"],
        data["latest_attempt"],
        data["published"],
        data["memory"],
    )
    lines = [
        "Project",
        f"  root: {project['root']}",
        f"  registration: {project['registration']}"
        + (f" ({project['project_id']})" if project["project_id"] else ""),
        f"  configured: {'yes' if project['configured'] else 'no'}",
        "Config",
        f"  rush.toml: {config['state']}"
        + (f" -- {config['diagnostic']}" if config["diagnostic"] else ""),
        "Engines",
        *(
            f"  {item['engine_id']}: {item['disposition']}"
            + (f" ({item['version']})" if item["version"] else "")
            for item in engines["items"]
        ),
        *(["  none detected"] if not engines["items"] else []),
        "Activity",
        f"  {activity['state']}"
        + (
            f" (run {activity['admission']['run_id']})" if activity["admission"] else ""
        ),
        "Latest attempt",
        f"  {latest['state']}"
        + (
            f": run {latest['run_id']} started {latest['started_at']}"
            if latest["run_id"]
            else ""
        )
        + (f" [{', '.join(latest['affected_ids'])}]" if latest["affected_ids"] else ""),
        "Published result",
        f"  {published['state']}"
        + (
            f": run {published['run_id']}, {published['finding_count']} finding(s), stale: {published['stale']}"
            if published["run_id"]
            else ""
        ),
        "Agents",
        *(
            f"  {a['agent_id']}: {a['state']}, activation {a['activation']}"
            for a in data["agents"]
        ),
        "Memory",
        f"  {memory['state']}"
        + (
            f": {memory['useful_count']} useful"
            if memory["useful_count"] is not None
            else ""
        ),
        "Next actions",
        *(
            f"  {a['reason']}" + (f": {a['command']}" if a["command"] else "")
            for a in data["next_actions"]
        ),
        *(["  none"] if not data["next_actions"] else []),
    ]
    return lines


__all__ = ["StatusTool", "collect_status", "render_status", "run_status_cli"]
