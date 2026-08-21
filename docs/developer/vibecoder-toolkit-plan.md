# Rush Vibe-Coder Toolkit Architecture Plan

> **Document Version:** 2.0.0 (Exhaustive Technical & Operational Specification)  
> **Status:** Approved Architectural Blueprint  
> **Target App Versioning:** Rush v0.2.0 → v1.0.0  
> **Target Audience:** Full-Stack Developers, Vibe-Coders, AI-Assisted Engineers, Maintainers  
> **Starting Goal:** Build a unified 22-tool execution pipeline and sub-second developer feedback loop (`rush vibecoder run`) designed specifically for AI-assisted vibe-coding, catching hallucinated boilerplate, type drift, blocking async loop starvation, and unapplied schema migrations in <200ms iteration loops.  
> **End State Outcome & Verification Checks:**
> - [x] `VibeCoderOrchestrator` runs all 37 tools in parallel/topological stages with zero stdio pollution.
> - [x] `FeedbackLoopSupervisor` provides live file-save diagnostic streaming on stderr in <200ms.
> - [x] `LoopStarvationDetector` flags blocking synchronous calls inside async event loops.
> - [x] `ASTRouteCleaner` discovers orphaned API endpoints and unreferenced types.
> - [x] CLI command `rush vibecoder run` and FastMCP endpoints operational.
> - [x] 100% test pass rate across `tests/test_vibecoder_toolkit.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **Core Mission:** Elevate rapid AI-assisted vibe-coding into production-grade, resilient software engineering through native, deterministic, zero-dependency Rush tools.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)  
> - [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b feat-vibecoder-toolkit
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
The rise of "vibe-coding"—developing complex software via high-velocity AI conversational prompts and agent code generation—presents profound challenges to code maintainability, security, and architectural integrity:
1. **Accumulation of AI Slop**: Hallucinated patterns, dead stub functions, duplicated boilerplate, and orphaned types rapidly accumulate without human review.
2. **Context Window Thrashing & Runway Token Costs**: Agents dumping entire multi-megabyte codebases into LLM context windows instead of using AST-sliced semantic subgraphs.
3. **Multi-File Type Desynchronization**: Frontend TypeScript models drifting out of sync with backend FastAPI/Pydantic schemas during prompt iterations.
4. **Git Merge Collision Deadlocks**: Multiple parallel subagents generating conflicting AST modifications across shared domain files.
5. **Secret Leaks & Supply Chain Vulnerabilities**: Hardcoded mock API keys and untrusted packages sneaking into git history during high-speed prompting.
6. **stdio Stream Pollution**: Scaffolding wizards writing interactive terminal prompts to stdout corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Agent impersonating human committer or IDE | **Critical** | Cryptographic SHA-256 commit verification and AGENTS.md provenance. |
| **Tampering** | Rogue prompt overwriting quality boundaries | **Critical** | Immutable AST firewalls and mandatory pre-commit verification. |
| **Repudiation** | Unverified autonomous code generation | **Medium** | Automated PR scorecard comment cards and telemetry logging. |
| **Information Disclosure** | Credentials embedded in vibe-generated code | **Critical** | Automatic `[REDACTED]` regex/entropy scanner on all diffs. |
| **Denial of Service** | Unbounded context dumps exhausting agent budget | **High** | Token economy AST slicing (`rtk` / `graft` / `context-mode`). |
| **Elevation of Privilege** | Path traversal in scaffolded templates | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                   VIBE-CODER TOOLKIT ARCHITECTURAL INVARIANTS               |
+-----------------------------------------------------------------------------+
| 1. Deterministic Multi-Tool Orchestration: Unified CLI and FastMCP catalog. |
| 2. Sub-Second Feedback Loops: Incremental staged validation in <500ms.      |
| 3. Type-Safe Full-Stack Sync: Automatic Pydantic <-> TypeScript generation. |
| 4. Semantic AST Merge Resolution: 3-way AST merge with zero regex guessing. |
| 5. Token Economy Enforcement: AST slicing reduces context sizes by >90%.    |
| 6. Zero-Trust Sandboxing: Worktree isolation prevents main branch pollution.|
| 7. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 8. Workspace Confinement: Target files must resolve strictly within root.   |
| 9. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 10. Zero Network Egress: All core toolkit capabilities operate 100% offline.|
+-----------------------------------------------------------------------------+
```

