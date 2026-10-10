"""Phase 70 T28-B continuation: Scans history wired into the section loader
path, Setup toggle/apply/retry actions driven by real key events, and the
per-stage `on_progress` hook on `setup_wizard.apply_setup_review`."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

import rush.tui as tui_module
from rush.permissions import ExecutionPermissions
from rush.tools import setup_wizard
from rush.tui import ProjectState, ScanActions, TuiState


def _actions() -> ScanActions:
    return ScanActions(
        plan_scan=lambda *a, **k: SimpleNamespace(plan_id="plan-1", candidates=[1]),
        execute_scan=lambda *a, **k: SimpleNamespace(aggregate=None),
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {"run": {"run_id": "r"}},
        build_handoff=lambda *a, **k: SimpleNamespace(
            handoff_id="h1", session_capability="c1"
        ),
        dispatch_handoff=lambda *a, **k: SimpleNamespace(state="delivered"),
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        dashboard_owner=lambda root: None,
    )


def _render_text(state: TuiState) -> str:
    console = Console(record=True, width=160)
    console.print(tui_module.render_app(state))
    return console.export_text()


def _keys(state: TuiState, actions: ScanActions, *keys: str) -> None:
    for key in keys:
        tui_module._dispatch_key(state, key, actions)


def _pump_until(state: TuiState, actions: ScanActions, key: tuple[str, str]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        tui_module._pump(state, actions)
        view = state.views.get(key)
        if view is not None and view.state not in ("loading", None):
            return
        time.sleep(0.01)
    pytest.fail(f"section load for {key!r} never finished")


def _seed_manifest(
    root: Path, run_id: str, attempt: str, state: str, findings: int
) -> None:
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "attempt_id": attempt,
                "run_state": state,
                "created_at": f"2026-09-2{findings}T10:00:00+00:00",
                "aggregate": {"findings": []},
                "totals": {"finding_count": findings},
            }
        ),
        encoding="utf-8",
    )


def _recording(
    calls: list[Any], result: dict[str, Any], *, record_kwargs: bool = False
) -> Any:
    def fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs if record_kwargs else args)
        return result

    return fake


# --- 1: Scans history -----------------------------------------------------


def test_entering_scans_shows_history_from_manifest_and_creates_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "proj"
    root.mkdir()
    _seed_manifest(root, "run-aaa", "attempt-1", "completed", 3)
    _seed_manifest(root, "run-bbb", "attempt-7", "failed", 0)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    project = ProjectState(name="demo", root=root)
    state = TuiState(projects=[project])
    actions = _actions()
    _keys(state, actions, "f3", "3")
    assert state.section == "scans"
    assert (tui_module.project_key(project), "scans") in state.load_requests
    _pump_until(state, actions, (tui_module.project_key(project), "scans"))

    view = state.views[(tui_module.project_key(project), "scans")]
    assert view.state == "populated"
    rendered = _render_text(state)
    for needle in (
        "run-aaa",
        "attempt-1",
        "completed",
        "2026-09-23T10:00:00+00:00",
        "findings 3",
        "run-bbb",
        "attempt-7",
        "failed",
        "findings 0",
    ):
        assert needle in rendered, f"Scans history must show {needle!r}"

    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    assert after == before, "reading Scans history must create zero files"


def test_scans_history_empty_without_runs_creates_no_rush_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = ProjectState(name="demo", root=tmp_path)
    state = TuiState(projects=[project])
    actions = _actions()
    _keys(state, actions, "f3", "3")
    _pump_until(state, actions, (tui_module.project_key(project), "scans"))
    view = state.views[(tui_module.project_key(project), "scans")]
    assert view.state == "empty"
    assert "no completed scan runs" in _render_text(state)
    assert not (tmp_path / ".rush").exists()


# --- 2: Setup actions -----------------------------------------------------

_FAKE_REVIEW: dict[str, Any] = {
    "kind": "setup_review",
    "review_id": "rev-1",
    "grants": {
        "config_create": ["artifact_write"],
        "register": ["cache_write", "artifact_write"],
        "configure": ["cache_write"],
        "identity_resolution": ["network"],
        "engines": [],
    },
}


def _setup_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apply_fn: Any
) -> tuple[TuiState, ProjectState, ScanActions, list[int]]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    builds: list[int] = []

    def fake_build(*a: Any, **k: Any) -> dict[str, Any]:
        builds.append(1)
        return {**_FAKE_REVIEW, "review_id": f"rev-{len(builds)}"}

    monkeypatch.setattr(setup_wizard, "build_setup_review", fake_build)
    monkeypatch.setattr(setup_wizard, "render_setup_review", lambda r: "REVIEW")
    monkeypatch.setattr(setup_wizard, "apply_setup_review", apply_fn)
    project = ProjectState(name="demo", root=tmp_path)
    state = TuiState(projects=[project])
    actions = _actions()
    _keys(state, actions, "f3", "8")
    assert state.section == "setup"
    return state, project, actions, builds


def _join(project: ProjectState) -> None:
    thread = project.setup_apply_thread
    assert thread is not None, "confirming the apply review must start the worker"
    thread.join(timeout=5)


def test_setup_actions_registered_with_keys_in_footer_and_help() -> None:
    ids = {a.id for a in tui_module._section_actions("setup")}
    assert {"setup_toggle_grant", "setup_apply", "setup_retry"} <= ids
    for action_id in ("setup_toggle_grant", "setup_apply", "setup_retry"):
        assert any(b.action_name == action_id for b in tui_module._BINDINGS), (
            f"{action_id} must have a key binding"
        )
    project = ProjectState(name="demo", root=Path("/nonexistent-t28b"))
    state = TuiState(projects=[project])
    state.section = "setup"
    footer = tui_module._keymap_footer(state).plain
    for label in ("t:Toggle grant", "p:Apply setup", "x:Retry stage"):
        assert label in footer, f"footer must list {label!r}: {footer!r}"


def test_toggle_apply_lists_exactly_toggled_grants_then_applies_with_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Any, Any]] = []

    def fake_apply(review, permissions, consent, *, on_progress=None, **k):
        calls.append((review, permissions))
        assert on_progress is not None
        on_progress("config", "started")
        on_progress("config", "completed")
        return {"status": "ok"}

    state, project, actions, _ = _setup_state(tmp_path, monkeypatch, fake_apply)
    rendered = _render_text(state)
    assert "register off" in rendered and "configure off" in rendered

    # highlight moves config_create -> register; `t` turns register on.
    _keys(state, actions, "j", "t")
    data = state.views[(tui_module.project_key(project), "setup")].data
    assert data["stage_grants"]["register"] is True
    assert data["stage_grants"]["config_create"] is False
    assert "register on" in _render_text(state)

    _keys(state, actions, "p")
    assert state.mode == "grant_review"
    grant = state.pending_grant
    assert grant is not None and grant["kind"] == "setup_apply"
    assert grant["grants"] == "artifact_write, cache_write"
    assert grant["stages"] == "register"
    review_text = _render_text(state)
    assert "grants: artifact_write, cache_write" in review_text
    assert not calls, "opening the review must not apply anything"

    _keys(state, actions, "y")
    _join(project)
    assert len(calls) == 1
    applied_review, permissions = calls[0]
    assert applied_review["review_id"] == data["review"]["review_id"]
    granted = {n for n, on in permissions.to_dict().items() if on}
    assert granted == {"artifact_write", "cache_write"}
    assert list(project.setup_apply_events) == [
        ("config", "started"),
        ("config", "completed"),
    ]
    assert "config completed" in _render_text(state)


def test_toggle_twice_turns_off_and_apply_with_nothing_lists_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    state, project, actions, _ = _setup_state(
        tmp_path, monkeypatch, _recording(calls, {"status": "ok"})
    )
    _keys(state, actions, "t", "t", "p")
    grant = state.pending_grant
    assert grant is not None and grant["grants"] == "none"
    assert grant["stages"] == "none"
    _keys(state, actions, "n")
    assert state.message == "declined"
    assert project.setup_apply_thread is None and not calls


def test_launch_grant_stage_defaults_on_and_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        setup_wizard, "build_setup_review", lambda *a, **k: dict(_FAKE_REVIEW)
    )
    monkeypatch.setattr(setup_wizard, "render_setup_review", lambda r: "REVIEW")
    project = ProjectState(name="demo", root=tmp_path)
    project.launch_permissions = ExecutionPermissions(cache_write=True)
    state = TuiState(projects=[project])
    actions = _actions()
    _keys(state, actions, "f3", "8", "p")
    grant = state.pending_grant
    assert grant is not None
    assert grant["stages"] == "configure"
    assert grant["grants"] == "cache_write"


def test_failed_stage_retry_regenerates_review_and_never_reapplies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    def failing_apply(review, permissions, consent, *, on_progress=None, **k):
        calls.append(review)
        on_progress("configure", "started")
        on_progress("configure", "failed")
        return {"status": "partial"}

    state, project, actions, builds = _setup_state(tmp_path, monkeypatch, failing_apply)
    _keys(state, actions, "x")
    assert state.mode != "grant_review", "retry needs a failed stage first"

    _render_text(state)
    first_review = state.views[(tui_module.project_key(project), "setup")].data[
        "review"
    ]
    _keys(state, actions, "p", "y")
    _join(project)
    assert len(calls) == 1

    _keys(state, actions, "x")
    grant = state.pending_grant
    assert state.mode == "grant_review"
    assert grant is not None and grant["kind"] == "setup_retry"
    assert grant["failed_stage"] == "configure"
    builds_before = len(builds)
    _keys(state, actions, "y")
    assert len(builds) == builds_before + 1, "retry must regenerate the review"
    assert len(calls) == 1, "retry must never re-apply the old review"
    new_review = state.views[(tui_module.project_key(project), "setup")].data["review"]
    assert new_review["review_id"] != first_review["review_id"]
    assert "review regenerated" in state.message


def test_apply_review_is_stale_after_project_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    state, project, actions, _ = _setup_state(
        tmp_path, monkeypatch, _recording(calls, {"status": "ok"})
    )
    _keys(state, actions, "p")
    project.run_id = "changed-after-review"
    _keys(state, actions, "y")
    assert "stale" in state.message
    assert project.setup_apply_thread is None and not calls


def test_worker_records_terminal_status_without_stage_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, project, actions, _ = _setup_state(
        tmp_path,
        monkeypatch,
        lambda *a, **k: {"status": "permission_denied", "missing": ["x"]},
    )
    _keys(state, actions, "p", "y")
    _join(project)
    assert list(project.setup_apply_events) == [("setup", "permission_denied")]
    assert "setup permission_denied" in _render_text(state)


# --- 3: apply_setup_review on_progress -----------------------------------


@pytest.fixture
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return home


_ALL = ExecutionPermissions(cache_write=True, artifact_write=True)


def test_on_progress_reports_each_stage_start_and_end_in_order(
    tmp_path: Path, _home: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    review = setup_wizard.build_setup_review(root)
    events: list[tuple[str, str]] = []
    result = setup_wizard.apply_setup_review(
        review, _ALL, None, on_progress=lambda s, st: events.append((s, st))
    )
    assert result["status"] == "ok"
    assert events == [
        ("config", "started"),
        ("config", "completed"),
        ("register", "started"),
        ("register", "completed"),
        ("configure", "started"),
        ("configure", "completed"),
        ("engines", "started"),
        ("engines", "completed"),
    ]


def test_on_progress_reports_failed_stage(
    tmp_path: Path, _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    review = setup_wizard.build_setup_review(root)

    def boom(self: Any) -> Any:
        raise OSError("registry unwritable")

    monkeypatch.setattr(setup_wizard._SetupTransaction, "register", boom)
    events: list[tuple[str, str]] = []
    result = setup_wizard.apply_setup_review(
        review, _ALL, None, on_progress=lambda s, st: events.append((s, st))
    )
    assert result["status"] != "ok"
    assert events == [
        ("config", "started"),
        ("config", "completed"),
        ("register", "started"),
        ("register", "failed"),
    ]


def _normalized(value: Any, root: Path, project_id: str) -> str:
    """Root-derived text removed: the root, the project id, hex ids/hashes."""
    text = json.dumps(value, sort_keys=True, default=str).replace(str(root), "<ROOT>")
    text = text.replace(project_id, "<PID>")
    return re.sub(r"[0-9a-f]{12,64}", "<HEX>", text)


class _Consent:
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)

    def ask(self, prompt: str) -> str:
        self.written.append(prompt)
        return "y"


def test_cli_output_and_result_unchanged_by_the_hook(
    tmp_path: Path, _home: Path
) -> None:
    outputs = []
    for name, hook in (("a", None), ("b", lambda s, st: None)):
        root = tmp_path / name / "proj"
        root.mkdir(parents=True)
        consent = _Consent()
        review = setup_wizard.build_setup_review(root)
        if hook is None:
            result = setup_wizard.apply_setup_review(review, None, consent)
        else:
            result = setup_wizard.apply_setup_review(
                review, None, consent, on_progress=hook
            )
        pid = str(result["project_id"])
        outputs.append(
            (_normalized(consent.written, root, pid), _normalized(result, root, pid))
        )
    assert outputs[0] == outputs[1]
    assert "started" not in outputs[0][0] and "completed" not in outputs[0][0]


def test_interactive_cli_never_passes_a_progress_hook(
    tmp_path: Path, _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        setup_wizard,
        "apply_setup_review",
        _recording(seen, {"status": "ok"}, record_kwargs=True),
    )
    setup_wizard.run_interactive_setup(tmp_path, None, _Consent(), which=lambda n: None)
    assert seen and all("on_progress" not in k for k in seen)
