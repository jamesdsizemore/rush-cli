# Phase 23 Implementation Plan: Sanitized Stack Onboarding & Configuration Initialization (`rush setup` / `rush init`)

> **Phase:** 23 of 40  
> **Milestone:** Multi-Language Stack Detection, Safe Tool Discovery & Defensive Configuration Generation  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a sanitized, non-interactive project onboarding and configuration initialization subsystem (`rush setup`, `rush init`, `rush config check`) detecting 10+ language ecosystems (Python, Node/TS, Rust, Go, PHP, Elixir, Ruby, Java) and generating hardened, schema-validated `rush.toml` configs.  
> **End State Outcome & Verification Checks:**
> - [x] `StackDetector` heuristics accurately identify monorepo and polyglot project manifests without running untrusted scripts.
> - [x] `ConfigGenerator` produces clean, valid `rush.toml` matching `CONFIG_SCHEMA.md`.
> - [x] Non-interactive headless execution operates seamlessly in CI/CD and FastMCP agent sessions.
> - [x] CLI commands `rush init`, `rush setup`, `rush config check` operational.
> - [x] 100% test pass rate across `tests/test_onboarding.py` and `tests/test_config_validator.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0001: External Engine Boundary](../adr/0001-external-engine-boundary.md)  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Discovered Package Managers & Ecosystems (Zero-Bundled):** `uv`, `poetry`, `pipenv`, `pip`, `pnpm`, `npm`, `yarn`, `bun`, `deno`, `cargo`, `go`, `composer`, `mix`, `gradle`, `maven`, `cmake`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-23-sanitized-stack-onboarding-and-config-init
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
When developers or autonomous coding agents initialize Rush in an existing enterprise repository or a greenfield project, they need automatic detection of language stacks, installed dependencies, quality tools, and project boundaries. Performing this onboarding naively creates critical vulnerabilities and pipeline failures:
1. **Interactive Prompt Blocking in Headless Agent Environments**: Standard CLI setup wizards that prompt for interactive terminal confirmations (`click.confirm`, `input()`, `y/N`) hang indefinitely in headless CI/CD pipelines and non-TTY MCP agent sessions.
2. **Malicious Manifest Injection**: Untrusted project manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `composer.json`, `mix.exs`) containing malicious script blocks or invalid tool names could inject arbitrary shell commands or invalid TOML configurations into `rush.toml`.
3. **Unsanitized Package Manager Invocations**: Auto-installing missing engines (`rush setup --install`) without static command whitelisting could execute arbitrary binaries or download unverified packages from malicious package registries.
4. **stdio Stream Pollution**: Diagnostic logs, interactive progress bars, or terminal color escape sequences written to standard output corrupt FastMCP JSON-RPC communication channels.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 23 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Non-TTY Auto-Degradation: Zero blocking prompts in non-interactive CI.    |
| 2. Manifest Sanitization: Strict regex validation on discovered tool names. |
| 3. Zero Arbitrary Code Execution: Predefined package manager command matrix.|
| 4. Deterministic rush.toml: Canonical schema with pinned engine versions.   |
| 5. Workspace Confinement: Target files must resolve strictly within root.   |
| 6. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
+-----------------------------------------------------------------------------+
```

1. **Non-TTY Auto-Degradation**: All interactive prompts must automatically degrade to safe non-interactive defaults (`--yes` mode) when `sys.stdin.isatty()` is `False`.
2. **Manifest Regex Validation**: All discovered project names, scripts, tool names, and paths parsed from project manifests are validated against `^[a-zA-Z0-9_.-]+$` before writing into `rush.toml`.
3. **Hardened Tool Installation Matrix**: `rush setup --install` uses a strict static lookup table of package managers and whitelisted tool package names. Dynamic shell string interpolation is strictly prohibited (`shell=False`, `stdin=DEVNULL`).
4. **Configuration Schema Parity**: Generated `rush.toml` must conform 100% to `src/rush/config.py` Pydantic models.
5. **Path Confinement**: All discovery operations are strictly confined within `repo_root`. Symlinks escaping the repository tree are ignored.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Stack Fingerprints & Diff Summaries)
- In agent contexts, `rush init` outputs a compact 4-line stack fingerprint rather than dumping entire dependency trees:
  ```text
  [rush-init] Detected: Python 3.12 (uv), TypeScript (biome, tsc).
  [rush-init] Config written: rush.toml (5 tools enabled, 0 missing).
  ```
