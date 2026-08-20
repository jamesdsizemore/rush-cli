# Developer Testing Guide & Test Architecture

This guide explains the 9 testing layers that maintain the 100% deterministic test pass rate across all 34 tools and 77 engines in Rush CLI.

---

## 1. The 9 Testing Layers

```text
Layer 1: Unit Contracts (Finding normalization, fingerprint hashing, secret redaction)
Layer 2: Parser Fixtures (tests/fixtures/engine_reports/ for all 77 engines)
Layer 3: Subprocess Invocation Tests (Mocked run_subprocess proving argv and timeout)
Layer 4: Routing & Aggregation Tests (Language marker detection and status precedence)
Layer 5: CLI Registry Tests (Click argument parsing, JSON emission, exit codes)
Layer 6: FastMCP Server Tests (stdio JSON-RPC transport and schema validity)
Layer 7: Execution Permission Tests (Flag enforcement for network, slow, browser, build)
Layer 8: Documentation Parity & Sync Tests (Link verification across 128 markdown files)
Layer 9: Packaging & Clean Distribution Tests (Wheel and sdist installation smoke tests)
```

---

## 2. Running Test Suites

```bash
# Run all tests quickly (mock-isolated, ~10s)
.venv/Scripts/python.exe -m pytest tests/ -q

# Run specific test category
.venv/Scripts/python.exe -m pytest tests/test_docs_parity_and_sync.py
.venv/Scripts/python.exe -m pytest tests/test_mcp.py
.venv/Scripts/python.exe -m pytest tests/test_permissions.py

# Verify code formatting and linting
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
```

---

## 3. Fixture-First Contract Requirements

- Never introduce a new engine adapter without corresponding `clean.json`, `findings.json`, and `malformed.json` test fixtures in `tests/fixtures/engine_reports/<engine>/`.
- Register the fixture suite in `src/rush/catalog.py` under `PARSER_FIXTURE_SUITES`.
- Run `pytest tests/test_phase01_truth_audit.py` to ensure fixture registration parity.

See [Testing Reference](../TESTING.md) and [Tool Development Guide](tool-development.md).
