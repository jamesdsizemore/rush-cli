"""T28-D (Phase 70 plan lines 384-394): failing backend tests for the `MemoryTool`
behavior the TUI's Memory action needs -- reviewable filtered listing, a real
apply=False preview for write/promote/maintain, apply restricted to a previewed
candidate set, and `required_grants` pinned at review time and enforced at apply.

Every test here runs against a real `TypedArtifactStore` in a `tmp_path` project
(HOME isolated by tests/conftest.py's autouse fixture) and fails today for the
reason recorded in its docstring. No source code is changed by this file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from rush.memory.maintenance import MaintenanceTask
from rush.memory.retrieval import MemoryAccess
from rush.memory.store import (
    MemoryArtifact,
    MemoryFamily,
    MemorySubject,
    TrustTier,
    TypedArtifactStore,
    legacy_owner_scope,
)
from rush.permissions import ExecutionPermissions
from rush.plugins.trust_store import PluginTrustStore
from rush.tools.memory import MemoryOperation, MemoryTool


def _nn[T](value: T | None) -> T:
    assert value is not None
    return value


_WRITE = ExecutionPermissions(cache_write=True)
_DAY = 86400.0
# 72-T04 (D9): a skill row's `closure_digest` is admitted only as a 64-hex digest.
_DIGEST = hashlib.sha256(b"demo-closure").hexdigest()


def _raw(result: Mapping[str, Any]) -> Any:
    raw = result["raw"]
    assert raw is not None
    return raw


def _db_path(root: Path) -> Path:
    return root / ".rush" / "memory.db"


def _db_bytes(root: Path) -> bytes | None:
    path = _db_path(root)
    return path.read_bytes() if path.exists() else None


def _owner_kwarg(root: Path) -> dict[str, Any]:
    owner = legacy_owner_scope(root)
    return {"owner_scope": {"kind": owner.kind, "id": owner.id}}


def _db_sources(root: Path, default: tuple[str, ...] = ("s1",)) -> list[str]:
    """Every source label stored in the project's memory.db (or `default` when there
    is no DB): the explicit source list 72-T04's `legacy` mode requires (D3)."""
    path = _db_path(root)
    if not path.exists():
        return list(default)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT DISTINCT source FROM memory_artifacts").fetchall()
    return sorted(str(r[0]) for r in rows) or list(default)


def _sources_kwarg(root: Path) -> dict[str, Any]:
    return {"sources": _db_sources(root)}


def _legacy_access(root: Path, operation: str) -> MemoryAccess:
    return MemoryAccess.legacy(
        root,
        _db_sources(root),
        owner_scope=legacy_owner_scope(root),
        operation=operation,
    )


def _seed_row(
    root: Path,
    *,
    artifact_id: str = "a1",
    subject: MemorySubject = "domain_knowledge",
    family: MemoryFamily = "memory",
    trust_tier: TrustTier = "DERIVED",
    source: str = "s1",
    content: dict | None = None,
    created_at: float | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
    stale: bool = False,
    origin: tuple[str, str] | None = None,
) -> MemoryArtifact:
    store = TypedArtifactStore(root)
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family=family,
            subject=subject,
            trust_tier=trust_tier,
            content=content if content is not None else {"body": artifact_id},
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            stale=stale,
            origin_kind=origin[0] if origin else None,
            origin_id=origin[1] if origin else None,
        )
    )


