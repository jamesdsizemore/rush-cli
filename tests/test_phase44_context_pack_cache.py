"""Unit tests for Phase 44 StaleSweeper, CacheAligner, and ContextPacker."""

from pathlib import Path

from src.rush.codegraph.context_packer import ContextPacker
from src.rush.token_economy.cache_aligner import CacheAligner
from src.rush.token_economy.stale_sweeper import StaleSweeper


def test_stale_sweeper():
    sweeper = StaleSweeper(keep_recent_turns=1)

    # Session with 3 turns
    turns = [
        {"role": "user", "content": "Read file a.py"},
        {
            "role": "assistant",
            "content": "def func():\n" + ("    print('lots of code')\n" * 50),
        },
        {"role": "user", "content": "What is next?"},
    ]

    swept = sweeper.sweep_history(turns)
    assert len(swept) == 3
    # Turn 1 is stale and should be collapsed
    assert swept[1].get("stale_pruned") is True
    assert "<!-- stale_read: collapsed" in swept[1]["content"]
    # Turn 2 is active turn and preserved
    assert swept[2]["content"] == "What is next?"


def test_cache_aligner():
    aligner = CacheAligner(min_prefix_tokens=100)

    short_system = "You are a coding assistant."
    aligned = aligner.align_prompt(short_system)
    assert aligned["cache_aligned"] is True
    assert aligned["system"]["aligned_tokens"] >= 100
    assert aligned["system"]["padded"] is True
    assert aligned["system"]["cache_control"] == {"type": "ephemeral"}


def test_context_packer(tmp_path: Path):
    target = tmp_path / "service.py"
    code = """
class AuthService:
    def authenticate(self, user: str, token: str) -> bool:
        if token == "secret":
            return True
        return False

    def revoke(self, token: str) -> None:
        pass
"""
    target.write_text(code.strip(), encoding="utf-8")

    packer = ContextPacker(project_root=tmp_path)
    res = packer.pack(target, target_symbol="authenticate", max_tokens=500)

    assert "error" not in res
    assert res["tokens"] > 0
    assert "AuthService" in res["packed_text"]
    assert "if token ==" in res["packed_text"]
    assert "def revoke" in res["packed_text"]
