"""Phase 70 T28-E/T28-F plan-named acceptance (part 2, tests only).

Plan: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` lines
427 (T28-E RED -> GREEN) and 429-432 (T28-F). Design gate:
`.scratch/phase-70-design-gate/W4-T23-T29.md` "### T28-F".

Written here for the orchestrator to move into
`tests/test_phase70_tui_usability.py`; every helper is local to this file.

Keys these journeys drive (the TUI contract they pin):

- Sections: F3 then a digit (5 Tokens, 6 Git, 7 Artifacts).
- Tokens: `/` opens the run filter entry, printable keys type the run id,
  Enter commits it as the view's `run_id` filter (a stored identity),
  Escape clears it.
- Git: `j`/`k` move the commit selection, `]`/`[` show the next/previous
  history page, Enter expands the selected commit's changed files and its
  bounded diff (`project_git_commit_diff`; a `more` marker when truncated),
  `d` expands the listed dirty file's bounded diff (`project_git_dirty_diff`).
- Artifacts: `/` opens search, printable keys type the query, Enter filters
  the captured index by path/type, Escape clears it; `j`/`k` select, `i`
  inspects by bounded continuation, `e` opens the export review, `y`/`n`
  approve/decline it.

Every journey drives real keys through `tui._dispatch_key` and reads the
result through `tui.render_app`, over projects registered under `tmp_path`
with an explicit `data_root` passed to `TuiState`. PTY journeys run the real
`run_interactive_tui` in a child started by `subprocess.Popen` on a
`pty.openpty` slave (never `os.fork`/`pty.fork`), the child claiming the slave
as its controlling terminal with TIOCSCTTY.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import itertools
import json
import os
import pty
import re
import select
import signal
import sqlite3
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from rush import tui
from rush.permissions import ExecutionPermissions
from rush.token_economy.telemetry import TelemetryStore
from rush.workflows import projects as wp

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent / "src"
_HOSTILE = "\x1b[2Jpwned[/bad]"
_ANSI_COLOR_SGR = re.compile(rb"\x1b\[[0-9;]*(?:3[0-8]|4[0-8]|9[0-7])(?:;[0-9]+)*m")

# --------------------------------------------------------------------------
# Local helpers
# --------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-02T03:04:05+00:00",
        "GIT_COMMITTER_DATE": "2026-01-02T03:04:05+00:00",
    }
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test Author",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def _commit(root: Path, rel_path: str, content: str, message: str) -> str:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(root, "add", rel_path)
    _git(root, "commit", "--quiet", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _register(
    tmp_path: Path, name: str, data_root: Path, *, init_git: bool = False
) -> tuple[str, Path]:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    if init_git:
        _git(root, "init", "--quiet")
    record = wp.register_project(root, data_root=data_root)
    return record.project_id, root


def _write_attempt(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
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
    (attempt_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (attempt_dir / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "attempt_id": attempt_id,
                "plan_id": f"plan-{run_id}",
                "project_id": project_id,
                "started_at": "2026-01-01T00:00:00+00:00",
                "attempt_generation": 1,
            }
        ),
        encoding="utf-8",
    )


def _snapshot(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    candidate_id: str,
    data: bytes,
    media_type: str = "text/plain",
) -> dict[str, Any]:
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:24]
    immutable_rel = (
        f".rush/runs/{run_id}/attempts/{attempt_id}/artifacts/{digest}/0.bin"
    )
    immutable = root / immutable_rel
    immutable.parent.mkdir(parents=True, exist_ok=True)
    immutable.write_bytes(data)
    return {
        "immutable_path": immutable_rel,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": media_type,
    }


def _captured_item(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    candidate_id: str,
    rel_path: str,
    data: bytes,
    category: str = "lint",
    media_type: str = "text/plain",
    total_tokens: int | None = None,
) -> dict[str, Any]:
    child: dict[str, Any] = {"status": "ok", "artifacts": [rel_path]}
    if total_tokens is not None:
        child["metrics"] = {"total_tokens": total_tokens}
    return {
        "candidate_id": candidate_id,
        "category": category,
        "outcome": "executed",
        "child": child,
        "artifact_snapshots": {
            rel_path: _snapshot(
                root,
                run_id=run_id,
                attempt_id=attempt_id,
                candidate_id=candidate_id,
                data=data,
                media_type=media_type,
            )
        },
    }


def _cursor(**payload: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _state(root: Path, project_id: str, data_root: Path) -> tui.TuiState:
    state = tui.TuiState(
        projects=[tui.ProjectState(name=root.name, root=root, project_id=project_id)],
        data_root=data_root,
    )
    # Narrow branch: the section body gets the whole width, so no pane split
    # crops a row the assertions look for.
    state.terminal_size = (79, 60)
    return state


def _render(state: tui.TuiState) -> str:
    console = Console(record=True, width=220, height=400, no_color=True)
    console.print(tui.render_app(state))
    return console.export_text()


def _keys(state: tui.TuiState, actions: tui.ScanActions, *keys: str) -> None:
    for key in keys:
        tui._dispatch_key(state, key, actions)


def _type(state: tui.TuiState, actions: tui.ScanActions, text: str) -> None:
    _keys(state, actions, *list(text))


def _section(state: tui.TuiState, actions: tui.ScanActions, digit: str) -> None:
    _keys(state, actions, "f3", digit)
    assert state.overlay is None


def _search_artifacts(state: tui.TuiState, actions: tui.ScanActions, query: str) -> str:
    _keys(state, actions, "/")
    _type(state, actions, query)
    _keys(state, actions, "enter")
    return _render(state)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# T28-E
# --------------------------------------------------------------------------


def _tokens_journey(tmp_path: Path, data_root: Path) -> None:
    project_id, root = _register(tmp_path, "tokens", data_root)
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
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
    handoffs = root / ".rush" / "handoffs"
    handoffs.mkdir(parents=True)
    # Unscoped handoffs (no run identity): counted unfiltered, never assigned
    # to a selected run.
    (handoffs / "handoff-1.json").write_text(
        json.dumps({"handoff_id": "handoff-1", "packet": {"tokens": 500}})
    )
    (handoffs / "handoff-2.json").write_text(
        json.dumps({"handoff_id": "handoff-2", "packet": {"tokens": 300}})
    )
    TelemetryStore(root).record_savings(
        "tool-a", raw_tokens=5000, compressed_tokens=3000
    )
    db = root / ".rush" / "telemetry" / "tokens.db"
    db_hash = _sha(db)

    actions = tui.default_scan_actions(ExecutionPermissions())
    state = _state(root, project_id, data_root)
    _section(state, actions, "5")
    assert state.section == "tokens"
    text = _render(state)
    assert "1500" in text, f"actual 1200+300 must show as 1500: {text}"
    assert "800" in text, f"tokenizer 800 must show separately: {text}"
    assert "2000" in text, f"avoided 2000 must show separately: {text}"
    for blended in ("4300", "3500", "2300", "2800"):
        assert blended not in text, f"actual must never be summed with {blended}"
    assert _sha(db) == db_hash, "rendering Tokens must not write the telemetry DB"

    # Run filter by stored identity: run-a only; run-b (foreign) and the
    # unscoped handoffs are excluded.
    _keys(state, actions, "/")
    _type(state, actions, "run-a")
    _keys(state, actions, "enter")
    view = state.views[(tui.project_key(state.active_project), "tokens")]
    assert view.filters.get("run_id") == "run-a", view.filters
    text = _render(state)
    assert "1200" in text, f"run-a scoped actual must be 1200: {text}"
    assert "1500" not in text, f"run-b must be excluded from run-a: {text}"
    assert "run-a" in text, f"the active run filter must be shown: {text}"
    assert '"total_tokens": 800' not in text, (
        f"unscoped handoffs must never be assigned to run-a: {text}"
    )
    _keys(state, actions, "/", "escape")
    assert not state.views[(tui.project_key(state.active_project), "tokens")].filters

    # Actual unavailable is not zero.
    empty_id, empty_root = _register(tmp_path, "tokens-empty", data_root)
    empty = _state(empty_root, empty_id, data_root)
    _section(empty, actions, "5")
    text = _render(empty)
    assert "no run manifest" in text, f"unavailable actual needs its reason: {text}"
    assert '"total_tokens": 0' not in text.split("tokenizer_counted")[0], (
        f"unavailable actual must never render as a known 0: {text}"
    )
    # Missing DB: reading never creates .rush/telemetry.
    assert not (empty_root / ".rush" / "telemetry").exists()

    # Legacy schema: read, never migrated.
    legacy_id, legacy_root = _register(tmp_path, "tokens-legacy", data_root)
    legacy_db = legacy_root / ".rush" / "telemetry" / "tokens.db"
    legacy_db.parent.mkdir(parents=True)
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            "CREATE TABLE token_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp INTEGER NOT NULL, tool_name TEXT NOT NULL, raw_tokens "
            "INTEGER NOT NULL, compressed_tokens INTEGER NOT NULL, duration_ms "
            "REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO token_events (timestamp, tool_name, raw_tokens, "
            "compressed_tokens, duration_ms) VALUES (1700000000, 'legacy', 5000, "
            "3000, 1.0)"
        )
    conn.close()
    legacy_hash = _sha(legacy_db)
    legacy = _state(legacy_root, legacy_id, data_root)
    _section(legacy, actions, "5")
    _render(legacy)
    assert _sha(legacy_db) == legacy_hash, "a legacy DB must never be migrated"
    with sqlite3.connect(legacy_db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(token_events)")}
    conn.close()
    assert "run_id" not in columns

    # Corrupt DB: unavailable with a reason, file untouched.
    corrupt_id, corrupt_root = _register(tmp_path, "tokens-corrupt", data_root)
    corrupt_db = corrupt_root / ".rush" / "telemetry" / "tokens.db"
    corrupt_db.parent.mkdir(parents=True)
    corrupt_db.write_bytes(b"not a sqlite database at all")
    corrupt = _state(corrupt_root, corrupt_id, data_root)
    _section(corrupt, actions, "5")
    text = _render(corrupt)
    assert "unreadable" in text, f"corrupt telemetry must say unreadable: {text}"
    assert corrupt_db.read_bytes() == b"not a sqlite database at all"


def _git_journey(tmp_path: Path, data_root: Path) -> None:
    project_id, root = _register(tmp_path, "gitproj", data_root, init_git=True)
    _commit(root, "alpha.txt", "one\n", "first")
    for index in range(19):
        subject = _HOSTILE if index == 7 else f"filler {index:02d}"
        _commit(root, f"f{index:02d}.txt", f"filler {index}\n", subject)
    bound = wp._GIT_DIFF_MAX_LINES
    big = "".join(f"line-{n:05d}\n" for n in range(bound + 50))
    _commit(root, "big.txt", big, "second")
    (root / "f05.txt").write_text("dirty change\n", encoding="utf-8")

    actions = tui.default_scan_actions(ExecutionPermissions())
    state = _state(root, project_id, data_root)
    _section(state, actions, "6")
    assert state.section == "git"
    text = _render(state)
    assert "second" in text and "first" not in text, (
        f"page 1 holds the 20 newest commits only: {text}"
    )
    assert "Test Author" in text and "2026-01-02" in text, (
        f"history rows need author and time: {text}"
    )
    assert "f05.txt" in text, f"the dirty file must be listed: {text}"
    assert "\x1b" not in text and "[/bad]" in text, "hostile subject must be literal"
    assert "line-00000" not in text and "+dirty change" not in text

    # Enter on the newest commit: changed files plus the bounded diff.
    _keys(state, actions, "enter")
    text = _render(state)
    assert "big.txt" in text, f"changed files of the selected commit: {text}"
    assert "+line-00000" in text, f"diff of the selected commit: {text}"
    assert f"line-{bound + 40:05d}" not in text, "the diff must stay bounded"
    assert "more" in text, f"a truncated diff must say more remains: {text}"

    # Next page, then expand the oldest commit's exact diff.
    _keys(state, actions, "]")
    text = _render(state)
    assert "first" in text and "second" not in text, f"page 2: {text}"
    _keys(state, actions, "enter")
    text = _render(state)
    assert "alpha.txt" in text and "+one" in text, f"first commit diff: {text}"
    assert "line-00000" not in text, "the previous commit's diff must be replaced"
    _keys(state, actions, "[")
    text = _render(state)
    assert "second" in text and "first" not in text, f"back on page 1: {text}"

    # Dirty file diff.
    _keys(state, actions, "d")
    text = _render(state)
    assert "+dirty change" in text and "-filler 5" in text, f"dirty diff: {text}"

    # No commit/reset/push action exists anywhere.
    for action in tui.ACTIONS:
        for word in ("commit", "reset", "push"):
            assert word not in action.id.lower(), action.id


def _artifacts_journey(
    tmp_path: Path, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, root = _register(tmp_path, "artproj", data_root)
    run, attempt = "run-a", "run-a-attempt-1"
    scheduled = [
        _captured_item(
            root,
            run_id=run,
            attempt_id=attempt,
            candidate_id=f"tool-{n:02d}",
            rel_path=f"report-{n:02d}.txt",
            data=f"captured report {n:02d}\n".encode(),
        )
        for n in range(22)
    ]
    scheduled.append(
        _captured_item(
            root,
            run_id=run,
            attempt_id=attempt,
            candidate_id="tracer",
            rel_path="trace.ctrace",
            data=b"trace-event-1\n",
            category="custom-trace",
            media_type="application/x-custom-trace",
        )
    )
    blob = b"\x00\x01\xffBIN\x00\x1b[2J"
    scheduled.append(
        _captured_item(
            root,
            run_id=run,
            attempt_id=attempt,
            candidate_id="blobber",
            rel_path="blob.bin",
            data=blob,
            category="binary-dump",
            media_type="application/octet-stream",
        )
    )
    scheduled.append(
        _captured_item(
            root,
            run_id=run,
            attempt_id=attempt,
            candidate_id="hostile",
            rel_path=_HOSTILE,
            data=_HOSTILE.encode(),
        )
    )
    _write_attempt(
        root, run_id=run, attempt_id=attempt, project_id=project_id, scheduled=scheduled
    )
    # Live files: report-00 changed after capture, report-01 deleted.
    (root / "report-00.txt").write_text("changed live content\n", encoding="utf-8")
    (root / "report-01.txt").write_text("gone\n", encoding="utf-8")
    (root / "report-01.txt").unlink()
    # report-02's immutable snapshot is missing.
    missing = (
        root / scheduled[2]["artifact_snapshots"]["report-02.txt"]["immutable_path"]
    )
    missing.unlink()

    foreign_id, foreign_root = _register(tmp_path, "foreign", data_root)
    foreign_item = _captured_item(
        foreign_root,
        run_id="run-f",
        attempt_id="run-f-attempt-1",
        candidate_id="tool-f",
        rel_path="secret.txt",
        data=b"FOREIGN SECRET",
    )
    _write_attempt(
        foreign_root,
        run_id="run-f",
        attempt_id="run-f-attempt-1",
        project_id=foreign_id,
        scheduled=[foreign_item],
    )

    actions = tui.default_scan_actions(ExecutionPermissions(artifact_write=True))
    state = _state(root, project_id, data_root)
    _section(state, actions, "7")
    assert state.section == "artifacts"
    key = (tui.project_key(state.active_project), "artifacts")

    # Multiple pages: every captured artifact is reachable.
    text = _render(state)
    assert "Captured (25)" in text and "page 1/2" in text, text
    seen = {n for n in range(22) if f"report-{n:02d}.txt" in text}
    for _ in range(24):
        _keys(state, actions, "j")
    text = _render(state)
    assert "page 2/2" in text, text
    seen |= {n for n in range(22) if f"report-{n:02d}.txt" in text}
    assert seen == set(range(22)), f"unreachable artifacts: {set(range(22)) - seen}"
    assert "\x1b" not in text

    # Search by type: only the unknown custom-trace artifact remains and its
    # generic detail is inspectable.
    text = _search_artifacts(state, actions, "custom-trace")
    assert "Captured (1)" in text and "trace.ctrace" in text, text
    assert "report-03.txt" not in text
    _keys(state, actions, "i")
    text = _render(state)
    assert "trace-event-1" in text and "application/x-custom-trace" in text, text
    _keys(state, actions, "/", "escape")
    assert "Captured (25)" in _render(state)

    # Search by path: deleted and changed live files keep their captured bytes.
    for rel, captured in (
        ("report-00.txt", "captured report 00"),
        ("report-01.txt", "captured report 01"),
    ):
        _search_artifacts(state, actions, rel)
        _keys(state, actions, "i")
        text = _render(state)
        assert captured in text, f"{rel} must show its captured snapshot: {text}"
        assert "changed live content" not in text

    # Missing immutable snapshot: unavailable with recovery guidance.
    _search_artifacts(state, actions, "report-02.txt")
    _keys(state, actions, "i")
    text = _render(state)
    assert "immutable_content_unavailable" in text and "rerun the scan" in text, text
    assert "captured report 02" not in text

    # Invalid cursor and a foreign-run cursor are refused, never read.
    _search_artifacts(state, actions, "report-03.txt")
    _keys(state, actions, "i")
    for bad in (
        "not-a-cursor!!",
        _cursor(
            project_id=project_id,
            run_id="run-does-not-exist",
            attempt_id=attempt,
            tool_id="tool-03",
            path="report-03.txt",
            sha256=scheduled[3]["artifact_snapshots"]["report-03.txt"]["sha256"],
            offset=0,
        ),
        _cursor(
            project_id=foreign_id,
            run_id="run-f",
            attempt_id="run-f-attempt-1",
            tool_id="tool-f",
            path="secret.txt",
            sha256=foreign_item["artifact_snapshots"]["secret.txt"]["sha256"],
            offset=0,
        ),
    ):
        state.views[key].data["_detail"]["next_cursor"] = bad
        _keys(state, actions, "i")
        text = _render(state)
        assert "read failed" in text, f"cursor {bad!r} must be refused: {text}"
        assert "FOREIGN SECRET" not in text

    # Binary: metadata only, then exact exported bytes.
    _search_artifacts(state, actions, "blob.bin")
    _keys(state, actions, "i")
    text = _render(state)
    assert "binary content" in text and "BIN" not in text, text
    assert "\x1b" not in text
    _keys(state, actions, "e")
    assert state.overlay == "grant_review"
    destination = Path(str((state.pending_grant or {})["destination"]))
    _keys(state, actions, "y")
    assert destination.read_bytes() == blob, "export must write the exact bytes"
    assert f"{len(blob)} bytes" in _render(state)

    # Denied (declined) export writes nothing.
    _search_artifacts(state, actions, "report-04.txt")
    _keys(state, actions, "e")
    declined = Path(str((state.pending_grant or {})["destination"]))
    _keys(state, actions, "n")
    assert not declined.exists(), "a declined export must write nothing"

    # Existing different destination is never overwritten.
    _keys(state, actions, "e")
    existing = Path(str((state.pending_grant or {})["destination"]))
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"someone else's file")
    _keys(state, actions, "y")
    assert existing.read_bytes() == b"someone else's file"
    assert "export failed" in _render(state)

    # Interrupted export removes only its own partial file.
    _search_artifacts(state, actions, "report-05.txt")
    _keys(state, actions, "e")
    interrupted = Path(str((state.pending_grant or {})["destination"]))
    other_partial = interrupted.parent / "unrelated.partial"
    other_partial.write_bytes(b"another export in flight")

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated interruption")

    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", _boom)
        _keys(state, actions, "y")
    assert not interrupted.exists()
    assert not list(interrupted.parent.glob(f"{interrupted.name}*partial*"))
    assert other_partial.read_bytes() == b"another export in flight"
    assert "export failed" in _render(state)

    # Hostile path renders literally.
    text = _search_artifacts(state, actions, "pwned")
    assert "[/bad]" in text and "\x1b" not in text, text


@pytest.mark.usefixtures("hermetic_engine_path")
def test_t28e_tokens_git_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan line 427 through the TUI: Tokens (actual/tokenizer/avoided kept
    apart, unavailable actual, run filter, read-only missing/legacy/corrupt
    DB), Git (paged history with author/time, changed files, bounded commit
    and dirty diffs, hostile subject) and Artifacts (pages, unknown and
    binary types, search, exact export, live-file drift, missing snapshot,
    invalid/foreign cursor, existing destination, declined and interrupted
    export, hostile text)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    data_root = tmp_path / "rush-data"
    _tokens_journey(tmp_path, data_root)
    _git_journey(tmp_path, data_root)
    _artifacts_journey(tmp_path, data_root, monkeypatch)


# --------------------------------------------------------------------------
# T28-F: full-surface acceptance (plan line 432; design gate "### T28-F")
# --------------------------------------------------------------------------

_F_SECTIONS = (
    "overview",
    "map",
    "scans",
    "memory",
    "tokens",
    "git",
    "artifacts",
    "setup",
)
_F_STATES = (
    "loading",
    "populated",
    "empty",
    "unavailable",
    "denied",
    "failed",
    "stale",
    "disconnected",
)
# Actions whose `enabled` is gated; the matrix must drive each one disabled.
_F_GATED = {
    "start_check",
    "start_scan",
    "rescan",
    "prepare_handoff",
    "project_add",
    "project_relink",
    "choose_later",
    "cancel_scan",
}


def _f_actions(**overrides: Any) -> tui.ScanActions:
    fields: dict[str, Any] = {
        "plan_scan": lambda *a, **k: None,
        "execute_scan": lambda *a, **k: None,
        "cancel_scan_run": lambda *a, **k: {},
        "rescan_project_run": lambda *a, **k: {},
        "build_handoff": lambda *a, **k: None,
        "dispatch_handoff": lambda *a, **k: None,
        "load_scan_events": lambda *a, **k: {"events": [], "run_state": None},
        "list_agents": list,
    }
    fields.update(overrides)
    return tui.ScanActions(**fields)


def _f_frame(state: tui.TuiState, size: tuple[int, int] = (120, 40)) -> str:
    state.terminal_size = size
    console = Console(
        file=io.StringIO(), width=size[0], height=size[1], color_system=None
    )
    console.print(tui.render_app(state))
    out = console.file
    assert isinstance(out, io.StringIO)
    return out.getvalue()


def _f_matrix_state(
    tmp_path: Path, condition: str
) -> tuple[tui.TuiState, tui.ProjectState]:
    """`idle`: unregistered, no run. `running`: a scan in flight.
    `done`: a completed run of a moved project with no agent chosen."""
    root = tmp_path / f"matrix-{condition}"
    root.mkdir(exist_ok=True)
    project = tui.ProjectState(name=f"m-{condition}", root=root)
    if condition == "idle":
        project.registration = {"state": "none"}
    elif condition == "running":
        project.registration = {"state": "registered"}
        project.status = "scanning"
        project.owner = "dashboard"
        project.run_id = "run-live"
    else:
        project.registration = {"state": "moved"}
        project.status = "complete"
        project.run_id = "run-done"
    state = tui.TuiState(projects=[project], data_root=tmp_path / "rush-data")
    return state, project


def _f_matrix_case(tmp_path: Path) -> None:
    # Vocabulary parity: the registry's sections and states are these eight.
    assert tui.SECTIONS == _F_SECTIONS
    assert tui.SECTION_STATES == _F_STATES

    # ACTIONS <-> _BINDINGS parity.
    ids = [action.id for action in tui.ACTIONS]
    assert len(ids) == len(set(ids)), f"duplicate action ids: {ids}"
    by_id = {action.id: action for action in tui.ACTIONS}
    orphan_bindings = [
        (b.key, b.action_name) for b in tui._BINDINGS if b.action_name not in by_id
    ]
    assert not orphan_bindings, f"bindings naming no action: {orphan_bindings}"
    key_owner: dict[str, str] = {}
    for binding in tui._BINDINGS:
        owner = key_owner.setdefault(binding.key, binding.action_name)
        assert owner == binding.action_name, (
            f"key {binding.key!r} bound to both {owner!r} and "
            f"{binding.action_name!r}: one of them is unreachable"
        )
        assert tui._KEYMAP.get_action_for_key(binding.key) == binding.action_name
    menu_ids = {row[0] for row in (*tui._CHOOSER_EXTRAS, *tui._SELECTOR_EXTRAS)}
    for action in tui.ACTIONS:
        assert action.keys == tuple(
            b.key for b in tui._BINDINGS if b.action_name == action.id
        )
        assert set(action.sections) <= set(_F_SECTIONS), action
        reachable = bool(action.keys) or action.id in menu_ids or bool(action.sections)
        assert reachable, (
            f"action {action.id!r} has no key, no F2/F3 menu row and no "
            "section actions-pane row"
        )
    for menu_id in menu_ids:
        assert menu_id in by_id, f"menu row {menu_id!r} names no action"

    # 8 sections x 8 states x every action, under three project conditions.
    actions = _f_actions()
    disabled_seen: set[str] = set()
    problems: list[str] = []
    for condition in ("idle", "running", "done"):
        for section in _F_SECTIONS:
            for view_state in _F_STATES:
                state, project = _f_matrix_state(tmp_path, condition)
                tui._enter_section(state, section, actions)
                reason = (
                    None
                    if view_state in ("loading", "populated")
                    else f"{view_state}-reason-{section}"
                )
                # Tokens/Artifacts cache their view by a key; seeding that key
                # makes the renderer show this view instead of reloading it.
                cache_key = {
                    "tokens": tui._tokens_cache_key,
                    "artifacts": tui._artifacts_cache_key,
                }.get(section)
                data: dict[str, Any] = {}
                if cache_key is not None:
                    data["_cache_key"] = cache_key(project.root, {})
                state.views[(tui.project_key(project), section)] = tui.SectionView(
                    state=view_state, reason=reason, data=data
                )
                where = f"{condition}/{section}/{view_state}"
                frame = _f_frame(state)
                if tui.SECTION_LABELS[section] not in frame:
                    problems.append(f"{where}: section label not in header")
                if view_state != "populated" and view_state not in frame:
                    problems.append(f"{where}: state label {view_state!r} not shown")
                if reason is not None and reason not in frame:
                    problems.append(f"{where}: state reason not shown")
                for action in tui.ACTIONS:
                    enabled, why = action.enabled(state)
                    if enabled:
                        continue
                    disabled_seen.add(action.id)
                    assert why, f"{where}: disabled {action.id!r} has no reason"
                    state.message = ""
                    tui._run_action(state, action, actions)
                    assert state.message == why, (where, action.id)
                    if why not in _f_frame(state):
                        problems.append(
                            f"{where}: disabled {action.id!r} reason {why!r} "
                            "not rendered"
                        )
                    if section in action.sections:
                        listed = tui._section_actions(section)
                        if listed.index(action) < tui._FOOTER_ACTIONS:
                            footer = tui._keymap_footer(state).plain
                            if f"({why})" not in footer:
                                problems.append(
                                    f"{where}: {action.id!r} footer lacks its reason"
                                )
    assert disabled_seen >= _F_GATED, sorted(_F_GATED - disabled_seen)
    assert not problems, f"{len(problems)} matrix cells fail:\n" + "\n".join(problems)


# The PTY child: the real `run_interactive_tui` on the PTY slave, with fake
# workflow seams. It logs one JSON line per rendered frame (the state that
# frame showed) so the parent can synchronise on real state, not on timing.
_F_CHILD = r"""
import fcntl, json, os, sys, termios, time
from pathlib import Path

