"""T27 fix round 1: renderer, producer and route defects found in review."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import runpy
import sqlite3
import sys
from pathlib import Path
from typing import Any, Literal

import click
import pytest
from click.testing import CliRunner

from rush import theme
from rush.cli import cli
from rush.tools.memory import MemoryOperation


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(theme, "_shared_console", None)
    return home


def _render(result: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> str:
    theme.render_result(result)
    return capsys.readouterr().out


# --- item 1: analyses show scope, engines, findings and coverage -------------


def test_analysis_renders_scope_engines_and_coverage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {
            "tool": "lint",
            "status": "warn",
            "summary": "lint: 1 finding",
            "findings": [
                {"path": "a.py", "line": 1, "rule": "F401", "message": "unused"}
            ],
            "metadata": {
                "scope": {
                    "version": 1,
                    "kind": "file",
                    "requested_targets": ["src", "tests"],
                    "matched_file_count": 3,
                    "consumed_file_count": 2,
                    "coverage": "partial",
                    "reason": "requested_files_not_consumed",
                },
                "engines": [
                    {"engine": "ruff", "status": "ok", "reason": None},
                    {
                        "engine": "eslint",
                        "status": "skipped",
                        "reason": "eslint not on PATH",
                    },
                ],
            },
        },
        capsys,
    )
    assert "scope: src, tests" in out
    assert "files: matched 3, consumed 2" in out
    assert "coverage: partial (requested_files_not_consumed)" in out
    assert "engine ruff: ok" in out
    assert "engine eslint: skipped (eslint not on PATH)" in out
    assert "F401" in out


def test_analysis_strict_v1_metadata_location_is_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {
            "tool": "lint",
            "status": "ok",
            "summary": "",
            "findings": [],
            "extensions": {
                "metadata": {
                    "scope": {"requested_targets": ["."], "coverage": "complete"},
                    "engines": [{"engine": "ruff", "status": "ok"}],
                }
            },
        },
        capsys,
    )
    assert "scope: ." in out
    assert "coverage: complete" in out
    assert "engine ruff: ok" in out


def test_analysis_missing_fields_render_unavailable_with_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {
            "tool": "lint",
            "status": "ok",
            "summary": "",
            "findings": [],
            "metadata": {
                "scope": {
                    "requested_targets": ["."],
                    "matched_file_count": None,
                    "consumed_file_count": None,
                    "coverage": "unavailable",
                    "reason": "tool_reports_no_file_consumption",
                }
            },
        },
        capsys,
    )
    assert (
        "files: matched unavailable: tool_reports_no_file_consumption, "
        "consumed unavailable: tool_reports_no_file_consumption"
    ) in out
    assert "coverage: unavailable (tool_reports_no_file_consumption)" in out
    assert "engines: unavailable: the producer reported no engine entries" in out

    bare = _render({"tool": "lint", "status": "ok", "summary": ""}, capsys)
    assert "scope: unavailable: the producer reported no scope" in bare
    assert "engines: unavailable: the producer reported no engine entries" in bare


# --- item 2: mutations render only the producer's changed/readback fields -----


def test_mutation_without_producer_fields_infers_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {
            "tool": "project",
            "status": "ok",
            "summary": "project add: ok",
            "raw": {"operation": "add", "data": {"project_id": "p1", "root": "/x"}},
        },
        capsys,
    )
    assert "changed: not reported by the producer" in out
    assert "readback: unavailable (the producer returned no readback record)" in out
    assert "readback project_id" not in out


def test_mutation_renders_changed_and_readback_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {
            "tool": "project",
            "status": "ok",
            "summary": "project add: ok",
            "raw": {
                "operation": "add",
                "data": {
                    "project_id": "p1",
                    "changed": {"project_id": "p1", "descriptor": "/x/.rush/p.json"},
                    "readback": {"project_id": "p1", "revision": 1},
                },
            },
        },
        capsys,
    )
    assert "changed: project_id=p1, descriptor=/x/.rush/p.json" in out
    assert "readback project_id: p1" in out
    assert "readback revision: 1" in out


def _project_add(project: Path) -> Any:
    return CliRunner().invoke(
        cli,
        [
            "project",
            "add",
            str(project),
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )


def test_project_add_twice_reports_unchanged(tmp_path: Path) -> None:
    project = tmp_path / "P"
    project.mkdir()
    first = _project_add(project)
    assert first.exit_code == 0, first.output
    assert "changed: project_id=" in first.output
    assert "readback project_id:" in first.output
    second = _project_add(project)
    assert second.exit_code == 0, second.output
    assert "unchanged: already registered" in second.output
    assert "\nchanged:" not in second.output
    assert "readback project_id:" in second.output


def test_project_add_json_carries_changed_and_readback(tmp_path: Path) -> None:
    project = tmp_path / "P"
    project.mkdir()
    first = json.loads(_project_add_json(project).output)
    data = first["raw"]
    assert data["changed"]["project_id"] == data["project_id"]
    assert data["readback"]["project_id"] == data["project_id"]
    assert "unchanged" not in data
    again = json.loads(_project_add_json(project).output)["raw"]
    assert again["unchanged"] == "already registered"
    assert "changed" not in again


def _project_add_json(project: Path) -> Any:
    return CliRunner().invoke(
        cli,
        [
            "project",
            "add",
            str(project),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )


# --- item 3: the findings count line always prints ----------------------------


def _findings(n: int) -> list[dict[str, Any]]:
    return [{"path": "a.py", "line": i, "rule": "R", "message": "m"} for i in range(n)]


def test_findings_count_line_prints_when_not_truncated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {"tool": "lint", "status": "warn", "summary": "", "findings": _findings(2)},
        capsys,
    )
    assert "2/2 findings" in out


def test_findings_truncated_prints_shown_total_and_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _render(
        {"tool": "lint", "status": "warn", "summary": "", "findings": _findings(60)},
        capsys,
    )
    assert "shown 50/60 findings; full list: rush" in out
    assert "--json" in out


# --- item 4: the copyable command is redacted ---------------------------------


def test_copyable_json_command_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123"
    monkeypatch.setattr(sys, "argv", ["rush", "lint", f"--token={secret}", secret])
    command = theme.copyable_json_command("lint")
    assert secret not in command
    assert "REDACTED" in command
    assert command.startswith("rush lint ")
    assert command.endswith("--json")


# --- item 5: AST merge keeps statement order and the docstring ----------------


_BASE = '"""Module doc."""\nimport os\n\n\ndef main():\n    return os.sep\n'


def test_ast_merge_keeps_main_guard_after_its_function(tmp_path: Path) -> None:
    from rush.hygiene.ast_merger import ASTConflictMerger

    a = _BASE + '\n\nif __name__ == "__main__":\n    RESULT = main()\n'
    b = _BASE + "\n\ndef helper():\n    return 1\n"
    ok, merged = ASTConflictMerger.merge_source_files(_BASE, a, b)
    assert ok, merged
    module = tmp_path / "merged.py"
    module.write_text(merged, encoding="utf-8")
    namespace = runpy.run_path(str(module), run_name="__main__")
    assert namespace["RESULT"] == __import__("os").sep
    assert namespace["helper"]() == 1
    assert ast.get_docstring(ast.parse(merged)) == "Module doc."


def test_ast_merge_still_refuses_conflicting_functions() -> None:
    from rush.hygiene.ast_merger import ASTConflictMerger

    a = _BASE + "\n\ndef f():\n    return 1\n"
    b = _BASE + "\n\ndef f():\n    return 2\n"
    ok, message = ASTConflictMerger.merge_source_files(_BASE, a, b)
    assert not ok
    assert "'f'" in message


# --- item 6: context persona read never mutates memory.db ---------------------


def test_context_persona_read_leaves_legacy_memory_db_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    rush_dir = project / ".rush"
    rush_dir.mkdir(parents=True)
    db = rush_dir / "memory.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE memory_artifacts (id TEXT, origin_kind TEXT, origin_id TEXT,"
        " symbol_ref TEXT, content TEXT, source TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO memory_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "a1",
            "preference",
            "persona_style",
            None,
            json.dumps({"value": "default"}),
            "legacy",
            "2026-01-01",
        ),
    )
    conn.commit()
    conn.close()
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    listing = sorted(p.name for p in rush_dir.iterdir())
    monkeypatch.chdir(project)
    result = CliRunner().invoke(cli, ["context", "persona"])
    assert result.exit_code == 0, result.output
    assert "Current persona style: default" in result.output
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert not (rush_dir / "cache").exists()
    assert sorted(p.name for p in rush_dir.iterdir()) == listing


# --- item 7: release check --json rows are a list -----------------------------


def test_release_check_json_rows_is_a_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["release", "check", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["rows"] == [{"manifest": "pyproject.toml", "version": "1.2.3"}]
    assert payload["total"] == 1


# --- item 8: CRLF survives terminal-safety escaping ---------------------------


def test_safe_terminal_text_keeps_crlf_and_escapes_lone_cr() -> None:
    assert theme.safe_terminal_text("a\r\nb") == "a\r\nb"
    assert theme.safe_terminal_text("a\rb") == "a\\x0db"
    assert theme.safe_terminal_text("a\r\r\nb") == "a\\x0d\r\nb"
    assert theme.safe_terminal_text("x\x1b[2J") == "x\\x1b[2J"


def test_echo_preserves_crlf_line_endings(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    from rush.cli_support.rendering import echo

    echo("line1\r\nline2\rX")
    out = capsysbinary.readouterr().out
    assert b"line1\r\nline2\\x0dX" in out


# --- item 2 (A2): memory and agent mutations report changed/readback ----------


def _memory(
    tmp_path: Path, operation: MemoryOperation, **kwargs: Any
) -> dict[str, Any]:
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    return dict(
        MemoryTool().run(
            tmp_path,
            operation=operation,
            permissions=ExecutionPermissions(cache_write=True),
            **kwargs,
        )
    )


def _memory_write(tmp_path: Path) -> dict[str, Any]:
    return _memory(
        tmp_path, "write", subject="preference", content={"value": 1}, source="unit"
    )


def _memory_request(
    tmp_path: Path,
    operation: MemoryOperation,
    artifact_id: str,
    version: int,
    **extra: Any,
) -> dict[str, Any]:
    return _memory(
        tmp_path,
        operation,
        request={
            "scope": "preference",
            "id": artifact_id,
            "expected_version": version,
            "apply": True,
            **extra,
        },
    )


def test_memory_write_reports_changed_and_readback(tmp_path: Path) -> None:
    result = _memory_write(tmp_path)
    raw = result["raw"]
    artifact_id = raw["id"]
    assert raw["changed"] == {artifact_id: {"revision": 1, "kind": "write"}}
    assert raw["readback"][artifact_id]["present"] is True
    assert raw["readback"][artifact_id]["revision"] == 1
    assert raw["readback"][artifact_id]["subject"] == "preference"
    assert "unchanged" not in raw


def test_memory_write_cli_renders_changed_and_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    out = CliRunner().invoke(
        cli,
        [
            "memory",
            "write",
            "preference",
            "unit",
            "--content",
            '{"value": 1}',
            "--allow-cache-write",
        ],
    )
    assert out.exit_code == 0, out.output
    assert re.search(r"changed: ([0-9a-f-]+)\.revision=1, \1\.kind=write", out.output)
    assert re.search(r"readback [0-9a-f-]+\.revision: 1", out.output)
    assert "not reported by the producer" not in out.output
    assert "readback: unavailable" not in out.output


def test_memory_promote_reports_changed_and_readback(tmp_path: Path) -> None:
    result = _memory(
        tmp_path,
        "promote",
        subject="preference",
        content={"value": 2},
        source="unit",
        user_stated=True,
    )
    raw = result["raw"]
    artifact_id = raw["artifact"]["id"]
    assert raw["promoted"] is True
    assert artifact_id in raw["changed"]
    revision = raw["changed"][artifact_id]["revision"]
    assert raw["readback"][artifact_id]["revision"] == revision
    assert "unchanged" not in raw


def test_memory_edit_archive_restore_delete_report_changed_and_readback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact_id = _memory_write(tmp_path)["raw"]["id"]

    edited = _memory_request(tmp_path, "edit", artifact_id, 1, content={"value": 9})
    data = edited["raw"]["data"]
    assert data["changed"] == {artifact_id: {"revision": 2, "kind": "edit"}}
    assert data["readback"][artifact_id]["revision"] == 2
    out = _render(edited, capsys)
    assert f"changed: {artifact_id}.revision=2, {artifact_id}.kind=edit" in out
    assert f"readback {artifact_id}.revision: 2" in out

    archived = _memory_request(tmp_path, "archive", artifact_id, 2)
    data = archived["raw"]["data"]
    assert data["changed"] == {artifact_id: {"revision": 3, "kind": "archive"}}
    assert data["readback"][artifact_id]["revision"] == 3

    restored = _memory_request(tmp_path, "archive", artifact_id, 3, archived=False)
    data = restored["raw"]["data"]
    assert data["changed"] == {artifact_id: {"revision": 4, "kind": "archive"}}
    assert data["readback"][artifact_id]["revision"] == 4

    deleted = _memory(
        tmp_path,
        "delete",
        request={
            "artifact_ids": [artifact_id],
            "expected_revisions": {artifact_id: 4},
            "scope": "preference",
            "apply": True,
        },
    )
    data = deleted["raw"]["data"]
    assert data["changed"] == {artifact_id: {"revision": 5, "kind": "delete"}}
    assert data["readback"] == {artifact_id: {"present": False}}
    out = _render(deleted, capsys)
    assert f"readback {artifact_id}.present: no" in out


def test_memory_preview_and_conflict_report_unchanged_with_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact_id = _memory_write(tmp_path)["raw"]["id"]

    preview = _memory_request(
        tmp_path, "edit", artifact_id, 1, content={"value": 9}, apply=False
    )
    data = preview["raw"]["data"]
    assert data["unchanged"] == "preview only (apply=false); nothing committed"
    assert "changed" not in data
    assert "readback" not in data
    out = _render(preview, capsys)
    assert "unchanged: preview only (apply=false); nothing committed" in out

    conflict = _memory_request(tmp_path, "edit", artifact_id, 7, content={"v": 1})
    assert conflict["raw"]["code"] == "E_VERSION"
    data = conflict["raw"]["data"]
    assert data["unchanged"] == data["message"]
    assert "changed" not in data


_RUSH_BINARY = "/opt/rush-fixture/bin/rush"


@pytest.fixture
def _agent_home(_isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from rush.integrations import agents as agents_mod

    monkeypatch.setattr(Path, "home", lambda: _isolated_home)
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    return _isolated_home


def _agent(
    action: Literal["connect", "disconnect"], tmp_path: Path, **kwargs: Any
) -> dict[str, Any]:
    from rush.permissions import ExecutionPermissions
    from rush.tools.agent_connection import AgentConnectionTool

    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    return dict(
        AgentConnectionTool().run(
            "codex",
            action=action,
            project_root=project,
            data_root=tmp_path / "data",
            permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
            **kwargs,
        )
    )


def test_agent_connect_reports_changed_and_host_readback(
    tmp_path: Path, _agent_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _agent_home / ".codex" / "config.toml"
    result = _agent(
        "connect",
        tmp_path,
        session_id="s1",
        rush_binary=_RUSH_BINARY,
        install_guidance=True,
    )
    raw = result["raw"]
    assert result["status"] == "ok", result["summary"]
    assert raw["changed"]["mcp_entry"] == str(config)
    assert raw["changed"]["instruction_block"] == raw["guidance"]["target_path"]
    assert raw["readback"]["config_path"] == str(config)
    assert raw["readback"]["registered"] is True
    assert raw["readback"]["rush_entry"]["command"] == _RUSH_BINARY
    assert "unchanged" not in raw
    out = _render({**result, "raw": {**raw, "operation": "connect"}}, capsys)
    assert f"changed: mcp_entry={config}" in out
    assert "readback registered: yes" in out

    again = _agent("connect", tmp_path, session_id="s1", rush_binary=_RUSH_BINARY)
    assert again["raw"]["unchanged"] == "already connected; nothing written"
    assert "changed" not in again["raw"]
    assert again["raw"]["readback"]["registered"] is True


def test_agent_connect_profile_preview_reports_unchanged(
    tmp_path: Path, _agent_home: Path
) -> None:
    _agent("connect", tmp_path, session_id="s1", rush_binary=_RUSH_BINARY)
    preview = _agent(
        "connect",
        tmp_path,
        session_id="s1",
        rush_binary=_RUSH_BINARY,
        profile="full",
    )
    raw = preview["raw"]
    assert preview["status"] == "skipped"
    assert raw["migration"]["state"] == "pending"
    assert (
        raw["unchanged"] == "profile migration pending; preview only, nothing written"
    )
    assert "changed" not in raw


def test_agent_disconnect_reports_removed_and_host_readback(
    tmp_path: Path, _agent_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _agent_home / ".codex" / "config.toml"
    _agent("connect", tmp_path, session_id="s1", rush_binary=_RUSH_BINARY)
    result = _agent("disconnect", tmp_path)
    raw = result["raw"]
    assert result["status"] == "ok", result["summary"]
    assert "mcp_entry" in raw["removed"]
    assert raw["changed"] == {"removed": raw["removed"]}
    assert raw["readback"] == {
        "config_path": str(config),
        "registered": False,
        "rush_entry": None,
    }
    out = _render({**result, "raw": {**raw, "operation": "disconnect"}}, capsys)
    assert "changed: removed=" in out
    assert "readback registered: no" in out

    again = _agent("disconnect", tmp_path)
    assert again["raw"]["unchanged"] == "nothing Rush-owned to remove"
    assert "changed" not in again["raw"]


# --- part B2 item 1: benchmark defaults resolve at call time -------------------


def test_importing_cli_reads_no_home(tmp_path: Path) -> None:
    # Denies Path.home() called from rush/cli.py or rush/plugins/trust.py while
    # they import, then proves the trust ledger follows a HOME changed after it.
    first, second = tmp_path / "first-home", tmp_path / "second-home"
    first.mkdir()
    second.mkdir()
    code = (
        "import os, pathlib, sys\n"
        "real = pathlib.Path.home.__func__\n"
        "def _deny(cls):\n"
        "    name = sys._getframe(1).f_code.co_filename\n"
        "    if name.endswith(('rush/cli.py', 'rush/plugins/trust.py')):\n"
        "        raise AssertionError('Path.home() read at import time: ' + name)\n"
        "    return real(cls)\n"
        "pathlib.Path.home = classmethod(_deny)\n"
        "import rush.cli, rush.plugins.trust\n"
        "pathlib.Path.home = classmethod(real)\n"
        f"os.environ['HOME'] = {str(second)!r}\n"
        "print(rush.plugins.trust.get_trust_ledger_path())\n"
    )
    import os
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "HOME": str(first)},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(second / ".rush" / "trusted_repositories.json")


@pytest.mark.parametrize("module", ["cli.py", "plugins/trust.py"])
def test_no_module_level_home_lookup(module: str) -> None:
    import rush

    source = Path(rush.__file__).parent / module
    tree = ast.parse(source.read_text(encoding="utf-8"))
    deferred = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    stack: list[ast.AST] = list(tree.body)
    hits: list[int] = []
    while stack:
        node = stack.pop()
        if isinstance(node, deferred):
            # Only the body is deferred; defaults and decorators run at import.
            stack.extend(node.args.defaults)
            stack.extend(d for d in node.args.kw_defaults if d is not None)
            if not isinstance(node, ast.Lambda):
                stack.extend(node.decorator_list)
            continue
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "home"
            and isinstance(node.value, ast.Name)
            and node.value.id == "Path"
        ):
            hits.append(node.lineno)
        stack.extend(ast.iter_child_nodes(node))
    assert hits == [], f"{module}: Path.home at import time, lines {sorted(hits)}"


def test_benchmark_status_default_output_is_under_temp_home(
    _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush import cli as cli_module

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    jobs = cli_module._benchmark_default_root() / "jobs"
    assert jobs.is_relative_to(_isolated_home)
    jobs.mkdir(parents=True)
    (jobs / "benchmark-abc.json").write_text(
        json.dumps({"job_id": "benchmark-abc", "state": "queued"}), encoding="utf-8"
    )
    result = CliRunner().invoke(cli, ["benchmark", "status", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["jobs"] == [
        {"job_id": "benchmark-abc", "state": "queued"}
    ]


def test_benchmark_run_defaults_are_under_temp_home(_isolated_home: Path) -> None:
    run = cli.commands["benchmark"].commands["run"]  # type: ignore[attr-defined]
    ctx = click.Context(run)
    for name in ("output", "model_cache"):
        param = next(p for p in run.params if p.name == name)
        value = param.get_default(ctx)
        assert Path(str(value)).is_relative_to(_isolated_home), (name, value)


# --- part B2 item 2: sync env with a missing env file -------------------------


@pytest.mark.parametrize(
    "missing", ["example"]
)  # a missing .env: see the domain-result test
def test_sync_env_missing_file_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.chdir(tmp_path)
    example, actual = tmp_path / "ex.env", tmp_path / "act.env"
    if missing == "example":
        actual.write_text("A=1\n", encoding="utf-8")
        absent = example
    else:
        example.write_text("A=1\n", encoding="utf-8")
        absent = actual
    for extra in ([], ["--json"]):
        result = CliRunner().invoke(
            cli, ["sync", "env", str(example), str(actual), *extra]
        )
        assert result.exit_code == 2, result.output
        assert str(absent) in result.output
        assert "present" not in result.output


# --- part B2 item 3: score compute exports into a missing folder --------------


@pytest.mark.parametrize("flag", ["--export-svg", "--export-html"])
def test_score_compute_export_creates_missing_parent(tmp_path: Path, flag: str) -> None:
    target = tmp_path / "missing" / "deeper" / "out.file"
    result = CliRunner().invoke(cli, ["score", "compute", flag, str(target)])
    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert target.is_file()


@pytest.mark.parametrize("flag", ["--export-svg", "--export-html"])
def test_score_compute_export_unwritable_is_exit_2(tmp_path: Path, flag: str) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    target = blocker / "out.file"
    result = CliRunner().invoke(cli, ["score", "compute", flag, str(target)])
    assert result.exit_code == 2, result.output
    assert not isinstance(result.exception, OSError)
    assert str(target) in result.output


# --- part B2 item 4: agent doctor --project <missing> -------------------------


def test_agent_doctor_missing_project_is_exit_2(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-project"
    for extra in ([], ["--json"]):
        result = CliRunner().invoke(
            cli, ["agent", "doctor", "--project", str(missing), *extra]
        )
        assert result.exit_code == 2, result.output
        assert str(missing) in result.output


# --- part B2 item 5: status <missing target> ----------------------------------


def test_status_missing_target_reports_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "gone" / "absent.py"
    result = CliRunner().invoke(cli, ["status", str(missing), "--json"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert str(missing) in payload["summary"]

    human = CliRunner().invoke(cli, ["status", str(missing)])
    assert human.exit_code == 2, human.output
    assert str(missing) in human.output
    assert "unregistered project" not in human.output


# --- part B2 item 6: binary refusal comes after the project/host checks -------


def _local_binary(tmp_path: Path) -> str:
    binary = tmp_path / "proj" / ".venv" / "bin" / "rush"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    return str(binary)


def test_connect_missing_project_wins_over_local_binary_refusal(
    tmp_path: Path, _agent_home: Path
) -> None:
    from rush.integrations.agents import AgentConnectionError, connect_agent

    missing = tmp_path / "no-such-project"
    with pytest.raises(AgentConnectionError) as info:
        connect_agent(
            "codex",
            session_id="s",
            rush_binary=_local_binary(tmp_path),
            project_root=missing,
            home=_agent_home,
            data_root=tmp_path / "data",
        )
    assert str(missing) in str(info.value)
    assert "project-local" not in str(info.value)


def test_connect_unknown_agent_wins_over_local_binary_refusal(
    tmp_path: Path, _agent_home: Path
) -> None:
    from rush.integrations.agents import UnknownAgentError, connect_agent

    with pytest.raises(UnknownAgentError):
        connect_agent(
            "phase70-agent",
            session_id="s",
            rush_binary=_local_binary(tmp_path),
            home=_agent_home,
            data_root=tmp_path / "data",
        )


def test_connect_valid_inputs_still_refuse_local_binary(
    tmp_path: Path, _agent_home: Path
) -> None:
    from rush.integrations.agents import AgentConnectionError, connect_agent

    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(AgentConnectionError, match="project-local rush binary"):
        connect_agent(
            "codex",
            session_id="s",
            rush_binary=_local_binary(tmp_path),
            project_root=project,
            home=_agent_home,
            data_root=tmp_path / "data",
        )
    assert not (tmp_path / "data").exists()


def test_cli_connect_missing_project_names_it(
    tmp_path: Path, _agent_home: Path
) -> None:
    missing = tmp_path / "no-such-project"
    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            "codex",
            "--session",
            "s",
            "--project",
            str(missing),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    assert str(missing) in result.output
    assert "project-local" not in result.output


# --- part B2 item 7: every empty collection states its reason -----------------


def test_echo_rows_empty_prints_reason_and_count(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from rush.cli_support.rendering import echo_rows

    echo_rows([], str, noun="jobs", empty="no benchmark jobs are queued")
    assert capsys.readouterr().out == (
        "0 records: no benchmark jobs are queued\n0/0 jobs\n"
    )
    echo_rows(["a"], str, empty="unused")
    assert capsys.readouterr().out == "a\n1/1 records\n"


def test_every_echo_rows_call_names_its_empty_reason() -> None:
    import rush.cli as cli_mod

    module = ast.parse(Path(cli_mod.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "echo_rows"
    ]
    assert len(calls) >= 39
    missing = [
        node.lineno
        for node in calls
        if not any(kw.arg == "empty" for kw in node.keywords)
    ]
    assert missing == []


_EMPTY_ROUTES: dict[str, list[str]] = {
    "api-diff": ["api-diff"],
    "arch-guard": ["arch-guard"],
    "audit": ["audit", "--allow-cache-write", "--allow-artifact-write"],
    "benchmark.status": ["benchmark", "status"],
    "bundle.analyze": ["bundle", "analyze", "<dir>"],
    "bundle.dead-assets": ["bundle", "dead-assets", "<dir>"],
    "check": ["check", "--allow-cache-write", "--allow-artifact-write"],
    "codegraph.callers": ["codegraph", "callers", "main"],
    "codegraph.slice": ["codegraph", "slice", "main"],
    "consensus.reconcile": ["consensus", "reconcile"],
    "context.mistakes": ["context", "mistakes"],
    "db-drift": ["db-drift"],
    "flight-recorder": ["flight-recorder"],
    "governance.sync": ["governance", "sync"],
    "hallu-guard": ["hallu-guard"],
    "hotspots.analyze": ["hotspots", "analyze"],
    "hotspots.bus-factor": ["hotspots", "bus-factor"],
    "hygiene.dead-code": ["hygiene", "dead-code"],
    "patch.memory": ["patch", "memory"],
    "plugin.list": ["plugin", "list"],
    "release.check": ["release", "check"],
    "ship.docs": ["ship", "docs"],
    "ship.env": ["ship", "env"],
    "ship.migration": ["ship", "migration"],
    "ship.pack": ["ship", "pack"],
    "ship.semver": ["ship", "semver", "<file>", "<file>"],
    "simplify": ["simplify", "--file", "<file>"],
    "strictify": ["strictify", "--file", "<file>"],
    "sync.env": ["sync", "env"],
    "trace": ["trace"],
    "workspace.affected": ["workspace", "affected"],
    "workspace.boundary": ["workspace", "boundary"],
    "workspace.list": ["workspace", "list"],
    "workspace.locks": ["workspace", "locks"],
}


@pytest.mark.parametrize("route", sorted(_EMPTY_ROUTES))
def test_empty_collection_route_prints_reason(
    route: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "example.py").write_text(
        '__all__ = ["f"]\n\n\ndef f(x: int) -> int:\n    return x\n', encoding="utf-8"
    )
    (project / "example.json").write_text("{}\n", encoding="utf-8")
    (project / ".env.example").write_text("", encoding="utf-8")
    (project / ".env").write_text("", encoding="utf-8")
    monkeypatch.chdir(project)
    if route in ("audit", "check"):
        import subprocess

        class _NoEnginePopen(subprocess.Popen[Any]):
            # Engines stay unavailable: no engine download into the temp HOME.
            def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
                argv0 = args[0] if isinstance(args, list | tuple) else str(args)
                if str(argv0) != sys.executable:
                    raise FileNotFoundError(f"t27-b2: {argv0} disabled")
                super().__init__(args, *rest, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", _NoEnginePopen)
    if route == "api-diff":
        import subprocess

        env = dict(os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.invalid",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.invalid",
            }
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main"],
            check=True,
            cwd=project,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "add", "-A"], check=True, cwd=project, capture_output=True, env=env
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "base"],
            check=True,
            cwd=project,
            capture_output=True,
            env=env,
        )
    argv = [
        {"<dir>": str(project), "<file>": str(project / "example.py")}.get(a, a)
        for a in _EMPTY_ROUTES[route]
    ]
    result = CliRunner().invoke(cli, argv)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    out = result.output
    assert re.search(r"^0/0 ", out, re.MULTILINE), out
    reasons = re.findall(r"^0 records: (.+)$", out, re.MULTILINE)
    assert reasons, out
    assert all(r.strip() for r in reasons)


# --- part B4 item 2: a missing status target on every path --------------------


def _assert_target_not_found(result: Any, shown: str) -> None:
    assert result["status"] == "error"
    assert result["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"
    assert result["metadata"]["error"]["target"] == shown
    assert result["summary"] == f"error: target not found: {shown}"
    assert "unregistered project" not in json.dumps(result)


@pytest.mark.parametrize("operation", ["status", "result"])
def test_status_tool_missing_target_is_target_not_found(
    tmp_path: Path, operation: str
) -> None:
    from rush.tools.status import StatusTool

    (tmp_path / ".rush").mkdir()
    missing = tmp_path / "gone" / "absent.py"
    result = StatusTool()(
        path=str(missing),
        operation=operation,  # type: ignore[arg-type]
        result_handle="handle-1" if operation == "result" else None,
        data_root=tmp_path / "data",
    )
    _assert_target_not_found(result, str(missing))
    # An existing target in the same project is still reported normally.
    present = StatusTool()(path=str(tmp_path), data_root=tmp_path / "data")
    assert present["status"] in ("ok", "warn"), present["summary"]
    assert "metadata" not in present


@pytest.mark.parametrize("shown", ["gone/absent.py", "ABSOLUTE"])
def test_status_mcp_missing_target_is_target_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shown: str
) -> None:
    from rush.mcp import _register_tools

    (tmp_path / ".rush").mkdir()
    monkeypatch.chdir(tmp_path)
    if shown == "ABSOLUTE":
        shown = str(tmp_path / "gone" / "absent.py")

    class Server:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def add_tool(self, *, fn: Any, name: str, description: str) -> None:
            self.handlers[name] = fn

    server = Server()
    _register_tools(server)
    result = server.handlers["rush_status"](path=shown, operation="status")
    _assert_target_not_found(result, shown)


# --- part B4 item 3: archive/restore readback carries the archived flag -------


def test_memory_readback_reports_archived_flag(tmp_path: Path) -> None:
    artifact_id = _memory_write(tmp_path)["raw"]["id"]

    edited = _memory_request(tmp_path, "edit", artifact_id, 1, content={"value": 2})
    assert edited["raw"]["data"]["readback"][artifact_id]["archived"] is False

    archived = _memory_request(tmp_path, "archive", artifact_id, 2)
    row = archived["raw"]["data"]["readback"][artifact_id]
    assert (row["revision"], row["archived"]) == (3, True)

    restored = _memory_request(tmp_path, "archive", artifact_id, 3, archived=False)
    row = restored["raw"]["data"]["readback"][artifact_id]
    assert (row["revision"], row["archived"]) == (4, False)


def test_benchmark_status_missing_explicit_output_is_an_invalid_target(
    tmp_path: Path,
) -> None:
    """T27: an explicit `--output` that does not exist is an invalid target,
    never an empty collection reported as zero recorded jobs."""
    missing = tmp_path / "no-such-dir"
    for extra in ([], ["--json"]):
        result = CliRunner().invoke(
            cli, ["benchmark", "status", "--output", str(missing), *extra]
        )
        assert result.exit_code == 2, result.output
        assert "Invalid value for '--output'" in result.output
        assert "does not exist" in result.output
        assert "0 records" not in result.output


def test_benchmark_status_default_output_not_yet_created_is_empty() -> None:
    """With the default output and no benchmark ever run, zero jobs is true."""
    result = CliRunner().invoke(cli, ["benchmark", "status", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"jobs": [], "results": []}


@pytest.mark.parametrize(
    "tool",
    ["continuity", "doctor", "pr-synthesize", "provenance-ai", "status", "tui-diff"],
)
def test_missing_explicit_target_is_target_not_found_for_every_path_tool(
    tmp_path: Path, tool: str
) -> None:
    """T27 R2: the shared executor check covers these tools too; a missing
    explicit target is never ok or skipped."""
    missing = tmp_path / "nope" / "missing"
    result = CliRunner().invoke(cli, [tool, str(missing), "--json"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["metadata"]["error"]["code"] == "TARGET_NOT_FOUND"


def test_blast_radius_rejects_a_path_outside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T27 R2: a changed path outside the analyzed project is an invalid
    target, never a clean LOW-risk report."""
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    outside = tmp_path / "nope" / "missing.py"
    result = CliRunner().invoke(cli, ["blast-radius", "--path", str(outside)])
    assert result.exit_code == 2, result.output
    assert "outside the project" in result.output
    assert "Risk=" not in result.output


