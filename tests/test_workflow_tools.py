"""Developer-workflow tool safety contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.ci import CiTool
from rush.tools.commit_msg import CommitMsgTool
from rush.tools.release import ReleaseTool


def test_commit_message_validation_never_mutates_git_history(tmp_path: Path) -> None:
    result = CommitMsgTool().run(tmp_path, message="not a conventional commit")

    assert result["tool"] == "commit-msg"
    assert result["status"] == "fail"
    assert result["findings"][0]["rule"] == "conventional-commit"
    assert result["artifacts"] == []


def test_ci_default_is_local_workflow_configuration_check(tmp_path: Path) -> None:
    result = CiTool().run(tmp_path)

    assert result["tool"] == "ci"
    assert result["status"] == "skipped"
    assert "workflow" in result["summary"]
    assert result["raw"] is None


def test_release_defaults_to_dry_run_without_publishing(tmp_path: Path) -> None:
    result = ReleaseTool().run(tmp_path)

    assert result["tool"] == "release"
    assert result["status"] == "ok"
    assert result["metadata"] == {"dry_run": True, "publish": False}
    assert result["artifacts"] == []


def test_release_refuses_publication_without_confirmation(tmp_path: Path) -> None:
    result = ReleaseTool().run(tmp_path, publish=True)

    assert result["status"] == "skipped"
    assert "confirmation" in result["summary"]
