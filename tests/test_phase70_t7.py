"""Phase 70 T7 -- Opt-in model-visible post-edit checks.

Test matrix for `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` (## T7,
section 6) and the T7 packet in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` (#### T7).

T7 is entirely unimplemented in this worktree: `rush.integrations.
agent_hooks` does not exist, `rush.cli.cli`'s `agent` group has only
`list`/`connect`/`doctor` (no `hook` subcommand), and `agent connect` has
no `--enable-agent-hooks` flag. T2, T3, T5, T16 and T17 are also
unimplemented predecessors per the task brief. Every case below is
therefore RED today because `rush agent hook <host>` does not exist
(`click`'s own "No such command 'hook'" `UsageError`, exit code 2, not the
required exit 0) -- confirmed by reading `src/rush/cli.py`'s `agent_group`
in full (only `agent_list_cmd`/`agent_connect_cmd`/`agent_doctor_cmd`
registered) and by `rtk find`/`rtk grep` turning up no
`src/rush/integrations/agent_hooks.py` anywhere in this worktree.

Two cases additionally depend on real predecessor behavior that does not
exist yet even once `agent hook` is added, so a correct T7 implementation
alone still cannot make them pass:
- The deadline test depends on T17's not-yet-built "record remaining
  steps as not_run on cancellation" contract. `run_workflow_suite`
  (`src/rush/workflows/suites.py:104-112`, read in full) already accepts
  a `cancel_check` polled between tools and sets
  `metadata["cancelled"] = True`, but on cancellation it `break`s with no
  entry at all for the tool that was about to run or any tool after it --
  it does not synthesize `not_run` children. Labeled RED-via-T17.
- The recovery-handle case depends on T16's unbuilt `result_handle`
  compact-mode contract; only presence of the key is asserted, not its
  internal shape. Labeled RED-via-T16.

Every other case asserts T7's own contract exactly against the current
CHECK_SUITE/`PhysicalRoot`/`SecretRedactor`/`register_project` primitives,
all read in full before writing assertions:
- `src/rush/workflows/suites.py`: `CHECK_SUITE` currently has 5 steps
  (format, lint, typecheck, dead, slop); D5 (plan line 60) adds `test` as
  the 6th, gated on a build grant that does not exist as a central check
  anywhere today (confirmed by grep across `src/rush/tools/test.py` and
  `src/rush/invocation/*.py` -- `TestTool.run` runs pytest unconditionally
  if a project marker exists, with zero permission gate). The
  "activated + faulty file" test therefore also exercises a contract T17
  must add, but is not blocked on T17's existence to run today (it is
  blocked purely on `agent hook` not existing) -- so it is not labeled
  RED-via-T17.
- `src/rush/io/physical_paths.py`'s `PhysicalRoot.open_contained` already
  raises `ContainmentError(code="SYMLINK_DISALLOWED", ...)` for any
  symlink component, which is the primitive a real T7 gate would use for
  the "escaping symlink" scope-exclusion case.
- `src/rush/safety/redactor.py`'s `SecretRedactor`/`SECRET_PATTERNS`
  already redacts `AKIA[0-9A-Z]{16}` to `[REDACTED_AWS_ACCESS_KEY]`; the
  redaction test assumes T7 reuses this existing redactor on finding text
  before emitting `additionalContext`, per the design brief's own X10/T7
  trust-boundary section.
- `src/rush/workflows/projects.py`'s `register_project` is used verbatim
  to obtain a real `project_id` for constructed activation-file fixtures
  (`<data_root>/agent-hooks/activations.json`, schema per brief item 1:
  `{host, project_id, canonical_root, recovery_cache_write}` -- the file
  wraps a list of such records under an `"activations"` key, a test-author
  choice since the brief pins the record shape but not the file's outer
  container).

Two tests (byte-budget, redaction) patch `rush.workflows.suites.
run_workflow_suite` at the module attribute directly, matching the design
brief's own §3 phrase "Shared CheckTool calls `run_workflow_suite`" --
this only takes effect if a real T7 implementation looks it up via
`suites.run_workflow_suite(...)` (module-attribute access) rather than
`from rush.workflows.suites import run_workflow_suite` (a separate bound
name the patch cannot reach); documented here rather than left implicit,
per this file's own no-hedge-without-research rule.

Every OS-level subprocess call an engine makes routes through
`subprocess.run`/`subprocess.Popen` (each engine module binds `
run_subprocess` from `rush.tools.common` at import time, so the
"zero engine calls" guarantee patches the stdlib `subprocess` module
directly, shared by every one of those already-bound references --
same technique as `tests/test_phase70_t9.py`).
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.setup.provision import default_data_root
from rush.workflows import suites as suites_module
from rush.workflows.projects import register_project

pytestmark = pytest.mark.filterwarnings("ignore")

HOSTS = ("claude", "codex")

# tool_name sets per host, per brief §T7 item 3.
_EDIT_TOOL_NAMES = {
    "claude": "Edit",
    "codex": "apply_patch",
}


def _install_subprocess_spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def _spy(argv, *_args, **_kwargs):
        recorded = tuple(argv) if isinstance(argv, (list, tuple)) else (str(argv),)
        calls.append(recorded)
        raise AssertionError(f"unexpected engine subprocess call: {recorded!r}")

    monkeypatch.setattr(subprocess, "run", _spy)
    monkeypatch.setattr(subprocess, "Popen", _spy)
    return calls


def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("RUSH_AGENT_HOOK_ACTIVE", raising=False)
    return home


def _data_root_for(home: Path) -> Path:
    return default_data_root()


def _activations_path(data_root: Path) -> Path:
    return data_root / "agent-hooks" / "activations.json"


def _write_activation(
    data_root: Path,
    *,
    host: str,
    project_id: str,
    canonical_root: str,
    recovery_cache_write: bool = False,
) -> None:
    path = _activations_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {"activations": []}
    if path.exists():
        existing = json.loads(path.read_text())
    existing["activations"].append(
        {
            "host": host,
            "project_id": project_id,
            "canonical_root": canonical_root,
            "recovery_cache_write": recovery_cache_write,
        }
    )
    path.write_text(json.dumps(existing))


def _remove_activations(data_root: Path) -> None:
    path = _activations_path(data_root)
    if path.exists():
        path.write_text(json.dumps({"activations": []}))


def _registered_project(tmp_path: Path, data_root: Path, name: str) -> tuple[Path, str]:
    root = tmp_path / name
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.0.1"\n')
    record = register_project(root, data_root=data_root)
    return root, record.project_id


def _payload(
    *,
    host: str,
    cwd: str,
    tool_name: str,
    file_path: str | None,
    event: str = "PostToolUse",
) -> dict:
    body: dict = {
        "session_id": "s-" + uuid.uuid4().hex[:8],
        "cwd": cwd,
        "hook_event_name": event,
        "tool_name": tool_name,
    }
    if file_path is not None:
        body["tool_input"] = {"file_path": file_path}
    else:
        body["tool_input"] = {}
    return body


def _invoke(host: str, stdin: str):
    return CliRunner().invoke(cli, ["agent", "hook", host], input=stdin)


def _invoke_process(host: str, stdin: str) -> SimpleNamespace:
    """`rush agent hook HOST` as its own process, as a host runs it.

    `CliRunner` swaps the process-global `sys.stdin`/`sys.stdout`, so two
    concurrent in-process invocations read and write each other's streams
    (click documents it as single-threaded only)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from rush.cli import cli; cli(prog_name='rush')",
            "agent",
            "hook",
            host,
        ],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return SimpleNamespace(exit_code=proc.returncode, output=proc.stdout)


