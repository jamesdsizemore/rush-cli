# Migration & Version Upgrade Guide

This guide helps teams migrate from direct standalone tool usage to Rush, or upgrade between Rush versions across all 19 phases.

---

## 1. Migrating from Direct CLI Tools to Rush

If your repository currently runs multiple disjointed linters, security scanners, and test tools in ad-hoc shell scripts:

### Step 1: Install Rush
```bash
uv tool install rush-cli
# Or install in your project development environment
uv add --dev rush-cli
```

### Step 2: Replace Ad-Hoc Scripts with Unified Commands
- Replace `ruff check` + `eslint` -> `rush lint .`
- Replace `ruff format --check` + `prettier --check` -> `rush format . --check`
- Replace `pip-audit` + `npm audit` + `trivy` -> `rush security .`
- Replace `gitleaks` + `trufflehog` -> `rush secrets .`
- Replace `pytest` + `vitest` -> `rush test .`

### Step 3: Retain Engine-Specific Configs
Rush uses your existing `pyproject.toml`, `eslint.config.js`, `.spectral.yaml`, and `hadolint.yaml` files. You do **not** need to discard your existing tool configurations.

---

## 2. Upgrading from Rush v0.1 to v0.2+

1. **ToolResult Schema Evolution**:
   - `duration` is now `duration_ms` (integer milliseconds).
   - `version` is now `engine_version` (string or null).
   - Optional extensions: `metrics`, `artifacts`, `metadata.execution`.
2. **Explicit Permissions Required**:
   - In v0.1, advanced tools were non-executing placeholders. In v0.2+, tools can execute live runners under explicit permission flags (e.g. `--allow-slow`, `--allow-network`, `--allow-browser`).
3. **Configuration Schema**:
   - `[tools.NAME]` sections are strictly validated against the 34 catalog tools in `src/rush/catalog.py`.

See [Known Issues](KNOWN_ISSUES.md) and [Result Reference](reference/result-reference.md).
