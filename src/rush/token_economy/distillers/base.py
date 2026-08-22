"""Base interfaces and data structures for subprocess command distillers."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class DistilledResult(BaseModel):
    """Structured result from distilling noisy command outputs."""

    summary: str
    failure_count: int = 0
    passed_count: int = 0
    failures: list[dict[str, Any]] = Field(default_factory=list)
    raw_lines: int
    distilled_lines: int
    savings_pct: float
    distilled_text: str


class BaseDistiller(ABC):
    """Abstract base class for command-specific output distillers."""

    @abstractmethod
    def can_distill(self, command: list[str]) -> bool:
        """Returns True if this distiller handles the given command invocation."""

    @abstractmethod
    def distill(
        self, raw_stdout: str, raw_stderr: str, exit_code: int
    ) -> DistilledResult:
        """Distills raw stdout/stderr into actionable error frames and summary."""
