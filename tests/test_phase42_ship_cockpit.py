"""Unit tests for Phase 42 Ship Gate Cockpit and Linters."""

from pathlib import Path

from src.rush.tools.ship.cockpit import ShipCockpit
from src.rush.tools.ship.migration_linter import MigrationLinter
from src.rush.tools.ship.package_linter import PackageLinter
from src.rush.tools.ship.semver_linter import SemverLinter


def test_migration_linter_table_locks():
    linter = MigrationLinter()

    # Dangerous SQL
    bad_sql = "ALTER TABLE users ADD COLUMN age INT NOT NULL;"
    hazards = linter.check_sql(bad_sql)
    assert len(hazards) >= 1
    assert "Table-locking" in hazards[0]

    # Safe SQL
    safe_sql = "ALTER TABLE users ADD COLUMN age INT DEFAULT 0 NOT NULL;"
    assert linter.check_sql(safe_sql) == []


def test_semver_linter():
    linter = SemverLinter()
    old_code = (
        "def process(item: str, count: int) -> bool:\n"
        "    pass\n"
        "def old_helper():\n"
        "    pass\n"
    )
    new_code = "def process(item: str) -> bool:\n    pass\n"

    breaking = linter.diff_apis(old_code, new_code)
    assert len(breaking) == 2
    assert any("old_helper" in b for b in breaking)
    assert any("process" in b for b in breaking)


def test_package_linter(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / ".env").write_text("SECRET=123", encoding="utf-8")

    linter = PackageLinter(project_root=tmp_path)
    res = linter.lint()
    assert res["passed"] is False
    assert res["leaks_count"] == 1


def test_ship_cockpit_evaluation(tmp_path: Path):
    # Setup a clean minimal workspace
    (tmp_path / ".env.example").write_text(
        "DATABASE_URL=sqlite:///app.db\n", encoding="utf-8"
    )
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "index.md").write_text("# Documentation", encoding="utf-8")

    cockpit = ShipCockpit(project_root=tmp_path)
    verdict = cockpit.evaluate_gate()
    assert len(verdict.vectors) == 5
    assert verdict.all_passed is True
    assert verdict.score_pct == 100.0