def _seed_eligible_rows(root: Path, task: str, artifact_ids: list[str]) -> None:
    """Seeds `len(artifact_ids)` rows that a real (non-preview) run of `task` would
    each mutate -- so a candidate_ids restriction that is silently ignored is
    observable as *both* rows changing instead of only the previewed one."""
    if task == "expiry_sweep":
        old = (
            time.time() - 15 * _DAY
        )  # DERIVED ttl is 14 days (expiry.py DEFAULT_POLICIES)
        for aid in artifact_ids:
            _seed_row(
                root,
                artifact_id=aid,
                trust_tier="DERIVED",
                source=f"src-{aid}",
                created_at=old,
            )
    elif task == "staleness_sweep":
        for aid in artifact_ids:
            _seed_row(
                root,
                artifact_id=aid,
                trust_tier="DERIVED",
                source=f"src-{aid}",
                symbol_ref="does/not/exist.py::Sym",
                content_hash="deadbeef",
                stale=False,
            )
    elif task in ("promotion_sweep", "skill_admission_check"):
        subject: MemorySubject = (
            "skill_pattern" if task == "skill_admission_check" else "domain_knowledge"
        )
        family: MemoryFamily = "skill" if task == "skill_admission_check" else "memory"
        for i, aid in enumerate(artifact_ids):
            # 72-T04 (D8): corroboration is equal stored content from distinct
            # sources with distinct non-null `(origin_kind, origin_id)` pairs.
            content = (
                {"plugin_name": "demo-plugin", "closure_digest": _DIGEST}
                if task == "skill_admission_check"
                else {"body": "shared"}
            )
            _seed_row(
                root,
                artifact_id=aid,
                subject=subject,
                family=family,
                trust_tier="DERIVED",
                source=f"src-{aid}",
                content=content,
                created_at=time.time() - (len(artifact_ids) - i) * 10,
                origin=("agent", f"origin-{aid}"),
            )
        if len(artifact_ids) > 1 and task == "promotion_sweep":
            # Two extra corroborating rows created *after* both candidates, so each
            # candidate is evaluated (created_at ASC) while the pool still has >= 2
            # distinct independent sources -- both promote in a real, unrestricted
            # sweep, regardless of candidate_ids.
            for j in range(2):
                _seed_row(
                    root,
                    artifact_id=f"{task}-helper{j}",
                    subject=subject,
                    family=family,
                    trust_tier="DERIVED",
                    source=f"helper-src-{j}",
                    content={"body": "shared"},
                    created_at=time.time(),
                    origin=("agent", f"origin-helper{j}"),
                )
        if len(artifact_ids) > 1 and task == "skill_admission_check":
            # Two extra rows that are never granted trust, so they never promote.
            for j in range(2):
                _seed_row(
                    root,
                    artifact_id=f"{task}-helper{j}",
                    subject=subject,
                    family=family,
                    trust_tier="DERIVED",
                    source=f"helper-src-{j}",
                    content={
                        "plugin_name": "untrusted-plugin",
                        "closure_digest": "nope",
                    },
                )
    else:
        raise ValueError(f"no seeding recipe for task {task!r}")


def _row_changed(root: Path, task: str, artifact_id: str) -> bool:
    conn = sqlite3.connect(str(_db_path(root)))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT expires_at, stale, promoted_at FROM memory_artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    if task == "expiry_sweep":
        return row["expires_at"] is not None
    if task == "staleness_sweep":
        return bool(row["stale"])
    return row["promoted_at"] is not None


def test_memory_list_filters_trust_source_freshness_archived(tmp_path: Path) -> None:
    """MemoryTool.run has no trust_filter/source_filter/freshness_filter/archived_filter
    keyword today (memory.py:368-401's `run` signature) -- fails today with a TypeError
    for the unknown keyword before any of the seeded rows below are ever inspected."""
    # write() only accepts non-STATED trust tiers directly (promotion is the only path
    # to STATED, store.py:2094's TrustTierError) -- EXTERNAL_WRITE stands in as the
    # "reviewed" tier here.
    fresh_reviewed = _seed_row(
        tmp_path,
        artifact_id="fresh-reviewed",
        trust_tier="EXTERNAL_WRITE",
        source="alice",
        stale=False,
    )
    stale_derived = _seed_row(
        tmp_path,
        artifact_id="stale-derived",
        trust_tier="DERIVED",
        source="bob",
        stale=True,
    )
    archived_reviewed = _seed_row(
        tmp_path,
        artifact_id="archived-reviewed",
        trust_tier="EXTERNAL_WRITE",
        source="alice",
        stale=False,
    )
    store = TypedArtifactStore(tmp_path)
    store.archive(
        archived_reviewed.id,
        expected_version=archived_reviewed.artifact_version,
        scope="domain_knowledge",
        apply=True,
    )

    result = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        session_allowlist=["s1"],
        trust_filter="EXTERNAL_WRITE",
        source_filter="alice",
        freshness_filter="fresh",
        archived_filter=False,
    )

    returned_ids = {item["id"] for item in _raw(result)}
    assert returned_ids == {fresh_reviewed.id}
    assert stale_derived.id not in returned_ids
    assert archived_reviewed.id not in returned_ids


