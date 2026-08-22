"""Real-time File System Watcher & Inner-Loop Workflow Trigger.

Architecture §8, Phase 25.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from rush.logging import get_logger, log_subsystem

logger = get_logger("watcher")

import fnmatch

DEFAULT_IGNORES = [
    "*/.git/*",
    "*/.git",
    "*/.venv/*",
    "*/.venv",
    "*/node_modules/*",
    "*/node_modules",
    "*/.rush/*",
    "*/.rush",
    "*/__pycache__/*",
    "*/__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.tmp",
    "*.swp",
    "*.swo",
    "*~",
    "*/build/*",
    "*/dist/*",
    "*/target/*",
    "*.egg-info/*",
    "*.egg-info",
]

DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        ".rush",
        "__pycache__",
        "build",
        "dist",
        "target",
        ".codegraph",
    }
)

EXTENSION_TOOL_MAP: dict[str, list[str]] = {
    ".py": ["ruff", "mypy", "pytest", "aislop", "tach", "bandit"],
    ".pyi": ["ruff", "mypy"],
    ".ts": ["biome", "eslint", "prettier", "tsc"],
    ".tsx": ["biome", "eslint", "prettier", "tsc"],
    ".js": ["biome", "eslint", "prettier"],
    ".jsx": ["biome", "eslint", "prettier"],
    ".rs": ["clippy", "rustfmt"],
    ".go": ["golangci-lint", "govulncheck", "gofmt"],
    ".toml": ["ruff"],
    ".json": ["biome", "prettier"],
    ".md": ["markdownlint", "rumdl"],
    ".css": ["prettier", "biome"],
}


class PathFilter:
    """Evaluates paths against default and custom ignore patterns."""

    def __init__(
        self,
        repo_root: Path | None = None,
        custom_ignores: list[str] | None = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.patterns = list(DEFAULT_IGNORES) + (custom_ignores or [])

    def is_ignored(self, path: Path) -> bool:
        for part in path.parts:
            if part in DEFAULT_IGNORE_DIRS:
                return True
        path_str = path.as_posix()
        for pattern in self.patterns:
            if (
                fnmatch.fnmatch(path_str, pattern)
                or fnmatch.fnmatch(f"/{path_str}", pattern)
                or fnmatch.fnmatch(f"/{path_str}/", pattern)
                or fnmatch.fnmatch(path.name, pattern)
            ):
                return True
        return False


class ToolRouter:
    """Maps modified filesystem paths to the exact subset of required quality tools."""

    @staticmethod
    def get_tools_for_paths(paths: list[Path]) -> list[str]:
        tools: set[str] = set()
        for p in paths:
            ext = p.suffix.lower()
            if ext in EXTENSION_TOOL_MAP:
                tools.update(EXTENSION_TOOL_MAP[ext])
        return sorted(tools)


class FileWatcher:
    """Monitors repository directories for modifications with debouncing."""

    def __init__(
        self,
        root: Path,
        debounce_ms: int = 300,
        on_change: Callable[[list[Path]], None] | None = None,
        ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
    ) -> None:
        self.root = root.resolve()
        self.debounce_sec = debounce_ms / 1000.0
        self.on_change = on_change
        self.ignore_dirs = ignore_dirs
        self.current_snapshot: dict[str, tuple[float, int]] = self.take_snapshot()

    def take_snapshot(self) -> dict[str, tuple[float, int]]:
        """Walk root and capture mapping of file_path -> (mtime_ns, size_bytes)."""
        snapshot: dict[str, tuple[float, int]] = {}
        for root_dir, dirs, files in os.walk(self.root):
            # Prune ignored directories in-place
            dirs[:] = [
                d for d in dirs if d not in self.ignore_dirs and not d.startswith(".")
            ]

            for file in files:
                if file.startswith("."):
                    continue
                full_path = Path(root_dir) / file
                try:
                    stat = full_path.stat()
                    snapshot[str(full_path)] = (stat.st_mtime, stat.st_size)
                except OSError:
                    continue
        return snapshot

    def detect_changes(self, baseline: dict[str, tuple[float, int]]) -> list[Path]:
        """Compare current filesystem state against baseline snapshot."""
        current = self.take_snapshot()
        changed: list[Path] = []

        for p_str, meta in current.items():
            if p_str not in baseline or baseline[p_str] != meta:
                changed.append(Path(p_str))

        return changed

    def step(self) -> list[Path]:
        """Perform one detection step and trigger callback if changes are found."""
        changes = self.detect_changes(self.current_snapshot)
        if changes:
            log_subsystem("watch", "INFO", f"Detected {len(changes)} modified file(s)")
            self.current_snapshot = self.take_snapshot()
            if self.on_change:
                self.on_change(changes)
        return changes

    def watch_blocking(self, max_iterations: int | None = None) -> None:
        """Run blocking watch loop with debounce intervals."""
        log_subsystem(
            "watch",
            "INFO",
            f"Watching {self.root} for changes (debounce={int(self.debounce_sec * 1000)}ms)...",
        )
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                time.sleep(self.debounce_sec)
                self.step()
                iterations += 1
        except KeyboardInterrupt:
            log_subsystem("watch", "INFO", "Watcher stopped by user.")
