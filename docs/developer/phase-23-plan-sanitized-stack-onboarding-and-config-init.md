# Phase 23 Implementation Plan: Sanitized Stack Onboarding & Config Init

> **Phase:** 23 of 30  
> **Milestone:** Zero-Friction Onboarding & Toolchain Initializer  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)

---

## 1. Objective & Scope

Deliver an intelligent repository onboarding wizard (`rush setup`) and configuration initializer (`rush init`, `rush config check`) that automatically detects polyglot stacks, recommends quality tools, installs toolchains via system package managers without shell injection vulnerabilities, and generates valid `rush.toml` configs.

Incorporate **Control 3 (Shell Injection Elimination)** to ensure package names are regex-sanitized and executed as typed argument lists (`list[str]`) with `shell=False`.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/discovery/stack.py` (New: Multi-language project stack detector)
- `src/rush/tools/setup_wizard.py` (New: Toolchain installer)
- `src/rush/tools/init_config.py` (New: `rush.toml` generator)
- `src/rush/config.py` (Modified: Configuration validation and diagnostics)
- `src/rush/cli.py` (Modified: Add `rush setup`, `rush init`, `rush config check`)
- `src/rush/logging.py` (Modified: `[rush-setup:LEVEL]` and `[rush-init:LEVEL]`)

### Test & Fixture Files
- `tests/test_stack_discovery.py` (New: Stack detection fixtures)
- `tests/test_setup_and_init.py` (New: Config generation and command injection prevention tests)
- `tests/fixtures/stacks/` (New: Sample `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod` fixtures)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_stack_discovery.py` and `tests/test_setup_and_init.py`:
1. `test_detect_python_uv_stack()`: Detects Python + uv from `pyproject.toml`.
2. `test_detect_node_typescript_stack()`: Detects Node + TS from `package.json` and `tsconfig.json`.
3. `test_setup_command_injection_sanitization()`: Verifies package specs containing `; rm -rf /` or `& calc.exe` are rejected.
4. `test_setup_argument_list_structure()`: Verifies `run_subprocess()` receives a pure list of strings.
5. `test_init_config_generation()`: Verifies generated `rush.toml` parses cleanly with `rush.config.load_config()`.

### 3.2 GREEN Phase
Implement `stack.py`, `setup_wizard.py`, `init_config.py`, and CLI commands.

### 3.3 REFACTOR Phase
Ensure interactive prompts degrade gracefully to non-interactive mode when `--yes` / `--non-interactive` is passed or stdout is non-TTY.

---

## 4. Step-by-Step Implementation Tasks

### Task 23.1: Stack Discovery Engine (`src/rush/discovery/stack.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class DetectedStack:
    language: str
    package_manager: str
    frameworks: list[str]
    suggested_engines: list[str]

def detect_project_stack(root: Path) -> list[DetectedStack]:
    stacks: list[DetectedStack] = []
    # Probe pyproject.toml, package.json, Cargo.toml, go.mod, pom.xml, Dockerfile, etc.
    return stacks
```

### Task 23.2: Sanitized Toolchain Installer (`src/rush/tools/setup_wizard.py`)
```python
import re
from pathlib import Path
from rush.tools.common import run_subprocess

PACKAGE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9@_./-]+$")

def install_engine_package(package_manager: str, package_name: str, cwd: Path) -> bool:
    if not PACKAGE_NAME_REGEX.match(package_name):
        raise ValueError(f"Invalid or hostile package name: {package_name}")
    
    cmd_map = {
        "uv": ["uv", "tool", "install", package_name],
        "npm": ["npm", "install", "-g", package_name],
        "brew": ["brew", "install", package_name],
        "cargo": ["cargo", "install", package_name],
        "winget": ["winget", "install", "--exact", package_name],
    }
    cmd = cmd_map.get(package_manager)
    if not cmd:
        return False
    
    code, stdout, stderr = run_subprocess(cmd, cwd=cwd)
    return code == 0
```

### Task 23.3: Configuration Initializer (`src/rush/tools/init_config.py`)
Generates a customized `rush.toml` based on detected stacks.

### Task 23.4: Stderr Diagnostics
- `[rush-setup:INFO] Detected project stacks: {stacks}`
- `[rush-setup:INFO] Installing recommended engine: {engine} via {pm}`
- `[rush-setup:ERROR] Invalid package specification: {pkg}`
- `[rush-init:INFO] Wrote initial configuration to rush.toml`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/GETTING_STARTED.md` & `docs/user-guide/quickstart.md` (Document `rush setup` and `rush init`).
2. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Document new commands and flags).
3. `docs/CONFIG_SCHEMA.md` & `docs/reference/configuration-reference.md` (Document `rush config check`).
4. Run `python scripts/sync_docs.py --update` to synchronize all 149+ docs.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run stack discovery and setup tests
.venv/Scripts/python.exe -m pytest tests/test_stack_discovery.py tests/test_setup_and_init.py -v

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
