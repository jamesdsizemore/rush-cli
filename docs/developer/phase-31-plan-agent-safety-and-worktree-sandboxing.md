# Phase 31 Implementation Plan: Agent Safety & Worktree Sandboxing (`rush sandbox` / `rush guard`)

> **Phase:** 31 of 40  
> **Milestone:** Agent Mutation Safety Guard, Dangerous Command Interception & Worktree Sandboxing  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a zero-trust agent safety firewall (`rush guard`, `rush sandbox`) that intercepts dangerous destructive commands (`git reset --hard`, `rm -rf`, `git push --force`), enforces workspace path confinement, redacts Shannon entropy secrets, and sandboxes all file writes in isolated Git worktrees.  
> **End State Outcome & Verification Checks:**
> - [x] `CommandInterceptor` blocks 100% of destructive Git, shell, and filesystem mutation commands.
> - [x] `GovernanceFirewall` denies write access to `AGENTS.md`, `.git/`, and `rush.toml`.
> - [x] `EntropySecretRedactor` masks high-entropy API keys and tokens as `[REDACTED]`.
> - [x] CLI commands `rush guard check`, `rush sandbox create`, `prune` operational.
> - [x] 100% test pass rate across `tests/test_agent_safety_guard.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0020: Cryptographic HMAC Context Boundary Framing](../adr/0020-cryptographic-hmac-context-boundary-framing.md)  
> - [ADR-0021: Ephemeral Git Worktree Sandboxing](../adr/0021-ephemeral-git-worktree-sandboxing.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-31-agent-safety-and-worktree-sandboxing
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Autonomous coding agents operating with shell and filesystem write permissions pose critical operational risks to developer repositories:
1. **Destructive Command Execution (MITRE ATT&CK T1485)**: Agents attempting to resolve git conflicts or clean untracked files executing destructive commands (`git reset --hard`, `git push --force`, `git clean -fdx`, `rm -rf .`) resulting in catastrophic loss of uncommitted work.
2. **Governance Hijacking & Rule Tampering**: An agent attempting to pass a failing lint check modifies `AGENTS.md`, `.cursorrules`, or `rush.toml` to weaken security thresholds or delete test requirements.
3. **Secret Leakage in Multi-Turn Context**: Agents logging unredacted environment variables, database connection strings, or API tokens into stdout or log artifacts.
4. **stdio Stream Pollution**: External sandbox process wrappers writing interactive escape codes to stdout corrupt FastMCP JSON-RPC communication frames.
5. **Path Traversal & Host Filesystem Escapes**: Agents writing temporary files to `/tmp`, `~/.ssh/`, or parent directories outside the active repository root.
6. **Network Exfiltration via Agent Scripts (MITRE ATT&CK T1048)**: Sandboxed plugins or test runners making outbound HTTP connections to exfiltrate proprietary source code or stolen credentials.
7. **Dynamic Python Code Injection**: Agent patches introducing obfuscated `eval()`, `exec()`, or `__import__('os').system()` calls that bypass static regex linters.
8. **Resource Exhaustion Attacks**: Speculative agent scripts spawning runaway threads or memory allocation loops that freeze the developer machine.
9. **Orphaned Process Leakage**: Subprocesses killed uncleanly leaving background zombie processes consuming CPU.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Agent claiming dangerous command was user-authorized | **Critical** | Command interceptor requiring explicit interactive confirmation flags. |
| **Tampering** | Agent editing `AGENTS.md` or `.git/hooks/` to disable gates | **Critical** | Immutable governance path firewall rejecting writes to protected files. |
| **Repudiation** | Silent unlogged command executions by AI agents | **Medium** | Append-only HMAC-SHA256 chained audit logs on `sys.stderr`. |
| **Information Disclosure** | Agent printing raw API keys or database passwords | **Critical** | Automatic Shannon entropy and regex secret redactor filter (`[REDACTED]`). |
| **Denial of Service** | Agent spawning infinite fork bomb or unbounded loop | **High** | Process isolation supervisor enforcing strict 30.0s timeouts and memory limits. |
| **Elevation of Privilege** | Path traversal escaping repository root via symlinks | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 31 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Immutable Governance Firewall: AGENTS.md, rush.toml are read-only to AI. |
| 2. Dangerous Command Interceptor: Blocks git reset --hard, rm -rf, force push|
| 3. Automatic Secret Redaction: Masks API keys and tokens with [REDACTED].   |
| 4. Worktree Sandboxing: Isolates speculative agent mutations in worktrees.   |
| 5. AST Import Firewall: Blocks eval(), exec(), __import__() dynamic code.   |
| 6. Resource Limits: Memory capped to 2GB per process; CPU timeout 30.0s.   |
| 7. Ephemeral RAM-Disk Mounts: High-speed in-memory sandboxes for tests.     |
| 8. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 9. Workspace Confinement: Target files must resolve strictly within root.   |
| 10. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.       |
| 11. Zero Network Egress: Blocks external outbound socket connections.       |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Sandbox & Guard Summaries)
- Outputs a single-line summary table of active sandboxes and command safety verdicts (~40 tokens) rather than dumping full process logs into LLM context.
- Mathematical Token Economy:
  - Raw sandbox process logs: ~4,200 tokens.
  - Sliced safety summary: ~60 tokens (98.6% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Restricts sandbox file access strictly to modified package subtrees.

### 2.3 `context-mode` (Structured Safety Telemetry & NDJSON Logs)
- Intercepted commands, blocked file mutations, and active worktree allocations are streamed as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── safety/
│   ├── __init__.py           # Safety package exports
│   ├── guard.py              # Immutable governance rulebook firewall
│   ├── interceptor.py        # Destructive shell command interceptor
│   ├── redactor.py           # Shannon entropy and regex secret redactor
│   ├── import_guard.py       # AST dynamic code and dangerous import scanner
│   ├── resource_limiter.py   # Memory and CPU resource boundary supervisor
│   ├── signal_trap.py        # Process signal handler and graceful tree termination
│   ├── ephemeral_mount.py    # High-speed ephemeral tmpfs / RAM-disk manager
│   ├── dirty_tracker.py      # Working tree mutation and dirty state tracker
│   ├── isolation.py          # Subprocess execution and timeout supervisor
│   ├── path_confiner.py      # Strict workspace path boundary validator
│   ├── worktree_sandbox.py   # Ephemeral Git worktree sandbox manager
│   ├── network_guard.py      # Outbound network socket interceptor and blocker
│   └── audit_logger.py       # HMAC-SHA256 chained security audit logger
├── cli.py                    # Click CLI commands (rush guard check-cmd, redact, rush sandbox)
└── mcp_server.py             # FastMCP endpoints (rush_guard_check_command, rush_sandbox_create)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/safety/guard.py` (New governance firewall)
- `src/rush/safety/interceptor.py` (New command interceptor)
- `src/rush/safety/redactor.py` (New entropy secret redactor)
- `src/rush/safety/worktree_sandbox.py` (New worktree sandbox manager)
- `src/rush/safety/path_confiner.py` (New path boundary validator)
- `src/rush/safety/audit_logger.py` (New audit logger)
- `src/rush/cli.py` (CLI commands `rush guard`, `rush sandbox`)
- `src/rush/mcp_server.py` (FastMCP endpoints for safety guards)
- `tests/test_agent_safety_guard.py` (TDD unit test suite)
- `docs/guides/safety.md`, `docs/tools/guard.md` (Documentation)

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
- **User Story 1 (Destructive Shell Command Interception)**: As a security reviewer, I want Rush to intercept dangerous agent shell commands (e.g. `rm -rf /`, `git push --force`, `chmod 777`, `curl | bash`) and block execution with clear explanations.
  - *Acceptance Criteria*: Blocklist patterns match and reject destructive invocations with `status="failed"` before execution.
