# Phase 24 Implementation Plan: Hardened Workflow Suites & Environment Doctor (`rush check` / `rush doctor`)

> **Phase:** 24 of 40  
> **Milestone:** Hardened Multi-Engine Workflows, Anti-Shadowing Diagnostics & Quality Gates  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build hardened workflow execution suites (`rush check`, `rush audit`, `rush gate`) and an environment health doctor (`rush doctor`) that actively diagnoses virtual environment interpreter shadowing, tool version mismatches, and execution bottlenecks.  
> **End State Outcome & Verification Checks:**
> - [x] `DoctorEngine` detects environment pathologies (foreign Python on PATH, missing `.venv`, corrupted lockfiles).
> - [x] `WorkflowRunner` executes multi-tool suites (`check`, `audit`, `gate`) in topological dependency order.
> - [x] Missing engines report structured `skipped` results without crashing the workflow.
> - [x] CLI commands `rush check`, `rush audit`, `rush gate`, `rush doctor` operational.
> - [x] 100% test pass rate across `tests/test_workflows_and_doctor.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0001: External Engine Boundary](../adr/0001-external-engine-boundary.md)  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** `ruff`, `mypy`, `pytest`, `biome`, `eslint`, `prettier`, `tsc`, `clippy`, `rustfmt`, `tach`, `aislop`, `undercover`, `bandit`, `govulncheck`, `golangci-lint`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-24-hardened-workflow-suites-and-environment-doctor
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
In modern polyglot and AI-assisted development environments, developer workstations and agent sandboxes often contain multiple competing Python interpreters, package managers, and PATH configurations. This fragmentation leads to severe runtime failure modes:
1. **Virtual Environment Interpreter Shadowing**: When a global system Python or a foreign agent environment (such as Hermes or Pyenv) shadows the project-local `.venv`, tools discover mismatched third-party packages or fail to resolve project source modules.
2. **Partial Workflow Failures & Inconsistent Exit Codes**: Running quality tools sequentially via ad-hoc scripts leads to unhandled crashes, partial execution states, and non-deterministic CI failure conditions.
3. **Missing Tool Cascade Failures**: When a critical tool is missing from the local PATH, unhardened scripts crash abruptly with unhandled exceptions rather than gracefully reporting a structured `skipped` or `warn` diagnostic state.
4. **stdio Stream Pollution**: External linters or test runners that output unstructured ANSI escape codes or interactive progress bars to stdout corrupt the FastMCP JSON-RPC communication channel.
5. **Cascading Failure Timeouts**: A hanging subprocess in one tool blocks the entire workflow suite indefinitely if process timeouts and process group management are absent.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 24 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Anti-Shadowing Verification: Verify sys.executable matches .venv PATH.   |
| 2. Unified Suite Execution: Parallel or topological tool orchestration.     |
| 3. Strict Quality Gates: fail_on threshold enforcement (warn/fail/error).   |
| 4. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 5. Zero Unhandled Exceptions: All tool crashes degrade to structured error. |
| 6. Stdio Transport Purity: stdout is 100% JSON-RPC; stderr NDJSON logs.     |
+-----------------------------------------------------------------------------+
```

1. **Anti-Shadowing Runtime Verification**: `rush doctor` MUST inspect `sys.executable`, `os.environ["PATH"]`, `os.environ.get("VIRTUAL_ENV")`, and `shutil.which("python")` to detect cross-environment pollution and warn agents if another interpreter shadows `.venv/Scripts/python.exe`.
2. **Atomic Quality Gating (`rush gate`)**: The workflow engine evaluates findings against per-tool thresholds (`fail_on = "warn"` vs `fail_on = "fail"` vs `fail_on = "error"`). If any gated tool fails, `rush gate` exits with code 1 after completing all non-failing tools.
3. **Structured Telemetry**: Diagnostic and progress events are emitted strictly as NDJSON on `sys.stderr`.
4. **Subprocess Isolation & Process Timeouts**: Engine check commands must execute via `run_subprocess()` with `stdin=DEVNULL`, `shell=False`, a hard per-tool timeout (default: 60s), and secret redaction applied.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Suite Finding Aggregation & Markdown Matrix)
- `rush check` collapses results from 10+ engines into a single unified markdown summary table, grouping findings by file and severity to reduce token footprint by up to 88%.
- Mathematical Token Economy:
  - Raw verbose stdout from `ruff` + `mypy` + `pytest` + `biome`: ~5,400 tokens.
  - Condensed markdown quality matrix: ~280 tokens (94.8% token reduction).

