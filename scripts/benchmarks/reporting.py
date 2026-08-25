"""Atomic reporting and handoff document writers for benchmark results."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .contracts import (
    DecisionRecord,
    FixtureError,
    Outcome,
    ProbeResult,
    SourceEvidence,
)


def write_result(output_root: Path, result: ProbeResult) -> Path:
    """Atomically writes a ProbeResult to JSON via temporary file + atomic replace."""
    output_root = output_root.resolve()
    # Path traversal protection on scenario_id
    if (
        "/" in result.scenario_id
        or "\\" in result.scenario_id
        or ".." in result.scenario_id
    ):
        raise FixtureError(f"scenario output path denied: {result.scenario_id}")

    output_root.mkdir(parents=True, exist_ok=True)
    dest_path = (output_root / f"{result.scenario_id}.json").resolve()
    tmp_path = (output_root / f"{result.scenario_id}.tmp").resolve()

    if output_root not in dest_path.parents:
        raise FixtureError(f"result destination denied: {dest_path}")

    serialized = result.to_dict()
    # Write to tmp file first
    tmp_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    # Atomic replace
    os.replace(tmp_path, dest_path)
    return dest_path


def write_handoff(
    decisions: list[dict[str, Any] | DecisionRecord], output_path: Path
) -> Path:
    """Validates decision records and writes final-handoff.md linking all gates."""
    output_path = output_path.resolve()
    lines = [
        "# Rush Benchmark Final Handoff & Decision Record",
        "",
        "This document records all deterministic gate evaluation decisions and unblocked engineering tasks.",
        "",
        "| Gate / Decision | Status | Unblocked Task | Fixtures | Result JSON | Fallback |",
        "|---|:---:|---|---|---|---|",
    ]

    for d in decisions:
        if isinstance(d, DecisionRecord):
            rec = asdict(d)
            rec["status"] = d.status.value
        else:
            rec = dict(d)

        # Validate required decision fields
        required_fields = [
            "decision_id",
            "title",
            "status",
            "unblocked_task",
            "fixture_ids",
            "result_path",
            "fallback",
            "reproduction",
        ]
        for field in required_fields:
            val = rec.get(field)
            if not val:
                raise FixtureError(
                    f"incomplete decision record for {rec.get('decision_id', 'unknown')}: missing {field}"
                )

        fixtures_str = ", ".join(rec["fixture_ids"])
        lines.append(
            f"| `{rec['decision_id']}` ({rec['title']}) | `{rec['status']}` | `{rec['unblocked_task']}` | {fixtures_str} | [`{rec['result_path']}`]({rec['result_path']}) | {rec['fallback']} |"
        )

    lines.append("")
    lines.append("## Reproduction Commands")
    lines.append("")
    for d in decisions:
        rec = asdict(d) if isinstance(d, DecisionRecord) else d
        lines.append(f"### `{rec['decision_id']}`: {rec['title']}")
        lines.append(f"```bash\n{rec['reproduction']}\n```\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _evaluate_gate_status(
    matching_scenarios: list[str],
    results_by_id: dict[str, ProbeResult],
) -> Outcome:
    """Returns PASS only for a complete, non-fixture, all-pass evidence set."""
    if matching_scenarios == ["*"] or any(
        sc_id not in results_by_id for sc_id in matching_scenarios
    ):
        return Outcome.INCONCLUSIVE
    matched_results = [results_by_id[sc_id] for sc_id in matching_scenarios]
    if any(r.outcome == Outcome.FAIL for r in matched_results):
        return Outcome.FAIL
    if any(
        r.metrics.get("evidence_mode") in {"fixture", "metadata-only"}
        for r in matched_results
    ):
        return Outcome.INCONCLUSIVE
    if any(r.outcome in {Outcome.DEFERRED, Outcome.SKIPPED} for r in matched_results):
        return Outcome.DEFERRED
    if all(r.outcome == Outcome.PASS for r in matched_results):
        return Outcome.PASS
    return Outcome.INCONCLUSIVE


def generate_and_write_decisions(
    results: list[ProbeResult], output_root: Path
) -> list[DecisionRecord]:
    """Evaluates all benchmark gate decisions dynamically from probe results and writes decision JSONs + final-handoff.md."""

    output_root = output_root.resolve()
    results_by_id = {r.scenario_id: r for r in results}

    # Dynamic gate scenario maps
    gate_scenarios = {
        "B-D01": list(results_by_id.keys()) if results_by_id else ["*"],
        "B-D02": [
            "drift-ast-hash-modified-01",
            "drift-downstream-premise-demotion-02",
            "drift-external-git-file-touch-03",
            "drift-schema-sql-version-04",
            "drift-type-definition-divergence-05",
            "drift-untracked-env-mutation-06",
        ],
        "B-D03": [
            "privacy-api-key-redaction-01",
            "privacy-synthetic-secret-tokens-02",
            "privacy-aws-key-scrub-03",
            "privacy-private-key-block-04",
            "privacy-bounded-max-bytes-05",
            "privacy-bounded-max-pages-06",
            "privacy-bounded-timeout-07",
            "privacy-candidate-binary-validation-08",
        ],
        "B-D04": [
            "budget-context-2k-pack-01",
            "budget-context-8k-pack-02",
            "budget-context-16k-pack-03",
        ],
        "B-D05": [
            "budget-ccr-chunk-store-05",
            "budget-ccr-chunk-restore-06",
        ],
        "B-D06": [
            "local-granite-278m-c0",
            "local-bge-small-c0",
            "local-phi-4-mini-c1",
            "local-qwen2.5-coder-7b-c2",
        ],
        "B-D07": [
            "handoff-claude-to-cursor-01",
            "handoff-cursor-to-deepseek-02",
            "handoff-openai-to-claude-03",
            "handoff-deepseek-to-antigravity-04",
        ],
        "B-D08": [
            "budget-router-9router-independence-07",
        ],
        "B-D09": [
            "budget-router-omniroute-independence-08",
        ],
        "B-D10": [
            "handoff-tampered-instructions-05",
            "handoff-cross-dialect-xml-07",
            "handoff-cross-dialect-json-08",
        ],
        "B-D11": [
            "recovery-circuit-breaker-loop-01",
            "recovery-worktree-sandbox-rollback-02",
            "concurrency-mutex-single-acquirer-01",
            "concurrency-lock-release-02",
            "concurrency-checkpoint-flight-03",
            "concurrency-ast-merge-04",
        ],
    }

    decisions = [
        DecisionRecord(
            decision_id="B-D01",
            title="Harness Foundation & Typed Contracts",
            status=_evaluate_gate_status(gate_scenarios["B-D01"], results_by_id),
            unblocked_task="P2-T01",
            fixture_ids=["scenarios.json"],
            result_path="B1/decision-B-D01-B-D02.json",
            evidence=[
                SourceEvidence(
                    url="https://rush.dev/docs/testing",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="fixture-only-mode",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_contracts.py tests/test_benchmark_runner.py -q",
        ),
        DecisionRecord(
            decision_id="B-D02",
            title="Control Corpus & Baseline Telemetry",
            status=_evaluate_gate_status(gate_scenarios["B-D02"], results_by_id),
            unblocked_task="P3-T01",
            fixture_ids=["scenarios.json"],
            result_path="B1/decision-B-D01-B-D02.json",
            evidence=[
                SourceEvidence(
                    url="https://rush.dev/docs/architecture",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="naive-summary-baseline",
            reproduction=".venv/Scripts/python.exe -m scripts.benchmarks.run --all --output research/benchmark/B1",
        ),
        DecisionRecord(
            decision_id="B-D03",
            title="Privacy Redaction & Parser Bounds",
            status=_evaluate_gate_status(gate_scenarios["B-D03"], results_by_id),
            unblocked_task="P2-T02",
            fixture_ids=["privacy_cases.json"],
            result_path="B3/decision-B-D03.json",
            evidence=[
                SourceEvidence(
                    url="https://gitleaks.io",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="strict-pattern-scrubbing",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_privacy.py -q",
        ),
        DecisionRecord(
            decision_id="B-D04",
            title="ContextPacker Token Reduction",
            status=_evaluate_gate_status(gate_scenarios["B-D04"], results_by_id),
            unblocked_task="P3-T01",
            fixture_ids=["context_cases.json"],
            result_path="B4/decision-B-D04-B-D05.json",
            evidence=[
                SourceEvidence(
                    url="https://rush.dev/docs/token-economy",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="full-file-fallback",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_context.py -q",
        ),
        DecisionRecord(
            decision_id="B-D05",
            title="CCR Chunk Cache & Exact Byte Restoration",
            status=_evaluate_gate_status(gate_scenarios["B-D05"], results_by_id),
            unblocked_task="P3-T02",
            fixture_ids=["context_cases.json"],
            result_path="B4/decision-B-D04-B-D05.json",
            evidence=[
                SourceEvidence(
                    url="https://rush.dev/docs/ccr",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="uncompressed-raw-text",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_context.py -q",
        ),
        DecisionRecord(
            decision_id="B-D06",
            title="Local Model Hardware Profiling & Runtime Bounds",
            status=_evaluate_gate_status(gate_scenarios["B-D06"], results_by_id),
            unblocked_task="P4-T01",
            fixture_ids=["local_candidates.json"],
            result_path="B6/decision-B-D06.json",
            evidence=[
                SourceEvidence(
                    url="https://huggingface.co/ibm-granite",
                    retrieved_at="2026-08-24",
                    license_or_terms="Apache-2.0",
                )
            ],
            fallback="lexical-symbol-search",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_local.py -q",
        ),
        DecisionRecord(
            decision_id="B-D07",
            title="Provider Route Security & Redaction",
            status=_evaluate_gate_status(gate_scenarios["B-D07"], results_by_id),
            unblocked_task="P5-T01",
            fixture_ids=["provider_routes.json"],
            result_path="B2/decision-B-D07-B-D10.json",
            evidence=[
                SourceEvidence(
                    url="https://docs.anthropic.com",
                    retrieved_at="2026-08-24",
                    license_or_terms="Proprietary Terms",
                )
            ],
            fallback="fixture-replay",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q",
        ),
        DecisionRecord(
            decision_id="B-D08",
            title="9Router Route Independence",
            status=_evaluate_gate_status(gate_scenarios["B-D08"], results_by_id),
            unblocked_task="P5-T02",
            fixture_ids=["routers.json"],
            result_path="B2/decision-B-D07-B-D10.json",
            evidence=[
                SourceEvidence(
                    url="https://9router.dev",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="direct-provider-route",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q",
        ),
        DecisionRecord(
            decision_id="B-D09",
            title="OmniRoute Independence",
            status=_evaluate_gate_status(gate_scenarios["B-D09"], results_by_id),
            unblocked_task="P5-T02",
            fixture_ids=["routers.json"],
            result_path="B2/decision-B-D07-B-D10.json",
            evidence=[
                SourceEvidence(
                    url="https://github.com/ourines/omniroute",
                    retrieved_at="2026-08-24",
                    license_or_terms="Apache-2.0",
                )
            ],
            fallback="direct-provider-route",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q",
        ),
        DecisionRecord(
            decision_id="B-D10",
            title="Protocol Quarantine of Tampered Envelopes",
            status=_evaluate_gate_status(gate_scenarios["B-D10"], results_by_id),
            unblocked_task="P5-T03",
            fixture_ids=["protocol_cases.json"],
            result_path="B2/decision-B-D07-B-D10.json",
            evidence=[
                SourceEvidence(
                    url="https://modelcontextprotocol.io",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="quarantined-import",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_providers.py -q",
        ),
        DecisionRecord(
            decision_id="B-D11",
            title="Multi-Agent Lock Mesh & Checkpoint Replay",
            status=_evaluate_gate_status(gate_scenarios["B-D11"], results_by_id),
            unblocked_task="P4-T02",
            fixture_ids=["coordination_cases.json"],
            result_path="B5/decision-B-D11.json",
            evidence=[
                SourceEvidence(
                    url="https://rush.dev/docs/mcp-mesh",
                    retrieved_at="2026-08-24",
                    license_or_terms="MIT",
                )
            ],
            fallback="optimistic-single-agent-lock",
            reproduction=".venv/Scripts/python.exe -m pytest tests/test_benchmark_coordination.py -q",
        ),
    ]

    # All generated evidence stays in the caller-selected campaign output.
    for d in decisions:
        matching_decisions = [
            asdict(x) for x in decisions if x.result_path == d.result_path
        ]
        for item in matching_decisions:
            if hasattr(item.get("status"), "value"):
                item["status"] = item["status"].value
        destination = output_root / d.result_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(matching_decisions, indent=2), encoding="utf-8"
        )
    write_handoff(decisions, output_root / "final-handoff.md")
    return decisions
