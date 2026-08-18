# rush — Architecture (v0.1)

> **Phase 2 deliverable.** This document is the authoritative architecture.
> Code in Phase 3 must conform. Any deviation is a bug against this document,
> not a bug against the code — update this file first.

**Companion docs:** [`requirements.md`](../requirements.md) (what), [`findings.md`](../findings.md) (why), [`task_plan.md`](../task_plan.md) (when), [`progress.md`](../progress.md) (log).

---

## 1. Hard constraints carried forward

From `requirements.md` §2, the ones that shape this architecture:

| # | Constraint | Architectural implication |
|---|---|---|
| C1 | MCP is the only agentic surface | No SDK, no plugin registry, no agent framework |
| C2 | stdio MCP only | Server uses `run_stdio_async()`; no host/port/sse config exposed |
| C3 | Single source of truth per tool | One Python function in `tools/<name>.py`; both CLI and MCP call it |
| C4 | JSON canonical | ToolResult TypedDict → serialized to JSON for both surfaces |
| C5 | stderr logs only | `logging` configured to write NDJSON to `sys.stderr`; stdout is sacred |
| C6 | No external imports beyond deps | rush's only third-party deps are `mcp`, `click`, `rich` |
| C7 | `review` never auto-claims reviewed | `review()` returns `status: heuristic` by default |
| C8 | Palette cyan → green → yellow | All UI strings route through `theme.py` constants |
| C9 | No LLM by default | `review()` heuristics only; `--llm` flag triggers env-key check |
| C10 | Engine discovery not hard-fail | All engine calls go through `common.run_engine()` which returns `status: skipped` on `FileNotFoundError` |

---

## 2. Package layout (final)

```
C:\Users\james\developer\rush-cli\
├── pyproject.toml              # uv-managed; deps: mcp>=1.28,<2, click>=8,<9, rich>=13,<14
├── .python-version             # 3.12
├── README.md
├── AGENTS.md                   # mirrors headcleaner structure
├── CHANGELOG.md
├── INSTALL.md
├── CONTRIBUTING.md
├── requirements.md             # Phase 1
├── task_plan.md                # phase tracker
├── findings.md                 # research + decisions
├── progress.md                 # session log
├── docs/
│   └── ARCHITECTURE.md         # this file (Phase 2)
├── research/                   # 1,055 repos of GitHub research (frozen at Phase 1)
├── src/rush/
│   ├── __init__.py             # version = "0.1.0"
│   ├── cli.py                  # click entrypoint — all 5 subcommands + `mcp serve`
│   ├── mcp.py                  # build_server() -> FastMCP instance + register_tools()
│   ├── theme.py                # palette constants + rich style helpers (C8)
│   ├── config.py               # rush.toml discovery + parsing (walk-up to git root)
│   ├── logging.py              # NDJSON-to-stderr, RUSH_LOG_LEVEL gate, redaction
│   ├── tools/
│   │   ├── __init__.py         # re-exports the 5 tool functions
│   │   ├── base.py             # ToolResult TypedDict, ToolFn ABC, Finding TypedDict
│   │   ├── common.py           # run_engine(), engine_on_path(), parse_json_output()
│   │   ├── review.py           # review() — heuristics + optional LLM
│   │   ├── lint.py             # lint() — engine dispatch per file type
│   │   ├── format.py           # format() — engine dispatch + --check
│   │   ├── test.py             # test() — engine dispatch (pytest / vitest / npm)
│   │   └── security.py         # security() — engine dispatch (pip-audit / npm audit)
│   └── engines/
│       ├── __init__.py         # registry: ENGINES = {"ruff": RuffEngine(), ...}
│       ├── base.py             # Engine ABC: name, version(), run(args) -> EngineResult
│       ├── ruff.py             # RuffEngine (lint + format for Python)
│       ├── eslint.py           # EslintEngine (lint for JS/TS)
│       ├── prettier.py         # PrettierEngine (format for JS/TS + others)
│       ├── vitest.py           # VitestEngine (test for JS/TS, JSON reporter)
│       ├── pytest.py           # PytestEngine (test for Python)
│       ├── pip_audit.py        # PipAuditEngine (security for Python)
│       └── npm_audit.py        # NpmAuditEngine (security for JS/TS)
└── tests/
    ├── conftest.py             # shared fixtures: tmp_repo, sample Python + TS files
    ├── test_base.py            # ToolResult shape + Finding shape
    ├── test_common.py          # engine discovery, subprocess runner, skipped behavior
    ├── test_review.py          # heuristic findings on sample repo
    ├── test_lint.py            # lint() returns canonical shape; skipped if no engine
    ├── test_format.py          # format() respects --check; skipped if no engine
    ├── test_test.py            # test() runs pytest; skipped if no engine
    ├── test_security.py        # security() returns skipped gracefully
    ├── test_config.py          # rush.toml discovery + walk-up + override
    ├── test_logging.py         # NDJSON to stderr, level gate, redaction
    ├── test_theme.py           # palette constants + style helpers
    ├── test_mcp.py             # build_server() registers 5 tools, descriptions present
    └── test_cli.py             # click subcommand smoke tests
```

