"""Phase 70 T1: canonical agent guidance skill contract.

Brief: `.scratch/phase-70-design-gate/W1-T1-T7-T23.md`, section "## T1".
Plan packet: `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`, "#### T1".

Per task instructions this is one new, self-contained file (no conftest, no
edits to shared helpers). The brief names a single test
`tests/test_phase70_adoption.py::test_t01_installed_skill_contract`; the
mapping from that one name to the functions below is documented at the
bottom of this module.

Isolation: every test that reaches a host binary/config sets `HOME` (and
`CLAUDE_CONFIG_DIR`/`CODEX_HOME`) to a tmp directory first. No test spawns a
subprocess for a real host CLI and no test performs network I/O. Zero-spawn
is not asserted here (T1 has no zero-spawn requirement of its own); the one
subprocess used is the resource-resolution proof the brief requires, and it
runs the current interpreter with a cleared `PYTHONPATH`.
"""

from __future__ import annotations

import asyncio
import getpass
import importlib.resources
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SKILL_RESOURCE = "agent_assets/skills/rush/SKILL.md"
_EXAMPLE_RE = re.compile(r"```json rush-example\n(.*?)\n```", re.DOTALL)
_REQUIRED_HEADINGS = [
    "## Triggers",
    "## Profiles",
    "## Paths",
    "## Statuses",
    "## Permissions",
    "## Compact recovery",
    "## Memory scope",
    "## Verification limits",
    "## Dead code",
    "## Host namespace mapping",
]
# Brief §7 trust boundary: the skill is guidance only. Project-specific text
# (absolute/user/temp paths, this repo, its plans) and memory-derived text
# (memory ids are uuid4, handoff session ids are 32-hex tokens, handoff
# capabilities are 43-char url-safe tokens; records carry timestamps) must
# never appear in it.
_PROJECT_OR_MEMORY_PATTERNS = [
    re.compile(r"/Users/|/home/|[A-Za-z]:\\Users\\"),
    re.compile(r"/private/|/tmp/|/var/folders/"),
    re.compile(r"rush-cli|\.scratch|worktree|phase[-_ ]?\d", re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r"\b[0-9a-fA-F]{16,}\b"),
    re.compile(r"[A-Za-z0-9_-]{32,}"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]
_SERVED_SKILL_COPIES = (
    SKILL_RESOURCE,
    "agent_assets/claude/skills/rush/SKILL.md",
    "agent_assets/codex/skills/rush/SKILL.md",
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file runs with HOME, XDG and host config dirs under
    tmp, so none can read or write the real HOME, `~/.claude` or `~/.codex`.
    `_isolate_home` below still re-points them per test where it is used."""
    home = tmp_path / "autouse-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(home / var.lower()))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude-config"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex-home"))


# --- local helpers (kept in this file only, per task instructions) ---------


def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated HOME/config dirs so a status/registry read or write never
    touches the real host config, before anything touches a host binary."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude-config"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex-home"))
    return home


def _skill_text() -> str:
    return (
        importlib.resources.files("rush.integrations")
        .joinpath(SKILL_RESOURCE)
        .read_text("utf-8")
    )


def _frontmatter(text: str) -> dict[str, str]:
    """Minimal `key: value` frontmatter reader. No PyYAML dependency: the
    contract only ever needs the two single-line scalar fields checked here."""
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _examples(text: str) -> list[dict[str, Any]]:
    return [json.loads(match) for match in _EXAMPLE_RE.findall(text)]


def _project(tmp_path: Path, *, f401: int = 0, dead: bool = False) -> Path:
    """A git-rooted project fixture. `f401` real unused imports (ruff F401 is
    an 'error'-severity rule; proven live: aggregate status becomes 'fail',
    never 'warn'). `dead` adds one real vulture-detectable unused function
    (proven live: a 60%-confidence finding)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    lines = [f"import os as m{i}\n" for i in range(f401)] or ["x = 1\n"]
    if dead:
        lines.append("def _unused_helper():\n    return 1\n")
    (root / "app.py").write_text("".join(lines), encoding="utf-8")
    return root


def _call(server: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Invoke one MCP tool in-process, return its structured result.
    `RushFastMCP.call_tool` only wraps request-model tools (`rush_project`,
    `rush_scan`, `rush_memory`) in a `CallToolResult`; every other tool
    (proven live against `rush_status`/`rush_lint`/`rush_check`/`rush_dead`)
    still returns the SDK's raw `(content, structured)` tuple."""
    result = asyncio.run(server.call_tool(name, arguments))
    if isinstance(result, tuple):
        return result[1]
    return result.structuredContent


# --- Group A: static content contract (keep-green today) -------------------


def test_t01_skill_resource_resolves_from_subprocess_outside_checkout(
    tmp_path: Path,
) -> None:
    """1: `importlib.resources` resolves the installed skill from a
    subprocess whose cwd is outside the checkout and whose env carries no
    `PYTHONPATH`. Frontmatter: `name: rush`, a single-line, <=1024-char,
    trigger-rich `description`."""
    outside = tmp_path / "outside"
    outside.mkdir()
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.resources as r; "
                "print(r.files('rush.integrations').joinpath("
                f"{SKILL_RESOURCE!r}).read_text('utf-8'), end='')"
            ),
        ],
        cwd=outside,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    frontmatter = _frontmatter(proc.stdout)
    assert frontmatter["name"] == "rush"
    description = frontmatter["description"]
    assert "\n" not in description
    assert len(description) <= 1024
    for trigger in ("commit", "code quality", "dead code"):
        assert trigger in description


def test_t01_required_headings_present() -> None:
    """3: every contract section is present by its exact heading."""
    text = _skill_text()
    for heading in _REQUIRED_HEADINGS:
        assert heading in text, heading


def test_t01_negative_asserts_no_forbidden_claims() -> None:
    """6: text asserts neither "Each takes a path" (not every tool takes
    `path`) nor the narrow "skipped means the engine is not installed" claim
    from the generic MCP server description (`skipped` has three real
    causes: missing engine, no supported targets, or denied permission)."""
    text = _skill_text()
    assert "Each takes a path" not in text
    assert "the underlying engine is not installed" not in text


def test_t01_examples_are_valid_with_required_keys() -> None:
    """4: every `rush-example` fenced block is valid JSON with exactly
    `profile`, `tool`, `arguments`, `expect: {status, raw_operation}`."""
    examples = _examples(_skill_text())
    assert examples, "no rush-example fenced blocks found"
    for example in examples:
        assert set(example) == {"profile", "tool", "arguments", "expect"}
        assert example["profile"] in ("core", "full")
        assert example["tool"].startswith("rush_")
        assert isinstance(example["arguments"], dict)
        assert set(example["expect"]) == {"status", "raw_operation"}
        assert example["expect"]["status"] in ("ok", "warn", "fail", "error", "skipped")


def test_t01_host_namespace_mapping_present() -> None:
    """3 (Host namespace mapping): Claude Code and Codex CLI both map the
    skill to `rush:rush` (owner decision: Cursor is removed from this
    brief; X8 proved the Codex mapping against a real, isolated Codex 0.155.1)."""
    text = _skill_text()
    assert "| Claude Code | `rush:rush` |" in text
    assert "| Codex CLI | `rush:rush` |" in text


def test_t01_docs_user_guide_deliverable_exists() -> None:
    """Deliverable file `docs/user-guide/working-with-ai-agents.md` exists.
    The brief gives no further testable content contract for this file
    beyond its existence as a T1 deliverable, so nothing further is
    asserted here."""
    path = (
        Path(__file__).resolve().parents[1]
        / "docs/user-guide/working-with-ai-agents.md"
    )
    assert path.is_file()


# --- Group B: must-fail cases (real T1 gaps, proven live) -------------------


def test_t01_declares_missing_engine_skipped_example() -> None:
    """6: "Missing-engine example -> skipped with reason." No such example
    exists in the shipped skill today (all 5 examples resolve to
    ok/warn/warn/warn/warn) -- a real, current T1 gap, not a T4 dependency."""
    examples = _examples(_skill_text())
    skipped = [ex for ex in examples if ex["expect"]["status"] == "skipped"]
    assert skipped, (
        "SKILL.md has no example demonstrating a missing-engine 'skipped' result"
    )


def test_t01_lint_example_status_matches_real_ruff_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T1's own bug, independent of T4: the shipped `rush_lint` example
    declares its F401 finding as `warn`, but ruff's F401 is an 'error'
    -severity rule and the router aggregates 'error' severity to a 'fail'
    status (proven live). Executed here against `profile="full"` --
    `rush_lint` is a full-profile tool regardless of which profile the
    example itself declares, so this is provable before T4 lands."""
    _isolate_home(tmp_path, monkeypatch)
    examples = _examples(_skill_text())
    lint_example = next(ex for ex in examples if ex["tool"] == "rush_lint")
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / lint_example["arguments"]["path"]).write_text(
        "import os\n", encoding="utf-8"
    )
    monkeypatch.chdir(root)
    from rush.mcp import build_server

    server = build_server(profile="full")
    result = _call(server, lint_example["tool"], lint_example["arguments"])
    assert result["status"] == lint_example["expect"]["status"], result["summary"]


def test_t01_full_profile_dead_example_executes_as_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6: the one shipped full-profile example (`rush_dead`) executes with
    its exact declared status and `raw_operation` (proven live: keep-green
    guard -- this one already matches its own contract)."""
    _isolate_home(tmp_path, monkeypatch)
    examples = _examples(_skill_text())
    full_examples = [ex for ex in examples if ex["profile"] == "full"]
    assert full_examples, "no full-profile example to execute"
    root = _project(tmp_path, dead=True)
    monkeypatch.chdir(root)
    from rush.mcp import build_server

    server = build_server(profile="full")
    for example in full_examples:
        result = _call(server, example["tool"], example["arguments"])
        assert result["status"] == example["expect"]["status"], result["summary"]
        raw = result.get("raw") or {}
        actual_raw_operation = raw.get("operation") if isinstance(raw, dict) else None
        assert actual_raw_operation == example["expect"]["raw_operation"]


def test_t01_core_profile_examples_execute_as_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED-via-T4: `build_server(profile="core")` raises `ValueError`
    ("unknown MCP profile 'core'; valid profiles: full") today because the
    core profile does not exist until T4 lands (X-ORD: T1 runs before T5,
    but after T4). This still asserts T1's own contract exactly: once a
    core profile exists, every core-profile example's declared tool and
    arguments must produce exactly its declared status and raw_operation.
    Arrange step only: register the fixture root through the real,
    documented `register_project` (never a guessed registry file name) so
    this is ready to execute the moment `profile="core"` is accepted."""
    _isolate_home(tmp_path, monkeypatch)
    examples = _examples(_skill_text())
    core_examples = [ex for ex in examples if ex["profile"] == "core"]
    assert core_examples, "no core-profile example to execute"
    # Brief §3: "tmp registered project with a known F401 file". The
    # pyproject.toml makes `rush_test` find the project, so the denied call is
    # a permission skip, not a no-supported-targets skip.
    root = _project(tmp_path, f401=1)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    from rush.workflows.projects import register_project

    record = register_project(root)
    assert record.root == str(root.resolve())

    from rush.mcp import build_server

    server = build_server(profile="core")
    for example in core_examples:
        result = _call(server, example["tool"], example["arguments"])
        assert result["status"] == example["expect"]["status"], result["summary"]


def test_t01_check_example_test_step_distinguishes_permission_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6: "Granted vs denied allow_build for check" -- the `test` step of a
    real `rush_check` run is `skipped` naming the withheld permission when
    `allow_build` is omitted, and is a distinct, executed outcome when
    granted (proven live). Asserted on the `test` child only, not on
    `rush_check`'s own aggregate status: this environment's `slop` step
    independently errors even on a trivial one-line fixture (proven live,
    confirmed unrelated to permissions or to this fixture), so the
    aggregate status is not a reliable signal here."""
    _isolate_home(tmp_path, monkeypatch)
    root = _project(tmp_path, f401=1)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0"\n', encoding="utf-8"
    )
    monkeypatch.chdir(root)
    from rush.mcp import build_server

    server = build_server(profile="full")

    def _test_child(result: dict[str, Any]) -> dict[str, Any]:
        children = (result.get("metadata") or {}).get("children") or []
        return next(child for child in children if child["tool"] == "test")

    denied = _test_child(_call(server, "rush_check", {"path": "."}))
    granted = _test_child(
        _call(server, "rush_check", {"path": ".", "allow_build": True})
    )
    assert denied["status"] == "skipped"
    assert "allow-build" in denied["summary"]
    assert (
        granted["status"] != denied["status"] or granted["summary"] != denied["summary"]
    )


