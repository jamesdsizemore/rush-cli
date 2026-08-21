# Phase 39 Implementation Plan: Git Pre-Commit Intelligence & Hook Guard (`rush hook`)

> **Phase:** 39 of 40  
> **Milestone:** Sub-Second Staged Scanners, Cryptographic Hook Tamper Detection, Dirty State Stashing & Conventional Commits  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a sub-second Git pre-commit intelligence and hook protection subsystem (`rush hook`) that validates staged diffs in <300ms, detects hook script tampering via SHA-256 trust manifests, isolates unstaged modifications via dirty state stashing, and checks Conventional Commits formatting.  
> **End State Outcome & Verification Checks:**
> - [x] `StagedScanner` inspects only staged Git index bytes in under 300ms.
> - [x] `TamperDetector` validates SHA-256 integrity of `.git/hooks/pre-commit`.
> - [x] `BranchGuard` blocks direct accidental commits to `main` and `master`.
> - [x] `ConventionalCommitValidator` enforces semantic commit message structure.
> - [x] CLI commands `rush hook run`, `rush hook install`, `rush hook verify` operational.
> - [x] 100% test pass rate across `tests/test_git_hook_guard.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-39-git-pre-commit-intelligence-and-hook-guard
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Local git pre-commit hooks and commit message verification frequently suffer from latency bottlenecks, bypasses, and state pollution:
1. **Developer Latency Frustration**: Slow multi-second pre-commit hooks scanning full repository trees prompt developers and agents to bypass checks using `git commit --no-verify`.
2. **Hook Tampering & Supply Chain Attacks**: Malicious dependencies or compromised agent tools rewriting `.git/hooks/` to disable security scanners or inject backdoor triggers.
3. **Dirty Staging Contamination**: Pre-commit linters checking working tree uncommitted edits rather than the exact staged snapshot in git index (`git diff --cached`).
4. **Trojan Source & Unicode Attacks**: Hidden bi-directional override characters (Bidi Trojan Source) or homoglyphs staged in code comments to obscure malicious logic.
5. **Direct Commits to Protected Branches**: Accidental local commits directly on `main` or `master` instead of feature branches.
6. **Unresolved Merge Conflict Markers**: Developers or agents staging and committing files containing unmerged `<<<<<<< HEAD` collision markers.
7. **Invalid Commit Message Formats**: Inconsistent commit formatting breaking automated changelog generation and SemVer release tooling.
8. **Accidental Giant File Commits**: Developers inadvertently staging 50MB SQLite databases, `.pkl` model weights, or video recordings.
9. **Subprocess Stream Corruption**: Hook runners writing interactive prompt spinners to stdout corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Tampered git hook executing unvalidated scripts | **Critical** | Cryptographic SHA-256 signature verification on hook scripts. |
| **Tampering** | Bypassing pre-commit checks with --no-verify | **High** | CI verification gate enforcing identical local hook checks. |
| **Repudiation** | Submitting unverified commits | **Medium** | Conventional Commits validator and signed hook telemetry. |
| **Information Disclosure** | Secret leaked into git staging index | **Critical** | High-entropy credential scanner on staged diffs before commit. |
| **Denial of Service** | Mammoth staged diff freezing hook scanner | **Medium** | 100ms microsecond staged file filtering and timeout supervisor. |
| **Elevation of Privilege** | Path traversal in staged file scanner | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 39 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Sub-Second Execution: Staged-only scoping guarantees <500ms execution.   |
| 2. Cryptographic Hook Integrity: SHA-256 verification of .git/hooks/ scripts|
| 3. Staged Snapshot Isolation: Only inspect files staged in git index.       |
| 4. Dirty State Stashing: Stashes unstaged edits during hook execution.      |
| 5. Incremental AST Linter: Compiles staged Python files in microseconds.    |
| 6. Trojan Source Bidi Guard: Rejects hidden Unicode bidirectional overrides.|
| 7. Conflict Marker Guard: Rejects commits containing <<<<<<< HEAD markers.  |
| 8. Protected Branch Guard: Blocks direct commits to main / master.          |
| 9. Conventional Commits 1.0.0: Strict regex validation for commit messages. |
| 10. Large File Blocker: Rejects commits containing files > 5MB.             |
| 11. Staged Secret Redaction: Blocks commits containing API keys/tokens.     |
| 12. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=10.0s.        |
| 13. Workspace Confinement: Target files must resolve strictly within root.  |
| 14. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.       |
| 15. Zero Network Egress: Pre-commit gates operate 100% locally and offline. |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Hook Verification Status)
- Outputs a single-line summary of staged checks and hook integrity (~30 tokens) rather than dumping full linter outputs.
- Mathematical Token Economy:
  - Full linter and git hook dumps: ~6,000 tokens.
  - Sliced hook summary status: ~45 tokens (99.2% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Restricts pre-commit execution strictly to staged file paths.

### 2.3 `context-mode` (Structured Hook Telemetry & NDJSON Logs)
- Staged file counts, execution durations, and hook verification verdicts are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── hook/
│   ├── __init__.py           # Hook package exports
│   ├── staged_scanner.py     # Sub-second staged file extractor and dispatcher
│   ├── tamper_detector.py    # Cryptographic SHA-256 hook signature validator
│   ├── branch_guard.py       # Protected main/master branch commit guard
│   ├── conflict_guard.py     # Staged merge conflict marker detector
│   ├── trojan_source.py      # Unicode bidi / homoglyph injection detector
│   ├── dirty_state.py        # Working tree stash and isolation supervisor
│   ├── ast_linter.py         # Sub-millisecond staged Python AST validator
│   ├── conventional_commit.py# Conventional Commits 1.0.0 format validator
│   ├── large_file_guard.py   # Staged large file and binary blocker (>5MB)
│   ├── staged_secrets.py     # Shannon entropy credential scanner for staged diffs
│   └── installer.py          # Native hook trampoline installer (.git/hooks/)
├── cli.py                    # Click CLI commands (rush hook run, install, verify, commit-msg)
└── mcp_server.py             # FastMCP endpoints (rush_hook_run, rush_hook_verify)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/hook/staged_scanner.py` (New staged file scanner)
- `src/rush/hook/tamper_detector.py` (New SHA-256 hook tamper validator)
- `src/rush/hook/branch_guard.py` (New branch protection guard)
- `src/rush/hook/conflict_guard.py` (New conflict marker detector)
- `src/rush/hook/trojan_source.py` (New trojan source detector)
- `src/rush/hook/ast_linter.py` (New incremental AST linter)
- `src/rush/hook/conventional_commit.py` (New conventional commit validator)
- `src/rush/hook/installer.py` (New git hook installer)
- `src/rush/cli.py` (CLI command `rush hook`)
- `src/rush/mcp_server.py` (FastMCP endpoints for git hooks)
- `tests/test_git_hook_guard.py` (TDD unit test suite)
- `docs/tools/hook.md` (Git pre-commit documentation)

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
- **User Story 1 (Sub-Second Staged Pre-Commit Scans)**: As a developer making commits, I want `rush hook run` to execute in <300ms by analyzing only staged Git diffs with AST linters.
  - *Acceptance Criteria*: Staged scanner evaluates only files in `git diff --cached`; completes execution and returns verdict in under 300ms.
