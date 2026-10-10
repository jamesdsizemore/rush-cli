"""Phase 70 T28-D (scoped memory administration) -- failing-first test matrix.

Binding design: `.scratch/phase-70-design-gate/W4-T23-T29.md` section "### T28-D:
scoped memory administration" plus the shared "### Shared design (all packets)"
bullets that apply to D's own render/read surface (the cross-cutting "Read-only"
rule and X3 terminal-text-safety, both of which D's memory panel touches
directly). Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-
plan.md` **T28-D -- Complete scoped memory administration**.

Test-name mapping (per task instructions -- the brief/plan name a shared file,
`tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`; this packet's
allowed files are limited to exactly one new file, so every case below lives in
this file, and the single brief-named function is kept as
`test_t28d_memory_workflows_matrix` grouping the sub-assertions its own
docstring enumerates, with each individually-testable requirement broken out
into its own `test_t28d_*` function so a single failure names the exact gap):

Cases with no fixed keybinding in the brief (subject cycling, archive/restore,
propose/create, maintenance) are driven through an ASSUMED key chosen for this
test only, named in each test's docstring -- the implementer picks the real
binding; these tests assert the *behavior* (state/call effects), not the key.

Merged state as of this worktree's HEAD (2a664ec): T28 (all of A-F) is NOT
merged. `test_t28a_workspace_and_outcomes` / `_render_app`'s new
section/overlay/focus model do not exist yet, so every test below drives the
CURRENT `mode`-based `TuiState` (mode == "memory"/"memory_search"/etc.), which
is what T28-D's own Deliverables list actually extends
(`_memory_refresh`/`_render_memory_admin`/`_handle_memory_key`/...). No case
here depends on an unmerged predecessor task.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, get_args

import pytest
from rich.console import Console

from rush import tui
from rush import tui as tui_mod
from rush.memory.maintenance import MaintenanceTask
from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    VersionConflictError,
    legacy_owner_scope,
)
from rush.permissions import ExecutionPermissions
from rush.token_economy.telemetry import TelemetryStore
from rush.tools.memory import MemoryTool
from rush.tui import ProjectSeed, ProjectState, ScanActions, TuiState

pytestmark = pytest.mark.usefixtures("_isolated_home", "_no_subprocess_spawns")


# ---------------------------------------------------------------------------
# Local fixtures / helpers (this packet's allowed files are exactly one new
# test file -- no conftest, no shared helper module).
# ---------------------------------------------------------------------------


@pytest.fixture
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp HOME so `default_data_root()`/the project registry never touch a
    real host config (task instruction: "Use temp dirs and a temp HOME.
    Never touch real host configs")."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def _no_subprocess_spawns(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Zero-spawn spy: memory administration must never launch a process.
    Patches both `subprocess.Popen` and `subprocess.run` (task instruction)."""
    calls: list[Any] = []

    def _deny(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        raise AssertionError(f"unexpected subprocess spawn: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "Popen", _deny)
    monkeypatch.setattr(subprocess, "run", _deny)
    return calls


class _MemoryRunSpy:
    """Fake `actions.memory_run` (real production wiring: `MemoryTool().run`,
    see `tui.py` P66-05 comment). Records every call and returns scripted
    responses per operation, defaulting to a plain `ok` envelope so a test
    only has to script the responses it actually cares about."""

    def __init__(
        self, responses: dict[str, list[dict[str, Any]]] | None = None
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = {k: list(v) for k, v in (responses or {}).items()}

    def __call__(self, root: Path, *, operation: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"root": root, "operation": operation, **kwargs})
        queue = self._responses.get(operation)
        response = queue.pop(0) if queue else {"status": "ok", "raw": {}}
        self.calls[-1]["response"] = response
        return response


def _actions(memory_run: _MemoryRunSpy) -> ScanActions:
    """Every non-memory seam is a no-op/None -- T28-D never touches scan,
    handoff, git, or check-suite plumbing."""
    return ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: None,
        rescan_project_run=lambda *a, **k: None,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        memory_run=memory_run,
        run_check_suite=None,
    )


def _drain(state: TuiState, actions: ScanActions) -> None:
    """Pumps like `run_interactive_tui` until no memory request is in flight."""
    deadline = time.monotonic() + 2
    tui_mod._pump(state, actions)
    while state.memory_request is not None:
        assert time.monotonic() < deadline, f"still in flight: {state.memory_request}"
        time.sleep(0.005)
        tui_mod._pump(state, actions)


def _memory_key(state: TuiState, key: str, actions: ScanActions) -> None:
    tui_mod._handle_memory_key(state, key, actions)
    _drain(state, actions)


class _ScriptedReader:
    """Local copy of `tests/test_tui.py::_ScriptedReader` (this packet's
    allowed files forbid a shared helper module)."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = iter(keys)

    def read_key(self, timeout: float) -> str | None:
        return next(self._keys, None)

    def get_size(self) -> tuple[int, int]:
        return (80, 24)


def _run(
    tmp_path: Path,
    keys: list[str],
    memory_run: _MemoryRunSpy,
    *,
    monkeypatch: pytest.MonkeyPatch,
    fixture_sources: list[str] | None = ("fixture-source",),
) -> TuiState:
    """Drives the real interactive loop headlessly (`run_interactive_tui`,
    this project's own test harness -- there is no Textual `App.run_test`
    here; `tui.py` is a custom Rich-Live loop, confirmed by reading
    `tests/test_tui.py::_ScriptedReader`/`run_interactive_tui` usage first).

    `_memory_sources_and_state` is monkeypatched to a fixed known-sources
    list so every test exercises the TUI dispatch contract under test,
    never a real `.rush/memory.db` (no such file is ever created in
    `tmp_path`) -- matching "no network calls, never touch real host
    configs" without needing a full schema fixture per case.
    """
    monkeypatch.setattr(
        tui_mod,
        "_memory_sources_and_state",
        lambda project: (list(fixture_sources or []), None),
    )
    dispatch = tui_mod._dispatch_key

    def _dispatch_and_drain(state: TuiState, key: str, actions: ScanActions) -> None:
        dispatch(state, key, actions)
        _drain(state, actions)

    monkeypatch.setattr(tui_mod, "_dispatch_key", _dispatch_and_drain)
    seed = ProjectSeed(name="demo", root=tmp_path / "project", results=[])
    return tui_mod.run_interactive_tui(
        [seed],
        key_reader=_ScriptedReader([*keys, "q"]),
        actions=_actions(memory_run),
        use_live=False,
        max_ticks=200,
    )


def _state_and_project(tmp_path: Path) -> tuple[TuiState, ProjectState]:
    """Direct construction for cases with no keybinding yet (filters, edit
    full-content, promote grants, conflict handling) -- there is no way to
    reach these through `_ScriptedReader` because the key that will drive
    them doesn't exist in `_handle_memory_key` yet."""
    project = ProjectState(name="demo", root=tmp_path / "project")
    state = TuiState(projects=[project])
    state.mode = "memory"
    return state, project


def _seed_promote_row(
    state: TuiState, project: ProjectState, item: dict[str, Any]
) -> None:
    """Keep spy preview tests grounded in the selected real source revision."""
    project.root.mkdir(parents=True, exist_ok=True)
    scope = tui_mod._memory_owner_scope(state, project)
    item.update(
        subject=state.memory_subject,
        symbol_ref=None,
        owner_scope=scope,
    )
    TypedArtifactStore(project.root).write(
        MemoryArtifact(
            id=item["id"],
            family="memory",
            subject=state.memory_subject,
            trust_tier="EXTERNAL_WRITE",
            content=item["content"],
            source=item["source"],
            created_at=time.time(),
            owner_scope=OwnerScope(scope["kind"], scope["id"]),
        )
    )


# ---------------------------------------------------------------------------
# Browse without a query (T28-D required behavior, bullet 1)
# ---------------------------------------------------------------------------


def test_t28d_browse_on_entry_shows_items_without_a_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Memory initially browses T18/T20 useful records without requiring a
    query." Today, entering memory admin ("M") only sets a hint message;
    `_memory_refresh` itself still requires `state.memory_query_buffer` to
    be non-empty ("type a query, then Enter"). RED: memory_items stays
    empty on entry alone."""
    spy = _MemoryRunSpy({"list": [{"status": "ok", "raw": [{"id": "a1"}]}]})
    state = _run(tmp_path, ["M"], spy, monkeypatch=monkeypatch)
    assert state.memory_items, (
        "T28-D requires memory admin to browse on entry with no typed query; "
        f"got memory_items={state.memory_items!r}, message={state.memory_message!r}"
    )


# ---------------------------------------------------------------------------
# Subject is selectable (T28-D required behavior, bullet 1)
# ---------------------------------------------------------------------------


def test_t28d_subject_is_selectable_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Subject is selectable rather than fixed to domain_knowledge until
    restart." Assumed key for this test only: "S" cycles subject -- no
    binding for this exists in `_handle_memory_key` today, so the key is
    inert and `memory_subject` never changes. RED."""
    spy = _MemoryRunSpy()
    state = _run(tmp_path, ["M", "S"], spy, monkeypatch=monkeypatch)
    assert state.memory_subject != "domain_knowledge", (
        "T28-D requires the memory subject to be switchable in-session; "
        f"still stuck at the fixed default {state.memory_subject!r}"
    )


# ---------------------------------------------------------------------------
# Filters: subject/owner/trust/source/freshness/archived (T28-D bullet 2)
# ---------------------------------------------------------------------------


def test_t28d_query_includes_trust_filter(tmp_path: Path) -> None:
    """`_memory_refresh` must forward a trust filter to `memory_run` when one
    is set. No such state field or forwarding exists today: `_memory_refresh`
    calls `memory_run` with only `subject`/`query`/`session_allowlist`. RED
    via `getattr` so a genuinely-missing field fails as a clean assertion,
    never an `AttributeError` crash."""
    state, project = _state_and_project(tmp_path)
    state.memory_query_buffer = "anything"
    state.memory_filter_trust = "verified"
    spy = _MemoryRunSpy({"list": [{"status": "ok", "raw": []}]})
    actions = _actions(spy)

    original = tui_mod._memory_sources_and_state
    tui_mod._memory_sources_and_state = lambda project: (["fixture-source"], None)
    try:
        tui_mod._memory_refresh(state, project, actions)
    finally:
        tui_mod._memory_sources_and_state = original
    assert spy.calls, "memory_run was never called"
    assert spy.calls[-1].get("trust_filter") == "verified", (
        "T28-D requires the trust filter to reach memory_run; "
        f"call kwargs were {spy.calls[-1]!r}"
    )


def test_t28d_query_includes_owner_source_freshness_archived_filters(
    tmp_path: Path,
) -> None:
    """Same requirement for owner scope, source, freshness, and archived --
    grouped into one test since they are the same gap (no filter state, no
    forwarding) rather than four independent code paths."""
    state, project = _state_and_project(tmp_path)
    state.memory_query_buffer = "anything"
    state.memory_filter_source = "cli"
    state.memory_filter_freshness = "stale"
    state.memory_filter_archived = True
    spy = _MemoryRunSpy({"list": [{"status": "ok", "raw": []}]})
    actions = _actions(spy)

    original = tui_mod._memory_sources_and_state
    tui_mod._memory_sources_and_state = lambda project: (["fixture-source"], None)
    try:
        tui_mod._memory_refresh(state, project, actions)
    finally:
        tui_mod._memory_sources_and_state = original
    assert spy.calls, "memory_run was never called"
    call = spy.calls[-1]
    missing = [
        key
        for key, expected in (
            ("source_filter", "cli"),
            ("freshness_filter", "stale"),
            ("archived_filter", True),
        )
        if call.get(key) != expected
    ]
    assert not missing, (
        "T28-D requires source/freshness/archived filters to reach "
        f"memory_run; missing/mismatched: {missing!r}, call was {call!r}"
    )


# ---------------------------------------------------------------------------
# Edit exposes full structured content, not a note-only field (T28-D bullet 2)
# ---------------------------------------------------------------------------


def test_t28d_edit_commits_full_structured_content(tmp_path: Path) -> None:
    """Today `_memory_edit_commit` always merges only a `note` key into
    `content`, regardless of what the admin actually edited (plan: "edit
    (full structured content, replacing the note-only editor)"). RED: a
    `title` field the test "edits" never reaches the committed content."""
    state, project = _state_and_project(tmp_path)
    item = {
        "id": "a1",
        "artifact_version": 3,
        "content": {"title": "orig-title", "note": "orig-note"},
    }
    state.memory_items = [item]
    state.memory_selected_index = 0
    # Simulate an admin editing the *title*, not the note -- current code has
    # no field-selection concept, only a single `memory_edit_buffer` string
    # that always lands in "note".
    state.memory_edit_buffer = "new-title"
    state.memory_edit_field = "title"
    spy = _MemoryRunSpy({"edit": [{"raw": {"code": "OK"}}]})
    tui_mod._memory_edit_commit(state, project, _actions(spy))
    assert spy.calls, "memory_run was never called for edit"
    sent_content = spy.calls[-1].get("request", {}).get("content", {})
    assert sent_content.get("title") == "new-title", (
        "T28-D requires a full structured-content edit form, not a hardcoded "
        f"note-only field; committed content was {sent_content!r}"
    )


def test_t28d_edit_conflict_keeps_entered_content(tmp_path: Path) -> None:
    """ "Mutation conflict keeps entered content and offers refresh/review,
    never blind retry." Today `_memory_edit_commit` unconditionally clears
    `memory_edit_buffer = None` at the end, even on a non-OK (conflict)
    response. RED: the buffer is lost even though the plan requires it kept."""
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 3, "content": {"note": "orig"}}
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_edit_buffer = "in-flight-edit"
    spy = _MemoryRunSpy({"edit": [{"raw": {"code": "VERSION_CONFLICT"}}]})
    tui_mod._memory_edit_commit(state, project, _actions(spy))
    assert state.memory_edit_buffer == "in-flight-edit", (
        "T28-D requires a mutation conflict to keep the entered content for "
        f"review, but memory_edit_buffer is {state.memory_edit_buffer!r}"
    )


