# Understanding Rush Results

When you run a command in Rush, you receive a clear, structured summary of what happened. This guide explains how to read Rush findings, what each status means, and how exit codes work when automating Rush in scripts or CI pipelines.

---

## 1. The Anatomy of a Rush Result

Whenever Rush evaluates a tool, it outputs a consistent, clean block:

```text
[WARN] lint [ruff]: 2 issue(s) (120ms)
  src/auth/jwt.py:42:10: F401 `datetime` imported but unused
  src/api/routes.py:15:1: E501 Line too long (92 > 88 characters)
```

Each result includes:
1. **Status Tag** (`[OK]`, `[WARN]`, `[FAIL]`, `[SKIPPED]`, `[ERROR]`): Instant visual indicator of health.
2. **Tool Name & Engine** (`lint [ruff]`): Which tool ran and which underlying engine produced the findings.
3. **Summary Message**: Total count of findings or confirmation of success.
4. **Duration** (`120ms`): Exactly how fast the engine finished.
5. **Findings List**: Location (`path:line:col`), rule name (`F401`), and a helpful description of what was flagged.

---

## 2. What Each Status Means

| Status | Color | Meaning | What You Should Do |
|---|---|---|---|
| **`OK`** | Green | The check passed completely with zero issues. | No action required! |
| **`WARN`** | Yellow | Non-fatal advisory issues were found (like stylistic hints or heuristic code smells). | Review the lines. They won’t break your build, but fixing them keeps the codebase tidy. |
| **`FAIL`** | Red | A rule was broken (a linter error, a failing test, a type mismatch, or a security vulnerability). | Fix the indicated lines before merging your pull request. |
| **`SKIPPED`** | Gray | An optional engine is not installed on your system or requires explicit permission flags. | If you want that engine, install it (e.g. via `uv pip install` or `npm install -g`). Otherwise, you can safely ignore it. |
| **`ERROR`** | Red | The engine crashed, was given an invalid argument, or hit a timeout. | Read the error traceback or run `rush doctor .` to check your environment. |

---

## 3. The "Worst Status Wins" Rule

When you run a composite workflow suite like `rush check .` (which runs linting, formatting, and typechecking together), Rush evaluates all tools and reports a single, definitive overall status according to strict precedence:

$$\text{ERROR} > \text{FAIL} > \text{WARN} > \text{OK} > \text{SKIPPED}$$

- If **even one tool fails**, the entire suite status is marked as **`FAIL`**.
- If all tools pass cleanly but one has advisory warnings, the suite status is **`WARN`**.
- If every tool passes with zero issues, the suite status is **`OK`**.

---

## 4. Exit Codes for Scripts & CI

If you run Rush inside GitHub Actions, GitLab CI, or pre-commit scripts, Rush returns standard Unix exit codes:

- **Exit Code `0`**: `OK` or `SKIPPED`. (Success; no blocking issues found).
- **Exit Code `1`**: `WARN` or `FAIL`. (Issues detected that require developer attention).
- **Exit Code `2`**: `ERROR`. (Configuration error or process crash).

---

## 5. Machine-Readable JSON Output

If your script, dashboard, or AI coding assistant needs to consume Rush findings programmatically, simply append `--json` to any command:

```bash
rush lint . --json
```

Rush returns a clean, canonical JSON object:
```json
{
  "tool": "lint",
  "engine": "ruff",
  "engine_version": "0.6.9",
  "status": "fail",
  "duration_ms": 45,
  "summary": "ruff: 1 issue(s)",
  "findings": [
    {
      "path": "src/main.py",
      "line": 12,
      "column": 5,
      "rule": "F401",
      "severity": "fail",
      "message": "`os` imported but unused"
    }
  ]
}
```

---

## Next Steps

- Learn how to pair with AI coding assistants in [Pair Programming with AI Agents](working-with-ai-agents.md).
- Discover how to test your code in [Testing with Confidence](testing-confidence.md).
