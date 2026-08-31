"""Unit tests for PromptEvalTool (PR50.2)."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.prompt_eval import PromptEvalTool


def test_prompt_eval_skipped_when_no_records(tmp_path: Path) -> None:
    tool = PromptEvalTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "prompt-eval"
    assert res["status"] == "skipped"
    assert "No recorded golden runs found" in res["summary"]
    assert res["findings"] == []


def test_prompt_eval_all_passing(tmp_path: Path) -> None:
    records_file = tmp_path / "golden_runs.json"
    records_data = [
        {
            "task_id": "task-01",
            "sequence": ["read_file", "edit_file", "run_test"],
            "expected_sequence": ["read_file", "edit_file", "run_test"],
            "patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-1\n+2",
            "expected_patch": "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-1\n+2",
            "tokens": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            "cost": 0.002,
            "passed": True,
        },
        {
            "task_id": "task-02",
            "sequence": ["lint", "format"],
            "expected_sequence": ["lint", "format"],
            "tokens": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
            "cost": 0.001,
            "passed": True,
        },
    ]
    records_file.write_text(json.dumps(records_data), encoding="utf-8")

    tool = PromptEvalTool()
    res = tool.run(records_file)

    assert res["tool"] == "prompt-eval"
    assert res["status"] == "ok"
    assert res["findings"] == []
    assert res["metrics"] is not None
    assert res["metrics"]["total_runs"] == 2
    assert res["metrics"]["passed_runs"] == 2
    assert res["metrics"]["pass_rate"] == 1.0
    assert res["metrics"]["total_tokens"] == 250
    assert res["metrics"]["total_cost"] == 0.003


def test_prompt_eval_sequence_mismatch(tmp_path: Path) -> None:
    records_file = tmp_path / "eval.json"
    records_data = [
        {
            "task_id": "task-mismatch",
            "sequence": ["read_file", "delete_file"],
            "expected_sequence": ["read_file", "edit_file"],
            "passed": True,
        }
    ]
    records_file.write_text(json.dumps(records_data), encoding="utf-8")

    tool = PromptEvalTool()
    res = tool.run(records_file)

    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "prompt-eval/sequence-mismatch"
    assert "sequence mismatch" in res["findings"][0]["message"]


def test_prompt_eval_patch_mismatch(tmp_path: Path) -> None:
    records_file = tmp_path / "eval.json"
    records_data = [
        {
            "task_id": "task-patch-diff",
            "sequence": ["edit_file"],
            "expected_sequence": ["edit_file"],
            "patch": "+x = 1",
            "expected_patch": "+x = 2",
            "passed": True,
        }
    ]
    records_file.write_text(json.dumps(records_data), encoding="utf-8")

    tool = PromptEvalTool()
    res = tool.run(records_file)

    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "prompt-eval/patch-mismatch"


def test_prompt_eval_budget_thresholds(tmp_path: Path) -> None:
    records_file = tmp_path / "eval.json"
    records_data = [
        {
            "task_id": "task-expensive",
            "sequence": ["edit_file"],
            "tokens": {"total_tokens": 5000},
            "cost": 0.50,
            "passed": True,
        }
    ]
    records_file.write_text(json.dumps(records_data), encoding="utf-8")

    tool = PromptEvalTool()
    res = tool.run(
        records_file,
        max_tokens_threshold=4000,
        max_cost_threshold=0.20,
    )

    assert res["status"] == "warn"
    rules = [f["rule"] for f in res["findings"]]
    assert "prompt-eval/token-budget-exceeded" in rules
    assert "prompt-eval/cost-budget-exceeded" in rules


def test_prompt_eval_mcp_call(tmp_path: Path) -> None:
    records_file = tmp_path / "eval.json"
    records_file.write_text(
        json.dumps([{"task_id": "t1", "passed": True}]),
        encoding="utf-8",
    )
    tool = PromptEvalTool()
    res = tool(records_file)
    assert res["status"] == "ok"