# The new session (start_new_session) claims the PTY slave as its controlling
# terminal first thing -- done here, not in a preexec_fn, which is unsafe to
# run in a forked child of a threaded parent.
fcntl.ioctl(0, termios.TIOCSCTTY, 0)

from rush import tui
from rush.dashboard.terminal_input import PosixKeyReader

scenario, log_path, *roots = sys.argv[1:]
log = open(log_path, "a", buffering=1)
calls = {"scan": 0, "check": 0}


def counted(name, value=None):
    def run(*args, **kwargs):
        calls[name] += 1
        return value

    return run


def run_check_suite(root, **kwargs):
    calls["check"] += 1
    cancel = kwargs.get("cancel_check")
    while not (cancel and cancel()):
        time.sleep(0.02)
    return {"tool": "check", "status": "ok", "findings": [],
            "metadata": {"cancelled": True}}


findings = [
    {"tool": "lint", "severity": "warn", "message": f"finding-row-{i}",
     "path": "a.py", "line": i + 1}
    for i in range(6)
]
seeds = [
    tui.ProjectSeed(
        name=f"proj{i}", root=Path(root),
        results=[{"tool": "lint", "status": "warn", "summary": "6 findings",
                  "findings": findings}],
    )
    for i, root in enumerate(roots)
]
actions = tui.ScanActions(
    plan_scan=counted("scan"),
    execute_scan=counted("scan"),
    cancel_scan_run=lambda *a, **k: {},
    rescan_project_run=counted("scan", {}),
    build_handoff=lambda *a, **k: None,
    dispatch_handoff=lambda *a, **k: None,
    load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
    list_agents=list,
    run_check_suite=run_check_suite,
)


