# Configuration cookbook

These examples use only the current schema. Comments distinguish implemented effects from organizational documentation.

## Python application

```toml
log_level = "warn"
[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/build/**"]
[review]
max_file_lines = 500
scaffold_markers = ["IMPLEMENT_ME", "TEMPORARY_STUB"]
source_policy_exclude = ["tests/fixtures/**"]
[tools.lint]
engine_args = ["--select", "E,F,W,I"]
```

Review and lint consume the highlighted settings. Project lists are useful declarative intent but are not universal routing overrides today.

## TypeScript application

```toml
log_level = "info"
[project]
src = ["src", "scripts"]
test = ["test"]
exclude = ["**/node_modules/**", "**/dist/**"]
[review]
max_file_lines = 450
```

Rush still relies on `package.json`, source extensions, and engine configuration for JS/TS applicability.

## Multi-language repository

```toml
[project]
src = ["backend/src", "frontend/src"]
test = ["backend/tests", "frontend/test"]
exclude = ["**/.venv/**", "**/node_modules/**", "**/vendor/**"]
[review]
max_file_lines = 500
use_graft = false
```

Run commands at the common repository root; installed applicable engines aggregate deterministically.

## Monorepo

Prefer a `rush.toml` at each independent Git-root-bounded project when policies differ. Rush chooses the nearest file; it does not merge root and package configurations.

```toml
# repository-root rush.toml
[project]
src = ["packages"]
test = ["packages"]
exclude = ["**/node_modules/**", "**/dist/**", "**/generated/**"]
```

## Strict team review policy

```toml
log_level = "warn"
[review]
max_file_lines = 350
scaffold_markers = ["TODO(PROD)", "NOT_IMPLEMENTED", "pass  # stub"]
source_policy_exclude = ["tests/fixtures/**", "examples/**"]
```

`fail_on` is intentionally omitted because it is parsed but not enforced. Enforce required status in CI after JSON inspection.

## CI-oriented policy

```toml
log_level = "info"
[review]
max_file_lines = 400
use_graft = false
[tools.lint]
engine_args = []
```

Keep permission-sensitive actions out of unattended CI unless an explicit, implemented consent surface exists. Pin engines in CI setup rather than expecting Rush to install them.
