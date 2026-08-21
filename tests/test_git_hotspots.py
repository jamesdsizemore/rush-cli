"""Tests for Phase 37: Git Hotspots, Code Churn & Developer Velocity."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rush.hotspots.complexity import CyclomaticComplexityCalculator
from rush.hotspots.function_churn import FunctionChurnMapper
from rush.hotspots.risk_matrix import RiskMatrixCalculator
from rush.hotspots.secret_scrubber import SecretScrubber
from rush.hotspots.time_decay import TimeDecayCalculator


def test_secret_scrubber() -> None:
    msg = "feat: update api_key = 'sk-1234567890abcdef1234567890abcdef1234567890abcdef' in auth"
    scrubbed = SecretScrubber.scrub_text(msg)
    assert "[REDACTED]" in scrubbed


def test_time_decay_calculator() -> None:
    calc = TimeDecayCalculator(half_life_days=90.0)
    now = datetime.now(timezone.utc)
    weight_now = calc.calculate_weight(now, current_date=now)
    assert weight_now == 1.0

    past = datetime.fromtimestamp(now.timestamp() - (90 * 86400), tz=timezone.utc)
    weight_past = calc.calculate_weight(past, current_date=now)
    assert round(weight_past, 2) == 0.50


def test_cyclomatic_complexity_calculator(tmp_path: Path) -> None:
    py_code = """
def complex_fn(x: int) -> int:
    if x > 10:
        for i in range(x):
            if i % 2 == 0:
                print(i)
    elif x < 0:
        while x < 0:
            x += 1
    return x
"""
    f = tmp_path / "complex.py"
    f.write_text(py_code, encoding="utf-8")
    score = CyclomaticComplexityCalculator.calculate_file(f)
    assert score >= 6


def test_function_churn_mapper(tmp_path: Path) -> None:
    py_code = """
def fn_one():
    print("line 2")
    print("line 3")

def fn_two():
    print("line 6")
"""
    f = tmp_path / "funcs.py"
    f.write_text(py_code, encoding="utf-8")

    findings = FunctionChurnMapper.map_file_function_churn(f, {2, 3})
    assert len(findings) == 1
    assert findings[0].function_name == "fn_one"
    assert findings[0].churn_lines == 2


def test_risk_matrix_calculator(tmp_path: Path) -> None:
    calc = RiskMatrixCalculator(tmp_path)
    scores = calc.analyze_hotspots()
    assert isinstance(scores, list)
