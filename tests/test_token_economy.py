"""Tests for Phase 32: Token Economy & Context Optimization."""

from __future__ import annotations

from pathlib import Path

from rush.token_economy.cache_advisor import PromptCacheAdvisor
from rush.token_economy.compressor import PythonAstOutlineCompressor
from rush.token_economy.counter import FastBPETokenCounter
from rush.token_economy.paginator import TokenChunkPaginator
from rush.token_economy.polyglot_compressor import PolyglotAstCompressor
from rush.token_economy.prompt_compressor import PromptCompressor


def test_token_counter(tmp_path: Path) -> None:
    text = "Hello world! This is a test for token counting."
    count = FastBPETokenCounter.count_tokens(text)
    assert count > 0

    f = tmp_path / "sample.py"
    f.write_text("def test(): pass\n", encoding="utf-8")
    f_count = FastBPETokenCounter.count_file_tokens(f)
    assert f_count > 0


def test_python_ast_outline_compressor() -> None:
    source = """
class Calculator:
    '''A basic calculator.'''
    def add(self, a: int, b: int) -> int:
        '''Adds two numbers.'''
        result = a + b
        return result
"""
    compressed = PythonAstOutlineCompressor.compress_source(source)
    assert "class Calculator:" in compressed
    assert "def add(self, a: int, b: int) -> int:" in compressed
    assert "result = a + b" not in compressed
    assert "..." in compressed


def test_polyglot_ast_compressor() -> None:
    ts_source = """
export interface User {
    id: string;
    name: string;
}
export function getUser(id: string): User {
    console.log("fetching user");
    return { id, name: "Alice" };
}
"""
    ts_compressed = PolyglotAstCompressor.compress_typescript(ts_source)
    assert "export interface User {" in ts_compressed
    assert "export function getUser(id: string): User { ... }" in ts_compressed
    assert "console.log" not in ts_compressed


def test_prompt_compressor() -> None:
    noisy_text = "Line 1\n\n\n\n\nLine 2   \nLine 3"
    cleaned = PromptCompressor.clean_text(noisy_text)
    assert "\n\n\n" not in cleaned
    assert "Line 2" in cleaned


def test_prompt_cache_advisor() -> None:
    short_prompt = "Short system prompt"
    suggestion_short = PromptCacheAdvisor.analyze_prefix(short_prompt)
    assert suggestion_short.estimated_cache_savings_percent == 0.0

    long_prompt = "A" * 2000
    suggestion_long = PromptCacheAdvisor.analyze_prefix(long_prompt)
    assert suggestion_long.estimated_cache_savings_percent > 80.0


def test_token_chunk_paginator() -> None:
    big_text = "abcdefghijklmnopqrstuvwxyz" * 100
    chunk1 = TokenChunkPaginator.paginate(big_text, offset=0, limit_bytes=50)
    assert len(chunk1.chunk_text.encode("utf-8")) == 50
    assert chunk1.has_more is True

    chunk2 = TokenChunkPaginator.paginate(
        big_text, offset=chunk1.cursor_offset, limit_bytes=5000
    )
    assert chunk2.has_more is False
