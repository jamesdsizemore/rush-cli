"""Phase 62 P62.3 contract tests: the maintenance sub-agent (`run_maintenance_cycle`).

Covers T-62.05, T-62.06, T-62.21, T-62.22 (phase-62-memory-integration-layer-plan.md §7).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import rush.memory.maintenance as maintenance_module
import rush.tools.memory as memory_module
from rush.mcp_mesh.lock_manager import MeshLockManager
from rush.memory.maintenance import MaintenanceRunResult, run_maintenance_cycle
from rush.memory.retrieval import MemoryAccess
from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    legacy_owner_scope,
)
from rush.tools.memory import MemoryTool


def _nn[T](value: T | None) -> T:
    assert value is not None
    return value


_LOCK_PATH = Path(".rush/memory-maintenance.lock")


def _access(
    root: Path, sources: list[str], owner: OwnerScope | None = None
) -> MemoryAccess:
    """72-T04 (D9): the resolved write access every cycle now takes."""
    return MemoryAccess.legacy(
        root,
        sources,
        owner_scope=owner or legacy_owner_scope(root),
        operation="write",
    )


def test_maintenance_rejects_missing_lock_capability(tmp_path: Path) -> None:
    with (
        patch.object(MeshLockManager, "acquire", return_value=False),
        pytest.raises(
            RuntimeError, match="memory-maintenance: failed to acquire maintenance lock"
        ),
    ):
        run_maintenance_cycle(
            "promotion_sweep",
            project_root=tmp_path,
            access=_access(tmp_path, ["tool-0"]),
        )


def _seed_candidate_rows(root: Path, count: int) -> None:
    store = TypedArtifactStore(root)
    for i in range(count):
        store.write(
            MemoryArtifact(
                id=f"candidate-{i}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"note": i},
                source=f"tool-{i}",
                created_at=time.time() + i,
            )
        )


def test_maintenance_cycle_acquires_and_releases_lock(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.05: `run_maintenance_cycle()` calls `MeshLockManager.acquire`/`release` (spy),
    releasing even when the cycle body raises."""
    monkeypatch.chdir(tmp_path)
    original_acquire = MeshLockManager.acquire
    original_release = MeshLockManager.release
    with (
        patch.object(MeshLockManager, "acquire", autospec=True) as spy_acquire,
        patch.object(MeshLockManager, "release", autospec=True) as spy_release,
    ):
        spy_acquire.side_effect = original_acquire
        spy_release.side_effect = original_release

        access = _access(tmp_path, ["tool"])
        result = run_maintenance_cycle("promotion_sweep", access=access)
        assert isinstance(result, MaintenanceRunResult)
        assert spy_acquire.call_count == 1
        assert spy_release.call_count == 1

        # 72-T04 (D9): an unrecognized task is a `ValueError` before any lease.
        with pytest.raises(ValueError):
            run_maintenance_cycle(
                "not_a_real_task",  # type: ignore[arg-type]
                access=access,
            )
        assert spy_acquire.call_count == 1
        assert spy_release.call_count == 1

        # A body that raises inside the lease (the access recheck after the lease)
        # still releases it -- T-62.05's actual intent.
        with (
            patch.object(
                maintenance_module, "recheck_failure", side_effect=RuntimeError("boom")
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            run_maintenance_cycle("promotion_sweep", access=access)
        assert spy_acquire.call_count == 2
        assert spy_release.call_count == 2


def test_maintenance_cycle_respects_batch_size_parameter(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.06: 600 candidate rows seeded; `batch_size=500` processes exactly 500, and a
    separate `batch_size=50` call processes exactly 50 — proving a real parameter, not a
    hardcoded constant."""
    # 500 per-row transactions must fit one policy-lock hold (D9).
    monkeypatch.setattr(maintenance_module, "POLICY_LOCK_HOLD_BUDGET_S", 120.0)
    sources = [f"tool-{i}" for i in range(600)]
    root_500 = tmp_path / "run-500"
    root_500.mkdir()
    monkeypatch.chdir(root_500)
    _seed_candidate_rows(root_500, 600)
    result_500 = run_maintenance_cycle(
        "promotion_sweep", batch_size=500, access=_access(root_500, sources)
    )
    assert result_500.processed == 500

    root_50 = tmp_path / "run-50"
    root_50.mkdir()
    monkeypatch.chdir(root_50)
    _seed_candidate_rows(root_50, 600)
    result_50 = run_maintenance_cycle(
        "promotion_sweep", batch_size=50, access=_access(root_50, sources)
    )
    assert result_50.processed == 50


def test_maintenance_sweep_never_touches_a_different_owners_rows(
    tmp_path: Path, monkeypatch
) -> None:
    """P69-07 subsection h: a sweep scoped to one owner never touches another owner's
    rows in the same project store, and omitting `owner_scope` defaults to this
    project's own legacy owner rather than a wildcard sweep."""
    monkeypatch.chdir(tmp_path)
    store = TypedArtifactStore(tmp_path)
    project_owned = MemoryArtifact(
        id="project-owned",
        family="memory",
        subject="domain_knowledge",
        trust_tier="DERIVED",
        content={"note": "default owner"},
        source="tool",
        created_at=time.time(),
    )
    store.write(project_owned)
    user_owned = MemoryArtifact(
        id="user-owned",
        family="memory",
        subject="domain_knowledge",
        trust_tier="DERIVED",
        content={"note": "user owner"},
        source="tool",
        created_at=time.time(),
        owner_scope=OwnerScope("user", "u-1"),
    )
    store.write(user_owned)

    result = run_maintenance_cycle(
        "promotion_sweep",
        access=_access(tmp_path, ["tool"], OwnerScope("user", "u-1")),
    )
    assert result.processed == 1
    assert result.errors == ()

    # M09: owner_scope is required (no silent default) -- the project-owned row
    # is reached only by explicitly passing this project's own legacy owner.
    default_result = run_maintenance_cycle(
        "promotion_sweep", access=_access(tmp_path, ["tool"])
    )
    assert default_result.processed == 1


def test_expired_lease_reclaimed_by_second_cycle_survives_first_cycles_stale_release(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.21: cycle A's lease expires mid-run; cycle B reclaims the lock (new generation,
    same fixed `agent_id`); cycle A's stale `release()` (via its now-stale capability) must
    return `False` and must not delete cycle B's live lock."""
    monkeypatch.chdir(tmp_path)
    mgr = MeshLockManager()

    acquired_a, cap_a = mgr.acquire(  # type: ignore[misc]
        _LOCK_PATH,
        agent_id="memory-maintenance",
        timeout_s=1.0,
        ttl_s=0.05,
        return_capability=True,
    )
    assert acquired_a is True
    assert cap_a is not None
    generation_a = MeshLockManager.inspect(tmp_path, _LOCK_PATH)["generation"]

    time.sleep(0.15)  # let cycle A's lease expire

    acquired_b, cap_b = mgr.acquire(  # type: ignore[misc]
        _LOCK_PATH,
        agent_id="memory-maintenance",
        timeout_s=1.0,
        ttl_s=60.0,
        return_capability=True,
    )
    assert acquired_b is True
    assert cap_b is not None

    state_before = MeshLockManager.inspect(tmp_path, _LOCK_PATH)
    assert state_before["state"] == "held"
    generation_b: Any = state_before["generation"]
    assert generation_b > generation_a

    # Cycle A's cleanup runs against its now-stale capability.
    assert mgr.release(_LOCK_PATH, capability=cap_a) is False

    state_after = MeshLockManager.inspect(tmp_path, _LOCK_PATH)
    assert state_after["state"] == "held"
    assert state_after["generation"] == generation_b


def test_memory_tool_maintain_operation_dispatches_to_run_maintenance_cycle(
    tmp_path: Path, monkeypatch
) -> None:
    """T-62.22: `MemoryTool()(operation="maintain", task="promotion_sweep")` dispatches to
    `run_maintenance_cycle(task="promotion_sweep")`, via the registered "maintain" operation
    (not only reachable by directly importing `run_maintenance_cycle` in a test)."""
    monkeypatch.chdir(tmp_path)
    stub_result = MaintenanceRunResult(
        task="promotion_sweep", processed=0, changed=0, errors=()
    )
    owner = legacy_owner_scope(tmp_path)
    with patch.object(memory_module, "run_maintenance_cycle") as spy:
        spy.return_value = stub_result
        result = MemoryTool()(
            tmp_path,
            operation="maintain",
            task="promotion_sweep",
            allow_cache_write=True,
            owner_scope=owner,
            sources=["tool"],
        )

    # 72-T04 (D3/D9): `legacy` mode builds the explicit-source write access; the
    # reviewed-set restriction keywords stay absent on an unrestricted call.
    spy.assert_called_once()
    assert spy.call_args.args == ("promotion_sweep",)
    kwargs = spy.call_args.kwargs
    assert kwargs["batch_size"] == 500
    assert kwargs["project_root"] == tmp_path.resolve()
    assert kwargs["access"] == MemoryAccess.legacy(
        tmp_path.resolve(), ["tool"], owner_scope=owner, operation="write"
    )
    assert not set(kwargs) - {
        "access",
        "batch_size",
        "project_root",
        "candidate_ids",
        "expected_revisions",
        "data_root",
    }
    assert kwargs.get("candidate_ids") is None
    assert kwargs.get("expected_revisions") is None
    assert result["status"] == "ok"
    assert _nn(result["metadata"])["operation"] == "maintain"
