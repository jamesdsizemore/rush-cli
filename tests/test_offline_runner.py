"""Unit tests for OfflineReviewTool (PR50.11 / I24)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rush.tools.offline_runner import (
    OfflineReviewTool,
    discover_local_runner,
    parse_review_findings,
)


def test_discover_local_runner_on_path() -> None:
    with (
        patch("rush.tools.offline_runner._is_ollama_ready", return_value=True),
        patch("shutil.which") as mock_which,
    ):
        mock_which.side_effect = lambda cmd: (
            "/usr/local/bin/ollama" if cmd == "ollama" else None
        )
        runner = discover_local_runner()
        assert runner is not None
        assert runner["type"] == "ollama"
        assert runner["path"] == "/usr/local/bin/ollama"

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/llama-cli" if cmd == "llama-cli" else None
        )
        runner = discover_local_runner()
        assert runner is not None
        assert runner["type"] == "llama-cli"
        assert runner["path"] == "/usr/bin/llama-cli"


def test_missing_runner_returns_structured_skipped(tmp_path: Path) -> None:
    tool = OfflineReviewTool()
    with patch("rush.tools.offline_runner.discover_local_runner", return_value=None):
        res = tool.run(tmp_path)

    assert res["tool"] == "offline-review"
    assert res["status"] == "skipped"
    assert "No external local LLM runner" in res["summary"]
    assert res["findings"] == []


def test_offline_discovery_is_project_relative(tmp_path: Path) -> None:
    prompts = []
    results = []
    for parent in ("ordinary", ".hidden"):
        project = tmp_path / parent / "project"
        project.mkdir(parents=True)
        (project / "app.py").write_text("x = 1\n")
        for child in (".hidden", "venv", "node_modules"):
            excluded = project / child
            excluded.mkdir()
            (excluded / "ignored.py").write_text("excluded_marker\n")
        with (
            patch(
                "rush.tools.offline_runner.discover_local_runner",
                return_value={"type": "ollama", "path": "/usr/bin/ollama"},
            ),
            patch(
                "rush.tools.offline_runner.run_subprocess",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ) as runner,
        ):
            results.append(OfflineReviewTool().run(project))
            assert runner.call_count == 1
            prompts.append(runner.call_args.args[0][-1])
    assert prompts[0] == prompts[1]
    assert "--- File: app.py ---" in prompts[0]
    assert "excluded_marker" not in prompts[0]
    for result in results:
        assert result["status"] == "ok"
        assert result["metrics"]["files_evaluated"] == 1


def test_offline_read_denial_does_not_invoke_runner(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    with (
        patch(
            "rush.tools.offline_runner.discover_local_runner",
            return_value={"type": "ollama", "path": "/usr/bin/ollama"},
        ),
        patch.object(Path, "read_text", side_effect=PermissionError),
        patch("rush.tools.offline_runner.run_subprocess") as runner,
    ):
        result = OfflineReviewTool().run(tmp_path)
    assert result["status"] == "error"
    assert "read" in result["summary"].lower()
    runner.assert_not_called()


def test_offline_discovery_denial_is_error(tmp_path: Path) -> None:
    with (
        patch(
            "rush.tools.offline_runner.discover_local_runner",
            return_value={"type": "ollama", "path": "/usr/bin/ollama"},
        ),
        patch("os.scandir", side_effect=PermissionError),
        patch("rush.tools.offline_runner.run_subprocess") as runner,
    ):
        result = OfflineReviewTool().run(tmp_path)
    assert result["status"] == "error"
    assert "read" in result["summary"].lower()
    runner.assert_not_called()


def test_query_local_runner_and_parse_findings(tmp_path: Path) -> None:
    code_file = tmp_path / "vulnerable.py"
    code_file.write_text("eval(user_input)\n", encoding="utf-8")

    tool = OfflineReviewTool()
    mock_runner = {"type": "ollama", "path": "/usr/bin/ollama"}

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = (
        "vulnerable.py:1:1: [ERROR] Use of eval allows arbitrary code execution"
    )
    mock_res.stderr = ""

    with (
        patch(
            "rush.tools.offline_runner.discover_local_runner", return_value=mock_runner
        ),
        patch("rush.tools.offline_runner.run_subprocess", return_value=mock_res),
    ):
        res = tool.run(tmp_path)

    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["severity"] == "error"
    assert "eval allows arbitrary code execution" in res["findings"][0]["message"]
    assert res["findings"][0]["path"] == "vulnerable.py"


def test_offline_review_clean_with_no_defects(tmp_path: Path) -> None:
    code_file = tmp_path / "clean.py"
    code_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    tool = OfflineReviewTool()
    mock_runner = {"type": "ollama", "path": "/usr/bin/ollama"}

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "Code looks clean, zero security issues found."
    mock_res.stderr = ""

    with (
        patch(
            "rush.tools.offline_runner.discover_local_runner", return_value=mock_runner
        ),
        patch("rush.tools.offline_runner.run_subprocess", return_value=mock_res),
    ):
        res = tool.run(tmp_path)

    assert res["status"] == "ok"
    assert res["findings"] == []
    assert res["metrics"]["issues_found"] == 0


def test_offline_review_handles_runner_error(tmp_path: Path) -> None:
    code_file = tmp_path / "app.py"
    code_file.write_text("print('hello')", encoding="utf-8")

    tool = OfflineReviewTool()
    mock_runner = {"type": "ollama", "path": "/usr/bin/ollama"}

    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = ""
    mock_res.stderr = "model 'codellama' not found"

    with (
        patch(
            "rush.tools.offline_runner.discover_local_runner", return_value=mock_runner
        ),
        patch("rush.tools.offline_runner.run_subprocess", return_value=mock_res),
    ):
        res = tool.run(tmp_path)

    assert res["status"] == "error"
    assert "Runner execution failed with exit code 1" in res["summary"]


def test_offline_review_json_findings_parsing(tmp_path: Path) -> None:
    findings_json = (
        '[{"path": "lib.py", "line": 5, "column": 2, "severity": "warn", '
        '"message": "Unvalidated input in query"}]'
    )
    findings = parse_review_findings(findings_json, tmp_path)
    assert len(findings) == 1
    assert findings[0]["path"] == "lib.py"
    assert findings[0]["line"] == 5
    assert findings[0]["severity"] == "warn"
