# Phase 24 Implementation Plan: Hardened Workflow Suites & Environment Doctor

> **Phase:** 24 of 30  
> **Milestone:** Composite Developer Workflows & PATH-Resilient Diagnostics  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0017: Composite Workflow Suites and File Watcher](../adr/0017-composite-workflow-suites-and-file-watcher.md)

---

## 1. Objective & Scope

Implement developer-aligned composite workflow suites (`rush check`, `rush audit`, `rush gate`) and an environment health diagnostic command (`rush doctor`).

Incorporate **Control 4 (PATH Precedence & Binary Integrity)** to strictly resolve binaries from active virtual environments before global system PATH, disallow relative `./` lookups, and detect untrusted executable shadowing.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/workflows/__init__.py` (New: Composite suite runner)
- `src/rush/workflows/suites.py` (New: Definitions for `check`, `audit`, `gate`)
- `src/rush/tools/doctor.py` (New: `DoctorTool` environment auditor)
- `src/rush/cli.py` (Modified: Register `rush check`, `rush audit`, `rush gate`, `rush doctor`)
- `src/rush/catalog.py` (Modified: Register suites in `TOOL_SPECS`)
- `src/rush/logging.py` (Modified: `[rush-doctor:LEVEL]` and `[rush-workflow:LEVEL]`)

### Test & Fixture Files
- `tests/test_workflows.py` (New: Suite aggregation and short-circuit tests)
- `tests/test_doctor.py` (New: PATH resolution, shadowing alert, and environment tests)
- `tests/fixtures/doctor/` (New: Mock PATH fixtures)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_workflows.py` and `tests/test_doctor.py`:
1. `test_check_suite_execution_order()`: Verifies `rush check` runs TDD -> format -> lint -> typecheck -> slop -> test in sequence.
2. `test_audit_suite_security_aggregation()`: Verifies `rush audit` runs security -> secrets -> license -> sbom -> contract.
3. `test_doctor_path_hijacking_detection()`: Asserts a local `./ruff` executable is ignored in favor of `.venv/Scripts/ruff`.
4. `test_doctor_shadowing_alert()`: Asserts that conflicting PATH duplicates generate structured warnings.

### 3.2 GREEN Phase
Implement `suites.py`, `doctor.py`, and CLI commands.

### 3.3 REFACTOR Phase
Ensure workflow suites aggregate findings deterministically and support `--fail-fast` and `--parallel` execution flags.

---

## 4. Step-by-Step Implementation Tasks

### Task 24.1: Composite Workflow Definitions (`src/rush/workflows/suites.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from rush.tools.base import ToolResult, ExecutionPermissions

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
```python
import sys
import shutil
from pathlib import Path

def resolve_binary_secure(name: str) -> Path | None:
    # 1. Check active Python virtualenv
    venv_bin = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin") / name
    if sys.platform == "win32":
        venv_bin = venv_bin.with_suffix(".exe")
    if venv_bin.is_file():
        return venv_bin
    
    # 2. Check system PATH (never relative ./)
    path_hit = shutil.which(name)
    if path_hit:
        resolved = Path(path_hit).resolve()
        # Verify not in current working directory
        if resolved.is_relative_to(Path.cwd()) and not resolved.is_relative_to(Path(sys.prefix)):
            return None  # Shadowing rejected
        return resolved
    return None
```

### Task 24.3: Stderr Diagnostics & Logging
- `[rush-workflow:INFO] Starting composite suite: {name}`
- `[rush-workflow:WARN] Suite {name} completed with warnings`
- `[rush-doctor:INFO] Discovered verified engine: {engine} at {path}`
- `[rush-doctor:WARN] Suspicious local binary shadowing detected: {path}`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Add `rush check`, `rush audit`, `rush gate`, `rush doctor`).
2. `docs/USER_GUIDE.md` & `docs/user-guide/everyday-workflow.md` (Guide to using composite suites in daily dev).
3. `docs/CI_CD_GUIDE.md` & `docs/integrations/github-actions.md` (Using `rush gate` in CI).
4. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run workflow and doctor unit tests
.venv/Scripts/python.exe -m pytest tests/test_workflows.py tests/test_doctor.py -v

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
