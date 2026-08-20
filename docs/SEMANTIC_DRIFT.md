# Semantic-drift detection

`rush semantic-drift <path>` is a correctness-analysis surface for browser locator, accessibility, and DOM drift detection.

## Safety contract

- It is **skipped by default** without explicit permissions.
- Both `--allow-browser` and `--allow-slow` are required to execute local analysis.
- Rush runs Playwright and axe-core in headless mode with detached process boundaries (`stdin=DEVNULL`, process kill on timeout).
- Without a configured local .NET or Playwright target, the enabled path returns a structured `skipped` result with an installation/configuration hint.

Normal CI uses parser and safety contracts; it never requires a browser unless explicitly authorized.