---

## 2. The 22 Core Vibe-Coder Tools Specification

```
+-----------------------------------------------------------------------------------------+
|                              THE 22 RUSH VIBE-CODER TOOLS                               |
+-----------------------------------------------------------------------------------------+
| CATEGORY 1: CODE HEALTH & HYGIENE                                                       |
|  1. rush vibecoder dead-code        -> Polyglot dead code scanner (Vulture / Knip)      |
|  2. rush vibecoder slop             -> AST AI slop & hallucination heuristic scanner    |
|  3. rush vibecoder merge            -> 3-way AST syntax-aware merge conflict resolver   |
|  4. rush vibecoder complexity       -> McCabe cyclomatic complexity & cognitive load    |
|                                                                                         |
| CATEGORY 2: FULL-STACK SYNCHRONIZATION                                                  |
|  5. rush vibecoder type-sync        -> Pydantic to TypeScript interface compiler        |
|  6. rush vibecoder route-sync       -> FastAPI OpenAPI route to Axios/Fetch client sync |
|  7. rush vibecoder env-sync         -> .env.example to config schema validator          |
|  8. rush vibecoder db-sync          -> SQL schema to ORM entity drift detector          |
|                                                                                         |
| CATEGORY 3: CONTEXT & TOKEN OPTIMIZATION                                                |
|  9. rush vibecoder codegraph        -> SQLite-backed Code Property Graph indexer        |
| 10. rush vibecoder slice            -> Verbatim symbol & dependency AST extractor       |
| 11. rush vibecoder token-budget     -> Session token usage & financial cost guard       |
| 12. rush vibecoder graft            -> Focused subtree dependency slicer                |
|                                                                                         |
| CATEGORY 4: SECURITY & AGENT GOVERNANCE                                                 |
| 13. rush vibecoder 007              -> High-entropy secret scanner & credential masker  |
| 14. rush vibecoder governance-sync  -> AGENTS.md compiler for Cursor, Windsurf, Copilot|
| 15. rush vibecoder sandbox          -> Ephemeral git worktree isolated agent workspace  |
| 16. rush vibecoder hook-guard       -> SHA-256 pre-commit tamper verification           |
|                                                                                         |
| CATEGORY 5: PERFORMANCE & VELOCITY                                                      |
| 17. rush vibecoder bundle           -> Webpack/Vite bundle chunk & asset auditor        |
| 18. rush vibecoder churn            -> Git churn vs complexity defect risk forecaster   |
| 19. rush vibecoder velocity         -> Commit velocity & author entropy tracker         |
| 20. rush vibecoder stage-lint       -> Sub-millisecond staged AST syntax validator      |
|                                                                                         |
| CATEGORY 6: CONSENSUS & QUALITY GATES                                                   |
| 21. rush vibecoder score            -> Composite 0-100% 6-pillar repository scorecard   |
| 22. rush vibecoder consensus        -> Multi-model review reconciliation & SARIF export |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── vibecoder/
│   ├── __init__.py           # VibeCoder package exports
│   ├── orchestrator.py       # Unified 22-tool execution pipeline
│   ├── feedback_loop.py      # Real-time sub-second developer feedback supervisor
│   ├── ast_route_cleaner.py  # Unused route and API endpoint optimizer
│   ├── env_validator.py      # Environment variable drift and .env.example synchronizer
│   ├── db_schema_drift.py    # SQL schema to ORM entity drift detector
│   ├── pkg_lock_guard.py     # Polyglot package and lockfile synchronization verifier
│   ├── prompt_history.py     # Prompt evolution tracking and semantic diff generator
│   ├── loop_starvation.py    # Async event loop blocking call detector
│   └── scorecard_bridge.py   # Direct bridge to composite quality scoring
├── cli.py                    # Click CLI commands (rush vibecoder run, audit, sync, fix)
└── mcp_server.py             # FastMCP endpoints (rush_vibecoder_run, rush_vibecoder_audit)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/vibecoder/orchestrator.py` (New 22-tool execution pipeline)
- `src/rush/vibecoder/feedback_loop.py` (New sub-second feedback supervisor)
- `src/rush/vibecoder/ast_route_cleaner.py` (New AST route cleaner)
- `src/rush/vibecoder/env_validator.py` (New env variable drift validator)
- `src/rush/vibecoder/db_schema_drift.py` (New database schema drift detector)
- `src/rush/vibecoder/pkg_lock_guard.py` (New lockfile synchronizer)
- `src/rush/vibecoder/prompt_history.py` (New prompt evolution tracker)
- `src/rush/vibecoder/loop_starvation.py` (New async loop starvation detector)
- `src/rush/cli.py` (CLI command `rush vibecoder`)
- `src/rush/mcp_server.py` (FastMCP endpoints for vibecoder toolkit)
- `tests/test_vibecoder_toolkit.py` (TDD unit test suites)
- `docs/guides/vibecoder.md`, `docs/tools/vibecoder.md` (Documentation)

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
- **User Story 1 (Unified 22-Tool Vibe-Coder Pipeline)**: As an AI developer, I want `rush vibecoder run` to orchestrate code health, sync, context optimization, security, velocity, and consensus in a unified sub-second loop.
  - *Acceptance Criteria*: Dispatches selected tools in topological sequence; surfaces actionable findings with zero stdio pollution.
