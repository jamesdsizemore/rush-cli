"""
Unit tests for Phase 41 / TDD-41-02: ContentRouter Payload Classification.
Tests automatic detection of AST code, Pytest logs, JSON tables, and prose.
"""

from enum import Enum


class ContentType(str, Enum):
    AST_CODE = "ast_code"
    TEST_LOG = "test_log"
    TABULAR_DATA = "tabular_data"
    PROSE_MARKDOWN = "prose_markdown"


def classify_payload(content: str) -> ContentType:
    """Classifies input text payload to route to optimal compressor."""
    lines = content.strip().splitlines()
    if not lines:
        return ContentType.PROSE_MARKDOWN

    first_line = lines[0].strip()
    if any(
        first_line.startswith(kw)
        for kw in ("def ", "class ", "import ", "from ", "pub fn ", "function ")
    ):
        return ContentType.AST_CODE
    if any(
        "FAILED" in line
        or "PASSED" in line
        or "=== FAILURES ===" in line
        or "error[E" in line
        for line in lines[:10]
    ):
        return ContentType.TEST_LOG
    if first_line.startswith(("[", "{")) and (lines[-1].strip().endswith(("]", "}"))):
        return ContentType.TABULAR_DATA
    return ContentType.PROSE_MARKDOWN


def test_classify_python_code():
    code = "def process_queue(items: list[str]) -> bool:\n    return len(items) > 0"
    assert classify_payload(code) == ContentType.AST_CODE


def test_classify_pytest_log():
    log = "=== FAILURES ===\n____ test_grounding_verifier ____\nassert False\nFAILED tests/test_grounding.py - assert False"
    assert classify_payload(log) == ContentType.TEST_LOG


def test_classify_json_table():
    data = '[{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]'
    assert classify_payload(data) == ContentType.TABULAR_DATA


def test_classify_prose():
    prose = "## Executive Summary\nThis report outlines the architecture for Context Intelligence."
    assert classify_payload(prose) == ContentType.PROSE_MARKDOWN
