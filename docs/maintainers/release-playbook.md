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

## Pre-Release Installed Artifact & Governance Probes (Phase 51: RM-P0-03)
Before publishing any release or pushing tags:
1. Verify first-party coverage manifest sync: `python scripts/build_remediation_manifests.py --coverage`
2. Verify public operations inventory sync: `python scripts/build_remediation_manifests.py --operations`
3. Execute clean isolated artifact probes outside the checkout:
   ```bash
   uv build
   python scripts/probe_installed_artifacts.py --json
   ```
4. Confirm `governance/remediation-phase-51.toml` status is `completed` and all prerequisite remediation release gates are satisfied.


