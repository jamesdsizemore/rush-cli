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

import base64
import io
import json
import os
import queue
import stat
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_args

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
from rush.memory.maintenance import MaintenanceTask
from rush.memory.store import MemorySubject
from rush.permissions import ExecutionPermissions
from rush.runtime.subprocesses import (
    OWNED_TERMINATION_TIMEOUT_SECONDS,
    reap_owner_processes,
)
from rush.theme import safe_terminal_text
from rush.tools.base import ToolResult

PAGE_SIZE = 20
"""Generic paginated page size, reused for every output type (findings,
handoff previews) that has no dedicated terminal visualization."""

_DETAIL_CONTEXT_LINES = 4
_DETAIL_MAX_BYTES = 8192

# T28-A: TUI-local bindings appended to the shared DEFAULT_KEYBINDINGS; the
# live `_KEYMAP` is built from both once `ACTIONS` (below) is defined, so every
# bound key names a registered action with a real run function.
_TUI_KEYBINDINGS = [
    KeybindingAction(
        key="M",
        action_name="toggle_memory_admin",
        description="Memory section: search/expand/promote/edit/delete",
    ),
    KeybindingAction(
        key="G",
        action_name="toggle_git_view",
        description="Git section: history, status, diff",
    ),
    KeybindingAction(
        key="C", action_name="start_check", description="Start analysis (check suite)"
    ),
    KeybindingAction(
        key="A",
        action_name="project_add",
        description="Add this folder as a project (reviewed)",
    ),
    KeybindingAction(
        key="N",
        action_name="project_create",
        description="Create a new project (reviewed)",
    ),
    KeybindingAction(
        key="R",
        action_name="project_relink",
        description="Relink a moved project root (reviewed)",
    ),
    KeybindingAction(
        key="L", action_name="choose_later", description="Choose a project later"
    ),
    KeybindingAction(
        key="t",
        action_name="setup_toggle_grant",
        description="Setup: toggle the highlighted stage's grant",
    ),
    KeybindingAction(
        key="p",
        action_name="setup_apply",
        description="Setup: review the toggled grants, then apply",
    ),
    KeybindingAction(
        key="x",
        action_name="setup_retry",
        description="Setup: regenerate the review after a failed stage",
    ),
    KeybindingAction(key="right", action_name="map_expand", description="Expand"),
    KeybindingAction(key="l", action_name="map_expand", description="Expand"),
    KeybindingAction(key="left", action_name="map_collapse", description="Collapse"),
    KeybindingAction(key="h", action_name="map_collapse", description="Collapse"),
]
_BINDINGS = [*DEFAULT_KEYBINDINGS, *_TUI_KEYBINDINGS]

_TERMINAL_RUN_STATES = {
    "completed": "complete",
    "incomplete": "complete",
    "cancelled": "cancelled",
    "failed": "error",
}

# U01 fix: Tab/Shift+Tab cycle visible panes; F3 cycles Sections. Both are
# state-only concerns here -- `render_app`'s width branches (U04) decide
# which of these panes actually gets drawn at the current terminal size.
# T28-A shared state vocabulary (all packets).
SECTIONS: tuple[str, ...] = (
    "overview",
    "map",
    "scans",
    "memory",
    "tokens",
    "git",
    "artifacts",
    "setup",
)
SECTION_LABELS = {
    "overview": "Overview",
    "map": "Map",
    "scans": "Scans/Findings",
    "memory": "Memory",
    "tokens": "Tokens",
    "git": "Git",
    "artifacts": "Artifacts",
    "setup": "Setup/Agents",
}
SECTION_STATES: tuple[str, ...] = (
    "loading",
    "populated",
    "empty",
    "unavailable",
    "denied",
    "failed",
    "stale",
    "disconnected",
)
OVERLAYS: tuple[str | None, ...] = (
    None,
    "projects",
    "sections",
    "help",
    "grant_review",
    "form",
    "quit_confirm",
    "resize_guidance",
    "detaching",
)
FOCUS_CYCLE: tuple[str, ...] = ("nav", "list", "detail", "actions")
# Sections rendered by an existing interaction mode; every other section is
# drawn in mode "list" from `TuiState.section`.
_SECTION_MODES = {"map": "map", "git": "git", "memory": "memory"}
_MODE_OVERLAYS = {
    "project_selector": "projects",
    "help": "help",
    "grant_review": "grant_review",
    "quit_confirm": "quit_confirm",
}
# F2 selector rows after the open projects: (action id, label).
_SELECTOR_EXTRAS: tuple[tuple[str, str], ...] = (
    ("project_add", "Add this folder"),
    ("project_create", "Create a new project"),
    ("choose_later", "Choose later"),
)
# F3 chooser rows after the eight sections: (action id, label).
_CHOOSER_EXTRAS: tuple[tuple[str, str], ...] = (
    ("start_check", "Check"),
    ("start_scan", "Scan"),
    ("open_project_selector", "Projects"),
    ("show_help", "Help"),
    ("quit", "Quit"),
)

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
    """Canonical `path` drives ONLY a bounded local file read -- never a
    subprocess, shell, or arbitrary command. The read goes through
    `PhysicalRoot.open_contained` (no absolute path, no `..`, no symlinked
    component even inside the root) and an `O_NOFOLLOW` open of a regular
    file, and shows the whole file up to `_DETAIL_MAX_BYTES` (scrollable,
    never a first-lines-only snippet), labelled "live file: <path>". A
    refused path or any read failure degrades to the finding's own message.
    Control characters are stripped from everything returned; no exception
    ever escapes this function."""
    message = safe_terminal_text(finding.get("message") or "")
    path_value = _finding_path(finding)
    if not path_value:
        return message or "(no path)"
    try:
        from rush.io.physical_paths import ContainmentError, PhysicalRoot

        try:
            target = PhysicalRoot(root).open_contained(path_value)
        except ContainmentError:
            return message or "(path refused)"
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return message or "(not a regular file)"
            raw = os.read(fd, _DETAIL_MAX_BYTES)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return message or "(unable to read local context)"
    text = safe_terminal_text(raw.decode("utf-8", errors="replace"))
    header = safe_terminal_text(f"live file: {path_value}")
    line_no = finding.get("line")
    if isinstance(line_no, int):
        header += f" (line {line_no})"
    return "\n".join(part for part in (header, message, text) if part)


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
    # T28-A: `load_overview(root, *, project_id, data_root)` -> the read-only
    # Overview payload (`rush status` data + Git/stack/run evidence +
    # derived `registration`). Same trailing + defaulted contract as above.
    load_overview: Callable[..., Any] | None = None


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
        lexical_path: Path | None = None,
        original_input: str | None = None,
        cancel_check: Callable[[], bool] | None = None,
        **kwargs: object,
    ) -> Any:
        from rush.workflows.suites import CHECK_SUITE, run_workflow_suite

        assert permissions is not None
        # P69-06f: this process's own identity travels into the suite, so
        # every subprocess it spawns is fenced under an owner recovery can
        # probe and Detach's force-exit can terminate.
        # T8 (4)(b): the suite walks the user's lexical path when known, so
        # a root-entry alias is judged as typed; `root` stays the resolved one.
        return run_workflow_suite(
            suite=CHECK_SUITE,
            path=lexical_path if lexical_path is not None else root,
            permissions=permissions,
            owner_instance_id=owner_instance_id,
            run_id=run_id,
            cancel_check=cancel_check,
            original_requested_targets=(
                (original_input,) if original_input is not None else None
            ),
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
        load_overview=load_overview,
    )


def _registration_from_status(data: Mapping[str, Any]) -> dict[str, Any]:
    """T28-A: the project's registry state from `rush status` data -- a
    corrupt/unreadable registry is never reported as "no project"."""
    registry = data.get("registry") or {}
    project = data.get("project") or {}
    registry_state = registry.get("state")
    if registry_state in ("corrupt", "unreadable"):
        return {
            "state": registry_state,
            "reason": registry.get("error") or f"registry {registry_state}",
        }
    registration = project.get("registration")
    if registration == "ambiguous":
        return {
            "state": "ambiguous",
            "reason": "more than one registered project matches this root",
        }
    if registration != "registered":
        return {"state": "none", "reason": "no project registered for this root"}
    identity = {
        "project_id": project.get("project_id"),
        "revision": project.get("revision"),
    }
    if project.get("root_exists") is False:
        return {"state": "moved", "reason": "registered root missing", **identity}
    return {"state": "ok", "reason": None, **identity}


def _moved_registration(root: Path, data_root: Path | None) -> dict[str, Any] | None:
    """`root` carries the `.rush/project.json` identity of a registered
    project whose recorded root no longer exists: the folder was moved, so
    Relink is offered instead of adding a duplicate. Read-only."""
    from rush.setup.provision import default_data_root
    from rush.workflows.projects import read_descriptor_strict, read_registry_strict

    descriptor = read_descriptor_strict(root).get("descriptor")
    project_id = descriptor.get("project_id") if isinstance(descriptor, dict) else None
    if not isinstance(project_id, str):
        return None
    registry = read_registry_strict(data_root or default_data_root()).get("registry")
    projects = registry.get("projects") if isinstance(registry, dict) else None
    entry = projects.get(project_id) if isinstance(projects, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("root"), str):
        return None
    recorded = Path(entry["root"])
    if recorded.is_dir() or recorded == root:
        return None
    return {
        "state": "moved",
        "reason": f"registered root missing: {recorded}",
        "project_id": project_id,
        "revision": entry.get("revision", 1),
        "new_root": str(root),
    }


def load_overview(
    root: Path, *, project_id: str | None = None, data_root: Path | None = None
) -> dict[str, Any]:
    """T28-A default Overview loader: `rush status` (T23, zero-write) plus
    `project_overview_evidence` (Git, stack, latest attempt counts)."""
    from rush.tools.status import StatusTool
    from rush.workflows.projects import project_overview_evidence

    status = StatusTool()(root, data_root=data_root)
    data = (status.get("raw") or {}).get("data") or {}
    registration = _registration_from_status(data)
    if registration["state"] == "none" and project_id:
        # `rush status` resolves by path, so a moved root reads as
        # unregistered; the known id tells the two apart.
        from rush.workflows.projects import ProjectNotFoundError, resolve_project

        with suppress(ProjectNotFoundError):
            record = resolve_project(project_id, data_root=data_root)
            if not record["exists"]:
                registration = {
                    "state": "moved",
                    "reason": f"registered root missing: {record['root']}",
                    "project_id": project_id,
                    "revision": record["revision"],
                }
    if registration["state"] == "none":
        registration = _moved_registration(root, data_root) or registration
    resolved_id = registration.get("project_id") or project_id
    return {
        "status": data,
        "status_summary": status.get("summary"),
        "evidence": project_overview_evidence(root, resolved_id),
        "registration": registration,
    }


