"""Contract tests T-62.07, T-62.08, T-62.23 for handoff diffs (Phase 62 §6.5 Invariant 3, §9 P62.4)."""

from __future__ import annotations

from pathlib import Path

import rush.hook.tamper_detector  # noqa: F401 -- import first, breaks a pre-existing circular

# import (memory.store -> hook -> tools -> continuity -> memory.checkpoint_journal ->
# memory.migration -> memory.store) that otherwise fires when a continuity module is the
# first module of this cycle touched in the process. See tests/test_phase61_handoff.py.

from rush.permissions import ExecutionPermissions
from rush.tools.continuity import SessionContinuityTool


def test_second_handoff_to_same_tool_sends_delta_only(tmp_path: Path) -> None:
    """T-62.07: a second handoff to a provider that already received one sends only the
    fields that changed since the prior handoff to that same provider, not the full
    snapshot."""
    tool = SessionContinuityTool()
    tool(
        path=tmp_path,
        operation="save",
        name="first",
        allow_cache_write=True,
        current_goal="build feature A",
        open_work=["task-1"],
        provider_id="codex_cli",
    )
    second = tool(
        path=tmp_path,
        operation="save",
        name="second",
        allow_cache_write=True,
        current_goal="build feature B",
        open_work=["task-1"],
        provider_id="codex_cli",
    )

    diff = second["metadata"]["handoff"]["diff"]
    assert diff == {"current_goal": "build feature B"}


def test_first_handoff_to_a_tool_sends_full_snapshot(tmp_path: Path) -> None:
    """T-62.08: no prior saved checkpoint has `target_provider == "codex_cli"`; the full
    snapshot is sent since there is no delta base to diff against."""
    tool = SessionContinuityTool()
    result = tool(
        path=tmp_path,
        operation="save",
        name="first",
        allow_cache_write=True,
        current_goal="build feature A",
        open_work=["task-1"],
        provider_id="codex_cli",
    )

    receipt = result["metadata"]["handoff"]
    diff = receipt["diff"]
    assert diff["current_goal"] == receipt["current_goal"]
    assert diff["open_work"] == receipt["open_work"]
    assert diff["historic_instruction"] == receipt["historic_instruction"]
    assert diff["dependencies"] == receipt["dependencies"]


def test_direct_run_caller_without_call_still_threads_provider_id(
    tmp_path: Path,
) -> None:
    """T-62.23: `cli.py`'s `rush session save` calls `SessionContinuityTool().run()`
    directly, bypassing `__call__()`; `target_provider` must still be merged into the
    handoff and land in the persisted receipt."""
    tool = SessionContinuityTool()
    result = tool.run(
        tmp_path,
        operation="save",
        name="direct",
        handoff={"current_goal": "ship it", "open_work": []},
        provider_id="codex_cli",
        permissions=ExecutionPermissions(cache_write=True),
    )

    assert result["metadata"]["handoff"]["target_provider"] == "codex_cli"