def note(state, **extra):
    project = state.projects[state.active_index or 0]
    log.write(json.dumps({
        "size": list(state.terminal_size), "overlay": state.overlay,
        "mode": state.mode, "section": state.section,
        "active": state.active_index, "selected": project.selected_index,
        "filter": project.filter_text, "status": project.status,
        "quit": state.should_quit, "calls": dict(calls),
        "lflag": termios.tcgetattr(0)[3], **extra,
    }) + "\n")


real_render = tui.render_app


def render_and_note(state):
    layout = real_render(state)
    note(state)
    return layout


tui.render_app = render_and_note
reader = None
if os.environ.get("F_KEY_FD"):
    reader = PosixKeyReader(int(os.environ["F_KEY_FD"]))
def modes():
    # PENDIN is a kernel status bit (set on returning to canonical mode with
    # input pending), not a mode the program sets or restores.
    attrs = termios.tcgetattr(0)
    attrs[3] &= ~termios.PENDIN
    return attrs


before = modes()
state = tui.run_interactive_tui(
    seeds, actions=actions, key_reader=reader,
    data_root=Path(os.environ["HOME"]) / "rush-data",
)
after = modes()
note(state, final=True, restored=after == before,
     icanon_before=bool(before[3] & termios.ICANON),
     termios_diff=[[i, repr(before[i]), repr(after[i])]
                   for i in range(len(before)) if before[i] != after[i]])
