"""Unit tests for ProvenanceAiTool (PR50.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.tools.provenance_ai import ProvenanceAiTool


def _init_test_git_repo(repo_dir: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Committer"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "committer@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def test_provenance_ai_parses_git_trailers_and_attribution(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)

    # Commit 1: Human commit
    (tmp_path / "file1.txt").write_text("initial", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file1.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: initial human commit"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Commit 2: AI-assisted with Co-authored-by trailer
    (tmp_path / "file2.txt").write_text("assisted code", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file2.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat: add assisted module\n\nCo-authored-by: Claude <noreply@anthropic.com>\nModel: claude-3-7-sonnet",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Commit 3: AI-generated with Generated-by trailer
    (tmp_path / "file3.txt").write_text("generated code", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file3.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "chore: automated scaffold\n\nGenerated-by: rush-cli-agent\nAgent: AutoScaffolder",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "provenance-ai"
    assert res["status"] in ("ok", "warn")
    assert res["raw"] is not None

    raw = res["raw"]
    assert raw["commits_audited"] >= 3
    assert raw["ai_generated_count"] >= 1
    assert raw["ai_assisted_count"] >= 1
    assert raw["human_count"] >= 1


def test_provenance_ai_reports_unknown_survival_states_per_d50_12(
    tmp_path: Path,
) -> None:
    _init_test_git_repo(tmp_path)
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(
        ["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feat: test\n\nGenerated-by: AI"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)

    metadata = res.get("metadata", {})
    survival = metadata.get("survival_states", {})
    assert survival.get("30d") == "unknown"
    assert survival.get("60d") == "unknown"
    assert survival.get("90d") == "unknown"

    defect = metadata.get("defect_correlation", {})
    assert defect.get("state") == "unknown"


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
    assert res["raw"]["shallow_history"] is True
    assert any(f.get("rule") == "shallow-history" for f in res["findings"])


def test_provenance_ai_handles_non_git_directory(tmp_path: Path) -> None:
    non_git = tmp_path / "not_git"
    non_git.mkdir()
    (non_git / "code.py").write_text("print('hello')", encoding="utf-8")

    tool = ProvenanceAiTool()
    res = tool.run(non_git)

    assert res["tool"] == "provenance-ai"
    assert res["status"] == "skipped"
    assert "git repository" in res["summary"].lower()


def test_provenance_ai_canonical_schema_and_call(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(
        ["git", "add", "a.txt"], cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
    )

    tool = ProvenanceAiTool()
    res = tool(tmp_path)

    assert res["tool"] == "provenance-ai"
    assert "status" in res
    assert isinstance(res["duration_ms"], int)
    assert isinstance(res["findings"], list)
    assert isinstance(res["summary"], str)
