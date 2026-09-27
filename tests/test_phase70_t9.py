"""Phase 70 T9 -- Distinguish invalid input, empty scope, and clean work.

Test matrix for `.scratch/phase-70-design-gate/W2-T9-T17.md` (## T9,
section 6) and the T9 packet in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`.

T9 is not implemented in this worktree (T8 is also not landed here, per
the design brief's own G-A finding, but no T9 case below depends on T8's
unbuilt interface -- see the per-test RED-reason docstrings). Probed
against real current code before writing every assertion below:

- Every catalog CLI route (`lint`/`review`/`format`/`sbom`/`check`/
  `audit`/`gate`) still declares `@click.argument("path",
  type=click.Path(exists=True, ...))`, so a missing target is rejected by
  Click itself (a bare `UsageError`, not the required `ToolResult` JSON).
- `InvocationExecutor.execute` has no target-existence check at all before
  calling the handler (confirmed by reading `src/rush/invocation/
  executor.py` in full).
- `resolve_target` (`src/rush/invocation/targets.py`) marks a missing
  target `state="deleted"` without raising, so an MCP wrapper or a scan
  candidate silently runs the real tool against a non-existent path.
- `LintTool.run` never attaches `metadata` at all (`src/rush/tools/
  lint.py`), so `metadata.scope` does not exist yet for the no-supported-
  files case.
- `theme.render_result` (`src/rush/theme.py`) hardcodes a glyph per tool
  name (lint always renders `✓` regardless of status) and puts the
  status word inside an unclosed `[{status}.{status}]` Rich markup tag
  that never renders as literal text; probed directly:
  `render_result({"tool": "lint", "status": "skipped", "summary": "lint
  [ruff]: 1 issue(s)", "findings": []})` prints
  `'✓   lint : 1 issue(s)\n'` -- no status word, a false-success
  glyph, and the `[ruff]` bracket silently dropped.
- `resolve_invocation` raises an uncaught `ValueError: lstat: embedded
  null character in path` for a NUL byte in an MCP path (probed directly
  through `make_tool_wrapper`), instead of a handled `TARGET_INVALID`
  error result.
- `plan_scan` (`src/rush/workflows/project_run.py`) never validates
  `targets[tool]["path"]` before staging a plan, and `_execute_candidate`
  has no equivalent check either, so a candidate run against a target
  deleted after planning still calls the real tool and returns `skipped`/
  `unavailable`, never `failed`.

Every "must fail today" case below traces to one of the above, confirmed
by reading the real file, not inferred.

Every OS-level subprocess call every engine makes routes through
`subprocess.run`/`subprocess.Popen` inside `rush.runtime.subprocesses`
(`ruff.py`, `eslint.py`, etc. each bind their own `run_subprocess` name at
import time via `from ..tools.common import run_subprocess`, so patching
only `rush.tools.common.run_subprocess` would miss those already-bound
references) -- so the "zero engine calls" guarantee below patches the
stdlib `subprocess` module directly, which every one of those modules
shares as the same object.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.console import Console

from rush import theme
from rush.cli import cli
from rush.discovery.git import get_changed_files, get_files_since, get_staged_files
from rush.mcp_support.tool_registry import make_custom_wrapper, make_tool_wrapper
from rush.permissions import ExecutionPermissions
from rush.tools import LintTool
from rush.tools.common import resolve_binary
from rush.workflows import project_run
from rush.workflows.project_run import (
    ScanInvalidRequestError,
    execute_scan,
    plan_scan,
)
from rush.workflows.projects import register_project
from rush.workflows.suites import CHECK_SUITE, run_workflow_suite

pytestmark = pytest.mark.filterwarnings("ignore")


def _install_subprocess_spy(
    monkeypatch: pytest.MonkeyPatch, *, block: bool = True
) -> list[tuple[str, ...]]:
    """Record (and, by default, reject) any real OS-level subprocess call for
    the duration of a test. See module docstring for why this patches the
    stdlib `subprocess` module directly rather than a Rush-side import.

    W2 finding 26: children are counted once, at `Popen.__init__`, which also
    catches `subprocess.run` (it constructs a `Popen`) and any
    `from subprocess import Popen` binding. `subprocess.run` is patched too,
    as a pass-through, so a module-attribute rebinding cannot bypass the
    count. `block=False` is the granted positive control: the same spy
    records and then lets the real child start."""
    calls: list[tuple[str, ...]] = []
    real_init = subprocess.Popen.__init__
    real_run = subprocess.run

    def _init_spy(self, argv, *args, **kwargs):
        recorded = tuple(argv) if isinstance(argv, (list, tuple)) else (str(argv),)
        calls.append(tuple(str(part) for part in recorded))
        if block:
            raise AssertionError(f"unexpected engine subprocess call: {recorded!r}")
        real_init(self, argv, *args, **kwargs)

    def _run_spy(*args, **kwargs):
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", _init_spy)
    monkeypatch.setattr(subprocess, "run", _run_spy)
    return calls


def _parse_json(output: str) -> dict | None:
    try:
        return json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return None


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "existing.py").write_text("x = 1\n")
    return root


# --- S9.1/S9.2/S9.3: missing target across every CLI/MCP transport --------

_CATALOG_TRANSPORTS = {
    "cli-catalog": "lint",
    "cli-review": "review",
    "cli-format": "format",
    "cli-sbom": "sbom",
}
_SUITE_TRANSPORTS = {
    "cli-check": "check",
    "cli-audit": "audit",
    "cli-gate": "gate",
}


@pytest.mark.parametrize("transport", sorted(_CATALOG_TRANSPORTS))
def test_t09_no_work_is_not_clean_catalog_cli(
    transport: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: every catalog command still uses
    `click.Path(exists=True)`, so Click rejects the missing target itself
    (a `UsageError`, not JSON) before the command body -- and therefore
    before any `InvocationExecutor` validation -- ever runs. `result.output`
    is Click's own error text, so `_parse_json` returns `None` and the
    first assertion fails."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / "missing.py"
    command = _CATALOG_TRANSPORTS[transport]

    result = CliRunner().invoke(cli, [command, str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == command
    assert parsed["status"] == "error"
    assert parsed["findings"] == []
    assert "missing.py" in parsed["summary"]
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert parsed["metadata"]["execution"]["disposition"] == "not_run"
    assert parsed["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": "target_not_found",
    }
    assert calls == []


@pytest.mark.parametrize("transport", sorted(_SUITE_TRANSPORTS))
def test_t09_no_work_is_not_clean_suite_cli(
    transport: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: same Click `exists=True` gate as the catalog commands
    (`check_cmd`/`audit_cmd`/`gate_cmd` in `cli.py` all declare it), so a
    missing target never reaches `_run_suite_cli`; `result.output` is
    Click's error text, not the required aggregate error JSON."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / "missing.py"
    command = _SUITE_TRANSPORTS[transport]

    result = CliRunner().invoke(cli, [command, str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, (
        f"expected aggregate ToolResult JSON, got: {result.output!r}"
    )
    assert parsed["tool"] == command
    assert parsed["status"] == "error"
    assert parsed["findings"] == []
    assert calls == []


def test_t09_mcp_missing_target_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S9.3. RED reason: `resolve_target` marks a missing target
    `state="deleted"` without raising, so `LintTool.run` executes against
    the (nonexistent) path directly and returns `skipped` ("no Python/JS/TS
    files found"), never `error`."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    monkeypatch.chdir(root)
    wrapper = make_tool_wrapper(LintTool())

    result = wrapper(path="src/missing.py")

    assert result["tool"] == "lint"
    assert result["status"] == "error"
    assert result["findings"] == []
    assert "missing.py" in result["summary"]
    assert result["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert result["metadata"]["execution"]["disposition"] == "not_run"
    assert result["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": "target_not_found",
    }
    assert calls == []


# --- S9.4: missing/deleted target in a project scan ------------------------


def test_t09_scan_plan_rejects_missing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: `plan_scan` (`src/rush/workflows/project_run.py`) never
    inspects `targets[tool_id]["path"]` for existence/containment before
    staging -- it stages the plan unconditionally. Confirmed by reading
    `plan_scan` in full: the only `targets` checks are unknown-tool-id and
    "must be an object"."""
    calls = _install_subprocess_spy(monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("import os\n")
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)

    with pytest.raises(ScanInvalidRequestError) as exc_info:
        plan_scan(
            record.project_id,
            targets={"lint": {"path": "missing.py"}},
            data_root=data_root,
        )

    assert "missing.py" in str(exc_info.value)
    assert not list((root / ".rush" / "scan_plans").glob("*"))
    assert calls == []


