# Workflow: Autonomous Test Healing & API Contract Governance

## 1. Healing a Flaky Async Test
Required end-to-end healing is planned in [P64-12](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-12--complete-test-healing-contract-f12). The current command is a legacy repeated-test/heuristic proposal route; it does not prove diagnosis or a verified repair. Do not treat a generated comment as a fix.
```bash
rush test-heal --target tests/test_async.py --runs 10
```

## 2. Pre-PR Breaking Change Verification
```bash
rush api-diff --base main
```