# ---------------------------------------------------------------------------
# Every mutating form previews (apply=False) before applying, with reviewed
# grants -- not the hardcoded ExecutionPermissions the current code sends
# (T28-D bullet 3; brief: "Flow: each form previews with apply=False
# (store.preview_mutation is read-only, :1461-1500) ... replacing the
# hardcoded grants at tui.py:1471,1552,1592").
# ---------------------------------------------------------------------------


def test_t28d_promote_previews_before_applying(tmp_path: Path) -> None:
    """Today `_memory_promote_selected` makes exactly one `memory_run` call
    (straight to apply) -- there is no preview step at all. RED: expects two
    calls, a preview then the apply, matching the delete flow's existing
    preview/apply shape."""
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 1, "content": {}, "source": "cli"}
    _seed_promote_row(state, project, item)
    state.memory_items = [item]
    state.memory_selected_index = 0
    spy = _MemoryRunSpy(
        {"promote": [{"raw": {"promoted": True, "new_tier": "verified"}}]}
    )
    tui_mod._memory_promote_selected(state, project, _actions(spy))
    _memory_key(state, "y", _actions(spy))
    operations = [c["operation"] for c in spy.calls]
    assert "promote" in operations and len(spy.calls) >= 2, (
        "T28-D requires promote to preview (apply=False) before applying; "
        f"only saw operations {operations!r}"
    )


def test_t28d_promote_uses_reviewed_grants_not_hardcoded(tmp_path: Path) -> None:
    """Today `_memory_promote_selected` always sends
    `ExecutionPermissions(cache_write=True)` verbatim. RED: when the (not-yet-
    existing) preview step declares `artifact_write` is also required, the
    applied permissions must reflect that, not the fixed constant."""
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 1, "content": {}, "source": "cli"}
    _seed_promote_row(state, project, item)
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_pending_promote = {"required_grants": ["artifact_write"]}
    spy = _MemoryRunSpy(
        {"promote": [{"raw": {"promoted": True, "new_tier": "verified"}}]}
    )
    tui_mod._memory_promote_selected(state, project, _actions(spy))
    _memory_key(state, "y", _actions(spy))
    apply_calls = [c for c in spy.calls if c["operation"] == "promote"]
    assert apply_calls, "promote was never dispatched"
    permissions = apply_calls[-1].get("permissions")
    assert (
        isinstance(permissions, ExecutionPermissions) and permissions.artifact_write
    ), (
        "T28-D requires reviewed, not hardcoded, grants; "
        f"got permissions={permissions!r}"
    )