@dataclass
class ProjectSeed:
    """One project panel's starting point before the interactive loop
    starts: a name, its root, and any already-known results."""

    name: str
    root: Path
    results: list[ToolResult] = field(default_factory=list)
    # T8 (4)(b): the lexical absolute path and the user's original input
    # string; `None` when unavailable (never a fabricated cwd string).
    lexical_path: Path | None = None
    original_input: str | None = None


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
    # T8 (4)(b): carried from `ProjectSeed` for the initial check suite.
    lexical_path: Path | None = None
    original_input: str | None = None
    selected_index: int = 0
    filter_text: str = ""
    detail_page: int = 0
    run_id: str | None = None
    plan_total: int = 0
    progress: ScanProgress | None = None
    progress_history: list[ScanProgress] = field(default_factory=list)
    # T28-C: the read-only `project_map_snapshot` (memories/agents branches,
    # captured artifact snapshots for detail), loaded lazily and reloaded
    # when `map_snapshot_key` (run_id, status) changes.
    map_snapshot: dict[str, Any] | None = field(default=None, repr=False, compare=False)
    map_snapshot_key: tuple[str | None, str] | None = field(
        default=None, repr=False, compare=False
    )
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
    # T28-A shared state. `registration`: {state none|ok|moved|corrupt|
    # unreadable|ambiguous, reason, project_id?, revision?, deferred?}; None
    # until the Overview has read it. `views` is only a constructor seed --
    # `TuiState` absorbs it into its (project_key, section) map.
    registration: dict[str, Any] | None = None
    work_kind: str | None = None  # check | scan | rescan | dashboard
    cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False
    )
    section: str = "overview"
    views: dict[str, Any] = field(default_factory=dict, repr=False)
    # T28-B: `rush ui --allow-*` grants for this project's Setup toggles, and
    # the ordered (stage, status) events a setup apply worker posted.
    launch_permissions: ExecutionPermissions | None = None
    setup_apply_events: list[tuple[str, str]] = field(default_factory=list)
    setup_apply_thread: threading.Thread | None = field(
        default=None, repr=False, compare=False
    )
    generation: int = 0
    pending: dict[Any, tuple[int, tuple[Any, ...]]] = field(
        default_factory=dict, repr=False
    )

    def identity(self) -> tuple[Any, ...]:
        # A section load is keyed by project and root only: starting a scan
        # (a new `run_id`) must not orphan an in-flight Overview/Tokens load.
        return (self.project_id, str(self.root))

    def begin_request(self, key: Any) -> int:
        """Start a background request for `key`; only its returned
        generation, under this same identity, may later be applied."""
        self.generation += 1
        self.pending[key] = (self.generation, self.identity())
        return self.generation

    def invalidate(self) -> None:
        """Switching away: every outstanding request becomes stale."""
        self.generation += 1
        self.pending.clear()

    def accepts(self, key: Any, generation: int, identity: tuple[Any, ...]) -> bool:
        return self.pending.get(key) == (generation, identity) and (
            identity == self.identity()
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


def project_key(project: ProjectState) -> str:
    """T28 view identity: the registered id, else the root path."""
    return project.project_id or f"path:{project.root}"


@dataclass
class SectionView:
    """One project's one section: its truthful load state plus the
    selection/filter/scroll it restores to when the user returns."""

    state: str = "loading"
    reason: str | None = None
    data: Any = None
    loaded_at: str | None = None
    generation: int = 0
    selection: int = 0
    scroll: int = 0
    filters: dict[str, Any] = field(default_factory=dict)
    expanded: set[str] = field(default_factory=set)
    page_cursor: str | None = None


def _coerce_view(value: SectionView | Mapping[str, Any]) -> SectionView:
    if isinstance(value, SectionView):
        return value
    known = {f.name for f in fields(SectionView)}
    return SectionView(**{k: v for k, v in value.items() if k in known})


@dataclass
class TuiState:
    projects: list[ProjectState]
    active_index: int | None = None
    mode: str = "list"  # list | search | detail | grant_review
    selected_agent_id: str | None = None
    agent_ids: list[str] = field(default_factory=list)
    pending_grant: dict[str, Any] | None = None
    message: str = ""
    should_quit: bool = False
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
    memory_pending_maintain: list[dict[str, Any]] | None = None
    memory_expanded: dict[str, Any] | None = None
    memory_edit_buffer: str | None = None
    memory_edit_field: str = "note"
    memory_edit_conflict: dict[str, Any] | None = None
    memory_message: str = ""
    memory_filter_trust: str | None = None
    memory_filter_source: str | None = None
    memory_filter_freshness: str | None = None
    memory_filter_archived: bool = False
    memory_filter_owner: str | None = None
    # T28-D: the "f" filter form (mode == "memory_filter"): one text buffer per
    # `_MEMORY_FILTER_FIELDS` entry; Enter applies every field, Escape discards.
    memory_filter_buffer: dict[str, str] | None = None
    memory_filter_field: str = "trust"
    # T28-D: grants the user reviewed for the next promote (list of ExecutionPermissions field names).
    memory_pending_promote: dict[str, Any] | None = None
    # T28-D confirm step: the previewed edit/archive/restore/promote/write held
    # for "y"; "n"/Escape clears it with zero writes. Keys: operation, verb,
    # call (memory_run kwargs of the apply), required_grants, ids, versions,
    # owner_scope, item (the selected row, edit/archive only).
    memory_pending_mutation: dict[str, Any] | None = None
    # T28-D: propose/create form fields {"subject","source","content"} (mode == "memory_create").
    memory_create_buffer: dict[str, str] | None = None
    memory_create_field: str = "content"
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
    # T28-A: Tab/Shift+Tab focus position (`FOCUS_CYCLE`; `active_pane` alias).
    focus: str = "list"
    section: str = "overview"
    overlay: str | None = None
    views: dict[tuple[str, str], SectionView] = field(default_factory=dict)
    result_queue: queue.SimpleQueue[Any] = field(
        default_factory=queue.SimpleQueue, repr=False, compare=False
    )
    # (project_key, section) loads the loop submits on its next tick --
    # dispatch and render never do I/O for a section load themselves.
    load_requests: set[tuple[str, str]] = field(default_factory=set)
    data_root: Path | None = None
    nav_index: int = 0
    action_index: int = 0
    chooser_index: int = 0
    form: dict[str, Any] | None = None
    launch_permissions: ExecutionPermissions | None = None
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

    def __post_init__(self) -> None:
        if self.active_index is None and self.projects:
            self.active_index = 0
        for project in self.projects:
            self.absorb(project)

    def absorb(self, project: ProjectState) -> None:
        """Move a project's constructor `views` seed into the shared map."""
        for section, view in project.views.items():
            self.views[(project_key(project), section)] = _coerce_view(view)
        project.views = {}
        key = (project_key(project), "setup")
        view = self.views.setdefault(key, SectionView())
        if not isinstance(view.data, dict):
            view.data = {}
        view.data.setdefault(
            "stage_grants", _default_stage_grants(project, self.launch_permissions)
        )

    @property
    def active_pane(self) -> str:
        return self.focus

    @active_pane.setter
    def active_pane(self, value: str) -> None:
        self.focus = value

    @property
    def active_project(self) -> ProjectState:
        if self.active_index is None:
            raise LookupError("no project is open")
        return self.projects[self.active_index]

    def to_dict(self) -> dict[str, Any]:
        if not self.projects:
            return {"active_project": None, "mode": self.mode, "message": self.message}
        active = self.active_project
        return {
            "section": self.section,
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

    T28-C: Memories and Agents branch nodes (parent "root", so hidden until
    the root is expanded) come from the lazily loaded read-only
    `project_map_snapshot`; not loaded or unavailable is said in the branch
    label, never an empty-looking branch."""
    rows = project.flattened_findings()
    by_path: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_path.setdefault(_finding_path(row), []).append(row)

    nodes: list[dict[str, Any]] = [
        {
            "key": "root",
            "label": project.name,
            "depth": 0,
            "kind": "project",
            "children": True,
        }
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
    snapshot = project.map_snapshot or {}
    for kind, field_name, title in (
        ("memory", "memories", "Memories"),
        ("agent", "agents", "Agents"),
    ):
        branch_key = f"branch:{field_name}"
        items = snapshot.get(field_name)
        if project.map_snapshot is None:
            label = f"{title}: not loaded"
        elif snapshot.get("available") is False:
            label = f"{title}: unavailable ({snapshot.get('reason')})"
        elif isinstance(items, list):
            label = f"{title} ({len(items)})"
        else:
            label = f"{title}: {items}"
        leaves = (
            [item for item in items if isinstance(item, dict)]
            if isinstance(items, list)
            else []
        )
        nodes.append(
            {
                "key": branch_key,
                "label": label,
                "depth": 1,
                "kind": kind,
                "parent": "root",
                "children": leaves,
            }
        )
        for idx, item in enumerate(leaves):
            related = item.get("cites") if kind == "memory" else item.get("assigned_to")
            nodes.append(
                {
                    "key": f"{branch_key}:{idx}",
                    "label": f"{item.get('id')} -> {', '.join(map(str, related or []))}",
                    "depth": 2,
                    "kind": kind,
                    "parent": branch_key,
                }
            )
    return nodes


def _map_visible_nodes(
    project: ProjectState, expanded: set[str]
) -> list[dict[str, Any]]:
    """A node is visible only when every ancestor's key is in `expanded`.
    The root and file nodes are always visible; finding leaves follow their
    file node, Memories/Agents branches follow the root."""
    nodes = _map_nodes(project)
    parent_of = {node["key"]: node.get("parent") for node in nodes}

    def shown(node: dict[str, Any]) -> bool:
        parent = node.get("parent")
        while parent is not None:
            if parent not in expanded:
                return False
            parent = parent_of.get(parent)
        return True

    return [node for node in nodes if shown(node)]


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

        if operation == "cancel":
            # T28-B: the TUI's work-kind cancel names the server's own op.
            operation = "scan_cancel"
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
    project.work_kind = "dashboard"
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


def _start_scan_thread(
    project: ProjectState,
    actions: ScanActions,
    permissions: ExecutionPermissions | None = None,
) -> None:
    # T28-B: only the reviewed grants run the scan; unreviewed = none.
    granted = permissions if permissions is not None else ExecutionPermissions()
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
    project.work_kind = "scan"
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
                plan,
                run_id=run_id,
                owner_instance_id=owner_instance_id,
                permissions=granted,
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
    # T28-B: the reviewed attempt; a newer attempt makes the rescan refuse.
    expected_attempt_id = project.run_id
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
    project.work_kind = "rescan"
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
                project.root,
                baseline_run_id,
                owner_instance_id=owner_instance_id,
                expected_attempt_id=expected_attempt_id,
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
    project.work_kind = "check"
    project.cancel_event.clear()
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
                    lexical_path=project.lexical_path,
                    original_input=project.original_input,
                    cancel_check=project.cancel_event.is_set,
                )
                if actions.run_check_suite
                else None
            )
            if isinstance(res, dict):
                project.results = [cast(ToolResult, res)]
            # T17: a cancelled suite is a terminal cancelled state, never
            # a clean completion.
            cancelled = isinstance(res, dict) and bool(
                (res.get("metadata") or {}).get("cancelled")
            )
            project.status = "cancelled" if cancelled else "complete"
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
    kind = grant["kind"]
    if kind.startswith("project_"):
        _start_project_grant(state, grant)
        return
    if kind == "setup_retry":
        _regenerate_setup_review(state, grant)
        return
    project = state.active_project
    try:
        if kind == "start_scan":
            _start_scan_thread(
                project, actions, _permissions_of(grant.get("_permissions", ()))
            )
        elif kind == "rescan":
            _start_rescan_thread(project, actions)
        elif kind == "setup_apply":
            _start_setup_apply_thread(
                project,
                actions,
                grant["_review"],
                _permissions_of(grant["_permissions"]),
            )
        elif kind == "handoff":
            handoff = actions.build_handoff(
                project.root,
                grant["run_id"],
                grant["agent_id"],
                finding_ids=tuple(grant["finding_ids"]),
            )
            dispatched = actions.dispatch_handoff(
                project.root, handoff.handoff_id, handoff.session_capability
            )
            # The receipt's own state, verbatim: "delivered" is a delivery
            # receipt, never proof of a completed repair.
            receipt = getattr(dispatched, "state", "unknown")
            state.message = f"handoff {receipt}"
            project.last_message = f"handoff {handoff.handoff_id} {receipt}"
    except Exception as exc:  # noqa: BLE001 -- the confirmed, user-approved
        # mutation itself calls injectable Phase65 actions (`build_handoff`/
        # `dispatch_handoff`/scan start/rescan); this is the single point
        # that turns any of their failures into a visible `state.message`
        # instead of crashing the interactive loop mid-render.
        state.message = f"{kind} failed: {exc}"
        project.status = "error"
        if kind == "handoff":
            _mark_agent_unavailable(state, project, grant["agent_id"], exc, actions)


def _permissions_of(names: Any) -> ExecutionPermissions:
    return ExecutionPermissions(**{name: True for name in names})


def _mark_agent_unavailable(
    state: TuiState,
    project: ProjectState,
    agent_id: str | None,
    exc: Exception,
    actions: ScanActions,
) -> None:
    """T28-B: a handoff to an agent absent from the detected agent list is
    its own `unavailable` state (the Agents view), not a generic failure."""
    try:
        known = actions.list_agents()
    except Exception as list_exc:  # noqa: BLE001 -- injectable agent-list
        # seam; unreadable means the agent's availability is unknown.
        known, reason = None, f"agent list unreadable: {list_exc}"
    else:
        reason = f"agent {agent_id} unavailable: {exc}"
    if known is not None and agent_id in known:
        return
    state.views[(project_key(project), "agents")] = SectionView(
        state="unavailable", reason=reason, data={"agent_id": agent_id}
    )
    state.message = reason


def _default_stage_grants(
    project: ProjectState, launch: ExecutionPermissions | None
) -> dict[str, bool]:
    """Per-stage Setup grant toggles: off, except a stage whose every grant
    was already given at launch (`rush ui --allow-*`)."""
    from rush.tools.setup_wizard import STAGE_GRANTS

    given = project.launch_permissions or launch or ExecutionPermissions()
    granted = {name for name, on in given.to_dict().items() if on}
    return {
        stage: bool(grants) and set(grants) <= granted
        for stage, grants in {**STAGE_GRANTS, "engines": ()}.items()
    }


def _build_setup_view(state: TuiState, project: ProjectState) -> None:
    """The resolution-only (`resolve=False`, no network) T26 preview for the
    Setup section, built once and kept on its view; never applied here."""
    from rush.tools import setup_wizard

    view = state.views.setdefault((project_key(project), "setup"), SectionView())
    data = view.data if isinstance(view.data, dict) else {}
    data.setdefault(
        "stage_grants", _default_stage_grants(project, state.launch_permissions)
    )
    view.data = data
    try:
        review = setup_wizard.build_setup_review(
            project.root, state.data_root, resolve=False
        )
        data["review"] = review
        data["review_text"] = setup_wizard.render_setup_review(review)
    except Exception as exc:  # noqa: BLE001 -- the preview reads config,
        # registry and engine state; any failure is shown as a failed view.
        data["review_error"] = str(exc) or type(exc).__name__
        view.state, view.reason = "failed", data["review_error"]
        return
    data.pop("review_error", None)
    view.state, view.reason = "populated", None
    view.loaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _regenerate_setup_review(state: TuiState, grant: Mapping[str, Any]) -> None:
    """Failed-stage retry: a fresh review, never a re-apply of the old one."""
    project = state.active_project
    view = state.views.get((project_key(project), "setup"))
    if view is not None and isinstance(view.data, dict):
        view.data.pop("review", None)
        view.data.pop("review_text", None)
    _build_setup_view(state, project)
    project.setup_apply_events.clear()
    state.message = (
        f"setup stage {grant.get('failed_stage')} failed: review regenerated, "
        "review it and apply again"
    )


def _setup_data(state: TuiState) -> dict[str, Any]:
    """The active project's Setup view data, building the preview first."""
    project = state.active_project
    view = state.views.get((project_key(project), "setup"))
    data = view.data if view is not None and isinstance(view.data, dict) else {}
    if "review" not in data and "review_error" not in data:
        _build_setup_view(state, project)
        data = state.views[(project_key(project), "setup")].data
    return data


def _setup_move(state: TuiState, step: int) -> None:
    data = _setup_data(state)
    count = len(data["stage_grants"])
    data["stage_index"] = (data.get("stage_index", 0) + step) % count


def _setup_toggle_grant(state: TuiState, actions: ScanActions) -> None:
    data = _setup_data(state)
    toggles = data["stage_grants"]
    stage = list(toggles)[data.get("stage_index", 0) % len(toggles)]
    toggles[stage] = not toggles[stage]
    state.message = f"{stage} grant {'on' if toggles[stage] else 'off'}"


def _setup_apply_running(project: ProjectState) -> bool:
    thread = project.setup_apply_thread
    return thread is not None and thread.is_alive()


def _failed_setup_stage(project: ProjectState) -> str | None:
    for stage, status in reversed(project.setup_apply_events):
        if status not in ("started", "completed"):
            return stage
    return None


def _setup_apply_enabled(state: TuiState) -> tuple[bool, str]:
    if _setup_apply_running(state.active_project):
        return False, "setup apply running"
    return True, ""


def _setup_retry_enabled(state: TuiState) -> tuple[bool, str]:
    if _setup_apply_running(state.active_project):
        return False, "setup apply running"
    if _failed_setup_stage(state.active_project) is None:
        return False, "no failed setup stage to retry"
    return True, ""


def _setup_apply_review(state: TuiState, actions: ScanActions) -> None:
    """Review exactly the toggled stages' grants before any apply."""
    data = _setup_data(state)
    review = data.get("review")
    if review is None:
        state.message = f"setup review unavailable: {data.get('review_error')}"
        return
    project = state.active_project
    stages = [stage for stage, on in data["stage_grants"].items() if on]
    grants = sorted({g for s in stages for g in review["grants"].get(s, ())})
    _open_grant(
        state,
        {
            "kind": "setup_apply",
            "project": project.name,
            "root": str(project.root),
            "summary": "Apply the reviewed setup: config, register, configure, "
            "engines.",
            "stages": ", ".join(stages) or "none",
            "grants": ", ".join(grants) or "none",
            "_permissions": tuple(grants),
            "_review": review,
            "_identity": _review_identity(state),
        },
    )


def _setup_retry_review(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    _open_grant(
        state,
        {
            "kind": "setup_retry",
            "project": project.name,
            "root": str(project.root),
            "failed_stage": _failed_setup_stage(project),
            "summary": "Regenerate the setup review; nothing is applied until "
            "the new review is applied.",
        },
    )


def _start_setup_apply_thread(
    project: ProjectState,
    actions: ScanActions,
    review: dict[str, Any],
    permissions: ExecutionPermissions | None = None,
) -> None:
    """Apply a reviewed setup on a worker; each (stage, status) progress
    event is appended to `project.setup_apply_events` in call order. An
    outcome no stage event reports (a missing grant, a stale precondition)
    is appended as `("setup", <status>)`."""
    from rush.tools import setup_wizard

    apply: Callable[..., Any] = setup_wizard.apply_setup_review
    events = project.setup_apply_events
    events.clear()

    def _on_progress(stage: str, status: str) -> None:
        events.append((stage, status))

    def _worker() -> None:
        try:
            result = apply(review, permissions, None, on_progress=_on_progress)
            status = str(result.get("status", "unknown"))
            if status not in ("ok", "partial"):
                events.append(("setup", status))
            project.last_message = f"setup apply {status}"
        except Exception as exc:  # noqa: BLE001 -- setup apply touches
            # config, registry and engine installs; surface, never crash.
            events.append(("setup", "failed"))
            project.last_message = f"setup apply failed: {exc}"

    thread = threading.Thread(target=_worker, daemon=True)
    project.setup_apply_thread = thread
    thread.start()


def _load_scans_section(
    root: Path, project_id: str | None, data_root: Path | None, actions: ScanActions
) -> tuple[str, str | None, Any]:
    """Scans history: every run's terminal manifest via the read-only
    `load_run_manifest`; creates nothing."""
    from rush.workflows.project_run import load_run_manifest

    runs_dir = root / ".rush" / "runs"
    history: list[dict[str, Any]] = []
    try:
        run_ids = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
    except OSError:
        run_ids = []
    for run_id in run_ids:
        manifest = load_run_manifest(root, run_id)
        if manifest is not None:
            history.append(manifest)
    if not history:
        return "empty", "no completed scan runs", {"history": history}
    return "populated", None, {"history": history}


def _scan_history_lines(view: SectionView | None) -> list[Any]:
    """Scans history rows: run id, attempt, status, finished, findings."""
    lines: list[Any] = _view_state_lines("Scan history", view)
    data = view.data if view is not None and isinstance(view.data, Mapping) else {}
    for manifest in data.get("history") or []:
        totals = manifest.get("totals") or {}
        lines.append(
            _safe(
                f"{manifest.get('run_id')}  {manifest.get('attempt_id')}  "
                f"{manifest.get('run_state')}  {manifest.get('created_at')}  "
                f"findings {totals.get('finding_count', 0)}"
            )
        )
    return lines


def _project_grant_worker(grant: Mapping[str, Any], data_root: Path | None) -> Any:
    """The reviewed ProjectTool mutation, then an independent registry
    readback of the resulting record (never the mutation's own echo)."""
    from rush.tools.project import ProjectTool
    from rush.workflows.projects import resolve_project

    kind = grant["kind"]
    permissions = ExecutionPermissions(cache_write=True, artifact_write=True)
    tool = ProjectTool()
    if kind == "project_add":
        result = tool.run(
            Path(grant["root"]),
            action="add",
            permissions=permissions,
            data_root=data_root,
        )
    elif kind == "project_create":
        result = tool.run(
            Path(grant["parent"]),
            action="create",
            name=grant["name"],
            init_git=bool(grant.get("init_git")),
            permissions=permissions,
            data_root=data_root,
        )
    else:
        revision = grant.get("expected_revision")
        result = tool.run(
            Path(grant["new_root"]),
            action="relink",
            project_id=grant.get("project_id"),
            expected_revision=None if revision is None else int(revision),
            permissions=permissions,
            data_root=data_root,
        )
    if result.get("status") != "ok":
        raise RuntimeError(result.get("summary") or f"{kind} failed")
    raw = result.get("raw") or {}
    identifier = raw.get("project_id") if isinstance(raw, Mapping) else None
    readback = identifier or grant.get("project_id") or grant.get("root")
    if not readback:
        raise RuntimeError(f"{kind}: no project id to read back")
    record = resolve_project(str(readback), data_root=data_root)
    if kind == "project_add":
        requested = Path(grant["root"])
    elif kind == "project_create":
        requested = Path(grant["parent"]) / grant["name"]
    else:
        requested = Path(grant["new_root"])
    if Path(record["root"]).resolve() != requested.resolve():
        raise RuntimeError(
            f"{kind} readback root {record['root']} is not the requested {requested}"
        )
    return record


def _start_project_grant(state: TuiState, grant: dict[str, Any]) -> None:
    """Run a confirmed project add/create/relink on a daemon thread; the
    readback is applied by `_drain_results` on a later tick."""
    target = state.active_project if state.projects else None
    data_root = state.data_root
    results = state.result_queue

    def _worker() -> None:
        try:
            payload, ok = _project_grant_worker(grant, data_root), True
        except Exception as exc:  # noqa: BLE001 -- registry/filesystem
            # failures of a user-confirmed mutation are shown in the footer,
            # never raised into the render loop.
            payload, ok = str(exc) or type(exc).__name__, False
        results.put(("grant", grant["kind"], target, ok, payload))

    state.message = f"{grant['kind'].replace('_', ' ')} running"
    threading.Thread(target=_worker, daemon=True).start()


def _apply_project_grant(
    state: TuiState,
    kind: str,
    target: ProjectState | None,
    ok: bool,
    payload: Any,
) -> None:
    label = kind.replace("_", " ")
    if not ok:
        state.message = f"{label} failed: {payload}"
        return
    record = payload
    registration = {
        "state": "ok",
        "reason": None,
        "project_id": record.get("project_id"),
        "revision": record.get("revision"),
    }
    if kind == "project_create" or target is None:
        project = ProjectState(
            name=str(record.get("name") or Path(record["root"]).name),
            root=Path(record["root"]),
            project_id=record.get("project_id"),
            registration=registration,
        )
        if state.projects:
            state.active_project.invalidate()
        state.projects.append(project)
        state.absorb(project)
        state.active_index = len(state.projects) - 1
        state.section = project.section = "overview"
        state.mode = "list"
    else:
        project = target
        if kind == "project_relink":
            project.invalidate()
            project.root = Path(record["root"])
        _apply_registration(state, project, registration)
    state.load_requests.add((project_key(project), "overview"))
    state.message = f"{label} done: {safe_terminal_text(record.get('root'))}"


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
    never overwrites that outcome message with a generic result count.
    Every held preview, selection and edit conflict is dropped first: each was
    built for the row set this refresh replaces."""
    _memory_clear_held(state)
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
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
            session_allowlist=sources,
            **_memory_list_kwargs(state),
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
    if announce:
        state.memory_message = f"{len(state.memory_items)} result(s)"


def _memory_clear_held(state: TuiState) -> None:
    """Drops every held preview, the selection and any edit conflict: each was
    built for the project and row set on screen, which a refresh or a project
    switch replaces."""
    state.memory_pending_mutation = None
    state.memory_pending_maintain = None
    state.memory_pending_delete = None
    state.memory_edit_conflict = None
    state.memory_selected_ids = set()


def _memory_held_for_other_project(state: TuiState, project: ProjectState) -> bool:
    """True, after discarding them, when a held preview was built for a project
    other than `project`: "y" never applies a preview to a different root."""
    held = [
        state.memory_pending_mutation,
        state.memory_pending_delete,
        *(state.memory_pending_maintain or []),
    ]
    active = project_key(project)
    if all(entry is None or entry.get("project_key") == active for entry in held):
        return False
    _memory_clear_held(state)
    state.memory_message = (
        "held preview was built for another project -- discarded, 0 records written"
    )
    return True


_MEMORY_FILTER_FIELDS = ("trust", "source", "freshness", "archived", "owner")
_MEMORY_PAGE_ROWS = 20


def _memory_filter_values(state: TuiState) -> dict[str, str]:
    """Each filter as the form edits and the render shows it ("" = unset)."""
    return {
        "trust": state.memory_filter_trust or "",
        "source": state.memory_filter_source or "",
        "freshness": state.memory_filter_freshness or "",
        "archived": "true" if state.memory_filter_archived else "",
        "owner": state.memory_filter_owner or "",
    }


def _memory_list_kwargs(state: TuiState) -> dict[str, Any]:
    """The `list` call's query and filters. No query is sent when none is typed,
    so entering Memory browses every row instead of requiring a search."""
    kwargs: dict[str, Any] = {}
    query = state.memory_query_buffer.strip()
    if query:
        kwargs["query"] = query
    for key, value in (
        ("trust_filter", state.memory_filter_trust),
        ("source_filter", state.memory_filter_source),
        ("freshness_filter", state.memory_filter_freshness),
        ("owner_filter", state.memory_filter_owner),
    ):
        if value is not None:
            kwargs[key] = value
    if state.memory_filter_archived:
        kwargs["archived_filter"] = True
    return kwargs


def _memory_targets(state: TuiState) -> list[dict[str, Any]]:
    """The rows archive/promote/delete act on: every space-selected row (in list
    order) when any is selected, otherwise the cursor row."""
    if state.memory_selected_ids:
        return [
            item
            for item in state.memory_items
            if item.get("id") in state.memory_selected_ids
        ]
    item = _memory_selected_item(state)
    return [] if item is None else [item]


def _memory_row_owner(
    state: TuiState, artifact_id: str, fallback: dict[str, Any] | None
) -> str:
    """`kind:id` of a listed row's own owner, else the owner the preview used."""
    scope = next(
        (
            item["owner_scope"]
            for item in state.memory_items
            if item.get("id") == artifact_id
            and isinstance(item.get("owner_scope"), dict)
        ),
        fallback or {},
    )
    return f"{scope.get('kind')}:{scope.get('id')}"


_MEMORY_OWNER_SCOPE_KINDS = ("project", "user", "session", "agent")


def _tui_session_owner_scope_id() -> str | None:
    """This standalone TUI invocation's `session`-kind owner id (P69-07 subsection b).

    A `rush ui` run with no dashboard server never creates a `DashboardAuth` session, so
    there is no browser session id to reuse. This process's own invocation identity
    (`_tui_owner_instance_id()`, minted once per process) is that identity: non-secret,
    already scoped to exactly this invocation, and never an authentication credential.
    `None` when the owner lifetime lock could not be acquired (no identity exists).
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
    invocation's session id, with no default when the owner lifetime lock is unavailable.
    `user`/`agent` are opaque and have no derivable default."""
    if kind == "project":
        return project.project_id or str(project.root)
    if kind == "session":
        return _tui_session_owner_scope_id() or ""
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
    denied (`insufficient_corroboration`), matching the CLI/MCP behavior.
    Acts on every targeted row (`_memory_targets`); one row's refused preview
    holds nothing at all."""
    items = _memory_targets(state)
    if not items or actions.memory_run is None:
        state.memory_message = "no row selected"
        return
    pending = state.memory_pending_promote or {}
    state.memory_pending_promote = None
    held: list[dict[str, Any]] = []
    for item in items:
        state.memory_pending_mutation = None
        _memory_write_preview(
            state,
            project,
            actions,
            "promote",
            "promote",
            list(pending.get("required_grants") or []),
            subject=state.memory_subject,
            content=item.get("content") or {},
            source=item.get("source", ""),
            symbol_ref=item.get("symbol_ref"),
            source_kind="local_tool",
            user_stated=False,
            candidate_sources=[item.get("source", "")],
        )
        if state.memory_pending_mutation is None:
            return  # the refusal message is already set; nothing is held
        held.append(state.memory_pending_mutation)
    state.memory_pending_mutation = {
        **held[0],
        "items": items,
        "calls": [call for entry in held for call in entry["calls"]],
        "drafts": [draft for entry in held for draft in entry["drafts"]],
        "consequences": [c for entry in held for c in entry["consequences"]],
        "required_grants": sorted(
            {g for entry in held for g in entry["required_grants"]}
        ),
        "ids": [item["id"] for item in items],
        "versions": {item["id"]: item.get("artifact_version") for item in items},
    }
    state.memory_message = _memory_pending_mutation_text(state.memory_pending_mutation)


def _memory_write_preview(
    state: TuiState,
    project: ProjectState,
    actions: ScanActions,
    operation: str,
    verb: str,
    grants: list[str],
    **fields: Any,
) -> None:
    """Preview a memory write with the requested grants, refuse on a non-ok
    preview or missing grants, else hold it for "y" with the grants the preview
    actually reported as required (never the caller's raw guess)."""
    if actions.memory_run is None:
        state.memory_message = "memory backend unavailable"
        return
    requested = sorted({"cache_write", *grants})
    try:
        preview = actions.memory_run(
            project.root,
            operation=operation,
            owner_scope=_memory_owner_scope(state, project),
            request={"apply": False, "required_grants": requested},
            permissions=ExecutionPermissions(**{g: True for g in requested}),
            **fields,
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"{operation} preview failed: {exc}"
        return
    praw = preview.get("raw") or {}
    if preview.get("status", "ok") != "ok" or praw.get("missing_grants"):
        state.memory_message = (
            f"{operation} preview refused: "
            f"{praw.get('message') or praw.get('missing_grants')}"
        )
        return
    reviewed = list(praw.get("required_grants") or requested)
    owner_scope = _memory_owner_scope(state, project)
    draft = praw.get("draft")
    state.memory_pending_mutation = {
        "operation": operation,
        "verb": verb,
        "items": [],
        "calls": [
            {
                "operation": operation,
                "owner_scope": owner_scope,
                "request": {"apply": True, "required_grants": reviewed},
                **fields,
            }
        ],
        "drafts": [draft] if isinstance(draft, dict) and draft else [],
        "consequences": [str(preview.get("summary") or "")],
        "required_grants": reviewed,
        "ids": list(praw.get("target_ids") or []),
        "versions": dict(praw.get("expected_revisions") or {}),
        "owner_scope": praw.get("owner_scope") or owner_scope,
        "project_key": project_key(project),
    }
    state.memory_message = _memory_pending_mutation_text(state.memory_pending_mutation)


def _memory_create_commit(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """Validate required fields, then preview a `write` via
    `_memory_write_preview` and hold it for "y" so create shares the same reviewed-grants
    path as every other mutating form."""
    buf = state.memory_create_buffer or {}
    missing = [
        f for f in ("subject", "source", "content") if not (buf.get(f) or "").strip()
    ]
    if missing:
        state.memory_message = f"required: {', '.join(missing)}"
        return
    subjects = get_args(MemorySubject)
    if buf["subject"] not in subjects:
        state.memory_message = (
            f"unknown subject {buf['subject']!r}; valid subjects: {', '.join(subjects)}"
        )
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    _memory_write_preview(
        state,
        project,
        actions,
        "write",
        "propose",
        [],
        subject=buf["subject"],
        content={"note": buf["content"]},
        source=buf["source"],
        symbol_ref=None,
        source_kind="local_tool",
    )
    if state.memory_pending_mutation is not None:
        state.mode = "memory"  # "y"/"n"/Esc are read by _handle_memory_key


def _handle_memory_create_key(state: TuiState, key: str, actions: ScanActions) -> None:
    if key == "escape":
        state.mode = "memory"
        state.memory_create_buffer = None
        state.memory_message = "create cancelled -- 0 records written"
        return
    if key == "tab":
        fields = ("subject", "source", "content")
        idx = (
            fields.index(state.memory_create_field)
            if state.memory_create_field in fields
            else 0
        )
        state.memory_create_field = fields[(idx + 1) % len(fields)]
        return
    if key == "enter":
        _memory_create_commit(state, state.active_project, actions)
        return
    buf = state.memory_create_buffer or {}
    current = buf.get(state.memory_create_field, "")
    if key == "backspace":
        buf[state.memory_create_field] = current[:-1]
    elif len(key) == 1 and key.isprintable():
        buf[state.memory_create_field] = current + key
    state.memory_create_buffer = buf


def _memory_delete_preview(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    items = _memory_targets(state)
    if not items:
        state.memory_message = "select a row before delete"
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    ids = sorted(item["id"] for item in items)
    revisions = {item["id"]: item["artifact_version"] for item in items}
    owner_scope = _memory_owner_scope(state, project)
    # Reviewed grants: cache_write (required, memory.py:2568) and artifact_write (unlinks handoff blobs, memory.py:2616) -- the same pair the apply used to hardcode.
    grants = ["cache_write", "artifact_write"]
    try:
        result = actions.memory_run(
            project.root,
            operation="delete",
            request={
                "artifact_ids": ids,
                "expected_revisions": revisions,
                "scope": state.memory_subject,
                "owner_scope": owner_scope,
                "required_grants": grants,
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
        "required_grants": grants,
        "affected": (data or {}).get("affected", []),
        "project_key": project_key(project),
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
                "required_grants": pending["required_grants"],
                "apply": True,
            },
            permissions=ExecutionPermissions(
                **{grant: True for grant in pending["required_grants"]}
            ),
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


def _memory_archive_selected(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """T28-D: archive/restore share one form, over every targeted row
    (`_memory_targets`); a row with `archived_at` set is restored, any other
    archived. Each row previews (apply=False) with its own id, expected_version,
    owner_scope and required_grants; only when every preview is OK is the set
    held for "y", which applies each with exactly those grants."""
    items = _memory_targets(state)
    if not items:
        state.memory_message = "select a row before archive/restore"
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    grants = ["cache_write"]
    owner_scope = _memory_owner_scope(state, project)
    calls: list[dict[str, Any]] = []
    for item in items:
        archived = not item.get("archived_at")
        verb = "archive" if archived else "restore"
        request: dict[str, Any] = {
            "scope": state.memory_subject,
            "id": item["id"],
            "expected_version": item["artifact_version"],
            "owner_scope": owner_scope,
            "archived": archived,
            "required_grants": grants,
            "apply": False,
        }
        try:
            preview = actions.memory_run(
                project.root, operation="archive", request=request
            )
        except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
            state.memory_message = f"{verb} preview failed: {exc}"
            return
        raw = preview.get("raw") or {}
        if raw.get("code") != "OK":
            state.memory_message = (
                f"{verb} preview refused: {item['id']}: "
                f"{(raw.get('data') or {}).get('message') or raw.get('code') or 'no result'}"
            )
            return
        calls.append({"operation": "archive", "request": {**request, "apply": True}})
    verbs = {"archive" if call["request"]["archived"] else "restore" for call in calls}
    state.memory_pending_mutation = {
        "operation": "archive",
        "verb": "/".join(sorted(verbs)),
        "items": items,
        "calls": calls,
        "drafts": [],
        "consequences": [],
        "required_grants": grants,
        "ids": [item["id"] for item in items],
        "versions": {item["id"]: item["artifact_version"] for item in items},
        "owner_scope": owner_scope,
        "project_key": project_key(project),
    }
    state.memory_message = _memory_pending_mutation_text(state.memory_pending_mutation)


def _memory_maintain_preview(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """T28-D: read-only preview of every maintenance task; 'y' applies exactly
    the previewed candidate IDs at their previewed versions with the reviewed
    grants, 'n'/'esc' cancels. A corrupt or busy store shows its read-only
    reason instead of any preview."""
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    _sources, store_state = _memory_sources_and_state(project)
    if store_state in ("corrupt", "busy"):
        from rush.memory.store import readonly_view_reason

        state.memory_message = (
            f"maintenance unavailable -- {store_state}: "
            f"{readonly_view_reason(store_state)}"
        )
        return
    owner_scope = _memory_owner_scope(state, project)
    pending: list[dict[str, Any]] = []
    for task in get_args(MaintenanceTask):
        try:
            result = actions.memory_run(
                project.root,
                operation="maintain",
                task=task,
                owner_scope=owner_scope,
                request={"apply": False, "required_grants": ["cache_write"]},
            )
        except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
            state.memory_message = f"maintenance preview failed: {exc}"
            return
        if result.get("status") == "error":
            state.memory_message = (
                f"maintenance preview failed: {result.get('summary')}"
            )
            return
        raw = result.get("raw") or {}
        pending.append(
            {
                "task": task,
                "owner_scope": owner_scope,
                "candidate_ids": list(raw.get("candidate_ids") or []),
                "expected_revisions": dict(raw.get("expected_revisions") or {}),
                "required_grants": list(raw.get("required_grants") or ["cache_write"]),
                "consequence": str(result.get("summary") or ""),
                "project_key": project_key(project),
            }
        )
    state.memory_pending_maintain = pending
    counts = ", ".join(f"{p['task']} {len(p['candidate_ids'])}" for p in pending)
    state.memory_message = (
        f"maintenance preview: {counts} -- [y] apply, [n]/[esc] cancel"
    )


def _memory_maintain_apply(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    pending = state.memory_pending_maintain
    state.memory_pending_maintain = None
    if pending is None:
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    summaries: list[str] = []
    for entry in pending:
        if not entry["candidate_ids"]:
            continue  # nothing previewed for this task: nothing to apply
        try:
            result = actions.memory_run(
                project.root,
                operation="maintain",
                task=entry["task"],
                owner_scope=entry["owner_scope"],
                permissions=_permissions_of(entry["required_grants"]),
                request={
                    "apply": True,
                    "required_grants": entry["required_grants"],
                    "candidate_ids": entry["candidate_ids"],
                    **(
                        {"expected_revisions": entry["expected_revisions"]}
                        if entry["expected_revisions"]
                        else {}
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
            summaries.append(f"{entry['task']} failed: {exc}")
            continue
        raw = result.get("raw") or {}
        refused = [
            f"{c.get('id')} changed v{c.get('expected')} -> "
            + ("deleted" if c.get("actual") is None else f"v{c.get('actual')}")
            for c in raw.get("refused") or []
            if isinstance(c, dict)
        ]
        outcome = (
            f"changed {raw.get('changed', 0)}"
            if refused
            else result.get("summary") or result.get("status")
        )
        summaries.append("; ".join([f"{entry['task']}: {outcome}", *refused]))
    state.memory_message = "; ".join(summaries) or "maintenance: nothing to apply"
    _memory_refresh(state, project, actions, announce=False)


def _memory_pending_mutation_text(pending: dict[str, Any]) -> str:
    owner = pending.get("owner_scope") or {}
    target = (
        f"ids {pending['ids']} versions {pending['versions']}"
        if pending["ids"]
        else "new record"
    )
    return (
        f"{pending['verb']} preview: {target} "
        f"owner {owner.get('kind')}:{owner.get('id')} "
        f"grants {pending['required_grants']} -- [y] apply, [n]/[esc] cancel"
    )


def _memory_edit_outcome(
    state: TuiState,
    project: ProjectState,
    actions: ScanActions,
    item: dict[str, Any],
    code: Any,
) -> None:
    """Shared by the edit preview (non-OK) and the confirmed apply. OK clears
    the buffer and refreshes; E_VERSION records `memory_edit_conflict` for
    `_memory_edit_refresh_and_rereview` (never a blind retry); any other code
    keeps the entered content."""
    if code == "OK":
        state.memory_message = "edit applied"
        state.memory_edit_buffer = None
        state.memory_edit_conflict = None
        _memory_refresh(state, project, actions, announce=False)
        return
    if code == "E_VERSION":
        state.memory_edit_conflict = {
            "id": item["id"],
            "expected_version": item["artifact_version"],
        }
        state.memory_message = (
            f"edit conflict on {item['id']} v{item['artifact_version']} -- "
            "[r] refresh and re-review"
        )
        return
    state.memory_message = f"edit denied: {code}"


def _memory_mutation_apply(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """T28-D confirm step ("y"): apply exactly the held preview's calls (one per
    previewed row) with the grants that preview reviewed, then report each
    row's own outcome, naming the version an archive/restore committed."""
    pending = state.memory_pending_mutation
    state.memory_pending_mutation = None
    if pending is None:
        return
    if actions.memory_run is None:
        state.memory_message = "memory operations unavailable"
        return
    verb = pending["verb"]
    operation = pending["operation"]
    permissions = _permissions_of(pending["required_grants"])
    messages: list[str] = []
    refresh = False
    for index, call in enumerate(pending["calls"]):
        try:
            result = actions.memory_run(project.root, **call, permissions=permissions)
        except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
            messages.append(f"{verb} failed: {exc}")
            continue
        raw = result.get("raw") or {}
        if operation == "edit":
            _memory_edit_outcome(
                state, project, actions, pending["items"][0], raw.get("code")
            )
            return
        if operation == "archive":
            item_id = pending["items"][index]["id"]
            row_verb = "archive" if call["request"]["archived"] else "restore"
            data = raw.get("data") or {}
            if raw.get("code") == "OK":
                revision = data.get("revision")
                committed = "" if revision is None else f" (v{revision})"
                messages.append(f"{row_verb}d {item_id}{committed}")
                refresh = True
            else:
                messages.append(
                    f"{row_verb} refused: {item_id}: "
                    f"{data.get('message') or raw.get('code') or 'no result'}"
                )
        elif operation == "promote":
            item_id = pending["items"][index]["id"]
            if raw.get("promoted"):
                messages.append(f"{item_id} promoted to {raw.get('new_tier')}")
            else:
                messages.append(
                    f"{item_id} promotion denied: {raw.get('denial_reason')}"
                )
        elif result.get("status", "ok") == "ok":
            state.memory_create_buffer = None
            state.mode = "memory"
            messages.append(f"proposed {raw.get('id')}")
            refresh = True
        else:
            messages.append(
                f"write refused: {raw.get('message') or result.get('summary')}"
            )
    state.memory_message = "; ".join(messages)
    if refresh:
        _memory_refresh(state, project, actions, announce=False)


def _memory_edit_commit(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """T28-D: previews the edit (apply=False) carrying id, expected_version,
    owner_scope and required_grants, and holds the OK preview in
    `memory_pending_mutation`; "y" applies it with exactly those reviewed grants. Any non-OK result
    keeps the entered content; E_VERSION also records `memory_edit_conflict`
    for `_memory_edit_refresh_and_rereview` -- never a blind retry."""
    item = _memory_selected_item(state)
    if item is None or state.memory_edit_buffer is None or actions.memory_run is None:
        return
    grants = ["cache_write"]
    request = {
        "scope": state.memory_subject,
        "id": item["id"],
        "expected_version": item["artifact_version"],
        "content": {
            **(item.get("content") or {}),
            state.memory_edit_field: state.memory_edit_buffer,
        },
        "owner_scope": _memory_owner_scope(state, project),
        "required_grants": grants,
    }
    try:
        preview = actions.memory_run(
            project.root, operation="edit", request={**request, "apply": False}
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"edit failed: {exc}"
        return
    code = (preview.get("raw") or {}).get("code")
    if code != "OK":
        _memory_edit_outcome(state, project, actions, item, code)
        return
    state.memory_pending_mutation = {
        "operation": "edit",
        "verb": "edit",
        "items": [item],
        "calls": [{"operation": "edit", "request": {**request, "apply": True}}],
        "drafts": [],
        "consequences": [],
        "required_grants": grants,
        "ids": [item["id"]],
        "versions": {item["id"]: item["artifact_version"]},
        "owner_scope": request["owner_scope"],
        "project_key": project_key(project),
    }
    state.memory_message = _memory_pending_mutation_text(state.memory_pending_mutation)


def _memory_edit_refresh_and_rereview(
    state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """T28-D conflict recovery: re-fetch the conflicted row, replace the
    stale copy in `memory_items`, and reopen the editor with the kept
    content for review. Never re-submits."""
    conflict = state.memory_edit_conflict
    if conflict is None or actions.memory_run is None:
        return
    try:
        result = actions.memory_run(
            project.root,
            operation="list",
            subject=state.memory_subject,
            session_allowlist=_memory_known_sources(project),
            **_memory_list_kwargs(state),
        )
    except Exception as exc:  # noqa: BLE001 -- see _memory_refresh
        state.memory_message = f"refresh failed: {exc}"
        return
    rows = result.get("raw") if result.get("status") == "ok" else None
    fresh = next(
        (
            row
            for row in rows or []
            if isinstance(row, dict) and row.get("id") == conflict["id"]
        ),
        None,
    )
    if fresh is None:
        state.memory_message = f"{conflict['id']} not found on refresh"
        return
    ids = [row.get("id") for row in state.memory_items]
    if conflict["id"] in ids:
        index = ids.index(conflict["id"])
        state.memory_items[index] = fresh
    else:
        state.memory_items.append(fresh)
        index = len(state.memory_items) - 1
    state.memory_selected_index = index
    state.memory_edit_conflict = None
    state.mode = "memory_edit"
    state.memory_message = (
        f"refreshed {conflict['id']} to v{fresh.get('artifact_version')} -- "
        "review, then Enter to submit"
    )


def _handle_memory_key(state: TuiState, key: str, actions: ScanActions) -> None:
    project = state.active_project
    if key in ("n", "escape") and state.memory_pending_mutation is not None:
        verb = state.memory_pending_mutation["verb"]
        state.memory_pending_mutation = None
        state.memory_message = f"{verb} cancelled -- 0 records written"
        return
    if key in ("n", "escape") and state.memory_pending_maintain is not None:
        state.memory_pending_maintain = None
        state.memory_message = "maintenance cancelled"
        return
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
    if key == "n":
        state.mode = "memory_create"
        state.memory_create_field = "content"
        state.memory_create_buffer = {
            "subject": state.memory_subject,
            "source": "tui",
            "content": "",
        }
        state.memory_message = (
            "new memory: [tab] field  [enter] preview+submit  [esc] cancel"
        )
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
    if key in ("]", "["):
        if state.memory_items:
            page = state.memory_selected_index // _MEMORY_PAGE_ROWS
            page += 1 if key == "]" else -1
            if 0 <= page * _MEMORY_PAGE_ROWS < len(state.memory_items):
                state.memory_selected_index = page * _MEMORY_PAGE_ROWS
        return
    if key == "f":
        state.mode = "memory_filter"
        state.memory_filter_field = _MEMORY_FILTER_FIELDS[0]
        state.memory_filter_buffer = _memory_filter_values(state)
        state.memory_message = "filters: [tab] field  [enter] apply  [esc] cancel"
        return
    if key == "S":
        subjects = list(get_args(MemorySubject))
        current = state.memory_subject
        index = subjects.index(current) if current in subjects else -1
        state.memory_subject = subjects[(index + 1) % len(subjects)]
        _memory_refresh(state, project, actions)
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
    if key == "r" and state.memory_edit_conflict is not None:
        _memory_edit_refresh_and_rereview(state, project, actions)
        return
    if key == "e":
        if _memory_selected_item(state) is not None:
            state.mode = "memory_edit"
            state.memory_edit_buffer = ""
            state.memory_edit_field = "note"
            state.memory_edit_conflict = None
        return
    if key == "o":
        state.mode = "memory_owner"
        state.memory_owner_buffer = state.memory_owner_scope_id or (
            _default_owner_scope_id(state.memory_owner_scope_kind, project)
        )
        return
    if key == "a":
        _memory_archive_selected(state, project, actions)
        return
    if key == "d":
        _memory_delete_preview(state, project, actions)
        return
    if key == "w":
        _memory_maintain_preview(state, project, actions)
        return
    if key == "y":
        if _memory_held_for_other_project(state, project):
            return
        if state.memory_pending_mutation is not None:
            _memory_mutation_apply(state, project, actions)
        elif state.memory_pending_maintain is not None:
            _memory_maintain_apply(state, project, actions)
        else:
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


def _handle_memory_filter_key(state: TuiState, key: str, actions: ScanActions) -> None:
    """T28-D: the "f" filter form. Tab cycles `_MEMORY_FILTER_FIELDS`, typed text
    edits the field under the cursor, Enter applies every field (empty = unset)
    and refreshes, Escape discards the form and keeps the active filters."""
    buf = state.memory_filter_buffer or _memory_filter_values(state)
    if key == "escape":
        state.mode = "memory"
        state.memory_filter_buffer = None
        state.memory_message = "filter cancelled"
        return
    if key == "tab":
        fields_ = _MEMORY_FILTER_FIELDS
        index = (
            fields_.index(state.memory_filter_field)
            if state.memory_filter_field in fields_
            else -1
        )
        state.memory_filter_field = fields_[(index + 1) % len(fields_)]
        return
    if key == "enter":
        archived = buf["archived"].strip().lower()
        if archived not in ("", "true", "false"):
            state.memory_message = "archived filter takes true or false"
            return
        state.memory_filter_trust = buf["trust"].strip() or None
        state.memory_filter_source = buf["source"].strip() or None
        state.memory_filter_freshness = buf["freshness"].strip() or None
        state.memory_filter_archived = archived == "true"
        state.memory_filter_owner = buf["owner"].strip() or None
        state.memory_filter_buffer = None
        state.mode = "memory"
        _memory_refresh(state, state.active_project, actions)
        return
    current = buf.get(state.memory_filter_field, "")
    if key == "backspace":
        buf[state.memory_filter_field] = current[:-1]
    elif len(key) == 1 and key.isprintable():
        buf[state.memory_filter_field] = current + key
    state.memory_filter_buffer = buf


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
    if key == "tab":
        item = _memory_selected_item(state)
        fields = sorted({*((item or {}).get("content") or {}), "note"})
        position = (
            fields.index(state.memory_edit_field)
            if state.memory_edit_field in fields
            else -1
        )
        state.memory_edit_field = fields[(position + 1) % len(fields)]
        return
    if key == "backspace":
        state.memory_edit_buffer = (state.memory_edit_buffer or "")[:-1]
        return
    if len(key) == 1 and key.isprintable():
        state.memory_edit_buffer = (state.memory_edit_buffer or "") + key


def _has_running_work(project: ProjectState) -> bool:
    return project.status in ("scanning", "cancelling")


def _reload_after_finished_work(state: TuiState, seen: dict[int, str]) -> bool:
    """True when any project's status changed since the last tick (the
    screen must redraw, also under reduced motion). Work that just finished
    reloads the views it changed: Overview, Tokens and scan history."""
    changed = False
    for project in state.projects:
        before = seen.get(id(project))
        if before == project.status:
            continue
        changed = True
        seen[id(project)] = project.status
        if before in ("scanning", "cancelling") and not _has_running_work(project):
            for section in ("overview", "tokens", "scans"):
                state.load_requests.add((project_key(project), section))
    return changed


def _request_cancel(project: ProjectState, actions: ScanActions) -> None:
    """Send the cooperative-cancel marker for `project`'s active run.
    Shared by the plain 'cancel_scan' key and Cancel-run-and-stay (P69-06g) --
    both send the identical request; they differ only in what happens to the
    TUI process afterward.

    T28-B: dispatched by `project.work_kind` -- a check observes
    `cancel_event` (forwarded as `run_workflow_suite`'s `cancel_check`), a
    scan/rescan uses the run's marker-file cancel, and dashboard-owned work
    is cancelled by the owning server's own `cancel` operation."""
    if project.status != "scanning":
        return
    kind = project.work_kind
    if kind == "check":
        project.cancel_event.set()
        project.status = "cancelling"
        return
    try:
        if kind == "dashboard" or (kind is None and project.owner == "dashboard"):
            owner = _dashboard_owner_for(project, actions)
            if owner is None:
                project.last_message = "cancel failed: dashboard owner not reachable"
                return
            owner.dispatch(
                "cancel", run_id=project.run_id or "", operation_id=project.operation_id
            )
            project.status = "cancelling"
            return
        if not project.run_id:
            return
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


# --------------------------------------------------------------------------
# T28-A X7: section loads run on a daemon thread and post to
# `state.result_queue`; the loop's per-tick `_pump` drains it and applies only
# results for the project's current outstanding request. Dispatch and render
# only ever add to `state.load_requests` -- neither does load I/O itself.
# --------------------------------------------------------------------------

LoadOutcome = tuple[str, str | None, Any]  # (section state, reason, data)


def _load_overview_section(
    root: Path, project_id: str | None, data_root: Path | None, actions: ScanActions
) -> LoadOutcome:
    if actions.load_overview is None:
        return "unavailable", "no overview loader configured", None
    data = actions.load_overview(root, project_id=project_id, data_root=data_root)
    return "populated", None, data


def _load_tokens_section(
    root: Path, project_id: str | None, data_root: Path | None, actions: ScanActions
) -> LoadOutcome:
    if project_id is None:
        return "unavailable", "project not registered", None
    from rush.workflows.projects import project_token_usage

    return "populated", None, project_token_usage(project_id, data_root=data_root)


def _load_artifacts_section(
    root: Path, project_id: str | None, data_root: Path | None, actions: ScanActions
) -> LoadOutcome:
    if project_id is None:
        return "unavailable", "project not registered", None
    from rush.workflows.projects import list_project_artifacts

    data = list_project_artifacts(project_id, data_root=data_root)
    lists = [v for v in data.values() if isinstance(v, list)]
    if lists and not any(lists):
        return "empty", "no artifacts recorded yet", data
    return "populated", None, data


def _load_setup_section(
    root: Path, project_id: str | None, data_root: Path | None, actions: ScanActions
) -> LoadOutcome:
    agents = actions.list_agents()
    if not agents:
        return "empty", "no agents detected", agents
    return "populated", None, agents


_SECTION_LOADERS: dict[
    str, Callable[[Path, str | None, Path | None, ScanActions], LoadOutcome]
] = {
    "overview": _load_overview_section,
    "scans": _load_scans_section,
    "tokens": _load_tokens_section,
    "artifacts": _load_artifacts_section,
    "setup": _load_setup_section,
}


def _submit(
    state: TuiState, project: ProjectState, section: str, actions: ScanActions
) -> None:
    """Start one background section load for `project`; its post carries the
    request generation and project identity `_drain_results` checks."""
    loader = _SECTION_LOADERS[section]
    if section == "overview" and actions.load_overview is None:
        # No loader: the outcome needs no I/O, so it is set now, not posted.
        state.views[(project_key(project), section)] = SectionView(
            state="unavailable", reason="no overview loader configured"
        )
        return
    generation = project.begin_request(section)
    identity = project.identity()
    key = (project_key(project), section)
    if key not in state.views:
        state.views[key] = SectionView(state="loading", generation=generation)
    args = (project.root, project.project_id, state.data_root, actions)
    results = state.result_queue

    def _worker() -> None:
        try:
            payload: Any = loader(*args)
            ok = True
        except Exception as exc:  # noqa: BLE001 -- a loader's failure space
            # (registry, SQLite, Git, injected seams) is open-ended; it is
            # posted and rendered as a failed/stale section, never raised
            # into the render loop.
            payload, ok = str(exc) or type(exc).__name__, False
        results.put((project, section, generation, identity, ok, payload))

    threading.Thread(target=_worker, daemon=True).start()


def _apply_registration(
    state: TuiState, project: ProjectState, registration: Mapping[str, Any]
) -> None:
    """Record the Overview's registry state; a newly learned project id
    re-keys this project's views and re-requests its outstanding loads."""
    deferred = (project.registration or {}).get("deferred")
    project.registration = {**registration, **({"deferred": True} if deferred else {})}
    new_id = registration.get("project_id")
    if not new_id or new_id == project.project_id:
        return
    old_key = project_key(project)
    project.project_id = new_id
    new_key = project_key(project)
    for pkey, section in [k for k in state.views if k[0] == old_key]:
        state.views[(new_key, section)] = state.views.pop((pkey, section))
    for section in list(project.pending):
        if section in _SECTION_LOADERS:
            state.load_requests.add((new_key, section))
    project.pending.clear()


def _drain_results(state: TuiState) -> bool:
    """Apply every accepted post; True when anything visible changed."""
    applied = False
    while True:
        try:
            post = state.result_queue.get_nowait()
        except queue.Empty:
            return applied
        if isinstance(post[0], str):  # ("grant", kind, target, ok, payload)
            _apply_project_grant(state, *post[1:])
            applied = True
            continue
        project, section, generation, identity, ok, payload = post
        if not any(p is project for p in state.projects):
            continue
        if not project.accepts(section, generation, identity):
            continue  # superseded, switched away, or identity changed
        del project.pending[section]
        applied = True
        if ok and section == "overview" and isinstance(payload[2], Mapping):
            registration = payload[2].get("registration")
            if isinstance(registration, Mapping):
                _apply_registration(state, project, registration)
        key = (project_key(project), section)
        prior = state.views.get(key)
        if ok:
            view_state, reason, data = payload
            if (
                section == "setup"
                and prior is not None
                and isinstance(prior.data, dict)
            ):
                data = {**prior.data, "agents": data}
                view_state = prior.state if "review" in prior.data else view_state
            state.views[key] = SectionView(
                state=view_state,
                reason=reason,
                data=data,
                loaded_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                generation=generation,
            )
        elif prior is not None and prior.data is not None:
            prior.state = "stale"
            prior.reason = f"refresh failed: {payload}"
        else:
            state.views[key] = SectionView(
                state="failed", reason=str(payload), generation=generation
            )


def _pump(state: TuiState, actions: ScanActions) -> bool:
    """One loop tick: apply finished loads, then start requested ones. A
    section already loading is not started again (F5 cannot pile up
    threads). True when a result was applied, so the screen must redraw."""
    applied = _drain_results(state)
    requests, state.load_requests = state.load_requests, set()
    for pkey, section in requests:
        for project in state.projects:
            if project_key(project) == pkey and section in _SECTION_LOADERS:
                if section not in project.pending:
                    _submit(state, project, section, actions)
                break
    return applied


def _handle_grant_review_key(state: TuiState, key: str, actions: ScanActions) -> None:
    grant = state.pending_grant
    state.pending_grant = None
    state.mode = "list"
    if key == "y" and grant is not None:
        if "_identity" in grant and grant["_identity"] != _review_identity(state):
            # T28-B: the project, attempt or source changed after review --
            # the review no longer describes the effect, so nothing runs.
            state.message = f"{grant['kind']} review is stale; nothing was run"
            return
        _execute_grant(state, grant, actions)
    else:
        state.message = "declined"


def _handle_project_selector_key(
    state: TuiState, key: str, actions: ScanActions
) -> None:
    """U01 fix: F2's overlay -- Up/Down/j/k move the highlight, Enter
    confirms the actual project switch (the only place `active_index`
    changes here), Escape cancels back with no switch at all. T28-A: the
    outgoing project's outstanding requests are invalidated, and the
    incoming project returns to its own last section."""
    rows = len(state.projects) + len(_SELECTOR_EXTRAS)
    if key in ("down", "j"):
        state.project_selector_index = (state.project_selector_index + 1) % rows
    elif key in ("up", "k"):
        state.project_selector_index = (state.project_selector_index - 1) % rows
    elif key == "enter" and state.project_selector_index >= len(state.projects):
        state.mode = "list"
        extra = state.project_selector_index - len(state.projects)
        _run_action(state, _ACTIONS_BY_ID[_SELECTOR_EXTRAS[extra][0]], actions)
    elif key == "enter":
        if state.project_selector_index != state.active_index:
            state.active_project.invalidate()
        state.active_index = state.project_selector_index
        state.memory_items = []
        _memory_clear_held(state)
        state.memory_expanded = None
        state.memory_message = ""
        state.git_data = None
        state.git_message = ""
        state.mode = "list"
        _enter_section(state, state.active_project.section, actions)
    elif key == "escape":
        state.mode = "list"


def _enter_section(state: TuiState, section: str, actions: ScanActions) -> None:
    project = state.active_project
    state.section = project.section = section
    state.nav_index = SECTIONS.index(section)
    state.mode = _SECTION_MODES.get(section, "list")
    if section == "git":
        _load_git_view(state, project, actions)
    elif section == "memory":
        _memory_refresh(state, project, actions)
    elif section in _SECTION_LOADERS:
        state.load_requests.add((project_key(project), section))


def _sync_section(state: TuiState) -> None:
    if state.mode in _SECTION_MODES.values() or state.mode.startswith("memory"):
        state.section = "memory" if state.mode.startswith("memory") else state.mode
    elif state.mode == "list" and state.section in _SECTION_MODES:
        state.section = "overview"
    if state.projects:
        state.active_project.section = state.section
    if state.overlay not in ("sections", "form"):
        state.overlay = _MODE_OVERLAYS.get(state.mode)


def _chooser_rows() -> list[tuple[str, str]]:
    return [(f"section:{s}", SECTION_LABELS[s]) for s in SECTIONS] + list(
        _CHOOSER_EXTRAS
    )


def _handle_section_chooser_key(
    state: TuiState, key: str, actions: ScanActions
) -> None:
    rows = _chooser_rows()
    if key in [str(i) for i in range(1, len(SECTIONS) + 1)]:
        state.overlay = None
        _enter_section(state, SECTIONS[int(key) - 1], actions)
    elif key == "f3":
        state.chooser_index = (state.chooser_index + 1) % len(SECTIONS)
        _enter_section(state, SECTIONS[state.chooser_index], actions)
    elif key in ("down", "j"):
        state.chooser_index = (state.chooser_index + 1) % len(rows)
    elif key in ("up", "k"):
        state.chooser_index = (state.chooser_index - 1) % len(rows)
    elif key == "escape":
        state.overlay = None
    elif key == "enter":
        state.overlay = None
        target = rows[state.chooser_index][0]
        if target.startswith("section:"):
            _enter_section(state, target.split(":", 1)[1], actions)
        else:
            _run_action(state, _ACTIONS_BY_ID[target], actions)


def _handle_focus_key(state: TuiState, key: str, actions: ScanActions) -> bool:
    if state.focus == "nav":
        if key in ("down", "j", "up", "k"):
            step = 1 if key in ("down", "j") else -1
            state.nav_index = (state.nav_index + step) % len(SECTIONS)
            return True
        if key == "enter":
            _enter_section(state, SECTIONS[state.nav_index], actions)
            return True
    elif state.focus == "actions":
        section_actions = _section_actions(state.section)
        if key in ("down", "j", "up", "k"):
            step = 1 if key in ("down", "j") else -1
            state.action_index = (state.action_index + step) % len(section_actions)
            return True
        if key == "enter":
            index = state.action_index % len(section_actions)
            _run_action(state, section_actions[index], actions)
            return True
    return False


_FORM_FIELDS: dict[str, tuple[str, ...]] = {
    "project_create": ("name", "parent", "init_git"),
    "project_relink": ("new_root",),
}


def _open_form(state: TuiState, kind: str, values: dict[str, str]) -> None:
    state.form = {"kind": kind, "values": values, "field": 0, "error": ""}
    state.overlay = "form"


def _handle_form_key(state: TuiState, key: str) -> None:
    form = state.form
    if form is None:
        state.overlay = None
        return
    names = _FORM_FIELDS[form["kind"]]
    current = names[form["field"]]
    if key == "escape":
        state.form = None
        state.overlay = None
        state.message = "cancelled"
    elif key == "tab":
        form["field"] = (form["field"] + 1) % len(names)
    elif key == "backspace":
        form["values"][current] = form["values"][current][:-1]
    elif key == "enter":
        _review_form(state, form)
    elif len(key) == 1 and key.isprintable():
        form["values"][current] += key


def _review_form(state: TuiState, form: dict[str, Any]) -> None:
    values = {k: v.strip() for k, v in form["values"].items()}
    missing = [name for name in _FORM_FIELDS[form["kind"]] if not values.get(name)]
    if missing:
        form["error"] = f"required: {', '.join(missing)}"
        return
    state.form = None
    state.overlay = None
    grant: dict[str, Any] = {"kind": form["kind"], **values}
    if form["kind"] == "project_create":
        grant["init_git"] = values["init_git"].lower() in ("y", "yes", "true")
        grant["summary"] = (
            f"Create folder {values['name']!r} under {values['parent']} and register it."
        )
    else:
        project = state.active_project
        registration = project.registration or {}
        grant.update(
            project_id=project.project_id or registration.get("project_id"),
            expected_revision=registration.get("revision"),
            summary=f"Relink project {project.name} to {values['new_root']}.",
        )
    _open_grant(state, grant)


_PROJECT_WRITE_GRANTS = ("cache_write", "artifact_write")


def _open_grant(state: TuiState, grant: dict[str, Any]) -> None:
    """Every review lists the `rush ui --allow-*` launch grants."""
    if grant["kind"].startswith("project_"):
        grant["grants"] = ", ".join(_PROJECT_WRITE_GRANTS)
    launch = state.launch_permissions or ExecutionPermissions()
    pre = [name for name, on in launch.to_dict().items() if on]
    grant["pre-granted at launch"] = ", ".join(pre) or "none"
    state.pending_grant = grant
    state.mode = "grant_review"


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    category: str  # Global | Navigation | Section | Text input | Running work
    sections: tuple[str, ...]
    run: Callable[[TuiState, ScanActions], None]
    enabled: Callable[[TuiState], tuple[bool, str]] = lambda state: (True, "")


def _run_action(state: TuiState, action: Action, actions: ScanActions) -> None:
    ok, reason = action.enabled(state)
    if not ok:
        state.message = reason
        return
    action.run(state, actions)


def _section_actions(section: str) -> list[Action]:
    return [a for a in ACTIONS if section in a.sections]


def _quit(state: TuiState, actions: ScanActions) -> None:
    if state.projects and _has_running_work(state.active_project):
        state.mode = "quit_confirm"
        state.message = ""
    else:
        state.should_quit = True


def _cursor(step: int) -> Callable[[TuiState, ScanActions], None]:
    def run(state: TuiState, actions: ScanActions) -> None:
        if state.mode == "map":
            _move_map_selection(state, state.active_project, step)
        elif state.section == "setup":
            _setup_move(state, step)
        else:
            _move_selection(state.active_project, step)

    return run


def _select_row(state: TuiState, actions: ScanActions) -> None:
    if state.active_project.visible_findings():
        state.mode = "detail"


def _open_project_selector(state: TuiState, actions: ScanActions) -> None:
    state.project_selector_index = state.active_index or 0
    state.mode = "project_selector"


def _open_section_chooser(state: TuiState, actions: ScanActions) -> None:
    state.chooser_index = SECTIONS.index(state.section)
    state.overlay = "sections"


def _cycle_focus(step: int) -> Callable[[TuiState, ScanActions], None]:
    def run(state: TuiState, actions: ScanActions) -> None:
        idx = FOCUS_CYCLE.index(state.focus) if state.focus in FOCUS_CYCLE else 1
        state.focus = FOCUS_CYCLE[(idx + step) % len(FOCUS_CYCLE)]

    return run


def _map_expand(state: TuiState, actions: ScanActions) -> None:
    if state.mode == "map":
        nodes = _map_visible_nodes(state.active_project, state.map_expanded)
        if 0 <= state.map_selected_index < len(nodes):
            node = nodes[state.map_selected_index]
            if node.get("children"):
                state.map_expanded.add(node["key"])


def _map_collapse(state: TuiState, actions: ScanActions) -> None:
    if state.mode == "map":
        nodes = _map_visible_nodes(state.active_project, state.map_expanded)
        if 0 <= state.map_selected_index < len(nodes):
            state.map_expanded.discard(nodes[state.map_selected_index]["key"])


def _cancel(state: TuiState, actions: ScanActions) -> None:
    if state.mode in ("detail", "help"):
        state.mode = _SECTION_MODES.get(state.section, "list")
    elif state.mode in ("git", "map"):
        _enter_section(state, "overview", actions)
    state.message = ""


def _refresh(state: TuiState, actions: ScanActions) -> None:
    if state.section == "git":
        _load_git_view(state, state.active_project, actions)
    elif state.section in _SECTION_LOADERS:
        state.load_requests.add((project_key(state.active_project), state.section))
    state.message = f"refreshing {SECTION_LABELS[state.section]}"


def _goto(section: str) -> Callable[[TuiState, ScanActions], None]:
    def run(state: TuiState, actions: ScanActions) -> None:
        _enter_section(state, section, actions)

    return run


def _set_mode(mode: str) -> Callable[[TuiState, ScanActions], None]:
    def run(state: TuiState, actions: ScanActions) -> None:
        state.mode = mode

    return run


def _start_check(state: TuiState, actions: ScanActions) -> None:
    if actions.run_check_suite is None:
        state.message = "no check suite configured"
        return
    _start_initial_check_thread(state.active_project, actions)
    state.message = "analysis started"


def _review_identity(state: TuiState) -> tuple[Any, ...]:
    """What a review describes: the project, its attempt and its source
    (the results the review was built from)."""
    if not state.projects:
        return ()
    project = state.active_project
    return (
        state.active_index,
        project_key(project),
        str(project.root),
        project.run_id,
        id(project.results),
        (project.registration or {}).get("revision"),
    )


def _start_scan_review(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    launch = state.launch_permissions or ExecutionPermissions()
    reviewed = sorted(
        {n for n, on in launch.to_dict().items() if on} | set(_PROJECT_WRITE_GRANTS)
    )
    _open_grant(
        state,
        {
            "kind": "start_scan",
            "project": project.name,
            "root": str(project.root),
            "summary": "Run a full scan against this project's real source.",
            "grants": ", ".join(reviewed),
            "per-candidate grants": (
                "engines: none (read-only); tools: at most the grants above -- "
                "a candidate needing any other grant ends permission_blocked"
            ),
            "_permissions": tuple(reviewed),
            "_identity": _review_identity(state),
        },
    )


def _rescan_review(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    _open_grant(
        state,
        {
            "kind": "rescan",
            "project": project.name,
            "root": str(project.root),
            "run_id": project.run_id,
            "expected attempt": project.run_id,
            "summary": f"Rescan run {project.run_id} against current source.",
            "_identity": _review_identity(state),
        },
    )


def _handoff_review(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    # T28-B: exactly the visible (filtered) findings are reviewed and sent.
    finding_ids = tuple(
        str(row["finding_id"])
        for row in project.visible_findings()
        if row.get("finding_id")
    )
    finding_count = len(finding_ids)
    _open_grant(
        state,
        {
            "kind": "handoff",
            "project": project.name,
            "root": str(project.root),
            "run_id": project.run_id,
            "agent_id": state.selected_agent_id,
            "finding_count": finding_count,
            "finding_ids": finding_ids,
            "_identity": _review_identity(state),
            "summary": (
                f"Send {finding_count} finding(s) from run {project.run_id} "
                f"to agent {state.selected_agent_id}."
            ),
        },
    )


def _project_add_review(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    _open_grant(
        state,
        {
            "kind": "project_add",
            "project": project.name,
            "root": str(project.root),
            "summary": f"Register {project.root} as a Rush project.",
        },
    )


def _project_create_form(state: TuiState, actions: ScanActions) -> None:
    parent = str(state.active_project.root.parent) if state.projects else ""
    _open_form(
        state, "project_create", {"name": "", "parent": parent, "init_git": "no"}
    )


def _project_relink_form(state: TuiState, actions: ScanActions) -> None:
    known = (state.active_project.registration or {}).get("new_root")
    _open_form(state, "project_relink", {"new_root": known or ""})


def _choose_later(state: TuiState, actions: ScanActions) -> None:
    project = state.active_project
    project.registration = {**(project.registration or {}), "deferred": True}
    state.message = "project choice deferred -- A adds or N creates one any time"


def _registration_state(state: TuiState) -> str | None:
    if not state.projects:
        return "none"
    registration = state.active_project.registration
    return registration.get("state") if registration else None


def _scan_enabled(state: TuiState) -> tuple[bool, str]:
    project = state.active_project
    worker = project.scan_thread
    # A local worker that has already exited is not running work, even
    # before the next poll records its terminal status.
    finished_locally = (
        project.owner == "local" and worker is not None and not worker.is_alive()
    )
    if project.status == "scanning" and not finished_locally:
        return False, "scan already running"
    return True, ""


def _rescan_enabled(state: TuiState) -> tuple[bool, str]:
    if not state.active_project.run_id:
        return False, "no completed run to rescan yet"
    return _scan_enabled(state)


def _handoff_enabled(state: TuiState) -> tuple[bool, str]:
    if not state.active_project.run_id:
        return False, "no completed run to hand off yet"
    if not state.selected_agent_id:
        return False, "press 'a' to choose a Setup/Agents target first"
    return True, ""


def _cancel_enabled(state: TuiState) -> tuple[bool, str]:
    if not _has_running_work(state.active_project):
        return False, "no running work to cancel"
    return True, ""


def _add_enabled(state: TuiState) -> tuple[bool, str]:
    registration = _registration_state(state)
    if registration is None:
        return False, "registration still loading"
    if registration != "none":
        return False, "project already registered or registry not readable"
    return True, ""


def _relink_enabled(state: TuiState) -> tuple[bool, str]:
    if _registration_state(state) != "moved":
        return False, "relink applies only to a moved project root"
    return True, ""


ACTIONS: tuple[Action, ...] = (
    Action("quit", "Quit", "Global", (), _quit),
    Action("open_project_selector", "Projects", "Global", (), _open_project_selector),
    Action("open_section_chooser", "Sections", "Global", (), _open_section_chooser),
    Action("show_help", "Help", "Global", (), _set_mode("help")),
    Action("refresh", "Refresh", "Global", SECTIONS, _refresh),
    Action("cancel", "Back", "Global", (), _cancel),
    Action("cursor_down", "Down", "Navigation", (), _cursor(1)),
    Action("cursor_up", "Up", "Navigation", (), _cursor(-1)),
    Action("select_row", "Inspect", "Navigation", ("scans",), _select_row),
    Action("cycle_pane", "Next pane", "Navigation", (), _cycle_focus(1)),
    Action("cycle_pane_reverse", "Prev pane", "Navigation", (), _cycle_focus(-1)),
    Action("map_expand", "Expand", "Navigation", ("map",), _map_expand),
    Action("map_collapse", "Collapse", "Navigation", ("map",), _map_collapse),
    Action("toggle_memory_admin", "Memory", "Navigation", (), _goto("memory")),
    Action("toggle_git_view", "Git", "Navigation", (), _goto("git")),
    Action("goto_tokens", "Tokens", "Navigation", (), _goto("tokens")),
    Action(
        "start_check",
        "Check",
        "Section",
        ("overview", "scans"),
        _start_check,
        _scan_enabled,
    ),
    Action(
        "start_scan",
        "Scan",
        "Section",
        ("overview", "scans"),
        _start_scan_review,
        _scan_enabled,
    ),
    Action("rescan", "Rescan", "Section", ("scans",), _rescan_review, _rescan_enabled),
    Action(
        "prepare_handoff",
        "Handoff",
        "Section",
        ("scans", "setup"),
        _handoff_review,
        _handoff_enabled,
    ),
    Action("cycle_agent", "Agent", "Section", ("setup",), _cycle_agent),
    Action(
        "setup_toggle_grant", "Toggle grant", "Section", ("setup",), _setup_toggle_grant
    ),
    Action(
        "setup_apply",
        "Apply setup",
        "Section",
        ("setup",),
        _setup_apply_review,
        _setup_apply_enabled,
    ),
    Action(
        "setup_retry",
        "Retry stage",
        "Section",
        ("setup",),
        _setup_retry_review,
        _setup_retry_enabled,
    ),
    Action(
        "project_add",
        "Add",
        "Section",
        ("overview",),
        _project_add_review,
        _add_enabled,
    ),
    Action("project_create", "Create", "Section", ("overview",), _project_create_form),
    Action(
        "project_relink",
        "Relink",
        "Section",
        ("overview",),
        _project_relink_form,
        _relink_enabled,
    ),
    Action("choose_later", "Later", "Section", (), _choose_later, _add_enabled),
    Action("focus_filter", "Filter", "Text input", ("scans",), _set_mode("search")),
    Action("confirm_grant", "Confirm", "Text input", (), lambda state, actions: None),
    Action(
        "cancel_scan",
        "Cancel run",
        "Running work",
        ("overview", "scans"),
        lambda state, actions: _request_cancel(state.active_project, actions),
        _cancel_enabled,
    ),
)
_ACTIONS_BY_ID = {action.id: action for action in ACTIONS}
_MIN_COLUMNS, _MIN_ROWS = 60, 20
_RESIZE_KEYS = ("q", "c", "f2", "escape")
# q and F2 open these below the minimum size too; their own keys answer them.
_RESIZE_MODALS = ("quit_confirm", "project_selector")
_ACTION_CATEGORIES = ("Global", "Navigation", "Section", "Text input", "Running work")
_KEYMAP = KeymapManager(_BINDINGS)


def _dispatch_key(state: TuiState, key: str, actions: ScanActions) -> None:
    _dispatch_key_inner(state, key, actions)
    _sync_section(state)


def _too_small(state: TuiState) -> bool:
    columns, rows = state.terminal_size
    return columns < _MIN_COLUMNS or rows < _MIN_ROWS


def _dispatch_key_inner(state: TuiState, key: str, actions: ScanActions) -> None:
    if (
        _too_small(state)
        and key not in _RESIZE_KEYS
        and state.mode not in _RESIZE_MODALS
    ):
        return  # resize_guidance: every other key waits; all state is kept
    if not state.projects:
        if state.overlay == "form":
            _handle_form_key(state, key)
        elif key == "q":
            state.should_quit = True
        elif key == "N":
            _project_create_form(state, actions)
        elif state.pending_grant is not None and key in ("y", "n", "escape"):
            _handle_grant_review_key(state, key, actions)
        return
    modal: dict[str, Callable[[TuiState, str, ScanActions], None]] = {
        "search": lambda st, k, a: _handle_search_key(st, k),
        "grant_review": _handle_grant_review_key,
        "memory_search": _handle_memory_search_key,
        "memory_edit": _handle_memory_edit_key,
        "memory_create": _handle_memory_create_key,
        "memory_owner": _handle_memory_owner_key,
        "memory_filter": _handle_memory_filter_key,
        "memory": _handle_memory_key,
        "quit_confirm": _handle_quit_confirm_key,
        "project_selector": _handle_project_selector_key,
    }
    if state.overlay == "sections":
        _handle_section_chooser_key(state, key, actions)
        return
    if state.overlay == "form":
        _handle_form_key(state, key)
        return
    if key == "f3" and state.mode == "memory":
        # The Memory section's own key handler never swallows the global
        # section chooser (its text-entry sub-modes still do).
        _open_section_chooser(state, actions)
        return
    handler = modal.get(state.mode)
    if handler is not None:
        handler(state, key, actions)
        return
    if _handle_focus_key(state, key, actions):
        return
    action = _ACTIONS_BY_ID.get(_KEYMAP.get_action_for_key(key) or "")
    if action is not None:
        _run_action(state, action, actions)


def _keymap_footer(state: TuiState) -> Text:
    parts = []
    for action in _section_actions(state.section)[:6] if state.projects else []:
        keys = [b.key for b in _BINDINGS if b.action_name == action.id]
        ok, reason = action.enabled(state)
        parts.append(f"{keys[0]}:{action.label}" + ("" if ok else f" ({reason})"))
    parts.extend(["F3:Sections", "F2:Projects", "?:Help"])
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
        sev = safe_terminal_text(row.get("severity", "info"))
        table.add_row(
            Text(marker),
            _safe(row.get("tool", "")),
            _safe(f"{_finding_path(row)}:{_finding_line(row)}"),
            Text(sev, style=_severity_style(sev)),
            _safe(row.get("message", "")),
        )
    # T28-C: a tool outcome with no findings (clean/skipped/denied/error)
    # still gets its own visible row with its status and reason.
    for result in project.results:
        if result.get("findings"):
            continue
        status = safe_terminal_text(result.get("status", ""))
        table.add_row(
            Text(""),
            _safe(result.get("tool", "")),
            Text("-"),
            Text(status, style=_severity_style(status)),
            _safe(result.get("summary") or "no findings"),
        )
    if project.status == "scanning":
        table.add_row(
            Text(""),
            Text("suite"),
            Text("-"),
            Text("running", style="bold yellow"),
            Text("more tool results pending"),
        )
    return Panel(
        table, title=_findings_title(project, rows, total_pages), style="green"
    )


def _safe(value: object, style: str = "") -> Text:
    """X3: a dynamic value as literal, control-free terminal text."""
    return Text(safe_terminal_text(value), style=style)


_UNAVAILABLE_STATUSES = ("skipped", "error")


def _findings_title(
    project: ProjectState, rows: list[dict[str, Any]], total_pages: int
) -> Text:
    """A count only when a tool actually completed: no result yet and
    nothing-completed are never shown as zero findings."""
    if not project.results:
        return Text("Findings (no result yet)")
    if all(r.get("status") in _UNAVAILABLE_STATUSES for r in project.results):
        return Text("Findings (unavailable: no tool completed)")
    title = f"Findings ({len(rows)}) page {project.detail_page + 1}/{total_pages}"
    if project.filter_text:
        title += f" filter={project.filter_text!r}"
    return _safe(title)


def _outcome_line(result: Mapping[str, Any]) -> Text:
    """One line per result: clean, N findings, unavailable, or error."""
    status = result.get("status")
    count = len(result.get("findings") or [])
    if status == "skipped":
        outcome, style = "unavailable", THEME["text_muted"]
    elif status == "error":
        outcome, style = "error", "bold red"
    elif count:
        outcome, style = f"{count} findings", "bold yellow"
    else:
        outcome, style = "clean", "bold green"
    tool = safe_terminal_text(result.get("tool", ""))
    summary = safe_terminal_text(result.get("summary", ""))
    return Text(f"{tool}: {outcome} -- {summary}", style=style)


def _registration_banner(project: ProjectState) -> list[Text]:
    registration = project.registration or {}
    kind = registration.get("state")
    reason = safe_terminal_text(registration.get("reason") or "")
    if kind == "none":
        lines = [Text("No project registered for this folder.", style="bold yellow")]
        if registration.get("deferred"):
            lines.append(Text("Project choice deferred.", style=THEME["text_muted"]))
        lines.append(
            Text(
                "[A] Add this folder  [N] Create a new project  [L] Choose later",
                style="bold",
            )
        )
        return lines
    if kind == "moved":
        return [
            Text(f"Project root moved: {reason}", style="bold yellow"),
            Text("[R] Relink to the new root (reviewed)", style="bold"),
        ]
    if kind in ("corrupt", "unreadable"):
        return [Text(f"Registry {kind}: {reason}", style="bold red")]
    if kind == "ambiguous":
        return [Text(f"Registration ambiguous: {reason}", style="bold yellow")]
    return []


def _view_state_lines(label: str, view: SectionView | None) -> list[Text]:
    """One fact per line: the state, then its time, then its cause."""
    if view is None or view.state == "populated":
        return []
    lines: list[Text] = []
    if view.state in ("failed", "stale"):
        lines.append(Text(f"{label} {view.state} (F5 retry)", style="bold red"))
    else:
        lines.append(Text(f"{label} {view.state}", style="bold yellow"))
    if view.state == "stale" and view.loaded_at:
        lines.append(_safe(f"last loaded {view.loaded_at}"))
    if view.reason:
        lines.append(_safe(view.reason))
    return lines


def _data_lines(data: Any) -> list[Text]:
    """A loaded section payload as bounded literal `key: value` lines."""
    if isinstance(data, Mapping):
        items = [(k, v) for k, v in data.items() if k != "registration"]
    elif isinstance(data, list):
        items = list(enumerate(data))
    else:
        items = [] if data is None else [("value", data)]
    return [
        _safe(f"{key}: {json.dumps(value, default=str)[:160]}")
        for key, value in items[:PAGE_SIZE]
    ]


def _overview_lines(data: Mapping[str, Any]) -> list[Text]:
    """The Overview facts: every `rush status` section (config, engines,
    activity, published result vs latest attempt, agents, useful memory),
    then Git, stack, runs and coverage -- each unavailable one with why."""
    from rush.tools.status import _status_sections

    lines: list[Text] = []
    status = data.get("status")
    if isinstance(status, Mapping) and status:
        try:
            lines.extend(_safe(line) for line in _status_sections(dict(status)))
        except (KeyError, TypeError) as exc:
            lines.append(_safe(f"Status unavailable -- incomplete status data: {exc}"))
    else:
        cause = data.get("status_summary") or "rush status returned no data"
        lines.append(_safe(f"Status unavailable -- {cause}"))
    evidence = data.get("evidence")
    if not isinstance(evidence, Mapping):
        return lines
    git = evidence.get("git") or {}
    if not git.get("has_git"):
        lines.append(Text("Git: unavailable -- no Git repository"))
    elif git.get("head") is None:
        lines.append(Text("Git: unavailable -- git could not read HEAD"))
    else:
        changed = len(git.get("dirty_files") or [])
        tree = "dirty" if git.get("dirty") else "clean"
        lines.append(
            _safe(
                f"Git: HEAD {str(git['head'])[:12]}, {tree}, {changed} changed file(s)"
            )
        )
    stack = evidence.get("stack") or []
    lines.append(_safe(f"Stack: {', '.join(stack) if stack else 'none detected'}"))
    runs = evidence.get("runs")
    if not isinstance(runs, Mapping):
        lines.append(Text("Runs: unavailable -- project not registered"))
        lines.append(Text("Coverage: unavailable -- project not registered"))
        return lines
    latest = runs.get("latest_run_id")
    lines.append(
        _safe(
            f"Runs: {runs.get('count')} recorded"
            + (f", latest {latest} ({runs.get('latest_run_state')})" if latest else "")
        )
    )
    findings, coverage = runs.get("findings_count"), runs.get("coverage")
    lines.append(
        _safe(
            f"Findings: {findings}"
            if findings is not None
            else "Findings: unavailable -- no completed run"
        )
    )
    lines.append(
        _safe(
            f"Coverage: {coverage}"
            if coverage is not None
            else "Coverage: unavailable -- the latest run recorded no coverage"
        )
    )
    return lines


def _render_overview(state: TuiState, project: ProjectState) -> Panel:
    view = state.views.get((project_key(project), "overview"))
    lines: list[Any] = [*_registration_banner(project)]
    lines.extend(_view_state_lines("Overview", view))
    if view is not None and view.data is not None:
        data = view.data if isinstance(view.data, Mapping) else {}
        lines.extend(_overview_lines(data))
    lines.extend(_outcome_line(result) for result in project.results)
    if project.status in ("scanning", "cancelling"):
        lines.append(_safe(f"{project.work_kind or 'work'} running"))
    if project.last_message:
        lines.append(_safe(project.last_message))
    if project.results:
        lines.append(_render_project_table(project))
    elif len(lines) == 0:
        lines.append(Text("No analysis yet -- press C to check or s to scan."))
    return Panel(Group(*lines), title="Overview", style=THEME["border"])


def _setup_apply_line(project: ProjectState) -> Text | None:
    events = list(project.setup_apply_events)
    if not events:
        return None
    return Text("\n").join(
        [Text("Setup apply:", style="bold")]
        + [_safe(f"  {stage} {status}") for stage, status in events]
    )


def _render_setup(state: TuiState, project: ProjectState) -> Panel:
    view = state.views.get((project_key(project), "setup"))
    data = view.data if view is not None and isinstance(view.data, dict) else {}
    if "review" not in data and "review_error" not in data:
        _build_setup_view(state, project)
        view = state.views[(project_key(project), "setup")]
        data = view.data
    lines: list[Any] = _view_state_lines("Setup", view)
    if data.get("review_text"):
        lines.extend(_safe(line) for line in str(data["review_text"]).splitlines())
    toggles = data.get("stage_grants") or {}
    current = data.get("stage_index", 0) % max(len(toggles), 1)
    lines.append(
        _safe(
            "Stage grants (j/k highlight, t toggle, p apply): "
            + ", ".join(
                f"{'>' if i == current else ''}{k} {'on' if v else 'off'}"
                for i, (k, v) in enumerate(toggles.items())
            )
        )
    )
    progress = _setup_apply_line(project)
    if progress is not None:
        lines.append(progress)
    agents = state.views.get((project_key(project), "agents"))
    if agents is not None:
        lines.extend(_view_state_lines("Agent", agents))
    return Panel(Group(*lines), title="Setup", style=THEME["border"])


def _render_section_view(state: TuiState, project: ProjectState) -> Panel:
    section = state.section
    label = SECTION_LABELS[section]
    if section == "setup":
        return _render_setup(state, project)
    view = state.views.get((project_key(project), section))
    lines: list[Any] = _view_state_lines(label, view)
    if view is None:
        lines.append(Text(f"{label} not loaded yet (F5 load)"))
    else:
        lines.extend(_data_lines(view.data))
    return Panel(Group(*lines), title=label, style=THEME["border"])


def _load_map_snapshot(project: ProjectState) -> dict[str, Any] | None:
    """T28-C: the read-only `project_map_snapshot` for the current attempt,
    loaded lazily and cached until (run_id, status) changes. Never writes;
    an unregistered project has none, a failure is an explicit unavailable
    snapshot."""
    key = (project.run_id, project.status)
    if project.map_snapshot_key == key:
        return project.map_snapshot
    project.map_snapshot_key = key
    project.map_snapshot = None
    if project.project_id is None:
        return None
    from rush.workflows.projects import (
        ProjectError,
        project_map_snapshot,
        resolve_project,
    )

    try:
        record = resolve_project(project.project_id)
        project.map_snapshot = project_map_snapshot(record, None, None)
    except (ProjectError, OSError, ValueError) as exc:
        project.map_snapshot = {
            "available": False,
            "reason": safe_terminal_text(exc),
        }
    return project.map_snapshot


def _captured_detail(project: ProjectState, finding: dict[str, Any]) -> str | None:
    """T28-C: the attempt's captured immutable snapshot of the finding's
    path (`read_project_artifact_page`), preferred over the live file and
    labelled with its run/attempt. `None` when nothing was captured."""
    snapshot = _load_map_snapshot(project)
    path_value = _finding_path(finding)
    if not snapshot or not path_value or project.project_id is None:
        return None
    captured = (snapshot.get("artifact_snapshots") or {}).get(path_value)
    if not isinstance(captured, dict):
        return None
    from rush.workflows.projects import ProjectError, read_project_artifact_page

    cursor = base64.urlsafe_b64encode(
        json.dumps(
            {
                "project_id": project.project_id,
                "run_id": snapshot.get("run_id"),
                "attempt_id": snapshot.get("attempt_id"),
                "tool_id": captured.get("tool_id"),
                "path": path_value,
                "sha256": captured.get("sha256"),
                "offset": 0,
            }
        ).encode("utf-8")
    ).decode("ascii")
    try:
        page = read_project_artifact_page(
            project.project_id, cursor, limit=_DETAIL_MAX_BYTES
        )
    except (ProjectError, OSError, ValueError):
        return None
    if page.get("error") or page.get("content_base64") is None:
        return None
    text = base64.b64decode(page["content_base64"]).decode("utf-8", errors="replace")
    message = safe_terminal_text(finding.get("message") or "")
    return "\n".join(
        part
        for part in (
            safe_terminal_text(page.get("label")),
            message,
            safe_terminal_text(text),
        )
        if part
    )


def _render_detail(project: ProjectState) -> Panel:
    rows = project.visible_findings()
    if not rows or project.selected_index >= len(rows):
        return Panel(Text("No finding selected."), title="Detail")
    finding = rows[project.selected_index]
    body = _safe(
        _captured_detail(project, finding)
        or _bounded_local_detail(project.root, finding)
    )
    title = _safe(
        f"{finding.get('tool', '')}: {_finding_path(finding)}:{_finding_line(finding)}"
    )
    return Panel(body, title=title, style="magenta")


def _render_grant_review(grant: dict[str, Any]) -> Panel:
    lines = [
        _safe(f"{key}: {value}", "white")
        for key, value in grant.items()
        if key != "kind" and not key.startswith("_")
    ]
    lines.append(Text(""))
    lines.append(Text("[y] confirm    [any other key] decline", style="bold yellow"))
    return Panel(
        Group(*lines),
        title=_safe(f"Review before mutation: {grant['kind']}"),
        style="red",
    )


def _memory_expanded_panel(expanded: dict[str, Any]) -> Panel:
    """T28-D: the exact expanded record as labelled sections -- record fields,
    Relationships and Receipts, one row per item with its own id and version --
    never a Python dict repr. Every cell goes through _safe (X3)."""
    fields = Table(title="Record", expand=True, show_header=False)
    fields.add_column("field", style="cyan")
    fields.add_column("value")
    for key, value in expanded.items():
        if key in ("relationships", "receipts"):
            continue
        shown = (
            json.dumps(value, sort_keys=True, default=str)
            if isinstance(value, (dict, list))
            else value
        )
        fields.add_row(_safe(key), _safe(shown))
    parts: list[Any] = [fields]
    for key, title in (("relationships", "Relationships"), ("receipts", "Receipts")):
        section = Table(title=title, expand=True)
        section.add_column("id", style="cyan")
        section.add_column("version")
        section.add_column("kind")
        for row in expanded.get(key) or []:
            if isinstance(row, dict):
                section.add_row(
                    _safe(row.get("id", "")),
                    _safe(row.get("artifact_version", "")),
                    _safe(row.get("kind", "")),
                )
        parts.append(section)
    return Panel(Group(*parts), title="expanded")


def _render_memory_admin(state: TuiState) -> Panel:
    """P66-05: real search results, selection, expansion, and pending-delete
    state -- never a static/example row. Render failures already surface via
    `state.memory_message` (set by the dispatch helpers above), so this
    function only ever formats whatever is currently in `state`."""
    owner = _memory_owner_scope(state, state.active_project)
    lines: list[Any] = [
        _safe(
            f"subject={state.memory_subject}  query={state.memory_query_buffer!r}",
            "cyan",
        ),
        _safe(f"owner={owner['kind']}:{owner['id']}  [o] change scope", "cyan"),
    ]
    if state.mode == "memory_owner":
        lines.append(
            _safe(
                f"owner {state.memory_owner_scope_kind} id> "
                f"{state.memory_owner_buffer or ''}"
                "   [tab] kind  [enter] apply  [esc] cancel",
                "bold yellow",
            )
        )
    active_filters = [
        f"{name}={value}"
        for name, value in _memory_filter_values(state).items()
        if value
    ]
    if active_filters:
        lines.append(_safe("filters: " + "  ".join(active_filters), "cyan"))
    if state.mode == "memory_filter":
        buf = state.memory_filter_buffer or {}
        for name in _MEMORY_FILTER_FIELDS:
            marker = ">" if name == state.memory_filter_field else " "
            lines.append(_safe(f"{marker} {name}: {buf.get(name, '')}", "bold yellow"))
        lines.append(_safe("[tab] field  [enter] apply  [esc] cancel", "bold yellow"))
    if state.mode == "memory_search":
        lines.append(_safe(f"/{state.memory_query_buffer}", "bold yellow"))
    if state.mode == "memory_edit":
        lines.append(
            _safe(
                f"edit {state.memory_edit_field}> {state.memory_edit_buffer or ''}",
                "bold yellow",
            )
        )
    if state.mode == "memory_create":
        buf = state.memory_create_buffer or {}
        for name in ("subject", "source", "content"):
            marker = ">" if name == state.memory_create_field else " "
            lines.append(_safe(f"{marker} {name}: {buf.get(name, '')}", "bold yellow"))

    table = Table(expand=True)
    table.add_column("", width=4)
    table.add_column("id", style="cyan")
    table.add_column("trust", width=14)
    table.add_column("source")
    table.add_column("stale", width=6)
    page = state.memory_selected_index // _MEMORY_PAGE_ROWS
    pages = max(1, -(-len(state.memory_items) // _MEMORY_PAGE_ROWS))
    start = page * _MEMORY_PAGE_ROWS
    for idx, item in enumerate(
        state.memory_items[start : start + _MEMORY_PAGE_ROWS], start
    ):
        cursor = ">" if idx == state.memory_selected_index else " "
        checked = "x" if item.get("id") in state.memory_selected_ids else " "
        table.add_row(
            f"{cursor}[{checked}]",
            _safe(item.get("id", "")),
            _safe(item.get("trust_tier", "")),
            _safe(item.get("source", "")),
            "yes" if item.get("stale") else "no",
        )
    lines.append(table)
    lines.append(
        _safe(f"page {page + 1}/{pages}  ] next page  [ previous page", "cyan")
    )

    if state.memory_pending_mutation is not None:
        pending_mutation = state.memory_pending_mutation
        lines.append(
            _safe(_memory_pending_mutation_text(pending_mutation), "bold yellow")
        )
        for artifact_id in pending_mutation["ids"]:
            owner_text = _memory_row_owner(
                state, artifact_id, pending_mutation.get("owner_scope")
            )
            lines.append(
                _safe(
                    f"  {artifact_id}  "
                    f"version={pending_mutation['versions'].get(artifact_id, '?')}  "
                    f"owner={owner_text}",
                    "yellow",
                )
            )
        for draft in pending_mutation.get("drafts") or []:
            fields_text = "  ".join(
                f"{name}="
                + (
                    json.dumps(value, sort_keys=True, default=str)
                    if isinstance(value, (dict, list))
                    else str(value)
                )
                for name, value in draft.items()
            )
            lines.append(_safe(f"  draft {fields_text}", "yellow"))
        for consequence in pending_mutation.get("consequences") or []:
            if consequence:
                lines.append(_safe(f"  consequence: {consequence}", "yellow"))
    if state.memory_pending_maintain is not None:
        lines.append(
            Text(
                "pending maintenance -- [y] apply  [n]/[esc] cancel",
                style="bold yellow",
            )
        )
        for entry in state.memory_pending_maintain:
            lines.append(
                _safe(
                    f"  {entry['task']}: {len(entry['candidate_ids'])} candidate(s)  "
                    f"grants {entry['required_grants']}  "
                    f"consequence: {entry.get('consequence', '')}",
                    "yellow",
                )
            )
            revisions = entry.get("expected_revisions") or {}
            for artifact_id in entry["candidate_ids"]:
                owner_text = _memory_row_owner(state, artifact_id, entry["owner_scope"])
                lines.append(
                    _safe(
                        f"    {entry['task']} {artifact_id}  "
                        f"version={revisions.get(artifact_id, '?')}  owner={owner_text}",
                        "yellow",
                    )
                )
    if state.memory_pending_delete is not None:
        count = len(state.memory_pending_delete["artifact_ids"])
        lines.append(
            Text(
                f"pending delete: {count} record(s) -- [y] confirm  [n]/[esc] cancel",
                style="bold red",
            )
        )
        pending = state.memory_pending_delete
        affected = {
            row.get("id"): row
            for row in pending.get("affected") or []
            if isinstance(row, dict)
        }
        lines.append(
            _safe(
                f"  grants {pending['required_grants']}  "
                f"consequence: permanently deletes {count} record(s)",
                "red",
            )
        )
        for artifact_id in pending["artifact_ids"]:
            row = affected.get(artifact_id, {})
            owner_text = _memory_row_owner(state, artifact_id, pending["owner_scope"])
            lines.append(
                _safe(
                    f"  {artifact_id}  version={pending['expected_revisions'].get(artifact_id, '?')}"
                    f"  owner={owner_text}"
                    f"  family={row.get('family', '?')}"
                    f"  references={row.get('references', '?')}",
                    "red",
                )
            )
    if state.memory_expanded is not None:
        lines.append(_memory_expanded_panel(state.memory_expanded))
    if state.memory_message:
        lines.append(_safe(state.memory_message, "bold magenta"))
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
        _safe(
            f"has_git={git.get('has_git')}  head={git.get('head') or '-'}  "
            f"dirty={git.get('dirty')}",
            "cyan",
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
            _safe(str(commit.get("hash", ""))[:8]),
            _safe(commit.get("author", "")),
            _safe(commit.get("date", "")),
            _safe(commit.get("subject", "")),
        )
    lines.append(history_table)

    dirty_files = git.get("dirty_files") or []
    if dirty_files:
        dirty_table = Table(expand=True, title=f"Dirty ({len(dirty_files)})")
        dirty_table.add_column("status", width=8)
        dirty_table.add_column("path")
        for entry in dirty_files[:PAGE_SIZE]:
            dirty_table.add_row(
                _safe(entry.get("status", "")),
                _safe(entry.get("path", "")),
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
            _safe(
                "artifacts: "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
                "white",
            )
        )
    if state.git_message:
        lines.append(_safe(state.git_message, "bold magenta"))
    return Panel(Group(*lines), title="Git & Artifacts", style="blue")


def _render_help(state: TuiState) -> Panel:
    """P69-06c: the real, current `_KEYMAP` bindings -- never a hardcoded
    help string that can drift from what's actually bound. T28-A: grouped
    by the bound action's `ACTIONS` category."""
    lines: list[str] = []
    for category in _ACTION_CATEGORIES:
        bound = [
            b
            for b in _KEYMAP.bindings
            if (action := _ACTIONS_BY_ID.get(b.action_name)) is not None
            and action.category == category
        ]
        if bound:
            lines.append(f"{category}:")
            lines.extend(f"  {b.key}: {b.description}" for b in bound)
    return Panel(Text("\n".join(lines)), title="Key Bindings", style="cyan")


def _render_nav_pane(state: TuiState) -> Panel:
    """U04 fix: the persistent nav pane shown alongside the main content at
    compact/wide widths (Phase 66 §3.8). T28-A: the eight numbered sections,
    the open projects, and the current section's actions with the reason
    any of them is disabled."""
    focus_nav = state.focus == "nav"
    lines: list[Text] = []
    for idx, section in enumerate(SECTIONS):
        current = section == state.section
        cursor = ">" if (focus_nav and idx == state.nav_index) or current else " "
        lines.append(
            Text(
                f"{cursor}{idx + 1} {SECTION_LABELS[section]}",
                style=THEME["blue"] if current else THEME["text_muted"],
            )
        )
    lines.append(Text("Projects", style="bold"))
    lines.extend(
        _safe(
            f"{'>' if idx == state.active_index else ' '}{p.name}",
            THEME["blue"] if idx == state.active_index else THEME["text_muted"],
        )
        for idx, p in enumerate(state.projects)
    )
    section_actions = _section_actions(state.section)
    if section_actions and state.projects:
        lines.append(Text("Actions", style="bold"))
        for idx, action in enumerate(section_actions):
            ok, reason = action.enabled(state)
            cursor = (
                ">" if state.focus == "actions" and idx == state.action_index else " "
            )
            lines.append(
                Text(
                    f"{cursor}{action.label}" + ("" if ok else f" ({reason})"),
                    style=THEME["text"] if ok else THEME["text_muted"],
                )
            )
    return Panel(Group(*lines), title="Navigate", style=THEME["border"])


def _render_section_chooser(state: TuiState) -> Panel:
    lines: list[Any] = []
    for idx, (target, label) in enumerate(_chooser_rows()):
        number = f"{idx + 1} " if target.startswith("section:") else "  "
        lines.append(
            Text(
                f"{'>' if idx == state.chooser_index else ' '}{number}{label}",
                style=THEME["blue"] if idx == state.chooser_index else THEME["text"],
            )
        )
    lines.append(Text(""))
    lines.append(Text("[1-8] go  [enter] choose  [escape] close", style="bold yellow"))
    return Panel(Group(*lines), title="Sections", style=THEME["border"])


def _render_form(state: TuiState) -> Panel:
    form = state.form or {"kind": "form", "values": {}, "field": 0, "error": ""}
    names = _FORM_FIELDS.get(form["kind"], ())
    lines: list[Any] = []
    for idx, name in enumerate(names):
        cursor = ">" if idx == form["field"] else " "
        lines.append(_safe(f"{cursor}{name}: {form['values'].get(name, '')}"))
    if form.get("error"):
        lines.append(_safe(form["error"], "bold red"))
    lines.append(Text(""))
    lines.append(
        Text("[tab] next field  [enter] review  [escape] cancel", style="bold yellow")
    )
    return Panel(Group(*lines), title=_safe(form["kind"]), style=THEME["border"])


def _render_project_selector(state: TuiState) -> Panel:
    """U01 fix: F2's overlay -- highlights `project_selector_index`,
    never `active_index` directly (that only changes on Enter)."""
    lines: list[Any] = [
        Text(
            safe_terminal_text(
                f"{'>' if idx == state.project_selector_index else ' '}{p.name}"
            ),
            style=THEME["blue"]
            if idx == state.project_selector_index
            else THEME["text"],
        )
        for idx, p in enumerate(state.projects)
    ]
    for offset, (_, label) in enumerate(_SELECTOR_EXTRAS):
        idx = len(state.projects) + offset
        selected = idx == state.project_selector_index
        lines.append(
            Text(
                f"{'>' if selected else ' '}{label}",
                style=THEME["blue"] if selected else THEME["text"],
            )
        )
    lines.append(Text(""))
    lines.append(Text("[enter] choose    [escape] cancel", style="bold yellow"))
    return Panel(Group(*lines), title="Project Selector", style=THEME["border"])


def _render_map(state: TuiState, project: ProjectState) -> Panel:
    """U01 fix: the real Project -> Files -> Findings hierarchy
    (`_map_nodes`/`_map_visible_nodes`), with a `[+]`/`[-]` glyph on every
    expandable file node -- previously no Map view existed at all. T28-C:
    the read-only `project_map_snapshot` feeding the Memories/Agents
    branches is loaded lazily here."""
    _load_map_snapshot(project)
    nodes = _map_visible_nodes(project, state.map_expanded)
    lines: list[Text] = []
    for idx, node in enumerate(nodes):
        marker = ">" if idx == state.map_selected_index else " "
        indent = "  " * int(node["depth"])
        glyph = ""
        if node.get("children"):
            glyph = "[-] " if node["key"] in state.map_expanded else "[+] "
        lines.append(_safe(f"{marker}{indent}{glyph}{node['label']}"))
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
        return _safe(state.message, "bold magenta")
    return Text("")


def _set_footer(layout: Layout, state: TuiState, status: Text) -> None:
    """The status line above the keymap footer; the footer grows to the
    keymap's wrapped height so `?:Help` is never cut off."""
    keymap = _keymap_footer(state)
    inner = max(1, state.terminal_size[0] - 4)
    measure = Console(width=inner, file=io.StringIO())
    rows = sum(max(1, len(text.wrap(measure, inner))) for text in (status, keymap))
    layout["footer"].size = 2 + rows
    layout["footer"].update(Panel(Group(status, keymap), style=_FOOTER_STYLE))


def _render_resize_guidance(state: TuiState) -> Panel:
    columns, rows = state.terminal_size
    lines: list[Any] = [
        Text(f"Terminal {columns}x{rows} is too small.", style="bold yellow"),
        Text(f"Resize to at least {_MIN_COLUMNS}x{_MIN_ROWS}."),
        Text("q quit  c cancel  F2 projects  Esc back", style="bold"),
    ]
    # What q, c or F2 just did stays visible: the open choice or the result.
    if state.mode == "quit_confirm" and state.projects:
        lines.append(_footer_status_line(state, state.active_project))
    elif state.mode == "project_selector":
        lines.append(_render_project_selector(state))
    elif state.message:
        lines.append(_safe(state.message, "bold magenta"))
    return Panel(Group(*lines), title="Resize", style=THEME["border"])


def _render_no_projects(state: TuiState) -> Layout:
    """No project open at all: only the workspace chooser (or its form)."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )
    header = Text(
        f"⚡ Rush Interactive Quality Explorer v{__version__}  (no project)",
        style=_HEADER_STYLE,
    )
    layout["header"].update(Panel(header, style=_HEADER_STYLE))
    if state.overlay == "form":
        body: Any = _render_form(state)
    elif state.mode == "grant_review" and state.pending_grant:
        body = _render_grant_review(state.pending_grant)
    else:
        body = Panel(
            Group(
                Text("No project open.", style="bold yellow"),
                Text("[N] Create a new project  [q] Quit", style="bold"),
            ),
            title="Choose a project",
            style=THEME["border"],
        )
    layout["main"].update(body)
    _set_footer(layout, state, _safe(state.message, "bold magenta"))
    return layout


def _render_body(state: TuiState, project: ProjectState) -> Any:
    if state.overlay == "sections":
        return _render_section_chooser(state)
    if state.overlay == "form":
        return _render_form(state)
    if state.mode in (
        "memory",
        "memory_search",
        "memory_edit",
        "memory_owner",
        "memory_create",
        "memory_filter",
    ):
        return _render_memory_admin(state)
    if state.mode == "git":
        return _render_git_panel(state)
    if state.mode == "map":
        return _render_map(state, project)
    if state.mode == "project_selector":
        return _render_project_selector(state)
    if state.mode == "grant_review" and state.pending_grant:
        return _render_grant_review(state.pending_grant)
    if state.mode == "detail":
        return _render_detail(project)
    if state.mode == "help":
        return _render_help(state)
    if state.section == "overview":
        progress = _setup_apply_line(project)
        if progress is not None:
            return Group(progress, _render_overview(state, project))
        return _render_overview(state, project)
    if state.section == "scans":
        history = state.views.get((project_key(project), "scans"))
        return Group(
            Panel(Group(*_scan_history_lines(history)), title="Scan history"),
            _render_project_table(project),
        )
    return _render_section_view(state, project)


def render_app(state: TuiState) -> Layout:
    if _too_small(state):
        guidance = Layout()
        guidance.update(_render_resize_guidance(state))
        return guidance
    if not state.projects:
        return _render_no_projects(state)
    project = state.active_project
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3),
    )

    header = _safe(
        f"⚡ Rush Interactive Quality Explorer v{__version__}  "
        f"[{(state.active_index or 0) + 1}/{len(state.projects)}] {project.name}  "
        f"{SECTION_LABELS[state.section]}  "
        f"({state.terminal_size[0]}x{state.terminal_size[1]})",
        _HEADER_STYLE,
    )
    layout["header"].update(Panel(header, style=_HEADER_STYLE))

    body = _render_body(state, project)

    # U04 fix: real width-dependent pane layout (Phase 66 §3.8) --
    # wide (>=100 cols) splits nav/list/detail three ways, compact
    # (80-99) splits nav/content, narrow (<80) shows a single pane with no
    # nav pane at all. Previously there was only one `>= 100` check with
    # no distinct 80-99/narrow behavior.
    branch = _width_branch(state.terminal_size[0])
    in_pane_mode = state.mode in ("list", "map") and state.overlay is None
    if branch == "wide" and in_pane_mode:
        overview = state.mode == "list" and state.section == "overview"
        layout["main"].split_row(
            Layout(name="nav", size=24),
            Layout(name="list", ratio=70 if overview else 45),
            Layout(name="detail", ratio=30 if overview else 55),
        )
        layout["main"]["nav"].update(_render_nav_pane(state))
        layout["main"]["list"].update(body)
        layout["main"]["detail"].update(_render_detail(project))
    elif branch == "compact" and in_pane_mode:
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
    _set_footer(layout, state, _footer_status_line(state, project))

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
    permissions: ExecutionPermissions | None = None,
    data_root: Path | None = None,
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
                lexical_path=seed.lexical_path,
                original_input=seed.original_input,
            )
            for seed in project_seeds
        ],
        data_root=data_root,
        launch_permissions=permissions,
    )
    state.terminal_size = reader.get_size()

    # T28-A: launch never starts analysis (plan: initial analysis is an
    # explicit Start action, `C`); the first tick only reads the Overview.
    if state.projects:
        state.load_requests.add((project_key(state.active_project), "overview"))

    # P69-06 CONNECT: explicit active/idle refresh-rate limiter -- 20Hz while
    # a key was just dispatched or a scan is running, 4Hz otherwise -- rather
    # than refreshing on every tick unconditionally.
    _pump(state, actions)  # immediate outcomes are in the first frame
    _ACTIVE_REFRESH_INTERVAL = 1.0 / 20
    _IDLE_REFRESH_INTERVAL = 1.0 / 4
    last_refresh = 0.0
    seen_setup_events = 0
    seen_statuses = {id(p): p.status for p in state.projects}

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
                resized = size != state.terminal_size
                if resized:
                    state.terminal_size = size

                applied = _pump(state, actions)
                _poll_running_scans(state, actions)

                key = reader.read_key(tick_seconds)
                if key is not None:
                    _dispatch_key(state, key, actions)
                status_changed = _reload_after_finished_work(state, seen_statuses)

                if live is not None:
                    setup_events = sum(
                        len(p.setup_apply_events) for p in state.projects
                    )
                    has_activity = (
                        key is not None
                        or applied
                        or resized
                        or setup_events != seen_setup_events
                        or status_changed
                        or any(
                            p.status in ("scanning", "cancelling")
                            for p in state.projects
                        )
                    )
                    seen_setup_events = setup_events
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
