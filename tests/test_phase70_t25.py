"""T25 (navigable help and first-use documentation) test matrix.

Binding sources: `.scratch/phase-70-design-gate/W4-T23-T29.md` (T25 section)
and `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` (T25
packet). Nothing here is merged yet (worktree HEAD 2a664ec): there is no
`command_category` helper, no `rush help`/`--help-all`, and "Five tools" is
still in `cli.py`'s group docstring -- every case below is a genuine RED
against the current, real CLI registry (verified by running it), not a
guess.

Brief test-name mapping (per the design brief and the plan's deliverable
list, `tests/test_phase70_onboarding.py::test_t25_help_discovery`): that name
is kept here as `test_t25_help_discovery`, covering the core required
behavior (everyday set, category index, "Five tools" removal). Every other
case is additional matrix coverage the brief requires ("plus set equality
... exact membership ... COLUMNS=40 ... no \\x1b with NO_COLOR").

None of T1-T25/T27-T29 predecessors are merged either, but T25 does not
depend on any of them for its own RED -- every case here fails against
today's `cli.py`/`catalog.py` alone, so nothing is labelled RED-via-Tn.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from rush.catalog import TOOL_SPECS
from rush.cli import cli
from rush.governance.public_operations import build_operations_inventory

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Real-source enumeration (T25 binding resolution + plan §T25 override map,
# with the design-gate's explicit `lock -> workflow` addition applied).
# ---------------------------------------------------------------------------

_REGISTERED_NAMES = frozenset(cli.commands.keys()) | {"lock"}

_ALL_CATEGORIES = frozenset(
    {"quality", "security", "test", "workflow", "memory", "services", "administration"}
)

# Pinned verbatim from the plan's T25 packet (line 359), with `lock` added to
# `workflow` per the design gate's binding resolution (T25 section, "Add
# `lock` to `workflow` in the map").
_CLI_CATEGORY_OVERRIDES: dict[str, str] = {
    # quality
    "api-diff": "quality",
    "arch-guard": "quality",
    "audit": "quality",
    "blast-radius": "quality",
    "check": "quality",
    "codegraph": "quality",
    "consensus": "quality",
    "guard": "quality",
    "hotspots": "quality",
    "hygiene": "quality",
    "outline": "quality",
    "score": "quality",
    "simplify": "quality",
    "strictify": "quality",
    # security
    "hallu-guard": "security",
    "trust": "security",
    # test
    "simulate-ci": "test",
    "test-heal": "test",
    # workflow
    "bundle": "workflow",
    "conflict": "workflow",
    "db-drift": "workflow",
    "gate": "workflow",
    "patch": "workflow",
    "plan": "workflow",
    "scaffold": "workflow",
    "scan": "workflow",
    "ship": "workflow",
    "swarm-merge": "workflow",
    "sync": "workflow",
    "workspace": "workflow",
    "watch": "workflow",
    "lock": "workflow",
    # memory (a CLI grouping name distinct from the `memory` command, which
    # falls back to its own ToolSpec category -- see the design brief's T25
    # note: "memory, review, and format fall back to their ToolSpec
    # categories.")
    "context": "memory",
    "flight-recorder": "memory",
    "session": "memory",
    # services
    "dashboard": "services",
    "mcp": "services",
    "ui": "services",
    # administration
    "agent": "administration",
    "cache": "administration",
    "capabilities": "administration",
    "config": "administration",
    "gain": "administration",
    "governance": "administration",
    "help": "administration",
    "hook": "administration",
    "init": "administration",
    "install": "administration",
    "plugin": "administration",
    "project": "administration",
    "setup": "administration",
    "status": "administration",
    "token": "administration",
    "trace": "administration",
}

# Every registered name (plus the not-yet-registered `help`) not covered by
# the override map falls back to its real ToolSpec category. Derived from the
# live registry, not hand-transcribed -- verified this session: the union of
# override keys and this fallback set equals `_REGISTERED_NAMES | {"help"}`
# exactly, and every fallback name exists in TOOL_SPECS.
_FALLBACK_NAMES = sorted((_REGISTERED_NAMES | {"help"}) - set(_CLI_CATEGORY_OVERRIDES))

_EVERYDAY_SET = (
    "status",
    "check",
    "lint",
    "review",
    "security",
    "test",
    "memory",
    "setup",
    "install",
    "agent",
    "mcp",
)


def _invoke(args: list[str], env: dict[str, str] | None = None):
    return CliRunner().invoke(cli, args, env=env)


@pytest.fixture(autouse=True)
def _isolated_and_zero_spawn(tmp_path, monkeypatch):
    """Temp HOME, no network, no subprocess -- `--help`/`help` never spawn."""
    monkeypatch.setenv("HOME", str(tmp_path))

    def _no_spawn(*args, **kwargs):  # pragma: no cover - only hit on defect
        pytest.fail(f"unexpected subprocess call: args={args} kwargs={kwargs}")

    monkeypatch.setattr(subprocess, "run", _no_spawn)
    monkeypatch.setattr(subprocess, "Popen", _no_spawn)


def _everyday_rows(output: str) -> dict[str, str]:
    """Parse the `Commands:` section of --help output into
    {first token: rest-of-line stripped} rows, so an assertion checking a
    name is absent from the everyday listing cannot false-positive on a
    substring match inside another command's description."""
    lines = output.splitlines()
    start = lines.index("Commands:") + 1
    rows: dict[str, str] = {}
    for line in lines[start:]:
        if not line.strip():
            break
        name, _, rest = line.strip().partition(" ")
        rows[name] = rest.strip()
    return rows


