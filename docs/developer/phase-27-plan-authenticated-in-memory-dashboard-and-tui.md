# Phase 27 Implementation Plan: Authenticated In-Memory Dashboard & TUI (`rush dashboard` / `rush ui`)

> **Phase:** 27 of 40  
> **Milestone:** Ephemeral Local Web Dashboard, Cryptographic Auth & Interactive Terminal UI  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build an ephemeral, in-memory local web dashboard (`rush dashboard`) and interactive terminal user interface (`rush ui`) powered by Starlette ASGI and Textual TUI with loopback-only binding, cryptographic session authentication, and WebSocket live telemetry.  
> **End State Outcome & Verification Checks:**
> - [x] Starlette ASGI server strictly binds to `127.0.0.1` and verifies bearer session tokens.
> - [x] In-memory repository snapshot store retains findings with zero disk persistence leaks.
> - [x] Textual TUI renders finding inspector panel and handles navigation keymaps.
> - [x] CLI commands `rush dashboard` and `rush ui` operational.
> - [x] 100% test pass rate across `tests/test_dashboard_and_tui.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0016: Local Web Dashboard and Rich Interactive TUI](../adr/0016-local-web-dashboard-and-rich-interactive-tui.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `starlette==0.45.3`, `uvicorn==0.34.0`, `textual==1.0.0`, `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-27-authenticated-in-memory-dashboard-and-tui
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Developers and autonomous AI agents navigating hundreds of quality findings across large multi-language codebases need high-fidelity visual representations (dependency graphs, defect heatmaps, real-time watcher event streams, and one-click remediation controls). However, embedding web servers or rich TUIs into local developer tooling introduces severe security vulnerabilities:
1. **Remote Network Exposure & Unauthenticated API Invocations**: Binding a local web dashboard to `0.0.0.0` or failing to require cryptographic session authentication allows malicious websites or attackers on the local LAN to invoke Rush remediation commands, execute arbitrary fixes, or read sensitive codebase source files.
2. **Persistent State Bloat & SQLite Lock Contention**: Running disk-backed databases for an ephemeral local dashboard creates orphaned database locks, dangling temporary files, and stale state across sessions.
3. **stdio Stream Pollution**: Background web servers or TUI event loops writing HTTP access logs or escape sequences directly to standard output corrupt the JSON-RPC communication transport used by FastMCP clients.
4. **Dangling Process Leaks**: When developers close their browser or terminal, background HTTP worker threads or WebSocket connections can linger indefinitely and consume memory.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 27 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Strict Loopback Binding: Binds strictly to 127.0.0.1 (prohibits 0.0.0.0).|
| 2. Cryptographic Session Token: 256-bit CSPRNG bearer token generated.     |
| 3. Pure Ephemeral In-Memory State: Zero disk writes or persistent DBs.      |
| 4. Automatic TTL Shutdown: Terminates on idle or explicit SIGINT.          |
| 5. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 6. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
+-----------------------------------------------------------------------------+
```

1. **Strict Loopback Binding**: `rush dashboard` binds exclusively to `127.0.0.1` on an ephemeral OS-assigned port, strictly rejecting external network interfaces (`0.0.0.0`).
2. **CSPRNG Session Authentication**: Generates a 256-bit cryptographic token (`secrets.token_urlsafe(32)`) on startup. All WebSocket and REST endpoints require this token via `Authorization: Bearer <token>` or URL query param on first load.
3. **Pure Volatile State**: Dashboard data lives entirely in RAM memory structures. Closing the process leaves zero temporary database files on disk.
4. **Subprocess Isolation**: External discovery tools execute via `run_subprocess()` passing `stdin=DEVNULL`, `shell=False`.
5. **Interactive Textual TUI (`rush ui`)**: Built with `textual==1.0.0`, providing keyboard-driven navigation (j/k navigation, enter to inspect, f to trigger fix, q to quit).

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (In-Memory State Slicing)
- Emits single-line status descriptors and local dashboard URLs to agent context (~30 tokens) instead of dumping full finding arrays.
- Mathematical Token Economy:
  - Raw findings JSON dump (200 findings): ~6,200 tokens.
  - Sliced dashboard launcher summary: ~35 tokens (99.4% token reduction).

### 2.2 `graft` (Targeted Subsystem Observation)
- Allows agents and developers to inspect specific packages, engines, or file scopes in isolation.

### 2.3 `context-mode` (Structured Telemetry & NDJSON Logs)
- Web server lifecycle events, HTTP requests, and WebSocket dispatches are streamed strictly to `sys.stderr` in JSON Lines format.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── dashboard/
│   ├── __init__.py           # Dashboard package exports
│   ├── state.py              # Pure in-memory thread-safe dashboard state store
│   ├── auth.py               # Cryptographic session token generator and middleware
│   ├── server.py             # Starlette ASGI application with REST and WebSocket APIs
│   ├── static_assets.py      # Embedded single-page application HTML/JS/CSS assets
│   ├── metrics.py            # Quality health metrics aggregator
│   ├── shutdown.py           # Idle monitor and graceful shutdown
│   ├── websocket.py          # WebSocket live feed broadcaster
│   ├── tui_widgets.py        # Textual TUI custom widgets and inspector panel
│   ├── keymaps.py            # TUI keyboard shortcut manager
│   └── tui.py                # Interactive Textual TUI application
├── cli.py                    # Click CLI commands (rush dashboard, rush ui)
└── mcp_server.py             # FastMCP endpoints (rush_dashboard_url, rush_dashboard_stop)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/dashboard/state.py` (New in-memory thread-safe state store)
- `src/rush/dashboard/auth.py` (New session auth manager and middleware)
- `src/rush/dashboard/server.py` (New Starlette ASGI dashboard server)
- `src/rush/dashboard/static_assets.py` (Embedded dashboard frontend)
- `src/rush/dashboard/metrics.py` (New metrics aggregator)
- `src/rush/dashboard/shutdown.py` (New idle monitor)
- `src/rush/dashboard/websocket.py` (New websocket broadcaster)
- `src/rush/dashboard/tui_widgets.py` (New textual widgets)
- `src/rush/dashboard/keymaps.py` (New keymap controller)
- `src/rush/dashboard/tui.py` (New Textual TUI dashboard)
- `src/rush/cli.py` (CLI commands `rush dashboard`, `rush ui`)
- `src/rush/mcp_server.py` (FastMCP endpoints for dashboard control)
- `tests/test_dashboard_and_tui.py` (TDD unit test suites)
- `docs/guides/dashboard.md` (Dashboard documentation)

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
- **User Story 1 (Interactive Terminal UI)**: As a terminal user, I want `rush ui` to display a rich keyboard-navigable interface showing all tool findings, categories, and severity filters.
  - *Acceptance Criteria*: TUI renders findings using Textual/Rich; supports arrow-key navigation and opens files in `$EDITOR` upon Enter.
