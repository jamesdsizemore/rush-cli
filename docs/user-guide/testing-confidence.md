# Testing confidence

Start with the tests your project already has:

```bash
rush test .
```

Rush can route Python projects to pytest, JS/TS projects to Vitest, and Postman collections to Newman. A passing test run shows the executed suite passed; it does not prove untested behavior is correct.

Rush supports dual modes for test quality: importing existing local reports or executing engines under permission flags (`--allow-slow`, `--allow-network`, `--allow-browser`, `--allow-artifact-write`):

| Command | Accepted local evidence | Native execution engine | Required permission |
|---|---|---|---|
| `coverage REPORT` | coverage.py JSON, LCOV, Cobertura XML | pytest --cov / Diff-Cover | `--allow-slow` |
| `mutation REPORT` | Stryker / mutmut summary JSON | Stryker, Cosmic Ray, Infection, Pitest, Cargo-mutants | `--allow-slow` |
| `pbt REPORT` | seeded property-test JSON | Hypothesis | `--allow-slow` |
| `flaky REPORT` | JUnit XML with duplicate-case evidence | pytest-rerun | `--allow-slow` |
| `contract REPORT` | Pact summary JSON | Schemathesis, pact-verifier | `--allow-slow` |
| `snapshot REPORT` | comparison JSON | pytest-snapshot | `--allow-slow` (`--allow-artifact-write` for `--accept`) |
| `fuzz REPORT` | seeded fuzz summary JSON | Atheris | `--allow-slow` |
| `load REPORT` | load summary JSON | k6 | `--allow-network` |
| `e2e` | Playwright test suites | Playwright, Wait-On | `--allow-browser` |
| `visual` | visual diff / baselines | Lost Pixel, BackstopJS, Lighthouse, PageSpeed | `--allow-browser` & `--allow-slow` |

For example, `rush coverage coverage.xml --json` imports an existing Cobertura report. Read each JSON summary and see [Advanced checks](advanced-checks.md).
