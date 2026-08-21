# Phase 27 Implementation Plan: Authenticated In-Memory Dashboard & Rich TUI

> **Phase:** 27 of 40  
> **Milestone:** Visual Finding Exploration & Interactive Developer Dashboards  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0016: Local Web Dashboard and Rich Interactive TUI](../adr/0016-local-web-dashboard-and-rich-interactive-tui.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `rich==13.9.4`, `mcp==1.28.1`, `click==8.4.2`, `pytest==9.0.3`

---

## 1. Objective & Scope

Developers and vibe-coders need interactive visual navigation of multi-tool findings without cluttering terminal scrollback or running heavy external web frameworks. Phase 27 delivers a fast interactive terminal UI (`rush ui`) and an authenticated, CSRF-hardened local web dashboard (`rush dashboard`).

All HTML, CSS, JavaScript, and SVG assets are compiled into immutable in-memory buffers at startup, binding strictly to IPv4 `127.0.0.1` (never `0.0.0.0`), enforcing ephemeral token authentication (`X-Rush-Auth`), and rejecting DNS rebinding attacks via strict `Host` and `Origin` header validation.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (In-Memory Finding Aggregation)**: The dashboard serves findings from an in-memory JSON state tree with pagination and filtering, allowing developers and agents to explore thousands of findings without printing them to terminal stdout.
- **`graft` (Source Code Preview Slices)**: The dashboard code viewer requests AST code slices (`rush_graft_slice`) on demand when inspecting findings rather than loading entire source files into memory.
- **`context-mode` (Zero Third-Party Web Frameworks)**: Pure Python standard library `http.server` / `socket` architecture adds 0 KB runtime dependency weight.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/dashboard.py` (New: Authenticated zero-dependency local HTTP server with CSRF/rebinding guards)
- `src/rush/tui.py` (New: Rich-based interactive terminal UI with keyboard event loop)
- `src/rush/templates/dashboard.html` (New: Single-file compiled dashboard template)
- `src/rush/cli.py` (Modified: Register `rush ui` and `rush dashboard`)
- `src/rush/mcp_server.py` (Modified: Provide dashboard launch / status hooks)
- `src/rush/catalog.py` (Modified: Register dashboard capabilities)

### Test & Fixture Files
- `tests/test_tui.py` (New: Rich layout generation, navigation, and keypress handling)
- `tests/test_dashboard.py` (New: HTTP server endpoints, token validation, CSRF/rebinding, in-memory latency tests)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_dashboard.py
def test_dashboard_unauthorized_request_rejected(tmp_path):
    server, port, token = start_test_dashboard(tmp_path)
    try:
        # Request missing token
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/api/findings")
        res = conn.getresponse()
        assert res.status == 401
    finally:
        server.shutdown()

def test_dashboard_dns_rebinding_rejected(tmp_path):
    server, port, token = start_test_dashboard(tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", f"/?token={token}", headers={"Host": "malicious.com"})
        res = conn.getresponse()
        assert res.status == 403
    finally:
        server.shutdown()
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/dashboard.py`, `src/rush/tui.py`, and single-file HTML template.

### 4.3 REFACTOR Phase
Ensure single-file HTML template bundles all CSS and JS inline with zero external CDN dependencies, guaranteeing 100% offline capability.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:45:00Z", "phase": 27, "tool": "rush_dashboard", "event": "server_started", "host": "127.0.0.1", "port": 8765, "auth_enabled": true}
{"timestamp": "2026-08-21T07:45:01Z", "phase": 27, "tool": "rush_dashboard", "event": "auth_rejected", "reason": "missing_token", "remote_ip": "127.0.0.1"}
{"timestamp": "2026-08-21T07:45:02Z", "phase": 27, "tool": "rush_dashboard", "event": "rebinding_blocked", "host_header": "malicious.com"}
```

---

## 6. Step-by-Step Task Specifications

### Task 27.1: Authenticated In-Memory Web Server (`src/rush/dashboard.py`)
```python
from __future__ import annotations
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DASHBOARD_HTML_BUFFER: str = ""

def init_in_memory_assets() -> None:
    global DASHBOARD_HTML_BUFFER
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    DASHBOARD_HTML_BUFFER = template_path.read_text(encoding="utf-8")

class AuthenticatedDashboardHandler(BaseHTTPRequestHandler):
    auth_token: str = ""
    
    def do_GET(self) -> None:
        """Validate Host, verify token, serve in-memory HTML or JSON."""
        ...
```

### Task 27.2: Rich Interactive Terminal UI (`src/rush/tui.py`)
Render full-screen tree view, finding pane, and severity filters using Python `rich.live.Live` and `rich.layout.Layout`.

### Task 27.3: CLI & FastMCP Registrations
Register `rush ui` and `rush dashboard` in CLI.

---

## 7. Semantic Drift Review & Verification Gate

1. **IPv4 Localhost Only**: Never bind to `0.0.0.0` or external network interfaces.
2. **Offline Invariant**: Zero CDN dependencies in dashboard template; all assets inline.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
