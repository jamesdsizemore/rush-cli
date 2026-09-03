"""Contract tests for Version Authority and Consumer Single-Source-of-Truth (Phase 52: P52.3)."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

import rush
from rush.cli import cli

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_public_version_comes_from_distribution_metadata() -> None:
    """Verify that rush.__version__ is derived from distribution package metadata."""
    try:
        dist_version = importlib.metadata.version("rush-cli")
        assert rush.__version__ == dist_version
    except importlib.metadata.PackageNotFoundError:
        # Fallback in bare non-installed environments
        assert rush.__version__ in ("0.3.0", "0.3.0-dev")


def test_cli_version_matches_public_version() -> None:
    """Verify that `rush --version` emits exactly rush.__version__."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == rush.__version__


def test_version_consumers_have_no_stale_hardcoded_literals() -> None:
    """Verify that no runtime providers, reporters, or generators carry stale '0.2.0' literals."""
    stale_pattern = re.compile(
        r'["\'](?:rush-cli/|Rush v|semanticVersion["\']:\s*["\']|version\s*=\s*["\'])0\.2\.0'
    )

    files_to_check = [
        PROJECT_ROOT / "src" / "rush" / "providers" / "anthropic.py",
        PROJECT_ROOT / "src" / "rush" / "providers" / "openai.py",
        PROJECT_ROOT / "src" / "rush" / "sarif.py",
        PROJECT_ROOT / "src" / "rush" / "score" / "sarif_export.py",
        PROJECT_ROOT / "src" / "rush" / "sync" / "ts_generator.py",
        PROJECT_ROOT / "src" / "rush" / "tui.py",
        PROJECT_ROOT / "src" / "rush" / "governance" / "scaffolder.py",
        PROJECT_ROOT / "src" / "rush" / "tools" / "pr_synthesize.py",
    ]

    violations: list[str] = []
    for filepath in files_to_check:
        content = filepath.read_text(encoding="utf-8")
        if stale_pattern.search(content):
            violations.append(filepath.name)

    assert not violations, (
        f"Found stale '0.2.0' hardcoded version literals in: {', '.join(violations)}. "
        "These must reference rush.__version__."
    )


def test_version_dev_fallback_on_package_not_found() -> None:
    """Verify that rush module handles PackageNotFoundError by falling back to 0.3.0."""
    with patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        importlib.reload(rush)
        assert rush.__version__ == "0.3.0"

    # Restore regular version
    importlib.reload(rush)