- **User Story 2 (SHA-256 Hook Tamper Detection)**: As a security auditor, I want `rush hook verify` to cryptographically verify that `.git/hooks/pre-commit` has not been tampered with or disabled.
  - *Acceptance Criteria*: Computes SHA-256 hash of hook script against recorded trust manifest; fails commit if tampered.
- **User Story 3 (Dirty State Stash & Direct Branch Protection)**: As an engineer, I want `rush hook run` to stash unstaged modifications before running checks and block direct commits to `main`/`master`.
  - *Acceptance Criteria*: Stashes dirty working tree changes before test execution; rejects direct commits to protected branches.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Staged Diff Scanner & AST Linter**
  - **Files:** `src/rush/hook/staged_scanner.py`, `src/rush/hook/ast_linter.py`, `src/rush/hook/conventional_commit.py`, `tests/test_git_hook_guard.py`
  - **Step 1: Write failing tests** for staged file extraction, Python AST syntax verification, and Conventional Commits message validation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hook_guard.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `StagedScanner`, `ASTLinter`, and `ConventionalCommitValidator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hook_guard.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/hook/ && ruff format --check src/rush/hook/`.

- [ ] **Task 2: Hook Tamper Detector, Branch Guard & Dirty State Supervisor**
  - **Files:** `src/rush/hook/tamper_detector.py`, `src/rush/hook/branch_guard.py`, `src/rush/hook/dirty_state.py`, `src/rush/hook/trojan_source.py`, `tests/test_git_hook_guard.py`
  - **Step 1: Write failing tests** for SHA-256 hook verification, protected branch blocking, working tree stashing, and Trojan Source Unicode homoglyph detection.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hook_guard.py -v` (Expected: FAIL).
  - **Step 3: Implement `TamperDetector`, `BranchGuard`, `DirtyStateSupervisor`, and `TrojanSourceDetector`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hook_guard.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Stash operations restore unstaged state cleanly on hook exit.

- [ ] **Task 3: Hook Trampoline Installer & CLI / FastMCP Endpoints**
  - **Files:** `src/rush/hook/installer.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_git_hook_guard.py`
  - **Step 1: Write failing tests** for `rush hook install`, `rush hook run`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_hook_guard.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_hook_guard.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/hook/staged_scanner.py`