"""

_F_SGR_OR_CSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")


class _FPtyChild:
    """`run_interactive_tui` in a child on a PTY slave: started with
    `subprocess.Popen` (never `os.fork`) in a new session, the child claiming
    the slave as its controlling terminal via TIOCSCTTY."""

    def __init__(
        self,
        tmp_path: Path,
        scenario: str,
        *,
        extra_env: dict[str, str] | None = None,
        key_pipe: bool = False,
    ) -> None:
        home = tmp_path / f"home-{scenario}"
        home.mkdir()
        roots = [tmp_path / f"{scenario}-a", tmp_path / f"{scenario}-b"]
        for root in roots:
            root.mkdir()
        self.log = tmp_path / f"{scenario}.jsonl"
        self.err = tmp_path / f"{scenario}.err"
        self.out = bytearray()
        self.seen = 0
        self.key_write: int | None = None
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": str(_SRC_DIR),
        }
        env.update(extra_env or {})
        pass_fds: tuple[int, ...] = ()
        key_read: int | None = None
        self.master, slave = pty.openpty()
        try:
            self._set_size(120, 40)
            if key_pipe:
                key_read, self.key_write = os.pipe()
                env["F_KEY_FD"] = str(key_read)
                pass_fds = (key_read,)
            with self.err.open("wb") as err:
                self.proc = subprocess.Popen(
                    [sys.executable, "-c", _F_CHILD, scenario, str(self.log)]
                    + [str(root) for root in roots],
                    stdin=slave,
                    stdout=slave,
                    stderr=err,
                    env=env,
                    cwd=str(tmp_path),
                    start_new_session=True,
                    pass_fds=pass_fds,
                )
        except BaseException:
            os.close(self.master)
            if self.key_write is not None:
                os.close(self.key_write)
            raise
        finally:
            os.close(slave)
            if key_read is not None:
                os.close(key_read)

    def _set_size(self, columns: int, rows: int) -> None:
        fcntl.ioctl(
            self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )

    def resize(self, columns: int, rows: int) -> None:
        self._set_size(columns, rows)
        os.kill(self.proc.pid, signal.SIGWINCH)

    def send(self, data: bytes) -> None:
        os.write(self.master, data)

    def send_key(self, data: bytes) -> None:
        assert self.key_write is not None
        os.write(self.key_write, data)

    def close_keys(self) -> None:
        assert self.key_write is not None
        os.close(self.key_write)
        self.key_write = None

    def drain(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while (left := deadline - time.monotonic()) > 0:
            ready, _, _ = select.select([self.master], [], [], min(left, 0.05))
            if not ready:
                continue
            try:
                chunk = os.read(self.master, 65536)
            except OSError:  # EIO: the child closed the slave (exited)
                return
            if not chunk:
                return
            self.out += chunk

    def entries(self) -> list[dict[str, Any]]:
        if not self.log.exists():
            return []
        lines = self.log.read_text().splitlines()
        return [json.loads(line) for line in lines if line.endswith("}")]

    def wait(self, what: str, pred: Any, timeout: float = 20.0) -> dict[str, Any]:
        """The first frame after the last match that satisfies `pred`."""
        deadline = time.monotonic() + timeout
        while True:
            self.drain(0.05)
            entries = self.entries()
            for index in range(self.seen, len(entries)):
                if pred(entries[index]):
                    self.seen = index + 1
                    return entries[index]
            if self.proc.poll() is not None or time.monotonic() > deadline:
                self.drain(0.2)
                raise AssertionError(
                    f"no frame showed {what}; child rc={self.proc.poll()}, "
                    f"last frames={entries[-3:]}, "
                    f"stderr={self.err.read_bytes()[-2000:]!r}"
                )

    def finish(self, timeout: float = 20.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while self.proc.poll() is None and time.monotonic() < deadline:
            self.drain(0.05)
        self.drain(0.2)
        assert self.proc.poll() == 0, (
            f"child did not exit cleanly: rc={self.proc.poll()}, "
            f"stderr={self.err.read_bytes()[-2000:]!r}"
        )
        final = self.entries()[-1]
        assert final.get("final") is True, final
        return final

    def text(self, start: int = 0) -> str:
        return _F_SGR_OR_CSI.sub(b"", bytes(self.out[start:])).decode(errors="replace")

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.kill()
            self.proc.wait(timeout=10)
        finally:
            os.close(self.master)
            if self.key_write is not None:
                os.close(self.key_write)
                self.key_write = None


def _f_started(entry: dict[str, Any]) -> bool:
    return entry["size"] == [120, 40] and entry["section"] == "overview"


def _f_pty_ss3_case(tmp_path: Path) -> None:
    """SS3 F2 (`ESC O Q`) switches project, SS3 F3 (`ESC O R`) section."""
    child = _FPtyChild(tmp_path, "ss3")
    try:
        child.wait("launch", _f_started)
        child.send(b"\x1bOQ")
        child.wait("F2 project selector", lambda e: e["mode"] == "project_selector")
        child.send(b"j")
        child.drain(0.3)
        child.send(b"\r")
        child.wait(
            "project 2 active", lambda e: e["active"] == 1 and e["mode"] == "list"
        )
        child.send(b"\x1bOR")
        child.wait("F3 section chooser", lambda e: e["overlay"] == "sections")
        child.send(b"3")
        child.wait(
            "Scans section", lambda e: e["section"] == "scans" and e["overlay"] is None
        )
        child.send(b"q")
        final = child.finish()
        assert final["active"] == 1 and final["section"] == "scans", final
        assert final["restored"] is True, final
    finally:
        child.close()


def _f_pty_paste_case(tmp_path: Path) -> None:
    """A bracketed paste of `sq ESC[2J` into search is literal text: no
    scan, no quit, no clear screen."""
    child = _FPtyChild(tmp_path, "paste")
    try:
        child.wait("launch", _f_started)
        child.send(b"/")
        child.wait("search mode", lambda e: e["mode"] == "search")
        mark = len(child.out)
        child.send(b"\x1b[200~sq\x1b[2J\x1b[201~")
        child.wait("pasted filter", lambda e: e["filter"] == "sq\x1b[2J")
        child.drain(0.6)
        last = child.entries()[-1]
        assert last["mode"] == "search" and last["quit"] is False, last
        assert last["calls"] == {"scan": 0, "check": 0}, last
        assert last["status"] == "idle", last
        pasted_output = bytes(child.out[mark:])
        assert b"\x1b[2J" not in pasted_output, (
            "the pasted ESC[2J reached the terminal as a control sequence"
        )
        assert "sq" in child.text(mark), "the pasted text is not shown literally"
        child.send(b"\x1b")
        child.wait("search closed", lambda e: e["mode"] == "list")
        child.send(b"q")
        final = child.finish()
        assert final["calls"] == {"scan": 0, "check": 0}, final
    finally:
        child.close()


def _f_pty_sigint_case(tmp_path: Path) -> None:
    """Ctrl-C (a real SIGINT from the PTY line discipline) with running work
    opens the quit choice: Detach, Cancel and stay, Return."""
    child = _FPtyChild(tmp_path, "sigint")
    try:
        child.wait("launch", _f_started)
        child.send(b"C")
        child.wait("running check", lambda e: e["status"] == "scanning")
        mark = len(child.out)
        child.send(b"\x03")
        choice = child.wait("quit choice", lambda e: e["mode"] == "quit_confirm")
        assert choice["quit"] is False and choice["status"] == "scanning", choice
        child.drain(0.3)
        shown = child.text(mark)
        for label in ("Detach", "Cancel run, stay open", "Return, keep observing"):
            assert label in shown, f"quit choice {label!r} not shown"
        child.send(b"r")
        back = child.wait("returned", lambda e: e["mode"] == "list")
        assert back["status"] == "scanning" and back["quit"] is False, back
        child.send(b"\x03")
        child.wait("quit choice again", lambda e: e["mode"] == "quit_confirm")
        child.send(b"d")
        final = child.finish()
        assert final["quit"] is True and final["status"] == "cancelled", final
        assert final["restored"] is True, final
    finally:
        child.close()


def _f_pty_eof_case(tmp_path: Path) -> None:
    """Input EOF with running work Detaches and restores termios. Keys come
    through a pipe read by the real `PosixKeyReader` (a hung-up PTY cannot
    report its restored termios), while `raw_terminal` puts the PTY itself
    into cbreak mode and must restore it."""
    child = _FPtyChild(tmp_path, "eof", key_pipe=True)
    try:
        started = child.wait("launch", _f_started)
        assert not started["lflag"] & termios.ICANON, "PTY was never put in cbreak"
        child.send_key(b"C")
        child.wait("running check", lambda e: e["status"] == "scanning")
        child.close_keys()
        child.wait("detaching", lambda e: e["overlay"] == "detaching")
        final = child.finish()
        assert final["quit"] is True and final["status"] == "cancelled", final
        assert final["icanon_before"] is True, final
        assert final["restored"] is True, "termios not restored after EOF"
        assert final["lflag"] & termios.ICANON, final
        assert b"\x1b[?2004l" in child.out, "bracketed paste left enabled"
        assert b"end-of-file" in child.err.read_bytes()
    finally:
        child.close()


def _f_pty_resize_case(tmp_path: Path) -> None:
    """120x40 -> 80x24 -> 60x20 -> 59x19 (guidance) -> 120x40 keeps the
    selection; keys other than q/c/F2/Escape wait while too small."""
    child = _FPtyChild(tmp_path, "resize")
    try:
        child.wait("launch", _f_started)
        child.send(b"\x1bOR")
        child.wait("F3 section chooser", lambda e: e["overlay"] == "sections")
        child.send(b"3")
        child.wait("Scans section", lambda e: e["section"] == "scans")
        child.send(b"j")
        child.wait("row 1", lambda e: e["selected"] == 1)
        child.send(b"j")
        child.wait("row 2", lambda e: e["selected"] == 2)
        for columns, rows in ((80, 24), (60, 20)):
            child.resize(columns, rows)
            entry = child.wait(
                f"{columns}x{rows}",
                lambda e, size=[columns, rows]: e["size"] == size,
            )
            assert entry["overlay"] is None and entry["selected"] == 2, entry
            assert entry["section"] == "scans", entry
        mark = len(child.out)
        child.resize(59, 19)
        small = child.wait("59x19", lambda e: e["size"] == [59, 19])
        assert small["overlay"] == "resize_guidance", small
        child.drain(0.3)
        assert "too small" in child.text(mark), "no minimum-size guidance shown"
        child.send(b"j")
        child.drain(0.3)
        assert child.entries()[-1]["selected"] == 2, "a key moved state while too small"
        child.resize(120, 40)
        big = child.wait("120x40 again", lambda e: e["size"] == [120, 40])
        assert big["overlay"] is None and big["selected"] == 2, big
        assert big["section"] == "scans", big
        child.send(b"q")
        child.finish()
    finally:
        child.close()


def _f_visit_all_sections(child: _FPtyChild) -> None:
    child.wait("launch", _f_started)
    for digit, section in zip("12345678", _F_SECTIONS, strict=True):
        child.send(b"\x1bOR")
        child.wait("F3 section chooser", lambda e: e["overlay"] == "sections")
        child.send(digit.encode())
        child.wait(section, lambda e, s=section: e["section"] == s)
        child.drain(0.1)
    child.send(b"\x1b")
    child.drain(0.2)
    child.send(b"q")
    child.finish()


def _f_pty_no_color_case(tmp_path: Path) -> None:
    """NO_COLOR: no colour SGR anywhere in every section's real terminal
    output (the same journey without NO_COLOR does emit colour)."""
    for no_color in (True, False):
        child = _FPtyChild(
            tmp_path,
            "nocolor" if no_color else "color",
            extra_env={"NO_COLOR": "1"} if no_color else None,
        )
        try:
            _f_visit_all_sections(child)
            found = _ANSI_COLOR_SGR.search(bytes(child.out))
            if no_color:
                assert found is None, f"NO_COLOR output carries colour SGR {found}"
            else:
                assert found is not None, "control run emitted no colour at all"
        finally:
            child.close()


def _f_first_scans_frame(child: _FPtyChild, start: int) -> str:
    frames = bytes(child.out[start:]).split(b"\x1b[H")
    for frame in frames:
        text = _F_SGR_OR_CSI.sub(b"", frame).decode(errors="replace")
        if "Scan history" in text:
            return text
    raise AssertionError("no rendered frame showed the Scans section")


def _f_pty_reduced_motion_case(tmp_path: Path) -> None:
    """RUSH_REDUCED_MOTION: the first Scans frame already shows every
    finding row (the final reveal state); without it the first frame is
    mid-reveal."""
    shown: dict[bool, int] = {}
    for reduced in (True, False):
        child = _FPtyChild(
            tmp_path,
            "reduced" if reduced else "motion",
            extra_env={"RUSH_REDUCED_MOTION": "1"} if reduced else None,
        )
        try:
            child.wait("launch", _f_started)
            # Wide enough that the findings table's Message column is shown.
            child.resize(220, 50)
            child.wait("220x50", lambda e: e["size"] == [220, 50])
            child.send(b"\x1bOR")
            child.wait("F3 section chooser", lambda e: e["overlay"] == "sections")
            child.drain(0.2)
            mark = len(child.out)
            child.send(b"3")
            child.wait("Scans section", lambda e: e["section"] == "scans")
            child.drain(0.5)
            first = _f_first_scans_frame(child, mark)
            shown[reduced] = sum(f"finding-row-{i}" in first for i in range(1, 6))
            child.send(b"q")
            child.finish()
        finally:
            child.close()
    assert shown[True] == 5, f"reduced motion first frame showed {shown[True]}/5"
    assert shown[False] < 5, "control: the first frame without reduced motion"


class _FFakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


class _FScriptedReader:
    """Keys every tick until `active_end`, nothing until `idle_end`, then
    `q`; each poll advances the fake clock by its full timeout."""

    def __init__(self, clock: _FFakeClock, active_end: float, idle_end: float):
        self.clock = clock
        self.active_end = active_end
        self.idle_end = idle_end
        self.timeouts: list[float] = []
        self.flip = False

    def read_key(self, timeout: float) -> str | None:
        self.timeouts.append(timeout)
        self.clock.now += timeout
        if self.clock.now <= self.active_end:
            self.flip = not self.flip
            return "j" if self.flip else "k"
        if self.clock.now >= self.idle_end:
            return "q"
        return None

    def get_size(self) -> tuple[int, int]:
        return (120, 40)


def _f_refresh_caps_case(tmp_path: Path) -> None:
    """20 Hz active / 4 Hz idle refresh caps and the <=50ms input poll,
    measured on a fake clock through the real loop and a real `Live`."""
    from rich import live as rich_live

    clock = _FFakeClock()
    start = clock.now
    reader = _FScriptedReader(clock, start + 1.0, start + 3.0)
    refreshes: list[float] = []
    real_update = rich_live.Live.update

    def counting_update(self: Any, renderable: Any, *, refresh: bool = False) -> None:
        if refresh:
            refreshes.append(clock.now - start)
        real_update(self, renderable, refresh=refresh)

    root = tmp_path / "caps"
    root.mkdir()
    console = Console(file=io.StringIO(), force_terminal=True, width=120, height=40)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(time, "monotonic", clock.monotonic)
        mp.setattr(rich_live.Live, "update", counting_update)
        mp.setenv("HOME", str(tmp_path / "home-caps"))
        mp.delenv("RUSH_REDUCED_MOTION", raising=False)
        state = tui.run_interactive_tui(
            [tui.ProjectSeed(name="caps", root=root)],
            console=console,
            key_reader=reader,
            actions=_f_actions(),
            tick_seconds=0.001,
            max_ticks=5000,
            data_root=tmp_path / "rush-data",
        )
    assert state.should_quit, "the scripted q never quit the loop"
    assert max(reader.timeouts) <= 0.05, "input poll above 50ms"
    gaps = [b - a for a, b in itertools.pairwise(refreshes)]
    assert min(gaps) >= 0.05 - 1e-9, f"refresh above 20 Hz: {min(gaps)}"
    active = [t for t in refreshes if t <= 1.0]
    assert 18 <= len(active) <= 21, f"active refreshes in 1s: {len(active)}"
    idle = [t for t in refreshes if 1.3 <= t < 3.0]
    idle_gaps = [b - a for a, b in itertools.pairwise(idle)]
    assert idle_gaps and min(idle_gaps) >= 0.25 - 1e-9, f"idle above 4 Hz: {idle}"
    assert 6 <= len(idle) <= 7, f"idle refreshes in 1.7s: {len(idle)}"


_F_CASES: dict[str, Any] = {
    "matrix": _f_matrix_case,
    "pty_ss3_f2_f3": _f_pty_ss3_case,
    "pty_bracketed_paste": _f_pty_paste_case,
    "pty_sigint_quit_choice": _f_pty_sigint_case,
    "pty_eof_detach": _f_pty_eof_case,
    "pty_resize": _f_pty_resize_case,
    "pty_no_color": _f_pty_no_color_case,
    "pty_reduced_motion": _f_pty_reduced_motion_case,
    "refresh_caps": _f_refresh_caps_case,
}


@pytest.mark.parametrize("case", list(_F_CASES))
def test_t28f_full_surface_acceptance(tmp_path: Path, case: str) -> None:
    """Plan line 432 (T28-F): the 8-section x 8-state x every-action matrix
    with ACTIONS/keymap parity and rendered disabled reasons, plus real-PTY
    terminal behavior and the measured 20 Hz/4 Hz refresh caps."""
    _F_CASES[case](tmp_path)