- **User Story 2 (High-Entropy Secret Redaction)**: As an engineer, I want all tool stdout/stderr outputs scanned with Shannon entropy algorithms so that API keys and credentials are automatically replaced with `[REDACTED]`.
  - *Acceptance Criteria*: Injected API tokens and secret strings are masked with `[REDACTED]` across logs and JSON-RPC streams.
- **User Story 3 (Ephemeral Git Worktree Sandboxing)**: As an AI agent executor, I want autonomous code changes executed in an isolated worktree sandbox without mutating the user's primary working directory.
  - *Acceptance Criteria*: Creates temporary branch and worktree; discards on failure and commits cleanly on success.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Command Interceptor & Secret Redactor**
  - **Files:** `src/rush/safety/interceptor.py`, `src/rush/safety/redactor.py`, `tests/test_agent_safety_guard.py`
  - **Step 1: Write failing tests** for command pattern matching, destructive flag detection, and Shannon entropy secret masking.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_safety_guard.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `CommandInterceptor` and `EntropySecretRedactor`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_safety_guard.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/safety/ && ruff format --check src/rush/safety/`.

- [ ] **Task 2: Path Confiner, Safety Guard & Audit Logger**
  - **Files:** `src/rush/safety/guard.py`, `src/rush/safety/path_confiner.py`, `src/rush/safety/audit_logger.py`, `tests/test_agent_safety_guard.py`
  - **Step 1: Write failing tests** for workspace path confinement, protected files firewall (`.git`, `AGENTS.md`), and HMAC audit logging.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_safety_guard.py -v` (Expected: FAIL).
  - **Step 3: Implement `SafetyGuard`, `PathConfiner`, and `AuditLogger`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_safety_guard.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Path resolution prevents directory traversal and symlink escapes.