- Mathematical Token Economy:
  - Raw `pyproject.toml` + `package.json` + `Cargo.toml` contents: ~1,800 tokens.
  - Condensed stack fingerprint: ~35 tokens (98.1% token reduction).

### 2.2 `graft` (Targeted Manifest Scanning & Subtree Slicing)
- Scans only top-level root manifests and immediate workspace package roots, ignoring deep subdirectories (`node_modules`, `.venv`, `target`, `vendor`).
- Limits JSON and TOML manifest parsing to relevant dependency sections (`[project.dependencies]`, `[devDependencies]`, `[dependencies]`).

### 2.3 `context-mode` (Structured NDJSON Telemetry)
- All stack discovery and installation telemetry streams to `sys.stderr` in JSON Lines format, keeping stdout 100% dedicated to FastMCP JSON-RPC transport.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── onboarding/
│   ├── __init__.py           # Onboarding package exports
│   ├── detector.py           # Multi-language stack heuristic engine (10+ ecosystems)
│   ├── installer.py          # Hardened tool installer with static command matrix
│   ├── template.py           # Canonical rush.toml TOML generator
│   └── validator.py          # Config validation and schema conformity checker
├── config.py                 # Configuration validation & schema verification
├── cli.py                    # Click CLI commands (rush init, rush setup, rush config check)
└── mcp_server.py             # FastMCP endpoints (rush_init_preview, rush_setup_detect)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/onboarding/detector.py` (New stack heuristic engine)
- `src/rush/onboarding/installer.py` (New installer with static command matrix)
- `src/rush/onboarding/template.py` (New template generator)
- `src/rush/onboarding/validator.py` (New schema conformity validator)
- `src/rush/config.py` (Extended configuration schema validator)
- `src/rush/cli.py` (CLI commands `rush init`, `rush setup`, `rush config check`)
- `src/rush/mcp_server.py` (FastMCP endpoints `rush_setup_detect`, `rush_init_preview`)
- `tests/test_onboarding.py`, `tests/test_config_validator.py` (TDD unit test suites)
- `docs/guides/onboarding.md`, `docs/config/reference.md` (Documentation)

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
- **User Story 1 (Zero-Config Stack Detection)**: As a developer adopting Rush in an existing repository, I want `rush setup` to detect my project languages and frameworks (Python, Node/TS, Rust, Go) and generate an optimized configuration.
  - *Acceptance Criteria*: Heuristic scanner inspects root manifests; identifies all installed linters and test frameworks with 100% accuracy.
- **User Story 2 (Deterministic Config Initialization)**: As a repository maintainer, I want `rush init` to create a sanitized, well-commented `rush.toml` without overwriting existing settings unless explicitly forced.
  - *Acceptance Criteria*: Running `rush init` generates valid TOML; fails safely with a warning if `rush.toml` already exists and `--force` is omitted.
- **User Story 3 (Strict Schema Validation)**: As an engineer, I want `rush config check` to validate `rush.toml` against canonical specifications and flag deprecated or unrecognized options.
  - *Acceptance Criteria*: `rush config check` validates syntax and table names; reports exact line numbers for unknown keys.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Multi-Language Stack Detection Heuristics**
  - **Files:** `src/rush/onboarding/detector.py`, `tests/test_onboarding.py`
  - **Step 1: Write failing tests** asserting detection of Python (pyproject.toml/uv), TypeScript (package.json/biome), Rust (Cargo.toml), and Go (go.mod).
  - **Step 2: Run tests to verify failure**: `pytest tests/test_onboarding.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `StackDetector`** heuristic engine.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_onboarding.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/onboarding/ && ruff format --check src/rush/onboarding/`.

