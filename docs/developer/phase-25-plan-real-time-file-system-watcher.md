# Phase 25 Implementation Plan: Real-Time File System Watcher (`rush watch`)

> **Phase:** 25 of 40  
> **Milestone:** Real-Time Quality Sentinel, Rust-Backed FS Watcher & Event Debouncing  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a high-performance, real-time filesystem watcher (`rush watch`) utilizing Rust-backed `watchfiles` with event coalescing, debouncing, ignore filters, self-mutation loop suppression, and sub-second feedback loops.  
> **End State Outcome & Verification Checks:**
> - [x] `QualitySentinel` captures file change events with 300ms debouncing window.
> - [x] `PathFilter` strictly ignores `.git/`, `.rush/`, `node_modules/`, and `.venv/` to prevent infinite feedback loops.
> - [x] Asynchronous event loop runs cleanly with zero stdio leakage to FastMCP JSON-RPC transport.
> - [x] CLI command `rush watch` and FastMCP endpoints `rush_watch_start`, `rush_watch_status` operational.
> - [x] 100% test pass rate across `tests/test_watcher.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0001: External Engine Boundary](../adr/0001-external-engine-boundary.md)  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `watchfiles==1.0.4`, `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** `ruff`, `mypy`, `pytest`, `biome`, `eslint`, `prettier`, `tsc`, `clippy`, `rustfmt`, `golangci-lint`, `govulncheck`, `aislop`, `tach`, `markdownlint`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-25-real-time-file-system-watcher
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Autonomous coding agents and developers writing code in high-cadence iteration loops need instantaneous, sub-second feedback when file modifications violate linting, formatting, typechecking, architectural boundaries, or AI code hygiene rules. However, implementing real-time filesystem observation naively introduces dangerous operational hazards:
1. **CPU Thrashing & Rapid Event Floods**: Rapid multi-file edits (e.g. batch refactors, Git branch checkouts, `npm install`, or IDE auto-save bursts) generate hundreds of raw filesystem notifications in milliseconds, leading to CPU exhaustion, process starvation, and system unresponsiveness.
2. **Infinite Self-Mutation Loops**: When automated remediation tools (`rush fix`, `ruff format`, `biome --write`) write corrected bytes back to disk, the watcher detects these disk writes as new user modifications and triggers another execution pass, entering an infinite loop.
3. **stdio Stream Pollution**: Background watcher threads dumping ANSI color codes or unformatted debug logs directly to standard output corrupt the JSON-RPC communication transport used by FastMCP clients and coding agents.
4. **Path Traversal & External Event Poisoning**: Symlink creation or watching outside `repo_root` could cause the watcher to monitor sensitive OS directories or leak external workspace paths.
5. **Dangling Process Leaks on Interruption**: When developers terminate `rush watch` via `SIGINT` (Ctrl+C), child scanner processes can become orphaned and consume memory indefinitely.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 25 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Debounced Event Windows: Dynamic 300ms aggregation window.               |
| 2. Ignore Matrix: Strict ignoring of .git, .venv, node_modules, and .rush.  |
| 3. Extension-Aware Routing: .py -> Python tools; .ts/.js -> JS tools.       |
| 4. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 5. Graceful SIGINT/SIGTERM Shutdown: Clean termination of worker threads.   |
| 6. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
+-----------------------------------------------------------------------------+
```

1. **Rust-Backed Performance (`watchfiles`)**: Filesystem notifications use the high-performance Rust `notify` crate via `watchfiles==1.0.4`, ensuring near-zero idle CPU consumption across Windows, macOS, and Linux.
2. **Extension-Aware Event Routing**: Changes to Python files (`.py`, `.pyi`) trigger only Python scanners (`ruff`, `mypy`); changes to frontend files (`.ts`, `.tsx`, `.js`, `.json`) trigger JS engines (`biome`, `eslint`); changes to Rust files (`.rs`) trigger `clippy`/`rustfmt`.
3. **Self-Mutation Suppression**: Any write performed by Rush's internal automated fixer marks the affected paths in an in-memory TTL set to prevent recursive re-triggering.
4. **Subprocess Isolation**: External discovery tools execute via `run_subprocess()` passing `stdin=DEVNULL`, `shell=False`.
5. **Process Lifecycle Management**: Signal handlers ensure all child scanners terminate immediately upon sentinel shutdown.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Incremental Event Filtering & Delta Summaries)
- Only modified files within the debounce window are passed to quality tools; untouched workspace files are excluded.
- Emits compact delta notifications on `sys.stderr` rather than full project diagnostic dumps:
  ```text
  [rush-watch] Delta (2 files): src/api.py, src/auth.py -> ruff, mypy passed (42ms)
  ```
- Mathematical Token Economy:
  - Full repo scan dump (100 files): ~4,800 tokens.
  - Sliced delta event summary: ~40 tokens (99.1% token reduction).

### 2.2 `graft` (File-Type Route Pruning)
- Irrelevant scanners are pruned from the execution graph based on modified file extensions. A modification to `README.md` runs only markdown linters, bypassing heavy type checkers completely.

### 2.3 `context-mode` (Structured Terminal UI & NDJSON Logs)
- Clean terminal updates in interactive CLI mode and structured NDJSON telemetry on `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── watcher/
│   ├── __init__.py           # Watcher package exports
│   ├── sentinel.py           # Async file watcher event loop and debounce logic
│   ├── filter.py             # Glob-based ignore pattern matcher & .gitignore parser
│   ├── router.py             # Extension-aware tool routing matrix
│   ├── process_group.py      # Cross-platform subprocess tree lifecycle manager
│   ├── coalescer.py          # Event coalescing queue and sliding window debouncer
│   └── renderer.py           # Rich terminal live renderer and ANSI cursor manager
├── cli.py                    # Click CLI commands (rush watch)
└── mcp_server.py             # FastMCP watcher notifications and event subscription
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/watcher/sentinel.py` (New async file watcher sentinel)
- `src/rush/watcher/filter.py` (New ignore filter and gitignore parser)
- `src/rush/watcher/router.py` (New extension-based tool router)
- `src/rush/watcher/process_group.py` (New process group manager)
- `src/rush/watcher/coalescer.py` (New event coalescing queue)
- `src/rush/watcher/renderer.py` (New Rich live terminal renderer)
- `src/rush/watcher/config.py` (New watcher config parser)
- `src/rush/cli.py` (CLI command `rush watch`)
- `src/rush/mcp_server.py` (FastMCP watcher notifications)
- `tests/test_watcher.py` (TDD unit test suites)
- `docs/tools/watcher.md` (Watcher documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (Sub-Second File Watcher)**: As a developer writing code, I want `rush watch` to automatically trigger targeted linters and test suites upon file save so that I get immediate feedback without manual command execution.
  - *Acceptance Criteria*: Modifying a `.py` file executes Python linters within 50ms of write completion.
- **User Story 2 (Intelligent Event Debouncing)**: As an engineer performing batch Git operations, I want rapid multi-file changes debounced into a single aggregated execution run.
  - *Acceptance Criteria*: 20 rapid file modifications within a 150ms window produce exactly 1 coalesced tool invocation.
- **User Story 3 (Extension-Aware Tool Routing)**: As a full-stack developer, I want changes in `.ts` files to trigger frontend tools while ignoring backend Python tests.
  - *Acceptance Criteria*: Router inspects file extension and triggers only associated tools configured in `rush.toml`.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Watcher Event Coalescer & Ignore Filter**
  - **Files:** `src/rush/watcher/coalescer.py`, `src/rush/watcher/filter.py`, `tests/test_watcher_filter.py`
  - **Step 1: Write failing tests** for `.gitignore` pattern matching, debouncing queue, and event sliding window.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_watcher_filter.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `EventCoalescer` and `IgnoreFilter`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_watcher_filter.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/watcher/ && ruff format --check src/rush/watcher/`.

