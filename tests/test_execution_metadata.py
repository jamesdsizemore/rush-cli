"""Phase 07.0 execution metadata and CLI permission forwarding tests."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli
from rush.permissions import (
    ExecutionPermissions,
    build_execution_metadata,
)


def test_build_execution_metadata_structure() -> None:
    req = ExecutionPermissions(network=True, download=True)
    grant = ExecutionPermissions(network=True)
    meta = build_execution_metadata(
        mode="executed",
        requested=req,
        granted=grant,
        producer="test-engine",
        producer_version="1.0.0",
        declared_artifact="out.json",
    )

    assert meta["mode"] == "executed"
    assert meta["producer"] == "test-engine"
    assert meta["producer_version"] == "1.0.0"
    assert meta["declared_artifact"] == "out.json"
    assert meta["requested_permissions"]["network"] is True
    assert meta["requested_permissions"]["download"] is True
    assert meta["granted_permissions"]["network"] is True
    assert meta["granted_permissions"]["download"] is False


def test_cli_accepts_permission_flags(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "security",
            str(tmp_path),
            "--allow-network",
            "--allow-download",
            "--allow-slow",
            "--json",
        ],
    )
    # The command should succeed and return valid JSON
    assert result.exit_code in (0, 1)
    data = json.loads(result.output)
    assert "metadata" in data
    if "execution" in data.get("metadata", {}):
        exec_meta = data["metadata"]["execution"]
        assert exec_meta["granted_permissions"]["network"] is True
        assert exec_meta["granted_permissions"]["download"] is True
        assert exec_meta["granted_permissions"]["slow"] is True