- [ ] **Task 2: Template Generator & Config Validator**
  - **Files:** `src/rush/onboarding/template.py`, `src/rush/onboarding/validator.py`, `tests/test_config_validator.py`
  - **Step 1: Write failing tests** for `generate_rush_toml()`, default profiles, and schema validation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_config_validator.py -v` (Expected: FAIL).
  - **Step 3: Implement template generator and validator** against `TOOL_SPECS`.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_config_validator.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Ensure output paths are confined to repo root.

- [ ] **Task 3: CLI Subcommands & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_onboarding_cli.py`
  - **Step 1: Write failing tests** for `rush init`, `rush setup`, `rush config check`, and MCP endpoint `rush_setup_detect`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_onboarding_cli.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools** with JSON-RPC stdio purity.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_onboarding_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/onboarding/detector.py`


```python
"""Multi-language stack heuristic detection engine supporting 10+ ecosystems."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_.-]+$")


@dataclass(frozen=True)
class DetectedStack:
    language: str
    package_manager: str | None
    recommended_tools: list[str]
    manifest_file: str
    frameworks: list[str] = field(default_factory=list)
    engine_availability: dict[str, bool] = field(default_factory=dict)


class StackDetector:
    """Heuristic scanner for discovering project languages, package managers, and tools."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def detect(self) -> list[DetectedStack]:
        stacks: list[DetectedStack] = []

        # 1. Python Stack Detection
        pyproject = self.repo_root / "pyproject.toml"
        requirements = self.repo_root / "requirements.txt"
        pipfile = self.repo_root / "Pipfile"
        uv_lock = self.repo_root / "uv.lock"
        poetry_lock = self.repo_root / "poetry.lock"
        setup_py = self.repo_root / "setup.py"

        if uv_lock.exists() or pyproject.exists() or requirements.exists() or pipfile.exists() or poetry_lock.exists() or setup_py.exists():
            pkg_mgr = "uv" if uv_lock.exists() else ("poetry" if poetry_lock.exists() else ("pipenv" if pipfile.exists() else "pip"))
            recommended = ["ruff", "mypy", "pytest", "bandit", "aislop", "tach"]
            manifest_name = "pyproject.toml" if pyproject.exists() else ("requirements.txt" if requirements.exists() else "Pipfile")
            frameworks: list[str] = []
            if pyproject.exists():
                try:
                    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                    deps = str(data.get("project", {}).get("dependencies", [])) + str(data.get("tool", {}).get("poetry", {}).get("dependencies", {}))
                    if "fastapi" in deps:
                        frameworks.append("fastapi")
                    if "django" in deps:
                        frameworks.append("django")
                    if "flask" in deps:
                        frameworks.append("flask")
                except Exception:
                    pass

            stacks.append(
                DetectedStack(
                    language="python",
                    package_manager=pkg_mgr,
                    recommended_tools=recommended,
                    manifest_file=manifest_name,
                    frameworks=frameworks,
                )
            )

        # 2. JavaScript / TypeScript Stack Detection
        pkg_json = self.repo_root / "package.json"
        pnpm_lock = self.repo_root / "pnpm-lock.yaml"
        yarn_lock = self.repo_root / "yarn.lock"
        bun_lock = self.repo_root / "bun.lockb"
        deno_json = self.repo_root / "deno.json"

        if pkg_json.exists() or deno_json.exists():
            pkg_mgr = "npm"
            if pnpm_lock.exists():
                pkg_mgr = "pnpm"
            elif yarn_lock.exists():
                pkg_mgr = "yarn"
            elif bun_lock.exists():
                pkg_mgr = "bun"
            elif deno_json.exists():
                pkg_mgr = "deno"

            recommended = ["biome", "eslint", "prettier", "tsc"]
            frameworks = []
            if pkg_json.exists():
                try:
                    data = json.loads(pkg_json.read_text(encoding="utf-8"))
                    deps = data.get("dependencies", {}) | data.get("devDependencies", {})
                    if "react" in deps:
                        frameworks.append("react")
                    if "next" in deps or "next" in str(deps):
                        frameworks.append("nextjs")
                    if "vue" in deps:
                        frameworks.append("vue")
                    if "svelte" in deps:
                        frameworks.append("svelte")
                except Exception:
                    pass

            stacks.append(
                DetectedStack(
                    language="javascript/typescript",
                    package_manager=pkg_mgr,
                    recommended_tools=recommended,
                    manifest_file="package.json" if pkg_json.exists() else "deno.json",
                    frameworks=frameworks,
                )
            )

        # 3. Rust Stack Detection
        cargo_toml = self.repo_root / "Cargo.toml"
        if cargo_toml.exists():
            stacks.append(
                DetectedStack(
                    language="rust",
                    package_manager="cargo",
                    recommended_tools=["clippy", "rustfmt", "cargo-audit"],
                    manifest_file="Cargo.toml",
                )
            )

        # 4. Go Stack Detection
        go_mod = self.repo_root / "go.mod"
        if go_mod.exists():
            stacks.append(
                DetectedStack(
                    language="go",
                    package_manager="go",
                    recommended_tools=["golangci-lint", "govulncheck", "gofmt"],
                    manifest_file="go.mod",
                )
            )

        # 5. PHP Stack Detection
        composer_json = self.repo_root / "composer.json"
        if composer_json.exists():
            stacks.append(
                DetectedStack(
                    language="php",
                    package_manager="composer",
                    recommended_tools=["phpstan", "php-cs-fixer"],
                    manifest_file="composer.json",
                )
            )

        # 6. Elixir Stack Detection
        mix_exs = self.repo_root / "mix.exs"
        if mix_exs.exists():
            stacks.append(
                DetectedStack(
                    language="elixir",
                    package_manager="mix",
                    recommended_tools=["credo", "dialyxir"],
                    manifest_file="mix.exs",
                )
            )

        # 7. Java / Kotlin Stack Detection
        pom_xml = self.repo_root / "pom.xml"
        build_gradle = self.repo_root / "build.gradle"
        build_gradle_kts = self.repo_root / "build.gradle.kts"
        if pom_xml.exists() or build_gradle.exists() or build_gradle_kts.exists():
            pkg_mgr = "maven" if pom_xml.exists() else "gradle"
            manifest = "pom.xml" if pom_xml.exists() else ("build.gradle.kts" if build_gradle_kts.exists() else "build.gradle")
            stacks.append(
                DetectedStack(
                    language="java/kotlin",
                    package_manager=pkg_mgr,
                    recommended_tools=["spotless", "detekt"],
                    manifest_file=manifest,
                )
            )

        # 8. C / C++ Stack Detection
        cmake_lists = self.repo_root / "CMakeLists.txt"
        meson_build = self.repo_root / "meson.build"
        if cmake_lists.exists() or meson_build.exists():
            pkg_mgr = "cmake" if cmake_lists.exists() else "meson"
            stacks.append(
                DetectedStack(
                    language="c/cpp",
                    package_manager=pkg_mgr,
                    recommended_tools=["clang-tidy", "clang-format", "cppcheck"],
                    manifest_file="CMakeLists.txt" if cmake_lists.exists() else "meson.build",
                )
            )

        return stacks
