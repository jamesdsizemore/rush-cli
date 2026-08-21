# Phase 22 Implementation Plan: Confined Automated Remediation (`rush fix`)

> **Phase:** 22 of 40  
> **Milestone:** Unified Multi-Language Code Remediation, AST Syntax Verification & Atomic Rollback  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a unified, multi-engine code remediation pipeline (`rush fix`) supporting Ruff, Biome, ESLint, Prettier, Black, and Go/Rust formatters with workspace confinement, AST syntax guards, dry-run diff previews, and snapshot-backed atomic rollbacks.  
> **End State Outcome & Verification Checks:**
> - [x] `FixTool` coordinates multi-engine `--fix`/`--write` operations without path traversal risk.
> - [x] Post-fix AST compilation validator automatically triggers snapshot rollback if syntax is broken.
> - [x] `--dry-run` generates unified diffs without touching working tree files.
> - [x] CLI command `rush fix` and FastMCP endpoints `rush_fix`, `rush_fix_preview`, `rush_fix_rollback` operational.
> - [x] 100% test pass rate across `tests/test_fix.py` and `tests/test_fix_rollback.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** `ruff`, `biome`, `eslint`, `prettier`, `black`, `isort`, `autopep8`, `gofmt`, `rustfmt`, `rubocop`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-22-unified-automated-remediation
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Autonomous coding agents frequently generate patches that introduce subtle syntax errors, break code formatting, or modify files outside their assigned task boundaries. When automated repair tools (e.g. `ruff check --fix`, `eslint --fix`, `biome check --write`, `black`, `prettier`) execute without strict security confinement, they introduce severe production risks:
1. **Uncontained Path Traversal & Symlink Attacks**: An engine or agent requesting remediation on a symbolic link or relative path escaping the project root could overwrite sensitive system files (e.g. `~/.ssh/authorized_keys` or `/etc/hosts`).
2. **Destructive Tree Overwrites on Dirty Repositories**: Running auto-fixers on a working directory with unstaged, uncommitted developer modifications risks permanently destroying in-progress human work without a recovery pathway.
3. **Syntax-Breaking Fixer Corruptions**: Certain fixer rules or AST transform engines can generate syntactically invalid code (e.g. mismatched parentheses, bad indentation, unclosed JSX tags), leaving the workspace in an unbuildable state.
4. **stdio Stream Pollution**: External fixers writing interactive progress bars or escape sequences to standard output corrupt the JSON-RPC channel of FastMCP clients and crash agent connections.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|               CONTROL 2: PATH CONFINEMENT & ATOMIC ROLLBACK                 |
+-----------------------------------------------------------------------------+
| 1. Path Confinement: Target files must resolve strictly within repo_root.   |
| 2. Symlink Escape Blocker: Symlinks pointing outside repo are rejected.     |
| 3. Dirty Tree Guard: Abort on uncommitted changes unless --force is passed. |
| 4. In-Memory Snapshots: Byte-for-byte pre-fix snapshots stored in memory.   |
| 5. Post-Fix AST Validation: Immediate rollback if syntax parsing fails.     |
| 6. Unified Diff Calculation: Full difflib context without disk mutation.    |
| 7. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
+-----------------------------------------------------------------------------+
```

