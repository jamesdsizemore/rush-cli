"""Tests for Phase 65 P65-06.1/.2: bounded agent handoff (F35).

Fixture manifests are written directly against the real, documented
`project_run` manifest schema (`{"aggregate": {"findings": [...]}, "scheduled":
[...]}`, produced by `execute_scan`/`_build_manifest`) rather than re-deriving
real tool execution -- `build_handoff`'s contract is "given a persisted run
manifest, prepare a bounded handoff", already independent of how that
manifest's findings were produced (covered by `test_full_project_scan.py`).
`test_prepare_dispatch_acknowledge_complete_round_trip` additionally proves
the whole lifecycle against a *real* `plan_scan`/`execute_scan` run so the
manifest-schema fixtures below are never the only path exercised.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.review import ReviewTool
from rush.tools.scan_handoff import ScanHandoffTool
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanHandoffAuthError,
    ScanHandoffInvalidStateError,
    ScanHandoffSourceChangedError,
    ScanInvalidRequestError,
    acknowledge_handoff,
    build_handoff,
    complete_handoff,
    dispatch_handoff,
    execute_scan,
    plan_scan,
    recover_prepared_handoff,
    status_handoff,
)
from rush.workflows.projects import register_project

pytestmark = pytest.mark.usefixtures("hermetic_engine_path")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    return root


def _register(tmp_path: Path) -> tuple[str, Path]:
    root = _fixture_root(tmp_path)
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    return record.project_id, data_root


def _finding(
    finding_id: str,
    *,
    tool: str = "review",
    engine: str | None = "no-engine",
    message: str = "issue",
    severity: str = "warn",
    path: str = "app.py",
    line: int = 1,
    column: int = 0,
    rule: str = "seeded-rule",
) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "path": path,
        "line": line,
        "column": column,
        "rule": rule,
        "severity": severity,
        "message": message,
        "provenance": f"{tool}/{engine or 'no-engine'}",
    }


def _write_manifest(
    root: Path,
    run_id: str,
    *,
    findings: list[dict[str, object]],
    scheduled: list[dict[str, object]] | None = None,
    plan_id: str = "fixture-plan",
) -> None:
    manifest_dir = root / ".rush" / "runs" / run_id / "attempts" / "attempt-1"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": "attempt-1",
        "plan_id": plan_id,
        "run_state": "completed",
        "aggregate": {"findings": findings},
        "scheduled": scheduled or [],
        "totals": {"finding_count": len(findings)},
    }
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def test_prepare_dispatch_acknowledge_complete_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool()])
    project_id, data_root = _register(tmp_path)
    plan = plan_scan(project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    handoff = build_handoff(project_id, run.run_id, "codex-cli", data_root=data_root)
    assert handoff.state == "prepared"
    assert handoff.finding_ids, "expected at least one seeded finding"

    dispatched = dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )
    assert dispatched.state == "delivered"

    acknowledged = acknowledge_handoff(
        project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
    )
    assert acknowledged.state == "acknowledged"

    completed = complete_handoff(
        project_id,
        handoff.handoff_id,
        handoff.delivery_nonce,
        artifact_ids=("agent-patch-1",),
        data_root=data_root,
    )
    assert completed.state == "agent_reported_complete"
    assert completed.agent_reported_complete_artifact_ids == ("agent-patch-1",)
    # Never auto-promoted to a verified fix -- no "resolved"/"verified" state exists here.
    assert completed.state not in ("resolved", "verified")

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "agent_reported_complete"
    assert "session_capability" not in status
    assert "delivery_nonce" not in status


def test_duplicate_findings_from_two_engines_retain_both_provenance_records(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    same_location = {"path": "app.py", "line": 5, "column": 0, "rule": "seeded-rule"}
    finding_a = _finding(
        "finding-engine-a", tool="eslint", engine="engine-a", **same_location
    )
    finding_b = _finding(
        "finding-engine-b", tool="eslint", engine="engine-b", **same_location
    )
    _write_manifest(root, "run-dup", findings=[finding_a, finding_b])

    handoff = build_handoff(project_id, "run-dup", "codex-cli", data_root=data_root)

    assert set(handoff.finding_ids) == {"finding-engine-a", "finding-engine-b"}
    assert "eslint/engine-a" in {
        item.get("provenance") for item in handoff.packet["items"]
    }
    assert "eslint/engine-b" in {
        item.get("provenance") for item in handoff.packet["items"]
    }
    assert len(handoff.packet["items"]) == 2


def test_large_logs_exceed_budget_but_compact_packet_fits(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])

    huge_message = "x" * 50_000
    huge_finding = _finding("finding-huge", message=huge_message, line=1)
    normal_finding = _finding("finding-normal", message="short issue", line=2)
    _write_manifest(root, "run-huge", findings=[huge_finding, normal_finding])

    handoff = build_handoff(
        project_id,
        "run-huge",
        "codex-cli",
        max_tokens=256,
        max_bytes=2048,
        data_root=data_root,
    )

    assert handoff.packet["bytes"] <= 2048
    assert handoff.packet["tokens"] <= 256
    # Never silently loses a selected finding: both IDs are still accounted for,
    # either embedded or referenced.
    assert set(handoff.finding_ids) == {"finding-huge", "finding-normal"}
    huge_item = next(
        item
        for item in handoff.packet["items"]
        if item.get("finding_id") == "finding-huge"
    )
    assert huge_item.get("reference_only") is True
    assert huge_item["excerpt_truncated"] is True
    assert len(huge_item["excerpt"]) < len(huge_message)


def test_stale_source_identity_refuses_apply(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-stale", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-stale", "codex-cli", data_root=data_root)

    (root / "app.py").write_text("def changed():\n    return 1\n", encoding="utf-8")

    with pytest.raises(ScanHandoffSourceChangedError):
        dispatch_handoff(
            project_id,
            handoff.handoff_id,
            handoff.session_capability,
            data_root=data_root,
        )

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "prepared"


def test_delivered_without_ack_remains_unacknowledged(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-ack", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-ack", "codex-cli", data_root=data_root)
    dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status["state"] == "delivered"

    with pytest.raises(ScanHandoffAuthError):
        acknowledge_handoff(
            project_id, handoff.handoff_id, "wrong-nonce", data_root=data_root
        )

    # A rejected wrong-nonce attempt never advances state either.
    status_again = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert status_again["state"] == "delivered"


def test_acknowledge_before_dispatch_is_invalid_state(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-order", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-order", "codex-cli", data_root=data_root)
    with pytest.raises(ScanHandoffInvalidStateError):
        acknowledge_handoff(
            project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
        )


def test_complete_before_acknowledge_is_invalid_state(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-order2", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-order2", "codex-cli", data_root=data_root)
    dispatch_handoff(
        project_id, handoff.handoff_id, handoff.session_capability, data_root=data_root
    )
    with pytest.raises(ScanHandoffInvalidStateError):
        complete_handoff(
            project_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
        )


def test_unknown_run_id_and_handoff_id_are_invalid_request(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    with pytest.raises(ScanInvalidRequestError):
        build_handoff(project_id, "no-such-run", "codex-cli", data_root=data_root)
    with pytest.raises(ScanInvalidRequestError):
        status_handoff(project_id, "no-such-handoff", data_root=data_root)


def test_wrong_session_capability_denies_dispatch(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-cap", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-cap", "codex-cli", data_root=data_root)
    with pytest.raises(ScanHandoffAuthError):
        dispatch_handoff(
            project_id, handoff.handoff_id, "wrong-capability", data_root=data_root
        )


def test_scanhandofftool_envelope_prepare_requires_run_id_and_agent_id(
    tmp_path: Path,
) -> None:
    project_id, data_root = _register(tmp_path)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        response = ScanHandoffTool().handle_request(
            {"schema_version": 1, "operation": "prepare", "project": project_id}
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert response["status"] == "error"
    assert response["raw"]["error"]["code"] == "INVALID_REQUEST"


def test_scanhandofftool_flat_run_denies_prepare_without_scope(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-scope", findings=[_finding("finding-1")])

    result = ScanHandoffTool().run(
        Path(project_id),
        action="prepare",
        run_id="run-scope",
        agent_id="codex-cli",
        data_root=data_root,
    )
    assert result["status"] == "skipped"


def test_scanhandofftool_flat_run_full_lifecycle(tmp_path: Path) -> None:
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-tool", findings=[_finding("finding-1")])

    perms = ExecutionPermissions(cache_write=True, artifact_write=True)
    prepare_result = ScanHandoffTool().run(
        Path(project_id),
        action="prepare",
        run_id="run-tool",
        agent_id="codex-cli",
        permissions=perms,
        data_root=data_root,
    )
    assert prepare_result["status"] == "ok"
    handoff_id = prepare_result["raw"]["handoff_id"]
    session_capability = prepare_result["raw"]["session_capability"]
    delivery_nonce = prepare_result["raw"]["delivery_nonce"]

    dispatch_result = ScanHandoffTool().run(
        Path(project_id),
        action="dispatch",
        handoff_id=handoff_id,
        session_capability=session_capability,
        permissions=perms,
        data_root=data_root,
    )
    assert dispatch_result["status"] == "ok"
    assert dispatch_result["raw"]["state"] == "delivered"

    ack_result = ScanHandoffTool().run(
        Path(project_id),
        action="acknowledge",
        handoff_id=handoff_id,
        delivery_nonce=delivery_nonce,
        permissions=perms,
        data_root=data_root,
    )
    assert ack_result["status"] == "ok"
    assert ack_result["raw"]["state"] == "acknowledged"


# --- S05: ledger operation_id correlation + no persisted plaintext capability


def test_scan_handoff_carries_operation_id_field(tmp_path: Path) -> None:
    """S05: `ScanHandoff` persists a dashboard-preallocated `operation_id`
    so a crash after 202 can recover/replay against the same ledger
    operation rather than reminting one."""
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-op", findings=[_finding("finding-1")])

    handoff = build_handoff(
        project_id,
        "run-op",
        "codex-cli",
        data_root=data_root,
        operation_id="ledger-op-123",
    )
    assert handoff.operation_id == "ledger-op-123"

    reloaded = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert reloaded["operation_id"] == "ledger-op-123"


def test_handoff_send_artifact_and_session_receipts_are_not_clobbered(
    tmp_path: Path,
) -> None:
    """S04 bullet 3: `build_handoff` persists two distinct effects (the
    handoff artifact write, then the handoff session create) under one
    ledger `operation_id`. Both go through `TypedArtifactStore`'s
    `mutation_receipts` table, keyed `operation_id TEXT PRIMARY KEY` -- if
    both effects reused that one shared id, the second `INSERT OR REPLACE`
    would silently clobber the first receipt, leaving crash recovery unable
    to tell "artifact written, session not yet created" apart from "both
    created" (S05's own recovery bullet 2 needs this distinction). Passing
    `effect_ids` from the reservation gives each sub-effect its own id, so
    both receipts survive independently."""
    from rush.memory.store import TypedArtifactStore

    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-receipts", findings=[_finding("finding-1")])

    effect_ids = {
        "artifact_create": "receipt-artifact-1",
        "session_create": "receipt-session-1",
    }
    build_handoff(
        project_id,
        "run-receipts",
        "codex-cli",
        data_root=data_root,
        operation_id="ledger-op-shared",
        effect_ids=effect_ids,
    )

    store = TypedArtifactStore(root)
    artifact_receipt = store.get_receipt("receipt-artifact-1")
    session_receipt = store.get_receipt("receipt-session-1")
    assert artifact_receipt is not None
    assert artifact_receipt["kind"] == "create"
    assert session_receipt is not None
    assert session_receipt["kind"] == "handoff_session"
    # The shared, coarser ledger operation_id was never used as either
    # receipt's key -- proving the two effects didn't collide on one row.
    assert store.get_receipt("ledger-op-shared") is None


def _prepared_handoff_with_effect_ids(
    tmp_path: Path, run_id: str = "run-recover", owner_instance_id: str = ""
) -> tuple[str, Path, dict[str, str], object]:
    """S05 bullets 2-3 fixture: a handoff `build_handoff` persisted (real
    S04 effect receipts committed) but never `dispatch_handoff`ed --
    exactly what a dead owner leaves behind if it crashes between prepare
    and dispatch."""
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, run_id, findings=[_finding("finding-1")])
    effect_ids = {
        "artifact_create": "artifact-receipt-1",
        "session_create": "session-receipt-1",
        "delivery_transition": "delivery-receipt-1",
    }
    handoff = build_handoff(
        project_id,
        run_id,
        "codex-cli",
        data_root=data_root,
        operation_id="dead-owner-op-1",
        effect_ids=effect_ids,
        owner_instance_id=owner_instance_id,
    )
    assert handoff.state == "prepared"
    return project_id, data_root, effect_ids, handoff


def test_recover_prepared_handoff_delivers_via_verified_delta_without_capability(
    tmp_path: Path,
) -> None:
    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )

    recovered = recover_prepared_handoff(
        project_id,
        handoff.handoff_id,
        claimed_operation_id="dead-owner-op-1",
        artifact_create_receipt_id=effect_ids["artifact_create"],
        session_create_receipt_id=effect_ids["session_create"],
        delivery_receipt_id=effect_ids["delivery_transition"],
        data_root=data_root,
    )

    assert recovered is not None
    assert recovered.state == "delivered"
    reloaded = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert reloaded["state"] == "delivered"


def test_recover_prepared_handoff_returns_none_on_operation_id_mismatch(
    tmp_path: Path,
) -> None:
    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )

    recovered = recover_prepared_handoff(
        project_id,
        handoff.handoff_id,
        claimed_operation_id="some-other-operation",
        artifact_create_receipt_id=effect_ids["artifact_create"],
        session_create_receipt_id=effect_ids["session_create"],
        delivery_receipt_id=effect_ids["delivery_transition"],
        data_root=data_root,
    )

    assert recovered is None
    reloaded = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert reloaded["state"] == "prepared"


def test_recover_prepared_handoff_returns_none_when_a_receipt_is_missing(
    tmp_path: Path,
) -> None:
    """S04's artifact_create/session_create receipts are the proof
    `build_handoff` actually committed both writes -- a missing one means
    a partial crash mid-write, never safe to recover from."""
    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )

    recovered = recover_prepared_handoff(
        project_id,
        handoff.handoff_id,
        claimed_operation_id="dead-owner-op-1",
        artifact_create_receipt_id="never-committed-receipt",
        session_create_receipt_id=effect_ids["session_create"],
        delivery_receipt_id=effect_ids["delivery_transition"],
        data_root=data_root,
    )

    assert recovered is None


def test_recover_prepared_handoff_returns_none_when_source_changed(
    tmp_path: Path,
) -> None:
    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )
    (Path(handoff.root) / "app.py").write_text(
        "def changed():\n    pass\n", encoding="utf-8"
    )

    recovered = recover_prepared_handoff(
        project_id,
        handoff.handoff_id,
        claimed_operation_id="dead-owner-op-1",
        artifact_create_receipt_id=effect_ids["artifact_create"],
        session_create_receipt_id=effect_ids["session_create"],
        delivery_receipt_id=effect_ids["delivery_transition"],
        data_root=data_root,
    )

    assert recovered is None


def test_recover_prepared_handoff_returns_none_when_session_revoked(
    tmp_path: Path,
) -> None:
    from rush.memory.store import TypedArtifactStore

    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )
    store = TypedArtifactStore(Path(handoff.root))
    store.revoke_handoff_session(handoff.memory_session_id)

    recovered = recover_prepared_handoff(
        project_id,
        handoff.handoff_id,
        claimed_operation_id="dead-owner-op-1",
        artifact_create_receipt_id=effect_ids["artifact_create"],
        session_create_receipt_id=effect_ids["session_create"],
        delivery_receipt_id=effect_ids["delivery_transition"],
        data_root=data_root,
    )

    assert recovered is None


def test_dispatch_handoff_recovers_from_crash_between_receipt_commit_and_descriptor_write(
    tmp_path: Path,
) -> None:
    """S05 bullet 3: the delivery receipt and the `prepared` -> `delivered`
    file descriptor write are not one transaction -- a death between them
    must repair from the matching receipt without redispatch (never a
    second, conflicting delivery). Simulated by pre-committing the exact
    receipt `dispatch_handoff` would have written, then calling it for
    real: it must succeed using the pre-existing receipt, not error."""
    from rush.memory.handoff import receive_handoff
    from rush.memory.store import TypedArtifactStore

    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )
    store = TypedArtifactStore(Path(handoff.root))
    # The exact delta `dispatch_handoff` will itself compute -- receive_handoff
    # is idempotent/replayable, so calling it here first doesn't disturb the
    # real dispatch below.
    real_delta = receive_handoff(
        store,
        session_id=handoff.memory_session_id,
        capability=handoff.session_capability,
    )
    digest = hashlib.sha256(
        json.dumps(real_delta.get("changes", []), sort_keys=True).encode("utf-8")
    ).hexdigest()
    pre_existing = store.write_handoff_delivery_receipt(
        effect_ids["delivery_transition"],
        artifact_id=handoff.memory_session_id,
        payload={
            "handoff_id": handoff.handoff_id,
            "operation_id": handoff.operation_id,
            "run_id": handoff.run_id,
            "attempt_id": handoff.attempt_id,
            "memory_session_id": handoff.memory_session_id,
            "delivery_nonce": handoff.delivery_nonce,
            "delta_digest": digest,
        },
    )
    assert pre_existing is not None

    delivered = dispatch_handoff(
        project_id,
        handoff.handoff_id,
        handoff.session_capability,
        data_root=data_root,
        delivery_receipt_id=effect_ids["delivery_transition"],
    )
    assert delivered.state == "delivered"


def test_dispatch_handoff_rejects_conflicting_delivery_receipt_binding(
    tmp_path: Path,
) -> None:
    """A delivery receipt already recorded under this id for a *different*
    handoff/binding is a genuine conflict -- recovery-required, never
    silently accepted as if it were this handoff's own receipt."""
    from rush.memory.store import TypedArtifactStore

    project_id, data_root, effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path
    )
    store = TypedArtifactStore(Path(handoff.root))
    store.write_handoff_delivery_receipt(
        effect_ids["delivery_transition"],
        artifact_id="a-different-session-id",
        payload={"handoff_id": "some-other-handoff-entirely"},
    )

    with pytest.raises(ScanHandoffInvalidStateError):
        dispatch_handoff(
            project_id,
            handoff.handoff_id,
            handoff.session_capability,
            data_root=data_root,
            delivery_receipt_id=effect_ids["delivery_transition"],
        )


