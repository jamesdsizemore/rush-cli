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
2. Run `rush attest --out release.intoto.jsonl`.
3. Verify all 42 FastMCP tools and CLI commands pass test suites.