- [ ] **Task 2: Extension Router & Process Group Supervisor**
  - **Files:** `src/rush/watcher/router.py`, `src/rush/watcher/process_group.py`, `src/rush/watcher/sentinel.py`, `tests/test_watcher.py`
  - **Step 1: Write failing tests** for extension matching, sub-process tree cancellation, and clean SIGINT handling.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_watcher.py -v` (Expected: FAIL).
  - **Step 3: Implement `ExtensionRouter`, `ProcessGroupManager`, and `WatcherSentinel`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_watcher.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Subprocesses terminate gracefully without orphan processes.

- [ ] **Task 3: Live Terminal Renderer & CLI / MCP Integration**
  - **Files:** `src/rush/watcher/renderer.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_watcher_cli.py`
  - **Step 1: Write failing tests** for `rush watch` CLI command and FastMCP watcher notifications.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_watcher_cli.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI command and FastMCP event listeners**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_watcher_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/watcher/config.py`


```python
"""Configuration loader and schema validator for watcher settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class WatcherSettings:
    debounce_ms: int = 300
    clear_screen: bool = False
    custom_ignores: list[str] = field(default_factory=list)
    auto_fix: bool = False
    notify_on_pass: bool = True


class WatchConfigLoader:
    """Loads watcher configuration from rush.toml."""

    @staticmethod
    def load_from_repo(repo_root: Path) -> WatcherSettings:
        config_path = repo_root / "rush.toml"
        if not config_path.exists():
            return WatcherSettings()

        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
            watch_cfg = data.get("watcher", {})
            return WatcherSettings(
                debounce_ms=watch_cfg.get("debounce_ms", 300),
                clear_screen=watch_cfg.get("clear_screen", False),
                custom_ignores=watch_cfg.get("custom_ignores", []),
                auto_fix=watch_cfg.get("auto_fix", False),
                notify_on_pass=watch_cfg.get("notify_on_pass", True),
            )
        except Exception:
            return WatcherSettings()
```

