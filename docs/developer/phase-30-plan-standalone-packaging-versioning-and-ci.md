# Phase 30 Implementation Plan: Standalone Packaging, Versioning & CI

> **Phase:** 30 of 40  
> **Milestone:** Multi-Platform Distribution, Semantic Versioning & Enterprise CI/CD  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.3.0  
> **ADR References:** [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Users and autonomous agents operating in production environments require Rush as zero-prerequisite standalone binaries without needing a global Python 3.12 installation. Phase 30 packages Rush into single-binary executables for macOS (arm64/x86_64), Linux (glibc/musl), and Windows (x86_64), establishes automated semantic release pipelines, author package manager formulas (Homebrew, Winget, Scoop), and configures enterprise GitHub Actions workflows.

All GitHub Action workflows are pinned to immutable 40-character commit hashes, and compiled release binaries include SHA-256 checksums and SLSA Level 3 provenance attestations.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Zero-Prerequisite Binary Execution)**: Standalone single-binary binaries boot in <10ms and execute quality checks with zero Python virtualenv setup overhead.
- **`graft` (CI Matrix AST Verification)**: CI pipelines run `tree-sitter` syntax checks before compiling binaries.
- **`context-mode` (Compact Release Metadata)**: Package manifests and version outputs (`rush --version`) return concise single-line strings.

---

## 3. File Rosters

### Target Implementation Files
- `packaging/homebrew/rush.rb` (New: Homebrew formula)
- `packaging/winget/rush.yaml` (New: Winget manifest)
- `packaging/scoop/rush.json` (New: Scoop manifest)
- `.github/workflows/release.yml` (New: Multi-platform binary compilation and release pipeline)
- `.github/workflows/quality.yml` (Modified: Enterprise matrix testing across Linux, macOS, Windows)
- `pyproject.toml` (Modified: Release versioning and build metadata)
- `src/rush/cli.py` (Modified: Version reflection and diagnostic build info in `rush --version`)

### Test & Fixture Files
- `tests/test_packaging_and_versioning.py` (New: Version parity and action SHA pinning tests)
- `tests/fixtures/packaging/` (New: Mock formula manifests)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_packaging_and_versioning.py
def test_version_parity_across_codebase():
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")
    init_text = Path("src/rush/__init__.py").read_text(encoding="utf-8")
    
    # Extract version strings
    v_pyproject = re.search(r'version\s*=\s*"([^"]+)"', pyproject_text).group(1)
    v_init = re.search(r'__version__\s*=\s*"([^"]+)"', init_text).group(1)
    assert v_pyproject == v_init

def test_github_action_sha_pinning():
    workflows = list(Path(".github/workflows").glob("*.yml"))
    for wf in workflows:
        content = wf.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "uses:" in line and not line.strip().startswith("#"):
                action_ref = line.split("uses:")[1].strip()
                if "@" in action_ref:
                    ref_part = action_ref.split("@")[1]
                    assert len(ref_part) == 40, f"Action {action_ref} in {wf.name} not pinned to 40-char SHA"
```

### 4.2 GREEN Phase (Implementation)
Create packaging manifests, author `.github/workflows/release.yml`, update `quality.yml`.

### 4.3 REFACTOR Phase
Ensure standalone binary builds execute with zero external Python runtime dependencies required.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T08:00:00Z", "phase": 30, "tool": "rush_release", "event": "version_verified", "version": "0.3.0", "commit": "3c93747"}
{"timestamp": "2026-08-21T08:00:01Z", "phase": 30, "tool": "rush_release", "event": "binary_compiled", "target": "rush-linux-x86_64", "size_bytes": 18450112}
{"timestamp": "2026-08-21T08:00:02Z", "phase": 30, "tool": "rush_release", "event": "sha256_generated", "file": "rush-linux-x86_64", "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
```

---

## 6. Step-by-Step Task Specifications

### Task 30.1: Package Manager Manifests
Author manifests for:
- Homebrew: `packaging/homebrew/rush.rb`
- Winget: `packaging/winget/rush.yaml`
- Scoop: `packaging/scoop/rush.json`

### Task 30.2: Multi-Platform PyInstaller Release Pipeline (`.github/workflows/release.yml`)
Configure GitHub Actions matrix build for:
- Linux (`rush-linux-x86_64`)
- macOS ARM64 (`rush-darwin-arm64`)
- macOS Intel (`rush-darwin-x86_64`)
- Windows (`rush-windows-x86_64.exe`)

### Task 30.3: Enterprise CI/CD Hardening (`.github/workflows/quality.yml`)
Enforce multi-OS matrix validation, 40-character SHA pinning, doc parity verification, and pytest execution.

### Task 30.4: CLI Build Information (`src/rush/cli.py`)
Add build commit and platform architecture info to `rush --version`.

---

## 7. Semantic Drift Review & Verification Gate

1. **SHA Pinning Invariant**: 100% of GitHub Actions must be pinned to 40-character commit hashes.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
