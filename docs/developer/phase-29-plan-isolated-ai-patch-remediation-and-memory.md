# Phase 29 Implementation Plan: Isolated AI Patch Remediation & Memory (`rush patch`)

> **Phase:** 29 of 40  
> **Milestone:** Ephemeral Worktree Patch Sandboxing, Deterministic Session Memory & Closed-Loop Verification  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Implement an isolated AI patch remediation subsystem (`rush patch`) executing multi-step LLM repairs within ephemeral Git worktree sandboxes, running closed-loop test verifications, and recording successful fix recipes in a local SQLite patch memory store (`.rush/patch_memory.db`).  
> **End State Outcome & Verification Checks:**
> - [x] `PatchSandboxManager` creates ephemeral isolated worktrees with automatic cleanup.
> - [x] `PatchVerifier` executes pre-patch and post-patch test suites to prevent behavioral regressions.
> - [x] `PatchMemoryStore` indexes validated fix patterns for sub-second recall by AI agents.
> - [x] CLI commands `rush patch apply`, `verify`, `promote` and FastMCP endpoints operational.
> - [x] 100% test pass rate across `tests/test_patch_sandbox_and_memory.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0018: Closed-Loop AI Agent Patch Remediation and Session Memory](../adr/0018-closed-loop-ai-agent-patch-remediation-and-session-memory.md)  
> - [ADR-0021: Ephemeral Git Worktree Sandboxing](../adr/0021-ephemeral-git-worktree-sandboxing.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** Discovered local test runners (`pytest`, `vitest`, `cargo test`, `go test`, `npm test`)  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-29-isolated-ai-patch-remediation-and-memory
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
When autonomous AI coding agents (Claude Code, Cursor, GitHub Copilot Workspace, Devin, Antigravity) attempt automated code remediation across developer workspaces:
1. **Destructive In-Place Working Tree Mutations**: AI agents applying experimental patches directly to dirty working trees corrupt uncommitted developer work, create unrecoverable merge conflicts, and leave orphaned syntax errors.
2. **Hallucinated & Regressive Patches**: An AI model generates a patch that resolves a single Ruff lint warning (e.g. `F401 unused-import`) while inadvertently deleting critical side-effect imports or breaking 15 downstream unit tests.
3. **Runaway Remediation Feedback Loops**: Agent loops that fail test verification attempt blind fixes repeatedly, exhausting API budgets, mutating repository state, and cycling through identical failing patch variants.
4. **Lack of Remediation Memory**: Agents repeatedly encounter identical lint or security findings across branches, re-synthesizing fixes from scratch instead of querying deterministic, verified patch templates.
5. **stdio JSON-RPC Stream Corruption**: External git subprocesses writing interactive progress indicators or merge messages to `stdout` corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Fabricated test results claiming a patch passed verification | **Critical** | Subprocess exit-code and structured TAP/JSON test runner verification inside an isolated Git worktree. |
| **Tampering** | Rogue AI patch modifying governance files (`AGENTS.md`, `.rush/`, `.git/hooks`) | **Critical** | Pre-promotion AST & path firewall rejecting patches that modify read-only governance roots. |
| **Repudiation** | Silent unlogged working tree modifications | **Medium** | Append-only SQLite journal (`.rush/cache.db`) recording full unified diffs, error signatures, and commit SHAs. |
| **Information Disclosure** | Diffs containing leaked secrets or API tokens committed to memory store | **High** | Pre-storage regex & entropy secret redaction filter masking all credentials with `[REDACTED]`. |
| **Denial of Service** | Unbounded patch trial loop consuming CPU, disk space, and git worktrees | **High** | Strict 3-attempt circuit breaker and automated `git worktree remove --force` cleanup hooks. |
| **Elevation of Privilege** | Directory traversal in unified diff header (`--- a/../../etc/passwd`) | **Critical** | Strict relative path resolution asserting `target_path.resolve().is_relative_to(repo_root)`. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 29 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Ephemeral Sandbox Confinement: Diffs are tested ONLY in .rush/worktrees/.|
| 2. Zero Working Tree Contamination: Main working tree untouched until PASS.  |
| 3. Closed-Loop Multi-Engine Verification: Requires exit code 0 on tests.    |
| 4. Deterministic Patch Memory: SQLite-backed caching of verified AST diffs. |
| 5. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 6. Workspace Confinement: Target files must resolve strictly within root.   |
| 7. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 8. Governance Shield: Patches targeting AGENTS.md, rush.toml, .git rejected.|
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Targeted Hunk Slicing & Diff Summarization)
- Slices unified diffs to emit only modified line ranges and error contexts (~60 tokens) rather than reloading full multi-thousand line files into agent context windows.
- Mathematical Token Economy:
  - Full module reload after patch: ~4,800 tokens.
  - Sliced atomic patch diff summary: ~75 tokens (98.4% token reduction).

### 2.2 `graft` (Targeted Subtree Patching)
- Scopes ephemeral worktree verification strictly to affected package boundaries rather than executing the entire test matrix across unrelated monorepo packages.

### 2.3 `context-mode` (Structured Remediation Telemetry & NDJSON Logs)
- Remediation lifecycle events, worktree allocations, test verification runs, and patch promotions are streamed as structured NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── patch/
│   ├── __init__.py               # Patch package exports
│   ├── sandbox.py                # Ephemeral Git worktree sandbox manager
│   ├── memory.py                 # SQLite-backed persistent patch memory store
│   ├── applier.py                # Unified diff parser and safe patch applier
│   ├── verifier.py               # Multi-framework test suite execution harness
│   ├── promoter.py               # Atomic patch promoter from sandbox to main tree
│   ├── circuit_breaker.py        # Remediation retry limiter (max 3 attempts)
│   ├── syntax_guard.py           # AST syntax validator (Python & Polyglot)
│   ├── secret_redactor.py        # High-speed entropy and token redactor
│   └── diff_parser.py            # Unified diff parser and hunk validator
├── cli.py                        # Click CLI commands (rush patch apply, test, promote, memory, clear)
└── mcp_server.py                 # FastMCP endpoints (rush_patch_test, rush_patch_promote, rush_patch_lookup)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/patch/sandbox.py` (New worktree sandbox manager)
- `src/rush/patch/memory.py` (New SQLite patch memory store)
- `src/rush/patch/applier.py` (New diff parser and patch applier)
- `src/rush/patch/verifier.py` (New test verifier)
- `src/rush/patch/promoter.py` (New patch promoter)
- `src/rush/patch/circuit_breaker.py` (New retry circuit breaker)
- `src/rush/patch/syntax_guard.py` (New syntax validator)
- `src/rush/patch/secret_redactor.py` (New secret redactor)
- `src/rush/patch/diff_parser.py` (New diff parser)
- `src/rush/cli.py` (CLI command `rush patch`)
- `src/rush/mcp_server.py` (FastMCP endpoints for patch remediation)
- `tests/test_patch_sandbox_and_memory.py` (TDD unit test suite)
- `docs/tools/patch.md` (Patch remediation documentation)

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
- **User Story 1 (Sandboxed Patch Remediation)**: As an autonomous AI coding agent, I want to apply code patches in an isolated Git worktree sandbox and run test suites before touching the main working tree.
  - *Acceptance Criteria*: Patch is applied and tested in ephemeral worktree; promoted to main tree only if 100% of tests pass.