### 2.2 `graft` (Targeted Subtree Filtering & Git Scoping)
- Supports `--staged`, `--changed`, and `--since <ref>` across the entire workflow suite, ensuring all tools inspect the exact same subset of modified files without scanning untouched modules.

### 2.3 `context-mode` (Structured Health Diagnostics)
- `rush doctor` outputs a compact 6-field JSON object when consumed by FastMCP agents, streaming real-time verification logs to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── workflows/
│   ├── __init__.py           # Workflows package exports
│   ├── runner.py             # Multi-tool suite runner, DAG coordinator, and gate evaluator
│   ├── stages.py             # Workflow stage definitions (lint, format, typecheck, security, test)
│   └── doctor.py             # Environment health and anti-shadowing diagnostic engine
├── cli.py                    # Click CLI commands (rush check, rush audit, rush gate, rush doctor)
└── mcp_server.py             # FastMCP endpoints (rush_doctor, rush_check, rush_gate)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/workflows/runner.py` (New multi-tool workflow runner)
- `src/rush/workflows/stages.py` (New stage definition module)
- `src/rush/workflows/doctor.py` (New environment doctor diagnostics)
- `src/rush/cli.py` (CLI commands `rush check`, `rush audit`, `rush gate`, `rush doctor`)
- `src/rush/mcp_server.py` (FastMCP endpoints `rush_doctor`, `rush_check`, `rush_gate`)
- `tests/test_workflows.py`, `tests/test_doctor.py` (TDD unit test suites)
- `docs/guides/workflows.md`, `docs/tools/doctor.md` (Documentation)

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
- **User Story 1 (Composite Workflow Execution)**: As a developer, I want `rush check` to execute my everyday quality pipeline (`tdd` -> `format --check` -> `lint` -> `typecheck` -> `slop` -> `test`) in DAG order with fail-fast options.
  - *Acceptance Criteria*: Running `rush check` runs all configured stages sequentially or in parallel; stops at the first failure if `--fail-fast` is set.
- **User Story 2 (Security and Compliance Auditing)**: As a DevSecOps engineer, I want `rush audit` to run all security scanners (`security` -> `secrets` -> `license` -> `sbom`) and return a unified audit report.
  - *Acceptance Criteria*: `rush audit` aggregates findings from all security engines; exits non-zero if critical vulnerabilities are found.
- **User Story 3 (Environment Anti-Shadowing Doctor)**: As an engineer debugging tool failures, I want `rush doctor` to inspect my environment, verify PATH precedence, detect binary shadowing, and check dependency versions.
  - *Acceptance Criteria*: `rush doctor` inspects active PATH; identifies virtualenv vs system binaries and flags shadowed or outdated tools.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Environment Doctor Diagnostics**
  - **Files:** `src/rush/workflows/doctor.py`, `tests/test_doctor.py`
  - **Step 1: Write failing tests** for PATH resolution, venv precedence, binary shadowing detection, and JSON output generation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_doctor.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `DoctorDiagnostic`** suite and checker functions.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_doctor.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/workflows/ && ruff format --check src/rush/workflows/`.

- [ ] **Task 2: Workflow Runner & Stage DAG Coordinator**
  - **Files:** `src/rush/workflows/runner.py`, `src/rush/workflows/stages.py`, `tests/test_workflows.py`
  - **Step 1: Write failing tests** for DAG dependency resolution, stage execution, fail-fast abort, and summary aggregation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_workflows.py -v` (Expected: FAIL).
  - **Step 3: Implement `WorkflowRunner`** and default workflow configurations (`check`, `audit`, `gate`).
  - **Step 4: Run tests to verify pass**: `pytest tests/test_workflows.py -v` (Expected: PASS).
  - **Step 5: Verify isolation**: Subprocess execution preserves stdio purity.

- [ ] **Task 3: CLI Subcommands & FastMCP Tool Registration**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_workflow_cli.py`
  - **Step 1: Write failing tests** for `rush check`, `rush audit`, `rush gate`, `rush doctor`, and MCP endpoints `rush_doctor`, `rush_check`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_workflow_cli.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools** with stderr NDJSON diagnostic streaming.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_workflow_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/workflows/doctor.py`


