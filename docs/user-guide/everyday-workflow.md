# The Everyday Developer Workflow

How does Rush fit into your actual day-to-day coding routine?

Whether you are sipping your morning coffee while fixing a small typo or pairing with an autonomous AI assistant to build a massive new subsystem, Rush is designed to give you continuous, lightning-fast feedback without breaking your flow.

Here is the narrative of a typical, productive day using Rush.

---

## 1. Starting Your Day: Checking the Ground Beneath You

Before you begin editing code on a new branch, it is always a good idea to ensure that your environment is clean and that the repository's baseline is healthy.

```bash
rush check .
```

### What happens:
In less than a second, Rush runs a rapid health check across your project:
- **Linting**: Did anyone leave syntax mistakes or unused imports behind?
- **Formatting**: Is all the code consistently formatted?
- **Type Checking**: Do all function signatures and data types match up?

If everything passes, you get a clean green bill of health and know that you are starting from a rock-solid foundation.

---

## 2. While You Code: Real-Time Feedback with Live Watcher

As you write functions, rename variables, or add new files, running commands manually every two minutes can get tiring. Instead, let Rush watch your back automatically:

```bash
rush watch .
```

### What this feels like:
Whenever you press `Ctrl+S` (or `Cmd+S`) in your editor, Rush instantly detects the saved file, waits 300 milliseconds so your editor finishes writing, and re-evaluates only the files you touched. 

If you make a typo or break a type signature, you’ll see the warning in your terminal before you even switch windows.

---

## 3. Cleaning Up the Mess: Automated Formatting with `rush fix`

We’ve all been there: you just finished writing a complex algorithm, but your indentation is messy, your quote styles are inconsistent, and you have four unused imports at the top of the file.

Instead of spending 15 minutes manually formatting your code line by line, let Rush handle it:

```bash
# Preview the cleanups without touching disk
rush fix . --dry-run

# Apply the safe fixes automatically
rush fix .
```

Rush safely coordinates Ruff, Prettier, ESLint, and Biome to format your files, clean unused imports, and tidy up whitespace—strictly confined within your repository boundary.

---

## 4. Testing Your Changes: Verifying Behavior

Code that looks clean must also work correctly. Rush makes running tests straightforward:

```bash
rush test .
```

- If you work in Python, Rush invokes `pytest`.
- If you work in TypeScript or JavaScript, Rush invokes `Vitest` or `Jest`.
- If your tests pass, you get a clear summary of how many tests ran and how fast they completed.
- If a test fails, Rush isolates the exact assertion error and stack trace so you can jump straight to the fix.

---

## 5. Before You Commit: The Pre-Commit Intelligence Guard

When you are ready to stage and commit your code, Rush provides a sub-second pre-commit check that catches common traps:

```bash
rush hook run
```

### What this catches in <300ms:
- Leftover merge conflict markers (`<<<<<<< HEAD`).
- Accidental secret leaks (API keys or passwords in staged files).
- Trojan Source Unicode vulnerabilities (invisible characters that look harmless in editors but execute maliciously).

---

## 6. Ready for Review: Generating Pull Request Artifacts

Before opening a pull request, you can calculate an objective quality scorecard to include in your PR description:

```bash
# Compute repository health grade (A+ to F)
rush score compute

# Generate an interactive visual dashboard you can inspect locally
rush dashboard .
```

Now you can submit your pull request knowing that every test passes, every file is formatted, and your code meets the highest quality standards.

---

## Summary of Everyday Commands

| When You Want To... | Run This Command | Why It's Great |
|---|---|---|
| Run a fast 1-second sanity check | `rush check .` | Instant feedback on linting, formatting, and types. |
| Auto-check code as you save | `rush watch .` | Zero-effort live background monitoring. |
| Auto-clean formatting and imports | `rush fix .` | Fixes formatting headaches in one keystroke. |
| Run all unit and integration tests | `rush test .` | Confirms that your logic works as expected. |
| Run pre-commit safety checks | `rush hook run` | Prevents bad commits from ever reaching Git history. |
| Open an interactive web dashboard | `rush dashboard .` | Visual report with charts and finding breakdowns. |

---

## Next Steps

- Learn more about linters and typecheckers in [Checking Your Code](checking-code.md).
- Discover how to pair safely with AI assistants in [Pair Programming with AI Agents](working-with-ai-agents.md).

## Everyday Workflow with Session & Ship Tools (Phases 41–43)
1. Start task: `rush session restore <name>` (or initialize with `rush session save <name>`).
2. Verify grounding during development: `rush hallu-guard`.
3. Check release gate before shipping: `rush ship gate`.

## Daily Blast Radius & Gain Checks
1. Check impact: `rush blast-radius --path <file>`
2. Monitor savings: `rush context gain`
3. Verify architecture: `rush arch-guard`



## Testing & API Validation
1. Heal flaky tests: `rush test-heal --target tests/test_api.py`
2. Verify contracts: `rush api-diff --base main`



## Database & Code Quality Checks
1. Check database drift: `rush db-drift`
2. Simplify complex code: `rush simplify --file src/app.py`
3. Synthesize type guards: `rush strictify --file src/app.py`

