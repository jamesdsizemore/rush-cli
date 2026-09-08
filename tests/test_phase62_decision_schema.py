"""Contract tests T-62.15 through T-62.17 for decision-record schema reuse (Phase 62 §6.4)."""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from rush.memory.decision_schema import DecisionRecordFields
from rush.memory.mistake_miner import MistakeMiner, shape_failure_candidates
from rush.memory.store import MemoryArtifact, TypedArtifactStore


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo_with_revert(repo: Path) -> None:
    _run_git(["init"], repo)
    _run_git(["config", "user.email", "test@example.com"], repo)
    _run_git(["config", "user.name", "Test"], repo)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _run_git(["add", "."], repo)
    _run_git(["commit", "-m", "feat: enable aggressive async socket pooling"], repo)
    _run_git(
        [
            "commit",
            "--allow-empty",
            "-m",
            'Revert "feat: enable aggressive async socket pooling"',
            "-m",
            "Caused a race condition under concurrent load.",
        ],
        repo,
    )


def test_architectural_decision_record_carries_remediation_shaped_fields(
    tmp_path: Path,
):
    fields = DecisionRecordFields(
        red_task="tests/test_seam.py::test_red",
        green_task="src/rush/seam.py::fix",
        target_seam="src/rush/seam.py::Seam.call",
        test_file="tests/test_seam.py",
        test_function="test_red",
        predecessor="ADR-0030",
        status="in_progress",
    )
    content = {"rationale": "seam needed a contract", **asdict(fields)}

    store = TypedArtifactStore(project_root=tmp_path)
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family="memory",
        subject="architectural_decision",
        trust_tier="DERIVED",
        content=content,
        source="test",
        created_at=time.time(),
    )
    store.write(artifact)

    recalled = store.recall(
        "architectural_decision", "seam", session_allowlist=["test"]
    )
    assert len(recalled) == 1
    for field_name in asdict(fields):
        assert recalled[0].content[field_name] == getattr(fields, field_name)


def test_status_defaults_in_progress_and_accepts_completed(tmp_path: Path):
    default_fields = DecisionRecordFields()
    assert default_fields.status == "in_progress"

    completed_fields = DecisionRecordFields(status="completed")

    store = TypedArtifactStore(project_root=tmp_path)
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family="memory",
        subject="architectural_decision",
        trust_tier="DERIVED",
        content={"rationale": "statusroundtrip marker", **asdict(completed_fields)},
        source="test",
        created_at=time.time(),
    )
    store.write(artifact)

    recalled = store.recall(
        "architectural_decision", "statusroundtrip", session_allowlist=["test"]
    )
    assert len(recalled) == 1
    assert recalled[0].content["status"] == "completed"


def test_mistake_miner_failure_write_carries_decision_schema_round_trip(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo_with_revert(repo)

    miner = MistakeMiner(project_root=repo)
    mistakes = miner.mine_mistakes()
    assert mistakes, "expected the seeded revert commit to be mined"

    candidates = shape_failure_candidates(mistakes, source="test")
    assert len(candidates) == 1
    candidate = candidates[0]

    store = TypedArtifactStore(project_root=repo)
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family=candidate["family"],
        subject=candidate["subject"],
        trust_tier=candidate["trust_tier"],
        content=candidate["content"],
        source=candidate["source"],
        created_at=time.time(),
    )
    assert artifact.subject == "failure"
    store.write(artifact)

    recalled = store.recall("failure", "pooling", session_allowlist=["test"])
    assert len(recalled) == 1
    assert recalled[0].content == candidate["content"]
    assert (
        recalled[0].content["target_seam"] == candidate["content"]["reverted_subject"]
    )
    assert recalled[0].content["status"] == "in_progress"
