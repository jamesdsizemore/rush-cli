# Phase 09 implementation ledger — AI, LLM & Agentic Systems Safety

Scope:
- Implement adapters for modern AI, LLM, and agentic redteaming, unit testing, and guardrails validation:
  - `PromptfooEngine` (`src/rush/engines/promptfoo.py`): Automated LLM evaluation, prompt injection testing, and redteaming.
  - `GarakEngine` (`src/rush/engines/garak.py`): LLM vulnerability probing and jailbreak defense scanning.
  - `DeepevalEngine` (`src/rush/engines/deepeval.py`): Unit-testing framework for RAG systems (faithfulness, answer relevancy, hallucination).
  - `GuardrailsEngine` (`src/rush/engines/guardrails.py`): Deterministic output structure and policy enforcement validation.
- Implement `AiEvalTool` (`src/rush/tools/ai_eval.py`): `rush ai-eval <path>` CLI command and `rush_ai-eval` FastMCP stdio tool.
- Wire deterministic reference test suites in `tests/test_promptfoo_reference.py`, `tests/test_garak_reference.py`, `tests/test_deepeval_reference.py`, `tests/test_guardrails_reference.py`, `tests/test_ai_eval.py`.
- Catalog registration in `src/rush/catalog.py` with `real_adapter` maturity.

## Verification Evidence
- Full pytest suite passing (324 passed, 7 skipped).
- Ruff linter & formatter clean.
