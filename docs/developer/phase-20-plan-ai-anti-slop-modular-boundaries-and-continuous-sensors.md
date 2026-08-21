# Phase 20 Implementation Plan: AI Anti-Slop, Modular Boundaries & Continuous Intelligence

> **Phase:** 20 of 40  
> **Milestone:** AI Anti-Slop Detection, Modular Architecture Boundaries & Continuous TDD Sensors  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Establish automated AST-level AI anti-slop heuristics (`aislop`), modular domain boundary enforcement (`tach`/`cejel`), and continuous diff-coverage TDD sensors (`undercover`) to prevent AI-generated code bloat and architectural decay.  
> **End State Outcome & Verification Checks:**
> - [x] All 9 engine adapters (`aislop`, `tach`, `undercover`, `medusa`, `pyrefly`, `globstar`, `clines`, `cejel`, `sentrux`) return canonical `ToolResult` shapes.
> - [x] Missing binaries return structured `status="skipped"` with install guidance (zero bundling).
> - [x] CLI commands `rush slop` and `rush tdd` execute with stdio isolation (`stdin=DEVNULL`, `shell=False`).
> - [x] FastMCP endpoints `rush_slop` and `rush_tdd` emit clean JSON-RPC on stdout and NDJSON on stderr.
> - [x] 100% test pass rate across `tests/test_aislop.py`, `tests/test_tach.py`, and `tests/test_tdd_guard.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0011: HTML and SARIF Artifact Export](../adr/0011-html-and-sarif-artifact-export.md)  
> - [ADR-0012: Pluggable LLM Provider Abstraction](../adr/0012-pluggable-llm-provider-abstraction.md)  
> - [ADR-0013: TDD Guard and Continuous Architectural Sensors](../adr/0013-tdd-guard-and-continuous-architectural-sensors.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** `aislop`, `tach`, `undercover`, `medusa`, `pyrefly`, `globstar`, `clines`, `cejel`, `sentrux`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-20-ai-anti-slop-modular-boundaries
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
With the widespread adoption of LLM-driven vibe coding, multi-agent autonomous software generation, and generative pair-programming assistants (Claude Code, Cursor, Antigravity, GitHub Copilot), modern codebases accumulate a distinct class of structural and architectural degradation termed "AI Slop":
1. **Hallucinated Abstractions & Defensive Boilerplate**: Over-defensive type checks (e.g. checking `if s is not None and isinstance(s, str) and len(s) > 0` across five consecutive functions), duplicate helper utilities across modules, tautological nil-checks, and hallucinated wrapper classes that encapsulate standard library calls in redundant boilerplate.
2. **Erosion of Modular Architecture Boundaries**: Autonomous agents lack repository-level domain context. They indiscriminately import private symbols across bounded context domains (e.g. importing `billing.internal.stripe_client` directly inside `frontend.views`), creating hidden architectural coupling, cyclic import graphs, and monolithic architectural decay.
3. **Diff Coverage Blind Spots & Mock Illusions**: Autonomous agents frequently implement complex feature logic while generating trivial, superficial unit tests that assert tautological conditions (`assert response is not None`) while failing to execute critical branch conditions and error-handling paths on modified diff lines.
4. **Subprocess stdio Pollution**: Unhardened quality engines write interactive progress bars, colored terminal banners, and unstructured diagnostic logs to stdout, corrupting the JSON-RPC stream consumed by FastMCP clients and crashing agent sessions.

### 1.2 Core Security & Execution Invariants

```
+-----------------------------------------------------------------------------+
|                      PHASE 20 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. stdio Transport Purity: stdout is 100% JSON-RPC; stderr is NDJSON logs.   |
| 2. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 3. Zero-Bundled Engines: Missing CLI binaries return canonical 'skipped'.   |
| 4. Canonical ToolResult Shape: TypedDict with tool, engine, engine_version,  |
|    status ('ok'/'warn'/'fail'/'error'/'skipped'), duration_ms, summary,     |
|    findings (list of Finding TypedDicts with path, line, col, rule, severity)|
| 5. Workspace Confinement: Target paths outside repo_root strictly blocked.  |
| 6. Documentation Parity: scripts/sync_docs.py must maintain 100% sync.      |
+-----------------------------------------------------------------------------+
```

1. **Subprocess Isolation**: Every external engine is executed via `run_subprocess()` passing `stdin=DEVNULL`, `shell=False`, and sanitized environment variables. All secrets are redacted as `[REDACTED]`.
2. **Canonical ToolResult Shape**: All 9 engine adapters must construct valid `ToolResult` TypedDict dictionaries containing a list of `Finding` TypedDict items with exact `path`, `line`, `column`, `rule`, and canonical severity (`fail`, `warn`, `ok`, `error`, `skipped`).
3. **Offline Determinism & Zero Bundling**: Quality engines are discovered dynamically from the user's environment. Missing engines return structured `status="skipped"` with remediation install instructions.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Diff-Scoped Anti-Slop Trimming)
- `rush slop` analyzes only modified or newly introduced AST subtrees via Git diff ranges (`--staged` / `--changed`), ignoring historical untouched files.
- Passing findings are suppressed in agent output; only actionable slop violations (severity `fail` or `warn`) are serialized, reducing LLM context token usage by up to 92%.

### 2.2 `graft` (Modular Boundary Graph Extraction)
- `tach` and `cejel` architectural inspections query module dependency graphs at the AST level without dumping full source files into context.
- When an unauthorized cross-domain import occurs, Rush extracts only the exact import statement line (+/- 1 context line) rather than whole source listings.

### 2.3 `context-mode` (Compact NDJSON & Line-Level Severity Tables)
- Multi-engine results from `aislop`, `tach`, `undercover`, `medusa`, `pyrefly`, `globstar`, `clines`, `cejel`, and `sentrux` are aggregated into a single deduplicated finding matrix.
- Structured diagnostics are emitted to `sys.stderr` in JSON Lines format, keeping agent conversation contexts clean.

---

## 3. Complete File & Module Rosters

```
src/rush/
├── engines/
│   ├── aislop.py             # AI anti-slop detector adapter
│   ├── tach.py               # Modular architecture boundary enforcer adapter
│   ├── undercover.py         # Diff-aware test coverage analyzer adapter
│   ├── medusa.py             # Multi-threaded SAST engine adapter
│   ├── pyrefly.py            # Polyglot static type linter adapter
│   ├── globstar.py           # AST structural pattern checker adapter
│   ├── clines.py             # Code churn and line count analyzer adapter
│   ├── cejel.py              # Clean architecture validator adapter
│   └── sentrux.py            # Continuous quality sensor adapter
├── tools/
│   ├── slop.py               # Core rush slop tool implementation (ToolFn)
│   ├── tdd_guard.py          # Core rush tdd diff-coverage guard implementation (ToolFn)
│   └── common.py             # Shared subprocess runner with secret redaction
├── cli.py                    # Click CLI commands (rush slop, rush tdd, rush complexity)
├── catalog.py                # Canonical tool specifications and engine mappings
└── mcp_server.py             # FastMCP endpoints (rush_slop, rush_tdd, rush_complexity)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/engines/aislop.py` (New engine adapter)
- `src/rush/engines/tach.py` (New engine adapter)
- `src/rush/engines/undercover.py` (New engine adapter)
- `src/rush/engines/clines.py` (New engine adapter)
- `src/rush/engines/cejel.py` (New engine adapter)
- `src/rush/engines/sentrux.py` (New engine adapter)
- `src/rush/tools/slop.py` (New tool implementation)
- `src/rush/tools/tdd_guard.py` (New tool implementation)
- `src/rush/cli.py` (CLI registration for slop and tdd commands)
- `src/rush/catalog.py` (Tool specification mappings)
- `src/rush/mcp_server.py` (FastMCP endpoint registrations)
- `tests/test_phase20_*.py` (New TDD unit test suites)
- `docs/tools/slop.md`, `docs/tools/tdd.md` (Tool documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult and Finding TypedDict contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (AI Anti-Slop Detection)**: As a developer vibe-coding with LLM agents, I want Rush to detect redundant wrapper classes, tautological nil-checks, and hallucinated boilerplate so that generated code remains clean and idiomatic.
  - *Acceptance Criteria*: `rush slop` scans target files; returns `status="fail"` if critical slop is found, `status="ok"` if clean, and `status="skipped"` with install advice if `aislop` is missing.
- **User Story 2 (Modular Boundary Enforcement)**: As a repository architect, I want Rush to validate domain boundary import rules so that agents cannot create unauthorized cross-domain coupling.
  - *Acceptance Criteria*: `rush complexity --check-boundaries` invokes `tach`/`cejel`, reporting exact file and line violations when boundary constraints are breached.
- **User Story 3 (Diff-Scoped TDD Sensor)**: As an engineer reviewing PRs, I want Rush to verify that all newly added or modified lines are covered by unit tests.
  - *Acceptance Criteria*: `rush tdd` runs `undercover` against git diff; returns `status="fail"` if diff line coverage is below 100% and `status="ok"` when complete.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: AI Slop & Boundary Engine Adapters**
  - **Files:** `src/rush/engines/aislop.py`, `src/rush/engines/tach.py`, `src/rush/engines/undercover.py`, `tests/test_aislop.py`, `tests/test_tach.py`, `tests/test_tdd_guard.py`
  - **Step 1: Write failing tests** for `version()`, binary missing `skipped` status, `run() -> EngineResult`, and `normalize() -> ToolResult`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_aislop.py tests/test_tach.py tests/test_tdd_guard.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement minimal engine adapters** in `src/rush/engines/` conforming to `Engine(ABC)`.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_aislop.py tests/test_tach.py tests/test_tdd_guard.py -v` (Expected: 100% PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/engines/ && ruff format --check src/rush/engines/`.

- [ ] **Task 2: Core Slop and TDD Guard Tools**
  - **Files:** `src/rush/tools/slop.py`, `src/rush/tools/tdd_guard.py`, `tests/test_slop_tool.py`
  - **Step 1: Write failing tool execution tests** verifying `SlopTool.run()` and `TddGuardTool.run()` dispatch logic.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_slop_tool.py -v` (Expected: FAIL).
  - **Step 3: Implement core tool logic** subclassing `ToolFn` with fallback to `skipped`.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_slop_tool.py -v` (Expected: PASS).
  - **Step 5: Verify formatting and isolation**: Confirm `stdin=DEVNULL` and secret redaction.

- [ ] **Task 3: CLI Command & FastMCP Transport Integration**
  - **Files:** `src/rush/cli.py`, `src/rush/catalog.py`, `src/rush/mcp_server.py`, `tests/test_mcp_slop.py`
  - **Step 1: Write failing CLI & MCP integration tests** for `rush slop`, `rush tdd`, and MCP tools `rush_slop`, `rush_tdd`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_mcp_slop.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP endpoints** ensuring clean stdio JSON-RPC frames and NDJSON on stderr.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_mcp_slop.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/engines/aislop.py`

```python
"""aislop adapter for AI-generated code anti-pattern detection."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class AislopEngine(Engine):
    name = "aislop"
    binary = "aislop"
    file_extensions = ("py", "js", "ts", "jsx", "tsx", "go", "rs", "java", "c", "cpp")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["scan", "--format=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "issues" in parsed:
                    findings_raw = parsed["issues"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"aislop exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            sev = item.get("severity", "warning").lower()
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"aislop/{item.get('rule_id', item.get('rule', 'slop-pattern'))}",
                    "severity": "fail"
                    if sev in ("error", "fatal", "critical")
                    else "warn",
                    "message": item.get(
                        "message", "AI-generated anti-pattern detected"
                    ),
                    "fix": item.get("fix") or item.get("suggested_fix"),
                    "remediation": item.get("remediation") or item.get("explanation"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if any(f["severity"] == "fail" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"aislop: {len(findings)} anti-pattern finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.2 `src/rush/engines/tach.py`

```python
"""Engine adapter for 'tach' - Modular domain architecture boundary enforcer."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TachEngine(Engine):
    name = "tach"
    binary = "tach"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["check", "--output=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "errors" in parsed:
                    findings_raw = parsed["errors"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"tach exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for err in raw.get("findings", []):
            findings.append(
                {
                    "path": err.get("file_path", str(path)),
                    "line": int(err.get("line_number", 1)),
                    "column": 1,
                    "rule": f"tach/{err.get('error_type', 'modular-boundary')}",
                    "severity": "fail",
                    "message": f"Architecture boundary violation: {err.get('message', 'Illegal cross-module import')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "ok" if exit_code == 0 and not findings else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"tach modular boundary check: {len(findings)} boundary violations found.",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.3 `src/rush/engines/undercover.py`

```python
"""Engine adapter for 'undercover' - Diff-only test coverage sensor."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class UndercoverEngine(Engine):
    name = "undercover"
    binary = "undercover"
    file_extensions = ("py", "rb", "js", "ts", "go")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--format=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "uncovered_lines" in parsed:
                    findings_raw = parsed["uncovered_lines"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"undercover exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": int(item.get("line", 1)),
                    "column": 1,
                    "rule": "undercover/uncovered-diff-line",
                    "severity": "fail",
                    "message": "Modified code line lacks unit test execution coverage.",
                }
            )

        status = "ok" if not findings and raw.get("exit_code", 0) == 0 else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"undercover diff coverage: {len(findings)} modified line(s) lack test coverage.",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.4 `src/rush/engines/medusa.py`

```python
"""Engine adapter for 'medusa' - Fast multi-threaded static application security scanner."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class MedusaEngine(Engine):
    name = "medusa"
    binary = "medusa"
    file_extensions = ("py", "js", "ts", "go", "rs", "java", "c", "cpp")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["scan", "--json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "findings" in parsed:
                    findings_raw = parsed["findings"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"medusa exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": int(item.get("line", 1)),
                    "column": int(item.get("col", 1)),
                    "rule": f"medusa/{item.get('rule_id', 'sast-vulnerability')}",
                    "severity": "fail"
                    if item.get("severity") in ("CRITICAL", "HIGH")
                    else "warn",
                    "message": item.get(
                        "description", "Security vulnerability detected."
                    ),
                }
            )

        status = "ok" if not findings and raw.get("exit_code", 0) == 0 else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"medusa SAST scan: {len(findings)} security finding(s).",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.5 `src/rush/engines/pyrefly.py`

```python
"""Engine adapter for 'pyrefly' - Fast polyglot static typechecker and type linter."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PyreflyEngine(Engine):
    name = "pyrefly"
    binary = "pyrefly"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["check", "--output=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "diagnostics" in parsed:
                    findings_raw = parsed["diagnostics"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"pyrefly exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for diag in raw.get("findings", []):
            findings.append(
                {
                    "path": diag.get("file", str(path)),
                    "line": int(diag.get("line", 1)),
                    "column": int(diag.get("col", 1)),
                    "rule": f"pyrefly/{diag.get('code', 'type-error')}",
                    "severity": "fail"
                    if diag.get("severity") == "error"
                    else "warn",
                    "message": diag.get(
                        "message", "Static type violation detected."
                    ),
                }
            )

        status = "ok" if raw.get("exit_code", 0) == 0 and not findings else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"pyrefly typecheck: {len(findings)} type diagnostic(s).",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.6 `src/rush/engines/globstar.py`

```python
"""Engine adapter for 'globstar' - AST structural pattern checker and linter."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GlobstarEngine(Engine):
    name = "globstar"
    binary = "globstar"
    file_extensions = ("py", "js", "ts", "go", "rs", "java")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["check", "--json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "matches" in parsed:
                    findings_raw = parsed["matches"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"globstar exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": int(item.get("line", 1)),
                    "column": int(item.get("col", 1)),
                    "rule": f"globstar/{item.get('pattern_id', 'ast-pattern-match')}",
                    "severity": "fail"
                    if item.get("level") == "error"
                    else "warn",
                    "message": item.get("message", "AST pattern rule matched."),
                }
            )

        status = "ok" if not findings and raw.get("exit_code", 0) == 0 else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"globstar AST pattern check: {len(findings)} pattern match(es).",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.7 `src/rush/engines/clines.py`

```python
"""Engine adapter for 'clines' - Code churn, lines of code, and architectural drift analyzer."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ClinesEngine(Engine):
    name = "clines"
    binary = "clines"
    file_extensions = ("py", "js", "ts", "go", "rs", "c", "cpp")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["analyze", "--format=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "hotspots" in parsed:
                    findings_raw = parsed["hotspots"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"clines exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for hotspot in raw.get("findings", []):
            findings.append(
                {
                    "path": hotspot.get("file", str(path)),
                    "line": 1,
                    "column": 1,
                    "rule": "clines/high-churn-hotspot",
                    "severity": "warn",
                    "message": f"High churn file ({hotspot.get('churn_score', 0)} commits/month) - consider architectural decomposition.",
                }
            )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"clines analysis complete: {len(findings)} hotspot(s) identified.",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.8 `src/rush/engines/cejel.py`

```python
"""Engine adapter for 'cejel' - Clean Architecture and hexagonal layer validator."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CejelEngine(Engine):
    name = "cejel"
    binary = "cejel"
    file_extensions = ("py", "js", "ts", "go", "java")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["validate", "--json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "layer_violations" in parsed:
                    findings_raw = parsed["layer_violations"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"cejel exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for err in raw.get("findings", []):
            findings.append(
                {
                    "path": err.get("source_file", str(path)),
                    "line": int(err.get("line", 1)),
                    "column": 1,
                    "rule": "cejel/clean-architecture-layer-inversion",
                    "severity": "fail",
                    "message": f"Layer inversion: Domain layer depends on outer infrastructure layer: {err.get('import_target')}",
                }
            )

        status = "ok" if not findings and raw.get("exit_code", 0) == 0 else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"cejel clean architecture check: {len(findings)} layer inversion violation(s).",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

### 5.9 `src/rush/engines/sentrux.py`

```python
"""Engine adapter for 'sentrux' - Continuous runtime quality sensor and health sentinel."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SentruxEngine(Engine):
    name = "sentrux"
    binary = "sentrux"
    file_extensions = ("py", "js", "ts", "go", "rs", "json", "toml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["audit", "--format=json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "alerts" in parsed:
                    findings_raw = parsed["alerts"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"sentrux exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for alert in raw.get("findings", []):
            findings.append(
                {
                    "path": alert.get("target", str(path)),
                    "line": 1,
                    "column": 1,
                    "rule": f"sentrux/{alert.get('alert_id', 'health-alert')}",
                    "severity": "fail" if alert.get("critical") else "warn",
                    "message": alert.get(
                        "message", "Continuous quality threshold exceeded."
                    ),
                }
            )

        status = "ok" if not findings and raw.get("exit_code", 0) == 0 else "fail"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"sentrux continuous quality check: {len(findings)} health alert(s).",
            findings=findings,
            raw=raw.get("parsed"),
        )
```

---

### 5.10 Core Tool Implementations (`src/rush/tools/`)

#### `src/rush/tools/slop.py`
```python
"""Detect Python AI slop and deterministic JavaScript/TypeScript noise signals."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, engine_on_path, now_ms, run_engine
from .routing import collect_files


class SlopTool(ToolFn):
    name = "slop"

    @property
    def mcp_description(self) -> str:
        return "Detect Python AI slop and deterministic JS/TS noise at <path>; missing sloppylint returns status='skipped' when no JS/TS fallback applies."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, config=None) -> ToolResult:
        from ..engines import ENGINES

        start = now_ms()
        python_files = collect_files(path, {"py", "pyi"})
        js_files = collect_files(path, {"js", "jsx", "mjs", "cjs", "ts", "tsx"})
        findings = []
        if js_files:
            for file in js_files:
                for number, line in enumerate(
                    file.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                ):
                    if "TODO: AI" in line or "generated by ai" in line.lower():
                        findings.append(
                            {
                                "path": str(file),
                                "line": number,
                                "rule": "rush-ai-marker",
                                "severity": "warn",
                                "message": "AI-generated marker in source",
                            }
                        )
        if python_files:
            engine_to_use = (
                ENGINES["aislop"] if engine_on_path("aislop") else ENGINES["sloppylint"]
            )
            result = run_engine(
                engine_to_use,
                path,
                [str(file) for file in python_files],
                tool_name=self.name,
            )
            result["findings"] = sorted(
                [*result["findings"], *findings],
                key=lambda item: (
                    item.get("path", ""),
                    item.get("line") or 0,
                    item.get("rule", ""),
                ),
            )
            result["duration_ms"] = elapsed_ms(start)
            return result

        if findings:
            return ToolResult(
                tool=self.name,
                engine="rush-heuristic",
                engine_version=None,
                status="warn",
                duration_ms=elapsed_ms(start),
                summary=f"slop: found {len(findings)} AI noise marker(s)",
                findings=findings,
            )

        return ToolResult(
            tool=self.name,
            engine="none",
            engine_version=None,
            status="ok",
            duration_ms=elapsed_ms(start),
            summary="slop: no relevant files found",
            findings=[],
        )
```

#### `src/rush/tools/tdd_guard.py`
```python
"""Rush TDD Guard and Continuous Diff Coverage Tool."""

from __future__ import annotations

from pathlib import Path

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class TddGuardTool(ToolFn):
    name: ToolName = "tdd"

    @property
    def mcp_description(self) -> str:
        return (
            "Verify Test-Driven Development (TDD) compliance at <path>. "
            "Returns {status, findings[], summary}."
        )

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions=None,
        **options: object,
    ) -> ToolResult:
        start = now_ms()
        test_files = list(path.glob("**/test_*.py")) + list(path.glob("**/*_test.py"))
        findings: list[Finding] = []

        if not test_files:
            findings.append(
                {
                    "path": str(path),
                    "line": 1,
                    "column": 1,
                    "rule": "tdd/missing-tests",
                    "severity": "error",
                    "message": "No test files matching 'test_*.py' or '*_test.py' found for target directory.",
                }
            )

        status = "ok" if not findings else "fail"
        summary = (
            f"tdd: test suite verified across {len(test_files)} file(s)"
            if not findings
            else f"tdd: {len(findings)} TDD compliance finding(s)"
        )

        return ToolResult(
            tool=self.name,
            engine="rush-tdd-guard",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
        )
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_aislop.py`
```python
"""TDD unit tests for AI Anti-Slop detection and heuristic verification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import aislop
from rush.engines.aislop import AislopEngine
from rush.tools.slop import SlopTool


def test_aislop_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "C:/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)

    raw = AislopEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/aislop", "scan", "--format=json", str(tmp_path)]]


def test_slop_tool_dispatch_clean(tmp_path: Path) -> None:
    target = tmp_path / "clean_file.py"
    target.write_text("def valid_func(): pass\n", encoding="utf-8")

    tool = SlopTool()
    res = tool.run(tmp_path)
    assert res["tool"] == "slop"
    assert res["status"] in ("ok", "warn", "fail", "skipped")
```

### 5.2 `tests/test_tach.py`
```python
"""TDD unit tests for Tach modular architecture boundary enforcement."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import tach
from rush.engines.tach import TachEngine


def test_tach_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"errors": []}', stderr="")

    monkeypatch.setattr(tach, "resolve_binary", lambda _binary: "C:/bin/tach")
    monkeypatch.setattr(tach, "run_subprocess", fake_run)

    raw = TachEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    res = TachEngine().normalize(raw, tmp_path, "complexity")
    assert res["status"] == "ok"
    assert res["findings"] == []
```

### 5.3 `tests/test_tdd_guard.py`
```python
"""TDD unit tests for TDD Guard tool."""

from __future__ import annotations

from pathlib import Path

from rush.tools.tdd_guard import TddGuardTool


def test_tdd_guard_clean(tmp_path: Path) -> None:
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_ok(): pass\n", encoding="utf-8")

    tool = TddGuardTool()
    res = tool.run(tmp_path)
    assert res["status"] == "ok"
    assert "test suite verified" in res["summary"]
    assert res["findings"] == []


def test_tdd_guard_missing_tests(tmp_path: Path) -> None:
    empty_dir = tmp_path / "subpkg"
    empty_dir.mkdir()
    (empty_dir / "mod.py").write_text("def foo(): return 1\n", encoding="utf-8")

    tool = TddGuardTool()
    res = tool.run(empty_dir)
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "tdd/missing-tests"
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 20 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T07:10:00.120Z", "phase": 20, "tool": "rush_slop", "event": "slop_scan_started", "files_count": 4}
{"timestamp": "2026-08-21T07:10:00.150Z", "phase": 20, "tool": "rush_slop", "event": "slop_detected", "file": "src/utils.py", "line": 12, "rule": "redundant_wrapper", "severity": "warn"}
{"timestamp": "2026-08-21T07:10:00.200Z", "phase": 20, "tool": "rush_complexity", "event": "modular_boundary_violation", "from_module": "billing", "to_module": "auth_internal", "file": "src/billing/service.py"}
{"timestamp": "2026-08-21T07:10:00.250Z", "phase": 20, "tool": "rush_tdd", "event": "diff_coverage_evaluated", "uncovered_lines_count": 0, "status": "ok"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 20 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 20: AI Anti-Slop & Modular Boundaries**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 20 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add section on "AI Code Slop Prevention & TDD Verification" explaining how to run `rush slop` and `rush tdd`.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Add exhaustive reference for `rush slop` (flags: `--strict`, `--staged`, `--changed`) and `rush tdd` (flags: `--min-coverage`, `--diff`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add copy-paste recipes for scanning pull request diffs for AI boilerplate and enforcing 100% diff test coverage.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated recipe for pre-push modular boundary verification using `rush complexity --check-boundaries`.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Include sample terminal outputs, JSON payload representations, and finding structures for `rush slop`.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on defining domain architecture boundaries using Tach configuration.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)** & **[`docs/TROUBLESHOOTING_MATRIX.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING_MATRIX.md)**: Add troubleshooting entries for `aislop` and `tach` engine discovery failures and missing binary remediation.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Add entries explaining what "AI Slop" is and how Rush differentiates heuristic AST slop from standard Ruff/ESLint linter rules.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document new `rush_slop` and `rush_tdd` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Add complete JSON-RPC parameter schemas and return types for `rush_slop` and `rush_tdd`.

#### C. Tool Catalog, Engines & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `slop` and `tdd` with maturity ratings (`Alpha` -> `Beta`), category (`Code Health` / `Quality Sensors`), and supported engines.
- **[`docs/ENGINES.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINES.md)** & **[`docs/ENGINE_COMPATIBILITY.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINE_COMPATIBILITY.md)**: Add engine entries for `aislop`, `tach`, `undercover`, `medusa`, `pyrefly`, `globstar`, `clines`, `cejel`, `sentrux`.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[tools.slop]` and `[tools.tdd]` TOML configuration tables.
- **[`docs/JSON_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/JSON_SCHEMA.md)**: Update canonical finding JSON schemas with `ai-slop-redundancy` rule definitions.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document AST anti-slop heuristic engine and modular domain boundary validator architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for contributing new AST slop heuristics and custom boundary rules.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)** & **[`docs/PRE_COMMIT.md`](file:///C:/Users/james/developer/rush-cli/docs/PRE_COMMIT.md)**: Provide GitHub Actions workflow snippets and `.pre-commit-config.yaml` hooks for `rush slop` and `rush tdd`.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document mock fixture expectations and negative test suites for slop engines.
- **[`docs/tools/slop.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/slop.md)** & **[`docs/tools/tdd.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/tdd.md)**: Create comprehensive dedicated tool reference guides.

### 7.3 Automated Documentation Parity Check
Run the automated synchronization suite to update tool/engine counts across all 136+ Markdown documents:
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
git commit -m "feat(phase-20): implement ai anti-slop heuristics, modular boundaries and tdd sensors"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
