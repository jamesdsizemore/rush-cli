# The Everyday Developer Workflow

How does Rush fit into your actual day-to-day coding routine?

Whether you are sipping your morning coffee while fixing a small typo or pairing with an autonomous AI assistant to build a massive new subsystem, Rush is designed to give you continuous, lightning-fast feedback without breaking your flow.

Here is the narrative of a typical, productive day using Rush.

---

## 1. Starting Your Day: Checking the Ground Beneath You

Before you begin editing code on a new branch, it is always a good idea to ensure that your environment is clean and that the repository's baseline is healthy.

```bash
uv run rush check . --json
```

### What happens:
Rush runs its current fixed check suite across the project:
- **Linting**: Did anyone leave syntax mistakes or unused imports behind?
- **Formatting**: Is all the code consistently formatted?
- **Type Checking**: Do all function signatures and data types match up?

Inspect every child result. A `skipped` optional engine is non-execution evidence, so exit code alone does not prove every applicable check ran.

---

## 2. While You Code: Real-Time Feedback with Live Watcher

As you write functions, rename variables, or add new files, running commands manually every two minutes can get tiring. Instead, let Rush watch your back automatically:

```bash
uv run rush watch .
```

### What this feels like:
Rush watches for supported file changes and triggers the configured suite after its debounce interval. It does not prove only changed files were evaluated; inspect the returned tool results.

If you make a typo or break a type signature, you’ll see the warning in your terminal before you even switch windows.

---

## 3. Remediation safety boundary

We’ve all been there: you just finished writing a complex algorithm, but your indentation is messy, your quote styles are inconsistent, and you have four unused imports at the top of the file.

Current `rush fix` has unresolved checkout/index preservation defects. Inspect its options, but do not run it on valued work:

```bash
uv run rush fix --help
```

Apply findings manually until [Phase 64, P64-01](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-01--preserve-checkoutindex-during-fixes-f01) proves dry-run, success, failure, and cancellation preserve unrelated files and Git state.

---

## 4. Testing Your Changes: Verifying Behavior

Code that looks clean must also work correctly. Rush makes running tests straightforward:

```bash
uv run rush test . --json
```

- If you work in Python, Rush invokes `pytest`.
- If you work in TypeScript or JavaScript, Rush invokes `Vitest` or `Jest`.
- If your tests pass, you get a clear summary of how many tests ran and how fast they completed.
- If a test fails, Rush isolates the exact assertion error and stack trace so you can jump straight to the fix.

---

## 5. Ready for review

Before opening a pull request, you can calculate an objective quality scorecard to include in your PR description:

```bash
# Compute repository health grade (A+ to F)
uv run rush score compute

# Inspect current dashboard command and limits
uv run rush dashboard --help
```

Current dashboard browser/server integration is broken at this baseline, and persistent workflow remains planned in [Phase 66](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md). Use command JSON and executed checks as evidence.

---

## Summary of Everyday Commands

| When You Want To... | Run This Command | Why It's Great |
|---|---|---|
| Run current check suite | `uv run rush check . --json` | Shows child execution and skip evidence. |
| Trigger checks on file changes | `uv run rush watch .` | Runs configured suite after debounce. |
| Inspect remediation options | `uv run rush fix --help` | Avoid execution until P64-01 passes. |
| Run applicable project tests | `uv run rush test . --json` | Shows executed, failed, and skipped evidence. |
| Inspect dashboard options | `uv run rush dashboard --help` | Current UI limits; Phase 66 owns completion. |

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



## Multi-Agent & Traceability Workflow
1. Check requirements: `rush trace`
2. Reconcile branches: `rush swarm-merge`
3. Simulate CI: `rush simulate-ci`



## Security & Release Workflow
1. Check licenses: `rush license-matrix`
2. Clean dead assets: `rush dead-asset`
3. Generate PR card: `rush pr-synthesize`
4. Attest build: `rush attest`