def test_memory_list_trust_filter_keeps_only_the_named_tier(tmp_path: Path) -> None:
    """G6 guard for the trust filter: two live, fresh rows of one source differ only
    in trust tier, so only the trust filter can separate them."""
    reviewed = _seed_row(
        tmp_path,
        artifact_id="same-reviewed",
        trust_tier="EXTERNAL_WRITE",
        source="alice",
    )
    derived = _seed_row(
        tmp_path, artifact_id="same-derived", trust_tier="DERIVED", source="alice"
    )

    def listed(**filters: Any) -> set[str]:
        result = MemoryTool().run(
            tmp_path,
            operation="list",
            subject="domain_knowledge",
            session_allowlist=["s1"],
            source_filter="alice",
            **filters,
        )
        return {item["id"] for item in _raw(result)}

    assert listed() == {reviewed.id, derived.id}
    assert listed(trust_filter="EXTERNAL_WRITE") == {reviewed.id}
    assert listed(trust_filter="DERIVED") == {derived.id}


@pytest.mark.parametrize("operation", ["write", "promote", "maintain"])
def test_promote_write_maintain_preview_writes_nothing(
    tmp_path: Path, operation: MemoryOperation
) -> None:
    """`_run_write`/`_run_promote`/`_run_maintain` (memory.py:499-526, :1173-1340) never
    receive `request` at all from the dispatch table, so `apply=False` is silently
    ignored and the operation writes for real -- fails today because DB bytes change
    and no preview shape (target ids/expected revisions/owner_scope/required_grants;
    candidate_ids for maintain) is returned."""
    if operation == "maintain":
        _seed_eligible_rows(tmp_path, "expiry_sweep", ["m1"])
    before = _db_bytes(tmp_path)

    tool = MemoryTool()
    request = {"apply": False, "required_grants": ["cache_write"]}
    if operation == "maintain":
        result = tool.run(
            tmp_path,
            operation="maintain",
            task="expiry_sweep",
            request=request,
            permissions=_WRITE,
            **_owner_kwarg(tmp_path),
            **_sources_kwarg(tmp_path),
        )
        data = _raw(result)
        assert "candidate_ids" in data, "maintain preview must return candidate_ids"
    else:
        result = tool.run(
            tmp_path,
            operation=operation,
            subject="domain_knowledge",
            content={"body": "new"},
            source="s2",
            request=request,
            permissions=_WRITE,
            **_owner_kwarg(tmp_path),
        )
        data = _raw(result)
        assert {
            "target_ids",
            "expected_revisions",
            "owner_scope",
            "required_grants",
        } <= set(_nn(data)), (
            f"{operation} preview must return target ids/expected revisions/owner_scope/required_grants"
        )

    after = _db_bytes(tmp_path)
    assert after == before, f"{operation}: apply=False must never write"


@pytest.mark.parametrize(
    "task",
    ["promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"],
)
def test_maintain_apply_restricted_to_previewed_candidate_ids(
    tmp_path: Path, task: MaintenanceTask
) -> None:
    """`run_maintenance_cycle` (maintenance.py) has no candidate_ids parameter and
    `_run_maintain` never threads `request` into it, so a candidate_ids restriction is
    silently ignored and every eligible row changes -- fails today because the
    non-candidate row changes too."""
    ids = ["cand1", "cand2"]
    _seed_eligible_rows(tmp_path, task, ids)
    if task == "skill_admission_check":
        PluginTrustStore(repo_root=tmp_path).grant_trust("demo-plugin", _DIGEST)

    MemoryTool().run(
        tmp_path,
        operation="maintain",
        task=task,
        request={"apply": True, "candidate_ids": [ids[0]]},
        permissions=_WRITE,
        **_owner_kwarg(tmp_path),
        **_sources_kwarg(tmp_path),
    )

    assert _row_changed(tmp_path, task, ids[0]) is True, (
        f"{task}: previewed candidate must change"
    )
    assert _row_changed(tmp_path, task, ids[1]) is False, (
        f"{task}: apply must be restricted to previewed candidate_ids"
    )


