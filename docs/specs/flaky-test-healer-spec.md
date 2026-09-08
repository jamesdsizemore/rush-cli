# Specification: Autonomous Flaky Test Healer

Status: planned — implementation [P64-12](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-12--complete-test-healing-contract-f12). The current runner repeats tests and emits heuristic/comment proposals; it does not satisfy the perturbation, cause-isolation or verified AST-repair contract below. Review finding F12 remains open.

## 1. Overview
The required `TestHealer` and `GitSandbox` behavior is repeated controlled perturbation runs in isolated throwaway worktrees, evidence-based diagnosis and verified AST stabilization. P64-12 specifies the exact three cause categories and 20-iteration default; existing CLI/MCP registration still exposes the legacy `runs=5` default until implementation.

## 2. CLI & FastMCP Reference
* `rush test-heal --target <TEST_PATH> [--runs <INT>]`
* `rush_test_heal(target, runs=5)`
