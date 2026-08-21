# Phase 28 Implementation Plan: Trust-Gated Plugins & Agent Skills

> **Phase:** 28 of 40  
> **Milestone:** Extensible Plugin Runtime & Autonomous AI Agent Skills  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0015: Extensible Plugin Architecture and Agent Skills](../adr/0015-extensible-plugin-architecture-and-agent-skills.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Developers and autonomous coding agents need the ability to author, test, install, and execute custom domain-specific quality engines without modifying Rush core code. Phase 28 delivers an extensible plugin architecture (`[plugins.<name>]` in `rush.toml` and `.rush/plugins/` executables) and standardized agent skill definitions.

To prevent Remote Code Execution (RCE) on cloned untrusted repositories containing malicious plugin hooks, plugins in untrusted repositories are blocked by default until explicitly authorized via `rush trust` or `--allow-untrusted-plugins`.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Plugin Output Schema Enforcement)**: Custom plugins are required to output structured JSON conforming to `ToolResult`. Malformed or overly verbose stderr outputs are truncated to preserve token budgets.
- **`graft` (Targeted Plugin Scope)**: Plugins receive explicit file target lists sliced from Git changed scopes rather than traversing the filesystem independently.
- **`context-mode` (Strict Schema Gating)**: Plugin outputs are validated in-process using JSON Schema Draft 2020-12 before being ingested into agent context.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/plugins/__init__.py` (New: Plugin loader, executor, and discovery dispatcher)
- `src/rush/plugins/loader.py` (New: Plugin manifest and directory parser)
- `src/rush/plugins/trust.py` (New: Repository trust ledger in `~/.rush/trusted_repositories.json`)
- `src/rush/plugins/validator.py` (New: Strict schema validator for plugin JSON outputs)
- `src/rush/skills/plugin_builder.md` (New: Agent Skill for plugin creation)
- `src/rush/skills/plugin_installer.md` (New: Agent Skill for plugin installation)
- `src/rush/cli.py` (Modified: Register `rush plugin` and `rush trust`)
- `src/rush/mcp_server.py` (Modified: Dynamically register trusted plugins as FastMCP tools)
- `src/rush/catalog.py` (Modified: Register plugin catalog spec)

### Test & Fixture Files
- `tests/test_plugins.py` (New: Plugin execution across Python, Bash, Node)
- `tests/test_plugin_trust.py` (New: Trust ledger, untrusted blocking, and authorization lifecycle)
- `tests/fixtures/plugins/compliant_plugin.py` (New: Valid plugin fixture)
- `tests/fixtures/plugins/malformed_plugin.py` (New: Invalid JSON plugin fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_plugin_trust.py
def test_untrusted_plugin_blocked_by_default(tmp_path):
    # Untrusted repo with plugin
    (tmp_path / "rush.toml").write_text('[plugins.custom]\ncommand = "echo ok"\n')
    assert is_repo_trusted(tmp_path) is False
    res = execute_plugin("custom", repo_root=tmp_path)
    assert res.status == "skipped"
    assert "Untrusted repository" in res.summary

def test_trust_repo_authorizes_plugin_execution(tmp_path):
    (tmp_path / "rush.toml").write_text('[plugins.custom]\ncommand = "echo ok"\n')
    trust_repo(tmp_path)
    assert is_repo_trusted(tmp_path) is True
```

### 4.2 GREEN Phase (Implementation)
Implement `loader.py`, `trust.py`, `validator.py`, and CLI commands.

### 4.3 REFACTOR Phase
Ensure plugin execution enforces 120s timeouts and passes `stdin=DEVNULL`, `shell=False` through `run_subprocess`.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:50:00Z", "phase": 28, "tool": "rush_plugin", "event": "plugin_loaded", "plugin_name": "custom_linter", "trusted": true}
{"timestamp": "2026-08-21T07:50:01Z", "phase": 28, "tool": "rush_plugin", "event": "trust_gate_blocked", "repo": "/tmp/untrusted_repo", "reason": "not_in_trust_ledger"}
{"timestamp": "2026-08-21T07:50:02Z", "phase": 28, "tool": "rush_plugin", "event": "plugin_executed", "plugin_name": "custom_linter", "duration_ms": 84, "status": "passed"}
```

---

## 6. Step-by-Step Task Specifications

### Task 28.1: Repository Trust Manager (`src/rush/plugins/trust.py`)
```python
from __future__ import annotations
import json
from pathlib import Path

TRUST_LEDGER_PATH = Path.home() / ".rush" / "trusted_repositories.json"

def is_repo_trusted(repo_root: Path) -> bool:
    """Check if repository root is listed in user trust ledger."""
    ...

def trust_repo(repo_root: Path) -> None:
    """Add repository path to trusted repositories ledger."""
    ...
```

### Task 28.2: Plugin Manifest Loader & Schema Validator (`src/rush/plugins/validator.py`)
Load `[plugins.*]` from `rush.toml` and `.rush/plugins/`, validating JSON output against `ToolResult`.

### Task 28.3: Agent Skill Specs (`src/rush/skills/`)
Author `plugin_builder.md` and `plugin_installer.md` providing step-by-step instructions for AI agents.

### Task 28.4: CLI & FastMCP Registrations
Register `rush plugin` and `rush trust` in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **RCE Prevention**: Never execute untrusted plugins without explicit user authorization.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
