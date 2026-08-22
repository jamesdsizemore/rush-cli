"""Unit tests for Phase 41 Memory and Ship Readiness Tools."""

from pathlib import Path

from src.rush.memory.checkpoint_journal import CheckpointJournal
from src.rush.memory.preference_store import PreferenceStore
from src.rush.tools.ship.cleaner import ScratchCleaner
from src.rush.tools.ship.docs_linter import DocsLinter
from src.rush.tools.ship.env_linter import EnvParityLinter


def test_preference_store(tmp_path: Path):
    store = PreferenceStore(project_root=tmp_path)
    assert store.list_all() == {}

    store.set("editor.theme", "dark")
    assert store.get("editor.theme") == "dark"
    assert store.get("nonexistent", "default") == "default"

    assert store.delete("editor.theme") is True
    assert store.get("editor.theme") is None
    assert store.delete("editor.theme") is False


def test_checkpoint_journal(tmp_path: Path):
    journal = CheckpointJournal(project_root=tmp_path)
    assert journal.list_checkpoints() == []

    dest = journal.save_checkpoint(
        "session-1", {"author": "agent"}, ["src/main.py", "tests/test.py"]
    )
    assert dest.exists()

    data = journal.restore_checkpoint("session-1")
    assert data is not None
    assert data["name"] == "session-1"
    assert data["files"] == ["src/main.py", "tests/test.py"]

    assert journal.restore_checkpoint("nonexistent") is None
    checkpoints = journal.list_checkpoints()
    assert len(checkpoints) == 1


def test_scratch_cleaner(tmp_path: Path):
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()
    (scratch_dir / "temp.txt").write_text("temporary data", encoding="utf-8")

    cleaner = ScratchCleaner(project_root=tmp_path)

    # Dry run
    dry_res = cleaner.clean(dry_run=True)
    assert dry_res["removed_count"] >= 1
    assert scratch_dir.exists()

    # Real clean
    clean_res = cleaner.clean(dry_run=False)
    assert clean_res["removed_count"] >= 1
    assert not scratch_dir.exists()


def test_env_parity_linter(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        """
import os
db_url = os.getenv("DATABASE_URL")
api_key = os.environ.get("API_KEY")
""",
        encoding="utf-8",
    )

    # Case 1: Missing in .env.example
    (tmp_path / ".env.example").write_text(
        "DATABASE_URL=sqlite:///app.db\n", encoding="utf-8"
    )
    linter = EnvParityLinter(project_root=tmp_path)
    res = linter.lint()
    assert res["passed"] is False
    assert "API_KEY" in res["missing_in_example"]

    # Case 2: All declared
    (tmp_path / ".env.example").write_text(
        "DATABASE_URL=sqlite:///app.db\nAPI_KEY=secret\n", encoding="utf-8"
    )
    res2 = linter.lint()
    assert res2["passed"] is True
    assert res2["missing_in_example"] == []


def test_docs_linter(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("See [readme](readme.md)", encoding="utf-8")

    linter = DocsLinter(project_root=tmp_path)
    res = linter.lint()
    assert res["passed"] is False
    assert res["broken_links_count"] == 1

    # Fix link
    (docs_dir / "readme.md").write_text("# Readme", encoding="utf-8")
    res2 = linter.lint()
    assert res2["passed"] is True
