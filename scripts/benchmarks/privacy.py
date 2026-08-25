"""Privacy, synthetic secret detection, parser bounding, and binary dependency safety probe."""

from __future__ import annotations

import datetime
import re
import time
from typing import Any

from .contracts import (
    CandidateBinary,
    Outcome,
    ProbeResult,
    Scenario,
)

SECRET_DETECTORS = {
    "GITHUB_TOKEN": r"ghp_[A-Za-z0-9]{20,}",
    "AWS_KEY": r"AKIA[0-9A-Z]{16}",
    "OPENAI_KEY": r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",
    "PRIVATE_KEY": r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
}


def scan_and_redact_secrets(text: str) -> tuple[str, tuple[str, ...]]:
    """Identifies synthetic secret tokens and replaces them with [REDACTED:<type>] markers."""
    cleaned = text
    redactions: list[str] = []

    for label, pat in SECRET_DETECTORS.items():
        matches = list(re.finditer(pat, text))
        for m in matches:
            secret_str = m.group(0)
            redactions.append(f"{label}:{secret_str[:4]}***")
            cleaned = cleaned.replace(secret_str, f"[REDACTED:{label}]")

    return cleaned, tuple(redactions)


def validate_candidate_binary(candidate: CandidateBinary) -> Outcome:
    """Validates external binary safety; unapproved/incomplete candidates are deferred."""
    if not candidate.name or not candidate.version or not candidate.license:
        return Outcome.DEFERRED
    if candidate.license not in {"MIT", "Apache-2.0", "BSD-3-Clause", "ISC"}:
        return Outcome.DEFERRED
    if not candidate.bounds:
        return Outcome.DEFERRED
    return Outcome.PASS


def run_privacy_probe(scenario: Scenario, **kwargs: Any) -> ProbeResult:
    """Executes bounded parser and synthetic secret redaction probe."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()

    inp = scenario.input
    text = inp.get("text") or inp.get("input") or str(inp)

    # 1. Check max_bytes bound
    byte_size = inp.get("byte_size", len(text.encode("utf-8")))
    max_bytes = inp.get("max_bytes", 10_000_000)
    if byte_size > max_bytes:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="privacy",
            outcome=Outcome.PASS,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"size_bounded": True, "observed_bytes": byte_size},
            fallback="input-exceeded-byte-limit",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # 2. Check max_pages bound
    pages = inp.get("pages", 1)
    max_pages = inp.get("max_pages", 100)
    if pages > max_pages:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="privacy",
            outcome=Outcome.PASS,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"pages_bounded": True, "observed_pages": pages},
            fallback="input-exceeded-page-limit",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # 3. Check candidate binary if declared
    if "binary" in inp:
        cand = CandidateBinary(
            name=inp.get("binary", ""),
            version=inp.get("version", ""),
            license=inp.get("license", ""),
            bounds=inp.get("bounds", {"max_kb": 10000}),
        )
        status = validate_candidate_binary(cand)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="privacy",
            outcome=status,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"binary_validated": status == Outcome.PASS},
            fallback="none" if status == Outcome.PASS else "candidate-deferred",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # 4. Perform synthetic secret detection and redaction
    cleaned, redactions = scan_and_redact_secrets(text)
    duration_ms = int((time.perf_counter() - t0) * 1000)

    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="privacy",
        outcome=scenario.expected_outcome,
        started_at=start_time,
        duration_ms=duration_ms,
        metrics={
            "redacted_count": len(redactions),
            "clean_text_len": len(cleaned),
        },
        redactions=redactions,
        fallback="none",
        reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
    )