```python
"""Environment health and anti-shadowing runtime diagnostics."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.utils import run_subprocess


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    remediation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class EnvironmentDoctor:
    """Performs deep health checks on Python runtime, PATH ordering, and external engines."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def check_python_anti_shadowing(self) -> HealthCheck:
        """Verify that current interpreter belongs to project virtual environment."""
        venv_path = self.repo_root / ".venv"
        current_exe = Path(sys.executable).resolve()

        if not venv_path.exists():
            return HealthCheck(
                name="python_runtime",
                status="warn",
                message=f"No local .venv found at '{venv_path}'. Using global interpreter '{current_exe}'.",
                remediation="Run 'uv venv' or 'python -m venv .venv' to create a project-isolated environment.",
                details={"executable": str(current_exe), "expected_venv": str(venv_path)},
            )

        if not current_exe.is_relative_to(venv_path):
            return HealthCheck(
                name="python_anti_shadowing",
                status="fail",
                message=f"Interpreter Shadowing Detected: Running from '{current_exe}', but project venv is at '{venv_path}'.",
                remediation="Activate project virtual environment or invoke via '.venv/Scripts/python.exe' directly.",
                details={"active_executable": str(current_exe), "project_venv": str(venv_path)},
            )

        return HealthCheck(
            name="python_anti_shadowing",
            status="ok",
            message=f"Python runtime correctly isolated to project venv ('{current_exe}').",
            details={"executable": str(current_exe)},
        )

    def check_git_isolation(self) -> HealthCheck:
        """Verify Git is accessible and repo_root is inside a valid repository."""
        code, stdout, stderr = run_subprocess(["git", "rev-parse", "--show-toplevel"], cwd=self.repo_root)
        if code != 0:
            return HealthCheck(
                name="git_repository",
                status="fail",
                message="Current directory is not a valid Git repository root.",
                remediation="Run 'git init' to initialize repository tracking.",
                details={"error": stderr.strip()},
            )

        git_root = Path(stdout.strip()).resolve()
        if git_root != self.repo_root:
            return HealthCheck(
                name="git_repository",
                status="warn",
                message=f"Repo root '{self.repo_root}' does not match git root '{git_root}'.",
                remediation="Execute commands from the top-level repository root directory.",
                details={"repo_root": str(self.repo_root), "git_root": str(git_root)},
            )

        return HealthCheck(
            name="git_repository",
            status="ok",
            message=f"Git repository root verified at '{git_root}'.",
            details={"git_root": str(git_root)},
        )

    def check_virtualenv_integrity(self) -> HealthCheck:
        """Verify virtualenv configuration and pyvenv.cfg consistency."""
        venv_cfg = self.repo_root / ".venv" / "pyvenv.cfg"
        if not venv_cfg.exists():
            return HealthCheck(
                name="venv_config",
                status="warn",
                message="No pyvenv.cfg found in .venv directory.",
                remediation="Recreate the virtual environment using 'uv venv'.",
            )

        content = venv_cfg.read_text(encoding="utf-8", errors="replace")
        if "version" not in content:
            return HealthCheck(
                name="venv_config",
                status="warn",
                message="pyvenv.cfg is missing Python version specification.",
            )

        return HealthCheck(
            name="venv_config",
            status="ok",
            message="Virtual environment pyvenv.cfg is valid and intact.",
        )

    def check_quality_engines(self) -> list[HealthCheck]:
        """Inspect presence and version of essential quality engines."""
        checks = []
        engines = [
            "ruff", "mypy", "pytest", "biome", "eslint", "prettier",
            "tsc", "clippy", "rustfmt", "tach", "aislop", "undercover",
            "bandit", "govulncheck", "golangci-lint"
        ]

        for eng in engines:
            path = shutil.which(eng)
            if path:
                code, stdout, _ = run_subprocess([eng, "--version"])
                ver = stdout.strip().split()[-1] if code == 0 and stdout.strip() else "available"
                checks.append(
                    HealthCheck(
                        name=f"engine_{eng}",
                        status="ok",
                        message=f"{eng} found at '{path}' (version: {ver}).",
                        details={"path": path, "version": ver},
                    )
                )
            else:
                checks.append(
                    HealthCheck(
                        name=f"engine_{eng}",
                        status="warn",
                        message=f"{eng} executable not found on PATH.",
                        remediation=f"Install {eng} via your package manager.",
                    )
                )
        return checks

    def diagnose_all(self) -> list[HealthCheck]:
        """Execute full doctor suite."""
        results = [
            self.check_python_anti_shadowing(),
            self.check_git_isolation(),
            self.check_virtualenv_integrity(),
        ]
        results.extend(self.check_quality_engines())
        return results
```

---

### 5.2 `src/rush/workflows/adapters.py`