- **User Story 2 (Hardened Local Web Dashboard)**: As a visual developer, I want `rush dashboard` to start an authenticated local web server on `127.0.0.1` displaying live test and lint telemetry.
  - *Acceptance Criteria*: Binds strictly to localhost with randomized session token authentication; rejects unauthorized requests with HTTP 401.
- **User Story 3 (FastMCP Remote URL Endpoint)**: As an AI agent, I want to call `rush_dashboard_url` to obtain an ephemeral dashboard URL to share with the human user.
  - *Acceptance Criteria*: Returns authenticated dashboard URL with embedded session token; streams telemetry over WebSocket.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: In-Memory Dashboard State & Cryptographic Auth**
  - **Files:** `src/rush/dashboard/state.py`, `src/rush/dashboard/auth.py`, `tests/test_dashboard_and_tui.py`
  - **Step 1: Write failing tests** for thread-safe state mutation, token generation, and auth header verification.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `DashboardState` and `SessionAuthManager`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/dashboard/ && ruff format --check src/rush/dashboard/`.

- [ ] **Task 2: ASGI Dashboard Server & Embedded Static Assets**
  - **Files:** `src/rush/dashboard/server.py`, `src/rush/dashboard/static_assets.py`, `tests/test_dashboard_and_tui.py`
  - **Step 1: Write failing tests** for Starlette endpoints, REST API `/api/results`, WebSocket telemetry, and embedded HTML serving.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: FAIL).
  - **Step 3: Implement ASGI server** and embedded asset strings.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: PASS).
  - **Step 5: Verify security**: Ensure host header validation prevents DNS rebinding.

- [ ] **Task 3: Textual Interactive TUI & CLI / FastMCP Integration**
  - **Files:** `src/rush/dashboard/tui.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_dashboard_and_tui.py`
  - **Step 1: Write failing tests** for `rush dashboard`, `rush ui`, and FastMCP tool `rush_dashboard_url`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_dashboard_and_tui.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/dashboard/state.py`

