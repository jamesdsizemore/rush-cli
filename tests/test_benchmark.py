"""Unit tests for BenchmarkTool (PR50.13)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.benchmark import BenchmarkTool


def test_benchmark_skipped_when_no_baseline(tmp_path: Path) -> None:
    tool = BenchmarkTool()
    res = tool.run(tmp_path, samples=[10.0, 11.0, 10.5])

    assert res["tool"] == "benchmark"
    assert res["status"] == "skipped"
    assert "not found in .rush/baselines.json" in res["summary"]
    assert res["findings"] == []


def test_benchmark_record_requires_allow_cache_write(tmp_path: Path) -> None:
    tool = BenchmarkTool()
    res = tool.run(
        tmp_path,
        samples=[10.0, 11.0, 10.5],
        record=True,
        permissions=ExecutionPermissions(),
    )

    assert res["status"] == "skipped"
    assert "--allow-cache-write" in res["summary"]


def test_benchmark_record_and_evaluate_passing(tmp_path: Path) -> None:
    tool = BenchmarkTool()
    # 1. Record baseline with permission
    record_res = tool.run(
        tmp_path,
        samples=[100.0, 102.0, 98.0],
        record=True,
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert record_res["status"] == "ok"
    assert (tmp_path / ".rush" / "baselines.json").is_file()

    # 2. Evaluate sample that is fast / within threshold (mean ~101 vs baseline ~100 -> 1% delta < 5%)
    eval_res = tool.run(
        tmp_path,
        samples=[101.0, 100.5, 101.5],
        threshold_percent=5.0,
    )
    assert eval_res["status"] == "ok"
    assert eval_res["findings"] == []
    assert eval_res["metrics"] is not None
    assert eval_res["metrics"]["regression_pct"] <= 5.0


def test_benchmark_detects_regression(tmp_path: Path) -> None:
    tool = BenchmarkTool()
    # 1. Record baseline 100.0
    tool.run(
        tmp_path,
        samples=[100.0],
        record=True,
        permissions=ExecutionPermissions(cache_write=True),
    )

    # 2. Run with regressed sample 120.0 (+20% regression > 5% threshold)
    res = tool.run(
        tmp_path,
        samples=[120.0],
        threshold_percent=5.0,
    )

    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "benchmark/performance-regression"
    assert "Performance regressed by 20.00%" in res["findings"][0]["message"]


def test_benchmark_ignores_nan_and_inf_samples(tmp_path: Path) -> None:
    tool = BenchmarkTool()
    tool.run(
        tmp_path,
        samples=[100.0, float("nan"), float("inf"), 100.0],
        record=True,
        permissions=ExecutionPermissions(cache_write=True),
    )

    # Clean samples only: mean should be 100.0
    baselines_file = tmp_path / ".rush" / "baselines.json"
    assert baselines_file.is_file()

    import json

    data = json.loads(baselines_file.read_text(encoding="utf-8"))
    assert data["default"]["mean"] == 100.0
    assert data["default"]["count"] == 2