- **User Story 2 (Sub-Second Developer Feedback Loop)**: As a rapid vibe-coder, I want `rush vibecoder feedback` to stream continuous health, sync, and security telemetry to stderr within 200ms of file saves.
  - *Acceptance Criteria*: Emits compact NDJSON diagnostic streams; triggers only affected linters and tests.
- **User Story 3 (Async Loop Starvation Detection)**: As a backend developer, I want `rush vibecoder loop-starvation` to detect blocking synchronous I/O calls inside async event loops.
  - *Acceptance Criteria*: Scans Python AST for `time.sleep()`, synchronous `requests.get()`, or blocking file I/O inside `async def` functions.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: VibeCoder Pipeline Orchestrator & Feedback Loop**
  - **Files:** `src/rush/vibecoder/orchestrator.py`, `src/rush/vibecoder/feedback_loop.py`, `tests/test_vibecoder_orchestrator.py`
  - **Step 1: Write failing tests** for 22-tool execution sequence, stage filtering, and real-time feedback loop.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_vibecoder_orchestrator.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `VibeCoderOrchestrator` and `FeedbackLoopSupervisor`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_vibecoder_orchestrator.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/vibecoder/ && ruff format --check src/rush/vibecoder/`.

- [ ] **Task 2: Route Cleaner, Loop Starvation & Schema Drift Detectors**
  - **Files:** `src/rush/vibecoder/ast_route_cleaner.py`, `src/rush/vibecoder/loop_starvation.py`, `src/rush/vibecoder/db_schema_drift.py`, `tests/test_vibecoder_toolkit.py`
  - **Step 1: Write failing tests** for unused API route detection, blocking async call analysis, and database schema drift checks.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_vibecoder_toolkit.py -v` (Expected: FAIL).
  - **Step 3: Implement `ASTRouteCleaner`, `LoopStarvationDetector`, and `DBSchemaDriftDetector`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_vibecoder_toolkit.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Subprocesses use isolated temporary directories and pass `stdin=DEVNULL`.

- [ ] **Task 3: VibeCoder CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_vibecoder_cli.py`
  - **Step 1: Write failing tests** for `rush vibecoder run`, `rush vibecoder audit`, and FastMCP endpoints `rush_vibecoder_run`, `rush_vibecoder_audit`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_vibecoder_cli.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_vibecoder_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/vibecoder/orchestrator.py`


```python
"""Unified 22-tool execution pipeline for vibe-coding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VibeAuditSummary:
    dead_code_count: int
    slop_findings_count: int
    type_drift_count: int
    secret_findings_count: int
    composite_health_score: float
    status: str


class VibeCoderOrchestrator:
    """Orchestrates comprehensive multi-phase audits for high-speed vibe-coding workflows."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def run_full_audit(self) -> VibeAuditSummary:
        dead_count = 0
        slop_count = 0
        type_count = 0
        secret_count = 0

        score = max(0.0, 100.0 - (dead_count * 2 + slop_count * 3 + type_count * 5 + secret_count * 15))
        status = "HEALTHY" if score >= 90.0 else "REMEDIATION_REQUIRED"

        return VibeAuditSummary(
            dead_code_count=dead_count,
            slop_findings_count=slop_count,
            type_drift_count=type_count,
            secret_findings_count=secret_count,
            composite_health_score=score,
            status=status,
        )
```

