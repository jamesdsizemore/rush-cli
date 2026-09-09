"""MC00 deterministic memory benchmark contracts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.benchmarks import memory
from scripts.benchmarks.contracts import FixtureError, Outcome, Scenario
from scripts.benchmarks.fixtures import load_memory_cases, load_scenarios
from scripts.benchmarks.memory import run_memory_probe
from scripts.benchmarks.run import get_probe_runner, main


def _scenario(case_id: str, **input_overrides: object) -> Scenario:
    payload: dict[str, object] = {
        "fixture": "memory_cases.json",
        "case_id": case_id,
    }
    payload.update(input_overrides)
    return Scenario(
        scenario_id=case_id,
        probe="memory",
        category="memory",
        input=payload,
        required_facts=("actual_memory_tool",),
        expected_outcome=Outcome.PASS,
    )


def test_memory_probe_uses_real_store(tmp_path: Path) -> None:
    assert get_probe_runner("memory") is run_memory_probe
    assert [case["scenario_id"] for case in load_memory_cases()] == [
        "M01",
        "M03",
        "M05",
        "M06",
        "M09",
        "M10",
    ]
    result = run_memory_probe(_scenario("M01"), output_root=tmp_path)

    assert result.outcome == Outcome.PASS
    assert result.metrics["artifact_count"] == 100
    assert result.metrics["serialized_bytes"] > 8192
    assert result.metrics["token_count"] > 0
    assert result.metrics["token_method"] == "tiktoken:cl100k_base"
    assert result.metrics["elapsed_ms"] >= 0
    assert len(result.metrics["source_hash"]) == 64
    assert len(result.metrics["scenario_hash"]) == 64


def test_memory_baseline_records_over_budget_payload(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M06"), output_root=tmp_path)

    assert result.outcome == Outcome.PASS
    assert result.metrics["serialized_bytes"] > 8192
    assert result.metrics["payload_truncated"] is False


def test_memory_probe_keeps_denied_content_out_of_results(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M05"), output_root=tmp_path)

    serialized = json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.metrics["denied_id_visible"] is False
    assert result.metrics["denied_source_visible"] is False
    assert "D1" not in serialized
    assert "DENIED_SECRET" not in serialized


def test_memory_probe_rejects_fixture_path_escape() -> None:
    with pytest.raises(FixtureError, match="fixture path denied"):
        load_memory_cases("../outside.json")


def test_memory_scenarios_are_public_and_write_probe_results(tmp_path: Path) -> None:
    scenarios = load_scenarios()
    for case_id in ("M01", "M03", "M05", "M06", "M09", "M10"):
        assert scenarios[case_id].probe == "memory"
    output = tmp_path / "public"
    assert main(["--scenario", "M01", "--output", str(output)]) == 0
    result = json.loads((output / "M01.json").read_text(encoding="utf-8"))
    assert result["probe"] == "memory"
    assert result["metrics"]["artifact_count"] == 100


def test_memory_probe_repeat_isolated_and_rejects_unsafe_id(tmp_path: Path) -> None:
    first = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    second = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    assert first.metrics["artifact_count"] == 100
    assert second.metrics["artifact_count"] == 100
    assert not list(tmp_path.glob("memory-*"))

    with pytest.raises(FixtureError, match="scenario path denied"):
        run_memory_probe(
            replace(_scenario("M01"), scenario_id="../outside"), output_root=tmp_path
        )
    assert not (tmp_path.parent / "outside").exists()


def test_memory_probe_fails_if_denied_allowlist_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = memory.MemoryTool

    class RecordingTool:
        def __init__(self) -> None:
            self.delegate = original()

        def run(self, root: Path, **kwargs: object) -> dict[str, object]:
            if kwargs.get("operation") == "ask":
                kwargs["session_allowlist"] = ["allowed", "denied"]
            return self.delegate.run(root, **kwargs)

    monkeypatch.setattr(memory, "MemoryTool", RecordingTool)
    result = run_memory_probe(_scenario("M05"), output_root=tmp_path)

    assert result.outcome == Outcome.FAIL
    assert result.metrics["denied_id_visible"] is True


def test_memory_probe_metrics_match_recorded_tool_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = memory.MemoryTool
    captured: dict[str, object] = {}

    class RecordingTool:
        def __init__(self) -> None:
            self.delegate = original()

        def run(self, root: Path, **kwargs: object) -> dict[str, object]:
            result = self.delegate.run(root, **kwargs)
            if kwargs.get("operation") == "ask":
                captured["result"] = result
            return result

    monkeypatch.setattr(memory, "MemoryTool", RecordingTool)
    result = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    recorded = captured["result"]
    assert isinstance(recorded, dict)
    serialized = json.dumps(recorded, ensure_ascii=False, separators=(",", ":"))
    assert result.metrics["serialized_bytes"] == len(serialized.encode("utf-8"))
    assert result.metrics["token_count"] == len(
        memory.tiktoken.get_encoding("cl100k_base").encode(serialized)
    )