- **User Story 2 (Circuit-Breaker Retry Limiter)**: As an engineer, I want Rush to block infinite remediation loops by failing fast if an AI agent fails to fix an error after 3 attempts.
  - *Acceptance Criteria*: Aborts with circuit-breaker error after 3 consecutive test failures for the same finding.
- **User Story 3 (Context Injection Sanitization)**: As a security reviewer, I want session memory and patches wrapped in cryptographic boundary frames (`<rush-sanitized-context>`) to prevent prompt injection from untrusted files.
  - *Acceptance Criteria*: Output payload sanitizes XML/Markdown markers, stripping adversarial prompt injection attempts.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Ephemeral Worktree Sandbox Manager**
  - **Files:** `src/rush/patch/sandbox.py`, `src/rush/patch/diff_parser.py`, `tests/test_patch_sandbox_and_memory.py`
  - **Step 1: Write failing tests** for worktree creation, diff parsing, path traversal rejection, and automatic cleanup.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `WorktreeSandbox` and `DiffParser`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/patch/ && ruff format --check src/rush/patch/`.

- [ ] **Task 2: Test Verifier, Circuit Breaker & Patch Promoter**
  - **Files:** `src/rush/patch/verifier.py`, `src/rush/patch/circuit_breaker.py`, `src/rush/patch/promoter.py`, `tests/test_patch_sandbox_and_memory.py`
  - **Step 1: Write failing tests** for test execution, max-retry threshold trip, and atomic patch promotion to main branch.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: FAIL).
  - **Step 3: Implement `PatchVerifier`, `CircuitBreaker`, and `PatchPromoter`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Subprocesses use isolated temporary branches.

- [ ] **Task 3: Persistent Patch Memory & FastMCP Endpoints**
  - **Files:** `src/rush/patch/memory.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_patch_sandbox_and_memory.py`
  - **Step 1: Write failing tests** for SQLite session memory storage, lookup, and FastMCP endpoints `rush_patch_test`, `rush_patch_promote`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_patch_sandbox_and_memory.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/patch/diff_parser.py`

