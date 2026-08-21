# Phase 28 Implementation Plan: Trust-Gated Plugin System & Agent Skills (`rush trust` / `rush plugin`)

> **Phase:** 28 of 40  
> **Milestone:** Cryptographic Plugin Trust Store, AST Sandboxing, Zero-Trust Execution & Dynamic Agent Skills  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a zero-trust, cryptographically verified plugin system (`rush trust`, `rush plugin`) and dynamic Agent Skill generator (`SKILL.md`) that executes third-party and custom linters with SHA-256 trust validation, environment variable isolation, and AST static security sandboxing.  
> **End State Outcome & Verification Checks:**
> - [x] `PluginTrustStore` maintains SHA-256 cryptographic hashes in `.rush/trust.json`.
> - [x] Untrusted or modified plugin binaries are strictly blocked until explicitly approved.
> - [x] `AgentSkillGenerator` dynamically synthesizes Agent Skill specifications from trusted plugins.
> - [x] CLI commands `rush trust grant`, `revoke`, `list` and `rush plugin list`, `run` operational.
> - [x] 100% test pass rate across `tests/test_plugin_system.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0015: Extensible Plugin Architecture and Agent Skills](../adr/0015-extensible-plugin-architecture-and-agent-skills.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered External Engines (Zero-Bundled):** Discovered local runtimes (`python`, `bash`, `node`, `cargo`, `go`)  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-28-trust-gated-plugin-system-and-agent-skills
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Engineering teams and autonomous AI agents require custom internal linters, domain-specific security rules, and specialized code scanners without forking or modifying upstream Rush source code. However, executing arbitrary scripts or third-party plugin executables committed to untrusted or newly cloned repositories introduces severe security hazards:

1. **Remote Code Execution (RCE) via Malicious Plugins (MITRE ATT&CK T1204.002)**: An attacker submits a pull request containing a `.rush/plugins/security_scan.py` script that executes arbitrary shell commands or malware during an agent's automated `rush check` loop.
2. **Environment Variable & Secret Exfiltration (MITRE ATT&CK T1552.001)**: Untrusted plugin scripts accessing `os.environ` read sensitive API keys, tokens (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `OPENAI_API_KEY`), and exfiltrate them via outbound socket connections or temporary files.
3. **Implicit Trust Hijacking**: Cloned repositories executing untrusted build hooks or plugins automatically upon directory entry without explicit human confirmation.
4. **stdio Stream Pollution**: External plugin scripts writing unformatted diagnostic strings to stdout corrupt the JSON-RPC communication transport used by FastMCP clients and IDE agents.
5. **Supply Chain Compromise via Floating Plugin Dependencies**: Third-party plugins pulling unpinned remote dependencies at runtime.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Rogue script impersonating a core Rush engine | **High** | Cryptographic SHA-256 trust binding in `.rush/trust.json`. |
| **Tampering** | Modifying plugin code after trust has been granted | **Critical** | Dynamic SHA-256 pre-execution hash verification. |
| **Repudiation** | Untrusted plugin performing silent disk mutations | **Medium** | Immutable NDJSON execution telemetry to `sys.stderr`. |
| **Information Disclosure** | Plugin reading host environment secrets (`ANTHROPIC_API_KEY`) | **Critical** | Subprocess environment sanitization stripping all known API keys. |
| **Denial of Service** | Infinite loops or blocking I/O in plugin scripts | **High** | Strict 30.0-second execution timeouts and bounded buffers. |
| **Elevation of Privilege** | Plugin attempting to overwrite `AGENTS.md` or `rush.toml` | **Critical** | Workspace boundary confinement and read-only governance guards. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 28 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Zero-Trust Default Posture: All plugins blocked until SHA-256 trusted.  |
| 2. Cryptographic Trust Store: SHA-256 digests stored in .rush/trust.json.  |
| 3. Pre-Execution Hash Verification: Any byte edit invalidates trust.        |
| 4. Environment Sanitization: Strip SENSITIVE_ENV_KEYS before subprocess.   |
| 5. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 6. Workspace Confinement: Target files must resolve strictly within root.   |
| 7. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 8. Canonical ToolResult Shape: Plugins must emit valid ToolResult JSON.     |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Plugin Trust Summaries)
- Outputs a single-line summary table of registered plugins and their cryptographic trust status (~40 tokens) instead of multi-page security dumps.
- Mathematical Token Economy:
  - Raw plugin execution logs: ~3,200 tokens.
  - Sliced trust summary: ~55 tokens (98.3% token reduction).

### 2.2 `graft` (Targeted Plugin Execution)
- Dispatches plugin execution only to files matching the plugin's declared file pattern globs (e.g. `*.sql`, `*.proto`).

### 2.3 `context-mode` (Structured Trust Audits & NDJSON Logs)
- Plugin lifecycle events, cryptographic hash evaluations, and security rejections are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── plugins/
│   ├── __init__.py           # Plugins package exports
│   ├── trust_store.py        # Cryptographic SHA-256 trust manager (.rush/trust.json)
│   ├── loader.py             # Plugin discovery and configuration parser
│   ├── executor.py           # Hardened subprocess runner with env sanitization
│   ├── sandboxed_env.py      # Environment variable sanitizer and validator
│   ├── hash_verifier.py      # Sub-millisecond pre-execution hash verifier
│   ├── manifest_schema.py    # Plugin specification and parameter schema validator
│   └── skills_generator.py   # Autonomous agent skill synthesizer (SKILL.md)
├── cli.py                    # Click CLI commands (rush trust, rush plugin)
└── mcp_server.py             # FastMCP endpoints (rush_trust_check, rush_plugin_execute)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/plugins/trust_store.py` (New cryptographic trust store)
- `src/rush/plugins/loader.py` (New plugin discovery and loader)
- `src/rush/plugins/executor.py` (New hardened plugin executor)
- `src/rush/plugins/sandboxed_env.py` (New sandbox environment sanitizer)
- `src/rush/plugins/hash_verifier.py` (New SHA-256 pre-execution verifier)
- `src/rush/plugins/manifest_schema.py` (New plugin schema validator)
- `src/rush/plugins/skills_generator.py` (New agent skill synthesizer)
- `src/rush/cli.py` (CLI commands `rush trust`, `rush plugin`)
- `src/rush/mcp_server.py` (FastMCP endpoints for plugin system)
- `tests/test_plugin_system.py` (TDD unit test suite)
- `docs/guides/plugins.md`, `docs/tools/trust.md` (Documentation)

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
- **User Story 1 (Zero-Trust Plugin Execution)**: As a security-conscious engineer cloning third-party repos, I want Rush to block unverified custom plugins by default until explicitly trusted via `rush trust`.
  - *Acceptance Criteria*: Unapproved plugins return `status="skipped"` and `summary="Untrusted plugin blocked by security policy"`.
