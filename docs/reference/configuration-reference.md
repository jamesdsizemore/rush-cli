# Configuration reference

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

`NAME` must exactly match one of the 33 catalog tool names. Unknown names raise `RushConfigError`. `engine_args` and `check` are parsed for every tool, but the verified direct consumer is lint's engine arguments; `check` is not a universal policy switch. `rush capabilities` reports a configured state when it reads an allowed local table; configuration does not run, install, or version-probe an engine. Prefer CLI `format --check` where supported.

## Validation behavior

Malformed TOML, unknown log levels, wrong value types, and unknown tool names fail configuration loading. Rush does not merge multiple files: nearest discovered file wins.

See [Configuration cookbook](configuration-cookbook.md) and [developer configuration guide](../developer/configuration-development.md).
