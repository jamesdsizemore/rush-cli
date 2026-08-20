"""Project stack discovery and ecosystem detection.

Architecture §8, Phase 23.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DetectedStack:
    language: str
    package_manager: str | None
    frameworks: list[str] = field(default_factory=list)
    suggested_engines: list[str] = field(default_factory=list)


def detect_project_stacks(root: Path) -> list[DetectedStack]:
    """Inspect repository markers to determine active polyglot technology stacks."""
    stacks: list[DetectedStack] = []
    resolved = root.resolve()

    # 1. Python Detection
    if (
        (resolved / "pyproject.toml").is_file()
        or (resolved / "requirements.txt").is_file()
        or (resolved / "setup.py").is_file()
        or (resolved / "Pipfile").is_file()
    ):
        pm = (
            "uv"
            if (resolved / "uv.lock").is_file()
            or (resolved / "pyproject.toml").is_file()
            else "pip"
        )
        stacks.append(
            DetectedStack(
                language="python",
                package_manager=pm,
                frameworks=["pytest"],
                suggested_engines=["ruff", "mypy", "pytest", "pip-audit", "bandit"],
            )
        )

    # 2. TypeScript / JavaScript Detection
    if (resolved / "package.json").is_file():
        is_ts = (resolved / "tsconfig.json").is_file()
        pm = (
            "pnpm"
            if (resolved / "pnpm-lock.yaml").is_file()
            else ("yarn" if (resolved / "yarn.lock").is_file() else "npm")
        )
        stacks.append(
            DetectedStack(
                language="typescript" if is_ts else "javascript",
                package_manager=pm,
                frameworks=["node"],
                suggested_engines=["biome", "eslint", "prettier", "tsc"]
                if is_ts
                else ["eslint", "prettier"],
            )
        )

    # 3. Rust Detection
    if (resolved / "Cargo.toml").is_file():
        stacks.append(
            DetectedStack(
                language="rust",
                package_manager="cargo",
                suggested_engines=["clippy", "cargo-audit", "rustfmt"],
            )
        )

    # 4. Go Detection
    if (resolved / "go.mod").is_file():
        stacks.append(
            DetectedStack(
                language="go",
                package_manager="go",
                suggested_engines=["golangci-lint", "govulncheck"],
            )
        )

    return stacks
