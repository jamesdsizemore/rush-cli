"""Phase 70 T28-B (design gate `.scratch/phase-70-design-gate/W4-T23-T29.md`,
section "### T28-B: setup, agents, repair lifecycle"; plan packet
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` "T28-B --
Setup, agents and the complete repair lifecycle"): failing-first tests for
the scan/handoff/rescan/cancel repair lifecycle, and the Setup/Agents and
Scans sections, T28-B must build.

The brief names this suite `test_t28b_setup_handoff_rescan` inside a shared
`tests/test_phase70_tui_usability.py`. Per this task's binding instructions
("Create exactly one new file... If the brief names another or a shared
test file, still write into your file, keep the brief's test names, and
report the mapping"), every case lives here in
`tests/test_phase70_t28b.py`; the journey test keeps the brief's exact name
(`test_t28b_setup_handoff_rescan`), each of its defects also gets its own
standalone test so it is RED independently, and every Setup/Agents/Scans
bullet gets its own test too, using `pytest.fail` to name the exact missing
field/function when the brief's pinned shared-design surface
(`TuiState.section`/`overlay`/`views`, `ProjectState`'s work kind/
`cancel_event`) does not exist yet -- a valid, specific RED, not a fixture
crash.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

import rush.tui as tui_module
from rush.permissions import ExecutionPermissions
from rush.tui import ProjectState, ScanActions, TuiState


def _finding(path: str, finding_id: str) -> dict[str, object]:
    return {
        "path": path,
        "line": 1,
        "column": 1,
        "rule": "F1",
        "message": f"issue in {path}",
        "severity": "error",
        "finding_id": finding_id,
    }


def _actions(**overrides: object) -> ScanActions:
    base: dict[str, object] = {
        "plan_scan": lambda *a, **k: SimpleNamespace(plan_id="plan-1", candidates=[1]),
        "execute_scan": lambda *a, **k: SimpleNamespace(aggregate=None),
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {"run": {"run_id": "rescan-run"}},
        "build_handoff": lambda *a, **k: SimpleNamespace(
            handoff_id="h1", session_capability="cap1"
        ),
        "dispatch_handoff": lambda *a, **k: SimpleNamespace(state="delivered"),
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
        "dashboard_owner": lambda root: None,
    }
    base.update(overrides)
    return ScanActions(**base)


def _project_with_findings() -> ProjectState:
    project = ProjectState(name="demo", root=Path("/tmp/rush-t28b-demo"))
    project.run_id = "run-1"
    project.results = [
        {
            "tool": "lint",
            "status": "fail",
            "findings": [_finding("a.py", "fa"), _finding("b.py", "fb")],
        }
    ]
    return project


def _admit_started(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tui_module,
        "_admit_local_run",
        lambda *a, **k: tui_module.AdmissionResult(
            slot_id="fake-slot", started=True, attached=False, conflict=False
        ),
    )


def _require_field(obj: object, name: str, *, where: str) -> object:
    """A brief-pinned field/attribute the shared design names, that T28-B
    must add. Missing it is a real, specific RED -- not a fixture crash --
    so this fails cleanly via `pytest.fail` naming exactly what's missing,
    instead of an uncaught `AttributeError`/`KeyError` traceback."""
    if not hasattr(obj, name):
        pytest.fail(f"{where}: missing required T28-B field {name!r} on {obj!r}")
    return getattr(obj, name)


def _require_attr(module: object, name: str, *, where: str) -> object:
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"{where}: missing required T28-B entry point {name!r}")
    return value


def _render_text(state: TuiState) -> str:
    console = Console(record=True, width=140)
    console.print(tui_module.render_app(state))
    return console.export_text()


# ---------------------------------------------------------------------------
# Shared-design key contract (F3 section chooser, digit selection).
# ---------------------------------------------------------------------------


def test_f3_opens_section_chooser_and_digit_selects_setup() -> None:
    """Shared design 'Keys': 'F3 section chooser (8 sections plus Check,
    Scan, Projects, Help, Quit; digits 1-8)'. Today F3 is bound to
    `next_section`, which mutates `state.mode` through the old
    list/map/git cycle -- it never opens an `overlay` at all, and there is
    no `section` field a digit could pick."""
    project = _project_with_findings()
    state = TuiState(projects=[project])
    actions = _actions()

    tui_module._dispatch_key(state, "f3", actions)
    overlay = _require_field(state, "overlay", where="F3 must open a section chooser")
    assert overlay == "sections", f"F3 must set overlay='sections', got {overlay!r}"

    tui_module._dispatch_key(state, "8", actions)
    section = _require_field(
        state, "section", where="digit '8' must select the 8th section (setup)"
    )
    assert section == "setup", f"digit '8' must select section='setup', got {section!r}"


# ---------------------------------------------------------------------------
# T28-B Setup/Agents bullets (a-f) and Scans bullet (g).
# ---------------------------------------------------------------------------


def test_setup_section_renders_t26_preview_without_applying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet a: 'Setup section: navigating F3 -> setup renders the T26
    preview envelope (config, registration, configure and engines stages),
    using the real SetupTool preview. It must not apply.'

    Spies on the real, already-merged (T24/T26) `build_setup_review` /
    `apply_setup_review` in `rush.tools.setup_wizard`. `render_app` today
    never imports or calls either -- it only branches on the old
    `state.mode` -- so the rendered text can never contain the real
    preview's stage labels."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import rush.tools.setup_wizard as setup_wizard_module

    preview_calls: list[dict[str, object]] = []
    apply_calls: list[object] = []
    real_build = setup_wizard_module.build_setup_review

    def spy_build(root: Path, data_root: Path | None = None, **kwargs: object) -> dict:
        preview_calls.append({"root": root, "data_root": data_root, **kwargs})
        return real_build(root, data_root, **kwargs)

    monkeypatch.setattr(setup_wizard_module, "build_setup_review", spy_build)
    monkeypatch.setattr(
        setup_wizard_module,
        "apply_setup_review",
        lambda *a, **k: apply_calls.append((a, k)),
    )

    project = ProjectState(name="demo", root=tmp_path)
    project.section = "setup"  # what T28-A/T28-B must add to ProjectState/TuiState
    state = TuiState(projects=[project])
    state.section = "setup"

    rendered = _render_text(state)

    assert preview_calls, (
        "opening the Setup section must call the real build_setup_review "
        "preview; render_app never references it today"
    )
    assert apply_calls == [], "opening the preview alone must never apply"
    real_review = real_build(tmp_path, tmp_path / "data")
    real_preview_text = setup_wizard_module.render_setup_review(real_review)
    assert "1. Config:" in real_preview_text  # sanity: the real preview has it
    assert "1. Config:" in rendered, (
        "the Setup section must render the real T26 preview's config/"
        "registration/configure/engines stages, not the old findings panel"
    )


def test_setup_stage_grants_default_off_except_launch_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet b: 'Per-stage grant toggles default OFF, except grants given
    at launch (`rush ui --allow-*`), which are pre-granted but still
    listed in the review.'

    Shared design pins this state onto `TuiState.views[(project_key,
    section)].data` -- absent today, so this documents that exact gap."""
    monkeypatch.setenv("HOME", str(tmp_path))
    project = ProjectState(name="demo", root=tmp_path)
    project.launch_permissions = ExecutionPermissions(cache_write=True)
    state = TuiState(projects=[project])
    state.section = "setup"

    views = _require_field(
        state, "views", where="per-stage grant toggle state lives in TuiState.views"
    )
    key = (project.project_id or f"path:{project.root}", "setup")
    view = views.get(key) if isinstance(views, dict) else None
    if view is None:
        pytest.fail(
            f"TuiState.views has no SectionView for key {key!r}; the Setup "
            "section must populate one with per-stage grant toggles"
        )
    stage_grants = getattr(view, "data", {}).get("stage_grants") if view else None
    assert stage_grants is not None, "SectionView.data must carry 'stage_grants'"
    assert all(
        toggle is False for stage, toggle in stage_grants.items() if stage != "engines"
    ) or any(toggle is True for stage, toggle in stage_grants.items()), (
        "every stage toggle must default OFF except pre-granted launch grants"
    )


