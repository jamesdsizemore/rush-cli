"""MC09 (Phase 63) `plan_checks`: ranks required checks by real evidence strength without
ever dropping or adding required membership -- reordering only.
"""

from __future__ import annotations

from pathlib import Path

from rush.memory.experience import write_observation
from rush.memory.verification import plan_checks
from rush.tools.memory import MemoryTool


def test_past_payload_regression_prioritizes_contract_check(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="contract",
        source="test:regression",
        content={
            "check_id": "payload-contract",
            "targets": ["payload.user_id"],
            "status": "fail",
        },
        project_root=tmp_path,
    )
    required_checks = [
        {"id": "slow-general", "argv": ["pytest", "tests/slow"], "cwd": "."},
        {"id": "payload-contract", "argv": ["pytest", "tests/contract"], "cwd": "."},
        {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[{"id": "payload.user_id", "version": None}],
        required_checks=required_checks,
        environment={},
    )

    assert plan["checks"][0]["ids"] == ["payload-contract"]
    assert plan["checks"][0]["rank"] == 0
    all_ids = [check_id for check in plan["checks"] for check_id in check["ids"]]
    assert sorted(all_ids) == ["checkout", "payload-contract", "slow-general"]
    assert len(all_ids) == 3, "each required check must appear exactly once"
    assert plan["required_ids"] == ["slow-general", "payload-contract", "checkout"]


def test_required_checks_remain_after_early_pass(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="test",
        source="test:early-pass",
        content={
            "check_id": "checkout",
            "targets": ["checkout.total"],
            "status": "ok",
        },
        project_root=tmp_path,
    )
    required_checks = [
        {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
        {"id": "slow-general", "argv": ["pytest", "tests/slow"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[{"id": "checkout.total", "version": None}],
        required_checks=required_checks,
        environment={},
    )

    all_ids = {check_id for check in plan["checks"] for check_id in check["ids"]}
    assert all_ids == {"checkout", "slow-general"}, (
        "an already-passing measured check must never be dropped from the plan"
    )
    assert plan["required_ids"] == ["checkout", "slow-general"]
    checkout_entry = next(c for c in plan["checks"] if "checkout" in c["ids"])
    assert checkout_entry["rank"] == 1


def test_dynamic_consumer_gap_is_explicit(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="source_graph",
        operation_id="blast-radius",
        source="test:dynamic-consumer",
        content={"targets": ["payload.user_id"]},
        project_root=tmp_path,
    )
    required_checks = [
        {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[{"id": "payload.user_id", "version": None}],
        required_checks=required_checks,
        environment={},
    )

    assert plan["coverage_gaps"], "an unmeasured dynamic consumer must surface a gap"
    gap = plan["coverage_gaps"][0]
    assert gap["target_id"] == "payload.user_id"
    assert gap["check_id"] is None
    checkout_entry = plan["checks"][0]
    assert checkout_entry["rank"] == 3, (
        "a structural relation naming no required check must never be invented as "
        "coverage for an unrelated check"
    )


def test_missing_engine_keeps_required_check_unresolved(tmp_path: Path) -> None:
    required_checks = [
        {
            "id": "checkout",
            "argv": ["pytest", "tests/checkout"],
            "cwd": ".",
            "engine": "pytest",
        },
        {
            "id": "e2e-browser",
            "argv": ["playwright", "test"],
            "cwd": ".",
            "engine": "playwright",
        },
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[],
        required_checks=required_checks,
        environment={"available_engines": ["pytest"]},
    )

    assert plan["required_ids"] == ["checkout", "e2e-browser"]
    assert len(plan["checks"]) == 2
    browser_entry = next(c for c in plan["checks"] if "e2e-browser" in c["ids"])
    assert browser_entry["availability"] == "unresolved"
    assert any("engine unavailable" in reason for reason in browser_entry["reasons"])


def test_security_license_version_change_reopens_finding(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="security_dependency",
        operation_id="license-matrix",
        source="test:license-scan",
        content={
            "check_id": "dependency-audit",
            "targets": ["left-pad"],
            "status": "ok",
            "metadata": {"dependency": {"name": "left-pad", "version": "1.0.0"}},
        },
        project_root=tmp_path,
    )
    required_checks = [
        {"id": "dependency-audit", "argv": ["rush", "license-matrix"], "cwd": "."},
        {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[{"id": "left-pad", "version": "2.0.0"}],
        required_checks=required_checks,
        environment={},
    )

    assert plan["checks"][0]["ids"] == ["dependency-audit"]
    assert plan["checks"][0]["rank"] == 0
    assert any("reopened" in reason for reason in plan["checks"][0]["reasons"])
    assert plan["required_ids"] == ["dependency-audit", "checkout"]


def test_mutation_observation_is_not_invented_coverage(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="mutation",
        source="test:mutation",
        content={
            "check_id": "checkout",
            "targets": ["checkout.total"],
            "metadata": {"killed": False},
        },
        project_root=tmp_path,
    )
    required_checks = [
        {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[{"id": "checkout.total", "version": None}],
        required_checks=required_checks,
        environment={},
    )

    checkout_entry = plan["checks"][0]
    assert checkout_entry["rank"] == 3, (
        "a surviving mutant must never be invented as measured coverage"
    )
    assert not any(
        "measured coverage" in reason for reason in checkout_entry["reasons"]
    )
    assert plan["coverage_gaps"], "a surviving mutation must surface an explicit gap"
    gap = plan["coverage_gaps"][0]
    assert gap["check_id"] == "checkout"
    assert "mutation" in gap["reason"]


def test_duplicate_check_identity_deduplicated_without_dropping_required_ids(
    tmp_path: Path,
) -> None:
    required_checks = [
        {"id": "checkout-a", "argv": ["pytest", "tests/checkout"], "cwd": "."},
        {"id": "checkout-b", "argv": ["pytest", "tests/checkout"], "cwd": "."},
    ]

    plan = plan_checks(
        project_root=tmp_path,
        changed_targets=[],
        required_checks=required_checks,
        environment={},
    )

    assert len(plan["checks"]) == 1, (
        "identical argv/cwd/environment must merge to one run"
    )
    assert set(plan["checks"][0]["ids"]) == {"checkout-a", "checkout-b"}
    assert plan["required_ids"] == ["checkout-a", "checkout-b"]


def test_memory_tool_plan_checks_operation_returns_ranked_plan(tmp_path: Path) -> None:
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="contract",
        source="test:regression",
        content={
            "check_id": "payload-contract",
            "targets": ["payload.user_id"],
            "status": "fail",
        },
        project_root=tmp_path,
    )

    result = MemoryTool().run(
        tmp_path,
        operation="plan_checks",
        request={
            "changed_targets": [{"id": "payload.user_id", "version": None}],
            "required_checks": [
                {"id": "checkout", "argv": ["pytest", "tests/checkout"], "cwd": "."},
                {
                    "id": "payload-contract",
                    "argv": ["pytest", "tests/contract"],
                    "cwd": ".",
                },
            ],
            "environment": {},
        },
    )

    assert result["status"] == "ok"
    data = result["raw"]["data"]
    assert data["checks"][0]["ids"] == ["payload-contract"]
    assert data["required_ids"] == ["checkout", "payload-contract"]
