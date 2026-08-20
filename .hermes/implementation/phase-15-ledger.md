# Phase 15 implementation ledger — Modern Web Standards, Accessibility & Safe DAST

Scope:
- Implement engines for automated WCAG accessibility auditing, W3C HTML validation, Core Web Vitals profiling, dead route crawling, and safe DAST vulnerability scanning:
  - `Pa11yEngine` (`src/rush/engines/pa11y.py`): Automated WCAG 2.1 AA/AAA accessibility testing engine.
  - `HtmlValidateEngine` (`src/rush/engines/html_validate.py`): Strict W3C HTML validator.
  - `LighthouseEngine` (`src/rush/engines/lighthouse.py`): Headless Core Web Vitals, performance, and SEO auditor.
  - `ZapEngine` (`src/rush/engines/zap.py`): Dynamic Application Security Testing (DAST) for local web services.
  - `DeadfinderEngine` (`src/rush/engines/deadfinder.py`): SPA web route crawler detecting 404s and broken links.
  - `BlcEngine` (`src/rush/engines/blc.py`): Recursive internal anchor tag and redirect validator.
  - `PagespeedEngine` (`src/rush/engines/pagespeed.py`): Real-world web performance auditor.
- Reference test suites in `tests/test_pa11y_reference.py`, `tests/test_html_validate_reference.py`, `tests/test_lighthouse_reference.py`, `tests/test_zap_reference.py`, `tests/test_deadfinder_reference.py`, `tests/test_blc_reference.py`, and `tests/test_pagespeed_reference.py`.
- Registered engines in `src/rush/catalog.py` and `src/rush/engines/__init__.py`.

## Verification Evidence
- Full pytest suite passing (394 passed, 7 skipped).
- Ruff linter & formatter clean.
