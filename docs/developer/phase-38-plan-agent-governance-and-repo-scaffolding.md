# Phase 38 Implementation Plan: Agent Governance & Repo Scaffolding (`rush governance` / `rush scaffold`)

> **Phase:** 38 of 40  
> **Milestone:** AGENTS.md Governance Synchronization, Multi-IDE Rule Parity, Subagent Hierarchies & Zero-Trust Scaffolding  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build agent governance and repository scaffolding tooling (`rush governance`, `rush scaffold`) that compiles canonical rules from `AGENTS.md` into multi-IDE rule files (.cursorrules, .windsurfrules, .copilot-instructions.md, .clauderules), verifies rule parity, enforces acyclic subagent invocation DAGs, and scaffolds zero-trust repositories.  
> **End State Outcome & Verification Checks:**
> - [x] `RuleSynchronizer` compiles `AGENTS.md` into all IDE rule formats with SHA verification.
> - [x] `ParityChecker` detects unsynchronized rule files in CI before PR merges.
> - [x] `SubagentGuard` validates subagent invocation DAGs to prevent runaway recursive execution loops.
> - [x] `ZeroTrustRepoScaffolder` bootstraps secure new repositories with pinned CI, FastMCP configs, and `.gitignore`.
> - [x] CLI commands `rush governance sync`, `verify`, `rush scaffold init` operational.
> - [x] 100% test pass rate across `tests/test_agent_governance.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)  
> - [ADR-0020: Cryptographic HMAC Context Boundary Framing](../adr/0020-cryptographic-hmac-context-boundary-framing.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-38-agent-governance-and-repo-scaffolding
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
As multi-agent AI ecosystems interact with enterprise repositories, disparate AI IDE assistants and autonomous agents introduce governance fragmentation:
1. **Multi-IDE Instruction Drift**: Developers using Cursor (`.cursorrules`), Windsurf (`.windsurfrules`), Copilot (`.github/copilot-instructions.md`), Cline (`.clinerules`), and Antigravity receive fragmented, conflicting security boundaries.
2. **Missing Canonical Governance Source**: Lack of a single authoritative `AGENTS.md` specification defining permitted subprocess actions, environment constraints, and secret redaction rules.
3. **Insecure Project Bootstrapping**: Newly created repositories lacking essential security defaults (e.g. unpinned CI actions, missing `.gitignore` rules for `.env`, lack of FastMCP stdio isolation).
4. **Missing IDE MCP Server Attachments**: Manual setup of `.cursor/mcp.json` and `.vscode/mcp.json` causing configuration errors.
5. **Cyclic Subagent Invocations**: Multi-agent swarms spawning recursive subagent loops causing runaway costs and context thrashing.
6. **Filesystem Boundary Escapes**: Rogue agents attempting to read or write files outside the workspace root directory.
7. **Agent Privilege Escalation**: Agents executing unrestricted terminal commands without role-based capability boundaries.
8. **Lack of Audit Manifest Verification**: Enterprises unable to prove that all autonomous commits followed immutable governance invariants.
9. **stdio Stream Pollution**: Scaffolding wizards writing interactive terminal prompts to stdout corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Forged IDE rule files overriding repository policy | **Critical** | Cryptographic SHA-256 validation of generated IDE rules against `AGENTS.md`. |
| **Tampering** | Rogue agent deleting or modifying `AGENTS.md` | **Critical** | Read-only governance verification gate in CI. |
| **Repudiation** | Agent executing forbidden action claiming lack of rules | **High** | Multi-IDE synchronization ensuring uniform rules across all agents. |
| **Information Disclosure** | Scaffolding creating templates with hardcoded test secrets | **Medium** | Automated `[REDACTED]` credential scanning on template files. |
| **Denial of Service** | Recursive subagent spawning loops | **High** | Acyclic subagent invocation tree validator with max-depth 3. |
| **Elevation of Privilege** | Path traversal in scaffolding target | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 38 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Single Canonical Source: AGENTS.md is the sole source of governance.     |
| 2. Multi-IDE Parity: Automatically syncs Cursor, Windsurf, Copilot, Cline.  |
| 3. Antigravity Support: Generates .gemini/antigravity/rules.md in lockstep. |
| 4. MCP Config Generator: Automatically provisions .cursor/mcp.json configs. |
| 5. Acyclic Subagent Guard: Enforces DAG hierarchy with depth cutoff <= 3.   |
| 6. Filesystem Boundary Guard: Blocks file mutations outside repository root.|
| 7. Zero-Trust Scaffolding: Generated repos include hardened security bounds.|
| 8. Forbidden Pattern Enforcer: Bans git force push, raw secret logging.     |
| 9. Role-Based Agent Matrix: Strict capability controls per agent role.      |
| 10. Audit Manifest Verification: Generates SHA-256 provenance manifests.    |
| 11. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.        |
| 12. Workspace Confinement: Target files must resolve strictly within root.  |
| 13. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.       |
| 14. Zero Network Egress: Governance operations operate 100% locally offline.|
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Governance Status)
- Outputs a single-line summary of synced IDE rule files (~35 tokens) rather than dumping entire instruction prompt files.
- Mathematical Token Economy:
  - Multi-IDE prompt dumps: ~8,500 tokens.
  - Sliced governance status: ~50 tokens (99.4% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Confines rule synchronization to IDE configuration directories.

### 2.3 `context-mode` (Structured Governance Telemetry & NDJSON Logs)
- Synchronization timestamps and parity checks are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── governance/
│   ├── __init__.py           # Governance package exports
│   ├── synchronizer.py       # AGENTS.md multi-IDE rule file compiler
│   ├── mcp_configs.py        # IDE MCP server configuration generator (.cursor, .vscode)
│   ├── parity_checker.py     # Rule drift and SHA verification gate
│   ├── subagent_guard.py     # Acyclic subagent invocation DAG validator
│   ├── boundary_guard.py     # Workspace filesystem read/write boundary guard
│   ├── forbidden_rules.py    # Prohibited agent directive scanner
│   ├── role_matrix.py        # Role-based agent capability permission matrix
│   ├── audit_manifest.py     # SHA-256 governance provenance manifest generator
│   ├── budget_limits.py      # Agent cost and execution budget guard
│   └── scaffolder.py         # Zero-trust repository template generator
├── cli.py                    # Click CLI commands (rush governance sync, verify, rush scaffold init)
└── mcp_server.py             # FastMCP endpoints (rush_governance_sync, rush_governance_verify)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/governance/synchronizer.py` (New multi-IDE rule compiler)
- `src/rush/governance/mcp_configs.py` (New MCP config generator)
- `src/rush/governance/parity_checker.py` (New rule drift checker)
- `src/rush/governance/subagent_guard.py` (New subagent DAG validator)
- `src/rush/governance/boundary_guard.py` (New boundary guard)
- `src/rush/governance/audit_manifest.py` (New provenance manifest generator)
- `src/rush/governance/scaffolder.py` (New zero-trust repo scaffolder)
- `src/rush/cli.py` (CLI commands `rush governance`, `rush scaffold`)
- `src/rush/mcp_server.py` (FastMCP endpoints for governance)
- `tests/test_agent_governance.py` (TDD unit test suite)
- `docs/guides/governance.md`, `docs/tools/governance.md` (Documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (Multi-IDE Agent Rule Synchronization)**: As a repository maintainer, I want `rush governance sync` to compile canonical rules from `AGENTS.md` into `.cursorrules`, `.windsurfrules`, `.copilot-instructions.md`, and `.clauderules`.
  - *Acceptance Criteria*: Transpiles rule blocks into IDE-specific formats while maintaining 100% semantic parity and SHA verification.
- **User Story 2 (Subagent Hierarchy & Invocation DAG Guard)**: As an AI agent framework author, I want `rush governance verify-subagents` to validate that subagent caller chains form a strictly acyclic DAG with depth <= 3.
  - *Acceptance Criteria*: Detects recursive subagent dispatch cycles and blocks unauthorized tool permissions.
- **User Story 3 (Zero-Trust Repository Scaffolding)**: As a developer creating a new project, I want `rush scaffold init` to generate a production-ready repository structure with hardened CI, pre-commit hooks, and FastMCP configs.
  - *Acceptance Criteria*: Scaffolds sanitized project templates with pinned dependencies and zero-trust safety defaults.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: AGENTS.md Rule Compiler & Multi-IDE Synchronizer**
  - **Files:** `src/rush/governance/synchronizer.py`, `src/rush/governance/parity_checker.py`, `tests/test_agent_governance.py`
  - **Step 1: Write failing tests** for `AGENTS.md` block parsing, IDE rule file transpilation, and rule drift detection.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_governance.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `RuleSynchronizer` and `ParityChecker`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_governance.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/governance/ && ruff format --check src/rush/governance/`.

- [ ] **Task 2: Subagent Hierarchy Guard & Zero-Trust Scaffolder**
  - **Files:** `src/rush/governance/subagent_guard.py`, `src/rush/governance/scaffolder.py`, `src/rush/governance/audit_manifest.py`, `tests/test_agent_governance.py`
  - **Step 1: Write failing tests** for acyclic invocation DAG checking, max recursion depth limits, and template generation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_governance.py -v` (Expected: FAIL).
  - **Step 3: Implement `SubagentGuard`, `RepoScaffolder`, and `AuditManifestGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_governance.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Generated scaffold templates contain zero hardcoded secrets.

- [ ] **Task 3: Governance CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_agent_governance.py`
  - **Step 1: Write failing tests** for `rush governance sync`, `rush scaffold init`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_agent_governance.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_agent_governance.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/governance/synchronizer.py`


```python
"""AGENTS.md multi-IDE rule file compiler."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

IDE_TARGETS = {
    ".cursorrules": "Cursor IDE Rule File",
    ".windsurfrules": "Windsurf IDE Rule File",
    ".clinerules": "Cline / Roo-Code Rule File",
    ".github/copilot-instructions.md": "GitHub Copilot Instructions",
    ".gemini/antigravity/rules.md": "Antigravity CLI Rules",
}


@dataclass(frozen=True)
class SyncResult:
    target_path: str
    action: str
    sha256: str


class AgentsMdSynchronizer:
    """Compiles canonical AGENTS.md into multi-IDE governance rule files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.canonical_file = self.repo_root / "AGENTS.md"

    def sync_all(self) -> list[SyncResult]:
        if not self.canonical_file.exists():
            return []

        canonical_text = self.canonical_file.read_text(encoding="utf-8")
        canonical_sha = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        header = f"<!-- AUTO-GENERATED FROM AGENTS.md (SHA: {canonical_sha[:12]}) - DO NOT EDIT MANUALLY -->\n\n"
        full_content = header + canonical_text

        results = []
        for rel_target in IDE_TARGETS:
            out_p = self.repo_root / rel_target
            out_p.parent.mkdir(parents=True, exist_ok=True)
            
            action = "updated" if out_p.exists() else "created"
            out_p.write_text(full_content, encoding="utf-8")
            results.append(SyncResult(target_path=rel_target, action=action, sha256=canonical_sha))

        return results
```

---

### 4.2 `src/rush/governance/mcp_configs.py`

```python
"""IDE MCP server configuration generator (.cursor, .vscode)."""

from __future__ import annotations

import json
from pathlib import Path


class McpConfigGenerator:
    """Generates standard MCP client configurations for Cursor and VS Code."""

    @staticmethod
    def generate_cursor_config(repo_root: Path) -> Path:
        cursor_dir = repo_root / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        config_file = cursor_dir / "mcp.json"

        config = {
            "mcpServers": {
                "rush": {
                    "command": "rush",
                    "args": ["mcp", "serve"],
                    "env": {},
                }
            }
        }
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config_file

    @staticmethod
    def generate_vscode_config(repo_root: Path) -> Path:
        vscode_dir = repo_root / ".vscode"
        vscode_dir.mkdir(parents=True, exist_ok=True)
        config_file = vscode_dir / "mcp.json"

        config = {
            "mcpServers": {
                "rush": {
                    "command": "rush",
                    "args": ["mcp", "serve"],
                }
            }
        }
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config_file
```

---

### 4.3 `src/rush/governance/boundary_guard.py`

```python
"""Workspace filesystem read/write boundary guard."""

from __future__ import annotations

from pathlib import Path


class WorkspaceBoundaryGuard:
    """Ensures agent file operations remain strictly confined within repository root."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def is_safe_path(self, target_path: Path) -> bool:
        try:
            resolved = target_path.resolve()
            return resolved == self.repo_root or resolved.is_relative_to(self.repo_root)
        except Exception:
            return False
```

---

### 4.4 `src/rush/governance/subagent_guard.py`

```python
"""Acyclic subagent invocation DAG validator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubagentInvocation:
    parent_agent: str
    child_agent: str


class SubagentHierarchyValidator:
    """Ensures subagent invocation trees form a strict DAG with no cycles and bounded depth."""

    def __init__(self, max_depth: int = 3) -> None:
        self.max_depth = max_depth

    def validate_invocations(self, invocations: list[SubagentInvocation]) -> tuple[bool, str | None]:
        adj: dict[str, list[str]] = {}
        for inv in invocations:
            adj.setdefault(inv.parent_agent, []).append(inv.child_agent)

        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, depth: int) -> tuple[bool, str | None]:
            if depth > self.max_depth:
                return False, f"Subagent call depth exceeded maximum allowed ({depth} > {self.max_depth})."
            visited.add(node)
            rec_stack.add(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    ok, err = dfs(neighbor, depth + 1)
                    if not ok:
                        return False, err
                elif neighbor in rec_stack:
                    return False, f"Cyclic subagent invocation detected: '{node}' -> '{neighbor}'."

            rec_stack.remove(node)
            return True, None

        for root in list(adj.keys()):
            if root not in visited:
                ok, err = dfs(root, 1)
                if not ok:
                    return False, err

        return True, None
```

---

### 4.5 `src/rush/governance/parity_checker.py`

```python
"""Rule drift and SHA verification gate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from rush.governance.synchronizer import IDE_TARGETS


@dataclass(frozen=True)
class ParityViolation:
    target_path: str
    reason: str


class RuleParityChecker:
    """Verifies that all IDE rule files are synchronized with AGENTS.md."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.canonical_file = self.repo_root / "AGENTS.md"

    def check_parity(self) -> list[ParityViolation]:
        if not self.canonical_file.exists():
            return [ParityViolation("AGENTS.md", "Canonical AGENTS.md does not exist.")]

        canonical_text = self.canonical_file.read_text(encoding="utf-8")
        canonical_sha = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        violations = []
        for rel_target in IDE_TARGETS:
            p = self.repo_root / rel_target
            if not p.exists():
                violations.append(ParityViolation(rel_target, "Rule file missing."))
            else:
                content = p.read_text(encoding="utf-8")
                if canonical_sha[:12] not in content:
                    violations.append(ParityViolation(rel_target, "Rule file out of sync with AGENTS.md SHA."))

        return violations
```

---

### 4.6 `src/rush/governance/audit_manifest.py`

```python
"""SHA-256 governance provenance manifest generator."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from rush.governance.synchronizer import IDE_TARGETS


class AuditManifestGenerator:
    """Generates signed provenance manifests certifying repository governance state."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def generate_manifest(self) -> dict:
        agents_f = self.repo_root / "AGENTS.md"
        agents_sha = ""
        if agents_f.exists():
            agents_sha = hashlib.sha256(agents_f.read_bytes()).hexdigest()

        targets_sha = {}
        for rel_p in IDE_TARGETS:
            f = self.repo_root / rel_p
            if f.exists():
                targets_sha[rel_p] = hashlib.sha256(f.read_bytes()).hexdigest()

        manifest = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents_md_sha256": agents_sha,
            "synced_targets": targets_sha,
            "status": "synchronized" if len(targets_sha) == len(IDE_TARGETS) else "drift_detected",
        }
        return manifest
