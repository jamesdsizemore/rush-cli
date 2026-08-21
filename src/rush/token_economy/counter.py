"""Fast BPE token counter and cost estimator."""

from __future__ import annotations

import math
import re
from pathlib import Path


class FastBPETokenCounter:
    """Estimates token counts using fast byte-pair heuristic (avg 3.8 - 4.0 chars/token)."""

    @staticmethod
    def count_tokens(text: str) -> int:
        if not text:
            return 0
        words = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
        char_count = len(text)
        word_count = len(words)
        estimated = math.ceil((char_count * 0.2) + (word_count * 0.5))
        return max(1, estimated)

    @staticmethod
    def count_file_tokens(path: Path) -> int:
        if not path.is_file():
            return 0
        text = path.read_text(encoding="utf-8", errors="replace")
        return FastBPETokenCounter.count_tokens(text)
