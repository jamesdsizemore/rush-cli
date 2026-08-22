"""Tests for all Phase 20-40 newly registered CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli


def test_cli_token_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    sample_file = tmp_path / "sample.py"
    sample_file.write_text(
        "def foo(x: int) -> int:\n    return x + 1\n", encoding="utf-8"
    )

    # 1. token count
    res_count = runner.invoke(cli, ["token", "count", str(sample_file)])
    assert res_count.exit_code == 0
    assert "tokens" in res_count.output

    # 2. token outline
    res_outline = runner.invoke(cli, ["token", "outline", str(sample_file)])
    assert res_outline.exit_code == 0
    assert "def foo(x: int) -> int:" in res_outline.output

    # 3. token cache-advisor
    res_advisor = runner.invoke(cli, ["token", "cache-advisor", str(sample_file)])
    assert res_advisor.exit_code == 0
    assert "Cache Advisor Analysis" in res_advisor.output


def test_cli_sync_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    env_ex = tmp_path / ".env.example"
    env_ex.write_text("API_KEY=\nDB_URL=\n", encoding="utf-8")
    env_act = tmp_path / ".env"
    env_act.write_text("API_KEY=123\nDB_URL=postgres://...\n", encoding="utf-8")

    # sync env
    res_env = runner.invoke(cli, ["sync", "env", str(env_ex), str(env_act)])
    assert res_env.exit_code == 0
    assert "are present" in res_env.output


def test_cli_hygiene_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    target_py = tmp_path / "dirty.py"
    target_py.write_text(
        "import sys\nimport os\n\nprint(os.getcwd())\n", encoding="utf-8"
    )

    # clean-imports
    res_clean = runner.invoke(cli, ["hygiene", "clean-imports", str(target_py)])
    assert res_clean.exit_code == 0
    assert "Cleaned 1 unused import(s)" in res_clean.output


def test_cli_bundle_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "main.js").write_text("console.log('test');", encoding="utf-8")

    res_analyze = runner.invoke(cli, ["bundle", "analyze", str(dist_dir)])
    assert res_analyze.exit_code == 0
    assert "main.js" in res_analyze.output


def test_cli_score_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    svg_out = tmp_path / "badge.svg"
    html_out = tmp_path / "report.html"

    res_score = runner.invoke(
        cli,
        [
            "score",
            "compute",
            "--export-svg",
            str(svg_out),
            "--export-html",
            str(html_out),
        ],
    )
    assert res_score.exit_code == 0
    assert "Composite Quality Score" in res_score.output
    assert svg_out.exists()
    assert html_out.exists()


def test_cli_consensus_subcommands(tmp_path: Path) -> None:
    runner = CliRunner()
    f1 = tmp_path / "claude.json"
    f1.write_text(
        json.dumps(
            [
                {
                    "path": "src/auth.py",
                    "line": 42,
                    "rule": "SEC001",
                    "severity": "high",
                    "message": "SQL Injection risk",
                }
            ]
        ),
        encoding="utf-8",
    )
    f2 = tmp_path / "gpt4.json"
    f2.write_text(
        json.dumps(
            [
                {
                    "path": "src/auth.py",
                    "line": 42,
                    "rule": "SEC001",
                    "severity": "high",
                    "message": "SQL Injection risk",
                }
            ]
        ),
        encoding="utf-8",
    )

    res_reconcile = runner.invoke(cli, ["consensus", "reconcile", str(f1), str(f2)])
    assert res_reconcile.exit_code == 0
    assert "Consensus Findings" in res_reconcile.output
    assert "SQL Injection risk" in res_reconcile.output