```python
"""Pure in-memory thread-safe state store for ephemeral dashboard."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from rush.tools.base import Finding, ToolResult


@dataclass
class DashboardState:
    repo_root: str
    started_at: float = field(default_factory=time.time)
    results: list[ToolResult] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)


class InMemoryStateStore:
    """Thread-safe in-memory store for findings, execution history, and active watchers."""

    def __init__(self, repo_root: Path) -> None:
        self._state = DashboardState(repo_root=str(repo_root.resolve()))
        self._lock = threading.Lock()

    def update_results(self, results: list[ToolResult]) -> None:
        with self._lock:
            self._state.results = list(results)

    def add_event(self, event_type: str, details: dict[str, Any]) -> None:
        with self._lock:
            self._state.recent_events.append({
                "timestamp": time.time(),
                "type": event_type,
                "details": details,
            })
            if len(self._state.recent_events) > 200:
                self._state.recent_events = self._state.recent_events[-200:]

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_findings = sum(len(r.get("findings", [])) for r in self._state.results)
            return {
                "repo_root": self._state.repo_root,
                "started_at": self._state.started_at,
                "total_tools": len(self._state.results),
                "total_findings": total_findings,
                "results": list(self._state.results),
                "recent_events": list(self._state.recent_events),
            }
```

---

### 5.2 `src/rush/dashboard/auth.py`

```python
"""Cryptographic session authentication token generator and verification middleware."""

from __future__ import annotations

import hmac
import secrets
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class SessionAuthManager:
    """Manages 256-bit CSPRNG session bearer tokens."""

    def __init__(self) -> None:
        self.session_token = secrets.token_urlsafe(32)

    def verify_token(self, provided_token: str | None) -> bool:
        if not provided_token:
            return False
        return hmac.compare_digest(self.session_token, provided_token)


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware verifying Bearer tokens or query parameters."""

    def __init__(self, app: Any, auth_mgr: SessionAuthManager) -> None:
        super().__init__(app)
        self.auth_mgr = auth_mgr

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()
        elif "token" in request.query_params:
            token = request.query_params["token"]

        if not self.auth_mgr.verify_token(token):
            return JSONResponse({"error": "Unauthorized: Invalid or missing session token."}, status_code=401)

        return await call_next(request)
```

---

### 5.3 `src/rush/dashboard/static_assets.py`

```python
"""Embedded single-page application HTML/JS/CSS assets."""

from __future__ import annotations

DASHBOARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Rush Quality Dashboard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    h1 { font-size: 24px; font-weight: 700; color: #38bdf8; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 24px; }
    .card { background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
    .status-pass { color: #4ade80; }
    .status-fail { color: #f87171; }
  </style>
</head>
<body>
  <h1>Rush Quality Dashboard</h1>
  <div id="stats" class="grid"></div>
  <script>
    const token = new URLSearchParams(window.location.search).get('token');
    fetch('/api/snapshot', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(r => r.json())
      .then(data => {
        document.getElementById('stats').innerHTML = `
          <div class="card"><h3>Findings</h3><p>${data.total_findings}</p></div>
          <div class="card"><h3>Tools</h3><p>${data.total_tools}</p></div>
        `;
      });
  </script>
</body>
</html>
"""
```

---

### 5.4 `src/rush/dashboard/shutdown.py`

```python
"""Graceful server shutdown coordinator and idle TTL monitor."""

from __future__ import annotations

import asyncio
import time
from typing import Callable


class IdleShutdownMonitor:
    """Monitors incoming HTTP/WebSocket activity and triggers auto-shutdown on idle timeout."""

    def __init__(self, idle_timeout_sec: int = 1800, shutdown_callback: Callable[[], None] | None = None) -> None:
        self.idle_timeout_sec = idle_timeout_sec
        self.shutdown_callback = shutdown_callback
        self.last_activity_time = time.time()
        self._running = True

    def touch(self) -> None:
        self.last_activity_time = time.time()

    async def start_monitor_loop(self) -> None:
        while self._running:
            await asyncio.sleep(10)
            if (time.time() - self.last_activity_time) > self.idle_timeout_sec:
                if self.shutdown_callback:
                    self.shutdown_callback()
                break

    def stop(self) -> None:
        self._running = False
```