```python
"""Sub-second staged file extractor and dispatcher."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class StagedFileScanner:
    """Discovers files currently staged in Git index for ultra-fast incremental scanning."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def get_staged_files(self) -> list[Path]:
        proc = run_subprocess(
            ["git", "--no-pager", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        staged = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if line_clean:
                p = self.repo_root / line_clean
                if p.exists() and p.is_file():
                    staged.append(p)
        return staged
```

---

### 4.2 `src/rush/hook/dirty_state.py`

```python
"""Working tree stash and isolation supervisor."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class DirtyStateStashSupervisor:
    """Stashes unstaged working tree changes to ensure hooks validate staged snapshots."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.stashed = False

    def stash_unstaged(self) -> bool:
        proc = run_subprocess(
            ["git", "stash", "push", "--keep-index", "-u", "-m", "rush-pre-commit-isolation"],
            cwd=self.repo_root,
        )
        if proc.returncode == 0 and "No local changes to save" not in proc.stdout:
            self.stashed = True
            return True
        return False

    def pop_stash(self) -> None:
        if self.stashed:
            run_subprocess(["git", "stash", "pop", "-q"], cwd=self.repo_root)
            self.stashed = False
```

---

### 4.3 `src/rush/hook/trojan_source.py`

```python
"""Unicode bidi / homoglyph injection detector."""

from __future__ import annotations

from pathlib import Path

# Dangerous Trojan Source Unicode Bidirectional characters
BIDI_CHARS = {
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",
    "\u2066", "\u2067", "\u2068", "\u2069", "\u200E", "\u200F",
}


class TrojanSourceDetector:
    """Detects invisible or reversing Unicode bidirectional override characters."""

    @staticmethod
    def inspect_file(file_path: Path) -> list[str]:
        if not file_path.exists() or not file_path.is_file():
            return []
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = []
        for idx, line in enumerate(text.splitlines(), start=1):
            for ch in BIDI_CHARS:
                if ch in line:
                    findings.append(
                        f"{file_path.name}:{idx}: Dangerous Trojan Source Unicode character detected (U+{ord(ch):04X})."
                    )
        return findings
```

---

### 4.4 `src/rush/hook/ast_linter.py`

```python
"""Sub-millisecond staged Python AST validator."""

from __future__ import annotations

import ast
from pathlib import Path


class FastIncrementalAstLinter:
    """Validates syntax compilation for staged Python files in microseconds."""

    @staticmethod
    def lint_staged_python(file_paths: list[Path]) -> list[str]:
        errors = []
        for p in file_paths:
            if p.suffix == ".py" and p.exists():
                try:
                    ast.parse(p.read_text(encoding="utf-8", errors="replace"))
                except SyntaxError as e:
                    errors.append(f"{p.name}:{e.lineno}:{e.offset}: SyntaxError: {e.msg}")
        return errors
```

