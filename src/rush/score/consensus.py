"""Multi-model review consensus reconciler."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFinding:
    model_name: str
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    description: str


@dataclass(frozen=True)
class ConsensusFinding:
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    description: str
    agreeing_models: list[str]
    confidence: float


class MultiModelConsensusReconciler:
    """Reconciles findings from multiple AI models using weighted agreement."""

    def __init__(self, min_agreement_ratio: float = 0.5) -> None:
        self.min_agreement_ratio = min_agreement_ratio

    def reconcile_findings(self, all_findings: list[ModelFinding], total_models: int) -> list[ConsensusFinding]:
        if total_models <= 0 or not all_findings:
            return []

        grouped: dict[tuple[str, int, str], list[ModelFinding]] = {}
        for f in all_findings:
            key = (f.file_path, f.line_number, f.rule_id)
            grouped.setdefault(key, []).append(f)

        consensus_list = []
        for (file_p, line_n, rule_id), items in grouped.items():
            models = sorted(list({item.model_name for item in items}))
            ratio = len(models) / total_models

            if ratio >= self.min_agreement_ratio:
                severities = [item.severity for item in items]
                most_common_sev = Counter(severities).most_common(1)[0][0]
                desc = items[0].description

                consensus_list.append(
                    ConsensusFinding(
                        file_path=file_p,
                        line_number=line_n,
                        rule_id=rule_id,
                        severity=most_common_sev,
                        description=desc,
                        agreeing_models=models,
                        confidence=round(ratio, 2),
                    )
                )

        return sorted(consensus_list, key=lambda c: (c.confidence, c.severity), reverse=True)