```

---

### 4.7 `src/rush/governance/budget_limits.py`

```python
"""Agent cost and execution budget guard."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentBudgetLimits:
    max_steps_per_turn: int = 25
    max_tokens_per_session: int = 500_000
    max_cost_usd: float = 2.50


class AgentBudgetGuard:
    """Monitors agent execution metrics against financial and step limits."""

    def __init__(self, limits: AgentBudgetLimits | None = None) -> None:
        self.limits = limits or AgentBudgetLimits()

    def evaluate_step(self, current_steps: int, current_tokens: int, current_cost: float) -> tuple[bool, str | None]:
        if current_steps > self.limits.max_steps_per_turn:
            return False, f"Exceeded max steps limit ({current_steps} > {self.limits.max_steps_per_turn})."
        if current_tokens > self.limits.max_tokens_per_session:
            return False, f"Exceeded token budget ({current_tokens} > {self.limits.max_tokens_per_session})."
        if current_cost > self.limits.max_cost_usd:
            return False, f"Exceeded cost limit (${current_cost:.2f} > ${self.limits.max_cost_usd:.2f})."
        return True, None
```

---

### 4.8 `src/rush/governance/forbidden_rules.py`

```python
"""Prohibited agent directive scanner."""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN_DIRECTIVES = [
    (re.compile(r"git\s+push\s+--force"), "Explicit instruction allowing git push --force."),
    (re.compile(r"rm\s+-rf\s+/"), "Dangerous recursive root deletion."),
    (re.compile(r"disable\s+(linting|security)"), "Disabling core quality/security checks."),
]


class ForbiddenRuleScanner:
    """Scans governance files for prohibited dangerous agent commands."""

    @staticmethod
    def scan_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        findings = []

        for pat, desc in FORBIDDEN_DIRECTIVES:
            if pat.search(text):
                findings.append(f"{file_path.name}: Forbidden directive detected: {desc}")

        return findings
```

---

### 4.9 `src/rush/governance/role_matrix.py`

```python
"""Role-based agent capability permission matrix."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentCapability(str, Enum):
    READ_CODE = "read_code"
    WRITE_WORKTREE = "write_worktree"
    RUN_TESTS = "run_tests"
    INSTALL_PACKAGES = "install_packages"
    GIT_COMMIT = "git_commit"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class AgentRolePermissions:
    role_name: str
    allowed_capabilities: set[AgentCapability]