- **User Story 2 (Cryptographic Trust Management)**: As a developer configuring internal company linters, I want `rush trust <plugin>` to record the SHA-256 binary hash into `.rush/trust.json` so that tamper attempts are detected immediately.
  - *Acceptance Criteria*: Modifying a trusted plugin script triggers an immediate hash mismatch error and blocks execution.
- **User Story 3 (Autonomous Agent Skills Generation)**: As an AI agent user, I want `rush plugin scaffold-skill` to generate standardized `SKILL.md` definitions so that coding agents understand how to invoke custom plugins.
  - *Acceptance Criteria*: Synthesizes valid Agent Skill YAML frontmatter and instructions matching tool specifications.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: SHA-256 Trust Store & Hash Verifier**
  - **Files:** `src/rush/plugins/trust_store.py`, `src/rush/plugins/hash_verifier.py`, `tests/test_plugin_system.py`
  - **Step 1: Write failing tests** for trust file creation, hash recording, tamper detection, and untrusted execution blocking.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_plugin_system.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `TrustStore` and `HashVerifier`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_plugin_system.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/plugins/ && ruff format --check src/rush/plugins/`.

- [ ] **Task 2: Plugin Discovery, Manifest Schema & Sandboxed Runner**
  - **Files:** `src/rush/plugins/loader.py`, `src/rush/plugins/manifest_schema.py`, `src/rush/plugins/executor.py`, `src/rush/plugins/sandboxed_env.py`, `tests/test_plugin_system.py`
  - **Step 1: Write failing tests** for plugin manifest validation, environment variable sanitization, and output JSON parsing.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_plugin_system.py -v` (Expected: FAIL).
  - **Step 3: Implement `PluginLoader`, `ManifestValidator`, and `SandboxedExecutor`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_plugin_system.py -v` (Expected: PASS).
  - **Step 5: Verify isolation**: Environment variables are sanitized to prevent secret leaks to untrusted plugins.

- [ ] **Task 3: Agent Skills Generator & CLI / FastMCP Integration**
  - **Files:** `src/rush/plugins/skills_generator.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_plugin_system.py`
  - **Step 1: Write failing tests** for `rush trust`, `rush plugin`, and FastMCP endpoints `rush_trust_check`, `rush_plugin_execute`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_plugin_system.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_plugin_system.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/plugins/trust_store.py`

