# Engines

Rush discovers external engine binaries on `PATH`; it does not bundle, install,
or download them. A missing executable returns a canonical `skipped` result.

Representative engines include Ruff/ESLint for linting, pytest/Vitest for tests,
mypy/tsc for type checking, gitleaks/cdxgen for supply chain analysis, and
optional language-native CLIs selected from project markers. Install hints are
available through the canonical `ENGINE_SPECS` catalog.

Experimental semantic drift requires an explicitly configured local target and
both browser and slow-run permission; see [SEMANTIC_DRIFT.md](SEMANTIC_DRIFT.md).