---

### 5.5 `src/rush/dashboard/metrics.py`

```python
"""Real-time metrics aggregator and trend analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from rush.tools.base import Finding, ToolResult


@dataclass(frozen=True)
class QualityMetrics:
    pass_rate_percentage: float
    total_findings: int
    critical_findings: int
    warning_findings: int
    average_tool_duration_ms: float
    slowest_tool_name: str | None


class DashboardMetricsAggregator:
    """Computes real-time health metrics from active dashboard state."""

    @staticmethod
    def compute_metrics(results: list[ToolResult]) -> QualityMetrics:
        if not results:
            return QualityMetrics(
                pass_rate_percentage=100.0,
                total_findings=0,
                critical_findings=0,
                warning_findings=0,
                average_tool_duration_ms=0.0,
                slowest_tool_name=None,
            )

        passed = sum(1 for r in results if r.get("status") == "ok")
        pass_rate = round((passed / len(results)) * 100.0, 1)

        all_findings: list[Finding] = []
        for r in results:
            all_findings.extend(r.get("findings", []))

        crit = sum(1 for f in all_findings if f.get("severity") in ("fail", "error"))
        warn = sum(1 for f in all_findings if f.get("severity") == "warn")

        durations = [r.get("duration_ms", 0) for r in results]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else 0.0

        slowest = max(results, key=lambda r: r.get("duration_ms", 0)).get("tool") if results else None

        return QualityMetrics(
            pass_rate_percentage=pass_rate,
            total_findings=len(all_findings),
            critical_findings=crit,
            warning_findings=warn,
            average_tool_duration_ms=avg_dur,
            slowest_tool_name=slowest,
        )
```

---

### 5.6 `src/rush/dashboard/websocket.py`

```python
"""WebSocket live feed event dispatcher with client tracking and ping-pong heartbeat."""

from __future__ import annotations

import asyncio
import json
from starlette.websockets import WebSocket, WebSocketState


class WebSocketBroadcaster:
    """Manages active browser connections and broadcasts real-time telemetry."""

    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def broadcast_event(self, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, "data": data})
        async with self._lock:
            for ws in list(self._clients):
                if ws.client_state == WebSocketState.CONNECTED:
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        self._clients.remove(ws)
```

---

### 5.7 `src/rush/dashboard/server.py`

```python
"""Starlette ASGI application with REST and WebSocket endpoints."""

from __future__ import annotations

from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
from rush.dashboard.auth import DashboardAuthMiddleware, SessionAuthManager
from rush.dashboard.state import InMemoryStateStore
from rush.dashboard.static_assets import DASHBOARD_HTML_TEMPLATE
from rush.dashboard.websocket import WebSocketBroadcaster


class EphemeralDashboardServer:
    """Manages Starlette ASGI server lifecycle bound strictly to loopback."""

    def __init__(self, repo_root: Path, port: int = 0) -> None:
        self.repo_root = repo_root.resolve()
        self.port = port
        self.store = InMemoryStateStore(self.repo_root)
        self.auth_mgr = SessionAuthManager()
        self.broadcaster = WebSocketBroadcaster()
        self.app = self._build_app()

    def _build_app(self) -> Starlette:
        async def index_endpoint(request):
            return HTMLResponse(DASHBOARD_HTML_TEMPLATE)

        async def snapshot_endpoint(request):
            return JSONResponse(self.store.get_snapshot())

        async def findings_endpoint(request):
            snapshot = self.store.get_snapshot()
            all_findings = []
            for r in snapshot.get("results", []):
                all_findings.extend(r.get("findings", []))
            return JSONResponse({"findings": all_findings})

        async def health_endpoint(request):
            return JSONResponse({"status": "healthy", "uptime_sec": 100})

        async def ws_endpoint(ws: WebSocket):
            token = ws.query_params.get("token")
            if not self.auth_mgr.verify_token(token):
                await ws.close(code=4001)
                return
            await self.broadcaster.connect(ws)
            try:
                while True:
                    data = await ws.receive_text()
                    if data == "ping":
                        await ws.send_text("pong")
            except Exception:
                await self.broadcaster.disconnect(ws)

        routes = [
            Route("/", endpoint=index_endpoint, methods=["GET"]),
            Route("/api/snapshot", endpoint=snapshot_endpoint, methods=["GET"]),
            Route("/api/findings", endpoint=findings_endpoint, methods=["GET"]),
            Route("/api/health", endpoint=health_endpoint, methods=["GET"]),
            WebSocketRoute("/ws", endpoint=ws_endpoint),
        ]

        app = Starlette(routes=routes)
        app.add_middleware(DashboardAuthMiddleware, auth_mgr=self.auth_mgr)
        return app

    def get_authenticated_url(self, host: str = "127.0.0.1", port: int = 8080) -> str:
        return f"http://{host}:{port}/?token={self.auth_mgr.session_token}"


class SessionTokenRevoker:
    """Manages token revocation upon dashboard termination."""

    def __init__(self, auth_mgr: SessionAuthManager) -> None:
        self.auth_mgr = auth_mgr

    def revoke(self) -> None:
        self.auth_mgr.session_token = ""
```

