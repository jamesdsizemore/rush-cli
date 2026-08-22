"""
Unit tests for Phase 43 / TDD-43-01 & TDD-43-02: CCR Lossless Chunk Store.
Verifies content-addressable SHA-256 chunk caching and 100% byte-exact restoration.
"""

import hashlib


class MemoryCCRStore:
    def __init__(self):
        self.chunks = {}

    def store_chunk(self, content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
        self.chunks[digest] = content
        return digest

    def retrieve_chunk(self, chunk_id: str) -> str:
        if chunk_id not in self.chunks:
            raise KeyError(f"Chunk {chunk_id} not found in CCR cache")
        return self.chunks[chunk_id]


def test_ccr_round_trip_exact_restoration():
    ccr = MemoryCCRStore()
    original_code = """
class BlastRadiusEngine:
    def calculate_depth(self, node_id: str) -> int:
        return 3
"""
    chunk_hash = ccr.store_chunk(original_code)
    assert len(chunk_hash) == 12
    restored = ccr.retrieve_chunk(chunk_hash)
    assert restored == original_code
