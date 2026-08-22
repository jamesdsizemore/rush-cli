# ADR-0033: Real-Time AST Package Hallucination and Phantom Import Guard

## Status
Accepted (v0.2.0 / Phase 42)

## Context
AI agents often generate code referencing nonexistent packages or phantom standard library functions, opening applications to typosquatting supply-chain vulnerabilities and runtime import failures.

## Decision
1. Implement `rush hallu-guard` (`src/rush/safety/hallucination.py`) and FastMCP tool `rush_hallu_guard`.
2. Inspect import statements via AST parsing and validate them against:
   - Python/Node.js/Rust standard library catalogs.
   - Project manifests (`pyproject.toml`, `package.json`, `Cargo.toml`).
   - Local active virtual environments and module paths.
3. Intercept hallucinated imports in $<20\text{ ms}$ before patches are applied to disk.
4. Support optional network verification (`--allow-network`) against the official PyPI / npm package registries.

## Consequences
- **Positive**: Prevents supply-chain typosquatting attacks and eliminates `ModuleNotFoundError` crashes.
- **Negative**: Requires maintainable standard library metadata matrices.
- **Safety**: Fully offline by default; network registry checks require explicit permission flags.
