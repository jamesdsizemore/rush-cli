"""Phase 70 T28-E (W4-T23-T29 design gate): Tokens, Git, Artifacts.

Binding design: `.scratch/phase-70-design-gate/W4-T23-T29.md`, "### T28-E: Tokens,
Git, Artifacts" plus "### Shared design (all packets)" and cross-cutting X2/X7/X9.
Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`,
"T28-E — Real Tokens, navigable Git and all artifact evidence".

None of T28-E's own deliverables have landed in this worktree (T28 is not in the
merged set: T2, T3, T6, T8-T18, T20, T22, T23, T24, T26, TS). Every test below is
RED against the real, current `src/rush` code -- either a missing symbol
(`AttributeError`), a missing keyword parameter (`TypeError`), or a real behavioral
gap (a mutating/creating call where a read-only one is required, or a hostile git
hook that actually executes). Fixtures are local to this file; no shared
conftest/helper is edited.

Names this file fixes for the implementer (not yet in `src/rush`, chosen here
because the binding design describes behavior, not exact signatures):
- `rush.workflows.projects.project_git_branch(project, *, data_root=None)`
- `rush.workflows.projects.project_git_worktree(project, *, data_root=None)`
- `rush.workflows.projects.project_git_dirty_diff(project, path, *, data_root=None)`
- `rush.workflows.projects.read_project_artifact_page(project, cursor, *, data_root=None)`
- `rush.workflows.projects.export_project_artifact(project, *, run_id, attempt_id,
  tool_id, path, destination, permissions, data_root=None, expected_sha256=None)`
- `project_token_usage(..., run_id=None, agent_id=None, session_id=None)` (new
  keyword-only filters on the existing function).
"""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from rush import tui as tui_mod
from rush.dashboard import server as dashboard_server
from rush.io.physical_paths import ContainmentError
from rush.permissions import ExecutionPermissions
from rush.token_economy.telemetry import TelemetryStore
from rush.workflows import projects as wp
from rush.workflows.project_run import load_run_manifest

pytestmark = pytest.mark.usefixtures("hermetic_engine_path")

# --------------------------------------------------------------------------
# Fixtures local to this file
# --------------------------------------------------------------------------

_GIT_ENV = {**os.environ}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test Author",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        cwd=root,
        env=_GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "--quiet")


def _commit(root: Path, rel_path: str, content: str, message: str) -> str:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(root, "add", rel_path)
    _git(root, "commit", "--quiet", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def _project(
    tmp_path: Path, name: str, *, init_git: bool = False
) -> tuple[str, Path, Path]:
    root = tmp_path / name
    if init_git:
        _init_repo(root)
    else:
        root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    data_root = _data_root(tmp_path) / name
    record = wp.register_project(root, data_root=data_root)
    return record.project_id, root, data_root


def _write_attempt(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    generation: int,
    project_id: str,
    scheduled: list[dict[str, Any]],
) -> None:
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": f"plan-{run_id}",
        "project_id": project_id,
        "root": str(root),
        "run_state": "completed",
        "severity": "warn",
        "concurrency": 1,
        "timeout_seconds": 300,
        "created_at": "2026-01-01T00:00:00+00:00",
        "candidates": scheduled,
        "scheduled": scheduled,
        "aggregate": {
            "tool": "scan",
            "engine": None,
            "status": "ok",
            "findings": [],
            "metadata": {"coverage": {"empty": False}},
        },
        "totals": {
            "candidate_count": len(scheduled),
            "scheduled_count": len(scheduled),
            "executed_count": len(scheduled),
            "finding_count": 0,
        },
    }
    (attempt_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (attempt_dir / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "plan_id": f"plan-{run_id}",
                "project_id": project_id,
                "started_at": "2026-01-01T00:00:00+00:00",
                "attempt_generation": generation,
            }
        ),
        encoding="utf-8",
    )


def _snapshot_artifact(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    candidate_id: str,
    rel_path: str,
    data: bytes,
    index: int = 0,
    media_type: str = "text/plain",
) -> dict[str, Any]:
    import hashlib

    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:24]
    immutable_rel = (
        f".rush/runs/{run_id}/attempts/{attempt_id}/artifacts/{digest}/{index}.bin"
    )
    immutable_path = root / immutable_rel
    immutable_path.parent.mkdir(parents=True, exist_ok=True)
    immutable_path.write_bytes(data)
    return {
        "immutable_path": immutable_rel,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": media_type,
    }


def _cursor(
    *,
    project_id: str,
    run_id: str,
    attempt_id: str,
    tool_id: str,
    path: str,
    sha256: str,
    offset: int = 0,
) -> str:
    payload = {
        "project_id": project_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "tool_id": tool_id,
        "path": path,
        "sha256": sha256,
        "offset": offset,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _legacy_telemetry_db(root: Path) -> Path:
    """A tokens.db with the pre-P69-07 schema: no project_id/run_id/agent_id/
    session_id identity columns at all. Never goes through `TelemetryStore`
    (which would migrate it on construction) -- raw `sqlite3` only."""
    db_path = root / ".rush" / "telemetry" / "tokens.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE token_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                raw_tokens INTEGER NOT NULL,
                compressed_tokens INTEGER NOT NULL,
                duration_ms REAL NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO token_events "
            "(timestamp, tool_name, raw_tokens, compressed_tokens, duration_ms) "
            "VALUES (1700000000, 'legacy_tool', 5000, 3000, 1.0)"
        )
        conn.commit()
    return db_path