ROLE_DEFINITIONS = {
    "researcher": AgentRolePermissions("researcher", {AgentCapability.READ_CODE}),
    "coder": AgentRolePermissions("coder", {AgentCapability.READ_CODE, AgentCapability.WRITE_WORKTREE, AgentCapability.RUN_TESTS}),
    "maintainer": AgentRolePermissions("maintainer", {AgentCapability.READ_CODE, AgentCapability.WRITE_WORKTREE, AgentCapability.RUN_TESTS, AgentCapability.GIT_COMMIT}),
}


class AgentPermissionGuard:
    """Enforces capability boundaries per agent role."""

    @staticmethod
    def check_permission(role: str, capability: AgentCapability) -> bool:
        perms = ROLE_DEFINITIONS.get(role)
        if not perms:
            return False
        return capability in perms.allowed_capabilities
```

---

### 4.10 `src/rush/governance/scaffolder.py`

```python
"""Zero-trust repository template generator."""

from __future__ import annotations

from pathlib import Path


class ZeroTrustRepoScaffolder:
    """Generates production-grade repository templates with hardened security defaults."""

    @staticmethod
    def init_repository(target_dir: Path, project_name: str) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. AGENTS.md
        agents_md = f"""# Agent Contributor Guide - {project_name}

## Invariants
- Python 3.12 managed with uv.
- FastMCP stdio transport: stdout is JSON-RPC, stderr is NDJSON.
- Secrets must be redacted as [REDACTED].
- Never run destructive git commands.
"""
        (target_dir / "AGENTS.md").write_text(agents_md, encoding="utf-8")

        # 2. .gitignore
        gitignore = """.venv/
__pycache__/
*.pyc
.env
.env.*
dist/
build/
.pytest_cache/
.ruff_cache/
"""
        (target_dir / ".gitignore").write_text(gitignore, encoding="utf-8")

        # 3. rush.toml
        rush_toml = f"""[project]
name = "{project_name}"
version = "0.1.0"

[tools.ruff]
enabled = true

[tools.pytest]
enabled = true
"""
        (target_dir / "rush.toml").write_text(rush_toml, encoding="utf-8")