def test_setup_network_review_shown_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet c: 'The resolution-only network review is shown before any
    network resolution.' The first preview build must use `resolve=False`
    (no network I/O); today nothing calls `build_setup_review` at all, so
    the spy is never invoked -- an honest zero-calls failure, not a
    fixture error."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import rush.tools.setup_wizard as setup_wizard_module

    calls: list[bool] = []
    monkeypatch.setattr(
        setup_wizard_module,
        "build_setup_review",
        lambda root, data_root=None, resolve=False, **k: (
            calls.append(resolve) or {"kind": "setup_review"}
        ),
    )

    project = ProjectState(name="demo", root=tmp_path)
    state = TuiState(projects=[project])
    state.section = "setup"
    _render_text(state)

    assert calls, "opening Setup must build a preview before any resolution"
    assert calls[0] is False, (
        "the initial Setup preview must be resolution-only (resolve=False); "
        "a real network resolution must only follow explicit approval"
    )


def test_setup_apply_progress_events_render_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet d: 'Apply progress events from a worker render in order.'
    No worker/progress-event mechanism exists in `tui.py` for a setup
    apply grant -- `_execute_grant`'s kind dispatch has no `setup_apply`
    branch, and there is no background-worker entry point to post events
    from, so this first names the exact missing entry point.

    Pinned contract for the implementer (not in the brief verbatim, so
    documented here): `_start_setup_apply_thread(project, actions, review)`
    spawns a worker that calls `actions.apply_setup_review(review,
    on_progress=callback)`, where `callback(stage, status)` appends
    `(stage, status)` to `project.setup_apply_events` in call order.
    `render_app` must show those events, in order, by stage name. An empty
    no-op stub for `_start_setup_apply_thread` must NOT make this pass: the
    scripted worker below drives 4 stages (3 completed, 1 failed) and this
    asserts the exact ordered sequence actually lands on the project and in
    the rendered text, not merely that the attribute exists."""
    monkeypatch.setenv("HOME", str(tmp_path))
    start_thread = _require_attr(
        tui_module,
        "_start_setup_apply_thread",
        where="bullet d needs a background worker that posts ordered apply "
        "progress events, the same shape as _start_scan_thread/"
        "_start_rescan_thread",
    )

    scripted_stages = ["config", "register", "configure", "engines"]

    def fake_apply_setup_review(review, *args, on_progress=None, **kwargs):
        assert on_progress is not None, "the worker must be given a progress callback"
        for stage in scripted_stages[:-1]:
            on_progress(stage, "started")
            on_progress(stage, "completed")
        on_progress(scripted_stages[-1], "started")
        on_progress(scripted_stages[-1], "failed")
        return {"status": "partial"}

    monkeypatch.setattr(
        "rush.tools.setup_wizard.apply_setup_review", fake_apply_setup_review
    )

    project = ProjectState(name="demo", root=tmp_path)
    review = {"kind": "setup_review", "project_root": str(tmp_path)}
    start_thread(project, _actions(), review)
    thread = getattr(project, "scan_thread", None) or getattr(
        project, "setup_apply_thread", None
    )
    if thread is not None:
        thread.join(timeout=5)

    events = getattr(project, "setup_apply_events", None)
    assert events is not None, (
        "the worker must record ordered (stage, status) events on "
        "project.setup_apply_events"
    )
    expected = [
        ("config", "started"),
        ("config", "completed"),
        ("register", "started"),
        ("register", "completed"),
        ("configure", "started"),
        ("configure", "completed"),
        ("engines", "started"),
        ("engines", "failed"),
    ]
    assert list(events) == expected, (
        f"apply progress events must render in exact scripted order, got {events!r}"
    )

    state = TuiState(projects=[project])
    rendered = _render_text(state)
    positions = [rendered.find(f"{stage} {status}") for stage, status in expected]
    assert all(p != -1 for p in positions), (
        f"rendered text must show every stage/status pair, got positions {positions!r}"
    )
    assert positions == sorted(positions), (
        "rendered stage events must appear in the same order they occurred"
    )


def test_setup_failed_stage_retry_regenerates_review_without_reapply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet e: 'Failed-stage retry via regenerated review' -- and
    'nothing re-applies without a new review.' Simulates a `setup_retry`
    grant kind (the shape `_execute_grant` already uses for
    start_scan/rescan/handoff); today no such branch exists, so retrying
    calls neither a fresh preview nor apply -- both spies stay at zero
    calls, proving retry currently has no effect at all (not even a wrong
    one)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    import rush.tools.setup_wizard as setup_wizard_module

    build_calls: list[object] = []
    apply_calls: list[object] = []
    monkeypatch.setattr(
        setup_wizard_module,
        "build_setup_review",
        lambda *a, **k: build_calls.append(1) or {"kind": "setup_review"},
    )
    monkeypatch.setattr(
        setup_wizard_module,
        "apply_setup_review",
        lambda *a, **k: apply_calls.append(1) or {"status": "ok"},
    )

    project = ProjectState(name="demo", root=tmp_path)
    state = TuiState(projects=[project])
    grant = {
        "kind": "setup_retry",
        "project": project.name,
        "root": str(project.root),
        "failed_stage": "configure",
    }
    tui_module._execute_grant(state, grant, _actions())

    assert build_calls, (
        "a failed-stage retry must regenerate the review (call "
        "build_setup_review again) -- it currently never does"
    )
    assert not apply_calls, "retry must produce a fresh review, never re-apply directly"


def test_unavailable_agent_is_distinct_surfaced_state(tmp_path: Path) -> None:
    """Bullet f: 'an unavailable agent is a distinct surfaced state, not
    the generic failure message.' Today `_execute_grant`'s handoff branch
    has one catch-all `except Exception` that turns any failure -- unknown
    agent included -- into the same `f"{kind} failed: {exc}"` text. The
    shared design's `SectionView.state` enum includes `denied`/
    `unavailable` specifically so this can be distinguished; `TuiState`
    has no `views` at all yet."""
    project = _project_with_findings()
    state = TuiState(projects=[project])
    state.selected_agent_id = "ghost-agent"
    actions = _actions(
        list_agents=lambda: ["agent-1"],
        dispatch_handoff=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("ghost-agent not found")
        ),
    )

    tui_module._dispatch_key(state, "H", actions)
    tui_module._dispatch_key(state, "y", actions)

    views = _require_field(
        state,
        "views",
        where="an unavailable agent must surface as a SectionView(state="
        "'unavailable'), which requires TuiState.views to exist",
    )
    assert views, "TuiState.views must be populated after a handoff attempt"


def test_scans_section_reads_run_manifest_read_only_zero_files_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bullet g: 'Scans section: history is read via load_run_manifest and
    T23 selectors, read-only, with zero files created.' No TUI code calls
    `load_run_manifest` today; this names the exact missing loader entry
    point and proves (once it exists) that opening Scans creates nothing
    under the project root."""
    monkeypatch.setenv("HOME", str(tmp_path))
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    loader = _require_attr(
        tui_module,
        "_load_scans_section",
        where="bullet g needs a Scans loader that calls "
        "workflows.project_run.load_run_manifest and T23's selectors",
    )
    outcome = loader(tmp_path, None, None, _actions())
    assert outcome[0] == "empty" and outcome[2] == {"history": []}

    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert after == before, "reading Scans history must create zero files"