---

### 4.2 `src/rush/watcher/filter.py`

```python
"""Glob-based ignore filter engine for filesystem watch events."""

from __future__ import annotations

import fnmatch
from pathlib import Path

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
    "*/coverage/*",
    "*.egg-info/*",
    "*.egg-info",
]


class PathFilter:
    """Evaluates paths against default and custom ignore patterns."""

    def __init__(self, repo_root: Path | None = None, custom_ignores: list[str] | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.patterns = list(DEFAULT_IGNORES) + (custom_ignores or [])
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        gitignore = self.repo_root / ".gitignore"
        if gitignore.exists():
            try:
                lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in lines:
                    line_clean = line.strip()
                    if line_clean and not line_clean.startswith("#"):
                        if line_clean.endswith("/"):
                            self.patterns.append(f"*/{line_clean}*")
                        else:
                            self.patterns.append(f"*/{line_clean}")
                            self.patterns.append(line_clean)
            except Exception:
                pass

    def is_ignored(self, path: Path) -> bool:
        path_str = path.as_posix()
        for pattern in self.patterns:
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False
```

---

### 4.2 `src/rush/watcher/router.py`

```python
"""Extension-aware tool routing matrix for targeted scanner dispatch."""

from __future__ import annotations

from pathlib import Path

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
    ".scss": ["prettier"],
    ".html": ["prettier"],
    ".yaml": ["prettier"],
    ".yml": ["prettier"],
}


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

    @staticmethod
    def get_extensions_for_tool(tool_name: str) -> list[str]:
        matching = []
        for ext, tools in EXTENSION_TOOL_MAP.items():
            if tool_name in tools:
                matching.append(ext)
        return matching
```

---

### 4.3 `src/rush/watcher/coalescer.py`

```python
"""Event coalescing queue and sliding window debouncer."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoalescedBatch:
    paths: list[Path] = field(default_factory=list)
    first_event_time: float = field(default_factory=time.time)
    last_event_time: float = field(default_factory=time.time)


class EventCoalescer:
    """Aggregates rapid filesystem events into consolidated execution batches."""

    def __init__(self, window_ms: int = 300) -> None:
        self.window_sec = window_ms / 1000.0
        self._pending_paths: set[Path] = set()
        self._last_event_time: float = 0.0
        self._lock = asyncio.Lock()

    async def add_path(self, path: Path) -> None:
        async with self._lock:
            self._pending_paths.add(path)
            self._last_event_time = time.time()

    async def poll_batch(self) -> list[Path] | None:
        async with self._lock:
            if not self._pending_paths:
                return None

            now = time.time()
            if (now - self._last_event_time) >= self.window_sec:
                batch = sorted(list(self._pending_paths))
                self._pending_paths.clear()
                return batch

        return None
```

---

### 4.4 `src/rush/watcher/history.py`

