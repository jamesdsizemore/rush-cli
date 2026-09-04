"""Unit tests for the AST contract verification engine."""

from __future__ import annotations

from scripts.verify_tool_contracts import verify_source


def test_rejects_banned_placeholder_in_production() -> None:
    bad_code = """
def analyze():
    return {"survival": "unknown"}
"""
    errors = verify_source(bad_code, filename="prod.py", is_test=False)
    assert len(errors) == 1
    assert "Banned placeholder string 'unknown'" in errors[0]


def test_allows_clean_production_code() -> None:
    clean_code = """
def analyze():
    return {"survival": 0.85, "status": "ok"}
"""
    errors = verify_source(clean_code, filename="prod.py", is_test=False)
    assert errors == []


def test_rejects_tautological_assertion_in_tests() -> None:
    bad_test = """
def test_something():
    res = {"status": "unknown"}
    assert res["status"] == "unknown"
"""
    errors = verify_source(bad_test, filename="test_bad.py", is_test=True)
    assert len(errors) == 1
    assert "Banned tautological assertion testing for 'unknown'" in errors[0]


def test_rejects_permissive_status_set_assertion() -> None:
    bad_test = """
def test_something():
    status = "warn"
    assert status in ("ok", "warn", "skipped")
"""
    errors = verify_source(bad_test, filename="test_bad.py", is_test=True)
    assert len(errors) == 1
    assert "Permissive assertion allows any status" in errors[0]


def test_rejects_fake_fallback_injection() -> None:
    bad_code = """
def get_actions():
    all_actions = fetch()
    if not all_actions:
        all_actions = {"s3:GetObject", "s3:PutObject"}
    return all_actions
"""
    errors = verify_source(bad_code, filename="tool.py", is_test=False)
    assert len(errors) == 1
    assert "Fake fallback injection detected for variable 'all_actions'" in errors[0]


def test_allows_exact_deterministic_assertions() -> None:
    good_test = """
def test_exact():
    status = "ok"
    assert status == "ok"
    assert 0.85 > 0.5
"""
    errors = verify_source(good_test, filename="test_good.py", is_test=True)
    assert errors == []