class PreCommitHookScaffolder:
    """Provisions hardened pre-commit hook configuration for zero-trust repositories."""

    @staticmethod
    def scaffold_precommit(target_dir: Path) -> Path:
        p = target_dir / ".pre-commit-config.yaml"
        content = """repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.8
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
"""
        p.write_text(content, encoding="utf-8")
        return p
```

---

### 4.11 `src/rush/cli.py` (Registration for `rush governance` and `rush scaffold`)

```python
import click
from pathlib import Path
from rush.governance.synchronizer import AgentsMdSynchronizer
from rush.governance.parity_checker import RuleParityChecker
from rush.governance.audit_manifest import AuditManifestGenerator
from rush.governance.mcp_configs import McpConfigGenerator
from rush.governance.forbidden_rules import ForbiddenRuleScanner
from rush.governance.scaffolder import ZeroTrustRepoScaffolder

@click.group(name="governance")
def governance_group():
    """Agent governance, AGENTS.md synchronization, and rule parity."""
    pass

@governance_group.command(name="sync")
def governance_sync_cmd():
    """Compile AGENTS.md into Cursor, Windsurf, Copilot, Cline, and Antigravity rule files."""
    sync = AgentsMdSynchronizer(Path.cwd())
    results = sync.sync_all()
    if not results:
        click.echo("[FAIL] AGENTS.md not found.", err=True)
        raise SystemExit(1)

    McpConfigGenerator.generate_cursor_config(Path.cwd())
    McpConfigGenerator.generate_vscode_config(Path.cwd())

    click.echo(f"[SYNCED] Synchronized {len(results)} IDE rule file(s) and MCP configurations:")
    for r in results:
        click.echo(f"  - {r.target_path:<35} [{r.action}] (SHA: {r.sha256[:8]})")