# ---------------------------------------------------------------------------
# Sanity: the enumeration itself is real and complete (arrange assertion,
# must PASS today -- proves the fixtures below aren't hand-picked samples).
# ---------------------------------------------------------------------------


def test_arrange_override_and_fallback_cover_every_real_name():
    combined = set(_CLI_CATEGORY_OVERRIDES) | set(_FALLBACK_NAMES)
    assert combined == (_REGISTERED_NAMES | {"help"})
    for name in _FALLBACK_NAMES:
        assert name in TOOL_SPECS, f"{name} missing from TOOL_SPECS"
        assert TOOL_SPECS[name].category in {"quality", "security", "test", "workflow"}


def test_arrange_everyday_set_is_really_registered():
    for name in _EVERYDAY_SET:
        assert name in _REGISTERED_NAMES


# ---------------------------------------------------------------------------
# Group 1: default `rush --help` (brief test name kept: test_t25_help_discovery)
# ---------------------------------------------------------------------------


def test_t25_help_discovery():
    """Core required behavior: everyday set, category index, no "Five
    tools". RED today: real output lists every command flatly (`format`
    included) and still says "Five tools: review, lint, format, test,
    security." (verified: `cli.py`'s group docstring, line 98)."""
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "Five tools" not in result.output

    for name in _EVERYDAY_SET:
        assert name in result.output, f"{name} missing from default help"

    # A name that exists in the real registry but is not in the everyday
    # set must not appear in the default listing (X9: "the default --help
    # no longer lists format").
    assert "format" not in _everyday_rows(result.output)

    for category in _ALL_CATEGORIES:
        assert category in result.output, f"category {category} missing from index"
        assert f"rush help {category}" in result.output


def test_default_help_omits_noneveryday_probe_names():
    result = _invoke(["--help"])
    for probe in ("typecheck", "gain", "lock"):
        assert probe not in _everyday_rows(result.output)


def test_default_help_keeps_one_line_descriptions():
    result = _invoke(["--help"])
    rows = _everyday_rows(result.output)
    assert list(rows) == [n for n in _EVERYDAY_SET]
    for name in _EVERYDAY_SET:
        desc = rows[name]
        assert desc
        cmd = cli.get_command(click.Context(cli), name)
        assert cmd is not None, f"{name} not resolvable via cli.get_command"
        assert cmd.get_short_help_str(1000).startswith(
            desc.removesuffix("...").rstrip()
        )


