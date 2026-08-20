# Phase 25 Implementation Plan: Real-Time File System Watcher (`rush watch`)

> **Phase:** 25 of 30  
> **Milestone:** Continuous Real-Time Quality Feedback  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md)

---

## 1. Objective & Scope

Implement a background file system watcher (`rush watch`) providing sub-second debounced feedback during active coding sessions.

Incorporate **Resource Throttling & Path Filtering** to ignore VCS/virtualenv paths (`.git/`, `.rush/`, `node_modules/`, `.venv/`) and enforce a 300ms debounce interval preventing CPU starvation loops.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/watcher.py` (New: File system watcher using `watchfiles`)
- `src/rush/cli.py` (Modified: Add `rush watch` command)
- `pyproject.toml` (Modified: Add `watchfiles==1.0.4` dependency)
- `src/rush/logging.py` (Modified: `[rush-watch:LEVEL]` prefix tags)

### Test & Fixture Files
- `tests/test_watcher.py` (New: Debounce, ignore filtering, and trigger tests)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_watcher.py`:
1. `test_watcher_debounce_throttling()`: Asserts that 50 file changes within 100ms collapse into a single scan execution.
2. `test_watcher_ignored_paths()`: Asserts modifications to `.git/HEAD` or `.rush/cache.db` do not trigger checks.
3. `test_watcher_targeted_tool_trigger()`: Asserts modifying a `.py` file runs python linters while modifying a `.ts` file runs typescript linters.

### 3.2 GREEN Phase
Implement `src/rush/watcher.py` and connect to Click CLI.

### 3.3 REFACTOR Phase
Ensure clean terminal screen clearing between runs and graceful termination on `Ctrl+C` (SIGINT).

---

## 4. Step-by-Step Implementation Tasks

### Task 25.1: File System Watcher Engine (`src/rush/watcher.py`)
```python
from __future__ import annotations
import asyncio
from pathlib import Path
from watchfiles import awatch, PythonFilter

IGNORED_DIRS = {".git", ".rush", "node_modules", ".venv", "__pycache__", ".pytest_cache"}

def should_watch_path(path: Path) -> bool:
    parts = set(path.parts)
    return not bool(parts & IGNORED_DIRS)

async def watch_workspace(root: Path, suite_name: str = "check", debounce_ms: int = 300) -> None:
    # Debounced async file event loop
    ...
```

### Task 25.2: CLI Command Registration (`src/rush/cli.py`)
Add `rush watch` command:
```python
@main.command(name="watch")
@click.option("--suite", default="check", help="Composite suite to run on change (check, audit, gate).")
@click.option("--tools", help="Comma-separated tools to run on change.")
@click.option("--clear/--no-clear", default=True, help="Clear terminal screen between runs.")
def watch_command(suite: str, tools: str | None, clear: bool) -> None:
    ...
```

### Task 25.3: Stderr Diagnostics & Logging
- `[rush-watch:INFO] Watching workspace {root} (debounce: 300ms)`
- `[rush-watch:INFO] Triggering suite '{suite}' for modified paths: {paths}`
- `[rush-watch:WARN] Watch loop interrupted by user signal`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Document `rush watch`).
2. `docs/USER_GUIDE.md` & `docs/user-guide/everyday-workflow.md` (Add watch mode workflow guide).
3. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run watcher unit tests
.venv/Scripts/python.exe -m pytest tests/test_watcher.py -v

# 2. Full test suite verification
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Documentation parity verification
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Lint and format
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Graft code graph check
graft --dir .hermes/graft build . && graft --dir .hermes/graft check .
```
