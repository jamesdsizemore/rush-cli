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

See [Versioning Policy](../VERSIONING.md) and [Release Process](../developer/release-process.md).