def _invoke_reviewed(
    tmp_path: Path,
    operation: MemoryOperation,
    *,
    apply: bool,
    required_grants: list[str],
    permissions,
):
    tool = MemoryTool()
    if operation in ("edit", "archive", "delete"):
        artifact = _seed_row(tmp_path)
        if operation == "delete":
            request = {
                "artifact_ids": [artifact.id],
                "expected_revisions": {artifact.id: artifact.artifact_version},
                "scope": artifact.subject,
                "apply": apply,
                "required_grants": required_grants,
            }
        else:
            request = {
                "scope": artifact.subject,
                "id": artifact.id,
                "expected_version": artifact.artifact_version,
                "apply": apply,
                "required_grants": required_grants,
            }
            if operation == "edit":
                request["content"] = {"body": "edited"}
        before = _db_bytes(tmp_path)
        result = tool.run(
            tmp_path, operation=operation, request=request, permissions=permissions
        )
        after = _db_bytes(tmp_path)
        data = _raw(result)["data"]
    elif operation in ("write", "promote"):
        before = _db_bytes(tmp_path)
        request = {"apply": apply, "required_grants": required_grants}
        result = tool.run(
            tmp_path,
            operation=operation,
            subject="domain_knowledge",
            content={"body": "new"},
            source="s2",
            request=request,
            permissions=permissions,
            **_owner_kwarg(tmp_path),
        )
        after = _db_bytes(tmp_path)
        data = _raw(result)
    else:  # maintain
        _seed_eligible_rows(tmp_path, "expiry_sweep", ["m1"])
        before = _db_bytes(tmp_path)
        request = {"apply": apply, "required_grants": required_grants}
        result = tool.run(
            tmp_path,
            operation="maintain",
            task="expiry_sweep",
            request=request,
            permissions=permissions,
            **_owner_kwarg(tmp_path),
            **_sources_kwarg(tmp_path),
        )
        after = _db_bytes(tmp_path)
        data = _raw(result)
    return result, data, before, after


@pytest.mark.parametrize(
    "operation", ["edit", "archive", "delete", "promote", "write", "maintain"]
)
def test_requests_accept_reviewed_required_grants(
    tmp_path: Path, operation: MemoryOperation
) -> None:
    """No request-gated operation has a `required_grants` field today (edit/archive's
    `_EDIT_REQUEST_KEYS`/`_ARCHIVE_REQUEST_KEYS`, delete's `_DELETE_REQUEST_KEYS` at
    memory.py:2310-2317 all reject it as unknown; write/promote/maintain never see
    `request` at all) -- fails today because the reviewed grants are never echoed back."""
    _result, data, _before, _after = _invoke_reviewed(
        tmp_path,
        operation,
        apply=False,
        required_grants=["cache_write"],
        permissions=_WRITE,
    )
    assert "required_grants" in data, (
        f"{operation}: a request's reviewed required_grants must be echoed back, not dropped"
    )


@pytest.mark.parametrize(
    "operation", ["edit", "archive", "delete", "promote", "write", "maintain"]
)
def test_apply_refused_when_permissions_differ_from_reviewed_grants(
    tmp_path: Path, operation: MemoryOperation
) -> None:
    """Only the coarse cache_write gate is enforced today; a request's own
    required_grants is never checked against the call's actual permissions, so apply
    proceeds and writes even though a reviewed grant (artifact_write) is missing --
    fails today both on the no-write assertion and on the missing-grant message."""
    permissions = ExecutionPermissions(cache_write=True)  # artifact_write withheld
    result, data, before, after = _invoke_reviewed(
        tmp_path,
        operation,
        apply=True,
        required_grants=["cache_write", "artifact_write"],
        permissions=permissions,
    )
    assert before == after, (
        f"{operation}: apply must be refused when permissions differ from the "
        "reviewed required_grants"
    )
    message = str(data.get("message", "")) + str(result.get("summary", ""))
    assert "artifact_write" in message, (
        f"{operation}: error must name the missing grant"
    )


@pytest.mark.parametrize(
    "task",
    ["promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"],
)
def test_maintenance_candidate_preview_is_zero_write(
    tmp_path: Path, task: MaintenanceTask
) -> None:
    """`run_maintenance_cycle` (maintenance.py) always constructs a writable
    `TypedArtifactStore`/connects to the real DB regardless of apply, and `_run_maintain`
    never threads apply=False into it -- fails today because a preview on a brand-new
    project still creates `.rush/`, and a preview on a populated store still mutates it."""
    tool = MemoryTool()

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    tool.run(
        empty_root,
        operation="maintain",
        task=task,
        request={"apply": False},
        permissions=_WRITE,
        **_owner_kwarg(empty_root),
        **_sources_kwarg(empty_root),
    )
    assert not (empty_root / ".rush").exists(), (
        f"{task}: preview on a project with no memory.db must create no DB, -wal, "
        "-shm, or .rush"
    )

    populated_root = tmp_path / "populated"
    populated_root.mkdir()
    _seed_eligible_rows(populated_root, task, ["p1"])
    if task == "skill_admission_check":
        PluginTrustStore(repo_root=populated_root).grant_trust("demo-plugin", _DIGEST)
    before = _db_bytes(populated_root)
    tool.run(
        populated_root,
        operation="maintain",
        task=task,
        request={"apply": False},
        permissions=_WRITE,
        **_owner_kwarg(populated_root),
        **_sources_kwarg(populated_root),
    )
    after = _db_bytes(populated_root)
    assert after == before, (
        f"{task}: preview on a populated store must leave its bytes unchanged"
    )