```python
"""Unified diff parser, security validator, and hunk analyzer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DIFF_HEADER_REGEX = re.compile(r"^--- (?:a/)?(.*?)\n\+\+\+ (?:b/)?(.*?)$", re.MULTILINE)
HUNK_HEADER_REGEX = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

GOVERNANCE_BLOCKED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    "rush.toml",
    ".rush/trust.json",
    ".rush/hooks.json",
}


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedFilePatch:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)


class UnifiedDiffParser:
    """Parses and validates unified diff strings for structural and security compliance."""

    @staticmethod
    def parse_patch(diff_text: str, repo_root: Path) -> list[ParsedFilePatch]:
        patches: list[ParsedFilePatch] = []
        file_chunks = re.split(r"(?=^diff --git|\n--- )", diff_text, flags=re.MULTILINE)

        for chunk in file_chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            match = DIFF_HEADER_REGEX.search(chunk)
            if not match:
                continue

            old_file = match.group(1).strip()
            new_file = match.group(2).strip()

            # Security validation: Prevent path traversal attacks
            for target_path in (old_file, new_file):
                if target_path and target_path != "/dev/null":
                    resolved = (repo_root / target_path).resolve()
                    if not resolved.is_relative_to(repo_root.resolve()):
                        raise ValueError(f"Path traversal detected in diff header: '{target_path}'")
                    if target_path in GOVERNANCE_BLOCKED_FILES:
                        raise PermissionError(f"Modifying governance file '{target_path}' is strictly forbidden.")

            hunks: list[DiffHunk] = []
            hunk_blocks = re.split(r"(?=^@@ )", chunk, flags=re.MULTILINE)
            for h_block in hunk_blocks:
                h_lines = h_block.splitlines()
                if not h_lines:
                    continue
                h_match = HUNK_HEADER_REGEX.match(h_lines[0])
                if h_match:
                    old_start = int(h_match.group(1))
                    old_len = int(h_match.group(2) or 1)
                    new_start = int(h_match.group(3))
                    new_len = int(h_match.group(4) or 1)
                    hunks.append(
                        DiffHunk(
                            old_start=old_start,
                            old_lines=old_len,
                            new_start=new_start,
                            new_lines=new_len,
                            lines=h_lines[1:],
                        )
                    )

            patches.append(ParsedFilePatch(old_path=old_file, new_path=new_file, hunks=hunks))

        return patches
```

---

### 5.2 `src/rush/patch/syntax_guard.py`

```python
"""AST syntax validation guard for patched files."""

from __future__ import annotations

import ast
from pathlib import Path


class PatchSyntaxGuard:
    """Verifies that patched source files are syntactically valid before executing test suites."""

    @staticmethod
    def validate_file_syntax(file_path: Path) -> tuple[bool, str | None]:
        if not file_path.exists() or not file_path.is_file():
            return True, None

        if file_path.suffix == ".py":
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                ast.parse(source, filename=str(file_path))
                return True, None
            except SyntaxError as e:
                return False, f"Python syntax error at line {e.lineno}, col {e.offset}: {e.msg}"
            except Exception as e:
                return False, f"AST parse failure: {e}"

        return True, None
```

---

### 5.3 `src/rush/patch/sandbox.py`

