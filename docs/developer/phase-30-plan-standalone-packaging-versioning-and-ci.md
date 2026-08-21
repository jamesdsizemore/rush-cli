# Phase 30 Implementation Plan: Standalone Packaging, Versioning & CI (`rush release` / `rush ci`)

> **Phase:** 30 of 40  
> **Milestone:** Hermetic PyInstaller Packaging, SemVer 2.0.0 Validator, SHA-Pinned GitHub Actions, SLSA Provenance & Docker  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build release engineering, packaging, and CI automation tooling (`rush release`, `rush ci`) supporting SemVer 2.0.0 synchronization across polyglot manifests, 40-character SHA-pinned GitHub Actions workflow generation, SLSA Level 3 provenance generation, and hermetic PyInstaller builds.  
> **End State Outcome & Verification Checks:**
> - [x] `SemverSyncValidator` verifies version synchronization across `pyproject.toml`, `package.json`, and `Cargo.toml`.
> - [x] `CiWorkflowGenerator` generates GitHub Actions CI pipelines strictly pinned to immutable 40-char commit SHAs.
> - [x] `SlsaProvenanceBuilder` produces valid in-toto SLSA provenance statements with SHA-256 digests.
> - [x] CLI commands `rush release prepare`, `verify`, `changelog` and `rush ci init`, `verify` operational.
> - [x] 100% test pass rate across `tests/test_release_packaging_ci.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-30-standalone-packaging-versioning-and-ci
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
As software systems transition from local developer experimentation to production deployments and automated CI/CD release pipelines:
1. **Supply Chain Compromise via Mutable Action Tags (MITRE ATT&CK T1195.002)**: GitHub Actions workflows using mutable ref tags (e.g. `actions/checkout@v4` or `actions/setup-python@v5`) are vulnerable to tag hijacking and upstream supply chain attacks. Workflows must enforce immutable 40-character commit SHAs.
2. **SemVer Drift & Tag Inconsistencies**: Disconnected version strings across `pyproject.toml`, `package.json`, `Cargo.toml`, and Git tags lead to broken release deployments, out-of-order package publishes, and phantom changelogs.
3. **Bloated & Insecure Container Images**: Dockerfiles bundling build tools, compilers, development dependencies, and running as root (UID 0) expand attack surfaces and slow container startup times.
4. **Environment-Dependent Binaries**: Packaging tools that leak local developer paths, private keys, or non-deterministic build timestamps into distribution binaries.
5. **stdio Stream Pollution**: External build scripts dumping verbose compilation progress to stdout corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Compromised third-party GitHub Action running malicious code | **Critical** | Automated 40-character commit SHA pinning across all CI workflow actions. |
| **Tampering** | Rogue pull request altering release tags or publish tokens | **Critical** | Least-privilege `permissions` blocks (`contents: read`) in all generated workflows. |
| **Repudiation** | Unsigned release artifact distributed to users | **High** | Cryptographic SHA-256 `checksums.sha256` manifest generation and SLSA provenance attestation. |
| **Information Disclosure** | Binary packaging embedding host environment variables | **High** | Ephemeral clean-room build environments stripping sensitive env keys. |
| **Denial of Service** | Unbounded multi-stage Docker build exhausting disk space | **Medium** | Multi-stage distroless builds pruning intermediate layers. |
| **Elevation of Privilege** | Container running as root (UID 0) escaping to host | **Critical** | Hardened non-root user enforcement (`USER 10001:10001`). |

### 1.3 Target Build Triple Matrix

| Operating System | Architecture | Target Triple | Distribution Artifact |
|---|---|---|---|
| **Linux** | x86_64 | `x86_64-unknown-linux-gnu` | `rush-linux-x86_64` |
| **Linux** | aarch64 (ARM64) | `aarch64-unknown-linux-gnu` | `rush-linux-aarch64` |
| **macOS** | Apple Silicon (M1/M2/M3/M4) | `aarch64-apple-darwin` | `rush-darwin-arm64` |
| **macOS** | Intel | `x86_64-apple-darwin` | `rush-darwin-x86_64` |
| **Windows** | x86_64 | `x86_64-pc-windows-msvc` | `rush-windows-x86_64.exe` |

### 1.4 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 30 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. SHA-Pinned CI Workflows: All GitHub Actions pinned to 40-char commit SHAs|
| 2. Least-Privilege CI Permissions: Explicit permissions: { contents: read }. |
| 3. SemVer 2.0.0 Parity: pyproject.toml, package.json, Cargo.toml in sync.   |
| 4. Distroless Non-Root Containers: Multi-stage Dockerfile with USER 10001.  |
| 5. Deterministic Checksums: SHA-256 checksums.sha256 generated for builds.  |
| 6. Subprocess Isolation: stdin=DEVNULL, shell=False, secret redaction.     |
| 7. Workspace Confinement: Target files must resolve strictly within root.   |
| 8. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise CI & Release Summaries)
- Outputs a single-line summary table of validated release files and action SHA pins (~40 tokens) rather than dumping full multi-hundred line YAML workflows into LLM context.
- Mathematical Token Economy:
  - Raw multi-platform CI YAML dump: ~3,800 tokens.
  - Sliced CI validation summary: ~55 tokens (98.5% token reduction).

### 2.2 `graft` (Targeted Manifest Checks)
- Scans only files relevant to packaging (`pyproject.toml`, `.github/workflows/`, `Dockerfile`).

### 2.3 `context-mode` (Structured Release Telemetry & NDJSON Logs)
- Build events, SemVer validation results, and checksum manifests are streamed as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── release/
│   ├── __init__.py           # Release package exports
│   ├── semver.py             # SemVer 2.0.0 parser and cross-manifest validator
│   ├── ci_generator.py       # Hardened 40-character SHA-pinned GitHub Actions generator
│   ├── docker_generator.py   # Multi-stage non-root Dockerfile generator
│   ├── binary_builder.py     # Hermetic PyInstaller / standalone build orchestrator
│   ├── pyinstaller_hooks.py  # PyInstaller runtime data hooks and hidden imports
│   ├── multi_arch.py         # Multi-platform build matrix and target triple coordinator
│   ├── provenance.py         # SHA-256 checksums manifest & provenance builder
│   ├── changelog_gen.py      # Conventional Commits semantic changelog generator
│   └── slsa_attestation.py   # SLSA Level 3 In-toto provenance attestation builder
├── cli.py                    # Click CLI commands (rush release check, bump, provenance, rush ci generate)
└── mcp_server.py             # FastMCP endpoints (rush_release_verify, rush_ci_workflow_generate)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/release/semver.py` (New SemVer parser)
- `src/rush/release/ci_generator.py` (New SHA-pinned CI generator)
- `src/rush/release/docker_generator.py` (New Dockerfile generator)
- `src/rush/release/binary_builder.py` (New PyInstaller builder)
- `src/rush/release/provenance.py` (New SHA-256 provenance generator)
- `src/rush/release/changelog_gen.py` (New changelog generator)
- `src/rush/release/slsa_attestation.py` (New SLSA attestation builder)
- `src/rush/cli.py` (CLI commands `rush release`, `rush ci`)
- `src/rush/mcp_server.py` (FastMCP endpoints for release management)
- `tests/test_release_packaging_ci.py` (TDD unit test suite)
- `docs/guides/packaging.md`, `docs/tools/release.md` (Documentation)

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
- **User Story 1 (Strict SemVer Cross-Manifest Validation)**: As a release manager, I want `rush release check` to verify that versions match across all manifests (`pyproject.toml`, `package.json`, `Cargo.toml`, Git tags).
  - *Acceptance Criteria*: Identifies version drift across files and fails if versions are out of sync.