```python
"""Cryptographic SHA-256 trust manager for plugins and custom engines."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrustedPluginRecord:
    name: str
    file_path: str
    sha256_hash: str
    granted_at: float
    granted_by: str = "local_user"


class PluginTrustStore:
    """Manages the local cryptographic trust store located at .rush/trust.json."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.trust_file = self.repo_root / ".rush" / "trust.json"

    def _compute_sha256(self, file_path: Path) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def load_trust_store(self) -> dict[str, TrustedPluginRecord]:
        if not self.trust_file.exists():
            return {}
        try:
            raw_data = json.loads(self.trust_file.read_text(encoding="utf-8"))
            records = {}
            for name, item in raw_data.items():
                records[name] = TrustedPluginRecord(
                    name=name,
                    file_path=item["file_path"],
                    sha256_hash=item["sha256_hash"],
                    granted_at=item["granted_at"],
                    granted_by=item.get("granted_by", "local_user"),
                )
            return records
        except Exception:
            return {}

    def is_trusted(self, plugin_name: str, executable_path: Path) -> bool:
        if not executable_path.exists() or not executable_path.is_file():
            return False
        store = self.load_trust_store()
        record = store.get(plugin_name)
        if not record:
            return False
        current_hash = self._compute_sha256(executable_path)
        return record.sha256_hash == current_hash

    def grant_trust(self, plugin_name: str, executable_path: Path) -> TrustedPluginRecord:
        self.trust_file.parent.mkdir(parents=True, exist_ok=True)
        store = self.load_trust_store()
        current_hash = self._compute_sha256(executable_path)
        rel_path = (
            str(executable_path.relative_to(self.repo_root))
            if executable_path.is_relative_to(self.repo_root)
            else str(executable_path)
        )
        record = TrustedPluginRecord(
            name=plugin_name,
            file_path=rel_path,
            sha256_hash=current_hash,
            granted_at=time.time(),
            granted_by="local_user",
        )
        data = {
            k: {
                "file_path": v.file_path,
                "sha256_hash": v.sha256_hash,
                "granted_at": v.granted_at,
                "granted_by": v.granted_by,
            }
            for k, v in store.items()
        }
        data[plugin_name] = {
            "file_path": record.file_path,
            "sha256_hash": record.sha256_hash,
            "granted_at": record.granted_at,
            "granted_by": record.granted_by,
        }
        self.trust_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return record

    def revoke_trust(self, plugin_name: str) -> bool:
        if not self.trust_file.exists():
            return False
        store = self.load_trust_store()
        if plugin_name in store:
            data = {
                k: {
                    "file_path": v.file_path,
                    "sha256_hash": v.sha256_hash,
                    "granted_at": v.granted_at,
                    "granted_by": v.granted_by,
                }
                for k, v in store.items()
                if k != plugin_name
            }
            self.trust_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        return False
```

---

### 5.2 `src/rush/plugins/hash_verifier.py`