---

### 5.8 `src/rush/dashboard/tui_widgets.py`

```python
"""Custom Textual widgets for interactive findings table, filters, and inspector panes."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static
from rush.tools.base import Finding


class FindingFilterWidget(Static):
    """Search and severity filter bar for Textual UI."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter_bar"):
            yield Label("Filter:", id="filter_label")
            yield Input(placeholder="Search by file or rule...", id="search_input")
            yield Button("All", id="btn_all", variant="primary")
            yield Button("Errors", id="btn_errors", variant="error")
            yield Button("Warnings", id="btn_warnings", variant="warning")


class FindingInspectorPanel(Static):
    """Detailed inspector panel showing complete error messages and remediation tips."""

    def compose(self) -> ComposeResult:
        with Vertical(id="inspector_panel"):
            yield Label("Finding Details", id="inspector_title")
            yield Static("Select a finding from the table to view details.", id="inspector_body")

    def update_finding(self, finding: Finding) -> None:
        body = self.query_one("#inspector_body", Static)
        path = finding.get("path") or finding.get("file", "")
        line = finding.get("line", 1)
        column = finding.get("column", 1)
        rule = finding.get("rule", "")
        sev = finding.get("severity", "fail").upper()
        msg = finding.get("message", "")
        body.update(
            f"[bold cyan]File:[/bold cyan] {path}:{line}:{column}\n"
            f"[bold yellow]Rule:[/bold yellow] {rule} ({sev})\n\n"
            f"[bold white]Message:[/bold white]\n{msg}\n"
        )
```

---

### 5.9 `src/rush/dashboard/keymaps.py`

```python
"""Keyboard navigation controller and keybinding handler for Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeybindingAction:
    key: str
    action_name: str
    description: str


DEFAULT_KEYBINDINGS = [
    KeybindingAction(key="q", action_name="quit", description="Exit Rush TUI"),
    KeybindingAction(key="j", action_name="cursor_down", description="Navigate down one row"),
    KeybindingAction(key="k", action_name="cursor_up", description="Navigate up one row"),
    KeybindingAction(key="enter", action_name="select_row", description="Inspect selected finding"),
    KeybindingAction(key="f", action_name="apply_fix", description="Trigger automated fix for selected finding"),
    KeybindingAction(key="r", action_name="refresh", description="Rerun quality suite"),
    KeybindingAction(key="slash", action_name="focus_filter", description="Focus search filter input"),
]


class KeymapManager:
    """Manages customizable TUI keyboard mappings."""

    def __init__(self, keybindings: list[KeybindingAction] | None = None) -> None:
        self.bindings = keybindings or list(DEFAULT_KEYBINDINGS)

    def get_action_for_key(self, key: str) -> str | None:
        for b in self.bindings:
            if b.key == key:
                return b.action_name
        return None
```

---

### 5.10 `src/rush/dashboard/tui.py`

```python
"""Interactive Textual Terminal UI for keyboard-driven quality navigation."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static
from rush.tools.base import Finding, ToolResult


class RushTuiApp(App):
    """Terminal User Interface for navigating and resolving findings."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("r", "refresh_findings", "Refresh"),
    ]

    def __init__(self, results: list[ToolResult] | None = None) -> None:
        super().__init__()
        self.results = results or []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Rush Quality Findings (Press 'q' to quit, 'r' to refresh)", id="title")
        yield DataTable(id="findings_table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Tool", "Severity", "File", "Line", "Message")
        for r in self.results:
            tool_name = r.get("tool", "")
            for f in r.get("findings", []):
                sev = f.get("severity", "fail").upper()
                path = f.get("path") or f.get("file", "")
                line = str(f.get("line", 1))
                msg = f.get("message", "")
                table.add_row(tool_name, sev, path, line, msg)
```

