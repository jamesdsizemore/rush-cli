"""Decision-record schema reuse (Phase 62 §6.4): remediation-contract-shaped fields
embedded inside MemoryArtifact.content for subject in {"architectural_decision", "failure"}.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionRecordFields:
    """Embedded inside MemoryArtifact.content for subject in {"architectural_decision", "failure"}."""

    red_task: str | None = None
    green_task: str | None = None
    target_seam: str | None = None
    test_file: str | None = None
    test_function: str | None = None
    predecessor: str | None = None
    status: str = "in_progress"  # rush's own default, not remediation-contracts.toml's closed "completed"-only vocabulary
