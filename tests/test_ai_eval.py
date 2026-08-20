"""Tests for AiEvalTool (Phase 09)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.ai_eval import AiEvalTool


def test_ai_eval_skipped_when_no_engine(monkeypatch, tmp_path: Path) -> None:
    tool = AiEvalTool()
    # Ensure no binary found
    monkeypatch.setattr("rush.tools.ai_eval.engine_on_path", lambda _bin: False)

    res = tool.run(tmp_path, permissions=ExecutionPermissions())
    assert res["status"] == "skipped"
    assert "no AI evaluation engine" in res["summary"]
    assert res["metadata"]["execution"]["mode"] == "executed"
    assert res["metadata"]["execution"]["producer"] == "ai-eval"


def test_ai_eval_call_interface(monkeypatch, tmp_path: Path) -> None:
    tool = AiEvalTool()
    monkeypatch.setattr("rush.tools.ai_eval.engine_on_path", lambda _bin: False)

    res = tool(tmp_path, allow_slow=True, allow_network=True)
    assert res["status"] == "skipped"
    assert res["metadata"]["execution"]["requested_permissions"]["slow"] is True
    assert res["metadata"]["execution"]["requested_permissions"]["network"] is True
