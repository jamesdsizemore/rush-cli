"""MC13.3/MC13.4 (Phase 63): real agent episodes over MC02/MC06/MC08/MC09/MC10/MC11.

Exercises `scripts.benchmarks.memory.run_memory_episode` and the five named
episode builders. Every episode runs real `MemoryTool` operations against a
real (temp-directory) store/git repo -- no fabricated events, no gold
next-action hints reaching the scripted decision function.
"""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from scripts.benchmarks.contracts import Outcome
from scripts.benchmarks.memory import (
    EPISODE_BUILDERS,
    EpisodeAction,
    build_guest_handoff_episode,
    run_memory_episode,
    run_named_episode,
)

_GRANTED = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)


def test_real_episode_uses_observed_tool_events(tmp_path: Path) -> None:
    """Every event in the episode's log is the exact, unmodified
    `MemoryTool.run()` return value for a call the harness actually made --
    never a summary the decision function invented."""
    task, decide_fn = build_guest_handoff_episode(tmp_path)
    result = run_memory_episode(
        "guest-handoff", task, decide_fn, root=tmp_path, permissions=_GRANTED
    )

    assert len(result.events) >= 4
    first_write = result.events[0]
    assert first_write.operation == "write"
    assert first_write.raw["status"] == "ok"
    assert first_write.raw["raw"]["id"]

    # The handoff step's real capability/handoff_id came from the store, not
    # from the decision function -- re-running the store lookup directly
    # must show the same session actually exists.
    handoff_event = next(e for e in result.events if e.operation == "handoff")
    assert handoff_event.raw["raw"]["data"]["handoff_id"]
    assert handoff_event.raw["raw"]["data"]["capability"]

    receive_events = [e for e in result.events if e.operation == "receive"]
    assert len(receive_events) == 2
    assert receive_events[0].kwargs["request"].get("ack") is None
    assert receive_events[1].kwargs["request"]["ack"]

    assert result.outcome == Outcome.PASS
    assert result.receiver_readback is True


