# Testing with Confidence: TDD, Coverage, & Reliability

Automated tests are the safety harness of modern software development. Without tests, refactoring code or deploying on a Friday feels terrifying. With a solid test suite, you can ship changes rapidly knowing that existing features will not break.

Rush makes running, verifying, and measuring your tests simple and transparent.

---

## 1. Running Your Tests (`rush test`)

```bash
rush test .
```

When you run `rush test`, Rush automatically detects your test framework and executes your suite:
- **Python**: Coordinates `pytest`.
- **TypeScript / JavaScript**: Coordinates `Vitest` or `Jest`.
- **API Scenarios**: Coordinates `Newman` (Postman CLI).

If all tests pass, you get a clean summary of total tests run and total execution time. If any test fails, Rush isolates the exact failure message, file path, and line number so you can fix it immediately.

---

## 2. Enforcing Test-Driven Development (`rush tdd`)

```bash
rush tdd .
```

How often have you seen a pull request where someone modified critical business logic, but forgot to write a test for it?

`rush tdd` inspects the files you’ve modified and verifies that corresponding test contracts exist:
- If you modified `src/services/billing.py`, Rush verifies that `tests/test_billing.py` exists and asserts behavior against the updated module.
- If no test exists, `rush tdd` flags a friendly reminder: `[FAIL] Missing test contract for billing.py`.

---

## 3. Code Coverage & Evidence Importers (`rush coverage`)

Code coverage tells you what percentage of your source lines and branches were actually executed during your test run.

Rush supports **dual-mode coverage**:

### Mode 1: Instant Offline Import (No Slow Re-runs!)
If your CI or local test runner already generated a coverage file (`coverage.json`, `lcov.info`, or `cobertura.xml`), Rush imports and normalizes it instantly:

```bash
rush coverage coverage.json
```

### Mode 2: Executed Mode
Run native coverage measurements on demand:
```bash
rush coverage . --allow-slow
```

---

## 4. Catching Flaky Tests (`rush flaky`)

A "flaky test" is a test that sometimes passes and sometimes fails without any code changes (often caused by timing issues, network race conditions, or unseeded random numbers).

```bash
rush flaky . --allow-slow
```

Rush executes tests under quarantined repetitions to identify flaky tests and report them before they destabilize your team's CI pipeline.

---

## 5. Mutation Testing: Testing Your Tests (`rush mutation`)

High code coverage doesn't always mean high test quality: you could have 100% test coverage with zero assertions!

Mutation testing introduces tiny intentional bugs ("mutations") into your code (like changing `if a > b:` to `if a < b:`) and checks if your tests catch the bug:

```bash
rush mutation . --allow-slow
```

If your tests fail when the code is mutated, the mutant is "killed" (your tests are strong). If the tests still pass, Rush highlights where your test assertions are too weak.

---

## Next Steps

- Learn how to protect your code and secrets in [Security & Supply Chain](security-and-supply-chain.md).
- Discover how to check project config files in [Checking Project Files](checking-project-files.md).