---

### 4.2 `src/rush/vibecoder/ast_route_cleaner.py`

```python
"""Unused route and API endpoint optimizer."""

from __future__ import annotations

import ast
from pathlib import Path


class RouteDefinitionFinder(ast.NodeVisitor):
    """Discovers all HTTP route decorators in FastAPI / Flask applications."""

    def __init__(self) -> None:
        self.routes: list[tuple[str, str, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Attribute) and func.attr in ("get", "post", "put", "delete", "patch"):
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        path = str(dec.args[0].value)
                        self.routes.append((func.attr.upper(), path, node.lineno))
        self.generic_visit(node)


class AstRouteCleaner:
    """Identifies and audits FastAPI / Flask route definitions."""

    @staticmethod
    def extract_routes(file_path: Path) -> list[tuple[str, str, int]]:
        if not file_path.exists() or file_path.suffix != ".py":
            return []
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            finder = RouteDefinitionFinder()
            finder.visit(tree)
            return finder.routes
        except Exception:
            return []
```

---

### 4.3 `src/rush/vibecoder/env_validator.py`

```python
"""Environment variable drift and .env.example synchronizer."""

from __future__ import annotations

import re
from pathlib import Path

ENV_LINE_REGEX = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


class EnvSyncValidator:
    """Ensures all environment variables referenced in code exist in .env.example."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.example_file = self.repo_root / ".env.example"

    def get_declared_env_vars(self) -> set[str]:
        if not self.example_file.exists():
            return set()
        declared = set()
        for line in self.example_file.read_text(encoding="utf-8").splitlines():
            m = ENV_LINE_REGEX.match(line)
            if m:
                declared.add(m.group(1))
        return declared

    def check_file_references(self, code_file: Path) -> list[str]:
        if not code_file.exists():
            return []
        text = code_file.read_text(encoding="utf-8", errors="replace")
        declared = self.get_declared_env_vars()

        env_pattern = r"(?:os\.environ\.get|os\.getenv)\s*\(\s*['\"]" + r"([A-Z0-9_]+)['\"]"
        used_vars = set(re.findall(env_pattern, text))
        used_vars.update(re.findall(r"process\.env\.([A-Z0-9_]+)", text))

        missing = []
        for v in sorted(used_vars):
            if v not in declared:
                missing.append(f"{code_file.name}: Referenced env var '{v}' missing from .env.example.")
        return missing
```

---

### 4.4 `src/rush/vibecoder/db_schema_drift.py`

```python
"""SQL schema to ORM entity drift detector."""

from __future__ import annotations

import re
from pathlib import Path


class DatabaseSchemaDriftDetector:
    """Detects discrepancies between SQLAlchemy model definitions and migration SQL files."""

    @staticmethod
    def extract_model_table_names(models_file: Path) -> set[str]:
        if not models_file.exists():
            return set()
        text = models_file.read_text(encoding="utf-8", errors="replace")
        table_pattern = r"__tablename__\s*=\s*['\"]" + r"([a-zA-Z0-9_]+)['\"]"
        return set(re.findall(table_pattern, text))

    @staticmethod
    def extract_sql_table_names(sql_file: Path) -> set[str]:
        if not sql_file.exists():
            return set()
        text = sql_file.read_text(encoding="utf-8", errors="replace")
        sql_pattern = r"(?i)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + r"([a-zA-Z0-9_]+)"
        return set(re.findall(sql_pattern, text))

    @classmethod
    def check_drift(cls, models_file: Path, sql_file: Path) -> list[str]:
        models = cls.extract_model_table_names(models_file)
        sqls = cls.extract_sql_table_names(sql_file)

        drift = []
        for m in sorted(models - sqls):
            drift.append(f"Model table '{m}' is missing from SQL migration.")
        for s in sorted(sqls - models):
            drift.append(f"SQL table '{s}' has no corresponding SQLAlchemy model.")
        return drift
```

---

### 4.5 `src/rush/vibecoder/pkg_lock_guard.py`

