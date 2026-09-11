"""MC07 (Phase 63) confirmed intent: an executed behavior's requirement, confirmed only by
a resolvable, currently-`STATED` user statement -- never by a caller flag, an agent-authored
timestamp, or an imported/inferred role label (docs/phase-plans/MC07.md)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from rush.memory.intent import check_intent, record_intent, supersede_intent
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.memory.trust import default_entry_tier


def _stated_statement(
    project_root: Path, statement_id: str, *, requires_account: bool
) -> dict[str, Any]:
    """An authorized local STATED artifact requiring (or not) an account for checkout --
    the real `write()` -> `promote(user_stated=True)` path, never a shortcut trust_tier."""
    store = TypedArtifactStore(project_root)
    store.write(
        MemoryArtifact(
            id=statement_id,
            family="memory",
            subject="architectural_decision",
            trust_tier=default_entry_tier("local_tool"),
            content={
                "statement": "guest checkout requires an account"
                if requires_account
                else "guest checkout is allowed without creating an account",
                "requires_account": requires_account,
            },
            source="user:cli",
            created_at=time.time(),
        )
    )
    artifact, decision = store.promote(statement_id, user_stated=True)
    assert decision.promoted, decision.denial_reason
    return {"id": artifact.id, "version": artifact.artifact_version}


def _imported_label(
    project_root: Path, label_id: str, *, requires_account: bool
) -> dict[str, Any]:
    """A real, resolvable artifact that is never STATED -- an imported role label carrying a
    newer agent timestamp than any real user statement. Neither confirms nor supersedes."""
    store = TypedArtifactStore(project_root)
    artifact = store.write(
        MemoryArtifact(
            id=label_id,
            family="handoff",
            subject="active_context",
            trust_tier=default_entry_tier("cross_tool_handoff"),
            content={"role": "agent", "requires_account": requires_account},
            source="agent:import",
            created_at=time.time() + 10_000.0,
        )
    )
    return {"id": artifact.id, "version": artifact.artifact_version}


def _execution_receipt(
    project_root: Path,
    receipt_id: str,
    *,
    behavior_id: str,
    status: str,
    revision: str,
) -> dict[str, Any]:
    """A real executed-command receipt (`ToolResult.status`-shaped, MC05's own vocabulary)."""
    store = TypedArtifactStore(project_root)
    artifact = store.write(
        MemoryArtifact(
            id=receipt_id,
            family="experience",
            subject="episodic",
            trust_tier=default_entry_tier("local_tool"),
            content={
                "kind": "observation",
                "behavior_id": behavior_id,
                "status": status,
                "revision": revision,
                "labels": ["guest-checkout-verified"],
            },
            source="pytest:guest-checkout",
            created_at=time.time(),
        )
    )
    return {"id": artifact.id, "version": artifact.artifact_version}


def _trace_tag(
    project_root: Path, tag_id: str, *, behavior_id: str, revision: str
) -> dict[str, Any]:
    """A bare label/trace record -- carries neither `status` nor `outcome`, so it is never
    mistaken for real behavioral verification."""
    store = TypedArtifactStore(project_root)
    artifact = store.write(
        MemoryArtifact(
            id=tag_id,
            family="experience",
            subject="episodic",
            trust_tier=default_entry_tier("local_tool"),
            content={
                "kind": "trace",
                "behavior_id": behavior_id,
                "revision": revision,
                "tags": ["guest-checkout-ok"],
            },
            source="pytest:guest-checkout",
            created_at=time.time(),
        )
    )
    return {"id": artifact.id, "version": artifact.artifact_version}


def test_inferred_preference_cannot_confirm_itself(tmp_path: Path) -> None:
    inferred_label = _imported_label(
        tmp_path, "inferred-preference-1", requires_account=False
    )

    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-inferred",
        behavior_id="guest-checkout",
        statement_ref=None,
    )
    assert created["code"] == "OK"
    assert created["status"] == "candidate"

    # Even pointing statement_ref at a real, resolvable artifact that is never STATED (an
    # inferred/imported record masquerading as a statement) never confirms it.
    pointed = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-inferred",
        statement_ref=inferred_label,
        expected_version=created["version"],
    )
    assert pointed["code"] == "OK"
    assert pointed["status"] == "candidate"


def test_guest_checkout_break_detected_by_execution(tmp_path: Path) -> None:
    statement = _stated_statement(
        tmp_path, "req-guest-checkout", requires_account=False
    )
    original = _execution_receipt(
        tmp_path,
        "receipt-rev-a",
        behavior_id="guest-checkout",
        status="ok",
        revision="rev-a",
    )
    regression = _execution_receipt(
        tmp_path,
        "receipt-rev-b",
        behavior_id="guest-checkout",
        status="fail",
        revision="rev-b",
    )

    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy",
        behavior_id="guest-checkout",
        statement_ref=statement,
        check_refs=[original],
    )
    assert created["code"] == "OK"
    assert created["status"] == "confirmed"

    updated = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy",
        check_refs=[original, regression],
        expected_version=created["version"],
    )
    assert updated["code"] == "OK"
    assert updated["status"] == "confirmed"

    at_original = check_intent(
        project_root=tmp_path, intent_id="guest-buy", current_revision="rev-a"
    )
    assert at_original["code"] == "OK"
    assert at_original["passed"] is True

    # Regression fails despite the same "labels" metadata as the original passing receipt --
    # only the real executed status, bound to the current revision, decides this.
    at_regression = check_intent(
        project_root=tmp_path, intent_id="guest-buy", current_revision="rev-b"
    )
    assert at_regression["code"] == "OK"
    assert at_regression["passed"] is False


