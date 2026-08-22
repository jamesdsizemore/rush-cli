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
rush review .
```

`rush review` is Rush’s built-in, lightning-fast heuristic engine. It requires zero configuration and zero external installations. It looks for:
- Forgotten `TODO`, `FIXME`, or `HACK` markers that shouldn't be merged to production.
- Giant functions (>100 lines) that should probably be broken down into smaller, testable units.
- Missing docstrings on public modules and API endpoints.

```bash
# Focus review on only the files you just changed:
rush review . --changed-file src/auth/login.py
```

---

## 2. Source Code Linting (`rush lint`)

```bash
rush lint .
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
rush format . --check

# Automatically format all files in place:
rush format .
```

Rush coordinates `Ruff format`, `Prettier`, and `Biome` to ensure your entire team shares identical formatting styles.

---

## 4. Static Type Checking (`rush typecheck`)

```bash
rush typecheck .
```

Type errors are some of the most common causes of runtime crashes in production (like trying to access `.name` on a variable that is actually `None` or `undefined`).

Rush coordinates:
- **`mypy`** for Python projects.
- **`tsc` (TypeScript Compiler)** for TypeScript and JavaScript projects.

---

## 5. Hunting Down AI Slop (`rush slop`)

```bash
rush slop .
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

`rush slop` analyzes comment-to-code ratios, identifies redundant AI boilerplate, and highlights empty function stubs before they clutter your repository.

---

## 6. Finding Dead Code & Unused Exports (`rush dead`)

```bash
rush dead .
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

