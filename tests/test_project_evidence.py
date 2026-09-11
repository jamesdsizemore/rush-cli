"""P65-07.1/.2 (plan §6.4): the shared project-evidence view (`project_snapshot`,
`list_project_artifacts`). Two projects never mix findings/memory even with identical
filenames; every discoverable output -- known category, unrecognized future category,
secret-bearing raw output, and a deleted memory reference -- stays discoverable with
provenance, and a generic reference view never exposes raw content.

Manifests are written directly, matching `rush.workflows.project_run._build_manifest`'s
documented on-disk schema (plan §6.1 layout, `ScanCandidate`/`CandidateResult.to_dict()`)
-- this suite tests the *read* side (`list_project_artifacts`/`project_snapshot`), not
`execute_scan`'s own classification/scheduling, which P65-04's own tests already cover.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool
from rush.workflows.projects import (
    list_project_artifacts,
    project_snapshot,
    register_project,
)

_WRITE = ExecutionPermissions(cache_write=True)


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def _write_manifest(
    root: Path,
    *,
    run_id: str,
    scheduled: list[dict[str, Any]],
    findings: list[dict[str, Any]] | None = None,
) -> None:
    attempt_id = f"{run_id}-attempt-1"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": f"plan-{run_id}",
        "project_id": "unused-by-reader",
        "root": str(root),
        "run_state": "completed",
        "severity": "warn",
        "concurrency": 2,
        "timeout_seconds": 300,
        "created_at": "2026-01-01T00:00:00+00:00",
        "candidates": scheduled,
        "scheduled": scheduled,
        "aggregate": {
            "tool": "scan",
            "engine": None,
            "status": "ok",
            "findings": findings or [],
            "metadata": {"coverage": {"empty": False}},
        },
        "totals": {
            "candidate_count": len(scheduled),
            "scheduled_count": len(scheduled),
            "executed_count": len(scheduled),
            "finding_count": len(findings or []),
        },
    }
    manifest_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _scheduled_item(
    candidate_id: str,
    category: str,
    *,
    metrics: dict[str, Any] | None = None,
    raw: Any = None,
    artifacts: list[str] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "kind": "tool",
        "category": category,
        "disposition": "applicable",
        "reason": "comprehensive_static_analysis",
        "outcome": "executed",
        "child": {
            "tool": candidate_id,
            "engine": None,
            "status": "ok",
            "findings": findings or [],
            "summary": f"{candidate_id} ok",
            "metrics": metrics or {},
            "artifacts": artifacts or [],
            "raw": raw,
        },
    }


def _project(tmp_path: Path, name: str) -> tuple[str, Path, Path]:
    root = tmp_path / name
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    data_root = _data_root(tmp_path) / name
    record = register_project(root, data_root=data_root)
    return record.project_id, root, data_root


def test_two_projects_with_identical_filenames_do_not_mix_findings_or_memory(
    tmp_path: Path,
) -> None:
    project_a, root_a, data_root_a = _project(tmp_path, "alpha")
    project_b, root_b, data_root_b = _project(tmp_path, "beta")

    _write_manifest(
        root_a,
        run_id="run-a",
        scheduled=[_scheduled_item("typecheck", "quality")],
        findings=[{"finding_id": "fa1", "path": "app.py", "severity": "error"}],
    )
    _write_manifest(
        root_b,
        run_id="run-b",
        scheduled=[_scheduled_item("typecheck", "quality")],
        findings=[
            {"finding_id": "fb1", "path": "app.py", "severity": "warn"},
            {"finding_id": "fb2", "path": "app.py", "severity": "warn"},
        ],
    )

    store_a = TypedArtifactStore(root_a)
    store_a.write(
        MemoryArtifact(
            id="mem-a",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"body": "alpha secret finding notes"},
            source="s1",
            created_at=time.time(),
        )
    )
    store_b = TypedArtifactStore(root_b)
    store_b.write(
        MemoryArtifact(
            id="mem-b",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"body": "beta unrelated notes"},
            source="s1",
            created_at=time.time(),
        )
    )

    snapshot_a = project_snapshot(project_a, data_root=data_root_a)
    snapshot_b = project_snapshot(project_b, data_root=data_root_b)

    assert snapshot_a["runs"]["findings_count"] == 1
    assert snapshot_b["runs"]["findings_count"] == 2
    assert snapshot_a["memory"]["counts_by_subject"] == {"domain_knowledge": 1}
    assert snapshot_b["memory"]["counts_by_subject"] == {"domain_knowledge": 1}

    serialized_a = json.dumps(snapshot_a)
    serialized_b = json.dumps(snapshot_b)
    assert "beta unrelated notes" not in serialized_a
    assert "alpha secret finding notes" not in serialized_b
    assert "fb1" not in serialized_a and "fb2" not in serialized_a
    assert "fa1" not in serialized_b


def test_known_profiling_export_and_unrecognized_categories_all_discoverable(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        scheduled=[
            _scheduled_item("typecheck", "quality"),
            _scheduled_item("py-spy", "profiling"),
            _scheduled_item("sbom-export", "export"),
            _scheduled_item("mystery-tool", "a_future_output_type_nobody_named_yet"),
        ],
    )

    result = list_project_artifacts(project_id, data_root=data_root)
    categories = {item["category"] for item in result["scan_outputs"]}
    assert categories == {
        "quality",
        "profiling",
        "export",
        "a_future_output_type_nobody_named_yet",
    }
    for item in result["scan_outputs"]:
        assert item["run_id"] == "run-1"
        assert item["attempt_id"]
        assert item["artifact_ref"].startswith("run:run-1:")


def test_secret_bearing_raw_output_never_surfaces_in_artifact_listing(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    secret = "sk-live-TOTALLY_REAL_SECRET_VALUE"
    _write_manifest(
        root,
        run_id="run-1",
        scheduled=[
            _scheduled_item(
                "leaky-tool",
                "quality",
                raw={"stdout": f"leaked token={secret}"},
                findings=[
                    {
                        "finding_id": "f1",
                        "path": "app.py",
                        "severity": "error",
                        "evidence": {"snippet": secret},
                    }
                ],
            )
        ],
    )

    artifacts = list_project_artifacts(project_id, data_root=data_root)
    snapshot = project_snapshot(project_id, data_root=data_root)
    assert secret not in json.dumps(artifacts)
    assert secret not in json.dumps(snapshot)


def test_deleted_memory_artifact_reference_remains_discoverable_with_provenance(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    store = TypedArtifactStore(root)
    store.write(
        MemoryArtifact(
            id="soon-deleted",
            family="memory",
            subject="preference",
            trust_tier="DERIVED",
            content={"body": "will be removed"},
            source="s1",
            created_at=time.time(),
        )
    )
    store.delete_batch(
        ["soon-deleted"],
        expected_revisions={"soon-deleted": 1},
        scope="preference",
        apply=True,
    )

    result = list_project_artifacts(project_id, data_root=data_root)
    deleted_entries = [item for item in result["memory"] if item["deleted"]]
    assert len(deleted_entries) == 1
    assert deleted_entries[0]["id"] == "soon-deleted"
    assert deleted_entries[0]["category"] == "preference"
    assert "will be removed" not in json.dumps(result)


def test_project_snapshot_has_overview_runs_memory_tokens_git_and_artifacts(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_manifest(
        root, run_id="run-1", scheduled=[_scheduled_item("typecheck", "quality")]
    )

    snapshot = project_snapshot(project_id, data_root=data_root)
    assert snapshot["project"]["project_id"] == project_id
    assert snapshot["runs"]["count"] == 1
    assert snapshot["runs"]["latest_run_id"] == "run-1"
    assert set(snapshot["memory"]) == {
        "counts_by_subject",
        "deleted_count",
        "admin_capabilities",
    }
    assert set(snapshot["memory"]["admin_capabilities"]) == {
        "write",
        "promote",
        "maintain",
        "delete",
        "edit",
        "archive",
    }
    assert set(snapshot["tokens"]) == {
        "provider_reported",
        "tokenizer_counted",
        "cache_hits",
        "estimated_avoided",
    }
    assert snapshot["git"]["has_git"] is False
    assert snapshot["artifacts"]["project_id"] == project_id


# T031 (plan §6.4 line 247): public `edit`/`archive` memory operations, added to the same
# P65-07 file set as `delete` (tests/test_memory_delete.py). Placed here (not
# test_memory_delete.py) per the plan's own explicit instruction.


def _seed_one(
    root: Path, *, artifact_id: str = "e1", subject: str = "domain_knowledge"
) -> None:
    TypedArtifactStore(root).write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=subject,
            trust_tier="DERIVED",
            content={"body": "original"},
            source="s1",
            created_at=time.time(),
        )
    )


def test_edit_preview_never_writes(tmp_path: Path) -> None:
    _seed_one(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "domain_knowledge",
            "id": "e1",
            "expected_version": 1,
            "content": {"body": "edited"},
            "apply": False,
        },
    )
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["applied"] is False
    store = TypedArtifactStore(tmp_path)
    assert store.get_current("e1").content == {"body": "original"}


def test_edit_apply_updates_content_under_compare_and_swap(tmp_path: Path) -> None:
    _seed_one(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "domain_knowledge",
            "id": "e1",
            "expected_version": 1,
            "content": {"body": "edited"},
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["applied"] is True
    store = TypedArtifactStore(tmp_path)
    current = store.get_current("e1")
    assert current.content == {"body": "edited"}
    assert current.artifact_version == 2


def test_edit_stale_version_conflict_refuses_the_edit(tmp_path: Path) -> None:
    _seed_one(tmp_path)
    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "domain_knowledge",
            "id": "e1",
            "expected_version": 2,  # real revision is 1
            "content": {"body": "edited"},
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "E_VERSION"
    store = TypedArtifactStore(tmp_path)
    assert store.get_current("e1").content == {"body": "original"}


def test_edit_cross_scope_refuses_the_edit(tmp_path: Path) -> None:
    _seed_one(tmp_path, subject="domain_knowledge")
    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "preference",  # e1's real subject is domain_knowledge
            "id": "e1",
            "expected_version": 1,
            "content": {"body": "edited"},
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "E_SCOPE"
    store = TypedArtifactStore(tmp_path)
    assert store.get_current("e1").content == {"body": "original"}


def test_edit_resets_promoted_trust_to_candidate(tmp_path: Path) -> None:
    _seed_one(tmp_path)
    store = TypedArtifactStore(tmp_path)
    promoted, _ = store.promote("e1", user_stated=True, candidate_sources=["s1"])
    assert promoted.trust_tier == "STATED"

    result = MemoryTool().run(
        tmp_path,
        operation="edit",
        request={
            "scope": "domain_knowledge",
            "id": "e1",
            "expected_version": promoted.artifact_version,
            "content": {"body": "edited after promotion"},
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["trust_tier"] != "STATED"
    current = store.get_current("e1")
    assert current.trust_tier != "STATED"
    assert current.signature is None
    assert current.promoted_at is None


def test_archive_preview_never_writes(tmp_path: Path) -> None:
    _seed_one(tmp_path, artifact_id="a1")
    result = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": 1,
            "apply": False,
        },
    )
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["applied"] is False
    listing = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        query="original",
        session_allowlist=["s1"],
    )
    assert len(listing["raw"]) == 1


def test_archive_excludes_artifact_from_default_recall(tmp_path: Path) -> None:
    _seed_one(tmp_path, artifact_id="a1")
    result = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": 1,
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert result["raw"]["code"] == "OK"
    assert result["raw"]["data"]["archived"] is True

    listing = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        query="original",
        session_allowlist=["s1"],
    )
    assert listing["raw"] == []

    store = TypedArtifactStore(tmp_path)
    current = store.get_current("a1")
    assert current is not None
    assert current.content == {"body": "original"}  # content/history retained


def test_archive_include_archived_reveals_it_for_authorized_inspection(
    tmp_path: Path,
) -> None:
    _seed_one(tmp_path, artifact_id="a1")
    MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": 1,
            "apply": True,
        },
        permissions=_WRITE,
    )

    listing = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        query="original",
        session_allowlist=["s1"],
        include_archived=True,
    )
    assert len(listing["raw"]) == 1
    assert listing["raw"][0]["id"] == "a1"


def test_archive_is_reversible_via_unarchive_with_expected_version(
    tmp_path: Path,
) -> None:
    _seed_one(tmp_path, artifact_id="a1")
    archived = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": 1,
            "apply": True,
        },
        permissions=_WRITE,
    )
    archived_version = archived["raw"]["data"]["revision"]

    unarchived = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": archived_version,
            "apply": True,
            "archived": False,
        },
        permissions=_WRITE,
    )
    assert unarchived["raw"]["code"] == "OK"
    assert unarchived["raw"]["data"]["archived"] is False

    listing = MemoryTool().run(
        tmp_path,
        operation="list",
        subject="domain_knowledge",
        query="original",
        session_allowlist=["s1"],
    )
    assert len(listing["raw"]) == 1


def test_archive_stale_version_and_cross_scope_refuse_atomically(
    tmp_path: Path,
) -> None:
    _seed_one(tmp_path, artifact_id="a1")
    stale = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "domain_knowledge",
            "id": "a1",
            "expected_version": 99,
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert stale["raw"]["code"] == "E_VERSION"

    cross_scope = MemoryTool().run(
        tmp_path,
        operation="archive",
        request={
            "scope": "preference",
            "id": "a1",
            "expected_version": 1,
            "apply": True,
        },
        permissions=_WRITE,
    )
    assert cross_scope["raw"]["code"] == "E_SCOPE"

    store = TypedArtifactStore(tmp_path)
    current = store.get_current("a1")
    assert current.artifact_version == 1  # neither refused attempt advanced the row


def test_propose_write_creates_unpromoted_candidate_never_stated(
    tmp_path: Path,
) -> None:
    """Plan §6.4: `propose` is a presentation label for existing `write(...)` -- it always
    creates an unpromoted candidate, never authoritative memory. A UI click alone (no
    explicit `promote(..., user_stated=True)` call) can never set trust_tier="STATED"."""
    result = MemoryTool().run(
        tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "proposed candidate"},
        source="s1",
        source_kind="local_tool",
        permissions=_WRITE,
    )
    assert result["status"] == "ok"
    written = result["raw"]
    assert written["trust_tier"] != "STATED"

    store = TypedArtifactStore(tmp_path)
    current = store.get_current(written["id"])
    assert current.trust_tier != "STATED"
    assert current.promoted_at is None
