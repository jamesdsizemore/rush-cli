"""Contract tests for Phase 58: Lock Capabilities and Verifier-Only Locks (P58.1.1 & P58.2.1)."""

from __future__ import annotations

import concurrent.futures
import json
import os
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.io import VerifierRecord
from rush.mcp_mesh.capabilities import (
    LockCapabilityInput,
    LockLeaseRecord,
    create_capability,
)
from rush.mcp_mesh.lock_manager import MeshLockManager


def test_caller_retains_only_raw_capability(tmp_path: Path) -> None:
    """T-58.01: Asserts caller generates high-entropy capability token; acquire() saves

    LockLeaseRecord with VerifierRecord from rush.io.VerifierRecord; raw capability
    token never appears in stored json, in LockLeaseRecord.__repr__, or in return value.
    """
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "protected_file.py"
    target.write_text("code = 1\n", encoding="utf-8")

    # Caller generates high-entropy capability token
    cap_input, raw_token = create_capability(
        agent_id="agent-alpha", channel_type="stdin"
    )
    assert len(raw_token) >= 16
    assert cap_input.token == raw_token
    assert cap_input.agent_id == "agent-alpha"

    # Acquire lock with capability
    result = mgr.acquire(target, agent_id="agent-alpha", capability=cap_input)
    assert result is True or (isinstance(result, tuple) and result[0] is True)

    # Raw token never appears in return value
    assert raw_token not in str(result)

    # Stored json verification
    lock_file = mgr._lock_file_for(target)
    assert lock_file.exists()
    stored_text = lock_file.read_text(encoding="utf-8")
    assert raw_token not in stored_text

    stored_json = json.loads(stored_text)
    assert "verifier_record" in stored_json
    vr_dict = stored_json["verifier_record"]
    assert "verifier" in vr_dict
    assert "salt" in vr_dict
    assert raw_token not in str(vr_dict)

    # Verify that stored verifier matches VerifierRecord format and verifies raw_token
    vr = VerifierRecord.from_dict(vr_dict)
    assert vr.verify(raw_token) is True
    assert vr.verify("wrong-token-value-here") is False

    # LockLeaseRecord.__repr__ never leaks raw capability token
    lease_record = LockLeaseRecord.from_dict(stored_json)
    assert raw_token not in repr(lease_record)
    assert raw_token not in str(lease_record)


def test_cli_uses_protected_input_not_argv_or_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-58.02: Verifies lock CLI commands reject capabilities in argv/env and accept only protected stdin/descriptor."""
    from rush.cli import cli

    runner = CliRunner()
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "shared.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    _cap_input, raw_token = create_capability(agent_id="agent-cli")

    # 1. Rejects capability passed via argv
    res_argv = runner.invoke(
        cli,
        [
            "lock",
            "acquire",
            str(target),
            "--agent-id",
            "agent-cli",
            "--capability",
            raw_token,
        ],
    )
    assert res_argv.exit_code != 0
    assert any(
        w in res_argv.output.lower()
        for w in ("argv", "rejected", "forbidden", "illegal")
    )

    # 2. Rejects capability passed via environment variable
    monkeypatch.setenv("RUSH_LOCK_CAPABILITY", raw_token)
    res_env = runner.invoke(
        cli,
        ["lock", "acquire", str(target), "--agent-id", "agent-cli"],
    )
    assert res_env.exit_code != 0
    assert any(
        w in res_env.output.lower()
        for w in ("environment", "rejected", "forbidden", "illegal")
    )
    monkeypatch.delenv("RUSH_LOCK_CAPABILITY", raising=False)

    # 3. Direct LockCapabilityInput rejects invalid channel_type
    with pytest.raises(ValueError, match=r"channel|argv|environment|supported"):
        LockCapabilityInput(token=raw_token, agent_id="agent-cli", channel_type="argv")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=r"channel|argv|environment|supported"):
        LockCapabilityInput(token=raw_token, agent_id="agent-cli", channel_type="env")  # type: ignore[arg-type]

    # 4. Accepts capability via protected stdin
    res_stdin = runner.invoke(
        cli,
        ["lock", "acquire", str(target), "--agent-id", "agent-cli", "--stdin"],
        input=raw_token,
    )
    assert res_stdin.exit_code == 0
    assert mgr.inspect(tmp_path, target)["state"] == "held"

    # 5. Accepts release via protected stdin
    res_release = runner.invoke(
        cli,
        ["lock", "release", str(target), "--agent-id", "agent-cli", "--stdin"],
        input=raw_token,
    )
    assert res_release.exit_code == 0
    assert mgr.inspect(tmp_path, target)["state"] == "available"

    # 6. Accepts via descriptor (pipe)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, raw_token.encode("utf-8"))
        os.close(write_fd)
        res_fd = runner.invoke(
            cli,
            [
                "lock",
                "acquire",
                str(target),
                "--agent-id",
                "agent-cli",
                "--descriptor",
                str(read_fd),
            ],
        )
        assert res_fd.exit_code == 0
        assert mgr.inspect(tmp_path, target)["state"] == "held"
    finally:
        try:
            os.close(read_fd)
        except OSError:
            pass


def test_mcp_sensitive_value_is_never_rendered_or_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-58.03: Verifies lock MCP tools mark capability parameter as sensitive, sanitize/redact in logs, and omit from tool results."""
    from rush.mcp import rush_mesh_acquire_lock, rush_mesh_release_lock
    from rush.safety.redactor import SecretRedactor

    target = tmp_path / "mcp_target.py"
    target.write_text("x = 1\n", encoding="utf-8")

    _cap_input, secret_token = create_capability(
        agent_id="mcp-agent", channel_type="mcp_sensitive"
    )

    # 1. MCP tool metadata marks capability parameter as sensitive
    sensitive_params = getattr(rush_mesh_acquire_lock, "_sensitive_params", ())
    assert "capability" in sensitive_params

    sensitive_release = getattr(rush_mesh_release_lock, "_sensitive_params", ())
    assert "capability" in sensitive_release

    # 2. Invoke acquire tool
    monkeypatch.chdir(tmp_path)
    res = rush_mesh_acquire_lock(
        str(target), agent_id="mcp-agent", capability=secret_token
    )
    assert (
        res is True
        or res == {"status": "ok"}
        or (isinstance(res, dict) and res.get("status") == "ok")
    )

    # 3. Secret token is never in the return value
    assert secret_token not in str(res)

    # 4. Secret token is never in disk lock file
    mgr = MeshLockManager(project_root=tmp_path)
    lock_file = mgr._lock_file_for(target)
    assert lock_file.exists()
    assert secret_token not in lock_file.read_text(encoding="utf-8")

    # 5. Redactor masks the secret token in logs/diagnostics
    redacted = SecretRedactor.redact_text(f"Acquired with capability={secret_token}")
    assert secret_token not in redacted
    assert "[REDACTED" in redacted

    # 6. Release tool also never leaks secret in return value
    rel_res = rush_mesh_release_lock(
        str(target), agent_id="mcp-agent", capability=secret_token
    )
    assert (
        rel_res is True
        or rel_res == {"status": "ok"}
        or (isinstance(rel_res, dict) and rel_res.get("status") == "ok")
    )
    assert secret_token not in str(rel_res)
    assert not lock_file.exists()


