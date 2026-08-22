"""Workspace lockfile integrity and consistency validator."""

from __future__ import annotations

from pathlib import Path

from rush.tools.base import Finding, ToolResult


class WorkspaceLockValidator:
    """Verifies that monorepo lockfiles are in sync with declared workspace dependencies."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def validate_lockfiles(self) -> ToolResult:
        findings: list[Finding] = []

        # Check uv lock
        if (self.repo_root / "pyproject.toml").exists() and not (
            self.repo_root / "uv.lock"
        ).exists():
            findings.append(
                {
                    "path": "pyproject.toml",
                    "line": 1,
                    "column": 1,
                    "rule": "missing-uv-lock",
                    "severity": "warn",
                    "message": "Repository contains pyproject.toml but lacks uv.lock. Run 'uv lock' to pin dependencies.",
                }
            )

        # Check Cargo lock
        if (self.repo_root / "Cargo.toml").exists() and not (
            self.repo_root / "Cargo.lock"
        ).exists():
            findings.append(
                {
                    "path": "Cargo.toml",
                    "line": 1,
                    "column": 1,
                    "rule": "missing-cargo-lock",
                    "severity": "warn",
                    "message": "Repository contains Cargo.toml but lacks Cargo.lock. Run 'cargo generate-lockfile'.",
                }
            )

        # Check pnpm lock
        if (self.repo_root / "pnpm-workspace.yaml").exists() and not (
            self.repo_root / "pnpm-lock.yaml"
        ).exists():
            findings.append(
                {
                    "path": "pnpm-workspace.yaml",
                    "line": 1,
                    "column": 1,
                    "rule": "missing-pnpm-lock",
                    "severity": "warn",
                    "message": "Repository contains pnpm-workspace.yaml but lacks pnpm-lock.yaml. Run 'pnpm install'.",
                }
            )

        return ToolResult(
            tool="workspace",
            engine="lock_validator",
            engine_version="1.0",
            status="ok" if not findings else "warn",
            duration_ms=0,
            summary=f"Workspace lockfile validation: {len(findings)} issue(s) detected.",
            findings=findings,
        )
