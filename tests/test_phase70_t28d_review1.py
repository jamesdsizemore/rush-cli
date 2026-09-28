"""T28-D review round 1: failing tests that drive the real TUI with the real MemoryTool.

Every earlier T28-D TUI test ran against a scripted `memory_run` spy, so production
defects passed (`.orchestrator/review1-T28-D-findings.md`). Every test here runs
`tui._dispatch_key` / `tui.render_app` against `MemoryTool().run` over real
`.rush/memory.db` stores under `tmp_path`, and asserts the committed rows.

Fixed key decisions these tests encode:
- "f" in memory mode opens the filter form. Fields, in Tab order: trust, source,
  freshness, archived, owner. Every unset filter starts empty; typed text sets the
  field under the cursor (archived takes "true", owner takes "kind:id"); Enter
  applies and refreshes; Escape cancels. The render shows each active filter as
  `name=value`.
- "]" shows the next page of 20 rows, "[" the previous; the render shows "page N/M".
- Archive, promote and delete act on every space-selected row when any are
  selected, otherwise on the cursor row.
- Preview rows render as `key=value` fields, like the existing delete preview's
  `version=`/`owner=` fields.

Tests other than the browse-on-entry test fill the list through "/" search, which
works today, so each fails only for its own finding.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, get_args

import pytest
from rich.console import Console

from rush import tui as tui_mod
from rush.memory.store import (
    MemoryArtifact,
    MemorySubject,
    OwnerScope,
    TrustTier,
    TypedArtifactStore,
    readonly_view_reason,
)
from rush.tools.memory import MemoryTool
from rush.tui import ProjectState, ScanActions, TuiState
from rush.workflows.projects import register_project

_DAY = 86400.0
_ROW_ID = re.compile(r"\bzq\d\d\b")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


class _RealMemoryRun:
    """`MemoryTool().run` (the production wiring), recording each call's operation."""

    def __init__(self) -> None:
        self._run = MemoryTool().run
        self.operations: list[str] = []

    def __call__(self, root: Path, **kwargs: Any) -> Any:
        self.operations.append(str(kwargs.get("operation")))
        return self._run(root, **kwargs)


def _noop(*args: Any, **kwargs: Any) -> None:
    return None


def _actions(memory_run: _RealMemoryRun | None = None) -> ScanActions:
    return ScanActions(
        plan_scan=_noop,
        execute_scan=_noop,
        cancel_scan_run=_noop,
        rescan_project_run=_noop,
        build_handoff=_noop,
        dispatch_handoff=_noop,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        memory_run=memory_run or _RealMemoryRun(),
    )


def _root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    return root.resolve()


def _seed(
    root: Path,
    artifact_id: str,
    *,
    note: str = "alpha",
    trust_tier: TrustTier = "DERIVED",
    source: str = "s1",
    created_at: float | None = None,
    stale: bool = False,
    owner: OwnerScope | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> MemoryArtifact:
    store = TypedArtifactStore(root)
    try:
        return store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier=trust_tier,
                content={"note": note},
                source=source,
                created_at=created_at if created_at is not None else time.time(),
                stale=stale,
                owner_scope=owner,
                symbol_ref=symbol_ref,
                content_hash=content_hash,
            )
        )
    finally:
        store.close()


def _edit_outside_tui(root: Path, artifact_id: str, note: str, version: int) -> None:
    store = TypedArtifactStore(root)
    try:
        store.edit(
            artifact_id,
            {"note": note},
            expected_version=version,
            scope="domain_knowledge",
            apply=True,
        )
    finally:
        store.close()


def _rows(root: Path) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(str(root / ".rush" / "memory.db"))
    conn.row_factory = sqlite3.Row
    try:
        return {
            r["id"]: dict(r) for r in conn.execute("SELECT * FROM memory_artifacts")
        }
    finally:
        conn.close()


def _row(root: Path, artifact_id: str) -> dict[str, Any]:
    return _rows(root)[artifact_id]