**Total Python files in `src/rush/`: 19** (8 top-level + 5 tools + 7 engines, minus empty `__init__.py`s counted in totals)
**Total test files: 12** (1 conftest + 11 test files)

---

## 3. Core types — `src/rush/tools/base.py`

### 3.1 `ToolStatus` — Literal type

```python
from typing import Literal

ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]
ToolName   = Literal["review", "lint", "format", "test", "security"]
Severity   = Literal["info", "warn", "error"]
LlmStatus  = Literal["heuristic", "llm"]   # never "reviewed" — that's C7
```

### 3.2 `Finding` — TypedDict (one issue from any engine)

```python
from typing import TypedDict, Optional, Any

class Finding(TypedDict, total=False):
    path: str               # POSIX-style relative path, e.g. "src/foo.py"
    line: int               # 1-indexed
    column: int             # 1-indexed; optional in many engines
    rule: str               # engine-native rule id, e.g. "E501", "no-unused-vars"
    severity: Severity      # normalized: info | warn | error
    message: str
    fix: Optional[dict]     # engine-native autofix hint, or None
```

`total=False` because some engines (esp. heuristics) don't supply every field. Validators in `tools/common.py` normalize before adding to `ToolResult`.

### 3.3 `ToolResult` — TypedDict (the canonical output per §3.5 of requirements.md)

```python
class ToolResult(TypedDict, total=False):
    tool: ToolName
    engine: Optional[str]            # "ruff", "eslint", "heuristic-v1", etc.; null if skipped
    engine_version: Optional[str]    # "0.6.9", "9.15.0", etc.; null if skipped
    status: ToolStatus
    duration_ms: int
    summary: str                     # human-readable one-liner
    findings: list[Finding]          # empty list when no findings
    raw: Optional[Any]               # engine-native payload, for debug or LLM context
    # review-only (omitted for other tools):
    review_kind: LlmStatus           # "heuristic" (default) | "llm" (when --llm used)
    review_provider: Optional[str]   # "anthropic" | "openai"; only when review_kind == "llm"
```

`total=False` because some fields are tool-specific (`review_kind` is only on `review`). Always-present minimum: `{tool, status, duration_ms, summary, findings}`.

### 3.4 `ToolFn` — abstract base for the 5 tool functions

```python
from abc import ABC, abstractmethod
from pathlib import Path

class ToolFn(ABC):
    """Base class for the 5 tool modules. Each subclass is a single
    source-of-truth function callable from both CLI and MCP."""

    name: ToolName

    @abstractmethod
    def __call__(self, path: Path, config: "RushConfig") -> ToolResult:
        """Run the tool on `path` (file or directory) under `config`."""
        ...
```

Why a class and not a bare function: lets us register them in a list (for MCP `add_tool` and CLI dispatch) without each module needing a `register()` shim. The class is a one-method ABC — it's a function with metadata.

### 3.5 Module-level singletons

