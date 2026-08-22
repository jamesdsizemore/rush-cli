# Workflow: Autonomous Test Healing & API Contract Governance

## 1. Healing a Flaky Async Test
```bash
rush test-heal --target tests/test_async.py --runs 10
```

## 2. Pre-PR Breaking Change Verification
```bash
rush api-diff --base main
```
