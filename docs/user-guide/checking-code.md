# Checking Your Code: Linters, Formatters, & Typecheckers

If you’ve ever wondered why software engineering teams use so many different static analysis tools, think of them as three distinct layers of proofreading:

1. **The Formatter (The Typographer)**: Ensures consistent spacing, quotes, line wraps, and indentation so code is easy to read.
2. **The Linter (The Grammar Checker)**: Catches syntax errors, unused variables, bad idioms, and subtle logic traps.
3. **The Typechecker (The Blueprint Validator)**: Checks that variables, function arguments, and return values fit together correctly like puzzle pieces.
4. **The Anti-Slop Filter (The AI Fluff Remover)**: Flags empty placeholder stubs, redundant AI-generated comments, and hallucinatory boilerplate.

Rush unites all four layers under simple, cohesive commands.

---

## 1. Quick Code Review Heuristics (`rush review`)

```bash
uv run rush review .
```

`rush review` is Rush’s built-in, lightning-fast heuristic engine. It requires zero configuration and zero external installations. It looks for:
- Forgotten `TODO`, `FIXME`, or `HACK` markers that shouldn't be merged to production.
- Giant functions (>100 lines) that should probably be broken down into smaller, testable units.
- Missing docstrings on public modules and API endpoints.

```bash
# Focus review on only the files you just changed:
uv run rush review . --changed-file src/auth/login.py
```

---

## 2. Source Code Linting (`rush lint`)

```bash
uv run rush lint .
```

When you run `rush lint`, Rush automatically detects the programming languages used in your project and runs the appropriate linters:
- **Python**: Invokes `Ruff` or `Flake8`.
- **JavaScript & TypeScript**: Invokes `ESLint` or `Biome`.
- **CSS / SCSS**: Invokes `Stylelint`.

If a linter spots an issue (like an undefined variable or an unhandled Promise), Rush gives you the exact file path, line number, column, and rule name so you can fix it immediately.

---

## 3. Formatting & Style Verification (`rush format`)

```bash
# Check if any files need formatting (without modifying them):
uv run rush format . --check

# Automatically format all files in place:
uv run rush format .
```

Rush coordinates `Ruff format`, `Prettier`, and `Biome` to ensure your entire team shares identical formatting styles.

---

## 4. Static Type Checking (`rush typecheck`)

```bash
uv run rush typecheck .
```

Type errors are some of the most common causes of runtime crashes in production (like trying to access `.name` on a variable that is actually `None` or `undefined`).

Rush coordinates:
- **`mypy`** for Python projects.
- **`pyrefly`** for Python projects, alongside `mypy` — required at minimum version 0.37.0 (an older or unrecognized version is skipped with an explanation); installed through this project's own `dev` extra (`pip install rush[dev]`), not bundled.
- **`tsc` (TypeScript Compiler)** for TypeScript and JavaScript projects.

### Choosing the Python interpreter environment

`--environment project|isolated` (MCP `environment`) picks which interpreter `mypy`/`pyrefly` analyze against:
- `project` uses the project's own `.venv` interpreter and requires `--allow-build` (starting that interpreter runs its own `.pth` code); without the grant, `project` is denied.
- `isolated` never starts a project-referenced interpreter.
- Omitting the flag prefers `project` and falls back to `isolated` automatically when the grant is missing or the `.venv` is absent/invalid.

The result's `analysis_environment` metadata records which one actually ran and why: `mode` (`project`, `isolated`, or `denied`), and on a non-default outcome, a `cause` such as `requested` (explicit `--environment isolated`), `project_environment_requires_allow_build` (project mode without the grant), `venv_missing`, `pyvenv_cfg_invalid`, or `interpreter_missing`.

### Scoping tsc to a specific config

`tsc` needs `--allow-cache-write` before it runs at all (including its own config discovery) — without it, the tsc child is `skipped` with `requires permission: --allow-cache-write`. Pass `--typecheck-config PATH` (MCP `typecheck_config`) to select an exact `tsconfig.json` (or a mypy/pyrefly config file) instead of Rush's automatic owning-config discovery; it must live inside the project's logical root and match the target engine's config file family. An invalid value is refused before any engine runs:
- `TYPECHECK_CONFIG_NOT_FOUND`: the path is not an existing regular file.
- `TYPECHECK_CONFIG_OUTSIDE_ROOT`: the path lies outside the project root.
- `TYPECHECK_CONFIG_INVALID`: the file is not a tsconfig (`.json`), mypy (`mypy.ini`, `.mypy.ini`, `setup.cfg`, `pyproject.toml`), or pyrefly (`pyrefly.toml`, `pyproject.toml`) config.
- `TYPECHECK_CONFIG_CONFLICT`: a freeform engine argument (`-p`, `--project`, `--config-file`, `--config`) already selects a different config.
- `TYPECHECK_CONFIG_REQUIRED`: automatic discovery could not find an owning tsconfig for the target (for example, a file under a solution config that no referenced project owns) — pass `--typecheck-config` explicitly.