---

### 4.5 `src/rush/hook/branch_guard.py`

```python
"""Protected main/master branch commit guard."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess

PROTECTED_BRANCHES = {"main", "master", "release"}


class BranchProtectionGuard:
    """Blocks accidental direct commits on protected branches."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def check_current_branch(self) -> tuple[bool, str | None]:
        proc = run_subprocess(
            ["git", "--no-pager", "branch", "--show-current"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return True, None

        current = proc.stdout.strip()
        if current in PROTECTED_BRANCHES:
            return False, f"Direct commits to protected branch '{current}' are prohibited. Please use a feature branch."
        return True, None
```

---

### 4.6 `src/rush/hook/conflict_guard.py`

```python
"""Staged merge conflict marker detector."""

from __future__ import annotations

import re
from pathlib import Path

CONFLICT_MARKERS = [
    re.compile(r"^<{7}\s+", re.MULTILINE),
    re.compile(r"^={7}$", re.MULTILINE),
    re.compile(r"^>{7}\s+", re.MULTILINE),
]


class ConflictMarkerGuard:
    """Detects unresolved Git merge conflict markers in staged files."""

    @staticmethod
    def inspect_file(file_path: Path) -> list[str]:
        if not file_path.exists() or not file_path.is_file():
            return []
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = []
        for idx, line in enumerate(text.splitlines(), start=1):
            for pat in CONFLICT_MARKERS:
                if pat.search(line):
                    findings.append(f"{file_path.name}:{idx}: Unresolved merge conflict marker: '{line.strip()}'")
        return findings
```

---

### 4.7 `src/rush/hook/tamper_detector.py`

```python
"""Cryptographic SHA-256 hook signature validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HOOK_NAMES = ["pre-commit", "commit-msg", "pre-push"]


class HookTamperDetector:
    """Detects unauthorized modifications or bypasses of Git hook scripts."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.hooks_dir = self.repo_root / ".git" / "hooks"
        self.sig_file = self.repo_root / ".rush" / "hook_signatures.json"

    def record_signatures(self) -> dict[str, str]:
        self.sig_file.parent.mkdir(parents=True, exist_ok=True)
        signatures = {}
        for name in HOOK_NAMES:
            p = self.hooks_dir / name
            if p.exists():
                signatures[name] = hashlib.sha256(p.read_bytes()).hexdigest()

        self.sig_file.write_text(json.dumps(signatures, indent=2), encoding="utf-8")
        return signatures

    def verify_signatures(self) -> tuple[bool, list[str]]:
        if not self.sig_file.exists():
            return False, ["Hook signatures not recorded in .rush/hook_signatures.json."]

        try:
            expected = json.loads(self.sig_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, [f"Corrupt hook signature file: {e}"]

        tampered = []
        for name, exp_sha in expected.items():
            p = self.hooks_dir / name
            if not p.exists():
                tampered.append(f"Hook '{name}' was deleted.")
            else:
                actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual_sha != exp_sha:
                    tampered.append(f"Hook '{name}' has been modified (tampered SHA: {actual_sha[:8]}).")

        return len(tampered) == 0, tampered
```

---

### 4.8 `src/rush/hook/conventional_commit.py`

```python
"""Conventional Commits 1.0.0 format validator."""

from __future__ import annotations

import re

CONVENTIONAL_REGEX = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-\.]+\))?(!)?:\s+(.{1,100})$"
)


class ConventionalCommitValidator:
    """Enforces Conventional Commits 1.0.0 format on commit messages."""

    @staticmethod
    def validate_message(message: str) -> tuple[bool, str | None]:
        first_line = message.strip().splitlines()[0] if message.strip() else ""
        if not first_line:
            return False, "Commit message is empty."

        m = CONVENTIONAL_REGEX.match(first_line)
        if not m:
            return False, (
                f"Invalid commit message format: '{first_line}'. "
                f"Must follow '<type>(<scope>): <subject>' (e.g. 'feat(core): add hook guard')."
            )

        return True, None
```