def test_blast_radius_accepts_a_deleted_file_inside_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deleted module is a real changed path: its importers are affected."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "user.py").write_text("import gone\n", encoding="utf-8")
    monkeypatch.chdir(project)
    result = CliRunner().invoke(cli, ["blast-radius", "--path", "gone.py"])
    assert result.exit_code == 0, result.output
    assert "user.py" in result.output


@pytest.mark.parametrize("aggregate_status", ["error", "warn", "fail", "skipped"])
def test_scan_run_reports_the_runs_own_aggregate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aggregate_status: str
) -> None:
    """T27 R2: an executed scan reports the run's aggregate outcome; an
    incomplete run with failed or unavailable candidates is never a bare ok."""
    from types import SimpleNamespace

    import rush.tools.scan as scan_module
    from rush.permissions import ExecutionPermissions

    run = {
        "run_id": "r1",
        "run_state": "incomplete",
        "aggregate": {"tool": "scan", "status": aggregate_status, "summary": "agg"},
    }
    monkeypatch.setattr(
        scan_module, "resolve_project", lambda *a, **k: {"root": str(tmp_path)}
    )
    monkeypatch.setattr(scan_module, "load_scan_plan", lambda *a, **k: object())
    monkeypatch.setattr(
        scan_module,
        "execute_scan",
        lambda *a, **k: SimpleNamespace(to_dict=lambda: dict(run)),
    )
    result = scan_module.ScanTool().run(
        tmp_path,
        action="run",
        plan_id="p1",
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )
    assert result["status"] == aggregate_status, result
    assert result["summary"].startswith(f"scan run: {aggregate_status}"), result