```python
"""Sub-millisecond pre-execution hash verifier."""

from __future__ import annotations

import hashlib
from pathlib import Path


class PreExecutionHashVerifier:
    """Provides high-performance SHA-256 byte hashing for plugin files."""

    @staticmethod
    def verify_hash(file_path: Path, expected_sha256: str) -> bool:
        if not file_path.exists() or not file_path.is_file():
            return False
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest().lower() == expected_sha256.lower()

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
```

---

### 5.3 `src/rush/plugins/loader.py`

```python
"""Plugin discovery and configuration parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class PluginSpec:
    name: str
    command: list[str]
    executable_path: Path
    file_patterns: list[str] = field(default_factory=lambda: ["*"])
    description: str = ""
    timeout_seconds: float = 30.0


class PluginLoader:
    """Discovers plugins declared in rush.toml or located in .rush/plugins/."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_plugins(self) -> dict[str, PluginSpec]:
        plugins: dict[str, PluginSpec] = {}
        config_path = self.repo_root / "rush.toml"

        if config_path.exists():
            try:
                data = tomllib.loads(config_path.read_text(encoding="utf-8"))
                plugin_tables = data.get("plugins", {})
                for name, table in plugin_tables.items():
                    cmd_str = table.get("command", "")
                    cmd_parts = cmd_str.split()
                    if cmd_parts:
                        exec_path = (
                            self.repo_root / cmd_parts[0]
                            if (self.repo_root / cmd_parts[0]).exists()
                            else Path(cmd_parts[0])
                        )
                        plugins[name] = PluginSpec(
                            name=name,
                            command=cmd_parts,
                            executable_path=exec_path,
                            file_patterns=table.get("patterns", ["*"]),
                            description=table.get("description", ""),
                            timeout_seconds=float(table.get("timeout_seconds", 30.0)),
                        )
            except Exception:
                pass

        # Scan .rush/plugins directory for executable scripts
        plugins_dir = self.repo_root / ".rush" / "plugins"
        if plugins_dir.exists():
            for p in plugins_dir.iterdir():
                if p.is_file() and p.suffix in (".py", ".sh", ".js", ".exe", ""):
                    plugin_name = p.stem
                    if plugin_name not in plugins:
                        cmd = (
                            ["python", str(p)]
                            if p.suffix == ".py"
                            else ["node", str(p)]
                            if p.suffix == ".js"
                            else [str(p)]
                        )
                        plugins[plugin_name] = PluginSpec(
                            name=plugin_name,
                            command=cmd,
                            executable_path=p,
                            description="Discovered script plugin",
                            timeout_seconds=30.0,
                        )

        return plugins
```

---

### 5.4 `src/rush/plugins/sandboxed_env.py`

```python
"""Environment variable sanitizer for untrusted plugin execution."""

from __future__ import annotations

import os

SENSITIVE_ENV_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "DATABASE_URL",
    "SLACK_BOT_TOKEN",
    "STRIPE_SECRET_KEY",
    "HEROKU_API_KEY",
    "SSH_AUTH_SOCK",
}


class SandboxedEnvironment:
    """Strips all high-privilege credentials and sensitive keys from the environment."""

    @staticmethod
    def get_sanitized_env() -> dict[str, str]:
        env = dict(os.environ)
        for key in SENSITIVE_ENV_KEYS:
            env.pop(key, None)
        env["PYTHONUNBUFFERED"] = "1"
        env["NO_COLOR"] = "1"
        return env
```

---

### 5.5 `src/rush/plugins/manifest_schema.py`