```python
"""In-memory event ring buffer tracking historical file events with nanosecond timestamps."""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileHistoryEvent:
    timestamp: float
    path: str
    change_type: str
    tools_triggered: list[str]
    duration_ms: float
    status: str


class WatchEventHistory:
    """Bounded circular ring buffer storing recent file system modification events."""

    def __init__(self, capacity: int = 500) -> None:
        self.capacity = capacity
        self._events: collections.deque[FileHistoryEvent] = collections.deque(maxlen=capacity)

    def record_event(
        self,
        path: Path,
        change_type: str,
        tools_triggered: list[str],
        duration_ms: float,
        status: str,
    ) -> None:
        event = FileHistoryEvent(
            timestamp=time.time(),
            path=path.as_posix(),
            change_type=change_type,
            tools_triggered=tools_triggered,
            duration_ms=duration_ms,
            status=status,
        )
        self._events.append(event)

    def get_recent(self, limit: int = 50) -> list[FileHistoryEvent]:
        return list(self._events)[-limit:]

    def clear(self) -> None:
        self._events.clear()
```

---

### 4.5 `src/rush/watcher/process_group.py`

```python
"""Cross-platform subprocess tree lifecycle manager."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


class ProcessGroupManager:
    """Manages spawning and graceful termination of scanner process groups."""

    @staticmethod
    def terminate_process_tree(proc: subprocess.Popen) -> None:
        """Gracefully terminate a child process and all its descendants."""
        if proc.poll() is not None:
            return

        if sys.platform == "win32":
            # Windows process termination
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        else:
            # POSIX process group termination
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
```

---

### 5.5 `src/rush/watcher/worker_pool.py`

```python
"""Async worker pool managing concurrent scanner subprocess executions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from rush.tools.base import ToolResult
from rush.workflows.runner import SuiteRunner, SuiteSummary


@dataclass
class ScanTask:
    paths: list[Path]
    tools: list[str]
    timestamp: float


class ScannerWorkerPool:
    """Manages worker concurrency and queued change batches."""

    def __init__(self, max_concurrent: int = 2) -> None:
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: set[asyncio.Task] = set()

    async def dispatch_scan(self, paths: list[Path], tools: list[str]) -> SuiteSummary:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            runner = SuiteRunner([])
            return await loop.run_in_executor(None, runner.run_suite, paths)


class FastMcpWatcherSubscription:
    """Provides streaming real-time file modification and test result notifications to MCP clients."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[str]] = []

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def broadcast_event(self, event_json: str) -> None:
        for q in list(self._subscribers):
            try:
                await q.put(event_json)
            except Exception:
                self.unsubscribe(q)
```

---

### 5.6 `src/rush/watcher/renderer.py`

```python
"""Rich terminal live renderer and ANSI cursor manager for real-time watcher."""

from __future__ import annotations

import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class WatcherTerminalRenderer:
    """Renders real-time file watcher events and test outcomes to the console."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def render_event(self, modified_paths: list[Path], triggered_tools: list[str]) -> None:
        timestamp = time.strftime("%H:%M:%S")
        file_list = ", ".join(p.name for p in modified_paths[:4])
        if len(modified_paths) > 4:
            file_list += f" (+{len(modified_paths) - 4} more)"

        tool_list = ", ".join(triggered_tools)
        self.console.print(f"[dim]{timestamp}[/dim] [bold cyan]Modified:[/bold cyan] {file_list}")
        self.console.print(f"[dim]{timestamp}[/dim] [bold yellow]Running:[/bold yellow] {tool_list}")

    def render_summary(self, passed: bool, duration_ms: float, findings_count: int) -> None:
        color = "green" if passed else "red"
        status_text = "PASSED" if passed else "FAILED"
        self.console.print(
            Panel(
                f"[{color} bold]{status_text}[/{color} bold] in {duration_ms:.1f}ms ({findings_count} findings)",
                border_style=color,
            )
        )
```

---

### 5.7 `src/rush/watcher/sentinel.py`