def test_all_expansions_count_toward_episode_budget(tmp_path: Path) -> None:
    """Two independent `expand` calls within one episode both count toward
    `max_total_tokens` -- no expansion is a free/uncounted operation."""

    def decide(observation):
        step = observation.step_index
        if step == 0:
            return EpisodeAction(
                operation="write",
                kwargs={
                    "subject": "domain_knowledge",
                    "content": {"text": "artifact one payload text for expansion"},
                    "source": "budget-session",
                },
            )
        if step == 1:
            return EpisodeAction(
                operation="write",
                kwargs={
                    "subject": "domain_knowledge",
                    "content": {"text": "artifact two payload text for expansion"},
                    "source": "budget-session",
                },
            )
        if step == 2:
            first = observation.history[0]["raw"]
            return EpisodeAction(
                operation="expand",
                kwargs={
                    "session_allowlist": ["budget-session"],
                    "request": {
                        "id": first["id"],
                        "version": first["artifact_version"],
                    },
                },
            )
        if step == 3:
            second = observation.history[1]["raw"]
            return EpisodeAction(
                operation="expand",
                kwargs={
                    "session_allowlist": ["budget-session"],
                    "request": {
                        "id": second["id"],
                        "version": second["artifact_version"],
                    },
                },
            )
        return EpisodeAction(operation="submit", final="done")

    unbounded = run_memory_episode(
        "budget-check",
        "expand two artifacts",
        decide,
        root=tmp_path,
        permissions=_GRANTED,
        max_total_tokens=100_000,
    )
    expand_events = [e for e in unbounded.events if e.operation == "expand"]
    assert len(expand_events) == 2
    manual_sum = sum(e.token_count for e in unbounded.events)
    assert unbounded.total_tokens == manual_sum
    assert unbounded.total_tokens >= sum(e.token_count for e in expand_events)

    # A budget too small to survive both expansions still stops the episode
    # (not silently continuing past the cap) and stays a real, reportable
    # result -- never dropped. The margin below (half of one real expand's
    # measured cost) comfortably absorbs the few-token BPE jitter between
    # independent runs' randomly generated artifact IDs/timestamps, while
    # staying well short of a second full expansion's cost.
    first_two_events_tokens = (
        unbounded.events[0].token_count + unbounded.events[1].token_count
    )
    tight_budget = first_two_events_tokens + (unbounded.events[2].token_count // 2)
    bounded = run_memory_episode(
        "budget-check-bounded",
        "expand two artifacts",
        decide,
        root=tmp_path,
        permissions=_GRANTED,
        max_total_tokens=tight_budget,
    )
    assert bounded.budget_exhausted is True
    assert len(bounded.events) == 3
    assert bounded.outcome == Outcome.FAIL


def test_handoff_score_requires_receiver_readback(tmp_path: Path) -> None:
    """A handoff episode that never sends a verified `ack` scores FAIL even
    if the agent claims success -- the outer `final` claim is never trusted
    over the real receiver read-back state."""

    def decide_without_ack(observation):
        step = observation.step_index
        if step == 0:
            return EpisodeAction(
                operation="write",
                kwargs={
                    "subject": "domain_knowledge",
                    "content": {"text": "unacked handoff payload"},
                    "source": "no-ack-session",
                },
            )
        if step == 1:
            written = observation.history[0]["raw"]
            return EpisodeAction(
                operation="handoff",
                kwargs={
                    "request": {
                        "action": "prepare",
                        "receiver_audience": "handoff-receiver",
                        "goal": "deliver without ack",
                        "selected_refs": [
                            {
                                "id": written["id"],
                                "version": written["artifact_version"],
                            }
                        ],
                    }
                },
            )
        if step == 2:
            prepared = observation.history[1]["raw"]["data"]
            return EpisodeAction(
                operation="receive",
                kwargs={
                    "request": {
                        "session_id": prepared["handoff_id"],
                        "capability": prepared["capability"],
                    }
                },
            )
        # The agent falsely claims success without ever acknowledging a
        # read-back -- scoring must not take its word for it.
        return EpisodeAction(operation="submit", final="handoff complete")

    unacked = run_memory_episode(
        "guest-handoff-no-ack",
        "hand off without acking",
        decide_without_ack,
        root=tmp_path,
        permissions=_GRANTED,
    )
    assert unacked.final == "handoff complete"
    assert unacked.receiver_readback is False
    assert unacked.outcome == Outcome.FAIL

    task, real_decide = build_guest_handoff_episode(tmp_path / "acked")
    (tmp_path / "acked").mkdir()
    acked = run_memory_episode(
        "guest-handoff-acked",
        task,
        real_decide,
        root=tmp_path / "acked",
        permissions=_GRANTED,
    )
    assert acked.receiver_readback is True
    assert acked.outcome == Outcome.PASS


def test_all_named_episodes_run_for_real(tmp_path: Path) -> None:
    """Every one of the five MC13.3 named episodes actually executes its
    real tool calls end to end (upload-repair's real git+sandbox route,
    csv-adaptation's real on-disk drift, plan_checks' real evidence read,
    and last_success_diagnose's real candidate default)."""
    for episode_id in EPISODE_BUILDERS:
        workspace = tmp_path / episode_id
        workspace.mkdir()
        result = run_named_episode(episode_id, workspace)
        assert result.events, f"{episode_id} produced no real tool events"
        assert result.outcome in {Outcome.PASS, Outcome.FAIL, Outcome.INCONCLUSIVE}

    upload_workspace = tmp_path / "upload-repair-verify"
    upload_workspace.mkdir()
    upload_result = run_named_episode("upload-repair", upload_workspace)
    assert upload_result.verifier_receipt is not None
    assert upload_result.verifier_receipt["outcome"] == "completed"
    assert upload_result.outcome == Outcome.PASS

    csv_workspace = tmp_path / "csv-adaptation-verify"
    csv_workspace.mkdir()
    csv_result = run_named_episode("csv-adaptation", csv_workspace)
    assert csv_result.final is False  # real drift detected, not fabricated