def _preview_missing_fields(call: dict[str, Any]) -> list[str]:
    """What a form's preview call must carry per the brief ("shows the
    affected IDs and versions, owner, and required grants"). Looks in
    `call["request"]` first (the shape `delete`/`edit` already use), then
    falls back to the call's own top-level kwargs (the shape `promote`
    uses today)."""
    request = call.get("request") if isinstance(call.get("request"), dict) else call
    payload = request
    if call.get("operation") in ("write", "promote"):
        # write/promote requests carry only apply + required_grants; the preview
        # names the affected ids/versions/owner in its response (memory.py:2941).
        raw = (call.get("response") or {}).get("raw") or {}
        if request.get("apply") is not False:
            return ["apply=False"]
        payload = {**raw, "required_grants": request.get("required_grants")}
    missing = []
    if not (
        "target_ids" in payload or payload.get("artifact_ids") or payload.get("id")
    ):
        missing.append("ids")
    if not (
        "expected_revisions" in payload
        or payload.get("expected_revisions")
        or payload.get("expected_version")
    ):
        missing.append("versions")
    if not payload.get("owner_scope"):
        missing.append("owner")
    if not payload.get("required_grants"):
        missing.append("required_grants")
    return missing


def _preview_form(
    form: str, state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    if form == "delete":
        tui_mod._memory_delete_preview(state, project, actions)
    elif form == "edit":
        tui_mod._memory_edit_commit(state, project, actions)
    elif form == "promote":
        tui_mod._memory_promote_selected(state, project, actions)
    elif form in ("archive", "restore"):
        _memory_key(state, "a", actions)
    elif form == "write_propose":
        # A create has no prior version: its preview names the new id with
        # expected revision 0 ("must not exist yet").
        state.memory_create_buffer = {
            "subject": "domain_knowledge",
            "source": "cli",
            "content": "proposed note",
        }
        tui_mod._memory_create_commit(state, project, actions)
    else:
        raise AssertionError(f"unknown form {form!r}")


def _run_form(
    form: str, state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    """Preview, then confirm with "y" (plan line 419: every form applies only on y)."""
    _preview_form(form, state, project, actions)
    _memory_key(state, "y", actions)


@pytest.mark.parametrize(
    "form", ["write_propose", "edit", "promote", "archive", "restore", "delete"]
)
def test_t28d_every_form_previews_with_reviewed_grants(
    form: str, tmp_path: Path
) -> None:
    """T28-D bullet 3, generalized across every mutating form: "each form
    previews with apply=False..., shows the affected IDs and versions,
    owner, and required grants, and applies only with the reviewed
    grants." RED per form:
    - write_propose: no dispatch function exists at all -- zero calls.
    - edit/promote/archive/restore: exactly one call (or zero), no
      preview step at all.
    - delete: the only form with an existing two-step preview/apply --
      RED here specifically because its preview payload never carries
      `required_grants`, so the apply's permissions can't be "reviewed"."""
    state, project = _state_and_project(tmp_path)
    item = {
        "id": "a1",
        "artifact_version": 1,
        "content": {"note": "x"},
        "source": "cli",
        # "restore" acts on an already-archived row (archived=False is the
        # expected effect); every other form uses a live, unarchived row.
        "archived_at": "2026-01-01" if form == "restore" else None,
    }
    if form == "promote":
        _seed_promote_row(state, project, item)
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_selected_ids = {"a1"}
    state.memory_edit_buffer = "y"
    new_preview = {
        "status": "ok",
        "raw": {
            "apply": False,
            "target_ids": [],
            "expected_revisions": {},
            "owner_scope": {"kind": "project", "id": "p"},
            "required_grants": ["cache_write"],
            "missing_grants": [],
            "draft": {},
        },
    }
    spy = _MemoryRunSpy(
        {
            "edit": [{"raw": {"code": "OK"}}],
            "promote": [
                new_preview,
                {"raw": {"promoted": True, "new_tier": "verified"}},
            ],
            "write": [
                new_preview,
                {"status": "ok", "raw": {"id": "new-1", "artifact_version": 1}},
            ],
            "archive": [{"raw": {"code": "OK"}}],
            "delete": [
                {"raw": {"code": "OK", "data": {"affected": ["a1"]}}},
                {"raw": {"code": "OK", "data": {"affected": ["a1"]}}},
            ],
        }
    )
    _run_form(form, state, project, _actions(spy))
    assert len(spy.calls) >= 2, (
        f"{form}: T28-D requires a preview (apply=False) call before the "
        f"apply call; got {spy.calls!r}"
    )
    preview_call, apply_call = spy.calls[0], spy.calls[1]
    missing = _preview_missing_fields(preview_call)
    assert not missing, (
        f"{form}: T28-D requires the preview to carry {missing!r}; "
        f"preview call was {preview_call!r}"
    )
    reviewed_grants = (preview_call.get("request") or preview_call).get(
        "required_grants"
    )
    permissions = apply_call.get("permissions")
    assert isinstance(permissions, ExecutionPermissions) and reviewed_grants, (
        f"{form}: T28-D requires the apply call's permissions to come from "
        f"the reviewed grants, not a hardcoded constant; permissions="
        f"{permissions!r}, reviewed_grants={reviewed_grants!r}"
    )


def test_t28d_delete_multiselect_preview_and_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T28-D bullet 1: "Delete is multi-select"; the preview must list all
    selected IDs and versions, and the apply must send exactly those. The
    dispatch already handles multiple IDs correctly (`_memory_delete_preview`
    filters `memory_items` by `memory_selected_ids`), but the *rendered*
    preview only ever shows a bare count ("pending delete: N record(s)")
    -- never the actual IDs/versions -- so this is RED on the render, not
    the dispatch, matching the brief's "shows the affected IDs and
    versions" requirement."""
    spy = _MemoryRunSpy(
        {
            "delete": [
                {"raw": {"code": "OK", "data": {"affected": ["a1", "a2"]}}},
                {"raw": {"code": "OK", "data": {"affected": ["a1", "a2"]}}},
            ]
        }
    )
    state = _run(tmp_path, ["M"], spy, monkeypatch=monkeypatch)
    state.memory_items = [
        {"id": "a1", "artifact_version": 1},
        {"id": "a2", "artifact_version": 7},
    ]
    state.memory_selected_ids = {"a1", "a2"}
    project = state.active_project
    actions = _actions(spy)
    tui_mod._memory_delete_preview(state, project, actions)
    assert state.memory_pending_delete["artifact_ids"] == ["a1", "a2"]
    assert state.memory_pending_delete["expected_revisions"] == {"a1": 1, "a2": 7}
    from rich.console import Console

    console = Console(record=True, width=200, no_color=True)
    console.print(tui_mod._render_memory_admin(state))
    rendered = console.export_text()
    missing = [needle for needle in ("a1", "a2", "1", "7") if needle not in rendered]
    assert not missing, (
        "T28-D requires the delete preview to render every selected ID and "
        f"version, not just a count; missing {missing!r} from rendered "
        f"output:\n{rendered}"
    )
    tui_mod._memory_delete_apply(state, project, actions)
    delete_calls = [c for c in spy.calls if c["operation"] == "delete"]
    assert delete_calls[-1]["request"]["artifact_ids"] == ["a1", "a2"]


def test_t28d_delete_preview_then_apply_matches_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep-green guard: the existing delete preview -> confirm -> apply
    two-step flow (already implemented pre-T28-D) must keep working, and the
    applied IDs must equal the previewed IDs -- this should PASS today,
    proving T28-D's new preview requirement is not itself the thing
    breaking the one form that already has it."""
    spy = _MemoryRunSpy(
        {
            "delete": [
                {"raw": {"code": "OK", "data": {"affected": ["a1"]}}},
                {"raw": {"code": "OK", "data": {"affected": ["a1"]}}},
            ]
        }
    )
    state = _run(
        tmp_path,
        ["M"],
        spy,
        monkeypatch=monkeypatch,
    )
    state.memory_items = [{"id": "a1", "artifact_version": 1}]
    state.memory_selected_ids = {"a1"}
    project = state.active_project
    actions = _actions(spy)
    tui_mod._memory_delete_preview(state, project, actions)
    assert state.memory_pending_delete is not None
    previewed_ids = state.memory_pending_delete["artifact_ids"]
    tui_mod._memory_delete_apply(state, project, actions)
    delete_calls = [c for c in spy.calls if c["operation"] == "delete"]
    assert len(delete_calls) == 2
    assert delete_calls[0]["request"]["apply"] is False
    assert delete_calls[1]["request"]["apply"] is True
    assert delete_calls[1]["request"]["artifact_ids"] == previewed_ids == ["a1"]


def test_t28d_delete_cancel_makes_zero_apply_calls(tmp_path: Path) -> None:
    """Keep-green guard: cancelling a delete preview (`n`) must never reach
    apply -- this already works today."""
    state, project = _state_and_project(tmp_path)
    state.memory_items = [{"id": "a1", "artifact_version": 1}]
    state.memory_selected_ids = {"a1"}
    spy = _MemoryRunSpy(
        {"delete": [{"raw": {"code": "OK", "data": {"affected": ["a1"]}}}]}
    )
    actions = _actions(spy)
    tui_mod._memory_delete_preview(state, project, actions)
    _memory_key(state, "n", actions)
    assert state.memory_pending_delete is None
    apply_calls = [
        c
        for c in spy.calls
        if c["operation"] == "delete" and c.get("request", {}).get("apply")
    ]
    assert not apply_calls, f"cancel must make zero apply calls, got {apply_calls!r}"


def test_t28d_promote_denied_insufficient_corroboration_regression(
    tmp_path: Path,
) -> None:
    """Keep-green guard: a lone-source promote is still denied by the real
    corroboration gate and rendered as a message, not silently accepted --
    this is existing, correct T20-era behavior T28-D must not regress."""
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 1, "content": {}, "source": "cli"}
    _seed_promote_row(state, project, item)
    state.memory_items = [item]
    state.memory_selected_index = 0
    # Preview first (never carries a denial: corroboration runs at apply), then the apply's denial.
    spy = _MemoryRunSpy(
        {
            "promote": [
                {
                    "status": "ok",
                    "raw": {
                        "apply": False,
                        "target_ids": [],
                        "expected_revisions": {},
                        "owner_scope": {"kind": "project", "id": "p"},
                        "required_grants": ["cache_write"],
                        "missing_grants": [],
                        "draft": {},
                    },
                },
                {
                    "raw": {
                        "promoted": False,
                        "denial_reason": "insufficient_corroboration",
                    }
                },
            ]
        }
    )
    tui_mod._memory_promote_selected(state, project, _actions(spy))
    _memory_key(state, "y", _actions(spy))
    assert "insufficient_corroboration" in state.memory_message


# ---------------------------------------------------------------------------
# Archive / restore (T28-D bullet 2: "archive/restore (archived=False,
# store.py:1148-1170)") -- entirely missing today.
# ---------------------------------------------------------------------------


def test_t28d_archive_selected_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assumed key for this test only: "a" archives the selected row. No case
    in `_handle_memory_key` handles "a" today (only x/p/e/o/d/y and
    up/down/space/escape//), so this key is a no-op and `memory_run` is never
    called. RED."""
    spy = _MemoryRunSpy({"archive": [{"raw": {"code": "OK"}}]})
    state = _run(tmp_path, ["M", "a"], spy, monkeypatch=monkeypatch)
    state.memory_items = [{"id": "a1", "artifact_version": 1, "archived_at": None}]
    state.memory_selected_index = 0
    _memory_key(state, "a", _actions(spy))
    archive_calls = [c for c in spy.calls if c["operation"] == "archive"]
    assert archive_calls, "T28-D requires an archive action; 'a' dispatched nothing"


def test_t28d_restore_clears_archived_flag(tmp_path: Path) -> None:
    """Restoring a previously-archived record must send `archived=False`
    (plan: "archive/restore (archived=False, store.py:1148-1170)"). RED for
    the same reason as archive: no handler exists."""
    state, _project = _state_and_project(tmp_path)
    state.memory_items = [
        {"id": "a1", "artifact_version": 1, "archived_at": "2026-01-01"}
    ]
    state.memory_selected_index = 0
    spy = _MemoryRunSpy({"archive": [{"raw": {"code": "OK"}}]})
    _memory_key(state, "a", _actions(spy))
    archive_calls = [c for c in spy.calls if c["operation"] == "archive"]
    assert (
        archive_calls and archive_calls[-1].get("request", {}).get("archived") is False
    ), f"T28-D requires restore to send archived=False; calls were {spy.calls!r}"


# ---------------------------------------------------------------------------
# Propose/create form (T28-D bullet 2: "Forms expose canonical shared
# MemoryTool operations to propose/create...") -- entirely missing today.
# ---------------------------------------------------------------------------


def test_t28d_propose_create_form_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assumed key for this test only: "n" (new) opens a create/propose
    form. Today "n" is only recognized while a delete preview is pending (as
    its cancel key) -- with no pending delete, it is a pure no-op, so
    `state.mode` never changes. RED."""
    spy = _MemoryRunSpy()
    state = _run(tmp_path, ["M", "n"], spy, monkeypatch=monkeypatch)
    assert state.mode == "memory_create", (
        "T28-D requires a reachable propose/create form; "
        f"mode is still {state.mode!r} after 'n'"
    )


def test_t28d_propose_create_validates_required_fields_before_submit(
    tmp_path: Path,
) -> None:
    """ "Validate required fields before submit." RED: with no create form
    implemented at all, there is no `_memory_create_commit` (or equivalent)
    to reject an empty submission -- `hasattr` fails cleanly rather than the
    test crashing on a missing attribute."""
    assert hasattr(tui_mod, "_memory_create_commit"), (
        "T28-D requires a create-form commit function that validates "
        "required fields before submit; none exists yet"
    )


# ---------------------------------------------------------------------------
# Maintenance (T28-D bullet 2/"Missing deliverable": memory/maintenance.py
# read-only preview whose candidate IDs equal the applied IDs, with zero
# writes on cancel).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("task", get_args(MaintenanceTask))
def test_t28d_maintenance_preview_ids_equal_applied_ids(
    task: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assumed key for this test only: "w" (sWeep) triggers a maintenance
    preview, "y" confirms. Today neither key is handled in memory mode, so
    `memory_run` is never called for a "maintain" operation at all. RED:
    the preview's candidate IDs must equal the IDs actually applied, for
    every real task in `memory/maintenance.py:30-32`
    (`typing.get_args(MaintenanceTask)`, never a guessed literal list)."""
    # "w" previews every task and "y" applies each one: one scripted
    # response per call (four previews, then four applies).
    tasks = len(get_args(MaintenanceTask))
    spy = _MemoryRunSpy(
        {
            "maintain": [
                {"status": "ok", "raw": {"candidate_ids": ["a1", "a2"], "apply": False}}
            ]
            * tasks
            + [{"status": "ok", "raw": {"candidate_ids": ["a1", "a2"], "changed": 2}}]
            * tasks
        }
    )
    _run(tmp_path, ["M", "w", "y"], spy, monkeypatch=monkeypatch)
    maintain_calls = [
        c for c in spy.calls if c["operation"] == "maintain" and c.get("task") == task
    ]
    assert len(maintain_calls) == 2, (
        f"T28-D requires a maintenance preview (apply=False) for task={task!r} "
        f"followed by an applied run (apply=True); saw {maintain_calls!r}"
    )
    assert maintain_calls[0]["request"]["apply"] is False
    preview_ids = maintain_calls[0]["response"]["raw"]["candidate_ids"]
    applied_ids = maintain_calls[1].get("request", {}).get("candidate_ids")
    assert preview_ids == applied_ids == ["a1", "a2"]


@pytest.mark.parametrize("task", get_args(MaintenanceTask))
def test_t28d_maintenance_cancel_makes_zero_apply_calls(
    task: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same feature, cancel path, for every real task name: previewing then
    declining must never call `maintain` with `apply=True`. RED for the
    same missing-handler reason; written as its own case so a future
    "preview happens but cancel still applies" regression fails
    independently of the happy path above."""
    spy = _MemoryRunSpy(
        {
            "maintain": [
                {"status": "ok", "raw": {"candidate_ids": ["a1"], "apply": False}},
            ]
        }
    )
    _run(tmp_path, ["M", "w", "n"], spy, monkeypatch=monkeypatch)
    preview_calls = [
        c for c in spy.calls if c["operation"] == "maintain" and c.get("task") == task
    ]
    assert preview_calls, f"T28-D requires a maintenance preview step for task={task!r}"
    applied = [c for c in preview_calls if c.get("request", {}).get("apply") is True]
    assert not applied, f"cancel must make zero apply calls, got {applied!r}"


# ---------------------------------------------------------------------------
# Shared-design case belonging to D: X3 terminal text safety applied to every
# TUI string cell (`_render_memory_admin` renders raw `str(item.get(...))`
# straight into Table cells today -- no `safe_terminal_text`/`Text(...)`
# wrapping at all).
# ---------------------------------------------------------------------------


def test_t28d_render_escapes_control_bytes_in_memory_rows(tmp_path: Path) -> None:
    """Design brief X3: `"\\x1b[2J"` must never reach the rendered output as
    a raw ESC byte. `_render_memory_admin` puts `str(item.get("source", ""))`
    directly into a `Table` cell with no escaping. RED: the captured console
    output still contains the raw ESC byte."""
    from rich.console import Console

    state = TuiState(projects=[ProjectState(name="demo", root=tmp_path)])
    state.mode = "memory"
    state.memory_items = [
        {
            "id": "a1",
            "trust_tier": "verified",
            "source": "hostile\x1b[2Jpayload",
            "stale": False,
        }
    ]
    panel = tui_mod._render_memory_admin(state)
    console = Console(record=True, width=100, no_color=True)
    console.print(panel)
    output = console.export_text()
    assert "\x1b" not in output, (
        "T28-D/X3 requires every TUI string cell to escape raw control bytes; "
        "found a literal ESC in the rendered memory table"
    )


def test_t28d_render_does_not_crash_on_markup_lookalike_content(tmp_path: Path) -> None:
    """Design brief X3: `"[/bad]"` must never raise `MarkupError`.
    `_render_memory_admin` hands a plain `str` id straight to a `Table` cell,
    which Rich renders through its markup parser by default. RED: this
    currently raises."""
    state = TuiState(projects=[ProjectState(name="demo", root=tmp_path)])
    state.mode = "memory"
    state.memory_items = [
        {"id": "[/bad]", "trust_tier": "verified", "source": "cli", "stale": False}
    ]
    # No pytest.raises: T28-D requires this to succeed. If it still raises
    # MarkupError, that exception is itself the correct RED signal.
    tui_mod._render_memory_admin(state)


# ---------------------------------------------------------------------------
# Missing deliverable: a read-only maintenance-sweep preview in
# `memory/maintenance.py`, against a real seeded store (not the TUI-level
# fake used above -- this tests the new module-level function itself).
# ---------------------------------------------------------------------------


def _db_state(root: Path) -> dict[str, Any]:
    """Local copy of `tests/test_phase70_memory_visibility.py::_db_state`'s
    pattern (this packet's allowed files forbid a shared helper module):
    exact row/schema/byte/journal state, so a preview call can be proven to
    have written nothing."""
    db = root / ".rush" / "memory.db"
    with sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True) as conn:
        state = {
            "memory_artifacts": conn.execute(
                "SELECT * FROM memory_artifacts ORDER BY id"
            ).fetchall(),
        }
    state["sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
    state["journal_files"] = sorted(
        p.name for p in (root / ".rush").iterdir() if p.name.startswith("memory.db-")
    )
    return state


def test_t28d_maintenance_module_gets_a_read_only_candidate_preview(
    tmp_path: Path,
) -> None:
    """Missing deliverable (brief T28-D: "a read-only preview of each
    sweep's candidate IDs using the same SQL predicates, with no lock and
    no writes"; plan T28-D: "Maintenance shows concrete supported action
    and results through existing shared operations"). Neither the brief nor
    the plan pins a function name, so this test searches the real module
    for one and `pytest.fail`s naming exactly what's missing -- never a
    guessed import that would crash with `ImportError` instead.

    Arrange (must pass today, independent of the missing deliverable): seed
    one real corroboration-eligible row via `TypedArtifactStore`/
    `MemoryArtifact` (same producers as
    `tests/test_phase62_maintenance.py::_seed_candidate_rows`) and confirm
    `run_maintenance_cycle("promotion_sweep", ...)` really processes it --
    proving the seed is a genuine sweep candidate before testing the new
    preview against it."""
    from rush.memory.maintenance import run_maintenance_cycle

    owner = legacy_owner_scope(tmp_path)
    store = TypedArtifactStore(tmp_path)
    store.write(
        MemoryArtifact(
            id="candidate-1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"note": "seed"},
            source="tool-1",
            created_at=time.time(),
        )
    )

    # Arrange-assert: the seeded row is a genuine promotion_sweep candidate
    # under the real predicate -- this must pass today.
    result = run_maintenance_cycle(
        "promotion_sweep", project_root=tmp_path, owner_scope=owner
    )
    assert result.processed == 1, (
        "arrange failed: the seeded row was not a real promotion_sweep "
        f"candidate; run_maintenance_cycle returned {result!r}"
    )

    import rush.memory.maintenance as maintenance_module

    candidate_names = ("preview_maintenance_candidates",)
    preview_fn = next(
        (
            getattr(maintenance_module, n)
            for n in candidate_names
            if hasattr(maintenance_module, n)
        ),
        None,
    )
    if preview_fn is None:
        pytest.fail(
            "T28-D requires a read-only maintenance-sweep candidate preview "
            "in memory/maintenance.py (brief W4 T28-D: 'a read-only preview "
            "of each sweep's candidate IDs using the same SQL predicates, "
            f"with no lock and no writes'); none of {candidate_names!r} "
            "exist on rush.memory.maintenance"
        )

    lock_path = tmp_path / ".rush" / "memory-maintenance.lock"
    before = _db_state(tmp_path)
    preview_ids = preview_fn(
        "promotion_sweep", project_root=tmp_path, owner_scope=owner
    )
    assert {row["id"] for row in preview_ids} == {"candidate-1"}, (
        "T28-D requires the preview's candidate IDs to equal what the real "
        f"sweep then processes; got {preview_ids!r}"
    )
    assert not lock_path.exists(), "T28-D requires the preview to take no lock"
    assert _db_state(tmp_path) == before, (
        "T28-D requires the preview to make zero writes -- memory.db bytes "
        "or journal files changed"
    )


# ---------------------------------------------------------------------------
# Conflict: keep entered content AND offer refresh/re-review, and a
# re-review after refresh shows the new version (T28-D bullet 2).
# ---------------------------------------------------------------------------


def test_t28d_edit_conflict_offers_refresh_and_rereview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beyond keeping the entered content (already covered by
    `test_t28d_edit_conflict_keeps_entered_content`), the brief requires
    the conflict to "offer refresh/review, never blind retry." RED: today
    a conflict sets a plain string message and nothing else -- there is no
    state a re-review flow could act on, and no refreshed version is ever
    fetched."""
    state, project = _state_and_project(tmp_path)
    owner = tui_mod._memory_owner_scope(state, project)
    item = {
        "id": "a1",
        "artifact_version": 3,
        "content": {"note": "orig"},
        "source": "fixture-source",
        "owner_scope": owner,
    }
    monkeypatch.setattr(tui_mod, "_memory_known_sources", lambda _: ["fixture-source"])
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_edit_buffer = "in-flight-edit"
    spy = _MemoryRunSpy(
        {
            "edit": [{"raw": {"code": "E_VERSION"}}],
            # A refresh/re-review re-fetches the row; its current version has
            # moved on from the stale `3` this edit started against.
            "list": [
                {
                    "status": "ok",
                    "raw": [
                        {
                            "id": "a1",
                            "artifact_version": 4,
                            "source": "fixture-source",
                            "owner_scope": owner,
                        }
                    ],
                }
            ],
        }
    )
    actions = _actions(spy)
    tui_mod._memory_edit_commit(state, project, actions)
    assert getattr(state, "memory_edit_conflict", None) is not None, (
        "T28-D requires a conflict to offer refresh/re-review, not just a "
        "message; no conflict/re-review state was set"
    )
    refresh = getattr(tui_mod, "_memory_edit_refresh_and_rereview", None)
    assert callable(refresh), (
        "T28-D requires a refresh/re-review action for a mutation conflict; "
        "no such function exists on rush.tui"
    )
    refresh(state, project, actions)
    refreshed = next((i for i in state.memory_items if i.get("id") == "a1"), None)
    assert refreshed is not None and refreshed["artifact_version"] == 4, (
        "T28-D requires a re-review after refresh to show the new version; "
        f"got {refreshed!r}"
    )


# ---------------------------------------------------------------------------
# Receipts/relationships display (T28-D bullet 1: "recorded relationships
# and actual read/write-use receipts").
# ---------------------------------------------------------------------------


def test_t28d_expand_renders_relationships_and_receipts_as_structured_sections(
    tmp_path: Path,
) -> None:
    """RED: `_render_memory_admin` today only ever does
    `Panel(Text(str(state.memory_expanded)), title="expanded")` -- a raw
    Python dict repr, never labelled "Relationships"/"Receipts" sections
    with one row per item carrying its own ID and version."""
    state, _project = _state_and_project(tmp_path)
    state.memory_expanded = {
        "id": "a1",
        "version": 1,
        "offset": 0,
        "next_offset": None,
        "complete": True,
        "content": '{"note": "x"}',
        "relationships": [{"id": "rel-1", "artifact_version": 2, "kind": "cites"}],
        "relationships_complete": True,
        "receipts": [
            {
                "id": "rcpt-1",
                "artifact_version": 1,
                "kind": "read",
                "origin": "telemetry",
            }
        ],
    }

    from rich.console import Console

    console = Console(record=True, width=200, no_color=True)
    console.print(tui_mod._render_memory_admin(state))
    rendered = console.export_text()

    assert "{'" not in rendered, (
        "T28-D requires relationships/receipts to render as labelled "
        f"structured sections, never a raw Python dict repr; got:\n{rendered}"
    )
    missing = [
        needle
        for needle in ("Relationships", "Receipts", "rel-1", "rcpt-1", "2", "1")
        if needle not in rendered
    ]
    assert not missing, (
        "T28-D requires labelled Relationships/Receipts sections with one "
        f"row per item (ID + version); missing {missing!r} from:\n{rendered}"
    )


_CONFIRM_FORMS = ["write_propose", "edit", "promote", "archive", "restore"]


def _form_fixture(
    form: str, tmp_path: Path
) -> tuple[TuiState, ProjectState, _MemoryRunSpy]:
    """The every-form setup, reused by the T28-D confirm-step tests."""
    state, project = _state_and_project(tmp_path)
    state.memory_items = [
        {
            "id": "a1",
            "artifact_version": 1,
            "content": {"note": "x"},
            "source": "cli",
            "archived_at": "2026-01-01" if form == "restore" else None,
        }
    ]
    if form == "promote":
        _seed_promote_row(state, project, state.memory_items[0])
    state.memory_selected_index = 0
    state.memory_edit_buffer = "edited"
    preview = {
        "status": "ok",
        "raw": {
            "apply": False,
            "target_ids": ["a1"],
            "expected_revisions": {"a1": 1},
            "owner_scope": {"kind": "project", "id": "p"},
            "required_grants": ["cache_write"],
            "missing_grants": [],
            "draft": {},
        },
    }
    spy = _MemoryRunSpy(
        {
            "edit": [{"raw": {"code": "OK"}}, {"raw": {"code": "OK"}}],
            "archive": [{"raw": {"code": "OK"}}, {"raw": {"code": "OK"}}],
            "promote": [preview, {"raw": {"promoted": True, "new_tier": "verified"}}],
            "write": [
                preview,
                {"status": "ok", "raw": {"id": "new-1", "artifact_version": 1}},
            ],
        }
    )
    return state, project, spy


@pytest.mark.parametrize("form", _CONFIRM_FORMS)
def test_t28d_form_holds_preview_until_y(form: str, tmp_path: Path) -> None:
    """Plan line 419: preview exact ids/versions/owner/grants before any write.
    RED today: the form key previews and applies in one call."""
    state, project, spy = _form_fixture(form, tmp_path)
    actions = _actions(spy)
    _preview_form(form, state, project, actions)
    assert [(c.get("request") or {}).get("apply") for c in spy.calls] == [False], (
        f"{form}: the form key must only preview; calls were {spy.calls!r}"
    )
    pending = getattr(state, "memory_pending_mutation", None)
    assert pending is not None, f"{form}: no pending preview held for [y]"
    assert pending["ids"] == ["a1"] and pending["versions"] == {"a1": 1}
    assert pending["owner_scope"] and pending["required_grants"] == ["cache_write"]
    assert "[y] apply" in state.memory_message
    _memory_key(state, "y", actions)
    applies = [c for c in spy.calls if (c.get("request") or {}).get("apply") is True]
    assert len(applies) == 1, f"{form}: y must apply once; calls {spy.calls!r}"
    permissions = applies[0].get("permissions")
    assert isinstance(permissions, ExecutionPermissions) and permissions.cache_write
    assert state.memory_pending_mutation is None


@pytest.mark.parametrize("cancel_key", ["n", "escape"])
@pytest.mark.parametrize("form", _CONFIRM_FORMS)
def test_t28d_form_cancel_makes_zero_apply_calls(
    form: str, cancel_key: str, tmp_path: Path
) -> None:
    """Plan line 419: "cancellation writes nothing". RED today: the apply
    already ran inside the form key, before any cancel is possible."""
    state, project, spy = _form_fixture(form, tmp_path)
    actions = _actions(spy)
    _preview_form(form, state, project, actions)
    _memory_key(state, cancel_key, actions)
    assert "0 records written" in state.memory_message
    _memory_key(state, "y", actions)
    applies = [c for c in spy.calls if (c.get("request") or {}).get("apply") is True]
    assert not applies, f"{form}: cancel must make zero apply calls, got {applies!r}"
    assert getattr(state, "memory_pending_mutation", None) is None


def test_t28d_pending_mutation_panel_shows_ids_versions_owner_grants(
    tmp_path: Path,
) -> None:
    """Plan line 419: the panel shows what [y] will write. RED today: no
    pending mutation exists to render."""
    from rich.console import Console

    state, project, spy = _form_fixture("archive", tmp_path)
    _preview_form("archive", state, project, _actions(spy))
    state.memory_message = ""
    console = Console(record=True, width=400)
    console.print(tui_mod._render_memory_admin(state))
    text = console.export_text()
    assert "archive preview: ids ['a1'] versions {'a1': 1} owner " in text
    assert "grants ['cache_write']" in text and "[n]/[esc] cancel" in text


def test_t28d_r_key_refreshes_recorded_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan line 419 "offers refresh/review": with a recorded edit conflict,
    [r] re-fetches the row and reopens the editor on the fresh version."""
    state, project = _state_and_project(tmp_path)
    owner = tui_mod._memory_owner_scope(state, project)
    monkeypatch.setattr(tui_mod, "_memory_known_sources", lambda _: ["fixture-source"])
    state.memory_items = [
        {
            "id": "a1",
            "artifact_version": 3,
            "content": {"note": "o"},
            "source": "fixture-source",
            "owner_scope": owner,
        }
    ]
    state.memory_selected_index = 0
    state.memory_edit_conflict = {"id": "a1", "expected_version": 3}
    spy = _MemoryRunSpy(
        {
            "list": [
                {
                    "status": "ok",
                    "raw": [
                        {
                            "id": "a1",
                            "artifact_version": 4,
                            "source": "fixture-source",
                            "owner_scope": owner,
                        }
                    ],
                }
            ]
        }
    )
    _memory_key(state, "r", _actions(spy))
    assert state.mode == "memory_edit"
    assert state.memory_items[0]["artifact_version"] == 4
    assert state.memory_edit_conflict is None


def test_t28d_e_key_resets_edit_field_and_conflict(tmp_path: Path) -> None:
    """Opening the editor starts on `note` and drops a stale conflict."""
    state, _project = _state_and_project(tmp_path)
    state.memory_items = [
        {"id": "a1", "artifact_version": 3, "content": {"title": "t", "note": "n"}}
    ]
    state.memory_selected_index = 0
    state.memory_edit_field = "title"
    state.memory_edit_conflict = {"id": "a1", "expected_version": 3}
    _memory_key(state, "e", _actions(_MemoryRunSpy()))
    assert state.mode == "memory_edit"
    assert state.memory_edit_field == "note"
    assert state.memory_edit_conflict is None


def test_t28d_edit_tab_cycles_content_fields(tmp_path: Path) -> None:
    """[tab] in the editor reaches every structured-content key plus note."""
    state, _project = _state_and_project(tmp_path)
    state.memory_items = [
        {"id": "a1", "artifact_version": 3, "content": {"title": "t", "note": "n"}}
    ]
    state.memory_selected_index = 0
    state.mode = "memory_edit"
    state.memory_edit_field = "note"
    actions = _actions(_MemoryRunSpy())
    tui_mod._handle_memory_edit_key(state, "tab", actions)
    assert state.memory_edit_field == "title"
    tui_mod._handle_memory_edit_key(state, "tab", actions)
    assert state.memory_edit_field == "note"


def test_t28d_edit_prompt_names_selected_field(tmp_path: Path) -> None:
    """The editor prompt shows which content field Enter commits."""
    from rich.console import Console

    state, _project = _state_and_project(tmp_path)
    state.memory_items = [
        {"id": "a1", "artifact_version": 3, "content": {"title": "t", "note": "n"}}
    ]
    state.memory_selected_index = 0
    state.mode = "memory_edit"
    state.memory_edit_field = "title"
    state.memory_edit_buffer = "abc"
    console = Console(record=True, width=400)
    console.print(tui_mod._render_memory_admin(state))
    assert "edit title> abc" in console.export_text()


def _screen(state: tui.TuiState, width: int = 60, height: int = 20) -> str:
    console = Console(record=True, width=width, height=height, no_color=True)
    console.print(tui.render_app(state))
    return console.export_text()


def test_memory_second_page_status_visible_at_small_terminal_sizes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    owner = OwnerScope("project", "project-one")
    for index in range(35):
        store.write(
            MemoryArtifact(
                id=f"native-page-{index:02d}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": f"real page row {index}"},
                source="native-pages",
                created_at=time.time(),
                owner_scope=owner,
            )
        )
    project = tui.ProjectState(name="project", root=root, project_id="project-one")
    project.section = "memory"
    state = tui.TuiState(projects=[project], data_root=tmp_path)
    state.mode = "memory"
    state.memory_subject = "domain_knowledge"
    actions = tui.default_scan_actions()
    tui._memory_refresh(state, project, actions)
    assert len(state.memory_items) == 35
    for width, height in ((80, 24), (60, 20)):
        state.terminal_size = (width, height)
        state.memory_selected_index = 0
        tui._handle_memory_key(state, "]", actions)
        assert state.memory_selected_index == 20
        screen = _screen(state, width, height)
        assert "page 2/2" in screen, (width, height, screen)
        tui._handle_memory_key(state, " ", actions)
        assert state.memory_selected_ids == {"native-page-20"}
        checked_screen = _screen(state, width, height)
        assert ">[x]" in checked_screen, (width, height, checked_screen)
        state.memory_selected_ids.clear()
        state.message = "declined"
        tui._enter_section(state, "memory", actions)
        tui._handle_memory_key(state, "o", actions)
        for _ in range(4):
            tui._handle_memory_owner_key(state, "tab", actions)
        tui._handle_memory_owner_key(state, "enter", actions)
        assert state.memory_owner_scope_kind == "project"
        owner_screen = _screen(state, width, height)
        assert "owner scope = project:project-one" in owner_screen, (
            width,
            height,
            owner_screen,
        )
        state.message = "current cancellation notice"
        assert "current cancellation notice" in _screen(state, width, height)
        state.message = ""


def test_memory_detail_decodes_exact_version_and_real_receipts(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    first = store.write(
        MemoryArtifact(
            id="detail-alpha",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"note": "decoded persistent detail"},
            source="review-a",
            created_at=time.time(),
            owner_scope=OwnerScope("project", "project-one"),
        ),
        receipt_operation_id="real-create-alpha",
    )
    for index in range(6):
        second = store.write(
            MemoryArtifact(
                id=f"detail-beta-{index}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="EXTERNAL_WRITE",
                content={"note": f"related real detail {index}"},
                source=f"review-b-{index}",
                created_at=time.time(),
                owner_scope=OwnerScope("project", "project-one"),
            )
        )
        linked = MemoryTool().run(
            root,
            operation="link",
            request={
                "source_id": first.id,
                "source_version": first.artifact_version,
                "target_id": second.id,
                "target_version": second.artifact_version,
                "kind": "depends_on",
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert linked["raw"]["code"] == "OK"
    telemetry = TelemetryStore(root)
    for index in range(6):
        assert telemetry.record_memory_event(
            "expansion",
            17 + index,
            request_id=f"{first.id}:{first.artifact_version}:0",
            event_id="expansion",
            invocation_id=f"real-expand-alpha-{index}",
            cache_write=True,
        )
    project = tui.ProjectState(name="project", root=root, project_id="project-one")
    project.section = "memory"
    state = tui.TuiState(projects=[project], data_root=tmp_path)
    state.mode = "memory"
    state.terminal_size = (60, 20)
    state.memory_items = [
        {
            "id": first.id,
            "artifact_version": first.artifact_version,
            "source": first.source,
            "subject": first.subject,
            "symbol_ref": first.symbol_ref,
            "owner_scope": {"kind": "project", "id": "project-one"},
            "content": first.content,
        }
    ]
    tui._memory_expand_selected(state, project, tui.default_scan_actions())
    actions = tui.default_scan_actions()
    frames = []
    for _ in range(12):
        frames.append(_screen(state))
        before = state.memory_expanded["scroll"]
        tui._handle_memory_key(state, "]", actions)
        if state.memory_expanded["scroll"] == before:
            break
    visible = "\n".join(frames)
    compact = "".join(char for char in visible if char.isalnum() or char == "-")
    for marker in (
        "decoded",
        "persistent detail",
        "detail-beta-5",
        "real-create-alpha",
        "real-expand-alpha-5",
    ):
        needle = "".join(char for char in marker if char.isalnum() or char == "-")
        assert needle in compact, (marker, visible)


def test_memory_promote_uses_two_real_current_sources_and_rejects_stale(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    owner = OwnerScope("project", "project-one")
    records = [
        store.write(
            MemoryArtifact(
                id=f"corroborated-{source}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="EXTERNAL_WRITE",
                content={"note": "same grounded observation"},
                source=source,
                created_at=time.time(),
                owner_scope=owner,
            )
        )
        for source in ("review-a", "review-b")
    ]
    project = tui.ProjectState(name="project", root=root, project_id="project-one")
    state = tui.TuiState(projects=[project], data_root=tmp_path)
    state.mode = "memory"
    state.memory_items = [
        {
            "id": records[0].id,
            "artifact_version": records[0].artifact_version,
            "source": records[0].source,
            "subject": records[0].subject,
            "symbol_ref": records[0].symbol_ref,
            "content": records[0].content,
            "owner_scope": {"kind": "project", "id": "project-one"},
        }
    ]
    actions = tui.default_scan_actions()
    tui._memory_promote_selected(state, project, actions)
    held = state.memory_pending_mutation
    assert held is not None
    refs = held["calls"][0]["request"]["candidate_refs"]
    assert {ref["source"] for ref in refs} == {"review-a", "review-b"}
    store.archive(
        records[1].id,
        expected_version=records[1].artifact_version,
        scope="domain_knowledge",
        owner_scope=owner,
        apply=True,
    )
    state.memory_pending_mutation = held
    tui._memory_mutation_apply(state, project, actions)
    assert "changed since review" in state.memory_message
    current = store.get_current(records[1].id)
    assert current is not None
    store.archive(
        records[1].id,
        expected_version=current.artifact_version,
        scope="domain_knowledge",
        owner_scope=owner,
        apply=True,
        archived=False,
    )
    state.memory_items = [
        {
            **state.memory_items[0],
            "artifact_version": store.get_current(records[0].id).artifact_version,
        }
    ]
    tui._memory_promote_selected(state, project, actions)
    assert state.memory_pending_mutation is not None
    tui._memory_mutation_apply(state, project, actions)
    assert "promoted to STATED" in state.memory_message


def test_memory_detail_pages_exact_bytes_and_refuses_stale_owner_or_missing_store(
    tmp_path: Path,
) -> None:
    root = tmp_path / "first"
    root.mkdir()
    store = TypedArtifactStore(root)
    first = store.write(
        MemoryArtifact(
            id="same-id",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={
                "note": "EARLYMARKER " * 3
                + "A" * 230
                + "MIDDLEMARKER " * 3
                + "B" * 230
                + "ENDMARKER " * 3
                + "é🚀" * 50
            },
            source="source-a",
            created_at=time.time(),
            owner_scope=OwnerScope("project", "first"),
        )
    )
    project = tui.ProjectState(name="first", root=root, project_id="first")
    state = tui.TuiState(projects=[project], data_root=tmp_path)
    state.mode = "memory"
    state.terminal_size = (60, 20)
    row = {
        "id": first.id,
        "artifact_version": first.artifact_version,
        "source": first.source,
        "owner_scope": {"kind": "project", "id": "first"},
    }
    state.memory_items = [row]
    actions = tui.default_scan_actions()
    offsets = []
    frames = []
    for _ in range(80):
        tui._memory_expand_selected(state, project, actions)
        expanded = state.memory_expanded
        assert expanded is not None, state.memory_message
        offsets.append(expanded["offset"])
        while True:
            frames.append(_screen(state))
            rows = max(3, state.terminal_size[1] - 10)
            detail = tui._memory_detail_lines(expanded, state.terminal_size[0])
            if expanded["scroll"] + rows >= len(detail):
                break
            tui._handle_memory_key(state, "]", actions)
        if expanded["complete"]:
            break
    else:
        pytest.fail("exact content did not complete within 80 bounded pages")
    assert len(offsets) > 1 and offsets == sorted(set(offsets))
    assert expanded["content"] == store.get_version_content(
        first.id, first.artifact_version
    )
    assert "�" not in expanded["content"]
    final_page = expanded["pages"][-1]
    assert final_page["next_offset"] is None
    detail_text = "".join(
        line.plain
        for line in tui._memory_detail_lines(expanded, state.terminal_size[0])
    )
    assert (
        f"bytes {final_page['offset']}..{len(expanded['content'].encode())} complete"
        in detail_text
    )
    visible = "\n".join(frames)
    compact = "".join(char for char in visible if char.isalnum() or char == "-")
    for marker in ("EARLYMARKER", "MIDDLEMARKER", "ENDMARKER"):
        assert marker in compact, (marker, visible)
    last_page = expanded["page_index"]
    while expanded["scroll"]:
        tui._handle_memory_key(state, "[", actions)
    tui._handle_memory_key(state, "[", actions)
    assert expanded["page_index"] == last_page - 1
    back = "".join(char for char in _screen(state) if char.isalnum() or char == ".")
    assert f"bytes{expanded['pages'][last_page - 1]['offset']}.." in back

    other_root = tmp_path / "other"
    other_root.mkdir()
    other = TypedArtifactStore(other_root).write(
        MemoryArtifact(
            id="same-id",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"note": "other project only"},
            source="source-a",
            created_at=time.time(),
            owner_scope=OwnerScope("project", "other"),
        )
    )
    other_project = tui.ProjectState(name="other", root=other_root, project_id="other")
    state.projects = [other_project]
    state.memory_items = [
        {
            **row,
            "artifact_version": other.artifact_version,
            "owner_scope": {"kind": "project", "id": "other"},
        }
    ]
    tui._memory_expand_selected(state, other_project, actions)
    assert state.memory_expanded is not None
    assert state.memory_expanded["offset"] == 0
    assert "other project only" in state.memory_expanded["content"]
    assert "EARLYMARKER" not in state.memory_expanded["content"]
    state.projects = [project]
    state.memory_items = [row]

    row["owner_scope"] = {"kind": "project", "id": "another-owner"}
    tui._memory_expand_selected(state, project, actions)
    assert state.memory_expanded is None
    assert "selected record changed" in state.memory_message
    row["owner_scope"] = {"kind": "project", "id": "first"}
    store.archive(
        first.id,
        expected_version=first.artifact_version,
        scope="domain_knowledge",
        owner_scope=OwnerScope("project", "first"),
        apply=True,
    )
    tui._memory_expand_selected(state, project, actions)
    assert state.memory_expanded is None
    assert "E_VERSION" in state.memory_message

    missing = tmp_path / "missing"
    missing.mkdir()
    missing_project = tui.ProjectState(
        name="missing", root=missing, project_id="missing"
    )
    state.memory_items = [row]
    tui._memory_expand_selected(state, missing_project, actions)
    assert state.memory_expanded is None
    assert not (missing / ".rush" / "memory.db").exists()


def test_memory_receipt_readers_do_not_create_or_mutate_storage(tmp_path: Path) -> None:
    from rush.token_economy.telemetry import read_artifact_expansion_receipts_readonly

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    record = store.write(
        MemoryArtifact(
            id="receipt-one",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"note": "owned"},
            source="one",
            created_at=time.time(),
            owner_scope=OwnerScope("project", "one"),
        ),
        receipt_operation_id="real-write-one",
    )
    db = root / ".rush" / "memory.db"
    before = db.stat().st_mtime_ns
    rows = TypedArtifactStore.read_artifact_receipts_readonly(
        root, record.id, record.artifact_version
    )
    assert [row["id"] for row in rows] == ["real-write-one"]
    assert TypedArtifactStore.read_artifact_receipts_readonly(root, record.id, 99) == []
    assert db.stat().st_mtime_ns == before
    assert read_artifact_expansion_receipts_readonly(root, record.id, 1) == []
    assert not (root / ".rush" / "telemetry" / "tokens.db").exists()


def test_memory_promotion_transaction_rejects_changed_corrob_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    owner = OwnerScope("project", "one")
    records = [
        store.write(
            MemoryArtifact(
                id=f"peer-{source}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="EXTERNAL_WRITE",
                content={"note": "same observation"},
                source=source,
                created_at=time.time(),
                owner_scope=owner,
            )
        )
        for source in ("one", "two")
    ]
    refs = [
        {"id": item.id, "version": item.artifact_version, "source": item.source}
        for item in records
    ]
    candidate = store.write(
        MemoryArtifact(
            id="candidate",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"note": "same observation"},
            source="one",
            created_at=time.time(),
            owner_scope=owner,
        )
    )
    store.archive(
        records[1].id,
        expected_version=records[1].artifact_version,
        scope="domain_knowledge",
        owner_scope=owner,
        apply=True,
    )
    with pytest.raises(VersionConflictError, match="changed since review"):
        store.promote(
            candidate.id,
            user_stated=False,
            candidate_refs=refs,
            expected_version=candidate.artifact_version,
            owner_scope=owner,
        )
    current = store.get_current(candidate.id)
    assert current is not None
    assert current.trust_tier == "EXTERNAL_WRITE"
    assert current.artifact_version == candidate.artifact_version


def test_memory_legacy_telemetry_receipts_expose_no_unknown_identity(
    tmp_path: Path,
) -> None:
    from rush.token_economy.telemetry import read_artifact_expansion_receipts_readonly

    root = tmp_path / "project"
    db = root / ".rush" / "telemetry" / "tokens.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE memory_events (request_id TEXT, event_id TEXT, "
            "kind TEXT, tokens INTEGER, timestamp INTEGER)"
        )
        conn.execute(
            "INSERT INTO memory_events VALUES ('unrelated:1:0', 'expansion', "
            "'expansion', 99, 1)"
        )
    before = db.stat().st_mtime_ns
    assert read_artifact_expansion_receipts_readonly(root, "related", 1) == []
    assert db.stat().st_mtime_ns == before