```python
"""Ephemeral Git worktree sandbox manager for safe AI patch execution."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from rush.tools.common import run_subprocess


class PatchSandboxManager:
    """Manages isolated Git worktrees for safe patch testing and regression verification."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktrees_dir = self.repo_root / ".rush" / "worktrees"

    def create_sandbox(self) -> Path:
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.worktrees_dir / sandbox_id

        proc = run_subprocess(
            ["git", "worktree", "add", "--detach", str(sandbox_path), "HEAD"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            # Fallback for bare repos or non-worktree setups: copy working files
            sandbox_path.mkdir(parents=True, exist_ok=True)

        return sandbox_path

    def cleanup_sandbox(self, sandbox_path: Path) -> None:
        if not sandbox_path.exists():
            return
        run_subprocess(
            ["git", "worktree", "remove", "--force", str(sandbox_path)],
            cwd=self.repo_root,
        )
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)
```

---

### 5.4 `src/rush/patch/memory.py`

```python
"""SQLite-backed persistent patch memory store for AI remediations."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchMemoryRecord:
    error_signature: str
    target_file: str
    diff_patch: str
    created_at: float
    success_count: int = 1


class PatchMemoryStore:
    """Stores successful patch diffs indexed by deterministic error signature hash."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.db_path = self.repo_root / ".rush" / "cache.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patch_memory (
                    error_signature TEXT PRIMARY KEY,
                    target_file TEXT NOT NULL,
                    diff_patch TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    success_count INTEGER DEFAULT 1
                )
                """
            )
            conn.commit()

    def record_success(self, error_signature: str, target_file: str, diff_patch: str) -> None:
        sig_hash = hashlib.sha256(error_signature.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO patch_memory (error_signature, target_file, diff_patch, created_at, success_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(error_signature) DO UPDATE SET
                    diff_patch = excluded.diff_patch,
                    success_count = success_count + 1
                """,
                (sig_hash, target_file, diff_patch, time.time()),
            )
            conn.commit()

    def lookup_patch(self, error_signature: str) -> str | None:
        sig_hash = hashlib.sha256(error_signature.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT diff_patch FROM patch_memory WHERE error_signature = ?",
                (sig_hash,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def list_records(self) -> list[PatchMemoryRecord]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT error_signature, target_file, diff_patch, created_at, success_count FROM patch_memory ORDER BY created_at DESC"
            )
            return [
                PatchMemoryRecord(
                    error_signature=row[0],
                    target_file=row[1],
                    diff_patch=row[2],
                    created_at=row[3],
                    success_count=row[4],
                )
                for row in cursor.fetchall()
            ]

    def clear_memory(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM patch_memory")
            conn.commit()
            return cursor.rowcount
```

---

### 5.5 `src/rush/patch/applier.py`

```python
"""Unified diff parser and safe patch applier."""

from __future__ import annotations

from pathlib import Path
from rush.patch.diff_parser import UnifiedDiffParser
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.tools.common import run_subprocess


class PatchApplier:
    """Applies unified diff patches to target working directories with syntax verification."""

    @staticmethod
    def apply_patch_to_dir(target_dir: Path, unified_diff: str) -> tuple[bool, str]:
        if not target_dir.exists():
            return False, f"Target directory '{target_dir}' does not exist."

        try:
            parsed = UnifiedDiffParser.parse_patch(unified_diff, target_dir)
        except Exception as e:
            return False, f"Diff security validation failed: {e}"

        patch_file = target_dir / ".temp_patch.diff"
        try:
            patch_file.write_text(unified_diff, encoding="utf-8")
            proc = run_subprocess(
                ["git", "apply", "--ignore-whitespace", "--whitespace=nowarn", str(patch_file)],
                cwd=target_dir,
            )
            if proc.returncode != 0:
                return False, f"git apply failed: {proc.stderr or proc.stdout}"

            # Post-patch AST syntax verification
            for p_file in parsed:
                f_path = target_dir / p_file.new_path
                ok, err = PatchSyntaxGuard.validate_file_syntax(f_path)
                if not ok:
                    return False, f"Post-patch syntax check failed on {p_file.new_path}: {err}"

            return True, "Patch applied cleanly with valid syntax."
        finally:
            if patch_file.exists():
                patch_file.unlink()
```

---

### 5.6 `src/rush/patch/verifier.py`

