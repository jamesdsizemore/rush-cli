"""Unit tests for PrSynthesizeTool and PrSynthesizer (PR50.15)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.pr_synthesize import PrSynthesizer, PrSynthesizeTool


def _init_git_repo_with_diff(repo_dir: Path) -> None:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo_dir, check=True, capture_output=True
    )
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
    (repo_dir / "initial.py").write_text(
        "def hello() -> str:\n    return 'hello'\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "initial.py"], cwd=repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "chore: initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Make modifications for diff
    (repo_dir / "initial.py").write_text(
        "def hello() -> str:\n    return 'hello world'\n", encoding="utf-8"
    )
    (repo_dir / "new_feature.py").write_text(
        "def feature() -> int:\n    return 42\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add new feature"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )


def test_pr_synthesize_generates_markdown_card_from_git_diff(tmp_path: Path) -> None:
    _init_git_repo_with_diff(tmp_path)

    tool = PrSynthesizeTool()
    res = tool.run(tmp_path, base_ref="HEAD~1")

    assert res["tool"] == "pr-synthesize"
    assert res["status"] == "ok"
    assert res["raw"] is not None

    card = res["raw"]["pr_card"]
    assert "# Pull Request" in card or "## Summary" in card
    assert "Diff Statistics" in card
    assert "Quality & Security Gates" in card
    assert res["metadata"]["files_changed"] >= 2


def test_pr_synthesize_export_requires_artifact_write_permission(
    tmp_path: Path,
) -> None:
    _init_git_repo_with_diff(tmp_path)
    export_file = tmp_path / "PR_SUMMARY.md"

    tool = PrSynthesizeTool()

    # Without permission -> export denied
    denied = tool.run(
        tmp_path,
        base_ref="HEAD~1",
        export_path=export_file,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert denied["status"] == "skipped"
    assert not export_file.exists()
    assert "--allow-artifact-write" in denied["summary"]

    # With permission -> export succeeds
    granted = tool.run(
        tmp_path,
        base_ref="HEAD~1",
        export_path=export_file,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert granted["status"] == "ok"
    assert export_file.exists()
    card_content = export_file.read_text(encoding="utf-8")
    assert "Diff Statistics" in card_content


def test_pr_synthesize_blocks_path_traversal_export(tmp_path: Path) -> None:
    _init_git_repo_with_diff(tmp_path)
    escape_file = tmp_path.parent / "escape_pr.md"

    tool = PrSynthesizeTool()
    res = tool.run(
        tmp_path,
        base_ref="HEAD~1",
        export_path=escape_file,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res["status"] == "error"
    assert not escape_file.exists()


def test_pr_synthesizer_backward_compatibility(tmp_path: Path) -> None:
    _init_git_repo_with_diff(tmp_path)

    synth = PrSynthesizer(project_root=tmp_path)
    card = synth.synthesize_pr_card(base_branch="HEAD~1")

    assert "Build Provenance" in card
    assert "Architecture Guard" in card


def test_pr_synthesize_canonical_schema_and_call(tmp_path: Path) -> None:
    _init_git_repo_with_diff(tmp_path)

    tool = PrSynthesizeTool()
    res = tool(tmp_path, base_ref="HEAD~1")

    assert res["tool"] == "pr-synthesize"
    assert res["status"] == "ok"
    assert isinstance(res["duration_ms"], int)
    assert isinstance(res["summary"], str)


def test_pr_synthesize_parses_codeowners_and_recommends_reviewers(
    tmp_path: Path,
) -> None:
    _init_git_repo_with_diff(tmp_path)

    github_dir = tmp_path / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    (github_dir / "CODEOWNERS").write_text(
        "*.py @python-team # primary owners\nnew_feature.py @feature-lead\n",
        encoding="utf-8",
    )

    tool = PrSynthesizeTool()
    res = tool.run(tmp_path, base_ref="HEAD~1")

    assert res["status"] == "ok"
    reviewers = res["metadata"]["recommended_reviewers"]
    assert "@python-team" in reviewers
    assert "@feature-lead" in reviewers
    assert "#" not in reviewers
    assert "primary" not in reviewers
    assert "@python-team" in res["raw"]["pr_card"]


def test_pr_synthesize_computes_risk_tier_from_diff_and_evidence(
    tmp_path: Path,
) -> None:
    _init_git_repo_with_diff(tmp_path)

    tool = PrSynthesizeTool()

    # Clean evidence, small diff -> low risk
    res_low = tool.run(tmp_path, base_ref="HEAD~1")
    assert res_low["metadata"]["risk_tier"] == "low"
    assert "**Risk Tier**: `LOW`" in res_low["raw"]["pr_card"]

    # Failing evidence -> high risk
    evidence_fail = [
        {"tool": "security", "status": "fail", "summary": "1 critical vulnerability"}
    ]
    res_high = tool.run(tmp_path, base_ref="HEAD~1", evidence=evidence_fail)
    assert res_high["metadata"]["risk_tier"] == "high"
    assert "**Risk Tier**: `HIGH`" in res_high["raw"]["pr_card"]

    # Warning evidence -> medium risk
    evidence_warn = [{"tool": "lint", "status": "warn", "summary": "2 style warnings"}]
    res_med = tool.run(tmp_path, base_ref="HEAD~1", evidence=evidence_warn)
    assert res_med["metadata"]["risk_tier"] == "medium"
    assert "**Risk Tier**: `MEDIUM`" in res_med["raw"]["pr_card"]