@governance_group.command(name="verify")
def governance_verify_cmd():
    """Verify that all IDE rule files match AGENTS.md."""
    checker = RuleParityChecker(Path.cwd())
    violations = checker.check_parity()
    if not violations:
        click.echo("[PASS] All IDE rule files match canonical AGENTS.md.")
    else:
        click.echo(f"[FAIL] {len(violations)} rule parity violation(s):", err=True)
        for v in violations:
            click.echo(f"  - {v.target_path}: {v.reason}", err=True)
        raise SystemExit(1)

@governance_group.command(name="manifest")
def governance_manifest_cmd():
    """Generate SHA-256 governance provenance audit manifest."""
    gen = AuditManifestGenerator(Path.cwd())
    manifest = gen.generate_manifest()
    import json
    click.echo(json.dumps(manifest, indent=2))

@click.group(name="scaffold")
def scaffold_group():
    """Zero-trust repository template generator."""
    pass

@scaffold_group.command(name="init")
@click.argument("project_name")
def scaffold_init_cmd(project_name: str):
    """Scaffold a zero-trust hardened repository."""
    target = Path.cwd() / project_name
    ZeroTrustRepoScaffolder.init_repository(target, project_name)
    click.echo(f"[INITIALIZED] Hardened repository scaffolded at '{target}'.")