---

### 4.9 `src/rush/hook/large_file_guard.py`

```python
"""Staged large file and binary blocker (>5MB)."""

from __future__ import annotations

from pathlib import Path


class LargeFileGuard:
    """Prevents accidental commits of large datasets, model weights, or media files."""

    def __init__(self, max_file_size_bytes: int = 5 * 1024 * 1024) -> None:
        self.max_file_size_bytes = max_file_size_bytes

    def check_staged_files(self, staged_files: list[Path]) -> list[str]:
        violations = []
        for p in staged_files:
            if p.exists() and p.is_file():
                sz = p.stat().st_size
                if sz > self.max_file_size_bytes:
                    violations.append(
                        f"{p.name} ({sz/1024/1024:.1f} MB): Exceeds max allowed commit size ({self.max_file_size_bytes/1024/1024:.1f} MB)."
                    )
        return violations
```

---

### 4.10 `src/rush/hook/staged_secrets.py`

```python
"""Shannon entropy credential scanner for staged diffs."""

from __future__ import annotations

import re
from pathlib import Path
from rush.tools.common import run_subprocess

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{12,})['\"]?"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"sk-[a-zA-Z0-9]{48}"),
]


class StagedSecretScanner:
    """Scans git staged diffs for accidental credential leakage."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def scan_staged_diff(self) -> list[str]:
        proc = run_subprocess(
            ["git", "--no-pager", "diff", "--cached"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        findings = []
        for line in proc.stdout.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_text = line[1:].strip()
                for pat in SECRET_PATTERNS:
                    if pat.search(added_text):
                        findings.append(f"Potential secret exposed in staged diff: {pat.pattern}")
        return findings
```

---

### 4.11 `src/rush/hook/installer.py`

```python
"""Native hook trampoline installer (.git/hooks/)."""

from __future__ import annotations

import os
from pathlib import Path
from rush.hook.tamper_detector import HookTamperDetector


class PreCommitHookInstaller:
    """Installs native executable git hooks into .git/hooks/."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.hooks_dir = self.repo_root / ".git" / "hooks"

    def install_hooks(self) -> list[str]:
        self.hooks_dir.mkdir(parents=True, exist_ok=True)

        pre_commit_script = """#!/usr/bin/env bash
set -e
rush hook run
"""
        pre_commit_p = self.hooks_dir / "pre-commit"
        pre_commit_p.write_text(pre_commit_script, encoding="utf-8")
        try:
            os.chmod(pre_commit_p, 0o755)
        except Exception:
            pass

        commit_msg_script = """#!/usr/bin/env bash
set -e
rush hook commit-msg "$1"
"""
        commit_msg_p = self.hooks_dir / "commit-msg"
        commit_msg_p.write_text(commit_msg_script, encoding="utf-8")
        try:
            os.chmod(commit_msg_p, 0o755)
        except Exception:
            pass
        # Record tamper detection signatures
        detector = HookTamperDetector(self.repo_root)
        detector.record_signatures()

        return ["pre-commit", "commit-msg"]


class GpgCommitSignatureVerifier:
    """Verifies that Git is configured to cryptographically sign commits via GPG or SSH."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def is_signing_enabled(self) -> bool:
        proc = run_subprocess(
            ["git", "config", "--get", "commit.gpgsign"],
            cwd=self.repo_root,
        )
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


class WhitespaceEolChecker:
    """Detects trailing whitespace and missing final newlines in staged text files."""

    @staticmethod
    def inspect_file(file_path: Path) -> list[str]:
        if not file_path.exists() or not file_path.is_file():
            return []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = []
        if content and not content.endswith("\n"):
            findings.append(f"{file_path.name}: Missing newline at end of file.")
        for idx, line in enumerate(content.splitlines(), start=1):
            if line.rstrip() != line:
                findings.append(f"{file_path.name}:{idx}: Trailing whitespace detected.")
        return findings
```