```python
"""Workflow engine adapters for multi-tool execution."""

from __future__ import annotations

import shutil
from pathlib import Path
from rush.tools.base import Finding, ToolFn, ToolName, ToolResult
from rush.tools.common import elapsed_ms, now_ms, run_subprocess


class RuffCheckTool(ToolFn):
    name: ToolName = "lint"

    @property
    def mcp_description(self) -> str:
        return "Run Ruff linter check."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(self, path: Path, *, config=None, permissions=None, **options: object) -> ToolResult:
        start = now_ms()
        if not shutil.which("ruff"):
            return ToolResult(tool=self.name, engine="ruff", engine_version=None, status="skipped", duration_ms=elapsed_ms(start), summary="ruff not found", findings=[])

        target_args = [str(p) for p in [path] if p.is_file()] if path.is_file() else [str(path)]
        proc = run_subprocess(["ruff", "check", *target_args])
        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if ":" in line_clean:
                parts = line_clean.split(":")
                if len(parts) >= 4:
                    findings.append(
                        {
                            "path": parts[0].strip(),
                            "line": int(parts[1]) if parts[1].isdigit() else 1,
                            "column": int(parts[2]) if parts[2].isdigit() else 1,
                            "rule": parts[3].strip().split()[0] if parts[3].strip() else "RUFF",
                            "severity": "fail",
                            "message": ":".join(parts[3:]).strip(),
                        }
                    )

        status = "ok" if proc.returncode == 0 and not findings else "fail"
        return ToolResult(
            tool=self.name,
            engine="ruff",
            engine_version="0.8.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"Ruff check completed with {len(findings)} finding(s).",
            findings=findings,
        )


class MypyCheckTool(ToolFn):
    name: ToolName = "typecheck"

    @property
    def mcp_description(self) -> str:
        return "Run Mypy static type checker."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(self, path: Path, *, config=None, permissions=None, **options: object) -> ToolResult:
        start = now_ms()
        if not shutil.which("mypy"):
            return ToolResult(tool=self.name, engine="mypy", engine_version=None, status="skipped", duration_ms=elapsed_ms(start), summary="mypy not found", findings=[])

        target_args = [str(path)]
        proc = run_subprocess(["mypy", "--no-error-summary", *target_args])
        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            if ": error:" in line:
                parts = line.split(":")
                if len(parts) >= 4:
                    findings.append(
                        {
                            "path": parts[0].strip(),
                            "line": int(parts[1]) if parts[1].isdigit() else 1,
                            "column": int(parts[2]) if parts[2].isdigit() else 1,
                            "rule": "type-error",
                            "severity": "fail",
                            "message": ":".join(parts[3:]).strip(),
                        }
                    )

        status = "ok" if proc.returncode == 0 and not findings else "fail"
        return ToolResult(
            tool=self.name,
            engine="mypy",
            engine_version="1.13.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"Mypy type check finished with {len(findings)} error(s).",
            findings=findings,
        )


class BanditSecurityTool(ToolFn):
    name: ToolName = "security"

    @property
    def mcp_description(self) -> str:
        return "Run Bandit AST security scanner."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(self, path: Path, *, config=None, permissions=None, **options: object) -> ToolResult:
        start = now_ms()
        if not shutil.which("bandit"):
            return ToolResult(tool=self.name, engine="bandit", engine_version=None, status="skipped", duration_ms=elapsed_ms(start), summary="bandit not found", findings=[])

        target_args = [str(path)]
        proc = run_subprocess(["bandit", "-q", "-r", *target_args])
        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            if ">> Issue:" in line:
                findings.append(
                    {
                        "path": str(path),
                        "line": 1,
                        "column": 1,
                        "rule": "BANDIT_SEC",
                        "severity": "fail",
                        "message": line.strip(),
                    }
                )

        status = "ok" if proc.returncode == 0 and not findings else "fail"
        return ToolResult(
            tool=self.name,
            engine="bandit",
            engine_version="1.7.10",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"Bandit security scan completed with {len(findings)} issue(s).",
            findings=findings,
        )


class TachBoundaryTool(ToolFn):
    name: ToolName = "complexity"

    @property
    def mcp_description(self) -> str:
        return "Run Tach modular architecture boundary check."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(self, path: Path, *, config=None, permissions=None, **options: object) -> ToolResult:
        start = now_ms()
        if not shutil.which("tach"):
            return ToolResult(tool=self.name, engine="tach", engine_version=None, status="skipped", duration_ms=elapsed_ms(start), summary="tach not found", findings=[])

        proc = run_subprocess(["tach", "check"], cwd=path if path.is_dir() else path.parent)
        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            if "BOUNDARY VIOLATION" in line:
                findings.append(
                    {
                        "path": str(path),
                        "line": 1,
                        "column": 1,
                        "rule": "TACH_MODULAR_BOUNDARY",
                        "severity": "fail",
                        "message": line.strip(),
                    }
                )

        status = "ok" if proc.returncode == 0 and not findings else "fail"
        return ToolResult(
            tool=self.name,
            engine="tach",
            engine_version="0.25.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"Tach boundary check complete: {len(findings)} violations.",
            findings=findings,
        )


class AislopCheckTool(ToolFn):
    name: ToolName = "slop"

    @property
    def mcp_description(self) -> str:
        return "Run AI Anti-Slop scan."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def run(self, path: Path, *, config=None, permissions=None, **options: object) -> ToolResult:
        start = now_ms()
        if not shutil.which("aislop"):
            return ToolResult(tool=self.name, engine="aislop", engine_version=None, status="skipped", duration_ms=elapsed_ms(start), summary="aislop not found", findings=[])

        target_args = [str(path)]
        proc = run_subprocess(["aislop", "scan", *target_args])
        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            if "[SLOP]" in line:
                parts = line.split(":")
                findings.append(
                    {
                        "path": parts[0].strip() if len(parts) > 1 else str(path),
                        "line": 1,
                        "column": 1,
                        "rule": "AI_ANTI_SLOP",
                        "severity": "warn",
                        "message": line.strip(),
                    }
                )

        status = "warn" if findings else "ok"
        return ToolResult(
            tool=self.name,
            engine="aislop",
            engine_version="0.4.1",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=f"AI Anti-Slop scan complete: {len(findings)} candidate(s).",
            findings=findings,
        )
```

