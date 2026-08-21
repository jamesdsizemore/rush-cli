"""Performance budget evaluator and PR gate."""

from __future__ import annotations

from dataclasses import dataclass
from rush.bundle.chunk_calculator import ChunkSizeReport


@dataclass(frozen=True)
class BudgetViolation:
    file_name: str
    metric: str
    actual_bytes: int
    max_bytes: int


class PerformanceBudgetGate:
    """Evaluates chunk size reports against defined size ceilings."""

    def __init__(self, max_gzip_bytes: int = 150 * 1024) -> None:
        self.max_gzip_bytes = max_gzip_bytes

    def evaluate_chunks(self, reports: list[ChunkSizeReport]) -> list[BudgetViolation]:
        violations = []
        for r in reports:
            if r.gzip_bytes > self.max_gzip_bytes:
                violations.append(
                    BudgetViolation(
                        file_name=r.file_name,
                        metric="gzip_size",
                        actual_bytes=r.gzip_bytes,
                        max_bytes=self.max_gzip_bytes,
                    )
                )
        return violations