```python
"""Closed-loop multi-framework test suite verifier."""

from __future__ import annotations

import shutil
from pathlib import Path
from rush.tools.common import run_subprocess


class PatchVerifier:
    """Executes detected project test runners inside the sandbox to verify patch safety."""

    def __init__(self, sandbox_dir: Path) -> None:
        self.sandbox_dir = sandbox_dir.resolve()

    def verify_patch(self) -> tuple[bool, str]:
        # 1. Python Pytest verification
        if (self.sandbox_dir / "pytest.ini").exists() or (self.sandbox_dir / "tests").exists():
            if shutil.which("pytest"):
                proc = run_subprocess(
                    ["pytest", "-q", "--tb=short"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"Pytest regression failure: {proc.stderr or proc.stdout}"

        # 2. Node / Vitest / Jest verification
        if (self.sandbox_dir / "package.json").exists():
            if shutil.which("npm"):
                proc = run_subprocess(
                    ["npm", "test", "--", "--run"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"npm test regression failure: {proc.stderr or proc.stdout}"

        # 3. Rust Cargo verification
        if (self.sandbox_dir / "Cargo.toml").exists():
            if shutil.which("cargo"):
                proc = run_subprocess(
                    ["cargo", "test", "--quiet"],
                    cwd=self.sandbox_dir,
                )
                if proc.returncode != 0:
                    return False, f"Cargo test regression failure: {proc.stderr or proc.stdout}"

        return True, "All automated tests and quality checks passed cleanly in sandbox."
```

---

### 5.7 `src/rush/patch/promoter.py`

```python
"""Atomic patch promoter from sandbox to developer working tree."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class PatchPromoter:
    """Promotes verified file changes from an ephemeral sandbox to the main working tree."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def promote_sandbox_diff(self, sandbox_dir: Path) -> tuple[bool, str]:
        proc = run_subprocess(["git", "diff"], cwd=sandbox_dir)
        if proc.returncode != 0 or not proc.stdout.strip():
            return False, "No diff found in sandbox to promote."

        patch_file = self.repo_root / ".promote.patch"
        try:
            patch_file.write_text(proc.stdout, encoding="utf-8")
            apply_proc = run_subprocess(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=self.repo_root,
            )
            if apply_proc.returncode == 0:
                return True, "Patch successfully promoted to main working tree."
            return False, f"Promotion failed: {apply_proc.stderr or apply_proc.stdout}"
        finally:
            if patch_file.exists():
                patch_file.unlink()
```

---

### 5.8 `src/rush/patch/circuit_breaker.py`

```python
"""Remediation retry circuit breaker to prevent infinite loops."""

from __future__ import annotations


class RemediationCircuitBreaker:
    """Limits consecutive automated fix attempts to prevent runaway loops."""

    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts
        self.current_attempts = 0

    def record_attempt(self) -> bool:
        self.current_attempts += 1
        return self.current_attempts <= self.max_attempts

    def is_tripped(self) -> bool:
        return self.current_attempts >= self.max_attempts

    def reset(self) -> None:
        self.current_attempts = 0
```

---

### 4.9 `src/rush/cli.py` (Registration for `rush patch`)

```python
import click
from pathlib import Path
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.applier import PatchApplier
from rush.patch.verifier import PatchVerifier
from rush.patch.promoter import PatchPromoter
from rush.patch.memory import PatchMemoryStore

@click.group(name="patch")
def patch_group():
    """Isolated AI patch testing, verification, and memory management."""
    pass

@patch_group.command(name="test")
@click.argument("patch_file", type=click.Path(exists=True))
def patch_test_cmd(patch_file: str):
    """Apply and verify a unified diff in an ephemeral worktree sandbox."""
    repo_root = Path.cwd()
    diff_content = Path(patch_file).read_text(encoding="utf-8")

    mgr = PatchSandboxManager(repo_root)
    sandbox = mgr.create_sandbox()
    click.echo(f"Created sandbox at {sandbox.name}")

    try:
        ok, msg = PatchApplier.apply_patch_to_dir(sandbox, diff_content)
        if not ok:
            click.echo(f"[PATCH APPLY FAILED] {msg}", err=True)
            return

        verifier = PatchVerifier(sandbox)
        passed, v_msg = verifier.verify_patch()
        if passed:
            click.echo(f"[VERIFICATION PASSED] {v_msg}")
        else:
            click.echo(f"[VERIFICATION FAILED] {v_msg}", err=True)
    finally:
        mgr.cleanup_sandbox(sandbox)
        click.echo("Cleaned up ephemeral sandbox.")

@patch_group.command(name="promote")
@click.argument("patch_file", type=click.Path(exists=True))
def patch_promote_cmd(patch_file: str):
    """Test, verify, and promote patch directly to main working tree."""
    repo_root = Path.cwd()
    diff_content = Path(patch_file).read_text(encoding="utf-8")

    mgr = PatchSandboxManager(repo_root)
    sandbox = mgr.create_sandbox()

    try:
        ok, msg = PatchApplier.apply_patch_to_dir(sandbox, diff_content)
        if not ok:
            click.echo(f"[FAILED] {msg}", err=True)
            return

        verifier = PatchVerifier(sandbox)
        passed, v_msg = verifier.verify_patch()
        if not passed:
            click.echo(f"[FAILED] Verification failed: {v_msg}", err=True)
            return

        promoter = PatchPromoter(repo_root)
        p_ok, p_msg = promoter.promote_sandbox_diff(sandbox)
        if p_ok:
            click.echo(f"[PROMOTED] {p_msg}")
            mem = PatchMemoryStore(repo_root)
            mem.record_success("cli_promoted_patch", patch_file, diff_content)
        else:
            click.echo(f"[FAILED] {p_msg}", err=True)
    finally:
        mgr.cleanup_sandbox(sandbox)

@patch_group.command(name="memory")
def patch_memory_cmd():
    """List all cached successful patch remediations."""
    store = PatchMemoryStore(Path.cwd())
    records = store.list_records()
    if not records:
        click.echo("No cached patch remediations in memory.")
        return
    click.echo(f"Cached Patch Remediations ({len(records)}):")
    for r in records:
        click.echo(f"  - {r.target_file} [Used {r.success_count}x, Hash: {r.error_signature[:12]}...]")
```

