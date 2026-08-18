# Experimental semantic-drift detection

`rush semantic-drift <path>` is an experimental correctness-analysis surface for
browser locator and self-healing drift.

## Safety contract

- It is **skipped by default**.
- Both `--allow-browser` and `--allow-slow` are required before any configured
  local analysis can be considered.
- Rush never starts a browser, invokes .NET, changes fixtures, accesses the
  network, or installs an engine by default.
- Without a configured local .NET or Playwright target, the enabled path also
  returns a structured `skipped` result with an installation/configuration hint.

The adapter accepts machine-readable local engine reports when a future
explicitly configured runner is enabled. Normal CI uses parser and safety
contracts only; it never requires a browser.