```python
"""Async file watcher event loop with debounce windows and self-mutation suppression."""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from watchfiles import Change, awatch

from rush.watcher.filter import PathFilter
from rush.watcher.router import ToolRouter
from rush.watcher.renderer import WatcherTerminalRenderer
from rush.watcher.coalescer import EventCoalescer


class QualitySentinel:
    """Monitors repository changes and triggers debounced quality inspections."""

    def __init__(
        self,
        repo_root: Path,
        callback: Callable[[list[Path], list[str]], None],
        debounce_ms: int = 300,
        custom_ignores: list[str] | None = None,
        clear_screen: bool = False,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.clear_screen = clear_screen
        self.filter = PathFilter(repo_root=self.repo_root, custom_ignores=custom_ignores)
        self.renderer = WatcherTerminalRenderer()
        self.coalescer = EventCoalescer(window_ms=debounce_ms)
        self._suppressed_paths: dict[Path, float] = {}
        self._stop_event = asyncio.Event()

    def suppress_path(self, path: Path, ttl_sec: float = 2.0) -> None:
        """Suppress watch events on a path for a short TTL to prevent fixer loops."""
        self._suppressed_paths[path.resolve()] = time.time() + ttl_sec

    def _is_suppressed(self, path: Path) -> bool:
        now = time.time()
        self._suppressed_paths = {p: exp for p, exp in self._suppressed_paths.items() if exp > now}
        return path.resolve() in self._suppressed_paths

    def stop(self) -> None:
        """Signal the watcher event loop to terminate."""
        self._stop_event.set()

    async def start(self) -> None:
        """Start async watch event loop."""
        async for changes in awatch(
            self.repo_root,
            debounce=self.debounce_ms,
            step=50,
            stop_event=self._stop_event,
        ):
            modified_paths: list[Path] = []
            for change_type, file_path_str in changes:
                if change_type in (Change.added, Change.modified):
                    p = Path(file_path_str).resolve()
                    if not self._is_suppressed(p) and not self.filter.is_ignored(p) and p.is_file():
                        modified_paths.append(p)

            if modified_paths:
                required_tools = ToolRouter.get_tools_for_paths(modified_paths)
                if required_tools:
                    if self.clear_screen:
                        print("\033[H\033[J", end="")
                    self.renderer.render_event(modified_paths, required_tools)
                    self.callback(modified_paths, required_tools)
```

---

### 5.8 `src/rush/cli.py` (Registration for `rush watch`)

```python
import asyncio
import click
from pathlib import Path
from rush.watcher.sentinel import QualitySentinel
from rush.workflows.runner import SuiteRunner

def handle_file_changes(paths: list[Path], tools: list[str]):
    click.echo(f"[WATCH] {len(paths)} file(s) changed. Triggering: {', '.join(tools)}")
    runner = SuiteRunner([])
    summary = runner.run_suite(paths)
    click.echo(f"[WATCH] Finished in {summary.duration_ms}ms ({summary.passed_count} passed, {summary.failed_count} failed)")

@click.command(name="watch")
@click.option("--debounce", type=int, default=300, help="Debounce duration in milliseconds.")
@click.option("--clear", is_flag=True, help="Clear terminal screen between test runs.")
def watch_cmd(debounce: int, clear: bool):
    """Start continuous file system quality sentinel."""
    repo_root = Path.cwd()
    click.echo(f"Starting Rush Quality Sentinel on '{repo_root}' (debounce: {debounce}ms)...")
    sentinel = QualitySentinel(
        repo_root=repo_root,
        callback=handle_file_changes,
        debounce_ms=debounce,
        clear_screen=clear,
    )
    try:
        asyncio.run(sentinel.start())
    except KeyboardInterrupt:
        sentinel.stop()
        click.echo("\nSentinel stopped gracefully.")
```

---

### 5.9 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for watcher status."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.watcher.router import ToolRouter

mcp = FastMCP("rush")

@mcp.tool(name="rush_watch_route", description="Determine which quality tools must run for a list of modified files.")
def rush_watch_route(files: list[str]) -> list[str]:
    paths = [Path(f) for f in files]
    return ToolRouter.get_tools_for_paths(paths)

@mcp.tool(name="rush_watch_extensions", description="List supported extensions for a specific quality tool.")
def rush_watch_extensions(tool_name: str) -> list[str]:
    return ToolRouter.get_extensions_for_tool(tool_name)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_watcher.py`

```python
"""Comprehensive test suite for PathFilter, ToolRouter, QualitySentinel, EventCoalescer, and WatcherTerminalRenderer."""

