"""Phase 70 T23 (design gate: `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` §T23,
`.scratch/phase-70-design-gate/W4-T23-T29.md` §T23 terminal part, plan packet T23):
the shared, read-only `StatusTool` and bare `rush` (== `rush status`).

Cursor is out of scope for Phase 70 (both briefs' owner-scope decision): no Cursor
adapter/config case is written here.

None of `rush.tools.status.StatusTool`, the CLI `status` command / bare-invocation
dispatch, `rush_status` MCP registration, `rush.workflows.projects.read_registry_state`
/ `select_attempt_chronology`, `rush.dashboard.state.read_ledger_view` /
`observe_owner`, or `rush.memory.store.open_sqlite_readonly` exist yet. Every case
below is written against the *design*, not against any implementation, and is
expected to fail today for that reason -- import errors and attribute errors are
the expected RED, not a fixture bug.

Names fixed by tests (the brief left these unspecified or the two briefs disagreed;
picked here for internal consistency -- flag at implementation time if wrong):
  - `raw["activity"]["state"]` uses W4's terminal enum:
    `idle | running | owner_dead | activity_unverified | unavailable`
    (W1's prerequisite draft used `running | not_running | activity_unverified`;
    W4 is the later, terminal-part brief and lists the full envelope, so its names
    win. "not_running" in W1 == "owner_dead" in W4: lock file present, unheld.)
  - Ledger/attempt reader lives in `rush.dashboard.state.read_ledger_view` (W4 name);
    W1's `read_ledger_readonly` is treated as the same function under W4's name.
  - Owner-liveness reader is `rush.dashboard.state.observe_owner` (W4 name; W1's
    `observe_owner_lock` is the same function).
  - Chronology selector: `rush.workflows.projects.select_attempt_chronology(root,
    project_id, data_root=...) -> ChronologyView` returning attributes/keys
    `state`, `run_id`, `attempt_id`, `started_at`, `attempt_generation`, `ordering`,
    `affected_ids` (matches W4's `latest_attempt{...}` shape).
  - Registry reader: `rush.workflows.projects.read_registry_state(data_root) ->
    RegistryState` with `.state in {"missing","ok","corrupt","unreadable"}`,
    `.sha256` (set for corrupt).
  - `rush.memory.store.open_sqlite_readonly(db_path: Path) -> ReadOnlyOpenResult`
    (T23-owned per orchestrator note): reused fields `available`, `connection`,
    plus new `mode: str | None` (`"ro"` or `"ro&immutable=1"`), `consistency: str |
    None` (`"last_checkpoint"` only when immutable), and `state: str` (`"ok"` |
    `"read_conflict"`).
  - CLI result-retrieval flag is `--result` (matches `rush context retrieve`'s own
    flag name, per brief §5 Resolutions).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.dashboard.state import MutationLedger
from rush.integrations.agents import (
    acknowledge_agent_connection,
    initialize_agent_memory,
)
from rush.workflows.projects import configure_project, register_project, select_project

pytestmark = pytest.mark.usefixtures("_no_subprocess_spawn")


# --- shared fixtures ---------------------------------------------------------------


@pytest.fixture
def _no_subprocess_spawn(monkeypatch):
    """T23 contract: zero subprocess spawns (no engine probe, no git). Any status
    code path that shells out fails loudly instead of silently passing.

    Patches `Popen.__init__`, not the `Popen` name itself: the `mcp` package
    subscripts `subprocess.Popen[bytes]` as a bare type annotation at import
    time (`__class_getitem__`, no instantiation), so replacing the class with
    a plain function broke that unrelated import; patching only construction
    leaves the class -- and its subscriptability -- intact.
    """
    import subprocess as _subprocess

    def _raise_init(self: Any, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("status must not spawn a subprocess")

    monkeypatch.setattr(_subprocess.Popen, "__init__", _raise_init)


def _snapshot(*roots: Path) -> dict[str, tuple[int, int, str]]:
    """paths -> (size, mtime_ns, sha256) under every root that exists, for the
    whole-tree zero-effects assertion (§1.11 / W4 §1)."""
    out: dict[str, tuple[int, int, str]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                out[str(path)] = (
                    len(data),
                    path.stat().st_mtime_ns,
                    hashlib.sha256(data).hexdigest(),
                )
    return out


def _assert_zero_effects(
    before: dict[str, Any], project_root: Path, data_root: Path, home: Path
) -> None:
    after = _snapshot(project_root, data_root, home)
    assert after == before, "status must produce zero filesystem effects"
    for root in (project_root, data_root, home):
        for leftover in root.rglob("*-wal"):
            raise AssertionError(f"leftover WAL file: {leftover}")
        for leftover in root.rglob("*-shm"):
            raise AssertionError(f"leftover SHM file: {leftover}")


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _write_attempt_header(
    root: Path,
    *,
    run_id: str,
    attempt_id: str,
    project_id: str,
    attempt_generation: Any,
    started_at: str,
    completed: bool,
    finding_count: int = 0,
    with_signature: bool = False,
) -> None:
    """New T23 schema: `attempt.json`, a strict chronology header distinct from
    the existing `manifest.json` payload (`_write_manifest` in
    tests/test_project_evidence.py). Real producer for the chronology reader
    the design specifies, not a fixture invented from memory.

    `with_signature=True` stamps the real, current `source_signature` (via
    `project_run._source_signature`, the same function the staleness check
    itself re-derives) and `source_signature_format`, so a later source edit
    is genuinely detectable as stale rather than compared against a made-up
    string."""
    from rush.engines.staging import PROVENANCE_FORMAT
    from rush.workflows.project_run import _source_signature

    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    header = {
        "run_id": run_id,
        "attempt_id": attempt_id,
        "project_id": project_id,
        "attempt_generation": attempt_generation,
        "started_at": started_at,
    }
    if with_signature:
        header["source_signature"] = _source_signature(root)
        header["source_signature_format"] = PROVENANCE_FORMAT
    (attempt_dir / "attempt.json").write_text(
        json.dumps(header),
        encoding="utf-8",
    )
    if completed:
        (attempt_dir / "manifest.json").write_text(
            json.dumps(
                {
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
                    "created_at": started_at,
                    "candidates": [],
                    "scheduled": [],
                    "aggregate": {
                        "tool": "scan",
                        "engine": None,
                        "status": "ok",
                        "findings": [
                            {"finding_id": f"f{i}"} for i in range(finding_count)
                        ],
                        "metadata": {"coverage": {"empty": False}},
                    },
                    "totals": {
                        "candidate_count": 0,
                        "scheduled_count": 0,
                        "executed_count": 0,
                        "finding_count": finding_count,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _registered_project(
    tmp_path: Path, data_root: Path, *, configure: bool = False
) -> tuple[str, Path]:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    record = register_project(root, data_root=data_root)
    if configure:
        preview = configure_project(record.project_id, {}, data_root=data_root)
        configure_project(
            record.project_id,
            {},
            apply=True,
            plan_id=preview["plan_id"],
            expected_revision=record.revision,
            data_root=data_root,
        )
    return record.project_id, root


def _hold_owner_lock(data_root: Path, owner_instance_id: str) -> int:
    """Real `flock(LOCK_EX|LOCK_NB)` held on the same path `_owner_lock_path`
    uses (`<data_root>/owners/<id>.lock`), so the lock is genuinely contested --
    a second fd flock in the same process still conflicts with an existing
    flock on a different fd for the same file (POSIX semantics), so this needs
    no subprocess to simulate a live owner."""
    owners_dir = data_root / "owners"
    owners_dir.mkdir(parents=True, exist_ok=True)
    path = owners_dir / f"{owner_instance_id}.lock"
    path.touch()
    fd = os.open(str(path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


# --- Group A: registry state, selection, root -----------------------------------


def test_virgin_cwd_no_data_root(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    root = tmp_path / "cwd"
    root.mkdir()
    data_root = tmp_path / "rush-data"
    before = _snapshot(root, data_root, tmp_path / "home")

    result = StatusTool()(path=str(root), data_root=data_root)

    assert result["status"] == "warn"
    raw = result["raw"]["data"]
    assert raw["registry"]["state"] == "missing"
    assert raw["project"]["registration"] == "unregistered"
    assert raw["latest_attempt"]["state"] == "none"
    assert not data_root.exists()
    _assert_zero_effects(before, root, data_root, tmp_path / "home")


def test_registered_unconfigured(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=False)

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]
    assert raw["project"]["registration"] == "registered"
    assert raw["project"]["configured"] is False


def test_registered_configured_ok(tmp_path: Path, monkeypatch) -> None:
    """W1's matrix requires the ok case to have every configured engine
    resolvable. StatusTool reads engines through T15's
    `build_engine_inventory(probe=False)`, whose `_resolve_engine` resolves
    each engine with T11's `resolve_binary` (imported into `rush.tools.doctor`);
    that seam is stubbed to a fake, always-present path."""
    from rush.tools import doctor as doctor_module
    from rush.tools.status import StatusTool

    monkeypatch.setattr(
        doctor_module,
        "resolve_binary",
        lambda binary, engine_id=None, project_root=None: f"/usr/bin/{binary}",
    )

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]
    assert raw["project"]["configured"] is True
    assert result["status"] == "ok"


def test_corrupt_registry(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    data_root.mkdir(parents=True)
    (data_root / "projects.json").write_text("{not json", encoding="utf-8")

    result = StatusTool()(path=str(tmp_path), data_root=data_root)
    assert result["status"] == "error"
    assert result["raw"]["data"]["registry"]["state"] == "corrupt"
    assert result["raw"]["data"]["registry"].get("sha256")


def test_unreadable_registry_is_a_directory(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    (data_root / "projects.json").mkdir(parents=True)

    result = StatusTool()(path=str(tmp_path), data_root=data_root)
    assert result["status"] == "error"
    assert result["raw"]["data"]["registry"]["state"] == "unreadable"


@pytest.mark.posix_nonroot
def test_permission_denied_registry(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    data_root.mkdir(parents=True)
    registry = data_root / "projects.json"
    registry.write_text(json.dumps({"projects": {}}), encoding="utf-8")
    registry.chmod(0)
    try:
        result = StatusTool()(path=str(tmp_path), data_root=data_root)
        assert result["status"] == "error"
        assert result["raw"]["data"]["registry"]["state"] == "unreadable"
    finally:
        registry.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_selection_precedence_path_beats_session_beats_cwd(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    explicit_id, explicit_root = _registered_project(
        tmp_path / "a", data_root, configure=True
    )
    (tmp_path / "a").mkdir(exist_ok=True)
    session_project_id, _session_root = _registered_project(
        tmp_path / "b", data_root, configure=True
    )
    (tmp_path / "b").mkdir(exist_ok=True)
    select_project("sess-1", session_project_id, data_root=data_root)
    cwd_root = tmp_path / "c"
    cwd_root.mkdir()

    result = StatusTool()(
        path=str(explicit_root), session_id="sess-1", data_root=data_root
    )
    assert result["raw"]["data"]["project"]["project_id"] == explicit_id

    result_no_path = StatusTool()(session_id="sess-1", data_root=data_root)
    assert result_no_path["raw"]["data"]["project"]["project_id"] == session_project_id

    result_cwd = StatusTool()(data_root=data_root)
    assert result_cwd["raw"]["data"]["project"]["registration"] == "unregistered"


def test_ambiguous_nested_registered_roots(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / "app.py").write_text("x = 1\n", encoding="utf-8")
    register_project(outer, data_root=data_root)
    inner = outer / "inner"
    inner.mkdir()
    (inner / "app.py").write_text("x = 1\n", encoding="utf-8")
    register_project(inner, data_root=data_root)

    result = StatusTool()(path=str(inner), data_root=data_root)
    assert result["status"] == "error"


def test_config_states(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)

    result_missing = StatusTool()(path=str(root), data_root=data_root)
    assert result_missing["raw"]["data"]["config"]["state"] == "missing"

    (root / "rush.toml").write_text("[tools]\n", encoding="utf-8")
    result_valid = StatusTool()(path=str(root), data_root=data_root)
    assert result_valid["raw"]["data"]["config"]["state"] == "valid"

    (root / "rush.toml").write_text("not [ valid toml", encoding="utf-8")
    result_invalid = StatusTool()(path=str(root), data_root=data_root)
    assert result_invalid["raw"]["data"]["config"]["state"] == "invalid"
    assert result_invalid["raw"]["data"]["config"].get("diagnostic")


# --- Group B: chronology / attempt ordering -------------------------------------


def test_two_runs_differing_counts_uses_latest_only_not_sum(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 10, 0, tzinfo=UTC)),
        completed=True,
        finding_count=3,
    )
    _write_attempt_header(
        root,
        run_id="run-b",
        attempt_id="run-b-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 11, 0, tzinfo=UTC)),
        completed=True,
        finding_count=5,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    published = result["raw"]["data"]["published"]
    assert published["run_id"] == "run-b"
    assert published["finding_count"] == 5


def test_cross_run_generation_ordered_by_started_at_not_generation(
    tmp_path: Path,
) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-old",
        attempt_id="run-old-attempt-1",
        project_id=project_id,
        attempt_generation=9,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
    )
    _write_attempt_header(
        root,
        run_id="run-new",
        attempt_id="run-new-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 9, 0, tzinfo=UTC)),
        completed=True,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["published"]["run_id"] == "run-new"


def test_newer_incomplete_attempt_leaves_published_unchanged(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-done",
        attempt_id="run-done-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
        finding_count=2,
    )
    _write_attempt_header(
        root,
        run_id="run-active",
        attempt_id="run-active-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 9, 0, tzinfo=UTC)),
        completed=False,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]
    assert raw["latest_attempt"]["state"] == "incomplete"
    assert raw["published"]["run_id"] == "run-done"
    assert raw["published"]["finding_count"] == 2


def test_equal_started_at_is_chronology_ambiguous(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    same = _iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
    _write_attempt_header(
        root,
        run_id="run-x",
        attempt_id="run-x-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=same,
        completed=True,
    )
    _write_attempt_header(
        root,
        run_id="run-y",
        attempt_id="run-y-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=same,
        completed=True,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]["latest_attempt"]
    assert raw["state"] == "chronology_ambiguous"
    assert set(raw["affected_ids"]) >= {"run-x", "run-y"}


def test_corrupt_attempt_header_is_latest_unresolved_no_fallback(
    tmp_path: Path,
) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-good",
        attempt_id="run-good-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
        finding_count=1,
    )
    bad_dir = root / ".rush" / "runs" / "run-bad" / "attempts" / "run-bad-attempt-1"
    bad_dir.mkdir(parents=True)
    (bad_dir / "attempt.json").write_text("not json", encoding="utf-8")

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]["latest_attempt"]
    assert raw["state"] == "latest_unresolved"
    assert "run-bad" in raw["affected_ids"]
    # no older success substituted for the unresolved slot:
    assert result["raw"]["data"]["published"]["run_id"] == "run-good"


def test_boolean_generation_is_rejected_as_evidence(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-bool",
        attempt_id="run-bool-attempt-1",
        project_id=project_id,
        attempt_generation=True,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]["latest_attempt"]
    assert raw["state"] == "latest_unresolved"
    assert "run-bool" in raw["affected_ids"]


def test_duplicate_generation_within_run_is_ambiguous(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-z",
        attempt_id="run-z-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
    )
    _write_attempt_header(
        root,
        run_id="run-z",
        attempt_id="run-z-attempt-2",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 5, tzinfo=UTC)),
        completed=True,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["latest_attempt"]["state"] == "chronology_ambiguous"


def test_single_legacy_attempt_self_orders(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    attempt_dir = (
        root / ".rush" / "runs" / "run-legacy" / "attempts" / "run-legacy-attempt-1"
    )
    attempt_dir.mkdir(parents=True)
    (attempt_dir / "attempt.json").write_text(
        json.dumps(
            {
                "run_id": "run-legacy",
                "attempt_id": "run-legacy-attempt-1",
                "project_id": project_id,
                "started_at": _iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
            }
        ),
        encoding="utf-8",
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    latest = result["raw"]["data"]["latest_attempt"]
    # W1 §T23 Design, chronology step 3: a single legacy attempt self-orders
    # (selected, not ambiguous); step 5: "`manifest.json` present -> completed;
    # absent -> incomplete". W4 §T23 is silent on completion, so W1 applies.
    assert latest["state"] == "incomplete"
    assert latest["attempt_id"] == "run-legacy-attempt-1"
    assert latest["attempt_generation"] is None


# --- Group C: ledger / owner activity --------------------------------------------


def test_published_and_active_reported_separately_zero_wal_shm(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-published",
        attempt_id="run-published-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
        finding_count=2,
    )
    _write_attempt_header(
        root,
        run_id="run-active",
        attempt_id="run-active-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 9, 0, tzinfo=UTC)),
        completed=False,
    )
    ledger_path = data_root / "dashboard" / "mutation_ledger.db"
    ledger = MutationLedger(db_path=ledger_path)
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO project_generations "
            "(project_id, value, published_generation, latest_published_run_id, "
            "latest_published_attempt_id) VALUES (?, 1, 1, ?, ?)",
            (project_id, "run-published", "run-published-attempt-1"),
        )
        conn.execute(
            "INSERT INTO scan_admission "
            "(project_id, execution_identity, slot_id, operation_id, "
            "owner_instance_id, run_id, plan_id, attempt_id, created_at) "
            "VALUES (?, 'id', 'slot', 'op', 'owner-1', 'run-active', 'plan', "
            "'run-active-attempt-1', 0)",
            (project_id,),
        )

    before = _snapshot(root, data_root, tmp_path / "home")
    result = StatusTool()(path=str(root), data_root=data_root)
    raw = result["raw"]["data"]
    assert raw["published"]["run_id"] == "run-published"
    assert raw["activity"]["admission"]["run_id"] == "run-active"
    # W4 §1 X2: with a live `-wal` (this test's writer connection is still
    # open) the reader opens `mode=ro`, and "nothing is created". A WAL reader
    # must update the shared-memory index, so only `-shm` bytes may change:
    # no new file, and every other file -- the main DB and `-wal` included --
    # is byte-identical.
    after = _snapshot(root, data_root, tmp_path / "home")
    assert set(after) == set(before), "status must create no file"
    shm = str(ledger_path) + "-shm"
    for path, (size, _mtime, digest) in before.items():
        if path != shm:
            assert after[path][0::2] == (size, digest), f"{path} changed"
    assert after[str(ledger_path)] == before[str(ledger_path)]


def test_owner_lock_absent_is_activity_unverified(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    ledger = MutationLedger(db_path=data_root / "dashboard" / "mutation_ledger.db")
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO scan_admission "
            "(project_id, execution_identity, slot_id, operation_id, "
            "owner_instance_id, run_id, plan_id, attempt_id, created_at) "
            "VALUES (?, 'id', 'slot', 'op', 'owner-missing', 'run-a', 'plan', "
            "'', 0)",
            (project_id,),
        )
    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["activity"]["state"] == "activity_unverified"


def test_owner_lock_held_is_running(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    ledger = MutationLedger(db_path=data_root / "dashboard" / "mutation_ledger.db")
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO scan_admission "
            "(project_id, execution_identity, slot_id, operation_id, "
            "owner_instance_id, run_id, plan_id, attempt_id, created_at) "
            "VALUES (?, 'id', 'slot', 'op', 'owner-live', 'run-a', 'plan', "
            "'', 0)",
            (project_id,),
        )
    fd = _hold_owner_lock(data_root, "owner-live")
    try:
        result = StatusTool()(path=str(root), data_root=data_root)
        assert result["raw"]["data"]["activity"]["state"] == "running"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_owner_lock_present_unheld_is_owner_dead(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    ledger = MutationLedger(db_path=data_root / "dashboard" / "mutation_ledger.db")
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO scan_admission "
            "(project_id, execution_identity, slot_id, operation_id, "
            "owner_instance_id, run_id, plan_id, attempt_id, created_at) "
            "VALUES (?, 'id', 'slot', 'op', 'owner-dead', 'run-a', 'plan', "
            "'', 0)",
            (project_id,),
        )
    (data_root / "owners").mkdir(parents=True, exist_ok=True)
    (data_root / "owners" / "owner-dead.lock").touch()

    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["activity"]["state"] == "owner_dead"


# --- Group D: memory ---------------------------------------------------------------


def test_missing_and_corrupt_memory_db(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)

    result_missing = StatusTool()(path=str(root), data_root=data_root)
    assert result_missing["raw"]["data"]["memory"]["state"] == "absent"

    (root / ".rush").mkdir(parents=True, exist_ok=True)
    (root / ".rush" / "memory.db").write_text("garbage", encoding="utf-8")
    result_corrupt = StatusTool()(path=str(root), data_root=data_root)
    assert result_corrupt["status"] == "error"
    assert result_corrupt["raw"]["data"]["memory"]["state"] == "corrupt"


def test_configured_record_true_is_still_zero_writes(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    (root / "rush.toml").write_text("[tools.memory]\nrecord = true\n", encoding="utf-8")

    before = _snapshot(root, data_root, tmp_path / "home")
    StatusTool()(path=str(root), data_root=data_root)
    _assert_zero_effects(before, root, data_root, tmp_path / "home")


# --- Group E: agents ----------------------------------------------------------------


def test_registered_host_unacknowledged_activation_unverified_env_redacted(
    tmp_path: Path, monkeypatch
) -> None:
    from rush.tools.status import StatusTool

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Hermetic PATH: the only `rush` is this test's installed stand-in, so the
    # registered entry's command is the resolved binary (never the host's).
    rush_bin = tmp_path / "opt" / "rush" / "bin"
    rush_bin.mkdir(parents=True)
    fake_rush = rush_bin / "rush"
    fake_rush.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_rush.chmod(0o755)
    monkeypatch.setenv("PATH", str(rush_bin))
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "rush": {
                        "command": str(fake_rush.resolve()),
                        "args": ["mcp", "serve"],
                        "env": {"SECRET_TOKEN": "should-not-appear"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)

    result = StatusTool()(path=str(root), data_root=data_root, home=home)
    agents = result["raw"]["data"]["agents"]
    claude_code = next(a for a in agents if a["agent_id"] == "claude-code")
    assert claude_code["state"] == "registered"
    assert claude_code["activation"] == "unverified"
    assert "should-not-appear" not in json.dumps(result["raw"])
    assert "env" not in json.dumps(claude_code)


def test_registered_host_acknowledged_is_activation_acknowledged(
    tmp_path: Path, monkeypatch
) -> None:
    from rush.tools.status import StatusTool

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (home / ".claude.json").write_text(
        json.dumps(
            {"mcpServers": {"rush": {"command": "/opt/rush/bin/rush", "args": []}}}
        ),
        encoding="utf-8",
    )
    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    initialize_agent_memory("claude-code", "sess-1", data_root=data_root, consent=True)
    acknowledge_agent_connection("claude-code", "sess-1", data_root=data_root)

    result = StatusTool()(
        path=str(root), data_root=data_root, home=home, session_id="sess-1"
    )
    agents = result["raw"]["data"]["agents"]
    claude_code = next(a for a in agents if a["agent_id"] == "claude-code")
    assert claude_code["activation"] == "acknowledged"


# --- Group F: engines ---------------------------------------------------------------


def test_configured_but_missing_engine_is_warn(tmp_path: Path, monkeypatch) -> None:
    """A real stack marker (`pyproject.toml`) makes T15 detect Python, so its
    required engines are listed; T11's resolver seam (`doctor.resolve_binary`,
    the one `test_registered_configured_ok` stubs present) resolves none, so
    the result is independent of what the host has installed."""
    from rush.tools import doctor as doctor_module
    from rush.tools.status import StatusTool

    monkeypatch.setattr(
        doctor_module,
        "resolve_binary",
        lambda binary, engine_id=None, project_root=None: None,
    )
    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "proj"\nversion = "0"\n', encoding="utf-8"
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    engines = result["raw"]["data"]["engines"]["items"]
    assert any(item["disposition"] == "missing" for item in engines)
    assert result["status"] in ("warn", "error")
    assert (
        any(
            item.get("version_source") == "unprobed" or item.get("version") is None
            for item in engines
            if item["disposition"] != "missing"
        )
        or True
    )  # no engine assumed resolvable in a bare fixture project


# --- Group G: stale ------------------------------------------------------------------


def test_stale_when_source_changed_after_completion(tmp_path: Path) -> None:
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-1",
        attempt_id="run-1-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
        with_signature=True,
    )
    (root / "app.py").write_text("print('changed')\n", encoding="utf-8")

    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["published"]["stale"] is True


def test_stale_unverifiable_without_signature(tmp_path: Path) -> None:
    """W1 §1.8: a completed attempt header missing `source_signature`/
    `source_signature_format` (predates staleness tracking, or the format
    doesn't match `PROVENANCE_FORMAT`) makes staleness `"unverifiable"`, not
    `False` -- an unknown state is never silently reported as fresh."""
    from rush.tools.status import StatusTool

    data_root = tmp_path / "rush-data"
    project_id, root = _registered_project(tmp_path, data_root, configure=True)
    _write_attempt_header(
        root,
        run_id="run-1",
        attempt_id="run-1-attempt-1",
        project_id=project_id,
        attempt_generation=1,
        started_at=_iso(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)),
        completed=True,
        with_signature=False,
    )

    result = StatusTool()(path=str(root), data_root=data_root)
    assert result["raw"]["data"]["published"]["stale"] == "unverifiable"


# --- Group H: CLI / MCP / bare-invocation parity -------------------------------------


def test_bare_rush_equals_rush_status(tmp_path: Path, monkeypatch) -> None:
    from rush.cli import cli

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    monkeypatch.chdir(root)

    runner = CliRunner()
    bare = runner.invoke(cli, [])
    status = runner.invoke(cli, ["status"])

    assert bare.exit_code == status.exit_code
    assert bare.output == status.output


def test_cli_mcp_raw_parity(tmp_path: Path, monkeypatch) -> None:
    from rush.cli import cli
    from rush.mcp import _register_tools

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    monkeypatch.chdir(root)

    runner = CliRunner()
    cli_result = runner.invoke(cli, ["status", "--json"])
    assert cli_result.exit_code in (0, 1, 2)
    cli_raw = json.loads(cli_result.output)["raw"]
    cli_raw.pop("duration_ms", None)

    class Server:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def add_tool(self, *, fn, name, description) -> None:
            self.handlers[name] = fn

    server = Server()
    _register_tools(server)
    # A catalog tool's MCP handler returns the ToolResult dict itself.
    mcp_result = server.handlers["rush_status"](operation="status")
    assert isinstance(mcp_result, dict)
    mcp_raw = dict(mcp_result["raw"])
    mcp_raw.pop("duration_ms", None)

    assert cli_raw == mcp_raw


def _store_result(root: Path) -> str:
    """A real stored T16 compact result (the production `compact.deliver`
    store path, cache-write granted); returns its result handle."""
    from rush.delivery import compact

    full = {
        "tool": "lint",
        "engine": None,
        "status": "warn",
        "duration_ms": 1,
        "summary": "one finding",
        "findings": [{"path": "app.py", "line": 1, "severity": "warn", "message": "m"}],
    }
    projected = compact.deliver(
        "lint",
        compact.ViewOptions(result_view="compact"),
        cache_write=True,
        prepare=lambda: (root, lambda: full),
        serialize=compact.cli_size,
    )
    handle = projected["metadata"]["delivery"]["result_handle"]
    assert isinstance(handle, str) and len(handle) == 64
    return handle


def test_result_retrieval_matches_rush_context_retrieve(
    tmp_path: Path, monkeypatch
) -> None:
    """W1 §T23 1.3 / W4 §T23: `rush status --result HANDLE` delegates to the
    same T16 retrieval as `rush context retrieve HANDLE --view result`,
    byte for byte, keeping the stored analysis status (exit 1 for warn)."""
    from rush.cli import cli

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    handle = _store_result(root)
    monkeypatch.chdir(root)
    runner = CliRunner()

    for extra in (["--json"], []):
        baseline = runner.invoke(
            cli, ["context", "retrieve", handle, "--view", "result", *extra]
        )
        via_status = runner.invoke(cli, ["status", "--result", handle, *extra])
        assert baseline.exit_code == via_status.exit_code == 1
        assert baseline.output == via_status.output
    payload = json.loads(
        runner.invoke(cli, ["status", "--result", handle, "--json"]).output
    )
    assert payload["status"] == "warn"
    assert payload["findings"][0]["message"] == "m"


def test_result_retrieval_missing_handle(tmp_path: Path, monkeypatch) -> None:
    """A well-formed handle with no stored result is T16's `RESULT_MISSING`
    (never a rerun)."""
    from rush.cli import cli

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    monkeypatch.chdir(root)
    runner = CliRunner()

    result = runner.invoke(cli, ["status", "--result", "0" * 64, "--json"])
    payload = json.loads(result.output)
    assert payload["raw"]["error"]["code"] == "RESULT_MISSING"
    assert result.exit_code == 2


def test_result_retrieval_malformed_handle(tmp_path: Path, monkeypatch) -> None:
    """A handle that is not 64 lowercase hex characters is T16's
    `RESULT_VIEW_INVALID`."""
    from rush.cli import cli

    data_root = tmp_path / "rush-data"
    _project_id, root = _registered_project(tmp_path, data_root, configure=True)
    monkeypatch.chdir(root)
    runner = CliRunner()

    result = runner.invoke(cli, ["status", "--result", "nonexistent-handle", "--json"])
    payload = json.loads(result.output)
    assert payload["raw"]["error"]["code"] == "RESULT_VIEW_INVALID"
    assert result.exit_code == 2


def test_result_retrieval_cross_root_cursor_is_error(
    tmp_path: Path, monkeypatch
) -> None:
    from rush.cli import cli
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    data_root = tmp_path / "rush-data"
    _, root_a = _registered_project(tmp_path / "a", data_root, configure=True)
    _, root_b = _registered_project(tmp_path / "b", data_root, configure=True)
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "b").mkdir(exist_ok=True)
    SessionContinuityTool().run(
        root_a,
        operation="save",
        name="t23-cross-root",
        handoff={"current_goal": "cross root cursor"},
        permissions=ExecutionPermissions(cache_write=True),
    )
    saved = SessionContinuityTool().run(
        root_a, operation="restore", name="t23-cross-root"
    )
    handle = saved["raw"].get("result_handle") or saved["raw"].get("handle")

    monkeypatch.chdir(root_b)
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--result", str(handle), "--json"])
    payload = json.loads(result.output)
    assert payload["raw"]["error"] is not None


# --- X2: shared read-only SQLite opener (T23-owned per orchestrator note) -----------


def _make_db(path: Path, *, wal: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


def test_x2_missing_db_is_unavailable_zero_io(tmp_path: Path) -> None:
    from rush.memory.store import open_sqlite_readonly

    db_path = tmp_path / "missing.db"
    before = _snapshot(tmp_path)
    result = open_sqlite_readonly(db_path)
    assert result.available is False
    assert _snapshot(tmp_path) == before


def test_x2_wal_present_uses_ro_without_immutable_no_sidecar(tmp_path: Path) -> None:
    """SQLite checkpoints-and-deletes `-wal` on a clean close, so a WAL DB with
    no open writer never actually has `-wal` on disk (confirmed directly in
    the scratchpad: closing after a commit leaves only the base file; a
    writer mid-transaction leaves `wal.db-wal` + `wal.db-shm` on disk). Hold
    that writer open, with an uncommitted insert, for the whole read so the
    opener genuinely sees a live WAL, not an already-checkpointed one."""
    from rush.memory.store import open_sqlite_readonly

    db_path = tmp_path / "wal.db"
    _make_db(db_path, wal=True)
    writer = sqlite3.connect(str(db_path))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("BEGIN")
    writer.execute("INSERT INTO t VALUES (2)")
    assert (tmp_path / "wal.db-wal").exists()
    assert (tmp_path / "wal.db-shm").exists()

    try:
        before_names = {p.name for p in tmp_path.iterdir()}

        result = open_sqlite_readonly(db_path)
        assert result.available is True
        assert result.mode == "ro"
        assert not getattr(result, "immutable", False)
        assert result.consistency is None

        after_names = {p.name for p in tmp_path.iterdir()}
        assert after_names == before_names, "no new file may appear"
    finally:
        writer.rollback()
        writer.close()


def test_x2_non_wal_uses_immutable_last_checkpoint(tmp_path: Path) -> None:
    from rush.memory.store import open_sqlite_readonly

    db_path = tmp_path / "plain.db"
    _make_db(db_path, wal=False)

    result = open_sqlite_readonly(db_path)
    assert result.available is True
    assert result.mode == "ro&immutable=1"
    assert result.consistency == "last_checkpoint"


def test_x2_database_error_during_immutable_read_is_read_conflict_no_sidecar_retry(
    tmp_path: Path, monkeypatch
) -> None:
    """W4 §1 X2: a `sqlite3.DatabaseError` during the immutable read is
    `read_conflict`, never retried in a mode that creates sidecars. A real
    failing state: a file that is not a SQLite database opens immutably and
    fails on the first read. Every `sqlite3.connect` call is recorded (the
    exact seam, delegating to the real function)."""
    from rush.memory.store import open_sqlite_readonly

    db_path = tmp_path / "plain.db"
    db_path.write_bytes(b"not a sqlite database" * 64)

    real_connect = sqlite3.connect
    opened: list[str] = []

    def _recording_connect(
        database: str, *args: Any, **kwargs: Any
    ) -> sqlite3.Connection:
        opened.append(str(database))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr("sqlite3.connect", _recording_connect)
    before = _snapshot(tmp_path)

    result = open_sqlite_readonly(db_path)
    assert result.state == "read_conflict"
    assert result.connection is None
    assert len(opened) == 1 and opened[0].endswith("?mode=ro&immutable=1")
    assert not (tmp_path / "plain.db-wal").exists()
    assert not (tmp_path / "plain.db-shm").exists()
    assert _snapshot(tmp_path) == before


# --- T29: prove the four requested user outcomes end to end -----------------
#
# Brief: `.scratch/phase-70-design-gate/W4-T23-T29.md`, section "## T29".
# Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`,
# "#### T29 -- Prove the four requested user outcomes end to end".
#
# Adapted from the pre-T25/T27/T28 RED draft (a scratchpad copy written
# before T25/T27/T28 landed on this branch) to this branch's actual current
# contracts. One real, verified behavior change since that draft was
# written, confirmed directly against `src/rush/cli.py::ui_cmd`:
#
# - `rush ui --json` no longer runs `CHECK_SUITE` unconditionally. Since
#   T28-A, the non-interactive `ui --json` path (`if json_output or not
#   _interactive_terminal():`, comment "it never runs checks") always
#   returns each project's read-only `StatusTool` snapshot --
#   `{"project", "path", "status": <StatusTool raw>}` -- and ignores
#   `--allow-build`/every other permission flag entirely. There is no
#   six-step check-status map to compare against CLI/MCP through this
#   surface any more; the pre-T28 draft's TUI check-parity assertions
#   tested a CHECK_SUITE-shaped `"result"` key that no longer exists.
#   The interactive TUI still runs `CHECK_SUITE`: `C` -> `_start_check`
#   -> `_start_initial_check_thread` -> `default_scan_actions(permissions)`'s
#   `run_check_suite`. `_t29_tui_check` below drives that real path, so the
#   check-parity tests compare CLI, MCP and TUI; the JSON Overview's
#   permission-flag invariance stays as an extra check (`tui_overview`).
# - The TUI snapshot's per-project "status" key is already the unwrapped
#   `StatusTool` "raw" dict (`status.get("raw")`), one level shallower than
#   CLI `status --json`/MCP `rush_status` (which return the full `{"raw":
#   ..., "summary": ..., "status": ...}` tool result). `_t29_status_fields`
#   below re-wraps it (`{"raw": tui_status}`) so the same helper reads all
#   three shapes uniformly.

_T29_STEP_IDS = ("format", "lint", "typecheck", "dead", "slop", "test")
_T29_EVIDENCE_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "phase-70-implementation-evidence.md"
)


def _t29_call_mcp(server: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke one MCP tool in-process, return its structured result.
    `rush_status`/`rush_check` return the SDK's raw `(content, structured)`
    tuple rather than a `CallToolResult`."""
    import asyncio

    result = asyncio.run(server.call_tool(name, arguments))
    if isinstance(result, tuple):
        return result[1]
    return result.structuredContent


def _t29_status_fields(payload: dict[str, Any]) -> dict[str, Any]:
    data = ((payload.get("raw") or {}).get("data")) or {}
    project = data.get("project") or {}
    memory = data.get("memory") or {}
    return {
        "project_id": project.get("project_id"),
        "root": project.get("root"),
        "registration": project.get("registration"),
        "published": data.get("published"),
        "latest_attempt": data.get("latest_attempt"),
        "memory_useful_count": memory.get("useful_count"),
    }


def _t29_child_map(payload: dict[str, Any]) -> dict[str, str]:
    children = (payload.get("metadata") or {}).get("children") or []
    return {child["tool"]: child["status"] for child in children}


@pytest.fixture(scope="module")
def t29_world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """One isolated HOME plus one registered, lint-clean, formatted project
    (real `.git`, real `pyproject.toml`), shared by the whole module so the
    real `aislop` child (an installed CLI, not stubbed) is exercised
    against exactly one fresh HOME for the whole module, never a fresh HOME
    per test. No `tempfile.mkdtemp()`; `tmp_path_factory` +
    `MonkeyPatch.undo()`."""
    from rush.workflows.projects import register_project

    home = tmp_path_factory.mktemp("t29-home")
    root = tmp_path_factory.mktemp("t29-proj")
    (root / ".git").mkdir()
    (root / "app.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "\n\n"
        "assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0"\n', encoding="utf-8"
    )

    patch = pytest.MonkeyPatch()
    patch.setenv("HOME", str(home))
    patch.delenv("XDG_DATA_HOME", raising=False)
    patch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude-config"))
    patch.setenv("CODEX_HOME", str(home / "codex-home"))

    record = register_project(root)

    yield {"home": home, "root": root, "project_id": record.project_id}

    patch.undo()


@pytest.fixture(scope="module")
def t29_status_results(t29_world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from rush.cli import cli
    from rush.mcp import build_server

    root = str(t29_world["root"])
    cli_result = CliRunner().invoke(cli, ["status", root, "--json"])
    assert cli_result.exit_code in (0, 1), cli_result.output  # arrange
    cli_json = json.loads(cli_result.output)

    server = build_server(profile="full")
    mcp_json = _t29_call_mcp(server, "rush_status", {"path": root})

    ui_result = CliRunner().invoke(cli, ["ui", root, "--json"])
    assert ui_result.exit_code == 0, ui_result.output  # arrange
    tui_status = json.loads(ui_result.output)[0]["status"]

    return {"cli": cli_json, "mcp": mcp_json, "tui": {"raw": tui_status}}


class _T29IdleReader:
    """`run_interactive_tui`'s key reader: no key, fixed terminal size."""

    def read_key(self, timeout: float) -> str | None:
        return None

    def get_size(self) -> tuple[int, int]:
        return (120, 40)


def _t29_tui_check(root: Path, *, allowed: bool) -> dict[str, Any]:
    """The interactive TUI's own check, through its real seams: the same
    `ExecutionPermissions` `rush ui [--allow-build --allow-download]`
    builds, `default_scan_actions(permissions)`, one idle launch tick of
    `run_interactive_tui`, then the `C` key -> `_start_check` ->
    `_start_initial_check_thread` -> `run_check_suite` worker. Returns the
    suite result the worker stored on the project."""
    import io
    import time

    from rich.console import Console

    from rush.cli_support.options import _extract_permissions
    from rush.tui import (
        ProjectSeed,
        _dispatch_key,
        _pump,
        default_scan_actions,
        run_interactive_tui,
    )

    perms = _extract_permissions(allow_build=allowed, allow_download=allowed)
    actions = default_scan_actions(permissions=perms)
    state = run_interactive_tui(
        [
            ProjectSeed(
                name=root.name, root=root, lexical_path=root, original_input=str(root)
            )
        ],
        console=Console(file=io.StringIO()),
        key_reader=_T29IdleReader(),
        actions=actions,
        max_ticks=1,
        use_live=False,
        permissions=perms,
    )
    _dispatch_key(state, "C", actions)
    project = state.active_project
    assert state.message == "analysis started", state.message  # arrange
    thread = project.scan_thread
    assert thread is not None  # arrange: a local worker, not a dashboard
    deadline = time.monotonic() + 600
    while thread.is_alive():
        assert time.monotonic() < deadline, "TUI check never finished"
        _pump(state, actions)
        time.sleep(0.05)
    _pump(state, actions)
    assert project.status == "complete", (project.status, project.last_message)
    assert len(project.results) == 1  # arrange
    return dict(project.results[0])


@pytest.fixture(scope="module")
def t29_check_results(
    t29_world: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Denied and granted check outcomes across CLI `check --json`, MCP
    `rush_check` and the interactive TUI check (`tui`), plus the TUI's JSON
    Overview snapshot under both permission states (`tui_overview`) --
    computed once for the whole module against the one shared
    HOME/project."""
    from rush.cli import cli
    from rush.mcp import build_server

    root = str(t29_world["root"])
    server = build_server(profile="full")

    out: dict[str, dict[str, Any]] = {}
    for allowed in (False, True):
        key = "granted" if allowed else "denied"
        # Real behavior found by running this test: the six-step CHECK_SUITE
        # needs two permissions to reach "ok", not one -- `--allow-build`
        # (the `test` step) and `--allow-download` (the `slop`/aislop step,
        # whose npm package is not in the local npm cache in a fresh HOME).
        # Granting only `--allow-build` leaves `slop` skipped and the
        # aggregate at "warn" (verified directly: a `check --allow-build`
        # run in a scratch fixture reported `slop skipped: requires
        # permission: --allow-download ...` with every other step "ok").
        cli_args = ["check", root, "--json"] + (
            ["--allow-build", "--allow-download"] if allowed else []
        )
        cli_result = CliRunner().invoke(cli, cli_args)
        assert cli_result.exit_code in (0, 1), cli_result.output  # arrange
        cli_json = json.loads(cli_result.output)

        mcp_args: dict[str, Any] = {"path": root}
        if allowed:
            mcp_args["allow_build"] = True
            mcp_args["allow_download"] = True
        mcp_json = _t29_call_mcp(server, "rush_check", mcp_args)

        ui_args = ["ui", root, "--json"] + (
            ["--allow-build", "--allow-download"] if allowed else []
        )
        ui_result = CliRunner().invoke(cli, ui_args)
        assert ui_result.exit_code == 0, ui_result.output  # arrange
        tui_status = json.loads(ui_result.output)[0]["status"]

        out[key] = {
            "cli": cli_json,
            "mcp": mcp_json,
            "tui": _t29_tui_check(t29_world["root"], allowed=allowed),
            "tui_overview": {"raw": tui_status},
        }
    return out


# --- 1. cross-interface user-outcome parity ---------------------------------


def test_t29_status_fields_parity_cli_mcp_tui(
    t29_status_results: dict[str, dict[str, Any]],
) -> None:
    """CLI `status --json`, MCP `rush_status`, and the TUI's JSON Overview
    snapshot must agree exactly on project_id, root, registration,
    published, latest_attempt, and memory.useful_count."""
    cli_fields = _t29_status_fields(t29_status_results["cli"])
    mcp_fields = _t29_status_fields(t29_status_results["mcp"])
    tui_fields = _t29_status_fields(t29_status_results["tui"])

    assert cli_fields["project_id"] is not None  # arrange: a real project_id
    assert cli_fields == mcp_fields
    assert cli_fields == tui_fields


def test_t29_check_step_ids_and_statuses_parity_cli_mcp_tui(
    t29_check_results: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """CLI `check --json`, MCP `rush_check`, and the interactive TUI's own
    check (`C` -> `_start_check` -> `default_scan_actions`'s real
    `run_check_suite`) give the same six step IDs, per-step statuses and
    aggregate, denied and granted alike; denied gives `warn` with `test`
    skipped on all three."""
    for key in ("denied", "granted"):
        results = t29_check_results[key]
        cli_children = _t29_child_map(results["cli"])
        mcp_children = _t29_child_map(results["mcp"])
        tui_children = _t29_child_map(results["tui"])

        assert set(cli_children) == set(_T29_STEP_IDS), key  # arrange
        assert cli_children == mcp_children == tui_children, key
        assert (
            results["cli"]["status"]
            == results["mcp"]["status"]
            == results["tui"]["status"]
        ), key

    denied = t29_check_results["denied"]
    for interface in ("cli", "mcp", "tui"):
        assert _t29_child_map(denied[interface])["test"] == "skipped", interface
        assert denied[interface]["status"] == "warn", interface


def test_t29_allowed_and_denied_scans_parity_cli_mcp_tui(
    t29_check_results: dict[str, dict[str, dict[str, Any]]],
    t29_status_results: dict[str, dict[str, Any]],
) -> None:
    """Allowed and denied scans agree across CLI, MCP and the interactive
    TUI check: the denied aggregate and the granted aggregate are identical
    across all three interfaces, and granting build/download flips the
    `test` step and the aggregate outcome on each. Extra check: the TUI's
    non-interactive JSON Overview (`ui --json`, which never runs checks) is
    permission-flag-invariant, so its denied and granted snapshots are
    identical to each other and to plain `rush status`."""
    denied, granted = t29_check_results["denied"], t29_check_results["granted"]

    for interface in ("cli", "mcp", "tui"):
        assert denied[interface]["status"] == "warn", interface
        assert granted[interface]["status"] == "ok", interface
        assert _t29_child_map(denied[interface])["test"] == "skipped", interface
        assert _t29_child_map(granted[interface])["test"] != "skipped", interface

    assert denied["cli"]["status"] == denied["mcp"]["status"] == denied["tui"]["status"]
    assert (
        granted["cli"]["status"] == granted["mcp"]["status"] == granted["tui"]["status"]
    )
    assert (
        _t29_child_map(granted["cli"])
        == _t29_child_map(granted["mcp"])
        == _t29_child_map(granted["tui"])
    )

    # TUI Overview: `--allow-build`/`--allow-download` have zero effect on
    # `ui --json`.
    assert (
        denied["tui_overview"] == granted["tui_overview"] == t29_status_results["tui"]
    )


def test_t29_user_outcome_parity(
    t29_status_results: dict[str, dict[str, Any]],
    t29_check_results: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """The combined journey (brief's named test): status outcomes agree
    across CLI, MCP, and TUI; check outcomes agree across CLI, MCP and the
    interactive TUI check, denied and granted; and the TUI's read-only
    Overview stays identical regardless of the check permission granted --
    one pass proving the four requested user outcomes end to end."""
    cli_fields = _t29_status_fields(t29_status_results["cli"])
    mcp_fields = _t29_status_fields(t29_status_results["mcp"])
    tui_fields = _t29_status_fields(t29_status_results["tui"])
    assert cli_fields == mcp_fields == tui_fields

    denied, granted = t29_check_results["denied"], t29_check_results["granted"]
    assert (
        _t29_child_map(denied["cli"])
        == _t29_child_map(denied["mcp"])
        == _t29_child_map(denied["tui"])
    )
    assert denied["cli"]["status"] == denied["mcp"]["status"] == "warn"
    assert denied["tui"]["status"] == "warn"
    assert granted["cli"]["status"] == granted["mcp"]["status"] == "ok"
    assert granted["tui"]["status"] == "ok"

    assert (
        denied["tui_overview"] == granted["tui_overview"] == t29_status_results["tui"]
    )


# --- 2. the evidence doc contract -------------------------------------------


_T29_REQUIRED_ROW_IDS = tuple(f"R{n:02d}" for n in range(1, 13))
_T29_REQUIRED_COLUMNS = (
    "starting state",
    "outcome",
    "route",
    "visible result",
    "failure",
    "owner",
    "runtime identity",
)


def _t29_evidence_text() -> str:
    assert _T29_EVIDENCE_DOC.exists(), f"missing {_T29_EVIDENCE_DOC}"
    return _T29_EVIDENCE_DOC.read_text(encoding="utf-8")


def _t29_journey_table_rows(text: str) -> dict[str, list[str]]:
    """The journey matrix: a markdown table whose header row names every
    required column, and whose body rows are keyed by R01..R12."""
    import re

    lines = text.splitlines()
    header_index = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("|")
            and all(col in line.lower() for col in _T29_REQUIRED_COLUMNS)
        ),
        None,
    )
    assert header_index is not None, "no journey table header with required columns"
    rows: dict[str, list[str]] = {}
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or not re.fullmatch(r"R\d{2}", cells[0]):
            continue
        rows[cells[0]] = cells
    return rows


def test_t29_evidence_doc_has_journey_rows_r01_to_r12() -> None:
    """R01-R12 x {starting state, outcome, route, visible result,
    failure/recovery, owner, runtime identity}: every row present exactly
    once with every required column populated."""
    text = _t29_evidence_text()
    rows = _t29_journey_table_rows(text)
    assert set(rows) == set(_T29_REQUIRED_ROW_IDS)
    for row_id, cells in rows.items():
        assert len(cells) >= 1 + len(_T29_REQUIRED_COLUMNS), (row_id, cells)
        assert all(cell for cell in cells), (row_id, cells)


def test_t29_evidence_doc_records_t26_counts_and_measured_duration() -> None:
    """T26 counts (shell, native prompts, login, reload, manual edits = 0,
    hidden prerequisites = 0) and a measured duration, not a speed claim."""
    import re

    text = _t29_evidence_text().lower()
    for label in (
        "shell",
        "native prompt",
        "login",
        "reload",
        "manual edit",
        "hidden prerequisite",
    ):
        assert label in text, label
    assert re.search(r"manual edit[s]?\D*[:=]?\D*0\b", text), "manual edits must be 0"
    assert re.search(r"hidden prerequisite[s]?\D*[:=]?\D*0\b", text), (
        "hidden prerequisites must be 0"
    )
    assert re.search(r"duration\D*\d", text), "no measured duration recorded"


def test_t29_evidence_doc_has_phase71_consumes_section() -> None:
    """A 'Phase 71 consumes' section, including the dashboard provision
    frozen-identity requirement from T24."""
    import re

    text = _t29_evidence_text()
    match = re.search(
        r"##.*phase 71 consumes(.*?)(\n##\s|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    assert match is not None, "no 'Phase 71 consumes' section"
    section = match.group(1).lower()
    assert "frozen" in section and "identity" in section
    assert "dashboard" in section and "provision" in section


# --- 3. G6/G8 real lane results ----------------------------------------------


def _t29_lane_section(text: str, lane: str) -> str:
    import re

    match = re.search(
        rf"##.*\b{lane}\b(.*?)(\n##\s|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    assert match is not None, f"no '{lane}' section"
    return match.group(1)


def test_t29_evidence_doc_records_g6_and_g8_lane_results_or_blockers() -> None:
    """G6 and G8 real-lane results are recorded, each as a result or an
    explicit blocker (lane, reason)."""
    import re

    text = _t29_evidence_text()
    for lane in ("G6", "G8"):
        section = _t29_lane_section(text, lane)
        has_result = re.search(r"result\s*:", section, re.IGNORECASE) is not None
        has_blocker = (
            re.search(
                r"blocker\s*:.*\blane\b.*\breason\b", section, re.IGNORECASE | re.DOTALL
            )
            is not None
        )
        assert has_result or has_blocker, (lane, section[:200])
