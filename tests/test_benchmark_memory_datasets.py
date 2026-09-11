"""MC13.1/MC13.2 (Phase 63): public benchmark dataset adapters.

Exercises `scripts.benchmarks.memory_datasets` against the bundled
LongMemEval-shaped fixture (`tests/fixtures/benchmarks/memory_datasets.json`).
Gold-answer fields must never reach an evaluated agent; a dataset manifest's
`revision`/`sha256` are mandatory and a hash mismatch fails before any record
is used; independent cases run in a fresh, isolated namespace; native
prediction schemas match each benchmark's official evaluator exactly; a
timed-out or budget-exhausted case still counts in the results denominator.
"""

from __future__ import annotations

import copy
import json

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool
from scripts.benchmarks.contracts import FixtureError
from scripts.benchmarks.fixtures import fixture_path
from scripts.benchmarks.memory_datasets import (
    _validate_section,
    aggregate_dataset_results,
    load_dataset_section,
    run_longmemeval_case,
    to_longmemeval_prediction,
    to_swe_prediction,
)
from scripts.benchmarks.run import (
    _MEMORY_VARIANTS,
    _case_completion_score,
    _run_variant_cases,
    build_parser,
    run_memory_suite,
)


def _raw_longmemeval_section() -> dict:
    raw = json.loads(fixture_path("memory_datasets.json").read_text(encoding="utf-8"))
    return copy.deepcopy(raw["longmemeval"])


def test_longmemeval_gold_fields_never_reach_agent() -> None:
    manifest, records = load_dataset_section("longmemeval")
    assert manifest.dataset == "longmemeval_cleaned_s_sample"
    record = records[0]
    from scripts.benchmarks.memory_datasets import strip_longmemeval_gold

    sanitized, gold = strip_longmemeval_gold(record)

    assert "answer" not in sanitized
    assert "answer_session_ids" not in sanitized
    for session in sanitized["haystack_sessions"]:
        for turn in session["turns"]:
            assert "has_answer" not in turn

    # Legitimate question context is retained.
    assert sanitized["question_id"] == record["question_id"]
    assert sanitized["question_date"] == record["question_date"]
    for sanitized_session, original_session in zip(
        sanitized["haystack_sessions"], record["haystack_sessions"], strict=True
    ):
        assert sanitized_session["session_id"] == original_session["session_id"]
        assert sanitized_session["date"] == original_session["date"]

    # Gold-only fields land in the separate grading payload, never dropped
    # silently and never merged back into `sanitized`.
    assert gold["answer"] == record["answer"]
    assert gold["answer_session_ids"] == record["answer_session_ids"]
    assert len(gold["has_answer"]) == sum(
        len(s["turns"]) for s in record["haystack_sessions"]
    )


def test_dataset_revision_and_hash_required() -> None:
    section = _raw_longmemeval_section()

    missing_revision = copy.deepcopy(section)
    del missing_revision["manifest"]["revision"]
    with pytest.raises(FixtureError):
        _validate_section("longmemeval", missing_revision)

    missing_hash = copy.deepcopy(section)
    del missing_hash["manifest"]["sha256"]
    with pytest.raises(FixtureError):
        _validate_section("longmemeval", missing_hash)

    # A tampered record changes the actual payload hash away from the
    # manifest's declared value -- must fail before any record is returned.
    tampered = copy.deepcopy(section)
    tampered["records"][0]["question"] = "a different question entirely"
    with pytest.raises(FixtureError):
        _validate_section("longmemeval", tampered)

    # The untouched section still validates and returns records.
    manifest, records = _validate_section("longmemeval", section)
    assert manifest.sha256 == section["manifest"]["sha256"]
    assert len(records) == len(section["records"])


def test_independent_cases_reset_namespace(tmp_path) -> None:
    _manifest, records = load_dataset_section("longmemeval")
    assert len(records) >= 2

    def _decide(root, tool, permissions, sanitized):
        session_ids = [s["session_id"] for s in sanitized["haystack_sessions"]]
        query_word = sanitized["question"].split()[-1].strip("?.,!")
        recalled = tool.run(
            root,
            operation="ask",
            subject="episodic",
            query=query_word,
            session_allowlist=session_ids,
        )
        return json.dumps(recalled["raw"])

    result_1 = run_longmemeval_case(
        records[0],
        decide_fn=_decide,
        max_total_tokens=16000,
        workspace_root=tmp_path,
    )
    result_2 = run_longmemeval_case(
        records[1],
        decide_fn=_decide,
        max_total_tokens=16000,
        workspace_root=tmp_path,
    )

    assert result_1.outcome == "scored"
    assert result_2.outcome == "scored"
    assert result_1.prediction is not None
    assert result_2.prediction is not None

    # Case 2's namespace never saw case 1's ingested content, and vice
    # versa -- each case ran in its own fresh temp-directory store.
    assert records[1]["answer"] not in result_1.prediction["hypothesis"]
    assert records[0]["answer"] not in result_2.prediction["hypothesis"]


def test_native_prediction_schema_preserved() -> None:
    prediction = to_longmemeval_prediction("q-1", "some hypothesis")
    assert set(prediction) == {"question_id", "hypothesis"}
    assert prediction["question_id"] == "q-1"
    assert prediction["hypothesis"] == "some hypothesis"

    swe_prediction = to_swe_prediction("repo__issue-1", "--- patch ---", "rush-cli")
    assert set(swe_prediction) == {"instance_id", "model_patch", "model_name_or_path"}
    assert swe_prediction["instance_id"] == "repo__issue-1"
    assert swe_prediction["model_patch"] == "--- patch ---"
    assert swe_prediction["model_name_or_path"] == "rush-cli"


