# ADR-0034: Autonomous Flaky Test Stress Perturbation and Self-Healing

## Status
Accepted (v0.2.0 / Phase 44)

## Context
Flaky tests undermine developer confidence in CI suites. Diagnosing intermittent race conditions, unseeded randomness, or global state leaks manually is time-consuming.

## Decision
1. Implement `rush test-heal` (`src/rush/tools/test_heal.py`) and FastMCP tool `rush_test_heal`.
2. Execute a 20-iteration perturbation stress loop with randomized thread scheduling, clock skew, and execution ordering.
3. Classify root cause into three deterministic categories:
   - Async Race Condition: Missing condition wait or future resolution.
   - Unseeded Random State: Non-deterministic pseudo-random number generator calls.
   - Global State Leak: Un-cleared module-level caches or environment variables across tests.
4. Synthesize AST patches (e.g. adding explicit wait conditions or fixture teardowns) and verify them in an ephemeral Git worktree sandbox before applying them to the working directory.

## Consequences
- **Positive**: Automatically repairs flaky tests without masking errors with simple retry loops.
- **Negative**: Requires process stress-loop execution time (governed by `--allow-slow`).
- **Safety**: Sandboxed in ephemeral Git worktrees; never applies unverified patches.