```python
# src/rush/tools/__init__.py
from .review import ReviewTool
from .lint import LintTool
from .format import FormatTool
from .test import TestTool
from .security import SecurityTool

ALL_TOOLS: list[ToolFn] = [
    ReviewTool(),
    LintTool(),
    FormatTool(),
    TestTool(),
    SecurityTool(),
]
```

CLI and MCP both iterate `ALL_TOOLS` to register subcommands/tools.

---

## 4. Engine dispatch table — `src/rush/engines/`

### 4.1 `Engine` ABC — `engines/base.py`

```python
class EngineResult(TypedDict, total=False):
    exit_code: int
    stdout: str
    stderr: str
    parsed: Optional[Any]        # engine-native JSON if available, else None
    findings: list[Finding]      # normalized from parsed
    summary: str                 # engine-native summary line
    duration_ms: int

class Engine(ABC):
    name: str                    # "ruff", "eslint", etc.
    binary: str                  # executable name to find on PATH
    file_extensions: tuple[str, ...]   # ("py", "pyi") for ruff; ("js","jsx","ts","tsx","mjs","cjs") for eslint

    def version(self) -> Optional[str]:
        """Run `<binary> --version`, parse, return. Cached after first call."""
        ...

    @abstractmethod
    def run(self, path: Path, args: list[str], cwd: Optional[Path] = None) -> EngineResult:
        """Run the engine and return a parsed result. Never raises — returns
        an EngineResult with exit_code != 0 on failure."""
        ...

    def normalize(self, raw: EngineResult, path: Path) -> ToolResult:
        """Convert engine-specific output to canonical ToolResult.
        Default impl wraps EngineResult in a ToolResult skeleton; engines
        override for richer normalization (e.g. ruff's JSON)."""
        ...
```

### 4.2 Engine registry — `engines/__init__.py`

```python
from .ruff import RuffEngine
from .eslint import EslintEngine
from .prettier import PrettierEngine
from .vitest import VitestEngine
from .pytest import PytestEngine
from .pip_audit import PipAuditEngine
from .npm_audit import NpmAuditEngine

# name -> Engine instance
ENGINES: dict[str, Engine] = {
    "ruff":      RuffEngine(),
    "eslint":    EslintEngine(),
    "prettier":  PrettierEngine(),
    "vitest":    VitestEngine(),
    "pytest":    PytestEngine(),
    "pip-audit": PipAuditEngine(),
    "npm-audit": NpmAuditEngine(),
}
```

### 4.3 Tool → engine dispatch

| Tool | Routing rule | Engine chosen |
|---|---|---|
| `review` | None — runs heuristics in-process. Engines only matter when `--use-graft` (v0.2). | n/a (v0.1) |
| `lint` | For each file in `path`, look up engine by extension. If no extension matches: walk up to project root looking for `pyproject.toml` / `package.json`; default to Python if both exist (Python wins for now). | `ruff` for `.py*`; `eslint` for `.js*`/`.jsx`/`.ts*`/`.tsx`/`.mjs`/`.cjs` |
| `format` | Same extension routing as `lint`. | `ruff format` for Python; `prettier --write` for JS/TS |
| `test` | Detect project root once; if `pyproject.toml` → pytest; if `package.json` → vitest preferred, npm fallback. | `pytest` / `vitest` / `npm test` |
| `security` | Same project-root detect as `test`. | `pip-audit` / `npm audit` |

### 4.4 `tools/common.py` — the shared subprocess layer

This is the C10 enforcement point:

```python
def engine_on_path(binary: str) -> bool:
    """Cross-platform: shutil.which(binary) is not None."""
    ...

def run_engine(engine: Engine, path: Path, args: list[str],
               cwd: Optional[Path] = None, timeout: int = 120) -> ToolResult:
    """Run `engine` on `path`. If engine not on PATH, return:
        {tool, engine: engine.name, engine_version: None,
         status: 'skipped', summary: 'ruff not found on PATH (install: pip install ruff)',
         findings: [], duration_ms: 0}
    Never raises. Never writes to stdout."""
    if not engine_on_path(engine.binary):
        return skipped_result(engine, "not found on PATH")
    try:
        result = engine.run(path, args, cwd=cwd)
    except subprocess.TimeoutExpired:
        return error_result(engine, f"timed out after {timeout}s")
    except Exception as e:
        return error_result(engine, f"engine crashed: {e!r}")
    return engine.normalize(result, path)
```