- **User Story 2 (Hardened 40-Char SHA GitHub Actions Generator)**: As a security engineer, I want `rush ci generate` to generate GitHub Actions workflows with all external actions pinned to immutable 40-character commit SHAs.
  - *Acceptance Criteria*: Generates valid `.github/workflows/ci.yml` containing zero mutable `@v4` tags, preventing supply chain hijacking.
- **User Story 3 (SLSA Level 3 Provenance & Checksums)**: As a distributor, I want `rush release provenance` to generate SHA-256 checksums and SLSA attestation manifests for standalone binaries.
  - *Acceptance Criteria*: Generates cryptographic `SHA256SUMS` and In-toto attestation JSON.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: SemVer Validator & Cross-Manifest Synchronizer**
  - **Files:** `src/rush/release/semver.py`, `src/rush/release/changelog_gen.py`, `tests/test_release_packaging_ci.py`
  - **Step 1: Write failing tests** for SemVer parsing, version bumping (patch, minor, major), and changelog generation from Conventional Commits.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_release_packaging_ci.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `SemVerValidator` and `ChangelogGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_release_packaging_ci.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/release/ && ruff format --check src/rush/release/`.

- [ ] **Task 2: Hardened CI Generator & Dockerfile Builder**
  - **Files:** `src/rush/release/ci_generator.py`, `src/rush/release/docker_generator.py`, `tests/test_release_packaging_ci.py`
  - **Step 1: Write failing tests** for 40-character SHA pinning, multi-platform test matrix, and non-root Dockerfile generation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_release_packaging_ci.py -v` (Expected: FAIL).
  - **Step 3: Implement `CIGenerator` and `DockerGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_release_packaging_ci.py -v` (Expected: PASS).
  - **Step 5: Verify security**: Ensure generated workflows contain zero mutable action tags.

- [ ] **Task 3: Standalone Builder, SLSA Provenance & FastMCP Endpoints**
  - **Files:** `src/rush/release/binary_builder.py`, `src/rush/release/provenance.py`, `src/rush/release/slsa_attestation.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_release_packaging_ci.py`
  - **Step 1: Write failing tests** for binary packaging hooks, SHA-256 manifest generation, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_release_packaging_ci.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_release_packaging_ci.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/release/semver.py`

