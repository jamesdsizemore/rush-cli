# Phase 17 implementation ledger — UI/UX, Visual Regression & Web Asset Optimization

Scope:
- Implement engines for multi-viewport responsive visual testing, Storybook component diffing, CSS architecture linting, and web asset/font compression:
  - `LostPixelEngine` (`src/rush/engines/lost_pixel.py`): Visual regression testing for Storybook, Next.js, and Ladle.
  - `BackstopEngine` (`src/rush/engines/backstop.py`): Multi-viewport responsive visual regression tester.
  - `StylelintEngine` (`src/rush/engines/stylelint.py`): Modern CSS/SCSS/Less and CSS-in-JS linter.
  - `A11ywatchEngine` (`src/rush/engines/a11ywatch.py`): Multi-page web accessibility crawler.
  - `SquooshEngine` (`src/rush/engines/squoosh.py`): Next-generation WebP/AVIF image optimizer.
  - `CriticalEngine` (`src/rush/engines/critical.py`): Above-the-fold CSS extraction and inlining engine.
  - `FontSpiderEngine` (`src/rush/engines/font_spider.py`): Web font compressor and glyph profiler.
- Reference test suites in `tests/test_lost_pixel_reference.py`, `tests/test_backstop_reference.py`, `tests/test_stylelint_reference.py`, `tests/test_a11ywatch_reference.py`, `tests/test_squoosh_reference.py`, `tests/test_critical_reference.py`, and `tests/test_font_spider_reference.py`.
- Registered engines in `src/rush/catalog.py` and `src/rush/engines/__init__.py`.

## Verification Evidence
- Full pytest suite passing (394 passed, 7 skipped).
- Ruff linter & formatter clean.