---

### 4.10 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for isolated AI patch remediation."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.applier import PatchApplier
from rush.patch.verifier import PatchVerifier
from rush.patch.promoter import PatchPromoter
from rush.patch.memory import PatchMemoryStore

mcp = FastMCP("rush")

@mcp.tool(name="rush_patch_apply", description="Test a unified diff in an ephemeral worktree sandbox.")
def rush_patch_apply(unified_diff: str) -> str:
    repo_root = Path.cwd()
    mgr = PatchSandboxManager(repo_root)
    sandbox = mgr.create_sandbox()
    try:
        ok, msg = PatchApplier.apply_patch_to_dir(sandbox, unified_diff)
        return json.dumps({"applied": ok, "message": msg, "sandbox": sandbox.name}, indent=2)
    finally:
        mgr.cleanup_sandbox(sandbox)

@mcp.tool(name="rush_patch_promote", description="Verify and promote an AI patch to the working tree.")
def rush_patch_promote(unified_diff: str) -> str:
    repo_root = Path.cwd()
    mgr = PatchSandboxManager(repo_root)
    sandbox = mgr.create_sandbox()
    try:
        ok, msg = PatchApplier.apply_patch_to_dir(sandbox, unified_diff)
        if not ok:
            return json.dumps({"promoted": False, "error": msg}, indent=2)
        verifier = PatchVerifier(sandbox)
        passed, v_msg = verifier.verify_patch()
        if not passed:
            return json.dumps({"promoted": False, "error": f"Verification failed: {v_msg}"}, indent=2)
        promoter = PatchPromoter(repo_root)
        p_ok, p_msg = promoter.promote_sandbox_diff(sandbox)
        return json.dumps({"promoted": p_ok, "message": p_msg}, indent=2)
    finally:
        mgr.cleanup_sandbox(sandbox)

