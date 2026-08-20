# Configuration Schema Specification (`rush.toml`)

Rush uses a typed TOML configuration model defined via Python dataclasses in `src/rush/config.py`. Configuration is discovery-driven, bounded by the repository root, and validated against the canonical catalog of all 36 tools.

---

## 1. Schema Structure

```toml
# Root settings
log_level = "warn" # debug | info | warn | error

# Project path boundaries
[project]
src = ["src", "lib"]
test = ["tests", "test"]
exclude = ["**/.venv/**", "**/node_modules/**", "**/dist/**", "**/build/**"]

# Heuristic review configuration
[review]
max_file_lines = 400
use_graft = false
scaffold_markers = ["TODO", "FIXME", "HACK", "XXX"]
source_policy_exclude = ["tests/**", "fixtures/**"]
fail_on = []

# Tool-specific engine overrides
[tools.lint]
engine_args = ["--select", "E,F,W,I"]
check = true

[tools.format]
engine_args = []
check = true

[tools.security]
engine_args = ["--severity", "high,critical"]
check = true

[tools.ai-eval]
engine_args = []
check = true
```

---

## 2. Table Validation & Precedence Rules

1. **Exact Tool Matching**: Every `[tools.NAME]` table header must match one of the 34 valid tool names in `rush.catalog.TOOL_SPECS`. Any unrecognized tool name raises `RushConfigError`.
2. **Precedence Hierarchy**:
   ```text
   Built-in Defaults -> Nearest rush.toml (upward walk to .git root) -> Explicit CLI Arguments
   ```
3. **Safety Isolation**: Rush stops walking upward upon reaching the `.git` directory boundary, preventing accidental inheritance of parent directory configuration.

See [Configuration Reference](reference/configuration-reference.md) and [Configuration Cookbook](reference/configuration-cookbook.md).
