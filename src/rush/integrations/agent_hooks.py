"""`rush agent hook <host>`: opt-in, model-visible post-edit checks (Phase 70 T7).

The Rush Claude Code/Codex plugins run `<rush> agent hook <host>` after every
edit. Until `rush agent connect ... --enable-agent-hooks` records an
activation for that host and project, the adapter prints nothing, runs no
check and writes nothing. The gate reads the activation record without
creating any file or directory (design brief X5: `lstat` + `json.loads`,
never `CASMapTransaction`).

An activated event runs the shared `CheckTool` once, with no grants, bounded
by an internal deadline below the host's 30-second hook timeout, and returns
a bounded summary in the host's native context field. The hook always exits
0: a failure never changes the edit's result.
"""

from __future__ import annotations

import contextvars
import fnmatch
import hashlib
import json
import logging
import os
import shlex
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rush.setup.provision import DataRootUnavailableError, default_data_root

HOOK_HOSTS = ("claude", "codex", "cursor", "antigravity", "zcode")
#: Agent ids (`rush agent connect AGENT`) whose Rush plugin ships the hook.
HOOK_AGENTS = {
    "claude-code": "claude",
    "codex": "codex",
    "cursor": "cursor",
    "antigravity": "antigravity",
    "zcode": "zcode",
}
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 8192
#: Below the plugins' `"timeout": 30`, so a slow check is reported, not killed.
# Reserve 15s of the host's 30s total budget for native startup and feedback.
DEADLINE_SECONDS = 15.0
ACTIVE_ENV = "RUSH_AGENT_HOOK_ACTIVE"
_EDIT_TOOLS = {
    "claude": frozenset({"Write", "Edit", "MultiEdit"}),
    "codex": frozenset({"apply_patch", "Edit", "Write"}),
}
_PATH_FIELDS = ("file_path", "notebook_path")
_MESSAGE_CHARS = 240
_SEVERITY_RANK = {"error": 0, "fail": 0, "warn": 1, "warning": 1}


def activation_record_path(data_root: Path) -> Path:
    return data_root / "agent-hooks" / "activations.json"


def read_activation_record(data_root: Path) -> Any | None:
    """The parsed activation record, or None when absent or unreadable."""
    path = activation_record_path(data_root)
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def _valid_record(record: Any) -> bool:
    return (
        isinstance(record, dict)
        and record.get("host") in HOOK_HOSTS
        and isinstance(record.get("project_id"), str)
        and isinstance(record.get("canonical_root"), str)
        and type(record.get("recovery_cache_write")) is bool
    )


def _records(document: Any) -> list[Any] | None:
    """`{"activations": [record, ...]}`'s records; None when not that shape."""
    if not isinstance(document, dict) or not isinstance(
        document.get("activations"), list
    ):
        return None
    return list(document["activations"])


# --- The hook ---------------------------------------------------------------


def _diagnose(message: str) -> None:
    """One diagnostic line on the process's stderr; stdout stays the host's
    context channel."""
    try:
        os.write(2, f"rush agent hook: {message}\n".encode("utf-8", "replace"))
    except OSError:
        pass


_QUIET: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "rush_agent_hook_quiet", default=False
)


class _QuietFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.ERROR or not _QUIET.get()


_QUIET_FILTER = _QuietFilter()


@contextmanager
def quiet_logging() -> Iterator[None]:
    """Below-ERROR `rush` log records from this context are dropped: the
    check's warnings are already in the context text, so stderr carries only
    the hook's own diagnostics and errors. Context-local, so a concurrent
    caller's logging is unaffected."""
    # On the handlers: records from child loggers skip a logger's filters.
    for handler in logging.getLogger("rush").handlers:
        if _QUIET_FILTER not in handler.filters:
            handler.addFilter(_QUIET_FILTER)
    token = _QUIET.set(True)
    try:
        yield
    finally:
        _QUIET.reset(token)


_MARKER_LOCK = threading.Lock()
_MARKER_HOLDERS = 0
_MARKER_PRIOR: str | None = None


def _inherited_active_marker() -> bool:
    """`RUSH_AGENT_HOOK_ACTIVE=1` came from the parent process: this process
    runs under a hook's check. A marker that a concurrent in-process hook set
    for its own children is not inherited."""
    with _MARKER_LOCK:
        return _MARKER_HOLDERS == 0 and os.environ.get(ACTIVE_ENV) == "1"


@contextmanager
def _children_marked() -> Iterator[None]:
    """Every child the check spawns inherits `RUSH_AGENT_HOOK_ACTIVE=1`, so a
    hook it triggers skips instead of recursing."""
    global _MARKER_HOLDERS, _MARKER_PRIOR
    with _MARKER_LOCK:
        if _MARKER_HOLDERS == 0:
            _MARKER_PRIOR = os.environ.get(ACTIVE_ENV)
            os.environ[ACTIVE_ENV] = "1"
        _MARKER_HOLDERS += 1
    try:
        yield
    finally:
        with _MARKER_LOCK:
            _MARKER_HOLDERS -= 1
            if _MARKER_HOLDERS == 0:
                if _MARKER_PRIOR is None:
                    os.environ.pop(ACTIVE_ENV, None)
                else:
                    os.environ[ACTIVE_ENV] = _MARKER_PRIOR


class _Scope:
    """What one activated event checks: `target` under `root`, how it was
    chosen, and which edited paths were excluded."""

    def __init__(
        self,
        root: Path,
        cwd: Path,
        target: Path,
        description: str,
        originals: tuple[str, ...] | None,
        excluded: list[str],
        recovery_cache_write: bool,
    ) -> None:
        self.root = root
        self.cwd = cwd
        self.target = target
        self.description = description
        self.originals = originals
        self.excluded = excluded
        self.recovery_cache_write = recovery_cache_write


def _registered_roots(data_root: Path) -> dict[str, str] | None:
    """project_id -> canonical root from a strict, read-only registry read;
    None when the registry is missing, corrupt or unreadable."""
    from rush.workflows.projects import read_registry_strict

    registry = read_registry_strict(data_root)
    if registry["state"] != "ok":
        return None
    return {
        str(project_id): entry["root"]
        for project_id, entry in registry["registry"]["projects"].items()
        if isinstance(entry, dict) and isinstance(entry.get("root"), str)
    }