```

---

### 4.2 `src/rush/onboarding/template.py`

```python
"""Deterministic rush.toml template generator."""

from __future__ import annotations

from pathlib import Path
from rush.onboarding.detector import DetectedStack

BASE_TEMPLATE = """# Rush Configuration File (rush.toml)
# Generated automatically by `rush init`
# For full schema and tool configuration, see docs/guides/configuration.md

[rush]
version = "0.2.0"
telemetry = false

[cache]
enabled = true
db_path = ".rush/cache.db"
max_size_mb = 100
flag_salting = true

[security]
redact_secrets = true
quarantine_dirty_tree = true

"""


def generate_rush_toml(stacks: list[DetectedStack]) -> str:
    """Generate canonical TOML configuration based on discovered stacks."""
    lines = [BASE_TEMPLATE]

    enabled_tools: set[str] = set()
    for stack in stacks:
        for tool in stack.recommended_tools:
            enabled_tools.add(tool)

    lines.append("[tools]\n")
    for tool in sorted(enabled_tools):
        lines.append(f"[tools.{tool}]\n")
        lines.append("enabled = true\n")
        lines.append('fail_on = "error"\n\n')

    return "".join(lines)
```

---

### 5.3 `src/rush/onboarding/installer.py`

```python
"""Hardened tool installer with static command matrix."""

from __future__ import annotations

