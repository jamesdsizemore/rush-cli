# Specification: Multi-Turn Stale Read Sweeper (TokenTamer)

## Continuity recovery boundary

An insufficient context budget must not silently discard selected evidence: the redacted omission is retained under a stable local CCR handle and reported as recoverable evidence. Freshness and stale-read analysis remain separate from any automatic replay or re-prompting.

## 1. Overview
The `StaleSweeper` (`src/rush/token_economy/stale_sweeper.py`) prunes conversational history by collapsing older turns' verbose file reads and tool payloads into 1-line summary signatures (`<!-- stale_read: collapsed N lines -->`), while preserving active turn contents verbatim.

## 2. API & Behavioral Contract
```python
sweeper = StaleSweeper(keep_recent_turns=1)
pruned_turns = sweeper.sweep_history(raw_conversation_turns)
```
