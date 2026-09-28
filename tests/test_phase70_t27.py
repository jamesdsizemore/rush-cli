"""T27: useful output and real behavior across the whole CLI.

Design gate: `.scratch/phase-70-design-gate/W4-T23-T29.md` (owner note, §0, §1, "## T27").
Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` (#### T27).

Test-name mapping (brief names one shared test,
``test_t27_catalog_semantics_and_human_output``; this file keeps that name for
the full-registry matrix and adds focused siblings for the section-6 bullets
that do not fit a single parametrized function):

- "Set equality between the matrix and the registry" ->
  ``test_t27_route_registry_matches_matrix_and_includes_lock``
- catalog closure over every real route ->
  ``test_t27_catalog_semantics_and_human_output`` (parametrized, one case per
  route; this IS the matrix)
- "A populated project list shows its identity and state" ->
  ``test_t27_populated_project_list_shows_identity_and_state``
- "Zero collections show 0 records plus the reason" ->
  ``test_t27_zero_collection_project_list_shows_count_and_reason``
- "distinct exit [for] ... error" + "unknown status must not exit 0" ->
  ``test_t27_unknown_status_result_never_exits_zero``
- "Redaction" -> ``test_t27_redaction_survives_cli_json_output``
- "Hostile [/x] and ESC in summaries and messages" ->
  ``test_t27_hostile_markup_and_escape_bytes_are_stripped_from_human_output``
- family projection design item (§3) ->
  ``test_t27_family_projection_covers_every_registered_tool``
- "Full versus compact JSON parity" ->
  ``test_t27_full_versus_compact_json_parity_preserves_tool_and_status``

Cannot express as a test (documented, not silently dropped):
- G5/G8 real-lane acceptance (installed hosts/engines) per X10: no pytest
  process for these exists anywhere in the current suite either (grepped
  `tests/test_phase70_result_trust.py` for "G5"/"G8"/"blocker": zero hits).
  These are recorded in `docs/reports/phase-70-implementation-evidence.md` by
  T29, not exercised here.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from rush.catalog import TOOL_SPECS
from rush.cli import cli, lock_cmd_group

_MATRIX_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "phase70" / "cli-outcomes.json"
)
_MATRIX_SCHEMA_KEYS = {
    "id",
    "argv",
    "canonical",
    "family",
    "fixture",
    "expect",
    "empty",
    "denied",
    "failure",
    "side_effects",
    "producer",
    "blocker",
}

# ---------------------------------------------------------------------------
# Isolation: fake HOME/data root before anything touches a host binary; zero
# real subprocess spawns; zero network.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("RUSH_LOG_LEVEL", raising=False)
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    return home


_REAL_SUBPROCESS_TESTS = {"test_t27_gain_terminates_within_10s_under_non_tty_stdout"}

# The external-process boundary for engine routes (plan T27: "stub external
# transport/process only"): a row declaring `"processes": "clean-engines"`
# gets each engine's real clean-run output for exactly its argv; any other
# spawn stays blocked. The tools' own parsing and normalization run for real.
_ENGINE_REPORTS = Path(__file__).parent / "fixtures" / "engine_reports"
_ENGINE_VERSIONS = {
    "ruff": "0.6.9",
    "mypy": "1.11.2",
    "pyrefly": "0.40.0",
    "radon": "6.0.1",
    "tach": "0.14.0",
    "sentrux": "0.5.0",
    "aislop": "0.16.1",
    "ollama": "0.3.0",
}


def _clean_engine_stdout(name: str, args: list[str]) -> str | None:
    if name == "ruff" and "--show-files" in args:
        files = [
            f
            for a in args
            if not a.startswith("-")
            for f in (sorted(Path(a).rglob("*.py")) if Path(a).is_dir() else [Path(a)])
            if f.suffix == ".py"
        ]
        return "".join(f"{f}\n" for f in files)
    if name == "ruff" and "--diff" in args:
        return ""
    if name == "ruff" and args[:1] in (["check"], ["format"]):
        return "[]"
    if name == "radon" and args[:1] == ["cc"]:
        return json.dumps({args[-1]: []})
    if name == "mypy":
        return "Success: no issues found in 1 source file\n"
    if name == "ollama" and args[:1] == ["run"]:
        return ""
    if name == "pyrefly" and args[1:2] == ["--help"]:
        return "--python-interpreter-path --skip-interpreter-query\n"
    if name in ("tach", "sentrux", "pyrefly", "aislop"):
        return (_ENGINE_REPORTS / name / "clean.json").read_text(encoding="utf-8")
    return None


def _ruff_finding(args: list[str]) -> str:
    target = next(a for a in reversed(args) if a.endswith(".py"))
    return json.dumps(
        [
            {
                "code": "F401",
                "message": "`os` imported but unused",
                "filename": target,
                "location": {"row": 1, "column": 8},
                "end_location": {"row": 1, "column": 10},
                "fix": None,
                "noqa_row": 1,
                "url": "https://docs.astral.sh/ruff/rules/unused-import",
            }
        ]
    )


def _engine_stub(findings: bool) -> Any:
    def run(exec_argv: list[str], argv: list[str], **_kwargs: Any) -> Any:
        name, args = Path(argv[0]).name, list(argv[1:])
        # aislop runs its pinned npm package: `npx --yes --package aislop@<v>
        # aislop <args>`.
        if (
            name == "npx"
            and args[1:2] == ["--package"]
            and args[2].split("@")[0] == "aislop"
            and args[3:4] == ["aislop"]
        ):
            name, args = "aislop", args[4:]
        if args == ["--version"] and name in _ENGINE_VERSIONS:
            stdout: str | None = f"{name} {_ENGINE_VERSIONS[name]}\n"
        elif findings and name == "ruff" and args[:1] == ["check"]:
            return subprocess.CompletedProcess(argv, 1, _ruff_finding(args), "")
        else:
            stdout = _clean_engine_stdout(name, args)
        if stdout is None:
            raise FileNotFoundError(f"phase70-t27: no stub for {name} {args[:2]}")
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    return run


# Captured before `_no_spawn` replaces them, for rows that need real git.
_REAL_POPEN = subprocess.Popen
_REAL_RUN = subprocess.run


def _allowlisted_popen(allowed: frozenset[str]) -> type:
    class _AllowlistedPopen(_REAL_POPEN):  # type: ignore[misc,valid-type]
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            argv0 = args[0] if isinstance(args, list | tuple) else str(args).split()[0]
            name = Path(str(argv0)).name
            if name not in allowed and not (
                "python" in allowed and str(argv0) == sys.executable
            ):
                raise FileNotFoundError(f"phase70-t27: {argv0} spawn blocked")
            super().__init__(args, *rest, **kwargs)

    return _AllowlistedPopen


def _fake_claude_cli(args: Any, *_rest: Any, **_kwargs: Any) -> Any:
    """The host CLI's own `mcp add/remove` effect on ~/.claude.json (the
    external process boundary for agent routes); anything else is blocked."""
    argv = [str(a) for a in args]
    if Path(argv[0]).name != "claude" or argv[1:2] != ["mcp"]:
        raise FileNotFoundError(f"phase70-t27: {argv[0]} spawn blocked")
    config = Path(os.environ["HOME"]) / ".claude.json"
    data = json.loads(config.read_text()) if config.is_file() else {}
    servers = data.setdefault("mcpServers", {})
    verb, name = argv[2], argv[3]
    if verb == "add":
        command = argv[argv.index("--") + 1 :]
        servers[name] = {"type": "stdio", "command": command[0], "args": command[1:]}
    elif verb == "remove" and name not in servers:
        return subprocess.CompletedProcess(argv, 1, "", f"No MCP server found: {name}")
    elif verb == "remove":
        del servers[name]
    config.write_text(json.dumps(data, indent=2))
    return subprocess.CompletedProcess(argv, 0, "", "")


# aislop resolves from the Rush runtime (its npm pin is read from the
# installed launcher), never from a PATH placeholder.
_ENGINE_PLACEHOLDERS = sorted(set(_ENGINE_VERSIONS) - {"aislop"})


def _route_engines_installed(route_id: str) -> Any:
    """A route whose positive outcome runs stubbed engines has them installed
    for every outcome, so its denied/failure rows exercise the same host."""
    from contextlib import ExitStack

    stack = ExitStack()
    modes = _MATRIX_CASES[route_id]["expect"].get("processes") or ()
    modes = [modes] if isinstance(modes, str) else list(modes)
    if {"clean-engines", "finding-engines"} & set(modes):
        _stub_binaries_on_path(stack, _ENGINE_PLACEHOLDERS)
    return stack


def _stub_binaries_on_path(stack: Any, names: Any) -> None:
    """Make each stubbed process resolvable on PATH, as on a host that has it
    installed. Appended, so a host's own copy still wins; the stub answers
    either way. Each placeholder fails loudly if it is ever really spawned."""
    import tempfile
    from unittest import mock

    bindir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
    for name in names:
        exe = bindir / name
        exe.write_text("#!/bin/sh\nexit 127\n")
        exe.chmod(0o755)
    path = os.environ.get("PATH", "")
    stack.enter_context(
        mock.patch.dict(os.environ, {"PATH": f"{path}{os.pathsep}{bindir}"})
    )


def _process_stub(spec: dict[str, Any]) -> Any:
    """`clean-engines`: engines answer with their clean output at the process
    boundary. `git`: real git only (a repository is the route's input)."""
    from contextlib import ExitStack
    from unittest import mock

    stack = ExitStack()
    modes = spec.get("processes") or ()
    modes = [modes] if isinstance(modes, str) else list(modes)
    engines = {"clean-engines": False, "finding-engines": True}
    for mode in modes:
        if mode in engines:
            _stub_binaries_on_path(stack, _ENGINE_PLACEHOLDERS)
            for target in ("_run_subprocess_blocking", "_run_subprocess_cancellable"):
                stack.enter_context(
                    mock.patch(
                        f"rush.runtime.subprocesses.{target}",
                        _engine_stub(engines[mode]),
                    )
                )
    if "host-cli" in modes:
        _stub_binaries_on_path(stack, ["claude"])
        stack.enter_context(mock.patch.object(subprocess, "run", _fake_claude_cli))
    real = frozenset(m for m in modes if m in ("git", "python"))
    if real:
        stack.enter_context(
            mock.patch.object(subprocess, "Popen", _allowlisted_popen(real))
        )
        stack.enter_context(mock.patch.object(subprocess, "run", _REAL_RUN))
    return stack


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Seed",
    "GIT_AUTHOR_EMAIL": "seed@example.invalid",
    "GIT_COMMITTER_NAME": "Seed",
    "GIT_COMMITTER_EMAIL": "seed@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _seed_git_repo(cwd: Path) -> dict[str, str]:
    env = {**os.environ, **_GIT_ENV}
    with _process_stub({"processes": "git"}):
        for args in (
            ["init", "-q", "-b", "main"],
            ["add", "-A"],
            ["commit", "-q", "-m", "seed"],
        ):
            _REAL_RUN(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)
    return {}


def _seed_project(cwd: Path) -> dict[str, str]:
    from rush.workflows.projects import register_project

    record = register_project(cwd, name="phase70-project")
    return {
        "<project-id>": record.project_id,
        "<project-revision>": str(record.revision),
    }


def _seed_moved_project(cwd: Path) -> dict[str, str]:
    from rush.workflows.projects import register_project

    old, new = cwd / "old-root", cwd / "new-root"
    old.mkdir()
    (old / "example.py").write_text("def example() -> int:\n    return 1\n")
    record = register_project(old, name="phase70-moved")
    old.rename(new)
    return {
        "<project-id>": record.project_id,
        "<project-revision>": str(record.revision),
        "<new-root>": str(new),
    }


def _seed_scanned_project(cwd: Path, *, findings: bool = False) -> dict[str, str]:
    source = cwd / "example.py"
    if not source.exists():
        source.write_text("import os\n" if findings else "VALUE = 1\n")
    _seed_git_repo(cwd)
    tokens = _seed_project(cwd)
    grants = ["--allow-cache-write", "--allow-artifact-write", "--json"]
    mode = "finding-engines" if findings else "clean-engines"
    with _process_stub({"processes": ["git", mode]}):
        result = CliRunner().invoke(
            cli, ["scan", "--project", str(cwd), "--full", *grants]
        )
    run = json.loads(result.stdout)["raw"]["data"]
    return {**tokens, "<run-id>": run["run_id"]}


def _seed_connected_agent(cwd: Path) -> dict[str, str]:
    grants = ["--allow-cache-write", "--allow-artifact-write", "--json"]
    shim = _seed_rush_shim(cwd)["<rush-binary>"]
    argv = ["agent", "connect", "claude-code", "--session", "phase70-session"]
    with _process_stub({"processes": "host-cli"}):
        result = CliRunner().invoke(cli, [*argv, "--rush-binary", shim, *grants])
    assert result.exit_code == 0, result.output
    return {}


def _seed_rush_shim(cwd: Path) -> dict[str, str]:
    """An installed-looking rush executable outside this checkout and any
    `.venv` (what `resolve_rush_binary` requires); it is registered, not run."""
    shim = cwd / "installed-bin" / "rush"
    shim.parent.mkdir()
    shim.write_text("#!/bin/sh\nexit 0\n")
    shim.chmod(0o755)
    return {"<rush-binary>": str(shim)}


def _seed_codegraph_index(cwd: Path) -> dict[str, str]:
    """A small real code-graph index (one target symbol plus its caller) so
    `codegraph callers`/`codegraph slice` can be asked about a name that
    genuinely is not in the index, raising the route's own BadParameter."""
    from rush.codegraph.python_ast import PythonCodeGraphBuilder
    from rush.codegraph.store import CodeGraphStore, GraphEdge

    store = CodeGraphStore(cwd / ".codegraph" / "graph.db")
    target = cwd / "target.py"
    target.write_text("def target_fn():\n    return 1\n", encoding="utf-8")
    PythonCodeGraphBuilder.index_python_file(target, target.read_text(), store)
    caller = cwd / "caller.py"
    caller.write_text("def caller_fn():\n    target_fn()\n", encoding="utf-8")
    PythonCodeGraphBuilder.index_python_file(caller, caller.read_text(), store)
    store.insert_edge(
        GraphEdge(
            source_id=f"{caller}:caller_fn:1",
            target_id=f"{target}:target_fn:1",
            edge_type="CALLS",
        )
    )
    return {}


def _seed_context_chunk(cwd: Path) -> dict[str, str]:
    """A real CCR chunk stored via `context pack` (budget forced below the
    packed size so it spills to the cache), so `context retrieve` has a real
    handle to recover instead of the all-zero not-found handle."""
    target = cwd / "example.py"
    if not target.exists():
        target.write_text("def example() -> int:\n    return 1\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        [
            "context",
            "pack",
            "--path",
            "example.py",
            "--budget",
            "1",
            "--allow-cache-write",
            "--json",
        ],
    )
    payload = json.loads(result.stdout)
    handle = payload["extensions"]["metadata"]["context_envelope"]["recovery"]["handle"]
    return {"<chunk-handle>": handle}