def _select_scope(host: str, event: dict[str, Any], data_root: Path) -> _Scope | None:
    """The gate: None means this event is not Rush's to check."""
    from rush.invocation.models import InvocationError
    from rush.invocation.targets import select_member, select_root
    from rush.io.physical_paths import ContainmentError, PhysicalRoot

    if event.get("hook_event_name") != "PostToolUse":
        return None
    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        return None
    if fnmatch.fnmatchcase(tool_name.lower(), "mcp__*rush*"):
        return None  # Rush's own tool: never recurse
    if tool_name not in _EDIT_TOOLS[host]:
        return None
    raw_cwd = event.get("cwd")
    if not isinstance(raw_cwd, str) or "\x00" in raw_cwd:
        return None
    cwd = Path(raw_cwd)
    if not cwd.is_absolute():
        return None
    records = _records(read_activation_record(data_root)) or []
    candidates = [r for r in records if _valid_record(r) and r["host"] == host]
    if not candidates:
        return None
    roots = _registered_roots(data_root)
    if not roots:
        return None

    # The T8 ROOT-ENTRY walk of the host's cwd against each activated root.
    matches: list[tuple[dict[str, Any], Path]] = []
    for record in candidates:
        if roots.get(record["project_id"]) != record["canonical_root"]:
            continue  # unregistered, or re-rooted since activation
        root = Path(record["canonical_root"])
        index = {record["project_id"]: record["canonical_root"]}
        try:
            select_root(raw_cwd, anchor=cwd, declared_root=root, index=index)
        except (InvocationError, OSError, ValueError):
            continue
        matches.append((record, root))
    if not matches:
        return None
    record, root = max(matches, key=lambda match: len(match[1].parts))
    index = {record["project_id"]: record["canonical_root"]}

    tool_input = event.get("tool_input")
    fields = tool_input if isinstance(tool_input, dict) else {}
    raw_paths = [
        value
        for name in _PATH_FIELDS
        if isinstance(value := fields.get(name), str) and value
    ]
    contained: list[tuple[str, Path]] = []
    excluded: list[str] = []
    for raw in raw_paths:
        try:
            relative = select_member(raw, anchor=cwd, root=root, index=index)
            PhysicalRoot(root).open_contained(relative, purpose="read")
        except (InvocationError, ContainmentError, OSError, ValueError):
            excluded.append(raw)
            continue
        contained.append((raw, relative))

    recovery = record["recovery_cache_write"]
    if raw_paths and not contained:
        _diagnose(
            "no check: every edited path is outside the activated project or "
            f"reaches it through a symlink: {', '.join(excluded)}"
        )
        return None
    if len({relative for _, relative in contained}) == 1:
        raw, relative = contained[0]
        return _Scope(
            root,
            cwd,
            root / relative,
            f"edited file {relative.as_posix()}",
            (raw,),
            excluded,
            recovery,
        )
    reason = (
        "the event names several edited files"
        if contained
        else "the event carries no trustworthy edited path"
    )
    return _Scope(
        root, cwd, root, f"project root {root} ({reason})", None, excluded, recovery
    )


def run_agent_hook(host: str, payload: bytes, *, data_root: Path | None = None) -> str:
    """Return the text the hook prints on stdout; empty means no feedback.

    Never raises: every failure is a stderr diagnostic or a bounded context
    line.
    """
    started = time.monotonic()  # the whole hook's deadline starts here
    if host not in _EDIT_TOOLS:
        return ""
    if len(payload) > MAX_PAYLOAD_BYTES:
        _diagnose(f"event exceeds {MAX_PAYLOAD_BYTES} bytes; no check")
        return ""
    if _inherited_active_marker():
        return ""
    try:
        event = json.loads(payload.decode("utf-8"))
    except ValueError:  # includes UnicodeDecodeError
        _diagnose("event is not valid JSON; no check")
        return ""
    if not isinstance(event, dict):
        _diagnose("event is not a JSON object; no check")
        return ""
    try:
        scope = _select_scope(host, event, data_root or default_data_root())
    except DataRootUnavailableError:
        return ""
    except Exception as exc:  # noqa: BLE001 -- the edit's result must never change
        _diagnose(f"gate failed ({type(exc).__name__}); no check")
        return ""
    if scope is None:
        return ""
    invocation_id = uuid.uuid4().hex
    try:
        text = _run_check(scope, invocation_id, started)
    except Exception as exc:  # noqa: BLE001 -- a hook never changes the edit result
        text = _bounded_error(invocation_id, scope, f"{type(exc).__name__}: {exc}")
    return _envelope(text)


_NATIVE_EVENTS = {
    "claude": frozenset(
        {"SessionStart", "PreCompact", "PostToolUse", "PostToolUseFailure", "Stop"}
    ),
    "codex": frozenset(
        {"SessionStart", "PreCompact", "PostToolUse", "PostToolUseFailure", "Stop"}
    ),
    "cursor": frozenset(
        {"sessionStart", "postToolUse", "postToolUseFailure", "preCompact", "stop"}
    ),
    "antigravity": frozenset({"PreInvocation", "PostToolUse", "Stop"}),
    "zcode": frozenset(
        {
            "SessionStart",
            "UserPromptSubmit",
            "PostToolUse",
            "PostToolUseFailure",
            "Stop",
        }
    ),
}
NATIVE_PAYLOAD_BYTES = 65536


def _native_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate event key")
        value[key] = item
    return value