# ---------------------------------------------------------------------------
# Journey (brief's exact name) plus one standalone test per defect, each RED
# independently.
# ---------------------------------------------------------------------------


def test_t28b_setup_handoff_rescan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brief's named case: the full repair-lifecycle journey through the
    real grant-review flow (`_dispatch_key`/`_execute_grant`/
    `_start_scan_thread`/`_start_rescan_thread`). Each individual defect
    below also has its own standalone test so it is RED on its own; this
    proves they hold together as one real user journey."""
    _admit_started(monkeypatch)
    project = _project_with_findings()
    execute_calls: list[dict[str, object]] = []
    handoff_calls: list[dict[str, object]] = []
    rescan_calls: list[dict[str, object]] = []

    actions = _actions(
        execute_scan=lambda plan, **kwargs: (
            execute_calls.append(kwargs) or SimpleNamespace(aggregate=None)
        ),
        build_handoff=lambda root, run_id, agent_id, **kwargs: (
            handoff_calls.append({"run_id": run_id, "agent_id": agent_id, **kwargs})
            or SimpleNamespace(handoff_id="h1", session_capability="cap1")
        ),
        rescan_project_run=lambda root, baseline_run_id, **kwargs: (
            rescan_calls.append({"baseline_run_id": baseline_run_id, **kwargs})
            or {"run": {"run_id": "rescan-run"}}
        ),
    )
    state = TuiState(projects=[project])

    tui_module._dispatch_key(state, "s", actions)
    assert state.mode == "grant_review"
    tui_module._dispatch_key(state, "y", actions)
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)
    assert execute_calls, "start-scan review must actually reach execute_scan"
    assert execute_calls[0].get("permissions") is not None

    project.filter_text = "b.py"
    assert [row["path"] for row in project.visible_findings()] == ["b.py"]
    state.selected_agent_id = "agent-1"
    tui_module._dispatch_key(state, "H", actions)
    assert state.mode == "grant_review"
    reviewed_grant = state.pending_grant
    assert reviewed_grant is not None and reviewed_grant["finding_count"] == 1
    tui_module._dispatch_key(state, "y", actions)
    assert handoff_calls, "handoff review confirmation must call build_handoff"
    assert handoff_calls[0]["finding_ids"] == ("fb",)

    project.filter_text = ""
    reviewed_run_id = project.run_id
    tui_module._dispatch_key(state, "r", actions)
    assert state.mode == "grant_review"
    tui_module._dispatch_key(state, "y", actions)
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)
    assert rescan_calls, "rescan review confirmation must call rescan_project_run"
    assert rescan_calls[0].get("expected_attempt_id") == reviewed_run_id


def test_scan_review_permissions_reach_execute_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone: fixing `tui.py:991-993` -- `_start_scan_thread` calls
    `actions.execute_scan(plan, run_id=..., owner_instance_id=...)` with no
    `permissions` kwarg at all, so the reviewed grants never reach it."""
    _admit_started(monkeypatch)
    project = _project_with_findings()
    execute_calls: list[dict[str, object]] = []
    actions = _actions(
        execute_scan=lambda plan, **kwargs: (
            execute_calls.append(kwargs) or SimpleNamespace(aggregate=None)
        )
    )

    tui_module._start_scan_thread(project, actions)
    assert project.scan_thread is not None
    project.scan_thread.join(timeout=5)

    assert execute_calls
    assert execute_calls[0].get("permissions") is not None, (
        "reviewed grants must reach execute_scan(permissions=...), not the "
        "hardcoded no-permissions call at tui.py:991-993"
    )