_MATRIX_SEEDS: dict[str, Any] = {
    "rush-shim": _seed_rush_shim,
    "scanned-project-with-findings": lambda cwd: _seed_scanned_project(
        cwd, findings=True
    ),
    "git-repo": _seed_git_repo,
    "project": _seed_project,
    "moved-project": _seed_moved_project,
    "scanned-project": _seed_scanned_project,
    "connected-agent": _seed_connected_agent,
    "codegraph": _seed_codegraph_index,
    "context-chunk": _seed_context_chunk,
}


def _apply_seed(spec: dict[str, Any], cwd: Path, args: list[str]) -> list[str]:
    tokens: dict[str, str] = {}
    for name in spec.get("seed", ()):
        tokens.update(_MATRIX_SEEDS[name](cwd))
    return [tokens.get(arg, arg) for arg in args]


@pytest.fixture(autouse=True)
def _no_spawn(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # One test (item 8: the `gain` hang) needs a REAL subprocess to prove a
    # real hang with a real timeout. `--strict-markers` is set repo-wide
    # (pyproject.toml) and this file cannot register a new marker there, so
    # the opt-out is by exact test name instead of a custom marker.
    if request.node.originalname in _REAL_SUBPROCESS_TESTS:
        return

    def _blocked(*_args: Any, **_kwargs: Any) -> Any:
        raise FileNotFoundError("phase70-t27: real process spawn blocked in tests")

    monkeypatch.setattr(subprocess, "Popen", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)


# ---------------------------------------------------------------------------
# Route set derivation: recursive walk of the real Click registry, plus the
# dynamically-resolved `lock` group (`RushGroup.get_command`, cli.py:59-65,
# not in `cli.commands`), plus explicit bare-group rows for the three
# `invoke_without_command=True` groups (root `rush`, `memory`, `scan`).
# ---------------------------------------------------------------------------


def _walk(
    group: click.Group, prefix: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], click.Command]]:
    routes: list[tuple[tuple[str, ...], click.Command]] = []
    for name in sorted(group.commands):
        command = group.commands[name]
        path = prefix + (name,)
        if isinstance(command, click.Group):
            routes.extend(_walk(command, path))
        else:
            routes.append((path, command))
    return routes


def _all_leaf_routes() -> list[tuple[tuple[str, ...], click.Command]]:
    routes = _walk(cli)
    routes.extend(
        (("lock", name), cmd) for name, cmd in sorted(lock_cmd_group.commands.items())
    )
    return routes


_BARE_GROUP_ROWS = ("<bare-rush>", "memory", "scan")

_ALL_LEAF_ROUTES = _all_leaf_routes()
_ALL_ROUTE_IDS = sorted(
    [*(".".join(path) for path, _ in _ALL_LEAF_ROUTES), *_BARE_GROUP_ROWS]
)

# Interactive/server/watch/live-panel routes that take over a real terminal,
# bind a real socket, or loop forever without an injectable seam at the CLI
# boundary (X10: "An unavailable lane stays an explicit blocker"). Verified by
# reading each: `mcp.serve` calls `asyncio.run(run_stdio(...))` (cli.py:706-715);
# `watch` drives a real `FileWatcher` loop (cli.py:1199-1221); `dashboard`
# starts a real threaded HTTP server on 127.0.0.1 (cli.py:1574-1660); `ui`
# takes over the real terminal for its interactive loop; `gain`/`context gain`
# both call `_run_gain_live_panel()` (cli.py:4866-4877), a live HUD loop with
# `max_updates=None` that only exits on `KeyboardInterrupt` -- confirmed by
# running it: it hangs indefinitely under `CliRunner`, which cannot deliver one.
# `install`/`benchmark.run` are the X10 network-bootstrap lane (real PyPI/npm/
# GitHub downloads and model-cache fetches): with subprocess/network stubbed
# per this file's isolation contract they have no injectable seam either, so
# they stay a documented blocker rather than a fake success.
_BLOCKED_ROUTES = {
    "mcp.serve",
    "watch",
    "dashboard",
    "ui",
    "gain",
    "context.gain",
    "install",
    "benchmark.run",
}


# ---------------------------------------------------------------------------
# Generic real-argument autofill, built from each command's actual Click
# params (never a hand-picked sample) so every leaf route is exercised at its
# real shared implementation boundary. Only subprocess/network are stubbed
# (via the autouse `_no_spawn` fixture above); no tool is stubbed into a
# result.
# ---------------------------------------------------------------------------