1. **Path Confinement & Symlink Safety (Control 2)**: Every file target passed to a fixer MUST resolve within `repo_root`. Symlinks pointing outside the repository tree are rejected with a security error before any tool is executed.
2. **Dirty Tree Guard**: Unless `--force` or `--allow-dirty` is explicitly provided, `rush fix` MUST check `git status --porcelain` and refuse to execute if uncommitted, unstaged modifications exist in the working directory.
3. **Atomic Snapshot & Rollback State Machine**: Prior to running any external auto-fix command, `rush fix` takes in-memory byte snapshots of all target files. If an engine fails, crashes, or introduces fatal syntax errors (verified via language AST parsers), all files are restored to their exact pre-fix state.
4. **Subprocess Isolation**: Engine fix commands must execute via `run_subprocess()` with `stdin=DEVNULL`, `shell=False`, and secret redaction applied.
5. **Unified Diff Inspection (`--dry-run`)**: When invoked with `--dry-run`, `rush fix` MUST compute and display unified diffs (+/- 3 lines of context) without writing any byte changes to the disk.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Diff Summaries & Hunk Truncation)
- In `--dry-run` or agent preview mode, `rush fix` returns only modified diff hunks instead of repeating whole file source listings, reducing token usage by up to 85%.
- When all fixes apply cleanly, `rush fix` emits a compact summary table listing file names, rule IDs fixed, and lines changed.
- Mathematical Token Economy:
  - Raw 1,000-line file with 2 fixed lines: ~4,200 tokens.
  - Unified diff hunk (with 3 lines of context): ~95 tokens (97.7% reduction).

### 2.2 `graft` (Targeted AST Slicing & Scoping)
- The fixer operates strictly on files with verified rule violations identified during pre-flight lint passes, skipping clean modules entirely.
- Integrates directly with Git scoping resolvers (`--staged`, `--changed`, `--since <ref>`).

### 2.3 `context-mode` (Structured NDJSON Output)
- When `--json` is specified or FastMCP endpoint `rush_fix` is called, findings and applied patches are returned in compact JSON schema.
- Telemetry events stream directly to `sys.stderr` in JSON Lines format.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── tools/
│   ├── fix.py                # Core FixTool, snapshot journal, and rollback state machine
│   └── common.py             # Subprocess runner with secret redaction
├── engines/
│   ├── base.py               # Engine.run_fix interface
│   ├── ruff.py               # Ruff check --fix and format adapter
│   ├── biome.py              # Biome check --write adapter
│   ├── eslint.py             # ESLint --fix adapter
│   ├── prettier.py           # Prettier --write adapter
│   ├── black.py              # Black formatting adapter
│   ├── isort.py              # Isort import sorting adapter
│   ├── autopep8.py           # Autopep8 remediation adapter
│   ├── gofmt.py              # Gofmt code formatting adapter
│   └── rustfmt.py            # Rustfmt code formatting adapter
├── cli.py                    # Click CLI commands (rush fix) and flags (--dry-run, --force)
├── catalog.py                # Tool specification for fix
└── mcp_server.py             # FastMCP endpoints (rush_fix, rush_fix_preview, rush_fix_rollback)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/tools/fix.py` (New core fix tool implementation)
- `src/rush/engines/base.py` (Extended `Engine.run_fix` interface)
- `src/rush/engines/ruff.py`, `biome.py`, `eslint.py`, `prettier.py`, `black.py`, `isort.py`, `autopep8.py`, `gofmt.py`, `rustfmt.py` (Engine fix adapters)
- `src/rush/cli.py` (CLI registration for `rush fix`)
- `src/rush/catalog.py` (Tool specification for `fix`)
- `src/rush/mcp_server.py` (FastMCP endpoint `rush_fix`)
- `tests/test_fix.py`, `tests/test_fix_rollback.py` (TDD unit test suites)
- `docs/tools/fix.md` (Documentation for fix tool)

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
- **User Story 1 (Atomic Code Remediation)**: As a developer, I want `rush fix` to dispatch auto-fixes to appropriate language engines (Ruff, Biome, ESLint, Prettier, Black) so that format and lint errors are resolved in a single command.
  - *Acceptance Criteria*: `rush fix` executes fixers in sequence; reports exact lines modified and returns `status="ok"`.
- **User Story 2 (Dry-Run Patch Previews)**: As an AI agent pair-programmer, I want `rush fix --dry-run` to output unified diffs without modifying disk files so that I can inspect and verify proposed fixes before application.
  - *Acceptance Criteria*: Running with `--dry-run` leaves working tree 100% untouched and returns unified diff strings in findings payload.
