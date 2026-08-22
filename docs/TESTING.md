# Testing Architecture & Verification Protocols

Rush uses a multi-layered testing strategy combining deterministic parser fixtures, mock subprocess isolation, and end-to-end transport verification.

---

## 1. Test Suite Architecture

```text
tests/
├── fixtures/
│   └── engine_reports/         # Deterministic fixture outputs (clean, findings, malformed)
├── test_*_reference.py         # Dedicated reference test suites for all 121 engines
├── test_docs_parity_and_sync.py # Zero-drift documentation and link validation suite
├── test_phase01_truth_audit.py # Truth audit verifying PARSER_FIXTURE_SUITES registration
├── test_mcp.py                 # FastMCP stdio transport and schema validation
├── test_permissions.py         # Execution permission flag boundary tests
└── test_executed_modes.py      # Dual-mode execution vs. report import tests
```

---

## 2. Running Test Suites

```bash
# Run all tests (deterministic, mock-isolated, fast)
.venv/Scripts/python.exe -m pytest tests/ -q

# Run specific engine reference test suite
.venv/Scripts/python.exe -m pytest tests/test_semgrep_reference.py

# Verify documentation parity
.venv/Scripts/python.exe -m pytest tests/test_docs_parity_and_sync.py
```

---

## 3. Contributor Test Contracts

1. **Deterministic Execution**: Tests must not make live internet requests or require all 77 third-party binaries to be installed in CI.
2. **Fixture-First Development**: Every engine adapter must have corresponding JSON/text/XML fixtures in `tests/fixtures/engine_reports/<engine>/`.
3. **Transport Isolation**: FastMCP stdio tests must verify that stdin/stdout frames remain pure.

See [Testing Guide](developer/testing-guide.md).

## Testing Context Intelligence & Distillers (Phases 41–43)
* Unit tests for distillers and token routing: `tests/test_phase41_router_distillers.py`.
* Unit tests for session memory and ship linting: `tests/test_phase41_memory_ship.py`.
* Unit tests for TOON serialization and AST outlines: `tests/test_phase42_toon_skeleton.py`.
* Unit tests for 7-vector Ship Cockpit: `tests/test_phase42_ship_cockpit.py`.
* Unit tests for CCR store and GroundingVerifier: `tests/test_phase43_ccr_grounding.py`.
* Unit tests for InvariantGraph, FailureLedger, and MistakeMiner: `tests/test_phase43_mistake_memory.py`.
