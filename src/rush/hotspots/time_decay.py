"""Exponential time-decay churn weight calculator."""

from __future__ import annotations

import math
from datetime import datetime, timezone


class TimeDecayCalculator:
    """Applies exponential half-life decay to git commit churn weights."""

    def __init__(self, half_life_days: float = 90.0) -> None:
        self.half_life_days = half_life_days
        self.decay_constant = math.log(2.0) / self.half_life_days

    def calculate_weight(self, commit_date: datetime, current_date: datetime | None = None) -> float:
        now = current_date or datetime.now(timezone.utc)
        age_days = max(0.0, (now - commit_date).total_seconds() / 86400.0)
        return math.exp(-self.decay_constant * age_days)