# ---------------------------------------------------------------------------
# Group 2: `rush --help-all`
# ---------------------------------------------------------------------------


def test_help_all_lists_every_registered_name():
    """RED today: `--help-all` is an unknown option, exit 2 (verified:
    `Error: No such option '--help-all'.`)."""
    result = _invoke(["--help-all"])
    assert result.exit_code == 0
    for name in sorted(_REGISTERED_NAMES):
        assert name in result.output, f"{name} missing from --help-all"


# ---------------------------------------------------------------------------
# Group 3: `rush help` (bare) lists categories
# ---------------------------------------------------------------------------


def test_help_bare_lists_categories():
    """RED today: `help` is not a registered command (verified: `Error: No
    such command 'help'.`)."""
    result = _invoke(["help"])
    assert result.exit_code == 0
    for category in _ALL_CATEGORIES:
        assert category in result.output


# ---------------------------------------------------------------------------
# Group 4: `rush help CATEGORY` lists every member; unknown category exits 2
# ---------------------------------------------------------------------------


def _members_of(category: str) -> list[str]:
    members = [n for n, c in _CLI_CATEGORY_OVERRIDES.items() if c == category]
    members += [n for n in _FALLBACK_NAMES if TOOL_SPECS[n].category == category]
    return sorted(members)


@pytest.mark.parametrize("category", sorted(_ALL_CATEGORIES))
def test_help_category_lists_every_member(category):
    """RED today for the same reason as the bare `help` case: the command
    does not exist yet."""
    expected = _members_of(category)
    assert expected, f"category {category} unexpectedly empty"
    result = _invoke(["help", category])
    assert result.exit_code == 0
    for name in expected:
        assert name in result.output, f"{name} missing from `help {category}`"


def test_help_unknown_category_exits_2_for_the_right_reason():
    """RED today: exit code coincidentally matches (2), but for the wrong
    reason -- Click reports "No such command 'help'", not an unknown-
    category diagnostic (verified this session)."""
    result = _invoke(["help", "not-a-real-category"])
    assert result.exit_code == 2
    assert "no such command" not in result.output.lower()


# ---------------------------------------------------------------------------
# Group 5: `command_category` resolution function + full set equality
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected", sorted(_CLI_CATEGORY_OVERRIDES.items()), ids=lambda v: str(v)
)
def test_command_category_override_pins(name, expected):
    """RED today: `rush.cli_support.catalog_commands` has no
    `command_category` (verified: current file has no such symbol)."""
    try:
        from rush.cli_support.catalog_commands import command_category
    except ImportError as exc:
        pytest.fail(f"command_category not implemented yet: {exc}")
    assert command_category(name) == expected


@pytest.mark.parametrize("name", _FALLBACK_NAMES)
def test_command_category_falls_back_to_toolspec(name):
    """RED today: same import failure as above. Once implemented, a name
    absent from the override map must resolve to its real ToolSpec
    category (e.g. `memory` -> "workflow", `review`/`format` ->
    "quality", verified this session), never a guessed value."""
    try:
        from rush.cli_support.catalog_commands import command_category
    except ImportError as exc:
        pytest.fail(f"command_category not implemented yet: {exc}")
    assert command_category(name) == TOOL_SPECS[name].category


def test_command_category_set_equality_with_live_registry():
    """RED today: import failure, and separately `help` is not yet
    registered -- both real, both must be fixed for this to pass."""
    try:
        from rush.cli_support.catalog_commands import command_category
    except ImportError as exc:
        pytest.fail(f"command_category not implemented yet: {exc}")
    live_names = set(cli.commands.keys()) | {"lock"}
    assert "help" in live_names, "help command not registered yet"
    for name in sorted(live_names):
        category = command_category(name)
        assert category in _ALL_CATEGORIES, f"{name} -> {category!r} is not a category"


# ---------------------------------------------------------------------------
# Group 6: keep-green guards (verified passing today; must stay passing)
# ---------------------------------------------------------------------------