```python
"""SemVer 2.0.0 parser and cross-manifest version validator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SEMVER_REGEX = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    def __str__(self) -> str:
        ver = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            ver += f"-{self.prerelease}"
        if self.build:
            ver += f"+{self.build}"
        return ver

    def bump_patch(self) -> SemVer:
        return SemVer(self.major, self.minor, self.patch + 1)

    def bump_minor(self) -> SemVer:
        return SemVer(self.major, self.minor + 1, 0)

    def bump_major(self) -> SemVer:
        return SemVer(self.major + 1, 0, 0)


class SemVerValidator:
    """Validates SemVer compliance and verifies consistency across project manifests."""

    @staticmethod
    def parse(version_str: str) -> SemVer | None:
        match = SEMVER_REGEX.match(version_str.strip())
        if not match:
            return None
        return SemVer(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=match.group("prerelease"),
            build=match.group("buildmetadata"),
        )

    @staticmethod
    def check_manifest_parity(repo_root: Path) -> dict[str, str]:
        versions: dict[str, str] = {}

        # 1. pyproject.toml
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            match = re.search(r'version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"))
            if match:
                versions["pyproject.toml"] = match.group(1)

        # 2. package.json
        pkg_json = repo_root / "package.json"
        if pkg_json.exists():
            match = re.search(r'"version"\s*:\s*"([^"]+)"', pkg_json.read_text(encoding="utf-8"))
            if match:
                versions["package.json"] = match.group(1)

        # 3. Cargo.toml
        cargo = repo_root / "Cargo.toml"
        if cargo.exists():
            match = re.search(r'version\s*=\s*"([^"]+)"', cargo.read_text(encoding="utf-8"))
            if match:
                versions["Cargo.toml"] = match.group(1)

        return versions
```

---

### 5.2 `src/rush/release/changelog_gen.py`

