# Release Management & Publishing Operations

This document defines the release workflow, semantic versioning rules, and pre-publish validation steps for Rush CLI.

---

## 1. Safety Boundary for Releases

- **No Implicit Tags or Push**: Rush never automatically writes Git tags or executes `git push` without explicit user control.
- **Dry-Run by Default**: Current `rush release` is a group exposing `release check` for version parity. Catalog/MCP release inspection is a separate registration; this CLI does not calculate a release plan.
- **Cryptographic Attestations**: Releases integrate with Cosign and SLSA Verifier (Phase 11/19) to verify supply chain signatures.

---

## 2. Release Steps

1. **Verify All Test Suites & Linters**:
   ```bash
   unset VIRTUAL_ENV PYTHONPATH
   uv run --python 3.12 --extra dev python -m pytest tests/ -q
   uv run --python 3.12 --extra dev python scripts/sync_docs.py --check
   uv run --python 3.12 --extra dev ruff check src tests scripts
   uv run --python 3.12 --extra dev ruff format --check src tests scripts
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

1. Inspect `rush ship clean --dry-run`; current default deletion is unsafe for user-owned scratch files (F02). Permission-gated, ownership-checked apply remains planned in P64-02.
2. Run `rush ship env` to verify environment variable parity.
3. Run `rush ship migration` to verify database DDL locks.
4. Run `rush ship semver OLD_FILE NEW_FILE` and inspect the static signature differences.
5. Run `rush ship pack` to ensure zero secret leaks in distributions.
6. Run `rush ship gate` for final 7-vector release readiness authorization.
### Pre-Release Verification (Phase 59)
Release readiness requires passing the current required tests, Ruff and installed-artifact checks. The old 1,189-test count is historical. CI currently invokes undeclared `mypy` and has ordering/portability failures; repair remains planned in [P64-20](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). Archive/checksum and clean-machine installation work remains planned in [P65-01](phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md). No release readiness is established by this document.
