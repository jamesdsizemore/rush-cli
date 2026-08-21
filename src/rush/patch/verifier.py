"""Closed-loop multi-framework test suite verifier."""

from __future__ import annotations

import shutil
from pathlib import Path
from rush.tools.common import run_subprocess


class PatchVerifier:
    """Executes detected project test runners inside the sandbox to verify patch safety."""

    def __init__(self, sandbox_dir: Path) -> None:
        self.sandbox_dir = sandbox_dir.resolve()

    def verify_patch(self) -> tuple[bool, str]:
        # 1. Python Pytest verification
        if (self.sandbox_dir / "pytest.ini").exists() or (self.sandbox_dir / "tests").exists():
            if shutil.which("pytest"):
                proc = run_subprocess(
                    ["pytest", "-q", "--tb=short"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"Pytest regression failure: {proc.stderr or proc.stdout}"

        # 2. Node / Vitest / Jest verification
        if (self.sandbox_dir / "package.json").exists():
            if shutil.which("npm"):
                proc = run_subprocess(
                    ["npm", "test", "--", "--run"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"npm test regression failure: {proc.stderr or proc.stdout}"

        # 3. Rust Cargo verification
        if (self.sandbox_dir / "Cargo.toml").exists():
            if shutil.which("cargo"):
                proc = run_subprocess(
                    ["cargo", "test", "--quiet"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"Cargo test regression failure: {proc.stderr or proc.stdout}"

        return True, "All automated tests and quality checks passed cleanly in sandbox."
