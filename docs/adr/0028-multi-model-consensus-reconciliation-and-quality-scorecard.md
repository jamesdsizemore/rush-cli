# ADR-0028: Multi-Model Consensus Reconciliation and Quality Scorecard

## Status
Accepted (v0.2.0)

## Context
Repositories subject to multi-agent automated code generation lack a mathematical, standardized health metric. Furthermore, when multiple AI model reviewers (e.g. Sonnet, GPT-4o, Gemini) evaluate a pull request, their findings frequently conflict or contain noise.

## Decision
1. Formulate a deterministic 0–100% composite quality scorecard across 6 weighted pillars:
   - Type Safety (20%)
   - Test Coverage & Assertions (25%)
   - Code Health & Anti-Slop AST (20%)
   - Security & Credential Redaction (15%)
   - Token Economy & Context Slicing (10%)
   - Governance & Doc Parity (10%)
2. Implement `MultiModelConsensusReconciler` using weighted voting and minimum agreement ratios (e.g. >= 50%) to eliminate single-model hallucinations.
3. Generate standalone SVG quality badges and OASIS SARIF 2.1.0 exports for GitHub Code Scanning.
4. Provide `GitHubPrCardFormatter` to format collapsible Markdown comment cards with delta diffs vs base branch.

## Consequences
- **Positive**: Objective, mathematical repository health metrics, noise-free multi-model reviews, native SARIF export.
- **Negative**: Requires historical run tracking in `.rush/score_history.json` for trend lines.
- **Safety**: Secret masking on all scorecard outputs and deterministic offline calculations.
