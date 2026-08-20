# ADR 0013: TDD Guard & Continuous Architectural Sensors

## Context
In rapid AI coding workflows, agents often generate implementation code without corresponding unit test suites, or introduce modular boundary violations and code decay across polyglot repositories.

## Decision
1. Implement `TddGuardTool` (`rush tdd`) in `src/rush/tools/tdd_guard.py`:
   - Scans project for test file discovery corresponding to newly added or modified source modules.
   - Enforces Red-Green-Refactor development discipline.
2. Integrate AST and modular architecture sensors:
   - `aislop` for AI boilerplate and hallucinated code detection.
   - `tach` for modular boundaries and dependency cycle enforcement.
   - `sentrux` for real-time architectural decay and cyclomatic spikes.
   - `clines` for token density and LLM context cost analysis.
   - `undercover` for git-diff structural test coverage verification.
   - `cejel` for offline cryptographic trust attestation.

## Consequences
- AI coding agents and human contributors have deterministic quality guardrails that prevent architectural degradation and untested code merges.
