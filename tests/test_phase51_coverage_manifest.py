"""Contract tests for First-Party Coverage Boundary (Phase 51: P51.1.1)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from rush.governance.coverage_manifest import (
    build_manifest,
    classify_path,
    render_toml,
)


def test_manifest_covers_every_first_party_path_once(tmp_path: Path) -> None:
    # Arrange synthetic tree
    (tmp_path / "src" / "rush").mkdir(parents=True)
    (tmp_path / "src" / "rush" / "main.py").write_text(
        "print('hello')", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "test_main.py").write_text(
        "def test_ok(): pass", encoding="utf-8"
    )
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "run.py").write_text("# script", encoding="utf-8")
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "index.md").write_text("# Docs", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='app'", encoding="utf-8")

    manifest = build_manifest(tmp_path, revision="test-rev")

    paths = [record.path for record in manifest.records]
    assert len(paths) == len(set(paths)), "Every path must be classified exactly once"
    assert "src/rush/main.py" in paths
    assert "tests/test_main.py" in paths
    assert "scripts/run.py" in paths
    assert "docs/index.md" in paths
    assert "pyproject.toml" in paths

    # Verify classification types
    record_map = {r.path: r for r in manifest.records}
    assert record_map["src/rush/main.py"].classification == "source"
    assert record_map["tests/test_main.py"].classification == "test"
    assert record_map["scripts/run.py"].classification == "script"
    assert record_map["docs/index.md"].classification == "doc"
    assert record_map["pyproject.toml"].classification == "metadata"


def test_manifest_is_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "z.md").write_text("z", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text("a", encoding="utf-8")

    manifest1 = build_manifest(tmp_path, revision="rev-1")
    manifest2 = build_manifest(tmp_path, revision="rev-1")

    toml1 = render_toml(manifest1)
    toml2 = render_toml(manifest2)

    assert toml1 == toml2, (
        "Rendered TOML must be byte-stable and deterministically sorted"
    )
    parsed = tomllib.loads(toml1)
    assert parsed["manifest"]["revision"] == "rev-1"
    assert len(parsed["records"]) >= 4


def test_manifest_rejects_unclassified_tracked_path(tmp_path: Path) -> None:
    # A path that does not match any known rule should raise or be flagged
    with pytest.raises(ValueError, match="Unclassified first-party path"):
        classify_path("unknown_foreign_blob.bin")


def test_repository_coverage_manifest_is_valid_and_non_empty() -> None:
    manifest_file = Path("governance/first-party-coverage.toml")
    assert manifest_file.is_file(), "governance/first-party-coverage.toml must exist"
    data = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
    assert "manifest" in data
    assert "records" in data
    assert len(data["records"]) > 0
    records = data["records"]
    assert any(r["path"] == "pyproject.toml" for r in records)
    assert any(r["classification"] == "source" for r in records)