def _snapshot(home: Path) -> set[Path]:
    return set(home.rglob("*"))


# ---------------------------------------------------------------------------
# Group A -- every no-op / skip gate condition (brief §T7 section 6, first
# bullet): all exit 0, empty stdout, zero writes, zero engine spawns.
# ---------------------------------------------------------------------------

_NOOP_CASES = (
    "malformed_json",
    "oversize_input",
    "wrong_event",
    "own_tool",
    "env_active",
    "foreign_cwd",
    "symlink_escape",
    "not_activated",
)


@pytest.mark.parametrize("host", HOSTS)
@pytest.mark.parametrize("case", _NOOP_CASES)
def test_t07_native_hook_feedback_noop_cases(
    case: str, host: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook <host>` does not exist (`agent_group` has no
    `hook` command) -- `CliRunner` returns exit code 2 with Click's
    "No such command 'hook'" text, not the required exit 0 with empty
    stdout, so both assertions fail today."""
    calls = _install_subprocess_spy(monkeypatch)
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    tool_name = _EDIT_TOOL_NAMES[host]

    if case != "not_activated":
        _write_activation(
            data_root,
            host=host,
            project_id=project_id,
            canonical_root=str(root.resolve()),
        )

    before = _snapshot(home)
    stdin = ""
    if case == "malformed_json":
        stdin = "{not valid json"
    elif case == "oversize_input":
        # 1 MiB stdin cap (brief item 2): 2 MiB of padding overflows it.
        big_payload = _payload(
            host=host,
            cwd=str(root),
            tool_name=tool_name,
            file_path=str(root / "bad.py"),
        )
        big_payload["padding"] = "x" * (2 * 1024 * 1024)
        stdin = json.dumps(big_payload)
    elif case == "wrong_event":
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name=tool_name,
                file_path=str(root / "bad.py"),
                event="PreToolUse",
            )
        )
    elif case == "own_tool":
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name="mcp__rush__rush_fix",
                file_path=str(root / "bad.py"),
            )
        )
    elif case == "env_active":
        monkeypatch.setenv("RUSH_AGENT_HOOK_ACTIVE", "1")
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name=tool_name,
                file_path=str(root / "bad.py"),
            )
        )
    elif case == "foreign_cwd":
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(foreign),
                tool_name=tool_name,
                file_path=str(foreign / "bad.py"),
            )
        )
    elif case == "symlink_escape":
        outside = tmp_path / "outside.py"
        outside.write_text("import os\n")
        link = root / "linked.py"
        link.symlink_to(outside)
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name=tool_name,
                file_path=str(link),
            )
        )
    elif case == "not_activated":
        stdin = json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name=tool_name,
                file_path=str(root / "bad.py"),
            )
        )

    result = _invoke(host, stdin)

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert calls == []
    assert _snapshot(home) == before


def test_t07_malformed_input_never_parses_payload_as_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trust boundary (brief §T7 section 7): a shell-metacharacter string
    inside `tool_input` must never reach a subprocess argv, even embedded
    in an otherwise well-formed activated event. RED: `rush agent hook`
    does not exist."""
    calls = _install_subprocess_spy(monkeypatch)
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="codex",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    marker = "$(touch /tmp/rush-t07-pwned-marker)"
    stdin = json.dumps(
        _payload(host="codex", cwd=str(root), tool_name="apply_patch", file_path=None)
        | {"tool_input": {"patch": marker}}
    )

    result = _invoke("codex", stdin)

    assert result.exit_code == 0, result.output
    for recorded in calls:
        assert marker not in " ".join(recorded)


# ---------------------------------------------------------------------------
# Group B -- apply_patch / no trustworthy path falls back to project-root
# scope, disclosed (brief §T7 item 4, second bullet).
# ---------------------------------------------------------------------------


def test_t07_apply_patch_with_no_path_falls_back_to_project_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook codex` does not exist. Uses a stubbed
    `run_workflow_suite` (see module docstring) so this asserts only T7's
    own scope-selection and disclosure text, not a real engine run."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="codex",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )

    seen_paths: list[Path] = []

    def _fake_run_workflow_suite(suite, path, permissions, config=None, **kwargs):
        seen_paths.append(Path(path))
        return {
            "tool": "check",
            "status": "ok",
            "duration_ms": 1,
            "summary": "check: clean",
            "findings": [],
        }

    monkeypatch.setattr(suites_module, "run_workflow_suite", _fake_run_workflow_suite)

    stdin = json.dumps(
        _payload(host="codex", cwd=str(root), tool_name="apply_patch", file_path=None)
    )
    result = _invoke("codex", stdin)

    assert result.exit_code == 0, result.output
    assert seen_paths and seen_paths[0].resolve() == root.resolve()
    parsed = json.loads(result.output)
    text = parsed["hookSpecificOutput"]["additionalContext"]
    assert "project" in text.lower()


# ---------------------------------------------------------------------------
# Group C -- activated + real faulty file: exact six-step JSON shape,
# test step denied, overall warn (brief §T7 item 6, bullet 2).
# ---------------------------------------------------------------------------


def test_t07_activated_faulty_file_reports_six_steps_and_denies_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook claude` does not exist. Not RED-via-T17: this
    only needs `agent hook` to exist and call the *existing* 5-step
    CHECK_SUITE plus a 6th `test` step denied for missing build grant --
    a real end-to-end run (ruff genuinely installed), no engine mocked."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    bad = root / "bad.py"
    bad.write_text("import os\n")

    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )
    result = _invoke("claude", stdin)

    assert result.exit_code == 0, result.output
    assert len(result.output.encode("utf-8")) <= 8192
    parsed = json.loads(result.output)
    text = parsed["hookSpecificOutput"]["additionalContext"]
    assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "warn" in text.lower()
    assert "F401" in text
    for step in ("format", "lint", "typecheck", "dead", "slop", "test"):
        assert step in text.lower() or step in text
    assert "build" in text.lower()
    assert f"rush check {root.resolve()} --json" in text


def test_t07_recovery_handle_present_only_with_cache_write_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED-via-T16: T16's compact `result_handle` contract does not exist
    yet. Only the key's presence/absence is asserted, not its shape
    (brief §T7 resolution 2)."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
        recovery_cache_write=True,
    )
    bad = root / "bad.py"
    bad.write_text("import os\n")

    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )
    result = _invoke("claude", stdin)

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    text = parsed["hookSpecificOutput"]["additionalContext"]
    assert "result_handle" in text
    assert f"rush check {root.resolve()} --json" not in text


# ---------------------------------------------------------------------------
# Group D -- two concurrent events get distinct invocation IDs and never
# mix findings (brief §T7 item 6, bullet 3).
# ---------------------------------------------------------------------------


def test_t07_concurrent_events_do_not_mix_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook claude` does not exist. Two real, distinct
    faulty files checked concurrently; each result must mention only its
    own file's unused import, never the other's."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    file_a = root / "a.py"
    file_a.write_text("import os\n")
    file_b = root / "b.py"
    file_b.write_text("import sys\n")

    stdin_a = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(file_a))
    )
    stdin_b = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(file_b))
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_invoke_process, "claude", stdin_a)
        fut_b = pool.submit(_invoke_process, "claude", stdin_b)
        result_a = fut_a.result()
        result_b = fut_b.result()

    assert result_a.exit_code == 0, result_a.output
    assert result_b.exit_code == 0, result_b.output
    text_a = json.loads(result_a.output)["hookSpecificOutput"]["additionalContext"]
    text_b = json.loads(result_b.output)["hookSpecificOutput"]["additionalContext"]
    assert "a.py" in text_a and "os" in text_a
    assert "b.py" not in text_a
    assert "b.py" in text_b and "sys" in text_b
    assert "a.py" not in text_b