All 5 tool functions call `run_engine(...)` (or the heuristic equivalent for `review`). No tool function ever invokes a subprocess directly.

---

## 5. MCP server skeleton — `src/rush/mcp.py`

```python
from mcp.server.fastmcp import FastMCP
from .tools import ALL_TOOLS

SERVER_NAME = "rush"
SERVER_INSTRUCTIONS = (
    "rush — code-quality tools for coding agents. "
    "Five tools: review, lint, format, test, security. "
    "Each takes a path (file or directory) and returns a structured JSON "
    "with status (ok|warn|fail|error|skipped), findings, and summary. "
    "If status is 'skipped', the underlying engine (ruff/eslint/etc.) is "
    "not installed; install it or pick a different path. "
    "Pairs well with `npx @nanonets/graft` for context-graph queries."
)

def build_server() -> FastMCP:
    """Construct and return the FastMCP server with all 5 tools registered.
    Does NOT start serving — caller decides transport."""
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    _register_tools(server)
    return server

def _register_tools(server: FastMCP) -> None:
    """Register each tool function as an MCP tool. The tool's `name` becomes
    the MCP tool name; the docstring (first line) becomes the description."""
    for tool in ALL_TOOLS:
        # FastMCP requires a sync or async callable; tool functions are sync
        # (they do subprocess + JSON parse, no I/O await needed).
        server.add_tool(
            fn=tool.__call__,
            name=tool.name,
            description=tool.mcp_description,   # per-tool, < 200 chars (Q3)
        )

async def run_stdio() -> None:
    """Entry point for `rush mcp serve`. Blocks until the parent process
    disconnects stdin (i.e. the agent disconnects)."""
    server = build_server()
    await server.run_stdio_async()
```

### 5.1 Tool name conventions (C3, Q3)

| MCP tool name | What the agent calls |
|---|---|
| `rush_review` | `review(path, ...)` |
| `rush_lint` | `lint(path, ...)` |
| `rush_format` | `format(path, check=False)` |
| `rush_test` | `test(path)` |
| `rush_security` | `security(path)` |

**Naming rule:** `<verb>_<noun>` matches the Graft pattern we adopted (C4 + Findings §"Graft — rush's conceptual neighbor"). All under the `rush_` namespace prefix so multi-server sessions don't collide with `graft_find_code`, `chrome-devtools-mcp`'s tools, etc.

### 5.2 MCP description format (per Q3: <200 chars)

Each tool's `mcp_description` follows the same template:

```
<verb> <path>. Returns {status, findings[], summary}. Engines: <engines>.
status='skipped' means engine not on PATH. <one sentence on what it does>.
```

Example for `lint`:

```
Lint Python/JS/TS files at <path>. Returns {status, findings[], summary}.
Engines: ruff (Python), eslint (JS/TS). status='skipped' means engine not on PATH.
```

(~190 chars — under 200)

---

## 6. CLI surface — `src/rush/cli.py`

Built with click. Each subcommand calls the same `tool.__call__(path, config)` that the MCP tool calls.

```python
import click
from pathlib import Path
from . import __version__
from .tools import ALL_TOOLS
from .config import load_config
from .theme import render_result   # rich rendering for human output
from .logging import setup_logging

@click.group()
@click.version_option(__version__, "--version", "-V")
@click.option("--log-level", envvar="RUSH_LOG_LEVEL", default="warn",
              type=click.Choice(["debug", "info", "warn", "error"]))
def cli(log_level: str) -> None:
    """rush — code-quality tools for humans and coding agents."""
    setup_logging(log_level)

@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Print raw ToolResult JSON")
def review(path: Path, as_json: bool) -> None:
    """Review code at PATH for size, naming, docstrings, complexity smells."""
    _run_tool("review", path, as_json)

# ... similarly for lint, format, test, security ...

@cli.group()
def mcp() -> None:
    """MCP server commands."""

@mcp.command()
def serve() -> None:
    """Start the rush MCP server on stdio (for coding agents)."""
    from .mcp import run_stdio
    import asyncio
    asyncio.run(run_stdio())

def _run_tool(tool_name: str, path: Path, as_json: bool) -> None:
    tool = next(t for t in ALL_TOOLS if t.name == tool_name)
    config = load_config(start=path)
    result = tool(path, config)
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        render_result(result)
    # Exit code: 0 = ok/skipped; 1 = warn/fail; 2 = error
    sys.exit(_exit_code(result))
```