def _files(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def _register(tmp_path: Path, root: Path) -> str:
    """Registers `root` (writing only `.rush/project.json` there) and returns its id."""
    return register_project(
        root, name=root.name, data_root=tmp_path / "data"
    ).project_id


def _state(tmp_path: Path, *roots: Path, project_ids: tuple[str, ...] = ()) -> TuiState:
    ids = project_ids or (None,) * len(roots)
    state = TuiState(
        projects=[
            ProjectState(name=root.name, root=root, project_id=project_id)
            for root, project_id in zip(roots, ids, strict=True)
        ],
        data_root=tmp_path / "data",
    )
    state.active_index = 0
    state.terminal_size = (400, 100)
    return state


def _drain(state: TuiState, actions: ScanActions) -> None:
    """Pumps like `run_interactive_tui` until no memory request is in flight."""
    deadline = time.monotonic() + 2
    tui_mod._pump(state, actions)
    while state.memory_request is not None:
        assert time.monotonic() < deadline, f"still in flight: {state.memory_request}"
        time.sleep(0.005)
        tui_mod._pump(state, actions)


def _keys(
    state: TuiState, actions: ScanActions, *keys: str, drain: bool = True
) -> None:
    for key in keys:
        tui_mod._dispatch_key(state, key, actions)
        if drain:
            _drain(state, actions)


def _enter_memory(state: TuiState, actions: ScanActions) -> None:
    """F3 section chooser, then the Memory section's number key."""
    _keys(state, actions, "f3", str(tui_mod.SECTIONS.index("memory") + 1))
    assert state.mode == "memory", state.mode


def _browse(state: TuiState, actions: ScanActions, query: str = "alpha") -> None:
    _keys(state, actions, "/", *query, "enter")


def _ids(state: TuiState) -> list[str]:
    return [item["id"] for item in state.memory_items]


def _cursor_to(state: TuiState, actions: ScanActions, artifact_id: str) -> None:
    for _ in range(len(state.memory_items)):
        if _ids(state)[state.memory_selected_index] == artifact_id:
            return
        _keys(state, actions, "down")
    raise AssertionError(f"{artifact_id} not listed: {_ids(state)}")


def _switch_project(
    state: TuiState, actions: ScanActions, index: int, *, drain: bool = True
) -> None:
    """F3 chooser -> Projects -> project selector -> Enter on `index`, then Memory.
    `drain=False` switches while a memory request is still in flight."""
    _keys(state, actions, "f3", drain=drain)
    rows = [row_id for row_id, _ in tui_mod._chooser_rows()]
    target = rows.index("open_project_selector")
    _keys(
        state, actions, *["down"] * (target - state.chooser_index), "enter", drain=drain
    )
    assert state.mode == "project_selector", state.mode
    steps = (index - state.project_selector_index) % (
        len(state.projects) + len(tui_mod._SELECTOR_EXTRAS)
    )
    _keys(state, actions, *["down"] * steps, "enter", drain=drain)
    assert state.active_index == index
    _enter_memory(state, actions)


def _screen(state: TuiState) -> str:
    console = Console(record=True, width=400, height=100, no_color=True)
    console.print(tui_mod.render_app(state))
    return console.export_text()


def _lines_with(screen: str, *parts: str) -> list[str]:
    return [line for line in screen.splitlines() if all(p in line for p in parts)]


def _set_filter(state: TuiState, actions: ScanActions, field: str, value: str) -> None:
    order = ("trust", "source", "freshness", "archived", "owner")
    _keys(state, actions, "f", *["tab"] * order.index(field), *value, "enter")


# ---------------------------------------------------------------------------
# Finding 1: browse on entry
# ---------------------------------------------------------------------------


def test_r1_browse_on_entry_lists_rows_without_a_query(tmp_path: Path) -> None:
    """RED: with no query and no filter, `list` routes to `_query`, which errors
    "memory list requires subject and query." and the list stays empty."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01", note="first")
    _seed(root, "zq02", note="second")
    state = _state(tmp_path, root)
    actions = _actions()

    _enter_memory(state, actions)

    assert state.memory_query_buffer == ""
    assert sorted(_ids(state)) == ["zq01", "zq02"], state.memory_message
    assert set(_ROW_ID.findall(_screen(state))) == {"zq01", "zq02"}


# ---------------------------------------------------------------------------
# Finding 2: a held preview never follows a project switch
# ---------------------------------------------------------------------------


def test_r1_switch_project_drops_held_archive_preview(tmp_path: Path) -> None:
    """RED: the project switch clears only the pending delete, so A's held archive
    call is rendered in B and "y" sends it to B's root, creating B's memory store."""
    a = _root(tmp_path, "a")
    b = _root(tmp_path, "b")
    ids = (_register(tmp_path, a), _register(tmp_path, b))
    _seed(a, "zq01", owner=OwnerScope("project", ids[0]))
    b_files = _files(b)
    state = _state(tmp_path, a, b, project_ids=ids)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    _keys(state, actions, "a")
    assert "archive preview" in state.memory_message

    _switch_project(state, actions, 1)
    assert "zq01" not in _screen(state)
    _keys(state, actions, "y")

    assert _files(b) == b_files
    row = _row(a, "zq01")
    assert (row["artifact_version"], row["archived_at"]) == (1, None)


def test_r1_switch_project_drops_held_maintenance_preview(tmp_path: Path) -> None:
    """RED: `memory_pending_maintain` survives the switch, so "y" in B runs A's
    reviewed maintenance (owner: A's registered id) on B's root, creating B's
    memory store."""
    a = _root(tmp_path, "a")
    b = _root(tmp_path, "b")
    ids = (_register(tmp_path, a), _register(tmp_path, b))
    _seed(
        a,
        "zq01",
        created_at=time.time() - 15 * _DAY,  # DERIVED ttl is 14 days
        owner=OwnerScope("project", ids[0]),
    )
    b_files = _files(b)
    state = _state(tmp_path, a, b, project_ids=ids)
    actions = _actions()
    _enter_memory(state, actions)
    _keys(state, actions, "w")
    assert "expiry_sweep 1" in state.memory_message

    _switch_project(state, actions, 1)
    assert "expiry_sweep 1" not in _screen(state)
    _keys(state, actions, "y")

    assert _files(b) == b_files
    row = _row(a, "zq01")
    assert (row["artifact_version"], row["expires_at"]) == (1, None)


def test_r1_switch_project_drops_edit_conflict(tmp_path: Path) -> None:
    """RED: `memory_edit_conflict` survives the switch, so "r" in B re-fetches A's
    row from B's root (creating B's memory store) and reports A's id there."""
    a = _root(tmp_path, "a")
    b = _root(tmp_path, "b")
    ids = (_register(tmp_path, a), _register(tmp_path, b))
    _seed(a, "zq01", note="alpha one", owner=OwnerScope("project", ids[0]))
    b_files = _files(b)
    state = _state(tmp_path, a, b, project_ids=ids)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    _edit_outside_tui(a, "zq01", "alpha changed", 1)
    _keys(state, actions, "e", *"mine", "enter")
    assert "edit conflict on zq01" in state.memory_message

    _switch_project(state, actions, 1)
    _keys(state, actions, "r")
    assert "zq01" not in state.memory_message
    _keys(state, actions, "y")

    assert _files(b) == b_files
    row = _row(a, "zq01")
    assert row["artifact_version"] == 2
    assert json.loads(row["content"]) == {"note": "alpha changed"}


# ---------------------------------------------------------------------------
# Findings 3 and 4: restore and the filter form
# ---------------------------------------------------------------------------


def test_r1_restore_round_trip_commits_versions(tmp_path: Path) -> None:
    """RED: no "f" filter form exists, so archived rows are unreachable; and the
    restore test reads `archived_at`, which listed rows never carry."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    _seed(root, "zq02")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    _cursor_to(state, actions, "zq01")
    _keys(state, actions, "a", "y")
    archived = _row(root, "zq01")
    assert archived["artifact_version"] == 2
    assert archived["archived_at"] is not None

    _set_filter(state, actions, "archived", "true")
    assert state.mode == "memory"
    assert _ids(state) == ["zq01"], state.memory_message
    _keys(state, actions, "a")
    assert "restore preview" in state.memory_message
    _keys(state, actions, "y")

    restored = _row(root, "zq01")
    assert restored["artifact_version"] == 3
    assert restored["archived_at"] is None
    assert "v3" in state.memory_message


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("trust", "EXTERNAL_WRITE", ["zq01"]),
        ("source", "s2", ["zq03"]),
        ("freshness", "stale", ["zq04"]),
        ("archived", "true", ["zq05"]),
        ("owner", "user:alice", ["zq06"]),
    ],
)
def test_r1_filter_form_sets_every_filter(
    tmp_path: Path, field: str, value: str, expected: list[str]
) -> None:
    """RED: no key or render sets or shows a filter, and no owner filter exists."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01", trust_tier="EXTERNAL_WRITE")
    _seed(root, "zq02")
    _seed(root, "zq03", source="s2")
    _seed(root, "zq04", stale=True)
    zq05 = _seed(root, "zq05")
    _seed(root, "zq06", owner=OwnerScope("user", "alice"))
    store = TypedArtifactStore(root)
    try:
        store.archive(
            "zq05",
            expected_version=zq05.artifact_version,
            scope="domain_knowledge",
            apply=True,
        )
    finally:
        store.close()
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)

    _set_filter(state, actions, field, value)

    assert state.mode == "memory"
    assert sorted(_ids(state)) == expected, state.memory_message
    assert f"{field}={value}" in _screen(state)