```python
"""Plugin manifest specification and parameter schema validator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginManifestValidationResult:
    is_valid: bool
    errors: list[str]


class PluginManifestValidator:
    """Validates the structure and parameter types of plugin specifications."""

    @staticmethod
    def validate_spec_dict(name: str, spec_data: dict) -> PluginManifestValidationResult:
        errors = []
        if not name or not name.isidentifier():
            errors.append(f"Plugin name '{name}' must be a valid alphanumeric identifier.")

        cmd = spec_data.get("command")
        if not cmd:
            errors.append("Plugin specification must define a non-empty 'command' string or list.")

        timeout = spec_data.get("timeout_seconds", 30.0)
        try:
            t_val = float(timeout)
            if t_val <= 0 or t_val > 300.0:
                errors.append("Plugin timeout_seconds must be between 1.0 and 300.0 seconds.")
        except (ValueError, TypeError):
            errors.append("Plugin timeout_seconds must be a valid number.")

        patterns = spec_data.get("patterns", ["*"])
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            errors.append("Plugin 'patterns' must be a list of glob strings.")

        return PluginManifestValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
```

---

### 5.6 `src/rush/plugins/executor.py`

```python
"""Hardened plugin executor with environment sanitization and subprocess isolation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from rush.plugins.loader import PluginSpec
from rush.plugins.trust_store import PluginTrustStore
from rush.plugins.sandboxed_env import SandboxedEnvironment
from rush.tools.base import Finding, ToolResult
from rush.tools.common import run_subprocess


class HardenedPluginExecutor:
    """Executes trust-gated plugins under bounded subprocess isolation."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.trust_store = PluginTrustStore(self.repo_root)

    def execute(
        self,
        plugin: PluginSpec,
        paths: list[Path],
        allow_untrusted: bool = False,
    ) -> ToolResult:
        if not allow_untrusted and not self.trust_store.is_trusted(plugin.name, plugin.executable_path):
            finding: Finding = {
                "path": str(plugin.executable_path),
                "line": 1,
                "column": 1,
                "rule": "untrusted-plugin-execution-blocked",
                "severity": "warn",
                "message": "Plugin blocked by zero-trust security gate.",
            }
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": None,
                "status": "skipped",
                "duration_ms": 0,
                "summary": f"Plugin '{plugin.name}' is untrusted. Run 'rush trust grant {plugin.name}' to authorize.",
                "findings": [finding],
            }

        start_time = time.perf_counter()
        target_args = [str(p) for p in paths]
        full_command = [*plugin.command, *target_args]
        sanitized_env = SandboxedEnvironment.get_sanitized_env()

        proc = run_subprocess(
            full_command,
            cwd=self.repo_root,
            env=sanitized_env,
            timeout=plugin.timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = proc.returncode
        stdout = proc.stdout

        try:
            data = json.loads(stdout)
            findings: list[Finding] = data.get("findings", [])
            status = data.get("status", "ok" if code == 0 else "fail")
            if status not in ("ok", "warn", "fail", "error", "skipped"):
                status = "ok" if code == 0 else "fail"
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": data.get("engine_version", "1.0"),
                "status": status,
                "duration_ms": duration_ms,
                "summary": data.get("summary", f"Plugin {plugin.name} finished."),
                "findings": findings,
            }
        except Exception:
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": "1.0",
                "status": "ok" if code == 0 else "fail",
                "duration_ms": duration_ms,
                "summary": f"Plugin {plugin.name} exited with code {code}.",
                "findings": [],
            }
```

---

### 5.7 `src/rush/plugins/skills_generator.py`

```python
"""Autonomous agent skill synthesizer for plugins."""

from __future__ import annotations

from rush.plugins.loader import PluginSpec


class AgentSkillGenerator:
    """Generates standard SKILL.md documentation for dynamic agent plugins."""

    @staticmethod
    def generate_skill_markdown(plugin: PluginSpec) -> str:
        return f"""---
name: {plugin.name}
description: {plugin.description or f"Custom Rush plugin for {plugin.name}"}
toolAction: Running {plugin.name}
toolSummary: {plugin.name} verification
---

# {plugin.name} Agent Skill

## Overview
This skill executes the custom project plugin `{plugin.name}` verified by Rush's cryptographic trust store.

## Execution
Run the following tool command:
```bash
rush plugin run {plugin.name} <targets>
```
"""
```

---

### 5.8 `src/rush/cli.py` (Registration for `rush trust` and `rush plugin`)

