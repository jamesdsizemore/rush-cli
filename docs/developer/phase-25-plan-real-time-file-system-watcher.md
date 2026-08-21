# Phase 25 Implementation Plan: Real-Time File System Watcher (`rush watch`)

> **Phase:** 25 of 40  
> **Milestone:** Continuous Real-Time Quality Feedback & Debounced Execution  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `watchfiles==1.0.4`, `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Vibe-coders and active developers need instantaneous sub-second feedback when editing files without manually re-triggering CLI scans. Phase 25 implements a high-performance background file system watcher (`rush watch`) that monitors the repository for file modifications and triggers debounced quality suites (`rush check`, `rush audit`, or individual tools).

To prevent CPU starvation and infinite feedback loops, the watcher ignores VCS and cache directories (`.git/`, `.rush/`, `node_modules/`, `.venv/`, `__pycache__/`) and enforces a 300ms debounce interval with targeted language-specific tool triggers.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Live Terminal Screen Slicing)**: Clears and redraws only the active status header and failing findings, preventing terminal scrollback explosion.
- **`graft` (Targeted Watch Triggers)**: Modifying a `.py` file executes only Python formatters/linters; modifying a `.ts` file triggers only TypeScript checkers, avoiding full repository rescans.
- **`context-mode` (Debounced Event Batching)**: Batches multiple file events occurring within 300ms into a single unified scan pass.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/watcher.py` (New: Async debounced file event listener using `watchfiles`)
- `src/rush/cli.py` (Modified: Register `rush watch` command with `--suite`, `--tools`, `--clear`)
- `src/rush/mcp_server.py` (Modified: Provide file event notification channels if MCP clients request live updates)
- `src/rush/catalog.py` (Modified: Register watcher capabilities)

### Test & Fixture Files
- `tests/test_watcher.py` (New: Debounce throttling, ignore filters, language routing, and clean SIGINT exit)
- `tests/fixtures/watcher/` (New: Mock filesystem watch directory)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_watcher.py
def test_watcher_debounce_throttling():
    events = [("modified", Path("src/a.py")) for _ in range(50)]
    batched = debounce_file_events(events, debounce_ms=300)
    assert len(batched) == 1

def test_watcher_ignores_special_directories():
    assert should_watch_path(Path(".git/HEAD")) is False
    assert should_watch_path(Path(".rush/cache.db")) is False
    assert should_watch_path(Path("node_modules/pkg/index.js")) is False
    assert should_watch_path(Path(".venv/lib/site-packages/x.py")) is False
    assert should_watch_path(Path("src/main.py")) is True

def test_watcher_routes_language_targets():
    py_target = Path("src/core.py")
    tools = route_tools_for_modified_files([py_target])
    assert "format" in tools or "lint" in tools
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/watcher.py` and connect Click CLI command.

### 4.3 REFACTOR Phase
Ensure asynchronous signal handlers (`SIGINT`, `SIGTERM`) cleanly close the event loop without leaving zombie worker subprocesses.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:35:00Z", "phase": 25, "tool": "rush_watch", "event": "watcher_started", "root": ".", "debounce_ms": 300, "suite": "check"}
{"timestamp": "2026-08-21T07:35:01Z", "phase": 25, "tool": "rush_watch", "event": "change_detected", "modified_files": ["src/api.py"], "triggered_suite": "check"}
{"timestamp": "2026-08-21T07:35:02Z", "phase": 25, "tool": "rush_watch", "event": "scan_finished", "duration_ms": 142, "status": "passed"}
```

---

## 6. Step-by-Step Task Specifications

### Task 25.1: File System Watcher Engine (`src/rush/watcher.py`)
```python
from __future__ import annotations
import asyncio
from pathlib import Path
from watchfiles import awatch

IGNORED_DIRS = {".git", ".rush", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}

def should_watch_path(path: Path) -> bool:
    """Filter out VCS, virtualenv, and build artifacts from watch loops."""
    parts = set(path.parts)
    return not bool(parts & IGNORED_DIRS)

async def watch_workspace(root: Path, suite_name: str = "check", debounce_ms: int = 300) -> None:
    """Debounced async file system event loop running workflow suites on change."""
    ...
```

### Task 25.2: CLI Command Registration (`src/rush/cli.py`)
```python
@main.command(name="watch")
@click.option("--suite", default="check", help="Composite suite to run on change (check, audit, gate).")
@click.option("--tools", help="Comma-separated tools to run on change.")
@click.option("--clear/--no-clear", default=True, help="Clear terminal screen between runs.")
def watch_command(suite: str, tools: str | None, clear: bool) -> None:
    ...
```

### Task 25.3: CLI & FastMCP Registrations
Register `rush watch` in CLI.

---

## 7. Semantic Drift Review & Verification Gate

1. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
2. **Clean Exit**: Pressing `Ctrl+C` must exit with return code 0 immediately.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
