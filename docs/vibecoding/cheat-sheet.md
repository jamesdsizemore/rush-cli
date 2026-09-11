# Vibecoder Cheat Sheet & Golden Prompts

Commands assume the editable source checkout and run through `uv`. Treat returned execution evidence literally; timing and completeness depend on project and installed engines.

---

## ⚡ The Essential Command Quick Reference

| Command | When to Run It | What it Does in Plain English |
|---|---|---|
| `uv run rush watch .` | During editing | Triggers configured checks after file changes. |
| `uv run rush check . --json` | During development | Returns child results from current check suite. |
| [`uv run rush fix . --dry-run --force`](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) | Before remediation | Non-mutating Ruff preview; apply requires `--allow-artifact-write`. |
| `uv run rush test . --json` | After writing features | Runs applicable configured test engines. |
| `uv run rush tdd . --json` | After an AI generation | Returns current deterministic TDD evidence. |
| `uv run rush slop . --json` | Code review pass | Reports current deterministic noise heuristics. |
| `uv run rush codegraph slice "<fn>"` | Before prompting | Requests current symbol slice. |
| `uv run rush score compute` | Before opening a PR | Computes current repository score inputs. |
| `uv run rush dashboard --help` | UI status | Shows current prototype options; Phase 66 owns completion. |

---

## 🤖 Golden Prompt Templates for Your AI Assistant

Copy and paste these prompt templates directly into **Cursor, Claude Code, Cline, Windsurf, or ChatGPT**:

### 1. The "Clean Feature" Prompt (Best for new modules)
```text
Implement [FEATURE NAME].
Requirements:
1. Write clean, idiomatic code with complete implementations (no placeholder stubs or empty pass statements).
2. Add comprehensive unit tests in the appropriate tests directory.
3. Keep docstrings lean and avoid obvious inline comment narration.
4. Verify your work by running `rush check .` and `rush tdd .`.
```

---

### 2. The "Refactor & Slim Down" Prompt (Best for cleaning up messy code)
```text
Refactor [TARGET FUNCTION / FILE] to improve readability and reduce complexity.
Requirements:
1. Preserve all existing behaviors and test contracts.
2. Run `rush codegraph slice "[FUNCTION]"` first to review the exact implementation.
3. Run `rush check .` and `rush test .` to verify that all tests pass 100% green.
```

---

### 3. The "Bug Hunt" Prompt (Best for fixing a tricky error)
```text
We have a bug in [DESCRIPTION OR ERROR TRACE].
1. Identify the root cause without modifying unrelated files.
2. Add a failing regression test that reproduces the bug.
3. Apply the fix so that `rush test .` passes cleanly.
4. Run project formatter checks; use `rush fix` apply only with `--allow-artifact-write`.
```

---

### 4. The "Pre-PR Polish" Prompt (Best before committing)
```text
Perform a final pre-PR quality sweep on this repository:
1. Run `rush slop .` and purge any redundant AI filler comments or dead stubs.
2. Run formatter checks and apply reviewed changes manually.
3. Run `rush gate .` to ensure all quality gates pass.
4. Run `uv run rush score compute` and report its returned score evidence.
```

---

## 🎯 Pro-Tips for Maximum Vibe Velocity

1. **Keep `rush watch .` running in a split terminal**: You will get real-time feedback without having to switch windows or type commands manually.
2. **Never paste full 2,000-line files**: Use `rush codegraph slice "<symbol>"` or `rush token outline <file>` to give your model exact, high-density context.
3. **Protect Git state**: [P64-01 dry run](../phase-plans/phase-64-implementation-evidence.md#p64-01--preserve-checkoutindex-during-fixes-f01) preserves it; P64-04 patch-sandbox restoration remains planned.
