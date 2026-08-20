"""Phase 08 Browser runtime evidence and permission boundary tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.e2e import E2eTool
from rush.tools.semantic_drift import SemanticDriftTool
from rush.tools.visual import VisualTool


def test_semantic_drift_requires_both_browser_and_slow_permissions(
    monkeypatch, tmp_path: Path
) -> None:
    tool = SemanticDriftTool()

    # Denied by default
    denied = tool.run(tmp_path)
    assert denied["status"] == "skipped"
    assert "--allow-browser" in denied["summary"]
    assert denied["metadata"]["execution"]["mode"] == "executed"

    # With only browser granted
    perms_browser_only = ExecutionPermissions(browser=True)
    denied_slow = tool.run(tmp_path, permissions=perms_browser_only)
    assert denied_slow["status"] == "skipped"

    # With both granted
    perms_both = ExecutionPermissions(browser=True, slow=True)
    import rush.tools.semantic_drift as sd_mod

    monkeypatch.setattr(sd_mod, "engine_on_path", lambda _b: True)
    monkeypatch.setattr(
        sd_mod,
        "run_subprocess",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="drift tests passed", stderr=""
        ),
    )
    granted = tool.run(tmp_path, permissions=perms_both)
    assert granted["status"] == "ok"
    assert granted["metadata"]["evidence_source"] == "browser-runtime"
    assert granted["metadata"]["execution"]["mode"] == "executed"
    assert granted["metadata"]["execution"]["granted_permissions"]["browser"] is True


def test_e2e_requires_browser_permission(tmp_path: Path) -> None:
    tool = E2eTool()
    denied = tool.run(tmp_path)
    assert denied["status"] == "skipped"
    assert "--allow-browser" in denied["summary"]

    perms = ExecutionPermissions(browser=True)
    granted = tool.run(tmp_path, permissions=perms)
    assert granted["metadata"]["execution"]["mode"] == "executed"
    assert granted["metadata"]["execution"]["granted_permissions"]["browser"] is True


def test_visual_requires_accept_option_for_baselines(tmp_path: Path) -> None:
    tool = VisualTool()
    denied = tool.run(tmp_path)
    assert denied["status"] == "skipped"
    assert "accept" in denied["summary"]
