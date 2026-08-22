# Specification: Autonomous Flaky Test Healer

## 1. Overview
`TestHealer` (`src/rush/tools/test_heal.py`) and `GitSandbox` (`src/rush/core/git_sandbox.py`) execute repeated perturbation runs on non-deterministic tests in isolated throwaway worktrees, diagnosing race conditions and synthesizing AST stabilization fixtures.

## 2. CLI & FastMCP Reference
* `rush test-heal --target <TEST_PATH> [--runs <INT>]`
* `rush_test_heal(target, runs=5)`
