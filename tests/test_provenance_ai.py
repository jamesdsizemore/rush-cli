"""Unit tests for ProvenanceAiTool with git trailer extraction and line survival curves."""

from __future__ import annotations

import os
import subprocess
import time
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


def _commit_at(root: Path, message: str, timestamp: int) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"{timestamp} +0000",
        "GIT_COMMITTER_DATE": f"{timestamp} +0000",
    }
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        check=True,
        capture_output=True,
        env=env,
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
    assert validated.survival_rate_30d is None
    assert validated.defect_correlation is None
    assert res["metadata"]["survival_windows"]["30d"]["unavailable_reason"]
    assert res["metadata"]["defect_association"]["unavailable_reason"]


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

    # Brand new lines have no complete historical cohort; never fabricate rates.
    assert r30 is None
    assert r60 is None
    assert r90 is None
    assert churn is None


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
    assert (
        res["metadata"]["defect_association"]["unavailable_reason"] == "shallow-history"
    )


def test_provenance_ai_skips_non_git_directory(tmp_path: Path) -> None:
    tool = ProvenanceAiTool()
    res = tool.run(tmp_path)
    assert res["status"] == "skipped"
    assert "not inside a valid Git repository" in res["summary"]


def test_provenance_ai_survival_uses_historical_cohort_and_rename_identity(
    tmp_path: Path,
) -> None:
    _init_test_git_repo(tmp_path)
    now = int(time.time())
    tracked = tmp_path / "tracked.py"
    tracked.write_text("old one\nold two\n", encoding="utf-8")
    _commit_at(tmp_path, "initial cohort", now - 100 * 86400)

    tracked.write_text("old one\n", encoding="utf-8")
    _commit_at(tmp_path, "fix: remove one old line", now - 86400)

    metrics = ProvenanceAiTool().run(tmp_path)["metrics"]
    assert metrics["survival_rate_30d"] == 0.5
    assert metrics["survival_rate_60d"] == 0.5
    assert metrics["survival_rate_90d"] == 0.5
    assert metrics["churn_rate_30d"] == 0.5
    assert metrics["churn_rate_60d"] == 0.5
    assert metrics["churn_rate_90d"] == 0.5

    rename_root = tmp_path / "rename-only"
    rename_root.mkdir()
    _init_test_git_repo(rename_root)
    original = rename_root / "original.py"
    original.write_text("old one\nold two\n", encoding="utf-8")
    _commit_at(rename_root, "initial rename cohort", now - 100 * 86400)
    original.rename(rename_root / "renamed.py")
    _commit_at(rename_root, "refactor: preserve file identity", now)
    renamed = ProvenanceAiTool().run(rename_root)["metrics"]
    assert renamed["survival_rate_90d"] == 1.0


def _association_history(root: Path, *, fix_ai: bool, now: int) -> None:
    _init_test_git_repo(root)
    sources = {
        "human1.py": "human one\n",
        "human2.py": "human two\n",
        "ai1.py": "ai one\n",
        "ai2.py": "ai two\n",
    }
    for index, (name, content) in enumerate(sources.items()):
        path = root / name
        path.write_text(content, encoding="utf-8")
        message = (
            "feat: generated helper" if name.startswith("ai") else "feat: human source"
        )
        if name.startswith("ai"):
            message += "\n\nAI-Generated: true"
        _commit_at(root, message, now - (100 - index) * 86400)
    if fix_ai:
        (root / "ai1.py").write_text("ai one fixed\n", encoding="utf-8")
        (root / "ai2.py").write_text("ai two fixed\n", encoding="utf-8")
    else:
        (root / "human1.py").write_text("human one fixed\n", encoding="utf-8")
        (root / "human2.py").write_text("human two fixed\n", encoding="utf-8")
    _commit_at(root, "fix: repair observed defect", now - 86400)


def test_provenance_ai_real_first_parent_association_phi(tmp_path: Path) -> None:
    now = int(time.time())
    aligned_root = tmp_path / "aligned"
    opposed_root = tmp_path / "opposed"
    aligned_root.mkdir()
    opposed_root.mkdir()
    _association_history(aligned_root, fix_ai=True, now=now)
    _association_history(opposed_root, fix_ai=False, now=now)

    aligned = ProvenanceAiTool().run(aligned_root)
    opposed = ProvenanceAiTool().run(opposed_root)
    assert aligned["metadata"]["defect_association"]["phi"] == 1.0
    assert opposed["metadata"]["defect_association"]["phi"] == -1.0
    for result in (aligned, opposed):
        association = result["metadata"]["defect_association"]
        assert association["sample_count"] == 4
        counts = association["counts"]
        if result is aligned:
            assert counts == {"n11": 2, "n10": 0, "n01": 0, "n00": 2}
        else:
            assert counts == {"n11": 0, "n10": 2, "n01": 2, "n00": 0}
        assert (
            association["linkage_method"] == "first-parent deleted-line origin linkage"
        )
        assert association["interpretation"] == "observed association, not causality"


