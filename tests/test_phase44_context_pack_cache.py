"""Unit tests for Phase 44 StaleSweeper, CacheAligner, and ContextPacker."""

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.continuity import SessionContinuityTool
from src.rush.codegraph.context_packer import ContextPacker
from src.rush.token_economy.cache_aligner import CacheAligner
from src.rush.token_economy.ccr_store import CCRStore
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


def test_continuity_context_pack_returns_bounded_evidence_envelope(tmp_path: Path):
    target = tmp_path / "service.py"
    target.write_text(
        "def authenticate(token: str) -> bool:\n"
        "    api_key = 'sk-ant-abcdefghijklmnopqrstuvwxyz012345'\n"
        "    return bool(token)\n",
        encoding="utf-8",
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="context_pack",
        context_path="service.py",
        target_symbol="authenticate",
        token_budget=500,
    )

    assert result["tool"] == "continuity"
    assert result["status"] == "ok"
    envelope = result["metadata"]["context_envelope"]
    assert envelope["selected_evidence"][0]["path"] == "service.py"
    assert envelope["tokens"]["estimated"] > 0
    assert envelope["tokens"]["actual"] is None
    assert envelope["omissions"] == []
    assert envelope["recovery"] == {"state": "not_needed"}
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz012345" not in result["raw"]["packed_text"]


def test_continuity_context_pack_fails_closed_when_budget_is_insufficient(
    tmp_path: Path,
):
    target = tmp_path / "service.py"
    target.write_text(
        "def authenticate() -> bool:\n    return True\n", encoding="utf-8"
    )

    result = SessionContinuityTool().run(
        tmp_path, operation="context_pack", context_path="service.py", token_budget=1
    )

    assert result["status"] == "skipped"
    assert result["metadata"]["context_envelope"]["omissions"] == [
        {"reason": "insufficient_budget", "mandatory": True}
    ]


def test_continuity_context_retrieve_returns_or_explicitly_misses_handle(
    tmp_path: Path,
):
    tag = CCRStore(tmp_path).store_chunk("selected source")
    handle = tag.split(":")[2].split()[0]

    found = SessionContinuityTool().run(
        tmp_path, operation="context_retrieve", context_handle=handle
    )
    missing = SessionContinuityTool().run(
        tmp_path, operation="context_retrieve", context_handle="f" * 64
    )

    assert found["status"] == "ok"
    assert found["raw"] == {"content": "selected source"}
    assert found["metadata"]["context_envelope"]["recovery"] == {
        "state": "recovered",
        "handle": handle,
    }
    assert missing["status"] == "skipped"
    assert missing["metadata"]["context_envelope"]["recovery"] == {
        "state": "not_found",
        "handle": "f" * 64,
    }


def test_continuity_overflow_requires_cache_write_and_preserves_target_evidence(
    tmp_path: Path,
):
    target = tmp_path / "service.py"
    target.write_text(
        "def authenticate() -> bool:\n    return True\n", encoding="utf-8"
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="context_pack",
        context_path="service.py",
        token_budget=1,
    )

    envelope = result["metadata"]["context_envelope"]
    assert result["status"] == "skipped"
    assert envelope["selected_evidence"] == [
        {"path": "service.py", "selection": "target_file"}
    ]
    assert envelope["recovery"] == {
        "state": "not_created",
        "reason": "cache_write_required",
    }
    assert not (tmp_path / ".rush" / "cache" / "ccr.db").exists()


def test_continuity_overflow_records_local_token_telemetry_without_provider_cost(
    tmp_path: Path,
):
    target = tmp_path / "service.py"
    target.write_text(
        "def authenticate() -> bool:\n    return True\n", encoding="utf-8"
    )

    result = SessionContinuityTool().run(
        tmp_path,
        operation="context_pack",
        context_path="service.py",
        token_budget=1,
        permissions=ExecutionPermissions(cache_write=True),
    )

    envelope = result["metadata"]["context_envelope"]
    assert result["status"] == "skipped"
    assert envelope["recovery"]["state"] == "available"
    assert envelope["telemetry"] == {
        "state": "recorded",
        "source": "local_estimate",
        "raw_tokens": envelope["tokens"]["estimated"],
        "compressed_tokens": 1,
        "provider_cost": None,
    }
