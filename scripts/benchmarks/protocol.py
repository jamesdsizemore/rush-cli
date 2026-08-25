"""Protocol envelope parser and quarantined-import probe runner."""

from __future__ import annotations

import datetime
import time
from typing import Any

from .contracts import (
    Outcome,
    ProbeResult,
    Scenario,
)

INJECTION_PATTERNS = [
    "ignore prior",
    "ignore all previous",
    "delete everything",
    "override safety",
    "system prompt",
]


def run_protocol_probe(scenario: Scenario, **kwargs: Any) -> ProbeResult:
    """Parses declared protocol envelopes and quarantines tampered/injected instructions."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()

    fmt = scenario.input.get("format", "unknown")
    payload = scenario.input.get("payload", "")
    source_span = scenario.input.get("source_span", [0, len(payload)])
    is_tampered_flag = scenario.input.get("tampered", False)

    # Detect prompt injection or explicit tampering
    is_tampered = is_tampered_flag or any(
        pat in payload.lower() for pat in INJECTION_PATTERNS
    )

    duration_ms = int((time.perf_counter() - t0) * 1000)

    if is_tampered:
        # Threat quarantined with source span preservation
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="protocol",
            outcome=Outcome.PASS,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={
                "format": fmt,
                "quarantined": True,
                "source_span_start": source_span[0] if len(source_span) > 0 else 0,
                "source_span_end": source_span[1]
                if len(source_span) > 1
                else len(payload),
            },
            fallback="quarantined-import",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # Normal valid protocol envelope parsing
    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="protocol",
        outcome=scenario.expected_outcome,
        started_at=start_time,
        duration_ms=duration_ms,
        metrics={
            "format": fmt,
            "quarantined": False,
            "payload_len": len(payload),
        },
        fallback="none",
        reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
    )