# ---------------------------------------------------------------------------
# Findings 5 and 6: maintenance versions and every preview's fields
# ---------------------------------------------------------------------------


def test_r1_maintain_refuses_changed_versions(tmp_path: Path) -> None:
    """RED: apply sends only candidate_ids, so a row edited after review is
    maintained anyway (expired, re-versioned) with its unreviewed content."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01", note="original", created_at=time.time() - 15 * _DAY)
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _keys(state, actions, "w")
    assert "expiry_sweep 1" in state.memory_message
    _edit_outside_tui(root, "zq01", "CHANGED AFTER REVIEW", 1)

    _keys(state, actions, "y")

    row = _row(root, "zq01")
    assert row["artifact_version"] == 2
    assert json.loads(row["content"]) == {"note": "CHANGED AFTER REVIEW"}
    assert (row["expires_at"], row["expired_at"], row["trust_tier"]) == (
        None,
        None,
        "DERIVED",
    )
    assert "zq01" in state.memory_message
    assert "v1" in state.memory_message and "v2" in state.memory_message


def test_r1_maintenance_preview_lists_ids_versions_owner_grants(tmp_path: Path) -> None:
    """RED: the maintenance preview renders per-task counts only."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01", created_at=time.time() - 15 * _DAY)
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)

    _keys(state, actions, "w")

    screen = _screen(state)
    assert _lines_with(screen, "expiry_sweep", "zq01", "version=1"), screen
    assert _lines_with(screen, "zq01", "version=1", f"owner=project:{root}"), screen
    assert _lines_with(screen, "grants", "cache_write"), screen


