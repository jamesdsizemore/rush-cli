# Rush Configuration Overview

## Session continuity permissions

`rush.toml` cannot grant session persistence. A caller must grant `--allow-cache-write` for each CLI save, or `allow_cache_write: true` for the corresponding MCP call; this prevents a repository configuration file from silently authorizing local writes.

Rush configuration is designed to be optional, lightweight, and local-first. Most repositories require zero configuration because Rush uses intelligent ecosystem discovery and sensible defaults across all 77 quality engines.

---

## 1. Quick Start

Create a `rush.toml` file at your repository root:

```toml
log_level = "warn"

[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]

[review]
max_file_lines = 400
use_graft = false
scaffold_markers = ["TODO", "FIXME", "HACK"]

[tools.lint]
check = true
```

---

## 2. Configuration Features

- **Automated Init (`rush init`)**: Automatically inspect your repository and write a tailored `rush.toml`.
- **Schema Validation (`rush config check`)**: Statically validates `rush.toml` against canonical schemas and tool catalogs.
- **Custom Plugins (`[plugins.<name>]`)**: Declare custom linter/analyzer script execution commands.
- **Local Dashboard (`[dashboard]`)**: Configure port and loopback parameters for the in-memory web dashboard.
- **Automatic Upward Discovery**: Rush walks upward from the target directory until it finds the nearest `rush.toml` file or reaches the `.git` boundary.
- **Strict Catalog Validation**: Every `[tools.<name>]` section is validated against `TOOL_SPECS` in `src/rush/catalog.py` at parse time. Typographical errors raise actionable configuration errors immediately.
- **Engine Arguments Pass-Through**: Pass specific flags to underlying linters (e.g. `engine_args = ["--select", "E,F,W,I"]`).
- **Observability with `rush capabilities`**: Inspect how Rush perceives your configuration and installed tools using `rush capabilities . --json`.

---

## 3. Related Documentation

- [Configuration Reference](reference/configuration-reference.md): Full field-by-field specification and type constraints.
- [Configuration Cookbook](reference/configuration-cookbook.md): Production configurations for Python, TypeScript, polyglot, and cloud-native repositories.
- [Configuration Schema](CONFIG_SCHEMA.md): Schema validation rules.

## Context Intelligence & Preferences Configuration (Phases 41–43)

```toml
[context_intel]
default_encoding = "cl100k_base"
enable_distillers = true
max_distilled_lines = 100

[context_intel.distillers]
pytest = true
cargo = true
ruff = true
vitest = true

[memory]
preferences_path = ".rush/preferences.json"
sessions_path = ".rush/sessions"
ccr_cache_path = ".rush/cache/ccr.db"
failures_db_path = ".rush/memory/failures.db"
invariants_path = ".rush/memory/invariants.json"
```