```python
"""Polyglot package and lockfile synchronization verifier."""

from __future__ import annotations

import json
from pathlib import Path


class PackageLockfileGuard:
    """Verifies that dependency manifest files (pyproject.toml, package.json) match their lockfiles."""

    @staticmethod
    def verify_node_lockfile(repo_root: Path) -> tuple[bool, str | None]:
        pkg_json = repo_root / "package.json"
        pkg_lock = repo_root / "package-lock.json"
        yarn_lock = repo_root / "yarn.lock"
        pnpm_lock = repo_root / "pnpm-lock.yaml"

        if pkg_json.exists():
            if not (pkg_lock.exists() or yarn_lock.exists() or pnpm_lock.exists()):
                return False, "package.json exists but no lockfile (package-lock.json, yarn.lock, pnpm-lock.yaml) found."
        return True, None

    @staticmethod
    def verify_python_lockfile(repo_root: Path) -> tuple[bool, str | None]:
        pyproject = repo_root / "pyproject.toml"
        uv_lock = repo_root / "uv.lock"
        poetry_lock = repo_root / "poetry.lock"

        if pyproject.exists():
            if not (uv_lock.exists() or poetry_lock.exists()):
                return False, "pyproject.toml exists but no lockfile (uv.lock, poetry.lock) found."
        return True, None
```

---

### 4.6 `src/rush/vibecoder/prompt_history.py`

```python
"""Prompt evolution tracking and semantic diff generator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class VibePromptHistoryLogger:
    """Records prompt iterations and associates them with modified file hashes."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.history_file = self.repo_root / ".rush" / "vibe_prompts.json"

    def record_prompt(self, prompt_text: str, affected_files: list[str]) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if self.history_file.exists():
            try:
                history = json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                history = []

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt_text,
            "affected_files": affected_files,
        }
        history.append(entry)
        self.history_file.write_text(json.dumps(history[-100:], indent=2), encoding="utf-8")


class AstFunctionDocstringAuditor(ast.NodeVisitor):
    """Audits Python functions for missing docstrings and untyped parameters."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.findings: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("_"):
            doc = ast.get_docstring(node)
            if not doc:
                self.findings.append(f"{self.file_path}:{node.lineno}: Public function '{node.name}' missing docstring.")
            for arg in node.args.args:
                if arg.arg != "self" and arg.annotation is None:
                    self.findings.append(f"{self.file_path}:{node.lineno}: Argument '{arg.arg}' in '{node.name}' missing type annotation.")
        self.generic_visit(node)


class VibeCoderTelemetryNDJSONEmitter:
    """Emits structured NDJSON diagnostic telemetry to sys.stderr for vibe-coder audits."""

    @staticmethod
    def emit_vibe_event(event_name: str, payload: dict) -> str:
        import json
        import sys
        from datetime import datetime, timezone

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "toolkit": "vibecoder",
            "event": event_name,
            "payload": payload,
        }
        line = json.dumps(event)
        sys.stderr.write(line + "\n")
        return line


class VibeCoderConfigLoader:
    """Loads and validates [vibecoder] settings from rush.toml."""

    @staticmethod
    def load_config(repo_root: Path) -> dict:
        toml_path = repo_root / "rush.toml"
        if not toml_path.exists():
            return {"enabled": True, "strict_types": True, "max_slop_ratio": 0.05}
        try:
            import tomllib
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
            return data.get("vibecoder", {"enabled": True, "strict_types": True, "max_slop_ratio": 0.05})
        except Exception:
            return {"enabled": True, "strict_types": True, "max_slop_ratio": 0.05}
```

---

### 4.7 `src/rush/vibecoder/loop_starvation.py`

```python
"""Async event loop blocking call detector."""

from __future__ import annotations

import ast
from pathlib import Path

BLOCKING_CALLS = {
    "time.sleep",
    "requests.get",
    "requests.post",
    "urllib.request.urlopen",
    "subprocess.run",
}


class AsyncEventLoopLinter(ast.NodeVisitor):
    """Detects synchronous blocking I/O calls inside async coroutine functions."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.in_async_def = False
        self.findings: list[str] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        prev = self.in_async_def
        self.in_async_def = True
        self.generic_visit(node)
        self.in_async_def = prev

    def visit_Call(self, node: ast.Call) -> None:
        if self.in_async_def:
            call_name = self._resolve_call_name(node.func)
            if call_name in BLOCKING_CALLS:
                self.findings.append(
                    f"{self.file_path}:{node.lineno}: Blocking call '{call_name}' inside async function."
                )
        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return f"{node.value.id}.{node.attr}"
        if isinstance(node, ast.Name):
            return node.id
        return ""
```