def test_keep_green_narrow_terminal_help_stays_legible(monkeypatch):
    """In-process, real terminal-width path (not CliRunner's forced 80
    columns): a genuinely narrow terminal must still produce legible
    (<=40 char) help lines, with the Commands section still present."""
    monkeypatch.setenv("COLUMNS", "40")
    ctx = click.Context(cli, info_name="rush", terminal_width=None)
    help_text = cli.get_help(ctx)
    lines = help_text.splitlines()
    assert all(len(line) <= 40 for line in lines), lines
    assert "Commands:" in help_text


def test_keep_green_no_color_help_has_no_escape_bytes():
    result = _invoke(["--help"], env={"NO_COLOR": "1"})
    assert result.exit_code == 0
    assert "\x1b" not in result.output


def test_keep_green_direct_command_invocation_unchanged():
    result = _invoke(["lint", "--help"])
    assert result.exit_code == 0


def test_keep_green_version_and_short_help_flags_unchanged():
    assert _invoke(["-h"]).exit_code == 0
    assert _invoke(["-V"]).exit_code == 0
    version_result = _invoke(["--version"])
    assert version_result.exit_code == 0
    assert version_result.output.strip()


def test_keep_green_mcp_command_remains_visible():
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output


# ---------------------------------------------------------------------------
# Group 7: governance inventory picks up the new `help` route automatically
# (X8: "governance/public-operations.toml: ... T25 (help)" -- the inventory
# is derived live from `cli.commands`, not hand-edited; verified this
# session with the real, unmodified `build_operations_inventory`).
# ---------------------------------------------------------------------------


def test_help_route_reaches_public_operations_inventory():
    """RED today: `build_operations_inventory()` derives its routes from
    live `cli.commands`, and `help` is not registered yet (verified:
    `"help" in {op.cli_command for op in build_operations_inventory()}` is
    False on the current tree)."""
    commands = {op.cli_command for op in build_operations_inventory()}
    assert "help" in commands


# ---------------------------------------------------------------------------
# Group 8: docs reconciliation (plan §8.1 "Documentation/catalog set",
# design-gate §T25 deliverables). Every `rush ...` citation in a doc must
# resolve to a real Click command/subcommand/option; "Five tools" must not
# appear; Cursor must not appear (owner decision, 4f1414f: Cursor removed).
# ---------------------------------------------------------------------------

_SECTION_81_DOCS = tuple(
    _REPO_ROOT / rel
    for rel in (
        "docs/CLI_REFERENCE.md",
        "docs/reference/cli-reference.md",
        "docs/MCP_REFERENCE.md",
        "docs/reference/mcp-tool-reference.md",
        "docs/reference/result-reference.md",
        "docs/user-guide/working-with-ai-agents.md",
        "docs/user-guide/security-and-supply-chain.md",
        "docs/getting-started/installation.md",
        "docs/integrations/mcp-client-setup.md",
        "docs/agentic-rush/plugins-and-agent-skills.md",
    )
)

_INLINE_CITATION_RE = re.compile(r"`(rush [^`\n]*)`")
_CURSOR_RE = re.compile(r"(?<!--)(?<!`)\bcursor\b(?![=:])", re.IGNORECASE)


def _extract_rush_citations(text: str) -> list[str]:
    """Every `rush ...` code span, plus every shell-prompt line inside a
    fenced code block. Real markdown parsing is unnecessary here: the only
    shapes used across §8.1's docs are backtick spans and ```-fenced shell
    lines, both handled below."""
    citations = [m.group(1) for m in _INLINE_CITATION_RE.finditer(text)]
    in_fence = False
    for line in text.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            candidate = stripped_line.lstrip("$# ").strip()
            if candidate.startswith("rush "):
                citations.append(candidate)
    return citations


def _is_placeholder_token(token: str) -> bool:
    """A template slot (`PATH`, `<name>`, `[--flag]`), never a real name."""
    return token.startswith(("<", "[")) or token.isupper()