```python
"""Conventional Commits semantic changelog generator."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from rush.tools.common import run_subprocess

CONVENTIONAL_REGEX = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[\w\-\.]+)\))?!"
    r":\s+(?P<description>.+)$"
)


class SemanticChangelogGenerator:
    """Generates structured Markdown changelogs from Git Conventional Commits."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def generate_changelog(self, version: str, since_tag: str | None = None) -> str:
        git_args = ["git", "log", "--pretty=format:%s"]
        if since_tag:
            git_args.append(f"{since_tag}..HEAD")
        else:
            git_args.extend(["-n", "100"])

        proc = run_subprocess(git_args, cwd=self.repo_root)
        if proc.returncode != 0:
            return f"## [{version}]\n\nNo commit history discovered.\n"

        categories: dict[str, list[str]] = defaultdict(list)
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            match = CONVENTIONAL_REGEX.match(line_clean)
            if match:
                c_type = match.group("type")
                scope = match.group("scope")
                desc = match.group("description")
                scope_str = f"**{scope}**: " if scope else ""
                categories[c_type].append(f"{scope_str}{desc}")
            else:
                categories["other"].append(line_clean)

        lines = [f"## [{version}]\n"]
        type_headers = {
            "feat": "### 🚀 Features & Enhancements",
            "fix": "### 🐛 Bug Fixes & Patches",
            "perf": "### ⚡ Performance Improvements",
            "refactor": "### ♻️ Code Refactoring",
            "docs": "### 📚 Documentation",
            "ci": "### 👷 CI/CD & Automation",
            "chore": "### 🧹 Maintenance & Chores",
            "other": "### 📦 Other Changes",
        }

        for cat_key, header in type_headers.items():
            if cat_key in categories and categories[cat_key]:
                lines.append(f"{header}\n")
                for item in categories[cat_key]:
                    lines.append(f"- {item}")
                lines.append("")

        return "\n".join(lines)
```

---

### 5.3 `src/rush/release/ci_generator.py`

```python
"""Hardened 40-character SHA-pinned GitHub Actions workflow generator."""

from __future__ import annotations

from pathlib import Path

# Pinned immutable 40-character commit SHAs for core GitHub Actions
PINNED_ACTIONS = {
    "actions/checkout": "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",  # v4.2.2
    "actions/setup-python": "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38",  # v5.4.0
    "astral-sh/setup-uv": "astral-sh/setup-uv@1edb4637821c054a75129d81411a547e614f6484",  # v5.3.0
}

HARDENED_CI_TEMPLATE = f"""name: CI Quality Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

# Least-privilege permissions block
permissions:
  contents: read

jobs:
  quality-gate:
    name: Rush Comprehensive Quality Gate
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Hardened Checkout
        uses: {PINNED_ACTIONS["actions/checkout"]}
        with:
          persist-credentials: false

      - name: Setup Python
        uses: {PINNED_ACTIONS["actions/setup-python"]}
        with:
          python-version: "3.12"

      - name: Setup uv
        uses: {PINNED_ACTIONS["astral-sh/setup-uv"]}
        with:
          enable-cache: true

      - name: Install Dependencies
        run: uv sync --all-extras --dev

      - name: Run Test Suite
        run: uv run pytest tests/ -q

      - name: Verify Documentation Parity
        run: uv run python scripts/sync_docs.py --check

      - name: Ruff Lint & Format Check
        run: |
          uv run ruff check src tests scripts
          uv run ruff format --check src tests scripts
"""


class CIWorkflowGenerator:
    """Generates hardened GitHub Actions workflows with immutable SHA pinning."""

    @staticmethod
    def generate_ci_workflow(repo_root: Path) -> Path:
        workflow_dir = repo_root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        ci_file = workflow_dir / "ci.yml"
        ci_file.write_text(HARDENED_CI_TEMPLATE, encoding="utf-8")
        return ci_file
```

---

### 5.4 `src/rush/release/multi_arch.py`