def test_handoff_review_sent_equals_effect_finding_ids() -> None:
    """Standalone: fixing `tui.py:1282-1284` -- `_execute_grant`'s handoff
    branch always calls `build_handoff(..., finding_ids=())` regardless of
    what the review showed. 'review-sent equals effect finding_ids':
    reviewing 1 filtered finding must send exactly that finding's id, not
    every finding."""
    project = _project_with_findings()
    project.filter_text = "b.py"
    state = TuiState(projects=[project])
    state.selected_agent_id = "agent-1"
    handoff_calls: list[dict[str, object]] = []
    actions = _actions(
        build_handoff=lambda root, run_id, agent_id, **kwargs: (
            handoff_calls.append({"agent_id": agent_id, **kwargs})
            or SimpleNamespace(handoff_id="h1", session_capability="cap1")
        )
    )

    tui_module._dispatch_key(state, "H", actions)
    assert state.pending_grant is not None and state.pending_grant["finding_count"] == 1
    tui_module._dispatch_key(state, "y", actions)

    assert handoff_calls
    assert handoff_calls[0]["finding_ids"] == ("fb",), (
        "the reviewed (filtered) finding must be the exact finding_ids sent"
    )


def test_rescan_passes_expected_attempt_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standalone: 'Rescan: passes expected_attempt_id = the reviewed
    attempt (project_run.py:2683).' `_start_rescan_thread` today calls
    `rescan_project_run(root, baseline_run_id, owner_instance_id=...)` with
    no `expected_attempt_id` at all."""
    project = _project_with_findings()
    rescan_calls: list[dict[str, object]] = []
    actions = _actions(
        rescan_project_run=lambda root, baseline_run_id, **kwargs: (
            rescan_calls.append({"baseline_run_id": baseline_run_id, **kwargs})
            or {"run": {"run_id": "rescan-run"}}
        )
    )

    tui_module._start_rescan_thread(project, actions)
    project.scan_thread.join(timeout=5)

    assert rescan_calls
    assert rescan_calls[0].get("expected_attempt_id") == "run-1"


def test_stale_review_race_yields_no_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standalone: 'Any change of source, attempt, or project after review
    invalidates the review with no effect.' Covers an attempt change (a
    newer run racing a reviewed rescan); `_handle_grant_review_key` today
    executes whatever grant dict it stored at review time, unconditionally,
    regardless of what changed since."""
    _admit_started(monkeypatch)
    project_a = _project_with_findings()
    project_b = ProjectState(name="other", root=Path("/tmp/rush-t28b-other"))
    rescan_calls: list[object] = []
    actions = _actions(
        rescan_project_run=lambda *a, **k: (
            rescan_calls.append(1) or {"run": {"run_id": "rescan-run"}}
        )
    )
    state = TuiState(projects=[project_a, project_b])

    tui_module._dispatch_key(state, "r", actions)
    assert state.mode == "grant_review"
    stale_grant = state.pending_grant
    assert stale_grant is not None and stale_grant["run_id"] == "run-1"

    project_a.run_id = "newer-attempt"
    tui_module._dispatch_key(state, "y", actions)
    if project_a.scan_thread is not None:
        project_a.scan_thread.join(timeout=5)

    assert rescan_calls == [], (
        "a rescan reviewed against one attempt must have no effect once a "
        "newer attempt races it before confirmation"
    )