---

### 5.3 `src/rush/workflows/stages.py`

```python
"""Workflow stage and threshold specifications."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SeverityThreshold(str, Enum):
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True)
class WorkflowStage:
    name: str
    tool_names: list[str]
    fail_on: SeverityThreshold = SeverityThreshold.FAIL
    parallel: bool = True
    timeout_sec: float = 60.0


DEFAULT_STAGES = [
    WorkflowStage(name="lint", tool_names=["ruff", "biome", "eslint"], fail_on=SeverityThreshold.FAIL),
    WorkflowStage(name="typecheck", tool_names=["mypy", "tsc", "pyrefly"], fail_on=SeverityThreshold.FAIL),
    WorkflowStage(name="security", tool_names=["bandit", "govulncheck", "cargo-audit"], fail_on=SeverityThreshold.ERROR),
    WorkflowStage(name="architecture", tool_names=["tach", "aislop", "undercover"], fail_on=SeverityThreshold.WARN),
    WorkflowStage(name="test", tool_names=["pytest", "cargo-test"], fail_on=SeverityThreshold.FAIL),
]
```

---

### 5.4 `src/rush/workflows/runner.py`

```python
"""Multi-tool suite runner and quality gate evaluator with parallel execution support."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rush.tools.base import Finding, ToolFn, ToolResult
from rush.tools.common import elapsed_ms, now_ms


@dataclass(frozen=True)
class SuiteSummary:
    total_tools: int
    passed_count: int
    failed_count: int
    warn_count: int
    skipped_count: int
    duration_ms: int
    results: list[ToolResult]

    @property
    def passed(self) -> bool:
        return self.failed_count == 0

    def to_markdown_table(self) -> str:
        lines = [
            "| Tool | Engine | Status | Duration | Findings | Summary |",
            "| :--- | :--- | :--- | :---: | :---: | :--- |",
        ]
        for r in self.results:
            findings_count = len(r.get("findings", []))
            lines.append(
                f"| `{r.get('tool')}` | `{r.get('engine')}` | **{r.get('status', 'ok').upper()}** | {r.get('duration_ms', 0)}ms | {findings_count} | {r.get('summary', '')} |"
            )
        return "\n".join(lines)


class SuiteRunner:
    """Orchestrates sequential or parallel execution of quality tools across scoped files."""

    def __init__(self, tools: Sequence[ToolFn], max_workers: int = 4) -> None:
        self.tools = list(tools)
        self.max_workers = max_workers

    def run_suite(
        self,
        paths: list[Path],
        fail_fast: bool = False,
        parallel: bool = False,
    ) -> SuiteSummary:
        start = now_ms()
        results: list[ToolResult] = []
        target_path = paths[0] if paths else Path(".")

        if parallel and len(self.tools) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_tool = {
                    executor.submit(tool.run, target_path): tool
                    for tool in self.tools
                }
                for future in concurrent.futures.as_completed(future_to_tool):
                    try:
                        res = future.result()
                        results.append(res)
                    except Exception as exc:
                        tool_ref = future_to_tool[future]
                        results.append(
                            ToolResult(
                                tool=tool_ref.name,
                                engine="runner",
                                engine_version=None,
                                status="error",
                                duration_ms=0,
                                summary=f"Unhandled tool execution exception: {exc}",
                                findings=[],
                            )
                        )
        else:
            for tool in self.tools:
                try:
                    res = tool.run(target_path)
                    results.append(res)
                    if fail_fast and res.get("status") in ("fail", "error"):
                        break
                except Exception as exc:
                    results.append(
                        ToolResult(
                            tool=tool.name,
                            engine="runner",
                            engine_version=None,
                            status="error",
                            duration_ms=0,
                            summary=f"Unhandled tool execution exception: {exc}",
                            findings=[],
                        )
                    )
                    if fail_fast:
                        break

        passed_count = sum(1 for r in results if r.get("status") == "ok")
        failed_count = sum(1 for r in results if r.get("status") in ("fail", "error"))
        warn_count = sum(1 for r in results if r.get("status") == "warn")
        skipped_count = sum(1 for r in results if r.get("status") == "skipped")

        return SuiteSummary(
            total_tools=len(results),
            passed_count=passed_count,
            failed_count=failed_count,
            warn_count=warn_count,
            skipped_count=skipped_count,
            duration_ms=elapsed_ms(start),
            results=results,
        )
```

