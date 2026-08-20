# Phase 28 Implementation Plan: Trust-Gated Plugins & Agent Skills

> **Phase:** 28 of 30  
> **Milestone:** Extensible Plugin Runtime & Autonomous AI Agent Skills  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0015: Extensible Plugin Architecture and Agent Skills](../adr/0015-extensible-plugin-architecture-and-agent-skills.md)

---

## 1. Objective & Scope

Enable developers and AI agents to create, test, install, and execute custom quality engines via declarative `rush.toml` plugins (`[plugins.<name>]`) and `.rush/plugins/` executables.

Incorporate **Control 6 (Repository Trust Gating)** to prevent Remote Code Execution (RCE) on cloned untrusted repositories by blocking untrusted plugin execution by default until explicitly authorized via `rush trust` or `--allow-untrusted-plugins`.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/plugins/__init__.py` (New: Plugin loader and dispatcher)
- `src/rush/plugins/loader.py` (New: Plugin manifest and directory parser)
- `src/rush/plugins/trust.py` (New: Repository trust ledger)
- `src/rush/plugins/validator.py` (New: Strict schema validator for plugin JSON outputs)
- `src/rush/skills/plugin_builder.md` (New: Agent Skill for plugin creation)
- `src/rush/skills/plugin_installer.md` (New: Agent Skill for plugin installation)
- `src/rush/cli.py` (Modified: Register `rush plugin` and `rush trust`)
- `src/rush/config.py` (Modified: Support `[plugins.*]` table in `rush.toml`)
- `src/rush/logging.py` (Modified: `[rush-plugin:LEVEL]` and `[rush-trust:LEVEL]`)

### Test & Fixture Files
- `tests/test_plugins.py` (New: Custom script execution in Python, Bash, Node)
- `tests/test_plugin_trust.py` (New: Trust ledger and untrusted execution blocking tests)
- `tests/fixtures/plugins/` (New: Sample compliant and non-compliant plugin scripts)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_plugins.py` and `tests/test_plugin_trust.py`:
1. `test_plugin_untrusted_repo_blocked_by_default()`: Verifies plugins in an untrusted repo return `untrusted` status without executing subprocesses.
2. `test_plugin_trust_gating_lifecycle()`: Verifies `rush trust` authorizes the repository and allows execution.
3. `test_plugin_output_schema_tamper_rejection()`: Verifies plugin output with missing keys or invalid structure is marked as `error`.
4. `test_plugin_subprocess_timeout_enforcement()`: Verifies hanging plugins are terminated at 120s.

### 3.2 GREEN Phase
Implement `loader.py`, `trust.py`, `validator.py`, and CLI subcommands.

### 3.3 REFACTOR Phase
Ensure plugin stdout is strictly validated against `ToolResult` dataclass and errors flow to `stderr`.

---

## 4. Step-by-Step Implementation Tasks

### Task 28.1: Repository Trust Manager (`src/rush/plugins/trust.py`)
```python
from __future__ import annotations
import json
from pathlib import Path

TRUST_LEDGER_PATH = Path.home() / ".rush" / "trusted_repositories.json"

def is_repo_trusted(repo_root: Path) -> bool:
    if not TRUST_LEDGER_PATH.is_file():
        return False
    try:
        data = json.loads(TRUST_LEDGER_PATH.read_text(encoding="utf-8"))
        return str(repo_root.resolve()) in data.get("trusted_paths", [])
    except Exception:
        return False

def trust_repo(repo_root: Path) -> None:
    TRUST_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    trusted = []
    if TRUST_LEDGER_PATH.is_file():
        try:
            trusted = json.loads(TRUST_LEDGER_PATH.read_text(encoding="utf-8")).get("trusted_paths", [])
        except Exception:
            trusted = []
    resolved = str(repo_root.resolve())
    if resolved not in trusted:
        trusted.append(resolved)
    TRUST_LEDGER_PATH.write_text(json.dumps({"trusted_paths": trusted}, indent=2), encoding="utf-8")
```

### Task 28.2: Plugin Validator & Loader (`src/rush/plugins/validator.py`)
Parses and validates plugin stdout against canonical `ToolResult` schema.

### Task 28.3: AI Agent Skills (`src/rush/skills/`)
Author `plugin_builder.md` and `plugin_installer.md` providing step-by-step instructions for AI agents to generate AST/regex linters and wire them into Rush.

### Task 28.4: Stderr Diagnostics & Logging
- `[rush-plugin:TRUST_GATE] Untrusted plugins found in repository. Run 'rush trust' to enable execution.`
- `[rush-plugin:INFO] Executing verified custom plugin: {name}`
- `[rush-plugin:ERROR] Plugin {name} emitted invalid ToolResult schema`
- `[rush-trust:INFO] Repository marked as trusted: {path}`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/PLUGINS.md` & `docs/developer/plugin-development-guide.md` (Plugin authoring and AI skill guide).
2. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Document `rush plugin` and `rush trust`).
3. `docs/CONFIG_SCHEMA.md` & `docs/reference/configuration-reference.md` (Document `[plugins.*]` schema).
4. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run plugin and trust unit tests
.venv/Scripts/python.exe -m pytest tests/test_plugins.py tests/test_plugin_trust.py -v

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