# A few required params are format-contracted by the command itself (parsed
# with `json.loads` before any tool ever sees them), so a "safe realistic
# fixture" for them must actually be valid JSON, not adversarial garbage:
# `--content` (`cli.py:3121,3189`) and `sync openapi`'s `openapi_file`
# (`cli.py:2287`). `--input` (memory family) already wraps its `json.loads`
# in `click.ClickException` (`cli.py:3331-3339`), so it degrades cleanly
# either way and needs no special case.
_JSON_CONTENT_NAMES = {"content"}
_JSON_FILE_NAMES = {"openapi_file"}


def _value_for(
    name: str,
    type_name: str,
    choices: tuple[str, ...] | None,
    fixture_file: Path,
    fixture_dir: Path,
    fixture_json_file: Path,
) -> str:
    if choices:
        return choices[0]
    if name in _JSON_CONTENT_NAMES:
        return "{}"
    if name in _JSON_FILE_NAMES:
        return str(fixture_json_file)
    if type_name in ("Path", "TargetPath"):
        return (
            str(fixture_dir)
            if name in {"dist_dir", "assets_dir"}
            else str(fixture_file)
        )
    if type_name == "IntParamType":
        return "0"
    overrides = {
        "run_id": "phase70-missing-run",
        "project": str(fixture_dir),
        "agent_id": "phase70-agent",
        "session_id": "phase70-session",
        "project_id": "phase70-project",
        "source": "phase70-source",
        "query": "phase70 fixture query",
        "name": "phase70-fixture",
        "symbol_name": "main",
        "chunk_hash": "0" * 64,
        "command_str": "echo phase70",
        "system": "phase70 fixture system prompt",
        "plugin_name": "phase70-nonexistent-plugin",
        "target": "phase70-fixture",
        "old_file": str(fixture_file),
        "new_file": str(fixture_file),
        "base": str(fixture_file),
        "ours": str(fixture_file),
        "theirs": str(fixture_file),
        "path": str(fixture_file),
        "file_path": str(fixture_file),
        "target_path": str(fixture_file),
        "provider_id": "claude_code",
    }
    return overrides.get(name, str(fixture_file))


def _build_argv(
    command: click.Command,
    fixture_file: Path,
    fixture_dir: Path,
    fixture_json_file: Path,
) -> list[str]:
    positional: list[str] = []
    options: list[str] = []
    for param in command.params:
        if not getattr(param, "required", False):
            continue
        choices = getattr(getattr(param, "type", None), "choices", None)
        value = _value_for(
            param.name or "",
            type(param.type).__name__,
            choices,
            fixture_file,
            fixture_dir,
            fixture_json_file,
        )
        if isinstance(param, click.Argument):
            positional.append(value)
        else:
            options.extend([f"--{(param.name or '').replace('_', '-')}", value])
    if any(param.name == "as_json" for param in command.params):
        options.append("--json")
    return positional + options


def _assert_real_exercise(result: Any) -> None:
    """Every route must reach its real producer with no uncaught crash."""
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"route crashed instead of returning a real ToolResult: {result.exc_info!r}"
    )
    assert result.exit_code in (0, 1, 2), (
        f"unexpected exit code {result.exit_code}: {result.output[:500]!r}"
    )


# ---------------------------------------------------------------------------
# The matrix itself: one parametrized case per real, currently-registered
# route. Set equality with the live registry is exact by construction (the
# ids come from the same walk); a newly exposed route fails coverage because
# it will not appear in `_ALL_ROUTE_IDS` until this file is re-collected
# against the new registry, and the dedicated set-equality test below re-runs
# the same live walk independently to prove nothing was cached wrong.
# ---------------------------------------------------------------------------


def test_t27_route_registry_matches_matrix_and_includes_lock() -> None:
    live_ids = sorted(
        [*(".".join(path) for path, _ in _all_leaf_routes()), *_BARE_GROUP_ROWS]
    )
    assert live_ids == _ALL_ROUTE_IDS, (
        "matrix route ids must equal the live Click registry exactly"
    )
    assert "lock.acquire" in _ALL_ROUTE_IDS
    assert "lock.release" in _ALL_ROUTE_IDS
    assert "lock.renew" in _ALL_ROUTE_IDS
    assert "lock.inspect" in _ALL_ROUTE_IDS


@pytest.mark.parametrize("route_id", _ALL_ROUTE_IDS, ids=_ALL_ROUTE_IDS)
def test_t27_catalog_semantics_and_human_output(route_id: str, tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixture-project"
    fixture_dir.mkdir()
    fixture_file = fixture_dir / "example.py"
    fixture_file.write_text("def example() -> int:\n    return 1\n", encoding="utf-8")
    fixture_json_file = fixture_dir / "example.json"
    fixture_json_file.write_text(
        json.dumps(
            {"openapi": "3.0.0", "info": {"title": "x", "version": "1.0"}, "paths": {}}
        ),
        encoding="utf-8",
    )

    if route_id in _BLOCKED_ROUTES:
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=fixture_dir):
            result = runner.invoke(cli, list(route_id.split(".")) + ["--help"])
        assert result.exit_code == 0, (
            f"blocked route {route_id} must still register --help"
        )
        assert "Usage" in result.output
        failure = _MATRIX_CASES[route_id]["failure"]
        if "argv" in failure:
            _assert_outcome(route_id, "failure", failure, failure["argv"], fixture_dir)
        return

    case = _MATRIX_CASES[route_id]
    _assert_outcome(route_id, "expect", case["expect"], case["argv"], fixture_dir)
    for kind in _SUBCASES:
        spec = case[kind]
        _assert_subcase_declared(route_id, kind, spec)
        if "argv" in spec:
            _assert_outcome(route_id, kind, spec, spec["argv"], fixture_dir)


_SUBCASES = ("empty", "denied", "failure")
_GRANT_PARAMS = {"allow_cache_write", "allow_artifact_write"}


def _route_command(route_id: str) -> click.Command:
    if route_id == "<bare-rush>":
        return cli
    path = route_id.split(".")
    # `lock` is resolved dynamically by `RushGroup.get_command`
    # (cli.py:59-65) and is never a member of `cli.commands`.
    command: click.Command = lock_cmd_group if path[0] == "lock" else cli
    for part in path[1:] if path[0] == "lock" else path:
        assert isinstance(command, click.Group)
        command = command.commands[part]
    return command


def _assert_subcase_declared(route_id: str, kind: str, spec: dict[str, Any]) -> None:
    """A sub-case either runs, is blocked on a named lane, or is impossible
    for this route -- and "impossible" is checked against the live command."""
    if "argv" in spec:
        assert {"json_paths", "human_contains", "exit"} <= spec.keys(), (
            f"{route_id} {kind}: a runnable sub-case needs json_paths, "
            f"human_contains and exit, got {sorted(spec)}"
        )
        return
    if "blocker" in spec:
        assert {"lane", "reason"} <= spec["blocker"].keys(), (route_id, kind, spec)
        return
    reason = spec.get("not_applicable")
    assert isinstance(reason, str) and reason, (
        f"{route_id} {kind}: must be runnable, a blocker, or not_applicable "
        f"with a reason, got {spec!r}"
    )
    command = _route_command(route_id)
    if kind == "empty":
        from rush.cli_support.rendering import COLLECTION_ROUTES

        if route_id in ("capabilities", "plan"):
            from rush.capabilities import _PLAN_PROFILES
            from rush.catalog import TOOL_SPECS

            assert len(TOOL_SPECS) > 0 and len(_PLAN_PROFILES["default"]) > 0, (
                f"{route_id}: not_applicable requires proof that its backing "
                "collections (TOOL_SPECS, default plan profile) are non-empty"
            )
            return
        assert command not in COLLECTION_ROUTES, (
            f"{route_id} is a collection route: its empty case must run"
        )
    elif kind == "denied":
        assert not {p.name for p in command.params} & _GRANT_PARAMS, (
            f"{route_id} declares a write grant: its denied case must run"
        )
    else:
        value_params = [
            p.name
            for p in command.params
            if not getattr(p, "is_flag", False) and p.name != "help"
        ]
        assert not value_params, (
            f"{route_id} takes value parameters {value_params}: its failure "
            "case must run"
        )


def _assert_outcome(
    route_id: str,
    kind: str,
    spec: dict[str, Any],
    argv: list[str],
    fixture_dir: Path,
) -> None:
    """Run one matrix outcome; assert its exact exit, every json_paths value
    (from the `--json` run) and every human_contains string (from the run
    without `--json`: stdout and stderr, as a user sees them)."""
    ran = False

    def invoke(args: list[str]) -> Any:
        nonlocal ran
        ran = True
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=fixture_dir) as cwd:
            for rel, text in spec.get("setup", {}).items():
                _write(Path(cwd), rel, text)
            seeded = _apply_seed(spec, Path(cwd), _materialize(args, fixture_dir))
            with _process_stub(spec), _route_engines_installed(route_id):
                result = runner.invoke(cli, seeded)
        _assert_real_exercise(result)
        assert result.exit_code == spec["exit"], (
            f"{route_id} {kind} {args}: exit {result.exit_code} != "
            f"{spec['exit']}; stdout={result.stdout[-1500:]!r} "
            f"stderr={result.stderr[-800:]!r}"
        )
        return result

    if spec["json_paths"]:
        machine = invoke([a for a in argv if a != "--json"] + ["--json"])
        payload = json.loads(machine.stdout)
        for dotted, value in spec["json_paths"].items():
            actual = _json_at(payload, dotted)
            assert actual == value, (
                f"{route_id} {kind}: --json {dotted!r} is {actual!r}, "
                f"expected {value!r}"
            )
    human_argv = [a for a in argv if a != "--json"]
    if spec["human_contains"] or not ran:
        human = invoke(human_argv)
        for text in spec["human_contains"]:
            assert text in human.output, (
                f"{route_id} {kind} {human_argv}: {text!r} not in human "
                f"output {human.output[-1500:]!r}"
            )


# ---------------------------------------------------------------------------
# E19: `project list` hides its rows. `theme.render_result` (theme.py:63-108)
# renders only tool/status/summary/findings; project/scan/memory/agent
# collection data lives in `raw` and never reaches human output.
# ---------------------------------------------------------------------------


