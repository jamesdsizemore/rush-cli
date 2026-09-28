"""Phase 70 T3 -- consent-aware host instructions and disconnect. RED phase.

Test matrix for T3 ("Consent-aware instructions and disconnect") per
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` (packet at
"#### T3") and `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` ("## T3",
binding design, no open decisions).

None of this behavior exists yet: `rush.integrations.agents` has no
instruction-block planner/applier/disconnect, `rush.tools.agent_connection`
has no `disconnect` action, and `rush.cli` has no `agent disconnect` command
and no `--install-guidance` flag. Every test below fails today for that
reason -- ImportError/AttributeError/click usage error, or an assertion that
the not-yet-existing marker/guidance/ledger artifact is present -- never a
fixture bug. Cursor is out of scope for T3 (owner decision, 2026-09-26); only
`claude-code` and `codex` are exercised.

Every host write here is confined to `tmp_path`: `Path.home()` and `HOME`
are patched to a throwaway directory, and all instruction files/ledgers live
under `project_root`/`data_root` fixtures. Nothing here ever touches a real
`~/.claude` or `~/.codex`.

Names fixed by this test file (none specified by name in either binding
document -- see receipt):
  - `rush.integrations.agents.plan_agent_instructions(agent_id, *, project_root, data_root=None) -> AgentInstructionPlan`
  - `AgentInstructionPlan(agent_id, target_path, diff, hosts, existing_sha256, conflict)`
  - `rush.integrations.agents.apply_agent_instructions(plan, *, consent) -> AgentInstructionApplyResult`
  - `AgentInstructionApplyResult(status, target_path, conflict)` -- status one of
    "applied" | "unchanged" | "declined" | "conflict"
  - `rush.integrations.agents.disconnect_agent(agent_id, *, project_root, data_root=None) -> AgentDisconnectResult`
  - `AgentDisconnectResult(status, removed, conflicts)`
  - Ownership ledger file `<data_root>/agents/owned.json`: a `CASMapTransaction`
    envelope `{schema_version, version, data}` whose `data` is keyed by entry
    id -> {kind, host, project_root, path, written_sha256, original_sha256,
    rush_version, created_at}, per design brief section 3.
  - CLI: `rush agent connect AGENT_ID --session S --project P --install-guidance`
    and `rush agent disconnect AGENT_ID --project P [--json]`.
  - `AgentConnectionTool` gains `action="disconnect"` (agent_id + project_root).
"""

from __future__ import annotations

import json
import os
import stat
import time
from multiprocessing import Process
from pathlib import Path
from typing import Any

import pytest
from _process_children import spawn_pty_child
from click.testing import CliRunner

from rush.integrations import agents as agents_mod
from rush.integrations.agents import ADAPTERS
from rush.tools.agent_connection import AgentConnectionTool

RUSH_BINARY = "/opt/rush-fixture/bin/rush"  # never resolved; outside repo/.venv


# --- Shared fixtures ---------------------------------------------------------


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    return home


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _ledger_path(data_root: Path) -> Path:
    return data_root / "agents" / "owned.json"


def _read_ledger(data_root: Path) -> dict[str, Any]:
    """Entries keyed by id, read from the `CASMapTransaction` envelope's `data`."""
    path = _ledger_path(data_root)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def _write_ledger(data_root: Path, entries: dict[str, Any]) -> None:
    """Seed the ledger in the `CASMapTransaction` envelope the brief specifies."""
    path = _ledger_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "1.0.0", "version": 1, "data": entries}),
        encoding="utf-8",
    )


def _plan_and_apply(
    agent_id: str, *, project_root: Path, data_root: Path, consent: bool = True
) -> Any:
    plan = agents_mod.plan_agent_instructions(
        agent_id, project_root=project_root, data_root=data_root
    )
    return agents_mod.apply_agent_instructions(plan, consent=consent)


# --- Anchor: consent (non-interactive), idempotence, disconnect twice ------