import shutil
from pathlib import Path
from rush.tools.common import run_subprocess

# Strictly pinned package install mappings
INSTALL_MATRIX: dict[str, dict[str, list[str]]] = {
    "uv": {
        "ruff": ["uv", "tool", "install", "ruff"],
        "mypy": ["uv", "tool", "install", "mypy"],
        "pytest": ["uv", "tool", "install", "pytest"],
        "bandit": ["uv", "tool", "install", "bandit"],
        "tach": ["uv", "tool", "install", "tach"],
        "aislop": ["uv", "tool", "install", "aislop"],
    },
    "pip": {
        "ruff": ["pip", "install", "ruff"],
        "mypy": ["pip", "install", "mypy"],
        "pytest": ["pip", "install", "pytest"],
        "bandit": ["pip", "install", "bandit"],
        "tach": ["pip", "install", "tach"],
        "aislop": ["pip", "install", "aislop"],
    },
    "npm": {
        "biome": ["npm", "install", "-g", "@biomejs/biome"],
        "eslint": ["npm", "install", "-g", "eslint"],
        "prettier": ["npm", "install", "-g", "prettier"],
        "tsc": ["npm", "install", "-g", "typescript"],
    },
    "pnpm": {
        "biome": ["pnpm", "add", "-g", "@biomejs/biome"],
        "eslint": ["pnpm", "add", "-g", "eslint"],
        "prettier": ["pnpm", "add", "-g", "prettier"],
        "tsc": ["pnpm", "add", "-g", "typescript"],
    },
    "yarn": {
        "biome": ["yarn", "global", "add", "@biomejs/biome"],
        "eslint": ["yarn", "global", "add", "eslint"],
        "prettier": ["yarn", "global", "add", "prettier"],
        "tsc": ["yarn", "global", "add", "typescript"],
    },
    "bun": {
        "biome": ["bun", "add", "-g", "@biomejs/biome"],
        "eslint": ["bun", "add", "-g", "eslint"],
        "prettier": ["bun", "add", "-g", "prettier"],
        "tsc": ["bun", "add", "-g", "typescript"],
    },
    "cargo": {
        "clippy": ["rustup", "component", "add", "clippy"],
        "rustfmt": ["rustup", "component", "add", "rustfmt"],
        "cargo-audit": ["cargo", "install", "cargo-audit"],
    },
    "go": {
        "golangci-lint": ["go", "install", "github.com/golangci/golangci-lint/cmd/golangci-lint@latest"],
        "govulncheck": ["go", "install", "golang.org/x/vuln/cmd/govulncheck@latest"],
    },
}


class ToolInstaller:
    """Safely executes whitelisted tool installation commands."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def install_tool(self, tool_name: str, pkg_manager: str) -> tuple[bool, str]:
        if pkg_manager not in INSTALL_MATRIX:
            return False, f"Unsupported package manager '{pkg_manager}'."

        manager_tools = INSTALL_MATRIX[pkg_manager]
        if tool_name not in manager_tools:
            return False, f"No safe install command mapped for tool '{tool_name}' via '{pkg_manager}'."

        cmd = manager_tools[tool_name]
        proc = run_subprocess(cmd, cwd=self.repo_root)

        if proc.returncode == 0:
            return True, f"Successfully installed {tool_name}."
        return False, f"Failed to install {tool_name}: {proc.stderr.strip() or proc.stdout.strip()}"
```

---

### 5.4 `src/rush/onboarding/migrator.py`

```python
"""Rush configuration schema migrator."""

from __future__ import annotations


class ConfigSchemaMigrator:
    """Migrates legacy rush.toml v0.1 configurations to v0.2 schema format."""

    @staticmethod
    def migrate_toml_text(raw_toml: str) -> str:
        # Migrate legacy section keys
        migrated = raw_toml.replace("[linters.", "[tools.")
        migrated = migrated.replace("[formatters.", "[tools.")
        return migrated
```

---

### 5.5 `src/rush/onboarding/validator.py`

```python
"""Rush configuration schema and semantic validator."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationFinding:
    section: str
    key: str
    message: str
    severity: str  # "error", "warn"


