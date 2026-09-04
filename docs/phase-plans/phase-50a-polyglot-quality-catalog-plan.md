# Phase 50a implementation plan — polyglot error catalog, license matrix, and cloud IAM audit

## 1. Purpose and status

- **Operation:** Create the implementation plan for Phase 50a (sub-phase 1 of the decomposed Phase 50).
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized by this plan. Code freeze in effect.
- **Authority:** Roadmap capability families I14, I17, and I18 from `docs/rush-token-innovation-enhancement-report-plan.md`.
- **Relationship to Remediation:** Precedes Phase 51. Does NOT attempt ad-hoc remediation of repository-wide kernel infrastructure (R-001 through R-016), which is strictly reserved for Phases 51–60.
- **Boundary:** Read-only polyglot static analysis, licensing metadata evaluation, and Cloud IAM least-privilege analysis. Zero filesystem writes outside test runs.
- **Predecessor:** Phase 49 trace and coordination cycle complete; `main` branch test baseline passing (847 tests).
- **Successor:** Phase 50b (Attribution, PR Evidence, and Workspace Hygiene).
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

---

## 2. Authority, evidence, and decisions

### 2.1 Authority order

1. User instructions and constraints (zero code modification during planning).
2. Repository `AGENTS.md` (canonical `ToolResult` shape, engine discovery, stdio MCP stdout, no UI/canvas scope).
3. Governing roadmap `docs/rush-token-innovation-enhancement-report-plan.md` (I14, I17, I18 requirements).
4. Repository remediation plan `docs/developer/repository-remediation-plan.md` and `docs/phase-plans/phase50-adversarial-review.md`.
5. Current repository source, tests, and configuration as empirical ground truth.

### 2.2 Current-state evidence

| Family | Existing Implementation | Existing Tests | Status in Repository |
|---|---|---|---|
| **I14 (Error Catalog)** | None | None | Needs complete clean implementation conforming to `src/rush/tools/base.py`. |
| **I17 (License Matrix)** | `src/rush/tools/license_matrix.py` (stub) | `tests/test_phase50_slsa_attestation.py:test_license_matrix_scanner` | Basic prototype exists; needs polyglot parser, SPDX mapping, copyleft categorization, and canonical `ToolResult`. |
| **I18 (Cloud IAM Audit)** | `src/rush/tools/iam_audit.py` (stub) | `tests/test_phase50_slsa_attestation.py:test_iam_policy_synthesizer` | Stub exists; needs multi-cloud mapping (AWS, GCP, Azure), Terraform/IaC parser, and canonical `ToolResult`. |

### 2.3 Closed decisions

- **No competing kernel infrastructure:** Phase 50a does not modify `src/rush/tools/common.py` atomic write helpers or invent `ToolOptionSpec` in `src/rush/catalog.py`. It uses the existing canonical `ToolFn` interface from `src/rush/tools/base.py`.
- **No heavy dependencies:** Use existing `tree-sitter==0.26.0`, stdlib `ast`, stdlib `json`, and add only lightweight AST/manifest parsers: `license-expression>=30.4,<31` and `python-hcl2>=8.1,<9`. No `scipy`, no `textual`, no `codebleu`.
- **Engine discovery:** Third-party CLI tools (e.g. `npm`, `cargo`) are discovered from PATH. If missing, tools evaluate available project files or return structured `skipped`.
- **Transport parity:** Register all 3 tools in `src/rush/catalog.py` (`TOOL_SPECS`), `src/rush/tools/__init__.py` (`ALL_TOOLS`), and expose standard CLI subcommands and MCP tool endpoints without manual ad-hoc wrappers in `mcp.py`.
- **Documentation:** Explicitly create documentation in `docs/tools/` for each tool. Zero reliance on non-existent `scripts/sync_docs.py`.

---

## 3. Goals, outcomes, exclusions, and invariants

### 3.1 Outcomes