def _spawn_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-spawn spy: any `subprocess.Popen`/`subprocess.run` call during a
    read-only operation is a bug, not an implementation detail."""

    def _forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"unexpected subprocess spawn: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "run", _forbidden)


def _argv_spy(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Records every `subprocess.run` argv used by `rush.workflows.projects`'s
    Git helpers, while still delegating to the real `subprocess.run` so the
    Git command actually executes (not a behavior-replacing mock)."""
    calls: list[list[str]] = []
    original_run = subprocess.run

    def _recording_run(argv: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(list(argv))
        return original_run(argv, *args, **kwargs)

    monkeypatch.setattr(wp.subprocess, "run", _recording_run)
    return calls


def _require_state_field(state: Any, name: str, *, why: str) -> None:
    """T28-E's shared design pins `TuiState.section`/`TuiState.views` (the
    per-section state model powering Tokens/Git/Artifacts). Neither exists
    in this worktree yet -- fail naming exactly what's missing, not with a
    raw AttributeError."""
    if not hasattr(state, name):
        pytest.fail(f"TuiState.{name} is not implemented yet ({why})")


def _render_text(state: Any) -> str:
    from rich.console import Console

    console = Console(record=True, width=140)
    console.print(tui_mod.render_app(state))
    return console.export_text()


def _settle(state: Any, actions: Any, section: str) -> None:
    """Drive the loop the way `run_interactive_tui` does (one `_pump` per
    tick) until `section` has no request in flight and its view has left
    "loading", bounded to 2 s."""
    project = state.active_project
    deadline = time.monotonic() + 2.0
    while True:
        tui_mod._pump(state, actions)
        view = state.views.get((tui_mod.project_key(project), section))
        idle = not any(str(key).startswith(section) for key in project.pending) and all(
            request[1] != section for request in state.load_requests
        )
        if idle and (view is None or view.state != "loading"):
            return
        assert time.monotonic() < deadline, f"{section} still loading after 2 s"
        time.sleep(0.01)


def _find_action(section: str, keyword: str) -> Any:
    """Look up a real entry in the shared design's finite `ACTIONS` registry
    (`Action(id, sections, keys, label, enabled, run)`) belonging to
    `section` whose id/label mentions `keyword`. Fails naming exactly what's
    missing/searched rather than an opaque `AttributeError`/`StopIteration`."""
    if not hasattr(tui_mod, "ACTIONS"):
        pytest.fail(
            "rush.tui.ACTIONS (the finite Action registry) is not implemented yet"
        )
    for action in tui_mod.ACTIONS:
        if section in action.sections and keyword.lower() in (
            f"{action.id} {action.label}".lower()
        ):
            return action
    pytest.fail(
        f"no ACTIONS entry for section={section!r} matching keyword={keyword!r}"
    )


def _full_project(tmp_path: Path) -> tuple[str, Path, Path]:
    """One real project carrying Git history, token usage, and a captured
    artifact together, for exercising all three sections against the same
    project."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="report.txt",
        data=b"hello artifact bytes",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {
                    "status": "ok",
                    "artifacts": ["report.txt"],
                    "metrics": {"total_tokens": 1200},
                },
                "artifact_snapshots": {"report.txt": snapshot},
            }
        ],
    )
    return project_id, root, data_root


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------


def test_token_usage_run_id_filter_keeps_actual_tokenizer_avoided_separate_and_scoped(
    tmp_path: Path,
) -> None:
    """Plan RED->GREEN case: actual 1200+300=1500, tokenizer 800 and avoided 2000
    stay separate; a `run_id` filter excludes the foreign run's events."""
    project_id, root, data_root = _project(tmp_path, "proj")

    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 1200}},
            }
        ],
    )
    _write_attempt(
        root,
        run_id="run-b",
        attempt_id="run-b-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-b",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 300}},
            }
        ],
    )
    # Arrange assertion: the already-shipped reader really sees both attempts.
    assert load_run_manifest(root, "run-a", attempt_id="run-a-attempt-1") is not None
    assert load_run_manifest(root, "run-b", attempt_id="run-b-attempt-1") is not None

    usage = wp.project_token_usage(project_id, data_root=data_root, run_id="run-a")
    assert usage["provider_reported"]["total_tokens"] == 1200
    assert usage["provider_reported"]["total_tokens"] != 1500


def test_token_usage_agent_and_session_filters_exclude_foreign_events(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root = _project(tmp_path, "proj")
    usage = wp.project_token_usage(
        project_id, data_root=data_root, agent_id="agent-1", session_id="sess-1"
    )
    assert usage["cache_hits"]["total_tokens"] == 0


def test_token_usage_never_creates_or_migrates_telemetry_db(tmp_path: Path) -> None:
    """Read-only requirement (shared design, X2): rendering/reading Tokens must
    never construct a directory, DB, or migration -- `TelemetryStore(root)`'s
    mutating constructor does exactly that today."""
    project_id, root, data_root = _project(tmp_path, "proj")
    telemetry_dir = root / ".rush" / "telemetry"
    assert not telemetry_dir.exists()

    wp.project_token_usage(project_id, data_root=data_root)

    assert not telemetry_dir.exists(), (
        "project_token_usage must not create .rush/telemetry on a read"
    )


def test_token_usage_corrupt_telemetry_db_returns_unavailable_not_raise(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    db_path = root / ".rush" / "telemetry" / "tokens.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"not a sqlite database at all")

    # Today: TelemetryStore(root)'s constructor raises sqlite3.DatabaseError
    # while creating tables over the corrupt file -- uncaught by
    # project_token_usage, which must instead return a graceful unavailable
    # result. RED for the real bug (an uncaught DatabaseError), not a
    # fixture problem.
    usage = wp.project_token_usage(project_id, data_root=data_root)
    assert usage["cache_hits"]["total_tokens"] == 0


def test_token_usage_legacy_schema_without_identity_columns_scoped_to_zero(
    tmp_path: Path,
) -> None:
    """Legacy schema (no identity columns) counts as unscoped -- excluded from
    any run/agent/session-scoped total, never raising `OperationalError` on a
    missing column and never silently attributed to the requested scope."""
    project_id, root, data_root = _project(tmp_path, "proj")
    db_path = _legacy_telemetry_db(root)
    assert db_path.is_file()

    usage = wp.project_token_usage(project_id, data_root=data_root, run_id="run-a")
    assert usage["cache_hits"]["total_tokens"] == 0


def test_gain_panel_shows_actual_provider_usage_separately_from_compression(
    tmp_path: Path,
) -> None:
    """`rush gain`/`context gain` must show the same actual/tokenizer/avoided
    separation `project_token_usage` returns (plan: "Show actual provider usage
    separately from tokenizer counts, avoided payload estimates and cost
    estimates"). `build_gain_panel` today only renders the compression HUD."""
    from rich.console import Console

    from rush.token_economy.tui_gain import build_gain_panel

    project_id, root, _data_root = _project(tmp_path, "proj")
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 1200}},
            }
        ],
    )

    console = Console(record=True, width=120)
    console.print(build_gain_panel(root))
    rendered = console.export_text()

    assert "1200" in rendered or "Actual" in rendered or "Provider" in rendered, (
        "Tokens HUD must surface actual provider-reported usage, not only the "
        f"compression estimate; got: {rendered!r}"
    )