### 6.1 Exit code map

| `status` | Exit code | Rationale |
|---|---|---|
| `ok` | 0 | All clean |
| `skipped` | 0 | Engine not present — not a failure |
| `warn` | 1 | Findings present, non-blocking |
| `fail` | 1 | Blocking findings |
| `error` | 2 | Engine crashed — distinct from "found a bug" |

---

## 7. Logging — `src/rush/logging.py` (C5)

```python
import sys
import json
import logging
import os
from datetime import datetime, timezone

REDACT_KEYS = {"api_key", "token", "secret", "password", "authorization"}

class NdjsonHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Mandatory: never write to stdout (C5)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.format(record.exc_info)
        # Redact obvious secrets in msg
        for key in REDACT_KEYS:
            if key in payload["msg"].lower():
                payload["msg"] = "[REDACTED — secret-like value]"
                break
        sys.stderr.write(json.dumps(payload, default=str) + "\n")
        sys.stderr.flush()

def setup_logging(level: str = "warn") -> None:
    """Wire up stderr NDJSON logging. Idempotent."""
    root = logging.getLogger("rush")
    root.setLevel(getattr(logging, level.upper()))
    # Remove handlers added by previous setup_logging calls (tests)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(NdjsonHandler())
```

### 7.1 Log levels (per requirements §3.6)

| Level | When | What gets logged |
|---|---|---|
| `error` | engine crashes, MCP protocol errors | everything |
| `warn` | `skipped` engines (with install hint), deprecated config keys | + heuristic findings counts |
| `info` | tool entry/exit, engine versions, duration | + which engine was picked per file |
| `debug` | full subprocess argv, raw engine stdout (truncated), timing per phase | + everything |

### 7.2 What is NEVER logged

- API key values (redaction is mandatory)
- Full file contents
- stdout from engines (could contain sensitive data)
- `tool_result["raw"]` payload

---

## 8. Configuration — `src/rush/config.py`

### 8.1 Discovery rule

```
start = path (file or directory passed to tool)
loop:
    candidate = start / "rush.toml"
    if candidate.exists(): return parse(candidate)
    if start has ".git" (file or directory): stop  → no config
    if start.parent == start: stop  → filesystem root, no config
    start = start.parent
```

Returns a `RushConfig` dataclass; missing config returns a `RushConfig()` with all defaults.

### 8.2 Schema (final, matches requirements §3.4)

```python
from dataclasses import dataclass, field

@dataclass
class ProjectConfig:
    src: list[str] = field(default_factory=lambda: ["src"])
    test: list[str] = field(default_factory=lambda: ["tests"])
    exclude: list[str] = field(default_factory=lambda: ["**/.venv/**", "**/node_modules/**"])

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
    tools: dict[str, ToolConfig] = field(default_factory=dict)  # "lint", "format", "test", "security"
    review: ReviewConfig = field(default_factory=ReviewConfig)
    log_level: str = "warn"
```

**Override order** (last wins, evaluated in this order):

1. Hardcoded defaults (in the dataclasses)
2. `rush.toml` values
3. CLI flags (`--engine-args`, `--check`, `--llm`)

### 8.3 TOML parsing — hand-rolled (Q6)

We use the stdlib `tomllib` (3.11+) — no `pydantic`, no `tomli`. Validation is hand-rolled in `config.py` and raises a clear `RushConfigError` on bad input.

---

## 9. Theme — `src/rush/theme.py` (C8)

