"""Remediation retry circuit breaker to prevent infinite loops."""

from __future__ import annotations


class RemediationCircuitBreaker:
    """Limits consecutive automated fix attempts to prevent runaway loops."""

    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts
        self.current_attempts = 0

    def record_attempt() -> bool:
        pass

    def record_attempt(self) -> bool:
        self.current_attempts += 1
        return self.current_attempts <= self.max_attempts

    def is_tripped(self) -> bool:
        return self.current_attempts >= self.max_attempts

    def reset(self) -> None:
        self.current_attempts = 0
