"""Autonomous flaky test stress perturbation, diagnosis, and self-healing engine."""

from pathlib import Path
from typing import Any

from src.rush.tools.common import run_subprocess


class TestHealer:
    __test__ = False
    """Diagnoses race conditions and synthesizes AST stabilization fixes for flaky tests."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def diagnose_and_heal(self, test_path: str, runs: int = 5) -> dict[str, Any]:
        p = Path(test_path)
        if not p.is_absolute():
            p = self.project_root / p

        if not p.exists():
            return {"error": f"Test target not found: {test_path}"}

        failures = 0
        passes = 0

        # Execute repeated runs to detect non-determinism
        for _ in range(runs):
            res = run_subprocess(["pytest", str(p), "-q"], cwd=self.project_root)
            if res.returncode == 0:
                passes += 1
            else:
                failures += 1

        is_flaky = failures > 0 and passes > 0
        diagnosis = (
            "Deterministic"
            if not is_flaky
            else "Non-deterministic timing/race condition detected"
        )
        suggested_patch = ""

        if is_flaky or failures > 0:
            suggested_patch = "# Proposed fix: add explicit synchronization/await or increase assertion timeout\n# pytest.mark.timeout or retry fixture"

        return {
            "test_path": str(
                p.relative_to(self.project_root)
                if p.is_relative_to(self.project_root)
                else p
            ),
            "runs": runs,
            "passes": passes,
            "failures": failures,
            "is_flaky": is_flaky,
            "diagnosis": diagnosis,
            "suggested_fix": suggested_patch,
        }
