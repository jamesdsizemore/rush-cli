# Contributor Coding Standards & Architecture Invariants

## Continuity standard

Any new session surface must call `SessionContinuityTool` and return `ToolResult`. Checkpoint writes require an explicit invocation permission and validation must reject a traversal-style checkpoint name before touching the filesystem.

This guide defines the architectural rules, coding conventions, type safety standards, and security requirements for writing code in Rush CLI.

---

## 1. Core Language & Type Safety

- **Python 3.12 Target**: Use modern Python 3.12 features (built-in generic syntax, `match` statements, union syntax `A | B`, typed dictionaries).
- **Strict Typing**: All function signatures and public classes must have complete type annotations. Use `TypedDict` for structured dictionary shapes like `ToolResult` and `Finding`.
- **Immutable Configurations**: Use `@dataclass(frozen=True)` for configuration models (`RushConfig`, `ExecutionPermissions`).

---

## 2. Layer Separation & Separation of Concerns

```text
Transport (cli.py / mcp.py)
       │ (Call ToolFn only; no direct engine execution)
       ▼
Tool Implementation (src/rush/tools/*.py)
       │ (Ecosystem routing, fallback heuristics, permission checking)
       ▼
Engine Adapters (src/rush/engines/*.py)
       │ (Discovery on PATH, CLI arg construction, subprocess isolation)
       ▼
Subprocess Execution (run_subprocess)
```

1. **Never Duplicate Logic in Transports**: `src/rush/cli.py` and `src/rush/mcp.py` must invoke the same underlying `ToolFn` objects.
2. **Subprocess Isolation**: External binaries must always be invoked through `run_subprocess()` with `stdin=subprocess.DEVNULL` and `shell=False`.
3. **Deterministic Aggregation**: When multiple engines run for a single tool (e.g. Ruff + ESLint for `rush lint`), statuses must resolve via `error > fail > warn > ok > skipped`, durations must sum, and findings must be coordinate-sorted.

---

## 3. Security & Redaction Standards

1. **Secret Masking**: Any finding or error message that contains high-entropy strings, passwords, or tokens must be redacted as `[REDACTED]`.
2. **Offline-First Defaults**: Engine adapters must never query external remote endpoints without explicit `--allow-network` permissions.
3. **No Stealth Installs**: If an engine is missing, return `status: "skipped"` with an install hint. Never invoke `pip install`, `npm install`, or `brew install` automatically.

---

## 4. Linting & Formatting Standards

- Code style is enforced by `ruff check src tests scripts` and `ruff format src tests scripts`.
- Code must pass with zero warnings or errors.

See [Contributor Onboarding](contributor-onboarding.md) and [Tool Development Guide](tool-development.md).