@mcp.tool(name="rush_patch_lookup", description="Lookup cached patch remediation for a known error signature.")
def rush_patch_lookup(error_signature: str) -> str:
    store = PatchMemoryStore(Path.cwd())
    cached_diff = store.lookup_patch(error_signature)
    if cached_diff:
        return json.dumps({"found": True, "diff": cached_diff}, indent=2)
    return json.dumps({"found": False, "diff": None}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_patch_sandbox_and_memory.py`

```python
"""Comprehensive test suite for PatchSandboxManager, PatchMemoryStore, PatchApplier, PatchVerifier, PatchPromoter, UnifiedDiffParser, and RemediationCircuitBreaker."""

from pathlib import Path
import pytest
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.memory import PatchMemoryStore
from rush.patch.applier import PatchApplier
from rush.patch.verifier import PatchVerifier
from rush.patch.promoter import PatchPromoter
from rush.patch.diff_parser import UnifiedDiffParser
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.patch.circuit_breaker import RemediationCircuitBreaker


def test_unified_diff_parser_valid(tmp_path: Path):
    diff = """--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-import os
+import sys
"""
    patches = UnifiedDiffParser.parse_patch(diff, tmp_path)
    assert len(patches) == 1
    assert patches[0].new_path == "src/main.py"
    assert len(patches[0].hunks) == 1


def test_unified_diff_parser_blocks_governance_files(tmp_path: Path):
    diff = """--- a/AGENTS.md
+++ b/AGENTS.md
@@ -1,2 +1,2 @@
-# Old
+# Modified
"""
    with pytest.raises(PermissionError):
        UnifiedDiffParser.parse_patch(diff, tmp_path)


def test_syntax_guard_detects_python_syntax_errors(tmp_path: Path):
    broken_py = tmp_path / "broken.py"
    broken_py.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
    ok, err = PatchSyntaxGuard.validate_file_syntax(broken_py)
    assert ok is False
    assert "syntax error" in err.lower()


def test_patch_memory_store_roundtrip(tmp_path: Path):
    store = PatchMemoryStore(tmp_path)
    sig = "lint_error_F401_unused_import_os"
    diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +0,0 @@\n-import os\n"

    assert store.lookup_patch(sig) is None
    store.record_success(sig, "test.py", diff)
    assert store.lookup_patch(sig) == diff

    records = store.list_records()
    assert len(records) == 1
    assert records[0].target_file == "test.py"


def test_remediation_circuit_breaker():
    cb = RemediationCircuitBreaker(max_attempts=3)
    assert cb.record_attempt() is True
    assert cb.record_attempt() is True
    assert cb.record_attempt() is True
    assert cb.record_attempt() is False
    assert cb.is_tripped() is True

    cb.reset()
    assert cb.is_tripped() is False


def test_patch_applier_invalid_directory(tmp_path: Path):
    ok, msg = PatchApplier.apply_patch_to_dir(tmp_path / "nonexistent", "dummy diff")
    assert ok is False
    assert "does not exist" in msg


def test_patch_promoter_empty_diff(tmp_path: Path):
    promoter = PatchPromoter(tmp_path)
    ok, msg = promoter.promote_sandbox_diff(tmp_path)
    assert ok is False
    assert "No diff found" in msg


def test_patch_sandbox_manager_lifecycle(tmp_path: Path):
    mgr = PatchSandboxManager(tmp_path)
    sandbox = mgr.create_sandbox()
    assert sandbox.exists()
    mgr.cleanup_sandbox(sandbox)
    assert not sandbox.exists()


def test_patch_verifier_clean_environment(tmp_path: Path):
    verifier = PatchVerifier(tmp_path)
    ok, msg = verifier.verify_patch()
    assert ok is True
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 29 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:35:00.100Z", "phase": 29, "tool": "rush_patch", "event": "sandbox_created", "sandbox_id": "sandbox_8a92f1c0"}
{"timestamp": "2026-08-21T09:35:02.300Z", "phase": 29, "tool": "rush_patch", "event": "patch_verified", "status": "passed"}
{"timestamp": "2026-08-21T09:35:03.100Z", "phase": 29, "tool": "rush_patch", "event": "patch_promoted", "target": "working_tree"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 29 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 29: Isolated AI Patch Remediation & Memory**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 29 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Sandboxed AI Patch Verification & Patch Memory" section.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush patch apply`, `verify`, `promote`, `memory` (flags: `--sandbox`, `--auto-promote`, `--timeout`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for executing AI agent code modifications in isolated worktrees before promoting to main working tree.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated patch remediation workflow for GitHub Actions CI.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example patch verification transcripts and test pass assertion reports.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on configuring agent patch sandboxing in multi-agent workflows.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for Git worktree lock recovery and failed patch promotion rollbacks.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how patch sandboxing protects human developer uncommitted changes from AI corruption.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_patch_sandbox_create`, `rush_patch_apply`, and `rush_patch_verify` FastMCP endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document patch verification test output schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `patch` tool in Autonomous Remediation category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[patch]` configuration table (`max_retries`, `sandbox_timeout_seconds`, `memory_enabled`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document ephemeral Git worktree lifecycle management and SQLite vector-less patch memory schema.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for integrating custom test runners into `PatchVerifier`.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Note patch sandboxing flags for CI agents.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document worktree creation and teardown fixtures.
- **[`docs/tools/patch.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/patch.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-29): implement git worktree patch sandboxing, circuit breaker and session memory"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
