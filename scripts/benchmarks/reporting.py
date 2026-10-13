"""Atomic reporting and handoff document writers for benchmark results."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from collections.abc import Sequence
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
from .privacy import scan_and_redact_secrets


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
    decisions: Sequence[dict[str, Any] | DecisionRecord], output_path: Path
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


# --- MC13.4/MC13.5: memory-suite paired scoring and report ------------------------


def paired_bootstrap_ci(
    differences: list[float], *, seed: int, resamples: int = 2000
) -> tuple[float, float]:
    """Seeded paired bootstrap 95% CI over per-case `candidate - baseline`
    differences. Deterministic for a fixed `(differences, seed, resamples)`
    -- resampling uses `random.Random(seed)`, never the shared global RNG.
    Returns `(0.0, 0.0)` for an empty input (insufficient precision, not a
    fabricated interval)."""
    if not differences:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(differences)
    means: list[float] = []
    for _ in range(resamples):
        resample = [differences[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lower_index = int(0.025 * resamples)
    upper_index = min(int(0.975 * resamples), resamples - 1)
    return (means[lower_index], means[upper_index])


_ID_KEYS = frozenset({"session_id", "uuid", "thread_id"})
_ID_MIN_LENGTH = 8
_REDACTED_ID = re.compile(r"redacted:[0-9a-f]{12}")
# ponytail: fixed nesting cap; real reports nest ~10 levels deep.
_MAX_REPORT_DEPTH = 64


def _check_depth(value: Any) -> None:
    """Iterative nesting check, so a hostile payload never recurses (G15)."""
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            children: Any = node.values()
        elif isinstance(node, (list, tuple)):
            children = node
        else:
            continue
        if depth > _MAX_REPORT_DEPTH:
            raise FixtureError(
                f"invalid_value: report nesting exceeds {_MAX_REPORT_DEPTH} levels"
            )
        stack.extend((child, depth + 1) for child in children)


def _collect_ids(value: Any, ids: set[str]) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if (
                key in _ID_KEYS
                and isinstance(inner, str)
                and len(inner) >= _ID_MIN_LENGTH
                and not _REDACTED_ID.fullmatch(inner)
            ):
                ids.add(inner)
            _collect_ids(inner, ids)
    elif isinstance(value, list):
        for inner in value:
            _collect_ids(inner, ids)


def redact_report(
    value: Any,
    *,
    redaction_patterns: Any = (),
    provider_id_values: Any = (),
    home: str | None = None,
) -> tuple[Any, int]:
    """D15: redacts every string of a report payload -- dictionary keys,
    values and list entries -- and returns `(redacted, redaction_count)`.

    Pass 0 normalizes through JSON (`Path`, tuples, dataclasses become plain
    strings and lists), pass 1 collects provider ids (every string of 8+
    characters under a `session_id`/`uuid`/`thread_id` key, plus
    `provider_id_values`), pass 2 maps each string: secrets, route patterns,
    provider ids (`redacted:<sha256[:12]>`) and the HOME prefix (`~`). An
    already redacted id marker is left unchanged, so the pass is idempotent. `home`
    is the HOME prefix to replace (default: this process's, which a run that redirects
    its own HOME passes explicitly as the caller's)."""
    _check_depth(value)
    try:
        normalized = json.loads(json.dumps(value, default=str))
    except (RecursionError, ValueError) as exc:
        raise FixtureError(
            f"invalid_value: report payload not serializable: {exc}"
        ) from None
    ids = {str(v) for v in provider_id_values if str(v)}
    _collect_ids(normalized, ids)
    ordered_ids = sorted(ids, key=len, reverse=True)
    patterns = list(redaction_patterns)
    home_path = Path(home) if home else Path.home()
    home = str(home_path) if len(home_path.parts) > 1 else None
    count = 0

    def redact_str(text: str) -> str:
        nonlocal count
        if _REDACTED_ID.fullmatch(text):
            return text
        cleaned, found = scan_and_redact_secrets(text)
        count += len(found)
        for pattern in patterns:
            cleaned, n = re.subn(pattern, "[REDACTED]", cleaned)
            count += n
        for provider_id in ordered_ids:
            occurrences = cleaned.count(provider_id)
            if occurrences:
                marker = (
                    "redacted:" + hashlib.sha256(provider_id.encode()).hexdigest()[:12]
                )
                cleaned = cleaned.replace(provider_id, marker)
                count += occurrences
        if home is not None:
            cleaned, n = re.subn(re.escape(home) + r"(?=[/\\]|$)", "~", cleaned)
            count += n
        return cleaned

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return redact_str(node)
        if isinstance(node, dict):
            return {redact_str(str(k)): walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(normalized), count


def write_memory_suite_report(
    output_root: Path,
    payload: dict[str, Any],
    *,
    redaction_patterns: Any = (),
    provider_id_values: Any = (),
    home: str | None = None,
) -> Path:
    """Atomically writes the MC13 memory-suite run's full JSON report
    (dataset case results, named-episode results, variant comparisons,
    named blockers) -- same temp-file + `os.replace` pattern as
    `write_result`. D15: the payload is redacted (`redact_report`) and
    serialized before any output byte is written, and carries
    `redaction_count`."""
    redacted, count = redact_report(
        payload,
        redaction_patterns=redaction_patterns,
        provider_id_values=provider_id_values,
        home=home,
    )
    if isinstance(redacted, dict):
        redacted["redaction_count"] = count
    try:
        text = json.dumps(redacted, indent=2)
    except (RecursionError, ValueError) as exc:
        raise FixtureError(f"invalid_value: report not serializable: {exc}") from None
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    dest_path = output_root / "memory-suite-report.json"
    tmp_path = output_root / "memory-suite-report.tmp"
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, dest_path)
    return dest_path


# --- 72-T08: hybrid retrieval evaluation (R12, R19, D14a, PR4) --------------------------

HYBRID_ARMS = ("current", "hybrid", "metadata")
_P72_SPLITS = ("literal", "paraphrase")


def recall_at_k(
    returned_ids: list[str], relevant_ids: list[str], k: int = 8
) -> float | None:
    """Share of `relevant_ids` among the first `k` returned ids; `None` when a case has
    no relevant ids (a baseline case)."""
    if not relevant_ids:
        return None
    return len(set(returned_ids[:k]) & set(relevant_ids)) / len(set(relevant_ids))


def chance_recall(returned_count: int, eligible_count: int) -> float:
    """`min(1, n_i / E_i)`: the recall a random draw of `n_i` of the `E_i` eligible
    records reaches in expectation."""
    if eligible_count <= 0:
        return 1.0
    return min(1.0, returned_count / eligible_count)


def _pair_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["case_id"],
        row["seed"],
        row.get("fixture_revision"),
        json.dumps(row.get("grants"), sort_keys=True),
        json.dumps(row.get("budgets"), sort_keys=True),
    )


