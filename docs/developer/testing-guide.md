# Developer Testing Guide & Test Architecture

This guide explains the 9 testing layers that maintain the deterministic test pass rate across all 52 tools and 124 engines in Rush CLI.

---

## 1. The 9 Testing Layers

```text
Layer 1: Unit Contracts (Finding normalization, fingerprint hashing, secret redaction)
Layer 2: Parser Fixtures (tests/fixtures/engine_reports/ for all 121 engines)
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

---

## 4. Benchmark Harness & Gate Verifications (Phases B1–B6)

The benchmark harness tests 40 declared scenarios across 6 core domains:

```bash
# Run all benchmark test suites (contracts, runner, providers, privacy, context, coordination, local)
.venv/Scripts/python.exe -m pytest tests/test_benchmark_*.py -q

# Run all 40 benchmark scenarios and print terminal execution table
.venv/Scripts/python.exe -m scripts.benchmarks.run --all
```

Key invariants:
- **Zero-Network Invariant**: All tests execute using local JSON fixtures in `tests/fixtures/benchmarks/`.
- **Secret Redaction**: Credentials never appear in output JSON or logs; sanitized to `[REDACTED:<TYPE>]`.
- **Ollama Rejection**: The `ollama` runtime and repository-local model caches are rejected.

---

## 5. Phase 50a Test Suites
- `tests/test_error_catalog.py`: Exception extraction (Python AST, TypeScript, Rust), deterministic RFC 7807 problem details generation, markdown documentation export permissions, path traversal rejection.
- `tests/test_license_matrix.py`: Polyglot package manifest parsing (`pyproject.toml`, `package.json`, `Cargo.toml`), copyleft violation detection, manual review classification, SPDX identifier normalization.
- `tests/test_iam_audit.py`: Multi-cloud SDK operation parsing (AWS boto3, GCP google.cloud, Azure blob), Terraform wildcard IAM action detection (`iam-wildcard-action`), least-privilege policy generation, artifact write permission gates.
- `tests/test_phase50a_integration.py`: End-to-end CLI JSON emission and MCP server registration parity for all Phase 50a tools.

## 6. Phase 50b Test Suites
- `tests/test_provenance_ai.py`: Git commit trailer parsing (`Co-authored-by:`, `Generated-by:`, `Model:`, `Agent:`), shallow clone detection, and deterministic survival curve baselines.
- `tests/test_dead_asset.py`: Polyglot static asset reference scanning (HTML, CSS, JS/TS, Markdown), potential disk space savings calculation, and guarded SHA-256 pre-prune validation.
- `tests/test_pr_synthesize.py`: Git diff aggregation, risk tier computation (`low`/`medium`/`high`), and CODEOWNERS pattern matching and reviewer recommendation.
- `tests/test_phase50b_integration.py`: End-to-end CLI JSON emission and FastMCP registration parity for all Phase 50b tools.



## 7. Phase 50c Test Suites
- `tests/test_attest.py`: in-toto v1 Statement generation, dist/ artifact discovery, unsigned draft assurance, export permission checks.
- `tests/test_mem_profile.py`: Static AST unclosed resource detection, clean context managers, dynamic tracemalloc sampling.
- `tests/test_cold_start.py`: Heavy top-level package detection, wildcard imports, dynamic importtime waterfall analysis.
- `tests/test_offline_review.py`: Model absence handling, onnxruntime skip semantics, mocked inference session.
- `tests/test_benchmark.py`: Missing baseline handling, cache write permission gating, regression detection.
- `tests/test_phase50c_integration.py`: End-to-end CLI JSON emission and FastMCP registration parity for all 5 tools.

## 8. Phase 51 Contract Test Suites (Remediation Governance)
- `tests/test_phase51_coverage_manifest.py`: First-party coverage boundary, single classification, byte-stable TOML rendering, unclassified path rejection.
- `tests/test_phase51_public_operations.py`: Full Click leaf (129) and FastMCP route (73) reconciliation, unique operation IDs, non-live safe probes, canonical implementation parity.
- `tests/test_phase51_artifact_probes.py`: Independent wheel and sdist installation into isolated virtualenvs, environment scrubbing, origin verification, R-001 negative import control.
- `tests/test_phase51_engine_policy.py`: Engine support taxonomy across 19 families, support class validation (`mandatory`, `supported-optional`, `best-effort`), skip prohibitions for supported engines.

## 9. Phase 52 Contract Test Suites (Package Identity, Artifacts & Version Authority)
- `tests/test_phase52_package_identity.py`: AST scan ensuring zero `src.rush` imports across all first-party production and test files, isolated import negative control, and pytest collection isolation (`pythonpath = ["src"]` without `.`).
- `tests/test_phase52_version_contract.py`: Single version authority verification (`importlib.metadata.version("rush-cli")`), CLI `--version` parity, zero stale `"0.2.0"` hardcoded literals across providers, templates, and generators, and `PackageNotFoundError` development fallback.
- `tests/test_phase52_installed_artifacts.py`: Verification of environment scrubbing (`PYTHONPATH`, `VIRTUAL_ENV`), package origin isolation from repository checkout, and clean installation/execution of wheel and sdist in external working directories (resolving Finding R-001).

## 10. Phase 53 Contract Test Suites (Sanitization, Write Boundaries & Diagnostics)
- `tests/test_phase53_sanitizer_contract.py`: Deep recursive sanitization of values and keys, loss-visible key collision suffixing, fail-closed handling of unsupported objects, and execution input immutability.
- `tests/test_phase53_output_boundaries.py`: Pre-truncation subprocess output redaction, SARIF and HTML report sanitization, ResultCache SQLite persistence sanitization, and consensus SARIF export.
- `tests/test_phase53_governance_writers.py`: Sanitization across IDE governance synchronizers (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`), MCP mesh lock manager payloads, and SVG score badges.
- `tests/test_phase53_state_writers.py`: Disk sanitization across security audit logger, SQLite patch memory store, session flight recorder, preference store, invariant graph, benchmarks, and artifact exports.
- `tests/test_phase53_logging_diagnostics.py`: Non-swallowed NDJSON exception serialization to stderr, secret redaction across log messages and stack traces, stderr fallback logging on format failure, and strict stdout purity (resolving Findings R-002 and R-008).

