# ADR-0046: Pre-Flight Ship-Readiness Cockpit

## Status
Accepted (v0.3.0 / Phase 41, 42)

## Context
Releasing code requires running numerous disparate commands (clean caches, check env parity, audit migrations, verify SemVer, sync docs, inspect packages, run test suite), leading to forgotten checks and broken deployments.

## Decision
1. Implement a unified **Pre-Flight Ship Cockpit (`rush ship`)** in `src/rush/tools/ship/` consolidating 7 deterministic quality vectors:
   - Vector 1: `rush ship clean` (Scratch & cache purger)
   - Vector 2: `rush ship env` (AST `.env.example` parity linter)
   - Vector 3: `rush ship migration` (Zero-downtime SQL DDL table lock linter)
   - Vector 4: `rush ship semver` (Public API signature diff enforcer)
   - Vector 5: `rush ship docs` (Markdown link & CLI reference parity auditor)
   - Vector 6: `rush ship pack` (Sandboxed RAM release archive leak auditor)
   - Vector 7: `rush ship gate` (Unified parallel 7-vector release green-light runner)
2. Execute all 7 checks in parallel worker pools, delivering a complete release verdict in $<2.0\text{ seconds}$.

## Consequences
- **Positive**: Eliminates deployment anxiety and pre-release oversights with 1-command verification.
- **Negative**: Requires maintaining polyglot AST linters for env vars, DDL, and API signatures.
- **Safety**: 100% local, zero-cloud execution; non-destructive by default.