def test_timeout_and_budget_exhaustion_stay_in_denominator(tmp_path) -> None:
    _manifest, records = load_dataset_section("longmemeval")

    def _decide(root, tool, permissions, sanitized):
        return "unused"

    scored = run_longmemeval_case(
        records[0],
        decide_fn=_decide,
        max_total_tokens=16000,
        workspace_root=tmp_path,
    )
    budget_exhausted = run_longmemeval_case(
        records[0],
        decide_fn=_decide,
        max_total_tokens=1,
        workspace_root=tmp_path,
    )
    timed_out = run_longmemeval_case(
        records[0],
        decide_fn=_decide,
        max_total_tokens=16000,
        timeout_seconds=-1.0,
        workspace_root=tmp_path,
    )

    assert scored.outcome == "scored"
    assert budget_exhausted.outcome == "budget_exhausted"
    assert budget_exhausted.prediction is None
    assert timed_out.outcome == "timeout"
    assert timed_out.prediction is None

    aggregate = aggregate_dataset_results([scored, budget_exhausted, timed_out])
    assert aggregate["total"] == 3
    assert aggregate["scored"] == 1
    assert aggregate["budget_exhausted"] == 1
    assert aggregate["timeout"] == 1


def test_variant_cases_produce_distinct_real_hypotheses(tmp_path) -> None:
    """MC13.4 fix: each named variant is a genuinely different retrieval
    path over the same cases -- `none` never touches the memory tool while
    `raw` concatenates the full haystack text, so their real hypotheses
    differ. This is the actual cross-variant comparison the old
    seed-vs-seed-of-one-variant check never exercised."""
    _manifest, records = load_dataset_section("longmemeval")

    none_results = _run_variant_cases(
        records, "none", max_total_tokens=16000, workspace_root=tmp_path
    )
    raw_results = _run_variant_cases(
        records, "raw", max_total_tokens=16000, workspace_root=tmp_path
    )

    assert len(none_results) == len(records)
    assert len(raw_results) == len(records)
    for none_case, raw_case in zip(none_results, raw_results, strict=True):
        assert none_case.outcome == "scored"
        assert raw_case.outcome == "scored"
        assert none_case.prediction["hypothesis"] == ""
        assert raw_case.prediction["hypothesis"] != ""


def test_cross_variant_comparison_produces_per_case_per_variant_scores(
    tmp_path,
) -> None:
    """MC13.4 fix: `run_memory_suite` runs the SAME cases through all seven
    named variants at fixed settings/budgets and reports real per-case,
    per-variant completion scores plus a genuine paired-bootstrap CI over
    real cross-variant score differences -- not seed noise within one
    variant."""
    args = build_parser().parse_args(
        ["--suite", "memory", "--output", str(tmp_path / "out")]
    )

    exit_code = run_memory_suite(args)
    assert exit_code == 0

    report = json.loads(
        (tmp_path / "out" / "memory-suite-report.json").read_text(encoding="utf-8")
    )

    comparison = report["cross_variant_comparison"]
    assert comparison["baseline_variant"] == "none"
    _manifest, records = load_dataset_section("longmemeval")
    assert len(comparison["case_ids"]) == len(records)

    per_variant = comparison["per_variant"]
    assert set(per_variant) == set(_MEMORY_VARIANTS)
    for variant in _MEMORY_VARIANTS:
        entry = per_variant[variant]
        assert len(entry["case_scores"]) == len(records)
        assert len(entry["diff_vs_baseline"]) == len(records)
        assert "low" in entry["paired_bootstrap_ci"]
        assert "high" in entry["paired_bootstrap_ci"]

    # The baseline variant diffed against itself is exactly zero everywhere
    # -- a real, honest identity, never fabricated variance.
    assert per_variant["none"]["diff_vs_baseline"] == [0.0] * len(records)

    # The old, misleadingly-named field is gone; the honest seed-noise field
    # (a genuinely different measurement) takes its place.
    assert "paired_bootstrap_ci_vs_first_seed" not in report
    seed_noise = report["paired_bootstrap_ci_seed_noise_within_variant"]
    assert seed_noise["variant"] == args.variant
    assert "low" in seed_noise and "high" in seed_noise


def test_case_completion_score_reflects_real_outcome(tmp_path) -> None:
    _manifest, records = load_dataset_section("longmemeval")

    def _decide(root, tool, permissions, sanitized):
        return "unused"

    scored = run_longmemeval_case(
        records[0], decide_fn=_decide, max_total_tokens=16000, workspace_root=tmp_path
    )
    budget_exhausted = run_longmemeval_case(
        records[0], decide_fn=_decide, max_total_tokens=1, workspace_root=tmp_path
    )

    assert _case_completion_score(scored) == 1.0
    assert _case_completion_score(budget_exhausted) == 0.0


def test_memory_tool_write_used_for_ingestion_sanity(tmp_path) -> None:
    """Sanity check that the harness's own `MemoryTool` wiring (reused, not
    duplicated) still writes real artifacts -- guards against a future
    refactor silently swapping in a fake store."""
    tool = MemoryTool()
    result = tool.run(
        tmp_path,
        operation="write",
        subject="episodic",
        content={"text": "sanity"},
        source="s1",
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert result["status"] == "ok"
