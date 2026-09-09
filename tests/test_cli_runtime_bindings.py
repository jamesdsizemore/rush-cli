"""CLI commands must call installed backends and report their actual results."""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.governance.synchronizer import AgentsMdSynchronizer


def test_dead_assets_command_respects_requested_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assets = tmp_path / "public"
    assets.mkdir()
    (assets / "used.png").write_bytes(b"used")
    (assets / "unused.svg").write_bytes(b"unused")
    (tmp_path / "outside.png").write_bytes(b"outside")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.tsx").write_text('<img src="/used.png" />')

    result = CliRunner().invoke(cli, ["bundle", "dead-assets", "public"])

    assert result.exit_code == 0, result.exception
    assert result.output == f"Unreferenced Assets (1):\n  - {assets / 'unused.svg'}\n"


def test_governance_check_reports_real_parity_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Run tests before committing.\n")
    AgentsMdSynchronizer(tmp_path).sync_all()
    runner = CliRunner()

    clean = runner.invoke(cli, ["governance", "check"])
    assert clean.exit_code == 0, clean.exception
    assert clean.output == "[OK] All multi-IDE governance rule files match AGENTS.md.\n"

    (tmp_path / ".cursorrules").write_text("stale rules\n")
    drift = runner.invoke(cli, ["governance", "check"])
    assert drift.exit_code == 1
    assert ".cursorrules: Rule file out of sync with AGENTS.md SHA." in drift.output


def test_bus_factor_command_reports_actual_ownership(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hooks = tmp_path / "disabled-hooks"
    hooks.mkdir()

    def git(*args: str, author: str = "Alice") -> None:
        subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                f"user.name={author}",
                "-c",
                "user.email=test@example.test",
                *args,
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-b", "fixture")
    for number, author in enumerate(("Alice", "Alice", "Bob"), 1):
        (tmp_path / "app.py").write_text(f"value = {number}\n")
        git("add", "app.py")
        git("commit", "-m", f"Edit {number}", author=author)

    result = CliRunner().invoke(cli, ["hotspots", "bus-factor"])

    assert result.exit_code == 0, result.exception
    assert "app.py: 2 authors, ownership entropy 0.92" in result.output
    assert "Primary author: Alice 66.7%" in result.output
