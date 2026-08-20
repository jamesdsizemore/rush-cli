# Phase 27 Implementation Plan: Authenticated In-Memory Dashboard & Rich TUI

> **Phase:** 27 of 30  
> **Milestone:** Visual Finding Exploration & Interactive Developer Dashboards  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0016: Local Web Dashboard and Rich Interactive TUI](../adr/0016-local-web-dashboard-and-rich-interactive-tui.md)

---

## 1. Objective & Scope

Provide high-fidelity visual finding exploration through an interactive terminal UI (`rush ui`) and an authenticated, CSRF-hardened local web dashboard (`rush dashboard`).

Incorporate **Control 5 (CSRF, Rebinding & Auth Gating)** and **Brooks-Sweep Recommendation 2 (Atomic In-Memory Asset Compilation)** to compile all dashboard HTML, CSS, JavaScript, and SVG assets into immutable in-memory buffers, bind strictly to IPv4 `127.0.0.1`, enforce ephemeral token authentication (`X-Rush-Auth`), and validate `Host` and `Origin` headers.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/tui.py` (New: Rich-based interactive terminal UI)
- `src/rush/dashboard.py` (New: Authenticated zero-dependency local HTTP server)
- `src/rush/templates/dashboard.html` (New: Single-file compiled dashboard template)
- `src/rush/cli.py` (Modified: Register `rush ui` and `rush dashboard`)
- `src/rush/config.py` (Modified: Add `[dashboard]` configuration section)
- `src/rush/logging.py` (Modified: `[rush-dashboard:LEVEL]` and `[rush-tui:LEVEL]`)

### Test & Fixture Files
- `tests/test_tui.py` (New: TUI layout and keyboard handler tests)
- `tests/test_dashboard.py` (New: HTTP server endpoints, token validation, CSRF/rebinding, in-memory latency tests)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_tui.py` and `tests/test_dashboard.py`:
1. `test_tui_layout_generation()`: Verifies layout structure with header, tree view, finding pane, and footer.
2. `test_dashboard_unauthorized_request_rejected()`: Asserts requests lacking `X-Rush-Auth` return HTTP 401.
3. `test_dashboard_dns_rebinding_host_header()`: Asserts requests with `Host: evil.com` return HTTP 403.
4. `test_dashboard_origin_header_validation()`: Asserts cross-origin `fetch` from untrusted origins is rejected.
5. `test_dashboard_in_memory_asset_serving()`: Asserts assets are served entirely from in-memory buffers with sub-millisecond latency.

### 3.2 GREEN Phase
Implement `tui.py`, `dashboard.py`, and CLI commands.

### 3.3 REFACTOR Phase
Ensure zero third-party web frameworks are introduced (using standard library `http.server` / `asyncio`).

---

## 4. Step-by-Step Implementation Tasks

### Task 27.1: Authenticated In-Memory Web Server (`src/rush/dashboard.py`)
```python
from __future__ import annotations
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Pre-compile assets into immutable in-memory buffers upon import/startup
DASHBOARD_HTML_BUFFER: str = ""

def init_in_memory_assets() -> None:
    global DASHBOARD_HTML_BUFFER
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    DASHBOARD_HTML_BUFFER = template_path.read_text(encoding="utf-8")

class AuthenticatedDashboardHandler(BaseHTTPRequestHandler):
    auth_token: str = ""
    
    def do_GET(self) -> None:
        # 1. Validate Host header is 127.0.0.1 or localhost
        # 2. Check auth token in header or query string
        # 3. Serve in-memory HTML buffer or JSON API response
        ...
```

### Task 27.2: Rich Interactive TUI (`src/rush/tui.py`)
```python
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.tree import Tree
from rush.tools.base import ToolResult

def launch_interactive_tui(results: list[ToolResult]) -> None:
    # Rich layout rendering with keyboard event loops
    ...
```

### Task 27.3: Stderr Diagnostics & Logging
- `[rush-dashboard:INFO] Local dashboard started at http://127.0.0.1:{port}/?token={token}`
- `[rush-dashboard:SECURITY_ALERT] Rejected unauthorized request missing X-Rush-Auth header`
- `[rush-dashboard:SECURITY_ALERT] Rejected request with invalid Host header: {host}`
- `[rush-dashboard:ERROR] In-memory asset compilation failed: {asset_name}`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Document `rush ui` and `rush dashboard`).
2. `docs/USER_GUIDE.md` & `docs/user-guide/visual-dashboard.md` (Dashboard navigation guide).
3. `docs/CONFIG_SCHEMA.md` & `docs/reference/configuration-reference.md` (Document `[dashboard]` table).
4. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run dashboard and TUI unit tests
.venv/Scripts/python.exe -m pytest tests/test_tui.py tests/test_dashboard.py -v

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
