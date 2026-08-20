# Testing confidence

Start with the tests your project already has:

```bash
rush test .
```

Rush can route Python projects to pytest and JS/TS projects to Vitest. A passing test run shows the executed suite passed; it does not prove untested behavior is correct.

Additional commands exist for `coverage`, `pbt`, `snapshot`, `visual`, `flaky`, and `contract`. Their current implementations import contained local evidence or return guarded placeholders rather than becoming surprise test runners:

- `coverage` imports a local coverage.py JSON report; it does not run tests.
- `pbt` imports a local property-test report.
- `flaky` examines a local JUnit report for duplicate-case evidence.
- `contract` imports a local Pact report and does not contact a live service.
- `snapshot` imports a local comparison report and never accepts a baseline.
- `visual` remains a guarded placeholder; no baseline is accepted by default.

The generic CLI currently passes only a path, so some evidence filenames and permission options are not configurable through CLI. Read each JSON summary and treat `skipped` as no conclusion. See [Advanced checks](advanced-checks.md).