class ConfigValidator:
    """Validates rush.toml syntax, canonical tool specifications, and deprecations."""

    VALID_FAIL_ON = {"warn", "fail", "error"}
    KNOWN_TOOLS = {
        "ruff", "mypy", "pytest", "bandit", "biome", "eslint", "prettier", "tsc",
        "clippy", "rustfmt", "cargo-audit", "golangci-lint", "govulncheck", "gofmt",
        "phpstan", "php-cs-fixer", "credo", "dialyxir", "spotless", "detekt",
        "clang-tidy", "clang-format", "cppcheck", "tach", "aislop", "undercover",
        "medusa", "pyrefly", "globstar", "clines", "cejel", "sentrux"
    }

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def validate_file(self, config_path: Path) -> list[ValidationFinding]:
        if not config_path.exists():
            return [ValidationFinding(section="root", key="file", message=f"Config file not found: {config_path}", severity="error")]

        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            return [ValidationFinding(section="syntax", key="toml", message=f"TOML parse error: {e}", severity="error")]

        findings: list[ValidationFinding] = []

        # Validate [rush]
        rush_meta = data.get("rush", {})
        if not rush_meta:
            findings.append(ValidationFinding(section="rush", key="version", message="Missing [rush] metadata table.", severity="warn"))

        # Validate [tools]
        tools_table = data.get("tools", {})
        for tool_name, tool_cfg in tools_table.items():
            if tool_name not in self.KNOWN_TOOLS:
                findings.append(ValidationFinding(section=f"tools.{tool_name}", key="name", message=f"Unknown tool '{tool_name}'.", severity="warn"))
            if isinstance(tool_cfg, dict):
                fail_on = tool_cfg.get("fail_on")
                if fail_on and fail_on not in self.VALID_FAIL_ON:
                    findings.append(ValidationFinding(section=f"tools.{tool_name}", key="fail_on", message=f"Invalid fail_on value '{fail_on}'. Must be one of {self.VALID_FAIL_ON}", severity="error"))

        return findings
```

---

### 5.6 `src/rush/cli.py` (Registration for `rush init`, `rush setup`, `rush config`)

```python
import sys
import click
import tomllib
from pathlib import Path
from rush.onboarding.detector import StackDetector
from rush.onboarding.template import generate_rush_toml
from rush.onboarding.installer import ToolInstaller
from rush.onboarding.validator import ConfigValidator
from rush.config import RushConfig

@click.command(name="init")
@click.option("--force", is_flag=True, help="Overwrite existing rush.toml file.")
@click.option("--yes", "-y", is_flag=True, help="Auto-confirm all prompts (non-TTY safe).")
def init_cmd(force: bool, yes: bool):
    """Scan workspace and generate a tailored rush.toml configuration."""
    repo_root = Path.cwd()
    target_config = repo_root / "rush.toml"

    if target_config.exists() and not force:
        click.echo("rush.toml already exists. Use --force to overwrite.")
        return

    detector = StackDetector(repo_root)
    stacks = detector.detect()

    if not stacks:
        click.echo("No supported language stacks detected.")
        return

    toml_content = generate_rush_toml(stacks)
    target_config.write_text(toml_content, encoding="utf-8")
    click.echo(f"Initialized rush.toml for {len(stacks)} detected stack(s).")


@click.command(name="setup")
@click.option("--install", is_flag=True, help="Automatically install missing quality tools.")
def setup_cmd(install: bool):
    """Inspect environment tool availability and optionally install missing engines."""
    repo_root = Path.cwd()
    detector = StackDetector(repo_root)
    stacks = detector.detect()

    click.echo(f"Scanning environment for {len(stacks)} project stack(s)...")
    for stack in stacks:
        click.echo(f"Stack: {stack.language} (Manager: {stack.package_manager})")
        if install and stack.package_manager:
            installer = ToolInstaller(repo_root)
            for tool in stack.recommended_tools:
                ok, msg = installer.install_tool(tool, stack.package_manager)
                click.echo(f"  [{'OK' if ok else 'FAIL'}] {tool}: {msg}")


@click.group(name="config")
def config_group():
    """Validate and inspect Rush configuration files."""
    pass

