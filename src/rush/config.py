"""rush.toml discovery + parsing.

Architecture §8.

Discovery rule:
    start = path (file or directory passed to tool)
    loop:
        candidate = start / "rush.toml"
        if candidate.exists(): return parse(candidate)
        if start has ".git" (file or directory): stop  → no config
        if start.parent == start: stop  → filesystem root, no config
        start = start.parent

Override order (last wins):
    1. Hardcoded defaults (in the dataclasses below)
    2. rush.toml values
    3. CLI flags
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# tomllib is stdlib; nothing to import


class RushConfigError(Exception):
    """Raised when rush.toml is malformed."""


@dataclass
class ProjectConfig:
    src: list[str] = field(default_factory=lambda: ["src"])
    test: list[str] = field(default_factory=lambda: ["tests"])
    exclude: list[str] = field(
        default_factory=lambda: ["**/.venv/**", "**/node_modules/**"]
    )


@dataclass
class ToolConfig:
    engine_args: list[str] = field(default_factory=list)
    check: bool = False


@dataclass
class ReviewConfig:
    max_file_lines: int = 400
    fail_on: list[str] = field(default_factory=list)


@dataclass
class RushConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    tools: dict[str, ToolConfig] = field(default_factory=dict)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    log_level: str = "warn"
    # Path of the rush.toml we loaded from, or None if defaults-only.
    source: Path | None = None


def _has_git_marker(p: Path) -> bool:
    """True if `p` is the git root (contains .git) or a child of one we crossed."""
    cur = p
    while True:
        if (cur / ".git").exists():
            return True
        if cur.parent == cur:
            return False
        cur = cur.parent


def discover_config(start: Path) -> Path | None:
    """Walk up from `start` looking for rush.toml. Stop at git root or filesystem root.

    Returns the path to rush.toml, or None if not found.
    """
    cur = start if start.is_dir() else start.parent
    while True:
        candidate = cur / "rush.toml"
        if candidate.is_file():
            return candidate
        # Stop at git root (config shouldn't escape the repo)
        if (cur / ".git").exists():
            return None
        if cur.parent == cur:
            return None
        cur = cur.parent


def load_config(start: Path | None = None) -> RushConfig:
    """Load rush.toml from `start` (or cwd if None), applying defaults.

    Never raises on missing config — returns defaults. Raises RushConfigError
    only when rush.toml exists but is malformed.
    """
    if start is None:
        start = Path.cwd()
    cfg_path = discover_config(start)
    if cfg_path is None:
        return RushConfig()
    try:
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise RushConfigError(f"malformed rush.toml at {cfg_path}: {e}") from e

    return _parse(raw, cfg_path)


def _parse(raw: dict, source: Path) -> RushConfig:
    project_raw = raw.get("project", {}) or {}
    project = ProjectConfig(
        src=list(project_raw.get("src", ["src"])),
        test=list(project_raw.get("test", ["tests"])),
        exclude=list(project_raw.get("exclude", ["**/.venv/**", "**/node_modules/**"])),
    )

    tools: dict[str, ToolConfig] = {}
    for tool_name, tr in (raw.get("tools", {}) or {}).items():
        tr = tr or {}
        tools[tool_name] = ToolConfig(
            engine_args=list(tr.get("engine_args", [])),
            check=bool(tr.get("check", False)),
        )

    review_raw = raw.get("review", {}) or {}
    review = ReviewConfig(
        max_file_lines=int(review_raw.get("max_file_lines", 400)),
        fail_on=list(review_raw.get("fail_on", [])),
    )

    return RushConfig(
        project=project,
        tools=tools,
        review=review,
        log_level=str(raw.get("log_level", "warn")),
        source=source,
    )