def test_token_usage_totals_separate_with_cost_estimate_and_unavailable_reason(
    tmp_path: Path,
) -> None:
    """Coordinator follow-up case 1: actual 1200+300=1500, tokenizer 800 and
    avoided 2000 stay separate, plus a cost estimate; an unavailable actual
    carries a reason (never a bare `0`); a `run_id` filter excludes the
    foreign run's 300."""
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 1200}},
            }
        ],
    )
    _write_attempt(
        root,
        run_id="run-b",
        attempt_id="run-b-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-b",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 300}},
            }
        ],
    )
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    (handoffs_dir / "handoff-1.json").write_text(
        json.dumps({"handoff_id": "handoff-1", "packet": {"tokens": 500}}),
        encoding="utf-8",
    )
    (handoffs_dir / "handoff-2.json").write_text(
        json.dumps({"handoff_id": "handoff-2", "packet": {"tokens": 300}}),
        encoding="utf-8",
    )
    TelemetryStore(root).record_savings(
        "tool-a", raw_tokens=5000, compressed_tokens=3000
    )

    unfiltered = wp.project_token_usage(project_id, data_root=data_root)
    assert unfiltered["provider_reported"]["total_tokens"] == 1500
    assert unfiltered["tokenizer_counted"]["total_tokens"] == 800
    assert unfiltered["estimated_avoided"]["net_tokens_saved"] == 2000
    assert unfiltered["estimated_avoided"]["dollar_savings_est"] > 0

    # An unavailable actual (no run manifests at all) must carry its reason,
    # never a coerced-known-zero `0`.
    empty_project_id, _empty_root, empty_data_root = _project(tmp_path, "empty")
    empty_usage = wp.project_token_usage(empty_project_id, data_root=empty_data_root)
    assert empty_usage["provider_reported"]["total_tokens"] is None
    assert empty_usage["provider_reported"].get("reason"), (
        "an unavailable actual-usage measurement must state why, never a bare None"
    )

    scoped = wp.project_token_usage(project_id, data_root=data_root, run_id="run-a")
    assert scoped["provider_reported"]["total_tokens"] == 1200


def test_token_usage_refreshes_only_on_root_filter_or_telemetry_mtime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 2: the Tokens section must cache its
    reader result and refresh only when root, filter, or telemetry mtime
    changes -- never once per painted frame. Drives several render ticks
    through the real TUI dispatch/render loop with an unchanged project and
    counts calls into `project_token_usage`."""
    project_id, root, _data_root = _project(tmp_path, "proj")
    calls: list[Any] = []
    original = wp.project_token_usage

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(wp, "project_token_usage", _counting)

    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)]
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions())

    _require_state_field(
        state,
        "section",
        why="a Tokens section selector is required before it can be entered "
        "and re-rendered without re-querying every frame",
    )
    _require_state_field(
        state,
        "views",
        why="the cached reader result and its invalidation key "
        "(root/filter/mtime) live in TuiState.views[(project_key, section)]",
    )

    tui_mod._dispatch_key(state, "f3", actions)
    tui_mod._dispatch_key(state, "5", actions)
    assert state.section == "tokens"
    assert calls == [], "entering Tokens only records the request"
    _settle(state, actions, "tokens")
    assert len(calls) == 1, f"entering Tokens reads once; got {len(calls)} calls"

    for _ in range(3):
        tui_mod.render_app(state)
        tui_mod._pump(state, actions)
    _settle(state, actions, "tokens")
    assert len(calls) == 1, (
        "Tokens must load project_token_usage exactly once across repeated "
        f"idle render ticks with no root/filter/mtime change; got {len(calls)} calls"
    )

    project_key = project_id
    view = state.views.get((project_key, "tokens"))
    if view is None:
        pytest.fail(
            "TuiState.views[(project_key, 'tokens')] has no entry after "
            "entering the Tokens section"
        )
    view.filters["run_id"] = "run-a"
    tui_mod.render_app(state)
    assert len(calls) == 1, "a render never reads; the loop tick requests it"
    _settle(state, actions, "tokens")
    assert len(calls) == 2, (
        "changing the Tokens section's filter must trigger exactly one more "
        f"read; got {len(calls)} calls"
    )

    TelemetryStore(root).record_savings("tool-a", raw_tokens=100, compressed_tokens=50)
    tui_mod.render_app(state)
    assert len(calls) == 2, "a render never reads; the loop tick requests it"
    _settle(state, actions, "tokens")
    assert len(calls) == 3, (
        "a changed telemetry mtime must trigger exactly one more read; "
        f"got {len(calls)} calls"
    )


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------


def test_git_commands_argv_carry_fsmonitor_and_optional_locks_hardening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 3 (argv spy, in addition to the existing
    end-to-end hostile-config tests below): every Git read carries
    `-c core.fsmonitor=false --no-optional-locks`; `show`/`diff` additionally
    carry `--no-ext-diff --no-textconv`. Also covers "paginated commits with
    author and time" (`project_git_history`) on the same hardened path."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")
    commit_sha = _commit(root, "a.txt", "one\ntwo\n", "second")
    calls = _argv_spy(monkeypatch)

    wp.project_snapshot(project_id, data_root=data_root)
    history = wp.project_git_history(project_id, data_root=data_root, limit=1)
    wp.project_git_commit_diff(project_id, commit_sha, data_root=data_root)

    assert history["has_git"] is True
    assert history["commits"][0]["author"]
    assert history["commits"][0]["date"]
    assert history.get("next_skip") is not None, "pagination must expose next_skip"

    git_calls = [argv for argv in calls if argv and argv[0] == "git"]
    assert git_calls, "expected at least one real git invocation"
    for argv in git_calls:
        assert "-c" in argv and "core.fsmonitor=false" in argv, argv
        assert "--no-optional-locks" in argv, argv
        if argv[1] == "show" or (len(argv) > 1 and "diff" in argv):
            assert "--no-ext-diff" in argv, argv
            assert "--no-textconv" in argv, argv


def test_git_section_states_missing_repo_failed_read_no_changes_distinctly(
    tmp_path: Path,
) -> None:
    """Coordinator follow-up case 3: missing repo, a failed read, and "no
    changes" must render as three distinct states -- the shared design's
    `SectionView.state` vocabulary
    (`loading|populated|empty|unavailable|denied|failed|stale|disconnected`),
    not an ambiguous mix of `None`/`False` fields."""
    no_repo_id, _no_repo_root, no_repo_data = _project(tmp_path, "no-repo")
    missing = wp.project_snapshot(no_repo_id, data_root=no_repo_data)
    assert missing["git"].get("state") == "empty", missing["git"]

    clean_id, clean_root, clean_data = _project(tmp_path, "clean", init_git=True)
    _commit(clean_root, "a.txt", "one\n", "first")
    clean = wp.project_snapshot(clean_id, data_root=clean_data)
    assert clean["git"].get("state") == "populated", clean["git"]

    failed_id, failed_root, failed_data = _project(tmp_path, "failed", init_git=True)
    _commit(failed_root, "a.txt", "one\n", "first")
    (failed_root / ".git" / "index").write_bytes(b"not a real git index")
    failed = wp.project_snapshot(failed_id, data_root=failed_data)
    assert failed["git"].get("state") == "failed", failed["git"]


def test_git_summary_never_invokes_hostile_fsmonitor_hook(tmp_path: Path) -> None:
    """Shared T28-E requirement: every Git command runs with
    `-c core.fsmonitor=false --no-optional-locks`. A hostile `core.fsmonitor`
    hook must never execute."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")

    marker = tmp_path / "fsmonitor-ran.marker"
    hook = tmp_path / "hostile-fsmonitor.sh"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n', encoding="utf-8")
    hook.chmod(0o755)
    _git(root, "config", "core.fsmonitor", str(hook))

    # Arrange assertion: the shipped Git summary genuinely reports this repo.
    snapshot = wp.project_snapshot(project_id, data_root=data_root)
    assert snapshot["git"]["has_git"] is True

    assert not marker.exists(), (
        "a Git read must run with -c core.fsmonitor=false so a repo-configured "
        "fsmonitor hook is never invoked"
    )