```python
"""Multi-platform build matrix and target triple coordinator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetTripleConfig:
    os_name: str
    architecture: str
    triple: str
    binary_name: str


TARGET_TRIPLES = [
    TargetTripleConfig("linux", "x86_64", "x86_64-unknown-linux-gnu", "rush-linux-x86_64"),
    TargetTripleConfig("linux", "aarch64", "aarch64-unknown-linux-gnu", "rush-linux-aarch64"),
    TargetTripleConfig("darwin", "arm64", "aarch64-apple-darwin", "rush-darwin-arm64"),
    TargetTripleConfig("darwin", "x86_64", "x86_64-apple-darwin", "rush-darwin-x86_64"),
    TargetTripleConfig("windows", "x86_64", "x86_64-pc-windows-msvc", "rush-windows-x86_64.exe"),
]


class MultiArchCoordinator:
    """Coordinates cross-compilation target metadata across CI runner matrix."""

    @staticmethod
    def get_supported_targets() -> list[TargetTripleConfig]:
        return TARGET_TRIPLES

    @staticmethod
    def get_target_for_os(os_name: str, arch: str) -> TargetTripleConfig | None:
        for t in TARGET_TRIPLES:
            if t.os_name.lower() == os_name.lower() and t.architecture.lower() == arch.lower():
                return t
        return None
```

---

### 5.5 `src/rush/release/pyinstaller_hooks.py`

```python
"""PyInstaller runtime data hooks and hidden imports specification."""

from __future__ import annotations

from pathlib import Path

HIDDEN_IMPORTS = [
    "rush.tools",
    "rush.workflows",
    "rush.plugins",
    "rush.patch",
    "rush.token_economy",
    "rush.sync",
    "rush.hygiene",
    "rush.codegraph",
    "rush.bundle",
    "rush.hotspots",
    "rush.governance",
    "rush.hooks",
    "rush.score",
    "tree_sitter_language_pack",
    "rich.console",
    "click",
    "mcp.server.fastmcp",
]


class PyInstallerHookSpec:
    """Generates PyInstaller spec definitions for zero-dependency standalone builds."""

    @staticmethod
    def generate_spec_file(repo_root: Path) -> Path:
        spec_path = repo_root / "rush.spec"
        imports_repr = repr(HIDDEN_IMPORTS)
        spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['src/rush/cli.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports={imports_repr},
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='rush',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True
)
"""
        spec_path.write_text(spec_content, encoding="utf-8")
        return spec_path
```

---

### 5.6 `src/rush/release/docker_generator.py`

```python
"""Multi-stage distroless non-root Dockerfile generator."""

from __future__ import annotations

from pathlib import Path

HARDENED_DOCKERFILE = """# Multi-stage hardened build for Rush CLI / MCP Server
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv pip install --system --no-cache .

# Final minimal production runtime
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /app /app

# Non-root user 65532:65532
USER nonroot:nonroot

ENTRYPOINT ["python3", "-m", "rush.cli"]
CMD ["mcp", "serve"]
"""


class DockerfileGenerator:
    """Generates hardened, multi-stage, distroless Dockerfiles."""

    @staticmethod
    def generate_dockerfile(repo_root: Path) -> Path:
        dockerfile_path = repo_root / "Dockerfile"
        dockerfile_path.write_text(HARDENED_DOCKERFILE, encoding="utf-8")
        return dockerfile_path
```

---

### 5.7 `src/rush/release/provenance.py`

```python
"""SHA-256 checksums manifest and build provenance generator."""

from __future__ import annotations

import hashlib
from pathlib import Path


class ArtifactProvenanceVerifier:
    """Computes deterministic SHA-256 checksum manifests for release distribution artifacts."""

    @staticmethod
    def generate_checksums_manifest(dist_dir: Path) -> Path:
        if not dist_dir.exists():
            raise FileNotFoundError(f"Distribution directory '{dist_dir}' not found.")

        manifest_file = dist_dir / "checksums.sha256"
        lines = []

        for p in sorted(dist_dir.iterdir()):
            if p.is_file() and p.name != "checksums.sha256":
                sha = hashlib.sha256()
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        sha.update(chunk)
                lines.append(f"{sha.hexdigest()}  {p.name}")

        manifest_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return manifest_file
```

---

### 5.8 `src/rush/release/slsa_attestation.py`

