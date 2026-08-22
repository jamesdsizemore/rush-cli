# ADR-0031: Pre-Flight Ship-Readiness Cockpit and Zero-Downtime Gates

## Status
Accepted (v0.2.0 / Phase 41C)

## Context
Releasing software often causes "shipping anxiety" because developers lack a unified, local, 1-command verification suite ensuring clean git working state, code-to-environment parity, lock-free database migrations, SemVer contract preservation, valid documentation links, and non-leaking distribution packages.

## Decision
1. Implement the **Pre-Flight Ship-Readiness Cockpit** (`rush ship`) in `src/rush/ship/`.
2. Organize 7 deterministic pre-flight subcommands across 4 shipping readiness pillars:
   - `rush ship clean`: Purges temporary scratch files and uncommitted build caches.
   - `rush ship env`: Extracts `os.getenv` / `process.env` calls from AST and cross-references `.env.example`.
   - `rush ship migration`: Audits SQL DDL migrations for table-locking hazards (`NOT NULL` without default, dangerous column drops).
   - `rush ship semver`: Uses AST signature analysis (Griffe) to enforce SemVer 2.0.0 breaking change detection.
   - `rush ship docs`: Validates all markdown documentation links and ensures CLI reference parity.
   - `rush ship pack`: Sandboxes wheel/npm package builds in RAM to verify zero file or secret leaks.
   - `rush ship gate`: Aggregates the 7-vector pre-flight suite into a single deterministic release green-light verdict in $<2\text{ seconds}$.

## Consequences
- **Positive**: Eliminates shipping anxiety, guarantees zero-downtime database migrations, and prevents missing environment variable crashes in production.
- **Negative**: Adds 7 subcommands to the CLI namespace requiring documentation synchronization.
- **Safety**: Fully deterministic, local-first execution with in-memory archive sandboxing.