def test_t01_skill_is_guidance_only_without_secrets_or_memory_text() -> None:
    """7 (trust boundary): the served skill (canonical resource and both host
    copies) is guidance only. The shared redactor changes nothing in it (no
    secret-shaped text), and it holds no project-specific or memory-derived
    strings."""
    from rush.safety.redactor import sanitize_value

    login = getpass.getuser().lower()
    assets = importlib.resources.files("rush.integrations")
    for resource in _SERVED_SKILL_COPIES:
        text = assets.joinpath(resource).read_text("utf-8")
        sanitized = sanitize_value(text)
        assert sanitized.value == text, resource
        assert not sanitized.redacted, resource
        for pattern in _PROJECT_OR_MEMORY_PATTERNS:
            match = pattern.search(text)
            assert match is None, (resource, pattern.pattern, match and match.group())
        if len(login) >= 3:
            assert login not in text.lower(), resource


# --- Mapping to the brief's single test name --------------------------------
#
# Brief: tests/test_phase70_adoption.py::test_t01_installed_skill_contract
#
# Split here (task instructions: one new file, brief test names kept) into:
#   test_t01_skill_resource_resolves_from_subprocess_outside_checkout
#   test_t01_required_headings_present
#   test_t01_negative_asserts_no_forbidden_claims
#   test_t01_examples_are_valid_with_required_keys
#   test_t01_host_namespace_mapping_present
#   test_t01_docs_user_guide_deliverable_exists
#   test_t01_declares_missing_engine_skipped_example
#   test_t01_lint_example_status_matches_real_ruff_severity
#   test_t01_full_profile_dead_example_executes_as_declared
#   test_t01_core_profile_examples_execute_as_declared
#   test_t01_check_example_test_step_distinguishes_permission_denial
#   test_t01_skill_is_guidance_only_without_secrets_or_memory_text