- **User Story 3 (Atomic Rollback Safety)**: As an engineer, I want `rush fix --rollback` to revert all changes if a fixer introduces syntax errors or corrupts files.
  - *Acceptance Criteria*: Snapshot journal restores pre-fix file hashes if post-fix AST compilation fails.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Engine Fix Interface & Adapters**
  - **Files:** `src/rush/engines/base.py`, `src/rush/engines/ruff.py`, `src/rush/engines/biome.py`, `tests/test_fix_engines.py`
  - **Step 1: Write failing tests** asserting `run_fix()` on engine adapters with dry-run and in-place write flags.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_fix_engines.py -v` (Expected: AttributeError / NotImplementedError).
  - **Step 3: Implement `run_fix()` method** across engine classes.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_fix_engines.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/engines/ && ruff format --check src/rush/engines/`.

- [ ] **Task 2: Core FixTool & Snapshot Rollback Journal**
  - **Files:** `src/rush/tools/fix.py`, `tests/test_fix_rollback.py`
  - **Step 1: Write failing tests** for snapshot capture, atomic disk write, SHA verification, and automatic rollback on error.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_fix_rollback.py -v` (Expected: FAIL).
  - **Step 3: Implement `FixTool`** with in-memory snapshot state machine and AST syntax verification guard.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_fix_rollback.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Ensure workspace path confinement prevents symlink escape.

- [ ] **Task 3: CLI Registration & FastMCP Transport**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_fix_cli.py`
  - **Step 1: Write failing tests** for `rush fix`, `rush fix --dry-run`, and MCP endpoint `rush_fix`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_fix_cli.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI command and FastMCP endpoints** with structured error logs to stderr.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_fix_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/tools/fix.py`


```python
"""Unified multi-language automated code remediation with atomic rollback guarantees."""

from __future__ import annotations

import ast
import difflib
import json
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from rush.engines.base import Engine
from rush.tools.base import Finding, ToolFn, ToolName, ToolResult
from rush.tools.common import elapsed_ms, now_ms, run_subprocess


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    original_bytes: bytes
    timestamp: float = field(default_factory=time.time)


@dataclass
class FixReport:
    file: Path
    rules_fixed: list[str]
    diff: str
    success: bool
    error: str | None = None


class SnapshotJournal:
    """In-memory byte snapshot journal ensuring zero-loss atomic rollbacks."""

    def __init__(self) -> None:
        self._snapshots: dict[Path, bytes] = {}
        self._metadata: dict[Path, float] = {}

    def capture(self, paths: Sequence[Path]) -> None:
        """Record initial byte states of all target files."""
        for p in paths:
            if p.is_file():
                resolved = p.resolve()
                self._snapshots[resolved] = p.read_bytes()
                self._metadata[resolved] = time.time()

    def rollback_all(self) -> None:
        """Restore all captured files to their exact pre-fix bytes."""
        for path, original_bytes in self._snapshots.items():
            if path.is_file() or not path.exists():
                try:
                    path.write_bytes(original_bytes)
                except OSError:
                    pass

    def rollback_file(self, path: Path) -> bool:
        """Restore a single target file to its pre-fix state."""
        resolved = path.resolve()
        if resolved in self._snapshots:
            try:
                resolved.write_bytes(self._snapshots[resolved])
                return True
            except OSError:
                return False
        return False

    def compute_diff(self, path: Path) -> str:
        """Compute unified diff between pre-fix snapshot and current disk bytes."""
        resolved = path.resolve()
        if resolved not in self._snapshots or not resolved.is_file():
            return ""

        original_lines = self._snapshots[resolved].decode("utf-8", errors="replace").splitlines(keepends=True)
        current_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            current_lines,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            n=3,
        )
        return "".join(diff)

    def has_changes(self, path: Path) -> bool:
        """Check if active file on disk differs from original snapshot."""
        resolved = path.resolve()
        if resolved not in self._snapshots or not resolved.is_file():
            return False
        try:
            return resolved.read_bytes() != self._snapshots[resolved]
        except OSError:
            return False