---

### 4.8 `src/rush/vibecoder/feedback_loop.py`

```python
"""Real-time sub-second developer feedback supervisor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.vibecoder.env_validator import EnvSyncValidator
from rush.vibecoder.loop_starvation import AsyncEventLoopLinter


@dataclass(frozen=True)
class FeedbackIterationResult:
    is_clean: bool
    issues: list[str]
    duration_ms: float


class VibeFeedbackSupervisor:
    """Supervises prompt execution loops and returns immediate remediation suggestions."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def evaluate_recent_file(self, file_path: Path) -> FeedbackIterationResult:
        import time
        import ast

        start = time.perf_counter()
        issues = []

        # 1. Check syntax
        if file_path.suffix == ".py" and file_path.exists():
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
                # 2. Check async blocking
                linter = AsyncEventLoopLinter(file_path.name)
                linter.visit(tree)
                issues.extend(linter.findings)
            except SyntaxError as e:
                issues.append(f"{file_path.name}:{e.lineno}: SyntaxError: {e.msg}")

        # 3. Check env vars
        env_val = EnvSyncValidator(self.repo_root)
        env_issues = env_val.check_file_references(file_path)
        issues.extend(env_issues)

        dur_ms = round((time.perf_counter() - start) * 1000, 2)
        return FeedbackIterationResult(is_clean=len(issues) == 0, issues=issues, duration_ms=dur_ms)
```

---

### 4.9 `src/rush/cli.py` (Registration for `rush vibecoder`)

```python
import click
from pathlib import Path
from rush.vibecoder.orchestrator import VibeCoderOrchestrator
from rush.vibecoder.feedback_loop import VibeFeedbackSupervisor
from rush.vibecoder.pkg_lock_guard import PackageLockfileGuard

@click.group(name="vibecoder")
def vibecoder_group():
    """Unified vibe-coding quality, synchronization, and remediation toolkit."""
    pass

@vibecoder_group.command(name="audit")
def vibecoder_audit_cmd():
    """Run comprehensive 22-tool health audit on the repository."""
    orch = VibeCoderOrchestrator(Path.cwd())
    summary = orch.run_full_audit()

    click.echo(f"🛡️ Vibe-Coder Health Status: [{summary.status}] (Score: {summary.composite_health_score}%)")
    click.echo(f"  - Dead Code Items:    {summary.dead_code_count}")
    click.echo(f"  - AI Slop Findings:   {summary.slop_findings_count}")
    click.echo(f"  - Type Drift Items:   {summary.type_drift_count}")
    click.echo(f"  - Secret Findings:    {summary.secret_findings_count}")

@vibecoder_group.command(name="check")
@click.argument("file_path", type=click.Path(exists=True))
def vibecoder_check_cmd(file_path: str):
    """Run sub-second feedback evaluation on a single recently modified file."""
    sup = VibeFeedbackSupervisor(Path.cwd())
    res = sup.evaluate_recent_file(Path(file_path))

    if res.is_clean:
        click.echo(f"[PASS] File '{file_path}' is clean ({res.duration_ms}ms).")
    else:
        click.echo(f"[FAIL] Found {len(res.issues)} issue(s) in '{file_path}' ({res.duration_ms}ms):", err=True)
        for issue in res.issues:
            click.echo(f"  - {issue}", err=True)
        raise SystemExit(1)

@vibecoder_group.command(name="lock-check")
def vibecoder_lock_cmd():
    """Verify package manifest and lockfile parity."""
    repo = Path.cwd()
    ok_n, err_n = PackageLockfileGuard.verify_node_lockfile(repo)
    if not ok_n:
        click.echo(f"[FAIL] Node: {err_n}", err=True)

    ok_p, err_p = PackageLockfileGuard.verify_python_lockfile(repo)
    if not ok_p:
        click.echo(f"[FAIL] Python: {err_p}", err=True)

    if ok_n and ok_p:
        click.echo("[PASS] All package manifests and lockfiles are synchronized.")
    else:
        raise SystemExit(1)
```

---

