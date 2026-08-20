# Phase 22 Implementation Plan: Confined Automated Remediation (`rush fix`)

> **Phase:** 22 of 30  
> **Milestone:** Unified Multi-Language Code Remediation  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)

---

## 1. Objective & Scope

Enable safe, multi-language automated code fixing across formatters, linters, and AST transformers with strict workspace confinement, git-safety checks, diff previews, and atomic rollbacks.

Incorporate **Control 2 (Path Confinement & Atomic Safety)** to prevent arbitrary file overwrites and symlink traversal escapes outside repository boundaries.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/tools/fix.py` (New: `FixTool` implementation)
- `src/rush/engines/base.py` (Modified: `Engine.run_fix()` interface)
- `src/rush/engines/ruff.py`, `biome.py`, `eslint.py`, `prettier.py` (Modified: add `run_fix()` implementations)
- `src/rush/cli.py` (Modified: add `rush fix` command and `--fix` flag on `lint`, `format`, `slop`)
- `src/rush/catalog.py` (Modified: register `fix` in `TOOL_SPECS`)
- `src/rush/logging.py` (Modified: `[rush-fix:LEVEL]` logging tags)

### Test & Fixture Files
- `tests/test_fix.py` (New: Auto-fix application, preview, and dirty-tree safety tests)
- `tests/fixtures/fix/` (New: Mock fix fixtures and malformed diffs)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write `tests/test_fix.py` testing:
1. `test_fix_path_traversal_rejection()`: Verifies that attempting to fix `../../etc/hosts` is blocked with a security error.
2. `test_fix_symlink_escape_blocked()`: Verifies that symlinks pointing outside the repository root are ignored.
3. `test_fix_dirty_tree_abort()`: Verifies that `rush fix` halts if uncommitted changes exist (unless `--force` is given).
4. `test_fix_diff_preview()`: Verifies `--dry-run` prints unified diffs without modifying files on disk.
5. `test_fix_atomic_rollback()`: Verifies that if an engine produces broken syntax, files are restored to pre-fix state.

### 3.2 GREEN Phase
Implement `src/rush/tools/fix.py` and engine `run_fix()` methods.

### 3.3 REFACTOR Phase
Ensure diff generation uses standard unified diff format and subprocess safety invariants are preserved.

---

## 4. Step-by-Step Implementation Tasks

### Task 22.1: Engine Auto-Fix Protocol (`src/rush/engines/base.py`)
Add `run_fix()` method to `Engine`:
```python
def run_fix(self, paths: list[Path], permissions: ExecutionPermissions) -> ToolResult:
    """Execute engine in auto-fix mode, returning modified files and residual findings."""
    return ToolResult(tool="fix", status="skipped", summary="Engine does not support automated fixing")
```

### Task 22.2: Core Fix Tool (`src/rush/tools/fix.py`)
Implement `FixTool` with workspace path assertions and git checks:
```python
from __future__ import annotations
from pathlib import Path
from rush.tools.base import BaseTool, ToolResult, ExecutionPermissions

class FixTool(BaseTool):
    name = "fix"
    
    def run(self, paths: list[Path], permissions: ExecutionPermissions, dry_run: bool = False, force: bool = False) -> ToolResult:
        # 1. Assert all paths resolve within repo root
        # 2. Check git clean status unless force=True
        # 3. Take pre-fix snapshots
        # 4. Dispatch engine fix commands
        # 5. Run post-fix verification
        ...
```

### Task 22.3: Engine Fix Adapters
Implement `run_fix` on:
- `RuffEngine`: `ruff format <paths>` and `ruff check --fix <paths>`
- `BiomeEngine`: `biome check --write <paths>`
- `ESLintEngine`: `eslint --fix <paths>`
- `PrettierEngine`: `prettier --write <paths>`

### Task 22.4: Error Logging & Stderr Diagnostics
- `[rush-fix:INFO] Applying safe fixes across {count} files via {engine}`
- `[rush-fix:WARN] Residual warnings remaining after auto-fix pass`
- `[rush-fix:SECURITY_ERROR] Target path outside repository boundary: {path}`
- `[rush-fix:ERROR] Uncommitted changes detected. Pass --force to override.`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/TOOL_CATALOG.md` & `docs/API_REFERENCE.md` (Add `rush fix` / `rush_fix`).
2. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Add `rush fix` command and `--fix` flags).
3. `docs/USER_GUIDE.md` & `docs/CLI_COOKBOOK.md` (Add recipes for `rush fix` and `--dry-run`).
4. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run fix tool and security tests
.venv/Scripts/python.exe -m pytest tests/test_fix.py -v

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