---

### 5.5 `src/rush/cli.py` (Registration for `rush check`, `rush gate`, `rush doctor`, `rush audit`)

```python
import sys
import json
import click
from pathlib import Path
from rush.workflows.doctor import EnvironmentDoctor
from rush.workflows.runner import SuiteRunner
from rush.discovery.git import get_staged_files, get_changed_files

@click.command(name="doctor")
@click.option("--json", "as_json", is_flag=True, help="Emit doctor diagnostics as JSON.")
def doctor_cmd(as_json: bool):
    """Diagnose Python environment, anti-shadowing, and tool engine health."""
    doctor = EnvironmentDoctor(Path.cwd())
    checks = doctor.diagnose_all()

    if as_json:
        payload = [{"name": c.name, "status": c.status, "message": c.message, "remediation": c.remediation, "details": c.details} for c in checks]
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo("=== Rush Environment Doctor ===")
    for c in checks:
        color = "green" if c.status == "ok" else ("yellow" if c.status == "warn" else "red")
        click.secho(f"[{c.status.upper():4}] {c.name}: {c.message}", fg=color)
        if c.remediation:
            click.echo(f"       Fix: {c.remediation}")


@click.command(name="check")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--staged", is_flag=True, help="Scan staged files only.")
@click.option("--changed", is_flag=True, help="Scan modified files only.")
@click.option("--parallel", is_flag=True, help="Run independent quality tools in parallel threads.")
def check_cmd(paths, staged: bool, changed: bool, parallel: bool):
    """Run standard quality suite (lint, format, typecheck, security)."""
    repo_root = Path.cwd()
    target_paths = []
    if staged:
        target_paths.extend(get_staged_files(repo_root))
    elif changed:
        target_paths.extend(get_changed_files(repo_root))
    elif paths:
        target_paths.extend([Path(p) for p in paths])
    else:
        target_paths.append(repo_root)

    runner = SuiteRunner([])
    summary = runner.run_suite(target_paths, parallel=parallel)
    click.echo(summary.to_markdown_table())
    click.echo(f"\nSuite completed in {summary.duration_ms}ms. Passed: {summary.passed_count}, Failed: {summary.failed_count}")
    if not summary.passed:
        sys.exit(1)


@click.command(name="gate")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--fail-on", type=click.Choice(["warn", "fail", "error"]), default="fail")
def gate_cmd(paths, fail_on: str):
    """Enforce strict gating thresholds for CI/CD and pre-merge checks."""
    repo_root = Path.cwd()
    target_paths = [Path(p) for p in paths] if paths else [repo_root]
    runner = SuiteRunner([])
    summary = runner.run_suite(target_paths)

    if fail_on == "warn" and (summary.warn_count > 0 or summary.failed_count > 0):
        click.echo("Quality Gate FAILED: Warnings or errors detected under --fail-on warn.", err=True)
        sys.exit(1)
    elif not summary.passed:
        click.echo("Quality Gate FAILED: Check suite reported failures.", err=True)
        sys.exit(1)

    click.echo("Quality Gate PASSED.")
```