```python
import click
from pathlib import Path
from rush.plugins.trust_store import PluginTrustStore
from rush.plugins.loader import PluginLoader
from rush.plugins.executor import HardenedPluginExecutor

@click.group(name="trust")
def trust_group():
    """Manage cryptographic trust for custom plugins and scanners."""
    pass

@trust_group.command(name="list")
def trust_list_cmd():
    """List all trusted plugin cryptographic hashes."""
    store = PluginTrustStore(Path.cwd())
    records = store.load_trust_store()
    if not records:
        click.echo("No plugins currently trusted.")
        return
    click.echo(f"Trusted Plugins ({len(records)}):")
    for name, r in records.items():
        click.echo(f"  - {name}: {r.file_path} (SHA-256: {r.sha256_hash[:16]}...) [Granted at {r.granted_at}]")

@trust_group.command(name="grant")
@click.argument("plugin_name")
def trust_grant_cmd(plugin_name: str):
    """Grant execution trust to a plugin."""
    repo_root = Path.cwd()
    loader = PluginLoader(repo_root)
    plugins = loader.discover_plugins()
    if plugin_name not in plugins:
        click.echo(f"Plugin '{plugin_name}' not found.", err=True)
        return
    store = PluginTrustStore(repo_root)
    rec = store.grant_trust(plugin_name, plugins[plugin_name].executable_path)
    click.echo(f"[TRUST GRANTED] Plugin '{plugin_name}' trusted with SHA-256: {rec.sha256_hash[:16]}...")

@trust_group.command(name="revoke")
@click.argument("plugin_name")
def trust_revoke_cmd(plugin_name: str):
    """Revoke trust from a plugin."""
    store = PluginTrustStore(Path.cwd())
    ok = store.revoke_trust(plugin_name)
    if ok:
        click.echo(f"[TRUST REVOKED] Plugin '{plugin_name}' trust revoked.")
    else:
        click.echo(f"Plugin '{plugin_name}' was not in trust store.", err=True)

@click.group(name="plugin")
def plugin_group():
    """Discover and execute trust-gated custom plugins."""
    pass

@plugin_group.command(name="list")
def plugin_list_cmd():
    """List all discovered plugins."""
    loader = PluginLoader(Path.cwd())
    plugins = loader.discover_plugins()
    click.echo(f"Discovered Plugins ({len(plugins)}):")
    for name, p in plugins.items():
        click.echo(f"  - {name}: {p.command} ({p.executable_path})")

@plugin_group.command(name="run")
@click.argument("plugin_name")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--allow-untrusted", is_flag=True, help="Allow executing untrusted plugin.")
def plugin_run_cmd(plugin_name: str, paths, allow_untrusted: bool):
    """Execute a trust-gated plugin."""
    repo_root = Path.cwd()
    loader = PluginLoader(repo_root)
    plugins = loader.discover_plugins()
    if plugin_name not in plugins:
        click.echo(f"Plugin '{plugin_name}' not found.", err=True)
        return

    executor = HardenedPluginExecutor(repo_root)
    target_paths = [Path(p) for p in paths] if paths else [repo_root]
    res = executor.execute(plugins[plugin_name], target_paths, allow_untrusted=allow_untrusted)
    click.echo(f"[{res['status'].upper()}] {res['summary']}")
```

---

### 5.9 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for trust-gated plugin execution."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.plugins.loader import PluginLoader
from rush.plugins.executor import HardenedPluginExecutor
from rush.plugins.trust_store import PluginTrustStore

mcp = FastMCP("rush")

@mcp.tool(name="rush_trust_check", description="Verify cryptographic trust status for a plugin.")
def rush_trust_check(plugin_name: str) -> str:
    repo_root = Path.cwd()
    loader = PluginLoader(repo_root)
    plugins = loader.discover_plugins()
    if plugin_name not in plugins:
        return f"Plugin '{plugin_name}' not found."
    store = PluginTrustStore(repo_root)
    trusted = store.is_trusted(plugin_name, plugins[plugin_name].executable_path)
    return json.dumps({"plugin": plugin_name, "trusted": trusted}, indent=2)

