Current status: historical decision; The clean-room authorship policy remains required. Its absolute licensing and enterprise-compliance consequences are not certification evidence; current license analysis has a grouped-SPDX interpretation defect ([application review F18](../reports/phase-64-66-application-review.md)) scheduled in [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). Preserve the policy without treating analyzer output as proof of legal compliance.

# ADR-0044: Clean-Room Implementation of Codebase Indexing Algorithms

## Status
Accepted (v0.3.0 / Phase 41-50)

## Context
Various open-source tools provide useful indexing, search, or compression ideas, but some carry viral copyleft licenses (e.g., GPLv3/AGPLv3) that conflict with Rush's permissive MIT/Apache-2.0 distribution model.

## Decision
1. Enforce a strict **Clean-Room Implementation Policy**: Rush incorporates architectural principles and algorithmic concepts exclusively through clean-room reimplementations in pure Python 3.12.
2. Prohibit copying or vendoring external code under GPLv3/AGPLv3 licenses.
3. Implement all AST tree extraction, PageRank traversal, FTS5 lexical indexing, and diff compression from first principles using standard libraries and permissively licensed dependencies (`tree-sitter`, `tiktoken`, `sqlglot`, `rich`, `mcp`, `click`).

## Consequences
- **Positive**: Guarantees zero license contamination and complete intellectual property safety for commercial and enterprise users.
- **Negative**: Requires in-house authorship and testing of all indexing algorithms.
- **Safety**: Fully compliant with enterprise open-source governance.
