"""Sliding window chunk paginator with byte-offset cursors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaginatedChunk:
    chunk_text: str
    cursor_offset: int
    total_bytes: int
    has_more: bool


class TokenChunkPaginator:
    """Splits large output text into byte-bounded sliding chunks."""

    @staticmethod
    def paginate(text: str, offset: int = 0, limit_bytes: int = 4096) -> PaginatedChunk:
        encoded = text.encode("utf-8")
        total = len(encoded)
        if offset >= total:
            return PaginatedChunk(
                chunk_text="", cursor_offset=total, total_bytes=total, has_more=False
            )

        end = min(offset + limit_bytes, total)
        chunk_bytes = encoded[offset:end]
        chunk_str = chunk_bytes.decode("utf-8", errors="replace")
        has_more = end < total

        return PaginatedChunk(
            chunk_text=chunk_str,
            cursor_offset=end,
            total_bytes=total,
            has_more=has_more,
        )
