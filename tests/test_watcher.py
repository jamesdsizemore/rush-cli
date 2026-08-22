"""Tests for Phase 25: Real-Time File System Watcher.

Verifies:
- File change detection based on mtime and content size
- Debounce window and ignoring ignored paths (.git, node_modules, .rush)
- Triggering callback upon file modifications
"""

from __future__ import annotations

import time
from pathlib import Path

from rush.watcher import FileWatcher


def test_file_watcher_scan_and_detect(tmp_path: Path) -> None:
    test_file = tmp_path / "app.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    watcher = FileWatcher(root=tmp_path, debounce_ms=50)
    initial_snapshot = watcher.take_snapshot()
    assert str(test_file) in initial_snapshot

    # Modify file
    time.sleep(0.02)
    test_file.write_text("print('hello world updated')", encoding="utf-8")

    changes = watcher.detect_changes(initial_snapshot)
    assert len(changes) == 1
    assert changes[0] == test_file


def test_file_watcher_ignores_excluded_directories(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "index").write_text("git internal", encoding="utf-8")

    node_dir = tmp_path / "node_modules"
    node_dir.mkdir()
    (node_dir / "package.json").write_text("{}", encoding="utf-8")

    watcher = FileWatcher(root=tmp_path)
    snapshot = watcher.take_snapshot()

    # Neither .git nor node_modules files should be in snapshot
    paths_str = list(snapshot.keys())
    assert not any(".git" in p for p in paths_str)
    assert not any("node_modules" in p for p in paths_str)


def test_file_watcher_callback(tmp_path: Path) -> None:
    events = []
    test_file = tmp_path / "module.py"
    test_file.write_text("x = 1\n", encoding="utf-8")

    def on_change(paths: list[Path]) -> None:
        events.extend(paths)

    watcher = FileWatcher(root=tmp_path, debounce_ms=10, on_change=on_change)

    time.sleep(0.02)
    test_file.write_text("x = 2\n", encoding="utf-8")

    # Run single cycle of watcher step
    watcher.step()
    assert len(events) == 1
    assert events[0] == test_file


def test_path_filter_and_router() -> None:
    from rush.watcher import PathFilter, ToolRouter

    filter_engine = PathFilter()
    assert filter_engine.is_ignored(Path(".git/config")) is True
    assert filter_engine.is_ignored(Path("src/app.py")) is False

    tools = ToolRouter.get_tools_for_paths([Path("src/app.py")])
    assert "ruff" in tools
    assert "mypy" in tools