def test_git_status_no_optional_locks_leaves_index_mtime_unchanged(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")
    # Force a stat mismatch against the index without changing content, the
    # classic trigger for git's "racy git" index-refresh-on-read behavior.
    tracked = root / "a.txt"
    stat_before = tracked.stat()
    os.utime(tracked, (stat_before.st_atime + 5, stat_before.st_mtime + 5))

    index_path = root / ".git" / "index"
    mtime_before = index_path.stat().st_mtime_ns

    wp.project_snapshot(project_id, data_root=data_root)

    mtime_after = index_path.stat().st_mtime_ns
    assert mtime_before == mtime_after, (
        "a read-only Git status must pass --no-optional-locks and never "
        "refresh/rewrite .git/index"
    )


def test_git_commit_diff_hostile_textconv_never_invoked(tmp_path: Path) -> None:
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    commit_sha = _commit(root, "data.bin", "payload\n", "add data.bin")

    marker = tmp_path / "textconv-ran.marker"
    hook = tmp_path / "hostile-textconv.sh"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\ncat "$1"\n', encoding="utf-8")
    hook.chmod(0o755)
    (root / ".gitattributes").write_text("*.bin diff=hostile\n", encoding="utf-8")
    _git(root, "add", ".gitattributes")
    _git(root, "commit", "--quiet", "-m", "attributes")
    _git(root, "config", "diff.hostile.textconv", str(hook))

    diff = wp.project_git_commit_diff(project_id, commit_sha, data_root=data_root)
    assert diff["has_git"] is True

    assert not marker.exists(), (
        "git show/diff must pass --no-ext-diff --no-textconv so a repo-configured "
        "textconv driver is never invoked"
    )


def test_git_branch_and_worktree_helpers_return_real_identity(tmp_path: Path) -> None:
    """Missing deliverable (binding design T28-E): branch
    (`symbolic-ref --short -q HEAD`) and worktree
    (`rev-parse --show-toplevel --git-common-dir`)."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")

    branch = wp.project_git_branch(project_id, data_root=data_root)
    assert branch.get("branch")

    worktree = wp.project_git_worktree(project_id, data_root=data_root)
    assert worktree.get("toplevel")
    assert worktree.get("git_common_dir")


def test_git_dirty_file_diff_returns_bounded_diff_for_a_real_dirty_path(
    tmp_path: Path,
) -> None:
    """Missing deliverable: dirty-file diff
    (`git diff --no-color --no-ext-diff --no-textconv -- <validated dirty path>`),
    validated against the actual dirty-file listing."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")
    (root / "a.txt").write_text("one\ntwo\n", encoding="utf-8")

    diff = wp.project_git_dirty_diff(project_id, "a.txt", data_root=data_root)
    assert "+two" in "\n".join(diff.get("lines") or [])


def test_git_dirty_file_diff_rejects_a_path_not_actually_dirty(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    _commit(root, "a.txt", "one\n", "first")

    diff = wp.project_git_dirty_diff(
        project_id, "not-a-real-file.txt", data_root=data_root
    )
    assert diff.get("error") == "not_dirty"


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------


def _artifact_project(tmp_path: Path) -> tuple[str, Path, Path, dict[str, Any]]:
    project_id, root, data_root = _project(tmp_path, "proj")
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="report.txt",
        data=b"hello artifact bytes",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["report.txt"]},
                "artifact_snapshots": {"report.txt": snapshot},
            }
        ],
    )
    return project_id, root, data_root, snapshot


def test_read_project_artifact_page_returns_exact_bytes(tmp_path: Path) -> None:
    project_id, _root, data_root, snapshot = _artifact_project(tmp_path)
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    content = base64.b64decode(page["content_base64"])
    assert content == b"hello artifact bytes"


def test_read_project_artifact_page_paginates_multiple_pages_cursor_roundtrip(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    payload = b"A" * 10 + b"B" * 10
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="big.bin",
        data=payload,
        media_type="application/octet-stream",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["big.bin"]},
                "artifact_snapshots": {"big.bin": snapshot},
            }
        ],
    )
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="big.bin",
        sha256=snapshot["sha256"],
    )

    first = wp.read_project_artifact_page(
        project_id, cursor, data_root=data_root, limit=10
    )
    assert base64.b64decode(first["content_base64"]) == b"A" * 10
    assert first.get("next_cursor")

    second = wp.read_project_artifact_page(
        project_id, first["next_cursor"], data_root=data_root, limit=10
    )
    assert base64.b64decode(second["content_base64"]) == b"B" * 10
    assert not second.get("next_cursor")