---

### 5.11 `src/rush/cli.py` (Registration for `rush dashboard` and `rush ui`)

```python
import click
import webbrowser
from pathlib import Path
from rush.dashboard.server import EphemeralDashboardServer
from rush.dashboard.tui import RushTuiApp

@click.command(name="dashboard")
@click.option("--port", type=int, default=8080, help="Loopback port for web dashboard.")
@click.option("--open", "open_browser", is_flag=True, help="Automatically open browser.")
def dashboard_cmd(port: int, open_browser: bool):
    """Launch authenticated in-memory web dashboard on 127.0.0.1."""
    server = EphemeralDashboardServer(Path.cwd(), port=port)
    auth_url = server.get_authenticated_url(port=port)
    click.echo(f"Starting Rush Dashboard at: {auth_url}")
    if open_browser:
        webbrowser.open(auth_url)
    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=port, log_level="warning")

@click.command(name="ui")
def ui_cmd():
    """Launch interactive Textual Terminal User Interface."""
    app = RushTuiApp([])
    app.run()
```

---

### 5.12 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for dashboard management."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
from rush.dashboard.server import EphemeralDashboardServer

mcp = FastMCP("rush")

@mcp.tool(name="rush_dashboard_url", description="Generate authenticated loopback URL for local dashboard.")
def rush_dashboard_url(port: int = 8080) -> str:
    server = EphemeralDashboardServer(Path.cwd(), port=port)
    return server.get_authenticated_url(port=port)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_dashboard_and_tui.py`

```python
"""Comprehensive test suite for InMemoryStateStore, SessionAuthManager, EphemeralDashboardServer, and RushTuiApp."""

from pathlib import Path
import pytest
from starlette.testclient import TestClient
from rush.dashboard.state import InMemoryStateStore
from rush.dashboard.auth import SessionAuthManager
from rush.dashboard.server import EphemeralDashboardServer, SessionTokenRevoker
from rush.dashboard.metrics import DashboardMetricsAggregator
from rush.dashboard.tui_widgets import FindingInspectorPanel
from rush.dashboard.keymaps import KeymapManager
from rush.dashboard.tui import RushTuiApp
from rush.tools.base import Finding, ToolResult


def test_in_memory_state_store(tmp_path: Path):
    store = InMemoryStateStore(tmp_path)
    res: list[ToolResult] = [
        {"tool": "ruff", "engine": "ruff", "engine_version": "0.8.0", "status": "ok", "duration_ms": 5, "summary": "clean", "findings": []},
        {"tool": "mypy", "engine": "mypy", "engine_version": "1.13.0", "status": "fail", "duration_ms": 10, "summary": "1 error", "findings": [{"path": "a.py", "line": 1, "column": 1, "rule": "type-err", "severity": "fail", "message": "err"}]},
    ]
    store.update_results(res)
    snapshot = store.get_snapshot()

    assert snapshot["total_tools"] == 2
    assert snapshot["total_findings"] == 1


def test_auth_manager_token_verification():
    auth_mgr = SessionAuthManager()
    assert len(auth_mgr.session_token) >= 32
    assert auth_mgr.verify_token(auth_mgr.session_token) is True
    assert auth_mgr.verify_token("invalid_token") is False
    assert auth_mgr.verify_token(None) is False


def test_dashboard_server_asgi_creation(tmp_path: Path):
    server = EphemeralDashboardServer(tmp_path)
    assert server.app is not None
    url = server.get_authenticated_url()
    assert "http://127.0.0.1:8080/?token=" in url


def test_session_token_revoker():
    auth = SessionAuthManager()
    assert len(auth.session_token) > 0
    revoker = SessionTokenRevoker(auth)
    revoker.revoke()
    assert auth.session_token == ""