## 11. Phase 54 Contract Test Suites (Tool Result Schema Kernel & Operation Adapters)
- `tests/test_phase54_result_schema.py`: Validation of canonical `ToolResultV1` dataclass, 8 required keys, ISO 8601 UTC timestamp format (`Z`), severity mapping (`info`, `warning`, `error`), schema error code validation (`MISSING_REQUIRED_KEY`, `INVALID_TYPE`, etc.), fail-closed structural validation, JSON serialization, and legacy adapter backward compatibility (`adapt_legacy_tool_result`, `adapt_legacy_finding`).
- `tests/test_phase54_operation_adapters.py`: Operation adapter taxonomy (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`, `OperationRegistry`), complete reconciliation with `governance/public-operations.toml` (146 operations: 67 tool, 62 admin, 17 service), tool execution output validation, and strict rejection of `ToolResultV1` wrapping on raw protocol frames (`mcp.initialize`, etc.).

## 12. Phase 55 Contract Test Suites (AtomicFile, Physical Containment & Verifier Records)
- `tests/test_phase55_atomic_file.py`: Validation of sanitized contracts (`SanitizedBytes`, `SanitizedJsonValue`), single implementation ownership, raw secret wrapper rejection, injected fault durability (old-or-new valid destination), and manager-owned tempfile cleanup.
- `tests/test_phase55_physical_containment.py`: Validation of symlink rejection (file/directory), Windows reparse point / junction rejection (`stat.FILE_ATTRIBUTE_REPARSE_POINT`), parent target swap detection, and outside sentinel preservation.
- `tests/test_phase55_verifier_record.py`: Validation of zero raw capability retention, constant-time verification (`hmac.compare_digest`), low-entropy capability rejection, and metadata non-invertibility.

### Phase 56: Plugin Trust Contract Test Suites
Run all 16 Phase 56 contract tests:
```powershell
.venv/Scripts/python.exe -m pytest tests/test_phase56_plugin_trust.py tests/test_phase56_plugin_closure.py tests/test_phase56_plugin_secret_channels.py tests/test_phase56_plugin_launch_identity.py tests/test_phase56_plugin_public_routes.py -v
```

## Phase 57 Invocation & Egress Contract Testing

Phase 57 introduced 25 contract tests across 5 test modules:
- `tests/test_phase57_invocation_context.py`: Transport equivalence, immutability, parity.
- `tests/test_phase57_physical_scope.py`: Scope widening, symlink/junction containment.
- `tests/test_phase57_public_operations.py`: Single execution, signature adaptation, route reconciliation, egress codes.
- `tests/test_phase57_cache_policy.py`: Cache key identity binding, bypass contracts, get/set sanitization.
- `tests/test_phase57_provider_egress.py`: Truthful provider outcomes, approved origins, redirect refusal.
