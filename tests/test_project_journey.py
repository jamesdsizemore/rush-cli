"""Tests for Phase 65 P65-09: installed end-to-end acceptance (F35, F41).

Exercises `scripts.benchmarks.run.run_project_journey` -- the single, shared
journey builder also used by `python -m scripts.benchmarks.run --suite
project_journey` (no second harness) -- across the real, already-implemented
P65-01..08/P65-10 pipeline: install, provision, two isolated projects
(Python+JS+IaC+docs and a second Python-only project), a connected-agent
isolated memory profile, scan, aggregate, agent handoff, rescan, and memory
retrieval.

Every filesystem interaction stays under `tmp_path`; nothing touches a real
installed client config or the real production Rush data root. The scan
step is scoped to `[ReviewTool()]` (mirroring `tests/test_scan_handoff.py`'s
own determinism precedent) so seeded Python defects produce an exact,
host-independent finding count -- JS/IaC/docs engines are real but honestly
unavailable in this sandbox, proven via a real `apply_provision_plan`
`SYSTEM_PREREQUISITE_REQUIRED` failure, never fabricated coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.benchmarks.run import run_project_journey

_MISSING_DOCSTRING = "missing-docstring"
_NAMING = "naming"


@pytest.fixture(scope="module")
def journey(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Runs the whole real pipeline exactly once; every test below asserts
    a different facet of this single, shared execution."""
    tmp_root = tmp_path_factory.mktemp("project-journey")
    return run_project_journey(tmp_root)


def test_install_produces_a_verified_binary_and_activates_memory(
    journey: dict[str, Any],
) -> None:
    install = journey["install"]
    assert install["status"] == "ok", install
    assert Path(install["raw"]["binary"]["path"]).is_file()
    # agents="none" reports every known adapter as unsupported/not-detected --
    # never silently omitted, never falsely "active".
    assert {a["agent_id"] for a in install["raw"]["agents"]} == {
        "claude-desktop",
        "claude-code",
        "cursor",
        "windsurf",
        "zed",
        "codex",
    }
    assert all(a["state"] == "unsupported" for a in install["raw"]["agents"])
    assert all(a["detected"] is False for a in install["raw"]["agents"])
    assert install["raw"]["project"] is None


def test_two_projects_are_registered_with_distinct_ids(
    journey: dict[str, Any],
) -> None:
    assert journey["project_a_id"] != journey["project_b_id"]
    assert journey["run_a"].project_id == journey["project_a_id"]
    assert journey["run_b"].project_id == journey["project_b_id"]


def test_provision_reports_missing_toolchain_never_a_fabricated_install(
    journey: dict[str, Any],
) -> None:
    failed = journey["provision_result"].failed
    assert journey["provision_result"].applied == {}
    assert set(failed) == {"eslint", "checkov", "markdownlint-cli"}
    for engine_id, manager in (
        ("eslint", "npm"),
        ("checkov", "uv"),
        ("markdownlint-cli", "npm"),
    ):
        assert failed[engine_id]["code"] == "SYSTEM_PREREQUISITE_REQUIRED"
        assert manager in failed[engine_id]["message"]


def test_connected_agent_profile_is_isolated_across_projects(
    journey: dict[str, Any],
) -> None:
    state_a = journey["agent_state_a"]
    state_b = journey["agent_state_b"]
    assert state_a is not None
    assert state_a["connected"] is True
    assert state_a["consent"] is True
    assert state_a["last_observation"] == {"tool": "scan", "project": "a"}

    assert state_b is not None
    assert state_b["connected"] is False
    assert state_b["last_observation"] is None


def test_scan_produces_exact_seeded_coverage_with_source_identities(
    journey: dict[str, Any],
) -> None:
    findings_a = journey["run_a"].aggregate.get("findings")
    assert findings_a is not None
    assert len(findings_a) == 3
    by_line = {finding["line"]: finding for finding in findings_a}
    assert by_line[1]["rule"] == _MISSING_DOCSTRING
    assert by_line[1]["message"] == "function 'unreviewed' has no docstring"
    assert by_line[5]["rule"] == _MISSING_DOCSTRING
    assert by_line[5]["message"] == "function 'compute_value' has no docstring"
    assert by_line[9]["rule"] == _NAMING
    assert all(f["provenance"] == "review/heuristic-v1" for f in findings_a)
    assert len({f["finding_id"] for f in findings_a}) == 3

    findings_b = journey["run_b"].aggregate.get("findings")
    assert findings_b is not None
    assert len(findings_b) == 1
    assert findings_b[0]["rule"] == _MISSING_DOCSTRING
    assert findings_b[0]["message"] == "function 'also_unreviewed' has no docstring"

    # Cross-project isolation: no finding_id from A ever appears in B.
    assert {f["finding_id"] for f in findings_a}.isdisjoint(
        {f["finding_id"] for f in findings_b}
    )
    assert journey["run_a"].aggregate["status"] == "ok"
    # The real 121-engine registry is scheduled too (not just ReviewTool) --
    # every JS/IaC/docs-class engine candidate is honestly "unavailable" in
    # this sandbox, so the run's own real state is "incomplete", never a
    # fabricated "completed" from exit-code-only reasoning (F35).
    assert journey["run_a"].run_state == "incomplete"
    outcomes = {c.outcome for c in journey["run_a"].candidate_results}
    assert "unavailable" in outcomes
    assert "executed" in outcomes


def test_handoff_completes_but_is_never_auto_promoted_to_verified(
    journey: dict[str, Any],
) -> None:
    handoff = journey["handoff"]
    completed = journey["completed"]
    status = journey["handoff_status"]

    assert handoff.state == "prepared"
    assert set(handoff.finding_ids) == {
        f["finding_id"] for f in journey["run_a"].aggregate["findings"]
    }
    assert completed.state == "agent_reported_complete"
    assert completed.agent_reported_complete_artifact_ids == ("agent-patch-1",)
    assert completed.state not in ("resolved", "verified")

    assert status["state"] == "agent_reported_complete"
    assert "session_capability" not in status
    assert "delivery_nonce" not in status


def test_rescan_against_real_execute_scan_shows_unmodified_findings_persisting(
    journey: dict[str, Any],
) -> None:
    comparison = journey["rescan_result"]["comparison"]
    seeded_ids = {f["finding_id"] for f in journey["run_a"].aggregate["findings"]}
    assert comparison["baseline_run_id"] == journey["run_a"].run_id
    assert set(comparison["persisting"]) == seeded_ids
    assert comparison["resolved"] == []
    assert comparison["new"] == []
    assert comparison["unverified"] == []


def test_memory_retrieval_returns_the_real_written_source_identity(
    journey: dict[str, Any],
) -> None:
    recalled = journey["memory_recall"]
    assert recalled["status"] == "ok"
    items = recalled["raw"]["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["source"] == "journey-session"
    assert journey["handoff"].handoff_id in item["excerpt"]
    assert journey["run_a"].run_id in item["excerpt"]