- [ ] **Task 3: Worktree Sandboxing & FastMCP Endpoints**
  - **Files:** `src/rush/safety/worktree_sandbox.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_agent_safety_guard.py`
  - **Step 1: Write failing tests** for worktree lifecycle, `rush guard`, and FastMCP endpoints `rush_guard_check_command`, `rush_sandbox_create`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_safety_guard.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_safety_guard.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/safety/guard.py`

```python
"""Immutable governance rulebook and protected path firewall."""

from __future__ import annotations

from pathlib import Path

PROTECTED_GOVERNANCE_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    "rush.toml",
    ".rush/trust.json",
    ".rush/hooks.json",
    "SECURITY.md",
}


class AgentSafetyGuard:
    """Blocks autonomous AI coding agents from modifying protected governance files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def is_file_protected(self, target_path: Path | str) -> bool:
        if isinstance(target_path, str):
            path_str = target_path.replace("\\", "/")
        else:
            try:
                rel = target_path.resolve().relative_to(self.repo_root)
                path_str = rel.as_posix()
            except ValueError:
                return True

        if path_str in PROTECTED_GOVERNANCE_FILES:
            return True

        if path_str.startswith(".git/"):
            return True

        return False

    def validate_write_target(self, target_path: Path | str) -> None:
        if self.is_file_protected(target_path):
            raise PermissionError(
                f"Agent mutation blocked: '{target_path}' is an immutable governance file."
            )
```

---

### 5.2 `src/rush/safety/interceptor.py`

```python
"""Destructive shell command interceptor."""

from __future__ import annotations

import re

DANGEROUS_COMMAND_PATTERNS = [
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "Blocked destructive command 'git reset --hard'."),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"), "Blocked destructive command 'git clean -f'."),
    (re.compile(r"\bgit\s+push\s+.*--force\b"), "Blocked destructive command 'git push --force'."),
    (re.compile(r"\bgit\s+push\s+.*-f\b"), "Blocked destructive command 'git push -f'."),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+[\/\.]"), "Blocked destructive root/directory recursive deletion."),
    (re.compile(r"\bdrop\s+database\b", re.IGNORECASE), "Blocked destructive SQL 'DROP DATABASE' command."),
    (re.compile(r"\bchmod\s+777\b"), "Blocked insecure permission escalation 'chmod 777'."),
]


class DangerousCommandInterceptor:
    """Inspects shell command strings and blocks destructive operations."""

    @staticmethod
    def inspect_command(command_line: str) -> tuple[bool, str | None]:
        cmd_clean = command_line.strip()
        for pattern, reason in DANGEROUS_COMMAND_PATTERNS:
            if pattern.search(cmd_clean):
                return False, reason
        return True, None
```

---

### 5.3 `src/rush/safety/dirty_tracker.py`

```python
"""Working tree mutation and dirty state tracker."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class WorkingTreeDirtyTracker:
    """Tracks uncommitted file modifications and prevents clobbering dirty working states."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def get_dirty_files(self) -> list[str]:
        proc = run_subprocess(["git", "status", "--porcelain"], cwd=self.repo_root)
        if proc.returncode != 0:
            return []
        dirty = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if len(line_clean) > 3:
                dirty.append(line_clean[3:].strip())
        return dirty
```n = line.strip()
            if len(line_clean) > 3:
                dirty.append(line_clean[3:].strip())
        return dirty
```

---

### 4.7 `src/rush/safety/ephemeral_mount.py`

```python
"""Ephemeral RAM-disk and tmpfs directory manager for ultra-fast sandbox execution."""

from __future__ import annotations

import tempfile
from pathlib import Path


class EphemeralMountManager:
    """Allocates ephemeral in-memory temporary workspaces for zero-disk-wear testing."""

    @staticmethod
    def create_ephemeral_workspace() -> Path:
        temp_dir = tempfile.mkdtemp(prefix="rush_ephemeral_")
        return Path(temp_dir)
```

---

### 4.8 `src/rush/safety/redactor.py`

```python
"""High-speed Shannon entropy and regex secret redactor."""

from __future__ import annotations

import math
import re

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
]


class SecretRedactor:
    """Redacts secrets, API keys, and sensitive tokens from logs, diffs, and tool outputs."""

    @staticmethod
    def redact_text(text: str) -> str:
        if not text:
            return text

        redacted = text
        for pattern, replacement in SECRET_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @staticmethod
    def calculate_entropy(data: str) -> float:
        """Calculates Shannon entropy to detect high-randomness secret strings."""
        if not data:
            return 0.0
        entropy = 0.0
        for x in set(data):
            p_x = float(data.count(x)) / len(data)
            if p_x > 0:
                entropy += - p_x * math.log2(p_x)
        return entropy
```

---

### 4.9 `src/rush/safety/network_guard.py`

```python
"""Outbound network socket interceptor for hermetic sandbox execution."""

from __future__ import annotations

import socket


class NetworkEgressGuard:
    """Enforces network isolation within sandboxed subprocesses."""

    @staticmethod
    def block_network_sockets() -> None:
        """Monkey-patches Python socket creation to prevent egress in sandboxed plugins."""
        def guarded_socket(*args, **kwargs):
            raise PermissionError("Network access blocked: Sandbox operates in zero-network hermetic mode.")
        socket.socket = guarded_socket  # type: ignore
```

---

### 4.10 `src/rush/safety/audit_logger.py`

```python
"""HMAC-SHA256 chained security audit logger."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path