def test_simultaneous_acquire_has_one_generation_owner(tmp_path: Path) -> None:
    """T-58.04: Concurrent acquisition attempts on the same lock target; exactly one winner acquires generation N with valid verifier; runner-up fails to acquire."""
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "racy_file.py"
    target.write_text("balance = 100\n", encoding="utf-8")

    candidates = [
        (f"agent-{i}", create_capability(agent_id=f"agent-{i}")) for i in range(5)
    ]

    results: list[tuple[str, str, bool]] = []

    def try_acquire(agent_id: str, cap_tuple: tuple) -> tuple[str, str, bool]:
        cap_input, token = cap_tuple
        success = mgr.acquire(
            target, agent_id=agent_id, capability=cap_input, timeout_s=0.2
        )
        is_ok = success is True or (isinstance(success, tuple) and success[0] is True)
        return agent_id, token, is_ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(try_acquire, agent_id, cap_tuple)
            for agent_id, cap_tuple in candidates
        ]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    winners = [r for r in results if r[2] is True]
    losers = [r for r in results if r[2] is False]

    # Exactly one winner acquires the lock
    assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {winners}"
    assert len(losers) == 4

    winner_agent, winner_token, _ = winners[0]

    # Verify lock file on disk
    lock_file = mgr._lock_file_for(target)
    assert lock_file.exists()
    lease = LockLeaseRecord.from_dict(json.loads(lock_file.read_text(encoding="utf-8")))

    assert lease.owner_agent_id == winner_agent
    assert lease.generation == 1

    vr = VerifierRecord.from_dict(lease.verifier_record)
    assert vr.verify(winner_token) is True

    # All loser tokens fail verification against the winner's verifier
    for _loser_agent, loser_token, _ in losers:
        assert vr.verify(loser_token) is False