def _seed_mean(rows: list[dict[str, Any]], arm: str, field: str) -> dict[str, float]:
    """Per `p72-` case, the mean of `field` over that arm's seeds (seeds are not
    independent observations; the case is the unit)."""
    sums: dict[str, list[float]] = {}
    for row in rows:
        if row["arm"] == arm and row.get("split") in _P72_SPLITS:
            sums.setdefault(row["case_id"], []).append(float(row[field] or 0.0))
    return {case: sum(values) / len(values) for case, values in sums.items()}


def _provider_verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The D14a table for one provider's rows, first matching row wins."""
    if any(int(row.get("security_inclusion") or 0) > 0 for row in rows):
        return {"verdict": "unsafe", "reason": "unauthorized or stale inclusion"}
    arms_by_key: dict[tuple[Any, ...], set[str]] = {}
    for row in rows:
        arms_by_key.setdefault(_pair_key(row), set()).add(row["arm"])
    if any(arms != set(HYBRID_ARMS) for arms in arms_by_key.values()):
        return {"verdict": "unavailable", "reason": "missing pair"}
    if any(row.get("route_available") is False for row in rows):
        return {"verdict": "unavailable", "reason": "route unavailable"}
    for row in rows:
        if row["arm"] != "hybrid":
            continue
        if (
            row.get("embedding_fallback_code")
            or row.get("override_skipped") == "no_request"
            or (row.get("retrieval_required") and row.get("retrieval") != "hybrid")
        ):
            return {"verdict": "unavailable", "reason": "hybrid arm not available"}
    seed = min(int(row["seed"]) for row in rows)
    split = {
        row["case_id"]: row["split"] for row in rows if row.get("split") in _P72_SPLITS
    }
    cases = sorted(split)
    pass_c = _seed_mean(rows, "current", "passed")
    pass_h = _seed_mean(rows, "hybrid", "passed")
    if not cases or sum(pass_c[c] for c in cases) == 0:
        return {"verdict": "unavailable", "reason": "no current passes"}
    recall_c = _seed_mean(rows, "current", "recall_at_8")
    recall_h = _seed_mean(rows, "hybrid", "recall_at_8")
    chance = _seed_mean(rows, "hybrid", "chance_recall")
    literal = [c for c in cases if split[c] == "literal"]
    paraphrase = [c for c in cases if split[c] == "paraphrase"]
    literal_delta = (
        sum(recall_h[c] - recall_c[c] for c in literal) / len(literal)
        if literal
        else 0.0
    )
    para_low, para_high = paired_bootstrap_ci(
        [recall_h[c] - recall_c[c] for c in paraphrase], seed=seed
    )
    if literal_delta < 0:
        return {"verdict": "harm", "reason": "literal recall fell"}
    if para_high < 0:
        return {"verdict": "harm", "reason": "paraphrase recall fell"}
    if sum(pass_h[c] for c in cases) < sum(pass_c[c] for c in cases):
        return {"verdict": "harm", "reason": "fewer passes"}
    # PR4: cost per correct answer, `d_i = (cost_h - cost_c) - R * (pass_h - pass_c)`
    # with `R` the current arm's cost per pass.
    for field in ("case_tokens", "case_ms"):
        cost_c = _seed_mean(rows, "current", field)
        cost_h = _seed_mean(rows, "hybrid", field)
        rate = sum(cost_c[c] for c in cases) / sum(pass_c[c] for c in cases)
        low, _high = paired_bootstrap_ci(
            [(cost_h[c] - cost_c[c]) - rate * (pass_h[c] - pass_c[c]) for c in cases],
            seed=seed,
        )
        if low > 0:
            return {"verdict": "harm", "reason": f"{field} per pass rose"}
    chance_low, _chance_high = paired_bootstrap_ci(
        [recall_h[c] - chance[c] for c in paraphrase], seed=seed
    )
    if para_low > 0 and chance_low > 0:
        return {"verdict": "benefit", "reason": "paraphrase recall rose above chance"}
    return {"verdict": "no_benefit", "reason": "no paraphrase gain"}