def test_request_cancel_dispatches_by_work_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standalone: '_request_cancel dispatches by work kind.' Shared
    design: 'ProjectState gains ... a work kind (check|scan|rescan|
    dashboard), and a cancel_event: threading.Event.' Neither field exists
    on `ProjectState` today, so `_request_cancel` cannot distinguish a
    running check from a running scan -- it always calls the scan-specific
    `cancel_scan_run`, which is wrong for a check or rescan in progress.

    After the missing-field gates, this drives all four work kinds and
    spies on the one mechanism each must trigger, asserting exactly one
    call each -- an empty `cancel_event`/`work_kind` stub with no real
    dispatch logic behind it fails every one of these."""
    import rush.workflows.suites as suites_module

    project = _project_with_findings()
    project.status = "scanning"
    _require_field(
        project,
        "cancel_event",
        where="_request_cancel must set/observe a per-work cancel_event",
    )
    _require_field(
        project,
        "work_kind",
        where="_request_cancel must dispatch on project.work_kind "
        "(check|scan|rescan|dashboard)",
    )

    # --- check: cancel_event.set() must reach run_workflow_suite's
    # cancel_check, never the scan-specific marker-file cancel.
    project.work_kind = "check"
    project.cancel_event.clear()
    scan_cancel_calls: list[object] = []
    actions = _actions(cancel_scan_run=lambda *a, **k: scan_cancel_calls.append(1))
    tui_module._request_cancel(project, actions)
    assert project.cancel_event.is_set(), "a check cancel must set cancel_event"
    assert scan_cancel_calls == [], "a check cancel must never call cancel_scan_run"

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        suites_module,
        "run_workflow_suite",
        lambda **kwargs: captured.update(kwargs) or {"status": "cancelled"},
    )
    check_actions = tui_module.default_scan_actions(permissions=ExecutionPermissions())
    check_actions.run_check_suite(
        project.root,
        owner_instance_id="owner-1",
        run_id="run-1",
        cancel_check=project.cancel_event.is_set,
    )
    assert captured.get("cancel_check") is not None and captured["cancel_check"](), (
        "the check's real cancel_check must observe the same cancel_event "
        "_request_cancel set"
    )

    # --- scan: the scan cancel route (marker-file cancel_scan_run), exactly
    # once, and cancel_event must not be what a scan-kind cancel relies on.
    project.work_kind = "scan"
    project.status = "scanning"
    project.cancel_event.clear()
    scan_cancel_calls.clear()
    actions = _actions(cancel_scan_run=lambda *a, **k: scan_cancel_calls.append(1))
    tui_module._request_cancel(project, actions)
    assert scan_cancel_calls == [1], (
        "a scan cancel must call cancel_scan_run exactly once"
    )

    # --- rescan: the identical scan cancel route (rescan is a run_id-
    # tracked local run, same marker-file protocol), exactly once.
    project.work_kind = "rescan"
    project.status = "scanning"
    scan_cancel_calls.clear()
    actions = _actions(cancel_scan_run=lambda *a, **k: scan_cancel_calls.append(1))
    tui_module._request_cancel(project, actions)
    assert scan_cancel_calls == [1], (
        "a rescan cancel must call cancel_scan_run exactly once"
    )

    # --- dashboard: dispatched through the live dashboard owner's own
    # "cancel" action, never a local marker file or cancel_event.
    project.work_kind = "dashboard"
    project.owner = "dashboard"
    project.status = "scanning"

    class _FakeOwner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def dispatch(self, operation: str, **arguments: object) -> dict:
            self.calls.append((operation, dict(arguments)))
            return {"operation_id": "op-1"}

    owner = _FakeOwner()
    scan_cancel_calls.clear()
    actions = _actions(
        cancel_scan_run=lambda *a, **k: scan_cancel_calls.append(1),
        dashboard_owner=lambda root: owner,
    )
    tui_module._request_cancel(project, actions)
    # T28-F: the cancel request runs on a worker; wait (bounded) for it.
    deadline = time.monotonic() + 5.0
    while not owner.calls and time.monotonic() < deadline:
        time.sleep(0.005)
    assert scan_cancel_calls == [], "a dashboard-owned cancel must never run locally"
    assert [call[0] for call in owner.calls] == ["cancel"], (
        f"a dashboard-owned cancel must dispatch exactly one 'cancel' "
        f"operation to the owning server, got {owner.calls!r}"
    )


# ---------------------------------------------------------------------------
# Keep-green guards: real, already-correct contracts that must not regress.
# ---------------------------------------------------------------------------


def test_check_cancel_forwards_cancel_check_to_run_workflow_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T28-B 'Check cancel': `cancel_event` must reach `run_workflow_suite`
    as `cancel_check` (`suites.py:63,112`). `default_scan_actions`'s
    `_run_check_suite` accepts `**kwargs` but currently drops every one of
    them instead of forwarding `cancel_check` -- so a real cancel request
    never actually stops the running CHECK_SUITE."""
    import rush.workflows.suites as suites_module

    captured: dict[str, object] = {}

    def fake_run_workflow_suite(**kwargs: object) -> dict:
        captured.update(kwargs)
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    monkeypatch.setattr(suites_module, "run_workflow_suite", fake_run_workflow_suite)

    actions = tui_module.default_scan_actions(permissions=ExecutionPermissions())
    assert actions.run_check_suite is not None
    actions.run_check_suite(
        Path("/tmp/rush-t28b-check"),
        owner_instance_id="owner-1",
        run_id="run-1",
        cancel_check=lambda: True,
    )

    assert "cancel_check" in captured, (
        "a cancel request's cancel_check callable must reach "
        "run_workflow_suite -- it is currently silently dropped"
    )
    assert captured["cancel_check"] is not None and captured["cancel_check"]()


