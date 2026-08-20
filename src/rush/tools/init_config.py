"""Smart rush.toml configuration generator.

Architecture §8, Phase 23.
"""

from __future__ import annotations

from pathlib import Path

from rush.discovery.stack import detect_project_stacks
from rush.logging import get_logger, log_subsystem

logger = get_logger("tools.init_config")


def generate_initial_config(root: Path) -> str:
    """Generate a starter rush.toml configuration tailored to the repository's detected stacks."""
    stacks = detect_project_stacks(root)
    languages = {s.language for s in stacks}

    src_dirs = []
    test_dirs = []

    if "python" in languages:
        src_dirs.extend(["src"] if (root / "src").is_dir() else [])
        test_dirs.extend(["tests"] if (root / "tests").is_dir() else [])
    if "typescript" in languages or "javascript" in languages:
        src_dirs.extend(["src", "lib", "app"])
        test_dirs.extend(["test", "tests", "__tests__"])

    # Filter to existing directories or use defaults
    existing_src = [d for d in dict.fromkeys(src_dirs) if (root / d).is_dir()] or [
        "src"
    ]
    existing_test = [d for d in dict.fromkeys(test_dirs) if (root / d).is_dir()] or [
        "tests"
    ]

    log_subsystem(
        "init",
        "INFO",
        f"Generating initial configuration for stacks: {list(languages)}",
    )

    config_template = f"""# Rush configuration generated for detected stacks: {", ".join(sorted(languages)) or "generic"}

[project]
src = {existing_src!r}
test = {existing_test!r}
exclude = ["**/.venv/**", "**/node_modules/**", "**/.git/**"]

[cache]
enabled = true
dir = ".rush"
max_size_mb = 100

[review]
max_file_lines = 400
fail_on = ["error"]
use_graft = false
"""
    return config_template