def aggregate_hybrid_verdict(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-provider and global hybrid verdict over arm/case/seed rows paired by
    `(provider, case_id, seed, fixture_revision, grants, budgets)`. Global: `unsafe`,
    then `unavailable`, then `harm` if any provider shows it; `benefit` only when every
    provider does; otherwise `no_benefit`."""
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_provider.setdefault(row["provider"], []).append(row)
    per_provider = {
        provider: _provider_verdict(provider_rows)
        for provider, provider_rows in sorted(by_provider.items())
    }
    verdicts = {value["verdict"] for value in per_provider.values()}
    if not verdicts:
        global_verdict = "unavailable"
    else:
        global_verdict = next(
            (v for v in ("unsafe", "unavailable", "harm") if v in verdicts),
            "benefit" if verdicts == {"benefit"} else "no_benefit",
        )
    return {"per_provider": per_provider, "global": {"verdict": global_verdict}}


def write_hybrid_verdict(eval_root: Path) -> Path:
    """Rewrites `<eval_root>/hybrid-verdict.json` from the `verdict_rows` of every
    `<arm>/<route>/memory-suite-report.json`; a route missing an arm has no pair and is
    `unavailable`."""
    rows: list[dict[str, Any]] = []
    for arm in HYBRID_ARMS:
        for report in sorted((eval_root / arm).glob("*/memory-suite-report.json")):
            payload = json.loads(report.read_text(encoding="utf-8"))
            rows.extend(payload.get("verdict_rows") or [])
    eval_root.mkdir(parents=True, exist_ok=True)
    dest_path = eval_root / "hybrid-verdict.json"
    tmp_path = eval_root / "hybrid-verdict.tmp"
    tmp_path.write_text(
        json.dumps(aggregate_hybrid_verdict(rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, dest_path)
    return dest_path
