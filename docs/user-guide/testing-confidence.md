# Testing confidence

Start with the tests your project already has:

```bash
rush test .
```

Rush can route Python projects to pytest and JS/TS projects to Vitest. A passing test run shows the executed suite passed; it does not prove untested behavior is correct.

Rush also imports test-quality evidence that your project has already produced.
Pass the report file itself as `PATH`; these commands do not discover a report
inside a directory or launch a runner:

| Command | Accepted local evidence | What Rush does not do |
|---|---|---|
| `coverage REPORT` | coverage.py JSON, LCOV, or Cobertura XML | run tests or coverage tools |
| `pbt REPORT` | seeded property-test JSON | execute property tests |
| `flaky REPORT` | JUnit XML with duplicate-case evidence | repeat tests |
| `contract REPORT` | Pact summary JSON | contact a provider or broker |
| `snapshot REPORT` | comparison JSON | accept, write, or update a baseline |
| `mutation REPORT` | mutation summary JSON | run a mutation engine |
| `fuzz REPORT` | seeded fuzz summary JSON | build or start a fuzzer |
| `load REPORT` | load summary JSON | send traffic to a target |

For example, `rush coverage coverage.xml --json` imports an existing Cobertura
report. A missing, malformed, or out-of-project report produces a structured
`skipped` or `error` result; it is not a clean test result. `visual` remains a
guarded placeholder, and no browser or baseline-changing behavior is available
through these commands. Read each JSON summary and see [Advanced checks](advanced-checks.md).