def test_t27_populated_project_list_shows_identity_and_state(tmp_path: Path) -> None:
    from rush.tools.project import ProjectTool
    from rush.workflows.projects import list_projects, register_project

    repo = tmp_path / "repo"
    repo.mkdir()
    record = register_project(repo)

    # Arrange-step check: real reader agrees a project was registered, before
    # asserting on T27 (human-rendering) behavior.
    arranged = list_projects()
    assert any(p["project_id"] == record.project_id for p in arranged), (
        f"arrange failed: register_project did not produce a readable entry, got {arranged!r}"
    )

    result = ProjectTool().run(Path("."), action="list")
    json_result = dict(result)
    assert json_result["status"] == "ok"
    assert any(
        p["project_id"] == record.project_id for p in json_result["raw"]["projects"]
    )

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        human = runner.invoke(cli, ["project", "list"])
    assert human.exit_code == 0
    assert record.project_id in human.output, (
        "T27 defect (E19): `project list` human output must show each project's "
        f"identity and state, not just a generic status line; got: {human.output!r}"
    )


def test_t27_zero_collection_project_list_shows_count_and_reason(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        human = runner.invoke(cli, ["project", "list"])
    assert human.exit_code == 0
    assert "0 records" in human.output or "no projects" in human.output.lower(), (
        "T27 defect: an empty collection must show an explicit zero-count and "
        f"reason, not a bare 'ok' line; got: {human.output!r}"
    )


# ---------------------------------------------------------------------------
# Unknown/missing status must not exit 0 (`cli_support/rendering.py:36-42`
# and `runtime/result_helpers.py:174-192` both currently fall through to 0).
# ---------------------------------------------------------------------------


def test_t27_unknown_status_result_never_exits_zero() -> None:
    from rush.cli_support.rendering import exit_code_for as rendering_exit_code_for
    from rush.runtime.result_helpers import (
        exit_code_for as result_helpers_exit_code_for,
    )

    bogus = {"tool": "phase70", "status": "not-a-real-status"}
    for exit_code_for, owner in (
        (rendering_exit_code_for, "cli_support/rendering.py"),
        (result_helpers_exit_code_for, "runtime/result_helpers.py"),
    ):
        assert exit_code_for(bogus) == 2, (
            f"T27 defect: {owner}::exit_code_for must exit 2 (INVALID_RESULT) for "
            f"a result dict with no valid ToolStatus, got {exit_code_for(bogus)}"
        )
    assert rendering_exit_code_for(None) == 2, (
        "T27 defect: a missing/None result must exit 2, not fall through to 0"
    )


# ---------------------------------------------------------------------------
# Family projection (§3 design item): a finite per-family projector keyed by
# (tool, operation). Does not exist yet.
# ---------------------------------------------------------------------------


def test_t27_family_projection_covers_every_registered_tool() -> None:
    try:
        from rush.theme import FAMILY_PROJECTIONS  # type: ignore[attr-defined]
    except ImportError:
        FAMILY_PROJECTIONS = None

    assert FAMILY_PROJECTIONS, (
        "T27 defect: theme.py must define FAMILY_PROJECTIONS, a "
        "dict[(tool, operation|None), projector] covering every catalog tool; "
        "not present yet"
    )
    missing = sorted(
        name for name in TOOL_SPECS if (name, None) not in FAMILY_PROJECTIONS
    )
    assert not missing, (
        f"FAMILY_PROJECTIONS is missing a projection for: {missing[:15]}"
    )


# ---------------------------------------------------------------------------
# X3: raw ESC/C0 control bytes reach the terminal today because `escape()`
# only escapes rich markup brackets, never control bytes.
# ---------------------------------------------------------------------------


def test_t27_hostile_markup_and_escape_bytes_are_stripped_from_human_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from rush import theme

    theme._shared_console = None  # force a fresh Console for this test's stdout
    hostile_summary = "\x1b[2Jsummary [/bad] here"
    hostile_message = "\x1b]0;pwned\x07finding message"
    theme.render_result(
        {
            "tool": "phase70",
            "status": "ok",
            "summary": hostile_summary,
            "findings": [
                {
                    "path": "a.py",
                    "line": 1,
                    "rule": "x",
                    "severity": "info",
                    "message": hostile_message,
                }
            ],
        }
    )
    out = capsys.readouterr().out
    assert "\x1b" not in out, (
        "T27 defect (X3): render_result must pass dynamic strings through "
        f"safe_terminal_text before printing; found a raw ESC byte in: {out!r}"
    )


# ---------------------------------------------------------------------------
# Full vs compact JSON parity: same tool/status, real byte-budget difference.
# ---------------------------------------------------------------------------


def test_t27_full_versus_compact_json_parity_preserves_tool_and_status(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "example.py"
    fixture.write_text("def f():\n    return 1\n" * 200, encoding="utf-8")

    runner = CliRunner()
    full = runner.invoke(cli, ["lint", str(fixture), "--json", "--result-view", "full"])
    compact = runner.invoke(
        cli, ["lint", str(fixture), "--json", "--result-view", "compact"]
    )

    assert full.exit_code in (0, 1, 2)
    assert compact.exit_code in (0, 1, 2)
    full_payload = json.loads(full.output)
    compact_payload = json.loads(compact.output)
    assert full_payload["tool"] == compact_payload["tool"] == "lint"
    assert full_payload["status"] == compact_payload["status"]
    assert len(compact.output) <= len(full.output)


# ---------------------------------------------------------------------------
# Redaction survives the shared CLI JSON path (regression guard: exercised
# already at `exit_with_result` via `sanitize_value`, per
# `test_context_pack_stores_redacted_omission_under_a_recoverable_handle` in
# `tests/test_cli_registry.py`; re-checked here through a plain catalog tool).
# ---------------------------------------------------------------------------


def test_t27_redaction_survives_cli_json_output(tmp_path: Path) -> None:
    secret = "sk-ant-abcdefghijklmnopqrstuvwxyz012345"
    fixture = tmp_path / "example.py"
    fixture.write_text(f"# {secret}\ndef f():\n    return 1\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["lint", str(fixture), "--json"])
    assert result.exit_code in (0, 1, 2)
    assert secret not in result.output, (
        f"a secret must never reach CLI JSON output unredacted: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Item 1: the §3 matrix fixture itself is a T27 deliverable. It does not
# exist yet -> RED. Once it exists, every case must satisfy the §3 schema,
# match the live registry exactly, and name a really-importable producer.
# ---------------------------------------------------------------------------


def test_t27_matrix_fixture_exists_matches_schema_registry_and_producers() -> None:
    assert _MATRIX_FIXTURE_PATH.is_file(), (
        "T27 defect: tests/fixtures/phase70/cli-outcomes.json is a required T27 "
        "deliverable (design brief §3 matrix schema) and does not exist yet"
    )
    matrix = json.loads(_MATRIX_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(matrix, list) and matrix, (
        "matrix must be a non-empty list of cases"
    )

    ids: list[str] = []
    for case in matrix:
        missing = _MATRIX_SCHEMA_KEYS - case.keys()
        assert not missing, (
            f"case {case.get('id')!r} missing schema keys: {sorted(missing)}"
        )
        assert isinstance(case["argv"], list)
        expect = case["expect"]
        assert {"json_paths", "human_contains", "exit"} <= expect.keys(), (
            f"case {case['id']!r} expect{{}} missing required sub-keys"
        )
        assert "allowed_paths" in case["side_effects"], (
            f"case {case['id']!r} side_effects{{}} missing allowed_paths"
        )
        blocker = case["blocker"]
        assert blocker is None or {"lane", "reason"} <= blocker.keys(), (
            f"case {case['id']!r} blocker must be null or {{lane, reason}}, got {blocker!r}"
        )
        producer = case["producer"]
        assert isinstance(producer, str) and ":" in producer, (
            f"case {case['id']!r} producer must be 'module:symbol', got {producer!r}"
        )
        module_name, _, symbol_path = producer.partition(":")
        module = importlib.import_module(module_name)
        target: Any = module
        for part in symbol_path.split("."):
            assert hasattr(target, part), (
                f"case {case['id']!r} producer {producer!r} does not resolve: "
                f"no attribute {part!r} on {target!r}"
            )
            target = getattr(target, part)
        ids.append(case["id"])

    assert sorted(ids) == _ALL_ROUTE_IDS, (
        "matrix ids must equal the live registry walk exactly (set equality)"
    )


# ---------------------------------------------------------------------------
# Item 2: the route set includes each real operation-enum value for
# multi-operation commands, derived from the live Click registry/choices --
# never a hand list -- plus the `context gain` -> `gain` alias.
# ---------------------------------------------------------------------------


def test_t27_route_set_includes_live_operation_enums_and_gain_alias() -> None:
    for group_name in ("memory", "project", "scan", "agent", "context", "session"):
        group = cli.commands[group_name]
        assert isinstance(group, click.Group)
        for op_name in group.commands:
            route_id = f"{group_name}.{op_name}"
            assert route_id in _ALL_ROUTE_IDS, (
                f"operation enum route {route_id!r} (derived live from the "
                f"{group_name!r} group's real Click subcommands) is missing "
                "from the walked route set"
            )
    # `subject` is itself a live Click Choice enum on the memory verbs; assert
    # against the choices Click actually declared, never a hand-typed list.
    subject_param = next(
        p
        for p in cli.commands["memory"].commands["write"].params
        if p.name == "subject"
    )
    assert subject_param.type.choices, "memory write's subject Choice must be non-empty"

    import inspect

    context_gain_cmd = cli.commands["context"].commands["gain"]
    root_gain_cmd = cli.commands["gain"]
    assert "_run_gain_live_panel" in inspect.getsource(context_gain_cmd.callback), (
        "`context gain` must be a real alias for the same `gain` producer"
    )
    assert "_run_gain_live_panel" in inspect.getsource(root_gain_cmd.callback)


# ---------------------------------------------------------------------------
# Item 3: human collections cap at 20 rows, findings cap at 50, both with an
# exact shown/total count, a truncation line, and a copyable `... --json`
# recovery command built from the real argv.
# ---------------------------------------------------------------------------


def test_t27_human_collection_caps_at_20_rows_with_count_and_copyable_json(
    tmp_path: Path,
) -> None:
    from rush.workflows.projects import register_project

    for i in range(25):
        root = tmp_path / f"repo-{i}"
        root.mkdir()
        register_project(root)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        human = runner.invoke(cli, ["project", "list"])
    assert human.exit_code == 0
    assert "20/25" in human.output or "20 of 25" in human.output.lower(), (
        "T27 defect: a human collection over 20 rows must show an exact "
        f"shown/total count and truncate; got: {human.output!r}"
    )
    assert "--json" in human.output, (
        "T27 defect: a truncated collection must offer a copyable "
        f"`rush ... --json` recovery command; got: {human.output!r}"
    )


def test_t27_human_findings_cap_at_50_with_count_and_copyable_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from rush import theme

    theme._shared_console = None
    findings = [
        {"path": f"f{i}.py", "line": i, "rule": "x", "severity": "info", "message": "m"}
        for i in range(75)
    ]
    theme.render_result(
        {
            "tool": "lint",
            "status": "warn",
            "summary": "many findings",
            "findings": findings,
        }
    )
    out = capsys.readouterr().out
    assert "50/75" in out or "50 of 75" in out.lower(), (
        "T27 defect: findings over 50 must show an exact shown/total count; "
        f"got: {out!r}"
    )
    assert "--json" in out, (
        f"T27 defect: truncated findings must offer a copyable --json recovery "
        f"command; got: {out!r}"
    )


# ---------------------------------------------------------------------------
# Item 4: distinct exit codes per real outcome (keep-green: the five real
# ToolStatus values already map correctly); invalid/missing status must exit
# 2 with INVALID_RESULT on stderr (RED: currently exits 0 with nothing on
# stderr).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,expected_exit",
    [("ok", 0), ("skipped", 0), ("warn", 1), ("fail", 1), ("error", 2)],
)
def test_t27_distinct_exit_codes_for_known_outcomes(
    status: str, expected_exit: int
) -> None:
    from rush.cli_support.rendering import exit_code_for

    assert exit_code_for({"tool": "phase70", "status": status}) == expected_exit


def test_t27_invalid_result_status_exits_2_with_invalid_result_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from rush.cli_support.rendering import exit_with_result

    with pytest.raises(SystemExit) as excinfo:
        exit_with_result(
            {
                "tool": "phase70",
                "status": "not-a-real-status",
                "summary": "x",
                "findings": [],
            }
        )
    assert excinfo.value.code == 2, (
        f"T27 defect: an invalid ToolStatus must exit 2, got {excinfo.value.code}"
    )
    captured = capsys.readouterr()
    assert "INVALID_RESULT" in captured.err, (
        "T27 defect: an invalid ToolStatus must print INVALID_RESULT on stderr; "
        f"got stderr={captured.err!r}"
    )


# ---------------------------------------------------------------------------
# Item 5: long Unicode, narrow width (COLUMNS=40), NO_COLOR and redirected
# output all stay free of raw ESC bytes (X3, same root cause as the hostile
# markup test above, exercised with a benign but wide/long payload instead).
# ---------------------------------------------------------------------------


def test_t27_long_unicode_and_narrow_width_output_has_no_escape_bytes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from rush import theme

    monkeypatch.setenv("COLUMNS", "40")
    monkeypatch.setenv("NO_COLOR", "1")
    theme._shared_console = None
    long_unicode = "long summary text " * 10 + "日本語" * 10
    theme.render_result(
        {"tool": "phase70", "status": "ok", "summary": long_unicode, "findings": []}
    )
    out = capsys.readouterr().out
    assert "\x1b" not in out, (
        f"T27 defect (X3): long Unicode under COLUMNS=40/NO_COLOR must render "
        f"with no raw ESC byte; found one in: {out!r}"
    )


# ---------------------------------------------------------------------------
# Item 6: mutation rendering shows the changed identifiers/paths plus a real
# readback outcome, never success inferred from status alone. `project add`
# is a real mutation route.
# ---------------------------------------------------------------------------


def test_t27_mutation_rendering_shows_changed_ids_not_status_alone(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "project",
                "add",
                str(repo),
                "--allow-cache-write",
                "--allow-artifact-write",
            ],
        )
    assert result.exit_code == 0
    assert str(repo) in result.output or "repo" in result.output, (
        "T27 defect: a mutation's human output must show the changed path/id "
        f"and readback outcome, not a generic status line; got: {result.output!r}"
    )


# ---------------------------------------------------------------------------
# Item 7: each executed real-only route writes only under its declared
# allowed_paths. Diff HOME before/after for read-only routes that the design
# brief documents as intended to be side-effect-free.
# ---------------------------------------------------------------------------


def _snapshot_tree(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.mark.parametrize(
    "route_id",
    ["project.list", "project.show", "project.snapshot", "project.artifacts"],
)
def test_t27_read_only_routes_write_nothing_under_home(
    route_id: str, tmp_path: Path, _isolated_home: Path
) -> None:
    home = _isolated_home
    before = _snapshot_tree(home)

    path = tuple(route_id.split("."))
    command = cli
    for part in path[:-1]:
        command = command.commands[part]
    command = command.commands[path[-1]]
    fixture_file = tmp_path / "example.py"
    fixture_file.write_text("def example():\n    return 1\n", encoding="utf-8")
    fixture_json_file = tmp_path / "example.json"
    fixture_json_file.write_text("{}", encoding="utf-8")
    argv = list(path) + _build_argv(command, fixture_file, tmp_path, fixture_json_file)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(cli, argv)

    after = _snapshot_tree(home)
    new_paths = after - before
    assert not new_paths, (
        f"T27/X2 defect: read-only route {route_id!r} must write nothing under "
        f"HOME; new paths: {sorted(new_paths)}"
    )


# ---------------------------------------------------------------------------
# Item 8: every blocked route must carry a `blocker: {lane, reason}` row in
# the matrix (covered structurally by the schema test above once the matrix
# exists); plus the concrete `gain` hang itself is a real, currently-RED
# defect: a real subprocess (no injected seam -- this is the point) with a
# real timeout, confirmed by hand before writing this test (it timed out).
# ---------------------------------------------------------------------------


def test_t27_blocked_routes_are_declared_with_a_blocker_in_the_matrix() -> None:
    if not _MATRIX_FIXTURE_PATH.is_file():
        pytest.fail(
            "T27 defect: cannot check blocker declarations because "
            "tests/fixtures/phase70/cli-outcomes.json does not exist yet "
            "(see test_t27_matrix_fixture_exists_matches_schema_registry_and_producers)"
        )
    matrix = json.loads(_MATRIX_FIXTURE_PATH.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in matrix}
    for route_id in _BLOCKED_ROUTES:
        case = by_id.get(route_id)
        assert case is not None, f"blocked route {route_id!r} missing from the matrix"
        blocker = case.get("blocker")
        assert blocker and {"lane", "reason"} <= blocker.keys(), (
            f"blocked route {route_id!r} must carry blocker: {{lane, reason}}, "
            f"got {blocker!r}"
        )


def test_t27_gain_terminates_within_10s_under_non_tty_stdout(tmp_path: Path) -> None:
    home = tmp_path / "gain-home"
    home.mkdir()
    cwd = tmp_path / "gain-cwd"
    cwd.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    rush_bin = Path(sys.executable).parent / "rush"

    before = _snapshot_tree(cwd)
    try:
        proc = subprocess.run(
            [str(rush_bin), "gain"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "T27 defect: `rush gain` with non-TTY (piped) stdout must print one "
            "read-only snapshot and exit, not loop forever waiting for a real "
            "terminal -- it did not terminate within 10s (confirmed by hand "
            "before writing this test)"
        )
    assert proc.returncode in (0, 1, 2)
    assert proc.stdout.strip() != "", (
        "`rush gain` must print a result even non-interactively"
    )

    after = _snapshot_tree(cwd)
    new_paths = after - before
    assert not new_paths, (
        f"T27/X2 defect: `rush gain` must not write files under cwd outside its "
        f"declared allowed_paths; new paths: {sorted(new_paths)}"
    )


# ---------------------------------------------------------------------------
# Coordinator follow-up (T27): the admin commands that print row lists with
# plain echo loops. Each is registered in `rendering.COLLECTION_ROUTES` (with
# the `--json` paths holding its full lists) and must cap its human view at
# 20 rows / 50 findings with the exact shown/total and a copyable `--json`
# line, while `--json` prints every row. The route set comes from the live
# Click registry, never a hand list.
# ---------------------------------------------------------------------------


def _collection_routes() -> dict[str, tuple[str, ...]]:
    from rush.cli_support.rendering import COLLECTION_ROUTES

    return {
        ".".join(path): COLLECTION_ROUTES[command]
        for path, command in _ALL_LEAF_ROUTES
        if command in COLLECTION_ROUTES
    }


_COLLECTION_ROUTES = _collection_routes()
_MATRIX_CASES: dict[str, dict[str, Any]] = (
    {case["id"]: case for case in json.loads(_MATRIX_FIXTURE_PATH.read_text("utf-8"))}
    if _MATRIX_FIXTURE_PATH.is_file()
    else {}
)
_EXECUTABLE_CASE_IDS = sorted(
    case_id for case_id, case in _MATRIX_CASES.items() if case["blocker"] is None
)


def _make_fixture(tmp_path: Path) -> Path:
    fixture_dir = tmp_path / "fixture-project"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "example.py").write_text(
        "def example() -> int:\n    return 1\n", encoding="utf-8"
    )
    (fixture_dir / "example.json").write_text(
        json.dumps(
            {"openapi": "3.0.0", "info": {"title": "x", "version": "1.0"}, "paths": {}}
        ),
        encoding="utf-8",
    )
    return fixture_dir


def _materialize(argv: list[str], fixture_dir: Path) -> list[str]:
    replacements = {
        "<fixture-file>": str(fixture_dir / "example.py"),
        "<fixture-json>": str(fixture_dir / "example.json"),
        "<fixture-dir>": str(fixture_dir),
        "<missing-target>": str(fixture_dir / "missing" / "absent.py"),
        "<unwritable-target>": str(fixture_dir / "example.py" / "out.svg"),
    }
    return [replacements.get(arg, arg) for arg in argv]


def _json_at(payload: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        payload = payload[int(part)] if isinstance(payload, list) else payload[part]
    return payload


def test_t27_echo_rows_caps_rows_and_findings_with_count_and_copyable_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from rush.cli_support.rendering import echo_rows

    echo_rows([f"row-{i}" for i in range(25)], str)
    out = capsys.readouterr().out
    assert "row-19" in out and "row-20" not in out
    assert "shown 20/25 records" in out and "--json" in out

    echo_rows([f"f-{i}" for i in range(75)], str, cap=50, noun="findings")
    out = capsys.readouterr().out
    assert "f-49" in out and "f-50" not in out
    assert "shown 50/75 findings" in out and "--json" in out

    echo_rows(["only"], str)
    assert capsys.readouterr().out == "only\n1/1 records\n"

    echo_rows([], str)
    assert capsys.readouterr().out == "0/0 records\n"


def test_t27_collection_route_registry_is_live_and_nonempty() -> None:
    assert len(_COLLECTION_ROUTES) >= 38, sorted(_COLLECTION_ROUTES)
    for route_id in _COLLECTION_ROUTES:
        path = tuple(route_id.split("."))
        group: click.Group = lock_cmd_group if path[0] == "lock" else cli
        for part in path[(1 if path[0] == "lock" else 0) : -1]:
            sub = group.commands[part]
            assert isinstance(sub, click.Group)
            group = sub
        command = group.commands[path[-1]]
        assert any(p.name == "as_json" for p in command.params), (
            f"collection route {route_id!r} must offer --json"
        )


def _run_collection(
    route_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    as_json: bool,
    pad: bool,
) -> tuple[Any, list[tuple[int, int]]]:
    import rush.cli as cli_module
    from rush.cli_support import rendering
    from rush.theme import ROW_CAP

    real = rendering.echo_rows
    calls: list[tuple[int, int]] = []

    def spy(rows: Any, line: Any, **kwargs: Any) -> None:
        rows = list(rows)
        cap = kwargs.get("cap", ROW_CAP)
        calls.append((len(rows), cap))
        if pad and rows:
            rows = (rows * (cap + 5))[: cap + 5]
        real(rows, line, **kwargs)

    monkeypatch.setattr(cli_module, "echo_rows", spy)
    fixture_dir = _make_fixture(tmp_path)
    argv = _materialize(_MATRIX_CASES[route_id]["argv"], fixture_dir)
    argv = [a for a in argv if a != "--json"] + (["--json"] if as_json else [])
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=fixture_dir):
        result = runner.invoke(cli, argv)
    _assert_real_exercise(result)
    return result, calls


@pytest.mark.parametrize("route_id", sorted(_COLLECTION_ROUTES))
def test_t27_collection_route_caps_human_rows_with_count_and_copyable_json(
    route_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, calls = _run_collection(
        route_id, tmp_path, monkeypatch, as_json=False, pad=True
    )
    paths = _COLLECTION_ROUTES[route_id]
    assert len(calls) == len(paths) or (not calls and result.exit_code != 0), (
        f"{route_id}: every list must go through the capped renderer; "
        f"calls={calls} paths={paths} output={result.output!r}"
    )
    for count, cap in calls:
        if count:
            assert f"shown {cap}/{cap + 5}" in result.output, result.output
            assert "--json" in result.output, result.output


@pytest.mark.parametrize("route_id", sorted(_COLLECTION_ROUTES))
def test_t27_collection_route_json_lists_every_row(
    route_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    human, calls = _run_collection(
        route_id, tmp_path / "human", monkeypatch, as_json=False, pad=False
    )
    machine, _ = _run_collection(
        route_id, tmp_path / "json", monkeypatch, as_json=True, pad=False
    )
    assert machine.exit_code == human.exit_code
    if not calls:
        return  # the route failed before listing anything (exit != 0 above)
    payload = json.loads(machine.stdout)
    for dotted, (count, _cap) in zip(_COLLECTION_ROUTES[route_id], calls, strict=True):
        assert len(_json_at(payload, dotted)) == count, (
            f"{route_id}: --json {dotted!r} must hold all {count} rows"
        )


def _new_leaf_paths(tmp_path: Path, before: set[Path], cwd: Path) -> set[str]:
    from rush.mcp_mesh.lock_manager import MeshLockManager
    from rush.workflows.projects import default_data_root

    new = {p for p in tmp_path.rglob("*")} - before
    leaves = [p for p in new if not any(q != p and p in q.parents for q in new)]
    labels = (
        (str(Path(cwd).resolve()), "<cwd>"),
        (str(cwd), "<cwd>"),
        (str(default_data_root()), "<data-root>"),
        (str(tmp_path / "home"), "<home>"),
        (str(tmp_path / "fixture-project"), "<fixture>"),
    )
    normalized: set[str] = set()
    for leaf in leaves:
        text = str(leaf)
        for real, label in labels:
            if text.startswith(real):
                text = label + text[len(real) :]
                break
        # A lock file's name is its target's absolute path, flattened.
        fixture = tmp_path / "fixture-project"
        for real in (fixture.resolve(), fixture):
            text = text.replace(MeshLockManager._lock_name(real), "_<fixture-flat>")
        if text != "<cwd>":
            normalized.add(text)
    return normalized


@pytest.mark.parametrize("case_id", _EXECUTABLE_CASE_IDS)
def test_t27_matrix_route_writes_only_its_allowed_paths(
    case_id: str, tmp_path: Path
) -> None:
    case = _MATRIX_CASES[case_id]
    fixture_dir = _make_fixture(tmp_path)
    argv = _materialize(case["argv"], fixture_dir)
    before = {p for p in tmp_path.rglob("*")}
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=fixture_dir) as cwd:
        # The positive case's own input files are arrangement, not effects.
        for rel, text in case["expect"].get("setup", {}).items():
            _write(Path(cwd), rel, text)
        argv = _apply_seed(case["expect"], Path(cwd), argv)
        before |= set(tmp_path.rglob("*"))
        with _process_stub(case["expect"]):
            result = runner.invoke(cli, argv)
        written = _new_leaf_paths(tmp_path, before, Path(cwd))
    _assert_real_exercise(result)
    assert result.exit_code == case["expect"]["exit"], (
        f"{case_id}: expected exit {case['expect']['exit']}, got "
        f"{result.exit_code}: {result.output}"
    )
    from fnmatch import fnmatchcase

    allowed = case["side_effects"]["allowed_paths"]
    # A `*` matches a generated id (plan, run, attempt or handoff) in a path.
    unexpected = {
        path for path in written if not any(fnmatchcase(path, a) for a in allowed)
    }
    assert not unexpected, (
        f"{case_id} wrote outside its declared allowed_paths: {sorted(unexpected)}"
    )


@pytest.mark.parametrize(
    "argv,reason",
    [
        (["codegraph", "callers", "main"], "no code graph index"),
        (["codegraph", "slice", "main"], "no code graph index"),
        (["patch", "memory"], "no patch memory store"),
        (["context", "persona"], "no preference store"),
    ],
)
def test_t27_read_routes_report_absent_store_and_create_nothing(
    argv: list[str], reason: str, tmp_path: Path
) -> None:
    before = {p for p in tmp_path.rglob("*")}
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, argv)
        written = _new_leaf_paths(tmp_path, before, Path(cwd))
    assert result.exit_code == 0, result.output
    assert reason in result.output
    assert not written, f"{argv} created {sorted(written)}"


# ---------------------------------------------------------------------------
# Coordinator follow-up 2 (T27): every collection route runs against real
# seeded data -- through the producers and stores each route reads, never a
# stubbed route -- so each list exceeds its cap (20 rows / 50 findings), and
# the human view must show the cap, the exact `shown/total`, the truncation
# line and the copyable `--json`, while `--json` lists every row.
#
# Seeding: files a route scans are written directly (they are the route's
# real input); stores are written through their public writer where one
# exists (`rush trust plugin`, `FlightRecorder.record_event`,
# `PythonCodeGraphBuilder.index_python_file`, benchmark `create_job`), else
# through the store's own write API (`CodeGraphStore.insert_edge`,
# `PatchMemoryStore.record_success`, benchmark `reporting.write_result`).
#
# Lists whose producer has a hard maximum at or under the cap cannot exceed
# it with real data; they are asserted at that maximum with the exact
# `n/n` count, and the bound is named in `_BOUNDED`.
# ---------------------------------------------------------------------------

_OVER = "over"
_BOUNDED = {
    "suite-steps": "a suite's step list is its fixed tool sequence "
    "(CHECK 6, AUDIT 5, GATE 6 steps; workflows/suites.py)",
    "audit-findings": "every AUDIT_SUITE engine is absent offline or needs the "
    "network lane (security: osv-scanner/pip-audit/npm audit query remote "
    "databases; secrets/sbom/iac/containerfile engines are not installed)",
    "governance-targets": "IDE_TARGETS has 5 entries (governance/synchronizer.py)",
    "scaffold-files": "init_repository creates at most AGENTS.md and rush.toml",
    "release-manifests": "check_manifest_parity reads only pyproject.toml, "
    "package.json and Cargo.toml",
    "lockfile-rules": "validate_lockfiles has 3 rules",
    "revert-log": "mine_mistakes runs `git log --grep=Revert -n 20`: at most 20",
}
_SEED_ENGINES = {"git", "ruff", "radon", "vulture", "python", "python3"}
_WIDE = 25  # rows seeded for a 20-row cap
_FINDINGS_WIDE = 55  # rows seeded for a 50-finding cap


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _git_repo(cwd: Path, files: dict[str, str]) -> None:
    _git(cwd, "init", "-q", "-b", "main")
    for rel, text in files.items():
        (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
        (cwd / rel).write_text(text, encoding="utf-8")
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-q", "-m", "seed")


def _write(cwd: Path, rel: str, text: str) -> Path:
    path = cwd / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _complex_fn(name: str, branches: int = 12) -> str:
    body = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(branches))
    return f"def {name}(x):\n{body}    return -1\n"


def _seed_api_diff(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    funcs = "".join(f"def api_{i}(a):\n    return a\n" for i in range(_WIDE))
    _git_repo(cwd, {"src/pkg/mod.py": funcs})
    _write(cwd, "src/pkg/mod.py", "VALUE = 1\n")
    return ["api-diff"], (_OVER,)


def _seed_arch_guard(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_WIDE):
        _write(cwd, f"src/domain/m{i}.py", "from app.infrastructure import db\n")
    return ["arch-guard"], (_OVER,)


def _seed_suite_lint(cwd: Path) -> None:
    _write(cwd, "bad.py", "".join(f"import mod_{i}\n" for i in range(_FINDINGS_WIDE)))


def _seed_check(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_suite_lint(cwd)
    return ["check", "."], ("suite-steps", _OVER)


def _seed_gate(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(
        cwd,
        "complex.py",
        "\n\n".join(_complex_fn(f"fn_{i}") for i in range(_FINDINGS_WIDE)),
    )
    return ["gate", ".", "--no-fail-fast"], ("suite-steps", _OVER)


def _seed_audit(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "requirements.txt", "requests==2.0.0\n")
    return ["audit", "."], ("suite-steps", "audit-findings")


def _seed_benchmark_status(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    from scripts.benchmarks.contracts import Outcome, ProbeResult
    from scripts.benchmarks.jobs import create_job
    from scripts.benchmarks.reporting import write_result

    output = cwd / "bench" / "run"
    (cwd / "bench" / "jobs").mkdir(parents=True)
    for i in range(_WIDE):
        create_job(job_root=cwd / "bench" / "jobs", argv=["--all"], output=output)
        write_result(
            output,
            ProbeResult(
                scenario_id=f"scenario-{i}",
                probe="seeded",
                outcome=Outcome.PASS,
                started_at="2026-01-01T00:00:00Z",
                duration_ms=i,
                metrics={},
            ),
        )
    return ["benchmark", "status", "--output", str(output)], (_OVER, _OVER)


def _seed_bundle_analyze(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_WIDE):
        _write(cwd, f"dist/chunk{i}.js", "console.log(1);\n" * (i + 1))
    return ["bundle", "analyze", str(cwd / "dist")], (_OVER,)


def _seed_bundle_dead_assets(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_WIDE):
        (cwd / "public").mkdir(exist_ok=True)
        (cwd / "public" / f"img{i}.png").write_bytes(b"png")
    return ["bundle", "dead-assets", str(cwd / "public")], (_OVER,)


def _seed_capabilities(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    return ["capabilities", "."], (_OVER,)


def _seed_codegraph(cwd: Path, *, edges: bool) -> None:
    from rush.codegraph.python_ast import PythonCodeGraphBuilder
    from rush.codegraph.store import CodeGraphStore, GraphEdge

    store = CodeGraphStore(cwd / ".codegraph" / "graph.db")
    target = _write(cwd, "target.py", "def main():\n    return 1\n")
    PythonCodeGraphBuilder.index_python_file(target, target.read_text(), store)
    for i in range(_WIDE):
        source = (
            "def main():\n    return 0\n"
            if not edges
            else f"def caller_{i}():\n    main()\n"
        )
        path = _write(cwd, f"m{i}.py", source)
        PythonCodeGraphBuilder.index_python_file(path, source, store)
        if edges:
            store.insert_edge(
                GraphEdge(
                    source_id=f"{path}:caller_{i}:1",
                    target_id=f"{target}:main:1",
                    edge_type="CALLS",
                )
            )


def _seed_codegraph_callers(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_codegraph(cwd, edges=True)
    return ["codegraph", "callers", "main"], (_OVER,)


def _seed_codegraph_slice(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_codegraph(cwd, edges=False)
    return ["codegraph", "slice", "main"], (_OVER,)


def _seed_consensus(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    findings = [
        {"path": f"f{i}.py", "line": i, "rule": "r", "severity": "warn", "message": "m"}
        for i in range(_WIDE)
    ]
    a = _write(cwd, "model_a.json", json.dumps(findings))
    b = _write(cwd, "model_b.json", json.dumps(findings))
    return ["consensus", "reconcile", str(a), str(b)], (_OVER,)


def _seed_mistakes(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _git_repo(cwd, {"a.txt": "0\n"})
    for i in range(_WIDE):
        _write(cwd, "a.txt", f"{i + 1}\n")
        _git(cwd, "commit", "-q", "-am", f"change {i}")
        _git(cwd, "revert", "--no-edit", "HEAD")
    return ["context", "mistakes"], ("revert-log",)


def _seed_db_drift(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    models = "from sqlalchemy import Column, Integer\nfrom sqlalchemy.orm import declarative_base\nBase = declarative_base()\n"
    models += "".join(
        f"class M{i}(Base):\n    __tablename__ = 't{i}'\n    id = Column(Integer, primary_key=True)\n"
        for i in range(_WIDE)
    )
    _write(cwd, "src/app/models.py", models)
    _write(cwd, "migrations/0001.sql", "CREATE TABLE unrelated (id INTEGER);\n")
    return ["db-drift"], (_OVER,)


def _seed_flight_recorder(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    from rush.invocation.targets import resolve_logical_root
    from rush.tools.flight_recorder import FlightRecorder

    recorder = FlightRecorder(resolve_logical_root(cwd))
    for i in range(_WIDE):
        recorder.record_event("seeded", "tool_call", {"n": i})
    return ["flight-recorder", "--replay", "seeded"], (_OVER,)


def _seed_governance_check(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "AGENTS.md", "rules\n")
    return ["governance", "check"], ("governance-targets",)


def _seed_governance_sync(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "AGENTS.md", "rules\n")
    return ["governance", "sync"], ("governance-targets",)


def _seed_hallu_guard(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_FINDINGS_WIDE):
        _write(cwd, f"pkg/m{i}.py", f"import phantom_pkg_{i}_zz\n")
    return ["hallu-guard"], (_OVER,)


def _seed_git_files(cwd: Path) -> None:
    _git_repo(
        cwd,
        {f"f{i}.py": _complex_fn(f"fn_{i}", branches=i % 5 + 1) for i in range(_WIDE)},
    )


def _seed_hotspots(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_git_files(cwd)
    return ["hotspots", "analyze"], (_OVER,)


def _seed_bus_factor(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_git_files(cwd)
    return ["hotspots", "bus-factor"], (_OVER,)


def _seed_dead_code(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "unused.py", "".join(f"import os as os_{i}\n" for i in range(_WIDE)))
    return ["hygiene", "dead-code"], (_OVER,)


def _seed_patch_memory(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    from rush.patch.memory import PatchMemoryStore

    store = PatchMemoryStore(cwd)
    for i in range(_WIDE):
        store.record_success(f"error {i}", f"f{i}.py", f"--- a\n+++ b\n@@ {i}\n")
    return ["patch", "memory"], (_OVER,)


def _seed_plan(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    return ["plan", ".", "--profile", "nonbrowser"], (_OVER,)


def _seed_plugin_list(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(
        cwd,
        "rush.toml",
        "".join(
            f'[plugins.p{i}]\ncommand = "python p.py"\ndescription = "plugin {i}"\n'
            for i in range(_WIDE)
        ),
    )
    return ["plugin", "list", "."], (_OVER,)


def _seed_plugin_run(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    findings = [
        {
            "path": "a.py",
            "line": i + 1,
            "rule": "r",
            "severity": "warn",
            "message": f"m{i}",
        }
        for i in range(_FINDINGS_WIDE)
    ]
    _write(
        cwd,
        "plugins/seeded/plugin_main.py",
        "import json\nprint(json.dumps({'status': 'warn', 'summary': 'seeded', "
        f"'findings': {findings!r}}}))\n",
    )
    _write(
        cwd,
        "rush.toml",
        '[plugins.seeded]\ncommand = "python plugins/seeded/plugin_main.py"\n',
    )
    trusted = CliRunner().invoke(cli, ["trust", "plugin", "seeded"])
    assert trusted.exit_code == 0, trusted.output
    return ["plugin", "run", "seeded", "."], (_OVER,)


def _seed_release_check(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "pyproject.toml", 'version = "1.0.0"\n')
    _write(cwd, "package.json", '{"version": "1.0.0"}\n')
    _write(cwd, "Cargo.toml", 'version = "1.0.0"\n')
    return ["release", "check"], ("release-manifests",)


def _seed_scaffold(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    return ["scaffold", "init"], ("scaffold-files",)


def _seed_ship_docs(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "docs/a.md", "".join(f"[x{i}](missing{i}.md)\n" for i in range(_WIDE)))
    return ["ship", "docs"], (_OVER,)


def _seed_ship_env(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(
        cwd,
        "app.py",
        "import os\n" + "".join(f"os.getenv('VAR_{i}')\n" for i in range(_WIDE)),
    )
    return ["ship", "env"], (_OVER,)


def _seed_ship_migration(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_FINDINGS_WIDE):
        _write(cwd, f"migrations/{i:03}.sql", f"ALTER TABLE t{i} DROP COLUMN c;\n")
    return ["ship", "migration"], (_OVER,)


def _seed_ship_pack(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    for i in range(_WIDE):
        _write(cwd, f"src/k{i}.pem", "key\n")
    return ["ship", "pack"], (_OVER,)


def _seed_ship_semver(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    old = _write(
        cwd, "old.py", "".join(f"def f{i}(a):\n    return a\n" for i in range(_WIDE))
    )
    new = _write(cwd, "new.py", "X = 1\n")
    return ["ship", "semver", str(old), str(new)], (_OVER,)


def _seed_simplify(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    f = _write(
        cwd, "complex.py", "\n\n".join(_complex_fn(f"fn_{i}") for i in range(_WIDE))
    )
    return ["simplify", "--file", str(f)], (_OVER,)


def _seed_strictify(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    args = ", ".join(f"a{i}" for i in range(_WIDE))
    f = _write(cwd, "untyped.py", f"def f({args}):\n    return a0\n")
    return ["strictify", "--file", str(f)], (_OVER,)


def _seed_sync_env(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, ".env.example", "".join(f"KEY_{i}=x\n" for i in range(_WIDE)))
    _write(cwd, ".env", "")
    return ["sync", "env"], (_OVER,)


def _seed_trace(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "docs/reqs.md", "".join(f"REQ-{i:04}\n" for i in range(_WIDE)))
    return ["trace"], (_OVER,)


def _seed_packages(cwd: Path) -> None:
    for i in range(_WIDE):
        _write(
            cwd, f"packages/p{i:02}/pyproject.toml", f'[project]\nname = "p{i:02}"\n'
        )
        _write(cwd, f"packages/p{i:02}/mod.py", "X = 1\n")


def _seed_workspace_list(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_packages(cwd)
    return ["workspace", "list", "."], (_OVER,)


def _seed_workspace_affected(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _seed_packages(cwd)
    _git_repo(cwd, {})
    for i in range(_WIDE):
        _write(cwd, f"packages/p{i:02}/mod.py", "X = 2\n")
    return ["workspace", "affected", "."], (_OVER,)


def _seed_workspace_boundary(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "packages/p00/pyproject.toml", '[project]\nname = "p00"\n')
    _write(
        cwd,
        "packages/p00/index.js",
        "".join(f"import '../../shared/m{i}'\n" for i in range(_FINDINGS_WIDE)),
    )
    return ["workspace", "boundary", "."], (_OVER,)


def _seed_workspace_locks(cwd: Path) -> tuple[list[str], tuple[str, ...]]:
    _write(cwd, "pyproject.toml", '[project]\nname = "x"\n')
    _write(cwd, "Cargo.toml", '[package]\nname = "x"\n')
    _write(cwd, "pnpm-workspace.yaml", "packages: []\n")
    return ["workspace", "locks", "."], ("lockfile-rules",)


_SEEDERS: dict[str, Any] = {
    "api-diff": _seed_api_diff,
    "arch-guard": _seed_arch_guard,
    "audit": _seed_audit,
    "benchmark.status": _seed_benchmark_status,
    "bundle.analyze": _seed_bundle_analyze,
    "bundle.dead-assets": _seed_bundle_dead_assets,
    "capabilities": _seed_capabilities,
    "check": _seed_check,
    "codegraph.callers": _seed_codegraph_callers,
    "codegraph.slice": _seed_codegraph_slice,
    "consensus.reconcile": _seed_consensus,
    "context.mistakes": _seed_mistakes,
    "db-drift": _seed_db_drift,
    "flight-recorder": _seed_flight_recorder,
    "gate": _seed_gate,
    "governance.check": _seed_governance_check,
    "governance.sync": _seed_governance_sync,
    "hallu-guard": _seed_hallu_guard,
    "hotspots.analyze": _seed_hotspots,
    "hotspots.bus-factor": _seed_bus_factor,
    "hygiene.dead-code": _seed_dead_code,
    "patch.memory": _seed_patch_memory,
    "plan": _seed_plan,
    "plugin.list": _seed_plugin_list,
    "plugin.run": _seed_plugin_run,
    "release.check": _seed_release_check,
    "scaffold.init": _seed_scaffold,
    "ship.docs": _seed_ship_docs,
    "ship.env": _seed_ship_env,
    "ship.migration": _seed_ship_migration,
    "ship.pack": _seed_ship_pack,
    "ship.semver": _seed_ship_semver,
    "simplify": _seed_simplify,
    "strictify": _seed_strictify,
    "sync.env": _seed_sync_env,
    "trace": _seed_trace,
    "workspace.affected": _seed_workspace_affected,
    "workspace.boundary": _seed_workspace_boundary,
    "workspace.list": _seed_workspace_list,
    "workspace.locks": _seed_workspace_locks,
}


def _allow_only_seed_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real spawns for the engines the seeded lists come from; every other
    engine (network scanners, aislop, ...) stays unavailable."""
    real_popen = subprocess.Popen

    class _SeedEnginePopen(real_popen):
        def __init__(self, args: Any, *rest: Any, **kwargs: Any) -> None:
            argv0 = args[0] if isinstance(args, list | tuple) else str(args).split()[0]
            name = Path(str(argv0)).name
            if name not in _SEED_ENGINES and str(argv0) != sys.executable:
                raise FileNotFoundError(f"phase70-t27: {name} not a seeded engine")
            super().__init__(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", _SeedEnginePopen)


# Seeded routes whose engine output comes from a process-boundary stub: CI's
# quality job does not install radon (its tests are needs_radon-deselected).
_RADON_STUBBED_ROUTES = {"gate"}


def _radon_cc_stub(real: Any) -> Any:
    """radon's `cc --json` report for the seeded files, at the process
    boundary; every other spawn goes to `real`. Complexity is 1 + the
    function's `if` count, radon's McCabe value for `_complex_fn`."""
    import ast

    def run(exec_argv: list[str], argv: list[str], **kwargs: Any) -> Any:
        name, args = Path(argv[0]).name, list(argv[1:])
        if name != "radon":
            return real(exec_argv, argv, **kwargs)
        if args == ["--version"]:
            return subprocess.CompletedProcess(
                argv, 0, f"radon {_ENGINE_VERSIONS['radon']}\n", ""
            )
        assert args[:2] == ["cc", "--json"], args
        report = {
            target: [
                {
                    "type": "function",
                    "name": node.name,
                    "lineno": node.lineno,
                    "complexity": 1
                    + sum(isinstance(n, ast.If) for n in ast.walk(node)),
                }
                for node in ast.parse(Path(target).read_text(encoding="utf-8")).body
                if isinstance(node, ast.FunctionDef)
            ]
            for target in args[2:]
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")

    return run


def _run_seeded(
    route_id: str, workdir: Path, *, as_json: bool
) -> tuple[Any, list[tuple[int, int]], tuple[str, ...]]:
    from contextlib import ExitStack

    import rush.cli as cli_module
    from rush.cli_support import rendering
    from rush.runtime import subprocesses
    from rush.theme import ROW_CAP

    real = rendering.echo_rows
    calls: list[tuple[int, int]] = []

    def spy(rows: Any, line: Any, **kwargs: Any) -> None:
        rows = list(rows)
        calls.append((len(rows), kwargs.get("cap", ROW_CAP)))
        real(rows, line, **kwargs)

    workdir.mkdir(parents=True)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=workdir) as cwd:
        argv, expectations = _SEEDERS[route_id](Path(cwd))
        with pytest.MonkeyPatch.context() as patch, ExitStack() as stack:
            patch.setattr(cli_module, "echo_rows", spy)
            _allow_only_seed_engines(patch)
            if route_id in _RADON_STUBBED_ROUTES:
                _stub_binaries_on_path(stack, ["radon"])
                for target in (
                    "_run_subprocess_blocking",
                    "_run_subprocess_cancellable",
                ):
                    patch.setattr(
                        subprocesses,
                        target,
                        _radon_cc_stub(getattr(subprocesses, target)),
                    )
            result = runner.invoke(cli, argv + (["--json"] if as_json else []))
    _assert_real_exercise(result)
    return result, calls, expectations


_REAL_SUBPROCESS_TESTS.add(
    "test_t27_collection_route_with_seeded_data_caps_and_lists_every_row"
)


@pytest.mark.parametrize("route_id", sorted(_COLLECTION_ROUTES))
def test_t27_collection_route_with_seeded_data_caps_and_lists_every_row(
    route_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert route_id in _SEEDERS, f"collection route {route_id!r} has no seeder"
    for var, value in {
        "GIT_AUTHOR_NAME": "Seed",
        "GIT_AUTHOR_EMAIL": "seed@example.invalid",
        "GIT_COMMITTER_NAME": "Seed",
        "GIT_COMMITTER_EMAIL": "seed@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(var, value)
    human, calls, expectations = _run_seeded(
        route_id, tmp_path / "human", as_json=False
    )
    machine, _, _ = _run_seeded(route_id, tmp_path / "json", as_json=True)

    paths = _COLLECTION_ROUTES[route_id]
    assert len(calls) == len(paths) == len(expectations), (
        f"{route_id}: calls={calls} paths={paths} output={human.output!r}"
    )
    payload = json.loads(machine.stdout)
    for (count, cap), dotted, expectation in zip(
        calls, paths, expectations, strict=True
    ):
        assert len(_json_at(payload, dotted)) == count, (
            f"{route_id}: --json {dotted!r} must list all {count} rows"
        )
        if expectation == _OVER:
            assert count > cap, (
                f"{route_id}: seeded {count} rows, cap {cap}: {human.output!r}"
            )
            assert f"shown {cap}/{count}" in human.output, human.output
            assert "full list: rush " in human.output and "--json" in human.output
        else:
            assert expectation in _BOUNDED, expectation
            if expectation != "audit-findings":
                assert count > 0, f"{route_id}: bounded list is empty: {human.output!r}"
            assert f"{count}/{count}" in human.output, human.output
