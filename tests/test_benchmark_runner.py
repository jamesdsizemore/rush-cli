"""Tests for benchmark runner dispatcher, CLI entrypoint, and atomic reporting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.benchmarks import run as benchmark_run
from scripts.benchmarks.contracts import (
    SCHEMA_VERSION,
    FixtureError,
    Outcome,
    ProbeResult,
    SourceEvidence,
)
from scripts.benchmarks.reporting import write_handoff, write_result
from scripts.benchmarks.run import build_parser


def test_parser_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--scenario",
            "handoff-claude-to-cursor-01",
            "--output",
            "research/benchmark/B1",
        ]
    )
    assert args.scenario == "handoff-claude-to-cursor-01"
    assert args.output == Path("research/benchmark/B1")
    assert args.model_cache is None
    assert args.allow_live_route == []
    assert args.allow_model_download == []


def test_model_download_opt_in_activates_local_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    captured = {}

    def probe(scenario, **_kwargs):
        captured["input"] = scenario.input
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.DEFERRED,
            started_at="2026-08-24T00:00:00Z",
            duration_ms=0,
            metrics={},
            fallback="onnxruntime-perf-test-missing",
        )

    monkeypatch.setattr(benchmark_run, "get_probe_runner", lambda _name: probe)

    benchmark_run.run_scenario(
        "local-granite-278m-c0",
        tmp_path,
        model_cache=tmp_path / "external-cache",
        allow_model_download=["granite-278m-embedding"],
    )

    assert "mode" not in captured["input"]


def test_write_result_atomic_and_path_security(tmp_path: Path):
    output_dir = tmp_path / "B1"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = ProbeResult(
        scenario_id="sc-atomic-01",
        probe="context",
        outcome=Outcome.PASS,
        started_at="2026-08-24T00:00:00Z",
        duration_ms=50,
        metrics={"tokens_raw": 1000, "tokens_packed": 400},
        reproduction="python -m scripts.benchmarks.run --scenario sc-atomic-01",
    )

    dest = write_result(output_dir, result)
    assert dest.exists()
    assert dest.name == "sc-atomic-01.json"

    # Temporary file is cleaned up
    tmp_file = output_dir / "sc-atomic-01.tmp"
    assert not tmp_file.exists()

    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["outcome"] == "pass"


def test_write_result_rejects_path_escape(tmp_path: Path):
    safe_root = tmp_path / "research" / "benchmark" / "B1"
    safe_root.mkdir(parents=True, exist_ok=True)

    # Result with path traversal scenario ID
    result = ProbeResult(
        scenario_id="../escape",
        probe="context",
        outcome=Outcome.FAIL,
        started_at="2026-08-24T00:00:00Z",
        duration_ms=10,
        metrics={},
    )
    with pytest.raises(FixtureError, match="denied"):
        write_result(safe_root, result)


def test_write_handoff_validation(tmp_path: Path):
    handoff_path = tmp_path / "final-handoff.md"
    evidence = SourceEvidence(url="https://example.com/docs", retrieved_at="2026-08-24")

    # Incomplete decision lacking result_path
    incomplete_decisions = [
        {
            "decision_id": "B-D01",
            "title": "Control Baseline",
            "status": "pass",
            "unblocked_task": "P2-T01",
            "fixture_ids": ["sc-01"],
            "result_path": "",
            "evidence": [evidence],
            "fallback": "none",
            "reproduction": "cmd",
        }
    ]
    with pytest.raises(FixtureError, match="incomplete decision"):
        write_handoff(incomplete_decisions, handoff_path)

    # Complete decision succeeds
    valid_decisions = [
        {
            "decision_id": "B-D01",
            "title": "Control Baseline",
            "status": "pass",
            "unblocked_task": "P2-T01",
            "fixture_ids": ["sc-01"],
            "result_path": "research/benchmark/B1/decision-B-D01.json",
            "evidence": [evidence],
            "fallback": "manual review",
            "reproduction": "python -m scripts.benchmarks.run --scenario sc-01",
        }
    ]
    write_handoff(valid_decisions, handoff_path)
    assert handoff_path.exists()
    content = handoff_path.read_text(encoding="utf-8")
    assert "B-D01" in content
    assert "P2-T01" in content


def test_runner_generates_all_decisions_and_handoff(tmp_path: Path):
    from scripts.benchmarks.run import main

    out_dir = tmp_path / "research" / "benchmark" / "run"
    exit_code = main(["--all", "--output", str(out_dir)])
    assert exit_code == 0

    # Assert decision JSONs exist beneath caller output directory
    assert (out_dir / "B1/decision-B-D01-B-D02.json").exists()
    assert (out_dir / "B2/decision-B-D07-B-D10.json").exists()
    assert (out_dir / "B3/decision-B-D03.json").exists()
    assert (out_dir / "B4/decision-B-D04-B-D05.json").exists()
    assert (out_dir / "B5/decision-B-D11.json").exists()
    assert (out_dir / "B6/decision-B-D06.json").exists()

    # Evidence remains under the caller-selected output directory. This keeps
    # benchmark runs reproducible in clean worktrees without writing ignored
    # repository-local result directories.

    # Assert final-handoff.md and hardware-profile.json were written
    assert (out_dir / "final-handoff.md").exists()
    assert (out_dir / "hardware-profile.json").exists()
    assert Path("docs/reports/final-handoff.md").exists()
    handoff_text = (out_dir / "final-handoff.md").read_text(encoding="utf-8")
    assert "B-D01" in handoff_text
    assert "B-D06" in handoff_text
    assert "B-D11" in handoff_text
