# Phase 07 implementation ledger — Advanced Nonbrowser Posture and Executed Modes

Scope:
- Permission Foundation (Phase 07.0): explicit consent flags (`--allow-network`, `--allow-download`, `--allow-cache-write`, `--allow-build`, `--allow-slow`, `--allow-artifact-write`, `--allow-browser`) with canonical `metadata.execution`.
- Promoting Existing Adapters (Phase 07.A): promoted 15 tools to `real_adapter` with reference fake-process test suites (`test_ruff_reference.py`, `test_eslint_reference.py`, `test_prettier_reference.py`, `test_pytest_reference.py`, `test_vitest_reference.py`, `test_mypy_reference.py`, `test_tsc_reference.py`, `test_vulture_reference.py`, `test_knip_reference.py`, `test_radon_reference.py`, `test_jscpd_reference.py`, `test_sloppylint_reference.py`, `test_djlint_reference.py`, `test_commitlint_reference.py`, `test_cdxgen_reference.py`).
- Executed Modes for Advanced Evidence (Phase 07.B): dual mode (`imported` vs `executed` under explicit permissions) across `coverage`, `contract`, `mutation`, `pbt`, `fuzz`, `load`, `flaky`, `snapshot`, `codeql`.
- Network and Security Scanners (Phase 07.C): adapters for Semgrep, Lychee, Trivy, Grype, Cosign, Kubeconform with offline defaults and explicit network/download gates.

## Error Register

| Timestamp | Attempt | Error | Recovery |
|---|---|---|---|
| 2026-08-19 | Snapshot executed mode permission test | Missing subprocess mock on `snapshot_mod.engine_on_path` led to unexpected skip | Mock `engine_on_path` and `run_subprocess` in `tests/test_executed_modes.py` |
| 2026-08-19 | Truth audit exact tuple assertion | Extra fixture in `PARSER_FIXTURE_SUITES["iac"]` failed equality test | Align `PARSER_FIXTURE_SUITES` entries with claimed `TOOL_SPECS.engine_names` |
| 2026-08-19 | Ruff lint & format checks | Formatting inconsistencies in new engines/tools | Ran `ruff check --fix` and `ruff format` across src and tests |

## Verification Evidence

- 294 passing tests, 7 skipped (due to optional uninstalled static binaries) in ~8.5s.
- `ruff check src tests` passed with zero errors.
- `ruff format --check src tests` passed with 162 files formatted.
- `graft check .` passed and graph in sync.