def test_read_project_artifact_page_unknown_custom_and_binary_types_safe_detail(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    binary_payload = bytes(range(256))
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="trace.custom-future-type",
        data=binary_payload,
        media_type="application/octet-stream",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "unknown-future-category",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["trace.custom-future-type"]},
                "artifact_snapshots": {"trace.custom-future-type": snapshot},
            }
        ],
    )
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="trace.custom-future-type",
        sha256=snapshot["sha256"],
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert "error" not in page
    assert base64.b64decode(page["content_base64"]) == binary_payload


def test_read_project_artifact_page_missing_immutable_snapshot_unavailable_reason(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["never-captured.txt"]},
                "artifact_snapshots": {},
            }
        ],
    )
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="never-captured.txt",
        sha256="0" * 64,
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert page.get("error") == "immutable_content_unavailable"


def test_read_project_artifact_page_invalid_cursor_rejected(tmp_path: Path) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)

    page = wp.read_project_artifact_page(
        project_id, "not-a-valid-cursor!!", data_root=data_root
    )
    assert page.get("error") == "invalid_cursor"


def test_read_project_artifact_page_foreign_run_cursor_rejected(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root, snapshot = _artifact_project(tmp_path)
    cursor = _cursor(
        project_id=project_id,
        run_id="run-does-not-exist",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert page.get("error") in {"invalid_cursor", "not_found"}


def test_read_project_artifact_page_deleted_live_file_serves_captured_snapshot(
    tmp_path: Path,
) -> None:
    project_id, root, data_root, snapshot = _artifact_project(tmp_path)
    live = root / "report.txt"
    if live.exists():
        live.unlink()

    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )
    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert base64.b64decode(page["content_base64"]) == b"hello artifact bytes"


def test_read_project_artifact_page_changed_live_file_keeps_original_bytes(
    tmp_path: Path,
) -> None:
    project_id, root, data_root, snapshot = _artifact_project(tmp_path)
    (root / "report.txt").write_text("mutated after capture", encoding="utf-8")

    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )
    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert base64.b64decode(page["content_base64"]) == b"hello artifact bytes"


def test_read_project_artifact_page_symlinked_declared_path_refused(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret outside root", encoding="utf-8")
    digest_dir = (
        root
        / ".rush"
        / "runs"
        / "run-a"
        / "attempts"
        / "run-a-attempt-1"
        / "artifacts"
        / "evil"
    )
    digest_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = digest_dir / "0.bin"
    symlink_path.symlink_to(outside)
    # Arrange assertion: PhysicalRoot really refuses this symlink today.
    from rush.io.physical_paths import PhysicalRoot

    with pytest.raises(ContainmentError):
        PhysicalRoot(root).open_contained(
            symlink_path.relative_to(root), purpose="read"
        )

    snapshot = {
        "immutable_path": str(symlink_path.relative_to(root)),
        "size": len(b"secret outside root"),
        "sha256": "0" * 64,
        "media_type": "text/plain",
    }
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["escape.txt"]},
                "artifact_snapshots": {"escape.txt": snapshot},
            }
        ],
    )
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="escape.txt",
        sha256=snapshot["sha256"],
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert page.get("error") in {"invalid_path", "not_found"}


def test_read_project_artifact_page_hostile_control_bytes_preserved_exactly(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    hostile = b"before\x1b[2Jafter\x1b]0;pwned\x07end"
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="hostile.txt",
        data=hostile,
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["hostile.txt"]},
                "artifact_snapshots": {"hostile.txt": snapshot},
            }
        ],
    )
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="hostile.txt",
        sha256=snapshot["sha256"],
    )

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert base64.b64decode(page["content_base64"]) == hostile


def test_read_project_artifact_page_reaches_non_latest_attempt(
    tmp_path: Path,
) -> None:
    """T28-E design: "Index every attempt of every run, not only the latest" --
    a superseded (generation 1) attempt's own captured artifact must stay
    reachable even after a later (generation 2) attempt of the same run_id."""
    project_id, root, data_root = _project(tmp_path, "proj")
    old_snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="old.txt",
        data=b"generation one bytes",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["old.txt"]},
                "artifact_snapshots": {"old.txt": old_snapshot},
            }
        ],
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-2",
        generation=2,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": []},
                "artifact_snapshots": {},
            }
        ],
    )
    # Arrange assertion: the latest-only reader really only sees generation 2.
    assert wp._iter_run_manifests(root)[0]["attempt_id"] == "run-a-attempt-2"

    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="old.txt",
        sha256=old_snapshot["sha256"],
    )
    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert base64.b64decode(page["content_base64"]) == b"generation one bytes"


def test_export_project_artifact_writes_exact_bytes_when_granted(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)
    destination = tmp_path / "exported.txt"

    result = wp.export_project_artifact(
        project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        destination=destination,
        permissions=ExecutionPermissions(artifact_write=True),
        data_root=data_root,
    )

    assert destination.read_bytes() == b"hello artifact bytes"
    assert result.get("path") == str(destination)
    assert result.get("size") == len(b"hello artifact bytes")
    assert not list(tmp_path.glob("*.partial"))


def test_export_project_artifact_denied_without_permission_writes_nothing(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)
    destination = tmp_path / "should-not-exist.txt"

    with pytest.raises(PermissionError):
        wp.export_project_artifact(
            project_id,
            run_id="run-a",
            attempt_id="run-a-attempt-1",
            tool_id="tool-a",
            path="report.txt",
            destination=destination,
            permissions=ExecutionPermissions(artifact_write=False),
            data_root=data_root,
        )

    assert not destination.exists()


def test_export_project_artifact_existing_identical_destination_is_noop(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)
    destination = tmp_path / "already-there.txt"
    destination.write_bytes(b"hello artifact bytes")
    existing_mtime = destination.stat().st_mtime_ns

    result = wp.export_project_artifact(
        project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        destination=destination,
        permissions=ExecutionPermissions(artifact_write=True),
        data_root=data_root,
    )

    assert result.get("noop") is True
    assert destination.stat().st_mtime_ns == existing_mtime


def test_export_project_artifact_existing_different_destination_is_conflict(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)
    destination = tmp_path / "already-there.txt"
    destination.write_bytes(b"a completely different file")

    with pytest.raises(FileExistsError):
        wp.export_project_artifact(
            project_id,
            run_id="run-a",
            attempt_id="run-a-attempt-1",
            tool_id="tool-a",
            path="report.txt",
            destination=destination,
            permissions=ExecutionPermissions(artifact_write=True),
            data_root=data_root,
        )

    assert destination.read_bytes() == b"a completely different file"