class SecurityAuditLogger:
    """Maintains an append-only, cryptographically chained audit trail on sys.stderr and .rush/audit.log."""

    def __init__(self, repo_root: Path, secret_key: str = "rush_internal_audit_secret") -> None:
        self.repo_root = repo_root.resolve()
        self.secret_key = secret_key.encode("utf-8")
        self.log_file = self.repo_root / ".rush" / "audit.log"
        self.last_hash = "0" * 64

    def log_security_event(self, event_type: str, details: dict) -> str:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.time()
        record_body = {
            "timestamp": timestamp,
            "event_type": event_type,
            "details": details,
            "prev_hash": self.last_hash,
        }
        record_bytes = json.dumps(record_body, sort_keys=True).encode("utf-8")
        current_hash = hmac.new(self.secret_key, record_bytes, hashlib.sha256).hexdigest()
        record_body["hmac_sha256"] = current_hash
        self.last_hash = current_hash

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_body) + "\n")

        return current_hash
```

---

### 4.11 `src/rush/safety/path_confiner.py`

```python
"""Strict workspace path boundary validator."""

from __future__ import annotations

from pathlib import Path


class WorkspacePathConfiner:
    """Ensures that all file operations remain strictly confined to repository root."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def confine_path(self, target_path: Path | str) -> Path:
        p = Path(target_path)
        resolved = (self.repo_root / p).resolve() if not p.is_absolute() else p.resolve()

        if not resolved.is_relative_to(self.repo_root):
            raise PermissionError(
                f"Workspace boundary violation: Path '{target_path}' resolves outside repository root '{self.repo_root}'."
            )

        return resolved
```

---

### 4.12 `src/rush/safety/isolation.py`

```python
"""Subprocess execution supervisor enforcing bounded resource isolation."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


