"""Closed-loop multi-framework test suite verifier."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Self

from rush.patch.contracts import (
    PatchContract,
    PatchOutcome,
    PatchVerificationError,
    PatchVerificationResult,
)
from rush.tools.common import resolve_binary, run_subprocess


class VerificationOutcomeTuple(tuple):
    """Tuple (bool, str) with outcome and result attributes."""

    outcome: PatchOutcome
    result: PatchVerificationResult | None

    def __new__(
        cls,
        success: bool,
        summary: str,
        outcome: PatchOutcome = "completed",
        result: PatchVerificationResult | None = None,
    ) -> Self:
        t = super().__new__(cls, (success, summary))
        t.outcome = outcome
        t.result = result
        return t


class PatchVerifier:
    """Executes detected project test runners inside the sandbox to verify patch safety."""

    def __init__(
        self, sandbox_dir: Path, contract: PatchContract | None = None
    ) -> None:
        self.sandbox_dir = sandbox_dir.resolve()
        self.contract = contract
        self.last_result: PatchVerificationResult | None = None

    def verify_patch(
        self, contract: PatchContract | None = None
    ) -> VerificationOutcomeTuple:
        active_contract = contract or self.contract

        # 1. Base commit and tree digest drift detection
        if active_contract is not None:
            # Policy check: privileged or policy-changing review classes
            if active_contract.review_class in ("policy-changing", "privileged"):
                summary = (
                    f"Policy-changing patch with review_class '{active_contract.review_class}' "
                    "cannot receive ordinary verified promotion."
                )
                self.last_result = PatchVerificationResult(
                    outcome="failed",
                    executed_commands=(),
                    passed_count=0,
                    summary=summary,
                    rollback_applied=False,
                )
                return VerificationOutcomeTuple(
                    False, summary, outcome="failed", result=self.last_result
                )

            # Check base commit drift in sandbox
            head_proc = run_subprocess(
                ["git", "rev-parse", "HEAD"], cwd=self.sandbox_dir
            )
            if head_proc.returncode == 0:
                current_head = head_proc.stdout.strip()
                if (
                    active_contract.base_commit
                    and current_head != active_contract.base_commit
                ):
                    raise PatchVerificationError(
                        f"Base commit drift detected: contract expects {active_contract.base_commit}, "
                        f"sandbox HEAD is {current_head}."
                    )

            # Check base tree digest drift in sandbox
            tree_proc = run_subprocess(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=self.sandbox_dir
            )
            if tree_proc.returncode == 0:
                current_tree = tree_proc.stdout.strip()
                if (
                    active_contract.base_tree_digest
                    and current_tree != active_contract.base_tree_digest
                ):
                    raise PatchVerificationError(
                        f"Base tree digest drift detected: contract expects {active_contract.base_tree_digest}, "
                        f"sandbox tree is {current_tree}."
                    )

        executed_commands: list[dict[str, Any]] = []
        passed_count = 0
        failed_details: list[str] = []
        project_env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(self.sandbox_dir / "src"), str(self.sandbox_dir))
            ),
        }

        # 2. Execute explicit command plan if bound in contract
        if active_contract and active_contract.required_commands:
            for plan in active_contract.required_commands:
                cmd_cwd = (self.sandbox_dir / plan.cwd_relative).resolve()
                proc = run_subprocess(
                    list(plan.command),
                    cwd=cmd_cwd,
                    timeout=plan.timeout_seconds,
                    env=project_env,
                )
                passed = proc.returncode == plan.expected_exit_code
                cmd_record = {
                    "command": plan.command,
                    "cwd": str(cmd_cwd),
                    "exit_code": proc.returncode,
                    "expected_exit_code": plan.expected_exit_code,
                    "passed": passed,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
                executed_commands.append(cmd_record)
                if passed:
                    passed_count += 1
                else:
                    failed_details.append(
                        f"Command '{' '.join(plan.command)}' failed with exit code {proc.returncode}: "
                        f"{proc.stderr or proc.stdout}"
                    )
        else:
            # 3. Auto-detected project test runners
            # Pytest
            if (
                (self.sandbox_dir / "pytest.ini").exists()
                or (self.sandbox_dir / "tests").exists()
            ) and resolve_binary("pytest"):
                proc = run_subprocess(
                    ["pytest", "-q", "--tb=short"],
                    cwd=self.sandbox_dir,
                    env=project_env,
                )
                passed = proc.returncode == 0
                cmd_record = {
                    "command": ("pytest", "-q", "--tb=short"),
                    "exit_code": proc.returncode,
                    "passed": passed,
                }
                executed_commands.append(cmd_record)
                if passed:
                    passed_count += 1
                else:
                    failed_details.append(
                        f"Pytest regression failure: {proc.stderr or proc.stdout}"
                    )

            # Node / Vitest / Jest
            if (self.sandbox_dir / "package.json").exists() and resolve_binary("npm"):
                proc = run_subprocess(
                    ["npm", "test", "--", "--run"],
                    cwd=self.sandbox_dir,
                )
                passed = proc.returncode == 0
                cmd_record = {
                    "command": ("npm", "test", "--", "--run"),
                    "exit_code": proc.returncode,
                    "passed": passed,
                }
                executed_commands.append(cmd_record)
                if passed:
                    passed_count += 1
                else:
                    failed_details.append(
                        f"npm test regression failure: {proc.stderr or proc.stdout}"
                    )

            # Rust Cargo
            if (self.sandbox_dir / "Cargo.toml").exists() and resolve_binary("cargo"):
                proc = run_subprocess(
                    ["cargo", "test", "--quiet"],
                    cwd=self.sandbox_dir,
                )
                passed = proc.returncode == 0
                cmd_record = {
                    "command": ("cargo", "test", "--quiet"),
                    "exit_code": proc.returncode,
                    "passed": passed,
                }
                executed_commands.append(cmd_record)
                if passed:
                    passed_count += 1
                else:
                    failed_details.append(
                        f"Cargo test regression failure: {proc.stderr or proc.stdout}"
                    )

        # 4. Zero executed commands never verify fail-closed
        if len(executed_commands) == 0:
            summary = (
                "No verification commands were executed. A patch requires at least one "
                "executed verification command to verify."
            )
            self.last_result = PatchVerificationResult(
                outcome="unavailable",
                executed_commands=(),
                passed_count=0,
                summary=summary,
                rollback_applied=False,
            )
            return VerificationOutcomeTuple(
                False, summary, outcome="unavailable", result=self.last_result
            )

        # 5. One or more commands failed
        if failed_details:
            summary = "; ".join(failed_details)
            self.last_result = PatchVerificationResult(
                outcome="failed",
                executed_commands=tuple(executed_commands),
                passed_count=passed_count,
                summary=summary,
                rollback_applied=False,
            )
            return VerificationOutcomeTuple(
                False, summary, outcome="failed", result=self.last_result
            )

        # 6. All commands passed (>= 1 command)
        summary = (
            f"All {len(executed_commands)} automated test and verification commands "
            "passed cleanly in sandbox."
        )
        self.last_result = PatchVerificationResult(
            outcome="completed",
            executed_commands=tuple(executed_commands),
            passed_count=passed_count,
            summary=summary,
            rollback_applied=False,
        )
        return VerificationOutcomeTuple(
            True, summary, outcome="completed", result=self.last_result
        )

    def verify(self, contract: PatchContract | None = None) -> PatchVerificationResult:
        """Directly returns truthful PatchVerificationResult."""
        self.verify_patch(contract=contract)
        assert self.last_result is not None
        return self.last_result
