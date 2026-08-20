# Phase 08 implementation ledger — Browser Runtime Evidence and Boundary Protection

Scope:
- Process Boundaries & Safety: stdio MCP transport is strictly isolated from browser subprocesses (`stdin=DEVNULL`, process kill on timeout).
- Permission Gates: `--allow-browser` required to launch browser engines (Playwright, Chromium/WebKit/Firefox), combined with `--allow-slow` for drift tests, and `--allow-artifact-write` for baseline mutation.
- Tools & Adapters:
  - `PlaywrightEngine` (`src/rush/engines/playwright.py`): E2E test runner with `--reporter=json`.
  - `AxeEngine` (`src/rush/engines/axe.py`): WCAG accessibility audits with JSON violations normalization.
  - `SemanticDriftTool` (`src/rush/tools/semantic_drift.py`): DOM/accessibility drift verification under `--allow-browser` and `--allow-slow`.
  - `E2eTool` (`src/rush/tools/e2e.py`): E2E test execution under `--allow-browser`.
  - `VisualTool` (`src/rush/tools/visual.py`): Visual comparison with baseline protection (`--accept` requires `--allow-artifact-write`).
- Reference Test Suites: `tests/test_playwright_reference.py`, `tests/test_axe_reference.py`, `tests/test_browser_evidence.py`.

## Verification Evidence

- All browser tests (`test_semantic_drift_requires_both_browser_and_slow_permissions`, `test_e2e_requires_browser_permission`, `test_visual_requires_accept_option_for_baselines`, etc.) passed.
- Full test suite: 294 passed, 7 skipped.
- Ruff clean: `ruff check src tests` and `ruff format --check src tests` passed.
- Graft graph updated and verified.