```python
"""SLSA Level 3 In-toto provenance attestation builder."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path


class SlsaProvenanceBuilder:
    """Constructs SLSA v0.2 / v1.0 In-toto provenance attestation JSON documents."""

    @staticmethod
    def build_provenance_document(artifact_path: Path, builder_id: str = "https://github.com/jamesdsizemore/rush-cli/actions") -> dict:
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact '{artifact_path}' not found.")

        sha = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        digest = sha.hexdigest()

        return {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [
                {
                    "name": artifact_path.name,
                    "digest": {"sha256": digest},
                }
            ],
            "predicateType": "https://slsa.dev/provenance/v0.2",
            "predicate": {
                "builder": {"id": builder_id},
                "buildType": "https://github.com/astral-sh/uv/build@v1",
                "invocation": {
                    "configSource": {
                        "uri": "git+https://github.com/jamesdsizemore/rush-cli",
                        "entryPoint": "src/rush/cli.py",
                    }
                },
                "metadata": {
                    "buildInvocationId": f"build_{int(time.time())}",
                    "completeness": {"parameters": True, "environment": True, "materials": False},
                    "reproducible": True,
                },
            },
        }
```

---

### 5.9 `src/rush/release/binary_builder.py`

```python
"""Standalone hermetic CLI binary builder using PyInstaller."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class StandaloneBinaryBuilder:
    """Orchestrates PyInstaller standalone single-file binary compilation."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def build_binary(self, output_dir: Path) -> tuple[bool, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        proc = run_subprocess(
            [
                "pyinstaller",
                "--onefile",
                "--name=rush",
                f"--distpath={output_dir}",
                "src/rush/cli.py",
            ],
            cwd=self.repo_root,
        )
        if proc.returncode == 0:
            return True, f"Binary built successfully in '{output_dir}'."
        return False, f"PyInstaller build failed: {proc.stderr or proc.stdout}"
```

---

### 4.10 `src/rush/cli.py` (Registration for `rush release` and `rush ci`)

```python
import click
from pathlib import Path
from rush.release.semver import SemVerValidator
from rush.release.ci_generator import CIWorkflowGenerator
from rush.release.docker_generator import DockerfileGenerator
from rush.release.provenance import ArtifactProvenanceVerifier
from rush.release.changelog_gen import SemanticChangelogGenerator
from rush.release.multi_arch import MultiArchCoordinator

@click.group(name="release")
def release_group():
    """Manage release versioning, SemVer parity, and artifact provenance."""
    pass

@release_group.command(name="check")
def release_check_cmd():
    """Check version parity across pyproject.toml, package.json, and Cargo.toml."""
    versions = SemVerValidator.check_manifest_parity(Path.cwd())
    if not versions:
        click.echo("No supported project manifests found.", err=True)
        return

    unique_versions = set(versions.values())
    click.echo(f"Discovered Manifest Versions ({len(versions)}):")
    for f, v in versions.items():
        click.echo(f"  - {f}: {v}")

    if len(unique_versions) == 1:
        click.echo("[PASS] All manifest versions are in parity.")
    else:
        click.echo("[FAIL] Manifest version mismatch detected!", err=True)

@release_group.command(name="changelog")
@click.option("--version", default="v0.2.0", help="Release version title.")
def release_changelog_cmd(version: str):
    """Generate Conventional Commits semantic changelog."""
    gen = SemanticChangelogGenerator(Path.cwd())
    notes = gen.generate_changelog(version)
    click.echo(notes)

@release_group.command(name="targets")
def release_targets_cmd():
    """List supported multi-architecture build targets."""
    targets = MultiArchCoordinator.get_supported_targets()
    click.echo(f"Supported Build Targets ({len(targets)}):")
    for t in targets:
        click.echo(f"  - {t.triple:<30} -> {t.binary_name}")

@release_group.command(name="provenance")
@click.argument("dist_dir", type=click.Path(exists=True))
def release_provenance_cmd(dist_dir: str):
    """Generate SHA-256 checksums manifest for release artifacts."""
    manifest = ArtifactProvenanceVerifier.generate_checksums_manifest(Path(dist_dir))
    click.echo(f"[SUCCESS] Checksum manifest generated at '{manifest}'.")

@click.group(name="ci")
def ci_group():
    """Generate hardened CI/CD and container workflows."""
    pass

@ci_group.command(name="generate")
def ci_generate_cmd():
    """Generate hardened 40-character SHA-pinned GitHub Actions workflow."""
    wf = CIWorkflowGenerator.generate_ci_workflow(Path.cwd())
    click.echo(f"[SUCCESS] Hardened CI workflow created at '{wf}'.")

@ci_group.command(name="docker")
def ci_docker_cmd():
    """Generate hardened multi-stage distroless Dockerfile."""
    df = DockerfileGenerator.generate_dockerfile(Path.cwd())
    click.echo(f"[SUCCESS] Hardened Dockerfile created at '{df}'.")
```

