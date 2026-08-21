# Phase 24 Implementation Plan: Hardened Workflow Suites & Environment Doctor

> **Phase:** 24 of 40  
> **Milestone:** Composite Developer Workflows & PATH-Resilient Diagnostics  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0017: Composite Workflow Suites and File Watcher](docs/adr/0017-composite-workflow-suites-and-file-watcher.md), [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Developers and autonomous agents waste tokens and time orchestrating dozens of individual quality tools manually. Phase 24 implements high-level composite workflow suites (`rush check`, `rush audit`, `rush gate`) and an environment health diagnostic command (`rush doctor`).

To prevent PATH hijacking attacks (where an untrusted `./ruff` or `./pytest` script in the working tree is executed), the environment doctor enforces virtual environment precedence, disallows relative `./` lookups, and flags untrusted executable shadowing.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Suite Failure Slicing)**: When running composite suites (`rush check`), passing steps are compressed into single-line green checkmarks; only failing tool outputs are expanded, saving up to 85% of terminal/LLM output tokens.
- **`graft` (Targeted Subprocess Execution)**: Workflows execute engines against scoped file targets (`--staged` / `--changed`) rather than scanning full trees.
- **`context-mode` (Aggregated Finding Tables)**: Results from 5+ tools in a suite are aggregated into a single deduplicated finding matrix.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/workflows/__init__.py` (New: Composite suite runner and parallel executor)
- `src/rush/workflows/suites.py` (New: Suite definitions for `check`, `audit`, `gate`)
- `src/rush/tools/doctor.py` (New: PATH-resilient toolchain and virtual environment auditor)
- `src/rush/cli.py` (Modified: Register `rush check`, `rush audit`, `rush gate`, `rush doctor`)
- `src/rush/mcp_server.py` (Modified: Register FastMCP composite suite endpoints)
- `src/rush/catalog.py` (Modified: Register workflow specifications)

### Test & Fixture Files
- `tests/test_workflows.py` (New: Execution order, `--fail-fast`, short-circuiting, and aggregation tests)
- `tests/test_doctor.py` (New: Virtualenv precedence, shadowing detection, untrusted binary rejection)
- `tests/fixtures/doctor/shadow_env/` (New: PATH shadowing test fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_workflows.py
def test_check_suite_runs_tools_in_order():
    suite = CHECK_SUITE
    assert suite.tool_sequence == ["tdd", "format", "lint", "typecheck", "slop", "test"]

def test_workflow_fail_fast_stops_on_first_error(tmp_path):
    runner = WorkflowRunner(repo_root=tmp_path)
    res = runner.run_suite(CHECK_SUITE, fail_fast=True)
    # Asserts execution halted immediately upon first failure

# tests/test_doctor.py
def test_doctor_rejects_cwd_binary_shadowing(tmp_path, monkeypatch):
    fake_bin = tmp_path / "ruff.exe"
    fake_bin.write_text("fake", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    
    resolved = resolve_binary_secure("ruff")
    # Must NOT resolve to local working directory fake binary
    assert resolved != fake_bin.resolve()
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/workflows/suites.py`, `src/rush/workflows/__init__.py`, and `src/rush/tools/doctor.py`.

### 4.3 REFACTOR Phase
Ensure composite suites support `--parallel` execution for independent tools (e.g. `lint` and `typecheck`) with thread-safe result aggregation.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:30:00Z", "phase": 24, "tool": "rush_workflow", "event": "suite_started", "suite": "check", "steps": 6}
{"timestamp": "2026-08-21T07:30:01Z", "phase": 24, "tool": "rush_doctor", "event": "binary_resolved", "binary": "ruff", "path": ".venv/Scripts/ruff.exe", "source": "virtualenv"}
{"timestamp": "2026-08-21T07:30:02Z", "phase": 24, "tool": "rush_doctor", "event": "shadowing_blocked", "binary": "ruff", "attempted": "./ruff.exe"}
```

---

## 6. Step-by-Step Task Specifications

### Task 24.1: Composite Workflow Definitions (`src/rush/workflows/suites.py`)
```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class WorkflowSuite:
    name: str
    description: str
    tool_sequence: list[str]

CHECK_SUITE = WorkflowSuite(
    name="check",
    description="Fast developer inner loop",
    tool_sequence=["tdd", "format", "lint", "typecheck", "slop", "test"],
)

AUDIT_SUITE = WorkflowSuite(
    name="audit",
    description="Security, supply chain, and compliance verification",
    tool_sequence=["security", "secrets", "license", "sbom", "contract"],
)

GATE_SUITE = WorkflowSuite(
    name="gate",
    description="Pull request and merge verification gate",
    tool_sequence=["coverage", "mutation", "complexity", "review"],
)
```

### Task 24.2: PATH-Resilient Environment Doctor (`src/rush/tools/doctor.py`)
Resolve binaries prioritizing active virtualenvs, strictly disallowing CWD relative lookups.

### Task 24.3: Parallel Workflow Runner (`src/rush/workflows/__init__.py`)
Execute suite steps with `--fail-fast` and `--parallel` flags.

### Task 24.4: CLI & FastMCP Registrations
Register `rush check`, `rush audit`, `rush gate`, `rush doctor` in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Anti-Shadowing Invariant**: Binaries in CWD must NEVER execute unless explicitly inside `.venv`.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