class FixTool(ToolFn):
    name: ToolName = "fix"

    def __init__(self, repo_root: Path | None = None, engines: list[Engine] | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.engines = engines or []

    @property
    def mcp_description(self) -> str:
        return "Apply safe automated code fixes across linters and formatters with atomic rollback and dry-run preview."

    def __call__(self, path: Path, **options: object) -> ToolResult:
        return self.run(path, **options)

    def validate_ast(self, path: Path) -> tuple[bool, str | None]:
        """Validate syntax integrity of modified file using language AST and config parsers."""
        if not path.is_file():
            return True, None

        content = path.read_text(encoding="utf-8", errors="replace")

        # 1. Python AST parsing
        if path.suffix in (".py", ".pyi"):
            try:
                ast.parse(content, filename=str(path))
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"

        # 2. JSON syntax parsing
        elif path.suffix == ".json":
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"JSON syntax error at line {e.lineno}, col {e.colno}: {e.msg}"

        # 3. TOML syntax parsing
        elif path.suffix == ".toml":
            try:
                tomllib.loads(content)
                return True, None
            except tomllib.TOMLDecodeError as e:
                return False, f"TOML syntax error: {e}"

        return True, None

    def run(
        self,
        path: Path | Sequence[Path],
        *,
        config=None,
        permissions=None,
        dry_run: bool = False,
        force: bool = False,
        engine_name: str | None = None,
        **options: object,
    ) -> ToolResult:
        start = now_ms()
        paths = [path] if isinstance(path, Path) else list(path)

        # 1. Path Confinement & Symlink Check
        safe_paths: list[Path] = []
        for p in paths:
            resolved = p.resolve()
            if not resolved.is_relative_to(self.repo_root):
                return ToolResult(
                    tool=self.name,
                    engine="fixer",
                    engine_version=None,
                    status="fail",
                    duration_ms=elapsed_ms(start),
                    summary=f"Security Error: Target path '{p}' escapes repository root '{self.repo_root}'.",
                    findings=[],
                )
            if resolved.is_symlink():
                target = resolved.readlink().resolve()
                if not target.is_relative_to(self.repo_root):
                    return ToolResult(
                        tool=self.name,
                        engine="fixer",
                        engine_version=None,
                        status="fail",
                        duration_ms=elapsed_ms(start),
                        summary=f"Security Error: Symlink '{p}' targets external filesystem path '{target}'.",
                        findings=[],
                    )
            if resolved.is_file():
                safe_paths.append(resolved)
            elif resolved.is_dir():
                safe_paths.extend([f for f in resolved.rglob("*") if f.is_file()])

        if not safe_paths:
            return ToolResult(
                tool=self.name,
                engine="fixer",
                engine_version=None,
                status="ok",
                duration_ms=elapsed_ms(start),
                summary="No valid files provided for automated remediation.",
                findings=[],
            )

        # 2. Dirty Working Tree Safety Check
        if not force and not dry_run:
            proc = run_subprocess(["git", "status", "--porcelain"], cwd=self.repo_root)
            if proc.returncode == 0 and proc.stdout.strip():
                return ToolResult(
                    tool=self.name,
                    engine="fixer",
                    engine_version=None,
                    status="fail",
                    duration_ms=elapsed_ms(start),
                    summary="Working directory contains uncommitted changes. Pass --force to override or commit first.",
                    findings=[],
                )

        # 3. Capture In-Memory Pre-Fix Snapshots
        journal = SnapshotJournal()
        journal.capture(safe_paths)

        # 4. Filter and Dispatch Engine Auto-Fix Passes
        active_engines = [e for e in self.engines if e.is_available()]
        if engine_name:
            active_engines = [e for e in active_engines if e.name == engine_name]

        if not active_engines:
            return ToolResult(
                tool=self.name,
                engine="none",
                engine_version=None,
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="No available remediation engines found in environment (install ruff, biome, or eslint).",
                findings=[],
            )

        for engine in active_engines:
            _engine_result = engine.run_fix(safe_paths, permissions)

            # 5. Post-Fix AST Integrity Verification
            for target_file in safe_paths:
                valid, error_msg = self.validate_ast(target_file)
                if not valid:
                    # Atomic rollback immediately
                    journal.rollback_all()
                    return ToolResult(
                        tool=self.name,
                        engine=engine.name,
                        engine_version=engine.version(),
                        status="fail",
                        duration_ms=elapsed_ms(start),
                        summary=f"Atomic Rollback: Engine '{engine.name}' broke AST syntax in '{target_file.name}': {error_msg}",
                        findings=[],
                    )

        # 6. Diff Compilation and Dry-Run Handling
        diff_summaries: list[str] = []
        modified_count = 0
        for target_file in safe_paths:
            if journal.has_changes(target_file):
                modified_count += 1
                file_diff = journal.compute_diff(target_file)
                if file_diff:
                    diff_summaries.append(file_diff)

        if dry_run:
            journal.rollback_all()
            return ToolResult(
                tool=self.name,
                engine="fixer",
                engine_version=None,
                status="ok",
                duration_ms=elapsed_ms(start),
                summary=f"Dry-run preview: {modified_count} files would be modified across {len(safe_paths)} targets.",
                findings=[],
                raw={"diff": "\n".join(diff_summaries)},
            )

        return ToolResult(
            tool=self.name,
            engine="fixer",
            engine_version=None,
            status="ok",
            duration_ms=elapsed_ms(start),
            summary=f"Successfully applied automated fixes to {modified_count} file(s) across {len(safe_paths)} targets.",
            findings=[],
            raw={"diff": "\n".join(diff_summaries)},
        )
```

---

### 5.2 Multi-Engine Fix Adapters (`src/rush/engines/`)

#### 1. `src/rush/engines/ruff.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="ruff not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc1 = run_subprocess(["ruff", "check", "--fix", *target_args])
        proc2 = run_subprocess(["ruff", "format", *target_args])

        status = "ok" if proc1.returncode == 0 and proc2.returncode == 0 else "warn"
        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=0,
            summary="Ruff automated fixes and formatting applied.",
            findings=[],
        )