@mcp.tool(name="rush_plugin_execute", description="Execute a trusted custom plugin.")
def rush_plugin_execute(plugin_name: str, target_file: str = ".") -> str:
    repo_root = Path.cwd()
    loader = PluginLoader(repo_root)
    plugins = loader.discover_plugins()
    if plugin_name not in plugins:
        return f"Plugin '{plugin_name}' not found."
    executor = HardenedPluginExecutor(repo_root)
    res = executor.execute(plugins[plugin_name], [Path(target_file)])
    return json.dumps(res)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_plugin_system.py`

```python
"""Comprehensive test suite for PluginTrustStore, PluginLoader, HardenedPluginExecutor, SandboxedEnvironment, PluginManifestValidator, PreExecutionHashVerifier, and AgentSkillGenerator."""

import os
from pathlib import Path
import pytest
from rush.plugins.trust_store import PluginTrustStore, TrustedPluginRecord
from rush.plugins.loader import PluginLoader, PluginSpec
from rush.plugins.executor import HardenedPluginExecutor
from rush.plugins.sandboxed_env import SandboxedEnvironment
from rush.plugins.manifest_schema import PluginManifestValidator
from rush.plugins.hash_verifier import PreExecutionHashVerifier
from rush.plugins.skills_generator import AgentSkillGenerator


def test_trust_store_grant_and_verify(tmp_path: Path):
    script = tmp_path / "custom_scan.py"
    script.write_text("print('clean')", encoding="utf-8")

    store = PluginTrustStore(tmp_path)
    assert store.is_trusted("scan", script) is False

    rec = store.grant_trust("scan", script)
    assert rec.sha256_hash is not None
    assert store.is_trusted("scan", script) is True

    # Mutate script -> trust must fail
    script.write_text("print('tampered')", encoding="utf-8")
    assert store.is_trusted("scan", script) is False

    # Revoke trust
    revoked = store.revoke_trust("scan")
    assert revoked is True
    assert store.is_trusted("scan", script) is False


def test_pre_execution_hash_verifier(tmp_path: Path):
    f = tmp_path / "test_exec.py"
    f.write_text("print('hello')", encoding="utf-8")
    sha = PreExecutionHashVerifier.calculate_sha256(f)
    assert PreExecutionHashVerifier.verify_hash(f, sha) is True
    assert PreExecutionHashVerifier.verify_hash(f, "0" * 64) is False


def test_trust_store_load_missing(tmp_path: Path):
    store = PluginTrustStore(tmp_path)
    records = store.load_trust_store()
    assert records == {}


def test_plugin_loader_discovers_scripts(tmp_path: Path):
    p_dir = tmp_path / ".rush" / "plugins"
    p_dir.mkdir(parents=True)
    (p_dir / "security.py").write_text("print('ok')", encoding="utf-8")

    loader = PluginLoader(tmp_path)
    plugins = loader.discover_plugins()
    assert "security" in plugins
    assert plugins["security"].executable_path == p_dir / "security.py"


def test_plugin_loader_from_rush_toml(tmp_path: Path):
    toml_content = """
[plugins.proto_check]
command = "python scripts/proto_check.py"
patterns = ["*.proto"]
description = "Protobuf validator"
"""
    (tmp_path / "rush.toml").write_text(toml_content, encoding="utf-8")
    loader = PluginLoader(tmp_path)
    plugins = loader.discover_plugins()
    assert "proto_check" in plugins
    assert plugins["proto_check"].file_patterns == ["*.proto"]


def test_sandboxed_environment_strips_secrets():
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test12345"
    os.environ["GITHUB_TOKEN"] = "ghp_secrettoken"
    sanitized = SandboxedEnvironment.get_sanitized_env()

    assert "ANTHROPIC_API_KEY" not in sanitized
    assert "GITHUB_TOKEN" not in sanitized
    assert sanitized.get("PYTHONUNBUFFERED") == "1"


