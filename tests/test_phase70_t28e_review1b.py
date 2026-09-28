"""Phase 70 T28-E review round 1, part B (plan lines 424-427, 430-431).

Kiara's round-1 review reproduced these defects (`.orchestrator/kiara_repro.py`
r5/r6/r7 and the r11 case); each test below pins one of them:

- r5: a new run manifest or handoff never refreshed the open Tokens view (its
  cache key covered only `tokens.db`), and the staleness check ran on the
  loop thread.
- r11: Tokens showed no measurement interval, never labelled unscoped events,
  and offered only a run filter with no attribution.
- r6: the evidence buckets (scan outputs, handoffs, memory) rendered only
  their first 20 items as plain, unselectable lines.
- r7: rendering Artifacts globbed and stat'ed every manifest per frame and ran
  `list_project_artifacts` on a cache miss on the render thread.
- `rush gain` rebuilt `root_token_usage` every tick with no invalidation.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from rush import tui
from rush.permissions import ExecutionPermissions
from rush.token_economy.telemetry import TelemetryStore
from rush.workflows import projects as wp
from tests import test_phase70_tui_usability_ef as H


def _attempt(
    root: Path,
    project_id: str,
    run_id: str,
    *,
    tokens: int | None = None,
    created_at: str = "2026-01-01T00:00:00+00:00",
    scheduled: list[dict[str, Any]] | None = None,
    **identity: str,
) -> None:
    """One completed attempt manifest (plus its attempt.json), optionally
    carrying stored agent/session identities."""
    attempt_id = f"{run_id}-attempt-1"
    items = scheduled
    if items is None:
        child: dict[str, Any] = {"status": "ok"}
        if tokens is not None:
            child["metrics"] = {"total_tokens": tokens}
        items = [{"candidate_id": "t", "category": "lint", "child": child}]
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "project_id": project_id,
        "root": str(root),
        "run_state": "completed",
        "created_at": created_at,
        "scheduled": items,
        **identity,
    }
    (attempt_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (attempt_dir / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "project_id": project_id,
                "started_at": created_at,
                "attempt_generation": 1,
            }
        ),
        encoding="utf-8",
    )


def _handoff(root: Path, handoff_id: str, **fields: Any) -> None:
    handoffs = root / ".rush" / "handoffs"
    handoffs.mkdir(parents=True, exist_ok=True)
    (handoffs / f"{handoff_id}.json").write_text(
        json.dumps({"handoff_id": handoff_id, **fields}), encoding="utf-8"
    )


def _pump_until(
    state: tui.TuiState,
    actions: tui.ScanActions,
    done: Callable[[str], bool],
    *,
    seconds: float = 3.0,
) -> str:
    """Drive the loop (one `_pump` per tick, like `run_interactive_tui`)
    until `done(frame)` holds, bounded; returns the last frame."""
    deadline = time.monotonic() + seconds
    while True:
        tui._pump(state, actions)
        text = H._render(state)
        if done(text) or time.monotonic() > deadline:
            return text
        time.sleep(0.02)


def _off_main_thread(name: str, real: Callable[..., Any]) -> Callable[..., Any]:
    """`real`, except that calling it on the loop (render/input) thread
    raises."""

    def guarded(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread() is threading.main_thread():
            raise AssertionError(f"{name} ran on the render/input thread")
        return real(*args, **kwargs)

    return guarded


# --------------------------------------------------------------------------
# r5: Tokens invalidation covers run manifests and handoffs, off-thread
# --------------------------------------------------------------------------


def test_r5_new_run_manifest_refreshes_open_tokens_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    _attempt(root, project_id, "run-a", tokens=1200)
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)
    H._section(state, actions, "5")
    H._settle(state, actions, "tokens")
    assert "1200" in H._render(state)

    # From here on the staleness check may only run off the loop thread.
    monkeypatch.setattr(
        tui,
        "_tokens_cache_key",
        _off_main_thread("_tokens_cache_key", tui._tokens_cache_key),
    )
    _attempt(root, project_id, "run-b", tokens=300)
    text = _pump_until(state, actions, lambda frame: "1500" in frame)
    assert "1500" in text, f"a new run manifest must refresh Tokens: {text}"


def test_r5_new_handoff_refreshes_open_tokens_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    _attempt(root, project_id, "run-a", tokens=1200)
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)
    H._section(state, actions, "5")
    H._settle(state, actions, "tokens")
    assert '"total_tokens": 800' not in H._render(state)

    monkeypatch.setattr(
        tui,
        "_tokens_cache_key",
        _off_main_thread("_tokens_cache_key", tui._tokens_cache_key),
    )
    _handoff(root, "H1", run_id="run-a", packet={"tokens": 800})
    text = _pump_until(state, actions, lambda frame: '"total_tokens": 800' in frame)
    assert '"total_tokens": 800' in text, f"a new handoff must refresh Tokens: {text}"


# --------------------------------------------------------------------------
# r11: unscoped label, measurement interval, run/agent/session attribution
# --------------------------------------------------------------------------


def _attribution_project(tmp_path: Path) -> tuple[str, Path, Path]:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    _attempt(
        root,
        project_id,
        "run-a",
        tokens=1200,
        created_at="2026-01-01T00:00:00+00:00",
        agent_id="ag-1",
        session_id="s-1",
    )
    _attempt(
        root,
        project_id,
        "run-b",
        tokens=300,
        created_at="2026-01-03T00:00:00+00:00",
        agent_id="ag-2",
        session_id="s-2",
    )
    # No stored agent/session identity: unscoped for an agent/session view.
    _attempt(
        root, project_id, "run-c", tokens=77, created_at="2026-01-05T00:00:00+00:00"
    )
    # A telemetry row with no stored identity at all.
    TelemetryStore(root).record_savings("tool-x", raw_tokens=900, compressed_tokens=400)
    return project_id, root, data_root


def test_r11_token_usage_reports_unscoped_count_and_interval(tmp_path: Path) -> None:
    project_id, _root, data_root = _attribution_project(tmp_path)

    scoped = wp.project_token_usage(project_id, data_root=data_root, agent_id="ag-1")
    assert scoped["provider_reported"]["total_tokens"] == 1200
    # run-b is foreign (other agent), not unscoped; run-c and the telemetry
    # row carry no agent identity: two unscoped events, never counted in.
    assert scoped["unscoped"]["event_count"] == 2, scoped["unscoped"]
    assert scoped["unscoped"]["identity_keys"] == ["agent_id"]
    assert scoped["interval"]["earliest"] == "2026-01-01T00:00:00+00:00"
    assert scoped["interval"]["latest"] == "2026-01-01T00:00:00+00:00"

    whole = wp.project_token_usage(project_id, data_root=data_root)
    assert whole["provider_reported"]["total_tokens"] == 1577
    # Unfiltered: only the telemetry row lacks a stored run identity.
    assert whole["unscoped"]["event_count"] == 1, whole["unscoped"]
    assert whole["unscoped"]["identity_keys"] == ["run_id"]
    assert whole["interval"]["earliest"] == "2026-01-01T00:00:00+00:00"
    latest = whole["interval"]["latest"]
    assert latest is not None and latest > "2026-01-05T00:00:00+00:00", latest


def _filter(state: tui.TuiState, actions: tui.ScanActions, text: str) -> None:
    H._keys(state, actions, "/")
    H._type(state, actions, text)
    H._keys(state, actions, "enter")
    H._settle(state, actions, "tokens")


def test_r11_tokens_view_labels_unscoped_interval_and_attribution(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _attribution_project(tmp_path)
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)
    H._section(state, actions, "5")
    H._settle(state, actions, "tokens")
    text = H._render(state)
    assert "interval: 2026-01-01T00:00:00+00:00 .. " in text, text
    assert "unscoped: 1 event without stored run_id identity" in text, text
    assert "attribution: run all | agent all | session all" in text, text

    def filters() -> dict[str, Any]:
        return state.views[(tui.project_key(state.active_project), "tokens")].filters

    _filter(state, actions, "agent:ag-1")
    assert filters() == {"agent_id": "ag-1"}, filters()
    text = H._render(state)
    assert '"total_tokens": 1200' in text and "1577" not in text, text
    assert "attribution: run all | agent ag-1 | session all" in text, text
    assert (
        "unscoped: 2 events without stored agent_id identity "
        "(excluded from this selection)"
    ) in text, text
    assert "interval: 2026-01-01T00:00:00+00:00 .. 2026-01-01T00:00:00+00:00" in text, (
        text
    )

    H._keys(state, actions, "/", "escape")
    assert not filters()
    _filter(state, actions, "session:s-2")
    text = H._render(state)
    assert '"total_tokens": 300' in text, text
    assert "attribution: run all | agent all | session s-2" in text, text
    assert "interval: 2026-01-03T00:00:00+00:00 .. 2026-01-03T00:00:00+00:00" in text, (
        text
    )

    H._keys(state, actions, "/", "escape")
    _filter(state, actions, "run:run-c")
    text = H._render(state)
    assert '"total_tokens": 77' in text, text
    assert "attribution: run run-c | agent all | session all" in text, text

    # A plain id is still a run id (the original `/` contract).
    H._keys(state, actions, "/", "escape")
    _filter(state, actions, "run-a")
    assert filters() == {"run_id": "run-a"}
    assert "attribution: run run-a | agent all | session all" in H._render(state)


# --------------------------------------------------------------------------
# r6: every evidence item is in one selectable, paginated, inspectable index
# --------------------------------------------------------------------------


def test_r6_thirty_handoffs_are_selectable_paginated_and_inspectable(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    item = H._captured_item(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="t",
        rel_path="r.txt",
        data=b"x",
    )
    H._write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        project_id=project_id,
        scheduled=[item],
    )
    for n in range(30):
        _handoff(root, f"H{n:02d}", run_id="run-a", packet={"tokens": n})
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)
    H._section(state, actions, "7")
    H._settle(state, actions, "artifacts")

    text = H._render(state)
    # One scan output + 30 handoffs, beneath the captured index.
    assert "Evidence (31) of 31 page 1/2" in text, text

    seen: dict[int, str] = {}
    for _ in range(40):
        for line in H._render(state).splitlines():
            for n in range(30):
                if f"handoff:H{n:02d}" in line:
                    seen[n] = line
        H._keys(state, actions, "j")
    assert sorted(seen) == list(range(30)), f"unreachable: {set(range(30)) - set(seen)}"
    for n, line in seen.items():
        assert "handoffs" in line and "run-a" in line, (n, line)
        assert " B" in line, f"H{n:02d} row must show its size: {line}"
    assert "Evidence (31) of 31 page 2/2" in H._render(state)

    # The last row is the selected one and inspects to its full record.
    selected = [line for line in H._render(state).splitlines() if "handoff:H29" in line]
    assert selected and ">" in selected[0], selected
    H._keys(state, actions, "i")
    text = H._render(state)
    # The reference record `list_project_artifacts` carries for it.
    assert '"artifact_ref": "handoff:H29"' in text, text
    assert '"tokens": 29' in text and '"run_id": "run-a"' in text, text


# --------------------------------------------------------------------------
# r7: rendering Artifacts only reads the view
# --------------------------------------------------------------------------


def test_r7_render_does_no_artifact_index_io_and_refreshes_off_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)

    def write(run: str) -> None:
        H._write_attempt(
            root,
            run_id=run,
            attempt_id=f"{run}-attempt-1",
            project_id=project_id,
            scheduled=[
                H._captured_item(
                    root,
                    run_id=run,
                    attempt_id=f"{run}-attempt-1",
                    candidate_id="t",
                    rel_path=f"{run}.txt",
                    data=b"x",
                )
            ],
        )

    for n in range(3):
        write(f"run-{n}")
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)
    H._section(state, actions, "7")
    H._settle(state, actions, "artifacts")

    real_glob, real_stat = Path.glob, Path.stat

    def glob(self: Path, pattern: str, *args: Any, **kwargs: Any) -> Any:
        if (
            "manifest" in pattern
            and threading.current_thread() is threading.main_thread()
        ):
            raise AssertionError(f"manifest glob {pattern!r} on the render thread")
        return real_glob(self, pattern, *args, **kwargs)

    def stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "manifest.json" and (
            threading.current_thread() is threading.main_thread()
        ):
            raise AssertionError(f"manifest stat {self} on the render thread")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "glob", glob)
    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(
        wp,
        "list_project_artifacts",
        _off_main_thread("list_project_artifacts", wp.list_project_artifacts),
    )
    monkeypatch.setattr(
        tui,
        "_artifacts_cache_key",
        _off_main_thread("_artifacts_cache_key", tui._artifacts_cache_key),
    )

    for _ in range(3):
        text = H._render(state)
    assert "t:run-2.txt" in text, text

    # A new attempt is picked up by the worker-side staleness check.
    write("run-3")
    text = _pump_until(state, actions, lambda frame: "t:run-3.txt" in frame)
    assert "t:run-3.txt" in text, f"a new attempt must refresh Artifacts: {text}"


def test_artifacts_first_entry_reads_off_the_input_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    H._write_attempt(
        root,
        run_id="run-0",
        attempt_id="run-0-attempt-1",
        project_id=project_id,
        scheduled=[
            H._captured_item(
                root,
                run_id="run-0",
                attempt_id="run-0-attempt-1",
                candidate_id="t",
                rel_path="run-0.txt",
                data=b"x",
            )
        ],
    )
    monkeypatch.setattr(
        wp,
        "list_project_artifacts",
        _off_main_thread("list_project_artifacts", wp.list_project_artifacts),
    )
    monkeypatch.setattr(
        tui,
        "_artifacts_cache_key",
        _off_main_thread("_artifacts_cache_key", tui._artifacts_cache_key),
    )
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = H._state(root, project_id, data_root)

    # Entering Artifacts the first time (the key handler) reads nothing: the
    # section loader is queued and a loading line renders meanwhile.
    H._section(state, actions, "7")
    assert state.section == "artifacts"
    text = H._render(state)
    assert "Artifacts loading" in text, text
    assert "t:run-0.txt" not in text, text

    # The index appears once the worker's result is drained.
    text = _pump_until(state, actions, lambda frame: "t:run-0.txt" in frame)
    assert "t:run-0.txt" in text, f"the worker load must land the index: {text}"
    assert "Artifacts loading" not in text, text


# --------------------------------------------------------------------------
# `rush gain`: idle refreshes do not re-read token usage
# --------------------------------------------------------------------------


def _gain_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, list[int]]:
    data_root = tmp_path / "data"
    project_id, root = H._register(tmp_path, "p", data_root)
    _attempt(root, project_id, "run-a", tokens=1200)
    monkeypatch.setattr(
        "rush.invocation.targets.resolve_logical_root", lambda *a, **k: root
    )
    reads: list[int] = []
    real = wp._iter_run_manifests

    def counting(r: Path) -> list[dict[str, Any]]:
        reads.append(1)
        return real(r)

    monkeypatch.setattr(wp, "_iter_run_manifests", counting)
    return root, project_id, reads


def test_gain_live_panel_idle_refreshes_do_not_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.cli as cli_module

    _root, _project_id, reads = _gain_setup(tmp_path, monkeypatch)
    console = Console(record=True, width=160)
    cli_module._run_gain_live_panel(console=console, max_updates=5, refresh_seconds=0.0)
    assert "1,200" in console.export_text()
    # Nothing watched changed across five refreshes: one read, not six.
    assert len(reads) == 1, reads


def test_gain_live_panel_rereads_when_a_watched_input_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.cli as cli_module

    root, project_id, reads = _gain_setup(tmp_path, monkeypatch)
    real_sleep = time.sleep
    ticks: list[int] = []

    def sleep(seconds: float) -> None:
        ticks.append(1)
        if len(ticks) == 3:
            _attempt(root, project_id, "run-b", tokens=300)
        real_sleep(0)

    monkeypatch.setattr(time, "sleep", sleep)
    console = Console(record=True, width=160)
    cli_module._run_gain_live_panel(console=console, max_updates=6, refresh_seconds=0.0)
    assert "1,500" in console.export_text()
    # The initial read, then exactly one re-read after the new manifest.
    assert len(reads) == 2, reads