def _native_protocol(host: str, event: str, text: str) -> dict[str, Any]:
    if host == "antigravity":
        if event == "PreInvocation":
            return {"injectSteps": [{"ephemeralMessage": text}]}
        return {"decision": "stop"} if event == "Stop" else {}
    if host == "cursor":
        if event == "preCompact":
            return {
                "user_message": "Rush: refresh scoped task context after compaction with memory bootstrap."
            }
        return {} if event == "stop" else {"additional_context": text}
    if event in ("Stop", "PreCompact"):
        return {}
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _native_checkpoint(
    root: Path,
    request: dict[str, Any],
    host: str,
    session: str,
    event: str,
    payload: dict[str, Any],
    data_root: Path,
) -> dict[str, Any]:
    """Suspend existing complete state; create no task identity, checks or success."""
    from rush.delivery.compact import canonical_json
    from rush.memory.capsule import _checkpoint
    from rush.memory.retrieval import DEFAULT_ENCODING, MemoryAccess, _count_tokens
    from rush.memory.store import TypedArtifactStore
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool, _storage_root

    access, reason = MemoryAccess.resolve_with_reason(
        root,
        operation="write",
        apply=True,
        session_binding=request["session_binding"],
        data_root=data_root,
        task_id=request["task_id"],
    )
    if access is None:
        return {"code": "E_PERMISSION", "reason": reason}
    view, state = TypedArtifactStore.open_readonly_view(_storage_root(access))
    if view is None or state is not None:
        return {"code": "E_NOT_VISIBLE", "reason": state or "checkpoint_required"}
    try:
        newest = None
        offset = 0
        while True:
            rows = view.scope_artifacts(
                "episodic",
                source_allowlist=access.sources,
                owner_scope=access.owner_scope,
                scan_offset=offset,
                scan_limit=64,
                include_archived=False,
                include_expired=False,
            )
            for candidate in rows:
                value = _checkpoint(view, candidate, access)
                if value is not None and value["task_id"] == request["task_id"]:
                    key = (float(candidate["created_at"]), candidate["id"])
                    if newest is None or key > newest[0]:
                        newest = (key, candidate, value)
            offset += len(rows)
            if len(rows) < 64:
                break
        if newest is None:
            return {"code": "E_INPUT", "reason": "checkpoint_required"}
        _, row, content = newest
        required = {
            "schema_version",
            "task_id",
            "task_lineage_id",
            "event_id",
            "event_kind",
            "project_id",
            "worktree_id",
            "source",
            "requirements",
            "implemented",
            "attempted",
            "disproved",
            "checks",
            "unresolved",
            "next_action",
            "origin",
            "description",
            "objective",
            "decisions",
            "blockers",
            "discoveries",
            "evidence_refs",
        }
        arrays = (
            "requirements",
            "implemented",
            "attempted",
            "disproved",
            "checks",
            "unresolved",
            "decisions",
            "blockers",
            "discoveries",
            "evidence_refs",
        )
        if (
            not isinstance(content, dict)
            or not required <= content.keys()
            or any(not isinstance(content[k], list) for k in arrays)
            or not isinstance(content["task_lineage_id"], str)
            or not content["task_lineage_id"]
            or not isinstance(content["source"], dict)
            or not content["next_action"]
            or content["origin"]
            not in ("user_explicit", "agent_report", "tool_receipt")
        ):
            return {"code": "E_INPUT", "reason": "checkpoint_required"}
        if content["task_id"] != request["task_id"]:
            return {"code": "E_INPUT", "reason": "checkpoint_basis_mismatch"}
        source = str(row["source"])
        basis = {
            "artifact_id": row["id"],
            "artifact_version": int(row["artifact_version"]),
        }
    finally:
        view.close()
    payload_sha = hashlib.sha256(canonical_json(payload)).hexdigest()
    discriminator = (
        payload.get("executionNum")
        if host == "antigravity" and event == "Stop"
        else payload.get("tool_use_id", payload_sha)
    )
    identity = hashlib.sha256(
        canonical_json(
            [access.project_id, access.worktree_id, host, session, event, discriminator]
        )
    ).hexdigest()
    existing = content.get("native_event")
    if isinstance(existing, dict) and existing.get("identity") == identity:
        if existing.get("payload_sha256") != payload_sha:
            return {"code": "E_VERSION", "reason": "event_digest_conflict"}
        basis = existing["basis"]
    else:
        content = {
            **content,
            "event_id": "native:" + identity,
            "event_kind": "compact"
            if event in ("PreCompact", "preCompact")
            else "interrupt",
            "origin": "agent_report",
            "native_event": {
                "host": host,
                "session_id": session,
                "event": event,
                "identity": identity,
                "payload_sha256": payload_sha,
                "basis": basis,
            },
        }
        if host == "antigravity":
            content["native_event"]["fully_idle"] = payload["fullyIdle"]
            content["native_event"]["termination_reason"] = payload["terminationReason"]
    body = canonical_json(content)
    if (
        len(body) > 65536
        or _count_tokens(body.decode("utf-8"), DEFAULT_ENCODING) > request["max_tokens"]
    ):
        return {"code": "E_BUDGET", "reason": "checkpoint_too_large"}
    result = MemoryTool().run(
        root,
        operation="write",
        task_id=request["task_id"],
        request={
            "schema_version": 2,
            "subject": "episodic",
            "content": content,
            "source": source,
            "sources": [source],
            "owner_scope": access.owner_scope.as_dict()
            if access.owner_scope is not None
            else None,
            "apply": True,
            "invocation_id": "native:" + identity,
            "effect_id": "checkpoint",
            "expected_basis": basis,
        },
        permissions=ExecutionPermissions(cache_write=True),
    )
    raw = result["raw"]
    assert isinstance(raw, dict)
    return {
        "code": raw["code"],
        "reason": raw["data"].get("reason"),
        "receipt": raw["data"].get("receipt"),
    }


