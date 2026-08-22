"""
Unit tests for Phase 41 / TDD-41-01: Offline BPE Token Accounting using tiktoken.
Verifies exact token counts across cl100k_base and o200k_base encodings.
"""

import tiktoken


def count_tokens_bpe(text: str, model: str = "cl100k_base") -> int:
    """Exact BPE token counter using tiktoken with deterministic fallback."""
    try:
        encoding = tiktoken.get_encoding(model)
        return len(encoding.encode(text))
    except Exception:  # noqa: BLE001
        # Fallback approximation: 1 token ≈ 4 chars
        return max(1, len(text) // 4)


def test_tiktoken_cl100k_exact_count():
    sample_text = "def calculate_blast_radius(symbol: str) -> Dict[str, Any]:\n    return {'score': 0.85}"
    enc = tiktoken.get_encoding("cl100k_base")
    exact_count = len(enc.encode(sample_text))
    assert count_tokens_bpe(sample_text, "cl100k_base") == exact_count
    assert exact_count > 0


def test_tiktoken_o200k_exact_count():
    sample_text = "Evaluating AST Merkle tree hash across 50 modified nodes."
    enc = tiktoken.get_encoding("o200k_base")
    exact_count = len(enc.encode(sample_text))
    assert count_tokens_bpe(sample_text, "o200k_base") == exact_count


def test_token_counter_empty_string():
    assert count_tokens_bpe("", "cl100k_base") == 0