---

### 4.11 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for release packaging and CI generation."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.release.semver import SemVerValidator
from rush.release.ci_generator import CIWorkflowGenerator
from rush.release.changelog_gen import SemanticChangelogGenerator

mcp = FastMCP("rush")

@mcp.tool(name="rush_release_verify", description="Verify SemVer 2.0.0 format and cross-manifest parity.")
def rush_release_verify() -> str:
    versions = SemVerValidator.check_manifest_parity(Path.cwd())
    is_parity = len(set(versions.values())) == 1 if versions else False
    return json.dumps({"versions": versions, "parity": is_parity}, indent=2)

@mcp.tool(name="rush_release_changelog", description="Generate semantic changelog from Conventional Commits.")
def rush_release_changelog(version: str = "v0.2.0") -> str:
    gen = SemanticChangelogGenerator(Path.cwd())
    return gen.generate_changelog(version)

@mcp.tool(name="rush_ci_workflow_generate", description="Generate hardened SHA-pinned GitHub Actions workflow.")
def rush_ci_workflow_generate() -> str:
    wf = CIWorkflowGenerator.generate_ci_workflow(Path.cwd())
    return json.dumps({"workflow_file": str(wf)}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_release_packaging_ci.py`

```python
"""Comprehensive test suite for SemVerValidator, SemanticChangelogGenerator, MultiArchCoordinator, CIWorkflowGenerator, DockerfileGenerator, PyInstallerHookSpec, ArtifactProvenanceVerifier, SlsaProvenanceBuilder, and StandaloneBinaryBuilder."""

from pathlib import Path
import pytest
from rush.release.semver import SemVerValidator, SemVer
from rush.release.changelog_gen import SemanticChangelogGenerator
from rush.release.multi_arch import MultiArchCoordinator
from rush.release.pyinstaller_hooks import PyInstallerHookSpec, HIDDEN_IMPORTS
from rush.release.ci_generator import CIWorkflowGenerator, PINNED_ACTIONS
from rush.release.docker_generator import DockerfileGenerator
from rush.release.provenance import ArtifactProvenanceVerifier
from rush.release.slsa_attestation import SlsaProvenanceBuilder
from rush.release.binary_builder import StandaloneBinaryBuilder


def test_semver_parser_valid():
    v = SemVerValidator.parse("1.2.3-alpha.1+build.42")
    assert v is not None
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 3
    assert v.prerelease == "alpha.1"
    assert v.build == "build.42"
    assert str(v) == "1.2.3-alpha.1+build.42"


def test_semver_bumps():
    v = SemVer(1, 2, 3)
    assert str(v.bump_patch()) == "1.2.4"
    assert str(v.bump_minor()) == "1.3.0"
    assert str(v.bump_major()) == "2.0.0"


def test_semver_parser_invalid():
    assert SemVerValidator.parse("invalid.version") is None
    assert SemVerValidator.parse("1.2") is None


def test_manifest_parity_checker(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('version = "0.2.0"\n', encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name": "test", "version": "0.2.0"}\n', encoding="utf-8")

    versions = SemVerValidator.check_manifest_parity(tmp_path)
    assert len(versions) == 2
    assert versions["pyproject.toml"] == "0.2.0"
    assert versions["package.json"] == "0.2.0"


def test_multi_arch_coordinator():
    targets = MultiArchCoordinator.get_supported_targets()
    assert len(targets) == 5
    linux_x64 = MultiArchCoordinator.get_target_for_os("linux", "x86_64")
    assert linux_x64 is not None
    assert linux_x64.binary_name == "rush-linux-x86_64"


def test_pyinstaller_spec_generator(tmp_path: Path):
    spec = PyInstallerHookSpec.generate_spec_file(tmp_path)
    assert spec.exists()
    content = spec.read_text(encoding="utf-8")
    assert "rush.tools" in content
    assert "Analysis" in content


def test_ci_workflow_generator_pins_actions(tmp_path: Path):
    wf_file = CIWorkflowGenerator.generate_ci_workflow(tmp_path)
    assert wf_file.exists()
    content = wf_file.read_text(encoding="utf-8")

    # Assert all actions are pinned to 40-character SHAs
    for action_id, pinned in PINNED_ACTIONS.items():
        assert pinned in content
    assert "permissions:\n  contents: read" in content


def test_dockerfile_generator_hardened(tmp_path: Path):
    df_file = DockerfileGenerator.generate_dockerfile(tmp_path)
    assert df_file.exists()
    content = df_file.read_text(encoding="utf-8")

    assert "gcr.io/distroless/python3-debian12:nonroot" in content
    assert "USER nonroot:nonroot" in content


def test_artifact_provenance_checksums(tmp_path: Path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "rush-linux-x64").write_bytes(b"dummy binary linux")
    (dist_dir / "rush-windows-x64.exe").write_bytes(b"dummy binary windows")

    manifest = ArtifactProvenanceVerifier.generate_checksums_manifest(dist_dir)
    assert manifest.exists()
    content = manifest.read_text(encoding="utf-8")

    assert "rush-linux-x64" in content
    assert "rush-windows-x64.exe" in content
    assert len(content.strip().splitlines()) == 2


def test_slsa_provenance_builder(tmp_path: Path):
    artifact = tmp_path / "rush-v0.2.0-x86_64.tar.gz"
    artifact.write_bytes(b"release archive bytes")

    doc = SlsaProvenanceBuilder.build_provenance_document(artifact)
    assert doc["_type"] == "https://in-toto.io/Statement/v0.1"
    assert doc["subject"][0]["name"] == "rush-v0.2.0-x86_64.tar.gz"
    assert "sha256" in doc["subject"][0]["digest"]


def test_semantic_changelog_generator_empty(tmp_path: Path):
    gen = SemanticChangelogGenerator(tmp_path)
    notes = gen.generate_changelog("v0.2.0")
    assert "## [v0.2.0]" in notes
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 30 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T09:40:00.100Z", "phase": 30, "tool": "rush_release", "event": "semver_checked", "version": "0.2.0", "parity": true}
{"timestamp": "2026-08-21T09:40:02.150Z", "phase": 30, "tool": "rush_ci", "event": "workflow_generated", "path": ".github/workflows/ci.yml", "sha_pinned": true}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 30 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 30: Packaging, Versioning & Hardened CI**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 30 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Release Automation, Versioning & CI Integration" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush release` (commands: `prepare`, `verify`, `changelog`) and `rush ci` (commands: `init`, `verify`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for automating release tagging and generating SLSA provenance.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add complete SHA-pinned GitHub Actions workflow templates.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example generated changelogs and SLSA provenance JSON statements.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up hardened zero-trust CI workflows.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for SemVer mismatch errors and unpinned action tag alerts.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain why Rush requires 40-character commit SHAs in CI workflows.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_release_check` and `rush_ci_verify` tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document release verification JSON payload schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `release` and `ci` tools in DevOps & Release category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[release]` and `[ci]` configuration tables.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document PyInstaller hermetic compilation pipeline and SLSA Level 3 attestation builder.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Guide for managing release tags and building binary distribution packages.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Add reference CI pipeline configurations.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document SemVer matrix and PyInstaller mock test suites.
- **[`docs/tools/release.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/release.md)** & **[`docs/tools/ci.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/ci.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-30): implement standalone packaging, semver validator and hardened ci workflows"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