def run_native_agent_hook(
    host: str,
    payload: bytes,
    *,
    event: str,
    data_root: Path | None = None,
    emit: Callable[[bytes], None] | None = None,
) -> bytes:
    """Native T07 protocol; direct calls preview bytes, `emit` owns real delivery.

    Only explicit Rush bootstrap arguments establish intent. Host observations
    are not task starts, check receipts, independent success or checkpoints.
    """
    from rush.delivery import compact
    from rush.integrations import agents
    from rush.memory import authorization as auth
    from rush.tools.memory import (
        MemoryTool,
        _bootstrap_access,
        _validate_bootstrap_request,
    )

    frame: compact.FrameContext | None = None
    result: Any = None
    root: Path | None = None
    request: dict[str, Any] | None = None
    emitting = False
    session = ""
    agent_id = next((aid for aid, name in HOOK_AGENTS.items() if name == host), "")
    resolved_data_root = data_root

    def unavailable(reason: str) -> bytes:
        _diagnose(f"native continuity unavailable: {reason}")
        text = (
            f"Rush continuation unavailable: {reason}. Discover rush_memory and its "
            "bootstrap schema; supply actual task_id, task_kind, query and an "
            "authorized session_binding. Never infer task intent from conversation ID."
        )
        return compact.canonical_json(_native_protocol(host, event, text)) + b"\n"

    def binding_reason() -> str | None:
        assert root is not None and request is not None
        assert resolved_data_root is not None
        current_records = _records(read_activation_record(resolved_data_root)) or []
        if not any(
            _valid_record(r) and r["host"] == host and r["canonical_root"] == str(root)
            for r in current_records
        ):
            return "activation_required"
        current_entries = agents.read_agent_memory_state_strict(
            project_root=root, data_root=resolved_data_root
        )
        current_ready = (current_entries or {}).get(f"{session}::{agent_id}")
        if (
            not isinstance(current_ready, dict)
            or current_ready.get("consent") is not True
            or current_ready.get("connected") is not True
        ):
            return "connection_consent_required"
        loaded = auth.load_policy_readonly(data_root=resolved_data_root)
        if loaded["state"] != "ok":
            return str(loaded["reason"])
        row = loaded["bindings"].get(request.get("session_binding"))
        if row is None or row["host_id"] != agent_id or row["session_id"] != session:
            return "binding_scope_mismatch"
        access, reason = _bootstrap_access(root, request, resolved_data_root)
        return reason if access is None else None

    try:
        if resolved_data_root is None:
            resolved_data_root = default_data_root()
        if host not in _NATIVE_EVENTS or event not in _NATIVE_EVENTS[host]:
            return b"{}\n"
        if len(payload) > NATIVE_PAYLOAD_BYTES:
            raise ValueError("event_too_large")
        parsed = json.loads(payload.decode("utf-8"), object_pairs_hook=_native_pairs)
        if not isinstance(parsed, dict):
            raise TypeError("invalid_event")
        if host == "antigravity":
            session_candidate = parsed.get("conversationId")
            workspaces = parsed.get("workspacePaths")
            counter = "invocationNum" if event == "PreInvocation" else "stepIdx"
            if event != "Stop" and (
                type(parsed.get(counter)) is not int or parsed[counter] < 0
            ):
                raise ValueError("invalid_event")
            if event == "Stop" and (
                type(parsed.get("fullyIdle")) is not bool
                or not isinstance(parsed.get("terminationReason"), str)
                or type(parsed.get("executionNum")) is not int
                or parsed["executionNum"] < 0
            ):
                raise ValueError("invalid_event")
        else:
            session_candidate = parsed.get("conversation_id", parsed.get("session_id"))
            workspaces = (
                parsed.get("workspace_roots")
                if host == "cursor"
                else [parsed.get("cwd")]
            )
            if parsed.get("hook_event_name") != event:
                raise ValueError("event_mismatch")
            if event == "SessionStart" and parsed.get("source") not in (
                "startup",
                "clear",
                "compact",
            ):
                raise ValueError("invalid_source")
        if (
            not isinstance(session_candidate, str)
            or not session_candidate
            or len(session_candidate.encode("utf-8")) > 512
            or "\x00" in session_candidate
        ):
            raise ValueError("invalid_session")
        session = session_candidate
        if (
            not isinstance(workspaces, list)
            or not workspaces
            or any(
                not isinstance(p, str) or "\x00" in p or not Path(p).is_absolute()
                for p in workspaces
            )
        ):
            raise ValueError("invalid_workspace")
        roots = {str(Path(p).resolve()) for p in workspaces}
        registered = _registered_roots(resolved_data_root) or {}
        activations = _records(read_activation_record(resolved_data_root)) or []
        selected = [
            r
            for r in activations
            if _valid_record(r)
            and r["host"] == host
            and r["canonical_root"] in roots
            and registered.get(r["project_id"]) == r["canonical_root"]
        ]
        if len(selected) != 1:
            output = unavailable(
                "ambiguous_workspace" if len(selected) > 1 else "activation_required"
            )
        else:
            activation = selected[0]
            root = Path(activation["canonical_root"])
            entries = agents.read_agent_memory_state_strict(
                project_root=root, data_root=resolved_data_root
            )
            readiness = (entries or {}).get(f"{session}::{agent_id}")
            if (
                not isinstance(readiness, dict)
                or readiness.get("consent") is not True
                or readiness.get("connected") is not True
            ):
                output = unavailable("connection_consent_required")
            else:
                prior = readiness.get("last_observation")
                prior = prior if isinstance(prior, dict) else {}
                candidate = prior.get("bootstrap_request")
                capture = False
                if event in ("PostToolUse", "postToolUse"):
                    tool = (
                        parsed.get("toolCall")
                        if host == "antigravity"
                        else {
                            "name": parsed.get("tool_name"),
                            "args": parsed.get("tool_input"),
                        }
                    )
                    if (
                        not isinstance(tool, dict)
                        or not isinstance(tool.get("name"), str)
                        or not isinstance(tool.get("args"), dict)
                    ):
                        raise ValueError("invalid_tool_event")
                    args = tool["args"]
                    if (
                        tool["name"] in ("rush_memory", "mcp__rush__rush_memory")
                        and args.get("operation") == "bootstrap"
                    ):
                        if parsed.get("error"):
                            raise ValueError("failed_bootstrap_event")
                        candidate = args.get("request")
                        capture = True
                if candidate is None:
                    output = unavailable("bootstrap_required")
                else:
                    request = _validate_bootstrap_request(candidate)
                    reason = binding_reason()
                    if reason is not None:
                        output = unavailable(reason)
                    else:

                        def packet(value: Any) -> bytes:
                            text = compact.canonical_json(value).decode("utf-8")
                            return (
                                compact.canonical_json(
                                    _native_protocol(host, event, text)
                                )
                                + b"\n"
                            )

                        frame = compact.FrameContext(
                            "in_process", None, emit=packet, pending_memory_events=[]
                        )
                        with compact.memory_frame(frame):
                            result = MemoryTool()._bootstrap(
                                time.monotonic(),
                                root,
                                request,
                                frame=frame,
                                data_root=resolved_data_root,
                            )
                        output = packet(result)
                        if (
                            event in ("Stop", "stop", "PreCompact", "preCompact")
                            and result["raw"]["code"] == "OK"
                        ):
                            if not activation["recovery_cache_write"]:
                                _diagnose(
                                    "native checkpoint unavailable: cache_write_required"
                                )
                            else:
                                with (
                                    agents._ledger_lock(resolved_data_root),
                                    auth.hold_policy_lock(data_root=resolved_data_root),
                                ):
                                    reason = binding_reason()
                                    if reason is None:
                                        current = (
                                            _records(
                                                read_activation_record(
                                                    resolved_data_root
                                                )
                                            )
                                            or []
                                        )
                                        if not any(
                                            _valid_record(record)
                                            and record["host"] == host
                                            and record["canonical_root"] == str(root)
                                            and record["recovery_cache_write"]
                                            for record in current
                                        ):
                                            reason = "cache_write_required"
                                    capture_result = (
                                        {"code": "E_PERMISSION", "reason": reason}
                                        if reason is not None
                                        else _native_checkpoint(
                                            root,
                                            request,
                                            host,
                                            session,
                                            event,
                                            parsed,
                                            resolved_data_root,
                                        )
                                    )
                                _diagnose(
                                    "native checkpoint "
                                    + compact.canonical_json(capture_result).decode(
                                        "utf-8"
                                    )
                                )
                                if capture_result["code"] != "OK":
                                    _diagnose(
                                        "Use rush_memory operation=write with schema_version=2, subject=episodic, complete actual checkpoint content and source; preview before explicitly approved apply."
                                    )
                        if capture and result["raw"]["code"] == "OK":
                            if not activation["recovery_cache_write"]:
                                _diagnose(
                                    "native bootstrap capture disabled: cache-write consent required"
                                )
                            else:
                                # Same policy lock as grant writers; recheck before consented CAS.
                                with auth._locked(resolved_data_root):
                                    reason = binding_reason()
                                    if reason is not None:
                                        output = unavailable(reason)
                                    elif prior.get("bootstrap_request") != request:
                                        agents.record_tool_observation(
                                            agent_id,
                                            session,
                                            {
                                                "kind": "rush_bootstrap",
                                                "bootstrap_request": request,
                                            },
                                            project_root=root,
                                            data_root=resolved_data_root,
                                        )
        if root is not None and request is not None:
            reason = binding_reason()
            if reason is not None:
                output = unavailable(reason)
        if emit is not None:
            try:
                emitting = True
                emit(output)
            except BaseException:
                if frame is not None:
                    compact.discard_memory_events(frame)
                raise
            if frame is not None:
                compact.finalize_memory_events(
                    frame,
                    output,
                    accepted=compact.accepted_memory_result(result),
                    outcome=compact.memory_delivery_outcome(result),
                )
        return output
    except (OSError, ValueError, TypeError, KeyError, DataRootUnavailableError) as exc:
        _diagnose(f"native hook refused ({type(exc).__name__})")
        if frame is not None:
            compact.discard_memory_events(frame)
        if emitting:
            return b""
        output = unavailable("invalid_event")
        if emit is not None:
            try:
                emit(output)
            except OSError:
                return b""
        return output