A project `mypy` config that declares `plugins` needs `--allow-build` (plugins execute code); without it, the `mypy` child is `skipped` with `requires permission: --allow-build (project mypy plugins execute code)`. A project `pyrefly` config whose interpreter keys make `pyrefly` execute a program needs the same grant, skipping otherwise with `requires permission: --allow-build (project pyrefly interpreter config executes a program)`.

Each typecheck finding carries `extensions.scope`, in priority order: `configuration` (a config-diagnostic finding, path-less or from the config file itself), `requested` (the file you actually asked to check), `engine_library` (the engine's own bundled type stubs), or `dependency` (an imported module reached transitively — never an unrelated sibling file). Dependency findings are kept, not filtered out, so a bug in code you import still surfaces.

`tsc`'s project-reference resolution reports three additional error codes: `TSC_REFERENCE_CYCLE` (the referenced projects form a cycle), `TSC_AMBIGUOUS_OWNER` (two equally deep configs both own the target — pass `--typecheck-config` to choose one), and `TSC_CONFIG_DIAGNOSTICS` (the resolved tsconfig itself has configuration errors, such as a missing referenced project).

---

## 5. Hunting Down AI Slop (`rush slop`)

```bash
uv run rush slop .
```

When pairing with AI coding assistants, models often generate repetitive filler comments like:
```python
# In this function, we will meticulously calculate the user discount based on the age
def calculate_discount(age: int) -> float:
    # First, we check if age is greater than 65
    if age > 65:
        # Return 0.2
        return 0.2
```

`rush slop` analyzes comment-to-code ratios, identifies redundant AI boilerplate, and highlights empty function stubs before they clutter your repository. For Python files it prefers `aislop` when installed (falling back to `sloppylint` otherwise): aislop scans the target directory itself (a file target becomes its parent directory plus `--include`), and its findings report as `aislop/<engine>/<rule>` for every aislop engine that ran. The result is `error` only when aislop produces no JSON report at all; findings on their own are `warn` or `fail` depending on severity.

---

## 6. Finding Dead Code & Unused Exports (`rush dead`)

```bash
uv run rush dead .
```

Over time, projects accumulate helper functions, classes, and dependencies that are no longer used anywhere. `rush dead` runs tools like `Vulture` (for Python) and `Knip` (for TypeScript) to help you prune dead weight and keep your repository lean.

---

## Next Steps

- Learn how to interpret Rush results in [Understanding Rush Results](understanding-results.md).
- Discover how to check Markdown, SQL, and Dockerfiles in [Checking Project Files](checking-project-files.md).

## Code Grounding & Outline Checks (Phases 41–43)
* **AST Grounding**: Run `rush hallu-guard` to verify all imported modules are installed.
* **AST Outlining**: Run `rush token outline <path>` for compact symbol signatures.

## Context Packing & Blast Radius
* `rush context pack`: Assemble token-bounded prompts.
* `rush blast-radius`: Check affected routes and tests.



## API Diffing
* `rush api-diff`: Compare AST signatures against base branches.



## Database & Complexity Auditing
* `rush db-drift`: Verify model/migration alignment.
* `rush simplify`: Score cognitive complexity.



## Traceability & Flight Recorder
* `rush trace`: Requirement compliance.
* `rush flight-recorder`: Replay session events.



## License & IAM Auditing
* `rush license-matrix`: Classify dependency licenses.
* `rush iam-audit`: Generate cloud access policies.

## Finding Severities & Schema (Phase 54)
Every Rush tool returns structured findings with canonical severity levels:
- **`info`**: Informational notices, clean suggestions, or non-blocking tips.
- **`warning`**: Style inconsistencies, potential performance bottlenecks, or mild code smells.
- **`error`**: Syntax errors, security vulnerabilities, breaking type mismatches, or failed tests.

All outputs conform to the canonical `ToolResultV1` schema specification.
