"""Experimental semantic-drift safety contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.semantic_drift import SemanticDriftTool


def test_semantic_drift_is_skipped_without_explicit_execution_guards(
    tmp_path: Path,
) -> None:
    result = SemanticDriftTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "allow-browser" in result["summary"]
    assert "allow-slow" in result["summary"]
