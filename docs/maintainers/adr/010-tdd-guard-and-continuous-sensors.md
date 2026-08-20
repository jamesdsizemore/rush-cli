# ADR-010: TDD Guard & Continuous Architectural Sensors

## Status
Accepted

## Context
Code bases rapidly accumulate architectural drift, AI code bloat (slop), and missing tests unless gated by deterministic guards.

## Decision
1. Implement `TddGuardTool` (`rush tdd`) verifying test file existence.
2. Integrate AST anti-pattern scanner (`aislop`), modular boundaries (`tach`), code decay sensors (`sentrux`), token density analyzer (`clines`), diff coverage (`undercover`), and offline trust verifier (`cejel`).

## Consequences
- Guaranteed regression protection for AI pair-programming and developer workflows.
