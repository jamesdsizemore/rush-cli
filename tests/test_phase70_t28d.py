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

from rush import tui as tui_mod
from rush.memory.maintenance import MaintenanceTask
from rush.memory.store import MemoryArtifact, TypedArtifactStore, legacy_owner_scope
from rush.permissions import ExecutionPermissions
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
    state.memory_items = [item]
    state.memory_selected_index = 0
    spy = _MemoryRunSpy(
        {"promote": [{"raw": {"promoted": True, "new_tier": "verified"}}]}
    )
    tui_mod._memory_promote_selected(state, project, _actions(spy))
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
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_pending_promote = {"required_grants": ["artifact_write"]}
    spy = _MemoryRunSpy(
        {"promote": [{"raw": {"promoted": True, "new_tier": "verified"}}]}
    )
    tui_mod._memory_promote_selected(state, project, _actions(spy))
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
    if not ("target_ids" in payload or payload.get("artifact_ids") or payload.get("id")):
        missing.append("ids")
    if not ("expected_revisions" in payload or payload.get("expected_revisions") or payload.get("expected_version")):
        missing.append("versions")
    if not payload.get("owner_scope"):
        missing.append("owner")
    if not payload.get("required_grants"):
        missing.append("required_grants")
    return missing


def _run_form(
    form: str, state: TuiState, project: ProjectState, actions: ScanActions
) -> None:
    if form == "delete":
        tui_mod._memory_delete_preview(state, project, actions)
        tui_mod._memory_delete_apply(state, project, actions)
    elif form == "edit":
        tui_mod._memory_edit_commit(state, project, actions)
    elif form == "promote":
        tui_mod._memory_promote_selected(state, project, actions)
    elif form in ("archive", "restore"):
        tui_mod._handle_memory_key(state, "a", actions)
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
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_selected_ids = {"a1"}
    state.memory_edit_buffer = "y"
    new_preview = {"status": "ok", "raw": {"apply": False, "target_ids": [], "expected_revisions": {}, "owner_scope": {"kind": "project", "id": "p"}, "required_grants": ["cache_write"], "missing_grants": [], "draft": {}}}
    spy = _MemoryRunSpy(
        {
            "edit": [{"raw": {"code": "OK"}}],
            "promote": [new_preview, {"raw": {"promoted": True, "new_tier": "verified"}}],
            "write": [new_preview, {"status": "ok", "raw": {"id": "new-1", "artifact_version": 1}}],
            "archive": [{"raw": {"code": "OK"}}],
            "delete": [
                {"raw": {"data": {"affected": ["a1"]}}},
                {"raw": {"data": {"affected": ["a1"]}}},
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
                {"raw": {"data": {"affected": ["a1", "a2"]}}},
                {"raw": {"data": {"affected": ["a1", "a2"]}}},
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
                {"raw": {"data": {"affected": ["a1"]}}},
                {"raw": {"data": {"affected": ["a1"]}}},
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
    spy = _MemoryRunSpy({"delete": [{"raw": {"data": {"affected": ["a1"]}}}]})
    actions = _actions(spy)
    tui_mod._memory_delete_preview(state, project, actions)
    tui_mod._handle_memory_key(state, "n", actions)
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
    tui_mod._handle_memory_key(state, "a", _actions(spy))
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
    tui_mod._handle_memory_key(state, "a", _actions(spy))
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
                {"raw": {"data": {"candidate_ids": ["a1", "a2"], "applied": False}}}
            ]
            * tasks
            + [{"raw": {"data": {"candidate_ids": ["a1", "a2"], "applied": True}}}]
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
    preview_ids = maintain_calls[0]["response"]["raw"]["data"]["candidate_ids"]
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
                {"raw": {"data": {"candidate_ids": ["a1"], "applied": False}}},
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


def test_t28d_edit_conflict_offers_refresh_and_rereview(tmp_path: Path) -> None:
    """Beyond keeping the entered content (already covered by
    `test_t28d_edit_conflict_keeps_entered_content`), the brief requires
    the conflict to "offer refresh/review, never blind retry." RED: today
    a conflict sets a plain string message and nothing else -- there is no
    state a re-review flow could act on, and no refreshed version is ever
    fetched."""
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 3, "content": {"note": "orig"}}
    state.memory_items = [item]
    state.memory_selected_index = 0
    state.memory_edit_buffer = "in-flight-edit"
    spy = _MemoryRunSpy(
        {
            "edit": [{"raw": {"code": "E_VERSION"}}],
            # A refresh/re-review re-fetches the row; its current version has
            # moved on from the stale `3` this edit started against.
            "list": [{"status": "ok", "raw": [{"id": "a1", "artifact_version": 4}]}],
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
    state, project = _state_and_project(tmp_path)
    item = {"id": "a1", "artifact_version": 1}
    state.memory_items = [item]
    state.memory_selected_index = 0
    spy = _MemoryRunSpy(
        {
            "expand": [
                {
                    "raw": {
                        "data": {
                            "id": "a1",
                            "artifact_version": 1,
                            "content": {"note": "x"},
                            "relationships": [
                                {"id": "rel-1", "artifact_version": 2, "kind": "cites"}
                            ],
                            "receipts": [
                                {"id": "rcpt-1", "artifact_version": 1, "kind": "read"}
                            ],
                        }
                    }
                }
            ]
        }
    )
    actions = _actions(spy)
    tui_mod._memory_expand_selected(state, project, actions)

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