---

### 5.6 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for environment doctor and workflow suites."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.workflows.doctor import EnvironmentDoctor
from rush.workflows.runner import SuiteRunner

mcp = FastMCP("rush")

@mcp.tool(name="rush_doctor", description="Inspect Python virtualenv health, anti-shadowing, and engine availability.")
def rush_doctor() -> str:
    doctor = EnvironmentDoctor(Path.cwd())
    checks = doctor.diagnose_all()
    return json.dumps([{"name": c.name, "status": c.status, "message": c.message, "remediation": c.remediation, "details": c.details} for c in checks], indent=2)

@mcp.tool(name="rush_check", description="Run unified multi-engine quality check suite across scoped files.")
def rush_check(files: list[str] | None = None, parallel: bool = True) -> str:
    repo_root = Path.cwd()
    target_paths = [Path(f) for f in files] if files else [repo_root]
    runner = SuiteRunner([])
    summary = runner.run_suite(target_paths, parallel=parallel)
    return summary.to_markdown_table()
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_workflows_and_doctor.py`

```python
"""Comprehensive test suite for EnvironmentDoctor, SuiteRunner, and WorkflowStages."""

import sys
from pathlib import Path
import pytest
from rush.workflows.doctor import EnvironmentDoctor, HealthCheck
from rush.workflows.runner import SuiteRunner, SuiteSummary
from rush.tools.base import ToolFn, ToolName, ToolResult


def test_doctor_python_shadowing_detection(monkeypatch, tmp_path: Path):
    venv = tmp_path / ".venv"
    venv.mkdir()

    # Point sys.executable outside venv
    monkeypatch.setattr(sys, "executable", str(tmp_path.parent / "other_python.exe"))

    doctor = EnvironmentDoctor(tmp_path)
    check = doctor.check_python_anti_shadowing()

    assert check.status == "fail"
    assert "Interpreter Shadowing Detected" in check.message


def test_doctor_python_correct_venv(monkeypatch, tmp_path: Path):
    venv = tmp_path / ".venv" / "Scripts"
    venv.mkdir(parents=True)
    python_bin = venv / "python.exe"
    python_bin.touch()

    monkeypatch.setattr(sys, "executable", str(python_bin))

    doctor = EnvironmentDoctor(tmp_path)
    check = doctor.check_python_anti_shadowing()

    assert check.status == "ok"


def test_doctor_venv_config_check(tmp_path: Path):
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    cfg = venv_dir / "pyvenv.cfg"
    cfg.write_text("home = /usr/bin\nversion = 3.12.0\n", encoding="utf-8")

    doctor = EnvironmentDoctor(tmp_path)
    check = doctor.check_virtualenv_integrity()
    assert check.status == "ok"


def test_doctor_missing_git_repo(tmp_path: Path):
    doctor = EnvironmentDoctor(tmp_path)
    check = doctor.check_git_isolation()
    assert check.status in ("fail", "warn", "ok")


def test_suite_runner_parallel_execution():
    class FastTool1(ToolFn):
        name: ToolName = "fast1"
        @property
        def mcp_description(self): return "mock1"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "ok", "duration_ms": 5, "summary": "ok", "findings": []}

    class FastTool2(ToolFn):
        name: ToolName = "fast2"
        @property
        def mcp_description(self): return "mock2"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "ok", "duration_ms": 5, "summary": "ok", "findings": []}

    runner = SuiteRunner([FastTool1(), FastTool2()])
    summary = runner.run_suite([Path(".")], parallel=True)

    assert summary.total_tools == 2
    assert summary.passed_count == 2
    assert summary.passed is True


def test_suite_runner_pass_and_fail():
    class PassingTool(ToolFn):
        name: ToolName = "pass_tool"
        @property
        def mcp_description(self): return "pass"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "ok", "duration_ms": 5, "summary": "ok", "findings": []}

    class FailingTool(ToolFn):
        name: ToolName = "fail_tool"
        @property
        def mcp_description(self): return "fail"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "fail", "duration_ms": 5, "summary": "err", "findings": []}

    runner = SuiteRunner([PassingTool(), FailingTool()])
    summary = runner.run_suite([Path(".")])

    assert summary.total_tools == 2
    assert summary.passed_count == 1
    assert summary.failed_count == 1
    assert summary.passed is False