def test_r1_delete_preview_lists_grants_and_consequences(tmp_path: Path) -> None:
    """RED: the delete preview render omits the reviewed grants and the backend's
    `affected` consequences (family, references)."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)

    _keys(state, actions, " ", "d")

    screen = _screen(state)
    assert _lines_with(screen, "grants", "cache_write", "artifact_write"), screen
    assert _lines_with(screen, "zq01", "family=memory", "references=0"), screen


def test_r1_write_and_promote_preview_list_ids_versions_and_draft(
    tmp_path: Path,
) -> None:
    """RED: write/promote previews render `ids [] versions {}` and drop the
    backend's draft (the canonical candidate the apply will create)."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01", note="alpha one", source="s1")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)

    _keys(state, actions, "n", *"hello draft", "enter")
    screen = _screen(state)
    assert "propose preview" in screen
    assert "ids []" not in screen and "versions {}" not in screen
    assert _lines_with(screen, "trust_tier=EXTERNAL_WRITE", "source=tui"), screen
    assert _lines_with(screen, "subject=domain_knowledge", "hello draft"), screen
    _keys(state, actions, "n")

    _cursor_to(state, actions, "zq01")
    _keys(state, actions, "p")
    screen = _screen(state)
    assert "promote preview" in screen
    assert "ids []" not in screen and "versions {}" not in screen
    assert _lines_with(screen, "zq01", "version=1"), screen
    assert _lines_with(screen, "trust_tier=EXTERNAL_WRITE", "source=s1"), screen
    assert _lines_with(screen, "alpha one"), screen


# ---------------------------------------------------------------------------
# Finding 8: paging
# ---------------------------------------------------------------------------


