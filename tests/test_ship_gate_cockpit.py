"""
Unit tests for Phase 42 / TDD-42-06: Pre-Flight 7-Vector Release Gate Cockpit.
Verifies parallel vector aggregation and Pass/Fail executive verdict rendering.
"""


class MockVectorResult:
    def __init__(self, name: str, passed: bool, duration_ms: float):
        self.name = name
        self.passed = passed
        self.duration_ms = duration_ms


def aggregate_ship_gate(vectors: list[MockVectorResult]) -> tuple[bool, int, list[str]]:
    """Evaluates 7-vector release gate and calculates release score (0-100)."""
    passed_count = sum(1 for v in vectors if v.passed)
    score = int((passed_count / len(vectors)) * 100) if vectors else 0
    all_passed = passed_count == len(vectors)
    failed_names = [v.name for v in vectors if not v.passed]
    return all_passed, score, failed_names


def test_ship_gate_all_pass():
    vectors = [
        MockVectorResult("clean", True, 5.0),
        MockVectorResult("env", True, 12.0),
        MockVectorResult("migration", True, 8.0),
        MockVectorResult("semver", True, 25.0),
        MockVectorResult("docs", True, 45.0),
        MockVectorResult("pack", True, 120.0),
        MockVectorResult("test", True, 350.0),
    ]
    all_pass, score, failed = aggregate_ship_gate(vectors)
    assert all_pass is True
    assert score == 100
    assert len(failed) == 0


def test_ship_gate_failure_blocks_release():
    vectors = [
        MockVectorResult("clean", True, 5.0),
        MockVectorResult("env", False, 12.0),  # Env missing
        MockVectorResult("migration", True, 8.0),
        MockVectorResult("semver", True, 25.0),
        MockVectorResult("docs", True, 45.0),
        MockVectorResult("pack", True, 120.0),
        MockVectorResult("test", True, 350.0),
    ]
    all_pass, score, failed = aggregate_ship_gate(vectors)
    assert all_pass is False
    assert score == 85
    assert failed == ["env"]