def test_trace_tag_is_not_behavioral_verification(tmp_path: Path) -> None:
    statement = _stated_statement(
        tmp_path, "req-guest-checkout-2", requires_account=False
    )
    tag = _trace_tag(
        tmp_path, "trace-only-1", behavior_id="guest-checkout", revision="rev-a"
    )

    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-2",
        behavior_id="guest-checkout",
        statement_ref=statement,
        check_refs=[tag],
    )
    assert created["code"] == "OK"
    assert created["status"] == "confirmed"

    result = check_intent(
        project_root=tmp_path, intent_id="guest-buy-2", current_revision="rev-a"
    )
    assert result["code"] == "UNRESOLVED"


def test_explicit_user_change_supersedes_old_intent(tmp_path: Path) -> None:
    guest_ok = _stated_statement(tmp_path, "req-guest-ok", requires_account=False)
    account_required = _stated_statement(
        tmp_path, "req-account-required", requires_account=True
    )

    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-3",
        behavior_id="guest-checkout",
        statement_ref=guest_ok,
    )
    assert created["code"] == "OK"
    assert created["status"] == "confirmed"

    superseded = supersede_intent(
        project_root=tmp_path,
        intent_id="guest-buy-3",
        expected_old_version=created["version"],
        new_statement_ref=account_required,
        new_behavior_id="account-required-checkout",
    )
    assert superseded["code"] == "OK"
    assert superseded["status"] == "confirmed"
    assert superseded["behavior_id"] == "account-required-checkout"
    assert superseded["statement_ref"] == account_required
    assert superseded["supersedes_version"] == created["version"]

    store = TypedArtifactStore(tmp_path)
    current = store.get_current("guest-buy-3")
    assert current is not None
    assert current.content["statement_ref"] == account_required
    assert current.content["behavior_id"] == "account-required-checkout"

    # Prior rationale/evidence is retained, never deleted.
    prior_bytes = store.get_version_content("guest-buy-3", created["version"])
    assert prior_bytes is not None
    prior_content = json.loads(prior_bytes)
    assert prior_content["statement_ref"] == guest_ok
    assert prior_content["behavior_id"] == "guest-checkout"


def test_agent_timestamp_cannot_supersede_user_intent(tmp_path: Path) -> None:
    guest_ok = _stated_statement(tmp_path, "req-guest-ok-2", requires_account=False)
    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-4",
        behavior_id="guest-checkout",
        statement_ref=guest_ok,
    )
    assert created["code"] == "OK"
    assert created["status"] == "confirmed"

    # A newer agent timestamp and an imported role label -- neither is a user statement.
    agent_label = _imported_label(tmp_path, "agent-import-1", requires_account=True)

    attempt = supersede_intent(
        project_root=tmp_path,
        intent_id="guest-buy-4",
        expected_old_version=created["version"],
        new_statement_ref=agent_label,
        new_behavior_id="account-required-checkout",
    )
    assert attempt["code"] == "E_PERMISSION"

    store = TypedArtifactStore(tmp_path)
    current = store.get_current("guest-buy-4")
    assert current is not None
    assert current.artifact_version == created["version"]
    assert current.content["statement_ref"] == guest_ok
    assert current.content["behavior_id"] == "guest-checkout"


def test_intent_check_bound_to_current_revision(tmp_path: Path) -> None:
    statement = _stated_statement(tmp_path, "req-guest-ok-3", requires_account=False)
    receipt = _execution_receipt(
        tmp_path,
        "receipt-rev-a-2",
        behavior_id="guest-checkout",
        status="ok",
        revision="rev-a",
    )
    created = record_intent(
        project_root=tmp_path,
        intent_id="guest-buy-5",
        behavior_id="guest-checkout",
        statement_ref=statement,
        check_refs=[receipt],
    )
    assert created["code"] == "OK"
    assert created["status"] == "confirmed"

    stale = check_intent(
        project_root=tmp_path, intent_id="guest-buy-5", current_revision="rev-z"
    )
    assert stale["code"] == "UNRESOLVED"

    current_ok = check_intent(
        project_root=tmp_path, intent_id="guest-buy-5", current_revision="rev-a"
    )
    assert current_ok["code"] == "OK"
    assert current_ok["passed"] is True

    unbound = check_intent(project_root=tmp_path, intent_id="guest-buy-5")
    assert unbound["code"] == "OK"
    assert unbound["passed"] is True