def test_r1_paging_shows_twenty_rows_per_page(tmp_path: Path) -> None:
    """RED: the render lists every row; there are no page keys."""
    root = _root(tmp_path, "a")
    for i in range(45):
        _seed(root, f"zq{i:02d}", note=f"alpha {i}")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    order = _ids(state)
    assert len(order) == 45

    screen = _screen(state)
    assert set(_ROW_ID.findall(screen)) == set(order[:20])
    assert "page 1/3" in screen

    _keys(state, actions, "]")
    screen = _screen(state)
    assert set(_ROW_ID.findall(screen)) == set(order[20:40])
    assert "page 2/3" in screen

    _keys(state, actions, "[")
    screen = _screen(state)
    assert set(_ROW_ID.findall(screen)) == set(order[:20])
    assert "page 1/3" in screen


# ---------------------------------------------------------------------------
# Findings 9, 10, 12: selection, committed-version message, subject validation
# ---------------------------------------------------------------------------


def test_r1_archive_and_promote_apply_to_every_selected_row(tmp_path: Path) -> None:
    """RED: archive and promote act on the cursor row only; the selection is
    honored by delete alone."""
    root = _root(tmp_path, "a")
    for artifact_id in ("zq01", "zq02", "zq03"):
        _seed(root, artifact_id, note=f"alpha {artifact_id}")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)

    _cursor_to(state, actions, "zq01")
    _keys(state, actions, " ")
    _cursor_to(state, actions, "zq02")
    _keys(state, actions, " ", "a")
    assert _lines_with(_screen(state), "archive preview", "zq01", "zq02")
    _keys(state, actions, "y")

    rows = _rows(root)
    for artifact_id in ("zq01", "zq02"):
        assert rows[artifact_id]["artifact_version"] == 2
        assert rows[artifact_id]["archived_at"] is not None
    assert (rows["zq03"]["artifact_version"], rows["zq03"]["archived_at"]) == (1, None)

    promote_root = _root(tmp_path, "b")
    for artifact_id in ("zq04", "zq05", "zq06"):
        _seed(
            promote_root, artifact_id, note=f"alpha {artifact_id}", source=artifact_id
        )
    before = set(_rows(promote_root))
    state = _state(tmp_path, promote_root)
    _enter_memory(state, actions)
    _browse(state, actions)
    _cursor_to(state, actions, "zq04")
    _keys(state, actions, " ")
    _cursor_to(state, actions, "zq05")
    _keys(state, actions, " ", "p")
    assert _lines_with(_screen(state), "promote preview", "zq04", "zq05")
    _keys(state, actions, "y")

    after = _rows(promote_root)
    candidates = [after[i] for i in set(after) - before]
    assert sorted(json.loads(c["content"])["note"] for c in candidates) == [
        "alpha zq04",
        "alpha zq05",
    ]


def test_r1_archive_message_reports_committed_version(tmp_path: Path) -> None:
    """RED: the success message names the pre-apply version ("archived zq01 (v1)")."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)

    _keys(state, actions, "a", "y")

    assert _row(root, "zq01")["artifact_version"] == 2
    assert "zq01" in state.memory_message
    assert "v2" in state.memory_message
    assert "v1" not in state.memory_message


def test_r1_create_form_rejects_unknown_subject_before_backend(tmp_path: Path) -> None:
    """RED: the create form checks presence only, so an unknown subject reaches the
    backend as a write preview."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    memory_run = _RealMemoryRun()
    state = _state(tmp_path, root)
    actions = _actions(memory_run)
    _enter_memory(state, actions)
    _keys(state, actions, "n", *"note text", "tab")
    assert state.memory_create_field == "subject"
    _keys(state, actions, *["backspace"] * len(state.memory_subject), *"bogus")
    calls_before = len(memory_run.operations)

    _keys(state, actions, "enter")

    assert memory_run.operations[calls_before:] == []
    for subject in get_args(MemorySubject):
        assert subject in state.memory_message, state.memory_message
    assert not (set(_rows(root)) - {"zq01"})


# ---------------------------------------------------------------------------
# Finding 7: corrupt store, and maintenance creates nothing
# ---------------------------------------------------------------------------


