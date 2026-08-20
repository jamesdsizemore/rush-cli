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
   - Update version in `pyproject.toml` and `src/rush/__init__.py`.
   - Update `CHANGELOG.md` with new features, fixes, and engine additions.

3. **Build Wheel & Source Distribution**:
   ```bash
   uv build
   ```

4. **Smoke-Test Clean Distribution**:
   - Install the built `.whl` into a temporary clean virtual environment.
   - Run `rush --version`, `rush --help`, `rush review src/`, and `rush mcp serve`.

5. **Publish to Package Registry**:
   - Publishing is executed through trusted CI pipelines using PyPI Trusted Publishing.

See [Release Process Guide](developer/release-process.md) and [Versioning Policy](maintainers/versioning-and-compatibility.md).