def test_session_capability_never_appears_in_persisted_descriptor_or_status_serialization(
    tmp_path: Path,
) -> None:
    """S05: the durable `.rush/handoffs/<id>.json` descriptor and the
    `handoff_status` read path both carry only a digest -- the raw
    one-time capability is never written to disk. Real dispatch (which
    presents the raw value from the same in-process `build_handoff` call)
    still succeeds, since comparison is now digest-based."""
    project_id, data_root = _register(tmp_path)
    from rush.workflows.projects import resolve_project

    root = Path(resolve_project(project_id, data_root=data_root)["root"])
    _write_manifest(root, "run-cap", findings=[_finding("finding-1")])

    handoff = build_handoff(project_id, "run-cap", "codex-cli", data_root=data_root)
    raw_capability = handoff.session_capability
    assert raw_capability

    descriptor_path = root / ".rush" / "handoffs" / f"{handoff.handoff_id}.json"
    on_disk = json.loads(descriptor_path.read_text(encoding="utf-8"))
    assert "session_capability" not in on_disk
    assert on_disk.get("session_capability_digest")
    assert on_disk["session_capability_digest"] != raw_capability

    status = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert "session_capability" not in status

    dispatched = dispatch_handoff(
        project_id, handoff.handoff_id, raw_capability, data_root=data_root
    )
    assert dispatched.state == "delivered"