def test_provenance_ai_unavailable_statistics_explain_evidence_limits(
    tmp_path: Path,
) -> None:
    _init_test_git_repo(tmp_path)
    result = ProvenanceAiTool().run(tmp_path)
    assert result["status"] == "warn"
    metrics = result.get("metrics") or {}
    assert metrics["defect_correlation"] is None
    evidence = result["metadata"]["defect_association"]
    assert evidence["sample_count"] == 0
    assert evidence["linkage_method"] == "first-parent deleted-line origin linkage"
    assert evidence["unavailable_reason"] == "no-history"


def test_provenance_ai_zero_variance_reports_reason(tmp_path: Path) -> None:
    _init_test_git_repo(tmp_path)
    (tmp_path / "stable.py").write_text("stable\n", encoding="utf-8")
    _commit_at(tmp_path, "feat: stable source", int(time.time()) - 100 * 86400)

    result = ProvenanceAiTool().run(tmp_path)
    association = result["metadata"]["defect_association"]
    assert association["phi"] is None
    assert association["sample_count"] == 1
    assert association["counts"] == {"n11": 0, "n10": 0, "n01": 0, "n00": 1}
    assert association["unavailable_reason"] == "zero-variance"


def test_provenance_ai_survival_tracks_lines_across_merge_history(
    tmp_path: Path,
) -> None:
    _init_test_git_repo(tmp_path)
    now = int(time.time())
    tracked = tmp_path / "tracked.py"
    tracked.write_text("root line one\nroot line two\n", encoding="utf-8")
    _commit_at(tmp_path, "root cohort", now - 100 * 86400)
    subprocess.run(
        ["git", "branch", "side"], cwd=tmp_path, check=True, capture_output=True
    )
    main_branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    tracked.write_text("root line one\n", encoding="utf-8")
    _commit_at(tmp_path, "main: remove second line", now - 95 * 86400)

    subprocess.run(
        ["git", "checkout", "side"], cwd=tmp_path, check=True, capture_output=True
    )
    tracked.write_text("root line two\n", encoding="utf-8")
    _commit_at(tmp_path, "side: remove first line", now - 2 * 86400)

    subprocess.run(
        ["git", "checkout", main_branch], cwd=tmp_path, check=True, capture_output=True
    )
    merge = subprocess.run(
        ["git", "merge", "--no-ff", "side", "--no-commit"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert merge.returncode != 0
    tracked.write_text("root line two\n", encoding="utf-8")
    _commit_at(tmp_path, "Merge side history", now - 86400)

    result = ProvenanceAiTool().run(tmp_path)
    assert result["metrics"]["survival_rate_90d"] == 0.0
    assert result["metrics"]["churn_rate_90d"] == 1.0
    window = result["metadata"]["survival_windows"]["90d"]
    assert window["original_cohort_lines"] == 1
    assert window["surviving_lines"] == 0
    assert window["lost_lines"] == 1


def test_provenance_ai_excludes_future_dated_fix_from_endpoint_cohort(
    tmp_path: Path, monkeypatch
) -> None:
    _init_test_git_repo(tmp_path)
    now = int(time.time())
    tracked = tmp_path / "tracked.py"
    tracked.write_text("root line one\nroot line two\n", encoding="utf-8")
    _commit_at(tmp_path, "root cohort", now - 100 * 86400)
    tracked.write_text("root line one\n", encoding="utf-8")
    _commit_at(tmp_path, "future: remove line", now + 86400)

    monkeypatch.setattr("rush.tools.provenance_ai.time.time", lambda: now)
    result = ProvenanceAiTool().run(tmp_path)
    metrics = result["metrics"]
    assert metrics["survival_rate_30d"] == 1.0
    assert metrics["survival_rate_60d"] == 1.0
    assert metrics["survival_rate_90d"] == 1.0
    window = result["metadata"]["survival_windows"]["90d"]
    assert window["original_cohort_lines"] == 2
    assert window["surviving_lines"] == 2
    assert window["lost_lines"] == 0
