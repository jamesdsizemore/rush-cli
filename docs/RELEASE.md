# Release Management & Publishing Operations

This document defines the release workflow, semantic versioning rules, and pre-publish validation steps for Rush CLI.

---

## 1. Safety Boundary for Releases

- **No Implicit Tags or Push**: Rush never automatically writes Git tags or executes `git push` without explicit user control.
- **Dry-Run by Default**: The `rush release` command operates in dry-run mode, calculating the next semantic version, verifying artifact inventory, and inspecting provenance attestations.
- **Cryptographic Attestations**: Releases integrate with Cosign and SLSA Verifier (Phase 11/19) to verify supply chain signatures.

---

## 2. Release Steps

1. **Verify All Test Suites & Linters**:
   ```bash
   unset VIRTUAL_ENV PYTHONPATH
   .venv/Scripts/python.exe -m pytest tests/ -q
   .venv/Scripts/python.exe scripts/sync_docs.py --check
   .venv/Scripts/ruff.exe check src tests scripts
   .venv/Scripts/ruff.exe format --check src tests scripts
   graft --dir .hermes/graft check .
   ```

2. **Update Version & Changelog**:
   - Update version in `pyproject.toml` (single source of truth; `src/rush/__init__.py` resolves it from distribution metadata).
   - Update `CHANGELOG.md` with new features, fixes, and engine additions.

3. **Build Wheel & Source Distribution**:
   ```bash
   uv build
   ```

4. **Verify Artifact Probes in Isolated Environments (Phase 51 & 52 Gate)**:
   - Run the automated probe harness against built distributions:
     ```bash
     python scripts/probe_installed_artifacts.py --dist-dir dist
     ```
   - Confirms wheel and sdist installation, origin isolation, and clean CLI execution from an external CWD with scrubbed `PYTHONPATH`.

5. **Publish to Package Registry**:
   - Publishing is executed through trusted CI pipelines using PyPI Trusted Publishing.

See [Release Process Guide](developer/release-process.md) and [Versioning Policy](maintainers/versioning-and-compatibility.md).

## Release Checklist with Ship Cockpit (Phases 41–43)

1. Run `rush ship clean` to remove scratch directories and build debris.
2. Run `rush ship env` to verify environment variable parity.
3. Run `rush ship migration` to verify database DDL locks.
4. Run `rush ship semver` to ensure no accidental breaking public API changes.
5. Run `rush ship pack` to ensure zero secret leaks in distributions.
6. Run `rush ship gate` for final 7-vector release readiness authorization.
### Pre-Release Verification (Phase 59)
Release readiness requires passing all 1,189 tests, zero ruff errors, clean wheel/sdist probes, non-skipped `mypy` release gate, and truthful provenance draft generation.