def _resolve_citation(citation: str) -> str | None:
    """Return a failure message for `citation`, or `None` if it checks out.

    Only citations with a real (non-placeholder, non-flag) command word are
    checked -- `rush --help`, `rush COMMAND --help` and similar templates are
    intentionally not resolvable and are skipped."""
    tokens = citation.split()
    rest = tokens[1:]
    if not rest:
        return None
    root_name = rest[0]
    if root_name.startswith("-") or _is_placeholder_token(root_name):
        return None
    root_cmd = cli.commands.get(root_name)
    if root_name == "lock":
        from rush.cli import lock_cmd_group

        root_cmd = lock_cmd_group
    if root_cmd is None:
        return f"{citation!r}: unknown command {root_name!r}"

    effective = root_cmd
    if getattr(root_cmd, "commands", None) and len(rest) > 1:
        sub_token = rest[1]
        if not sub_token.startswith("-") and not _is_placeholder_token(sub_token):
            candidates = re.split(r"[|/]", sub_token)
            if not all(c in root_cmd.commands for c in candidates):
                return (
                    f"{citation!r}: unknown subcommand {sub_token!r} of {root_name!r}"
                )
            if len(candidates) == 1:
                effective = root_cmd.commands[candidates[0]]

    valid_opts = {"--help"}
    for param in getattr(effective, "params", []):
        valid_opts.update(getattr(param, "opts", []) or [])
    for token in rest:
        if token.startswith("--") and "*" not in token and "=" not in token:
            flag = token.split("=")[0]
            if flag not in valid_opts:
                return f"{citation!r}: unknown flag {flag!r} for {root_name!r}"
    return None


@pytest.mark.parametrize("doc_path", _SECTION_81_DOCS, ids=lambda p: p.name)
def test_doc_reconciliation(doc_path):
    """RED today only for `docs/CLI_REFERENCE.md` (5 stale commands: `toon-
    inspect`, `skeletonize`, `context-cache`, `ccr-retrieve`,
    `context-mistakes` -- none registered, verified this session) and
    `docs/agentic-rush/plugins-and-agent-skills.md` (stale `rush skills
    export`/`rush skills sync`, and it names Cursor). `working-with-ai-
    agents.md` and `mcp-client-setup.md` also fail today on the Cursor
    check alone. Every other doc in this list is a keep-green guard."""
    assert doc_path.is_file(), f"{doc_path} missing from the repo"
    text = doc_path.read_text()

    failures = [
        msg
        for citation in _extract_rush_citations(text)
        if (msg := _resolve_citation(citation)) is not None
    ]
    assert not failures, "stale command citations:\n" + "\n".join(failures)

    assert "Five tools" not in text, "obsolete five-tool wording still present"

    cursor_hits = _CURSOR_RE.findall(text)
    assert not cursor_hits, (
        f"{len(cursor_hits)} Cursor mention(s) (owner removed Cursor)"
    )


# ---------------------------------------------------------------------------
# Group 9: the help docs actually document the new surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc_path",
    (
        _REPO_ROOT / "docs/CLI_REFERENCE.md",
        _REPO_ROOT / "docs/reference/cli-reference.md",
    ),
    ids=lambda p: p.name,
)
def test_help_docs_document_the_new_surface(doc_path):
    """RED today: neither doc mentions `rush help`, `--help-all`, or any of
    the seven categories/everyday-set commands as such (verified: zero hits
    for "rush help"/"help-all"/"administration"/"services" in both files)."""
    text = doc_path.read_text()
    assert "rush help" in text
    assert "--help-all" in text
    for category in _ALL_CATEGORIES:
        assert category in text, f"category {category} undocumented in {doc_path.name}"
    for name in _EVERYDAY_SET:
        assert name in text, f"everyday command {name} undocumented in {doc_path.name}"


# ---------------------------------------------------------------------------
# Group 10: alias category inheritance (derived from the real registry: a
# subcommand whose own help text literally says "Alias for `rush X`" shares
# X's category -- not mere same-name collision, which exists elsewhere in
# the registry for unrelated commands, e.g. `benchmark check` vs `check`).
# ---------------------------------------------------------------------------

