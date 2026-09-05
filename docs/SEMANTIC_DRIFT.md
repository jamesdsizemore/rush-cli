# Semantic-drift detection

`rush semantic-drift <path>` is a correctness-analysis surface for browser locator, accessibility, and DOM drift detection.

## Safety contract

- It is **skipped by default** without explicit permissions.
- Both `--allow-browser` and `--allow-slow` are required to execute local analysis.
- Rush runs Playwright and axe-core in headless mode with detached process boundaries (`stdin=DEVNULL`, process kill on timeout).
- Without a configured local .NET or Playwright target, the enabled path returns a structured `skipped` result with an installation/configuration hint.

Normal CI uses parser and safety contracts; it never requires a browser unless explicitly authorized.

### Phase 56: Plugin Trust & Execution Semantic Alignment
- **Reconciliation**: Demoted repository `.rush/trust.json` from authority to non-authorizing evidence; established user-owned ledger `~/.rush/plugin_trust_ledger.json` via `rush.io.AtomicFile` and `rush.io.PhysicalRoot`.
- **Closure Discovery**: Replaced single-file SHA-256 checks with complete transitive closure manifest.
- **TOCTOU Elimination**: Replaced in-place workspace execution with immutable byte snapshots.
- **Secret Exposure**: Replaced environment variable leakage with protected descriptor/stdin channels.
- **Bypass Removal**: Deprecated `loader.execute_plugin()` and removed `allow_untrusted` flag.

## Reconciliation of Invocation Semantic Drift (Phase 57)

Phase 57 resolved seven core semantic drifts: transport divergence, scope widening, TypeError retries, public route drift, cache key incompleteness, misleading LLM labeling, and dual-transport parity deficits.