# --- T038: owner_instance_id linkage from a dead owner to its prepared handoff


def test_build_handoff_carries_owner_instance_id_field(tmp_path: Path) -> None:
    """T038: `build_handoff` threads the caller's own dashboard owner
    identity onto the persisted `ScanHandoff` -- the only linkage
    `reconcile_admissions`/`list_prepared_handoffs` have from a dead
    `owner_instance_id` to a handoff it left `prepared`."""
    project_id, data_root, _effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path, owner_instance_id="dashboard:owner-1"
    )
    assert handoff.owner_instance_id == "dashboard:owner-1"

    reloaded = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert reloaded["owner_instance_id"] == "dashboard:owner-1"


def test_list_prepared_handoffs_matches_prepared_state_and_owner(
    tmp_path: Path,
) -> None:
    """T038: `list_prepared_handoffs` returns only handoffs still `prepared`
    for the exact `owner_instance_id` given -- a different owner's handoff,
    and this same owner's already-dispatched handoff, are both excluded."""
    project_id, data_root, effect_ids, handoff_a = _prepared_handoff_with_effect_ids(
        tmp_path, run_id="run-owner-a", owner_instance_id="dashboard:owner-a"
    )
    root = Path(handoff_a.root)

    # Same owner, but already dispatched -- must not be recovered again.
    dispatch_handoff(
        project_id,
        handoff_a.handoff_id,
        handoff_a.session_capability,
        data_root=data_root,
        delivery_receipt_id=effect_ids["delivery_transition"],
    )

    _write_manifest(root, "run-owner-a-2", findings=[_finding("finding-2")])
    handoff_a2 = build_handoff(
        project_id,
        "run-owner-a-2",
        "codex-cli",
        data_root=data_root,
        operation_id="dead-owner-op-2",
        effect_ids={
            "artifact_create": "artifact-receipt-2",
            "session_create": "session-receipt-2",
        },
        owner_instance_id="dashboard:owner-a",
    )
    assert handoff_a2.state == "prepared"

    _write_manifest(root, "run-owner-b", findings=[_finding("finding-3")])
    build_handoff(
        project_id,
        "run-owner-b",
        "codex-cli",
        data_root=data_root,
        operation_id="dead-owner-op-3",
        effect_ids={
            "artifact_create": "artifact-receipt-3",
            "session_create": "session-receipt-3",
        },
        owner_instance_id="dashboard:owner-b",
    )

    matches = project_run.list_prepared_handoffs(root, "dashboard:owner-a")

    assert [m.handoff_id for m in matches] == [handoff_a2.handoff_id]


def test_list_prepared_handoffs_skips_a_pre_schema_handoff_missing_owner_instance_id(
    tmp_path: Path,
) -> None:
    """T038: a handoff persisted before `owner_instance_id` existed has no
    such key in its on-disk JSON -- `ScanHandoff.from_dict`/
    `list_prepared_handoffs` must degrade to "never matches a real owner",
    never raise, when reading it back."""
    project_id, data_root, _effect_ids, handoff = _prepared_handoff_with_effect_ids(
        tmp_path, owner_instance_id=""
    )
    root = Path(handoff.root)
    descriptor_path = root / ".rush" / "handoffs" / f"{handoff.handoff_id}.json"
    payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    assert "owner_instance_id" in payload
    del payload["owner_instance_id"]
    descriptor_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    reloaded = status_handoff(project_id, handoff.handoff_id, data_root=data_root)
    assert reloaded["owner_instance_id"] == ""

    matches = project_run.list_prepared_handoffs(root, "dashboard:some-owner")
    assert matches == []
    # An empty/unknown owner_instance_id must never match either -- an
    # empty string is never treated as a wildcard.
    assert project_run.list_prepared_handoffs(root, "") == []
