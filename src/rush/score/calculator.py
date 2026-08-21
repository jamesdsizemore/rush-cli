"""Composite 0-100% 6-pillar quality scorecard calculator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PillarScores:
    type_safety: float      # Weight: 20%
    test_coverage: float    # Weight: 25%
    code_health: float      # Weight: 20%
    security: float         # Weight: 15%
    token_economy: float    # Weight: 10%
    governance: float       # Weight: 10%


@dataclass(frozen=True)
class ScorecardReport:
    composite_score: float
    letter_grade: str
    pillars: PillarScores
    summary: str


class WeightNormalizer:
    """Validates and normalizes user-defined pillar weights from configuration."""

    @staticmethod
    def normalize(weights: dict[str, float]) -> dict[str, float]:
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Total weights must be strictly positive.")
        return {k: round(v / total, 4) for k, v in weights.items()}


class CompositeScorecardCalculator:
    """Calculates deterministic 0-100% repository health score and letter grade."""

    WEIGHTS = {
        "type_safety": 0.20,
        "test_coverage": 0.25,
        "code_health": 0.20,
        "security": 0.15,
        "token_economy": 0.10,
        "governance": 0.10,
    }

    @classmethod
    def compute_scorecard(cls, pillars: PillarScores) -> ScorecardReport:
        total = (
            pillars.type_safety * cls.WEIGHTS["type_safety"]
            + pillars.test_coverage * cls.WEIGHTS["test_coverage"]
            + pillars.code_health * cls.WEIGHTS["code_health"]
            + pillars.security * cls.WEIGHTS["security"]
            + pillars.token_economy * cls.WEIGHTS["token_economy"]
            + pillars.governance * cls.WEIGHTS["governance"]
        )
        total = max(0.0, min(100.0, round(total, 1)))

        if total >= 97.0:
            grade = "A+"
        elif total >= 93.0:
            grade = "A"
        elif total >= 90.0:
            grade = "A-"
        elif total >= 85.0:
            grade = "B+"
        elif total >= 80.0:
            grade = "B"
        elif total >= 70.0:
            grade = "C"
        elif total >= 60.0:
            grade = "D"
        else:
            grade = "F"

        summary = f"Composite Quality Score: {total}% (Grade: {grade})"
        return ScorecardReport(composite_score=total, letter_grade=grade, pillars=pillars, summary=summary)
