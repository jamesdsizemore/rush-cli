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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rush.setup.provision import DataRootUnavailableError, default_data_root

HOOK_HOSTS = ("claude", "codex")
#: Agent ids (`rush agent connect AGENT`) whose Rush plugin ships the hook.
HOOK_AGENTS = {"claude-code": "claude", "codex": "codex"}
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
    if host not in HOOK_HOSTS:
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


__all__ = [
    "ACTIVE_ENV",
    "DEADLINE_SECONDS",
    "HOOK_AGENTS",
    "HOOK_HOSTS",
    "MAX_OUTPUT_BYTES",
    "MAX_PAYLOAD_BYTES",
    "activation_record_path",
    "read_activation_record",
    "registered_project_id",
    "remove_activation",
    "run_agent_hook",
    "set_hook_activation",
]
