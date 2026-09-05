# Rush Configuration Overview

## Provider continuation has no persistent configuration

Rush does not store provider credentials, executable paths, OAuth profiles, endpoint URLs, or network grants in `rush.toml`. Each resume invocation supplies its own explicit `--allow-network`; installed CLI authentication stays owned by the CLI. `9router_cli` reads `RUSH_9ROUTER_API_KEY` only from the invoking process and passes it only to its Codex child; it has no `rush.toml` setting and no Rush-selected model.

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

## Phase 50a Quality & Security Suite Tool Configuration

```toml
[tools.error-catalog]
operation = "audit"
export_docs = "docs/ERROR_CATALOG.md"
output_module = "src/rush/errors.py"

[tools.license-matrix]
project_license = "Apache-2.0"
allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"]
export_path = "reports/licenses.json"

[tools.iam-audit]
export_path = "reports/iam-policy.json"
```

## Phase 50b/50c Flagship Tool Configuration

```toml
[tools.attest]
target_artifact = "dist/app-0.1.0-py3-none-any.whl"
export_path = "dist/app-0.1.0.intoto.json"

[tools.license-matrix]
project_license = "Apache-2.0"
allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"]
export_path = "reports/licenses.json"

[tools.iam-audit]
export_path = "reports/iam-policy.json"

[tools.dead-asset]
operation = "audit"
export_manifest = "reports/dead-assets.json"

[tools.pr-synthesize]
base_ref = "main"
export_card = "reports/pr-card.md"

[tools.prompt-eval]
pass_rate_threshold = 1.0
max_tokens = 50000
max_cost = 0.50

[tools.error-catalog]
operation = "audit"
export_docs = "docs/ERROR_CATALOG.md"
output_module = "src/rush/errors.py"

[tools.mem-profile]
mode = "static"

[tools.cold-start]
mode = "static"
threshold_ms = 50.0

[tools.media-opt]
operation = "audit"

[tools.offline-review]
model_path = "models/reviewer.onnx"

[tools.tui-diff]
target_ref = "HEAD"

[tools.benchmark]
metric = "duration_ms"
threshold_pct = 10.0
```

### Plugin Configuration & Secret References (Phase 56)
In `rush.toml`, configure plugins under `[plugins.<name>]`:
```toml
[plugins.custom_scanner]
command = "python scan.py"
timeout_seconds = 30.0
patterns = ["*.py", "*.ts"]
description = "Custom security scanner"
channel_type = "stdin" # "descriptor", "stdin", "provider"
secret_refs = ["secret:API_KEY"]
allowed_env = ["RUSH_PROJECT_ROOT"]
```
Literal secrets are forbidden and will be rejected at parse time.

## Invocation Context & Cache Configuration (Phase 57)

Configuration digests (`effective_config_digest`) are derived from normalized tool configuration tables. Modifications to tool settings invalidate cached results deterministically without relying on ad-hoc salt defaults.
