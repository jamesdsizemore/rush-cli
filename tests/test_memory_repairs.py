"""MC06 (Phase 63): repair-episode recall by exact §9.0 conditions.

Exercises `record_attempt`/`recall_repair_episodes`/`prepare_memory`
(`rush.memory.experience`) and their wiring into `MemoryTool` (`prepare`/`resume`
operations, `rush.tools.memory.MemoryTool`). Repair episodes bind symptom, exact
patch hash, hypothesis, §9.0 condition identity and receipted check outcomes.
Recall only ever reads what was already recorded -- it never runs a new check.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from rush.memory.experience import (
    prepare_memory,
    recall_repair_episodes,
    record_attempt,
    write_observation,
)
from rush.memory.store import TypedArtifactStore
from rush.tools.memory import MemoryTool

_SYMPTOM = "upload timeout regression"
_SOURCE = f"repair_attempt:{_SYMPTOM}"


def _conditions(**overrides: Any) -> dict[str, Any]:
    """§9.0 fixture conditions: cpython/3.12, test/test platform, parser==1.0."""
    base: dict[str, Any] = {
        "runtime": "cpython/3.12",
        "platform": "test/test",
        "dependencies": {"parser": "1.0"},
        "config_digest": hashlib.sha256(b"upload-config-v1").hexdigest(),
        "source_digest": hashlib.sha256(b"upload.py-v1").hexdigest(),
    }
    base.update(overrides)
    return base


def _receipt(tmp_path: Path, *, outcome: str) -> str:
    """A real recorded regression-check receipt (MC05 `write_observation`) -- the only
    evidence a check actually ran. Never a fabricated string."""
    artifact = write_observation(
        evidence_kind="sandbox_verification",
        operation_id="memory.verify_attempt",
        source=_SOURCE,
        content={"attempt_symptom": _SYMPTOM, "outcome": outcome, "passed_count": 1},
        project_root=tmp_path,
    )
    assert artifact is not None
    return artifact.id


def _record(
    tmp_path: Path,
    *,
    hypothesis: str,
    patch_hash: str | None,
    conditions: dict[str, Any],
    outcome: str,
    receipt_ref: str | None = None,
    behavior_ids: tuple[str, ...] = ("upload-timeout-fixed",),
    commit_message: str | None = None,
):
    return record_attempt(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        hypothesis=hypothesis,
        patch_hash=patch_hash,
        conditions=conditions,
        receipt_ref=receipt_ref,
        behavior_ids=behavior_ids,
        outcome=outcome,  # type: ignore[arg-type]
        commit_message=commit_message,
    )


def test_same_failed_timeout_patch_returns_evidence(tmp_path: Path) -> None:
    conditions = _conditions()
    t1_receipt = _receipt(tmp_path, outcome="failed")
    t1 = _record(
        tmp_path,
        hypothesis="increase timeout to 60s",
        patch_hash="patch-timeout-only",
        conditions=conditions,
        outcome="failed",
        receipt_ref=t1_receipt,
    )
    s1_receipt = _receipt(tmp_path, outcome="verified")
    s1 = _record(
        tmp_path,
        hypothesis="lower size limit to 25",
        patch_hash="patch-size-limit",
        conditions=conditions,
        outcome="verified",
        receipt_ref=s1_receipt,
        behavior_ids=("upload-timeout-fixed", "upload-size-limit-fixed"),
    )

    result = recall_repair_episodes(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=conditions,
        patch_hash="patch-timeout-only",
        session_allowlist=[_SOURCE],
    )

    assert result["code"] == "OK"
    assert len(result["failures"]) == 1
    failure = result["failures"][0]
    assert failure["id"] == t1.id
    assert failure["match"] == "same"
    assert t1.id in failure["warning"]
    # Recall never claims a new execution: the receipt is exactly the one already recorded.
    assert failure["receipt_ref"] == t1_receipt

    assert len(result["verified_repairs"]) == 1
    verified = result["verified_repairs"][0]
    assert verified["id"] == s1.id
    assert s1.id in verified["note"]
    assert verified["receipt_ref"] == s1_receipt


def test_dependency_change_permits_retrial(tmp_path: Path) -> None:
    original_conditions = _conditions()
    t1 = _record(
        tmp_path,
        hypothesis="increase timeout to 60s",
        patch_hash="patch-timeout-only",
        conditions=original_conditions,
        outcome="failed",
        receipt_ref=_receipt(tmp_path, outcome="failed"),
    )

    changed_conditions = _conditions(dependencies={"parser": "2.0"})
    result = recall_repair_episodes(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=changed_conditions,
        patch_hash="patch-timeout-only",
        session_allowlist=[_SOURCE],
    )

    assert result["code"] == "OK"
    assert len(result["failures"]) == 1
    failure = result["failures"][0]
    assert failure["id"] == t1.id
    assert failure["match"] == "changed"
    assert "warning" not in failure


def test_verified_size_limit_fix_links_regression_check(tmp_path: Path) -> None:
    conditions = _conditions()
    s1_receipt = _receipt(tmp_path, outcome="verified")
    s1 = _record(
        tmp_path,
        hypothesis="lower size limit to 25",
        patch_hash="patch-size-limit",
        conditions=conditions,
        outcome="verified",
        receipt_ref=s1_receipt,
    )

    result = recall_repair_episodes(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=conditions,
        session_allowlist=[_SOURCE],
    )

    assert len(result["verified_repairs"]) == 1
    verified = result["verified_repairs"][0]
    assert verified["id"] == s1.id
    assert verified["receipt_ref"] == s1_receipt

    # The receipt actually links to a real, independently retrievable regression check.
    store = TypedArtifactStore(tmp_path)
    linked = store.get_current(s1_receipt)
    assert linked is not None
    assert linked.content["outcome"] == "verified"
    assert linked.content["passed_count"] == 1


def test_revert_and_fix_label_do_not_prove_cause(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _record(
            tmp_path,
            hypothesis="apply upstream fix",
            patch_hash="patch-revert",
            conditions=_conditions(),
            outcome="verified",
            receipt_ref=None,
            commit_message="fix: patched upload timeout",
        )

    untested = _record(
        tmp_path,
        hypothesis="revert to previous timeout handling",
        patch_hash="patch-revert",
        conditions=_conditions(),
        outcome="untested",
        receipt_ref=None,
        commit_message="revert previous timeout patch",
    )

    result = recall_repair_episodes(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=_conditions(),
        session_allowlist=[_SOURCE],
    )

    assert [e["id"] for e in result["untested_hypotheses"]] == [untested.id]
    assert untested.id not in {e["id"] for e in result["verified_repairs"]}
    assert untested.id not in {e["id"] for e in result["failures"]}


def test_failed_and_successful_conditions_remain_distinct(tmp_path: Path) -> None:
    conditions = _conditions()
    t1 = _record(
        tmp_path,
        hypothesis="increase timeout to 60s",
        patch_hash="patch-timeout-only",
        conditions=conditions,
        outcome="failed",
        receipt_ref=_receipt(tmp_path, outcome="failed"),
    )
    s1 = _record(
        tmp_path,
        hypothesis="lower size limit to 25",
        patch_hash="patch-size-limit",
        conditions=conditions,
        outcome="verified",
        receipt_ref=_receipt(tmp_path, outcome="verified"),
    )

    result = recall_repair_episodes(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=conditions,
        session_allowlist=[_SOURCE],
    )

    failure_ids = {e["id"] for e in result["failures"]}
    verified_ids = {e["id"] for e in result["verified_repairs"]}
    assert failure_ids == {t1.id}
    assert verified_ids == {s1.id}
    assert failure_ids.isdisjoint(verified_ids)


def test_prepare_exposes_untested_hypothesis_without_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conditions = _conditions()
    untested = _record(
        tmp_path,
        hypothesis="try increasing retry backoff",
        patch_hash="patch-backoff",
        conditions=conditions,
        outcome="untested",
        receipt_ref=None,
    )

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("prepare must execute zero subprocess calls")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)

    tool = MemoryTool()
    for operation in ("prepare", "resume"):
        result = tool.run(
            tmp_path,
            operation=operation,  # type: ignore[arg-type]
            request={"task": _SYMPTOM, "conditions": conditions},
            session_allowlist=[_SOURCE],
        )
        assert result["status"] == "ok"
        assert result["raw"]["code"] == "OK"
        data = result["raw"]["data"]
        assert [e["id"] for e in data["untested_hypotheses"]] == [untested.id]
        assert {"id": untested.id, "version": untested.artifact_version} in data[
            "evidence_refs"
        ]
        # `prepare`/`resume` never automatically prohibits a patch: no denial/blocking
        # field, just recorded evidence for the caller to decide from.
        assert "denied" not in data
        assert "prohibited" not in data

    # `prepare_memory` itself is also directly zero-subprocess (not only through the tool).
    direct = prepare_memory(
        project_root=tmp_path,
        symptom=_SYMPTOM,
        conditions=conditions,
        session_allowlist=[_SOURCE],
    )
    assert direct["code"] == "OK"
    assert len(direct["untested_hypotheses"]) == 1
