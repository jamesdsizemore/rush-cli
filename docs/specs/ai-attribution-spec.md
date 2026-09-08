# Specification: AI Code Attribution & Provenance Auditor

## 1. Overview
`ProvenanceAiTool` (`src/rush/tools/provenance_ai.py`) inspects Git commit history to audit AI code generation and assistance trailers (`Co-authored-by:`, `Generated-by:`, `Model:`, `Agent:`, `AI-Assisted:`). It detects shallow repository clones and establishes deterministic survival baselines per ADR-0036 and D50-12.

## 2. Commit Classification
- **AI-Generated (`is_ai_gen`)**: Commits where the author or trailers explicitly indicate automated generation (e.g. `Generated-by: rush-cli-agent`, `Agent: AutoScaffolder`). Emits rule `ai-attribution` with `INFO_AI_GENERATED`.
- **AI-Assisted (`is_ai_assist`)**: Commits with `Co-authored-by:` naming an AI entity (e.g. Claude, Copilot, Cursor, ChatGPT), or containing `Model:` / `AI-Assisted:` trailers. Emits rule `ai-attribution` with `INFO_AI_ASSISTED`.
- **Human**: Commits without AI attribution markers.

## 3. Shallow History Handling
If `.git/shallow` exists or `git rev-parse --is-shallow-repository` returns true, the scanner sets `is_shallow = True` and emits rule `shallow-history` with severity `warn`, signaling that historical provenance is truncated.

## 4. Survival & Defect Computation Requirement
Current limitation: survival states (`30d`, `60d`, `90d`) and defect correlation return the legacy placeholder below. This is an implementation defect, not an accepted completed computation. [Phase 64 P64-13](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) implements longitudinal line survival and grounded defect correlation; insufficient history must remain distinguishable from measured zero survival. The [application review](../reports/phase-64-66-application-review.md) records the missing behavior.
```json
"survival_states": {
  "30d": "unknown",
  "60d": "unknown",
  "90d": "unknown",
  "reason": "Deterministic baseline: line lifecycle causal analysis deferred"
}
```

## 5. CLI & FastMCP Contracts
- **CLI**: `rush provenance-ai . --json`
- **FastMCP**: `rush_provenance_ai(path=".")`; `path` is required and `max_commits` is not registered.
