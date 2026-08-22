"""Unit tests for Phase 41 ContentRouter and Command Distillers."""

from src.rush.token_economy.distillers import get_distiller_for_command
from src.rush.token_economy.distillers.cargo_distiller import CargoDistiller
from src.rush.token_economy.distillers.pytest_distiller import PytestDistiller
from src.rush.token_economy.distillers.ruff_distiller import RuffDistiller
from src.rush.token_economy.distillers.vitest_distiller import VitestDistiller
from src.rush.token_economy.router import ContentRouter, ContentType


def test_content_router_classification():
    router = ContentRouter()

    # Python code
    code = "def foo():\n    return 42"
    assert router.classify(code, "main.py") == ContentType.AST_CODE

    # Test log
    assert router.classify("FAILED test_foo.py - assert 1 == 2") == ContentType.TEST_LOG

    # Tabular
    assert router.classify('[{"a": 1}, {"a": 2}]') == ContentType.TABULAR_DATA

    # Markdown prose
    assert (
        router.classify("# Introduction\nThis is a report.")
        == ContentType.PROSE_MARKDOWN
    )


def test_content_router_token_counting():
    router = ContentRouter()
    count = router.count_tokens("Hello world from Rush CLI!")
    assert count > 0
    assert router.count_tokens("") == 0


def test_pytest_distiller_success():
    distiller = PytestDistiller()
    assert distiller.can_distill(["pytest", "tests/"])
    res = distiller.distill("All tests passed", "", 0)
    assert res.failure_count == 0
    assert res.passed_count == 1


def test_pytest_distiller_failure_compression():
    distiller = PytestDistiller()
    raw = """
============================= test session starts =============================
rootdir: /repo
collected 100 items

tests/test_auth.py ..F...                                                [100%]

=================================== FAILURES ===================================
_________________________________ test_login ___________________________________

    def test_login():
>       assert login("wrong") is True
E       AssertionError: assert False is True

tests/test_auth.py:42: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_auth.py::test_login - AssertionError: assert False is True
======================== 1 failed, 99 passed in 2.14s =========================
"""
    res = distiller.distill(raw, "", 1)
    assert res.failure_count == 1
    assert "test login" in res.failures[0]["test"]
    assert res.savings_pct > 50.0


def test_cargo_distiller():
    distiller = CargoDistiller()
    assert distiller.can_distill(["cargo", "test"])
    raw = "error[E0425]: cannot find value `foo` in this scope\n --> src/main.rs:5:10"
    res = distiller.distill(raw, "", 101)
    assert res.failure_count >= 1
    assert "error[E0425]" in res.distilled_text


def test_ruff_distiller():
    distiller = RuffDistiller()
    assert distiller.can_distill(["ruff", "check"])
    raw = "src/main.py:10:1: F401 `os` imported but unused"
    res = distiller.distill(raw, "", 1)
    assert res.failure_count == 1
    assert "F401" in res.distilled_text


def test_vitest_distiller():
    distiller = VitestDistiller()
    assert distiller.can_distill(["vitest", "run"])
    raw = (
        "FAIL src/app.test.ts > renders app\nAssertionError: expected true to be false"
    )
    res = distiller.distill(raw, "", 1)
    assert res.failure_count >= 1
    assert "FAIL" in res.distilled_text


def test_get_distiller_lookup():
    assert isinstance(get_distiller_for_command(["pytest", "-q"]), PytestDistiller)
    assert isinstance(get_distiller_for_command(["cargo", "test"]), CargoDistiller)
    assert isinstance(get_distiller_for_command(["ruff", "check"]), RuffDistiller)
    assert isinstance(get_distiller_for_command(["vitest"]), VitestDistiller)
    assert get_distiller_for_command(["unknown_tool"]) is None
