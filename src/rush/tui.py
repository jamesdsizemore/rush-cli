"""Persistent, colorful, animated Rich terminal UI (P66-03, F36).

Architecture §8, Phase 27; extended Phase 66 into a real persistent event
loop: a shared `TuiState`/`ProjectState` model, bounded POSIX/Windows key
handling (`rush.dashboard.terminal_input`), and direct wiring onto Phase 65's
shared scan/handoff actions (`rush.workflows.project_run`).

Every displayed key (`rush.dashboard.keymaps.DEFAULT_KEYBINDINGS`, plus this
module's own P66-05 memory-admin `_MEMORY_KEYBINDINGS` entry) has a real
handler below -- none are silently unimplemented. A canonical finding
`path`/`line` only ever drives a bounded local file read for context
(`_bounded_local_detail`); it never reaches a subprocess or shell. Terminal
state is restored on both a clean 'q' exit and any exception, because the
whole loop runs inside `terminal_input.raw_terminal()`, whose `finally`
always executes.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from rush import __version__
from rush.dashboard.keymaps import DEFAULT_KEYBINDINGS, KeybindingAction, KeymapManager
from rush.dashboard.state import AdmissionResult, MutationLedger
from rush.dashboard.terminal_input import KeyReader, make_key_reader, raw_terminal
from rush.dashboard.theme import THEME
from rush.permissions import ExecutionPermissions
from rush.runtime.subprocesses import (
    OWNED_TERMINATION_TIMEOUT_SECONDS,
    reap_owner_processes,
)
from rush.tools.base import ToolResult

PAGE_SIZE = 20
"""Generic paginated page size, reused for every output type (findings,
handoff previews) that has no dedicated terminal visualization."""

_DETAIL_CONTEXT_LINES = 4
_DETAIL_MAX_BYTES = 8192

# P66-05: memory-admin entry point. `keymaps.py` (owned by an earlier packet)
# is not part of this packet's allowed files, so the one new binding this
# packet needs is appended locally rather than editing that module's own
# DEFAULT_KEYBINDINGS list.
_MEMORY_KEYBINDINGS = [
    KeybindingAction(
        key="M",
        action_name="toggle_memory_admin",
        description="Memory admin: search/expand/promote/edit/delete",
    ),
]

# P66-06: Git history and every generated artifact view. Same rationale as
# _MEMORY_KEYBINDINGS above -- `keymaps.py` is not part of this packet's
# allowed files, so this one new binding is appended locally.
_GIT_KEYBINDINGS = [
    KeybindingAction(
        key="G",
        action_name="toggle_git_view",
        description="Git & artifacts: history, status, diff",
    ),
]
_KEYMAP = KeymapManager([*DEFAULT_KEYBINDINGS, *_MEMORY_KEYBINDINGS, *_GIT_KEYBINDINGS])

_TERMINAL_RUN_STATES = {
    "completed": "complete",
    "incomplete": "complete",
    "cancelled": "cancelled",
    "failed": "error",
}

# U01 fix: Tab/Shift+Tab cycle visible panes; F3 cycles Sections. Both are
# state-only concerns here -- `render_app`'s width branches (U04) decide
# which of these panes actually gets drawn at the current terminal size.
PANE_CYCLE: tuple[str, ...] = ("nav", "list", "detail")
SECTION_CYCLE: tuple[str, ...] = ("list", "map", "git")

# U04 fix: the smallest Rich style mapping from the shared THEME tokens
# (`rush.dashboard.theme`) -- replacing the hardcoded named colors
# ("cyan"/"red"/"yellow"/"grey50") the header, footer, and severity
# rendering used before. Never introduce a second theme/animation system;
# THEME is the sole source of these values (see that module's docstring).
_HEADER_STYLE = f"bold {THEME['blue']}"
_FOOTER_STYLE = THEME["surface_raised"]


def _severity_style(severity: str) -> str:
    if severity in ("error", "fail"):
        return THEME["error"]
    if severity == "warn":
        return THEME["warning"]
    return THEME["blue"]


def _width_branch(columns: int) -> str:
    """U04 fix: the exact Phase 66 §3.8 column breakpoints -- `render_app`
    branches its pane layout on this, replacing the prior single `>= 100`
    check that had no distinct 80-99/`< 80` behavior at all."""
    if columns >= 100:
        return "wide"
    if columns >= 80:
        return "compact"
    return "narrow"


# --------------------------------------------------------------------------
# Canonical field access -- Finding's schema key is `path` (tools/base.py),
# never `file`. Reading `file` silently produced an empty location for
# every real finding.
# --------------------------------------------------------------------------


def _finding_path(finding: Mapping[str, Any]) -> str:
    return str(finding.get("path") or "")


def _finding_line(finding: Mapping[str, Any]) -> str:
    line = finding.get("line")
    return str(line) if line is not None else ""


def paginate(
    items: list[Any], page: int, page_size: int = PAGE_SIZE
) -> tuple[list[Any], int]:
    """Generic paginated slice, reused for every detail/list view lacking a
    dedicated terminal visualization. Returns (page_items, total_pages)."""
    if not items:
        return [], 1
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return items[start : start + page_size], total_pages


def _bounded_local_detail(root: Path, finding: dict[str, Any]) -> str:
    """Canonical `path`/`line` drives ONLY a bounded local file read for
    context -- never a subprocess, shell, or arbitrary command. A path
    outside the project root, or any read failure, degrades to the
    finding's own message; no exception ever escapes this function."""
    path_value = _finding_path(finding)
    if not path_value:
        return str(finding.get("message") or "(no path)")
    try:
        target = (root / path_value).resolve()
        target.relative_to(root.resolve())
        raw = target.read_bytes()[:_DETAIL_MAX_BYTES]
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        line_no = finding.get("line")
        if isinstance(line_no, int) and lines:
            start = max(0, line_no - 1 - _DETAIL_CONTEXT_LINES)
            end = min(len(lines), line_no + _DETAIL_CONTEXT_LINES)
            return "\n".join(lines[start:end]) or str(finding.get("message") or "")
        return "\n".join(lines[: _DETAIL_CONTEXT_LINES * 2])
    except (OSError, ValueError):
        return str(finding.get("message") or "(unable to read local context)")


# --------------------------------------------------------------------------
# Static one-shot layout -- kept for `build_tui_layout`'s existing contract
# (Phase 27), fixed to read the canonical `path` field.
# --------------------------------------------------------------------------


