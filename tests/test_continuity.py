"""Unit and contract tests for SessionContinuityTool and ToolResultV1 conformance."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rush.contracts.results import ToolResultV1, validate_tool_result
from rush.permissions import ExecutionPermissions
from rush.tools.continuity import SessionContinuityTool


def test_continuity_list_with_valid_and_corrupt_checkpoints(tmp_path: Path) -> None:
    """Asserts continuity list properly handles both valid and corrupt checkpoint entries and conforms to ToolResultV1."""
    tool = SessionContinuityTool()

    # 1. Initially empty list
    empty_res = tool.run(tmp_path, operation="list")
    assert empty_res["status"] == "ok"
    assert "0" in empty_res["summary"]
    assert empty_res["raw"] == []
    empty_v1 = empty_res.to_tool_result_v1()
    assert isinstance(empty_v1, ToolResultV1)
    assert empty_v1.schema_version == "1.0.0"
    assert validate_tool_result(empty_v1).status == "ok"

    # 2. Save a valid checkpoint
    save_res = tool.run(
        tmp_path,
        operation="save",
        name="valid_ckpt",
        files=["src/main.py"],
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert save_res["status"] == "ok"
    save_v1 = save_res.to_tool_result_v1()
    assert isinstance(save_v1, ToolResultV1)
    assert validate_tool_result(save_v1).status == "ok"

    # 3. Inject a corrupt checkpoint JSON directly into storage
    sessions_dir = tmp_path / ".rush" / "sessions"
    corrupt_bytes = b'{"truncated": true, "unclosed_string": "error\xff\xfe'
    corrupt_file = sessions_dir / "corrupt_ckpt.json"
    corrupt_file.write_bytes(corrupt_bytes)
    corrupt_digest = hashlib.sha256(corrupt_bytes).hexdigest()

    # 4. List checkpoints with mixed valid + corrupt entries
    list_res = tool.run(tmp_path, operation="list")
    assert list_res["status"] == "warn"
    assert "1 corrupt" in list_res["summary"]
    assert len(list_res["raw"]) == 2
    assert len(list_res["findings"]) == 1

    finding = list_res["findings"][0]
    assert finding["rule_id"] == "CORRUPT_CHECKPOINT_JOURNAL"
    assert finding["severity"] in ("warn", "warning")
    assert corrupt_digest in finding["fingerprint"] or corrupt_digest in str(
        finding.get("evidence", "")
    )

    # Verify corrupt entry in raw
    corrupt_entry = next(
        (c for c in list_res["raw"] if c.get("checkpoint_id") == "corrupt_ckpt"),
        None,
    )
    assert corrupt_entry is not None
    assert corrupt_entry["status"] == "corrupt"
    assert corrupt_entry["raw_bytes_digest"] == corrupt_digest

    # Verify ToolResultV1 contract compliance
    list_v1 = list_res.to_tool_result_v1()
    assert isinstance(list_v1, ToolResultV1)
    assert list_v1.schema_version == "1.0.0"
    validated = validate_tool_result(list_v1)
    assert validated.status == "warn"
    assert len(validated.findings) == 1


def test_continuity_restore_valid_and_corrupt_entries(tmp_path: Path) -> None:
    """Asserts restore handles nonexistent, valid, and corrupt checkpoints correctly."""
    tool = SessionContinuityTool()

    # 1. Nonexistent checkpoint returns skipped
    missing_res = tool.run(tmp_path, operation="restore", name="nonexistent")
    assert missing_res["status"] == "skipped"
    assert "was not found" in missing_res["summary"]
    assert validate_tool_result(missing_res.to_tool_result_v1()).status == "skipped"

    # 2. Save valid checkpoint and restore it
    tool.run(
        tmp_path,
        operation="save",
        name="good_ckpt",
        handoff={"current_goal": "verify restore"},
        permissions=ExecutionPermissions(cache_write=True),
    )
    restore_res = tool.run(tmp_path, operation="restore", name="good_ckpt")
    assert restore_res["status"] == "ok"
    assert restore_res["raw"]["name"] == "good_ckpt"
    assert restore_res["raw"]["schema_version"] == "1.0.0"
    assert restore_res["metadata"]["handoff"]["current_goal"] == "verify restore"
    assert validate_tool_result(restore_res.to_tool_result_v1()).status == "ok"

    # 3. Corrupt checkpoint file returns error status
    sessions_dir = tmp_path / ".rush" / "sessions"
    bad_file = sessions_dir / "bad_ckpt.json"
    bad_bytes = b"NOT_VALID_JSON"
    bad_file.write_bytes(bad_bytes)

    corrupt_restore = tool.run(tmp_path, operation="restore", name="bad_ckpt")
    assert corrupt_restore["status"] == "error"
    assert "corrupt or unreadable" in corrupt_restore["summary"]
    assert len(corrupt_restore["findings"]) == 1
    assert corrupt_restore["findings"][0]["rule_id"] == "CORRUPT_CHECKPOINT_JOURNAL"
    assert validate_tool_result(corrupt_restore.to_tool_result_v1()).status == "error"


def test_continuity_as_v1_mode_returns_tool_result_v1_directly(tmp_path: Path) -> None:
    """Asserts that calling continuity tool with as_v1=True returns ToolResultV1 instance directly."""
    tool = SessionContinuityTool()
    v1_result = tool.run(
        tmp_path,
        operation="save",
        name="direct_v1",
        permissions=ExecutionPermissions(cache_write=True),
        as_v1=True,
    )
    assert isinstance(v1_result, ToolResultV1)
    assert v1_result.schema_version == "1.0.0"
    assert v1_result.tool == "continuity"
    assert v1_result.status == "ok"
    assert validate_tool_result(v1_result).status == "ok"