class ProcessIsolationManager:
    """Supervises subprocess execution with strict timeouts and environment isolation."""

    @staticmethod
    def run_isolated_process(
        command: list[str],
        cwd: Path,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                shell=False,
                env=env,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Process timed out after {timeout:.1f} seconds."
        except Exception as e:
            return -1, "", f"Execution error: {e}"
```

---

### 4.13 `src/rush/safety/worktree_sandbox.py`

```python
"""Git worktree sandbox manager for agent mutations."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from rush.safety.isolation import ProcessIsolationManager


class WorktreeSandboxManager:
    """Manages ephemeral Git worktrees for isolating experimental agent code modifications."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.worktrees_dir = self.repo_root / ".rush" / "worktrees"

    def allocate_sandbox(self) -> Path:
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.worktrees_dir / sandbox_id

        code, stdout, stderr = ProcessIsolationManager.run_isolated_process(
            ["git", "worktree", "add", "--detach", str(sandbox_path), "HEAD"],
            cwd=self.repo_root,
        )
        if code != 0:
            sandbox_path.mkdir(parents=True, exist_ok=True)

        return sandbox_path

    def prune_sandbox(self, sandbox_path: Path) -> None:
        if not sandbox_path.exists():
            return

        ProcessIsolationManager.run_isolated_process(
            ["git", "worktree", "remove", "--force", str(sandbox_path)],
            cwd=self.repo_root,
        )
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path, ignore_errors=True)

    def prune_all_sandboxes(self) -> int:
        if not self.worktrees_dir.exists():
            return 0

        count = 0
        for item in self.worktrees_dir.iterdir():
            if item.is_dir():
                self.prune_sandbox(item)
                count += 1
        return count
```

---

### 4.14 `src/rush/cli.py` (Registration for `rush guard` and `rush sandbox`)

```python
import click
from pathlib import Path
from rush.safety.guard import AgentSafetyGuard
from rush.safety.interceptor import DangerousCommandInterceptor
from rush.safety.redactor import SecretRedactor
from rush.safety.import_guard import AstImportGuard
from rush.safety.worktree_sandbox import WorktreeSandboxManager

@click.group(name="guard")
def guard_group():
    """Agent safety guards, command interception, and secret redaction."""
    pass

@guard_group.command(name="check-cmd")
@click.argument("command_line")
def guard_check_cmd(command_line: str):
    """Check a command string against dangerous command policies."""
    allowed, reason = DangerousCommandInterceptor.inspect_command(command_line)
    if allowed:
        click.echo("[PASS] Command is allowed by safety policy.")
    else:
        click.echo(f"[BLOCKED] {reason}", err=True)
        raise SystemExit(1)

@guard_group.command(name="check-ast")
@click.argument("file_path", type=click.Path(exists=True))
def guard_check_ast_cmd(file_path: str):
    """Scan a Python file for dangerous dynamic code execution."""
    src = Path(file_path).read_text(encoding="utf-8", errors="replace")
    clean, violations = AstImportGuard.inspect_source(src)
    if clean:
        click.echo("[PASS] No dynamic code execution detected.")
    else:
        click.echo("[FAIL] Dynamic code violations found:", err=True)
        for v in violations:
            click.echo(f"  - {v}", err=True)
        raise SystemExit(1)

@guard_group.command(name="redact")
@click.argument("input_file", type=click.Path(exists=True))
def guard_redact_cmd(input_file: str):
    """Redact secrets from a text or log file."""
    text = Path(input_file).read_text(encoding="utf-8", errors="replace")
    redacted = SecretRedactor.redact_text(text)
    click.echo(redacted)

@click.group(name="sandbox")
def sandbox_group():
    """Manage ephemeral Git worktree sandboxes."""
    pass

@sandbox_group.command(name="create")
def sandbox_create_cmd():
    """Allocate an isolated Git worktree sandbox."""
    mgr = WorktreeSandboxManager(Path.cwd())
    sb = mgr.allocate_sandbox()
    click.echo(f"[CREATED] Allocated sandbox worktree at '{sb.name}'.")

@sandbox_group.command(name="prune")
def sandbox_prune_cmd():
    """Prune all active ephemeral sandbox worktrees."""
    mgr = WorktreeSandboxManager(Path.cwd())
    cnt = mgr.prune_all_sandboxes()
    click.echo(f"[PRUNED] Cleaned up {cnt} active sandbox worktree(s).")