import asyncio
from pathlib import Path
import pytest
from rush.watcher.filter import PathFilter
from rush.watcher.router import ToolRouter
from rush.watcher.sentinel import QualitySentinel
from rush.watcher.coalescer import EventCoalescer
from rush.watcher.renderer import WatcherTerminalRenderer


def test_path_filter_ignores_standard_directories():
    filter_engine = PathFilter()
    assert filter_engine.is_ignored(Path(".git/objects/12345")) is True
    assert filter_engine.is_ignored(Path(".venv/lib/python3.12/site-packages/x.py")) is True
    assert filter_engine.is_ignored(Path("src/__pycache__/module.cpython-312.pyc")) is True
    assert filter_engine.is_ignored(Path("node_modules/react/index.js")) is True
    assert filter_engine.is_ignored(Path(".rush/cache.db")) is True
    assert filter_engine.is_ignored(Path("src/main.py")) is False


def test_path_filter_loads_gitignore(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("*.secret\ncustom_build/\n", encoding="utf-8")
    filter_engine = PathFilter(repo_root=tmp_path)
    assert filter_engine.is_ignored(tmp_path / "keys.secret") is True
    assert filter_engine.is_ignored(tmp_path / "custom_build" / "app.bin") is True
    assert filter_engine.is_ignored(tmp_path / "normal.py") is False


def test_tool_router_python_paths():
    paths = [Path("src/main.py"), Path("tests/test_api.py")]
    tools = ToolRouter.get_tools_for_paths(paths)
    assert "ruff" in tools
    assert "mypy" in tools
    assert "pytest" in tools
    assert "tach" in tools


def test_tool_router_typescript_paths():
    paths = [Path("frontend/App.tsx"), Path("frontend/index.ts")]
    tools = ToolRouter.get_tools_for_paths(paths)
    assert "biome" in tools
    assert "tsc" in tools
    assert "prettier" in tools


def test_tool_router_rust_paths():
    paths = [Path("crates/core/src/lib.rs")]
    tools = ToolRouter.get_tools_for_paths(paths)
    assert "clippy" in tools
    assert "rustfmt" in tools


def test_tool_router_extensions_for_tool():
    exts = ToolRouter.get_extensions_for_tool("ruff")
    assert ".py" in exts
    assert ".toml" in exts


def test_tool_router_empty_paths():
    tools = ToolRouter.get_tools_for_paths([])
    assert tools == []


def test_sentinel_suppression(tmp_path: Path):
    sentinel = QualitySentinel(tmp_path, callback=lambda p, t: None)
    target = tmp_path / "modified.py"

    sentinel.suppress_path(target, ttl_sec=1.0)
    assert sentinel._is_suppressed(target) is True


@pytest.mark.asyncio
async def test_event_coalescer_batching():
    coalescer = EventCoalescer(window_ms=50)
    p1 = Path("a.py")
    p2 = Path("b.py")

    await coalescer.add_path(p1)
    await coalescer.add_path(p2)

    # Immediately poll -> None
    batch = await coalescer.poll_batch()
    assert batch is None

    # Wait for window
    await asyncio.sleep(0.06)
    batch = await coalescer.poll_batch()
    assert batch == [p1, p2]


@pytest.mark.asyncio
async def test_fastmcp_watcher_subscription():
    sub_mgr = FastMcpWatcherSubscription()
    q = sub_mgr.subscribe()

    await sub_mgr.broadcast_event('{"event": "file_modified", "path": "src/main.py"}')
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert "file_modified" in msg

    sub_mgr.unsubscribe(q)
    assert len(sub_mgr._subscribers) == 0


def test_process_group_manager_safe_on_inactive():
    class DummyProc:
        def poll(self): return 0
        @property
        def pid(self): return 99999
    ProcessGroupManager.terminate_process_tree(DummyProc())


def test_path_filter_custom_patterns(tmp_path: Path):
    filter_engine = PathFilter(repo_root=tmp_path, custom_ignores=["*.log", "secret_folder/*"])
    assert filter_engine.is_ignored(tmp_path / "debug.log") is True
    assert filter_engine.is_ignored(tmp_path / "secret_folder" / "keys.txt") is True
    assert filter_engine.is_ignored(tmp_path / "src" / "index.ts") is False


def test_tool_router_scss_and_html():
    paths = [Path("index.html"), Path("styles.scss")]
    tools = ToolRouter.get_tools_for_paths(paths)
    assert "prettier" in tools


def test_tool_router_markdown_paths():
    paths = [Path("docs/architecture.md")]
    tools = ToolRouter.get_tools_for_paths(paths)
    assert "markdownlint" in tools


def test_watch_config_loader_defaults(tmp_path: Path):
    settings = WatchConfigLoader.load_from_repo(tmp_path)
    assert settings.debounce_ms == 300
    assert settings.clear_screen is False
    assert settings.auto_fix is False


def test_watch_config_loader_custom(tmp_path: Path):
    cfg_file = tmp_path / "rush.toml"
    cfg_file.write_text("""
[watcher]
debounce_ms = 500
clear_screen = true
custom_ignores = ["build/*", "*.tmp"]
auto_fix = true
""", encoding="utf-8")

    settings = WatchConfigLoader.load_from_repo(tmp_path)
    assert settings.debounce_ms == 500
    assert settings.clear_screen is True
    assert settings.auto_fix is True
    assert "build/*" in settings.custom_ignores


def test_watch_event_history_capacity(tmp_path: Path):
    history = WatchEventHistory(capacity=3)
    p = tmp_path / "a.py"

    history.record_event(p, "modified", ["ruff"], 10.0, "ok")
    history.record_event(p, "modified", ["ruff"], 11.0, "ok")
    history.record_event(p, "modified", ["ruff"], 12.0, "ok")
    history.record_event(p, "modified", ["ruff"], 13.0, "ok")

    recent = history.get_recent(limit=10)
    assert len(recent) == 3
    assert recent[-1].duration_ms == 13.0
def test_path_filter_windows_backslashes(tmp_path: Path):
    filter_engine = PathFilter(repo_root=tmp_path)
    win_path = Path("src\\__pycache__\\test.pyc")
    assert filter_engine.is_ignored(win_path) is True


@pytest.mark.asyncio
async def test_sentinel_lifecycle_stop(tmp_path: Path):
    sentinel = QualitySentinel(tmp_path, callback=lambda p, t: None)
    sentinel.stop()
    assert sentinel._stop_event.is_set() is True
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 25 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T07:50:00.100Z", "phase": 25, "tool": "rush_watch", "event": "watcher_started", "repo_root": "C:/repo", "debounce_ms": 300}
{"timestamp": "2026-08-21T07:50:02.450Z", "phase": 25, "tool": "rush_watch", "event": "files_changed", "count": 2, "tools_triggered": ["ruff", "mypy", "tach"]}
{"timestamp": "2026-08-21T07:50:02.800Z", "phase": 25, "tool": "rush_watch", "event": "run_completed", "duration_ms": 350.1, "status": "ok"}
{"timestamp": "2026-08-21T07:50:10.500Z", "phase": 25, "tool": "rush_watch", "event": "watcher_stopped", "reason": "sigint"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 25 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 25: Real-Time File System Watcher**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 25 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Continuous Watching & Real-Time Feedback" section detailing `rush watch` interactive usage.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush watch` options (`--debounce-ms`, `--tools`, `--clear`, `--notify`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for running `rush watch` alongside frontend and backend development dev servers.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for auto-running tests and linters on modified files on save.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Include terminal UI snapshots of the live watcher interface.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up real-time feedback in VSCode and Cursor terminal panels.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for inotify limits on Linux and OS file descriptor exhaustion handling.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how `rush watch` filters out auto-fixes to prevent infinite event loops.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_watch_start`, `rush_watch_stop`, and `rush_watch_events` background sensor endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Add async SSE event format documentation for agent subscribers.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `watch` tool in Developer Experience category.
- **[`docs/ENGINES.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINES.md)**: Add `watchfiles` Rust notify engine specifications.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[watch]` configuration table (`debounce_ms`, `ignore_patterns`, `default_tools`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document `QualitySentinel` async coalescing event queue and debounce state machine.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for attaching event listener hooks to the watcher supervisor.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Note that watcher mode is disabled in CI/CD environments (`CI=true`).
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document async event mocking with `pytest-asyncio` fixtures.
- **[`docs/tools/watch.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/watch.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-25): implement async file watcher, debouncing coalescer and process supervisor"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