# ---------------------------------------------------------------------------
# Group E -- 25s internal deadline cancels remaining steps as not_run
# (brief §T7 item 5/6, bullet 4).
# ---------------------------------------------------------------------------


def test_t07_deadline_cancels_remaining_steps_as_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED-via-T17: forces every `time.monotonic()` read after the first
    to report far past any real deadline, so a cancel_check comparing
    against a captured start fires before the first suite step runs.
    `run_workflow_suite` (read in full, `src/rush/workflows/suites.py:
    104-120`) currently `break`s on a true `cancel_check` with zero
    entries recorded for skipped tools -- it does not yet backfill
    `not_run` children, which T17 must add. Combined with the zero-spawn
    spy: if T7 measures the deadline before spawning any engine, no
    engine subprocess may run either."""
    calls = _install_subprocess_spy(monkeypatch)
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    bad = root / "bad.py"
    bad.write_text("import os\n")

    reads = {"n": 0}

    def _fake_monotonic():
        reads["n"] += 1
        return 0.0 if reads["n"] == 1 else 999_999.0

    monkeypatch.setattr(time, "monotonic", _fake_monotonic)

    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )
    result = _invoke("claude", stdin)

    assert result.exit_code == 0, result.output
    assert len(result.output.encode("utf-8")) <= 8192
    parsed = json.loads(result.output)
    text = parsed["hookSpecificOutput"]["additionalContext"]
    assert "not_run" in text
    assert "warn" in text.lower()
    assert calls == []


# ---------------------------------------------------------------------------
# Group F -- output byte budget (<= 8192 UTF-8 bytes) with "shown N of M"
# and secret redaction (brief §T7 item 6, bullet 5 / item 6, design §3).
# ---------------------------------------------------------------------------


def _stub_many_findings(monkeypatch: pytest.MonkeyPatch, findings: list[dict]) -> None:
    def _fake_run_workflow_suite(suite, path, permissions, config=None, **kwargs):
        return {
            "tool": "check",
            "status": "warn",
            "duration_ms": 1,
            "summary": f"check: {len(findings)} issue(s)",
            "findings": findings,
        }

    monkeypatch.setattr(suites_module, "run_workflow_suite", _fake_run_workflow_suite)


def test_t07_output_stays_within_byte_budget_and_reports_shown_of_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook claude` does not exist. Stubs
    `run_workflow_suite` with 395 synthetic findings (see module
    docstring for why this patch target only works if T7 calls it via
    module-attribute access)."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    findings = [
        {
            "path": "bad.py",
            "line": i,
            "rule": "F401",
            "severity": "warn",
            "message": f"'mod{i}' imported but unused",
        }
        for i in range(395)
    ]
    _stub_many_findings(monkeypatch, findings)
    bad = root / "bad.py"
    bad.write_text("import os\n")

    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )
    result = _invoke("claude", stdin)

    assert result.exit_code == 0, result.output
    raw_bytes = result.output.encode("utf-8")
    assert len(raw_bytes) <= 8192
    parsed = json.loads(result.output)
    text = parsed["hookSpecificOutput"]["additionalContext"]
    assert "395" in text
    assert "shown" in text.lower()


def test_t07_redacts_secret_in_finding_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook claude` does not exist. Stubs
    `run_workflow_suite` with one finding whose message literally
    contains an AWS access key matching `SECRET_PATTERNS`
    (`src/rush/safety/redactor.py:15`); asserts T7 redacts it using the
    existing `SecretRedactor` before emitting `additionalContext`."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    secret = "AKIAABCDEFGHIJKL1234"
    findings = [
        {
            "path": "bad.py",
            "line": 1,
            "rule": "secret-leak",
            "severity": "error",
            "message": f"hardcoded credential found: {secret}",
        }
    ]
    _stub_many_findings(monkeypatch, findings)
    bad = root / "bad.py"
    bad.write_text("import os\n")

    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )
    result = _invoke("claude", stdin)

    assert result.exit_code == 0, result.output
    text = json.loads(result.output)["hookSpecificOutput"]["additionalContext"]
    assert secret not in text
    assert "[REDACTED_AWS_ACCESS_KEY]" in text


# ---------------------------------------------------------------------------
# Group G -- disable/disconnect makes subsequent events a no-op (brief
# §T7 item 6, bullet 6), tested at T7's own activation-read layer.
# ---------------------------------------------------------------------------


def test_t07_removing_activation_makes_subsequent_events_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED: `rush agent hook claude` does not exist. First call is
    activated and must not be a no-op (real finding present); after the
    activation record is removed (simulating disable/disconnect, whose
    own CLI wiring is T2/T3 and out of this task's scope), the identical
    event must become a full no-op with zero engine spawns."""
    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _write_activation(
        data_root,
        host="claude",
        project_id=project_id,
        canonical_root=str(root.resolve()),
    )
    bad = root / "bad.py"
    bad.write_text("import os\n")
    stdin = json.dumps(
        _payload(host="claude", cwd=str(root), tool_name="Edit", file_path=str(bad))
    )

    first = _invoke("claude", stdin)
    assert first.exit_code == 0, first.output
    assert first.output != ""

    _remove_activations(data_root)
    calls = _install_subprocess_spy(monkeypatch)
    before = _snapshot(home)

    second = _invoke("claude", stdin)

    assert second.exit_code == 0, second.output
    assert second.output == ""
    assert calls == []
    assert _snapshot(home) == before


