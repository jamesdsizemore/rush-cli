# Specification: Semantic PR Card Synthesizer & CODEOWNERS Router

## 1. Overview
`PrSynthesizeTool` (`src/rush/tools/pr_synthesize.py`) extracts Git diff statistics, categorizes changed paths, parses CODEOWNERS routing rules, computes risk tiers, and aggregates quality verification evidence into a structured pull request description card.

## 2. Risk Tiering Algorithm
Risk tiering is deterministically computed based on net line churn and quality evidence status:
- **`HIGH` Risk**:
  - Total changes (insertions + deletions) > 500 lines, OR
  - Any verification tool in `evidence` reports `status == "fail"` or `status == "error"`.
- **`MEDIUM` Risk**:
  - Total changes > 100 lines, OR
  - Any verification tool in `evidence` reports `status == "warn"`.
- **`LOW` Risk**:
  - Total changes <= 100 lines AND all verification tools report `status == "ok"` or clean findings.

## 3. CODEOWNERS Reviewer Routing
The synthesizer automatically locates `.github/CODEOWNERS`, `CODEOWNERS`, or `docs/CODEOWNERS`:
- Parses pattern-to-owner mapping lines (e.g. `*.py @python-team`).
- Matches each changed file path against the rule patterns using `fnmatch`.
- Aggregates unique reviewers into `metadata.recommended_reviewers` and renders them in the PR markdown card.

## 4. Contained Artifact Export
MCP `export_path` requests PR card output with explicit `allow_artifact_write` permission and containment checks. CLI `--export-path` is not registered. Use CLI `--json` to return the card to the caller; neither route publishes a pull request by itself.

## 5. CLI & FastMCP Contracts
- **CLI**: `rush pr-synthesize . --json`; CLI `--base-ref` and `--export-path` are not registered.
- **FastMCP**: `rush_pr_synthesize(path=".", base_ref="main")`. MCP additionally exposes `export_path` and `allow_artifact_write`; use the live schema for defaults.