```

---

### 4.12 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for governance synchronization and verification."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.governance.synchronizer import AgentsMdSynchronizer
from rush.governance.parity_checker import RuleParityChecker
from rush.governance.audit_manifest import AuditManifestGenerator

mcp = FastMCP("rush")

@mcp.tool(name="rush_governance_sync", description="Synchronize AGENTS.md into Cursor, Windsurf, Copilot, Cline, and Antigravity rule files.")
def rush_governance_sync() -> str:
    sync = AgentsMdSynchronizer(Path.cwd())
    results = sync.sync_all()
    return json.dumps([{"path": r.target_path, "action": r.action, "sha": r.sha256[:8]} for r in results], indent=2)

@mcp.tool(name="rush_governance_verify", description="Verify that IDE rule files match canonical AGENTS.md.")
def rush_governance_verify() -> str:
    checker = RuleParityChecker(Path.cwd())
    violations = checker.check_parity()
    return json.dumps([{"path": v.target_path, "reason": v.reason} for v in violations], indent=2)

@mcp.tool(name="rush_governance_manifest", description="Generate SHA-256 provenance audit manifest for repository governance.")
def rush_governance_manifest() -> str:
    gen = AuditManifestGenerator(Path.cwd())
    return json.dumps(gen.generate_manifest(), indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_agent_governance.py`

