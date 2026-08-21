# Phase 23 Implementation Plan: Sanitized Stack Onboarding & Config Init

> **Phase:** 23 of 40  
> **Milestone:** Zero-Friction Onboarding & Sanitized Toolchain Initializer  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Autonomous coding agents and developers setting up a new repository often struggle with manual configuration generation and missing toolchain dependencies. Phase 23 delivers an intelligent onboarding wizard (`rush setup`) and configuration initializer (`rush init`, `rush config check`) that automatically detects polyglot stacks, recommends quality tools, installs toolchains via system package managers without shell injection vulnerabilities, and generates valid `rush.toml` configs.

Package names and arguments are strictly regex-sanitized (`^[a-zA-Z0-9@_./-]+$`) and passed as typed argument lists (`list[str]`) with `shell=False` and `stdin=DEVNULL`.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Concise Stack Summaries)**: `rush setup` analyzes root manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`) without dumping deep dependency trees, emitting a concise 5-line stack summary.
- **`graft` (Manifest AST Extraction)**: Uses Tree-Sitter / TOML / JSON parsers to extract only the dependency tables and scripts, skipping lockfiles and build outputs.
- **`context-mode` (Interactive TTY Degradation)**: Automatically falls back to non-interactive structured JSON mode (`--json` or non-TTY) when invoked by an AI agent.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/discovery/stack.py` (New: Polyglot project stack and framework detector)
- `src/rush/tools/setup_wizard.py` (New: Sanitized toolchain installer supporting uv, npm, brew, cargo, winget)
- `src/rush/tools/init_config.py` (New: Tailored `rush.toml` generator)
- `src/rush/config.py` (Modified: Configuration validation and diagnostics in `rush config check`)
- `src/rush/cli.py` (Modified: Register `rush setup`, `rush init`, `rush config check`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints for stack detection)
- `src/rush/catalog.py` (Modified: Tool specifications)

### Test & Fixture Files
- `tests/test_stack_discovery.py` (New: Stack detection fixtures across Python, TypeScript, Rust, Go)
- `tests/test_setup_and_init.py` (New: Config generation and command injection prevention tests)
- `tests/fixtures/stacks/pyproject.toml` (New: Python fixture)
- `tests/fixtures/stacks/package.json` (New: Node fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_setup_and_init.py
def test_setup_command_injection_sanitization():
    hostile_pkg = "requests; rm -rf /"
    with pytest.raises(ValueError, match="Invalid or hostile package name"):
        install_engine_package("uv", hostile_pkg, cwd=Path("."))

def test_init_config_generation_produces_valid_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    generated_path = generate_initial_config(tmp_path)
    assert generated_path.exists()
    loaded = load_config(generated_path)
    assert "tools" in loaded

# tests/test_stack_discovery.py
def test_detect_python_uv_stack(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    stacks = detect_project_stack(tmp_path)
    assert any(s.language == "python" for s in stacks)
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/discovery/stack.py`, `src/rush/tools/setup_wizard.py`, and `src/rush/tools/init_config.py`.

### 4.3 REFACTOR Phase
Ensure interactive prompts degrade gracefully to non-interactive mode when `--yes` / `--non-interactive` is passed or stdout is non-TTY.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:25:00Z", "phase": 23, "tool": "rush_setup", "event": "stacks_detected", "languages": ["python", "typescript"], "frameworks": ["fastapi", "react"]}
{"timestamp": "2026-08-21T07:25:01Z", "phase": 23, "tool": "rush_setup", "event": "engine_installed", "engine": "ruff", "package_manager": "uv", "status": "success"}
{"timestamp": "2026-08-21T07:25:02Z", "phase": 23, "tool": "rush_init", "event": "config_generated", "file": "rush.toml", "tools_enabled": 14}
```

---

## 6. Step-by-Step Task Specifications

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
    """Inspect root manifests to identify languages, frameworks, and recommended engines."""
    ...
```

### Task 23.2: Sanitized Toolchain Installer (`src/rush/tools/setup_wizard.py`)
```python
import re
from pathlib import Path
from rush.tools.common import run_subprocess

PACKAGE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9@_./-]+$")

def install_engine_package(package_manager: str, package_name: str, cwd: Path) -> bool:
    """Execute typed, sanitized package manager installation commands."""
    ...
```

### Task 23.3: Configuration Initializer (`src/rush/tools/init_config.py`)
Generates a customized `rush.toml` based on detected stacks.

### Task 23.4: CLI & FastMCP Registrations
Register `rush setup`, `rush init`, `rush config check` in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Injection Guard**: Every package name must match `^[a-zA-Z0-9@_./-]+$`.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