def test_export_project_artifact_interrupted_write_removes_only_its_own_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _root, data_root, _snapshot = _artifact_project(tmp_path)
    destination = tmp_path / "interrupted.txt"
    other_partial = tmp_path / "unrelated.txt.partial"
    other_partial.write_bytes(b"a different in-flight export, must survive")

    original_replace = os.replace

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated interruption before os.replace")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        wp.export_project_artifact(
            project_id,
            run_id="run-a",
            attempt_id="run-a-attempt-1",
            tool_id="tool-a",
            path="report.txt",
            destination=destination,
            permissions=ExecutionPermissions(artifact_write=True),
            data_root=data_root,
        )

    monkeypatch.setattr(os, "replace", original_replace)
    assert not destination.exists()
    assert not list(tmp_path.glob("interrupted.txt*.partial"))
    assert other_partial.exists(), (
        "a failed export must remove only its own .partial file"
    )


def test_read_and_export_artifact_never_spawn_a_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _root, data_root, snapshot = _artifact_project(tmp_path)
    cursor = _cursor(
        project_id=project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        sha256=snapshot["sha256"],
    )
    _spawn_guard(monkeypatch)

    page = wp.read_project_artifact_page(project_id, cursor, data_root=data_root)
    assert base64.b64decode(page["content_base64"]) == b"hello artifact bytes"

    destination = tmp_path / "no-spawn.txt"
    wp.export_project_artifact(
        project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="tool-a",
        path="report.txt",
        destination=destination,
        permissions=ExecutionPermissions(artifact_write=True),
        data_root=data_root,
    )
    assert destination.read_bytes() == b"hello artifact bytes"


# --------------------------------------------------------------------------
# HTTP adapter (dashboard/server.py) delegates to the shared reader
# --------------------------------------------------------------------------


def test_http_artifact_route_delegates_to_read_project_artifact_page_and_keeps_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 4: `dashboard/server.py`'s artifact page
    route must call the shared `read_project_artifact_page` (spy), not keep
    its own independent read path, and must keep offset semantics."""
    _project_id, root, _data_root, _snapshot = _artifact_project(tmp_path)
    entry = {"run_id": "run-a", "attempt_id": "run-a-attempt-1", "tool_id": "tool-a"}

    calls: list[Any] = []

    def _spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        return {"path": "report.txt", "offset": kwargs.get("offset", 0)}

    monkeypatch.setattr(wp, "read_project_artifact_page", _spy, raising=False)

    result = dashboard_server._read_artifact_content_page(
        root, entry, "report.txt", offset=5, limit=10
    )

    assert calls, (
        "dashboard/server.py::_read_artifact_content_page must delegate to "
        "workflows/projects.py::read_project_artifact_page, not keep its own "
        "independent artifact-reading path"
    )
    assert result.get("offset") == 5


# --------------------------------------------------------------------------
# TUI sections (Tokens, Git, Artifacts) via _dispatch_key + render_app
# --------------------------------------------------------------------------


def test_tui_state_lacks_section_and_views_fields(tmp_path: Path) -> None:
    """The shared design's per-section state model
    (`TuiState.section ∈ {overview,map,scans,memory,tokens,git,artifacts,setup}`,
    `TuiState.views: dict[(project_key,section), SectionView]`) is required to
    reach Tokens/Git/Artifacts as first-class sections at all. Neither field
    exists on `TuiState` in this worktree yet."""
    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=tmp_path)]
    )
    _require_state_field(
        state, "section", why="binding design shared state model, section enum"
    )
    _require_state_field(
        state, "views", why="binding design shared state model, per-section SectionView"
    )


def test_tui_f3_digit_or_alias_reaches_tokens_git_artifacts_sections(
    tmp_path: Path,
) -> None:
    """Coordinator follow-up case 5: via `_dispatch_key` + `render_app`,
    reach Tokens, Git, and Artifacts through F3 plus a digit (or the `m`/`G`
    aliases), and each landing renders that section's real data -- not just
    a state-field flip that any empty stub would satisfy."""
    project_id, root, data_root = _full_project(tmp_path)
    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions())

    _require_state_field(
        state, "section", why="F3+digit/alias section navigation needs it"
    )
    _require_state_field(
        state, "overlay", why="F3 must open the 'sections' chooser overlay"
    )

    tui_mod._dispatch_key(state, "f3", actions)
    assert state.overlay == "sections", (
        f"F3 must open the section chooser overlay; got {state.overlay!r}"
    )
    tui_mod._dispatch_key(state, "5", actions)
    assert state.overlay is None, "selecting a section must close the chooser"
    assert state.section == "tokens"
    _settle(state, actions, "tokens")
    rendered = _render_text(state)
    assert "1200" in rendered or "1,200" in rendered, (
        f"Tokens section must render real actual-usage data; got: {rendered!r}"
    )

    tui_mod._dispatch_key(state, "G", actions)
    assert state.section == "git", "the 'G' alias must jump directly to Git"
    _settle(state, actions, "git")
    rendered = _render_text(state)
    assert "first" in rendered, (
        f"Git section must render this repo's real commit history; got: {rendered!r}"
    )

    tui_mod._dispatch_key(state, "f3", actions)
    tui_mod._dispatch_key(state, "7", actions)
    assert state.section == "artifacts"
    rendered = _render_text(state)
    assert "report.txt" in rendered, (
        f"Artifacts section must render the real captured artifact index; "
        f"got: {rendered!r}"
    )

    tui_mod._dispatch_key(state, "m", actions)
    assert state.section == "tokens", "the 'm' alias must jump directly to Tokens"


def test_tui_artifacts_section_inspects_via_bounded_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 5: inspect an artifact through bounded
    continuation -- `read_project_artifact_page` is called with successive
    `next_cursor`s until exhausted, and the rendered text contains every
    page's content, not just the first."""
    project_id, root, data_root = _project(tmp_path, "proj")
    payload = b"A" * 10 + b"B" * 10
    snapshot = _snapshot_artifact(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="tool-a",
        rel_path="big.bin",
        data=payload,
        media_type="application/octet-stream",
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-a",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": ["big.bin"]},
                "artifact_snapshots": {"big.bin": snapshot},
            }
        ],
    )

    calls: list[Any] = []
    original = wp.read_project_artifact_page

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(wp, "read_project_artifact_page", _counting, raising=False)
    # Two 10-byte pages, so the 20-byte artifact needs a real continuation.
    monkeypatch.setattr(tui_mod, "_ARTIFACT_PAGE_BYTES", 10)

    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions())
    _require_state_field(
        state,
        "views",
        why="the Artifacts section's bounded-continuation cursor is stored "
        "per (project_key, section) in TuiState.views",
    )

    tui_mod._dispatch_key(state, "f3", actions)
    tui_mod._dispatch_key(state, "7", actions)
    assert state.section == "artifacts"

    inspect = _find_action("artifacts", "inspect")
    for _ in range(4):
        inspect.run(state, actions)

    assert len(calls) >= 2, (
        "bounded continuation must call read_project_artifact_page more than "
        f"once across pages; got {len(calls)} calls"
    )
    cursors = [
        kwargs.get("cursor") or (args[1] if len(args) > 1 else None)
        for args, kwargs in calls
    ]
    assert cursors[0] != cursors[-1], (
        "successive inspect calls must advance the cursor, not repeat the same page"
    )
    rendered = _render_text(state)
    assert "A" * 10 in rendered, f"first page content missing from render: {rendered!r}"
    assert "B" * 10 in rendered, (
        f"second page content missing from render: {rendered!r}"
    )