def _edit_to_v2(root: Path, artifact_id: str, content: dict) -> None:
    """The concurrent edit: a real CAS edit through the store, v1 -> v2."""
    store = TypedArtifactStore(root)
    current = store.get_current(artifact_id)
    assert current is not None
    store.edit(
        artifact_id, content, expected_version=1, scope=current.subject, apply=True
    )


def _current_row(root: Path, artifact_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(str(_db_path(root)))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT artifact_version, content, expired_at FROM memory_artifacts "
            "WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


def _run_after_passed_precheck(
    root: Path,
    task: MaintenanceTask,
    artifact_id: str,
    v2_content: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Reviews `artifact_id` at v1, lands a v2 edit, then runs the cycle as if the
    lease-time pre-check had already passed before the edit committed -- only a
    version check inside the write transaction itself can refuse the row now."""
    from rush.memory import maintenance

    preview = maintenance.preview_maintenance_candidates(
        task,
        project_root=root,
        access=_legacy_access(root, "list"),
        candidate_ids=[artifact_id],
    )
    reviewed = {str(c["id"]): int(str(c["artifact_version"])) for c in preview}
    assert reviewed == {artifact_id: 1}
    _edit_to_v2(root, artifact_id, v2_content)
    monkeypatch.setattr(
        maintenance, "_revision_conflicts", lambda _conn, _exp, **_kw: ()
    )
    return maintenance.run_maintenance_cycle(
        task,
        project_root=root,
        access=_legacy_access(root, "write"),
        expected_revisions=reviewed,
    )


def test_maintain_refuses_a_row_edited_after_the_check_inside_the_write_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sweep_expired` stamps whatever candidate rows exist inside its own BEGIN
    IMMEDIATE, never re-checking the reviewed version -- an edit that commits between
    the lease-time pre-check and the sweep is expired unreviewed."""
    from rush.memory.maintenance import RevisionConflict

    _seed_eligible_rows(tmp_path, "expiry_sweep", ["x1"])
    v2 = {"body": "edited-v2"}

    result = _run_after_passed_precheck(tmp_path, "expiry_sweep", "x1", v2, monkeypatch)

    row = _current_row(tmp_path, "x1")
    assert row["artifact_version"] == 2
    assert json.loads(row["content"]) == v2
    assert row["expired_at"] is None
    assert _row_changed(tmp_path, "expiry_sweep", "x1") is False
    assert result.changed == 0
    assert result.refused == (RevisionConflict("x1", 1, 2),)


@pytest.mark.parametrize(
    "task", ["promotion_sweep", "staleness_sweep", "skill_admission_check"]
)
def test_per_row_maintain_refuses_a_row_edited_after_the_check(
    tmp_path: Path, task: MaintenanceTask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-row tasks mutate from `_select_rows`' snapshot without re-checking
    the reviewed version inside the row's own write transaction -- an edit that
    commits after the pre-check is promoted/staled unreviewed."""
    from rush.memory.maintenance import RevisionConflict

    _seed_eligible_rows(tmp_path, task, ["r1", "r2"])
    if task == "skill_admission_check":
        PluginTrustStore(repo_root=tmp_path).grant_trust("demo-plugin", _DIGEST)
        v2: dict = {
            "plugin_name": "demo-plugin",
            "closure_digest": _DIGEST,
            "note": "edited-v2",
        }
    else:
        v2 = {"body": "edited-v2"}

    result = _run_after_passed_precheck(tmp_path, task, "r1", v2, monkeypatch)

    row = _current_row(tmp_path, "r1")
    assert row["artifact_version"] == 2
    assert json.loads(row["content"]) == v2
    assert _row_changed(tmp_path, task, "r1") is False
    assert _row_changed(tmp_path, task, "r2") is False
    assert result.changed == 0
    assert result.refused == (RevisionConflict("r1", 1, 2),)
