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

import threading
import uuid
from collections.abc import Callable, Mapping
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
from rush.dashboard.terminal_input import KeyReader, make_key_reader, raw_terminal
from rush.permissions import ExecutionPermissions
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


def default_scan_actions() -> ScanActions:
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
    results: list[ToolResult] = field(default_factory=list)
    selected_index: int = 0
    filter_text: str = ""
    detail_page: int = 0
    run_id: str | None = None
    plan_total: int = 0
    progress: ScanProgress | None = None
    progress_history: list[ScanProgress] = field(default_factory=list)
    status: str = "idle"  # idle | scanning | cancelling | cancelled | complete | error
    last_message: str = ""
    scan_thread: threading.Thread | None = field(
        default=None, repr=False, compare=False
    )

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
    # P66-06: Git history and every generated artifact (mode == "git").
    # `git_data` is the real `project_snapshot()` result loaded by
    # `_load_git_view` below -- reset on every project switch so a stale
    # project's history/status can never leak into the newly active one.
    git_data: dict[str, Any] | None = None
    git_message: str = ""

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


def _start_scan_thread(project: ProjectState, actions: ScanActions) -> None:
    plan = actions.plan_scan(project.root)
    run_id = str(uuid.uuid4())
    project.run_id = run_id
    project.plan_total = len(list(getattr(plan, "candidates", None) or []))
    project.status = "scanning"
    project.progress = None
    project.progress_history = []

    def _worker() -> None:
        try:
            run = actions.execute_scan(plan, run_id=run_id)
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

    thread = threading.Thread(target=_worker, daemon=True)
    project.scan_thread = thread
    thread.start()


def _start_rescan_thread(project: ProjectState, actions: ScanActions) -> None:
    baseline_run_id = project.run_id
    project.status = "scanning"
    project.progress = None
    project.progress_history = []

    def _worker() -> None:
        try:
            outcome = actions.rescan_project_run(project.root, baseline_run_id)
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


def _poll_running_scans(state: TuiState, actions: ScanActions) -> None:
    for project in state.projects:
        if project.status not in ("scanning", "cancelling"):
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
    """Every distinct `source` this project's memory store has ever recorded
    -- an admin session sees the whole project (mirrors the dashboard's own
    `_all_known_sources` in `server.py`), never a narrower cross-tool
    allowlist. Read-only: `TypedArtifactStore.list_artifact_refs()` is a
    public read method, never a raw SQLite write."""
    from rush.memory.store import TypedArtifactStore

    store = TypedArtifactStore(project.root)
    return sorted({row["source"] for row in store.list_artifact_refs()})


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
    sources = _memory_known_sources(project)
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
    try:
        result = actions.memory_run(
            project.root,
            operation="delete",
            request={
                "artifact_ids": ids,
                "expected_revisions": revisions,
                "scope": state.memory_subject,
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
    if state.mode == "memory":
        _handle_memory_key(state, key, actions)
        return

    action = _KEYMAP.get_action_for_key(key)
    if action is None:
        return
    project = state.active_project

    if action == "quit":
        state.should_quit = True
    elif action == "cursor_down":
        _move_selection(project, 1)
    elif action == "cursor_up":
        _move_selection(project, -1)
    elif action == "select_row":
        if project.visible_findings():
            state.mode = "detail"
    elif action == "next_project":
        state.active_index = (state.active_index + 1) % len(state.projects)
        # P66-05: two-project isolation -- a memory admin session never
        # carries a prior project's list/selection/pending-delete across a
        # project switch.
        state.memory_items = []
        state.memory_selected_ids = set()
        state.memory_pending_delete = None
        state.memory_expanded = None
        state.memory_message = ""
        # P66-06: same two-project isolation guarantee for the Git/artifacts
        # view -- a prior project's history/status never leaks into the
        # newly active one before it is explicitly reloaded.
        state.git_data = None
        state.git_message = ""
    elif action == "focus_filter":
        state.mode = "search"
    elif action == "cancel":
        if state.mode in ("detail", "git"):
            state.mode = "list"
        state.message = ""
    elif action == "cycle_agent":
        _cycle_agent(state, actions)
    elif action == "toggle_memory":
        state.show_memory = not state.show_memory
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
        if project.status == "scanning" and project.run_id:
            try:
                actions.cancel_scan_run(project.root, project.run_id)
                project.status = "cancelling"
            except Exception as exc:  # noqa: BLE001 -- injectable Phase65
                # seam (`cancel_scan_run`); a failed cancel request must
                # surface to the user, never crash the key-dispatch path.
                state.message = f"cancel failed: {exc}"
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
        sev_style = (
            "red"
            if sev in ("error", "fail")
            else ("yellow" if sev == "warn" else "blue")
        )
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
    lines: list[Any] = [
        Text(
            f"subject={state.memory_subject}  query={state.memory_query_buffer!r}",
            style="cyan",
        )
    ]
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
        style="bold cyan",
    )
    layout["header"].update(Panel(header, style="cyan"))

    if state.mode in ("memory", "memory_search", "memory_edit"):
        body: Any = _render_memory_admin(state)
    elif state.mode == "git":
        body = _render_git_panel(state)
    elif state.mode == "grant_review" and state.pending_grant:
        body = _render_grant_review(state.pending_grant)
    elif state.mode == "detail":
        body = _render_detail(project)
    else:
        body = _render_project_table(project)

    if state.show_memory:
        from rush.token_economy.tui_gain import build_gain_panel

        layout["main"].split_row(
            Layout(name="primary", ratio=2),
            Layout(name="memory", ratio=1),
        )
        layout["main"]["primary"].update(body)
        layout["main"]["memory"].update(build_gain_panel(project.root))
    else:
        layout["main"].update(body)

    footer_lines = [_keymap_footer()]
    if state.mode == "search":
        footer_lines.insert(0, Text(f"/{project.filter_text}", style="bold yellow"))
    if project.status in ("scanning", "cancelling") and project.progress:
        footer_lines.insert(0, _render_progress_bar(project.progress))
    if state.message:
        footer_lines.insert(0, Text(state.message, style="bold magenta"))
    footer_body: Any = (
        footer_lines[0] if len(footer_lines) == 1 else Group(*footer_lines)
    )
    layout["footer"].update(Panel(footer_body, style="grey50"))

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

    reduced_motion = bool(
        os.environ.get("NO_COLOR") or os.environ.get("RUSH_REDUCED_MOTION")
    )
    console = console or Console(no_color=bool(os.environ.get("NO_COLOR")))
    actions = actions or default_scan_actions()
    reader = key_reader or make_key_reader()

    state = TuiState(
        projects=[
            ProjectState(name=seed.name, root=seed.root, results=list(seed.results))
            for seed in project_seeds
        ]
    )
    state.terminal_size = reader.get_size()

    ticks = 0
    with raw_terminal():
        live = (
            Live(
                render_app(state),
                console=console,
                screen=False,
                auto_refresh=False,
                refresh_per_second=(2 if reduced_motion else 12),
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
                    live.update(render_app(state), refresh=True)
        finally:
            if live is not None:
                live.stop()

    return state