def test_r1_corrupt_store_renders_reason_and_writes_nothing(tmp_path: Path) -> None:
    """RED: entering Memory and searching show the corrupt reason, but the
    maintenance preview reaches `MemoryStoreUnreadableError` and reports a
    retryable read conflict ("... (read_conflict); retry") instead of the corrupt
    store."""
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    (root / ".rush" / "memory.db").write_bytes(b"not a database" * 100)
    before = _files(root / ".rush")
    reason = readonly_view_reason("corrupt")
    state = _state(tmp_path, root)
    actions = _actions()

    _enter_memory(state, actions)
    assert reason in _screen(state)
    _browse(state, actions)
    assert reason in state.memory_message
    _keys(state, actions, "w")
    assert reason in state.memory_message, state.memory_message
    assert "retry" not in state.memory_message

    assert _files(root / ".rush") == before


_MAINTENANCE_STATUS_COLUMNS = {
    "trust_tier",
    "corroboration_count",
    "promoted_at",
    "signature",
    "stale",
    "expires_at",
    "expired_at",
    "expired_by",
    "artifact_version",
}


def test_r1_maintenance_never_creates_rows_or_enables_learning(tmp_path: Path) -> None:
    """Guard for the plan clause "does not silently enable learning or create
    synthetic data": a real maintenance apply through the TUI keeps the row id set,
    changes only status columns of previewed candidates, and creates or changes no
    file other than the memory database."""
    root = _root(tmp_path, "a")
    for i, source in enumerate(("sa", "sb", "sc")):
        _seed(root, f"zq0{i}", note=f"alpha {i}", source=source)
    _seed(root, "zq10", created_at=time.time() - 15 * _DAY)
    _seed(root, "zq11", symbol_ref="missing.py::Sym", content_hash="deadbeef")
    rows_before = _rows(root)
    files_before = {
        path: digest
        for path, digest in _files(tmp_path).items()
        if not Path(path).name.startswith("memory.db")
    }
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _keys(state, actions, "w")
    previewed = {
        artifact_id
        for entry in state.memory_pending_maintain or []
        for artifact_id in entry["candidate_ids"]
    }
    assert previewed

    _keys(state, actions, "y")

    rows_after = _rows(root)
    assert set(rows_after) == set(rows_before)
    for artifact_id, before in rows_before.items():
        changed = {c for c in before if rows_after[artifact_id][c] != before[c]}
        if artifact_id in previewed:
            assert changed <= _MAINTENANCE_STATUS_COLUMNS, (artifact_id, changed)
        else:
            assert not changed, (artifact_id, changed)
    files_after = {
        path: digest
        for path, digest in _files(tmp_path).items()
        if not Path(path).name.startswith("memory.db")
    }
    assert files_after == files_before


# ---------------------------------------------------------------------------
# T28-D review round 2: promote binds the reviewed source row and version;
# delete reports a denied or conflicting outcome instead of a zero-count
# success; a refresh after an outcome keeps that outcome's message.
# ---------------------------------------------------------------------------


def _archive_outside_tui(root: Path, artifact_id: str, version: int) -> None:
    store = TypedArtifactStore(root)
    try:
        store.archive(
            artifact_id, expected_version=version, scope="domain_knowledge", apply=True
        )
    finally:
        store.close()


def _promote_preview(tmp_path: Path, root: Path) -> tuple[TuiState, ScanActions]:
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    _cursor_to(state, actions, "zq01")
    _keys(state, actions, "p")
    assert _lines_with(_screen(state), "promote preview", "zq01")
    return state, actions