1. **`rush error-catalog` (I14):** Extracts structured error definitions across Python, TypeScript, and Rust files. Builds typed error taxonomy with unique error codes and RFC 7807 problem detail representations.
2. **`rush license-matrix` (I17):** Scans polyglot package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`), determines license expressions via SPDX standards, identifies copyleft risks (Permissive, Weak Copyleft, Strong Copyleft, Proprietary), and flags dual-licensing conflicts.
3. **`rush iam-audit` (I18):** Analyzes application code for cloud SDK calls (boto3, @google-cloud, @azure) and scans Terraform (`.tf`) manifests to detect wildcard actions (`*`), unused permissions, and least-privilege violations against bundled provider schemas.
4. **Clean integration:** Adds 3 tools to `TOOL_SPECS` and `ALL_TOOLS`, increasing catalog tool count from 38 to 41.

### 3.2 Exclusions

- Zero filesystem modification of user source code.
- Zero ad-hoc persistence or file-locking systems.
- Zero Git hook installations.
- Zero network requests (all analysis is offline and local).

### 3.3 Invariants

- Python 3.12 with `uv`.
- MCP stdio stdout contains only valid JSON-RPC messages; diagnostics go to stderr.
- Tool returns canonical `ToolResult` with `status="ok|warn|fail|error|skipped"`.
- All checks use portable `uv run` commands, compatible with POSIX and Windows.

---

## 4. Admission and predecessor gate

Before starting Phase 50a tasks:
1. Verify clean git status: `git status --short --branch`.
2. Verify Python 3.12 environment: `uv run python --version`.
3. Verify test baseline: `uv run python -m pytest -q` passes with exactly 847 tests.
4. Verify code formatting and linting: `uv run ruff check src tests scripts` and `uv run ruff format --check src tests scripts`.
5. Stop condition: If any baseline test fails or git working tree contains uncommitted product changes, stop and report blocker.

---

## 5. Requirement-ownership ledger

| Requirement ID | Family | Capability Description | Owning Tasks | Deliverable Files |
|---|---|---|---|---|
| **REQ-50A-I14-CORE** | I14 | Polyglot error extraction (Python/TS/Rust) | P50A-001..P50A-004 | `src/rush/tools/error_catalog.py`, `tests/test_error_catalog.py` |
| **REQ-50A-I14-GEN** | I14 | RFC 7807 problem details & catalog export | P50A-005..P50A-006 | `src/rush/tools/error_catalog.py`, `tests/test_error_catalog.py` |
| **REQ-50A-I17-CORE** | I17 | Polyglot package manifest license scanner | P50A-007..P50A-010 | `src/rush/tools/license_matrix.py`, `tests/test_license_matrix.py` |
| **REQ-50A-I17-SPDX** | I17 | SPDX evaluation and copyleft classification | P50A-011..P50A-012 | `src/rush/tools/license_matrix.py`, `tests/test_license_matrix.py` |
| **REQ-50A-I18-CORE** | I18 | Multi-cloud SDK action parser (AWS/GCP/Azure) | P50A-013..P50A-016 | `src/rush/tools/iam_audit.py`, `tests/test_iam_audit.py` |
| **REQ-50A-I18-IAC** | I18 | Terraform/HCL2 policy audit & wildcard check | P50A-017..P50A-018 | `src/rush/tools/iam_audit.py`, `tests/test_iam_audit.py` |
| **REQ-50A-INTEG** | Shared | Catalog, CLI, MCP registration & docs | P50A-019..P50A-022 | `src/rush/catalog.py`, `src/rush/tools/__init__.py`, `docs/tools/*.md` |

---

## 6. Shared contracts and handoff

- **Canonical ToolFn:** All three tools subclass `ToolFn` from `src/rush/tools/base.py`.
- **ToolResult Schema:**
  - `name`: `"error-catalog"`, `"license-matrix"`, `"iam-audit"`
  - `status`: `"ok"` (no findings), `"warn"` (warnings), `"fail"` (violations found), `"skipped"` (no relevant files found)
  - `findings`: List of `Finding(path, line, column, severity, message, rule, remediation)`
  - `summary`: Human-readable summary string
- **Registration:**
  - `TOOL_SPECS["error-catalog"]`, `TOOL_SPECS["license-matrix"]`, `TOOL_SPECS["iam-audit"]` in `src/rush/catalog.py`.
  - Added to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Handoff:** Phase 50a delivers 41 canonical catalog tools with 100% test pass rate to Phase 50b.

---

## 7. Contract-test inventory

| Test File | Target Seam | Key Assertions |
|---|---|---|
| `tests/test_error_catalog.py` | `ErrorCatalogTool` | Extracts custom exceptions from Python AST, TS error classes, Rust `thiserror`/enums; formats RFC 7807 JSON. |
| `tests/test_license_matrix.py` | `LicenseMatrixTool` | Parses `pyproject.toml`, `package.json`, `Cargo.toml`; maps licenses to SPDX identifiers; flags GPL/AGPL copyleft risk. |
| `tests/test_iam_audit.py` | `IamAuditTool` | Extracts `s3:GetObject`, `storage.objects.get` calls; flags `*` resource/action in `.tf` policies; outputs minimal policy recommendations. |
| `tests/test_phase50a_integration.py` | CLI & MCP transports | `rush error-catalog`, `rush license-matrix`, `rush iam-audit` CLI execution; `rush_error_catalog`, `rush_license_matrix`, `rush_iam_audit` MCP tools. |

---

## 8. File, dependency, and documentation governance

### 8.1 File writes

- **Production:**
  - `src/rush/tools/error_catalog.py` (new)
  - `src/rush/tools/license_matrix.py` (rewrite existing prototype)
  - `src/rush/tools/iam_audit.py` (rewrite existing prototype)
  - `src/rush/catalog.py` (register 3 tool specs)
  - `src/rush/tools/__init__.py` (export and register in `ALL_TOOLS`)
  - `src/rush/resources/iam/aws_actions.json` (new reference data)
  - `src/rush/resources/iam/gcp_actions.json` (new reference data)
  - `src/rush/resources/iam/azure_actions.json` (new reference data)
- **Tests:**
  - `tests/test_error_catalog.py` (new)
  - `tests/test_license_matrix.py` (rewrite/expand)
  - `tests/test_iam_audit.py` (rewrite/expand)
  - `tests/test_phase50a_integration.py` (new)
- **Documentation:**
  - `docs/tools/error_catalog.md` (new)
  - `docs/tools/license_matrix.md` (new)
  - `docs/tools/iam_audit.md` (new)
  - `docs/TOOL_CATALOG.md` (update catalog entries)
  - `docs/CLI_REFERENCE.md` (update CLI commands)
  - `docs/MCP_REFERENCE.md` (update MCP tools)

### 8.2 Dependencies

- Minimal additions to `pyproject.toml`:
  - `license-expression>=30.4,<31` (lightweight pure-Python SPDX parser)
  - `python-hcl2>=8.1,<9` (pure-Python Terraform HCL parser)
- Prohibited dependencies: `scipy`, `textual`, `codebleu`, `onnxruntime`, `llama-cpp-python`.

---

## 9. Ordered execution workstreams and atomic task cards

### Workstream 1: I14 Polyglot Error Catalog (Tasks P50A-001..P50A-006)

#### P50A-001 — RED: Pin Python exception AST extraction
- **Action:** Create `tests/test_error_catalog.py` with `test_extract_python_exceptions_ast`. Assert extracting class name, docstring, base exception, and line number from sample Python code.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` fails with `ModuleNotFoundError` or `ImportError`.

#### P50A-002 — GREEN: Implement Python exception AST extractor
- **Action:** Create `src/rush/tools/error_catalog.py` implementing `PythonExceptionExtractor` using stdlib `ast.NodeVisitor`.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` passes.

#### P50A-003 — RED: Pin TypeScript and Rust error extraction
- **Action:** Add `test_extract_typescript_errors` and `test_extract_rust_errors` to `tests/test_error_catalog.py`.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` fails at new assertions.

#### P50A-004 — GREEN: Implement TypeScript and Rust error extractors
- **Action:** Implement regex and tree-sitter based extraction for TypeScript `Error` subclasses and Rust `enum` error declarations in `error_catalog.py`.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` passes.

#### P50A-005 — RED: Pin RFC 7807 problem details and catalog generation
- **Action:** Add `test_generate_rfc7807_problem_detail` and `test_generate_error_catalog_json`.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` fails at new assertions.

#### P50A-006 — GREEN: Implement RFC 7807 formatting and ErrorCatalogTool
- **Action:** Implement `ErrorCatalogTool(ToolFn)` returning canonical `ToolResult` with RFC 7807 metadata in findings.
- **Checks:** `uv run python -m pytest tests/test_error_catalog.py -q` passes.

---

### Workstream 2: I17 Polyglot License Matrix (Tasks P50A-007..P50A-012)

#### P50A-007 — RED: Pin manifest dependency extraction (Python, Node, Rust)
- **Action:** Create `tests/test_license_matrix.py` with `test_parse_pyproject_dependencies`, `test_parse_package_json_dependencies`, `test_parse_cargo_toml_dependencies`.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` fails.

#### P50A-008 — GREEN: Implement polyglot manifest parser
- **Action:** Update `src/rush/tools/license_matrix.py` with parser using stdlib `tomllib` and `json` to extract package names and versions.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` passes.

#### P50A-009 — RED: Pin SPDX license resolution and normalization
- **Action:** Add `test_resolve_spdx_expressions` with valid and invalid SPDX expressions.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` fails.

#### P50A-010 — GREEN: Implement SPDX expression resolver
- **Action:** Implement license normalization using `license-expression` in `license_matrix.py`.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` passes.

#### P50A-011 — RED: Pin copyleft classification and dual-license conflict detection
- **Action:** Add `test_classify_copyleft_risk` (Permissive, Weak Copyleft, Strong Copyleft, Proprietary) and `test_detect_license_conflicts`.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` fails.

#### P50A-012 — GREEN: Implement LicenseMatrixTool with canonical ToolResult
- **Action:** Complete `LicenseMatrixTool(ToolFn)` emitting structured findings for strong copyleft licenses in application dependencies.
- **Checks:** `uv run python -m pytest tests/test_license_matrix.py -q` passes.

---

### Workstream 3: I18 Cloud IAM Audit (Tasks P50A-013..P50A-018)

#### P50A-013 — RED: Pin cloud SDK API call extraction from code
- **Action:** Create `tests/test_iam_audit.py` with `test_extract_aws_boto3_actions`, `test_extract_gcp_client_actions`, `test_extract_azure_sdk_actions`.
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` fails.

#### P50A-014 — GREEN: Implement SDK action extractor
- **Action:** In `src/rush/tools/iam_audit.py`, implement AST analyzer mapping SDK method invocations to IAM permission strings (e.g. `s3.get_object` -> `s3:GetObject`).
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` passes.

#### P50A-015 — RED: Pin Terraform/HCL2 IAM policy parser and wildcard detection
- **Action:** Add `test_parse_terraform_iam_policy` and `test_detect_wildcard_iam_actions`.
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` fails.

#### P50A-016 — GREEN: Implement Terraform policy parser with python-hcl2
- **Action:** In `iam_audit.py`, parse Terraform `.tf` files, inspect `aws_iam_policy_document` and JSON policy blocks, and flag `Action: "*"` or `Resource: "*"`.
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` passes.

#### P50A-017 — RED: Pin least-privilege comparison and minimal policy synthesis
- **Action:** Add `test_synthesize_minimal_policy_from_usage`.
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` fails.

#### P50A-018 — GREEN: Complete IamAuditTool with canonical ToolResult
- **Action:** Finalize `IamAuditTool(ToolFn)` in `src/rush/tools/iam_audit.py` returning unused permissions and least-privilege recommendations.
- **Checks:** `uv run python -m pytest tests/test_iam_audit.py -q` passes.

---

### Workstream 4: Integration, Registration, Documentation & Graft (Tasks P50A-019..P50A-022)

#### P50A-019 — RED: Pin catalog and transport registration
- **Action:** Create `tests/test_phase50a_integration.py` asserting `error-catalog`, `license-matrix`, and `iam-audit` are in `TOOL_SPECS`, in `ALL_TOOLS`, and have CLI and MCP endpoints.
- **Checks:** `uv run python -m pytest tests/test_phase50a_integration.py -q` fails.

#### P50A-020 — GREEN: Register tools in catalog, CLI, and MCP
- **Action:** Add specs in `src/rush/catalog.py`, add instances to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Checks:** `uv run python -m pytest tests/test_phase50a_integration.py tests/test_catalog.py tests/test_cli_registry.py -q` passes.

#### P50A-021 — DOCS: Author exact documentation pages
- **Action:** Create `docs/tools/error_catalog.md`, `docs/tools/license_matrix.md`, `docs/tools/iam_audit.md`. Update `docs/TOOL_CATALOG.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`.
- **Checks:** Verify links and command syntax against registered options.

#### P50A-022 — GRAFT: Rebuild repository context graph
- **Action:** Run `npx @nanonets/graft build` or verify `graft/` index includes all newly added symbols.
- **Checks:** `uv run python -m pytest -q` passes; full suite reaches `>= 875` tests (847 baseline + >=28 new tests).

---

## 10. Final verification and delivery gate

1. Run full test suite: `uv run python -m pytest tests/ -q`. All tests must pass (expected count >= 875).
2. Run linters: `uv run ruff check src tests scripts` (zero errors).
3. Run format check: `uv run ruff format --check src tests scripts` (zero diffs).
4. Verify catalog count: Exactly 41 tools registered in `TOOL_SPECS` and `ALL_TOOLS`.
5. Verify zero code changes outside Phase 50a deliverables.

---

## 11. Exit checklist and successor handoff

- [ ] All 22 task cards completed in RED/GREEN/VERIFY sequence.
- [ ] Zero unverified SLSA claims, zero `scipy`/`textual` dependencies, zero hardcoded `.venv/Scripts/` paths.
- [ ] Clean handoff to Phase 50b (Attribution, PR Evidence, and Workspace Hygiene).
