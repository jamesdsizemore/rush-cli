"""MC10 (Phase 63) last-success pointer + diagnosis: compares a current failure to the
recorded per-behavior/runtime-platform last successful observation.
"""

from __future__ import annotations

from pathlib import Path

from rush.memory.experience import (
    behavior_runtime_digest,
    compare_last_success,
    record_behavior_success,
    record_cause_experiment,
    write_observation,
)
from rush.memory.store import TypedArtifactStore
from rush.tools.memory import MemoryTool

_UPLOAD_CONDITIONS = {
    "runtime": "python3.11",
    "platform": "darwin",
    "code_digest": "code-v1",
    "config_digest": "config-v1",
    "dependency_digest": "deps-v1",
    "engine": "pytest",
    "engine_version": "8.0.0",
}


def test_success_is_per_behavior_and_environment(tmp_path: Path) -> None:
    passed = record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    # A later failure of the same behavior/environment must never move the pointer.
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="test",
        source="test:upload-fail",
        content={"behavior_id": "upload", "status": "fail"},
        project_root=tmp_path,
    )
    upload_digest = behavior_runtime_digest(runtime="python3.11", platform="darwin")
    store = TypedArtifactStore(tmp_path)
    assert store.get_behavior_success(
        namespace="default", behavior_id="upload", runtime_digest=upload_digest
    ) == (passed.id, passed.artifact_version)

    # Recording a different behavior under a different runtime must not touch Upload's entry.
    record_behavior_success(
        project_root=tmp_path,
        behavior_id="download",
        conditions={**_UPLOAD_CONDITIONS, "runtime": "python3.12", "platform": "linux"},
        source="test:download-pass",
    )
    assert store.get_behavior_success(
        namespace="default", behavior_id="upload", runtime_digest=upload_digest
    ) == (passed.id, passed.artifact_version)
    download_digest = behavior_runtime_digest(runtime="python3.12", platform="linux")
    assert (
        store.get_behavior_success(
            namespace="default", behavior_id="upload", runtime_digest=download_digest
        )
        is None
    )


def test_skipped_or_cached_check_cannot_advance_success(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    upload_digest = behavior_runtime_digest(runtime="python3.11", platform="darwin")

    # A skipped/cached/tag-only observation, with no call to record_behavior_success, must
    # never create a pointer.
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="test",
        source="test:upload-cached",
        content={"behavior_id": "upload", "status": "cached", "tag": "cache-hit"},
        project_root=tmp_path,
    )
    assert (
        store.get_behavior_success(
            namespace="default", behavior_id="upload", runtime_digest=upload_digest
        )
        is None
    )

    # Once a real pass establishes the pointer, a later cache-hit/skip observation must not
    # move it.
    passed = record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="test",
        source="test:upload-skip",
        content={"behavior_id": "upload", "status": "skipped"},
        project_root=tmp_path,
    )
    assert store.get_behavior_success(
        namespace="default", behavior_id="upload", runtime_digest=upload_digest
    ) == (passed.id, passed.artifact_version)


def test_code_dependency_and_config_changes_are_distinguished(tmp_path: Path) -> None:
    record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    code_only = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
    )
    assert code_only["code_changes"] == {"baseline": "code-v1", "current": "code-v2"}
    assert code_only["config_changes"] is None
    assert code_only["dependency_changes"] is None
    assert code_only["engine_changes"] is None

    dependency_only = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "dependency_digest": "deps-v2"},
    )
    assert dependency_only["dependency_changes"] == {
        "baseline": "deps-v1",
        "current": "deps-v2",
    }
    assert dependency_only["code_changes"] is None
    assert dependency_only["config_changes"] is None
    assert dependency_only["engine_changes"] is None

    config_only = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "config_digest": "config-v2"},
    )
    assert config_only["config_changes"] == {
        "baseline": "config-v1",
        "current": "config-v2",
    }
    assert config_only["code_changes"] is None
    assert config_only["dependency_changes"] is None
    assert config_only["engine_changes"] is None


def test_unavailable_engine_is_not_application_regression(tmp_path: Path) -> None:
    record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    result = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "engine": None, "engine_version": None},
    )

    assert result["engine_changes"] == {
        "baseline": {"engine": "pytest", "engine_version": "8.0.0"},
        "current": {"engine": None, "engine_version": None},
    }
    assert result["code_changes"] is None
    assert result["config_changes"] is None
    assert result["dependency_changes"] is None
    assert result["cause_state"] == "candidate"


def test_only_controlled_reproduction_confirms_cause(tmp_path: Path) -> None:
    record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    diagnosis = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
    )
    assert diagnosis["cause_state"] == "candidate"
    baseline_ref = diagnosis["baseline_ref"]
    assert baseline_ref is not None

    # A control run that never executed (no receipt -- e.g. an unavailable engine) never
    # confirms the cause, even if it "would have" changed the outcome.
    unreproduced = record_cause_experiment(
        project_root=tmp_path,
        behavior_id="upload",
        baseline_ref=baseline_ref,
        changed_factor="code",
        control_receipt_ref=None,
        outcome_changed=True,
        source="test:cause-unavailable",
    )
    assert unreproduced["cause_state"] == "candidate"
    still_candidate = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
    )
    assert still_candidate["cause_state"] == "candidate"

    # A real receipted controlled run whose outcome changed confirms the cause.
    reproduced = record_cause_experiment(
        project_root=tmp_path,
        behavior_id="upload",
        baseline_ref=baseline_ref,
        changed_factor="code",
        control_receipt_ref="receipt:pytest-run-42",
        outcome_changed=True,
        source="test:cause-reproduced",
    )
    assert reproduced["cause_state"] == "reproduced"
    confirmed = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
    )
    assert confirmed["cause_state"] == "reproduced"


def test_later_failure_does_not_destroy_last_success(tmp_path: Path) -> None:
    passed = record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    write_observation(
        evidence_kind="tests_contracts",
        operation_id="test",
        source="test:upload-fail",
        content={
            "behavior_id": "upload",
            "status": "fail",
            "conditions": {**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
        },
        project_root=tmp_path,
    )

    upload_digest = behavior_runtime_digest(runtime="python3.11", platform="darwin")
    store = TypedArtifactStore(tmp_path)
    assert store.get_behavior_success(
        namespace="default", behavior_id="upload", runtime_digest=upload_digest
    ) == (passed.id, passed.artifact_version)

    diagnosis = compare_last_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions={**_UPLOAD_CONDITIONS, "code_digest": "code-v2"},
    )
    assert diagnosis["baseline_ref"] == {
        "id": passed.id,
        "version": passed.artifact_version,
    }


def test_memory_tool_last_success_diagnose_operation_returns_diagnosis(
    tmp_path: Path,
) -> None:
    record_behavior_success(
        project_root=tmp_path,
        behavior_id="upload",
        conditions=_UPLOAD_CONDITIONS,
        source="test:upload-pass",
    )

    result = MemoryTool().run(
        tmp_path,
        operation="last_success_diagnose",
        request={
            "behavior_id": "upload",
            "conditions": {**_UPLOAD_CONDITIONS, "config_digest": "config-v2"},
        },
    )

    assert result["status"] == "ok"
    data = result["raw"]["data"]
    assert data["config_changes"] == {"baseline": "config-v1", "current": "config-v2"}
    assert data["code_changes"] is None
    assert data["cause_state"] == "candidate"