# ---------------------------------------------------------------------------
# Group H -- the activation lifecycle behind `agent connect
# --enable-agent-hooks` / `--disable-agent-hooks` and `agent disconnect`
# (brief §T7 item 1): one owned, ledgered record per (host, project).
# ---------------------------------------------------------------------------


def _stub_clean_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_many_findings(monkeypatch, [])


def test_t07_enable_disable_and_disconnect_manage_owned_activation_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.integrations.agent_hooks import set_hook_activation
    from rush.integrations.agents import disconnect_agent, ownership_ledger_path

    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    _stub_clean_check(monkeypatch)
    bad = root / "bad.py"
    bad.write_text("import os\n")

    def event(host: str) -> str:
        return json.dumps(
            _payload(
                host=host,
                cwd=str(root),
                tool_name=_EDIT_TOOL_NAMES[host],
                file_path=str(bad),
            )
        )

    assert _invoke("claude", event("claude")).output == ""
    first = set_hook_activation("claude-code", root, enable=True, data_root=data_root)
    again = set_hook_activation("claude-code", root, enable=True, data_root=data_root)
    codex = set_hook_activation("codex", root, enable=True, data_root=data_root)
    assert (first["state"], again["state"], codex["state"]) == (
        "applied",
        "unchanged",
        "applied",
    )
    records = json.loads(_activations_path(data_root).read_text())["activations"]
    assert sorted(r["host"] for r in records) == ["claude", "codex"]
    assert all(r["project_id"] == project_id for r in records)
    assert all(r["canonical_root"] == str(root.resolve()) for r in records)
    assert all(r["recovery_cache_write"] is False for r in records)
    ledger = json.loads(ownership_ledger_path(data_root).read_text())
    kinds = [row["kind"] for row in ledger["data"].values()]
    assert kinds.count("hook_activation") == 2
    assert _invoke("claude", event("claude")).output != ""
    assert _invoke("codex", event("codex")).output != ""

    calls = _install_subprocess_spy(monkeypatch)
    result = disconnect_agent(
        "claude-code", project_root=root, data_root=data_root, home=home
    )
    assert "hook_activation" in result.removed, result
    assert calls == []
    records = json.loads(_activations_path(data_root).read_text())["activations"]
    assert [r["host"] for r in records] == ["codex"]
    assert _invoke("claude", event("claude")).output == ""
    assert _invoke("codex", event("codex")).output != ""

    # A record changed since Rush wrote it is kept and reported, not removed.
    edited = [{**records[0], "recovery_cache_write": True}]
    _activations_path(data_root).write_text(json.dumps({"activations": edited}))
    conflict = set_hook_activation("codex", root, enable=False, data_root=data_root)
    assert conflict["state"] == "conflict"
    assert json.loads(_activations_path(data_root).read_text())["activations"] == edited

    _activations_path(data_root).write_text(json.dumps({"activations": records}))
    removed = set_hook_activation("codex", root, enable=False, data_root=data_root)
    assert removed["state"] == "removed"
    assert not _activations_path(data_root).exists()
    assert _invoke("codex", event("codex")).output == ""
    absent = set_hook_activation("codex", root, enable=False, data_root=data_root)
    assert absent["state"] == "absent"


