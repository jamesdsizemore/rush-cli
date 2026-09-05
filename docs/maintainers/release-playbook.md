# Maintainers/Release Playbook

## Pre-Release Gate Verification (Phases 41–43)
Before publishing a release:
```bash
rush ship clean
rush ship env
rush ship docs
rush ship migration
rush ship semver
rush ship pack
rush ship gate
```

## Pre-Release Architecture & Blast Radius Checks
1. Run `rush arch-guard` to ensure clean architectural boundaries.
2. Run `rush blast-radius` across all modified core modules.



## Pre-Release API Diff Verification
Verify public API contract compatibility using `rush api-diff --base main`.



## Pre-Release Database Audit
Execute `rush db-drift` to guarantee zero unmigrated schema changes before tagging releases.



## Pre-Release Traceability Verification
Run `rush trace` and `rush simulate-ci` to verify full specification compliance prior to tagging releases.



## Flagship v0.3.0 Release Checklist
1. Execute `rush license-matrix` and `rush iam-audit`.
2. Run `rush attest --target-artifact dist/*.whl --export-path dist/release.intoto.json --allow-artifact-write`.
3. Verify all 52 catalog tools and 73 FastMCP tools pass test suites.

## Pre-Release Installed Artifact & Governance Probes (Phases 51 & 52: Findings R-001 & R-012 Closed)
Before publishing any release or pushing tags:
1. Verify first-party coverage manifest sync: `python scripts/build_remediation_manifests.py`
2. Verify public operations inventory sync: `python scripts/build_remediation_manifests.py --operations`
3. Execute clean isolated artifact probes outside the checkout:
   ```bash
   uv build
   python scripts/probe_installed_artifacts.py --json
   ```
4. Verify Package Identity & Version Authority contract suites:
   ```bash
   pytest tests/test_phase52_package_identity.py tests/test_phase52_version_contract.py tests/test_phase52_installed_artifacts.py -v
   ```
5. Confirm `governance/remediation-phase-52.toml` status is `completed` and R-001 and R-012 in `governance/remediation-contracts.toml` are marked `completed`.

## Pre-Release Sanitization & Diagnostic Probes (Phase 53: Findings R-002 & R-008 Closed)
Before finalizing any release candidate:
1. Verify deep recursive sanitization and pre-truncation contracts:
   ```bash
   pytest tests/test_phase53_sanitizer_contract.py tests/test_phase53_output_boundaries.py tests/test_phase53_governance_writers.py tests/test_phase53_state_writers.py -v
   ```
2. Verify exception diagnostics and stderr logging invariants:
   ```bash
   pytest tests/test_phase53_logging_diagnostics.py -v
   ```
3. Confirm `governance/remediation-phase-53.toml` status is `completed` and R-002 and R-008 in `governance/remediation-contracts.toml` are marked `completed`.

## Pre-Release Tool Result Schema & Operation Probes (Phase 54: Finding R-011 Closed)
Before finalizing any release candidate:
1. Verify ToolResultV1 schema kernel and operation adapter contract suites:
   ```bash
   pytest tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py -v
   ```
2. Confirm 100% operation reconciliation (146 operations) across Click leaves and FastMCP routes:
   ```bash
   pytest tests/test_phase51_public_operations.py -v
   ```
3. Confirm `governance/remediation-phase-54.toml` status is `completed` and R-011 in `governance/remediation-contracts.toml` is marked `completed`.

## Pre-Release Physical Containment & Verifier Probes (Phase 55: Foundations for R-003, R-009, R-010, R-016)
Before finalizing any release candidate:
1. Verify Phase 55 contract suites:
   ```bash
   pytest tests/test_phase55_atomic_file.py tests/test_phase55_physical_containment.py tests/test_phase55_verifier_record.py -v
   ```
2. Confirm `governance/remediation-phase-55.toml` status is `completed`.

### Phase 56 Pre-Release Verification
- Verify all 16 Phase 56 contract tests pass.
- Verify user ledger authority operates outside git repositories.
- Verify plugin output conforms to `ToolResultV1`.

## Phase 57 Release Gates

Prior to release:
1. Verify all 48 Phase 57 tests pass (`pytest tests/test_phase57_*.py`).
2. Verify full test suite passes with >= 1,134 tests.
3. Verify public operations manifest reconciles with 100% of declared operations.