def build_tui_layout(results: list[ToolResult]) -> Layout:
    """Construct a full-screen Rich Layout hierarchy for results exploration."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )

    header_text = Text("⚡ Rush Interactive Quality Explorer", style="bold cyan")
    layout["header"].update(Panel(header_text, style="cyan"))

    layout["main"].split_row(
        Layout(name="tree", ratio=1),
        Layout(name="details", ratio=2),
    )

    tree = Tree("📋 [bold]Evaluation Results[/bold]")
    for r in results:
        status_style = (
            "green"
            if r["status"] == "ok"
            else ("yellow" if r["status"] == "warn" else "red")
        )
        tool_branch = tree.add(
            f"[{status_style}]{r['tool']}[/{status_style}] ({r['status']})"
        )
        for f in (r.get("findings") or [])[:5]:
            tool_branch.add(
                f"[dim]{_finding_path(f)}:{_finding_line(f)}[/dim] - {f.get('message', '')}"
            )
    layout["tree"].update(Panel(tree, title="Tools", style="blue"))

    table = Table(expand=True)
    table.add_column("Tool", style="cyan", width=12)
    table.add_column("Path:Line", style="dim", width=24)
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Message", style="white")

    for r in results:
        for f in r.get("findings") or []:
            sev = f.get("severity", "info")
            sev_style = (
                "red" if sev == "error" else ("yellow" if sev == "warn" else "blue")
            )
            table.add_row(
                r["tool"],
                f"{_finding_path(f)}:{_finding_line(f)}",
                f"[{sev_style}]{sev}[/{sev_style}]",
                f.get("message", ""),
            )

    layout["details"].update(Panel(table, title="Finding Stream", style="green"))

    footer_text = Text(
        f"Press Ctrl+C or 'q' to exit | Rush v{__version__}", style="dim"
    )
    layout["footer"].update(Panel(footer_text, style="grey50"))

    return layout


# --------------------------------------------------------------------------
# Persistent interactive engine (P66-03)
# --------------------------------------------------------------------------


@dataclass
class ScanProgress:
    executed: int
    total: int
    status: str  # "running" | "complete" | "cancelled" | "error"

    @property
    def ratio(self) -> float:
        return 0.0 if self.total <= 0 else min(1.0, self.executed / self.total)


@dataclass
class ScanActions:
    """Injectable seam onto Phase65's shared workflow functions. Production
    callers get `default_scan_actions()`; tests inject fakes so the whole
    interactive loop is exercisable without a real project or filesystem."""

    plan_scan: Callable[..., Any]
    execute_scan: Callable[..., Any]
    cancel_scan_run: Callable[..., Any]
    rescan_project_run: Callable[..., Any]
    build_handoff: Callable[..., Any]
    dispatch_handoff: Callable[..., Any]
    load_scan_events: Callable[..., Any]
    list_agents: Callable[[], list[str]]
    # P66-05: trailing + defaulted so every pre-existing `ScanActions(...)`
    # call site (this packet's allowed files never include those tests)
    # keeps constructing without naming it.
    memory_run: Callable[..., Any] | None = None
    # P66-06: same trailing + defaulted contract as `memory_run` above.
    # `git_snapshot(project.root)` returns the real, registry-resolved
    # `project_snapshot()` (Git history/status + categorized artifacts) --
    # the same shared evidence view the dashboard's `section=git`/
    # `section=artifacts` HTTP endpoints render, so a commit/artifact ID
    # inspected in the TUI always matches the browser.
    git_snapshot: Callable[..., Any] | None = None
    # P69-06a: same trailing + defaulted contract as `memory_run` above.
    # `run_check_suite(root)` runs the initial `CHECK_SUITE` as the
    # background job `_start_initial_check_thread` attaches to at loop
    # startup, instead of `ui_cmd` blocking interface startup on it.
    run_check_suite: Callable[..., Any] | None = None
    # P69-06d: `dashboard_owner(root)` answers the one ownership question
    # every scan-triggering action asks at *start* time -- "is a dashboard
    # server live for this project right now?" -- returning that server's
    # dispatch handle, or None for local ownership. Production wires
    # `_find_live_dashboard_owner`; tests inject a fake.
    dashboard_owner: Callable[..., Any] | None = None


def default_scan_actions(
    permissions: ExecutionPermissions | None = None,
) -> ScanActions:
    from rush.tools.agent_connection import AgentConnectionTool
    from rush.tools.memory import MemoryTool
    from rush.workflows import project_run as pr
    from rush.workflows.projects import project_snapshot

    def _list_agents() -> list[str]:
        result = AgentConnectionTool().run(None, action="list")
        raw = result.get("raw") or {}
        agents = raw.get("agents") if isinstance(raw, dict) else []
        return [
            entry["agent_id"]
            for entry in (agents or [])
            if isinstance(entry, dict) and entry.get("agent_id")
        ]

    def _run_check_suite(
        root: Path,
        *,
        owner_instance_id: str = "",
        run_id: str = "",
        **kwargs: object,
    ) -> Any:
        from rush.workflows.suites import CHECK_SUITE, run_workflow_suite

        assert permissions is not None
        # P69-06f: this process's own identity travels into the suite, so
        # every subprocess it spawns is fenced under an owner recovery can
        # probe and Detach's force-exit can terminate.
        return run_workflow_suite(
            suite=CHECK_SUITE,
            path=root,
            permissions=permissions,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
        )

    return ScanActions(
        plan_scan=pr.plan_scan,
        execute_scan=pr.execute_scan,
        cancel_scan_run=pr.cancel_scan_run,
        rescan_project_run=pr.rescan_project_run,
        build_handoff=pr.build_handoff,
        dispatch_handoff=pr.dispatch_handoff,
        load_scan_events=pr.load_scan_events,
        list_agents=_list_agents,
        memory_run=MemoryTool().run,
        git_snapshot=project_snapshot,
        run_check_suite=_run_check_suite,
        dashboard_owner=_find_live_dashboard_owner,
    )


@dataclass
class ProjectSeed:
    """One project panel's starting point before the interactive loop
    starts: a name, its root, and any already-known results."""

    name: str
    root: Path
    results: list[ToolResult] = field(default_factory=list)


@dataclass
class ProjectState:
    name: str
    root: Path
    # M09: this project's registered canonical UUID, resolved once at load
    # time (`_resolve_registered_project_id`) -- `None` only for an explicit
    # project-not-found result, never for a registry read failure, so a
    # transient registry error can't silently fall back to path-form
    # ownership. Used by `_default_owner_scope_id`'s "project" branch instead
    # of the raw root path.
    project_id: str | None = None
    results: list[ToolResult] = field(default_factory=list)
    selected_index: int = 0
    filter_text: str = ""
    detail_page: int = 0
    run_id: str | None = None
    plan_total: int = 0
    progress: ScanProgress | None = None
    progress_history: list[ScanProgress] = field(default_factory=list)
    status: str = "idle"  # idle | scanning | cancelling | cancelled | complete | error
    # P69-06d: which process owns the run currently reflected here --
    # "dashboard" (a live server is the executor) or "local" (this TUI
    # process's own daemon thread). Decided at scan-*start* time and never
    # transferred mid-flight: the two processes share no memory, and no
    # handshake in this phase can move a live thread between them.
    owner: str = "local"
    last_message: str = ""
    scan_thread: threading.Thread | None = field(
        default=None, repr=False, compare=False
    )
    # P69-06g/h/i: the currently-admitted local run's own identity -- unset
    # (empty) whenever `owner != "local"` or no admission was made (best-
    # effort; see `_admit_local_run`). `operation_id` doubles as the
    # `MutationLedger` slot_id, matching the dashboard's own
    # `slot_id = operation_id` convention (`server.py`).
    owner_instance_id: str = ""
    operation_id: str = ""
    # True only once `_admit_local_run` durably registered `operation_id` in
    # the `MutationLedger` -- gates whether Detach's timeout/the worker's own
    # completion may write a ledger outcome at all. Subprocess-group reaping
    # (subsection h) never depends on this: it acts on `.procs` records keyed
    # by `owner_instance_id` alone, real for every local run.
    ledger_admitted: bool = False
    # P69-06i CAS guard: only the first of {the worker's own completion,
    # Detach's force-exit timeout} to observe an unresolved run may write its
    # terminal/`recovery_required` ledger outcome -- see `_resolve_local_run`.
    resolution_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )
    run_resolved: bool = True

    def flattened_findings(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in self.results:
            for finding in result.get("findings") or []:
                rows.append({"tool": result.get("tool"), **finding})
        return rows

    def visible_findings(self) -> list[dict[str, Any]]:
        rows = self.flattened_findings()
        needle = self.filter_text.strip().lower()
        if not needle:
            return rows
        return [
            row
            for row in rows
            if needle in _finding_path(row).lower()
            or needle in str(row.get("message", "")).lower()
            or needle in str(row.get("tool", "")).lower()
        ]


@dataclass
class TuiState:
    projects: list[ProjectState]
    active_index: int = 0
    mode: str = "list"  # list | search | detail | grant_review
    selected_agent_id: str | None = None
    agent_ids: list[str] = field(default_factory=list)
    pending_grant: dict[str, Any] | None = None
    message: str = ""
    should_quit: bool = False
    show_memory: bool = False
    terminal_size: tuple[int, int] = (80, 24)
    # P66-05: memory administration (mode == "memory"/"memory_search"/
    # "memory_edit"). `memory_subject` is fixed per admin session (switch by
    # restarting the loop with a different seed); `memory_query_buffer` also
    # doubles as the last-committed search text so a delete/edit/promote can
    # refresh the same result set afterward.
    memory_subject: str = "domain_knowledge"
    memory_query_buffer: str = ""
    memory_items: list[dict[str, Any]] = field(default_factory=list)
    memory_selected_index: int = 0
    memory_selected_ids: set[str] = field(default_factory=set)
    memory_pending_delete: dict[str, Any] | None = None
    memory_expanded: dict[str, Any] | None = None
    memory_edit_buffer: str | None = None
    memory_message: str = ""
    # P69-07 CONNECT: the owner every memory mutation this admin session makes is
    # attributed to (mode == "memory_owner" is the selector). `project`/`session`
    # kinds have a real derived default id (`_default_owner_scope_id`), so an empty
    # `memory_owner_scope_id` still produces a valid owner; `user`/`agent` kinds are
    # opaque caller-supplied strings and must be typed in.
    memory_owner_scope_kind: str = "project"
    memory_owner_scope_id: str = ""
    memory_owner_buffer: str | None = None
    # P66-06: Git history and every generated artifact (mode == "git").
    # `git_data` is the real `project_snapshot()` result loaded by
    # `_load_git_view` below -- reset on every project switch so a stale
    # project's history/status can never leak into the newly active one.
    git_data: dict[str, Any] | None = None
    git_message: str = ""
    # U01 fix: Tab/Shift+Tab's pane-cycle position (see `PANE_CYCLE`).
    active_pane: str = "list"
    # U01 fix: `mode == "project_selector"` overlay state -- the project
    # F2 currently highlights, distinct from `active_index` (which only
    # changes once the selector is confirmed with Enter).
    project_selector_index: int = 0
    # U01 fix: `mode == "map"` hierarchy state -- the set of expanded file
    # node keys and the selected row within the currently visible
    # (expand-aware) flattened node list. Never reset on resize (U04) or
    # re-entering Map via F3, so both survive either.
    map_expanded: set[str] = field(default_factory=set)
    map_selected_index: int = 0

    @property
    def active_project(self) -> ProjectState:
        return self.projects[self.active_index]

    def to_dict(self) -> dict[str, Any]:
        active = self.active_project
        return {
            "active_project": active.name,
            "active_index": self.active_index,
            "mode": self.mode,
            "selected_index": active.selected_index,
            "filter_text": active.filter_text,
            "run_id": active.run_id,
            "status": active.status,
            "message": self.message,
            "selected_agent_id": self.selected_agent_id,
            "terminal_size": list(self.terminal_size),
            "should_quit": self.should_quit,
            "progress_history": [
                {"executed": p.executed, "total": p.total, "status": p.status}
                for p in active.progress_history
            ],
        }


def _progress_from_events(
    payload: dict[str, Any], total_candidates: int
) -> ScanProgress:
    events = payload.get("events") or []
    executed = sum(
        1
        for e in events
        if isinstance(e, dict) and e.get("event") == "candidate_completed"
    )
    run_state = payload.get("run_state")
    status = _TERMINAL_RUN_STATES.get(str(run_state), "running")
    return ScanProgress(
        executed=executed, total=max(total_candidates, 1), status=status
    )


def _move_selection(project: ProjectState, delta: int) -> None:
    rows = project.visible_findings()
    if not rows:
        project.selected_index = 0
        return
    project.selected_index = max(0, min(len(rows) - 1, project.selected_index + delta))
    project.detail_page = project.selected_index // PAGE_SIZE


def _map_nodes(project: ProjectState) -> list[dict[str, Any]]:
    """U01 fix: the real Map hierarchy -- Project root -> one node per
    distinct finding path -> one leaf node per finding under that path.
    `key` is stable and drives expand/collapse + selection; `parent` gates
    a finding leaf's visibility on its file node's expanded state.

    ponytail: only the Files/Findings branches this module can source
    data for are built here -- the full §3.8 Map spec also names
    Directories/Memories/Agents branches, which would need data this
    packet's allowed files have no access to (the web dashboard's
    `project_map` machinery). Add those branches if/when that data
    becomes reachable from here; nothing about this shape blocks it."""
    rows = project.flattened_findings()
    by_path: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_path.setdefault(_finding_path(row), []).append(row)

    nodes: list[dict[str, Any]] = [
        {"key": "root", "label": project.name, "depth": 0, "kind": "project"}
    ]
    for path in sorted(by_path):
        findings = by_path[path]
        file_key = f"file:{path}"
        nodes.append(
            {
                "key": file_key,
                "label": f"{path} ({len(findings)})",
                "depth": 1,
                "kind": "file",
                "children": findings,
            }
        )
        for idx, finding in enumerate(findings):
            nodes.append(
                {
                    "key": f"{file_key}:finding:{idx}",
                    "label": str(finding.get("message", "")),
                    "depth": 2,
                    "kind": "finding",
                    "parent": file_key,
                }
            )
    return nodes


def _map_visible_nodes(
    project: ProjectState, expanded: set[str]
) -> list[dict[str, Any]]:
    """Only a finding leaf is ever hidden -- gated on its file node's key
    being in `expanded`. The root and file nodes are always visible."""
    return [
        node
        for node in _map_nodes(project)
        if node.get("parent") is None or node["parent"] in expanded
    ]


def _move_map_selection(state: TuiState, project: ProjectState, delta: int) -> None:
    nodes = _map_visible_nodes(project, state.map_expanded)
    if not nodes:
        state.map_selected_index = 0
        return
    state.map_selected_index = max(
        0, min(len(nodes) - 1, state.map_selected_index + delta)
    )


_OWNER_INSTANCE: list[str] = []
_OWNER_LOCK: list[Any] = []
"""S15: retains the acquired `OwnerLock` object itself (not merely its id),
so the underlying lock is never left as an unreferenced, easily-confused-
for-released value. `_OWNER_INSTANCE` alone is this pair's single source of
truth for "has a lock already been minted this process": pre-existing test
helpers reset local ownership between scenarios by clearing only
`_OWNER_INSTANCE` (matching this module's original single-list design), so
`_tui_owner_instance_id` must re-derive from that one list's emptiness
alone -- never gate on `_OWNER_LOCK` independently, or a reset that only
clears `_OWNER_INSTANCE` leaves `_OWNER_LOCK` stale and wrongly blocks the
very re-mint that reset was asking for.
"""


def _tui_owner_instance_id() -> str | None:
    """P69-01.2j/S15: this TUI process's own executor identity, minted once
    and backed by a real owner-liveness lock retained (not merely acquired
    and discarded) for the process's lifetime -- so recovery can tell "this
    owner is still working" from "this owner died and its engine children
    need reaping" (subsection h's contract).

    Returns `None` if the lifetime lock could not be acquired. A missing
    lock is never equivalent to permission to proceed: every caller must
    treat `None` as a hard stop for that local path -- reserve no work,
    launch no worker -- never silently continue unowned as this used to.

    Idempotent: once acquired, the lock is retained process-wide across
    every project this coordinator runs -- one project finishing must never
    release or re-attempt a lock another still-running local project needs.
    There is no per-project close; the lock is only ever released by the
    kernel at process exit.
    """
    if not _OWNER_INSTANCE:
        _OWNER_LOCK.clear()
        owner_instance_id = f"tui:{uuid.uuid4()}"
        from rush.dashboard.state import OwnerLock

        try:
            lock = OwnerLock(owner_instance_id)
        except Exception:  # noqa: BLE001 -- any acquisition failure (lock
            # already held, unreadable data root) is a hard stop for local
            # ownership, never a silently-swallowed no-op.
            return None
        _OWNER_INSTANCE.append(owner_instance_id)
        _OWNER_LOCK.append(lock)
    return _OWNER_INSTANCE[0] if _OWNER_INSTANCE else None


def _admit_local_run(
    project: ProjectState,
    *,
    owner_instance_id: str,
    run_id: str,
    execution_identity: str,
    plan_id: str,
) -> AdmissionResult | None:
    """P69-06i/S15: durably register this locally-owned run in the same
    `scan_admission`/`mutation_ledger` tables the dashboard's own
    `_admit_and_launch` uses, so recovery's existing generic dead-owner sweep
    (`reconcile_admissions`, `state.py` -- unmodified, out of this packet's
    file scope) finds a real row for this TUI process's own owner-instance
    lock, not nothing.

    A real `mutation_ledger` row (not just the `scan_admission` one) is what
    lets `record_status_transition`/`terminalize_and_release` -- and
    `prune_expired`'s TTL check -- actually apply to this run later; that row
    only exists with a caller-chosen `operation_id` via `ledger.reserve()`
    (the one public primitive that mints one), which is why `operation_id`
    here is that reservation's own id, distinct from `run_id`, and stored as
    `project.operation_id` for every later ledger write against this run --
    the dashboard's own `slot_id = operation_id` convention (`server.py`),
    reused as-is.

    Returns the durable `AdmissionResult` so the caller decides what happens
    next: `started=True` may launch a new local worker; `attached=True` must
    adopt the stored executor's identity and only observe it, never launch a
    second worker for the same admitted slot; `conflict=True` (or a `None`
    return, meaning admission itself raised) must display failure and
    reserve/launch nothing. A reservation/admission failure (a locked-out
    ledger, an unreadable data root) is reported as `None`, never silently
    treated as permission to proceed unowned.
    """
    project.owner_instance_id = owner_instance_id
    project.run_resolved = False
    project.ledger_admitted = False
    try:
        from rush.workflows.projects import resolve_project

        project_id = resolve_project(project.root)["project_id"]
        ledger = MutationLedger()
        reservation = ledger.reserve(
            project_id,
            request_id=f"tui-local:{run_id}",
            body_hash="",
            operation_type=execution_identity,
        )
        operation_id = reservation.operation_id
        project.operation_id = operation_id
        result = ledger.admit(
            project_id,
            execution_identity=execution_identity,
            slot_id=operation_id,
            operation_id=operation_id,
            run_id=run_id,
            plan_id=plan_id,
            owner_instance_id=owner_instance_id,
        )
        project.ledger_admitted = result.started
        return result
    except Exception:  # noqa: BLE001 -- a reservation/admission failure (a
        # locked-out ledger, an unreadable data root) leaves the run
        # unresolved for the caller to fail closed on, never silently
        # continue as admitted.
        project.run_resolved = True
        return None


def _resolve_local_run(project: ProjectState) -> bool:
    """P69-06i CAS guard: True only for the caller that wins the race to
    resolve this run -- the loser must not write a second, possibly
    contradictory, ledger outcome. Both racers (the worker thread's own
    completion, and Detach's force-exit timeout on the main thread) live in
    this one process for a locally-owned run, so an in-process lock is the
    real compare-and-swap here; `record_status_transition`'s own primitive
    (`state.py`) is an unconditional overwrite and adding a durable CAS
    primitive there is out of this packet's file scope."""
    with project.resolution_lock:
        if project.run_resolved:
            return False
        project.run_resolved = True
        return True


def _finalize_local_run(project: ProjectState, payload: dict[str, Any]) -> None:
    """The worker's own normal-completion path (success, error, or a
    cooperative-cancel acknowledgment) -- releases the admission slot and
    records a real terminal outcome. No-ops if Detach's force-exit timeout
    already won the CAS and marked `recovery_required` first."""
    if not project.operation_id or not _resolve_local_run(project):
        return
    with suppress(Exception):
        # `_admit_local_run` docstring. A failure here must never crash the
        # worker thread or surface as a scan failure to the user.
        MutationLedger().terminalize_and_release(
            project.operation_id,
            operation_id=project.operation_id,
            payload=payload,
        )


@dataclass(frozen=True)
class DashboardOwner:
    """P69-06d case (a): a dashboard server that is live for this project
    *right now*, and therefore the executor of any scan started from here on.

    Every dispatch crosses a real process boundary: `check_suite` through the
    private `X-Rush-Control` control command (P69-06e), the scan-lifecycle
    operations through that server's own HTTP action route. There is no
    same-process shortcut, because an internal server function called from
    this process would run here, against no `DashboardContext` at all."""

    base_url: str
    control_capability: str
    project_id: str
    # U02: a cached, already-exchanged (cookie, csrf) session, reused across
    # repeated status polls instead of bootstrapping on every call. Mutating
    # the dict's contents (never reassigning the field itself) is compatible
    # with this dataclass's `frozen=True`; excluded from repr/comparison so
    # two `DashboardOwner`s naming the same server still compare equal.
    _session_cache: dict[str, tuple[str, str]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def dispatch(self, operation: str, **arguments: Any) -> dict[str, Any]:
        from rush.dashboard.server import (
            dispatch_control_check_suite,
            dispatch_dashboard_action,
        )

        if operation == "check_suite":
            return dispatch_control_check_suite(
                self.base_url, self.control_capability, self.project_id
            )
        return dispatch_dashboard_action(
            self.base_url,
            self.control_capability,
            self.project_id,
            operation,
            arguments=arguments,
            # The dashboard executes the run, so the grants it needs to write
            # its own cache/artifacts are this dispatch's, not a fabrication:
            # these are the exact two `scan_start`/`rescan` require.
            grants={"cache_write": True, "artifact_write": True},
        )

    def operation_status(self, operation_id: str) -> dict[str, Any]:
        """U02: durable `GET .../operations/{operation_id}` status, reusing
        one cached authenticated session across repeated polls. On a 401
        (the cached session expired) re-exchanges exactly once and retries;
        a second failure is a visible disconnection, surfaced to the caller."""
        from urllib.error import HTTPError

        from rush.dashboard.server import (
            _control_session,
            dispatch_dashboard_operation_status,
        )

        session = self._session_cache.get("session")
        if session is None:
            session = _control_session(self.base_url, self.control_capability)
            self._session_cache["session"] = session
        try:
            return dispatch_dashboard_operation_status(
                self.base_url, self.project_id, operation_id, session=session
            )
        except HTTPError as exc:
            if exc.code != 401:
                raise
            session = _control_session(self.base_url, self.control_capability)
            self._session_cache["session"] = session
            return dispatch_dashboard_operation_status(
                self.base_url, self.project_id, operation_id, session=session
            )


def _find_live_dashboard_owner(root: Path) -> DashboardOwner | None:
    """P69-06d: the production ownership probe, using the identical
    descriptor + `/api/control/health` liveness mechanism
    `rush dashboard --reconnect` already uses (`_newest_dashboard_descriptor`
    returns a descriptor only after proving the recorded pid/start-nonce is
    still the process listening at that address).

    Returns None -- local ownership -- for any unreachable, unparseable, or
    unregistered case; a liveness probe that cannot prove a live server is
    never treated as one.
    """
    try:
        from rush.cli import _newest_dashboard_descriptor
        from rush.workflows.projects import resolve_project

        descriptor_path = _newest_dashboard_descriptor(None)
        if descriptor_path is None:
            return None
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        project_id = resolve_project(root)["project_id"]
    except Exception:  # noqa: BLE001 -- descriptor discovery is best-effort:
        # an unreadable descriptor, an unregistered project, or an
        # unreachable server all mean exactly one thing here (no live
        # dashboard owner), and none of them may break starting a scan.
        return None
    return DashboardOwner(
        base_url=f"http://{descriptor.get('bound_host')}:{descriptor.get('bound_port')}",
        control_capability=str(descriptor.get("control_capability", "")),
        project_id=project_id,
    )


def _dashboard_owner_for(project: ProjectState, actions: ScanActions) -> Any | None:
    """The single ownership decision every scan-triggering TUI action makes
    at its own start. One shared adapter, not three independent checks that
    can drift apart -- and re-asked per action, so a rescan after a
    dashboard-owned scan cannot silently fall back to local ownership."""
    finder = actions.dashboard_owner
    if finder is None:
        return None
    try:
        return finder(project.root)
    except Exception:  # noqa: BLE001 -- see `_find_live_dashboard_owner`:
        # failing to prove a live owner means local ownership, never a crash.
        return None


def _start_dashboard_owned(
    project: ProjectState,
    owner: Any,
    operation: str,
    arguments: dict[str, Any],
) -> None:
    """Hand one scan-triggering action to the live dashboard server that
    already owns this project, and observe it from here.

    The work is never TUI-owned for a moment, so Detach is trivially correct
    for this case: this process simply stops observing, and the dashboard's
    own durable status record is what a later `rush ui`/`rush dashboard`
    invocation reads to find the result."""
    project.owner = "dashboard"
    project.status = "scanning"
    project.progress = None
    project.progress_history = []
    project.operation_id = ""

    def _worker() -> None:
        try:
            response = owner.dispatch(operation, **arguments)
        except Exception as exc:  # noqa: BLE001 -- the dispatch crosses a
            # real network boundary into another process; its failure space
            # is unbounded. Surface it, and never silently re-run the work
            # locally: ownership is decided once, visibly.
            project.last_message = f"{operation} failed on dashboard: {exc}"
            project.status = "error"
            return
        run_id = response.get("run_id") if isinstance(response, dict) else None
        if isinstance(run_id, str) and run_id:
            project.run_id = run_id
        operation_id = (
            response.get("operation_id") if isinstance(response, dict) else None
        )
        if isinstance(operation_id, str) and operation_id:
            project.operation_id = operation_id
        # U02: completion is never inferred from `plan_total` (CHECK_SUITE
        # never has one) -- `_poll_running_scans`'s dashboard-owned branch
        # below is the only thing that ever moves this project out of
        # "scanning", by polling the retained `operation_id`'s real durable
        # status.
        project.last_message = (
            f"{operation} running in dashboard (operation {operation_id or '?'})"
        )

    thread = threading.Thread(target=_worker, daemon=True)
    project.scan_thread = thread
    thread.start()


def _start_scan_thread(project: ProjectState, actions: ScanActions) -> None:
    plan = actions.plan_scan(project.root)
    owner = _dashboard_owner_for(project, actions)
    if owner is not None:
        project.plan_total = len(list(getattr(plan, "candidates", None) or []))
        _start_dashboard_owned(
            project,
            owner,
            "scan_start",
            {"plan_id": getattr(plan, "plan_id", "")},
        )
        return

    owner_instance_id = _tui_owner_instance_id()
    if owner_instance_id is None:
        # S15: a lock that cannot be acquired is a hard stop, never
        # permission to reserve/launch unowned local work.
        project.owner = "local"
        project.status = "error"
        project.last_message = "scan_start refused: owner lifetime lock unavailable"
        return

    project.owner = "local"
    run_id = str(uuid.uuid4())
    project.run_id = run_id
    project.plan_total = len(list(getattr(plan, "candidates", None) or []))
    project.status = "scanning"
    project.progress = None
    project.progress_history = []
    admission = _admit_local_run(
        project,
        owner_instance_id=owner_instance_id,
        run_id=run_id,
        execution_identity=f"scan_start:{getattr(plan, 'plan_id', '')}",
        plan_id=str(getattr(plan, "plan_id", "")),
    )
    if admission is not None and admission.conflict:
        # S15: a genuinely-read, structured admission conflict -- another
        # executor already durably holds this project's slot. Display
        # failure, launch nothing, never incorrectly take over.
        project.status = "error"
        project.last_message = "scan_start refused: admission conflict"
        return
    if admission is not None and admission.attached:
        # S15: adopt the already-running executor's identity and observe
        # it -- never launch a second local worker for the same slot.
        project.run_id = admission.run_id or run_id
        project.operation_id = admission.operation_id or project.operation_id
        project.owner_instance_id = admission.owner_instance_id or owner_instance_id
        project.last_message = "scan_start attached to the already-running executor"
        return
    # `admission is None` means `_admit_local_run` itself raised (an
    # unreachable ledger, an unresolvable/unregistered project root) --
    # never a durably-read ownership decision. This is deliberately still
    # best-effort, matching the pre-S15 tolerance for reservation
    # infrastructure being unavailable: the scan still runs locally (just
    # unrecoverable if this process dies mid-run, same as before this
    # subsection existed). Only a lock failure (above) and a genuinely-read
    # conflict/attached result (above) are hard stops.

    def _worker() -> None:
        outcome_status = "success"
        try:
            run = actions.execute_scan(
                plan, run_id=run_id, owner_instance_id=owner_instance_id
            )
            aggregate = getattr(run, "aggregate", None)
            if aggregate is not None:
                # `actions.execute_scan` is `Callable[..., Any]` (injectable
                # seam); at runtime this is Phase65's real `ScanRun.aggregate`,
                # already a `ToolResult`-shaped dict -- the cast documents
                # that contract instead of erasing it with `dict(...)`.
                project.results = [cast(ToolResult, dict(aggregate))]
        except Exception as exc:  # noqa: BLE001 -- `actions.execute_scan` is an
            # injectable seam (real Phase65 workflow, or any test fake); this
            # background worker thread's only job is to surface whatever it
            # raises via `last_message` instead of dying silently or taking
            # the interactive loop down with it. The exception space is
            # genuinely unbounded by design (network, filesystem, arbitrary
            # tool errors, test-injected failures).
            project.last_message = f"scan error: {exc}"
            outcome_status = "error"
        finally:
            outcome = "cancelled" if project.status == "cancelling" else outcome_status
            _finalize_local_run(project, {"status": outcome})

    thread = threading.Thread(target=_worker, daemon=True)
    project.scan_thread = thread
    thread.start()


def _start_rescan_thread(project: ProjectState, actions: ScanActions) -> None:
    baseline_run_id = project.run_id
    owner = _dashboard_owner_for(project, actions)
    if owner is not None:
        # P69-06d: the identical check applies to every scan-triggering
        # action -- a rescan after a dashboard-owned scan must not silently
        # become locally owned mid-session.
        # `rescan`'s real argument name is `run_id` (the baseline run being
        # re-executed), per the server's own argument allowlist.
        _start_dashboard_owned(
            project, owner, "rescan", {"run_id": baseline_run_id or ""}
        )
        return

    owner_instance_id = _tui_owner_instance_id()
    if owner_instance_id is None:
        # S15: same hard stop as `_start_scan_thread` -- an unacquired
        # lifetime lock never means proceed unowned.
        project.owner = "local"
        project.status = "error"
        project.last_message = "rescan refused: owner lifetime lock unavailable"
        return

    project.owner = "local"
    project.status = "scanning"
    project.progress = None
    project.progress_history = []
    operation_id = str(uuid.uuid4())
    # P69-06h: tag this local run's owner identity even without a durable
    # admission row -- `reap_owner_processes` reads `.procs` by
    # `owner_instance_id` alone, so Detach's force-exit can still stop this
    # run's owned subprocess groups. Full ledger admission (recovery
    # reconciliation) is `_start_scan_thread`'s scope, not duplicated here.
    project.owner_instance_id = owner_instance_id
    project.operation_id = operation_id
    project.run_resolved = True
    project.ledger_admitted = False

    def _worker() -> None:
        try:
            outcome = actions.rescan_project_run(
                project.root, baseline_run_id, owner_instance_id=owner_instance_id
            )
            run = outcome.get("run") if isinstance(outcome, dict) else None
            if isinstance(run, dict):
                project.run_id = run.get("run_id", project.run_id)
                aggregate = run.get("aggregate")
                if isinstance(aggregate, dict):
                    # Same contract as `_start_scan_thread._worker`: this is
                    # Phase65's real `ScanRun.aggregate`, `ToolResult`-shaped
                    # at runtime.
                    project.results = [cast(ToolResult, aggregate)]
            project.status = "complete"
        except Exception as exc:  # noqa: BLE001 -- same contract as
            # `_start_scan_thread._worker` above: `actions.rescan_project_run`
            # is an injectable Phase65 seam whose failure space this
            # background thread cannot enumerate; surface it, never crash.
            project.last_message = f"rescan error: {exc}"
            project.status = "error"

    thread = threading.Thread(target=_worker, daemon=True)
    project.scan_thread = thread
    thread.start()


def _start_initial_check_thread(project: ProjectState, actions: ScanActions) -> None:
    """P69-06a: runs the initial `CHECK_SUITE` as a background job the
    interactive loop attaches to at startup, instead of `ui_cmd` blocking
    interface startup on it. Self-contained like `_start_rescan_thread`
    above -- the worker sets `project.status` itself on completion, since
    CHECK_SUITE doesn't go through the run_id/events-polling protocol
    `_poll_running_scans` understands.

    P69-06d/e: ownership is decided here too, by the same shared adapter. A
    live dashboard server runs the suite in its *own* process, reached
    through the private control command -- never a same-process call into a
    `DashboardContext` this process does not have. Otherwise it falls back to
    a local daemon thread carrying this process's own owner-instance lock id
    and run id, so the subprocesses it spawns stay fenced and reapable."""
    owner = _dashboard_owner_for(project, actions)
    if owner is not None:
        _start_dashboard_owned(project, owner, "check_suite", {})
        return

    owner_instance_id = _tui_owner_instance_id()
    if owner_instance_id is None:
        # S15: same hard stop as `_start_scan_thread` -- an unacquired
        # lifetime lock never means proceed unowned.
        project.owner = "local"
        project.status = "error"
        project.last_message = "initial check refused: owner lifetime lock unavailable"
        return

    project.owner = "local"
    project.status = "scanning"
    run_id = str(uuid.uuid4())
    # P69-06h: tag this local run's owner identity so Detach's force-exit can
    # still reap its owned subprocess groups (see `_start_rescan_thread`'s
    # identical comment -- ledger admission stays `_start_scan_thread`'s
    # scope, not duplicated here).
    project.owner_instance_id = owner_instance_id
    project.operation_id = run_id
    project.run_resolved = True
    project.ledger_admitted = False

    def _worker() -> None:
        try:
            res = (
                actions.run_check_suite(
                    project.root,
                    owner_instance_id=owner_instance_id,
                    run_id=run_id,
                )
                if actions.run_check_suite
                else None
            )
            if isinstance(res, dict):
                project.results = [cast(ToolResult, res)]
            project.status = "complete"
        except Exception as exc:  # noqa: BLE001 -- same contract as
            # `_start_rescan_thread._worker` above: `actions.run_check_suite`
            # is an injectable seam whose failure space this background
            # thread cannot enumerate; surface it, never crash the loop.
            project.last_message = f"initial check error: {exc}"
            project.status = "error"

    thread = threading.Thread(target=_worker, daemon=True)
    project.scan_thread = thread
    thread.start()


def _poll_dashboard_owned_scan(project: ProjectState, actions: ScanActions) -> None:
    """U02: the dashboard-owned counterpart to `_poll_running_scans`'s
    local-events polling below -- durable operation status through
    `DashboardOwner.operation_status`, never inferred from `plan_total`."""
    if not project.operation_id:
        return
    owner = _dashboard_owner_for(project, actions)
    if owner is None or not hasattr(owner, "operation_status"):
        return
    try:
        status_payload = owner.operation_status(project.operation_id)
    except Exception as exc:  # noqa: BLE001 -- a poll failure crosses a real
        # network boundary; surface it and retry next tick, never crash the
        # render loop.
        project.last_message = f"dashboard status poll failed: {exc}"
        return
    ledger_status = (
        status_payload.get("status") if isinstance(status_payload, dict) else None
    )
    if ledger_status != "terminal":
        return
    if project.scan_thread is not None:
        project.scan_thread.join(timeout=2.0)
    outcome_payload = (
        (status_payload.get("payload") or {})
        if isinstance(status_payload, dict)
        else {}
    )
    outcome = outcome_payload.get("status", "complete")
    project.status = "complete" if outcome == "success" else outcome
    run_id = outcome_payload.get("run_id")
    if isinstance(run_id, str) and run_id:
        project.run_id = run_id


def _poll_running_scans(state: TuiState, actions: ScanActions) -> None:
    for project in state.projects:
        if project.status not in ("scanning", "cancelling"):
            continue
        if project.owner == "dashboard":
            _poll_dashboard_owned_scan(project, actions)
            continue
        if project.run_id is None or project.plan_total <= 0:
            continue  # rescan-style thread reports its own terminal status directly
        try:
            payload = actions.load_scan_events(project.root, project.run_id)
        except Exception as exc:  # noqa: BLE001 -- injectable Phase65 seam;
            # a transient poll failure (e.g. the events file mid-write) must
            # not kill the render loop -- surface it and retry next tick
            # instead of silently swallowing it.
            project.last_message = f"progress poll failed: {exc}"
            continue
        progress = _progress_from_events(payload, project.plan_total)
        project.progress = progress
        project.progress_history.append(progress)
        if len(project.progress_history) > 500:
            del project.progress_history[:-500]
        if progress.status != "running":
            if project.scan_thread is not None:
                project.scan_thread.join(timeout=2.0)
            project.status = progress.status


def _cycle_agent(state: TuiState, actions: ScanActions) -> None:
    if not state.agent_ids:
        try:
            state.agent_ids = actions.list_agents()
        except Exception:  # noqa: BLE001 -- injectable Phase65/agent-tool
            # seam; falling back to "no agents discovered" (below) is the
            # correct user-facing outcome for any failure here, not a crash.
            state.agent_ids = []
    if not state.agent_ids:
        state.message = "no agents discovered"
        return
    if state.selected_agent_id not in state.agent_ids:
        state.selected_agent_id = state.agent_ids[0]
    else:
        idx = state.agent_ids.index(state.selected_agent_id)
        state.selected_agent_id = state.agent_ids[(idx + 1) % len(state.agent_ids)]


def _load_git_view(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """P66-06: load the real Git history/status + categorized artifacts for
    `project` (the same `project_snapshot()` the dashboard's `section=git`/
    `section=artifacts` HTTP endpoints render). A load failure surfaces via
    `state.git_message`, never a crash of the render loop -- same contract as
    `_start_scan_thread`'s worker-error handling above."""
    if actions.git_snapshot is None:
        state.git_data = None
        state.git_message = "git view unavailable"
        return
    try:
        state.git_data = actions.git_snapshot(project.root)
        state.git_message = ""
    except Exception as exc:  # noqa: BLE001 -- injectable Phase65/workflows
        # seam (`actions.git_snapshot`); a failed load must surface to the
        # user, never crash key dispatch or the render loop.
        state.git_data = None
        state.git_message = f"git view failed: {exc}"


def _handle_search_key(state: TuiState, key: str) -> None:
    project = state.active_project
    if key == "enter":
        state.mode = "list"
        return
    if key == "escape":
        project.filter_text = ""
        state.mode = "list"
        return
    if key == "backspace":
        project.filter_text = project.filter_text[:-1]
        return
    if len(key) == 1 and key.isprintable():
        project.filter_text += key
        project.selected_index = 0
        project.detail_page = 0


def _execute_grant(
    state: TuiState, grant: dict[str, Any], actions: ScanActions
) -> None:
    project = state.active_project
    kind = grant["kind"]
    try:
        if kind == "start_scan":
            _start_scan_thread(project, actions)
        elif kind == "rescan":
            _start_rescan_thread(project, actions)
        elif kind == "handoff":
            handoff = actions.build_handoff(
                project.root, grant["run_id"], grant["agent_id"], finding_ids=()
            )
            dispatched = actions.dispatch_handoff(
                project.root, handoff.handoff_id, handoff.session_capability
            )
            state.message = f"handoff {dispatched.state}"
    except Exception as exc:  # noqa: BLE001 -- the confirmed, user-approved
        # mutation itself calls injectable Phase65 actions (`build_handoff`/
        # `dispatch_handoff`/scan start/rescan); this is the single point
        # that turns any of their failures into a visible `state.message`
        # instead of crashing the interactive loop mid-render.
        state.message = f"{kind} failed: {exc}"
        project.status = "error"


# --------------------------------------------------------------------------
# P66-05: TUI memory administration (F38) -- direct, injectable dispatch onto
# `actions.memory_run` (production: `MemoryTool().run`, wired in
# `default_scan_actions()`). Every action below is a real call through that
# one canonical dispatch, never a hand-rolled store/SQLite write; a failure
# renders as `state.memory_message`, never a silently emptied list.
# --------------------------------------------------------------------------


def _memory_known_sources(project: ProjectState) -> list[str]:
    """Known useful sources only; see `_memory_sources_and_state`."""
    return _memory_sources_and_state(project)[0]


def _memory_sources_and_state(project: ProjectState) -> tuple[list[str], str | None]:
    """Every distinct `source` this project's memory store has ever recorded
    -- an admin session sees the whole project (mirrors the dashboard's own
    `_all_known_sources` in `server.py`), never a narrower cross-tool
    allowlist. Read-only: `TypedArtifactStore.list_artifact_refs()` is a
    public read method, never a raw SQLite write."""
    from rush.memory.store import TypedArtifactStore, is_internal_memory_source

    # R20.G8: a read-only view -- never creates or migrates `.rush/memory.db`.
    # An unreadable store returns its state (e.g. `migration_required`) so the
    # caller shows it instead of an empty list.
    store, state = TypedArtifactStore.open_readonly_view(project.root)
    if store is None:
        return [], state
    try:
        return sorted(
            {
                row["source"]
                for row in store.list_artifact_refs()
                if not is_internal_memory_source(row["source"])
            }
        ), None
    finally:
        store.close()


def _memory_refresh(
    state: TuiState,
    project: ProjectState,
    actions: ScanActions,
    *,
    announce: bool = True,
) -> None:
    """(Re-)runs the last-committed search text against `state.memory_subject`,
    scoped to every source this project's memory store has ever recorded.
    `announce=False` (used to refresh the list after a delete/edit already
    set its own outcome message) still updates `memory_items`/selection but
    never overwrites that outcome message with a generic result count."""
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    query = state.memory_query_buffer.strip()
    if not query:
        state.memory_message = "type a query, then Enter"
        return
    sources, store_state = _memory_sources_and_state(project)
    if store_state is not None:
        from rush.memory.store import readonly_view_reason

        state.memory_items = []
        state.memory_message = f"{store_state}: {readonly_view_reason(store_state)}"
        return
    if not sources:
        state.memory_items = []
        state.memory_message = "no memory recorded for this project yet"
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="list",
            subject=state.memory_subject,
            query=query,
            session_allowlist=sources,
        )
    except Exception as exc:  # noqa: BLE001 -- injectable Phase61/63 memory
        # seam; a failure must render as a retryable message, never crash the
        # interactive loop or silently empty the list.
        state.memory_message = f"memory search failed: {exc}"
        return
    if result.get("status") != "ok":
        state.memory_items = []
        state.memory_message = str(
            result.get("summary") or "memory search returned nothing"
        )
        return
    state.memory_items = list(result.get("raw") or [])
    state.memory_selected_index = 0
    state.memory_selected_ids = set()
    state.memory_pending_delete = None
    if announce:
        state.memory_message = f"{len(state.memory_items)} result(s)"


_MEMORY_OWNER_SCOPE_KINDS = ("project", "user", "session", "agent")


def _tui_session_owner_scope_id() -> str:
    """This standalone TUI invocation's `session`-kind owner id (P69-07 subsection b).

    A `rush ui` run with no dashboard server never creates a `DashboardAuth` session, so
    there is no browser session id to reuse. This process's own invocation identity
    (`_tui_owner_instance_id()`, minted once per process) is that identity: non-secret,
    already scoped to exactly this invocation, and never an authentication credential.
    """
    return _tui_owner_instance_id()


def _resolve_registered_project_id(root: Path) -> str | None:
    """M09: this root's registered canonical UUID, or `None` for an explicit
    project-not-found result. A registry read failure (any other exception)
    propagates rather than silently resolving to `None` -- that would look
    identical to "genuinely unregistered" and change ownership without
    telling the caller anything went wrong."""
    from rush.workflows.projects import ProjectNotFoundError, resolve_project

    try:
        return resolve_project(root)["project_id"]
    except ProjectNotFoundError:
        return None


def _default_owner_scope_id(kind: str, project: ProjectState) -> str:
    """The derived id for an owner kind that has one. `project` is this project's own
    registered canonical id (M09) when one was resolved at load time, falling back to
    the legacy root-path identity only for an unregistered project; `session` is this
    invocation's session id. `user`/`agent` are opaque and have no derivable default."""
    if kind == "project":
        return project.project_id or str(project.root)
    if kind == "session":
        return _tui_session_owner_scope_id()
    return ""


def _memory_owner_scope(state: TuiState, project: ProjectState) -> dict[str, str]:
    """The `owner_scope` payload every TUI memory mutation sends (P69-07 CONNECT)."""
    kind = state.memory_owner_scope_kind
    identifier = state.memory_owner_scope_id or _default_owner_scope_id(kind, project)
    return {"kind": kind, "id": identifier}


def _memory_selected_item(state: TuiState) -> dict[str, Any] | None:
    if not state.memory_items or state.memory_selected_index >= len(state.memory_items):
        return None
    return state.memory_items[state.memory_selected_index]


def _memory_expand_selected(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    item = _memory_selected_item(state)
    if item is None or actions.memory_run is None:
        state.memory_message = "no row selected"
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="expand",
            request={"id": item["id"], "version": item["artifact_version"]},
            session_allowlist=_memory_known_sources(project),
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"expand failed: {exc}"
        return
    raw = result.get("raw") or {}
    data = raw.get("data") if isinstance(raw, dict) else None
    state.memory_expanded = data
    state.memory_message = (
        "expanded" if data else str(raw.get("code", result.get("summary")))
    )


def _memory_promote_selected(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """Real `promote` dispatch on the selected row's own content/source
    (never a fabricated candidate) -- corroboration is evaluated by the
    canonical `evaluate_promotion` gate, so a lone source is correctly
    denied (`insufficient_corroboration`), matching the CLI/MCP behavior."""
    item = _memory_selected_item(state)
    if item is None or actions.memory_run is None:
        state.memory_message = "no row selected"
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="promote",
            subject=state.memory_subject,
            content=item.get("content") or {},
            source=item.get("source", ""),
            symbol_ref=item.get("symbol_ref"),
            source_kind="local_tool",
            user_stated=False,
            candidate_sources=[item.get("source", "")],
            owner_scope=_memory_owner_scope(state, project),
            permissions=ExecutionPermissions(cache_write=True),
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"promote failed: {exc}"
        return
    raw = result.get("raw") or {}
    if raw.get("promoted"):
        state.memory_message = f"promoted to {raw.get('new_tier')}"
    else:
        state.memory_message = f"promotion denied: {raw.get('denial_reason')}"


def _memory_delete_preview(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    if not state.memory_selected_ids:
        state.memory_message = "select at least one row (space) before delete"
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    ids = sorted(state.memory_selected_ids)
    revisions = {
        item["id"]: item["artifact_version"]
        for item in state.memory_items
        if item.get("id") in state.memory_selected_ids
    }
    owner_scope = _memory_owner_scope(state, project)
    try:
        result = actions.memory_run(
            project.root,
            operation="delete",
            request={
                "artifact_ids": ids,
                "expected_revisions": revisions,
                "scope": state.memory_subject,
                "owner_scope": owner_scope,
                "apply": False,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"delete preview failed: {exc}"
        return
    raw = result.get("raw") or {}
    data = raw.get("data") if isinstance(raw, dict) else {}
    state.memory_pending_delete = {
        "artifact_ids": ids,
        "expected_revisions": revisions,
        "scope": state.memory_subject,
        "owner_scope": owner_scope,
        "affected": (data or {}).get("affected", []),
    }
    state.memory_message = (
        f"preview: {len(ids)} record(s) selected -- [y] delete, [n]/[esc] cancel"
    )


def _memory_delete_apply(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    pending = state.memory_pending_delete
    if pending is None:
        return
    if actions.memory_run is None:
        state.memory_pending_delete = None
        state.memory_message = "memory operations unavailable"
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="delete",
            request={
                "artifact_ids": pending["artifact_ids"],
                "expected_revisions": pending["expected_revisions"],
                "scope": pending["scope"],
                # The exact owner the preview validated against, never re-derived:
                # a scope change between preview and apply must not silently widen
                # what the confirmed 'y' actually deletes.
                "owner_scope": pending["owner_scope"],
                "apply": True,
            },
            permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"delete failed: {exc}"
        state.memory_pending_delete = None
        return
    raw = result.get("raw") or {}
    data = raw.get("data") if isinstance(raw, dict) else {}
    deleted = len((data or {}).get("affected") or [])
    state.memory_pending_delete = None
    state.memory_selected_ids = set()
    state.memory_message = f"deleted {deleted} record(s)"
    _memory_refresh(state, project, actions, announce=False)


def _memory_edit_commit(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """ponytail: the keyboard editor commits one fixed `note` content field
    rather than a full structured-content form -- a real, testable single-
    field edit; upgrade to a multi-field form if admin content needs more
    than one editable field."""
    item = _memory_selected_item(state)
    if item is None or state.memory_edit_buffer is None or actions.memory_run is None:
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="edit",
            request={
                "scope": state.memory_subject,
                "id": item["id"],
                "expected_version": item["artifact_version"],
                "content": {
                    **(item.get("content") or {}),
                    "note": state.memory_edit_buffer,
                },
                "owner_scope": _memory_owner_scope(state, project),
                "apply": True,
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"edit failed: {exc}"
        state.memory_edit_buffer = None
        return
    raw = result.get("raw") or {}
    if raw.get("code") == "OK":
        state.memory_message = "edit applied"
        _memory_refresh(state, project, actions, announce=False)
    else:
        state.memory_message = f"edit denied: {raw.get('code')}"
    state.memory_edit_buffer = None


def _handle_memory_key(state: TuiState, key: str, actions: ScanActions) -> None:
    project = state.active_project
    if key == "escape":
        if state.memory_pending_delete is not None:
            state.memory_pending_delete = None
            state.memory_message = "delete cancelled -- 0 records removed"
        else:
            state.mode = "list"
            state.memory_message = ""
        return
    if key == "n" and state.memory_pending_delete is not None:
        state.memory_pending_delete = None
        state.memory_message = "delete cancelled -- 0 records removed"
        return
    if key in ("down", "j"):
        if state.memory_items:
            state.memory_selected_index = (state.memory_selected_index + 1) % len(
                state.memory_items
            )
        return
    if key in ("up", "k"):
        if state.memory_items:
            state.memory_selected_index = (state.memory_selected_index - 1) % len(
                state.memory_items
            )
        return
    if key == "/":
        state.mode = "memory_search"
        state.memory_query_buffer = ""
        return
    if key == " ":
        item = _memory_selected_item(state)
        item_id = item.get("id") if item is not None else None
        if isinstance(item_id, str):
            if item_id in state.memory_selected_ids:
                state.memory_selected_ids.discard(item_id)
            else:
                state.memory_selected_ids.add(item_id)
        return
    if key == "x":
        _memory_expand_selected(state, project, actions)
        return
    if key == "p":
        _memory_promote_selected(state, project, actions)
        return
    if key == "e":
        if _memory_selected_item(state) is not None:
            state.mode = "memory_edit"
            state.memory_edit_buffer = ""
        return
    if key == "o":
        state.mode = "memory_owner"
        state.memory_owner_buffer = state.memory_owner_scope_id or (
            _default_owner_scope_id(state.memory_owner_scope_kind, project)
        )
        return
    if key == "d":
        _memory_delete_preview(state, project, actions)
        return
    if key == "y":
        _memory_delete_apply(state, project, actions)
        return


def _handle_memory_search_key(state: TuiState, key: str, actions: ScanActions) -> None:
    if key == "enter":
        state.mode = "memory"
        _memory_refresh(state, state.active_project, actions)
        return
    if key == "escape":
        state.mode = "memory"
        return
    if key == "backspace":
        state.memory_query_buffer = state.memory_query_buffer[:-1]
        return
    if len(key) == 1 and key.isprintable():
        state.memory_query_buffer += key


def _handle_memory_owner_key(state: TuiState, key: str, actions: ScanActions) -> None:
    """P69-07 CONNECT: the full user/project/session/agent scope selector.

    `tab` cycles the kind (prefilling the derived id for the kinds that have one),
    printable characters edit the id, `enter` commits, `escape` discards -- the same
    buffer/commit/cancel shape the existing search and edit input modes already use.
    """
    del actions  # selection is pure state; nothing dispatches until a mutation runs
    if key == "escape":
        state.mode = "memory"
        state.memory_owner_buffer = None
        return
    if key == "tab":
        index = _MEMORY_OWNER_SCOPE_KINDS.index(state.memory_owner_scope_kind)
        next_kind = _MEMORY_OWNER_SCOPE_KINDS[
            (index + 1) % len(_MEMORY_OWNER_SCOPE_KINDS)
        ]
        state.memory_owner_scope_kind = next_kind
        state.memory_owner_buffer = _default_owner_scope_id(
            next_kind, state.active_project
        )
        return
    if key == "enter":
        identifier = (state.memory_owner_buffer or "").strip()
        if not identifier and state.memory_owner_scope_kind in ("user", "agent"):
            state.memory_message = (
                f"{state.memory_owner_scope_kind} scope needs an id -- type one"
            )
            return
        state.memory_owner_scope_id = identifier
        state.memory_owner_buffer = None
        state.mode = "memory"
        state.memory_message = (
            f"owner scope = {state.memory_owner_scope_kind}:"
            f"{_memory_owner_scope(state, state.active_project)['id']}"
        )
        return
    if key == "backspace":
        state.memory_owner_buffer = (state.memory_owner_buffer or "")[:-1]
        return
    if len(key) == 1 and key.isprintable():
        state.memory_owner_buffer = (state.memory_owner_buffer or "") + key


def _handle_memory_edit_key(state: TuiState, key: str, actions: ScanActions) -> None:
    if key == "escape":
        state.mode = "memory"
        state.memory_edit_buffer = None
        return
    if key == "enter":
        _memory_edit_commit(state, state.active_project, actions)
        state.mode = "memory"
        return
    if key == "backspace":
        state.memory_edit_buffer = (state.memory_edit_buffer or "")[:-1]
        return
    if len(key) == 1 and key.isprintable():
        state.memory_edit_buffer = (state.memory_edit_buffer or "") + key


def _has_running_work(project: ProjectState) -> bool:
    return project.status in ("scanning", "cancelling")


def _request_cancel(project: ProjectState, actions: ScanActions) -> None:
    """Send the cooperative-cancel marker for `project`'s active run.
    Shared by the plain 'cancel_scan' key and Cancel-run-and-stay (P69-06g) --
    both send the identical request; they differ only in what happens to the
    TUI process afterward."""
    if project.status != "scanning" or not project.run_id:
        return
    try:
        # Filesystem-based, so this is correct for a dashboard-owned run too
        # (both processes share the same project root) -- never routed
        # through the dashboard's own HTTP action for this local button.
        actions.cancel_scan_run(project.root, project.run_id)
        project.status = "cancelling"
    except Exception as exc:  # noqa: BLE001 -- injectable Phase65
        # seam (`cancel_scan_run`/dashboard dispatch); a failed cancel
        # request must surface to the user, never crash the key-dispatch
        # path.
        project.last_message = f"cancel failed: {exc}"


def _wait_for_cancel_ack(
    state: TuiState, project: ProjectState, actions: ScanActions, *, timeout: float
) -> bool:
    """P69-06g: blocks up to `timeout` seconds for the cooperative-cancel
    marker to be acknowledged (a real terminal status transition), polling
    the identical events protocol `_poll_running_scans` uses every render
    tick -- a self-reporting local worker (rescan/check_suite) needs no
    polling call at all, since it writes `project.status` itself and that
    write is visible across threads without one. Returns True the instant
    `project.status` leaves `"cancelling"`, False once `timeout` is
    exhausted with no acknowledgment observed."""
    deadline = time.monotonic() + timeout
    while True:
        _poll_running_scans(state, actions)
        if project.status != "cancelling":
            return True
        if time.monotonic() >= deadline:
            return project.status != "cancelling"
        time.sleep(0.05)


def _handle_detach(
    state: TuiState,
    project: ProjectState,
    actions: ScanActions,
    *,
    timeout: float = OWNED_TERMINATION_TIMEOUT_SECONDS,
) -> None:
    """P69-06g/h/i: Detach's two genuinely different behaviors per Phase 66
    S3.9's superseding clause (this plan's own S3) -- case (a) dashboard-owned
    is a trivial background continuation (the work was never TUI-owned);
    case (b) locally-owned is Cancel-with-saved-partial-result, since no
    mechanism this phase can build keeps a bare CLI process's work alive
    past its own exit."""
    if project.owner == "dashboard" or not project.owner_instance_id:
        state.mode = "list"
        state.should_quit = True
        return

    state.message = "detaching -- cancelling local run..."
    _request_cancel(project, actions)
    acknowledged = _wait_for_cancel_ack(state, project, actions, timeout=timeout)
    if not acknowledged:
        # The worker never acknowledged within the deadline: force-stop every
        # subprocess group *this run* owns (subsection h). U03: this
        # coordinator process can own more than one project's run at once,
        # so the `run_id` filter is required here -- owner-only filtering
        # would reap a sibling project's still-running subprocesses too.
        # Reaping acts on `.procs` records, real for every local run
        # regardless of ledger admission -- never assume termination
        # succeeded just because a signal was sent.
        reap_owner_processes(
            project.owner_instance_id, timeout=timeout, run_id=project.run_id
        )
        if project.ledger_admitted and _resolve_local_run(project):
            with suppress(Exception):
                # `_admit_local_run`/`_finalize_local_run`'s contract: this
                # process exits regardless of whether the ledger write lands.
                MutationLedger().record_status_transition(
                    project.operation_id,
                    "recovery_required",
                    {
                        "status": "recovery_required",
                        "code": "detach_force_exit_timeout",
                    },
                )
    state.mode = "list"
    state.should_quit = True


def _handle_cancel_and_stay(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """P69-06g: a distinct third choice from Detach -- the TUI process never
    exits. There is no timeout: a late worker acknowledgment, however late,
    still lands as a genuine terminal transition the still-open TUI displays
    on a later render tick's `_poll_running_scans` call, never lost to a
    force-exit that does not apply to this choice."""
    _request_cancel(project, actions)
    state.mode = "list"
    state.message = "cancelling -- run continues to be observed"


def _handle_quit_confirm_key(state: TuiState, key: str, actions: ScanActions) -> None:
    project = state.active_project
    if key in ("d", "enter"):
        _handle_detach(state, project, actions)
    elif key == "c":
        _handle_cancel_and_stay(state, project, actions)
    elif key in ("r", "n", "escape"):
        state.mode = "list"
        state.message = "quit cancelled -- still observing"
    # any other key: stay in the menu, awaiting a valid choice.


def _handle_project_selector_key(state: TuiState, key: str) -> None:
    """U01 fix: F2's overlay -- Up/Down/j/k move the highlight, Enter
    confirms the actual project switch (the only place `active_index`
    changes here), Escape cancels back to `list` with no switch at all."""
    if key in ("down", "j"):
        state.project_selector_index = (state.project_selector_index + 1) % len(
            state.projects
        )
    elif key in ("up", "k"):
        state.project_selector_index = (state.project_selector_index - 1) % len(
            state.projects
        )
    elif key == "enter":
        state.active_index = state.project_selector_index
        # P66-05/P66-06: same two-project isolation guarantee the old
        # `next_project` action gave -- a prior project's memory-admin/git
        # state never leaks into the newly active one.
        state.memory_items = []
        state.memory_selected_ids = set()
        state.memory_pending_delete = None
        state.memory_expanded = None
        state.memory_message = ""
        state.git_data = None
        state.git_message = ""
        state.mode = "list"
    elif key == "escape":
        state.mode = "list"


def _handle_grant_review_key(state: TuiState, key: str, actions: ScanActions) -> None:
    grant = state.pending_grant
    state.pending_grant = None
    state.mode = "list"
    if key == "y" and grant is not None:
        _execute_grant(state, grant, actions)
    else:
        state.message = "declined"


def _dispatch_key(state: TuiState, key: str, actions: ScanActions) -> None:
    if state.mode == "search":
        _handle_search_key(state, key)
        return
    if state.mode == "grant_review":
        _handle_grant_review_key(state, key, actions)
        return
    if state.mode == "memory_search":
        _handle_memory_search_key(state, key, actions)
        return
    if state.mode == "memory_edit":
        _handle_memory_edit_key(state, key, actions)
        return
    if state.mode == "memory_owner":
        _handle_memory_owner_key(state, key, actions)
        return
    if state.mode == "memory":
        _handle_memory_key(state, key, actions)
        return
    if state.mode == "quit_confirm":
        _handle_quit_confirm_key(state, key, actions)
        return
    if state.mode == "project_selector":
        _handle_project_selector_key(state, key)
        return

    action = _KEYMAP.get_action_for_key(key)
    if action is None:
        return
    project = state.active_project

    if action == "quit":
        # P69-06g: Phase 66 S3.9 -- quitting with running work offers a
        # real three-way choice (Detach/Cancel run and stay/Return), never
        # an immediate exit that silently loses or orphans that work.
        if _has_running_work(project):
            state.mode = "quit_confirm"
            state.message = ""
        else:
            state.should_quit = True
    elif action == "cursor_down":
        if state.mode == "map":
            _move_map_selection(state, project, 1)
        else:
            _move_selection(project, 1)
    elif action == "cursor_up":
        if state.mode == "map":
            _move_map_selection(state, project, -1)
        else:
            _move_selection(project, -1)
    elif action == "select_row":
        if project.visible_findings():
            state.mode = "detail"
    elif action == "open_project_selector":
        # U01 fix: opens the overlay -- the project only actually switches
        # once Enter confirms a highlighted row (`_handle_project_selector_
        # key`), distinct from Tab's `cycle_pane` (never switches projects).
        state.project_selector_index = state.active_index
        state.mode = "project_selector"
    elif action == "cycle_pane":
        idx = (
            PANE_CYCLE.index(state.active_pane)
            if state.active_pane in PANE_CYCLE
            else 0
        )
        state.active_pane = PANE_CYCLE[(idx + 1) % len(PANE_CYCLE)]
    elif action == "cycle_pane_reverse":
        idx = (
            PANE_CYCLE.index(state.active_pane)
            if state.active_pane in PANE_CYCLE
            else 0
        )
        state.active_pane = PANE_CYCLE[(idx - 1) % len(PANE_CYCLE)]
    elif action == "next_section":
        current = state.mode if state.mode in SECTION_CYCLE else "list"
        idx = SECTION_CYCLE.index(current)
        state.mode = SECTION_CYCLE[(idx + 1) % len(SECTION_CYCLE)]
        if state.mode == "git":
            _load_git_view(state, project, actions)
    elif action == "map_expand":
        if state.mode == "map":
            nodes = _map_visible_nodes(project, state.map_expanded)
            if 0 <= state.map_selected_index < len(nodes):
                node = nodes[state.map_selected_index]
                if node.get("children"):
                    state.map_expanded.add(node["key"])
    elif action == "map_collapse":
        if state.mode == "map":
            nodes = _map_visible_nodes(project, state.map_expanded)
            if 0 <= state.map_selected_index < len(nodes):
                node = nodes[state.map_selected_index]
                state.map_expanded.discard(node["key"])
    elif action == "focus_filter":
        state.mode = "search"
    elif action == "cancel":
        if state.mode in ("detail", "git", "help", "map"):
            state.mode = "list"
        state.message = ""
    elif action == "cycle_agent":
        _cycle_agent(state, actions)
    elif action == "toggle_memory":
        state.show_memory = not state.show_memory
    elif action == "show_help":
        # P69-06c: a real "?" binding -- `_render_help` renders `_KEYMAP`'s
        # actual current bindings, never a hardcoded string that can drift.
        state.mode = "help"
    elif action == "toggle_memory_admin":
        state.mode = "memory"
        state.memory_message = f"press / to search {state.memory_subject} memories"
    elif action == "toggle_git_view":
        state.mode = "git"
        _load_git_view(state, project, actions)
    elif action == "start_scan":
        if project.status == "scanning":
            state.message = "scan already running"
        else:
            state.pending_grant = {
                "kind": "start_scan",
                "project": project.name,
                "root": str(project.root),
                "summary": "Run a full scan against this project's real source.",
            }
            state.mode = "grant_review"
    elif action == "rescan":
        if project.run_id:
            state.pending_grant = {
                "kind": "rescan",
                "project": project.name,
                "root": str(project.root),
                "run_id": project.run_id,
                "summary": f"Rescan run {project.run_id} against current source.",
            }
            state.mode = "grant_review"
        else:
            state.message = "no completed run to rescan yet"
    elif action == "prepare_handoff":
        if not project.run_id:
            state.message = "no completed run to hand off yet"
        elif not state.selected_agent_id:
            state.message = "press 'a' to choose a Setup/Agents target first"
        else:
            finding_count = len(project.visible_findings())
            state.pending_grant = {
                "kind": "handoff",
                "project": project.name,
                "root": str(project.root),
                "run_id": project.run_id,
                "agent_id": state.selected_agent_id,
                "finding_count": finding_count,
                "summary": (
                    f"Send {finding_count} finding(s) from run {project.run_id} "
                    f"to agent {state.selected_agent_id}."
                ),
            }
            state.mode = "grant_review"
    elif action == "cancel_scan":
        _request_cancel(project, actions)
    elif action == "confirm_grant":
        pass  # only meaningful inside grant_review, handled above


def _keymap_footer() -> Text:
    parts = [f"{b.key}:{b.description}" for b in _KEYMAP.bindings]
    return Text(" | ".join(parts), style="dim")


def _render_progress_bar(progress: ScanProgress) -> Text:
    width = 24
    filled = int(width * progress.ratio)
    bar = "#" * filled + "-" * (width - filled)
    return Text(
        f"[{bar}] {progress.executed}/{progress.total} ({progress.status})",
        style="bold blue",
    )


def _render_project_table(project: ProjectState) -> Panel:
    rows = project.visible_findings()
    page_items, total_pages = paginate(rows, project.detail_page)
    table = Table(expand=True)
    table.add_column("", width=2)
    table.add_column("Tool", style="cyan", width=12)
    table.add_column("Path:Line", style="dim", width=30)
    table.add_column("Severity", width=10)
    table.add_column("Message", style="white")
    base = project.detail_page * PAGE_SIZE
    for idx, row in enumerate(page_items):
        marker = ">" if base + idx == project.selected_index else ""
        sev = str(row.get("severity", "info"))
        sev_style = _severity_style(sev)
        table.add_row(
            marker,
            str(row.get("tool", "")),
            f"{_finding_path(row)}:{_finding_line(row)}",
            f"[{sev_style}]{sev}[/{sev_style}]",
            str(row.get("message", "")),
        )
    title = f"Findings ({len(rows)}) page {project.detail_page + 1}/{total_pages}"
    if project.filter_text:
        title += f" filter={project.filter_text!r}"
    return Panel(table, title=title, style="green")


def _render_detail(project: ProjectState) -> Panel:
    rows = project.visible_findings()
    if not rows or project.selected_index >= len(rows):
        return Panel(Text("No finding selected."), title="Detail")
    finding = rows[project.selected_index]
    body = Text(_bounded_local_detail(project.root, finding))
    title = (
        f"{finding.get('tool', '')}: {_finding_path(finding)}:{_finding_line(finding)}"
    )
    return Panel(body, title=title, style="magenta")


def _render_grant_review(grant: dict[str, Any]) -> Panel:
    lines = [
        Text(f"{key}: {value}", style="white")
        for key, value in grant.items()
        if key != "kind"
    ]
    lines.append(Text(""))
    lines.append(Text("[y] confirm    [any other key] decline", style="bold yellow"))
    return Panel(
        Group(*lines), title=f"Review before mutation: {grant['kind']}", style="red"
    )


def _render_memory_admin(state: TuiState) -> Panel:
    """P66-05: real search results, selection, expansion, and pending-delete
    state -- never a static/example row. Render failures already surface via
    `state.memory_message` (set by the dispatch helpers above), so this
    function only ever formats whatever is currently in `state`."""
    owner = _memory_owner_scope(state, state.active_project)
    lines: list[Any] = [
        Text(
            f"subject={state.memory_subject}  query={state.memory_query_buffer!r}",
            style="cyan",
        ),
        Text(
            f"owner={owner['kind']}:{owner['id']}  [o] change scope",
            style="cyan",
        ),
    ]
    if state.mode == "memory_owner":
        lines.append(
            Text(
                f"owner {state.memory_owner_scope_kind} id> "
                f"{state.memory_owner_buffer or ''}"
                "   [tab] kind  [enter] apply  [esc] cancel",
                style="bold yellow",
            )
        )
    if state.mode == "memory_search":
        lines.append(Text(f"/{state.memory_query_buffer}", style="bold yellow"))
    if state.mode == "memory_edit":
        lines.append(
            Text(f"edit note> {state.memory_edit_buffer or ''}", style="bold yellow")
        )

    table = Table(expand=True)
    table.add_column("", width=4)
    table.add_column("id", style="cyan")
    table.add_column("trust", width=14)
    table.add_column("source")
    table.add_column("stale", width=6)
    for idx, item in enumerate(state.memory_items):
        cursor = ">" if idx == state.memory_selected_index else " "
        checked = "x" if item.get("id") in state.memory_selected_ids else " "
        table.add_row(
            f"{cursor}[{checked}]",
            str(item.get("id", "")),
            str(item.get("trust_tier", "")),
            str(item.get("source", "")),
            "yes" if item.get("stale") else "no",
        )
    lines.append(table)

    if state.memory_pending_delete is not None:
        count = len(state.memory_pending_delete["artifact_ids"])
        lines.append(
            Text(
                f"pending delete: {count} record(s) -- [y] confirm  [n]/[esc] cancel",
                style="bold red",
            )
        )
    if state.memory_expanded is not None:
        lines.append(Panel(Text(str(state.memory_expanded)), title="expanded"))
    if state.memory_message:
        lines.append(Text(state.memory_message, style="bold magenta"))
    return Panel(Group(*lines), title="Memory Administration", style="magenta")


def _render_git_panel(state: TuiState) -> Panel:
    """P66-06: real bounded commit history, working-tree/index status, and
    generic artifact category counts -- never a static/example row. Every
    value that can carry hostile content (a commit subject, a dirty-file
    path, an artifact category from a future engine this dashboard has never
    seen) is wrapped in a plain `Text(...)` -- never an f-string handed to a
    Table cell or `console.print` -- so it can never be interpreted as Rich
    markup or a terminal escape sequence, only ever displayed as literal
    text (plan §6.4/P66-06: hostile content "must render as safe text, never
    executable markup")."""
    data = state.git_data or {}
    git = data.get("git") or {}
    lines: list[Any] = [
        Text(
            f"has_git={git.get('has_git')}  head={git.get('head') or '-'}  "
            f"dirty={git.get('dirty')}",
            style="cyan",
        )
    ]

    history = git.get("history") or []
    history_table = Table(expand=True, title=f"History ({len(history)})")
    history_table.add_column("hash", width=10)
    history_table.add_column("author", width=16)
    history_table.add_column("date", width=22)
    history_table.add_column("subject")
    for commit in history[:PAGE_SIZE]:
        history_table.add_row(
            Text(str(commit.get("hash", ""))[:8]),
            Text(str(commit.get("author", ""))),
            Text(str(commit.get("date", ""))),
            Text(str(commit.get("subject", ""))),
        )
    lines.append(history_table)

    dirty_files = git.get("dirty_files") or []
    if dirty_files:
        dirty_table = Table(expand=True, title=f"Dirty ({len(dirty_files)})")
        dirty_table.add_column("status", width=8)
        dirty_table.add_column("path")
        for entry in dirty_files[:PAGE_SIZE]:
            dirty_table.add_row(
                Text(str(entry.get("status", ""))),
                Text(str(entry.get("path", ""))),
            )
        lines.append(dirty_table)

    artifacts = data.get("artifacts") or {}
    counts: dict[str, int] = {}
    for bucket in ("scan_outputs", "handoffs", "memory"):
        for item in artifacts.get(bucket) or []:
            key = str(item.get("category", "unknown"))
            counts[key] = counts.get(key, 0) + 1
    if counts:
        lines.append(
            Text(
                "artifacts: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
                style="white",
            )
        )
    if state.git_message:
        lines.append(Text(state.git_message, style="bold magenta"))
    return Panel(Group(*lines), title="Git & Artifacts", style="blue")


def _render_help(state: TuiState) -> Panel:
    """P69-06c: the real, current `_KEYMAP` bindings -- never a hardcoded
    help string that can drift from what's actually bound."""
    lines = [f"{b.key}: {b.description}" for b in _KEYMAP.bindings]
    return Panel(Text("\n".join(lines)), title="Key Bindings", style="cyan")


def _render_nav_pane(state: TuiState) -> Panel:
    """U04 fix: the persistent project list shown alongside the main
    content at compact/wide widths (Phase 66 §3.8's nav pane)."""
    lines = [
        Text(
            f"{'>' if idx == state.active_index else ' '}{p.name}",
            style=THEME["blue"] if idx == state.active_index else THEME["text_muted"],
        )
        for idx, p in enumerate(state.projects)
    ]
    return Panel(Group(*lines), title="Projects", style=THEME["border"])


def _render_project_selector(state: TuiState) -> Panel:
    """U01 fix: F2's overlay -- highlights `project_selector_index`,
    never `active_index` directly (that only changes on Enter)."""
    lines: list[Any] = [
        Text(
            f"{'>' if idx == state.project_selector_index else ' '}{p.name}",
            style=THEME["blue"]
            if idx == state.project_selector_index
            else THEME["text"],
        )
        for idx, p in enumerate(state.projects)
    ]
    lines.append(Text(""))
    lines.append(Text("[enter] switch    [escape] cancel", style="bold yellow"))
    return Panel(Group(*lines), title="Project Selector", style=THEME["border"])


def _render_map(state: TuiState, project: ProjectState) -> Panel:
    """U01 fix: the real Project -> Files -> Findings hierarchy
    (`_map_nodes`/`_map_visible_nodes`), with a `[+]`/`[-]` glyph on every
    expandable file node -- previously no Map view existed at all."""
    nodes = _map_visible_nodes(project, state.map_expanded)
    lines: list[Text] = []
    for idx, node in enumerate(nodes):
        marker = ">" if idx == state.map_selected_index else " "
        indent = "  " * int(node["depth"])
        glyph = ""
        if node.get("children"):
            glyph = "[-] " if node["key"] in state.map_expanded else "[+] "
        lines.append(Text(f"{marker}{indent}{glyph}{node['label']}"))
    if not lines:
        lines.append(Text("No findings."))
    return Panel(Group(*lines), title="Map", style=THEME["blue"])


def _footer_status_line(state: TuiState, project: ProjectState) -> Text:
    """U04 fix: the single optional status row -- always exactly one
    renderable, so the footer is always exactly 2 rows total alongside
    `_keymap_footer()` (previously grew to 3+ whenever any of these was
    present, since each used to insert its own extra line)."""
    if state.mode == "search":
        return Text(f"/{project.filter_text}", style="bold yellow")
    if state.mode == "quit_confirm":
        # P69-06g: the copy names exactly what Detach does for this run's
        # *current* ownership state -- never implying invisible continuation
        # a locally-owned run cannot actually provide.
        detach_desc = (
            "Detach: run continues on the dashboard"
            if project.owner == "dashboard"
            else "Detach: cancels with saved partial result (no dashboard running)"
        )
        return Text(
            f"{detach_desc}  [d]  |  Cancel run, stay open  [c]  |  "
            "Return, keep observing  [r]",
            style="bold yellow",
        )
    if project.status in ("scanning", "cancelling") and project.progress:
        return _render_progress_bar(project.progress)
    if state.message:
        return Text(state.message, style="bold magenta")
    return Text("")


def render_app(state: TuiState) -> Layout:
    project = state.active_project
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )

    header = Text(
        f"⚡ Rush Interactive Quality Explorer v{__version__}  "
        f"[{state.active_index + 1}/{len(state.projects)}] {project.name}  "
        f"({state.terminal_size[0]}x{state.terminal_size[1]})",
        style=_HEADER_STYLE,
    )
    layout["header"].update(Panel(header, style=_HEADER_STYLE))

    if state.mode in ("memory", "memory_search", "memory_edit", "memory_owner"):
        body: Any = _render_memory_admin(state)
    elif state.mode == "git":
        body = _render_git_panel(state)
    elif state.mode == "map":
        body = _render_map(state, project)
    elif state.mode == "project_selector":
        body = _render_project_selector(state)
    elif state.mode == "grant_review" and state.pending_grant:
        body = _render_grant_review(state.pending_grant)
    elif state.mode == "detail":
        body = _render_detail(project)
    elif state.mode == "help":
        body = _render_help(state)
    else:
        body = _render_project_table(project)

    # U04 fix: real width-dependent pane layout (Phase 66 §3.8) --
    # wide (>=100 cols) splits nav/list/detail three ways, compact
    # (80-99) splits nav/content, narrow (<80) shows a single pane with no
    # nav pane at all. Previously there was only one `>= 100` check with
    # no distinct 80-99/narrow behavior. `show_memory`'s split stays the
    # highest-priority branch, unrelated to width.
    branch = _width_branch(state.terminal_size[0])
    if state.show_memory:
        from rush.token_economy.tui_gain import build_gain_panel

        layout["main"].split_row(
            Layout(name="primary", ratio=2),
            Layout(name="memory", ratio=1),
        )
        layout["main"]["primary"].update(body)
        layout["main"]["memory"].update(build_gain_panel(project.root))
    elif branch == "wide" and state.mode in ("list", "map"):
        layout["main"].split_row(
            Layout(name="nav", size=24),
            Layout(name="list", ratio=45),
            Layout(name="detail", ratio=55),
        )
        layout["main"]["nav"].update(_render_nav_pane(state))
        layout["main"]["list"].update(body)
        layout["main"]["detail"].update(_render_detail(project))
    elif branch == "compact" and state.mode in ("list", "map"):
        layout["main"].split_row(
            Layout(name="nav", size=20),
            Layout(name="content", ratio=1),
        )
        layout["main"]["nav"].update(_render_nav_pane(state))
        layout["main"]["content"].update(body)
    else:
        layout["main"].update(body)

    # U04 fix: the footer is always exactly two rows -- a single optional
    # status line plus the keymap line -- regardless of width or how many
    # of search/quit-confirm/progress/message conditions are active.
    footer_body: Any = Group(_footer_status_line(state, project), _keymap_footer())
    layout["footer"].update(Panel(footer_body, style=_FOOTER_STYLE))

    return layout


def run_interactive_tui(
    project_seeds: list[ProjectSeed],
    *,
    console: Console | None = None,
    key_reader: KeyReader | None = None,
    actions: ScanActions | None = None,
    tick_seconds: float = 0.05,
    max_ticks: int | None = None,
    use_live: bool = True,
) -> TuiState:
    """Persistent Rich-Live interactive loop (P66-03/F36). Restores the
    terminal via `raw_terminal()` on both a clean 'q' exit and any
    exception -- the `with` block's `finally` always runs, regardless of
    how the loop body exits."""
    import os

    from rich.live import Live

    # U04 fix: NO_COLOR and reduced motion are independent settings --
    # NO_COLOR only ever controls the Console's own color output below;
    # only RUSH_REDUCED_MOTION controls whether this loop's idle refresh
    # heartbeat runs at all.
    reduced_motion = bool(os.environ.get("RUSH_REDUCED_MOTION"))
    console = console or Console(no_color=bool(os.environ.get("NO_COLOR")))
    actions = actions or default_scan_actions()
    reader = key_reader or make_key_reader()

    state = TuiState(
        projects=[
            ProjectState(
                name=seed.name,
                root=seed.root,
                results=list(seed.results),
                project_id=_resolve_registered_project_id(seed.root),
            )
            for seed in project_seeds
        ]
    )
    state.terminal_size = reader.get_size()

    # P69-06a: start the interactive interface immediately -- the initial
    # CHECK_SUITE runs as a background job the loop's own polling
    # (`_poll_running_scans`/`project.status`) attaches to, instead of
    # `ui_cmd` blocking interface startup on it.
    for project in state.projects:
        if not project.results and actions.run_check_suite is not None:
            _start_initial_check_thread(project, actions)

    # P69-06 CONNECT: explicit active/idle refresh-rate limiter -- 20Hz while
    # a key was just dispatched or a scan is running, 4Hz otherwise -- rather
    # than refreshing on every tick unconditionally.
    _ACTIVE_REFRESH_INTERVAL = 1.0 / 20
    _IDLE_REFRESH_INTERVAL = 1.0 / 4
    last_refresh = 0.0

    ticks = 0
    with raw_terminal():
        live = (
            Live(
                render_app(state),
                console=console,
                screen=True,
                auto_refresh=False,
            )
            if use_live
            else None
        )
        if live is not None:
            live.start()
        try:
            while not state.should_quit:
                if max_ticks is not None and ticks >= max_ticks:
                    break
                ticks += 1

                size = reader.get_size()
                if size != state.terminal_size:
                    state.terminal_size = size

                _poll_running_scans(state, actions)

                key = reader.read_key(tick_seconds)
                if key is not None:
                    _dispatch_key(state, key, actions)

                if live is not None:
                    has_activity = key is not None or any(
                        p.status in ("scanning", "cancelling") for p in state.projects
                    )
                    # U04 fix: reduced motion renders the final state
                    # (already shown once by `Live(render_app(state), ...)`
                    # above) and never refreshes again on an idle timer --
                    # only a real key/scan event re-renders. Normal motion
                    # keeps its active/idle heartbeat regardless.
                    if reduced_motion:
                        if has_activity:
                            live.update(render_app(state), refresh=True)
                    else:
                        interval = (
                            _ACTIVE_REFRESH_INTERVAL
                            if has_activity
                            else _IDLE_REFRESH_INTERVAL
                        )
                        now = time.monotonic()
                        if now - last_refresh >= interval:
                            live.update(render_app(state), refresh=True)
                            last_refresh = now
        finally:
            if live is not None:
                live.stop()

    return state