def _run_check(scope: _Scope, invocation_id: str, started: float) -> str:
    from rush.delivery import compact
    from rush.permissions import ExecutionPermissions
    from rush.tools.check import CheckTool

    def past_deadline() -> bool:
        return time.monotonic() - started >= DEADLINE_SECONDS

    with _children_marked():
        result = dict(
            CheckTool().run(
                scope.target,
                permissions=ExecutionPermissions(),  # no inherited grants
                cancel_check=past_deadline,
                cancel_cause="hook_deadline",
                owner_instance_id=f"hook-{invocation_id}",
                run_id=invocation_id,
                original_requested_targets=scope.originals,
                invocation_start_cwd=scope.cwd,
            )
        )
    handle: str | None = None
    store_error: str | None = None
    if scope.recovery_cache_write:
        # Consented at enable time: store the full redacted result (T16).
        delivered = compact.deliver(
            "check",
            compact.ViewOptions(result_view="compact"),
            cache_write=True,
            prepare=lambda: (scope.root, lambda: result),
            serialize=compact.cli_size,
        )
        delivery = (dict(delivered).get("metadata") or {}).get("delivery") or {}
        handle = delivery.get("result_handle")
        if not handle:
            store_error = "the full result could not be stored"
    return _fit(_Report(result, scope, invocation_id, handle, store_error))


# --- Bounded rendering ------------------------------------------------------


class _Report:
    def __init__(
        self,
        result: dict[str, Any],
        scope: _Scope,
        invocation_id: str,
        handle: str | None,
        store_error: str | None,
    ) -> None:
        from rush.safety.redactor import sanitize_value

        self.result: dict[str, Any] = sanitize_value(result).value
        self.scope = scope
        self.invocation_id = invocation_id
        self.handle = handle
        self.store_error = store_error


def _full_command(root: Path) -> str:
    return f"rush check {shlex.quote(str(root))} --json"


def _one_line(value: Any, limit: int) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _finding_line(finding: dict[str, Any], root: Path) -> str:
    path = str(finding.get("path") or "")
    if path and Path(path).is_absolute() and Path(path).is_relative_to(root):
        path = Path(path).relative_to(root).as_posix()
    if finding.get("line") is not None:
        path = f"{path}:{finding['line']}"
    parts = [
        path,
        str(finding.get("rule") or finding.get("rule_id") or "-"),
        f"[{finding.get('severity') or 'info'}]",
        _one_line(finding.get("message") or "", _MESSAGE_CHARS),
    ]
    return "- " + " ".join(part for part in parts if part)


def _fixed_lines(report: _Report) -> tuple[list[str], list[str]]:
    """The fixed fields, and every finding line in display order."""
    from rush.tools.routing import aggregate_status
    from rush.workflows.suites import CHECK_SUITE

    result = report.result
    metadata = result.get("metadata") or {}
    children = metadata.get("children") or []
    by_tool = {c.get("tool"): c for c in children if isinstance(c, dict)}
    steps: list[str] = []
    incomplete = 0
    for name in CHECK_SUITE.tool_sequence:
        child = by_tool.get(name)
        if child is None:
            steps.append(f"  {name}: not reported")
            incomplete += 1
            continue
        execution = child.get("execution") or {}
        disposition = execution.get("disposition") or "executed"
        line = f"  {name}: {child.get('status')}"
        if disposition != "executed":
            incomplete += 1
            line += f" ({disposition}: {execution.get('cause') or 'unknown'})"
        if child.get("summary"):
            line += f" -- {_one_line(child['summary'], 160)}"
        steps.append(line)
    status = str(result.get("status") or "error")
    if incomplete or metadata.get("cancelled"):
        status = aggregate_status([status, "warn"])  # never clean when incomplete
    overall = f"overall: {status}"
    if incomplete:
        overall += (
            f"; incomplete: {incomplete} of {len(CHECK_SUITE.tool_sequence)} "
            "steps did not run"
        )
    lines = [
        f"Rush post-edit check (invocation {report.invocation_id})",
        f"scope: {report.scope.description}",
        overall,
        "steps:",
        *steps,
    ]
    lines.extend(
        f"excluded edited path (outside the project or via a symlink): {raw}"
        for raw in report.scope.excluded
    )
    if report.handle:
        lines.append(
            f"full result: result_handle {report.handle} -- "
            f'rush_status(operation="result", result_handle="{report.handle}") or '
            f"rush status {shlex.quote(str(report.scope.root))} "
            f"--result {report.handle} --json"
        )
    else:
        if report.store_error:
            lines.append(f"recovery: {report.store_error}")
        lines.append(f"full result: {_full_command(report.scope.root)}")
    findings = [f for f in result.get("findings") or [] if isinstance(f, dict)]
    findings.sort(key=lambda f: _SEVERITY_RANK.get(str(f.get("severity")), 2))
    return lines, [_finding_line(f, report.scope.root) for f in findings]


