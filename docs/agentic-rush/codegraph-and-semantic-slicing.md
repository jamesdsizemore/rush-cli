# CodeGraph & Semantic Slicing

When an AI agent is asked to fix a bug or add a parameter to a function, traditional tools force the agent to either run `grep` (which returns noisy, disconnected line snippets) or read the entire 2,000-line file into memory (which wastes tokens and risks context saturation).

Rush’s **CodeGraph Subsystem** (`rush codegraph`) builds an ultra-fast, local Code Property Graph (CPG) stored in an embedded SQLite database (`.rush/codegraph.db`), enabling sub-millisecond verbatim symbol slicing and caller graph traversal.

---

## 1. Verbatim Symbol Slicing

The `rush codegraph slice` command extracts the complete, line-numbered implementation of any class, function, method, or type definition across Python, TypeScript, JavaScript, Rust, and Go.

```bash
# Slice an exact function implementation
rush codegraph slice "calculate_total_risk"
```

### Output Example:
```python
# [src/rush/hotspots/risk_matrix.py:45-62]
45: def calculate_total_risk(churn_count: int, cyclomatic_complexity: int) -> float:
46:     """Compute composite defect risk score combining commit frequency and complexity."""
47:     if churn_count <= 0:
48:         return 0.0
49:     weight = 1.5 if cyclomatic_complexity > 10 else 1.0
50:     return round((churn_count * 0.6 + cyclomatic_complexity * 0.4) * weight, 2)
```

- **Line-Numbered & Verbatim**: The agent receives the exact line numbers needed to construct accurate unified diff patches.
- **Minimal Token Footprint**: Passes only the 15–30 relevant lines instead of thousands of lines of unrelated code.

---

## 2. Caller & Dependency Traversal

Before refactoring a symbol, an agent must know who calls it to avoid introducing breaking API changes.

```bash
# Find all upstream callers of a symbol
rush codegraph callers "AuthService.validate_token"

# Explore symbol definitions across the workspace
rush codegraph explore "UserSession"
```

### Caller Tree Output:
```text
Symbol: AuthService.validate_token
  ├── src/api/middleware.py:28 (AuthMiddleware.authenticate_request)
  ├── src/api/routes/users.py:114 (get_current_user_profile)
  └── src/api/routes/admin.py:42 (verify_admin_access)
```

---

## 3. Graft CLI & Local Fallbacks

Rush integrates natively with **Graft** (`@nanonets/graft`) when available on PATH, and provides a zero-dependency internal AST fallback when external tools are absent.

```bash
# Run review heuristics augmented with CodeGraph symbol awareness
rush review . --use-graft
```

---

## Next Steps

- Learn how to clean dead code and resolve parallel agent conflicts in [Codebase Hygiene & AST Merges](codebase-hygiene-and-ast-merging.md).
- Discover how to standardize rules across multiple AI coding assistants in [Agent Governance & Multi-IDE Rules](governance-and-multi-ide-rules.md).