```python
CYAN   = "#22D3EE"   # primary, ok
GREEN  = "#22FF88"   # secondary, active
YELLOW = "#FFE600"   # tertiary, review-needed, warn
PINK   = "#EC4899"   # failed status only (bright, not red)
GREY   = "#6B7280"   # skipped, muted

# rich style helpers
from rich.style import Style
from rich.console import Console

def console() -> Console:
    return Console(theme={
        "status.ok":       Style(color=CYAN),
        "status.warn":     Style(color=YELLOW),
        "status.fail":     Style(color=PINK, bold=True),
        "status.error":    Style(color=PINK, bold=True),
        "status.skipped":  Style(color=GREY),
        "severity.info":   Style(color=CYAN),
        "severity.warn":   Style(color=YELLOW),
        "severity.error":  Style(color=PINK),
        "tool.review":     Style(color=GREEN),
        "tool.lint":       Style(color=CYAN),
        "tool.format":     Style(color=GREEN),
        "tool.test":       Style(color=CYAN),
        "tool.security":   Style(color=YELLOW),
    })

def render_result(result: ToolResult) -> None:
    """Human-facing rich render: glyph + status + summary line, then a
    Findings table if any. Called only by CLI (C4). MCP returns raw JSON."""
    ...
```

---

## 10. Heuristics for `review` — `src/rush/tools/review.py`

v0.1 ships four heuristics (no LLM call unless `--llm`):

| Heuristic | Rule | Default |
|---|---|---|
| `file-size` | `len(lines) > config.review.max_file_lines` | 400 |
| `todo-density` | `count("TODO", "FIXME", "XXX") / lines > 0.02` | 2% |
| `missing-docstrings` | every `def`/`class` in Python without a docstring immediately above | n/a |
| `naming` | identifiers matching `^[A-Z_]+$` that aren't module-level constants | n/a |

Each heuristic is a function `(path: Path, source: str) -> list[Finding]`. The `ReviewTool.__call__` runs all four (sequentially per Q2 — deterministic output) and aggregates.

### 10.1 `--llm` opt-in (C9)

```python
if use_llm:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return error_result(self.name, "review --llm requires ANTHROPIC_API_KEY or OPENAI_API_KEY in env")
    provider = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "openai"
    # ... call provider with heuristic findings as context ...
    result["review_kind"] = "llm"
    result["review_provider"] = provider
else:
    result["review_kind"] = "heuristic"
```

**Q4 resolution:** the LLM prompt is `Heuristic findings: <JSON>. Write a short summary of the highest-impact issue.` — no free-form asking, deterministic framing.

---

## 11. Testing strategy — `tests/`

### 11.1 Test categories

| Category | What | Skip-on-missing |
|---|---|---|
| Unit | `test_base`, `test_common`, `test_config`, `test_logging`, `test_theme` | none (no engine deps) |
| Tool smoke | `test_review`, `test_lint`, `test_format`, `test_test`, `test_security` | yes — pytest-style `skipif(not engine_on_path(...))` |
| Integration | `test_mcp`, `test_cli` | none |

### 11.2 Shared fixtures (`tests/conftest.py`)

```python
@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A temp dir with a sample Python file (one good, one with findings)
    and a sample TS file. Returns the path."""
    ...

@pytest.fixture
def rush_toml_minimal(tmp_repo: Path) -> Path:
    """Writes a minimal rush.toml in tmp_repo."""
    ...

@pytest.fixture
def skip_if_no(binary: str):
    """pytest.skip decorator factory: `skip_if_no("ruff")(test_fn)`."""
    ...
```

### 11.3 MCP smoke test pattern

```python
# tests/test_mcp.py
import asyncio
from rush.mcp import build_server

def test_server_registers_five_tools():
    server = build_server()
    tools = asyncio.run(server.get_tools())  # private API but stable in 1.28.x
    assert set(tools.keys()) == {"rush_review", "rush_lint", "rush_format", "rush_test", "rush_security"}

def test_each_tool_has_under_200_char_description():
    server = build_server()
    tools = asyncio.run(server.get_tools())
    for name, tool in tools.items():
        assert len(tool.description) < 200, f"{name} description too long: {len(tool.description)}"
```

