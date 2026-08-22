"""Live integration tests executing all installed quality engines against a real polyglot project."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.tools import ALL_TOOLS
from tests.fixtures.live_polyglot_generator import create_polyglot_test_repo


def test_all_tools_execute_live_on_polyglot_repo(tmp_path: Path) -> None:
    repo_dir = create_polyglot_test_repo(tmp_path)

    results = {}
    for tool in ALL_TOOLS:
        try:
            res = tool.run(repo_dir)
            results[tool.name] = res
            assert "tool" in res
            assert "status" in res
            assert "summary" in res
            assert "findings" in res
            assert res["status"] in ("ok", "warn", "fail", "error", "skipped")
        except Exception as e:
            raise AssertionError(
                f"Tool '{tool.name}' crashed during live execution: {e}"
            ) from e

    # Assert specific installed tools produce valid results
    assert results["review"]["status"] in ("ok", "warn")
    assert results["lint"]["status"] in ("ok", "warn")
    assert results["format"]["status"] in ("ok", "warn")
    assert results["sql"]["status"] in ("ok", "warn", "skipped")
    assert results["templates"]["status"] in ("ok", "warn", "skipped")
    assert results["markdown"]["status"] in ("ok", "warn", "skipped")
    assert results["doctor"]["status"] in ("ok", "warn")


def test_cli_live_scans_on_polyglot_repo(tmp_path: Path) -> None:
    repo_dir = create_polyglot_test_repo(tmp_path)
    runner = CliRunner()

    # 1. rush review
    res_rev = runner.invoke(cli, ["review", str(repo_dir)])
    assert res_rev.exit_code in (0, 1)

    # 2. rush lint
    res_lint = runner.invoke(cli, ["lint", str(repo_dir)])
    assert res_lint.exit_code in (0, 1)

    # 3. rush format --check
    res_fmt = runner.invoke(cli, ["format", str(repo_dir)])
    assert res_fmt.exit_code in (0, 1)

    # 4. rush markdown
    res_md = runner.invoke(cli, ["markdown", str(repo_dir)])
    assert res_md.exit_code in (0, 1)

    # 5. rush sql
    res_sql = runner.invoke(cli, ["sql", str(repo_dir)])
    assert res_sql.exit_code in (0, 1)

    # 6. rush templates
    res_tmpl = runner.invoke(cli, ["templates", str(repo_dir)])
    assert res_tmpl.exit_code in (0, 1)

    # 7. rush doctor
    res_doc = runner.invoke(cli, ["doctor", str(repo_dir)])
    assert res_doc.exit_code == 0
    assert "doctor:" in res_doc.output
