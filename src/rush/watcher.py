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

DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".rush",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        "build",
        ".turbo",
        ".next",
    }
)


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
