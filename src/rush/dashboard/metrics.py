"""Real-time metrics aggregator and trend analyzer."""

from __future__ import annotations

from dataclasses import dataclass

from rush.tools.base import Finding, ToolResult


@dataclass(frozen=True)
class QualityMetrics:
    pass_rate_percentage: float
    total_findings: int
    critical_findings: int
    warning_findings: int
    average_tool_duration_ms: float
    slowest_tool_name: str | None


class DashboardMetricsAggregator:
    """Computes real-time health metrics from active dashboard state."""

    @staticmethod
    def compute_metrics(results: list[ToolResult]) -> QualityMetrics:
        if not results:
            return QualityMetrics(
                pass_rate_percentage=100.0,
                total_findings=0,
                critical_findings=0,
                warning_findings=0,
                average_tool_duration_ms=0.0,
                slowest_tool_name=None,
            )

        passed = sum(1 for r in results if r.get("status") == "ok")
        pass_rate = round((passed / len(results)) * 100.0, 1)

        all_findings: list[Finding] = []
        for r in results:
            all_findings.extend(r.get("findings", []))

        crit = sum(1 for f in all_findings if f.get("severity") in ("fail", "error"))
        warn = sum(1 for f in all_findings if f.get("severity") == "warn")

        durations = [r.get("duration_ms", 0) for r in results]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else 0.0

        slowest = (
            max(results, key=lambda r: r.get("duration_ms", 0)).get("tool")
            if results
            else None
        )

        return QualityMetrics(
            pass_rate_percentage=pass_rate,
            total_findings=len(all_findings),
            critical_findings=crit,
            warning_findings=warn,
            average_tool_duration_ms=avg_dur,
            slowest_tool_name=slowest,
        )