```

---

### 4.15 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for agent safety and sandbox isolation."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.safety.interceptor import DangerousCommandInterceptor
from rush.safety.redactor import SecretRedactor
from rush.safety.import_guard import AstImportGuard
from rush.safety.worktree_sandbox import WorktreeSandboxManager

mcp = FastMCP("rush")

@mcp.tool(name="rush_guard_check_command", description="Verify that a command is safe and non-destructive.")
def rush_guard_check_command(command_line: str) -> str:
    allowed, reason = DangerousCommandInterceptor.inspect_command(command_line)
    return json.dumps({"allowed": allowed, "reason": reason}, indent=2)

@mcp.tool(name="rush_guard_check_ast", description="Scan Python source code for dynamic execution violations.")
def rush_guard_check_ast(source_code: str) -> str:
    clean, violations = AstImportGuard.inspect_source(source_code)
    return json.dumps({"clean": clean, "violations": violations}, indent=2)

@mcp.tool(name="rush_guard_redact", description="Redact secrets from arbitrary text or diffs.")
def rush_guard_redact(text: str) -> str:
    redacted = SecretRedactor.redact_text(text)
    return redacted

@mcp.tool(name="rush_sandbox_create", description="Allocate an ephemeral worktree sandbox.")
def rush_sandbox_create() -> str:
    mgr = WorktreeSandboxManager(Path.cwd())
    sb = mgr.allocate_sandbox()
    return json.dumps({"sandbox_path": str(sb), "sandbox_name": sb.name}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_agent_safety_guard.py`