def test_t03_consent_idempotence_disconnect(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """Non-TTY apply with explicit consent writes one marker pair; an
    identical rerun is a no-op; disconnect removes it; disconnecting again is
    an idempotent no-op `ok`."""
    result = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert result.status == "applied"
    target = project_root / "AGENTS.md"
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert text.count("<!-- rush:begin") == 1
    assert text.count("<!-- rush:end -->") == 1
    ledger = _read_ledger(data_root)
    assert any(e.get("kind") == "instruction_block" for e in ledger.values())

    mtime_after_first = target.stat().st_mtime_ns
    rerun = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert rerun.status == "unchanged"
    assert target.stat().st_mtime_ns == mtime_after_first

    disconnect_once = agents_mod.disconnect_agent(
        "codex", project_root=project_root, data_root=data_root
    )
    assert disconnect_once.status == "ok"
    assert "instruction_block" in disconnect_once.removed
    assert not target.exists() or "<!-- rush:begin" not in target.read_text(
        encoding="utf-8"
    )

    disconnect_twice = agents_mod.disconnect_agent(
        "codex", project_root=project_root, data_root=data_root
    )
    assert disconnect_twice.status == "ok"
    assert disconnect_twice.removed == []


def test_t03_second_host_updates_hosts_field_and_preserves_unrelated_content(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """A second host connecting to the same physical file only touches the
    marker region -- existing unrelated content and the diff stay confined to
    the block."""
    target = project_root / "AGENTS.md"
    target.write_text("UNRELATED PROJECT CONTENT\n", encoding="utf-8")

    first = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert first.status == "applied"

    plan_second = agents_mod.plan_agent_instructions(
        "codex", project_root=project_root, data_root=data_root
    )
    assert "UNRELATED PROJECT CONTENT" not in plan_second.diff

    text_after = target.read_text(encoding="utf-8")
    assert "UNRELATED PROJECT CONTENT" in text_after


# --- Consent: interactive TTY (accept / decline / EOF) ----------------------


def _child_run_agent_connect(project_root: str, session_id: str) -> None:
    from rush.cli import cli

    try:
        cli.main(
            [
                "agent",
                "connect",
                "claude-code",
                "--session",
                session_id,
                "--project",
                project_root,
                "--rush-binary",
                RUSH_BINARY,
                "--allow-cache-write",
                "--allow-artifact-write",
            ],
            standalone_mode=False,
        )
    except BaseException as exc:  # noqa: BLE001 -- child diagnostics only
        # This is the child process's last chance to see any failure
        # before it exits silently; there is no parent-side channel for
        # it (the pty carries the CLI's own stdout/stderr, which the
        # tests already assert on).
        print(f"harness child failed: {exc!r}")


def _fork_interactive_connect(
    project_root: Path, *, session_id: str = "sess-tty"
) -> tuple[int, int]:
    return spawn_pty_child(
        __name__, "_child_run_agent_connect", [str(project_root), session_id]
    )


def _send(master_fd: int, text: str) -> None:
    os.write(master_fd, text.encode("utf-8"))


def _reap(
    pid: int, master_fd: int, *, timeout: float = 5.0, capture: bool = False
) -> str:
    """Wait for the forked child to exit, draining its pty output the whole
    time, and return everything it wrote when `capture` is set (real
    rendered output, not pytest's own stdout capture -- `capfd` never sees
    pty writes).

    Draining is unconditional: a macOS pty holds only 1024 bytes of unread
    output, so a child printing a full preview would otherwise block on
    write before it ever reads the answer."""
    import select

    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master_fd], [], [], 0.05)
        if ready:
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                chunk = b""
            if chunk:
                chunks.append(chunk)
        done_pid, _ = os.waitpid(pid, os.WNOHANG)
        if done_pid == pid:
            break
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    if capture:
        # Drain whatever is left buffered after exit.
        while True:
            ready, _, _ = select.select([master_fd], [], [], 0.05)
            if not ready:
                break
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    os.close(master_fd)
    return b"".join(chunks).decode("utf-8", errors="replace")


