"""Composite defect risk calculator."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from rush.hotspots.churn import FileChurnStats, GitChurnExtractor
from rush.hotspots.complexity import CyclomaticComplexityCalculator


@dataclass(frozen=True)
class HotspotRiskScore:
    file_path: str
    churn_score: int
    complexity_score: int
    composite_risk: float
    risk_tier: str


class RiskMatrixCalculator:
    """Combines code churn with cyclomatic complexity to compute defect probability."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def analyze_hotspots(self) -> list[HotspotRiskScore]:
        churn_extractor = GitChurnExtractor(self.repo_root)
        churn_map = churn_extractor.extract_churn(max_commits=200)

        scores = []
        for fp, stats in churn_map.items():
            full_p = self.repo_root / fp
            complexity = CyclomaticComplexityCalculator.calculate_file(full_p)
            composite = math.log1p(stats.total_churn) * math.log1p(complexity)

            tier = "Low"
            if composite > 15.0:
                tier = "Critical"
            elif composite > 8.0:
                tier = "High"
            elif composite > 4.0:
                tier = "Medium"

            scores.append(
                HotspotRiskScore(
                    file_path=fp,
                    churn_score=stats.total_churn,
                    complexity_score=complexity,
                    composite_risk=round(composite, 2),
                    risk_tier=tier,
                )
            )

        return sorted(scores, key=lambda s: s.composite_risk, reverse=True)
