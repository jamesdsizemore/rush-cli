"""T28-D (Phase 70 plan lines 384-394): failing backend tests for the `MemoryTool`
behavior the TUI's Memory action needs -- reviewable filtered listing, a real
apply=False preview for write/promote/maintain, apply restricted to a previewed
candidate set, and `required_grants` pinned at review time and enforced at apply.

Every test here runs against a real `TypedArtifactStore` in a `tmp_path` project
(HOME isolated by tests/conftest.py's autouse fixture) and fails today for the
reason recorded in its docstring. No source code is changed by this file.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from rush.memory.store import MemoryArtifact, TypedArtifactStore, legacy_owner_scope
from rush.permissions import ExecutionPermissions
from rush.plugins.trust_store import PluginTrustStore
from rush.tools.memory import MemoryTool

_WRITE = ExecutionPermissions(cache_write=True)
_DAY = 86400.0


def _db_path(root: Path) -> Path:
    return root / ".rush" / "memory.db"


def _db_bytes(root: Path) -> bytes | None:
    path = _db_path(root)
    return path.read_bytes() if path.exists() else None


def _owner_kwarg(root: Path) -> dict[str, dict[str, str]]:
    owner = legacy_owner_scope(root)
    return {"owner_scope": {"kind": owner.kind, "id": owner.id}}


def _seed_row(
    root: Path,
    *,
    artifact_id: str = "a1",
    subject: str = "domain_knowledge",
    family: str = "memory",
    trust_tier: str = "DERIVED",
    source: str = "s1",
    content: dict | None = None,
    created_at: float | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
    stale: bool = False,
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
        subject = (
            "skill_pattern" if task == "skill_admission_check" else "domain_knowledge"
        )
        family = "skill" if task == "skill_admission_check" else "memory"
        for i, aid in enumerate(artifact_ids):
            content = (
                {"plugin_name": "demo-plugin", "closure_digest": "abc123"}
                if task == "skill_admission_check"
                else {"body": aid}
            )
            # Every row shares (subject, symbol_ref=None) so corroboration counting sees
            # them all as one candidate pool.
            _seed_row(
                root,
                artifact_id=aid,
                subject=subject,
                family=family,
                trust_tier="DERIVED",
                source=f"src-{aid}",
                content=content,
                created_at=time.time() - (len(artifact_ids) - i) * 10,
            )
        if len(artifact_ids) > 1 and task == "promotion_sweep":
            # Two extra corroborating rows created *after* both candidates, so each
            # candidate is evaluated (created_at ASC) while the pool still has >= 2
            # distinct non-STATED sources -- both promote in a real, unrestricted sweep,
            # regardless of candidate_ids.
            for j in range(2):
                _seed_row(
                    root,
                    artifact_id=f"{task}-helper{j}",
                    subject=subject,
                    family=family,
                    trust_tier="DERIVED",
                    source=f"helper-src-{j}",
                    content={"body": f"helper-{j}"},
                    created_at=time.time(),
                )
        if len(artifact_ids) > 1 and task == "skill_admission_check":
            # Two extra rows in the same corroboration pool that are never granted
            # trust, so they never promote and permanently corroborate both candidates
            # (>= 2 distinct sources) regardless of processing order.
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

    returned_ids = {item["id"] for item in result["raw"]}
    assert returned_ids == {fresh_reviewed.id}
    assert stale_derived.id not in returned_ids
    assert archived_reviewed.id not in returned_ids


@pytest.mark.parametrize("operation", ["write", "promote", "maintain"])
def test_promote_write_maintain_preview_writes_nothing(
    tmp_path: Path, operation: str
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
        )
        data = result["raw"]
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
        data = result["raw"]
        assert {
            "target_ids",
            "expected_revisions",
            "owner_scope",
            "required_grants",
        } <= set(data), (
            f"{operation} preview must return target ids/expected revisions/owner_scope/required_grants"
        )

    after = _db_bytes(tmp_path)
    assert after == before, f"{operation}: apply=False must never write"


@pytest.mark.parametrize(
    "task",
    ["promotion_sweep", "staleness_sweep", "skill_admission_check", "expiry_sweep"],
)
def test_maintain_apply_restricted_to_previewed_candidate_ids(
    tmp_path: Path, task: str
) -> None:
    """`run_maintenance_cycle` (maintenance.py) has no candidate_ids parameter and
    `_run_maintain` never threads `request` into it, so a candidate_ids restriction is
    silently ignored and every eligible row changes -- fails today because the
    non-candidate row changes too."""
    ids = ["cand1", "cand2"]
    _seed_eligible_rows(tmp_path, task, ids)
    if task == "skill_admission_check":
        PluginTrustStore(repo_root=tmp_path).grant_trust("demo-plugin", "abc123")

    MemoryTool().run(
        tmp_path,
        operation="maintain",
        task=task,
        request={"apply": True, "candidate_ids": [ids[0]]},
        permissions=_WRITE,
        **_owner_kwarg(tmp_path),
    )

    assert _row_changed(tmp_path, task, ids[0]) is True, (
        f"{task}: previewed candidate must change"
    )
    assert _row_changed(tmp_path, task, ids[1]) is False, (
        f"{task}: apply must be restricted to previewed candidate_ids"
    )


def _invoke_reviewed(
    tmp_path: Path,
    operation: str,
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
        data = result["raw"]["data"]
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
        data = result["raw"]
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
        )
        after = _db_bytes(tmp_path)
        data = result["raw"]
    return result, data, before, after


@pytest.mark.parametrize(
    "operation", ["edit", "archive", "delete", "promote", "write", "maintain"]
)
def test_requests_accept_reviewed_required_grants(
    tmp_path: Path, operation: str
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
    tmp_path: Path, operation: str
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
def test_maintenance_candidate_preview_is_zero_write(tmp_path: Path, task: str) -> None:
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
    )
    assert not (empty_root / ".rush").exists(), (
        f"{task}: preview on a project with no memory.db must create no DB, -wal, "
        "-shm, or .rush"
    )

    populated_root = tmp_path / "populated"
    populated_root.mkdir()
    _seed_eligible_rows(populated_root, task, ["p1"])
    if task == "skill_admission_check":
        PluginTrustStore(repo_root=populated_root).grant_trust("demo-plugin", "abc123")
    before = _db_bytes(populated_root)
    tool.run(
        populated_root,
        operation="maintain",
        task=task,
        request={"apply": False},
        permissions=_WRITE,
        **_owner_kwarg(populated_root),
    )
    after = _db_bytes(populated_root)
    assert after == before, (
        f"{task}: preview on a populated store must leave its bytes unchanged"
    )