def test_t03_consent_interactive_accept_writes_instruction_block(
    fake_home: Path, project_root: Path, capfd: pytest.CaptureFixture
) -> None:
    """A real TTY prompts `[y/N]`; `y` applies the instruction block."""
    with capfd.disabled():
        pid, master_fd = _fork_interactive_connect(project_root)
        time.sleep(0.3)
        _send(master_fd, "y\n")
        _reap(pid, master_fd)

    target = project_root / "CLAUDE.md"
    assert target.exists(), "interactive accept must write the instruction block"
    assert "<!-- rush:begin" in target.read_text(encoding="utf-8")


def test_t03_consent_interactive_decline_leaves_file_absent(
    fake_home: Path, project_root: Path, capfd: pytest.CaptureFixture
) -> None:
    """`n` declines; no instruction file is created, and the reported
    guidance state is `declined` (design item 3), never a silent no-op."""
    with capfd.disabled():
        pid, master_fd = _fork_interactive_connect(project_root)
        time.sleep(0.3)
        _send(master_fd, "n\n")
        output = _reap(pid, master_fd, capture=True)

    assert not (project_root / "CLAUDE.md").exists()
    assert "declined" in output.lower(), output


def test_t03_consent_interactive_eof_declines(
    fake_home: Path, project_root: Path, capfd: pytest.CaptureFixture
) -> None:
    """A real terminal EOF (Ctrl-D) before answering declines -- never
    applies, and is reported as `declined` the same way an explicit `n` is."""
    with capfd.disabled():
        pid, master_fd = _fork_interactive_connect(project_root)
        time.sleep(0.3)
        _send(master_fd, "\x04")  # Ctrl-D: real terminal EOF, not fd close
        output = _reap(pid, master_fd, capture=True)

    assert not (project_root / "CLAUDE.md").exists()
    assert "declined" in output.lower(), output


# --- Consent: non-TTY (CliRunner) ------------------------------------------


