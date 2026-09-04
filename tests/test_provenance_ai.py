"""Unit tests for ProvenanceAiTool with git trailer extraction and line survival curves."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.tools.provenance_ai import (
    GitTrailerParser,
    LineSurvivalEngine,
    ProvenanceAiTool,
)
from rush.tools.schemas import ProvenanceMetrics


def _init_test_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "committer@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_provenance_ai_metadata() -> None:
    tool = ProvenanceAiTool()
    assert tool.name == "provenance-ai"
    assert "attribution" in tool.mcp_description.lower()
    assert len(tool.mcp_description) < 200


def test_git_trailer_parser() -> None:
    sample_log = (
        "h1\x00Dev\x00dev@example.com\x001700000000\x00feat: initial\n\nAI-Generated: true\x01"
        "h2\x00Dev\x00dev@example.com\x001700000100\x00feat: assisted\n\nCo-authored-by: Claude <claude@anthropic.com>\x01"
        "h3\x00Dev\x00dev@example.com\x001700000200\x00fix: resolved bug\n\nFixes #12\x01"
    )
    commits = GitTrailerParser.parse_commit_records(sample_log)
    assert len(commits) == 3
    assert commits[0]["is_ai_generated"] is True
    assert commits[1]["is_ai_assisted"] is True
    assert commits[2]["is_fix"] is True


def test_provenance_ai_runs_on_git_repository(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)

    # Commit 1: Human commit
    (tmp_path / "hello.py").write_text("print('hello world')\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "hello.py"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: initial commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Commit 2: AI-generated commit
    (tmp_path / "utils.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "utils.py"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: math utils\n\nAI-Generated: true"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Commit 3: Fix commit
    (tmp_path / "hello.py").write_text(
        "print('hello world updated')\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "hello.py"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "fix: update hello greeting\n\nCloses #1"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "provenance-ai"
    assert res["status"] == "ok"
    metrics = res.get("metrics") or {}
    assert metrics["total_commits"] == 3
    assert metrics["ai_generated_count"] == 1
    assert metrics["human_count"] == 2

    # Verify exact numeric bounds with strict Pydantic model
    validated = ProvenanceMetrics.model_validate(metrics)
    assert 0.0 <= validated.survival_rate_30d <= 1.0
    assert -1.0 <= validated.defect_correlation <= 1.0


def test_provenance_ai_line_survival_engine(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)
    (tmp_path / "tracked.py").write_text("line1\nline2\nline3\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.py"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: tracked file"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    import time

    now_ts = int(time.time())
    r30, r60, r90, churn = LineSurvivalEngine.compute_survival(tmp_path, now_ts)

    # Brand new lines committed just now have age < 30 days, so 30d survival is 0.0
    assert r30 == 0.0
    assert r60 == 0.0
    assert r90 == 0.0
    assert churn == 1.0


def test_provenance_ai_detects_shallow_clone(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Simulate shallow repository
    (tmp_path / ".git" / "shallow").write_text("dummy_hash\n", encoding="utf-8")

    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)

    assert res["status"] == "warn"
    assert res["metrics"]["shallow_history"] is True
    assert any(f.get("rule_id") == "WARN_SHALLOW_CLONE" for f in res["findings"])


def test_provenance_ai_skips_non_git_directory(tmp_path: Path) -> None:
    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)
    assert res["status"] == "skipped"
    assert "not inside a valid Git repository" in res["summary"]