def test_t07_connect_enable_flag_records_activation_with_result_cache_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`agent connect ... --enable-agent-hooks --hook-result-cache` reaches the
    activation writer after the (stubbed) connect transaction succeeds."""
    from rush.tools import agent_connection

    home = _isolated_home(tmp_path, monkeypatch)
    data_root = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data_root, "proj")
    monkeypatch.setattr(
        agent_connection,
        "connect_agent",
        lambda *_a, **_k: {
            "apply": {"ok": True},
            "guidance": {"state": "not_requested"},
        },
    )

    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            "claude-code",
            "--session",
            "s1",
            "--project",
            str(root),
            "--enable-agent-hooks",
            "--hook-result-cache",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "ok", payload
    assert payload["raw"]["hooks"]["state"] == "applied"
    assert "agent hooks: applied" in payload["summary"]
    records = json.loads(_activations_path(data_root).read_text())["activations"]
    assert records == [
        {
            "host": "claude",
            "project_id": project_id,
            "canonical_root": str(root.resolve()),
            "recovery_cache_write": True,
        }
    ]


@pytest.mark.parametrize(
    ("agent", "host"), [("claude-code", "claude"), ("codex", "codex")]
)
@pytest.mark.parametrize("as_json", [True, False])
@pytest.mark.parametrize("enable", [True, False])
def test_t07_public_native_plugin_hooks_preserves_registration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
    host: str,
    as_json: bool,
    enable: bool,
) -> None:
    from rush.integrations.agent_hooks import set_hook_activation
    from rush.integrations.agents import (
        ADAPTERS,
        materialize_agent_plugins,
        ownership_ledger_path,
        record_native_plugin_install,
    )

    home = _isolated_home(tmp_path, monkeypatch)
    data = _data_root_for(home)
    root, _ = _registered_project(tmp_path, data, "proj")
    config = ADAPTERS[agent].config_paths(sys.platform, home)[0]
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        b'{"mcpServers":{"other":{"command":"other"}}}\n'
        if host == "claude"
        else b'# preserve bytes\n[mcp_servers.other]\ncommand = "other"\n'
    )
    config.write_bytes(original)
    roots = materialize_agent_plugins(
        rush_binary=str(Path(sys.executable).resolve()), data_root=data
    )
    record_native_plugin_install(host=host, plugin_root=roots[host], data_root=data)
    if not enable:
        assert (
            set_hook_activation(agent, root, enable=True, data_root=data)["state"]
            == "applied"
        )
    bad = root / "bad.py"
    bad.write_text("import os\n")
    event = json.dumps(
        _payload(
            host=host,
            cwd=str(root),
            tool_name=_EDIT_TOOL_NAMES[host],
            file_path=str(bad),
        )
    )
    assert bool(_invoke(host, event).output) is (not enable)

    if not as_json:
        monkeypatch.setattr("rush.cli.os.isatty", lambda _fd: True)
        monkeypatch.setattr("rush.cli._is_terminal", lambda _out: True)
        monkeypatch.setattr(
            "rush.cli._confirm_guidance",
            lambda _plan: pytest.fail("hook-only connect prompted for guidance"),
        )
    calls = _install_subprocess_spy(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            agent,
            "--session",
            "hook-only",
            "--rush-binary",
            str(Path(sys.executable).resolve()),
            "--project",
            str(root),
            "--enable-agent-hooks" if enable else "--disable-agent-hooks",
            "--allow-cache-write",
            "--allow-artifact-write",
            *(["--json"] if as_json else []),
        ],
    )
    assert result.exit_code == 0, result.output
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["status"] == "ok", payload
        assert payload["raw"]["hooks"]["state"] == ("applied" if enable else "removed")
    else:
        assert f"agent hooks: {'applied' if enable else 'removed'}" in result.output
    assert config.read_bytes() == original
    assert calls == []
    rows = json.loads(ownership_ledger_path(data).read_text())["data"].values()
    assert not any(row["kind"] == "mcp_entry" and row["host"] == agent for row in rows)
    assert bool(_invoke(host, event).output) is enable
    if not enable:
        assert calls == []


def test_t07_disable_with_explicit_guidance_callback_runs_connect_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.integrations.agent_hooks import set_hook_activation
    from rush.integrations.agents import (
        materialize_agent_plugins,
        record_native_plugin_install,
    )
    from rush.permissions import ExecutionPermissions
    from rush.tools.agent_connection import AgentConnectionTool

    home = _isolated_home(tmp_path, monkeypatch)
    data = _data_root_for(home)
    root, _ = _registered_project(tmp_path, data, "proj")
    roots = materialize_agent_plugins(
        rush_binary=str(Path(sys.executable).resolve()), data_root=data
    )
    record_native_plugin_install(
        host="claude", plugin_root=roots["claude"], data_root=data
    )
    assert (
        set_hook_activation("claude-code", root, enable=True, data_root=data)["state"]
        == "applied"
    )
    previews = []

    def decline(plan):
        previews.append(plan)
        return False

    result = AgentConnectionTool().run(
        "claude-code",
        action="connect",
        session_id="explicit-guidance",
        rush_binary=str(Path(sys.executable).resolve()),
        project_root=root,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        home=home,
        data_root=data,
        confirm_guidance=decline,
        agent_hooks="disable",
    )
    assert len(previews) == 1
    assert result["raw"]["guidance"]["state"] == "declined"
    assert result["raw"]["hooks"]["state"] == "removed"


def test_t07_interactive_disable_without_native_plugin_keeps_guidance_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = _isolated_home(tmp_path, monkeypatch)
    data = _data_root_for(home)
    root, _ = _registered_project(tmp_path, data, "proj")
    previews = []
    monkeypatch.setattr("rush.cli.os.isatty", lambda _fd: True)
    monkeypatch.setattr("rush.cli._is_terminal", lambda _out: True)

    def decline(plan):
        previews.append(plan)
        return False

    monkeypatch.setattr("rush.cli._confirm_guidance", decline)
    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            "claude-code",
            "--session",
            "non-native-disable",
            "--rush-binary",
            str(Path(sys.executable).resolve()),
            "--project",
            str(root),
            "--disable-agent-hooks",
            "--allow-cache-write",
            "--allow-artifact-write",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(previews) == 1
    assert "guidance: declined" in result.output
    assert "agent hooks: absent" in result.output


@pytest.mark.parametrize(
    ("agent", "extra", "message"),
    (
        ("cursor", ["--enable-agent-hooks"], "available for"),
        ("claude-code", ["--enable-agent-hooks"], "--project"),
        ("claude-code", ["--hook-result-cache"], "--enable-agent-hooks"),
        (
            "claude-code",
            ["--enable-agent-hooks", "--project", "UNREGISTERED"],
            "rush project add",
        ),
    ),
)
def test_t07_connect_hook_flags_rejected_before_any_write(
    agent: str,
    extra: list[str],
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_subprocess_spy(monkeypatch)
    home = _isolated_home(tmp_path, monkeypatch)
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    args = [str(unregistered) if arg == "UNREGISTERED" else arg for arg in extra]
    before = _snapshot(home)

    result = CliRunner().invoke(
        cli,
        [
            "agent",
            "connect",
            agent,
            "--session",
            "s1",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
            *args,
        ],
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert message in payload["summary"]
    assert calls == []
    assert _snapshot(home) == before


@pytest.mark.parametrize(
    ("agent", "host"), [("claude-code", "claude"), ("codex", "codex")]
)
@pytest.mark.parametrize("cache", [False, True])
def test_t07_shared_native_hook_enable_disable_preserves_config(
    tmp_path, monkeypatch, agent, host, cache
):
    from rush.integrations.agents import (
        ADAPTERS,
        materialize_agent_plugins,
        ownership_ledger_path,
        record_native_plugin_install,
    )
    from rush.permissions import ExecutionPermissions
    from rush.tools.agent_connection import AgentConnectionTool

    home = _isolated_home(tmp_path, monkeypatch)
    data = _data_root_for(home)
    root, project_id = _registered_project(tmp_path, data, "proj")
    config = ADAPTERS[agent].config_paths(sys.platform, home)[0]
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        b'{"mcpServers":{}}\n' if host == "claude" else b"# no manual Rush server\n"
    )
    config.write_bytes(original)
    roots = materialize_agent_plugins(
        rush_binary=str(Path(sys.executable).resolve()), data_root=data
    )
    record_native_plugin_install(host=host, plugin_root=roots[host], data_root=data)
    tool = AgentConnectionTool()
    options = {
        "action": "connect",
        "session_id": "native-hooks",
        "rush_binary": str(Path(sys.executable).resolve()),
        "project_root": root,
        "home": home,
        "data_root": data,
        "permissions": ExecutionPermissions(cache_write=True, artifact_write=True),
    }
    calls = _install_subprocess_spy(monkeypatch)
    before = _snapshot(home)
    for overrides, operation, result_cache, status, message in (
        (
            {"permissions": ExecutionPermissions()},
            "enable",
            False,
            "skipped",
            "requires",
        ),
        ({"session_id": None}, "enable", False, "error", "connect requires session_id"),
        ({"project_root": None}, "enable", False, "error", "pass --project PATH"),
        (
            {},
            "disable",
            True,
            "error",
            "--hook-result-cache needs --enable-agent-hooks",
        ),
    ):
        rejected = tool.run(
            agent,
            agent_hooks=operation,
            hook_result_cache=result_cache,
            **{**options, **overrides},
        )
        assert rejected["status"] == status
        assert message in rejected["summary"]
        assert _snapshot(home) == before
        assert calls == []
    enabled = tool.run(agent, agent_hooks="enable", hook_result_cache=cache, **options)
    assert enabled["status"] == "ok", enabled
    assert enabled["raw"]["hooks"]["state"] == "applied"
    assert json.loads(_activations_path(data).read_text())["activations"] == [
        {
            "host": host,
            "project_id": project_id,
            "canonical_root": str(root.resolve()),
            "recovery_cache_write": cache,
        }
    ]
    assert config.read_bytes() == original
    assert calls == []
    disabled = tool.run(agent, agent_hooks="disable", **options)
    assert disabled["status"] == "ok", disabled
    assert disabled["raw"]["hooks"]["state"] == "removed"
    assert not _activations_path(data).exists()
    assert config.read_bytes() == original
    rows = json.loads(ownership_ledger_path(data).read_text())["data"].values()
    assert not any(row["kind"] == "mcp_entry" and row["host"] == agent for row in rows)
