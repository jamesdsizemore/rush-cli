"""Phase 07.A8 commitlint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import commitlint
from rush.engines.commitlint import CommitlintEngine
from rush.tools.commit_msg import CommitMsgTool


def test_commitlint_runs_bounded_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        commitlint, "resolve_binary", lambda _binary: "C:/bin/commitlint"
    )
    monkeypatch.setattr(commitlint, "run_subprocess", fake_run)

    raw = CommitlintEngine().run(tmp_path, ["--edit"], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/commitlint",
            "--edit",
        ]
    ]


def test_commit_msg_tool_validates_message() -> None:
    tool = CommitMsgTool()
    valid_res = tool.run(Path("."), message="feat(core): add new feature")
    assert valid_res["status"] == "ok"
    assert valid_res["summary"] == "commit message is valid"
    assert len(valid_res["findings"]) == 0

    invalid_res = tool.run(Path("."), message="random commit message without prefix")
    assert invalid_res["status"] == "fail"
    assert invalid_res["summary"] == "commit message is invalid"
    assert len(invalid_res["findings"]) == 1
    assert invalid_res["findings"][0]["rule"] == "conventional-commit"


def test_commit_msg_tool_reads_file_if_empty_message(tmp_path: Path) -> None:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("fix(cli): fix argument parsing\n")
    tool = CommitMsgTool()
    res = tool.run(msg_file)
    assert res["status"] == "ok"
