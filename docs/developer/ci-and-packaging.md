# Contributor CI, Packaging & Build Engineering

This guide details the continuous integration workflow, package build procedures, and clean distribution validation tests for contributors and maintainers.

---

## 1. Local Pre-Push CI Simulation

Before pushing commits or opening pull requests, execute the exact validation loop run by GitHub Actions CI:

```bash
# 1. Clear foreign virtualenv contamination
unset VIRTUAL_ENV PYTHONPATH

# 2. Synchronize exact pinned dependencies
uv sync --all-extras --frozen

# 3. Run all pytest test suites (986+ tests including contract suites, 100% pass rate required)
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Verify benchmark harness execution across all 40 scenarios
.venv/Scripts/python.exe -m scripts.benchmarks.run --all --output research/benchmark/B1

# 5. Verify documentation parity & internal cross-links
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 6. Run Ruff linter and formatter
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 7. Check Graft knowledge graph sync
graft --dir .hermes/graft check .
```

---

## 2. GitHub Actions CI Matrix (`.github/workflows/ci.yml`)

The repository CI workflow runs across Ubuntu, macOS, and Windows runners:
1. **Lint & Formatting**: `ruff check` and `ruff format --check`.
2. **Doc Parity & Links**: `python scripts/sync_docs.py --check`.
3. **Unit & Engine Reference Tests**: `pytest tests/ -q`.
4. **Vulnerability Audit**: `pip-audit`.
5. **Distribution Build**: `uv build`.
6. **Isolated Artifact Probes (Finding R-001 Closed)**: Matrix job across `ubuntu-latest` and `windows-latest` executing `scripts/probe_installed_artifacts.py` in scrubbed virtual environments.

---

## 3. Clean Wheel & Sdist Validation Protocol

Validate distribution packages in an isolated, clean Python environment:

```bash
# Build artifacts
uv build

# Create clean virtual environment
uv venv .clean_test_env
uv pip install --python .clean_test_env/Scripts/python.exe dist/rush_cli-0.3.0-py3-none-any.whl

# Validate CLI execution in clean environment
.clean_test_env/Scripts/rush.exe --version
.clean_test_env/Scripts/rush.exe --help
.clean_test_env/Scripts/rush.exe review src/

# Validate FastMCP server startup
.clean_test_env/Scripts/python.exe -c "
import subprocess, sys
p = subprocess.Popen(['.clean_test_env/Scripts/rush.exe', 'mcp', 'serve'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
p.stdin.close()
p.wait(timeout=5)
print('MCP smoke test exit code:', p.returncode)
"
```

---

## 4. Pytest Collection Isolation & Package Identity (Phase 52)

- **Strict Pythonpath Isolation**: `pyproject.toml` configures `pythonpath = ["src"]` without exposing repository root `.`. This prevents root directory leakage into module import paths during local test execution.
- **Canonical Imports**: Every internal module must import `rush` (never `src.rush`). This invariant is enforced continuously by `tests/test_phase52_package_identity.py`.
- **Version Contract**: `src/rush/__init__.py` derives `__version__` dynamically from `importlib.metadata.version("rush-cli")`, verified by `tests/test_phase52_version_contract.py`.

See [Distribution Guide](../DISTRIBUTION.md) and [Release Process](release-process.md).
### Hardened CI & Engine Conformance (Phase 59)
CI workflows provision pinned engine environments and enforce mandatory non-skipped `mypy` typechecks.