def test_t09_scan_run_fails_candidate_when_target_deleted_after_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: `_execute_candidate` has no target-existence check
    before calling the real tool. With the target deleted after planning,
    `LintTool.run` runs against the missing path and returns `skipped`
    ("no Python/JS/TS files found"), which `_execute_candidate` maps to
    outcome `unavailable`, never `failed` with a `TARGET_NOT_FOUND` child.
    Confirmed by reading `_execute_candidate` in full: it only special-
    cases `status in {"error", "skipped"}` after the tool has already run,
    never before.

    No subprocess spy here: `execute_scan` -> `_finalize_attempt` always
    shells out to real `git` for the run manifest's source-identity section
    (`_git_link`/`_source_identity`), independent of any candidate's
    outcome -- that is legitimate run-manifest bookkeeping, not one of the
    "zero engine calls" this case is actually about (the lint *engine*,
    ruff, must never run against the deleted target)."""
    root = tmp_path / "project"
    root.mkdir()
    target = root / "mod.py"
    target.write_text("import os\n")
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(project_run, "ALL_TOOLS", [LintTool()])
    record = register_project(root, data_root=data_root)

    plan = plan_scan(
        record.project_id,
        targets={"lint": {"path": "mod.py"}},
        data_root=data_root,
    )
    target.unlink()

    run = execute_scan(plan, data_root=data_root)

    lint_result = next(
        cr for cr in run.candidate_results if cr.candidate.candidate_id == "lint"
    )
    assert lint_result.outcome == "failed"
    assert lint_result.result["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"


# --- S9.9: malformed path over MCP -----------------------------------------


def test_t09_mcp_malformed_path_returns_target_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED reason: `resolve_invocation` -> `resolve_target` calls
    `contained_path.exists()` on a path containing an embedded NUL byte,
    which raises an uncaught `ValueError: lstat: embedded null character
    in path` -- probed directly against `make_tool_wrapper(LintTool())`.
    Not RED-via-T8: this is `resolve_target`'s own pre-existing Phase 57
    code, unrelated to T8's unbuilt interface."""
    calls = _install_subprocess_spy(monkeypatch)
    wrapper = make_tool_wrapper(LintTool())

    result = wrapper(path="bad\x00path")

    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "TARGET_INVALID"
    assert calls == []


