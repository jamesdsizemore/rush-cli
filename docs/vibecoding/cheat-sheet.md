# Vibecoder Cheat Sheet & Golden Prompts

Keep this cheat sheet handy during your coding sessions. Below are the essential commands and copy-paste prompt templates to make any AI coding assistant 10x faster, cleaner, and more reliable.

---

## ⚡ The Essential Command Quick Reference

| Command | When to Run It | What it Does in Plain English |
|---|---|---|
| `rush watch .` | Start of coding session | Watches files in the background and auto-evaluates on save. |
| `rush check .` | During development | Runs linting, formatting, and type checks together (<0.5s). |
| `rush fix .` | Whenever code looks messy | Auto-formats code and cleans unused imports across all files. |
| `rush test .` | After writing features | Executes unit and integration test suites. |
| `rush tdd .` | After an AI generation | Verifies that the AI actually wrote tests for the new code. |
| `rush slop .` | Code review pass | Flags redundant AI comments and empty placeholder stubs. |
| `rush codegraph slice "<fn>"` | Before prompting | Slices out just the target function (saves 90% tokens). |
| `rush score compute` | Before opening a PR | Computes 0–100% repository health grade (A+ to F). |
| `rush dashboard .` | Visual inspection | Opens an interactive local web dashboard on `127.0.0.1`. |

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
4. Run `rush fix .` to ensure formatting is spotless.
```

---

### 4. The "Pre-PR Polish" Prompt (Best before committing)
```text
Perform a final pre-PR quality sweep on this repository:
1. Run `rush slop .` and purge any redundant AI filler comments or dead stubs.
2. Run `rush fix .` to standardize formatting and clean imports.
3. Run `rush gate .` to ensure all quality gates pass.
4. Run `rush score pr-card` and output the summary card for our pull request.
```

---

## 🎯 Pro-Tips for Maximum Vibe Velocity

1. **Keep `rush watch .` running in a split terminal**: You will get real-time feedback without having to switch windows or type commands manually.
2. **Never paste full 2,000-line files**: Use `rush codegraph slice "<symbol>"` or `rush token outline <file>` to give your model exact, high-density context.
3. **Trust `rush fix .`**: Don't waste time hand-formatting brackets or organizing imports. Let Rush handle the busywork so you can focus on building amazing products!