def test_agent_connect_reports_a_failed_host_registration_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T27 R2: when the host registration itself fails (apply.ok false), the
    connect result is an error with the cause, never `agent connect: ok`."""
    import subprocess

    def _no_host_cli(*_args: Any, **_kwargs: Any) -> Any:
        raise FileNotFoundError("claude: host CLI unavailable")

    monkeypatch.setattr(subprocess, "run", _no_host_cli)
    monkeypatch.setattr(subprocess, "Popen", _no_host_cli)
    shim = tmp_path / "installed-bin" / "rush"
    shim.parent.mkdir()
    shim.write_text("#!/bin/sh\nexit 0\n")
    shim.chmod(0o755)
    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            "claude-code",
            "--session",
            "s1",
            "--rush-binary",
            str(shim),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["raw"]["apply"]["ok"] is False, payload
    assert payload["status"] == "error", payload
    assert result.exit_code == 2
    assert "host CLI unavailable" in payload["summary"]


def _finished_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aggregate_status: str
) -> tuple[Path, str]:
    """A registered project whose run has one finished attempt manifest."""
    from rush.workflows import project_run
    from rush.workflows.projects import register_project

    root = tmp_path / "project"
    root.mkdir()
    register_project(root, name="p")
    attempt = root / ".rush" / "runs" / "r1" / "attempts" / "a1"
    attempt.mkdir(parents=True)
    (attempt / "manifest.json").write_text(
        json.dumps({"run_id": "r1", "attempt_id": "a1", "run_state": "incomplete"})
    )
    monkeypatch.setattr(project_run, "latest_attempt_id", lambda *a, **k: "a1")
    return root, aggregate_status


def test_scan_cancel_of_a_finished_run_says_nothing_was_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T27 R2: cancelling a run whose attempt already finished reports that,
    never `requested` as if in-flight work will stop."""
    root, _ = _finished_run(tmp_path, monkeypatch, "ok")
    result = CliRunner().invoke(
        cli, ["scan", "cancel", "r1", "--project", str(root), "--json"]
    )
    payload = json.loads(result.stdout)
    assert "already finished" in payload["summary"], payload
    assert "requested" not in payload["summary"]
    assert payload["raw"]["already_finished"] is True
    assert payload["raw"]["run_state"] == "incomplete"