def _envelope(text: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": text,
            }
        },
        ensure_ascii=True,  # stdout encoding can never fail the hook
    )


def _fits(text: str) -> bool:
    # +1: the newline `click.echo` appends.
    return len(_envelope(text).encode("utf-8")) + 1 <= MAX_OUTPUT_BYTES


def _fit(report: _Report) -> str:
    """Fixed fields first, then findings while the next one still fits,
    with the shown-of-total count. Fixed fields alone too large -> a bounded
    error text, never a clean-looking truncation."""
    fixed, finding_lines = _fixed_lines(report)
    total = len(finding_lines)

    def build(count: int) -> str:
        if not total:
            return "\n".join([*fixed, "findings: none"])
        return "\n".join(
            [*fixed, f"findings (shown {count} of {total}):", *finding_lines[:count]]
        )

    if not _fits(build(0)):
        return _bounded_error(
            report.invocation_id,
            report.scope,
            f"the report exceeds the {MAX_OUTPUT_BYTES}-byte hook budget "
            f"(overall status {report.result.get('status')})",
        )
    shown = 0
    while shown < total and _fits(build(shown + 1)):
        shown += 1
    return build(shown)


def _bounded_error(invocation_id: str, scope: _Scope, detail: str) -> str:
    from rush.safety.redactor import sanitize_value

    text = str(
        sanitize_value(
            f"Rush post-edit check (invocation {invocation_id}) did not complete: "
            f"{_one_line(detail, 400)}. Full result: {_full_command(scope.root)}"
        ).value
    )
    if _fits(text):
        return text
    return (
        f"Rush post-edit check (invocation {invocation_id}) did not complete. "
        "Run `rush check --json` in the project."
    )


# --- Activation records (written by `rush agent connect`) --------------------


