# Configuration Subsystem Development Guide

## Continuity is intentionally not configuration

Do not add a `rush.toml` flag that grants session writes. The existing invocation-scoped `ExecutionPermissions(cache_write=True)` contract is the authorization boundary and is tested as denied by default.

This guide explains how configuration loading, dataclass parsing, discovery boundaries, and tool catalog validation are implemented in `src/rush/config.py`.

---

## 1. Architecture of Configuration Loading

```text
Target Path (file or directory)
       │
       ▼
Walk Upward (find nearest rush.toml)
       │
       ├── Found rush.toml -> Parse and Validate against TOOL_SPECS
       │
       └── Hit .git boundary or root -> Return RushConfig() defaults
```

---

## 2. Configuration Data Models (`src/rush/config.py`)

All configuration structures are defined as frozen dataclasses:

```python
@dataclass(frozen=True)
class ProjectConfig:
    src: tuple[str, ...] = ("src", "lib")
    test: tuple[str, ...] = ("tests", "test")
    exclude: tuple[str, ...] = ("**/.venv/**", "**/node_modules/**")

@dataclass(frozen=True)
class ReviewConfig:
    max_file_lines: int = 400
    use_graft: bool = False
    scaffold_markers: tuple[str, ...] = ("TODO", "FIXME", "HACK")
    source_policy_exclude: tuple[str, ...] = ("tests/**", "fixtures/**")
    fail_on: tuple[str, ...] = ()

@dataclass(frozen=True)
class ToolOverrideConfig:
    engine_args: tuple[str, ...] = ()
    check: bool = True

@dataclass(frozen=True)
class RushConfig:
    log_level: str = "warn"
    project: ProjectConfig = field(default_factory=ProjectConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    tools: dict[str, ToolOverrideConfig] = field(default_factory=dict)
```

---

## 3. Adding New Configuration Fields

When adding a configuration field:
1. **Define Field**: Add to the respective `@dataclass(frozen=True)` in `src/rush/config.py`.
2. **Parse in `_parse()`**: Validate value types strictly. Raise `RushConfigError` for malformed types.
3. **Validate Tool Tables**: Validate that any `[tools.NAME]` corresponds to a key in `TOOL_SPECS`.
4. **Unit Tests**: Add tests in `tests/test_config.py` covering:
   - Default value initialization
   - Valid TOML parsing
   - Unknown tool table rejection
   - Git boundary stopping behavior
5. **Documentation**: Update `docs/reference/configuration-reference.md`, `docs/reference/configuration-cookbook.md`, and `docs/CONFIG_SCHEMA.md`.

See [Configuration Reference](../reference/configuration-reference.md).
