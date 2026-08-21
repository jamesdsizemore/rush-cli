# Phase 22 Implementation Plan: Unified Multi-Language Code Remediation (`rush fix`)

> **Phase:** 22 of 40  
> **Milestone:** Unified Multi-Language Code Remediation & Atomic Rollback  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Autonomous coding agents frequently make unstructured edits that leave syntax errors or formatting violations in the repository. Phase 22 introduces a safe, multi-language automated code remediation engine (`rush fix` / `rush_fix`) across linters, formatters, and static analyzers.

To guarantee zero repository corruption, the tool enforces strict workspace confinement (blocking symlink escapes and path traversals), dirty-tree safety checks (aborting if uncommitted changes exist unless `--force` is provided), unified diff previews (`--dry-run`), and atomic post-fix rollbacks if syntax errors are introduced.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Diff Summaries)**: When previewing fixes (`--dry-run`), `rush fix` emits compact unified diffs truncated to modified hunks (+/- 3 context lines), saving up to 80% tokens compared to echoing whole files.
- **`graft` (Targeted File Slicing)**: Scans only the specific files containing autofixable rule violations identified in pre-flight checks.
- **`context-mode` (Compact JSON & Patch Output)**: Emits structured fix summaries with exact line ranges and applied rule IDs in NDJSON.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/fix.py` (New: `FixTool` implementation with atomic snapshotting and post-fix validation)
- `src/rush/engines/base.py` (Modified: `Engine.run_fix()` interface)
- `src/rush/engines/ruff.py`, `biome.py`, `eslint.py`, `prettier.py` (Modified: add `run_fix()` adapter methods)
- `src/rush/cli.py` (Modified: Register `rush fix` command and `--fix` flags on `lint`, `format`)
- `src/rush/mcp_server.py` (Modified: Register FastMCP `rush_fix` endpoint)
- `src/rush/catalog.py` (Modified: Register `fix` tool specification)

### Test & Fixture Files
- `tests/test_fix.py` (New: Multi-engine auto-fix, `--dry-run` diff preview, path confinement, atomic rollback)
- `tests/fixtures/fix/unformatted.py` (New: Python formatting test fixture)
- `tests/fixtures/fix/unformatted.ts` (New: TypeScript formatting test fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_fix.py
def test_fix_path_traversal_rejection(tmp_path):
    tool = FixTool(repo_root=tmp_path)
    res = tool.run(paths=[Path("../../etc/shadow")], permissions=ExecutionPermissions.default())
    assert res.status == "failed"
    assert "outside repository boundary" in res.summary

def test_fix_dry_run_generates_diff_without_writing(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("x =  1\n", encoding="utf-8")
    tool = FixTool(repo_root=tmp_path)
    res = tool.run(paths=[f], permissions=ExecutionPermissions.default(), dry_run=True)
    assert f.read_text(encoding="utf-8") == "x =  1\n"
    assert res.diff != ""

def test_fix_atomic_rollback_on_broken_syntax(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def valid(): pass\n", encoding="utf-8")
    # Simulate an engine producing invalid syntax
    tool = FixTool(repo_root=tmp_path)
    res = tool.apply_with_rollback(f, replacement_code="def broken(:\n")
    assert res.status == "failed"
    assert f.read_text(encoding="utf-8") == "def valid(): pass\n"
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/fix.py` and adapter methods on `RuffEngine`, `BiomeEngine`, `ESLintEngine`, and `PrettierEngine`.

### 4.3 REFACTOR Phase
Ensure pre-fix file snapshots are stored in-memory for small files and tempfiles for large files, guaranteeing atomic rollback on error.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:20:00Z", "phase": 22, "tool": "rush_fix", "event": "fix_started", "files_count": 4, "dry_run": false}
{"timestamp": "2026-08-21T07:20:01Z", "phase": 22, "tool": "rush_fix", "event": "engine_fix_applied", "engine": "ruff", "file": "src/api.py", "rules_fixed": ["F401", "I001"]}
{"timestamp": "2026-08-21T07:20:02Z", "phase": 22, "tool": "rush_fix", "event": "fix_completed", "files_modified": 3, "residual_findings": 0}
```

---

## 6. Step-by-Step Task Specifications

### Task 22.1: Engine Auto-Fix Protocol (`src/rush/engines/base.py`)
```python
def run_fix(self, paths: list[Path], permissions: ExecutionPermissions) -> ToolResult:
    """Execute engine in auto-fix mode, returning modified files and residual findings."""
    return ToolResult(tool="fix", status="skipped", summary="Engine does not support automated fixing")
```

### Task 22.2: Core Fix Tool with Atomic Rollbacks (`src/rush/tools/fix.py`)
```python
from __future__ import annotations
from pathlib import Path
from rush.tools.base import BaseTool, ToolResult, ExecutionPermissions

class FixTool(BaseTool):
    name = "fix"
    
    def run(
        self,
        paths: list[Path],
        permissions: ExecutionPermissions,
        dry_run: bool = False,
        force: bool = False,
    ) -> ToolResult:
        """Confined auto-fix runner with pre-flight dirty checks and post-fix AST validation."""
        ...
```

### Task 22.3: Engine Fix Adapters (`src/rush/engines/*.py`)
- `RuffEngine`: `ruff format <paths>` and `ruff check --fix <paths>`
- `BiomeEngine`: `biome check --write <paths>`
- `ESLintEngine`: `eslint --fix <paths>`
- `PrettierEngine`: `prettier --write <paths>`

### Task 22.4: CLI & FastMCP Registrations
Register `rush fix` and `rush_fix` with `--dry-run`, `--force`, `--staged` flags.

---

## 7. Semantic Drift Review & Verification Gate

1. **Path Safety**: Reject any path outside `repo_root` with structured security error.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
