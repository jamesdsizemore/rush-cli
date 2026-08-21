"""Rule drift and SHA verification gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from rush.governance.synchronizer import IDE_TARGETS


@dataclass(frozen=True)
class ParityViolation:
    target_path: str
    reason: str


class RuleParityChecker:
    """Verifies that all IDE rule files are synchronized with AGENTS.md."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.canonical_file = self.repo_root / "AGENTS.md"

    def check_parity(self) -> list[ParityViolation]:
        if not self.canonical_file.exists():
            return [ParityViolation("AGENTS.md", "Canonical AGENTS.md does not exist.")]

        canonical_text = self.canonical_file.read_text(encoding="utf-8")
        canonical_sha = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        violations = []
        for rel_target in IDE_TARGETS:
            p = self.repo_root / rel_target
            if not p.exists():
                violations.append(ParityViolation(rel_target, "Rule file missing."))
            else:
                content = p.read_text(encoding="utf-8")
                if canonical_sha[:12] not in content:
                    violations.append(ParityViolation(rel_target, "Rule file out of sync with AGENTS.md SHA."))

        return violations
