"""Exercise public patch application against real isolated Git checkouts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True
    ).stdout


def _patch_project(root: Path, *, passing: bool = True) -> Path:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "patch-test@example.invalid")
    _git(root, "config", "user.name", "Patch test")
    (root / ".gitignore").write_text(".rush/\n__pycache__/\n.pytest_cache/\n")
    (root / "app.py").write_text("def value():\n    return 1\n")
    (root / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    (root / "tests").mkdir()
    (root / "tests/test_app.py").write_text(
        "from app import value\n\ndef test_value():\n"
        f"    assert value() == {2 if passing else 3}\n"
    )
    patch_file = root / "fix.patch"
    patch_file.write_text(
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n"
        " def value():\n-    return 1\n+    return 2\n"
    )
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    return patch_file


def test_apply_dry_run_preserves_source(tmp_path: Path, monkeypatch) -> None:
    patch_file = _patch_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    before_head = _git(tmp_path, "rev-parse", "HEAD")
    before_index = (tmp_path / ".git/index").read_bytes()

    result = CliRunner().invoke(
        cli,
        ["patch", "apply", str(patch_file), "--dry-run", "--circuit-breaker", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["metadata"]["promoted"] is False
    assert payload["metadata"]["verified"] is True
    assert payload["metadata"]["executed_commands"] == 1
    assert (tmp_path / "app.py").read_text() == "def value():\n    return 1\n"
    assert _git(tmp_path, "rev-parse", "HEAD") == before_head
    assert (tmp_path / ".git/index").read_bytes() == before_index


@pytest.mark.parametrize(
    "circuit_breaker", ["--circuit-breaker", "--no-circuit-breaker"]
)
def test_apply_refuses_failed_verification(
    tmp_path: Path, monkeypatch, circuit_breaker
) -> None:
    patch_file = _patch_project(tmp_path, passing=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "patch",
            "apply",
            str(patch_file),
            "--no-dry-run",
            circuit_breaker,
            "--allow-artifact-write",
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "fail"
    assert payload["metadata"]["promoted"] is False
    assert payload["metadata"]["executed_commands"] == 1
    assert (tmp_path / "app.py").read_text() == "def value():\n    return 1\n"
    assert _git(tmp_path, "status", "--porcelain") == b""


def test_apply_requires_grant_and_promotes_verified_patch(
    tmp_path: Path, monkeypatch
) -> None:
    patch_file = _patch_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    denied = runner.invoke(
        cli, ["patch", "apply", str(patch_file), "--no-dry-run", "--json"]
    )
    assert denied.exit_code == 0, denied.output
    assert json.loads(denied.output)["status"] == "skipped"
    assert (tmp_path / "app.py").read_text() == "def value():\n    return 1\n"

    applied = runner.invoke(
        cli,
        [
            "patch",
            "apply",
            str(patch_file),
            "--no-dry-run",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert applied.exit_code == 0, applied.output
    payload = json.loads(applied.output)
    assert payload["status"] == "ok"
    assert payload["metadata"]["promoted"] is True
    assert (tmp_path / "app.py").read_text() == "def value():\n    return 2\n"
    assert _git(tmp_path, "diff", "--cached") == b""


def test_apply_verifies_src_layout_from_sandbox(tmp_path: Path, monkeypatch) -> None:
    patch_file = _patch_project(tmp_path)
    package = tmp_path / "src/rush"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("ISOLATION_MARKER = 1\n")
    (tmp_path / "tests/test_app.py").write_text(
        "from pathlib import Path\nimport rush\n\ndef test_value():\n"
        "    assert rush.ISOLATION_MARKER == 2\n"
        "    assert Path(rush.__file__).is_relative_to(Path.cwd())\n"
    )
    patch_file.write_text(
        "--- a/src/rush/__init__.py\n+++ b/src/rush/__init__.py\n"
        "@@ -1 +1 @@\n-ISOLATION_MARKER = 1\n+ISOLATION_MARKER = 2\n"
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "src layout")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        cli, ["patch", "apply", str(patch_file), "--dry-run", "--json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["metadata"]["verified"] is True
    assert (package / "__init__.py").read_text() == "ISOLATION_MARKER = 1\n"