def test_wrong_guessed_stale_capability_cannot_renew_or_release(tmp_path: Path) -> None:
    """T-58.05: Wrong token, low-entropy token, or token from previous generation fails renewal and release fail-closed."""
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "sensitive_resource.py"
    target.write_text("data = 42\n", encoding="utf-8")

    # 1. Acquire generation 1
    cap1, _token1 = create_capability(agent_id="agent-1")
    assert mgr.acquire(target, agent_id="agent-1", capability=cap1) is True

    inspect_data = mgr.inspect(tmp_path, target)
    assert inspect_data["state"] == "held"
    assert inspect_data["generation"] == 1

    # 2. Try renew with wrong token
    wrong_cap, _ = create_capability(agent_id="agent-1")
    assert mgr.renew(target, capability=wrong_cap) is False

    # 3. Try release with wrong token
    assert mgr.release(target, capability=wrong_cap) is False
    # Lock is still held!
    assert mgr.inspect(tmp_path, target)["state"] == "held"

    # 4. Try renew with low-entropy / guessed token (fail-closed)
    low_entropy_cap = LockCapabilityInput(
        token="aaaaaaaaaaaaaaaa", agent_id="agent-1", channel_type="stdin"
    )
    assert mgr.renew(target, capability=low_entropy_cap) is False
    assert mgr.release(target, capability=low_entropy_cap) is False
    assert mgr.inspect(tmp_path, target)["state"] == "held"

    # 5. Successfully renew with valid token1 (increments generation to 2)
    assert mgr.renew(target, capability=cap1, ttl_s=60.0) is True
    assert mgr.inspect(tmp_path, target)["generation"] == 2

    # 6. Release lock with valid token1
    assert mgr.release(target, capability=cap1) is True
    assert mgr.inspect(tmp_path, target)["state"] == "available"

    # 7. Re-acquire by agent-2 (generation 3)
    cap2, _token2 = create_capability(agent_id="agent-2")
    assert mgr.acquire(target, agent_id="agent-2", capability=cap2) is True
    assert mgr.inspect(tmp_path, target)["generation"] == 3

    # 8. Token from previous generation (token1) cannot renew or release generation 3
    assert mgr.renew(target, capability=cap1) is False
    assert mgr.release(target, capability=cap1) is False
    assert mgr.inspect(tmp_path, target)["state"] == "held"
    assert mgr.inspect(tmp_path, target)["owner"] == "agent-2"

    # Clean release by current generation owner
    assert mgr.release(target, capability=cap2) is True


def test_link_swap_expiry_and_crash_recovery_fail_closed(tmp_path: Path) -> None:
    """T-58.06: Injected symlinks/reparse points or crash leftovers fail closed or cleanly recover without allowing unauthorized release."""
    mgr = MeshLockManager(project_root=tmp_path)
    target = tmp_path / "target_file.py"
    target.write_text("x = 10\n", encoding="utf-8")

    # 1. Injected symlink on lock file fails closed
    lock_file = mgr._lock_file_for(target)
    outside_file = tmp_path.parent / "escape.txt"
    outside_file.write_text("secret\n", encoding="utf-8")

    try:
        lock_file.symlink_to(outside_file)
        has_symlinks = True
    except (OSError, NotImplementedError):
        has_symlinks = False

    if has_symlinks:
        cap_sym, _ = create_capability(agent_id="agent-sym")
        # acquire should fail closed and refuse to overwrite symlink target
        assert (
            mgr.acquire(target, agent_id="agent-sym", capability=cap_sym, timeout_s=0.1)
            is False
        )
        assert outside_file.read_text(encoding="utf-8") == "secret\n"
        # release on symlink fails closed
        assert mgr.release(target, capability=cap_sym) is False
        lock_file.unlink()

    # 2. Crash leftover (corrupt/truncated JSON) fails closed for release and recovers on acquire
    lock_file.write_text("{corrupted_json: true, unterminated", encoding="utf-8")
    unauth_cap, _ = create_capability(agent_id="agent-unauth")
    # Release fails closed on corrupt lock
    assert mgr.release(target, capability=unauth_cap) is False

    # Inspect reports unavailable
    assert mgr.inspect(tmp_path, target)["state"] == "unavailable"

    # Clean acquisition recovers from corrupt crash file
    cap_rec, _ = create_capability(agent_id="agent-rec")
    assert (
        mgr.acquire(target, agent_id="agent-rec", capability=cap_rec, timeout_s=0.5)
        is True
    )
    assert mgr.inspect(tmp_path, target)["state"] == "held"

    # 3. Expiry handling: expired lock cannot be released by unauthorized caller
    data = json.loads(lock_file.read_text(encoding="utf-8"))
    data["expires_at"] = time.time() - 100.0
    lock_file.write_text(json.dumps(data), encoding="utf-8")

    assert mgr.inspect(tmp_path, target)["state"] == "expired"
    # Unauthorized release on expired lock returns False
    assert mgr.release(target, capability=unauth_cap) is False

    # New agent acquires expired lock, incrementing generation
    cap_new, _ = create_capability(agent_id="agent-new")
    assert (
        mgr.acquire(target, agent_id="agent-new", capability=cap_new, timeout_s=0.5)
        is True
    )
    new_inspect = mgr.inspect(tmp_path, target)
    assert new_inspect["state"] == "held"
    assert new_inspect["owner"] == "agent-new"
    assert new_inspect["generation"] >= 2
    assert mgr.release(target, capability=cap_new) is True