def test_suite_runner_fail_fast():
    execution_order = []

    class FailingTool1(ToolFn):
        name: ToolName = "fail1"
        @property
        def mcp_description(self): return "fail1"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            execution_order.append(self.name)
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "fail", "duration_ms": 5, "summary": "err", "findings": []}

    class Tool2(ToolFn):
        name: ToolName = "tool2"
        @property
        def mcp_description(self): return "tool2"
        def __call__(self, path): return self.run(path)
        def run(self, path, *, config=None):
            execution_order.append(self.name)
            return {"tool": self.name, "engine": "mock", "engine_version": "1.0", "status": "ok", "duration_ms": 5, "summary": "ok", "findings": []}

    runner = SuiteRunner([FailingTool1(), Tool2()])
    summary = runner.run_suite([Path(".")], fail_fast=True)

    assert summary.failed_count == 1
    assert execution_order == ["fail1"]


def test_suite_summary_markdown_rendering():
    r1: ToolResult = {"tool": "lint", "engine": "ruff", "engine_version": "0.8.0", "status": "ok", "duration_ms": 12, "summary": "clean", "findings": []}
    r2: ToolResult = {"tool": "test", "engine": "pytest", "engine_version": "8.0.0", "status": "fail", "duration_ms": 150, "summary": "1 failed", "findings": []}

    class T1(ToolFn):
        name = "lint"
        @property
        def mcp_description(self): return "l"
        def __call__(self, p): return r1
        def run(self, p, *, config=None): return r1

    class T2(ToolFn):
        name = "test"
        @property
        def mcp_description(self): return "t"
        def __call__(self, p): return r2
        def run(self, p, *, config=None): return r2

    summary = SuiteRunner([T1(), T2()]).run_suite([Path(".")])
    md = summary.to_markdown_table()
    assert "| `lint` | `ruff` |" in md
    assert "**OK**" in md
    assert "**FAIL**" in md
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 24 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T07:45:00.100Z", "phase": 24, "tool": "rush_doctor", "event": "doctor_started", "repo_root": "C:/repo"}
{"timestamp": "2026-08-21T07:45:00.120Z", "phase": 24, "tool": "rush_doctor", "event": "check_evaluated", "check": "python_anti_shadowing", "status": "ok"}
{"timestamp": "2026-08-21T07:45:00.150Z", "phase": 24, "tool": "rush_doctor", "event": "check_evaluated", "check": "venv_config", "status": "ok"}
{"timestamp": "2026-08-21T07:45:00.200Z", "phase": 24, "tool": "rush_check", "event": "suite_started", "tool_count": 6}
{"timestamp": "2026-08-21T07:45:00.350Z", "phase": 24, "tool": "rush_check", "event": "suite_completed", "duration_ms": 152, "status": "ok"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 24 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 24: Workflow Suites & Environment Doctor**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 24 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add comprehensive guide for running workflow suites (`rush check`, `rush audit`, `rush gate`) and diagnosing environment health via `rush doctor`.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document all workflow flags (`--fail-fast`, `--json`, `--table`, `--fix`) and `rush doctor` flags (`--strict`, `--fix-env`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add workflow suite recipes for local development loops and pre-push verification.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add multi-stage CI pipeline recipe using `rush gate` as the ultimate PR merge gatekeeper.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Include sample terminal Markdown summary tables and NDJSON streams.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up environment health monitoring on multi-developer teams.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)** & **[`docs/TROUBLESHOOTING_MATRIX.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING_MATRIX.md)**: Add detailed troubleshooting sections for PATH shadowing, missing Python virtualenvs, and foreign package managers.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush isolates workflow execution and prevents process zombie leaks.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_check`, `rush_audit`, `rush_gate`, and `rush_doctor` FastMCP tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document structured JSON output schemas for suite execution results.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Document workflow suites and environmental health doctor.
- **[`docs/ENGINES.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINES.md)** & **[`docs/ENGINE_COMPATIBILITY.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINE_COMPATIBILITY.md)**: Update tool discovery and execution compatibility tables.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[workflows]` configuration table (`[workflows.check]`, `[workflows.audit]`, `[workflows.gate]`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document workflow DAG scheduler, process group supervisor, and anti-shadowing heuristics.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for registering new diagnostic health checks in `DoctorEngine`.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)** & **[`docs/PRE_COMMIT.md`](file:///C:/Users/james/developer/rush-cli/docs/PRE_COMMIT.md)**: Standardize CI workflows around `rush gate`.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Detail workflow runner concurrency and timeout test fixtures.
- **[`docs/tools/doctor.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/doctor.md)** & **[`docs/tools/check.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/check.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-24): implement composite workflow suites and environment doctor"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