@pytest.mark.parametrize("aggregate_status", ["error", "warn"])
def test_scan_resume_reports_the_new_attempts_aggregate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aggregate_status: str
) -> None:
    """T27 R2: a resumed attempt reports its own aggregate, never a bare ok."""
    from types import SimpleNamespace

    from rush.workflows import project_run

    run = {
        "run_id": "r1",
        "attempt_id": "a2",
        "run_state": "incomplete",
        "aggregate": {"status": aggregate_status},
    }
    monkeypatch.setattr(
        project_run,
        "resume_scan_run",
        lambda *a, **k: SimpleNamespace(
            attempt_id="a2", run_state="incomplete", to_dict=lambda: dict(run)
        ),
    )
    result = CliRunner().invoke(
        cli,
        [
            "scan",
            "resume",
            "r1",
            "--project",
            str(tmp_path),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == aggregate_status, payload
    assert result.exit_code == (2 if aggregate_status == "error" else 1)


def test_project_artifacts_empty_reason_names_artifacts_not_projects() -> None:
    """T27 R2: an empty collection's reason belongs to its operation; empty
    artifacts of a registered project never read as 'no projects registered'."""
    import io

    from rich.console import Console

    from rush import theme

    result = {
        "tool": "project",
        "status": "ok",
        "summary": "project artifacts: ok",
        "findings": [],
        "raw": {
            "schema_version": 1,
            "operation": "artifacts",
            "data": {
                "project_id": "p1",
                "scan_outputs": [],
                "handoffs": [],
                "memory": [],
            },
        },
    }
    console = Console(file=io.StringIO(), width=200, no_color=True)
    theme._collection(result, console)
    text = console.file.getvalue()
    assert "no projects are registered" not in text, text
    assert "0 records: no artifacts are recorded for this project" in text, text


def test_project_select_reports_changed_binding_and_its_readback(
    tmp_path: Path,
) -> None:
    """T27 R2: select is a mutation; it names what it wrote (the session
    binding) and the binding re-read from disk."""
    from rush.workflows.projects import register_project

    root = tmp_path / "proj"
    root.mkdir()
    record = register_project(root, name="p")
    result = CliRunner().invoke(
        cli,
        [
            "project",
            "select",
            record.project_id,
            "--session",
            "s1",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    raw = json.loads(result.stdout)["raw"]
    data = raw["data"] if "operation" in raw else raw
    assert data["changed"] == {"session_id": "s1", "project_id": record.project_id}
    assert data["readback"] == {
        "session_id": "s1",
        "selected_project_id": record.project_id,
    }
    human = CliRunner().invoke(
        cli,
        [
            "project",
            "select",
            record.project_id,
            "--session",
            "s1",
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )
    assert "not reported by the producer" not in human.output, human.output


def test_project_configure_preview_says_nothing_was_written(tmp_path: Path) -> None:
    """T27 R2: a configure preview is not a mutation; it says so."""
    from rush.workflows.projects import register_project

    root = tmp_path / "proj"
    root.mkdir()
    record = register_project(root, name="p")
    result = CliRunner().invoke(
        cli, ["project", "configure", record.project_id, "--json"]
    )
    raw = json.loads(result.stdout)["raw"]
    data = raw["data"] if "operation" in raw else raw
    assert data["unchanged"] == "preview only; nothing written"
    assert "changed" not in data


def test_scan_plan_never_runs_the_fix_remediation_tool() -> None:
    """T27 R2: a scan is analysis; `fix` rewrites source (and inside a scan it
    only saw the staged copy without `.git`, so it failed every full scan).
    It is a visible not-applicable candidate with its reason."""
    from rush.workflows.project_run import _classify_tool

    assert _classify_tool("fix", {}) == ("not_applicable", "remediation_operation")
    assert _classify_tool("lint", {})[0] == "applicable"


@pytest.mark.parametrize("aggregate_status", ["error", "warn"])
def test_scan_rescan_cli_reports_the_rescans_aggregate_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, aggregate_status: str
) -> None:
    """T27 R2: `scan rescan` reports the re-executed run's own aggregate."""
    from rush.workflows import project_run

    empty: dict[str, list[str]] = {
        "resolved": [],
        "persisting": [],
        "new": [],
        "unverified": [],
    }
    monkeypatch.setattr(
        project_run,
        "rescan_project_run",
        lambda *a, **k: {
            "comparison": empty,
            "run": {"aggregate": {"status": aggregate_status}},
        },
    )
    result = CliRunner().invoke(
        cli,
        [
            "scan",
            "rescan",
            "r1",
            "--project",
            str(tmp_path),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert json.loads(result.stdout)["status"] == aggregate_status
    assert result.exit_code == (2 if aggregate_status == "error" else 1)


@pytest.mark.parametrize("operation", ["snapshot", "artifacts"])
def test_project_read_views_create_no_store(tmp_path: Path, operation: str) -> None:
    """T27 R2: snapshot and artifacts are reads; they never create the memory
    DB, its cache, or the token telemetry DB."""
    from rush.workflows.projects import register_project

    root = tmp_path / "proj"
    root.mkdir()
    record = register_project(root, name="p")
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    result = CliRunner().invoke(
        cli, ["project", operation, "--project-id", record.project_id, "--json"]
    )
    assert result.exit_code == 0, result.output
    after = sorted(p.relative_to(root) for p in root.rglob("*"))
    assert after == before, sorted(set(after) - set(before))


def test_benchmark_default_root_keeps_its_existing_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T27 R2: the default benchmark root stays where existing history lives
    (LOCALAPPDATA/Rush/benchmarks, else ~/AppData/Local/Rush/benchmarks)."""
    from rush import cli as cli_module

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert (
        cli_module._benchmark_default_root()
        == tmp_path / "local" / "Rush" / "benchmarks"
    )
    monkeypatch.delenv("LOCALAPPDATA")
    assert cli_module._benchmark_default_root() == (
        Path.home() / "AppData" / "Local" / "Rush" / "benchmarks"
    )


def test_benchmark_status_explicit_output_that_is_a_file_is_invalid(
    tmp_path: Path,
) -> None:
    """T27 R2: an explicit --output naming a file is an invalid target, never
    an empty history read from its parent."""
    target = tmp_path / "hosts"
    target.write_text("x")
    result = CliRunner().invoke(cli, ["benchmark", "status", "--output", str(target)])
    assert result.exit_code == 2, result.output
    assert "Invalid value for '--output'" in result.output


def test_sync_env_missing_env_file_lists_every_key_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T27 R2: a missing `.env` is the domain result (every example key is
    missing, exit 1), not a usage error; a missing `.env.example` stays one."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("API_URL=\nDEBUG=\n")
    result = CliRunner().invoke(cli, ["sync", "env", "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is False
    assert sorted(payload["rows"]) == ["API_URL", "DEBUG"]


# --- T27 R2: unknown identifiers and missing inputs are errors, never ok --------


def test_trust_refuses_a_path_that_does_not_exist(tmp_path: Path) -> None:
    """Trusting a nonexistent repository path would approve nothing real."""
    missing = tmp_path / "nope" / "repo"
    result = CliRunner().invoke(cli, ["trust", str(missing)])
    assert result.exit_code == 2, result.output
    assert "does not exist" in result.output
    assert "Approved" not in result.output


def test_session_restore_of_an_unknown_name_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["session", "restore", "never-saved", "--json"])
    payload = json.loads(result.stdout)
    assert payload["status"] == "error", payload
    assert result.exit_code == 2
    assert "never-saved" in payload["summary"]


def test_context_retrieve_of_an_unknown_handle_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["context", "retrieve", "0" * 64, "--json"])
    payload = json.loads(result.stdout)
    assert payload["status"] == "error", payload
    assert result.exit_code == 2


def test_api_diff_with_an_unknown_base_ref_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def f(x):\n    return x\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "a"]):
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["api-diff", "--base", "no-such-ref", "--json"])
    assert result.exit_code == 2, result.output
    assert "no-such-ref" in result.output
    assert '"passed": true' not in result.output


def test_flight_recorder_replay_of_an_unknown_session_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["flight-recorder", "--replay", "never-recorded", "--json"]
    )
    assert result.exit_code == 2, result.output
    assert "never-recorded" in result.output


def test_simulate_ci_with_a_missing_workflow_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["simulate-ci", "--workflow", "missing.yml"])
    assert result.exit_code == 2, result.output
    assert "passed" not in result.output
    assert "missing.yml" in result.output


def test_mcp_serve_with_an_unknown_project_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["mcp", "serve", "--project", "no-such-project"])
    assert result.exit_code == 2, result.output
    assert "no-such-project" in (result.output + (result.stderr or ""))


def test_session_resume_of_an_unknown_name_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "session",
            "resume",
            "never-saved",
            "--provider",
            "claude_code",
            "--allow-network",
            "--json",
        ],
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "error", payload
    assert result.exit_code == 2


def _codegraph_index(root: Path) -> None:
    from rush.codegraph.python_ast import PythonCodeGraphBuilder
    from rush.codegraph.store import CodeGraphStore

    store = CodeGraphStore(root / ".codegraph" / "graph.db")
    target = root / "target.py"
    target.write_text("def main():\n    return 1\n")
    PythonCodeGraphBuilder.index_python_file(target, target.read_text(), store)


@pytest.mark.parametrize("sub", ["callers", "slice"])
def test_codegraph_unknown_symbol_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sub: str
) -> None:
    """An unknown symbol is not a symbol with zero callers or an empty slice."""
    _codegraph_index(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["codegraph", sub, "no_such_symbol", "--json"])
    assert result.exit_code == 2, result.output
    assert "no_such_symbol" in result.output
    known = CliRunner().invoke(cli, ["codegraph", sub, "main", "--json"])
    assert known.exit_code == 0, known.output


def test_benchmark_run_with_an_unknown_scenario_is_an_invalid_input(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "run",
            "--scenario",
            "no-such-scenario",
            "--foreground",
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 2, result.output
    assert "no-such-scenario" in result.output


def test_test_heal_invalid_target_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "test-heal",
            "--target",
            str(tmp_path.parent / "elsewhere.py"),
            "--allow-slow",
            "--allow-artifact-write",
        ],
    )
    assert result.exit_code == 2, result.output
    assert "invalid test target" in result.output
