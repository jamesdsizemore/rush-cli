# Contributor CI, Packaging & Build Engineering

This guide details the continuous integration workflow, package build procedures, and clean distribution validation tests for contributors and maintainers.

---

## 1. Local Pre-Push CI Simulation

Before an authorized push, run the locked Python 3.12 gates below. Explicit empty
marker selection includes slow tests. Source typechecking uses `src/rush`.

```bash
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python --version
rtk proxy env -u PYTHONPATH TERM=xterm-256color uv run --frozen --no-sync --python 3.12 --extra dev env -u NO_COLOR python -m pytest tests/ -q -m ""
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python scripts/sync_docs.py --check
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev ruff check src tests scripts
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev ruff format --check src tests scripts
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev mypy src/rush
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev pip-audit
rtk git diff --check
rtk proxy uv build --python 3.12
```

---

## 2. GitHub Actions CI Matrix (`.github/workflows/ci.yml`)

The quality job runs on Ubuntu; installed-artifact probes and Windows runtime
contracts execute on their respective CI runners. Phase 70 uses these existing
Linux/Windows lanes and local macOS checks. Record each run's actual revision,
URL and conclusion; an older run does not accept new source.
Existing Linux quality and Windows contracts jobs also execute installed TUI
journeys against their built native archive. `RUSH_G8_NATIVE_ARCHIVE`,
`RUSH_G8_NATIVE_SUMS` and `RUSH_G8_NATIVE_RECEIPT_DIR` bind archive, checksum
manifest and observation directory. Tests assert actual terminal/console
behavior; the job additionally requires valid `posix-installed-tui.json` or
`windows-installed-tui.json` so omitted native collection fails. Source PTY,
reader tests and receipt presence alone do not prove native acceptance.
Linux sets `TERM=xterm-256color` and clears inherited `PYTHONPATH` and `NO_COLOR`
inside the command after `uv run`. Windows preserves pytest's `$LASTEXITCODE`
before checking its receipt. Both jobs print parsed observation JSON with the
`RUSH_G8_NATIVE_RECEIPT=` prefix for CI logs; no receipt artifact upload is
configured. Static workflow review does not establish an executed CI result.
Extended POSIX native assertions include real scan grants/cancellation,
configuration failure/recovery, literal paste, color/motion and idle interrupt
alongside three viewport sizes and section/action observations. Source passes
and collection alone do not establish those installed-binary outcomes; execute
the rebuilt archive in the existing job or local macOS lane before acceptance.
Native journey tests require owned process groups to disappear after normal
quit and idle interrupt before their safety cleanup runs. Real orphan cleanup
regressions exercise harness cleanup separately; they do not prove installed
Rush exited cleanly. Keep final native observations distinct from source/helper
passes and inspect each actual action, grant, cancellation and recovery result.

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
CI invokes `uv run mypy src/rush`; development dependencies pin `mypy==2.3.1`
in `pyproject.toml` and `uv.lock`. Test helpers that launch ordinary children
must import without POSIX terminal modules on Windows. Import `pty` only inside
the PTY helper; use the existing `spawn_child` helper for independent child
processes when background threads may already exist.

## 5. Native Dashboard Assets

Native PyInstaller builds must include all three data collections:

```text
--collect-data license_expression --collect-data rush.integrations --collect-data rush.dashboard --collect-submodules tiktoken_ext
```

Keep these flags aligned in `.github/workflows/ci.yml`,
`.github/workflows/release.yml` and `tests/conftest.py`. The dashboard collection
includes `application.js` and `project_map.js`; Python imports and MCP startup
alone cannot verify that these browser modules reached the native archive.

The existing native probe in `tests/test_phase52_installed_artifacts.py`
extracts the checksummed archive, starts `dashboard --port 0 --no-open --json`
from an arbitrary directory with isolated HOME and no Python or uv on PATH,
then requires HTTP 200 and exact source bytes from `/assets/application.js`
and `/assets/project_map.js`. It keeps the private bootstrap URL out of logs
and stops the dashboard process afterward. Run this probe against the rebuilt
archive alongside `scripts/probe_installed_artifacts.py`; wheel or source
checks do not verify native asset packaging.

Native Memory expansion also requires the dynamically discovered
`tiktoken_ext` plugin. Its acceptance walkthrough uses an existing, verified
`cl100k_base` BPE cache; verify cached bytes against SHA-256
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.
This proves expansion under that cache condition, not offline operation with
an empty cache. Do not let acceptance fixtures fetch tokenizer data without
explicit network authorization.