def _record_digest(record: Any) -> str:
    data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _document_bytes(records: list[Any]) -> bytes:
    text = json.dumps({"activations": records}, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _same_activation(record: Any, host: str, root: str) -> bool:
    return (
        isinstance(record, dict)
        and record.get("host") == host
        and record.get("canonical_root") == root
    )


def registered_project_id(project_root: Path, data_root: Path | None = None) -> str:
    """The registered project id of `project_root`'s canonical root.

    Raises ValueError when the registry is unusable or the root is not
    registered: an activation names a registered project."""
    root = str(Path(project_root).resolve())
    register = f"rush project add {shlex.quote(root)} --allow-cache-write --allow-artifact-write"
    roots = _registered_roots(data_root or default_data_root())
    if roots is None:
        raise ValueError(
            f"agent hooks need a readable project registry; register first: {register}"
        )
    for project_id, registered in roots.items():
        if registered == root:
            return project_id
    raise ValueError(f"agent hooks need a registered project; run: {register}")


def set_hook_activation(
    agent_id: str,
    project_root: Path,
    *,
    enable: bool,
    recovery_cache_write: bool = False,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Add (enable) or remove (disable) this host's activation for one project.

    One record per (host, canonical root) in the shared activations file,
    each recorded in the T3 ownership ledger (`kind="hook_activation"`) with
    the digest of the record Rush wrote. Disabling removes only a record
    still exactly as Rush wrote it; anything else is a reported conflict.
    """
    from rush.integrations import agents

    host = HOOK_AGENTS.get(agent_id)
    if host is None:
        raise ValueError(
            f"agent hooks are available for {', '.join(sorted(HOOK_AGENTS))} only"
        )
    root = Path(project_root).resolve()
    resolved_data_root = data_root or default_data_root()
    project_id = registered_project_id(root, resolved_data_root)
    path = activation_record_path(resolved_data_root)
    entry_id = f"{agent_id}:hook_activation:{path}:{root}"
    report: dict[str, Any] = {"host": host, "project_id": project_id, "path": str(path)}

    with agents._ledger_lock(resolved_data_root):
        ledger, version = agents._load_ledger(resolved_data_root)
        row = ledger.get(entry_id)
        if not enable:
            if row is None:
                return {**report, "state": "absent"}
            outcome = remove_activation(row)
            if isinstance(outcome, dict):
                return {**report, "state": "conflict", "conflict": outcome}
            del ledger[entry_id]
            agents._save_ledger(resolved_data_root, ledger, version)
            return {**report, "state": outcome}

        record = {
            "host": host,
            "project_id": project_id,
            "canonical_root": str(root),
            "recovery_cache_write": recovery_cache_write,
        }
        digest = _record_digest(record)
        try:
            current = agents._read_regular(path)
        except agents.CASConflictError as exc:
            return {**report, "state": "conflict", "conflict": exc.reason}
        records: list[Any] = []
        if current is not None:
            try:
                parsed = _records(json.loads(current))
            except ValueError:
                parsed = None
            if parsed is None:
                return {**report, "state": "conflict", "conflict": "unreadable"}
            records = parsed
        existing = [r for r in records if _same_activation(r, host, str(root))]
        owned = row.get("written_sha256") if row else None
        if existing and _record_digest(existing[0]) not in (digest, owned):
            return {**report, "state": "conflict", "conflict": "not_owned"}
        state = "unchanged"
        if not existing or _record_digest(existing[0]) != digest:
            kept = [r for r in records if not _same_activation(r, host, str(root))]
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                agents.cas_replace_file(
                    path,
                    _document_bytes([*kept, record]),
                    expected_sha256=agents._digest_or_none(current),
                )
            except agents.CASConflictError as exc:
                return {**report, "state": "conflict", "conflict": exc.reason}
            state = "applied"
        ledger[entry_id] = agents._ledger_entry(
            entry_id, "hook_activation", agent_id, root, str(path), digest, None
        )
        agents._save_ledger(resolved_data_root, ledger, version)
        return {**report, "state": state, "recovery_cache_write": recovery_cache_write}


def remove_activation(row: dict[str, Any]) -> str | dict[str, Any]:
    """Remove the activation one ledger row records (the caller holds the
    ledger lock): `removed`, `absent`, or a conflict row when the record is
    no longer exactly what Rush wrote."""
    from rush.integrations import agents

    path = Path(str(row.get("path")))
    host = HOOK_AGENTS.get(str(row.get("host")))
    root = row.get("project_root")
    written = row.get("written_sha256")
    current = agents._read_regular(path)
    if current is None or host is None or not isinstance(root, str):
        return "absent"
    actual = agents._sha256(current)
    try:
        records = _records(json.loads(current))
    except ValueError:
        records = None
    if records is None:
        return agents._conflict_row(
            "hook_activation", str(path), written, actual, "unreadable"
        )
    mine = [r for r in records if _same_activation(r, host, root)]
    if not mine:
        return "absent"
    if _record_digest(mine[0]) != written:
        return agents._conflict_row(
            "hook_activation", str(path), written, _record_digest(mine[0]), "changed"
        )
    remaining = [r for r in records if r is not mine[0]]
    if remaining:
        agents.cas_replace_file(
            path, _document_bytes(remaining), expected_sha256=actual
        )
    else:
        agents.cas_unlink(path, expected_sha256=actual)
    return "removed"


def deliver_continuation(
    root: Any,
    task_request: Any,
    native_state: Any,
    rush_binary: Any,
    expected_scope: Any,
    native_result: Any = None,
    approved_capsule: Any = None,
) -> dict[str, Any]:
    """Validate native-first delivery; only unavailable transports permit approved offline bytes."""
    import json
    import subprocess
    import unicodedata
    from pathlib import Path

    from pydantic import ValidationError

    from rush.delivery.compact import canonical_json
    from rush.memory.capsule import (
        _hex64,
        _Invalid,
        _strict_loads,
        _tokens,
        read_snapshot,
    )
    from rush.tools.memory import (
        _CODE_STATUS,
        _bootstrap_access,
        _validate_bootstrap_request,
    )

    def output(
        mode: str, channel: str | None, reason: str | None, data: Any = None
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "channel": channel,
            "reason": reason,
            "data": data or {},
            "recovery": {
                "reason": reason,
                "action": None
                if reason is None
                else "Review the recorded failure and retry the same approved route.",
            },
        }

    def decoded(result: Any, channel: str) -> dict[str, Any]:
        required = {
            "tool",
            "engine",
            "engine_version",
            "status",
            "duration_ms",
            "summary",
            "findings",
            "metadata",
            "raw",
        }
        if (
            not isinstance(result, dict)
            or not required.issubset(result)
            or result["engine"] is not None
            or result["engine_version"] is not None
            or type(result["duration_ms"]) is not int
            or result["duration_ms"] < 0
            or not isinstance(result["summary"], str)
            or not isinstance(result["findings"], list)
            or result["findings"] != []
            or not isinstance(result["metadata"], dict)
            or result["metadata"].get("operation") != "bootstrap"
        ):
            return output("unavailable", None, "invalid_result")
        raw = result.get("raw")
        if (
            result.get("tool") != "memory"
            or not isinstance(raw, dict)
            or set(raw) != {"schema_version", "operation", "code", "data"}
            or raw.get("schema_version") != 1
            or type(raw.get("schema_version")) is not int
            or raw.get("operation") != "bootstrap"
            or not isinstance(raw.get("code"), str)
            or raw.get("code") not in _CODE_STATUS
            or result.get("status") != _CODE_STATUS[raw["code"]]
            or not isinstance(raw.get("data"), dict)
        ):
            return output("unavailable", None, "invalid_result")
        code, data = raw["code"], raw["data"]
        if not isinstance(data.get("items"), list):
            return output("unavailable", None, "invalid_result")
        if code != "OK":
            if data["items"] or data.get("scope") is not None:
                return output("unavailable", None, "invalid_result")
            return output("unavailable", None, str(data.get("reason") or code))
        if (
            data.get("task_id") != request["task_id"]
            or data.get("task_kind") != request["task_kind"]
            or data.get("intent")
            != {
                "task_id": request["task_id"],
                "task_kind": request["task_kind"],
                "query": request["query"],
            }
            or data.get("progress_state")
            not in {
                "no_verified_checkpoint",
                "invalid_checkpoint",
                "checkpoint_available",
            }
            or not isinstance(data.get("next_action"), dict)
            or not isinstance(data["next_action"].get("text"), str)
            or not data["next_action"]["text"]
            or data.get("scope") != expected_scope
            or data.get("state") not in {"ready", "empty", "stale_only"}
            or type(data.get("complete")) is not bool
            or not (
                data.get("next_cursor") is None
                or isinstance(data.get("next_cursor"), str)
            )
            or (data["state"] in {"empty", "stale_only"} and data["items"])
            or (data["state"] == "ready" and not data["items"])
        ):
            return output("unavailable", None, "invalid_result")
        for item in data["items"]:
            if not isinstance(item, dict) or not isinstance(
                item.get("reference"), dict
            ):
                return output("unavailable", None, "invalid_result")
            ref = item["reference"]
            if (
                ref.get("project_id") != expected_scope["project_id"]
                or ref.get("worktree_id") != expected_scope["worktree_id"]
                or ref.get("owner_scope") != expected_scope["owner_scope"]
                or not isinstance(ref.get("artifact_id"), str)
                or type(ref.get("artifact_version")) is not int
                or ref["artifact_version"] < 1
                or not isinstance(ref.get("source"), str)
                or not _hex64(ref.get("payload_hash"))
                or (
                    item.get("content_hash") is not None
                    and not _hex64(item["content_hash"])
                )
            ):
                return output("unavailable", None, "invalid_result")
        return output("live", channel, None, data)

    def path(value: Any, *, directory: bool) -> Path:
        if not isinstance(value, (str, Path)):
            raise TypeError("path")
        text = str(value)
        text.encode("utf-8", "strict")
        if not text or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in text):
            raise ValueError("path")
        named = Path(text)
        if not named.is_absolute():
            raise ValueError("path")
        canonical = named.resolve(strict=True)
        if (directory and not canonical.is_dir()) or (
            not directory and not canonical.is_file()
        ):
            raise ValueError("path")
        return canonical

    try:
        request = _validate_bootstrap_request(task_request)
        root = path(root, directory=True)
        scope_fields = {
            "project_root",
            "project_id",
            "worktree_id",
            "owner_scope",
            "grant_id",
            "policy_revision",
            "session_binding",
        }
        if (
            not isinstance(expected_scope, dict)
            or set(expected_scope) != scope_fields
            or expected_scope["project_root"] != str(root)
            or not isinstance(expected_scope["owner_scope"], dict)
            or expected_scope["session_binding"] is None
            or (
                "session_binding" in request
                and request["session_binding"] != expected_scope["session_binding"]
            )
        ):
            raise ValueError("scope")
    except (ValidationError, TypeError, ValueError, UnicodeError, OSError):
        return output("unavailable", None, "invalid_bootstrap_request")

    from rush.memory.retrieval import DEFAULT_ENCODING, recall_admission

    limits = {"max_bytes": 65536, "max_tokens": request.get("max_tokens", 2048)}

    def budget_output(
        reason: str, required: dict[str, int], *, admission_failure: bool = False
    ) -> dict[str, Any]:
        refused = output("unavailable", None, reason)
        refused["recovery"]["action"] = {
            "kind": "approve_budget",
            "required": required,
            "limits": limits,
            "admission_failure": admission_failure,
            "code": "E_INPUT" if admission_failure else "E_BUDGET",
        }
        return refused

    def admission_frame(_code: str, _data: dict[str, Any]) -> bytes:
        result = budget_output(
            "budget_below_minimum", {"bytes": 2**63 - 1, "tokens": 2**63 - 1}
        )
        result["recovery"]["action"]["limits"] = {
            "max_tokens": max(2**63 - 1, limits["max_tokens"]),
            "max_bytes": 2**63 - 1,
        }
        return canonical_json(result)

    admission = recall_admission(
        limit=1,
        max_bytes=limits["max_bytes"],
        max_tokens=limits["max_tokens"],
        encoding=DEFAULT_ENCODING,
        frame_bytes=admission_frame,
    )
    if admission is not None:
        minimum = admission["required"]
        return budget_output(
            "budget_below_minimum",
            {"bytes": minimum["max_bytes"], "tokens": minimum["max_tokens"]},
            admission_failure=True,
        )

    def publish(result: dict[str, Any]) -> dict[str, Any]:
        rendered = canonical_json(result)
        required = {"bytes": len(rendered), "tokens": _tokens(rendered.decode("utf-8"))}
        if (
            required["bytes"] > limits["max_bytes"]
            or required["tokens"] > limits["max_tokens"]
        ):
            return budget_output(
                "snapshot_blocked"
                if result["mode"] == "offline_snapshot"
                else "continuation_blocked",
                required,
            )
        return result

    def active_scope() -> str | None:
        access, reason = _bootstrap_access(root, request)
        if access is None or access.owner_scope is None:
            return str(reason)
        actual = {
            "project_root": str(access.project_root),
            "project_id": access.project_id,
            "worktree_id": access.worktree_id,
            "owner_scope": access.owner_scope.as_dict(),
            "grant_id": access.grant_id,
            "policy_revision": access.policy_revision,
            "session_binding": access.session_binding,
        }
        return None if actual == expected_scope else "scope_changed"

    refusal = active_scope()
    if refusal is not None:
        return output("unavailable", None, refusal)
    if native_state == "not_attempted":
        result = output("unavailable", None, "native_bootstrap_required")
        result["recovery"]["action"] = {
            "tool": "rush_memory",
            "operation": "bootstrap",
            "request": request,
        }
        return publish(result)
    if native_state == "returned":
        projected = decoded(native_result, "managed_live")
        if projected["mode"] == "live":
            refusal = active_scope()
            if refusal is not None:
                return output("unavailable", None, refusal)
        return publish(projected)
    if native_state != "unavailable":
        return output("unavailable", None, "invalid_native_state")
    try:
        executable = path(rush_binary, directory=False)
    except FileNotFoundError:
        executable = None
    except (TypeError, ValueError, UnicodeError, OSError):
        return output("unavailable", None, "invalid_cli_path")
    argv = [
        str(executable),
        "memory",
        "bootstrap",
        "--project",
        str(root),
        "--task-id",
        request["task_id"],
        "--task-kind",
        request["task_kind"],
        "--query",
        request["query"],
        "--max-tokens",
        str(request.get("max_tokens", 2048)),
        "--json",
    ]
    if "session_binding" in request:
        argv += ["--session-binding", request["session_binding"]]
    try:
        if executable is None:
            raise FileNotFoundError("approved installed CLI unavailable")
        process = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if not isinstance(process.stdout, str):
            return output("unavailable", None, "invalid_result")
        result = _strict_loads(process.stdout.encode("utf-8", "strict"))
        projected = decoded(result, "cli_live")
        if projected["mode"] == "unavailable":
            return publish(projected)
        if process.returncode == 0:
            refusal = active_scope()
            if refusal is not None:
                return output("unavailable", None, refusal)
            return publish(projected)
        return output("unavailable", None, "cli_exit_mismatch")
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        reason = "cli_unavailable"
    except (UnicodeError, json.JSONDecodeError, _Invalid):
        return output("unavailable", None, "invalid_cli_result")
    if not isinstance(approved_capsule, dict) or set(approved_capsule) != {
        "path",
        "format",
        "digest",
    }:
        return output("unavailable", None, reason)
    snapshot = read_snapshot(
        root,
        approved_capsule["path"],
        approved_capsule["format"],
        approved_capsule["digest"],
        request.get("max_tokens", 2048),
    )
    if snapshot["code"] != "OK":
        return output(
            "unavailable", None, str(snapshot.get("reason") or snapshot["code"])
        )
    refusal = active_scope()
    if refusal is not None:
        return output("unavailable", None, refusal)
    snapshot["scope"] = dict(expected_scope)
    snapshot["task_id"], snapshot["task_kind"] = (
        request["task_id"],
        request["task_kind"],
    )
    snapshot["intent"] = {
        "task_id": request["task_id"],
        "task_kind": request["task_kind"],
        "query": request["query"],
    }
    return publish(output("offline_snapshot", "offline_capsule", None, snapshot))


__all__ = [
    "ACTIVE_ENV",
    "DEADLINE_SECONDS",
    "HOOK_AGENTS",
    "HOOK_HOSTS",
    "MAX_OUTPUT_BYTES",
    "MAX_PAYLOAD_BYTES",
    "activation_record_path",
    "deliver_continuation",
    "read_activation_record",
    "registered_project_id",
    "remove_activation",
    "run_agent_hook",
    "set_hook_activation",
]