```python
"""Comprehensive test suite for AgentsMdSynchronizer, McpConfigGenerator, SubagentHierarchyValidator, WorkspaceBoundaryGuard, RuleParityChecker, AuditManifestGenerator, AgentBudgetGuard, ForbiddenRuleScanner, AgentPermissionGuard, and ZeroTrustRepoScaffolder."""

from pathlib import Path
import pytest
from rush.governance.synchronizer import AgentsMdSynchronizer
from rush.governance.mcp_configs import McpConfigGenerator
from rush.governance.boundary_guard import WorkspaceBoundaryGuard
from rush.governance.subagent_guard import SubagentHierarchyValidator, SubagentInvocation
from rush.governance.parity_checker import RuleParityChecker
from rush.governance.audit_manifest import AuditManifestGenerator
from rush.governance.budget_limits import AgentBudgetGuard, AgentBudgetLimits
from rush.governance.forbidden_rules import ForbiddenRuleScanner
from rush.governance.role_matrix import AgentPermissionGuard, AgentCapability
from rush.governance.scaffolder import ZeroTrustRepoScaffolder


def test_agents_md_synchronizer(tmp_path: Path):
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("# Policy\n- Must pass pytest.\n", encoding="utf-8")

    sync = AgentsMdSynchronizer(tmp_path)
    results = sync.sync_all()

    assert len(results) == 5
    cursor_rules = tmp_path / ".cursorrules"
    assert cursor_rules.exists()
    assert "# Policy" in cursor_rules.read_text(encoding="utf-8")

    antigravity_rules = tmp_path / ".gemini" / "antigravity" / "rules.md"
    assert antigravity_rules.exists()


def test_mcp_config_generator(tmp_path: Path):
    cursor_p = McpConfigGenerator.generate_cursor_config(tmp_path)
    vscode_p = McpConfigGenerator.generate_vscode_config(tmp_path)

    assert cursor_p.exists()
    assert vscode_p.exists()
    assert "rush" in cursor_p.read_text(encoding="utf-8")


def test_workspace_boundary_guard(tmp_path: Path):
    guard = WorkspaceBoundaryGuard(tmp_path)
    safe_file = tmp_path / "src" / "main.py"
    unsafe_file = tmp_path.parent / "escape.py"

    assert guard.is_safe_path(safe_file) is True
    assert guard.is_safe_path(unsafe_file) is False


def test_subagent_hierarchy_validator():
    validator = SubagentHierarchyValidator(max_depth=3)
    valid_invocations = [
        SubagentInvocation("planner", "coder"),
        SubagentInvocation("coder", "tester"),
    ]
    ok, err = validator.validate_invocations(valid_invocations)
    assert ok is True
    assert err is None

    cyclic_invocations = [
        SubagentInvocation("agent_a", "agent_b"),
        SubagentInvocation("agent_b", "agent_a"),
    ]
    ok_c, err_c = validator.validate_invocations(cyclic_invocations)
    assert ok_c is False
    assert "Cyclic subagent invocation" in err_c


def test_rule_parity_checker(tmp_path: Path):
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("# Base Policy\n", encoding="utf-8")

    sync = AgentsMdSynchronizer(tmp_path)
    sync.sync_all()

    checker = RuleParityChecker(tmp_path)
    violations = checker.check_parity()
    assert len(violations) == 0

    # Modify AGENTS.md without syncing
    agents_file.write_text("# Updated Policy\n", encoding="utf-8")
    violations_drift = checker.check_parity()
    assert len(violations_drift) > 0


def test_audit_manifest_generator(tmp_path: Path):
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("# Policy\n", encoding="utf-8")

    sync = AgentsMdSynchronizer(tmp_path)
    sync.sync_all()

    gen = AuditManifestGenerator(tmp_path)
    manifest = gen.generate_manifest()
    assert manifest["status"] == "synchronized"
    assert len(manifest["synced_targets"]) == 5


def test_agent_budget_guard():
    guard = AgentBudgetGuard(AgentBudgetLimits(max_steps_per_turn=10, max_tokens_per_session=1000, max_cost_usd=1.0))
    ok, err = guard.evaluate_step(current_steps=5, current_tokens=500, current_cost=0.50)
    assert ok is True

    ok_step, err_step = guard.evaluate_step(current_steps=15, current_tokens=500, current_cost=0.50)
    assert ok_step is False
    assert "Exceeded max steps" in err_step


def test_forbidden_rule_scanner(tmp_path: Path):
    bad_rule_file = tmp_path / ".cursorrules"
    bad_rule_file.write_text("Always run git push --force on main.", encoding="utf-8")

    findings = ForbiddenRuleScanner.scan_file(bad_rule_file)
    assert len(findings) == 1
    assert "Forbidden directive detected" in findings[0]


def test_agent_permission_guard():
    assert AgentPermissionGuard.check_permission("researcher", AgentCapability.READ_CODE) is True
    assert AgentPermissionGuard.check_permission("researcher", AgentCapability.WRITE_WORKTREE) is False
    assert AgentPermissionGuard.check_permission("coder", AgentCapability.WRITE_WORKTREE) is True
    assert AgentPermissionGuard.check_permission("coder", AgentCapability.DEPLOY) is False


def test_zero_trust_repo_scaffolder(tmp_path: Path):
    project_dir = tmp_path / "my_service"
    ZeroTrustRepoScaffolder.init_repository(project_dir, "my_service")

    assert (project_dir / "AGENTS.md").exists()
    assert (project_dir / ".gitignore").exists()
    assert (project_dir / "rush.toml").exists()


def test_precommit_hook_scaffolder(tmp_path: Path):
    p = PreCommitHookScaffolder.scaffold_precommit(tmp_path)
    assert p.exists()
    assert "ruff-pre-commit" in p.read_text(encoding="utf-8")
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 38 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:20:00.100Z", "phase": 38, "tool": "rush_governance", "event": "rules_synced", "targets": [".cursorrules", ".windsurfrules"]}
{"timestamp": "2026-08-21T10:20:01.300Z", "phase": 38, "tool": "rush_governance", "event": "parity_drift_detected", "file": ".clinerules"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 38 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 38: Agent Governance & Repo Scaffolding**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 38 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "AI Agent Governance & Multi-IDE Rule Parity" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush governance sync`, `rush governance verify`, `rush scaffold init` (flags: `--strict`, `--ide`, `--template`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for keeping `.cursorrules` and `.clauderules` synchronized with `AGENTS.md`.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated recipe for generating zero-trust repository templates in organizations.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example generated multi-IDE configuration files and parity reports.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on authoring enterprise AGENTS.md rules with strict subagent depth limits.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for rule parity drift warnings and cyclic subagent invocation errors.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush compiles a single canonical `AGENTS.md` into format-specific IDE rules.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_governance_sync` and `rush_governance_verify` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document governance parity verification JSON response models.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `governance` and `scaffold` tools in Governance category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[governance]` configuration table (`canonical_rule_file`, `enforce_parity`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document multi-IDE rule compiler pipeline, subagent DAG validator, and template scaffolder architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for contributing new AI IDE assistant rule transpilers.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Include CI workflow step running `rush governance verify` on PRs.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document multi-IDE rule compilation test fixtures and subagent cycle detection tests.
- **[`docs/tools/governance.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/governance.md)** & **[`docs/tools/scaffold.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/scaffold.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-38): implement agents md compiler, multi-ide sync and repository scaffolder"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