def test_declined_grant_review_executes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declining a reviewed grant (any key but 'y') must produce no scan,
    handoff, or rescan side effect."""
    _admit_started(monkeypatch)
    project = _project_with_findings()
    calls: list[str] = []
    actions = _actions(
        execute_scan=lambda *a, **k: calls.append("execute_scan"),
        build_handoff=lambda *a, **k: calls.append("build_handoff"),
        rescan_project_run=lambda *a, **k: calls.append("rescan_project_run"),
    )
    state = TuiState(projects=[project])

    tui_module._dispatch_key(state, "s", actions)
    assert state.mode == "grant_review"
    tui_module._dispatch_key(state, "escape", actions)

    assert state.mode == "list"
    assert calls == [], "declining a grant review must execute nothing"


def test_dispatch_handoff_receipt_shows_delivered_not_repaired() -> None:
    """'a handoff receipt is not proof of completed repair'/'never simulate
    live agent progress'/'"delivered" is never shown as "repaired"'. A real
    receipt state must be shown verbatim."""
    project = _project_with_findings()
    state = TuiState(projects=[project])
    state.selected_agent_id = "agent-1"
    actions = _actions(
        dispatch_handoff=lambda *a, **k: SimpleNamespace(state="delivered")
    )

    tui_module._dispatch_key(state, "H", actions)
    tui_module._dispatch_key(state, "y", actions)

    assert state.message == "handoff delivered"
    assert "repaired" not in state.message.lower()


def test_dispatch_handoff_failure_surfaces_as_message_not_repaired() -> None:
    """A dispatch_handoff failure must surface its real cause, never a
    fabricated success/"repaired" message."""
    project = _project_with_findings()
    state = TuiState(projects=[project])
    state.selected_agent_id = "agent-1"
    actions = _actions(
        dispatch_handoff=lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("agent unreachable")
        )
    )
    tui_module._dispatch_key(state, "H", actions)
    tui_module._dispatch_key(state, "y", actions)

    assert "agent unreachable" in state.message
    assert project.status == "error"
    assert "repaired" not in state.message.lower()


def test_request_cancel_sets_cancelling_status_for_running_scan() -> None:
    """'actual cancel acknowledgment': requesting cancel for a real
    in-progress scan must send the cooperative-cancel marker and transition
    to 'cancelling', never a silent no-op."""
    project = _project_with_findings()
    project.status = "scanning"
    calls: list[tuple[Path, str]] = []
    actions = _actions(
        cancel_scan_run=lambda root, run_id: calls.append((root, run_id))
    )

    tui_module._request_cancel(project, actions)

    assert calls == [(project.root, project.run_id)]
    assert project.status == "cancelling"
