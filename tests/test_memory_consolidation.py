"""MC03 §6.3 duplicate episode consolidation preserving originals, exceptions, contradictions
and trust (docs/phase-plans/MC03.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rush.memory.consolidation import consolidate_episodes, summary_is_current
from rush.memory.store import MemoryArtifact, TypedArtifactStore


def _episode(
    store: TypedArtifactStore,
    artifact_id: str,
    *,
    symptom: str,
    condition: dict[str, Any],
    attempt: str,
    outcome: str,
    trust_tier: str = "DERIVED",
    source: str = "allowed",
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="experience",
            subject="episodic",
            trust_tier=trust_tier,
            content={
                "symptom": symptom,
                "condition": condition,
                "attempt": attempt,
                "outcome": outcome,
            },
            source=source,
            created_at=1.0,
        )
    )


def test_duplicate_summary_preserves_originals_and_exception(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    failure_ids = ["f1", "f2", "f3"]
    for artifact_id in failure_ids:
        _episode(
            store,
            artifact_id,
            symptom="timeout",
            condition={"env": "ci"},
            attempt="retry",
            outcome="failed",
        )
    _episode(
        store,
        "success",
        symptom="timeout",
        condition={"env": "local"},
        attempt="retry",
        outcome="success",
    )
    original_bytes = {
        artifact_id: store.get_version_content(artifact_id, 1)
        for artifact_id in [*failure_ids, "success"]
    }

    result = consolidate_episodes(
        store, symptom="timeout", session_allowlist=["allowed"]
    )
    assert result["code"] == "OK"
    summary = result["summary"]

    assert set(summary["member_ids"]) == {*failure_ids, "success"}
    assert summary["repetition"] == 3
    assert [exc["id"] for exc in summary["exceptions"]] == ["success"]
    assert summary["trust_tier"] == "DERIVED"

    # Originals are never mutated or deleted by consolidation.
    for artifact_id in [*failure_ids, "success"]:
        assert store.get_version_content(artifact_id, 1) == original_bytes[artifact_id]
        assert store.get_current(artifact_id) is not None

    assert summary_is_current(store, summary) is True
    store.update_content(
        "f1",
        {
            "symptom": "timeout",
            "condition": {"env": "ci"},
            "attempt": "retry",
            "outcome": "failed still",
        },
        expected_version=1,
    )
    assert summary_is_current(store, summary) is False


def test_repetition_cannot_promote_trust(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    for artifact_id in ("r1", "r2", "r3"):
        _episode(
            store,
            artifact_id,
            symptom="flaky network",
            condition={"env": "ci"},
            attempt="retry",
            outcome="failed",
            trust_tier="DERIVED",
        )

    result = consolidate_episodes(
        store, symptom="flaky network", session_allowlist=["allowed"]
    )

    assert result["code"] == "OK"
    summary = result["summary"]
    assert summary["repetition"] == 3
    assert summary["trust_tier"] == "DERIVED"
    assert summary["trust_tier"] != "STATED"


def test_contradictory_conditions_are_not_merged(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _episode(
        store,
        "py39",
        symptom="import error",
        condition={"python": "3.9"},
        attempt="pin dependency",
        outcome="failed",
    )
    _episode(
        store,
        "py311",
        symptom="import error",
        condition={"python": "3.11"},
        attempt="pin dependency",
        outcome="failed",
    )

    result = consolidate_episodes(
        store, symptom="import error", session_allowlist=["allowed"]
    )

    assert result["code"] == "OK"
    summary = result["summary"]
    # Contradictory conditions never merge into one repeated group.
    assert summary["repetition"] == 1
    assert len(summary["exceptions"]) == 1
    assert set(summary["member_ids"]) == {"py39", "py311"}