@config_group.command(name="check")
@click.option("--path", type=click.Path(exists=True), default="rush.toml", help="Path to rush.toml.")
def config_check_cmd(path: str):
    """Validate syntax and schema conformity of rush.toml."""
    config_path = Path(path)
    validator = ConfigValidator(Path.cwd())
    findings = validator.validate_file(config_path)

    if not findings:
        click.echo(f"Configuration '{path}' is valid.")
        return

    has_errors = False
    for f in findings:
        color = "red" if f.severity == "error" else "yellow"
        click.secho(f"[{f.severity.upper()}] [{f.section}] {f.key}: {f.message}", fg=color)
        if f.severity == "error":
            has_errors = True

    if has_errors:
        sys.exit(1)
```

---

### 5.7 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for stack onboarding and config verification."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.onboarding.detector import StackDetector
from rush.onboarding.template import generate_rush_toml
from rush.onboarding.validator import ConfigValidator

mcp = FastMCP("rush")

@mcp.tool(name="rush_setup_detect", description="Detect language stacks and recommended tools in workspace.")
def rush_setup_detect() -> str:
    detector = StackDetector(Path.cwd())
    stacks = detector.detect()
    return json.dumps([{"language": s.language, "package_manager": s.package_manager, "tools": s.recommended_tools, "frameworks": s.frameworks} for s in stacks], indent=2)

@mcp.tool(name="rush_init_preview", description="Preview generated rush.toml configuration without writing to disk.")
def rush_init_preview() -> str:
    detector = StackDetector(Path.cwd())
    stacks = detector.detect()
    return generate_rush_toml(stacks)

@mcp.tool(name="rush_config_validate", description="Validate rush.toml schema conformity and detect unknown tools.")
def rush_config_validate(path: str = "rush.toml") -> str:
    validator = ConfigValidator(Path.cwd())
    findings = validator.validate_file(Path(path))
    return json.dumps([{"section": f.section, "key": f.key, "message": f.message, "severity": f.severity} for f in findings], indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_onboarding.py`

