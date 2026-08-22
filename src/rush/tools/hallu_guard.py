"""Real-time phantom package and hallucinated import guard."""

from pathlib import Path
from typing import Any

from src.rush.codegraph.grounding_verifier import GroundingVerifier


class HalluGuard:
    """Audits files or git diffs for hallucinated dependencies."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.verifier = GroundingVerifier(self.project_root)

    def check_file(self, target_file: Path) -> list[str]:
        if not target_file.exists():
            return [f"File not found: {target_file}"]
        code = target_file.read_text(encoding="utf-8", errors="ignore")
        return self.verifier.verify_code(code)

    def audit_codebase(self) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        for py_file in self.project_root.glob("**/*.py"):
            if (
                ".venv" in str(py_file)
                or ".git" in str(py_file)
                or "tests" in str(py_file)
            ):
                continue
            violations = self.check_file(py_file)
            if violations:
                findings.append(
                    {
                        "file": str(py_file.relative_to(self.project_root)),
                        "violations": violations,
                    }
                )

        return {
            "passed": len(findings) == 0,
            "findings_count": len(findings),
            "findings": findings,
        }