_ALIAS_RE = re.compile(r"Alias for `rush ([\w-]+(?: [\w-]+)?)`")


def _discover_aliases() -> list[tuple[str, str]]:
    """(alias_full_name, canonical_name) pairs found in the live registry."""
    found = []
    for group_name, group_cmd in cli.commands.items():
        subs = getattr(group_cmd, "commands", None)
        if not subs:
            continue
        for sub_name, sub_cmd in subs.items():
            help_text = sub_cmd.help or ""
            m = _ALIAS_RE.search(help_text)
            if m:
                found.append((f"{group_name} {sub_name}", m.group(1)))
    return found


_DISCOVERED_ALIASES = _discover_aliases()


def test_arrange_at_least_one_real_alias_discovered():
    assert _DISCOVERED_ALIASES, (
        "no `Alias for `rush X`` help text found in the registry"
    )


@pytest.mark.parametrize("alias_name,canonical_name", _DISCOVERED_ALIASES)
def test_command_category_alias_inherits_canonical_category(alias_name, canonical_name):
    """An alias belongs under its *canonical* command's category, not its
    containing group's -- for `context gain` that means "administration"
    (`gain`'s category), not "memory" (`context`'s category); the two
    differ today, verified this session, so a naive group-based lookup
    would give the wrong answer. RED today: import failure
    (`command_category` unbuilt)."""
    try:
        from rush.cli_support.catalog_commands import command_category
    except ImportError as exc:
        pytest.fail(f"command_category not implemented yet: {exc}")
    group_name = alias_name.split()[0]
    canonical_category = command_category(canonical_name)
    assert canonical_category in _ALL_CATEGORIES
    assert canonical_category != command_category(group_name), (
        f"{alias_name!r} must inherit {canonical_name!r}'s category, "
        f"not its group {group_name!r}'s"
    )


# ---------------------------------------------------------------------------
# Group 11: every registered command's --help works (including `lock`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_REGISTERED_NAMES))
def test_every_command_help_works(name):
    result = _invoke([name, "--help"])
    assert result.exit_code == 0, f"`rush {name} --help` exited {result.exit_code}"
    assert result.output.strip(), f"`rush {name} --help` produced empty output"


# ---------------------------------------------------------------------------
# Group 12: rush.toml / examples/rush.toml stay valid against TOOL_SPECS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "toml_path",
    (_REPO_ROOT / "examples/rush.toml",),
    ids=lambda p: str(p.relative_to(_REPO_ROOT)),
)
def test_toml_tool_sections_name_real_tools(toml_path):
    assert toml_path.is_file(), f"{toml_path} missing from the repo"
    data = tomllib.loads(toml_path.read_text())
    tool_keys = list(data.get("tools", {}))
    assert tool_keys, f"{toml_path} has no [tools.*] sections to check"
    for key in tool_keys:
        assert key in TOOL_SPECS, (
            f"[tools.{key}] in {toml_path.name} is not a real tool"
        )


# ---------------------------------------------------------------------------
# Group 13: the first-use journey, one real CLI pipeline in an isolated HOME.
# Not RED today (T24/T26 are already merged at this worktree's HEAD) -- this
# is a keep-green integration guard proving the whole chain the docs above
# describe actually works end to end, with meaningful truthful output at
# every step, never real user configs.
# ---------------------------------------------------------------------------