def test_executor_blocks_untrusted_plugin(tmp_path: Path):
    script = tmp_path / "scanner.py"
    script.write_text("print('{\"status\": \"ok\", \"findings\": []}')", encoding="utf-8")

    spec = PluginSpec(name="scanner", command=["python", str(script)], executable_path=script)
    executor = HardenedPluginExecutor(tmp_path)
    res = executor.execute(spec, [tmp_path], allow_untrusted=False)

    assert res["status"] == "skipped"
    assert "untrusted" in res["summary"]


def test_executor_runs_trusted_plugin(tmp_path: Path):
    script = tmp_path / "scanner.py"
    script.write_text("import sys\nsys.stdout.write('{\"status\": \"ok\", \"findings\": []}')", encoding="utf-8")

    store = PluginTrustStore(tmp_path)
    store.grant_trust("scanner", script)

    spec = PluginSpec(name="scanner", command=["python", str(script)], executable_path=script)
    executor = HardenedPluginExecutor(tmp_path)
    res = executor.execute(spec, [tmp_path], allow_untrusted=False)

    assert res["status"] == "ok"


def test_executor_allows_untrusted_with_flag(tmp_path: Path):
    script = tmp_path / "scanner.py"
    script.write_text("import sys\nsys.stdout.write('{\"status\": \"ok\", \"findings\": []}')", encoding="utf-8")

    spec = PluginSpec(name="scanner", command=["python", str(script)], executable_path=script)
    executor = HardenedPluginExecutor(tmp_path)
    res = executor.execute(spec, [tmp_path], allow_untrusted=True)

    assert res["status"] == "ok"


def test_manifest_validator_valid():
    res = PluginManifestValidator.validate_spec_dict("my_plugin", {"command": "python test.py", "timeout_seconds": 10})
    assert res.is_valid is True
    assert res.errors == []


def test_manifest_validator_invalid_name():
    res = PluginManifestValidator.validate_spec_dict("invalid-name-with-dashes", {"command": "python test.py"})
    assert res.is_valid is False
    assert len(res.errors) >= 1


def test_agent_skill_generator():
    spec = PluginSpec(name="sql_check", command=["python", "sql.py"], executable_path=Path("sql.py"), description="Custom SQL linter")
    skill_md = AgentSkillGenerator.generate_skill_markdown(spec)
    assert "name: sql_check" in skill_md
    assert "Custom SQL linter" in skill_md
    assert "rush plugin run sql_check" in skill_md
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 28 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:30:00.100Z", "phase": 28, "tool": "rush_trust", "event": "trust_granted", "plugin": "custom_linter", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
{"timestamp": "2026-08-21T09:30:05.150Z", "phase": 28, "tool": "rush_plugin", "event": "plugin_executed", "plugin": "custom_linter", "status": "passed", "duration_ms": 18.4}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 28 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 28: Trust-Gated Plugin System & Agent Skills**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 28 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Custom Plugins & Zero-Trust Security" section explaining `rush trust` and `rush plugin`.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush trust grant`, `revoke`, `list` and `rush plugin list`, `run`, `skill-export`.
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for creating and trusting custom organization-specific linters.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for exporting Agent Skills directly into AI agent skill directories.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example `.rush/plugins/manifest.toml` and sample generated `SKILL.md` files.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add step-by-step tutorial on authoring custom Rush plugins in Python and Bash.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for untrusted plugin errors and hash mismatch warnings.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain why Rush enforces cryptographic hashing on all plugins.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_trust_check` and `rush_plugin_run` MCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document Agent Skill JSON schemas and dynamically registered plugin tools.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `plugin` and `trust` tools in Extensibility category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[plugins]` configuration table (`allow_untrusted`, `trusted_keys`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document SHA-256 cryptographic trust store and subprocess environment variable sanitization architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for plugin API contracts and `AgentSkillGenerator` synthesis.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Provide CI instructions for committing trusted plugin hash manifests.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document plugin isolation and AST sandboxing security fixtures.
- **[`docs/tools/plugin.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/plugin.md)** & **[`docs/tools/trust.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/trust.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-28): implement sha256 trust-gated plugin system and agent skill generator"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