# --- Adversarial missing-target shapes (all via the CLI catalog route) -----


def test_t09_missing_nested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: identical to `test_t09_no_work_is_not_clean_catalog_cli`
    but the *directory* is also missing, not just the file -- same Click
    `exists=True` gate blocks it before any JSON is produced."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "nosuchdir" / "deeper" / "missing.py"

    result = CliRunner().invoke(cli, ["lint", str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert calls == []


def test_t09_whitespace_padded_missing_name_preserved_literally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: same Click gate; additionally checks that once R9.1
    lands, the padded literal name must survive into the summary
    untouched (T8's own literal-preservation rule, reused here for a name
    that never even needs T8's helper to fail this way -- Click blocks it
    at the same boundary as any other missing path)."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / "  weird name .py"

    result = CliRunner().invoke(cli, ["lint", str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert "  weird name .py" in parsed["summary"]
    assert calls == []


def test_t09_dotdot_escaping_to_a_missing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: same Click gate. Not RED-via-T8: `PhysicalRoot.
    open_contained` (`src/rush/io/physical_paths.py`) already does a
    pre-existing Phase 57 component-wise containment walk for `..`,
    unrelated to T8's unbuilt root-normalization helper -- the gap here is
    purely R9.1 (no validation before the handler runs), same as every
    other missing-target case."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / ".." / "src" / "missing.py"

    result = CliRunner().invoke(cli, ["lint", str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert calls == []


def test_t09_cli_staged_missing_target_no_git_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: same Click `exists=True` gate as every other catalog
    case -- `result.output` is Click's error text, not the required JSON,
    so the JSON-shape assertion fails today even though (both today and
    after R9.1) zero git/engine subprocesses ever run for this missing
    target, since Click rejects it before the command body executes."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / "missing.py"

    result = CliRunner().invoke(cli, ["lint", str(missing), "--staged", "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert calls == []


# --- S9.5: existing target, no supported files -> skipped with scope ------


@pytest.mark.parametrize(
    "make_dir",
    [
        pytest.param(lambda d: None, id="empty-directory"),
        pytest.param(
            lambda d: (d / "notes.txt").write_text("hello\n"), id="txt-only-directory"
        ),
    ],
)
def test_t09_no_supported_files_scope_metadata(make_dir, tmp_path: Path) -> None:
    """RED reason: `LintTool.run`'s no-targets branch
    (`src/rush/tools/lint.py::run`) returns `_build_skipped_result` with no
    `metadata` key at all -- confirmed by reading the whole function.
    `result["metadata"]` raises `KeyError` today. This is the existing
    `skipped`/exit-0 characterization (unchanged: no new failure is
    fabricated); only the `metadata.scope` shape is new."""
    target_dir = tmp_path / "empty"
    target_dir.mkdir()
    make_dir(target_dir)

    result = LintTool().run(target_dir)

    assert result["status"] == "skipped"
    assert result["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": "no_supported_targets",
        "matched_file_count": 0,
        "consumed_file_count": 0,
    }


# --- S9.6: engine absent -> skipped -----------------------------------------


def test_t09_engine_absent_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED reason: `run_engine` (`src/rush/runtime/subprocesses.py`) already
    builds a per-engine skipped result with summary `"{binary} not on PATH
    (install: ...)"` when the engine binary is absent (checked via
    `rush.tools.common.engine_on_path`, looked up dynamically off
    `sys.modules`) -- but `_run_selected_engines`/`_assemble_lint_result`
    (`src/rush/tools/lint.py`) never surface that per-engine summary text.
    `engines_used.append(name)` runs unconditionally once a name has
    matching files, regardless of the engine's own returned status, so the
    top-level result becomes `"lint [ruff]: skipped"` -- confirmed by
    reading both functions and tracing the call: no "not on PATH" text
    anywhere in the final summary."""
    (tmp_path / "mod.py").write_text("import os\n")
    monkeypatch.setattr("rush.tools.common.engine_on_path", lambda _name: False)

    result = LintTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "not on PATH" in result["summary"]


# --- S9.7: clean analysis -> ok (keep-green guard) --------------------------


def test_t09_clean_analysis_is_ok(tmp_path: Path) -> None:
    """Keep-green guard: a real clean ruff pass already returns `ok` today
    (`_assemble_lint_result`'s `status == "ok" and n_findings > 0` branch
    never triggers with zero findings); T9 must not regress this."""
    assert resolve_binary("ruff") is not None, "ruff is a required dev dependency"
    (tmp_path / "clean.py").write_text("x = 1\n")

    result = LintTool().run(tmp_path)

    assert result["status"] == "ok"


# --- S9.8: human output shows status, never a false glyph, escapes text ---


def _render(monkeypatch: pytest.MonkeyPatch, result: dict) -> str:
    buf = io.StringIO()
    test_console = Console(
        file=buf, force_terminal=False, width=200, theme=theme.RUSH_THEME
    )
    monkeypatch.setattr(theme, "console", lambda: test_console)
    theme.render_result(result)
    return buf.getvalue()


def test_t09_human_output_shows_status_word_not_a_false_glyph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED reason: probed directly -- `render_result({"tool": "lint",
    "status": "skipped", ...})` prints `'✓   lint : 1 issue(s)\n'`:
    the glyph is hardcoded per-tool (always `✓` for lint) regardless
    of status, and the status word never appears as literal text because
    `f"[{status}.{status}]"` is unclosed Rich markup, not printed text."""
    output = _render(
        monkeypatch,
        {
            "tool": "lint",
            "status": "skipped",
            "summary": "lint [ruff]: 1 issue(s)",
            "findings": [],
        },
    )

    assert "skipped" in output
    assert "✓" not in output


def test_t09_human_output_escapes_bracketed_summary_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED reason: probed directly -- the same call above drops the
    `[ruff]` segment of the summary entirely (Rich treats it as an
    unmatched/invalid markup tag and swallows it), leaving `"lint :
    1 issue(s)"`. The literal bracketed text must survive."""
    output = _render(
        monkeypatch,
        {
            "tool": "lint",
            "status": "ok",
            "summary": "lint [ruff]: clean",
            "findings": [],
        },
    )

    assert "[ruff]" in output


def test_t09_human_output_escapes_finding_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S9.8 / design step 6: every finding cell is rendered literally --
    engine text can never inject Rich markup into the table."""
    output = _render(
        monkeypatch,
        {
            "tool": "lint",
            "status": "warn",
            "summary": "lint [ruff]: 1 issue(s)",
            "findings": [
                {
                    "path": "[red]a.py",
                    "line": 1,
                    "rule": "[bold]F401",
                    "severity": "warn",
                    "message": "unused [os] import",
                }
            ],
        },
    )

    assert "warn" in output
    assert "[red]a.py" in output
    assert "[bold]F401" in output
    assert "unused [os] import" in output


# --- W2 T9 amendment 6: the spy's granted positive control -----------------


def test_t09_spawn_spy_positive_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 6 (finding 26): the same spy every zero-spawn assertion in
    this file uses records at least one child when an engine really runs --
    so a `calls == []` elsewhere is evidence, not a blind spy."""
    assert resolve_binary("ruff") is not None, "ruff is a required dev dependency"
    (tmp_path / "clean.py").write_text("x = 1\n")
    calls = _install_subprocess_spy(monkeypatch, block=False)

    result = LintTool().run(tmp_path)

    assert result["status"] == "ok"
    assert len(calls) >= 1


# --- W2 T9 amendment 1: malformed (NUL) input -> TARGET_INVALID ------------


def _assert_target_invalid(result: dict, calls: list[tuple[str, ...]]) -> None:
    assert result["status"] == "error", result
    assert result["findings"] == []
    assert result["metadata"]["error"]["code"] == "TARGET_INVALID"
    assert result["metadata"]["execution"]["disposition"] == "not_run"
    assert calls == []


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("bad\x00path", id="nul-path"),
        pytest.param("nosuchdir/a\x00b.py", id="nul-after-missing-component"),
    ],
)
def test_t09_cli_nul_path_is_target_invalid(
    raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 1 `cli-nul-path`: exit 2, TARGET_INVALID JSON, zero spawns,
    no traceback (the only exception is Click's own `SystemExit`)."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(cli, ["lint", raw, "--json"])

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    _assert_target_invalid(parsed, calls)


def test_t09_mcp_nul_after_missing_component_is_target_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 1: a NUL after a missing component never reaches `lstat`
    during the walk (the walk stops at the first missing component), so it
    must be rejected before walking."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    monkeypatch.chdir(root)

    result = make_tool_wrapper(LintTool())(path="nosuchdir/a\x00b.py")

    _assert_target_invalid(result, calls)


class _FilesProbe:
    """A standard-wrapper tool with a `files` list, recording every call."""

    name = "t9-files-probe"
    mcp_description = "T9 files probe."

    def __init__(self) -> None:
        self.calls: list[tuple[Path, list[str] | None]] = []

    def __call__(self, path: Path, files: list[str] | None = None) -> dict:
        self.calls.append((path, files))
        return {"tool": self.name, "status": "ok", "summary": "", "findings": []}


def test_t09_mcp_standard_wrapper_nul_files_member_is_target_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 1 `mcp-nul-files-member` (standard wrapper): `select_member`
    rejects a NUL member; the handler never runs."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    monkeypatch.chdir(root)
    probe = _FilesProbe()

    result = make_tool_wrapper(probe)(path=".", files=["src/a\x00b.py"])

    _assert_target_invalid(result, calls)
    assert probe.calls == []


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"path": "src/a\x00b.py"}, id="nul-path"),
        pytest.param({"path": ".", "files": ["a\x00b.py"]}, id="nul-files-member"),
    ],
)
def test_t09_mcp_custom_wrapper_nul_is_target_invalid(
    kwargs: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 1 (both wrappers): the custom wrapper's path walk and the
    `_resolve_targets` fallback (its `files` members bypass the T8 member
    walk) both surface TARGET_INVALID, never a `ValueError` traceback."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    monkeypatch.chdir(root)
    handled: list[object] = []

    def probe(path: str, files: list[str] | None = None) -> dict:
        handled.append(path)
        return {"tool": "t9-custom", "status": "ok", "summary": "", "findings": []}

    result = make_custom_wrapper(probe, "t9-custom")(**kwargs)

    _assert_target_invalid(result, calls)
    assert handled == []


# --- W2 T9 amendment 2: remaining _run_tool routes lose exists=True --------


@pytest.mark.parametrize(
    ("argv_prefix", "tool"),
    [
        pytest.param(["attest"], "attest", id="cli-attest"),
        pytest.param(["license-matrix"], "license-matrix", id="cli-license-matrix"),
        pytest.param(["iam-audit"], "iam-audit", id="cli-iam-audit"),
        pytest.param(["benchmark", "check"], "benchmark", id="cli-benchmark-check"),
    ],
)
def test_t09_remaining_run_tool_routes_missing_target(
    argv_prefix: list[str],
    tool: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Amendment 2 (finding 19): canonical JSON error, exit 2, zero spawns."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)
    missing = root / "src" / "missing.py"

    result = CliRunner().invoke(cli, [*argv_prefix, str(missing), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == tool
    assert parsed["status"] == "error"
    assert parsed["findings"] == []
    assert "missing.py" in parsed["summary"]
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert parsed["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": "target_not_found",
    }
    assert calls == []


# --- W2 T9 amendment 3: tdd validates its target ---------------------------


@pytest.mark.parametrize(
    "relative",
    ["nope/tests", "nope/missing_test.py", "nope/missing.py"],
)
def test_t09_tdd_missing_target(
    relative: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 3 (finding 20): `tdd` is `workflow` category but sets
    `validates_target`, so a missing target is TARGET_NOT_FOUND, never the
    name-based `ok` ("test suite verified") it returned before."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)

    result = CliRunner().invoke(cli, ["tdd", str(root / relative), "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "tdd"
    assert parsed["status"] == "error"
    assert parsed["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert calls == []


# --- W2 T9 amendments 4/5: git selections and workspaces -------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t9@example.invalid",
            "-c",
            "user.name=t9",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _committed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        pytest.param(["--staged"], "no_staged_files", id="cli-staged-empty-json"),
        pytest.param(["--changed"], "no_changed_files", id="cli-changed-empty-json"),
        pytest.param(
            ["--since", "HEAD"], "no_files_since_ref", id="cli-since-empty-json"
        ),
    ],
)
def test_t09_empty_git_selection_is_skipped_toolresult(
    flags: list[str], reason: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 4 (finding 18): an empty selection is a skipped ToolResult
    (exit 0, exact scope reason), not plain text. Only `git` may spawn."""
    repo = _committed_repo(tmp_path)
    calls = _install_subprocess_spy(monkeypatch, block=False)

    result = CliRunner().invoke(cli, ["lint", str(repo), *flags, "--json"])

    assert result.exit_code == 0, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    assert parsed["status"] == "skipped"
    assert parsed["findings"] == []
    assert parsed["metadata"]["scope"] == {
        "version": 1,
        "kind": "files",
        "coverage": "none",
        "reason": reason,
        "matched_file_count": 0,
    }
    assert calls, "the selection must really consult git"
    assert all(Path(call[0]).name == "git" for call in calls), calls


def test_t09_staged_selection_analyzes_only_staged_files(tmp_path: Path) -> None:
    """Amendment 5 `cli-staged-nonempty`: a non-empty selection is what gets
    analyzed -- the unstaged sibling with the same issue is never reported."""
    assert resolve_binary("ruff") is not None, "ruff is a required dev dependency"
    repo = _committed_repo(tmp_path)
    (repo / "staged.py").write_text("import os\n")
    (repo / "unstaged.py").write_text("import os\n")
    _git(repo, "add", "staged.py")

    result = CliRunner().invoke(cli, ["lint", str(repo), "--staged", "--json"])

    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    assert parsed["findings"], parsed
    assert {Path(str(f["path"])).name for f in parsed["findings"]} == {"staged.py"}


def _monorepo_with_selection(tmp_path: Path, kind: str) -> Path:
    """A repo with committed `pkg_a/a.py`, `pkg_b/b.py` and `top.py`, then one
    lint-dirty change per location selected by `kind` (staged, changed, or
    committed since `HEAD~1`)."""
    repo = tmp_path / "mono"
    (repo / "pkg_a").mkdir(parents=True)
    (repo / "pkg_b").mkdir()
    _git(repo, "init", "-q")
    files = [repo / "pkg_a" / "a.py", repo / "pkg_b" / "b.py", repo / "top.py"]
    for file in files:
        file.write_text("x = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    for file in files:
        file.write_text("import os\n")
    if kind in ("staged", "since"):
        _git(repo, "add", ".")
    if kind == "since":
        _git(repo, "commit", "-q", "-m", "change")
    return repo


_SELECTORS = {
    "staged": (lambda target: get_staged_files(target), ["--staged"]),
    "changed": (lambda target: get_changed_files(target), ["--changed"]),
    "since": (lambda target: get_files_since(target, "HEAD~1"), ["--since", "HEAD~1"]),
}


@pytest.mark.parametrize("kind", sorted(_SELECTORS))
def test_t09_git_selection_on_subfolder_is_exactly_that_folder(
    kind: str, tmp_path: Path
) -> None:
    """Fix round 1: git reports repo-root-relative paths. A subfolder target
    selects exactly its own changed files -- never a sibling folder's, never a
    file above it -- and the repo root still selects every changed file."""
    repo = _monorepo_with_selection(tmp_path, kind)
    select, _ = _SELECTORS[kind]
    real = repo.resolve()

    assert select(repo / "pkg_a") == [real / "pkg_a" / "a.py"]
    assert select(repo / "pkg_b") == [real / "pkg_b" / "b.py"]
    assert sorted(select(repo)) == sorted(
        [real / "pkg_a" / "a.py", real / "pkg_b" / "b.py", real / "top.py"]
    )


@pytest.mark.parametrize("kind", sorted(_SELECTORS))
def test_t09_cli_git_selection_on_subfolder_analyzes_only_that_folder(
    kind: str, tmp_path: Path
) -> None:
    """Fix round 1, CLI: `rush lint <repo>/pkg_a --<selection>` reports only
    `pkg_a`'s changed file (it previously selected nothing: a skipped
    `no_*_files` result)."""
    assert resolve_binary("ruff") is not None, "ruff is a required dev dependency"
    repo = _monorepo_with_selection(tmp_path, kind)
    _, flags = _SELECTORS[kind]

    result = CliRunner().invoke(cli, ["lint", str(repo / "pkg_a"), *flags, "--json"])

    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["metadata"]["scope"]["matched_file_count"] == 1, parsed
    assert {Path(str(f["path"])).name for f in parsed["findings"]} == {"a.py"}


def test_t09_malformed_since_ref_is_target_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hostile `--since` ref (rejected by `validate_git_ref`) is malformed
    input: TARGET_INVALID JSON, exit 2, no traceback, no git or engine call."""
    repo = _committed_repo(tmp_path)
    calls = _install_subprocess_spy(monkeypatch)

    result = CliRunner().invoke(
        cli, ["lint", str(repo), "--since=--output=/tmp/x", "--json"]
    )

    assert result.exit_code == 2, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    _assert_target_invalid(parsed, calls)


def test_t09_unknown_workspace_is_target_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 5 `cli-workspace-not-found-json`: TARGET_NOT_FOUND JSON with
    reason `workspace_not_found` and the workspace name, exit 2."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)

    result = CliRunner().invoke(cli, ["lint", str(root), "-w", "nope", "--json"])

    assert result.exit_code == 2, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    assert parsed["status"] == "error"
    assert parsed["findings"] == []
    error = parsed["metadata"]["error"]
    assert error["code"] == "TARGET_NOT_FOUND"
    assert error["reason"] == "workspace_not_found"
    assert error["workspace"] == "nope"
    assert calls == []


def _js_monorepo(tmp_path: Path, names: tuple[str, ...]) -> Path:
    root = tmp_path / "mono"
    root.mkdir()
    (root / "package.json").write_text(json.dumps({"workspaces": ["packages/*"]}))
    for name in names:
        pkg = root / "packages" / name
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({"name": name}))
    return root


def test_t09_all_workspaces_runs_once_per_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 5 `cli-all-workspaces`: one child per discovered workspace
    (the flag was previously never read, so one single target ran)."""
    monkeypatch.setattr("rush.tools.lint.engine_on_path", lambda _name: False)
    root = _js_monorepo(tmp_path, ("alpha", "beta"))

    result = CliRunner().invoke(cli, ["lint", str(root), "--all-workspaces", "--json"])

    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    children = parsed["metadata"]["children"]
    assert sorted(child["workspace"] for child in children) == ["alpha", "beta"]
    assert all(child["tool"] == "lint" for child in children)


def test_t09_all_workspaces_with_zero_workspaces_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 5: zero discovered workspaces is `skipped` with reason
    `no_workspaces`, exit 0 -- never a clean run of the whole tree."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)

    result = CliRunner().invoke(cli, ["lint", str(root), "--all-workspaces", "--json"])

    assert result.exit_code == 0, result.output
    parsed = _parse_json(result.output)
    assert parsed is not None, f"expected ToolResult JSON, got: {result.output!r}"
    assert parsed["tool"] == "lint"
    assert parsed["status"] == "skipped"
    assert parsed["metadata"]["scope"]["reason"] == "no_workspaces"
    assert parsed["metadata"]["scope"]["coverage"] == "none"
    assert calls == []


# --- Design steps 4/5: suite accounting and scan containment ---------------


def test_t09_suite_never_counts_a_not_run_step_as_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design step 4: a step the executor refused (`disposition=not_run`) is
    retained as an error child but never listed in `executed_tools`."""
    calls = _install_subprocess_spy(monkeypatch)
    root = _project_root(tmp_path)

    result = run_workflow_suite(
        CHECK_SUITE,
        root / "src" / "missing.py",
        ExecutionPermissions(),
        fail_fast=False,
        invocation_start_cwd=root,
    )

    assert result["status"] == "error"
    assert result["metadata"]["executed_tools"] == ()
    assert [c["status"] for c in result["metadata"]["children"]] == ["error"] * len(
        CHECK_SUITE.tool_sequence
    )
    assert "executed 0 tool(s)" in result["summary"]
    assert calls == []


def test_t09_scan_plan_rejects_target_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design step 5: a plan target must be contained in the project root
    (normalized with the T8 walk), not merely exist somewhere."""
    calls = _install_subprocess_spy(monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("import os\n")
    (tmp_path / "outside.py").write_text("import os\n")
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)

    with pytest.raises(ScanInvalidRequestError) as exc_info:
        plan_scan(
            record.project_id,
            targets={"lint": {"path": "../outside.py"}},
            data_root=data_root,
        )

    assert "outside.py" in str(exc_info.value)
    assert not (root / ".rush" / "scan_plans").exists() or not list(
        (root / ".rush" / "scan_plans").glob("*")
    )
    assert calls == []