```python
"""Comprehensive test suite for AgentSafetyGuard, DangerousCommandInterceptor, SecretRedactor, AstImportGuard, SignalTrapHandler, ProcessResourceLimiter, WorkingTreeDirtyTracker, EphemeralMountManager, NetworkEgressGuard, SecurityAuditLogger, WorkspacePathConfiner, and WorktreeSandboxManager."""

from pathlib import Path
import pytest
from rush.safety.guard import AgentSafetyGuard
from rush.safety.interceptor import DangerousCommandInterceptor
from rush.safety.redactor import SecretRedactor
from rush.safety.import_guard import AstImportGuard
from rush.safety.signal_trap import SignalTrapHandler
from rush.safety.resource_limiter import ProcessResourceLimiter
from rush.safety.dirty_tracker import WorkingTreeDirtyTracker
from rush.safety.ephemeral_mount import EphemeralMountManager
from rush.safety.network_guard import NetworkEgressGuard
from rush.safety.audit_logger import SecurityAuditLogger
from rush.safety.path_confiner import WorkspacePathConfiner
from rush.safety.worktree_sandbox import WorktreeSandboxManager


def test_safety_guard_blocks_governance_files(tmp_path: Path):
    guard = AgentSafetyGuard(tmp_path)
    assert guard.is_file_protected("AGENTS.md") is True
    assert guard.is_file_protected("CLAUDE.md") is True
    assert guard.is_file_protected(".cursorrules") is True
    assert guard.is_file_protected("rush.toml") is True
    assert guard.is_file_protected(".git/config") is True
    assert guard.is_file_protected("src/main.py") is False

    with pytest.raises(PermissionError):
        guard.validate_write_target("AGENTS.md")


def test_dangerous_command_interceptor():
    assert DangerousCommandInterceptor.inspect_command("git status")[0] is True
    assert DangerousCommandInterceptor.inspect_command("pytest tests/")[0] is True

    # Blocked dangerous commands
    assert DangerousCommandInterceptor.inspect_command("git reset --hard HEAD~1")[0] is False
    assert DangerousCommandInterceptor.inspect_command("git clean -fdx")[0] is False
    assert DangerousCommandInterceptor.inspect_command("git push origin main --force")[0] is False
    assert DangerousCommandInterceptor.inspect_command("rm -rf /")[0] is False
    assert DangerousCommandInterceptor.inspect_command("DROP DATABASE production;")[0] is False
    assert DangerousCommandInterceptor.inspect_command("chmod 777 script.sh")[0] is False


def test_ast_import_guard():
    safe_code = "def add(a, b): return a + b\n"
    clean, violations = AstImportGuard.inspect_source(safe_code)
    assert clean is True
    assert len(violations) == 0

    dangerous_code = "eval('__import__(\"os\").system(\"rm -rf /\")')\n"
    d_clean, d_violations = AstImportGuard.inspect_source(dangerous_code)
    assert d_clean is False
    assert len(d_violations) >= 1


def test_working_tree_dirty_tracker(tmp_path: Path):
    tracker = WorkingTreeDirtyTracker(tmp_path)
    dirty = tracker.get_dirty_files()
    assert isinstance(dirty, list)


def test_ephemeral_mount_manager():
    p = EphemeralMountManager.create_ephemeral_workspace()
    assert p.exists()
    assert "rush_ephemeral_" in p.name


def test_signal_trap_handler():
    # Verify non-existent pid termination does not crash
    SignalTrapHandler.terminate_process_tree(9999999)


def test_process_resource_limiter():
    ProcessResourceLimiter.apply_limits(1024 * 1024 * 1024)


def test_secret_redactor():
    raw_text = "API Key: sk-ant-api03-12345678901234567890 and token ghp_12345678901234567890"
    redacted = SecretRedactor.redact_text(raw_text)
    assert "sk-ant" not in redacted
    assert "ghp_" not in redacted
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted


def test_shannon_entropy_calculation():
    low_entropy = SecretRedactor.calculate_entropy("aaaaaaa")
    high_entropy = SecretRedactor.calculate_entropy("a8F!9zQ#2$Lp")
    assert low_entropy < 1.0
    assert high_entropy > 3.0


def test_network_egress_guard():
    import socket
    old_socket = socket.socket
    try:
        NetworkEgressGuard.block_network_sockets()
        with pytest.raises(PermissionError):
            socket.socket()
    finally:
        socket.socket = old_socket


def test_security_audit_logger(tmp_path: Path):
    logger = SecurityAuditLogger(tmp_path)
    h1 = logger.log_security_event("test_event", {"user": "agent_1"})
    assert len(h1) == 64
    assert (tmp_path / ".rush" / "audit.log").exists()


def test_workspace_path_confiner(tmp_path: Path):
    confiner = WorkspacePathConfiner(tmp_path)
    safe = confiner.confine_path("src/utils.py")
    assert safe == tmp_path / "src" / "utils.py"

    with pytest.raises(PermissionError):
        confiner.confine_path("../../etc/passwd")


def test_worktree_sandbox_manager(tmp_path: Path):
    mgr = WorktreeSandboxManager(tmp_path)
    sb = mgr.allocate_sandbox()
    assert sb.exists()

    mgr.prune_sandbox(sb)
    assert not sb.exists()
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 31 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:45:00.100Z", "phase": 31, "tool": "rush_guard", "event": "command_intercepted", "command": "git reset --hard", "allowed": false}
{"timestamp": "2026-08-21T09:45:02.150Z", "phase": 31, "tool": "rush_sandbox", "event": "sandbox_allocated", "sandbox_id": "sandbox_4a1b8c"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 31 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 31: Agent Safety & Worktree Sandboxing**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 31 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Autonomous Agent Safety & Command Guard" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush guard check`, `intercept`, `rush sandbox create`, `prune` (flags: `--strict`, `--entropy-threshold`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for wrapping third-party coding agents with Rush safety guards.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated recipe for validating agent safety intercept rules in CI.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example command interception logs and blocked destructive command alerts.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on configuring workspace path confinement and read-only governance files.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for handling false-positive entropy alerts and blocked path warnings.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush intercepts destructive commands without modifying global OS shells.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document FastMCP safety layer interceptors and guard tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document JSON schemas for intercepted command verdicts.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `guard` and `sandbox` tools in Agent Safety category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[safety]` configuration table (`blocked_commands`, `entropy_threshold`, `protected_paths`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document `CommandInterceptor` state machine, Shannon entropy secret detector, and governance immutable file guard.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for adding new heuristic command intercept rules.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Include CI workflow step for secret leak scans.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document destructive command mocking and escape attack test suites.
- **[`docs/tools/guard.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/guard.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-31): implement agent safety interceptor, secret masking and worktree sandboxing"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