def test_tui_export_review_writes_only_after_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 5: starting an export shows a review
    listing `artifact_write` and the destination; approval calls
    `export_project_artifact` exactly once with the reviewed grants and
    writes the file -- never before approval."""
    project_id, root, data_root, _snapshot = _artifact_project(tmp_path)
    calls: list[Any] = []
    original = wp.export_project_artifact

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(wp, "export_project_artifact", _counting, raising=False)

    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions(artifact_write=True))
    _require_state_field(
        state, "overlay", why="the export review is shown via the overlay field"
    )

    tui_mod._dispatch_key(state, "f3", actions)
    tui_mod._dispatch_key(state, "7", actions)
    export_action = _find_action("artifacts", "export")
    export_action.run(state, actions)

    assert state.overlay == "grant_review", (
        f"starting an export must open the grant_review overlay; got {state.overlay!r}"
    )
    grant_text = json.dumps(state.pending_grant, default=str)
    assert "artifact_write" in grant_text, (
        f"the review must list artifact_write; got {grant_text!r}"
    )
    assert "destination" in grant_text or "path" in grant_text, (
        f"the review must list the destination; got {grant_text!r}"
    )
    assert len(calls) == 0, "must not export before approval"

    tui_mod._dispatch_key(state, "y", actions)

    assert len(calls) == 1, (
        f"approval must call export_project_artifact exactly once; got {len(calls)}"
    )
    _call_args, call_kwargs = calls[0]
    assert call_kwargs.get("permissions") is not None
    assert call_kwargs["permissions"].artifact_write is True
    destination = Path(call_kwargs["destination"])
    assert destination.exists()
    assert destination.read_bytes() == b"hello artifact bytes"


def test_tui_export_review_declined_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coordinator follow-up case 5: a declined export review calls
    `export_project_artifact` zero times and writes nothing."""
    project_id, root, data_root, _snapshot = _artifact_project(tmp_path)
    calls: list[Any] = []
    original = wp.export_project_artifact

    def _counting(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(wp, "export_project_artifact", _counting, raising=False)

    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions(artifact_write=True))
    _require_state_field(
        state, "overlay", why="the export review is shown via the overlay field"
    )

    tui_mod._dispatch_key(state, "f3", actions)
    tui_mod._dispatch_key(state, "7", actions)
    export_action = _find_action("artifacts", "export")
    export_action.run(state, actions)
    assert state.overlay == "grant_review"

    before_files = sorted(p for p in tmp_path.rglob("*") if p.is_file())
    tui_mod._dispatch_key(state, "n", actions)
    after_files = sorted(p for p in tmp_path.rglob("*") if p.is_file())

    assert len(calls) == 0, (
        "declining the review must never call export_project_artifact"
    )
    assert after_files == before_files, "declining the review must write nothing"


def test_tui_hostile_text_rendered_safely_in_tokens_git_artifacts_sections(
    tmp_path: Path,
) -> None:
    """Coordinator follow-up case 5: hostile text (raw escape sequences,
    Rich markup-looking text) must render safely -- no raw ESC byte reaches
    the terminal, and markup-looking text (`[/bad]`) shows up literally
    (never raises `MarkupError`, never silently vanishes) -- in each of the
    three sections."""
    project_id, root, data_root = _project(tmp_path, "proj", init_git=True)
    hostile = "\x1b[2Jpwned[/bad]"
    _commit(root, "a.txt", "one\n", "first")
    _commit(root, "b.txt", "two\n", hostile)

    _write_attempt(
        root,
        run_id="run-tokens",
        attempt_id="run-tokens-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": hostile,
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "metrics": {"total_tokens": 1}},
            }
        ],
    )
    snapshot = _snapshot_artifact(
        root,
        run_id="run-artifacts",
        attempt_id="run-artifacts-attempt-1",
        candidate_id="tool-hostile",
        rel_path=hostile,
        data=hostile.encode("utf-8"),
    )
    _write_attempt(
        root,
        run_id="run-artifacts",
        attempt_id="run-artifacts-attempt-1",
        generation=1,
        project_id=project_id,
        scheduled=[
            {
                "candidate_id": "tool-hostile",
                "category": "lint",
                "outcome": "executed",
                "child": {"status": "ok", "artifacts": [hostile]},
                "artifact_snapshots": {hostile: snapshot},
            }
        ],
    )

    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions())
    _require_state_field(state, "section", why="reaching each section needs it")

    for digit, section in (("5", "tokens"), ("6", "git"), ("7", "artifacts")):
        tui_mod._dispatch_key(state, "f3", actions)
        tui_mod._dispatch_key(state, digit, actions)
        assert state.section == section
        _settle(state, actions, section)
        rendered = _render_text(state)
        assert "\x1b" not in rendered, (
            f"{section} section rendered a raw ESC byte: {rendered!r}"
        )
        assert "[/bad]" in rendered, (
            f"{section} section must show markup-looking hostile text "
            f"literally, not swallow/crash on it: {rendered!r}"
        )


