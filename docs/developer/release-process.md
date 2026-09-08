# Contributor Release Process & Verification Protocol

This runbook defines the exact multi-step procedure for validating, building, tagging, and releasing a new version of Rush CLI.

---

## 1. Pre-Release Verification Loop

Before cutting any release candidate:

```bash
# 1. Clear foreign virtualenv contamination
unset VIRTUAL_ENV PYTHONPATH

# 2. Run the complete pytest test suite; every collected test must pass
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Verify recursive documentation parity, hashes, links and runtime contracts
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Check linter and formatter
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Check Graft knowledge graph
graft check .
```

---

## 2. Version Bump & Changelog

1. Update version in `pyproject.toml` to the intended release version.
2. Confirm `src/rush/__init__.py` still derives installed version from `importlib.metadata.version("rush-cli")`; update only its development fallback when the project version changes.
3. Document all new features, engine additions, and bug fixes in `CHANGELOG.md`.

---

## 3. Package Build & Clean Artifact Testing

```bash
# Build wheel and sdist
uv build

# Test clean wheel installation in temporary environment
uv venv .release_test_env
uv pip install --python .release_test_env/Scripts/python.exe dist/*.whl

# Verify CLI commands
.release_test_env/Scripts/rush.exe --version
.release_test_env/Scripts/rush.exe review src/
.release_test_env/Scripts/rush.exe lint src/
```

Commands above use Windows executable paths. On macOS/Linux use `.release_test_env/bin/python` and `.release_test_env/bin/rush`.

---

## 4. Git Tagging & Publishing

1. Commit changes: `git commit -m "chore(release): bump version to 0.2.0"`
2. Tag release: `git tag -a v0.2.0 -m "Release v0.2.0"`
3. Push to remote and let GitHub Actions CI perform PyPI Trusted Publishing.

See [Distribution Guide](../DISTRIBUTION.md) and [Versioning Policy](../maintainers/versioning-and-compatibility.md).
