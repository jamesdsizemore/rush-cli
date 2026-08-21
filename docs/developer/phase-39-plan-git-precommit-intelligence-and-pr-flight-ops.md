# Phase 39 Implementation Plan: Git-Native Pre-Commit Intelligence, Branch Sanity & PR Flight Operations

> **Phase:** 39 of 40  
> **Milestone:** Flight Operations, Pre-Commit Intelligence & Branch Sanity  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.11.0  
> **ADR References:** [ADR-0019: Native Graft Semantic Slicing & Tree-Sitter AST Engine](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md), [ADR-0025: Polyglot Grammar Expansion via `tree-sitter-language-pack`](../adr/0025-polyglot-grammar-expansion.md)  
> **Pinned Dependencies:** `tree-sitter==0.24.0`, `tree-sitter-language-pack==0.4.0`, `mcp==1.28.1`

---

## 1. Objective & Scope

Autonomous coding agents frequently produce lazy, generic commit messages (`"fix bugs"`, `"update code"`), pollute repositories with dozens of abandoned feature branches, and submit massive 2,000-line Pull Requests that combine unrelated changes, overwhelming human code reviewers and CI pipelines.

Phase 39 introduces intelligent Git flight operations to ensure clean, structured development workflows:
1. **AST-Aware Conventional Commit Generator (`rush git-smart-commit`)**: Analyzes staged Tree-Sitter AST diffs (e.g. modified function signatures, newly exported interfaces) to construct structured Conventional Commit messages (`feat(auth): ...`, `fix(api): ...`) with zero generic placeholders.
2. **Autonomous Agent Pre-Flight Verifier (`rush git-preflight`)**: Multi-scanner orchestration gate that verifies linting, typechecking, tests, secret leaks, and doc parity before allowing a commit or push.
3. **PR Blast Radius & Micro-PR Split Guard (`rush git-pr-scope`)**: Enforces Pull Request size budgets (e.g. max 300 changed lines) and generates atomic branch-splitting plans when PRs become bloated.
4. **Stale Branch & Worktree Hygiene Pruner (`rush git-branch-hygiene`)**: Identifies merged, abandoned, or diverged feature branches and provides safe prune commands.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`graft` (AST Diff Slicing)**: Instead of sending 500 lines of raw git diffs to generate a commit message, `rush git-smart-commit` extracts only the modified AST symbol headers (e.g. `Modified function 'validate_token' -> Added parameter 'scope'`).
- **`rtk` (Pre-Flight Result Bundling)**: `rush git-preflight` bundles all scanner checks into a single concise PASS/FAIL summary table.
- **`context-mode` (Deterministic Split Manifest)**: `rush git-pr-scope` outputs structured patch manifests for atomic branch splitting.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/git/smart_commit.py` (New: AST diff analyzer and Conventional Commit generator)
- `src/rush/git/preflight.py` (New: Multi-scanner pre-commit and pre-push orchestration gate)
- `src/rush/git/pr_scope.py` (New: PR size budget enforcer and branch-split planner)
- `src/rush/git/branch_hygiene.py` (New: Stale and merged branch scanner)
- `src/rush/cli.py` (Modified: Register `rush git-smart-commit`, `rush git-preflight`, `rush git-pr-scope`, `rush git-branch-hygiene`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Catalog specifications)

### Test & Fixture Files
- `tests/test_git_smart_commit.py` (New: Conventional commit generation from AST diffs)
- `tests/test_git_preflight.py` (New: Pre-flight gate blocking on failing lint/tests)
- `tests/test_git_pr_scope.py` (New: PR line threshold checks and atomic split plans)
- `tests/test_git_branch_hygiene.py` (New: Merged vs active branch classification)
- `tests/fixtures/diffs/sample.patch` (New: Test diff fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_git_smart_commit.py
def test_smart_commit_generates_feat_for_new_function():
    diff = """
diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
+def verify_jwt(token: str) -> bool:
+    return True
"""
    msg = generate_conventional_commit_from_diff(diff, language="python")
    assert msg.startswith("feat(auth):")
    assert "verify_jwt" in msg

# tests/test_git_pr_scope.py
def test_pr_scope_flags_oversized_diff():
    # 500 lines diff
    diff_text = "\n".join([f"+ line_{i} = {i}" for i in range(500)])
    result = evaluate_pr_scope(diff_text=diff_text, max_lines=300)
    assert result.is_oversized is True
    assert len(result.recommended_split_branches) >= 2
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/git/smart_commit.py`, `src/rush/git/preflight.py`, `src/rush/git/pr_scope.py`, and `src/rush/git/branch_hygiene.py`.

### 4.3 REFACTOR Phase
Ensure Git commands execute with strict subprocess sandboxing, timeout guards (30s), and clean error handling when uncommitted files exist.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:55:00Z", "phase": 39, "tool": "rush_git_smart_commit", "event": "commit_msg_generated", "type": "feat", "scope": "auth", "ast_nodes_modified": 2}
{"timestamp": "2026-08-21T07:55:01Z", "phase": 39, "tool": "rush_git_preflight", "event": "preflight_completed", "passed_checks": 6, "failed_checks": 0, "status": "GREEN"}
{"timestamp": "2026-08-21T07:55:02Z", "phase": 39, "tool": "rush_git_pr_scope", "event": "pr_oversized", "lines_changed": 482, "limit": 300, "splits_suggested": 2}
```

---

## 6. Step-by-Step Task Specifications

### Task 39.1: AST Conventional Commit Engine (`src/rush/git/smart_commit.py`)
```python
from __future__ import annotations
from rush.tools.base import ToolResult

def generate_smart_commit_message(staged_only: bool = True) -> ToolResult:
    """Analyze staged Tree-Sitter AST diffs and generate structured Conventional Commit message."""
    ...
```

### Task 39.2: Agent Pre-Flight Orchestrator (`src/rush/git/preflight.py`)
Run all configured quality engines in parallel and enforce clean working trees before commits.

### Task 39.3: PR Scope & Split Guard (`src/rush/git/pr_scope.py`)
Audit proposed PR diff size and generate atomic branch split plans.

### Task 39.4: Stale Branch Hygiene Pruner (`src/rush/git/branch_hygiene.py`)
Audit local and remote branches against `main`/`master` to identify merged branches ready for pruning.

### Task 39.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Conventional Commit Standard**: Output messages must strictly conform to Conventional Commits 1.0.0 (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`).
2. **Branch Prune Safety**: Never delete unmerged branches without explicit `--force` flag.
3. **Doc Parity**: Synchronize and verify all `/docs` files.