def test_render_never_calls_token_or_git_readers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan line 431: no synchronous token/Git work on the render or input
    path. Every token and Git reader raises when called on the thread that
    dispatches keys and renders; a key only records the request, a render
    only reads the loaded state and shows "loading" until the loop drains
    the result, and the loop's worker does the reads."""
    project_id, root, data_root = _full_project(tmp_path)
    (root / "a.txt").write_text("two\n", encoding="utf-8")
    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="proj", root=root, project_id=project_id)],
        data_root=data_root,
    )
    render_thread = threading.get_ident()

    def _guard(name: str, reader: Any) -> Any:
        def _off_render_thread(*args: Any, **kwargs: Any) -> Any:
            if threading.get_ident() == render_thread:
                raise AssertionError(f"{name} called on the render thread")
            return reader(*args, **kwargs)

        return _off_render_thread

    hold = threading.Event()  # set once the Git steps are done
    started = threading.Event()
    release = threading.Event()
    usage = wp.project_token_usage

    def _held_usage(*args: Any, **kwargs: Any) -> Any:
        if hold.is_set():  # the Git snapshot also reads token usage
            started.set()
            release.wait(2.0)
        return usage(*args, **kwargs)

    monkeypatch.setattr(
        wp, "project_token_usage", _guard("project_token_usage", _held_usage)
    )
    for name in (
        "project_git_history",
        "project_git_commit_diff",
        "project_git_dirty_diff",
        "project_git_branch",
        "project_git_worktree",
    ):
        monkeypatch.setattr(wp, name, _guard(name, getattr(wp, name)))
    base = tui_mod.default_scan_actions(ExecutionPermissions())
    actions = dataclasses.replace(
        base, git_snapshot=_guard("git_snapshot", base.git_snapshot)
    )

    # Git: entering, Enter (commit diff) and `d` (dirty diff) only record
    # the request; the render in between shows "loading".
    tui_mod._enter_section(state, "git", actions)
    rendered = _render_text(state)
    assert "loading" in rendered, rendered
    _settle(state, actions, "git")
    rendered = _render_text(state)
    assert "first" in rendered and "failed:" not in rendered, rendered
    assert "worktree=" in rendered, "branch/worktree load on the worker too"

    tui_mod._dispatch_key(state, "enter", actions)
    assert "loading" in _render_text(state)
    _settle(state, actions, "git")
    assert state.git_message == "", state.git_message
    assert state.git_expanded is not None and "+one" in state.git_expanded["lines"]

    tui_mod._dispatch_key(state, "d", actions)
    assert "loading" in _render_text(state)
    _settle(state, actions, "git")
    assert state.git_message == "", state.git_message
    assert state.git_expanded is not None and "+two" in state.git_expanded["lines"]

    tui_mod._dispatch_key(state, "f5", actions)
    _settle(state, actions, "git")
    assert "first" in _render_text(state)

    # Tokens.
    hold.set()
    tui_mod._enter_section(state, "tokens", actions)
    rendered = _render_text(state)
    assert not started.wait(0.1), "rendering Tokens started a token read"
    tui_mod._pump(state, actions)  # the loop tick starts the read
    assert started.wait(2.0), "the loop tick must start the Tokens read"
    rendered = _render_text(state)
    assert "loading" in rendered, rendered
    release.set()
    _settle(state, actions, "tokens")
    rendered = _render_text(state)
    assert "1200" in rendered or "1,200" in rendered, rendered


def test_git_result_for_a_switched_away_project_is_discarded(
    tmp_path: Path,
) -> None:
    """A Git load still running for project A when the user switches to B
    is discarded; only B's history is ever shown."""
    data_root = _data_root(tmp_path)
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    _init_repo(root_a)
    _commit(root_a, "a.txt", "a\n", "commit in A")
    _init_repo(root_b)
    _commit(root_b, "b.txt", "b\n", "commit in B")
    id_a = wp.register_project(root_a, data_root=data_root).project_id
    id_b = wp.register_project(root_b, data_root=data_root).project_id
    base = tui_mod.default_scan_actions(ExecutionPermissions())
    assert base.git_snapshot is not None
    snapshot = base.git_snapshot
    release = threading.Event()

    def _held(root: Path, **kwargs: Any) -> Any:
        if Path(root) == root_a:
            release.wait(2.0)
        return snapshot(root, **kwargs)

    actions = dataclasses.replace(base, git_snapshot=_held)
    state = tui_mod.TuiState(
        projects=[
            tui_mod.ProjectState(name="a", root=root_a, project_id=id_a),
            tui_mod.ProjectState(name="b", root=root_b, project_id=id_b),
        ],
        data_root=data_root,
    )
    tui_mod._enter_section(state, "git", actions)
    for key in ("f2", "down", "enter"):
        tui_mod._dispatch_key(state, key, actions)
    assert state.active_project.name == "b"
    tui_mod._enter_section(state, "git", actions)
    _settle(state, actions, "git")
    release.set()
    time.sleep(0.2)
    for _ in range(5):
        tui_mod._pump(state, actions)
    subjects = {c["subject"] for c in state.git_data["git"]["history"]}
    assert subjects == {"commit in B"}, subjects


def test_git_page_result_is_discarded_after_returning_to_page_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`]` then `[` before the older page arrives: the late page-two result
    is stale and never replaces page one."""
    project_id, root, data_root = _project(tmp_path, "paged", init_git=True)
    for index in range(tui_mod.PAGE_SIZE + 1):
        _commit(root, f"f{index}.txt", f"{index}\n", f"commit {index:02d}")
    history = wp.project_git_history
    release = threading.Event()

    def _held(*args: Any, **kwargs: Any) -> Any:
        release.wait(2.0)
        return history(*args, **kwargs)

    monkeypatch.setattr(wp, "project_git_history", _held)
    state = tui_mod.TuiState(
        projects=[tui_mod.ProjectState(name="p", root=root, project_id=project_id)],
        data_root=data_root,
    )
    actions = tui_mod.default_scan_actions(ExecutionPermissions())
    tui_mod._enter_section(state, "git", actions)
    _settle(state, actions, "git")
    tui_mod._dispatch_key(state, "]", actions)
    tui_mod._dispatch_key(state, "[", actions)
    release.set()
    time.sleep(0.2)
    for _ in range(5):
        tui_mod._pump(state, actions)
    assert state.git_page is None, state.git_page
    rendered = _render_text(state)
    assert "commit 20" in rendered and "commit 00" not in rendered, rendered