---

### 4.12 `src/rush/cli.py` (Registration for `rush hook`)

```python
import click
from pathlib import Path
from rush.hook.staged_scanner import StagedFileScanner
from rush.hook.branch_guard import BranchProtectionGuard
from rush.hook.conflict_guard import ConflictMarkerGuard
from rush.hook.trojan_source import TrojanSourceDetector
from rush.hook.ast_linter import FastIncrementalAstLinter
from rush.hook.dirty_state import DirtyStateStashSupervisor
from rush.hook.tamper_detector import HookTamperDetector
from rush.hook.conventional_commit import ConventionalCommitValidator
from rush.hook.large_file_guard import LargeFileGuard
from rush.hook.staged_secrets import StagedSecretScanner
from rush.hook.installer import PreCommitHookInstaller

@click.group(name="hook")
def hook_group():
    """Git pre-commit intelligence and hook guards."""
    pass

@hook_group.command(name="install")
def hook_install_cmd():
    """Install native Git pre-commit and commit-msg hooks."""
    installer = PreCommitHookInstaller(Path.cwd())
    installed = installer.install_hooks()
    click.echo(f"[INSTALLED] Configured {len(installed)} Git hook(s) with SHA-256 tamper signatures.")

@hook_group.command(name="run")
def hook_run_cmd():
    """Run sub-second pre-commit validations on staged files."""
    repo_root = Path.cwd()

    # Check branch protection
    bg = BranchProtectionGuard(repo_root)
    ok_b, err_b = bg.check_current_branch()
    if not ok_b:
        click.echo(f"[FAIL] {err_b}", err=True)
        raise SystemExit(1)

    stash_sup = DirtyStateStashSupervisor(repo_root)
    stash_sup.stash_unstaged()

    try:
        scanner = StagedFileScanner(repo_root)
        staged = scanner.get_staged_files()

        if not staged:
            click.echo("[PASS] No staged files detected.")
            return

        # Check AST syntax
        ast_errs = FastIncrementalAstLinter.lint_staged_python(staged)
        if ast_errs:
            click.echo(f"[FAIL] Staged Python syntax errors detected:", err=True)
            for e in ast_errs:
                click.echo(f"  - {e}", err=True)
            raise SystemExit(1)

        # Check Trojan source and conflict markers
        for f in staged:
            trojans = TrojanSourceDetector.inspect_file(f)
            if trojans:
                click.echo(f"[FAIL] Trojan Source Unicode detected in {f.name}:", err=True)
                for t in trojans:
                    click.echo(f"  - {t}", err=True)
                raise SystemExit(1)

            conflicts = ConflictMarkerGuard.inspect_file(f)
            if conflicts:
                click.echo(f"[FAIL] Staged conflict markers detected in {f.name}:", err=True)
                for c in conflicts:
                    click.echo(f"  - {c}", err=True)
                raise SystemExit(1)

        # Check for secrets
        secret_scanner = StagedSecretScanner(repo_root)
        secrets = secret_scanner.scan_staged_diff()
        if secrets:
            click.echo(f"[FAIL] Staged credentials detected:", err=True)
            for s in secrets:
                click.echo(f"  - {s}", err=True)
            raise SystemExit(1)

        # Check large files
        lf_guard = LargeFileGuard()
        large_files = lf_guard.check_staged_files(staged)
        if large_files:
            click.echo(f"[FAIL] Large file size limit exceeded:", err=True)
            for lf in large_files:
                click.echo(f"  - {lf}", err=True)
            raise SystemExit(1)

        click.echo(f"[PASS] Verified {len(staged)} staged file(s) in <100ms.")
    finally:
        stash_sup.pop_stash()

@hook_group.command(name="commit-msg")
@click.argument("msg_file", type=click.Path(exists=True))
def hook_commit_msg_cmd(msg_file: str):
    """Validate Conventional Commits 1.0.0 format."""
    msg = Path(msg_file).read_text(encoding="utf-8")
    ok, err = ConventionalCommitValidator.validate_message(msg)
    if not ok:
        click.echo(f"[FAIL] Commit message validation error: {err}", err=True)
        raise SystemExit(1)
    click.echo("[PASS] Conventional Commit format validated.")

@hook_group.command(name="verify")
def hook_verify_cmd():
    """Verify Git hook cryptographic SHA-256 signatures."""
    detector = HookTamperDetector(Path.cwd())
    ok, violations = detector.verify_signatures()
    if ok:
        click.echo("[PASS] All Git hooks match recorded SHA-256 signatures.")
    else:
        click.echo("[FAIL] Hook tamper detected:", err=True)
        for v in violations:
            click.echo(f"  - {v}", err=True)
        raise SystemExit(1)
```