def test_r2_promote_refuses_source_edited_after_preview(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    state, actions = _promote_preview(tmp_path, root)
    before = set(_rows(root))
    _edit_outside_tui(root, "zq01", "beta", 1)

    _keys(state, actions, "y")

    assert set(_rows(root)) == before, "a candidate was created from stale content"
    assert _row(root, "zq01")["artifact_version"] == 2
    assert "changed since review" in state.memory_message, state.memory_message
    assert "reviewed v1, now v2" in state.memory_message, state.memory_message


def test_r2_promote_refuses_source_archived_after_preview(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    state, actions = _promote_preview(tmp_path, root)
    before = set(_rows(root))
    _archive_outside_tui(root, "zq01", 1)

    _keys(state, actions, "y")

    assert set(_rows(root)) == before, "an archived row was revived as a candidate"
    assert "it was archived" in state.memory_message, state.memory_message


def test_r2_promote_denial_names_the_created_candidate(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    state, actions = _promote_preview(tmp_path, root)
    before = set(_rows(root))

    _keys(state, actions, "y")

    created = set(_rows(root)) - before
    assert len(created) == 1, created
    (candidate_id,) = created
    assert "promotion denied" in state.memory_message, state.memory_message
    assert f"candidate {candidate_id} v1" in state.memory_message, state.memory_message


def test_r2_delete_denied_preview_is_not_held(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01", owner=OwnerScope(kind="user", id="alice"))
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)

    _keys(state, actions, " ", "d")

    assert state.memory_pending_delete is None
    assert "delete refused: E_OWNER" in state.memory_message, state.memory_message
    assert "permanently deletes" not in _screen(state)
    _keys(state, actions, "y")
    assert "zq01" in _rows(root)


def test_r2_delete_conflict_reports_the_change_and_deletes_nothing(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    _seed(root, "zq02", note="alpha two")
    state = _state(tmp_path, root)
    actions = _actions()
    _enter_memory(state, actions)
    _browse(state, actions)
    _cursor_to(state, actions, "zq01")
    _keys(state, actions, " ")
    _cursor_to(state, actions, "zq02")
    _keys(state, actions, " ", "d")
    assert state.memory_pending_delete is not None
    _edit_outside_tui(root, "zq02", "alpha changed", 1)

    _keys(state, actions, "y")

    rows = _rows(root)
    assert {"zq01", "zq02"} <= set(rows), "a reviewed row was deleted on conflict"
    assert rows["zq02"]["artifact_version"] == 2
    assert "changed since the preview" in state.memory_message, state.memory_message
    assert "deleted 0" not in state.memory_message


def test_r2_refresh_without_announce_keeps_the_outcome_message(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path, "a")
    state = _state(tmp_path, root)
    actions = _actions()
    state.memory_message = "maintenance: expiry_sweep changed 1"

    tui_mod._memory_refresh(state, state.active_project, actions, announce=False)

    assert state.memory_message == "maintenance: expiry_sweep changed 1"


# ---------------------------------------------------------------------------
# T28 (plan line 431): memory work runs off the input path
# ---------------------------------------------------------------------------


def _await_post(state: TuiState) -> None:
    """Waits (bounded) until a worker has posted to `state.result_queue`."""
    deadline = time.monotonic() + 2
    while state.result_queue.empty():
        assert time.monotonic() < deadline, "no worker result was posted"
        time.sleep(0.005)


class _OffKeyThreadRun(_RealMemoryRun):
    """Raises when called on the thread that dispatches keys."""

    def __init__(self) -> None:
        super().__init__()
        self.key_thread = threading.get_ident()

    def __call__(self, root: Path, **kwargs: Any) -> Any:
        if threading.get_ident() == self.key_thread:
            raise AssertionError(
                f"memory_run({kwargs.get('operation')}) ran on the key thread"
            )
        return super().__call__(root, **kwargs)


class _GatedRun(_RealMemoryRun):
    """Holds each call matching `root`/`operation` until `gate` is set."""

    def __init__(self) -> None:
        super().__init__()
        self.root: Path | None = None
        self.operation: str | None = None
        self.gate = threading.Event()
        self.started = threading.Event()
        self.finished = threading.Event()

    def hold(self, *, root: Path | None = None, operation: str | None = None) -> None:
        self.root, self.operation = root, operation
        self.gate.clear()
        self.started.clear()
        self.finished.clear()

    def __call__(self, root: Path, **kwargs: Any) -> Any:
        held = (self.root is None or root == self.root) and (
            self.operation is None or kwargs.get("operation") == self.operation
        )
        if not held or (self.root is None and self.operation is None):
            return super().__call__(root, **kwargs)
        self.started.set()
        self.gate.wait(5)
        try:
            return super().__call__(root, **kwargs)
        finally:
            self.finished.set()


def test_memory_key_path_never_calls_memory_run(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    _seed(root, "zq02")
    _seed(root, "zq03", created_at=time.time() - 15 * _DAY)
    run = _OffKeyThreadRun()
    state = _state(tmp_path, root)
    actions = _actions(run)
    _enter_memory(state, actions)
    _browse(state, actions)
    assert sorted(_ids(state)) == ["zq01", "zq02", "zq03"], state.memory_message

    _cursor_to(state, actions, "zq01")
    _keys(state, actions, "x")
    assert state.memory_expanded is not None, state.memory_message

    _keys(state, actions, "a")
    assert "archive preview" in state.memory_message
    _keys(state, actions, "y")
    assert _row(root, "zq01")["artifact_version"] == 2
    assert _row(root, "zq01")["archived_at"] is not None

    _cursor_to(state, actions, "zq02")
    _keys(state, actions, "d")
    assert "record(s) selected" in state.memory_message
    _keys(state, actions, "y")
    assert "zq02" not in _rows(root)
    assert "deleted 1 record(s)" in state.memory_message

    _keys(state, actions, "w")
    assert "expiry_sweep 1" in state.memory_message
    _keys(state, actions, "y")
    assert _row(root, "zq03")["artifact_version"] == 2
    assert {"list", "expand", "archive", "delete", "maintain"} <= set(run.operations)


def test_memory_result_for_old_project_is_discarded(tmp_path: Path) -> None:
    a = _root(tmp_path, "a")
    b = _root(tmp_path, "b")
    ids = (_register(tmp_path, a), _register(tmp_path, b))
    _seed(a, "zq01", owner=OwnerScope("project", ids[0]))
    b_files = _files(b)
    run = _GatedRun()
    state = _state(tmp_path, a, b, project_ids=ids)
    actions = _actions(run)
    _enter_memory(state, actions)
    _browse(state, actions)
    assert _ids(state) == ["zq01"], state.memory_message

    run.hold(root=a, operation="archive")
    tui_mod._dispatch_key(state, "a", actions)
    assert run.started.wait(2)
    # The preview is held only when its result is drained, never before.
    assert state.memory_pending_mutation is None
    assert state.memory_message == "working: archive preview..."

    _switch_project(state, actions, 1, drain=False)
    run.gate.set()
    assert run.finished.wait(2)
    _await_post(state)
    tui_mod._pump(state, actions)

    assert state.memory_pending_mutation is None
    assert "archive preview" not in state.memory_message
    assert "zq01" not in _screen(state)
    _keys(state, actions, "y")
    assert _files(b) == b_files
    row = _row(a, "zq01")
    assert (row["artifact_version"], row["archived_at"]) == (1, None)


def test_help_and_escape_work_while_memory_request_in_flight(tmp_path: Path) -> None:
    root = _root(tmp_path, "a")
    _seed(root, "zq01")
    run = _GatedRun()
    state = _state(tmp_path, root)
    actions = _actions(run)
    _enter_memory(state, actions)
    _browse(state, actions)

    run.hold(operation="expand")
    tui_mod._dispatch_key(state, "x", actions)
    assert run.started.wait(2)
    assert state.memory_request is not None
    assert state.memory_message == "working: expand..."

    tui_mod._dispatch_key(state, "?", actions)
    assert state.mode == "help"
    assert state.memory_request is not None
    tui_mod._dispatch_key(state, "escape", actions)
    assert state.mode == "memory"
    tui_mod._dispatch_key(state, "escape", actions)
    assert state.mode == "memory"
    assert state.memory_request is None
    assert state.memory_message == "expand cancelled"
    run.gate.set()
    assert run.finished.wait(2)
    _await_post(state)
    tui_mod._pump(state, actions)
    assert state.memory_expanded is None
    assert state.memory_message == "expand cancelled"

    run.hold(operation="expand")
    tui_mod._dispatch_key(state, "x", actions)
    assert run.started.wait(2)
    tui_mod._dispatch_key(state, "n", actions)
    assert state.mode == "memory"
    assert state.memory_request is None
    assert state.memory_message == "expand cancelled"
    run.gate.set()
    assert run.finished.wait(2)
    _await_post(state)
    tui_mod._pump(state, actions)
    assert state.memory_expanded is None
    # A second mutation key while one is in flight is refused, never queued.
    run.hold(operation="archive")
    tui_mod._dispatch_key(state, "a", actions)
    assert run.started.wait(2)
    tui_mod._dispatch_key(state, "d", actions)
    assert "still running" in state.memory_message
    tui_mod._dispatch_key(state, "q", actions)
    assert state.should_quit
    run.gate.set()
    assert run.finished.wait(2)
    _await_post(state)
    tui_mod._pump(state, actions)
    assert "archive preview" in state.memory_message
    assert state.memory_pending_delete is None
    assert run.operations.count("delete") == 0