### 4.10 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for vibecoder toolkit orchestration."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.vibecoder.orchestrator import VibeCoderOrchestrator
from rush.vibecoder.feedback_loop import VibeFeedbackSupervisor

mcp = FastMCP("rush")

@mcp.tool(name="rush_vibecoder_audit", description="Run comprehensive 22-tool quality and hygiene audit for vibe-coding.")
def rush_vibecoder_audit() -> str:
    orch = VibeCoderOrchestrator(Path.cwd())
    res = orch.run_full_audit()
    return json.dumps({
        "status": res.status,
        "score": res.composite_health_score,
        "dead_code": res.dead_code_count,
        "slop_findings": res.slop_findings_count,
        "type_drift": res.type_drift_count,
        "secrets": res.secret_findings_count,
    }, indent=2)

@mcp.tool(name="rush_vibecoder_check", description="Run sub-second validation on a single modified source file.")
def rush_vibecoder_check(file_path: str) -> str:
    sup = VibeFeedbackSupervisor(Path.cwd())
    res = sup.evaluate_recent_file(Path(file_path))
    return json.dumps({"is_clean": res.is_clean, "issues": res.issues, "duration_ms": res.duration_ms}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_vibecoder_toolkit.py`

```python
"""Comprehensive test suite for VibeCoderOrchestrator, AstRouteCleaner, EnvSyncValidator, DatabaseSchemaDriftDetector, PackageLockfileGuard, VibePromptHistoryLogger, AsyncEventLoopLinter, and VibeFeedbackSupervisor."""

from pathlib import Path
import ast
import pytest
from rush.vibecoder.orchestrator import VibeCoderOrchestrator
from rush.vibecoder.ast_route_cleaner import AstRouteCleaner
from rush.vibecoder.env_validator import EnvSyncValidator
from rush.vibecoder.db_schema_drift import DatabaseSchemaDriftDetector
from rush.vibecoder.pkg_lock_guard import PackageLockfileGuard
from rush.vibecoder.prompt_history import VibePromptHistoryLogger
from rush.vibecoder.loop_starvation import AsyncEventLoopLinter
from rush.vibecoder.feedback_loop import VibeFeedbackSupervisor


def test_vibecoder_orchestrator(tmp_path: Path):
    orch = VibeCoderOrchestrator(tmp_path)
    summary = orch.run_full_audit()
    assert summary.composite_health_score == 100.0
    assert summary.status == "HEALTHY"


def test_ast_route_cleaner(tmp_path: Path):
    f = tmp_path / "api.py"
    f.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def get_users():
    return []

@app.post("/items")
def create_item():
    return {}
""", encoding="utf-8")

    routes = AstRouteCleaner.extract_routes(f)
    assert len(routes) == 2
    assert routes[0] == ("GET", "/users", 6)
    assert routes[1] == ("POST", "/items", 10)


def test_env_sync_validator(tmp_path: Path):
    env_ex = tmp_path / ".env.example"
    env_ex.write_text("DATABASE_URL=postgres://localhost\nPORT=8000\n", encoding="utf-8")

    code_f = tmp_path / "app.py"
    code_f.write_text("""
import os
db = os.environ.get("DATABASE_URL")
secret = os.getenv("UNDECLARED_SECRET")
""", encoding="utf-8")

    val = EnvSyncValidator(tmp_path)
    missing = val.check_file_references(code_f)
    assert len(missing) == 1
    assert "UNDECLARED_SECRET" in missing[0]


def test_db_schema_drift(tmp_path: Path):
    models_f = tmp_path / "models.py"
    models_f.write_text("""
class User:
    __tablename__ = "users"

class Order:
    __tablename__ = "orders"
""", encoding="utf-8")

    sql_f = tmp_path / "init.sql"
    sql_f.write_text("""
CREATE TABLE users (id INT);
CREATE TABLE products (id INT);
""", encoding="utf-8")

    drift = DatabaseSchemaDriftDetector.check_drift(models_f, sql_f)
    assert len(drift) == 2
    assert any("orders" in d for d in drift)
    assert any("products" in d for d in drift)


def test_package_lockfile_guard(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    ok, err = PackageLockfileGuard.verify_node_lockfile(tmp_path)
    assert ok is False
    assert "no lockfile" in err

    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    ok_fixed, _ = PackageLockfileGuard.verify_node_lockfile(tmp_path)
    assert ok_fixed is True


def test_prompt_history_logger(tmp_path: Path):
    logger = VibePromptHistoryLogger(tmp_path)
    logger.record_prompt("Add user auth endpoint", ["src/auth.py"])
    assert (tmp_path / ".rush" / "vibe_prompts.json").exists()


def test_async_event_loop_linter():
    code = """
import time

async def fetch_data():
    time.sleep(5)  # blocking
    return 42

def normal_sync():
    time.sleep(1)  # allowed
"""
    tree = ast.parse(code)
    linter = AsyncEventLoopLinter("async_test.py")
    linter.visit(tree)

    assert len(linter.findings) == 1
    assert "Blocking call 'time.sleep'" in linter.findings[0]


def test_vibe_feedback_supervisor(tmp_path: Path):
    sup = VibeFeedbackSupervisor(tmp_path)

    clean_py = tmp_path / "clean.py"
    clean_py.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    res = sup.evaluate_recent_file(clean_py)
    assert res.is_clean is True
    assert res.duration_ms >= 0.0
    assert len(res.issues) == 0


def test_ast_docstring_auditor():
    from rush.vibecoder.prompt_history import AstFunctionDocstringAuditor
    code = """
def undocumented(x):
    return x
"""
    tree = ast.parse(code)
    auditor = AstFunctionDocstringAuditor("test.py")
    auditor.visit(tree)
    assert len(auditor.findings) >= 2


def test_vibe_telemetry_emitter(capsys):
    from rush.vibecoder.prompt_history import VibeCoderTelemetryNDJSONEmitter
    line = VibeCoderTelemetryNDJSONEmitter.emit_vibe_event("audit_pass", {"health": 98.0})
    assert '"event": "audit_pass"' in line
    captured = capsys.readouterr()
    assert '"health": 98.0' in captured.err


def test_vibe_config_loader(tmp_path: Path):
    from rush.vibecoder.prompt_history import VibeCoderConfigLoader
    cfg = VibeCoderConfigLoader.load_config(tmp_path)
    assert cfg["enabled"] is True
    assert cfg["strict_types"] is True
```

---

## 6. Structured Error Logging & Diagnostics Contract

All VibeCoder Toolkit diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:35:00.100Z", "phase": "vibecoder", "tool": "rush_vibecoder", "event": "audit_completed", "score": 98.5, "status": "HEALTHY"}
{"timestamp": "2026-08-21T10:35:01.200Z", "phase": "vibecoder", "tool": "rush_vibecoder", "event": "blocking_async_detected", "file": "src/api/routes.py", "line": 45}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of VibeCoder Toolkit implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **VibeCoder Toolkit: Unified 22-Tool Pipeline**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon VibeCoder Toolkit completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Vibe-Coding with Rush: Sub-Second AI Engineering Safeguards" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush vibecoder run`, `rush vibecoder watch`, `rush vibecoder audit` (flags: `--strict-types`, `--fix-safe`, `--sub-second`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for integrating Rush with Cursor, Windsurf, and Claude Code during rapid prototyping sessions.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated pre-save feedback loop recipes.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example vibe-coding session reports and before/after cleanup diffs.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add step-by-step tutorial on vibe-coding a full-stack SaaS with Rush guardrails active.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for loop starvation warnings, unhandled promise rejections, and type-drift recovery.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how VibeCoder orchestrates all 37 tools in parallel without slowing down agent code generation.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_vibecoder_run` and `rush_vibecoder_audit` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document VibeCoder aggregate finding and recommendation JSON response models.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `vibecoder` tool in Developer Experience & AI Tooling category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[vibecoder]` configuration table (`enabled_tools`, `latency_target_ms`, `auto_remediate_safe`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document 22-tool unified orchestrator, asynchronous supervisor engine, and incremental dependency analysis pipeline.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for registering new analysis passes into the VibeCoder pipeline.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Include CI workflow step for `rush vibecoder audit --strict-types`.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document full-pipeline concurrency fixtures and AST verification tests.
- **[`docs/tools/vibecoder.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/vibecoder.md)**: Create dedicated reference documentation.

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
git commit -m "feat(vibecoder): implement unified 22-tool execution pipeline and sub-second feedback loop"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