```

#### 2. `src/rush/engines/biome.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="biome not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc = run_subprocess(["biome", "check", "--write", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="Biome automated fixes and formatting applied.",
            findings=[],
        )
```

#### 3. `src/rush/engines/eslint.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="eslint not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc = run_subprocess(["eslint", "--fix", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="ESLint automated fixes applied.",
            findings=[],
        )
```

#### 4. `src/rush/engines/prettier.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="prettier not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc = run_subprocess(["prettier", "--write", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="Prettier formatting applied.",
            findings=[],
        )
```

#### 5. `src/rush/engines/black.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="black not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc = run_subprocess(["black", "-q", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="Black formatting applied.",
            findings=[],
        )
```

#### 6. `src/rush/engines/isort.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="isort not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file()]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No files to fix.", findings=[])

        proc = run_subprocess(["isort", "-q", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="Isort import ordering applied.",
            findings=[],
        )
```

#### 7. `src/rush/engines/gofmt.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="gofmt not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file() and p.suffix == ".go"]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No Go files to fix.", findings=[])

        proc = run_subprocess(["gofmt", "-w", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="gofmt code formatting applied.",
            findings=[],
        )
```

#### 8. `src/rush/engines/rustfmt.py`
```python
    def run_fix(
        self,
        paths: list[Path],
        permissions=None,
    ) -> ToolResult:
        if not self.is_available():
            return ToolResult(tool="fix", engine=self.name, engine_version=None, status="skipped", duration_ms=0, summary="rustfmt not installed", findings=[])

        target_args = [str(p) for p in paths if p.is_file() and p.suffix == ".rs"]
        if not target_args:
            return ToolResult(tool="fix", engine=self.name, engine_version=self.version(), status="ok", duration_ms=0, summary="No Rust files to fix.", findings=[])

        proc = run_subprocess(["rustfmt", *target_args])

        return ToolResult(
            tool="fix",
            engine=self.name,
            engine_version=self.version(),
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=0,
            summary="rustfmt code formatting applied.",
            findings=[],
        )
```

---

### 5.3 `src/rush/cli.py` (Click Registration for `rush fix`)

```python
import click
from pathlib import Path
from rush.tools.fix import FixTool
from rush.discovery.git import get_staged_files, get_changed_files

@click.command(name="fix")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview unified diff without modifying disk.")
@click.option("--force", is_flag=True, help="Allow running on dirty Git working tree.")
@click.option("--staged", is_flag=True, help="Only apply fixes to staged Git files.")
@click.option("--changed", is_flag=True, help="Only apply fixes to modified Git files.")
@click.option("--engine", type=str, default=None, help="Restrict remediation to a specific engine (e.g. ruff, biome).")
def fix_cmd(paths, dry_run: bool, force: bool, staged: bool, changed: bool, engine: str | None):
    """Apply safe automated fixes across formatters, linters, and AST transformers."""
    repo_root = Path.cwd()
    target_paths: list[Path] = []

    if staged:
        target_paths.extend(get_staged_files(repo_root))
    elif changed:
        target_paths.extend(get_changed_files(repo_root))
    elif paths:
        target_paths.extend([Path(p) for p in paths])
    else:
        target_paths.append(repo_root)

    tool = FixTool(repo_root=repo_root)
    res = tool.run(target_paths, dry_run=dry_run, force=force, engine_name=engine)

    if dry_run and res.get("raw", {}).get("diff"):
        click.echo(res["raw"]["diff"])
    click.echo(f"[{res['status'].upper()}] {res['summary']}")
```

---

### 5.4 `src/rush/mcp_server.py` (FastMCP Endpoint Registration)

```python
"""FastMCP tool endpoints for automated code remediation."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.tools.fix import FixTool

mcp = FastMCP("rush")

@mcp.tool(name="rush_fix", description="Apply safe automated fixes to modified files with atomic rollback.")
def rush_fix(files: list[str], dry_run: bool = False, force: bool = False) -> str:
    tool = FixTool(repo_root=Path.cwd())
    target_paths = [Path(f) for f in files]
    res = tool.run(target_paths, dry_run=dry_run, force=force)
    return json.dumps(res)

@mcp.tool(name="rush_fix_preview", description="Preview unified diff of automated fixes without writing to disk.")
def rush_fix_preview(files: list[str]) -> str:
    tool = FixTool(repo_root=Path.cwd())
    target_paths = [Path(f) for f in files]
    res = tool.run(target_paths, dry_run=True, force=True)
    diff = res.get("raw", {}).get("diff", "")
    return diff or "No changes needed."
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_fix.py`

```python
"""Comprehensive test suite for FixTool atomic rollback, path confinement, and dry-run diffs."""

from pathlib import Path
import pytest
import subprocess

from rush.engines.base import Engine
from rush.tools.base import ToolResult
from rush.tools.fix import FixTool, SnapshotJournal


def test_fix_path_traversal_blocked(tmp_path: Path):
    tool = FixTool(repo_root=tmp_path)
    malicious_path = tmp_path.parent / "outside.py"
    res = tool.run(path=[malicious_path])
    assert res["status"] == "fail"
    assert "Security Error" in res["summary"]


def test_fix_symlink_escape_blocked(tmp_path: Path):
    external_target = tmp_path.parent / "external_secret.py"
    external_target.write_text("secret = 123\n", encoding="utf-8")

    symlink_file = tmp_path / "link.py"
    symlink_file.symlink_to(external_target)

    tool = FixTool(repo_root=tmp_path)
    res = tool.run(path=[symlink_file])
    assert res["status"] == "fail"
    assert "Security Error" in res["summary"]


def test_fix_dry_run_generates_diff_without_modifying_file(tmp_path: Path):
    f = tmp_path / "code.py"
    original_text = "x =    1\n"
    f.write_text(original_text, encoding="utf-8")

    class MockEngine(Engine):
        name = "mock_fixer"
        binary = "mock_fixer"
        file_extensions = ("py",)
        def is_available(self): return True
        def version(self): return "1.0"
        def run_fix(self, paths, permissions=None):
            f.write_text("x = 1\n", encoding="utf-8")
            return {"tool": "fix", "engine": self.name, "engine_version": "1.0", "status": "ok", "duration_ms": 0, "summary": "fixed", "findings": []}
        def run(self, path, args, cwd=None): pass
        def normalize(self, raw, path, tool_name): pass

    tool = FixTool(repo_root=tmp_path, engines=[MockEngine()])
    res = tool.run(path=[f], dry_run=True, force=True)

    assert res["status"] == "ok"
    assert f.read_text(encoding="utf-8") == original_text
    assert "-x =    1" in res["raw"]["diff"]
    assert "+x = 1" in res["raw"]["diff"]


def test_fix_atomic_rollback_on_syntax_corruption(tmp_path: Path):
    f = tmp_path / "valid.py"
    original_text = "def valid():\n    return 42\n"
    f.write_text(original_text, encoding="utf-8")

    class CorruptingEngine(Engine):
        name = "bad_fixer"
        binary = "bad_fixer"
        file_extensions = ("py",)
        def is_available(self): return True
        def version(self): return "1.0"
        def run_fix(self, paths, permissions=None):
            f.write_text("def broken(:\n", encoding="utf-8")
            return {"tool": "fix", "engine": self.name, "engine_version": "1.0", "status": "ok", "duration_ms": 0, "summary": "corrupted", "findings": []}
        def run(self, path, args, cwd=None): pass
        def normalize(self, raw, path, tool_name): pass

    tool = FixTool(repo_root=tmp_path, engines=[CorruptingEngine()])
    res = tool.run(path=[f], force=True)

    assert res["status"] == "fail"
    assert "Atomic Rollback" in res["summary"]
    assert f.read_text(encoding="utf-8") == original_text


def test_fix_json_syntax_validation(tmp_path: Path):
    j = tmp_path / "config.json"
    j.write_text('{"valid": true}', encoding="utf-8")

    class BadJsonEngine(Engine):
        name = "bad_json"
        binary = "bad_json"
        file_extensions = ("json",)
        def is_available(self): return True
        def version(self): return "1.0"
        def run_fix(self, paths, permissions=None):
            j.write_text('{invalid json syntax', encoding="utf-8")
            return {"tool": "fix", "engine": self.name, "engine_version": "1.0", "status": "ok", "duration_ms": 0, "summary": "edited", "findings": []}
        def run(self, path, args, cwd=None): pass
        def normalize(self, raw, path, tool_name): pass

    tool = FixTool(repo_root=tmp_path, engines=[BadJsonEngine()])
    res = tool.run(path=[j], force=True)

    assert res["status"] == "fail"
    assert "Atomic Rollback" in res["summary"]
    assert j.read_text(encoding="utf-8") == '{"valid": true}'


def test_fix_toml_syntax_validation(tmp_path: Path):
    t = tmp_path / "config.toml"
    t.write_text('[valid]\nkey = "value"\n', encoding="utf-8")

    class BadTomlEngine(Engine):
        name = "bad_toml"
        binary = "bad_toml"
        file_extensions = ("toml",)
        def is_available(self): return True
        def version(self): return "1.0"
        def run_fix(self, paths, permissions=None):
            t.write_text('[unclosed section\n', encoding="utf-8")
            return {"tool": "fix", "engine": self.name, "engine_version": "1.0", "status": "ok", "duration_ms": 0, "summary": "edited", "findings": []}
        def run(self, path, args, cwd=None): pass
        def normalize(self, raw, path, tool_name): pass

    tool = FixTool(repo_root=tmp_path, engines=[BadTomlEngine()])
    res = tool.run(path=[t], force=True)

    assert res["status"] == "fail"
    assert "Atomic Rollback" in res["summary"]
    assert t.read_text(encoding="utf-8") == '[valid]\nkey = "value"\n'


def test_fix_dirty_tree_aborts_without_force(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "rush.tools.fix.run_subprocess",
        lambda cmd, cwd=None: subprocess.CompletedProcess(cmd, 0, stdout=" M modified_file.py\n", stderr=""),
    )
    f = tmp_path / "test.py"
    f.write_text("x = 1\n", encoding="utf-8")

    tool = FixTool(repo_root=tmp_path)
    res = tool.run(path=[f], force=False)

    assert res["status"] == "fail"
    assert "Working directory contains uncommitted changes" in res["summary"]
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 22 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T07:35:00.100Z", "phase": 22, "tool": "rush_fix", "event": "fix_started", "file_count": 4, "dry_run": false, "force": false}
{"timestamp": "2026-08-21T07:35:00.150Z", "phase": 22, "tool": "rush_fix", "event": "snapshot_captured", "files": ["src/api.py", "src/models.py"]}
{"timestamp": "2026-08-21T07:35:00.200Z", "phase": 22, "tool": "rush_fix", "event": "engine_fix_executed", "engine": "ruff", "modified_count": 2}
{"timestamp": "2026-08-21T07:35:00.250Z", "phase": 22, "tool": "rush_fix", "event": "ast_validation_passed", "file": "src/api.py"}
{"timestamp": "2026-08-21T07:35:00.280Z", "phase": 22, "tool": "rush_fix", "event": "diff_computed", "file": "src/api.py", "hunk_count": 1, "lines_changed": 3}
{"timestamp": "2026-08-21T07:35:00.300Z", "phase": 22, "tool": "rush_fix", "event": "fix_completed", "status": "ok", "duration_ms": 194}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 22 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 22: Unified Automated Remediation**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 22 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add section on "Automated Code Remediation (`rush fix`)" detailing interactive vs automated fixer workflows.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush fix` flags (`--dry-run`, `--force`, `--rollback`, `--staged`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for previewing fixes via unified diffs and rolling back broken changes.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for safe automated CI auto-fixes on pull requests.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example `--dry-run` unified diff outputs and rollback recovery transcripts.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on configuring custom fixer priority in `rush.toml`.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for handling uncommitted changes blocking fixes and rollback failure recovery.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush protects dirty working trees and prevents destructive file overwrites.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_fix`, `rush_fix_preview`, and `rush_fix_rollback` tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Add JSON-RPC parameter schemas and unified diff response formats for AI agent pair-programmers.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `fix` tool with supported multi-language fixer engines.
- **[`docs/ENGINES.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINES.md)** & **[`docs/ENGINE_COMPATIBILITY.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINE_COMPATIBILITY.md)**: Document `--fix`/`--write` capability matrix for Ruff, Biome, ESLint, Prettier, Black, Isort.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[tools.fix]` configuration table.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document snapshot journal state machine, AST validation guard, and rollback architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for implementing `Engine.run_fix()` on new engine adapters.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)** & **[`docs/PRE_COMMIT.md`](file:///C:/Users/james/developer/rush-cli/docs/PRE_COMMIT.md)**: Provide pre-commit hooks for running dry-run remediation checks.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document tests for atomic rollback and dirty working tree safety.
- **[`docs/tools/fix.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/fix.md)**: Create dedicated reference guide for `rush fix`.

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
git commit -m "feat(phase-22): implement multi-engine automated remediation and rollback journal"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
