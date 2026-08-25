# Configuration reference

## Provider resume is invocation-scoped

There is no configuration table for provider executable paths, profiles, credentials, endpoints, or persistent network permission. Authentication is inherited from the already configured user-owned CLI, and `--allow-network` is required per invocation.

## Continuity permissions

No `rush.toml` value enables checkpoint writes. Use `--allow-cache-write` only on a save invocation; MCP callers pass `allow_cache_write: true` for that individual call.

Rush configuration is optional. It discovers the nearest `rush.toml` while walking upward from the target and stops at the Git root or filesystem root.

## Precedence

```text
Built-in defaults -> nearest rush.toml -> explicit CLI arguments
```

Only behavior confirmed by implementation should drive policy. The parser accepts more fields than current tools consume.

## Root

```toml
log_level = "warn"
```

`log_level`: `debug`, `info`, `warn`, or `error`; default `warn`. `RUSH_LOG_LEVEL` supplies the CLI option default, and explicit `--log-level` wins for that invocation.

## `[project]`

```toml
[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]
```

All are string lists. Defaults are shown. These fields are parsed but current command routing generally uses the supplied path and built-in collectors; do not assume they redefine every scan until a tool has a verified consumer.

## `[review]`

```toml
[review]
max_file_lines = 400
fail_on = []
use_graft = false
scaffold_markers = []
source_policy_exclude = []
```

- `max_file_lines`: threshold for the deterministic file-size heuristic; implemented.
- `use_graft`: requests local Graft context when available; implemented.
- `scaffold_markers`: exact strings to report as configured unfinished markers; implemented.
- `source_policy_exclude`: relative glob patterns excluded from scaffold-marker checks; implemented.
- `fail_on`: parsed but not currently enforced by review status logic.

## `[tools.NAME]`

```toml
[tools.lint]
engine_args = ["--select", "E,F,W,I"]
check = true
```

`NAME` must exactly match one of the catalog tool names (e.g. `lint`, `format`, `test`, `security`, `tdd`, `slop`, `complexity`). Unknown names raise `RushConfigError`.

## `[plugins.NAME]` (Phase 28)

```toml
[plugins.custom-linter]
command = "python scripts/my_linter.py"
description = "Custom AST rule scanner"
file_extensions = [".py"]
```

Custom quality engine plugins defined in `rush.toml`. Requires repository trust authorization via `rush trust` (Control 6).

## `[dashboard]` (Phase 27)

```toml
[dashboard]
port = 8080
host = "127.0.0.1"
```

Configures default binding port and parameters for the local in-memory web dashboard.

## `[bundle]` (Phase 36)

```toml
[bundle]
max_gzip_bytes = 153600
forbidden_barrels = ["@mui/material", "lodash", "rxjs"]
```

Enforces frontend JavaScript chunk transfer budgets and blocks unoptimized barrel file imports.

## `[score.weights]` (Phase 40)

```toml
[score.weights]
type_safety = 0.20
test_coverage = 0.25
code_health = 0.20
security = 0.15
token_economy = 0.10
governance = 0.10
```

Customizes the relative weighting for the 6-pillar composite quality scorecard.

## `[guard]` (Phase 31)

```toml
[guard]
block_destructive_commands = true
max_subagent_depth = 3
confine_workspace_paths = true
```

Configures agent safety boundaries, destructive command interception, and tree depth constraints.

## Validation behavior

Malformed TOML, unknown log levels, wrong value types, and unknown tool names fail configuration loading. Rush does not merge multiple files: nearest discovered file wins. Validate anytime with `rush config check .`.

See [Configuration cookbook](configuration-cookbook.md) and [developer configuration guide](../developer/configuration-development.md).