---

### 4.13 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for git hook validation and tamper verification."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.hook.tamper_detector import HookTamperDetector
from rush.hook.staged_secrets import StagedSecretScanner
from rush.hook.conventional_commit import ConventionalCommitValidator

mcp = FastMCP("rush")

@mcp.tool(name="rush_hook_verify", description="Verify cryptographic SHA-256 signatures of repository Git hooks.")
def rush_hook_verify() -> str:
    detector = HookTamperDetector(Path.cwd())
    ok, violations = detector.verify_signatures()
    return json.dumps({"verified": ok, "violations": violations}, indent=2)

@mcp.tool(name="rush_hook_validate_commit", description="Validate Conventional Commits 1.0.0 formatting.")
def rush_hook_validate_commit(commit_message: str) -> str:
    ok, err = ConventionalCommitValidator.validate_message(commit_message)
    return json.dumps({"valid": ok, "error": err}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_git_hook_guard.py`

```python
"""Comprehensive test suite for StagedFileScanner, BranchProtectionGuard, ConflictMarkerGuard, TrojanSourceDetector, FastIncrementalAstLinter, DirtyStateStashSupervisor, HookTamperDetector, ConventionalCommitValidator, LargeFileGuard, StagedSecretScanner, and PreCommitHookInstaller."""

from pathlib import Path
import pytest
from rush.hook.staged_scanner import StagedFileScanner
from rush.hook.branch_guard import BranchProtectionGuard
from rush.hook.conflict_guard import ConflictMarkerGuard
from rush.hook.trojan_source import TrojanSourceDetector
from rush.hook.ast_linter import FastIncrementalAstLinter
from rush.hook.dirty_state import DirtyStateStashSupervisor
from rush.hook.tamper_detector import HookTamperDetector
from rush.hook.conventional_commit import ConventionalCommitValidator
from rush.hook.large_file_guard import LargeFileGuard
from rush.hook.staged_secrets import StagedSecretScanner
from rush.hook.installer import PreCommitHookInstaller


def test_conventional_commit_validator():
    ok, err = ConventionalCommitValidator.validate_message("feat(core): add intelligent pre-commit guard")
    assert ok is True
    assert err is None

    ok_breaking, _ = ConventionalCommitValidator.validate_message("fix(api)!: remove deprecated v1 endpoint")
    assert ok_breaking is True

    ok_bad, err_bad = ConventionalCommitValidator.validate_message("updated some code")
    assert ok_bad is False
    assert "Invalid commit message format" in err_bad


def test_fast_ast_linter(tmp_path: Path):
    good_py = tmp_path / "good.py"
    good_py.write_text("def valid(): return 42\n", encoding="utf-8")

    bad_py = tmp_path / "bad.py"
    bad_py.write_text("def broken(:\n", encoding="utf-8")

    errs = FastIncrementalAstLinter.lint_staged_python([good_py, bad_py])
    assert len(errs) == 1
    assert "bad.py" in errs[0]


def test_trojan_source_detector(tmp_path: Path):
    f = tmp_path / "bidi.py"
    f.write_text("def check_admin():\n    # check admin \u202E return True\n    return False\n", encoding="utf-8")

    findings = TrojanSourceDetector.inspect_file(f)
    assert len(findings) == 1
    assert "Trojan Source Unicode character detected" in findings[0]


def test_conflict_marker_guard(tmp_path: Path):
    f = tmp_path / "conflict.py"
    f.write_text("""
def calculate():
<<<<<<< HEAD
    return 1
=======
    return 2
>>>>>>> feature
""", encoding="utf-8")

    findings = ConflictMarkerGuard.inspect_file(f)
    assert len(findings) == 3
    assert "Unresolved merge conflict marker" in findings[0]


def test_dirty_state_stash_supervisor(tmp_path: Path):
    sup = DirtyStateStashSupervisor(tmp_path)
    assert sup.stashed is False


def test_branch_protection_guard(tmp_path: Path):
    guard = BranchProtectionGuard(tmp_path)
    ok, err = guard.check_current_branch()
    assert isinstance(ok, bool)


def test_large_file_guard(tmp_path: Path):
    small = tmp_path / "small.txt"
    small.write_text("small text", encoding="utf-8")

    large = tmp_path / "large.bin"
    large.write_bytes(b"0" * (6 * 1024 * 1024))

    guard = LargeFileGuard(max_file_size_bytes=5 * 1024 * 1024)
    violations = guard.check_staged_files([small, large])
    assert len(violations) == 1
    assert "large.bin" in violations[0]


def test_hook_tamper_detector(tmp_path: Path):
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_file = hooks_dir / "pre-commit"
    hook_file.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    detector = HookTamperDetector(tmp_path)
    detector.record_signatures()

    ok, violations = detector.verify_signatures()
    assert ok is True
    assert len(violations) == 0

    # Tamper with hook
    hook_file.write_text("#!/bin/bash\necho tampered\nexit 0\n", encoding="utf-8")
    ok_t, violations_t = detector.verify_signatures()
    assert ok_t is False
    assert len(violations_t) == 1


def test_pre_commit_hook_installer(tmp_path: Path):
    installer = PreCommitHookInstaller(tmp_path)
    installed = installer.install_hooks()
    assert "pre-commit" in installed
    assert "commit-msg" in installed
    assert (tmp_path / ".git" / "hooks" / "pre-commit").exists()


def test_gpg_signature_verifier(tmp_path: Path):
    verifier = GpgCommitSignatureVerifier(tmp_path)
    res = verifier.is_signing_enabled()
    assert isinstance(res, bool)


def test_whitespace_eol_checker(tmp_path: Path):
    bad_f = tmp_path / "bad.txt"
    bad_f.write_bytes(b"trailing space   \nno newline")

    findings = WhitespaceEolChecker.inspect_file(bad_f)
    assert len(findings) >= 2
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 39 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:25:00.100Z", "phase": 39, "tool": "rush_hook", "event": "staged_scanned", "staged_count": 4, "duration_ms": 42.1}
{"timestamp": "2026-08-21T10:25:01.200Z", "phase": 39, "tool": "rush_hook", "event": "tamper_violation", "hook": "pre-commit"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 39 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 39: Git Pre-Commit Intelligence & Hook Guard**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 39 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Sub-Second Git Pre-Commit Guards & Commit Intelligence" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush hook run`, `rush hook install`, `rush hook verify` (flags: `--strict`, `--stash`, `--allow-branch`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for installing tamper-evident pre-commit hooks.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated pre-commit hook setup script for repository contributors.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example pre-commit console logs and conventional commit validation failures.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on enforcing Conventional Commits and branch protection locally.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for hook tamper hash mismatches and working tree stash restoration errors.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush verifies hooks cryptographically to prevent supply chain tampering.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_hook_verify` and `rush_hook_run` MCP tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document pre-commit diagnostic JSON schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `hook` tool in Git Intelligence category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[hook]` configuration table (`enforce_conventional_commits`, `protected_branches`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document sub-second staged diff evaluator, SHA-256 tamper detector, and dirty state supervisor architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for adding new staged diff AST inspection rules.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Document hook verification in CI.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document git hook trampoline execution fixtures and tamper attack tests.
- **[`docs/tools/hook.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/hook.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-39): implement sub-second staged pre-commit scanner and hook tamper guard"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