(Note: `get_tools()` is the FastMCP-internal accessor. If 1.28.x doesn't expose it, we'll iterate the `tool_manager._tools` dict and document the dependency.)

---

## 12. Acceptance gate (per requirements §5)

Architecture pre-conditions checked before Phase 3 starts:

- [x] `pyproject.toml` deps list — `mcp>=1.28,<2`, `click>=8,<9`, `rich>=13,<14` (verified against actual installed versions)
- [x] Package layout locked (this file §2)
- [x] ToolResult TypedDict locked (§3)
- [x] Engine ABC + registry locked (§4)
- [x] FastMCP registration pattern locked (§5)
- [x] Logging contract locked (NDJSON to stderr, C5) (§7)
- [x] rush.toml schema + walk-up discovery locked (§8)
- [x] Theme constants locked (C8) (§9)
- [x] Heuristics list for `review` locked (§10)
- [x] Test categories + fixtures locked (§11)

**Phase 2 is complete.** Phase 3 (Skeleton & Tooling) can begin.

---

## 13. Open questions — RESOLVED in Phase 2

(Re-confirming the answers from requirements §6.)

| # | Question | Resolution |
|---|---|---|
| Q1 | Engine version capture | Cache after first `engine.version()` call; key on engine name |
| Q2 | Concurrent engine execution | **Sequential everywhere.** Determinism beats wall-clock speed for v0.1. The 5 tools each invoke 1–2 engines; the parallelism savings are negligible. |
| Q3 | MCP description length | **<200 chars per tool.** Template at §5.2 |
| Q4 | `--llm` prompt content | **Heuristic findings JSON becomes the prompt context.** No free-form asking. Template at §10.1. |
| Q5 | Path handling | **`pathlib.Path` only. No `os.path.join` anywhere.** Verify with a `grep -r "os.path.join" src/` in CI. |
| Q6 | `rush.toml` schema validation | **`tomllib` (stdlib 3.11+) + hand-rolled validators.** No pydantic in v0.1. |

---

## 14. What's explicitly NOT in this architecture

(Per requirements §4 — non-goals reinforced.)

- No HTTP/SSE MCP transport (C2)
- No plugin/extension system
- No `pyproject.toml`-driven tool auto-discovery (engines are hardcoded in `engines/__init__.py`)
- No remote telemetry, no analytics, no update checks
- No `--claim-reviewed` flag — out of scope, deferred to v0.2
- No Graft integration code — integration is at the agent level (MCP-to-MCP), not in rush's code
- No AI-slop detection as a separate tool
- No secrets/IaC/Dockerfile/Markdown/Actions/YAML/SQL/Dead/Coverage/Mutation/E2E/Typecheck/Complexity engines
- No languages beyond Python + JS/TS

If Phase 3 implementation finds any of these creeping in, stop and surface it.

---

## 15. v0.2 architecture overlay

v0.2 supersedes the fixed-five-tool assumptions above without changing the
stdio-only MCP or canonical-result constraints. `catalog.py` is the declarative
source for every ToolSpec and EngineSpec; `ALL_TOOLS` must have exactly one
matching ToolSpec. Path-only tools are registered by the Click factory and by
the existing MCP registry loop, while commands with safety-specific flags keep
dedicated typed handlers.

`tools/routing.py` owns deterministic source collection, status precedence,
and multi-engine aggregation. Tool modules select compatible engines and call
only `tools/common.py:run_engine()`. Engine adapters own argv formation and
native-report parsing; they never print and they never call a subprocess outside
the common gateway.

The optional ToolResult fields `metrics`, `artifacts`, and `metadata` carry
v0.2-specific data without changing the v0.1 minimum. Missing executables,
disabled slow operations, and unsupported project types remain structured
`skipped` results. Browser, fuzzing, network, publishing, and baseline-writing
operations require explicit opt-in and are rejected by default.

The full capability matrix and support levels live in `requirements.md` §9 and
`docs/V0_2_SCOPE.md`; deferred cloud/credentialed capabilities do not enter the
default runtime dependency set.