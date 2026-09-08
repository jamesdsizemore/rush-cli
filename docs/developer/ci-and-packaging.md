# Contributor CI, Packaging & Build Engineering

This guide details the continuous integration workflow, package build procedures, and clean distribution validation tests for contributors and maintainers.

---

## 1. Local Pre-Push CI Simulation

Before pushing commits or opening pull requests, execute the currently provisioned local gates below. CI also invokes the pending `mypy` gate described in §4.

```bash
# 1. Clear foreign virtualenv contamination
unset VIRTUAL_ENV PYTHONPATH

# 2. Synchronize exact pinned dependencies
uv sync --all-extras --frozen

# 3. Run all pytest test suites; every collected test must pass
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Verify documentation parity & internal cross-links
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 5. Run Ruff linter and formatter
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 6. Run dependency audit and whitespace check
uv run pip-audit
git diff --check

# 7. Build wheel and sdist
uv build
```

---

## 2. GitHub Actions CI Matrix (`.github/workflows/ci.yml`)

The quality job runs on Ubuntu; installed-artifact probes run on Ubuntu and Windows:
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
uv pip install --python .clean_test_env/Scripts/python.exe dist/*.whl

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

Commands above use Windows executable paths. On macOS/Linux use `.clean_test_env/bin/python` and `.clean_test_env/bin/rush`.

## 4. Pytest Collection Isolation & Package Identity (Phase 52)

- **Strict Pythonpath Isolation**: `pyproject.toml` configures `pythonpath = ["src"]` without exposing repository root `.`. This prevents root directory leakage into module import paths during local test execution.
- **Canonical Imports**: Every internal module must import `rush` (never `src.rush`). This invariant is enforced continuously by `tests/test_phase52_package_identity.py`.
- **Version Contract**: `src/rush/__init__.py` derives `__version__` dynamically from `importlib.metadata.version("rush-cli")`, verified by `tests/test_phase52_version_contract.py`.

See [Distribution Guide](../DISTRIBUTION.md) and [Release Process](release-process.md).
### Hardened CI & Engine Conformance (Phase 59)
CI invokes `uv run mypy src/rush`, but `mypy` is not yet declared in `pyproject.toml` or `uv.lock`. Status: planned — implementation [P64-20](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-20-repair-baseline-test-packaging-and-ci-gates-f27-f29) adds the locked dependency before this gate can count as provisioned typecheck evidence.
