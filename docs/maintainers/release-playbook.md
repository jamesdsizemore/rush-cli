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



