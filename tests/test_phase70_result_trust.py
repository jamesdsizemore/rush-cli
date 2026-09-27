"""Tests for Phase 70 W2 "Results an agent can trust" packets.

Contracts:
- T8: CLI, standard MCP, custom MCP wrappers, suite, and scan callers resolve
  a relative/absolute target to the same normalized logical target exactly
  once (no double rebase: CLI's `src/bad.py` must never become
  `project/src/src/bad.py`), while `InvocationContext` retains the caller's
  original requested strings and the invocation-start cwd for diagnostics.

Later T9-T17 tests for this same plan packet also live in this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from rush.engines.staging import StagingContext, staging_scope
from rush.invocation import InvocationContext
from rush.invocation.models import AmbiguousRootError, ScopeWideningError
from rush.invocation.targets import resolve_logical_root
from rush.permissions import ExecutionPermissions
from rush.workflows.project_run import ScanCandidate, _execute_candidate
from rush.workflows.projects import register_project, resolve_project
from rush.workflows.suites import WorkflowSuite, run_workflow_suite


class _ProbeTool:
    """Minimal ALL_TOOLS-shaped probe: reports exactly the path it received."""

    def __init__(self, name: str = "t8-probe") -> None:
        self.name = name
        self.mcp_description = "t8 probe"

    def __call__(self, path: Path = Path(".")) -> dict:
        return {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "probe",
            "findings": [],
            "path": str(path),
        }


def _custom_probe(path: Path = Path(".")) -> dict:
    return {"status": "ok", "path": str(path)}


def _spy(monkeypatch: pytest.MonkeyPatch, module) -> list[InvocationContext]:
    """Wrap `module.resolve_invocation`, recording every real context it builds."""
    captured: list[InvocationContext] = []
    original = module.resolve_invocation

    def spy_fn(*args, **kwargs):
        ctx = original(*args, **kwargs)
        captured.append(ctx)
        return ctx

    monkeypatch.setattr(module, "resolve_invocation", spy_fn)
    return captured


def _resolved_target(context: InvocationContext) -> Path:
    assert len(context.targets) == 1
    return context.workspace_root / context.targets[0].relative_path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "has space.py").write_text("x = 1\n", encoding="utf-8")
    return root


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, typed_path: str, chdir: Path
) -> InvocationContext:
    from rush.cli_support import rendering

    monkeypatch.chdir(chdir)
    monkeypatch.setattr(rendering, "ALL_TOOLS", [_ProbeTool()])
    captured = _spy(monkeypatch, rendering)
    with pytest.raises(SystemExit):
        rendering._run_tool("t8-probe", Path(typed_path), as_json=True)
    return captured[-1]


def _run_mcp_standard(
    monkeypatch: pytest.MonkeyPatch,
    typed_path: str,
    chdir: Path,
    anchor_cwd: Path | None = None,
) -> tuple[InvocationContext, dict]:
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(chdir)
    captured = _spy(monkeypatch, tool_registry)
    tool = _ProbeTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    wrapper = tool_registry.make_tool_wrapper(tool, executor, anchor_cwd=anchor_cwd)
    result = wrapper(path=typed_path)
    return captured[-1], result


def _run_mcp_custom(
    monkeypatch: pytest.MonkeyPatch,
    typed_path: str,
    chdir: Path,
    anchor_cwd: Path | None = None,
) -> tuple[InvocationContext, dict]:
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(chdir)
    captured = _spy(monkeypatch, tool_registry)
    executor = InvocationExecutor()
    executor.register("t8-custom-probe", tool_registry._make_handler(_custom_probe))
    wrapper = tool_registry.make_custom_wrapper(
        _custom_probe, "t8-custom-probe", executor, anchor_cwd=anchor_cwd
    )
    result = wrapper(path=typed_path)
    return captured[-1], result


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
@pytest.mark.parametrize("relative_filename", ["src/bad.py", "src/has space.py"])
@pytest.mark.parametrize("cwd_choice", ["root", "nested", "sibling"])
def test_t08_relative_target_identity(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    cwd_choice: str,
    relative_filename: str,
    transport: str,
) -> None:
    target_file = project / relative_filename
    cwd = {
        "root": project,
        "nested": project / "src",
        "sibling": project.parent,
    }[cwd_choice]
    typed = os.path.relpath(target_file, cwd)

    if transport == "cli":
        context = _run_cli(monkeypatch, typed, cwd)
    elif transport == "mcp-standard":
        context, _ = _run_mcp_standard(monkeypatch, typed, cwd)
    else:
        context, _ = _run_mcp_custom(monkeypatch, typed, cwd)

    assert _resolved_target(context) == target_file.resolve()
    assert context.original_requested_targets == (typed,)


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
def test_t08_absolute_target_identity(
    monkeypatch: pytest.MonkeyPatch, project: Path, transport: str
) -> None:
    target_file = project / "src" / "bad.py"
    typed = str(target_file)

    if transport == "cli":
        context = _run_cli(monkeypatch, typed, project)
    elif transport == "mcp-standard":
        context, _ = _run_mcp_standard(monkeypatch, typed, project)
    else:
        context, _ = _run_mcp_custom(monkeypatch, typed, project)

    assert _resolved_target(context) == target_file.resolve()
    assert context.original_requested_targets == (typed,)


def test_t08_missing_path_reports_deleted_state_without_double_rebase(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    context = _run_cli(monkeypatch, "src/missing.py", project)

    assert _resolved_target(context) == project / "src" / "missing.py"
    assert context.targets[0].state == "deleted"


def test_t08_dotdot_input_resolves_without_parent_traversal_rejection(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    # Deliberately verbose: up out of `src/`, then back down into it.
    context = _run_cli(monkeypatch, "../src/bad.py", project / "src")

    assert _resolved_target(context) == (project / "src" / "bad.py").resolve()


def test_t08_declared_root_precedence_wins_over_request_workspace_root(
    tmp_path: Path,
) -> None:
    from rush.invocation import resolve_invocation

    declared = tmp_path / "declared"
    declared.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    context = resolve_invocation(
        {"operation_id": "t8-probe", "workspace_root": str(other)},
        transport="cli",
        workspace_root=declared,
    )

    assert context.workspace_root == declared.resolve()


def test_t08_process_cwd_change_after_server_start_does_not_retarget(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    # The anchor is captured once at wrapper-creation time (mirrors
    # build_server capturing the server-start cwd exactly once), then the
    # process cwd changes before the relative call is actually made.
    monkeypatch.chdir(project)
    anchor_cwd = Path.cwd().resolve()
    context, result = _run_mcp_standard(
        monkeypatch, "src/bad.py", project / "src", anchor_cwd=anchor_cwd
    )

    assert _resolved_target(context) == (project / "src" / "bad.py").resolve()
    assert result["status"] == "ok"


def test_t08_suite_file_target_resolves_without_double_rebase(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    from rush.workflows import suites

    monkeypatch.setattr(suites, "ALL_TOOLS", [_ProbeTool()])
    captured = _spy(monkeypatch, suites)
    monkeypatch.chdir(project)

    suite = WorkflowSuite(
        name="t8-suite", description="test", tool_sequence=("t8-probe",)
    )
    aggregate = run_workflow_suite(suite, Path("src/bad.py"), ExecutionPermissions())

    context = captured[-1]
    assert _resolved_target(context) == (project / "src" / "bad.py").resolve()
    # T8 finding 7 (fix round 1): never derived from `path` -- every
    # production caller already passes an already-resolved path, so the
    # default is explicitly "unavailable" (see the dedicated default/
    # passthrough tests below), not a reconstruction of `path` itself.
    assert context.original_requested_targets == ()
    assert aggregate["status"] == "ok"


def _registered_project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "scan-project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "rush-data"
    register_project(root, data_root=data_root)
    return root, data_root


def test_t08_nested_scan_target_resolves_under_declared_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from rush.workflows import project_run

    root, _ = _registered_project(tmp_path)
    captured = _spy(monkeypatch, project_run)

    candidate = ScanCandidate(
        candidate_id="t8-probe",
        kind="tool",
        category="quality",
        disposition="applicable",
        reason="test",
    )
    outcome, result = _execute_candidate(
        candidate,
        root=root,
        permissions=ExecutionPermissions(),
        targets={"t8-probe": {"path": "src/bad.py"}},
        config=None,
        tools_by_name={"t8-probe": _ProbeTool()},
    )

    context = captured[-1]
    assert outcome == "executed"
    assert result["status"] == "ok"
    assert _resolved_target(context) == (root / "src" / "bad.py").resolve()
    assert context.original_requested_targets == ("src/bad.py",)


def test_t08_staged_scan_preserves_original_while_normalizing_execution_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from rush.workflows import project_run

    root, _ = _registered_project(tmp_path)
    staged_root = tmp_path / "staged"
    (staged_root / "src").mkdir(parents=True)
    (staged_root / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")

    captured = _spy(monkeypatch, project_run)

    candidate = ScanCandidate(
        candidate_id="t8-probe",
        kind="tool",
        category="quality",
        disposition="applicable",
        reason="test",
    )
    staging_context = StagingContext(original_root=root, staged_root=staged_root)

    with staging_scope(staging_context):
        outcome, result = _execute_candidate(
            candidate,
            root=root,
            permissions=ExecutionPermissions(),
            targets={"t8-probe": {"path": "src/bad.py"}},
            config=None,
            tools_by_name={"t8-probe": _ProbeTool()},
        )

    context = captured[-1]
    assert outcome == "executed"
    assert result["status"] == "ok"
    # Execution identity is the staged tree, never the logical project root.
    assert _resolved_target(context) == (staged_root / "src" / "bad.py").resolve()
    # Original request data survives the staging substitution untouched.
    assert context.original_requested_targets == ("src/bad.py",)


def test_t08_original_strings_survive_for_relative_and_absolute_aliases(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    target_file = project / "src" / "bad.py"

    relative_context = _run_cli(monkeypatch, "src/bad.py", project)
    absolute_context = _run_cli(monkeypatch, str(target_file), project)

    assert _resolved_target(relative_context) == _resolved_target(absolute_context)
    assert relative_context.original_requested_targets == ("src/bad.py",)
    assert absolute_context.original_requested_targets == (str(target_file),)


# --- FIX ROUND 1 review findings -------------------------------------------


@pytest.fixture
def project_with_marker(tmp_path: Path) -> Path:
    """Same shape as `project`, plus a `rush.toml` at its own root so the
    logical-root climb (tier 2) has something to find."""
    root = tmp_path / "marked-project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    (root / "rush.toml").write_text("[tools.lint]\n", encoding="utf-8")
    return root


def _run_cli_raises(
    monkeypatch: pytest.MonkeyPatch, typed_path: str, chdir: Path, exc_type: type
) -> None:
    from rush.cli_support import rendering

    monkeypatch.chdir(chdir)
    monkeypatch.setattr(rendering, "ALL_TOOLS", [_ProbeTool()])
    with pytest.raises(exc_type):
        rendering._run_tool("t8-probe", Path(typed_path), as_json=True)


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
def test_t08_escaping_symlink_raises_scope_widening_error(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    outside = project_with_marker.parent / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET = 1\n", encoding="utf-8")
    (project_with_marker / "src" / "link.py").symlink_to(outside / "secret.py")

    if transport == "cli":
        _run_cli_raises(
            monkeypatch, "src/link.py", project_with_marker, ScopeWideningError
        )
        return

    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(project_with_marker)
    if transport == "mcp-standard":
        tool = _ProbeTool()
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
        wrapper = tool_registry.make_tool_wrapper(tool, executor)
        with pytest.raises(ScopeWideningError):
            wrapper(path="src/link.py")
    else:
        executor = InvocationExecutor()
        executor.register("t8-custom-probe", tool_registry._make_handler(_custom_probe))
        wrapper = tool_registry.make_custom_wrapper(
            _custom_probe, "t8-custom-probe", executor
        )
        with pytest.raises(ScopeWideningError):
            wrapper(path="src/link.py")


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
def test_t08_in_root_symlink_rejected(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    """Correction: only a symlink *above* the logical root (e.g. macOS's
    /var -> /private/var) is transparently allowed. A symlink anywhere
    inside the root -- even pointing at another file inside that same
    root -- is rejected fail-closed, matching the pre-existing
    resolve_target/open_contained contract (ARCHITECTURE.md, Phase 55/57)."""
    real_target = project_with_marker / "src" / "bad.py"
    alias = project_with_marker / "src" / "alias.py"
    alias.symlink_to(real_target)

    if transport == "cli":
        _run_cli_raises(
            monkeypatch, "src/alias.py", project_with_marker, ScopeWideningError
        )
        return

    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(project_with_marker)
    if transport == "mcp-standard":
        tool = _ProbeTool()
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
        wrapper = tool_registry.make_tool_wrapper(tool, executor)
        with pytest.raises(ScopeWideningError):
            wrapper(path="src/alias.py")
    else:
        executor = InvocationExecutor()
        executor.register("t8-custom-probe", tool_registry._make_handler(_custom_probe))
        wrapper = tool_registry.make_custom_wrapper(
            _custom_probe, "t8-custom-probe", executor
        )
        with pytest.raises(ScopeWideningError):
            wrapper(path="src/alias.py")


def test_t08_above_root_symlink_is_transparently_followed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A symlinked ANCESTOR directory above the logical root (e.g. macOS's
    /var -> /private/var for a tmp_path under it) is followed transparently
    -- only symlinks *inside* the root are rejected."""
    real_base = tmp_path / "real_base"
    (real_base / "proj" / "src").mkdir(parents=True)
    (real_base / "proj" / "rush.toml").write_text("", encoding="utf-8")
    (real_base / "proj" / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    link_base = tmp_path / "link_base"
    link_base.symlink_to(real_base, target_is_directory=True)

    context = _run_cli(monkeypatch, "src/bad.py", link_base / "proj")

    assert (
        _resolved_target(context) == (real_base / "proj" / "src" / "bad.py").resolve()
    )


def test_t08_symlink_loop_raises_scope_widening_error_not_runtime_error(
    tmp_path: Path,
) -> None:
    """Finding 3: no resolve()-and-retry on SYMLINK_DISALLOWED -- a genuine
    symlink loop (a -> b -> a) must fail closed with `ScopeWideningError`,
    never a bare `RuntimeError` from an internal `Path.resolve()` call."""
    from rush.invocation.targets import resolve_target

    root = tmp_path / "looproot"
    root.mkdir()
    (root / "a").symlink_to(root / "b")
    (root / "b").symlink_to(root / "a")

    with pytest.raises(ScopeWideningError):
        resolve_target(root, "a")


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_whitespace_is_literal_not_stripped(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    """Finding 4: leading/trailing whitespace is part of the literal
    filename, never stripped -- a typed " ws.py" must select the
    space-prefixed file, never its unspaced sibling."""
    (project_with_marker / "src" / " ws.py").write_text(
        "LEADING_SPACE_FILE\n", encoding="utf-8"
    )
    (project_with_marker / "src" / "ws.py").write_text("PLAIN_FILE\n", encoding="utf-8")

    if transport == "cli":
        context = _run_cli(monkeypatch, " ws.py", project_with_marker / "src")
    else:
        context, result = _run_mcp_standard(
            monkeypatch, " ws.py", project_with_marker / "src"
        )
        assert result["path"] == str((project_with_marker / "src" / " ws.py").resolve())

    assert (
        _resolved_target(context) == (project_with_marker / "src" / " ws.py").resolve()
    )


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_whitespace_padded_existing_relpath_reports_deleted_state(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    """ " src/bad.py " (with stray spaces) is a different, nonexistent
    literal filename from "src/bad.py" -- it must report a deleted target
    state under the correct (still-unaffected) logical root, never crash
    and never silently resolve to the unspaced sibling."""
    if transport == "cli":
        context = _run_cli(monkeypatch, " src/bad.py ", project_with_marker)
    else:
        context, _ = _run_mcp_standard(monkeypatch, " src/bad.py ", project_with_marker)

    assert context.targets[0].state == "deleted"
    assert context.workspace_root == project_with_marker.resolve()


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_dot_prefixed_input_normalizes(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    target_file = project_with_marker / "src" / "bad.py"

    if transport == "cli":
        context = _run_cli(monkeypatch, "./src/bad.py", project_with_marker)
    else:
        context, _ = _run_mcp_standard(monkeypatch, "./src/bad.py", project_with_marker)

    assert _resolved_target(context) == target_file.resolve()


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_missing_directory_reports_deleted_state_without_crash(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path, transport: str
) -> None:
    if transport == "cli":
        context = _run_cli(monkeypatch, "nope/missing.py", project_with_marker)
    else:
        context, _ = _run_mcp_standard(
            monkeypatch, "nope/missing.py", project_with_marker
        )

    assert context.targets[0].state == "deleted"
    assert context.workspace_root == project_with_marker.resolve()


def test_t08_logical_root_finds_rush_toml_ancestor(project_with_marker: Path) -> None:
    nested = project_with_marker / "src" / "bad.py"
    assert resolve_logical_root(nested) == project_with_marker


def test_t08_logical_root_finds_git_only_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "git-only-project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".git").mkdir()

    assert resolve_logical_root(root / "src" / "bad.py") == root


def test_t08_logical_root_falls_back_to_parent_when_no_markers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "unmarked-project"
    (root / "src").mkdir(parents=True)
    target = root / "src" / "bad.py"
    target.write_text("x = 1\n", encoding="utf-8")

    assert resolve_logical_root(target) == root / "src"


def test_t08_logical_root_honors_explicit_registered_root(tmp_path: Path) -> None:
    root = tmp_path / "registered-project"
    (root / "src").mkdir(parents=True)
    target = root / "src" / "bad.py"
    target.write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)

    resolved = resolve_logical_root(
        target, registered_root=record.project_id, data_root=data_root
    )
    assert resolved == root.resolve()
    assert resolved == Path(
        resolve_project(record.project_id, data_root=data_root)["root"]
    )


def test_t08_ambiguous_registered_root_raises_named_error(tmp_path: Path) -> None:
    registered = tmp_path / "registered-project"
    registered.mkdir(parents=True)
    data_root = tmp_path / "rush-data"
    record = register_project(registered, data_root=data_root)

    other = tmp_path / "unrelated-project"
    (other / "src").mkdir(parents=True)
    outside_target = other / "src" / "bad.py"
    outside_target.write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(AmbiguousRootError):
        resolve_logical_root(
            outside_target, registered_root=record.project_id, data_root=data_root
        )


def test_t08_declared_mcp_root_takes_precedence_over_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    declared_root = tmp_path / "declared-project"
    (declared_root / "src").mkdir(parents=True)
    target = declared_root / "src" / "bad.py"
    target.write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "rush-data"
    record = register_project(declared_root, data_root=data_root)

    anchor_elsewhere = tmp_path / "anchor-elsewhere"
    anchor_elsewhere.mkdir()

    class _ProbeToolWithProject:
        name = "t8-probe-project"
        mcp_description = "t8 probe with declared project root"

        def __call__(self, path: Path = Path("."), project: str | None = None) -> dict:
            return {"status": "ok", "path": str(path)}

    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    tool = _ProbeToolWithProject()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    captured = _spy(monkeypatch, tool_registry)
    wrapper = tool_registry.make_tool_wrapper(
        tool, executor, anchor_cwd=anchor_elsewhere
    )

    wrapper(path="src/bad.py", project=record.project_id)

    context = captured[-1]
    assert context.workspace_root == declared_root.resolve()
    assert _resolved_target(context) == target.resolve()


def test_t08_build_server_wiring_survives_cwd_change_custom_tool(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    from rush import mcp
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(project_with_marker)
    server = mcp.build_server()
    elsewhere = project_with_marker.parent
    monkeypatch.chdir(elsewhere)

    tools = getattr(server, "_tool_manager", None)
    assert tools is not None
    test_heal_fn = tools._tools["rush_test_heal"].fn

    captured = _spy(monkeypatch, tool_registry)
    result = test_heal_fn(target="src/bad.py")

    context = captured[-1]
    assert context.workspace_root == project_with_marker.resolve()
    # `target` is a typed argument (not a `path`/`files`/`paths` key), so the
    # engine receives it via `typed_args`, already rebased onto the fixed
    # anchor-derived root -- never the live post-chdir cwd.
    assert dict(context.typed_args)["target"] == str(
        project_with_marker / "src" / "bad.py"
    )
    parsed = json.loads(result)
    assert parsed == {
        "status": "skipped",
        "summary": "test-heal requires --allow-slow, --allow-artifact-write",
        "runs": 20,
        "seed": 0,
        "dry_run": True,
    }


def test_t08_cache_and_config_identity_match_for_relative_and_absolute_spellings(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    from rush.cli_support import rendering
    from rush.invocation import decide_cache

    target_file = project_with_marker / "src" / "bad.py"

    contexts: dict[str, InvocationContext] = {}
    for label, typed, chdir in (
        ("rel-root", "src/bad.py", project_with_marker),
        ("abs-root", str(target_file), project_with_marker),
        ("rel-nested", "bad.py", project_with_marker / "src"),
        ("abs-nested", str(target_file), project_with_marker / "src"),
    ):
        monkeypatch.setattr(rendering, "ALL_TOOLS", [_ProbeTool()])
        captured = _spy(monkeypatch, rendering)
        monkeypatch.chdir(chdir)
        with pytest.raises(SystemExit):
            rendering._run_tool("t8-probe", Path(typed), as_json=True)
        contexts[label] = captured[-1]

    digests = {label: ctx.effective_config_digest for label, ctx in contexts.items()}
    assert len(set(digests.values())) == 1

    keys = {label: decide_cache(ctx).cache_key for label, ctx in contexts.items()}
    assert len(set(keys.values())) == 1


def test_t08_suite_original_requested_targets_default_unavailable(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    from rush.workflows import suites

    monkeypatch.setattr(suites, "ALL_TOOLS", [_ProbeTool()])
    captured = _spy(monkeypatch, suites)
    monkeypatch.chdir(project_with_marker)

    suite = WorkflowSuite(
        name="t8-suite-default", description="test", tool_sequence=("t8-probe",)
    )
    run_workflow_suite(suite, Path("src/bad.py"), ExecutionPermissions())

    assert captured[-1].original_requested_targets == ()


def test_t08_suite_explicit_original_requested_targets_passthrough(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    from rush.workflows import suites

    monkeypatch.setattr(suites, "ALL_TOOLS", [_ProbeTool()])
    captured = _spy(monkeypatch, suites)
    monkeypatch.chdir(project_with_marker)

    suite = WorkflowSuite(
        name="t8-suite-explicit", description="test", tool_sequence=("t8-probe",)
    )
    run_workflow_suite(
        suite,
        Path("src/bad.py"),
        ExecutionPermissions(),
        original_requested_targets=("src/bad.py",),
    )

    assert captured[-1].original_requested_targets == ("src/bad.py",)


def _make_symlink_escape_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """proj/vendor -> otherrepo (which has its own .git, a real marker)."""
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "rush.toml").write_text("", encoding="utf-8")
    otherrepo = tmp_path / "otherrepo"
    (otherrepo / ".git").mkdir(parents=True)
    (otherrepo / "secret.py").write_text("OUTSIDE_SECRET\n", encoding="utf-8")
    (proj / "vendor").symlink_to(otherrepo, target_is_directory=True)
    return proj, otherrepo, proj / "vendor"


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
def test_t08_dir_symlink_escape_with_marker_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str
) -> None:
    """Finding 1: a symlinked directory whose target has its own marker
    (`.git`) must never become the logical root, and the symlinked
    component itself must still be rejected by physical containment."""
    proj, _otherrepo, _vendor = _make_symlink_escape_fixture(tmp_path)

    if transport == "cli":
        _run_cli_raises(monkeypatch, "vendor/secret.py", proj, ScopeWideningError)
        return

    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(proj)
    if transport == "mcp-standard":
        tool = _ProbeTool()
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
        wrapper = tool_registry.make_tool_wrapper(tool, executor)
        with pytest.raises(ScopeWideningError):
            wrapper(path="vendor/secret.py")
    else:
        executor = InvocationExecutor()
        executor.register("t8-custom-probe", tool_registry._make_handler(_custom_probe))
        wrapper = tool_registry.make_custom_wrapper(
            _custom_probe, "t8-custom-probe", executor
        )
        with pytest.raises(ScopeWideningError):
            wrapper(path="vendor/secret.py")


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom"])
def test_t08_dir_symlink_escape_without_marker_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str
) -> None:
    """Finding 1: same escape, but neither the symlinked directory's real
    target nor any real ancestor has a marker -- the climb must fall back
    to the nearest *non-symlink* real ancestor, never the symlinked `out`
    directory itself, and containment must still reject the symlink."""
    outdir = tmp_path / "outdir"
    outdir.mkdir()
    (outdir / "s.py").write_text("OUTDIR_SECRET\n", encoding="utf-8")
    noproj = tmp_path / "nomark"
    noproj.mkdir()
    (noproj / "out").symlink_to(outdir, target_is_directory=True)

    if transport == "cli":
        _run_cli_raises(monkeypatch, "out/s.py", noproj, ScopeWideningError)
        return

    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(noproj)
    if transport == "mcp-standard":
        tool = _ProbeTool()
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
        wrapper = tool_registry.make_tool_wrapper(tool, executor)
        with pytest.raises(ScopeWideningError):
            wrapper(path="out/s.py")
    else:
        executor = InvocationExecutor()
        executor.register("t8-custom-probe", tool_registry._make_handler(_custom_probe))
        wrapper = tool_registry.make_custom_wrapper(
            _custom_probe, "t8-custom-probe", executor
        )
        with pytest.raises(ScopeWideningError):
            wrapper(path="out/s.py")


def test_t08_custom_and_standard_wrapper_omitted_path_parity(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    """Finding 6: an omitted path means "." in both wrappers -- the target
    is the anchor directory, never widened to the logical root the anchor
    happens to sit under."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    anchor = project_with_marker / "src"

    standard_tool = _ProbeTool("t8-parity-standard")
    executor = InvocationExecutor()
    executor.register(standard_tool.name, standard_tool.__call__)
    captured = _spy(monkeypatch, tool_registry)
    standard_wrapper = tool_registry.make_tool_wrapper(
        standard_tool, executor, anchor_cwd=anchor
    )
    standard_wrapper()
    standard_context = captured[-1]

    custom_executor = InvocationExecutor()
    custom_executor.register(
        "t8-parity-custom", tool_registry._make_handler(_custom_probe)
    )
    custom_wrapper = tool_registry.make_custom_wrapper(
        _custom_probe, "t8-parity-custom", custom_executor, anchor_cwd=anchor
    )
    custom_wrapper()
    custom_context = captured[-1]

    assert _resolved_target(standard_context) == anchor.resolve()
    assert _resolved_target(custom_context) == anchor.resolve()


def test_t08_test_heal_schema_adds_project_never_project_root(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    """F + decision (4)(a): `rush_test_heal`'s public MCP schema is its
    ebd836c parameter set plus the optional declared-root `project` -- and
    never the internal `project_root` anchor."""
    from rush import mcp

    monkeypatch.chdir(project_with_marker)
    server = mcp.build_server()

    tools = asyncio.run(server.list_tools())
    test_heal_tool = next(t for t in tools if t.name == "rush_test_heal")
    props = test_heal_tool.inputSchema.get("properties", {})

    assert set(props) == {
        "target",
        "runs",
        "seed",
        "dry_run",
        "allow_slow",
        "allow_artifact_write",
        "allow_build",
        "project",
    }
    assert "project_root" not in props
    assert "project" not in test_heal_tool.inputSchema.get("required", [])


def test_t08_test_heal_root_is_anchor_derived_and_caller_cannot_override(
    monkeypatch: pytest.MonkeyPatch, project_with_marker: Path
) -> None:
    """Finding 5: `TestHealer`'s root is the fixed server-start anchor,
    wired internally -- a caller cannot name, see, or override it."""
    from rush import mcp
    from rush.tools import test_heal as test_heal_module

    monkeypatch.chdir(project_with_marker)
    server = mcp.build_server()
    monkeypatch.chdir(project_with_marker.parent)

    fn = server._tool_manager._tools["rush_test_heal"].fn

    captured_roots: list[Path] = []
    original_init = test_heal_module.TestHealer.__init__

    def spy_init(self, project_root: Path | None = None) -> None:
        captured_roots.append((project_root or Path.cwd()).resolve())
        original_init(self, project_root=project_root)

    monkeypatch.setattr(test_heal_module.TestHealer, "__init__", spy_init)

    fn(target="src/bad.py")

    assert captured_roots == [project_with_marker.resolve()]

    with pytest.raises(TypeError):
        fn(target="src/bad.py", project_root="/")


def test_t08_scan_candidate_original_targets_unavailable_without_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Finding 8: with no per-candidate override, `original_requested_targets`
    is explicitly unavailable (`()`) -- never the resolved registered root
    fabricated as a fake "original request"."""
    from rush.workflows import project_run

    root, _ = _registered_project(tmp_path)
    captured = _spy(monkeypatch, project_run)

    candidate = ScanCandidate(
        candidate_id="t8-probe",
        kind="tool",
        category="quality",
        disposition="applicable",
        reason="test",
    )
    outcome, result = _execute_candidate(
        candidate,
        root=root,
        permissions=ExecutionPermissions(),
        targets={},
        config=None,
        tools_by_name={"t8-probe": _ProbeTool()},
    )

    context = captured[-1]
    assert outcome == "executed"
    assert result["status"] == "ok"
    assert context.original_requested_targets == ()


def test_t08_injected_project_param_actually_redirects_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Finding 9: the wrapper-injected `project` argument (a tool that
    declares no such parameter itself) actually redirects resolution to the
    declared root, and is never forwarded to the tool's own call."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    declared_root = tmp_path / "declared-project"
    (declared_root / "src").mkdir(parents=True)
    target = declared_root / "src" / "bad.py"
    target.write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "rush-data"
    record = register_project(declared_root, data_root=data_root)

    anchor_elsewhere = tmp_path / "anchor-elsewhere"
    anchor_elsewhere.mkdir()

    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    received_kwargs: list[dict] = []

    class _RecordingProbe:
        name = "t8-inject-probe"
        mcp_description = "records what it actually received"

        def __call__(self, path: Path = Path(".")) -> dict:
            received_kwargs.append({"path": path})
            return {"status": "ok", "path": str(path)}

    tool = _RecordingProbe()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    captured = _spy(monkeypatch, tool_registry)
    wrapper = tool_registry.make_tool_wrapper(
        tool, executor, anchor_cwd=anchor_elsewhere
    )

    wrapper(path="src/bad.py", project=record.project_id)

    context = captured[-1]
    assert context.workspace_root == declared_root.resolve()
    assert _resolved_target(context) == target.resolve()
    assert "project" not in received_kwargs[0]


def test_t08_project_id_param_honored_as_declared_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Finding 9: a tool with its own pre-existing `project_id` parameter
    (continuity/memory-shaped) keeps that exact parameter -- no duplicate
    `project` -- and a supplied `project_id` is honored as the declared
    root for path resolution too."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    declared_root = tmp_path / "declared-project-id"
    (declared_root / "src").mkdir(parents=True)
    target = declared_root / "src" / "bad.py"
    target.write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "rush-data"
    record = register_project(declared_root, data_root=data_root)

    class _ProbeToolWithProjectId:
        name = "t8-probe-project-id"
        mcp_description = "t8 probe with project_id"

        def __call__(
            self, path: Path = Path("."), project_id: str | None = None
        ) -> dict:
            return {"status": "ok", "path": str(path)}

    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    anchor_elsewhere = tmp_path / "anchor-elsewhere"
    anchor_elsewhere.mkdir()
    tool = _ProbeToolWithProjectId()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    captured = _spy(monkeypatch, tool_registry)
    wrapper = tool_registry.make_tool_wrapper(
        tool, executor, anchor_cwd=anchor_elsewhere
    )

    wrapper(path="src/bad.py", project_id=record.project_id)

    context = captured[-1]
    assert context.workspace_root == declared_root.resolve()
    assert _resolved_target(context) == target.resolve()
    assert "project" not in inspect.signature(tool.__call__).parameters


def test_t08_invocation_start_cwd_recorded_for_cli_and_mcp(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    """T8: `invocation_start_cwd` is the real per-transport anchor, captured
    before any resolution -- CLI's real process cwd, MCP's fixed
    `anchor_cwd`."""
    context_cli = _run_cli(monkeypatch, "src/bad.py", project)
    assert context_cli.invocation_start_cwd == project.resolve()

    anchor = project / "src"
    context_mcp, _ = _run_mcp_standard(
        monkeypatch, "bad.py", project, anchor_cwd=anchor
    )
    assert context_mcp.invocation_start_cwd == anchor.resolve()


# --- FIX ROUND 3 (tests-first): root walk, declared roots, originals -------
#
# Binding contract for this block (Phase 70 T8, §3.2 + Execution decisions
# (1)-(4), `.orchestrator/reviews/codex-diag-T8-rootwalk.md`):
# - The logical root is found by a no-follow, ancestor-first walk from the
#   invocation anchor (CLI invocation cwd, MCP server-start anchor, or a
#   declared/registered root). A symlink met after a project is established
#   is INTERNAL and rejected (`[SYMLINK_DISALLOWED]`); a symlink met before
#   any project is established is a ROOT ENTRY only when its destination is a
#   registered or marked project root. Symlinks above the root are
#   transparent. `..` pops after a real dir and is rejected after a symlink.
# - A rejected target causes zero reads outside the root: no config read, no
#   target hash, no handler call. Proven with a process-wide `open` audit hook
#   plus recording tools, never inferred from the exception alone.

_OPEN_LOG: list[str] | None = None


def _open_audit_hook(event: str, args: tuple) -> None:
    log = _OPEN_LOG
    if log is None or event != "open":
        return
    target = args[0] if args else None
    if target is None or isinstance(target, int):
        return
    try:
        log.append(os.path.join(os.getcwd(), os.fsdecode(target)))
    except (TypeError, ValueError, OSError):
        return


sys.addaudithook(_open_audit_hook)


@contextlib.contextmanager
def _recording_opens():
    """Record every `open` (config reads, target hashing, handler reads)
    made while the block runs, as absolute path strings."""
    global _OPEN_LOG
    log: list[str] = []
    _OPEN_LOG = log
    try:
        yield log
    finally:
        _OPEN_LOG = None


def _reads_under(log: list[str], *dirs: Path) -> list[str]:
    real_dirs = [os.path.realpath(d) for d in dirs]
    hits = set()
    for raw in log:
        real = os.path.realpath(raw)
        if any(real == d or real.startswith(d + os.sep) for d in real_dirs):
            hits.add(real)
    return sorted(hits)


class _RecordingProbe:
    """ALL_TOOLS-shaped probe that records the target and cwd it actually
    ran with, and really reads the target (so an escape is observable)."""

    def __init__(self, name: str = "t8-probe") -> None:
        self.name = name
        self.mcp_description = "t8 recording probe"
        self.calls: list[tuple[str, str]] = []

    def __call__(self, path: Path = Path(".")) -> dict:
        p = Path(path)
        self.calls.append((str(p), os.getcwd()))
        if p.is_file():
            p.read_bytes()
        return {
            "tool": self.name,
            "engine": None,
            "engine_version": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "probe",
            "findings": [],
            "path": str(p),
        }


_CUSTOM_CALLS: list[tuple[str, str, str]] = []


def _record_custom(key: str, value: str) -> dict:
    _CUSTOM_CALLS.append((key, str(value), os.getcwd()))
    p = Path(value)
    if p.is_file():
        p.read_bytes()
    return {"status": "ok", key: str(value)}


def _custom_path_probe(path: str = ".") -> dict:
    return _record_custom("path", path)


def _custom_file_probe(file: str) -> dict:
    return _record_custom("file", file)


def _custom_target_probe(target: str) -> dict:
    return _record_custom("target", target)


_CUSTOM_PROBES = {
    "mcp-custom-path": ("path", _custom_path_probe),
    "mcp-custom-file": ("file", _custom_file_probe),
    "mcp-custom-target": ("target", _custom_target_probe),
}

_ALL_TRANSPORTS = [
    "cli",
    "mcp-standard",
    "mcp-custom-path",
    "mcp-custom-file",
    "mcp-custom-target",
    "suite",
]


def _isolate_registry(monkeypatch: pytest.MonkeyPatch, data_root: Path) -> None:
    monkeypatch.setattr("rush.workflows.projects.default_data_root", lambda: data_root)
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: data_root)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """One filesystem with every escape shape from the T8 root-walk review.

    real/                       (unmarked; `above` -> real is an above-root alias)
      proj/                     rush.toml (valid) -- a marked project
        src/bad.py              INROOT
        src/alias.py -> src/bad.py              (in-root file link)
        src/chain.py -> outdir/l2 -> src/bad.py (chain via outside)
        src/loop_a -> loop_b -> loop_a          (loop)
        src/dangling.py -> real/missing.py      (dangling)
        linkdir -> src                          (in-root dir link)
        vendor -> otherrepo                     (escape to a marked repo)
      otherrepo/  .git/, rush.toml (MALFORMED), secret.py,
                  pkg/.git/, pkg/rush.toml (MALFORMED), pkg/secret.py,
                  pkg/deep/secret.py
      outdir/     s.py, sub/s.py, l2 -> proj/src/bad.py  (no markers)
      nomark/     out -> outdir                          (no markers)
      realproj/   rush.toml, src/bad.py -- a marked project
      alias -> realproj                                  (root entry, marked)
      regproj/    src/bad.py -- registered, no markers
      regalias -> regproj                                (root entry, registered)
    """
    base = tmp_path / "real"
    proj = base / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "rush.toml").write_text("[tools.lint]\n", encoding="utf-8")
    (proj / "src" / "bad.py").write_text("INROOT = 1\n", encoding="utf-8")

    otherrepo = base / "otherrepo"
    (otherrepo / ".git").mkdir(parents=True)
    (otherrepo / "rush.toml").write_text("[[[ malformed\n", encoding="utf-8")
    (otherrepo / "secret.py").write_text("OUTSIDE_SECRET = 1\n", encoding="utf-8")
    (otherrepo / "pkg" / ".git").mkdir(parents=True)
    (otherrepo / "pkg" / "rush.toml").write_text("[[[ malformed\n", encoding="utf-8")
    (otherrepo / "pkg" / "secret.py").write_text(
        "NESTED_SECRET = 1\n", encoding="utf-8"
    )
    (otherrepo / "pkg" / "deep").mkdir()
    (otherrepo / "pkg" / "deep" / "secret.py").write_text(
        "DEEP_SECRET = 1\n", encoding="utf-8"
    )

    outdir = base / "outdir"
    (outdir / "sub").mkdir(parents=True)
    (outdir / "s.py").write_text("OUTDIR_SECRET = 1\n", encoding="utf-8")
    (outdir / "sub" / "s.py").write_text("DEEP_OUTDIR_SECRET = 1\n", encoding="utf-8")
    (outdir / "l2").symlink_to(proj / "src" / "bad.py")

    (proj / "vendor").symlink_to(otherrepo, target_is_directory=True)
    (proj / "linkdir").symlink_to(proj / "src", target_is_directory=True)
    (proj / "src" / "alias.py").symlink_to(proj / "src" / "bad.py")
    (proj / "src" / "chain.py").symlink_to(outdir / "l2")
    (proj / "src" / "loop_a").symlink_to(proj / "src" / "loop_b")
    (proj / "src" / "loop_b").symlink_to(proj / "src" / "loop_a")
    (proj / "src" / "dangling.py").symlink_to(base / "missing.py")

    nomark = base / "nomark"
    nomark.mkdir()
    (nomark / "out").symlink_to(outdir, target_is_directory=True)

    realproj = base / "realproj"
    (realproj / "src").mkdir(parents=True)
    (realproj / "rush.toml").write_text("", encoding="utf-8")
    (realproj / "src" / "bad.py").write_text("REAL = 1\n", encoding="utf-8")
    (base / "alias").symlink_to(realproj, target_is_directory=True)

    data_root = tmp_path / "rush-data"
    _isolate_registry(monkeypatch, data_root)
    regproj = base / "regproj"
    (regproj / "src").mkdir(parents=True)
    (regproj / "src" / "bad.py").write_text("REG = 1\n", encoding="utf-8")
    reg_record = register_project(regproj, data_root=data_root)
    (base / "regalias").symlink_to(regproj, target_is_directory=True)

    above = tmp_path / "above"
    above.symlink_to(base, target_is_directory=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    _CUSTOM_CALLS.clear()
    return SimpleNamespace(
        tmp=tmp_path,
        base=base,
        above=above,
        elsewhere=elsewhere,
        proj=proj,
        otherrepo=otherrepo,
        outdir=outdir,
        nomark=nomark,
        realproj=realproj,
        regproj=regproj,
        reg_record=reg_record,
        data_root=data_root,
    )


def _var_spelling(real: Path) -> Path:
    """The /var -> /private/var above-root alias spelling of a real tmp
    path. On a host whose tmp dir is not under /private/var, the fixture's
    own `above -> real` link is the same above-root alias shape."""
    text = str(real)
    if text.startswith("/private/var/") and Path("/var").is_symlink():
        return Path(text[len("/private") :])
    return real.parent / "above"


def _world_path(world: SimpleNamespace, spec: str) -> Path:
    if spec == "@elsewhere":
        return world.elsewhere
    if spec.startswith("@above/"):
        return world.above / spec[len("@above/") :]
    if spec.startswith("@base/"):
        return world.base / spec[len("@base/") :]
    if spec.startswith("@var/"):
        return _var_spelling(world.base) / spec[len("@var/") :]
    return world.base / spec


def _typed(world: SimpleNamespace, spec: str, cwd: Path, spelling: str) -> str:
    """`@...` specs are absolute already. A relative spec is typed verbatim
    (spelling "relative") or as the lexical, un-normalized join onto the
    invocation cwd (spelling "absolute") -- `..` and every link component
    survive into the absolute spelling unchanged."""
    if spec.startswith("@"):
        return str(_world_path(world, spec))
    if spelling == "absolute":
        return f"{cwd}{os.sep}{spec}"
    return spec


def _spelled(cases: list[tuple]) -> tuple[list[tuple], list[str]]:
    """Every relative case runs in both spellings (identical outcome
    required); an already-absolute case runs once."""
    params: list[tuple] = []
    ids: list[str] = []
    for case_id, cwd_spec, typed_spec, *rest in cases:
        spellings = (
            ["absolute"] if typed_spec.startswith("@") else ["relative", "absolute"]
        )
        for spelling in spellings:
            params.append((cwd_spec, typed_spec, spelling, *rest))
            ids.append(f"{case_id}-{spelling}")
    return params, ids


def _invoke(
    monkeypatch: pytest.MonkeyPatch, transport: str, typed: str, cwd: Path
) -> SimpleNamespace:
    """Run one request through one real transport boundary, capturing the
    exception (or suite error child), the resolved context, the probe's own
    received target/cwd, and every file opened during the call."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry
    from rush.workflows import suites

    monkeypatch.chdir(cwd)
    probe = _RecordingProbe()
    out = SimpleNamespace(
        exc=None,
        exit_code=None,
        context=None,
        result=None,
        calls=probe.calls,
        errors=[],
        opens=[],
    )

    if transport == "cli":
        from rush.cli_support import rendering

        monkeypatch.setattr(rendering, "ALL_TOOLS", [probe])
        captured = _spy(monkeypatch, rendering)
        with _recording_opens() as log:
            try:
                rendering._run_tool("t8-probe", Path(typed), as_json=True)
            except SystemExit as exit_:
                out.exit_code = exit_.code
            except Exception as exc:  # noqa: BLE001 -- the assertion subject
                out.exc = exc
        out.opens = log
    elif transport == "mcp-standard":
        captured = _spy(monkeypatch, tool_registry)
        executor = InvocationExecutor()
        executor.register(probe.name, probe.__call__)
        wrapper = tool_registry.make_tool_wrapper(probe, executor, anchor_cwd=cwd)
        with _recording_opens() as log:
            try:
                out.result = wrapper(path=typed)
            except Exception as exc:  # noqa: BLE001 -- the assertion subject
                out.exc = exc
        out.opens = log
    elif transport in _CUSTOM_PROBES:
        key, fn = _CUSTOM_PROBES[transport]
        captured = _spy(monkeypatch, tool_registry)
        executor = InvocationExecutor()
        executor.register("t8-custom", tool_registry._make_handler(fn))
        wrapper = tool_registry.make_custom_wrapper(
            fn, "t8-custom", executor, anchor_cwd=cwd
        )
        out.calls = _CUSTOM_CALLS
        with _recording_opens() as log:
            try:
                out.result = wrapper(**{key: typed})
            except Exception as exc:  # noqa: BLE001 -- the assertion subject
                out.exc = exc
        out.opens = log
    else:
        assert transport == "suite"
        monkeypatch.setattr(suites, "ALL_TOOLS", [probe])
        captured = _spy(monkeypatch, suites)
        original_error_result = suites.error_result

        def _error_spy(tool: str, engine: object, message: str) -> dict:
            out.errors.append((tool, message))
            return original_error_result(tool, engine, message)

        monkeypatch.setattr(suites, "error_result", _error_spy)
        suite = WorkflowSuite(
            name="t8-suite", description="t8", tool_sequence=("t8-probe",)
        )
        with _recording_opens() as log:
            out.result = run_workflow_suite(suite, Path(typed), ExecutionPermissions())
        out.opens = log

    out.context = captured[-1] if captured else None
    return out


def _refused_child(tool: str, summary: str) -> dict:
    """Phase 70 T16 §3 item 3: a suite child refused before it ran, as the
    full child entry; T17 S17.4 mirrors the disposition in its metadata."""
    return {
        "tool": tool,
        "status": "error",
        "summary": summary,
        "reason": None,
        "engines": [],
        "scope": {"coverage": "unavailable", "reason": None},
        "execution": {"disposition": "executed", "cause": None},
        "metadata": {"execution": {"disposition": "executed", "cause": None}},
    }


def _assert_symlink_rejected(out: SimpleNamespace, transport: str, world) -> None:
    outside = (world.otherrepo, world.outdir)
    if transport == "suite":
        assert out.result["status"] == "error"
        assert out.result["metadata"]["children"] == [
            _refused_child("t8-probe", f"error: {out.errors[0][1]}")
        ]
        assert out.result["metadata"]["executed_tools"] == ()
        assert len(out.errors) == 1
        assert out.errors[0][0] == "t8-probe"
        assert out.errors[0][1].startswith("[SYMLINK_DISALLOWED]"), out.errors[0][1]
    else:
        assert isinstance(out.exc, ScopeWideningError), repr(out.exc)
        assert str(out.exc).startswith("[SYMLINK_DISALLOWED]"), str(out.exc)
    assert out.calls == []
    assert _reads_under(out.opens, *outside) == []


_REJECT_CASES = [
    # (id, cwd spec, typed spec)
    ("vendor-file", "proj", "vendor/secret.py"),
    ("vendor-nested-marker", "proj", "vendor/pkg/secret.py"),
    ("vendor-deeper", "proj", "vendor/pkg/deep/secret.py"),
    ("vendor-dir", "proj", "vendor"),
    ("vendor-from-nested-cwd", "proj/src", "../vendor/secret.py"),
    ("out-file", "nomark", "out/s.py"),
    ("out-nested", "nomark", "out/sub/s.py"),
    ("inroot-file-link", "proj", "src/alias.py"),
    ("inroot-dir-link", "proj", "linkdir/bad.py"),
    ("chain-via-outside", "proj", "src/chain.py"),
    ("loop", "proj", "src/loop_a"),
    ("dangling", "proj", "src/dangling.py"),
    ("dotdot-after-inroot-link", "proj", "linkdir/../src/bad.py"),
    ("dotdot-after-outside-link", "proj", "vendor/../src/bad.py"),
    ("abs-inroot-file-link", "proj", "@base/proj/src/alias.py"),
    ("abs-above-alias-inroot-dir-link", "proj", "@above/proj/linkdir/bad.py"),
    ("abs-above-alias-vendor", "proj", "@above/proj/vendor/secret.py"),
    ("abs-var-spelling-vendor", "proj", "@var/proj/vendor/secret.py"),
    ("abs-outside-cwd-vendor", "@elsewhere", "@base/proj/vendor/secret.py"),
    ("abs-outside-cwd-vendor-nested", "@elsewhere", "@base/proj/vendor/pkg/secret.py"),
    ("abs-outside-cwd-var-vendor", "@elsewhere", "@var/proj/vendor/pkg/secret.py"),
]
_REJECT_PARAMS, _REJECT_IDS = _spelled(_REJECT_CASES)


@pytest.mark.parametrize("transport", _ALL_TRANSPORTS)
@pytest.mark.parametrize(
    ("cwd_spec", "typed_spec", "spelling"), _REJECT_PARAMS, ids=_REJECT_IDS
)
def test_t08_rootwalk_rejects_symlink_with_zero_outside_reads(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
    cwd_spec: str,
    typed_spec: str,
    spelling: str,
    transport: str,
) -> None:
    """A/B/D: every internal link, pre-project link to an unmarked
    destination, chain, loop, dangling link, `..` after a link, and
    absolute spelling of any of them is rejected with SYMLINK_DISALLOWED,
    with zero handler calls and zero reads under any outside directory --
    on the CLI, standard MCP, custom MCP (`path`, `file`, `target`), and
    suite boundaries alike."""
    cwd = _world_path(world, cwd_spec)
    out = _invoke(monkeypatch, transport, _typed(world, typed_spec, cwd, spelling), cwd)
    _assert_symlink_rejected(out, transport, world)


_ACCEPT_CASES = [
    # (id, cwd spec, typed spec, expected root attr, expected relative path)
    ("plain", "proj", "src/bad.py", "proj", "src/bad.py"),
    ("dotdot-after-real-dir-pops", "proj", "src/../src/bad.py", "proj", "src/bad.py"),
    ("root-entry-marked-file", "real", "alias/src/bad.py", "realproj", "src/bad.py"),
    ("root-entry-marked-dir", "real", "alias", "realproj", "."),
    ("root-entry-registered", "real", "regalias/src/bad.py", "regproj", "src/bad.py"),
    ("abs-above-root-alias", "proj", "@above/proj/src/bad.py", "proj", "src/bad.py"),
    ("cwd-via-above-root-alias", "@above/proj", "src/bad.py", "proj", "src/bad.py"),
    ("abs-var-spelling-marked", "proj", "@var/proj/src/bad.py", "proj", "src/bad.py"),
    ("abs-var-outside-cwd", "@elsewhere", "@var/proj/src/bad.py", "proj", "src/bad.py"),
    (
        "abs-outside-cwd-marked",
        "@elsewhere",
        "@base/proj/src/bad.py",
        "proj",
        "src/bad.py",
    ),
    (
        "abs-outside-cwd-alias",
        "@elsewhere",
        "@base/alias/src/bad.py",
        "realproj",
        "src/bad.py",
    ),
    ("abs-outside-cwd-alias-dir", "@elsewhere", "@base/alias", "realproj", "."),
]
_ACCEPT_PARAMS, _ACCEPT_IDS = _spelled(_ACCEPT_CASES)


@pytest.mark.parametrize("transport", _ALL_TRANSPORTS)
@pytest.mark.parametrize(
    ("cwd_spec", "typed_spec", "spelling", "root_attr", "rel"),
    _ACCEPT_PARAMS,
    ids=_ACCEPT_IDS,
)
def test_t08_rootwalk_selects_exact_logical_root(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
    cwd_spec: str,
    typed_spec: str,
    spelling: str,
    root_attr: str,
    rel: str,
    transport: str,
) -> None:
    """A/B/D/L: a marked or registered root entry reached through a link
    before any project is established becomes the logical root (its
    canonical destination); above-root aliases are transparent; `..` after a
    real directory pops. Exact root, exact relative target, exact engine
    target and engine cwd (no process-wide chdir), exact originals and
    invocation-start cwd per transport."""
    cwd = world.base if cwd_spec == "real" else _world_path(world, cwd_spec)
    typed = _typed(world, typed_spec, cwd, spelling)
    out = _invoke(monkeypatch, transport, typed, cwd)

    expected_root = getattr(world, root_attr).resolve()
    expected_target = expected_root / rel if rel != "." else expected_root
    assert out.exc is None, repr(out.exc)
    assert out.context is not None
    assert out.context.workspace_root == expected_root
    assert [t.relative_path for t in out.context.targets] == [Path(rel)]
    assert _reads_under(out.opens, world.otherrepo, world.outdir) == []

    if transport == "suite":
        assert out.result["status"] == "ok"
        assert out.errors == []
        assert out.context.original_requested_targets == ()
    else:
        assert out.context.original_requested_targets == (typed,)
        assert out.context.invocation_start_cwd == cwd.resolve()

    assert len(out.calls) == 1
    if transport in _CUSTOM_PROBES:
        key, received, engine_cwd = out.calls[0]
        assert key == _CUSTOM_PROBES[transport][0]
    else:
        received, engine_cwd = out.calls[0]
    assert received == str(expected_target)
    assert os.path.realpath(engine_cwd) == os.path.realpath(cwd)


@pytest.mark.parametrize("transport", ["cli", "mcp-standard", "mcp-custom-path"])
@pytest.mark.parametrize(
    ("typed", "malformed"),
    [
        ("vendor/secret.py", "otherrepo/rush.toml"),
        ("vendor/pkg/secret.py", "otherrepo/pkg/rush.toml"),
    ],
)
def test_t08_rejected_target_never_reads_outside_config(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
    typed: str,
    malformed: str,
    transport: str,
) -> None:
    """C: config is loaded only from the chosen logical root, after root
    selection. A malformed rush.toml outside the root is never opened and
    never surfaces as a RushConfigError / exit 2 -- the target is rejected
    as SYMLINK_DISALLOWED first."""
    from rush.config import RushConfigError

    out = _invoke(monkeypatch, transport, typed, world.proj)

    assert not isinstance(out.exc, RushConfigError), repr(out.exc)
    assert isinstance(out.exc, ScopeWideningError), repr(out.exc)
    assert str(out.exc).startswith("[SYMLINK_DISALLOWED]")
    assert _reads_under(out.opens, world.base / malformed) == []
    assert out.calls == []


def _declared_standard_wrapper(
    monkeypatch: pytest.MonkeyPatch, anchor: Path
) -> tuple[object, _RecordingProbe, list[InvocationContext]]:
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    probe = _RecordingProbe()
    executor = InvocationExecutor()
    executor.register(probe.name, probe.__call__)
    captured = _spy(monkeypatch, tool_registry)
    wrapper = tool_registry.make_tool_wrapper(probe, executor, anchor_cwd=anchor)
    return wrapper, probe, captured


def test_t08_registered_root_lexical_descendant_with_internal_link_is_scope_widening(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """E: a lexical descendant of the declared registered root that crosses a
    forbidden internal link reaches ScopeWideningError/SYMLINK_DISALLOWED --
    never AmbiguousRootError from resolving the whole target first."""
    record = register_project(world.proj, data_root=world.data_root)
    wrapper, probe, _ = _declared_standard_wrapper(monkeypatch, world.nomark)

    with _recording_opens() as log, pytest.raises(ScopeWideningError) as excinfo:
        wrapper(path="vendor/pkg/secret.py", project=record.project_id)

    assert not isinstance(excinfo.value, AmbiguousRootError)
    assert str(excinfo.value).startswith("[SYMLINK_DISALLOWED]")
    assert probe.calls == []
    assert _reads_under(log, world.otherrepo) == []


def test_t08_registered_root_unrelated_target_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """E: a genuinely unrelated absolute target under a declared root raises
    the named AmbiguousRootError, before any handler call."""
    record = register_project(world.proj, data_root=world.data_root)
    wrapper, probe, _ = _declared_standard_wrapper(monkeypatch, world.nomark)

    with pytest.raises(AmbiguousRootError):
        wrapper(path=str(world.realproj / "src" / "bad.py"), project=record.project_id)
    assert probe.calls == []


def test_t08_registered_root_above_root_alias_spelling_is_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """E: the same file spelled through an above-root alias (the
    /var -> /private/var shape) is not a false AmbiguousRootError; the root
    stays the registered one and the target is its exact descendant."""
    record = register_project(world.proj, data_root=world.data_root)
    wrapper, probe, captured = _declared_standard_wrapper(monkeypatch, world.nomark)
    typed = str(world.above / "proj" / "src" / "bad.py")

    wrapper(path=typed, project=record.project_id)

    context = captured[-1]
    assert context.workspace_root == world.proj.resolve()
    assert [t.relative_path for t in context.targets] == [Path("src/bad.py")]
    assert probe.calls[0][0] == str(world.proj.resolve() / "src" / "bad.py")


def test_t08_every_path_taking_tool_declares_exactly_one_root_arg() -> None:
    """F: iterate the real FastMCP tools/list. The set of tools publishing a
    declared-root argument is exactly the path-taking set (all 55 catalog
    tools, the rush_attest_generate alias, and the 11 custom tools whose
    handler takes path/file/target, rush_test_heal included); each publishes
    exactly one of `project` or its own existing `project_id`, optional.
    Phase 70 T17: 55 catalog tools with `rush_check` (80 tools, 67 path-taking)."""
    from rush import mcp
    from rush.tools import ALL_TOOLS

    server = mcp.build_server()
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert len(tools) == 81

    catalog = {f"rush_{t.name.replace('-', '_')}" for t in ALL_TOOLS}
    custom_path_taking = {
        "rush_ship_clean",
        "rush_token_outline",
        "rush_context_retrieve",
        "rush_hallu_guard",
        "rush_context_pack",
        "rush_blast_radius",
        "rush_test_heal",
        "rush_simplify",
        "rush_strictify",
        "rush_mesh_acquire_lock",
        "rush_mesh_release_lock",
    }
    path_taking = catalog | {"rush_attest_generate"} | custom_path_taking
    assert len(path_taking) == 68

    # T8 5.2 / T6: `rush_project` and `rush_scan` are not path-taking; since T6
    # their published `project` field is operation data (a project reference
    # for the operation), never a declared-root argument.
    operation_data_project = {"rush_project", "rush_scan"}
    assert operation_data_project <= set(tools)
    assert not (operation_data_project & path_taking)
    with_declared = {
        name
        for name, t in tools.items()
        if {"project", "project_id"} & set(t.inputSchema.get("properties", {}))
    } - operation_data_project
    assert with_declared == path_taking

    for name in sorted(path_taking):
        schema = tools[name].inputSchema
        declared = {"project", "project_id"} & set(schema.get("properties", {}))
        expected = (
            {"project_id"}
            if name in {"rush_continuity", "rush_memory"}
            else {"project"}
        )
        assert declared == expected, name
        assert not (declared & set(schema.get("required", []))), name


@pytest.mark.parametrize("project_value", ["myproj", "./myproj"])
def test_t08_relative_declared_project_resolves_against_server_start_anchor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_value: str
) -> None:
    """F: a relative `project` path resolves against the server-start
    anchor captured in build_server, never the live cwd after a chdir
    (both directories hold a registered `myproj`)."""
    from rush import mcp
    from rush.mcp_support import tool_registry

    data_root = tmp_path / "rush-data"
    _isolate_registry(monkeypatch, data_root)
    anchor = tmp_path / "anchor"
    elsewhere = tmp_path / "elsewhere"
    for parent in (anchor, elsewhere):
        (parent / "myproj" / "src").mkdir(parents=True)
        (parent / "myproj" / "src" / "bad.py").write_text("x = 1\n", encoding="utf-8")
        register_project(parent / "myproj", data_root=data_root)

    monkeypatch.chdir(anchor)
    server = mcp.build_server()
    monkeypatch.chdir(elsewhere)
    captured = _spy(monkeypatch, tool_registry)

    server._tool_manager._tools["rush_token_outline"].fn(
        path="src/bad.py", project=project_value
    )

    context = captured[-1]
    assert context.workspace_root == (anchor / "myproj").resolve()
    assert [t.relative_path for t in context.targets] == [Path("src/bad.py")]
    assert context.invocation_start_cwd == anchor.resolve()


def _g_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Registry where every G spelling is discriminating: `myproj` and
    `team/app` exist as directories under BOTH the server-start anchor and
    the later live cwd, and `team/app` is also a real registered ID."""
    data_root = tmp_path / "rush-data"
    _isolate_registry(monkeypatch, data_root)
    anchor = tmp_path / "anchor"
    elsewhere = tmp_path / "elsewhere"
    ids: dict[str, str] = {}
    for label, parent in (("anchor", anchor), ("elsewhere", elsewhere)):
        (parent / "myproj").mkdir(parents=True)
        (parent / "team" / "app").mkdir(parents=True)
        ids[f"{label}/myproj"] = register_project(
            parent / "myproj", data_root=data_root
        ).project_id
        ids[f"{label}/team/app"] = register_project(
            parent / "team" / "app", data_root=data_root
        ).project_id
    realproj = tmp_path / "realproj"
    realproj.mkdir()
    (realproj / "rush.toml").write_text("", encoding="utf-8")
    ids["realproj"] = register_project(realproj, data_root=data_root).project_id
    (anchor / "alias").symlink_to(realproj, target_is_directory=True)

    # A registered project whose ID is literally "team/app".
    id_root = tmp_path / "id-owned"
    id_root.mkdir()
    temp_id = register_project(id_root, data_root=data_root).project_id
    registry_file = next(p for p in data_root.iterdir() if p.suffix == ".json")
    registry = json.loads(registry_file.read_text(encoding="utf-8"))
    registry["projects"]["team/app"] = registry["projects"].pop(temp_id)
    registry_file.write_text(json.dumps(registry), encoding="utf-8")
    ids["id:team/app"] = "team/app"

    return SimpleNamespace(
        anchor=anchor, elsewhere=elsewhere, ids=ids, data_root=data_root
    )


@pytest.mark.parametrize("tool_name", ["rush_scan", "rush_project"])
@pytest.mark.parametrize(
    ("value", "expected_key"),
    [
        ("myproj", "anchor/myproj"),
        ("./myproj", "anchor/myproj"),
        (".", None),
        ("team/app", "id:team/app"),
        ("alias", "realproj"),
    ],
    ids=["bare-path", "dot-slash-path", "dot", "id-with-slash", "alias-root-entry"],
)
def test_t08_scan_and_project_value_is_id_first_then_anchored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tool_name: str,
    value: str,
    expected_key: str | None,
) -> None:
    """G: rush_scan/rush_project look `project` up as a registered ID first,
    then anchor it to the server-start cwd (never the live cwd after a
    chdir) when it is not an ID."""
    from rush import mcp

    g = _g_world(tmp_path, monkeypatch)
    if expected_key is None:
        g.ids["anchor"] = register_project(g.anchor, data_root=g.data_root).project_id
        register_project(g.elsewhere, data_root=g.data_root)
        expected_key = "anchor"

    monkeypatch.chdir(g.anchor)
    server = mcp.build_server()
    monkeypatch.chdir(g.elsewhere)

    operation = "plan" if tool_name == "rush_scan" else "show"
    result = server._tool_manager._tools[tool_name].fn(
        request={"schema_version": 1, "operation": operation, "project": value}
    )

    assert result["status"] == "ok", result
    assert result["raw"]["data"]["project_id"] == g.ids[expected_key]


def _project_tool_call(server: object, request: dict) -> dict:
    return server._tool_manager._tools["rush_project"].fn(
        request={
            "schema_version": 1,
            "allow_cache_write": True,
            "allow_artifact_write": True,
            **request,
        }
    )


def test_t08_rush_project_add_path_anchored_to_server_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """G: rush_project add `path` resolves against the server-start anchor."""
    from rush import mcp
    from rush.workflows.projects import ProjectNotFoundError

    g = _g_world(tmp_path, monkeypatch)
    for parent in (g.anchor, g.elsewhere):
        (parent / "newproj").mkdir()

    monkeypatch.chdir(g.anchor)
    server = mcp.build_server()
    monkeypatch.chdir(g.elsewhere)

    result = _project_tool_call(server, {"operation": "add", "path": "newproj"})

    assert result["status"] == "ok", result
    assert result["raw"]["data"]["root"] == str((g.anchor / "newproj").resolve())
    with pytest.raises(ProjectNotFoundError):
        resolve_project(g.elsewhere / "newproj", data_root=g.data_root)


def test_t08_rush_project_relink_path_anchored_to_server_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """G: rush_project relink `path` resolves against the server-start anchor."""
    from rush import mcp

    g = _g_world(tmp_path, monkeypatch)
    (g.anchor / "old").mkdir()
    record = register_project(g.anchor / "old", data_root=g.data_root)
    for parent in (g.anchor, g.elsewhere):
        (parent / "moved").mkdir()

    monkeypatch.chdir(g.anchor)
    server = mcp.build_server()
    monkeypatch.chdir(g.elsewhere)

    result = _project_tool_call(
        server,
        {
            "operation": "relink",
            "project": record.project_id,
            "path": "moved",
            "expected_revision": record.revision,
        },
    )

    assert result["status"] == "ok", result
    assert resolve_project(record.project_id, data_root=g.data_root)["root"] == str(
        (g.anchor / "moved").resolve()
    )


def test_t08_rush_project_create_parent_anchored_to_server_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """G: rush_project create `parent` resolves against the server-start anchor."""
    from rush import mcp

    g = _g_world(tmp_path, monkeypatch)
    for parent in (g.anchor, g.elsewhere):
        (parent / "parents").mkdir()

    monkeypatch.chdir(g.anchor)
    server = mcp.build_server()
    monkeypatch.chdir(g.elsewhere)

    result = _project_tool_call(
        server, {"operation": "create", "parent": "parents", "name": "made"}
    )

    assert result["status"] == "ok", result
    assert result["raw"]["data"]["root"] == str(
        (g.anchor / "parents" / "made").resolve()
    )
    assert not (g.elsewhere / "parents" / "made").exists()


def _probe_check_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_RecordingProbe, list[InvocationContext]]:
    """Replace CHECK_SUITE with a one-probe suite at the real module seam the
    CLI/TUI/dashboard call sites import from."""
    from rush.workflows import suites

    probe = _RecordingProbe()
    monkeypatch.setattr(suites, "ALL_TOOLS", [probe])
    monkeypatch.setattr(
        suites,
        "CHECK_SUITE",
        WorkflowSuite(name="check", description="t8", tool_sequence=("t8-probe",)),
    )
    return probe, _spy(monkeypatch, suites)


def test_t08_check_cli_alias_root_entry_runs_on_canonical_root(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """B/H/L: `rush check alias` (alias -> a marked root) works: logical root
    is the canonical destination, the engine gets it as its target with the
    invocation cwd unchanged, originals are the user's own input, and the
    invocation-start cwd is recorded."""
    from click.testing import CliRunner

    from rush.cli import cli

    probe, captured = _probe_check_suite(monkeypatch)
    monkeypatch.chdir(world.base)

    result = CliRunner().invoke(cli, ["check", "alias", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "ok"
    context = captured[-1]
    assert context.workspace_root == world.realproj.resolve()
    assert [t.relative_path for t in context.targets] == [Path(".")]
    assert context.original_requested_targets == ("alias",)
    assert context.invocation_start_cwd == world.base.resolve()
    assert probe.calls == [(str(world.realproj.resolve()), str(world.base.resolve()))]


def test_t08_check_cli_rejects_symlink_escape_via_cli_runner(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """B (real `rush check` call site): a symlink escape is one error child,
    exit 2, zero handler calls, zero outside reads, and no secret in output."""
    from click.testing import CliRunner

    from rush.cli import cli

    probe, _ = _probe_check_suite(monkeypatch)
    monkeypatch.chdir(world.proj)

    with _recording_opens() as log:
        result = CliRunner().invoke(cli, ["check", "vendor/secret.py", "--json"])

    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    (child,) = payload["metadata"]["children"]
    assert child["summary"].startswith("error: [SYMLINK_DISALLOWED]"), child
    assert payload["metadata"]["children"] == [
        _refused_child("t8-probe", child["summary"])
    ]
    assert payload["metadata"]["executed_tools"] == []
    assert "OUTSIDE_SECRET" not in result.output
    assert probe.calls == []
    assert _reads_under(log, world.otherrepo) == []


def test_t08_ui_json_without_paths_records_originals_unavailable(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """H: `rush ui --json` with no paths records original_requested_targets
    as unavailable (the model's empty tuple), never a fabricated cwd string."""
    from click.testing import CliRunner

    from rush.cli import cli

    probe, captured = _probe_check_suite(monkeypatch)
    monkeypatch.chdir(world.proj)

    result = CliRunner().invoke(cli, ["ui", "--json"])

    assert result.exit_code == 0, result.output
    context = captured[-1]
    assert context.original_requested_targets == ()
    assert context.workspace_root == world.proj.resolve()
    assert probe.calls == [(str(world.proj.resolve()), str(world.proj.resolve()))]


def test_t08_ui_json_alias_root_entry_runs_on_canonical_root(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """B/H: `rush ui --json alias` works on the canonical marked root and
    passes the user's own original input."""
    from click.testing import CliRunner

    from rush.cli import cli

    probe, captured = _probe_check_suite(monkeypatch)
    monkeypatch.chdir(world.base)

    result = CliRunner().invoke(cli, ["ui", "--json", "alias"])

    assert result.exit_code == 0, result.output
    snapshots = json.loads(result.stdout)
    assert [s["result"]["status"] for s in snapshots] == ["ok"]
    context = captured[-1]
    assert context.workspace_root == world.realproj.resolve()
    assert [t.relative_path for t in context.targets] == [Path(".")]
    assert context.original_requested_targets == ("alias",)
    assert probe.calls == [(str(world.realproj.resolve()), str(world.base.resolve()))]


def test_t08_dashboard_alias_suite_runs_on_registered_root(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """B/H + decision (4)(d): `rush dashboard alias` runs its initial suite
    on the root it just registered (`record.root`, the canonical realproj),
    passing the user's own original input -- never SYMLINK_DISALLOWED."""
    import threading

    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush.cli import cli
    from rush.dashboard import server as dashboard_server

    probe, captured = _probe_check_suite(monkeypatch)
    published: list[dict] = []
    done = threading.Event()

    class _FakeServer:
        def serve_forever(self) -> None:
            done.wait(timeout=20)

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    fake_ctx = SimpleNamespace(
        server_id="t8-server",
        owner_instance_id="t8-owner",
        mutations=SimpleNamespace(allocate_scan_generation=lambda project_id: 1),
    )

    def _publish(ctx, project_id, root, aggregate, **kwargs) -> None:
        published.append({"project_id": project_id, "aggregate": aggregate})
        done.set()

    monkeypatch.setattr(
        dashboard_server,
        "create_dashboard_server",
        lambda snapshots, port=0: (_FakeServer(), fake_ctx, "tok"),
    )
    monkeypatch.setattr(
        dashboard_server, "bootstrap_launch_url", lambda ctx, token: "http://t8"
    )
    monkeypatch.setattr(
        dashboard_server,
        "capture_initial_scan_provenance",
        lambda root, project_id: ("run-t8", "attempt-t8"),
    )
    monkeypatch.setattr(dashboard_server, "publish_check_suite_scan", _publish)
    monkeypatch.setattr(
        cli_module,
        "_write_dashboard_descriptor",
        lambda ctx: world.tmp / "descriptor.json",
    )
    monkeypatch.setattr(cli_module, "_remove_dashboard_descriptor", lambda path: None)
    monkeypatch.chdir(world.base)

    result = CliRunner().invoke(cli, ["dashboard", "alias", "--no-open", "--json"])

    assert result.exit_code == 0, result.output
    assert done.is_set()
    record = resolve_project(world.realproj, data_root=world.data_root)
    assert [p["project_id"] for p in published] == [record["project_id"]]
    assert published[0]["aggregate"]["status"] == "ok"
    context = captured[-1]
    assert context.workspace_root == Path(record["root"])
    assert [t.relative_path for t in context.targets] == [Path(".")]
    assert context.original_requested_targets == ("alias",)
    assert probe.calls[0][0] == record["root"]


def test_t08_tui_seed_and_state_gain_optional_lexical_and_original_fields() -> None:
    """I: ProjectSeed/ProjectState keep `root` and gain two optional fields,
    default None: `lexical_path` and `original_input`."""
    from rush.tui import ProjectSeed, ProjectState

    seed = ProjectSeed(name="p", root=Path("/r"))
    state = ProjectState(name="p", root=Path("/r"))
    for obj in (seed, state):
        assert obj.root == Path("/r")
        assert obj.lexical_path is None
        assert obj.original_input is None


def test_t08_ui_interactive_seeds_keep_resolved_root_and_carry_lexical_original(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """I: interactive `rush ui alias` seeds keep `root` resolved and carry
    the lexical absolute path and the user's original input; with no paths
    the original is None (never a fabricated cwd string)."""
    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush import tui
    from rush.cli import cli

    seen: list[list] = []
    monkeypatch.setattr(cli_module, "_stdout_is_tty", lambda: True)
    monkeypatch.setattr(
        tui, "run_interactive_tui", lambda seeds, **kwargs: seen.append(list(seeds))
    )
    monkeypatch.chdir(world.base)

    assert CliRunner().invoke(cli, ["ui", "alias"]).exit_code == 0
    assert CliRunner().invoke(cli, ["ui"]).exit_code == 0

    [aliased], [bare] = seen
    assert aliased.root == world.realproj.resolve()
    assert aliased.lexical_path == world.base / "alias"
    assert aliased.original_input == "alias"
    assert bare.root == Path.cwd()
    assert bare.original_input is None


def test_t08_tui_state_copy_and_initial_check_pass_lexical_and_original(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """I: run_interactive_tui copies both fields seed -> state, and the
    initial check passes both to actions.run_check_suite alongside root."""
    from rich.console import Console

    from rush.tui import ProjectSeed, ScanActions, run_interactive_tui

    calls: list[tuple[Path, dict]] = []

    def _fake_check(root: Path, **kwargs: object) -> dict:
        calls.append((root, dict(kwargs)))
        return {"tool": "suite", "status": "ok", "findings": [], "summary": "done"}

    class _QuitReader:
        def read_key(self, timeout: float) -> str | None:
            return "q"

        def get_size(self) -> tuple[int, int]:
            return (80, 24)

    actions = ScanActions(
        plan_scan=lambda *a, **k: None,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=lambda *a, **k: {},
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        run_check_suite=_fake_check,
        dashboard_owner=lambda root: None,
    )
    seed = ProjectSeed(
        name="alias",
        root=world.realproj.resolve(),
        lexical_path=world.base / "alias",
        original_input="alias",
    )

    state = run_interactive_tui(
        [seed],
        console=Console(file=io.StringIO()),
        key_reader=_QuitReader(),
        actions=actions,
        max_ticks=5,
        use_live=False,
    )
    project = state.projects[0]
    project.scan_thread.join(timeout=10)

    assert project.root == world.realproj.resolve()
    assert project.lexical_path == world.base / "alias"
    assert project.original_input == "alias"
    assert len(calls) == 1
    root, kwargs = calls[0]
    assert root == world.realproj.resolve()
    assert kwargs["lexical_path"] == world.base / "alias"
    assert kwargs["original_input"] == "alias"


@pytest.mark.parametrize("with_lexical", [True, False])
def test_t08_default_run_check_suite_uses_lexical_path_when_set(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace, with_lexical: bool
) -> None:
    """I: default_scan_actions' _run_check_suite runs the suite on the
    lexical path when set (else `root`), with `(original,)` or None as
    original_requested_targets."""
    from rush.tui import default_scan_actions
    from rush.workflows import suites

    seen: list[dict] = []

    def _fake_suite(**kwargs: object) -> dict:
        seen.append(kwargs)
        return {"tool": "check", "status": "ok", "findings": [], "summary": "ok"}

    monkeypatch.setattr(suites, "run_workflow_suite", _fake_suite)
    actions = default_scan_actions(permissions=ExecutionPermissions())
    extra = (
        {"lexical_path": world.base / "alias", "original_input": "alias"}
        if with_lexical
        else {}
    )

    actions.run_check_suite(
        world.realproj.resolve(), owner_instance_id="o", run_id="r", **extra
    )

    assert len(seen) == 1
    if with_lexical:
        assert seen[0]["path"] == world.base / "alias"
        assert seen[0]["original_requested_targets"] == ("alias",)
    else:
        assert seen[0]["path"] == world.realproj.resolve()
        assert seen[0].get("original_requested_targets") is None
    assert seen[0]["owner_instance_id"] == "o"
    assert seen[0]["run_id"] == "r"


def test_t08_invocation_start_cwd_recorded_for_custom_mcp(
    monkeypatch: pytest.MonkeyPatch, project: Path
) -> None:
    """L: the custom MCP wrapper records its fixed anchor as
    invocation_start_cwd, not the live cwd."""
    anchor = project / "src"
    context, _ = _run_mcp_custom(monkeypatch, "bad.py", project, anchor_cwd=anchor)
    assert context.invocation_start_cwd == anchor.resolve()
    assert _resolved_target(context) == (anchor / "bad.py").resolve()


def _root_entry_ui_seeds(
    monkeypatch: pytest.MonkeyPatch, typed: str
) -> tuple[object, list[list]]:
    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush import tui
    from rush.cli import cli

    seen: list[list] = []
    monkeypatch.setattr(cli_module, "_stdout_is_tty", lambda: True)
    monkeypatch.setattr(
        tui, "run_interactive_tui", lambda seeds, **kwargs: seen.append(list(seeds))
    )
    return CliRunner().invoke(cli, ["ui", typed]), seen


def test_t08_root_entry_dispatch_tui_scan_routes_use_registered_root(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """(4)(c)/(5.1) case (ii): `rush ui alias` yields one seed whose root is the
    canonical project, and the TUI plan_scan/rescan_project_run routes built
    from that seed dispatch exactly that root -- the registered root
    `resolve_project` returns, never a symlink-followed spelling."""
    from rush import tui

    register_project(world.realproj, data_root=world.data_root)
    monkeypatch.chdir(world.base)
    result, seen = _root_entry_ui_seeds(monkeypatch, "alias")

    assert result.exit_code == 0, result.output
    [[seed]] = seen
    canonical = world.realproj.resolve()
    assert seed.root == canonical

    planned: list[Path] = []
    rescanned: list[Path] = []

    def _plan(root: Path, **kwargs: object) -> SimpleNamespace:
        planned.append(root)
        return SimpleNamespace(plan_id="t8-plan", candidates=[])

    def _rescan(root: Path, *args: object, **kwargs: object) -> dict:
        rescanned.append(root)
        return {}

    actions = tui.ScanActions(
        plan_scan=_plan,
        execute_scan=lambda *a, **k: None,
        cancel_scan_run=lambda *a, **k: {},
        rescan_project_run=_rescan,
        build_handoff=lambda *a, **k: None,
        dispatch_handoff=lambda *a, **k: None,
        load_scan_events=lambda *a, **k: {"events": [], "run_state": None},
        list_agents=list,
        dashboard_owner=lambda root: None,
    )
    project = tui.ProjectState(
        name=seed.name,
        root=seed.root,
        lexical_path=seed.lexical_path,
        original_input=seed.original_input,
    )

    tui._start_scan_thread(project, actions)
    if project.scan_thread is not None:
        project.scan_thread.join(timeout=10)
    tui._start_rescan_thread(project, actions)
    if project.scan_thread is not None:
        project.scan_thread.join(timeout=10)

    assert planned == [canonical]
    assert rescanned == [canonical]
    record = resolve_project(canonical, data_root=world.data_root)
    assert Path(record["root"]) == canonical


@pytest.mark.parametrize("typed", ["proj/vendor", "nomark/out"])
def test_t08_root_entry_dispatch_rejects_internal_and_unmarked_links(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace, typed: str
) -> None:
    """(5.1) cases (iv)/(v): `rush dashboard`, `rush ui` (interactive and
    --json), and `rush check` on an internal link (`proj/vendor`) or a
    pre-project link to an unmarked directory (`nomark/out`) are rejected
    with SYMLINK_DISALLOWED: no register_project call, no seed, no server,
    no engine run."""
    from click.testing import CliRunner

    from rush.cli import cli
    from rush.dashboard import server as dashboard_server
    from rush.workflows import projects

    probe, _ = _probe_check_suite(monkeypatch)
    registered: list[object] = []
    servers: list[object] = []
    monkeypatch.setattr(
        projects, "register_project", lambda *a, **k: registered.append(a)
    )
    monkeypatch.setattr(
        dashboard_server, "create_dashboard_server", lambda *a, **k: servers.append(a)
    )
    monkeypatch.chdir(world.base)

    dashboard = CliRunner().invoke(cli, ["dashboard", typed, "--no-open", "--json"])
    assert dashboard.exit_code == 2, dashboard.output
    assert "[SYMLINK_DISALLOWED]" in dashboard.output
    assert registered == []
    assert servers == []

    ui_json = CliRunner().invoke(cli, ["ui", "--json", typed])
    assert ui_json.exit_code == 2, ui_json.output
    assert "[SYMLINK_DISALLOWED]" in ui_json.output

    ui_result, seen = _root_entry_ui_seeds(monkeypatch, typed)
    assert ui_result.exit_code == 2, ui_result.output
    assert seen == []

    check = CliRunner().invoke(cli, ["check", typed, "--json"])
    assert check.exit_code == 2, check.output
    assert json.loads(check.stdout)["status"] == "error"
    assert probe.calls == []


def _fake_watcher(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Replace the blocking FileWatcher with one that fires a single change."""
    from rush import watcher

    roots: list[Path] = []

    class _OneShotWatcher:
        def __init__(self, root: Path, debounce_ms: int, on_change) -> None:
            roots.append(root)
            self._on_change = on_change

        def watch_blocking(self) -> None:
            self._on_change([roots[-1]])

    monkeypatch.setattr(watcher, "FileWatcher", _OneShotWatcher)
    return roots


def test_t08_watch_tool_alias_runs_on_canonical_root(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    """`rush watch --tool <t> alias` walks once from the invocation cwd and
    runs the tool on the canonical marked root with the user's original
    input; the watcher itself watches that canonical path."""
    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush.cli import cli
    from rush.cli_support import rendering

    probe = _RecordingProbe()
    monkeypatch.setattr(cli_module, "ALL_TOOLS", [probe])
    roots = _fake_watcher(monkeypatch)
    captured = _spy(monkeypatch, rendering)
    monkeypatch.chdir(world.base)

    result = CliRunner().invoke(cli, ["watch", "--tool", "t8-probe", "alias"])

    assert result.exit_code == 0, result.output
    canonical = world.realproj.resolve()
    assert roots == [canonical]
    context = captured[-1]
    assert context.workspace_root == canonical
    assert [t.relative_path for t in context.targets] == [Path(".")]
    assert context.original_requested_targets == ("alias",)
    assert context.invocation_start_cwd == world.base.resolve()
    assert probe.calls == [(str(canonical), str(world.base.resolve()))]


@pytest.mark.parametrize("typed", ["vendor", "vendor/secret.py"])
def test_t08_watch_tool_rejects_symlink_escape(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace, typed: str
) -> None:
    """`rush watch --tool <t> <internal link>` is rejected before anything is
    watched or run: exit 2, SYMLINK_DISALLOWED, zero handler calls, zero
    reads outside the project."""
    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush.cli import cli

    probe = _RecordingProbe()
    monkeypatch.setattr(cli_module, "ALL_TOOLS", [probe])
    roots = _fake_watcher(monkeypatch)
    monkeypatch.chdir(world.proj)

    with _recording_opens() as log:
        result = CliRunner().invoke(cli, ["watch", "--tool", "t8-probe", typed])

    assert result.exit_code == 2, result.output
    assert "[SYMLINK_DISALLOWED]" in result.output
    assert roots == []
    assert probe.calls == []
    assert _reads_under(log, world.otherrepo) == []


def test_t08_test_heal_declared_project_sets_healer_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(5.3): `rush_test_heal` with `project` set to a registered root that
    differs from both the server-start cwd and the live cwd constructs its
    TestHealer on that declared root, and resolves `target` under it."""
    from rush import mcp
    from rush.mcp_support import tool_registry
    from rush.tools import test_heal as test_heal_module

    _isolate_registry(monkeypatch, tmp_path / "rush-data")
    declared = tmp_path / "declared"
    (declared / "tests").mkdir(parents=True)
    (declared / "tests" / "test_x.py").write_text("X = 1\n", encoding="utf-8")
    record = register_project(declared, data_root=tmp_path / "rush-data")
    start = tmp_path / "start"
    start.mkdir()
    later = tmp_path / "later"
    later.mkdir()

    monkeypatch.chdir(start)
    server = mcp.build_server()
    monkeypatch.chdir(later)

    roots: list[Path | None] = []
    original_init = test_heal_module.TestHealer.__init__

    def spy_init(self, project_root: Path | None = None) -> None:
        roots.append(project_root)
        original_init(self, project_root=project_root)

    monkeypatch.setattr(test_heal_module.TestHealer, "__init__", spy_init)
    captured = _spy(monkeypatch, tool_registry)

    server._tool_manager._tools["rush_test_heal"].fn(
        target="tests/test_x.py", project=record.project_id
    )

    assert roots == [declared.resolve()]
    context = captured[-1]
    assert context.workspace_root == declared.resolve()
    assert dict(context.typed_args)["target"] == str(
        declared.resolve() / "tests" / "test_x.py"
    )
    assert "project" not in dict(context.typed_args)


# --- T8 design brief (.orchestrator/design/T8.md) §3.7, §3.8, §5, §6 ------
#
# `w` is the brief's §6 world. Every walk in this block reads an isolated,
# empty-by-default registry (never the developer's real one).


def _w_symlink(link: Path, target: Path | str, *, directory: bool = True) -> None:
    link.symlink_to(target, target_is_directory=directory)


@pytest.fixture
def w(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    base = tmp_path.resolve()
    data_root = base / "data"
    _isolate_registry(monkeypatch, data_root)
    root = base / "w"

    proj = root / "proj"
    for d in ("src", "sub/deep", "nested"):
        (proj / d).mkdir(parents=True)
    (proj / "rush.toml").write_text("", encoding="utf-8")
    (proj / "src" / "bad.py").write_text("BAD = 1\n", encoding="utf-8")
    (proj / "src" / "has space.py").write_text("S = 1\n", encoding="utf-8")
    (proj / "sub" / "deep" / "f.py").write_text("F = 1\n", encoding="utf-8")
    (proj / "nested" / "rush.toml").write_text("", encoding="utf-8")
    (proj / "nested" / "n.py").write_text("N = 1\n", encoding="utf-8")

    otherrepo = root / "otherrepo"
    (otherrepo / "pkg" / ".git").mkdir(parents=True)
    (otherrepo / "rush.toml").write_text("", encoding="utf-8")
    (otherrepo / "secret.py").write_text("OUTSIDE_SECRET = 1\n", encoding="utf-8")
    (otherrepo / "pkg" / "secret.py").write_text("PKG_SECRET = 1\n", encoding="utf-8")

    _w_symlink(proj / "vendor", "../otherrepo")
    _w_symlink(proj / "vabs", otherrepo)
    _w_symlink(proj / "vchain", "vendor")
    _w_symlink(proj / "self", ".")
    _w_symlink(proj / "loop1", "loop2")
    _w_symlink(proj / "loop2", "loop1")
    _w_symlink(proj / "src" / "link.py", "../../otherrepo/secret.py", directory=False)
    _w_symlink(proj / "src" / "alias.py", "bad.py", directory=False)
    _w_symlink(proj / "srcdir_alias", "src")

    unmarked = root / "unmarked"
    (unmarked / "sub").mkdir(parents=True)
    (unmarked / "s.py").write_text("S = 1\n", encoding="utf-8")
    (unmarked / "sub" / "s.py").write_text("S = 1\n", encoding="utf-8")
    nomark = root / "nomark"
    (nomark / "real").mkdir(parents=True)
    (nomark / "real" / "f.py").write_text("F = 1\n", encoding="utf-8")
    _w_symlink(nomark / "out", "../unmarked")
    _w_symlink(nomark / "outabs", unmarked)
    _w_symlink(nomark / "filelink", "../unmarked/s.py", directory=False)

    _w_symlink(root / "alias", "proj")
    _w_symlink(root / "chain2", "proj")
    _w_symlink(root / "chain1", "chain2")
    (root / "plain").mkdir()
    (root / "plain" / "f.py").write_text("F = 1\n", encoding="utf-8")
    _w_symlink(root / "plainalias", "plain")
    regplain = root / "regplain"
    regplain.mkdir()
    (regplain / "f.py").write_text("F = 1\n", encoding="utf-8")
    _w_symlink(root / "regalias", "regplain")

    (root / "gitwt").mkdir()
    (root / "gitwt" / ".git").write_text("gitdir: x\n", encoding="utf-8")
    (root / "gitwt" / "g.py").write_text("G = 1\n", encoding="utf-8")
    (root / "fakegit").mkdir()
    _w_symlink(root / "fakegit" / ".git", "../otherrepo/pkg/.git")
    (root / "fakegit" / "x.py").write_text("X = 1\n", encoding="utf-8")
    (root / "fakerush").mkdir()
    _w_symlink(root / "fakerush" / ".rush", "../otherrepo")
    (root / "fakerush" / "f.py").write_text("F = 1\n", encoding="utf-8")
    (root / "symtoml").mkdir()
    _w_symlink(root / "symtoml" / "rush.toml", "../proj/rush.toml", directory=False)
    (root / "symtoml" / "f.py").write_text("F = 1\n", encoding="utf-8")

    (root / "home" / ".git").mkdir(parents=True)
    _w_symlink(root / "home" / "code", "../datacode")
    proj2 = root / "datacode" / "proj2"
    (proj2 / "src").mkdir(parents=True)
    (proj2 / "rush.toml").write_text("", encoding="utf-8")
    (proj2 / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")

    _w_symlink(root / "loopA", "loopB")
    _w_symlink(root / "loopB", "loopA")
    _w_symlink(root / "dangleW", "missing")
    (root / "locked" / "inner").mkdir(parents=True)
    (root / "locked" / "inner" / "f.py").write_text("F = 1\n", encoding="utf-8")
    (root / "u").mkdir()
    _w_symlink(base / "above", root)

    team = root / "team"
    (team / ".rush").mkdir(parents=True)
    (team / ".rush" / "project.json").write_text(
        json.dumps({"project_id": "team/alpha"}), encoding="utf-8"
    )
    ids = {
        "proj": register_project(proj, data_root=data_root).project_id,
        "otherrepo": register_project(otherrepo, data_root=data_root).project_id,
        "regplain": register_project(regplain, data_root=data_root).project_id,
        "team": register_project(team, data_root=data_root).project_id,
    }
    for leftover in (regplain / ".rush" / "project.json", regplain / ".rush"):
        if leftover.is_dir():
            leftover.rmdir()
        elif leftover.exists():
            leftover.unlink()
    _CUSTOM_CALLS.clear()
    return SimpleNamespace(
        base=base,
        root=root,
        above=base / "above",
        data_root=data_root,
        ids=ids,
        proj=proj,
        otherrepo=otherrepo,
        unmarked=unmarked,
        nomark=nomark,
        regplain=regplain,
        u=root / "u",
    )


class _FsRecorder:
    """Records every `os.lstat`/`os.stat`/`os.readlink` path (pathlib and
    `os.path.realpath` call these at runtime) and every `open`, while armed."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[str, str]] = []
        self.armed = False
        for name in ("lstat", "stat", "readlink"):
            original = getattr(os, name)

            def wrapped(path, *args, _name=name, _original=original, **kwargs):
                if self.armed and not isinstance(path, int):
                    self.calls.append((_name, os.fsdecode(path)))
                return _original(path, *args, **kwargs)

            monkeypatch.setattr(os, name, wrapped)

    @contextlib.contextmanager
    def arm(self):
        with _recording_opens() as opens:
            self.armed = True
            try:
                yield self
            finally:
                self.armed = False
                self.calls.extend(("open", path) for path in opens)

    def opens_outside(self, *allowed: Path) -> list[str]:
        prefixes = [str(d) for d in allowed]
        return [
            path
            for kind, path in self.calls
            if kind == "open"
            and not any(path == p or path.startswith(p + os.sep) for p in prefixes)
        ]

    def touched(self, *dirs: Path) -> list[tuple[str, str]]:
        prefixes = [str(d) for d in dirs]
        return [
            (kind, path)
            for kind, path in self.calls
            if any(path == p or path.startswith(p + os.sep) for p in prefixes)
        ]


@pytest.fixture
def fs_recorder(monkeypatch: pytest.MonkeyPatch) -> _FsRecorder:
    return _FsRecorder(monkeypatch)


def _w_path(w: SimpleNamespace, spec: str) -> Path:
    if spec == "/":
        return Path("/")
    if spec.startswith("@above/"):
        return w.above / spec[len("@above/") :]
    return w.root / spec if spec != "w" else w.root


def _select(w: SimpleNamespace, anchor: str, raw: str, declared: str | None = None):
    from rush.invocation.targets import assert_contained, select_root

    anchor_path = _w_path(w, anchor)
    typed = str(_w_path(w, raw[1:])) if raw.startswith("=") else raw
    declared_root = _w_path(w, declared) if declared is not None else None
    selection = select_root(typed, anchor=anchor_path, declared_root=declared_root)
    assert_contained(selection)
    return typed, selection


# (id, anchor, raw, expected root, expected relative). A raw starting with
# "=" is the absolute path of the `w`-relative spec after it; "@above/..."
# is spelled through the `above -> w` alias.
_T3_ACCEPTS = [
    ("R1", "proj", "src/bad.py", "proj", "src/bad.py"),
    ("R2", "proj", "src/../src/bad.py", "proj", "src/bad.py"),
    ("R3", "proj/sub/deep", "../../src/bad.py", "proj", "src/bad.py"),
    ("R4", "w", "proj/src/bad.py", "proj", "src/bad.py"),
    ("R5", "u", "=proj/src/bad.py", "proj", "src/bad.py"),
    ("R6", "u", "=@above/proj/src/bad.py", "proj", "src/bad.py"),
    ("R7", "proj", "=@above/proj/src/bad.py", "proj", "src/bad.py"),
    ("R8", "proj", "nested/n.py", "proj/nested", "n.py"),
    ("R9", "w", "alias/src/bad.py", "proj", "src/bad.py"),
    ("R10", "w", "alias", "proj", "."),
    ("R11", "w", "chain1/src/bad.py", "proj", "src/bad.py"),
    ("R12", "w", "regalias/f.py", "regplain", "f.py"),
    ("R13", "u", "=nomark/out/s.py", "unmarked", "s.py"),
    ("R14", "u", "=nomark/out/sub/s.py", "unmarked/sub", "s.py"),
    ("R15", "u", "=plainalias/f.py", "plain", "f.py"),
    (
        "R16",
        "datacode/proj2",
        "=home/code/proj2/src/a.py",
        "datacode/proj2",
        "src/a.py",
    ),
    ("R17", "w", "gitwt/g.py", "gitwt", "g.py"),
    ("R18", "w", "fakegit/x.py", "fakegit", "x.py"),
    ("R19", "w", "fakerush/f.py", "fakerush", "f.py"),
    ("R20", "w", "symtoml/f.py", "symtoml", "f.py"),
    ("R21", "proj", "src/missing.py", "proj", "src/missing.py"),
    ("R22", "w", "nomark/real/f.py", "nomark/real", "f.py"),
    ("R23", "nomark/real", "../out/s.py", "unmarked", "s.py"),
    ("R24", "w", "proj", "proj", "."),
    ("R25", "proj", ".", "proj", "."),
    ("R26", "proj", "", "proj", "."),
    ("R27", "proj", "src/has space.py", "proj", "src/has space.py"),
    ("R28", "proj", " src/bad.py", "proj", " src/bad.py"),
    ("R29", "proj", "src/bad.py/", "proj", "src/bad.py"),
    ("R30", "proj", "src//bad.py", "proj", "src/bad.py"),
    ("R31", "proj", "src/bad.py/x", "proj", "src/bad.py/x"),
    ("R32", "/", "=@above/proj/src/bad.py", "proj", "src/bad.py"),
]


@pytest.mark.parametrize(
    ("anchor", "raw", "root", "relative"),
    [case[1:] for case in _T3_ACCEPTS],
    ids=[case[0] for case in _T3_ACCEPTS],
)
def test_t08_select_root_matrix_accepts(
    w: SimpleNamespace,
    fs_recorder: _FsRecorder,
    anchor: str,
    raw: str,
    root: str,
    relative: str,
) -> None:
    """§6 T3 accepts: exact (root, relative) for every link class, marker
    shape, spelling and anchor, including R1(iii) final directory links
    translated outside the anchor, R1(iv) the L2 anchor-alias case and R1(v)
    a filesystem-root anchor."""
    with fs_recorder.arm():
        _, selection = _select(w, anchor, raw)

    assert selection.root == _w_path(w, root)
    assert selection.relative == Path(relative)
    assert selection.target == _w_path(w, root) / relative
    # Marker probes never pass through a link: no probe below a symlinked
    # `.git` or `.rush`.
    assert fs_recorder.touched(w.otherrepo / "pkg" / ".git") == []
    assert fs_recorder.touched(w.root / "fakerush" / ".rush" / "project.json") == []
    # The only file opened is the registry index under the data root.
    assert fs_recorder.opens_outside(w.data_root) == []


def _l1(component: Path, project: Path) -> str:
    return f"Symlink detected at component '{component}' inside project '{project}'"


def _l3(component: Path, destination: Path) -> str:
    return (
        f"Symlink at component '{component}' is not a project root entry: "
        f"'{destination}' is not a marked or registered project root"
    )


def _unresolvable(component: Path, reason: str) -> str:
    return f"Symlink at component '{component}' cannot be resolved: {reason}"


def _t3_rejects(w: SimpleNamespace) -> dict[str, tuple]:
    """(anchor, raw, exception type, code, message tail) per §6 T3 reject row."""
    proj, root = w.proj, w.root
    return {
        "X1": (
            "proj",
            "vendor/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vendor", proj),
        ),
        "X2": (
            "proj",
            "vendor/pkg/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vendor", proj),
        ),
        "X3": (
            "w",
            "proj/vendor/pkg/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vendor", proj),
        ),
        "X4": (
            "u",
            "=proj/vendor/pkg/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vendor", proj),
        ),
        "X5": (
            "u",
            "=@above/proj/vendor/pkg/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vendor", proj),
        ),
        "X6": (
            "proj",
            "vabs/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vabs", proj),
        ),
        "X7": (
            "proj",
            "vchain/secret.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "vchain", proj),
        ),
        "X8": (
            "proj",
            "self/src/bad.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "self", proj),
        ),
        "X9": ("proj", "loop1/x", "SYMLINK_DISALLOWED", _l1(proj / "loop1", proj)),
        "X10": (
            "w",
            "loopA/x",
            "SYMLINK_DISALLOWED",
            _unresolvable(root / "loopA", "Too many levels of symbolic links"),
        ),
        "X11": (
            "w",
            "dangleW/x",
            "SYMLINK_DISALLOWED",
            _unresolvable(root / "dangleW", "No such file or directory"),
        ),
        "X12": (
            "u",
            "=dangleW/x",
            "SYMLINK_DISALLOWED",
            _unresolvable(root / "dangleW", "No such file or directory"),
        ),
        "X13": (
            "proj",
            "src/link.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "src" / "link.py", proj),
        ),
        "X14": (
            "proj",
            "src/alias.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "src" / "alias.py", proj),
        ),
        "X15": (
            "proj",
            "srcdir_alias/bad.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "srcdir_alias", proj),
        ),
        "X16": (
            "w",
            "nomark/out/s.py",
            "SYMLINK_DISALLOWED",
            _l3(w.nomark / "out", w.unmarked),
        ),
        "X17": (
            "w",
            "nomark/out/sub/s.py",
            "SYMLINK_DISALLOWED",
            _l3(w.nomark / "out", w.unmarked),
        ),
        "X18": (
            "nomark",
            "out/s.py",
            "SYMLINK_DISALLOWED",
            _l3(w.nomark / "out", w.unmarked),
        ),
        "X19": (
            "nomark",
            "=@above/nomark/out/s.py",
            "SYMLINK_DISALLOWED",
            _l3(w.nomark / "out", w.unmarked),
        ),
        "X20": (
            "w",
            "nomark/outabs/s.py",
            "SYMLINK_DISALLOWED",
            _l3(w.nomark / "outabs", w.unmarked),
        ),
        "X21": (
            "w",
            "plainalias/f.py",
            "SYMLINK_DISALLOWED",
            _l3(root / "plainalias", root / "plain"),
        ),
        "X22": (
            "u",
            "=proj/src/link.py",
            "SYMLINK_DISALLOWED",
            _l1(proj / "src" / "link.py", proj),
        ),
        "X23": (
            "w",
            "alias/../proj/src/bad.py",
            "PARENT_TRAVERSAL_DISALLOWED",
            f"'..' after symlink component '{root / 'alias'}' is forbidden",
        ),
        "X25": (
            "w",
            "home/code/proj2/src/a.py",
            "SYMLINK_DISALLOWED",
            _l1(root / "home" / "code", root / "home"),
        ),
        "X26": (
            "u",
            "=home/code/proj2/src/a.py",
            "SYMLINK_DISALLOWED",
            _l1(root / "home" / "code", root / "home"),
        ),
        "X27": (
            "datacode/proj2",
            "=home/code",
            "SYMLINK_DISALLOWED",
            _l1(root / "home" / "code", root / "home"),
        ),
        "X32": (
            "u",
            "=nomark/filelink",
            "SYMLINK_DISALLOWED",
            (
                f"Symlink detected at component '{w.nomark / 'filelink'}': "
                "a symlinked file is never transparent"
            ),
        ),
    }


_T3_REJECT_IDS = [
    *(f"X{i}" for i in range(1, 24)),
    "X25",
    "X26",
    "X27",
    "X32",
]


@pytest.mark.parametrize("row", _T3_REJECT_IDS)
def test_t08_select_root_matrix_rejects(
    w: SimpleNamespace, fs_recorder: _FsRecorder, row: str
) -> None:
    """§6 T3 rejects: exact code and message for L1 internal links (R1(ii)),
    L2 out-of-anchor links (R1(iv)), L3 non-root entries (R1(i): the /var or
    alias spelling of the anchor is judged by identity, X19 == X18), final
    file links, loops, dangling links and `..` after a link. Zero reads and
    zero descendant probes through the rejected link."""
    anchor, raw, code, message = _t3_rejects(w)[row]
    with fs_recorder.arm(), pytest.raises(ScopeWideningError) as excinfo:
        _select(w, anchor, raw)

    typed = str(_w_path(w, raw[1:])) if raw.startswith("=") else raw
    assert str(excinfo.value) == f"[{code}] at '{typed}': {message}"
    # The only file opened is the registry index under the data root.
    assert fs_recorder.opens_outside(w.data_root) == []
    # L1: nothing through the link at all; L2 only the destination itself;
    # L3 only the destination's own marker names.
    otherrepo_touches = fs_recorder.touched(w.otherrepo)
    destinations = {str(w.otherrepo)}
    if row == "X22":
        destinations.add(str(w.otherrepo / "secret.py"))
    assert {path for _, path in otherrepo_touches} <= destinations, otherrepo_touches
    if row in {"X1", "X2", "X3", "X6", "X7"}:
        assert otherrepo_touches == []
        assert [
            call
            for call in fs_recorder.touched(w.proj / "vendor")
            if call != ("lstat", str(w.proj / "vendor"))
        ] == []
    unmarked_touches = {path for _, path in fs_recorder.touched(w.unmarked)}
    allowed_unmarked = {
        str(w.unmarked),
        str(w.unmarked / "rush.toml"),
        str(w.unmarked / ".rush"),
        str(w.unmarked / ".git"),
    }
    if row == "X32":
        allowed_unmarked.add(str(w.unmarked / "s.py"))
    assert unmarked_touches <= allowed_unmarked, unmarked_touches


def test_t08_select_root_dotdot_in_missing_tail_is_rejected_by_containment(
    w: SimpleNamespace,
) -> None:
    """§6 T3 X24: `..` inside a missing tail stays in the suffix; the walk
    returns and the containment pre-check rejects it."""
    from rush.invocation.targets import assert_contained, select_root

    selection = select_root("missing/../src/bad.py", anchor=w.proj)
    assert selection.relative == Path("missing/../src/bad.py")
    with pytest.raises(ScopeWideningError) as excinfo:
        assert_contained(selection)
    assert str(excinfo.value) == (
        "[PARENT_TRAVERSAL_DISALLOWED] at 'missing/../src/bad.py': "
        "Parent traversal '..' is forbidden"
    )


def test_t08_select_root_reparse_point_is_rejected(
    w: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§6 T3 X28 / R21: a non-symlink reparse point (Windows junction) is a
    link with its own code, tested by injecting the `lstat` result."""
    from rush.invocation.targets import select_root

    junction = w.proj / "junc"
    real_lstat = os.lstat

    def fake_lstat(path, *args, **kwargs):
        if os.fspath(path) == str(junction):
            return SimpleNamespace(
                st_mode=0o040755, st_dev=1, st_ino=2, st_file_attributes=0x400
            )
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", fake_lstat)
    with pytest.raises(ScopeWideningError) as excinfo:
        select_root("junc/x", anchor=w.proj)
    assert str(excinfo.value) == (
        f"[REPARSE_POINT_DISALLOWED] at 'junc/x': {_l1(junction, w.proj)}"
    )


@pytest.mark.parametrize(
    ("raw", "error", "message"),
    [
        ("=otherrepo/secret.py", AmbiguousRootError, "does not contain"),
        ("vendor/x", ScopeWideningError, "[SYMLINK_DISALLOWED]"),
        ("..", AmbiguousRootError, "does not contain"),
    ],
    ids=["X29", "X30", "X31"],
)
def test_t08_select_root_declared_root_rejects(
    w: SimpleNamespace, raw: str, error: type, message: str
) -> None:
    """§6 T3 X29-X31: under a declared root, an unrelated target (or `..`
    out of it) is AmbiguousRootError; a link below it is ScopeWideningError."""
    with pytest.raises(error) as excinfo:
        _select(w, "proj", raw, declared="proj")
    assert type(excinfo.value) is error
    assert message in str(excinfo.value)
    if error is AmbiguousRootError:
        typed = str(_w_path(w, raw[1:])) if raw.startswith("=") else raw
        assert str(excinfo.value) == (
            f"registered root '{w.proj}' does not contain requested target '{typed}'"
        )


@pytest.mark.parametrize(
    ("raw", "relative"),
    [
        ("nested/n.py", "nested/n.py"),
        ("=@above/proj/src/bad.py", "src/bad.py"),
        ("=alias/src/bad.py", "src/bad.py"),
        (".", "."),
    ],
    ids=["D1", "D2", "D3", "D4"],
)
def test_t08_select_root_declared_root_accepts(
    w: SimpleNamespace, raw: str, relative: str
) -> None:
    """§6 T3 D1-D4: a declared root is authoritative over nested markers and
    accepts alias spellings of itself."""
    _, selection = _select(w, "proj", raw, declared="proj")
    assert selection.root == w.proj
    assert selection.relative == Path(relative)


@pytest.mark.parametrize("transport", ["direct", "mcp-custom-path"])
def test_t08_select_root_permission_error_propagates(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace, transport: str
) -> None:
    """§6 T3 P1 / B19 / R22: an unreadable component raises PermissionError
    unchanged -- no anchor fallback, no handler call."""
    locked = w.root / "locked"
    locked.chmod(0)
    try:
        if transport == "direct":
            from rush.invocation.targets import select_root

            with pytest.raises(PermissionError):
                select_root("locked/inner/f.py", anchor=w.root)
        else:
            out = _invoke(monkeypatch, "mcp-custom-path", "locked/inner/f.py", w.root)
            assert isinstance(out.exc, PermissionError), repr(out.exc)
            assert out.calls == []
    finally:
        locked.chmod(0o755)


# §5 validation table: every row, every spelling column. `alias -> proj`
# here is the table's `alias`; `above -> w` is its `/var`-style alias.
_TABLE_ROWS = [
    # (row id, target spec under w, outcome per column: rel-from-w,
    #  abs-physical-from-w, abs-alias-from-w, from-u, from-inner-anchor)
    ("proj/vendor/x", "proj/vendor/x", ("L1", "L1", "L1", "L1", "L1")),
    (
        "proj/vendor/pkg/secret.py",
        "proj/vendor/pkg/secret.py",
        ("L1", "L1", "L1", "L1", "L1"),
    ),
    ("nomark/out/s.py", "nomark/out/s.py", ("L3", "L3", "L3", "unmarked", "L3")),
    (
        "nomark/out/sub/s.py",
        "nomark/out/sub/s.py",
        ("L3", "L3", "L3", "unmarked/sub", "L3"),
    ),
    ("alias", "alias", ("proj", "proj", "proj", "proj", None)),
    ("var-alias-proj-file", "proj/src/bad.py", (None, None, "proj", "proj", "proj")),
    ("var-alias-no-marker-file", "plain/f.py", (None, None, "plain", "plain", "plain")),
]


def _table_inner_anchor(spec: str) -> tuple[str, str]:
    """The table's last column: from anchor `proj` or `nomark`, spelled
    relative to that anchor (or as the /var-style absolute alias)."""
    if spec.startswith("proj/vendor/"):
        return "proj", spec[len("proj/") :]
    if spec.startswith("nomark/"):
        return "nomark", spec[len("nomark/") :]
    return "proj", "=@above/" + spec


_TABLE_COLUMNS = (
    "rel-from-w",
    "abs-physical-from-w",
    "abs-alias-from-w",
    "from-u",
    "inner",
)
_TABLE_CELLS = [
    (row_id, spec, column, expected)
    for row_id, spec, outcomes in _TABLE_ROWS
    for column, expected in zip(_TABLE_COLUMNS, outcomes, strict=True)
    if expected is not None
]


@pytest.mark.parametrize(
    ("spec", "column", "expected"),
    [cell[1:] for cell in _TABLE_CELLS],
    ids=[f"{cell[0]}-{cell[2]}" for cell in _TABLE_CELLS],
)
def test_t08_validation_table(
    w: SimpleNamespace, spec: str, column: str, expected: str
) -> None:
    """§5 R1 validation table, every applicable cell: L1/L3 rejects or the
    exact accepted root, identical across relative, absolute physical and
    absolute alias spellings of the same anchor (R1(i))."""
    anchor, raw = {
        "rel-from-w": ("w", spec),
        "abs-physical-from-w": ("w", "=" + spec),
        "abs-alias-from-w": ("w", "=@above/" + spec),
        "from-u": ("u", "=" + spec),
        "inner": _table_inner_anchor(spec),
    }[column]
    if expected in ("L1", "L3"):
        with pytest.raises(ScopeWideningError) as excinfo:
            _select(w, anchor, raw)
        detail = str(excinfo.value).split(": ", 1)[1]
        if expected == "L1":
            assert detail.startswith("Symlink detected at component"), detail
            assert detail.endswith(f"inside project '{w.proj}'"), detail
        else:
            assert "is not a project root entry" in detail, detail
        return
    _, selection = _select(w, anchor, raw)
    assert selection.root == _w_path(w, expected)


@pytest.mark.parametrize("transport", ["check", "ui", "ui-json", "dashboard"])
def test_t08_root_entry_dispatch_unmarked_and_registered_aliases(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace, transport: str
) -> None:
    """§6 T2 (vi)/(vii): an alias to an unmarked, unregistered directory is
    rejected with the L3 message and exit 2; an alias to a registered root is
    accepted with that registered root."""
    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush import tui
    from rush.cli import cli
    from rush.dashboard import server as dashboard_server

    probe, captured = _probe_check_suite(monkeypatch)
    seeds: list[list] = []
    monkeypatch.setattr(cli_module, "_stdout_is_tty", lambda: transport == "ui")
    monkeypatch.setattr(
        tui, "run_interactive_tui", lambda s, **kwargs: seeds.append(list(s))
    )
    monkeypatch.setattr(
        dashboard_server,
        "create_dashboard_server",
        lambda *a, **k: pytest.fail("no server for a rejected input"),
    )
    monkeypatch.chdir(w.root)
    argv = {
        "check": ["check", "--json"],
        "ui": ["ui"],
        "ui-json": ["ui", "--json"],
        "dashboard": ["dashboard", "--no-open", "--json"],
    }[transport]

    rejected = CliRunner().invoke(cli, [*argv, "plainalias"])
    assert rejected.exit_code == 2, rejected.output
    message = _l3(w.root / "plainalias", w.root / "plain")
    if transport == "check":
        assert json.loads(rejected.stdout)["status"] == "error"
    else:
        assert f"[SYMLINK_DISALLOWED] at 'plainalias': {message}" in rejected.output
    assert probe.calls == []
    assert seeds == []

    if transport == "dashboard":
        return
    accepted = CliRunner().invoke(cli, [*argv, "regalias"])
    assert accepted.exit_code == 0, accepted.output
    if transport == "ui":
        [[seed]] = seeds
        assert seed.root == w.regplain
        assert seed.lexical_path == w.root / "regalias"
        return
    assert captured[-1].workspace_root == w.regplain
    assert probe.calls == [(str(w.regplain), str(w.root))]


def test_t08_suite_walks_once(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T5 / B14: one walk per suite run, reused by every step; a rejected
    input becomes one identical error child per step (fail_fast stops after
    the first) with zero handler calls."""
    from rush.workflows import suites

    probes = [_RecordingProbe(f"t8-step{i}") for i in range(3)]
    monkeypatch.setattr(suites, "ALL_TOOLS", probes)
    walks: list[str] = []
    real_select = suites.select_root

    def spy_select(raw, **kwargs):
        walks.append(str(raw))
        return real_select(raw, **kwargs)

    monkeypatch.setattr(suites, "select_root", spy_select)
    captured = _spy(monkeypatch, suites)
    monkeypatch.chdir(w.proj)
    suite = WorkflowSuite(
        name="t8", description="t8", tool_sequence=tuple(p.name for p in probes)
    )

    ok = run_workflow_suite(suite, Path("src/bad.py"), ExecutionPermissions())
    assert ok["status"] == "ok"
    assert walks == ["src/bad.py"]
    assert {(c.workspace_root, c.targets[0].relative_path) for c in captured} == {
        (w.proj, Path("src/bad.py"))
    }

    walks.clear()
    for probe in probes:
        probe.calls.clear()
    rejected = run_workflow_suite(
        suite, Path("vendor/secret.py"), ExecutionPermissions(), fail_fast=False
    )
    assert walks == ["vendor/secret.py"]
    summaries = [c["summary"] for c in rejected["metadata"]["children"]]
    assert all(s.startswith("error: [SYMLINK_DISALLOWED]") for s in summaries)
    assert rejected["metadata"]["children"] == [
        _refused_child(p.name, summary)
        for p, summary in zip(probes, summaries, strict=True)
    ]
    assert all(p.calls == [] for p in probes)
    fast = run_workflow_suite(
        suite, Path("vendor/secret.py"), ExecutionPermissions(), fail_fast=True
    )
    fast_child, *_later = fast["metadata"]["children"]
    assert fast_child["summary"].startswith("error: [SYMLINK_DISALLOWED]")
    # Phase 70 T17 S17.2: fail-fast records every later step as not run.
    not_run = {"disposition": "not_run", "cause": "fail_fast_after:t8-step0"}
    assert fast["metadata"]["children"] == [
        _refused_child("t8-step0", fast_child["summary"]),
        *(
            {
                "tool": p.name,
                "status": "skipped",
                "summary": "skipped: not run",
                "reason": "fail_fast_after:t8-step0",
                "engines": [],
                "scope": {"coverage": "unavailable", "reason": None},
                "execution": not_run,
                "metadata": {"execution": not_run},
            }
            for p in probes[1:]
        ),
    ]
    assert all(p.calls == [] for p in probes)


def _std_probe_wrapper(
    monkeypatch: pytest.MonkeyPatch, anchor: Path, probe: object | None = None
):
    from rush.invocation import InvocationExecutor
    from rush.mcp_support import tool_registry

    probe = probe or _RecordingProbe()
    executor = InvocationExecutor()
    executor.register(probe.name, probe.__call__)
    captured = _spy(monkeypatch, tool_registry)
    return (
        tool_registry.make_tool_wrapper(probe, executor, anchor_cwd=anchor),
        probe,
        captured,
    )


def test_t08_declared_project_routing(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T6 / B11 / R5 / R9: `project` routes ID first, then as a path
    anchored to the server-start cwd (never the live cwd); one registry read
    per call, never `resolve_project`; the probe never receives `project`;
    named errors for empty, unknown and missing roots."""
    from rush.mcp_support import tool_registry
    from rush.workflows import projects
    from rush.workflows.projects import ProjectNotFoundError, ProjectRootMissingError

    reads: list[object] = []
    real_index = tool_registry.registered_root_index

    def spy_index(*args, **kwargs):
        reads.append(args)
        return real_index(*args, **kwargs)

    monkeypatch.setattr(tool_registry, "registered_root_index", spy_index)
    monkeypatch.setattr(
        projects,
        "resolve_project",
        lambda *a, **k: pytest.fail("wrappers never call resolve_project"),
    )
    monkeypatch.chdir(w.nomark)
    wrapper, probe, captured = _std_probe_wrapper(monkeypatch, w.u)

    for value in (
        w.ids["proj"],
        "../proj",
        str(w.proj),
        str(w.above / "proj"),
    ):
        reads.clear()
        wrapper(path="src/bad.py", project=value)
        assert reads == [()], value
        assert captured[-1].workspace_root == w.proj, value
        assert captured[-1].declared_root == w.proj, value
        assert captured[-1].targets[0].relative_path == Path("src/bad.py")
        assert "project" not in dict(captured[-1].typed_args or ()), value
    assert len(probe.calls) == 4

    team_wrapper, _, team_captured = _std_probe_wrapper(monkeypatch, w.u)
    team_wrapper(project="team/alpha")
    assert team_captured[-1].workspace_root == w.root / "team"
    bare_wrapper, _, bare_captured = _std_probe_wrapper(monkeypatch, w.root)
    bare_wrapper(path="src/bad.py", project="proj")
    assert bare_captured[-1].workspace_root == w.proj

    with pytest.raises(ProjectNotFoundError) as empty:
        wrapper(path="src/bad.py", project="")
    assert empty.value.code == "PROJECT_NOT_FOUND"
    with pytest.raises(
        ProjectNotFoundError, match="^no registered project matches: nope$"
    ):
        wrapper(path="src/bad.py", project="nope")
    gone = w.root / "gone"
    gone.mkdir()
    gone_id = register_project(gone, data_root=w.data_root).project_id
    for leftover in (gone / ".rush" / "project.json", gone / ".rush", gone):
        leftover.unlink() if leftover.is_file() else leftover.rmdir()
    with pytest.raises(ProjectRootMissingError) as missing:
        wrapper(path="src/bad.py", project=gone_id)
    assert missing.value.code == "PROJECT_ROOT_MISSING"


def test_t08_project_id_tools_route_declared_root_and_forward_it(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T6 / R20: a tool with its own `project_id` routes it as the
    declared root and receives it unchanged; the real continuity and memory
    schemas publish `project_id` with the §3.2 description and no `project`."""
    from rush import mcp

    received: list[object] = []

    class _ProjectIdProbe:
        name = "t8-project-id"
        mcp_description = "t8"

        def __call__(self, path: Path = Path("."), project_id: str | None = None):
            received.append(project_id)
            return {"status": "ok", "path": str(path)}

    wrapper, _, captured = _std_probe_wrapper(monkeypatch, w.u, _ProjectIdProbe())
    wrapper(path="src/bad.py", project_id=w.ids["proj"])
    assert captured[-1].declared_root == w.proj
    assert received == [w.ids["proj"]]

    monkeypatch.chdir(w.u)
    tools = {t.name: t for t in asyncio.run(mcp.build_server().list_tools())}
    for name in ("rush_continuity", "rush_memory"):
        props = tools[name].inputSchema["properties"]
        assert "project" not in props
        assert props["project_id"]["description"].startswith(
            "Also serves as this call's declared root. Registered project ID"
        )
    assert (
        tools["rush_lint"]
        .inputSchema["properties"]["project"]["description"]
        .startswith("Registered project ID or registered project root path")
    )


def _server_tool(server: object, name: str):
    return server._tool_manager._tools[name].fn


def test_t08_request_tool_anchoring(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T7 / B17 / §3.7: request-dict tools anchor their path-bearing
    fields to the server-start cwd; project references route ID first; the
    UUID-only select operation is untouched."""
    from rush import mcp
    from rush.tools import agent_connection, project, scan, scan_handoff
    from rush.workflows import project_run

    seen: dict[str, list[dict]] = {}

    def spy_handle(label: str, cls: type) -> None:
        original = cls.handle_request

        def handle(self, request):
            seen.setdefault(label, []).append(dict(request))
            return original(self, request)

        monkeypatch.setattr(cls, "handle_request", handle)

    spy_handle("scan", scan.ScanTool)
    spy_handle("project", project.ProjectTool)
    spy_handle("handoff", scan_handoff.ScanHandoffTool)
    spy_handle("agent", agent_connection.AgentConnectionTool)
    cancels: list[str] = []
    monkeypatch.setattr(
        project_run,
        "cancel_scan_run",
        lambda project_ref, run_id: cancels.append(project_ref) or {},
    )

    monkeypatch.chdir(w.root)
    server = mcp.build_server()
    monkeypatch.chdir(w.u)
    base = {"schema_version": 1}

    status = _server_tool(server, "rush_scan")(
        request={**base, "operation": "status", "project": "proj", "run_id": "nope"}
    )
    assert seen["scan"][-1]["project"] == str(w.proj)
    assert status["raw"]["error"]["message"] == "unknown run_id: nope"
    _server_tool(server, "rush_scan")(
        request={**base, "operation": "status", "project": "team/alpha", "run_id": "r"}
    )
    assert seen["scan"][-1]["project"] == "team/alpha"
    _server_tool(server, "rush_scan")(
        request={**base, "operation": "cancel", "project": "proj", "run_id": "r"}
    )
    assert cancels == [str(w.proj)]

    grants = {"allow_cache_write": True, "allow_artifact_write": True}
    added = _server_tool(server, "rush_project")(
        request={**base, **grants, "operation": "add", "path": "plain"}
    )
    assert added["status"] == "ok", added
    assert added["raw"]["data"]["root"] == str(w.root / "plain")
    made = _server_tool(server, "rush_project")(
        request={
            **base,
            **grants,
            "operation": "create",
            "parent": "nomark",
            "name": "made",
        }
    )
    assert made["status"] == "ok", made
    assert (w.nomark / "made").is_dir()
    (w.root / "moved").mkdir()
    record = resolve_project(w.ids["regplain"], data_root=w.data_root)
    _server_tool(server, "rush_project")(
        request={
            **base,
            **grants,
            "operation": "relink",
            "project": w.ids["regplain"],
            "path": "moved",
            "expected_revision": record["revision"],
        }
    )
    assert seen["project"][-1]["path"] == str(w.root / "moved")
    assert seen["project"][-1]["project"] == w.ids["regplain"]
    selected = _server_tool(server, "rush_project")(
        request={
            **base,
            "operation": "select",
            "project": "not-a-uuid",
            "session_id": "s",
        }
    )
    assert seen["project"][-1]["project"] == "not-a-uuid"
    assert selected["status"] == "error"
    shown = _server_tool(server, "rush_project")(
        request={**base, "operation": "show", "project": "proj"}
    )
    assert seen["project"][-1]["project"] == str(w.proj)
    assert shown["status"] == "ok", shown

    _server_tool(server, "rush_scan_handoff")(
        request={**base, "operation": "status", "project": "proj", "handoff_id": "h"}
    )
    assert seen["handoff"][-1]["project"] == str(w.proj)

    for project_root, binary, expected_root, expected_binary in (
        ("x", "bin/rush", str(w.root / "x"), str(w.root / "bin" / "rush")),
        ("~/r", "/abs/rush", "~/r", "/abs/rush"),
    ):
        _server_tool(server, "rush_agent_connection")(
            request={
                **base,
                "operation": "doctor",
                "agent_id": "a",
                "project_root": project_root,
                "rush_binary": binary,
            }
        )
        assert seen["agent"][-1]["project_root"] == expected_root
        assert seen["agent"][-1]["rush_binary"] == expected_binary


def test_t08_custom_tool_roots_and_containment(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T8 / B15 / B16 / R4: custom `file` arguments are contained like
    `path`; every custom helper is rooted at the declared root (else the
    server-start cwd) through `_anchor`, which no schema publishes and no
    caller can set."""
    from rush import mcp
    from rush.mcp_mesh import lock_manager
    from rush.mcp_support import tool_registry
    from rush.tools import blast_radius, hallu_guard, simplify, strictify, test_heal

    roots: dict[str, list[Path | None]] = {}
    for label, cls in (
        ("hallu", hallu_guard.HalluGuard),
        ("blast", blast_radius.BlastRadiusAnalyzer),
        ("heal", test_heal.TestHealer),
        ("simplify", simplify.ComplexityDecomposer),
        ("strictify", strictify.TypeSynthesizer),
        ("mesh", lock_manager.MeshLockManager),
    ):
        original_init = cls.__init__

        def spy_init(self, project_root=None, *, _label=label, _init=original_init):
            roots.setdefault(_label, []).append(project_root)
            _init(self, project_root=project_root)

        monkeypatch.setattr(cls, "__init__", spy_init)

    monkeypatch.chdir(w.u)
    server = mcp.build_server()
    monkeypatch.chdir(w.nomark)
    proj_id = w.ids["proj"]

    with pytest.raises(ScopeWideningError) as excinfo:
        _server_tool(server, "rush_simplify")(file="src/alias.py", project=proj_id)
    assert str(excinfo.value).startswith("[SYMLINK_DISALLOWED] at 'src/alias.py'")
    assert "simplify" not in roots

    captured = _spy(monkeypatch, tool_registry)
    _server_tool(server, "rush_strictify")(file="src/bad.py", project=proj_id)
    assert dict(captured[-1].typed_args)["file"] == str(w.proj / "src" / "bad.py")
    assert roots["strictify"] == [w.proj]

    _server_tool(server, "rush_hallu_guard")(path="src/bad.py", project=proj_id)
    _server_tool(server, "rush_blast_radius")(path="src/bad.py", project=proj_id)
    _server_tool(server, "rush_simplify")(file="src/bad.py", project=proj_id)
    _server_tool(server, "rush_mesh_acquire_lock")(
        path="src/bad.py", agent_id="a", project=proj_id
    )
    _server_tool(server, "rush_mesh_release_lock")(
        path="src/bad.py", agent_id="a", project=proj_id
    )
    _server_tool(server, "rush_test_heal")(target="tests/test_x.py")
    for label in ("hallu", "blast", "simplify"):
        assert roots[label] == [w.proj], label
    assert roots["mesh"] == [w.proj, w.proj]
    assert roots["heal"] == [w.u]

    with pytest.raises(TypeError):
        _server_tool(server, "rush_strictify")(file="src/bad.py", _anchor="/etc")
    asyncio.run(
        server.call_tool(
            "rush_strictify",
            {"file": "src/bad.py", "project": proj_id, "_anchor": "/etc"},
        )
    )
    assert roots["strictify"][-1] == w.proj
    for tool in asyncio.run(server.list_tools()):
        props = tool.inputSchema.get("properties", {})
        assert "_anchor" not in props, tool.name
        assert "project_root" not in props, tool.name


def test_t08_standard_wrapper_contains_files_members(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§3.4 step 2: every `files` member is walked like the target and must lie
    under the selected root. Relative members keep their root-relative base
    contract (not the server anchor); an alias spelling is normalized, a
    member outside the root is undeclared, a member through an internal link
    is rejected."""
    from rush.invocation.models import UndeclaredInputError

    class _FilesProbe:
        name = "t8-files"
        mcp_description = "t8"

        def __call__(self, path: Path = Path("."), files: list[str] | None = None):
            return {"status": "ok", "path": str(path)}

    wrapper, _, captured = _std_probe_wrapper(monkeypatch, w.u, _FilesProbe())
    wrapper(
        path=str(w.proj),
        files=["src/bad.py", str(w.above / "proj" / "src" / "bad.py")],
    )
    assert [t.relative_path for t in captured[-1].targets] == [
        Path("."),
        Path("src/bad.py"),
        Path("src/bad.py"),
    ]
    with pytest.raises(UndeclaredInputError):
        wrapper(path=str(w.proj), files=[str(w.otherrepo / "secret.py")])
    with pytest.raises(ScopeWideningError):
        wrapper(path=str(w.proj), files=["vendor/secret.py"])


def test_t08_secondary_cwd_relative_args(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T9 / §3.8 / R3: cwd-relative secondary arguments resolve against the
    declared root (else the server-start cwd); root-relative ones keep their
    tool contracts and pass through unchanged."""
    import functools

    from rush import mcp
    from rush.tools import ALL_TOOLS

    received: dict[str, dict] = {}
    by_name = {tool.name: tool for tool in ALL_TOOLS}
    for name in ("coverage", "sbom", "offline-review", "mutation", "error-catalog"):
        tool_type = type(by_name[name])

        def record_call(self, path, *args, _name=name, **kwargs):
            received[_name] = {"path": path, **kwargs}
            return {
                "tool": _name,
                "engine": None,
                "engine_version": None,
                "status": "ok",
                "duration_ms": 0,
                "summary": "t8",
                "findings": [],
            }

        monkeypatch.setattr(
            tool_type,
            "__call__",
            functools.wraps(tool_type.__call__)(record_call),
        )

    monkeypatch.chdir(w.u)
    server = mcp.build_server()
    monkeypatch.chdir(w.nomark)

    _server_tool(server, "rush_coverage")(
        path=".", report_path="cov.xml", project=w.ids["proj"]
    )
    assert Path(received["coverage"]["report_path"]) == w.proj / "cov.xml"
    _server_tool(server, "rush_sbom")(path=".", output_path="sbom.json")
    assert Path(received["sbom"]["output_path"]) == w.u / "sbom.json"
    _server_tool(server, "rush_offline_review")(path=".", runner_path="bin/run")
    assert Path(received["offline-review"]["runner_path"]) == w.u / "bin" / "run"
    _server_tool(server, "rush_mutation")(
        path=".", source_paths=["src"], project=w.ids["proj"]
    )
    assert received["mutation"]["source_paths"] == ["src"]
    _server_tool(server, "rush_error_catalog")(path=".", export_path="out.md")
    assert received["error-catalog"]["export_path"] in ("out.md", Path("out.md"))


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_config_after_containment(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace, transport: str
) -> None:
    """§6 T10 / B8 / R6: walk < containment < config read < target hash, for
    CLI and MCP; a symlinked root `rush.toml` is rejected before any config
    read."""
    from rush.cli_support import rendering
    from rush.mcp_support import tool_registry

    module = rendering if transport == "cli" else tool_registry
    order: list[str] = []
    for name in ("select_root", "assert_contained", "load_config"):
        original = getattr(module, name)

        def spy(*args, _name=name, _original=original, **kwargs):
            order.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, spy)
    target = w.proj / "src" / "bad.py"
    real_read_bytes = Path.read_bytes

    def spy_read_bytes(self: Path) -> bytes:
        if self == target:
            order.append("hash")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)

    def run(typed: str, cwd: Path) -> InvocationContext:
        if transport == "cli":
            return _run_cli(monkeypatch, typed, cwd)
        context, _ = _run_mcp_standard(monkeypatch, typed, cwd, anchor_cwd=cwd)
        return context

    run("src/bad.py", w.proj)
    assert order[:4] == ["select_root", "assert_contained", "load_config", "hash"]

    order.clear()
    with pytest.raises(ScopeWideningError) as excinfo:
        run("symtoml/f.py", w.root)
    assert str(excinfo.value) == (
        "[SYMLINK_DISALLOWED] at 'rush.toml': Symlink detected at component "
        f"'{w.root / 'symtoml' / 'rush.toml'}'"
    )
    assert order == ["select_root", "assert_contained"]


@pytest.mark.parametrize("transport", ["cli", "mcp-standard"])
def test_t08_config_discovery_starts_at_selected_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, transport: str
) -> None:
    """§6 T10 / R6: config discovery starts at the selected root (loaded after
    containment); a descriptor-rooted project below a marked directory still
    loads that directory's `rush.toml`."""
    _isolate_registry(monkeypatch, tmp_path / "rush-data")
    outer = tmp_path.resolve() / "outer"
    (outer / "src").mkdir(parents=True)
    (outer / "rush.toml").write_text(
        "[tools.memory]\nrecord = true\n", encoding="utf-8"
    )
    (outer / "src" / "a.py").write_text("A = 1\n", encoding="utf-8")
    inner = outer / "inner"
    (inner / ".rush").mkdir(parents=True)
    (inner / ".rush" / "project.json").write_text("{}", encoding="utf-8")
    (inner / "b.py").write_text("B = 1\n", encoding="utf-8")

    def run(typed: str) -> InvocationContext:
        if transport == "cli":
            return _run_cli(monkeypatch, typed, outer)
        context, _ = _run_mcp_standard(monkeypatch, typed, outer, anchor_cwd=outer)
        return context

    marked = run("src/a.py")
    assert marked.workspace_root == outer
    assert marked.memory_record is True
    nested = run("inner/b.py")
    assert nested.workspace_root == inner
    assert nested.memory_record is True


def test_t08_resolve_target_has_no_resolve_fallback(w: SimpleNamespace) -> None:
    """§6 T11 / B8 / R12: an absolute spelling that is not lexically under the
    root is undeclared -- never resolved through links onto the root."""
    from rush.invocation.models import UndeclaredInputError
    from rush.invocation.targets import resolve_target

    typed = w.above / "proj" / "srcdir_alias" / "bad.py"
    with pytest.raises(UndeclaredInputError) as excinfo:
        resolve_target(w.proj, str(typed))
    assert str(excinfo.value) == (
        f"External host input '{typed}' is outside workspace root '{w.proj}'"
    )
    target = resolve_target(w.proj, str(w.proj / "src" / "bad.py"))
    assert target.relative_path == Path("src/bad.py")


def test_t08_original_request_data(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T12 / B9 / R8: a Click-defaulted path and an omitted MCP path are
    unavailable originals (never fabricated); typed input is verbatim; the
    normalized targets, ordered args and config digest do not depend on the
    spelling; a secret-shaped segment is redacted in a rejection message."""
    from click.testing import CliRunner

    from rush.cli import cli

    _, captured = _probe_check_suite(monkeypatch)
    monkeypatch.chdir(w.proj)
    assert CliRunner().invoke(cli, ["check", "--json"]).exit_code == 0
    assert captured[-1].original_requested_targets == ()
    assert captured[-1].invocation_start_cwd == w.proj
    assert CliRunner().invoke(cli, ["check", ".", "--json"]).exit_code == 0
    assert captured[-1].original_requested_targets == (".",)
    assert CliRunner().invoke(cli, ["ui", "--json"]).exit_code == 0
    assert captured[-1].original_requested_targets == ()
    assert captured[-1].invocation_start_cwd == w.proj

    wrapper, _, mcp_captured = _std_probe_wrapper(monkeypatch, w.proj)
    wrapper()
    assert mcp_captured[-1].original_requested_targets == ()

    contexts = [
        _run_cli(monkeypatch, typed, w.proj)
        for typed in (
            "src/bad.py",
            str(w.proj / "src" / "bad.py"),
            str(w.above / "proj" / "src" / "bad.py"),
            "./src/bad.py",
        )
    ]
    assert len({c.targets for c in contexts}) == 1
    assert len({c.ordered_args for c in contexts}) == 1
    assert len({c.effective_config_digest for c in contexts}) == 1

    token = "ghp_" + "a" * 36
    (w.proj / token).symlink_to(w.otherrepo, target_is_directory=True)
    with pytest.raises(ScopeWideningError) as excinfo:
        _run_cli(monkeypatch, f"{token}/secret.py", w.proj)
    assert token not in str(excinfo.value)
    assert "[REDACTED_GITHUB_TOKEN]" in str(excinfo.value)


def test_t08_process_cwd_change_after_server_build(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T13 / B2: after `build_server` at `proj` and a chdir, every custom
    wrapper kind (path, file, target) and a relative declared project still
    resolve under `proj`."""
    from rush import mcp
    from rush.mcp_support import tool_registry

    monkeypatch.chdir(w.proj)
    server = mcp.build_server()
    monkeypatch.chdir(w.u)
    captured = _spy(monkeypatch, tool_registry)

    _server_tool(server, "rush_token_outline")(path="src/bad.py")
    _server_tool(server, "rush_strictify")(file="src/bad.py")
    _server_tool(server, "rush_test_heal")(target="src/bad.py")
    _server_tool(server, "rush_token_outline")(path="src/bad.py", project=".")
    for context in captured:
        assert context.workspace_root == w.proj
        assert context.targets[0].relative_path == Path("src/bad.py")
        assert context.invocation_start_cwd == w.proj


def test_t08_dashboard_uses_registered_root_everywhere(
    monkeypatch: pytest.MonkeyPatch, w: SimpleNamespace
) -> None:
    """§6 T15 / B12: for `rush dashboard alias`, provenance capture, artifact
    snapshots, the suite and the publish all receive `Path(record.root)`."""
    import threading

    from click.testing import CliRunner

    from rush import cli as cli_module
    from rush.cli import cli
    from rush.dashboard import server as dashboard_server
    from rush.workflows import project_run, suites

    received: dict[str, object] = {}
    done = threading.Event()

    class _FakeServer:
        def serve_forever(self) -> None:
            done.wait(timeout=20)

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    fake_ctx = SimpleNamespace(
        server_id="t8",
        owner_instance_id="t8-owner",
        mutations=SimpleNamespace(allocate_scan_generation=lambda project_id: 1),
    )

    def fake_suite(**kwargs):
        received["suite"] = kwargs["path"]
        kwargs["on_tool_complete"]({"tool": "t8-probe", "status": "ok"})
        return {"tool": "check", "status": "ok", "findings": [], "summary": "ok"}

    def fake_snapshots(root, *args, **kwargs):
        received["snapshots"] = root
        return {}

    def fake_provenance(root, project_id):
        received["provenance"] = root
        return ("run", "attempt")

    def fake_publish(ctx, project_id, root, aggregate, **kwargs):
        received["publish"] = root
        done.set()

    monkeypatch.setattr(
        dashboard_server,
        "create_dashboard_server",
        lambda snapshots, port=0: (_FakeServer(), fake_ctx, "tok"),
    )
    monkeypatch.setattr(dashboard_server, "bootstrap_launch_url", lambda c, t: "u")
    monkeypatch.setattr(
        dashboard_server, "capture_initial_scan_provenance", fake_provenance
    )
    monkeypatch.setattr(dashboard_server, "publish_check_suite_scan", fake_publish)
    monkeypatch.setattr(project_run, "_capture_artifact_snapshots", fake_snapshots)
    monkeypatch.setattr(suites, "run_workflow_suite", fake_suite)
    monkeypatch.setattr(
        cli_module, "_write_dashboard_descriptor", lambda ctx: w.base / "d.json"
    )
    monkeypatch.setattr(cli_module, "_remove_dashboard_descriptor", lambda p: None)
    monkeypatch.chdir(w.root)

    result = CliRunner().invoke(cli, ["dashboard", "alias", "--no-open", "--json"])

    assert result.exit_code == 0, result.output
    assert done.is_set()
    record_root = Path(resolve_project(w.proj, data_root=w.data_root)["root"])
    assert received == {
        "provenance": record_root,
        "snapshots": record_root,
        "suite": record_root,
        "publish": record_root,
    }


def test_t08_server_instructions_state_the_root_rule() -> None:
    """B20 / §3.9: the server instructions state the §3.2 rule for `project`
    and `project_id`."""
    from rush.mcp import build_server_instructions

    assert (
        "Path resolution (§3.2): relative paths resolve against the server-start "
        "working directory captured once at startup; a `project` (or existing "
        "`project_id`) argument declares a registered root that relative paths "
        "resolve against instead."
    ) in build_server_instructions()


@pytest.mark.parametrize("operation", ["scan_start", "scan_resume", "rescan"])
def test_t08_dashboard_events_visible_between_release_and_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """T8.md §4: T037 releases a dashboard scan's admission before
    `_publish_scan_snapshot` ingests its candidate events. With that publish
    ingest held open after the release, `/events` must still return the
    attempt's candidate events (the route catches up the latest attempt whose
    publication is pending), for scan_start, scan_resume and rescan alike."""
    import threading

    from rush.dashboard import state
    from tests.test_dashboard_missing_routes import _events, _seed_one_run
    from tests.test_dashboard_scan_actions import (
        _action,
        _grant_all,
        _scans,
        _wait_until,
    )

    released: list[str] = []
    held = threading.Event()
    resume = threading.Event()
    real_ingest = state.MutationLedger.ingest_attempt_events
    real_submit = state.PendingOutcomeQueue.submit

    def spy_submit(self, slot_id, *, operation_id="", payload=None):
        result = real_submit(self, slot_id, operation_id=operation_id, payload=payload)
        released.append(str((payload or {}).get("attempt_id")))
        return result

    def spy_ingest(self, project_id, run_id, attempt_id, events):
        publishing = "_run_supervised" in threading.current_thread().name
        if publishing and str(attempt_id) in released and not held.is_set():
            held.set()
            resume.wait(timeout=60)
        return real_ingest(self, project_id, run_id, attempt_id, events)

    server, base_url, cookie, csrf, project_id, _root, run_id = _seed_one_run(
        tmp_path, monkeypatch
    )

    def _seed_published() -> bool:
        status, scans = _scans(base_url, project_id, cookie, run_id=run_id)
        return (
            status == 200
            and scans["data"]["active_run_id"] is None
            and scans["data"]["publication"] != "not_yet"
        )

    _wait_until(_seed_published, timeout=60.0)
    monkeypatch.setattr(state.PendingOutcomeQueue, "submit", spy_submit)
    monkeypatch.setattr(state.MutationLedger, "ingest_attempt_events", spy_ingest)
    try:
        if operation == "scan_start":
            status, body = _action(
                base_url, project_id, cookie, csrf, operation="provision_plan"
            )
            assert status == 200
            arguments = {"plan_id": body["data"]["scan_plan"]["plan_id"]}
        else:
            arguments = {"run_id": run_id}
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation=operation,
            arguments=arguments,
            grants=_grant_all(),
        )
        assert status == 202, body
        attempt_id = str(body["data"]["attempt_id"])
        attempt_run_id = str(body["data"]["run_id"])
        _wait_until(held.is_set, timeout=60.0)
        assert attempt_id in released

        events: list[dict] = []
        after = "0"
        while True:
            status, events_body = _events(base_url, project_id, cookie, after=after)
            assert status == 200
            events.extend(events_body["data"]["events"])
            if not events_body["data"]["has_more"]:
                break
            after = str(events_body["data"]["after"])
        from rush.workflows.project_run import load_scan_events

        durable = load_scan_events(_root, attempt_run_id, attempt_id)["events"]
        assert durable
        visible = [
            e["payload"]
            for e in events
            if e["event_kind"] == "candidate" and e["attempt_id"] == attempt_id
        ]
        assert visible == durable
    finally:
        resume.set()
        server.shutdown()
        server.server_close()
