# Phase 30 Implementation Plan: Standalone Packaging, Versioning & CI

> **Phase:** 30 of 30  
> **Milestone:** Multi-Platform Distribution, Semantic Versioning & Enterprise CI/CD  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.3.0 → v1.0.0  
> **ADR Reference:** [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)

---

## 1. Objective & Scope

Package Rush into zero-prerequisite standalone binaries for macOS, Linux, and Windows, establish automated semantic release management, package manager formulas (Homebrew, Winget, Scoop), and configure enterprise-grade GitHub Actions workflows.

Incorporate **Supply Chain Attestation & SHA Pinning** to pin all GitHub Actions to immutable 40-character commit hashes and generate SHA-256 checksums and SLSA Level 3 provenance for all compiled release binaries.

---

## 2. File Rosters

### Allowed & Target Files
- `packaging/homebrew/rush.rb` (New: Homebrew formula)
- `packaging/winget/rush.yaml` (New: Winget manifest)
- `packaging/scoop/rush.json` (New: Scoop manifest)
- `.github/workflows/release.yml` (New: Multi-platform binary compilation and release pipeline)
- `.github/workflows/quality.yml` (Modified: Enterprise matrix testing across Linux, macOS, Windows)
- `pyproject.toml` (Modified: Version bump and build metadata)
- `src/rush/logging.py` (Modified: `[rush-release:LEVEL]`)

### Test & Fixture Files
- `tests/test_packaging_and_versioning.py` (New: Version parity and action pinning tests)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_packaging_and_versioning.py`:
1. `test_version_parity_across_codebase()`: Asserts version string in `pyproject.toml`, `src/rush/__init__.py`, and CLI output match exactly.
2. `test_github_action_sha_pinning()`: Asserts that all `uses:` directives in `.github/workflows/*.yml` use 40-character commit hashes rather than mutable tags.
3. `test_package_manifest_urls()`: Asserts that package manifest URLs follow canonical release patterns.

### 3.2 GREEN Phase
Create packaging manifests, author `.github/workflows/release.yml`, update `quality.yml`.

### 3.3 REFACTOR Phase
Ensure standalone binary builds execute with zero external Python dependencies required.

---

## 4. Step-by-Step Implementation Tasks

### Task 30.1: Package Manager Manifests
Author manifests for:
- Homebrew: `packaging/homebrew/rush.rb`
- Winget: `packaging/winget/rush.yaml`
- Scoop: `packaging/scoop/rush.json`

### Task 30.2: Multi-Platform Release Pipeline (`.github/workflows/release.yml`)
Configure PyInstaller/Nuitka matrix compilation:
- `ubuntu-latest` -> `rush-linux-x86_64`
- `macos-latest` -> `rush-darwin-arm64` & `rush-darwin-x86_64`
- `windows-latest` -> `rush-windows-x86_64.exe`

### Task 30.3: Enterprise CI/CD Hardening (`.github/workflows/quality.yml`)
Enforce multi-OS matrix validation:
- Python 3.12 on Linux, macOS, Windows
- Full pytest test suite execution
- Whole-tree documentation parity check (`python scripts/sync_docs.py --check`)
- Ruff linter and formatter verification

### Task 30.4: Stderr Diagnostics & Logging
- `[rush-release:INFO] Validating release version {version}`
- `[rush-release:INFO] Compiling standalone distribution binaries`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/INSTALLATION.md` & `docs/GETTING_STARTED.md` (Add standalone binary installation instructions).
2. `docs/CI_CD_GUIDE.md` & `docs/maintainers/release-process.md` (Release procedure and manifest publishing).
3. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run packaging and version parity unit tests
.venv/Scripts/python.exe -m pytest tests/test_packaging_and_versioning.py -v

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
