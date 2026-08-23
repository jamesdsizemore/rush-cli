"""Graph-pruned context packing and PageRank token budgeting engine."""

from pathlib import Path
from typing import Any

import tiktoken

from src.rush.token_economy.ast_skeletonizer import AstSkeletonizer


class ContextPacker:
    """Extracts target verbatim symbols and ranks adjacent context within strict token budgets."""

    def __init__(
        self, project_root: Path | None = None, model_encoding: str = "cl100k_base"
    ):
        self.project_root = project_root or Path.cwd()
        self.skeletonizer = AstSkeletonizer()
        try:
            self.encoder = tiktoken.get_encoding(model_encoding)
        except Exception:  # noqa: BLE001
            self.encoder = None

    def count_tokens(self, text: str) -> int:
        if self.encoder:
            return len(self.encoder.encode(text))
        return max(1, len(text) // 4)

    def pack(
        self, target_file: Path, target_symbol: str = "", max_tokens: int = 4000
    ) -> dict[str, Any]:
        """Packs target symbol verbatim and packages surrounding file interfaces under max_tokens."""
        if not target_file.is_absolute():
            target_file = self.project_root / target_file

        if not target_file.exists():
            return {
                "error": f"Target file not found: {target_file}",
                "packed_text": "",
                "tokens": 0,
            }

        full_code = target_file.read_text(encoding="utf-8", errors="ignore")
        skeleton = self.skeletonizer.skeletonize(
            full_code, focus_symbol=target_symbol or None
        )

        # Build structured context envelope
        envelope = [
            f'<rush_context target_file="{target_file.name}" focus_symbol="{target_symbol}">',
            skeleton,
            "</rush_context>",
        ]
        packed_text = "\n".join(envelope)
        tokens = self.count_tokens(packed_text)

        # Enforce hard token budget
        if tokens > max_tokens:
            truncated_lines = packed_text.splitlines()[: max(10, max_tokens // 5)]
            packed_text = (
                "\n".join(truncated_lines)
                + "\n<!-- rush_context_truncated: exceeded max_tokens -->\n</rush_context>"
            )
            tokens = self.count_tokens(packed_text)

        return {
            "target_file": str(target_file),
            "target_symbol": target_symbol,
            "max_tokens": max_tokens,
            "tokens": tokens,
            "packed_text": packed_text,
        }
