"""Benchmark regression guard tool.

Compares supplied performance samples against recorded baselines in
.rush/baselines.json. Recording baselines is guarded by --allow-cache-write.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms


def _calc_stats(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    return {
        "mean": float(mean(samples)),
        "median": float(median(samples)),
        "min": float(min(samples)),
        "max": float(max(samples)),
        "count": len(samples),
    }


class BenchmarkTool(ToolFn):
    name: ToolName = "benchmark"

    @property
    def mcp_description(self) -> str:
        return (
            "Compare performance samples against baseline thresholds at <path>; "
            "baseline recording requires --allow-cache-write. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions, **options)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        samples: list[float] | None = None,
        threshold_percent: float = 5.0,
        record: bool = False,
        operation: str = "check",
        baseline_name: str = "default",
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        p = Path(path)
        root = p if p.is_dir() else p.parent
        rush_dir = root / ".rush"
        baseline_file = rush_dir / "baselines.json"
        granted_perms = permissions or ExecutionPermissions()

        import math

        sample_list = [
            float(s)
            for s in (samples or [])
            if not math.isnan(float(s)) and not math.isinf(float(s))
        ]
        is_record = record or (operation == "record")

        if is_record:
            if not getattr(granted_perms, "cache_write", False):
                return ToolResult(
                    tool=self.name,
                    engine="benchmark",
                    engine_version="1.0.0",
                    status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary="benchmark: Recording baseline requires --allow-cache-write permission.",
                    findings=[],
                    raw=None,
                    metadata={
                        "execution": build_execution_metadata(
                            "executed",
                            granted=permissions,
                            producer="benchmark",
                        )
                    },
                )

            if not sample_list:
                return ToolResult(
                    tool=self.name,
                    engine="benchmark",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="benchmark: No samples provided to record baseline.",
                    findings=[],
                    raw=None,
                    metadata={
                        "execution": build_execution_metadata(
                            "executed",
                            granted=permissions,
                            producer="benchmark",
                        )
                    },
                )

            rush_dir.mkdir(parents=True, exist_ok=True)
            baselines_data: dict[str, Any] = {}
            if baseline_file.is_file():
                try:
                    baselines_data = json.loads(
                        baseline_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    baselines_data = {}

            stats = _calc_stats(sample_list)
            baselines_data[baseline_name] = stats
            from rush.safety.redactor import sanitize_value

            clean_baselines = sanitize_value(baselines_data).value
            baseline_file.write_text(
                json.dumps(clean_baselines, indent=2), encoding="utf-8"
            )

            return ToolResult(
                tool=self.name,
                engine="benchmark",
                engine_version="1.0.0",
                status="ok",
                duration_ms=elapsed_ms(start),
                summary=f"benchmark: Baseline '{baseline_name}' recorded successfully in .rush/baselines.json.",
                findings=[],
                metrics=stats,
                raw={"recorded": stats},
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="benchmark",
                    )
                },
            )

        # Evaluating against baseline
        if not baseline_file.is_file():
            return ToolResult(
                tool=self.name,
                engine="benchmark",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"benchmark: Baseline '{baseline_name}' not found in .rush/baselines.json; record one with --allow-cache-write.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="benchmark",
                    )
                },
            )

        try:
            baselines_data = json.loads(baseline_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            baselines_data = {}

        if baseline_name not in baselines_data:
            return ToolResult(
                tool=self.name,
                engine="benchmark",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"benchmark: Baseline '{baseline_name}' not found in .rush/baselines.json; record one with --allow-cache-write.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="benchmark",
                    )
                },
            )

        if not sample_list:
            return ToolResult(
                tool=self.name,
                engine="benchmark",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="benchmark: No current benchmark samples provided to evaluate.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="benchmark",
                    )
                },
            )

        base_stats = baselines_data[baseline_name]
        base_mean = float(base_stats.get("mean", 1.0))
        curr_stats = _calc_stats(sample_list)
        curr_mean = curr_stats["mean"]

        regression_pct = 0.0
        if base_mean > 0:
            regression_pct = ((curr_mean - base_mean) / base_mean) * 100.0

        findings: list[Finding] = []
        if regression_pct > threshold_percent:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,
                    rule="benchmark/performance-regression",
                    severity="error",
                    message=(
                        f"Performance regressed by {regression_pct:.2f}% "
                        f"(mean {curr_mean:.2f} vs baseline {base_mean:.2f}, exceeds threshold of {threshold_percent}%)"
                    ),
                    remediation="Optimize hot paths or verify if regression is intended and re-record baseline.",
                )
            )

        status: ToolStatus = "fail" if findings else "ok"
        summary = (
            f"benchmark: Evaluated {len(sample_list)} sample(s) against '{baseline_name}' baseline: "
            f"{regression_pct:+.2f}% delta ({'PASS' if not findings else 'FAIL'})"
        )

        return ToolResult(
            tool=self.name,
            engine="benchmark",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "current_mean": curr_mean,
                "baseline_mean": base_mean,
                "regression_pct": round(regression_pct, 4),
                "threshold_percent": threshold_percent,
            },
            raw={"current_stats": curr_stats, "baseline_stats": base_stats},
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="benchmark",
                )
            },
        )