def test_t03_non_tty_without_flag_writes_nothing(
    fake_home: Path, project_root: Path
) -> None:
    """Non-interactive `agent connect` with no `--install-guidance` writes no
    instruction file and reports guidance as pending, never applies by
    default."""
    from rush.cli import cli

    runner = CliRunner()
    invocation = runner.invoke(
        cli,
        [
            "agent",
            "connect",
            "codex",
            "--session",
            "sess-1",
            "--project",
            str(project_root),
            "--rush-binary",
            RUSH_BINARY,
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )
    assert not (project_root / "AGENTS.md").exists()
    assert "guidance: pending" in invocation.output.lower(), invocation.output


def test_t03_non_tty_with_install_guidance_and_grants_writes(
    fake_home: Path, project_root: Path
) -> None:
    """`--install-guidance` plus the write grants applies non-interactively."""
    from rush.cli import cli

    runner = CliRunner()
    invocation = runner.invoke(
        cli,
        [
            "agent",
            "connect",
            "codex",
            "--session",
            "sess-1",
            "--project",
            str(project_root),
            "--rush-binary",
            RUSH_BINARY,
            "--install-guidance",
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )
    assert invocation.exit_code == 0, invocation.output
    target = project_root / "AGENTS.md"
    assert target.exists()
    assert "<!-- rush:begin" in target.read_text(encoding="utf-8")


# --- Conflicts: CAS digest mismatch, corrupt/duplicate/unmatched markers ----


def test_t03_conflict_changed_digest_between_preview_and_apply(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """A file mutated after `plan` but before `apply` conflicts without
    overwriting the concurrent edit."""
    target = project_root / "AGENTS.md"
    target.write_text("original\n", encoding="utf-8")

    plan = agents_mod.plan_agent_instructions(
        "codex", project_root=project_root, data_root=data_root
    )
    target.write_text("concurrently edited by someone else\n", encoding="utf-8")

    result = agents_mod.apply_agent_instructions(plan, consent=True)
    assert result.status == "conflict"
    assert target.read_text(encoding="utf-8") == "concurrently edited by someone else\n"


@pytest.mark.parametrize(
    "existing_text",
    [
        "<!-- rush:begin v=1 hosts=codex sha256=deadbeef -->\nbody, no end\n",
        (
            "<!-- rush:begin v=1 hosts=codex sha256=a -->\nbody\n<!-- rush:end -->\n"
            "<!-- rush:begin v=1 hosts=codex sha256=b -->\nbody2\n<!-- rush:end -->\n"
        ),
        "<!-- rush:end -->\nbody with no matching begin\n",
    ],
    ids=["unmatched", "duplicate", "unmatched-end-only"],
)
def test_t03_conflict_corrupt_duplicate_unmatched_markers(
    fake_home: Path, project_root: Path, data_root: Path, existing_text: str
) -> None:
    target = project_root / "AGENTS.md"
    target.write_text(existing_text, encoding="utf-8")
    before = target.read_bytes()

    plan = agents_mod.plan_agent_instructions(
        "codex", project_root=project_root, data_root=data_root
    )
    result = agents_mod.apply_agent_instructions(plan, consent=True)

    assert result.status == "conflict"
    assert target.read_bytes() == before


def test_t03_conflict_user_edited_block_retained(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """A body digest mismatch (user hand-edited the managed block) conflicts
    and leaves the user's edit exactly as-is."""
    first = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert first.status == "applied"
    target = project_root / "AGENTS.md"

    text = target.read_text(encoding="utf-8")
    begin = text.index("<!-- rush:begin")
    begin_line_end = text.index("\n", begin) + 1
    end = text.index("<!-- rush:end -->")
    edited = text[:begin_line_end] + "hand-edited body\n" + text[end:]
    target.write_text(edited, encoding="utf-8")

    plan = agents_mod.plan_agent_instructions(
        "codex", project_root=project_root, data_root=data_root
    )
    result = agents_mod.apply_agent_instructions(plan, consent=True)

    assert result.status == "conflict"
    assert target.read_text(encoding="utf-8") == edited


# --- Mode preservation -------------------------------------------------------


def test_t03_write_preserves_existing_file_mode(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    target = project_root / "AGENTS.md"
    target.write_text("existing\n", encoding="utf-8")
    target.chmod(0o644)

    result = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert result.status == "applied"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


# --- Symlinks ----------------------------------------------------------------


def test_t03_symlinked_claude_md_shares_block_with_codex_agents_md(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """`CLAUDE.md` symlinked to `AGENTS.md` (a common layout) shares one
    physical block; `hosts=` becomes the union of both connected hosts."""
    agents_md = project_root / "AGENTS.md"
    agents_md.write_text("shared file\n", encoding="utf-8")
    claude_md = project_root / "CLAUDE.md"
    claude_md.symlink_to(agents_md)

    codex_result = _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )
    assert codex_result.status == "applied"
    claude_result = _plan_and_apply(
        "claude-code", project_root=project_root, data_root=data_root, consent=True
    )
    assert claude_result.status == "applied"

    text = agents_md.read_text(encoding="utf-8")
    assert text.count("<!-- rush:begin") == 1, "must share one physical block"
    marker_line = next(
        line for line in text.splitlines() if line.startswith("<!-- rush:begin")
    )
    assert "claude-code" in marker_line
    assert "codex" in marker_line


def test_t03_symlink_outside_project_root_conflicts(
    fake_home: Path, project_root: Path, data_root: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("outside content\n", encoding="utf-8")
    claude_md = project_root / "CLAUDE.md"
    claude_md.symlink_to(outside)

    plan = agents_mod.plan_agent_instructions(
        "claude-code", project_root=project_root, data_root=data_root
    )
    assert plan.conflict == "symlink_outside_root"

    result = agents_mod.apply_agent_instructions(plan, consent=True)
    assert result.status == "conflict"
    assert outside.read_text(encoding="utf-8") == "outside content\n"


# --- Concurrency --------------------------------------------------------------


def _worker_apply(project_root_s: str, data_root_s: str) -> None:
    from rush.integrations import agents as worker_agents_mod

    plan = worker_agents_mod.plan_agent_instructions(
        "codex", project_root=Path(project_root_s), data_root=Path(data_root_s)
    )
    worker_agents_mod.apply_agent_instructions(plan, consent=True)


def test_t03_concurrent_connects_yield_one_lock_winner_and_consistent_ledger(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """Two processes racing to connect the same agent/project never corrupt
    the ledger or double-insert the marker pair."""
    procs = [
        Process(target=_worker_apply, args=(str(project_root), str(data_root)))
        for _ in range(2)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=15)
        assert proc.exitcode == 0

    target = project_root / "AGENTS.md"
    text = target.read_text(encoding="utf-8")
    assert text.count("<!-- rush:begin") == 1
    assert text.count("<!-- rush:end -->") == 1

    ledger = _read_ledger(data_root)
    instruction_entries = [
        e for e in ledger.values() if e.get("kind") == "instruction_block"
    ]
    assert len(instruction_entries) == 1


# --- Rollback / recovery-required (fixture ledger, per cross-task note) -----


def test_t03_disconnect_reports_recovery_required_for_concurrently_mutated_component(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """Disconnect/rollback share one conflict contract (design brief items
    7-8): a component whose current bytes no longer match its recorded
    digest is left untouched and reported by name, while every other
    Rush-owned component is still removed cleanly."""
    instruction_path = project_root / "AGENTS.md"
    instruction_path.write_text(
        "<!-- rush:begin v=1 hosts=codex sha256=abc -->\nbody\n<!-- rush:end -->\n",
        encoding="utf-8",
    )
    resource_path = project_root / ".rush" / "skills" / "rush.md"
    resource_path.parent.mkdir(parents=True, exist_ok=True)
    resource_path.write_text("owned resource\n", encoding="utf-8")

    import hashlib

    instruction_digest = hashlib.sha256(instruction_path.read_bytes()).hexdigest()
    resource_digest_recorded = hashlib.sha256(b"owned resource\n").hexdigest()

    _write_ledger(
        data_root,
        {
            "codex:instruction_block:AGENTS.md": {
                "kind": "instruction_block",
                "host": "codex",
                "project_root": str(project_root),
                "path": "AGENTS.md",
                "written_sha256": instruction_digest,
                "original_sha256": None,
                "rush_version": "0.0.0-test",
                "created_at": "2026-09-26T00:00:00Z",
            },
            "codex:file_resource:.rush/skills/rush.md": {
                "kind": "file_resource",
                "host": "codex",
                "project_root": str(project_root),
                "path": ".rush/skills/rush.md",
                "written_sha256": resource_digest_recorded,
                "original_sha256": None,
                "rush_version": "0.0.0-test",
                "created_at": "2026-09-26T00:00:00Z",
            },
        },
    )

    # Concurrent user edit to the resource component after Rush wrote it.
    resource_path.write_text(
        "user changed this after rush wrote it\n", encoding="utf-8"
    )

    result = agents_mod.disconnect_agent(
        "codex", project_root=project_root, data_root=data_root
    )

    assert result.status == "conflict"
    assert not instruction_path.exists()
    assert resource_path.read_text(encoding="utf-8") == (
        "user changed this after rush wrote it\n"
    )
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict["path"] == ".rush/skills/rush.md"
    assert conflict["expected"] == resource_digest_recorded
    assert conflict["actual"] != resource_digest_recorded


# --- Disconnect: shared assets and unrelated entries preserved -------------


def test_t03_disconnect_preserves_unrelated_mcp_and_hook_entries(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    home = fake_home
    config_path = ADAPTERS["codex"].config_paths("Darwin", home)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[mcp_servers.other]\ncommand = "npx"\nargs = ["other"]\n', encoding="utf-8"
    )
    before_unrelated = config_path.read_text(encoding="utf-8")

    _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )

    result = agents_mod.disconnect_agent(
        "codex", project_root=project_root, data_root=data_root
    )
    assert result.status == "ok"
    assert config_path.read_text(encoding="utf-8") == before_unrelated


# --- AgentConnectionTool: disconnect operation, strict fields ---------------


def test_t03_agent_connection_tool_disconnect_operation(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    _plan_and_apply(
        "codex", project_root=project_root, data_root=data_root, consent=True
    )

    tool = AgentConnectionTool()
    result = tool.run(
        "codex",
        action="disconnect",
        project_root=project_root,
        data_root=data_root,
    )
    assert result["status"] == "ok"
    assert isinstance(result["raw"], dict)
    assert result["raw"]["status"] == "ok"
    assert "removed" in result["raw"]
    assert "conflicts" in result["raw"]


# --- CLI: agent disconnect ---------------------------------------------------


def test_t03_cli_agent_disconnect_removes_owned_registration(
    fake_home: Path, project_root: Path
) -> None:
    """Connect and disconnect both go through the CLI, so both resolve
    `data_root` identically (via the same patched `Path.home()`) -- no
    separate `--data-root` flag exists or is needed."""
    from rush.cli import cli

    runner = CliRunner()
    connect = runner.invoke(
        cli,
        [
            "agent",
            "connect",
            "codex",
            "--session",
            "sess-1",
            "--project",
            str(project_root),
            "--rush-binary",
            RUSH_BINARY,
            "--install-guidance",
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )
    assert connect.exit_code == 0, connect.output
    assert (project_root / "AGENTS.md").exists()
    invocation = runner.invoke(
        cli,
        [
            "agent",
            "disconnect",
            "codex",
            "--project",
            str(project_root),
            "--json",
        ],
    )
    assert invocation.exit_code == 0, invocation.output
    payload = json.loads(invocation.output)
    assert payload["status"] == "ok"
    assert not (project_root / "AGENTS.md").exists() or "<!-- rush:begin" not in (
        project_root / "AGENTS.md"
    ).read_text(encoding="utf-8")


# --- Install reconciliation for already-connected agents --------------------


def test_t03_install_acknowledged_agent_yields_guidance_preview(
    fake_home: Path, project_root: Path, data_root: Path
) -> None:
    """InstallTool's already-connected/acknowledged branch (`install.py`
    ~479-488) must still surface a guidance preview instead of silently
    continuing past it -- reconnect is never required (design item 9)."""
    import io
    import platform
    import tarfile

    from rush.integrations.agents import (
        acknowledge_agent_connection,
        apply_agent_registration,
        initialize_agent_memory,
        plan_agent_registration,
    )
    from rush.tools.install import InstallTool, select_release_asset

    home = fake_home
    plan = plan_agent_registration("codex", rush_binary=RUSH_BINARY, home=home)
    apply_agent_registration(plan)
    initialize_agent_memory(
        "codex", "sess-1", project_root=None, data_root=data_root, consent=True
    )
    acknowledge_agent_connection(
        "codex", "sess-1", project_root=None, data_root=data_root
    )

    binary_bytes = (
        b'#!/bin/sh\nif [ "$1" = "--version" ]; then\n  echo 9.9.9\nfi\nexit 0\n'
    )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="rush")
        info.size = len(binary_bytes)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(binary_bytes))
    archive_bytes = buf.getvalue()
    asset_name = select_release_asset(platform.system(), platform.machine())
    import hashlib as _hashlib

    digest = _hashlib.sha256(archive_bytes).hexdigest()
    sums_text = f"{digest}  {asset_name}\n"
    assets = {asset_name: archive_bytes, "SHA256SUMS": sums_text.encode("utf-8")}

    def _fake_downloader(url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        return assets[name]

    from rush.permissions import ExecutionPermissions

    install_dir = project_root.parent / "install-bin"
    tool = InstallTool()
    result = tool.run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader,
        project=None,
        permissions=ExecutionPermissions(
            network=True, download=True, cache_write=True, artifact_write=True
        ),
    )

    agent_reports = {a["agent_id"]: a for a in result["raw"]["agents"]}
    assert agent_reports["codex"]["state"] == "active"
    assert "guidance" in agent_reports["codex"], (
        "an already-connected/acknowledged agent must still surface a "
        "guidance preview (design item 9), not a bare 'active' report"
    )


# --- Apply-time rollback across components (design item 8) -----------------


@pytest.mark.parametrize("concurrent_edit", [False, True], ids=["clean", "concurrent"])
def test_t03_apply_rollback_multi_component(
    fake_home: Path,
    project_root: Path,
    data_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    concurrent_edit: bool,
) -> None:
    """One connect writes the MCP registration, the instruction block and a
    resource. A failure on the third write undoes the first two byte for
    byte and records nothing in the ownership ledger. A component the user
    changed after Rush wrote it is never overwritten by the undo; it comes
    back as `recovery_required{component, path, expected, actual}`."""
    import hashlib

    from rush.permissions import ExecutionPermissions

    config_path = ADAPTERS["codex"].config_paths("Darwin", fake_home)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    prior_config = (
        b'[mcp_servers.other]\ncommand = "npx"\nargs = ["other"]\n\n'
        b'[mcp_servers.rush]\ncommand = "/old/rush"\nargs = ["mcp", "serve"]\n'
    )
    config_path.write_bytes(prior_config)
    instruction_path = project_root / "AGENTS.md"
    prior_instructions = b"# Project rules\n\nKeep this.\n"
    instruction_path.write_bytes(prior_instructions)
    resource_rel = ".rush/skills/rush.md"
    resource_path = project_root / resource_rel

    real_cas_replace = agents_mod.cas_replace_file
    user_edit = b"# Project rules\n\nUser edited during connect.\n"
    rush_written: dict[str, str] = {}

    def failing_third_write(path: Path, data: bytes, **kwargs: Any) -> str:
        if Path(path) == resource_path:
            rush_written["instruction"] = hashlib.sha256(
                instruction_path.read_bytes()
            ).hexdigest()
            if concurrent_edit:
                instruction_path.write_bytes(user_edit)
            raise OSError("injected failure on the resource write")
        return real_cas_replace(path, data, **kwargs)

    monkeypatch.setattr(agents_mod, "cas_replace_file", failing_third_write)

    result = AgentConnectionTool().run(
        "codex",
        action="connect",
        session_id="sess-rollback",
        rush_binary=RUSH_BINARY,
        install_guidance=True,
        project_root=project_root,
        data_root=data_root,
        resources=[
            agents_mod.OwnedResource("file_resource", resource_rel, b"rush skill\n")
        ],
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )

    assert result["status"] == "error"
    assert "instruction" in rush_written, "the resource write was never reached"
    assert config_path.read_bytes() == prior_config
    assert not resource_path.exists()
    assert _read_ledger(data_root) == {}

    recovery = result["raw"]["recovery_required"]
    if not concurrent_edit:
        assert instruction_path.read_bytes() == prior_instructions
        assert recovery == []
        return

    assert instruction_path.read_bytes() == user_edit
    assert recovery == [
        {
            "component": "instruction_block",
            "path": str(instruction_path.resolve()),
            "expected": rush_written["instruction"],
            "actual": hashlib.sha256(user_edit).hexdigest(),
        }
    ]
