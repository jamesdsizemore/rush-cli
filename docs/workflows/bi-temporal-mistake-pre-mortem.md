# Workflow: Bi-Temporal Git Revert Mistake Pre-Mortem

## Continuity recovery integration

`coordination_recovery` surfaces up to three redacted mined revert guardrails as `historical_evidence`. They help a new agent avoid known mistakes but never authorize a patch replay, lock release, or retry.

## 1. Overview
The Mistake Miner extracts anti-patterns from repository Git revert history (`git log --grep="[Rr]evert"`). It structures historical regressions into proactive guardrails, preventing AI agents from repeating known failure loops.

Continuity recovery does not execute those guardrails or rerun a failed patch. It exposes only a bounded, redacted failure receipt and replay metadata so the next agent can inspect evidence before choosing a new action.

## 2. Mistake Triplet Architecture
Every mined revert is indexed as a structured triplet:
1. **Believed** (Reverted feature or change description)
2. **Found False** (Rationale or regression reported in commit body)
3. **Truth Now** (Active guardrail preventing repeat regressions)

## 3. CLI and FastMCP Usage
```bash
# Query active mistake guardrails
rush context mistakes

# FastMCP query
rush_context_mistakes_check()
```
