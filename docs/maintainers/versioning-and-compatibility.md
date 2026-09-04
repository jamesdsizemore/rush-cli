# Maintainer Versioning & Compatibility Contracts

Guidelines for maintaining backward compatibility across CLI commands, FastMCP registrations, configuration files, and ToolResult schemas.

---

## 1. Stable Compatibility Contracts

1. **CLI Commands and Arguments**: Command names (`rush lint`, `rush security`, `rush ai-eval`), options (`--json`, `--check`, `--allow-*`), and POSIX exit codes (0, 1, 2).
2. **FastMCP Registration Contracts**: Tool names (`rush_<name>`), parameter types, and docstrings.
3. **Canonical ToolResult**: The 8 required fields (`tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`).
4. **Configuration Syntax**: `rush.toml` schema and table names.

---

## 2. Breaking Change Deprecation Policy

If a breaking change is unavoidable:
1. Announce deprecation in minor release notes (`0.X.0`) with actionable migration guidance.
2. Maintain backward-compatible fallback for at least one minor release cycle.
3. Remove deprecated behavior only in the subsequent major version release.

---

## 3. Version Resolution & Package Identity Architecture (Phase 52)

- **Single Version Source**: All runtime modules must consume `rush.__version__`. Never hardcode static version literals (e.g. `"0.2.0"`, `"0.3.0"`) in headers, templates, or exporters.
- **Distribution Metadata Resolution**: `rush.__version__` resolves dynamically via `importlib.metadata.version("rush-cli")`. When running uninstalled, it falls back to `"0.3.0"`.
- **Strict Root Namespace**: All internal imports across `src/` and `tests/` must use canonical `rush` or relative imports. `src.rush` imports are strictly prohibited.

See [Versioning Policy](../VERSIONING.md) and [Release Process](../developer/release-process.md).