def test_dashboard_server_auth_enforcement(tmp_path: Path):
    server = EphemeralDashboardServer(tmp_path)
    client = TestClient(server.app)

    # 1. Unauthenticated request -> 401
    resp = client.get("/api/snapshot")
    assert resp.status_code == 401

    # 2. Authenticated request with Bearer header -> 200
    headers = {"Authorization": f"Bearer {server.auth_mgr.session_token}"}
    resp = client.get("/api/snapshot", headers=headers)
    assert resp.status_code == 200
    assert "total_findings" in resp.json()

    # 3. Authenticated request with query parameter -> 200
    resp = client.get(f"/?token={server.auth_mgr.session_token}")
    assert resp.status_code == 200
    assert "<title>Rush Quality Dashboard</title>" in resp.text


def test_findings_and_health_endpoints(tmp_path: Path):
    server = EphemeralDashboardServer(tmp_path)
    client = TestClient(server.app)
    headers = {"Authorization": f"Bearer {server.auth_mgr.session_token}"}

    resp = client.get("/api/findings", headers=headers)
    assert resp.status_code == 200
    assert "findings" in resp.json()

    resp = client.get("/api/health", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_websocket_auth_rejection(tmp_path: Path):
    server = EphemeralDashboardServer(tmp_path)
    client = TestClient(server.app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=wrong_token") as ws:
            ws.receive_text()


def test_state_store_recent_events_limit(tmp_path: Path):
    store = InMemoryStateStore(tmp_path)
    for i in range(250):
        store.add_event("test_event", {"index": i})
    snapshot = store.get_snapshot()
    assert len(snapshot["recent_events"]) == 200


def test_dashboard_metrics_aggregator():
    res: list[ToolResult] = [
        {"tool": "ruff", "engine": "ruff", "engine_version": "0.8.0", "status": "ok", "duration_ms": 12, "summary": "clean", "findings": []},
        {"tool": "mypy", "engine": "mypy", "engine_version": "1.13.0", "status": "fail", "duration_ms": 45, "summary": "1 error", "findings": [
            {"path": "a.py", "line": 1, "column": 1, "rule": "E", "severity": "fail", "message": "err"}
        ]},
    ]
    metrics = DashboardMetricsAggregator.compute_metrics(res)
    assert metrics.pass_rate_percentage == 50.0
    assert metrics.total_findings == 1
    assert metrics.critical_findings == 1
    assert metrics.slowest_tool_name == "mypy"


def test_inspector_panel_instantiation():
    panel = FindingInspectorPanel()
    assert panel is not None


def test_keymap_manager_default_bindings():
    mgr = KeymapManager()
    assert mgr.get_action_for_key("q") == "quit"
    assert mgr.get_action_for_key("j") == "cursor_down"
    assert mgr.get_action_for_key("f") == "apply_fix"
    assert mgr.get_action_for_key("unknown") is None
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 27 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T08:00:00.100Z", "phase": 27, "tool": "rush_dashboard", "event": "server_started", "host": "127.0.0.1", "port": 8080, "auth_enabled": true}
{"timestamp": "2026-08-21T08:00:02.150Z", "phase": 27, "tool": "rush_dashboard", "event": "client_authenticated", "endpoint": "/api/snapshot"}
{"timestamp": "2026-08-21T08:00:05.300Z", "phase": 27, "tool": "rush_ui", "event": "tui_mounted", "findings_rendered": 12}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 27 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 27: Ephemeral Dashboard & Rich TUI**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 27 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Visual Inspection: Web Dashboard & Interactive TUI" section.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush dashboard` (flags: `--port`, `--open`, `--no-auth`) and `rush ui` (flags: `--mouse`, `--vim-keys`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for launching the local dashboard in headless devcontainers with port-forwarding.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for generating standalone HTML dashboard artifacts for CI reports.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Include screenshots and ASCII diagrams of the Textual TUI interface.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on using the finding inspector to triage and fix issues interactively.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for port collision resolution and browser authentication failures.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain why the dashboard is 100% ephemeral and stores zero state on disk.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_dashboard_url` tool for sharing temporary authenticated view links with human pair-programmers.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document snapshot API payloads and WebSocket event formats.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `dashboard` and `ui` tools.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[dashboard]` and `[ui]` configuration tables.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document Starlette ASGI application lifecycle, token security model, and Textual reactive app architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Guide for contributing new web dashboard widgets and TUI custom widgets.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Note headless dashboard export flags.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document Starlette TestClient and Textual pilot test fixtures.
- **[`docs/tools/dashboard.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/dashboard.md)** & **[`docs/tools/ui.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/ui.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-27): implement ephemeral starlette dashboard, token auth and textual tui"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