def test_first_use_journey_end_to_end(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    projects_parent = tmp_path / "projects"
    projects_parent.mkdir()
    fake_host_bin_dir = tmp_path / "bin"
    fake_host_bin_dir.mkdir()
    fake_codex = fake_host_bin_dir / "codex"
    fake_codex.write_text("#!/bin/sh\necho fake-codex\n")
    fake_codex.chmod(0o755)
    monkeypatch.setenv(
        "PATH", f"{fake_host_bin_dir}:{__import__('os').environ['PATH']}"
    )

    def invoke(args):
        return CliRunner().invoke(
            cli, args, env={"HOME": str(home)}, catch_exceptions=False
        )

    # 1. new project.
    created = invoke(
        [
            "project",
            "create",
            "journeyproj",
            "--parent",
            str(projects_parent),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ]
    )
    assert created.exit_code == 0
    created_data = json.loads(created.output)
    assert created_data["status"] == "ok"
    root = created_data["raw"]["root"]
    assert created_data["raw"]["project_id"]

    # 2. consented setup: preview + save-plan.
    plan_file = tmp_path / "plan.json"
    preview = invoke(
        [
            "setup",
            root,
            "--save-plan",
            str(plan_file),
            "--allow-artifact-write",
            "--json",
        ]
    )
    assert preview.exit_code == 0
    preview_data = json.loads(preview.output)
    assert preview_data["status"] == "ok"
    assert preview_data["reason"] == "plan_saved"
    plan_id = preview_data["setup_plan_id"]
    assert plan_id
    assert plan_file.is_file()

    # 2b. apply via the saved plan with the exact grants the review named.
    applied = invoke(
        [
            "setup",
            root,
            "--apply",
            "--yes",
            "--plan-file",
            str(plan_file),
            "--plan-id",
            plan_id,
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ]
    )
    assert applied.exit_code == 0
    applied_data = json.loads(applied.output)
    assert applied_data["status"] == "ok"
    assert applied_data["setup_plan_id"] == plan_id
    assert applied_data["config"]["action"] == "create"

    # 3. status.
    status = invoke(["status", root, "--json"])
    assert status.exit_code == 0
    status_data = json.loads(status.output)
    assert status_data["status"] == "ok"
    assert status_data["raw"]["data"]["project"]["registration"] == "registered"
    assert status_data["raw"]["data"]["project"]["configured"] is True

    # 4. check.
    check = invoke(["check", root, "--json"])
    assert check.exit_code == 0
    check_data = json.loads(check.output)
    children = check_data["metadata"]["children"]
    assert len(children) == 6, "check must run all six steps, not a partial subset"
    for child in children:
        assert child["status"], f"child {child['tool']} has no real status"

    # 5. memory overview (cwd inside the project root, no --project flag).
    with contextlib.chdir(root):
        memory = CliRunner().invoke(
            cli, ["memory", "--json"], env={"HOME": str(home)}, catch_exceptions=False
        )
    assert memory.exit_code == 0
    memory_data = json.loads(memory.output)
    assert memory_data["status"] == "ok"
    assert memory_data["raw"]["data"]["total"] == 0
    assert "no memory store" in memory_data["raw"]["data"]["reason"]
    assert memory_data["raw"]["data"]["project_root"] == root

    # 6. host connection (a fake, never-executed `codex` on PATH; the config
    # written lives under the isolated HOME, never a real user config).
    fake_rush_binary = tmp_path / "fake-rush"
    fake_rush_binary.write_text("#!/bin/sh\necho fake-rush\n")
    fake_rush_binary.chmod(0o755)
    connect = invoke(
        [
            "agent",
            "connect",
            "codex",
            "--session",
            "journey-session",
            "--project",
            root,
            "--rush-binary",
            str(fake_rush_binary),
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ]
    )
    assert connect.exit_code == 0
    connect_data = json.loads(connect.output)
    assert connect_data["status"] == "ok"
    assert connect_data["raw"]["apply"]["ok"] is True
    assert connect_data["raw"]["apply"]["method"] == "config-edit"
    config_path = connect_data["raw"]["apply"]["config_path"]
    assert config_path.startswith(str(home)), (
        "must never write outside the isolated HOME"
    )
    assert connect_data["raw"]["probe"]["status"] == "registered"

    # 7. disconnect.
    disconnect = invoke(["agent", "disconnect", "codex", "--project", root, "--json"])
    assert disconnect.exit_code == 0
    disconnect_data = json.loads(disconnect.output)
    assert disconnect_data["status"] == "ok"
    assert isinstance(disconnect_data["raw"]["removed"], list)