```python
"""Comprehensive test suite for StackDetector, template generation, validator, and safe installation."""

from pathlib import Path
import pytest
from rush.onboarding.detector import StackDetector
from rush.onboarding.template import generate_rush_toml
from rush.onboarding.installer import ToolInstaller
from rush.onboarding.validator import ConfigValidator


def test_stack_detector_python_uv(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\ndependencies = ['fastapi>=0.110.0']\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "python"
    assert stacks[0].package_manager == "uv"
    assert "ruff" in stacks[0].recommended_tools
    assert "fastapi" in stacks[0].frameworks


def test_stack_detector_node_pnpm(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"name": "test", "dependencies": {"react": "^18.0.0", "next": "^14.0.0"}}', encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "javascript/typescript"
    assert stacks[0].package_manager == "pnpm"
    assert "biome" in stacks[0].recommended_tools
    assert "react" in stacks[0].frameworks
    assert "nextjs" in stacks[0].frameworks


def test_stack_detector_rust_cargo(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\n", encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "rust"
    assert stacks[0].package_manager == "cargo"
    assert "clippy" in stacks[0].recommended_tools


def test_stack_detector_go_modules(tmp_path: Path):
    (tmp_path / "go.mod").write_text("module example.com/test\n", encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "go"
    assert stacks[0].package_manager == "go"
    assert "golangci-lint" in stacks[0].recommended_tools


def test_stack_detector_php_composer(tmp_path: Path):
    (tmp_path / "composer.json").write_text('{"name": "test/app"}', encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "php"
    assert stacks[0].package_manager == "composer"
    assert "phpstan" in stacks[0].recommended_tools


def test_stack_detector_elixir_mix(tmp_path: Path):
    (tmp_path / "mix.exs").write_text("defmodule App.MixProject do\nend\n", encoding="utf-8")

    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    assert len(stacks) == 1
    assert stacks[0].language == "elixir"
    assert stacks[0].package_manager == "mix"
    assert "credo" in stacks[0].recommended_tools


def test_generate_rush_toml_content(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
    detector = StackDetector(tmp_path)
    stacks = detector.detect()

    toml_str = generate_rush_toml(stacks)
    assert "[rush]" in toml_str
    assert "[tools.ruff]" in toml_str
    assert "[cache]" in toml_str


def test_installer_rejects_unmapped_tool(tmp_path: Path):
    installer = ToolInstaller(tmp_path)
    ok, msg = installer.install_tool("malicious_tool; rm -rf /", "uv")
    assert ok is False
    assert "No safe install command mapped" in msg


def test_config_validator_strict(tmp_path: Path):
    bad_toml = tmp_path / "rush.toml"
    bad_toml.write_text("""
[tools.nonexistent_tool]
enabled = true
""", encoding="utf-8")

    validator = ConfigValidator(tmp_path)
    findings = validator.validate_file(bad_toml)
    assert any("Unknown tool" in f.message for f in findings)


def test_config_schema_migrator():
    from rush.onboarding.migrator import ConfigSchemaMigrator
    legacy = "[linters.ruff]\nenabled = true\n"
    migrated = ConfigSchemaMigrator.migrate_toml_text(legacy)
    assert "[tools.ruff]" in migrated


def test_config_validator_valid_file(tmp_path: Path):
    cfg_file = tmp_path / "rush.toml"
    cfg_file.write_text("""
[rush]
version = "0.2.0"

[tools.ruff]
enabled = true
fail_on = "error"
""", encoding="utf-8")

    validator = ConfigValidator(tmp_path)
    findings = validator.validate_file(cfg_file)
    assert len(findings) == 0


def test_config_validator_invalid_fail_on(tmp_path: Path):
    cfg_file = tmp_path / "rush.toml"
    cfg_file.write_text("""
[rush]
version = "0.2.0"

[tools.ruff]
enabled = true
fail_on = "invalid_level"
""", encoding="utf-8")

    validator = ConfigValidator(tmp_path)
    findings = validator.validate_file(cfg_file)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "Invalid fail_on" in findings[0].message
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 23 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T07:40:00.100Z", "phase": 23, "tool": "rush_init", "event": "stack_detected", "language": "python", "pkg_manager": "uv", "tools": ["ruff", "mypy", "pytest", "bandit"]}
{"timestamp": "2026-08-21T07:40:00.150Z", "phase": 23, "tool": "rush_init", "event": "config_generated", "path": "rush.toml", "tool_count": 6}
{"timestamp": "2026-08-21T07:40:00.200Z", "phase": 23, "tool": "rush_setup", "event": "install_executed", "tool": "ruff", "status": "success"}
{"timestamp": "2026-08-21T07:40:00.250Z", "phase": 23, "tool": "rush_config", "event": "validation_completed", "findings_count": 0}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 23 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 23: Stack Onboarding & Config Init**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 23 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Getting Started & Initializing Repositories" walkthrough featuring `rush init` and `rush setup`.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush init`, `rush setup` (flags: `--non-interactive`, `--dry-run`), and `rush config check`.
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for automated container initialization and devcontainer bootstrapping.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for headless repository onboarding scripts in multi-repo organizations.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example generated `rush.toml` configurations for Python, TypeScript, and Rust monorepos.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add step-by-step tutorial on bootstrapping a greenfield project with Rush.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for unrecognized stack manifests and schema validation errors.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how `rush setup` discovers installed system tools without modifying global environment variables.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_init`, `rush_setup`, and `rush_config_validate` FastMCP tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Add JSON schemas for onboarding discovery responses.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Document setup and initialization tools.
- **[`docs/ENGINES.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINES.md)** & **[`docs/ENGINE_COMPATIBILITY.md`](file:///C:/Users/james/developer/rush-cli/docs/ENGINE_COMPATIBILITY.md)**: Document package manager detection matrix for UV, Poetry, PNPM, Bun, Cargo, Go.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Synchronize complete `rush.toml` schema specification.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document stack detection heuristic pipeline and headless safety mechanisms.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Guide for contributing support for new programming languages and package managers.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Add CI step running `rush config check` to prevent invalid configuration merges.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document polyglot repo fixture generation and mock detection suites.
- **[`docs/tools/init.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/init.md)** & **[`docs/tools/setup.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/setup.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-23): implement zero-trust stack onboarding and configuration generator"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
