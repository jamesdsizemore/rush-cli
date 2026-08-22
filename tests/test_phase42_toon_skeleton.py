"""Unit tests for Phase 42 TOON Serialization and AST Skeletonizer."""

from pathlib import Path

from src.rush.memory.merkle_invalidator import MerkleInvalidator
from src.rush.token_economy.ast_skeletonizer import AstSkeletonizer
from src.rush.token_economy.toon import decode_toon, encode_toon


def test_toon_roundtrip():
    data = [
        {"id": "1", "tool": "pytest", "status": "ok"},
        {"id": "2", "tool": "ruff", "status": "ok"},
    ]
    encoded = encode_toon(data)
    assert "|id|tool|status|" in encoded
    assert "|1|pytest|ok|" in encoded

    decoded = decode_toon(encoded)
    assert len(decoded) == 2
    assert decoded[0]["id"] == "1"
    assert decoded[0]["tool"] == "pytest"
    assert decoded[1]["status"] == "ok"


def test_toon_empty_data():
    assert encode_toon([]) == ""
    assert decode_toon("") == []


def test_ast_skeletonizer_python():
    code = (
        "def calculate_metrics(items: list[int]) -> int:\n"
        '    """Sum up all items."""\n'
        "    total = sum(items)\n"
        "    return total\n\n"
        "def run_task():\n"
        "    do_something()\n"
    )
    skeletonizer = AstSkeletonizer()
    res = skeletonizer.skeletonize_python(code)
    assert "Sum up all items" in res
    assert "..." in res
    assert "total = sum(items)" not in res
    assert "do_something()" not in res


def test_ast_skeletonizer_focus_symbol():
    code = "def helper_fn():\n    return 1\n\ndef target_fn():\n    important_logic()\n"
    skeletonizer = AstSkeletonizer()
    res = skeletonizer.skeletonize_python(code, focus_symbol="target_fn")
    assert "important_logic()" in res
    assert "return 1" not in res


def test_merkle_invalidator(tmp_path: Path):
    invalidator = MerkleInvalidator(project_root=tmp_path)
    key = "func:calculate_metrics"

    # First time: change detected
    assert invalidator.check_and_update(key, "def foo(): pass") is True

    # Second time with identical content: no change
    assert invalidator.check_and_update(key, "def foo(): pass") is False

    # Third time with updated content: change detected
    assert invalidator.check_and_update(key, "def foo(): return 42") is True
